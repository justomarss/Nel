from dataclasses import dataclass


@dataclass(frozen=True)
class CommandExecutionResult:
    response: str
    completed: bool
