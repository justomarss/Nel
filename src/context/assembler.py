import hashlib
import json
from collections import Counter
from datetime import datetime

from src.brain.local_intent_classifier import LocalIntentClassifier
from src.context.models import (
    ContextAssemblyResult,
    ContextBudget,
    ContextBundle,
    GoalContextRecord,
    IdentityContext,
    MemoryContextRecord,
    PreferenceContextRecord,
    TruncationMetadata,
    UserFactContextRecord,
)
from src.context.relevance import is_relevant, relevance_tuple
from src.errors import ContextAssemblyError
from src.goals.models import GoalPriority, GoalState
from src.memory.normalization import memory_fingerprint


SOURCE_SNAPSHOT_LIMIT = 1000
IDENTITY_DISPLAY_RENDERINGS = {
    "nature": {"artificial": "süni"},
    "role": {
        "Ömər’s persistent digital companion": "Ömərin davamlı rəqəmsal yoldaşı",
    },
}
_GOAL_STATE_ORDER = {GoalState.ACTIVE: 0, GoalState.PAUSED: 1}
_GOAL_PRIORITY_ORDER = {
    GoalPriority.HIGH: 0,
    GoalPriority.NORMAL: 1,
    GoalPriority.LOW: 2,
}
_TRUNCATION_REASONS = {"budget_exceeded", "record_oversized", "source_limit"}


def canonical_json(payload) -> str:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise ContextAssemblyError("context_serialization_failed") from None


def render_identity_value(field: str, value: str) -> str:
    return IDENTITY_DISPLAY_RENDERINGS.get(field, {}).get(value, value)


def _timestamp(value: str | None) -> float:
    if not value:
        return float("-inf")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return float("-inf")


class ContextAssembler:
    def __init__(
        self,
        *,
        identity_service,
        knowledge_service,
        goal_service,
        memory_service,
        budget: ContextBudget | None = None,
        local_intent_classifier=None,
    ):
        self.identity_service = identity_service
        self.knowledge_service = knowledge_service
        self.goal_service = goal_service
        self.memory_service = memory_service
        self.budget = budget or ContextBudget()
        self.local_intent = local_intent_classifier or LocalIntentClassifier()

    def assemble(self, user_message: str) -> ContextAssemblyResult:
        if not isinstance(user_message, str):
            raise ContextAssemblyError("invalid_user_message")
        if len(user_message) > self.budget.user_message_characters:
            raise ContextAssemblyError("user_message_oversized")

        identity_snapshot = self._identity_snapshot()
        core = self._identity_core(identity_snapshot)
        omitted = Counter()
        reasons = set()

        established, provisional = self._preference_candidates(
            user_message,
            identity_snapshot,
            omitted,
            reasons,
        )
        facts = self._fact_candidates(user_message, omitted, reasons)
        active_goals, terminal_goals = self._goal_candidates(
            user_message,
            omitted,
            reasons,
        )
        memories = self._memory_candidates(user_message, omitted, reasons)

        selected = {
            "facts": [],
            "active_goals": [],
            "established": [],
            "memories": [],
            "provisional": [],
            "terminal_goals": [],
        }
        accepted_order = []
        candidates = (
            [("facts", record) for record in facts]
            + [("active_goals", record) for record in active_goals]
            + [("established", record) for record in established]
            + [("memories", record) for record in memories]
            + [("provisional", record) for record in provisional]
            + [("terminal_goals", record) for record in terminal_goals]
        )

        baseline = self._finalize(core, selected, omitted, reasons)
        if len(baseline[1]) > self.budget.total_context_characters:
            raise ContextAssemblyError("mandatory_identity_oversized")

        for category, record in candidates:
            selected[category].append(record)
            _bundle, encoded = self._finalize(core, selected, omitted, reasons)
            if len(encoded) <= self.budget.total_context_characters:
                accepted_order.append(category)
                continue
            selected[category].pop()
            omitted[category] += 1
            reasons.add("budget_exceeded")

        bundle, encoded = self._finalize(core, selected, omitted, reasons)
        while len(encoded) > self.budget.total_context_characters and accepted_order:
            category = accepted_order.pop()
            selected[category].pop()
            omitted[category] += 1
            reasons.add("budget_exceeded")
            bundle, encoded = self._finalize(core, selected, omitted, reasons)
        if len(encoded) > self.budget.total_context_characters:
            raise ContextAssemblyError("mandatory_identity_oversized")

        return ContextAssemblyResult(
            bundle=bundle,
            canonical_json=encoded,
            serialized_characters=len(encoded),
            context_digest=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        )

    def _identity_snapshot(self):
        if self.identity_service is None:
            raise ContextAssemblyError("identity_context_unavailable")
        try:
            reader = getattr(self.identity_service, "context_snapshot", None)
            if callable(reader):
                snapshot = reader(limit=SOURCE_SNAPSHOT_LIMIT)
            else:
                reader = getattr(self.identity_service, "snapshot", None)
                snapshot = reader()
            required = ("identity_id", "display_name", "nature", "role", "preferences")
            if reader is None or any(not hasattr(snapshot, field) for field in required):
                raise ValueError
            return snapshot
        except ContextAssemblyError:
            raise
        except Exception:
            raise ContextAssemblyError("identity_context_unavailable") from None

    @staticmethod
    def _identity_core(snapshot) -> dict:
        values = {
            "identity_id": snapshot.identity_id,
            "display_name": snapshot.display_name,
            "nature": snapshot.nature,
            "role": snapshot.role,
        }
        if any(not isinstance(value, str) or not value for value in values.values()):
            raise ContextAssemblyError("identity_context_unavailable")
        values["derived_display"] = {
            "nature": render_identity_value("nature", snapshot.nature),
            "role": render_identity_value("role", snapshot.role),
        }
        return values

    def _preference_candidates(self, message, snapshot, omitted, reasons):
        broad = self.local_intent.is_broad_identity_query(message)
        groups = {"established": [], "provisional": []}
        try:
            records = tuple(snapshot.preferences)
        except Exception:
            omitted["identity_preferences"] += 1
            reasons.add("identity_preferences_omitted")
            return (), ()
        for record in records:
            state = getattr(record, "preference_state", None)
            if state not in groups:
                continue
            key = getattr(record, "key", None)
            value = getattr(record, "value", None)
            if not isinstance(key, str) or not isinstance(value, str):
                omitted[f"{state}_preferences"] += 1
                reasons.add("invalid_snapshot_record")
                continue
            score = relevance_tuple(message, value, key.replace("_", " "))
            if not is_relevant(score) and not broad:
                omitted[f"{state}_preferences"] += 1
                reasons.add("not_relevant")
                continue
            groups[state].append((score, key, {"key": key, "state": state, "value": value}))

        result = []
        for state, limit in (
            ("established", self.budget.established_preference_limit),
            ("provisional", self.budget.provisional_preference_limit),
        ):
            ordered = sorted(groups[state], key=lambda item: self._score_key(item[0], item[1]))
            if len(ordered) > limit:
                omitted[f"{state}_preferences"] += len(ordered) - limit
                reasons.add("source_limit")
            result.append(tuple(item[2] for item in ordered[:limit]))
        return tuple(result)

    def _fact_candidates(self, message, omitted, reasons):
        broad = self.local_intent.is_broad_user_profile_query(message)
        try:
            reader = getattr(self.knowledge_service, "context_snapshot", None)
            if callable(reader):
                snapshots = reader(limit=SOURCE_SNAPSHOT_LIMIT)
            else:
                snapshots = tuple(
                    type("Fact", (), {"key": key, "value": value})()
                    for key, value in self.knowledge_service.facts().items()
                )
        except Exception:
            omitted["facts"] += 1
            reasons.add("fact_context_omitted")
            return ()

        candidates = []
        for fact in snapshots:
            key = getattr(fact, "key", None)
            value = getattr(fact, "value", None)
            if not isinstance(key, str) or not isinstance(value, str):
                omitted["facts"] += 1
                reasons.add("invalid_snapshot_record")
                continue
            readable = key.replace("_", " ")
            score = relevance_tuple(message, value, readable)
            if not is_relevant(score) and not broad:
                omitted["facts"] += 1
                reasons.add("not_relevant")
                continue
            candidates.append((score, key, {"key": key, "readable_key": readable, "value": value}))
        candidates.sort(key=lambda item: self._score_key(item[0], item[1]))
        if len(candidates) > self.budget.active_fact_limit:
            omitted["facts"] += len(candidates) - self.budget.active_fact_limit
            reasons.add("source_limit")
        return tuple(item[2] for item in candidates[: self.budget.active_fact_limit])

    def _goal_candidates(self, message, omitted, reasons):
        broad = self.local_intent.is_broad_goal_query(message)
        try:
            reader = getattr(self.goal_service, "context_snapshot", None)
            if callable(reader):
                snapshots = reader(limit=SOURCE_SNAPSHOT_LIMIT)
            elif self.goal_service is None:
                raise RuntimeError
            else:
                snapshots = self.goal_service.list_current()
        except Exception:
            omitted["goals"] += 1
            reasons.add("goal_context_omitted")
            return (), ()

        current = []
        terminal = []
        for goal in snapshots:
            text = " ".join(
                value
                for value in (
                    goal.title,
                    goal.description,
                    goal.success_condition,
                    goal.progress_summary,
                )
                if value
            )
            score = relevance_tuple(message, text, goal.title)
            payload = self._goal_payload(goal)
            if goal.state in {GoalState.ACTIVE, GoalState.PAUSED}:
                if not is_relevant(score) and not broad:
                    omitted["active_goals"] += 1
                    reasons.add("not_relevant")
                    continue
                current.append((goal, score, payload))
            elif goal.state in {GoalState.COMPLETED, GoalState.CANCELLED}:
                if not is_relevant(score):
                    omitted["terminal_goals"] += 1
                    reasons.add("not_relevant")
                    continue
                terminal.append((goal, score, payload))

        current.sort(key=self._current_goal_key)
        terminal.sort(key=self._terminal_goal_key)
        if len(current) > self.budget.active_or_paused_goal_limit:
            omitted["active_goals"] += len(current) - self.budget.active_or_paused_goal_limit
            reasons.add("source_limit")
        if len(terminal) > self.budget.terminal_goal_limit:
            omitted["terminal_goals"] += len(terminal) - self.budget.terminal_goal_limit
            reasons.add("source_limit")
        return (
            tuple(item[2] for item in current[: self.budget.active_or_paused_goal_limit]),
            tuple(item[2] for item in terminal[: self.budget.terminal_goal_limit]),
        )

    def _memory_candidates(self, message, omitted, reasons):
        try:
            reader = getattr(self.memory_service, "context_snapshot", None)
            if callable(reader):
                snapshots = reader(limit=SOURCE_SNAPSHOT_LIMIT)
            else:
                snapshots = tuple(
                    type("Memory", (), {"event_id": index, "stored_at": None, "text": text})()
                    for index, text in enumerate(self.memory_service.recall(), start=1)
                )
        except Exception:
            omitted["memories"] += 1
            reasons.add("memory_context_omitted")
            return ()

        unique = {}
        for memory in sorted(snapshots, key=lambda item: item.event_id):
            text = getattr(memory, "text", None)
            if not isinstance(text, str):
                omitted["memories"] += 1
                reasons.add("invalid_snapshot_record")
                continue
            if len(text) > self.budget.individual_memory_character_limit:
                omitted["memories"] += 1
                reasons.add("record_oversized")
                continue
            fingerprint = memory_fingerprint(text)
            if fingerprint in unique:
                omitted["memories"] += 1
                reasons.add("duplicate_record")
                continue
            unique[fingerprint] = memory

        candidates = []
        for memory in unique.values():
            score = relevance_tuple(message, memory.text)
            if not is_relevant(score):
                omitted["memories"] += 1
                reasons.add("not_relevant")
                continue
            candidates.append(
                (
                    score,
                    memory,
                    {
                        "event_id": memory.event_id,
                        "stored_at": memory.stored_at,
                        "text": memory.text,
                    },
                )
            )
        candidates.sort(
            key=lambda item: (
                -item[0][0],
                -item[0][1],
                -item[0][2],
                -_timestamp(item[1].stored_at),
                item[1].event_id,
            )
        )
        if len(candidates) > self.budget.memory_limit:
            omitted["memories"] += len(candidates) - self.budget.memory_limit
            reasons.add("source_limit")
        return tuple(item[2] for item in candidates[: self.budget.memory_limit])

    @staticmethod
    def _score_key(score, stable_key):
        return (-score[0], -score[1], -score[2], stable_key)

    @staticmethod
    def _current_goal_key(item):
        goal, score, _payload = item
        return (
            _GOAL_STATE_ORDER[goal.state],
            _GOAL_PRIORITY_ORDER[goal.priority],
            -int(is_relevant(score)),
            -score[0],
            -score[1],
            -score[2],
            -_timestamp(goal.updated_at),
            goal.goal_id,
        )

    @staticmethod
    def _terminal_goal_key(item):
        goal, score, _payload = item
        return (
            -score[0],
            -score[1],
            -score[2],
            -_timestamp(goal.updated_at),
            goal.goal_id,
        )

    @staticmethod
    def _goal_payload(goal):
        return {
            "deadline": goal.deadline,
            "goal_id": goal.goal_id,
            "owner": goal.owner.value,
            "priority": goal.priority.value,
            "progress_percent": goal.progress_percent,
            "progress_summary": goal.progress_summary,
            "progress_verification": goal.progress_verification.value,
            "state": goal.state.value,
            "success_condition": goal.success_condition,
            "title": goal.title,
            "updated_at": goal.updated_at,
        }

    def _finalize(self, core, selected, omitted, reasons):
        identity_payload = {
            **core,
            "established_preferences": selected["established"],
            "provisional_preferences": selected["provisional"],
        }
        goals_payload = selected["active_goals"] + selected["terminal_goals"]
        included = {
            "active_goals": len(selected["active_goals"]),
            "core_identity": 1,
            "established_preferences": len(selected["established"]),
            "facts": len(selected["facts"]),
            "memories": len(selected["memories"]),
            "provisional_preferences": len(selected["provisional"]),
            "terminal_goals": len(selected["terminal_goals"]),
        }
        section_sizes = {
            "goals": len(canonical_json(goals_payload)),
            "identity": len(canonical_json(identity_payload)),
            "memories": len(canonical_json(selected["memories"])),
            "user_facts": len(canonical_json(selected["facts"])),
        }
        metadata_payload = {
            "configured_budget": self.budget.total_context_characters,
            "included_counts": included,
            "omission_reason_codes": sorted(reasons),
            "omitted_counts": dict(sorted((key, count) for key, count in omitted.items() if count)),
            "section_sizes": section_sizes,
            "truncation": bool(_TRUNCATION_REASONS.intersection(reasons)),
        }
        payload = {
            "goals": goals_payload,
            "identity": identity_payload,
            "memories": selected["memories"],
            "truncation_metadata": metadata_payload,
            "user_facts": selected["facts"],
        }
        encoded = canonical_json(payload)
        bundle = ContextBundle(
            identity=IdentityContext(
                identity_id=core["identity_id"],
                display_name=core["display_name"],
                nature=core["nature"],
                role=core["role"],
                derived_display=tuple(sorted(core["derived_display"].items())),
                established_preferences=tuple(
                    PreferenceContextRecord(item["key"], item["value"], item["state"])
                    for item in selected["established"]
                ),
                provisional_preferences=tuple(
                    PreferenceContextRecord(item["key"], item["value"], item["state"])
                    for item in selected["provisional"]
                ),
            ),
            user_facts=tuple(
                UserFactContextRecord(item["key"], item["readable_key"], item["value"])
                for item in selected["facts"]
            ),
            goals=tuple(
                GoalContextRecord(
                    goal_id=item["goal_id"],
                    owner=item["owner"],
                    state=item["state"],
                    priority=item["priority"],
                    title=item["title"],
                    success_condition=item["success_condition"],
                    deadline=item["deadline"],
                    progress_summary=item["progress_summary"],
                    progress_percent=item["progress_percent"],
                    progress_verification=item["progress_verification"],
                    updated_at=item["updated_at"],
                )
                for item in goals_payload
            ),
            memories=tuple(
                MemoryContextRecord(item["event_id"], item["stored_at"], item["text"])
                for item in selected["memories"]
            ),
            truncation_metadata=TruncationMetadata(
                included_counts=tuple(sorted(included.items())),
                omitted_counts=tuple(sorted(metadata_payload["omitted_counts"].items())),
                omission_reason_codes=tuple(metadata_payload["omission_reason_codes"]),
                section_sizes=tuple(sorted(section_sizes.items())),
                configured_budget=self.budget.total_context_characters,
                truncation=metadata_payload["truncation"],
            ),
        )
        return bundle, encoded
