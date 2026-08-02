from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    total_context_characters: int = 12000
    user_message_characters: int = 4096
    system_instruction_characters: int = 8192
    active_fact_limit: int = 20
    active_or_paused_goal_limit: int = 10
    terminal_goal_limit: int = 5
    established_preference_limit: int = 10
    provisional_preference_limit: int = 10
    memory_limit: int = 10
    individual_memory_character_limit: int = 2000

    def __post_init__(self):
        for field_name, value in self.__dict__.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer.")


@dataclass(frozen=True)
class FactContextSnapshot:
    key: str
    value: str


@dataclass(frozen=True)
class MemoryContextSnapshot:
    event_id: int
    stored_at: str | None
    text: str


@dataclass(frozen=True)
class PreferenceContextRecord:
    key: str
    value: str
    state: str


@dataclass(frozen=True)
class IdentityContext:
    identity_id: str
    display_name: str
    nature: str
    role: str
    derived_display: tuple[tuple[str, str], ...]
    established_preferences: tuple[PreferenceContextRecord, ...]
    provisional_preferences: tuple[PreferenceContextRecord, ...]


@dataclass(frozen=True)
class UserFactContextRecord:
    key: str
    readable_key: str
    value: str


@dataclass(frozen=True)
class GoalContextRecord:
    goal_id: str
    owner: str
    state: str
    priority: str
    title: str
    success_condition: str
    deadline: str | None
    progress_summary: str | None
    progress_percent: int | None
    progress_verification: str
    updated_at: str


@dataclass(frozen=True)
class MemoryContextRecord:
    event_id: int
    stored_at: str | None
    text: str


@dataclass(frozen=True)
class TruncationMetadata:
    included_counts: tuple[tuple[str, int], ...]
    omitted_counts: tuple[tuple[str, int], ...]
    omission_reason_codes: tuple[str, ...]
    section_sizes: tuple[tuple[str, int], ...]
    configured_budget: int
    truncation: bool


@dataclass(frozen=True)
class ContextBundle:
    identity: IdentityContext
    user_facts: tuple[UserFactContextRecord, ...]
    goals: tuple[GoalContextRecord, ...]
    memories: tuple[MemoryContextRecord, ...]
    truncation_metadata: TruncationMetadata


@dataclass(frozen=True)
class ContextAssemblyResult:
    bundle: ContextBundle
    canonical_json: str
    serialized_characters: int
    context_digest: str
