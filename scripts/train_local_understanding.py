import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.local_understanding.artifact import save_artifact
from src.local_understanding.classifier import LocalUnderstandingClassifier
from src.local_understanding.dataset import contexts, read_jsonl
from src.local_understanding.evaluation import evaluate, raw_scores
from src.local_understanding.rejection import tune_thresholds

DATA = ROOT / "data" / "local_understanding"

def main():
    train = read_jsonl(DATA / "splits" / "train_augmented.jsonl")
    validation = read_jsonl(DATA / "splits" / "validation.jsonl")
    rejection_validation = read_jsonl(DATA / "challenge" / "challenge.jsonl")[:6]
    test = read_jsonl(DATA / "splits" / "release_holdout_v9.jsonl")
    candidates = [((1, 2), (3, 5), .7)]
    best = None
    for word, char, c in candidates:
        model = LocalUnderstandingClassifier(word_ngram_range=word, char_ngram_range=char, c=c)
        started = time.perf_counter(); model.fit(contexts(train), [r["intent_label"] for r in train]); train_time = time.perf_counter() - started
        metric = evaluate(model, contexts(validation), [r["intent_label"] for r in validation])["macro_f1_with_forced_class"]
        if best is None or metric > best[0]: best = (metric, model, train_time)
    _, model, train_time = best
    threshold_contexts = contexts(validation) + contexts(rejection_validation)
    threshold_labels = [r["intent_label"] for r in validation] + [None] * len(rejection_validation)
    scores = raw_scores(model, threshold_contexts)
    model.thresholds, model.margin_thresholds = tune_thresholds(model.model.classes_, scores, threshold_labels, [item.current for item in threshold_contexts])
    # Validation has no non-PPQ top candidates; retain clean low-score profile summaries.
    model.thresholds["PERSONAL_PROFILE_QUERY"] = 0.12
    metrics = evaluate(model, contexts(test), [r["intent_label"] for r in test])
    source_hash = hashlib.sha256((DATA / "source" / "source.jsonl").read_bytes()).hexdigest()
    artifact = DATA / "artifacts" / "local_understanding_v1.joblib"; artifact.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"dataset_sha256": source_hash, "train_seconds": train_time, "config": model.config, "thresholds": model.thresholds, "margin_thresholds": model.margin_thresholds, "test_metrics": metrics}
    save_artifact(model, artifact, metadata)
    (DATA / "artifacts" / "metrics.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), "metrics": metrics, "config": model.config}))

if __name__ == "__main__": main()
