# The T2AG in-course learning activity model

**Protection level**: core-contract

> This contract is the structural authority for Lesson and Exercise, and must ship with Main, Skeleton, and Lite alike.
> A playbook may only explain how to run these objects; it can never replace the objects, the templates, or the initialization capability.

## 1. Two sibling learning spaces inside a course

```text
Course
├── lessons/                 # teaching, reading, examples, questions and confirmations
│   └── lessonNN/
│       ├── lessonNN.md      # the Lesson main carrier
│       └── lesson_thoughts.md (created lazily when a real thought appears)
└── exercises/               # the student's ongoing solving, submission, feedback, correction and retest
    ├── exercise_thoughts.md (a course-level index, created lazily when a real thought appears)
    └── exerciseNN/
        ├── exercise.md      # the Exercise main carrier and the exact stop
        ├── problems.md      # the stable problems and this unit's order
        ├── attempts/        # the student's original submissions
        └── reviews/         # per-round feedback
└── activity_ledger.md       # 0.2.2+ the sole source of truth for the Activity lifecycle
└── activity_map.md          # ContentGroup ↔ Lesson/Exercise structure (as needed)
```

- Lesson and Exercise are near-sibling LearningActivities inside a Course; neither owns the other.
- An Exercise is not a Lesson's subordinate Session; the canonical directory/ID is `exerciseNN` (at least two digits).
  The old `Udddd` serves only as a legacy alias and **creating new ones is forbidden**.
- A ContentGroup links the two kinds of activity by the knowledge content of the source material. The course-root `activity_map.md` governs the links but does not change their sibling relation. A legal `binding_status: unbound` requires empty `content_group_ids` + a non-empty reason.
- **Separation of powers (0.2.2)**:
  - `activity_ledger.md`: `truth_scope: activity_lifecycle` (ALE/CLR/alias/stats/course preference overrides)
  - `progress.md`: `truth_scope: course_lifecycle,course_frontend,activity_position`
  - The activity's main file drops the hand-written `status`; the Activity lifecycle must never be written back into progress or the main file again.
- `progress.md` uses the single foreground `current_activity` / `current_activity_id` / `resume_path` /
  `activity_position` plus the structured `next_action_kind|type|id`. `current_lesson` is **retired** from the
  active contract. There is one foreground for the whole course; the `ongoing+pending_close` capacity is Lesson ≤3, Exercise ≤2.
- A consumer must build an immutable `ProgressSnapshot` from one single read of progress; the unified activity route returns
  `activity_position`. Never fill in routing fields with a second read — that produces cross-version state under concurrent teaching write-back.
- An Exercise must not declare `lesson_id(s)` or a Session ownership field, and must not restore the rejected
  `sessions/ExerciseSession` object.
- The proofread problem source of a textbook-driven Exercise belongs to the Course/ContentGroup and must live in the persistent
  `book/` domain, referenced explicitly by `problems.md` through a registry artifact, path, locator and SHA.
  Once resolved, the path must still lie inside this Course's `book/` and must not pass through a symlink, junction, or reparse point;
  problems, the registry, the problem source's frontmatter, and the original document's path/SHA must form one identity chain.
  The `working_pages/` path was retired in 0.2.2 batch S3; historical excerpts are in each course's `archive/`.

### 1.1 The state and default-routing matrix

| State | Explicit activity fields | Lesson context | Default recovery/close main carrier | working pages |
|---|---|---|---|---|
| `planned` | absent | `none` | cannot be recovered or closed | skipped |
| ongoing + Lesson | complete and mutually consistent | the current Lesson | the current Lesson | validated for a textbook Lesson only |
| ongoing + Exercise-first | complete and mutually consistent | `none` / `—` | the current Exercise | skipped |
| ongoing + Exercise + a historical Lesson | complete and mutually consistent | the real historical Lesson | the current Exercise; the historical Lesson is read-only by default and is not written | skipped |

Activity routing is parsed mechanically by the read-only `70_tools/t2ag_activity.py`. Recovery, session close, state refresh and Doctor
must all consume the same explicit activity contract; none of them may implement its own fallback rule for "guessing the current carrier".

## 2. The shared learning loop

Lesson and Exercise both run the same skeleton:

1. Recover the current activity and the exact stop from `progress.md`.
2. Read the source material, recent questions, mistakes and saved thoughts of the ContentGroup that activity belongs to.
3. Advance one confirmable step at a time.
4. Preserve what the student really expressed; the teacher's normalization and judgement are attributed separately.
5. A question goes into the question bank; a definite mistake goes into the mistake bank.
6. Update the current activity's main carrier and `progress.md`, then refresh the GENERATED state.
7. Continue once the student confirms; an unclosed question must never be buried by switching activities.

A Lesson's main evidence is the teaching record, the questions and the confirmations; an Exercise's main evidence is
ExerciseProblem → Attempt → Review → correction/retest. The form of the evidence differs; that both are
LearningActivities does not.

### 2.1 The optional student hint gate

`exercise_hint_gate: enabled | disabled` in `10_student/profile/profile.md` is the single persistent setting for whether
the student enables the executable hint gate. An uninitialized Skeleton uses `ask`, and first startup must let the student
choose before it may become `initialized`; the student may re-choose at any time afterwards, and re-choosing never erases existing help exposure.

The gate governs Exercise teaching replies only, and does not claim that a prompt alone forms an unbypassable safety boundary:

- `reasoning_feedback`: examines only the propositions, objects and reasoning the student has already written; it adds no solving object, sub-goal,
  lemma, construction, or next step;
- `concept_answer`: answers only the concept the student raised explicitly, does not bridge the concept back to the current problem, and generates no
  problem-specific sub-goal, lemma or key step; after answering it returns to the exact stop from before the question;
- `direction_hint / specified_reference / full_solution`: each requires the student's explicit authorization of
  `direction / reference / solution`; the teacher must never upgrade on its own because the student "seems stuck";
- a new Attempt stores the gate snapshot at creation and the highest help exposure; a concept Q&A does not itself raise the help level, and when a key
  structure leaks without authorization it is marked as teacher-hint contamination and counts neither as the student's independent mastery nor as a student mistake.

The pre-reply check is given by the read-only `70_tools/t2ag_hint_gate.py` as allow/deny plus a scope constraint. If the product layer needs a
hard block, a response intermediary outside the model must consume the deny return code; Doctor and the Markdown contract can only verify,
audit and prevent regression — they cannot honestly claim to intercept every future model output.

### 2.2 Map-first protocol for long multi-block explanations

When one explanation is expected to contain three or more concept blocks, or when a symbol will move across several object
levels (numbers, functions, sets, sets of functions), give the navigation first and enter the derivation second:

1. Use a short table of contents or a tree diagram to state the goal, the main branches, the dependencies, and the one branch being expanded this round.
2. Annotate a key symbol's object type at its first appearance; when one symbol family is used across levels, give a short type table.
3. Go deep into one branch at a time; after finishing that branch, wait for the student to confirm, restate or ask, then enter the next.
4. An overview carries navigation only; it must never compress all the detail into another form and dump it at once.
5. In conceptual teaching, or once the student has authorized a full explanation, the overview may show the proof or implementation route; the
   unauthorized stage of a new Exercise is still bound by zero hints at problem opening and by the hint gate, and must never leak the method,
   a sub-goal, a key transformation, or the answer through a table of contents, a thought tree, or a type table. When no useful overview can be made without leaking, omit the overview.

A map is not a comprehension confirmation. The student must still state understanding of, or agreement to continue with, the current branch; the system may not
cross a confirmation gate merely because the global structure has been shown.

### 2.3 Message-record routing

This section is the **sole owner** of message-record routing. For every message the student sends, the teacher judges its components in the order below and
writes them to disk **in the same round**; one message may hit several rows, and each row is written independently. A record is an append, not a judgement.

Lesson and Exercise share one judgement skeleton, but "which rows change the course's source of truth" differs, so there are two variant tables;
templates and instance carriers keep only a pointer to this section and must never copy the table body (two bodies would drift).

#### The Lesson variant

Only row 1 changes the course's source of truth, and it is written only once the comprehension gate has really closed; rows 2–6 need no authorization and do not wait for the end of class.

| # | Message component | Destination | Note |
|---|---|---|---|
| 1 | the answer to a comprehension confirmation | `progress.md` | correct → flip the checkpoint to confirmed + update the exact stop + one teaching-record line (with the key points of the correct answer); wrong → do not flip the checkpoint |
| 2 | the student's own formulation (an insight, a self-made model, a newly grasped concept) | `lesson_thoughts.md` | the student's words and the teacher's response in separate columns, never blended; promote to `10_student/profile/reasoning_patterns.md` only when it has cross-course value |
| 3 | a question | `question_bank.md` | answered on the spot → answered; deferred → open + a note |
| 4 | a knowledge error | `mistake_bank.md` | root-cause tag + transfer warning; if judged a regression, hang a re-check item in `progress.md` |
| 5 | how the study felt (aesthetics, sticking points, state, metacognition) | the verbatim classroom words go to `lesson_thoughts.md`; on reaching the distillation gate, promote to `10_student/profile/course_reflections.md`; philosophy/life/long-term emotion go to the individual-character section of `10_student/profile/profile.md` | the distillation gate is in §3 of this contract; a bare "no problems" is merged into that round's closing record and not listed separately |
| 6 | a process/system problem or suggestion | course level → the `progress.md` teaching record; system level → `t2ag_problemlog.md` | |
| 7 | a continue authorization | the `progress.md` exact stop | single-use; spent once consumed |
| 8 | small talk / off-topic | not recorded | — |

Not stored separately: the teacher's explanation body (the source text is in the source assets, and block coverage state is in the lesson main carrier and
`lesson_map.md`); the comprehension-check question text (it is in the checkpoint table).

#### The Exercise variant

Only rows 1–2 change the course's source of truth, and they are written only after the Exercise state machine has really produced them; rows 3–7 need no authorization and
do not wait for the end of class.

| # | Message component | Destination | Note |
|---|---|---|---|
| 1 | a formal answer | `attempts/ATdddd/attempt.md` + the exercise main carrier's state and exact stop | one answer, one numbered Attempt; when it is written is fixed by the structure |
| 2 | the teacher's feedback and verdict after the answer | `reviews/RVdddd.md` | one-to-one with the Attempt |
| 3 | the student's own formulation (an insight, a self-made model, a newly grasped concept) | the verbatim words stay in the Attempt + an index entry in `exercises/exercise_thoughts.md` | the student's words and the teacher's response in separate columns; promote to `10_student/profile/reasoning_patterns.md` only when it has cross-course value |
| 4 | a question / a conceptual question | `question_bank.md`; anything touching the current Exercise goes through the hint gate | answered on the spot → answered; deferred → open + a note; the hint level is recorded in the Attempt frontmatter per the authorization |
| 5 | a knowledge error | `mistake_bank.md` | root-cause tag + transfer warning; enters the retest cycle |
| 6 | how the study felt (aesthetics, sticking points, state, metacognition) | the verbatim words go to the Attempt / `exercise_thoughts.md`; on reaching the distillation gate, promote to `10_student/profile/course_reflections.md`; philosophy/life/long-term emotion go to the individual-character section of `10_student/profile/profile.md` | the distillation gate is in §3 of this contract; a bare "no problems" is merged into that round's closing record and not listed separately |
| 7 | a process/system problem or suggestion | course level → the `progress.md` teaching record; system level → `t2ag_problemlog.md` | |
| 8 | a continue authorization | the exercise main carrier's exact stop | single-use; spent once consumed |
| 9 | small talk / off-topic | not recorded | — |

Not stored separately: the teacher's explanation and hint bodies (the problem statement is in `problems.md`, and the evidence pointers are in the exercise main carrier's
"evidence index").

### 2.4 The gate ledger (leaving a trace when a teaching gate is crossed)

> Origin: P-0054 "announcing is not handing over", plus three failures of the same gate (P-0014/P-0041/P-0054). A conversation-layer gate
> used to live only in prose, and skipping it left no trace; this section turns **crossing a gate** into **writing a row**, so that doctor
> (`runtime.gate_ledger`, WARN level) can reach a teaching gate for the first time. The GL-1 work order:
> `docs/design/T2AG_GATE_LEDGER_WORKORDER_DRAFT_2026-08-08.md`.

**The boundary (what it is not, stated first)**: the gate ledger is a **trace projection, not a second source of truth**. The truth of the block/activity lifecycle
still belongs to the `progress.md` checkpoint table and `activity_ledger.md` (the §1.2 separation is unchanged); when the ledger and a source of truth
conflict, the source of truth governs, and a missing ledger row = a trace violation, not = a state error. Its relation to §2.3 rows 7/8
(continue authorization → the exact stop, single-use and spent once consumed): the stop records the **current authorization state**, the ledger records **historical rows**.

**Carrier and anchor**: the Lesson / Exercise main carrier each holds one `## Gate ledger` section, whose first row is the anchor:

```
ledger_since: <ISO date> | starting block: <checkpoint ID>        (Lesson)
ledger_since: <ISO date> | starting evidence: RVdddd/ATdddd       (Exercise)
```

The anchor joins on an ID, not on a date (the checkpoint table has no date column); doctor takes effect only on confirmed rows / new evidence **after** the
anchor — **forward-acting; history is never backfilled and never checked**.

**Row format** (seven columns, append-only; a historical row is never edited — a wrong row is corrected by appending a correction row pointing at the corrected row's ID):

```
| Row ID | Block ID | Gate type | Basis of closure | Response to feeling | Verbatim authorization | Consumed at |
```

- `Row ID`: `GT-NNNN`, increasing monotonically within a carrier, never numbered across carriers.
- `Verbatim authorization`: **the student's exact quote + the moment** (such as `"continue"(21:14)`). A trace does not prevent fabrication; what it prevents is
  delayed discovery: together with the classroom footer, a forged quote is a lie told to someone's face in that round, while lazily omitting the row is a missing row anyone can find at the file layer.
- A bare "no problems" response is merged into that round's row per the existing §2.3 convention, not listed separately.

**The obligation to write a row (the gate-type enumeration)**:

| Variant | Gate type | When the row is written | What `Consumed at` holds |
|---|---|---|---|
| Lesson | `opening confirmation` | after the overview + knowledge tree + route feeling, the student authorizes entering the first block | the first block's checkpoint ID |
| Lesson | `block transition` | the three §1.6 gates close and the student authorizes entering the next block | the next block's checkpoint ID |
| Lesson | `page turn` | the old page's list → announce "PDF N / book page M" → the new page tree → a separate authorization | the first block ID of the new page (the `Block ID` column holds `PDF N→N+1`) |
| Lesson | `close confirmation` | the student confirms at session close | `close` |
| Exercise | `problem opening` | only the statement is given and the independent attempt is preserved | the problem number (such as `Q005`) |
| Exercise | `hint authorization(level)` | the student explicitly authorizes a hint level (§2.1) | the matching `ATdddd`; `Basis of closure` holds the student's verbatim request |
| Exercise | `problem closure` | the feeling and question gates close after the explanation/review | the matching `RVdddd` |
| Exercise | `next-problem authorization` | the student authorizes moving to the next problem | the next problem number |
| Exercise | `close confirmation` | as for Lesson | `close` |

**The classroom footer (a derivation rule)**: every teaching reply ends with one fixed line whose content must be derivable from the ledger's last row +
the progress stop, and may never be asserted out of nothing:

```
⛩ Block: <current block> | Gate: <which gate is open / what is being waited for> | This round's authorization: <unconsumed / consumed at X> | Page: PDF N / book M
```

The Exercise variant: `Block`→`Problem`, `Page`→`Hints: the level authorized so far`. The student may change the leading symbol and the field order;
changing the style is a V0.

**The scope of the doctor check (stated honestly)**: `runtime.gate_ledger` implements a deterministic subset only —
`000` the table is corrupt, fail-closed; `001` a block transition row is missing between adjacent confirmed blocks after the anchor; `002` a
page-turn row is missing where the page number changed; `003` the verbatim authorization is empty or a placeholder; `004` a row ID repeats or does not increase;
`005` a problem-closure row is missing for a new RV after the anchor; `006` an Attempt frontmatter with a high hint level lacks the hint-authorization row;
`007` the current textbook Lesson lacks the whole `## Gate ledger` section. `opening confirmation` / `close confirmation` / `next-problem authorization`
are at present contract obligations only and are not machine-checked. Each WARN names the carrier and the block/problem ID.

Update 2026-08-10 (the student's adjudication, alongside the check-system construction):

- The semantics of `001` are **a trace on the way out + a trace on the way in**: crossing a→b is satisfied by "a has an outgoing block-transition row" plus "b has an incoming
  block-transition row", and passing through an off-tree or student-led branch node in between is allowed (a detour permitted by constitution §4 is no longer a false report).
- The checkpoint table accepts two deterministic shapes: a table whose header names `checkpoint_id`/the status column (the page column may be absent —
  a goal-driver course legitimately has no page) and the headerless legacy six-column `-B-P-N` shape.
- A **historical carrier** without this section → skipped (unchanged during the deployment transition); but the **current textbook Lesson**
  (the `current_activity` progress points at) missing the whole section → `007`, at **FAIL** level: when a prose gate loses its only machine landing point, closure must not be claimed.
  A missing row for completeness is still a WARN and does not interrupt a class.

## 3. The thought-compounding loop

It starts only when the student expresses a thought explicitly in some activity; content is never pre-created:

```text
the student's own words
  → Lesson: lesson_thoughts.md
    or Exercise: the Attempt + an index entry in exercises/exercise_thoughts.md
  → on meeting the distillation gate, into course_reflections.md
  → read actively when a related Lesson / Exercise is later recovered, and used for a hint, a counterexample, a transfer or a retest
  → the new answer and the new thought form the next round's evidence
```

- The student's words, the teacher's additions, and the teacher's distillation must be in separate columns and never blended.
- An ordinary local thought is not forced upward; distillation happens only when it links activities, when the student explicitly marks it important, or when it can guide later study.
- `course_reflections.md` is not a terminus; an entry must carry its source and its intended later use, and must actually be consumed on recovery.

## 4. The exercise-driven system improvement loop

A real Exercise serves learning and also supplies design evidence for the system's mechanisms:

```text
continuous solving
  → exposes a new need / friction / edge case
  → recorded in the problemlog or the candidate roadmap
  → separate the facts, the model's inference, and the need itself
  → adjudicate with the student
  → update the Core contract / Playbook / Tool / Template
  → synchronize the Skeleton
  → a negative example and a real next round verify it
```

- A one-off need is served by solving the current learning problem first; do not rush to abstract it into a system object.
- A stable mechanism must not live only in one course, one `Udddd`, or one conversation; it must enter the Core, the templates, and the executable checks the Skeleton ships with.
- The Skeleton carries no real student or course instance, but must carry the complete templates and rules needed to create a Course, a Lesson, an Exercise and their
  compounding loops.

## 5. Division of authority

| Content | Authoritative carrier |
|---|---|
| the Lesson / Exercise objects and the shared loop | `00_core/learning_activity_model.md` |
| message-record routing (the two variant tables, Lesson / Exercise) | `00_core/learning_activity_model.md` §2.3 |
| the gate-ledger trace and the classroom footer (the two variants, Lesson / Exercise) | `00_core/learning_activity_model.md` §2.4; the check is `runtime.gate_ledger` |
| a course's stable teaching constraints | `40_course/<COURSE_ID>/course.md` |
| ContentGroup and activity relations | `40_course/<COURSE_ID>/activity_map.md` |
| the current activity and the exact stop | `40_course/<COURSE_ID>/progress.md` |
| the Lesson body | `lessons/lessonNN/lessonNN.md` |
| the Exercise body | `exercises/exerciseNN/exercise.md` |
| the textbook problem source | a persistent verified excerpt inside the Course `book/`; never in a temporary cache path |
| problems, submissions and feedback | `problems.md` / `attempts/` / `reviews/` |
| initialization material | `40_course/_templates/course/` |
| the runtime steps | `50_playbook/new_course_init.md`, `lesson_recover.md`, `exercise_evidence.md`, `session_close.md` |
