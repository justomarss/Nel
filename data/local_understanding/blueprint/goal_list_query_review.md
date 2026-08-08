# GOAL_LIST_QUERY Review

Initial candidate families: 13. Final clean families: 10. `direct list`, `show`, and `indirect polite request` were merged into GLQ-02 because their distinction is only request surface. `colloquial standalone retrieval` was merged into GLQ-01/02 as a register variant. `progress status` was rejected: asking how far the user has progressed is not goal retrieval.

The ten retained families have 50 illustrative examples and 30 explicit hard negatives. Context-only challenge cases: `Bəs məqsədlər?`, `Bəs mənimki?`, `Onları göstər.`, `Bəs o?`; none is clean training material.

Boundary review: goal assertions remain the main confusion risk for GLQ-01, GLQ-04, GLQ-05, GLQ-06, GLQ-07, and GLQ-08. Goal write requests are closest to GLQ-02, GLQ-06, and GLQ-10. Philosophical/advice questions are closest to GLQ-04, GLQ-05, and GLQ-08. Assistant-goal questions and broad profile/history queries are forbidden.

Azerbaijani review removed task-like and unsupported-history wording. `öhdəlik` and `istiqamət` are lower-weight, standard-register constructions; they require later native review before source generation. GLQ-09 is limited to explicit goal nouns to avoid conflating goal retrieval with broad memory retrieval.

Ready to freeze provisionally: yes, subject to native-speaker review of GLQ-07 and GLQ-08.
