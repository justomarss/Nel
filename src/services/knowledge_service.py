from dataclasses import dataclass

from src.brain.knowledge_extractor import KnowledgeExtractor
from src.persistence.normalization import normalize_fact_key


@dataclass(frozen=True)
class FactRevision:
    key: str
    value: str
    version: int
    fact_state: str
    revision_reason: str | None
    updated_at: str
    is_current: bool


class KnowledgeService:

    def __init__(self, brain, repository):
        self.extractor = KnowledgeExtractor(brain)
        self.knowledge = repository

    def process(self, text):

        facts = self.extractor.extract(text)

        if not isinstance(facts, dict):
            return

        set_many = getattr(self.knowledge, "set_many", None)
        if callable(set_many):
            batch = [
                {"key": key, "value": value, "subject": "user"}
                for key, value in facts.items()
            ]
            if batch:
                set_many(batch)
            return

        for key, value in facts.items():
            self.knowledge.set(key, value)

    def get(self, key):
        return self.knowledge.get(key)

    def facts(self):
        return self.knowledge.load()

    def correct_fact(self, key, value, *, confirmed=False):
        if not confirmed:
            raise ValueError("Fact correction requires explicit confirmation.")
        if not isinstance(value, str):
            raise ValueError("Fact value must be a string.")
        normalized_key = normalize_fact_key(key)
        if not normalized_key:
            raise ValueError("Fact key must be non-empty.")
        before = self.knowledge.get(normalized_key)
        self.knowledge.set(normalized_key, value)
        return before != value

    def retire_fact(self, key, *, confirmed=False, reason=None):
        if not confirmed:
            raise ValueError("Fact retirement requires explicit confirmation.")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Fact retirement requires a non-empty reason.")
        retire = getattr(self.knowledge, "retire", None)
        if not callable(retire):
            raise RuntimeError("Fact retirement is unavailable.")
        return retire(key, reason)

    def history(self, key):
        history = getattr(self.knowledge, "history", None)
        if not callable(history):
            return ()
        return tuple(
            FactRevision(
                key=row["fact_key"],
                value=row["value"],
                version=row["version"],
                fact_state=row["fact_state"],
                revision_reason=row["revision_reason"],
                updated_at=row["updated_at"],
                is_current=bool(row["is_current"]),
            )
            for row in history(key)
        )

    def answer(self, text):
        return None
