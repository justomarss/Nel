import json
from datetime import datetime

from src.goals.models import GoalPriority, GoalSnapshot, GoalState


MAX_CURRENT_GOALS = 10
MAX_TERMINAL_GOALS = 5
MAX_SERIALIZED_CHARACTERS = 4096


_PRIORITY_ORDER = {
    GoalPriority.HIGH: 0,
    GoalPriority.NORMAL: 1,
    GoalPriority.LOW: 2,
}
_STATE_ORDER = {
    GoalState.ACTIVE: 0,
    GoalState.PAUSED: 1,
}


class GoalContextSerializer:
    def serialize(self, goals) -> str:
        snapshots = tuple(goals)
        if any(not isinstance(goal, GoalSnapshot) for goal in snapshots):
            raise ValueError("Goal context accepts only GoalSnapshot values.")

        current = sorted(
            (
                goal
                for goal in snapshots
                if goal.state in {GoalState.ACTIVE, GoalState.PAUSED}
            ),
            key=self._current_order,
        )[:MAX_CURRENT_GOALS]
        terminal = sorted(
            (
                goal
                for goal in snapshots
                if goal.state in {GoalState.COMPLETED, GoalState.CANCELLED}
            ),
            key=self._terminal_order,
        )[:MAX_TERMINAL_GOALS]

        while True:
            serialized = self._encode(current, terminal)
            if len(serialized) <= MAX_SERIALIZED_CHARACTERS:
                return serialized
            if terminal:
                terminal.pop()
            elif current:
                current.pop()
            else:
                raise ValueError("Empty goal context exceeds its character limit.")

    @staticmethod
    def _current_order(goal: GoalSnapshot):
        deadline = goal.deadline or ""
        return (
            _STATE_ORDER[goal.state],
            _PRIORITY_ORDER[goal.priority],
            goal.deadline is None,
            deadline,
            -GoalContextSerializer._timestamp(goal.updated_at),
            goal.goal_id,
        )

    @staticmethod
    def _terminal_order(goal: GoalSnapshot):
        return (
            -GoalContextSerializer._timestamp(goal.updated_at),
            goal.goal_id,
        )

    @staticmethod
    def _timestamp(value: str) -> float:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

    @classmethod
    def _encode(cls, current, terminal) -> str:
        payload = {
            "active_or_paused": [cls._goal_payload(goal) for goal in current],
            "completed_or_cancelled": [
                cls._goal_payload(goal) for goal in terminal
            ],
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _goal_payload(goal: GoalSnapshot) -> dict:
        return {
            "deadline": goal.deadline,
            "goal_id": goal.goal_id,
            "owner": goal.owner.value,
            "priority": goal.priority.value,
            "progress": {
                "percent": goal.progress_percent,
                "summary": goal.progress_summary,
                "verification": goal.progress_verification.value,
            },
            "state": goal.state.value,
            "success_condition": goal.success_condition,
            "title": goal.title,
            "updated_at": goal.updated_at,
        }
