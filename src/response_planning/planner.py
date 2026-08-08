from src.brain.local_intent_classifier import LocalIntentClassifier
from src.conversation import ExchangeCompletion, RecentConversationSnapshot, RecentExchangeKind
from src.response_planning.models import ContinuitySource, IdentityPolicy, PersonalizationPolicy, ResponseDelivery, ResponsePlan, ResponsePurpose, ResponseReason


class ResponsePlanner:
    _CREATIVE_PREFIXES = ("mahnı yaz", "mahnı sözləri yaz", "hekayə yaz", "şeir yaz")
    _CONTINUATIONS = frozenset({"davam et", "kədərli olsun", "biraz qısalt", "daha ciddi yaz", "ikincisini dəyiş", "formalaşdır"})

    def __init__(self, local_intent_classifier=None):
        self.local_intent = local_intent_classifier or LocalIntentClassifier()

    def plan(self, user_input, recent_snapshot):
        normalized = self.local_intent.normalize(user_input)
        if normalized.startswith("öz kimliyini"):
            return ResponsePlan(ResponseDelivery.PROVIDER, ResponsePurpose.IDENTITY, IdentityPolicy.REQUIRED, PersonalizationPolicy.NONE, ContinuitySource.NONE, ResponseReason.EXPLICIT_IDENTITY)
        if normalized.startswith("sənin ən sevdiyin"):
            return ResponsePlan(ResponseDelivery.PROVIDER, ResponsePurpose.GENERAL, IdentityPolicy.REQUIRED, PersonalizationPolicy.OPTIONAL_STRUCTURED, ContinuitySource.NONE, ResponseReason.OWN_PREFERENCE_QUERY)
        if self._is_continuation(normalized, recent_snapshot):
            return self._provider(ResponsePurpose.CONTINUATION, ContinuitySource.IMMEDIATE_CONVERSATION, ResponseReason.IMMEDIATE_CONTINUATION)
        if normalized.startswith(self._CREATIVE_PREFIXES):
            return self._provider(ResponsePurpose.CREATIVE, ContinuitySource.NONE, ResponseReason.CREATIVE_REQUEST)
        return self._provider(ResponsePurpose.GENERAL, ContinuitySource.NONE, ResponseReason.GENERAL_INPUT)

    def safe_failure_plan(self):
        return self._provider(ResponsePurpose.GENERAL, ContinuitySource.NONE, ResponseReason.PLANNER_FAILURE)

    @staticmethod
    def _provider(purpose, continuity, reason):
        return ResponsePlan(ResponseDelivery.PROVIDER, purpose, IdentityPolicy.FORBIDDEN, PersonalizationPolicy.NONE, continuity, reason)

    @staticmethod
    def _is_continuation(normalized, snapshot):
        if normalized not in ResponsePlanner._CONTINUATIONS or not isinstance(snapshot, RecentConversationSnapshot) or not snapshot.exchanges:
            return False
        previous = snapshot.exchanges[-1]
        return previous.kind is RecentExchangeKind.CONVERSATION and previous.completion is ExchangeCompletion.COMPLETE
