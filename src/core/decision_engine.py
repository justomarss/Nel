import json
from dataclasses import dataclass, field
from enum import Enum


USER_INPUT_MAX_CHARS = 4096
COMMAND_PARSE_MAX_CHARS = 4096
DECISION_CONTEXT_MAX_CHARS = 8192
IDENTIFIER_MAX_CHARS = 128
STATE_MAX_CHARS = 64
VALID_OPERATIONAL_STATES = frozenset(
    {"idle", "thinking", "talking", "busy", "bored", "sleeping"}
)
VALID_BACKGROUND_THOUGHT_STATES = frozenset({"idle", "running"})


class DecisionType(str, Enum):
    CONVERSATION_RESPONSE = "conversation_response"
    ASK_CLARIFICATION = "ask_clarification"
    GOAL_COMMAND = "goal_command"
    FACT_COMMAND = "fact_command"
    THOUGHT_START = "thought_start"
    NO_ACTION = "no_action"


class EventKind(str, Enum):
    USER_TURN = "user_turn"
    BACKGROUND_EVENT = "background_event"


class GoalCommandParseStatus(str, Enum):
    NOT_COMMAND = "not_command"
    CONFIRMED = "confirmed"
    CLARIFICATION_REQUIRED = "clarification_required"


class DecisionReason(str, Enum):
    INVALID_CONTEXT = "invalid_context"
    CONFIRMED_GOAL_COMMAND = "confirmed_goal_command"
    GOAL_COMMAND_REQUIRES_CLARIFICATION = (
        "goal_command_requires_clarification"
    )
    CONFIRMED_FACT_COMMAND = "confirmed_fact_command"
    FACT_COMMAND_REQUIRES_CLARIFICATION = (
        "fact_command_requires_clarification"
    )
    ORDINARY_USER_INPUT = "ordinary_user_input"
    EMPTY_USER_INPUT = "empty_user_input"
    FOREGROUND_ACTIVE = "foreground_active"
    THOUGHT_ALREADY_RUNNING = "thought_already_running"
    OPERATIONAL_STATE_NOT_IDLE = "operational_state_not_idle"
    BACKGROUND_ELIGIBLE = "background_eligible"


@dataclass(frozen=True)
class ExplicitCommandParse:
    status: GoalCommandParseStatus = GoalCommandParseStatus.NOT_COMMAND
    operation: str | None = None
    arguments: tuple[str, ...] = ()
    command_kind: str | None = None

    @classmethod
    def not_command(cls):
        return cls()

    def serialized_length(self) -> int:
        return len(
            json.dumps(
                {
                    "status": getattr(self.status, "value", self.status),
                    "operation": self.operation,
                    "arguments": self.arguments,
                    "command_kind": self.command_kind,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )


@dataclass(frozen=True)
class DecisionContext:
    event_id: str
    event_kind: EventKind
    user_input: str
    operational_state: str
    explicit_command_parse: ExplicitCommandParse = field(
        default_factory=ExplicitCommandParse.not_command
    )
    foreground_activity: bool = False
    background_thought_state: str = "idle"


_TARGETS = {
    DecisionType.CONVERSATION_RESPONSE: "conversation_flow",
    DecisionType.ASK_CLARIFICATION: "deterministic_clarification",
    DecisionType.GOAL_COMMAND: "goal_command_handler",
    DecisionType.FACT_COMMAND: "fact_command_handler",
    DecisionType.THOUGHT_START: "thought_coordinator",
    DecisionType.NO_ACTION: "none",
}
_REASONS = {
    DecisionType.CONVERSATION_RESPONSE: {
        DecisionReason.ORDINARY_USER_INPUT,
    },
    DecisionType.ASK_CLARIFICATION: {
        DecisionReason.GOAL_COMMAND_REQUIRES_CLARIFICATION,
        DecisionReason.FACT_COMMAND_REQUIRES_CLARIFICATION,
    },
    DecisionType.GOAL_COMMAND: {
        DecisionReason.CONFIRMED_GOAL_COMMAND,
    },
    DecisionType.FACT_COMMAND: {
        DecisionReason.CONFIRMED_FACT_COMMAND,
    },
    DecisionType.THOUGHT_START: {
        DecisionReason.BACKGROUND_ELIGIBLE,
    },
    DecisionType.NO_ACTION: {
        DecisionReason.INVALID_CONTEXT,
        DecisionReason.EMPTY_USER_INPUT,
        DecisionReason.FOREGROUND_ACTIVE,
        DecisionReason.THOUGHT_ALREADY_RUNNING,
        DecisionReason.OPERATIONAL_STATE_NOT_IDLE,
    },
}


@dataclass(frozen=True)
class DecisionResult:
    event_id: str
    primary_decision: DecisionType
    target_route: str
    reason_code: DecisionReason
    validated_command_payload: tuple[str, ...] | None = None
    requires_confirmation: bool = False

    def __post_init__(self):
        if not isinstance(self.primary_decision, DecisionType):
            raise ValueError("Decision type is invalid.")
        if self.target_route != _TARGETS[self.primary_decision]:
            raise ValueError("Decision target does not match its type.")
        if not isinstance(self.reason_code, DecisionReason):
            raise ValueError("Decision reason is invalid.")
        if self.reason_code not in _REASONS[self.primary_decision]:
            raise ValueError("Decision reason does not match its type.")
        if self.primary_decision in {
            DecisionType.GOAL_COMMAND,
            DecisionType.FACT_COMMAND,
        }:
            if not self.validated_command_payload:
                raise ValueError("Command payload is required.")
        elif self.validated_command_payload is not None:
            raise ValueError("Only explicit commands may carry a payload.")
        if self.requires_confirmation is not (
            self.primary_decision is DecisionType.ASK_CLARIFICATION
        ):
            raise ValueError("Decision confirmation flag is inconsistent.")


class DecisionEngine:
    def decide(self, context: DecisionContext) -> DecisionResult:
        if not self._valid_context(context):
            return self._result(
                context,
                DecisionType.NO_ACTION,
                DecisionReason.INVALID_CONTEXT,
            )
        if context.event_kind is EventKind.USER_TURN:
            return self._decide_user_turn(context)
        return self._decide_background_event(context)

    def _decide_user_turn(self, context: DecisionContext) -> DecisionResult:
        command = context.explicit_command_parse
        if command.status is GoalCommandParseStatus.CONFIRMED:
            if command.command_kind == "fact":
                return self._result(
                    context,
                    DecisionType.FACT_COMMAND,
                    DecisionReason.CONFIRMED_FACT_COMMAND,
                    payload=command.arguments,
                )
            return self._result(
                context,
                DecisionType.GOAL_COMMAND,
                DecisionReason.CONFIRMED_GOAL_COMMAND,
                payload=command.arguments,
            )
        if command.status is GoalCommandParseStatus.CLARIFICATION_REQUIRED:
            reason = (
                DecisionReason.FACT_COMMAND_REQUIRES_CLARIFICATION
                if command.command_kind == "fact"
                else DecisionReason.GOAL_COMMAND_REQUIRES_CLARIFICATION
            )
            return self._result(
                context,
                DecisionType.ASK_CLARIFICATION,
                reason,
                requires_confirmation=True,
            )
        if context.user_input.strip():
            return self._result(
                context,
                DecisionType.CONVERSATION_RESPONSE,
                DecisionReason.ORDINARY_USER_INPUT,
            )
        return self._result(
            context,
            DecisionType.NO_ACTION,
            DecisionReason.EMPTY_USER_INPUT,
        )

    def _decide_background_event(
        self,
        context: DecisionContext,
    ) -> DecisionResult:
        if context.foreground_activity:
            return self._result(
                context,
                DecisionType.NO_ACTION,
                DecisionReason.FOREGROUND_ACTIVE,
            )
        if context.background_thought_state == "running":
            return self._result(
                context,
                DecisionType.NO_ACTION,
                DecisionReason.THOUGHT_ALREADY_RUNNING,
            )
        if context.operational_state != "idle":
            return self._result(
                context,
                DecisionType.NO_ACTION,
                DecisionReason.OPERATIONAL_STATE_NOT_IDLE,
            )
        return self._result(
            context,
            DecisionType.THOUGHT_START,
            DecisionReason.BACKGROUND_ELIGIBLE,
        )

    @staticmethod
    def _result(
        context,
        decision_type,
        reason,
        *,
        payload=None,
        requires_confirmation=False,
    ) -> DecisionResult:
        event_id = getattr(context, "event_id", None)
        if not isinstance(event_id, str) or not event_id:
            event_id = "invalid-event"
        return DecisionResult(
            event_id=event_id[:IDENTIFIER_MAX_CHARS],
            primary_decision=decision_type,
            target_route=_TARGETS[decision_type],
            reason_code=reason,
            validated_command_payload=payload,
            requires_confirmation=requires_confirmation,
        )

    @staticmethod
    def _valid_context(context) -> bool:
        if not isinstance(context, DecisionContext):
            return False
        if (
            not isinstance(context.event_id, str)
            or not context.event_id
            or len(context.event_id) > IDENTIFIER_MAX_CHARS
            or not isinstance(context.event_kind, EventKind)
            or not isinstance(context.user_input, str)
            or len(context.user_input) > USER_INPUT_MAX_CHARS
            or not isinstance(context.operational_state, str)
            or len(context.operational_state) > STATE_MAX_CHARS
            or context.operational_state not in VALID_OPERATIONAL_STATES
            or not isinstance(context.explicit_command_parse, ExplicitCommandParse)
            or not isinstance(context.foreground_activity, bool)
            or not isinstance(context.background_thought_state, str)
            or len(context.background_thought_state) > STATE_MAX_CHARS
            or context.background_thought_state
            not in VALID_BACKGROUND_THOUGHT_STATES
        ):
            return False
        command = context.explicit_command_parse
        if (
            not isinstance(command.status, GoalCommandParseStatus)
            or (command.operation is not None and not isinstance(command.operation, str))
            or command.command_kind not in {None, "goal", "fact"}
            or not isinstance(command.arguments, tuple)
            or any(not isinstance(value, str) for value in command.arguments)
            or command.serialized_length() > COMMAND_PARSE_MAX_CHARS
        ):
            return False
        if command.status is GoalCommandParseStatus.NOT_COMMAND and (
            command.operation is not None
            or command.arguments
            or command.command_kind is not None
        ):
            return False
        if command.status is GoalCommandParseStatus.CONFIRMED and (
            not command.operation or not command.arguments
        ):
            return False
        try:
            serialized = json.dumps(
                {
                    "event_id": context.event_id,
                    "event_kind": context.event_kind.value,
                    "user_input": context.user_input,
                    "operational_state": context.operational_state,
                    "explicit_command_parse": {
                        "status": command.status.value,
                        "operation": command.operation,
                        "arguments": command.arguments,
                        "command_kind": command.command_kind,
                    },
                    "foreground_activity": context.foreground_activity,
                    "background_thought_state": context.background_thought_state,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            return False
        return len(serialized) <= DECISION_CONTEXT_MAX_CHARS
