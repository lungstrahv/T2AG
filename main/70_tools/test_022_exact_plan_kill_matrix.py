#!/usr/bin/env python3
"""Contract tests for exact-plan kill boundary enumeration."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import exact_plan_kill_matrix as matrix


class ExactMatrixContractTests(unittest.TestCase):
    def test_every_operation_has_before_after_and_kind_boundaries(self) -> None:
        plan = {
            "ops": [
                {"kind": "move"},
                {"kind": "write"},
            ]
        }
        points = matrix.boundary_points(plan)
        required = {
            "before_install:1",
            "move_before_rename:1",
            "move_after_rename:1",
            "after_install:1",
            "before_install:2",
            "write_after_temp_fsync:2",
            "write_before_replace:2",
            "write_after_replace:2",
            "after_install:2",
            "before_installed_state",
            "after_installed_state",
            "before_committed_marker",
        }
        self.assertTrue(required.issubset(points))
        self.assertEqual(len(points), len(set(points)))


if __name__ == "__main__":
    raise SystemExit(
        0
        if unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        ).wasSuccessful()
        else 1
    )
