import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from .features import FeatureContext
from .normalization import normalize_text, remove_azerbaijani_diacritics
from .schema import validate_record


SPLIT_SEED = 25025


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def source_from_blueprint(path):
    rows = []
    for family in read_jsonl(path):
        for index, text in enumerate(family["representative_examples"], 1):
            rows.append({
                "id": f"SRC-{family['family_id']}-{index:02d}", "text": text,
                "intent_label": family["intent_label"], "source_family": family["family_id"],
                "semantic_pattern": family["construction_type"], "register": family["allowed_registers"][0],
                "language_mix": "az", "difficulty": "high" if family["generation_weight"] >= 8 else "normal",
                "contextual": False, "previous_user": "", "previous_assistant": "",
                "hard_negative_group": "", "correction_signal": family["family_id"] == "PAS-05",
                "generation_method": "reviewed_blueprint_example", "review_status": "reviewed",
                "lineage_id": f"LINEAGE-{family['family_id']}-{index:02d}",
                "high_risk": family["family_id"] in {"GLQ-07","GLQ-08","PFQ-06","PFQ-07","PPQ-04","MWR-05","GWR-03","GWR-05","GWR-06"},
            })
    return rows


def deterministic_split(rows):
    by_label_lineage = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_label_lineage[row["intent_label"]][row["lineage_id"]].append(row)
    result = []
    for label, lineages in sorted(by_label_lineage.items()):
        keys = sorted(lineages, key=lambda key: hashlib.sha256(f"{SPLIT_SEED}:final:{key}".encode()).hexdigest())
        count = len(keys)
        validation_count = max(1, round(count * .15))
        test_count = max(1, round(count * .15))
        for position, key in enumerate(keys):
            split = "validation" if position < validation_count else "test" if position < validation_count + test_count else "train"
            for row in lineages[key]:
                result.append({**row, "split": split})
    return sorted(result, key=lambda row: row["id"])


def augment(rows):
    augmented = []
    for row in rows:
        augmented.append(row)
        variants = []
        if any(ch in row["text"] for ch in "əçğıöşüƏÇĞİÖŞÜ"):
            variants.append(("diacritic_removal", remove_azerbaijani_diacritics(row["text"])))
        variants.append(("lowercase_punctuation", row["text"].lower().rstrip("?.!")))
        for index, (kind, text) in enumerate(variants, 1):
            if normalize_text(text) == normalize_text(row["text"]) and kind != "diacritic_removal":
                continue
            augmented.append({**row, "id": f"{row['id']}-A{index}", "text": text, "parent_id": row["id"], "augmentation": kind, "generation_method": "post_split_augmentation"})
    return augmented


def qc(rows):
    issues = [issue for row in rows for issue in validate_record(row)]
    ids = Counter(row["id"] for row in rows)
    issues.extend(("duplicate_id", key) for key, count in ids.items() if count > 1)
    exact = defaultdict(list)
    normalized = defaultdict(list)
    for row in rows:
        exact[row["text"]].append(row["id"])
        normalized[normalize_text(row["text"])].append(row["id"])
    return {
        "issues": issues,
        "exact_duplicates": {key: value for key, value in exact.items() if len(value) > 1},
        "normalized_duplicates": {key: value for key, value in normalized.items() if len(value) > 1},
    }


def contexts(rows):
    return [FeatureContext(row["text"], row.get("previous_user", ""), row.get("previous_assistant", "")) for row in rows]
