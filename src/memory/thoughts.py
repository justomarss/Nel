import json
from pathlib import Path
from datetime import datetime


class Thoughts:

    def __init__(self):
        self.path = Path("memory/internal_thoughts.json")

    def load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def add(self, text):

        thoughts = self.load()

        thoughts.append({
            "time": datetime.now().isoformat(),
            "thought": text
        })

        self.save(thoughts)