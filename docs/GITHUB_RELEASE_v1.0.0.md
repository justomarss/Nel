# Nel v1.0.0

Nel v1.0.0 is the first release-qualified version of the local-first persistent personal AI core.

## Highlights

- Deterministic Decision Engine routing before provider calls.
- Provider-independent persistent identity, facts, goals, and memory.
- Generic Knowledge Grounding with exact literal source evidence and no provider-authoritative writes.
- One canonical, deterministic `ContextAssembler` JSON bundle per conversational request, bounded to 12,000 characters.
- SQLite schema v4 with eight `STRICT` tables, immutable identity triggers, versioned history, fact retirement, optimistic goal updates, and guarded startup.
- Explicit provider-free `/goal`, `/fact`, and `/remember` commands plus common Azerbaijani local reads.
- Minimal in-memory Thought System with cancellation, single-flight execution, and no permanent write authority.
- Validated SQLite backup and isolated restore verification.

## Verification

- **300** assertion-based tests pass.
- UTF-8 test run, `compileall`, dependency verification, and `git diff --check` pass.
- Final acceptance verified restart continuity, canonical-context exclusivity, local provider-free routes, failure boundaries, sustained runtime, and unchanged persistence.

## Operational Notes

- Tested on Windows with Python 3.14.5 only.
- Runtime requires an existing validated schema-v4 database; it never auto-creates or auto-migrates production storage.
- Private runtime data is not included in the source release.
- NVIDIA NIM is the configured provider and has no automatic fallback. Provider outages fail gracefully while local routes remain available.
- Historical JSON is not an active backend. `scripts/sqlite_cutover.py` is retired schema-v1 tooling.

## Known Limitations

The CLI remains a development shell. Context relevance is lexical, grounding is intentionally conservative, background thoughts are disabled, and planning, reminders, external actions, semantic retrieval, voice, vision, and hardware integration are not implemented.

See [RELEASE_NOTES_v1.0.0.md](../RELEASE_NOTES_v1.0.0.md) and [Readme.md](../Readme.md) for complete details.

Nel is experimental personal AI software. It is artificial and does not claim consciousness or human equivalence.
