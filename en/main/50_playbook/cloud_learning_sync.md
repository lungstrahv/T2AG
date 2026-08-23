# Cloud learning and local write-back protocol (cloud_learning_sync)

**Protection level**: playbook

> **Protocol identifier**: `T2AG-CLOUD-1`
>
> This flow is for teaching environments that cannot modify the local repository directly:
> a ChatGPT Project, a phone chat, and the like. The cloud side teaches and produces events
> awaiting synchronization; the local T2AG adjudicates, writes back, and verifies with doctor.

T2AG cloud synchronization has two channels, and they must never be written into each other:

| Channel | Local → cloud | Cloud → local | Purpose |
|---|---|---|---|
| Teaching-state sync | `t2ag_mobile_entry.md` / the sync baseline | `T2AG_PROGRESS_RECEIPT` / `T2AG_SESSION_CLOSE` | node progress, questions, mistakes, mastery evidence |
| Component-change sync | `T2AG_CLOUD_CHANGE_DIRECTIVE` | `T2AG_CLOUD_HANDOFF` | rules, prompts, templates, mirrors, cloud-side component edits |

## 1. The four authority layers

| Layer | Role | Authority boundary |
|---|---|---|
| local `progress.md` | Course lifecycle, the single foreground, the exact stop | a cloud record must never overwrite it directly |
| local `activity_ledger.md` | Activity lifecycle, pending/CLR, aliases and statistics | a cloud record must never overwrite it directly |
| the cloud sync baseline | a read-only projection of one local state | identified by `base_state_id`; proves only the state at export time |
| `T2AG_SESSION_CLOSE` | teaching events after that baseline, awaiting write-back | in the cloud, `sync_status` may only be `pending` |
| `t2ag_mobile_entry.md` | the phone-side fast-recovery cache | not an independent source of truth; must not override local state or a valid event block |

A full text mirror is likewise only a read-only snapshot. It may supply rules, lesson and
source-material context, but it must not override a newer sync baseline or a valid event
block. The cloud model must never claim it has modified a local file, run doctor, or completed
a synchronization.

### 1.1 Cloud project mode and identity routing

`t2ag_mobile_entry.md` must declare `cloud_project_mode`, and only these two modes are allowed:

| Mode | Purpose | Identity source |
|---|---|---|
| `personal_instance` | the personal cloud classroom of an instantiated student | a synchronized read-only projection of `main/10_student/profile/profile.md` and `main/20_teacher/overlay.md` |
| `generic_skeleton` | a fresh install, a template demo, or the public skeleton | the empty profile template; teacher unconfigured or defaulting to T001; no instance course progress may be loaded |

- In `personal_instance`, the student ID, the teacher role and the template mapping must come
  from a mobile entry carrying a `base_state_id`; a full text mirror, a skeleton example or a
  historical lesson may only supply context and must never rewrite identity backwards.
- A teacher template number is not a personal identity. Write "teacher role TRxx in this course
  uses template T00x"; never treat a template number as a real teacher entity.
- When the mode is missing, an identity field is missing, or the materials contradict each other,
  identity stays `UNKNOWN/UNASSIGNED` and a minimal confirmation is requested; never guess from
  course examples, from lite, from historical logs, or from the skeleton.
- `generic_skeleton` must never inherit a `personal_instance` student profile, course stop, or
  teacher mapping.

### 1.2 The instance-level end-of-message marker (anti-impersonation; record the mechanism, not the value)

A `personal_instance` may agree on an **instance-level literal end-of-message marker**: an ordinary
cloud teaching reply appends that marker on its own line after the body, as a lightweight
anti-impersonation signal about where the reply came from.

- The **value** of the marker exists only in instance files (`t2ag_mobile_entry.md` and the Project
  Instructions generated from it); it is a shared secret between the instance and the cloud Project.
- The protocol layer, the `cloud_instructions_template.md` template, the skeleton, and every
  open-source surface **never record any value**; once a value reaches a public carrier it is
  considered burned and must be rotated at the next baseline export.
- The marker is a literal token, not a filename or a path; the cloud must not try to read, create,
  or infer a file of the same name.
- `generic_skeleton` mode configures no marker; a missing marker does not block teaching, it only
  lowers confidence in the source.

## 2. Cloud session recovery

1. Read the Project Instructions and confirm the protocol identifier is `T2AG-CLOUD-1`.
2. Read `t2ag_mobile_entry.md` for `cloud_project_mode`, the course, the lesson, the exact stop,
   `base_state_id`, the next action, and the identity-routing fields that mode allows.
3. Find the newest valid `T2AG_SESSION_CLOSE` after that baseline; recover in `closed_at` order,
   and count a repeated `session_id` only once.
4. If a state block from an older chat is not visible, do not pretend to have read it; ask the
   student to paste the newest state block, or state explicitly that you are continuing from the
   baseline alone.
5. If the baseline, a state block, a full mirror, or the student's account conflict, pause new
   content and check with the student; never pick one version silently.
6. Before teaching new content, read the uploaded source text, the text-layer PDF, or the current
   supplementary handout; when the required source is missing, state the gap and do not pass off
   model memory as the textbook.
7. Report the recovery point in one sentence and ask whether to continue; teach only after the
   student confirms.

## 3. The cloud teaching gate

- On the phone, advance by default only one concept, definition, theorem, proof step, or worked
  example per turn.
- "Has seen it", "was taught it", or a correct exercise answer is contact/comprehension evidence
  only; it does not automatically mean mastery and does not automatically release the next concept.
- Closing a concept requires at least a student restatement plus the ability to give, judge, or
  explain one positive and one negative example; where a counterexample does not fit, use a
  boundary case or a wrong-method contrast instead. When evidence is insufficient, keep
  `confirmation_state: pending`.
- End every node with a "continue / say it again / ask a question" gate; advance only on an
  explicit "continue".
- When the student writes `Question:` or `Doubt:`, pause all advancement immediately, answer
  first, and record the question in the session-close event block.
- After the student answers an exercise, unless they explicitly say this turn that they have no
  questions, analyze the method from their actual steps and ask whether anything is unclear; when
  process evidence is insufficient, ask them to supply it rather than guessing their reasoning.
- Teaching pace may be adjusted from a state the student explicitly expresses, but never by
  lowering the mastery standard, skipping a lesson, skipping a page, or leaving source text unread.
- The cloud does not produce a ZIP by default; it supplies only what the current teaching needs
  plus the event blocks awaiting synchronization.

## 4. The cloud session-close event block

When a completion node is finished, or the student says "save my progress" by hand, the cloud
first produces a compact receipt; an ordinary checkpoint is saved silently inside the cloud
without interrupting the student point by point:

```text
T2AG_PROGRESS_RECEIPT
- protocol_version: T2AG-CLOUD-1
- receipt_id: CPR-<COURSE>-<YYYYMMDDTHHMMSS+TZ>-<4CHARS>
- produced_at: <ISO-8601 with timezone>
- base_state_id: <id or UNKNOWN>
- course: <course code>
- current_activity: <lesson | exercise>
- current_activity_id: <lessonNN | exerciseNN>
- resume_path: <canonical current activity path>
- lesson_context: <lesson id | NONE>
- receipt_kind: <completion_node | manual_save>
- completion_node_id: <stable id or NONE>
- checkpoint_id: <stable id>
- exact_stop: <page / section / action>
- confirmation_state: <pending | confirmed | not_applicable>
- sync_status: pending
END_T2AG_PROGRESS_RECEIPT
```

The same `receipt_id` may be imported only once. `manual_save` only forces the current stop to be
saved; it must not move a completion node to completed. A normal session close still emits the full
event block below.

When the student says "class is over", "that's it for today", "let's stop here", or "done", or when
the lesson reaches a natural end, the cloud model must emit the following plain-text block. No field
may be omitted; write `UNKNOWN` for an unknown value and never invent one.

```text
T2AG_SESSION_CLOSE
- protocol_version: T2AG-CLOUD-1
- session_id: CLOUD-<COURSE>-<YYYYMMDDTHHMMSS+TZ>-<4CHARS>
- closed_at: <ISO-8601 with timezone>
- t2ag_version: <version or UNKNOWN>
- base_state_id: <id from t2ag_mobile_entry.md or UNKNOWN>
- course: <course code>
- current_activity: <lesson | exercise>
- current_activity_id: <lessonNN | exerciseNN>
- resume_path: <canonical current activity path>
- lesson_context: <lesson id | NONE>
- duration_minutes: <non-negative integer or UNKNOWN>
- source_evidence: <file / page / section actually used, or NONE>
- covered: <explained or attempted content>
- completed: <only content whose confirmation gate is closed>
- confirmation_state: <pending | confirmed | not_applicable>
- pending_checkpoint: <exact unclosed confirmation, or NONE>
- mastery_evidence: <student-produced evidence only, or NONE>
- open_questions: <questions and status, or NONE>
- mistakes_to_retest: <knowledge-level candidates, or NONE>
- student_state_note: <student-expressed observation only, or NONE>
- exact_stop: <page / section / concept / before-or-after checkpoint>
- next_first_action: <one directly executable action>
- files_to_update: <suggested local relative paths>
- privacy_scope: uploaded_project_only
- sync_status: pending
END_T2AG_SESSION_CLOSE
```

Field discipline:

- `session_id` is unique across all cloud sessions; once emitted it must never be renumbered and
  re-sent.
- `base_state_id` identifies a course-state snapshot and must not be replaced by `t2ag_version`:
  the same rule version does not mean the same progress.
- `covered` records what was taught; `completed` records only what has passed a confirmation gate.
  The two must never be blended.
- `mastery_evidence` records only what the student actually restated, exemplified, proved, or
  solved — never a teacher's inference.
- `source_evidence` must be traceable to uploaded material that was actually read; when no source
  text was read, write `NONE`.
- The cloud has no authority to write `sync_status: synced`, nor to claim in prose that a local
  write-back has happened.
- The event block contains only what this teaching session needs; it never copies personal,
  emotional, transactional, or identity material unrelated to the course.

## 5. Local import and duplicate protection

When the local agent receives one or more event blocks, it proceeds in this order:

1. Save the input verbatim for checking, and parse only the fields between `T2AG_SESSION_CLOSE` and
   `END_T2AG_SESSION_CLOSE`; an ordinary chat summary cannot substitute for the event block.
2. Validate the protocol, the required fields, the enumerated values, the timestamps, and
   `duration_minutes`; on failure, stop the write-back and list what is missing.
3. Search `main/` and `cloud/cloud_sync_state.md` for the `session_id` or `receipt_id`. If it is
   already there, treat it as a duplicate import and do not accumulate the hours, questions, or
   mistake records a second time.
4. Check `base_state_id` against the known baseline in `cloud/cloud_sync_state.md`, then validate
   the explicit activity triple in the event, and read the local `progress.md`, the current
   Lesson/Exercise main carrier, and the related question/mistake records. An old event carrying
   only `lesson` must go through manual compatibility migration; never infer the current activity
   silently.
5. If the baseline is unknown, if it is behind while the local side has moved on, or if the exact
   stops contradict each other, mark `conflict`; check with the student first and change no course
   progress before they confirm.
6. When there is no conflict, update the `progress.md` source of truth first and keep the
   `session_id` in the teaching record; then, following the unified activity routing, update the
   current Lesson/Exercise main carrier, `question_bank.md`, `mistake_bank.md`, and the student
   profile. Candidate mistakes still have to be attributed through the existing threshold; being
   listed by the cloud does not automatically make one a formal mistake record.
7. Refresh `t2ag_memory.md` and `learning_path.md` from the source of truth; never overwrite a
   source of truth backwards from the mobile entry.
8. Run `main/70_tools/t2ag_doctor.py --profile runtime`. Only when the write-back is complete and
   the runtime doctor reports `0 FAIL` may it be recorded as `synced`; cloud sync does not trigger
   the release profile.
9. Append the synchronization result to `cloud/cloud_sync_state.md` and emit a `T2AG_SYNC_RECEIPT`
   to the user; on a conflict, write status `conflict` and keep the reason and the items awaiting
   confirmation.

```text
T2AG_SYNC_RECEIPT
- protocol_version: T2AG-CLOUD-1
- session_id: <imported session id>
- status: <synced | duplicate | conflict | rejected>
- written_files: <relative paths or NONE>
- doctor: <N FAIL, N WARN | NOT_RUN>
- note: <short result>
END_T2AG_SYNC_RECEIPT
```

## 6. Conflict adjudication and degraded modes

| Situation | Action |
|---|---|
| `session_id` already seen | return `duplicate`, write nothing |
| `base_state_id: UNKNOWN` | import only after the local stop has been checked by hand |
| local state is ahead of the cloud baseline | merge only non-conflicting evidence; a progress change needs student confirmation |
| `covered` and `completed` are blended | the confirmation-gate evidence decides; with no evidence, stay pending |
| the source material is missing | the discussion may be recorded, but new knowledge is not counted as textbook-driven completion |
| several event blocks contradict each other | list the differences in time order and ask the student to adjudicate; never overwrite automatically on a "newest is correct" rule |

When rule versions or cloud projections disagree, degrade by risk instead of blocking teaching
outright:

- Only display, wording, or non-current-course auxiliary fields differ: mark `safe_degraded`,
  continue the current teaching, and leave the missing feature disabled.
- Progress fields or the node schema differ: recover read-only on the shared fields, suspend
  automatic node write-back, and require a minimal check.
- The authority chain, identity routing, privacy scope, the current stop, or a confirmation gate
  conflict: suspend both advancement and write-back and wait for local adjudication.

## 7. Two-way component-change synchronization

### 7.1 After a local update, issue a change directive

After a local change to rules, prompts, templates, a state-block schema, the cloud mirror structure,
or any other component that affects how the cloud runs, the following must be completed before the
round ends:

1. Identify which local changes affect the cloud; ordinary course-progress changes still go through
   teaching-state sync and do not warrant a second component directive.
2. Create a unique file `CD-YYYYMMDD-NNNN.md` in `cloud/outbox/` holding the complete change
   directive. A `draft` may be edited; once it reaches `ready_to_send` and is assigned a formal ID,
   the body must not be rewritten. To correct it, create a new directive and link it with
   `supersedes`.
3. The directive must state what changed locally, what the cloud should change, the acceptance
   criteria, the attachments required, and the privacy impact; "sync the latest version" alone is
   not acceptable. If the change touches the cloud sync protocol itself,
   `main/50_playbook/cloud_learning_sync.md` must be sent with the directive as the protocol
   definition source; the Project Instructions are only an execution projection and cannot stand in
   for the definition source in an architecture review.
4. Register the `directive_id` and its current status in `cloud/cloud_sync_state.md`.
5. Send the directive and the attachments it lists to the cloud. Without upload-tool evidence or
   user confirmation, record only `ready_to_send`; never claim `sent`.
6. Once the cloud confirms receipt, move the status to `acknowledged`; only after the cloud returns
   a handoff and the local side finishes adjudicating may it become `closed`.

```text
T2AG_CLOUD_CHANGE_DIRECTIVE
- protocol_version: T2AG-CLOUD-1
- directive_id: CD-<YYYYMMDD>-<NNNN>
- created_at: <ISO-8601 with timezone>
- local_t2ag_version: <version>
- target_cloud: <project name or UNKNOWN>
- affected_components: <component names>
- local_changed_files: <relative paths>
- expected_cloud_changes: <explicit required modifications>
- acceptance_criteria: <observable completion conditions>
- attachments_to_send: <relative paths>
- migration_notes: <compatibility or ordering notes, or NONE>
- privacy_impact: <NONE | REVIEW_REQUIRED | description>
- reply_required: T2AG_CLOUD_HANDOFF
- sent_at: <ISO-8601 with timezone or NONE>
- send_evidence: <upload/message evidence or NONE>
- status: <draft | ready_to_send | sent | acknowledged | closed>
END_T2AG_CLOUD_CHANGE_DIRECTIVE
```

When the user confirms that a formal directive has already been applied on the phone but the local
side has no cloud acknowledgement, record the status as `applied_unacknowledged` and keep the time
of the user's confirmation together with a note on the evidence; the next synchronization then only
needs a lightweight acknowledgement:

```text
T2AG_DIRECTIVE_ACK
- directive_id: <formal id>
- directive_hash: <sha256 of immutable directive block>
- applied_version: <cloud-visible version>
- applied_at: <ISO-8601 with timezone or UNKNOWN>
END_T2AG_DIRECTIVE_ACK
```

### 7.2 After a cloud-side change, a handoff is mandatory

On receiving a change directive, the cloud executes or generates only the cloud-side modifications
the directive lists explicitly. When the platform cannot edit the Project Instructions or an
existing file directly, it produces a complete replacement file and must not pretend the change is
already live in the settings. If the cloud finds something outside the directive worth changing, it
may only write it into the handoff as a proposal; it must never widen scope silently.

After any real modification, replacement-file generation, or new proposal, the cloud must produce a
downloadable/copyable `CH-YYYYMMDD-NNNN.md` containing this complete block:

```text
T2AG_CLOUD_HANDOFF
- protocol_version: T2AG-CLOUD-1
- handoff_id: CH-<YYYYMMDD>-<NNNN>
- directive_id: <source CD id or NONE_FOR_UNSOLICITED_PROPOSAL>
- produced_at: <ISO-8601 with timezone>
- cloud_project: <project name or UNKNOWN>
- cloud_base_state_id: <base_state_id or UNKNOWN>
- changes_applied: <actual cloud-side changes, or NONE>
- generated_files: <downloadable file names, or NONE>
- deviations: <differences from directive, or NONE>
- verification: <checks actually performed, or NOT_RUN>
- open_questions: <items requiring local discussion, or NONE>
- proposed_local_changes: <explicit local proposals, or NONE>
- privacy_impact: <NONE | REVIEW_REQUIRED | description>
- status: proposed_for_local_review
END_T2AG_CLOUD_HANDOFF
```

The cloud has no authority to write a handoff status of accepted, merged, or synced. A chat summary
cannot substitute for the handoff file; if no file can be generated, emit at least the complete
plain-text block so the local side can save it.

**A protocol invariant (the local side obeys it too)**: the `status` field inside the block stays
**permanently** at the cloud-produced value `proposed_for_local_review`. Doctor verifies this
invariant. A local adjudication result **must not** rewrite the in-block `status`; it is written to
(a) the `local_decision` column of the cloud-handoff table in `cloud_sync_state.md`; and
(b) optionally, a local-adjudication section in the same CH file, placed **after**
`END_T2AG_CLOUD_HANDOFF` (`sync_completed` and the like). A work order demanding a change to the
in-block status is a defective order (see `batch_workorder_spec.md` §3 item 9).

### 7.3 Local receipt, discussion, and adjudication

1. Save the cloud handoff verbatim to `cloud/inbox/CH-YYYYMMDD-NNNN.md`, and first validate
   `handoff_id`, `directive_id`, the protocol, the actual files, and the stated deviations.
2. A handoff is a proposal plus execution evidence, not a local rule source; it must never
   automatically overwrite `main/`, `cloud/`, or course files.
3. Show the user "changes made / deviations from the directive / proposed local changes / open
   questions / privacy impact" and discuss them item by item.
4. Only after the user adjudicates accept, partial accept, or reject may the accepted part be
   implemented locally; a partial accept must record what was not accepted.
5. After the local modification, run doctor and register the adjudication, the files, and the
   verification result in `cloud_sync_state.md`; do **not** change the in-block CH `status` to
   accepted/synced.
6. If the local adjudication in turn changes what the cloud state should be, produce a new
   `directive_id`; never rewrite an old directive to fake a closed loop.

Cloud modifications the local side did not accept may stay in the Project for experimentation, but
must not be described as formal T2AG rules. A cloud handoff is not part of the daily startup chain
by default; it is read only when the current synchronization discussion points at it explicitly, so
that an old proposal cannot contaminate teaching recovery.

## 8. Privacy and the upload boundary

The privacy scope has two layers:

- `existing_project_scope`: content the user has already uploaded by hand into the current personal
  instance may continue to be used inside that Project; it is not cleaned up retroactively, and it
  does not thereby authorize a second copy, an export, publication, or migration to another service.
- `automatic_sync_allowlist`: the minimal low-risk fields the agent prepares or proposes to sync
  automatically, containing by default only the course code, the lesson, stable node IDs, the exact
  stop, the rule version, internal role/template numbers, and a state summary with no body text.

The user may upload personal information by hand; that authorization applies only to the current
personal instance. Every new automatic-sync field must be registered and reviewed explicitly. The
skeleton and lite must never absorb personal-instance content.

- When context that a privacy rule may be blocking is missing, report the gap and continue with the
  minimum necessary information; never lead the user into supplying unrelated identity information.
- When necessary context is missing, request the minimum only; never infer or fill in a private
  field from material that was deliberately omitted.

## 9. Prompt consistency

The copyable cloud prompt lives at `cloud/T2AG_PROJECT_INSTRUCTIONS.txt`. This file is the protocol
definition source; the prompt is its execution projection for the cloud model. When the authority
chain, a state-block field, a confirmation gate, a change directive, a cloud handoff, the privacy
boundary, or the synchronization semantics change, both must be synchronized in the same batch, a
new outbox directive must be produced, and doctor must be run, so that the local rules and the cloud
behaviour cannot fork.
