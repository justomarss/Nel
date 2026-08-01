import sqlite3

from src.core.config import NEL_DATABASE_PATH
from src.core.nel import Nel
from src.errors import PersistenceStartupError
from src.goals import GoalRepository, GoalService
from src.identity import IdentityRepository, IdentityService
from src.persistence.identity_migration import IDENTITY_BOOTSTRAP
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase


SQLITE_STARTUP_ERROR = "SQLite persistence is unavailable or invalid."


def create_runtime_nel(
    *,
    nel_factory=Nel,
    provider=None,
    database_path=None,
):
    target_path = NEL_DATABASE_PATH if database_path is None else database_path
    try:
        database = SQLiteDatabase(
            target_path,
            require_existing=True,
        )
        database.validate_existing()
        identity = IdentityService(IdentityRepository(database))
        goals = GoalService(GoalRepository(database))
        identity_snapshot = identity.snapshot()
        if {
            "identity_id": identity_snapshot.identity_id,
            "display_name": identity_snapshot.display_name,
            "nature": identity_snapshot.nature,
            "role": identity_snapshot.role,
        } != IDENTITY_BOOTSTRAP:
            raise RuntimeError("Identity bootstrap is incompatible.")
    except (OSError, RuntimeError, sqlite3.Error):
        raise PersistenceStartupError(SQLITE_STARTUP_ERROR) from None

    arguments = {
        "memory_repository": SQLiteMemory(database),
        "knowledge_repository": SQLiteKnowledge(database),
        "identity_service": identity,
        "goal_service": goals,
    }
    if provider is not None:
        arguments["provider"] = provider
    return nel_factory(**arguments)
