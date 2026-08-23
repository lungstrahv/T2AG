# The group-transition ritual (group_transition)

**Protection level**: core-playbook

> **Trigger**: when the final evaluation is complete, and only then.
> **Definition source**: `main/50_playbook/course_group_rules.md` §5.

---

## The five-step flow

1. The old group's status becomes archived, and the final evaluation table becomes the group-closing archive
2. The new group's file is **created only at this moment** (a pre-plan table must never be filed early — this prevents zombie files): the member table, the tracks, the budget, this term's goals
3. Write the status, the members, and the current course into the new group's `plan.md`; it is the sole source of truth for capacity
4. Handle the course lifecycle and the capacity combination separately: a continuing course stays ongoing; a finished one becomes completed;
   a course the user explicitly ended becomes dropped; an ongoing course that did not join the new group merely loses its reserved capacity and is not automatically paused
5. Run the state refresh to generate the memory/learning_path caches, then run doctor → record it in the changelog

---

## A pre-plan table ≠ a group file

- **A planned group file / pre-plan table** is a draft of the next capacity combination; it may be written at any time, it does not change any course lifecycle, and it consumes none of the current budget.
- **An active group file** is a formal capacity commitment; only one group may be active at a time.
- A course in a planned group may be planned or ongoing; on activation, the member courses must be verified as actually executable, and a planned course moves to ongoing only after the user confirms.
- The essential difference: planned is intent, active is a capacity commitment; neither is the same as a course lifecycle.

---

## Authority and the boundary of suggestions

- The system may propose a group change or a frequency reduction based on actual duration, learning capacity, a failed start, a deadline, a dependency, or a project constraint.
- A change to group membership, a course lifecycle change, and a budget reallocation must all be confirmed by the user; none may be executed automatically.
- An ongoing course outside the group may be advanced temporarily by the user, but it must never consume the active group's budget silently.

---

## G's course reference contract

G's `course_members` references the stable `COURSE_ID` directly; each ID corresponds uniquely to
`main/40_course/<COURSE_ID>/course.md` and `progress.md`. The Case,
CourseDefinition/CourseRun, and `CR-<case_id>-*` wrappers must never be restored.
