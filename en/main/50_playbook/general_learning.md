# general_learning.md — the R binding rules (elastic execution binding)

**Protection level**: playbook

> R's formal name is "Elastic Binding".
> The old "general track / Reading track" survives only as an archival term and is not R's domain definition.

---

## Background

R (elastic execution binding) is the second kind of execution constraint, a peer of G (Group, the rigid
course group).
G and R differ in how rigid the execution constraint is; the success criterion belongs to course
progress, not to the G/R container.

> **The domain model (v0.2.0)**: the curriculum plan, the Student, G/R, and Course form a reference
> graph, not a strict parent-child tree. The full definition is in `00_core/domain_model.md`.

R shares t2ag's teaching discipline (textbook classification, the teacher red lines, memory pointers),
and does not share G's execution constraints (cycles, the frequency red line, the 4h budget, the
four-layer overlay, in-group freezing, the group-transition ritual, the written examination).

Directory: `main/30_group/<GID>/bindings/`. A binding belongs to a specific group,
but only references a Course; it never owns course content or progress.

---

## R's definition and boundary

- R may bind only Project or Praxis course progress
- Mastery may enter G only
- Casual reading, habit records, and exploration with no explicit acceptance go first into a classified
  ActivityRecord; ordinary reading must never be upgraded automatically into a
  Course, an Engagement, or an R binding, and must never become an R just because it "has no exam" or
  "is not a degree requirement"
- R has no course success criterion of its own; how it is accepted is decided by the type of course
  progress it binds

---

## The course types R permits

| Course type | Acceptance | Typical course |
|---|---|---|
| Project | bound to verification mode A/B/B-K | data science, an independent project |
| Praxis | real action + external feedback | trading discipline, habit formation |

**Mastery must never enter R** (it may enter G only).

---

## Lifecycle

R may be `idle / active / paused / closed`. Before activation, the course must be confirmed to exist,
its type must be Project or Praxis, the corresponding group must exist, and the student must confirm.
The migration-preserved
`R002_PHIL1101r` is the only legacy Reading evidence: it must keep both
`binding_status: idle` and `legacy_frozen: true`, and must never be activated, copied, or used as a
precedent for a new one.
It is not a legally activatable R. Apart from that exact frozen evidence, a Mastery binding is always
illegal;
and no other binding may declare `legacy_frozen` or borrow the registry's legacy category.

---

## R stores binding fields only

Once the full object-layer migration is complete, R will store only binding fields:

```yaml
type: binding
binding_id: RNNN
course_id: <COURSE_ID>
group_id: <GID>
binding_status: idle
execution_mode: flexible
```

R does not own the course plan, progress, acceptance records, lessons, or the mistake bank; those belong
to the Course it binds.

A real binding exists only in its owning group's `bindings/`; this general playbook does not enumerate
the current instance's
R numbers, courses, or groups. The rejected legacy Reading R semantics must never be reopened.

---

## Core rules

### Rule 1: it does not consume G's budget

R does not consume the active group's budget by default; if the user wants to allocate in-group time, it
must be written explicitly into that group's
`plan.md` and `calendar.md`.

### Rule 2: D4-compatible but with no KPI

R may use a KPI-free elastic slot explicitly marked in the group calendar, but it does not automatically
inherit any old overlay's D4 or 3-1-3 rhythm.

### Rule 3: several Rs in parallel

The number of active Rs is not capped, though no more than 2 at once is recommended.

### Rule 4: the ritual anchor

**A Project R**: the milestone is the ritual. Acceptance follows the bound verification mode (A/B/B-K).

**A Praxis R**: the action record is the ritual. Record action evidence and external feedback at a set
frequency, and review periodically.

### Rule 5: how it is accepted

**A Project R**: accepted by the bound mode. The verification-mode definitions are in
`50_playbook/project_verification.md`.

**A Praxis R**: accepted on action evidence.

### Rule 6: R never offsets the account

R may never be used as an explanation, a compensation, or a substitute for a week in which G fell short.

---

## Doctor interface

| Check | Level | Note |
|---|---|---|
| a binding references a non-existent course/group | **FAIL** | references must close |
| a Mastery course bound to R (the exact frozen R002 evidence excepted) | **FAIL** | Mastery may enter G only |
| a binding status outside the enumeration | **FAIL** | the status must be decidable |
| a legacy Reading binding that is not the existing frozen R002 | **FAIL** | keep the migration evidence only; do not restore the old model |

---

## Memory interface

The memory pointer is separate from the G pointer:

```
| active binding | none or `<RID>` | main/30_group/<GID>/bindings/ |
```

With no active R, the cache writes "none"; once one is activated, the state refresh generates the real
pointer.
