from datetime import datetime, timezone

from src.persistence.sqlite import (
    EXPECTED_COLUMNS,
    EXPECTED_TABLES,
    GOAL_INDEX_DEFINITIONS,
    GOAL_SCHEMA_STATEMENTS,
    GOAL_SCHEMA_VERSION,
    GOAL_TABLE_DEFINITIONS,
    IDENTITY_TRIGGER_DEFINITIONS,
    IDENTITY_TRIGGERS,
    V3_EXPECTED_COLUMNS,
    V3_EXPECTED_TABLES,
    SQLiteDatabase,
    _normalize_schema_sql,
)


class GoalMigrationError(RuntimeError):
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


def _tables(connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _validate_columns(connection, expected_columns, message: str) -> None:
    table_metadata = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_list")
        if row["name"] in expected_columns
    }
    for table, columns_expected in expected_columns.items():
        metadata = table_metadata.get(table)
        if metadata is None or metadata["strict"] != 1:
            raise GoalMigrationError(message)
        columns = tuple(
            (
                row["name"],
                row["type"],
                row["notnull"],
                row["pk"],
            )
            for row in connection.execute(f"PRAGMA table_info({table})")
        )
        if columns != columns_expected:
            raise GoalMigrationError(message)


def _validate_identity_triggers(connection, message: str) -> None:
    triggers = {
        row["name"]: (row["tbl_name"], row["sql"])
        for row in connection.execute(
            "SELECT name, tbl_name, sql FROM sqlite_schema "
            "WHERE type = 'trigger'"
        )
    }
    if set(triggers) != IDENTITY_TRIGGERS:
        raise GoalMigrationError(message)
    for name, (expected_table, expected_sql) in (
        IDENTITY_TRIGGER_DEFINITIONS.items()
    ):
        table, sql = triggers[name]
        if (
            table != expected_table
            or sql is None
            or _normalize_schema_sql(sql)
            != _normalize_schema_sql(expected_sql)
        ):
            raise GoalMigrationError(message)


def _validate_v2_source(connection) -> None:
    integrity = [
        row[0] for row in connection.execute("PRAGMA integrity_check")
    ]
    if integrity != ["ok"]:
        raise GoalMigrationError("Schema v2 integrity check failed.")
    if _schema_versions(connection) != [2]:
        raise GoalMigrationError("Goal migration requires schema version 2.")
    if _tables(connection) != EXPECTED_TABLES:
        raise GoalMigrationError("Schema v2 tables are incompatible.")
    _validate_columns(
        connection,
        EXPECTED_COLUMNS,
        "Schema v2 columns are incompatible.",
    )
    _validate_identity_triggers(
        connection,
        "Schema v2 triggers are incompatible.",
    )
    indexes = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if indexes:
        raise GoalMigrationError("Schema v2 indexes are incompatible.")


def _validate_v3(connection) -> None:
    integrity = [
        row[0] for row in connection.execute("PRAGMA integrity_check")
    ]
    if integrity != ["ok"]:
        raise GoalMigrationError("Schema v3 integrity check failed.")
    if _schema_versions(connection) != [GOAL_SCHEMA_VERSION]:
        raise GoalMigrationError("Schema v3 version is incompatible.")
    if _tables(connection) != V3_EXPECTED_TABLES:
        raise GoalMigrationError("Schema v3 tables are incompatible.")

    _validate_columns(
        connection,
        V3_EXPECTED_COLUMNS,
        "Schema v3 columns are incompatible.",
    )

    table_sql = {
        row["name"]: row["sql"]
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_schema "
            "WHERE type = 'table' AND name IN "
            "('goals_current', 'goals_history')"
        )
    }
    for name, expected_sql in GOAL_TABLE_DEFINITIONS.items():
        sql = table_sql.get(name)
        if (
            sql is None
            or _normalize_schema_sql(sql)
            != _normalize_schema_sql(expected_sql)
        ):
            raise GoalMigrationError("Goal table definition is incompatible.")

    indexes = {
        row["name"]: (row["tbl_name"], row["sql"])
        for row in connection.execute(
            "SELECT name, tbl_name, sql FROM sqlite_schema "
            "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if set(indexes) != set(GOAL_INDEX_DEFINITIONS):
        raise GoalMigrationError("Goal index is incompatible.")
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
            raise GoalMigrationError("Goal index is incompatible.")

    _validate_identity_triggers(
        connection,
        "Schema v3 triggers are incompatible.",
    )


def migrate_goal_schema_v2_to_v3(
    database: SQLiteDatabase,
    applied_at: str | None = None,
) -> bool:
    applied_at = applied_at or _utc_now()
    try:
        with database.transaction() as connection:
            versions = _schema_versions(connection)
            if versions == [GOAL_SCHEMA_VERSION]:
                _validate_v3(connection)
                return False
            if versions != [2]:
                raise GoalMigrationError(
                    "Goal migration requires schema version 2."
                )

            _validate_v2_source(connection)
            for statement in GOAL_SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute("DELETE FROM schema_version")
            connection.execute(
                "INSERT INTO schema_version (version, applied_at) "
                "VALUES (?, ?)",
                (GOAL_SCHEMA_VERSION, applied_at),
            )
            _validate_v3(connection)
            return True
    except GoalMigrationError:
        raise
    except Exception as exc:
        raise GoalMigrationError(
            f"Goal migration failed ({type(exc).__name__})."
        ) from None
