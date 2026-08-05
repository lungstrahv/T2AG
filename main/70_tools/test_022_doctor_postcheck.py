from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import t2ag_doctor as doctor


class DoctorTransactionScopeTests(unittest.TestCase):
    def test_lite_exclusion_requires_matching_active_transaction_plan(self) -> None:
        transaction_id = "MIG022-0123456789abcdef"
        all_releases = ("t2ag", "t2ag-skeleton", "t2ag-lite")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = {"T2AG_022_EXPECT_TRANSACTION_ID": transaction_id}
            self.assertEqual(
                doctor.distribution_release_names(root, {}), all_releases
            )
            self.assertEqual(
                doctor.distribution_release_names(root, env), all_releases
            )
            plan = root / ".activity_txn" / transaction_id / "plan.json"
            plan.parent.mkdir(parents=True)
            plan.write_text(
                json.dumps(
                    {"transaction_id": transaction_id, "status": "staged"}
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                doctor.distribution_release_names(root, env), all_releases
            )
            for status in (
                "installed_pending_postcheck",
                "postcheck_passed",
                "committed",
            ):
                plan.write_text(
                    json.dumps(
                        {"transaction_id": transaction_id, "status": status}
                    ),
                    encoding="utf-8",
                )
                self.assertEqual(
                    doctor.distribution_release_names(root, env),
                    ("t2ag", "t2ag-skeleton"),
                )
            plan.write_text(
                json.dumps(
                    {
                        "transaction_id": "MIG022-fedcba9876543210",
                        "status": "committed",
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                doctor.distribution_release_names(root, env), all_releases
            )

    def test_close_and_lifecycle_ids_require_matching_transaction_plan(self) -> None:
        all_releases = ("t2ag", "t2ag-skeleton", "t2ag-lite")
        for transaction_id in (
            "CLOSE022-0123456789abcdef0123456789abcdef",
            "LIFECYCLE022-fedcba9876543210fedcba9876543210",
        ):
            with self.subTest(transaction_id=transaction_id), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                env = {"T2AG_022_EXPECT_TRANSACTION_ID": transaction_id}
                plan = root / ".activity_txn" / transaction_id / "plan.json"
                plan.parent.mkdir(parents=True)
                plan.write_text(
                    json.dumps(
                        {"transaction_id": transaction_id, "status": "committed"}
                    ),
                    encoding="utf-8",
                )
                self.assertEqual(
                    doctor.distribution_release_names(root, env),
                    ("t2ag", "t2ag-skeleton"),
                )
                self.assertEqual(
                    doctor.distribution_release_names(
                        root, {"T2AG_022_EXPECT_TRANSACTION_ID": transaction_id + "x"}
                    ),
                    all_releases,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
