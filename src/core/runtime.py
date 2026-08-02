import sqlite3

from src.brain.providers import GeminiProvider, NvidiaNimProvider
from src.core.config import ConfigurationError, load_runtime_config
from src.core.nel import Nel
from src.errors import (
    ApplicationError,
    PersistenceOperationError,
    PersistenceStartupError,
    ProviderError,
)
from src.goals import GoalRepository, GoalService
from src.identity import IdentityRepository, IdentityService
from src.persistence.identity_migration import IDENTITY_BOOTSTRAP
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase
from src.services.memory_service import MemoryService


SQLITE_STARTUP_ERROR = "SQLite persistence is unavailable or invalid."


def create_runtime_nel(
    *,
    nel_factory=Nel,
    provider=None,
    database_path=None,
    environment=None,
):
    try:
        configuration = load_runtime_config(
            environment,
            require_provider=provider is None,
        )
        target_path = (
            configuration.database_path
            if database_path is None
            else database_path
        )
        if provider is None:
            if configuration.provider_name == "gemini":
                provider = GeminiProvider(
                    model=configuration.gemini_model,
                    api_key=configuration.gemini_api_key,
                    timeout=configuration.gemini_timeout_seconds,
                )
            else:
                provider = NvidiaNimProvider(
                    model=configuration.nvidia_model,
                    api_key=configuration.nvidia_api_key,
                    base_url=configuration.nvidia_base_url,
                    timeout=configuration.nvidia_timeout_seconds,
                )
    except (ConfigurationError, ProviderError):
        raise ApplicationError("Runtime configuration is invalid.") from None

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
    except (OSError, RuntimeError, sqlite3.Error, PersistenceOperationError):
        raise PersistenceStartupError(SQLITE_STARTUP_ERROR) from None

    arguments = {
        "provider": provider,
        "enable_background_thoughts": configuration.enable_background_thoughts,
        "memory_service": MemoryService(SQLiteMemory(database)),
        "knowledge_repository": SQLiteKnowledge(database),
        "identity_service": identity,
        "goal_service": goals,
    }
    try:
        return nel_factory(**arguments)
    except ProviderError:
        raise ApplicationError(
            "Model provider configuration is unavailable."
        ) from None
