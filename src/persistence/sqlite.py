import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
ACTIVE_SCHEMA_VERSION = 2
V1_EXPECTED_TABLES = {
    "schema_version",
    "memory_events",
    "user_facts_current",
    "user_fact_history",
}
IDENTITY_TABLES = {
    "nel_identity_current",
    "nel_identity_history",
}
EXPECTED_TABLES = V1_EXPECTED_TABLES | IDENTITY_TABLES
IDENTITY_TRIGGERS = {
    "nel_identity_core_no_update",
    "nel_identity_core_no_delete",
}
IDENTITY_TRIGGER_DEFINITIONS = {
    "nel_identity_core_no_update": (
        "nel_identity_current",
        """
        CREATE TRIGGER nel_identity_core_no_update
        BEFORE UPDATE ON nel_identity_current
        WHEN OLD.immutable = 1
        BEGIN
            SELECT RAISE(ABORT, 'immutable identity record');
        END
        """,
    ),
    "nel_identity_core_no_delete": (
        "nel_identity_current",
        """
        CREATE TRIGGER nel_identity_core_no_delete
        BEFORE DELETE ON nel_identity_current
        WHEN OLD.immutable = 1
        BEGIN
            SELECT RAISE(ABORT, 'immutable identity record');
        END
        """,
    ),
}
V1_EXPECTED_COLUMNS = {
    "schema_version": (
        ("version", "INTEGER", 0, 1),
        ("applied_at", "TEXT", 1, 0),
    ),
    "memory_events": (
        ("id", "INTEGER", 0, 1),
        ("content", "TEXT", 1, 0),
        ("stored_at", "TEXT", 1, 0),
        ("source_id", "TEXT", 0, 0),
    ),
    "user_facts_current": (
        ("fact_key", "TEXT", 1, 1),
        ("value", "TEXT", 1, 0),
        ("version", "INTEGER", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ),
    "user_fact_history": (
        ("id", "INTEGER", 0, 1),
        ("fact_key", "TEXT", 1, 0),
        ("value", "TEXT", 1, 0),
        ("version", "INTEGER", 1, 0),
        ("valid_from", "TEXT", 1, 0),
        ("superseded_at", "TEXT", 1, 0),
    ),
}
IDENTITY_EXPECTED_COLUMNS = {
    "nel_identity_current": (
        ("identity_key", "TEXT", 1, 1),
        ("record_type", "TEXT", 1, 0),
        ("value", "TEXT", 1, 0),
        ("preference_state", "TEXT", 0, 0),
        ("immutable", "INTEGER", 1, 0),
        ("source_kind", "TEXT", 1, 0),
        ("source_reference", "TEXT", 1, 0),
        ("version", "INTEGER", 1, 0),
        ("updated_at", "TEXT", 1, 0),
    ),
    "nel_identity_history": (
        ("id", "INTEGER", 0, 1),
        ("identity_key", "TEXT", 1, 0),
        ("record_type", "TEXT", 1, 0),
        ("value", "TEXT", 1, 0),
        ("preference_state", "TEXT", 0, 0),
        ("immutable", "INTEGER", 1, 0),
        ("source_kind", "TEXT", 1, 0),
        ("source_reference", "TEXT", 1, 0),
        ("version", "INTEGER", 1, 0),
        ("valid_from", "TEXT", 1, 0),
        ("superseded_at", "TEXT", 1, 0),
    ),
}
EXPECTED_COLUMNS = V1_EXPECTED_COLUMNS | IDENTITY_EXPECTED_COLUMNS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_schema_sql(value: str) -> str:
    return " ".join(value.split()).casefold()


class UnsupportedSchemaVersion(RuntimeError):
    pass


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY CHECK (version > 0),
        applied_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_events (
        id INTEGER PRIMARY KEY,
        content TEXT NOT NULL,
        stored_at TEXT NOT NULL,
        source_id TEXT UNIQUE
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS user_facts_current (
        fact_key TEXT PRIMARY KEY COLLATE BINARY,
        value TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        updated_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS user_fact_history (
        id INTEGER PRIMARY KEY,
        fact_key TEXT NOT NULL COLLATE BINARY,
        value TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        valid_from TEXT NOT NULL,
        superseded_at TEXT NOT NULL,
        UNIQUE (fact_key, version)
    ) STRICT
    """,
)


class SQLiteDatabase:
    def __init__(
        self,
        path: str | Path,
        timeout: float = 5.0,
        require_existing: bool = False,
    ):
        self.path = Path(path)
        self.timeout = timeout
        self.require_existing = require_existing

    def connect(self) -> sqlite3.Connection:
        target = self.path
        uri = False
        if self.require_existing:
            if not self.path.is_file():
                raise FileNotFoundError("SQLite database does not exist.")
            target = f"{self.path.resolve().as_uri()}?mode=rw"
            uri = True

        connection = sqlite3.connect(
            target,
            timeout=self.timeout,
            isolation_level=None,
            uri=uri,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def initialize(self, applied_at: str | None = None) -> None:
        applied_at = applied_at or _utc_now()
        with self.transaction() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)

            versions = [
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_version ORDER BY version"
                )
            ]
            if not versions:
                connection.execute(
                    "INSERT INTO schema_version (version, applied_at) "
                    "VALUES (?, ?)",
                    (SCHEMA_VERSION, applied_at),
                )
                return

            if versions != [SCHEMA_VERSION]:
                raise UnsupportedSchemaVersion(
                    "Unsupported SQLite schema version."
                )

    def current_schema_version(self) -> int | None:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_version"
            ).fetchone()
            return row["version"]
        finally:
            connection.close()

    def validate_existing(
        self,
        expected_version: int = ACTIVE_SCHEMA_VERSION,
    ) -> None:
        if not self.require_existing:
            raise RuntimeError(
                "Existing-database validation requires guarded mode."
            )

        if expected_version == SCHEMA_VERSION:
            expected_tables = V1_EXPECTED_TABLES
            expected_columns = V1_EXPECTED_COLUMNS
            expected_triggers = set()
        elif expected_version == ACTIVE_SCHEMA_VERSION:
            expected_tables = EXPECTED_TABLES
            expected_columns = EXPECTED_COLUMNS
            expected_triggers = IDENTITY_TRIGGERS
        else:
            raise UnsupportedSchemaVersion(
                "Unsupported SQLite schema version."
            )

        connection = self.connect()
        try:
            integrity = [
                row[0]
                for row in connection.execute("PRAGMA integrity_check")
            ]
            if integrity != ["ok"]:
                raise RuntimeError("SQLite integrity validation failed.")

            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables != expected_tables:
                raise RuntimeError("SQLite schema is not initialized.")

            table_metadata = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_list")
                if row["name"] in expected_tables
            }
            for table, columns_expected in expected_columns.items():
                if table_metadata[table]["strict"] != 1:
                    raise RuntimeError("SQLite schema is incompatible.")

                columns = tuple(
                    (
                        row["name"],
                        row["type"],
                        row["notnull"],
                        row["pk"],
                    )
                    for row in connection.execute(
                        f"PRAGMA table_info({table})"
                    )
                )
                if columns != columns_expected:
                    raise RuntimeError("SQLite schema is incompatible.")

            triggers = {
                row["name"]: (row["tbl_name"], row["sql"])
                for row in connection.execute(
                    "SELECT name, tbl_name, sql FROM sqlite_schema "
                    "WHERE type = 'trigger'"
                )
            }
            if set(triggers) != expected_triggers:
                raise RuntimeError("SQLite schema is incompatible.")
            for name in expected_triggers:
                expected_table, expected_sql = IDENTITY_TRIGGER_DEFINITIONS[
                    name
                ]
                table, sql = triggers[name]
                if (
                    table != expected_table
                    or sql is None
                    or _normalize_schema_sql(sql)
                    != _normalize_schema_sql(expected_sql)
                ):
                    raise RuntimeError("SQLite schema is incompatible.")

            versions = [
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_version ORDER BY version"
                )
            ]
            if versions != [expected_version]:
                raise UnsupportedSchemaVersion(
                    "Unsupported SQLite schema version."
                )
        finally:
            connection.close()
