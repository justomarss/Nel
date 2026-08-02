import argparse
import shlex
from uuid import uuid4

from src.core.decision_engine import (
    ExplicitCommandParse,
    GoalCommandParseStatus,
)
from src.goals.models import (
    GoalCandidate,
    GoalOwner,
    GoalPriority,
    GoalSourceKind,
    GoalState,
    ProgressVerification,
)
from src.goals.policy import GoalPolicyError
from src.goals.repository import (
    GoalNotFoundError,
    GoalRepositoryError,
    GoalVersionConflict,
)


class GoalCommandError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise GoalCommandError(message)


def _positive_version(value: str) -> int:
    try:
        version = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("version must be an integer") from None
    if version < 1:
        raise argparse.ArgumentTypeError("version must be positive")
    return version


def _percentage(value: str) -> int:
    try:
        percent = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("percent must be an integer") from None
    if not 0 <= percent <= 100:
        raise argparse.ArgumentTypeError("percent must be from 0 to 100")
    return percent


class GoalCommandHandler:
    PREFIX = "/goal"

    def __init__(self, service, *, reference_factory=lambda: uuid4().hex):
        self._service = service
        self._reference_factory = reference_factory
        self._parser = self._build_parser()

    @classmethod
    def is_command(cls, text: str) -> bool:
        stripped = text.strip()
        return stripped == cls.PREFIX or stripped.startswith(cls.PREFIX + " ")

    def inspect(self, text: str) -> ExplicitCommandParse:
        if not self.is_command(text):
            return ExplicitCommandParse.not_command()
        try:
            arguments = self._arguments(text)
            command = self._parser.parse_args(arguments)
            if self._requires_clarification(command):
                status = GoalCommandParseStatus.CLARIFICATION_REQUIRED
            else:
                status = GoalCommandParseStatus.CONFIRMED
            return ExplicitCommandParse(
                status=status,
                operation=command.operation,
                arguments=tuple(arguments),
            )
        except (GoalCommandError, ValueError):
            return ExplicitCommandParse(
                status=GoalCommandParseStatus.CLARIFICATION_REQUIRED,
            )

    @staticmethod
    def clarification_response(command_parse=None) -> str:
        operation = getattr(command_parse, "operation", None)
        if operation == "complete":
            return "Tamamlama üçün --accept-success təsdiqi tələb olunur."
        if operation == "progress":
            return (
                "İrəliləyiş üçün uyğun xülasə və tələb olunduqda "
                "--confirm təsdiqi verilməlidir."
            )
        return (
            "Məqsəd əmri natamamdır və ya tələb olunan təsdiq yoxdur. "
            "Əmri düzgün arqumentlər və təsdiqlə yenidən yaz."
        )

    def execute(self, text: str) -> str:
        if self._service is None:
            return "Məqsəd xidməti əlçatan deyil."
        try:
            return self.execute_payload(self._arguments(text))
        except GoalVersionConflict:
            return "Məqsəd versiyası dəyişib. Siyahını yenilə və yenidən cəhd et."
        except GoalNotFoundError:
            return "Məqsəd tapılmadı."
        except (GoalCommandError, GoalPolicyError, ValueError) as exc:
            return f"Məqsəd əmri rədd edildi: {exc}"
        except GoalRepositoryError:
            return "Məqsəd əmri yaddaşa yazıla bilmədi."

    def execute_payload(self, arguments) -> str:
        if self._service is None:
            return "Məqsəd xidməti əlçatan deyil."
        try:
            command = self._parser.parse_args(list(arguments))
            if self._requires_clarification(command):
                return self.clarification_response(
                    self.inspect(self.PREFIX + " " + shlex.join(arguments))
                )
            return self._dispatch(command)
        except GoalVersionConflict:
            return "Məqsəd versiyası dəyişib. Siyahını yenilə və yenidən cəhd et."
        except GoalNotFoundError:
            return "Məqsəd tapılmadı."
        except (GoalCommandError, GoalPolicyError, ValueError) as exc:
            return f"Məqsəd əmri rədd edildi: {exc}"
        except GoalRepositoryError:
            return "Məqsəd əmri yaddaşa yazıla bilmədi."

    @classmethod
    def _arguments(cls, text: str):
        if not cls.is_command(text):
            raise GoalCommandError("goal command is required")
        arguments = shlex.split(text.strip()[len(cls.PREFIX):].strip())
        if not arguments:
            raise GoalCommandError("goal operation is required")
        return arguments

    @staticmethod
    def _requires_clarification(command) -> bool:
        if command.operation == "complete":
            return not command.accept_success
        if command.operation == "progress":
            verification = ProgressVerification(command.verification)
            if verification is ProgressVerification.UNKNOWN:
                return command.summary is not None or command.percent is not None
            return not command.confirm or not command.summary
        if command.operation == "create":
            return (
                not command.title.strip()
                or not command.success.strip()
                or (
                    command.description is not None
                    and not command.description.strip()
                )
            )
        if command.operation in {"reopen", "restore"}:
            return not command.reason.strip()
        return False

    def _dispatch(self, command) -> str:
        operation = command.operation
        if operation == "create":
            return self._create(command)
        if operation == "list":
            return self._list()
        if operation == "progress":
            return self._progress(command)
        if operation in {"reopen", "restore"}:
            return self._activate_terminal(command)
        return self._update_state(command)

    def _create(self, command) -> str:
        reference = self._reference("create")
        goal = self._service.create(
            GoalCandidate(
                title=command.title,
                description=command.description,
                success_condition=command.success,
                owner=GoalOwner.USER,
                priority=GoalPriority(command.priority),
                deadline=command.deadline,
                source_kind=GoalSourceKind.VALIDATED_USER.value,
                source_reference=reference,
            ),
            explicit_user_approval=True,
            approval_reference=reference,
        )
        return self._changed("Məqsəd əlavə edildi", goal)

    def _list(self) -> str:
        goals = tuple(
            goal
            for goal in self._service.list_current()
            if goal.state in {GoalState.ACTIVE, GoalState.PAUSED}
        )
        if not goals:
            return "Aktiv və ya dayandırılmış məqsəd yoxdur."
        lines = ["Aktiv və dayandırılmış məqsədlər:"]
        for goal in goals:
            lines.append(
                f"- {goal.title} [ID: {goal.goal_id}; "
                f"vəziyyət: {goal.state.value}; versiya: {goal.version}]"
            )
        return "\n".join(lines)

    def _update_state(self, command) -> str:
        states = {
            "pause": GoalState.PAUSED,
            "resume": GoalState.ACTIVE,
            "complete": GoalState.COMPLETED,
            "cancel": GoalState.CANCELLED,
        }
        labels = {
            "pause": "Məqsəd dayandırıldı",
            "resume": "Məqsəd davam etdirildi",
            "complete": "Məqsəd tamamlandı",
            "cancel": "Məqsəd ləğv edildi",
        }
        if command.operation == "complete" and not command.accept_success:
            raise GoalCommandError(
                "completion requires --accept-success confirmation"
            )
        self._require_version(command.goal_id, command.version)
        reference = self._reference(command.operation)
        goal = self._service.update(
            command.goal_id,
            {"state": states[command.operation]},
            expected_version=command.version,
            source_kind=GoalSourceKind.VALIDATED_USER.value,
            source_reference=reference,
            explicit_user_approval=True,
            approval_reference=reference,
            revision_reason=f"Explicit {command.operation} command.",
            success_condition_accepted=(command.operation == "complete"),
        )
        return self._changed(labels[command.operation], goal)

    def _activate_terminal(self, command) -> str:
        self._require_version(command.goal_id, command.version)
        reference = self._reference(command.operation)
        method = (
            self._service.reopen
            if command.operation == "reopen"
            else self._service.restore
        )
        goal = method(
            command.goal_id,
            expected_version=command.version,
            source_reference=reference,
            explicit_user_approval=True,
            approval_reference=reference,
            revision_reason=command.reason,
        )
        label = (
            "Tamamlanmış məqsəd yenidən açıldı"
            if command.operation == "reopen"
            else "Ləğv edilmiş məqsəd bərpa edildi"
        )
        return self._changed(label, goal)

    def _progress(self, command) -> str:
        verification = ProgressVerification(command.verification)
        if verification is not ProgressVerification.UNKNOWN and not command.confirm:
            raise GoalCommandError(
                "accepted progress requires --confirm user confirmation"
            )
        self._require_version(command.goal_id, command.version)
        reference = self._reference("progress")
        goal = self._service.update(
            command.goal_id,
            {
                "progress_summary": command.summary,
                "progress_percent": command.percent,
                "progress_verification": verification,
            },
            expected_version=command.version,
            source_kind=GoalSourceKind.VALIDATED_USER.value,
            source_reference=reference,
            explicit_user_approval=True,
            approval_reference=reference,
            revision_reason="Explicit progress report command.",
            owner_confirmation=command.confirm,
        )
        return self._changed("Məqsəd irəliləyişi yeniləndi", goal)

    def _reference(self, operation: str) -> str:
        return f"cli:{operation}:{self._reference_factory()}"

    def _require_version(self, goal_id: str, expected_version: int) -> None:
        current = self._service.get(goal_id)
        if current is None:
            raise GoalNotFoundError("Goal does not exist.")
        if current.version != expected_version:
            raise GoalVersionConflict("Goal version changed.")

    @staticmethod
    def _changed(label: str, goal) -> str:
        return (
            f"{label}: {goal.title} "
            f"[ID: {goal.goal_id}; versiya: {goal.version}]."
        )

    @staticmethod
    def _build_parser():
        parser = _Parser(add_help=False)
        commands = parser.add_subparsers(dest="operation", required=True)

        create = commands.add_parser("create", add_help=False)
        create.add_argument("--title", required=True)
        create.add_argument("--success", required=True)
        create.add_argument("--description")
        create.add_argument(
            "--priority",
            choices=[priority.value for priority in GoalPriority],
            default=GoalPriority.NORMAL.value,
        )
        create.add_argument("--deadline")

        commands.add_parser("list", add_help=False)

        for operation in ("pause", "resume", "cancel"):
            update = commands.add_parser(operation, add_help=False)
            update.add_argument("goal_id")
            update.add_argument("--version", type=_positive_version, required=True)

        complete = commands.add_parser("complete", add_help=False)
        complete.add_argument("goal_id")
        complete.add_argument("--version", type=_positive_version, required=True)
        complete.add_argument("--accept-success", action="store_true")

        for operation in ("reopen", "restore"):
            activate = commands.add_parser(operation, add_help=False)
            activate.add_argument("goal_id")
            activate.add_argument("--version", type=_positive_version, required=True)
            activate.add_argument("--reason", required=True)

        progress = commands.add_parser("progress", add_help=False)
        progress.add_argument("goal_id")
        progress.add_argument("--version", type=_positive_version, required=True)
        progress.add_argument(
            "--verification",
            choices=[state.value for state in ProgressVerification],
            required=True,
        )
        progress.add_argument("--summary")
        progress.add_argument("--percent", type=_percentage)
        progress.add_argument("--confirm", action="store_true")

        return parser
