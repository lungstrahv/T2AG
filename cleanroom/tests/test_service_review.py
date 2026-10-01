"""Non-author service/model regressions using explicit synthetic bad snapshots.

Internal fixture installation deliberately bypasses domain planners to test that
recovery/doctor do not mistake journal structural integrity for domain validity.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from t2ag_next import service, support, learning
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, get, put


class ServiceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "instance"
        self.store = Journal(self.path)
        self.store.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, effects):
        request = {"request_id": "review-fixture", "action": "internal.synthetic_fixture",
                   "payload": {}, "actor": {"role": "system", "source": "non-author regression fixture", "text": "Synthetic state."},
                   "expected": {}}
        self.store.apply(request, lambda *_: effects)

    def textbook(self, session_changes=None, scan_changes=None, include_scan=True):
        session = {"activity_id": "C/L", "course_id": "C", "status": "active", "readiness": "ready",
                   "scope_id": "scope-current", "preparation_id": "prep-current", "scan_id": "scan-current"}
        scan = {"session_id": "session-current", "scope_id": "scope-current", "deliveries": []}
        session.update(session_changes or {})
        scan.update(scan_changes or {})
        effects = [put("course", "C", {"title": "Synthetic", "course_type": "mastery", "learning_mode": "textbook",
                                      "status": "ongoing", "source_ids": [], "current_activity_id": "C/L"}),
                   put("activity", "C/L", {"course_id": "C", "activity_type": "lesson", "status": "ongoing",
                                           "scope_id": "scope-current", "preparation_id": "prep-current"}),
                   put("session", "session-current", session)]
        if include_scan:
            effects.append(put("scan", "scan-current", scan))
        self.seed(effects)

    def context(self):
        return service.context(self.path, entry="entry.teach", session_lane="teach", scope="C", session_id="session-current")

    def test_model_get_returns_copy(self):
        self.seed([put("note", "n", {"nested": {"value": "original"}})])
        state = self.store.read_state()
        value = get(state, "note", "n")
        value["nested"]["value"] = "changed"
        self.assertEqual(state["objects"]["note/n"]["data"]["nested"]["value"], "original")

    def test_svc_r1_rehashed_full_plan_cannot_remove_checks(self):
        self.seed([put("course", "C", {"title": "Synthetic", "status": "ongoing", "current_activity_id": "missing"})])
        self.assertFalse(service.doctor(self.path, full=True)["ok"])
        plan = service.check_plan(self.store.read_state(), full=True)
        plan["checks"] = []
        plan["plan_sha256"] = support.digest({k: v for k, v in plan.items() if k != "plan_sha256"})
        with self.assertRaises(DomainError):
            service.doctor(self.path, plan=plan)

    def test_svc_r2_historical_scan_cannot_mark_current_session_ready(self):
        self.textbook(scan_changes={"session_id": "old-session", "scope_id": "old-scope"})
        self.assertFalse(self.context()["learning_ready"])

    def test_svc_r2_missing_scan_cannot_mark_ready(self):
        self.textbook(include_scan=False)
        self.assertFalse(self.context()["learning_ready"])

    def test_svc_r2_pending_session_cannot_mark_ready(self):
        self.textbook(session_changes={"readiness": "source_pending"})
        self.assertFalse(self.context()["learning_ready"])

    def test_svc_r2_changed_preparation_cannot_mark_ready(self):
        self.textbook(session_changes={"preparation_id": "old-preparation"})
        self.assertFalse(self.context()["learning_ready"])

    def test_svc_r3_audit_entry_can_restore_maintain_lane_without_teaching(self):
        self.seed([put("handoff", "h", {"status": "active", "lane": "maintain", "scope": "feature", "source_versions": {}})])
        result = service.context(self.path, entry="entry.audit", session_lane="maintain", scope="feature")
        self.assertEqual(result["lane"], "maintain")
        self.assertEqual([row["id"] for row in result["handoffs"]], ["h"])
        self.assertFalse(result["learning_ready"])
        self.assertNotIn("course", result)

    def test_svc_r3_missing_lane_is_not_inferred(self):
        with self.assertRaises(DomainError):
            service.context(self.path, entry="entry.audit")

    def test_svc_r4_missing_scope_and_preparation_are_not_ready_evidence(self):
        self.textbook()
        self.assertFalse(self.context()["learning_ready"])

    def test_svc_r4_full_doctor_detects_session_scan_identity_conflict(self):
        self.textbook(scan_changes={"session_id": "old-session"})
        self.assertFalse(service.doctor(self.path, full=True)["ok"])

    def test_svc_r5_complete_identity_closure_does_not_bless_unverified_or_mismatched_page(self):
        source_sha = "a" * 64
        text = "Source statement."
        objects = {}
        def add(kind, identity, data):
            objects[kind + "/" + identity] = {"kind": kind, "id": identity, "version": 1, "data": data}
        add("session", "S", {"activity_id": "C/L", "status": "active", "readiness": "ready", "scope_id": "Scope", "preparation_id": "Prep", "scan_id": "Scan"})
        add("activity", "C/L", {"scope_id": "Scope", "preparation_id": "Prep"})
        add("scope", "Scope", {"activity_id": "C/L", "page_ids": ["P"]})
        add("preparation", "Prep", {"activity_id": "C/L", "scope_id": "Scope", "lessonmap_id": "Map", "receipts": [{"page_id": "P"}]})
        add("lessonmap", "Map", {"activity_id": "C/L", "scope_id": "Scope", "page_ids": ["P"]})
        add("source", "Doc", {"content_sha256": source_sha, "page_count": 1})
        page = {"source_id": "Doc", "pdf_page_index": 1, "layout_critical": False, "verified_text": text,
                "verified_text_sha256": learning.digest(text),
                "verification": {"status": "verified", "source_document_sha256": source_sha}}
        add("page", "P", page)
        add("page_head", "Doc/1", {"page_id": "P"})
        add("scan", "Scan", {"session_id": "S", "scope_id": "Scope", "deliveries": [{"page_id": "P", "session_id": "S",
            "source_document_sha256": source_sha, "form": "verified_text", "content": text}]})
        state = {"revision": 1, "objects": objects}
        self.assertTrue(service.teaching_readiness(state, "S", "C/L")["ready"])
        invalids = [
            {"migration_requires_reconciliation": True},
            {"verification": {"status": "unresolved", "source_document_sha256": source_sha}},
            {"verification": {"status": "verified", "source_document_sha256": "b" * 64}},
            {"verified_text_sha256": "c" * 64}]
        for changes in invalids:
            with self.subTest(changes=changes):
                bad = deepcopy(state)
                bad["objects"]["page/P"]["data"].update(changes)
                self.assertFalse(service.teaching_readiness(bad, "S", "C/L")["ready"])
        bad = deepcopy(state)
        bad["objects"]["source/Doc"]["data"]["migration_requires_reconciliation"] = True
        self.assertFalse(service.teaching_readiness(bad, "S", "C/L")["ready"])

    def test_compact_context_versions_bind_named_decisions_without_unrelated_enumeration(self):
        effects = [put("student", "current", {"language": "zh"}),
                   put("course", "C", {"status": "ongoing", "learning_mode": "goal", "current_activity_id": "C/L"}),
                   put("activity", "C/L", {"course_id": "C", "status": "ongoing"}),
                   put("cursor", "C/L", {"next_action": "ask"}),
                   put("question", "C/Q", {"course_id": "C", "status": "open"}),
                   put("reflection", "C/R", {"course_id": "C", "body": "long note" * 1000}),
                   put("suggestion", "C/S", {"scope": "C", "status": "proposed", "body": "long note" * 1000})]
        effects += [put("question", "D/Q" + str(n), {"course_id": "D", "status": "open", "text": "unrelated"}) for n in range(100)]
        self.seed(effects)
        packet = service.context(self.path, entry="entry.teach", session_lane="teach", scope="C", level="critical")
        self.assertEqual(set(packet["versions"]), {"student/current", "course/C", "activity/C/L", "cursor/C/L",
                                                   "question/C/Q", "reflection/C/R", "suggestion/C/S"})
        self.assertFalse(any("body" in row for row in packet["methods"] + packet["suggestions"]))
        self.assertLess(packet["size"]["utf8_bytes_before_size_field"], 10000)

    def test_new_doctor_groups_reject_broken_domain_claims(self):
        cases = [
            ("learning_history", [put("review", "bad", {"attempt_id": "missing", "criterion_id": "missing"})], "review.broken_evidence"),
            ("authorization", [put("ticket", "bad", {"status": "issued", "session_id": "missing", "activity_id": "C/L"})], "ticket.invalid_session"),
            ("exchange", [put("contribution", "bad", {"envelope": {}})], "exchange.invalid_envelope"),
            ("lifecycles", [put("reading", "bad", {"status": "impossible"})], "lifecycle.unknown")]
        for name, effects, expected in cases:
            with self.subTest(check=name):
                path = Path(self.temp.name) / name
                store = Journal(path); store.initialize()
                store.apply({"request_id": "fixture", "action": "internal.fixture", "payload": {}, "expected": {},
                             "actor": {"role": "system", "source": "synthetic review", "text": name}}, lambda *_: effects)
                report = service.doctor(path, changed_kinds=[effects[0]["kind"]])
                self.assertIn(name, report["plan"]["checks"])
                self.assertFalse(report["ok"])
                self.assertTrue(any(item["code"] == expected and item["status"] == "FAIL" for item in report["findings"]))


if __name__ == "__main__":
    unittest.main()
