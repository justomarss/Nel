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

    def internal_monologue(self):

        prompt = """
You are Nel.

You are thinking to yourself.

Nobody will read this immediately.

Write ONE short internal thought.

Do not answer the user.

Do not explain.

Only write the thought.

Always write in Azerbaijani.
"""

        return self.provider.generate(prompt)
