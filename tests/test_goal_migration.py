import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.identity import IdentityRepository, IdentityService
from src.persistence.goal_migration import (
    GoalMigrationError,
    migrate_goal_schema_v2_to_v3,
)
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import (
    GOAL_SCHEMA_VERSION,
    SQLiteDatabase,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GoalMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production_path = Path("memory/nel.sqlite3")
        cls.production_hash = (
            _sha256(cls.production_path)
            if cls.production_path.is_file()
            else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls.production_hash is not None:
            if _sha256(cls.production_path) != cls.production_hash:
                raise AssertionError("Production database changed during tests.")

    @staticmethod
    def _v2_database(directory):
        path = Path(directory) / "goal-migration.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        memory = SQLiteMemory(database)
        knowledge = SQLiteKnowledge(database)
        memory.remember("Unicode yaddaş: Ömər")
        knowledge.set("display_label", "Məqsəd")
        knowledge.set("display_label", "Yeni məqsəd")
        migrate_identity_schema_v1_to_v2(
            database,
            "2026-08-02T01:00:00Z",
        )
        identity = IdentityService(IdentityRepository(database))
        identity.create_preference_candidate(
            "language_style",
            "Azərbaycan dili",
            source_kind="manual",
            source_reference="goal-migration-test",
        )
        identity.transition_preference(
            "language_style",
            "provisional",
            source_kind="experiment",
            source_reference="goal-migration-test",
        )
        return path, database

    @staticmethod
    def _existing_rows(database):
        queries = {
            "memory_events": "SELECT * FROM memory_events ORDER BY id",
            "user_facts_current": (
                "SELECT * FROM user_facts_current ORDER BY fact_key"
            ),
            "user_fact_history": (
                "SELECT * FROM user_fact_history ORDER BY id"
            ),
            "nel_identity_current": (
                "SELECT * FROM nel_identity_current ORDER BY identity_key"
            ),
            "nel_identity_history": (
                "SELECT * FROM nel_identity_history ORDER BY id"
            ),
        }
        connection = database.connect()
        try:
            return {
                name: tuple(tuple(row) for row in connection.execute(query))
                for name, query in queries.items()
            }
        finally:
            connection.close()

    def test_v2_to_v3_migration_preserves_existing_namespaces(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._v2_database(directory)
            before = self._existing_rows(database)

            changed = migrate_goal_schema_v2_to_v3(
                database,
                "2026-08-02T02:00:00Z",
            )

            self.assertTrue(changed)
            self.assertEqual(database.current_schema_version(), 3)
            self.assertEqual(self._existing_rows(database), before)
            guarded = SQLiteDatabase(path, require_existing=True)
            guarded.validate_existing(expected_version=GOAL_SCHEMA_VERSION)

    def test_migration_creates_exact_tables_and_index(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            migrate_goal_schema_v2_to_v3(database)
            connection = database.connect()
            try:
                tables = {
                    row["name"]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_schema "
                        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                indexes = {
                    row["name"]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_schema "
                        "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                strict = {
                    row["name"]: row["strict"]
                    for row in connection.execute("PRAGMA table_list")
                    if row["name"] in {"goals_current", "goals_history"}
                }
            finally:
                connection.close()

            self.assertEqual(len(tables), 8)
            self.assertEqual(
                tables,
                {
                    "schema_version",
                    "memory_events",
                    "user_facts_current",
                    "user_fact_history",
                    "nel_identity_current",
                    "nel_identity_history",
                    "goals_current",
                    "goals_history",
                },
            )
            self.assertEqual(indexes, {"goals_current_state_updated_idx"})
            self.assertEqual(
                strict,
                {"goals_current": 1, "goals_history": 1},
            )

    def test_repeated_valid_v3_migration_is_no_op(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            self.assertTrue(migrate_goal_schema_v2_to_v3(database))
            before = self._existing_rows(database)

            changed = migrate_goal_schema_v2_to_v3(database)

            self.assertFalse(changed)
            self.assertEqual(database.current_schema_version(), 3)
            self.assertEqual(self._existing_rows(database), before)

    def test_migration_failure_rolls_back_to_intact_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            before = self._existing_rows(database)
            broken_statements = (
                "CREATE TABLE goals_current (goal_id TEXT PRIMARY KEY) STRICT",
                "INVALID SQL",
            )

            with patch(
                "src.persistence.goal_migration.GOAL_SCHEMA_STATEMENTS",
                broken_statements,
            ):
                with self.assertRaises(GoalMigrationError):
                    migrate_goal_schema_v2_to_v3(database)

            self.assertEqual(database.current_schema_version(), 2)
            self.assertEqual(self._existing_rows(database), before)
            connection = database.connect()
            try:
                goal_objects = connection.execute(
                    "SELECT COUNT(*) FROM sqlite_schema "
                    "WHERE name LIKE 'goals_%'"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(goal_objects, 0)

    def test_migration_requires_exact_schema_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.sqlite3"
            database = SQLiteDatabase(path)
            database.initialize("2026-08-02T00:00:00Z")

            with self.assertRaisesRegex(GoalMigrationError, "version 2"):
                migrate_goal_schema_v2_to_v3(database)

            self.assertEqual(database.current_schema_version(), 1)

    def test_malformed_v2_layout_is_rejected_without_goal_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            with database.transaction() as connection:
                connection.execute(
                    "ALTER TABLE user_facts_current DROP COLUMN updated_at"
                )

            with self.assertRaisesRegex(GoalMigrationError, "columns"):
                migrate_goal_schema_v2_to_v3(database)

            self.assertEqual(database.current_schema_version(), 2)
            connection = database.connect()
            try:
                goal_objects = connection.execute(
                    "SELECT COUNT(*) FROM sqlite_schema "
                    "WHERE name LIKE 'goals_%'"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(goal_objects, 0)

    def test_goal_schema_preserves_unicode_and_enforces_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            migrate_goal_schema_v2_to_v3(database)
            base = (
                "goal-unicode",
                "Azərbaycan dilində məqsəd",
                None,
                "Ömər nəticəni qəbul edir",
                "user",
                "active",
                "normal",
                None,
                None,
                None,
                "unknown",
                "validated_user",
                "conversation:Ömər",
                "approval:Ömər",
                None,
                1,
                "2026-08-02T02:00:00Z",
                "2026-08-02T02:00:00Z",
            )
            statement = (
                "INSERT INTO goals_current VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            with database.transaction() as connection:
                connection.execute(statement, base)
            connection = database.connect()
            try:
                row = connection.execute(
                    "SELECT title, success_condition, source_reference, "
                    "approval_reference FROM goals_current"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(
                tuple(row),
                (
                    "Azərbaycan dilində məqsəd",
                    "Ömər nəticəni qəbul edir",
                    "conversation:Ömər",
                    "approval:Ömər",
                ),
            )

            invalid = list(base)
            invalid[0] = "goal-model"
            invalid[11] = "model_output"
            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as connection:
                    connection.execute(statement, invalid)

    def test_guarded_v3_validation_is_explicit_not_runtime_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._v2_database(directory)
            migrate_goal_schema_v2_to_v3(database)
            guarded = SQLiteDatabase(path, require_existing=True)

            guarded.validate_existing(expected_version=3)
            with self.assertRaises(RuntimeError):
                guarded.validate_existing()


if __name__ == "__main__":
    unittest.main()
