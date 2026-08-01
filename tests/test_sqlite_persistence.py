import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

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

    def test_failed_fact_update_rolls_back_history_and_current(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("favorite_anime", "Bleach")

            with self.assertRaises(sqlite3.ProgrammingError):
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
