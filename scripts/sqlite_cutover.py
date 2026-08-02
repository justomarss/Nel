import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.persistence.backup import (
    BackupError,
    backup_sqlite_database,
    verify_sqlite_backup,
)
from src.persistence.migration import MigrationError, migrate_json_to_sqlite
from src.persistence.sqlite import SCHEMA_VERSION, SQLiteDatabase


class CutoverError(RuntimeError):
    def __init__(self, status: str):
        super().__init__(status)
        self.status = status


@dataclass(frozen=True)
class VerificationResult:
    database_hash: str
    logical_hash: str
    counts: dict[str, int]


@dataclass
class OperationReport:
    status: str
    counts: dict[str, int] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)
    statuses: dict[str, str] = field(default_factory=dict)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_directory(timestamp: str) -> str:
    return (
        timestamp.replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace("+", "")
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _logical_hash(rows) -> str:
    payload = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _check_unicode(rows) -> None:
    try:
        for row in rows:
            for value in row:
                if isinstance(value, str):
                    if value.encode("utf-8").decode("utf-8") != value:
                        raise CutoverError("unicode_validation_failed")
    except UnicodeError:
        raise CutoverError("unicode_validation_failed") from None


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    return connection


def verify_database(database_path: str | Path) -> VerificationResult:
    path = Path(database_path)
    try:
        SQLiteDatabase(path, require_existing=True).validate_existing(
            expected_version=SCHEMA_VERSION,
        )
        connection = _connect_read_only(path)
        try:
            memory_rows = [
                tuple(row)
                for row in connection.execute(
                    "SELECT id, content, stored_at, source_id "
                    "FROM memory_events ORDER BY id"
                )
            ]
            current_rows = [
                tuple(row)
                for row in connection.execute(
                    "SELECT fact_key, value, version, updated_at "
                    "FROM user_facts_current ORDER BY fact_key"
                )
            ]
            history_rows = [
                tuple(row)
                for row in connection.execute(
                    "SELECT id, fact_key, value, version, valid_from, "
                    "superseded_at FROM user_fact_history "
                    "ORDER BY fact_key, version"
                )
            ]
        finally:
            connection.close()
    except CutoverError:
        raise
    except (OSError, RuntimeError, sqlite3.Error):
        raise CutoverError("database_validation_failed") from None

    memory_ids = [row[0] for row in memory_rows]
    if memory_ids != sorted(memory_ids) or len(memory_ids) != len(set(memory_ids)):
        raise CutoverError("memory_order_validation_failed")

    current_versions = {row[0]: row[2] for row in current_rows}
    history_versions = {}
    for row in history_rows:
        history_versions.setdefault(row[1], []).append(row[3])

    if set(history_versions) - set(current_versions):
        raise CutoverError("fact_history_validation_failed")
    for key, version in current_versions.items():
        if version < 1:
            raise CutoverError("current_fact_validation_failed")
        if history_versions.get(key, []) != list(range(1, version)):
            raise CutoverError("fact_history_validation_failed")

    _check_unicode(memory_rows)
    _check_unicode(current_rows)
    _check_unicode(history_rows)

    counts = {
        "memory_events": len(memory_rows),
        "user_facts_current": len(current_rows),
        "user_fact_history": len(history_rows),
    }
    return VerificationResult(
        database_hash=_sha256(path),
        logical_hash=_logical_hash(
            [memory_rows, current_rows, history_rows]
        ),
        counts=counts,
    )


def verify_existing(
    database_path: str | Path,
    backup_path: str | Path | None = None,
) -> OperationReport:
    database_path = Path(database_path).resolve()
    result = verify_database(database_path)
    report = OperationReport(
        status="PASS",
        counts=result.counts,
        hashes={"database": result.database_hash},
        paths={"database": database_path},
        statuses={
            "integrity": "validated",
            "schema": "version_1_validated",
            "data": "validated",
        },
    )

    if backup_path is not None:
        backup_path = Path(backup_path).resolve()
        try:
            verify_sqlite_backup(backup_path)
            backup_result = verify_database(backup_path)
        except (BackupError, CutoverError):
            raise CutoverError("backup_validation_failed") from None
        if backup_result.logical_hash != result.logical_hash:
            raise CutoverError("backup_content_mismatch")
        report.hashes["backup"] = backup_result.database_hash
        report.paths["backup"] = backup_path
        report.statuses["backup"] = "validated"

    return report


def _copy_source(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise CutoverError("source_file_missing")
    try:
        with source.open("rb") as input_file, destination.open("xb") as output:
            shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        raise CutoverError("destination_exists") from None
    except OSError:
        raise CutoverError("source_snapshot_failed") from None


def _migrate(
    database: SQLiteDatabase,
    long_term_path: Path,
    knowledge_path: Path,
    timestamp: str,
) -> None:
    try:
        database.initialize(timestamp)
        migrate_json_to_sqlite(
            database,
            long_term_path,
            knowledge_path,
            migrated_at=timestamp,
        )
    except (MigrationError, OSError, RuntimeError, sqlite3.Error):
        raise CutoverError("migration_failed") from None


def _create_validated_backup(database_path: Path, backup_path: Path) -> None:
    try:
        backup_sqlite_database(database_path, backup_path)
        verify_sqlite_backup(backup_path)
    except BackupError:
        raise CutoverError("backup_failed") from None


def rehearse(
    long_term_json: str | Path,
    knowledge_json: str | Path,
) -> OperationReport:
    long_term_json = Path(long_term_json).resolve()
    knowledge_json = Path(knowledge_json).resolve()
    if not long_term_json.is_file() or not knowledge_json.is_file():
        raise CutoverError("source_file_missing")

    source_hashes = {
        "long_term_json": _sha256(long_term_json),
        "knowledge_json": _sha256(knowledge_json),
    }
    timestamp = _utc_now()

    with tempfile.TemporaryDirectory(prefix="nel-sqlite-rehearsal-") as directory:
        workspace = Path(directory)
        memory_copy = workspace / "long_term.json"
        knowledge_copy = workspace / "knowledge.json"
        database_path = workspace / "nel.sqlite3"
        backup_path = workspace / "nel.sqlite3.backup"

        _copy_source(long_term_json, memory_copy)
        _copy_source(knowledge_json, knowledge_copy)
        if (
            _sha256(memory_copy) != source_hashes["long_term_json"]
            or _sha256(knowledge_copy) != source_hashes["knowledge_json"]
        ):
            raise CutoverError("source_snapshot_hash_mismatch")

        _migrate(
            SQLiteDatabase(database_path),
            memory_copy,
            knowledge_copy,
            timestamp,
        )
        result = verify_database(database_path)
        _create_validated_backup(database_path, backup_path)
        backup_result = verify_database(backup_path)
        if backup_result.logical_hash != result.logical_hash:
            raise CutoverError("backup_content_mismatch")

        if (
            _sha256(long_term_json) != source_hashes["long_term_json"]
            or _sha256(knowledge_json) != source_hashes["knowledge_json"]
        ):
            raise CutoverError("source_changed_during_rehearsal")

        return OperationReport(
            status="PASS",
            counts=result.counts,
            hashes={
                **source_hashes,
                "database": result.database_hash,
                "backup": backup_result.database_hash,
            },
            paths={
                "long_term_json": long_term_json,
                "knowledge_json": knowledge_json,
                "workspace": workspace,
                "database": database_path,
                "backup": backup_path,
            },
            statuses={
                "migration": "validated",
                "backup": "validated",
                "sources": "unchanged",
            },
        )


def _application_version() -> str | None:
    try:
        return importlib.metadata.version("nel")
    except importlib.metadata.PackageNotFoundError:
        return None


def _write_manifest(path: Path, manifest: dict) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(
                manifest,
                output,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        path.chmod(stat.S_IREAD)
    except FileExistsError:
        raise CutoverError("manifest_exists") from None
    except OSError:
        raise CutoverError("manifest_publish_failed") from None


def _publish_database(source: Path, destination: Path) -> None:
    _copy_source(source, destination)


def _remove_file(path: Path) -> None:
    try:
        if path.exists():
            path.chmod(stat.S_IWRITE)
            path.unlink()
    except OSError:
        pass


def _make_read_only(path: Path) -> None:
    try:
        path.chmod(stat.S_IREAD)
    except OSError:
        raise CutoverError("snapshot_permission_failed") from None


def _remove_directory(path: Path | None) -> None:
    if path is None:
        return
    try:
        for child in path.rglob("*"):
            if child.is_file():
                child.chmod(stat.S_IWRITE)
        path.chmod(stat.S_IWRITE)
        shutil.rmtree(path)
    except OSError:
        pass


def cutover(
    long_term_json: str | Path,
    knowledge_json: str | Path,
    database_path: str | Path,
    backup_root: str | Path,
    manifest_path: str | Path | None = None,
    *,
    timestamp: str | None = None,
) -> OperationReport:
    long_term_json = Path(long_term_json).resolve()
    knowledge_json = Path(knowledge_json).resolve()
    database_path = Path(database_path).resolve()
    backup_root = Path(backup_root).resolve()
    manifest_path = (
        Path(manifest_path).resolve()
        if manifest_path is not None
        else database_path.with_suffix(database_path.suffix + ".cutover.json")
    )

    if database_path.exists():
        raise CutoverError("database_exists")
    if manifest_path.exists():
        raise CutoverError("manifest_exists")
    if not long_term_json.is_file() or not knowledge_json.is_file():
        raise CutoverError("source_file_missing")
    if not database_path.parent.is_dir() or not manifest_path.parent.is_dir():
        raise CutoverError("destination_directory_missing")

    source_hashes = {
        "long_term_json": _sha256(long_term_json),
        "knowledge_json": _sha256(knowledge_json),
    }
    timestamp = timestamp or _utc_now()
    final_directory = backup_root / _timestamp_directory(timestamp)
    if final_directory.exists():
        raise CutoverError("cutover_directory_exists")

    backup_root.mkdir(parents=True, exist_ok=True)
    staging_directory = Path(
        tempfile.mkdtemp(prefix=".cutover-", dir=backup_root)
    )
    published_directory = None

    try:
        memory_snapshot = staging_directory / "long_term.json"
        knowledge_snapshot = staging_directory / "knowledge.json"
        staged_database = staging_directory / "nel.sqlite3"
        backup_path = staging_directory / "nel.sqlite3.backup"

        _copy_source(long_term_json, memory_snapshot)
        _copy_source(knowledge_json, knowledge_snapshot)
        if (
            _sha256(memory_snapshot) != source_hashes["long_term_json"]
            or _sha256(knowledge_snapshot) != source_hashes["knowledge_json"]
        ):
            raise CutoverError("source_snapshot_hash_mismatch")

        _migrate(
            SQLiteDatabase(staged_database),
            memory_snapshot,
            knowledge_snapshot,
            timestamp,
        )
        result = verify_database(staged_database)
        _create_validated_backup(staged_database, backup_path)
        backup_result = verify_database(backup_path)
        if backup_result.logical_hash != result.logical_hash:
            raise CutoverError("backup_content_mismatch")

        if (
            _sha256(long_term_json) != source_hashes["long_term_json"]
            or _sha256(knowledge_json) != source_hashes["knowledge_json"]
        ):
            raise CutoverError("source_changed_during_cutover")

        manifest = {
            "timestamp": timestamp,
            "schema_version": SCHEMA_VERSION,
            "migration_status": "validated",
            "backup_status": "validated",
            "source_file_hashes": source_hashes,
            "destination_database_hash": result.database_hash,
            "row_counts": result.counts,
        }
        application_version = _application_version()
        if application_version is not None:
            manifest["application_version"] = application_version

        staging_directory.rename(final_directory)
        published_directory = final_directory
        staging_directory = None
        staged_database = final_directory / "nel.sqlite3"
        backup_path = final_directory / "nel.sqlite3.backup"
        memory_snapshot = final_directory / "long_term.json"
        knowledge_snapshot = final_directory / "knowledge.json"

        _publish_database(staged_database, database_path)
        published_result = verify_database(database_path)
        if (
            published_result.database_hash != result.database_hash
            or published_result.logical_hash != result.logical_hash
        ):
            raise CutoverError("database_publish_validation_failed")

        _remove_file(staged_database)
        _make_read_only(memory_snapshot)
        _make_read_only(knowledge_snapshot)
        _write_manifest(manifest_path, manifest)

        return OperationReport(
            status="PASS",
            counts=result.counts,
            hashes={
                **source_hashes,
                "database": result.database_hash,
                "backup": backup_result.database_hash,
            },
            paths={
                "database": database_path,
                "manifest": manifest_path,
                "backup_directory": final_directory,
                "backup": backup_path,
                "long_term_snapshot": memory_snapshot,
                "knowledge_snapshot": knowledge_snapshot,
            },
            statuses={
                "migration": "validated",
                "backup": "validated",
                "manifest": "published_read_only",
                "sources": "unchanged",
            },
        )
    except BaseException:
        _remove_file(manifest_path)
        _remove_file(database_path)
        _remove_directory(published_directory)
        _remove_directory(staging_directory)
        raise


def print_report(report: OperationReport, output=sys.stdout) -> None:
    print(f"STATUS {report.status}", file=output)
    for name, value in sorted(report.counts.items()):
        print(f"COUNT {name} {value}", file=output)
    for name, value in sorted(report.hashes.items()):
        print(f"HASH {name} {value}", file=output)
    for name, value in sorted(report.paths.items()):
        print(f"PATH {name} {value}", file=output)
    for name, value in sorted(report.statuses.items()):
        print(f"STATUS_DETAIL {name} {value}", file=output)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sqlite_cutover")
    commands = parser.add_subparsers(dest="command", required=True)

    rehearse_parser = commands.add_parser("rehearse")
    rehearse_parser.add_argument("--long-term-json", required=True)
    rehearse_parser.add_argument("--knowledge-json", required=True)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--database", required=True)
    verify_parser.add_argument("--backup")

    cutover_parser = commands.add_parser("cutover")
    cutover_parser.add_argument("--long-term-json", required=True)
    cutover_parser.add_argument("--knowledge-json", required=True)
    cutover_parser.add_argument("--database", required=True)
    cutover_parser.add_argument("--backup-root", required=True)
    cutover_parser.add_argument("--manifest")
    return parser


def main(argv=None, output=sys.stdout) -> int:
    del argv
    print_report(
        OperationReport(
            status="FAIL",
            statuses={"operation": "historical_schema_v1_tool_retired"},
        ),
        output,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
