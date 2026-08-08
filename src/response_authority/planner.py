import re
from dataclasses import dataclass
from enum import Enum

from src.brain.local_intent_classifier import IntentType, LocalIntentClassifier
from src.conversation import RecentConversationSnapshot, RecentExchangeKind


class ResponseMode(str, Enum):
    LOCAL_RENDER = "local_render"
    PROVIDER_GENERAL = "provider_general"
    PROVIDER_GUARDED = "provider_guarded"
    CLARIFY = "clarify"


class AuthorityRequirement(str, Enum):
    NONE = "none"
    STRUCTURED_REQUIRED = "structured_required"
    DURABLE_MEMORY_ONLY = "durable_memory_only"


class ResponseReason(str, Enum):
    GENERAL_CONVERSATION = "general_conversation"
    AMBIGUOUS_PERSONAL_FOLLOWUP = "ambiguous_personal_followup"
    UNSUPPORTED_PERSONAL_STATE_QUERY = "unsupported_personal_state_query"
    MIXED_PERSONAL_GENERAL_REQUEST = "mixed_personal_general_request"
    PLANNER_FAILURE_PERSONAL_SAFETY = "planner_failure_personal_safety"


@dataclass(frozen=True)
class ResponseAuthorityPlan:
    mode: ResponseMode
    authority_requirement: AuthorityRequirement
    reason_code: ResponseReason


class ResponseAuthorityPlanner:
    """Pure, narrow protection for deterministic personal-state boundaries."""

    _SHORT_CONTRAST = re.compile(r"^bəs\s+[^?!.]{1,80}\?$")
    _GENERAL_CUES = frozenset(
        {"nədir", "necədir", "kimdir", "haradadır", "nə üçün"}
    )

    def __init__(self, local_intent_classifier=None):
        self.local_intent = local_intent_classifier or LocalIntentClassifier()

    def plan(self, user_input, recent_snapshot):
        if self._is_guarded_personal_followup(user_input, recent_snapshot):
            return ResponseAuthorityPlan(
                ResponseMode.CLARIFY,
                AuthorityRequirement.STRUCTURED_REQUIRED,
                ResponseReason.AMBIGUOUS_PERSONAL_FOLLOWUP,
            )
        if self._is_personal_state_question(user_input):
            reason = (
                ResponseReason.MIXED_PERSONAL_GENERAL_REQUEST
                if self._has_general_cue(user_input)
                else ResponseReason.UNSUPPORTED_PERSONAL_STATE_QUERY
            )
            return ResponseAuthorityPlan(
                ResponseMode.CLARIFY,
                AuthorityRequirement.STRUCTURED_REQUIRED,
                reason,
            )
        return ResponseAuthorityPlan(
            ResponseMode.PROVIDER_GENERAL,
            AuthorityRequirement.NONE,
            ResponseReason.GENERAL_CONVERSATION,
        )

    def safe_failure_plan(self, user_input, recent_snapshot):
        if self._is_guarded_personal_followup(
            user_input,
            recent_snapshot,
        ) or self._is_personal_state_question(user_input):
            return ResponseAuthorityPlan(
                ResponseMode.CLARIFY,
                AuthorityRequirement.STRUCTURED_REQUIRED,
                ResponseReason.PLANNER_FAILURE_PERSONAL_SAFETY,
            )
        return ResponseAuthorityPlan(
            ResponseMode.PROVIDER_GENERAL,
            AuthorityRequirement.NONE,
            ResponseReason.GENERAL_CONVERSATION,
        )

    def _is_guarded_personal_followup(self, user_input, recent_snapshot):
        if not isinstance(recent_snapshot, RecentConversationSnapshot):
            return False
        normalized = self.local_intent.normalize(user_input)
        if not self._SHORT_CONTRAST.fullmatch(normalized + "?"):
            return False
        if not recent_snapshot.exchanges:
            return False
        exchange = recent_snapshot.exchanges[-1]
        if exchange.kind is RecentExchangeKind.LOCAL_READ:
            return (
                self.local_intent.classify(exchange.user.literal_text)
                is IntentType.USER_FACT_QUERY
            )
        return self._looks_like_personal_assertion(exchange.user.literal_text)

    def _is_personal_state_question(self, user_input):
        if not isinstance(user_input, str) or "?" not in user_input:
            return False
        normalized = self.local_intent.normalize(user_input)
        if "məqsəd" in normalized or "hədəf" in normalized:
            return False
        return normalized.startswith("mən ") or normalized.startswith("mənim ")

    def _has_general_cue(self, user_input):
        normalized = self.local_intent.normalize(user_input)
        return any(cue in normalized for cue in self._GENERAL_CUES)

    def _looks_like_personal_assertion(self, text):
        if not isinstance(text, str) or "?" in text:
            return False
        normalized = self.local_intent.normalize(text)
        return normalized.startswith("mən ") or normalized.startswith("mənim ")
