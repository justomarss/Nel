from src.brain.brain import Brain
from src.brain.providers import OllamaProvider
from src.core.config import MODEL_NAME

from src.memory.memory import Memory
from src.memory.thoughts import Thoughts

from src.core.state_manager import StateManager
from src.core.state import State
from src.core.clock import Clock
from src.core.decision_engine import DecisionEngine

from src.events.event_bus import EventBus


class Nel:

    def __init__(self):

        provider = OllamaProvider(MODEL_NAME)

        self.brain = Brain(provider)

        self.memory = Memory()
        self.thoughts = Thoughts()

        self.state = StateManager()

        self.decision = DecisionEngine()

        self.events = EventBus()
        self.events.subscribe("clock_tick", self.on_clock_tick)

        self.clock = Clock(5, self.tick)
        self.clock.start()

    def think(self, prompt: str):

        self.state.set(State.THINKING)

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

        response = self.brain.think(final_prompt)

        self.state.set(State.IDLE)

        return response

    def remember(self, text):
        self.memory.remember(text)

    def tick(self):
        self.events.emit("clock_tick")

    def on_clock_tick(self, data):

        if not self.decision.should_think():
            return

        thought = self.brain.internal_monologue()

        self.thoughts.add(thought)

        print("[THOUGHT]", thought)