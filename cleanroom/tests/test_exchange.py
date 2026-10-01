import copy
import unittest

from t2ag_next import exchange, cloud
from t2ag_next.model import DomainError, put
from t2ag_next.support import digest


class ExchangeJourneys(unittest.TestCase):
    def setUp(self):
        self.state = {"revision": 0, "objects": {}}
        self.add("course", "C", {"title": "Course", "status": "ongoing", "current_activity_id": "C/L"})
        self.add("activity", "C/L", {"course_id": "C", "status": "ongoing"})
        self.add("cursor", "C/L", {"position": "block1", "waiting_for": "comprehension"})
        self.n = 0
        self.act("bridge.configure", {"instance_id": "local", "instance_kind": "personal_instance", "trusted_sources": ["reader", "cloud"]})

    def add(self, kind, identity, data):
        self.state["objects"][f"{kind}/{identity}"] = {"kind": kind, "id": identity, "version": self.state["revision"], "data": data}

    def act(self, action, payload):
        self.n += 1
        request = {"request_id": str(self.n), "action": action, "payload": payload, "actor": {"role": "student", "source": "synthetic-choice", "text": "Accept this explicitly bound operation."},
                   "expected": {k: v["version"] for k, v in self.state["objects"].items()}}
        effects = (cloud.plan if action in cloud.ACTIONS else exchange.plan)(copy.deepcopy(self.state), request)
        self.state["revision"] += 1
        for e in effects: self.add(e["kind"], e["id"], e["data"])

    def enabled(self): self.act("bridge.pause", {"paused": False})
    def data(self, kind, identity): return self.state["objects"][f"{kind}/{identity}"]["data"]

    def candidate(self, identity="con1", target="local", base=None):
        return exchange.envelope("reading_contribution", identity, "reader", target, "C",
                                 self.state["revision"] if base is None else base, {"note": "A reading candidate, not a learning judgment."})

    def test_pause_prevents_import_and_context_projection(self):
        with self.assertRaises(DomainError): self.act("bridge.import", {"envelope": self.candidate()})
        with self.assertRaises(DomainError): exchange.context_export(self.state, "ctx", "C")
        self.assertNotIn("contribution/con1", self.state["objects"])

    def test_identity_and_hash_conflict_make_no_partial_writes(self):
        self.enabled()
        before = copy.deepcopy(self.state)
        with self.assertRaises(DomainError): self.act("bridge.import", {"envelope": self.candidate(target="other-instance")})
        e = self.candidate(); e["body"]["note"] = "changed after hash"
        with self.assertRaises(DomainError): self.act("bridge.import", {"envelope": e})
        self.assertEqual(before, self.state)

    def test_candidate_is_not_consumption_and_duplicate_id_is_not_reused(self):
        self.enabled(); original_cursor = copy.deepcopy(self.data("cursor", "C/L")); e = self.candidate()
        self.act("bridge.import", {"envelope": e})
        self.assertEqual(self.data("contribution", "con1")["status"], "candidate")
        self.assertEqual(original_cursor, self.data("cursor", "C/L"))
        with self.assertRaises(DomainError): self.act("bridge.import", {"envelope": e})

    def test_stale_cloud_is_candidate_conflict_never_progress_overwrite(self):
        self.enabled()
        self.act("cloud.compatibility.configure", {"enabled": True})
        old = copy.deepcopy(self.data("cursor", "C/L"))
        e = exchange.envelope("cloud_pending", "remote1", "cloud", "local", "C", 0,
                              {"session_id": "remote-session", "proposed_cursor": {"position": "future"}, "local_cursor_sha256": digest(old)})
        self.act("bridge.import", {"envelope": e})
        self.assertEqual(self.data("contribution", "remote1")["status"], "conflict")
        self.assertEqual(self.data("cursor", "C/L"), old)

    def test_receipt_requires_actual_same_course_consumption_then_transport_ack(self):
        self.enabled(); e = self.candidate(); self.act("bridge.import", {"envelope": e})
        self.state["revision"] += 1
        self.add("thought", "T", {"course_id": "C", "body": "Actual student's reading response", "evidence": ["con1"], "contribution_refs": [{"kind": "contribution", "id": "con1", "sha256": e["content_sha256"]}]})
        self.act("bridge.receipt.prepare", {"id": "con1", "target_kind": "thought", "target_id": "T", "target_sha256": digest(self.data("thought", "T")), "content_sha256": e["content_sha256"], "consumption_ref": "actual-message"})
        receipt = self.data("receipt", "con1")
        self.assertEqual(receipt["status"], "prepared")
        self.act("bridge.receipt.ack", {"id": "con1", "receipt_sha256": digest(receipt), "transport_evidence": "external-copy-ack"})
        self.assertEqual(self.data("receipt", "con1")["status"], "acknowledged")
        with self.assertRaises(DomainError): self.act("bridge.receipt.ack", {"id": "con1", "receipt_sha256": digest(receipt), "transport_evidence": "replay"})

    def test_receipt_cannot_claim_unrelated_course(self):
        self.enabled(); e = self.candidate(); self.act("bridge.import", {"envelope": e})
        self.add("thought", "T", {"course_id": "OTHER", "body": "different course"})
        with self.assertRaises(DomainError):
            self.act("bridge.receipt.prepare", {"id": "con1", "target_kind": "thought", "target_id": "T", "target_sha256": digest(self.data("thought", "T")), "content_sha256": e["content_sha256"], "consumption_ref": "actual-message"})


if __name__ == "__main__": unittest.main()
