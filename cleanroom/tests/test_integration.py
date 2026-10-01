from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from t2ag_next import service
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, parse_json
from test_learning import Instance


class IntegratedJourneys(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "instance"
        self.journal = Journal(self.path)
        self.i = Instance(self.journal)

    def tearDown(self): self.temp.cleanup()

    def test_textbook_ready_then_exact_feedback_resume_across_new_journal(self):
        aid, bids = self.i.lesson()
        before = service.context(self.path, entry="entry.teach", session_lane="teach", scope="C", session_id="s1")
        self.assertFalse(before["learning_ready"])
        self.i.ready()
        self.assertTrue(service.context(self.path, entry="entry.teach", session_lane="teach", scope="C", session_id="s1")["learning_ready"])
        self.i.ticket(bids[0]); self.i.present(bids[0]); self.i.answer(bids[0])
        resumed = service.context(self.path, entry="entry.teach", session_lane="teach", scope="C", session_id="s1")
        self.assertEqual(resumed["cursor"]["judgement"]["verdict"], "correct")
        self.assertEqual(resumed["waiting_for"], "feeling")
        self.assertEqual(resumed["current_activity"]["status"], "ongoing")
        self.assertEqual(resumed["current_block"]["id"], bids[0])
        self.assertEqual(resumed["current_criterion"]["id"], "criterion-1")
        self.assertIn("criterion/criterion-1", resumed["versions"])
        self.assertTrue(service.doctor(self.path, full=True)["ok"])

    def test_projection_is_rebuildable_without_learning_changes(self):
        self.i.lesson(); self.i.ready()
        state = self.journal.read_state()
        self.assertTrue(service.refresh(self.path)["changed"])
        self.assertTrue(service.refresh(self.path, True)["written"])
        self.assertFalse(service.refresh(self.path, True)["changed"])
        (self.path / "derived/state.json").write_text("corrupt", encoding="utf-8")
        self.assertTrue(service.refresh(self.path, True)["written"])
        self.assertEqual(self.journal.read_state(), state)

    def test_actual_dispatch_and_cli_failure_do_not_claim_saved(self):
        self.i.course("goal")
        request = self.i.request("course.activate", {"id": "C"}, "Activate the planned course.")
        receipt = service.execute(self.path, request)
        self.assertEqual(receipt["persistence"], "committed")
        self.assertTrue(service.execute(self.path, request)["replayed"])
        command = [sys.executable, "-m", "t2ag_next", "--instance", str(self.path), "context", "--entry", "entry.audit"]
        output = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(output.returncode, 0)
        self.assertIn("--lane", output.stderr)

    def test_stale_plan_and_unknown_changed_kind_are_rejected(self):
        self.i.course("goal")
        plan = service.check_plan(self.journal.read_state(), ["course"])
        self.i.call("course.activate", {"id": "C"}, "Activate.")
        with self.assertRaises(DomainError): service.doctor(self.path, plan=plan)
        with self.assertRaises(DomainError): service.doctor(self.path, changed_kinds=["coures"])
        self.assertIn("lifecycles", service.doctor(self.path, changed_kinds=["timespan"])["plan"]["checks"])

    def test_actual_negative_probe_is_scoped_durable_and_never_applies_candidate(self):
        self.i.course("goal")
        request = self.i.request("course.activate", {"id": "C"})
        before = self.journal.read_state()
        result = service.validate_negative(self.path, "no-teacher-activation", request, "STUDENT_DECISION_REQUIRED")
        after = self.journal.read_state()
        self.assertEqual(after["objects"]["course/C"], before["objects"]["course/C"])
        self.assertEqual(result["effects"][0]["kind"], "validation")
        self.assertTrue(service.validate_negative(self.path, "no-teacher-activation", request, "STUDENT_DECISION_REQUIRED")["replayed"])
        good = self.i.request("course.activate", {"id": "C"}, "Activate.")
        with self.assertRaises(DomainError) as error:
            service.validate_negative(self.path, "actually-accepted", good, "STUDENT_DECISION_REQUIRED")
        self.assertEqual(error.exception.code, "NEGATIVE_ACCEPTED")
        self.assertEqual(self.journal.read_state(), after)

    def test_external_json_never_selects_between_duplicate_or_nonfinite_facts(self):
        for text in ('{"actor":{"role":"student","role":"teacher"}}', '{"score":NaN}', '{"score":Infinity}'):
            with self.assertRaises(DomainError): parse_json(text)


if __name__ == "__main__": unittest.main()
