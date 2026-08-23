# Handoff context management

**Protection level**: core-playbook

> This file governs context handoff across conversations, agents and maintainers: when to create a handoff, how to index it, how to preserve the continuity of reasoning from long conversations, how to verify against the formal source of truth, and when to close or archive it.
>
> **Applies to**: a course or implementation task that has not closed while the conversation must change; the user explicitly asking for a handoff; several long conversations forming a discussion trail later decisions cannot do without; a project, topic or maintenance task being handed over.
>
> **Core positioning**: a handoff is recovery evidence and task routing. It is not a rule source, not a progress source of truth, and not a substitute for historical text.

---

## 1. Goals and non-goals

### 1.1 Goals

- Let whoever takes over know the current state, the unclosed items and the next action quickly.
- Preserve the discussion trail that determined the user's intent and the choice of approach, avoiding "the task continues but the reasoning is severed".
- Load only the handoffs relevant to the task scope, avoiding indiscriminate swallowing of all history.
- Give a handoff an explicit lifecycle: creation, activation, verification, closure, supersession, archiving.
- Always return to the formal source of truth during recovery; forming a second authority chain is forbidden.

### 1.2 Non-goals

- Not copying every normally-ended conversation into a handoff.
- Not storing a full copy of what can be read directly from the formal files.
- Not defining a permanent rule in a handoff document; a rule must be written back into the constitution, a playbook, a course `progress.md`, or another formal definition source.
- Not treating "shorter is better" as a quality goal, and not accepting it by how many seconds a model takes to read it.
- Not requiring a skeleton or lite to carry instance handoffs by default; they carry only this generic process.
- Not calling every file in `<handoff_root>` a Handoff; a workorder, plan, evidence, review, release backlog and archive are merely supporting material in the same directory.

---

## 2. Basic concepts

### 2.1 handoff root

`<handoff_root>` is the handoff directory agreed for the current workspace, named by an entry file, a project description, or the user. Common locations are the workspace `docs/handoffs/` or an in-instance `docs/handoffs/`.

Resolution order:

1. A path explicitly given by the user or an entry file.
2. A handoff directory that already exists in the current workspace and is registered by the project description.
3. An existing `docs/handoffs/` inside the current instance.
4. When none exists, there is no handoff system right now; a new one is created only when this process's creation trigger fires and the current task has write authorization — never automatically on an ordinary startup.

One startup may resolve exactly one runtime `<handoff_root>`. When the workspace entry has already registered a handoff directory, an in-instance `docs/handoffs/` of the same name may only be a release projection or a supporting-material directory; its `README.md` must state plainly that it is **not the runtime index** and point at the single runtime index, and must never copy the `Active Handoffs` table. When doctor runs the release handoff check on Main, it must refuse such a shadow index.

`<handoff_root>/README.md` is the index entry point. The directory may stay flat, or be layered as `active/`, `topics/`, `archive/`; the index fields and lifecycle do not change with directory shape. Never move a historical file that outside links still reference merely for tidiness.

`handoffs/` is a physical container name formed by history, not a domain type declaration. Whether something is a real Handoff depends only on `artifact_role`; sitting in that directory, having report/workorder/review in its filename, or being referenced by some Handoff, none of these admit a file to the recovery route.

### 2.2 scope

Legal scopes:

- `course_session`: a specific unclosed course/lesson session.
- `project`: a project architecture, release, maintenance or implementation handoff.
- `topic`: a topic that keeps evolving across several conversations.
- `implementation`: a specific change batch not yet finished or not yet verified.

There is at most one `active` handoff per `(scope, applies_to)`. The same task refreshes in place by default; the user may also ask for a new handoff by hand. A new file must not be empty, and only after its content is complete, a takeover rehearsal passes, and the index is written, is the old file marked `superseded` with bidirectional pointers established.

### 2.3 lane

`lane` answers "which work channel this cross-conversation material belongs to":

- `learning`: a course, Lesson, Exercise or study session.
- `maintenance`: routine maintenance, local repairs and unfinished small problems.
- `topic_design`: a sustained topic, conceptual design and multi-round discussion.
- `version_campaign`: a version upgrade, a frozen candidate, a migration and a formal release.

scope and lane are orthogonal dimensions. An unfinished local tool repair may be
`scope=implementation + lane=maintenance`; an Activity Close design may be
`scope=topic + lane=version_campaign`.

Orthogonal does not mean mixable: one Handoff belongs to exactly one lane. When a maintenance work order is discovered during course recovery, the course facts stay in `course_session + learning` and the maintenance item moves into a separate Handoff or work order under `implementation/project + maintenance`; the two are linked, and a compound `applies_to` must never be used to obtain both startup routes at once.

### 2.4 artifact_role

`artifact_role` answers "what part this file plays in the workflow":

- `handoff`: a recovery and routing file; only this role may enter Active Handoffs.
- `workorder`: construction requirements, the definition of done, and the authorization boundary.
- `plan`: a plan, the frozen objects, a baseline or a manifest.
- `evidence`: actual execution results, receipts, reports and reusable SHAs.
- `review`: an independent review, a checklist, or an adjudication conclusion.
- `release_backlog`: deferred verification or release to-dos handled only at the next frozen candidate.
- `archive`: for historical reference only.

Supporting material may carry a `+`-combined role such as `evidence + release_backlog`; a real Handoff must carry exactly `artifact_role=handoff`. A workorder, plan, evidence, review or release_backlog must never disguise itself as `status=active` to gain startup read priority.

### 2.5 status

Legal states:

```text
active -> resolved -> archived
   |----> superseded
   |----> stale
```

- `active`: an unclosed, executable task exists, the applicable baseline is still compatible, and the next action and closing condition are explicit.
- `resolved`: the formal source has been written back and verified, and the handoff no longer takes part in recovery.
- `superseded`: replaced by a newer, more precise handoff.
- `stale`: still of historical value, but the baseline, path or next step has expired; executing it directly is forbidden.
- `archived`: for historical reference only.

A state must never be inferred from a date alone; it must be written explicitly in the document and in the index.

A handoff's content state and its size aging are recorded separately. The legal `aging_state` values are `normal / check_1 / check_2 / old`, and `old` must never stand in for `resolved` or `superseded`.

### 2.6 Minimum sufficient context

The optimization goal of a handoff is "maximum continuity of reasoning within a limited context", not the fewest words.

The retention criterion:

> If this passage were deleted, could whoever takes over end up with a different understanding of the user's intent, the current conclusion, the reason for the approach, a risk, or the next decision?

If yes, keep it; if no and the formal source already holds it, turn it into a pointer or delete the duplicate.

---

## 3. Creation and reading triggers

### 3.1 Creating a handoff

Create or update a handoff when any of these holds:

1. The user explicitly asks for a handoff document.
2. A course, implementation or maintenance matter has not closed, yet the conversation, agent or maintainer must change.
3. An unexpected interruption left the formal source of truth unwritten while the lesson, workspace or current conversation holds finer evidence.
4. Several long conversations formed a discussion trail later decisions depend on, which an ordinary state pointer cannot preserve with its reasons and evolution.
5. A complex change has happened but verification is incomplete, so the change scope, risks and verification entry point must be handed over explicitly.

By default, do not create one when:

- `session_close` completed normally and the formal source, caches and verification all closed.
- Only the current state needs reporting, with no cross-conversation handover.
- The content merely duplicates a formal file.
- There is no open question, no unverified change, and no discussion trail worth keeping.

### 3.2 Reading a handoff

Read one only when all of these hold:

1. The current task scope has been identified.
2. The index has an `active` entry matching that task.
3. The handoff's `applies_to` matches the current course, project, topic or implementation batch.

With no match, read no handoff. A newer date on some file must never cause an unrelated topic handoff to be loaded into ordinary course teaching.

Typical routing:

| Situation | Reading behaviour |
|---|---|
| resuming a course that never ran `session_close` | read the matching active `course_session` handoff |
| continuing a course whose close write-back completed normally | read no historical classroom handoff; go memory -> progress -> the explicit activity route |
| maintaining the project architecture | read the matching active `project` handoff |
| resuming a topic design | read the matching active `topic` handoff |
| the current task has no active handoff | skip every unrelated handoff |

---

## 4. The handoff document data contract

The top of every handoff contains at least:

```markdown
> **handoff_id**: stable and unique
> **scope**: course_session / project / topic / implementation
> **lane**: learning / maintenance / topic_design / version_campaign
> **artifact_role**: handoff
> **applies_to**: the course, lesson, project, topic or implementation batch
> **status**: active / resolved / superseded / archived
> **aging_state**: normal / check_1 / check_2 / old
> **task_match**: which task needs to read it
> **created_at**: a timezone-bearing time
> **updated_at**: a timezone-bearing time
> **version_context**: the applicable project/release version; write — when none
> **supersedes**: the handoff replaced; write — when none
> **superseded_by**: the replacement; write — when none
> **close_condition**: what fact makes resolved possible
> **canonical_sources**: paths of the formal rule, progress or state sources
> **next_action**: the next directly executable action
> **semantic_check**: the most recent four-question recovery check and its result
```

Paths use a stable relative path from the current workspace or instance root; a generic handoff must never carry a private absolute path. When a time, version or path is unknown, write `—` explicitly and never guess.

---

## 5. The layered content structure

Every `active` Handoff must carry at least the two explicit headings "minimum state summary" and "continuity summary", so whoever takes over can read in layers. Even a simple task with no additional discussion line must state in the continuity summary that there is no additional line to recover; a missing section must never leave the taker guessing whether it was empty or omitted.

### 5.1 Layer one: the minimum state summary

This section is for locating and does not carry the whole context. Twelve short lines is a good ceiling, and it answers at least:

```text
scope
status
the exact stopping point or the current stage
what is done
what is not written back or not verified
current risk / blocker
the single next action
the formal sources
```

"One-minute summary" is not a formal term; a model's read time cannot be accepted reliably. The formal name of this section is the **minimum state summary**.

### 5.2 Layer two: the continuity summary

When a task has passed through several long conversations, had its concepts clarified step by step, or turned direction more than once, this section must exist. It has no hard "shorter is better" budget and keeps, by relevance, every core discussion point that would change later understanding.

Each "discussion line" should contain:

```text
origin: what was originally being asked
evolution: which key counterexamples, clarifications or turns it passed through
current understanding: what conclusion is now accepted
reason: why it is accepted
rejected approaches: what was rejected and why
key wording from the user: a small amount of accurate phrasing where needed
open questions: what still needs adjudication next round
```

Discussion lines are chosen by relevance to the task, never mechanically limited to the last N conversations. An older discussion that still determines the current direction must be kept; a recent but decision-free repeated confirmation may be omitted.

### 5.3 Layer three: operations and evidence

Record by task type:

- files changed, unchanged, and that must not be changed.
- verifications run and not yet run.
- actual errors, workspace state, failing output and risks.
- the exact textbook page in a course, the lesson evidence, the student's confirmation state.
- design adjudications, interfaces, migrations or compatibility boundaries in a project.

Write only what has been observed; keep plans and completion status in separate columns, and never write a candidate approach as implemented.

### 5.4 Layer four: detailed history and the entry point to raw material

The full text of a long conversation, detailed terminal output, a complete design draft or a historical snapshot are stored on demand in an appendix, a topic file or the raw record. This layer supplies the link and the expansion condition; it does not require a full read on every takeover.

### 5.5 Size aging and the semantic recovery check

A handoff is checked each time it reaches 350 lines or 30,000 characters:

| Threshold | aging_state | Behaviour |
|---|---|---|
| 350 lines or 30,000 characters | `check_1` | run the four-question check; refreshing in place is allowed |
| 700 lines or 60,000 characters | `check_2` | check again, and recommend generating a replacement handoff |
| 1,000 lines or 90,000 characters | `old` | a non-empty replacement handoff must be generated and verified before the old active is retired |

The four-question check is answered by the taking-over agent:

1. What is the current unclosed task?
2. What is the single next executable action?
3. Which formal sources must be verified first?
4. What fact makes closure possible?

Doctor is responsible only for mechanical checks — line count, character count, fields and the index; the four answers are the agent's judgement. When any of them cannot be answered reliably, the handoff must not continue as an active execution entry point: repair it in place or generate a new one.

### 5.6 Verifiable assertions and their recomputation source

This section is written in two layers: first what must be proven, then which evidence forms count. The two must never be merged.

#### 5.6.1 What must be proven

**A verifiable assertion must carry a recomputation source.** Wherever the handoff body states a count, an existence claim or a hash ("N files", "zero hits", "the sha is X"), a directly executable recomputation command must appear on the same line or the line immediately after, in the form `assertion <- command`. Whoever takes over treats such an assertion without a recomputation source as unproven, and it must never be a basis for a decision. Prose description ("this batch of changes is small") is not bound by this clause.

What must be proven is that **the taker can independently replay the same number**, not that "the person writing the handoff saw that number at the time". So the recomputation source must be directly executable by the taker in their own environment, never "I ran it back then".

#### 5.6.2 Which evidence forms count

Any of these may be the recomputation source on the right of `<-`:

| Form | Example | Accounting requirement |
|---|---|---|
| a directly executable shell command | `git status --porcelain \| wc -l` | pasteable as written; no alias that exists only on one machine |
| a directly executable repository tool command | `python -B main/70_tools/t2ag_doctor.py --profile runtime` | the profile/arguments must be stated and the output lines identifiable |
| a file path + a content anchor | `grep -n "EA-0001" main/50_playbook/environment_assumptions.md` | use a content anchor, not a line number |
| a frozen receipt/manifest file | `docs/handoffs/XXX_sha_table.json` | give a locating key inside the file, not just the filename |

This list is extensible. A new form must declare how it is accounted for at the same time, or it must not be used.

#### 5.6.3 The taker's obligation

On takeover, **spot-check at least one** assertion carrying a recomputation source, and state in the first report which one was checked and whether the result agreed. Only when everything agrees may the handoff's conclusions be cited; on disagreement, stop advancing immediately and follow §9.

The point of the spot check is falsification, not ceremony: prefer the assertion the **conclusion leans on hardest**, not the one that is easiest to run.

#### 5.6.4 Quotation and paraphrase

Quoting this section's trigger words ("N items", "zero hits", "the sha is X") while **not** asserting the current state — restating a historical lesson, or citing a rule verbatim — still raises a WARN from `release.handoff`. That is deliberate: a mechanical gate does not distinguish tone. The resolution is to reword or to add a `<-` source, never to add an exemption to the gate.

---

## 6. Index rules

`<handoff_root>/README.md` is both the recovery route and the supporting-material directory, but the two must be partitioned. Recommended format:

```markdown
## Active Handoffs

| handoff_id | scope | lane | artifact_role | status | applies_to | task_match | updated_at | File | close_condition |
|---|---|---|---|---|---|---|---|---|---|

## Next-version backlog

| id | lane | artifact_role | status | File | trigger |
|---|---|---|---|---|---|

## Workorders / Plans

## Evidence / Reviews

## Resolved / Archive Handoffs

| handoff_id | scope | lane | artifact_role | status | applies_to | File | replaced/resolved by |
|---|---|---|---|---|---|---|---|
```

Index rules:

1. Filter first by `artifact_role=handoff + status=active`, then match the current task's `lane`, `scope` and `applies_to`.
2. Do not establish a global "newest first" ordering across scopes.
3. A topic handoff never automatically outranks a course or project handoff because its date is newer.
4. `resolved`, `superseded`, `stale` and `archived` take no part in daily recovery and are expanded only when checking history.
5. Update the index in the same batch as a file is created, renamed, superseded or closed.
6. The index never copies handoff body text; it stores routing and lifecycle fields only.
7. `release_backlog` is read only at an explicit frozen candidate or a formal release, and must never enter Active Handoffs.
8. A historical flat directory may stay; fix the terminology and the index first. Move files only when every reference is under control and a migration plan exists.
9. **One index row may carry several files.** The work order, adjudication, read-only report and construction report produced by one order may be registered as a single row; a row per artifact is unnecessary. The index exists for discoverability, not one-file-one-record; raising the accounting cost only makes people skip the accounting.
10. **Into the drawer means into the accounts.** Putting a file into `<handoff_root>` and writing its index row are one action, not two. "Leave it for now, backfill the index later" is not an acceptable intermediate state — once the backfill window opens it never closes; see §6.1.
11. **Not indexing is also a registration.** A file with a real reason not to be registered (a temporary draft, an artifact delivered outward) must either move out of `<handoff_root>`, or have one explicit row in the index saying why it takes no part in routing. **Lying silently in the drawer is not a disposition.**

### 6.1 Index consistency needs a mechanical backstop

"Update the index in the same batch" (rule 5) is a prose clause. A prose clause does not fail loudly; it accumulates — **every orphan file is one bypassed rule, and bypassing a rule produces no signal at all.**

Therefore: index consistency for `<handoff_root>` must have an executable check, and that check must hang on a channel **proven to actually run every day** (a routine morning brief, the startup flow, or CI), not "run it by hand when needed". Hanging it where nobody runs it is equivalent to not having it.

The minimum contract (checks are extensible; these three are mandatory):

| ID | Check | Meaning |
|---|---|---|
| index orphan | every top-level file in `<handoff_root>` is referenced by the index | the file exists but is undiscoverable |
| index dangling | every local path the index references really exists | the index points at a corpse |
| subdirectory unmentioned | every subdirectory is mentioned by the index at least once | a whole body of material is undiscoverable |

The executor is registered by the workspace and is not named by this process: doctor has jurisdiction only over its own repo, and a workspace-level `<handoff_root>` must be backstopped by the workspace's own channel. The severity is WARN — it reports accounting debt, not a correctness error, and must not block the current task.

The instrument **must be red-tested**: manufacture an orphan and a dangling reference, confirm the check really reports them, then clean up. An untested check and a prose clause are the same thing — both merely claim to be working.

**A known coverage hole is written on the instrument itself.** A mechanical check cannot verify "whether the index description is true" (a wrong status or a mis-assigned role passes either way). What it cannot check must be stated explicitly in the script header, never left to silence to imply coverage.

---

## 7. The creation flow

1. **Confirm the trigger**: state why the ordinary formal sources are insufficient for this cross-conversation recovery.
2. **Resolve the handoff root**: locate the existing index per §2.1; never create a directory automatically on an ordinary startup.
3. **Identify lane, scope and applies_to**: fix the work channel and task scope, and check whether an active Handoff of the same scope already exists; the same task refreshes in place by default.
4. **Verify the formal sources**: read the canonical sources, the actual files, and any necessary workspace state.
5. **Separate fact from plan**: list what is done, not done, unverified, and awaiting adjudication.
6. **Write the metadata**: a stable handoff_id, the status, the closing condition and the supersession relations.
7. **Write the minimum state summary**: for quick locating only; never let it replace the continuity that follows.
8. **Write the continuity summary**: gather the discussion lines, reasons and open questions from earlier long conversations that still affect the current judgement.
9. **Write operations and evidence**: store the exact stopping point, the files, the verifications, the risks, and the entry point to raw material.
10. **Update the index**: register only `artifact_role=handoff + status=active` into Active Handoffs; when superseding an old handoff, first verify the new file is non-empty and recoverable, then update the old file's status and the bidirectional pointers.
11. **Run the authority-chain check**: delete any wording implying "a handoff automatically overrides the source of truth", replacing it with a verify-and-repair flow.
12. **Run the takeover rehearsal**: read only the index, the minimum state summary and the continuity summary, and check whether a taker can decide the next step without misusing an unrelated handoff.

---

## 8. The reading and recovery flow

1. Identify the current task; do not read the whole handoff root first.
2. Read the index and filter only matching `handoff + active` entries.
3. Read the minimum state summary first and confirm the scope, risks and next step.
4. Where user intent, design reasons or multi-round conceptual evolution are involved, then read the continuity summary.
5. Check whether the version, update time, applicable object and canonical sources still exist.
6. Read the formal source of truth and any necessary fine-grained evidence.
7. If they agree, continue from the formal source; the handoff only supplements context and open items.
8. If they conflict, pause advancing and repair per §9; never adopt the handoff's conclusion directly.
9. Expand detailed history or raw material only when a detail must be checked.
10. After the task, check whether the handoff reached its close_condition, and confirm per the §10.1 preconditions that the file holds no un-migrated open item.

### 8.1 The post-recovery action authorization gate

Reading and recovery are themselves read-only. Once the taker has read, the first output must be three things: a restatement of the minimum state, a list of the actions intended, and the authorization source each action rests on. Until the user responds to that list, no file may be written — including creating a work order, registering an index row, appending to a changelog, or creating a file "just to leave a trace".

There are only two legal forms of authorization source:

| Source | Effect |
|---|---|
| a user instruction this round | covers only what it literally names, and only actions specifically listed in the same round |
| a Handoff's `authorization` field | a historical record proving "what was approved at the time"; **does not constitute permission for this round** |

Therefore:

1. **A general acknowledgement covers only the actions specifically listed this round.** "Do what you recommend", "ok", "continue" inherit the one list they respond to and must never expand into construction outside it; where no list exists, such a response authorizes continued reporting only, never a write.
2. When citing a Handoff's `authorization` field, determine whether it has been consumed or is still unused. An unused historical authorization must equally be re-confirmed by the user this round and must never activate itself across conversations.
3. An object needing independent adjudication must never be chosen on the user's behalf, even where the Handoff names a recommendation: a licence choice, a version bump, a directory migration, deleting or moving a historical file, registering a new EV, and judging a re-review closed.
4. Once out of bounds, do not silently continue: stop construction, report the list of files already written and the point of overstep, and wait for the user to adjudicate keeping or rolling back.

This gate shares a root with `batch_workorder_spec.md`'s "Authorization is non-amplifying". That section governs not widening scope inside a work order; this one governs not starting work on a historical authorization or a general phrase during cross-conversation recovery.

---

## 9. The authority chain and conflict repair

### 9.1 General rules

A handoff document is never the formal source of truth. It can prove "what was observed at the time, what was discussed, which write-backs have not happened", but it cannot change project state on its own.

On conflict:

```text
the handoff / conversation / fine-grained record supplies recovery evidence
-> read the formal source of truth
-> verify against a finer file or the actual workspace
-> confirm with the user where needed
-> repair the formal source of truth
-> refresh the caches
-> then continue the task
```

### 9.2 The course case

`progress.md` always owns the Course lifecycle, the single foreground and the stopping point, and `activity_ledger.md` always owns the Activity lifecycle. A classroom handoff from a session that never ran `session_close` can only indicate that those separated sources of truth may be behind.

If the current activity main carrier (Lesson or Exercise) or the handoff shows finer progress:

1. Pause teaching new content.
2. Compare, via the explicit activity route, the current main carrier, the corresponding textbook/problem evidence and the student's explicit confirmation record; a historical Lesson can never stand in for the current Exercise.
3. Verify the actual completion point with the student.
4. Repair `progress.md`'s `activity_position` first, then refresh the memory/learning_path GENERATED caches.
5. Continue the course after the repair; never let a handoff serve as a temporary source of truth for long.

### 9.3 The rule and project case

- A permanent rule reached in a handoff takes effect only after it is written into the corresponding definition file and verified.
- Git status, test results and file contents are governed by an actual check, never by "already done" wording in a handoff.
- When a version, path or interface a handoff cites has expired, flag the risk and re-verify; never carry on silently.

### 9.4 The version campaign case

A campaign handoff records only this execution's recovery facts and routing. It may store the `campaign_id`, the formal source pointer for the authorization envelope, the frozen baseline, the current unit, the evidence/recovery checkpoints, the retained RT3 gates, the authorization expiry facts and the next action. It must never:

- copy or expand a permanent governance rule; generic rules are written only in `batch_workorder_spec.md`, `git_workflow.md` and `remediation_governance.md`;
- treat "already authorized" in a handoff as new authorization, or substitute for the user's original approval and the actual Git/file state;
- read an old conversation, a receipt, a policy or a reviewer conclusion as RT3 authorization for an exact object/body/ID/SHA/result not yet generated;
- use a new summary to add an unlisted path, an unknown repo, a risk escalation or an RT3 into the campaign;
- write a recovery checkpoint as a release snapshot, or write clean as reviewed/released.

The taker must read back the formal work order, the authorization envelope and the actual repository state. Any disagreement stops and repairs per §9; a handoff can say only "where the last execution reached", and can never revive a lapsed continuous authorization. RT3 is confirmed only by the user, directly, in the current round, after the exact object has been displayed.

---

## 10. Closing, superseding and archiving

### 10.1 resolved

**Precondition for delisting — never resolve while the criterion is narrower than the content.** Meeting `close_condition` proves only that the few things it names have closed; it does not prove the rest of the file's sections closed too. Before turning `resolved`, scan section by section for to-dos, leftovers, pending release items, unclosed subsections and "next step" wording; anything that did not close in this round must first be migrated into the index's "Next-version backlog", or into a new receiving entry with its `trigger` stated, before delisting. After delisting, the file leaves the daily loading scope, and an open item never migrated out goes offline with it and nobody takes it over — the classic shape of formal closure arriving before semantic closure, sharing a root with §6.3 "rules resist compression".

Once `close_condition` is met and the precondition above holds:

1. Write back and verify every canonical source.
2. Confirm section by section that the file holds no un-migrated open item; where it does, migrate first and note in the original subsection which Backlog entry it went to.
3. Change the document status to `resolved`, recording the completion time and the verification result.
4. Move it out of Active Handoffs and into Resolved / Archive Handoffs.
5. Delete the temporary "the next step must repair X first" wording, or note the completed result.

A course handoff is usually resolved after `session_close` completes, doctor passes, and the write confirmation has been shown.

### 10.2 superseded

When a newer, more precise handoff takes over from an old file:

1. The new file must first carry a valid status, next step, closing condition, formal sources and continuity summary.
2. Run the takeover rehearsal and the four-question check against the new file, confirming it is not a shell.
3. The new file writes `supersedes`.
4. Only then does the old file write `status: superseded` and `superseded_by`.
5. Active Handoffs keeps only the new file.
6. Do not delete a discussion trail in the old file that still has audit value.

### 10.3 archived

A `resolved` or `superseded` file may be archived once daily reference is no longer needed. Archiving changes only where it is stored and indexed; it changes no formal source and deletes no history automatically.

---

## 11. Interfaces with the existing T2AG processes

### 11.1 Startup and course recovery

- `t2ag.md` provides a conditional entry point only: where the agreed index exists, read the matching active handoff per this process.
- `lesson_recover.md` owns course recovery; a handoff is loaded only when an unclosed course matches an active `course_session`.
- A course that closed normally reads no historical classroom handoff.

### 11.2 Session close

- After `session_close.md` completes the formal write-back and verification, check for a matching active course handoff.
- If there is one, turn it `resolved` per §10 and update the index; if there is none, do not create a handoff to complete the ritual.

### 11.3 Projects and topics

- The project master handoff covers architecture, release, maintenance and implementation state, and never overrides course progress.
- A topic handoff stores the conceptual evolution, decision reasons and open questions across several long conversations, and is read only in the relevant topic task.
- Where a discussion has already become a formal playbook, the handoff keeps the process and the reasoning, and the rule text only cites the playbook.
- A version campaign handoff records only that campaign's baseline, checkpoints, retained gates and stopping point; it must never become a cross-version permanent authorization or a review rule source.

---

## 12. Common mistakes

- **Writing the summary ever shorter**: only the stopping point and to-dos survive, losing user intent and the reasons for the approach. Rewrite the continuity summary.
- **Sorting globally by date**: different scopes override each other. Match by task first, then look at the update time.
- **A handoff outranking progress**: this manufactures two sources of truth. A handoff can only trigger verification and repair.
- **Creating a handoff every conversation**: this produces many duplicate documents. Rely on the formal sources when a session closes normally.
- **Storing only the final conclusion**: it becomes impossible to see how the conclusion formed and which approaches were rejected. Add the discussion lines.
- **Copying a formal rule verbatim**: the rule later drifts. Use a pointer, and keep only the adjudication reasoning of the time.
- **An old active never retiring**: several current entry points appear in one scope. Establish supersedes/superseded_by and update the index.
- **Closing the old file before writing the new one**: a failure midway breaks the recovery chain. Complete and verify the new file first, then supersede.
- **Treating 350 lines as a forced generation change**: 350 lines is only the first check; the third threshold forces a verified new handoff.
- **Writing a plan as completion**: the taker misjudges the implementation state. Keep fact, candidate, unverified and to-do in separate columns.
- **Truncating mechanically by "the last N conversations"**: an older but critical discussion is lost. Use the minimum-sufficient-context criterion.
- **Treating a directory name as a domain type**: a workorder, evidence or backlog inside `handoffs/` is misread as an active Handoff. Partition the index by `artifact_role`, and let only `handoff + active` enter the recovery route.
- **Hanging a release to-do on Active**: the daily startup repeatedly loads release cost. Register it as `lane=version_campaign + artifact_role=release_backlog` and wait for an explicit candidate trigger.
- **Diagnosing without installing an instrument**: finding a batch of orphans, writing "we should add a consistency check", then not doing it. The diagnosis itself becomes a new orphan — it lies in the same drawer, and nobody indexes it either. The criterion is: after this disposition, **who finds the next failure of the same kind**? If the answer is "next time somebody thinks to look", nothing was disposed of. See §6.1.
- **Treating backfill as normal**: allowing a file to lie there with the index backfilled later means the backfill window never closes. Accounting happens in the same batch as placing the file, or it does not happen.

---

## 13. Related files

- `main/t2ag.md` — the takeover entry point, structural registration and the authority chain.
- `main/00_core/t2ag_memory.md` — daily recovery pointers and the key-decision index.
- `main/50_playbook/lesson_recover.md` — cross-session course recovery.
- `main/50_playbook/session_close.md` — formal course write-back and the handoff-closing trigger.
- `main/50_playbook/playbook_management.md` — playbook grading protection and release sync discipline.
- `<handoff_root>/README.md` — the runtime handoff index; never injected with instance content by the skeleton.
