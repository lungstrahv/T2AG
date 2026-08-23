# The problemlog maintenance flow

**Protection level**: meta-playbook

> This file is one of T2AG's "skill consolidation" documents.
> Triggered when a session hits a problem with a tool, the environment, the file structure, rule execution, or memory governance.
>
> **Applies to**: OCR, downloads, dependencies, paths, encoding, course initialization, course recovery, doctor repair, an authority-chain conflict, a stale playbook, a rule upgrade.
>
> **Related files**:
> - Rule definition: `main/t2ag.md` → "the problem-and-solution log main/00_core/t2ag_problemlog.md"
> - The system mistake book: `main/00_core/t2ag_problemlog.md`
> - The startup index: `main/00_core/t2ag_memory.md`
> - The session-close flow: `main/50_playbook/session_close.md`
>
> **Role in the loop**: `t2ag_problemlog.md` is the throughput ledger of the
> `problemlog → 50_playbook/` loop, not a decaying instance store in the mistake_bank style.
> Entries are referenced by a stable `P-NNNN`; whether a playbook has been distilled is a settlement field, and a same-kind recurrence leaves a trace in the counter.

---

## 1. Triggers

- A system/process problem was hit, and it may recur in future.
- The user points out that some mechanism is not being used effectively and a rule is needed.
- Doctor reports an error, a cache conflicts with a source of truth, or a course structure is inconsistent.
- An existing playbook failed, went stale, or missed a key step.

---

## 2. The full steps

### Step 1: triage first

Decide where the problem should be written:

| Problem type | Written to |
|---|---|
| a student's conceptual, proof, calculation, or code-comprehension error | `[course]/mistake_bank.md` |
| course progress, the stopping point, cumulative hours | `[course]/progress.md` |
| the student's emotional or stable learning state | `main/10_student/profile/profile.md` |
| a tool, environment, file-structure, rule-execution, or memory-governance problem | `main/00_core/t2ag_problemlog.md` |

### Step 2: search the old records first

Before doing any repair, search by keyword:

```powershell
rg -n "keyword1|keyword2" main/00_core/t2ag_problemlog.md main/playbook
```

If a playbook already exists, follow it first; if an old log entry is similar, read that entry before acting.

When an old entry with the same root cause is hit:

- Do not create a new ID; `occurrence_count += 1`.
- When an entry already resolved recurs, additionally do `reopen_count += 1` and set the status back to `open`.
- If a playbook exists, re-run it first; if it still fails, update the old entry's attribution and handling, and revise that playbook.

Only when the tags look similar but the root cause differs is a new ID allocated; a tag is not an entry's identity.

### Step 3: resolve, or mark it blocked

After the repair, record the path that worked; if it is unresolved, write out the current blocking condition and who must decide what, or supply what information, next.

### Step 4: append the problemlog entry

Read `next_id` from the top of the file, allocate it, and increment it immediately. Write these fields:

```markdown
## P-NNNN | [YYYY-MM-DD HH:00] | one-sentence title

- tags: [OCR, doctor]
- playbook_status: none
- occurrence_count: 1
- reopen_count: 0

**Phenomenon**: what happened; write observable facts, not speculation.

**Attribution**: which layer the root cause lands on — process, rule, or tool.

**Handling**: the repair already performed; when unresolved, the blocking condition and the next step.

**Precedent value**: low / medium / high; state in what future situation this entry should be searched for.

**Status**: open / resolved / blocked

---
```

Field rules:

- `tags` takes at least one and may take several; it is for search and same-kind counting, and does not replace the stable ID.
- `playbook_status` may only be:
  - `none`: not yet judged;
  - `candidate`: the distillation threshold has been reached;
  - `extracted:<path>`: distilled, with the path pointing at the existing original;
  - `not_applicable:<reason>`: definitely should not be distilled.
- `occurrence_count` is the cumulative number of occurrences of the same root cause, starting at 1.
- `reopen_count` is the number of recurrences after being resolved, starting at 0.
- `extracted:<path>` is this ledger's formal settlement marker; writing "the playbook has been updated" in the body while leaving the field unfilled is not allowed.
- Where a historical entry cannot be backfilled reliably, use an explicit `legacy_unknown`; never leave it blank and never fabricate a conclusion.

### Step 5: synchronize memory

If the entry's reuse value is medium or high, update `main/00_core/t2ag_memory.md`:

- add a one-sentence summary to "the last 5 problems";
- if it affects a future startup or the order of actions, add it to the "key decision index";
- keep the whole file under 150 lines; where necessary replace an old summary rather than appending indefinitely.

### Step 6: judge whether to upgrade it into a playbook

Suggest to the user that a playbook be distilled or updated when any of these holds:

- the same root cause has `occurrence_count >= 2`;
- a single occurrence is high-risk with complex steps, and the probability of repeating it is high;
- stable steps have already formed, and leaving them in the problemlog means understanding them from scratch next time;
- an existing playbook missed a step, causing the same problem to recur.

Once distilled, set `playbook_status` to `extracted:<path>`; if it is judged unsuitable for distillation,
write `not_applicable:<reason>`. When a same-kind problem recurs, still reopen the original entry and increment the counter;
never create a duplicate entry just because the original was settled.

---

## 3. Common problems and pitfalls

- **Writing the log but never consuming it**: useless. Before a similar task next time, the memory index, the playbooks, and the problemlog must be searched first.
- **Putting a course knowledge error into the problemlog**: wrong layer. A knowledge error goes into `mistake_bank.md`.
- **Upgrading everything into a playbook**: over-structuring. Only a reusable flow gets upgraded.
- **Writing the problemlog and forgetting memory**: a high-reuse entry sinks out of sight. The recent summary or the key index must be synchronized.
- **A playbook exists but only the log is appended to**: it means the process document is not being maintained. Update the playbook.

---

## 4. Related files

- `main/00_core/t2ag_problemlog.md` — the system/process mistake book
- `main/00_core/t2ag_memory.md` — the startup index and action scheduler
- `main/50_playbook/session_close.md` — the harvest trigger at session close
- `main/00_core/t2ag_changelog.md` — the history of rule or file-structure changes
- `[course]/mistake_bank.md` — the student's knowledge mistake book
