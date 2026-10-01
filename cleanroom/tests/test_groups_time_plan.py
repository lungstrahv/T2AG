from pathlib import Path
import hashlib
import tempfile
import unittest

from t2ag_next import groups, service
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, put
from t2ag_next.support import digest


class GroupTimeAndClosingJourney(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "instance"
        self.store = Journal(self.path)
        self.store.initialize({"language": "en"})
        self.serial = 0
        for cid in ("ALG", "CODE"):
            self.act("course.create", {"id": cid, "title": cid, "course_type": "mastery", "learning_mode": "goal"})
            self.act("course.activate", {"id": cid})
            self.act("activity.create", {"id": cid + "/L", "course_id": cid, "activity_type": "lesson", "title": cid})
            self.act("activity.start", {"id": cid + "/L"})
        self.act("group.propose", {"id": "G", "members": ["ALG", "CODE"], "capacity": 2,
            "calendar": {"frequency": "preserved", "stagnation_days": 14, "cycle_anchor_learning_day": "TBD"},
            "thresholds": {"close_condition": "explicit course outcomes"}, "goal": "A synthetic two-course plan"})

    def tearDown(self):
        self.temp.cleanup()

    def request(self, action, payload, role="student", text="Use this exact synthetic plan."):
        self.serial += 1
        state = self.store.read_state()
        return {"request_id": "time-plan-" + str(self.serial), "action": action, "payload": payload,
            "actor": {"role": role, "source": "synthetic-test", "text": text},
            "expected": {key: row["version"] for key, row in state["objects"].items()}}

    def act(self, action, payload, **actor):
        return service.execute(self.path, self.request(action, payload, **actor))

    def data(self, kind, identity):
        return self.store.read_state()["objects"][kind + "/" + identity]["data"]

    def seed(self, kind, identity, data):
        request = self.request("fixture.seed", {})
        self.store.apply(request, lambda state, req: [put(kind, identity, data)])

    def plan(self):
        return {"period": "calendar_week", "week_starts_on": 0,
            "course_weekly_seconds": {"ALG": 43200, "CODE": 28800},
            "daily_total_max_seconds": 14400, "course_daily_seconds": {"ALG": 7200, "CODE": 5400},
            "other_daily_seconds": {"review": 1800}}

    def configure_time(self):
        self.act("group.time_plan.configure", {"group_id": "G", "basis": "student_decision", "reason": "Time plan", "time_plan": self.plan()})

    def conditions(self):
        return [{"id": "exit", "kind": "course_outcome", "course_id": "ALG", "description": "The agreed chapter exit is complete."},
                {"id": "readme", "kind": "artifact", "course_id": "CODE", "description": "The agreed README exists."},
                {"id": "debts", "kind": "debt_disposition", "description": "All member debts have an explicit disposition."},
                {"id": "review", "kind": "group_review", "description": "The final group assessment is recorded."}]

    def configure_close(self):
        self.act("group.closure.configure", {"group_id": "G", "basis": "student_decision", "reason": "The actual complete criteria",
            "conditions": self.conditions(), "requires_next_group_choice": True})

    def record(self, identity, refs, **extras):
        self.act("group.condition.record", {"group_id": "G", "id": "evidence-" + identity + "-" + str(self.serial + 1),
            "condition_id": identity, "verdict": "met", "rationale": "Attributed review of the cited actual records against the named condition.",
            "evidence_refs": refs, **extras})

    def fulfill(self):
        for status in ("queued", "arrived", "pending", "confirmed"):
            self.act("checkpoint.record", {"id": "exit-check", "activity_id": "ALG/L", "position": "chapter exit", "status": status,
                "body": "Actual synthetic exit evidence", "evidence": ["Actual synthetic checkpoint observation"]})
        self.act("completion.record", {"id": "exit-done", "course_id": "ALG", "judgment_kind": "comprehension", "evidence_ids": ["exit-check"]})
        self.record("exit", [{"kind": "completion", "id": "exit-done"}])
        content = "# Synthetic README\nThe artifact and its use."
        self.act("source.register", {"source_id": "README", "course_ids": ["CODE"], "title": "README", "format": "artifact",
            "source_version": "1", "content": content, "content_sha256": hashlib.sha256(content.encode()).hexdigest()}, role="teacher")
        self.record("readme", [{"kind": "source", "id": "README"}])
        self.record("debts", [], dispositions=[])
        self.act("group.review", {"id": "final", "group_id": "G", "frequency_observation": "Recorded separately",
            "progress_observation": "The named outputs were inspected", "judgment": {"phase": "final", "verdict": "met"},
            "evidence": ["Actual synthetic final review"]}, role="teacher")
        self.record("review", [{"kind": "group_review", "id": "final"}])

    def assessment(self):
        return groups.assessment(self.store.read_state(), "G", "2026-01-18T12:00:00Z")

    def test_time_budgets_are_consumed_without_changing_capacity_or_cycle_anchor(self):
        self.configure_time()
        for identity, cid, day, seconds in [("math", "ALG", 5, 7200), ("code", "CODE", 5, 5400), ("later", "ALG", 12, 3600)]:
            self.act("time.record", {"id": identity, "activity_id": cid + "/L", "quality": "exact", "seconds": seconds,
                "started_at": f"2026-01-{day:02}T12:00:00Z"})
        report = self.assessment()["time_budget"]
        self.assertEqual([row["week_start"] for row in report["weeks"]], ["2026-01-05", "2026-01-12"])
        self.assertEqual(report["weeks"][0]["courses"][0], {"course_id": "ALG", "actual_seconds": 7200, "budget_seconds": 43200, "difference_seconds": -36000})
        self.assertEqual(report["days"][0]["course_actual_seconds"], 12600)
        self.assertIsNone(report["days"][0]["other_actual_seconds"])
        self.assertEqual(self.data("group", "G")["capacity"], 2)
        self.assertEqual(self.data("group", "G")["calendar"]["cycle_anchor_learning_day"], "TBD")
        self.act("time.record", {"id": "unknown", "activity_id": "ALG/L", "quality": "unknown"})
        self.assertEqual(self.assessment()["time_budget"]["status"], "partial_unknown_time")

    def test_preserved_frozen_source_mapping_needs_no_new_student_agreement(self):
        group = self.data("group", "G")
        group.update(legacy={"snapshot_id": "frozen-test-snapshot"}, original_body="ALG 12h; CODE 8h; daily 4h.")
        self.seed("group", "G", group)
        ref = {"field": "original_body", "excerpt": group["original_body"], "value_sha256": digest(group["original_body"])}
        self.act("group.time_plan.configure", {"group_id": "G", "basis": "source_evidence", "source_refs": [ref], "reason": "Unit conversion of known historical facts", "time_plan": self.plan()}, role="teacher")
        self.assertEqual(self.data("group", "G")["time_plan_agreement"]["basis"], "source_evidence")

    def test_explicit_closing_conditions_work_without_generic_threshold_or_cycle_anchor(self):
        self.configure_time(); self.configure_close(); self.fulfill()
        report = self.assessment()
        self.assertEqual(report["status"], "met")
        self.assertEqual(len(report["closure_conditions"]), 4)
        self.assertFalse(report["threshold_results"])
        request = self.request("group.close", {"id": "G", "closure_plan_sha256": self.data("group", "G")["closure_plan_sha256"],
            "next_group_choice": {"kind": "later", "reason": "Choose the next group later."}})
        groups.validate_close(self.store.read_state(), request, self.data("group", "G"), report)
        del request["payload"]["next_group_choice"]
        with self.assertRaises(DomainError):
            groups.validate_close(self.store.read_state(), request, self.data("group", "G"), report)

    def test_actual_evidence_change_and_new_debt_invalidate_met_assessment(self):
        self.configure_close(); self.fulfill()
        self.seed("mistake", "new", {"course_id": "ALG", "status": "active"})
        report = self.assessment()
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(next(row for row in report["closure_conditions"] if row["id"] == "debts")["reason"], "condition_evidence_changed")
        self.record("debts", [{"kind": "mistake", "id": "new"}], dispositions=[{"kind": "mistake", "id": "new", "choice": "carry_forward", "reason": "Retain for the next learning cycle", "destination": "Next group"}])
        self.assertEqual(self.assessment()["status"], "met")
        self.assertEqual(self.data("mistake", "new")["status"], "active")

    def test_incomplete_evidence_and_unrelated_course_cannot_satisfy_condition(self):
        self.configure_close()
        self.act("checkpoint.record", {"id": "pending", "activity_id": "ALG/L", "position": "chapter exit", "status": "queued", "evidence": ["Actual synthetic observation"]})
        before = self.store.read_state()["revision"]
        with self.assertRaises(DomainError):
            self.record("exit", [{"kind": "checkpoint", "id": "pending"}])
        self.assertEqual(self.store.read_state()["revision"], before)
        self.seed("completion", "other", {"course_id": "CODE", "judgment_kind": "comprehension", "evidence_ids": []})
        with self.assertRaises(DomainError):
            self.record("exit", [{"kind": "completion", "id": "other"}])

    def test_public_close_consumes_complete_assessment_and_one_current_choice(self):
        self.configure_close()
        self.act("group.activate", {"id": "G", "proposal_sha256": self.data("group", "G")["proposal_sha256"]})
        self.act("group.assess", {"id": "incomplete", "group_id": "G", "as_of": "2026-01-18T12:00:00Z"})
        payload = {"id": "G", "closure_plan_sha256": self.data("group", "G")["closure_plan_sha256"],
            "assessment_id": "incomplete", "evidence": ["The complete recorded group assessment"],
            "next_group_choice": {"kind": "later", "reason": "Choose the next group later."}}
        before = self.store.read_state()["revision"]
        with self.assertRaises(DomainError):
            self.act("group.close", payload, text="Close this group and choose the next group later.")
        self.assertEqual(self.store.read_state()["revision"], before)
        self.fulfill()
        self.act("group.assess", {"id": "complete", "group_id": "G", "as_of": "2026-01-18T12:00:00Z"})
        payload["assessment_id"] = "complete"
        self.act("group.close", payload, text="Close this group and choose the next group later.")
        self.assertEqual(self.data("group", "G")["status"], "closed")
        self.assertEqual(self.data("group", "G")["next_group_choice"], payload["next_group_choice"])
        self.assertEqual(self.data("group", "G")["decision"]["text"], "Close this group and choose the next group later.")
        self.assertEqual(self.data("course", "ALG")["status"], "ongoing")

    def test_untriggered_legacy_exam_debt_is_not_omitted_or_invented_settled(self):
        self.configure_close(); self.fulfill()
        debt = {"course_id": "ALG", "status": "open", "sittings_used": "0",
            "settlement_authority": "legacy_ledger", "next_sitting": "Waiting for the first real trigger",
            "legacy_fields": {"type": "exam_ledger", "truth_scope": "exam_settlement", "schema_version": "exam_ledger.v1"}}
        self.seed("exam_debt", "ALG", debt)
        self.assertEqual(self.assessment()["status"], "unknown")
        before = self.store.read_state()["revision"]
        with self.assertRaises(DomainError):
            self.record("debts", [{"kind": "exam_debt", "id": "ALG"}],
                dispositions=[{"kind": "exam_debt", "id": "ALG", "choice": "closed"}])
        self.assertEqual(self.store.read_state()["revision"], before)
        self.record("debts", [{"kind": "exam_debt", "id": "ALG"}], dispositions=[{
            "kind": "exam_debt", "id": "ALG", "choice": "carry_forward",
            "reason": "Explicit current synthetic student choice", "destination": "The next agreed group"}])
        self.assertEqual(self.data("exam_debt", "ALG"), debt)
        self.assertEqual(self.assessment()["status"], "met")
        self.assertFalse(any(row["kind"] == "exam" for row in self.store.read_state()["objects"].values()))

    def test_agreed_member_frequency_survives_without_generic_closing_thresholds(self):
        self.configure_close()
        self.act("group.frequency.configure", {"group_id": "G", "basis": "student_decision", "reason": "Only ALG has an agreed frequency",
            "frequency_plan": {"count_unit": "sessions", "minimum_per_cycle": {"ALG": 3}}})
        pending = self.assessment()
        self.assertEqual(pending["frequency"], [])
        self.assertIn("cycle_anchor_or_length_not_agreed", pending["process_unresolved"])
        self.assertEqual(pending["frequency_plan"]["minimum_per_cycle"], {"ALG": 3})
        self.act("group.schedule.configure", {"id": "G", "reason": "An actual synthetic anchor decision",
            "calendar": {"cycle_anchor_learning_day": "2026-01-05", "cycle_length_learning_days": 6}})
        for day in range(5, 11):
            cid = "ALG" if day % 2 else "CODE"
            session_id = "recorded-session-" + str(day)
            self.act("session.start", {"session_id": session_id, "activity_id": cid + "/L"})
            self.act("time.record", {"id": "frequency-" + str(day), "activity_id": cid + "/L", "quality": "exact",
                "seconds": 60, "session_id": session_id, "started_at": f"2026-01-{day:02}T12:00:00Z"})
            self.act("session.close", {"session_id": session_id})
        observed = self.assessment()
        self.assertEqual(len(observed["frequency"]), 1)
        self.assertEqual(observed["frequency"][0]["course_id"], "ALG")
        self.assertEqual(observed["frequency"][0]["actual"], 3)
        self.assertEqual(observed["frequency"][0]["status"], "met")
        self.assertEqual(observed["threshold_results"], {})
        self.assertEqual(observed["status"], "unknown")
        self.assertEqual(self.data("group", "G").get("evaluation_thresholds"), None)


if __name__ == "__main__":
    unittest.main()
