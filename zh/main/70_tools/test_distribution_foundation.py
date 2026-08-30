#!/usr/bin/env python3
"""Atomic contracts for the validation foundation shared by all distributions."""
from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sys
import tempfile
import unittest
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

    def test_release_audit_helper_keeps_profile_sensitive_line_endings(self) -> None:
        """NEGATIVE: absorbing the release ID must not erase its release-only sweep."""
        workflow = doctor.load_doctor_workflow()
        expected_ids = [
            "runtime.line_endings",
            *workflow["profiles"]["release"]["checks"],
        ]
        with mock.patch.object(doctor, "execute_doctor_checks") as execute:
            doctor.run_release_audit_checks()

        execute.assert_called_once()
        rows = execute.call_args.args[0]
        self.assertEqual([row["id"] for row in rows], expected_ids)
        self.assertTrue(execute.call_args.kwargs["include_release_parity"])

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

    def test_doctor_changed_selector_schema_and_corpus(self) -> None:
        workflow = doctor.load_doctor_workflow()
        # 66 -> 62: DEC-0a-2 four-way merge (2026-08-26)
        self.assertEqual(len(workflow["doctor_checks"]), 62)
        self.assertTrue(all(
            isinstance(spec["path_prefixes"], list) and spec["path_prefixes"]
            for spec in workflow["doctor_checks"].values()
        ))

        course = doctor.build_changed_doctor_plan(
            workflow,
            ["main/40_course/AIF1001r/lessons/lesson01/lesson01.md"],
        )
        self.assertIn("runtime.structure", course["selected"])
        self.assertIn("runtime.course_discovery", course["selected"])
        self.assertIn("runtime.gate_ledger", course["selected"])

        core = doctor.build_changed_doctor_plan(
            workflow,
            ["main/00_core/t2ag_changelog.md"],
        )
        self.assertIn("runtime.changelog", core["selected"])

        union = doctor.build_changed_doctor_plan(
            workflow,
            [
                "main/40_course/AIF1001r/lessons/lesson01/lesson01.md",
                "main/00_core/t2ag_changelog.md",
            ],
        )
        self.assertEqual(len(union["selected"]), len(set(union["selected"])))
        self.assertEqual(
            union["selected"],
            [
                check_id
                for check_id in workflow["profiles"]["runtime"]["checks"]
                if check_id in set(union["selected"])
            ],
        )

        tools = doctor.build_changed_doctor_plan(
            workflow,
            ["main/70_tools/t2ag_test.py"],
        )
        self.assertNotIn("runtime.groups", tools["selected"])
        self.assertNotIn("runtime.changelog", tools["selected"])

        empty = doctor.build_changed_doctor_plan(workflow, [])
        always = [
            check_id
            for check_id in workflow["profiles"]["runtime"]["checks"]
            if workflow["doctor_checks"][check_id]["path_prefixes"] == ["*"]
        ]
        expected_empty = validation_control.build_doctor_plan(
            workflow,
            profile="runtime",
            requested_checks=always,
        )
        self.assertEqual(
            empty["selected"],
            [row["id"] for row in expected_empty["checks"]],
        )
        with self.assertRaises(validation_control.ValidationControlError):
            doctor.build_changed_doctor_plan(workflow, ["unregistered/path.xyz"])

    # --- DEC-0a-2 / C8: four-way merge contracts -------------------------

    MERGED = {
        "runtime.line_budget": ("check_line_budget",
                                ("runtime.memory_budget", "runtime.constitution_budget")),
        "runtime.line_endings": ("check_line_endings",
                                 ("release.line_endings",)),
        "runtime.stale_identifiers": ("check_stale_identifiers",
                                      ("runtime.legacy_references",
                                       "runtime.retired_instance_ids")),
        "runtime.decision_records": ("check_decision_records",
                                     ("runtime.decision_record_citations",)),
    }

    def test_merged_check_ids_replace_their_members(self) -> None:
        """POSITIVE + NEGATIVE: survivors registered, absorbed members gone.

        A merge that leaves an absorbed ID behind is not a merge, it is a fork:
        the registry would schedule both and the corroborating assertions would
        keep passing against a name nothing dispatches.
        """
        checks = doctor.load_doctor_workflow()["doctor_checks"]
        for survivor, (handler, absorbed) in self.MERGED.items():
            self.assertIn(survivor, checks, f"survivor missing: {survivor}")
            self.assertEqual(checks[survivor]["handler"], handler)
            for gone in absorbed:
                self.assertNotIn(gone, checks, f"absorbed member still registered: {gone}")

    def test_merged_path_prefixes_are_inherited_as_a_union(self) -> None:
        """NEGATIVE: an intersection, or keeping only one member's prefixes, silently under-selects.

        This is the quietest way for the merge to go wrong: every run stays green
        because the check simply is not selected for the paths the absorbed member
        used to own.
        """
        checks = doctor.load_doctor_workflow()["doctor_checks"]
        budget = checks["runtime.line_budget"]["path_prefixes"]
        self.assertIn("main/00_core/", budget,
                      "memory carrier prefix lost in the merge")
        self.assertIn("main/t2ag.md", budget,
                      "constitution carrier prefix lost in the merge")
        for wildcard in ("runtime.line_endings", "runtime.stale_identifiers",
                         "runtime.decision_records"):
            self.assertEqual(checks[wildcard]["path_prefixes"], ["*"],
                             f"{wildcard} must keep the union wildcard")

    def test_merged_selection_never_shrinks_against_changed_paths(self) -> None:
        """NEGATIVE: --changed must still select the survivor for every member's paths."""
        workflow = doctor.load_doctor_workflow()
        cases = {
            "main/t2ag.md": "runtime.line_budget",
            "main/00_core/t2ag_memory.md": "runtime.line_budget",
            "main/50_playbook/git_workflow.md": "runtime.line_endings",
            "main/00_core/domain_model.md": "runtime.decision_records",
        }
        for path, expected in cases.items():
            plan = doctor.build_changed_doctor_plan(workflow, [path])
            selected = {str(row["id"]) for row in plan["checks"]}
            self.assertIn(expected, selected,
                          f"{expected} dropped out of the selection for {path}")

    def test_doctor_atom_set_sha_matches_the_merged_registry(self) -> None:
        """POSITIVE: the anchor value C10 must publish is computed, not copied.

        check_changelog_contract recomputes this on every runtime sweep and warns
        when the changelog's declared value drifts, so a stale n=66 / 50300baa...
        would surface as "状态漂移无记录" instead of a hard failure.
        """
        checks = doctor.load_doctor_workflow()["doctor_checks"]
        identifiers = sorted(checks)
        self.assertEqual(len(identifiers), 62,
                         "four-way merge must take the atom set from 66 to 62")
        digest = hashlib.sha256("\n".join(identifiers).encode("utf-8")).hexdigest()
        self.assertEqual(len(digest), 64)
        self.assertNotEqual(
            digest,
            "50300baa" + digest[8:],
            "atom set sha must change when the identifier set changes",
        )

    def test_verdict_semantics_and_ledger_are_written_down(self) -> None:
        """POSITIVE + NEGATIVE: the two-layer verdict must exist as prose, and be honest.

        Negative half: the depreciation thresholds must carry their own
        "no data source" caveat.  Publishing thresholds that nothing computes is
        how a rule turns into a slogan -- the exact failure EV-0020 recorded.
        """
        contracts_text = (REPO / "main/50_playbook/doctor_contracts.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("verdict", contracts_text.lower())
        for token in ("`act`", "`reason`", "checker_defect", "not_applicable",
                      "env_waiver", "known_debt", "paused"):
            self.assertIn(token, contracts_text, f"verdict vocabulary missing: {token}")
        self.assertIn("eligible_entries", contracts_text,
                      "depreciation thresholds must declare they have no data source")

        ledger = REPO / "main/00_core/t2ag_verdict_ledger.md"
        self.assertTrue(ledger.is_file(), "verdict ledger was not created")
        ledger_text = ledger.read_text(encoding="utf-8")
        for field in ("check_id", "object", "act", "reason", "verdict_at",
                      "verdict_by", "object_fingerprint", "checker_version",
                      "wake_condition"):
            self.assertIn(field, ledger_text, f"ledger field missing: {field}")
        self.assertIn("复利回路·部件", ledger_text,
                      "ledger must declare its loop-component role")

    def test_doctor_path_prefixes_fail_closed_and_fprime_is_bounded(self) -> None:
        workflow = doctor.load_doctor_workflow()
        broken = json.loads(json.dumps(workflow))
        broken["doctor_checks"]["runtime.gate_ledger"].pop("path_prefixes")
        with tempfile.TemporaryDirectory() as folder:
            workflow_path = Path(folder) / "workflow.json"
            workflow_path.write_text(
                json.dumps(broken, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaises(validation_control.ValidationControlError):
                doctor.load_doctor_workflow(workflow_path)

            window_path = Path(folder) / "selection_window.json"
            plan = doctor.build_changed_doctor_plan(
                workflow,
                ["main/40_course/AIF1001r/course.md"],
            )
            for index in range(6):
                doctor.record_changed_selection(
                    plan,
                    startup_id=f"maintenance-{index}",
                    eligible_for_depreciation=False,
                    path=window_path,
                )
            first = json.loads(window_path.read_text(encoding="utf-8"))
            self.assertEqual(first["schema"], doctor.DOCTOR_SELECTION_SCHEMA)
            self.assertEqual(first["eligible_entries"], [])
            self.assertEqual(len(first["recent_ineligible"]), 5)

            doctor.record_changed_selection(
                plan,
                startup_id="shared-id",
                eligible_for_depreciation=False,
                path=window_path,
            )
            doctor.record_changed_selection(
                plan,
                startup_id="shared-id",
                eligible_for_depreciation=True,
                path=window_path,
            )
            self.assertFalse(doctor.record_changed_selection(
                plan,
                startup_id="shared-id",
                eligible_for_depreciation=True,
                path=window_path,
            ))
            for index in range(15):
                doctor.record_changed_selection(
                    plan,
                    startup_id=f"startup-{index}",
                    eligible_for_depreciation=True,
                    path=window_path,
                )
            second = json.loads(window_path.read_text(encoding="utf-8"))
            self.assertEqual(len(second["eligible_entries"]), 15)
            self.assertLessEqual(len(second["recent_ineligible"]), 5)
            self.assertEqual(
                sum(
                    entry["startup_id"] == "shared-id"
                    for entry in second["eligible_entries"]
                ),
                0,
            )
            self.assertFalse(doctor.record_changed_selection(
                plan,
                startup_id="startup-14",
                eligible_for_depreciation=True,
                path=window_path,
            ))

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
        marker_assertions.assert_states_rule(
            self, startup, "CTX-PACKET-005", name="startup_orchestration.md"
        )
        marker_assertions.assert_states_rule(
            self, startup, "CTX-PACKET-006", name="startup_orchestration.md"
        )
        for marker in (
            "Startup Formation",
            "Task Assist Budget",
            "learning-ready",
            "recovery-settled",
        ):
            self.assertIn(marker, startup)
        self.assertIn("一分钟启动与 Agent 偏好", (REPO / "README.md").read_text(encoding="utf-8"))

    def test_startup_entry_contract_has_no_implicit_teach_fallback(self) -> None:
        constitution = (REPO / "main/t2ag.md").read_text(encoding="utf-8")
        startup = (REPO / "main/50_playbook/startup_orchestration.md").read_text(encoding="utf-8")
        agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        for token in ("entry.teach", "entry.maintain", "entry.audit", "entry.release"):
            self.assertIn(token, constitution)
            self.assertIn(token, startup)
        self.assertNotIn("每次进入本项目", constitution)
        self.assertIn("缺 token 时 fail closed", constitution)
        self.assertIn("四入口共用前缀只有三项", startup)
        self.assertIn("只有 `entry.teach`", startup)

    def test_release_projection_rules_have_one_operational_owner(self) -> None:
        constitution = (REPO / "main/t2ag.md").read_text(encoding="utf-8")
        owner = (REPO / "main/50_playbook/playbook_management.md").read_text(encoding="utf-8")
        flow = (REPO / "main/50_playbook/t2ag_flow.md").read_text(encoding="utf-8")
        self.assertIn("playbook_management.md` §五", constitution)
        self.assertIn("发行投影纪律（唯一操作 owner）", owner)
        self.assertIn("machine-query artifact manifest", owner)
        self.assertIn("**0.2.5**", owner)
        self.assertIn("发行投影 owner", flow)
        self.assertNotIn("Main ↔ Skeleton", flow)
        self.assertNotIn("`cmp` 逐一核对", flow)

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
            "Doctor/测试基础结构",
            "--profile runtime",
            "--profile release",
            "validation_workflow.json",
            "validation_flow.md",
            "只读",
        ):
            self.assertIn(marker, sync_lite.LITE_README + sync_lite.LITE_AGENTS)
        self.assertIn("不得在 Lite 执行", sync_lite.LITE_AGENTS)
        self.assertIn("docs/adr", sync_lite.LITE_README)
        self.assertIn("只读审查", sync_lite.LITE_README)

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

    def test_handoffs_are_not_shipped_to_lite_and_absence_speaks(self) -> None:
        """P-0071 (W3)：收窄后 Lite 不随行 handoff，且缺席必须发声。

        这条守的不是「投影为零」——它本来就是零。守的是**零不再沉默**：旧实现悄悄投
        了个空集，再生与校验全绿，缺席不可见，最后靠外部审查者肉眼发现（F4）。所以断言
        分两半：清单里确实没有 handoff，且每次再生都打印边界行。
        """
        src = REPO
        dst = REPO.parent / "t2ag-lite"
        if not dst.is_dir():
            self.skipTest("t2ag-lite not beside main")
        projected = [
            label for label, _, _ in sync_lite.projection_manifest(src, dst)
        ]
        self.assertEqual(
            [rel for rel in projected if rel.startswith("docs/handoffs")],
            [],
            "P-0071 收窄后不得再有任何 handoff 进入 Lite 投影",
        )
        line = sync_lite.report_handoff_boundary()
        self.assertIn("not shipped", line)
        self.assertIn("P-0071", line)
        source = (REPO / "main/70_tools/sync_lite.py").read_text(encoding="utf-8")
        self.assertEqual(
            source.count("print(report_handoff_boundary())"),
            2,
            "写入路径与 check-only 路径都必须播报，少一条就有沉默分支",
        )
        self.assertNotIn(
            "_CONSTITUTION_HANDOFFS",
            source,
            "宪法六份的投影职责已撤除；残留名单会让读者以为承诺还在",
        )

    def test_version_ledger_anchors_resolve_at_workspace_root(self) -> None:
        """P-0071 (W3)：台账里的六份权威锚必须真的能解析开，且 SHA 对得上。

        F4 报的是「SHA 锚指向不可得文件」。修的是路径不是锚——所以这里既验路径存在，
        也验 SHA 仍然字节对齐；只改路径而锚早已漂移，那是另一种假绿。
        """
        ledger = (REPO / "main/60_journal/t2ag_version_ledger.md").read_text(
            encoding="utf-8"
        )
        workspace = REPO.parent
        anchors = re.findall(r"`<workspace>/(docs/handoffs/[^`]+\.md)`", ledger)
        self.assertGreaterEqual(len(anchors), 6, "六份权威锚一份都不能少")
        for rel in set(anchors):
            self.assertTrue(
                (workspace / rel).is_file(),
                msg=f"版本台账锚不可解析：{rel}（P-0071 F4 复发）",
            )
        shas = re.findall(
            r"`<workspace>/(docs/handoffs/[^`]+\.md)`，SHA-256\s*\n?\s*`([0-9a-f]{64})`",
            ledger,
        )
        self.assertGreaterEqual(len(shas), 2, "带 SHA 的锚至少两份（0.2.1/0.2.2 review）")
        for rel, expected in shas:
            actual = hashlib.sha256((workspace / rel).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, msg=f"{rel} SHA 漂移")
        self.assertIn("不随 Lite 发行", ledger)

    def test_cache_eviction_clause_is_homologous_main_skeleton(self) -> None:
        """EV-0012 CacheEviction must exist in self and match sibling byte-for-byte."""
        relative = "main/50_playbook/batch_workorder_spec.md"
        self_path = REPO / relative
        self.assertTrue(self_path.is_file(), msg=f"missing {relative} in {REPO.name}")

        sister = None
        for candidate in ("t2ag", "t2ag-skeleton"):
            sibling = REPO.parent / candidate
            if sibling != REPO and (sibling / relative).is_file():
                sister = sibling
                break
        self.assertIsNotNone(sister, msg="no sibling distribution with batch_workorder_spec.md")
        sister_path = sister / relative

        self_text = self_path.read_text(encoding="utf-8")
        sister_text = sister_path.read_text(encoding="utf-8")
        for marker in (
            "#### 1.2.1 CacheEviction",
            "EV-0012",
            "book/.cache/**",
            "不构成 RT3",
            "仍为 RT3",
            "working_pages",
            "0.2.2",
        ):
            self.assertIn(marker, self_text)
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

    # --- changelog 读写机制三判据（changelog_management.md §3b.3）---
    # One positive and one negative example each.  The negatives must fail for the
    # judgement's own reason, not incidentally, so each pair differs in exactly the
    # property under test.

    TEMPLATED_ENTRY_BODY = (
        "\n"
        "- **change**：66 个 atom 新增必填 `path_prefixes[]`。\n"
        "- **reason**：把小改动从全量税中解耦。\n"
        "- **validation_entry**：测试计划 SHA `abc123`；\n"
        "  读数见 `workspace:docs/handoffs/T2AG_SOME_REPORT_2026-08-25.md`。\n"
        "\n"
        "#### 锚定断言（必填）\n"
        "\n"
        "- runtime checks = 46\n"
    )

    def test_changelog_template_gaps_positive_and_negative(self) -> None:
        self.assertEqual(doctor.changelog_template_gaps(self.TEMPLATED_ENTRY_BODY), [])

        without_validation = self.TEMPLATED_ENTRY_BODY.replace(
            "- **validation_entry**：", "- 验证：", 1
        )
        self.assertEqual(
            doctor.changelog_template_gaps(without_validation),
            ["validation_entry"],
        )

    def test_changelog_campaign_granularity_positive_and_negative(self) -> None:
        def entry(campaign: str, date: str) -> dict[str, str]:
            title = f"{campaign} · 一句话标题（不升版）"
            return {
                "date": date,
                "title": title,
                "heading": f"## [{date}] {title}",
                "body": self.TEMPLATED_ENTRY_BODY,
            }

        single = [entry("DEC-0a-3", "2026-08-25"), entry("DEC-0a-1", "2026-08-25")]
        self.assertEqual(doctor.changelog_campaign_duplicates(single), [])

        # Negative: the same campaign split into two entries within one day —
        # exactly the "逐 action 落痕" form 写-粒度 forbids.
        split = [entry("DEC-0a-3", "2026-08-25"), entry("DEC-0a-3", "2026-08-25")]
        self.assertEqual(
            doctor.changelog_campaign_duplicates(split),
            [
                "## [2026-08-25] DEC-0a-3 · 一句话标题（不升版）",
                "## [2026-08-25] DEC-0a-3 · 一句话标题（不升版）",
            ],
        )

        # Positive, and the reason the scan surface is same-date: a campaign that
        # appends again on a later day is legitimate continuation.  A whole-file
        # scan would convict it with no remedy — editing the earlier entry is
        # barred by hard rule 4.  EV-0034 is the real precedent.
        continued = [entry("EV-0034", "2026-08-25"), entry("EV-0034", "2026-08-24")]
        self.assertEqual(doctor.changelog_campaign_duplicates(continued), [])

    def test_changelog_receipt_locatability_positive_and_negative(self) -> None:
        report_path = "workspace:docs/handoffs/T2AG_SOME_REPORT_2026-08-25.md"
        self.assertEqual(
            doctor.changelog_receipt_paths(self.TEMPLATED_ENTRY_BODY),
            [report_path],
        )
        self.assertEqual(
            doctor.unlocatable_changelog_receipts(
                self.TEMPLATED_ENTRY_BODY, lambda candidate: True
            ),
            [],
        )
        self.assertEqual(
            doctor.unlocatable_changelog_receipts(
                self.TEMPLATED_ENTRY_BODY, lambda candidate: False
            ),
            [report_path],
        )
        # Tri-state: None means "outside the judgement surface" and must not be
        # confused with "missing".  Folding the two together is what would make a
        # shipped Skeleton — which carries no workspace handoff root — light up.
        self.assertEqual(
            doctor.unlocatable_changelog_receipts(
                self.TEMPLATED_ENTRY_BODY, lambda candidate: None
            ),
            [],
        )
        # A validation_entry that names no path at all yields no object to judge,
        # so it yields no finding either.
        pathless = self.TEMPLATED_ENTRY_BODY.replace(
            "  读数见 `workspace:docs/handoffs/T2AG_SOME_REPORT_2026-08-25.md`。\n",
            "  读数见施工报告。\n",
            1,
        )
        self.assertEqual(doctor.changelog_receipt_paths(pathless), [])
        self.assertEqual(
            doctor.unlocatable_changelog_receipts(
                pathless, lambda candidate: False
            ),
            [],
        )

    def test_changelog_receipt_regex_returns_whole_carrier_token(self) -> None:
        """§2.6.7: the receipt token comes back whole, carrier prefix included.

        This is the one assertion that catches the `findall()` trap: a pattern
        with groups makes findall return *group contents*, so a naive inner
        capturing group would silently truncate every receipt to `workspace` or
        to the bare path — and the bare path is exactly the ambiguity the carrier
        syntax exists to remove.  The judgement would keep passing while judging
        the wrong string.
        """
        body = (
            "- **validation_entry**：读数见 "
            "`workspace:docs/handoffs/T2AG_SOME_REPORT_2026-08-25.md`、"
            "`repo:main/70_tools/validation_workflow.json` 与 `docs/handoffs/BARE.md`。\n"
        )
        self.assertEqual(
            doctor.changelog_receipt_paths(body),
            [
                "workspace:docs/handoffs/T2AG_SOME_REPORT_2026-08-25.md",
                "repo:main/70_tools/validation_workflow.json",
                "docs/handoffs/BARE.md",
            ],
        )
        self.assertEqual(
            doctor.split_receipt_carrier(
                "workspace:docs/handoffs/T2AG_SOME_REPORT_2026-08-25.md"
            ),
            ("workspace", "docs/handoffs/T2AG_SOME_REPORT_2026-08-25.md"),
        )
        self.assertEqual(
            doctor.split_receipt_carrier("docs/handoffs/BARE.md"),
            (None, "docs/handoffs/BARE.md"),
        )

    def test_changelog_receipt_carrier_judgement_table(self) -> None:
        """判据三 real-carrier binding: every cell of the §3b.3 table, no lambdas.

        The defect this replaces was a fail-open prefix rule that made the same
        `docs/handoffs/` path mean True when present and None when misspelt — so
        neither a real receipt nor a typo was ever judged.  Explicit carriers
        therefore fail closed, and the only surviving exemption is an unmounted
        workspace root, which is asserted against a synthetic root below rather
        than described.
        """
        # repo: — present / absent / escaping.
        self.assertIs(
            doctor.resolve_receipt_in_repo(f"repo:{doctor.CHANGELOG_REL}"), True
        )
        self.assertIs(
            doctor.resolve_receipt_in_repo("repo:main/70_tools/no_such_receipt.md"),
            False,
        )
        self.assertIs(doctor.resolve_receipt_in_repo("repo:../outside/x.md"), False)

        # workspace: — the live evidence root is mounted in the development tree.
        self.assertIsNotNone(doctor.workspace_evidence_root())
        self.assertIs(
            doctor.resolve_receipt_in_repo(
                f"workspace:{doctor.CHANGELOG_WORKSPACE_ROOT_MARKER}"
            ),
            True,
        )
        self.assertIs(
            doctor.resolve_receipt_in_repo(
                "workspace:docs/handoffs/T2AG_NO_SUCH_REPORT_2026-08-25.md"
            ),
            False,
        )
        self.assertIs(
            doctor.resolve_receipt_in_repo("workspace:../../outside/x.md"), False
        )

        # Bare path — names neither root, so it cannot be resolved at all.
        self.assertIs(doctor.resolve_receipt_in_repo(doctor.CHANGELOG_REL), False)
        self.assertIs(
            doctor.resolve_receipt_in_repo("docs/handoffs/README.md"), False
        )

        # workspace: with the evidence root **not** mounted → the one exemption.
        # A shipped Skeleton / Lite / EN unpacks exactly like this, and judging it
        # would manufacture cross-repo false signals.  Mount detection is by
        # canonical marker, so an empty same-named directory must not count.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw).resolve()
            (tmp / "t2ag").mkdir()
            with self._doctor_root(tmp / "t2ag"):
                self.assertIsNone(doctor.workspace_evidence_root())
                self.assertIsNone(
                    doctor.resolve_receipt_in_repo("workspace:docs/handoffs/X.md")
                )
                # Bare directory, no marker: still unmounted.
                (tmp / "docs" / "handoffs").mkdir(parents=True)
                self.assertIsNone(doctor.workspace_evidence_root())
                self.assertIsNone(
                    doctor.resolve_receipt_in_repo("workspace:docs/handoffs/X.md")
                )
                # Marker present → mounted, and now judged.
                (tmp / doctor.CHANGELOG_WORKSPACE_ROOT_MARKER).write_text(
                    "# handoff index\n", encoding="utf-8"
                )
                self.assertEqual(doctor.workspace_evidence_root(), tmp)
                self.assertIs(
                    doctor.resolve_receipt_in_repo("workspace:docs/handoffs/X.md"),
                    False,
                )

        # End to end on the live changelog: the latest entry's own receipt
        # pointers, resolved for real, must not produce a finding.
        text = (REPO / doctor.CHANGELOG_REL).read_text(encoding="utf-8")
        latest = doctor.parse_changelog_entries(text)[0]
        self.assertEqual(
            doctor.unlocatable_changelog_receipts(
                latest["body"], doctor.resolve_receipt_in_repo
            ),
            [],
        )

    @contextlib.contextmanager
    def _doctor_root(self, root: Path):
        """Point the doctor module at another tree for the duration of a block."""
        original = doctor.ROOT
        doctor.ROOT = root
        try:
            yield
        finally:
            doctor.ROOT = original

    @staticmethod
    def _run_changelog_contract() -> list[tuple[str, str]]:
        """Call the real check with ``report()`` captured instead of accumulated."""
        captured: list[tuple[str, str]] = []
        original = doctor.report
        doctor.report = lambda level, message: captured.append((level, message))
        try:
            doctor.check_changelog_contract()
        finally:
            doctor.report = original
        return captured

    def test_check_changelog_contract_judges_the_real_receipt(self) -> None:
        """Integration: the gate itself, not just its helpers.

        Until this batch every judgement test called a pure helper, and
        `check_changelog_contract` had zero callers in the tree — so a resolver
        that never returned False could not be caught by the suite.  This drives
        the assembled gate over the live carrier and over an injected typo.
        """
        # Real carrier, real receipt → the gate is silent.
        self.assertEqual(self._run_changelog_contract(), [])

        text = (REPO / doctor.CHANGELOG_REL).read_text(encoding="utf-8")
        # The receipt under test is the LATEST entry's own pointer, read out of
        # the carrier -- never a literal.  Binding this fixture to one campaign's
        # file name makes every later batch fail here for no reason: on
        # 2026-08-26 it did, the moment DEC-0a-2 appended its entry above
        # DEC-0a-3's and the staged tree was still seeded with DEC-0a-3's receipt.
        latest_entry = doctor.parse_changelog_entries(text)[0]
        pointers = re.findall(r"workspace:(\S+?\.md)", latest_entry["body"])
        self.assertEqual(len(pointers), 1, msg=pointers)
        real = pointers[0]
        typo = real[: -len(".md")] + "_TYPO.md"
        self.assertIn(f"workspace:{real}", text)

        def stage(root: Path, changelog: str, *, marker: bool, receipt: str) -> None:
            (root / "t2ag" / "main" / "00_core").mkdir(parents=True)
            (root / "t2ag" / doctor.CHANGELOG_REL).write_text(
                changelog, encoding="utf-8"
            )
            (root / "docs" / "handoffs").mkdir(parents=True)
            if marker:
                (root / doctor.CHANGELOG_WORKSPACE_ROOT_MARKER).write_text(
                    "# handoff index\n", encoding="utf-8"
                )
            if receipt:
                (root / receipt).write_text("# receipt\n", encoding="utf-8")

        # Mounted root, receipt present → still silent, on a synthetic tree.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw).resolve()
            stage(tmp, text, marker=True, receipt=real)
            with self._doctor_root(tmp / "t2ag"):
                self.assertEqual(self._run_changelog_contract(), [])

        # Mounted root, receipt misspelt → exactly one WARN naming the path.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw).resolve()
            stage(tmp, text.replace(real, typo, 1), marker=True, receipt=real)
            with self._doctor_root(tmp / "t2ag"):
                findings = self._run_changelog_contract()
        self.assertEqual(len(findings), 1, msg=findings)
        level, message = findings[0]
        self.assertEqual(level, "WARN")
        self.assertIn(f"workspace:{typo}", message)
        self.assertNotIn(real, message)

        # Bare path (carrier dropped) → WARN, and the message says how to fix it.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw).resolve()
            stage(
                tmp,
                text.replace(f"workspace:{real}", real, 1),
                marker=True,
                receipt=real,
            )
            with self._doctor_root(tmp / "t2ag"):
                findings = self._run_changelog_contract()
        self.assertEqual(len(findings), 1, msg=findings)
        self.assertEqual(findings[0][0], "WARN")
        self.assertIn(real, findings[0][1])
        self.assertIn("repo:", findings[0][1])
        self.assertIn("workspace:", findings[0][1])

        # Unmounted evidence root (a shipped distribution) → zero false signals,
        # even though the very same pointer is unresolvable there.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw).resolve()
            stage(tmp, text, marker=False, receipt="")
            with self._doctor_root(tmp / "t2ag"):
                self.assertEqual(self._run_changelog_contract(), [])

        # No receipt path at all → no object to judge, so no finding.  This is
        # the X 位 ruling the amendment kept: "no path" must not become a WARN.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw).resolve()
            stage(
                tmp,
                text.replace(f"`workspace:{real}`", "施工报告", 1),
                marker=True,
                receipt="",
            )
            with self._doctor_root(tmp / "t2ag"):
                self.assertEqual(self._run_changelog_contract(), [])

        # Guard against silence for the wrong reason: drop the field itself and
        # the gate must speak again.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw).resolve()
            stage(
                tmp,
                text.replace("- **validation_entry**：", "- 验证：", 1),
                marker=True,
                receipt=real,
            )
            with self._doctor_root(tmp / "t2ag"):
                findings = self._run_changelog_contract()
        self.assertEqual(len(findings), 1, msg=findings)
        self.assertIn("validation_entry", findings[0][1])

    def test_changelog_mechanism_binds_to_the_real_carrier(self) -> None:
        """Same-batch checker and carrier: run the judgements on the real file.

        Synthetic bodies above cover the branch matrix; this one proves the parser
        still lands on the live changelog rather than only on hand-shaped strings.
        """
        text = (REPO / doctor.CHANGELOG_REL).read_text(encoding="utf-8")
        entries = doctor.parse_changelog_entries(text)
        self.assertTrue(entries)
        latest = entries[0]
        self.assertIsNotNone(doctor.changelog_campaign_id(latest["title"]))
        self.assertEqual(doctor.changelog_campaign_duplicates(entries), [])
        self.assertEqual(doctor.changelog_template_gaps(latest["body"]), [])

    def test_changelog_read_write_mechanism_is_written_down(self) -> None:
        rules = (REPO / "main/50_playbook/changelog_management.md").read_text(
            encoding="utf-8"
        )
        for pointer in (
            "handoff_management.md` §5.4",
            "handoff_management.md` §八",
            "lesson_recover.md` §二",
        ):
            self.assertIn(pointer, rules)
        for field in doctor.CHANGELOG_TEMPLATE_FIELDS:
            self.assertIn(field, rules)

        workflow = json.loads(
            (TOOLS / "validation_workflow.json").read_text(encoding="utf-8")
        )
        self.assertIn(
            "main/50_playbook/changelog_management.md",
            workflow["doctor_checks"]["runtime.changelog"]["path_prefixes"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
