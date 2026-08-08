import json
import unittest
from dataclasses import FrozenInstanceError

from src.conversation import (
    MAX_RECENT_CONTEXT_CHARACTERS,
    MAX_RECENT_TURN_CHARACTERS,
    MAX_RECENT_TURNS,
    ConversationContextError,
    ConversationContextSerializer,
    ConversationSession,
    ExchangeCompletion,
    RecentConversationSnapshot,
    RecentExchange,
    RecentExchangeKind,
    RecentTurn,
    RecentTurnRole,
)


class ConversationContextModelTests(unittest.TestCase):
    def test_models_are_frozen_and_validate_exchange_shape(self):
        user = RecentTurn(1, RecentTurnRole.USER, "Salam")
        assistant = RecentTurn(2, RecentTurnRole.ASSISTANT, "Salam")
        exchange = RecentExchange(
            1,
            RecentExchangeKind.CONVERSATION,
            user,
            assistant,
            ExchangeCompletion.COMPLETE,
        )
        snapshot = RecentConversationSnapshot((exchange,))

        with self.assertRaises(FrozenInstanceError):
            user.literal_text = "changed"
        with self.assertRaises(FrozenInstanceError):
            exchange.kind = RecentExchangeKind.COMMAND
        with self.assertRaises(FrozenInstanceError):
            snapshot.truncated = True
        with self.assertRaises(ValueError):
            RecentExchange(
                2,
                RecentExchangeKind.COMMAND,
                user,
                None,
                ExchangeCompletion.INCOMPLETE,
            )

    def test_accepted_limits_are_exact(self):
        self.assertEqual(MAX_RECENT_TURNS, 8)
        self.assertEqual(MAX_RECENT_CONTEXT_CHARACTERS, 6000)
        self.assertEqual(MAX_RECENT_TURN_CHARACTERS, 4096)


class ConversationContextSerializerTests(unittest.TestCase):
    def test_serialization_is_deterministic_canonical_and_unicode_literal(self):
        session = ConversationSession()
        session.append_complete(
            RecentExchangeKind.CONVERSATION,
            "Kədərli olsun.",
            "Səssiz gecə.",
        )
        serializer = ConversationContextSerializer()

        first = serializer.serialize(session.snapshot())
        second = serializer.serialize(session.snapshot())

        self.assertEqual(first, second)
        self.assertEqual(first.serialized_characters, len(first.canonical_json))
        self.assertIn("Kədərli", first.canonical_json)
        self.assertNotIn("\\u0259", first.canonical_json)
        self.assertEqual(json.loads(first.canonical_json)["availability"], "available")

    def test_serializer_rejects_oversized_snapshot_without_truncation(self):
        user = RecentTurn(1, RecentTurnRole.USER, "u" * 4096)
        assistant = RecentTurn(2, RecentTurnRole.ASSISTANT, "a" * 4096)
        snapshot = RecentConversationSnapshot(
            (
                RecentExchange(
                    1,
                    RecentExchangeKind.CONVERSATION,
                    user,
                    assistant,
                    ExchangeCompletion.COMPLETE,
                ),
            )
        )

        with self.assertRaises(ConversationContextError) as raised:
            ConversationContextSerializer().serialize(snapshot)

        self.assertEqual(raised.exception.reason_code, "recent_context_oversized")

    def test_unavailable_result_is_bounded_valid_json(self):
        result = ConversationContextSerializer().unavailable()

        self.assertEqual(result.availability, "unavailable")
        self.assertLessEqual(result.serialized_characters, 6000)
        self.assertEqual(json.loads(result.canonical_json)["exchanges"], [])


class ConversationSessionTests(unittest.TestCase):
    def test_all_exchange_kinds_are_retained_with_provenance(self):
        session = ConversationSession()
        for kind in RecentExchangeKind:
            self.assertTrue(session.append_complete(kind, kind.value, "cavab"))

        self.assertEqual(
            tuple(item.kind for item in session.snapshot().exchanges),
            tuple(RecentExchangeKind),
        )

    def test_eight_turn_limit_evicts_oldest_complete_exchange(self):
        session = ConversationSession()
        for index in range(5):
            session.append_complete(
                RecentExchangeKind.CONVERSATION,
                f"user-{index}",
                f"assistant-{index}",
            )

        snapshot = session.snapshot()
        self.assertEqual(snapshot.turn_count, 8)
        self.assertEqual(snapshot.exchanges[0].user.literal_text, "user-1")
        self.assertEqual(snapshot.exchanges[-1].assistant.literal_text, "assistant-4")
        self.assertTrue(snapshot.truncated)

    def test_character_budget_evicts_whole_oldest_exchange(self):
        session = ConversationSession(character_limit=500)
        for index in range(4):
            session.append_complete(
                RecentExchangeKind.CONVERSATION,
                f"user-{index}-" + "u" * 80,
                f"assistant-{index}-" + "a" * 80,
            )

        snapshot = session.snapshot()
        serialized = session.serializer.serialize(snapshot)
        self.assertLessEqual(serialized.serialized_characters, 500)
        self.assertEqual(snapshot.turn_count % 2, 0)
        for exchange in snapshot.exchanges:
            self.assertEqual(len(exchange.turns), 2)
        self.assertEqual(snapshot.exchanges[-1].user.literal_text[:6], "user-3")

    def test_oversized_complete_exchange_is_not_retained_or_truncated(self):
        session = ConversationSession()
        retained = session.append_complete(
            RecentExchangeKind.COMMAND,
            "u" * 4096,
            "a" * 4096,
        )

        self.assertFalse(retained)
        self.assertEqual(session.snapshot(), RecentConversationSnapshot())

    def test_individual_oversized_turn_is_rejected(self):
        session = ConversationSession()

        self.assertFalse(
            session.append_complete(
                RecentExchangeKind.CONVERSATION,
                "u" * 4097,
                "assistant",
            )
        )
        self.assertEqual(session.snapshot().turn_count, 0)

    def test_incomplete_provider_turn_is_user_only_and_atomic(self):
        session = ConversationSession()

        self.assertTrue(session.append_incomplete("Davam et."))

        exchange = session.snapshot().exchanges[0]
        self.assertIs(exchange.completion, ExchangeCompletion.INCOMPLETE)
        self.assertIs(exchange.kind, RecentExchangeKind.CONVERSATION)
        self.assertIsNone(exchange.assistant)
        self.assertEqual(exchange.turns, (exchange.user,))

    def test_clear_discards_session_without_persistence(self):
        session = ConversationSession()
        session.append_complete(
            RecentExchangeKind.LOCAL_READ,
            "Sən kimsən?",
            "Nel",
        )

        session.clear()

        self.assertEqual(session.snapshot(), RecentConversationSnapshot())


if __name__ == "__main__":
    unittest.main()
