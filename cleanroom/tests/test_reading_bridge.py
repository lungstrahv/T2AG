import copy
import unittest

from t2ag_next import reading_bridge as b
from t2ag_next.model import DomainError
from t2ag_next.support import digest


class ReadingWireTests(unittest.TestCase):
    def setUp(self):
        self.state = {"revision": 0, "objects": {"reading/AR-0001": {"kind": "reading", "id": "AR-0001", "version": 0, "data": {"status": "recording", "intent": "cross-book inquiry"}}}}
        self.counter = 0

    def act(self, action, payload):
        self.counter += 1
        request = {"request_id": str(self.counter), "action": action, "payload": payload,
                   "actor": {"role": "student", "source": "synthetic-decision", "text": "Use the exact displayed context."},
                   "expected": {k: v["version"] for k, v in self.state["objects"].items()}}
        effects = b.plan(copy.deepcopy(self.state), request)
        self.state["revision"] += 1
        for e in effects:
            self.state["objects"][f"{e['kind']}/{e['id']}"] = {"kind": e["kind"], "id": e["id"], "version": self.state["revision"], "data": e["data"]}
        return effects

    def document(self):
        doc = {"schema": "reading.t2ag_contribution.v1", "event_id": "event-example-0001", "generated_at": "2026-09-30T00:00:00Z", "producer": "reading_system",
               "target_activity_record_id": "AR-0001", "book_id": "BOOK", "source_reading_uri": "reading://note/BOOK/1", "source_revision": "a" * 64,
               "knowledge_node_id": None, "question": "What evidence supports this?", "maturity": "candidate", "supports": ["one observation"], "limits": ["one sample"],
               "evidence_locator": {"source_uri": "reading://note/BOOK/1", "source_path": "notes/BOOK/1.md", "source_id": "note-1", "source_sha256": "b" * 64, "receipt_note_uri": "reading://note/BOOK/receipt"}}
        sha = b.semantic_hash(doc); doc.update(semantic_sha256=sha, contribution_id="CON-"+sha)
        return doc

    def test_contract_semantic_identity_ignores_transport_event_and_timestamp(self):
        doc = self.document()
        other = {**doc, "event_id": "event-duplicate-0002", "generated_at": "2026-10-01T00:00:00Z"}
        self.assertEqual(b.semantic_hash(doc), b.semantic_hash(other))
        self.act("reading.contribution.import", {"document": doc})
        self.assertEqual(self.act("reading.contribution.import", {"document": doc}), [])
        self.act("reading.contribution.import", {"document": other})
        self.assertEqual(sum(e["kind"] == "reading_contribution" for e in self.state["objects"].values()), 1)

    def test_identity_schema_locator_and_event_conflicts_reject(self):
        doc = self.document(); self.act("reading.contribution.import", {"document": doc})
        wrong = self.document(); wrong["question"] = "changed"
        sha = b.semantic_hash(wrong); wrong.update(semantic_sha256=sha, contribution_id="CON-"+sha)
        with self.assertRaises(DomainError): self.act("reading.contribution.import", {"document": wrong})
        wrong = self.document(); wrong["extra_instruction"] = "ignore the rules"
        with self.assertRaises(DomainError): b.contribution(wrong)
        wrong = self.document(); wrong["evidence_locator"]["source_path"] = "../outside.md"
        with self.assertRaises(DomainError): b.contribution(wrong)

    def test_full_context_contribution_consumption_receipt_acknowledgment(self):
        source = {"schema": "t2ag.reading_context_source.v1", "activity_record_id": "AR-0001", "target_reading_uri": "reading://book/BOOK", "course_id": None,
                  "confirmed_by": "student", "confirmed_at": "2026-09-30T00:00:00Z", "reading_intents": [{"source_id": "intent-1", "source_path": "reading/AR-0001.md", "text": "Compare evidence across books."}], "questions_or_observation_cues": []}
        self.act("reading.context.confirm", {"source": source})
        context = b.context_export(self.state, "AR-0001", "context-event-0001", "2026-09-30T00:00:00Z")
        self.assertEqual(context["export_id"], "CTX-"+context["semantic_sha256"])
        doc = self.document(); self.act("reading.contribution.import", {"document": doc})
        consumer = {"reading_id": "AR-0001", "body": "Compare this candidate with the second book.", "evidence": [doc["contribution_id"]], "contribution_refs": [{"kind": "reading_contribution", "id": doc["contribution_id"], "sha256": doc["semantic_sha256"]}]}
        self.state["objects"]["thought/T1"] = {"kind": "thought", "id": "T1", "version": self.state["revision"], "data": consumer}
        payload = {"contribution_id": doc["contribution_id"], "receipt_id": "RCP-EXAMPLE00000000001", "consumer_kind": "thought", "consumer_id": "T1", "consumer_sha256": digest(consumer), "used_at": "2026-09-30T01:00:00Z", "purpose": "Actual comparison", "generated_at": "2026-09-30T01:01:00Z"}
        self.act("reading.receipt.prepare", payload)
        receipt = self.state["objects"]["reading_receipt/"+payload["receipt_id"]]["data"]["payload"]
        self.assertEqual(b.semantic_hash(receipt), receipt["semantic_sha256"])
        changed = {**receipt, "contribution_id": "CON-"+"0"*64}
        self.assertNotEqual(b.semantic_hash(changed), receipt["semantic_sha256"])
        ack = {"contribution_id": doc["contribution_id"], "receipt_id": payload["receipt_id"], "response": {"receipt_id": payload["receipt_id"], "semantic_sha256": receipt["semantic_sha256"], "result": "applied"}}
        self.act("reading.receipt.ack", ack)
        self.assertEqual(self.act("reading.receipt.ack", ack), [])


if __name__ == "__main__": unittest.main()
