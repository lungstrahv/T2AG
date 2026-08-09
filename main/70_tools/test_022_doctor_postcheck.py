from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import t2ag_doctor as doctor


class DoctorProfileDispatchTests(unittest.TestCase):
    def test_default_profile_runs_runtime_only(self) -> None:
        with mock.patch.object(doctor, "execute_doctor_checks") as execute:
            self.assertEqual(doctor.main([]), 0)
        execute.assert_called_once()
        rows = execute.call_args.args[0]
        self.assertTrue(rows)
        self.assertTrue(all(row["phase"] == "runtime" for row in rows))
        self.assertFalse(execute.call_args.kwargs["include_release_parity"])

    def test_release_profile_is_plan_only_until_bound(self) -> None:
        with mock.patch.object(doctor, "execute_doctor_checks") as execute:
            self.assertEqual(doctor.main(["--profile", "release"]), 0)
        execute.assert_not_called()


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


class HandoffClassificationTests(unittest.TestCase):
    def test_workspace_handoff_index_contract(self) -> None:
        if doctor.FLAVOR != "main":
            self.skipTest("workspace handoff index belongs to Main")
        doctor.fails.clear()
        doctor.warns.clear()
        doctor.check_handoff_contract()
        self.assertEqual(doctor.fails, [])

    def test_active_handoff_and_release_backlog_are_separate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            repo = workspace / "t2ag"
            handoffs = workspace / "docs/handoffs"
            repo.mkdir()
            handoffs.mkdir(parents=True)
            (handoffs / "active.md").write_text(
                """# Active fixture
> **handoff_id**：HO-1
> **scope**：topic
> **lane**：topic_design
> **artifact_role**：handoff
> **applies_to**：fixture topic
> **status**：active
> **aging_state**：normal
> **task_match**：fixture task
> **created_at**：2026-08-05T00:00:00+08:00
> **updated_at**：2026-08-05T00:00:00+08:00
> **version_context**：—
> **supersedes**：—
> **superseded_by**：—
> **close_condition**：fixture closed
> **canonical_sources**：fixture source
> **next_action**：fixture action
> **semantic_check**：PASS

## 最小状态摘要

fixture state

## 连续性摘要

无需要恢复的额外主线。
""",
                encoding="utf-8",
            )
            (handoffs / "backlog.md").write_text("# backlog\n", encoding="utf-8")
            (handoffs / "closed.md").write_text("# closed\n", encoding="utf-8")

            def write_index(role: str) -> None:
                (handoffs / "README.md").write_text(
                    f"""# Index

## Active Handoffs

| handoff_id | scope | lane | artifact_role | status | applies_to | task_match | updated_at | 文件 | close_condition |
|---|---|---|---|---|---|---|---|---|---|
| HO-1 | topic | topic_design | handoff | active | fixture topic | fixture task | 2026-08-05T00:00:00+08:00 | `active.md` | fixture closed |

## 下一版本 Backlog

| id | scope | lane | artifact_role | status | 文件 | trigger |
|---|---|---|---|---|---|---|
| BL-1 | project | version_campaign | {role} | pending_next_candidate | `backlog.md` | next candidate |

## Workorders / Plans

## Evidence / Reviews

## Resolved / Archive Handoffs

| handoff_id | scope | lane | artifact_role | status | applies_to | 文件 | replaced/resolved by |
|---|---|---|---|---|---|---|---|
| HO-0 | project | maintenance | handoff | resolved | old fixture | `closed.md` | fixture |
""",
                    encoding="utf-8",
                )

            with (
                mock.patch.object(doctor, "ROOT", repo),
                mock.patch.object(doctor, "FLAVOR", "main"),
            ):
                write_index("evidence + release_backlog")
                doctor.fails.clear()
                doctor.warns.clear()
                with contextlib.redirect_stdout(io.StringIO()):
                    doctor.check_handoff_contract()
                self.assertEqual(doctor.fails, [])

                write_index("evidence")
                doctor.fails.clear()
                with contextlib.redirect_stdout(io.StringIO()):
                    doctor.check_handoff_contract()
                self.assertTrue(any("backlog 分类非法" in message for message in doctor.fails))


if __name__ == "__main__":
    unittest.main(verbosity=2)
