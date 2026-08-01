from dotenv import load_dotenv
import os

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


NVIDIA_API_KEY = _required_env("NVIDIA_API_KEY")
NVIDIA_MODEL = _required_env("NVIDIA_MODEL")
NVIDIA_BASE_URL = _required_env("NVIDIA_BASE_URL")
RAW_MEMORY_CONTEXT_LIMIT = _non_negative_int_env(
    "RAW_MEMORY_CONTEXT_LIMIT",
    20,
)
