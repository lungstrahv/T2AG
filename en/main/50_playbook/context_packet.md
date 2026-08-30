# The learning-session context packet

**Protection level**: core-playbook

> This process reduces repeated context loading when starting or resuming a course. It optimizes
> **which sources are read**, not rewriting long-term evidence into a shorter second source of truth.

## 1. Goal and boundaries

<!-- rule: CTX-PACKET-002 -->
Daily teaching uses **immediate excerpt + triggered expansion**:

1. `t2ag_context.py` generates a read-only context packet from the current authoritative files every time;
2. body text in the packet must be a verbatim excerpt of the source file or a mechanical routing field; no factual rewriting is generated;
3. the packet goes to standard output only: it is never written to disk, owns no state, and takes no part in write-back;
4. `progress.md` supplies only the Course lifecycle, the single foreground and the stopping point; the Activity lifecycle must be replayed from `activity_ledger.md`, while the profile, Group, teacher and activity evidence each keep their own authority boundary;
5. character counts are only a cross-tokenizer cost proxy; an approximate token count must never pose as an exact bill;
6. the soft budget may trigger a review and must never truncate a definition, a problem statement, a confirmation gate or a safety boundary.

When the context packet and a source file disagree, the source file wins and work stops. Activity
resolution, teacher mapping and excerpting must share one raw byte cache; before finishing, verify
that every source is unchanged, by file bytes and by the directory listings already observed.
`source_sha256` must be the digest of the raw file bytes and directly comparable with
`Get-FileHash`; the displayed text only normalizes CRLF / CR to LF, to fix the serialized character
count across platforms, and does not change what is digested.

In the daily three-agent startup, the Context Prefetcher must independently run
`--format critical` first and hand back L0-critical immediately, then generate the full Markdown L0
in the background in the same round. Critical reads only the sources the route and the first
action genuinely depend on; it does not wait for reflections, non-current mistakes, Group details
or the cost account. Once Main has a trusted handoff, a non-textbook course may enter
`learning-ready`. A textbook critical only reaches `route-ready` and must still wait for the Scope
session scan of the same snapshot (`source_page_assets.md` §3.1 A1–A6). The background packet must
report back the same `snapshot_id`, and only once doctor/state and the full source verification
have also converged does it enter `recovery-settled`. The handoff is never written to disk; after
Main receives critical it must not run the Markdown L0 again, search the ledger, decode a pending
body or assemble a close confirmation. The full background timeout is still 45 seconds; the
critical target is under 10 seconds; the 15-second first-action target applies only to routes that
need no Scope visual scan.

> **The packet does not authorize** (2026-08-06): for a textbook with `scope_scan` pending, the top
> level of critical should be `status=route_ready`, `blocking_teach=true`,
> `teaching_gate.admission_status=unavailable`, `egress_mode=status_only`, and withhold must cover
> textbook body text and opening text that could otherwise be sent. Those fields and
> `may_release_action` are **for observability only** and do not constitute send authorization. The
> structural hard gate depends on the host `lesson_emit` (see
> `docs/adr/0002-host-controlled-textbook-teaching-egress.md` and
> `docs/protocol/host-teaching-egress-api.md`). A withhold at the repository layer is **not** the
> same as having intercepted the outgoing output.

## 2. The three-layer reading model

### L0-critical: the critical-path packet

Run on the startup critical path:

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --format critical
```

The output is JSON of at most 12,000 characters, holding only status, course, snapshot, route,
blocker, the four classes of public source SHA, `teaching_gate` and `action_payload`. A Lesson's
authoritative pending prompt must come verbatim from the "exact stopping point" of the current
slice of `progress.md`, with its source named; the model may add clearly-labelled summaries,
warm-ups, analogies or exploratory questions, but must never replace the authoritative stopping
point or bypass the Exercise hint gate. The current textbook fragment must come from the actual
page asset of the current `pdf_page_index`, never from the first file path in Scope. When a
`LessonPreparationSnapshot` exists, critical / `action_payload` may carry
`preparation_snapshot_id`, `lesson_scope_version`, the current page's `source_page` and the
`scope_scan` manifest (PDF path/SHA, the full page index, the render profile), and must carry
`page_teaching_contract`. That contract gives the PDF/in-book page, the ASCII classroom tree, the
per-block in-page coverage register, and the incompressible understanding/feeling/continue/page-turn
gates. The manifest declares the inputs to be scanned only; it can never self-report that the scan
is complete. An Exercise gives the problem statement only. `confirm_close` returns, in one go, the
latest pending ID, the body SHA, the complete student-facing retrospective Markdown, the
presentation SHA, the recommended conclusion, the system-bound tuple and a short reply word. A
first run returns the `first_run.md` route. A state conflict returns `status=blocked` with an
explicit blocker and never guesses a route.

Critical must also carry `classroom_creativity_policy`: creative interaction is allowed by default;
the only hard boundaries are not leaking, ahead of time, answers or solution structure for
exercises that were not requested, and not skipping a required textbook block; extra exercises are
generated only after the student requests them or explicitly opts in. A comprehension-check question
does not count as an extra exercise.

Every Lesson action payload must also carry `lesson_opening_contract`: the opening content
overview, the ASCII knowledge tree, its source or a `creative_composition_required` status, and the
gate "ask how the route feels and obtain continuation authorization to enter the first block". The
opening overview counts as neither textbook page coverage nor mastery evidence.

`snapshot_id` is `CTX-<COURSE_ID>-<SHA256>`; the trailing SHA canonically binds course_id together
with the raw-byte SHAs of the memory, learning path, progress, activity ledger, current activity,
profile and teacher overlay that critical actually observed. Context work must not be started twice
for the same snapshot.

### L0-background: the full session recovery packet

When a new conversation resumes an existing course, run:

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --format markdown
```

The Prefetcher should bind critical's snapshot to the background verification:

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --format markdown --expect-snapshot <SNAPSHOT_ID>
```

Only a match may hand back `background-settled`; on a mismatch, discard the old candidate and
regenerate critical and the background packet once. A second inconsistency returns a blocker and
must not settle.

When `--course` is omitted, resolution is permitted only from memory's current-course pointer;
never scan directories to guess. When a non-current course is named explicitly, that course must
still belong to the active Group memory points at; the packet must be marked
`explicit_same_active_group`, and the previous course's summary must never be taken as the target
course's recovery pointer. A course outside the group fails outright: switch course groups first.
L0 contains:

- memory's last-lesson summary and current pointers;
- the profile's initialization status, `exercise_hint_gate`, learning goals, tutoring preferences, execution parameters and individual outline;
- the exact table rows in the learning path for the current course and the active Group;
- the active Group's current budget, members and cycle schedule;
- the frontmatter and "current progress" of `progress.md`;
- the recovery capsule of the explicit LearningActivity;
- open questions and questions needing review, plus the active mistake scheduling summary;
- reflections relevant to the current course, active reasoning patterns and the effective teacher constraints;
- the single problem statement of the current Exercise, or the full verified Scope text window of the current Lesson; and at the same time `source_consumption.scope_text_status=complete_in_current_packet` states this round's text consumption explicitly, while the visual status stays `external_scan_required` until the Prefetcher has actually opened the page images one by one.

Full Scope text entering L0 proves only "readable this round"; it does not prove "taught block by
block in class". Main must maintain a session-local page coverage register; every active lesson
block may only be `covered`, `explicitly_deferred` or `outside_active_lesson_boundary`. Until every
block has a status and the student has separately authorized a page turn, the next page's body must
not be consumed. A correct answer never generates continuation authorization automatically.

L0 does not load the full teaching history, every closed question, every Attempt/Review, unrelated
courses, unrelated handoffs, or the complete journal.

### L1: the current step

When actually about to advance one step, expand only the evidence that step directly needs and that
L0 does not already contain. Run:

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --include-l1
```

- Exercise: the current problem statement and the manually proofread problem source are already in L0; if the current problem already has a submission, append the Attempt/Review directly related to it;
- textbook Lesson: prefer the current `LessonPreparationSnapshot` + LessonMap + `source_assets` (a contiguous Scope of 5–8, or the whole book for a short book); the legacy `working_pages` path was retired in 0.2.2 batch S3, and without a preparation Snapshot `ready` must not be returned.
- the current question or retest: the corresponding question / mistake entry and its backlinks;
- an idea the student raised explicitly: the corresponding thoughts and any distilled reflection.

The first presentation of an exercise still gives the problem statement only. The context packet may
let the teacher read the state it needs, but must never show the student internal hints, answers,
someone else's historical solution or a reasoning tree ahead of time.

When the current activity is an Exercise and `exercise_hint_gate: enabled`, run
`t2ag_hint_gate.py` against the current problem before every teaching reply. `concept_answer`
answers only the concept the student explicitly asked about and does not carry the definition,
example or conclusion back to the problem; the help level rises only by explicit student
authorization.

### L2: triggered full expansion

Read a full source only when one of these triggers appears:

| Trigger | What is expanded |
|---|---|
| a state conflict, a dangling pointer, a concurrent change | the full progress, the activity main carrier and the related fine-grained evidence |
| the user asks about history, a design reason or the original wording | the corresponding historical record, handoff or journal |
| scheduling, parameter changes, a group review or closing a group | the full profile execution parameters, and the Group plan/calendar/review |
| a formal retest, a correction, or a reasoning-pattern adjudication | the full mistake/question/reasoning entry and its evidence backlinks |
| a teacher rule conflict, or changing the teacher | the full overlay, template and change source |
| session close | every write and read-back target named by `session_close.md` |
| a project audit, migration or release | the matching project handoff, contract, tests and the actual Git state |

"It might be useful" is not a reason to expand; you must be able to name the current trigger.

## 3. In-session reuse and invalidation

Within one conversation, Main accepts critical once per `snapshot_id`, and the Prefetcher starts the
background verification for it once. Any of the following invalidates it:

1. `progress.md`, the current activity, the profile, the active Group or the teacher mapping was written;
2. an external sync, another agent, or the user edited a source inside the packet;
3. after conversation compaction it cannot be confirmed that the current stopping point and key constraints are still held;
4. the current activity or the current problem changed;
5. the tool reports that a source changed during generation;
6. the background packet's `snapshot_id` differs from the critical already released;
7. a textbook's session-local Scope scan is missing a page, the snapshot/PDF SHA differs, or `pdf_page_index` and `printed_page_label` were mixed up.

Re-run the context tool after invalidation. An ordinary question-and-answer turn must never
mechanically re-read every file.

## 4. Write-back discipline

The context packet can never be edited or written back. Session close still follows:

```text
progress.md
-> the current Lesson / Exercise and the real ledger
-> state_refresh --write
-> state_refresh --check
-> doctor
-> re-read this round's actual write targets
```

The closing read-back covers only the actual write targets; it never reloads all history for the
sake of verification. The next session generates a new packet from the new state.

## 5. The cost account and acceptance

The tool reports two different questions separately:

- `reference_inventory_chars`: the current full-text character inventory of the source files involved this round, for selection comparison only; it is not a measurement of the old prompt flow;
- `l0_selected_source_chars` / `l1_selected_source_chars`: the character count of verbatim excerpted body text;
- `source_selection_ratio` / `source_inventory_omitted_percent`: the selection rate over source content; **never call that ratio an end-to-end token reduction**;
- `serialized_l0_markdown_chars`: the full character count of the default Markdown, including headings, paths, raw-byte SHAs, routing and the L2 table;
- `serialized_l0_plus_l1_markdown_chars`: the full Markdown character count after appending the first L1;
- the raw file byte SHA-256 and the selection label of every source.

Without a saved real serialization of the old prompt, this tool must not state an end-to-end
reduction percentage. Character counts remain a tokenizer-independent proxy and are not model tokens
or a bill. Acceptance requires all of:

1. the current pointers, the single activity, the next action, the student constraints, the teacher red lines and the current textbook/problem statement are all recoverable; the Lesson pending prompt matches the progress exact stopping point word for word, and the current page path matches the page index;
2. the packet contains no full progress history, no set of closed questions, and no unrelated course body text;
3. packet generation is read-only and creates no `.venv`, no cached state file and no second source of truth;
4. the two `serialized_*` values each equal the length of the actual rendered result;
5. the core playbook and tools stay homologous across Main, Skeleton and Lite;
6. critical does not exceed 4,096 characters and does not call the full L0 build path;
7. `confirm_close` returns the complete content to be displayed in one call, and an Exercise leaks no hint;
8. no compression gain may be bought by lowering a confirmation, evidence or safety standard;
9. a textbook's Snapshot/receipt/hash must never be stated as "scanned this round"; the first teaching action may be released only once both the full L0 text consumption of the same snapshot and the per-page visual open records exist.

The default soft budget is 16,000 actual serialized Markdown characters, checked separately for L0
and for L0 plus the first L1. On exceeding it, output `REVIEW` only, and let the maintainer check
whether a new duplicated inventory has appeared; never silently drop a field.

### Character and byte accounts are reported separately

`serialized_l0_markdown_bytes` and `serialized_l0_plus_l1_markdown_bytes` sit beside the character
fields. They are never collapsed into one number, and the byte side has no gate: the soft budget is
measured in characters while actual context transport is measured in bytes.

### Optional components: the student owns the switches

Four sections may be disabled: `contract`, `reflections`, `overlay`, and `template`. Disabling one
must not break the recovery chain; stopping point, progress, textbook window and current pointers
are therefore not switchable. The profile key is `l0_optional_off`, with comma- or space-separated
IDs. An unknown ID is an error, never silently ignored. Every render reports each component's state,
bytes, and total avoidable cost. Turning one off changes it to read-on-demand; it saves recurring
cost while relying on the agent to fetch it when needed, and the tool must state that tradeoff.

## 6. Degradation

- The profile is uninitialized, still contains required placeholders, or the memory date is `—`: output `first_run_required` and route to `first_run.md`; do not generate a fake course packet.
- Critical's current course does not exist, is not `ongoing`, does not belong to the active Group, activity routing failed, the ledger and progress conflict, or a source changed during reading: return `status=blocked`; the background command still exits non-zero, and the authority chain is repaired first.
- The tool cannot execute: do the layered excerpting by hand per the section of the same name in `lesson_recover.md`; never fall back to an undifferentiated full-repository read.

## 7. On-ramp rendering (ELI5 form)

An on-ramp is a low-cost trunk projection shown before heavy work. It supplies structure and very
few words; it never replaces the explanation. `preview` uses the existing lesson-opening overview
and ASCII knowledge tree; `resume` shows where the student is. Every textual node must be selected
from a keystone row, a textbook contents heading, or a listed lesson objective—no new factual claim
may be generated. A progress group anchors on keystones; a schedule group falls back to course
section numbers. `crosstext` uses canonical source-page anchors and is manual-only.

Only `preview` is frozen before blind extraction and may not be regenerated mid-problem. The profile
switch `onramp_off` accepts `preview` and `crosstext`; unknown IDs fail. After the first preview, the
student judges once whether it compresses or dilutes; dilution turns that slot off. Projections are
not persisted: their source content already has an authority, and storing the rearrangement would
create a second truth source.

## 8. Related files

- `main/t2ag.md`: the startup entry point and daily takeover.
- `main/50_playbook/lesson_recover.md`: course recovery and the L1/L2 triggers.
- `main/50_playbook/session_close.md`: write-back and read-back.
- `main/50_playbook/startup_orchestration.md`: the three-agent startup, join and degradation.
- `main/70_tools/t2ag_context.py`: the read-only context packet generator.
- `main/70_tools/t2ag_activity.py`: the single activity router.
- `main/50_playbook/course_group_rules.md`: keystone anchors and the schedule fallback.
- `main/50_playbook/source_page_assets.md`: canonical page anchors for `crosstext`.

<!-- rule: CTX-PACKET-004 -->
## Main consumption discipline and course selection (canonical; sunk from constitution §3.2 on 2026-08-08 / EV-0020)

The standard two-command sequence (critical first, markdown as the verification backstop):

```powershell
python -B main/70_tools/t2ag_context.py --course <ID> --format critical
python -B main/70_tools/t2ag_context.py --course <ID> --format markdown
```

- When the course ID is omitted, only memory's current-course pointer may be used; never scan directories to guess. An explicit switch is permitted only within the active Group; for a course outside it, switch groups first.
- After Main receives critical, its context call count is 0: it must not run the Markdown L0, search the ledger, decode a pending, assemble a close confirmation, or re-read the full L0. Only when critical has hit its 10-second timeout and that branch has terminated may Main degrade to running `--format critical` once.
<!-- rule: CTX-PACKET-003 -->
- The same snapshot is never dispatched twice; if the background snapshot differs, the Prefetcher discards the candidate and re-runs once; **an unchanged L0 is not re-read within the same conversation**.
- Critical recovers only the route, the stopping point, the next action, the necessary source SHAs and the first round's action payload; the packet is a verbatim read-only projection, not a source of truth, and must never be written to disk and edited. The authoritative pending prompt must come verbatim from the current slice of `progress.md` with its source named, and added material must never replace the authoritative stopping point or bypass the hint gate.
- Use `--include-l1` when advancing the current step needs additional direct evidence; enter a full L2 read only on an explicit trigger such as a state conflict, retest/question recovery, scheduling/review, session close, a historical follow-up, or a project audit.
