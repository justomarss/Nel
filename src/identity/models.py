from dataclasses import dataclass


PREFERENCE_STATES = {
    "candidate",
    "provisional",
    "established",
    "retired",
}


@dataclass(frozen=True)
class IdentityRecord:
    key: str
    value: str
    record_type: str
    preference_state: str | None
    immutable: bool
    source_kind: str
    source_reference: str
    version: int
    updated_at: str
    superseded_at: str | None = None


@dataclass(frozen=True)
class IdentitySnapshot:
    identity_id: str
    display_name: str
    nature: str
    role: str
    preferences: tuple[IdentityRecord, ...]
