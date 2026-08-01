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

from src.core.state_manager import StateManager
from src.core.state import State
from src.core.clock import Clock
from src.core.decision_engine import DecisionEngine

from src.events.event_bus import EventBus

from src.services.thought_service import ThoughtService
from src.services.knowledge_service import KnowledgeService

from src.brain.intent_classifier import IntentClassifier


logger = logging.getLogger(__name__)

IDENTITY_PREFERENCE_CONTEXT_LIMIT = 20
IDENTITY_CONTEXT_MAX_CHARS = 4096


class Nel:
    def __init__(
        self,
        raw_memory_context_limit=RAW_MEMORY_CONTEXT_LIMIT,
        enable_background_thoughts=ENABLE_BACKGROUND_THOUGHTS,
        provider=None,
        memory_repository=None,
        knowledge_repository=None,
        identity_service=None,
    ):
        if memory_repository is None or knowledge_repository is None:
            raise ValueError(
                "Memory and knowledge repositories must be injected."
            )

        if provider is None:
            provider = NvidiaNimProvider(
                model=NVIDIA_MODEL,
                api_key=NVIDIA_API_KEY,
                base_url=NVIDIA_BASE_URL,
                timeout=NVIDIA_INTERACTIVE_TIMEOUT_SECONDS,
            )

        self.brain = Brain(provider)
        self.memory = memory_repository
        self.identity = identity_service
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
            identity_context = self._identity_context()
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
            structured_identity = json.dumps(
                identity_context,
                ensure_ascii=False,
                separators=(",", ":"),
            )

            final_prompt = f"""
You are Nel.

Speak only Azerbaijani.

Nel identity snapshot (read-only):
{structured_identity}

Structured user facts (authoritative; override conflicting long-term memories):
{structured_facts}

Long-term memories:
{memory_text}

Rules:
- The Nel identity snapshot describes Nel, never the user.
- User facts and long-term memories describe the user, not Nel, unless explicitly stored as Nel's own state.
- Structured user facts cannot define or modify Nel's identity.
- Answer questions about Nel's identity only from the stored identity snapshot.
- When expressing stored identity fields in Azerbaijani, use natural first-person predicate agreement for Nel. Express the role directly as what Nel is, not as a possessive "my role is" construction.
- Do not invent identity details absent from the snapshot.
- Candidate preferences must not influence answers and are excluded from the snapshot.
- Provisional preferences are labeled provisional and must be described as provisional.
- Established preferences may influence answers as Nel's current stored preferences.
- Generated responses must never update identity.
- In the user's message, first-person forms such as "mən" and "mənim" refer to the user. When answering about user-owned facts, address the user with informal second-person forms such as "sən" and "sənin", never "siz" or "sizin". Use "mən" and "mənim" in Nel's answer only for Nel's own identity or state.
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

    def _identity_context(self) -> dict:
        identity_service = getattr(self, "identity", None)
        if identity_service is None:
            return {
                "identity_id": None,
                "display_name": None,
                "nature": None,
                "role": None,
                "established_preferences": {},
                "provisional_preferences": {},
            }

        snapshot = identity_service.snapshot()
        context = {
            "identity_id": snapshot.identity_id,
            "display_name": snapshot.display_name,
            "nature": snapshot.nature,
            "role": snapshot.role,
            "established_preferences": {},
            "provisional_preferences": {},
        }
        included = 0
        states = (
            ("established", "established_preferences"),
            ("provisional", "provisional_preferences"),
        )
        for state, section in states:
            records = sorted(
                (
                    record
                    for record in snapshot.preferences
                    if record.preference_state == state
                ),
                key=lambda record: record.key,
            )
            for record in records:
                if included >= IDENTITY_PREFERENCE_CONTEXT_LIMIT:
                    return context
                candidate = {
                    **context,
                    section: {
                        **context[section],
                        record.key: record.value,
                    },
                }
                serialized = json.dumps(
                    candidate,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                if len(serialized) > IDENTITY_CONTEXT_MAX_CHARS:
                    continue
                context = candidate
                included += 1
        return context

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
