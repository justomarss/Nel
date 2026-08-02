import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.brain.knowledge_extractor import is_interrogative_user_input
from src.core.runtime import create_runtime_nel
from src.identity import IdentityRepository, IdentityService
from src.goals import GoalCandidate, GoalOwner, GoalPriority, GoalRepository, GoalService
from src.persistence.backup import backup_sqlite_database, verify_sqlite_backup
from src.persistence.fact_migration import (
    FactMigrationError,
    migrate_fact_schema_v3_to_v4,
)
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import FACT_SCHEMA_VERSION, SQLiteDatabase
from src.services.fact_commands import FactCommandHandler, readable_fact_label
from src.services.knowledge_service import KnowledgeService


class QueueProvider:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = 0

    def generate_structured(self, _prompt, _schema, _schema_name):
        self.calls += 1
        return next(self.responses)


class NoProvider:
    def generate_structured(self, *_args):
        raise AssertionError("Fact commands must not call the provider.")


class RecordingProvider:
    def __init__(self, response="Söhbət cavabı"):
        self.response = response
        self.prompts = []
        self.structured_calls = 0

    def generate(self, prompt):
        self.prompts.append(prompt)
        if "Should this be stored as a long-term memory?" in prompt:
            return "no"
        return self.response

    def generate_structured(self, *_args):
        self.structured_calls += 1
        return '{"facts": []}'


def fact_response(key, value):
    return json.dumps(
        {
            "facts": [
                {
                    "key": key,
                    "value": value,
                    "subject": "user",
                    "confidence": 1.0,
                }
            ]
        },
        ensure_ascii=False,
    )


class FactV4Tests(unittest.TestCase):
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
            actual = hashlib.sha256(cls.production_path.read_bytes()).hexdigest()
            if actual != cls.production_hash:
                raise AssertionError("Production database changed during tests.")

    @staticmethod
    def _v3(directory):
        path = Path(directory) / "facts.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        SQLiteMemory(database).remember("Unicode memory: Ömər")
        knowledge = SQLiteKnowledge(database)
        knowledge.set("favorite_color", "Göy")
        knowledge.set("favorite_color", "Yaşıl")
        migrate_identity_schema_v1_to_v2(
            database,
            "2026-08-02T00:00:01Z",
        )
        identity = IdentityService(IdentityRepository(database))
        identity.create_preference_candidate(
            "test_preference",
            "Azərbaycan dili",
            source_kind="experiment",
            source_reference="fact-v4-test",
        )
        migrate_goal_schema_v2_to_v3(
            database,
            "2026-08-02T00:00:02Z",
        )
        goals = GoalService(GoalRepository(database))
        goals.create(
            GoalCandidate(
                title="Unicode məqsəd",
                success_condition="Ömər qəbul edir",
                owner=GoalOwner.USER,
                priority=GoalPriority.NORMAL,
                source_kind="validated_user",
                source_reference="fact-v4-test",
            ),
            explicit_user_approval=True,
            approval_reference="fact-v4-test",
        )
        return path, database

    @staticmethod
    def _rows(database):
        connection = database.connect()
        try:
            tables = (
                "memory_events",
                "user_facts_current",
                "user_fact_history",
                "nel_identity_current",
                "nel_identity_history",
                "goals_current",
                "goals_history",
            )
            return {
                table: tuple(
                    tuple(row)
                    for row in connection.execute(
                        f"SELECT * FROM {table} ORDER BY rowid"
                    )
                )
                for table in tables
            }
        finally:
            connection.close()

    def _v4_service(self, directory, provider=None):
        path, database = self._v3(directory)
        before = self._rows(database)
        migrate_fact_schema_v3_to_v4(database, "2026-08-02T00:00:03Z")
        service = KnowledgeService(
            type("Brain", (), {"provider": provider or NoProvider()})(),
            SQLiteKnowledge(database),
        )
        return path, database, service, before

    def test_v3_to_v4_migration_is_exact_and_preserves_namespaces(self):
        with tempfile.TemporaryDirectory() as directory:
            path, database = self._v3(directory)
            before = self._rows(database)
            changed = migrate_fact_schema_v3_to_v4(database)

            self.assertTrue(changed)
            self.assertEqual(database.current_schema_version(), 4)
            guarded = SQLiteDatabase(path, require_existing=True)
            guarded.validate_existing(FACT_SCHEMA_VERSION)
            connection = database.connect()
            try:
                tables = {
                    row["name"]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_schema WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    )
                }
                current = tuple(
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(user_facts_current)"
                    )
                )
                states = tuple(
                    row[0]
                    for row in connection.execute(
                        "SELECT fact_state FROM user_facts_current"
                    )
                )
            finally:
                connection.close()
            self.assertEqual(len(tables), 8)
            self.assertEqual(current[-2:], ("fact_state", "revision_reason"))
            self.assertTrue(all(state == "active" for state in states))
            after = self._rows(database)
            for table in (
                "memory_events",
                "nel_identity_current",
                "nel_identity_history",
                "goals_current",
                "goals_history",
            ):
                self.assertEqual(after[table], before[table])

    def test_migration_rerun_is_no_op_and_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._v3(directory)
            with patch(
                "src.persistence.fact_migration.FACT_RETIREMENT_COLUMNS",
                ("fact_state TEXT NOT NULL DEFAULT 'active'", "invalid SQL"),
            ):
                with self.assertRaises(FactMigrationError):
                    migrate_fact_schema_v3_to_v4(database)
            self.assertEqual(database.current_schema_version(), 3)
            connection = database.connect()
            try:
                columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(user_facts_current)"
                    )
                }
            finally:
                connection.close()
            self.assertNotIn("fact_state", columns)

            self.assertTrue(migrate_fact_schema_v3_to_v4(database))
            self.assertFalse(migrate_fact_schema_v3_to_v4(database))

    def test_correction_history_same_value_retirement_and_reactivation(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _database, service, _before = self._v4_service(directory)
            self.assertFalse(
                service.correct_fact("favorite_color", "Yaşıl", confirmed=True)
            )
            self.assertTrue(
                service.correct_fact("favorite_color", "Qırmızı", confirmed=True)
            )
            self.assertTrue(
                service.retire_fact(
                    "favorite_color",
                    confirmed=True,
                    reason="İstifadəçi düzəlişi",
                )
            )
            self.assertIsNone(service.get("favorite_color"))
            self.assertEqual(service.facts(), {})
            self.assertTrue(
                service.correct_fact("favorite_color", "Bənövşəyi", confirmed=True)
            )
            versions = service.history("favorite_color")
            self.assertEqual([item.version for item in versions], [1, 2, 3, 4, 5])
            self.assertEqual(versions[-2].fact_state, "retired")
            self.assertEqual(versions[-2].revision_reason, "İstifadəçi düzəlişi")
            self.assertEqual(versions[-1].value, "Bənövşəyi")
            self.assertEqual(versions[-1].fact_state, "active")

            reopened = KnowledgeService(
                type("Brain", (), {"provider": NoProvider()})(),
                SQLiteKnowledge(SQLiteDatabase(path)),
            )
            self.assertEqual(reopened.get("favorite_color"), "Bənövşəyi")
            self.assertEqual(len(reopened.history("favorite_color")), 5)

    def test_fact_commands_are_confirmed_local_and_unicode_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, _database, service, _before = self._v4_service(directory)
            handler = FactCommandHandler(service)
            listing = handler.execute("/fact list")
            rejected_set = handler.execute(
                '/fact set favorite_color --value "Çəhrayı"'
            )
            changed = handler.execute(
                '/fact set favorite_color --value "Çəhrayı" --confirm'
            )
            history = handler.execute("/fact history favorite_color")
            rejected_retire = handler.execute(
                '/fact retire favorite_color --reason "Səhv fakt"'
            )
            retired = handler.execute(
                '/fact retire favorite_color --confirm --reason "Səhv fakt"'
            )

            self.assertIn("favorite color", listing)
            self.assertIn("--confirm", rejected_set)
            self.assertEqual(changed, "Fakt yeniləndi.")
            self.assertIn("Çəhrayı", history)
            self.assertIn("--confirm", rejected_retire)
            self.assertEqual(retired, "Fakt istifadədən çıxarıldı.")
            self.assertEqual(readable_fact_label("unknown__key-2"), "unknown key 2")

    def test_v4_backup_and_isolated_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _database, service, _before = self._v4_service(directory)
            service.retire_fact(
                "favorite_color",
                confirmed=True,
                reason="Unicode səbəb",
            )
            destination = root / "backup.sqlite3"
            result = backup_sqlite_database(path, destination)
            self.assertEqual(result.validation_status, "validated")
            self.assertTrue(verify_sqlite_backup(destination))


class InterrogativeGuardTests(unittest.TestCase):
    def test_questions_are_rejected_without_provider_calls(self):
        questions = (
            "Mənim nə məqsədlərim var?",
            "Mənim ən sevdiyim oyun hansıdır?",
            "Nə məqsədlərim var",
            "Ən sevdiyim oyun hansıdır",
            "Kimdir",
        )
        for question in questions:
            with self.subTest(question=question):
                provider = QueueProvider()
                with tempfile.TemporaryDirectory() as directory:
                    database = SQLiteDatabase(Path(directory) / "guard.sqlite3")
                    database.initialize()
                    service = KnowledgeService(
                        type("Brain", (), {"provider": provider})(),
                        SQLiteKnowledge(database),
                    )
                    service.process(question)
                    self.assertEqual(service.facts(), {})
                    self.assertEqual(provider.calls, 0)

    def test_declarative_counterexamples_reach_extraction(self):
        cases = (
            (
                "Nə vaxtsa Türkiyədə yaşamışam.",
                "former_residence",
                "Türkiyə",
            ),
            (
                "Mən nəhayət Alman dilinə başladım.",
                "started_language",
                "Alman dili",
            ),
        )
        for text, key, value in cases:
            with self.subTest(text=text):
                provider = QueueProvider(fact_response(key, value))
                with tempfile.TemporaryDirectory() as directory:
                    database = SQLiteDatabase(Path(directory) / "guard.sqlite3")
                    database.initialize()
                    service = KnowledgeService(
                        type("Brain", (), {"provider": provider})(),
                        SQLiteKnowledge(database),
                    )
                    service.process(text)
                    self.assertEqual(service.facts(), {key: value})
                    self.assertEqual(provider.calls, 1)
                    self.assertFalse(is_interrogative_user_input(text))

    def test_explicit_declarative_fact_still_works(self):
        provider = QueueProvider(fact_response("name", "Ömər"))
        with tempfile.TemporaryDirectory() as directory:
            database = SQLiteDatabase(Path(directory) / "guard.sqlite3")
            database.initialize()
            service = KnowledgeService(
                type("Brain", (), {"provider": provider})(),
                SQLiteKnowledge(database),
            )
            service.process("Mənim adım Ömərdir.")
            self.assertEqual(service.facts(), {"name": "Ömər"})


class FactCommandRuntimeTests(unittest.TestCase):
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
            actual = hashlib.sha256(cls.production_path.read_bytes()).hexdigest()
            if actual != cls.production_hash:
                raise AssertionError("Production database changed during tests.")

    def setUp(self):
        patcher = patch("src.core.nel.Clock.start")
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _runtime(directory, provider=None):
        path = Path(directory) / "fact-runtime.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        migrate_identity_schema_v1_to_v2(
            database,
            "2026-08-02T00:00:01Z",
        )
        migrate_goal_schema_v2_to_v3(
            database,
            "2026-08-02T00:00:02Z",
        )
        migrate_fact_schema_v3_to_v4(
            database,
            "2026-08-02T00:00:03Z",
        )
        return path, create_runtime_nel(
            provider=provider or RecordingProvider(),
            database_path=path,
        )

    def test_commands_route_locally_through_knowledge_service(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            _path, nel = self._runtime(directory, provider)
            try:
                created = nel.think(
                    '/fact set preferred_language --value "Azərbaycan dili" '
                    "--confirm"
                )
                listing = nel.think("/fact list")
                corrected = nel.think(
                    '/fact set preferred_language --value "Türk dili" '
                    "--confirm"
                )
                history = nel.think("/fact history preferred_language")
            finally:
                nel.stop()

        self.assertEqual(created, "Fakt yeniləndi.")
        self.assertIn("Azərbaycan dili", listing)
        self.assertEqual(corrected, "Fakt yeniləndi.")
        self.assertIn("Azərbaycan dili", history)
        self.assertIn("Türk dili", history)
        self.assertEqual(provider.prompts, [])
        self.assertEqual(provider.structured_calls, 0)

    def test_retirement_is_excluded_and_reactivation_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            path, first = self._runtime(directory, provider)
            try:
                first.think('/fact set display_note --value "Köhnə" --confirm')
                retired = first.think(
                    '/fact retire display_note --confirm '
                    '--reason "İstifadəçi düzəlişi"'
                )
                local_read = first.think("Mənim haqqında nə bilirsən?")
                conversation = first.think("Bu gün necə davam edək")
                final_prompt = provider.prompts[-1]
                first.think('/fact set display_note --value "Yeni" --confirm')
            finally:
                first.stop()

            second_provider = RecordingProvider()
            second = create_runtime_nel(
                provider=second_provider,
                database_path=path,
            )
            try:
                value = second.knowledge.get("display_note")
                history = second.think("/fact history display_note")
            finally:
                second.stop()

        self.assertEqual(retired, "Fakt istifadədən çıxarıldı.")
        self.assertNotIn("Köhnə", local_read)
        self.assertEqual(conversation, "Söhbət cavabı")
        structured = final_prompt.split(
            "Structured user facts (authoritative; override conflicting long-term memories):\n",
            1,
        )[1].split("\n\nLong-term memories:", 1)[0]
        self.assertNotIn("display_note", structured)
        self.assertEqual(value, "Yeni")
        self.assertIn("retired", history)
        self.assertEqual(second_provider.prompts, [])

    def test_malformed_commands_clarify_without_provider_or_write(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            _path, nel = self._runtime(directory, provider)
            try:
                responses = (
                    nel.think('/fact set name --value "Ömər"'),
                    nel.think('/fact retire name --reason "Səhv"'),
                    nel.think("/fact history"),
                )
                facts = nel.knowledge.facts()
            finally:
                nel.stop()

        self.assertTrue(all("natamamdır" in item for item in responses))
        self.assertEqual(facts, {})
        self.assertEqual(provider.prompts, [])
        self.assertEqual(provider.structured_calls, 0)

    def test_question_guard_and_provider_output_cannot_mutate_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider(
                response='/fact set injected --value "bad" --confirm'
            )
            _path, nel = self._runtime(directory, provider)
            try:
                nel.think("Mənim nə məqsədlərim var?")
                after_question = nel.knowledge.facts()
                response = nel.think("Adi söhbət")
                after_output = nel.knowledge.facts()
            finally:
                nel.stop()

        self.assertEqual(after_question, {})
        self.assertEqual(provider.structured_calls, 0)
        self.assertTrue(response.startswith("/fact set"))
        self.assertEqual(after_output, {})


if __name__ == "__main__":
    unittest.main()
