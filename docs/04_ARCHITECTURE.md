# Nel Architecture

Status: Normative direction. Items marked [Provisional] are reversible
technical defaults, not accepted permanent architecture.

## Architectural Principles

1. The language model is a replaceable component, not Nel's identity.
2. Durable state, not generated prose, defines continuity.
3. User facts and Nel-owned facts use separate, explicit namespaces.
4. Structured validated data overrides conflicting raw conversation memory.
5. New values may supersede current values without destroying history.
6. Runtime code contains no domain-specific demo rules.
7. Private data remains local unless an explicitly configured operation needs
   cloud inference.
8. Reliability and observability precede expanded autonomy.
9. Architecture serves Nel first; it is not a generic agent framework.
10. Nel Core behavior remains independent of any single user interface or
    device form factor.

## Current Runtime Flow

```text
root main.py (development CLI)
  -> src/core/runtime.py (guarded schema-v4 composition)
     -> src/core/nel.py (temporary composition root)
        -> bounded immutable DecisionContext
        -> pure deterministic DecisionEngine
           -> goal_command -> GoalCommandHandler -> GoalService
           -> fact_command -> FactCommandHandler -> KnowledgeService
           -> memory_command -> MemoryCommandHandler -> MemoryService
           -> ask_clarification -> deterministic response
           -> conversation_response -> existing conversation flow
              -> IntentClassifier
              -> KnowledgeService / KnowledgeExtractor
              -> ContextAssembler
                 -> one canonical relevance-selected JSON bundle
                 -> 12,000-character hard data-context ceiling
              -> Brain -> NvidiaNimProvider
           -> no_action -> no provider or write
        -> Clock / background event
           -> DecisionEngine
              -> thought_start -> ThoughtService -> ThoughtCoordinator
                 -> ThoughtWorker -> temporary TypedThoughtResult
                 -> deny-by-default policy boundaries
        -> shared guarded SQLite persistence
```

This diagram describes the current prototype, not the desired stable runtime.

## Decision Boundary

ADR-020 defines Decision Engine v1 as a pure provider-independent routing
boundary. It receives only bounded operational event data and explicit
command syntax. It selects exactly one route before any provider call and has
no repository access or write authority.

The active routes are `conversation_response`, `ask_clarification`,
`goal_command`, `fact_command`, `memory_command`, `thought_start`, and
`no_action`. Memory, Knowledge, and Identity candidate routing is deliberately
absent. Natural-language goal text is conversation, never a write command.

## Concept Boundaries

| Concept | Meaning | May become authoritative? | Current implementation |
|---|---|---|---|
| User Knowledge | Validated facts about Ömər | Yes, for user facts | Versioned SQLite current/history records |
| Raw Memory | Historical interaction material | No, without validation | SQLite memory events written explicitly through MemoryService |
| Nel Identity | Durable self-description and continuity | Yes, for Nel-owned facts | Versioned SQLite identity records and read-only snapshots |
| Nel State | Current operational/internal condition | Yes within its defined lifetime | In-memory enum only |
| Thoughts | Generated private reflection candidates | No, unless separately evaluated | Bounded in-memory typed observations; no persistence |
| Goals | Explicit desired outcomes | Yes after validation/ownership rules | Versioned SQLite goals and GoalService commands |
| Conversation Context | Bounded material for the current exchange | No | Immutable canonical JSON assembled from read-only service snapshots |
| Inference | A reasoned but unverified conclusion | No | No explicit representation |

Thoughts, model replies, and inferences must never silently promote themselves
to identity, knowledge, memory, or goals.

Thought System v1 permits one background thought at a time. Foreground work
invalidates the active token, and late provider output is discarded. Memory,
Knowledge, and Identity policies reject all thought proposals by default;
thought components have no direct permanent-state write boundary.

## Composition and Application Layer

`src/core/nel.py` may remain the composition root during the prototype. It
should coordinate components, not accumulate provider, persistence,
retrieval, or policy details.

[Provisional] Introduce explicit lifecycle methods such as start and stop
before replacing the composition root. This is reversible and addresses
resource ownership without selecting a final runtime framework.

## Interface Boundary

The root CLI is a development shell, not the product interface. Nel's intended
final primary interface is a small physical desktop companion with a display,
microphone, speaker, camera, and either onboard computation or a client link
to Nel Core. Motors and physical movement are optional.

Nel Core must remain sufficiently platform-independent that the CLI, a future
desktop application, a mobile connection, and the physical device can use the
same memory, identity, reasoning, provider, state, and autonomy behavior.
Interfaces may translate input and output, but they must not become separate
authorities for Nel's identity or memory.

```text
Development CLI ----\
Desktop app ---------+--> Nel Core --> durable state and providers
Mobile connection ---+
Physical companion -/
```

This is a product boundary, not approval to implement device protocols,
audio, camera, animation, robotics, or UI systems. Do not introduce hardware
abstraction layers until a physical prototype establishes real interfaces and
constraints.

## Provider Boundary

Providers must expose stable capabilities for:

- text generation;
- schema-constrained structured generation;
- request timeout handling;
- clear errors that do not expose credentials.

Runtime explicitly selects NVIDIA NIM or Gemini. NVIDIA uses an
OpenAI-compatible client; Gemini uses the official Google Gen AI SDK. Both
implement text and structured generation without provider-side conversation
state. Environment values are inert during import. Guarded runtime
construction validates the selected provider name, required credentials,
model constraints, endpoint where applicable, bounded timeout, database path,
and boolean flags. Configuration failures cross one redacted application
boundary before Nel or its clock is constructed. Request failure never causes
automatic fallback to the other provider.

[Provisional] Define a formal Python protocol or abstract interface only when
the two concrete providers demonstrate a maintenance need beyond their shared
duck-typed generation contract.

Streaming, tool calling, and multimodal operations are not current provider
requirements.

## Structured Knowledge

The generic extraction pipeline is:

1. Receive user text.
2. Exclude questions, slash commands, and local read-only intents.
3. Request one schema-constrained candidate envelope containing the normalized
   key, exact literal value, user subject, confidence, and exact source/value
   spans.
4. Reject the whole batch when provider output is malformed; do not repair or
   retry with a more permissive prompt.
5. Validate every candidate deterministically against the original Unicode
   text, including exact offsets, exact quotes, literal values, user
   ownership, and conservative linguistic safety rules.
6. Compare grounded candidates with current facts only to classify temporary
   new, correction, reactivation, or same-value results.
7. Render non-no-op proposals as local guidance for an explicit confirmed
   `/fact set` command. Do not persist candidates or pending state.

Provider extraction is advisory and has no durability authority. Only
confirmed `/fact set` and `/fact retire` commands may write through
`KnowledgeService`. The schema and grounding policy remain topic-neutral.

## Nel-Owned Identity and State

Nel-owned identity and preferences use versioned current/history tables
separate from user knowledge. Immutable core identity is protected by two
canonical SQLite triggers. Preference writes are available only through
`IdentityService`; automatic preference formation is not implemented.

## Persistence

JSON files are prototype persistence only. They do not provide transactions,
concurrency control, migrations, relational integrity, or recoverable value
history.

ADR-013 accepts SQLite as Nel's authoritative local persistence foundation.
Schema v4 has exactly eight STRICT tables: `schema_version`, `memory_events`,
`user_facts_current`, `user_fact_history`, `nel_identity_current`,
`nel_identity_history`, `goals_current`, and `goals_history`. It also requires
the two identity immutability triggers and
`goals_current_state_updated_idx`. Current records are stored directly;
superseded fact, identity, and goal versions remain recoverable in history.

A vector database must not be added until semantic retrieval is necessary,
measured, and shown to outperform simpler indexed retrieval.

## Context and Retrieval

ADR-024 defines `ContextAssembler` as the sole stored-data assembly boundary
for conversational provider requests. It reads immutable bounded snapshots
through Identity, Knowledge, Goal, and Memory services; it has no provider,
repository, or write authority.

The assembler produces one canonical JSON string using deterministic Unicode
normalization, lexical relevance, stable tie-breaking, complete-record
packing, and a 12,000-character hard ceiling. Core identity is atomic. Active
facts, current goals, eligible preferences, and memories are normally included
only when relevant. Unused budget remains unused. Digest and character-count
diagnostics remain outside provider-facing JSON.

Identity failure aborts conversational generation. Fact, goal, or memory
source failures omit the optional section with safe metadata. A fact omission
also adds a strict instruction prohibiting personal-fact invention for that
turn. Local fact reads fail safely instead of claiming that no records exist.

Selection is exact and predictable but does not understand synonyms,
paraphrases, or Azerbaijani morphology. Measure false negatives before
considering embeddings or semantic retrieval. Structured facts remain
authoritative when included memories conflict.

## Runtime and Events

The current daemon-thread Clock is provisional. A stable runtime needs:

- owned startup and shutdown;
- cancellable scheduled work;
- exception isolation;
- backpressure or overlap prevention;
- observable task state;
- protection against concurrent persistence writes.

[Provisional] Evaluate a single-process event loop after lifecycle tests
exist. Do not migrate runtimes as an unrelated refactor.

## Failure Handling

Provider, network, parsing, persistence, and background-task failures must be
distinguishable. Failures must not corrupt memory or fabricate successful
work.

[Provisional] Use standard Python logging with redaction, typed application
errors, bounded retry policies, and atomic persistence operations before
introducing external observability infrastructure.

Expected SQLite failures are converted at service or command boundaries into
redacted `ApplicationError` values or deterministic local responses. Optional
ContextAssembler sources omit their complete section on read or snapshot-shape
failure; malformed facts activate the no-personal-fact assertion rule. Core
identity failure remains fatal to conversational generation. Programming
errors are not treated as operational persistence failures.

Backup creation uses `sqlite3.Connection.backup()`. Verification restores into
an isolated path, applies the same version-specific structural validator used
by runtime startup, then checks integrity, Unicode, ordering, current/history
continuity, and source equality during creation. The historical schema-v1
cutover CLI is retired and is not an active operational tool.

## Security Boundaries

- Credentials enter only through environment configuration.
- Secrets must not appear in prompts, logs, tests, or committed files.
- External side effects require explicit capability and permission checks.
- Tests use temporary persistence.
- Production memory must not be used as test fixtures.
- Self-modification cannot bypass review and approval.

## Architecture Change Gate

A change requires Ömər's approval before implementation when it changes data
ownership, privacy exposure, autonomy, external side effects, durable storage
format, provider contract, or the core runtime model.
