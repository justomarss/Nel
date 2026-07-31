from .providers import OllamaProvider

class Brain:
    def __init__(self, provider):
        self.provider = provider

    def think(self, prompt: str) -> str:
        return self.provider.generate(prompt)

    def should_remember(self, text: str) -> bool:

        prompt = f"""
You are a memory classifier.

Should this information be stored as long-term memory?

Store things like:
- user's preferences
- goals
- plans
- personal information
- recurring habits

Do NOT store:
- temporary conversation
- greetings
- random questions
- one-time requests

Reply ONLY with:

YES

or

NO

Text:
{text}
"""

        answer = self.provider.generate(prompt).strip().upper()

        return answer.startswith("YES")