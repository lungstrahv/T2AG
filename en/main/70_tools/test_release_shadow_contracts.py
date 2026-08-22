#!/usr/bin/env python3
"""Atomic contracts for isolated release-shadow authorization and cleanup."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import exact_plan_shadow as shadow


class ExactPlanShadowContractTests(unittest.TestCase):
    def test_shadow_authorization_binds_exact_plan_and_is_not_production(self) -> None:
        plan = {
            "campaign_id": "C",
            "plan_id": "P",
            "transaction_id": "T",
            "payload_sha256": "1" * 64,
            "executor_bundle_sha256": "2" * 64,
            "baseline_binding_sha256": "3" * 64,
            "worktree_manifest_sha256": "4" * 64,
            "watched_root_manifest": {"sha256": "5" * 64},
        }
        auth = shadow.shadow_authorization(plan, "6" * 64)
        self.assertEqual(auth["authorization_mode"], "shadow")
        self.assertEqual(auth["plan_file_sha256"], "6" * 64)
        self.assertIn("SHADOW ONLY", auth["approval_text"])
        self.assertEqual(
            shadow.mig.sha256_text(auth["approval_text"]),
            auth["approval_text_sha256"],
        )

    def test_cleanup_guard_rejects_any_non_dedicated_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-shadow-guard-") as tmp:
            root = Path(tmp)
            shadow.assert_cleanup_target(root, root / "t2ag-shadow")
            with self.assertRaises(shadow.ShadowError):
                shadow.assert_cleanup_target(root, root / "other")
            with self.assertRaises(shadow.ShadowError):
                shadow.assert_cleanup_target(root, root.parent / "t2ag-shadow")

    def test_immutable_report_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-shadow-report-") as tmp:
            path = Path(tmp) / "report.json"
            shadow.write_exclusive(path, b"{}\n")
            self.assertEqual(path.read_bytes(), b"{}\n")
            with self.assertRaises(shadow.ShadowError):
                shadow.write_exclusive(path, b"changed\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
