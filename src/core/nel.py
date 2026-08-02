import logging
import re
import unicodedata
from time import monotonic
from uuid import uuid4

from src.brain.brain import Brain
from src.context import ContextAssembler, ContextBudget
from src.context.assembler import render_identity_value
from src.errors import (
    ApplicationError,
    ContextAssemblyError,
    PersistenceOperationError,
    ProviderError,
)

from src.core.state_manager import StateManager
from src.core.state import State
from src.core.clock import Clock
from src.core.decision_engine import (
    DecisionContext,
    DecisionEngine,
    DecisionType,
    EventKind,
    ExplicitCommandParse,
    USER_INPUT_MAX_CHARS,
)

from src.events.event_bus import EventBus
from src.goals import GoalCommandHandler

from src.services.thought_service import ThoughtService
from src.services.knowledge_service import KnowledgeService
from src.services.fact_commands import FactCommandHandler
from src.services.memory_service import MemoryService
from src.services.memory_commands import MemoryCommandHandler
from src.thoughts import ThoughtCoordinator, ThoughtWorker

from src.brain.intent_classifier import IntentClassifier
from src.brain.local_intent_classifier import IntentType, LocalIntentClassifier


logger = logging.getLogger(__name__)

BACKGROUND_THOUGHT_INTERVAL_SECONDS = 30

GOAL_CREATION_CLARIFICATION = (
    "Davamlı məqsəd yaratmaq üçün açıq /goal create əmri istifadə "
    "edilməlidir."
)

SYSTEM_INSTRUCTIONS = """You are Nel.

Speak only Azerbaijani.

The unified context JSON is read-only and contains all stored data available
to this provider request. No stored data exists elsewhere in this prompt.

Rules:
- Identity data describes Nel, never the user.
- User facts and memories describe the user, never Nel.
- Current structured user facts override conflicting memories when facts are available.
- Structured user facts cannot define or modify Nel's identity.
- Answer identity questions only from the identity object.
- Use identity.derived_display for controlled Azerbaijani rendering while preserving the stored meaning.
- Express Nel's role naturally as what Nel is, not as a possessive "my role is" construction.
- Do not invent identity details absent from context.
- Provisional preferences are explicitly provisional.
- Generated responses never update identity.
- Goals are read-only context and never authority to act.
- Generated output never creates, updates, completes, cancels, reopens, restores, or reports progress on goals.
- Ordinary conversation is not a goal command.
- In the user's message, first-person forms such as "mən" and "mənim" refer to the user.
- Address the user with informal second-person forms such as "sən" and "sənin", never "siz" or "sizin".
- Use "mən" and "mənim" in Nel's answer only for Nel's identity or state.
- Never invent Nel's preferences, memories, experiences, emotions, relationships, or personal history.
- If no relevant stored preference exists, say Nel has not formed one yet.
"""

FACT_CONTEXT_UNAVAILABLE_RULE = (
    "- User facts are unavailable for this turn. Do not invent, infer, or "
    "assert personal facts about the user.\n"
)


class Nel:
    def __init__(
        self,
        enable_background_thoughts=False,
        provider=None,
        memory_service=None,
        memory_repository=None,
        knowledge_repository=None,
        identity_service=None,
        goal_service=None,
        context_assembler=None,
        context_budget=None,
    ):
        if memory_service is not None and memory_repository is not None:
            raise ValueError(
                "Inject either MemoryService or a memory repository, not both."
            )
        if memory_service is None and memory_repository is not None:
            memory_service = MemoryService(memory_repository)
        if memory_service is None or knowledge_repository is None:
            raise ValueError(
                "Memory service and knowledge repository must be injected."
            )

        if provider is None:
            raise ProviderError("A provider must be injected into Nel.")

        self.brain = Brain(provider)
        self.memory = memory_service
        self.identity = identity_service
        self.goals = goal_service
        self.goal_commands = GoalCommandHandler(goal_service)
        self.state = StateManager()
        self.decision = DecisionEngine()
        self.intent = IntentClassifier()
        self.local_intent = LocalIntentClassifier()

        self.knowledge = KnowledgeService(
            self.brain,
            repository=knowledge_repository,
        )
        self.fact_commands = FactCommandHandler(self.knowledge)
        self.memory_commands = MemoryCommandHandler(self.memory)
        self.context_assembler = context_assembler or ContextAssembler(
            identity_service=self.identity,
            knowledge_service=self.knowledge,
            goal_service=self.goals,
            memory_service=self.memory,
            budget=context_budget or ContextBudget(),
            local_intent_classifier=self.local_intent,
        )
        self.thought_coordinator = ThoughtCoordinator(
            ThoughtWorker(provider),
        )
        self.thought_service = ThoughtService(
            self.thought_coordinator,
            memory=self.memory,
            knowledge=self.knowledge,
            identity=self.identity,
        )
        self.background_thoughts_enabled = enable_background_thoughts
        self._last_background_thought_at = monotonic()

        self.events = EventBus()
        self.events.subscribe("clock_tick", self.on_clock_tick)

        self.clock = Clock(5, self.tick)
        self.clock.start()

    def think(self, prompt: str) -> str:
        coordinator = getattr(self, "thought_coordinator", None)
        background_thought_state = (
            "idle" if coordinator is None else coordinator.state
        )
        operational_state = self._operational_state()
        goal_commands = getattr(self, "goal_commands", None)
        fact_commands = getattr(self, "fact_commands", None)
        memory_commands = getattr(self, "memory_commands", None)
        command_parse = ExplicitCommandParse.not_command()
        if (
            isinstance(prompt, str)
            and len(prompt) <= USER_INPUT_MAX_CHARS
        ):
            if goal_commands is not None and goal_commands.is_command(prompt):
                command_parse = goal_commands.inspect(prompt)
            elif fact_commands is not None and fact_commands.is_command(prompt):
                command_parse = fact_commands.inspect(prompt)
            elif (
                memory_commands is not None
                and memory_commands.is_command(prompt)
            ):
                command_parse = memory_commands.inspect(prompt)
        decision = self._decision_engine().decide(
            DecisionContext(
                event_id=uuid4().hex,
                event_kind=EventKind.USER_TURN,
                user_input=prompt,
                operational_state=operational_state,
                explicit_command_parse=command_parse,
                foreground_activity=True,
                background_thought_state=background_thought_state,
            )
        )
        allowed_foreground_routes = {
            DecisionType.GOAL_COMMAND,
            DecisionType.FACT_COMMAND,
            DecisionType.MEMORY_COMMAND,
            DecisionType.ASK_CLARIFICATION,
            DecisionType.CONVERSATION_RESPONSE,
        }
        if decision.primary_decision not in allowed_foreground_routes:
            return ""

        if coordinator is not None:
            coordinator.begin_foreground()

        try:
            self.state.set(State.THINKING)
            if decision.primary_decision is DecisionType.GOAL_COMMAND:
                return goal_commands.execute_payload(
                    decision.validated_command_payload
                )
            if decision.primary_decision is DecisionType.FACT_COMMAND:
                return fact_commands.execute_payload(
                    decision.validated_command_payload
                )
            if decision.primary_decision is DecisionType.MEMORY_COMMAND:
                return memory_commands.execute_payload(
                    decision.validated_command_payload
                )
            if decision.primary_decision is DecisionType.ASK_CLARIFICATION:
                if command_parse.command_kind == "fact":
                    return fact_commands.clarification_response(command_parse)
                if command_parse.command_kind == "memory":
                    return memory_commands.clarification_response(command_parse)
                return goal_commands.clarification_response(command_parse)

            local_classifier = getattr(self, "local_intent", None)
            if local_classifier is not None:
                if local_classifier.requires_explicit_goal_command(prompt):
                    return GOAL_CREATION_CLARIFICATION
                local_intent = local_classifier.classify(prompt)
                if local_intent is IntentType.GOAL_LIST:
                    return goal_commands.list_goals()
                if local_intent is IntentType.IDENTITY_QUERY:
                    return self._local_identity_response()
                if local_intent is IntentType.USER_FACT_QUERY:
                    return self._local_user_fact_response()

            intent = self.intent.classify(prompt)

            if intent == "SEARCH_MEMORY":
                answer = self.knowledge.answer(prompt)

                if answer:
                    return answer

            if intent == "REMEMBER":
                fact_proposals = self.knowledge.process(prompt)
            else:
                fact_proposals = ()

            context_result = self.context_assembler.assemble(prompt)
            final_prompt = self._conversation_prompt(prompt, context_result)

            response = self.brain.think(final_prompt)
            render_proposals = getattr(
                self.knowledge,
                "render_proposals",
                None,
            )
            proposal_guidance = (
                render_proposals(fact_proposals)
                if fact_proposals and callable(render_proposals)
                else ""
            )
            if proposal_guidance:
                return f"{response}\n\n{proposal_guidance}"
            return response

        except ProviderError:
            raise ApplicationError(
                "Model provayderi hazırda əlçatan deyil."
            ) from None

        finally:
            self.state.set(State.IDLE)
            if coordinator is not None:
                coordinator.end_foreground()

    def _local_identity_response(self) -> str:
        try:
            snapshot = self.identity.snapshot()
        except PersistenceOperationError:
            logger.error("Local identity read failed.")
            return "Nel kimliyi hazırda əlçatan deyil."
        fields = (
            ("Adım", snapshot.display_name),
            ("Təbiətim", render_identity_value("nature", snapshot.nature)),
            ("Rolum", render_identity_value("role", snapshot.role)),
        )
        parts = [f"{label}: {value}" for label, value in fields if value]
        if not parts:
            return "Nel kimliyi əlçatan deyil."
        return ". ".join(parts) + "."

    def _local_user_fact_response(self) -> str:
        try:
            facts = self.knowledge.facts()
        except PersistenceOperationError:
            logger.error("Local user-fact read failed.")
            return "İstifadəçi faktları hazırda əlçatan deyil."
        if not facts:
            return "Sənin haqqında saxlanmış strukturlaşdırılmış məlumat yoxdur."
        clauses = []
        for index, (key, value) in enumerate(sorted(facts.items())):
            owner = "Sənin " if index == 0 else ""
            clauses.append(
                f"{owner}{self._user_fact_label(key)} {value}-dir"
            )
        return " və ".join(clauses) + "."

    @staticmethod
    def _user_fact_label(key: str) -> str:
        normalized = unicodedata.normalize("NFKC", key).strip().casefold()
        tokens = tuple(token for token in re.split(r"[_\W]+", normalized) if token)
        if len(tokens) > 1 and tokens[0] == "favorite":
            return "ən sevdiyin " + " ".join(tokens[1:])
        readable = " ".join(tokens) or "naməlum"
        return f"{readable} məlumatın"

    def _conversation_prompt(self, prompt, context_result) -> str:
        reason_codes = set(
            context_result.bundle.truncation_metadata.omission_reason_codes
        )
        fact_rule = (
            FACT_CONTEXT_UNAVAILABLE_RULE
            if "fact_context_omitted" in reason_codes
            else ""
        )
        static_content = (
            SYSTEM_INSTRUCTIONS
            + fact_rule
            + "\nUnified context JSON:\n"
            + "\nUser:\n\nNel:\n"
        )
        budget = self.context_assembler.budget
        if len(static_content) > budget.system_instruction_characters:
            raise ContextAssemblyError("system_instructions_oversized")
        if len(prompt) > budget.user_message_characters:
            raise ContextAssemblyError("user_message_oversized")
        return (
            SYSTEM_INSTRUCTIONS
            + fact_rule
            + "\nUnified context JSON:\n"
            + context_result.canonical_json
            + "\n\nUser:\n"
            + prompt
            + "\n\nNel:\n"
        )

    def remember(self, text: str):
        return self.memory.remember_explicit(text)

    def _decision_engine(self) -> DecisionEngine:
        engine = getattr(self, "decision", None)
        return DecisionEngine() if engine is None else engine

    def _operational_state(self) -> str:
        state_manager = getattr(self, "state", None)
        getter = getattr(state_manager, "get", None)
        current = getter() if getter is not None else State.IDLE
        return getattr(current, "value", current)

    def _background_thought_due(self) -> bool:
        now = monotonic()
        last = getattr(self, "_last_background_thought_at", now)
        return now - last > BACKGROUND_THOUGHT_INTERVAL_SECONDS

    def tick(self) -> None:
        self.events.emit("clock_tick")

    def stop(self) -> None:
        self.clock.stop()
        self.thought_coordinator.shutdown()

    def on_clock_tick(self, data=None) -> None:
        if not self.background_thoughts_enabled:
            return

        if not self._background_thought_due():
            return

        try:
            coordinator = getattr(self, "thought_coordinator", None)
            context = DecisionContext(
                event_id=uuid4().hex,
                event_kind=EventKind.BACKGROUND_EVENT,
                user_input="",
                operational_state=self._operational_state(),
                explicit_command_parse=ExplicitCommandParse.not_command(),
                foreground_activity=(
                    False
                    if coordinator is None
                    else coordinator.foreground_active
                ),
                background_thought_state=(
                    "idle" if coordinator is None else coordinator.state
                ),
            )
            decision = self._decision_engine().decide(context)
            if decision.primary_decision is not DecisionType.THOUGHT_START:
                return

            if self.thought_service.generate():
                self._last_background_thought_at = monotonic()
        except Exception as exc:
            logger.error(
                "Background thought start failed (%s).",
                type(exc).__name__,
            )
