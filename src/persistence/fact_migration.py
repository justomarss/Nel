from datetime import datetime, timezone

from src.persistence.goal_migration import (
    _tables,
    _validate_columns,
    _validate_identity_triggers,
    _validate_v3,
)
from src.persistence.sqlite import (
    FACT_RETIREMENT_COLUMNS,
    FACT_SCHEMA_VERSION,
    GOAL_INDEX_DEFINITIONS,
    GOAL_TABLE_DEFINITIONS,
    V3_EXPECTED_TABLES,
    V4_EXPECTED_COLUMNS,
    SQLiteDatabase,
    _normalize_schema_sql,
)


class FactMigrationError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _schema_versions(connection) -> list[int]:
    return [
        row["version"]
        for row in connection.execute(
            "SELECT version FROM schema_version ORDER BY version"
        )
    ]


def _validate_v4(connection) -> None:
    integrity = [
        row[0] for row in connection.execute("PRAGMA integrity_check")
    ]
    if integrity != ["ok"]:
        raise FactMigrationError("Schema v4 integrity check failed.")
    if _schema_versions(connection) != [FACT_SCHEMA_VERSION]:
        raise FactMigrationError("Schema v4 version is incompatible.")
    if _tables(connection) != V3_EXPECTED_TABLES:
        raise FactMigrationError("Schema v4 tables are incompatible.")
    _validate_columns(
        connection,
        V4_EXPECTED_COLUMNS,
        "Schema v4 columns are incompatible.",
    )
    _validate_identity_triggers(
        connection,
        "Schema v4 identity triggers are incompatible.",
    )

    table_sql = {
        row["name"]: row["sql"]
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_schema WHERE type = 'table'"
        )
    }
    for name, expected_sql in GOAL_TABLE_DEFINITIONS.items():
        if _normalize_schema_sql(table_sql.get(name) or "") != (
            _normalize_schema_sql(expected_sql)
        ):
            raise FactMigrationError("Schema v4 goal tables are incompatible.")
    for name in ("user_facts_current", "user_fact_history"):
        normalized = _normalize_schema_sql(table_sql.get(name) or "")
        if any(
            _normalize_schema_sql(definition) not in normalized
            for definition in FACT_RETIREMENT_COLUMNS
        ):
            raise FactMigrationError("Schema v4 fact tables are incompatible.")

    indexes = {
        row["name"]: (row["tbl_name"], row["sql"])
        for row in connection.execute(
            "SELECT name, tbl_name, sql FROM sqlite_schema "
            "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if set(indexes) != set(GOAL_INDEX_DEFINITIONS):
        raise FactMigrationError("Schema v4 indexes are incompatible.")
    for name, (expected_table, expected_sql) in (
        GOAL_INDEX_DEFINITIONS.items()
    ):
        table, sql = indexes[name]
        if table != expected_table or _normalize_schema_sql(sql or "") != (
            _normalize_schema_sql(expected_sql)
        ):
            raise FactMigrationError("Schema v4 indexes are incompatible.")


def migrate_fact_schema_v3_to_v4(
    database: SQLiteDatabase,
    applied_at: str | None = None,
) -> bool:
    applied_at = applied_at or _utc_now()
    try:
        with database.transaction() as connection:
            versions = _schema_versions(connection)
            if versions == [FACT_SCHEMA_VERSION]:
                _validate_v4(connection)
                return False
            if versions != [3]:
                raise FactMigrationError(
                    "Fact migration requires schema version 3."
                )

            _validate_v3(connection)
            for table in ("user_facts_current", "user_fact_history"):
                for definition in FACT_RETIREMENT_COLUMNS:
                    connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN {definition}"
                    )
            connection.execute("DELETE FROM schema_version")
            connection.execute(
                "INSERT INTO schema_version (version, applied_at) "
                "VALUES (?, ?)",
                (FACT_SCHEMA_VERSION, applied_at),
            )
            _validate_v4(connection)
    except FactMigrationError:
        raise
    except Exception as exc:
        raise FactMigrationError(
            f"Fact migration failed ({type(exc).__name__})."
        ) from None

    return True
