import sqlite3
import unittest
from unittest.mock import patch

import main
from src.core.nel import Nel
from src.errors import ApplicationError, PersistenceOperationError
from src.goals.commands import GoalCommandHandler
from src.goals.repository import GoalRepositoryError
from src.services.fact_commands import FactCommandHandler
from src.services.knowledge_service import KnowledgeService
from src.services.memory_commands import MemoryCommandHandler
from src.services.memory_service import MemoryService, MemoryWriteStatus


class _Brain:
    provider = object()


class _FailingKnowledgeRepository:
    def load(self):
        raise sqlite3.OperationalError("PRIVATE FACT VALUE")

    def get(self, _key):
        raise sqlite3.OperationalError("PRIVATE FACT VALUE")

    def set(self, _key, _value):
        raise sqlite3.OperationalError("PRIVATE FACT VALUE")

    def history(self, _key):
        raise sqlite3.OperationalError("PRIVATE FACT VALUE")

    def retire(self, _key, _reason):
        raise sqlite3.OperationalError("PRIVATE FACT VALUE")


class _FailingMemoryRepository:
    def recall(self, limit=None):
        raise sqlite3.OperationalError("PRIVATE MEMORY VALUE")

    def remember(self, _text):
        raise sqlite3.OperationalError("PRIVATE MEMORY VALUE")


class _FailingGoals:
    def list_current(self):
        raise GoalRepositoryError("PRIVATE GOAL VALUE")

    def get(self, _goal_id):
        raise GoalRepositoryError("PRIVATE GOAL VALUE")


class _FailingIdentity:
    def snapshot(self):
        raise PersistenceOperationError()


class OperationalErrorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.knowledge = KnowledgeService(
            _Brain(),
            _FailingKnowledgeRepository(),
        )

    def test_fact_commands_bound_all_sqlite_failures(self):
        handler = FactCommandHandler(self.knowledge)
        commands = (
            "/fact list",
            "/fact history name",
            '/fact set name --value "Ömər" --confirm',
            '/fact retire name --confirm --reason "obsolete"',
        )
        for command in commands:
            with self.subTest(command=command):
                response = handler.execute(command)
                self.assertEqual(response, "Fakt xidməti hazırda əlçatan deyil.")
                self.assertNotIn("PRIVATE", response)

    def test_goal_list_and_goal_read_fail_locally(self):
        handler = GoalCommandHandler(_FailingGoals())
        self.assertEqual(
            handler.list_goals(),
            "Məqsəd xidməti hazırda əlçatan deyil.",
        )
        response = handler.execute("/goal pause goal-1 --version 1")
        self.assertEqual(response, "Məqsəd əmri yaddaşa yazıla bilmədi.")
        self.assertNotIn("PRIVATE", response)

    def test_remember_failure_is_deterministic_and_provider_free(self):
        service = MemoryService(_FailingMemoryRepository())
        result = service.remember_explicit("literal memory")
        self.assertEqual(result.status, MemoryWriteStatus.FAILURE)
        self.assertEqual(result.message, "Yaddaş saxlanıla bilmədi.")
        handler = MemoryCommandHandler(service)
        parsed = handler.inspect("/remember literal memory")
        self.assertEqual(
            handler.execute_payload(parsed.arguments),
            "Yaddaş saxlanıla bilmədi.",
        )

    def test_local_identity_and_fact_reads_fail_safely(self):
        nel = Nel.__new__(Nel)
        nel.identity = _FailingIdentity()
        nel.knowledge = self.knowledge

        self.assertEqual(
            nel._local_identity_response(),
            "Nel kimliyi hazırda əlçatan deyil.",
        )
        self.assertEqual(
            nel._local_user_fact_response(),
            "İstifadəçi faktları hazırda əlçatan deyil.",
        )

    def test_cli_catches_application_error_without_traceback(self):
        class _Nel:
            def think(self, _text):
                raise PersistenceOperationError()

            def stop(self):
                return None

        with (
            patch.object(main, "create_runtime_nel", return_value=_Nel()),
            patch("builtins.input", side_effect=["salam", "exit"]),
            patch("builtins.print") as output,
        ):
            self.assertEqual(main.run(), 0)

        rendered = "\n".join(
            " ".join(str(value) for value in call.args)
            for call in output.call_args_list
        )
        self.assertIn("Yaddaş xidməti hazırda əlçatan deyil.", rendered)
        self.assertNotIn("Traceback", rendered)

    def test_programmer_errors_are_not_swallowed(self):
        class _BrokenRepository:
            def recall(self, limit=None):
                raise AssertionError("programmer defect")

        with self.assertRaises(AssertionError):
            MemoryService(_BrokenRepository()).remember_explicit("text")


if __name__ == "__main__":
    unittest.main()
