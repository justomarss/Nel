import math
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


DEFAULT_DATABASE_PATH = Path("memory/nel.sqlite3")
DEFAULT_NVIDIA_TIMEOUT_SECONDS = 45.0
MAX_NVIDIA_TIMEOUT_SECONDS = 300.0
ENABLE_BACKGROUND_THOUGHTS = False
NVIDIA_INTERACTIVE_TIMEOUT_SECONDS = DEFAULT_NVIDIA_TIMEOUT_SECONDS


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    database_path: Path
    enable_background_thoughts: bool
    nvidia_api_key: str | None
    nvidia_model: str | None
    nvidia_base_url: str | None
    nvidia_timeout_seconds: float


def _optional_text(environment, name: str) -> str | None:
    value = environment.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _required_text(environment, name: str) -> str:
    value = _optional_text(environment, name)
    if value is None or any(ord(character) < 32 for character in value):
        raise ConfigurationError("Required runtime configuration is invalid.")
    return value


def _boolean(environment, name: str, default: bool) -> bool:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    if not isinstance(raw_value, str):
        raise ConfigurationError("Runtime boolean configuration is invalid.")
    normalized = raw_value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError("Runtime boolean configuration is invalid.")


def _timeout(environment, name: str, default: float) -> float:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise ConfigurationError("Runtime timeout configuration is invalid.") from None
    if not math.isfinite(value) or not 0 < value <= MAX_NVIDIA_TIMEOUT_SECONDS:
        raise ConfigurationError("Runtime timeout configuration is invalid.")
    return value


def _database_path(environment) -> Path:
    raw_value = environment.get("NEL_DATABASE_PATH")
    if raw_value is None:
        return DEFAULT_DATABASE_PATH
    if not isinstance(raw_value, str) or not raw_value.strip() or "\x00" in raw_value:
        raise ConfigurationError("Runtime database configuration is invalid.")
    return Path(raw_value.strip())


def _provider_url(environment) -> str:
    value = _required_text(environment, "NVIDIA_BASE_URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError("Runtime provider URL is invalid.")
    return value.rstrip("/")


def load_runtime_config(
    environment=None,
    *,
    require_provider: bool = True,
) -> RuntimeConfig:
    if environment is None:
        try:
            load_dotenv()
        except OSError:
            raise ConfigurationError("Runtime configuration is unavailable.") from None
        environment = os.environ

    api_key = _optional_text(environment, "NVIDIA_API_KEY")
    model = _optional_text(environment, "NVIDIA_MODEL")
    base_url = _optional_text(environment, "NVIDIA_BASE_URL")
    timeout = _timeout(
        environment,
        "NVIDIA_TIMEOUT_SECONDS",
        DEFAULT_NVIDIA_TIMEOUT_SECONDS,
    )

    if require_provider:
        api_key = _required_text(environment, "NVIDIA_API_KEY")
        model = _required_text(environment, "NVIDIA_MODEL")
        if len(model) > 256:
            raise ConfigurationError("Runtime provider model is invalid.")
        base_url = _provider_url(environment)

    return RuntimeConfig(
        database_path=_database_path(environment),
        enable_background_thoughts=_boolean(
            environment,
            "ENABLE_BACKGROUND_THOUGHTS",
            False,
        ),
        nvidia_api_key=api_key,
        nvidia_model=model,
        nvidia_base_url=base_url,
        nvidia_timeout_seconds=timeout,
    )
