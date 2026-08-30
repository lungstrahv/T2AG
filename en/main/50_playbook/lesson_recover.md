# Cross-session course context recovery

**Protection level**: core-playbook

> This file is one of T2AG's "solidified skill" documents.
> When a student says "continue with XXX" in a new conversation, follow this process to restore
> the previous teaching context: progress, textbook source text, and emotional state.
>
> **Applies to**: restoring the teaching context of a course in a new conversation.
>
> **Path resolution convention**: "the corresponding course" in this process always resolves to
> `main/40_course/<COURSE_ID>/`. Never guess a directory from an English title or a display name.
>
> **Related files**:
> - rule definition: `main/t2ag.md` -> "daily takeover"
> - course list: the GENERATED course index in `main/10_student/profile/learning_path.md`
> - course state: the corresponding course `progress.md` -> "current progress"
> - current activity: uniquely determined by progress's `current_activity / current_activity_id / resume_path`
> - Lesson notes: read `lessons/lessonXX/lessonXX.md` only when the current activity is a Lesson
> - Exercise evidence: read `exercises/exerciseNN/` only when the current activity is an Exercise
> - course questions: the corresponding course `question_bank.md` -> "open / needs review"
> - course mistake bank: the corresponding course `mistake_bank.md`
> - student state profile: `main/10_student/profile/profile.md`, `reasoning_patterns.md` and `course_reflections.md`
> - textbook cache: when the current activity is a Lesson, delivered via the preparation Snapshot + source_assets (the legacy `working_pages/` was retired in 0.2.2 batch S3)
> - handoff management: `main/50_playbook/handoff_management.md` + the runtime `<handoff_root>/README.md`
> - self-check tool: `main/70_tools/t2ag_doctor.py`

---

## 1. Triggers

Any one of the following triggers the cross-session recovery process:

1. **The student says "continue with XXX"**: for example "continue with CS1953", "continue with MATH1607H".
2. **The student says "read progress.md"**: for example "read main/40_course/CS1953/progress.md".
3. **The student mentions a course name or code**: mentioning an existing course in a new conversation, intending to continue.
4. **A new conversation begins and the student mentions course content without explicitly saying continue**: judge from context whether recovery is needed.

> **Not triggered when**:
> - The student wants to study a **new course** (absent from the course list) -> follow the new-course initialization process (see `new_course_init.md`).
> - The student is only chatting or asking a question that does not involve restoring course progress.

---

## 2. The complete steps

The default entry point runs first:

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --format markdown
```

When the tool succeeds, steps 1–4 describe the selection semantics the L0 packet must have; they
do not require the agent to read the same files in full again. Only when the tool fails are these
steps performed by hand as section-by-section excerpting; degradation must never be read as
"read everything".

### Step 1: restore the memory state pointers from L0

By default the current course consumes exact excerpts of the "last lesson summary" and "current
state pointers" from `main/00_core/t2ag_memory.md`, establishing the previous course, the
LearningActivity and the stopping point. When another course in the same active Group is
explicitly requested, consume only the two switch-verification rows (active Group / current
course) and never mix the previous course's summary into the target course. A course outside the
group requires a course-group switch first. Memory is only a cache: its Lesson pointer must never
be used to backfill an explicit activity field missing from progress, and on conflict with
`progress.md`, `progress.md` wins.

If memory is missing or its pointers are invalid, stop the tool-driven recovery, read the current
course row in the learning path and verify it against the current slice of the corresponding
`progress.md`; never scan directories or guess a course from a display name.

### Step 1.5: conditionally read the active classroom handoff

If the entry point declares a handoff index, or the agreed `<handoff_root>/README.md` exists at
runtime, check per `handoff_management.md` for an entry satisfying all of:

- `status=active`
- `scope=course_session`
- `applies_to` matching the current course / current LearningActivity
- the previous class did not complete `session_close`, or a difference against the formal source is pending verification

On a hit, read the "minimum state summary" first, and read the "continuity summary" only when the
user's intent, the evolution of a discussion, or the reason for an approach must be recovered.
Skip entirely when there is no match, when it is already resolved, or when it is an unrelated
topic handoff. A handoff is recovery evidence only and can never override `progress.md`.

If the exact stopping point shown by the handoff or the current activity is newer than
`progress.md`, pause new content first, verify the source position, the activity ID and the
student's confirmation record, repair `progress.md` after confirming with the student, then
refresh memory/learning_path, and only then continue teaching.

If `progress.md` has progress-node fields, verify the current completion node, checkpoint and
confirmation status at the same time. The current activity or cloud evidence may serve as
evidence pending promotion, but must never silently overwrite the source of truth; write it back
per `progress_tracking.md` after the student confirms.

<!-- rule: CTX-PACKET-007 -->
### Step 2: consume the current slice of progress.md

L0 excerpts only the complete frontmatter and the "current progress" section of the corresponding
course `progress.md`. That file remains the source of truth for the Course lifecycle, the single
foreground and the exact stopping point. The Activity lifecycle comes only from the ledger; the
file header should distinguish `lifecycle_status` from capacity status: the Course lifecycle comes
from this file, and capacity status is derived from the active G file.

- **In progress**: the current Lesson/Exercise, the source range and the exact stopping point
- **Completed**: what has been taught
- **Study hours invested**: the accumulated total
- **Next step plan**: what is to be taught next

<!-- rule: CTX-PACKET-008 -->
Only when the current slice cannot explain a conflict, the user asks about history, a formal
retest is due, or a mastery judgement is to be changed, does **L2 reads the corresponding teaching record** and the "mastered knowledge points" entries; daily recovery does not load whole stretches
of history by default.

### Step 2.5: consume the unclosed-question excerpt

L0 excerpts only "open" and "needs review" from the current course `question_bank.md`. When
recovering a class, prioritize questions blocking current progress; an answered entry enters L2
only when the current knowledge point or the student's follow-up hits it, never as a bulk load.

<!-- rule: ACT-ROUTE-001 -->
### Step 3: restore the main carrier per current_activity

First read `current_activity`, `current_activity_id` and `resume_path` verbatim from
`progress.md`. When an ongoing course is missing any of these fields, the ID does not match the
type, the path is not canonical, or the target does not exist, stop recovery immediately and
repair the `progress.md` foreground contract; never backfill from the retired `current_lesson`,
from memory, or from a directory scan.

Run the read-only route and let its result drive every activity read and write that follows:

```powershell
python -B main/70_tools/t2ag_activity.py --course <COURSE_ID> --intent recover
```

Do not continue if the command exits non-zero. `primary_read` is the single current activity main
carrier; `working_pages: null` means the default recovery chain must skip the textbook cache. No
Lesson/Exercise example below may override that routing result.

<!-- rule: ACT-ROUTE-002 -->
#### `lesson` branch

Only when `current_activity: lesson`:

1. require `current_activity_id` to be a real `lessonNN`; an active progress must never backfill `current_lesson`;
2. L0 reads the frontmatter of the canonical `resume_path` and the most recent recovery capsule;
3. a textbook Lesson must have, in L0, the current textbook window complete page by page and matching the progress page number; when it is missing the command exits non-zero and must not advance as `ready`;
4. in a new conversation this round must also complete the session Scope scan per `source_page_assets.md` §3.1 (A1–A6) and critical's `scope_scan` manifest; an existing Snapshot, a historical load receipt, or "path only / SHA only" is not A1 consumption for this round;
5. L1 reads, per the current stopping point, the necessary teaching records, Q&A, wrong attempts and completion node/checkpoint that L0 does not already contain;
6. when the current Lesson has `lesson_thoughts.md`, read the relevant ideas as needed.

<!-- rule: ACT-ROUTE-003 -->
#### `exercise` branch

Only when `current_activity: exercise`:

1. require `current_activity_id` to be a real `exerciseNN`; an old `Udddd` may be resolved only through this course's ledger alias;
2. L0 excerpts the "study scope" from the canonical `resume_path` and the current ExerciseProblem metadata from `problems.md`; a textbook-driven Exercise additionally excerpts only the current problem statement from the registry- and SHA-verified `source_path`;
3. L1 reads the directly related Attempt/Review only when the current problem already has a submission, grading or correction; opening a problem for the first time preloads no other problem's history, and must never leak a hint or answer to the student;
4. find same-ContentGroup context through `activity_map.md`; never read an Exercise as a Session of a Lesson;
5. historical Lesson context is resolved only from ledger events and ContentGroup relations, and is never written back to progress;
6. read `exercise_hint_gate` from the profile. When it is `enabled`, run
   `python -B main/70_tools/t2ag_hint_gate.py --course <COURSE_ID> --problem <PROBLEM_ID> --intent <INTENT>`
   before every reply; on deny, nothing may be sent. A conceptual question uses `concept_answer`,
   answering only that concept and never applying it back to the current problem automatically.

<!-- rule: ACT-ROUTE-004 -->
<!-- rule: ACT-ROUTE-008 -->
**An Exercise first start must not read or construct a Lesson path**; it does not write
`current_lesson`, and it points `resume_path` straight at
`exercises/exerciseNN/exercise.md`. A historical Lesson's `working_pages/` may be entirely absent
without affecting Exercise recovery.

### Step 4: consume the student teaching contract

L0 excerpts section by section from the student profile, focusing on:

- **`main/10_student/profile/profile.md`**: frontmatter, basic information, execution parameters, learning goals, tutoring preferences, special requirements and the individual character outline; dated historical quotations are not read in full by default
- **`course_reflections.md`**: the knowledge-point tree of the current course and the three most recent course reflections
- **`reasoning_patterns.md`**: relevant entries as needed when handling practice, retests or cross-course transfer

**File path**: `main/10_student/` (the current student instance)

**Reading rules**:

1. Consume L0's profile teaching contract; do not read it in full again.
2. Enter L2 for the corresponding profile text only when scheduling, adjusting parameters, or explaining personal history.
3. Read the current course's knowledge-point tree and three most recent reflections in `main/10_student/profile/course_reflections.md`.
4. When handling practice, retests or cross-course transfer, read `main/10_student/profile/reasoning_patterns.md` as needed; when alternative-method training or a state update is involved, also run `method_distillation.md`.
5. When the current activity is a Lesson, read `lesson_thoughts.md` as needed; when it is an Exercise, read `exercises/exercise_thoughts.md` and the current Unit's evidence as needed; also read the course core-content reflections distilled from those local sources in `course_reflections.md`.
6. **Adjust teaching tone and pace accordingly**:
   - if the student has recently shown anxiety, frustration or other negative emotion -> slow the pace and confirm more often
   - if the student's mood is positive -> some added challenge is appropriate

> **Emotional state adjusts only "how to teach"**: when recovering context, confirm the student's
> state before adjusting pace, but never lower course standards, avoid correction, or go easy on a retest.

### Step 5: the textbook source window (Snapshot-only)

<!-- rule: ACT-ROUTE-005 -->
In the default recovery chain, **the textbook source window applies only to `lesson` +
`course_type: mastery` + `learning_mode: textbook`** (or the equivalent legacy driver during migration). Skip this step when the current activity is an Exercise; goal /
project / praxis Lessons skip the textbook window.

**Current path (EV-0012)**:

1. read the **current** `LessonPreparationSnapshot` (the `preparation/current_snapshot.json` pointer; taking the lexicographically last `PREP-*.json` is **forbidden**) and the `LessonMap`;
2. load the Course `source_assets` page text per Snapshot/Scope; page images come from `.cache` or are rebuilt from the PDF;
3. tool entry points: `t2ag_source_pages.py prepare --course … --current …` (read-only) and the snapshot fields in critical.

Those three prove `prepared` and the text source only (they do not satisfy A1). The first time
each new conversation enters a textbook Lesson, the Prefetcher must also consume the full Scope
content body page by page in this session, per `source_page_assets.md` §3.1 and critical's
`scope_scan` manifest (the current default observable path is in §3.1.4), and report back: the
snapshot, the PDF SHA, the complete `pdf_page_index`, the consumption evidence for each page
(including the in-book `printed_page_label`) and any conflict. Stop teaching on a page missing
relative to Scope (an A4 omission) or on the two page numbering schemes being mixed. Main must
never read a historical `content_consumed=true`, a receipt, a file hash, frontmatter alone, or a
helper agent's "no further reading needed" as itself having satisfied A1 this round. The
completion statement is issued by the host only (A6).

<!-- rule: CTX-PACKET-009 -->
**The legacy path is retired**: the former
`lessons/<current_activity_id>/working_pages/` path was retired in 0.2.2 batch S3. If the new
preparation path does not exist, the context tool must fail and **never return `ready` without
the textbook**. Complete it per `ocr_correct_flow.md` + `source_page_assets.md` and re-run.

**Read-only discipline during recovery**:

<!-- rule: ACT-ROUTE-010 -->
- The recovery chain treats `book/.cache/`, `preparation/` and `source_assets/` as strictly read-only. On an over-quota, suspected-stale or inconsistent pointer, report and stop — **never clean up automatically**, evict, rename or rebuild those directories, and never evict a P0 page of the current Scope. Cleanup is a separate maintenance action requiring the user's authorization with full knowledge of what is being deleted.
- If recovery reveals that a write-back is needed (a missing page, a Snapshot pointer change, a source-of-truth repair), that is a separate action: perform it only after obtaining **exact RT3** authorization, and that authorization covers only the objects named in the current round. Recovery itself carries no write authorization, and "so the class can continue" is never a reason to skip it.
- A Lesson not yet entered (no `learning_enter` in the ledger) legitimately has no Snapshot; report "pages not prepared yet" and never fabricate an empty Snapshot or a fake receipt to pass a check.

### Step 6: confirm the health checks still hold, and run the opening spot-check

If this session's entry point already passed `t2ag_state_refresh.py --check` and then doctor, and
nothing has been written or changed externally since L0 was generated, reuse that result rather
than re-running. Otherwise run the state check first, then doctor. Generated-cache drift is a
blocking item for the current recovery: repair the source of truth, or promote the evidence after
confirmation, then refresh with `--write`; never hand-copy a generated block.

If the environment can execute code, run:

```bash
python -B main/70_tools/t2ag_doctor.py --profile runtime
```

- On a FAIL: repair the authority chain as instructed before starting the class.

#### The opening spot-check budget (tiered)

The number of spot-check questions is set by **how much content the previous class advanced**
(judged from the last teaching-record entry in `progress.md`):

| Previous advance | Questions | Composition |
|---|---|---|
| <= 20 min of content (about 1 knowledge point) | 1 | 1 active mistake or knowledge-point coverage |
| 20–40 min (about 2–3 knowledge points) | 2 | 1 knowledge-point coverage + 1 active mistake |
| > 40 min (about 4+ knowledge points) | 3 | 1 knowledge-point coverage + 1 active mistake + 1 aged rumination |

- Skip a slot when no candidate exists; never manufacture a record to fill the quota.
- The specific retest rules still follow `main/50_playbook/mistake_retest.md`.

#### Skipping, and the switch to embedded confirmation

- The student may skip the spot-check: "skip", "not today" or similar counts as skipping this time, with no penalty, going straight to step 7.
- Record `spot_check_skip_streak: N` (consecutive skips) in the `progress.md` file header; completing a spot-check resets it to 0.
- **After 3 consecutive skips**: the agent silently switches to "embedded confirmation" — no separate spot-check questions, but 1–2 confirming questions woven naturally into the teaching that follows (such as "how does this concept relate to the XXX we did last time?"), not marked as a formal retest and not counted in the mistake_bank formal results.
- Embedded confirmation constrains nothing: the student may say "I'd like a retest" at any time to restore the formal spot-check.

### Step 7: confirm with the student — "last time we reached XXX, continue?"

This step consumes the canonical four-state `turn_intent` vocabulary in
`progress_governance.md` §9; it maps recovery behavior to that vocabulary rather than defining a
second taxonomy. `explicit_continue` and `ambiguous_resume` split at item 3,
`conflict_resolution` is handled by item 5, and `new_scope` returns to the normal authorization
gate for the requested new scope.

Combine the above and confirm the recovery point with the student:

1. **Summarize the previous progress**: the Lesson branch names the chapter, textbook page and exact position; the Exercise branch names the Unit, the current problem/batch and the exact stopping point. Never invent a chapter or Lesson.
2. **Confirm the student's state**: if personality_baseline or course_reflections show recent emotional fluctuation, greet appropriately.
3. **Route by `turn_intent`**: only when the user has not already asked to continue this round, ask
   "continue from here, or would you like to review what came before?"; when the user has already
   said continue, do not ask again.
4. **Authoritative action and creative addition coexist**: a pending checkpoint must be reused verbatim and marked as the "exact stopping point" of the current slice of `progress.md`; clearly-labelled summary questions, warm-ups, analogies or model-generated exploratory questions may be added, but must never replace the authoritative stopping point, pose as progress evidence, or bypass the Exercise hint gate.
5. **Stop on conflict (`turn_intent=conflict_resolution`)**: when the route, progress, Activity,
   current page SourcePageAsset or Scope manifest disagree, report the conflict first and show the
   student no candidate teaching action. Explain in natural language how each choice changes the
   result; expand internal IDs, schema, and status codes only when needed.
6. **Restore the classroom tree**: before the first content in a textbook Lesson, show a location
   summary rather than expanding the full tree by default. Read the profile's
   `lesson_tree_display_mode`: a missing value or `progressive` uses this default; `full` expands
   the same complete coverage tree immediately. An explicit request this round overrides either
   mode, and the profile is changed only when the student asks to save that preference. Derive the
   cursor deterministically from the complete ordered checklist as
   `N blocks on this page / current block K / N-K remaining`. Then traverse in order until every
   block reaches `covered`, `explicitly_deferred`, or `outside_active_lesson_boundary`; omit no
   block silently. A completed scan is not completed teaching coverage.
7. **Restore the three-gate protocol**: a "continue" from an old conversation is never reused across a recovery point; a correct answer closes the understanding gate only. After a derivation or summary you must again ask how the student feels and what they doubt, and obtain a one-shot continuation authorization for the next teaching block.
8. **Restore the Lesson opening**: if the current Lesson has no opening shown and confirmed in this
   session, first summarize this lesson's content. The ASCII knowledge tree consumes the same
   `lesson_tree_display_mode`: `progressive` gives a compact summary of goal, trunk, branch index,
   dependencies, this round's scope and current branch; `full` expands the same complete tree.
   Both modes then traverse in teaching order, and an explicit request for the full tree takes
   effect immediately. The summary is a deterministic rearrangement of that one complete tree,
   never a second truth source. Where no ready-made tree exists, compose one creatively from the
   Lesson scope and LessonMap; after displaying it, ask how the route feels and whether to enter
   the first block, and never record the overview as content already taught.

**Confirmation example**:

```text
Last time we reached MATH1607H Mathematical Analysis, Chapter 1 §1 Sets. We finished the
definition and notation of a set on page 21; the empty set, subsets, set equality and intervals
on page 22 are **not yet covered**.

Continue from here, or would you like to review what came before?
```

> **Important rule**: before the student explicitly confirms "continue", do not jump to later
> content. Even if the student asks a question about later material, answer only that question and
> do not expand into material not yet taught.

When moving to a new page, "continue" must be obtained **after** the teacher has shown the
previous page's coverage checklist, announced "page turn: PDF N / in-book M" and displayed the new
page's character tree. If the teacher has already crossed the page without satisfying those gates,
the exchange on the new page counts only as clarification, not as formal advance, and the recovery
point falls back to the most recent fully covered and confirmed block on the old page.

---

## 3. Choosing a presentation form, and generating one on the spot

> The student may always ask the model to switch to, or add, a presentation form that helps them
> learn. An explicitly requested form takes priority over the default judgement.

| Form | Strengths | Limits | Default use |
|---|---|---|---|
| cropped PNG of the original | faithful to the textbook, cheap | hard to edit or interact with | the original figure is clear and readable |
| SVG | crisp, light, good for structure diagrams | poor for photos and complex texture | set diagrams, flowcharts, static relations |
| TikZ | rigorous mathematical typesetting, reproducible | higher compile and viewing cost | geometry, paper-style mathematical figures |
| HTML | operable, responsive, can simulate | needs a browser and interaction upkeep | sliders, animation, interactive quizzes |

Default decision: crop when the original is readable; auto-generate the single most suitable
format when the structure is uniquely determined by the body text; ask first when proportions,
data or geometric relations are uncertain; generate nothing purely decorative; use HTML only when
manipulation and immediate feedback are needed. A figure rebuilt from body text must be labelled
"a schematic rebuilt by AI from the textbook text, not the original textbook figure".

A one-off display may stay in the conversation; an asset with reuse value is routed by the current
activity:

- Lesson: save to `lessons/<current_activity_id>/illustration/` and register the source, format and date in the current Lesson;
- Exercise: a general teaching schematic goes to the course `book/course_materials/supplements/` with a backlink from the current `exercise.md`; a student's submitted image goes only into the corresponding Attempt's `assets/` and must never be reused as a teaching asset.

A preference recurring within a course is written into `course_reflections.md`; a preference stable
across courses is written into `profile.md`.

---

## 4. Page-window management during recovery

**This section runs only when the read-only activity route returns `current_activity: lesson` and
the course is Mastery + textbook-led. An Exercise (including one with a historical Lesson) and every
other progression protocol skips the whole section, does not parse an old `textbook_page`, and does not construct a
Lesson path from it.**

After context is restored, textbook source text is managed through the preparation Snapshot +
source_assets:

### Baseline Scope / TeachingWindow (EV-0012)

- **LessonScope**: a contiguous **5–8** pages including the current page (a short book = all available pages, fixed); see `source_page_assets.md`.
- **TeachingWindow**: projects the current page and its residents; the default preference is relative `[-1,0,+1,+2,+3]`, shifted at the start/end of the book.
- Page images prefer `.cache`; when the quota is full, a legitimate CacheEviction applies, and only on failure session_temp.

### The preload / prepared acceptance gate

**New path**: before teaching begins there must be a valid `LessonPreparationSnapshot` (Scope + Map + load receipts) and a sufficient verification level (`t2ag.md`).

**The legacy path is retired**: the former `working_pages/source_excerpt.md` + `progress.md`
`textbook_page` / `working_pages_window` path was retired in 0.2.2 batch S3; historical excerpts
are in each course's `archive/`.

The atomic page-turn flow: **render -> visually inspect -> OCR -> proofread into source_assets ->
new Scope/Snapshot -> progress -> doctor**. A new page must not be taught while any step is
incomplete.

### Window management rules (EV-0012)

| Situation | Operation | Result |
|---|---|---|
<!-- rule: ACT-ROUTE-009 -->
| starting a normal book | prepare a contiguous Scope of **5–8** pages (default 5) | new Snapshot + current pointer |
| widening / page turn | new Scope version -> a **new** Snapshot; the old Snapshot is kept read-only | the old PREP is unchanged |
| short book `N<5` | Scope = all available pages, fixed | `short_document: true` |
| page-image quota | rebuildable non-P0 items inside `.cache` go by CacheEviction | P0 is never deleted; on failure `cache_quota_blocked` |
| legacy physical files | retired (0.2.2 batch S3); historical excerpts in each course's `archive/` | — |

**Abolished**: working_pages_window, automatic deletion of `working_pages` at session close, and
the old 4-page baseline / 6-page ceiling wording.

> **source_assets**: persistent verified text is never deleted for window management. Only the
> `.cache` PNGs are evictable derivatives. The legacy `working_pages/` path was retired in 0.2.2
> batch S3; historical excerpts are in each course's `archive/`.

---

## 5. Points to watch

### 5.1 Confirm the student's emotional state before adjusting pace

- When recovering context, read `main/10_student/profile/profile.md` and the recent course reflections first; read the reasoning profile as needed when handling practice or a retest
- Recent anxiety, frustration or other negative emotion -> slow down, encourage more, lower the difficulty
- A positive mood -> some added challenge, a faster pace
- **Never look at progress without looking at the person**: teaching pace is set by mastery and emotional state together

### 5.2 Confirm section by section; never skip content

- After recovery, continue from the position **not yet finished** last time; never skip content that was left unfinished
- After finishing all the content of the current page/section, stop and ask the student: "understood? continue / explain again / a question?"
- Treat `question:` or `doubt:` from the student as the same trigger: pause further advance, answer first; the question's status is written to `question_bank.md`, and the activity record is written to the current Lesson or Exercise main carrier returned by the read-only route
- Before the student explicitly confirms "continue", do not jump to later content
- Even if the student asks a question about later material, answer only that question and do not expand into material not yet taught

### 5.2.1 The exercise closure gate

- After each exercise, check whether the student's reply explicitly says they have no questions
- If it does not: analyse the reasoning method from the steps the student actually wrote, then ask whether anything is unclear
- If there is only a final answer with insufficient process evidence: never fill in or guess the student's reasoning; ask them to supply the method
- If the student did explicitly say they have no questions in that reply: the reasoning analysis and the question prompt may be skipped for this problem
- Exercise closure does not replace section-by-section confirmation; before entering the next concept, definition or theorem, the student must still explicitly say "continue"

### 5.3 Textbook source text comes first

- When teaching resumes after recovery, every concept, definition, theorem and proof must cite the textbook source text first
- The teaching plan supplies the framework; the textbook source supplies the content
- "Look at the textbook source" means actually scanning and extracting the source, not restating from material already at hand

### 5.4 The `working_pages/` lifecycle (retired)

- `working_pages/` was a textbook Lesson's legacy scratch area and was retired in 0.2.2 batch S3.
- The new authority is the Course `source_assets` + the preparation Snapshot/Map.
- Historical excerpts and OCR are archived in each course's `archive/`; they must not be rebuilt or reused.
- `illustration/` is persistent and is unaffected by a course ending

### 5.5 Reliability of the state pointers

- The foreground fields and the exact stopping point in `progress.md` are the recovery entry; the Activity lifecycle must be replayed from `activity_ledger.md`
- A local stopping point inside the current activity main carrier is fine-grained evidence used to help repair the source of truth; neither a Lesson's "last stopping point snapshot" nor an Exercise's exact stopping point is a GENERATED cache
- When files disagree, run `main/70_tools/t2ag_doctor.py --profile runtime` first, then take `progress.md` as authoritative; when the current activity's evidence is finer, write back `activity_position` after confirming with the student, and never infer it from a historical Lesson
- A checkpoint may silently store the exact stopping point, but a completion node completes only when the course's existing closure evidence is satisfied; the two must never be written interchangeably

### 5.6 Synchronized updates after recovery

- After recovering and continuing to teach, each session end updates:
  - the current Lesson or Exercise main carrier returned by the read-only route; an Exercise never updates a historical Lesson
  - `progress.md`'s `activity_position`, the "current progress" section, the "teaching record" and the accumulated study time
  - new knowledge errors and retest results in `[course]/mistake_bank.md`
  - the progress caches in `main/00_core/t2ag_memory.md` and `main/10_student/profile/learning_path.md`
  - `main/10_student/profile/profile.md` or `course_reflections.md` (if there is a new state/reflection record)
  - if this session was recovered from an active classroom handoff, close it per `handoff_management.md` after the formal write-back is verified
