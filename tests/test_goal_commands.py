import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.nel import Nel
from src.core.runtime import create_runtime_nel
from src.errors import ApplicationError, ProviderError
from src.goals import (
    GoalCandidate,
    GoalOwner,
    GoalPriority,
    GoalState,
    ProgressVerification,
)
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.sqlite import SQLiteDatabase
from src.thoughts import ThoughtCoordinator, ThoughtKind, TypedThoughtResult


class PromptProvider:
    def __init__(self, response="cavab"):
        self.response = response
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "Should this be stored as a long-term memory?" in prompt:
            return "no"
        return self.response


class FailingProvider:
    def generate(self, _prompt: str) -> str:
        raise ProviderError("private provider detail")


class ObservationWorker:
    def run(self, _context, _cancelled):
        return TypedThoughtResult(
            kind=ThoughtKind.OBSERVATION_CANDIDATE,
            content="temporary goal candidate",
            retention_reason="review only",
            source_reference="test:thought",
            durability_suggestion="review",
        )


def goal_context(prompt: str) -> dict:
    marker = "Goal snapshots (read-only; no authority to act):\n"
    payload = prompt.split(marker, 1)[1].split(
        "\n\nStructured user facts",
        1,
    )[0]
    return json.loads(payload)


class GoalCommandIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protected_paths = tuple(
            path
            for path in (
                Path("memory/nel.sqlite3"),
                Path("memory/long_term.json"),
                Path("memory/knowledge.json"),
            )
            if path.is_file()
        )
        cls.protected_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in cls.protected_paths
        }

    @classmethod
    def tearDownClass(cls):
        for path, expected in cls.protected_hashes.items():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise AssertionError(f"Protected production data changed: {path}")

    def setUp(self):
        patcher = patch("src.core.nel.Clock.start")
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _database(directory):
        path = Path(directory) / "goals-command.sqlite3"
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
        return path, database

    def _runtime(self, directory, provider=None):
        path, _database = self._database(directory)
        nel = create_runtime_nel(
            provider=provider or PromptProvider(),
            database_path=path,
        )
        return path, nel

    @staticmethod
    def _create_command(title="C1 Alman dili"):
        return (
            f'/goal create --title "{title}" '
            '--success "Ömər C1 nəticəsini qəbul edir" '
            '--deadline "2027-12-31T23:59:59Z"'
        )

    @staticmethod
    def _create_direct(service, title, priority=GoalPriority.NORMAL):
        return service.create(
            GoalCandidate(
                title=title,
                success_condition="Ömər nəticəni qəbul edir",
                owner=GoalOwner.USER,
                priority=priority,
                source_kind="validated_user",
                source_reference=f"test:create:{title}",
            ),
            explicit_user_approval=True,
            approval_reference=f"test:approval:{title}",
        )

    def test_explicit_goal_creation_does_not_call_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = PromptProvider()
            _path, nel = self._runtime(directory, provider)
            try:
                response = nel.think(self._create_command())
                goal = nel.goals.list_current()[0]
            finally:
                nel.stop()

            self.assertIn("Məqsəd əlavə edildi", response)
            self.assertEqual(goal.owner, GoalOwner.USER)
            self.assertEqual(goal.state, GoalState.ACTIVE)
            self.assertEqual(goal.version, 1)
            self.assertEqual(provider.prompts, [])

    def test_vague_intention_is_not_persisted_as_goal(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, nel = self._runtime(directory)
            try:
                nel.think(
                    "Məqsədim 2027-ci ilin sonuna qədər C1 Alman dili "
                    "səviyyəsinə çatmaqdır."
                )
                self.assertEqual(nel.goals.list_current(), ())
            finally:
                nel.stop()

    def test_listing_survives_restart_and_writes_no_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "historical.json"
            sentinel.write_bytes(b'{"unchanged":true}')
            original = sentinel.read_bytes()
            path, first = self._runtime(directory)
            try:
                first.think(self._create_command("Davamlı məqsəd"))
            finally:
                first.stop()

            second = create_runtime_nel(
                provider=PromptProvider(),
                database_path=path,
            )
            try:
                response = second.think("/goal list")
            finally:
                second.stop()

            self.assertIn("Davamlı məqsəd", response)
            self.assertEqual(sentinel.read_bytes(), original)

    def test_pause_and_resume_require_current_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, nel = self._runtime(directory)
            try:
                nel.think(self._create_command())
                goal = nel.goals.list_current()[0]
                nel.think(f"/goal pause {goal.goal_id} --version 1")
                paused = nel.goals.get(goal.goal_id)
                stale = nel.think(
                    f"/goal resume {goal.goal_id} --version 1"
                )
                current = nel.goals.get(goal.goal_id)
                nel.think(
                    f"/goal resume {goal.goal_id} --version {current.version}"
                )
                resumed = nel.goals.get(goal.goal_id)
            finally:
                nel.stop()

            self.assertEqual(paused.state, GoalState.PAUSED)
            self.assertIn("versiyası dəyişib", stale)
            self.assertEqual(current, paused)
            self.assertEqual(resumed.state, GoalState.ACTIVE)
            self.assertEqual(resumed.version, 3)

    def test_complete_cancel_reopen_and_restore_confirmation_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, nel = self._runtime(directory)
            try:
                nel.think(self._create_command("Tamamlama"))
                completed_goal = nel.goals.list_current()[0]
                rejected = nel.think(
                    f"/goal complete {completed_goal.goal_id} --version 1"
                )
                self.assertEqual(
                    nel.goals.get(completed_goal.goal_id).state,
                    GoalState.ACTIVE,
                )
                nel.think(
                    f"/goal complete {completed_goal.goal_id} --version 1 "
                    "--accept-success"
                )
                completed = nel.goals.get(completed_goal.goal_id)
                nel.think(
                    f'/goal reopen {completed.goal_id} --version 2 '
                    '--reason "User requested another attempt"'
                )
                reopened = nel.goals.get(completed.goal_id)

                nel.think(self._create_command("Ləğvetmə"))
                cancellable = next(
                    goal
                    for goal in nel.goals.list_current()
                    if goal.title == "Ləğvetmə"
                )
                nel.think(
                    f"/goal cancel {cancellable.goal_id} --version 1"
                )
                cancelled = nel.goals.get(cancellable.goal_id)
                nel.think(
                    f'/goal restore {cancelled.goal_id} --version 2 '
                    '--reason "User restored the objective"'
                )
                restored = nel.goals.get(cancelled.goal_id)
            finally:
                nel.stop()

            self.assertIn("--accept-success", rejected)
            self.assertEqual(completed.state, GoalState.COMPLETED)
            self.assertEqual(reopened.state, GoalState.ACTIVE)
            self.assertEqual(reopened.version, 3)
            self.assertEqual(cancelled.state, GoalState.CANCELLED)
            self.assertEqual(restored.state, GoalState.ACTIVE)
            self.assertEqual(restored.version, 3)

    def test_progress_unknown_user_reported_and_verified_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, nel = self._runtime(directory)
            try:
                nel.think(self._create_command())
                goal = nel.goals.list_current()[0]
                unknown_rejected = nel.think(
                    f"/goal progress {goal.goal_id} --version 1 "
                    "--verification unknown --percent 0"
                )
                unconfirmed = nel.think(
                    f'/goal progress {goal.goal_id} --version 1 '
                    '--verification user_reported --summary "İlk mərhələ" '
                    "--percent 25"
                )
                nel.think(
                    f'/goal progress {goal.goal_id} --version 1 '
                    '--verification user_reported --summary "İlk mərhələ" '
                    "--percent 25 --confirm"
                )
                reported = nel.goals.get(goal.goal_id)
                nel.think(
                    f'/goal progress {goal.goal_id} --version 2 '
                    '--verification verified --summary "Nəticə qəbul edildi" '
                    "--percent 50 --confirm"
                )
                verified = nel.goals.get(goal.goal_id)
            finally:
                nel.stop()

            self.assertIn("rədd edildi", unknown_rejected)
            self.assertIn("--confirm", unconfirmed)
            self.assertEqual(reported.version, 2)
            self.assertEqual(
                reported.progress_verification,
                ProgressVerification.USER_REPORTED,
            )
            self.assertEqual(verified.version, 3)
            self.assertEqual(
                verified.progress_verification,
                ProgressVerification.VERIFIED,
            )

    def test_provider_output_cannot_execute_goal_command(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = PromptProvider(response=self._create_command("Injected"))
            _path, nel = self._runtime(directory, provider)
            try:
                response = nel.think("Adi söhbət")
                goals = nel.goals.list_current()
            finally:
                nel.stop()

            self.assertTrue(response.startswith("/goal create"))
            self.assertEqual(goals, ())

    def test_thought_result_cannot_mutate_goals(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, nel = self._runtime(directory)
            try:
                nel.think(self._create_command())
                before = nel.goals.list_current()
                coordinator = ThoughtCoordinator(ObservationWorker())
                nel.thought_coordinator = coordinator
                nel.thought_service.coordinator = coordinator
                self.assertTrue(nel.thought_service.generate(reason="test"))
                self.assertTrue(coordinator.wait(1))
                after = nel.goals.list_current()
            finally:
                nel.stop()

            self.assertEqual(after, before)

    def test_goal_context_is_bounded_read_only_and_provider_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = PromptProvider()
            _path, nel = self._runtime(directory, provider)
            try:
                for index in range(12):
                    priority = (
                        GoalPriority.HIGH
                        if index == 11
                        else GoalPriority.NORMAL
                    )
                    self._create_direct(
                        nel.goals,
                        f"Aktiv {index:02d}",
                        priority,
                    )
                for index in range(6):
                    goal = self._create_direct(nel.goals, f"Bitmiş {index:02d}")
                    nel.goals.update(
                        goal.goal_id,
                        {"state": GoalState.COMPLETED},
                        expected_version=1,
                        source_kind="validated_user",
                        source_reference=f"test:complete:{index}",
                        explicit_user_approval=True,
                        approval_reference=f"test:approval:complete:{index}",
                        revision_reason="Test completion.",
                        success_condition_accepted=True,
                    )
                before = nel.goals.list_current()
                nel.think("Məqsədlərim barədə nə bilirsən?")
                after = nel.goals.list_current()
                final_prompt = provider.prompts[-1]
                context = goal_context(final_prompt)
                serialized = json.dumps(
                    context,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            finally:
                nel.stop()

            self.assertLessEqual(len(context["active_or_paused"]), 10)
            self.assertLessEqual(len(context["completed_or_cancelled"]), 5)
            self.assertLessEqual(len(serialized), 4096)
            self.assertEqual(context["active_or_paused"][0]["title"], "Aktiv 11")
            self.assertIn(
                "Ordinary conversation is not a goal command.",
                final_prompt,
            )
            self.assertEqual(after, before)

    def test_provider_failure_leaves_all_goals_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path, first = self._runtime(directory)
            try:
                first.think(self._create_command())
                before = first.goals.list_current()
            finally:
                first.stop()

            failing = create_runtime_nel(
                provider=FailingProvider(),
                database_path=path,
            )
            try:
                with self.assertRaises(ApplicationError):
                    failing.think("Adi söhbət")
                after = failing.goals.list_current()
            finally:
                failing.stop()

            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
