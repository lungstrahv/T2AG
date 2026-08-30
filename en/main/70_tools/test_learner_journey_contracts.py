#!/usr/bin/env python3
"""Atomic contracts for the deterministic learner journey surface."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import learner_journey as journey


TOOLS = Path(__file__).resolve().parent
MANIFEST = TOOLS / "learner_journey_scenarios.json"
REQUIRED = {
    "scenario_id", "initial_state", "user_turns", "required_surface_order",
    "max_meaningful_pauses", "forbidden_operator_terms", "expected_writes",
    "zero_partial_write", "structured_operator_result",
}


def load_scenarios() -> list[dict]:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if document.get("schema") != "t2ag.learner_journey_scenarios.v1":
        raise AssertionError("unexpected learner journey manifest schema")
    return document["scenarios"]


class LearnerJourneyContracts(unittest.TestCase):
    def test_manifest_has_exact_six_scenarios_and_event_contracts(self) -> None:
        scenarios = load_scenarios()
        self.assertEqual(
            [item["scenario_id"] for item in scenarios],
            ["install", "first_run_project", "explicit_continue", "conflict_recovery", "activity_close", "group_activation"],
        )
        for scenario in scenarios:
            self.assertEqual(set(scenario), REQUIRED)
            result = scenario["structured_operator_result"]
            self.assertGreaterEqual(len(result["events"]), 2)
            self.assertIn(result["pause_owner"], {"none", "journey_owner"})
            pause_count = 0 if result["pause_owner"] == "none" else 1
            self.assertLessEqual(pause_count, scenario["max_meaningful_pauses"])
            self.assertEqual(result["writes"], scenario["expected_writes"])

    def test_renderer_orders_surfaces_and_blocks_operator_leaks(self) -> None:
        for scenario in load_scenarios():
            rendered = journey.render_learner_summary(
                scenario["structured_operator_result"],
                {"scenario_id": scenario["scenario_id"], "audience": "learner"},
            )
            positions = [rendered.index(label) for label in scenario["required_surface_order"]]
            self.assertEqual(positions, sorted(positions))
            for forbidden in scenario["forbidden_operator_terms"]:
                self.assertNotIn(forbidden, rendered)
            self.assertIsNone(re.search(r"(?i)(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", rendered))

    def test_state_and_disk_results_are_fail_closed(self) -> None:
        for scenario in load_scenarios():
            result = scenario["structured_operator_result"]
            with tempfile.TemporaryDirectory(prefix="learner-journey-") as directory:
                root = Path(directory)
                if not result["blockers"]:
                    for relative in result["writes"]:
                        (root / relative).write_text(result["state_after"], encoding="utf-8")
                written = sorted(path.name for path in root.iterdir())
                self.assertEqual(written, sorted(result["writes"]) if not result["blockers"] else [])
                if scenario["zero_partial_write"] and result["blockers"]:
                    self.assertEqual(result["writes"], [])
        group = next(item for item in load_scenarios() if item["scenario_id"] == "group_activation")
        self.assertEqual(group["structured_operator_result"]["state_after"], "planned")
        self.assertIn("keystone_ledger_mismatch", group["structured_operator_result"]["blockers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
