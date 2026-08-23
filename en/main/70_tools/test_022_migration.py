#!/usr/bin/env python3
"""Hardened migration tests: plan binding, fidelity, txn apply on fixtures."""
from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_ledger as ledger
import migrate_022_activity_close as mig
import t2ag_doctor as doctor
from migration_test_support import write_test_authorization


class ProductionAuthorizationBoundaryTests(unittest.TestCase):
    def test_released_022_production_apply_entry_is_retired(self) -> None:
        self.assertFalse(mig.PRODUCTION_MIGRATION_APPLY_ENABLED)
        with tempfile.TemporaryDirectory(prefix="t2ag-022-retired-") as tmp:
            root = Path(tmp) / "t2ag"
            root.mkdir()
            with patch.object(mig, "PRODUCTION_ROOT", root.resolve()):
                with self.assertRaisesRegex(mig.MigrateError, "entry is retired"):
                    mig.validate_apply_authorization(
                        root,
                        {},
                        authorization_receipt=root / "delegated-receipt.json",
                        expect_authorization_sha="0" * 64,
                    )


class PlanDryRunMainTests(unittest.TestCase):
    def test_porcelain_first_row_preserves_status_columns_and_path(self) -> None:
        """The first dirty path must not lose its first character."""
        with tempfile.TemporaryDirectory(prefix="t2ag-022-porcelain-") as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()

            def git(*args: str) -> None:
                subprocess.run(
                    ["git", *args],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )

            git("init")
            git("config", "user.email", "t2ag-test@example.invalid")
            git("config", "user.name", "T2AG Test")
            agents = repo / "AGENTS.md"
            agents.write_text("baseline\n", encoding="utf-8")
            git("add", "AGENTS.md")
            git("commit", "-m", "baseline")
            agents.write_text("changed\n", encoding="utf-8")

            porcelain = mig.campaign.git(repo, "status", "--porcelain=v1", "-uall")
            self.assertEqual(porcelain, " M AGENTS.md")
            manifest = mig.candidate_overlay_manifest(repo)
            self.assertEqual(
                manifest["rows"],
                [
                    {
                        "path": "AGENTS.md",
                        "status": " M",
                        "kind": "file",
                        "bytes": agents.stat().st_size,
                        "sha256": mig.sha256_file(agents),
                    }
                ],
            )

    def test_course_template_tree_exact_allowlist(self) -> None:
        """Main and Skeleton ship one exact, non-recursive template tree."""
        sibling_name = "t2ag-skeleton" if ROOT.name == "t2ag" else "t2ag"
        sibling = ROOT.parent / sibling_name
        if not sibling.is_dir():
            self.skipTest("workspace sibling distribution absent")
        # LV-5: byte parity holds within one language edition, not across two.
        if doctor.edition_language(sibling) != doctor.edition_language(ROOT):
            self.skipTest("workspace sibling is a different language edition")
        local_base = ROOT / "main/40_course/_templates/course"
        sibling_base = sibling / "main/40_course/_templates/course"

        def relative_files(base: Path) -> set[str]:
            return {
                path.relative_to(base).as_posix()
                for path in base.rglob("*")
                if path.is_file()
            }

        local = relative_files(local_base)
        other = relative_files(sibling_base)
        self.assertEqual(local, other)
        for rel in local:
            self.assertEqual(
                hashlib.sha256((local_base / rel).read_bytes()).hexdigest(),
                hashlib.sha256((sibling_base / rel).read_bytes()).hexdigest(),
                msg=f"template content mirror drift: {rel}",
            )
            parts = Path(rel).parts
            self.assertFalse(
                any(left == right for left, right in zip(parts, parts[1:])),
                msg=f"recursive placeholder directory survived: {rel}",
            )

    def test_active_templates_do_not_create_legacy_exercises(self) -> None:
        """Compatibility prose may mention Udddd; creation syntax may not."""
        roots = (
            ROOT / "main/40_course/_templates",
            ROOT / "main/50_playbook",
        )
        forbidden = (
            re.compile(r"exercises[/\\]U\d{4}"),
            re.compile(r"(?m)^exercise_id:\s*U\d{4}\s*$"),
            re.compile(r"(?m)^current_activity_id:\s*U\d{4}\s*$"),
            re.compile(r"(?m)^\s*[-*]\s+U\d{4}-Q\d{3}\b"),
        )
        for base in roots:
            for path in base.rglob("*"):
                if not path.is_file() or "_retired_Udddd" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8-sig")
                for pattern in forbidden:
                    self.assertIsNone(
                        pattern.search(text),
                        msg=f"active legacy creation syntax: {path} / {pattern.pattern}",
                    )
        self.assertFalse(
            (ROOT / "main/40_course/_templates/course/exercises/Udddd").exists()
        )

    def test_dry_run_utf8_immutable_and_unique_aliases(self) -> None:
        if not (ROOT / "main/40_course/MATH1607H/exercises/U1101").is_dir():
            self.skipTest("Main fixture U1101 not present (skeleton)")
        with tempfile.TemporaryDirectory(prefix="t2ag-022-plan-") as tmp:
            plan_path = Path(tmp) / "plan.json"
            result = mig.materialize_plan_file(ROOT, plan_path)
            self.assertTrue(result["ok"])
            raw = plan_path.read_bytes()
            self.assertFalse(raw.startswith(b"\xff\xfe"))
            self.assertEqual(raw.decode("utf-8").encode("utf-8"), raw)
            plan = json.loads(raw.decode("utf-8"))
            self.assertEqual(plan["payload_sha256"], result["payload_sha256"])
            self.assertEqual(result["file_sha256"], mig.sha256_bytes(raw))
            self.assertEqual(plan["alias_count"], 8)
            legs = [a["legacy_id"] for a in plan["aliases"]]
            self.assertEqual(len(legs), len(set(legs)))
            self.assertIn("U1101", legs)
            for q in range(1, 8):
                self.assertIn(f"U1101-Q{q:03d}", legs)
            # ledger embedded sha matches body
            for cid, text in plan["ledgers"].items():
                self.assertEqual(
                    mig.sha256_text(text), plan["ledger_sha256"][cid], msg=cid
                )
                self.assertEqual(ledger.parse_ledger_text(text).validate(), [])
            # U1101 untouched
            self.assertTrue(
                (ROOT / "main/40_course/MATH1607H/exercises/U1101").is_dir()
            )
            self.assertFalse(
                (ROOT / "main/40_course/MATH1607H/exercises/exercise01").exists()
            )

    def test_progress_position_preserved_in_plan(self) -> None:
        if not (ROOT / "main/40_course/MATH1607H/progress.md").is_file():
            self.skipTest("no MATH1607H")
        original = (ROOT / "main/40_course/MATH1607H/progress.md").read_text(
            encoding="utf-8"
        )
        import re

        m = re.search(r"(?m)^activity_position:\s*(.+)$", original)
        self.assertIsNotNone(m)
        pos = m.group(1).strip()
        with tempfile.TemporaryDirectory(prefix="t2ag-022-pos-") as tmp:
            plan_path = Path(tmp) / "plan.json"
            mig.materialize_plan_file(ROOT, plan_path)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            updated = plan["progress_full"][
                "main/40_course/MATH1607H/progress.md"
            ]
            m2 = re.search(r"(?m)^activity_position:\s*(.+)$", updated)
            self.assertIsNotNone(m2)
            self.assertEqual(m2.group(1).strip(), pos)

    def test_review_status_not_stripped_in_plan(self) -> None:
        if not (ROOT / "main/40_course/MATH1607H/exercises/U1101/reviews/RV0001.md").is_file():
            self.skipTest("no RV0001")
        with tempfile.TemporaryDirectory(prefix="t2ag-022-rv-") as tmp:
            plan_path = Path(tmp) / "plan.json"
            mig.materialize_plan_file(ROOT, plan_path)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            rel = "main/40_course/MATH1607H/exercises/exercise01/reviews/RV0001.md"
            if rel not in plan["files"]:
                # no rewrite planned is also OK if content unchanged except paths
                return
            text = plan["files"][rel]
            self.assertRegex(text, r"(?m)^status:\s*")
            self.assertIn("status: amended", text)
            self.assertIn("## exercise01-Q003", text)
            self.assertIn("`U1101-Q003(2)`", text)

    def test_planned_progress_gains_canonical_none_frontend(self) -> None:
        path = ROOT / "main/40_course/DS1001r/progress.md"
        if not path.is_file():
            self.skipTest("Main planned-course fixture absent")
        with tempfile.TemporaryDirectory(prefix="t2ag-022-planned-") as tmp:
            plan_path = Path(tmp) / "plan.json"
            mig.materialize_plan_file(ROOT, plan_path)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            text = plan["progress_full"][
                "main/40_course/DS1001r/progress.md"
            ]
            self.assertNotIn("current_lesson:", text)
            self.assertNotIn("truth_source:", text)
            self.assertIn("current_activity: none", text)
            self.assertIn("current_activity_id: none", text)
            self.assertIn("resume_path: none", text)
            self.assertIn("activity_position: between_activities", text)
            self.assertIn("next_action_kind: none", text)

    def test_apply_requires_hash_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-022-bind-") as tmp:
            plan_path = Path(tmp) / "plan.json"
            if not (ROOT / "main/40_course/MATH1607H/exercises/U1101").is_dir():
                self.skipTest("Main only")
            mig.materialize_plan_file(ROOT, plan_path)
            with self.assertRaises(mig.MigrateError):
                mig.apply_plan(
                    ROOT,
                    plan_path,
                    expect_payload_sha="0" * 64,
                    expect_file_sha="0" * 64,
                    confirm="E_migration_apply",
                    authorization_receipt=plan_path,
                    expect_authorization_sha="0" * 64,
                )


class FixtureApplyTests(unittest.TestCase):
    def test_apply_via_transaction_with_rollback_safety(self) -> None:
        """Copy a minimal course tree and apply bound plan through txn."""
        with tempfile.TemporaryDirectory(prefix="t2ag-022-apply-") as tmp:
            root = Path(tmp) / "t2ag"
            course = root / "main/40_course/DEMO"
            ex = course / "exercises/U1101"
            ex.mkdir(parents=True)
            def w(path: Path, text: str) -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode("utf-8"))

            w(
                ex / "exercise.md",
                "---\ntype: exercise\ncourse_id: DEMO\nexercise_id: U1101\nstatus: ongoing\n---\n# body U1101-Q001 prose stays\n",
            )
            w(
                ex / "problems.md",
                "---\ntype: exercise_problem_set\ncourse_id: DEMO\nexercise_id: U1101\n"
                "source_order: [U1101-Q001]\nteaching_sequence: [U1101-Q001]\nstatus: closed\n---\n"
                "# set\n\n## U1101-Q001\n\n- 题号：U1101-Q001\n- 状态：closed\n",
            )
            w(
                ex / "reviews/RV0001.md",
                "---\ntype: exercise_review\ncourse_id: DEMO\nexercise_id: U1101\n"
                "review_id: RV0001\nproblem_ids: [U1101-Q001]\nstatus: recorded\n---\n"
                "# RV\n\n## U1101-Q001\n\n- 结果：correct\n",
            )
            w(
                course / "progress.md",
                "---\ntype: course_progress\ncourse_id: DEMO\nlifecycle_status: ongoing\n"
                "course_driver: goal\ntruth_source: true\ncurrent_activity: exercise\n"
                "current_activity_id: U1101\ncurrent_lesson: none\n"
                "resume_path: main/40_course/DEMO/exercises/U1101/exercise.md\n"
                "activity_position: exact-demo-position-must-keep\n"
                "updated: 2026-08-05\ncurrent_completion_node: N1\n"
                "current_checkpoint: C1\ncheckpoint_state: confirmed\n---\n# p\n",
            )
            w(
                course / "activity_map.md",
                "---\ntype: course_activity_map\ncourse_id: DEMO\n---\n"
                "| content_group_id | source_scope | lesson_ids | exercise_ids |\n"
                "|---|---|---|---|\n| DEMO-B001-C01-S01 | x |  | U1101 |\n",
            )
            # monkeypatch COURSES for this fixture
            old = mig.COURSES
            mig.COURSES = ["DEMO"]
            try:
                plan_path = Path(tmp) / "plan.json"
                result = mig.materialize_plan_file(root, plan_path)
                auth_path, auth_sha = write_test_authorization(
                    plan_path, result, Path(tmp)
                )
                self.assertEqual(result["alias_count"], 2)  # U1101 + U1101-Q001
                os.environ["T2AG_022_ALLOW_APPLY"] = "1"
                os.environ["T2AG_022_SHADOW_APPLY"] = "1"
                try:
                    applied = mig.apply_plan(
                        root,
                        plan_path,
                        expect_payload_sha=result["payload_sha256"],
                        expect_file_sha=result["file_sha256"],
                        confirm="E_migration_apply",
                        authorization_receipt=auth_path,
                        expect_authorization_sha=auth_sha,
                    )
                finally:
                    os.environ.pop("T2AG_022_ALLOW_APPLY", None)
                    os.environ.pop("T2AG_022_SHADOW_APPLY", None)
                self.assertIn(applied["status"], {"committed", "already_committed_verified"})
                self.assertFalse((course / "exercises/U1101").exists())
                self.assertTrue((course / "exercises/exercise01/exercise.md").is_file())
                rv = (course / "exercises/exercise01/reviews/RV0001.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("status: recorded", rv)
                self.assertIn("## exercise01-Q001", rv)
                # free prose in exercise body may keep U1101-Q001
                ex_body = (course / "exercises/exercise01/exercise.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("U1101-Q001 prose stays", ex_body)
                self.assertNotRegex(ex_body, r"(?m)^status:\s*")
                prog = (course / "progress.md").read_text(encoding="utf-8")
                self.assertIn("exact-demo-position-must-keep", prog)
                self.assertIn("exercise01", prog)
                problems = (course / "exercises/exercise01/problems.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("status: closed", problems)
                self.assertIn("exercise_id: exercise01", problems)
                # second-run no path ops
                second = mig.build_write_set(root)
                self.assertEqual(second["summary"]["path_ops"], 0)
            finally:
                mig.COURSES = old


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
