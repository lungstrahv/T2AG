"""Two real CLI processes sharing one instance, not actual phone/network tests."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from t2ag_next import service
from t2ag_next.journal import Journal


class SharedInstanceAccess(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.instance = Path(self.temp.name)/"instance"
        self.store = Journal(self.instance); self.store.initialize({"language": "en"})
        self.request_number = 0
        self.apply("course.create", {"id": "C", "title": "Shared instance", "course_type": "mastery", "learning_mode": "goal"})
        self.apply("course.activate", {"id": "C"})
        self.apply("activity.create", {"id": "C/L", "course_id": "C", "activity_type": "lesson", "title": "Shared lesson"})
        self.apply("activity.start", {"id": "C/L"})

    def tearDown(self): self.temp.cleanup()

    def request(self, action, payload):
        self.request_number += 1
        return {"request_id": f"shared-{self.request_number}", "action": action, "payload": payload,
            "actor": {"role": "student", "source": "synthetic-attributed-message", "text": "Explicit synthetic instruction."},
            "expected": {k: v["version"] for k, v in self.store.read_state()["objects"].items()}}

    def apply(self, action, payload): return service.execute(self.instance, self.request(action, payload))

    def cli(self, *args, request=None):
        process = subprocess.run([sys.executable, "-B", "-m", "t2ag_next", "--instance", str(self.instance), *args],
            cwd=str(Path(__file__).resolve().parents[1]), input=json.dumps(request) if request else None,
            encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return process.returncode, json.loads(process.stdout if process.returncode == 0 else process.stderr)

    def test_second_process_continues_exact_same_instance_without_cloud_state(self):
        request = self.request("time.record", {"id": "T", "activity_id": "C/L", "quality": "exact", "seconds": 90, "started_at": "2026-09-30T12:00:00-04:00"})
        code, committed = self.cli("act", "-", request=request)
        self.assertEqual(code, 0)
        code, context = self.cli("context", "--entry", "entry.teach", "--lane", "teach", "--scope", "C")
        self.assertEqual(code, 0)
        self.assertEqual(context["revision"], committed["revision"])
        self.assertEqual(context["current_activity"]["id"], "C/L")
        self.assertFalse(any(obj["kind"].startswith("cloud") for obj in self.store.read_state()["objects"].values()))

    def test_ignored_reply_then_other_process_lookup_and_retry_is_one_commit(self):
        request = self.request("time.record", {"id": "T", "activity_id": "C/L", "quality": "exact", "seconds": 90, "started_at": "2026-09-30T12:00:00-04:00"})
        # The process ran; its response is deliberately not used as client state.
        code, _ = self.cli("act", "-", request=request)
        self.assertEqual(code, 0)
        code, recovered = self.cli("lookup", request["request_id"])
        self.assertEqual(code, 0)
        revision = recovered["receipt"]["revision"]
        code, replay = self.cli("act", "-", request=request)
        self.assertEqual(code, 0)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["revision"], revision)
        self.assertEqual(self.store.read_state()["revision"], revision)
        self.assertEqual(service.projection(self.store.read_state())["time_statistics"]["C/L"]["exact_seconds"], 90)

    def test_old_client_decision_rejected_after_other_client_changed_object(self):
        old_request = self.request("course.pause", {"id": "C", "happened_at": "2026-09-30T12:00:00-04:00"})
        current_request = self.request("course.pause", {"id": "C", "happened_at": "2026-09-30T11:00:00-04:00"})
        code, _ = self.cli("act", "-", request=current_request)
        self.assertEqual(code, 0)
        before = self.store.read_state()["revision"]
        code, rejected = self.cli("act", "-", request=old_request)
        self.assertNotEqual(code, 0)
        self.assertEqual(rejected["code"], "STALE_VERSION")
        self.assertEqual(self.store.read_state()["revision"], before)


if __name__ == "__main__": unittest.main()
