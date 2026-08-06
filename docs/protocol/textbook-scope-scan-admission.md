# Protocol: Textbook Scope Scan & Teaching Admission

**Status:** draft companion to [ADR-0002](../adr/0002-host-controlled-textbook-teaching-egress.md)  
**Authority:** packet fields are observability only; authorization is host-side only.

This document defines protocol objects for host-controlled textbook teaching egress.
It does **not** replace the architectural decision in ADR-0002.

## Pipeline

```text
Context compiler
    │  route-ready envelope (no copy-paste teaching body)
    ▼
Host Scan Orchestrator
    │  PageViewOpened(page_i)… → ScanJobCompleted
    ▼
ScopeVisualScanReceipt   (host/tool issuer only)
    ▼
Runtime Join Gate        (host deterministic validator)
    ▼
server-side TeachingAdmissionCapability
    ▼
lesson_emit(block_id, content, emission_id)
    │  re-check snapshot → validate block → atomic consume → log → send
    ▼
learner-visible message
```

Concurrent constraint for a textbook gated session:

```text
ordinary assistant egress = disabled | host fixed-template only
```

## ScopeVisualScanReceipt

### Semantics (strict)

Host confirms that every page image in the active LessonScope was **presented** in the
current runtime session via the designated visual tool path, with complete, conflict-free
page events binding the declared digests and indices.

It is **not** a proof that the model cognitively “understood” every page.

### Issuer

Only the **Host Scan Orchestrator** (or equivalent tool aggregate) after `ScanJobCompleted`.
Agents must not mint, flip, or assemble a complete receipt from partial self-reports.
Per-page open events may be recorded as they happen; **complete** receipt is only the
aggregate seal.

### Not substitutable by

- prepare-time `LoadReceipt` / `content_consumed`
- Prefetcher handoff text (`opened=true`, scan complete)
- historical session receipts, file hashes alone, or model memory

### Recommended fields

```yaml
receipt_id
schema_version

issuer_id
issuer_key_id
signature_or_mac

runtime_session_nonce    # preferred over conversation_id alone
conversation_id: optional
scan_job_id

critical_snapshot_id
preparation_snapshot_id
lesson_scope_version

source_document_sha256
scope_manifest_sha256
render_profile

ordered_pdf_page_indices

page_view_events:
  - event_id
    pdf_page_index
    rendered_asset_sha256
    source_document_sha256
    render_profile
    opened_at
    tool_identity

completed_at
conflicts: []
```

`runtime_session_nonce` is issued once per classroom runtime start and must not be reused
across sessions. Missing page, open conflict, digest mismatch, snapshot change, or nonce
mismatch → fail-closed (no complete receipt).

## TeachingAdmissionCapability

### Semantics

Server-side, **one-shot**, **block-scoped** authority to emit exactly one teaching block
through `lesson_emit`. Not a whole-lesson pass, not a whole-page pass.

### Visibility

Prefer **not** exposing the capability body to the model. The model submits:

```text
lesson_emit(block_id, content, emission_id)
```

The host resolves admission from runtime context (session nonce, current page contract,
issued capability store). If an opaque handle is ever used, it must be MAC/signed and
validated only by the emission boundary — never trusted because it appeared in model output.

### Recommended fields (host store)

```yaml
capability_id
audience: lesson_emit

runtime_session_nonce
critical_snapshot_id
scope_visual_scan_receipt_id

pdf_page_index
teaching_block_id
action: emit_teaching_block

max_uses: 1
not_before
expires_at
status: issued | reserved | consumed | revoked
```

### Issue conditions (Join Gate)

Host verifies, among other invariants:

- complete ScopeVisualScanReceipt for the same nonce + critical snapshot + prep + scope;
- page-contract presentation requirements met for the admitted block’s page;
- no admission-related job still running (see “Background fail-closed” below);
- no source / route / snapshot conflict.

### Invalidate / revoke when

session nonce ends; critical snapshot, source, scope, page, or block identity changes;
receipt conflicts appear; capability expires; concurrent superseding admission.

Later blocks require new capabilities after their own understand / feel / continue / page
gates — first capability does not authorize the rest of the lesson.

## lesson_emit atomicity

Do **not** use:

```text
validate → mark consumed → send
```

Use a single logical transaction with an **idempotent emission_id**:

```text
validate
→ reserve capability (exclusive)
→ enqueue/send
→ commit: status=consumed + TeachingBlockEmitted(emission_id, …)
```

Rules:

- retry must reuse the same `emission_id` (no second teaching body on retry);
- concurrent callers must not both pass validate against the same one-shot capability;
- send failure after reserve must leave a recoverable state that does not free a second
  independent emit of different content without explicit host policy;
- success path always writes the session event log entry used by audit.

## Critical packet (observability only)

Before scan/admission, preferred shape:

```yaml
status: route_ready
blocking_teach: true

teaching_gate:
  scope_scan_required: true
  scope_scan_status: pending
  admission_status: unavailable
  egress_mode: status_only
```

Carry identities and structure, not copy-ready teaching body:

- route and exact stop identity;
- SourceDocument / preparation / scope version identities;
- scope_scan manifest (inputs only — never self-reported complete);
- page contract structure identity or reference.

Omit or isolate until after controlled emit path may fetch content:

- `textbook_excerpt` as sendable prose;
- first teaching candidate body;
- lesson opening text that can be pasted verbatim to the learner.

**Normative rule:** packet fields never authorize. Only a live host-side admission does.

## Background fail-closed (narrow)

**Must block capability issue while any of these run or are incomplete:**

- Scope scan job;
- receipt aggregation;
- admission / Join Gate validation tied to the same session nonce and snapshot.

**Must not** (in this protocol) force-merge into teaching admission:

- Runtime Sentinel full path;
- full Markdown L0 background settle;
- runtime Doctor completion.

Those remain under `recovery-settled` / write gates per existing startup design
(`learning_ready_first`). Changing that merge is a separate decision.

## Assurance layers

| Layer | Role |
|---|---|
| Host emission boundary | Real-time prevent (only hard gate) |
| Session audit | Detect TeachingBlockEmitted without valid consumption chain |
| Runtime Doctor | Schema, validators, invalidation rules, event-chain integrity — not live intercept |

## Relation to LoadReceipt

Prepare-time load receipts prove **preparation consumption** at snapshot build time.
They never satisfy this protocol’s session visual-scan or teaching admission requirements.

## Host egress API (normative pointer)

Full call shapes, result codes, channel modes, and atomic reserve/commit rules:

→ [host-teaching-egress-api.md](./host-teaching-egress-api.md)

Pure state-machine anchor (no message send):

→ `main/70_tools/host_teaching_egress.py`

### lesson_emit signature (summary)

```text
lesson_emit(session_nonce, teaching_block_id, emission_id, content,
            teaching_block_version?=None, pdf_page_index?=None) -> EmitResult
```

Model does not pass capability bodies. Host resolves admission server-side.

### EmitResult codes (summary)

`EMITTED` · `ALREADY_EMITTED` · `NO_ADMISSION` · `ADMISSION_EXPIRED` ·
`SNAPSHOT_MISMATCH` · `BLOCK_MISMATCH` · `EGRESS_DISABLED` · `RESERVE_CONFLICT` ·
`SEND_FAILED` · `ABORTED`

### Capability status (summary)

`issued | reserved | consumed | aborted | revoked`

`TeachingBlockEmitted` is written **only after successful send**, not at reserve time.

### Textbook gated channels (summary)

```text
freeform_egress: disabled
status_template_egress: host_only
teaching_egress: lesson_emit_only
```

### Defense-in-depth in context compiler (non-authorizing)

When `scope_scan` is pending, `t2ag_context.build_critical_packet` uses
`status=route_ready`, `blocking_teach=true`, and withholds copy-ready teaching bodies.
Packet fields remain observability-only.
