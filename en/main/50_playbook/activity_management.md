# ActivityRecord management

**Protection level**: playbook

An ActivityRecord is for a low-governance, pausable activity that has not yet become a formal course.

## Creation

The path (in 0.2.1 the only legal kind at first is `reading`):

`main/10_student/activities/<activity_kind>/AR-NNNN_Title.md`

The minimal frontmatter:

```yaml
---
type: activity_record
activity_kind: reading
activity_record_id: AR-NNNN
title: Title
record_status: recording
upgraded_to_course: —
created_at: YYYY-MM-DD
---
```

The ID shares one global numbering space across every kind under `10_student/activities/`, increasing
monotonically, never reordered and never reused.
Adding a kind requires changing the schema/registry/Doctor first; a directory must never be created
arbitrarily. The file holds facts, short notes,
and the upgrade judgement; it never holds a formal course's stopping point.

One stable reading intent uses exactly one ActivityRecord; an AR is not created per book. One intent may
reference several books, and
ordinary reading must never be upgraded automatically into a Course, an Engagement, or an R binding just
because a book title or a course association came up.

## States

- `recording`: being recorded continuously;
- `paused`: paused by the user;
- `archived`: finished and no longer advancing;
- `upgraded`: upgraded to a Course, with `upgraded_to_course` filled in.

## Upgrading

1. Confirm the stable course ID and scope with the user.
2. Create the Course per `new_course_init.md`.
3. Merge the reusable content into `course.md`, and write the current state into `progress.md`.
4. Mark the ActivityRecord `upgraded` and point it at the Course; do not copy later course progress into it.
5. Refresh the state and run doctor.

An ActivityRecord does not join a group automatically and consumes none of a group's budget.
