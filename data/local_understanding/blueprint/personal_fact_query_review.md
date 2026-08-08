# PERSONAL_FACT_QUERY Review

Initial candidates: 11. Final clean families: 7. Merged: comparative preference and negative-preference retrieval into PFQ-02; indirect requests into PFQ-01/02; uncertainty confirmation into PFQ-07. Rejected: broad profile questions, historical utterance recall, `Bəs Bleach?`/`Bəs GTA?`, targetless ellipses, and question-particle-omitted polar forms.

The seven retained families contain 35 examples and 21 hard negatives. PFQ-06 is current-fact recall only: `Yadındadır mən hansı dili öyrənirəm?` is eligible, while `Keçən dəfə hansı dili demişdim?` is unresolved history challenge material.

PFQ-07 uses only unambiguous explicit polar morphology and is low weight. Forms such as `Mən Bleach-i sevirəm?` must be challenge data because punctuation does not reliably distinguish assertion from question.

All families would benefit from future fact-key/slot extraction for precise answers. Current inventory-style runtime can classify the request safely but cannot guarantee a keyed answer; this is a known capability mismatch, not a classifier justification for slots.

Language review: `hobbiim` and some explicit polar suffix forms require native review before generation. `Mənim favoritimi bilirsən?` is conversational but should be checked for naturalness. Ready to freeze provisionally: yes, with PFQ-06 and PFQ-07 tracked as high-risk.
