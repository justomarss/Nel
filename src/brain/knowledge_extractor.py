import json
import logging
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.brain.local_intent_classifier import IntentType, LocalIntentClassifier
from src.errors import ProviderError
from src.knowledge.models import FactCandidate, GroundingEvidence
from src.persistence.normalization import normalize_fact_key


logger = logging.getLogger(__name__)

QUESTION_MARKS = frozenset({"?", "؟", "﹖", "？"})
LEADING_INTERROGATIVES = frozenset(
    {
        "nə",
        "nədir",
        "hansı",
        "hansıdır",
        "kim",
        "kimdir",
        "harada",
        "haradadır",
        "necə",
        "necədir",
        "niyə",
    }
)
INTERROGATIVE_TOKENS = frozenset(
    {"nə", "hansı", "kim", "harada", "necə", "niyə"}
)
QUESTION_ENDINGS = frozenset(
    {
        "var",
        "yoxdur",
        "nədir",
        "hansıdır",
        "kimdir",
        "haradadır",
        "necədir",
        "mı",
        "mi",
        "mu",
        "mü",
    }
)


def _question_tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("\N{COMBINING DOT ABOVE}", "")
    return tuple(re.findall(r"\w+", normalized, flags=re.UNICODE))


def is_interrogative_user_input(text: str) -> bool:
    if not isinstance(text, str) or not text.strip():
        return True
    normalized = unicodedata.normalize("NFKC", text)
    if any(mark in normalized for mark in QUESTION_MARKS):
        return True
    tokens = _question_tokens(normalized)
    if not tokens:
        return True
    leading_indefinite_time = tokens[:2] == ("nə", "vaxtsa")
    if tokens[0] in LEADING_INTERROGATIVES and not leading_indefinite_time:
        return True
    if tokens[-1] in QUESTION_ENDINGS:
        return True
    interrogative_positions = {
        index
        for index, token in enumerate(tokens)
        if token in INTERROGATIVE_TOKENS
    }
    if tokens[:1] == ("mənim",) and interrogative_positions:
        return True
    if any(
        tokens[index : index + 2] == ("nə", "vaxt")
        for index in range(len(tokens) - 1)
    ):
        return True
    return False


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    subject: Literal["user"]
    confidence: float = Field(ge=0.0, le=1.0)
    source_start: int = Field(ge=0)
    source_end: int = Field(gt=0)
    source_quote: str = Field(min_length=1)
    value_start: int = Field(ge=0)
    value_end: int = Field(gt=0)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, key: str) -> str:
        normalized = normalize_fact_key(key)
        if not normalized:
            raise ValueError("Fact key is empty after normalization.")
        return normalized

    @field_validator("value")
    @classmethod
    def reject_blank_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Fact value must not be blank.")
        return value


class FactEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    facts: list[ExtractedFact]


FACT_SCHEMA = FactEnvelope.model_json_schema()
FACT_SCHEMA_TEXT = json.dumps(FACT_SCHEMA, ensure_ascii=False)


class KnowledgeExtractor:
    def __init__(self, brain):
        self.brain = brain

    def extract(self, text) -> tuple[FactCandidate, ...]:
        if self._excluded_input(text):
            logger.info("Input excluded from fact candidate extraction.")
            return ()
        prompt = self._build_prompt(text)
        try:
            response = self._generate_structured(prompt)
        except ProviderError as exc:
            logger.warning(
                "Knowledge candidate extraction failed (%s).",
                type(exc).__name__,
            )
            return ()
        envelope, error = self._validate(response)
        if envelope is None:
            logger.warning(
                "Knowledge candidate extraction rejected (%s).",
                error,
            )
            return ()

        return tuple(
            FactCandidate(
                key=fact.key,
                value=fact.value,
                subject=fact.subject,
                confidence=fact.confidence,
                evidence=GroundingEvidence(
                    source_start=fact.source_start,
                    source_end=fact.source_end,
                    source_quote=fact.source_quote,
                    value_start=fact.value_start,
                    value_end=fact.value_end,
                ),
            )
            for fact in envelope.facts
        )

    def _generate_structured(self, prompt):
        generate_structured = getattr(
            self.brain.provider,
            "generate_structured",
            None,
        )
        if generate_structured is not None:
            return generate_structured(
                prompt,
                FACT_SCHEMA,
                "user_fact_extraction",
            )
        return self.brain.provider.generate(prompt)

    @staticmethod
    def _validate(response):
        try:
            data = json.loads(response)
        except json.JSONDecodeError as exc:
            return None, f"invalid JSON at position {exc.pos}"
        except TypeError:
            return None, "response was not text"

        try:
            return FactEnvelope.model_validate(data), None
        except ValidationError as exc:
            return None, f"schema validation failed with {exc.error_count()} error(s)"

    @staticmethod
    def _build_prompt(text):
        return f"""
Extract only durable fact candidates explicitly stated about the user.

Return only data matching this JSON schema:
{FACT_SCHEMA_TEXT}

Rules:
- Use subject "user" only. Exclude facts about Nel or other people.
- Write keys as concise, topic-neutral English snake_case identifiers.
- Copy each value exactly and literally from the user's text.
- Return Python Unicode code-point offsets for exact source and value spans.
- source_quote must equal text[source_start:source_end].
- value must equal text[value_start:value_end].
- The value span must be inside the source span.
- Do not expand abbreviations, translate, rename, trim, or canonicalize values.
- Do not infer facts that are not explicitly stated.
- If the text contains no durable user fact, return an empty facts list.

User text:
{text}
"""

    @staticmethod
    def _excluded_input(text) -> bool:
        if not isinstance(text, str) or not text.strip():
            return True
        if text.lstrip().startswith("/"):
            return True
        if is_interrogative_user_input(text):
            return True
        return (
            LocalIntentClassifier().classify(text)
            is not IntentType.CONVERSATION
        )
