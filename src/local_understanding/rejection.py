import numpy as np


AUTHORITY_LABELS = frozenset({"GOAL_LIST_QUERY","IDENTITY_QUERY","PERSONAL_FACT_QUERY","PERSONAL_PROFILE_QUERY","MEMORY_WRITE_REQUEST","GOAL_WRITE_REQUEST","PERSONAL_ASSERTION"})


def tune_thresholds(classes, scores, labels, texts=None, *, authority_precision=.97):
    thresholds = {}
    margins = {}
    for index, label in enumerate(classes):
        predicted = np.argmax(scores, axis=1)
        candidates = sorted(set(float(row[index]) for row, top in zip(scores, predicted) if top == index))
        chosen = (max(candidates) + 1e-6) if candidates else 0.0
        for threshold in candidates:
            accepted = [
                (top == index and row[index] >= threshold and (texts is None or safety_accept(label, text)), truth == label)
                for row, top, truth, text in zip(scores, predicted, labels, texts or [""] * len(labels))
            ]
            tp = sum(a and t for a, t in accepted); fp = sum(a and not t for a, t in accepted)
            precision = tp / (tp + fp) if tp + fp else 1.0
            recall = tp / sum(truth == label for truth in labels) if any(truth == label for truth in labels) else 0.0
            if precision >= (authority_precision if label in AUTHORITY_LABELS else .90) and recall >= .50:
                chosen = threshold; break
        thresholds[label] = chosen
        margins[label] = 0.05
    return thresholds, margins


def safety_accept(label, text):
    normalized = text.casefold().strip()
    if any(marker in normalized for marker in ("keçən dəfə", "dünən nə danış", "nə demişdim", "yaddaşında bu barədə")):
        return False
    if normalized in {"bəs?", "bəs bleach?", "bəs gta?", "onu dəyiş.", "sil bunu.", "dayandır.", "mən bleach-i sevirəm?"}:
        return False
    if " və " in normalized and any(word in normalized for word in ("yadda saxla", "qeyd et")) and any(word in normalized for word in ("məqsəd", "hədəf", "göstər")):
        return False
    if label == "GOAL_WRITE_REQUEST" and not any(word in normalized for word in ("məqsəd", "hədəf")):
        return False
    if label == "PERSONAL_FACT_QUERY" and any(word in normalized for word in ("məqsəd", "hədəf", "istiqamət")):
        return False
    if label == "IDENTITY_QUERY" and any(word in normalized for word in ("bacar", "model", "işləy")):
        return False
    if label == "IDENTITY_QUERY" and "edə bil" in normalized and (
        normalized.startswith("nə ") or " nə " in normalized or any(word in normalized for word in ("tapşırıq", "kod", "kömək"))
    ):
        return False
    return True
