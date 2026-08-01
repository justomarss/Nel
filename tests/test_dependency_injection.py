import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.core.nel import Nel
from src.core.state import State
from src.errors import ApplicationError, ProviderError
from src.services.knowledge_service import KnowledgeService


class FakeProvider:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "Should this be stored as a long-term memory?" in prompt:
            return "no"
        return "foreground reply"


class FailingProvider:
    def generate(self, prompt: str) -> str:
        raise ProviderError("safe test failure")


class InMemoryMemoryRepository:
    def __init__(self):
        self.items = []

    def remember(self, text):
        self.items.append(text)

    def recall(self, limit=None):
        if limit is None:
            return list(self.items)
        if limit <= 0:
            return []
        return self.items[-limit:]


class AtomicKnowledgeRepository:
    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self.batches = []

    def set_many(self, facts):
        batch = [dict(fact) for fact in facts]
        self.batches.append(batch)
        for fact in batch:
            self.data[fact["key"]] = fact["value"]

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def load(self):
        return dict(self.data)


class LegacyKnowledgeRepository:
    def __init__(self):
        self.data = {}
        self.set_calls = []

    def set(self, key, value):
        self.set_calls.append((key, value))
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def load(self):
        return dict(self.data)


class DependencyInjectionTests(unittest.TestCase):
    def test_nel_rejects_missing_persistence_repositories(self):
        with self.assertRaisesRegex(
            ValueError,
            "Memory and knowledge repositories must be injected",
        ):
            Nel(provider=FakeProvider())

    @patch("src.core.nel.Clock.start")
    def test_injected_repositories_are_used_by_nel(self, _clock_start):
        provider = FakeProvider()
        memory = InMemoryMemoryRepository()
        knowledge = AtomicKnowledgeRepository({"name": "Ömər"})
        nel = Nel(
            provider=provider,
            memory_repository=memory,
            knowledge_repository=knowledge,
        )
        try:
            nel.remember("injected memory")
            response = nel.think("Salam")

            self.assertEqual(response, "foreground reply")
            self.assertEqual(memory.items, ["injected memory"])
            self.assertIn('"name": "Ömər"', provider.prompts[-1])
            self.assertIn("injected memory", provider.prompts[-1])
        finally:
            nel.stop()

    def test_knowledge_service_uses_atomic_set_many_when_available(self):
        repository = AtomicKnowledgeRepository()
        service = KnowledgeService(object(), repository=repository)
        service.extractor = SimpleNamespace(
            extract=lambda _text: {
                "favorite_anime": "AoT",
                "name": "Ömər",
            }
        )

        service.process("ignored")

        self.assertEqual(
            repository.batches,
            [[
                {
                    "key": "favorite_anime",
                    "value": "AoT",
                    "subject": "user",
                },
                {"key": "name", "value": "Ömər", "subject": "user"},
            ]],
        )

    @patch("src.core.nel.Clock.start")
    def test_injected_identity_service_is_retained(self, _clock_start):
        identity_service = object()
        nel = Nel(
            provider=FakeProvider(),
            memory_repository=InMemoryMemoryRepository(),
            knowledge_repository=AtomicKnowledgeRepository(),
            identity_service=identity_service,
        )
        try:
            self.assertIs(nel.identity, identity_service)
        finally:
            nel.stop()

    def test_knowledge_service_preserves_legacy_repository_contract(self):
        repository = LegacyKnowledgeRepository()
        service = KnowledgeService(object(), repository=repository)
        service.extractor = SimpleNamespace(
            extract=lambda _text: {"name": "Ömər", "favorite_game": "MK11"}
        )

        service.process("ignored")

        self.assertEqual(
            repository.set_calls,
            [("name", "Ömər"), ("favorite_game", "MK11")],
        )
        self.assertEqual(service.get("name"), "Ömər")
        self.assertEqual(
            service.facts(),
            {"name": "Ömər", "favorite_game": "MK11"},
        )

    @patch("src.core.nel.Clock.start")
    def test_injected_provider_failure_and_shutdown_behavior(self, _clock_start):
        nel = Nel(
            provider=FailingProvider(),
            memory_repository=InMemoryMemoryRepository(),
            knowledge_repository=AtomicKnowledgeRepository(),
        )

        with self.assertRaises(ApplicationError):
            nel.think("Salam")

        self.assertEqual(nel.state.get(), State.IDLE)
        nel.stop()
        nel.stop()


if __name__ == "__main__":
    unittest.main()
