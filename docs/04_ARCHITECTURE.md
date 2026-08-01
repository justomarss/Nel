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

## Current Runtime Flow

```text
root main.py (development CLI)
  -> src/core/nel.py (temporary composition root)
     -> IntentClassifier
     -> Brain
        -> NvidiaNimProvider
     -> KnowledgeService
        -> KnowledgeExtractor
        -> Knowledge JSON
     -> Memory
        -> raw long-term JSON
     -> StateManager
     -> DecisionEngine
     -> EventBus
     -> Clock
        -> ThoughtService
           -> internal-thought JSON
```

This diagram describes the current prototype, not the desired stable runtime.

## Concept Boundaries

| Concept | Meaning | May become authoritative? | Current implementation |
|---|---|---|---|
| User Knowledge | Validated facts about Ömər | Yes, for user facts | Structured JSON key/value store |
| Raw Memory | Historical interaction material | No, without validation | Long-term JSON list |
| Nel Identity | Durable self-description and continuity | Yes, for Nel-owned facts | Not implemented |
| Nel State | Current operational/internal condition | Yes within its defined lifetime | In-memory enum only |
| Thoughts | Generated private reflection candidates | No, unless separately evaluated | Timestamped JSON entries |
| Goals | Explicit desired outcomes | Yes after validation/ownership rules | JSON helper, not integrated |
| Conversation Context | Bounded material for the current exchange | No | All raw long-term memory is injected |
| Inference | A reasoned but unverified conclusion | No | No explicit representation |

Thoughts, model replies, and inferences must never silently promote themselves
to identity, knowledge, memory, or goals.

## Composition and Application Layer

`src/core/nel.py` may remain the composition root during the prototype. It
should coordinate components, not accumulate provider, persistence,
retrieval, or policy details.

[Provisional] Introduce explicit lifecycle methods such as start and stop
before replacing the composition root. This is reversible and addresses
resource ownership without selecting a final runtime framework.

## Provider Boundary

Providers must expose stable capabilities for:

- text generation;
- schema-constrained structured generation;
- request timeout handling;
- clear errors that do not expose credentials.

The current NVIDIA NIM implementation uses an OpenAI-compatible client.

[Provisional] Define a Python protocol or abstract interface only when a
second provider or provider-level test double makes the contract necessary.
Provider selection should then move to configuration-driven construction.

Streaming, tool calling, and multimodal operations are not current provider
requirements.

## Structured Knowledge

The generic extraction pipeline is:

1. Receive user text.
2. Request a schema-constrained fact envelope.
3. Validate key, literal value, subject, and confidence locally.
4. Accept only facts whose subject is `user`.
5. Normalize key formatting generically.
6. Retry invalid output once with a repair prompt.
7. Log a visible diagnostic and store nothing after a second failure.
8. Supersede the current value for the same normalized key.

The schema must remain topic-neutral. Semantic key consistency and historical
supersession require stronger persistence than the current flat JSON object.

## Nel-Owned Identity and State

Nel-owned identity and preferences require storage separate from user
knowledge. A Nel preference may be formed only through an approved formation
process using actual observations or interactions. Generated claims alone are
not evidence.

[Provisional] Model Nel-owned records with explicit fields for value,
confidence, evidence references, creation time, update time, and status
(`provisional`, `established`, or `retired`). The exact schema requires
an ADR before implementation.

## Persistence

JSON files are prototype persistence only. They do not provide transactions,
concurrency control, migrations, relational integrity, or recoverable value
history.

[Provisional] SQLite is the default candidate for the first durable store
because it is local, transactional, inspectable, and reversible through
export. Adoption requires a migration proposal, backup plan, validation
tests, and Ömər's approval.

A vector database must not be added until semantic retrieval is necessary,
measured, and shown to outperform simpler indexed retrieval.

## Context and Retrieval

The stable system must not send all historical memory to the model.

[Provisional] Begin with deterministic metadata filtering, recency, explicit
fact lookup, and a bounded context budget. Measure misses and irrelevant
retrieval before considering embeddings.

Structured facts remain authoritative when retrieved raw memories conflict.
The prompt must preserve the distinction between user data and Nel-owned
state.

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
