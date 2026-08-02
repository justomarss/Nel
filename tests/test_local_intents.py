import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.brain.local_intent_classifier import IntentType, LocalIntentClassifier
from src.core.runtime import create_runtime_nel
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.sqlite import SQLiteDatabase


class RecordingProvider:
    def __init__(self, response="Adi söhbət cavabı"):
        self.response = response
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "Should this be stored as a long-term memory?" in prompt:
            return "no"
        return self.response


class LocalIntentClassifierTests(unittest.TestCase):
    def setUp(self):
        self.classifier = LocalIntentClassifier()

    def test_goal_list_phrases(self):
        phrases = (
            "Məqsədlərim nədir?",
            "Məqsədlərimi göstər.",
            "Mənim hədəflərim hansılardır?",
            "Nə məqsədlərim var?",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIs(
                    self.classifier.classify(phrase),
                    IntentType.GOAL_LIST,
                )

    def test_identity_phrases(self):
        for phrase in ("Sən kimsən?", "Adın nədir?", "Sən nəsan?"):
            with self.subTest(phrase=phrase):
                self.assertIs(
                    self.classifier.classify(phrase),
                    IntentType.IDENTITY_QUERY,
                )

    def test_user_fact_phrases(self):
        phrases = (
            "Mənim ən sevdiyim oyun nədir?",
            "Mənim ən sevdiyim rəng hansıdır?",
            "Mənim haqqında nə bilirsən?",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIs(
                    self.classifier.classify(phrase),
                    IntentType.USER_FACT_QUERY,
                )

    def test_case_punctuation_and_unicode_are_normalized(self):
        self.assertIs(
            self.classifier.classify("  MƏQSƏDLƏRİM... NƏDİR?!  "),
            IntentType.GOAL_LIST,
        )
        self.assertIs(
            self.classifier.classify("SƏN—KİMSƏN?!"),
            IntentType.IDENTITY_QUERY,
        )

    def test_unsupported_wording_and_false_positives_are_conversation(self):
        phrases = (
            "Bu gün hava necədir?",
            "Məqsəd sözünün mənası nədir?",
            "Sənin ən sevdiyin oyun nədir?",
            "Öz kimliyini ətraflı təsvir et.",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIs(
                    self.classifier.classify(phrase),
                    IntentType.CONVERSATION,
                )

    def test_goal_aspirations_require_explicit_command(self):
        phrases = (
            "Məqsədim C1 olmaqdır.",
            "Gələcəkdə Alman dilini öyrənmək istəyirəm.",
            "Mən istəyirəm ki, daha çox kitab oxuyum.",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIs(
                    self.classifier.classify(phrase),
                    IntentType.CONVERSATION,
                )
                self.assertTrue(
                    self.classifier.requires_explicit_goal_command(phrase)
                )


class LocalIntentIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protected_paths = tuple(
            path
            for path in (
                Path("memory/nel.sqlite3"),
                Path("memory/long_term.json"),
                Path("memory/knowledge.json"),
            )
            if path.is_file()
        )
        cls.protected_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in cls.protected_paths
        }

    @classmethod
    def tearDownClass(cls):
        for path, expected in cls.protected_hashes.items():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise AssertionError(f"Protected production data changed: {path}")

    def setUp(self):
        patcher = patch("src.core.nel.Clock.start")
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _runtime(directory, provider=None):
        path = Path(directory) / "local-intents.sqlite3"
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
        return path, create_runtime_nel(
            provider=provider or RecordingProvider(),
            database_path=path,
        )

    def test_goal_list_uses_local_service_without_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            _path, nel = self._runtime(directory, provider)
            try:
                nel.think(
                    '/goal create --title "C1 Alman dili" '
                    '--success "Ömər nəticəni qəbul edir"'
                )
                response = nel.think("Məqsədlərimi göstər.")
            finally:
                nel.stop()

        self.assertIn("C1 Alman dili", response)
        self.assertEqual(provider.prompts, [])

    def test_identity_query_uses_local_snapshot_without_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            _path, nel = self._runtime(directory, provider)
            before = nel.identity.snapshot()
            try:
                response = nel.think("Sən kimsən?")
                after = nel.identity.snapshot()
            finally:
                nel.stop()

        self.assertIn("Nel", response)
        self.assertIn("süni", response)
        self.assertIn("Ömərin davamlı rəqəmsal yoldaşı", response)
        self.assertEqual(before, after)
        self.assertEqual(provider.prompts, [])

    def test_user_fact_query_uses_local_knowledge_without_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            _path, nel = self._runtime(directory, provider)
            nel.knowledge.knowledge.set("favorite_game", "MK11")
            try:
                response = nel.think("Mənim ən sevdiyim oyun nədir?")
            finally:
                nel.stop()

        self.assertIn("favorite game: MK11", response)
        self.assertEqual(provider.prompts, [])

    def test_goal_aspiration_returns_clarification_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            _path, nel = self._runtime(directory, provider)
            try:
                response = nel.think("Məqsədim C1 olmaqdır.")
                goals = nel.goals.list_current()
            finally:
                nel.stop()

        self.assertIn("/goal create", response)
        self.assertEqual(goals, ())
        self.assertEqual(provider.prompts, [])

    def test_existing_goal_command_and_conversation_routes_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            _path, nel = self._runtime(directory, provider)
            try:
                goal_response = nel.think("/goal list")
                conversation_response = nel.think("Bu gün necəsən?")
            finally:
                nel.stop()

        self.assertIn("məqsəd yoxdur", goal_response)
        self.assertEqual(conversation_response, "Adi söhbət cavabı")
        self.assertGreaterEqual(len(provider.prompts), 1)


if __name__ == "__main__":
    unittest.main()
