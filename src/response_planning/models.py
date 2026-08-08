from dataclasses import dataclass
from enum import Enum


class ResponseDelivery(str, Enum):
    LOCAL = "local"
    PROVIDER = "provider"


class ResponsePurpose(str, Enum):
    GENERAL = "general"
    CREATIVE = "creative"
    CONTINUATION = "continuation"
    CLARIFICATION = "clarification"
    PERSONAL_AUTHORITATIVE = "personal_authoritative"
    IDENTITY = "identity"


class IdentityPolicy(str, Enum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


class PersonalizationPolicy(str, Enum):
    NONE = "none"
    OPTIONAL_STRUCTURED = "optional_structured"


class ContinuitySource(str, Enum):
    NONE = "none"
    IMMEDIATE_CONVERSATION = "immediate_conversation"


class ResponseReason(str, Enum):
    GENERAL_INPUT = "general_input"
    CREATIVE_REQUEST = "creative_request"
    IMMEDIATE_CONTINUATION = "immediate_continuation"
    PLANNER_FAILURE = "planner_failure"
    EXPLICIT_IDENTITY = "explicit_identity"
    OWN_PREFERENCE_QUERY = "own_preference_query"


@dataclass(frozen=True)
class ResponsePlan:
    delivery: ResponseDelivery
    purpose: ResponsePurpose
    identity_policy: IdentityPolicy
    personalization_policy: PersonalizationPolicy
    continuity_source: ContinuitySource
    reason_code: ResponseReason
