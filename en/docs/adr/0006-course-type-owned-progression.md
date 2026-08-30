---
adr_id: ADR-0006
portable_key: course-type-owned-progression
status: accepted
authority_project: T2AG
source_evolution: [EV-0033]
supersedes: []
implementation_refs: [main/00_core/domain_model.md, main/50_playbook/book_management.md, main/50_playbook/progress_tracking.md, main/50_playbook/project_verification.md]
---

# ADR-0006: Course Type owns non-Mastery progression

T2AG no longer treats `course_type` and a four-value `course_driver` as fully orthogonal axes.
`course_type` still determines completion evidence; only a Mastery Course additionally selects
`textbook-led / goal-led / project-led` Learning Mode. A Project Course advances through the next
open Goal/Milestone in its Project Plan. A Praxis Course advances through real action, feedback,
reflection, and the next action. Neither carries an independent Learning Mode.

Legacy `default_driver/course_driver` fields remain readable during migration but are no longer
writable domain truth for Project/Praxis. Mastery project-led remains Mastery; a Project Goal is a
plan node, not goal-led mode.

## Consequences

- Initialization, recovery, Doctor, and templates validate the conditional field matrix.
- Project Plan reuses the existing `course.md` plus `progress.md` / `activity_ledger.md` owners;
  no second plan truth source is created.
- A Praxis Course is not incomplete merely because it has no driver; progression requires a real
  action entry point and behavioral evidence.
