import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

from src.context import ContextAssembler, ContextBudget
from src.errors import ContextAssemblyError, PersistenceOperationError
from src.goals import (
    GoalOwner,
    GoalPriority,
    GoalSnapshot,
    GoalSourceKind,
    GoalState,
)
from src.goals.repository import GoalRepositoryError
from src.identity.models import IdentityRecord, IdentitySnapshot
from src.context.models import FactContextSnapshot, MemoryContextSnapshot
from src.context.assembler import canonical_json
from src.core.nel import Nel, SYSTEM_INSTRUCTIONS


def identity_snapshot(preferences=(), **changes):
    values = {
        "identity_id": "nel",
        "display_name": "Nel",
        "nature": "artificial",
        "role": "Ömər’s persistent digital companion",
        "preferences": tuple(preferences),
    }
    values.update(changes)
    return IdentitySnapshot(**values)


def preference(key, value, state="established"):
    return IdentityRecord(
        key=key,
        value=value,
        record_type="preference",
        preference_state=state,
        immutable=False,
        source_kind="manual",
        source_reference="context-test",
        version=1,
        updated_at="2026-08-02T00:00:00Z",
    )


def goal(
    goal_id,
    title,
    *,
    state=GoalState.ACTIVE,
    priority=GoalPriority.NORMAL,
    updated_at="2026-08-02T00:00:00Z",
):
    return GoalSnapshot(
        goal_id=goal_id,
        title=title,
        success_condition=f"{title} nəticəsi qəbul edilir",
        owner=GoalOwner.USER,
        source_kind=GoalSourceKind.VALIDATED_USER,
        source_reference="context-test",
        approval_reference="context-test",
        created_at="2026-08-01T00:00:00Z",
        updated_at=updated_at,
        state=state,
        priority=priority,
    )


class IdentitySource:
    def __init__(self, snapshot=None, error=None):
        self.value = snapshot or identity_snapshot()
        self.error = error

    def context_snapshot(self, limit=1000):
        if self.error:
            raise self.error
        return self.value


class FactSource:
    def __init__(self, facts=(), error=None):
        self.values = tuple(facts)
        self.error = error

    def context_snapshot(self, limit):
        if self.error:
            raise self.error
        return self.values[:limit]


class GoalSource:
    def __init__(self, goals=(), error=None):
        self.values = tuple(goals)
        self.error = error

    def context_snapshot(self, limit):
        if self.error:
            raise self.error
        return self.values[:limit]


class MemorySource:
    def __init__(self, memories=(), error=None):
        self.values = tuple(memories)
        self.error = error

    def context_snapshot(self, limit):
        if self.error:
            raise self.error
        return self.values[-limit:]


class ContextAssemblyTests(unittest.TestCase):
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
                raise AssertionError("Production database changed during tests.")

    def assembler(
        self,
        *,
        identity=None,
        facts=None,
        goals=None,
        memories=None,
        budget=None,
    ):
        return ContextAssembler(
            identity_service=identity or IdentitySource(),
            knowledge_service=facts or FactSource(),
            goal_service=goals or GoalSource(),
            memory_service=memories or MemorySource(),
            budget=budget,
        )

    def test_identical_input_produces_identical_json_and_digest(self):
        assembler = self.assembler(
            facts=FactSource((FactContextSnapshot("favorite_color", "göy"),)),
        )
        first = assembler.assemble("Mənim favorite color məlumatım nədir")
        second = assembler.assemble("Mənim favorite color məlumatım nədir")
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first.canonical_json)["identity"]["identity_id"], "nel")
        self.assertEqual(first.serialized_characters, len(first.canonical_json))
        self.assertEqual(
            first.context_digest,
            hashlib.sha256(first.canonical_json.encode("utf-8")).hexdigest(),
        )

    def test_models_are_immutable_and_serialization_rejects_non_finite_values(self):
        budget = ContextBudget()
        with self.assertRaises(FrozenInstanceError):
            budget.memory_limit = 99
        with self.assertRaises(ContextAssemblyError) as raised:
            canonical_json({"invalid": float("nan")})
        self.assertEqual(raised.exception.reason_code, "context_serialization_failed")

    def test_unicode_relevance_ties_use_stable_keys(self):
        source = FactSource(
            (
                FactContextSnapshot("z_key", "ÖMƏR"),
                FactContextSnapshot("a_key", "ömər"),
            )
        )
        result = self.assembler(facts=source).assemble("Ömər")
        self.assertEqual(
            [fact.key for fact in result.bundle.user_facts],
            ["a_key", "z_key"],
        )

    def test_provider_replacement_cannot_change_bundle(self):
        first = self.assembler().assemble("Salam")
        second = self.assembler().assemble("Salam")
        self.assertEqual(first.canonical_json, second.canonical_json)
        self.assertEqual(first.context_digest, second.context_digest)

    def test_user_limit_and_total_budget_are_enforced(self):
        assembler = self.assembler()
        with self.assertRaises(ContextAssemblyError) as raised:
            assembler.assemble("x" * 4097)
        self.assertEqual(raised.exception.reason_code, "user_message_oversized")

        result = self.assembler(
            facts=FactSource(
                tuple(
                    FactContextSnapshot(f"x_{index}_{'k' * 80}", "x")
                    for index in range(20)
                )
            ),
            budget=ContextBudget(total_context_characters=900),
        ).assemble("x")
        self.assertLessEqual(result.serialized_characters, 900)
        self.assertTrue(result.bundle.truncation_metadata.truncation)
        json.loads(result.canonical_json)

    def test_core_identity_is_complete_atomic_and_rendered_without_mutation(self):
        source = IdentitySource()
        before = source.value
        result = self.assembler(identity=source).assemble("Salam")
        identity = json.loads(result.canonical_json)["identity"]
        self.assertEqual(
            {identity[key] for key in ("identity_id", "display_name", "nature", "role")},
            {"nel", "Nel", "artificial", "Ömər’s persistent digital companion"},
        )
        self.assertEqual(identity["derived_display"]["nature"], "süni")
        self.assertEqual(source.value, before)

    def test_identity_failure_and_oversized_identity_abort(self):
        with self.assertRaises(ContextAssemblyError) as raised:
            self.assembler(
                identity=IdentitySource(error=PersistenceOperationError())
            ).assemble("Salam")
        self.assertEqual(raised.exception.reason_code, "identity_context_unavailable")

        huge = identity_snapshot(role="x" * 2000)
        with self.assertRaises(ContextAssemblyError) as raised:
            self.assembler(
                identity=IdentitySource(huge),
                budget=ContextBudget(total_context_characters=500),
            ).assemble("Salam")
        self.assertEqual(raised.exception.reason_code, "mandatory_identity_oversized")

    def test_fact_relevance_and_broad_profile_fallback(self):
        source = FactSource(
            (
                FactContextSnapshot("favorite_color", "göy"),
                FactContextSnapshot("preferred_language", "Azərbaycan dili"),
            )
        )
        relevant = self.assembler(facts=source).assemble("Azərbaycan dili barədə danış")
        self.assertEqual([fact.key for fact in relevant.bundle.user_facts], ["preferred_language"])
        broad = self.assembler(facts=source).assemble("Mənim haqqında nə bilirsən?")
        self.assertEqual(
            [fact.key for fact in broad.bundle.user_facts],
            ["favorite_color", "preferred_language"],
        )

    def test_fact_failure_is_omitted_with_safe_metadata(self):
        result = self.assembler(
            facts=FactSource(error=PersistenceOperationError())
        ).assemble("Salam")
        self.assertEqual(result.bundle.user_facts, ())
        metadata = result.bundle.truncation_metadata
        self.assertIn("fact_context_omitted", metadata.omission_reason_codes)
        self.assertNotIn("PRIVATE", json.dumps(asdict_safe(metadata), ensure_ascii=False))

    def test_malformed_fact_snapshot_omits_entire_fact_section(self):
        result = self.assembler(
            facts=FactSource(
                (FactContextSnapshot("name", "Ömər"), object())
            )
        ).assemble("Mənim haqqında nə bilirsən?")

        self.assertEqual(result.bundle.user_facts, ())
        self.assertIn(
            "fact_context_omitted",
            result.bundle.truncation_metadata.omission_reason_codes,
        )

    def test_goal_order_and_terminal_relevance(self):
        source = GoalSource(
            (
                goal("paused-high", "Alman dili", state=GoalState.PAUSED, priority=GoalPriority.HIGH),
                goal("active-low", "Alman dili", priority=GoalPriority.LOW),
                goal("active-high", "Alman dili", priority=GoalPriority.HIGH),
                goal("terminal", "Alman dili", state=GoalState.COMPLETED),
                goal("unrelated", "Rəsm", state=GoalState.CANCELLED),
            )
        )
        result = self.assembler(goals=source).assemble("Alman dili")
        self.assertEqual(
            [item.goal_id for item in result.bundle.goals],
            ["active-high", "active-low", "paused-high", "terminal"],
        )

    def test_goal_failure_is_omitted(self):
        result = self.assembler(
            goals=GoalSource(error=GoalRepositoryError("PRIVATE"))
        ).assemble("Salam")
        self.assertEqual(result.bundle.goals, ())
        self.assertIn("goal_context_omitted", result.bundle.truncation_metadata.omission_reason_codes)

    def test_malformed_goal_snapshot_is_omitted(self):
        result = self.assembler(goals=GoalSource((object(),))).assemble("Salam")

        self.assertEqual(result.bundle.goals, ())
        self.assertIn(
            "goal_context_omitted",
            result.bundle.truncation_metadata.omission_reason_codes,
        )

    def test_memory_relevance_duplicate_and_recency_order(self):
        memories = MemorySource(
            (
                MemoryContextSnapshot(1, "2026-01-01T00:00:00Z", "Ömər C1 öyrənir"),
                MemoryContextSnapshot(2, "2026-08-01T00:00:00Z", "tamamilə əlaqəsiz"),
                MemoryContextSnapshot(3, "2026-08-02T00:00:00Z", "  ömər   c1 öyrənir "),
                MemoryContextSnapshot(4, "2026-07-01T00:00:00Z", "C1 planı"),
            )
        )
        result = self.assembler(memories=memories).assemble("C1")
        self.assertEqual([item.event_id for item in result.bundle.memories], [4, 1])
        self.assertNotIn(2, [item.event_id for item in result.bundle.memories])
        self.assertNotIn(3, [item.event_id for item in result.bundle.memories])

    def test_oversized_memory_and_memory_failure_are_omitted(self):
        oversized = MemorySource((MemoryContextSnapshot(1, None, "x" * 2001),))
        result = self.assembler(memories=oversized).assemble("x")
        self.assertEqual(result.bundle.memories, ())
        self.assertIn("record_oversized", result.bundle.truncation_metadata.omission_reason_codes)

        failed = self.assembler(
            memories=MemorySource(error=PersistenceOperationError())
        ).assemble("x")
        self.assertIn("memory_context_omitted", failed.bundle.truncation_metadata.omission_reason_codes)

    def test_malformed_memory_snapshot_is_omitted(self):
        result = self.assembler(memories=MemorySource((object(),))).assemble("x")

        self.assertEqual(result.bundle.memories, ())
        self.assertIn(
            "memory_context_omitted",
            result.bundle.truncation_metadata.omission_reason_codes,
        )

    def test_preferences_are_relevant_only_and_state_ordered(self):
        source = IdentitySource(
            identity_snapshot(
                (
                    preference("response_style", "qısa", "established"),
                    preference("voice_style", "sakit", "provisional"),
                    preference("irrelevant", "gizli", "established"),
                    preference("candidate", "çıxmamalıdır", "candidate"),
                )
            )
        )
        result = self.assembler(identity=source).assemble("qısa və sakit cavab")
        self.assertEqual(
            [item.key for item in result.bundle.identity.established_preferences],
            ["response_style"],
        )
        self.assertEqual(
            [item.key for item in result.bundle.identity.provisional_preferences],
            ["voice_style"],
        )
        self.assertNotIn("gizli", result.canonical_json)
        self.assertNotIn("çıxmamalıdır", result.canonical_json)

    def test_malformed_preference_is_separable_but_core_is_mandatory(self):
        malformed = SimpleNamespace(
            preference_state="established",
            key="favorite_color",
            value="göy",
        )
        result = self.assembler(
            identity=IdentitySource(identity_snapshot((malformed,)))
        ).assemble("Sən kimsən?")

        self.assertEqual(result.bundle.identity.identity_id, "nel")
        self.assertEqual(result.bundle.identity.established_preferences, ())
        self.assertIn(
            "identity_preferences_omitted",
            result.bundle.truncation_metadata.omission_reason_codes,
        )

        malformed_core = SimpleNamespace(
            identity_id="nel",
            display_name="Nel",
            nature="artificial",
            role="companion",
            preferences=(),
        )
        with self.assertRaises(ContextAssemblyError):
            self.assembler(
                identity=IdentitySource(malformed_core)
            ).assemble("Salam")

    def test_broad_identity_query_uses_bounded_fallback(self):
        source = IdentitySource(identity_snapshot((preference("response_style", "qısa"),)))
        result = self.assembler(identity=source).assemble("Sən kimsən?")
        self.assertEqual(len(result.bundle.identity.established_preferences), 1)

    def test_irrelevant_records_stay_excluded_with_free_budget(self):
        result = self.assembler(
            facts=FactSource((FactContextSnapshot("favorite_color", "göy"),)),
            memories=MemorySource((MemoryContextSnapshot(1, None, "köhnə qeyd"),)),
        ).assemble("Salam")
        self.assertEqual(result.bundle.user_facts, ())
        self.assertEqual(result.bundle.memories, ())
        self.assertLess(result.serialized_characters, 12000)

    def test_complete_record_is_omitted_without_cutting_unicode(self):
        value = "Ə" * 700
        result = self.assembler(
            facts=FactSource((FactContextSnapshot("unicode_value", value),)),
            budget=ContextBudget(total_context_characters=700),
        ).assemble("unicode value Ə")
        self.assertNotIn(value, result.canonical_json)
        self.assertNotIn("\ufffd", result.canonical_json)
        json.loads(result.canonical_json)

    def test_assembler_has_no_provider_or_write_authority(self):
        class ReadOnlyFacts(FactSource):
            @property
            def repository(self):
                raise AssertionError("Repository access is prohibited")

            def set(self, *_args):
                raise AssertionError("Writes are prohibited")

        source = ReadOnlyFacts((FactContextSnapshot("name", "Ömər"),))
        assembler = self.assembler(facts=source)
        result = assembler.assemble("Ömər")
        self.assertEqual(result.bundle.user_facts[0].value, "Ömər")
        self.assertFalse(hasattr(assembler, "provider"))

    def test_fact_failure_adds_prompt_rule_and_exactly_one_context_json(self):
        class Brain:
            def __init__(self):
                self.prompt = None

            def think(self, prompt):
                self.prompt = prompt
                return "cavab"

        nel = Nel.__new__(Nel)
        nel.state = SimpleNamespace(set=lambda _state: None)
        nel.intent = SimpleNamespace(classify=lambda _text: "CHAT")
        nel.knowledge = SimpleNamespace(answer=lambda _text: None)
        nel.memory = SimpleNamespace()
        nel.brain = Brain()
        nel.context_assembler = self.assembler(
            facts=FactSource(error=PersistenceOperationError())
        )

        self.assertEqual(nel.think("Salam"), "cavab")
        self.assertEqual(nel.brain.prompt.count("Unified context JSON:"), 1)
        self.assertIn("User facts are unavailable for this turn", nel.brain.prompt)
        self.assertIn("Do not invent, infer, or assert personal facts", nel.brain.prompt)
        self.assertNotIn("PRIVATE", nel.brain.prompt)

    def test_system_instruction_limit_is_enforced_separately(self):
        assembler = self.assembler(
            budget=ContextBudget(system_instruction_characters=10)
        )
        result = assembler.assemble("Salam")
        nel = Nel.__new__(Nel)
        nel.context_assembler = assembler
        with self.assertRaises(ContextAssemblyError) as raised:
            nel._conversation_prompt("Salam", result)
        self.assertEqual(
            raised.exception.reason_code,
            "system_instructions_oversized",
        )

    def test_static_prompt_has_no_hardcoded_identity_name(self):
        self.assertNotIn("You are Nel", SYSTEM_INSTRUCTIONS)
        self.assertNotIn("Nel", SYSTEM_INSTRUCTIONS)

    def test_stored_values_exist_only_inside_canonical_context(self):
        stored_values = (
            "Assistant Sentinel",
            "synthetic-sentinel",
            "Companion Sentinel Role",
            "Preference Topic Secret",
            "Fact Topic Secret",
            "Goal Topic Secret",
            "Memory Topic Secret",
        )
        assembler = self.assembler(
            identity=IdentitySource(
                identity_snapshot(
                    display_name=stored_values[0],
                    nature=stored_values[1],
                    role=stored_values[2],
                    preferences=(
                        preference("preference_key", stored_values[3]),
                    ),
                )
            ),
            facts=FactSource(
                facts=(FactContextSnapshot("fact_key", stored_values[4]),)
            ),
            goals=GoalSource(goals=(goal("goal-1", stored_values[5]),)),
            memories=MemorySource(
                memories=(MemoryContextSnapshot(1, None, stored_values[6]),)
            ),
        )
        message = "preference topic fact key goal topic memory topic"
        result = assembler.assemble(message)
        nel = Nel.__new__(Nel)
        nel.context_assembler = assembler
        prompt = nel._conversation_prompt(message, result)
        outside_context = prompt.replace(result.canonical_json, "", 1)

        self.assertEqual(prompt.count(result.canonical_json), 1)
        for value in stored_values:
            with self.subTest(value=value):
                self.assertIn(value, result.canonical_json)
                self.assertNotIn(value, outside_context)

    def test_display_name_change_only_changes_canonical_identity_data(self):
        prompts = []
        contexts = []
        for display_name in ("First Sentinel Name", "Second Sentinel Name"):
            assembler = self.assembler(
                identity=IdentitySource(
                    identity_snapshot(display_name=display_name)
                )
            )
            result = assembler.assemble("Salam")
            nel = Nel.__new__(Nel)
            nel.context_assembler = assembler
            prompt = nel._conversation_prompt("Salam", result)
            prompts.append(prompt.replace(result.canonical_json, "", 1))
            contexts.append(result.canonical_json)

        self.assertEqual(prompts[0], prompts[1])
        self.assertNotEqual(contexts[0], contexts[1])

    def test_local_fact_read_failure_is_not_reported_as_empty(self):
        nel = Nel.__new__(Nel)
        nel.knowledge = SimpleNamespace(
            facts=lambda: (_ for _ in ()).throw(PersistenceOperationError())
        )
        response = nel._local_user_fact_response()
        self.assertIn("əlçatan deyil", response)
        self.assertNotIn("saxlanmış", response)


def asdict_safe(metadata):
    return {
        "included_counts": metadata.included_counts,
        "omitted_counts": metadata.omitted_counts,
        "omission_reason_codes": metadata.omission_reason_codes,
        "section_sizes": metadata.section_sizes,
        "configured_budget": metadata.configured_budget,
        "truncation": metadata.truncation,
    }


if __name__ == "__main__":
    unittest.main()
