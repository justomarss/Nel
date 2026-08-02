# Nel v1.0.0 Release Notes

## Release Summary

Nel v1.0.0 establishes a tested local-first core for a persistent personal digital companion. The release separates durable identity and owner-approved state from language-model output, uses deterministic routing and bounded context assembly, and stores authoritative data in guarded SQLite schema v4.

This release is qualified for the existing Windows personal deployment with Python 3.14.5. It is not a turnkey public assistant distribution and does not include private runtime data or a public database bootstrap workflow.

## Main Capabilities

- Azerbaijani conversation through NVIDIA NIM's OpenAI-compatible API.
- Deterministic Decision Engine routing before provider invocation.
- Provider-free local identity, user-fact, and goal reads.
- Explicit `/goal`, `/fact`, and `/remember` command families.
- Persistent immutable core identity and bounded read-only identity context.
- Versioned goals with history, expected-version updates, and controlled terminal-state restoration.
- Versioned facts with history, correction, retirement, and reactivation.
- Explicit durable memory with deterministic exact-duplicate rejection.
- Generic Knowledge Grounding using literal values and exact source spans.
- Unified deterministic `ContextAssembler` with one canonical JSON bundle and a 12,000-character ceiling.
- Minimal in-memory Thought System with cancellation, single-flight execution, and no write authority.
- Redacted startup, provider, persistence, context, and background failure boundaries.

## Architecture Highlights

The provider is a replaceable language component, not Nel's identity or durable state. `DecisionEngine` selects one route per event. Local commands call their owning services directly; conversation uses Knowledge Grounding, ContextAssembler, Brain, and the configured provider.

`MemoryService`, `KnowledgeService`, `IdentityService`, and `GoalService` are the normal state boundaries. Generated replies and temporary thoughts cannot bypass them. Provider-proposed facts remain ephemeral until the user executes a confirmed `/fact set` command.

Every conversational provider request contains one deterministic canonical JSON context. Stored identity, facts, goals, preferences, and memories do not appear through another prompt path. Static instructions and user input have separate bounds.

## Persistence and Data Integrity

SQLite schema v4 contains exactly eight `STRICT` tables:

- `schema_version`
- `memory_events`
- `user_facts_current`
- `user_fact_history`
- `nel_identity_current`
- `nel_identity_history`
- `goals_current`
- `goals_history`

The schema also requires two immutable-core identity triggers and one goal-state index. Runtime requires an existing integrity-checked schema-v4 database and never silently creates or migrates production storage.

Accepted writes use explicit transactions. Current records are stored directly, previous fact/identity/goal versions remain recoverable, goal updates use optimistic version checks, and retired facts remain in history while disappearing from normal reads and context.

Backups use Python's `sqlite3` backup API and are accepted only after isolated restore, integrity, complete schema, continuity, Unicode, and logical-equality validation.

## Safety Guarantees

- Provider output has no direct durable-write authority.
- Ordinary conversation does not automatically create memory.
- Questions and local read routes do not enter fact extraction.
- Thoughts cannot mutate memory, facts, identity, goals, or external state.
- Missing or malformed optional context sections fail closed or are safely omitted according to policy.
- Identity failure aborts conversation rather than fabricating identity.
- Expected operational failures are redacted; credentials and stored values are not included in diagnostics.
- Tests use temporary persistence and protect production files by hash.

## Migration History

Nel moved from prototype JSON persistence through four controlled SQLite schema stages:

1. Schema v1 introduced memory events and current/history user facts.
2. Schema v2 added current/history Nel identity and immutable-core triggers.
3. Schema v3 added current/history goals and the goal-state index.
4. Schema v4 added versioned fact retirement and revision reasons without adding tables.

Each production migration was transactional, rehearsed on isolated copies, protected by validated backups, and followed by runtime compatibility checks. Historical JSON snapshots remain inactive history. `scripts/sqlite_cutover.py` is retired schema-v1 tooling and refuses operational CLI use.

## Test and Acceptance Evidence

- 300 assertion-based `unittest` tests pass with UTF-8 output.
- `compileall` passes for runtime, scripts, and tests.
- `git diff --check` passes.
- Credential-free imports and exact dependency verification pass.
- Invalid configuration exits without traceback or credential exposure.
- Schema-v4 backup corruption tests reject missing identity triggers and the goal index.
- Failure-injection tests cover SQLite reads, malformed context snapshots, invalid core identity, provider failure, and backup structure.
- Sustained runtime covers multiple clock ticks with background thoughts disabled, clean shutdown, and no spontaneous writes.
- Final acceptance confirmed deterministic local reads, canonical-context exclusivity, restart continuity, isolated backup restore, and unchanged production persistence.

The configured live provider was unavailable during final acceptance. The request failed through the documented redacted boundary without corrupting state or disabling local routes.

## Breaking and Operational Notes

- Runtime requires schema v4; schema v1-v3 databases are rejected at startup.
- Runtime no longer supports JSON as an active backend and performs no dual writes.
- Runtime never auto-migrates or creates an empty production database.
- Recovery after new SQLite writes must use an explicitly selected verified SQLite backup; historical JSON is not current state.
- The tested environment is Windows with Python 3.14.5. Other platforms and Python versions are not release-qualified.
- NVIDIA credentials, model ID, and OpenAI-compatible base URL are required for conversation, but not for imports or local tests.

## Upgrade and Startup Notes

1. Stop all Nel processes.
2. Confirm the database is schema v4 and passes integrity and structural validation.
3. Create and independently verify a fresh SQLite backup.
4. Install the exact versions in `requirements.txt` using Python 3.14.5.
5. Run `scripts/verify_environment.py`.
6. Configure `.env` locally without committing it.
7. Start with `.\.venv\Scripts\python.exe main.py`.
8. Exit immediately once to confirm guarded startup and clean shutdown before normal use.

See `Readme.md` for commands and backup/restore procedures.

## Known Limitations

- NVIDIA availability and latency are external operational risks; no provider fallback exists.
- The CLI is a development shell.
- Context selection is lexical, not semantic, and can miss paraphrases or morphology.
- The character budget is not a provider-token guarantee.
- Grounding favors false negatives over unsafe fact storage.
- Memory duplicate detection has a documented concurrent-writer race.
- Background thoughts remain disabled and non-persistent.
- A fresh clone has no private runtime database or public schema bootstrap workflow.

## Intentionally Deferred

- Automatic fact correction or confidence-based writes.
- Automatic conversation-memory retention.
- Automatic identity preference learning or promotion.
- Persistent thoughts, emotions, consciousness modeling, and autonomous goals.
- Natural-language goal creation, planning, reminders, recurrence, scheduling, and external actions.
- Embeddings, vector search, semantic summaries, and graph storage.
- Configuration-driven provider selection, streaming, tools, and multimodal input.
- Voice, vision, desktop/mobile clients, and physical companion hardware.
- Multi-user support, multi-device identity, unrestricted browsing, and self-modification.

Nel remains experimental personal AI software. It is artificial and does not claim consciousness, human equivalence, or independent authority.
