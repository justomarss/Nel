import json
import threading

from src.thoughts.models import ReadOnlyThoughtContext, TypedThoughtResult


THOUGHT_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "observation_candidate",
                "contradiction_candidate",
                "possible_conversation_topic",
                "no_action",
            ],
        },
        "content": {"type": ["string", "null"]},
        "retention_reason": {"type": ["string", "null"]},
        "durability_suggestion": {
            "type": "string",
            "enum": ["none", "temporary", "review"],
        },
    },
    "required": [
        "kind",
        "content",
        "retention_reason",
        "durability_suggestion",
    ],
    "additionalProperties": False,
}


class ThoughtWorker:
    def __init__(self, provider):
        self.provider = provider

    def run(
        self,
        context: ReadOnlyThoughtContext,
        cancelled: threading.Event,
    ) -> TypedThoughtResult | None:
        if cancelled.is_set():
            return None
        prompt = self._prompt(context)
        generate_structured = getattr(
            self.provider,
            "generate_structured",
            None,
        )
        if callable(generate_structured):
            payload = generate_structured(
                prompt,
                THOUGHT_RESULT_SCHEMA,
                "nel_temporary_thought",
            )
        else:
            payload = self.provider.generate(prompt)
        if cancelled.is_set():
            return None
        if isinstance(payload, str):
            payload = json.loads(payload)
        return TypedThoughtResult.from_payload(
            payload,
            source_reference=context.source_reference,
        )

    @staticmethod
    def _prompt(context: ReadOnlyThoughtContext) -> str:
        payload = json.dumps(
            context.to_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"""
Produce one temporary internal observation for Nel from the bounded read-only
context below. A thought is an observation, never an authority.

The result is not conversation, memory, knowledge, identity, a goal, or an
action. Do not request or perform writes. Return only the required typed JSON.

Read-only context:
{payload}
"""
