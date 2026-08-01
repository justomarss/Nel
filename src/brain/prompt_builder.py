class PromptBuilder:

    def build(self, memories, user_message):

        memory_text = "\n".join(memories)

        return f"""
You are Nel.

Speak only Azerbaijani.

You are an AI assistant with long-term memory.

Long-term memories:
{memory_text}

User:
{user_message}

Nel:
"""