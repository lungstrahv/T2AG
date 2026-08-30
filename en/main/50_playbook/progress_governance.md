# Progress presentation governance (`progress_governance`)

**Protection level**: meta-playbook

> **Role**: the canonical presentation boundary between Learner Surface and Operator Surface and
> the canonical governance of Meaningful Pauses (EV-0034; PG-D0=A). It governs what the learner
> sees, in what order, when a pause is mandatory, and when internal information may be exposed.
> **Non-role**: progress facts belong to `progress_tracking.md`; gate semantics and the gate index
> belong to `main/00_core/gate_index.md`; admission, revision, and retirement of process objects
> belong to `process_governance.md`; each journey's procedure remains in its original playbook.
> This file never copies state truth or gate-semantics body text.
> **Edition status**: PG9 promoted this file to meta-playbook and projected it across Main, Chinese
> Skeleton, and English Skeleton. The English edition is concept-equivalent, not byte-identical.

## 1. Domain language (consumed, not redefined)

The canonical definitions of **Learner Surface**, **Operator Surface**, **Meaningful Pause**, and
**Learner Journey Contract** are in the root `CONTEXT.md`. This file consumes those definitions and
creates no second glossary. Any wording fork must be repaired in favor of `CONTEXT.md`.

## 2. Presentation invariants

1. **The learner decides experience; the machine implements decisions.** Mapping, notarizing,
   refreshing, and checking an already-confirmed plan are not new decisions and receive no new gate.
2. **Facts have no defaults.** Learning level, foundation, goals, time, tool habits, Course Type,
   Learning Mode, and real entry point may not be manufactured from machine defaults. Learner facts
   have three states only: provided, not provided, or explicit assumption. A neutral form of address
   may use a fallback.
3. **Binding is not display.** Event IDs, SHA values, schemas, and internal status codes may be
   integrity conditions but are not default learner copy. On a requested diagnosis or conflict,
   explain impact and choices in natural language first; expand the technical appendix only as needed.
4. **Every pause must answer what different learner responses change.** Remove a pause that cannot
   answer that question, or demote it to an internal step.
5. **Recovery obeys this turn's intent.** When the learner explicitly said continue this turn, do not
   ask for generic continuation again. Only a conflict, new scope, or an unexpressed real choice pauses.
6. **Diagnostics are progressively disclosed.** Default to result, impact, and possible actions.
   Internal IDs, file lists, test counts, and full WARN text appear only for blocker handling, audit,
   or at the learner's request.
7. **One canonical owner per user journey.** README, INSTALL, and Edition documents may project or
   point to a governed journey, but may not own their own pause sequence or defaults.
8. **Audit semantic gates separately from conversational turns.** Preserving a safety gate does not
   automatically create a mechanical question, but independent waits required by the constitution
   cannot be merged. Exact authorization for deletion, external writes, release, and terminal RT3 is
   never weakened by experience work.

## 3. Governed surfaces and pointers

The eight journey surfaces are installation, first run, course/group creation, recovery, teaching,
session close, cloud sync, and maintenance receipts. Their procedures remain owned by:

- first run: `first_run.md` and `t2ag_flow.md`;
- recovery: `lesson_recover.md` and `startup_orchestration.md`;
- session close: `session_close.md`;
- cloud sync: `cloud_learning_sync.md`;
- course/group creation: `new_course_init.md` and `course_group_rules.md`.

For a presentation question, this file decides; for a procedural question, the owning playbook
decides. Journey pause-count budgets remain product hypotheses and are not copied here.

## 4. Adjudicated results

- **PG-D1=A**: retain the three gates between teaching blocks and their independent waits. Not asking
  is not evidence that there was no problem. The block-transition protocol, gate semantics, and
  `gate_visibility` boundary are not weakened.
- **PG-D2=A+G**: retain the complete coverage checklist and use progressive display by default.
  `lesson_tree_display_mode` may be `progressive | full`. A compact summary derives a deterministic
  cursor from the same complete tree; both modes traverse in order until every block has a terminal
  status. Dual PDF/in-book page numbers and the four page-turn beats remain unchanged.

## 5. Enforcement declarations

PG8 established the machine landing point for the renderer surface:
`70_tools/learner_journey.py` is the single canonical owner of learner copy,
`70_tools/learner_journey_scenarios.json` fixes six scenarios, and
`contracts.learner_journey` checks structured events, pause ownership, state/disk results, zero
partial writes, and Operator-token leakage. Tools produce structured results and Operator messages;
live model conversation remains `model_dependent`.

enforcement: check=runtime.playbook_taxonomy
enforcement: context=50_playbook/first_run.md#Learner-visible states and pauses
enforcement: context=50_playbook/lesson_recover.md#confirm with the student
enforcement: context=50_playbook/session_close.md#The close domain tree and applicability
enforcement: context=50_playbook/cloud_learning_sync.md#Conflict adjudication and degraded modes
enforcement: context=50_playbook/course_group_rules.md#for a second user decision
enforcement: tool=70_tools/learner_journey.py

For PG2, the repository carries machine evidence for the three-state defaults and the two-pause,
no-start-gate structure in `t2ag_init.py` and `contract_test_support.py`. Installer behavior is not
shipped in this repository and remains honestly prose-enforced.

enforcement: tool=70_tools/t2ag_init.py
enforcement: tool=70_tools/contract_test_support.py
enforcement: prose_accepted (reason: installer behavior is outside this repository)

For PG3, required semantic arguments and activation preflight live in `t2ag_init.py`, share criteria
with `t2ag_doctor.py`, and are asserted by `contract_test_support.py` and `runtime.groups`. The live
conversation boundary is covered only at renderer level by `contracts.learner_journey`.

enforcement: check=runtime.groups
enforcement: tool=70_tools/t2ag_init.py
enforcement: tool=70_tools/contract_test_support.py
enforcement: context=50_playbook/course_group_rules.md#for a second user decision
enforcement: prose_accepted (reason: live model conversation remains model-dependent)

For PG4, `lesson_recover.md` carries the local behavior and `contract_test_support.py` locks its
vocabulary, pointer, and conditional wording. Live-model behavior and cloud recovery delegated to C4
are not posed as covered.

enforcement: tool=70_tools/contract_test_support.py
enforcement: context=50_playbook/lesson_recover.md#confirm with the student
enforcement: context=50_playbook/lesson_recover.md#Stop on conflict
enforcement: prose_accepted (reason: live local presentation and C4 cloud behavior lack this batch's black-box carrier)

For PG6, `activity_close.py`, `test_022_close_roundtrip.py`, and `contract_test_support.py` enforce the
learner retrospective, internal binding, explicit tuple, and fail-before-write route checks. A live
model separately reading an Operator payload aloud remains outside the machine claim.

enforcement: tool=70_tools/activity_close.py
enforcement: tool=70_tools/test_022_close_roundtrip.py
enforcement: tool=70_tools/contract_test_support.py
enforcement: context=50_playbook/session_close.md#generate the pending, decide strictly, and write back transactionally
enforcement: prose_accepted (reason: tool rendering is testable; live-model leakage is not)

## 6. Rule migration

The canonical body was added without deleting, merging, moving, or retiring existing rules. Any
future sink from journey playbooks into this file requires an exact migration-table amendment.

## 7. Installation and first-run presentation (PG2)

This section governs how installation and first planning are seen. Procedure remains in
`first_run.md` and its derived `t2ag_flow.md`; the installer itself is outside this repository.

### 7.1 Three states for learner facts

| State | Criterion | Internal shape | Learner-visible wording |
|---|---|---|---|
| provided | stated by the learner | mapped learner statement | restate it directly |
| not provided | not stated and no assumption is needed | `not_provided` | “not provided” |
| explicit assumption | not stated but a provisional choice is needed | value marked as assumption | show it in the plan and say it can change |

Machine defaults are operating parameters only. They never occupy “provided” and never become a
learner statement. If an unstated field has a value, it is either an operating parameter or an
explicit assumption; there is no third legal form. Storage shapes are owned by
`answers.schema.json` and `t2ag_init.py`.

### 7.2 Pause structure

- **Pause A | Add conditions**: optional profile and planning conditions are one natural conversation,
  not two blocking questionnaires. Enough information, a request to draft now, or an empty reply ends it.
- **Pause B | Review the plan**: present the complete plan, including explicit assumptions, then explain
  Course Type and applicable Learning Modes; wait for confirmation or revision.
- The internal write sequence (`init → new-course → new-group → plan mapping → activate-group → refresh
  → doctor`) creates no learner pause. Command receipts, planned→active, and non-blocking warnings are
  not confirmation gates.
- Completion is not a third pause. Give the first action and begin it; do not ask “start now?”.

This section sets no numeric journey budget and does not weaken teaching-block waits or source display.

### 7.3 Release-source retention (F09)

The copied release-source directory is retained by default. Completion may say it can be cleaned up
later but does not ask to delete it. Deletion occurs only after the learner raises it and gives the
separate destructive confirmation. Public entry points project this one rule and own no alternative.

**Rule migration**: not applicable; this is an additive projection of the same behavior.

## 8. Course/group creation presentation (PG3)

### 8.1 Semantic parameters are required when a default would answer for the learner

| Criterion | Rule | Current examples |
|---|---|---|
| one correct answer the model cannot infer | required, no default | `--source-language`, `--container-mode` |
| a default would manufacture a learning fact | required | `--course-type`, `--entry`, `--verification-status` |
| no single right answer; must be settled ceremonially | no CLI parameter; visible `TBD` | the three container parameters |
| protected by an interlocking invariant | a default may remain | `--lifecycle` with `--entry` |

`--verification-status` is strongest: a default would falsely claim human verification.
`--learning-mode` is not universally required because its Mastery/non-Mastery invariant already rejects
invalid combinations. Required flags remain internal mappings of the confirmed plan, not learner copy.

### 8.2 `planned → active` is internal notarization

Activation is not a Meaningful Pause. A preflight refusal defaults to internal correction. Only when the
confirmed plan lacks route-changing information does the flow return to Pause B with a revised plan; it
must never ask “confirm activation”.

### 8.3 Refuse once and report all blockers

Preflight evaluates and reports all blockers together and shares criteria exactly with Doctor. A criterion
may move earlier only when it fires on active state and is decidable at activation time. Review and calendar
are written before plan, because `plan.md status: active` is the Doctor's activation signal. This ordering
prevents a failed operation from leaving a self-declared active group, but is not transaction atomicity.

### 8.4 Refusals and notices are Operator Surface

Preflight codes, paths, blocker/notice levels, and stdout receipts are Operator information. Learner copy
explains the missing plan condition in natural language. A notice is neither a refusal nor a pause.

**Rule migration**: not applicable; no current rule is removed or relocated.

## 9. Local recovery presentation (PG4)

The canonical key is `turn_intent`, with exactly four values:

| Value | Criterion | Local pause and exit |
|---|---|---|
| `explicit_continue` | learner explicitly requested continuation this turn | summarize the point and execute the next authoritative action; no generic pause |
| `ambiguous_resume` | recovery requested, but continue vs review is unknown | pause once and show both result-changing choices |
| `conflict_resolution` | route, progress, Activity, current page asset, or Scope identity conflicts | stop; explain choices and impact in natural language; expand internal details only as needed |
| `new_scope` | request leaves the current recovery scope | never reuse old continuation; enter the new scope's normal authorization gate |

This table governs local recovery only. Cloud recovery remains `dependency_closed → C4`. Quiet gate
visibility does not waive a real recovery authorization, and authorization never crosses recovery points.

**Rule migration**: not applicable; the existing behavior gains one taxonomy and owner.

## 10. Session-close Learner Surface and explicit safety objects (PG6)

Learner copy shows only the complete retrospective, the natural-language meaning of the result, and up to
three learner actions. Event IDs, body/presentation SHA values, receipts, schema, and internal state codes
remain strictly bound on Operator Surface and are disclosed progressively only for diagnosis or conflict.

Completion states are translated into natural language. The available actions are: confirm the terminal
result, identify retrospective content to revise, or continue filling gaps / do not close yet. A short
“close” binds only the unique, fully displayed, undrifted pending event; hiding the tuple weakens none of
the ambiguity, drift, invalidation, or direct-user terminal authorization checks.

`--plan-pending` and `--plan-decision` require the complete course/type/id tuple and validate the current
route before creating any plan file. `--plan-reopen` also requires a tuple but may target a historical
terminal activity in the same course ledger. `--parse-confirm` and `--apply` do not consume that tuple.
Real terminal apply remains RT3 and is not authorized by this section.

**Rule migration**: `PG-R003 = narrow`; exact tuple display moved from learner copy to internal binding,
while the full retrospective and fail-before-write tests preserve the safety outcome.

## 11. Operator Result Envelope (PG7)

The six CLI families that enter Agent context — init, Doctor, state refresh, context, activity close, and
cloud sync — emit a neutral `t2ag.operator_result.v1` sidecar in addition to existing stdout. `audience`
is always `operator`; machine code, Operator message, and `structured_result` are separate. The sidecar is
stderr and must never be forwarded wholesale to the learner.

`70_tools/operator_result.py` owns the neutral envelope and contains no learner copy or renderer import.
An upper orchestrator may pass only `structured_result` to `learner_journey.py`. Doctor remains a pure
Operator producer and neither calls nor owns the renderer. Error families are stable at
`T2AG.<TOOL>.ERROR`; domain finding codes remain with their existing owners.

enforcement: tool=70_tools/operator_result.py
enforcement: tool=70_tools/test_operator_result_contracts.py

**Rule migration**: not applicable; the sidecar is additive and changes no stdout, algorithm, write order,
check set, or learner copy.
