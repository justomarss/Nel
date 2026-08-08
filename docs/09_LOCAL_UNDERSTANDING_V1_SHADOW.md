# Local Understanding v1 Shadow Status

Status: Diagnostics-only shadow infrastructure. Learned routing is not active.

## Frozen Taxonomy

The trained labels are `GOAL_LIST_QUERY`, `IDENTITY_QUERY`,
`PERSONAL_FACT_QUERY`, `PERSONAL_PROFILE_QUERY`, `MEMORY_WRITE_REQUEST`,
`GOAL_WRITE_REQUEST`, `PERSONAL_ASSERTION`, and `GENERAL_CONVERSATION`.
`UNKNOWN` is a rejection outcome, not a trained label.

## Baseline And Provenance

The repository-owned corpus, reviewed blueprint, splits, challenge sets, and
artifact live under `data/local_understanding/`. The baseline uses word TF-IDF
1-2 grams plus character TF-IDF 3-5 grams with `LinearSVC(C=0.7)`.
The persisted artifact records the feature configuration and class-specific
score thresholds. No production user data, provider calls, or Kimi material is
used by this pipeline.

## Current V9 Evaluation

V9 forced macro F1 is 0.954. Challenge false authority acceptance is 0.0%
across 12 cases. Held-out hard-negative forced accuracy is 1.000 across 16
cases. Noisy accepted accuracy is 0.867.

V9 accepted precision/recall is: GLQ 1.000/0.875, Identity 1.000/0.875,
PFQ 0.889/1.000, PPQ 1.000/1.000, MWR 0.889/1.000, Goal Write 1.000/0.875,
Personal Assertion 1.000/0.875, and General Conversation 1.000/0.875.

## Authority And Runtime Status

Explicit commands and the deterministic DecisionEngine always precede the
shadow prediction. The shadow object is optional constructor injection only.
Normal runtime neither imports nor loads the learned artifact. A shadow
prediction is ignored for route selection, command confirmation, command
execution, service writes, and user-visible responses. Shadow failures are
logged and do not interrupt ordinary conversation.

Learned routing is not authorized. PPQ coverage improved after targeted data,
but the shared LinearSVC boundary then regressed MWR and PFQ accepted precision
on the fresh V9 holdout. This small-corpus, shared-boundary sensitivity means
the artifact may remain diagnostics-only, not a routing authority.

## Deferred Work

Any future routing activation requires a fresh acceptance decision, broader
independent holdouts, stable authority-label precision, and separate response
claim validation. This artifact cannot write facts, memory, identity, or
goals and cannot resolve A-E expression or provider-claim failures by itself.
