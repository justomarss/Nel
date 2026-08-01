import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from src.persistence import (
    SCHEMA_VERSION,
    SQLiteDatabase,
    SQLiteKnowledge,
    SQLiteMemory,
    UnsupportedSchemaVersion,
)


class SQLitePersistenceTests(unittest.TestCase):
    def create_database(self, directory):
        database = SQLiteDatabase(Path(directory) / "nel-test.sqlite3")
        database.initialize("2026-08-02T00:00:00Z")
        return database

    def test_schema_creation_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            connection = database.connect()
            try:
                tables = {
                    row["name"]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_schema
                        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                        """
                    )
                }
                definitions = {
                    row["name"]: row["sql"]
                    for row in connection.execute(
                        """
                        SELECT name, sql
                        FROM sqlite_schema
                        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                        """
                    )
                }
            finally:
                connection.close()

            self.assertEqual(
                tables,
                {
                    "schema_version",
                    "memory_events",
                    "user_facts_current",
                    "user_fact_history",
                },
            )
            self.assertTrue(
                all("STRICT" in sql.upper() for sql in definitions.values())
            )
            self.assertEqual(database.current_schema_version(), SCHEMA_VERSION)

    def test_repeated_initialization_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            database.initialize("2099-01-01T00:00:00Z")
            connection = database.connect()
            try:
                versions = connection.execute(
                    "SELECT version, applied_at FROM schema_version"
                ).fetchall()
            finally:
                connection.close()

            self.assertEqual(len(versions), 1)
            self.assertEqual(versions[0]["version"], SCHEMA_VERSION)
            self.assertEqual(versions[0]["applied_at"], "2026-08-02T00:00:00Z")

    def test_concurrent_initialization_creates_one_schema_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nel-test.sqlite3"
            barrier = threading.Barrier(4)
            errors = []

            def initialize():
                try:
                    barrier.wait()
                    SQLiteDatabase(path).initialize("2026-08-02T00:00:00Z")
                except BaseException as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=initialize) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(2)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])

            database = SQLiteDatabase(path)
            connection = database.connect()
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM schema_version"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 1)

    def test_unsupported_schema_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            with database.transaction() as connection:
                connection.execute("DELETE FROM schema_version")
                connection.execute(
                    "INSERT INTO schema_version (version, applied_at) "
                    "VALUES (2, 'future')"
                )

            with self.assertRaises(UnsupportedSchemaVersion):
                database.initialize("2026-08-02T00:00:00Z")

    def test_memory_ordering_limits_and_full_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            memory = SQLiteMemory(database)
            for text in ("oldest", "middle", "newest"):
                memory.remember(text)

            self.assertEqual(memory.recall(limit=2), ["middle", "newest"])
            self.assertEqual(memory.recall(limit=0), [])
            self.assertEqual(
                memory.recall(),
                ["oldest", "middle", "newest"],
            )

    def test_memory_and_knowledge_preserve_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            memory = SQLiteMemory(database)
            knowledge = SQLiteKnowledge(database)

            memory.remember("Mənim adım Ömərdir.")
            knowledge.set("name", "Ömər")

            self.assertEqual(memory.recall(), ["Mənim adım Ömərdir."])
            self.assertEqual(knowledge.get("name"), "Ömər")

    def test_new_fact_insertion_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)

            knowledge.set("favorite_anime", "AoT")

            self.assertEqual(knowledge.get("favorite_anime"), "AoT")
            self.assertIsNone(knowledge.get("missing"))
            self.assertEqual(knowledge.load(), {"favorite_anime": "AoT"})

    def test_multiple_new_facts_are_written_in_one_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)

            knowledge.set_many(
                [
                    {"key": "Name", "value": "Ömər", "subject": "user"},
                    {
                        "key": "Favorite Anime",
                        "value": "AoT",
                        "subject": "user",
                    },
                ]
            )

            self.assertEqual(
                knowledge.load(),
                {"favorite_anime": "AoT", "name": "Ömər"},
            )

    def test_batch_mixes_no_op_and_changed_value(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("favorite_anime", "Bleach")
            knowledge.set("favorite_game", "MK11")

            knowledge.set_many(
                [
                    {
                        "key": "favorite-game",
                        "value": "MK11",
                        "subject": "user",
                    },
                    {
                        "key": "favorite anime",
                        "value": "AoT",
                        "subject": "user",
                    },
                ]
            )

            connection = database.connect()
            try:
                current = {
                    row["fact_key"]: (row["value"], row["version"])
                    for row in connection.execute(
                        """
                        SELECT fact_key, value, version
                        FROM user_facts_current
                        """
                    )
                }
                history = [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT fact_key, value, version
                        FROM user_fact_history
                        """
                    )
                ]
            finally:
                connection.close()

            self.assertEqual(current["favorite_game"], ("MK11", 1))
            self.assertEqual(current["favorite_anime"], ("AoT", 2))
            self.assertEqual(history, [("favorite_anime", "Bleach", 1)])

    def test_batch_updates_increment_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("favorite_anime", "Bleach")
            knowledge.set_many(
                [
                    {
                        "key": "favorite_anime",
                        "value": "AoT",
                        "subject": "user",
                    }
                ]
            )
            knowledge.set_many(
                [
                    {
                        "key": "favorite_anime",
                        "value": "Monster",
                        "subject": "user",
                    }
                ]
            )

            connection = database.connect()
            try:
                current = connection.execute(
                    """
                    SELECT value, version FROM user_facts_current
                    WHERE fact_key = 'favorite_anime'
                    """
                ).fetchone()
                history = connection.execute(
                    """
                    SELECT value, version FROM user_fact_history
                    WHERE fact_key = 'favorite_anime'
                    ORDER BY version
                    """
                ).fetchall()
            finally:
                connection.close()

            self.assertEqual(tuple(current), ("Monster", 3))
            self.assertEqual(
                [tuple(row) for row in history],
                [("Bleach", 1), ("AoT", 2)],
            )

    def test_invalid_batches_are_rejected_before_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            invalid_batches = [
                [{"key": "", "value": "x", "subject": "user"}],
                [{"key": "---", "value": "x", "subject": "user"}],
                [{"key": "name", "value": 123, "subject": "user"}],
                [{"key": "name", "value": "Ömər", "subject": "nel"}],
                [
                    {
                        "key": "Favorite Anime",
                        "value": "AoT",
                        "subject": "user",
                    },
                    {
                        "key": "favorite-anime",
                        "value": "Bleach",
                        "subject": "user",
                    },
                ],
            ]

            with patch.object(
                database,
                "transaction",
                side_effect=AssertionError("transaction opened"),
            ):
                for batch in invalid_batches:
                    with self.subTest(batch=batch):
                        with self.assertRaises(ValueError):
                            knowledge.set_many(batch)

            self.assertEqual(knowledge.load(), {})

    def test_batch_failure_rolls_back_current_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("first", "old-first")
            knowledge.set("blocked", "old-blocked")

            connection = database.connect()
            try:
                connection.execute(
                    """
                    CREATE TRIGGER fail_blocked_update
                    BEFORE UPDATE ON user_facts_current
                    WHEN NEW.fact_key = 'blocked'
                    BEGIN
                        SELECT RAISE(ABORT, 'synthetic batch failure');
                    END
                    """
                )
            finally:
                connection.close()

            with self.assertRaises(sqlite3.IntegrityError):
                knowledge.set_many(
                    [
                        {
                            "key": "first",
                            "value": "new-first",
                            "subject": "user",
                        },
                        {
                            "key": "blocked",
                            "value": "new-blocked",
                            "subject": "user",
                        },
                    ]
                )

            self.assertEqual(
                knowledge.load(),
                {"blocked": "old-blocked", "first": "old-first"},
            )
            connection = database.connect()
            try:
                history_count = connection.execute(
                    "SELECT COUNT(*) FROM user_fact_history"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(history_count, 0)

    def test_same_value_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("favorite_game", "MK11")

            connection = database.connect()
            try:
                before = connection.execute(
                    "SELECT version, updated_at FROM user_facts_current"
                ).fetchone()
            finally:
                connection.close()

            knowledge.set("favorite_game", "MK11")

            connection = database.connect()
            try:
                after = connection.execute(
                    "SELECT version, updated_at FROM user_facts_current"
                ).fetchone()
                history_count = connection.execute(
                    "SELECT COUNT(*) FROM user_fact_history"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(tuple(after), tuple(before))
            self.assertEqual(history_count, 0)

    def test_changed_fact_creates_recoverable_history(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("favorite_anime", "Bleach")
            knowledge.set("favorite_anime", "AoT")

            connection = database.connect()
            try:
                current = connection.execute(
                    """
                    SELECT value, version
                    FROM user_facts_current
                    WHERE fact_key = 'favorite_anime'
                    """
                ).fetchone()
                history = connection.execute(
                    """
                    SELECT value, version, valid_from, superseded_at
                    FROM user_fact_history
                    WHERE fact_key = 'favorite_anime'
                    """
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(tuple(current), ("AoT", 2))
            self.assertEqual(history["value"], "Bleach")
            self.assertEqual(history["version"], 1)
            self.assertTrue(history["valid_from"])
            self.assertTrue(history["superseded_at"])

    def test_set_rejects_invalid_value_without_writing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("favorite_anime", "Bleach")

            with self.assertRaises(ValueError):
                knowledge.set("favorite_anime", object())

            connection = database.connect()
            try:
                current = connection.execute(
                    "SELECT value, version FROM user_facts_current"
                ).fetchone()
                history_count = connection.execute(
                    "SELECT COUNT(*) FROM user_fact_history"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(tuple(current), ("Bleach", 1))
            self.assertEqual(history_count, 0)


if __name__ == "__main__":
    unittest.main()
