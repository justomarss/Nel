import re
import unicodedata


def normalize_for_relevance(text: str) -> str:
    if not isinstance(text, str):
        return ""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("\N{COMBINING DOT ABOVE}", "")
    normalized = normalized.replace("_", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def relevance_tokens(text: str) -> tuple[str, ...]:
    normalized = normalize_for_relevance(text)
    return tuple(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


def relevance_tuple(
    user_message: str,
    value_or_text: str,
    key_or_title: str = "",
) -> tuple[int, int, int]:
    query = normalize_for_relevance(user_message)
    value = normalize_for_relevance(value_or_text)
    key = normalize_for_relevance(key_or_title)
    query_tokens = set(relevance_tokens(query))
    record_tokens = set(relevance_tokens(f"{key} {value}"))
    return (
        int(bool(value) and value in query),
        int(bool(key) and key in query),
        len(query_tokens.intersection(record_tokens)),
    )


def is_relevant(score: tuple[int, int, int]) -> bool:
    return any(score)
