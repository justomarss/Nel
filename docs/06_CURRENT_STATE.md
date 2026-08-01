# Nel Current State

Status: Descriptive

Baseline date: 2026-08-02

## Summary

Nel is an early Python prototype with a command-line development shell,
NVIDIA NIM inference, generic validated user-fact extraction, authoritative
SQLite persistence, transient operational state, and a daemon-thread
reflection clock.

The provisional inference model is `meta/llama-3.1-70b-instruct`. Automatic
LLM-generated background thoughts are disabled by default while foreground
conversation and structured extraction remain active.

The core direction is clearer than the implementation maturity. Nel does not
yet meet the first-stable criteria.

## Supported Development Path

- Entry point: root `main.py`
- Composition root: `src/core/nel.py`
- Environment: `.env` supplies NVIDIA credentials and endpoint configuration;
  the provisional model policy is tracked in `src/core/config.py`
- Dependencies: `openai`, `pydantic`, `python-dotenv`, `rich`
- Interface: interactive CLI only

## Implemented

- `Brain` delegates text generation to an injected provider.
- `NvidiaNimProvider` supports text and strict JSON-schema generation,
  a 45-second interactive timeout, no SDK retries, empty-response checks,
  and redacted error messages.
- `KnowledgeExtractor` uses a generic fact envelope, local Pydantic
  validation, generic key normalization, one repair attempt, and warning
  diagnostics.
- Structured user facts overwrite the current value for a normalized key.
- The active conversation prompt marks structured facts authoritative and
  prohibits fabricated Nel preferences and history. It also defines generic
  Azerbaijani perspective ownership so user first-person questions become
  second-person answers while Nel-owned identity remains first-person.
- Runtime Memory and Knowledge use one shared, guarded SQLite database at
  `memory/nel.sqlite3` by default.
- Runtime code requires an existing integrity-checked schema-version-2
  database with the six approved persistence tables and identity immutability
  triggers. It never migrates or creates a production database at startup.
- Identity v1 storage and runtime composition are implemented. Production is
  still schema version 1 pending the controlled offline migration, so the
  production CLI is intentionally blocked until that migration is completed.
- Runtime Memory, Knowledge, and Identity services share one guarded database;
  identity remains namespace-separated and is not included in prompts.
- Current user facts are stored directly, changed values retain recoverable
  history, and validated extraction batches are transactional.
- The verified JSON-to-SQLite cutover is complete. JSON files and the initial
  cutover backup remain historical snapshots and are not runtime backends.
- `StateManager`, `EventBus`, `Clock`, `DecisionEngine`, and
  `ThoughtService` are wired through `src/core/nel.py`.
- `Clock` owns a cancellable thread with idempotent startup and shutdown.
- The CLI always stops Nel in a `finally` block.
- Foreground provider failures become redacted application errors instead of
  terminating the CLI.
- Background thought failures are logged without exception messages, and
  thought generation cannot overlap.
- Background thought generation is configuration-gated and defaults off;
  `Clock`, `EventBus`, `ThoughtService`, and `DecisionEngine` remain wired.
- Raw prompt context has a configurable count limit and prefers the newest
  memories without deleting older stored memory.
- Windows stdout and stderr are configured for UTF-8 when supported.
- Private SQLite data, cutover artifacts, historical JSON, and `.env` are
  ignored by Git.

## Partially Implemented

| Capability | Current limitation |
|---|---|
| Memory | Raw long-term strings; only a bounded newest subset is sent, without relevance scoring |
| Knowledge | Current values and superseded history are transactional; provenance beyond version history is not implemented |
| Intent classification | Keyword rules; narrow and not robustly tested |
| State | Operational state is an in-memory enum; persistent Nel identity is stored separately and is not yet prompt-integrated |
| Thoughts | Generation code remains wired but automatic generation is disabled by default |
| Goals | JSON helper exists but is not connected to active Nel |
| Clock | Lifecycle is owned, but an active provider callback cannot be cancelled early |
| Provider independence | Brain is injected, but composition hardcodes NVIDIA NIM |
| Error handling | Provider and background failures are bounded; startup persistence failures are redacted, while operational write failures need broader application handling |
| Retrieval | Structured facts enter prompts, but there is no relevant-memory retrieval |
| Silence/autonomy | Reflection exists; controlled silence and topic initiation do not |

## Not Implemented

- automatic Nel preference learning and identity prompt integration;
- semantic retrieval evaluation;
- configuration-driven provider selection;
- safe long-running runtime lifecycle;
- explicit autonomy permissions;
- stable user interface;
- voice, vision, mobile, desktop control, or physical movement;
- self-modification pipeline.

## Tests

The repository has 102 assertion-based `unittest` cases covering:

- user favorite update from an older to newer value;
- literal value preservation for different fact domains;
- Unicode user-name preservation;
- no-fact extraction;
- one malformed-JSON repair followed by visible failure;
- prompt protection against unstored Nel preferences.
- idempotent Clock lifecycle and callback-failure survival;
- CLI cleanup and foreground provider-error recovery;
- state restoration after provider failure;
- provider and background-log secret redaction;
- prevention of overlapping background thoughts;
- bounded newest-memory recall and full on-disk preservation.
- guarded SQLite startup and schema rejection;
- transactional memory and fact persistence across restart;
- migration idempotency, rollback, backup, restore, and cutover cleanup;
- JSON snapshot immutability and absence of runtime dual writes;
- generic Azerbaijani user/Nel perspective ownership.
- schema-v2 identity migration, immutability, history, backup, and runtime
  composition without production database writes.

`tests/test_event.py` is a print-based EventBus smoke script, not an
assertion-based test.

Structured-output support was successfully probed against the configured NIM
endpoint. Live requests have also shown variable latency and timeout failures,
so provider integration is not yet operationally reliable.

## Known Technical Risks

1. Raw history is count-bounded in prompts but selected by recency rather
   than relevance and can still conflict with current facts.
2. SQLite rollback to historical JSON is no longer valid after post-cutover
   writes; recovery must use SQLite or a verified SQLite backup.
3. Clock shutdown waits for an active callback; provider work is not
   cancellable after it starts.
4. `Brain.should_remember` relies on unconstrained yes/no text and a
   substring check.
5. Structured keys are format-normalized, but semantic synonym consistency
   is not guaranteed.
6. The provisional 70B model showed variable latency in qualification; a
   foreground request can occupy the full 45-second timeout.
7. Tests primarily use fakes; live provider outage behavior still lacks
   deterministic automated coverage.

## Legacy, Duplicate, and Placeholder Code

The isolated legacy runtime (`src/main.py`, `src/nel.py`,
`src/brain.py`, `src/state.py`, and `src/life_loop.py`) was removed
after reference, import, and regression checks confirmed the root
`main.py` and `src/core/nel.py` path does not use it.

Retained future placeholders are classified as dormant, not implemented:
`src/brain/chat_engine.py`, `src/brain/memory_judge.py`,
`src/brain/planner.py`, `src/brain/thinker.py`, empty service modules,
and planner, scheduler, tools, voice, and vision package shells. They are not
evidence that those capabilities exist and must not be expanded outside the
roadmap.

`src/memory/goals.py` is an unfinished, unintegrated prototype.
`src/memory.py` is an empty obsolete placeholder retained for a later
cleanup decision.

`TODO.md` is now a deprecation pointer to the authoritative roadmap.

## Documentation State

The onboarding documents and accepted ADRs are authoritative. Older design
documents remain present but are non-normative until reconciled.

## Current Contradictions With Direction

- The target requires relevant retrieval; current prompts use a bounded newest
  subset without relevance scoring.
- The target is provider-independent; construction currently hardcodes NIM.

## Provisional Baseline Choices

- Keep Python as the only orchestration language.
- Keep root `main.py` and `src/core/nel.py` as the supported prototype
  path.
- Keep `unittest` until a testing limitation justifies another dependency.
- Use standard logging and temporary-file tests.
- Keep the threaded runtime provisional while SQLite remains the accepted
  authoritative persistence foundation.
