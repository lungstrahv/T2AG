# The playbook management flow

**Protection level**: meta-playbook

> This file is one of T2AG's "skill consolidation" documents.
> Triggered when the model is about to add, rewrite, merge, or protect some `main/50_playbook/*.md`.
>
> **Applies to**: distilling a flow out of the problem log, maintaining an existing playbook, judging whether a new playbook is needed, judging whether a playbook belongs to the core/protected flows.

---

## 1. Core principles

- A playbook is **procedural memory**, not a fact, a log, or a record.
- A playbook stores "the method for doing a thing", especially a flow that has been through trial, revision, and verification.
- A fact that could go into `t2ag_memory.md` is not thereby something that should become a playbook.
- A case that could go into `t2ag_problemlog.md` is likewise not something that should immediately become a playbook.

---

## 2. The creation threshold

Before adding an ordinary playbook, all of these must hold:

1. It is not a one-off, temporary, or experimental task.
2. At least 6 key steps.
3. At least 6 tool invocations.
4. At least 1 round of correction, adjustment, or verification feedback.
5. It generalizes; it is not bound to one course, one file, or a temporary environment.
6. It is unlikely to go stale within 7 days, and does not depend on a PR number, an issue number, a commit SHA, or the current task state.
7. No existing playbook covers the same flow.
8. Its trigger, inputs and outputs, reuse value, and common pitfalls can all be written clearly.

When these do not hold, write it into `t2ag_problemlog.md` or `t2ag_memory.md` only; do not force a new playbook into existence.

---

## 3. Definition of a key step

A key step must satisfy at least one of:

- It produces a persistent state change: writing a file, changing configuration, creating a resource, updating an index.
- It makes an irreversible or high-impact design decision.
- It executes and verifies a real result.

These do not count as key steps by default:

- Merely opening or reading a file.
- Merely looking something up, confirming user input, or explaining a concept.
- The user naming something, brainstorming, ordinary discussion.
- Recording, archiving, indexing, backing up — unless the record itself reshapes a later decision.

---

## 4. Protection levels (three tiers)

There are only three legal marker values: `meta-playbook`, `core-playbook`, `playbook`. They are written
at the top of the file, in exactly the form `**Protection level**: <value>`. Anything outside the three is
illegal.

### 4.1 meta-playbook (the functional criterion governs; the regeneration criterion is a verifying corollary)

**The functional criterion** (primary): it governs the lifecycle of a governance object — playbooks,
journal, memory, problem log, changelog, gate and rule admission, process. This is an open enumeration,
not a closed one.

**The regeneration criterion** (verifying corollary): remove it from a release projection with no
canonical owner and it cannot regenerate. The project regenerates around meta; shared meta must have a
single Main source of truth and verifiable downstream projections, and the concrete mechanism is owned
solely by §5.

When the two criteria disagree, the conflict must be adjudicated and registered; it must never be carried
forward silently.

The protection semantics of meta: release projections close per §5 + a major change defaults to a
diff-patch + a semantic relocation requires a `rule_migration`.

### 4.2 core-playbook

Mark a file `core-playbook` when any of these holds:

- The user explicitly asked for it to be kept long-term.
- High complexity: at least 3 major revisions during development, and a final flow of at least 12 key steps.
- Triggered more than 5 times within 13 days.

Neither core nor meta should be archived, merged, or substantially rewritten automatically; when a change
is needed, the reason must be stated in `t2ag_changelog.md`. Protection does not mean uneditable — it only
blocks automatic cleanup and casual merging.

For a core-playbook, a meta-playbook, or a governance document carrying a hard boundary, a version update
or a major change defaults to a **diff-patch**. Deleting, merging, generalizing, relocating, or retiring
normative body text, or changing the semantics of a named hard boundary, requires a registered
`rule_migration`; a pure addition, or a formatting or meaning-preserving clarification, may be recorded as
`not_applicable`. A whole-file rewrite requires the complete migration table to be frozen first. A
demotion must prove the new canonical owner, the necessary entry pointers, the consumers, and the
verification closure; file length, a keyword, or a historical list only triggers a re-review and does not
by itself constitute a finding. The full discipline is in
`main/t2ag.md` §6.3 and `batch_workorder_spec.md` §3 item 11.

### 4.3 playbook

Every other procedure manual is marked `playbook`. Changes go through a batch, and it does not carry the
three-repository byte-identity obligation of core/meta (the distribution axis is a separate matter).

The machine landing point of a normative line (an example, inside a fence):

```text
enforcement: check=runtime.playbook_taxonomy
enforcement: check=release.playbook_taxonomy_parity
```

## 5. Release-projection discipline (the sole operating owner)

This section is the sole operating owner of Main → zh Skeleton / Lite. The constitution keeps only the
hard boundary — a single source of truth and verifiable projections — and the flow chart only draws the
call relations; no other carrier may duplicate the commands, the order, or any "mirror repository" rule.

### 5.1 The current 0.2.4 boundary

- **Main is the only canonical source.** The zh Skeleton is a projection of the general mechanism, not a
  reverse template source; Lite is Main's one-way redacted review projection and must not become a rule
  source in reverse either.
- **The zh mechanism projection** has no whole-repository generator. Cross-release H5 must be named per
  batch, take explicit paths from a committed Main, and synchronize only low-privacy shared mechanism
  and the registered constitution sections; after landing, byte/SHA-verify the named paths. Real
  instances, host logs and legal release identity divergences must not be copied.
- **The Lite projection** is produced only by `main/70_tools/sync_lite.py`: the default command is
  check-only; `--write` accepts only a clean Main and does a full regenerate, redaction and hash
  re-verification. Hand-editing Lite long-term is forbidden.
- **The EN edition is in the 0.2.4 scope (T2AC closeout workorder 14.130)**; its content
  synchronization runs as its own named release batches — per-batch H5, ordered after zh — and the
  mechanism axis it carries is deferred to the clean-room rebuild by the same ruling.
- The class-level machine-query artifact manifest is explicitly a **0.2.5** item; 0.2.4 creates no
  second registry, and a design document must not pose as machine truth already in force. The current
  mechanism closes with this section, `sync_lite.py` and the existing doctor gates.

### 5.2 Projection gates and order

#### 5.2.1 Constitution and 00_core section homology

`main/t2ag.md` and the three `00_core` models are compared by `## ` section SHA; the Skeleton
constitution's §6 de-instantiation is a registered divergence, and `AGENTS.md` takes a file-level
exemption for its different audience. owner=`t2ag_doctor.py` `check_constitution_parity`.
enforcement: check=release.constitution_parity

#### 5.2.2 core/meta release integrity

The named projection set and the bodies that should be homologous for core/meta playbooks must be
complete; a low-privacy shared file must not carry a student name, a host absolute path, current course
progress, a fixed commit or a private remote. enforcement: check=release.core_playbooks

#### 5.2.3 Order

1. A Main change first passes directed tests, the runtime doctor and the state check, then commits its
   named source paths.
2. Within the same named H5, close the zh mechanism paths; the constitution and `00_core` are compared
   by registered section, core/meta playbooks by file; `AGENTS.md`, release identity and redacted
   output accept only registered divergences.
3. After Main is clean, first run the `python -B main/70_tools/sync_lite.py` dry run; when an update is
   needed, run `python -B main/70_tools/sync_lite.py --write` (optionally `--root <T2AC>`).
4. `runtime.skeleton_privacy` and the Lite full projection hash are independent gates; if either fails,
   projection closure must not be claimed.
5. When a core/meta playbook is added or substantially changed, complete the projections above and the
   doctor applicable to each release; an online suggestion can only return to Main for adjudication —
   never edit Lite directly, and never backfeed Main from zh.

### 5.3 DEC-4 A8 rule_migration

| rule_id | Old location/action | New owner/equivalent gate | Consumer | Verification |
|---|---|---|---|---|
| DEC4-PROJ-01 | Constitution §1.9 "three releases byte-homologous" → keep the hard boundary, sink the operating detail | This section §5.1; the constitution keeps a pointer only | All release batches | The constitution contains the `playbook_management.md` §5 pointer |
| DEC4-PROJ-02 | The mirror/cmp manual path in `t2ag_flow.md` → sink | This section §5.1–§5.2 | The Git/release flow chart | The flow chart names the "release-projection owner" and has no "Main ↔ Skeleton" |
| DEC4-PROJ-03 | The scattered synchronization rules of this file's former §5 → rewrite | This section §5.1–§5.2; `sync_lite.py`; `runtime.skeleton_privacy` | Main/zh/Lite | A9 mutation + named H5 probe |

Unregistered-deletion review: no hard gate was retired — single source of truth, privacy, constitution
section homology, core/meta integrity and Main-clean all stand; only the duplicated manual mirror
wording was retired, and the machine manifest's new capability is explicitly moved to 0.2.5.

---

## 6. The maintenance flow

1. First check whether `main/50_playbook/` already has a flow of the same kind.
2. If it does, update the old file only; do not create a duplicate.
3. If it comes from a system problem, first make sure `t2ag_problemlog.md` has the case recorded.
4. Judge whether it is worth distilling, using the thresholds in this file.
5. After adding or substantially changing a playbook, synchronize:
   - the current playbook file table in `main/50_playbook/_README.md`;
   - `main/00_core/t2ag_changelog.md`;
   - where necessary, the key-decision index in `main/00_core/t2ag_memory.md`.
6. If journal-writing rules are involved, also check `main/50_playbook/journal_management.md`.

### Cleanup and archiving

T2AG follows these governance principles:

- Preview before cleaning; never delete directly.
- Prefer archiving to a location a human named, over permanent deletion.
- When flows have reuse value but overlapping scope, prefer merging them into a broader umbrella playbook.
- A core playbook takes no part in automatic archiving or merging.

---

## 7. Related files

- `main/t2ag.md` — the general playbook rules and the seed notes.
- `main/00_core/t2ag_problemlog.md` — the source of system/process cases.
- `main/50_playbook/problemlog_maintenance.md` — the upgrade flow from problem log to playbook.
- `main/50_playbook/journal_management.md` — the boundary of journal records.
- `main/50_playbook/naming_conventions.md` — the naming boundary for files, directories, assets, and migrations.
- `main/00_core/t2ag_changelog.md` — the record of playbook rule changes.

## 8. rule_migration (the W0 frozen item, landed)

For §4 this batch is a semantic expansion (the three tiers are seated; no clause was deleted). The table is
isomorphic to §6 of the work order, and its row count is frozen.

| rule_id | rule_id | Action | New owner / equivalent gate | Consumers | Verification |
|---|---|---|---|---|---|
| PB-TAX-001 | §4 opening sentence "protect a high-value flow with core-playbook semantics" | keep (rewritten as a three-tier overview) | §4 of this file | maintenance session / doctor tier instrument | `grep -n "only three legal marker values" 50_playbook/playbook_management.md` |
| PB-TAX-002 | §4 condition "the user explicitly asked for it to be kept long-term" | keep | §4.2 of this file | the adjudication to promote to core | `grep -n "explicitly asked for it to be kept long-term" 50_playbook/playbook_management.md` |
| PB-TAX-003 | §4 condition "governs the lifecycle of …, hence meta-playbook" | keep (promoted to a standalone meta definition) | §4.1 of this file | the adjudication to promote to meta / U-0 | `grep -n "The functional criterion" 50_playbook/playbook_management.md` |
| PB-TAX-004 | §4 condition "high complexity, 3 revisions + 12 steps" | keep | §4.2 of this file | the adjudication to promote to core | `grep -n "12 key steps" 50_playbook/playbook_management.md` |
| PB-TAX-005 | §4 condition "triggered more than 5 times within 13 days" | keep | §4.2 of this file | the adjudication to promote to core | `grep -n "within 13 days" 50_playbook/playbook_management.md` |
| PB-TAX-006 | §4 paragraph "should not be archived automatically …" | keep (scope widened to core+meta) | §4.2 of this file | the archive/merge gate | `grep -n "Neither core nor meta should be archived" 50_playbook/playbook_management.md` |
| PB-TAX-007 | §4 diff-patch / rule_migration paragraph | keep (scope stated explicitly as core+meta) | §4.2 of this file | the work order / the re-review | `grep -n "a governance document carrying a hard boundary" 50_playbook/playbook_management.md` |
| PB-TAX-008 | §5 six release disciplines | keep; a meta clause added | §5 of this file | three-release sync / doctor | `grep -n "meta-playbook" 50_playbook/playbook_management.md` |
| PB-TAX-009 | §6 "the current playbook file table in t2ag.md" | keep (repointed at `_README.md`) | §6 of this file | maintenance session | `grep -n "_README.md" 50_playbook/playbook_management.md` |
