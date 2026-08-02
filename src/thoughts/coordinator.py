import logging
import threading

from src.thoughts.policies import (
    IdentityPolicy,
    KnowledgePolicy,
    MemoryPolicy,
)


logger = logging.getLogger(__name__)


class ThoughtCoordinator:
    IDLE = "idle"
    RUNNING = "running"

    def __init__(
        self,
        worker,
        *,
        memory_policy=None,
        knowledge_policy=None,
        identity_policy=None,
    ):
        self.worker = worker
        self.memory_policy = memory_policy or MemoryPolicy()
        self.knowledge_policy = knowledge_policy or KnowledgePolicy()
        self.identity_policy = identity_policy or IdentityPolicy()
        self._lock = threading.Lock()
        self._state = self.IDLE
        self._generation = 0
        self._cancelled = None
        self._thread = None
        self._last_result = None
        self._foreground_active = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def foreground_active(self) -> bool:
        with self._lock:
            return self._foreground_active

    @property
    def last_result(self):
        with self._lock:
            return self._last_result

    def start(self, context) -> bool:
        with self._lock:
            if self._foreground_active:
                return False
            if self._state == self.RUNNING:
                return False
            if self._thread is not None and self._thread.is_alive():
                return False
            self._generation += 1
            generation = self._generation
            cancelled = threading.Event()
            self._cancelled = cancelled
            self._state = self.RUNNING
            self._last_result = None
            thread = threading.Thread(
                target=self._run,
                args=(generation, context, cancelled),
                name="nel-thought-worker",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return True

    def begin_foreground(self) -> bool:
        with self._lock:
            self._foreground_active = True
            return self._cancel_locked()

    def end_foreground(self) -> None:
        with self._lock:
            self._foreground_active = False

    def cancel_for_foreground(self) -> bool:
        with self._lock:
            return self._cancel_locked()

    def shutdown(self) -> None:
        self.begin_foreground()
        with self._lock:
            self._last_result = None

    def _cancel_locked(self) -> bool:
        if self._state != self.RUNNING:
            return False
        self._generation += 1
        if self._cancelled is not None:
            self._cancelled.set()
        self._state = self.IDLE
        self._last_result = None
        return True

    def wait(self, timeout=None) -> bool:
        with self._lock:
            thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _run(self, generation, context, cancelled) -> None:
        result = None
        try:
            result = self.worker.run(context, cancelled)
        except Exception as exc:
            logger.error(
                "Thought generation failed (%s).",
                type(exc).__name__,
            )
        finally:
            with self._lock:
                current = (
                    generation == self._generation
                    and self._state == self.RUNNING
                    and not cancelled.is_set()
                )
                if current:
                    if result is not None:
                        self.memory_policy.allows(result, context)
                        self.knowledge_policy.allows(result, context)
                        self.identity_policy.allows(result, context)
                    self._last_result = result
                    self._state = self.IDLE
                    self._cancelled = None
                if self._thread is threading.current_thread():
                    self._thread = None
