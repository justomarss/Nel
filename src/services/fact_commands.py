import argparse
import re
import shlex
import unicodedata


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
            arguments = shlex.split(text.strip()[len(self.PREFIX) :].strip())
            if not arguments:
                raise FactCommandError("fact operation is required")
            command = self._parser.parse_args(arguments)
            if command.operation == "list":
                return self._list()
            if command.operation == "set":
                return self._set(command)
            if command.operation == "history":
                return self._history(command)
            return self._retire(command)
        except KeyError:
            return "Fakt tapılmadı."
        except (FactCommandError, ValueError, RuntimeError) as exc:
            return f"Fakt əmri rədd edildi: {exc}"

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
        return "Fakt istifadədən çıxarıldı." if changed else "Fakt artıq retired vəziyyətindədir."

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
