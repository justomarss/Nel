import hashlib
import sqlite3
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from src.identity import IdentityRepository, IdentityService
from src.persistence.backup import (
    backup_sqlite_database,
    verify_sqlite_backup,
)
from src.persistence.identity_migration import (
    IDENTITY_BOOTSTRAP,
    IDENTITY_SCHEMA_VERSION,
    IdentityMigrationError,
    migrate_identity_schema_v1_to_v2,
)
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class IdentityV1Tests(unittest.TestCase):
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

    def _v1_database(self, directory):
        path = Path(directory) / "identity-test.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        return path, database

    def _v2_database(self, directory):
        path, database = self._v1_database(directory)
        migrate_identity_schema_v1_to_v2(
            database,
            "2026-08-02T01:00:00Z",
        )
        return path, database

    @staticmethod
    def _base_rows(database):
        connection = database.connect()
        try:
            return {
                "memory": tuple(
                    tuple(row)
                    for row in connection.execute(
                        "SELECT * FROM memory_events ORDER BY id"
                    )
                ),
                "facts": tuple(
                    tuple(row)
                    for row in connection.execute(
                        "SELECT * FROM user_facts_current ORDER BY fact_key"
                    )
                ),
                "fact_history": tuple(
                    tuple(row)
                    for row in connection.execute(
                        "SELECT * FROM user_fact_history ORDER BY id"
                    )
                ),
            }
        finally:
            connection.close()

    def test_migration_from_v1_to_v2_preserves_memory_and_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v1_database(directory)
            memory = SQLiteMemory(database)
            knowledge = SQLiteKnowledge(database)
            memory.remember("Yaddaş: Ömər")
            knowledge.set("name", "Ömər")
            knowledge.set("name", "Omar")
            before = self._base_rows(database)

            changed = migrate_identity_schema_v1_to_v2(
                database,
                "2026-08-02T01:00:00Z",
            )

            self.assertTrue(changed)
            self.assertEqual(database.current_schema_version(), 2)
            self.assertEqual(self._base_rows(database), before)
            connection = database.connect()
            try:
                strict_tables = {
                    row["name"]: row["strict"]
                    for row in connection.execute("PRAGMA table_list")
                    if row["name"].startswith("nel_identity_")
                }
            finally:
                connection.close()
            self.assertEqual(
                strict_tables,
                {
                    "nel_identity_current": 1,
                    "nel_identity_history": 1,
                },
            )

    def test_repeated_v2_migration_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            before = self._base_rows(database)

            changed = migrate_identity_schema_v1_to_v2(database)

            self.assertFalse(changed)
            self.assertEqual(self._base_rows(database), before)
            self.assertEqual(database.current_schema_version(), 2)

    def test_bootstrap_identity_is_immutable_and_unicode_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            repository = IdentityRepository(database)
            snapshot = repository.snapshot()

            self.assertEqual(snapshot.identity_id, "nel")
            self.assertEqual(snapshot.display_name, "Nel")
            self.assertEqual(snapshot.nature, "artificial")
            self.assertEqual(
                snapshot.role,
                "Ömər’s persistent digital companion",
            )
            self.assertEqual(snapshot.preferences, ())
            with self.assertRaises(FrozenInstanceError):
                snapshot.display_name = "Changed"

            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as connection:
                    connection.execute(
                        "UPDATE nel_identity_current SET value = 'Changed' "
                        "WHERE identity_key = 'display_name'"
                    )
            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as connection:
                    connection.execute(
                        "DELETE FROM nel_identity_current "
                        "WHERE identity_key = 'display_name'"
                    )
            self.assertEqual(repository.snapshot(), snapshot)

    def test_user_facts_and_identity_have_separate_namespaces(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v1_database(directory)
            knowledge = SQLiteKnowledge(database)
            knowledge.set("favorite_language", "Python-user")
            migrate_identity_schema_v1_to_v2(database)
            service = IdentityService(IdentityRepository(database))

            service.create_preference_candidate(
                "favorite_language",
                "Rust-Nel",
                source_kind="manual",
                source_reference="owner-review-1",
            )

            self.assertEqual(
                knowledge.get("favorite_language"),
                "Python-user",
            )
            self.assertEqual(
                service.get_preference("favorite_language").value,
                "Rust-Nel",
            )
            self.assertEqual(service.snapshot().role, IDENTITY_BOOTSTRAP["role"])

    def test_valid_preference_transitions_preserve_history(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            service = IdentityService(IdentityRepository(database))

            candidate = service.create_preference_candidate(
                "interface_style",
                "minimal",
                source_kind="experiment",
                source_reference="experiment-1",
            )
            provisional = service.transition_preference(
                "interface_style",
                "provisional",
                source_kind="experiment",
                source_reference="experiment-2",
            )
            established = service.transition_preference(
                "interface_style",
                "established",
                source_kind="manual",
                source_reference="owner-review-2",
            )
            retired = service.transition_preference(
                "interface_style",
                "retired",
                source_kind="manual",
                source_reference="owner-review-3",
            )

            self.assertEqual(candidate.version, 1)
            self.assertEqual(provisional.version, 2)
            self.assertEqual(established.version, 3)
            self.assertEqual(retired.version, 4)
            self.assertEqual(
                [record.preference_state for record in service.preference_history(
                    "interface_style"
                )],
                ["candidate", "provisional", "established"],
            )
            self.assertTrue(
                all(
                    record.superseded_at is not None
                    for record in service.preference_history("interface_style")
                )
            )

    def test_invalid_transitions_and_untrusted_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            service = IdentityService(IdentityRepository(database))

            for source_kind in (
                "generated_text",
                "user_statement",
                "temporary_thought",
            ):
                with self.assertRaisesRegex(ValueError, "not authorized"):
                    service.create_preference_candidate(
                        source_kind,
                        "value",
                        source_kind=source_kind,
                        source_reference="rejected",
                    )

            service.create_preference_candidate(
                "response_length",
                "short",
                source_kind="manual",
                source_reference="owner-review-4",
            )
            with self.assertRaisesRegex(ValueError, "Invalid"):
                service.transition_preference(
                    "response_length",
                    "established",
                    source_kind="manual",
                    source_reference="owner-review-5",
                )
            current = service.get_preference("response_length")
            self.assertEqual(current.preference_state, "candidate")
            self.assertEqual(current.version, 1)
            self.assertEqual(service.preference_history("response_length"), ())

    def test_preference_unicode_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            service = IdentityService(IdentityRepository(database))

            record = service.create_preference_candidate(
                "ünsiyyət_üslubu",
                "Ömərlə Azərbaycan dilində",
                source_kind="manual",
                source_reference="unicode-review",
            )

            self.assertEqual(record.key, "ünsiyyət_üslubu")
            self.assertEqual(record.value, "Ömərlə Azərbaycan dilində")

    def test_migration_failure_rolls_back_schema_and_base_data(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v1_database(directory)
            SQLiteMemory(database).remember("preserved")
            before = self._base_rows(database)

            with patch(
                "src.persistence.identity_migration._bootstrap_identity",
                side_effect=RuntimeError("private failure"),
            ):
                with self.assertRaises(IdentityMigrationError):
                    migrate_identity_schema_v1_to_v2(database)

            self.assertEqual(database.current_schema_version(), 1)
            self.assertEqual(self._base_rows(database), before)
            connection = database.connect()
            try:
                identity_table_count = connection.execute(
                    "SELECT COUNT(*) FROM sqlite_schema "
                    "WHERE type = 'table' AND name LIKE 'nel_identity_%'"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(identity_table_count, 0)

    def test_identity_change_failure_rolls_back_partial_history(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v2_database(directory)
            service = IdentityService(IdentityRepository(database))
            service.create_preference_candidate(
                "interaction_pace",
                "measured",
                source_kind="manual",
                source_reference="owner-review-6",
            )
            with database.transaction() as connection:
                connection.execute(
                    """
                    CREATE TRIGGER reject_identity_update
                    BEFORE UPDATE ON nel_identity_current
                    BEGIN
                        SELECT RAISE(ABORT, 'synthetic failure');
                    END
                    """
                )

            with self.assertRaises(sqlite3.IntegrityError):
                service.transition_preference(
                    "interaction_pace",
                    "provisional",
                    source_kind="manual",
                    source_reference="owner-review-7",
                )

            current = service.get_preference("interaction_pace")
            self.assertEqual(current.preference_state, "candidate")
            self.assertEqual(current.version, 1)
            self.assertEqual(service.preference_history("interaction_pace"), ())

    def test_schema_v2_backup_and_isolated_restore_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._v2_database(directory)
            service = IdentityService(IdentityRepository(database))
            service.create_preference_candidate(
                "response_tone",
                "sakit",
                source_kind="manual",
                source_reference="owner-review-8",
            )
            service.transition_preference(
                "response_tone",
                "provisional",
                source_kind="manual",
                source_reference="owner-review-9",
            )
            backup_path = Path(directory) / "identity-v2.backup"

            result = backup_sqlite_database(path, backup_path)

            self.assertEqual(result.validation_status, "validated")
            self.assertTrue(verify_sqlite_backup(backup_path))
            restored = IdentityService(
                IdentityRepository(SQLiteDatabase(backup_path))
            )
            self.assertEqual(restored.snapshot(), service.snapshot())


if __name__ == "__main__":
    unittest.main()
