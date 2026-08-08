import re

from src.response_planning.models import IdentityPolicy


class ExpressionBoundaryValidator:
    """Rejects only known literal identity preambles; it is not semantic NLP."""

    def violates(self, plan, response, identity):
        if plan.identity_policy is not IdentityPolicy.FORBIDDEN or not isinstance(response, str):
            return False
        display_name = getattr(identity, "display_name", "")
        nature = getattr(identity, "nature", "")
        role = getattr(identity, "role", "")
        normalized = self._normalize(response)
        if not display_name or not normalized:
            return False
        name = self._normalize(display_name)
        nature = self._normalize(nature)
        role = self._normalize(role)
        starts_self_intro = bool(re.match(r"^(salam )?mən ", normalized))
        return starts_self_intro and (name in normalized[:160] or nature in normalized[:160] or role in normalized[:200])

    @staticmethod
    def _normalize(value):
        return " ".join(re.findall(r"\w+", value.casefold())) if isinstance(value, str) else ""
