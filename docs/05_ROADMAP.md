# Nel Roadmap

Status: Descriptive. Capability-based; no promised dates.

## Planning Rules

- Reliability and clarity precede feature count.
- Each milestone starts only when its dependencies are satisfied.
- Completion requires evidence, not the presence of placeholder classes.
- Major architecture still requires the approval process.
- Voice, vision, desktop control, and public-product work remain deferred
  until core behavior is stable.

## Milestone 0: Onboarding Baseline

Goal: establish one authoritative description of Nel.

Deliverables:

- constitution, team, project, architecture, roadmap, current state,
  decisions, and AI rules;
- active versus legacy code inventory;
- supported run and test commands;
- explicit product and architecture contradictions.

Exit criteria:

- all onboarding documents exist and link correctly;
- provisional choices are visibly marked;
- no runtime or memory data changed as part of documentation work.

## Milestone 1: Reliability and Test Baseline

Goal: make current behavior observable and reproducible before expansion.

Deliverables:

- classify and quarantine or remove legacy/duplicate modules through an
  approved cleanup;
- tests for startup, shutdown, provider failures, state restoration, Clock
  failures, and memory safety;
- deterministic test fixtures using temporary data;
- clear logging and error boundaries;
- a reliable supported command for all tests.

Dependencies: Milestone 0.

Exit criteria:

- Nel starts and stops without orphaned work;
- provider/network failure does not corrupt data or crash silently;
- critical current workflows have automated tests;
- no real memory is touched by tests.

## Milestone 2: Durable Data Boundaries

Goal: separate user knowledge, Nel identity, raw memory, thoughts, goals, and
conversation context in persistent storage.

Deliverables:

- approved persistence ADR and migration plan;
- recoverable history for superseded facts;
- dedicated Nel-owned identity/state records;
- atomic writes and migration tests;
- backup, restore, correction, and deletion behavior;
- sanitized export path for debugging.

Dependencies: Milestone 1.

Exit criteria:

- user facts cannot be mistaken for Nel facts;
- current values and historical values are both recoverable;
- interrupted writes cannot corrupt the store;
- migration preserves existing private data.

## Milestone 3: Bounded Memory Retrieval

Goal: provide relevant context without sending all history to the model.

Deliverables:

- context budget and retrieval policy;
- deterministic structured-fact retrieval;
- recency and metadata filtering;
- conflict resolution using authoritative structured knowledge;
- retrieval quality tests and measurements.

Dependencies: Milestone 2.

Exit criteria:

- ordinary conversation uses bounded context;
- known relevant facts are retrieved reliably;
- stale conflicting raw memory does not override current knowledge;
- semantic retrieval is added only if measured gaps justify it.

## Milestone 4: Provider and Runtime Resilience

Goal: keep Nel coherent during provider, network, and scheduled-task failure.

Deliverables:

- configuration-driven provider construction;
- formal provider capability contract;
- bounded timeout/retry policy;
- owned lifecycle and safe scheduled work;
- concurrency protection for persistence;
- long-running resource and corruption tests.

Dependencies: Milestones 1-3.

Exit criteria:

- a test provider can replace NIM without changing Nel state;
- outages produce clear recoverable behavior;
- scheduled work cannot overlap uncontrollably;
- Nel can run for extended periods without resource growth or data damage.

## Milestone 5: Controlled Identity and Autonomy

Goal: let Nel develop and initiate without fabricating identity or exceeding
permission.

Deliverables:

- approved preference-formation policy;
- persistent provisional and established Nel traits;
- controlled topic proposals and silence decisions;
- explicit autonomy permissions;
- reflection that cannot directly become truth;
- interruption controls chosen by Ömər.

Dependencies: Milestones 2-4 and product choices on proactive interaction.

Exit criteria:

- Nel can explain whether a trait is stored, provisional, or unknown;
- autonomous behavior is bounded, inspectable, and stoppable;
- generated thoughts cannot silently mutate identity;
- proactive behavior is useful in sustained personal use.

## Milestone 6: First Stable Nel

Goal: satisfy the stable-version criteria in `03_PROJECT.md`.

Deliverables:

- end-to-end acceptance suite;
- privacy and failure review;
- memory accuracy evaluation;
- provider substitution test;
- sustained-use and long-running operational evaluation;
- current-state and decision documentation updated to match reality.

Dependencies: Milestones 1-5.

Exit criteria:

- all first-stable requirements pass with evidence;
- unresolved high-impact risks have owner-approved disposition;
- Ömər trusts memory and voluntarily uses Nel regularly.

## Post-Stable Exploration

Only after Milestone 6:

- desktop/avatar experience;
- voice;
- mobile connection;
- vision;
- physical movement;
- public-product evaluation.

These are not committed roadmap deliverables.

## Critical Dependency Chain

`documentation -> reliability tests -> durable data boundaries -> bounded retrieval -> resilient runtime -> controlled autonomy -> stable evaluation`

## Roadmap Risks

| Risk | Impact | Mitigation | Trigger |
|---|---|---|---|
| Feature work bypasses foundations | High | Enforce milestone dependencies | Voice/UI/autonomy proposed before reliability exits |
| Prototype JSON persists too long | High | Approve migration after baseline tests | Concurrent writes or unrecoverable conflicts |
| LLM behavior mistaken for product behavior | High | Validate and persist explicit state | Prompt-only personality fixes proliferate |
| Provider latency blocks testing | Medium | Test doubles and bounded integration tests | Repeated timeout failures |
| Roadmap becomes stale | Medium | Update after capability changes | Current State contradicts milestone status |
