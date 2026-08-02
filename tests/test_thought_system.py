import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.core.config import ENABLE_BACKGROUND_THOUGHTS
from src.core.nel import Nel
from src.identity import IdentityRepository, IdentityService
from src.memory.thoughts import Thoughts
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase
from src.services.thought_service import ThoughtService
from src.thoughts import (
    IdentityPolicy,
    KnowledgePolicy,
    MemoryPolicy,
    ReadOnlyThoughtContext,
    ThoughtCoordinator,
    ThoughtKind,
    ThoughtWorker,
    TypedThoughtResult,
)
from src.thoughts.models import THOUGHT_MEMORY_LIMIT
from tests.context_helpers import attach_context_assembler


def observation(content="temporary observation"):
    return TypedThoughtResult(
        kind=ThoughtKind.OBSERVATION_CANDIDATE,
        content=content,
        retention_reason="review only",
        source_reference="test",
        durability_suggestion="review",
    )


def context():
    return ReadOnlyThoughtContext(
        reason="test",
        source_reference="test",
    )


class ResultWorker:
    def __init__(self, result=None):
        self.result = result or observation()
        self.calls = 0

    def run(self, _context, _cancelled):
        self.calls += 1
        return self.result


class BlockingWorker:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def run(self, _context, _cancelled):
        self.calls += 1
        self.entered.set()
        self.release.wait(1)
        return observation("late observation")


class FailingWorker:
    def __init__(self, exception):
        self.exception = exception

    def run(self, _context, _cancelled):
        raise self.exception


class StructuredProvider:
    def generate_structured(self, _prompt, _schema, _schema_name):
        return {
            "kind": "observation_candidate",
            "content": "temporary",
            "retention_reason": "review only",
            "durability_suggestion": "review",
        }


class ThoughtSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protected_paths = (
            Path("memory/nel.sqlite3"),
            Path("memory/internal_thoughts.json"),
        )
        cls.protected_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in cls.protected_paths
            if path.is_file()
        }

    @classmethod
    def tearDownClass(cls):
        for path, expected_hash in cls.protected_hashes.items():
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise AssertionError(f"Protected runtime data changed: {path}")

    @staticmethod
    def _database(directory):
        path = Path(directory) / "thought-test.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        migrate_identity_schema_v1_to_v2(
            database,
            "2026-08-02T01:00:00Z",
        )
        return path, database

    def test_only_one_thought_may_run(self):
        worker = BlockingWorker()
        coordinator = ThoughtCoordinator(worker)

        self.assertTrue(coordinator.start(context()))
        self.assertTrue(worker.entered.wait(0.5))
        self.assertEqual(coordinator.state, "running")
        self.assertFalse(coordinator.start(context()))

        worker.release.set()
        self.assertTrue(coordinator.wait(0.5))
        self.assertEqual(coordinator.state, "idle")
        self.assertEqual(worker.calls, 1)

    def test_foreground_cancels_and_discards_late_result(self):
        worker = BlockingWorker()
        coordinator = ThoughtCoordinator(worker)
        self.assertTrue(coordinator.start(context()))
        self.assertTrue(worker.entered.wait(0.5))

        nel = Nel.__new__(Nel)
        nel.thought_coordinator = coordinator
        nel.state = SimpleNamespace(set=lambda _state: None)
        nel.intent = SimpleNamespace(classify=lambda _text: "CHAT")
        nel.knowledge = SimpleNamespace(
            answer=lambda _text: None,
            facts=lambda: {},
        )
        nel.memory = SimpleNamespace(recall=lambda limit=None: [])
        nel.brain = SimpleNamespace(
            should_remember=lambda _text: False,
            think=lambda _prompt: "foreground",
        )
        attach_context_assembler(nel)

        self.assertEqual(nel.think("hello"), "foreground")
        self.assertEqual(coordinator.state, "idle")
        worker.release.set()
        self.assertTrue(coordinator.wait(0.5))
        self.assertIsNone(coordinator.last_result)

    def test_foreground_gate_rejects_new_background_start(self):
        coordinator = ThoughtCoordinator(ResultWorker())
        coordinator.begin_foreground()

        self.assertFalse(coordinator.start(context()))
        self.assertEqual(coordinator.state, "idle")

        coordinator.end_foreground()
        self.assertTrue(coordinator.start(context()))
        self.assertTrue(coordinator.wait(0.5))

    def test_timeout_and_failure_release_coordinator(self):
        for exception in (
            TimeoutError("private timeout detail"),
            RuntimeError("private provider detail"),
        ):
            coordinator = ThoughtCoordinator(FailingWorker(exception))
            with self.assertLogs(
                "src.thoughts.coordinator",
                level="ERROR",
            ) as logs:
                self.assertTrue(coordinator.start(context()))
                self.assertTrue(coordinator.wait(0.5))

            self.assertEqual(coordinator.state, "idle")
            self.assertIsNone(coordinator.last_result)
            self.assertNotIn(str(exception), logs.output[0])
            coordinator.worker = ResultWorker()
            self.assertTrue(coordinator.start(context()))
            self.assertTrue(coordinator.wait(0.5))
            self.assertIsNotNone(coordinator.last_result)

    def test_valid_result_is_temporary_and_never_printed(self):
        worker = ThoughtWorker(StructuredProvider())
        result = worker.run(context(), threading.Event())
        coordinator = ThoughtCoordinator(ResultWorker(result))

        with patch("builtins.print") as output:
            self.assertTrue(coordinator.start(context()))
            self.assertTrue(coordinator.wait(0.5))

        output.assert_not_called()
        self.assertEqual(
            coordinator.last_result.kind,
            ThoughtKind.OBSERVATION_CANDIDATE,
        )
        self.assertEqual(coordinator.last_result.content, "temporary")

    def test_policies_reject_everything_by_default(self):
        result = observation()
        thought_context = context()
        self.assertFalse(MemoryPolicy().allows(result, thought_context))
        self.assertFalse(KnowledgePolicy().allows(result, thought_context))
        self.assertFalse(IdentityPolicy().allows(result, thought_context))
        with self.assertRaises(ValueError):
            TypedThoughtResult.from_payload(
                {
                    "kind": "external_action",
                    "content": "do something",
                    "retention_reason": None,
                    "durability_suggestion": "none",
                },
                source_reference="test",
            )

    def test_no_json_or_sqlite_writes_and_no_state_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thought_json = root / "internal_thoughts.json"
            path, database = self._database(directory)
            memory = SQLiteMemory(database)
            knowledge = SQLiteKnowledge(database)
            identity = IdentityService(IdentityRepository(database))
            memory.remember("preserved memory")
            knowledge.set("name", "preserved fact")
            before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            before_memory = memory.recall()
            before_facts = knowledge.load()
            before_identity = identity.snapshot()
            coordinator = ThoughtCoordinator(ResultWorker())
            service = ThoughtService(
                coordinator,
                memory=memory,
                knowledge=SimpleNamespace(facts=knowledge.load),
                identity=identity,
            )

            with patch.object(
                Thoughts,
                "add",
                side_effect=AssertionError("legacy JSON write"),
            ):
                self.assertTrue(
                    service.generate(
                        required_fact_keys=("name",),
                        source_reference="test",
                    )
                )
                self.assertTrue(coordinator.wait(0.5))

            self.assertFalse(thought_json.exists())
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                before_hash,
            )
            self.assertEqual(memory.recall(), before_memory)
            self.assertEqual(knowledge.load(), before_facts)
            self.assertEqual(identity.snapshot(), before_identity)

    def test_context_is_bounded_and_facts_are_explicitly_selected(self):
        memories = [f"memory-{index}" for index in range(10)]
        facts = {f"fact_{index}": f"value-{index}" for index in range(30)}
        identity = SimpleNamespace(
            snapshot=lambda: SimpleNamespace(
                identity_id="nel",
                display_name="Nel",
                nature="artificial",
                role="companion",
                preferences=(),
            )
        )
        service = ThoughtService(
            ThoughtCoordinator(ResultWorker()),
            memory=SimpleNamespace(
                recall=lambda limit=None: memories[-limit:]
            ),
            knowledge=SimpleNamespace(facts=lambda: facts),
            identity=identity,
        )

        bounded = service.build_context(
            reason="test",
            source_reference="test",
            required_fact_keys=("fact_2", "fact_1", "missing"),
        )

        self.assertEqual(len(bounded.memories), THOUGHT_MEMORY_LIMIT)
        self.assertEqual(
            bounded.user_facts,
            (("fact_1", "value-1"), ("fact_2", "value-2")),
        )
        self.assertEqual(dict(bounded.identity_core)["identity_id"], "nel")

    def test_disabled_by_default_and_restart_has_no_running_state(self):
        self.assertFalse(ENABLE_BACKGROUND_THOUGHTS)
        worker = BlockingWorker()
        first = ThoughtCoordinator(worker)
        self.assertTrue(first.start(context()))
        self.assertTrue(worker.entered.wait(0.5))
        first.shutdown()
        self.assertEqual(first.state, "idle")

        restarted = ThoughtCoordinator(ResultWorker())
        self.assertEqual(restarted.state, "idle")
        self.assertIsNone(restarted.last_result)
        worker.release.set()
        self.assertTrue(first.wait(0.5))
        self.assertIsNone(first.last_result)

        completed = ThoughtCoordinator(ResultWorker())
        self.assertTrue(completed.start(context()))
        self.assertTrue(completed.wait(0.5))
        self.assertIsNotNone(completed.last_result)
        completed.shutdown()
        self.assertIsNone(completed.last_result)


if __name__ == "__main__":
    unittest.main()
