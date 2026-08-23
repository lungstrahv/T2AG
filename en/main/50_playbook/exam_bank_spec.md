# Problem-bank storage and pre-exam checks (exam_bank_spec)

**Protection level**: core-playbook

> **0.2.0 status: deferred design, not activated.** A cross-course examination system is explicitly out of scope for 0.2.0; this file preserves the existing design for a separate adjudication later. It is not in effect in the current directory/schema/doctor contracts, and `_exam/` must not be created on its basis.
>
> Companion to `main/50_playbook/exam_protocol.md`. This file specifies only problem-bank storage, the registration tables, problem-level metadata, and the mechanical pre-exam checks.

## 1. Directory structure

> The problem bank always lives at `main/40_course/<COURSE_ID>/_exam/`, inside the same course
> aggregate root as that course's `course.md` and `progress.md`.

```text
[course root]/_exam/
├ index.md
└ papers/
   ├ MIT_18100B_2019F/
   │   ├ paper.pdf
   │   ├ solution.pdf
   │   └ meta.md
   └ Fudan_MathAnalysis_2021S/
```

- `index.md` is the paper-level registration table and the sole source of truth for pool status.
- The pool, "used", and "sat" are all columns in the registration table; files are never moved — moving a file breaks references.
- The original paper PDF is kept as-is, problem statements are read through the source-cache rules, and transcribing or re-typesetting is forbidden.
- Acquisition channels: a public course page such as MIT OCW may be downloaded by the agent; a domestically circulating paper is obtained by the student and archived into the bank. With no network, the student downloads and the teacher registers.

## 2. The paper-level table in index.md

```markdown
| Paper ID | School | Year | Course level (honours/ordinary) | Total time | Problems | Per-problem baseline time | Solution (yes/no) | Pool | Status (in pool/sat) |
|---|---|---|---|---|---|---|---|---|---|
```

## 3. The problem-level table in meta.md

```markdown
| Problem no. | Type | Knowledge node (against the knowledge map) | Difficulty tier | Used in teaching | Sat | Solution page | Pre-exam check note (PASS/REJECT + reason) |
|---|---|---|---|---|---|---|---|
```

The problem-type enumeration:
- computation (limits / derivatives / integrals)
- proof
- construction
- true-false-and-correct
- concept statement

Difficulty tiers: L1 basic / L2 standard / L3 hardest. The tier is the median of three signals and is not changed once registered:
- the source course's level: an honours paper shifts the whole paper +1 tier
- position within the paper: the first third skews lower, the last third higher
- problem type: concept statement / computation skew lower, construction / multi-part proof skew higher

## 4. The pre-exam suitability check

For each candidate problem, output PASS / REJECT + a reason, recorded in the meta table's "pre-exam check note" column:

| # | Check | If it fails |
|---|---|---|
| 1 | the knowledge node is among those already taught | REJECT-out-of-scope |
| 2 | every upstream dependency of the node has been taught | REJECT-missing-dependency |
| 3 | `solution.pdf` exists and contains this problem | REJECT-no-solution |
| 4 | Chinese / English, or an official translation | REJECT-language |
| 5 | not marked "used / sat"; the statement is not a same-source adaptation of a problem already used | REJECT-already-seen |
| 6 | the sitting's ratios still hold once it is selected | redraw |

Drawing quiz problems: unused problems from the practice pool → check each → randomly draw 3 from the qualifying set on that day's seed.

Assembling the final paper: unused problems from the assessment pool → check each → draw randomly once the ratio constraints of `exam_protocol` §7 are satisfied.

## 5. Doctor checks proposed for a later version (not executed in 0.2.0)

| Check | Level |
|---|---|
| a problem-number reference from an assessment-pool paper appears in any lesson / practice file | FAIL |
| a paper folder exists under `papers/` but is not registered in `index.md` | WARN |
| `meta.md` is missing a column or a solution page number | WARN |
