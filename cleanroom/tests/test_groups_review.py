"""Non-author group regressions by parity_inventory; no production edits.

Public requests create synthetic instances. These tests are review evidence,
not a claim of filesystem or conversation isolation from the author.
"""
import tempfile
from pathlib import Path
import unittest

from t2ag_next import groups, service
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError


class IndependentGroupReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "instance"
        self.store = Journal(self.path)
        self.store.initialize({"language": "en"})
        self.serial = 0
        for course in ("C", "D"):
            self.act("course.create", {"id": course, "title": "Synthetic " + course, "course_type": "mastery", "learning_mode": "goal"})
            self.act("course.activate", {"id": course})
            self.act("activity.create", {"id": course + "/L", "course_id": course, "activity_type": "lesson", "title": "Synthetic activity"})
            self.act("activity.start", {"id": course + "/L"})
        self.act("group.propose", {"id": "G", "members": ["C", "D"], "capacity": 2, "calendar": {"frequency": "declared test schedule", "stagnation_days": 10}, "thresholds": {"close_condition": "actual evaluation"}, "goal": "Independent clock review"})
        self.act("group.schedule.configure", {"id": "G", "reason": "Explicit test parameters", "calendar": {"cycle_anchor_learning_day": "2026-01-01", "cycle_length_learning_days": 2, "keystone_dwell_budget_cycles": 2, "cycle_count": None, "exam_bank_build_cycles": [], "exam_quiz_cycles": [], "exam_final_cycle": None}})
        self.act("group.keystones.configure", {"id": "G", "container_mode": "progress", "keystone_ids": ["K1", "K2"], "keystone_courses": {"K1": "C", "K2": "C"}, "reason": "Two actual planned milestones"})
        self.act("group.thresholds.configure", {"group_id": "G", "reason": "Separate budget review from completion grades", "thresholds": {"count_unit": "learning_days", "minimum_per_cycle": {"C": 0, "D": 0}, "minimum_frequency_attainment": 1, "time_budget_seconds": 240, "maximum_time_deviation": 10, "maximum_start_failure_days": 0, "minimum_major_adjustments": 0}})

    def tearDown(self):
        self.temp.cleanup()

    def act(self, action, payload):
        self.serial += 1
        state = self.store.read_state()
        return service.execute(self.path, {"request_id": "independent-group-" + str(self.serial), "action": action, "payload": payload,
            "actor": {"role": "student", "source": "independent synthetic event " + str(self.serial), "text": "Confirm this exact synthetic request."},
            "expected": {k: v["version"] for k, v in state["objects"].items()}})

    def data(self, kind, identity):
        return self.store.read_state()["objects"][kind + "/" + identity]["data"]

    def activate(self):
        self.act("group.activate", {"id": "G", "proposal_sha256": self.data("group", "G")["proposal_sha256"]})

    def span(self, day, course="C"):
        self.act("time.record", {"id": course + "-day-" + str(day), "activity_id": course + "/L", "quality": "exact", "seconds": 60, "started_at": f"2026-01-{day:02d}T12:00:00Z"})

    def assess(self, day=4, ident="A"):
        self.act("group.assess", {"id": ident, "group_id": "G", "as_of": f"2026-01-{day:02d}T23:00:00Z"})
        return self.data("group_assessment", ident)

    def completion(self, checkpoint="CP1", position="K1"):
        for status in ("queued", "arrived", "pending", "confirmed"):
            self.act("checkpoint.record", {"id": checkpoint, "activity_id": "C/L", "status": status, "position": position, "evidence": ["Actual synthetic learner response."]})
        self.act("completion.record", {"id": checkpoint + "-done", "course_id": "C", "judgment_kind": "comprehension", "evidence_ids": [checkpoint]})
        return checkpoint + "-done"

    def test_gr_r1_unset_budget_produces_unknown_instead_of_guessed_triage(self):
        self.act("group.schedule.configure", {"id": "G", "reason": "Budget remains undecided", "calendar": {"keystone_dwell_budget_cycles": "TBD"}})
        self.activate()
        for day in range(1, 5): self.span(day)
        report = self.assess()
        self.assertEqual([], report["stagnation"])
        self.assertEqual("unknown", report["stagnation_scope"]["status"])

    def test_gr_r1_successor_clock_does_not_inherit_predecessor_learning_dates(self):
        self.activate()
        for day in range(1, 5): self.span(day)
        completion = self.completion()
        self.act("group.keystone.complete", {"id": "G", "keystone_id": "K1", "completion_id": completion})
        unresolved = self.assess(4, "before-entry")
        self.assertEqual([], unresolved["stagnation"])
        self.assertEqual("unknown", unresolved["stagnation_scope"]["status"])
        self.act("group.keystone.enter", {"group_id": "G", "keystone_id": "K2", "activity_id": "C/L", "happened_at": "2026-01-04T12:00:00Z", "evidence": ["Actual start of the next named milestone."]})
        self.assertEqual([], self.assess(4, "one-current-date")["stagnation"])
        for day in range(5, 8): self.span(day)
        self.assertEqual("K2", self.assess(7, "full-own-budget")["stagnation"][0]["keystone_id"])

    def test_gr_r2_progress_or_course_pause_invalidates_saved_triage(self):
        self.activate()
        for day in range(1, 5): self.span(day)
        self.assess()
        self.act("course.pause", {"id": "C", "happened_at": "2026-01-04T23:01:00Z"})
        with self.assertRaises(DomainError) as result:
            self.act("group.triage", {"id": "stale-pause", "group_id": "G", "assessment_id": "A", "course_id": "C", "choice": "stuck"})
        self.assertEqual("STALE_TRIAGE", result.exception.code)
        self.act("course.resume", {"id": "C", "happened_at": "2026-01-05T12:00:00Z"})
        self.assess(5, "before-progress")
        completion = self.completion()
        self.act("group.observation.record", {"id": "P1", "group_id": "G", "course_id": "C", "keystone_id": "K1", "kind": "progress", "happened_at": "2026-01-05T13:00:00Z", "evidence": ["Actual progress."], "completion_id": completion})
        with self.assertRaises(DomainError) as result:
            self.act("group.triage", {"id": "stale-progress", "group_id": "G", "assessment_id": "before-progress", "course_id": "C", "choice": "stuck"})
        self.assertEqual("STALE_TRIAGE", result.exception.code)

    def test_gr_r2_same_evidence_window_cannot_be_triaged_twice(self):
        self.activate()
        for day in range(1, 5): self.span(day)
        self.assess()
        payload = {"id": "once", "group_id": "G", "assessment_id": "A", "course_id": "C", "choice": "no_statement"}
        self.act("group.triage", payload)
        with self.assertRaises(DomainError) as result:
            self.act("group.triage", {**payload, "id": "twice"})
        self.assertEqual("TRIAGE_ALREADY_RECORDED", result.exception.code)

    def test_gr_r1_pause_interval_is_excluded_after_resume_or_reported_unknown(self):
        self.activate()
        self.act("group.keystone.enter", {"group_id": "G", "keystone_id": "K1", "activity_id": "C/L", "happened_at": "2026-01-01T12:00:00Z", "evidence": ["Actual start of K1."]})
        self.span(1, "C")
        self.act("course.pause", {"id": "C", "happened_at": "2026-01-02T04:00:00Z", "resume_condition": "A declared time constraint clears."})
        for day in range(2, 5): self.span(day, "D")
        self.act("course.resume", {"id": "C", "happened_at": "2026-01-05T12:00:00Z"})
        report = self.assess(5, "after-resume")
        self.assertEqual([], report["stagnation"], "Days when C was paused cannot become C's four eligible dwell dates merely because member D studied.")

    def test_gr_r1_unknown_pause_timestamp_stays_unknown_after_resume(self):
        self.activate()
        self.span(1)
        self.act("course.pause", {"id": "C"})
        for day in range(2, 5): self.span(day, "D")
        self.act("course.resume", {"id": "C", "happened_at": "2026-01-05T12:00:00Z"})
        report = self.assess(5, "unknown-pause")
        self.assertIsNone(self.data("course", "C")["pause_history"][0]["learning_day"])
        self.assertEqual([], report["stagnation"])
        self.assertEqual("historical_pause_interval_not_established", report["stagnation_scope"]["reason"])
        self.assertTrue(all(row["status"] == "pause_interval_unknown" for row in report["frequency"] if row["course_id"] == "C"))

    def test_gr_r1_partial_pause_cycle_does_not_guess_frequency_minimum(self):
        self.activate()
        self.span(1)
        self.act("course.pause", {"id": "C", "happened_at": "2026-01-02T04:00:00Z"})
        self.span(2, "D")
        self.act("course.resume", {"id": "C", "happened_at": "2026-01-03T04:00:00Z"})
        for day in (3, 4): self.span(day, "D")
        report = self.assess(4, "partial-cycle")
        row = next(row for row in report["frequency"] if row["course_id"] == "C" and row["cycle"] == 1)
        self.assertEqual("partial_pause_cycle", row["status"])
        self.assertNotIn("minimum", row)
        self.assertEqual("unknown", report["status"])
        self.assertEqual([], report["stagnation"])

    def test_gr_r1_no_time_triage_creates_pause_history_for_the_same_clock(self):
        self.activate()
        for day in range(1, 5): self.span(day)
        self.assess()
        self.act("group.triage", {"id": "no-time", "group_id": "G", "assessment_id": "A", "course_id": "C", "choice": "no_time", "resume_condition": "Declared time constraint clears."})
        history = self.data("course", "C")["pause_history"]
        self.assertEqual("pause", history[0]["transition"])
        self.assertEqual("2026-01-04", history[0]["learning_day"])
        for day in range(5, 8): self.span(day, "D")
        self.act("course.resume", {"id": "C", "happened_at": "2026-01-08T04:00:00Z"})
        self.assertEqual([], self.assess(8, "triage-resumed")["stagnation"])


if __name__ == "__main__": unittest.main()
