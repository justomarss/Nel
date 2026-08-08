import json

from src.context import ContextAssembler
from src.identity.models import IdentitySnapshot


class StaticIdentityService:
    def __init__(self):
        self.value = IdentitySnapshot(
            identity_id="nel",
            display_name="Nel",
            nature="artificial",
            role="Ömər’s persistent digital companion",
            preferences=(),
        )

    def snapshot(self):
        return self.value

    def context_snapshot(self, limit=1000):
        return self.value


def attach_context_assembler(nel):
    nel.identity = getattr(nel, "identity", None) or StaticIdentityService()
    nel.goals = getattr(nel, "goals", None)
    nel.context_assembler = ContextAssembler(
        identity_service=nel.identity,
        knowledge_service=nel.knowledge,
        goal_service=nel.goals,
        memory_service=nel.memory,
    )
    return nel.context_assembler


def unified_context(prompt: str) -> dict:
    marker = "Unified context JSON:\n"
    payload = prompt.split(marker, 1)[1]
    payload = payload.split("\n\nRecent conversation JSON:\n", 1)[0]
    payload = payload.split("\n\nUser:\n", 1)[0]
    return json.loads(payload)


def recent_conversation_context(prompt: str) -> dict:
    marker = "Recent conversation JSON:\n"
    payload = prompt.split(marker, 1)[1]
    payload = payload.split("\n\nResponse plan:\n", 1)[0]
    payload = payload.split("\n\nUser:\n", 1)[0]
    return json.loads(payload)
