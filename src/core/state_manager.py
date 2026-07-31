from .state import State


class StateManager:

    def __init__(self):
        self.state = State.IDLE

    def get(self):
        return self.state

    def set(self, new_state):
        print(f"[STATE] {self.state.value} -> {new_state.value}")
        self.state = new_state