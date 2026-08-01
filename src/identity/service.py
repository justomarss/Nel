from src.identity.models import PREFERENCE_STATES, IdentitySnapshot
from src.identity.repository import CORE_KEYS, IdentityRepository
from src.persistence.normalization import normalize_fact_key


ALLOWED_CANDIDATE_SOURCES = {"manual", "experiment"}
PREFERENCE_TRANSITIONS = {
    "candidate": {"provisional", "retired"},
    "provisional": {"established", "retired"},
    "established": {"retired"},
    "retired": set(),
}


class IdentityService:
    def __init__(self, repository: IdentityRepository):
        self._repository = repository

    def snapshot(self) -> IdentitySnapshot:
        return self._repository.snapshot()

    def get_preference(self, key: str):
        normalized = self._validate_key(key)
        return self._repository.get_preference(normalized)

    def preference_history(self, key: str):
        normalized = self._validate_key(key)
        return self._repository.history(normalized)

    def create_preference_candidate(
        self,
        key: str,
        value: str,
        *,
        source_kind: str,
        source_reference: str,
    ):
        normalized = self._validate_key(key)
        self._validate_value(value)
        self._validate_source(source_kind, source_reference)
        return self._repository._create_candidate(
            normalized,
            value,
            source_kind,
            source_reference,
        )

    def transition_preference(
        self,
        key: str,
        target_state: str,
        *,
        source_kind: str,
        source_reference: str,
    ):
        normalized = self._validate_key(key)
        if target_state not in PREFERENCE_STATES:
            raise ValueError("Unsupported preference state.")
        self._validate_source(source_kind, source_reference)
        current = self._repository.get_preference(normalized)
        if current is None:
            raise ValueError("Preference does not exist.")
        if target_state not in PREFERENCE_TRANSITIONS[current.preference_state]:
            raise ValueError("Invalid preference-state transition.")
        return self._repository._transition(
            normalized,
            current.preference_state,
            target_state,
            source_kind,
            source_reference,
        )

    @staticmethod
    def _validate_key(key: str) -> str:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Preference key must be a non-empty string.")
        normalized = normalize_fact_key(key)
        if not normalized or normalized in CORE_KEYS:
            raise ValueError("Preference key is reserved or invalid.")
        return normalized

    @staticmethod
    def _validate_value(value: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("Preference value must be a non-empty string.")

    @staticmethod
    def _validate_source(source_kind: str, source_reference: str) -> None:
        if source_kind not in ALLOWED_CANDIDATE_SOURCES:
            raise ValueError("Identity source is not authorized.")
        if not isinstance(source_reference, str) or not source_reference.strip():
            raise ValueError("Identity source reference is required.")
