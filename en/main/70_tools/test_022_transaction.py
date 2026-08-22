#!/usr/bin/env python3
"""Hardened tests for activity_transaction."""
from __future__ import annotations

import sys
import json
import os
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_transaction as txn


class TransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="t2ag-022-txn-")
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        (self.root / "progress.md").write_text("old\n", encoding="utf-8")
        src = self.root / "exercises" / "U1101"
        src.mkdir(parents=True)
        (src / "exercise.md").write_text("body\n", encoding="utf-8")
        self.engine = txn.ActivityTransaction(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_apply_and_idempotent_second_commit(self) -> None:
        head = self.engine.current_head(["progress.md"])
        plan = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-1",
            ops=[
                txn.FileOp("progress.md", "write", content=b"new\n"),
                txn.FileOp("activity_ledger.md", "write", content=b"ledger\n"),
            ],
            expected_head=head,
        )
        self.engine.stage(plan)
        result = self.engine.apply("TXN-1")
        self.assertEqual(result["status"], "committed")
        self.assertEqual((self.root / "progress.md").read_text(encoding="utf-8"), "new\n")
        again = self.engine.apply("TXN-1")
        self.assertEqual(again["status"], "already_committed_verified")

    def test_failure_rolls_back_write(self) -> None:
        head = self.engine.current_head(["progress.md"])
        plan = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-2",
            ops=[
                txn.FileOp("progress.md", "write", content=b"mutated\n"),
                txn.FileOp("extra.md", "write", content=b"x\n"),
            ],
            expected_head=head,
        )
        self.engine.stage(plan)
        with self.assertRaises(txn.TransactionError):
            self.engine.apply("TXN-2", fail_at="after_install:1")
        self.assertEqual((self.root / "progress.md").read_text(encoding="utf-8"), "old\n")
        self.assertFalse((self.root / "extra.md").exists())

    def test_exception_at_replace_and_journal_boundaries_rolls_back(self) -> None:
        for offset, point in enumerate(("write_after_replace:1", "after_journal:1")):
            transaction_id = f"TXN-FINE-{offset}"
            engine = txn.ActivityTransaction(self.root)
            plan = txn.TransactionPlan(
                scope_id="main",
                transaction_id=transaction_id,
                ops=[txn.FileOp("progress.md", "write", content=b"candidate\n")],
                expected_head={"progress.md": txn.sha256_file(self.root / "progress.md")},
            )
            engine.stage(plan)
            with self.assertRaisesRegex(txn.TransactionError, point):
                engine.apply(transaction_id, fail_at=point, defer_commit=True)
            self.assertEqual((self.root / "progress.md").read_text(encoding="utf-8"), "old\n")

    def test_deferred_commit_can_rollback_after_postcheck_failure(self) -> None:
        before = (self.root / "progress.md").read_bytes()
        plan = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-DEFER",
            ops=[txn.FileOp("progress.md", "write", content=b"candidate\n")],
            expected_head={"progress.md": txn.sha256_file(self.root / "progress.md")},
        )
        self.engine.stage(plan)
        installed = self.engine.apply("TXN-DEFER", defer_commit=True)
        self.assertEqual(installed["status"], "installed_pending_postcheck")
        self.assertEqual((self.root / "progress.md").read_bytes(), b"candidate\n")
        self.engine.rollback("TXN-DEFER")
        self.assertEqual((self.root / "progress.md").read_bytes(), before)

    def test_deferred_commit_requires_postcheck_marker(self) -> None:
        plan = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-FINALIZE",
            ops=[txn.FileOp("progress.md", "write", content=b"candidate\n")],
            expected_head={"progress.md": txn.sha256_file(self.root / "progress.md")},
        )
        self.engine.stage(plan)
        self.engine.apply("TXN-FINALIZE", defer_commit=True)
        with self.assertRaisesRegex(txn.TransactionError, "cannot commit"):
            self.engine.commit("TXN-FINALIZE")
        self.engine.mark_postcheck_passed("TXN-FINALIZE")
        committed = self.engine.commit("TXN-FINALIZE")
        self.assertEqual(committed["status"], "committed")
        verified = self.engine.apply("TXN-FINALIZE")
        self.assertEqual(verified["status"], "already_committed_verified")

    def test_move_failure_restores_source(self) -> None:
        head = self.engine.current_head(
            ["exercises/U1101", "exercises/exercise01", "progress.md"]
        )
        # only U1101 exists
        head = {
            "exercises/U1101": txn.sha256_tree(self.root / "exercises" / "U1101"),
            "exercises/exercise01": None,
            "progress.md": txn.sha256_file(self.root / "progress.md"),
        }
        plan = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-MOVE",
            ops=[
                txn.FileOp(
                    "exercises/exercise01",
                    "move",
                    source_relative="exercises/U1101",
                ),
                txn.FileOp("progress.md", "write", content=b"after-move\n"),
            ],
            expected_head=head,
        )
        self.engine.stage(plan)
        with self.assertRaises(txn.TransactionError):
            self.engine.apply("TXN-MOVE", fail_at="after_install:1")
        self.assertTrue((self.root / "exercises" / "U1101" / "exercise.md").is_file())
        self.assertFalse((self.root / "exercises" / "exercise01").exists())
        self.assertEqual((self.root / "progress.md").read_text(encoding="utf-8"), "old\n")

    def test_path_escape_rejected(self) -> None:
        head = self.engine.current_head(["progress.md"])
        plan = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-ESC",
            ops=[txn.FileOp("../outside.txt", "write", content=b"x\n")],
            expected_head=head,
        )
        with self.assertRaises(txn.TransactionError):
            self.engine.stage(plan)

    def test_same_txn_id_requires_identical_plan(self) -> None:
        head = self.engine.current_head(["progress.md"])
        plan1 = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-SAME",
            ops=[txn.FileOp("progress.md", "write", content=b"a\n")],
            expected_head=head,
        )
        self.engine.stage(plan1)
        plan2 = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-SAME",
            ops=[txn.FileOp("progress.md", "write", content=b"b\n")],
            expected_head=head,
        )
        with self.assertRaises(txn.TransactionError):
            self.engine.stage(plan2)

    def test_move_target_preexist_restored_on_rollback(self) -> None:
        # create target that already exists
        dst = self.root / "exercises" / "exercise01"
        dst.mkdir(parents=True)
        (dst / "old_target.md").write_text("keep-me\n", encoding="utf-8")
        head = {
            "exercises/U1101": txn.sha256_tree(self.root / "exercises" / "U1101"),
            "exercises/exercise01": txn.sha256_tree(dst),
        }
        plan = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-PRE",
            ops=[
                txn.FileOp(
                    "exercises/exercise01",
                    "move",
                    source_relative="exercises/U1101",
                ),
                txn.FileOp("progress.md", "write", content=b"x\n"),
            ],
            expected_head={**head, "progress.md": txn.sha256_file(self.root / "progress.md")},
        )
        self.engine.stage(plan)
        with self.assertRaises(txn.TransactionError):
            self.engine.apply("TXN-PRE", fail_at="after_install:1")
        self.assertTrue((self.root / "exercises" / "U1101" / "exercise.md").is_file())
        self.assertTrue((dst / "old_target.md").is_file())
        self.assertEqual((dst / "old_target.md").read_text(encoding="utf-8"), "keep-me\n")

    def test_baseline_conflict(self) -> None:
        plan = txn.TransactionPlan(
            scope_id="main",
            transaction_id="TXN-3",
            ops=[txn.FileOp("progress.md", "write", content=b"x\n")],
            expected_head={"progress.md": "deadbeef"},
        )
        with self.assertRaises(txn.TransactionError):
            self.engine.stage(plan)

    def test_live_owner_blocks_concurrent_and_wrong_nonce_release(self) -> None:
        self.engine.acquire_lock("TXN-LOCK-A")
        other = txn.ActivityTransaction(self.root)
        with self.assertRaisesRegex(txn.TransactionError, "scope lock held"):
            other.acquire_lock("TXN-LOCK-B")
        with self.assertRaisesRegex(txn.TransactionError, "wrong owner nonce"):
            other.release_lock("TXN-LOCK-A")
        self.engine.release_lock("TXN-LOCK-A")

    def test_pid_reuse_identity_mismatch_preserves_stale_evidence(self) -> None:
        self.engine.acquire_lock("TXN-OLD")
        payload = self.engine._lock_payload()
        payload["pid"] = os.getpid()
        payload["pid_start_identity"] = "reused-pid-old-process"
        self.engine._atomic_write_json(self.engine.lock_path, payload)
        other = txn.ActivityTransaction(self.root)
        other.acquire_lock("TXN-NEW")
        self.assertEqual(other._lock_payload()["transaction_id"], "TXN-NEW")
        evidence = list(other.recovery_root.glob("stale-lock-*.json"))
        self.assertEqual(len(evidence), 1)
        preserved = json.loads(evidence[0].read_text(encoding="utf-8"))
        self.assertEqual(preserved["transaction_id"], "TXN-OLD")
        other.release_lock("TXN-NEW")

    def test_corrupt_lock_is_not_silently_deleted(self) -> None:
        self.engine.recovery_root.mkdir(parents=True, exist_ok=True)
        self.engine.lock_path.write_bytes(b"{not-json")
        with self.assertRaisesRegex(txn.TransactionError, "corrupt scope lock"):
            self.engine.acquire_lock("TXN-CORRUPT")
        self.assertEqual(self.engine.lock_path.read_bytes(), b"{not-json")

    def test_completed_lock_can_be_superseded_with_evidence(self) -> None:
        self.engine.acquire_lock("TXN-DONE")
        payload = self.engine._lock_payload()
        payload["status"] = "committed"
        self.engine._atomic_write_json(self.engine.lock_path, payload)
        other = txn.ActivityTransaction(self.root)
        other.acquire_lock("TXN-NEXT")
        self.assertEqual(other._lock_payload()["transaction_id"], "TXN-NEXT")
        self.assertEqual(len(list(other.recovery_root.glob("stale-lock-*.json"))), 1)
        other.release_lock("TXN-NEXT")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
