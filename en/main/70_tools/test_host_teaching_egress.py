#!/usr/bin/env python3
"""Pure-contract tests for host teaching egress (not host interception proof)."""
from __future__ import annotations

import unittest

import host_teaching_egress as egress


def _cap(**kwargs: object) -> egress.TeachingAdmissionCapability:
    base = dict(
        capability_id="cap-1",
        runtime_session_nonce="nonce-A",
        critical_snapshot_id="CTX-1",
        scope_visual_scan_receipt_id="rcpt-1",
        teaching_block_id="B1",
        pdf_page_index=26,
        teaching_block_version="v1",
    )
    base.update(kwargs)
    return egress.TeachingAdmissionCapability(**base)  # type: ignore[arg-type]


class LessonEmitContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = egress.HostEgressStore()
        self.store.put_capability(_cap())

    def test_lesson_emit_happy_path_consumes_once(self) -> None:
        r1 = egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="第一教学块正文",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
        )
        self.assertEqual(r1.code, egress.EmitResultCode.EMITTED)
        r2 = egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-2",
            content="第二块尝试",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
        )
        self.assertEqual(r2.code, egress.EmitResultCode.NO_ADMISSION)

    def test_idempotent_emission_id(self) -> None:
        kwargs = dict(
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="同一正文",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
        )
        self.assertEqual(
            egress.lesson_emit(self.store, **kwargs).code,
            egress.EmitResultCode.EMITTED,
        )
        self.assertEqual(
            egress.lesson_emit(self.store, **kwargs).code,
            egress.EmitResultCode.ALREADY_EMITTED,
        )

    def test_emission_id_content_mismatch_rejected(self) -> None:
        egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="A",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
        )
        bad = egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="B",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
        )
        self.assertEqual(bad.code, egress.EmitResultCode.BLOCK_MISMATCH)

    def test_snapshot_mismatch(self) -> None:
        r = egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="x",
            critical_snapshot_id="CTX-OTHER",
            teaching_block_version="v1",
            pdf_page_index=26,
        )
        self.assertEqual(r.code, egress.EmitResultCode.SNAPSHOT_MISMATCH)

    def test_block_version_mismatch(self) -> None:
        r = egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="x",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v9",
            pdf_page_index=26,
        )
        self.assertEqual(r.code, egress.EmitResultCode.BLOCK_MISMATCH)

    def test_send_failed_keeps_reserved_for_retry(self) -> None:
        fail = egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="正文",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
            send_ok=False,
        )
        self.assertEqual(fail.code, egress.EmitResultCode.SEND_FAILED)
        cap = self.store.capabilities["cap-1"]
        self.assertEqual(cap.status, egress.CapabilityStatus.RESERVED)
        ok = egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="正文",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
            send_ok=True,
        )
        self.assertEqual(ok.code, egress.EmitResultCode.EMITTED)

    def test_reserve_conflict_other_emission_id(self) -> None:
        egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="A",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
            send_ok=False,
        )
        other = egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-2",
            content="B",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
        )
        self.assertEqual(other.code, egress.EmitResultCode.RESERVE_CONFLICT)

    def test_abort_reserved(self) -> None:
        egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="A",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
            send_ok=False,
        )
        ab = egress.abort_reserved(self.store, emission_id="em-1")
        self.assertEqual(ab.code, egress.EmitResultCode.ABORTED)
        self.assertEqual(
            self.store.capabilities["cap-1"].status,
            egress.CapabilityStatus.ABORTED,
        )

    def test_freeform_disabled_under_textbook_policy(self) -> None:
        r = egress.freeform_send(self.store, content="偷偷讲课")
        self.assertEqual(r.code, egress.EmitResultCode.EGRESS_DISABLED)

    def test_status_template_host_only(self) -> None:
        templates = {"scan_wait": "正在核对教材页面（{pages}）"}
        r = egress.status_template_emit(
            self.store,
            template_id="scan_wait",
            emission_id="st-1",
            allowed_templates=templates,
            slots={"pages": "25-29"},
        )
        self.assertEqual(r.code, egress.EmitResultCode.EMITTED)
        again = egress.status_template_emit(
            self.store,
            template_id="scan_wait",
            emission_id="st-1",
            allowed_templates=templates,
            slots={"pages": "25-29"},
        )
        self.assertEqual(again.code, egress.EmitResultCode.ALREADY_EMITTED)

    def test_expired_capability(self) -> None:
        self.store.put_capability(_cap(expired=True, capability_id="cap-x"))
        # clear the live one to force the expired match path via same block search
        self.store.capabilities.clear()
        self.store.put_capability(_cap(expired=True))
        r = egress.lesson_emit(
            self.store,
            session_nonce="nonce-A",
            teaching_block_id="B1",
            emission_id="em-1",
            content="x",
            critical_snapshot_id="CTX-1",
            teaching_block_version="v1",
            pdf_page_index=26,
        )
        self.assertEqual(r.code, egress.EmitResultCode.ADMISSION_EXPIRED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
