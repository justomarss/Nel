# Nel Team

## Roles

### Ömər: Project Owner

Ömər owns the product vision and has final approval over major product and
architectural decisions. Ömər is not expected to design software
architecture, understand implementation details, or edit complex code.

Technical proposals must explain user-visible impact, risks, tradeoffs, and
reversibility in non-specialist language.

### Codex: Implementation Agent

Codex performs repository inspection, implementation, refactoring, testing,
and documentation directly when authorized. Codex must protect user changes,
keep scope minimal, report evidence, and follow `08_RULES_FOR_AI.md`.

Codex may make small implementation decisions that preserve approved
architecture. It must not independently approve major architecture.

### ChatGPT: Product and Architecture Reviewer

ChatGPT acts as an architectural critic, product-thinking partner, and
long-term consistency reviewer. It should identify contradictions, weak
assumptions, product drift, and risks.

ChatGPT does not automatically approve implementation and is not a source of
truth merely because it generated a recommendation.

## Shared Standard

Neither a human nor an AI participant is automatically correct. Claims
should be tested against repository evidence, product principles, and
observed behavior.

## Decision Authority

| Change | Owner | Approval |
|---|---|---|
| Product identity or constitutional principle | Ömər | Required before change |
| Major architecture or irreversible migration | Ömər | Required before implementation |
| External action or expanded autonomy | Ömər | Required before enablement |
| Small bug fix within approved architecture | Codex | May implement and report |
| Reversible implementation detail | Codex | May choose simplest option and mark provisional |
| Product/architecture critique | ChatGPT | Advisory |
| Commit or push | Ömər | Explicit authorization required |

## Major Decision Process

For a major architectural change:

1. State the problem.
2. Present realistic alternatives.
3. Explain advantages, disadvantages, risks, and reversibility.
4. Give a recommendation.
5. Wait for Ömər's approval.
6. Implement only after approval.

## Communication

- Explain outcomes before implementation mechanics.
- Separate accepted decisions from provisional technical choices.
- Ask Ömər only for decisions that materially change the product.
- Do not require Ömər to choose libraries, patterns, schemas, or runtime
  details unless the choice creates meaningful product consequences.
- Report changed files, reasons, tests, results, risks, and git status.

## Current Team Constraint

The project currently depends on one Project Owner and AI collaborators.
There is no separate security, QA, operations, or release owner.

[Provisional] Until human contributors are added, Codex performs
implementation and test execution, ChatGPT provides independent review, and
Ömər remains the approval gate for material decisions.
