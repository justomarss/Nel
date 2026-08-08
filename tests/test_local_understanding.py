import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.local_understanding.artifact import load_artifact, save_artifact
from src.local_understanding.classifier import LocalUnderstandingClassifier
from src.local_understanding.dataset import augment, deterministic_split, qc
from src.local_understanding.features import FeatureContext, build_feature_text
from src.local_understanding.labels import TRAINED_LABELS
from src.local_understanding.rejection import safety_accept
from src.local_understanding.schema import validate_record
from src.local_understanding.shadow import ShadowLocalUnderstanding
from src.core.nel import Nel
from tests.context_helpers import StaticIdentityService


class _Provider:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return "provider response"


class _MemoryRepository:
    def __init__(self):
        self.items = []

    def remember(self, text):
        self.items.append(text)

    def recall(self, limit=None):
        return self.items[-limit:] if limit is not None else list(self.items)


class _KnowledgeRepository:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def load(self):
        return dict(self.data)


class _Shadow:
    def __init__(self, value="GOAL_WRITE_REQUEST"):
        self.value = value
        self.calls = []

    def predict(self, prompt):
        self.calls.append(prompt)
        return self.value


def row(index, label, text, family="family"):
    return {"id":str(index),"text":text,"intent_label":label,"source_family":family,"semantic_pattern":"pattern","register":"standard","language_mix":"az","difficulty":"normal","contextual":False,"previous_user":"","previous_assistant":"","hard_negative_group":"","correction_signal":False,"generation_method":"test","review_status":"reviewed","lineage_id":str(index)}


class LocalUnderstandingTests(unittest.TestCase):
    def test_taxonomy_has_exactly_eight_labels_and_no_unknown(self):
        self.assertEqual(len(TRAINED_LABELS), 8); self.assertNotIn("UNKNOWN", TRAINED_LABELS)

    def test_schema_and_qc_reject_invalid_label(self):
        value=row(1,"UNKNOWN","x")
        self.assertTrue(validate_record(value)); self.assertTrue(qc([value])["issues"])

    def test_split_is_deterministic_and_augmentation_stays_in_split(self):
        rows=[row(i,label,f"text {i}",f"f{i%3}") for label in TRAINED_LABELS for i in range(20)]
        first=deterministic_split(rows); second=deterministic_split(rows)
        self.assertEqual(first,second)
        parents={item["id"]:item["split"] for item in first[:2]}
        for item in augment(first[:2]):
            if "parent_id" in item: self.assertEqual(item["split"],parents[item["parent_id"]])

    def test_context_uses_only_explicit_short_followups(self):
        plain=build_feature_text(FeatureContext("Mahnı yaz.","old goal","old answer"))
        follow=build_feature_text(FeatureContext("Davam et.","Mahnı yaz.","Birinci bənd"))
        self.assertNotIn("old goal",plain); self.assertIn("Mahnı yaz.",follow)

    def test_safety_rejects_targetless_goal_write_and_capability_identity(self):
        self.assertFalse(safety_accept("GOAL_WRITE_REQUEST","Onu dəyiş."))
        self.assertFalse(safety_accept("IDENTITY_QUERY","Nə edə bilirsən?"))
        self.assertFalse(safety_accept("PERSONAL_FACT_QUERY","Mənim hədəflərim hansılardır?"))
        self.assertTrue(safety_accept("IDENTITY_QUERY","Sənə hansı adla xitab edə bilərəm?"))

    def test_classifier_artifact_roundtrip_and_shadow_is_diagnostic(self):
        contexts=[FeatureContext("Sən kimsən?"),FeatureContext("Məqsədlərim nədir?"),FeatureContext("Bleach necə animedir?")]
        labels=["IDENTITY_QUERY","GOAL_LIST_QUERY","GENERAL_CONVERSATION"]
        model=LocalUnderstandingClassifier().fit(contexts,labels)
        shadow=ShadowLocalUnderstanding(model); prediction=shadow.predict("Sən kimsən?")
        self.assertEqual(prediction.intent,"IDENTITY_QUERY")
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"model.joblib";save_artifact(model,path,{"test":True})
            self.assertEqual(load_artifact(path)["classifier"].predict_one(contexts[0]).intent,"IDENTITY_QUERY")

    @patch("src.core.nel.Clock.start")
    def test_shadow_prediction_cannot_change_conversation_route_or_write_state(self, _clock_start):
        provider = _Provider(); memory = _MemoryRepository(); shadow = _Shadow()
        nel = Nel(provider=provider, memory_repository=memory, knowledge_repository=_KnowledgeRepository(), identity_service=StaticIdentityService(), local_understanding_shadow=shadow)
        try:
            self.assertEqual(nel.think("Bleach necə animedir?"), "provider response")
            self.assertEqual(shadow.calls, ["Bleach necə animedir?"])
            self.assertEqual(len(provider.prompts), 1)
            self.assertEqual(memory.items, [])
        finally:
            nel.stop()

    @patch("src.core.nel.Clock.start")
    def test_shadow_cannot_execute_or_confirm_explicit_command(self, _clock_start):
        provider = _Provider(); memory = _MemoryRepository(); shadow = _Shadow("MEMORY_WRITE_REQUEST")
        nel = Nel(provider=provider, memory_repository=memory, knowledge_repository=_KnowledgeRepository(), identity_service=StaticIdentityService(), local_understanding_shadow=shadow)
        try:
            response = nel.think("/remember only-current-command")
            self.assertEqual(memory.items, ["only-current-command"])
            self.assertEqual(shadow.calls, [])
            self.assertEqual(provider.prompts, [])
            self.assertIn("Yadda", response)
        finally:
            nel.stop()

    @patch("src.local_understanding.artifact.load_artifact", side_effect=RuntimeError("broken artifact"))
    @patch("src.core.nel.Clock.start")
    def test_normal_runtime_does_not_load_or_require_shadow_artifact(self, _clock_start, _load_artifact):
        provider = _Provider()
        nel = Nel(provider=provider, memory_repository=_MemoryRepository(), knowledge_repository=_KnowledgeRepository(), identity_service=StaticIdentityService())
        try:
            self.assertEqual(nel.think("Salam"), "provider response")
            self.assertEqual(len(provider.prompts), 1)
            _load_artifact.assert_not_called()
        finally:
            nel.stop()

if __name__ == "__main__": unittest.main()
