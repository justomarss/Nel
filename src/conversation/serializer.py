import json

from src.conversation.models import (
    MAX_RECENT_CONTEXT_CHARACTERS,
    MAX_RECENT_TURN_CHARACTERS,
    RecentConversationContextResult,
    RecentConversationSnapshot,
)


class ConversationContextError(ValueError):
    def __init__(self, reason_code):
        self.reason_code = reason_code
        super().__init__(reason_code)


class ConversationContextSerializer:
    def __init__(
        self,
        *,
        character_limit=MAX_RECENT_CONTEXT_CHARACTERS,
        turn_character_limit=MAX_RECENT_TURN_CHARACTERS,
    ):
        for name, value in (
            ("character_limit", character_limit),
            ("turn_character_limit", turn_character_limit),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        self.character_limit = character_limit
        self.turn_character_limit = turn_character_limit

    def serialize(self, snapshot):
        if not isinstance(snapshot, RecentConversationSnapshot):
            raise ConversationContextError("recent_context_malformed")
        canonical = self._canonical(snapshot)
        if len(canonical) > self.character_limit:
            raise ConversationContextError("recent_context_oversized")
        return RecentConversationContextResult(
            canonical_json=canonical,
            serialized_characters=len(canonical),
            retained_turns=snapshot.turn_count,
            truncated=snapshot.truncated,
            availability="available",
        )

    def measure(self, snapshot):
        if not isinstance(snapshot, RecentConversationSnapshot):
            raise ConversationContextError("recent_context_malformed")
        return len(self._canonical(snapshot))

    def unavailable(self):
        canonical = self._dump(
            {
                "availability": "unavailable",
                "exchanges": [],
                "truncated": False,
            }
        )
        return RecentConversationContextResult(
            canonical_json=canonical,
            serialized_characters=len(canonical),
            retained_turns=0,
            truncated=False,
            availability="unavailable",
        )

    def _canonical(self, snapshot):
        exchanges = []
        for exchange in snapshot.exchanges:
            turns = []
            for turn in exchange.turns:
                if len(turn.literal_text) > self.turn_character_limit:
                    raise ConversationContextError("recent_turn_oversized")
                turns.append(
                    {
                        "role": turn.role.value,
                        "text": turn.literal_text,
                    }
                )
            exchanges.append(
                {
                    "completion": exchange.completion.value,
                    "kind": exchange.kind.value,
                    "turns": turns,
                }
            )
        return self._dump(
            {
                "availability": "available",
                "exchanges": exchanges,
                "truncated": snapshot.truncated,
            }
        )

    @staticmethod
    def _dump(value):
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError):
            raise ConversationContextError("recent_context_serialization_failed") from None
