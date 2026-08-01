# Nel Current State

Status: Descriptive

Baseline date: 2026-08-01

## Summary

Nel is an early Python prototype with a command-line development shell,
NVIDIA NIM inference, generic validated user-fact extraction, JSON
persistence, transient operational state, and a daemon-thread reflection
clock.

The core direction is clearer than the implementation maturity. Nel does not
yet meet the first-stable criteria.

## Supported Development Path

- Entry point: root `main.py`
- Composition root: `src/core/nel.py`
- Environment: `.env` with NVIDIA variable names documented in Start Here
- Dependencies: `openai`, `pydantic`, `python-dotenv`, `rich`
- Interface: interactive CLI only

## Implemented

- `Brain` delegates text generation to an injected provider.
- `NvidiaNimProvider` supports text and strict JSON-schema generation,
  request timeout, empty-response checks, and redacted error messages.
- `KnowledgeExtractor` uses a generic fact envelope, local Pydantic
  validation, generic key normalization, one repair attempt, and warning
  diagnostics.
- Structured user facts overwrite the current value for a normalized key.
- The active conversation prompt marks structured facts authoritative and
  prohibits fabricated Nel preferences and history.
- `StateManager`, `EventBus`, `Clock`, `DecisionEngine`, and
  `ThoughtService` are wired through `src/core/nel.py`.
- Windows stdout and stderr are configured for UTF-8 when supported.
- Private JSON memory and `.env` are ignored by Git.

## Partially Implemented

| Capability | Current limitation |
|---|---|
| Memory | Raw long-term strings; every entry is sent to the model |
| Knowledge | Flat current-value object; no provenance or value history |
| Intent classification | Keyword rules; narrow and not robustly tested |
| State | In-memory enum; no persistent Nel identity or preferences |
| Thoughts | Generated and stored, but not evaluated or integrated safely |
| Goals | JSON helper exists but is not connected to active Nel |
| Clock | Daemon thread starts automatically; lifecycle and failures are unmanaged |
| Provider independence | Brain is injected, but composition hardcodes NVIDIA NIM |
| Error handling | Provider errors are clear but generally propagate to the CLI |
| Retrieval | Structured facts enter prompts, but there is no relevant-memory retrieval |
| Silence/autonomy | Reflection exists; controlled silence and topic initiation do not |

## Not Implemented

- persistent Nel-owned identity and preference storage;
- recoverable structured-fact history;
- transactional persistence or migrations;
- bounded context selection;
- semantic retrieval evaluation;
- configuration-driven provider selection;
- safe long-running runtime lifecycle;
- explicit autonomy permissions;
- stable user interface;
- voice, vision, mobile, desktop control, or physical movement;
- self-modification pipeline.

## Tests

The repository has six `unittest` cases covering:

- user favorite update from an older to newer value;
- literal value preservation for different fact domains;
- Unicode user-name preservation;
- no-fact extraction;
- one malformed-JSON repair followed by visible failure;
- prompt protection against unstored Nel preferences.

`tests/test_event.py` is a print-based EventBus smoke script, not an
assertion-based test.

Structured-output support was successfully probed against the configured NIM
endpoint. Live requests have also shown variable latency and timeout failures,
so provider integration is not yet operationally reliable.

## Known Technical Risks

1. Raw history grows without a context bound and can conflict with current
   facts.
2. JSON read-modify-write operations are not atomic or concurrency-safe.
3. The Clock can trigger provider calls on a background daemon thread without
   exception isolation or overlap prevention.
4. Exiting the CLI does not explicitly stop owned runtime components.
5. `Brain.should_remember` relies on unconstrained yes/no text and a
   substring check.
6. Structured keys are format-normalized, but semantic synonym consistency
   is not guaranteed.
7. Provider timeout applies per client attempt, so total elapsed time may
   exceed the nominal timeout.
8. Tests primarily use fakes; startup, shutdown, persistence interruption,
   and provider outage behavior lack automated coverage.

## Legacy, Duplicate, and Placeholder Code

The supported path uses `src/core/nel.py`, but the repository also contains
older parallel modules including `src/nel.py`, `src/brain.py`,
`src/state.py`, `src/life_loop.py`, and `src/main.py`.

Several files are empty or placeholders, including brain planner/thinker/chat
modules, service modules, scheduler/planner packages, voice, vision, and
tools. Their intended status has not been formally decided.

`TODO.md` describes a sprint sequence that conflicts with the accepted
capability-first roadmap and includes deferred interface/framework work.

## Documentation State

The nine onboarding documents are being added as uncommitted files. Older
design documents remain present but are non-normative until reconciled.

## Current Contradictions With Direction

- The target requires relevant retrieval; current prompts include all raw
  long-term memory.
- The target separates user and Nel identity; Nel-owned persistent storage
  does not exist.
- The target requires recoverable supersession; current structured values
  overwrite without history.
- The target is provider-independent; construction currently hardcodes NIM.
- The target requires graceful failure; provider and background errors are
  not handled end to end.
- The target requires reliable stop behavior; the daemon Clock is not stopped
  explicitly by the CLI.
- The target prohibits premature framework/interface work; legacy TODO items
  still advertise CLI plugins, voice, vision, and desktop control as near-term
  sprints.

## Provisional Baseline Choices

- Keep Python as the only orchestration language.
- Keep root `main.py` and `src/core/nel.py` as the supported prototype
  path.
- Keep `unittest` until a testing limitation justifies another dependency.
- Use standard logging and temporary-file tests.
- Treat SQLite and an event-loop runtime as candidates, not approved
  migrations.
