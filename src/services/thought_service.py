from src.thoughts.models import (
    THOUGHT_FACT_LIMIT,
    THOUGHT_IDENTITY_PREFERENCE_LIMIT,
    THOUGHT_MEMORY_LIMIT,
    THOUGHT_TEXT_LIMIT,
    THOUGHT_VALUE_LIMIT,
    ReadOnlyThoughtContext,
)


class ThoughtService:
    def __init__(
        self,
        coordinator,
        *,
        memory,
        knowledge,
        identity,
    ):
        self.coordinator = coordinator
        self.memory = memory
        self.knowledge = knowledge
        self.identity = identity

    def generate(
        self,
        *,
        reason="scheduled_reflection",
        source_reference="clock_tick",
        required_fact_keys=(),
    ) -> bool:
        context = self.build_context(
            reason=reason,
            source_reference=source_reference,
            required_fact_keys=required_fact_keys,
        )
        return self.coordinator.start(context)

    def build_context(
        self,
        *,
        reason,
        source_reference,
        required_fact_keys=(),
    ) -> ReadOnlyThoughtContext:
        memories = tuple(
            memory
            for memory in self.memory.recall(limit=THOUGHT_MEMORY_LIMIT)
            if isinstance(memory, str) and len(memory) <= THOUGHT_TEXT_LIMIT
        )
        all_facts = self.knowledge.facts()
        selected_keys = sorted(set(required_fact_keys))[:THOUGHT_FACT_LIMIT]
        user_facts = tuple(
            (key, all_facts[key])
            for key in selected_keys
            if key in all_facts
            and self._valid_pair(key, all_facts[key])
        )

        identity_core = ()
        established = ()
        provisional = ()
        if self.identity is not None:
            snapshot = self.identity.snapshot()
            identity_core = tuple(
                (key, value)
                for key, value in (
                    ("identity_id", snapshot.identity_id),
                    ("display_name", snapshot.display_name),
                    ("nature", snapshot.nature),
                    ("role", snapshot.role),
                )
                if self._valid_pair(key, value)
            )
            established_records = sorted(
                (
                    record
                    for record in snapshot.preferences
                    if record.preference_state == "established"
                    and self._valid_pair(record.key, record.value)
                ),
                key=lambda record: record.key,
            )
            provisional_records = sorted(
                (
                    record
                    for record in snapshot.preferences
                    if record.preference_state == "provisional"
                    and self._valid_pair(record.key, record.value)
                ),
                key=lambda record: record.key,
            )
            established = tuple(
                (record.key, record.value)
                for record in established_records[
                    :THOUGHT_IDENTITY_PREFERENCE_LIMIT
                ]
            )
            remaining = (
                THOUGHT_IDENTITY_PREFERENCE_LIMIT - len(established)
            )
            provisional = tuple(
                (record.key, record.value)
                for record in provisional_records[:remaining]
            )

        return ReadOnlyThoughtContext(
            reason=reason,
            source_reference=source_reference,
            memories=memories,
            user_facts=user_facts,
            identity_core=identity_core,
            established_preferences=established,
            provisional_preferences=provisional,
        )

    @staticmethod
    def _valid_pair(key, value) -> bool:
        return (
            isinstance(key, str)
            and isinstance(value, str)
            and bool(key)
            and len(key) <= THOUGHT_VALUE_LIMIT
            and len(value) <= THOUGHT_VALUE_LIMIT
        )
