# Session close and manual archiving

**Protection level**: core-playbook

`progress.md` owns the Course lifecycle, the single foreground and the exact stopping point;
`activity_ledger.md` owns the Lesson/Exercise lifecycle, pending/CLR, aliases and statistics. A
close must be routed by the explicit foreground and go through `activity_close.py`'s immutable
plan plus transactional apply; the retired `current_lesson` must take no part in routing or
write-back.

## The close domain tree and applicability

A full close checks every node first and then aggregates the applicable ones; it does not require
every lesson to invent content for every node. Each leaf node may only be:

- `applicable`: this lesson really has the corresponding fact, so a student-facing summary is mandatory, with evidence where needed;
- `not_applicable`: this lesson did not trigger it, so a reason is mandatory, and it does not block Lesson completion;
- `missing`: not yet checked, or the expected content is absent — kept as an explicit gap, and it may block `completed`.

The five presentation preferences control presentation only. They do not decide whether a node is
applicable, and they can never create, delete or replace evidence. The student-visible teaching
retrospective aggregates only the `applicable` items; the pending body simultaneously stores the
per-node status of the whole tree, so nothing can be checked off as missed.

The teaching retrospective has two delivery surfaces, and neither may be skipped: the same
retrospective must be written into the Lesson main carrier as a durable record, **and** expanded
directly into the student's current conversation before the close. Giving only a file path, a
link, a summary, an event ID or a SHA does not count as conversational presentation. The student
may correct it after reading. With no revision, the student replies "close" (or `结课`) to confirm
the single `completed` pending just shown. Binding the event ID, body SHA, result and presentation
SHA is the system's job and is never something the student has to transcribe. When the result is
`closed_incomplete`, they must say explicitly "close as incomplete" (or `以未完成状态结课`). If
nothing was shown first, several candidates exist, drift occurred, or a different version was
shown, the short intent is void and the write-back is refused.

```text
Lesson full close flow
│
├── 0. Freeze the close scope
│   ├── confirm the current Lesson
│   ├── confirm the textbook / knowledge scope
│   ├── exclude the next Lesson's content
│   └── confirm whether the paired Exercise closes independently
│
├── 1. Collect learning evidence
│   ├── teaching and Q&A records
│   ├── the student's raw answers
│   ├── the student's self-corrections
│   ├── checkpoint / completion node
│   ├── Attempt / Review
│   └── question / mistake / thoughts
│
├── 2. Teaching retrospective
│   ├── 2.1 actual teaching process
│   │   ├── what was actually taught
│   │   ├── the teaching sequence actually used
│   │   ├── what was expanded or skipped
│   │   └── how it differed from the plan
│   ├── 2.2 course content completion
│   │   ├── completed content
│   │   ├── unfinished content
│   │   ├── out-of-scope content
│   │   └── the boundary with the next Lesson
│   ├── 2.3 knowledge absorption (student-facing)
│   │   ├── how the student understood it at first
│   │   ├── which reasoning difficulties appeared
│   │   ├── which example or follow-up question caused the shift
│   │   ├── how the student self-corrected
│   │   ├── whether they can finally restate or transfer it independently
│   │   ├── current mastery
│   │   └── weak points still needing retest
│   ├── 2.4 student course content feedback (about course content only)
│   │   ├── which content was valuable
│   │   ├── which content was hard to follow
│   │   ├── whether the content order suited them
│   │   ├── whether the examples worked
│   │   ├── what was redundant or missing
│   │   └── how the student would like this course adjusted
│   ├── 2.5 teacher teaching reflection
│   │   ├── which explanations worked
│   │   ├── which phrasing was over-compressed
│   │   ├── where too much help was given
│   │   └── how to improve next time
│   └── 2.6 follow-up learning transition
│       ├── spaced retests
│       ├── the entry point of the next Lesson
│       └── the student's ideas that need consuming later
│
├── 3. Completeness determination
│   ├── is the evidence sufficient
│   ├── do blockers exist
│   ├── is a scope change confirmed
│   ├── recommend completed / closed_incomplete
│   └── the reason for the determination
│
├── 4. Student check and revision
│   ├── the Lesson main carrier stores the full teaching retrospective
│   ├── the full student-facing retrospective is shown directly in the current conversation
│   ├── the student corrects a fact or an assessment
│   ├── a pending revision is generated where needed
│   └── the final body awaiting confirmation is frozen
│
├── 5. Terminal confirmation
│   ├── pending event ID
│   ├── body SHA
│   └── completed / closed_incomplete
│
└── 6. Write-back and verification
    ├── ledger terminal event / CLR
    ├── progress clears the current activity and the page window
    ├── state refresh
    ├── runtime doctor
    └── read back the actual write results
```

Feedback is routed by its object; system experience must never be mixed into course-content
feedback:

```text
Feedback the student expresses
├── about the subject content, difficulty, ordering or examples
│   └── Course-content Feedback -> teaching retrospective 2.4
└── about the interface, startup speed, agents, ledgers or input method
    └── System Feedback
        ├── profile preferences
        ├── problem log
        └── system improvement tasks
```

## 0. The full Exercise close tree

Exercise and Lesson share the same close transaction—pending, student review, terminal confirmation,
transactional write-back—but use separate close-tree variants selected by `activity_type`. Passing a
Lesson section to Exercise, or the reverse, is rejected as an unknown section.

Exercise-only sections are:

- `actual_exercise_process`: problems attempted, teaching reordering versus source order, hint-gate
  use, and plan differences;
- `question_coverage`: account for every problem and subpart against textbook `source_order`, not the
  freely reordered `teaching_sequence`;
- `mastery_ledger`: summarize existing Attempt/Review verdicts only; close creates no new rating;
- `byproduct_audit`: unresolved discussion chains, retest hooks, idea routing, and Attempt/Review
  completeness. Routed byproducts do not block `completed`; only unfinished problems and unconfirmed
  scope changes are blockers;
- `learning_transition`: spaced retest, return to the Lesson trunk by default, and later consumption
  of student ideas. Routing directly to another exercise must be explicit.

The student explicitly initiates close. The system presents all four accounts; existing mandatory
evidence and blocker rules decide completeness. Enforcement: `main/70_tools/activity_close.py`.

## 1. Resolve the single activity before closing

Run the read-only route first:

```powershell
python -B main/70_tools/t2ag_activity.py --course <COURSE_ID> --intent close
```

If the command exits non-zero, stop the close and repair `progress.md`. The
`activity_write_target` in the output is this round's single activity main carrier:

- `lesson`: write `lessons/<current_activity_id>/<current_activity_id>.md`;
- `exercise`: write `exercises/<current_activity_id>/exercise.md`, and write the Attempt / Review separately once there is a real submission and grading;
- the historical Lesson context is resolved from the ledger/ContentGroup and is not a default write target;
- a planned course has no current activity and must not be closed.

## 2. The mandatory transaction shared by Micro and full close

**Both a Micro close and a full close must complete atomically** over the write set each declares;
only an Activity close the user explicitly starts enters `ongoing -> pending_close`. An ordinary
course switch, crossing midnight, a session save, a chat interruption and a Micro save never
automatically produce pending/terminal/pause. A formal close must put the ledger, progress, the
first-prompt marker and the GENERATED cache in one transaction; any post-check failure rolls the
whole thing back.

### Step 1: fix this round's process evidence first

Update the foreground stopping point and next_action in
`main/40_course/<COURSE_ID>/progress.md` according to what really changed, but never write the
Activity lifecycle into progress or the activity main file:

- `updated`;
- `current_activity`, `current_activity_id` and the canonical `resume_path`;
- `activity_position`, the completion node, the checkpoint and its `queued / arrived / pending / confirmed / archived` status;
- the first thing next time, and this session's teaching summary;
- an active progress never writes `current_lesson`; the historical Lesson context is resolved from ledger events only.

### Step 2: write the current activity's main carrier

- Lesson: append this session's teaching, Q&A, confirmations and wrong attempts. The "Lesson last stopping point snapshot" is local evidence, does not use `T2AG_GENERATED`, and does not override progress.
- Exercise: update the current problem, the exact stopping point and the evidence pointers in `exercise.md`; create an Attempt per `exercise_evidence.md` only when there is a real submission, and a Review only when there is real grading. A new Attempt also stores the `hint_gate` snapshot at creation, the highest `assistance_level`, and the real authorization/contamination record. A conceptual Q&A that stays scope-only does not raise the help level; when key structure was leaked without authorization, it must not count as independent mastery.
- Both activity kinds write only their own body. Cross-activity relations are written only in `activity_map.md`; **an Exercise close must never be done casually** to a historical Lesson.

### Step 3: close the ledgers this round really produced

- questions are written or merged into `question_bank.md`;
- clear knowledge errors and formal retests are written or merged into `mistake_bank.md`;
- a student's original images for an Exercise go only into that Attempt's `assets/`, never into a teaching-figure directory;
- ideas the student expressed explicitly are routed to Lesson thoughts or to Attempt/Exercise thoughts; with no real evidence, no empty object is created.

### Step 4: generate the pending, decide strictly, and write back transactionally

First generate the immutable pending body with
`activity_close.py --plan-pending --plan-out <new-file>`. The new body uses
`activity_close_body.v2`, binding the scope, the evidence collection, the full teaching
retrospective tree, the student-facing summary of applicable items, the five knowledge states,
blockers, the preference snapshot, the event ID and the body SHA. An old v1 pending is readable,
but on any revision it must be upgraded to v2; never keep generating three sibling
`actual_review / student_feedback / knowledge_absorption` blocks. A terminal decision must first
display the exact `pending_event_id`, `body_sha256` and `result` — but those are the system's
integrity binding, not homework for the student to copy. Once the full retrospective and the tuple
have been shown in the current conversation and the single pending has not drifted, `completed`
may be confirmed directly by the student replying "close" / "confirm close"
(or `结课` / `确认结课` / `愿意结课`); an incomplete state must be answered with
"close as incomplete" (or `以未完成状态结课`). An old conversation, a standing delegation, a
receipt, a policy, a model recommendation, and an unbound "ok / go on / sure" are all void.

Before requesting terminal confirmation, the pending body's `learner_visible_retrospective` must
be rendered into the full student-facing text and sent directly into the current conversation,
with the presentation SHA computed at the same time. After the student expresses a short close
intent, the tool binds that intent to the tuple already shown and to the terminal result; if the
retrospective is revised at all after being shown, the old presentation SHA and the old intent
expire immediately and the revised full text must be shown again.

- Revision: append `pending_close -> pending_close`; the old pending is not overwritten;
- Refusal: append `pending_close -> ongoing`; no CLR is generated;
- Terminal: `--plan-decision` must bind the pending ID, the body SHA, the result, `user + direct_user` and the current round's authorization source; only after apply is a CLR generated carrying the `valid_direct_user` program state;
- **a receipt records only authorization evidence** and can never create authorization; a plan may be installed only by a receipt matching the payload/file SHA and the exact direct-user text.

### Step 5: verify what landed on disk

```powershell
python -B main/70_tools/t2ag_state_refresh.py --write
python -B main/70_tools/t2ag_state_refresh.py --check
python -B main/70_tools/t2ag_doctor.py --profile runtime
```

`--write` cannot be skipped and must come before `--check` — the same order as
`progress_tracking.md` §3, "the execution order is fixed at
`progress.md -> --write -> --check -> doctor`". Since P-0058, `--check` covers the checkpoint
projection in the `progress.md` frontmatter, so if this session added or closed any checkpoint,
skipping `--write` guarantees this step reports `[FAIL] generated cache drift` — and this step's
criterion is precisely "state has no drift".

Then re-read progress, the `activity_write_target`, the `mandatory_write_targets` in the command
output, and the `conditional_write_targets` that actually changed this round. Only when every
write reads back, state has no drift, and the runtime doctor is `0 FAIL` may this close be
declared closed. **Read back only these actual targets**, never reloading all history for the sake
of verification. When the current activity is an Exercise, also confirm that no historical Lesson
was modified by this transaction.

The write-back means **the previous L0 context packet expires immediately** for this session; if
the same class continues after the close, regenerate one per `context_packet.md` rather than
editing or reusing the old packet.

### Step 6: handle working pages and the classroom handoff

- Working pages are in the default close scope only when the current activity is a textbook Lesson.
- Keep the needed window while the Lesson continues; when closing the Lesson or switching to an Exercise, the physical cache may be cleaned, but the Lesson-specific page window fields must be handled correctly at the same time.
- An Exercise never reads or writes a historical Lesson's working pages, even if progress temporarily retains old page fields.
- If an active handoff matches this `course_session`, verify the formal write-back against its `close_condition`; only after that verification passes is it marked `resolved` with the verification result registered. A project-level construction handoff is not closed by a classroom close.

## 3. Micro close

Micro close applies to a five-minute warm-up, a short retest, a manual "save progress", or the
student stopping midway. It atomically saves only the real process evidence, the foreground
stopping point and next_action; it produces no pending, no CLR and no automatic pause, and it may
skip optional syntheses such as course reflection or composition-level summary that this session
produced no new evidence for.

A Micro close creates no debt and writes no deferred marker. If it cannot complete the mandatory
transaction for lack of information or permission, then it is not a closed Micro close: keep or
create a matching active `course_session` handoff naming the gap and the recovery entry point.

## 4. Additional synthesis in a full close

Beyond the mandatory transaction, add these per their real triggers:

1. Check `lesson_thoughts.md` and `exercise_thoughts.md`; when the distillation threshold is met, update `10_student/profile/course_reflections.md` and keep the source backlinks.
2. Update `reasoning_patterns.md` only after a repeated cross-problem pattern reaches the evidence threshold.
3. Composition-level frequency, time deviation and debt handling go into the group `review.md`; single-lesson mastery is never copied there.
4. When the cloud bridge is `paused`, skip the mobile projection; a cloud handoff can never override the local progress.
5. **The learning day is bounded at 04:00, not by the calendar day**: progress wrapped up before 04:00 local belongs to the previous learning day. The canonical rule and the scope split (learning progress follows the 04:00 learning day; system logs / monthly journals / release forensics follow the calendar date) are in `progress_tracking.md` §3.5. This section is only a consumer pointer and **does not repeat the text**.

## 5. Manual archiving

When the student says "save progress", perform a Micro save immediately; the same class may
continue afterwards. Never change only memory, the learning path or a historical Lesson, and never
read "save" as a close confirmation.
