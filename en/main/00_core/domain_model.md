# T2AG 0.2.3 Domain Model

## 1. Student

This repository *is* one student instance. A Student owns the profile, learning path, reasoning
patterns, reflections, activities and engagements; there is no longer a Case, an SN route, or a
`students/<id>/` wrapper layer.

Authorities:

- identity and execution parameters: `10_student/profile/profile.md`
- the course list cache: `10_student/profile/learning_path.md`
- problem-solving patterns: `10_student/profile/reasoning_patterns.md`
- course reflections and core-content thinking: `10_student/profile/course_reflections.md`
- agent collaboration preferences: `agent_collaboration_schema / agent_pool_limit / agent_max_active / agent_parallel_startup / agent_startup_readiness / agent_background_reporting` in `10_student/profile/profile.md`. They express only the maximum compute topology the student permits, the startup-readiness policy and the background-reporting preference. `agent_pool_limit` is the capacity of the retained identity pool including Main; `agent_max_active` is the concurrent-run ceiling including Main. A completed agent releases its concurrency slot while remaining reusable; none of this is a write permission, a terminal lifecycle, or RT3 authorization.

## 2. Course

A Course is the single aggregate root of the course definition and the current instance progress:

```text
40_course/<COURSE_ID>/
  course.md       # stable content, textbooks, teaching constraints
  progress.md     # Course lifecycle, the single foreground and the exact stopping point
  activity_ledger.md # Activity lifecycle, pending/CLR, aliases, statistics
  activity_map.md # ContentGroup <-> Lesson/Exercise structure
  lessons/
  exercises/
  mistake_bank.md
  question_bank.md
  book/
```

`course.md` never stores the student's current stopping point; `progress.md` never copies the
whole course plan and never owns the LearningActivity lifecycle. The Course
lifecycle/foreground/stopping point and the Activity lifecycle are owned by `progress.md` and
`activity_ledger.md` respectively, and a conflict must never be resolved by "last writer wins".

### 2.0 Course Type owns progression; Learning Mode belongs only to Mastery

- **`course_type` = completion semantics**: what evidence can close this course to completed (the **stopping condition**).
- **`course_type` also selects the progression protocol**: Mastery enters a selectable Learning Mode; Project enters its Project Plan; Praxis enters the real-action, feedback, and reflection loop.
- **`learning_mode` belongs only to `course_type: mastery`**, with `textbook | goal | project`. Project and Praxis declare no mode. Legacy `default_driver/course_driver` fields remain readable only during migration and are no longer writable truth.

The three values of `course_type` differ in **who judges**:

| Value | Judge | Reproducible | Closing evidence | Authority |
|---|---|---|---|---|
| `mastery` | inside the system: the teacher/student confirmation gate | — | block-by-block understanding closed, no dangling questions | the confirmation gate mechanism (common to every course) |
| `project` | outside the system, reproducibly decided | yes | every milestone binds verification mode A/B/B-K and satisfies the three mechanisms | `project_verification.md` §0 |
| `praxis` | outside the system, open-world consequences | no | a real action entry point + a bundle of behavioural evidence | `book_management.md` §3 |

**"There is an artifact" is not the criterion for `project`** — a mastery course may also produce
artifacts, where the artifact is evidence of understanding. `project` requires the artifact to be
judged by an **external judge that does not listen to explanations** (running in reality / an OJ
grader / a Kaggle private leaderboard). `praxis` sits outside the system like `project`; the
difference is that its judge is **not reproducible**, so it must carry a disclaimer.

`Mastery + learning_mode: project` is still a Mastery Course. A Project Goal/Milestone is a Project Plan node, not `learning_mode: goal`.

### 2.1 ContentGroup / Lesson / Exercise

- Lesson and Exercise are near-sibling LearningActivities inside a Course: the former advances through explanation, reading, examples and confirmation; the latter through sustained problem work, submission, feedback, correction and retest. Neither owns the other.
- `lessons/lessonNN/lessonNN.md` is the Lesson main carrier; `exercises/exerciseNN/exercise.md` is the Exercise main carrier, with `problems.md`, Attempts and Reviews as its problem and evidence structure.
- A ContentGroup connects the two activity kinds along `Book -> chapter -> section/knowledge group`. The course-level `activity_map.md` is the connection source of truth; a leaf declares only its own ContentGroup and holds no ownership pointer to the other.
- `progress.md`'s `current_activity / current_activity_id / resume_path / activity_position` point at the single foreground Lesson or Exercise; `current_lesson` has been retired from the active contract, and historical Lesson context is resolved from ledger events and ContentGroup relations. The full shared loop and the Skeleton release contract are in `learning_activity_model.md`.
- An ExerciseUnit distinguishes `source_order` from `teaching_sequence`: the former faithfully preserves the textbook's problem-number order, the latter the current teaching execution route. The teaching route may be adjusted for prerequisites and the student's real evidence, but never changes a problem number, never crosses a content group, and must record the reason for the adjustment.
- A lesson/exercise local idea keeps its context; core-content thinking with a chapter through-line, a cross-activity connection, or later reuse value is then distilled into `10_student/profile/course_reflections.md` with the local source pointer retained.
- An aggregated entry must distinguish the ownership of evidence: what the student explicitly said is written as "the student's own words / the student's self-correction", while the teacher's formalization, extension and explanation are written as "teacher addition / teacher distillation". The two may sit side by side but must never be merged into shared "own words".

### 2.2 ExerciseProblem / Attempt / Review

- An ExerciseProblem is a stable problem entry in `exercises/<EXERCISE_ID>/problems.md`; the textbook remains the source, and copying problems to build a second question bank is forbidden.
- An Attempt is one real submission batch and may contain several problems and several original images; its carrier is `attempts/ATdddd/attempt.md`, and its full identity is the Course, the Unit and the local Attempt ID.
- A student idea is optional first-hand evidence inside an Attempt: it stores only the solving impressions, associations or strategy the student expressed explicitly, is never inferred and written on their behalf by the teacher, and establishes no independent stable ID.
- A Review is the per-problem grading of one Attempt plus that round's reasoning observation; its carrier is `reviews/RVdddd.md`.
- A "student idea" belongs to the Attempt; a "reasoning observation" belongs to the Review. The former is the student's own words, the latter the teacher's judgement, and neither may overwrite the other. One student idea does not automatically become a ReasoningPattern.
- `exercises/exercise_thoughts.md` is the in-course index aggregating exercise ideas across Exercises; it is not a new source of truth for the student's own words. It deduplicates by the `Exercise / Attempt / Problem` source tuple and stores a short excerpt, index tags and later use; the original wording is still governed by the Attempt.
- A Review only cites mistake/question/reasoning evidence and does not own those feedback ledgers.
- `profile.md`'s `exercise_hint_gate` stores whether the student enabled the hint gate; when enabled, the reply intent is checked by `t2ag_hint_gate.py` first. A conceptual question is answered as the concept asked and is never applied to the current problem automatically; a direction, named material and a full explanation each require the student's explicit authorization. An Attempt stores the gate snapshot and the highest help exposure, and never lets a conceptual Q&A or a teacher's over-level hint pose as the student's independent evidence.
- KnowledgePoint and AbilitySummary are not yet 0.2.0 activity objects. OCR verification is provenance evidence for a SourcePageAsset, not an independent LearningActivity or student mastery.

### 2.3 Textbook source and lesson preparation

Textbook source evidence is held persistently by the Course/Book; a Lesson holds only the
consumption scope, the navigation and the preparation receipts. The same page asset may be
referenced by several Lessons, but no Lesson's progress, Snapshot or student learning evidence may
ever be shared.

- **SourceDocument**: the original textbook document and its version, held by the Course/Book, and the final authority for the textbook source; it does not lapse when a Lesson closes.
- **SourcePageAsset**: the persistent logical asset of one physical page in a SourceDocument version, anchoring its source location, its OCR and its verification provenance; "verified" does not mean the student has studied or mastered it.
- **LessonScope**: the versioned, immutable ordered set of page assets a Lesson owns, and the scope truth that version must consume. For a normal document it is a contiguous 5–8 pages including the current page; a short book with fewer than 5 available pages is fixed at all available pages. A page turn or a widening creates a new Scope version and never rewrites the old one.
- **TeachingWindow**: the mutable runtime view owned by Lesson Progress, projecting the current page, the relative display and the residents of the current LessonScope; it is not a second, independently trimmable teaching scope.
- **LessonMap**: the navigation map a Lesson derives per Scope version, which must cover every SourcePageAsset in the current Scope; it owns no mastery, completion or student confirmation.
- **LessonPreparationSnapshot**: the immutable preparation receipt a Lesson owns, binding one Scope version, its LessonMap and the per-page consumption receipts. A Scope change requires a new Snapshot; an old Snapshot is never modified in place and is never treated as student learning evidence.

The relation chain is `SourceDocument -> SourcePageAsset`, `LessonScope -> ordered page assets`,
`TeachingWindow -> a projection of the current Scope`, `LessonMap -> full Scope coverage`,
`LessonPreparationSnapshot -> Scope + Map + consumption receipts`.

## 3. Group

A Group is a capacity composition, not a course lifecycle:

```text
30_group/<GID>/
  plan.md
  calendar.md
  review.md
  bindings/
```

- plan: members, budget boundaries, cross-course interfaces, the activation gate;
- calendar: an executable schedule and decidable group-closing thresholds;
- review: cycle evidence, debt handling and user confirmation;
- binding: the elastic execution relation of one course; it owns neither the course body nor its progress.

A course outside the group may stay ongoing; joining or leaving a group never changes a course
lifecycle automatically.

## 4. Teacher

`20_teacher/T00X.md` is a stable template, and `20_teacher/overlay.md` is the explicit override
for the current student and course. An overlay may change tone, entry point, pace and feedback
frequency; it must never change the factual standard, the required course content, or a student
confirmation gate.

- **TR01**: the teacher-identity factual standard, generated by `t2ag_state_refresh.py` and validated by `t2ag_doctor.py`. Semantic definition: `overlay.md`, the teacher factual standard section. A GENERATED literal; never hand-written. Format: `"TR01 -> {teacher_id}"`.

## 5. ActivityRecord

An ActivityRecord holds a low-governance, pausable activity not yet promoted to a formal course:

- ID: `AR-NNNN`
- path: `10_student/activities/<activity_kind>/AR-NNNN_Title.md`
- `activity_kind` is decided by a controlled registry; 0.2.1 initially registers only `reading`
- it owns no course progress; after promotion it keeps only a link to the Course and the history.

## 6. Engagement

An Engagement holds a sustained real-world practice and its evidence:

- ID: `EG-NNNN`
- carrier: `10_student/engagements/EG-NNNN_Title/engagement.md`
- required: `type`, `engagement_id`, `status`, `governance`
- `governance: external` requires a `governance_source`
- evidence stores an evidence index only and never substitutes for an external discipline or source of fact.

## 7. State and feedback ledgers

- memory / learning path: caches generated from the masters;
- mistake bank: the stock of knowledge errors;
- question bank: the stock of questions, with states `open / answered / closed`;
- problemlog: the flow ledger of system problems, settled once distilled into a playbook;
- changelog / journal: append-only history, outside the retire loop;
- trade journal: T2AG learning and process evidence; it owns neither Trading-OS discipline nor execution facts.

## 8. Registry

`70_tools/artifact_registry.json` holds stable artifact IDs:

- active: the canonical must exist and be globally unique;
- tombstone: an old composite, or an artifact absorbed by a survivor, which must carry `successors` or `alias_to`;
- archived: readable historical text, taking no part in active routing;
- redirects: append-only, and must reach a canonical, tombstone or archive record in one hop.

## 9. Invariants

1. `main/` has exactly nine numbered domains, plus `bin/`.
2. An old 0.1.x active domain must never be revived.
3. Each instance course has at most one `course.md` and one `progress.md`.
4. There is exactly one active group; a Skeleton may have zero.
5. The course members of the active group must exist, and a planned/completed/dropped course must never be mistaken for active capacity.
6. A stable ID is never re-created because of a rename after migration.
7. A GENERATED cache must never lead or override the source of truth.
8. Lite derives from Main only; a Skeleton contains no real instance data.
9. The problems an Attempt cites must belong to the same unit; a Review must cite a real Attempt and must never exceed that Attempt's problem set.
10. The Lesson/Exercise connection of a textbook course must be managed by the course-level `activity_map.md`; the ContentGroup declarations of both activity leaves must agree with that table, and no reference may dangle.
11. Main, Skeleton and Lite must all carry the same set of Course/Lesson/Exercise initialization templates; a Skeleton holds no real instance but must not lack the system capability needed to create and run both activity kinds.
