# The T2AG 0.2.4 cross-session memory index

> The Skeleton's empty-instance cache. Never fill in a real student, course, or group before first run.

## Section budgets and sinking

This file is read at every startup. **The budget is a line count**, written as `[max N]` after each section
heading; doctor's `runtime.memory_budget` **reads that marker from this file** rather than hard-coding it — so
changing a budget is a one-line edit here, with no code change and no batch. What the gate guards is the
**mechanism**, not the number.

When the budget is exceeded, **sink the oldest entries** and leave one **tombstone** line in place naming where they went:

```markdown
- D-001 ~ D-011 sunk → `t2ag_changelog.md` [2026-07-26] ~ [2026-07-27] (sunk YYYY-MM-DD)
```

**Sinking is not deleting**: the entry body was always in the changelog / problemlog, and memory keeps only a pointer.
**Deleting a line must state where it went.**

The three sections below are empty template scaffolding: **the heading and the `[max N]` are reserved, and the
content grows naturally after first run.** Do not delete a marker just because its section is empty — deleting it
means the budget mechanism never takes effect on this instance.

## Last session summary

<!-- T2AG_GENERATED:ACTIVE_PROGRESS:START -->
- **Date**: —
- **Reached**: —
- **Current completion node**: `—`
- **Current checkpoint**: `—` (—)
- **Source**: local
- **First thing next time**: —
<!-- T2AG_GENERATED:ACTIVE_PROGRESS:END -->

- **Student state**: —

## Current state pointers

<!-- T2AG_GENERATED:STATE_POINTERS:START -->
| Item | Current value | Details location |
|---|---|---|
| Active course group | — | created after first run |
| Current course | — | created after first run |
| Lesson context | none | — |
| Current teaching activity | —: — | — |
| Current teacher | — | `main/20_teacher/overlay.md` |
| Student profile | uninitialized | `main/10_student/profile/profile.md` |
| active binding | none | created after first run |
| T2AG version | 0.2.4 | `main/t2ag.md` |
| Cloud bridge | paused | `cloud/cloud_sync_state.md` |
<!-- T2AG_GENERATED:STATE_POINTERS:END -->

## Checks before the next session  [max 30]

- — (filled in after first run)

## Recent key decisions  [max 100]

- — (filled in after first run; when over budget, sink the oldest entries per "Section budgets and sinking" and leave a tombstone)

## Recent problem summaries  [max 50]

- — (filled in after first run; the bodies live in `t2ag_problemlog.md` and this section keeps pointers only)

## Startup prompts

1. Read `main/10_student/profile/profile.md`.
2. When the profile is uninitialized or still contains required placeholders, run `main/50_playbook/first_run.md`.
3. Do not create, delete, rebuild, or upgrade a `.venv`.

## Current governance summary

- The default construction mode is `independent_batch`; `version_campaign` is enabled only under a user-approved,
  frozen, enumerated, expiring authorization envelope.
- A campaign covers only the RT1/RT2 units and the limited local checkpoints listed in the envelope; RT3 must be
  authorized separately, once the exact object and its body text are visible.
- Neither an evidence nor a recovery checkpoint is a release snapshot; a formal local version boundary may be named
  only after both the first candidate's full independent re-review and the bounded finalization delta re-review pass.
- The current version is 0.2.4 (development); Course progress and the activity ledger are now separated, and the Skeleton provides
  an empty ledger, exerciseNN, atomic lifecycle/close and recover capabilities, but carries no real migration or
  session-close instance.
- The 0.2.1 closing candidate supplied the reading ActivityRecord empty container, six JSON schemas, and the
  context/contribution/receipt saga in which each side writes its own repository; the Skeleton contains no real AR,
  book, sidecar, or receipt.
- EV-0012 general capability: the Course `source_assets` + `.cache/source_pages` + Lesson
  Map/Snapshot/pointer/Context contracts have landed; playbooks no longer treat `working_pages` as an authoritative
  output for new work. The Skeleton holds only the general contracts and empty templates, and carries no MATH1607H,
  student, or other instance data. See the changelog entry
  `[2026-08-05] EV-0012 教材页资产与 Lesson Preparation 技术收口`.
- P-0090 release-gate remediation: candidate binding uses a dedicated invited-manifest
  collector with resolved-absolute-path de-duplication; package-surface scanning is
  unchanged. See `[2026-08-24] P-0090 candidate-binding collection boundary remediation`.

<!-- The two T2AG_GENERATED blocks above are emitted verbatim by 70_tools/t2ag_state_refresh.py.
     Do not hand-edit them: `t2ag_state_refresh.py --check` compares them against what the tool
     would emit, so an edit here is drift. Change the tool, then run --write. -->
