from src.brain.knowledge_extractor import KnowledgeExtractor
from src.memory.knowledge import Knowledge


class KnowledgeService:

    def __init__(self, brain):
        self.extractor = KnowledgeExtractor(brain)
        self.knowledge = Knowledge()

    def process(self, text):

        facts = self.extractor.extract(text)

        if not isinstance(facts, dict):
            return

        for key, value in facts.items():
            self.knowledge.set(key, value)

    def get(self, key):
        return self.knowledge.get(key)

    def facts(self):
        return self.knowledge.load()

    def answer(self, text):
        return None
