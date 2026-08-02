import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.goals import (
    GoalCandidate,
    GoalOwner,
    GoalPolicyError,
    GoalRepository,
    GoalRepositoryError,
    GoalService,
    GoalState,
    GoalVersionConflict,
)
from src.identity import IdentityRepository, IdentityService
from src.persistence.backup import (
    BackupValidationError,
    backup_sqlite_database,
    verify_sqlite_backup,
)
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase


class SequentialClock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 1
        return f"2026-08-03T00:00:{self.value:02d}Z"


def user_candidate(**changes):
    values = {
        "title": "Azərbaycan dilini inkişaf etdirmək",
        "success_condition": "Ömər nəticəni açıq şəkildə qəbul edir",
        "owner": GoalOwner.USER,
        "source_kind": "validated_user",
        "source_reference": "conversation:create",
    }
    values.update(changes)
    return GoalCandidate(**values)


class GoalRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production_path = Path("memory/nel.sqlite3")
        cls.production_hash = (
            hashlib.sha256(cls.production_path.read_bytes()).hexdigest()
            if cls.production_path.is_file()
            else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls.production_hash is not None:
            current = hashlib.sha256(
                cls.production_path.read_bytes()
            ).hexdigest()
            if current != cls.production_hash:
                raise AssertionError("Production database changed during tests.")

    @staticmethod
    def _database(directory):
        path = Path(directory) / "goals.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-03T00:00:00Z")
        migrate_identity_schema_v1_to_v2(
            database,
            "2026-08-03T00:00:01Z",
        )
        migrate_goal_schema_v2_to_v3(
            database,
            "2026-08-03T00:00:02Z",
        )
        return path, database

    @classmethod
    def _service(cls, directory):
        path, database = cls._database(directory)
        repository = GoalRepository(database)
        service = GoalService(
            repository,
            clock=SequentialClock(),
            id_factory=lambda: "goal-001",
        )
        return path, database, repository, service

    @staticmethod
    def _create(service):
        return service.create(
            user_candidate(),
            explicit_user_approval=True,
            approval_reference="approval:create",
        )

    def test_create_read_list_and_no_hard_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, _database, repository, service = self._service(directory)

            created = self._create(service)

            self.assertEqual(created.goal_id, "goal-001")
            self.assertEqual(created.version, 1)
            self.assertEqual(created.state, GoalState.ACTIVE)
            self.assertEqual(service.get(created.goal_id), created)
            self.assertEqual(service.list_current(), (created,))
            self.assertFalse(hasattr(repository, "delete"))
            self.assertFalse(hasattr(service, "delete"))

    def test_service_rejects_untrusted_sources_without_repository_write(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, _database, _repository, service = self._service(directory)

            with self.assertRaises(GoalPolicyError):
                service.create(
                    user_candidate(source_kind="model_output"),
                    explicit_user_approval=True,
                    approval_reference="approval:model",
                )

            self.assertEqual(service.list_current(), ())

    def test_update_preserves_previous_version_in_history(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, _database, _repository, service = self._service(directory)
            created = self._create(service)

            updated = service.update(
                created.goal_id,
                {"title": "Unicode məqsəd yeniləndi"},
                expected_version=1,
                source_kind="validated_user",
                source_reference="conversation:update",
                explicit_user_approval=True,
                approval_reference="approval:update",
                revision_reason="Ömər başlığı dəyişdi",
            )

            self.assertEqual(updated.version, 2)
            self.assertEqual(updated.title, "Unicode məqsəd yeniləndi")
            history = service.history(created.goal_id)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].snapshot, created)
            self.assertEqual(history[0].snapshot.version, 1)

    def test_expected_version_conflict_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, _database, _repository, service = self._service(directory)
            created = self._create(service)
            first = service.update(
                created.goal_id,
                {"title": "First"},
                expected_version=1,
                source_kind="validated_user",
                source_reference="conversation:first",
                explicit_user_approval=True,
                approval_reference="approval:first",
                revision_reason="First revision",
            )

            with self.assertRaises(GoalPolicyError):
                service.update(
                    created.goal_id,
                    {"title": "Stale"},
                    expected_version=1,
                    source_kind="validated_user",
                    source_reference="conversation:stale",
                    explicit_user_approval=True,
                    approval_reference="approval:stale",
                    revision_reason="Stale revision",
                )

            self.assertEqual(service.get(created.goal_id), first)
            self.assertEqual(len(service.history(created.goal_id)), 1)

    def test_repository_detects_version_conflict_inside_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, _database, repository, service = self._service(directory)
            created = self._create(service)
            proposed = service.update(
                created.goal_id,
                {"title": "Version two"},
                expected_version=1,
                source_kind="validated_user",
                source_reference="conversation:two",
                explicit_user_approval=True,
                approval_reference="approval:two",
                revision_reason="Version two",
            )

            with self.assertRaises(GoalVersionConflict):
                repository._update(proposed, expected_version=1)
            self.assertEqual(repository.get(created.goal_id), proposed)
            self.assertEqual(len(repository.history(created.goal_id)), 1)

    def test_failure_after_history_insert_rolls_back_everything(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, _database, repository, service = self._service(directory)
            created = self._create(service)

            with patch.object(
                repository,
                "_write_current",
                side_effect=sqlite3.OperationalError("synthetic private failure"),
            ):
                with self.assertRaises(GoalRepositoryError):
                    service.update(
                        created.goal_id,
                        {"title": "Must roll back"},
                        expected_version=1,
                        source_kind="validated_user",
                        source_reference="conversation:rollback",
                        explicit_user_approval=True,
                        approval_reference="approval:rollback",
                        revision_reason="Rollback test",
                    )

            self.assertEqual(service.get(created.goal_id), created)
            self.assertEqual(service.history(created.goal_id), ())

    def test_terminal_goals_require_dedicated_reopen_or_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, _database, _repository, service = self._service(directory)
            created = self._create(service)
            completed = service.update(
                created.goal_id,
                {"state": GoalState.COMPLETED},
                expected_version=1,
                source_kind="validated_user",
                source_reference="conversation:complete",
                explicit_user_approval=True,
                approval_reference="approval:complete",
                revision_reason="Success condition accepted",
                success_condition_accepted=True,
            )

            with self.assertRaisesRegex(GoalPolicyError, "terminal"):
                service.update(
                    completed.goal_id,
                    {"state": GoalState.ACTIVE},
                    expected_version=2,
                    source_kind="validated_user",
                    source_reference="conversation:ordinary",
                    explicit_user_approval=True,
                    approval_reference="approval:ordinary",
                    revision_reason="Ordinary reopen is forbidden",
                )

            reopened = service.reopen(
                completed.goal_id,
                expected_version=2,
                source_reference="conversation:reopen",
                explicit_user_approval=True,
                approval_reference="approval:reopen",
                revision_reason="Ömər məqsədi yenidən açdı",
            )
            self.assertEqual(reopened.state, GoalState.ACTIVE)
            self.assertEqual(reopened.version, 3)
            self.assertEqual(
                [item.snapshot.version for item in service.history(created.goal_id)],
                [1, 2],
            )

    def test_cancelled_goal_can_only_use_dedicated_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, _database, _repository, service = self._service(directory)
            created = self._create(service)
            cancelled = service.update(
                created.goal_id,
                {"state": GoalState.CANCELLED},
                expected_version=1,
                source_kind="validated_user",
                source_reference="conversation:cancel",
                explicit_user_approval=True,
                approval_reference="approval:cancel",
                revision_reason="Ömər məqsədi ləğv etdi",
            )

            restored = service.restore(
                cancelled.goal_id,
                expected_version=2,
                source_reference="conversation:restore",
                explicit_user_approval=True,
                approval_reference="approval:restore",
                revision_reason="Ömər məqsədi bərpa etdi",
            )

            self.assertEqual(restored.state, GoalState.ACTIVE)
            self.assertEqual(restored.version, 3)
            self.assertEqual(len(service.history(created.goal_id)), 2)

    def test_goal_writes_preserve_other_namespaces(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database, _repository, service = self._service(directory)
            memory = SQLiteMemory(database)
            knowledge = SQLiteKnowledge(database)
            identity = IdentityService(IdentityRepository(database))
            memory.remember("Yaddaş: dəyişməməlidir")
            knowledge.set("name", "Ömər")
            before = (
                tuple(memory.recall()),
                knowledge.load(),
                identity.snapshot(),
            )

            created = self._create(service)
            service.update(
                created.goal_id,
                {"description": "Ayrı məqsəd namespace-i"},
                expected_version=1,
                source_kind="validated_user",
                source_reference="conversation:namespace",
                explicit_user_approval=True,
                approval_reference="approval:namespace",
                revision_reason="Namespace isolation test",
            )

            self.assertEqual(
                (
                    tuple(memory.recall()),
                    knowledge.load(),
                    identity.snapshot(),
                ),
                before,
            )

    def test_schema_v3_backup_and_isolated_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _database, _repository, service = self._service(directory)
            created = self._create(service)
            service.update(
                created.goal_id,
                {"title": "Bərpa edilən Unicode məqsəd"},
                expected_version=1,
                source_kind="validated_user",
                source_reference="conversation:backup",
                explicit_user_approval=True,
                approval_reference="approval:backup",
                revision_reason="Backup yoxlaması",
            )
            destination = Path(directory) / "goal-backup.sqlite3"

            result = backup_sqlite_database(path, destination)

            self.assertEqual(result.validation_status, "validated")
            self.assertTrue(verify_sqlite_backup(destination))
            restored = SQLiteDatabase(destination)
            connection = restored.connect()
            try:
                counts = tuple(
                    connection.execute(
                        "SELECT "
                        "(SELECT COUNT(*) FROM goals_current), "
                        "(SELECT COUNT(*) FROM goals_history)"
                    ).fetchone()
                )
                title = connection.execute(
                    "SELECT title FROM goals_current WHERE goal_id = ?",
                    (created.goal_id,),
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(counts, (1, 1))
            self.assertEqual(title, "Bərpa edilən Unicode məqsəd")

    def test_v3_backup_rejects_missing_goal_index(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database, _repository, _service = self._service(directory)
            with database.transaction() as connection:
                connection.execute("DROP INDEX goals_current_state_updated_idx")

            with self.assertRaisesRegex(BackupValidationError, "index"):
                verify_sqlite_backup(path)

    def test_v3_backup_rejects_goal_history_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database, _repository, service = self._service(directory)
            created = self._create(service)
            with database.transaction() as connection:
                connection.execute(
                    "UPDATE goals_current "
                    "SET version = 2, revision_reason = 'invalid gap' "
                    "WHERE goal_id = ?",
                    (created.goal_id,),
                )

            with self.assertRaisesRegex(BackupValidationError, "history"):
                verify_sqlite_backup(path)


if __name__ == "__main__":
    unittest.main()
