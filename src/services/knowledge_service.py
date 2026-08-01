from src.brain.knowledge_extractor import KnowledgeExtractor
from src.memory.knowledge import Knowledge


class KnowledgeService:

    def __init__(self, brain, repository=None):
        self.extractor = KnowledgeExtractor(brain)
        self.knowledge = repository if repository is not None else Knowledge()

    def process(self, text):

        facts = self.extractor.extract(text)

        if not isinstance(facts, dict):
            return

        set_many = getattr(self.knowledge, "set_many", None)
        if callable(set_many):
            batch = [
                {"key": key, "value": value, "subject": "user"}
                for key, value in facts.items()
            ]
            if batch:
                set_many(batch)
            return

        for key, value in facts.items():
            self.knowledge.set(key, value)

    def get(self, key):
        return self.knowledge.get(key)

    def facts(self):
        return self.knowledge.load()

    def answer(self, text):
        return None
