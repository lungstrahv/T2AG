#!/usr/bin/env python3
"""Inject recoverable exceptions at every install boundary of one exact plan."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_transaction as txn
import exact_plan_kill_matrix as kill
import migrate_022_activity_close as migration


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transaction_plan(plan: dict[str, Any]) -> txn.TransactionPlan:
    contents = plan.get("_write_contents") or plan.get("files") or {}
    ops: list[txn.FileOp] = []
    for op in plan["ops"]:
        if op["kind"] == "move":
            ops.append(
                txn.FileOp(
                    op["relative_path"], "move", source_relative=op["source_relative"]
                )
            )
        else:
            ops.append(
                txn.FileOp(
                    op["relative_path"],
                    "write",
                    content=contents[op["relative_path"]].encode("utf-8"),
                )
            )
    return txn.TransactionPlan(
        scope_id="main",
        transaction_id=plan["transaction_id"],
        ops=ops,
        expected_head=plan["expected_head"],
        metadata={"payload_sha256": plan["payload_sha256"]},
    )


def run_matrix(source_root: Path, plan_path: Path, report_file: Path) -> dict[str, Any]:
    plan = migration.load_plan(plan_path)
    plan_file_sha = plan.pop("_file_sha256")
    plan.pop("_raw", None)
    points = kill.boundary_points(plan)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="t2ag-022-exact-exception-") as temp:
        shadow = Path(temp) / "t2ag"
        kill.copy_shadow(source_root, shadow)
        before_sha = kill.verify_prestate(shadow, plan)
        for point in points:
            started = time.perf_counter_ns()
            engine = txn.ActivityTransaction(shadow)
            engine.stage(transaction_plan(plan))
            raised = ""
            try:
                if point == "before_committed_marker":
                    engine.apply(plan["transaction_id"], defer_commit=True)
                    engine.mark_postcheck_passed(plan["transaction_id"])
                    engine.commit(plan["transaction_id"], fail_at=point)
                else:
                    engine.apply(
                        plan["transaction_id"], defer_commit=True, fail_at=point
                    )
            except txn.TransactionError as exc:
                raised = str(exc)
            if not raised or point not in raised:
                raise RuntimeError(f"exception point did not raise exact marker: {point}: {raised}")
            status = txn.recover(engine, plan["transaction_id"], mode="status")
            if status.get("status") not in {"rolled_back", "postcheck_passed"}:
                raise RuntimeError(f"unexpected recovery state at {point}: {status}")
            if status.get("status") != "rolled_back":
                engine.rollback(plan["transaction_id"])
            after_sha = kill.verify_prestate(shadow, plan)
            if after_sha != before_sha:
                raise RuntimeError(f"manifest digest mismatch after {point}")
            rows.append(
                {
                    "failure_injection_point": point,
                    "exception": raised,
                    "recover_result": "rolled_back",
                    "before_manifest_sha256": before_sha,
                    "after_manifest_sha256": after_sha,
                    "duration_ms": (time.perf_counter_ns() - started) // 1_000_000,
                    "status": "pass",
                }
            )
            kill.remove_recovery(shadow)
    payload = {
        "schema": "t2ag.exact_plan_exception_matrix.v1",
        "campaign_id": plan["campaign_id"],
        "plan_id": plan["plan_id"],
        "transaction_id": plan["transaction_id"],
        "plan_file": str(plan_path.resolve()),
        "plan_file_sha256": plan_file_sha,
        "payload_sha256": plan["payload_sha256"],
        "tool_source_manifest_sha256": plan["executor_manifest"]["sha256"],
        "operation_count": len(plan["ops"]),
        "point_count": len(points),
        "pass_count": len(rows),
        "fail_count": 0,
        "rows": rows,
        "consumer_runs": [
            {
                "run_id": "exception.full_matrix",
                "status": "pass",
                "argv": [
                    sys.executable, "-B", str(Path(__file__).resolve()),
                    "--source-root", str(source_root.resolve()),
                    "--plan-file", str(plan_path.resolve()),
                    "--report-file", str(report_file.resolve()),
                ],
                "exit_code": 0,
                "assertions": [
                    "every_exception_boundary_raised_exact_marker",
                    "all_exception_points_rolled_back_to_identical_manifest",
                ],
            }
        ],
        "status": "pass",
    }
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with report_file.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "status": "pass",
        "report_file": str(report_file.resolve()),
        "report_sha256": sha256_bytes(raw),
        "operation_count": len(plan["ops"]),
        "point_count": len(points),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument("--report-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_matrix(
            args.source_root.resolve(), args.plan_file.resolve(), args.report_file.resolve()
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
