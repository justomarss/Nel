from dataclasses import replace

from src.goals.models import (
    GoalCandidate,
    GoalOwner,
    GoalSnapshot,
    GoalSourceKind,
    GoalState,
    ProgressVerification,
)


ACCEPTED_SOURCE_KINDS = frozenset(kind.value for kind in GoalSourceKind)
ALLOWED_TRANSITIONS = {
    GoalState.ACTIVE: {
        GoalState.PAUSED,
        GoalState.COMPLETED,
        GoalState.CANCELLED,
    },
    GoalState.PAUSED: {
        GoalState.ACTIVE,
        GoalState.COMPLETED,
        GoalState.CANCELLED,
    },
    GoalState.COMPLETED: set(),
    GoalState.CANCELLED: set(),
}
PROGRESS_TRANSITIONS = {
    ProgressVerification.UNKNOWN: {
        ProgressVerification.UNKNOWN,
        ProgressVerification.USER_REPORTED,
        ProgressVerification.VERIFIED,
    },
    ProgressVerification.USER_REPORTED: {
        ProgressVerification.USER_REPORTED,
        ProgressVerification.VERIFIED,
    },
    ProgressVerification.VERIFIED: {ProgressVerification.VERIFIED},
}


class GoalPolicyError(ValueError):
    pass


class GoalPolicy:
    def authorize_creation(
        self,
        candidate: GoalCandidate,
        *,
        explicit_user_approval: bool = False,
        approval_reference: str | None = None,
        controlled_experiment: bool = False,
    ) -> GoalCandidate:
        if not isinstance(candidate, GoalCandidate):
            raise GoalPolicyError("A valid goal candidate is required.")
        self._require_approval(
            candidate.source_kind,
            explicit_user_approval,
            approval_reference,
            owner=candidate.owner,
            controlled_experiment=controlled_experiment,
        )
        if candidate.source_reference is None:
            raise GoalPolicyError("Validated source reference is required.")

        if (
            candidate.source_kind == GoalSourceKind.APPROVED_SYSTEM.value
            and (
                candidate.owner is not GoalOwner.NEL
                or candidate.outcome_primarily_user
            )
        ):
            raise GoalPolicyError(
                "Approved-system goals must be explicitly authorized and Nel-owned."
            )

        if candidate.outcome_primarily_user and candidate.owner is not GoalOwner.USER:
            return replace(candidate, owner=GoalOwner.USER)
        return candidate

    def validate_transition(
        self,
        current: GoalSnapshot,
        target_state: GoalState,
        *,
        source_kind: str,
        explicit_user_approval: bool = False,
        approval_reference: str | None = None,
        success_condition_accepted: bool = False,
        controlled_experiment: bool = False,
    ) -> None:
        if not isinstance(current, GoalSnapshot):
            raise GoalPolicyError("A current goal snapshot is required.")
        if not isinstance(target_state, GoalState):
            raise GoalPolicyError("Target goal state is invalid.")
        self._require_nonterminal(current)
        self._require_approval(
            source_kind,
            explicit_user_approval,
            approval_reference,
            owner=current.owner,
            controlled_experiment=controlled_experiment,
        )
        if target_state not in ALLOWED_TRANSITIONS[current.state]:
            raise GoalPolicyError("Goal state transition is not allowed.")
        if (
            target_state is GoalState.COMPLETED
            and not success_condition_accepted
        ):
            raise GoalPolicyError(
                "Completion requires explicit success-condition acceptance."
            )

    def validate_progress(
        self,
        current: GoalSnapshot,
        verification: ProgressVerification,
        *,
        summary: str | None = None,
        percent: int | None = None,
        source_kind: str,
        explicit_user_approval: bool = False,
        approval_reference: str | None = None,
        owner_confirmation: bool = False,
        deterministic_evidence: bool = False,
        controlled_experiment: bool = False,
    ) -> None:
        if not isinstance(current, GoalSnapshot):
            raise GoalPolicyError("A current goal snapshot is required.")
        if not isinstance(verification, ProgressVerification):
            raise GoalPolicyError("Progress verification state is invalid.")
        self._require_nonterminal(current)
        self._require_approval(
            source_kind,
            explicit_user_approval,
            approval_reference,
            owner=current.owner,
            controlled_experiment=controlled_experiment,
        )
        if verification not in PROGRESS_TRANSITIONS[current.progress_verification]:
            raise GoalPolicyError("Progress verification cannot be downgraded.")
        if verification is ProgressVerification.UNKNOWN:
            if summary is not None or percent is not None:
                raise GoalPolicyError(
                    "Unknown progress is not zero and cannot contain evidence."
                )
            return
        if not isinstance(summary, str) or not summary.strip():
            raise GoalPolicyError("Accepted progress requires a summary.")
        if percent is not None and (
            isinstance(percent, bool)
            or not isinstance(percent, int)
            or not 0 <= percent <= 100
        ):
            raise GoalPolicyError("Progress percent must be from 0 to 100.")
        if verification is ProgressVerification.USER_REPORTED:
            if not owner_confirmation:
                raise GoalPolicyError(
                    "User-reported progress requires an explicit user report."
                )
            return
        if not owner_confirmation and not deterministic_evidence:
            raise GoalPolicyError(
                "Verified progress requires owner confirmation or deterministic evidence."
            )

    def validate_update(
        self,
        current: GoalSnapshot,
        proposed: GoalSnapshot,
        *,
        source_kind: str,
        explicit_user_approval: bool,
        approval_reference: str,
        revision_reason: str,
        expected_version: int,
        success_condition_accepted: bool = False,
        owner_confirmation: bool = False,
        deterministic_evidence: bool = False,
        controlled_experiment: bool = False,
    ) -> None:
        if not isinstance(current, GoalSnapshot) or not isinstance(
            proposed,
            GoalSnapshot,
        ):
            raise GoalPolicyError("Current and proposed goal snapshots are required.")
        self._require_nonterminal(current)
        self._validate_revision_metadata(
            current,
            proposed,
            expected_version=expected_version,
            revision_reason=revision_reason,
        )
        self._require_approval(
            source_kind,
            explicit_user_approval,
            approval_reference,
            owner=proposed.owner,
            controlled_experiment=controlled_experiment,
        )
        if proposed.source_kind.value != source_kind:
            raise GoalPolicyError("Proposed goal source does not match validation.")
        if proposed.approval_reference != approval_reference:
            raise GoalPolicyError("Proposed goal approval does not match validation.")

        if proposed.state is not current.state:
            if proposed.state not in ALLOWED_TRANSITIONS[current.state]:
                raise GoalPolicyError("Goal state transition is not allowed.")
            if (
                proposed.state is GoalState.COMPLETED
                and not success_condition_accepted
            ):
                raise GoalPolicyError(
                    "Completion requires explicit success-condition acceptance."
                )

        progress_changed = (
            proposed.progress_verification != current.progress_verification
            or proposed.progress_summary != current.progress_summary
            or proposed.progress_percent != current.progress_percent
        )
        if progress_changed:
            if (
                proposed.progress_verification
                not in PROGRESS_TRANSITIONS[current.progress_verification]
            ):
                raise GoalPolicyError(
                    "Progress verification cannot be downgraded."
                )
            if (
                proposed.progress_verification
                is ProgressVerification.USER_REPORTED
                and not owner_confirmation
            ):
                raise GoalPolicyError(
                    "User-reported progress requires an explicit user report."
                )
            if (
                proposed.progress_verification is ProgressVerification.VERIFIED
                and not owner_confirmation
                and not deterministic_evidence
            ):
                raise GoalPolicyError(
                    "Verified progress requires owner confirmation or deterministic evidence."
                )

    def validate_reopen(
        self,
        current: GoalSnapshot,
        *,
        source_kind: str,
        approval_reference: str,
        revision_reason: str,
        expected_version: int,
        explicit_user_approval: bool = False,
    ) -> None:
        self._validate_terminal_activation(
            current,
            required_state=GoalState.COMPLETED,
            operation="reopen",
            source_kind=source_kind,
            approval_reference=approval_reference,
            revision_reason=revision_reason,
            expected_version=expected_version,
            explicit_user_approval=explicit_user_approval,
        )

    def validate_restore(
        self,
        current: GoalSnapshot,
        *,
        source_kind: str,
        approval_reference: str,
        revision_reason: str,
        expected_version: int,
        explicit_user_approval: bool = False,
    ) -> None:
        self._validate_terminal_activation(
            current,
            required_state=GoalState.CANCELLED,
            operation="restore",
            source_kind=source_kind,
            approval_reference=approval_reference,
            revision_reason=revision_reason,
            expected_version=expected_version,
            explicit_user_approval=explicit_user_approval,
        )

    def _validate_terminal_activation(
        self,
        current: GoalSnapshot,
        *,
        required_state: GoalState,
        operation: str,
        source_kind: str,
        approval_reference: str,
        revision_reason: str,
        expected_version: int,
        explicit_user_approval: bool,
    ) -> None:
        if not isinstance(current, GoalSnapshot):
            raise GoalPolicyError("A current goal snapshot is required.")
        if current.state is not required_state:
            raise GoalPolicyError(f"Goal is not eligible for {operation}.")
        if source_kind != GoalSourceKind.VALIDATED_USER.value:
            raise GoalPolicyError(
                f"Goal {operation} requires a validated-user source."
            )
        self._require_approval(
            source_kind,
            explicit_user_approval,
            approval_reference,
            owner=current.owner,
        )
        if not isinstance(revision_reason, str) or not revision_reason.strip():
            raise GoalPolicyError(
                f"Goal {operation} requires a revision reason."
            )
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
            or expected_version != current.version
        ):
            raise GoalPolicyError("Expected goal version does not match.")

    @staticmethod
    def _validate_revision_metadata(
        current: GoalSnapshot,
        proposed: GoalSnapshot,
        *,
        expected_version: int,
        revision_reason: str,
    ) -> None:
        if proposed.goal_id != current.goal_id:
            raise GoalPolicyError("Goal ID cannot change.")
        if proposed.created_at != current.created_at:
            raise GoalPolicyError("Goal creation timestamp cannot change.")
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version != current.version
        ):
            raise GoalPolicyError("Expected goal version does not match.")
        if proposed.version != current.version + 1:
            raise GoalPolicyError("Proposed goal version is invalid.")
        if not isinstance(revision_reason, str) or not revision_reason.strip():
            raise GoalPolicyError("Goal update requires a revision reason.")
        if proposed.revision_reason != revision_reason:
            raise GoalPolicyError("Proposed revision reason does not match.")

    @staticmethod
    def _require_nonterminal(current: GoalSnapshot) -> None:
        if current.state in {GoalState.COMPLETED, GoalState.CANCELLED}:
            raise GoalPolicyError(
                "Ordinary updates cannot modify terminal goals."
            )

    @staticmethod
    def _require_approval(
        source_kind: str,
        explicit_user_approval: bool,
        approval_reference: str | None,
        *,
        owner: GoalOwner,
        controlled_experiment: bool = False,
    ) -> None:
        if source_kind not in ACCEPTED_SOURCE_KINDS:
            raise GoalPolicyError("Goal write source is not authorized.")
        if explicit_user_approval is not True:
            raise GoalPolicyError("Explicit validated user approval is required.")
        if not isinstance(approval_reference, str) or not approval_reference.strip():
            raise GoalPolicyError("Approval reference is required.")
        if (
            source_kind == GoalSourceKind.APPROVED_SYSTEM.value
            and owner is not GoalOwner.NEL
        ):
            raise GoalPolicyError("Approved-system goals must be Nel-owned.")
        if (
            source_kind == GoalSourceKind.APPROVED_EXPERIMENT.value
            and controlled_experiment is not True
        ):
            raise GoalPolicyError(
                "Approved-experiment goals require controlled test context."
            )
