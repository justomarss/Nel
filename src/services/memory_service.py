import logging
from dataclasses import dataclass
from enum import Enum

from src.context.models import MemoryContextSnapshot
from src.memory.normalization import memory_fingerprint, normalize_memory_text


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

    def context_snapshot(self, limit=1000) -> tuple[MemoryContextSnapshot, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("Memory context limit must be a non-negative integer.")
        reader = getattr(self._repository, "context_snapshot", None)
        if callable(reader):
            rows = reader(limit=limit)
            return tuple(
                MemoryContextSnapshot(
                    event_id=row["event_id"],
                    stored_at=row["stored_at"],
                    text=row["text"],
                )
                for row in rows
            )
        memories = self._repository.recall(limit=limit)
        return tuple(
            MemoryContextSnapshot(index, None, text)
            for index, text in enumerate(memories, start=1)
        )

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
