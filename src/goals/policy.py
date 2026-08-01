from dataclasses import replace

from src.goals.models import (
    GoalCandidate,
    GoalOwner,
    GoalSnapshot,
    GoalState,
    ProgressVerification,
)


VALIDATED_USER_SOURCE = "validated_user"
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
    ) -> GoalCandidate:
        if not isinstance(candidate, GoalCandidate):
            raise GoalPolicyError("A valid goal candidate is required.")
        self._require_approval(
            candidate.source_kind,
            explicit_user_approval,
            approval_reference,
        )
        if candidate.source_reference is None:
            raise GoalPolicyError("Validated source reference is required.")

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
    ) -> None:
        if not isinstance(current, GoalSnapshot):
            raise GoalPolicyError("A current goal snapshot is required.")
        if not isinstance(target_state, GoalState):
            raise GoalPolicyError("Target goal state is invalid.")
        self._require_approval(
            source_kind,
            explicit_user_approval,
            approval_reference,
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
    ) -> None:
        if not isinstance(current, GoalSnapshot):
            raise GoalPolicyError("A current goal snapshot is required.")
        if not isinstance(verification, ProgressVerification):
            raise GoalPolicyError("Progress verification state is invalid.")
        self._require_approval(
            source_kind,
            explicit_user_approval,
            approval_reference,
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

    @staticmethod
    def _require_approval(
        source_kind: str,
        explicit_user_approval: bool,
        approval_reference: str | None,
    ) -> None:
        if source_kind != VALIDATED_USER_SOURCE:
            raise GoalPolicyError("Goal write source is not authorized.")
        if explicit_user_approval is not True:
            raise GoalPolicyError("Explicit validated user approval is required.")
        if not isinstance(approval_reference, str) or not approval_reference.strip():
            raise GoalPolicyError("Approval reference is required.")
