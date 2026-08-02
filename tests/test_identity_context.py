import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.nel import (
    IDENTITY_CONTEXT_MAX_CHARS,
    IDENTITY_PREFERENCE_CONTEXT_LIMIT,
    Nel,
)
from src.core.runtime import create_runtime_nel
from src.errors import ApplicationError, ProviderError
from src.identity import IdentityRepository, IdentityService
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.fact_migration import migrate_fact_schema_v3_to_v4
from src.persistence.repositories import SQLiteKnowledge, SQLiteMemory
from src.persistence.sqlite import SQLiteDatabase


def identity_context(prompt: str) -> dict:
    marker = "Nel identity snapshot (read-only):\n"
    payload = prompt.split(marker, 1)[1].split(
        "\n\nGoal snapshots",
        1,
    )[0]
    return json.loads(payload)


def user_facts_context(prompt: str) -> dict:
    marker = (
        "Structured user facts "
        "(authoritative; override conflicting long-term memories):\n"
    )
    payload = prompt.split(marker, 1)[1].split(
        "\n\nLong-term memories:",
        1,
    )[0]
    return json.loads(payload)


class PromptProvider:
    def __init__(self, responder=None):
        self.prompt = None
        self.responder = responder or (lambda _prompt: "cavab")

    def generate(self, prompt: str) -> str:
        if "Should this be stored as a long-term memory?" in prompt:
            return "no"
        self.prompt = prompt
        return self.responder(prompt)


class FailingProvider:
    def generate(self, _prompt: str) -> str:
        raise ProviderError("private provider detail")


class CountingIdentityService:
    def __init__(self, service):
        self.service = service
        self.snapshot_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        return self.service.snapshot()


class IdentityContextTests(unittest.TestCase):
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
            current_hash = hashlib.sha256(
                cls.production_path.read_bytes()
            ).hexdigest()
            if current_hash != cls.production_hash:
                raise AssertionError("Production database changed during tests.")

    def setUp(self):
        patcher = patch("src.core.nel.Clock.start")
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _database(directory):
        path = Path(directory) / "identity-context.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-02T00:00:00Z")
        migrate_identity_schema_v1_to_v2(
            database,
            "2026-08-02T01:00:00Z",
        )
        migrate_goal_schema_v2_to_v3(
            database,
            "2026-08-02T02:00:00Z",
        )
        migrate_fact_schema_v3_to_v4(
            database,
            "2026-08-02T00:00:03Z",
        )
        return path, database

    @staticmethod
    def _nel(database, provider, identity=None):
        identity = identity or IdentityService(IdentityRepository(database))
        return Nel(
            provider=provider,
            memory_repository=SQLiteMemory(database),
            knowledge_repository=SQLiteKnowledge(database),
            identity_service=identity,
        )

    def test_snapshot_appears_once_and_core_identity_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._database(directory)
            service = CountingIdentityService(
                IdentityService(IdentityRepository(database))
            )

            def respond(prompt):
                context = identity_context(prompt)
                if (
                    context["identity_id"] == "nel"
                    and context["display_name"] == "Nel"
                    and context["nature"] == "süni"
                    and context["role"]
                    and "already rendered for Azerbaijani" in prompt
                ):
                    return "Mən Neləm, süni rəqəmsal yoldaşam."
                return "Naməlumdur."

            provider = PromptProvider(respond)
            nel = self._nel(database, provider, service)
            try:
                response = nel.think("Öz kimliyini ətraflı təsvir et.")
            finally:
                nel.stop()

            context = identity_context(provider.prompt)
            self.assertEqual(service.snapshot_calls, 1)
            self.assertEqual(context["identity_id"], "nel")
            self.assertEqual(context["display_name"], "Nel")
            self.assertEqual(context["nature"], "süni")
            self.assertEqual(service.service.snapshot().nature, "artificial")
            self.assertTrue(context["role"])
            self.assertEqual(response, "Mən Neləm, süni rəqəmsal yoldaşam.")
            lowered = response.lower()
            self.assertNotIn("sənətə əsaslanan", lowered)
            self.assertNotIn("incəsənətlə bağlı", lowered)
            self.assertNotIn("artistic", lowered)

    def test_role_uses_natural_azerbaijani_first_person_predicate(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._database(directory)

            def respond(prompt):
                context = identity_context(prompt)
                required_rules = (
                    "natural first-person predicate agreement",
                    "Express the role directly as what Nel is",
                )
                if context["role"] and all(
                    rule in prompt for rule in required_rules
                ):
                    return "Mən Ömərin davamlı rəqəmsal yoldaşıyam."
                return "Mənim rolum Ömərin davamlı rəqəmsal yoldaşımdır."

            provider = PromptProvider(respond)
            nel = self._nel(database, provider)
            try:
                response = nel.think("Öz kimliyini ətraflı təsvir et.")
            finally:
                nel.stop()

            self.assertEqual(
                response,
                "Mən Ömərin davamlı rəqəmsal yoldaşıyam.",
            )
            self.assertNotIn(response, provider.prompt)
            self.assertNotIn(
                "Mənim rolum Ömərin davamlı rəqəmsal yoldaşımdır.",
                provider.prompt,
            )

    def test_user_facts_and_identity_do_not_cross_namespaces(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._database(directory)
            SQLiteKnowledge(database).set("display_name", "User alias")
            provider = PromptProvider()
            nel = self._nel(database, provider)
            try:
                nel.think("Adlar nədir?")
            finally:
                nel.stop()

            identity = identity_context(provider.prompt)
            facts = user_facts_context(provider.prompt)
            self.assertEqual(identity["display_name"], "Nel")
            self.assertEqual(facts["display_name"], "User alias")

    def test_absent_preference_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._database(directory)

            def respond(prompt):
                context = identity_context(prompt)
                if not context["established_preferences"]:
                    return "Hələ belə bir seçim formalaşdırmamışam."
                return "Bleach-i üstün tuturam."

            provider = PromptProvider(respond)
            nel = self._nel(database, provider)
            try:
                response = nel.think("Sənin ən sevdiyin anime hansıdır?")
            finally:
                nel.stop()

            self.assertEqual(
                response,
                "Hələ belə bir seçim formalaşdırmamışam.",
            )
            self.assertNotIn("Bleach", provider.prompt)

    def test_candidate_is_excluded_and_provisional_is_labeled(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._database(directory)
            service = IdentityService(IdentityRepository(database))
            service.create_preference_candidate(
                "candidate_only",
                "CANDIDATE_SECRET",
                source_kind="experiment",
                source_reference="context-test-1",
            )
            service.create_preference_candidate(
                "interface_style",
                "minimal",
                source_kind="experiment",
                source_reference="context-test-2",
            )
            service.transition_preference(
                "interface_style",
                "provisional",
                source_kind="experiment",
                source_reference="context-test-3",
            )
            provider = PromptProvider()
            nel = self._nel(database, provider, service)
            try:
                nel.think("Seçimlərin varmı?")
            finally:
                nel.stop()

            context = identity_context(provider.prompt)
            self.assertNotIn("CANDIDATE_SECRET", provider.prompt)
            self.assertEqual(context["established_preferences"], {})
            self.assertEqual(
                context["provisional_preferences"],
                {"interface_style": "minimal"},
            )
            self.assertIn(
                "Provisional preferences are labeled provisional",
                provider.prompt,
            )

    def test_established_preference_may_influence_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._database(directory)
            service = IdentityService(IdentityRepository(database))
            service.create_preference_candidate(
                "response_style",
                "concise",
                source_kind="manual",
                source_reference="context-test-4",
            )
            service.transition_preference(
                "response_style",
                "provisional",
                source_kind="manual",
                source_reference="context-test-5",
            )
            service.transition_preference(
                "response_style",
                "established",
                source_kind="manual",
                source_reference="context-test-6",
            )

            def respond(prompt):
                stored = identity_context(prompt)["established_preferences"]
                return stored.get("response_style", "not formed")

            provider = PromptProvider(respond)
            nel = self._nel(database, provider, service)
            try:
                response = nel.think("Cavab üslubun necədir?")
            finally:
                nel.stop()

            self.assertEqual(response, "concise")

    def test_user_statement_and_generated_output_cannot_mutate_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._database(directory)
            service = IdentityService(IdentityRepository(database))
            before = service.snapshot()
            provider = PromptProvider(lambda _prompt: "Mənim adım Kenpachidir.")
            nel = self._nel(database, provider, service)
            try:
                nel.think("Sənin adın Kenpachidir.")
            finally:
                nel.stop()

            self.assertEqual(service.snapshot(), before)

    def test_restart_preserves_identity_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _database = self._database(directory)
            first_provider = PromptProvider()
            first = create_runtime_nel(
                provider=first_provider,
                database_path=path,
            )
            try:
                first.think("Öz kimliyini ətraflı təsvir et.")
            finally:
                first.stop()

            second_provider = PromptProvider()
            second = create_runtime_nel(
                provider=second_provider,
                database_path=path,
            )
            try:
                second.think("Öz kimliyini ətraflı təsvir et.")
            finally:
                second.stop()

            self.assertEqual(
                identity_context(first_provider.prompt),
                identity_context(second_provider.prompt),
            )

    def test_provider_failure_leaves_identity_and_memory_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._database(directory)
            memory = SQLiteMemory(database)
            memory.remember("preserved")
            service = IdentityService(IdentityRepository(database))
            before_identity = service.snapshot()
            before_memory = memory.recall()
            nel = self._nel(database, FailingProvider(), service)
            try:
                with self.assertRaises(ApplicationError):
                    nel.think("Salam")
            finally:
                nel.stop()

            self.assertEqual(service.snapshot(), before_identity)
            self.assertEqual(memory.recall(), before_memory)

    def test_identity_context_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, database = self._database(directory)
            service = IdentityService(IdentityRepository(database))
            for index in range(IDENTITY_PREFERENCE_CONTEXT_LIMIT + 5):
                key = f"preference_{index:02d}"
                service.create_preference_candidate(
                    key,
                    "x" * 300,
                    source_kind="experiment",
                    source_reference=f"context-limit-{index}",
                )
                service.transition_preference(
                    key,
                    "provisional",
                    source_kind="experiment",
                    source_reference=f"context-limit-p-{index}",
                )
                service.transition_preference(
                    key,
                    "established",
                    source_kind="manual",
                    source_reference=f"context-limit-e-{index}",
                )
            provider = PromptProvider()
            nel = self._nel(database, provider, service)
            try:
                nel.think("Seçimlərin nədir?")
            finally:
                nel.stop()

            context = identity_context(provider.prompt)
            encoded = json.dumps(
                context,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            self.assertLessEqual(
                len(context["established_preferences"]),
                IDENTITY_PREFERENCE_CONTEXT_LIMIT,
            )
            self.assertLessEqual(len(encoded), IDENTITY_CONTEXT_MAX_CHARS)


if __name__ == "__main__":
    unittest.main()
