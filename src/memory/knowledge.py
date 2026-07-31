import json
from pathlib import Path


class Knowledge:

    def __init__(self):
        self.path = Path("memory/knowledge.json")

    def load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def set(self, key, value):
        data = self.load()
        data[key] = value
        self.save(data)

    def get(self, key):
        data = self.load()
        return data.get(key)