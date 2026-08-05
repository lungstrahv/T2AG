#!/usr/bin/env python3
"""Apply one exact frozen migration plan to a manifest-built shadow."""
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

import migrate_022_activity_close as mig


class ShadowError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ShadowError(f"immutable output exists: {path}")
    temp = path.with_suffix(path.suffix + ".tmp")
    if temp.exists():
        raise ShadowError(f"stale temp exists: {temp}")
    try:
        with temp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if temp.read_bytes() != raw:
            raise ShadowError("immutable output readback mismatch")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def assert_cleanup_target(temp_root: Path, shadow: Path) -> None:
    temp_resolved = temp_root.resolve()
    shadow_resolved = shadow.resolve()
    if shadow_resolved.parent != temp_resolved or shadow_resolved.name != "t2ag-shadow":
        raise ShadowError(f"unsafe cleanup target: {shadow_resolved}")


def shadow_authorization(plan: dict[str, Any], plan_file_sha: str) -> dict[str, Any]:
    approval = (
        "SHADOW ONLY exact frozen-plan projection; no production authorization; "
        f"plan_id={plan['plan_id']} file_sha256={plan_file_sha}"
    )
    return {
        "campaign_id": plan["campaign_id"],
        "phase": "E_AUTHORIZED",
        "state": "delegated_authorized",
        "authorization_mode": "shadow",
        "plan_id": plan["plan_id"],
        "transaction_id": plan["transaction_id"],
        "plan_file_sha256": plan_file_sha,
        "payload_sha256": plan["payload_sha256"],
        "d_review_sha256": "0" * 64,
        "executor_bundle_sha256": plan["executor_bundle_sha256"],
        "baseline_binding_sha256": plan["baseline_binding_sha256"],
        "worktree_manifest_sha256": plan["worktree_manifest_sha256"],
        "watched_root_manifest_sha256": plan["watched_root_manifest"]["sha256"],
        "approval_text": approval,
        "approval_text_sha256": mig.sha256_text(approval),
        "authorization_source_sha256": "0" * 64,
        "shadow_root_binding": "declared-by-report",
    }


def clone_and_overlay(root: Path, shadow: Path, plan: dict[str, Any]) -> None:
    run = subprocess.run(
        ["git", "clone", "--shared", "--quiet", str(root), str(shadow)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if run.returncode != 0:
        raise ShadowError(f"git clone failed: {run.stdout}{run.stderr}")
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise ShadowError("git ls-files failed while building exact shadow")
    for raw_rel in tracked.stdout.split(b"\0"):
        if not raw_rel:
            continue
        rel = raw_rel.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        source = root / rel
        target = shadow / rel
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
    for row in plan["candidate_overlay_manifest"]["rows"]:
        rel = row["path"]
        source = root / rel
        target = shadow / rel
        if row["kind"] == "file":
            if not source.is_file() or mig.sha256_file(source) != row["sha256"]:
                raise ShadowError(f"candidate overlay source drift: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif row["kind"] == "absent":
            if target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
        else:
            raise ShadowError(f"unsupported overlay row kind: {row}")
    # Git checkout may normalize line endings.  Overlay every plan-bound
    # source row from the live candidate so the shadow consumes the exact
    # source bytes/tree hashes recorded by the frozen plan.
    for row in plan["source_tree_manifest"]["rows"]:
        rel = row["path"]
        source = root / rel
        target = shadow / rel
        if row["kind"] == "file":
            if mig.sha256_file(source) != row["sha256"]:
                raise ShadowError(f"frozen source row drift: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif row["kind"] == "tree":
            if mig.txn.sha256_tree(source) != row["sha256"]:
                raise ShadowError(f"frozen source tree drift: {rel}")
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        elif row["kind"] == "absent":
            if target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
        else:
            raise ShadowError(f"unsupported source row kind: {row}")
    actual = mig.path_manifest(shadow, plan["expected_head"].keys())
    if actual != plan["source_tree_manifest"]:
        expected_rows = {
            row["path"]: row for row in plan["source_tree_manifest"]["rows"]
        }
        actual_rows = {row["path"]: row for row in actual["rows"]}
        differing = [
            path
            for path in sorted(set(expected_rows) | set(actual_rows))
            if expected_rows.get(path) != actual_rows.get(path)
        ]
        raise ShadowError(
            f"shadow source manifest does not match frozen plan: {differing[:20]}"
        )


def run_command(argv: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    started = time.time()
    run = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    result: dict[str, Any] = {
        "argv": argv,
        "exit_code": run.returncode,
        "duration_ms": int((time.time() - started) * 1000),
        "stdout_sha256": mig.sha256_text(run.stdout or ""),
        "stderr_sha256": mig.sha256_text(run.stderr or ""),
    }
    try:
        result["json"] = json.loads(run.stdout)
    except json.JSONDecodeError:
        result["stdout_tail"] = (run.stdout or "")[-4000:]
        result["stderr_tail"] = (run.stderr or "")[-4000:]
    if run.returncode != 0:
        raise ShadowError(
            f"command failed exit={run.returncode}: {' '.join(argv)}\n"
            f"{(run.stdout + run.stderr)[-12000:]}"
        )
    return result


def operational_run(
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    *,
    run_id: str,
    assertions: list[str],
) -> dict[str, Any]:
    result = run_command(argv, cwd, env)
    result.update(
        {
            "run_id": run_id,
            "status": "pass",
            "assertions": assertions,
        }
    )
    return result


def expected_failure_run(
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    *,
    run_id: str,
    assertions: list[str],
    watched_paths: list[str],
) -> dict[str, Any]:
    before = mig.path_manifest(cwd, watched_paths)
    started = time.time()
    run = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    after = mig.path_manifest(cwd, watched_paths)
    if run.returncode == 0:
        raise ShadowError(f"negative command unexpectedly passed: {' '.join(argv)}")
    if before != after:
        raise ShadowError(f"negative command changed watched paths: {run_id}")
    return {
        "run_id": run_id,
        "status": "pass",
        "expected_failure": True,
        "argv": argv,
        "exit_code": run.returncode,
        "duration_ms": int((time.time() - started) * 1000),
        "stdout_sha256": mig.sha256_text(run.stdout or ""),
        "stderr_sha256": mig.sha256_text(run.stderr or ""),
        "before_manifest_sha256": before["sha256"],
        "after_manifest_sha256": after["sha256"],
        "assertions": assertions,
    }


def shadow_close_authorization(
    plan_path: Path, phase: str, directory: Path, serial: str
) -> tuple[Path, str]:
    close_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    payload = {
        "campaign_id": close_plan["campaign_id"],
        "phase": phase,
        "state": "shadow_authorized",
        "authorization_mode": "shadow",
        "authorization_source_sha256": "a" * 64,
        "plan_id": close_plan["plan_id"],
        "transaction_id": close_plan["transaction_id"],
        "payload_sha256": close_plan["payload_sha256"],
    }
    path = directory / f"shadow-close-authorization-{serial}.json"
    raw = canonical_bytes(payload)
    path.write_bytes(raw)
    return path, sha256_bytes(raw)


def execute(root: Path, plan_file: Path, report_file: Path) -> dict[str, Any]:
    root = root.resolve()
    plan_file = plan_file.resolve()
    raw_plan = plan_file.read_bytes()
    plan_file_sha = sha256_bytes(raw_plan)
    plan = mig.load_plan(plan_file)
    plan.pop("_raw", None)
    plan.pop("_file_sha256", None)
    if mig.candidate_overlay_manifest(root) != plan["candidate_overlay_manifest"]:
        raise ShadowError("live candidate overlay differs from frozen plan")
    source_before = mig.path_manifest(root, plan["expected_head"].keys())
    if source_before != plan["source_tree_manifest"]:
        raise ShadowError("live source manifest differs from frozen plan")

    temp_root = Path(tempfile.mkdtemp(prefix="t2ag-022-exact-shadow-"))
    shadow = temp_root / "t2ag-shadow"
    assert_cleanup_target(temp_root, shadow)
    report: dict[str, Any]
    try:
        clone_and_overlay(root, shadow, plan)
        auth = shadow_authorization(plan, plan_file_sha)
        auth_path = temp_root / "shadow-authorization.json"
        auth_raw = canonical_bytes(auth)
        auth_path.write_bytes(auth_raw)
        auth_sha = sha256_bytes(auth_raw)
        env = os.environ.copy()
        env["T2AG_022_ALLOW_APPLY"] = "1"
        env["T2AG_022_SHADOW_APPLY"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        cli = shadow / "main/70_tools/migrate_022_activity_close.py"
        apply_argv = [
            sys.executable,
            "-B",
            str(cli),
            "--root",
            str(shadow),
            "--apply",
            "--plan-file",
            str(plan_file),
            "--expect-payload-sha",
            plan["payload_sha256"],
            "--expect-file-sha",
            plan_file_sha,
            "--authorization-receipt",
            str(auth_path),
            "--expect-authorization-sha",
            auth_sha,
            "--confirm",
            "E_migration_apply",
        ]
        first = run_command(apply_argv, shadow, env)
        if first["json"].get("status") != "committed":
            raise ShadowError(f"first exact apply did not commit: {first['json']}")
        mig.verify_projected_state(shadow, plan)
        second = run_command(apply_argv, shadow, env)
        if second["json"].get("status") != "already_committed_verified":
            raise ShadowError(f"second exact apply not idempotent: {second['json']}")

        fresh_path = temp_root / "fresh-zero-plan.json"
        fresh = run_command(
            [
                sys.executable,
                "-B",
                str(cli),
                "--root",
                str(shadow),
                "--dry-run",
                "--plan-out",
                str(fresh_path),
            ],
            shadow,
            env,
        )
        summary = fresh["json"]["summary"]
        if any(summary.get(key) != 0 for key in ("path_ops", "write_ops", "move_ops")):
            raise ShadowError(f"fresh planner is not zero-op: {summary}")

        env["T2AG_022_CLOSE_TEST"] = "1"
        consumer_runs: list[dict[str, Any]] = []
        first_run = dict(first)
        first_run.update(
            run_id="migration.first_apply",
            status="pass",
            assertions=["exact_plan_committed", "all_migration_postchecks_passed"],
        )
        consumer_runs.append(first_run)
        second_run = dict(second)
        second_run.update(
            run_id="migration.second_apply",
            status="pass",
            assertions=["already_committed_verified"],
        )
        consumer_runs.append(second_run)
        fresh_run = dict(fresh)
        fresh_run.update(
            run_id="migration.fresh_zero",
            status="pass",
            assertions=["fresh_planner_zero_ops"],
        )
        consumer_runs.append(fresh_run)

        initial_specs = (
            (
                "doctor.post_migration",
                [sys.executable, "-B", str(shadow / "main/70_tools/t2ag_doctor.py")],
                ["doctor_zero_fail_post_migration"],
            ),
            (
                "state.post_migration",
                [sys.executable, "-B", str(shadow / "main/70_tools/t2ag_state_refresh.py"), "--check"],
                ["state_zero_drift_post_migration"],
            ),
            (
                "context.post_migration",
                [sys.executable, "-B", str(shadow / "main/70_tools/t2ag_context.py"), "--course", "MATH1607H", "--format", "json"],
                ["context_routes_canonical_exercise01"],
            ),
            (
                "activity.post_migration",
                [sys.executable, "-B", str(shadow / "main/70_tools/t2ag_activity.py"), "--course", "MATH1607H", "--intent", "recover"],
                ["activity_routes_canonical_exercise01"],
            ),
        )
        for run_id, spec, assertions in initial_specs:
            run = operational_run(
                spec, shadow, env, run_id=run_id, assertions=assertions
            )
            if run_id == "context.post_migration" and run["json"]["route"]["current_activity_id"] != "exercise01":
                raise ShadowError("post-migration context did not route exercise01")
            if run_id == "activity.post_migration" and run["json"]["current_activity_id"] != "exercise01":
                raise ShadowError("post-migration activity did not route exercise01")
            consumer_runs.append(run)

        ledger_cli = shadow / "main/70_tools/activity_ledger.py"
        close_cli = shadow / "main/70_tools/activity_close.py"
        lifecycle_cli = shadow / "main/70_tools/activity_lifecycle.py"
        math_ledger = shadow / "main/40_course/MATH1607H/activity_ledger.md"
        math_progress = shadow / "main/40_course/MATH1607H/progress.md"
        watched_close = [
            "main/40_course/MATH1607H/activity_ledger.md",
            "main/40_course/MATH1607H/progress.md",
            "main/00_core/t2ag_memory.md",
            "main/10_student/profile/learning_path.md",
        ]
        consumer_runs.append(
            operational_run(
                [sys.executable, "-B", str(ledger_cli), "validate", str(math_ledger)],
                shadow,
                env,
                run_id="ledger.post_migration_validate",
                assertions=["canonical_ledger_valid_post_migration"],
            )
        )

        def plan_and_apply(
            *,
            tool: Path,
            plan_argv: list[str],
            plan_path: Path,
            phase: str,
            prefix: str,
            plan_assertion: str,
            apply_assertion: str,
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            planned = operational_run(
                plan_argv,
                shadow,
                env,
                run_id=f"{prefix}.plan",
                assertions=[plan_assertion],
            )
            auth_path, close_auth_sha = shadow_close_authorization(
                plan_path, phase, temp_root, prefix.replace(".", "-")
            )
            applied = operational_run(
                [
                    sys.executable,
                    "-B",
                    str(tool),
                    "--root",
                    str(shadow),
                    "--course-id",
                    "MATH1607H",
                    "--activity-type",
                    "exercise",
                    "--activity-id",
                    "exercise01",
                    "--apply",
                    "--plan-file",
                    str(plan_path),
                    "--expect-payload-sha",
                    planned["json"]["payload_sha256"],
                    "--expect-file-sha",
                    planned["json"]["file_sha256"],
                    "--authorization-receipt",
                    str(auth_path),
                    "--expect-authorization-sha",
                    close_auth_sha,
                ],
                shadow,
                env,
                run_id=f"{prefix}.apply",
                assertions=[apply_assertion],
            )
            if applied["json"].get("status") != "committed":
                raise ShadowError(f"{prefix} did not commit: {applied['json']}")
            consumer_runs.extend([planned, applied])
            return planned, applied

        span_id = "LS-SHADOW-0001"
        enter_path = temp_root / "lifecycle-enter.json"
        plan_and_apply(
            tool=lifecycle_cli,
            plan_argv=[
                sys.executable, "-B", str(lifecycle_cli), "--root", str(shadow),
                "--course-id", "MATH1607H", "--activity-type", "exercise",
                "--activity-id", "exercise01", "--plan", "--event-kind",
                "learning_enter", "--learning-span-id", span_id,
                "--evidence-ref", "shadow:learning_enter", "--plan-out", str(enter_path),
            ],
            plan_path=enter_path,
            phase="F_AUTHORIZED",
            prefix="lifecycle.learning_enter",
            plan_assertion="learning_enter_plan_bound",
            apply_assertion="learning_enter_committed",
        )
        exit_path = temp_root / "lifecycle-exit.json"
        plan_and_apply(
            tool=lifecycle_cli,
            plan_argv=[
                sys.executable, "-B", str(lifecycle_cli), "--root", str(shadow),
                "--course-id", "MATH1607H", "--activity-type", "exercise",
                "--activity-id", "exercise01", "--plan", "--event-kind",
                "learning_exit", "--learning-span-id", span_id, "--duration-mode",
                "exact", "--duration-minutes", "25", "--evidence-ref",
                "shadow:learning_exit", "--plan-out", str(exit_path),
            ],
            plan_path=exit_path,
            phase="F_AUTHORIZED",
            prefix="lifecycle.learning_exit",
            plan_assertion="learning_exit_plan_bound",
            apply_assertion="learning_exit_duration_stats_committed",
        )

        prefs_path = temp_root / "close-prefs.json"
        knowledge_path = temp_root / "close-knowledge.json"
        content_path = temp_root / "close-content.json"
        prefs_path.write_text("{}\n", encoding="utf-8")
        knowledge_path.write_text(
            json.dumps(
                [{"topic": "shadow canonical close", "state": "partial"}],
                ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )
        content_path.write_text(
            json.dumps(
                {
                    "problem_review": {"summary": "shadow integrated CLI close"},
                    "student_feedback": {"status": "captured", "reference": "shadow:feedback"},
                },
                ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )

        def close_pending(prefix: str, *, blocker: str | None = None) -> tuple[dict[str, Any], Path]:
            pending_path = temp_root / f"{prefix}-pending.json"
            argv = [
                sys.executable, "-B", str(close_cli), "--root", str(shadow),
                "--course-id", "MATH1607H", "--activity-type", "exercise",
                "--activity-id", "exercise01", "--plan-pending", "--plan-out",
                str(pending_path), "--prefs-json", str(prefs_path),
                "--knowledge-json", str(knowledge_path), "--content-json", str(content_path),
                "--evidence-ref", "shadow:exercise01", "--student-feedback-ref",
                "shadow:feedback",
            ]
            if blocker:
                argv.extend(["--blocker", blocker])
            planned, _ = plan_and_apply(
                tool=close_cli,
                plan_argv=argv,
                plan_path=pending_path,
                phase="F0_PENDING",
                prefix=f"close.{prefix}.pending",
                plan_assertion="pending_body_and_recommendation_bound",
                apply_assertion="pending_close_committed_without_clr",
            )
            return planned, pending_path

        def close_decision(
            prefix: str,
            pending: dict[str, Any],
            decision: str,
            terminal_assertion: str,
        ) -> tuple[dict[str, Any], Path]:
            decision_path = temp_root / f"{prefix}-decision.json"
            details = pending["json"]["details"]
            planned, _ = plan_and_apply(
                tool=close_cli,
                plan_argv=[
                    sys.executable, "-B", str(close_cli), "--root", str(shadow),
                    "--course-id", "MATH1607H", "--activity-type", "exercise",
                    "--activity-id", "exercise01", "--plan-decision", "--plan-out",
                    str(decision_path), "--pending-event-id", details["pending_event_id"],
                    "--body-sha256", details["body_sha256"], "--decision", decision,
                    "--authorization-source-sha256", "a" * 64, "--delegated-quote",
                    "shadow continuous delegation", "--decision-actor", "delegated_operator",
                    "--authorization-mode", "user_continuous_delegation",
                ],
                plan_path=decision_path,
                phase="F_AUTHORIZED",
                prefix=f"close.{prefix}.decision",
                plan_assertion="decision_binds_pending_body_and_authority",
                apply_assertion=terminal_assertion,
            )
            return planned, decision_path

        pending_one, _ = close_pending("completed")
        close_decision(
            "completed",
            pending_one,
            "confirm_completed",
            "completed_clr_and_resume_route_committed",
        )
        reopen_path = temp_root / "close-reopen.json"
        plan_and_apply(
            tool=close_cli,
            plan_argv=[
                sys.executable, "-B", str(close_cli), "--root", str(shadow),
                "--course-id", "MATH1607H", "--activity-type", "exercise",
                "--activity-id", "exercise01", "--plan-reopen", "--plan-out",
                str(reopen_path),
            ],
            plan_path=reopen_path,
            phase="F_AUTHORIZED",
            prefix="close.reopen",
            plan_assertion="reopen_plan_preserves_historical_clr",
            apply_assertion="terminal_activity_reopened_to_ongoing",
        )
        pending_two, _ = close_pending(
            "closed_incomplete", blocker="shadow_required_checkpoint_unresolved"
        )
        close_decision(
            "closed_incomplete",
            pending_two,
            "confirm_closed_incomplete",
            "closed_incomplete_clr_preserves_blocker",
        )

        negative_plan = temp_root / "invalid-lifecycle.json"
        consumer_runs.append(
            expected_failure_run(
                [
                    sys.executable, "-B", str(lifecycle_cli), "--root", str(shadow),
                    "--course-id", "MATH1607H", "--activity-type", "exercise",
                    "--activity-id", "exercise01", "--plan", "--event-kind",
                    "transition", "--to-state", "completed", "--plan-out", str(negative_plan),
                ],
                shadow,
                env,
                run_id="lifecycle.illegal_terminal_transition",
                assertions=["illegal_lifecycle_transition_zero_write"],
                watched_paths=watched_close,
            )
        )
        consumer_runs.append(
            expected_failure_run(
                [sys.executable, "-B", str(close_cli), "--parse-confirm", "OK"],
                shadow,
                env,
                run_id="close.vague_confirmation",
                assertions=["vague_confirmation_rejected_zero_write"],
                watched_paths=watched_close,
            )
        )

        final_specs = (
            (
                "ledger.post_terminal_validate",
                [sys.executable, "-B", str(ledger_cli), "validate", str(math_ledger)],
                ["ledger_replay_valid_after_completed_reopen_closed_incomplete"],
            ),
            (
                "doctor.post_terminal",
                [sys.executable, "-B", str(shadow / "main/70_tools/t2ag_doctor.py")],
                ["doctor_zero_fail_post_terminal"],
            ),
            (
                "state.post_terminal",
                [sys.executable, "-B", str(shadow / "main/70_tools/t2ag_state_refresh.py"), "--check"],
                ["state_zero_drift_post_terminal"],
            ),
            (
                "context.post_terminal",
                [sys.executable, "-B", str(shadow / "main/70_tools/t2ag_context.py"), "--course", "MATH1607H", "--format", "json"],
                ["context_routes_between_activities_and_resume_lesson01"],
            ),
            (
                "activity.post_terminal",
                [sys.executable, "-B", str(shadow / "main/70_tools/t2ag_activity.py"), "--course", "MATH1607H", "--intent", "recover"],
                ["activity_routes_none_with_resume_lesson01"],
            ),
        )
        for run_id, spec, assertions in final_specs:
            run = operational_run(
                spec, shadow, env, run_id=run_id, assertions=assertions
            )
            if run_id == "context.post_terminal" and run["json"]["route"]["current_activity"] != "none":
                raise ShadowError("post-terminal context did not route none")
            if run_id == "activity.post_terminal" and run["json"]["current_activity"] != "none":
                raise ShadowError("post-terminal activity did not route none")
            consumer_runs.append(run)
        consumer_runs.append(
            {
                "run_id": "shadow.exact_plan_full_roundtrip",
                "status": "pass",
                "argv": [
                    sys.executable, "-B", str(Path(__file__).resolve()),
                    "--root", str(root), "--plan-file", str(plan_file),
                    "--report-file", str(report_file.resolve()),
                ],
                "exit_code": 0,
                "assertions": [
                    "exact_shadow_migration_and_runtime_roundtrip_passed",
                    "production_main_untouched",
                ],
            }
        )

        source_after = mig.path_manifest(root, plan["expected_head"].keys())
        overlay_after = mig.candidate_overlay_manifest(root)
        if source_after != source_before:
            raise ShadowError("production source changed during shadow")
        if overlay_after != plan["candidate_overlay_manifest"]:
            raise ShadowError("production candidate overlay changed during shadow")
        report = {
            "schema": "t2ag.022.exact_plan_shadow_report.v1",
            "campaign_id": plan["campaign_id"],
            "status": "pass",
            "assertions_passed": sum(
                len(run.get("assertions") or []) for run in consumer_runs
            ),
            "tool_source_manifest_sha256": plan["executor_manifest"]["sha256"],
            "plan_file": str(plan_file),
            "plan_file_sha256": plan_file_sha,
            "payload_sha256": plan["payload_sha256"],
            "plan_id": plan["plan_id"],
            "transaction_id": plan["transaction_id"],
            "source_manifest_sha256": source_before["sha256"],
            "candidate_overlay_manifest_sha256": overlay_after["sha256"],
            "projected_manifest_sha256": plan["projected_target_manifest"]["sha256"],
            "shadow_root_binding": sha256_bytes(str(shadow.resolve()).encode("utf-8")),
            "cleanup_guard": "shadow parent equals dedicated temp root and name is t2ag-shadow",
            "first_apply": first,
            "second_apply": second,
            "fresh_planner": fresh,
            "consumer_runs": consumer_runs,
        }
        write_exclusive(report_file.resolve(), canonical_bytes(report))
    finally:
        assert_cleanup_target(temp_root, shadow)
        shutil.rmtree(temp_root)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument("--report-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = execute(args.root, args.plan_file, args.report_file)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "status": report["status"],
                "report_file": str(args.report_file.resolve()),
                "report_sha256": sha256_bytes(args.report_file.read_bytes()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
