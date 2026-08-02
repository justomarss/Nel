import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main
from src.brain.providers import NvidiaNimProvider
from src.core.clock import Clock
from src.core.config import (
    ENABLE_BACKGROUND_THOUGHTS,
    NVIDIA_INTERACTIVE_TIMEOUT_SECONDS,
    NVIDIA_MODEL,
)
from src.core.nel import Nel
from src.core.state import State
from src.errors import ApplicationError, ProviderError


class RuntimeLifecycleTests(unittest.TestCase):
    def test_provisional_model_and_provider_policy(self):
        with patch("src.brain.providers.OpenAI") as client:
            NvidiaNimProvider(
                model=NVIDIA_MODEL,
                api_key="test-key",
                base_url="https://example.invalid/v1",
                timeout=NVIDIA_INTERACTIVE_TIMEOUT_SECONDS,
            )

        self.assertEqual(NVIDIA_MODEL, "meta/llama-3.1-70b-instruct")
        client.assert_called_once_with(
            api_key="test-key",
            base_url="https://example.invalid/v1",
            timeout=45.0,
            max_retries=0,
        )

    def test_background_thoughts_are_disabled_by_default(self):
        nel = Nel.__new__(Nel)
        nel.background_thoughts_enabled = ENABLE_BACKGROUND_THOUGHTS
        nel.decision = SimpleNamespace(
            should_think=lambda: self.fail("decision should not run")
        )
        nel.thought_service = SimpleNamespace(
            generate=lambda: self.fail("thought should not run")
        )

        nel.on_clock_tick()

        self.assertFalse(ENABLE_BACKGROUND_THOUGHTS)

    def test_foreground_chat_works_with_background_thoughts_disabled(self):
        class Brain:
            def should_remember(self, text):
                return False

            def think(self, prompt):
                return "foreground reply"

        nel = Nel.__new__(Nel)
        nel.background_thoughts_enabled = False
        nel.state = SimpleNamespace(set=lambda state: None)
        nel.intent = SimpleNamespace(classify=lambda text: "CHAT")
        nel.knowledge = SimpleNamespace(
            answer=lambda text: None,
            facts=lambda: {},
        )
        nel.memory = SimpleNamespace(recall=lambda limit=None: [])
        nel.brain = Brain()
        nel.raw_memory_context_limit = 20

        self.assertEqual(nel.think("hello"), "foreground reply")

    def test_empty_input_never_enters_foreground_or_touches_subsystems(self):
        class StateRecorder:
            def __init__(self):
                self.states = []

            def get(self):
                return State.IDLE

            def set(self, state):
                self.states.append(state)

        class Coordinator:
            state = "idle"

            def begin_foreground(self):
                raise AssertionError("foreground thought path must not run")

            def end_foreground(self):
                raise AssertionError("foreground thought path must not run")

        def forbidden(*_args, **_kwargs):
            raise AssertionError("empty input touched a subsystem")

        nel = Nel.__new__(Nel)
        nel.state = StateRecorder()
        nel.thought_coordinator = Coordinator()
        nel.brain = SimpleNamespace(
            should_remember=forbidden,
            think=forbidden,
        )
        nel.memory = SimpleNamespace(
            remember=forbidden,
            recall=forbidden,
        )
        nel.knowledge = SimpleNamespace(
            answer=forbidden,
            process=forbidden,
            facts=forbidden,
        )
        nel.identity = SimpleNamespace(snapshot=forbidden)
        nel.goals = SimpleNamespace(list_current=forbidden)
        nel.intent = SimpleNamespace(classify=forbidden)

        self.assertEqual(nel.think("   "), "")
        self.assertEqual(nel.state.states, [])

    def test_cli_does_not_print_empty_no_action_response(self):
        class FakeNel:
            def __init__(self):
                self.stopped = 0
                self.inputs = []

            def think(self, text):
                self.inputs.append(text)
                return ""

            def stop(self):
                self.stopped += 1

        fake_nel = FakeNel()
        with (
            patch.object(main, "create_runtime_nel", return_value=fake_nel),
            patch("builtins.input", side_effect=["   ", "exit"]),
            patch("builtins.print") as output,
        ):
            result = main.run()

        self.assertEqual(result, 0)
        self.assertEqual(fake_nel.inputs, ["   "])
        self.assertEqual(fake_nel.stopped, 1)
        output.assert_not_called()

    def test_clock_start_and_stop_are_idempotent(self):
        callback_ran = threading.Event()
        calls = []

        def callback():
            calls.append(1)
            callback_ran.set()

        clock = Clock(0.01, callback)
        clock.start()
        first_thread = clock._thread
        clock.start()

        self.assertIs(clock._thread, first_thread)
        self.assertTrue(callback_ran.wait(0.5))

        clock.stop()
        clock.stop()
        calls_after_stop = len(calls)
        time.sleep(0.03)

        self.assertFalse(clock.running)
        self.assertIsNone(clock._thread)
        self.assertEqual(len(calls), calls_after_stop)

    def test_clock_survives_callback_failure(self):
        recovered = threading.Event()
        calls = []

        def callback():
            calls.append(1)
            if len(calls) == 1:
                raise ValueError("synthetic secret")
            recovered.set()

        clock = Clock(0.01, callback)
        with self.assertLogs("src.core.clock", level="ERROR") as logs:
            clock.start()
            self.assertTrue(recovered.wait(0.5))
            clock.stop()

        self.assertIn("Clock callback failed (ValueError).", logs.output[0])
        self.assertNotIn("synthetic secret", logs.output[0])

    def test_cli_recovers_from_application_error_and_stops(self):
        class FakeNel:
            instance = None

            def __init__(self):
                self.stopped = 0
                FakeNel.instance = self

            def think(self, text):
                raise ApplicationError("provider unavailable")

            def remember(self, text):
                raise AssertionError("remember should not be called")

            def stop(self):
                self.stopped += 1

        fake_nel = FakeNel()
        with (
            patch.object(main, "create_runtime_nel", return_value=fake_nel),
            patch("builtins.input", side_effect=["hello", "exit"]),
            patch("builtins.print") as output,
        ):
            main.run()

        self.assertEqual(fake_nel.stopped, 1)
        output.assert_any_call("Nel: provider unavailable")

    def test_cli_stops_when_input_is_interrupted(self):
        class FakeNel:
            instance = None

            def __init__(self):
                self.stopped = 0
                FakeNel.instance = self

            def stop(self):
                self.stopped += 1

        fake_nel = FakeNel()
        with (
            patch.object(main, "create_runtime_nel", return_value=fake_nel),
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            with self.assertRaises(KeyboardInterrupt):
                main.run()

        self.assertEqual(fake_nel.stopped, 1)

    def test_foreground_provider_failure_restores_idle_state(self):
        class StateRecorder:
            def __init__(self):
                self.states = []

            def set(self, state):
                self.states.append(state)

        class Brain:
            def should_remember(self, text):
                return False

            def think(self, prompt):
                raise ProviderError("redacted")

        nel = Nel.__new__(Nel)
        nel.state = StateRecorder()
        nel.intent = SimpleNamespace(classify=lambda text: "CHAT")
        nel.knowledge = SimpleNamespace(
            answer=lambda text: None,
            facts=lambda: {},
        )
        nel.memory = SimpleNamespace(recall=lambda limit=None: [])
        nel.brain = Brain()
        nel.raw_memory_context_limit = 20

        with self.assertRaises(ApplicationError):
            nel.think("hello")

        self.assertEqual(
            nel.state.states,
            [State.THINKING, State.IDLE],
        )

    def test_foreground_timeout_becomes_application_error(self):
        class StateRecorder:
            def __init__(self):
                self.states = []

            def set(self, state):
                self.states.append(state)

        class TimedOutBrain:
            def should_remember(self, text):
                raise ProviderError(
                    "NVIDIA NIM request failed (APITimeoutError)."
                )

        nel = Nel.__new__(Nel)
        nel.state = StateRecorder()
        nel.intent = SimpleNamespace(classify=lambda text: "CHAT")
        nel.knowledge = SimpleNamespace(
            answer=lambda text: None,
            facts=lambda: {},
        )
        nel.memory = SimpleNamespace(recall=lambda limit=None: [])
        nel.brain = TimedOutBrain()
        nel.raw_memory_context_limit = 20

        with self.assertRaises(ApplicationError):
            nel.think("hello")

        self.assertEqual(
            nel.state.states,
            [State.THINKING, State.IDLE],
        )

    def test_provider_error_does_not_expose_original_message(self):
        class Completions:
            def create(self, **kwargs):
                raise RuntimeError("synthetic API key")

        provider = NvidiaNimProvider.__new__(NvidiaNimProvider)
        provider.model = "test-model"
        provider.client = SimpleNamespace(
            chat=SimpleNamespace(completions=Completions())
        )

        with self.assertRaises(ProviderError) as raised:
            provider.generate("hello")

        self.assertNotIn("synthetic API key", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
