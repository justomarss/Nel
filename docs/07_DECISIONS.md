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
