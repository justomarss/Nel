import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.persistence import (
    BackupError,
    BackupValidationError,
    SQLiteDatabase,
    SQLiteKnowledge,
    SQLiteMemory,
    backup_sqlite_database,
    verify_sqlite_backup,
)


class SQLiteBackupTests(unittest.TestCase):
    def create_populated_database(self, directory, name="source.sqlite3"):
        path = Path(directory) / name
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        memory = SQLiteMemory(database)
        memory.remember("birinci")
        memory.remember("təkrar")
        memory.remember("təkrar")
        memory.remember("Ömərin yaddaşı")
        knowledge = SQLiteKnowledge(database)
        knowledge.set("name", "Ömər")
        knowledge.set("favorite_anime", "Bleach")
        knowledge.set("favorite_anime", "AoT")
        return database

    def file_hash(self, path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def partial_files(self, directory):
        return list(Path(directory).glob(".*.partial"))

    def test_successful_backup_preserves_counts_order_unicode_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_populated_database(directory)
            destination = Path(directory) / "backup.sqlite3"

            result = backup_sqlite_database(
                database.path,
                destination,
                timestamp="2026-08-02T01:00:00Z",
            )

            self.assertEqual(result.source_path, database.path.resolve())
            self.assertEqual(result.destination_path, destination.resolve())
            self.assertEqual(result.timestamp, "2026-08-02T01:00:00Z")
            self.assertEqual(result.validation_status, "validated")
            self.assertTrue(destination.is_file())
            self.assertTrue(verify_sqlite_backup(destination))

            backup = SQLiteDatabase(destination)
            self.assertEqual(
                SQLiteMemory(backup).recall(),
                ["birinci", "təkrar", "təkrar", "Ömərin yaddaşı"],
            )
            self.assertEqual(
                SQLiteKnowledge(backup).load(),
                {"favorite_anime": "AoT", "name": "Ömər"},
            )
            connection = backup.connect()
            try:
                counts = tuple(
                    connection.execute(
                        """
                        SELECT
                            (SELECT COUNT(*) FROM memory_events),
                            (SELECT COUNT(*) FROM user_facts_current),
                            (SELECT COUNT(*) FROM user_fact_history)
                        """
                    ).fetchone()
                )
                history = connection.execute(
                    """
                    SELECT fact_key, value, version
                    FROM user_fact_history
                    """
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(counts, (4, 2, 1))
            self.assertEqual(tuple(history), ("favorite_anime", "Bleach", 1))

    def test_verification_opens_an_isolated_restored_path(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_populated_database(directory)
            destination = Path(directory) / "backup.sqlite3"
            backup_sqlite_database(database.path, destination)

            opened_paths = []
            from src.persistence import backup as backup_module

            original = backup_module._connect_read_only

            def track(path):
                opened_paths.append(Path(path).resolve())
                return original(path)

            with patch.object(backup_module, "_connect_read_only", side_effect=track):
                self.assertTrue(verify_sqlite_backup(destination))

            self.assertEqual(len(opened_paths), 1)
            self.assertNotEqual(opened_paths[0], destination.resolve())
            self.assertNotEqual(opened_paths[0], database.path.resolve())

    def test_existing_destination_is_not_overwritten_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_populated_database(directory)
            destination = Path(directory) / "backup.sqlite3"
            destination.write_bytes(b"existing backup artifact")
            before = destination.read_bytes()

            with self.assertRaises(BackupError):
                backup_sqlite_database(database.path, destination)

            self.assertEqual(destination.read_bytes(), before)

    def test_explicit_overwrite_replaces_existing_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_populated_database(directory)
            destination = Path(directory) / "backup.sqlite3"
            destination.write_bytes(b"obsolete")

            backup_sqlite_database(
                database.path,
                destination,
                overwrite=True,
            )

            self.assertNotEqual(destination.read_bytes(), b"obsolete")
            self.assertTrue(verify_sqlite_backup(destination))

    def test_missing_source_is_rejected_without_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "missing.sqlite3"
            destination = Path(directory) / "backup.sqlite3"

            with self.assertRaises(BackupError):
                backup_sqlite_database(source, destination)

            self.assertFalse(source.exists())
            self.assertFalse(destination.exists())

    def test_uninitialized_source_is_rejected_without_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "uninitialized.sqlite3"
            sqlite3.connect(source).close()
            destination = Path(directory) / "backup.sqlite3"

            with self.assertRaises(BackupValidationError):
                backup_sqlite_database(source, destination)

            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())
            self.assertEqual(self.partial_files(directory), [])

    def test_corrupt_backup_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "corrupt.sqlite3"
            backup.write_bytes(b"not a sqlite database")

            with self.assertRaises(BackupValidationError):
                verify_sqlite_backup(backup)

    def test_incompatible_schema_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_populated_database(directory)
            with database.transaction() as connection:
                connection.execute("DELETE FROM schema_version")
                connection.execute(
                    "INSERT INTO schema_version (version, applied_at) "
                    "VALUES (2, 'future')"
                )

            with self.assertRaises(BackupValidationError):
                verify_sqlite_backup(database.path)

    def test_failed_backup_cleans_partial_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_populated_database(directory)
            destination = Path(directory) / "backup.sqlite3"

            with patch(
                "src.persistence.backup._perform_backup",
                side_effect=sqlite3.OperationalError("synthetic private error"),
            ):
                with self.assertRaises(BackupError) as raised:
                    backup_sqlite_database(database.path, destination)

            self.assertNotIn("synthetic private error", str(raised.exception))
            self.assertFalse(destination.exists())
            self.assertEqual(self.partial_files(directory), [])

    def test_failed_validation_preserves_existing_destination_and_cleans_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_populated_database(directory)
            destination = Path(directory) / "backup.sqlite3"
            destination.write_bytes(b"previous valid artifact placeholder")
            before = destination.read_bytes()

            with patch(
                "src.persistence.backup._verify_backup",
                side_effect=BackupValidationError("synthetic validation failure"),
            ):
                with self.assertRaises(BackupValidationError):
                    backup_sqlite_database(
                        database.path,
                        destination,
                        overwrite=True,
                    )

            self.assertEqual(destination.read_bytes(), before)
            self.assertEqual(self.partial_files(directory), [])

    def test_source_database_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self.create_populated_database(directory)
            destination = Path(directory) / "backup.sqlite3"
            before_hash = self.file_hash(database.path)
            before_memory = SQLiteMemory(database).recall()
            before_facts = SQLiteKnowledge(database).load()

            backup_sqlite_database(database.path, destination)

            self.assertEqual(self.file_hash(database.path), before_hash)
            self.assertEqual(SQLiteMemory(database).recall(), before_memory)
            self.assertEqual(SQLiteKnowledge(database).load(), before_facts)


if __name__ == "__main__":
    unittest.main()
