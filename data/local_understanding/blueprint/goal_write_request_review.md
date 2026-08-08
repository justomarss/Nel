# GOAL_WRITE_REQUEST Review

Initial candidates: 12. Final clean families: 6. Add/create was merged into establishment; change/replace/correct into revision; pause/resume/reactivate into activation lifecycle; complete/cancel/retire into terminal lifecycle. Rename and reprioritize share metadata semantics but are low-weight because current command support may be incomplete.

Thirty examples and eighteen hard negatives are retained. Challenge-only: `Onu dəyiş.`, `Sil bunu.`, `Dayandır.`, `Yenilə.`, and any pronoun-only command without explicit goal ownership. The label recognizes intent only and never supplies action, target, identifier, confirmation, or execution.

Highest risk: GWR-02 replacement target resolution, GWR-03 generic pause language, GWR-04 completion-versus-cancellation, GWR-05 unsupported metadata operations, and GWR-06 assertion-versus-conversion. Future deterministic parsing needs action and goal-target slots; classifier output cannot supply them safely.

Language review: `təqaüdə çıxar` is metaphorical and lower-weight; use only after native review. `pauzaya al` is conversational. Ready to freeze provisionally: yes, with GWR-05 lower weight and all lifecycle families subject to strict rejection when ownership is not explicit.
