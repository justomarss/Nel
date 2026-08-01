from datetime import datetime, timezone

from src.persistence.sqlite import SQLiteDatabase


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


class SQLiteKnowledge:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def load(self):
        connection = self.database.connect()
        try:
            rows = connection.execute(
                "SELECT fact_key, value "
                "FROM user_facts_current ORDER BY fact_key"
            ).fetchall()
            return {row["fact_key"]: row["value"] for row in rows}
        finally:
            connection.close()

    def get(self, key):
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT value FROM user_facts_current WHERE fact_key = ?",
                (key,),
            ).fetchone()
            return None if row is None else row["value"]
        finally:
            connection.close()

    def set(self, key, value):
        with self.database.transaction() as connection:
            current = connection.execute(
                """
                SELECT value, version, updated_at
                FROM user_facts_current
                WHERE fact_key = ?
                """,
                (key,),
            ).fetchone()
            now = _utc_now()

            if current is None:
                connection.execute(
                    """
                    INSERT INTO user_facts_current (
                        fact_key, value, version, updated_at
                    ) VALUES (?, ?, 1, ?)
                    """,
                    (key, value, now),
                )
                return

            if current["value"] == value:
                return

            connection.execute(
                """
                INSERT INTO user_fact_history (
                    fact_key,
                    value,
                    version,
                    valid_from,
                    superseded_at
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
            connection.execute(
                """
                UPDATE user_facts_current
                SET value = ?, version = ?, updated_at = ?
                WHERE fact_key = ?
                """,
                (value, current["version"] + 1, now, key),
            )
