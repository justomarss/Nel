from src.persistence.backup import (
    BackupError,
    BackupResult,
    BackupValidationError,
    backup_sqlite_database,
    verify_sqlite_backup,
)
from src.persistence.migration import (
    MigrationError,
    MigrationResult,
    migrate_json_to_sqlite,
)
from src.persistence.identity_migration import (
    IDENTITY_SCHEMA_VERSION,
    IdentityMigrationError,
    migrate_identity_schema_v1_to_v2,
)
from src.persistence.goal_migration import (
    GoalMigrationError,
    migrate_goal_schema_v2_to_v3,
)
from src.persistence.fact_migration import (
    FactMigrationError,
    migrate_fact_schema_v3_to_v4,
)
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import (
    GOAL_SCHEMA_VERSION,
    FACT_SCHEMA_VERSION,
    SCHEMA_VERSION,
    SQLiteDatabase,
    UnsupportedSchemaVersion,
)


__all__ = [
    "SCHEMA_VERSION",
    "BackupError",
    "BackupResult",
    "BackupValidationError",
    "MigrationError",
    "MigrationResult",
    "IDENTITY_SCHEMA_VERSION",
    "GOAL_SCHEMA_VERSION",
    "FACT_SCHEMA_VERSION",
    "FactMigrationError",
    "GoalMigrationError",
    "IdentityMigrationError",
    "SQLiteDatabase",
    "SQLiteKnowledge",
    "SQLiteMemory",
    "UnsupportedSchemaVersion",
    "backup_sqlite_database",
    "migrate_json_to_sqlite",
    "migrate_identity_schema_v1_to_v2",
    "migrate_goal_schema_v2_to_v3",
    "migrate_fact_schema_v3_to_v4",
    "verify_sqlite_backup",
]
