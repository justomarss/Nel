import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from src.core.runtime import create_runtime_nel
from src.errors import ApplicationError, ProviderError
from src.persistence.fact_migration import migrate_fact_schema_v3_to_v4
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.sqlite import SQLiteDatabase
from src.services.memory_service import (
    MemoryService,
    MemoryWriteResult,
    MemoryWriteStatus,
    memory_fingerprint,
    normalize_memory_text,
)


class InMemoryRepository:
    def __init__(self):
        self.items = []

    def remember(self, text):
        self.items.append(text)

    def recall(self, limit=None):
        items = list(self.items)
        return items if limit is None else items[-limit:]


class FailingRepository(InMemoryRepository):
    def remember(self, text):
        raise OSError("private repository detail")


class RecordingProvider:
    def __init__(self, response="cavab"):
        self.response = response
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.response


class FailingProvider:
    def generate(self, prompt):
        raise ProviderError("private provider detail")


class MemoryServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production_path = Path("memory/nel.sqlite3")
        cls.production_hash = (
            hashlib.sha256(cls.production_path.read_bytes()).hexdigest()
            if cls.production_path.is_file()
            else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls.production_hash is not None:
            actual = hashlib.sha256(
                cls.production_path.read_bytes()
            ).hexdigest()
            if actual != cls.production_hash:
                raise AssertionError("Production database changed during tests.")

    def setUp(self):
        patcher = patch("src.core.nel.Clock.start")
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _database(directory):
        path = Path(directory) / "memory-service.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        migrate_identity_schema_v1_to_v2(
            database,
            "2026-08-02T00:00:01Z",
        )
        migrate_goal_schema_v2_to_v3(
            database,
            "2026-08-02T00:00:02Z",
        )
        migrate_fact_schema_v3_to_v4(
            database,
            "2026-08-02T00:00:03Z",
        )
        return path

    def test_explicit_remember_accepts_and_preserves_literal_text(self):
        repository = InMemoryRepository()
        service = MemoryService(repository)
        literal = "  Ömər\tUnicode yaddaş  "

        result = service.remember_explicit(literal)

        self.assertEqual(result.status, MemoryWriteStatus.ACCEPTED)
        self.assertEqual(result.message, "Yadda saxladım.")
        self.assertEqual(repository.items, [literal])

    def test_duplicate_uses_whitespace_case_and_unicode_normalization(self):
        repository = InMemoryRepository()
        service = MemoryService(repository)
        first = "  ÖMƏR\tüçün  yaddaş "
        equivalent = "o\u0308mər üçün\nyaddaş"

        self.assertEqual(
            service.remember_explicit(first).status,
            MemoryWriteStatus.ACCEPTED,
        )
        duplicate = service.remember_explicit(equivalent)

        self.assertEqual(duplicate.status, MemoryWriteStatus.DUPLICATE)
        self.assertEqual(duplicate.message, "Bu yaddaş artıq mövcuddur.")
        self.assertEqual(repository.items, [first])
        self.assertEqual(
            normalize_memory_text(first),
            normalize_memory_text(equivalent),
        )
        self.assertEqual(
            memory_fingerprint(first),
            memory_fingerprint(equivalent),
        )

    def test_empty_remember_is_rejected_without_repository_write(self):
        repository = InMemoryRepository()
        result = MemoryService(repository).remember_explicit(" \t\n ")

        self.assertEqual(result.status, MemoryWriteStatus.EMPTY)
        self.assertEqual(result.message, "Yadda saxlanacaq mətn boşdur.")
        self.assertEqual(repository.items, [])

    def test_repository_failure_returns_deterministic_safe_result(self):
        service = MemoryService(FailingRepository())

        with self.assertLogs("src.services.memory_service", level="ERROR") as logs:
            result = service.remember_explicit("literal private text")

        self.assertEqual(result.status, MemoryWriteStatus.FAILURE)
        self.assertEqual(result.message, "Yaddaş saxlanıla bilmədi.")
        self.assertIn("Explicit memory write failed (OSError).", logs.output[0])
        self.assertNotIn("literal private text", logs.output[0])
        self.assertNotIn("private repository detail", logs.output[0])

    def test_explicit_remember_never_calls_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            provider = RecordingProvider()
            nel = create_runtime_nel(provider=provider, database_path=path)
            try:
                result = nel.remember("explicit memory")
            finally:
                nel.stop()

        self.assertEqual(result.status, MemoryWriteStatus.ACCEPTED)
        self.assertEqual(provider.prompts, [])

    def test_ordinary_successful_conversation_never_writes_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            provider = RecordingProvider()
            nel = create_runtime_nel(provider=provider, database_path=path)
            try:
                before = nel.memory.recall()
                self.assertEqual(nel.think("Salam"), "cavab")
                after = nel.memory.recall()
            finally:
                nel.stop()

        self.assertEqual(before, after)
        self.assertEqual(len(provider.prompts), 1)

    def test_provider_failure_never_writes_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            nel = create_runtime_nel(
                provider=FailingProvider(),
                database_path=path,
            )
            try:
                before = nel.memory.recall()
                with self.assertRaises(ApplicationError):
                    nel.think("Salam")
                after = nel.memory.recall()
            finally:
                nel.stop()

        self.assertEqual(before, after)

    def test_explicit_memory_survives_restart_and_duplicate_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._database(directory)
            first = create_runtime_nel(
                provider=RecordingProvider(),
                database_path=path,
            )
            try:
                accepted = first.remember("Davamlı yaddaş: Ömər")
            finally:
                first.stop()

            second = create_runtime_nel(
                provider=RecordingProvider(),
                database_path=path,
            )
            try:
                duplicate = second.remember("davamlı   yaddaş: ömər")
                stored = second.memory.recall()
            finally:
                second.stop()

        self.assertEqual(accepted.status, MemoryWriteStatus.ACCEPTED)
        self.assertEqual(duplicate.status, MemoryWriteStatus.DUPLICATE)
        self.assertEqual(stored, ["Davamlı yaddaş: Ömər"])

    def test_cli_remember_uses_deterministic_local_results(self):
        class FakeNel:
            def __init__(self):
                self.payloads = []

            def remember(self, text):
                self.payloads.append(text)
                status = (
                    MemoryWriteStatus.EMPTY
                    if not text
                    else MemoryWriteStatus.ACCEPTED
                )
                messages = {
                    MemoryWriteStatus.EMPTY: "Yadda saxlanacaq mətn boşdur.",
                    MemoryWriteStatus.ACCEPTED: "Yadda saxladım.",
                }
                return MemoryWriteResult(status, messages[status])

            def think(self, text):
                raise AssertionError("/remember must not enter conversation")

            def stop(self):
                pass

        nel = FakeNel()
        with (
            patch.object(main, "create_runtime_nel", return_value=nel),
            patch(
                "builtins.input",
                side_effect=["/remember literal text", "/remember", "exit"],
            ),
            patch("builtins.print") as output,
        ):
            result = main.run()

        self.assertEqual(result, 0)
        self.assertEqual(nel.payloads, ["literal text", ""])
        self.assertEqual(
            [call.args[0] for call in output.call_args_list],
            ["Yadda saxladım.", "Yadda saxlanacaq mətn boşdur."],
        )


if __name__ == "__main__":
    unittest.main()
