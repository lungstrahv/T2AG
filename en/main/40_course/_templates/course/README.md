# Course initialization templates

This directory is a system release template, not a real course instance. On first initialization or when
adding a course, copy the files you need per `main/50_playbook/new_course_init.md` and replace every
uppercase placeholder with a real ID.

Lesson and Exercise are sibling learning activities; which one is created first depends on the student's
real entry point into the material.
A `.template` must never be copied with its placeholders left in, and an Attempt, a Review, or thought
evidence must never be pre-created.
A textbook Exercise must additionally copy `book/primary/verified_excerpts/source.md.template`, register
the artifact after proofreading, and have `problems.md` reference it by path, locator and SHA; a Lesson
cache must never be referenced.
A new Attempt's `HINT_GATE_MODE` must be the snapshot of `exercise_hint_gate` from the profile at creation
time.

Created when the course is created: `course.md`, `progress.md`, `activity_ledger.md`, `question_bank.md`,
`mistake_bank.md`, plus `activity_map.md` and `book/README.md` for a textbook course.

Created lazily: `lessons/lessonNN/lesson_thoughts.md` and `exercises/exercise_thoughts.md` are
instantiated from their templates only when a student's own formulation really appears; they are never
pre-created as empty files at course creation. The templates ship with the release so the current model
does not have to invent a schema on the spot — not because an instance must exist in advance.

The course-group templates are not in this directory; see `main/30_group/_templates/group/`.
