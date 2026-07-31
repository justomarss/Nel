from enum import Enum


class State(Enum):
    IDLE = "idle"
    THINKING = "thinking"
    TALKING = "talking"
    BUSY = "busy"
    BORED = "bored"
    SLEEPING = "sleeping"