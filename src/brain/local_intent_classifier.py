import re
import unicodedata
from enum import Enum


class IntentType(str, Enum):
    GOAL_LIST = "goal_list"
    IDENTITY_QUERY = "identity_query"
    USER_FACT_QUERY = "user_fact_query"
    CONVERSATION = "conversation"


class LocalIntentClassifier:
    _GOAL_LIST_PHRASES = frozenset(
        {
            "məqsədlərim nədir",
            "məqsədlərimi göstər",
            "məqsədlərim hansılardır",
            "mənim hədəflərim hansılardır",
            "nə məqsədlərim var",
        }
    )
    _IDENTITY_PHRASES = frozenset(
        {
            "sən kimsən",
            "adın nədir",
            "sən nəsan",
            "sən nəsən",
        }
    )
    _USER_FACT_PHRASES = frozenset(
        {
            "mənim haqqında nə bilirsən",
        }
    )
    _FAVORITE_FACT_QUERY = re.compile(
        r"^mənim ən sevdiyim .+ (?:nədir|hansıdır)$"
    )

    def classify(self, text: str) -> IntentType:
        normalized = self.normalize(text)
        if normalized in self._GOAL_LIST_PHRASES:
            return IntentType.GOAL_LIST
        if normalized in self._IDENTITY_PHRASES:
            return IntentType.IDENTITY_QUERY
        if (
            normalized in self._USER_FACT_PHRASES
            or self._FAVORITE_FACT_QUERY.fullmatch(normalized)
        ):
            return IntentType.USER_FACT_QUERY
        return IntentType.CONVERSATION

    def requires_explicit_goal_command(self, text: str) -> bool:
        normalized = self.normalize(text)
        return (
            normalized.startswith("məqsədim ")
            or normalized.startswith("mən istəyirəm ki ")
            or (
                normalized.startswith("gələcəkdə ")
                and " istəyirəm" in normalized
            )
        )

    @staticmethod
    def normalize(text: str) -> str:
        if not isinstance(text, str):
            return ""
        normalized = unicodedata.normalize("NFKC", text).casefold()
        normalized = normalized.replace("\N{COMBINING DOT ABOVE}", "")
        normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
        return re.sub(r"\s+", " ", normalized).strip()
