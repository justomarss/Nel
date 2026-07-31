from src.memory.thoughts import Thoughts


class ThoughtService:

    def __init__(self, brain):
        self.brain = brain
        self.thoughts = Thoughts()

    def generate(self):

        thought = self.brain.internal_monologue()

        self.thoughts.add(thought)

        print("[THOUGHT]", thought)