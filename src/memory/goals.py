import json
from pathlib import Path


class Goals:

    def __init__(self):
        self.path = Path("memory/goals.json")

    def load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def add(self, goal):

        data = self.load()

        if goal not in data:
            data.append(goal)
            self.save(data)

    def all(self):
        return self.load()

    def remove(self, goal):

        data = self.load()

        if goal in data:
            data.remove(goal)

        self.save(data)