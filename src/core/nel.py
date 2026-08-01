from src.brain.brain import Brain
from src.brain.providers import NvidiaNimProvider
from src.core.config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL

from src.memory.memory import Memory

from src.core.state_manager import StateManager
from src.core.state import State
from src.core.clock import Clock
from src.core.decision_engine import DecisionEngine

from src.events.event_bus import EventBus

from src.services.thought_service import ThoughtService
from src.services.knowledge_service import KnowledgeService

from src.brain.intent_classifier import IntentClassifier


class Nel:
    def __init__(self):
        provider = NvidiaNimProvider(
            model=NVIDIA_MODEL,
            api_key=NVIDIA_API_KEY,
            base_url=NVIDIA_BASE_URL,
        )

        self.brain = Brain(provider)
        self.memory = Memory()
        self.state = StateManager()
        self.decision = DecisionEngine()
        self.intent = IntentClassifier()

        self.thought_service = ThoughtService(self.brain)
        self.knowledge = KnowledgeService(self.brain)

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

            memories = self.memory.recall()
            memory_text = "\n".join(memories)

            final_prompt = f"""
You are Nel.

Speak only Azerbaijani.

Long-term memories:
{memory_text}

User:
{prompt}

Nel:
"""

            return self.brain.think(final_prompt)

        finally:
            self.state.set(State.IDLE)

    def remember(self, text: str) -> None:
        self.memory.remember(text)

    def tick(self) -> None:
        self.events.emit("clock_tick")

    def on_clock_tick(self, data=None) -> None:
        if not self.decision.should_think():
            return

        self.thought_service.generate()
