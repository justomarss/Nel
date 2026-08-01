import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.persistence import (
    MigrationError,
    SQLiteDatabase,
    SQLiteKnowledge,
    SQLiteMemory,
    migrate_json_to_sqlite,
)


class SQLiteMigrationTests(unittest.TestCase):
    def create_paths(self, directory):
        root = Path(directory)
        return root / "long_term.json", root / "knowledge.json"

    def create_database(self, directory, name="nel-test.sqlite3"):
        database = SQLiteDatabase(Path(directory) / name)
        database.initialize("2026-08-02T00:00:00Z")
        return database

    def write_json(self, path, data):
        path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )

    def assert_empty_target(self, database):
        connection = database.connect()
        try:
            memory_count = connection.execute(
                "SELECT COUNT(*) FROM memory_events"
            ).fetchone()[0]
            current_count = connection.execute(
                "SELECT COUNT(*) FROM user_facts_current"
            ).fetchone()[0]
            history_count = connection.execute(
                "SELECT COUNT(*) FROM user_fact_history"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual((memory_count, current_count, history_count), (0, 0, 0))

    def test_success_preserves_order_duplicates_unicode_and_literals(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self.create_paths(directory)
            self.write_json(
                memory_path,
                ["birinci", "təkrar", "təkrar", "Ömər"],
            )
            self.write_json(
                knowledge_path,
                {"Favorite Anime": "AoT", "Name": "Ömər"},
            )
            database = self.create_database(directory)

            result = migrate_json_to_sqlite(
                database,
                memory_path,
                knowledge_path,
                "2026-08-02T01:00:00Z",
            )

            self.assertEqual(
                SQLiteMemory(database).recall(),
                ["birinci", "təkrar", "təkrar", "Ömər"],
            )
            self.assertEqual(
                SQLiteKnowledge(database).load(),
                {"favorite_anime": "AoT", "name": "Ömər"},
            )
            self.assertEqual(result.memory_inserted, 4)
            self.assertEqual(result.facts_inserted, 2)

            connection = database.connect()
            try:
                source_ids = [
                    row["source_id"]
                    for row in connection.execute(
                        "SELECT source_id FROM memory_events ORDER BY id"
                    )
                ]
                history_count = connection.execute(
                    "SELECT COUNT(*) FROM user_fact_history"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(
                source_ids,
                [
                    "json:memory/long_term.json:0",
                    "json:memory/long_term.json:1",
                    "json:memory/long_term.json:2",
                    "json:memory/long_term.json:3",
                ],
            )
            self.assertEqual(history_count, 0)

    def test_repeated_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self.create_paths(directory)
            self.write_json(memory_path, ["one", "one"])
            self.write_json(knowledge_path, {"Name": "Ömər"})
            database = self.create_database(directory)

            migrate_json_to_sqlite(database, memory_path, knowledge_path)
            second = migrate_json_to_sqlite(
                database,
                memory_path,
                knowledge_path,
            )

            self.assertEqual(SQLiteMemory(database).recall(), ["one", "one"])
            self.assertEqual(SQLiteKnowledge(database).load(), {"name": "Ömər"})
            self.assertEqual(second.memory_inserted, 0)
            self.assertEqual(second.memory_existing, 2)
            self.assertEqual(second.facts_inserted, 0)
            self.assertEqual(second.facts_existing, 1)

    def test_malformed_json_aborts_without_writes_or_private_values(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self.create_paths(directory)
            self.write_json(memory_path, ["PRIVATE_MEMORY_VALUE"])
            knowledge_path.write_text(
                '{"name": "PRIVATE_FACT_VALUE"',
                encoding="utf-8",
            )
            database = self.create_database(directory)

            with self.assertRaises(MigrationError) as raised:
                migrate_json_to_sqlite(database, memory_path, knowledge_path)

            self.assertIn(str(knowledge_path), str(raised.exception))
            self.assertNotIn("PRIVATE_MEMORY_VALUE", str(raised.exception))
            self.assertNotIn("PRIVATE_FACT_VALUE", str(raised.exception))
            self.assert_empty_target(database)

    def test_wrong_top_level_types_abort(self):
        cases = [
            ({"not": "a list"}, {}),
            ([], ["not", "an", "object"]),
        ]
        for memory_data, knowledge_data in cases:
            with self.subTest(memory_data=memory_data, knowledge_data=knowledge_data):
                with tempfile.TemporaryDirectory() as directory:
                    memory_path, knowledge_path = self.create_paths(directory)
                    self.write_json(memory_path, memory_data)
                    self.write_json(knowledge_path, knowledge_data)
                    database = self.create_database(directory)

                    with self.assertRaises(MigrationError):
                        migrate_json_to_sqlite(
                            database,
                            memory_path,
                            knowledge_path,
                        )
                    self.assert_empty_target(database)

    def test_non_string_memory_and_fact_values_abort(self):
        cases = [
            (["valid", 7], {}),
            ([], {"name": 7}),
        ]
        for memory_data, knowledge_data in cases:
            with self.subTest(memory_data=memory_data, knowledge_data=knowledge_data):
                with tempfile.TemporaryDirectory() as directory:
                    memory_path, knowledge_path = self.create_paths(directory)
                    self.write_json(memory_path, memory_data)
                    self.write_json(knowledge_path, knowledge_data)
                    database = self.create_database(directory)

                    with self.assertRaises(MigrationError):
                        migrate_json_to_sqlite(
                            database,
                            memory_path,
                            knowledge_path,
                        )
                    self.assert_empty_target(database)

    def test_non_string_fact_key_is_rejected_defensively(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self.create_paths(directory)
            self.write_json(memory_path, [])
            self.write_json(knowledge_path, {})
            database = self.create_database(directory)

            with patch(
                "src.persistence.migration._load_json",
                side_effect=[[], {7: "value"}],
            ):
                with self.assertRaises(MigrationError):
                    migrate_json_to_sqlite(
                        database,
                        memory_path,
                        knowledge_path,
                    )
            self.assert_empty_target(database)

    def test_normalized_key_collision_aborts(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self.create_paths(directory)
            self.write_json(memory_path, ["must not import"])
            self.write_json(
                knowledge_path,
                {"Favorite Anime": "AoT", "favorite-anime": "Bleach"},
            )
            database = self.create_database(directory)

            with self.assertRaises(MigrationError) as raised:
                migrate_json_to_sqlite(database, memory_path, knowledge_path)

            self.assertIn("favorite_anime", str(raised.exception))
            self.assert_empty_target(database)

    def test_existing_matching_fact_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self.create_paths(directory)
            self.write_json(memory_path, [])
            self.write_json(knowledge_path, {"Name": "Ömər"})
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("name", "Ömər")

            result = migrate_json_to_sqlite(
                database,
                memory_path,
                knowledge_path,
            )

            self.assertEqual(result.facts_inserted, 0)
            self.assertEqual(result.facts_existing, 1)
            connection = database.connect()
            try:
                history_count = connection.execute(
                    "SELECT COUNT(*) FROM user_fact_history"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(history_count, 0)

    def test_conflicting_fact_rolls_back_memory_and_partial_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self.create_paths(directory)
            self.write_json(memory_path, ["must roll back"])
            self.write_json(
                knowledge_path,
                {"Favorite Game": "MK11", "Name": "New Name"},
            )
            database = self.create_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("name", "Existing Name")

            with self.assertRaises(MigrationError) as raised:
                migrate_json_to_sqlite(database, memory_path, knowledge_path)

            self.assertIn("name", str(raised.exception))
            self.assertEqual(SQLiteMemory(database).recall(), [])
            self.assertEqual(knowledge.load(), {"name": "Existing Name"})
            connection = database.connect()
            try:
                history_count = connection.execute(
                    "SELECT COUNT(*) FROM user_fact_history"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(history_count, 0)

    def test_database_error_rolls_back_all_migration_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self.create_paths(directory)
            self.write_json(memory_path, ["PRIVATE_MEMORY"])
            self.write_json(
                knowledge_path,
                {"First": "PRIVATE_FIRST", "Blocked": "PRIVATE_BLOCKED"},
            )
            database = self.create_database(directory)
            connection = database.connect()
            try:
                connection.execute(
                    """
                    CREATE TRIGGER fail_blocked_import
                    BEFORE INSERT ON user_facts_current
                    WHEN NEW.fact_key = 'blocked'
                    BEGIN
                        SELECT RAISE(ABORT, 'synthetic database failure');
                    END
                    """
                )
            finally:
                connection.close()

            with self.assertRaises(MigrationError) as raised:
                migrate_json_to_sqlite(database, memory_path, knowledge_path)

            diagnostic = str(raised.exception)
            self.assertIn(str(knowledge_path), diagnostic)
            self.assertIn("blocked", diagnostic)
            self.assertNotIn("PRIVATE_MEMORY", diagnostic)
            self.assertNotIn("PRIVATE_FIRST", diagnostic)
            self.assertNotIn("PRIVATE_BLOCKED", diagnostic)
            self.assert_empty_target(database)

    def test_failed_target_can_be_discarded_and_repeated_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self.create_paths(directory)
            self.write_json(memory_path, ["one", "two"])
            self.write_json(
                knowledge_path,
                {"Name": "Ömər", "name": "Collision"},
            )
            database = self.create_database(directory)

            with self.assertRaises(MigrationError):
                migrate_json_to_sqlite(database, memory_path, knowledge_path)
            self.assert_empty_target(database)

            database.path.unlink()
            self.write_json(knowledge_path, {"Name": "Ömər"})
            clean_database = self.create_database(directory)
            migrate_json_to_sqlite(
                clean_database,
                memory_path,
                knowledge_path,
            )

            self.assertEqual(SQLiteMemory(clean_database).recall(), ["one", "two"])
            self.assertEqual(SQLiteKnowledge(clean_database).load(), {"name": "Ömər"})


if __name__ == "__main__":
    unittest.main()
