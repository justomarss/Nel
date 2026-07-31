from enum import Enum


class Action(Enum):
    DO_NOTHING = "do_nothing"
    THINK = "think"
    TALK = "talk"
    LEARN = "learn"
    OBSERVE = "observe"


class Brain:

    def decide(self, state):

        if state.energy < 20:
            return Action.DO_NOTHING

        if state.social > 70:
            return Action.TALK

        if state.curiosity > 70:
            return Action.LEARN

        return Action.THINK