# Playbook procedure-manual directory

> **What goes here**: the teaching agent's operating manuals — how to close a session, how to start a course, how to import a textbook, how to set an exam.
> **Who writes, who reads**: maintained as the system evolves; read by the teaching agent while executing a flow.
> **When to come here**: when a flow has to be executed (session close, course start, textbook management, an exam), come here for the matching manual.

Flows are indexed by name; naming is in `naming_conventions.md`.

- `process_governance.md`: process governance (meta-playbook). The admission / revision / retirement of
  process objects (gates + flows + the directed graph) and the graph-maintenance discipline; this batch
  is a skeleton, and expanding the three process sections to full text is stage two.
- `gate_index.md`: the gate index (playbook, managed_by: process_governance). One table of every gate in
  T2AG — the directed graph + what each gate governs +
  a pointer to the body's owner, **pointers only, no copied body text**. Four lanes: A teaching gates,
  B construction gates, C machine gates,
  D cross-boundary gates, plus the cross-cutting evidence discipline. It carries two honest notes: the
  evidence discipline is currently registered in one course only, AIF1001r
  (whether to promote it globally is undecided); and even after ⑥ is layered with the three-tier
  calibration, a spatial gap of "should have read it and did not" is still uncovered.
  Its own declaration is `enforcement: prose_accepted` — **it is an index, not a constraint, and has no
  machine backstop**.
- `rule_admission_gate.md`: the rule admission gate (R-GATE). A new rule entering `00_core`/`50_playbook`
  passes this gate first: the Q0 rejection line (a character clause with no failure visibility is not
  admitted), the four values of `enforcement:` and the
  `check=` namespace, placement discipline and the exclusion list (the record area and the constitution
  are explicitly exempt), and the self-reference escape hard constraint.
  It governs **what was said having to hold**, not what was left unsaid. The machine landing point is
  `runtime.rule_enforcement_integrity`.
- `canon_carrier.md`: the canonical carrier for teaching body text (the G2 floor, EV-0030). In a
  textbook-driver course, teaching body text counts only once it has been written through
  `70_tools/canon_append.py` into `teaching_log.md` + `emissions.jsonl`;
  chat sends only a pointer. The machine landing point is `runtime.canonical_teaching_carrier`
  (CANON-000..004, an inconsistency
  detector: it catches a naive bypass, not a self-consistent double write, and it is not the ADR-0002
  hard gate).
- `host_g1_optional.md`: the optional host G1 pre-write interception (a reinforcement, not a floor). A
  shell may be marked "can be opened" only after passing the four-cell test;
  it does not enter doctor, the course directory, or a release surface. Grok was tested 2026-08-19 as
  openable but is not resident.
- `okf_adaptation.md`: the OKF v0.2 knowledge-bundle adaptation protocol (`T2AG-OKF-1`, EV-0024). How the
  main repository is expressed as an
  exchangeable OKF bundle: the scope allowlist, the frontmatter mapping, promoting a backtick reference
  into a graph edge, and the
  leak gate before writing to disk; the final section is the phase-two import boundary (rules only, with
  implementation unauthorized). The machine landing point is `70_tools/okf_export.py`.
- `environment_assumptions.md`: the host environment assumption register (`EA-XXXX`). Environment
  preconditions that hold in the code but were never written into a rule, each with a probe method and
  the correct response when the probe fails; implemented by doctor's `runtime.environment`.
- `changelog_management.md`: the changelog verification layer (drift traces / non-rot). The anchoring and
  corroborating layers are written separately;
  the form list is reused from `handoff_management.md` §5.6.2. **It does not prove completeness.** Before
  U3 landed it was a normative convention;
  doctor's automatic comparison is the later `runtime.changelog` (implementation not authorized in this
  batch).
