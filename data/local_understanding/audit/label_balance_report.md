
## Counts

| Label | Reusable | Review required | Challenge only | Rejected/split | Target | Deficit after reusable+review |
|---|---:|---:|---:|---:|---:|---:|
| GOAL_LIST_QUERY | 10 | 1 | 0 | 0 | 800 | 789 |
| IDENTITY_QUERY | 2 | 0 | 0 | 0 | 800 | 798 |
| PERSONAL_FACT_QUERY | 8 | 0 | 0 | 0 | 800 | 792 |
| PERSONAL_PROFILE_QUERY | 7 | 0 | 0 | 0 | 800 | 793 |
| MEMORY_WRITE_REQUEST | 14 | 1 | 0 | 0 | 800 | 785 |
| GOAL_WRITE_REQUEST | 1 | 0 | 0 | 0 | 800 | 799 |
| PERSONAL_ASSERTION | 1 | 0 | 0 | 0 | 800 | 799 |
| GENERAL_CONVERSATION | 161 | 0 | 1 | 0 | 1600 | 1439 |

- Source-pool rows: 234
- Embedded hard-negative examples: 60
- Context scenarios: 15
- Total adjudicated records: 309
- Unresolved/no-label records: 102
- Context-only scenario records: 15
- Preserved hard-negative groups: 12; accepted as audit contrast material, not yet final evaluation groups.

## Decisions

- Personal-history questions remain challenge-only and receive no frozen label.
- Targetless generic change/delete requests are challenge-only.
- Capability questions are GENERAL_CONVERSATION except explicit identity questions.
- Natural-language writes are interpretation-only labels and have no write authority.
