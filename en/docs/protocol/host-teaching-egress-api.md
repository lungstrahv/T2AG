# Host Teaching Egress API (design)

**Status:** design specification — **not implemented as a structural hard gate**  
**Companion:** [ADR-0002](../adr/0002-host-controlled-textbook-teaching-egress.md),
[textbook-scope-scan-admission.md](./textbook-scope-scan-admission.md)  
**Code contract (pure, host-agnostic):** `main/70_tools/host_teaching_egress.py`

This document defines the host-owned emission boundary for textbook teaching. Until a
real host wires these calls into the message path, the repository only provides
defense-in-depth packet shaping and pure contract tests.

## Session egress modes (textbook gated)

```yaml
freeform_egress: disabled          # ordinary assistant free text must not reach learner
status_template_egress: host_only  # fixed templates only, filled by host
teaching_egress: lesson_emit_only  # teaching prose only via lesson_emit
```

Non-textbook sessions may keep unmanaged freeform egress until separately gated.

## Primary API: lesson_emit

```text
lesson_emit(
    session_nonce: str,
    teaching_block_id: str,
    emission_id: str,
    content: str,
    *,
    teaching_block_version: str | None = None,  # optional content-lineage pin
    pdf_page_index: int | None = None,          # host re-checks against admission
) -> EmitResult
```

### Model-visible contract

The model **must not** pass capability token bodies. The host resolves
`TeachingAdmissionCapability` from:

- `session_nonce` (runtime session),
- current critical snapshot / page contract,
- host capability store (`status=issued` for matching block).

### Binding: block_id vs block_version

| Field | Role |
|---|---|
| `teaching_block_id` | Stable id of the admitted teaching block (required; capability audience key) |
| `teaching_block_version` | Optional pin of block content lineage (hash or map revision). If the capability was issued with a version, emit must match; if capability has no version, host may admit id-only |

Admission is **block-scoped**, not page-scoped or lesson-scoped. A new block needs a new
capability after understand / feel / continue / page gates.

### EmitResult codes

| Code | Meaning |
|---|---|
| `EMITTED` | reserved → send succeeded → committed consumed + `TeachingBlockEmitted` |
| `ALREADY_EMITTED` | same `emission_id` already committed (idempotent success) |
| `NO_ADMISSION` | no live capability for this session/block |
| `ADMISSION_EXPIRED` | capability past `expires_at` or revoked |
| `SNAPSHOT_MISMATCH` | live critical/prep/scope era ≠ capability binding |
| `BLOCK_MISMATCH` | `teaching_block_id` / version / page ≠ capability |
| `EGRESS_DISABLED` | session not in teaching_egress mode or freeform attempted |
| `RESERVE_CONFLICT` | another in-flight reserve holds the one-shot capability |
| `SEND_FAILED` | transport failed after reserve; capability left `reserved` or `aborted` per policy |
| `ABORTED` | explicit abort of a reserved emission (no learner-visible body) |

### Atomic flow (normative)

Do **not**:

```text
validate → mark consumed → send
```

Do:

```text
validate
→ reserve(capability, emission_id)     # status: issued → reserved
→ enqueue/send(content)
→ on success: commit
      capability: reserved → consumed
      event: TeachingBlockEmitted(emission_id, …)
→ on failure: abort_or_hold
      capability: reserved → aborted (or hold reserved for same emission_id retry)
      event: TeachingEmissionAborted / TeachingEmissionHeld
```

Rules:

1. Retry **must** reuse the same `emission_id`.
2. Same `emission_id` + same content after commit → `ALREADY_EMITTED`.
3. Same `emission_id` + **different** content → hard fail (never second body).
4. Concurrent emits against one one-shot capability → one wins reserve; others
   `RESERVE_CONFLICT` or `NO_ADMISSION`.
5. Audit: **commit event only after successful send**. Reserve may write a private
   host log; learner-audit `TeachingBlockEmitted` is success-path only.

### Capability lifecycle (host store)

```text
issued → reserved → consumed
                 ↘ aborted
issued → revoked
issued → expired (logical)
```

## Status template API (same boundary)

Fixed host templates (for example “checking the textbook page”) also pass the emission boundary so freeform
cannot be smuggled as “status”:

```text
status_emit(
    session_nonce: str,
    template_id: str,
    emission_id: str,
    slots: mapping[str, str] | None = None,  # host-validated slot fill only
) -> EmitResult
```

- Templates are host-owned strings; model cannot supply arbitrary prose.
- Codes reuse the EmitResult set where applicable (`EGRESS_DISABLED`, `ALREADY_EMITTED`, …).
- Does **not** consume a teaching capability.

## Freeform assistant path

While `freeform_egress: disabled`:

```text
assistant_freeform_send(...) → EGRESS_DISABLED
```

There is no semantic classifier exception. Opening text, scan summaries, and “short
answers” that contain teaching prose must use `lesson_emit` after admission, or a host
template if they are pure status.

## Events (session audit log)

Minimum event types:

| Event | When |
|---|---|
| `ScopeScanJobStarted` / `PageViewOpened` / `ScanJobCompleted` | scan path |
| `ScopeVisualScanReceiptIssued` | host seals receipt |
| `TeachingAdmissionIssued` | Join Gate |
| `TeachingEmissionReserved` | optional private host log |
| `TeachingBlockEmitted` | **after** successful learner-visible send |
| `TeachingEmissionAborted` | reserve released without send |
| `TeachingAdmissionRevoked` | snapshot/session/block invalidation |

## Relation to critical packet (defense-in-depth)

`t2ag_context.py` may emit:

```yaml
status: route_ready
blocking_teach: true
teaching_gate:
  admission_status: unavailable
  egress_mode: status_only
  packet_fields_do_not_authorize_emission: true
```

and withhold copy-ready teaching bodies. That **reduces accidental policy bypass** but
**does not** implement this API or intercept model messages.

## Implementation checklist (host)

- [ ] Runtime session nonce at classroom start
- [ ] Message interceptor / channel split (freeform / template / lesson_emit)
- [ ] Capability store with issued|reserved|consumed|aborted|revoked
- [ ] Atomic reserve→send→commit with emission_id idempotency
- [ ] Session event log readable by audit + Doctor schema checks
- [ ] Wire Join Gate as host code, not Main playbook reasoning
