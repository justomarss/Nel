import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


logger = logging.getLogger(__name__)


class MemoryWriteStatus(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    EMPTY = "empty"
    FAILURE = "failure"


MEMORY_WRITE_MESSAGES = {
    MemoryWriteStatus.ACCEPTED: "Yadda saxladım.",
    MemoryWriteStatus.DUPLICATE: "Bu yaddaş artıq mövcuddur.",
    MemoryWriteStatus.EMPTY: "Yadda saxlanacaq mətn boşdur.",
    MemoryWriteStatus.FAILURE: "Yaddaş saxlanıla bilmədi.",
}


@dataclass(frozen=True)
class MemoryWriteResult:
    status: MemoryWriteStatus
    message: str


def normalize_memory_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold().strip()
    return re.sub(r"\s+", " ", normalized, flags=re.UNICODE)


def memory_fingerprint(text: str) -> str:
    normalized = normalize_memory_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class MemoryService:
    """Validates and performs explicit durable-memory writes.

    Duplicate lookup and insertion are separate repository operations until a
    persisted fingerprint constraint exists. Concurrent writers can therefore
    race and insert the same normalized text.
    """

    def __init__(self, repository):
        self._repository = repository

    @property
    def repository(self):
        return self._repository

    def recall(self, limit=None):
        return self._repository.recall(limit=limit)

    def remember_explicit(self, text: str) -> MemoryWriteResult:
        if not isinstance(text, str) or not normalize_memory_text(text):
            return self._result(MemoryWriteStatus.EMPTY)

        candidate = memory_fingerprint(text)
        try:
            for existing in self._repository.recall():
                if (
                    isinstance(existing, str)
                    and memory_fingerprint(existing) == candidate
                ):
                    return self._result(MemoryWriteStatus.DUPLICATE)
            self._repository.remember(text)
        except Exception as exc:
            logger.error(
                "Explicit memory write failed (%s).",
                type(exc).__name__,
            )
            return self._result(MemoryWriteStatus.FAILURE)

        return self._result(MemoryWriteStatus.ACCEPTED)

    @staticmethod
    def _result(status: MemoryWriteStatus) -> MemoryWriteResult:
        return MemoryWriteResult(status, MEMORY_WRITE_MESSAGES[status])
