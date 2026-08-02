import sqlite3
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

from src.core.decision_engine import (
    DecisionContext,
    DecisionEngine,
    DecisionReason,
    DecisionResult,
    DecisionType,
    EventKind,
    ExplicitCommandParse,
    GoalCommandParseStatus,
    USER_INPUT_MAX_CHARS,
)
from src.core.nel import Nel
from src.core.state import State


def context(**changes):
    values = {
        "event_id": "event-001",
        "event_kind": EventKind.USER_TURN,
        "user_input": "Salam",
        "operational_state": "idle",
        "explicit_command_parse": ExplicitCommandParse.not_command(),
        "foreground_activity": True,
        "background_thought_state": "idle",
    }
    values.update(changes)
    return DecisionContext(**values)


class DecisionEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionEngine()

    def test_models_are_immutable_and_result_has_one_primary_decision(self):
        decision_context = context()
        result = self.engine.decide(decision_context)

        with self.assertRaises(FrozenInstanceError):
            decision_context.user_input = "changed"
        with self.assertRaises(FrozenInstanceError):
            result.primary_decision = DecisionType.NO_ACTION

        self.assertIsInstance(result.primary_decision, DecisionType)
        self.assertEqual(
            result.primary_decision,
            DecisionType.CONVERSATION_RESPONSE,
        )

    def test_result_rejects_mismatched_or_multiple_route_payloads(self):
        with self.assertRaises(ValueError):
            DecisionResult(
                event_id="event-001",
                primary_decision=DecisionType.NO_ACTION,
                target_route="conversation_flow",
                reason_code=DecisionReason.EMPTY_USER_INPUT,
            )
        with self.assertRaises(ValueError):
            DecisionResult(
                event_id="event-001",
                primary_decision=DecisionType.CONVERSATION_RESPONSE,
                target_route="conversation_flow",
                reason_code=DecisionReason.ORDINARY_USER_INPUT,
                validated_command_payload=("list",),
            )
        with self.assertRaises(ValueError):
            DecisionResult(
                event_id="event-001",
                primary_decision=DecisionType.NO_ACTION,
                target_route="none",
                reason_code=DecisionReason.ORDINARY_USER_INPUT,
            )

    def test_invalid_and_oversized_context_precede_every_user_route(self):
        confirmed = ExplicitCommandParse(
            status=GoalCommandParseStatus.CONFIRMED,
            operation="list",
            arguments=("list",),
        )
        cases = (
            context(event_id=""),
            context(event_kind="user_turn"),
            context(background_thought_state="unknown"),
            context(
                explicit_command_parse=ExplicitCommandParse(
                    status=GoalCommandParseStatus.CONFIRMED,
                )
            ),
            context(
                user_input="x" * (USER_INPUT_MAX_CHARS + 1),
                explicit_command_parse=confirmed,
            ),
        )

        for candidate in cases:
            with self.subTest(candidate=candidate):
                result = self.engine.decide(candidate)
                self.assertEqual(result.primary_decision, DecisionType.NO_ACTION)
                self.assertEqual(
                    result.reason_code,
                    DecisionReason.INVALID_CONTEXT,
                )

    def test_confirmed_goal_command_precedes_ordinary_conversation(self):
        command = ExplicitCommandParse(
            status=GoalCommandParseStatus.CONFIRMED,
            operation="list",
            arguments=("list",),
        )

        result = self.engine.decide(
            context(
                user_input="/goal list",
                explicit_command_parse=command,
            )
        )

        self.assertEqual(result.primary_decision, DecisionType.GOAL_COMMAND)
        self.assertEqual(
            result.reason_code,
            DecisionReason.CONFIRMED_GOAL_COMMAND,
        )
        self.assertEqual(result.validated_command_payload, ("list",))

    def test_confirmed_fact_command_has_its_own_deterministic_route(self):
        command = ExplicitCommandParse(
            status=GoalCommandParseStatus.CONFIRMED,
            operation="list",
            arguments=("list",),
            command_kind="fact",
        )
        result = self.engine.decide(
            context(
                user_input="/fact list",
                explicit_command_parse=command,
            )
        )

        self.assertIs(result.primary_decision, DecisionType.FACT_COMMAND)
        self.assertEqual(result.target_route, "fact_command_handler")
        self.assertEqual(
            result.reason_code,
            DecisionReason.CONFIRMED_FACT_COMMAND,
        )
        self.assertEqual(result.validated_command_payload, ("list",))

    def test_confirmed_memory_command_has_its_own_deterministic_route(self):
        command = ExplicitCommandParse(
            status=GoalCommandParseStatus.CONFIRMED,
            operation="remember",
            arguments=("literal memory",),
            command_kind="memory",
        )

        result = self.engine.decide(
            context(
                user_input="/remember literal memory",
                explicit_command_parse=command,
            )
        )

        self.assertIs(result.primary_decision, DecisionType.MEMORY_COMMAND)
        self.assertEqual(result.target_route, "memory_command_handler")
        self.assertEqual(
            result.reason_code,
            DecisionReason.CONFIRMED_MEMORY_COMMAND,
        )
        self.assertEqual(result.validated_command_payload, ("literal memory",))

    def test_empty_memory_command_requires_deterministic_clarification(self):
        command = ExplicitCommandParse(
            status=GoalCommandParseStatus.CLARIFICATION_REQUIRED,
            operation="remember",
            command_kind="memory",
        )

        result = self.engine.decide(
            context(
                user_input="/remember",
                explicit_command_parse=command,
            )
        )

        self.assertIs(result.primary_decision, DecisionType.ASK_CLARIFICATION)
        self.assertEqual(
            result.reason_code,
            DecisionReason.MEMORY_COMMAND_REQUIRES_CLARIFICATION,
        )

    def test_malformed_fact_command_requires_deterministic_clarification(self):
        command = ExplicitCommandParse(
            status=GoalCommandParseStatus.CLARIFICATION_REQUIRED,
            command_kind="fact",
        )
        result = self.engine.decide(
            context(
                user_input="/fact set name",
                explicit_command_parse=command,
            )
        )

        self.assertIs(
            result.primary_decision,
            DecisionType.ASK_CLARIFICATION,
        )
        self.assertEqual(
            result.reason_code,
            DecisionReason.FACT_COMMAND_REQUIRES_CLARIFICATION,
        )
        self.assertTrue(result.requires_confirmation)

    def test_malformed_goal_command_precedes_conversation(self):
        command = ExplicitCommandParse(
            status=GoalCommandParseStatus.CLARIFICATION_REQUIRED,
            operation="create",
        )

        result = self.engine.decide(
            context(
                user_input="/goal create",
                explicit_command_parse=command,
            )
        )

        self.assertEqual(
            result.primary_decision,
            DecisionType.ASK_CLARIFICATION,
        )
        self.assertEqual(
            result.reason_code,
            DecisionReason.GOAL_COMMAND_REQUIRES_CLARIFICATION,
        )
        self.assertTrue(result.requires_confirmation)

    def test_ordinary_and_empty_user_turn_routes(self):
        conversation = self.engine.decide(context(user_input="Adi söhbət"))
        empty = self.engine.decide(context(user_input="   "))

        self.assertEqual(
            conversation.primary_decision,
            DecisionType.CONVERSATION_RESPONSE,
        )
        self.assertEqual(
            conversation.reason_code,
            DecisionReason.ORDINARY_USER_INPUT,
        )
        self.assertEqual(empty.primary_decision, DecisionType.NO_ACTION)
        self.assertEqual(empty.reason_code, DecisionReason.EMPTY_USER_INPUT)

    def test_background_precedence_is_exhaustive_and_ordered(self):
        base = {
            "event_kind": EventKind.BACKGROUND_EVENT,
            "user_input": "",
            "foreground_activity": False,
        }
        foreground = self.engine.decide(
            context(**{
                **base,
                "foreground_activity": True,
                "background_thought_state": "running",
                "operational_state": "thinking",
            })
        )
        running = self.engine.decide(
            context(**base, background_thought_state="running")
        )
        busy = self.engine.decide(
            context(**base, operational_state="thinking")
        )
        eligible = self.engine.decide(context(**base))

        self.assertEqual(foreground.reason_code, DecisionReason.FOREGROUND_ACTIVE)
        self.assertEqual(
            running.reason_code,
            DecisionReason.THOUGHT_ALREADY_RUNNING,
        )
        self.assertEqual(
            busy.reason_code,
            DecisionReason.OPERATIONAL_STATE_NOT_IDLE,
        )
        self.assertEqual(
            eligible.primary_decision,
            DecisionType.THOUGHT_START,
        )
        self.assertEqual(
            eligible.reason_code,
            DecisionReason.BACKGROUND_ELIGIBLE,
        )

    def test_engine_has_no_provider_advice_or_repository_access(self):
        self.assertNotIn("provider_advice", DecisionContext.__dataclass_fields__)
        provider = SimpleNamespace(generate=lambda _prompt: self.fail("provider"))
        with patch.object(
            sqlite3,
            "connect",
            side_effect=AssertionError("repository access"),
        ):
            result = self.engine.decide(context())

        self.assertEqual(
            result.primary_decision,
            DecisionType.CONVERSATION_RESPONSE,
        )
        self.assertIsNotNone(provider)


class DecisionIntegrationTests(unittest.TestCase):
    def _background_nel(
        self,
        *,
        state=State.IDLE,
        foreground=False,
        thought_state="idle",
    ):
        calls = []
        nel = Nel.__new__(Nel)
        nel.background_thoughts_enabled = True
        nel._background_thought_due = lambda: True
        nel.state = SimpleNamespace(get=lambda: state)
        nel.decision = DecisionEngine()
        nel.thought_coordinator = SimpleNamespace(
            foreground_active=foreground,
            state=thought_state,
        )
        nel.thought_service = SimpleNamespace(
            generate=lambda: calls.append("start") or True
        )
        return nel, calls

    def test_background_integration_honors_all_gates(self):
        cases = (
            (True, "idle", State.IDLE),
            (False, "running", State.IDLE),
            (False, "idle", State.THINKING),
        )
        for foreground, thought_state, state in cases:
            with self.subTest(
                foreground=foreground,
                thought_state=thought_state,
                state=state,
            ):
                nel, calls = self._background_nel(
                    state=state,
                    foreground=foreground,
                    thought_state=thought_state,
                )
                nel.on_clock_tick()
                self.assertEqual(calls, [])

        nel, calls = self._background_nel()
        nel.on_clock_tick()
        self.assertEqual(calls, ["start"])


if __name__ == "__main__":
    unittest.main()
