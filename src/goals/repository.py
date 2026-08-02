import sqlite3

from src.goals.models import (
    GoalOwner,
    GoalPriority,
    GoalRevision,
    GoalSnapshot,
    GoalSourceKind,
    GoalState,
    ProgressVerification,
)
from src.persistence.sqlite import SQLiteDatabase


CURRENT_COLUMNS = """
    goal_id, title, description, success_condition, owner, state,
    priority, deadline, progress_summary, progress_percentage,
    progress_verification, source_kind, source_reference,
    approval_reference, revision_reason, version, created_at, updated_at
"""


class GoalRepositoryError(RuntimeError):
    pass


class GoalNotFoundError(GoalRepositoryError):
    pass


class GoalVersionConflict(GoalRepositoryError):
    pass


def _snapshot(row) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id=row["goal_id"],
        title=row["title"],
        description=row["description"],
        success_condition=row["success_condition"],
        owner=GoalOwner(row["owner"]),
        state=GoalState(row["state"]),
        priority=GoalPriority(row["priority"]),
        deadline=row["deadline"],
        progress_summary=row["progress_summary"],
        progress_percent=row["progress_percentage"],
        progress_verification=ProgressVerification(
            row["progress_verification"]
        ),
        source_kind=GoalSourceKind(row["source_kind"]),
        source_reference=row["source_reference"],
        approval_reference=row["approval_reference"],
        revision_reason=row["revision_reason"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _values(snapshot: GoalSnapshot) -> tuple:
    return (
        snapshot.goal_id,
        snapshot.title,
        snapshot.description,
        snapshot.success_condition,
        snapshot.owner.value,
        snapshot.state.value,
        snapshot.priority.value,
        snapshot.deadline,
        snapshot.progress_summary,
        snapshot.progress_percent,
        snapshot.progress_verification.value,
        snapshot.source_kind.value,
        snapshot.source_reference,
        snapshot.approval_reference,
        snapshot.revision_reason,
        snapshot.version,
        snapshot.created_at,
        snapshot.updated_at,
    )


class GoalRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def get(self, goal_id: str) -> GoalSnapshot | None:
        connection = None
        try:
            connection = self.database.connect()
            row = connection.execute(
                f"SELECT {CURRENT_COLUMNS} FROM goals_current "
                "WHERE goal_id = ?",
                (goal_id,),
            ).fetchone()
            return None if row is None else _snapshot(row)
        except (OSError, sqlite3.Error) as exc:
            raise GoalRepositoryError(
                f"Goal read failed ({type(exc).__name__})."
            ) from None
        finally:
            if connection is not None:
                connection.close()

    def list_current(self) -> tuple[GoalSnapshot, ...]:
        connection = None
        try:
            connection = self.database.connect()
            rows = connection.execute(
                f"SELECT {CURRENT_COLUMNS} FROM goals_current "
                "ORDER BY updated_at DESC, goal_id"
            ).fetchall()
            return tuple(_snapshot(row) for row in rows)
        except (OSError, sqlite3.Error) as exc:
            raise GoalRepositoryError(
                f"Goal list failed ({type(exc).__name__})."
            ) from None
        finally:
            if connection is not None:
                connection.close()

    def history(self, goal_id: str) -> tuple[GoalRevision, ...]:
        connection = None
        try:
            connection = self.database.connect()
            rows = connection.execute(
                f"SELECT {CURRENT_COLUMNS}, superseded_at "
                "FROM goals_history WHERE goal_id = ? ORDER BY version",
                (goal_id,),
            ).fetchall()
            return tuple(
                GoalRevision(
                    snapshot=_snapshot(row),
                    superseded_at=row["superseded_at"],
                    revision_reason=row["revision_reason"],
                )
                for row in rows
            )
        except (OSError, sqlite3.Error) as exc:
            raise GoalRepositoryError(
                f"Goal history read failed ({type(exc).__name__})."
            ) from None
        finally:
            if connection is not None:
                connection.close()

    def _create(self, snapshot: GoalSnapshot) -> GoalSnapshot:
        if not isinstance(snapshot, GoalSnapshot):
            raise ValueError("Goal creation requires a GoalSnapshot.")
        if snapshot.version != 1 or snapshot.revision_reason is not None:
            raise ValueError("Goal creation requires an initial version.")
        if snapshot.state is not GoalState.ACTIVE:
            raise ValueError("New goals must start active.")
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    f"INSERT INTO goals_current ({CURRENT_COLUMNS}) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    _values(snapshot),
                )
        except GoalRepositoryError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise GoalRepositoryError(
                f"Goal creation failed ({type(exc).__name__})."
            ) from None
        return self._require(snapshot.goal_id)

    def _update(
        self,
        proposed: GoalSnapshot,
        *,
        expected_version: int,
    ) -> GoalSnapshot:
        return self._replace(
            proposed,
            expected_version=expected_version,
            allowed_current_states={GoalState.ACTIVE, GoalState.PAUSED},
        )

    def _reopen(
        self,
        proposed: GoalSnapshot,
        *,
        expected_version: int,
    ) -> GoalSnapshot:
        if proposed.state is not GoalState.ACTIVE:
            raise ValueError("Reopened goals must become active.")
        return self._replace(
            proposed,
            expected_version=expected_version,
            allowed_current_states={GoalState.COMPLETED},
        )

    def _restore(
        self,
        proposed: GoalSnapshot,
        *,
        expected_version: int,
    ) -> GoalSnapshot:
        if proposed.state is not GoalState.ACTIVE:
            raise ValueError("Restored goals must become active.")
        return self._replace(
            proposed,
            expected_version=expected_version,
            allowed_current_states={GoalState.CANCELLED},
        )

    def _replace(
        self,
        proposed: GoalSnapshot,
        *,
        expected_version: int,
        allowed_current_states: set[GoalState],
    ) -> GoalSnapshot:
        if not isinstance(proposed, GoalSnapshot):
            raise ValueError("Goal update requires a GoalSnapshot.")
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    f"SELECT {CURRENT_COLUMNS} FROM goals_current "
                    "WHERE goal_id = ?",
                    (proposed.goal_id,),
                ).fetchone()
                if row is None:
                    raise GoalNotFoundError("Goal does not exist.")
                current = _snapshot(row)
                if current.version != expected_version:
                    raise GoalVersionConflict("Goal version changed concurrently.")
                if current.state not in allowed_current_states:
                    raise GoalRepositoryError("Goal state does not allow this update.")
                if proposed.version != expected_version + 1:
                    raise GoalVersionConflict("Proposed goal version is invalid.")
                if proposed.created_at != current.created_at:
                    raise GoalRepositoryError("Goal creation timestamp changed.")

                self._insert_history(
                    connection,
                    current,
                    superseded_at=proposed.updated_at,
                )
                self._write_current(
                    connection,
                    proposed,
                    expected_version=expected_version,
                )
        except GoalRepositoryError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise GoalRepositoryError(
                f"Goal update failed ({type(exc).__name__})."
            ) from None
        return self._require(proposed.goal_id)

    def _require(self, goal_id: str) -> GoalSnapshot:
        snapshot = self.get(goal_id)
        if snapshot is None:
            raise GoalNotFoundError("Goal does not exist.")
        return snapshot

    @staticmethod
    def _insert_history(connection, current, *, superseded_at: str) -> None:
        connection.execute(
            f"INSERT INTO goals_history ({CURRENT_COLUMNS}, superseded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _values(current) + (superseded_at,),
        )

    @staticmethod
    def _write_current(connection, proposed, *, expected_version: int) -> None:
        cursor = connection.execute(
            """
            UPDATE goals_current
            SET title = ?, description = ?, success_condition = ?, owner = ?,
                state = ?, priority = ?, deadline = ?, progress_summary = ?,
                progress_percentage = ?, progress_verification = ?,
                source_kind = ?, source_reference = ?, approval_reference = ?,
                revision_reason = ?, version = ?, updated_at = ?
            WHERE goal_id = ? AND version = ?
            """,
            (
                proposed.title,
                proposed.description,
                proposed.success_condition,
                proposed.owner.value,
                proposed.state.value,
                proposed.priority.value,
                proposed.deadline,
                proposed.progress_summary,
                proposed.progress_percent,
                proposed.progress_verification.value,
                proposed.source_kind.value,
                proposed.source_reference,
                proposed.approval_reference,
                proposed.revision_reason,
                proposed.version,
                proposed.updated_at,
                proposed.goal_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise GoalVersionConflict("Goal version changed concurrently.")
