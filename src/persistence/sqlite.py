import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
EXPECTED_TABLES = {
    "schema_version",
    "memory_events",
    "user_facts_current",
    "user_fact_history",
}
EXPECTED_COLUMNS = {
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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

    def validate_existing(self) -> None:
        if not self.require_existing:
            raise RuntimeError(
                "Existing-database validation requires guarded mode."
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
            if tables != EXPECTED_TABLES:
                raise RuntimeError("SQLite schema is not initialized.")

            table_metadata = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_list")
                if row["name"] in EXPECTED_TABLES
            }
            for table, expected_columns in EXPECTED_COLUMNS.items():
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
                if columns != expected_columns:
                    raise RuntimeError("SQLite schema is incompatible.")

            versions = [
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_version ORDER BY version"
                )
            ]
            if versions != [SCHEMA_VERSION]:
                raise UnsupportedSchemaVersion(
                    "Unsupported SQLite schema version."
                )
        finally:
            connection.close()
