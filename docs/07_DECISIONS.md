# Nel Decisions

Status: Normative for records marked Accepted.

## Record Format

Each architecture decision record (ADR) contains context, realistic options,
the accepted decision, consequences, and status.

Statuses:

- Proposed: under review; not authoritative.
- Accepted: approved and normative.
- Superseded: retained historically but replaced by a newer ADR.
- Rejected: considered and not selected.

Accepted records are not silently rewritten when direction changes. Add a new
record that explicitly supersedes the old one.

## ADR-001: Nel Is a Persistent Digital Personality

Context: The project needs an identity that prevents drift into a generic
chatbot or fictional roleplay.

Options: generic assistant; roleplay character; persistent digital
personality and personal autonomous agent.

Decision: Nel is a persistent digital personality and personal autonomous
agent, initially for Ömər alone.

Consequences: Identity must survive provider replacement; generated prose
cannot define identity; public-product concerns are deferred.

Status: Accepted.

## ADR-013: Persistent Memory Architecture

Context: Nel currently stores raw memories and current user facts in JSON
files that are read and rewritten as whole documents. This is adequate for
early experiments but does not provide transactions, schema migrations,
reliable concurrent access, or recoverable history for superseded facts.

Nel is initially a single-owner, local-first application. Its immediate
persistence problem is durable continuity, not distributed scale, semantic
search, relationship traversal, or a general-purpose memory framework.

### Options Considered

1. Retain JSON as the authoritative store.
2. Adopt SQLite with a minimal relational schema.
3. Adopt SQLite with FTS5.
4. Adopt SQLite with vector search.
5. Adopt PostgreSQL.
6. Adopt a graph database.

JSON remains simple and inspectable, but improving it with locking, atomic
replacement, indexing, migrations, and cross-record consistency would
duplicate database behavior. SQLite provides local ACID transactions,
constraints, indexes, backups, and schema versioning without operating a
server.

The remaining options introduce retrieval or operational capabilities that
Nel has not yet demonstrated a need for. They are not rejected permanently,
but they are outside this decision.

### Decision

SQLite is accepted as Nel's authoritative local persistence foundation.

Only the following smallest viable schema is approved:

1. **schema_version**
2. **memory_events**
3. **user_facts_current**
4. **user_fact_history**

No additional persistence tables, search extensions, synchronization
services, or database engines are authorized by this ADR.

**schema_version** records which numbered schema migrations have been applied.
The exact migration representation may remain simple, but migration state
must be explicit and testable.

**memory_events** stores durable raw memory events in an ordered, individually
addressable form. It replaces whole-file list rewrites. Raw memory is
historical material and is not automatically authoritative truth.

**user_facts_current** stores each current validated user fact directly.
Foreground reads must not reconstruct current facts from history through
window functions, status scans, or expensive views.

**user_fact_history** preserves prior validated values and supersession
history. Updating a fact must write its historical record and current value
inside one transaction so current state and recoverable history cannot
diverge.

~~~mermaid
flowchart LR
    E["memory_events"]
    H["user_fact_history"]
    C["user_facts_current"]
    V["schema_version"]
    R["Bounded runtime retrieval"]

    E --> R
    C --> R
    H -. "audit and recovery, not routine prompt lookup" .-> R
    V -. "controls schema compatibility" .-> E
    V -. "controls schema compatibility" .-> C
    V -. "controls schema compatibility" .-> H
~~~

The four table names and responsibilities are accepted. Exact columns,
indexes, constraints, identifiers, and timestamp representation must be
proposed in the implementation plan and kept to the minimum needed to enforce
these responsibilities.

### Current-Fact and History Rules

- Current validated facts are read from **user_facts_current**.
- A newer validated value replaces the current value for the same normalized
  key.
- The displaced value remains recoverable through **user_fact_history**.
- Current and historical writes occur in one transaction.
- Raw memories cannot override a conflicting current structured fact.
- Generated model text is not automatically a fact or memory event.
- History retention does not yet imply that every record must be retained
  forever; deletion policy remains a product decision.
- The database schema must preserve literal Unicode values.

### Migration Decision

Migration from JSON must be offline, transactional, idempotent, and safely
repeatable.

Idempotent means that running the migration repeatedly against the same
source data produces the same target records without duplicates. The
implementation may use deterministic source identifiers, uniqueness
constraints, or recreation of an uncommitted clean target, but it must prove
the property with tests.

The approved cutover sequence is:

1. Stop Nel so JSON cannot change during migration.
2. Validate source JSON before creating an authoritative target.
3. Create a verified read-only backup of the source files.
4. Create a clean SQLite database with the approved schema version.
5. Import all source data inside a transaction.
6. Validate counts, ordering, literal values, current facts, history, schema
   version, foreign keys, and database integrity.
7. Commit and switch the runtime authority only after all validation passes.
8. If any step fails before cutover, discard the incomplete database and
   repeat from a clean database and the unchanged JSON source.

~~~mermaid
flowchart TD
    J["Validated read-only JSON"] --> B["Verified source backup"]
    B --> D["Clean SQLite database"]
    D --> T["Single migration transaction"]
    T --> V{"All validation passes?"}
    V -- "No" --> X["Discard target and repeat from clean database"]
    V -- "Yes" --> C["Commit and cut over authority"]
    C --> S["New writes exist only in SQLite"]
~~~

A long-lived JSON/SQLite dual-write mode is not approved. It would create two
possible authorities and additional partial-failure cases.

Before the first successful SQLite write, the untouched JSON backup can
support rollback to the old runtime. After SQLite accepts new writes, JSON is
only a historical pre-cutover snapshot and must not be described as current.
Recovery after that point must use a valid SQLite backup or an explicitly
tested forward export of post-cutover data. Rolling back to JSON while
discarding newer SQLite records is data loss and requires explicit owner
approval.

### Backup and Recovery

- SQLite backups must use a database-consistent mechanism rather than copying
  only the main file while writes may be active.
- A backup is not considered valid until it has been restored and checked in
  an isolated location.
- Backup and restore must preserve current facts, history, raw event order,
  Unicode values, and schema version.
- Backup frequency, retention, encryption, and storage location are not
  selected by this ADR.
- Recovery procedures must identify which store is authoritative and must
  never merge JSON and SQLite implicitly.

### Required Tests Before Cutover

Implementation approval requires isolated tests using temporary data for:

- interruption or failure during migration;
- safe repetition after a failed migration;
- duplicate import prevention;
- malformed or structurally unexpected JSON;
- literal Unicode preservation;
- preservation of raw-memory ordering;
- preservation of current fact values;
- recovery of superseded fact history;
- atomic current-fact and history updates;
- backup creation and successful restore;
- source/destination count and integrity validation.

Tests must not read from or modify real memory files.

### Explicitly Deferred Decisions

The following are not part of the accepted architecture and require separate
evidence and approval:

- SQLite FTS5;
- vector search and embedding storage;
- PostgreSQL;
- graph databases or graph projections;
- evidence graphs;
- persistent Nel identity tables;
- persistent goal tables;
- multi-device synchronization;
- database encryption implementation;
- cloud embedding of private memory;
- WAL mode and checkpoint policy;
- semantic retrieval and ranking;
- permanent schemas for thoughts, preferences, identity, or autonomy.

Deferral means no schema should reserve speculative tables or columns for
these capabilities. They should be evaluated only after real access patterns,
retrieval failures, privacy requirements, or concurrency needs are measured.

### Consequences

Positive consequences:

- Nel gains a local transactional source of truth with a small maintenance
  surface.
- Current user facts remain fast and direct to read.
- Superseded facts remain recoverable without making routine reads depend on
  history reconstruction.
- Failed migration can be discarded and repeated safely.
- Future retrieval technologies can be evaluated without being embedded in
  the authoritative persistence decision.

Negative consequences:

- JSON-to-SQLite migration still carries private-data conversion risk.
- SQLite serializes writes and assumes the initial single-owner,
  single-process operating model.
- Search remains limited to deterministic SQL, metadata, and recency until a
  separate retrieval decision is approved.
- The accepted schema does not yet persist Nel identity, goals, or generated
  thoughts.
- Operational backup discipline is still required.

### Remaining Product Questions

This ADR does not decide:

- which interactions qualify as durable **memory_events**;
- how long raw memory and superseded fact history are retained;
- whether corrections hide, tombstone, or physically erase prior values;
- backup frequency, retention period, and storage location;
- the local-device threat model;
- whether losing post-backup events is acceptable during disaster recovery;
- whether multi-device use will ever become a product requirement.

Decision: adopt SQLite with only **schema_version**, **memory_events**,
**user_facts_current**, and **user_fact_history** as Nel's authoritative local
persistence architecture. Keep all retrieval extensions and additional
domain tables deferred.

Status: Accepted.

## ADR-002: Product Ownership and Major Decisions

Context: The Project Owner should control product consequences without being
required to design software architecture.

Options: AI-led architecture without approval; owner chooses every technical
detail; delegated reversible implementation with owner approval for material
changes.

Decision: Ömər approves major product and architecture decisions. AI agents
choose the simplest reversible implementation details and mark undefined
choices provisional.

Consequences: Major changes require alternatives, tradeoffs, recommendation,
and approval. Small architecture-preserving fixes may proceed with evidence.

Status: Accepted.

## ADR-003: Separate Truth Categories and Namespaces

Context: Model output and user facts were previously capable of being
misattributed to Nel.

Options: one undifferentiated memory; prompt-only distinctions; explicit
separation of user facts, Nel state, inference, thoughts, and raw memory.

Decision: Truth categories and ownership namespaces must be explicit. User
facts and Nel-owned facts cannot share an unmarked namespace.

Consequences: Structured user knowledge overrides conflicting raw memory.
Nel-owned identity requires separate storage. Existing persistence is
insufficient for the stable system.

Status: Accepted.

## ADR-004: Local-First With Explicit Cloud Inference

Context: Nel must protect private continuity while using capable hosted
models when configured.

Options: cloud-only; local-only; local-first with explicit cloud inference.

Decision: Nel is local-first, not local-only. Cloud inference is permitted
only through explicit configuration.

Consequences: Data and credentials remain owned by Ömər. Prompt context must
be minimized. Provider use cannot make cloud state authoritative.

Status: Accepted.

## ADR-005: Provider-Neutral Core, NVIDIA NIM as Current Provider

Context: Ollama was removed and the repository migrated to NVIDIA NIM through
an OpenAI-compatible API.

Options: bind Nel to NIM; bind Nel to a generic OpenAI implementation; keep a
stable capability boundary with NIM as the configured implementation.

Decision: NIM is the current provider, but provider replacement must not
change Nel's identity or memory. The stable boundary covers text generation,
structured generation, timeouts, and clear errors.

Consequences: Current hardcoded construction is temporary. Configuration-
driven selection is expected. Streaming, tools, and multimodal support remain
future capabilities.

Status: Accepted.

## ADR-006: Generic Validated User-Fact Extraction

Context: Topic-specific extraction and unconstrained JSON caused stale or
normalized-away user facts.

Options: hardcoded domain parsers; unconstrained model JSON; generic
schema-constrained extraction with local validation and repair.

Decision: Use a topic-neutral fact envelope containing key, literal value,
subject, and confidence. Accept validated `subject=user` facts only,
normalize keys generically, retry invalid output once, then log and store
nothing.

Consequences: Runtime code cannot add demo extractors for hobbies or media.
Literal values should be preserved. Semantic key synonym handling remains an
open technical problem.

Status: Accepted.

## ADR-007: JSON Is Prototype Persistence

Context: Flat JSON is simple but lacks transactions, migrations, concurrency
control, and historical supersession.

Options: retain JSON indefinitely; migrate immediately without baseline
tests; treat JSON as temporary and approve a tested migration later.

Decision: JSON remains prototype persistence only. A durable transactional
store is required before the first stable version.

Consequences: A migration needs backup, restore, validation, and history
preservation. SQLite is the provisional leading option, not yet an accepted
implementation decision.

Status: Accepted.

## ADR-008: Controlled Autonomy and Self-Modification

Context: Initiative is central to Nel, but external action and code changes
can create irreversible harm.

Options: reactive-only behavior; unrestricted autonomy; bounded internal
autonomy with explicit approval for risky effects.

Decision: Permit non-destructive internal state, reflection, silence, topic
proposals, memory organization, provisional preferences, and plans. Risky
external actions require explicit approval.

Consequences: Capabilities need permission boundaries. Future
self-modification must use proposal, isolated patch, tests, review, explicit
approval, and merge.

Status: Accepted.

## ADR-009: CLI Is a Development Shell

Context: Interface ideas can distract from unreliable core behavior.

Options: treat CLI as product; begin desktop/voice/mobile now; keep CLI as a
temporary shell and defer interfaces.

Decision: The current CLI is not the final interface. Interface development
waits until core behavior is reliable.

Consequences: Voice, vision, desktop control, mobile, and physical movement
are post-foundation work. The project must not become a generic CLI or plugin
framework prematurely.

Status: Accepted.

## ADR-010: Capability-Based Roadmap

Context: Date promises and feature-count sprints are not credible at the
prototype stage.

Options: fixed-date roadmap; feature sprints; dependency-gated capability
milestones.

Decision: Use capability-based milestones with evidence-based exit criteria
and no unsupported completion dates.

Consequences: Documentation, cleanup, persistence reliability, and testing
precede major autonomy or interfaces. `TODO.md` is non-authoritative.

Status: Accepted.

## ADR-011: Current Composition and Runtime Are Temporary

Context: `src/core/nel.py` and a daemon-thread Clock currently own runtime
wiring, but stable lifecycle requirements are not met.

Options: declare current design permanent; replace it immediately; retain it
while testing lifecycle boundaries and evaluating a safer runtime.

Decision: Keep the current composition root and threaded Clock provisionally.
Any replacement is a major architecture change requiring a proposal and
approval.

Consequences: Lifecycle tests come before migration. A single-process event
loop is a candidate, not an accepted decision.

Status: Accepted.

## ADR-012: Provisional NIM Model and Background Thought Policy

Context: Qualification found `meta/llama-3.1-70b-instruct` to have the best
combined Azerbaijani conversation and structured extraction quality among
the tested NIM models, but latency and timeout reliability remain variable.
Automatic background generation would compete with foreground requests and
could repeatedly consume long timeout windows.

Options: retain the previous model and automatic thoughts; adopt the 70B
model for all generation; adopt the 70B model for foreground work while
temporarily disabling automatic LLM-generated background thoughts.

Decision: Adopt `meta/llama-3.1-70b-instruct` provisionally for foreground
conversation and structured extraction. Use a 45-second request timeout with
SDK retries disabled. Keep automatic background thoughts disabled by default
through configuration while retaining the existing Clock, EventBus,
ThoughtService, and DecisionEngine implementation.

Consequences: Foreground requests fail once after at most one configured
client attempt and continue through existing graceful error handling.
Reflection code remains available but inactive by default. Re-enabling it or
selecting a permanent model requires evidence from a faster reliable model or
an approved scheduling policy.

Status: Accepted.
