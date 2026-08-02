import logging
import shlex
from dataclasses import dataclass

from src.brain.knowledge_extractor import KnowledgeExtractor
from src.knowledge import (
    FactGroundingPolicy,
    FactProposal,
    FactProposalType,
    GroundingError,
)
from src.persistence.normalization import normalize_fact_key


logger = logging.getLogger(__name__)


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

    def __init__(self, brain, repository, grounding_policy=None):
        self.extractor = KnowledgeExtractor(brain)
        self.knowledge = repository
        self.grounding_policy = grounding_policy or FactGroundingPolicy()

    def process(self, text):
        candidates = self.extractor.extract(text)
        try:
            grounded = self.grounding_policy.validate_batch(text, candidates)
        except GroundingError as exc:
            logger.info(
                "Fact candidate batch rejected (%s).",
                exc.reason_code,
            )
            return ()
        return tuple(
            proposal
            for candidate in grounded
            if (proposal := self._classify(candidate)) is not None
        )

    def render_proposals(self, proposals) -> str:
        sections = []
        for proposal in proposals:
            if not isinstance(proposal, FactProposal):
                continue
            candidate = proposal.candidate
            sections.append(
                "Proposed, not stored "
                f"({proposal.proposal_type.value}):\n"
                f"{candidate.key} = {candidate.value}\n\n"
                "To store it, use:\n"
                f"/fact set {candidate.key} "
                f"--value {shlex.quote(candidate.value)} --confirm"
            )
        return "\n\n".join(sections)

    def _classify(self, candidate):
        current = self.knowledge.get(candidate.key)
        if current == candidate.value:
            return None
        if current is not None:
            proposal_type = FactProposalType.CORRECTION
        else:
            current_revision = next(
                (
                    revision
                    for revision in reversed(self.history(candidate.key))
                    if revision.is_current
                ),
                None,
            )
            proposal_type = (
                FactProposalType.REACTIVATION
                if current_revision is not None
                and current_revision.fact_state == "retired"
                else FactProposalType.NEW
            )
        return FactProposal(candidate, proposal_type)

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
