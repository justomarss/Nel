from dataclasses import dataclass


FOLLOW_UP_MARKERS = ("bəs", "onu", "bunu", "onda", "sonra", "indi", "davam", "formalaşdır", "niyə", "hansı")


@dataclass(frozen=True)
class FeatureContext:
    current: str
    previous_user: str = ""
    previous_assistant: str = ""
    previous_kind: str = "none"
    has_incomplete_exchange: bool = False


def build_feature_text(context: FeatureContext) -> str:
    current = context.current.strip()
    text = f"CURRENT: {current}"
    short_follow_up = len(current) <= 96 and any(marker in current.casefold() for marker in FOLLOW_UP_MARKERS)
    if not short_follow_up:
        return text
    if context.previous_user:
        text += f" PREVIOUS_USER: {context.previous_user[:256]}"
    if context.previous_assistant:
        text += f" PREVIOUS_ASSISTANT: {context.previous_assistant[:256]}"
    return text + f" PREVIOUS_KIND: {context.previous_kind} INCOMPLETE: {str(context.has_incomplete_exchange).lower()}"
