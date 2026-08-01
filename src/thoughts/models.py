from dataclasses import dataclass
from enum import Enum


THOUGHT_MEMORY_LIMIT = 5
THOUGHT_FACT_LIMIT = 20
THOUGHT_IDENTITY_CORE_LIMIT = 4
THOUGHT_IDENTITY_PREFERENCE_LIMIT = 10
THOUGHT_TEXT_LIMIT = 1000
THOUGHT_VALUE_LIMIT = 256


class ThoughtKind(str, Enum):
    OBSERVATION_CANDIDATE = "observation_candidate"
    CONTRADICTION_CANDIDATE = "contradiction_candidate"
    POSSIBLE_CONVERSATION_TOPIC = "possible_conversation_topic"
    NO_ACTION = "no_action"


@dataclass(frozen=True)
class ReadOnlyThoughtContext:
    reason: str
    source_reference: str
    memories: tuple[str, ...] = ()
    user_facts: tuple[tuple[str, str], ...] = ()
    identity_core: tuple[tuple[str, str], ...] = ()
    established_preferences: tuple[tuple[str, str], ...] = ()
    provisional_preferences: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if (
            not isinstance(self.reason, str)
            or not isinstance(self.source_reference, str)
            or not self.reason
            or not self.source_reference
            or len(self.reason) > THOUGHT_VALUE_LIMIT
            or len(self.source_reference) > THOUGHT_VALUE_LIMIT
        ):
            raise ValueError("Thought context requires a reason and source.")
        if len(self.memories) > THOUGHT_MEMORY_LIMIT:
            raise ValueError("Thought memory context exceeds its limit.")
        if len(self.user_facts) > THOUGHT_FACT_LIMIT:
            raise ValueError("Thought fact context exceeds its limit.")
        if len(self.identity_core) > THOUGHT_IDENTITY_CORE_LIMIT:
            raise ValueError("Thought identity core exceeds its limit.")
        if (
            len(self.established_preferences)
            + len(self.provisional_preferences)
            > THOUGHT_IDENTITY_PREFERENCE_LIMIT
        ):
            raise ValueError("Thought identity context exceeds its limit.")
        for memory in self.memories:
            if not isinstance(memory, str) or len(memory) > THOUGHT_TEXT_LIMIT:
                raise ValueError("Thought memory context is invalid.")
        for collection in (
            self.user_facts,
            self.identity_core,
            self.established_preferences,
            self.provisional_preferences,
        ):
            for key, value in collection:
                if (
                    not isinstance(key, str)
                    or not isinstance(value, str)
                    or not key
                    or len(key) > THOUGHT_VALUE_LIMIT
                    or len(value) > THOUGHT_VALUE_LIMIT
                ):
                    raise ValueError("Thought structured context is invalid.")

    def to_payload(self) -> dict:
        return {
            "reason": self.reason,
            "source_reference": self.source_reference,
            "memories": list(self.memories),
            "user_facts": dict(self.user_facts),
            "nel_identity": {
                "core": dict(self.identity_core),
                "established_preferences": dict(
                    self.established_preferences
                ),
                "provisional_preferences": dict(
                    self.provisional_preferences
                ),
            },
        }


@dataclass(frozen=True)
class TypedThoughtResult:
    kind: ThoughtKind
    content: str | None
    retention_reason: str | None
    source_reference: str
    durability_suggestion: str

    def __post_init__(self):
        if not isinstance(self.kind, ThoughtKind):
            raise ValueError("Thought result kind is invalid.")
        if not self.source_reference:
            raise ValueError("Thought result source is required.")
        if self.durability_suggestion not in {
            "none",
            "temporary",
            "review",
        }:
            raise ValueError("Thought durability suggestion is invalid.")
        if self.kind is ThoughtKind.NO_ACTION:
            if self.content is not None or self.retention_reason is not None:
                raise ValueError("No-action thought result must be empty.")
            if self.durability_suggestion != "none":
                raise ValueError("No-action thought cannot suggest durability.")
            return
        if (
            not isinstance(self.content, str)
            or not self.content.strip()
            or len(self.content) > THOUGHT_TEXT_LIMIT
        ):
            raise ValueError("Thought result content is invalid.")
        if (
            not isinstance(self.retention_reason, str)
            or not self.retention_reason.strip()
            or len(self.retention_reason) > THOUGHT_VALUE_LIMIT
        ):
            raise ValueError("Thought retention reason is invalid.")

    @classmethod
    def from_payload(
        cls,
        payload: dict,
        *,
        source_reference: str,
    ):
        if not isinstance(payload, dict):
            raise ValueError("Thought result must be an object.")
        allowed = {
            "kind",
            "content",
            "retention_reason",
            "durability_suggestion",
        }
        if set(payload) != allowed:
            raise ValueError("Thought result fields are invalid.")
        try:
            kind = ThoughtKind(payload["kind"])
        except (TypeError, ValueError):
            raise ValueError("Thought result kind is invalid.") from None
        return cls(
            kind=kind,
            content=payload["content"],
            retention_reason=payload["retention_reason"],
            source_reference=source_reference,
            durability_suggestion=payload["durability_suggestion"],
        )
