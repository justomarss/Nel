import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.local_understanding.artifact import load_artifact
from src.local_understanding.dataset import augment, read_jsonl
from src.local_understanding.features import FeatureContext, build_feature_text
from src.local_understanding.rejection import AUTHORITY_LABELS

DATA = ROOT / "data" / "local_understanding"

def main():
    started = time.perf_counter(); bundle = load_artifact(DATA / "artifacts" / "local_understanding_v1.joblib"); load_seconds = time.perf_counter() - started
    model = bundle["classifier"]
    holdout = read_jsonl(DATA / "splits" / "release_holdout_v9.jsonl")
    predictions = [(row, model.predict_one(FeatureContext(row["text"]))) for row in holdout]
    per_label = {}
    for label in model.model.classes_:
        accepted = [(row, pred) for row, pred in predictions if pred.intent == label]
        tp = sum(row["intent_label"] == label for row, _ in accepted); fp = len(accepted) - tp
        total = sum(row["intent_label"] == label for row, _ in predictions)
        per_label[str(label)] = {"accepted_precision": tp / len(accepted) if accepted else 1.0, "accepted_recall": tp / total if total else 0.0, "accepted": len(accepted)}
    challenge = read_jsonl(DATA / "challenge" / "challenge.jsonl")
    challenge_predictions = [model.predict_one(FeatureContext(row["text"])) for row in challenge]
    hard_negative = read_jsonl(DATA / "challenge" / "hard_negative_v9.jsonl")
    hard_negative_predictions = [model.predict_one(FeatureContext(row["text"])) for row in hard_negative]
    hard_negative_forced = [
        prediction.intent or model.model.classes_[int(np.argmax(model.model.decision_function(model.features.transform([build_feature_text(FeatureContext(row["text"]))]))[0]))]
        for row, prediction in zip(hard_negative, hard_negative_predictions)
    ]
    hard_negative_accuracy = sum(prediction == row["intent_label"] for row, prediction in zip(hard_negative, hard_negative_forced)) / len(hard_negative)
    rejection_rates = {label: sum(pred.rejected for row, pred in predictions if row["intent_label"] == label) / sum(row["intent_label"] == label for row, _ in predictions) for label in model.model.classes_}
    context_cases = [
        ("goal_follow_up", FeatureContext("Bəs məqsədlərim?", "Mənim bir neçə hədəfim var.", "Hədəflərini göstərə bilərəm.", "conversation"), "GOAL_LIST_QUERY"),
        ("memory_follow_up", FeatureContext("Bunu yadda saxla.", "Mən italyan dili öyrənirəm.", "Başa düşdüm.", "conversation"), "MEMORY_WRITE_REQUEST"),
        ("creative_continuation", FeatureContext("Davam et.", "Mənim üçün mahnı yaz.", "Birinci bənd budur.", "conversation"), None),
    ]
    context_results = [{"case": name, "prediction": (prediction := model.predict_one(context)).intent or "UNKNOWN", "expected": expected or "UNKNOWN"} for name, context, expected in context_cases]
    noisy = augment(holdout)
    noisy_accuracy = sum(model.predict_one(FeatureContext(row["text"])).intent == row["intent_label"] for row in noisy) / len(noisy)
    latencies=[]
    for _ in range(100):
        before=time.perf_counter(); model.predict_one(FeatureContext("Məqsədlərim nədir?")); latencies.append(time.perf_counter()-before)
    report={"per_label_acceptance":per_label,"rejection_rate_per_label":rejection_rates,"challenge_count":len(challenge),"challenge_false_authority_acceptance":sum(p.intent in AUTHORITY_LABELS for p in challenge_predictions)/len(challenge),"challenge_predictions":[p.intent or "UNKNOWN" for p in challenge_predictions],"hard_negative_count":len(hard_negative),"hard_negative_forced_accuracy":hard_negative_accuracy,"noisy_acceptance_accuracy":noisy_accuracy,"context_assisted":context_results,"cold_load_seconds":load_seconds,"mean_inference_ms":statistics.mean(latencies)*1000,"artifact_bytes":(DATA/"artifacts"/"local_understanding_v1.joblib").stat().st_size}
    (DATA/"artifacts"/"evaluation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report))
if __name__ == "__main__": main()
