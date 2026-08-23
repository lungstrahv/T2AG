# Progress nodes and the auto-archive flow (progress_tracking)

**Protection level**: core-playbook

> This process defines the course lifecycle, the capacity composition, fine-grained recovery
> points and coarse-grained completion nodes.
> `progress.md` owns only the Course lifecycle, the single foreground and the exact stopping
> point; `activity_ledger.md` owns the Lesson/Exercise lifecycle. A course group decides capacity
> only and overrides neither source of truth.

## 1. Two independent sets of state

### 1.0 The current learning activity

`progress.md` must keep the course lifecycle and the current learning activity apart:

```yaml
current_activity: lesson       # lesson / exercise
current_activity_id: lesson01  # lessonNN / exerciseNN
resume_path: main/40_course/COURSE_ID/lessons/lesson01/lesson01.md
activity_position: the exact stopping point
next_action_kind: resume
next_activity_type: lesson
next_activity_id: lesson01
```

- When switching to an Exercise, `resume_path` points at `exercises/exerciseNN/exercise.md`.
- The explicit foreground and the next_action fields must never be backfilled from memory, a directory scan, or the retired `current_lesson`. Historical Lesson context is resolved on demand from ledger events and ContentGroup relations only, and must never trigger a default Lesson/working-pages recovery.
- Lesson and Exercise are sibling activities; switching changes only the current recovery entry point, and never the ContentGroup relations, nor closes the other activity's open questions on its own.
- `activity_position` is the exact-stopping-point field shared by both activity kinds; `lesson_position` must not continue to hold an Exercise's or a new Lesson's state.
- A planned course writes only `progress_nodes_status: lazy_on_activation`, and carries no `current_activity / current_activity_id / resume_path / activity_position`. On activation, create the real carrier first, then write the complete activity fields atomically.

### 1.1 The course lifecycle

Every course uses this in the `progress.md` file header:

```yaml
lifecycle_status: planned  # planned / ongoing / paused / completed / dropped (paused added 2026-08-19: paused is not abandoned, and activity_position must record the stopping point and the resume condition; first case CS1953)
```

- `planned`: a plan or archive exists, but study has not actually begun.
- `ongoing`: the course has started and has not ended; it may stay ongoing even while outside the current capacity composition.
- `completed`: the course's completion criteria have closed.
- `dropped`: the user explicitly terminated it; the reason and history are kept.

### 1.2 The current capacity composition

The currently active `Gxx.md` is the focused execution composition the user confirmed: courses
inside it receive a time budget, a minimum frequency and milestone commitments.
An `ongoing` course outside the group may still be advanced ad hoc when the user explicitly asks,
but must never automatically crowd out the in-group budget, and one ad hoc session must never
switch groups automatically.
The system may propose group changes based on real durations, failed starts, learning capacity,
deadlines, dependencies and project constraints; a membership change still requires user
confirmation.

## 2. Two layers of progress node

### 2.1 checkpoint: the arrival node

A checkpoint is a fine-grained recovery point answering "which sentence, which proof step, or
which project action exactly did we reach".

- A textbook course scopes it to the current 5–8 page working window; one page may hold several checkpoints. The Scope specification's owner is `50_playbook/source_page_assets.md` §2 LessonScope, and this file does not redefine it.
- A project/practice course generates them from the fine steps of the current schedule, milestone or project order table.
- A checkpoint uses a source-locating ID, such as `MATH1607H-B001-P026-N02`.
- Checkpoints hang under a LessonMap block: one block may hold several (a student may stop more than once inside one block). A block reference uses the stable ID `page_key#block_id`; the same textbook block of the same SourcePageAsset keeps the same ID across Scope versions.
- On reaching a checkpoint, save silently and automatically; the student is not required to say "save progress".
- The status distinguishes at least `queued / arrived / pending / confirmed / archived`.
- A checkpoint proves the position reached and the confirmation state only; it does not equal completing a textbook subsection or a project node.
- The checkpoint table is the authoritative source of truth; the frontmatter `current_checkpoint` / `checkpoint_state` are generated from the table by `t2ag_state_refresh.py --write` (a GENERATED projection), and writing them by hand has no effect.

### 2.2 completion node: the completion node

A completion node is a coarse-grained, permanently stable unit of formal progress, usually
spanning several checkpoints or several pages.

- A textbook course usually maps it to one subsection of the textbook contents, a complete theorem chain, or another natural content boundary.
- A `course_type: project` course maps it to a stable step or milestone in the project plan (the axis definition is in `00_core/domain_model.md` §2.0).
- A practice course maps it to an action/review unit in the schedule.
- Once generated, an ID must never be reordered or reused; the title, page number or description may be revised.
- The status uses `queued / in_progress / completed / superseded`.
- Temporary supplementary content hangs under its parent completion node and must never change the main sequence on its own.

## 3. Generation and the rolling window

1. Completion nodes are generated first from the verified textbook contents, the project order table or the practice schedule; never guess the structure from model memory.
2. A textbook course generates checkpoints only for the current Scope (5–8 pages). When the Scope version changes:
   (1) the current LessonMap block membership derives the routing, and "leaving a block" is decided by the difference between the old and new Map block ID sets;
   (2) a `confirmed` checkpoint stays `confirmed`; a Scope version change never rewrites an established confirmation;
   (3) if a block about to leave Scope still has a `queued / arrived / pending` checkpoint -> fail-closed: it must first be closed by confirmation, or explicitly deferred/retired by the student;
   (4) `archived` means only that the checkpoint itself was explicitly judged duplicate, void, superseded or no longer recoverable, and the retirement reason must leave a trace in the corresponding Lesson/activity record; `archived` is no longer an automatic clean-out mechanism for a Scope rollover.

### Re-blocking and block migration

A textbook's block division is not static. The same SourcePageAsset may be re-blocked in a later
Scope version (a definition and its example split into different blocks; a textbook revision
moving a block boundary). A block ID change must be recorded explicitly through a **block
migration table**; silently overwriting an old ID, or inventing a new one with no correspondence
established, is forbidden.

The block migration table records at least:

| Field | Meaning |
|---|---|
| page_key | the unchanging page-level ID |
| old_block_id | the old block's short ID (such as B02) |
| new_block_id | the new block's short ID (such as B03) |
| kind | `split / merge / renumber / boundary_shift / retired / new` |
| successor_of | whether the old block is fully contained or superseded; a one-to-many or many-to-one relation must be explained |
| decision | the adjudication the student or teacher confirmed (such as "B03 supersedes B02; the old B03 becomes B04") |

Rules:

- Within one Scope version change, when a one-to-many successor mapping exists under the same `page_key` **with no exact successor determination, doctor must fail closed** (CKP-SCOPE-003), requiring the teacher to state the successor explicitly in the migration table.
- A `kind: retired` block: the old checkpoint may be marked `archived`, with the retirement reason recorded in the corresponding Lesson.
- A `kind: new` block: content that never appeared in any confirmed completion node inherits no old checkpoint.

3. An inactive course keeps only the minimal lifecycle fields, and generates nodes lazily on first activation or genuine recovery.
4. A `node_id` is bound to the source identity; a file rename is resolved through the artifact registry, and node IDs are never re-created.

## 3.5 Learning-day attribution (the 04:00 boundary)

> **This section is the canonical landing point of item 14 in the memory decision section
> (provisional, 2026-07-31).**
> The rule has been governing behaviour since 2026-07-31, yet as late as 2026-08-07 a whole-repo
> `grep -rln "04:00\|凌晨" main/50_playbook/ main/00_core/ main/t2ag.md` returned **zero hits**
> — it lived only in memory with no normative carrier, and was therefore blocked by a tombstone
> from sinking. The migration registration is in the `rule_migration` at the end of §6.

**The rule**: **task progress produced before 04:00 local belongs to the previous learning day.**

Example: progress actually saved at 01:00 on 2026-08-01 is attributed to 2026-07-31, and closes
as that learning day's last task.

**The scope split (this half matters as much as the rule itself and must never be omitted)**:

| Object | Which date |
|---|---|
| **learning progress** (checkpoints, completion nodes, progress records, the learning-day wrap-up) | the **04:00 learning day** |
| **system logs, monthly journals, release forensics** (changelog, journal, release evidence, the doctor monthly gate) | the **calendar date** |

Extending the 04:00 boundary onto the forensic chain is **wrong** — two date concepts sharing one
name is exactly where the `P-0045` conflict came from.

**Cross-month attribution: record both, marked explicitly (`P-0045` adjudication, student, 2026-08-07)**

When a record's **learning day differs from its calendar date** (that is, it was produced between
00:00 and 04:00 local), **both dates must be written**; writing only one is not permitted:

```
learning day 2026-07-31 (calendar 2026-08-01 01:12)
```

When the two agree, write one — **no noise is manufactured for records that do not straddle the
boundary**; the double entry appears only where the fork is real.

**Any consumer doing weekly/monthly aggregation must declare in its own document which calendar it
uses.** An undeclared consumer is a missing contract, and the reader must never be left to guess.

> **Why both rather than "pick one"**: the student's reason is **lowering the long-run cost for
> every model**. With only one date recorded, every model that takes over has to re-derive "which
> calendar applies here" on encountering a straddling record; the double entry pays that
> derivation once and writes it into the record. This is not error prevention but **prevention of
> repeated derivation** — the same orientation as this file's other rules, "make the truth
> directly readable rather than repeatedly recomputed".
>
> The price is one extra parenthesis on a straddling record. That happens at most about once a
> month (a study session that happens to wrap up between 00:00 and 04:00), so the cost is
> negligible.

**This does not change the scope split**: the table above still holds — the **attribution** of
learning progress follows the 04:00 learning day, and the **attribution** of system logs /
monthly journals / forensics follows the calendar date. The double entry settles "what is written
on the record", not "which attribution applies". The two must never be conflated.

## 4. Saving and formal promotion entry points

### 4.1 Automatic checkpoint

On entering a checkpoint, immediately update the current checkpoint, the exact stopping point and
the confirmation status in `progress.md`, and refresh the machine-generated caches. This saves the
position only and must never write the parent completion node as completed.

### 4.2 Automatic completion node

Once a completion node's existing completion evidence is satisfied, mark that node completed
automatically and mark the next node in_progress.

- Textbook course: the content is taught, with no dangling confirmation and no unanswered question; no extra exercises are forced. Extra exercises are not auto-generated by default and are created only after the student requests them or explicitly opts in; a classroom comprehension check is not an extra exercise.
- The textbook's own worked examples and exercises: the exercise closure loop still runs, but it is not an additional exam attached to every completion node.
- A `course_type: project` course: closed by code that runs, a file produced, or a functional result already in the plan — and that result must be judged by an **external source of truth** (`project_verification.md` §0, the three mechanisms), not confirmed by the teacher alone. Bound to `course_type`, not to `default_driver`.
- Practice course: closed by an action record or a review result already in the plan.
- Mistake retests, chapter sets and aged sets stay independent and are never bundled to each completion node.

### 4.3 The student's manual "save progress"

When the student says "save progress", force-save the current checkpoint, the pending status and
the classroom key points immediately, whether or not a node boundary was reached. A manual save
never completes the parent node automatically and never substitutes for the closing ritual.

### 4.4 Session close and recovery confirmation

An ordinary close completes the formal write-back per `session_close.md`. When recovering after an
abnormal interruption, if the current Lesson/Exercise, a cloud event or the student's statement is
newer than the source of truth, pause new content and verify first; update `progress.md` once the
student confirms, then refresh the caches together.

## 5. Cloud checkpoints

- A mobile checkpoint is recorded silently inside the cloud.
- On each completed completion node, the cloud automatically produces a compact `T2AG_PROGRESS_RECEIPT`.
- When the student says "save progress", a receipt is produced immediately; an ordinary close still produces a complete `T2AG_SESSION_CLOSE`.
- Local deduplicates by event ID; a receipt already contained in a later close block is not counted twice.
- The cloud must never write the local `progress.md` as synced directly; a receipt stays pending until verified locally.

## 6. Machine-generated caches

`70_tools/t2ag_state_refresh.py` owns only these local GENERATED blocks:

- memory's `ACTIVE_PROGRESS` and `STATE_POINTERS`;
- `learning_path.md`'s `COURSE_INDEX` and `GROUP_INDEX`;
- the active group plan's `GROUP_VIEW`.

A Lesson's or Exercise's local stopping point is written as activity evidence by
`session_close.md`; it is not a GENERATED cache and must never override progress. The mobile entry
point is owned separately by the Cloud sync protocol and is not written while the bridge is
`paused`. Any GENERATED anchor with no generator explicitly responsible for it is a contract
error.

The execution order is fixed at:

```text
progress.md / the active group file
  -> t2ag_state_refresh.py --write
  -> t2ag_state_refresh.py --check
  -> t2ag_doctor.py --profile runtime
```

When a tool fails, a hand-copied result must never pose as a successful generation.

---

## rule_migration

Registered per `main/t2ag.md` §6.3.1 for the rule migration this file receives.

| rule_id | old location / text anchor | action | new owner / equivalence gate | consumers | verification |
|---|---|---|---|---|---|
| the 04:00 learning-day boundary | `grep -n "04:00" main/00_core/t2ag_memory.md` -> decision-section item 14 (provisional, 2026-07-31), **no playbook carrier** | **sink** | this file §3.5 | the session close flow (the `session_close.md` §4 pointer), progress writers, monthly forensics consumers (which follow the calendar date per the scope split) | `grep -rln "04:00" main/50_playbook/` hits this file; the `⚠` tombstone on memory #14 may be removed and sunk |

**Sink closure check (the four items of §6.3.3)**: new canonical owner = this file §3.5 [x];
entry pointer = `session_close.md` §4 [x]; consumers = column five above [x];
verification = the grep in column six [x].

**`P-0045` was adjudicated and landed with this migration** (student, 2026-08-07; option C:
record both, marked explicitly). The rule is in the last part of §3.5. That entry's problemlog
record may be turned to resolved on this basis — this file does not change the problemlog status
on its behalf; the maintainer does so per `problemlog_maintenance.md`.
