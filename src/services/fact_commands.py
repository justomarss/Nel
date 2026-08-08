import argparse
import re
import shlex
import unicodedata

from src.core.decision_engine import (
    ExplicitCommandParse,
    GoalCommandParseStatus,
)
from src.core.command_result import CommandExecutionResult
from src.errors import PersistenceOperationError


class FactCommandError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise FactCommandError(message)


def readable_fact_label(key: str) -> str:
    normalized = unicodedata.normalize("NFKC", key).strip()
    label = re.sub(r"[_\-]+", " ", normalized)
    label = re.sub(r"\s+", " ", label).strip()
    return label or "naməlum fakt"


class FactCommandHandler:
    PREFIX = "/fact"

    def __init__(self, knowledge_service):
        self._service = knowledge_service
        self._parser = self._build_parser()

    @classmethod
    def is_command(cls, text: str) -> bool:
        stripped = text.strip()
        return stripped == cls.PREFIX or stripped.startswith(cls.PREFIX + " ")

    def execute(self, text: str) -> str:
        try:
            return self.execute_payload(self._arguments(text))
        except KeyError:
            return "Fakt tapılmadı."
        except PersistenceOperationError:
            return "Fakt xidməti hazırda əlçatan deyil."
        except (FactCommandError, ValueError) as exc:
            return f"Fakt əmri rədd edildi: {exc}"

    def inspect(self, text: str) -> ExplicitCommandParse:
        if not self.is_command(text):
            return ExplicitCommandParse.not_command()
        try:
            arguments = self._arguments(text)
            command = self._parser.parse_args(arguments)
            status = (
                GoalCommandParseStatus.CLARIFICATION_REQUIRED
                if self._requires_confirmation(command)
                else GoalCommandParseStatus.CONFIRMED
            )
            return ExplicitCommandParse(
                status=status,
                operation=command.operation,
                arguments=tuple(arguments),
                command_kind="fact",
            )
        except (FactCommandError, ValueError):
            return ExplicitCommandParse(
                status=GoalCommandParseStatus.CLARIFICATION_REQUIRED,
                command_kind="fact",
            )

    @staticmethod
    def clarification_response(_command_parse=None) -> str:
        return (
            "Fakt əmri natamamdır və ya tələb olunan --confirm təsdiqi "
            "yoxdur. Əmri düzgün arqumentlərlə yenidən yaz."
        )

    def execute_payload(self, arguments) -> str:
        return self.execute_payload_result(arguments).response

    def execute_payload_result(self, arguments) -> CommandExecutionResult:
        try:
            command = self._parser.parse_args(list(arguments))
            if command.operation == "list":
                response = self._list()
            elif command.operation == "set":
                response = self._set(command)
            elif command.operation == "history":
                response = self._history(command)
            else:
                response = self._retire(command)
            return CommandExecutionResult(response, completed=True)
        except KeyError:
            return CommandExecutionResult("Fakt tapılmadı.", completed=False)
        except PersistenceOperationError:
            return CommandExecutionResult(
                "Fakt xidməti hazırda əlçatan deyil.",
                completed=False,
            )
        except (FactCommandError, ValueError) as exc:
            return CommandExecutionResult(
                f"Fakt əmri rədd edildi: {exc}",
                completed=False,
            )

    @classmethod
    def _arguments(cls, text: str):
        if not cls.is_command(text):
            raise FactCommandError("fact command is required")
        arguments = shlex.split(text.strip()[len(cls.PREFIX) :].strip())
        if not arguments:
            raise FactCommandError("fact operation is required")
        return arguments

    @staticmethod
    def _requires_confirmation(command) -> bool:
        return command.operation in {"set", "retire"} and not command.confirm

    def _list(self) -> str:
        facts = self._service.facts()
        if not facts:
            return "Aktiv istifadəçi faktı yoxdur."
        lines = ["Aktiv istifadəçi faktları:"]
        for key, value in sorted(facts.items()):
            lines.append(f"- {readable_fact_label(key)} [{key}]: {value}")
        return "\n".join(lines)

    def _set(self, command) -> str:
        if not command.confirm:
            raise FactCommandError("--confirm is required")
        changed = self._service.correct_fact(
            command.fact_key,
            command.value,
            confirmed=True,
        )
        return "Fakt yeniləndi." if changed else "Fakt dəyişmədi."

    def _history(self, command) -> str:
        revisions = self._service.history(command.fact_key)
        if not revisions:
            return "Fakt tarixçəsi tapılmadı."
        lines = [f"Fakt tarixçəsi [{command.fact_key}]:"]
        for revision in revisions:
            reason = (
                f"; səbəb: {revision.revision_reason}"
                if revision.revision_reason
                else ""
            )
            current = "; cari" if revision.is_current else ""
            lines.append(
                f"- v{revision.version}; {revision.fact_state}{current}; "
                f"dəyər: {revision.value}{reason}"
            )
        return "\n".join(lines)

    def _retire(self, command) -> str:
        if not command.confirm:
            raise FactCommandError("--confirm is required")
        changed = self._service.retire_fact(
            command.fact_key,
            confirmed=True,
            reason=command.reason,
        )
        return (
            "Fakt istifadədən çıxarıldı."
            if changed
            else "Fakt artıq retired vəziyyətindədir."
        )

    @staticmethod
    def _build_parser():
        parser = _Parser(prog="/fact", add_help=False)
        operations = parser.add_subparsers(dest="operation", required=True)
        operations.add_parser("list", add_help=False)

        set_parser = operations.add_parser("set", add_help=False)
        set_parser.add_argument("fact_key")
        set_parser.add_argument("--value", required=True)
        set_parser.add_argument("--confirm", action="store_true")

        history_parser = operations.add_parser("history", add_help=False)
        history_parser.add_argument("fact_key")

        retire_parser = operations.add_parser("retire", add_help=False)
        retire_parser.add_argument("fact_key")
        retire_parser.add_argument("--confirm", action="store_true")
        retire_parser.add_argument("--reason", required=True)
        return parser
