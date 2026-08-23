# New course initialization

**Protection level**: core-playbook

## Preconditions

- Create one only when the user explicitly wants a course built, or a candidate course brought into T2AG.
- The course directory *is* the current instance's course; no Case, Definition/Run, or student-number wrapper is created.
- Creating a course is not the same as joining the active group. A capacity change goes through the group activation / group-closing flow separately.

## Directory

```text
main/40_course/<COURSE_ID>/
  course.md
  progress.md
  activity_map.md      # created when a textbook course first establishes a Lesson/Exercise
  lessons/
  exercises/
  mistake_bank.md
  question_bank.md
  book/
```

The structure and fields are instantiated from `main/40_course/_templates/course/`; the Core semantics
are in `main/00_core/learning_activity_model.md`. Lesson and Exercise are sibling learning activities,
and the templates must ship with the Skeleton — they must never be rebuilt from the current model's
recollection.

## The generation entry point

```powershell
python -B main/70_tools/t2ag_init.py new-course --course-id <ID> --name <name> `
  --driver textbook --lifecycle ongoing --entry lesson|exercise --teacher Tddd `
  --source-language <en|zh-CN|...> `
  --source-scope <scope> --position <stop> --date YYYY-MM-DD
```

`--source-language` is required and has no default: it is the language of the course's
own materials, and the T001 §9 terminology discipline reads it to decide which terms
keep their original form. A wrong value fails silently — the teacher goes on obeying
the discipline, just against the wrong language — so it is asked once, at creation.

With a textbook driver and `--entry exercise`, `--source-document`, `--source-locator`
and `--problem-text` must all be supplied, so the tool can create the persistent proofread problem
source, register the artifact, and write the SHA into `problems.md`;
missing any one of them refuses generation, and an empty problem source may never be used as a
placeholder. `--lifecycle planned` must be paired with `--entry none`.

The steps below are the contract that command implements, for human review and reverse lookup; they are
not an instruction for the model to transcribe files by hand.

## Steps

1. Validate the stable course ID per `naming_conventions.md` and confirm no directory with that ID exists.
2. Create `course.md`:
   - `type: course`
   - `course_id`
   - `school_course_code`, `name`, `course_type`, `default_driver`, `prerequisites`,
     `status: active`. The status here means only that the course definition is usable; the student
     lifecycle is written in progress alone.
   - The textbooks, the teaching principles, and the course milestones; do not write a milestone's
     current status.
   - Do not write the student's current stop.
3. Create `progress.md`:
   - `type: course_progress`
   - `course_id`
   - `lifecycle_status: planned | ongoing` (the full lifecycle vocabulary also includes paused/completed/dropped; see `progress_tracking.md` — a new course starts only from planned/ongoing)
   - `course_driver: textbook | goal | project | praxis`
   - `truth_scope: course_lifecycle,course_frontend,activity_position`
   - A planned course writes only `updated`,
     `progress_nodes_status: lazy_on_activation`, and the next action; it must never pre-fill
     `current_activity / current_activity_id / resume_path / activity_position`.
   - An ongoing course creates its first Lesson or Exercise at the real entry point, then writes
     atomically `current_activity: lesson | exercise`, `current_activity_id`, the canonical
     `resume_path`, `activity_position`, the completion node, the checkpoint, and the next action;
     the target must exist first. An Exercise first start does not write `current_lesson`, and the state
     refresher's
     "Lesson context" must come out as "none / no path" from the ledger/ContentGroup — it must never be
     inferred, and `lessons/none/none.md` must never be pre-created.
4. Create `activity_ledger.md` with `truth_scope: activity_lifecycle`; a new course starts from an empty
   ledger, and a genesis ALE is appended only when an activity is really created — planned activities are
   never pre-created.
5. Create the question bank V2, with statuses limited to `open / answered / closed`; create the mistake
   bank.
6. Create `book/`, `lessons/`, and `exercises/` from the templates; an empty activity domain is made
   persistent with a `_README.md`.
   - Entering through teaching for the first time: create `lessons/lesson01/lesson01.md`; a textbook
     course also initializes
     `book/primary/source_assets/` (the manifest template) plus the lesson's `preparation/` and
     `lesson_map` templates —
     see `source_page_assets.md`; page assets go through the preparation Snapshot, never the legacy path.
   - Entering through exercises for the first time: create `exercises/exercise01/exercise.md`,
     `problems.md`, and the empty attempts/reviews notes; a textbook-driven course must additionally
     establish the persistent proofread problem source inside the Course `book/` and register the
     artifact first, with `problems.md` recording its path, locator, and SHA.
   - A textbook course creates `activity_map.md` and registers the existing Lessons/Exercises by
     ContentGroup; an activity that does not exist is written `—`, and a real activity or evidence is
     never pre-created.
7. Add one row to the single "Course-to-teacher mapping" table in `20_teacher/overlay.md`; the "Teacher
   template" cell must be written exactly as `` `main/20_teacher/Tddd.md` `` — never as a separate quick
   reference, and never inferred from prose about style.
8. Update the target group's plan/calendar only if the user explicitly allocates capacity; otherwise
   leave it unallocated.
9. Run:

```powershell
python -B main/70_tools/t2ag_state_refresh.py --write
python -B main/70_tools/t2ag_state_refresh.py --check
python -B main/70_tools/t2ag_doctor.py --profile runtime
```

## Forbidden

- Do not create a second progress-node file; the nodes belong in `progress.md`.
- Do not stuff course body text or progress into a binding.
- Do not add a planned course to the active group automatically.
- Do not create a `.venv`, install dependencies, or download a textbook automatically; obtain the user's
  authorization first when they are needed.
