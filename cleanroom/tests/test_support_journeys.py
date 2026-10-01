"""Ordinary user choices and compact recovery through real public transactions."""
from pathlib import Path
import tempfile
import unittest

from t2ag_next import service, support
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, get


class SupportPublicJourneys(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "instance"
        self.store = Journal(self.path)
        self.store.initialize({"language": "en"})
        self.sequence = 0

    def act(self, action, payload, text=None):
        self.sequence += 1
        state = self.store.read_state()
        return service.execute(self.path, {
            "request_id": f"journey-{self.sequence}", "action": action, "payload": payload,
            "actor": {"role": "student" if text else "teacher", "source": "synthetic-user-journey",
                      "text": text or "Record the observed result."},
            "expected": {k: v["version"] for k, v in state["objects"].items()},
        })

    def course(self, teacher_id=None):
        self.act("course.create", {"id": "C", "title": "Algebra", "course_type": "mastery",
            "learning_mode": "goal", "teacher_id": teacher_id}, "Please create this algebra course.")

    def pending_close(self):
        self.act("course.activate", {"id": "C"}, "Let's start this course.")
        self.act("activity.create", {"id": "C/L", "course_id": "C", "activity_type": "lesson", "title": "Domain"})
        self.act("activity.start", {"id": "C/L"}, "Let's begin the lesson.")
        body = "We checked the denominator restriction. The remaining examples are unfinished."
        self.act("activity.close.propose", {"id": "C/L", "body": body,
            "outcome": "closed_incomplete", "presentation_ref": "displayed-review",
            "reconciliation": {"remaining": ["examples"]}})
        return get(self.store.read_state(), "activity", "C/L")["pending_close"]

    def test_refusal_keeps_plan_and_natural_acceptance_activates_once(self):
        self.course()
        before = self.store.read_state()
        with self.assertRaises(DomainError) as error:
            self.act("course.activate", {"id": "C"}, "Do not activate this course.")
        self.assertEqual(error.exception.code, "DECISION_CONTRADICTED")
        self.assertEqual(self.store.read_state(), before)
        statement = "This arrangement works for me; let's start."
        receipt = self.act("course.activate", {"id": "C"}, statement)
        decision = get(self.store.read_state(), "course", "C")["last_transition_decision"]
        self.assertEqual(decision["text"], statement)
        self.assertFalse(decision["decision_basis"]["host_identity_authenticated"])
        self.assertEqual(self.store.lookup(receipt["request_id"])["revision"], receipt["revision"])

    def test_natural_close_retains_the_displayed_incomplete_outcome(self):
        self.course()
        proposal = self.pending_close()
        activity = get(self.store.read_state(), "activity", "C/L")
        statement = "Please close this unfinished activity now."
        receipt = self.act("activity.close.confirm", {"id": "C/L", "outcome": "closed_incomplete",
            "body_sha256": activity["pending_sha256"]}, statement)
        record = get(self.store.read_state(), "close", receipt["request_id"])
        self.assertEqual(record["proposal"], proposal)
        self.assertEqual(record["decision"]["text"], statement)
        self.assertEqual(get(self.store.read_state(), "course", "C")["status"], "ongoing")

    def test_compact_recovery_keeps_full_pending_body_and_addressable_teacher(self):
        template = "Explain patiently with concrete examples.\n" * 200
        self.act("teacher.register", {"id": "T", "name": "Algebra tutor", "template": template, "overlay": {}})
        self.course("T")
        proposal = self.pending_close()
        critical = service.context(self.path, entry="entry.teach", session_lane="teach", scope="C")
        expanded = service.context(self.path, entry="entry.teach", session_lane="teach", scope="C", level="L1")
        self.assertEqual(critical["pending_close"], proposal)
        self.assertEqual(critical["teacher"]["inspect"], ["teacher", "T"])
        self.assertEqual(expanded["teacher"]["template"], template)
        self.assertEqual(critical["versions"]["teacher/T"], expanded["versions"]["teacher/T"])
        self.assertLess(critical["size"]["characters_before_size_field"], expanded["size"]["characters_before_size_field"])

    def test_manual_save_restores_notes_without_advancing_a_pending_decision(self):
        self.course()
        proposal = self.pending_close()
        before = get(self.store.read_state(), "activity", "C/L")
        note = "The student wants to revisit why the denominator cannot be zero."
        pending = "Shall we work through a concrete example next time?"
        self.act("activity.save", {"id": "C/L", "note_id": "N1", "body": note, "pending_text": pending}, "Save where we are; leave the lesson open.")
        recovered = service.context(self.path, entry="entry.teach", session_lane="teach", scope="C")
        self.assertEqual(recovered["saved_note"]["body"], note)
        self.assertEqual(recovered["saved_note"]["pending_text"], pending)
        self.assertFalse(recovered["saved_note"]["advances_learning"])
        self.assertEqual(recovered["pending_close"], proposal)
        self.assertEqual(get(self.store.read_state(), "activity", "C/L"), before)

    def test_keystone_draft_becomes_student_path_only_after_step_confirmation(self):
        self.course()
        self.pending_close()
        chain = ["A zero denominator makes the expression undefined.", "Therefore exclude x=2."]
        self.act("keystone.record", {"id": "K", "course_id": "C", "body": "Proposed reasoning path.",
            "claim": "The domain excludes 2.", "reasons": chain, "dependencies": [],
            "review_status": "unreviewed", "evidence": ["synthetic-discussion"]})
        self.assertEqual(get(self.store.read_state(), "keystone", "K")["confirmation_status"], "draft")
        consumption = {"id": "UseK", "method_kind": "keystone", "method_id": "K", "activity_id": "C/L",
                       "effect": "Recall the learner's confirmed reasoning.", "evidence": ["synthetic-use"]}
        with self.assertRaises(DomainError) as error:
            self.act("method.consume", consumption)
        self.assertEqual(error.exception.code, "KEYSTONE_NOT_CONFIRMED")
        steps = [{"step": 1, "statement": "Yes, that was my first reason."},
                 {"step": 2, "statement": "Then I excluded 2, as written."}]
        self.act("keystone.confirm", {"id": "K", "chain_sha256": support.digest(chain), "steps": steps},
                 "Those two steps describe how I actually reasoned.")
        self.act("method.consume", consumption)
        self.assertEqual(get(self.store.read_state(), "keystone", "K")["step_confirmations"], steps)


if __name__ == "__main__":
    unittest.main()
