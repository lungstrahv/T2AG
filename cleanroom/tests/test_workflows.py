"""Checks for the small read-only task catalog, not an execution engine."""
import unittest

from t2ag_next.model import DomainError
from t2ag_next.service import actions
from t2ag_next.workflows import get_workflow, list_workflows


class TaskLoops(unittest.TestCase):
    def test_both_languages_share_names_and_reference_live_actions(self):
        known = set(actions())
        zh, en = list_workflows("zh"), list_workflows("en")
        self.assertEqual(len(zh), 6)
        self.assertEqual([x["name"] for x in zh], [x["name"] for x in en])
        self.assertNotEqual([x["title"] for x in zh], [x["title"] for x in en])
        for row in zh:
            for language in ("zh", "en"):
                workflow = get_workflow(row["name"], language)
                self.assertTrue(all(action in known for step in workflow["steps"] for action in step["actions"]))

    def test_failure_returns_are_local_and_maintenance_can_stop(self):
        for row in list_workflows("en"):
            workflow = get_workflow(row["name"], "en")
            points = {step["id"] for step in workflow["steps"]} | {"stop"}
            self.assertTrue(all(branch["return_to"] in points for branch in workflow["on_failure"]))
            self.assertTrue(workflow["done"] and workflow["stop"] and workflow["checks"])
        repair = get_workflow("repair", "en")
        self.assertEqual(next(branch for branch in repair["on_failure"] if branch["when"] == "same_failure_no_new_evidence")["return_to"], "stop")

    def test_calls_return_independent_copies_and_reject_unknown_selection(self):
        changed = get_workflow("feedback-save", "en")
        changed["steps"][1]["actions"].clear()
        self.assertIn("comprehension.assess", get_workflow("feedback-save", "en")["steps"][1]["actions"])
        for name, language, code in (("missing", "en", "WORKFLOW_NOT_FOUND"), ("repair", "fr", "WORKFLOW_LANGUAGE")):
            with self.assertRaises(DomainError) as raised:
                get_workflow(name, language)
            self.assertEqual(raised.exception.code, code)


if __name__ == "__main__":
    unittest.main()
