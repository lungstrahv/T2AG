#!/usr/bin/env python3
"""Run hard-kill/recover at every operation boundary of one exact 0.2.2 plan."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_transaction as txn
import migrate_022_activity_close as migration


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def copy_shadow(src_root: Path, dst_root: Path) -> None:
    clone = subprocess.run(
        ["git", "clone", "--shared", "--quiet", str(src_root), str(dst_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if clone.returncode != 0:
        raise RuntimeError(clone.stdout + clone.stderr)
    for rel in ("main", "cloud", "AGENTS.md", "CONTEXT.md", "README.md", "t2ag_directory_guide.html"):
        source = src_root / rel
        target = dst_root / rel
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(
                source,
                target,
                ignore=shutil.ignore_patterns(
                    ".venv", "__pycache__", "*.pyc", ".activity_txn", "archives", "ATBS_3e"
                ),
                dirs_exist_ok=True,
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def boundary_points(plan: dict[str, Any]) -> list[str]:
    points: list[str] = []
    for index, op in enumerate(plan["ops"], start=1):
        points.append(f"before_install:{index}")
        if op["kind"] == "write":
            points.extend(
                [
                    f"write_after_temp_fsync:{index}",
                    f"write_before_replace:{index}",
                    f"write_after_replace:{index}",
                ]
            )
        elif op["kind"] == "move":
            points.extend(
                [f"move_before_rename:{index}", f"move_after_rename:{index}"]
            )
        points.extend(
            [
                f"before_journal:{index}",
                f"after_journal:{index}",
                f"after_install:{index}",
            ]
        )
    points.extend(
        [
            "before_installed_state",
            "after_installed_state",
            "before_committed_marker",
        ]
    )
    return points


WORKER = """
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).resolve() / "main/70_tools"))
import activity_transaction as txn
root = Path(sys.argv[1]).resolve()
plan = json.loads(Path(sys.argv[2]).read_bytes().decode("utf-8"))
contents = plan.get("_write_contents") or plan.get("files") or {}
ops = []
for op in plan["ops"]:
    if op["kind"] == "move":
        ops.append(txn.FileOp(op["relative_path"], "move", source_relative=op["source_relative"]))
    else:
        ops.append(txn.FileOp(op["relative_path"], "write", content=contents[op["relative_path"]].encode("utf-8")))
engine = txn.ActivityTransaction(root)
tplan = txn.TransactionPlan(
    scope_id="main",
    transaction_id=plan["transaction_id"],
    ops=ops,
    expected_head=plan["expected_head"],
    metadata={"payload_sha256": plan["payload_sha256"]},
)
engine.stage(tplan)
engine.apply(plan["transaction_id"], defer_commit=True)
if os.environ.get("T2AG_TXN_HARD_EXIT_AT") == "before_committed_marker":
    engine.mark_postcheck_passed(plan["transaction_id"])
    engine.commit(plan["transaction_id"])
"""


def run_cli(command: list[str], *, cwd: Path) -> dict[str, Any]:
    run = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if run.returncode != 0:
        raise RuntimeError(run.stdout + run.stderr)
    payload = json.loads(run.stdout)
    if not payload.get("ok"):
        raise RuntimeError(str(payload))
    return payload


def verify_prestate(root: Path, plan: dict[str, Any]) -> str:
    engine = txn.ActivityTransaction(root)
    actual = engine.current_head(list(plan["expected_head"]))
    mismatches = {
        rel: {"expected": want, "actual": actual.get(rel)}
        for rel, want in plan["expected_head"].items()
        if actual.get(rel) != want
    }
    if mismatches:
        raise RuntimeError("rollback prestate mismatch: " + json.dumps(mismatches, sort_keys=True))
    residues = [
        str(path.relative_to(root))
        for path in root.rglob("*.tmp")
        if ".activity_txn" not in path.parts
    ]
    if residues:
        raise RuntimeError(f"install temp residues: {residues}")
    return sha256_bytes(
        json.dumps(actual, sort_keys=True, separators=(",", ":")).encode()
    )


def remove_recovery(shadow: Path) -> None:
    target = (shadow / ".activity_txn").resolve()
    expected = shadow.resolve() / ".activity_txn"
    if target != expected:
        raise RuntimeError(f"unexpected recovery target: {target}")
    if target.exists():
        shutil.rmtree(target)


def run_matrix(source_root: Path, plan_path: Path, report_file: Path) -> dict[str, Any]:
    plan = migration.load_plan(plan_path)
    plan_file_sha = plan.pop("_file_sha256")
    plan.pop("_raw", None)
    points = boundary_points(plan)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="t2ag-022-exact-kill-") as temp:
        temp_root = Path(temp)
        shadow = temp_root / "t2ag"
        copy_shadow(source_root, shadow)
        shadow_plan = temp_root / plan_path.name
        shutil.copy2(plan_path, shadow_plan)
        worker = temp_root / "kill_worker.py"
        worker.write_text(WORKER, encoding="utf-8", newline="\n")
        before_sha = verify_prestate(shadow, plan)
        for point in points:
            started = time.perf_counter_ns()
            env = os.environ.copy()
            env["T2AG_TXN_HARD_EXIT_AT"] = point
            child = subprocess.run(
                [sys.executable, "-B", str(worker), str(shadow), str(shadow_plan)],
                cwd=shadow,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if child.returncode != 97:
                raise RuntimeError(
                    f"hard-kill point did not exit 97: {point}: "
                    + child.stdout
                    + child.stderr
                )
            status = run_cli(
                [
                    sys.executable,
                    "-B",
                    str(shadow / "main/70_tools/activity_transaction.py"),
                    "--root",
                    str(shadow),
                    "--transaction-id",
                    plan["transaction_id"],
                    "--recover",
                    "status",
                ],
                cwd=shadow,
            )
            rolled = run_cli(
                [
                    sys.executable,
                    "-B",
                    str(shadow / "main/70_tools/activity_transaction.py"),
                    "--root",
                    str(shadow),
                    "--transaction-id",
                    plan["transaction_id"],
                    "--recover",
                    "rollback",
                ],
                cwd=shadow,
            )
            after_sha = verify_prestate(shadow, plan)
            if after_sha != before_sha:
                raise RuntimeError(f"manifest digest mismatch after {point}")
            rows.append(
                {
                    "failure_injection_point": point,
                    "child_exit_code": child.returncode,
                    "status_before_recover": status["status"],
                    "recover_result": rolled["status"],
                    "before_manifest_sha256": before_sha,
                    "after_manifest_sha256": after_sha,
                    "duration_ms": (time.perf_counter_ns() - started) // 1_000_000,
                    "status": "pass",
                }
            )
            remove_recovery(shadow)
    payload = {
        "schema": "t2ag.exact_plan_kill_matrix.v1",
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
                "run_id": "kill.full_matrix",
                "status": "pass",
                "argv": [
                    sys.executable, "-B", str(Path(__file__).resolve()),
                    "--source-root", str(source_root.resolve()),
                    "--plan-file", str(plan_path.resolve()),
                    "--report-file", str(report_file.resolve()),
                ],
                "exit_code": 0,
                "assertions": [
                    "every_hard_kill_boundary_exited_97",
                    "all_hard_kill_points_recovered_identical_manifest",
                ],
            }
        ],
        "status": "pass",
    }
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
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
            args.source_root.resolve(),
            args.plan_file.resolve(),
            args.report_file.resolve(),
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
