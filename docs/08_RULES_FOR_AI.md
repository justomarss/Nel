# Rules for AI Agents

Status: Normative

These rules apply to every AI agent working on Nel, including Codex and
ChatGPT. The Constitution and accepted ADRs take precedence if a conflict is
found.

## Before Changing Anything

An AI agent must:

1. Read the relevant onboarding documents.
2. Inspect the relevant repository files rather than relying on summaries.
3. Run `git status --short` and preserve existing user changes.
4. Identify the active entry point and affected modules.
5. Confirm whether the task is a small implementation change or a material
   architecture/product change.
6. Keep scope minimal.
7. Explain architectural impact when material.

Do not ask Ömər to select routine libraries, patterns, or low-level
implementation details. Use the simplest reversible option and mark it
[Provisional].

## Approval Boundaries

Before a major architecture change, the agent must:

1. state the problem;
2. present realistic alternatives;
3. explain advantages, disadvantages, risks, and reversibility;
4. recommend one option;
5. wait for Ömər's approval;
6. implement only after approval.

Major changes include:

- durable storage format or migration;
- provider contract;
- runtime/concurrency model;
- data ownership or privacy exposure;
- autonomy or external side effects;
- Nel identity formation rules;
- irreversible deletion;
- public or multi-user product direction.

Small bug fixes and reversible details that preserve approved architecture may
be implemented directly when requested.

## Protected Data and Secrets

AI agents must not:

- edit `.env`;
- print, log, expose, hardcode, or commit credentials;
- include secrets in prompts unnecessarily;
- modify real memory during tests;
- use production memory as a test fixture;
- commit private runtime data;
- disclose memory values in reports unless Ömər explicitly requests them.

Tests must use temporary isolated files or in-memory fakes.

## Scope Rules

AI agents must not:

- perform unrelated refactors;
- redesign architecture silently;
- add unrequested features;
- create domain-specific demo logic;
- convert placeholder files into speculative systems;
- treat generated output as stored truth;
- mix user facts with Nel-owned state;
- introduce a vector database, framework, language, or service without
  demonstrated need;
- begin interface work before core reliability unless Ömər explicitly changes
  the roadmap.

Work with dirty files rather than reverting them. Never discard user changes
without explicit authorization.

## Implementation Standard

- Prefer existing project patterns until an approved decision replaces them.
- Keep provider, persistence, identity, memory, and runtime boundaries clear.
- Preserve literal user values when extracting facts.
- Validate structured model output locally.
- Make failures visible without exposing secrets.
- Avoid broad exception handling that silently converts failure into success.
- Preserve historical data during migrations and conflict resolution.
- Keep technical explanations understandable to a non-programmer.

## Testing Standard

An agent must run tests proportional to the risk of the change.

At minimum:

- a bug fix receives a focused regression test;
- persistence changes receive isolated migration, interruption, and rollback
  tests;
- provider changes receive mocked contract tests and a bounded live smoke test
  when configured and safe;
- runtime changes receive startup, shutdown, cancellation, overlap, and
  exception tests;
- identity or memory changes test namespace separation and hallucination
  boundaries.

An agent must never claim a test passed without running it. Report timeouts,
skips, nondeterminism, and environmental failures separately from passing
tests.

Live tests must not write real memory unless Ömər explicitly authorizes that
specific write.

## Documentation and Decisions

Update documentation when behavior, structure, constraints, or roadmap state
changes materially.

- Do not silently rewrite accepted historical decisions.
- Add a new ADR that supersedes an old record.
- Mark technical assumptions [Provisional].
- Keep `06_CURRENT_STATE.md` factual.
- Do not describe planned capabilities as implemented.
- Reconcile old documents explicitly rather than deleting contradictory
  history during unrelated work.

## Git and External Actions

AI agents must not:

- commit or push without explicit authorization;
- create a pull request without authorization;
- rewrite history;
- run destructive Git or filesystem commands unless explicitly requested and
  verified;
- send messages, publish content, spend money, install arbitrary software, or
  control external accounts on Ömər's behalf without approval.

Dependency installation needed for an approved implementation is allowed only
when scoped, reported, and free of unrelated packages.

## Required Implementation Report

Every implementation report must include:

1. changed files;
2. reason for each change;
3. tests run;
4. exact results;
5. errors or skipped checks;
6. remaining risks;
7. uncommitted/commit status.

If real memory was intentionally changed, report that fact without exposing
private values unless requested.

## Uncertainty

When product intent is genuinely unresolved and alternatives materially
change Nel, stop and ask Ömər.

When only a technical detail is missing:

- choose the simplest reversible implementation;
- state the assumption;
- mark it [Provisional];
- avoid expanding scope.

Neither confidence nor fluency is evidence. Repository state, tests, accepted
decisions, and observed behavior are evidence.

## Self-Modification

Nel and AI collaborators may not directly merge production self-modification.
The required sequence is:

`proposal -> isolated patch -> tests -> review -> explicit approval -> merge`

No component may bypass this sequence by labeling generated code as memory,
reflection, maintenance, or autonomy.
