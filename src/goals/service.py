from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from src.goals.models import (
    GoalCandidate,
    GoalSnapshot,
    GoalSourceKind,
    GoalState,
)
from src.goals.policy import GoalPolicy, GoalPolicyError
from src.goals.repository import GoalNotFoundError, GoalRepository


_UPDATABLE_FIELDS = {
    "title",
    "description",
    "success_condition",
    "owner",
    "state",
    "priority",
    "deadline",
    "progress_summary",
    "progress_percent",
    "progress_verification",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class GoalService:
    def __init__(
        self,
        repository: GoalRepository,
        policy: GoalPolicy | None = None,
        *,
        clock=_utc_now,
        id_factory=lambda: uuid4().hex,
    ):
        self._repository = repository
        self._policy = policy or GoalPolicy()
        self._clock = clock
        self._id_factory = id_factory

    def get(self, goal_id: str) -> GoalSnapshot | None:
        return self._repository.get(goal_id)

    def list_current(self) -> tuple[GoalSnapshot, ...]:
        return self._repository.list_current()

    def history(self, goal_id: str):
        return self._repository.history(goal_id)

    def create(
        self,
        candidate: GoalCandidate,
        *,
        explicit_user_approval: bool,
        approval_reference: str,
        controlled_experiment: bool = False,
    ) -> GoalSnapshot:
        approved = self._policy.authorize_creation(
            candidate,
            explicit_user_approval=explicit_user_approval,
            approval_reference=approval_reference,
            controlled_experiment=controlled_experiment,
        )
        source_kind = self._source_kind(approved.source_kind)
        now = self._clock()
        snapshot = GoalSnapshot(
            goal_id=self._id_factory(),
            title=approved.title,
            description=approved.description,
            success_condition=approved.success_condition,
            owner=approved.owner,
            state=GoalState.ACTIVE,
            priority=approved.priority,
            deadline=approved.deadline,
            source_kind=source_kind,
            source_reference=approved.source_reference,
            approval_reference=approval_reference,
            created_at=now,
            updated_at=now,
        )
        return self._repository._create(snapshot)

    def update(
        self,
        goal_id: str,
        changes: Mapping,
        *,
        expected_version: int,
        source_kind: str,
        source_reference: str,
        explicit_user_approval: bool,
        approval_reference: str,
        revision_reason: str,
        success_condition_accepted: bool = False,
        owner_confirmation: bool = False,
        deterministic_evidence: bool = False,
        controlled_experiment: bool = False,
    ) -> GoalSnapshot:
        if not isinstance(changes, Mapping) or not changes:
            raise ValueError("Goal update requires changed fields.")
        unsupported = set(changes) - _UPDATABLE_FIELDS
        if unsupported:
            raise ValueError("Goal update contains unsupported fields.")
        current = self._require(goal_id)
        accepted_source = self._source_kind(source_kind)
        proposed = replace(
            current,
            **dict(changes),
            source_kind=accepted_source,
            source_reference=source_reference,
            approval_reference=approval_reference,
            revision_reason=revision_reason,
            version=current.version + 1,
            updated_at=self._clock(),
        )
        self._policy.validate_update(
            current,
            proposed,
            source_kind=source_kind,
            explicit_user_approval=explicit_user_approval,
            approval_reference=approval_reference,
            revision_reason=revision_reason,
            expected_version=expected_version,
            success_condition_accepted=success_condition_accepted,
            owner_confirmation=owner_confirmation,
            deterministic_evidence=deterministic_evidence,
            controlled_experiment=controlled_experiment,
        )
        return self._repository._update(
            proposed,
            expected_version=expected_version,
        )

    def reopen(
        self,
        goal_id: str,
        *,
        expected_version: int,
        source_reference: str,
        explicit_user_approval: bool,
        approval_reference: str,
        revision_reason: str,
    ) -> GoalSnapshot:
        return self._activate_terminal(
            goal_id,
            operation="reopen",
            expected_version=expected_version,
            source_reference=source_reference,
            explicit_user_approval=explicit_user_approval,
            approval_reference=approval_reference,
            revision_reason=revision_reason,
        )

    def restore(
        self,
        goal_id: str,
        *,
        expected_version: int,
        source_reference: str,
        explicit_user_approval: bool,
        approval_reference: str,
        revision_reason: str,
    ) -> GoalSnapshot:
        return self._activate_terminal(
            goal_id,
            operation="restore",
            expected_version=expected_version,
            source_reference=source_reference,
            explicit_user_approval=explicit_user_approval,
            approval_reference=approval_reference,
            revision_reason=revision_reason,
        )

    def _activate_terminal(
        self,
        goal_id: str,
        *,
        operation: str,
        expected_version: int,
        source_reference: str,
        explicit_user_approval: bool,
        approval_reference: str,
        revision_reason: str,
    ) -> GoalSnapshot:
        current = self._require(goal_id)
        validator = (
            self._policy.validate_reopen
            if operation == "reopen"
            else self._policy.validate_restore
        )
        validator(
            current,
            source_kind=GoalSourceKind.VALIDATED_USER.value,
            explicit_user_approval=explicit_user_approval,
            approval_reference=approval_reference,
            revision_reason=revision_reason,
            expected_version=expected_version,
        )
        proposed = replace(
            current,
            state=GoalState.ACTIVE,
            source_kind=GoalSourceKind.VALIDATED_USER,
            source_reference=source_reference,
            approval_reference=approval_reference,
            revision_reason=revision_reason,
            version=current.version + 1,
            updated_at=self._clock(),
        )
        writer = (
            self._repository._reopen
            if operation == "reopen"
            else self._repository._restore
        )
        return writer(proposed, expected_version=expected_version)

    def _require(self, goal_id: str) -> GoalSnapshot:
        snapshot = self._repository.get(goal_id)
        if snapshot is None:
            raise GoalNotFoundError("Goal does not exist.")
        return snapshot

    @staticmethod
    def _source_kind(value: str) -> GoalSourceKind:
        try:
            return GoalSourceKind(value)
        except (TypeError, ValueError):
            raise GoalPolicyError("Goal write source is not authorized.") from None
