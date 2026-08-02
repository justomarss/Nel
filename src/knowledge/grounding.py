import re
import unicodedata

from src.knowledge.models import FactCandidate, GroundingEvidence
from src.persistence.normalization import normalize_fact_key


FIRST_PERSON_TOKENS = frozenset({"mən", "mənim"})
NON_USER_OWNERSHIP_TOKENS = frozenset(
    {"onun", "onların", "sənin", "sizin"}
)
NESTED_POSSESSIVE_SUFFIXES = ("mın", "min", "mun", "mün")
NEGATION_TOKENS = frozenset({"deyil", "yox", "yoxdur"})
HISTORICAL_TOKENS = frozenset(
    {"əvvəl", "əvvəllər", "öncə", "keçmişdə", "idi"}
)
CURRENT_TOKENS = frozenset({"indi", "hazırda", "artıq"})
COMPARATIVE_TOKENS = frozenset({"daha", "nisbətən"})
CONTRAST_TOKENS = frozenset({"amma", "lakin", "ancaq"})
NEGATIVE_SUFFIXES = ("mıram", "mirəm", "muram", "mürəm")


class GroundingError(ValueError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("\N{COMBINING DOT ABOVE}", "")
    return tuple(re.findall(r"\w+", normalized, flags=re.UNICODE))


class FactGroundingPolicy:
    def validate_batch(
        self,
        user_text: str,
        candidates,
    ) -> tuple[FactCandidate, ...]:
        if not isinstance(user_text, str) or not user_text.strip():
            raise GroundingError("empty_user_text")
        if isinstance(candidates, (str, bytes)):
            raise GroundingError("invalid_candidate_batch")
        try:
            batch = tuple(candidates)
        except TypeError:
            raise GroundingError("invalid_candidate_batch") from None

        validated = []
        keys = set()
        for candidate in batch:
            self._validate_candidate(user_text, candidate)
            if candidate.key in keys:
                raise GroundingError("duplicate_normalized_key")
            keys.add(candidate.key)
            validated.append(candidate)
        return tuple(validated)

    def _validate_candidate(self, user_text: str, candidate) -> None:
        if not isinstance(candidate, FactCandidate):
            raise GroundingError("invalid_candidate")
        if candidate.subject != "user":
            raise GroundingError("unsupported_subject")
        if (
            isinstance(candidate.confidence, bool)
            or not isinstance(candidate.confidence, (int, float))
            or not 0.0 <= candidate.confidence <= 1.0
        ):
            raise GroundingError("invalid_confidence")
        if not isinstance(candidate.key, str) or not candidate.key:
            raise GroundingError("invalid_key")
        normalized_key = normalize_fact_key(candidate.key)
        if not normalized_key or normalized_key != candidate.key:
            raise GroundingError("invalid_key")
        if not isinstance(candidate.value, str) or not candidate.value:
            raise GroundingError("empty_value")
        if candidate.value != candidate.value.strip():
            raise GroundingError("transformed_value")

        evidence = candidate.evidence
        if not isinstance(evidence, GroundingEvidence):
            raise GroundingError("invalid_evidence")
        if not self._valid_span(
            getattr(evidence, "source_start", None),
            getattr(evidence, "source_end", None),
            len(user_text),
        ):
            raise GroundingError("invalid_source_bounds")
        if (
            not isinstance(evidence.source_quote, str)
            or not evidence.source_quote
        ):
            raise GroundingError("empty_source_quote")
        if (
            user_text[evidence.source_start : evidence.source_end]
            != evidence.source_quote
        ):
            raise GroundingError("source_quote_mismatch")
        if not self._valid_span(
            getattr(evidence, "value_start", None),
            getattr(evidence, "value_end", None),
            len(user_text),
        ):
            raise GroundingError("invalid_value_bounds")
        if not (
            evidence.source_start <= evidence.value_start
            and evidence.value_end <= evidence.source_end
        ):
            raise GroundingError("value_outside_source")
        if user_text[evidence.value_start : evidence.value_end] != candidate.value:
            raise GroundingError("literal_value_mismatch")

        self._validate_language(
            evidence.source_quote,
            evidence.value_start - evidence.source_start,
            evidence.value_end - evidence.source_start,
        )

    @staticmethod
    def _valid_span(start, end, text_length: int) -> bool:
        return (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and 0 <= start < end <= text_length
        )

    @staticmethod
    def _validate_language(source: str, value_start: int, value_end: int) -> None:
        source_tokens = _tokens(source)
        prefix_tokens = _tokens(source[:value_start])
        if not FIRST_PERSON_TOKENS.intersection(prefix_tokens):
            raise GroundingError("user_ownership_ambiguous")
        if NON_USER_OWNERSHIP_TOKENS.intersection(source_tokens):
            raise GroundingError("user_ownership_ambiguous")
        if any(
            token not in FIRST_PERSON_TOKENS
            and token.endswith(NESTED_POSSESSIVE_SUFFIXES)
            for token in prefix_tokens
        ):
            raise GroundingError("user_ownership_ambiguous")
        if NEGATION_TOKENS.intersection(source_tokens) or any(
            token.endswith(NEGATIVE_SUFFIXES) for token in source_tokens
        ):
            raise GroundingError("negated_evidence")
        if COMPARATIVE_TOKENS.intersection(source_tokens):
            raise GroundingError("comparative_evidence")

        suffix_tokens = _tokens(source[value_end:])
        current_before_value = bool(CURRENT_TOKENS.intersection(prefix_tokens))
        if CURRENT_TOKENS.intersection(suffix_tokens):
            raise GroundingError("historical_evidence")
        if (
            HISTORICAL_TOKENS.intersection(source_tokens)
            and not current_before_value
        ):
            raise GroundingError("historical_evidence")
        if (
            CONTRAST_TOKENS.intersection(source_tokens)
            and not current_before_value
        ):
            raise GroundingError("contradictory_evidence")
