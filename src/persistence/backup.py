import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.persistence.identity_migration import (
    IDENTITY_BOOTSTRAP,
    IDENTITY_SCHEMA_VERSION,
    IDENTITY_TABLES,
)
from src.persistence.sqlite import (
    GOAL_EXPECTED_COLUMNS,
    GOAL_INDEX_DEFINITIONS,
    GOAL_SCHEMA_VERSION,
    GOAL_TABLE_DEFINITIONS,
    GOAL_TABLES,
    SCHEMA_VERSION,
    _normalize_schema_sql,
)


V1_TABLES = {
    "schema_version",
    "memory_events",
    "user_facts_current",
    "user_fact_history",
}


class BackupError(RuntimeError):
    pass


class BackupValidationError(BackupError):
    pass


@dataclass(frozen=True)
class BackupResult:
    source_path: Path
    destination_path: Path
    timestamp: str
    validation_status: str


@dataclass(frozen=True)
class _Snapshot:
    schema_versions: tuple[int, ...]
    memory_rows: tuple[tuple, ...]
    current_fact_rows: tuple[tuple, ...]
    history_rows: tuple[tuple, ...]
    identity_current_rows: tuple[tuple, ...] = ()
    identity_history_rows: tuple[tuple, ...] = ()
    goal_current_rows: tuple[tuple, ...] = ()
    goal_history_rows: tuple[tuple, ...] = ()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _check_utf8(values) -> None:
    try:
        for value in values:
            if isinstance(value, str):
                if value.encode("utf-8").decode("utf-8") != value:
                    raise BackupValidationError(
                        "Backup Unicode round-trip validation failed."
                    )
    except UnicodeError:
        raise BackupValidationError(
            "Backup Unicode round-trip validation failed."
        ) from None


def _read_and_validate(connection: sqlite3.Connection) -> _Snapshot:
    integrity = [
        row[0] for row in connection.execute("PRAGMA integrity_check")
    ]
    if integrity != ["ok"]:
        raise BackupValidationError("Backup integrity validation failed.")

    try:
        schema_versions = tuple(
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_version ORDER BY version"
            )
        )
    except sqlite3.DatabaseError:
        raise BackupValidationError(
            "Backup schema version is incompatible."
        ) from None
    if schema_versions == (SCHEMA_VERSION,):
        expected_tables = V1_TABLES
    elif schema_versions == (IDENTITY_SCHEMA_VERSION,):
        expected_tables = V1_TABLES | IDENTITY_TABLES
    elif schema_versions == (GOAL_SCHEMA_VERSION,):
        expected_tables = V1_TABLES | IDENTITY_TABLES | GOAL_TABLES
    else:
        raise BackupValidationError("Backup schema version is incompatible.")

    tables = {
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }
    if tables != expected_tables:
        raise BackupValidationError("Backup table validation failed.")

    memory_rows = tuple(
        tuple(row)
        for row in connection.execute(
            """
            SELECT id, content, stored_at, source_id
            FROM memory_events
            ORDER BY id
            """
        )
    )
    memory_ids = [row[0] for row in memory_rows]
    if memory_ids != sorted(memory_ids) or len(memory_ids) != len(set(memory_ids)):
        raise BackupValidationError("Backup memory ordering validation failed.")

    current_fact_rows = tuple(
        tuple(row)
        for row in connection.execute(
            """
            SELECT fact_key, value, version, updated_at
            FROM user_facts_current
            ORDER BY fact_key
            """
        )
    )
    history_rows = tuple(
        tuple(row)
        for row in connection.execute(
            """
            SELECT id, fact_key, value, version, valid_from, superseded_at
            FROM user_fact_history
            ORDER BY fact_key, version
            """
        )
    )
    identity_current_rows = ()
    identity_history_rows = ()
    has_identity = schema_versions in {
        (IDENTITY_SCHEMA_VERSION,),
        (GOAL_SCHEMA_VERSION,),
    }
    if has_identity:
        identity_current_rows = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT identity_key, record_type, value, preference_state,
                       immutable, source_kind, source_reference, version,
                       updated_at
                FROM nel_identity_current
                ORDER BY identity_key
                """
            )
        )
        identity_history_rows = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT id, identity_key, record_type, value, preference_state,
                       immutable, source_kind, source_reference, version,
                       valid_from, superseded_at
                FROM nel_identity_history
                ORDER BY identity_key, version
                """
            )
        )
    counts = tuple(
        connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM memory_events),
                (SELECT COUNT(*) FROM user_facts_current),
                (SELECT COUNT(*) FROM user_fact_history)
            """
        ).fetchone()
    )
    if counts != (
        len(memory_rows),
        len(current_fact_rows),
        len(history_rows),
    ):
        raise BackupValidationError("Backup row-count validation failed.")

    current_versions = {
        row[0]: row[2] for row in current_fact_rows
    }
    history_versions = {}
    for row in history_rows:
        history_versions.setdefault(row[1], []).append(row[3])

    if set(history_versions) - set(current_versions):
        raise BackupValidationError("Backup fact history is inconsistent.")
    for key, version in current_versions.items():
        if version < 1:
            raise BackupValidationError("Backup current facts are inconsistent.")
        if history_versions.get(key, []) != list(range(1, version)):
            raise BackupValidationError("Backup fact history is inconsistent.")

    for row in memory_rows:
        _check_utf8(row)
    for row in current_fact_rows:
        _check_utf8(row)
    for row in history_rows:
        _check_utf8(row)

    if has_identity:
        core = {
            row[0]: row[2]
            for row in identity_current_rows
            if row[1] == "core"
        }
        if core != IDENTITY_BOOTSTRAP:
            raise BackupValidationError("Backup identity core is inconsistent.")

        identity_versions = {
            row[0]: row[7] for row in identity_current_rows
        }
        identity_history_versions = {}
        for row in identity_history_rows:
            identity_history_versions.setdefault(row[1], []).append(row[8])
            if row[2] == "core":
                raise BackupValidationError(
                    "Backup immutable identity history is inconsistent."
                )
        if set(identity_history_versions) - set(identity_versions):
            raise BackupValidationError(
                "Backup identity history is inconsistent."
            )
        for key, version in identity_versions.items():
            if version < 1:
                raise BackupValidationError(
                    "Backup current identity is inconsistent."
                )
            if identity_history_versions.get(key, []) != list(
                range(1, version)
            ):
                raise BackupValidationError(
                    "Backup identity history is inconsistent."
                )
        for row in identity_current_rows:
            _check_utf8(row)
        for row in identity_history_rows:
            _check_utf8(row)

    goal_current_rows = ()
    goal_history_rows = ()
    if schema_versions == (GOAL_SCHEMA_VERSION,):
        table_metadata = {
            row["name"]: row
            for row in connection.execute("PRAGMA table_list")
            if row["name"] in GOAL_EXPECTED_COLUMNS
        }
        for table, expected_columns in GOAL_EXPECTED_COLUMNS.items():
            metadata = table_metadata.get(table)
            if metadata is None or metadata["strict"] != 1:
                raise BackupValidationError(
                    "Backup goal schema is incompatible."
                )

        goal_table_sql = {
            row["name"]: row["sql"]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_schema "
                "WHERE type = 'table' AND name IN "
                "('goals_current', 'goals_history')"
            )
        }
        for name, expected_sql in GOAL_TABLE_DEFINITIONS.items():
            sql = goal_table_sql.get(name)
            if (
                sql is None
                or _normalize_schema_sql(sql)
                != _normalize_schema_sql(expected_sql)
            ):
                raise BackupValidationError(
                    "Backup goal schema is incompatible."
                )
            columns = tuple(
                (
                    row["name"],
                    row["type"],
                    row["notnull"],
                    row["pk"],
                )
                for row in connection.execute(f"PRAGMA table_info({table})")
            )
            if columns != expected_columns:
                raise BackupValidationError(
                    "Backup goal schema is incompatible."
                )

        indexes = {
            row["name"]: (row["tbl_name"], row["sql"])
            for row in connection.execute(
                "SELECT name, tbl_name, sql FROM sqlite_schema "
                "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if set(indexes) != set(GOAL_INDEX_DEFINITIONS):
            raise BackupValidationError("Backup goal index is incompatible.")
        for name, (expected_table, expected_sql) in (
            GOAL_INDEX_DEFINITIONS.items()
        ):
            table, sql = indexes[name]
            if (
                table != expected_table
                or sql is None
                or _normalize_schema_sql(sql)
                != _normalize_schema_sql(expected_sql)
            ):
                raise BackupValidationError(
                    "Backup goal index is incompatible."
                )

        goal_current_rows = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT goal_id, title, description, success_condition,
                       owner, state, priority, deadline, progress_summary,
                       progress_percentage, progress_verification,
                       source_kind, source_reference, approval_reference,
                       revision_reason, version, created_at, updated_at
                FROM goals_current
                ORDER BY goal_id
                """
            )
        )
        goal_history_rows = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT goal_id, title, description, success_condition,
                       owner, state, priority, deadline, progress_summary,
                       progress_percentage, progress_verification,
                       source_kind, source_reference, approval_reference,
                       revision_reason, version, created_at, updated_at,
                       superseded_at
                FROM goals_history
                ORDER BY goal_id, version
                """
            )
        )
        goal_counts = tuple(
            connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM goals_current),
                    (SELECT COUNT(*) FROM goals_history)
                """
            ).fetchone()
        )
        if goal_counts != (
            len(goal_current_rows),
            len(goal_history_rows),
        ):
            raise BackupValidationError(
                "Backup goal row-count validation failed."
            )

        current_goal_versions = {
            row[0]: row[15] for row in goal_current_rows
        }
        goal_history_versions = {}
        for row in goal_history_rows:
            goal_history_versions.setdefault(row[0], []).append(row[15])
        if set(goal_history_versions) - set(current_goal_versions):
            raise BackupValidationError(
                "Backup goal history is inconsistent."
            )
        for goal_id, version in current_goal_versions.items():
            if version < 1 or goal_history_versions.get(goal_id, []) != list(
                range(1, version)
            ):
                raise BackupValidationError(
                    "Backup goal history is inconsistent."
                )
        for row in goal_current_rows:
            _check_utf8(row)
        for row in goal_history_rows:
            _check_utf8(row)

    return _Snapshot(
        schema_versions=schema_versions,
        memory_rows=memory_rows,
        current_fact_rows=current_fact_rows,
        history_rows=history_rows,
        identity_current_rows=identity_current_rows,
        identity_history_rows=identity_history_rows,
        goal_current_rows=goal_current_rows,
        goal_history_rows=goal_history_rows,
    )


def _verify_backup(
    backup_path: Path,
    expected_snapshot: _Snapshot | None = None,
) -> None:
    if not backup_path.is_file():
        raise BackupValidationError("Backup file does not exist.")

    try:
        with tempfile.TemporaryDirectory(prefix="nel-restore-check-") as directory:
            restored_path = Path(directory) / "restored.sqlite3"
            shutil.copy2(backup_path, restored_path)
            connection = _connect_read_only(restored_path)
            try:
                restored_snapshot = _read_and_validate(connection)
            finally:
                connection.close()
    except BackupValidationError:
        raise
    except (OSError, sqlite3.DatabaseError) as exc:
        raise BackupValidationError(
            f"Backup restore verification failed ({type(exc).__name__})."
        ) from None

    if expected_snapshot is not None and restored_snapshot != expected_snapshot:
        raise BackupValidationError(
            "Backup content does not match the source snapshot."
        )


def verify_sqlite_backup(backup_path: str | Path) -> bool:
    _verify_backup(Path(backup_path))
    return True


def _perform_backup(
    source: sqlite3.Connection,
    destination: sqlite3.Connection,
) -> None:
    source.backup(destination)


def _remove_if_exists(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def backup_sqlite_database(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    overwrite: bool = False,
    timestamp: str | None = None,
) -> BackupResult:
    source_path = Path(source_path).resolve()
    destination_path = Path(destination_path).resolve()
    timestamp = timestamp or _utc_now()

    if source_path == destination_path:
        raise BackupError("Backup destination must differ from the source.")
    if not source_path.is_file():
        raise BackupError("Backup source does not exist.")
    if not destination_path.parent.is_dir():
        raise BackupError("Backup destination directory does not exist.")
    if destination_path.exists() and not overwrite:
        raise BackupError("Backup destination already exists.")

    partial_path = None
    source = None
    destination = None
    try:
        source = _connect_read_only(source_path)
        source.execute("BEGIN")
        source_snapshot = _read_and_validate(source)

        descriptor, partial_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.",
            suffix=".partial",
            dir=destination_path.parent,
        )
        os.close(descriptor)
        partial_path = Path(partial_name)
        destination = sqlite3.connect(partial_path)
        _perform_backup(source, destination)
        destination.close()
        destination = None
        source.rollback()

        _verify_backup(partial_path, source_snapshot)

        if overwrite:
            os.replace(partial_path, destination_path)
        else:
            try:
                os.link(partial_path, destination_path)
            except FileExistsError:
                raise BackupError("Backup destination already exists.") from None
            partial_path.unlink()
        partial_path = None
    except BackupError:
        raise
    except (OSError, sqlite3.DatabaseError) as exc:
        raise BackupError(
            f"SQLite backup failed ({type(exc).__name__})."
        ) from None
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            if source.in_transaction:
                source.rollback()
            source.close()
        _remove_if_exists(partial_path)

    return BackupResult(
        source_path=source_path,
        destination_path=destination_path,
        timestamp=timestamp,
        validation_status="validated",
    )
