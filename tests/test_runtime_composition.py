import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from src.core.runtime import create_runtime_nel
from src.errors import ApplicationError, PersistenceStartupError, ProviderError
from src.goals import GoalCandidate, GoalOwner, GoalService
from src.identity import IdentityService
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.fact_migration import migrate_fact_schema_v3_to_v4
from src.persistence.identity_migration import (
    IDENTITY_BOOTSTRAP,
    migrate_identity_schema_v1_to_v2,
)
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase
from src.services.fact_commands import FactCommandHandler
from src.services.memory_service import MemoryService


class FakeProvider:
    def generate(self, prompt: str) -> str:
        if "Should this be stored as a long-term memory?" in prompt:
            return "no"
        return "foreground reply"


class FailingProvider:
    def generate(self, prompt: str) -> str:
        raise ProviderError("private provider detail")


class RuntimeCompositionTests(unittest.TestCase):
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
            current_hash = hashlib.sha256(
                cls.production_path.read_bytes()
            ).hexdigest()
            if current_hash != cls.production_hash:
                raise AssertionError("Production database changed during tests.")

    def _v1_database(self, directory, name="nel.sqlite3"):
        path = Path(directory) / name
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        return path, database

    def _v2_database(self, directory, name="nel.sqlite3"):
        path, database = self._v1_database(directory, name)
        migrate_identity_schema_v1_to_v2(
            database,
            "2026-08-02T01:00:00Z",
        )
        return path, database

    def _v3_database(self, directory, name="nel.sqlite3"):
        path, database = self._v2_database(directory, name)
        migrate_goal_schema_v2_to_v3(
            database,
            "2026-08-02T02:00:00Z",
        )
        return path, database

    def _database(self, directory, name="nel.sqlite3"):
        path, database = self._v3_database(directory, name)
        migrate_fact_schema_v3_to_v4(
            database,
            "2026-08-02T03:00:00Z",
        )
        return path, database

    @staticmethod
    def _create_goal(service):
        return service.create(
            GoalCandidate(
                title="Temporary goal",
                success_condition="Explicitly accepted in the test",
                owner=GoalOwner.USER,
                source_kind="validated_user",
                source_reference="test:runtime",
            ),
            explicit_user_approval=True,
            approval_reference="test:approval",
        )

    @patch("src.core.nel.Clock.start")
    def test_default_runtime_uses_schema_v4_sqlite_only(self, _clock_start):
        with tempfile.TemporaryDirectory() as directory:
            path, _database = self._database(directory)
            nel = create_runtime_nel(
                provider=FakeProvider(),
                environment={"NEL_DATABASE_PATH": str(path)},
            )
            try:
                memory = nel.memory
                memory_repository = memory.repository
                knowledge = nel.knowledge.knowledge
                self.assertIsInstance(memory, MemoryService)
                self.assertIsInstance(memory_repository, SQLiteMemory)
                self.assertIsInstance(knowledge, SQLiteKnowledge)
                self.assertIsInstance(nel.identity, IdentityService)
                self.assertIsInstance(nel.goals, GoalService)
                self.assertIsInstance(nel.fact_commands, FactCommandHandler)
                self.assertIs(nel.fact_commands._service, nel.knowledge)
                self.assertIs(memory_repository.database, knowledge.database)
                self.assertIs(
                    memory_repository.database,
                    nel.identity._repository.database,
                )
                self.assertIs(
                    memory_repository.database,
                    nel.goals._repository.database,
                )
                self.assertEqual(memory_repository.database.path, path)
                self.assertTrue(memory_repository.database.require_existing)
                self.assertEqual(
                    nel.identity.snapshot().role,
                    IDENTITY_BOOTSTRAP["role"],
                )
            finally:
                nel.stop()

    def test_schema_v1_production_startup_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _database = self._v1_database(directory)

            with self.assertRaises(PersistenceStartupError) as raised:
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

            self.assertEqual(
                str(raised.exception),
                "SQLite persistence is unavailable or invalid.",
            )

    def test_schema_v2_production_startup_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _database = self._v2_database(directory)

            with self.assertRaises(PersistenceStartupError) as raised:
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

            self.assertEqual(
                str(raised.exception),
                "SQLite persistence is unavailable or invalid.",
            )

    def test_schema_v3_production_startup_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _database = self._v3_database(directory)

            with self.assertRaises(PersistenceStartupError) as raised:
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

            self.assertEqual(
                str(raised.exception),
                "SQLite persistence is unavailable or invalid.",
            )

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
                    "VALUES (99, '2026-08-02T00:00:00Z')"
                )

            with self.assertRaises(PersistenceStartupError):
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

    def test_incompatible_table_layout_fails_safely(self):
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

    def test_partial_fact_retirement_schema_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._database(directory)
            with database.transaction() as connection:
                connection.execute(
                    "ALTER TABLE user_facts_current DROP COLUMN revision_reason"
                )

            with self.assertRaises(PersistenceStartupError):
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

    def test_missing_identity_trigger_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._database(directory)
            with database.transaction() as connection:
                connection.execute("DROP TRIGGER nel_identity_core_no_delete")

            with self.assertRaises(PersistenceStartupError):
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

    def test_malformed_identity_trigger_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._database(directory)
            with database.transaction() as connection:
                connection.execute("DROP TRIGGER nel_identity_core_no_update")
                connection.execute(
                    "CREATE TRIGGER nel_identity_core_no_update "
                    "BEFORE UPDATE ON nel_identity_current "
                    "BEGIN SELECT 1; END"
                )

            with self.assertRaises(PersistenceStartupError):
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

    def test_partial_goal_schema_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._database(directory)
            with database.transaction() as connection:
                connection.execute("DROP TABLE goals_history")

            with self.assertRaises(PersistenceStartupError):
                create_runtime_nel(
                    provider=FakeProvider(),
                    database_path=path,
                )

    def test_missing_goal_index_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._database(directory)
            with database.transaction() as connection:
                connection.execute("DROP INDEX goals_current_state_updated_idx")

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
            first_identity = first.identity.snapshot()
            first_goal = self._create_goal(first.goals)
            first.remember("Yaddaş: Ömər")
            first.knowledge.knowledge.set("name", "Ömər")
            first.stop()

            second = create_runtime_nel(
                provider=FakeProvider(),
                database_path=path,
            )
            try:
                self.assertEqual(second.identity.snapshot(), first_identity)
                self.assertEqual(second.goals.get(first_goal.goal_id), first_goal)
                self.assertEqual(second.memory.recall(), ["Yaddaş: Ömər"])
                self.assertEqual(second.knowledge.get("name"), "Ömər")
            finally:
                second.stop()

    @patch("src.core.nel.Clock.start")
    def test_goal_user_fact_and_identity_namespaces_are_isolated(
        self,
        _clock_start,
    ):
        with tempfile.TemporaryDirectory() as directory:
            path, _database = self._database(directory)
            nel = create_runtime_nel(
                provider=FakeProvider(),
                database_path=path,
            )
            try:
                nel.knowledge.knowledge.set("display_name", "User name")
                nel.knowledge.knowledge.set("goal_id", "user namespace")
                goal = self._create_goal(nel.goals)
                self.assertEqual(
                    nel.knowledge.get("display_name"),
                    "User name",
                )
                self.assertEqual(
                    nel.identity.snapshot().display_name,
                    IDENTITY_BOOTSTRAP["display_name"],
                )
                self.assertEqual(nel.goals.get(goal.goal_id), goal)
                self.assertEqual(
                    nel.knowledge.get("goal_id"),
                    "user namespace",
                )
            finally:
                nel.stop()

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
            before_identity = nel.identity.snapshot()
            self._create_goal(nel.goals)
            before_goals = nel.goals.list_current()
            try:
                with self.assertRaises(ApplicationError):
                    nel.think("Salam")
            finally:
                nel.stop()

            self.assertEqual(memory.recall(), before_memory)
            self.assertEqual(knowledge.load(), before_facts)
            self.assertEqual(nel.identity.snapshot(), before_identity)
            self.assertEqual(nel.goals.list_current(), before_goals)
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
