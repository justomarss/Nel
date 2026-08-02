import importlib
import importlib.metadata
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SUPPORTED_PYTHON = (3, 14)
REQUIRED_PACKAGES = {
    "openai": "2.52.0",
    "pydantic": "2.13.4",
    "python-dotenv": "1.2.2",
}
IMPORT_NAMES = {
    "openai": "openai",
    "pydantic": "pydantic",
    "python-dotenv": "dotenv",
}


def verify_environment() -> tuple[str, ...]:
    if sys.version_info[:2] != SUPPORTED_PYTHON:
        raise RuntimeError("Unsupported Python version.")

    statuses = []
    for distribution, expected_version in REQUIRED_PACKAGES.items():
        installed_version = importlib.metadata.version(distribution)
        if installed_version != expected_version:
            raise RuntimeError("Installed dependency version is incompatible.")
        importlib.import_module(IMPORT_NAMES[distribution])
        statuses.append(f"{distribution}={installed_version}")

    for module in (
        "src.core.config",
        "src.core.runtime",
        "src.core.nel",
        "src.context.assembler",
    ):
        importlib.import_module(module)
    return tuple(statuses)


def main() -> int:
    try:
        statuses = verify_environment()
    except Exception as exc:
        print(f"FAIL environment_verification {type(exc).__name__}")
        return 1
    print("PASS environment_verification")
    for status in statuses:
        print(f"STATUS {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
