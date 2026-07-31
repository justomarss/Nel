class MemoryManager:

    def should_remember(self, text: str) -> bool:

        text = text.lower()

        keywords = [
            "mənim",
            "adım",
            "sevirəm",
            "sevmirəm",
            "yaşım",
            "hədəfim",
            "məqsədim"
        ]

        return any(word in text for word in keywords)