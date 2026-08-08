import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.runtime import create_runtime_nel
from src.persistence.fact_migration import migrate_fact_schema_v3_to_v4
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.sqlite import SQLiteDatabase
from src.response_authority import (
    AuthorityRequirement,
    ResponseAuthorityPlanner,
    ResponseMode,
    ResponseReason,
)


class ScriptedProvider:
    def __init__(self, responses=None, default="provider response"):
        self.responses = responses or {}
        self.default = default
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        user_text = prompt.split("\nUser:\n", 1)[1].split(
            "\n\nAssistant:\n",
            1,
        )[0]
        return self.responses.get(user_text, self.default)

    def generate_structured(self, _prompt, _schema, _schema_name):
        return '{"facts":[]}'


class BrokenPlanner:
    def plan(self, _user_input, _recent_snapshot):
        raise RuntimeError("planner unavailable")


class BrokenValidator:
    def validate_plan(self, _plan):
        raise RuntimeError("validator unavailable")

    def validate_provider_result(self, _plan, _response):
        raise RuntimeError("validator unavailable")


class ResponseAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.clock_patcher = patch("src.core.nel.Clock.start")
        self.clock_patcher.start()

    def tearDown(self):
        self.clock_patcher.stop()

    @staticmethod
    def runtime(directory, provider, **kwargs):
        path = Path(directory) / "response-authority.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-08T00:00:00Z")
        migrate_identity_schema_v1_to_v2(database, "2026-08-08T00:00:01Z")
        migrate_goal_schema_v2_to_v3(database, "2026-08-08T00:00:02Z")
        migrate_fact_schema_v3_to_v4(database, "2026-08-08T00:00:03Z")
        nel = create_runtime_nel(provider=provider, database_path=path)
        for key, value in kwargs.items():
            setattr(nel, key, value)
        return nel

    def test_planner_marks_only_authoritative_fact_followup_as_guarded(self):
        planner = ResponseAuthorityPlanner()
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            nel = self.runtime(directory, provider)
            try:
                nel.think('/fact set favorite_anime --value "AoT" --confirm')
                nel.think("Mənim ən sevdiyim anime hansıdır?")
                plan = planner.plan(
                    "Bəs Bleach?",
                    nel.conversation_session.snapshot(),
                )
            finally:
                nel.stop()

        self.assertIs(plan.mode, ResponseMode.CLARIFY)
        self.assertIs(
            plan.authority_requirement,
            AuthorityRequirement.STRUCTURED_REQUIRED,
        )
        self.assertIs(
            plan.reason_code,
            ResponseReason.AMBIGUOUS_PERSONAL_FOLLOWUP,
        )

    def test_guarded_followup_never_exposes_malicious_provider_fact(self):
        followup = "Bəs Bleach?"
        invention = "Sənin ən sevdiyin anime Bleach-dir."
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider({followup: invention})
            nel = self.runtime(directory, provider)
            try:
                nel.think('/fact set favorite_anime --value "AoT" --confirm')
                nel.think("Mənim ən sevdiyim anime hansıdır?")
                answer = nel.think(followup)
                facts = nel.knowledge.facts()
            finally:
                nel.stop()

        self.assertNotEqual(answer, invention)
        self.assertEqual(facts, {"favorite_anime": "AoT"})
        self.assertEqual(provider.prompts, [])

    def test_absent_personal_state_is_deterministic_and_does_not_call_provider(self):
        question = "Mən Gemini istifadə edirəm?"
        invention = "Bəli, sən Gemini istifadə edirsən."
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider({question: invention})
            nel = self.runtime(directory, provider)
            try:
                answer = nel.think(question)
                facts = nel.knowledge.facts()
                memories = nel.memory.recall()
            finally:
                nel.stop()

        self.assertNotEqual(answer, invention)
        self.assertEqual(provider.prompts, [])
        self.assertEqual(facts, {})
        self.assertEqual(memories, [])

    def test_general_question_remains_available_with_no_personal_state(self):
        question = "Gemini nədir?"
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider({question: "Gemini ümumi anlayışdır."})
            nel = self.runtime(directory, provider)
            try:
                answer = nel.think(question)
            finally:
                nel.stop()

        self.assertEqual(answer, "Gemini ümumi anlayışdır.")
        self.assertEqual(len(provider.prompts), 1)

    def test_mixed_personal_and_general_request_clarifies_without_provider(self):
        question = "Mən Bleach-i izləmişəm, Bleach nədir?"
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            nel = self.runtime(directory, provider)
            try:
                answer = nel.think(question)
            finally:
                nel.stop()

        self.assertIn("ayrı", answer)
        self.assertEqual(provider.prompts, [])

    def test_recent_personal_assertion_cannot_override_current_structured_fact(self):
        followup = "Bəs Bleach?"
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(
                {
                    "Mənim ən sevdiyim anime Bleach-dir.": "Qeyd etdim.",
                    followup: "Sənin ən sevdiyin anime Bleach-dir.",
                }
            )
            nel = self.runtime(directory, provider)
            try:
                nel.think('/fact set favorite_anime --value "AoT" --confirm')
                nel.think("Mənim ən sevdiyim anime Bleach-dir.")
                answer = nel.think(followup)
                facts = nel.knowledge.facts()
            finally:
                nel.stop()

        self.assertNotIn("Bleach-dir", answer)
        self.assertEqual(facts, {"favorite_anime": "AoT"})

    def test_planner_failure_fails_closed_for_recognized_personal_followup(self):
        followup = "Bəs Bleach?"
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider({followup: "Sənin seçimin Bleach-dir."})
            nel = self.runtime(directory, provider)
            try:
                nel.think('/fact set favorite_anime --value "AoT" --confirm')
                nel.think("Mənim ən sevdiyim anime hansıdır?")
                nel.response_authority_planner = BrokenPlanner()
                answer = nel.think(followup)
                facts = nel.knowledge.facts()
            finally:
                nel.stop()

        self.assertNotIn("Bleach-dir", answer)
        self.assertEqual(provider.prompts, [])
        self.assertEqual(facts, {"favorite_anime": "AoT"})

    def test_broken_validator_does_not_block_general_conversation(self):
        question = "Atom nədir?"
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider({question: "Atom maddənin hissəciyidir."})
            nel = self.runtime(directory, provider)
            nel.response_authority_validator = BrokenValidator()
            try:
                answer = nel.think(question)
            finally:
                nel.stop()

        self.assertEqual(answer, "Atom maddənin hissəciyidir.")
        self.assertEqual(len(provider.prompts), 1)


if __name__ == "__main__":
    unittest.main()
