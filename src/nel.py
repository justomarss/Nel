from state import InternalState
from brain import Brain


class Nel:

    def __init__(self):

        self.name = "Nel"

        self.state = InternalState()

        self.brain = Brain()

    def think(self):

        action = self.brain.decide(self.state)

        print(f"[{self.name}]")

        print("Energy:", self.state.energy)

        print("Curiosity:", self.state.curiosity)

        print("Decision:", action.value)

        return action