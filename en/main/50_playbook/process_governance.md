# Process governance (process_governance)

**Protection level**: meta-playbook

> **Function**: the admission, revision, and retirement of process objects (gates + flows + the directed graph), plus the graph-maintenance discipline.
> **What it does not do**: it does not swallow R-GATE (`rule_admission_gate.md` stands on its own and is referenced here by pointer);
> it does not write the rule bodies of individual gates and flows (pointers only).
> **This version**: a skeleton. Expanding the three process sections to full text is stage two, and this file's structure does not change here.

## 1. Scope

The process objects this file governs:

- gates (carried by the Main-only canonical `main/00_core/gate_index.md`; not shipped in Skeleton)
- flows (the nine flow forms of `t2ag_flow.md`: `first_run`, `panorama`, `teaching_loop`,
  `authority_chain`, `cycles`, `skin`, `git`, `batch`, `exercise_loop`)
- the directed graph (the relation graph of gates and flows)

Responsibilities: the admission / revision / retirement of those objects + the graph-maintenance
discipline (changing a gate or a flow must change the graph; the graph holds pointers only)
+ the gate-ledger pointer (`learning_activity_model.md` §2.4). `t2ag_flow.md` itself remains a
core-playbook, and its body does not move into this file.

## 2. Admission (expanded in stage two)

Placeholder. Stage two writes: the conditions under which a new gate / new flow comes under governance,
where it is registered, and how the graph is updated.

## 3. Revision (expanded in stage two)

Placeholder. Stage two writes: the revision procedure for changing a gate or a flow, and the same-batch
obligation toward the graph and the governance list.

## 4. Retirement (expanded in stage two)

Placeholder. Stage two writes: the conditions for retiring a gate / flow, deletion from the graph, and
the visibility of an invalidated pointer.

## 5. Directed-graph discipline

1. Changing a gate or a flow must change the graph.
2. The graph holds pointers only and never copies body text.

## 6. The governance list

- Main-only canonical `main/00_core/gate_index.md` (instance data; not shipped in Skeleton)
- the nine flow forms of `50_playbook/t2ag_flow.md` (the file itself remains core; its body is untouched)

## 7. The enforcement declaration and Q0

There is no machine means during the skeleton stage. The failure-visibility path is left to stage two's
acceptance: at that point a disagreement between the graph and the governance list must be catchable by a
named check (the candidate machine landing point is `runtime.gate_index`). During the skeleton stage it is
declared honestly:

```text
enforcement: prose_accepted (reason: no machine means during the skeleton stage; the candidate machine landing point runtime.gate_index is reserved)
```
