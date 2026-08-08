import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.brain.local_intent_classifier import IntentType, LocalIntentClassifier
from src.core.runtime import create_runtime_nel
from src.errors import ApplicationError, ProviderError
from src.persistence.fact_migration import migrate_fact_schema_v3_to_v4
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.sqlite import SQLiteDatabase
from tests.context_helpers import unified_context


GOAL_TITLE = "C1 Alman dili"
GOAL_CREATE = (
    '/goal create --title "C1 Alman dili" '
    '--success "C1 səviyyəsi təsdiqlənir"'
)
CONTINUITY_LIMITS_PENDING_ADR = (
    "Conversation Continuity v1 turn and character limits require an accepted ADR."
)
CONTINUITY_EVICTION_PENDING_ADR = (
    "Conversation Continuity v1 eviction policy requires accepted ADR limits."
)


def provider_user_message(prompt):
    return prompt.split("\nUser:\n", 1)[1].split("\n\nAssistant:\n", 1)[0]


class ScriptedProvider:
    def __init__(self, responses=None, default="Provayder cavabı"):
        self.responses = responses or {}
        self.default = default
        self.prompts = []
        self.structured_prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.responses.get(provider_user_message(prompt), self.default)

    def generate_structured(self, prompt, schema, schema_name):
        self.structured_prompts.append((prompt, schema, schema_name))
        return '{"facts":[]}'


class FailingProvider(ScriptedProvider):
    def generate(self, prompt):
        self.prompts.append(prompt)
        raise ProviderError("simulated provider failure")


class ConversationRegressionTestCase(unittest.TestCase):
    protected_paths = (
        Path("memory/nel.sqlite3"),
        Path("memory/long_term.json"),
        Path("memory/knowledge.json"),
    )

    @classmethod
    def setUpClass(cls):
        cls.protected_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in cls.protected_paths
            if path.is_file()
        }

    @classmethod
    def tearDownClass(cls):
        for path, expected in cls.protected_hashes.items():
            if not path.is_file():
                raise AssertionError(f"Protected production data removed: {path}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise AssertionError(f"Protected production data changed: {path}")

    def setUp(self):
        clock_patcher = patch("src.core.nel.Clock.start")
        clock_patcher.start()
        self.addCleanup(clock_patcher.stop)

    @staticmethod
    def runtime(directory, provider=None):
        path = Path(directory) / "conversation-regressions.sqlite3"
        database = SQLiteDatabase(path)
        database.initialize("2026-08-08T00:00:00Z")
        migrate_identity_schema_v1_to_v2(database, "2026-08-08T00:00:01Z")
        migrate_goal_schema_v2_to_v3(database, "2026-08-08T00:00:02Z")
        migrate_fact_schema_v3_to_v4(database, "2026-08-08T00:00:03Z")
        return create_runtime_nel(
            provider=provider or ScriptedProvider(),
            database_path=path,
        )

    def set_authoritative_fact(self, nel, key, value):
        provider_calls = len(nel.brain.provider.prompts)
        nel.think(f'/fact set {key} --value "{value}" --confirm')
        self.assertEqual(nel.knowledge.facts().get(key), value)
        self.assertEqual(len(nel.brain.provider.prompts), provider_calls)


class DeterministicArchitectureCharacterizationTests(
    ConversationRegressionTestCase
):
    def test_current_characterization_a_phrase_table_mismatch_is_deterministic(self):
        # This exact phrase-table mismatch is the reproducible A routing bug.
        phrases = {
            "Məqsədlərim nədir?": IntentType.GOAL_LIST,
            "Nə məqsədlərim var?": IntentType.GOAL_LIST,
            "Mənim nə məqsədlərim var?": IntentType.CONVERSATION,
            "Hansı məqsədlərim var?": IntentType.CONVERSATION,
            "Mənim hansı məqsədlərim var?": IntentType.CONVERSATION,
        }
        classifier = LocalIntentClassifier()

        for phrase, expected in phrases.items():
            with self.subTest(phrase=phrase):
                self.assertIs(classifier.classify(phrase), expected)

        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(default="Provayder məqsəd cavabı")
            nel = self.runtime(directory, provider)
            try:
                nel.think(GOAL_CREATE)
                responses = {phrase: nel.think(phrase) for phrase in phrases}
            finally:
                nel.stop()

        self.assertIn(GOAL_TITLE, responses["Məqsədlərim nədir?"])
        self.assertIn(GOAL_TITLE, responses["Nə məqsədlərim var?"])
        for phrase in tuple(phrases)[2:]:
            self.assertEqual(responses[phrase], "Provayder məqsəd cavabı")
        self.assertEqual(
            [provider_user_message(prompt) for prompt in provider.prompts],
            list(tuple(phrases)[2:]),
        )

    def test_current_characterization_a_hard_negatives_remain_non_list_routes(self):
        # These may converse or clarify, but must never be treated as goal lists.
        classifier = LocalIntentClassifier()
        phrases = (
            "Məqsədim C1 olmaqdır.",
            "Məqsədlər haqqında danışaq.",
            "Məqsəd qoymaq faydalıdırmı?",
        )

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIs(
                    classifier.classify(phrase),
                    IntentType.CONVERSATION,
                )
        self.assertTrue(classifier.requires_explicit_goal_command(phrases[0]))
        self.assertFalse(classifier.requires_explicit_goal_command(phrases[1]))
        self.assertFalse(classifier.requires_explicit_goal_command(phrases[2]))

    def test_current_characterization_b1_anime_fact_is_omitted_for_followup(self):
        self._assert_authoritative_fact_omitted(
            "favorite_anime",
            "AoT",
            "Bəs Bleach?",
        )

    def test_current_characterization_b1_game_fact_is_omitted_for_followup(self):
        self._assert_authoritative_fact_omitted(
            "favorite_game",
            "MK11",
            "Bəs GTA?",
        )

    def _assert_authoritative_fact_omitted(self, key, value, followup):
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            nel = self.runtime(directory, provider)
            self.set_authoritative_fact(nel, key, value)
            try:
                nel.think(followup)
                facts = nel.knowledge.facts()
            finally:
                nel.stop()

        context = unified_context(provider.prompts[-1])
        self.assertEqual(facts, {key: value})
        self.assertEqual(context["user_facts"], [])
        self.assertNotIn(f'"key":"{key}"', provider.prompts[-1])
        self.assertNotIn(f'"value":"{value}"', provider.prompts[-1])

    def test_current_characterization_c_song_turns_have_no_prior_context(self):
        turns = (
            "Bir mahnı yaz mənim üçün.",
            "Kədərli olsun.",
            "Davam et.",
        )
        prompts, memories = self._run_turns(turns)

        self.assertEqual(
            [provider_user_message(prompt) for prompt in prompts],
            list(turns),
        )
        self.assertNotIn(turns[0], prompts[1])
        self.assertNotIn(turns[0], prompts[2])
        self.assertNotIn(turns[1], prompts[2])
        self.assertEqual(memories, [])

    def test_current_characterization_c_formalasdir_has_no_song_context(self):
        turns = ("Bir mahnı yaz mənim üçün.", "formalaşdır")
        prompts, memories = self._run_turns(turns)

        self.assertEqual(provider_user_message(prompts[1]), turns[1])
        self.assertNotIn(turns[0], prompts[1])
        self.assertEqual(memories, [])

    def test_current_characterization_c_topic_followup_has_no_prior_topic(self):
        turns = ("Bleach haqqında danış.", "Bəs HxH?")
        prompts, memories = self._run_turns(turns)

        self.assertEqual(provider_user_message(prompts[1]), turns[1])
        self.assertNotIn(turns[0], prompts[1])
        self.assertEqual(memories, [])

    def _run_turns(self, turns):
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            nel = self.runtime(directory, provider)
            try:
                for turn in turns:
                    nel.think(turn)
                memories = nel.memory.recall()
            finally:
                nel.stop()
        return provider.prompts, memories

    def test_current_characterization_d1_public_questions_use_conversation_route(self):
        responses = {
            "Gemini nədir?": "Gemini ümumi bilik cavabı.",
            "Bleach necə animedir?": "Bleach ümumi bilik cavabı.",
            "Stoik fəlsəfə nədir?": "Stoik fəlsəfə ümumi bilik cavabı.",
        }
        classifier = LocalIntentClassifier()
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            nel = self.runtime(directory, provider)
            try:
                answers = {question: nel.think(question) for question in responses}
            finally:
                nel.stop()

        for question in responses:
            self.assertIs(classifier.classify(question), IntentType.CONVERSATION)
        self.assertEqual(answers, responses)
        self.assertEqual(
            [provider_user_message(prompt) for prompt in provider.prompts],
            list(responses),
        )
        self.assertEqual(provider.structured_prompts, [])

    def test_current_characterization_d2_personal_questions_have_no_authority(self):
        questions = (
            "Mən Gemini istifadə edirəm?",
            "Mən Bleach-i izləmişəm?",
            "Mən stoik fəlsəfəni sevirəm?",
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(default="Şəxsi vəziyyət cavabı")
            nel = self.runtime(directory, provider)
            try:
                before_facts = nel.knowledge.facts()
                before_memories = nel.memory.recall()
                answers = [nel.think(question) for question in questions]
                after_facts = nel.knowledge.facts()
                after_memories = nel.memory.recall()
            finally:
                nel.stop()

        self.assertEqual(answers, ["Şəxsi vəziyyət cavabı"] * 3)
        self.assertEqual(before_facts, {})
        self.assertEqual(after_facts, {})
        self.assertEqual(before_memories, [])
        self.assertEqual(after_memories, [])
        for prompt in provider.prompts:
            context = unified_context(prompt)
            self.assertEqual(context["user_facts"], [])
            self.assertEqual(context["memories"], [])

    def test_current_characterization_e2_identity_is_in_unrelated_context(self):
        questions = (
            "2+2 neçədir?",
            "Kod yaza bilirsən?",
            "Bir mahnı sözləri yaz.",
            "Gemini nədir?",
        )
        classifier = LocalIntentClassifier()
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(default="Tapşırıq cavabı")
            nel = self.runtime(directory, provider)
            try:
                answers = [nel.think(question) for question in questions]
            finally:
                nel.stop()

        self.assertEqual(answers, ["Tapşırıq cavabı"] * 4)
        for question, prompt in zip(questions, provider.prompts):
            self.assertIs(classifier.classify(question), IntentType.CONVERSATION)
            identity = unified_context(prompt)["identity"]
            self.assertEqual(identity["display_name"], "Nel")
            self.assertEqual(identity["nature"], "artificial")
            self.assertTrue(identity["role"])

    def test_current_characterization_e2_explicit_identity_is_local(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            nel = self.runtime(directory, provider)
            try:
                answer = nel.think("Sən kimsən?")
            finally:
                nel.stop()

        self.assertIn("Nel", answer)
        self.assertIn("süni", answer)
        self.assertIn("davamlı rəqəmsal yoldaşı", answer)
        self.assertEqual(provider.prompts, [])


class SimulatedProviderRiskTests(ConversationRegressionTestCase):
    def test_simulated_provider_risk_b_conflicting_personal_fact_passes_through(self):
        scenarios = (
            (
                "favorite_anime",
                "AoT",
                "Bəs Bleach?",
                "Sənin ən sevdiyin anime Bleach-dir.",
            ),
            (
                "favorite_game",
                "MK11",
                "Bəs GTA?",
                "Sənin ən sevdiyin oyun GTA-dır.",
            ),
        )

        for key, authoritative, followup, invention in scenarios:
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as directory:
                    provider = ScriptedProvider({followup: invention})
                    nel = self.runtime(directory, provider)
                    self.set_authoritative_fact(nel, key, authoritative)
                    try:
                        before = nel.knowledge.facts()
                        answer = nel.think(followup)
                        after = nel.knowledge.facts()
                    finally:
                        nel.stop()

                self.assertEqual(answer, invention)
                self.assertEqual(after, before)

    def test_simulated_provider_risk_d_personal_state_invention_passes_through(self):
        responses = {
            "Mən Gemini istifadə edirəm?": "Bəli, sən Gemini istifadə edirsən.",
            "Mən Bleach-i izləmişəm?": "Bəli, sən Bleach-i izləmisən.",
            "Mən stoik fəlsəfəni sevirəm?": "Bəli, sən stoik fəlsəfəni sevirsən.",
        }
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(responses)
            nel = self.runtime(directory, provider)
            try:
                answers = {question: nel.think(question) for question in responses}
                facts = nel.knowledge.facts()
                memories = nel.memory.recall()
            finally:
                nel.stop()

        self.assertEqual(answers, responses)
        self.assertEqual(facts, {})
        self.assertEqual(memories, [])

    def test_simulated_provider_risk_e_identity_repetition_passes_through(self):
        questions = (
            "2+2 neçədir?",
            "Kod yaza bilirsən?",
            "Bir mahnı sözləri yaz.",
            "Gemini nədir?",
        )
        prefix = "Mən Neləm, süni varlıq və Ömərin davamlı rəqəmsal yoldaşıyam."
        provider = ScriptedProvider(
            {question: f"{prefix} Cavab." for question in questions}
        )
        with tempfile.TemporaryDirectory() as directory:
            nel = self.runtime(directory, provider)
            try:
                answers = [nel.think(question) for question in questions]
            finally:
                nel.stop()

        self.assertTrue(all(answer.startswith(prefix) for answer in answers))


class FutureConversationContractTests(ConversationRegressionTestCase):
    @unittest.expectedFailure
    def test_future_contract_a_equivalent_goal_phrasings_use_authority(self):
        phrases = (
            "Məqsədlərim nədir?",
            "Nə məqsədlərim var?",
            "Mənim nə məqsədlərim var?",
            "Hansı məqsədlərim var?",
            "Mənim hansı məqsədlərim var?",
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(default="Uydurulmuş məqsəd")
            nel = self.runtime(directory, provider)
            try:
                nel.think(GOAL_CREATE)
                answers = [nel.think(phrase) for phrase in phrases]
            finally:
                nel.stop()

        self.assertTrue(all(answer == answers[0] for answer in answers))
        self.assertTrue(all(GOAL_TITLE in answer for answer in answers))
        self.assertEqual(provider.prompts, [])

    @unittest.expectedFailure
    def test_future_contract_b_anime_invention_is_blocked(self):
        self._assert_conflicting_personal_fact_is_blocked(
            "favorite_anime",
            "AoT",
            "Bəs Bleach?",
            "Sənin ən sevdiyin anime Bleach-dir.",
            "Bleach",
        )

    @unittest.expectedFailure
    def test_future_contract_b_game_invention_is_blocked(self):
        self._assert_conflicting_personal_fact_is_blocked(
            "favorite_game",
            "MK11",
            "Bəs GTA?",
            "Sənin ən sevdiyin oyun GTA-dır.",
            "GTA",
        )

    def _assert_conflicting_personal_fact_is_blocked(
        self, key, authoritative, followup, invention, candidate
    ):
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider({followup: invention})
            nel = self.runtime(directory, provider)
            self.set_authoritative_fact(nel, key, authoritative)
            try:
                answer = nel.think(followup)
                facts = nel.knowledge.facts()
            finally:
                nel.stop()

        self.assertEqual(facts, {key: authoritative})
        self.assertFalse(
            candidate in answer and "ən sevdiyin" in answer,
            "The response must clarify or preserve authoritative state.",
        )

    @unittest.expectedFailure
    def test_future_contract_c_prior_user_turn_reaches_song_followup(self):
        self._assert_followup_receives_prior_user_turn(
            "Bir mahnı yaz mənim üçün.",
            "Kədərli olsun.",
        )

    @unittest.expectedFailure
    def test_future_contract_c_prior_user_turn_reaches_continue(self):
        self._assert_followup_receives_prior_user_turn(
            "Kədərli olsun.",
            "Davam et.",
            prelude="Bir mahnı yaz mənim üçün.",
        )

    @unittest.expectedFailure
    def test_future_contract_c_prior_user_turn_reaches_formalasdir(self):
        self._assert_followup_receives_prior_user_turn(
            "Bir mahnı yaz mənim üçün.",
            "formalaşdır",
        )

    @unittest.expectedFailure
    def test_future_contract_c_prior_user_turn_reaches_topic_followup(self):
        self._assert_followup_receives_prior_user_turn(
            "Bleach haqqında danış.",
            "Bəs HxH?",
        )

    def _assert_followup_receives_prior_user_turn(
        self, prior, followup, prelude=None
    ):
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            nel = self.runtime(directory, provider)
            try:
                if prelude:
                    nel.think(prelude)
                nel.think(prior)
                nel.think(followup)
                memories = nel.memory.recall()
            finally:
                nel.stop()

        self.assertIn(prior, provider.prompts[-1])
        self.assertEqual(memories, [])

    @unittest.expectedFailure
    def test_future_contract_c_prior_assistant_response_is_available(self):
        request = "Bir mahnı yaz mənim üçün."
        assistant_response = "Birinci bənd: Səssiz gecə."
        followup = "Davam et."
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider(
                {request: assistant_response, followup: "İkinci bənd."}
            )
            nel = self.runtime(directory, provider)
            try:
                self.assertEqual(nel.think(request), assistant_response)
                nel.think(followup)
            finally:
                nel.stop()

        self.assertIn(assistant_response, provider.prompts[-1])

    @unittest.skip(CONTINUITY_LIMITS_PENDING_ADR)
    def test_future_contract_c_recent_turn_count_is_bounded(self):
        pass

    @unittest.skip(CONTINUITY_LIMITS_PENDING_ADR)
    def test_future_contract_c_recent_conversation_characters_are_bounded(self):
        pass

    @unittest.skip(CONTINUITY_EVICTION_PENDING_ADR)
    def test_future_contract_c_oldest_turn_eviction_is_deterministic(self):
        pass

    @unittest.expectedFailure
    def test_future_contract_c_recent_conversation_is_session_scoped(self):
        prior = "Sessiya A üçün əvvəlki dönüş."
        followup = "Davam et."
        with tempfile.TemporaryDirectory() as first_directory:
            first_provider = ScriptedProvider()
            first = self.runtime(first_directory, first_provider)
            try:
                first.think(prior)
                first.think(followup)
            finally:
                first.stop()
        with tempfile.TemporaryDirectory() as second_directory:
            second_provider = ScriptedProvider()
            second = self.runtime(second_directory, second_provider)
            try:
                second.think(followup)
            finally:
                second.stop()

        self.assertIn(prior, first_provider.prompts[-1])
        self.assertNotIn(prior, second_provider.prompts[-1])

    @unittest.expectedFailure
    def test_future_contract_c_restart_clears_recent_conversation(self):
        prior = "Restartdan əvvəlki dönüş."
        followup = "Davam et."
        with tempfile.TemporaryDirectory() as directory:
            provider_before = ScriptedProvider()
            before = self.runtime(directory, provider_before)
            try:
                before.think(prior)
                before.think(followup)
            finally:
                before.stop()

            provider_after = ScriptedProvider()
            after = create_runtime_nel(
                provider=provider_after,
                database_path=Path(directory) / "conversation-regressions.sqlite3",
            )
            try:
                after.think(followup)
            finally:
                after.stop()

        self.assertIn(prior, provider_before.prompts[-1])
        self.assertNotIn(prior, provider_after.prompts[-1])

    def test_future_contract_c_recent_conversation_is_never_durable_memory(self):
        turns = ("Bir mahnı yaz mənim üçün.", "Kədərli olsun.", "Davam et.")
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            nel = self.runtime(directory, provider)
            try:
                for turn in turns:
                    nel.think(turn)
                memories = nel.memory.recall()
            finally:
                nel.stop()

        self.assertEqual(memories, [])

    def test_future_contract_c_provider_failure_never_writes_durable_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            nel = self.runtime(directory, FailingProvider())
            try:
                before = nel.memory.recall()
                with self.assertRaises(ApplicationError):
                    nel.think("Davam et.")
                after = nel.memory.recall()
            finally:
                nel.stop()

        self.assertEqual(before, after)

    @unittest.expectedFailure
    def test_future_contract_c_current_input_is_distinct_from_prior_context(self):
        prior = "Əvvəlki istifadəçi dönüşü."
        current = "Cari istifadəçi dönüşü."
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider()
            nel = self.runtime(directory, provider)
            try:
                nel.think(prior)
                nel.think(current)
            finally:
                nel.stop()

        prompt = provider.prompts[-1]
        prior_context, current_section = prompt.split("\nUser:\n", 1)
        self.assertIn(prior, prior_context)
        self.assertEqual(
            current_section.split("\n\nAssistant:\n", 1)[0],
            current,
        )

    @unittest.expectedFailure
    def test_future_contract_d_absent_gemini_usage_is_not_invented(self):
        self._assert_absent_personal_fact_is_not_invented(
            "Mən Gemini istifadə edirəm?",
            "Bəli, sən Gemini istifadə edirsən.",
        )

    @unittest.expectedFailure
    def test_future_contract_d_absent_bleach_history_is_not_invented(self):
        self._assert_absent_personal_fact_is_not_invented(
            "Mən Bleach-i izləmişəm?",
            "Bəli, sən Bleach-i izləmisən.",
        )

    @unittest.expectedFailure
    def test_future_contract_d_absent_stoic_preference_is_not_invented(self):
        self._assert_absent_personal_fact_is_not_invented(
            "Mən stoik fəlsəfəni sevirəm?",
            "Bəli, sən stoik fəlsəfəni sevirsən.",
        )

    def _assert_absent_personal_fact_is_not_invented(self, question, invention):
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider({question: invention})
            nel = self.runtime(directory, provider)
            try:
                answer = nel.think(question)
                facts = nel.knowledge.facts()
                memories = nel.memory.recall()
            finally:
                nel.stop()

        self.assertEqual(facts, {})
        self.assertEqual(memories, [])
        self.assertNotEqual(answer, invention)

    @unittest.expectedFailure
    def test_future_contract_d_empty_personal_state_does_not_deny_public_knowledge(self):
        question = "Gemini nədir?"
        denial = "Şəxsi yaddaşımda Gemini barədə məlumat yoxdur."
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider({question: denial})
            nel = self.runtime(directory, provider)
            try:
                answer = nel.think(question)
                prompt = provider.prompts[-1]
            finally:
                nel.stop()

        context = unified_context(prompt)
        self.assertEqual(context["user_facts"], [])
        self.assertEqual(context["memories"], [])
        self.assertNotEqual(answer, denial)

    @unittest.expectedFailure
    def test_future_contract_e_arithmetic_does_not_repeat_identity(self):
        self._assert_ordinary_answer_has_no_identity("2+2 neçədir?")

    @unittest.expectedFailure
    def test_future_contract_e_code_task_does_not_repeat_identity(self):
        self._assert_ordinary_answer_has_no_identity("Kod yaza bilirsən?")

    @unittest.expectedFailure
    def test_future_contract_e_song_task_does_not_repeat_identity(self):
        self._assert_ordinary_answer_has_no_identity("Bir mahnı sözləri yaz.")

    @unittest.expectedFailure
    def test_future_contract_e_gemini_question_does_not_repeat_identity(self):
        self._assert_ordinary_answer_has_no_identity("Gemini nədir?")

    def _assert_ordinary_answer_has_no_identity(self, question):
        repeated_identity = (
            "Mən Neləm, süni varlıq və Ömərin davamlı rəqəmsal yoldaşıyam."
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = ScriptedProvider({question: repeated_identity})
            nel = self.runtime(directory, provider)
            try:
                answer = nel.think(question)
            finally:
                nel.stop()

        self.assertNotIn("Nel", answer)
        self.assertNotIn("süni", answer)
        self.assertNotIn("davamlı rəqəmsal yoldaşı", answer)


if __name__ == "__main__":
    unittest.main()
