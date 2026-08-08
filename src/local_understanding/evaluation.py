import time
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, f1_score

from .features import build_feature_text


def raw_scores(classifier, contexts):
    return classifier.model.decision_function(classifier.features.transform([build_feature_text(item) for item in contexts]))


def evaluate(classifier, contexts, labels):
    started = time.perf_counter()
    predictions = [classifier.predict_one(item).intent or "UNKNOWN" for item in contexts]
    elapsed = time.perf_counter() - started
    known = [prediction if prediction != "UNKNOWN" else classifier.model.classes_[int(np.argmax(row))] for prediction, row in zip(predictions, raw_scores(classifier, contexts))]
    return {
        "macro_f1_with_forced_class": f1_score(labels, known, average="macro"),
        "report": classification_report(labels, known, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(labels, known, labels=classifier.model.classes_).tolist(),
        "classes": classifier.model.classes_.tolist(),
        "rejected": predictions.count("UNKNOWN"),
        "inference_seconds": elapsed,
        "prediction_count": len(predictions),
    }
