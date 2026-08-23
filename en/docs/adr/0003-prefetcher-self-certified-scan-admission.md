---
adr_id: ADR-0003
portable_key: prefetcher-self-certified-scan-admission
status: accepted
authority_project: T2AG
source_evolution: [EV-0019]
supersedes: []
implementation_refs:
  - main/50_playbook/source_page_assets.md
  - main/50_playbook/startup_orchestration.md
  - main/70_tools/t2ag_context.py
---

# ADR-0003: host-observable self-certification for scan admission

**Status:** accepted　**source_evolution:** EV-0019

Textbook-course admission was originally designed to require a host Scan Orchestrator that aggregates
PageViewOpened events and issues a receipt (the ADR-0002 family). That component does not exist in the
current hosts (Cowork/WorkBuddy) and will not exist soon (EA-0004, P-0056), so textbook critical was
permanently `route_ready + blocking_teach=true`: the "degraded path" became the only path, yet was
maintained as a temporary state — every textbook startup carried a debt against a condition that could
never be met.

**Decision**: the formal criterion for session scan complete becomes — **A1–A5 of
`source_page_assets.md` §3.1 proven within this session through host-observable tool-call delivery**.
Before that proof, the pending state must not be cleared; a self-reported opened/complete with no
delivery, a Snapshot, a historical receipt, and a hash check are none of them proof (the §3.1.3 Layer A
"must never pose as" clause stands unchanged). The A2/A4 full-preload semantics are unchanged.

**Future state**: when a host gains orchestrator / interceptor capability, issuance authority returns to
it, the host-issued criterion is restored, and this ADR is superseded; the `lesson_emit` egress boundary
of ADR-0002 likewise remains a future state.

**Defences**: delivery is host-observable, the SHA chain is recomputable, boot is always pending
(guaranteed structurally by the compiler), and the specification anchors are tested
(`test_context_packet.py::ScanEvidenceSpecTests`). A trace does not prevent fabrication; it prevents
delayed discovery (the same criterion as EV-0018).

**Adjudication source**: the student's three consecutive adjudications in the round of 2026-08-08; the
work order is
`docs/handoffs/T2AG_SCAN_CONTRACT_NORMALIZATION_WORKORDER_2026-08-08.md` (on the workspace side).
