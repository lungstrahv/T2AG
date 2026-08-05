#!/usr/bin/env python3
"""RD shadow apply: isolated root, real apply, second-run, no Main mutation."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
MAIN = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import migrate_022_activity_close as mig
import activity_close as close
import activity_ledger as ledger
import t2ag_activity as activity
from test_022_migration import write_test_authorization


def _copy_subset(src_root: Path, dst_root: Path) -> None:
    """Copy only contract/runtime + seven courses + A-D tools needed for shadow."""
    clone = subprocess.run(
        ["git", "clone", "--shared", "--quiet", str(src_root), str(dst_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if clone.returncode != 0:
        raise RuntimeError(clone.stdout + clone.stderr)
    rels = [
        "main",
        "cloud",
        "AGENTS.md",
        "CONTEXT.md",
        "README.md",
        "t2ag_directory_guide.html",
    ]
    for rel in rels:
        src = src_root / rel
        dst = dst_root / rel
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(
                src,
                dst,
                ignore=shutil.ignore_patterns(
                    ".venv",
                    "__pycache__",
                    "*.pyc",
                    ".activity_txn",
                    "archives",
                    "ATBS_3e",
                ),
                dirs_exist_ok=True,
            )
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    # minimal git identity so migrator baseline is optional
    # no .git in shadow — migrator allows missing git


def _close_authorization(
    plan_path: Path,
    directory: Path,
    phase: str,
) -> tuple[Path, str]:
    import hashlib

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    payload = {
        "campaign_id": close.CAMPAIGN_ID,
        "phase": phase,
        "authorization_mode": "shadow",
        "authorization_source_sha256": "a" * 64,
        "plan_id": plan["plan_id"],
        "transaction_id": plan["transaction_id"],
        "payload_sha256": plan["payload_sha256"],
    }
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    path = directory / f"close-auth-{phase}.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


class ShadowApplyTests(unittest.TestCase):
    def test_each_postcheck_group_failure_rolls_back(self) -> None:
        if not (MAIN / "main/40_course/MATH1607H/exercises/U1101").is_dir():
            self.skipTest("Main U1101 required")
        points = (
            "projected_state",
            "ledger_replay",
            "fresh_zero",
            "doctor",
            "state",
            "context",
            "recover",
            "pending_replay",
            "postcheck_marker",
            "commit_marker",
            "committed_replay",
        )
        with tempfile.TemporaryDirectory(prefix="t2ag-022-postchecks-") as tmp:
            temp_root = Path(tmp)
            shadow = temp_root / "t2ag"
            _copy_subset(MAIN, shadow)
            plan_path = temp_root / "frozen-plan.json"
            result = mig.materialize_plan_file(MAIN, plan_path)
            auth_path, auth_sha = write_test_authorization(
                plan_path, result, temp_root
            )
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
            auth["authorization_mode"] = "shadow"
            auth_raw = (json.dumps(auth, ensure_ascii=False, sort_keys=True) + "\n").encode()
            auth_path.write_bytes(auth_raw)
            import hashlib
            auth_sha = hashlib.sha256(auth_raw).hexdigest()
            command = [
                sys.executable,
                "-B",
                str(shadow / "main/70_tools/migrate_022_activity_close.py"),
                "--root",
                str(shadow),
                "--apply",
                "--plan-file",
                str(plan_path),
                "--expect-payload-sha",
                result["payload_sha256"],
                "--expect-file-sha",
                result["file_sha256"],
                "--authorization-receipt",
                str(auth_path),
                "--expect-authorization-sha",
                auth_sha,
                "--confirm",
                "E_migration_apply",
            ]
            for point in points:
                with self.subTest(point=point):
                    env = os.environ.copy()
                    env["T2AG_022_ALLOW_APPLY"] = "1"
                    env["T2AG_022_SHADOW_APPLY"] = "1"
                    env["T2AG_022_FAIL_POSTCHECK_AT"] = point
                    env["PYTHONIOENCODING"] = "utf-8"
                    run = subprocess.run(
                        command,
                        cwd=shadow,
                        env=env,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                    )
                    self.assertEqual(run.returncode, 1, msg=point + run.stdout + run.stderr)
                    self.assertIn("rolled back", run.stdout, msg=point)
                    self.assertTrue(
                        (shadow / "main/40_course/MATH1607H/exercises/U1101").is_dir(),
                        msg=point,
                    )
                    self.assertFalse(
                        (shadow / "main/40_course/MATH1607H/exercises/exercise01").exists(),
                        msg=point,
                    )
                    self.assertEqual(
                        len(list((shadow / "main/40_course").glob("*/activity_ledger.md"))),
                        0,
                        msg=point,
                    )
                    recovery = (shadow / ".activity_txn").resolve()
                    self.assertEqual(recovery, shadow.resolve() / ".activity_txn")
                    if recovery.exists():
                        shutil.rmtree(recovery)

    def test_shadow_apply_second_run_and_main_untouched(self) -> None:
        if not (MAIN / "main/40_course/MATH1607H/exercises/U1101").is_dir():
            self.skipTest("Main U1101 required")
        main_u1101_before = sum(
            1
            for p in (MAIN / "main/40_course/MATH1607H/exercises/U1101").rglob("*")
            if p.is_file()
        )
        with tempfile.TemporaryDirectory(prefix="t2ag-022-shadow-") as tmp:
            shadow = Path(tmp) / "t2ag"
            _copy_subset(MAIN, shadow)
            plan_path = Path(tmp) / "frozen-main-plan.json"
            result = mig.materialize_plan_file(MAIN, plan_path)
            self.assertTrue(result["ok"])
            self.assertEqual(result["alias_count"], 8)
            auth_path, auth_sha = write_test_authorization(plan_path, result, Path(tmp))
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
            auth["authorization_mode"] = "shadow"
            auth_raw = (json.dumps(auth, ensure_ascii=False, sort_keys=True) + "\n").encode()
            auth_path.write_bytes(auth_raw)
            import hashlib
            auth_sha = hashlib.sha256(auth_raw).hexdigest()
            command = [
                sys.executable,
                "-B",
                str(shadow / "main/70_tools/migrate_022_activity_close.py"),
                "--root",
                str(shadow),
                "--apply",
                "--plan-file",
                str(plan_path),
                "--expect-payload-sha",
                result["payload_sha256"],
                "--expect-file-sha",
                result["file_sha256"],
                "--authorization-receipt",
                str(auth_path),
                "--expect-authorization-sha",
                auth_sha,
                "--confirm",
                "E_migration_apply",
            ]
            env = os.environ.copy()
            env["T2AG_022_ALLOW_APPLY"] = "1"
            env["T2AG_022_SHADOW_APPLY"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            first = subprocess.run(
                command, cwd=shadow, env=env, capture_output=True, text=True, encoding="utf-8"
            )
            self.assertEqual(first.returncode, 0, msg=first.stdout + first.stderr)
            applied = json.loads(first.stdout)
            self.assertIn(applied["status"], {"committed", "already_committed_verified"})
            self.assertFalse(
                (shadow / "main/40_course/MATH1607H/exercises/U1101").exists()
            )
            self.assertTrue(
                (
                    shadow
                    / "main/40_course/MATH1607H/exercises/exercise01/exercise.md"
                ).is_file()
            )
            # ledger exists for seven courses
            for cid in mig.COURSES:
                self.assertTrue(
                    (shadow / f"main/40_course/{cid}/activity_ledger.md").is_file(),
                    msg=cid,
                )
            # Legacy identifiers remain resolvable only through the
            # course-scoped alias table.  A post-0.2.2 progress pointer may
            # never route through that compatibility namespace directly.
            math_ledger = ledger.load_ledger(
                shadow / "main/40_course/MATH1607H/activity_ledger.md"
            )
            self.assertEqual(
                ledger.resolve_legacy_id(
                    "MATH1607H", "U1101", math_ledger.aliases
                ),
                "exercise01",
            )
            math_progress_path = (
                shadow / "main/40_course/MATH1607H/progress.md"
            )
            canonical_progress_raw = math_progress_path.read_bytes()
            canonical_progress = canonical_progress_raw.decode("utf-8")
            legacy_progress = canonical_progress.replace(
                "current_activity_id: exercise01",
                "current_activity_id: U1101",
                1,
            ).replace(
                "exercises/exercise01/exercise.md",
                "exercises/U1101/exercise.md",
                1,
            )
            math_progress_path.write_bytes(legacy_progress.encode("utf-8"))
            try:
                with self.assertRaises(activity.ActivityContractError) as caught:
                    activity.resolve_activity(shadow, "MATH1607H")
                self.assertIn(
                    "progress 不得直接路由 legacy Exercise",
                    "; ".join(caught.exception.errors),
                )
                legacy_doctor = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(shadow / "main/70_tools/t2ag_doctor.py"),
                    ],
                    cwd=shadow,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertNotEqual(legacy_doctor.returncode, 0)
                self.assertIn(
                    "progress 不得直接路由 legacy Exercise",
                    legacy_doctor.stdout + legacy_doctor.stderr,
                )
            finally:
                math_progress_path.write_bytes(canonical_progress_raw)

            physical_legacy = (
                shadow / "main/40_course/MATH1607H/exercises/U9999"
            )
            physical_legacy.mkdir()
            try:
                physical_doctor = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(shadow / "main/70_tools/t2ag_doctor.py"),
                    ],
                    cwd=shadow,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertNotEqual(physical_doctor.returncode, 0)
                self.assertIn(
                    "习题单元 ID 非法",
                    physical_doctor.stdout + physical_doctor.stderr,
                )
            finally:
                physical_legacy.rmdir()

            # Once any ledger exists, planned courses must expose the full
            # canonical-none frontend.  Exercise Doctor against an actual
            # migrated shadow rather than only testing an in-memory parser.
            planned_path = shadow / "main/40_course/DS1001r/progress.md"
            planned_progress_raw = planned_path.read_bytes()
            planned_progress = planned_progress_raw.decode("utf-8")
            planned_path.write_bytes(
                planned_progress.replace("current_activity_id: none\n", "", 1).encode(
                    "utf-8"
                )
            )
            try:
                planned_doctor = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(shadow / "main/70_tools/t2ag_doctor.py"),
                    ],
                    cwd=shadow,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertNotEqual(planned_doctor.returncode, 0)
                self.assertIn(
                    "planned 课程 canonical-none 非法",
                    planned_doctor.stdout + planned_doctor.stderr,
                )
            finally:
                planned_path.write_bytes(planned_progress_raw)
            # second exact full CLI command path
            second = subprocess.run(
                command, cwd=shadow, env=env, capture_output=True, text=True, encoding="utf-8"
            )
            self.assertEqual(second.returncode, 0, msg=second.stdout + second.stderr)
            again = json.loads(second.stdout)
            self.assertEqual(again["status"], "already_committed_verified")
            # fresh full CLI dry-run has no operations
            fresh_path = Path(tmp) / "fresh-zero-plan.json"
            fresh_run = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(shadow / "main/70_tools/migrate_022_activity_close.py"),
                    "--root",
                    str(shadow),
                    "--dry-run",
                    "--plan-out",
                    str(fresh_path),
                ],
                cwd=shadow,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(fresh_run.returncode, 0, msg=fresh_run.stdout + fresh_run.stderr)
            fresh = json.loads(fresh_run.stdout)
            self.assertEqual(fresh["summary"]["path_ops"], 0)
            self.assertEqual(fresh["summary"]["move_ops"], 0)
            self.assertEqual(fresh["summary"]["write_ops"], 0)
            # F shadow: terminal close carries generated caches in the same
            # transaction and leaves state-refresh at zero drift.
            old_close_test = os.environ.get("T2AG_022_CLOSE_TEST")
            os.environ["T2AG_022_CLOSE_TEST"] = "1"
            try:
                pending_path = Path(tmp) / "close-pending.json"
                pending = close.materialize_pending_plan(
                    shadow,
                    pending_path,
                    course_id="MATH1607H",
                    activity_type="exercise",
                    activity_id="exercise01",
                    prefs={key: "on" for key in close.PREF_KEYS},
                    knowledge=[
                        {
                            "topic": "exercise01 reviewed set",
                            "state": "independent_confirmed",
                        }
                    ],
                    blockers=[],
                    evidence_refs=["attempts/AT0001", "reviews/RV0001"],
                    student_feedback_ref="exercise_thoughts.md",
                )
                pending_auth, pending_auth_sha = _close_authorization(
                    pending_path, Path(tmp), "F0_PENDING"
                )
                close.apply_close_plan(
                    shadow,
                    pending_path,
                    expect_payload_sha=pending["payload_sha256"],
                    expect_file_sha=pending["file_sha256"],
                    authorization_receipt=pending_auth,
                    expect_authorization_sha=pending_auth_sha,
                )
                decision_path = Path(tmp) / "close-decision.json"
                decision = close.materialize_decision_plan(
                    shadow,
                    decision_path,
                    course_id="MATH1607H",
                    activity_type="exercise",
                    activity_id="exercise01",
                    pending_event_id=pending["details"]["pending_event_id"],
                    body_sha256=pending["details"]["body_sha256"],
                    decision="confirm_completed",
                    authorization_source_sha256="a" * 64,
                    delegated_quote="continuous delegation",
                )
                decision_plan = json.loads(decision_path.read_text(encoding="utf-8"))
                self.assertIn("main/00_core/t2ag_memory.md", decision_plan["files"])
                self.assertIn(
                    "main/10_student/profile/learning_path.md",
                    decision_plan["files"],
                )
                decision_auth, decision_auth_sha = _close_authorization(
                    decision_path, Path(tmp), "F_AUTHORIZED"
                )
                close.apply_close_plan(
                    shadow,
                    decision_path,
                    expect_payload_sha=decision["payload_sha256"],
                    expect_file_sha=decision["file_sha256"],
                    authorization_receipt=decision_auth,
                    expect_authorization_sha=decision_auth_sha,
                )
            finally:
                if old_close_test is None:
                    os.environ.pop("T2AG_022_CLOSE_TEST", None)
                else:
                    os.environ["T2AG_022_CLOSE_TEST"] = old_close_test
            state = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(shadow / "main/70_tools/t2ag_state_refresh.py"),
                    "--check",
                ],
                cwd=shadow,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(state.returncode, 0, msg=state.stdout + state.stderr)
            progress_after_close_raw = math_progress_path.read_bytes()
            progress_after_close = progress_after_close_raw.decode("utf-8")
            progress_meta, _, _ = close.frontmatter_split(progress_after_close)
            self.assertEqual(
                {
                    key: progress_meta[key]
                    for key in (
                        "current_activity",
                        "current_activity_id",
                        "resume_path",
                        "activity_position",
                        "next_action_kind",
                        "next_activity_type",
                        "next_activity_id",
                    )
                },
                {
                    "current_activity": "none",
                    "current_activity_id": "none",
                    "resume_path": "none",
                    "activity_position": "between_activities",
                    "next_action_kind": "resume",
                    "next_activity_type": "lesson",
                    "next_activity_id": "lesson01",
                },
            )
            next_lines = re.findall(
                r"(?m)^-\s+\*\*(?:下一步计划|下一步|下次第一件事)\*\*[：:]\s*(.+)$",
                progress_after_close,
            )
            self.assertEqual(
                next_lines,
                ["resume lesson:lesson01；以结构化 next_action_* 字段为准。"],
            )
            current_match = re.search(
                r"(?ms)^## 二、当前进度\s*(.*?)(?=^---\s*$|^##\s|\Z)",
                progress_after_close,
            )
            self.assertIsNotNone(current_match)
            current_slice = current_match.group(1)
            self.assertNotIn("活动仍为 `ongoing`", current_slice)
            self.assertNotIn("没有 Exercise 单元正式结课流程", current_slice)
            self.assertNotIn("P-0044", current_slice)
            memory_after_close = (
                shadow / "main/00_core/t2ag_memory.md"
            ).read_text(encoding="utf-8")
            active_match = re.search(
                r"(?s)<!-- T2AG_GENERATED:ACTIVE_PROGRESS:START -->(.*?)"
                r"<!-- T2AG_GENERATED:ACTIVE_PROGRESS:END -->",
                memory_after_close,
            )
            self.assertIsNotNone(active_match)
            active_memory = active_match.group(1)
            self.assertIn("MATH1607H none none，between_activities", active_memory)
            self.assertIn("resume lesson:lesson01", active_memory)
            self.assertNotIn("exercise01", active_memory)
            context = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(shadow / "main/70_tools/t2ag_context.py"),
                    "--course",
                    "MATH1607H",
                    "--format",
                    "json",
                ],
                cwd=shadow,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(context.returncode, 0, msg=context.stdout + context.stderr)
            context_packet = json.loads(context.stdout)
            self.assertEqual(context_packet["route"]["current_activity"], "none")
            self.assertEqual(context_packet["route"]["current_activity_id"], "none")
            progress_selections = [
                item
                for item in context_packet["selections"]
                if item["source"] == "main/40_course/MATH1607H/progress.md"
                and item["label"] == "进度真相源当前切片"
            ]
            self.assertEqual(len(progress_selections), 1)
            selected_progress = progress_selections[0]["content"]
            self.assertIn("resume lesson:lesson01", selected_progress)
            self.assertNotIn("活动仍为 `ongoing`", selected_progress)
            self.assertNotIn("没有 Exercise 单元正式结课流程", selected_progress)
            self.assertNotIn("P-0044", selected_progress)
            doctor = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(shadow / "main/70_tools/t2ag_doctor.py"),
                ],
                cwd=shadow,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(doctor.returncode, 0, msg=doctor.stdout + doctor.stderr)

            # The Doctor must reject a stale narrative even when the
            # structured fields and ledger are internally valid.
            math_progress_path.write_bytes(
                progress_after_close.replace(
                    "- **下一步计划**：resume lesson:lesson01；以结构化 next_action_* 字段为准。",
                    "- **下一步计划**：confirm_close exercise:exercise01；以结构化 next_action_* 字段为准。",
                    1,
                ).encode("utf-8")
            )
            try:
                stale_doctor = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(shadow / "main/70_tools/t2ag_doctor.py"),
                    ],
                    cwd=shadow,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertNotEqual(stale_doctor.returncode, 0)
                self.assertIn(
                    "progress 正文 next action 与结构化字段漂移",
                    stale_doctor.stdout + stale_doctor.stderr,
                )
            finally:
                math_progress_path.write_bytes(progress_after_close_raw)
            duplicate = progress_after_close.replace(
                "- **下一步计划**：resume lesson:lesson01；以结构化 next_action_* 字段为准。",
                "- **下一步计划**：resume lesson:lesson01；以结构化 next_action_* 字段为准。\n"
                "- **下一步计划**：confirm_close exercise:exercise01",
                1,
            )
            math_progress_path.write_bytes(duplicate.encode("utf-8"))
            try:
                duplicate_doctor = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(shadow / "main/70_tools/t2ag_doctor.py"),
                    ],
                    cwd=shadow,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertNotEqual(duplicate_doctor.returncode, 0)
                self.assertIn("actual_count=2", duplicate_doctor.stdout)
            finally:
                math_progress_path.write_bytes(progress_after_close_raw)
            # Main untouched
            self.assertTrue(
                (MAIN / "main/40_course/MATH1607H/exercises/U1101").is_dir()
            )
            self.assertFalse(
                (MAIN / "main/40_course/MATH1607H/exercises/exercise01").exists()
            )
            main_u1101_after = sum(
                1
                for p in (MAIN / "main/40_course/MATH1607H/exercises/U1101").rglob("*")
                if p.is_file()
            )
            self.assertEqual(main_u1101_before, main_u1101_after)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
