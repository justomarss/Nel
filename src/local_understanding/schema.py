from dataclasses import dataclass

from .labels import TRAINED_LABELS


REQUIRED_FIELDS = frozenset({
    "id", "text", "intent_label", "source_family", "semantic_pattern",
    "register", "language_mix", "difficulty", "contextual",
    "previous_user", "previous_assistant", "hard_negative_group",
    "correction_signal", "generation_method", "review_status",
})


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    record_id: str
    message: str


def validate_record(record):
    issues = []
    record_id = str(record.get("id", ""))
    missing = REQUIRED_FIELDS.difference(record)
    if missing:
        issues.append(ValidationIssue("missing_fields", record_id, ",".join(sorted(missing))))
    if record.get("intent_label") not in TRAINED_LABELS:
        issues.append(ValidationIssue("invalid_label", record_id, str(record.get("intent_label"))))
    if not isinstance(record.get("text"), str) or not record.get("text", "").strip():
        issues.append(ValidationIssue("invalid_text", record_id, "text must be non-empty"))
    if record.get("contextual") and not (record.get("previous_user") or record.get("previous_assistant")):
        issues.append(ValidationIssue("missing_context", record_id, "contextual row has no previous turn"))
    return tuple(issues)
