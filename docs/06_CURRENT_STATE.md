# Nel Current State

Status: Descriptive

Baseline date: 2026-08-02

## Summary

Nel is an early Python prototype with a command-line development shell,
NVIDIA NIM inference, generic grounded user-fact proposals, authoritative
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
- Environment: `.env` may supply NVIDIA credentials, model, and endpoint
  configuration. Importing runtime modules does not require those values;
  provider construction validates them when NVIDIA NIM is actually selected.
- Dependencies: `openai`, `pydantic`, `python-dotenv`, `rich`
- Interface: interactive CLI only

## Implemented

- `Brain` delegates text generation to an injected provider.
- `NvidiaNimProvider` supports text and strict JSON-schema generation,
  a 45-second interactive timeout, no SDK retries, empty-response checks,
  and redacted error messages.
- `KnowledgeExtractor` produces schema-validated temporary candidates with
  exact source and value spans. Malformed output rejects the batch without a
  repair retry.
- `FactGroundingPolicy` validates candidates deterministically against the
  original user text and fails closed on unsupported ownership, negation,
  historical-only evidence, comparative overclaims, contradictions, or any
  transformed literal value.
- Provider-proposed facts never write durable state. Grounded new, correction,
  and reactivation proposals are temporary guidance for an explicit confirmed
  `/fact set`; same-value candidates are no-ops.
- The active conversation prompt marks structured facts authoritative and
  prohibits fabricated Nel preferences and history. It also defines generic
  Azerbaijani perspective ownership so user first-person questions become
  second-person answers while Nel-owned identity remains first-person.
- Runtime Memory and Knowledge use one shared, guarded SQLite database at
  `memory/nel.sqlite3` by default.
- Runtime code requires an existing integrity-checked schema-version-4
  database with exactly the eight approved persistence tables, the goal index,
  identity immutability triggers, and fact-retirement columns. It never
  migrates or creates a production database at startup. Production is schema
  version 4 after the controlled migration.
- Identity v1 storage and runtime composition are implemented. The controlled
  production migration to schema version 2 is complete.
- Runtime Memory, Knowledge, Identity, and Goal services share one guarded
  database. Identity and goals remain namespace-separated and enter
  conversation prompts only through bounded read-only snapshots.
- Goal writes are available only through explicit `/goal` commands handled
  before provider invocation. GoalService remains the write boundary, all
  updates use expected versions, and completion, progress, reopen, and restore
  operations enforce their accepted confirmation rules.
- Fact inspection, correction, history, and retirement are routed locally
  through explicit `/fact` commands and `KnowledgeService` on schema v4.
- `MemoryService` is the sole normal durable-memory write boundary. Ordinary
  conversation and provider failures do not create memory. Explicit non-empty
  `/remember` commands route through Decision Engine, invalidate foreground
  thought work, and execute locally without a provider call.
- Decision Engine v1 uses immutable bounded contexts and results to select
  exactly one deterministic foreground or background route before any provider
  call. It routes explicit goal, fact, and memory commands, has no repository
  or write access, and cannot be influenced by provider output.
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
- Thought System v1 uses a single in-memory coordinator, bounded read-only
  context, typed temporary observations, and deny-by-default Memory,
  Knowledge, and Identity policies.
- Background thought failures are logged without exception messages. Thought
  generation cannot overlap, foreground interaction invalidates active work,
  and late cancelled results are discarded.
- Background thought generation is configuration-gated and defaults off;
  `Clock`, `EventBus`, `ThoughtService`, and `DecisionEngine` remain wired.
- `ContextAssembler` is the sole stored-data prompt boundary for conversational
  provider requests. It emits deterministic canonical JSON with a 12,000
  character hard ceiling, SHA-256 diagnostics, complete-record packing, and
  relevance-selected identity preferences, active facts, current goals, and
  memory events.
- Core identity is mandatory. Optional fact, goal, and memory read failures are
  represented by safe omission metadata; fact omission adds a strict
  no-personal-fact assertion rule for that turn.
- Windows stdout and stderr are configured for UTF-8 when supported.
- Private SQLite data, cutover artifacts, historical JSON, and `.env` are
  ignored by Git.

## Partially Implemented

| Capability | Current limitation |
|---|---|
| Memory | Raw long-term strings; exact lexical relevance and duplicate defense select at most ten complete events, without semantic retrieval |
| Knowledge | Current values, superseded history, and versioned retirement are transactional; provider candidates are grounded but ephemeral, and durable provenance beyond revision reasons is not implemented |
| Intent classification | Keyword rules; narrow and not robustly tested |
| State | Operational state is an in-memory enum; persistent Nel identity is stored separately and is read into prompts without a conversation write path |
| Thoughts | Minimal in-memory typed observation pipeline is wired; policies reject permanent changes and automatic generation remains disabled by default |
| Goals | Explicit storage commands and bounded read-only conversation context are integrated; natural-language inference, planning, reminders, scheduling, actions, and autonomous creation remain absent |
| Decision Engine | Deterministic routing covers conversation, explicit goal, fact, and memory commands, clarification, background thought starts, and no-action; natural-language write routing and knowledge or identity candidates are deferred |
| Clock | Lifecycle is owned, but an active provider callback cannot be cancelled early |
| Provider independence | Brain is injected, but composition hardcodes NVIDIA NIM |
| Error handling | Provider and background failures are bounded; startup persistence and provider-configuration failures are redacted, while operational write failures need broader application handling |
| Retrieval | Unified deterministic lexical selection is active; synonyms, paraphrases, morphology, embeddings, and semantic retrieval are absent |
| Silence/autonomy | Reflection exists; controlled silence and topic initiation do not |

## Not Implemented

- automatic Nel preference learning or promotion;
- semantic retrieval evaluation;
- configuration-driven provider selection;
- safe long-running runtime lifecycle;
- explicit autonomy permissions;
- stable user interface;
- voice, vision, mobile, desktop control, or physical movement;
- self-modification pipeline.

## Tests

The repository has 277 assertion-based `unittest` cases covering:

- temporary new, correction, reactivation, and same-value fact proposals with
  no provider-authoritative durable writes;
- exact source/value grounding, literal Unicode preservation, batch rejection,
  conservative linguistic rejection, and no malformed-output repair retry;
- Unicode user-name preservation;
- no-fact extraction;
- malformed extraction rejection without retry or durable writes;
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
- bounded read-only identity context, preference-state filtering, namespace
  isolation, restart continuity, and identity immutability during conversation.
- single-flight temporary thoughts, foreground cancellation, late-result
  rejection, bounded context, failure recovery, and absence of persistent
  thought writes.
- explicit goal commands, confirmation gates, expected-version conflicts,
  restart persistence, bounded read-only context, and provider/thought
  isolation from goal writes.
- immutable bounded decision models, exact foreground and background
  precedence, fail-closed routing, and provider/repository exclusion from route
  selection.
- schema-v4 fact retirement, reactivation, history continuity, backup and
  restore validation, interrogative extraction rejection, and deterministic
  provider-free `/fact` routing.
- explicit `/remember` Decision Engine routing, deterministic clarification,
  foreground thought invalidation, provider exclusion, and CLI routing.
- import safety without NVIDIA credentials and redacted provider-configuration
  failures at provider and CLI startup boundaries.
- canonical context determinism, SHA-256 digests, separate system/user limits,
  complete-record budgeting, relevance and stable ordering, source failures,
  duplicate memory defense, and absence of provider/repository/write authority.

`tests/test_event.py` is a print-based EventBus smoke script, not an
assertion-based test.

Structured-output support was successfully probed against the configured NIM
endpoint. Live requests have also shown variable latency and timeout failures,
so provider integration is not yet operationally reliable.

## Known Technical Risks

1. Context relevance is deterministic lexical matching; it can miss synonyms,
   paraphrases, and Azerbaijani morphological variants.
2. SQLite rollback to historical JSON is no longer valid after post-cutover
   writes; recovery must use SQLite or a verified SQLite backup.
3. In-flight thought provider work cannot be interrupted after it starts;
   cancellation invalidates and discards its eventual result instead.
4. Conservative grounding intentionally produces false negatives for
   linguistically ambiguous statements and does not resolve semantic key
   synonyms.
5. Structured keys are format-normalized, but semantic synonym consistency
   is not guaranteed.
6. The provisional 70B model showed variable latency in qualification; a
   foreground request can occupy the full 45-second timeout.
7. Tests primarily use fakes; live provider outage behavior still lacks
   deterministic automated coverage.
8. The 12,000-character limit is provider-independent but does not guarantee a
   provider token count or latency bound.
9. The retained cutover CLI targets schema v1 and is not the operational
   verifier for the active schema-v4 database.

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

- The target is provider-independent; construction currently hardcodes NIM.

## Remaining v1.0 Blockers

- Replace or retire schema-v1-only operational cutover verification tooling.
- Create a fresh validated release backup and complete sustained runtime,
  controlled initiation, and appropriate-silence acceptance checks.

## Provisional Baseline Choices

- Keep Python as the only orchestration language.
- Keep root `main.py` and `src/core/nel.py` as the supported prototype
  path.
- Keep `unittest` until a testing limitation justifies another dependency.
- Use standard logging and temporary-file tests.
- Keep the threaded runtime provisional while SQLite remains the accepted
  authoritative persistence foundation.
