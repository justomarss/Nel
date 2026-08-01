from dotenv import load_dotenv
import os

load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


NVIDIA_API_KEY = _required_env("NVIDIA_API_KEY")
NVIDIA_MODEL = _required_env("NVIDIA_MODEL")
NVIDIA_BASE_URL = _required_env("NVIDIA_BASE_URL")
