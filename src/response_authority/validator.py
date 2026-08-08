from src.response_authority.planner import ResponseAuthorityPlan, ResponseMode


class ResponseAuthorityValidator:
    """Checks plan/result compatibility; it never interprets provider prose."""

    def validate_plan(self, plan):
        if not isinstance(plan, ResponseAuthorityPlan):
            raise ValueError("response_authority_plan_invalid")

    def validate_provider_result(self, plan, response):
        self.validate_plan(plan)
        return plan.mode is ResponseMode.PROVIDER_GENERAL and isinstance(
            response,
            str,
        )
