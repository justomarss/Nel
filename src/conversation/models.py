from dataclasses import dataclass
from enum import Enum


MAX_RECENT_TURNS = 8
MAX_RECENT_CONTEXT_CHARACTERS = 6000
MAX_RECENT_TURN_CHARACTERS = 4096


class RecentTurnRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class RecentExchangeKind(str, Enum):
    CONVERSATION = "conversation"
    LOCAL_READ = "local_read"
    COMMAND = "command"


class ExchangeCompletion(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class RecentTurn:
    turn_id: int
    role: RecentTurnRole
    literal_text: str

    def __post_init__(self):
        if (
            isinstance(self.turn_id, bool)
            or not isinstance(self.turn_id, int)
            or self.turn_id < 1
        ):
            raise ValueError("turn_id must be a positive integer.")
        if not isinstance(self.role, RecentTurnRole):
            raise ValueError("role must be a RecentTurnRole.")
        if not isinstance(self.literal_text, str) or not self.literal_text:
            raise ValueError("literal_text must be a non-empty string.")


@dataclass(frozen=True)
class RecentExchange:
    exchange_id: int
    kind: RecentExchangeKind
    user: RecentTurn
    assistant: RecentTurn | None
    completion: ExchangeCompletion

    def __post_init__(self):
        if (
            isinstance(self.exchange_id, bool)
            or not isinstance(self.exchange_id, int)
            or self.exchange_id < 1
        ):
            raise ValueError("exchange_id must be a positive integer.")
        if not isinstance(self.kind, RecentExchangeKind):
            raise ValueError("kind must be a RecentExchangeKind.")
        if not isinstance(self.user, RecentTurn):
            raise ValueError("user must be a RecentTurn.")
        if self.user.role is not RecentTurnRole.USER:
            raise ValueError("exchange user turn must have the user role.")
        if self.completion is ExchangeCompletion.COMPLETE:
            if not isinstance(self.assistant, RecentTurn):
                raise ValueError("complete exchanges require an assistant turn.")
            if self.assistant.role is not RecentTurnRole.ASSISTANT:
                raise ValueError("exchange assistant turn must have the assistant role.")
            if self.assistant.turn_id <= self.user.turn_id:
                raise ValueError("assistant turn must follow the user turn.")
        elif self.completion is ExchangeCompletion.INCOMPLETE:
            if self.assistant is not None:
                raise ValueError("incomplete exchanges cannot have an assistant turn.")
            if self.kind is not RecentExchangeKind.CONVERSATION:
                raise ValueError("only conversation exchanges may be incomplete.")
        else:
            raise ValueError("completion must be an ExchangeCompletion.")

    @property
    def turns(self) -> tuple[RecentTurn, ...]:
        if self.assistant is None:
            return (self.user,)
        return (self.user, self.assistant)


@dataclass(frozen=True)
class RecentConversationSnapshot:
    exchanges: tuple[RecentExchange, ...] = ()
    truncated: bool = False

    def __post_init__(self):
        if not isinstance(self.exchanges, tuple):
            raise ValueError("exchanges must be a tuple.")
        if any(not isinstance(item, RecentExchange) for item in self.exchanges):
            raise ValueError("snapshot exchanges must be RecentExchange values.")
        if isinstance(self.truncated, bool) is False:
            raise ValueError("truncated must be a boolean.")
        exchange_ids = tuple(item.exchange_id for item in self.exchanges)
        if exchange_ids != tuple(sorted(exchange_ids)):
            raise ValueError("snapshot exchanges must be chronologically ordered.")
        if len(exchange_ids) != len(set(exchange_ids)):
            raise ValueError("snapshot exchange identifiers must be unique.")

    @property
    def turn_count(self) -> int:
        return sum(len(exchange.turns) for exchange in self.exchanges)


@dataclass(frozen=True)
class RecentConversationContextResult:
    canonical_json: str
    serialized_characters: int
    retained_turns: int
    truncated: bool
    availability: str
