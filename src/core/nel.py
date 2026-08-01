import json
import logging
import threading

from src.brain.brain import Brain
from src.brain.providers import NvidiaNimProvider
from src.core.config import (
    ENABLE_BACKGROUND_THOUGHTS,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_INTERACTIVE_TIMEOUT_SECONDS,
    NVIDIA_MODEL,
    RAW_MEMORY_CONTEXT_LIMIT,
)
from src.errors import ApplicationError, ProviderError

from src.memory.memory import Memory

from src.core.state_manager import StateManager
from src.core.state import State
from src.core.clock import Clock
from src.core.decision_engine import DecisionEngine

from src.events.event_bus import EventBus

from src.services.thought_service import ThoughtService
from src.services.knowledge_service import KnowledgeService

from src.brain.intent_classifier import IntentClassifier


logger = logging.getLogger(__name__)


class Nel:
    def __init__(
        self,
        raw_memory_context_limit=RAW_MEMORY_CONTEXT_LIMIT,
        enable_background_thoughts=ENABLE_BACKGROUND_THOUGHTS,
        provider=None,
        memory_repository=None,
        knowledge_repository=None,
    ):
        if provider is None:
            provider = NvidiaNimProvider(
                model=NVIDIA_MODEL,
                api_key=NVIDIA_API_KEY,
                base_url=NVIDIA_BASE_URL,
                timeout=NVIDIA_INTERACTIVE_TIMEOUT_SECONDS,
            )

        self.brain = Brain(provider)
        self.memory = (
            memory_repository
            if memory_repository is not None
            else Memory()
        )
        self.state = StateManager()
        self.decision = DecisionEngine()
        self.intent = IntentClassifier()

        self.thought_service = ThoughtService(self.brain)
        self.knowledge = KnowledgeService(
            self.brain,
            repository=knowledge_repository,
        )
        self.raw_memory_context_limit = raw_memory_context_limit
        self.background_thoughts_enabled = enable_background_thoughts
        self._thought_lock = threading.Lock()

        self.events = EventBus()
        self.events.subscribe("clock_tick", self.on_clock_tick)

        self.clock = Clock(5, self.tick)
        self.clock.start()

    def think(self, prompt: str) -> str:
        self.state.set(State.THINKING)

        try:
            intent = self.intent.classify(prompt)

            if intent == "SEARCH_MEMORY":
                answer = self.knowledge.answer(prompt)

                if answer:
                    return answer

            if intent == "REMEMBER":
                self.knowledge.process(prompt)

            if self.brain.should_remember(prompt):
                self.memory.remember(prompt)

            memories = self.memory.recall(
                limit=self.raw_memory_context_limit,
            )
            memory_text = "\n".join(memories)
            structured_facts = json.dumps(
                self.knowledge.facts(),
                ensure_ascii=False,
                indent=2,
            )

            final_prompt = f"""
You are Nel.

Speak only Azerbaijani.

Structured user facts (authoritative; override conflicting long-term memories):
{structured_facts}

Long-term memories:
{memory_text}

Rules:
- User facts and long-term memories describe the user, not Nel, unless explicitly stored as Nel's own state.
- Never invent Nel's own preferences, memories, experiences, emotions, relationships, or personal history.
- If Nel has no stored preference, say it has not formed one yet.

User:
{prompt}

Nel:
"""

            return self.brain.think(final_prompt)

        except ProviderError:
            raise ApplicationError(
                "Model provayderi hazırda əlçatan deyil."
            ) from None

        finally:
            self.state.set(State.IDLE)

    def remember(self, text: str) -> None:
        self.memory.remember(text)

    def tick(self) -> None:
        self.events.emit("clock_tick")

    def stop(self) -> None:
        self.clock.stop()

    def on_clock_tick(self, data=None) -> None:
        if not self.background_thoughts_enabled:
            return

        if not self._thought_lock.acquire(blocking=False):
            return

        try:
            if not self.decision.should_think():
                return

            self.thought_service.generate()
        except Exception as exc:
            logger.error(
                "Background thought generation failed (%s).",
                type(exc).__name__,
            )
        finally:
            self._thought_lock.release()
