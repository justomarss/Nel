from threading import RLock

from src.conversation.models import (
    MAX_RECENT_CONTEXT_CHARACTERS,
    MAX_RECENT_TURN_CHARACTERS,
    MAX_RECENT_TURNS,
    ExchangeCompletion,
    RecentConversationSnapshot,
    RecentExchange,
    RecentExchangeKind,
    RecentTurn,
    RecentTurnRole,
)
from src.conversation.serializer import ConversationContextSerializer


class ConversationSession:
    def __init__(
        self,
        *,
        turn_limit=MAX_RECENT_TURNS,
        character_limit=MAX_RECENT_CONTEXT_CHARACTERS,
        turn_character_limit=MAX_RECENT_TURN_CHARACTERS,
        serializer=None,
    ):
        for name, value in (
            ("turn_limit", turn_limit),
            ("character_limit", character_limit),
            ("turn_character_limit", turn_character_limit),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        self.turn_limit = turn_limit
        self.character_limit = character_limit
        self.turn_character_limit = turn_character_limit
        self.serializer = serializer or ConversationContextSerializer(
            character_limit=character_limit,
            turn_character_limit=turn_character_limit,
        )
        self._snapshot = RecentConversationSnapshot()
        self._next_turn_id = 1
        self._next_exchange_id = 1
        self._lock = RLock()

    def snapshot(self):
        with self._lock:
            return self._snapshot

    def append_complete(self, kind, user_text, assistant_text):
        if not isinstance(kind, RecentExchangeKind):
            return False
        if not self._eligible_text(user_text) or not self._eligible_text(
            assistant_text
        ):
            return False
        with self._lock:
            user = RecentTurn(
                self._next_turn_id,
                RecentTurnRole.USER,
                user_text,
            )
            assistant = RecentTurn(
                self._next_turn_id + 1,
                RecentTurnRole.ASSISTANT,
                assistant_text,
            )
            exchange = RecentExchange(
                exchange_id=self._next_exchange_id,
                kind=kind,
                user=user,
                assistant=assistant,
                completion=ExchangeCompletion.COMPLETE,
            )
            if not self._append(exchange):
                return False
            self._next_turn_id += 2
            self._next_exchange_id += 1
            return True

    def append_incomplete(self, user_text):
        if not self._eligible_text(user_text):
            return False
        with self._lock:
            user = RecentTurn(
                self._next_turn_id,
                RecentTurnRole.USER,
                user_text,
            )
            exchange = RecentExchange(
                exchange_id=self._next_exchange_id,
                kind=RecentExchangeKind.CONVERSATION,
                user=user,
                assistant=None,
                completion=ExchangeCompletion.INCOMPLETE,
            )
            if not self._append(exchange):
                return False
            self._next_turn_id += 1
            self._next_exchange_id += 1
            return True

    def clear(self):
        with self._lock:
            self._snapshot = RecentConversationSnapshot()
            self._next_turn_id = 1
            self._next_exchange_id = 1

    def _eligible_text(self, text):
        return (
            isinstance(text, str)
            and bool(text)
            and len(text) <= self.turn_character_limit
        )

    def _append(self, exchange):
        single = RecentConversationSnapshot(exchanges=(exchange,))
        try:
            if self.serializer.measure(single) > self.character_limit:
                return False
        except Exception:
            return False

        exchanges = self._snapshot.exchanges + (exchange,)
        evicted = False
        while exchanges:
            candidate = RecentConversationSnapshot(
                exchanges=exchanges,
                truncated=self._snapshot.truncated or evicted,
            )
            try:
                measured = self.serializer.measure(candidate)
            except Exception:
                return False
            if candidate.turn_count <= self.turn_limit and measured <= self.character_limit:
                self._snapshot = candidate
                return True
            exchanges = exchanges[1:]
            evicted = True
        return False
