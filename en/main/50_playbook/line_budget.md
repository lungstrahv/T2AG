# Section budgets and sinking

**Protection level**: core-playbook

> **What goes here**: how the two carriers that are read at every startup —
> `main/00_core/t2ag_memory.md` and `main/t2ag.md` — hold their own size down with a line budget;
> what to do when a section goes over budget, and what trace a removal must leave behind.
> **Who writes, who reads**: maintenance sessions write; the section-budget gates read, and so does
> any session that is about to edit those two carriers.
> **When to come here**: when a gate reports a section over budget; when adjusting a section's
> `[max N]`; when sinking old entries.

This file is the **canonical original** of the section-budget mechanism. In this release the
`70_tools/t2ag_doctor.py` docstrings of `memory_section_budgets()`, `check_memory_budget` and
`check_constitution_budget`, together with the mechanism paragraph of `00_core/t2ag_memory.md`
§Section budgets and sinking, **keep nothing but a pointer back here**: the mechanism prose exists
exactly once. Two wordings are two things that drift apart independently, and when they drift
nothing mechanical can find it — before this batch the v0.1.2 provenance paragraph had already
drifted between editions with no gate reporting it.

**The single exception is the definition of a section's extent** (which line a section begins on and
where it ends). That is the parser contract of `memory_section_budgets()`; it **belongs to the code,
not to this file**, and this file does not restate it (2026-08-27 adjudication). The division is
fixed: the mechanism belongs to the playbook, the function's behaviour belongs to its docstring,
each complete on its own side and with no overlap.

---

## 1. The budget lives in the carrier, not in the code

**The budget is a line count**, written as `[max N]` after each section heading:

```markdown
## Recent key decisions  [max 100]
```

The gate **reads that marker out of the carrier itself** and does **not** hard-code it. Adjusting a
budget is a one-line edit in the carrier — no code change, no batch, no cross-release sync. That
price difference is deliberate. If the budget lived in the code, changing it would cost a batch plus
a cross-release sync plus tests; at that price people stop writing entries instead of raising the
budget, which destroys exactly what the budget existed to protect.

So the division of labour is fixed: **this gate owns the mechanism; the student owns the numbers.**
What the gate guards is the mechanism, not the number.

## 2. Two carriers, two severities

| Carrier | Severity | Why |
|---|---|---|
| `main/00_core/t2ag_memory.md` | **WARN** | It is a summary index. An oversized summary is a hygiene problem that must stay visible, but it **must not block a lesson mid-session**. |
| `main/t2ag.md` | **FAIL** | It is the startup entry every session reads. An oversized section **taxes every future boot**. |

**Severity is set per carrier and MUST NOT be levelled.** Both directions of levelling are a net
loss: raise memory to FAIL and the gate acquires the power to interrupt teaching while guarding only
hygiene; drop `t2ag.md` to WARN and the boot tax turns back into a notice nobody has to act on —
which is how the v0.1.2 constitution budget gate ended after `4e72556`, its surviving prose
reference degenerating into exactly such an unenforceable slogan (EV-0020).

When a carrier has no `[max N]` marker at all, the gates report against the same severity table:
memory missing its markers is a WARN, `t2ag.md` missing its markers is a FAIL. **Do not delete a
marker just because its section is empty** — delete it and the budget mechanism never takes effect
on this instance.

## 3. Over budget: sink the oldest entries, leave a tombstone in place

When a section is over budget, **sink the oldest entries** and leave one **tombstone** line in place
naming where they went:

```markdown
- D-001 ~ D-011 sunk → `t2ag_changelog.md` [2026-07-26] ~ [2026-07-27] (sunk YYYY-MM-DD)
```

**Sinking is not deleting**: the entry body was always in `t2ag_changelog.md` /
`t2ag_problemlog.md`, and memory keeps only a pointer. **Deleting a line must state where it went** —
that discipline is inherited from the v0.1.2 rule that retirement leaves a trace, which died together
with `[max N]` and the constitution budget gate in `4e72556` (the 0.2.0 snapshot migration) and was
rebuilt in 0.2.3.

Going over budget on the `t2ag.md` side does **not** use memory's sinking route. It goes through
`main/t2ag.md` §6.3 rule semantic migration (or the student adjudicates an adjustment to that
section's `[max N]`): the destination of a constitutional clause has to be proved line by line, and a
one-line tombstone will not do.

**Two things this file deliberately does not carry**: the criterion for *when* an entry may be sunk
(the result of an executed decision must already have a home), and memory's own numbering convention
(`D-NNN` / `P-NNNN`). They describe how memory's own entries are judged and numbered, not the
section-budget mechanism itself (2026-08-27 adjudication). **In this release there is no pointer to
give for either**: `00_core/t2ag_memory.md` here is the empty-instance cache and carries neither
section. That is a registered gap, not an omission — and it is why this file must not be made to say
they remain in `00_core/t2ag_memory.md`, which in this edition would be a dangling pointer.

## 4. Where the gate is: naming differs between releases

The mechanism exists once; **the gate's implementation name differs by release**, so read it out of
the repository before writing it down:

| Release | Current check IDs |
|---|---|
| This release (`t2ag-skeleton-en`) | `runtime.memory_budget` (handler `check_memory_budget`; memory carrier; WARN) + `runtime.constitution_budget` (handler `check_constitution_budget`; constitution carrier; FAIL) |
| Main | the two were merged into one carrier-parameterized gate on 2026-08-26; that merge has not been sunk to this release |

**Why this file may be in English.** The core-playbook file-set and sha comparison, and
`check_playbook_taxonomy_parity`, run only over the editions returned by
`distribution_release_names()`, and this release is **not** among them. This file is therefore **not**
on the byte-identical sha surface that the Chinese editions' copies must stay on. Translating it here
breaks nothing; leaving it in Chinese would instead break this repository's all-English playbook
convention.

**No `enforcement:` forward edge is written in this file.** That is a registered debt carried over
from the batch that created the canonical original, not an oversight: the gate naming has not
converged across releases (Main merged its two gates; this release still runs them separately), and
the edge is deferred until it does. The reverse edge (`rule_binding`) is absent here for a separate
reason — `70_tools/validation_workflow.json` in this release carries no `rule_binding` field on any
check at all; that field has not been sunk to this release. Both are known gaps, both are tracked,
and neither is closed by this batch.

## 5. Provenance

- v0.1.2: inline `[max N]` in `t2ag.md` plus a standalone constitution budget gate.
- `4e72556` (the 0.2.0 snapshot migration): both were lost together, leaving one line of prose that
  nobody enforced.
- 0.2.3: the mechanism was rebuilt in `00_core/t2ag_memory.md` (EV-0020).
- 2026-08-26: on the Main side the two gates were merged into one and severity became a per-carrier
  parameter. **This release still runs the two gates separately.**
- 2026-08-27: on the Main side the mechanism prose moved out of memory into this file, and memory and
  the docstrings were both cut down to pointers.
- 2026-08-28: this file was created for this release as an English edition, and this release's memory
  paragraph and three doctor docstrings were cut down to pointers. See §6.

## 6. rule_migration

For this release this file is a **new file**; for `00_core/t2ag_memory.md` and
`70_tools/t2ag_doctor.py` the change **relocates normative text**, registered line by line per
`main/t2ag.md` §6.3 and `50_playbook/playbook_management.md`. These entries are **this release's own
accounting** and deliberately do not reuse the Main-side batch numbering.

| rule_id | old location / text anchor | action | new owner / equivalence gate | consumer | verification |
|---|---|---|---|---|---|
| LB-EN-001 | `00_core/t2ag_memory.md` §Section budgets and sinking, the whole mechanism paragraph: the `[max N]` line-count budget and why the gate reads it from the file, the sink-and-tombstone rule, and the do-not-delete-an-empty-section-marker rule. The empty-template scaffolding note stays in place (it describes this instance, not the mechanism). | sink | this file §1, §2, §3 | both section-budget gates; maintenance sessions adjusting `[max N]` or sinking | `grep -n "Deleting a line must state where it went" main/50_playbook/line_budget.md` |
| LB-EN-002 | `70_tools/t2ag_doctor.py` `check_memory_budget` docstring, the WARN-not-FAIL severity rationale | sink | this file §2 | the memory budget gate; sessions changing gate severity | `grep -n "must stay visible" main/50_playbook/line_budget.md` |
| LB-EN-003 | `70_tools/t2ag_doctor.py` `check_constitution_budget` docstring, the FAIL-not-WARN severity rationale | sink | this file §2 | the constitution budget gate; sessions changing gate severity | `grep -n "taxes every future boot" main/50_playbook/line_budget.md` |
| LB-EN-004 | `70_tools/t2ag_doctor.py` `memory_section_budgets()` docstring, paragraph one (the `[max N]` ownership argument) | sink | this file §1 | sessions changing where `[max N]` lives | `grep -n "the student owns the numbers" main/50_playbook/line_budget.md` |
| LB-EN-005 | `70_tools/t2ag_doctor.py` `memory_section_budgets()` docstring, paragraph three (the v0.1.2 provenance) | sink | this file §5 | sessions reading the gate's release history | `grep -n "unenforceable slogan" main/50_playbook/line_budget.md` |
| LB-EN-006 | `70_tools/t2ag_doctor.py` `memory_section_budgets()` docstring, paragraph two (the definition of a section's extent) | **keep** | unchanged, in place in the docstring | sessions changing the section-splitting implementation | `grep -n "A section spans its own heading line" main/70_tools/t2ag_doctor.py` |

**The four-item sink closure**:

1. **New canonical owner**: this file (`main/50_playbook/line_budget.md`, core-playbook).
2. **Necessary entry pointers**: `00_core/t2ag_memory.md` §Section budgets and sinking; the
   `memory_section_budgets()`, `check_memory_budget` and `check_constitution_budget` docstrings in
   `70_tools/t2ag_doctor.py`; and both gates' over-budget remedy strings — all now point here.
3. **Consumers**: `runtime.memory_budget` and `runtime.constitution_budget`; any maintenance session
   adjusting a `[max N]` or performing a sink.
4. **Verification evidence**: `PYTHONUTF8=1 python main/70_tools/t2ag_doctor.py --profile runtime` is
   no worse than the pre-batch reading; `parse_playbook_protection_levels` recognizes this file as
   `core-playbook`; the mechanism-prose concept grep over `main/70_tools/` and `main/00_core/`
   returns zero hits.

**Unregistered-deletion audit**: all four carriers were **cut down to a pointer**, not deleted;
paragraph two of `memory_section_budgets()` is unchanged word for word (LB-EN-006). **No `LB-EN-*`
entry exists for the sinking-criteria table, for the `D-NNN` / `P-NNNN` numbering convention, or for
a `rule_binding` value** — none of the three exists in this release, so there was nothing to migrate.
Registering a migration that did not happen would be a false record.
