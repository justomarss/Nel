from datetime import datetime, timezone

from src.persistence.sqlite import SQLiteDatabase


IDENTITY_SCHEMA_VERSION = 2
IDENTITY_TABLES = {
    "nel_identity_current",
    "nel_identity_history",
}
IDENTITY_BOOTSTRAP = {
    "identity_id": "nel",
    "display_name": "Nel",
    "nature": "artificial",
    "role": "Ömər’s persistent digital companion",
}

IDENTITY_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE nel_identity_current (
        identity_key TEXT PRIMARY KEY COLLATE BINARY,
        record_type TEXT NOT NULL CHECK (
            record_type IN ('core', 'preference')
        ),
        value TEXT NOT NULL,
        preference_state TEXT CHECK (
            preference_state IS NULL OR preference_state IN (
                'candidate', 'provisional', 'established', 'retired'
            )
        ),
        immutable INTEGER NOT NULL CHECK (immutable IN (0, 1)),
        source_kind TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        updated_at TEXT NOT NULL,
        CHECK (
            (record_type = 'core' AND preference_state IS NULL AND immutable = 1)
            OR
            (record_type = 'preference' AND preference_state IS NOT NULL AND immutable = 0)
        )
    ) STRICT
    """,
    """
    CREATE TABLE nel_identity_history (
        id INTEGER PRIMARY KEY,
        identity_key TEXT NOT NULL COLLATE BINARY,
        record_type TEXT NOT NULL CHECK (
            record_type IN ('core', 'preference')
        ),
        value TEXT NOT NULL,
        preference_state TEXT CHECK (
            preference_state IS NULL OR preference_state IN (
                'candidate', 'provisional', 'established', 'retired'
            )
        ),
        immutable INTEGER NOT NULL CHECK (immutable IN (0, 1)),
        source_kind TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        valid_from TEXT NOT NULL,
        superseded_at TEXT NOT NULL,
        UNIQUE (identity_key, version),
        CHECK (
            (record_type = 'core' AND preference_state IS NULL AND immutable = 1)
            OR
            (record_type = 'preference' AND preference_state IS NOT NULL AND immutable = 0)
        )
    ) STRICT
    """,
    """
    CREATE TRIGGER nel_identity_core_no_update
    BEFORE UPDATE ON nel_identity_current
    WHEN OLD.immutable = 1
    BEGIN
        SELECT RAISE(ABORT, 'immutable identity record');
    END
    """,
    """
    CREATE TRIGGER nel_identity_core_no_delete
    BEFORE DELETE ON nel_identity_current
    WHEN OLD.immutable = 1
    BEGIN
        SELECT RAISE(ABORT, 'immutable identity record');
    END
    """,
)


class IdentityMigrationError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bootstrap_identity(connection, applied_at: str) -> None:
    for key, value in IDENTITY_BOOTSTRAP.items():
        connection.execute(
            """
            INSERT INTO nel_identity_current (
                identity_key,
                record_type,
                value,
                preference_state,
                immutable,
                source_kind,
                source_reference,
                version,
                updated_at
            ) VALUES (?, 'core', ?, NULL, 1, 'bootstrap', 'ADR-015', 1, ?)
            """,
            (key, value, applied_at),
        )


def _validate_v2(connection) -> None:
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    required = {
        "schema_version",
        "memory_events",
        "user_facts_current",
        "user_fact_history",
        *IDENTITY_TABLES,
    }
    if tables != required:
        raise IdentityMigrationError("Schema v2 tables are incompatible.")

    rows = connection.execute(
        """
        SELECT identity_key, value, record_type, preference_state,
               immutable, version
        FROM nel_identity_current
        WHERE record_type = 'core'
        ORDER BY identity_key
        """
    ).fetchall()
    actual = {
        row["identity_key"]: (
            row["value"],
            row["record_type"],
            row["preference_state"],
            row["immutable"],
            row["version"],
        )
        for row in rows
    }
    expected = {
        key: (value, "core", None, 1, 1)
        for key, value in IDENTITY_BOOTSTRAP.items()
    }
    if actual != expected:
        raise IdentityMigrationError("Identity bootstrap is incompatible.")


def migrate_identity_schema_v1_to_v2(
    database: SQLiteDatabase,
    applied_at: str | None = None,
) -> bool:
    applied_at = applied_at or _utc_now()
    try:
        with database.transaction() as connection:
            versions = [
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_version ORDER BY version"
                )
            ]
            if versions == [IDENTITY_SCHEMA_VERSION]:
                _validate_v2(connection)
                return False
            if versions != [1]:
                raise IdentityMigrationError(
                    "Identity migration requires schema version 1."
                )

            existing_identity_tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema "
                    "WHERE type = 'table' AND name IN "
                    "('nel_identity_current', 'nel_identity_history')"
                )
            }
            if existing_identity_tables:
                raise IdentityMigrationError(
                    "Schema v1 contains unexpected identity tables."
                )

            for statement in IDENTITY_SCHEMA_STATEMENTS:
                connection.execute(statement)
            _bootstrap_identity(connection, applied_at)
            connection.execute("DELETE FROM schema_version")
            connection.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (IDENTITY_SCHEMA_VERSION, applied_at),
            )
            _validate_v2(connection)
            return True
    except IdentityMigrationError:
        raise
    except Exception as exc:
        raise IdentityMigrationError(
            f"Identity migration failed ({type(exc).__name__})."
        ) from None
