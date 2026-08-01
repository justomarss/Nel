import json
from pathlib import Path


class Memory:

    def __init__(self):
        self.short_path = Path("memory/short_term.json")
        self.long_path = Path("memory/long_term.json")

    def load_short(self):
        with open(self.short_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_long(self):
        with open(self.long_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_short(self, data):
        with open(self.short_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def save_long(self, data):
        with open(self.long_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def remember(self, text):
        data = self.load_long()
        data.append(text)
        self.save_long(data)

    def recall(self, limit=None):
        memories = self.load_long()

        if limit is None:
            return memories
        if limit == 0:
            return []

        return memories[-limit:]
