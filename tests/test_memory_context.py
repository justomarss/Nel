import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.core.nel import Nel
from src.memory.memory import Memory


class MemoryContextTests(unittest.TestCase):
    def test_recall_returns_newest_memories_without_changing_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "long_term.json"
            stored = ["oldest", "middle", "newest"]
            path.write_text(
                json.dumps(stored),
                encoding="utf-8",
            )

            memory = Memory()
            memory.long_path = path

            self.assertEqual(
                memory.recall(limit=2),
                ["middle", "newest"],
            )
            self.assertEqual(memory.recall(), stored)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                stored,
            )

    def test_prompt_excludes_old_memories_beyond_context_limit(self):
        class Brain:
            def __init__(self):
                self.prompt = None

            def should_remember(self, text):
                return False

            def think(self, prompt):
                self.prompt = prompt
                return "ok"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "long_term.json"
            stored = [
                "OLD_MEMORY_SHOULD_NOT_APPEAR",
                "RECENT_MEMORY_ONE",
                "RECENT_MEMORY_TWO",
            ]
            path.write_text(
                json.dumps(stored),
                encoding="utf-8",
            )

            memory = Memory()
            memory.long_path = path
            brain = Brain()

            nel = Nel.__new__(Nel)
            nel.state = SimpleNamespace(set=lambda state: None)
            nel.intent = SimpleNamespace(classify=lambda text: "CHAT")
            nel.knowledge = SimpleNamespace(
                answer=lambda text: None,
                facts=lambda: {},
            )
            nel.memory = memory
            nel.brain = brain
            nel.raw_memory_context_limit = 2

            self.assertEqual(nel.think("hello"), "ok")
            self.assertNotIn(
                "OLD_MEMORY_SHOULD_NOT_APPEAR",
                brain.prompt,
            )
            self.assertIn("RECENT_MEMORY_ONE", brain.prompt)
            self.assertIn("RECENT_MEMORY_TWO", brain.prompt)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                stored,
            )


if __name__ == "__main__":
    unittest.main()
