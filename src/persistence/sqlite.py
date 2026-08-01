import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1


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
    def __init__(self, path: str | Path, timeout: float = 5.0):
        self.path = Path(path)
        self.timeout = timeout

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=self.timeout,
            isolation_level=None,
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
