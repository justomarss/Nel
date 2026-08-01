import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from src.core.runtime import create_runtime_nel
from src.errors import ApplicationError, PersistenceStartupError, ProviderError
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase


class FakeProvider:
    def generate(self, prompt: str) -> str:
        if "Should this be stored as a long-term memory?" in prompt:
            return "no"
        return "foreground reply"


class FailingProvider:
    def generate(self, prompt: str) -> str:
        raise ProviderError("private provider detail")


class RuntimeCompositionTests(unittest.TestCase):
    def _database(self, directory, name="nel.sqlite3"):
        path = Path(directory) / name
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        return path, database

    @patch("src.core.nel.Clock.start")
    def test_default_runtime_uses_sqlite_only(self, _clock_start):
        with tempfile.TemporaryDirectory() as directory:
            path, _database = self._database(directory)
            with patch("src.core.runtime.NEL_DATABASE_PATH", path):
                nel = create_runtime_nel(provider=FakeProvider())
            try:
                memory = nel.memory
                knowledge = nel.knowledge.knowledge
                self.assertIsInstance(memory, SQLiteMemory)
                self.assertIsInstance(knowledge, SQLiteKnowledge)
                self.assertIs(memory.database, knowledge.database)
                self.assertEqual(memory.database.path, path)
                self.assertTrue(memory.database.require_existing)
            finally:
                nel.stop()

    def test_missing_database_fails_without_creating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite3"
            with self.assertRaises(PersistenceStartupError) as raised:
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

            self.assertFalse(path.exists())
            self.assertNotIn(str(path), str(raised.exception))

    def test_corrupt_database_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.sqlite3"
            path.write_bytes(b"not a sqlite database")

            with self.assertRaises(PersistenceStartupError):
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

    def test_uninitialized_database_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.sqlite3"
            sqlite3.connect(path).close()

            with self.assertRaises(PersistenceStartupError):
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

    def test_incompatible_schema_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._database(directory)
            with database.transaction() as connection:
                connection.execute("DELETE FROM schema_version")
                connection.execute(
                    "INSERT INTO schema_version (version, applied_at) "
                    "VALUES (2, '2026-08-02T00:00:00Z')"
                )

            with self.assertRaises(PersistenceStartupError):
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

    def test_incompatible_version_one_table_layout_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._database(directory)
            with database.transaction() as connection:
                connection.execute(
                    "ALTER TABLE user_facts_current DROP COLUMN updated_at"
                )

            with self.assertRaises(PersistenceStartupError):
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

    @patch("src.core.nel.Clock.start")
    def test_sqlite_data_survives_nel_reconstruction(self, _clock_start):
        with tempfile.TemporaryDirectory() as directory:
            path, _database = self._database(directory)

            first = create_runtime_nel(
                provider=FakeProvider(),
                database_path=path,
            )
            first.remember("Yaddaş: Ömər")
            first.knowledge.knowledge.set("name", "Ömər")
            first.stop()

            second = create_runtime_nel(
                provider=FakeProvider(),
                database_path=path,
            )
            try:
                self.assertEqual(second.memory.recall(), ["Yaddaş: Ömər"])
                self.assertEqual(second.knowledge.get("name"), "Ömər")
            finally:
                second.stop()

    @patch("src.core.nel.Clock.start")
    def test_provider_failure_does_not_damage_sqlite(self, _clock_start):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._database(directory)
            memory = SQLiteMemory(database)
            knowledge = SQLiteKnowledge(database)
            memory.remember("preserved memory")
            knowledge.set("name", "Ömər")
            before_memory = memory.recall()
            before_facts = knowledge.load()

            nel = create_runtime_nel(
                provider=FailingProvider(),
                database_path=path,
            )
            try:
                with self.assertRaises(ApplicationError):
                    nel.think("Salam")
            finally:
                nel.stop()

            self.assertEqual(memory.recall(), before_memory)
            self.assertEqual(knowledge.load(), before_facts)
            SQLiteDatabase(path, require_existing=True).validate_existing()

    @patch("src.core.nel.Clock.start")
    def test_sqlite_runtime_never_writes_json_or_dual_writes(
        self,
        _clock_start,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory_directory = root / "memory"
            memory_directory.mkdir()
            long_term = memory_directory / "long_term.json"
            knowledge_json = memory_directory / "knowledge.json"
            long_term.write_text(
                json.dumps(["json memory"], ensure_ascii=False),
                encoding="utf-8",
            )
            knowledge_json.write_text(
                json.dumps({"name": "JSON"}, ensure_ascii=False),
                encoding="utf-8",
            )
            original_memory = long_term.read_bytes()
            original_knowledge = knowledge_json.read_bytes()
            path, database = self._database(directory)

            nel = create_runtime_nel(
                provider=FakeProvider(),
                database_path=path,
            )
            nel.remember("sqlite only")
            nel.knowledge.knowledge.set("name", "SQLite")
            nel.stop()

            self.assertEqual(long_term.read_bytes(), original_memory)
            self.assertEqual(knowledge_json.read_bytes(), original_knowledge)
            self.assertEqual(SQLiteMemory(database).recall(), ["sqlite only"])
            self.assertEqual(SQLiteKnowledge(database).get("name"), "SQLite")

    def test_cli_reports_startup_failure_without_constructed_shutdown(self):
        error = PersistenceStartupError(
            "SQLite persistence is unavailable or invalid."
        )
        with (
            patch.object(main, "create_runtime_nel", side_effect=error),
            patch("builtins.print") as output,
        ):
            result = main.run()

        self.assertEqual(result, 1)
        output.assert_called_once_with(
            "Nel: SQLite persistence is unavailable or invalid.",
            file=main.sys.stderr,
        )


if __name__ == "__main__":
    unittest.main()
