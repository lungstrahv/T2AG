#!/usr/bin/env python3
"""RC: real subprocess hard-kill/recover matrix for transaction boundaries."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def tree_manifest(root: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".activity_txn" in path.parts:
            continue
        rows.append(
            (
                path.relative_to(root).as_posix(),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return rows


WORKER = """
import os
import sys
from pathlib import Path
sys.path.insert(0, {tools!r})
import activity_transaction as txn
root = Path(sys.argv[1])
transaction_id = sys.argv[2]
engine = txn.ActivityTransaction(root)
plan = txn.TransactionPlan(
    scope_id="main",
    transaction_id=transaction_id,
    ops=[
        txn.FileOp(
            "exercises/exercise01",
            "move",
            source_relative="exercises/U1101",
        ),
        txn.FileOp("progress.md", "write", content=b"new-progress\\n"),
        txn.FileOp("new-index.md", "write", content=b"new-index\\n"),
    ],
    expected_head={{
        "exercises/U1101": txn.sha256_tree(root / "exercises/U1101"),
        "exercises/exercise01": txn.sha256_tree(root / "exercises/exercise01"),
        "progress.md": txn.sha256_file(root / "progress.md"),
        "new-index.md": None,
    }},
)
engine.stage(plan)
installed = engine.apply(transaction_id, defer_commit=True)
if os.environ.get("T2AG_TXN_MARK_AND_COMMIT") == "1":
    engine.mark_postcheck_passed(transaction_id)
    engine.commit(transaction_id)
print(installed["status"])
"""


class KillRecoverTests(unittest.TestCase):
    HARD_KILL_POINTS = (
        "before_install:1",
        "move_before_target_remove:1",
        "move_before_rename:1",
        "move_after_rename:1",
        "before_journal:1",
        "after_journal:1",
        "after_install:1",
        "before_install:2",
        "write_after_temp_fsync:2",
        "write_before_replace:2",
        "write_after_replace:2",
        "before_journal:2",
        "after_journal:2",
        "after_install:2",
        "before_install:3",
        "write_after_temp_fsync:3",
        "write_before_replace:3",
        "write_after_replace:3",
        "before_journal:3",
        "after_journal:3",
        "after_install:3",
        "before_installed_state",
        "after_installed_state",
    )

    def make_fixture(self, directory: Path) -> tuple[Path, Path, list[tuple[str, str]]]:
        root = directory / "repo"
        root.mkdir()
        (root / "progress.md").write_bytes(b"old-progress\n")
        source = root / "exercises/U1101"
        source.mkdir(parents=True)
        (source / "exercise.md").write_bytes(b"source-body\n")
        target = root / "exercises/exercise01"
        target.mkdir(parents=True)
        (target / "old-target.md").write_bytes(b"preexisting-target\n")
        worker = directory / "worker.py"
        worker.write_text(
            textwrap.dedent(WORKER.format(tools=str(TOOLS))),
            encoding="utf-8",
        )
        return root, worker, tree_manifest(root)

    def recover_cli(self, root: Path, transaction_id: str, mode: str) -> dict:
        run = subprocess.run(
            [
                sys.executable,
                "-B",
                str(TOOLS / "activity_transaction.py"),
                "--root",
                str(root),
                "--transaction-id",
                transaction_id,
                "--recover",
                mode,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(run.returncode, 0, msg=run.stdout + run.stderr)
        payload = json.loads(run.stdout)
        self.assertTrue(payload.get("ok"), payload)
        return payload

    def test_real_hard_kill_before_and_after_every_install_boundary(self) -> None:
        for ordinal, point in enumerate(self.HARD_KILL_POINTS, start=1):
            with self.subTest(point=point), tempfile.TemporaryDirectory(
                prefix="t2ag-022-kill-"
            ) as tmp:
                root, worker, before = self.make_fixture(Path(tmp))
                transaction_id = f"TXN-KILL-{ordinal:03d}"
                env = os.environ.copy()
                env["T2AG_TXN_HARD_EXIT_AT"] = point
                child = subprocess.run(
                    [sys.executable, "-B", str(worker), str(root), transaction_id],
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(
                    child.returncode,
                    97,
                    msg=f"{point}: {child.stdout}{child.stderr}",
                )
                status = self.recover_cli(root, transaction_id, "status")
                self.assertIn(
                    status["status"],
                    {"installing", "installed_pending_postcheck"},
                    msg=point,
                )
                rolled = self.recover_cli(root, transaction_id, "rollback")
                self.assertEqual(rolled["status"], "rolled_back")
                self.assertEqual(tree_manifest(root), before, msg=point)
                leftovers = [
                    path
                    for path in root.rglob("*.tmp")
                    if ".activity_txn" not in path.parts
                ]
                self.assertEqual(leftovers, [], msg=point)

    def test_hard_kill_before_commit_rolls_back_and_after_commit_verifies(self) -> None:
        for point, expected in (
            ("before_committed_marker", "rollback"),
            ("after_committed_marker", "committed"),
        ):
            with self.subTest(point=point), tempfile.TemporaryDirectory(
                prefix="t2ag-022-commit-kill-"
            ) as tmp:
                root, worker, before = self.make_fixture(Path(tmp))
                transaction_id = "TXN-" + point.upper()
                env = os.environ.copy()
                env["T2AG_TXN_HARD_EXIT_AT"] = point
                env["T2AG_TXN_MARK_AND_COMMIT"] = "1"
                child = subprocess.run(
                    [sys.executable, "-B", str(worker), str(root), transaction_id],
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(child.returncode, 97)
                status = self.recover_cli(root, transaction_id, "status")
                if expected == "rollback":
                    self.assertEqual(status["status"], "postcheck_passed")
                    self.recover_cli(root, transaction_id, "rollback")
                    self.assertEqual(tree_manifest(root), before)
                else:
                    self.assertEqual(status["status"], "committed")
                    resumed = self.recover_cli(root, transaction_id, "resume")
                    self.assertEqual(resumed["status"], "already_committed_verified")
                    self.assertNotEqual(tree_manifest(root), before)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
