#!/usr/bin/env python3
"""Atomic release receipt-chain contracts."""
from __future__ import annotations

import json
import io
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from unittest.mock import patch
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import campaign_receipt as cr


class ReceiptGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="t2ag-receipt-")
        self.workspace = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def emit(self, phase: str, state: str, prev: str | None, **extra):
        payload = {
            "campaign_id": cr.CAMPAIGN_ID,
            "phase": phase,
            "state": state,
            "previous_receipt_sha256": prev,
            **extra,
        }
        return cr.write_receipt(self.workspace, payload)

    def test_chain_uses_previous_sha_not_filename_order(self) -> None:
        r0_path, r0 = self.emit("AD_REMEDIATING", "Z_state", None)
        progress_path, progress = self.emit("AD_REMEDIATING", "A_state", r0)
        path, data = cr.latest_receipt(self.workspace)
        self.assertEqual(path, progress_path)
        self.assertEqual(data["previous_receipt_sha256"], r0)
        self.assertNotEqual(path, r0_path)

    def test_validate_chain_cli_is_operational_and_machine_readable(self) -> None:
        _, start = self.emit("AD_REMEDIATING", "start", None)
        head_path, head_sha = self.emit("AD_REMEDIATING", "next", start)
        output = io.StringIO()
        with redirect_stdout(output):
            code = cr.main(
                ["--workspace", str(self.workspace), "--validate-chain"]
            )
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["head_path"], str(head_path.resolve()))
        self.assertEqual(payload["head_sha256"], head_sha)
        self.assertEqual(payload["chain_length"], 2)
        self.assertIn("unique_active_head", payload["assertions"])

    def test_rejected_side_branch_can_be_preserved(self) -> None:
        _, r0 = self.emit("AD_REMEDIATING", "R0", None)
        _, progress = self.emit("AD_REMEDIATING", "progress", r0)
        _, rejected = self.emit("D_PACKAGE_FROZEN", "invalid", r0)
        with self.assertRaisesRegex(RuntimeError, "one head"):
            cr.latest_receipt(self.workspace)
        ack_path, _ = self.emit(
            "AD_REMEDIATING",
            "e_rejected_acknowledged",
            progress,
            rejected_receipt_sha256=[rejected],
        )
        path, data, chain = cr.validate_receipt_chain(self.workspace)
        self.assertEqual(path, ack_path)
        self.assertEqual(len(chain), 3)
        self.assertIn(rejected, data["rejected_receipt_sha256"])

    def test_missing_predecessor_fails(self) -> None:
        self.emit("AD_REMEDIATING", "bad", "0" * 64)
        with self.assertRaisesRegex(RuntimeError, "missing/rejected predecessor"):
            cr.latest_receipt(self.workspace)

    def test_phase_regression_fails(self) -> None:
        _, frozen = self.emit("D_PACKAGE_FROZEN", "ready", None)
        self.emit("AD_REMEDIATING", "bad-regression", frozen)
        with self.assertRaisesRegex(RuntimeError, "phase regression"):
            cr.latest_receipt(self.workspace)

    def test_corrupt_json_fails(self) -> None:
        directory = cr.receipt_dir(self.workspace)
        directory.mkdir(parents=True)
        (directory / "broken.json").write_bytes(b"{")
        with self.assertRaisesRegex(RuntimeError, "invalid receipt"):
            cr.latest_receipt(self.workspace)

    def test_unknown_phase_fails(self) -> None:
        self.emit("UNKNOWN", "bad", None)
        with self.assertRaisesRegex(RuntimeError, "unknown receipt phase"):
            cr.latest_receipt(self.workspace)

    def test_phase_skip_fails(self) -> None:
        _, start = self.emit("AD_REMEDIATING", "start", None)
        self.emit("E_AUTHORIZED", "bad-skip", start)
        with self.assertRaisesRegex(RuntimeError, "phase skip"):
            cr.latest_receipt(self.workspace)

    def test_cycle_is_detected_explicitly(self) -> None:
        records = [
            {
                "path": Path("a.json"),
                "sha256": "a",
                "data": {
                    "phase": "AD_REMEDIATING",
                    "previous_receipt_sha256": "b",
                },
            },
            {
                "path": Path("b.json"),
                "sha256": "b",
                "data": {
                    "phase": "AD_REMEDIATING",
                    "previous_receipt_sha256": "a",
                },
            },
        ]
        with patch.object(cr, "receipt_records", return_value=records):
            with self.assertRaisesRegex(RuntimeError, "receipt cycle"):
                cr.validate_receipt_chain(self.workspace)

    def test_rejected_receipt_cannot_be_reused_as_predecessor(self) -> None:
        _, r0 = self.emit("AD_REMEDIATING", "R0", None)
        _, progress = self.emit("AD_REMEDIATING", "progress", r0)
        _, rejected = self.emit("D_PACKAGE_FROZEN", "bad", r0)
        self.emit(
            "AD_REMEDIATING",
            "ack",
            progress,
            rejected_receipt_sha256=[rejected],
        )
        self.emit("D_PACKAGE_FROZEN", "reuse", rejected)
        with self.assertRaisesRegex(RuntimeError, "missing/rejected predecessor"):
            cr.latest_receipt(self.workspace)

    def test_stale_campaign_receipt_is_ignored(self) -> None:
        valid_path, _ = self.emit("AD_REMEDIATING", "valid", None)
        directory = cr.receipt_dir(self.workspace)
        (directory / "stale.json").write_text(
            json.dumps(
                {
                    "campaign_id": "STALE",
                    "phase": "UNKNOWN",
                    "previous_receipt_sha256": None,
                }
            ),
            encoding="utf-8",
        )
        path, _ = cr.latest_receipt(self.workspace)
        self.assertEqual(path, valid_path)

    def test_concurrent_writers_create_detectable_fork(self) -> None:
        _, start = self.emit("AD_REMEDIATING", "start", None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.emit, "AD_REMEDIATING", f"branch-{i}", start)
                for i in range(2)
            ]
            for future in futures:
                future.result()
        with self.assertRaisesRegex(RuntimeError, "one head"):
            cr.latest_receipt(self.workspace)


if __name__ == "__main__":
    raise SystemExit(
        0
        if unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        ).wasSuccessful()
        else 1
    )
