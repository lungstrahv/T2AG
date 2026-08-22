#!/usr/bin/env python3
"""Pure contract for host-controlled textbook teaching egress.

This module is a **design and unit-test anchor** for ADR-0002 / host-teaching-egress-api.
It does **not** send messages, intercept chat, or establish a structural hard gate by
itself. A real host must wire these transitions into the outbound path.

This change reduces accidental policy bypass when combined with critical-packet
withhold logic, but host-runtime enforcement remains required.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Mapping


class EmitResultCode(str, Enum):
    EMITTED = "EMITTED"
    ALREADY_EMITTED = "ALREADY_EMITTED"
    NO_ADMISSION = "NO_ADMISSION"
    ADMISSION_EXPIRED = "ADMISSION_EXPIRED"
    SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
    BLOCK_MISMATCH = "BLOCK_MISMATCH"
    EGRESS_DISABLED = "EGRESS_DISABLED"
    RESERVE_CONFLICT = "RESERVE_CONFLICT"
    SEND_FAILED = "SEND_FAILED"
    ABORTED = "ABORTED"


class CapabilityStatus(str, Enum):
    ISSUED = "issued"
    RESERVED = "reserved"
    CONSUMED = "consumed"
    ABORTED = "aborted"
    REVOKED = "revoked"


class EgressMode(str, Enum):
    """Textbook-gated session modes (host configuration)."""

    FREEFORM = "freeform"  # not allowed while textbook-gated hard path is on
    STATUS_TEMPLATE = "status_template"
    LESSON_EMIT = "lesson_emit"


@dataclass(frozen=True)
class SessionEgressPolicy:
    freeform_egress: str = "disabled"
    status_template_egress: str = "host_only"
    teaching_egress: str = "lesson_emit_only"

    def freeform_allowed(self) -> bool:
        return self.freeform_egress == "enabled"

    def teaching_via_lesson_emit_only(self) -> bool:
        return self.teaching_egress == "lesson_emit_only"


@dataclass(frozen=True)
class TeachingAdmissionCapability:
    capability_id: str
    runtime_session_nonce: str
    critical_snapshot_id: str
    scope_visual_scan_receipt_id: str
    teaching_block_id: str
    pdf_page_index: int
    teaching_block_version: str | None = None
    max_uses: int = 1
    status: CapabilityStatus = CapabilityStatus.ISSUED
    reserved_emission_id: str | None = None
    consumed_emission_id: str | None = None
    expired: bool = False


@dataclass(frozen=True)
class EmissionRecord:
    emission_id: str
    teaching_block_id: str
    content_sha256: str
    result: EmitResultCode


@dataclass
class HostEgressStore:
    """In-memory host store for pure contract tests (not production persistence)."""

    policy: SessionEgressPolicy = field(default_factory=SessionEgressPolicy)
    capabilities: dict[str, TeachingAdmissionCapability] = field(default_factory=dict)
    emissions: dict[str, EmissionRecord] = field(default_factory=dict)
    # private reserve log; TeachingBlockEmitted only after successful send
    reserved: dict[str, str] = field(default_factory=dict)  # emission_id -> capability_id

    def put_capability(self, cap: TeachingAdmissionCapability) -> None:
        self.capabilities[cap.capability_id] = cap


@dataclass(frozen=True)
class EmitResult:
    code: EmitResultCode
    detail: str = ""
    emission_id: str | None = None
    capability_id: str | None = None


def content_digest(content: str) -> str:
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def find_session_block_capability(
    store: HostEgressStore,
    *,
    session_nonce: str,
    teaching_block_id: str,
) -> TeachingAdmissionCapability | None:
    """Locate capability by session+block before finer mismatch codes."""
    for cap in store.capabilities.values():
        if cap.runtime_session_nonce != session_nonce:
            continue
        if cap.teaching_block_id != teaching_block_id:
            continue
        if cap.status not in {
            CapabilityStatus.ISSUED,
            CapabilityStatus.RESERVED,
            CapabilityStatus.CONSUMED,
            CapabilityStatus.ABORTED,
            CapabilityStatus.REVOKED,
        }:
            continue
        return cap
    return None


def lesson_emit(
    store: HostEgressStore,
    *,
    session_nonce: str,
    teaching_block_id: str,
    emission_id: str,
    content: str,
    critical_snapshot_id: str,
    teaching_block_version: str | None = None,
    pdf_page_index: int | None = None,
    send_ok: bool = True,
) -> EmitResult:
    """Pure lesson_emit state machine.

    ``send_ok`` simulates transport success/failure. Real hosts replace it with
    the actual send and must commit only after success.
    """
    if store.policy.teaching_via_lesson_emit_only() is False:
        return EmitResult(EmitResultCode.EGRESS_DISABLED, "teaching_egress not lesson_emit_only")

    prior = store.emissions.get(emission_id)
    digest = content_digest(content)
    if prior is not None:
        if prior.content_sha256 == digest and prior.result == EmitResultCode.EMITTED:
            return EmitResult(
                EmitResultCode.ALREADY_EMITTED,
                "idempotent replay",
                emission_id=emission_id,
            )
        if prior.content_sha256 != digest:
            return EmitResult(
                EmitResultCode.BLOCK_MISMATCH,
                "emission_id reused with different content",
                emission_id=emission_id,
            )
        if prior.result == EmitResultCode.EMITTED:
            return EmitResult(
                EmitResultCode.ALREADY_EMITTED,
                emission_id=emission_id,
            )

    cap = find_session_block_capability(
        store,
        session_nonce=session_nonce,
        teaching_block_id=teaching_block_id,
    )
    if cap is None:
        return EmitResult(EmitResultCode.NO_ADMISSION, "no matching capability")

    if cap.expired or cap.status == CapabilityStatus.REVOKED:
        return EmitResult(
            EmitResultCode.ADMISSION_EXPIRED,
            "capability expired or revoked",
            capability_id=cap.capability_id,
        )

    if cap.critical_snapshot_id != critical_snapshot_id:
        return EmitResult(
            EmitResultCode.SNAPSHOT_MISMATCH,
            capability_id=cap.capability_id,
        )

    if (
        cap.teaching_block_version is not None
        and teaching_block_version is not None
        and cap.teaching_block_version != teaching_block_version
    ):
        return EmitResult(
            EmitResultCode.BLOCK_MISMATCH,
            "block_version",
            capability_id=cap.capability_id,
        )

    if pdf_page_index is not None and cap.pdf_page_index != pdf_page_index:
        return EmitResult(
            EmitResultCode.BLOCK_MISMATCH,
            "pdf_page_index",
            capability_id=cap.capability_id,
        )

    if cap.status == CapabilityStatus.CONSUMED:
        if cap.consumed_emission_id == emission_id:
            return EmitResult(
                EmitResultCode.ALREADY_EMITTED,
                emission_id=emission_id,
                capability_id=cap.capability_id,
            )
        return EmitResult(EmitResultCode.NO_ADMISSION, "capability already consumed")

    if cap.status == CapabilityStatus.RESERVED:
        if cap.reserved_emission_id != emission_id:
            return EmitResult(
                EmitResultCode.RESERVE_CONFLICT,
                "capability reserved by another emission_id",
                capability_id=cap.capability_id,
            )
        # same emission_id retry after SEND_FAILED
    elif cap.status == CapabilityStatus.ISSUED:
        store.capabilities[cap.capability_id] = replace(
            cap,
            status=CapabilityStatus.RESERVED,
            reserved_emission_id=emission_id,
        )
        store.reserved[emission_id] = cap.capability_id
        cap = store.capabilities[cap.capability_id]
    else:
        return EmitResult(EmitResultCode.NO_ADMISSION, f"status={cap.status}")

    if not send_ok:
        # Hold reserved for same emission_id retry; do not free a second body.
        return EmitResult(
            EmitResultCode.SEND_FAILED,
            "transport failed; capability remains reserved for same emission_id",
            emission_id=emission_id,
            capability_id=cap.capability_id,
        )

    # commit after successful send
    store.capabilities[cap.capability_id] = replace(
        cap,
        status=CapabilityStatus.CONSUMED,
        consumed_emission_id=emission_id,
    )
    store.emissions[emission_id] = EmissionRecord(
        emission_id=emission_id,
        teaching_block_id=teaching_block_id,
        content_sha256=digest,
        result=EmitResultCode.EMITTED,
    )
    store.reserved.pop(emission_id, None)
    return EmitResult(
        EmitResultCode.EMITTED,
        emission_id=emission_id,
        capability_id=cap.capability_id,
    )


def abort_reserved(
    store: HostEgressStore,
    *,
    emission_id: str,
) -> EmitResult:
    """Abort a reserved emission without learner-visible send."""
    cap_id = store.reserved.get(emission_id)
    if not cap_id:
        return EmitResult(EmitResultCode.NO_ADMISSION, "nothing reserved")
    cap = store.capabilities.get(cap_id)
    if cap is None or cap.status != CapabilityStatus.RESERVED:
        return EmitResult(EmitResultCode.NO_ADMISSION, "not reserved")
    if cap.reserved_emission_id != emission_id:
        return EmitResult(EmitResultCode.RESERVE_CONFLICT)
    store.capabilities[cap_id] = replace(
        cap,
        status=CapabilityStatus.ABORTED,
        reserved_emission_id=None,
    )
    store.reserved.pop(emission_id, None)
    return EmitResult(
        EmitResultCode.ABORTED,
        emission_id=emission_id,
        capability_id=cap_id,
    )


def freeform_send(store: HostEgressStore, *, content: str) -> EmitResult:
    """Ordinary assistant path: disabled under textbook-gated policy."""
    del content  # content must not be delivered
    if not store.policy.freeform_allowed():
        return EmitResult(EmitResultCode.EGRESS_DISABLED, "freeform_egress disabled")
    return EmitResult(EmitResultCode.EMITTED, "unmanaged freeform (not textbook-gated)")


def status_template_emit(
    store: HostEgressStore,
    *,
    template_id: str,
    emission_id: str,
    allowed_templates: Mapping[str, str],
    slots: Mapping[str, str] | None = None,
) -> EmitResult:
    """Host-only fixed templates; model cannot supply free prose."""
    if store.policy.status_template_egress != "host_only":
        return EmitResult(EmitResultCode.EGRESS_DISABLED, "status_template_egress")
    if template_id not in allowed_templates:
        return EmitResult(EmitResultCode.EGRESS_DISABLED, "unknown template")
    if emission_id in store.emissions:
        return EmitResult(EmitResultCode.ALREADY_EMITTED, emission_id=emission_id)
    body = allowed_templates[template_id]
    if slots:
        try:
            body = body.format(**slots)
        except KeyError as exc:
            return EmitResult(EmitResultCode.BLOCK_MISMATCH, f"slot {exc}")
    digest = content_digest(body)
    store.emissions[emission_id] = EmissionRecord(
        emission_id=emission_id,
        teaching_block_id=f"template:{template_id}",
        content_sha256=digest,
        result=EmitResultCode.EMITTED,
    )
    return EmitResult(EmitResultCode.EMITTED, emission_id=emission_id)
