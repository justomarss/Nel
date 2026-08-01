import json
import sqlite3
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from src.goals import (
    MAX_CURRENT_GOALS,
    MAX_SERIALIZED_CHARACTERS,
    MAX_TERMINAL_GOALS,
    GoalCandidate,
    GoalContextSerializer,
    GoalOwner,
    GoalPolicy,
    GoalPolicyError,
    GoalPriority,
    GoalRevision,
    GoalSnapshot,
    GoalState,
    ProgressVerification,
)


NOW = "2026-08-02T10:00:00+00:00"


def candidate(**changes):
    values = {
        "title": "Azerbaycanca danismaq",
        "success_condition": "User explicitly accepts the outcome",
        "owner": GoalOwner.USER,
        "source_kind": "validated_user",
        "source_reference": "conversation:1",
    }
    values.update(changes)
    return GoalCandidate(**values)


def snapshot(index=1, **changes):
    values = {
        "goal_id": f"goal-{index:02d}",
        "title": f"Goal {index}",
        "success_condition": "Explicitly accepted result",
        "owner": GoalOwner.USER,
        "approval_reference": "conversation:1",
        "created_at": "2026-08-01T10:00:00+00:00",
        "updated_at": f"2026-08-02T10:{index % 60:02d}:00+00:00",
    }
    values.update(changes)
    return GoalSnapshot(**values)


class GoalModelTests(unittest.TestCase):
    def test_models_are_immutable(self):
        item = candidate()
        current = snapshot()
        revision = GoalRevision(
            snapshot=current,
            superseded_at=NOW,
            revision_reason="Owner-approved revision",
        )

        with self.assertRaises(FrozenInstanceError):
            item.title = "Changed"
        with self.assertRaises(FrozenInstanceError):
            current.state = GoalState.PAUSED
        with self.assertRaises(FrozenInstanceError):
            revision.revision_reason = "Changed"

    def test_invalid_ownership_and_enums_are_rejected(self):
        with self.assertRaises(ValueError):
            candidate(owner="user")
        with self.assertRaises(ValueError):
            candidate(priority="high")
        with self.assertRaises(ValueError):
            snapshot(state="active")

    def test_unknown_progress_is_not_zero_percent(self):
        with self.assertRaisesRegex(ValueError, "Unknown progress"):
            snapshot(progress_percent=0)
        with self.assertRaisesRegex(ValueError, "Unknown progress"):
            snapshot(progress_summary="No progress")

    def test_revision_contains_recoverable_immutable_snapshot(self):
        old = snapshot(version=2, state=GoalState.PAUSED)
        revision = GoalRevision(
            snapshot=old,
            superseded_at=NOW,
            revision_reason="Resumed by user",
        )
        self.assertEqual(revision.snapshot, old)
        self.assertEqual(revision.snapshot.version, 2)


class GoalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = GoalPolicy()

    def test_creation_is_denied_by_default(self):
        with self.assertRaisesRegex(GoalPolicyError, "approval"):
            self.policy.authorize_creation(candidate())

    def test_model_thought_and_unvalidated_runtime_sources_are_rejected(self):
        for source_kind in ("model_output", "thought_output", "runtime"):
            with self.subTest(source_kind=source_kind):
                with self.assertRaisesRegex(GoalPolicyError, "not authorized"):
                    self.policy.authorize_creation(
                        candidate(source_kind=source_kind),
                        explicit_user_approval=True,
                        approval_reference="conversation:2",
                    )

    def test_validated_user_creation_is_allowed(self):
        approved = self.policy.authorize_creation(
            candidate(),
            explicit_user_approval=True,
            approval_reference="conversation:2",
        )
        self.assertEqual(approved.owner, GoalOwner.USER)

    def test_primarily_user_outcome_is_normalized_to_user_owner(self):
        approved = self.policy.authorize_creation(
            candidate(owner=GoalOwner.SHARED, outcome_primarily_user=True),
            explicit_user_approval=True,
            approval_reference="conversation:2",
        )
        self.assertEqual(approved.owner, GoalOwner.USER)

    def test_shared_goal_records_collaboration_not_agency(self):
        approved = self.policy.authorize_creation(
            candidate(owner=GoalOwner.SHARED, outcome_primarily_user=False),
            explicit_user_approval=True,
            approval_reference="conversation:2",
        )
        self.assertEqual(approved.owner, GoalOwner.SHARED)
        self.assertFalse(hasattr(approved, "authority_to_act"))
        self.assertFalse(hasattr(approved, "independent_desire"))

    def test_valid_state_transitions(self):
        for target in (
            GoalState.PAUSED,
            GoalState.COMPLETED,
            GoalState.CANCELLED,
        ):
            with self.subTest(target=target):
                self.policy.validate_transition(
                    snapshot(),
                    target,
                    source_kind="validated_user",
                    explicit_user_approval=True,
                    approval_reference="conversation:3",
                    success_condition_accepted=(
                        target is GoalState.COMPLETED
                    ),
                )

    def test_invalid_and_terminal_state_transitions_are_rejected(self):
        with self.assertRaisesRegex(GoalPolicyError, "not allowed"):
            self.policy.validate_transition(
                snapshot(state=GoalState.COMPLETED),
                GoalState.ACTIVE,
                source_kind="validated_user",
                explicit_user_approval=True,
                approval_reference="conversation:3",
            )
        with self.assertRaisesRegex(GoalPolicyError, "not allowed"):
            self.policy.validate_transition(
                snapshot(),
                GoalState.ACTIVE,
                source_kind="validated_user",
                explicit_user_approval=True,
                approval_reference="conversation:3",
            )

    def test_completion_requires_success_condition_acceptance(self):
        with self.assertRaisesRegex(GoalPolicyError, "success-condition"):
            self.policy.validate_transition(
                snapshot(),
                GoalState.COMPLETED,
                source_kind="validated_user",
                explicit_user_approval=True,
                approval_reference="conversation:3",
            )

    def test_user_reported_and_verified_progress_require_evidence(self):
        with self.assertRaisesRegex(GoalPolicyError, "explicit user report"):
            self.policy.validate_progress(
                snapshot(),
                ProgressVerification.USER_REPORTED,
                summary="Half complete",
                percent=50,
                source_kind="validated_user",
                explicit_user_approval=True,
                approval_reference="conversation:4",
            )
        self.policy.validate_progress(
            snapshot(),
            ProgressVerification.USER_REPORTED,
            summary="User reports half complete",
            percent=50,
            source_kind="validated_user",
            explicit_user_approval=True,
            approval_reference="conversation:4",
            owner_confirmation=True,
        )
        self.policy.validate_progress(
            snapshot(),
            ProgressVerification.VERIFIED,
            summary="Deterministic check passed",
            source_kind="validated_user",
            explicit_user_approval=True,
            approval_reference="conversation:4",
            deterministic_evidence=True,
        )

    def test_progress_cannot_be_downgraded_or_promoted_by_model(self):
        reported = snapshot(
            progress_verification=ProgressVerification.USER_REPORTED,
            progress_summary="Reported",
        )
        with self.assertRaisesRegex(GoalPolicyError, "downgraded"):
            self.policy.validate_progress(
                reported,
                ProgressVerification.UNKNOWN,
                source_kind="validated_user",
                explicit_user_approval=True,
                approval_reference="conversation:5",
            )
        with self.assertRaisesRegex(GoalPolicyError, "not authorized"):
            self.policy.validate_progress(
                snapshot(),
                ProgressVerification.VERIFIED,
                summary="Model claim",
                source_kind="model_output",
                explicit_user_approval=True,
                approval_reference="model:1",
                deterministic_evidence=True,
            )


class GoalContextTests(unittest.TestCase):
    def setUp(self):
        self.serializer = GoalContextSerializer()

    def test_context_is_deterministic_and_capped_by_state_counts(self):
        current = [snapshot(index) for index in range(1, 15)]
        terminal = [
            snapshot(index + 20, state=GoalState.COMPLETED)
            for index in range(1, 9)
        ]
        goals = current + terminal

        first = self.serializer.serialize(reversed(goals))
        second = self.serializer.serialize(goals)
        payload = json.loads(first)

        self.assertEqual(first, second)
        self.assertLessEqual(
            len(payload["active_or_paused"]),
            MAX_CURRENT_GOALS,
        )
        self.assertLessEqual(
            len(payload["completed_or_cancelled"]),
            MAX_TERMINAL_GOALS,
        )
        self.assertLessEqual(len(first), MAX_SERIALIZED_CHARACTERS)

    def test_active_and_high_priority_goals_are_ordered_first(self):
        goals = [
            snapshot(1, state=GoalState.PAUSED, priority=GoalPriority.HIGH),
            snapshot(2, state=GoalState.ACTIVE, priority=GoalPriority.LOW),
            snapshot(3, state=GoalState.ACTIVE, priority=GoalPriority.HIGH),
            snapshot(4, state=GoalState.ACTIVE, priority=GoalPriority.NORMAL),
        ]
        payload = json.loads(self.serializer.serialize(goals))
        self.assertEqual(
            [goal["goal_id"] for goal in payload["active_or_paused"]],
            ["goal-03", "goal-04", "goal-02", "goal-01"],
        )

    def test_recent_terminal_goals_are_ordered_first(self):
        goals = [
            snapshot(
                1,
                state=GoalState.CANCELLED,
                updated_at="2026-08-02T09:00:00+00:00",
            ),
            snapshot(
                2,
                state=GoalState.COMPLETED,
                updated_at="2026-08-02T11:00:00+00:00",
            ),
        ]
        payload = json.loads(self.serializer.serialize(goals))
        self.assertEqual(
            [goal["goal_id"] for goal in payload["completed_or_cancelled"]],
            ["goal-02", "goal-01"],
        )

    def test_character_budget_removes_lowest_ranked_items(self):
        goals = [
            snapshot(
                index,
                title=("Məqsəd " + str(index) + " ") * 30,
                success_condition="Şərt " * 45,
                priority=(
                    GoalPriority.HIGH if index == 1 else GoalPriority.LOW
                ),
            )
            for index in range(1, 11)
        ]
        serialized = self.serializer.serialize(goals)
        payload = json.loads(serialized)
        ids = [goal["goal_id"] for goal in payload["active_or_paused"]]

        self.assertLessEqual(len(serialized), MAX_SERIALIZED_CHARACTERS)
        self.assertIn("goal-01", ids)
        self.assertLess(len(ids), MAX_CURRENT_GOALS)

    def test_context_is_structured_and_preserves_unicode(self):
        encoded = self.serializer.serialize(
            [snapshot(title="Ömərin məqsədi", success_condition="Tamamlandı")]
        )
        self.assertIn("Ömərin məqsədi", encoded)
        payload = json.loads(encoded)
        self.assertEqual(
            set(payload),
            {"active_or_paused", "completed_or_cancelled"},
        )

    def test_domain_and_context_operations_do_not_write_files_or_databases(self):
        item = candidate()
        policy = GoalPolicy()
        with (
            patch("builtins.open", side_effect=AssertionError("file access")),
            patch.object(
                Path,
                "write_text",
                side_effect=AssertionError("file write"),
            ),
            patch.object(
                Path,
                "write_bytes",
                side_effect=AssertionError("file write"),
            ),
            patch.object(
                sqlite3,
                "connect",
                side_effect=AssertionError("database access"),
            ),
        ):
            approved = policy.authorize_creation(
                item,
                explicit_user_approval=True,
                approval_reference="conversation:6",
            )
            encoded = self.serializer.serialize([snapshot(title=approved.title)])
        self.assertTrue(encoded)


if __name__ == "__main__":
    unittest.main()
