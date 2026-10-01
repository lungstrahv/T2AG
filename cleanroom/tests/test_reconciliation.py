from copy import deepcopy
import unittest

from t2ag_next import reconciliation as r
from t2ag_next.model import DomainError
from t2ag_next.support import digest


class LegacyResolutionJourneys(unittest.TestCase):
    def setUp(self):
        self.old = {"activity_id": "C/L", "course_id": "C", "position": "unresolved narrative", "waiting_for": "clarify_conflict", "legacy": {"path": "frozen/progress.md"},
                    "legacy_current_section": "At problem 2: waiting_for=feeling. The answer was correct.", "uncertainties": ["cursor_mapping_unknown", "source_pending"], "reconciliation_ids": ["earlier"]}
        self.state = {"revision": 1, "objects": {"cursor/C/L": {"kind": "cursor", "id": "C/L", "version": 1, "data": self.old}}}
        self.payload = {"id": "resolve-1", "target_kind": "cursor", "target_id": "C/L", "changes": {"position": "At problem 2", "waiting_for": "feeling"},
            "resolves": ["cursor_mapping_unknown"], "basis": "source_evidence", "rationale": "Literal preserved cursor and gate; no permission is renewed.",
            "evidence": [{"kind": "cursor", "id": "C/L", "field": "legacy_current_section", "value_sha256": digest(self.old["legacy_current_section"]), "excerpt": self.old["legacy_current_section"]}]}

    def run_plan(self, payload=None, role="teacher"):
        return r.plan(self.state, {"request_id": "fixture", "action": "migration.reconcile", "payload": payload or self.payload,
            "actor": {"role": role, "source": "synthetic original evidence", "text": "Resolve this particular preserved ambiguity."}, "expected": {k: v["version"] for k, v in self.state["objects"].items()}})

    def test_literal_stop_is_reconciled_without_erasing_other_ambiguity_or_permissions(self):
        original = deepcopy(self.state)
        effects = self.run_plan()
        updated, receipt = effects[0]["data"], effects[1]["data"]
        self.assertEqual(updated["position"], "At problem 2")
        self.assertEqual(updated["uncertainties"], ["source_pending"])
        self.assertFalse(updated["historical_permissions_active"])
        self.assertEqual(receipt["before_sha256"], digest(self.old))
        self.assertEqual(self.state, original)

    def test_new_guess_wrong_evidence_or_unknown_reason_cannot_be_a_source_mapping(self):
        cases = []
        bad = deepcopy(self.payload); bad["changes"]["position"] = "The next chapter"; cases.append(bad)
        bad = deepcopy(self.payload); bad["evidence"][0]["value_sha256"] = "0"*64; cases.append(bad)
        bad = deepcopy(self.payload); bad["resolves"] = ["made_up"]; cases.append(bad)
        bad = deepcopy(self.payload); bad["changes"]["waiting_for"] = "ready"; cases.append(bad)
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(DomainError): self.run_plan(bad)

    def test_specific_student_resolution_retains_evidence_and_cannot_regrade_history(self):
        p = deepcopy(self.payload); p["basis"] = "student_resolution"; p["changes"]["position"] = "Student-selected new stopping point"
        with self.assertRaises(DomainError): self.run_plan(p)
        self.assertEqual(self.run_plan(p, "student")[1]["data"]["basis"], "student_resolution")
        for kind in ("attempt", "review", "page", "ticket", "session", "mistake"):
            p["target_kind"] = kind
            with self.subTest(kind=kind), self.assertRaises(DomainError): self.run_plan(p, "student")


if __name__ == "__main__": unittest.main()
