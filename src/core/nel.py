from src.brain.brain import Brain
from src.brain.providers import OllamaProvider
from src.core.config import MODEL_NAME
from src.memory.memory import Memory


class Nel:
    def __init__(self):
        provider = OllamaProvider(MODEL_NAME)

        self.brain = Brain(provider)
        self.memory = Memory()

    def think(self, prompt: str):

        # Lazımdırsa yaddaşa yaz
        if self.brain.should_remember(prompt):
            self.memory.remember(prompt)

        # Yaddaşı oxu
        memories = self.memory.recall()
        memory_text = "\n".join(memories)

        # Modelə göndərilən əsas prompt
        final_prompt = f"""
You are Nel.

You are speaking with your owner.

Below are long-term memories about the user.

Long-term memories:
{memory_text}

Rules:
- Use these memories ONLY if they are relevant.
- If they are not relevant, ignore them.
- Never invent memories.
- Answer naturally.
- Always answer in Azerbaijani.
- Stay in character as Nel.

User:
{prompt}

Nel:
"""

        return self.brain.think(final_prompt)

    def remember(self, text):
        self.memory.remember(text)