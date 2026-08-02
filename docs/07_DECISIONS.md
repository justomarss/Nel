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

## ADR-014: Physical Companion as the Intended Primary Interface

Context: The CLI is already defined as a development shell, but Nel's
long-term product form was not explicit. A known direction is needed so core
behavior does not become coupled to the CLI or prematurely optimized for a
desktop application.

Options: leave the final interface undefined; make a conventional desktop or
mobile application primary; target a small physical desktop companion while
keeping Nel Core interface-independent.

Decision: Nel's intended final primary interface is a small physical desktop
companion, likely in a custom 3D-printed enclosure. Expected future hardware
includes a screen, microphone, speaker, camera, and either onboard computing
or a client connection to Nel Core. Physical movement and motors are optional.
The CLI, future desktop application, mobile connection, and physical device
must use the same platform-independent Nel Core behavior.

Consequences: This decision does not change roadmap priorities or authorize
hardware, robotics, camera, audio, UI, or device implementation. The CLI
remains the current development shell. Hardware abstraction must wait until a
physical prototype provides concrete constraints, and no interface may become
a separate authority for Nel's identity or memory.

Status: Accepted.

## ADR-015: Persistent Nel Identity v1

Context: Nel requires continuity that survives sessions and provider changes,
but generated personality prose is not authoritative identity. User facts,
temporary thoughts, and Nel-owned identity need an explicit conceptual
boundary before identity persistence is implemented.

Options: define identity through prompts; treat generated text as identity;
build a broad autonomous personality-learning system; establish a minimal
structured identity with controlled updates and recoverable history.

Decision: Identity v1 consists only of a stable identity ID, display name,
artificial nature, role as Ömər's persistent digital companion, and
provider-independent continuity. Nel identity must use a separate namespace
and storage boundary from user facts. Persistent identity must retain direct
current records and recoverable history. Only `IdentityService` may modify
identity.

Preferences use four states: `candidate`, `provisional`, `established`, and
`retired`. A user cannot directly assign Nel a preference, and one model
response cannot create one. Identity v1 may accept manually or experimentally
supplied candidate evidence and apply simple controlled promotion rules. It
does not define a complex autonomous preference-learning algorithm. Generated
text and temporary thoughts may propose candidates but never become identity
automatically.

Consequences: Identity must remain structured, provider-neutral, auditable,
and distinct from user knowledge. Implementation requires a separately
approved storage/schema change; this decision does not authorize database
tables or runtime integration. Evidence graphs, complex confidence formulas,
the long-term belief engine, automatic personality-trait formation,
relationship modeling, sensor-derived identity, emotional identity,
multi-user or multi-device identity, and autonomous constitutional changes
remain deferred.

Status: Accepted.

## ADR-016: Internal Thought System v1

Context: Nel needs a bounded internal process that is separate from
conversation, memory, knowledge, identity, goals, and actions. Existing
generated internal text must not acquire authority merely because a model
produced it. The governing principle is: "A thought is an observation, never
an authority."

Options: treat internal model text as persistent thought or truth; permit
thoughts to write directly to owned state; build a continuous autonomous
monologue and scheduler; use temporary observations that can cross only
explicit policy boundaries.

Decision: A Thought v1 instance is one temporary, bounded internal observation
created for a specific reason. Generated thought text is not truth. A thought
is not conversation, memory, knowledge, identity, a goal, or an action, and it
cannot directly modify any of them or external state.

A thought may produce typed candidates. A memory-related candidate contains
only an observation candidate, retention reason, source reference, and
durability suggestion. `MemoryPolicy` decides whether anything may reach
`MemoryService`. Knowledge, identity, future goal, and action candidates must
respectively pass through `KnowledgePolicy`, `IdentityPolicy`, future
`GoalPolicy`, and `Decision/PermissionPolicy`, followed by the service that
owns the permanent state. A generated thought or temporary thought record can
never bypass these policies.

Thought System v1 has one coordinator, one active background thought at most,
read-only bounded context, typed candidate validation, and policy boundaries.
Its only lifecycle states are `idle` and `running`. Completion or failure
returns the coordinator to `idle`. Cancellation invalidates the active job
token and returns it to `idle`; any late result carrying that token is
discarded. No queue, complex scheduler, or persistent thought database is
approved.

Background thinking remains disabled by default. If separately enabled after
reliability approval, it must be bounded by a timeout and resource limit.
Foreground interaction always has priority and cancels or invalidates active
background work. Device events from a future screen, microphone, or camera may
eventually supply permitted observations, but the thought system remains
hardware-independent and those observations gain no authority automatically.

Consequences: Permanent changes require validation by both the owning policy
and service. Raw thought text should disappear after use and must not be shown
as conversation or treated as durable state. The current Clock,
DecisionEngine, and ThoughtService are retained code but do not yet implement
this boundary. Persistent thought storage, continuous monologue, emotion,
autonomous goals, external actions, self-modification, consciousness modeling,
and complex preference learning remain deferred.

Status: Accepted.

## ADR-017: SQLite Runtime Cutover and Perspective Ownership

Context: The verified JSON-to-SQLite cutover produced an integrity-checked
schema-version-1 database and backup. The live database has since received a
post-cutover write, so historical JSON is no longer current and runtime
fallback would risk split authority. Conversation also demonstrated a generic
ownership error in which user first-person language was rendered as Nel
first-person language in the answer.

Options: retain a JSON/SQLite selector; dual-write both stores; make SQLite
the sole runtime authority while retaining JSON only as immutable history.
For perspective, add topic-specific response rules or define generic
speaker-ownership rules.

Decision: SQLite is the sole active Memory and Knowledge backend. Runtime
defaults to `memory/nel.sqlite3`, may accept an explicit database path for
isolated operation, and must open an existing validated database without
creating one. The temporary JSON backend selector is removed. Historical JSON
files remain migration and cutover evidence but receive no runtime writes.

Conversation context must distinguish speaker ownership generically. In user
input, Azerbaijani first-person forms refer to the user. Answers about
user-owned facts address the user in informal second person. Nel first-person
forms are reserved for Nel-owned identity or state. No topic-specific game,
anime, hobby, or media response logic is permitted.

Consequences: JSON rollback is invalid after the first SQLite-only write.
Recovery must use the live SQLite database or a verified SQLite backup. A
missing, corrupt, uninitialized, or incompatible production database causes a
redacted startup failure. Provider behavior, identity separation, graceful
provider failures, and shutdown behavior remain unchanged.

Status: Accepted.

## ADR-018: Goal System v1

Context: Nel needs to store, track, and review approved long-term outcomes
without treating wishes, generated text, thoughts, or reminders as durable
goals. Goal state must remain provider-independent, auditable, and separate
from user facts, memory, and Nel identity. A goal records an approved desired
outcome; it does not grant authority to act.

Options: infer and execute goals directly from conversation; allow thoughts
or model output to create goals; introduce a planning and scheduling system;
or implement a minimal controlled goal record with explicit ownership,
validation, revision history, and no autonomous execution.

Decision: Goal v1 is a durable, explicitly validated desired outcome with a
stable ID, title, optional bounded description, owner, observable success
condition, lifecycle state, priority, optional deadline, accepted progress,
version, timestamps, and approval/source reference. A goal is not a task,
plan, reminder, memory, fact, preference, identity record, or authority to
act. Vague intentions, user statements, thoughts, and model suggestions remain
temporary candidates until explicitly validated.

Ownership is `user`, `nel`, or `shared`. A user goal primarily belongs to
Ömər. A Nel goal is an explicitly owner-authorized system objective, not an
independent desire. A shared goal is a user-approved collaborative objective;
it does not imply equal agency, emotion, consent, or independent desire. Nel
may participate only through separately authorized capabilities. If the
outcome primarily belongs to Ömər, ownership remains `user` even when Nel
assists.

Durable lifecycle states are `active`, `paused`, `completed`, and `cancelled`.
Candidates are not a durable state. Reopening a completed or cancelled goal
requires explicit approval, creates a new version, and preserves terminal
history. Priority is `low`, `normal`, or `high`, defaults to `normal`, and
affects review ordering only. Deadlines are optional, preserve original input
and normalized date/time semantics, and never trigger automatic completion,
cancellation, reminders, or execution.

Progress verification state is `unknown`, `user_reported`, or `verified`.
`unknown` is not zero percent; it means no accepted progress evidence exists.
User-reported progress must be described as reported rather than verified.
Verified progress requires explicit owner confirmation or deterministic
evidence. Model output cannot promote progress from `unknown` to
`user_reported` or `verified`. Optional percentages do not replace evidence,
and completion always requires explicit acceptance that the success condition
has been satisfied.

`GoalService` is the sole normal write boundary. `GoalPolicy` validates
ownership, actor authority, lifecycle transitions, deadlines, progress
evidence, and expected versions before `GoalService` may write through a
repository. Every accepted update requires an expected-version check, stores
the new current record directly, and preserves the previous version in
recoverable history. Current goals and goal history remain separate from user
facts and identity. Thoughts and model output may create only temporary goal
candidates; they cannot create, update, pause, complete, cancel, or execute a
durable goal. In v1, durable changes require an explicitly validated user
instruction.

Goal context supplied to a provider is read-only, structured, and
provider-independent. It must never include all goals. The default maximum is
10 relevant `active` or `paused` goals, 5 recent `completed` or `cancelled`
goals, and 4,096 serialized characters total. Selection and truncation are
deterministic: active goals precede paused goals, high priority precedes normal
and low priority, then earlier deadlines, newer updates, and stable goal ID;
terminal goals are ordered by most recent update and stable goal ID. Items are
removed from the end of that order until the character budget is satisfied.

Exact duplicates and invalid state transitions are rejected deterministically.
Possible semantic conflicts are review candidates only: existing goals remain
unchanged until Ömər explicitly chooses to reprioritize, pause, revise, or
cancel. Staleness is a derived review condition, not a lifecycle state. A
missed deadline or an approved inactivity threshold may mark a goal for
review, but cannot mutate it automatically.

The smallest approved architecture consists of immutable `GoalCandidate`,
`GoalSnapshot`, and `GoalRevision` types; a deny-by-default `GoalPolicy` for
temporary candidates; `GoalService` as the only write boundary; a
transactional `GoalRepository`; and a bounded read-only goal-context builder.
The storage schema requires a separately approved migration and is not defined
by this ADR.

Consequences: Goal operations remain local and deterministic even if a model
or provider is unavailable. Nel cannot claim unverified progress, convert a
thought into a goal, or treat a goal as permission for external action.
Implementation must test transaction rollback, expected-version conflicts,
history recovery, namespace isolation, bounded context, Unicode preservation,
and absence of production-data writes.

Autonomous goal creation, execution, planning, subtasks, dependency graphs,
reminders, recurrence, notification scheduling, automatic progress claims,
automatic conflict resolution, semantic retrieval, external actions,
multi-user delegation, sensor-derived progress, device-specific behavior,
rewards, emotions, relationship modeling, consciousness, and
self-modification remain deferred.

Status: Accepted.

## ADR-019: Minimal Goal Persistence Schema

Context: ADR-018 requires durable current goals, recoverable revisions,
expected-version updates, explicit approval, and strict namespace separation.
Schema version 2 contains memory, user-fact, and Nel-identity storage but no
goal persistence. Goal persistence must remain small enough to reverse before
runtime integration and must not introduce planning or action infrastructure.

Options: store goals in JSON; add a single mutable SQLite table; add an event
log and reconstruct current goals; or add direct current storage plus a
history table. JSON lacks transactional integration, a mutable-only table
loses revisions, and event reconstruction adds unnecessary complexity.

Decision: schema version 3 adds exactly two `STRICT` tables,
`goals_current` and `goals_history`, plus one secondary current-state index.
`goals_current` stores the latest accepted record directly.
`goals_history` stores every superseded record. Goal tables have no foreign
keys to memory events, user facts, Nel identity, or thoughts.

The accepted schema is:

```sql
CREATE TABLE goals_current (
    goal_id TEXT PRIMARY KEY COLLATE BINARY,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT CHECK (
        description IS NULL OR length(trim(description)) > 0
    ),
    success_condition TEXT NOT NULL CHECK (
        length(trim(success_condition)) > 0
    ),
    owner TEXT NOT NULL CHECK (
        owner IN ('user', 'nel', 'shared')
    ),
    state TEXT NOT NULL CHECK (
        state IN ('active', 'paused', 'completed', 'cancelled')
    ),
    priority TEXT NOT NULL CHECK (
        priority IN ('low', 'normal', 'high')
    ),
    deadline TEXT CHECK (
        deadline IS NULL OR (
            length(deadline) >= 20
            AND substr(deadline, 11, 1) = 'T'
            AND substr(deadline, -1, 1) = 'Z'
        )
    ),
    progress_summary TEXT CHECK (
        progress_summary IS NULL OR length(trim(progress_summary)) > 0
    ),
    progress_percentage INTEGER CHECK (
        progress_percentage IS NULL
        OR progress_percentage BETWEEN 0 AND 100
    ),
    progress_verification TEXT NOT NULL CHECK (
        progress_verification IN (
            'unknown', 'user_reported', 'verified'
        )
    ),
    source_kind TEXT NOT NULL CHECK (
        source_kind IN (
            'validated_user', 'approved_system', 'approved_experiment'
        )
    ),
    source_reference TEXT NOT NULL CHECK (
        length(trim(source_reference)) > 0
    ),
    approval_reference TEXT NOT NULL CHECK (
        length(trim(approval_reference)) > 0
    ),
    revision_reason TEXT CHECK (
        revision_reason IS NULL OR length(trim(revision_reason)) > 0
    ),
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL CHECK (
        length(created_at) >= 20
        AND substr(created_at, 11, 1) = 'T'
        AND substr(created_at, -1, 1) = 'Z'
    ),
    updated_at TEXT NOT NULL CHECK (
        length(updated_at) >= 20
        AND substr(updated_at, 11, 1) = 'T'
        AND substr(updated_at, -1, 1) = 'Z'
    ),
    CHECK (
        (progress_verification = 'unknown'
         AND progress_summary IS NULL
         AND progress_percentage IS NULL)
        OR
        (progress_verification IN ('user_reported', 'verified')
         AND progress_summary IS NOT NULL)
    ),
    CHECK (
        source_kind != 'approved_system' OR owner = 'nel'
    ),
    CHECK (
        (version = 1 AND revision_reason IS NULL)
        OR (version > 1 AND revision_reason IS NOT NULL)
    )
) STRICT;

CREATE TABLE goals_history (
    goal_id TEXT NOT NULL COLLATE BINARY,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT CHECK (
        description IS NULL OR length(trim(description)) > 0
    ),
    success_condition TEXT NOT NULL CHECK (
        length(trim(success_condition)) > 0
    ),
    owner TEXT NOT NULL CHECK (
        owner IN ('user', 'nel', 'shared')
    ),
    state TEXT NOT NULL CHECK (
        state IN ('active', 'paused', 'completed', 'cancelled')
    ),
    priority TEXT NOT NULL CHECK (
        priority IN ('low', 'normal', 'high')
    ),
    deadline TEXT CHECK (
        deadline IS NULL OR (
            length(deadline) >= 20
            AND substr(deadline, 11, 1) = 'T'
            AND substr(deadline, -1, 1) = 'Z'
        )
    ),
    progress_summary TEXT CHECK (
        progress_summary IS NULL OR length(trim(progress_summary)) > 0
    ),
    progress_percentage INTEGER CHECK (
        progress_percentage IS NULL
        OR progress_percentage BETWEEN 0 AND 100
    ),
    progress_verification TEXT NOT NULL CHECK (
        progress_verification IN (
            'unknown', 'user_reported', 'verified'
        )
    ),
    source_kind TEXT NOT NULL CHECK (
        source_kind IN (
            'validated_user', 'approved_system', 'approved_experiment'
        )
    ),
    source_reference TEXT NOT NULL CHECK (
        length(trim(source_reference)) > 0
    ),
    approval_reference TEXT NOT NULL CHECK (
        length(trim(approval_reference)) > 0
    ),
    revision_reason TEXT CHECK (
        revision_reason IS NULL OR length(trim(revision_reason)) > 0
    ),
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL CHECK (
        length(created_at) >= 20
        AND substr(created_at, 11, 1) = 'T'
        AND substr(created_at, -1, 1) = 'Z'
    ),
    updated_at TEXT NOT NULL CHECK (
        length(updated_at) >= 20
        AND substr(updated_at, 11, 1) = 'T'
        AND substr(updated_at, -1, 1) = 'Z'
    ),
    superseded_at TEXT NOT NULL CHECK (
        length(superseded_at) >= 20
        AND substr(superseded_at, 11, 1) = 'T'
        AND substr(superseded_at, -1, 1) = 'Z'
    ),
    PRIMARY KEY (goal_id, version),
    CHECK (
        (progress_verification = 'unknown'
         AND progress_summary IS NULL
         AND progress_percentage IS NULL)
        OR
        (progress_verification IN ('user_reported', 'verified')
         AND progress_summary IS NOT NULL)
    ),
    CHECK (
        source_kind != 'approved_system' OR owner = 'nel'
    ),
    CHECK (
        (version = 1 AND revision_reason IS NULL)
        OR (version > 1 AND revision_reason IS NOT NULL)
    )
) STRICT;

CREATE INDEX goals_current_state_updated_idx
ON goals_current (state, updated_at DESC, goal_id);
```

Only `description`, `deadline`, `progress_summary`, `progress_percentage`, and
version-1 `revision_reason` may be `NULL`. `unknown` progress is not zero
percent and carries neither summary nor percentage. Reported and verified
progress require a summary; their percentage remains optional.

Durable source kinds are `validated_user`, `approved_system`, and
`approved_experiment`. Every source kind still requires explicit Ömər approval
and a non-empty approval reference. `approved_system` is valid only for an
explicitly authorized Nel-owned goal. `approved_experiment` is valid only in
controlled development or isolated tests. Model output, thought output, and
unvalidated runtime input are prohibited durable sources. `GoalPolicy` and
`GoalService` enforce approval provenance; the database additionally prevents
`approved_system` from being stored with a non-Nel owner.

Ordinary updates may transition only non-terminal goals according to
`GoalPolicy`; they must reject every update to `completed` or `cancelled`
records. `completed` to `active` is permitted only through a dedicated reopen
operation. `cancelled` to `active` is permitted only through a dedicated
restore operation. Both operations require `validated_user` source, explicit
Ömər approval, an approval reference, a non-empty revision reason, and an
expected version. They insert the terminal current record into history and
write a new active current version atomically. No trigger enforces lifecycle
transitions; `GoalPolicy`, `GoalService`, and dedicated repository operations
own that validation because SQLite lacks approval context.

Creation and every revision use an explicit `BEGIN IMMEDIATE` transaction.
For an update, the repository reads the current row, compares it with the
required expected version, inserts the complete old row into history, and
updates exactly one current row to `expected_version + 1`. Any mismatch,
constraint failure, or row-count failure rolls back both writes. Goals are
cancelled rather than physically deleted.

All human-readable data uses SQLite `TEXT` and Python `str`; values are bound
as parameters and are not normalized, case-folded, trimmed, or rewritten.
Timestamps are canonical UTC ISO-8601 text ending in `Z`. Application code
performs strict calendar parsing before opening the write transaction; schema
checks enforce only the canonical structural shape. `created_at` never
changes, `updated_at` marks when a version became current, and
`superseded_at` marks when it entered history.

Migration from schema version 2 to 3 requires a valid v2 database, successful
integrity check, and exactly the six approved v2 tables and identity triggers.
Inside one `BEGIN IMMEDIATE` transaction it refuses pre-existing goal schema,
creates the two empty goal tables and index, replaces the schema-version row
with version 3, validates exactly eight approved tables, and confirms existing
memory, facts, fact history, and identity are unchanged. A valid v3 database
is an idempotent no-op. Any failure rolls back to v2. Runtime must never
migrate automatically.

A validated v2 backup is required before migration. A post-migration v3
backup must be independently restore-verified for schema, integrity, Unicode,
goal counts, and current/history consistency. Before the first goal write,
rollback restores the v2 backup and v2-compatible runtime. After the first
goal write, v2 rollback would lose authoritative goal data and is prohibited;
recovery must use a validated v3 backup. SQL down-migration is not supported.

Required tests cover v2-to-v3 migration, idempotency, unchanged existing
namespaces, current/history consistency, expected-version conflicts,
transaction rollback, reopen and restore boundaries, source-kind rules,
Unicode preservation, backup and isolated restore, namespace isolation, and
temporary-data-only operation.

Consequences: Goal persistence remains direct, transactional, auditable, and
provider-independent. The schema adds no subtasks, reminders, recurrence,
dependencies, plans, evidence graphs, semantic search, action authority, or
additional goal tables or triggers. Repository, service, runtime, and backup
support remain separate implementation stages.

Status: Accepted.

## ADR-020: Decision Engine v1

Context: Nel needs one deterministic routing decision before any provider call
after an input event. The current `DecisionEngine` is only a time-based
background-thought eligibility check, while foreground routing is distributed
through `Nel.think()`. Decision Engine v1 must establish a narrow routing
boundary without changing the existing Memory, Knowledge, or Identity flows.

Options: keep routing embedded in `Nel`; let the provider classify routes; add
a broad candidate-routing engine for every persistent subsystem; or add a
small deterministic engine for foreground conversation, explicit goal
commands, and background thought starts. Embedded routing remains difficult to
test as one decision, provider classification would grant generated output
operational authority, and broad candidate routing would prematurely refactor
accepted persistence behavior.

Decision: Decision Engine v1 is a pure provider-independent routing layer. A
decision is the immutable selection of exactly one primary route for one
bounded input event. It records what route is allowed and why; it does not
perform the route, validate persistent domain state, grant write authority, or
represent truth, memory, identity, or permission.

The only allowed primary decisions are:

- `conversation_response`;
- `ask_clarification`;
- `goal_command`;
- `thought_start`;
- `no_action`.

`memory_candidate`, `knowledge_candidate`, and `identity_candidate` are not
Decision Engine v1 decisions. Their design and routing are deferred. Existing
memory judging, knowledge extraction, and read-only identity behavior remain
unchanged after a `conversation_response` route is selected. Decision Engine
v1 must not refactor, replace, or bypass their current services and policies.

`DecisionContext` is immutable and contains only:

```text
event_id
event_kind
user_input
operational_state
explicit_command_parse
foreground_activity
background_thought_state
```

`event_kind` is `user_turn` or `background_event`. `user_input` is limited to
4,096 characters. `explicit_command_parse` is a bounded deterministic parse
result containing only command recognition, operation, required command
arguments, confirmation markers, and syntax status; it is limited to 4,096
serialized characters. Identifiers and state values use fixed enums or bounded
strings. Total serialized context is limited to 8,192 characters. Oversized or
invalid context is rejected before routing. Full memory, user facts, Nel
identity, goals, and provider output are excluded. A service may read the
domain records required after its route is selected, but those records do not
participate in route selection.

`DecisionResult` is immutable and contains only:

```text
event_id
primary_decision
target_route
reason_code
validated_command_payload
requires_confirmation
```

`validated_command_payload` is absent except for a syntactically valid explicit
goal command. It is bounded by the command-parse limit and is not proof that a
domain transition is valid. GoalPolicy and GoalService retain that authority.
Reason codes are fixed machine-readable values, not generated prose. No
confidence score, chain-of-thought, secondary candidate list, or provider
advice is stored.

Decision precedence for a `user_turn` is exactly:

1. Validate the bounded context. Invalid or oversized context produces
   `no_action` with a deterministic rejection reason.
2. Require the foreground dispatcher to cancel or invalidate any running
   background thought before it executes the selected route. The pure engine
   records no cancellation side effect; late cancelled output remains
   discarded.
3. If `explicit_command_parse` recognizes `/goal`:
   - a syntactically complete command with its command-level confirmation
     markers produces `goal_command`;
   - a malformed, incomplete, or confirmation-deficient command produces
     `ask_clarification`.
4. A non-empty ordinary user input produces `conversation_response`.
   Natural-language goal statements remain ordinary conversation and cannot
   produce `goal_command`.
5. Empty or whitespace-only input produces `no_action`.

Decision precedence for a `background_event` is exactly:

1. If foreground activity exists, produce `no_action`.
2. If a background thought is already running, produce `no_action`.
3. If operational state is not idle, produce `no_action`.
4. Otherwise produce `thought_start`.

Background scheduling, the disabled-by-default configuration gate, and
time-based eligibility remain outside the pure engine. They determine whether
a background event is submitted; they do not change routing precedence.
Foreground conversation always has priority.

The correct execution flow is:

```text
input event
-> bounded deterministic DecisionContext
-> DecisionEngine
-> immutable DecisionResult
-> selected route
-> provider only when that selected route requires it
```

No provider call may occur while constructing the context or selecting the
route. Provider output never participates in route selection. A
`conversation_response` may enter the existing conversation pipeline after
selection. `ask_clarification` should use deterministic command guidance in v1
and therefore does not require a provider. `goal_command` routes only explicit
slash commands to GoalService. `thought_start` routes to ThoughtCoordinator.
`no_action` invokes no provider or write service.

Decision Engine has no repository access and no write authority. It cannot
create or update goals, memories, knowledge, or identity; execute external
actions; grant permission; retry stale goal versions; or bypass GoalPolicy.
GoalService remains the only goal write boundary. ThoughtCoordinator retains
single-flight and cancellation ownership. Existing Memory, Knowledge, and
Identity services retain their current behavior and authority.

Failure handling is fail-closed and route-specific. Invalid context yields
`no_action`. Invalid explicit goal syntax or missing command confirmation yields
`ask_clarification`. Goal policy rejection, expected-version conflict, or
transaction failure produces the existing safe goal-command error without a
provider fallback or alternate write. Provider failure after
`conversation_response` produces the existing redacted application error.
Thought start or worker failure produces a redacted diagnostic and restores a
valid idle state. An unknown decision, unknown route, engine exception, or
result/context mismatch executes nothing. A failure never falls back to a more
permissive route.

The smallest architecture is:

```text
User turn --------------------+
                              v
Background event -> DecisionContext -> DecisionEngine -> DecisionResult
                                                      |
                 +------------------------------------+------------------+
                 |                 |                  |                  |
        conversation_response  goal_command   ask_clarification   thought_start
                 |                 |                  |                  |
        existing Nel pipeline  GoalService   deterministic text  ThoughtCoordinator
                 |
          provider if needed

Any rejected or ineligible route -> no_action
```

Implementation should proceed in the smallest reversible stages:

1. Add frozen `DecisionContext`, decision enum, reason-code enum, and
   `DecisionResult` with bounded validation and no runtime wiring.
2. Implement and exhaustively test a pure `decide(context)` function using the
   accepted precedence.
3. Build the bounded context at the start of Nel orchestration, before any
   provider call, and route explicit goal commands or deterministic
   clarification through the result.
4. Gate background thought starts through separate background-event decisions
   while preserving the existing configuration, timing, single-flight, and
   cancellation behavior.
5. Run regression tests proving the current conversation, Memory, Knowledge,
   Identity, GoalService, provider-failure, and shutdown behavior remains
   unchanged outside the selected routing boundary.

Required tests cover immutable bounded models, exact precedence, exactly one
primary decision, no provider call during route selection, explicit `/goal`
routing only, malformed-command clarification, natural-language goal text as
conversation, foreground cancellation, background rejection while foreground
or thought work is active, unknown-result rejection, fail-closed behavior, no
repository access, and unchanged existing Memory, Knowledge, and Identity
flows.

Deferred scope includes memory candidates, knowledge candidates, identity
candidates, natural-language goal interpretation, provider-assisted routing,
secondary or compound decisions, durable decision history, candidate queues,
planning, reminders, scheduling policy, external actions, permission
escalation, autonomous goal creation, probabilistic ranking, confidence
formulas, rewards, emotion, consciousness modeling, and self-modification.

Consequences: v1 creates one narrow deterministic boundary before provider
use and prevents provider output from selecting operational routes. It does
not unify every existing subsystem, and ordinary conversation may continue to
run the current memory and knowledge behavior after its route is selected.
This limitation is intentional and keeps the first implementation reversible.

Status: Accepted.
