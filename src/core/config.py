from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
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


NVIDIA_API_KEY = _optional_env("NVIDIA_API_KEY")
NVIDIA_BASE_URL = _optional_env("NVIDIA_BASE_URL")
NVIDIA_MODEL = _optional_env("NVIDIA_MODEL")
NVIDIA_INTERACTIVE_TIMEOUT_SECONDS = 45.0
NEL_DATABASE_PATH = Path(
    os.getenv("NEL_DATABASE_PATH") or "memory/nel.sqlite3"
)
ENABLE_BACKGROUND_THOUGHTS = _bool_env(
    "ENABLE_BACKGROUND_THOUGHTS",
    False,
)
RAW_MEMORY_CONTEXT_LIMIT = _non_negative_int_env(
    "RAW_MEMORY_CONTEXT_LIMIT",
    20,
)
