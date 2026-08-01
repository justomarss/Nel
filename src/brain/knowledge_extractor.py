import json


class KnowledgeExtractor:

    def __init__(self, brain):
        self.brain = brain

    def extract(self, text):

        prompt = f"""
Extract user facts.

Return ONLY valid JSON.

Example:

{{
    "favorite_anime":"Bleach"
}}

If there is nothing useful return:

{{}}

User:

{text}
"""

        response = self.brain.provider.generate(prompt)

        try:
            return json.loads(response)
        except:
            return {}