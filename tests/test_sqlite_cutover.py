import hashlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import sqlite_cutover
from src.persistence.backup import BackupError
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase


class SQLiteCutoverTests(unittest.TestCase):
    def _sources(self, directory, *, malformed=False):
        root = Path(directory)
        memory_path = root / "long_term.json"
        knowledge_path = root / "knowledge.json"
        if malformed:
            memory_path.write_text('["private memory",', encoding="utf-8")
        else:
            memory_path.write_text(
                json.dumps(
                    ["Gizli yaddaş", "Gizli yaddaş", "Ömərin qeydi"],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        knowledge_path.write_text(
            json.dumps(
                {"name": "Ömər", "favorite_game": "MK11"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return memory_path, knowledge_path

    def _cutover_paths(self, directory):
        root = Path(directory)
        return (
            root / "nel.sqlite3",
            root / "backups" / "sqlite-cutover",
            root / "nel.sqlite3.cutover.json",
        )

    def _hash(self, path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def test_successful_rehearsal_uses_copies_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            memory_bytes = memory_path.read_bytes()
            knowledge_bytes = knowledge_path.read_bytes()

            report = sqlite_cutover.rehearse(memory_path, knowledge_path)

            self.assertEqual(report.status, "PASS")
            self.assertEqual(report.counts["memory_events"], 3)
            self.assertEqual(report.counts["user_facts_current"], 2)
            self.assertEqual(report.counts["user_fact_history"], 0)
            self.assertEqual(memory_path.read_bytes(), memory_bytes)
            self.assertEqual(knowledge_path.read_bytes(), knowledge_bytes)
            self.assertEqual(report.hashes["long_term_json"], self._hash(memory_path))
            self.assertEqual(report.hashes["knowledge_json"], self._hash(knowledge_path))

    def test_successful_verify_checks_database_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            database_path, backup_root, manifest_path = self._cutover_paths(directory)
            report = sqlite_cutover.cutover(
                memory_path,
                knowledge_path,
                database_path,
                backup_root,
                manifest_path,
            )

            verified = sqlite_cutover.verify_existing(
                database_path,
                report.paths["backup"],
            )

            self.assertEqual(verified.status, "PASS")
            self.assertEqual(verified.statuses["backup"], "validated")
            self.assertEqual(verified.counts, report.counts)

    def test_successful_cutover_publishes_validated_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            database_path, backup_root, manifest_path = self._cutover_paths(directory)

            report = sqlite_cutover.cutover(
                memory_path,
                knowledge_path,
                database_path,
                backup_root,
                manifest_path,
                timestamp="2026-08-02T12:00:00Z",
            )

            self.assertTrue(database_path.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(report.paths["backup"].is_file())
            self.assertTrue(report.paths["long_term_snapshot"].is_file())
            self.assertTrue(report.paths["knowledge_snapshot"].is_file())
            for snapshot_name in (
                "long_term_snapshot",
                "knowledge_snapshot",
            ):
                self.assertFalse(
                    report.paths[snapshot_name].stat().st_mode
                    & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
                )
            self.assertFalse(
                manifest_path.stat().st_mode
                & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
            )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            allowed_fields = {
                "timestamp",
                "schema_version",
                "migration_status",
                "backup_status",
                "source_file_hashes",
                "destination_database_hash",
                "row_counts",
                "application_version",
            }
            self.assertLessEqual(set(manifest), allowed_fields)
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["migration_status"], "validated")
            self.assertEqual(manifest["backup_status"], "validated")
            self.assertEqual(
                manifest["destination_database_hash"],
                self._hash(database_path),
            )
            self.assertEqual(manifest["row_counts"], report.counts)

    def test_interrupted_cutover_removes_partial_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            database_path, backup_root, manifest_path = self._cutover_paths(directory)

            def interrupted(source, destination):
                destination.write_bytes(b"partial")
                raise KeyboardInterrupt

            with patch.object(
                sqlite_cutover,
                "_publish_database",
                side_effect=interrupted,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    sqlite_cutover.cutover(
                        memory_path,
                        knowledge_path,
                        database_path,
                        backup_root,
                        manifest_path,
                        timestamp="2026-08-02T12:00:00Z",
                    )

            self.assertFalse(database_path.exists())
            self.assertFalse(manifest_path.exists())
            self.assertEqual(list(backup_root.iterdir()), [])

    def test_existing_database_is_refused_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            database_path, backup_root, manifest_path = self._cutover_paths(directory)
            database_path.write_bytes(b"existing database")
            original = database_path.read_bytes()

            with self.assertRaisesRegex(
                sqlite_cutover.CutoverError,
                "database_exists",
            ):
                sqlite_cutover.cutover(
                    memory_path,
                    knowledge_path,
                    database_path,
                    backup_root,
                    manifest_path,
                )

            self.assertEqual(database_path.read_bytes(), original)

    def test_existing_manifest_is_refused_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            database_path, backup_root, manifest_path = self._cutover_paths(directory)
            manifest_path.write_text("existing manifest", encoding="utf-8")
            original = manifest_path.read_bytes()

            with self.assertRaisesRegex(
                sqlite_cutover.CutoverError,
                "manifest_exists",
            ):
                sqlite_cutover.cutover(
                    memory_path,
                    knowledge_path,
                    database_path,
                    backup_root,
                    manifest_path,
                )

            self.assertEqual(manifest_path.read_bytes(), original)

    def test_malformed_json_fails_without_partial_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(
                directory,
                malformed=True,
            )
            database_path, backup_root, manifest_path = self._cutover_paths(directory)

            with self.assertRaisesRegex(
                sqlite_cutover.CutoverError,
                "migration_failed",
            ):
                sqlite_cutover.cutover(
                    memory_path,
                    knowledge_path,
                    database_path,
                    backup_root,
                    manifest_path,
                )

            self.assertFalse(database_path.exists())
            self.assertFalse(manifest_path.exists())
            self.assertEqual(list(backup_root.iterdir()), [])

    def test_validation_failure_rolls_back_cutover(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            database_path, backup_root, manifest_path = self._cutover_paths(directory)

            with patch.object(
                sqlite_cutover,
                "verify_database",
                side_effect=sqlite_cutover.CutoverError(
                    "database_validation_failed"
                ),
            ):
                with self.assertRaisesRegex(
                    sqlite_cutover.CutoverError,
                    "database_validation_failed",
                ):
                    sqlite_cutover.cutover(
                        memory_path,
                        knowledge_path,
                        database_path,
                        backup_root,
                        manifest_path,
                    )

            self.assertFalse(database_path.exists())
            self.assertFalse(manifest_path.exists())
            self.assertEqual(list(backup_root.iterdir()), [])

    def test_backup_failure_rolls_back_cutover(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            database_path, backup_root, manifest_path = self._cutover_paths(directory)

            with patch.object(
                sqlite_cutover,
                "backup_sqlite_database",
                side_effect=BackupError("private backup detail"),
            ):
                with self.assertRaisesRegex(
                    sqlite_cutover.CutoverError,
                    "backup_failed",
                ):
                    sqlite_cutover.cutover(
                        memory_path,
                        knowledge_path,
                        database_path,
                        backup_root,
                        manifest_path,
                    )

            self.assertFalse(database_path.exists())
            self.assertFalse(manifest_path.exists())
            self.assertEqual(list(backup_root.iterdir()), [])

    def test_cutover_can_retry_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            database_path, backup_root, manifest_path = self._cutover_paths(directory)
            timestamp = "2026-08-02T12:00:00Z"

            with patch.object(
                sqlite_cutover,
                "_write_manifest",
                side_effect=sqlite_cutover.CutoverError(
                    "manifest_publish_failed"
                ),
            ):
                with self.assertRaises(sqlite_cutover.CutoverError):
                    sqlite_cutover.cutover(
                        memory_path,
                        knowledge_path,
                        database_path,
                        backup_root,
                        manifest_path,
                        timestamp=timestamp,
                    )

            report = sqlite_cutover.cutover(
                memory_path,
                knowledge_path,
                database_path,
                backup_root,
                manifest_path,
                timestamp=timestamp,
            )
            self.assertEqual(report.status, "PASS")

    def test_json_hashes_and_original_bytes_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            memory_bytes = memory_path.read_bytes()
            knowledge_bytes = knowledge_path.read_bytes()
            database_path, backup_root, manifest_path = self._cutover_paths(directory)

            report = sqlite_cutover.cutover(
                memory_path,
                knowledge_path,
                database_path,
                backup_root,
                manifest_path,
            )

            self.assertEqual(memory_path.read_bytes(), memory_bytes)
            self.assertEqual(knowledge_path.read_bytes(), knowledge_bytes)
            self.assertEqual(
                report.hashes["long_term_json"],
                hashlib.sha256(memory_bytes).hexdigest(),
            )
            self.assertEqual(
                report.hashes["knowledge_json"],
                hashlib.sha256(knowledge_bytes).hexdigest(),
            )

    def test_no_private_values_appear_in_success_or_failure_output(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            output = io.StringIO()

            result = sqlite_cutover.main(
                [
                    "rehearse",
                    "--long-term-json",
                    str(memory_path),
                    "--knowledge-json",
                    str(knowledge_path),
                ],
                output=output,
            )

            self.assertEqual(result, 1)
            rendered = output.getvalue()
            self.assertIn("historical_schema_v1_tool_retired", rendered)
            for private_value in (
                "Gizli yaddaş",
                "Ömərin qeydi",
                "Ömər",
                "MK11",
            ):
                self.assertNotIn(private_value, rendered)

            memory_path.write_text('["LEAK-ME",', encoding="utf-8")
            output = io.StringIO()
            result = sqlite_cutover.main(
                [
                    "rehearse",
                    "--long-term-json",
                    str(memory_path),
                    "--knowledge-json",
                    str(knowledge_path),
                ],
                output=output,
            )
            self.assertEqual(result, 1)
            self.assertNotIn("LEAK-ME", output.getvalue())
            self.assertIn("STATUS FAIL", output.getvalue())

    def test_historical_cli_refuses_every_command(self):
        for command in ("rehearse", "verify", "cutover"):
            with self.subTest(command=command):
                output = io.StringIO()
                result = sqlite_cutover.main([command], output=output)
                self.assertEqual(result, 1)
                self.assertIn(
                    "historical_schema_v1_tool_retired",
                    output.getvalue(),
                )

    def test_migrated_data_is_complete_without_history(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path, knowledge_path = self._sources(directory)
            database_path, backup_root, manifest_path = self._cutover_paths(directory)
            sqlite_cutover.cutover(
                memory_path,
                knowledge_path,
                database_path,
                backup_root,
                manifest_path,
            )
            database = SQLiteDatabase(database_path, require_existing=True)

            self.assertEqual(
                SQLiteMemory(database).recall(),
                ["Gizli yaddaş", "Gizli yaddaş", "Ömərin qeydi"],
            )
            self.assertEqual(
                SQLiteKnowledge(database).load(),
                {"favorite_game": "MK11", "name": "Ömər"},
            )
            connection = database.connect()
            try:
                history_count = connection.execute(
                    "SELECT COUNT(*) FROM user_fact_history"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(history_count, 0)


if __name__ == "__main__":
    unittest.main()
