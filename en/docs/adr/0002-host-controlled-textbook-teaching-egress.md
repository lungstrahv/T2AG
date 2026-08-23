---
adr_id: ADR-0002
portable_key: host-controlled-textbook-teaching-egress
status: proposed
authority_project: T2AG
source_evolution: [EV-0013]
supersedes: []
implementation_refs:
  - docs/protocol/host-teaching-egress-api.md
  - docs/protocol/textbook-scope-scan-admission.md
  - main/70_tools/host_teaching_egress.py
  - main/70_tools/t2ag_context.py
---

# ADR-0002: a host-controlled emission boundary for textbook teaching

**Status:** proposed  
**source_evolution:** EV-0013  
**Also:** accepted in principle for the architectural shape — **blocked on host-runtime
enforcement** (no claim of a structural hard gate until that exists)

## Context

The real decision is not “introduce receipts and capabilities”; it is:

> **Textbook teaching output must pass through a host-level emission boundary the model cannot bypass.**

`ScopeVisualScanReceipt` and `TeachingAdmissionCapability` are the **protocol objects** that implement
that boundary, not the boundary itself. The previous version, titled around the capability and marked
`accepted`, misled the reader: if the repository holds only fields and a playbook, saying so amounts to
claiming a hard gate already exists.

For a long time the implementation had only a **policy gate**, never an **enforcement gate**:

- (historically) critical could return `status: ready` and `blocking_teach: false` together with
  `scope_scan_status: pending_visual_scan` and `may_release_action: false` (mixed signals).
- The learning-ready condition was adjudicated by the Main Conductor, and Main is also the one who
  speaks outward; the trust chain was `read a field → the model judges → the same model speaks`.
- The Context Prefetcher writing `opened=true` / scan complete in a handoff is still an Agent's textual
  claim, not an unforgeable tool event.
- A preparation `LoadReceipt` proves only that a page was loaded at prepare time and **must not** pose as
  this session's Scope visual scan (see `source_page_assets.md`).

**Defence in depth (landed; still not a hard gate)**: while a Scope scan is pending, `t2ag_context.py`
emits `status: route_ready`, `blocking_teach: true`, `admission_status: unavailable`, and
`egress_mode: status_only`, and withholds directly-sendable teaching body text; the negative tests are in
`test_context_packet.py`. This **reduces accidental policy bypass but does not establish a
structural teaching-output gate. Host-runtime enforcement remains required.**

Until a host message interceptor, an enforced `lesson_emit`, a session output event log, and an
unforgeable capability store all exist, this decision must not be marked as an implemented hard gate.

## Decision

### The architectural decision (this ADR's only hard commitment)

1. **The host holds final emission authority.** An Agent (including the Main Conductor and the
   Prefetcher) is not part of the trusted computing base (TCB) for teaching egress.
2. **Textbook teaching body text may leave only through a host-controlled emission boundary** (the
   normative name is `lesson_emit`, or an equivalent host API). Validation, reservation, sending, and
   event writing are all performed by the host.
3. **In a textbook gated session the ordinary assistant exit must be closed, or restricted to fixed host
   templates** (for example “checking the textbook page”). The model must never carry textbook teaching
   body text through a freeform text channel.
   “We recommend using `lesson_emit`”, or classifying after the fact whether something was teaching,
   **is not** a hard gate.
4. **The Runtime Join Gate is a deterministic validator inside the host runtime**, not a reasoning step
   of Main's. An Agent must never simultaneously hold: the right to request, to judge the evidence, to
   approve, and to send.
5. Packet / playbook fields are **for observability and diagnosis only and confer no authorization**. The
   emission layer honours only a currently valid **server-side** admission; JSON visible to the model is
   never a source of authority.

### Protocol implementation (not an alternative decision to this ADR)

The objects, events and invalidation rules above the boundary are in:

- `docs/protocol/textbook-scope-scan-admission.md` — the receipt / admission protocol
- `docs/protocol/host-teaching-egress-api.md` — `lesson_emit` / channel modes / return codes / the atomic flow
- `main/70_tools/host_teaching_egress.py` — the pure state machine and the contract-test anchor (it does **not** send messages)

A summary (so that reading the ADR alone does not lose the context):

| Object | Role |
|---|---|
| Host Scan Orchestrator | aggregates PageViewOpened → ScanJobCompleted; issues the receipt |
| ScopeVisualScanReceipt | verifiable proof of **access and presentation**, not of “the model understood” |
| Runtime Join Gate | the host validator; issues a server-side TeachingAdmissionCapability |
| TeachingAdmissionCapability | a host-side single-use object bound to a **block_id** (optionally a **block_version**); the model only calls `lesson_emit` and never holds the token body |
| lesson_emit | re-validates the snapshot, binds the block, and **atomically** validate→reserve→send→commit consumed + event |

The distinction between `learning-ready` and `recovery-settled` is **kept**. The fail-closed “work is
still running in the background” refers only to work directly related to admission (the Scope scan job,
receipt aggregation, admission validation); it does **not** fold the Runtime Sentinel / the full L0 /
Doctor back into the same gate — those still follow the existing settled rules.

### Design closure (interface conclusions, 2026-08-06)

1. **Admission binding**: `teaching_block_id` is required; `teaching_block_version` is optional as a
   content-lineage pin. With a version, an emit must match it; without one, the id alone applies. It is
   not a whole-page or whole-lesson pass.
2. **Capability states**: `issued → reserved → consumed`, with `aborted` on failure, plus `revoked` /
   expired. `validate → mark used → send` is forbidden.
3. **Audit posting**: `TeachingBlockEmitted` is committed only **after a successful send**; a reservation
   may have a host-private log.
4. **Fixed status templates**: they share the egress boundary with teaching, through `status_emit`; the
   template body is held by the host and the model must never fill in freeform prose.
5. **The textbook gated channel**:
   `freeform_egress: disabled` · `status_template_egress: host_only` ·
   `teaching_egress: lesson_emit_only`。

### In-repository defence in depth (done; still not a hard gate)

- before a critical scan: `status: route_ready`, `blocking_teach: true`,
  `admission_status: unavailable`、`egress_mode: status_only`；
- withholds the directly-sendable `textbook_excerpt`, the first teaching candidate, the copyable opening body, and `prompt`;
- negative tests: `PendingScopeScanWithholdTests`; the host contract test: `test_host_teaching_egress.py`.

These **must not** be advertised as “an implemented structural hard gate”.

## Considered Options

| Option | Conclusion |
|---|---|
| add more booleans such as `teaching_released` + Doctor | rejected: ignorable, after the fact, no TCB boundary |
| receipt → Join Gate → capability, but the Join Gate still executed by Main | rejected: the trust boundary is unchanged |
| capability JSON visible to the model / the model carrying the token body | rejected: copyable and forgeable; it must be an opaque handle validated server-side or at the emission layer, and preferably invisible to the model |
| having `lesson_emit` while the ordinary assistant stays free | rejected: bypassable; it must be closed or templated |
| a semantic classifier filtering whether freeform text “looks like teaching” | rejected as a hard gate: misses plus disguise |
| host-controlled egress + the ordinary channel closed/templated | **chosen** (architecture) |
| folding all background work (Doctor included) into the teaching fail-closed | implicit folding rejected: it would cancel `learning_ready_first`; a separate decision |

## Consequences

- **A hard gate depends on the host runtime** and does not close inside plain Markdown plus an
  unconstrained chat exit. Until the host capability lands, the status stays
  **proposed / blocked on host enforcement**.
- An in-session event log is required (at minimum the receipt, capability issuance/consumption, and
  TeachingBlockEmitted) plus an emission idempotency key; without them there is no audit and no atomic
  consumption.
- Compatible with the existing Startup Formation / Prefetcher: the Prefetcher may trigger a scan job but
  **must not** self-report complete as a basis for authorization.
- Later blocks (comprehension / feeling / continue / page turn) may reuse the “host-issued block-scoped
  capability + `lesson_emit`” pattern; each block gets a new capability, not a whole-page or
  whole-lesson pass.
- The previous capability-centred formulation is void; this file and the protocol specification govern.
