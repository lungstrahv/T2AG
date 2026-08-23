# The in-course exercise evidence loop

**Protection level**: core-playbook

> This flow defines the minimal 0.2.0 ExerciseProblem → Attempt → Review loop. It does not
> establish KnowledgePoint, an OCR confirmation state machine, or a cross-course AbilitySummary;
> those candidate capabilities are deferred to a 0.2.1 design adjudication, after three rounds of
> real Attempt/Review have accumulated.

## 1. Rule boundary, activity links, and identity

- The system objects of an Exercise and the shared learning loop are defined by
  `00_core/learning_activity_model.md`; this file governs only the runtime procedure
  ExerciseProblem → Attempt → Review. `activity_map.md` holds the in-course ContentGroup links;
  `exercises/<EXERCISE_ID>/exercise.md` is the activity main carrier, and `problems.md` holds only
  the problems, their source, and this unit's execution route.
- Never stuff a general schema, a course-wide ordering policy, or a master Lesson–Exercise link
  table into a single Unit; a Unit may state why it reordered itself, but it must never become the
  rule source governing other Units.

Create the course-level activity map the first time a textbook course establishes a Lesson or an
ExerciseUnit:

```text
40_course/<COURSE_ID>/
  activity_map.md            # the course-level source of truth linking ContentGroup to Lesson/Exercise
  lessons/lessonNN/lessonNN.md
  exercises/<UNIT_ID>/
```

`activity_map.md` must contain a "Content group map", and every row carries at least:

```markdown
| content_group_id | source_scope | lesson_ids | exercise_ids |
|---|---|---|---|
| COURSE123-B001-C01-S01 | B001 / ch.1 / §1 | lesson01 | exercise01 |
```

- A ContentGroup is a knowledge link point in the source material, not a class session and not a
  problem.
- Lesson and Exercise are sibling LearningActivities inside a Course; neither one owns the other.
- Separate multiple `lesson_ids` or `exercise_ids` with commas; write `—` when there is no
  corresponding activity.
- The map is the source of truth for the relation; a Lesson and an Exercise declare only their own
  ContentGroup and must agree with the map. Any dangling entry, duplicate registration, or
  ContentGroup drift is a FAIL. The same activity must not be written twice in one cell; every
  Lesson/Exercise that exists must be registered at least once, and an empty `content_group_ids` is
  not an exemption from registering.
- An Exercise must not declare ownership fields such as `lesson_id(s)` or a Session reference, and
  must not create `sessions/` or an `exercise_session` object.

The first time the student expresses an explicit thought about an exercise, add the course-level
summary index; do not create an empty file when there is no real thought yet:

```text
40_course/<COURSE_ID>/exercises/
  exercise_thoughts.md       # the cross-Unit summary index; the verbatim words stay in the Attempt
```

```text
40_course/<COURSE_ID>/exercises/<UNIT_ID>/
  exercise.md
  problems.md
  attempts/
    AT0001/
      attempt.md
      assets/          # required in image/mixed mode
  reviews/
    RV0001.md
```

- `EXERCISE_ID`: the in-course canonical `exerciseNN`; `Udddd` is permitted only as a course-scoped
  legacy alias.
- The `exercise.md` of a textbook-driven Exercise must declare `exercise_id` and
  `content_group_ids`; `problems.md` must declare the same `exercise_id` and a unique
  `content_group_id`, and must point through
  `source_artifact_id / source_path / source_locator / source_sha256` at the persistent proofread
  problem source inside the Course `book/`. Lesson and Exercise directories are physically separate
  and are related to the source-material knowledge group only through the activity map.
- `source_path` and the `source_document` inside the problem source must be canonical POSIX
  relative paths that, once resolved, still lie inside the same Course `book/`, and the path chain
  must not pass through a symlink, a junction, or a reparse point.
  `problems.source_artifact_id`, the active registry canonical, and the problem source's
  `artifact_id` must be identical, and the two `source_locator` values must agree; both the
  problem-source digest and the original-document digest must be real SHA-256. When lite
  deliberately omits the original textbook binary, a hash-bound migration manifest must prove the
  path + SHA exactly.
- In a textbook-driven unit, every problem's dependency field must be written in full as
  ``- Depends on completion node: `<content_group_id>-N<number>` ``. The backticks, the full
  canonical ID, and the current `content_group_id` are all three required, and the full ID must
  really exist in the `Completion nodes` table of that course's `progress.md`. An empty value, a
  fabricated value, an unparseable value, a fake node in the same group, or a pointer into another
  content group is a FAIL.
- An active textbook exercise unit must declare all of:
  - `source_order`: the original textbook order, which must cover every problem ID and must not
    reorder the problem statements;
  - `teaching_sequence`: the current execution order, which must contain the same set of problems
    with no repeats; absent a deliberate design it equals `source_order`;
  - `sequence_rationale`: when the order departs from the textbook, the prerequisite relation or
    the student evidence that justifies it.
- While teaching, work on only the earliest unclosed problem in `teaching_sequence` at a time; an
  open in-problem question or an unfinished correction must not be skipped over to the next
  problem. The route may be adjusted on new evidence, but the change must be recorded in
  `problems.md`, `exercise.md`, and progress together; never sneak across a `content_group_id`.
- `problem_id`: in-course `<UNIT_ID>-Qddd`.
- `attempt_id`: in-unit `ATdddd`; one Attempt is one real submission batch and may contain several
  problems.
- `review_id`: in-unit `RVdddd`, chosen to avoid colliding with a Binding's `RNNN`.
- The full identity is `course_id / unit_id / local_id`; a local number is allocated only inside its
  owning unit and is never reused.

When there is no real submission, keep only `_README.md`; never create an empty AT/RV instance to
make a check pass.

## 2. The optional student hint gate

### 2.1 Setting and intent

`exercise_hint_gate` in the student profile frontmatter is the single persistent switch:

- `enabled`: an Exercise teaching reply must first run the read-only `t2ag_hint_gate.py`;
- `disabled`: no extra gate denial is executed, but zero hints at problem opening, the hint ladder,
  and the independent-evidence rule all still apply;
- an uninitialized Skeleton uses `ask`, and the student must choose at first startup; the model must
  never choose on their behalf.

When enabled, reply intents are classified as:

| intent | allowed without extra authorization | scope |
|---|---|---|
| `reasoning_feedback` | yes | only examines the reasoning the student already expressed; adds no object, sub-goal, lemma, construction, or next step |
| `concept_answer` | yes | by default answers only the concept the student explicitly asked about, does not apply it back to the current problem automatically, and returns to the original stop afterwards; when the student explicitly asks for the application, it moves to the corresponding hint authorization |
| `direction_hint` | no | requires an explicit `direction` authorization |
| `specified_reference` | no | requires an explicit `reference` authorization |
| `full_solution` | no | requires an explicit `solution` authorization |

The deny return code of `t2ag_hint_gate.py` must be consumed; you may not send the reply first and
run the check afterwards. That tool is an auditable preflight, not an unbypassable safety boundary
inside the model; to hard-block output, a response intermediary outside the model must run the tool
and intercept the deny.

### 2.2 Creative interaction and extra-exercise opt-in

- Spoiler protection guards only the independent attempt at the current Exercise; it does not
  forbid analogies, alternative phrasings, student-invented examples, historical background,
  graphical explanations, or another route the student asks for. If such content would expose the
  key structure of the current problem, it is still handled at the real `assistance_level` and hint
  authorization.
- "Extra exercises" means new practice beyond the textbook problems, the current Exercise, and
  immediate comprehension checks. Unless the student requested it or explicitly opted in, the
  teacher may at most ask "would you like extra practice?" and must not generate or display the
  actual problems in advance.
- After the student requests or explicitly agrees, extra exercises may be generated; they must be
  labelled `teacher_generated_supplement`, must not pose as textbook problems, past exam papers,
  or an assessment pool, and are not added automatically to `source_order` or to completion
  evidence.
- A one-sentence restatement, judgement, or concept check about the teaching block just delivered is
  a comprehension gate, not an extra exercise, and may be used at the pace of the class.

### 2.3 The Attempt snapshot and help exposure

An Attempt's `created` must be a parseable, zero-padded, really existing ISO `YYYY-MM-DD` date; a
timestamp, arbitrary text, a non-zero-padded date, and a non-existent date are all illegal. An
Attempt created on or after 2026-08-01 must additionally carry in its frontmatter:

```yaml
hint_gate: enabled | disabled
assistance_level: none | direction | reference | solution
```

- `hint_gate` is a snapshot of the profile setting at the moment the Attempt was created; a later
  change to the switch does not rewrite a historical snapshot.
- `assistance_level` records the highest real help exposure as of that Attempt, and must not be
  lowered because the gate was switched off afterwards.
- A compliant `concept_answer` does not raise the help level, but the concept scope and
  `scope_only` must be recorded in "Answer context"; if the answer bridges the concept back to the
  problem, or gives a problem-specific sub-goal or step, it is upgraded to the real exposure.
- Record the student's verbatim authorization for every direction/reference/full explanation;
  without an explicit authorization, never upgrade on the grounds that "the student seems stuck".
- When a key step, structure, or answer leaks without authorization, record
  `teacher_hint_contamination`; that content must not count as the student's independent mastery,
  and must not be written down as a student mistake either.
- A legitimate historical Attempt from before 2026-08-01 does not get a retro-fabricated gate
  snapshot; if the two fields appear, they must appear together and use legal enumerated values.
  Doctor enforces the fields only for new Attempts from 2026-08-01 onward.

## 3. The Attempt schema

`attempts/AT0001/attempt.md`:

```markdown
---
type: exercise_attempt
course_id: COURSE123
exercise_id: exercise01
attempt_id: AT0001
problem_ids: [exercise01-Q001, exercise01-Q002]
mode: mixed
status: submitted
created: 2026-07-26
hint_gate: enabled
assistance_level: none
---
# AT0001 answers

## Answer context

- Help used: none
- Hint gate: enabled
- Authorization and concept Q&A: none

## exercise01-Q001

- Answer: see body; if the answer exists only in the original image, write "see the original
  image" and never fabricate a transcription.

### Student thoughts (optional)

- Verbatim: record only the solving insight, association, or strategy the student stated
  explicitly; omit this section when there is none.

## exercise01-Q002

- Answer: ...

## Original evidence

- `assets/page01.png`: the student's submitted original image
```

Constraints:

- `mode` is only `text / image / mixed`; image/mixed must keep at least one original image file.
- `status` is only `submitted / withdrawn`. The AT directory is created only on the first real
  submission.
- The image is the original evidence; a manual transcription must state its source, and an OCR
  result must never overwrite or replace the original image.
- "Student thoughts" is optional first-hand evidence inside an Attempt; it must come from something
  the student expressed explicitly and should preserve their words. The teacher must not write it in
  from the answer. Missing student thoughts is not missing evidence, and no empty placeholder is
  produced.
- The teacher's interpretation, evaluation, or normalization of a thought goes into the Review's
  "Reasoning observation / response to student thoughts" and must never overwrite the Attempt's
  verbatim words; only after it repeats across at least two problems and really transfers may it be
  promoted to `reasoning_patterns.md`.
- The course-level `exercises/exercise_thoughts.md` holds only source links, short excerpts, tags,
  and intended future use; it deduplicates on the `Unit / Attempt / Problem` source tuple, copies no
  full answer, and never becomes a second source of the student's words.
- A "short excerpt of the student's words" in the summary must be a directly quotable, traceable
  quotation; a model paraphrase may only be labelled "teacher distillation". A student self-
  correction and a teacher addition are attributed separately and must never be merged into a
  conclusion that looks as if the student produced it whole.
- This version does not record OCR confidence or a student transcription-confirmation state; never
  use an empty field to pretend that capability exists.
- Every `problem_id` must exist in the same unit's `problems.md`, and the body must carry the
  matching second-level heading and answer item.

## 4. The Review schema

`reviews/RV0001.md`:

```markdown
---
type: exercise_review
course_id: COURSE123
exercise_id: exercise01
review_id: RV0001
attempt_id: AT0001
problem_ids: [exercise01-Q001, exercise01-Q002]
reviewer: teacher
status: recorded
reviewed: 2026-07-26
---
# RV0001 grading

## exercise01-Q001

- Result: correct
- Reasoning observation: ...
- Response to student thoughts: ... (only when the Attempt carries student thoughts)
- Feedback: ...
- mistake_refs: []
- question_refs: []
```

- `reviewer` is only `teacher / student / joint`; `status` is only `recorded / amended`.
- A per-problem result is only `correct / partial / incorrect / unresolved`.
- A Review must reference a really existing Attempt, and its problem set must come from that
  Attempt.
- A Review records only this round's evidence; promotion to `reasoning_patterns.md` requires the
  pattern to repeat across at least two problems.

## 5. Session-close write-back

1. On entering an Exercise, create or recover `exercise.md` first; it holds the current problem, the
   exact stop, and the evidence pointers, and copies no original answer.
2. After the student submits, create one batch-level Attempt; multiple images from the same batch go
   into the same `assets/`; when the student expresses a solving insight explicitly, append their
   verbatim "Student thoughts" under the matching problem; a new Attempt also stores the gate
   snapshot, the highest help exposure, and the real authorization/contamination record.
3. After grading, create the Review and record the result, the reasoning observation, and the
   feedback problem by problem.
4. Write or merge a definite knowledge error into the mistake bank, and write `mistake_refs` in the
   Review.
5. Write an unclosed question into the question bank, and write `question_refs` in the Review.
6. Update the status and error level in `problems.md`; never copy a problem statement backwards out
   of a Review. A textbook problem statement may only be projected from its persistent problem
   source after proofreading; never read a historical Lesson's `working_pages/` as a runtime
   dependency.
7. Update the reasoning patterns only after a cross-problem repeated pattern reaches the evidence
   threshold.
8. Update the exact stop and the evidence pointers in `exercise.md`, then update progress; Lesson
   and Exercise each write their own learning record and never serve as the other's body.
9. Finally run the state refresh and doctor.

## 6. The exercise-thoughts summary

Create it the first time a real student thought appears:

```markdown
---
type: exercise_thought_index
course_id: COURSE123
updated: 2026-07-26
---
# COURSE123 exercise thoughts

> This file is a summary index; the student's verbatim words are governed by the linked Attempt.

## exercise01 / AT0001 / exercise01-Q001 / 2026-07-26

- Source: `exercise01/attempts/AT0001/attempt.md`
- Short excerpt of the student's words: ...
- Teacher distillation: ...
- Index tags: ...
- Later use: ...
- Reasoning pattern: not promoted / `RP-xxxx`
```

- A raw insight triggered inside a lesson by the teaching itself still goes in
  `lessons/lessonXX/lesson_thoughts.md`; a thought triggered while answering an exercise goes to the
  Attempt first and is then summarized here.
- Course experience, pace, and how the course felt, plus core-content reflections distilled from a
  lesson or exercise, go in `10_student/profile/course_reflections.md`; life, philosophy, emotion,
  and long-term metacognition go in `10_student/profile/profile.md`; a stable cross-problem solving
  pattern goes in `reasoning_patterns.md`.
- The distillation gate for a core-content reflection: the student explicitly marked it as
  important, or the content links a lesson to an exercise, links more than two knowledge nodes, or
  can guide later study — any one of these suffices. A distilled entry must link back to its local
  source; an ordinary local spark stays in its own file and is not promoted just to raise the count.
- When recovering an exercise, read the recent entries related to the current Unit/knowledge point;
  "Later use" must land on one of a hint, a counterexample, a retest, or a method transfer — never
  collected and left unconsumed.

## 7. The doctor contract

- Validates the U/problem/AT/RV IDs, the filenames, the frontmatter, and reference closure.
- Validates the Skeleton initialization template, and the sibling links among `activity_map.md`,
  Lesson, and Exercise; a dangling activity, a duplicate inside a table cell, a missing registration,
  or ContentGroup drift is a FAIL.
- Rejects Lesson/Exercise holding ownership of each other, and the retired
  `sessions/ExerciseSession` structure.
- An image/mixed Attempt missing its original image is a FAIL.
- An Attempt referencing an unknown problem, a Review referencing an unknown Attempt, and a problem
  set out of range are all FAILs.
- An Attempt `created` that is not a real ISO date is a FAIL; so is a new Attempt from 2026-08-01
  onward that lacks `hint_gate / assistance_level`, carries only half the pair, uses an illegal
  enumerated value, or a template that does not carry that schema; a legitimate historical Attempt
  does not get retro-fabricated fields.
- A Review missing a per-problem result, or carrying an illegal result value, is a FAIL.
- The Skeleton carries this schema only, never a real AT/RV instance.
