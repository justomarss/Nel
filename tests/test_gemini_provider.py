import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.brain.providers import (
    GEMINI_MODEL_ID,
    GeminiProvider,
)
from src.core.config import ConfigurationError, load_runtime_config
from src.core.runtime import create_runtime_nel
from src.errors import ApplicationError, ProviderError
from src.persistence.fact_migration import migrate_fact_schema_v3_to_v4
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.repositories import SQLiteKnowledge
from src.persistence.sqlite import SQLiteDatabase
from src.services.knowledge_service import KnowledgeService


def create_v4_database(path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(path)
    database.initialize("2026-08-02T00:00:00Z")
    migrate_identity_schema_v1_to_v2(database, "2026-08-02T00:00:01Z")
    migrate_goal_schema_v2_to_v3(database, "2026-08-02T00:00:02Z")
    migrate_fact_schema_v3_to_v4(database, "2026-08-02T00:00:03Z")
    return database


class GeminiProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production = Path("memory/nel.sqlite3")
        cls.production_hash = (
            hashlib.sha256(cls.production.read_bytes()).hexdigest()
            if cls.production.is_file()
            else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls.production_hash is not None:
            actual = hashlib.sha256(cls.production.read_bytes()).hexdigest()
            if actual != cls.production_hash:
                raise AssertionError("Production database changed during tests.")

    @staticmethod
    def provider_with_response(text="Salam"):
        models = MagicMock()
        models.generate_content.return_value = SimpleNamespace(text=text)
        client = SimpleNamespace(models=models)
        client_factory = MagicMock(return_value=client)
        patcher = patch("src.brain.providers.genai.Client", client_factory)
        patcher.start()
        provider = GeminiProvider(
            model=GEMINI_MODEL_ID,
            api_key="test-key",
            timeout=12.5,
        )
        return provider, models, client_factory, patcher

    def test_text_generation_timeout_and_retry_configuration(self):
        provider, models, client_factory, patcher = self.provider_with_response()
        self.addCleanup(patcher.stop)

        self.assertEqual(provider.generate("hello"), "Salam")
        request = models.generate_content.call_args.kwargs
        self.assertEqual(request["model"], GEMINI_MODEL_ID)
        self.assertEqual(request["contents"], "hello")
        self.assertIsNone(request["config"].system_instruction)

        http_options = client_factory.call_args.kwargs["http_options"]
        self.assertEqual(http_options.timeout, 12500)
        self.assertEqual(http_options.retry_options.attempts, 1)

    def test_system_instruction_is_sent_through_sdk_config(self):
        provider, models, _factory, patcher = self.provider_with_response()
        self.addCleanup(patcher.stop)

        provider.generate("hello", system_instruction="system rule")

        config = models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.system_instruction, "system rule")

    def test_structured_generation_uses_standard_json_schema(self):
        provider, models, _factory, patcher = self.provider_with_response(
            '{"facts":[]}'
        )
        self.addCleanup(patcher.stop)
        schema = {
            "type": "object",
            "properties": {"facts": {"type": "array"}},
            "required": ["facts"],
        }

        result = provider.generate_structured(
            "extract",
            schema,
            "user_fact_extraction",
        )

        self.assertEqual(result, '{"facts":[]}')
        config = models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.response_json_schema, schema)

    def test_missing_key_wrong_model_and_invalid_timeout_are_rejected(self):
        invalid = (
            {"model": GEMINI_MODEL_ID, "api_key": None, "timeout": 45},
            {
                "model": "gemini-2.5-flash-lite",
                "api_key": "key",
                "timeout": 45,
            },
            {"model": GEMINI_MODEL_ID, "api_key": "key", "timeout": 0},
        )
        with patch("src.brain.providers.genai.Client") as client:
            for values in invalid:
                with self.subTest(values=values), self.assertRaises(ProviderError):
                    GeminiProvider(**values)
        client.assert_not_called()

    def test_configuration_and_request_failures_are_redacted(self):
        with patch(
            "src.brain.providers.genai.Client",
            side_effect=RuntimeError("private API key"),
        ):
            with self.assertRaises(ProviderError) as raised:
                GeminiProvider(GEMINI_MODEL_ID, "test-key")
        self.assertNotIn("private API key", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

        provider, models, _factory, patcher = self.provider_with_response()
        self.addCleanup(patcher.stop)
        models.generate_content.side_effect = TimeoutError("private response")
        with self.assertRaises(ProviderError) as raised:
            provider.generate("hello")
        self.assertEqual(
            str(raised.exception),
            "Gemini request failed (TimeoutError).",
        )
        self.assertNotIn("private response", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

    def test_empty_response_is_rejected(self):
        provider, _models, _factory, patcher = self.provider_with_response(" ")
        self.addCleanup(patcher.stop)
        with self.assertRaises(ProviderError):
            provider.generate("hello")

    def test_each_request_is_stateless_generate_content(self):
        provider, models, _factory, patcher = self.provider_with_response()
        self.addCleanup(patcher.stop)

        provider.generate("first")
        provider.generate("second")

        self.assertEqual(models.generate_content.call_count, 2)
        self.assertEqual(
            [call.kwargs["contents"] for call in models.generate_content.call_args_list],
            ["first", "second"],
        )

    def test_runtime_selects_gemini_and_defaults_explicitly_to_nvidia(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.sqlite3"
            create_v4_database(path)
            factory = lambda **arguments: arguments

            with (
                patch("src.core.runtime.GeminiProvider", return_value="gemini") as gemini,
                patch("src.core.runtime.NvidiaNimProvider") as nvidia,
            ):
                result = create_runtime_nel(
                    nel_factory=factory,
                    database_path=path,
                    environment={
                        "NEL_PROVIDER": "gemini",
                        "GEMINI_API_KEY": "test-key",
                        "GEMINI_MODEL": GEMINI_MODEL_ID,
                    },
                )
            self.assertEqual(result["provider"], "gemini")
            gemini.assert_called_once()
            nvidia.assert_not_called()

            with (
                patch("src.core.runtime.GeminiProvider") as gemini,
                patch("src.core.runtime.NvidiaNimProvider", return_value="nvidia") as nvidia,
            ):
                result = create_runtime_nel(
                    nel_factory=factory,
                    database_path=path,
                    environment={
                        "NVIDIA_API_KEY": "test-key",
                        "NVIDIA_MODEL": "test-model",
                        "NVIDIA_BASE_URL": "https://example.invalid/v1",
                    },
                )
            self.assertEqual(result["provider"], "nvidia")
            nvidia.assert_called_once()
            gemini.assert_not_called()

    def test_invalid_selection_and_missing_selected_credentials_fail_safely(self):
        with self.assertRaises(ConfigurationError):
            load_runtime_config({"NEL_PROVIDER": "unknown"})
        with self.assertRaises(ApplicationError) as raised:
            create_runtime_nel(
                environment={"NEL_PROVIDER": "gemini"},
                database_path="missing.sqlite3",
            )
        self.assertEqual(str(raised.exception), "Runtime configuration is invalid.")

    def test_injected_provider_needs_no_credentials(self):
        config = load_runtime_config(
            {"NEL_PROVIDER": "gemini"},
            require_provider=False,
        )
        self.assertEqual(config.provider_name, "gemini")
        self.assertIsNone(config.gemini_api_key)
        self.assertEqual(config.gemini_model, GEMINI_MODEL_ID)

    def test_context_is_identical_for_gemini_and_nvidia_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.sqlite3"
            create_v4_database(path)
            results = []
            with patch("src.core.nel.Clock.start"):
                for provider_name in ("gemini", "nvidia"):
                    provider = SimpleNamespace(
                        name=provider_name,
                        generate=lambda _prompt: "ok",
                    )
                    nel = create_runtime_nel(
                        provider=provider,
                        database_path=path,
                    )
                    try:
                        results.append(nel.context_assembler.assemble("Salam"))
                    finally:
                        nel.stop()

        self.assertEqual(results[0].canonical_json, results[1].canonical_json)
        self.assertEqual(results[0].context_digest, results[1].context_digest)

    def test_malformed_gemini_extraction_writes_nothing(self):
        provider, models, _factory, patcher = self.provider_with_response(
            "not-json"
        )
        self.addCleanup(patcher.stop)
        with tempfile.TemporaryDirectory() as directory:
            database = create_v4_database(
                Path(directory) / "grounding.sqlite3"
            )
            service = KnowledgeService(
                SimpleNamespace(provider=provider),
                SQLiteKnowledge(database),
            )

            proposals = service.process("Mənim adım Testdir.")

            self.assertEqual(proposals, ())
            self.assertEqual(service.facts(), {})
            models.generate_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
