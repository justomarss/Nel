import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from src.brain.providers import NvidiaNimProvider
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
            "assert config.NVIDIA_API_KEY is None; "
            "assert config.NVIDIA_MODEL is None; "
            "assert config.NVIDIA_BASE_URL is None"
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

            with (
                patch("src.core.nel.NVIDIA_API_KEY", None),
                patch("src.core.nel.NVIDIA_MODEL", None),
                patch("src.core.nel.NVIDIA_BASE_URL", None),
                self.assertRaises(ApplicationError) as raised,
            ):
                create_runtime_nel(database_path=path)

        self.assertEqual(
            str(raised.exception),
            "Model provider configuration is unavailable.",
        )

    def test_cli_reports_provider_startup_failure_without_traceback(self):
        error = ApplicationError("Model provider configuration is unavailable.")
        with (
            patch.object(main, "create_runtime_nel", side_effect=error),
            patch("builtins.print") as output,
        ):
            result = main.run()

        self.assertEqual(result, 1)
        output.assert_called_once_with(
            "Nel: Model provider configuration is unavailable.",
            file=main.sys.stderr,
        )


if __name__ == "__main__":
    unittest.main()
