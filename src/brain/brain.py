class Brain:
    def __init__(self, provider):
        self.provider = provider

    def think(self, prompt: str) -> str:
        return self.provider.generate(prompt)

    def should_remember(self, text: str) -> bool:

        prompt = f"""
Should this be stored as a long-term memory?

Reply ONLY yes or no.

Text:
{text}
"""

        answer = self.provider.generate(prompt).lower()

        return "yes" in answer
