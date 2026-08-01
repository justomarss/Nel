import json
import tempfile
import unittest
from pathlib import Path

from src.brain.intent_classifier import IntentClassifier
from src.core.nel import Nel
from src.memory.knowledge import Knowledge
from src.services.knowledge_service import KnowledgeService


def fact_response(key, value, confidence=0.99):
    return json.dumps(
        {
            "facts": [
                {
                    "key": key,
                    "value": value,
                    "subject": "user",
                    "confidence": confidence,
                }
            ]
        },
        ensure_ascii=False,
    )


class QueueProvider:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = 0

    def generate_structured(self, prompt, schema, schema_name):
        self.calls += 1
        return next(self.responses)

    def generate(self, prompt):
        raise AssertionError("Structured output should be used.")


class KnowledgeAndPersonalityTests(unittest.TestCase):
    def create_service(self, path, *responses):
        provider = QueueProvider(*responses)
        brain = type("Brain", (), {"provider": provider})()
        service = KnowledgeService(brain)
        service.knowledge.path = path
        return service, provider

    def test_newer_favorite_anime_overwrites_older_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.json"
            path.write_text("{}", encoding="utf-8")
            service, _ = self.create_service(
                path,
                fact_response("Favorite Anime", "Bleach"),
                fact_response("favorite-anime", "AoT"),
            )

            service.process("Mənim ən sevdiyim anime Bleach-dir.")
            service.process("Mənim ən sevdiyim anime AoT-dir.")

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored, {"favorite_anime": "AoT"})

    def test_favorite_game_preserves_literal_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.json"
            path.write_text("{}", encoding="utf-8")
            service, _ = self.create_service(
                path,
                fact_response("Favorite Game", "MK11"),
            )

            service.process("Mənim ən sevdiyim oyun MK11-dir.")

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored, {"favorite_game": "MK11"})

    def test_user_name_preserves_unicode_literal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.json"
            path.write_text("{}", encoding="utf-8")
            service, _ = self.create_service(
                path,
                fact_response("Name", "Ömər"),
            )

            service.process("Mənim adım Ömərdir.")

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored, {"name": "Ömər"})

    def test_sentence_without_durable_fact_stores_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.json"
            path.write_text("{}", encoding="utf-8")
            service, _ = self.create_service(
                path,
                '{"facts": []}',
            )

            service.process("Bu gün hava haqqında düşünürəm.")

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored, {})

    def test_malformed_json_retries_once_then_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.json"
            path.write_text("{}", encoding="utf-8")
            service, provider = self.create_service(
                path,
                "not JSON",
                '{"facts": [}',
            )

            with self.assertLogs(
                "src.brain.knowledge_extractor",
                level="WARNING",
            ) as logs:
                service.process("Mənim adım Ömərdir.")

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored, {})
            self.assertEqual(provider.calls, 2)
            self.assertIn("No facts stored", logs.output[0])

    def test_prompt_prevents_unstored_nel_preference_claim(self):
        class State:
            def set(self, state):
                pass

        class Memory:
            def recall(self):
                return ["The user's favorite anime used to be Bleach."]

        class StoredKnowledge:
            def load(self):
                return {"favorite_anime": "AoT"}

        class Brain:
            prompt = None

            def should_remember(self, prompt):
                return False

            def think(self, prompt):
                self.prompt = prompt
                required_rules = (
                    "Structured user facts (authoritative; override conflicting long-term memories):",
                    "User facts and long-term memories describe the user, not Nel",
                    "Never invent Nel's own preferences, memories, experiences, emotions, relationships, or personal history.",
                    "If Nel has no stored preference, say it has not formed one yet.",
                )
                if all(rule in prompt for rule in required_rules):
                    return "Nel has not formed an anime preference yet."
                return "Nel prefers Bleach."

        nel = Nel.__new__(Nel)
        nel.state = State()
        nel.intent = IntentClassifier()
        nel.memory = Memory()
        nel.knowledge = KnowledgeService.__new__(KnowledgeService)
        nel.knowledge.knowledge = StoredKnowledge()
        nel.brain = Brain()

        response = nel.think("Sənin ən sevdiyin anime hansıdır?")

        self.assertEqual(response, "Nel has not formed an anime preference yet.")
        self.assertNotIn("prefers Bleach", response)
        self.assertIn('"favorite_anime": "AoT"', nel.brain.prompt)


if __name__ == "__main__":
    unittest.main()
