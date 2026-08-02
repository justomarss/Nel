from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class GroundingEvidence:
    source_start: int
    source_end: int
    source_quote: str
    value_start: int
    value_end: int


@dataclass(frozen=True)
class FactCandidate:
    key: str
    value: str
    subject: str
    confidence: float
    evidence: GroundingEvidence


class FactProposalType(str, Enum):
    NEW = "new"
    CORRECTION = "correction"
    REACTIVATION = "reactivation"


@dataclass(frozen=True)
class FactProposal:
    candidate: FactCandidate
    proposal_type: FactProposalType
