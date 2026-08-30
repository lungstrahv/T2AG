# Multi-agent orchestration for the daily startup

**Protection level**: core-playbook

> This process optimizes the wait, on a healthy instance, between the user asking to continue
> studying and the first actionable piece of learning content appearing.
> It separates "read-only teaching may begin" from "the recovery checks have converged", without
> lowering source consistency, student confirmation, Activity lifecycle or write-back standards.

## 0. The startup welcome message (canonical; sunk from constitution §3.0 on 2026-08-08 / EV-0020)

Both first initialization and daily takeover must display the welcome message once, in parallel
with the recovery branches and without either waiting on the other:

1. read `active` and the matching registry from `80_interface/skin.yaml`;
2. read `welcome_msg` and `art_file` from the `skin.yaml` inside the active skin directory;
3. output `welcome_msg` first, then the plain-text character art `art_file` points at, verbatim, and finally the version;
4. Main and Lite display the character art the current instance selected; a Skeleton installation template displays the default `t2ag` identity art. A Skeleton default must never override Main's personal choice.

This section owns the startup rule for **when** to display; the skin metadata owns the truth of
**what** is displayed. `bin/t2ag` is only an optional terminal projection of the same rule and must
never hardcode a second welcome message or character art.

## 1. Goal and the default topology

- Healthy-path targets: critical route <= 10 seconds; the first actionable learning content for a non-textbook course <= 15 seconds; a textbook must first complete the Scope text and visual consumption of the same snapshot, targeted at 45–60 seconds together with full `recovery-settled`.
- The agent pool keeps at most 6 identities with at most 3 running at once (both including Main); the default active formation is still one Main Conductor and **two helper** agents. A completed agent releases its concurrency slot; a new one may be created while the pool is not full, and reuse is preferred when it is.
- **Single-agent degradation** is permitted when helper-agent capability is unavailable; degradation changes no safety or authorization boundary.
- Multi-agent is a daily startup preference, not a mandated concurrency count, and it authorizes no widening of read, test or write scope.
- The Startup Formation is one main plus two helpers for daily takeover; the Task Assist Budget is one helper, three tests and ten minutes by default when changing or verifying the system. The two must never be merged into one budget.

Two states must never be conflated:

- `learning-ready`: the current route, stopping point, required content and source identity are trustworthy, with no known teaching blocker; the Main Conductor may give read-only explanation, ask questions, give feedback, or display a body awaiting confirmation.
- `recovery-settled`: the runtime doctor, the state check and the full source verification have all converged; only after this may progress be written, a checkpoint confirmed, the foreground switched, a terminal/RT3 action performed, or local state declared all green.

Default roles:

| Role | Responsibility | Startup-phase permissions |
|---|---|---|
| Main Conductor | display the welcome message, join the two helper branches, interact with the student | after receiving critical, the context call count must be 0 |
| Runtime Sentinel | verify the local teaching runtime state | read-only: the runtime doctor and state refresh `--check` |
| Context Prefetcher | generate and consume the current course context, preparing a first-round candidate that is not yet sent | read-only context; no write-back, and never entering L2 on its own |

<!-- rule: CTX-PACKET-005 -->
## 2. Build the dependency tree first, then assign agents

Before dispatching, the Main Conductor draws the minimal dependency tree and estimates the critical
path. A fixed startup may reuse the diagram below directly; dispatching agents first and looking for
their responsibilities afterwards is not allowed:

```text
user continues studying
├─ Main: welcome + read collaboration preferences (about 0.2–2s)
├─ Runtime Sentinel (parallel; about 1s of program time, 3–15s including scheduling)
│  ├─ runtime doctor
│  └─ state --check
└─ Context Prefetcher (a lean agent context)
   ├─ --format critical -> hand off immediately (target <= 10s)
   └─ the full Markdown L0
      └─ textbook: open every page image per the scope_scan manifest -> background-settled
        v
Main joins L0-critical -> learning-ready (healthy target <= 15s)
        v
Runtime + L0-background converge -> recovery-settled
```

Only dependency-free, read-only branches may run in parallel. User confirmation, every write-back,
checkpoints, terminal/RT3 and the final adjudication always stay on the Main Conductor's serial
path. When the task is not a fixed startup, Main must also list the dependencies, the expected
duration and the write set before assigning helper agents; two agents must never hold the same
source of truth at once.

## 3. Parallel startup

The Main Conductor displays the current skin's welcome message per `main/t2ag.md` and dispatches
two read-only branches at the same time:

Both helper branches must use a clean or minimal context. When the host supports a context-forking
strategy, prefer the mode that inherits no history (such as `fork_turns=none`); when recent
messages genuinely must be carried, carry only the minimum turns needed for that branch, never
inheriting a whole teaching or construction conversation. The task statement names the role, the
working directory, the exact commands, the fields to return, the read/write boundary and the
timeout behaviour directly; it must never require a helper agent to re-read this file,
`context_packet.md` or the full profile to derive the contract for itself. The two read-only
identities of the Startup Formation also inherit no Task Assist, migration, release or RT3
authorization.

### Branch A: Runtime Sentinel

Run in parallel:

```powershell
python -B main/70_tools/t2ag_doctor.py --profile runtime
python -B main/70_tools/t2ag_state_refresh.py --check
```

Return a minimal structured result:

- the doctor exit code, FAIL count and a WARN summary;
- the state refresh exit code and drift count;
- the duration of each;
- whether `runtime_ready` holds.

WARNs are handled per the current doctor contract; only a FAIL or a non-zero exit blocks. The
Runtime Sentinel does not repair, does not run the release profile, and does not add candidates,
Lite, Git or release hygiene to the daily startup gate.

### Branch B: Context Prefetcher

Executed in two phases within one agent turn, handing back twice:

```powershell
python -B main/70_tools/t2ag_context.py --format critical
python -B main/70_tools/t2ag_context.py --format markdown --expect-snapshot <SNAPSHOT_ID>
```

Send the critical handoff immediately after the first command completes, without waiting for the
full L0; then continue verifying and send background-settled. A textbook Lesson's critical is only
`route-ready` and must never release a classroom action directly; the Prefetcher must consume the
complete content body of the whole Scope page by page in this session, per
`action_payload.scope_scan` and `source_page_assets.md` §3.1 (A1–A6), through host-observable
delivery. The **current default observable path** (before the U2 form list is frozen) is in
`source_page_assets.md` §3.1.4: L0 consumes the verified body, plus delivery of the whole page image
per the manifest/profile with the page index and `printed_page_label` reported back. Completion is
proven per A6 (ADR-0003) by host-observable delivery; a Snapshot `content_consumed` or a historical
receipt must never pose as this round's. The task statement embeds the field contract directly,
inherits no full history, re-reads neither this file nor `context_packet.md`, and does not consume
course reflections, non-current mistakes or the cost account before the route. The handoff contains:

- `status`, course, current activity, the exact stopping point and the next action;
  while a textbook scan is pending, the critical JSON `status` is `route_ready` (not `ready`) and
  `blocking_teach=true`; these fields authorize no sending (see ADR-0002).
- the student constraints and teacher red lines this round requires;
- the first actionable learning-content candidate (while a scan is pending the compiler withholds the body; the identity and manifest remain);
- the Lesson opening contract: the structural gates and whether it has been shown; while a scan is pending, the **body** of the overview/knowledge tree is withheld by critical. When the opening source is missing, creative composition is permitted only after admission, and a withheld item must never be treated as authorized.
- `snapshot_id` and the public `source_sha256`;
- the `sources_unchanged` conclusion.
- for a textbook, also return `scope_scan`: the snapshot, the PDF SHA, every `pdf_page_index`, the consumption evidence per page (under the current path including `opened=true` / the in-book page number / the heading), the current page, and any page-number or content conflict found; **a single page missing relative to Scope means not complete** (an A4 omission FAILs; a duplicate only WARNs). **Note**: a textual declaration of `opened=true` / complete **with no delivery** does not constitute proof; proof = host-observable delivery of each page's content body (A6/ADR-0003). A host Scan Orchestrator receipt is reserved as a future state, reclaiming the issuing right once it lands.
- for a textbook, also return `page_teaching_contract`: the current PDF/in-book page, the character classroom tree requirement, the in-page coverage register, and the four gates — understanding confirmation, feeling feedback, one-shot continuation authorization and the page-turn announcement. A "continue studying" at this round's entry must never be read as standing authorization for the whole lesson.

<!-- rule: CTX-PACKET-006 -->
A candidate must stay withheld until Main adjudicates. Once the host lands, textbook teaching body
text passes only through `lesson_emit`; in a textbook-gated session the ordinary freeform assistant
egress is closed, or is a fixed host template only (see
`docs/protocol/host-teaching-egress-api.md`). Decoding the latest pending for `confirm_close` is a
fixed responsibility of the critical generator, returning in one call the complete student-facing
retrospective Markdown, the presentation SHA, the recommendation, the ID, the body SHA, the
system-bound tuple and the acceptable short close intents. Main must send the complete Markdown
straight to the student; **never show only an ID/SHA and have the student sign blind**, and never
require the student to transcribe the tuple.
A Lesson's action payload must project verbatim, and mark as authoritative, the exact stopping point
and next step from the current slice of `progress.md`; clearly-labelled restatement questions,
warm-ups, analogies or exploratory questions may be added alongside. An addition must never replace
the authoritative stopping point, manufacture false progress, or bypass the Exercise hint gate. The
current page's `source` must land exactly on the `SourcePageAsset` of the current
`pdf_page_index`, never returning the path of Scope's first page. After receiving critical, Main is
forbidden to run the Markdown L0, search the ledger, decode a pending, assemble a close
confirmation, or re-read the full L0; a `snapshot_id` already received must never be dispatched
again.

## 4. The two-phase join

### 4.1 Learning-ready

The first read-only learning action may be released once the following hold, without waiting for the
Runtime Sentinel to return in full:

```text
context_status in { ready, route_ready }   # route_ready while a textbook scan is pending
AND sources_unchanged == true
AND the critical snapshot_id has not been consumed
AND no route / source identity conflict
AND current activity / next action / required content all present
AND no returned report has blocking_teach == true   # while a textbook is pending, blocking_teach is still true -> cannot release
AND (non-textbook OR scope_text_status == complete_in_current_packet)
AND (non-textbook OR scope_visual_scan == complete_for_same_snapshot)  # A1–A5 proven in this session by host-observable delivery (ADR-0003), not a delivery-free self-report
AND (non-textbook OR page_teaching_contract complete and the current classroom tree already shown to the student)
```

The host TeachingAdmissionCapability / `lesson_emit` is a future state (ADR-0002/ADR-0003): once the
host lands, that capability reclaims the issuing right and is restored as a release condition;
before it lands, the expression above is the formal criterion per ADR-0003, and it is no longer
carried as a never-satisfiable defense-in-depth debt.

A `LessonPreparationSnapshot.content_consumed=true`, a historical receipt, and a matching
manifest/file hash prove preparation and identity only (some links on the A3 chain); they do **not**
satisfy this session's A1 consumption and do not constitute A6 proof (ADR-0003). Stop on any
conflict among the route, the progress exact stopping point, the action payload, the current page
path and the Scope manifest (A5); Main must never pick one version and continue.

Releasing a learning action permits one teaching block only. A student answering, restating or
saying "yes" closes the understanding gate only; the feeling gate after a derivation/summary and the
one-shot continuation authorization for the next block must each still be obtained. Before a new
page, the in-page coverage gate must also pass and the page number be announced first.

At this point it must be stated plainly that the internal state may still be `recovery_pending`;
never claim the doctor is all green or that state is closed. If the Runtime Sentinel arrives late
reporting a genuine teaching blocker, Main pauses before the next logical action and explains; a
WARN, release/Lite/Git hygiene, or a construction dirty tree must never retroactively erase a real
classroom exchange that already happened.

### 4.2 Recovery-settled

`recovery-settled` is entered only once all of the following hold:

```text
doctor_exit == 0
AND doctor_fail_count == 0
AND state_refresh_exit == 0
AND state_drift_count == 0
AND the context sources / route are still valid
AND background snapshot_id == critical snapshot_id
```

Any write, checkpoint result, foreground switch, terminal/RT3 action, or claim that "the startup
checks are complete" must wait for that state. The Main Conductor makes the final adjudication for
both phases; helper agents must never publish answers to the student on their own.

If the current activity is `pending_close`, or the next action is `confirm_close`, the first
actionable content must be the close confirmation for that exact object, body, ID, SHA and result.
"Start within 15 seconds" must never be read as skipping the close, writing `completed`
automatically, or creating the next Lesson early.

## 5. Timeouts and degradation

- The standalone wait for critical is capped at 10 seconds; the wait for the full background, the textbook Scope visual scan and the Runtime Sentinel is still capped at 45 seconds.
- Runtime Sentinel timeout: if L0-critical already satisfies `learning-ready`, read-only teaching may proceed marked hygiene-pending; nothing may be written back and settled must not be claimed. If it returns FAIL/drift, pause the next action per whether `blocking_teach` holds and report the specific blocker.
- The Context Prefetcher has not even returned critical within 10 seconds: Main must first confirm that branch has terminated before running one degraded `--format critical`; it must not run Markdown or generate a duplicate snapshot.
- Helper agents unavailable: the Main Conductor performs the same read-only checks and context recovery in sequence, per `t2ag.md`.
- The background snapshot differs: discard the old candidate and have the Prefetcher re-run critical + background once; if it still differs, stop advancing. Main takes no part in the re-run.
- `first_run_required`: route to `first_run.md`; do not fabricate course content.

A failure path may exceed the healthy targets, and may report only the blocker; guessing a route,
writing state, or calling recovery-pending "settled" in order to meet a time target is forbidden.

## 6. Concurrency and write-back boundaries

The startup parallel region is strictly read-only. None of the following may run concurrently with
the doctor, state `--check` or the context prefetch:

- modifying `progress.md`, an Activity main carrier, the ledger, the profile, a Group or the teacher mapping;
- `state_refresh.py --write`;
- an Activity close, a migration, a sync, a commit, a release, or any other disposition of real state;
- any RT3, terminal lifecycle, or action needing the student's strict confirmation.

After entering recovery-settled, single-writer still applies: only the Main Conductor may coordinate
a write-back, and helper agents supply evidence or drafts only. Write-back still runs serially in
the authoritative order of `session_close.md`; multiple agents do not change the loop
`progress.md -> the real activity/ledger -> state_refresh --write -> --check -> runtime doctor -> read back`.

L2 is still opened only by the explicit triggers listed in `context_packet.md`. A helper agent must
never read L2 early on the grounds of parallel prefetching, and neither an implementer, a reviewer
nor the Prefetcher may make an RT3 decision for the student. After conversation compaction, recovery
or a handoff, existing authorization may only be preserved or narrowed.

## 7. Observable results

A healthy startup should leave at least the following results within the session, without requiring
them to be written to disk as a second source of truth:

- the welcome message was displayed;
- the Runtime Sentinel's gate conclusion and duration;
- the Context Prefetcher's route, source summary and withheld/released status;
- the Main Conductor's `learning-ready` and `recovery-settled` conclusions and the time of each;
- the total elapsed time from the user's request to the first actionable learning content;
- Main's context call count on the healthy path (must be `0`) and its degradation count (at most `1`).

These results serve this orchestration and its diagnosis only. They own no course state, replace no
authoritative file, and never automatically become release evidence.

## 8. The healthy-startup feel check

Every startup uses these five questions as a quick in-session acceptance. They are observability
checks and create no extra state file:

1. did the welcome message appear almost immediately, and does it come from the current active skin;
2. did a non-textbook healthy path produce the first classroom content within 15 seconds; did a textbook first complete a page-by-page scan of the whole Scope within 45–60 seconds and only then produce a classroom action matching the exact stopping point;
3. after receiving critical, did Main keep its context call count at `0`, without searching the ledger or decoding a pending;
4. were the two helper branches genuinely **parallel**, and did the Prefetcher deliver critical first and then verify the L0 of the same snapshot;
5. before `recovery-settled`, was there consistently no write-back, checkpoint result, terminal/RT3 action or "all green" claim.

If critical's authoritative route is explicitly `none`, item 2 becomes reporting truthfully, within
the same time target, that "there is no actionable learning action right now"; course content must
never be invented to satisfy a metric. When a feel item falls short, record this round's observation
and the actual durations; only a FAIL, drift, source conflict or `blocking_teach` from the sections
above escalates into a teaching blocker.

## 9. Agent lifecycle operating phrases

- Starting a class: launch per the Startup Formation, critical-first, and Main does not redo context;
- Wrapping up: a helper agent ends normally, releasing its `agent_max_active` slot immediately, while its identity may stay in the pool;
- Reopening similar work: prefer reusing a completed agent with the same responsibility;
- A new area, or a need for clean context: create one while the pool is not full, still bounded by `agent_max_active`;
- Changing or verifying the system: use the Task Assist Budget — one helper agent, three test commands and ten minutes by default; the two read-only identities of the daily startup must never be expanded automatically into a construction budget.

Pool capacity and active concurrency must be understood separately: `agent_pool_limit=6` is the
number of identities that may be kept, and `agent_max_active=3` is the number running at once
(including Main). Efficiency comes from the first sufficiently small delivery on the critical path,
not from waking every identity in the pool at once.

## 10. Authority index and the efficiency formula

| Topic | Authoritative path |
|---|---|
| startup orchestration | `main/50_playbook/startup_orchestration.md` |
| constitution entry | `main/t2ag.md` §3 |
| workspace entry | the `AGENTS.md` of the workspace and the current form |
| collaboration preferences | `agent_collaboration_preferences.v1` in `main/10_student/profile/profile.md` |
| pool and active semantics | `main/00_core/domain_model.md` |
| critical tool | `main/70_tools/t2ag_context.py --format critical` |

Operating mnemonic:

```text
parallel read-only branches x a first delivery small enough x zero duplication by Main x release the slot when done
!= piling on more agents
```

## 11. The entry-axis contract (entry.*)

The constitution `main/t2ag.md` §3 keeps only a pointer; the entry-axis contract body lives only in this
file. This axis is **not** the `session_lane` canonical (0a-4 / closeout §14.66 / §14.81): the four names
share wording, but the axes evolve independently. This file does not own `session_lane`.

The prefix token is fixed as **`entry.`** (AS-8; ruled where rulable). The four entries:

| Entry | I/O | Forbidden |
|---|---|---|
| `entry.teach` | course recovery + Scope | must not bypass the kernel |
| `entry.maintain` | does not trigger course recovery | must not bypass the kernel |
| `entry.audit` | read-only evidence; no recovery | must not bypass the kernel |
| `entry.release` | acquires no release authorization | must not bypass the kernel |

the prefix shared by the four entries contains only three items: reading `main/t2ag.md`, displaying the
welcome message per §0, and passing the existing `runtime.authorization` kernel (closeout §14.80; **no**
new check ID). After the branch point, only `entry.teach` runs course recovery, the Context Prefetcher
and the textbook Scope scan, and produces `learning-ready`; each entry obtains the `recovery-settled`
that applies to it before any write action. This axis dispatches no code and builds no new dispatcher.

## 12. rule_migration (DEC-3 A3 · constitution §3 sub-constraints)

Denominator = sub-constraints ≥18 (closeout §14.77 AS-5; where rulable: S3-10 split into 4, S3-13 into 2,
S3-09 into 4 timing/halt clauses). The table has 20 rows (S3-01..08 + S3-09a..d + S3-10a..d + S3-11 +
S3-12 + S3-13a..b). No retire. S3-03 / S3-12 undetermined-then-ruled sink. No new check ID. The A3
freeze batch did not edit `main/t2ag.md`; the closeout repair compresses §3 into entry pointers and the
immutable gates without changing this table's keep/sink rulings.

> Edition note (registered divergence): the literal grep evidence in the verification column binds
> against the zh canonical record (skeleton commit `040cdcf`); this edition records the same rulings at
> section level for its own files.

| rule_id | Old location/anchor | Action | New owner/equivalent gate | Consumer | Verification |
|---|---|---|---|---|---|
| S3-01 | constitution §3 "display the welcome message on every entry" | sink | `startup_orchestration.md` §0 | `main/bin/t2ag`; `80_interface/README.md`; `skin_playbook.md`; `first_run.md` (E1: zero doctor consumption) | §0 heading |
| S3-02 | constitution §3 "start the read-only recovery branches in parallel (Runtime Sentinel + Context Prefetcher)" | sink | `startup_orchestration.md` §1 / §3 | `AGENTS.md` startup entry (E1) | §1 command block |
| S3-03 | constitution §3 "never wait for all recovery checks before first feedback" | sink | `startup_orchestration.md` §3 / §4.1 (E1: equivalent body already present) | Main Conductor join (E1 T-08) | §3 body |
| S3-04 | constitution §3 "two observable states (criteria canonical §4.1/§4.2)" | keep | the constitution keeps the pointer; gates = §4.1 / §4.2 | startup sessions | constitution §3 pointer |
| S3-05 | constitution §3 `learning-ready` definition (exact stopping point; textbook Scope A1–A5/A6) | sink | `startup_orchestration.md` §4.1 | ADR-0003; `source_page_assets.md` §3.1 (E1) | §4.1 heading |
| S3-06 | constitution §3 "Snapshot / `content_consumed` / a historical receipt must never pose as this round" | sink | `startup_orchestration.md` §4.1 | `AGENTS.md` textbook scan gate (E1) | `content_consumed` in §4.1 |
| S3-07 | constitution §3 `recovery-settled` definition (doctor 0 FAIL, no drift, sources verified) | sink | `startup_orchestration.md` §4.2 | `t2ag_doctor.py --profile runtime`; `t2ag_state_refresh.py --check` (E1) | §4.2 criteria |
| S3-08 | constitution §3 "any progress write / checkpoint / terminal-RT3 / foreground switch / closure claim must wait for that state" | keep | constitutional canonical (closeout §14.80); machine leftover = existing `runtime.authorization` (§6.2); no new check | write paths; the A1 kernel (E1) | `runtime.authorization` in `validation_workflow.json` |
| S3-09a | constitution §3 "critical ≤10s" | sink | `startup_orchestration.md` §1 / §5 | startup orchestration (E1) | §5 timing row |
| S3-09b | constitution §3 "first content ≤15s" | sink | `startup_orchestration.md` §1 / §5 | startup orchestration (E1) | §5 timing row |
| S3-09c | constitution §3 "full background ≤45–60s" | sink | `startup_orchestration.md` §5 (machine cap = the written 45s, **not** the constitution's 45–60) | startup orchestration (E1) | §5 timing row |
| S3-09d | constitution §3 "a late blocker pauses further advance" | sink | `startup_orchestration.md` §5 | Main Conductor (E1) | §5 body |
| S3-10a | constitution §3 "uninitialized criteria and the initialization flow are canonical in first_run.md" | sink | `50_playbook/first_run.md` (criteria / steps sections) | `t2ag_init.py` (E1) | first_run criteria heading |
| S3-10b | constitution §3 "templates must come from 40_course/_templates/course/" | sink | `40_course/_templates/course/` (rulable split; the E1 composite owner was `first_run.md`) | `t2ag_init.py` / `first_run.md` (E1) | template README |
| S3-10c | constitution §3 "never pre-fill a real student number" | sink | `50_playbook/first_run.md` | `t2ag_init.py` (E1) | first_run body |
| S3-10d | constitution §3 "never auto-create .venv" | sink | `50_playbook/first_run.md` | `t2ag_init.py` (E1) | `venv` in first_run |
| S3-11 | constitution §3 routine-takeover canonical `context_packet.md` | keep | `50_playbook/context_packet.md`; enforcement = existing `runtime.context_packet` (rule_binding → the session_lane rule-loading section) | `runtime.context_packet` (E1: the only doctor-enforced takeover clause) | `runtime.context_packet` |
| S3-12 | constitution §3 "on runtime doctor FAIL repair local teaching state first; a release-side FAIL blocks only candidate and release" | sink | `50_playbook/doctor_contracts.md` (FAIL semantics canonical; rulable: undetermined → sink; no new doctor check) | runtime / release startup paths (E1) | doctor_contracts FAIL section |
| S3-13a | constitution §3 "while the cloud bridge is paused the cloud projection is read-only" | keep | `doctor_contracts.md` cloud-pause section; enforcement = existing `runtime.cloud_pause` | `runtime.cloud_pause` (E1) | `runtime.cloud_pause` |
| S3-13b | constitution §3 "when the context tool cannot run, do manual layered excerpting per lesson_recover.md; never fall back to undifferentiated full reads" | sink | `50_playbook/lesson_recover.md` | the degradation path (E1 T-13); `startup_orchestration.md` §5 | lesson_recover manual-excerpt steps |

**The four sinking-closure items** (shared by the whole table):

1. **New canonical owner**: sink rows above; keep rows stay canonical in the constitution or an existing
   playbook / existing check.
2. **Necessary entry pointers**: constitution §3 now keeps only the explicit entry declaration, the
   shared prefix, the state hard gates and the sunk-owner pointers.
3. **Consumers**: per the table. The doctor-enforced surface is still only S3-11
   (`runtime.context_packet`) and S3-13a (`runtime.cloud_pause`). The S3-08 machine leftover = the
   existing `runtime.authorization`.
4. **Verification evidence**: the table's verification column; all existing anchors or existing check
   IDs, no new ID.

**Unregistered-deletion review**: no retire. Items E1 initially judged sink/keep are all followed;
S3-03 / S3-12 sink where rulable, not retired.

## 13. Entry cutover (DEC-3 A6)

The contract body is §11; the constitution §3 sub-constraint migration table is §12 (20 rows, not
duplicated in this batch). This cutover changes only the startup calling surface: it dispatches no code,
builds no dispatcher, adds no check ID.

### 13.1 The two-axis declaration (the caller must fill both)

Whoever invokes "startup" must declare, **at the same time and separately**:

1. The **entry axis** token: `entry.teach` | `entry.maintain` | `entry.audit` | `entry.release` (§11).
2. **`session_lane`** (not owned by this file; 0a-4 / closeout §14.66 / §14.81). The two axes are
   independent; one word must not serve both.

`--profile runtime` / `--profile release` are **not** entries. That is the doctor profile axis (AS-7:
`--profile release` = 59 checks; orthogonal to the entry axis). A profile word must never be read as
`entry.*`.

### 13.2 Four-entry I/O (cutover)

| Entry | Allowed | Forbidden |
|---|---|---|
| `entry.teach` | **only this entry** may start course recovery + the textbook Scope scan (`first_run.md` / `t2ag_init.py`) | must not bypass the kernel |
| `entry.maintain` | runtime doctor + `state --check`; does **not** start course recovery | must not bypass the kernel |
| `entry.audit` | read-only evidence; does **not** start course recovery | must not bypass the kernel |
| `entry.release` | grants **no** release authorization | must not treat this entry as publish permission; doctor `--profile release` is another axis |

Write actions at every entry wait for `recovery-settled` (§4.2). kernel = the existing
`runtime.authorization` (§11 / closeout §14.80; no new check ID).

### 13.3 Protocol retirement

The implicit "run the full startup on every entry" **is retired by this protocol**. The caller must give
the entry-axis token explicitly; a missing token must not default to the full `entry.teach` recovery.

### 13.4 The 3.0 leftover anchors the original A6 batch did not edit

The original A6 batch did not edit the following anchors, which then still pointed at the constitution's
"3.0 startup welcome message"; A8 has since repointed all of them to this file's §0:

- `main/50_playbook/first_run.md`
- `main/50_playbook/skin_playbook.md`
- `main/80_interface/README.md`
- `main/bin/t2ag`

The original A6 write face was `startup_orchestration.md` only. The closeout repair separately repoints
`t2ag.md` and the active `AGENTS.md` call sites; it still does not touch doctor, the `--profile` call
sites, or zh/EN/Lite.

## 14. The polarity matrix (DEC-3 A7)

The contract / cutover / rule_migration bodies are §11–§13; this table does not restate them, it only
records polarity.

| Polarity | Proposition |
|---|---|
| + | `entry.teach` starts course recovery + Scope |
| − | `entry.maintain` / `entry.audit` do not start course recovery |
| − | `entry.release` grants no release authorization |
| − | `--profile` is not an entry (the doctor profile axis, orthogonal to the entry axis) |
| − | a missing entry token must not default to the full teach recovery |
| − | write actions always wait for `recovery-settled` |
| − | kernel = the existing `runtime.authorization` (no new check ID) |
