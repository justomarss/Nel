import subprocess
import sys
import unittest
from pathlib import Path

from scripts.verify_environment import verify_environment


class EnvironmentVerificationTests(unittest.TestCase):
    def test_active_environment_matches_pinned_dependencies(self):
        statuses = verify_environment()
        self.assertEqual(len(statuses), 4)

    def test_verifier_runs_without_provider_credentials(self):
        environment = {
            "PATH": str(Path(sys.executable).parent),
            "PYTHONIOENCODING": "utf-8",
            "SYSTEMROOT": "C:\\Windows",
        }
        result = subprocess.run(
            [sys.executable, "scripts/verify_environment.py"],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS environment_verification", result.stdout)
        self.assertNotIn("NVIDIA_API_KEY", result.stdout)
        self.assertNotIn("GEMINI_API_KEY", result.stdout)


if __name__ == "__main__":
    unittest.main()
