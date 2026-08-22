#!/usr/bin/env python3
"""Atomic contracts for the validation foundation shared by all distributions."""
from __future__ import annotations

import sys
import unittest
import re
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import sync_lite
import marker_assertions
import t2ag_doctor as doctor
import t2ag_test as selector
import validation_control


def edition_language(tree: Path) -> str:
    """Which language edition a distribution tree is, from its constitution.

    LV-5 (2026-08-20): byte parity is asserted *within* a language edition, never
    across two.  A translated edition is a fourth distribution, and demanding it be
    byte-identical to the zh-CN one is not a contract anyone can satisfy -- it would
    make a correctly-built English tree permanently red for the one reason that is
    intended.  Parity still has teeth: it holds between same-edition siblings, and
    the marker assertions below hold in every edition.
    """
    constitution = tree / "main/t2ag.md"
    if not constitution.is_file():
        return "unknown"
    text = constitution.read_text(encoding="utf-8", errors="replace")
    if re.search(r"^##\s+Preface\b", text, re.MULTILINE):
        return "en"
    if re.search(r"^##\s+序\b", text, re.MULTILINE):
        return "zh-CN"
    return "unknown"


class DistributionFoundationTests(unittest.TestCase):
    def test_base_validation_files_are_present(self) -> None:
        missing = [
            relative
            for relative in doctor.BASE_VALIDATION_FILES
            if not (REPO / relative).is_file()
        ]
        self.assertEqual(missing, [])

    def test_doctor_profiles_are_split_and_runtime_is_default(self) -> None:
        self.assertEqual(doctor.parse_args([]).profile, "runtime")
        self.assertEqual(doctor.parse_args(["--profile", "release"]).profile, "release")
        self.assertIsNot(doctor.run_runtime_checks, doctor.run_release_audit_checks)

    def test_control_file_composes_atomic_doctor_plans(self) -> None:
        workflow = validation_control.load_workflow()
        runtime = validation_control.build_doctor_plan(
            workflow,
            profile="runtime",
            requested_checks=[],
        )
        release = validation_control.build_doctor_plan(
            workflow,
            profile="release",
            requested_checks=[],
        )
        targeted = validation_control.build_doctor_plan(
            workflow,
            profile="runtime",
            requested_checks=["runtime.memory_pointers"],
        )
        runtime_ids = [row["id"] for row in runtime["checks"]]
        release_ids = [row["id"] for row in release["checks"]]
        targeted_ids = [row["id"] for row in targeted["checks"]]
        self.assertEqual(release_ids[:len(runtime_ids)], runtime_ids)
        self.assertTrue(all(row["phase"] == "runtime" for row in runtime["checks"]))
        self.assertIn("release.dirty_tree", release_ids)
        self.assertEqual(
            targeted_ids,
            [
                "runtime.structure",
                "runtime.course_discovery",
                "runtime.teacher_contract",
                "runtime.memory_pointers",
            ],
        )
        self.assertFalse(targeted["claimable_profile_result"])

    def test_test_plans_are_bound_by_budget_and_release_guards(self) -> None:
        manifest = selector.load_manifest(TOOLS / "test_dependencies.json")
        workflow = validation_control.load_workflow()
        narrow = selector.build_plan(
            manifest,
            workflow,
            requested_components=[],
            requested_test_ids=["foundation.structure", "doctor.postcheck"],
            changed_paths=[],
            tier="fast",
        )
        wide = selector.build_plan(
            manifest,
            workflow,
            requested_components=[],
            requested_test_ids=[
                "foundation.structure",
                "contracts.runtime",
                "contracts.activity",
                "doctor.postcheck",
            ],
            changed_paths=[],
            tier="fast",
        )
        release = selector.build_plan(
            manifest,
            workflow,
            requested_components=["release_suite"],
            requested_test_ids=[],
            changed_paths=[],
            tier="release_only",
        )
        self.assertTrue(narrow["ordinary_budget"]["within_budget"])
        self.assertFalse(wide["ordinary_budget"]["within_budget"])
        self.assertTrue(release["plan_only_required"])
        self.assertTrue(release["release_execution_requires_reason"])

    def test_manifest_registers_distribution_foundation(self) -> None:
        manifest = selector.load_manifest(TOOLS / "test_dependencies.json")
        component = manifest["components"]["distribution_foundation"]
        self.assertIn("foundation.structure", component["tests"])
        self.assertIn("main/70_tools/sync_lite.py", component["sources"])
        startup = manifest["components"]["startup_orchestration"]
        self.assertEqual(
            startup["tests"],
            ["foundation.structure", "contracts.runtime", "context.packet"],
        )
        self.assertIn("main/50_playbook/startup_orchestration.md", startup["sources"])
        release_suite = manifest["components"]["release_suite"]
        self.assertTrue(release_suite["aggregate"])
        self.assertTrue(release_suite["plan_only"])
        self.assertEqual(release_suite["sources"], [])

    def test_startup_formation_is_distinct_from_task_assist_budget(self) -> None:
        workflow = validation_control.load_workflow()
        self.assertEqual(workflow["ordinary_budget"]["max_agents"], 1)
        profile = (REPO / "main/10_student/profile/profile.md").read_text(encoding="utf-8-sig")
        for marker in (
            "agent_collaboration_schema: agent_collaboration_preferences.v1",
            "agent_pool_limit: 6",
            "agent_max_active: 3",
            "agent_parallel_startup: enabled",
            "agent_startup_readiness: learning_ready_first",
            "agent_background_reporting: blockers_only",
        ):
            self.assertIn(marker, profile)
        startup = (REPO / "main/50_playbook/startup_orchestration.md").read_text(encoding="utf-8")
        # Registered prose markers resolve through the registry: asserting the zh-CN
        # literal here would bypass MARKER_VARIANTS exactly as the gates once did, and
        # a translated edition would fail on a document that states the rule (L3).
        marker_assertions.assert_states_rule(
            self, startup, "先建依赖树，再分配 Agent", name="startup_orchestration.md"
        )
        marker_assertions.assert_states_rule(
            self, startup, "不得只展示 ID/SHA 让学生盲签", name="startup_orchestration.md"
        )
        # Literals that are identifiers, not prose, stay exact.
        for marker in (
            "Startup Formation",
            "Task Assist Budget",
            "learning-ready",
            "recovery-settled",
        ):
            self.assertIn(marker, startup)
        self.assertIn("One-minute startup and agent preferences", (REPO / "README.md").read_text(encoding="utf-8"))

    def test_lite_keeps_foundation_as_read_only_audit_content(self) -> None:
        for marker in (
            "doctor/test base structure",
            "--profile runtime",
            "--profile release",
            "validation_workflow.json",
            "validation_flow.md",
            "read-only",
        ):
            self.assertIn(marker, sync_lite.LITE_README + sync_lite.LITE_AGENTS)
        self.assertIn("Do not execute", sync_lite.LITE_AGENTS)
        self.assertIn("docs/adr", sync_lite.LITE_README)
        self.assertIn("read-only review material", sync_lite.LITE_README)

    def test_decision_docs_are_in_lite_projection_manifest(self) -> None:
        """Active ADR/protocol paths referenced by tests must project to Lite."""
        src = REPO
        dst = REPO.parent / "t2ag-lite"
        if not dst.is_dir():
            self.skipTest("t2ag-lite not beside main")
        projected = {
            label for label, _, _ in sync_lite.projection_manifest(src, dst)
        }
        required = [
            "docs/adr/README.md",
            "docs/adr/0001-textbook-source-assets-and-bounded-cache.md",
            "docs/adr/0002-host-controlled-textbook-teaching-egress.md",
            "docs/protocol/host-teaching-egress-api.md",
            "docs/protocol/textbook-scope-scan-admission.md",
        ]
        for rel in required:
            self.assertTrue((src / rel).is_file(), msg=f"main missing {rel}")
            self.assertIn(rel, projected, msg=f"{rel} not in Lite projection rules")

    def test_cache_eviction_clause_is_homologous_main_skeleton(self) -> None:
        """EV-0012 CacheEviction must exist in self and match sibling byte-for-byte."""
        relative = "main/50_playbook/batch_workorder_spec.md"
        self_path = REPO / relative
        self.assertTrue(self_path.is_file(), msg=f"missing {relative} in {REPO.name}")

        self_text = self_path.read_text(encoding="utf-8")
        mine = edition_language(REPO)

        # The clause must be present in EVERY edition; only its spelling varies.
        for marker in (
            "#### 1.2.1 CacheEviction",
            "EV-0012",
            "book/.cache/**",
            ("不构成 RT3", "does not constitute an RT3"),
            ("仍为 RT3", "Still RT3"),
            "working_pages",
            "0.2.2",
        ):
            spellings = (marker,) if isinstance(marker, str) else marker
            self.assertTrue(
                any(sp in self_text for sp in spellings),
                msg=f"CacheEviction clause missing {spellings[0]!r} in {REPO.name}",
            )

        # Byte parity is asserted only against a sibling of the SAME language edition.
        sister = None
        for candidate in ("t2ag", "t2ag-skeleton", "t2ag-skeleton-en"):
            sibling = REPO.parent / candidate
            if (
                sibling != REPO
                and (sibling / relative).is_file()
                and edition_language(sibling) == mine
            ):
                sister = sibling
                break
        if sister is None:
            self.skipTest(
                f"no same-edition ({mine}) sibling holding {relative}; "
                "cross-edition byte parity is not a satisfiable contract"
            )
        sister_text = (sister / relative).read_text(encoding="utf-8")
        self.assertEqual(
            self_text,
            sister_text,
            msg=f"batch_workorder_spec.md {REPO.name}/{sister.name} must be homologous",
        )

        manifest = selector.load_manifest(TOOLS / "test_dependencies.json")
        self.assertIn(
            relative,
            manifest["components"]["workorder_governance"]["sources"],
        )
        self.assertIn(
            relative,
            manifest["components"]["distribution_foundation"]["sources"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
