import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.errors import ProviderError
from src.core.runtime import create_runtime_nel
from src.knowledge import (
    FactCandidate,
    FactGroundingPolicy,
    FactProposalType,
    GroundingError,
    GroundingEvidence,
)
from src.persistence.fact_migration import migrate_fact_schema_v3_to_v4
from src.persistence.goal_migration import migrate_goal_schema_v2_to_v3
from src.persistence.identity_migration import migrate_identity_schema_v1_to_v2
from src.persistence.repositories import SQLiteKnowledge
from src.persistence.sqlite import SQLiteDatabase
from src.services.knowledge_service import KnowledgeService


def make_candidate(
    text,
    key,
    value,
    *,
    occurrence=0,
    source_start=0,
    source_end=None,
    source_quote=None,
    value_start=None,
    value_end=None,
):
    if source_end is None:
        source_end = len(text)
    if source_quote is None:
        source_quote = text[source_start:source_end]
    if value_start is None:
        position = -1
        for _ in range(occurrence + 1):
            position = text.index(value, position + 1)
        value_start = position
    if value_end is None:
        value_end = value_start + len(value)
    return FactCandidate(
        key=key,
        value=value,
        subject="user",
        confidence=1.0,
        evidence=GroundingEvidence(
            source_start=source_start,
            source_end=source_end,
            source_quote=source_quote,
            value_start=value_start,
            value_end=value_end,
        ),
    )


def candidate_response(text, key, value, **overrides):
    candidate = make_candidate(text, key, value, **overrides)
    evidence = candidate.evidence
    return json.dumps(
        {
            "facts": [
                {
                    "key": candidate.key,
                    "value": candidate.value,
                    "subject": candidate.subject,
                    "confidence": candidate.confidence,
                    "source_start": evidence.source_start,
                    "source_end": evidence.source_end,
                    "source_quote": evidence.source_quote,
                    "value_start": evidence.value_start,
                    "value_end": evidence.value_end,
                }
            ]
        },
        ensure_ascii=False,
    )


class RecordingProvider:
    def __init__(self, structured_response='{"facts": []}', chat_response="Cavab"):
        self.structured_response = structured_response
        self.chat_response = chat_response
        self.structured_calls = 0
        self.chat_calls = 0

    def generate_structured(self, *_args):
        self.structured_calls += 1
        if isinstance(self.structured_response, Exception):
            raise self.structured_response
        return self.structured_response

    def generate(self, _prompt):
        self.chat_calls += 1
        return self.chat_response


def create_v4_database(path):
    database = SQLiteDatabase(path)
    database.initialize("2026-08-02T00:00:00Z")
    migrate_identity_schema_v1_to_v2(database, "2026-08-02T00:00:01Z")
    migrate_goal_schema_v2_to_v3(database, "2026-08-02T00:00:02Z")
    migrate_fact_schema_v3_to_v4(database, "2026-08-02T00:00:03Z")
    return database


class FactGroundingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = FactGroundingPolicy()

    def assert_rejected(self, reason, text, *candidates):
        with self.assertRaises(GroundingError) as raised:
            self.policy.validate_batch(text, candidates)
        self.assertEqual(raised.exception.reason_code, reason)

    def test_exact_literal_offsets_and_punctuation_are_preserved(self):
        text = 'Mənim ləqəbim "Ömər!"dir.'
        candidate = make_candidate(text, "nickname", '"Ömər!"')
        self.assertEqual(self.policy.validate_batch(text, (candidate,)), (candidate,))

    def test_invalid_source_and_value_bounds_are_rejected(self):
        text = "Mənim seçimim AoT-dir."
        self.assert_rejected(
            "invalid_source_bounds",
            text,
            make_candidate(text, "choice", "AoT", source_end=len(text) + 1),
        )
        self.assert_rejected(
            "invalid_value_bounds",
            text,
            make_candidate(text, "choice", "AoT", value_end=len(text) + 1),
        )

    def test_absent_translated_and_expanded_values_are_rejected(self):
        text = "Mənim seçimim AoT-dir."
        start = text.index("AoT")
        for value in ("Attack on Titan", "Titanlara hücum"):
            with self.subTest(value=value):
                self.assert_rejected(
                    "literal_value_mismatch",
                    text,
                    make_candidate(
                        text,
                        "choice",
                        value,
                        value_start=start,
                        value_end=start + 3,
                    ),
                )

    def test_abbreviation_casing_and_internal_whitespace_are_literal(self):
        text = "Mənim seçimim AoT və kodum A  B-dir."
        exact = (
            make_candidate(text, "choice", "AoT"),
            make_candidate(text, "code", "A  B"),
        )
        self.assertEqual(self.policy.validate_batch(text, exact), exact)
        start = text.index("AoT")
        self.assert_rejected(
            "literal_value_mismatch",
            text,
            make_candidate(
                text,
                "choice",
                "aot",
                value_start=start,
                value_end=start + 3,
            ),
        )

    def test_repeated_identical_value_is_resolved_by_offsets(self):
        text = "Mənim kodum AoT idi, indi AoT-dir."
        candidate = make_candidate(text, "current_code", "AoT", occurrence=1)
        self.assertEqual(candidate.evidence.value_start, text.rindex("AoT"))
        self.assertEqual(self.policy.validate_batch(text, (candidate,)), (candidate,))

    def test_user_ownership_negation_history_and_comparison_fail_closed(self):
        cases = (
            ("user_ownership_ambiguous", "Onun adı Ömərdir.", "name", "Ömər"),
            (
                "user_ownership_ambiguous",
                "Mən bilirəm ki, onun adı Ömərdir.",
                "name",
                "Ömər",
            ),
            (
                "user_ownership_ambiguous",
                "Mənim dostumun adı Ömərdir.",
                "name",
                "Ömər",
            ),
            ("negated_evidence", "Mən AoT-ni sevmirəm.", "favorite", "AoT"),
            ("historical_evidence", "Mənim seçimim əvvəl Bleach idi.", "choice", "Bleach"),
            ("comparative_evidence", "Mən AoT-ni daha çox sevirəm.", "favorite", "AoT"),
        )
        for reason, text, key, value in cases:
            with self.subTest(reason=reason):
                self.assert_rejected(reason, text, make_candidate(text, key, value))

    def test_explicit_current_correction_is_grounded(self):
        text = "Mənim seçimim əvvəl Bleach idi, indi AoT-dir."
        candidate = make_candidate(text, "choice", "AoT")
        self.assertEqual(self.policy.validate_batch(text, (candidate,)), (candidate,))

    def test_duplicate_key_or_one_invalid_member_rejects_entire_batch(self):
        text = "Mənim adım Ömərdir və kodum AoT-dir."
        first = make_candidate(text, "name", "Ömər")
        duplicate = make_candidate(text, "name", "AoT")
        self.assert_rejected("duplicate_normalized_key", text, first, duplicate)
        invalid = make_candidate(text, "code", "AoT", source_quote="wrong")
        self.assert_rejected("source_quote_mismatch", text, first, invalid)


class KnowledgeGroundingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production = Path("memory/nel.sqlite3")
        cls.production_hash = (
            hashlib.sha256(cls.production.read_bytes()).hexdigest()
            if cls.production.is_file()
            else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls.production_hash is not None:
            actual = hashlib.sha256(cls.production.read_bytes()).hexdigest()
            if actual != cls.production_hash:
                raise AssertionError("Production database was modified by tests.")

    def create_service(self, directory, provider):
        repository = SQLiteKnowledge(
            create_v4_database(Path(directory) / "grounding.sqlite3")
        )
        service = KnowledgeService(
            type("Brain", (), {"provider": provider})(),
            repository,
        )
        return service, repository

    def test_questions_commands_and_local_reads_do_not_call_provider(self):
        inputs = (
            "Mənim ən sevdiyim oyun hansıdır?",
            "/fact list",
            "Mənim haqqımda nə bilirsən?",
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider()
            service, _ = self.create_service(directory, provider)
            for text in inputs:
                self.assertEqual(service.process(text), ())
            self.assertEqual(provider.structured_calls, 0)

    def test_malformed_output_has_no_repair_retry_or_write(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider("not-json")
            service, _ = self.create_service(directory, provider)
            self.assertEqual(service.process("Mənim adım Ömərdir."), ())
            self.assertEqual(provider.structured_calls, 1)
            self.assertEqual(service.facts(), {})

    def test_new_correction_same_and_reactivation_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            text = "Mənim kodum AoT-dir."
            provider = RecordingProvider(candidate_response(text, "code", "AoT"))
            service, _ = self.create_service(directory, provider)

            proposal = service.process(text)[0]
            self.assertEqual(proposal.proposal_type, FactProposalType.NEW)
            self.assertEqual(service.facts(), {})

            service.correct_fact("code", "Bleach", confirmed=True)
            proposal = service.process(text)[0]
            self.assertEqual(proposal.proposal_type, FactProposalType.CORRECTION)
            self.assertEqual(service.get("code"), "Bleach")

            service.correct_fact("code", "AoT", confirmed=True)
            self.assertEqual(service.process(text), ())

            service.retire_fact("code", confirmed=True, reason="test retirement")
            proposal = service.process(text)[0]
            self.assertEqual(proposal.proposal_type, FactProposalType.REACTIVATION)
            self.assertIsNone(service.get("code"))

    def test_proposal_rendering_is_temporary_and_shell_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            text = "Mənim ləqəbim O'Brien-dir."
            provider = RecordingProvider(candidate_response(text, "nickname", "O'Brien"))
            service, _ = self.create_service(directory, provider)
            proposals = service.process(text)
            rendered = service.render_proposals(proposals)
            self.assertIn("Proposed, not stored", rendered)
            self.assertIn("/fact set nickname", rendered)
            self.assertEqual(service.facts(), {})
            self.assertFalse(hasattr(service, "pending_candidates"))

    def test_provider_failure_stores_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider(ProviderError("safe failure"))
            service, _ = self.create_service(directory, provider)
            self.assertEqual(service.process("Mənim adım Ömərdir."), ())
            self.assertEqual(service.facts(), {})

    def test_conversation_response_and_temporary_proposal_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            text = "Mənim adım Ömərdir."
            path = Path(directory) / "runtime.sqlite3"
            create_v4_database(path)
            provider = RecordingProvider(candidate_response(text, "name", "Ömər"))
            nel = create_runtime_nel(database_path=path, provider=provider)
            try:
                response = nel.think(text)
                self.assertTrue(response.startswith("Cavab\n\nProposed, not stored"))
                self.assertEqual(nel.knowledge.facts(), {})
                self.assertEqual(provider.structured_calls, 1)
                self.assertEqual(provider.chat_calls, 1)
            finally:
                nel.stop()

    def test_extraction_failure_continues_normal_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.sqlite3"
            create_v4_database(path)
            provider = RecordingProvider(ProviderError("safe failure"))
            nel = create_runtime_nel(database_path=path, provider=provider)
            try:
                self.assertEqual(nel.think("Mənim adım Ömərdir."), "Cavab")
                self.assertEqual(nel.knowledge.facts(), {})
                self.assertEqual(provider.structured_calls, 1)
                self.assertEqual(provider.chat_calls, 1)
            finally:
                nel.stop()

    def test_explicit_fact_set_still_persists_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _ = self.create_service(directory, RecordingProvider())
            service.correct_fact("name", "Ömər", confirmed=True)
            service.correct_fact("name", "Ömər Məmmədov", confirmed=True)
            self.assertEqual(service.get("name"), "Ömər Məmmədov")
            revisions = service.history("name")
            self.assertEqual([row.value for row in revisions], ["Ömər", "Ömər Məmmədov"])
            self.assertEqual([row.version for row in revisions], [1, 2])


if __name__ == "__main__":
    unittest.main()
