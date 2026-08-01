from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class GoalOwner(str, Enum):
    USER = "user"
    NEL = "nel"
    SHARED = "shared"


class GoalState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProgressVerification(str, Enum):
    UNKNOWN = "unknown"
    USER_REPORTED = "user_reported"
    VERIFIED = "verified"


class GoalPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


def _require_text(value, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


def _validate_optional_text(value, field_name: str) -> None:
    if value is not None:
        _require_text(value, field_name)


def _validate_timestamp(value: str, field_name: str) -> None:
    _require_text(value, field_name)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp.") from None


def _validate_enum(value, enum_type, field_name: str) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"{field_name} is invalid.")


def _validate_progress(
    verification: ProgressVerification,
    summary: str | None,
    percent: int | None,
) -> None:
    _validate_enum(
        verification,
        ProgressVerification,
        "progress_verification",
    )
    if verification is ProgressVerification.UNKNOWN:
        if summary is not None or percent is not None:
            raise ValueError(
                "Unknown progress cannot contain accepted progress evidence."
            )
        return
    _require_text(summary, "progress_summary")
    if percent is not None and (
        isinstance(percent, bool)
        or not isinstance(percent, int)
        or not 0 <= percent <= 100
    ):
        raise ValueError("progress_percent must be an integer from 0 to 100.")


@dataclass(frozen=True)
class GoalCandidate:
    title: str
    success_condition: str
    owner: GoalOwner = GoalOwner.USER
    description: str | None = None
    priority: GoalPriority = GoalPriority.NORMAL
    deadline: str | None = None
    source_kind: str = "unvalidated"
    source_reference: str | None = None
    outcome_primarily_user: bool = True

    def __post_init__(self):
        _require_text(self.title, "title")
        _require_text(self.success_condition, "success_condition")
        _validate_enum(self.owner, GoalOwner, "owner")
        _validate_enum(self.priority, GoalPriority, "priority")
        _validate_optional_text(self.description, "description")
        _validate_optional_text(self.source_reference, "source_reference")
        _require_text(self.source_kind, "source_kind")
        if not isinstance(self.outcome_primarily_user, bool):
            raise ValueError("outcome_primarily_user must be a boolean.")
        if self.deadline is not None:
            _validate_timestamp(self.deadline, "deadline")


@dataclass(frozen=True)
class GoalSnapshot:
    goal_id: str
    title: str
    success_condition: str
    owner: GoalOwner
    approval_reference: str
    created_at: str
    updated_at: str
    state: GoalState = GoalState.ACTIVE
    priority: GoalPriority = GoalPriority.NORMAL
    description: str | None = None
    deadline: str | None = None
    progress_verification: ProgressVerification = ProgressVerification.UNKNOWN
    progress_summary: str | None = None
    progress_percent: int | None = None
    version: int = 1

    def __post_init__(self):
        _require_text(self.goal_id, "goal_id")
        _require_text(self.title, "title")
        _require_text(self.success_condition, "success_condition")
        _require_text(self.approval_reference, "approval_reference")
        _validate_enum(self.owner, GoalOwner, "owner")
        _validate_enum(self.state, GoalState, "state")
        _validate_enum(self.priority, GoalPriority, "priority")
        _validate_optional_text(self.description, "description")
        _validate_timestamp(self.created_at, "created_at")
        _validate_timestamp(self.updated_at, "updated_at")
        if self.deadline is not None:
            _validate_timestamp(self.deadline, "deadline")
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise ValueError("version must be a positive integer.")
        if self.version < 1:
            raise ValueError("version must be a positive integer.")
        _validate_progress(
            self.progress_verification,
            self.progress_summary,
            self.progress_percent,
        )


@dataclass(frozen=True)
class GoalRevision:
    snapshot: GoalSnapshot
    superseded_at: str
    revision_reason: str

    def __post_init__(self):
        if not isinstance(self.snapshot, GoalSnapshot):
            raise ValueError("snapshot must be a GoalSnapshot.")
        _validate_timestamp(self.superseded_at, "superseded_at")
        _require_text(self.revision_reason, "revision_reason")
