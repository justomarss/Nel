import json
import logging
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


logger = logging.getLogger(__name__)


def normalize_fact_key(key: str) -> str:
    normalized = unicodedata.normalize("NFKC", key).strip().casefold()
    normalized = re.sub(r"[^\w]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError("Fact key is empty after normalization.")
    return normalized


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    subject: Literal["user"]
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, key: str) -> str:
        return normalize_fact_key(key)

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

    def extract(self, text):
        prompt = self._build_prompt(text)
        response = self._generate_structured(prompt)
        envelope, error = self._validate(response)

        if envelope is None:
            repair_prompt = self._build_repair_prompt(text, response, error)
            response = self._generate_structured(repair_prompt)
            envelope, error = self._validate(response)

        if envelope is None:
            logger.warning(
                "Knowledge extraction failed after one repair attempt (%s). "
                "No facts stored.",
                error,
            )
            return {}

        return {fact.key: fact.value for fact in envelope.facts}

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
Extract only durable facts explicitly stated about the user.

Return only data matching this JSON schema:
{FACT_SCHEMA_TEXT}

Rules:
- Use subject "user" only. Exclude facts about Nel or other people.
- Write keys as concise, topic-neutral English snake_case identifiers.
- Copy each value literally from the user's text when possible.
- Do not expand abbreviations, translate, rename, or canonicalize values.
- Do not infer facts that are not explicitly stated.
- If the text contains no durable user fact, return an empty facts list.

User text:
{text}
"""

    @staticmethod
    def _build_repair_prompt(text, response, error):
        return f"""
Repair a failed durable-user-fact extraction.

Return only data matching this JSON schema:
{FACT_SCHEMA_TEXT}

Rules:
- Use subject "user" only.
- Preserve literal values from the original user text.
- Do not infer missing facts.
- Return an empty facts list when no durable user fact exists.

Original user text:
{text}

Invalid response:
{response}

Validation error:
{error}
"""
