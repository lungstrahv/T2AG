from pathlib import Path
import tempfile
import unittest

from t2ag_next import groups, service
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError


class GroupEvidenceJourneys(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "instance"
        self.store = Journal(self.path)
        self.store.initialize({"language": "en"})
        self.serial = 0
        self.act("course.create", {"id": "C", "title": "Synthetic course", "course_type": "mastery", "learning_mode": "goal"})
        self.act("course.activate", {"id": "C"})
        self.act("activity.create", {"id": "C/L", "course_id": "C", "activity_type": "lesson", "title": "Synthetic activity"})
        self.act("activity.start", {"id": "C/L"})
        self.act("group.propose", {"id": "G", "members": ["C"], "capacity": 1, "calendar": {"frequency": "agreed explicit unit below", "stagnation_days": 14}, "thresholds": {"close_condition": "measured thresholds"}, "goal": "Synthetic group"})
        self.act("group.schedule.configure", {"id": "G", "reason": "Agreed synthetic two-day cycles", "calendar": {"cycle_anchor_learning_day": "2026-01-01", "cycle_length_learning_days": 2, "keystone_dwell_budget_cycles": 2, "cycle_count": 2, "exam_bank_build_cycles": [], "exam_quiz_cycles": [], "exam_final_cycle": None}})
        self.act("group.keystones.configure", {"id": "G", "container_mode": "progress", "keystone_ids": ["K1"], "keystone_courses": {"K1": "C"}, "reason": "Specific member milestone"})

    def tearDown(self): self.temp.cleanup()

    def act(self, action, payload):
        self.serial += 1
        state = self.store.read_state()
        return service.execute(self.path, {"request_id": "group-case-"+str(self.serial), "action": action, "payload": payload,
            "actor": {"role": "student", "text": "Confirm these exact synthetic conditions.", "source": "synthetic-turn-"+str(self.serial)},
            "expected": {k: v["version"] for k, v in state["objects"].items()}})

    def data(self, kind, identity): return self.store.read_state()["objects"][kind+"/"+identity]["data"]

    def active(self, minimum=1):
        self.act("group.thresholds.configure", {"group_id": "G", "reason": "Complete explicit criteria", "thresholds": {
            "count_unit": "learning_days", "minimum_per_cycle": {"C": minimum}, "minimum_frequency_attainment": 1,
            "time_budget_seconds": 240, "maximum_time_deviation": 0, "maximum_start_failure_days": 0, "minimum_major_adjustments": 0}})
        self.act("group.activate", {"id": "G", "proposal_sha256": self.data("group", "G")["proposal_sha256"]})
        for number in range(1, 5):
            self.act("time.record", {"id": "span-"+str(number), "activity_id": "C/L", "quality": "exact", "seconds": 60, "started_at": f"2026-01-0{number}T12:00:00Z"})

    def assess(self, identity="assessment"):
        self.act("group.assess", {"id": identity, "group_id": "G", "as_of": "2026-01-04T23:00:00Z"})
        return self.data("group_assessment", identity)

    def close(self, identity="assessment"):
        return self.act("group.close", {"id": "G", "proposal_sha256": self.data("group", "G")["proposal_sha256"], "assessment_id": identity, "evidence": ["Actual recorded threshold assessment"]})

    def test_all_thresholds_derive_from_real_records_and_close_preserves_course(self):
        self.active()
        report = self.assess()
        self.assertEqual(report["status"], "met")
        self.assertEqual(report["complete_cycles"], 2)
        self.assertEqual(report["threshold_results"]["time_budget_deviation"]["actual"], 0)
        self.assertEqual(report["stagnation"][0]["grade_effect"], "none")
        self.close()
        self.assertEqual(self.data("group", "G")["status"], "closed")
        self.assertEqual(self.data("course", "C")["status"], "ongoing")

    def test_changed_actual_time_invalidates_prior_group_assessment(self):
        self.active(); self.assess()
        self.act("time.record", {"id": "corrected", "activity_id": "C/L", "quality": "exact", "seconds": 180, "started_at": "2026-01-04T12:00:00Z", "corrects": "span-4"})
        with self.assertRaises(DomainError): self.close()
        self.assertEqual(self.assess("current")["status"], "not_met")

    def test_frequency_shortfall_is_not_blame_without_available_time_evidence(self):
        self.active(minimum=3)
        report = self.assess()
        self.assertEqual(report["status"], "unknown")
        self.assertTrue(all(row["status"] == "needs_capacity_triage" for row in report["frequency"]))
        for day in (1, 3):
            self.act("group.observation.record", {"id": "available-"+str(day), "group_id": "G", "course_id": "C", "kind": "available_but_not_done", "happened_at": f"2026-01-0{day}T12:00:00Z", "evidence": ["Actual attributed capacity observation"]})
        report = self.assess("attributed")
        self.assertEqual(report["status"], "not_met")
        self.assertTrue(report["frequency"][-1]["emergency_review"])
        self.assertEqual(report["stagnation"][0]["grade_effect"], "none")

    def test_stagnation_no_time_preserves_cursor_and_pauses_without_grade_penalty(self):
        self.active(); self.assess()
        before = self.store.read_state()["objects"].get("cursor/C/L")
        self.act("group.triage", {"id": "triage", "group_id": "G", "assessment_id": "assessment", "course_id": "C", "choice": "no_time", "resume_condition": "When the declared time constraint clears"})
        self.assertTrue(self.data("course", "C")["paused"])
        self.assertEqual(self.data("group_triage", "triage")["grade_effect"], "none")
        self.assertEqual(self.store.read_state()["objects"].get("cursor/C/L"), before)

    def test_unknown_span_and_unset_anchor_never_become_zero_time_or_pass(self):
        before = groups.assessment(self.store.read_state(), "G", "2026-01-04T12:00:00Z")
        self.assertEqual(before["status"], "unknown")
        self.active()
        self.act("time.record", {"id": "unknown", "activity_id": "C/L", "quality": "unknown"})
        self.assertEqual(self.assess()["status"], "unknown")
        with self.assertRaises(DomainError): self.close()
        with self.assertRaises(DomainError):
            self.act("group.schedule.configure", {"id": "G", "reason": "Move the deadline after outcomes", "calendar": {"cycle_anchor_learning_day": "2026-01-03"}})


if __name__ == "__main__": unittest.main()
