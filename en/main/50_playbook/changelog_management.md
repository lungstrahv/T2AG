# Changelog management (drift traces and non-rot)

> **Function**: it specifies the **verification layer** of `main/00_core/t2ag_changelog.md` — an entry must be recomputable, and a state drift must leave a trace.  
> **Protection level**: meta-playbook (the same tier as `handoff_management.md`; it constrains record discipline across sessions and across platforms).  
> **What it does not do**: it does not prove "everything that should have been recorded was recorded" (completeness / L5 is unreachable). The input to a record is human judgement, not repository state, so the L4 "deterministically regenerable" route is structurally closed here.  
> **Canonical owner (verification layer)**: this file. The order-writer's obligation and the executor's hard rules stay where they are, in `batch_workorder_spec.md` (see the rule_migration at the end).

---

## 1. What is to be proven

Two independent goals, which **must never be blended with "which forms count"**:

1. **A drift trace**  
   When the repository's **anchored state** changes, a matching changelog entry must record that change (or say explicitly why it is not recorded — which is still an auditable record, not silence).

2. **Non-rot**  
   A **recomputable claim** written in an entry still holds when it is spot-checked later.

Explicitly **not proven**:

- It does not prove "everything that should have been recorded was recorded";
- It does not prove whether an entry's narrative is complete or a teaching judgement correct;
- It does not equate "there is a changelog" with "the release is sound" or "it has been re-reviewed".

---

## 2. Which forms count

The **form list of recomputation sources is reused directly** from `handoff_management.md` §5.6.2, and **no second table is created**.  
Whoever takes over only has to learn one `claim ← command` syntax.

### 2.1 Differences from handoff claims (changelog-specific)

| Claim class | Constraint |
|---|---|
| **Anchoring claim** | accepts only forms that are **recomputable with repo + python alone** (zero git dependency: `git log` / `git status` / a commit hash must never be an anchoring quantity). The default candidates are in the work order's U2 adjudication; once landed, doctor compares the declared values of the **newest entry** against the measured values. |
| **Corroborating claim** | an entry-specific recomputable claim pointing at the repository (typically: a `grep` hit, a path's existence, a tool subcommand's output). The form still falls inside the §5.6.2 list. |

The format is the same as for a handoff: `claim ← recomputation command`, and the command must be
pasteable and runnable as-is in the taking-over party's environment.

---

## 3. Entry structure

Every changelog entry (`## [date] …` and the body below it) carries an impact block in addition to the
narrative:

```markdown
#### Anchored assertions (required)
- runtime plan sha256 = <value> ← `python -B main/70_tools/t2ag_doctor.py --profile runtime | head -1`
- runtime checks = <value>      ← as above

#### Corroborating assertions (optional, entry-specific)
- <claim> ← <recomputation command>
```

> The field set of the anchoring block (approved by the student 2026-08-07): **A+B+C** (runtime plan sha256, runtime checks, the sha of the doctor_checks key set); **D/E excluded**. The full recomputation commands are in the U2 report. Before U3 landed this structure was a normative convention and doctor did not compare it automatically.

### 3.1 Judgement semantics (written separately)

| Class | Who judges (after U3) | On failure |
|---|---|---|
| **Anchoring** | doctor takes the declared values of the **newest** changelog entry and compares them with this round's measurement | not equal → WARN "state drift with no record", and the message must contain **both numbers, declared and measured** (a WARN that names nothing is no report at all) |
| **Corroborating** | doctor spot-checks the `grep`-class (or other registered) recomputation commands in an entry | zero hits → WARN "the entry has rotted", and it must name **the entry title and the verbatim failing claim** |

### 3.2 Relation to the existing preamble obligations

The preamble of `t2ag_changelog.md` still requires: expand on demand; update the `t2ag_memory.md` summary when an entry is appended; and sink old entries that exceed the memory section's budget.  
This playbook **restates these as normative clauses** (keep; the preamble text itself is not sunk):

- after a new entry is written, the memory "recent change summary" pointer must be updated in step;
- historical changelog lines and historical memory summary lines are **not edited** (`batch_workorder_spec.md` hard rule 4).

---

## 3a. When a release fact is written (same origin as the version ledger's three layers)

If a fact only becomes true **after the package is built**, while the carrier that records it lives **inside the package**, then writing it stales the package — the three-layer write ownership in `60_journal/t2ag_version_ledger.md` has already resolved that loop twice (`candidate_review` at layer 2, `release_candidate` at layer 3, whose own text names the loop "write pass → repack → new package unreviewed").  A changelog entry is **a third instance of the same shape**, and this section disposes of it by the same solution.

- The change entry that describes this batch is a **pre-build fact**: it is frozen **before** the candidate is built and ships with the package (as layer 1, "the source-intrinsic status").
- The remote facts produced by publishing (the commit, tag and asset name/size/hash of a push/tag/Release) are **post-build facts**: they are written into a release receipt or into `60_journal/t2ag_version_ledger.md`, and **must not be written back into the already frozen product tree** (as layer 3, "not a packaged carrier; its own commit").

⚠ The observable consequence of breaking this (measured 2026-08-27): when the changelog's anchoring block is not refreshed after a change, doctor leaves one "state drift with no record" WARN hanging in each of the three repositories, and on the skeleton side that breaks the self-declared cold-start guard "an empty template and a new trial user's doctor must stay at 0 WARN".

---

## 4. rule_migration (this batch's execution table)

Creating this file makes it the canonical owner of the changelog **verification layer**; the existing conventions are spread across the order-writer's and the executor's sides and are **all kept**, not sunk into a single file.

| rule_id | rule_id | Action | New owner / equivalent gate | Consumers | Verification |
|---|---|---|---|---|---|
| changelog preamble "expand on demand / update the memory summary when appending an entry" | `grep -n "追加条目时同步更新" main/00_core/t2ag_changelog.md` | **keep** (the preamble keeps its text; historical lines untouched) + restated in §3.2 of this file | `changelog_management.md` | every maintenance session | `grep -n "memory .recent change summary. pointer" main/50_playbook/changelog_management.md` |
| `batch_workorder_spec.md` §2.5 "the registration section: the changelog draft" | `grep -n "changelog draft" main/50_playbook/batch_workorder_spec.md` | **keep** (the order-writer's obligation stays where it is) + a back-pointer (step 3b) | `batch_workorder_spec.md` | the order writer | both greps hit |
| hard rule 4 "historical changelog lines are not edited" | `grep -n "Historical lines in" main/50_playbook/batch_workorder_spec.md` | **keep** + a back-pointer (step 3b) | `batch_workorder_spec.md` §3.4 | the executor | both greps hit |
| the spec's own modification discipline "changes to this file go through a batch + the changelog" | `grep -n "Changes to this file go through a batch" main/50_playbook/batch_workorder_spec.md` | **keep** + a back-pointer (step 3b) | `batch_workorder_spec.md` §6 | the order writer | both greps hit |

> Closing expansion: the work order's original table had 3 rows; the closing grep hit 3 changelog-related sentences in `batch_workorder_spec.md`, so the table was expanded to 4 rows (adjudication sheet, [work-order defect 2]).

---

## 5. Lending this mechanism out

This mechanism (the **anchoring claim + corroborating claim** split) is **carrier-independent**. The applicability criteria are below.

| Criterion | Anchoring claim usable | Corroborating claim usable |
|---|---|---|
| **Condition** | a cheap, deterministic global invariant exists, and it changes with whatever that carrier records | the entry body contains a **recomputable claim pointing at the repository** |
| `t2ag_changelog.md` | ✔ (runtime plan sha and the like, per the U2 adjudication) | ✔ |
| `t2ag_problemlog.md` | ✘ no corresponding global invariant | **✔** the body contains path claims such as `playbook_status: extracted:<path>` (they do dangle; the current measurement uses `grep -c`) |
| `course_reflections.md` | ✘ | depends on whether an entry cites a course/activity ID; needs measuring first |
| `lesson_thoughts.md` / `exercise_thoughts.md` | ✘ | ✘ they record lines of thought and almost never contain a repository claim. **These two carriers want a different gate (L1.5 trigger-based existence detection), which is out of scope for this order** |
| a carrier that already has an L2–L4 gate | it already has a stronger mechanism | ✔ can be layered on, specifically against entry rot |

**This table is a criterion, not a to-do list.** Actually erecting a gate on any carrier requires **its own work order**; nothing may be built directly from this table.

### 5.1 A tiered correction about problemlog (written into the construction report; the historical survey text is not edited)

An earlier survey wrote "no workable trigger condition can be found for `problemlog`; accept that it stays at L0 long-term" — **that conclusion was wrong**.  
`problemlog` **cannot carry anchoring**, but it **can carry corroboration**; it should sit at "corroboration usable, anchoring unusable", not at L0.

---

## 6. Interface with doctor

| Stage | Status |
|---|---|
| U1+U4 | the specification and the criteria landed; `doctor_contracts.md` registers the "changelog drift and rot" row |
| U3 (implemented) | `runtime.changelog` → `check_changelog_contract`; a pure function + positive and negative tests + mutation verification; the anchoring fields = the A+B+C approved by U2 |

---

## 7. Related files

- Carrier: `main/00_core/t2ag_changelog.md` (Main and Skeleton **fork separately** and must never be copied across)
- Form list: `handoff_management.md` §5.6.2
- Order writing / hard rules: `batch_workorder_spec.md` §2.5, §3.4, §6
- Contract matrix: `doctor_contracts.md`
- Work order: `docs/handoffs/T2AG_CHANGELOG_VERIFICATION_WORKORDER_2026-08-07.md`
- Adjudication: `docs/handoffs/T2AG_CHANGELOG_VERIFICATION_AUTHORIZATION_2026-08-07.md`
- EV: `EV-0017` (Register)
