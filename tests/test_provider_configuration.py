import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from src.brain.providers import NvidiaNimProvider
from src.core.config import (
    DEFAULT_NVIDIA_TIMEOUT_SECONDS,
    ConfigurationError,
    load_runtime_config,
)
from src.core.runtime import create_runtime_nel
from src.errors import ApplicationError, ProviderError
from src.persistence.fact_migration import migrate_fact_schema_v3_to_v4
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.sqlite import SQLiteDatabase


class ProviderConfigurationTests(unittest.TestCase):
    def test_runtime_modules_import_without_nvidia_configuration(self):
        environment = dict(os.environ)
        environment.update(
            NVIDIA_API_KEY="",
            NVIDIA_MODEL="",
            NVIDIA_BASE_URL="",
            PYTHONIOENCODING="utf-8",
        )
        command = (
            "import src.core.config as config; "
            "import src.core.runtime; import src.core.nel; "
            "import src.goals.commands; import src.services.fact_commands; "
            "import src.services.memory_commands; "
            "assert callable(config.load_runtime_config)"
        )

        result = subprocess.run(
            [sys.executable, "-c", command],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_provider_rejects_missing_configuration_before_client_creation(self):
        with patch("src.brain.providers.OpenAI") as client:
            with self.assertRaises(ProviderError) as raised:
                NvidiaNimProvider(model=None, api_key=None, base_url=None)

        client.assert_not_called()
        self.assertEqual(
            str(raised.exception),
            "NVIDIA NIM provider configuration is unavailable.",
        )

    def test_provider_redacts_client_construction_failure(self):
        with patch(
            "src.brain.providers.OpenAI",
            side_effect=RuntimeError("private credential detail"),
        ):
            with self.assertRaises(ProviderError) as raised:
                NvidiaNimProvider(
                    model="test-model",
                    api_key="test-key",
                    base_url="https://example.invalid/v1",
                )

        self.assertEqual(
            str(raised.exception),
            "NVIDIA NIM provider configuration failed (RuntimeError).",
        )
        self.assertNotIn("private credential detail", str(raised.exception))

    def test_runtime_redacts_missing_provider_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.sqlite3"
            database = SQLiteDatabase(path)
            database.initialize("2026-08-02T00:00:00Z")
            migrate_identity_schema_v1_to_v2(database)
            migrate_goal_schema_v2_to_v3(database)
            migrate_fact_schema_v3_to_v4(database)

            with self.assertRaises(ApplicationError) as raised:
                create_runtime_nel(database_path=path, environment={})

        self.assertEqual(
            str(raised.exception),
            "Runtime configuration is invalid.",
        )

    def test_runtime_configuration_validates_values_and_boundaries(self):
        valid = {
            "NEL_DATABASE_PATH": "memory/test.sqlite3",
            "ENABLE_BACKGROUND_THOUGHTS": "false",
            "NVIDIA_API_KEY": "test-key",
            "NVIDIA_MODEL": "meta/test-model",
            "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1/",
            "NVIDIA_TIMEOUT_SECONDS": "300",
        }
        configuration = load_runtime_config(valid)
        self.assertEqual(configuration.nvidia_timeout_seconds, 300.0)
        self.assertEqual(
            configuration.nvidia_base_url,
            "https://integrate.api.nvidia.com/v1",
        )
        self.assertFalse(configuration.enable_background_thoughts)

        invalid_overrides = (
            {"ENABLE_BACKGROUND_THOUGHTS": "sometimes"},
            {"ENABLE_BACKGROUND_THOUGHTS": 1},
            {"NVIDIA_TIMEOUT_SECONDS": "not-a-number"},
            {"NVIDIA_TIMEOUT_SECONDS": "0"},
            {"NVIDIA_TIMEOUT_SECONDS": "301"},
            {"NVIDIA_BASE_URL": "not-a-url"},
            {"NVIDIA_BASE_URL": "ftp://example.invalid/v1"},
            {"NVIDIA_MODEL": "bad\nmodel"},
            {"NEL_DATABASE_PATH": "   "},
        )
        for override in invalid_overrides:
            with self.subTest(override=tuple(override)):
                environment = dict(valid)
                environment.update(override)
                with self.assertRaises(ConfigurationError):
                    load_runtime_config(environment)

        self.assertEqual(
            load_runtime_config(valid).nvidia_timeout_seconds,
            DEFAULT_NVIDIA_TIMEOUT_SECONDS
            if "NVIDIA_TIMEOUT_SECONDS" not in valid
            else 300.0,
        )

    def test_injected_provider_does_not_require_nvidia_credentials(self):
        configuration = load_runtime_config({}, require_provider=False)
        self.assertIsNone(configuration.nvidia_api_key)
        self.assertIsNone(configuration.nvidia_model)
        self.assertIsNone(configuration.nvidia_base_url)

    def test_invalid_configuration_cli_has_no_traceback(self):
        environment = dict(os.environ)
        environment.update(
            ENABLE_BACKGROUND_THOUGHTS="invalid",
            PYTHONIOENCODING="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            input="",
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("Nel: Runtime configuration is invalid.", result.stderr)

    def test_cli_reports_provider_startup_failure_without_traceback(self):
        error = ApplicationError("Runtime configuration is invalid.")
        with (
            patch.object(main, "create_runtime_nel", side_effect=error),
            patch("builtins.print") as output,
        ):
            result = main.run()

        self.assertEqual(result, 1)
        output.assert_called_once_with(
            "Nel: Runtime configuration is invalid.",
            file=main.sys.stderr,
        )


if __name__ == "__main__":
    unittest.main()
