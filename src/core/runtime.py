import sqlite3

from src.core.config import load_persistence_config
from src.core.nel import Nel
from src.errors import PersistenceStartupError
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase


SQLITE_STARTUP_ERROR = "SQLite persistence is unavailable or invalid."


def create_runtime_nel(*, nel_factory=Nel, provider=None, environ=None):
    try:
        settings = load_persistence_config(environ)
    except (AttributeError, TypeError, ValueError):
        raise PersistenceStartupError(
            "Persistence configuration is invalid."
        ) from None

    if settings.backend == "json":
        if provider is None:
            return nel_factory()
        return nel_factory(provider=provider)

    try:
        database = SQLiteDatabase(
            settings.database_path,
            require_existing=True,
        )
        database.validate_existing()
    except (OSError, RuntimeError, sqlite3.Error):
        raise PersistenceStartupError(SQLITE_STARTUP_ERROR) from None

    arguments = {
        "memory_repository": SQLiteMemory(database),
        "knowledge_repository": SQLiteKnowledge(database),
    }
    if provider is not None:
        arguments["provider"] = provider
    return nel_factory(**arguments)
