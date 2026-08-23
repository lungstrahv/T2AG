# Group initialization templates

This directory is a system release template, not a real course-group instance. On first run, or when
creating a course group, copy the files you need into `main/30_group/Gdd/` per
`main/50_playbook/course_group_rules.md` and `group_transition.md`, and replace every uppercase
placeholder with a real value.

A newly created course group defaults to `status: planned`. Turning it `active` requires a separate group
activation review; `active` must never be written directly at creation — one instance permits only one
active group.

- `plan.md`: the member combination, the activation gate, and the capacity boundary. Course progress is
  still governed solely by each course's `progress.md`.
- `calendar.md`: the capacity draft. A planned group's calendar produces no course progress and changes no
  course's lifecycle.
- `review.md`: the combination-level review and the closing evidence. A planned group only reserves the
  place and produces no completion record.
- `bindings/_README.md`: makes the empty binding domain persistent. With no elastic execution binding,
  keeping this note file is enough.

A `.template` must never be copied with its placeholders left in; course body text or course progress must
never be stuffed into a binding; and a planned course must never be added to an active group
automatically.
