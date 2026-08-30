#!/usr/bin/env python3
"""Atomic contracts for the validation foundation shared by all distributions."""
from __future__ import annotations

import sys
import tempfile
import unittest
import re
from pathlib import Path
from unittest import mock


TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import sync_lite
import marker_assertions
import t2ag_doctor as doctor
import t2ag_test as selector
import validation_control


# LV-5: one definition, in doctor, so every sibling-comparison test resolves the
# edition identically.  See `doctor.edition_language` for why parity is
# asserted within an edition and never across two.
edition_language = doctor.edition_language


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
            self, startup, "CTX-PACKET-005", name="startup_orchestration.md"
        )
        marker_assertions.assert_states_rule(
            self, startup, "CTX-PACKET-006", name="startup_orchestration.md"
        )
        # Literals that are identifiers, not prose, stay exact.
        for marker in (
            "Startup Formation",
            "Task Assist Budget",
            "learning-ready",
            "recovery-settled",
        ):
            self.assertIn(marker, startup)
        self.assertIn(
            "Startup formation and construction-helper budget are different things",
            (REPO / "README.md").read_text(encoding="utf-8"),
        )

    def test_startup_entry_contract_has_no_implicit_teach_fallback(self) -> None:
        constitution = (REPO / "main/t2ag.md").read_text(encoding="utf-8")
        startup = (REPO / "main/50_playbook/startup_orchestration.md").read_text(encoding="utf-8")
        for token in ("entry.teach", "entry.maintain", "entry.audit", "entry.release"):
            self.assertIn(token, constitution)
            self.assertIn(token, startup)
        self.assertNotIn("On every entry to this project", constitution)
        self.assertIn("a missing token fails closed", constitution)
        self.assertIn("the prefix shared by the four entries contains only three items", startup)
        self.assertIn("only `entry.teach`", startup)

    def test_release_projection_rules_have_one_operational_owner(self) -> None:
        constitution = (REPO / "main/t2ag.md").read_text(encoding="utf-8")
        owner = (REPO / "main/50_playbook/playbook_management.md").read_text(encoding="utf-8")
        flow = (REPO / "main/50_playbook/t2ag_flow.md").read_text(encoding="utf-8")
        self.assertIn("playbook_management.md` §5", constitution)
        self.assertIn("Release-projection discipline (the sole operating owner)", owner)
        self.assertIn("machine-query artifact manifest", owner)
        self.assertIn("**0.2.5**", owner)
        self.assertIn("release-projection owner", flow)
        self.assertNotIn("Main ↔ Skeleton", flow)
        self.assertNotIn("cmp for byte parity", flow)

    def test_release_projection_mutations_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-dec4-lite-") as temporary:
            root = Path(temporary)
            source = root / "src" / "rule.md"
            target = root / "dst" / "rule.md"
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            source.write_text("canonical\n", encoding="utf-8")
            target.write_text("canonical\n", encoding="utf-8")
            projected = [("rule.md", source, target)]
            self.assertEqual(
                sync_lite.verify_projection(root / "src", root / "dst", projected), 0
            )
            target.write_text("mutated\n", encoding="utf-8")
            self.assertGreater(
                sync_lite.verify_projection(root / "src", root / "dst", projected), 0
            )

        with tempfile.TemporaryDirectory(prefix="t2ag-dec4-privacy-") as temporary:
            skeleton = Path(temporary)
            leak = skeleton / "main/50_playbook/leak.md"
            leak.parent.mkdir(parents=True)
            leak.write_text("C:\\Users\\FixtureMaintainer\\private\n", encoding="utf-8")
            with (
                mock.patch.object(doctor, "ROOT", skeleton),
                mock.patch.object(doctor, "MAIN", skeleton / "main"),
                mock.patch.object(doctor, "FLAVOR", "skeleton"),
                mock.patch.object(doctor, "fails", []),
                mock.patch.object(doctor, "warns", []),
                mock.patch.object(doctor, "infos", []),
            ):
                doctor.check_skeleton_privacy()
                self.assertTrue(any("leak.md" in finding for finding in doctor.fails))

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
