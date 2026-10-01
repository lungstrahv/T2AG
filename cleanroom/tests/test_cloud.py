import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from t2ag_next import cloud, service
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError
from t2ag_next.support import digest


def block(kind, **overrides):
    data = {key: "NONE" for key in cloud.REQUIRED[kind]}
    data.update(protocol_version=cloud.PROTOCOL, session_id="CLOUD-C-1", receipt_id="CPR-C-1", produced_at="2026-09-30T12:00:00-04:00", closed_at="2026-09-30T12:00:00-04:00",
        created_at="2026-09-30T12:00:00-04:00", base_state_id="B1", course="C", current_activity="lesson", current_activity_id="L", resume_path="C/L", duration_minutes="15", sync_status="pending", exact_stop="Synthetic page 2, before confirmation", next_first_action="Check the actual pending answer.", confirmation_state="pending", privacy_scope="uploaded_project_only", receipt_kind="manual_save", status="proposed_for_local_review", directive_id="CD-1", handoff_id="CH-1")
    data.update(overrides)
    return kind + "\n" + "\n".join(f"- {key}: {data[key]}" for key in cloud.REQUIRED[kind]) + "\nEND_" + kind


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"instance"
        self.store = Journal(self.path); self.store.initialize({"language": "en"})
        self.n = 0
        self.act("course.create", {"id": "C", "title": "Synthetic cloud course", "course_type": "mastery", "learning_mode": "goal"})
        self.act("course.activate", {"id": "C"})
        self.act("activity.create", {"id": "C/L", "course_id": "C", "activity_type": "lesson", "title": "Synthetic lesson"})
        self.act("activity.start", {"id": "C/L"})
        self.act("bridge.configure", {"instance_id": self.store.validate()["instance_id"], "instance_kind": "personal_instance", "trusted_sources": ["mobile"]})
        self.act("bridge.pause", {"paused": False})
        self.act("cloud.compatibility.configure", {"enabled": True})
        self.act("cloud.baseline.create", {"id": "B1", "course_id": "C", "created_at": "2026-09-30T10:00:00-04:00"})

    def tearDown(self): self.temp.cleanup()

    def request(self, action, payload):
        self.n += 1
        state = self.store.read_state()
        return {"request_id": f"cloud-test-{self.n}", "action": action, "payload": payload,
            "actor": {"role": "student", "text": "confirm cloud progress import" if action == "cloud.event.apply" else "Explicit synthetic decision.", "source": f"synthetic-{self.n}"},
            "expected": {k: v["version"] for k, v in state["objects"].items()}}

    def act(self, action, payload): return service.execute(self.path, self.request(action, payload))
    def data(self, kind, identity): return self.store.read_state()["objects"][kind+"/"+identity]["data"]

    def imported(self, kind=cloud.CLOSE, **values):
        raw = block(kind, **values)
        self.act("cloud.event.import", {"raw": raw, "source_identity": "mobile"})
        return "CLOUD-C-1" if kind == cloud.CLOSE else "CPR-C-1"

    def apply_request(self, identity, **extra):
        event = self.data("cloud_event", identity)
        return self.request("cloud.event.apply", {"id": identity, "event_sha256": event["block"]["sha256"],
            "local_basis_sha256": digest(cloud.route_basis(self.store.read_state(), "C")), "mode": "progress", **extra})

    def test_progress_sync_is_checked_and_replayed_without_double_time(self):
        identity = self.imported(completed="A cloud claim retained for local review", mastery_evidence="Actual reported answer, not a local mastery judgment")
        request = self.apply_request(identity)
        result = cloud.sync_event(self.path, request)
        self.assertEqual(result["status"], "synced")
        self.assertTrue(result["receipt"]["doctor"]["ok"])
        self.assertEqual(self.data("cursor", "C/L")["waiting_for"], "authorization")
        self.assertEqual(self.data("timespan", "cloud/"+identity)["seconds"], 900)
        self.assertEqual(self.data("cloud_candidate", identity+"/completed")["status"], "unreviewed")
        again = cloud.sync_event(self.path, request)
        self.assertEqual(again["status"], "duplicate")
        spans = [x for x in self.store.read_state()["objects"].values() if x["kind"] == "timespan"]
        self.assertEqual(len(spans), 1)
        self.assertFalse(any(x["kind"] == "completion" for x in self.store.read_state()["objects"].values()))

    def test_pending_event_is_not_synced_when_real_checks_fail(self):
        identity = self.imported()
        request = self.apply_request(identity)
        # Simulate a failed runtime result at the boundary; application is durable.
        with patch.object(service, "doctor", return_value={"ok": False, "counts": {"FAIL": 1}}):
            result = cloud.sync_event(self.path, request)
        self.assertEqual(result["status"], "applied_needs_validation")
        self.assertEqual(self.data("cloud_event", identity)["status"], "applied")
        self.assertEqual(cloud.sync_event(self.path, request)["status"], "synced")
        self.assertEqual(service.projection(self.store.read_state())["time_statistics"]["C/L"]["estimated_seconds"], 900)

    def test_late_baseline_requires_explicit_reconciliation(self):
        self.act("course.pause", {"id": "C", "happened_at": "2026-09-30T10:30:00-04:00"})
        self.act("course.resume", {"id": "C", "happened_at": "2026-09-30T11:00:00-04:00"})
        identity = self.imported()
        self.assertEqual(self.data("cloud_event", identity)["status"], "conflict")
        with self.assertRaises(DomainError): service.execute(self.path, self.apply_request(identity))
        result = cloud.sync_event(self.path, self.apply_request(identity, reconciliation="The student explicitly selected the reported stop after comparing both states."))
        self.assertEqual(result["status"], "synced")

    def test_manual_save_retains_stop_without_new_time_or_completion(self):
        identity = self.imported(cloud.PROGRESS, confirmation_state="confirmed", receipt_kind="manual_save")
        cloud.sync_event(self.path, self.apply_request(identity))
        state = self.store.read_state()
        self.assertFalse(any(x["kind"] in ("completion", "timespan") for x in state["objects"].values()))
        self.assertEqual(self.data("activity", "C/L")["status"], "ongoing")

    def test_reimport_preserves_identity_and_changed_body_is_rejected(self):
        self.imported()
        self.imported()
        with self.assertRaises(DomainError): self.imported(duration_minutes="20")
        self.assertEqual(len([x for x in self.store.read_state()["objects"].values() if x["kind"] == "cloud_event"]), 1)

    def test_pause_and_active_local_session_prevent_overwrite(self):
        identity = self.imported()
        self.act("session.start", {"session_id": "local", "activity_id": "C/L"})
        with self.assertRaises(DomainError): service.execute(self.path, self.apply_request(identity, reconciliation="Keep safety check."))
        self.act("bridge.pause", {"paused": True})
        with self.assertRaises(DomainError): self.imported()
        with self.assertRaises(DomainError): self.act("cloud.baseline.create", {"id": "B2", "course_id": "C", "created_at": "2026-09-30T13:00:00-04:00"})

    def test_cloud_cannot_assert_synced_or_replace_component_proposal_status(self):
        for raw in (block(cloud.CLOSE, sync_status="synced"), block(cloud.HANDOFF, status="accepted"), block(cloud.CLOSE)+"\n"+block(cloud.PROGRESS), block(cloud.CLOSE).replace("- sync_status: pending", "- sync_status: pending\n- sync_status: pending")):
            with self.assertRaises(DomainError): cloud.parse_block(raw)

    def test_disabling_compatibility_preserves_normal_same_instance_operations(self):
        self.act("cloud.compatibility.configure", {"enabled": False})
        with self.assertRaises(DomainError): self.imported()
        self.act("time.record", {"id": "normal-local", "activity_id": "C/L", "quality": "exact", "seconds": 30, "started_at": "2026-09-30T12:00:00-04:00"})
        self.assertEqual(self.data("timespan", "normal-local")["seconds"], 30)

    def test_component_decision_is_separate_and_preserves_original_status(self):
        raw = block(cloud.HANDOFF, proposed_local_changes="Propose a wording correction.")
        self.act("cloud.handoff.import", {"raw": raw, "source_identity": "mobile"})
        with self.assertRaises(DomainError): self.act("cloud.event.import", {"raw": raw, "source_identity": "mobile"})
        self.act("cloud.handoff.decide", {"id": "CH-1", "handoff_sha256": digest(raw), "status": "partially_accepted", "accepted": ["wording"], "rejected": ["unrelated suggestion"], "rationale": "Explicit limited scope."})
        result = self.data("cloud_handoff", "CH-1")
        self.assertEqual(result["block"]["fields"]["status"], "proposed_for_local_review")
        self.assertEqual(result["local_decision"]["implementation_status"], "not_applied_by_this_decision")


if __name__ == "__main__": unittest.main()
