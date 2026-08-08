from src.core.decision_engine import (
    ExplicitCommandParse,
    GoalCommandParseStatus,
)
from src.core.command_result import CommandExecutionResult
from src.services.memory_service import MemoryWriteStatus


class MemoryCommandHandler:
    PREFIX = "/remember"

    def __init__(self, memory_service):
        self._service = memory_service

    @classmethod
    def is_command(cls, text: str) -> bool:
        if not isinstance(text, str):
            return False
        return text == cls.PREFIX or (
            text.startswith(cls.PREFIX)
            and len(text) > len(cls.PREFIX)
            and text[len(cls.PREFIX)].isspace()
        )

    def inspect(self, text: str) -> ExplicitCommandParse:
        if not self.is_command(text):
            return ExplicitCommandParse.not_command()
        payload = self._payload(text)
        if not payload.strip():
            return ExplicitCommandParse(
                status=GoalCommandParseStatus.CLARIFICATION_REQUIRED,
                operation="remember",
                command_kind="memory",
            )
        return ExplicitCommandParse(
            status=GoalCommandParseStatus.CONFIRMED,
            operation="remember",
            arguments=(payload,),
            command_kind="memory",
        )

    @staticmethod
    def clarification_response(_command_parse=None) -> str:
        return "Yadda saxlanacaq boş olmayan mətni /remember əmrindən sonra yaz."

    def execute_payload(self, arguments) -> str:
        return self.execute_payload_result(arguments).response

    def execute_payload_result(self, arguments) -> CommandExecutionResult:
        if (
            not isinstance(arguments, tuple)
            or len(arguments) != 1
            or not isinstance(arguments[0], str)
        ):
            return CommandExecutionResult(
                self.clarification_response(),
                completed=False,
            )
        result = self._service.remember_explicit(arguments[0])
        return CommandExecutionResult(
            result.message,
            completed=result.status
            in {MemoryWriteStatus.ACCEPTED, MemoryWriteStatus.DUPLICATE},
        )

    @classmethod
    def _payload(cls, text: str) -> str:
        if text == cls.PREFIX:
            return ""
        return text[len(cls.PREFIX) + 1 :]
