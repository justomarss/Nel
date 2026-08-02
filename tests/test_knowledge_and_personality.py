import json
import tempfile
import unittest
from pathlib import Path

from src.brain.intent_classifier import IntentClassifier
from src.core.nel import Nel
from src.persistence.repositories import SQLiteKnowledge
from src.persistence.sqlite import SQLiteDatabase
from src.services.knowledge_service import KnowledgeService


def fact_response(text, key, value, confidence=0.99):
    value_start = text.index(value)
    return json.dumps(
        {
            "facts": [
                {
                    "key": key,
                    "value": value,
                    "subject": "user",
                    "confidence": confidence,
                    "source_start": 0,
                    "source_end": len(text),
                    "source_quote": text,
                    "value_start": value_start,
                    "value_end": value_start + len(value),
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
    def create_service(self, directory, *responses):
        provider = QueueProvider(*responses)
        brain = type("Brain", (), {"provider": provider})()
        database = SQLiteDatabase(Path(directory) / "knowledge.sqlite3")
        database.initialize("2026-08-02T00:00:00Z")
        service = KnowledgeService(
            brain,
            repository=SQLiteKnowledge(database),
        )
        return service, provider

    def test_provider_correction_is_proposed_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            text = "Mənim ən sevdiyim anime AoT-dir."
            service, _ = self.create_service(
                directory,
                fact_response(text, "favorite_anime", "AoT"),
            )
            service.correct_fact("favorite_anime", "Bleach", confirmed=True)

            proposals = service.process(text)

            self.assertEqual(service.facts(), {"favorite_anime": "Bleach"})
            self.assertEqual(proposals[0].candidate.value, "AoT")
            self.assertEqual(proposals[0].proposal_type.value, "correction")

    def test_favorite_game_preserves_literal_value(self):
        with tempfile.TemporaryDirectory() as directory:
            text = "Mənim ən sevdiyim oyun MK11-dir."
            service, _ = self.create_service(
                directory,
                fact_response(text, "favorite_game", "MK11"),
            )

            proposals = service.process(text)

            self.assertEqual(service.facts(), {})
            self.assertEqual(proposals[0].candidate.value, "MK11")

    def test_user_name_preserves_unicode_literal(self):
        with tempfile.TemporaryDirectory() as directory:
            text = "Mənim adım Ömərdir."
            service, _ = self.create_service(
                directory,
                fact_response(text, "name", "Ömər"),
            )

            proposals = service.process(text)

            self.assertEqual(service.facts(), {})
            self.assertEqual(proposals[0].candidate.value, "Ömər")

    def test_sentence_without_durable_fact_stores_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _ = self.create_service(
                directory,
                '{"facts": []}',
            )

            service.process("Bu gün hava haqqında düşünürəm.")

            stored = service.facts()
            self.assertEqual(stored, {})

    def test_malformed_json_is_rejected_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            service, provider = self.create_service(
                directory,
                "not JSON",
            )

            with self.assertLogs(
                "src.brain.knowledge_extractor",
                level="WARNING",
            ) as logs:
                service.process("Mənim adım Ömərdir.")

            stored = service.facts()
            self.assertEqual(stored, {})
            self.assertEqual(provider.calls, 1)
            self.assertIn("Knowledge candidate extraction rejected", logs.output[0])

    def test_prompt_prevents_unstored_nel_preference_claim(self):
        class State:
            def set(self, state):
                pass

        class Memory:
            def recall(self, limit=None):
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
        nel.raw_memory_context_limit = 20

        response = nel.think("Sənin ən sevdiyin anime hansıdır?")

        self.assertEqual(response, "Nel has not formed an anime preference yet.")
        self.assertNotIn("prefers Bleach", response)
        self.assertIn('"favorite_anime": "AoT"', nel.brain.prompt)

    def test_user_first_person_question_becomes_second_person_answer(self):
        class Brain:
            prompt = None

            def should_remember(self, prompt):
                return False

            def think(self, prompt):
                self.prompt = prompt
                required = (
                    'first-person forms such as "mən" and "mənim" refer to the user',
                    'address the user with informal second-person forms such as "sən" and "sənin"',
                    'Use "mən" and "mənim" in Nel\'s answer only for Nel\'s own identity or state',
                )
                if all(rule in prompt for rule in required):
                    return "Sənin ən sevdiyin oyun MK11-dir."
                return "Sizin ən sevdiyim oyun MK11-dir."

        nel = Nel.__new__(Nel)
        nel.state = type("State", (), {"set": lambda self, state: None})()
        nel.intent = IntentClassifier()
        nel.memory = type("Memory", (), {"recall": lambda self, limit=None: []})()
        nel.knowledge = type(
            "Knowledge",
            (),
            {
                "answer": lambda self, text: None,
                "facts": lambda self: {"favorite_game": "MK11"},
            },
        )()
        nel.brain = Brain()
        nel.raw_memory_context_limit = 20

        response = nel.think("Mənim ən sevdiyim oyun hansıdır?")

        self.assertEqual(response, "Sənin ən sevdiyin oyun MK11-dir.")
        rules = nel.brain.prompt.split("Rules:", 1)[1].split("User:", 1)[0]
        self.assertNotIn("anime", rules.casefold())
        self.assertNotIn("game", rules.casefold())
        self.assertNotIn("oyun", rules.casefold())

    def test_nel_identity_remains_first_person_in_answer(self):
        class Brain:
            def should_remember(self, prompt):
                return False

            def think(self, prompt):
                if (
                    'Use "mən" and "mənim" in Nel\'s answer only for '
                    "Nel's own identity or state"
                ) in prompt:
                    return "Mən Neləm."
                return "Sən Nel'sən."

        nel = Nel.__new__(Nel)
        nel.state = type("State", (), {"set": lambda self, state: None})()
        nel.intent = IntentClassifier()
        nel.memory = type("Memory", (), {"recall": lambda self, limit=None: []})()
        nel.knowledge = type(
            "Knowledge",
            (),
            {
                "answer": lambda self, text: None,
                "facts": lambda self: {},
            },
        )()
        nel.brain = Brain()
        nel.raw_memory_context_limit = 20

        self.assertEqual(nel.think("Sən kimsən?"), "Mən Neləm.")


if __name__ == "__main__":
    unittest.main()
