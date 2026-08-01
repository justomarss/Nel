from dotenv import load_dotenv
import os
from dataclasses import dataclass
from pathlib import Path

load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _non_negative_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError:
        raise RuntimeError(
            f"Environment variable {name} must be a non-negative integer."
        ) from None

    if value < 0:
        raise RuntimeError(
            f"Environment variable {name} must be a non-negative integer."
        )
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(
        f"Environment variable {name} must be a boolean."
    )


@dataclass(frozen=True)
class PersistenceConfig:
    backend: str
    database_path: Path | None


def load_persistence_config(environ=None) -> PersistenceConfig:
    values = os.environ if environ is None else environ
    backend = values.get("NEL_PERSISTENCE_BACKEND", "json").strip().casefold()
    if backend not in {"json", "sqlite"}:
        raise ValueError(
            "NEL_PERSISTENCE_BACKEND must be json or sqlite."
        )

    if backend == "json":
        return PersistenceConfig(backend="json", database_path=None)

    raw_path = values.get("NEL_DATABASE_PATH", "").strip()
    if not raw_path:
        raise ValueError(
            "NEL_DATABASE_PATH is required for SQLite persistence."
        )

    return PersistenceConfig(
        backend="sqlite",
        database_path=Path(raw_path),
    )


NVIDIA_API_KEY = _required_env("NVIDIA_API_KEY")
NVIDIA_BASE_URL = _required_env("NVIDIA_BASE_URL")
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"
NVIDIA_INTERACTIVE_TIMEOUT_SECONDS = 45.0
ENABLE_BACKGROUND_THOUGHTS = _bool_env(
    "ENABLE_BACKGROUND_THOUGHTS",
    False,
)
RAW_MEMORY_CONTEXT_LIMIT = _non_negative_int_env(
    "RAW_MEMORY_CONTEXT_LIMIT",
    20,
)
