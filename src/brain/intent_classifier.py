class IntentClassifier:

    def classify(self, text: str):

        text = text.lower()

        if (
            "xatırlayırsan" in text
            or "hansı" in text
            or "mən hansı" in text
            or "nəyi sevirəm" in text
        ):
            return "SEARCH_MEMORY"

        if (
            "mənim" in text
            or "sevirəm" in text
            or "adım" in text
            or "yaşım" in text
        ):
            return "REMEMBER"

        if (
            "plan" in text
            or "məqsəd" in text
            or "goal" in text
        ):
            return "PLAN"

        return "CHAT"