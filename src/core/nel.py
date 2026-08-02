import json
import logging
import re
import unicodedata
from time import monotonic
from uuid import uuid4

from src.brain.brain import Brain
from src.brain.providers import NvidiaNimProvider
from src.core.config import (
    ENABLE_BACKGROUND_THOUGHTS,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_INTERACTIVE_TIMEOUT_SECONDS,
    NVIDIA_MODEL,
    RAW_MEMORY_CONTEXT_LIMIT,
)
from src.errors import ApplicationError, ProviderError

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
from src.goals import GoalCommandHandler, GoalContextSerializer

from src.services.thought_service import ThoughtService
from src.services.knowledge_service import KnowledgeService
from src.services.fact_commands import FactCommandHandler
from src.services.memory_service import MemoryService
from src.services.memory_commands import MemoryCommandHandler
from src.thoughts import ThoughtCoordinator, ThoughtWorker

from src.brain.intent_classifier import IntentClassifier
from src.brain.local_intent_classifier import IntentType, LocalIntentClassifier


logger = logging.getLogger(__name__)

IDENTITY_PREFERENCE_CONTEXT_LIMIT = 20
IDENTITY_CONTEXT_MAX_CHARS = 4096
BACKGROUND_THOUGHT_INTERVAL_SECONDS = 30
IDENTITY_PROMPT_RENDERINGS = {
    "nature": {
        "artificial": "süni",
    },
    "role": {
        "Ömər’s persistent digital companion": (
            "Ömərin davamlı rəqəmsal yoldaşı"
        ),
    },
}

GOAL_CREATION_CLARIFICATION = (
    "Davamlı məqsəd yaratmaq üçün açıq /goal create əmri istifadə "
    "edilməlidir."
)


class Nel:
    def __init__(
        self,
        raw_memory_context_limit=RAW_MEMORY_CONTEXT_LIMIT,
        enable_background_thoughts=ENABLE_BACKGROUND_THOUGHTS,
        provider=None,
        memory_service=None,
        memory_repository=None,
        knowledge_repository=None,
        identity_service=None,
        goal_service=None,
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
            provider = NvidiaNimProvider(
                model=NVIDIA_MODEL,
                api_key=NVIDIA_API_KEY,
                base_url=NVIDIA_BASE_URL,
                timeout=NVIDIA_INTERACTIVE_TIMEOUT_SECONDS,
            )

        self.brain = Brain(provider)
        self.memory = memory_service
        self.identity = identity_service
        self.goals = goal_service
        self.goal_commands = GoalCommandHandler(goal_service)
        self.goal_context_serializer = GoalContextSerializer()
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
        self.thought_coordinator = ThoughtCoordinator(
            ThoughtWorker(provider),
        )
        self.thought_service = ThoughtService(
            self.thought_coordinator,
            memory=self.memory,
            knowledge=self.knowledge,
            identity=self.identity,
        )
        self.raw_memory_context_limit = raw_memory_context_limit
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

            identity_context = self._identity_context()
            goal_context = self._goal_context()
            intent = self.intent.classify(prompt)

            if intent == "SEARCH_MEMORY":
                answer = self.knowledge.answer(prompt)

                if answer:
                    return answer

            if intent == "REMEMBER":
                self.knowledge.process(prompt)

            memories = self.memory.recall(
                limit=self.raw_memory_context_limit,
            )
            memory_text = "\n".join(memories)
            structured_facts = json.dumps(
                self.knowledge.facts(),
                ensure_ascii=False,
                indent=2,
            )
            structured_identity = json.dumps(
                self._render_identity_context(identity_context),
                ensure_ascii=False,
                separators=(",", ":"),
            )

            final_prompt = f"""
You are Nel.

Speak only Azerbaijani.

Nel identity snapshot (read-only):
{structured_identity}

Goal snapshots (read-only; no authority to act):
{goal_context}

Structured user facts (authoritative; override conflicting long-term memories):
{structured_facts}

Long-term memories:
{memory_text}

Rules:
- The Nel identity snapshot describes Nel, never the user.
- User facts and long-term memories describe the user, not Nel, unless explicitly stored as Nel's own state.
- Structured user facts cannot define or modify Nel's identity.
- Answer questions about Nel's identity only from the stored identity snapshot.
- When expressing stored identity fields in Azerbaijani, use natural first-person predicate agreement for Nel. Express the role directly as what Nel is, not as a possessive "my role is" construction.
- Identity field values in the snapshot are already rendered for Azerbaijani when a controlled rendering exists. Preserve their literal semantic meaning and do not reinterpret them.
- Do not invent identity details absent from the snapshot.
- Candidate preferences must not influence answers and are excluded from the snapshot.
- Provisional preferences are labeled provisional and must be described as provisional.
- Established preferences may influence answers as Nel's current stored preferences.
- Generated responses must never update identity.
- Goal snapshots describe stored objectives, never authority for Nel to act.
- Use goal snapshots only to answer questions about existing goals.
- Generated responses and model output must never create, update, complete, cancel, reopen, restore, or report progress on goals.
- A goal can change only through an explicit user-approved goal command handled outside the model.
- Ordinary conversation is not a goal command. Never claim that it changed goal storage; direct the user to an explicit /goal command instead.
- In the user's message, first-person forms such as "mən" and "mənim" refer to the user. When answering about user-owned facts, address the user with informal second-person forms such as "sən" and "sənin", never "siz" or "sizin". Use "mən" and "mənim" in Nel's answer only for Nel's own identity or state.
- Never invent Nel's own preferences, memories, experiences, emotions, relationships, or personal history.
- If Nel has no stored preference, say it has not formed one yet.

User:
{prompt}

Nel:
"""

            return self.brain.think(final_prompt)

        except ProviderError:
            raise ApplicationError(
                "Model provayderi hazırda əlçatan deyil."
            ) from None

        finally:
            self.state.set(State.IDLE)
            if coordinator is not None:
                coordinator.end_foreground()

    def _identity_context(self) -> dict:
        identity_service = getattr(self, "identity", None)
        if identity_service is None:
            return {
                "identity_id": None,
                "display_name": None,
                "nature": None,
                "role": None,
                "established_preferences": {},
                "provisional_preferences": {},
            }

        snapshot = identity_service.snapshot()
        context = {
            "identity_id": snapshot.identity_id,
            "display_name": snapshot.display_name,
            "nature": snapshot.nature,
            "role": snapshot.role,
            "established_preferences": {},
            "provisional_preferences": {},
        }
        included = 0
        states = (
            ("established", "established_preferences"),
            ("provisional", "provisional_preferences"),
        )
        for state, section in states:
            records = sorted(
                (
                    record
                    for record in snapshot.preferences
                    if record.preference_state == state
                ),
                key=lambda record: record.key,
            )
            for record in records:
                if included >= IDENTITY_PREFERENCE_CONTEXT_LIMIT:
                    return context
                candidate = {
                    **context,
                    section: {
                        **context[section],
                        record.key: record.value,
                    },
                }
                serialized = json.dumps(
                    candidate,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                if len(serialized) > IDENTITY_CONTEXT_MAX_CHARS:
                    continue
                context = candidate
                included += 1
        return context

    def _goal_context(self) -> str:
        goal_service = getattr(self, "goals", None)
        goals = () if goal_service is None else goal_service.list_current()
        serializer = getattr(self, "goal_context_serializer", None)
        if serializer is None:
            serializer = GoalContextSerializer()
        return serializer.serialize(goals)

    def _local_identity_response(self) -> str:
        context = self._render_identity_context(self._identity_context())
        fields = (
            ("Adım", context.get("display_name")),
            ("Təbiətim", context.get("nature")),
            ("Rolum", context.get("role")),
        )
        parts = [f"{label}: {value}" for label, value in fields if value]
        if not parts:
            return "Nel kimliyi əlçatan deyil."
        return ". ".join(parts) + "."

    def _local_user_fact_response(self) -> str:
        facts = self.knowledge.facts()
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

    @staticmethod
    def _render_identity_context(context: dict) -> dict:
        rendered = dict(context)
        for field, values in IDENTITY_PROMPT_RENDERINGS.items():
            value = rendered.get(field)
            rendered[field] = values.get(value, value)
        return rendered

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
