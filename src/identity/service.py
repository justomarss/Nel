import sqlite3

from src.errors import PersistenceOperationError
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
        try:
            return self._repository.snapshot()
        except (OSError, sqlite3.Error):
            raise PersistenceOperationError() from None

    def context_snapshot(self, limit=1000) -> IdentitySnapshot:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError(
                "Identity preference context limit must be a non-negative integer."
            )
        snapshot = self.snapshot()
        preferences = tuple(
            sorted(
                (
                    record
                    for record in snapshot.preferences
                    if record.preference_state in {"established", "provisional"}
                ),
                key=lambda record: (record.preference_state, record.key),
            )[:limit]
        )
        return IdentitySnapshot(
            identity_id=snapshot.identity_id,
            display_name=snapshot.display_name,
            nature=snapshot.nature,
            role=snapshot.role,
            preferences=preferences,
        )

    def get_preference(self, key: str):
        normalized = self._validate_key(key)
        try:
            return self._repository.get_preference(normalized)
        except (OSError, sqlite3.Error):
            raise PersistenceOperationError() from None

    def preference_history(self, key: str):
        normalized = self._validate_key(key)
        try:
            return self._repository.history(normalized)
        except (OSError, sqlite3.Error):
            raise PersistenceOperationError() from None

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
