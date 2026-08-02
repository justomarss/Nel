from collections.abc import Mapping
from datetime import datetime, timezone

from src.persistence.normalization import normalize_fact_key
from src.persistence.sqlite import SQLiteDatabase


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_fact_batch(facts) -> list[tuple[str, str]]:
    if isinstance(facts, (str, bytes, Mapping)):
        raise ValueError("Fact batch must be an iterable of fact mappings.")

    try:
        items = list(facts)
    except TypeError:
        raise ValueError(
            "Fact batch must be an iterable of fact mappings."
        ) from None

    validated = []
    keys = set()
    for fact in items:
        if not isinstance(fact, Mapping):
            raise ValueError("Each fact must be a mapping.")

        key = fact.get("key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Fact key must be a non-empty string.")

        normalized_key = normalize_fact_key(key)
        if not normalized_key:
            raise ValueError("Fact key is empty after normalization.")

        value = fact.get("value")
        if not isinstance(value, str):
            raise ValueError("Fact value must be a string.")

        if fact.get("subject") != "user":
            raise ValueError("Only facts with subject=user are supported.")

        if normalized_key in keys:
            raise ValueError("Fact batch contains a duplicate normalized key.")

        keys.add(normalized_key)
        validated.append((normalized_key, value))

    return validated


class SQLiteMemory:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def remember(self, text):
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO memory_events (content, stored_at) VALUES (?, ?)",
                (text, _utc_now()),
            )

    def recall(self, limit=None):
        connection = self.database.connect()
        try:
            if limit is None:
                rows = connection.execute(
                    "SELECT content FROM memory_events ORDER BY id"
                ).fetchall()
                return [row["content"] for row in rows]

            if limit == 0:
                return []

            if limit < 0:
                rows = connection.execute(
                    "SELECT content FROM memory_events ORDER BY id"
                ).fetchall()
                memories = [row["content"] for row in rows]
                return memories[-limit:]

            rows = connection.execute(
                """
                SELECT content
                FROM (
                    SELECT id, content
                    FROM memory_events
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id
                """,
                (limit,),
            ).fetchall()
            return [row["content"] for row in rows]
        finally:
            connection.close()

    def context_snapshot(self, limit=1000):
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT id, content, stored_at
                FROM (
                    SELECT id, content, stored_at
                    FROM memory_events
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id
                """,
                (limit,),
            ).fetchall()
            return tuple(
                {
                    "event_id": row["id"],
                    "stored_at": row["stored_at"],
                    "text": row["content"],
                }
                for row in rows
            )
        finally:
            connection.close()


class SQLiteKnowledge:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def load(self):
        connection = self.database.connect()
        try:
            rows = connection.execute(
                "SELECT fact_key, value "
                "FROM user_facts_current "
                f"{self._active_filter(connection)} "
                "ORDER BY fact_key"
            ).fetchall()
            return {row["fact_key"]: row["value"] for row in rows}
        finally:
            connection.close()

    def get(self, key):
        connection = self.database.connect()
        try:
            where = "WHERE fact_key = ?"
            if self._supports_retirement(connection):
                where += " AND fact_state = 'active'"
            row = connection.execute(
                f"SELECT value FROM user_facts_current {where}",
                (normalize_fact_key(key),),
            ).fetchone()
            return None if row is None else row["value"]
        finally:
            connection.close()

    def set(self, key, value):
        self.set_many(
            [
                {
                    "key": key,
                    "value": value,
                    "subject": "user",
                }
            ]
        )

    def set_many(self, facts):
        updates = _validate_fact_batch(facts)
        if not updates:
            return

        now = _utc_now()
        with self.database.transaction() as connection:
            for key, value in updates:
                self._set_fact(connection, key, value, now)

    def retire(self, key, reason):
        if not isinstance(key, str) or not normalize_fact_key(key):
            raise ValueError("Fact key must be a non-empty string.")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Retirement reason must be non-empty.")
        normalized_key = normalize_fact_key(key)
        now = _utc_now()
        with self.database.transaction() as connection:
            if not self._supports_retirement(connection):
                raise RuntimeError("Fact retirement requires schema version 4.")
            current = self._current(connection, normalized_key)
            if current is None:
                raise KeyError(normalized_key)
            if current["fact_state"] == "retired":
                return False
            self._archive_current(connection, normalized_key, current, now)
            connection.execute(
                """
                UPDATE user_facts_current
                SET fact_state = 'retired', revision_reason = ?,
                    version = ?, updated_at = ?
                WHERE fact_key = ?
                """,
                (reason, current["version"] + 1, now, normalized_key),
            )
            return True

    def history(self, key):
        normalized_key = normalize_fact_key(key)
        connection = self.database.connect()
        try:
            supports_retirement = self._supports_retirement(connection)
            if supports_retirement:
                history_columns = "fact_state, revision_reason"
                current_columns = "fact_state, revision_reason"
            else:
                history_columns = "'active' AS fact_state, NULL AS revision_reason"
                current_columns = "'active' AS fact_state, NULL AS revision_reason"
            rows = connection.execute(
                f"""
                SELECT fact_key, value, version, valid_from AS updated_at,
                       {history_columns}, 0 AS is_current
                FROM user_fact_history
                WHERE fact_key = ?
                UNION ALL
                SELECT fact_key, value, version, updated_at,
                       {current_columns}, 1 AS is_current
                FROM user_facts_current
                WHERE fact_key = ?
                ORDER BY version
                """,
                (normalized_key, normalized_key),
            ).fetchall()
            return tuple(dict(row) for row in rows)
        finally:
            connection.close()

    @classmethod
    def _set_fact(cls, connection, key, value, now):
        supports_retirement = cls._supports_retirement(connection)
        current = cls._current(connection, key)

        if current is None:
            if supports_retirement:
                connection.execute(
                    """
                    INSERT INTO user_facts_current (
                        fact_key, value, version, updated_at,
                        fact_state, revision_reason
                    ) VALUES (?, ?, 1, ?, 'active', NULL)
                    """,
                    (key, value, now),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO user_facts_current (
                        fact_key, value, version, updated_at
                    ) VALUES (?, ?, 1, ?)
                    """,
                    (key, value, now),
                )
            return

        if (
            current["value"] == value
            and (
                not supports_retirement
                or current["fact_state"] == "active"
            )
        ):
            return

        cls._archive_current(connection, key, current, now)
        if supports_retirement:
            connection.execute(
                """
                UPDATE user_facts_current
                SET value = ?, fact_state = 'active', revision_reason = NULL,
                    version = ?, updated_at = ?
                WHERE fact_key = ?
                """,
                (value, current["version"] + 1, now, key),
            )
        else:
            connection.execute(
                """
                UPDATE user_facts_current
                SET value = ?, version = ?, updated_at = ?
                WHERE fact_key = ?
                """,
                (value, current["version"] + 1, now, key),
            )

    @staticmethod
    def _supports_retirement(connection) -> bool:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(user_facts_current)"
            )
        }
        return {"fact_state", "revision_reason"} <= columns

    @classmethod
    def _active_filter(cls, connection) -> str:
        return (
            "WHERE fact_state = 'active'"
            if cls._supports_retirement(connection)
            else ""
        )

    @classmethod
    def _current(cls, connection, key):
        columns = "value, version, updated_at"
        if cls._supports_retirement(connection):
            columns += ", fact_state, revision_reason"
        return connection.execute(
            f"SELECT {columns} FROM user_facts_current WHERE fact_key = ?",
            (key,),
        ).fetchone()

    @classmethod
    def _archive_current(cls, connection, key, current, now):
        if cls._supports_retirement(connection):
            connection.execute(
                """
                INSERT INTO user_fact_history (
                    fact_key, value, version, valid_from, superseded_at,
                    fact_state, revision_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    current["value"],
                    current["version"],
                    current["updated_at"],
                    now,
                    current["fact_state"],
                    current["revision_reason"],
                ),
            )
            return
        connection.execute(
            """
            INSERT INTO user_fact_history (
                fact_key, value, version, valid_from, superseded_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                key,
                current["value"],
                current["version"],
                current["updated_at"],
                now,
            ),
        )
