import math
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


DEFAULT_DATABASE_PATH = Path("memory/nel.sqlite3")
DEFAULT_PROVIDER = "nvidia"
DEFAULT_NVIDIA_TIMEOUT_SECONDS = 45.0
DEFAULT_GEMINI_TIMEOUT_SECONDS = 45.0
GEMINI_MODEL_ID = "gemini-3.5-flash-lite"
MAX_NVIDIA_TIMEOUT_SECONDS = 300.0
ENABLE_BACKGROUND_THOUGHTS = False
NVIDIA_INTERACTIVE_TIMEOUT_SECONDS = DEFAULT_NVIDIA_TIMEOUT_SECONDS


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    database_path: Path
    enable_background_thoughts: bool
    provider_name: str
    nvidia_api_key: str | None
    nvidia_model: str | None
    nvidia_base_url: str | None
    nvidia_timeout_seconds: float
    gemini_api_key: str | None
    gemini_model: str
    gemini_timeout_seconds: float


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


def _provider_name(environment) -> str:
    value = _optional_text(environment, "NEL_PROVIDER") or DEFAULT_PROVIDER
    normalized = value.casefold()
    if normalized not in {"gemini", "nvidia"}:
        raise ConfigurationError("Runtime provider selection is invalid.")
    return normalized


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

    provider_name = _provider_name(environment)
    nvidia_api_key = _optional_text(environment, "NVIDIA_API_KEY")
    nvidia_model = _optional_text(environment, "NVIDIA_MODEL")
    nvidia_base_url = _optional_text(environment, "NVIDIA_BASE_URL")
    gemini_api_key = _optional_text(environment, "GEMINI_API_KEY")
    gemini_model = (
        _optional_text(environment, "GEMINI_MODEL") or GEMINI_MODEL_ID
    )
    nvidia_timeout = DEFAULT_NVIDIA_TIMEOUT_SECONDS
    gemini_timeout = DEFAULT_GEMINI_TIMEOUT_SECONDS

    if provider_name == "nvidia":
        nvidia_timeout = _timeout(
            environment,
            "NVIDIA_TIMEOUT_SECONDS",
            DEFAULT_NVIDIA_TIMEOUT_SECONDS,
        )
        if require_provider:
            nvidia_api_key = _required_text(environment, "NVIDIA_API_KEY")
            nvidia_model = _required_text(environment, "NVIDIA_MODEL")
            if len(nvidia_model) > 256:
                raise ConfigurationError("Runtime provider model is invalid.")
            nvidia_base_url = _provider_url(environment)
    else:
        gemini_timeout = _timeout(
            environment,
            "GEMINI_TIMEOUT_SECONDS",
            DEFAULT_GEMINI_TIMEOUT_SECONDS,
        )
        if gemini_model != GEMINI_MODEL_ID:
            raise ConfigurationError("Runtime provider model is invalid.")
        if require_provider:
            gemini_api_key = _required_text(environment, "GEMINI_API_KEY")

    return RuntimeConfig(
        database_path=_database_path(environment),
        enable_background_thoughts=_boolean(
            environment,
            "ENABLE_BACKGROUND_THOUGHTS",
            False,
        ),
        provider_name=provider_name,
        nvidia_api_key=nvidia_api_key,
        nvidia_model=nvidia_model,
        nvidia_base_url=nvidia_base_url,
        nvidia_timeout_seconds=nvidia_timeout,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        gemini_timeout_seconds=gemini_timeout,
    )
