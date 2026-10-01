"""Normal outcomes that final review could not establish from smaller tests."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from test_learning import Instance
from t2ag_next import service
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError


class PublicInstance(Instance):
    def call(self, action, payload, student=None):
        receipt = service.execute(self.journal.path, self.request(action, payload, student))
        self.state = self.journal.read_state()
        return receipt["effects"]


def png(pixel):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0" + pixel)) + chunk(b"IEND", b""))


class ObservableJourneys(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "instance"
        self.store = Journal(self.path)
        self.w = PublicInstance(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        run = subprocess.run([sys.executable, "-B", "-m", "t2ag_next", "--instance", str(self.path), *args],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_multiple_source_questions_and_images_keep_order_owner_and_bytes(self):
        w = self.w
        aid = w.exercise()
        w.call("problem.add", {"activity_id": aid, "problem_id": "q2", "text": "Problem 2: explain.",
            "origin": "source", "page_id": "page-2", "source_excerpt": "Problem 2: explain.", "locator": "same source, second page"})
        raw = "A second synthetic verified source."
        from t2ag_next.learning import digest
        w.call("source.register", {"source_id": "book-v2", "course_id": "C", "title": "Second source", "format": "pdf",
            "source_version": "1", "content": raw, "content_sha256": digest(raw), "page_count": 1})
        w.call("page.register", {"page_id": "other-page", "source_id": "book-v2", "pdf_page_index": 1,
            "printed_page_label": "1", "verified_text": "Problem 3: compare.", "layout_critical": False,
            "verification": {"status": "verified", "reference": "synthetic-source-check", "source_document_sha256": digest(raw)}})
        w.call("problem.add", {"activity_id": aid, "problem_id": "q3", "text": "Problem 3: compare.",
            "origin": "source", "page_id": "other-page", "source_excerpt": "Problem 3: compare.", "locator": "second verified book"})
        w.call("exercise.reorder", {"activity_id": aid, "teaching_sequence": ["q3", "q1", "q2"], "reason": "Compare first, then explain."})
        w.call("criterion.create", {"criterion_id": "all-three", "target_kind": "exercise", "target_id": aid,
            "rubric": "State each question's condition.", "problem_ids": ["q1", "q2", "q3"],
            "max_scores": {"q1": 10, "q2": 10, "q3": 10}, "pass_score": 18})
        images = [png(bytes(pixel)) for pixel in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
        refs = [self.store.put_blob(data) for data in images]
        answers = [{"problem_id": "q2", "text": "Second answer", "blob_refs": refs[:2]},
                   {"problem_id": "q1", "text": "First answer", "blob_refs": refs[2:]},
                   {"problem_id": "q3", "text": "Comparison"}]
        w.call("attempt.submit", {"activity_id": aid, "attempt_id": "multi-image", "answers": answers}, "Here are all three answers and their original images.")
        w.call("registry.alias", {"id": "U0001", "kind": "exercise", "target_id": aid})
        restored = Journal(self.path).read_state()
        self.assertEqual(restored["objects"]["attempt/multi-image"]["data"]["answers"], answers)
        self.assertEqual([self.store.read_blob(ref["sha256"]) for ref in refs], images)
        exercise = restored["objects"]["exercise/" + aid]["data"]
        self.assertEqual(exercise["source_order"], ["q1", "q2", "q3"])
        self.assertEqual(exercise["teaching_sequence"], ["q3", "q1", "q2"])
        self.assertEqual(service.resolve(restored, "exercise", "U0001")[0], aid)
        self.assertEqual(exercise["problems"]["q3"]["page_id"], "other-page")

    def test_preferences_skin_and_binding_reach_recovery_without_awarding_progress(self):
        w = self.w
        aid = w.exercise()
        w.call("student.update", {"id": "current", "declarations": {"presentation_preferences": {"show_optional_tree": False, "style": "concise"},
            "collaboration_preferences": {"max_agents": 1}, "domain_tiers": {"mathematics": "registered"},
            "future_preference": {"original_text": "Keep this unknown preference."}}}, "Use concise presentation and one teacher.")
        w.call("skin.register", {"id": "quiet", "title": "Quiet", "art": ".", "welcome": "Welcome back."})
        w.call("skin.select", {"id": "quiet"}, "Use the quiet skin.")
        w.call("activity.save", {"id": aid, "note_id": "note", "body": "Completed today's practice routine."})
        before = {k: deepcopy(e) for k, e in w.state["objects"].items() if e["kind"] in {"course", "activity", "exercise", "cursor", "checkpoint", "completion", "group"}}
        w.call("binding.create", {"id": "R1", "course_ids": ["C"], "intent": "Keep a practice routine", "ritual_anchor": "After breakfast"}, "Keep this routine.")
        w.call("binding.create", {"id": "R2", "course_ids": ["C"], "intent": "Weekly review", "ritual_anchor": "Sunday"}, "Keep this second routine too.")
        w.call("binding.record", {"id": "R1", "observation": "Today's routine produced the saved practice note.",
            "evidence_refs": [{"kind": "study_note", "id": "note"}]})
        context = self.cli("context", "--entry", "entry.teach", "--lane", "teach", "--scope", "C", "--level", "L1")
        self.assertEqual(context["preferences"]["presentation_preferences"]["style"], "concise")
        self.assertEqual(context["profile"]["future_preference"]["original_text"], "Keep this unknown preference.")
        self.assertEqual(context["skin_display"]["welcome"], "Welcome back.")
        self.assertEqual(context["bindings"][0]["ritual_anchor"], "After breakfast")
        self.assertFalse(context["bindings"][0]["latest_observation"]["mastery_or_budget_credit"])
        self.assertIn("waiting_for", context)
        self.assertEqual(w.data("student", "current")["exercise_hint_gate"], "enabled")
        w.call("binding.retire", {"id": "R1"}, "Stop this routine.")
        after = {k: e for k, e in w.state["objects"].items() if k in before}
        self.assertEqual(after, before)
        self.assertEqual(w.data("binding", "R1")["observations"][0]["evidence_refs"][0]["id"], "note")
        self.assertEqual([b["id"] for b in service.context(self.path, entry="entry.teach", session_lane="teach", scope="C")["bindings"]], ["R2"])

    def test_handoff_new_process_resume_completion_and_stale_source(self):
        w = self.w
        w.course("goal")
        course_version = w.state["objects"]["course/C"]["version"]
        w.call("handoff.create", {"id": "H1", "lane": "maintain", "scope": "C", "body": "Record the reviewed display preference.",
            "source_versions": {"course/C": course_version}, "completion_condition": "Student preference is durably recorded."})
        context = self.cli("context", "--entry", "entry.maintain", "--lane", "maintain", "--scope", "C")
        self.assertFalse(context["handoffs"][0]["source_stale"])
        w.call("student.update", {"id": "current", "declarations": {"presentation_preferences": {"style": "concise"}}}, "Use concise display.")
        w.call("handoff.resolve", {"id": "H1", "condition_evidence": {"kind": "student", "id": "current", "version": w.state["objects"]["student/current"]["version"]}})
        self.assertEqual(self.cli("context", "--entry", "entry.maintain", "--lane", "maintain", "--scope", "C")["handoffs"], [])
        w.call("handoff.create", {"id": "H2", "lane": "maintain", "scope": "C", "body": "Course is still planned; activate when chosen.",
            "source_versions": {"course/C": course_version}, "completion_condition": "Course activation recorded."})
        w.call("course.activate", {"id": "C"}, "Activate the course now.")
        stale = self.cli("context", "--entry", "entry.maintain", "--lane", "maintain", "--scope", "C")["handoffs"][0]
        self.assertTrue(stale["source_stale"])
        self.assertFalse(any(e["kind"] == "ticket" for e in w.state["objects"].values()))

    def test_failed_group_switch_can_restore_the_previous_capacity_combination(self):
        from test_groups_time_plan import GroupTimeAndClosingJourney
        helper = GroupTimeAndClosingJourney()
        helper.setUp()
        try:
            helper.configure_time(); helper.configure_close(); helper.fulfill()
            helper.act("group.activate", {"id": "G", "proposal_sha256": helper.data("group", "G")["proposal_sha256"]})
            helper.act("course.create", {"id": "NEW", "title": "A planned future course", "course_type": "mastery", "learning_mode": "goal"})
            previous = deepcopy(helper.data("group", "G"))
            proposal = {name: deepcopy(previous[name]) for name in ("members", "capacity", "calendar", "thresholds", "goal")}
            helper.act("group.propose", {**proposal, "id": "G-next", "members": ["NEW"]})
            helper.act("group.assess", {"id": "closing", "group_id": "G", "as_of": "2026-01-18T12:00:00Z"})
            choice = "Close this group and try G-next; if it cannot activate, retain my prior course combination."
            helper.act("group.close", {"id": "G", "closure_plan_sha256": previous["closure_plan_sha256"],
                "assessment_id": "closing", "evidence": ["Complete bound assessment"], "next_group_choice": {"kind": "group", "id": "G-next"}}, text=choice)
            before = helper.store.read_state()
            with self.assertRaises(DomainError) as failure:
                helper.act("group.activate", {"id": "G-next", "proposal_sha256": helper.data("group", "G-next")["proposal_sha256"]}, text=choice)
            self.assertEqual(failure.exception.code, "GROUP_MEMBER_STATE")
            self.assertEqual(helper.store.read_state(), before)
            helper.act("group.propose", {**proposal, "id": "G-restored"}, text=choice)
            helper.act("group.time_plan.configure", {"group_id": "G-restored", "basis": "student_decision", "reason": "Use the already chosen fallback combination.", "time_plan": previous["time_plan"]}, text=choice)
            helper.act("group.activate", {"id": "G-restored", "proposal_sha256": helper.data("group", "G-restored")["proposal_sha256"]}, text=choice)
            restored = helper.data("group", "G-restored")
            for name in ("members", "capacity", "calendar", "time_plan"):
                self.assertEqual(restored[name], previous[name])
            self.assertEqual(restored["status"], "active")
            self.assertEqual(helper.data("group", "G")["status"], "closed")
            for cid in ("ALG", "CODE", "NEW"):
                self.assertEqual(helper.store.read_state()["objects"]["course/" + cid], before["objects"]["course/" + cid])
        finally:
            helper.tearDown()


if __name__ == "__main__":
    unittest.main()
