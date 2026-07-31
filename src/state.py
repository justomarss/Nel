from dataclasses import dataclass

@dataclass
class InternalState:
    curiosity: int = 70
    social: int = 40
    energy: int = 100
    boredom: int = 20
    focus: int = 60

    mood: str = "Neutral"

    current_goal: str | None = None
    current_task: str | None = None

    thinking_state: str = "Idle"

    confidence: int = 50
    stress: int = 0
    motivation: int = 50