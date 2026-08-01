import re
import unicodedata


def normalize_fact_key(key: str) -> str:
    normalized = unicodedata.normalize("NFKC", key).strip().casefold()
    normalized = re.sub(r"[^\w]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized
