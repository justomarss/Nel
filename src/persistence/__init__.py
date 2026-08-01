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
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import (
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
    "IdentityMigrationError",
    "SQLiteDatabase",
    "SQLiteKnowledge",
    "SQLiteMemory",
    "UnsupportedSchemaVersion",
    "backup_sqlite_database",
    "migrate_json_to_sqlite",
    "migrate_identity_schema_v1_to_v2",
    "verify_sqlite_backup",
]
