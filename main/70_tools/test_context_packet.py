#!/usr/bin/env python3
"""Regression checks for the read-only learning context packet."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

import t2ag_context as context
from t2ag_activity import resolve_activity


def write_utf8(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


class HeadingSelectionTests(unittest.TestCase):
    def test_section_stops_at_same_or_higher_heading(self) -> None:
        sample = (
            "# Root\n\n"
            "## Alpha\n\n"
            "alpha\n\n"
            "### Child\n\n"
            "child\n\n"
            "## Beta\n\n"
            "beta\n"
        )
        selected = context.section(sample, "Alpha", level=2)
        self.assertIn("alpha", selected)
        self.assertIn("### Child", selected)
        self.assertNotIn("## Beta", selected)

    def test_missing_required_section_fails(self) -> None:
        with self.assertRaises(context.ContextPacketError):
            context.section("# Root\n", "Missing", level=2)

    def test_initialized_requires_hint_gate_choice(self) -> None:
        memory = "## 上次课摘要\n\n- **日期**：2026-08-01\n"
        unresolved = (
            "---\ninitialization_status: initialized\n"
            "exercise_hint_gate: ask\n---\n"
        )
        resolved = unresolved.replace(
            "exercise_hint_gate: ask", "exercise_hint_gate: enabled"
        )
        self.assertFalse(context.initialized(unresolved, memory))
        self.assertTrue(context.initialized(resolved, memory))


class SourceSnapshotTests(unittest.TestCase):
    def test_digest_uses_original_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            raw = b"\xef\xbb\xbfalpha\r\nbeta\r\n"
            source.write_bytes(raw)
            cache = context.SourceCache(root)

            self.assertEqual(cache.read(source), "alpha\nbeta\n")
            self.assertEqual(
                cache.digest(source),
                hashlib.sha256(raw).hexdigest(),
            )

    def test_activity_router_uses_same_cache_and_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course_root = root / "main/40_course/TEST100"
            progress_path = course_root / "progress.md"
            carrier_path = course_root / "exercises/U0001/exercise.md"
            problems_path = course_root / "exercises/U0001/problems.md"
            progress = (
                "---\n"
                "type: course_progress\n"
                "course_id: TEST100\n"
                "lifecycle_status: ongoing\n"
                "course_driver: goal\n"
                "truth_source: true\n"
                "current_activity: exercise\n"
                "current_activity_id: U0001\n"
                "current_lesson: none\n"
                "resume_path: main/40_course/TEST100/exercises/U0001/exercise.md\n"
                "activity_position: start\n"
                "---\n"
            )
            write_utf8(progress_path, progress)
            write_utf8(
                carrier_path,
                "---\n"
                "type: exercise\n"
                "course_id: TEST100\n"
                "exercise_id: U0001\n"
                "---\n",
            )
            write_utf8(
                problems_path,
                "---\n"
                "type: exercise_problem_set\n"
                "course_id: TEST100\n"
                "exercise_id: U0001\n"
                "---\n",
            )
            cache = context.SourceCache(root)
            progress_content = cache.read(progress_path)
            snapshot = context.ProgressSnapshot(
                path=progress_path,
                content=progress_content,
                meta=context.frontmatter_text(progress_content),
            )

            route = context.resolve_activity(
                root,
                "TEST100",
                snapshot=snapshot,
                reader=cache.read,
            )
            self.assertEqual(route.activity_id, "U0001")

            problems_path.write_bytes(
                cache.read_bytes(problems_path) + b"\nchanged\n"
            )
            with self.assertRaisesRegex(
                context.ContextPacketError,
                "changed during packet build",
            ):
                cache.assert_unchanged()

    def test_teacher_router_uses_same_cache_and_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            teacher_root = root / "main/20_teacher"
            overlay = teacher_root / "overlay.md"
            teacher = teacher_root / "T001.md"
            write_utf8(
                overlay,
                "# Overlay\n\n"
                "## 课程—教师映射\n\n"
                "| 课程代码 | 课程名称 | 教师模板 | 教师风格 |\n"
                "|---|---|---|---|\n"
                "| TEST100 | Test | `main/20_teacher/T001.md` | strict |\n"
                "| (默认) | Default | `main/20_teacher/T001.md` | strict |\n",
            )
            write_utf8(
                teacher,
                "---\n"
                "type: teacher_template\n"
                "template_id: T001\n"
                "---\n",
            )
            cache = context.SourceCache(root)
            teacher_paths = cache.glob(teacher_root, "T*.md")
            mapping = context.resolve_teacher_mapping(
                root,
                reader=cache.read,
                teacher_paths=teacher_paths,
            )
            self.assertEqual(mapping["TEST100"][0], "T001")

            teacher.write_bytes(cache.read_bytes(teacher) + b"\nchanged\n")
            with self.assertRaisesRegex(
                context.ContextPacketError,
                "changed during packet build",
            ):
                cache.assert_unchanged()


class TextbookWindowTests(unittest.TestCase):
    @staticmethod
    def route() -> SimpleNamespace:
        return SimpleNamespace(
            activity_type="lesson",
            course_driver="textbook",
            activity_id="lesson01",
            resume_path=(
                "main/40_course/TEST100/lessons/lesson01/lesson01.md"
            ),
        )

    def test_textbook_lesson_without_preparation_returns_none(self) -> None:
        """Without preparation Snapshot, textbook_lesson_window returns None (legacy retired)."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = context.SourceCache(root)
            progress_path = root / "main/40_course/TEST100/progress.md"
            snapshot = context.ProgressSnapshot(
                path=progress_path,
                content="",
                meta={},
            )
            # No preparation → returns None, not an error
            result = context.textbook_lesson_window(
                cache,
                snapshot,
                self.route(),
            )
            self.assertIsNone(result)

    def test_invalid_snapshot_does_not_fallback_to_legacy(self) -> None:
        # Post-S3 defense: working_pages 目录创建仅用于验证不回退 legacy
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lesson = root / "main/40_course/TEST100/lessons/lesson01"
            working = lesson / "working_pages/source_excerpt.md"
            write_utf8(
                working,
                "# Excerpt\n\n"
                + "\n\n".join(
                    f"## 第 {page} 页\n\npage {page}"
                    for page in (9, 10, 11, 12)
                )
                + "\n",
            )
            prep = lesson / "preparation"
            write_utf8(
                prep / "PREP-deadbeefdeadbeef.json",
                json.dumps(
                    {
                        "schema": "t2ag.lesson_preparation_snapshot.v1",
                        "snapshot_id": "PREP-deadbeefdeadbeef",
                        "state": "valid",
                        "scope_coverage": "complete",
                        "content_consumed": True,
                        "page_keys": [],
                    }
                ),
            )
            # New path present (PREP file) but pointer missing → must fail, not legacy.
            snapshot = context.ProgressSnapshot(
                path=root / "main/40_course/TEST100/progress.md",
                content="",
                meta={
                    "textbook_page": "10",
                },
            )
            with self.assertRaisesRegex(
                context.ContextPacketError,
                "不得回退 legacy|缺 current_snapshot",
            ):
                context.textbook_lesson_window(
                    context.SourceCache(root),
                    snapshot,
                    self.route(),
                )

    def test_valid_snapshot_source_assets_path_succeeds_with_crlf_map(self) -> None:
        """Legal Snapshot + current pointer + source_assets must open (CRLF map ok)."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course_id = "TEST100"
            lesson = "lesson01"
            document_id = "DOC1"
            pages = [9, 10, 11, 12, 13]
            doc_sha = "a" * 64
            course = root / "main/40_course" / course_id
            # CRLF LessonMap on disk
            map_rows = "\r\n".join(
                f"| {i + 1} | {p} | {document_id}-P{p:04d} | n |"
                for i, p in enumerate(pages)
            )
            map_body = (
                "# Lesson Map\r\n\r\n"
                "| 序 | pdf_page_index | asset_id / page_key | 节点摘要 |\r\n"
                "|---:|---:|---|---|\r\n"
                f"{map_rows}\r\n"
            ).encode("utf-8")
            map_path = course / "lessons" / lesson / "lesson_map.md"
            map_path.parent.mkdir(parents=True, exist_ok=True)
            map_path.write_bytes(map_body)
            map_sha = hashlib.sha256(map_body).hexdigest()
            asset_shas: dict[int, str] = {}
            for p in pages:
                asset = (
                    course
                    / "book/primary/source_assets"
                    / document_id
                    / "pages"
                    / f"page_{p}.md"
                )
                write_utf8(
                    asset,
                    "---\n"
                    f"verification_status: verified\n"
                    f"source_document_id: {document_id}\n"
                    f"source_document_sha256: {doc_sha}\n"
                    f"pdf_page_index: {p}\n"
                    "---\n\n"
                    f"# Page {p}\n\ncontent {p}\n",
                )
                asset_shas[p] = hashlib.sha256(asset.read_bytes()).hexdigest()
            page_keys = [
                {
                    "source_document_sha256": doc_sha,
                    "pdf_page_index": p,
                    "render_profile": "pdf-300dpi-rgb-v1",
                }
                for p in pages
            ]
            receipts = [
                {
                    "receipt_id": f"RCP-{p}",
                    "page_key": page_keys[i],
                    "verified_text_sha256": "b" * 64,
                    "source_page_asset_sha256": asset_shas[p],
                    "source_document_sha256": doc_sha,
                }
                for i, p in enumerate(pages)
            ]
            snap = {
                "schema": "t2ag.lesson_preparation_snapshot.v1",
                "snapshot_id": "PREP-validcrlf00001",
                "lesson_id": lesson,
                "lesson_scope_version": "SCOPE-test",
                "page_keys": page_keys,
                "load_receipt_ids": [r["receipt_id"] for r in receipts],
                "load_receipts": receipts,
                "lesson_map_sha256": map_sha,
                "source_document_sha256": doc_sha,
                "document_id": document_id,
                "scope_coverage": "complete",
                "content_consumed": True,
                "short_document": False,
                "snapshot_body_sha256": "d" * 64,
                "state": "valid",
            }
            prep = course / "lessons" / lesson / "preparation"
            prep.mkdir(parents=True, exist_ok=True)
            (prep / f"{snap['snapshot_id']}.json").write_text(
                json.dumps(snap, indent=2) + "\n",
                encoding="utf-8",
            )
            (prep / "current_snapshot.json").write_text(
                json.dumps(
                    {
                        "schema": "t2ag.preparation_current_pointer.v1",
                        "lesson_id": lesson,
                        "snapshot_id": snap["snapshot_id"],
                        "snapshot_body_sha256": snap["snapshot_body_sha256"],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            # Post-S3 defense: legacy working_pages 创建仅用于验证不被选中
            write_utf8(
                course / "lessons" / lesson / "working_pages/source_excerpt.md",
                "# legacy should not be selected\n\n## 第 10 页\n\nlegacy\n",
            )
            progress = context.ProgressSnapshot(
                path=course / "progress.md",
                content="",
                meta={"textbook_page": "10"},
            )
            path, excerpt = context.textbook_lesson_window(
                context.SourceCache(root),
                progress,
                self.route(),
            )
            self.assertIn("source_assets", str(path).replace("\\", "/"))
            self.assertIn("content 10", excerpt)
            self.assertNotIn("legacy should not be selected", excerpt)


class ConditionalRoutingTests(unittest.TestCase):
    def test_between_activities_route_has_no_fake_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_utf8(
                root / "main/40_course/TEST100/progress.md",
                "---\ntype: course_progress\ncourse_id: TEST100\n"
                "lifecycle_status: ongoing\ncourse_driver: goal\n"
                "truth_scope: course_lifecycle,course_frontend,activity_position\n"
                "current_activity: none\ncurrent_activity_id: none\n"
                "resume_path: none\nactivity_position: between_activities\n"
                "---\n# progress\n",
            )
            route = resolve_activity(root, "TEST100")
            self.assertEqual(route.activity_type, "none")
            self.assertEqual(route.recovery_plan()["activity_read_targets"], [])
            reads = context.conditional_reads("TEST100", route, "G01")
            rendered = "\n".join(item["read"] for item in reads)
            self.assertNotIn("lessons/none", rendered)
            self.assertIn("activity_ledger.md", rendered)

    def test_lesson_conditional_reads_never_point_to_exercise_tree(self) -> None:
        route = SimpleNamespace(
            activity_type="lesson",
            activity_id="lesson01",
        )
        reads = context.conditional_reads("TEST100", route, "G01")
        rendered = "\n".join(item["read"] for item in reads)
        self.assertIn("lessons/lesson01/lesson01.md", rendered)
        self.assertNotIn("exercises/lesson01", rendered)


class FirstStepTests(unittest.TestCase):
    def test_canonical_exercise_problem_id_is_valid(self) -> None:
        scope = "## 学习范围\n\n- 当前题目：exercise01-Q002\n"
        self.assertEqual(context.current_problem_id(scope), "exercise01-Q002")

    def test_exercise_first_step_selects_only_current_problem(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exercise_root = (
                root / "main/40_course/TEST100/exercises/U0001"
            )
            write_utf8(
                exercise_root / "attempts/AT0001/attempt.md",
                "---\nproblem_ids: [U0001-Q001]\n---\n\ncurrent\n",
            )
            write_utf8(
                exercise_root / "attempts/AT0002/attempt.md",
                "---\nproblem_ids: [U0001-Q002]\n---\n\nother\n",
            )
            write_utf8(
                exercise_root / "reviews/RV0001.md",
                "---\nproblem_ids: [U0001-Q001]\n---\n\nreview\n",
            )
            selections = context.exercise_first_step_selections(
                context.SourceCache(root),
                root / "main",
                "TEST100",
                "U0001",
                "U0001-Q001",
            )
            self.assertEqual(len(selections), 2)
            self.assertEqual(
                {item.source for item in selections},
                {
                    (
                        "main/40_course/TEST100/exercises/U0001/"
                        "attempts/AT0001/attempt.md"
                    ),
                    (
                        "main/40_course/TEST100/exercises/U0001/"
                        "reviews/RV0001.md"
                    ),
                },
            )

    def test_nonempty_l1_is_included_in_serialized_combined_cost(self) -> None:
        packet = {
            "schema_version": 2,
            "status": "ready",
            "course_id": "TEST100",
            "snapshot_id": "CTX-TEST100-" + "0" * 64,
            "sources_unchanged": True,
            "memory_current_course": "TEST100",
            "context_mode": "memory_current",
            "group_id": "G01",
            "route": {
                "current_activity": "exercise",
                "current_activity_id": "U0001",
                "activity_position": "start",
                "primary_read": "main/example.md",
                "next_action_kind": "resume",
                "next_activity_type": "exercise",
                "next_activity_id": "U0001",
            },
            "cost": {
                "reference_inventory_chars": 1000,
                "l0_selected_source_chars": 100,
                "l1_selected_source_chars": 23,
                "source_selection_ratio": 0.123,
                "source_inventory_omitted_percent": 87.7,
                "serialized_l0_markdown_chars": 0,
                "serialized_l0_plus_l1_markdown_chars": 0,
                "soft_char_budget": 16000,
                "l0_budget_state": "PENDING",
                "l0_plus_l1_budget_state": "PENDING",
            },
            "selections": [],
            "l1_selections": [
                {
                    "source": "main/direct.md",
                    "label": "直接证据",
                    "sha256": "0" * 64,
                    "content": "DIRECT-L1-CONTENT",
                }
            ],
            "l1_empty_reason": "unused",
            "conditional_reads": [],
        }
        context.finalize_serialized_cost(packet)
        l0 = context.render_markdown(packet)
        combined = context.render_markdown(packet, include_l1=True)
        self.assertNotIn("DIRECT-L1-CONTENT", l0)
        self.assertIn("DIRECT-L1-CONTENT", combined)
        self.assertEqual(
            len(l0),
            packet["cost"]["serialized_l0_markdown_chars"],
        )
        self.assertEqual(
            len(combined),
            packet["cost"]["serialized_l0_plus_l1_markdown_chars"],
        )


class CriticalPacketTests(unittest.TestCase):
    def test_live_critical_contract_is_bounded_and_complete(self) -> None:
        packet = context.build_critical_packet(context.ROOT)
        rendered = context.render_critical(packet)
        self.assertLessEqual(len(rendered), context.CRITICAL_MAX_CHARS)
        self.assertTrue(packet["snapshot_id"].startswith("CTX-"))
        self.assertTrue(packet["sources_unchanged"])
        if packet["status"] == "first_run_required":
            self.assertEqual(packet["action_payload"]["kind"], "first_run")
            return
        self.assertEqual(packet["status"], "ready")
        self.assertFalse(packet["blocking_teach"])
        self.assertIn(packet["route"]["next_action_kind"], context.NEXT_ACTION_KINDS)
        self.assertEqual(
            set(packet["source_sha256"]),
            {"progress", "activity", "profile", "teacher_overlay"},
        )
        creativity = packet["classroom_creativity_policy"]
        self.assertEqual(creativity["creative_interaction_default"], "allowed")
        self.assertFalse(creativity["automatic_extra_exercise_generation"])
        self.assertEqual(
            creativity["extra_exercise_trigger"],
            "student_request_or_explicit_opt_in",
        )
        self.assertFalse(creativity["understanding_check_counts_as_extra_exercise"])
        self.assertEqual(len(creativity["hard_limits"]), 2)
        if packet["action_payload"].get("kind") == "lesson":
            payload = packet["action_payload"]
            resume = payload["resume_contract"]
            self.assertTrue(resume["authoritative_prompt_must_remain_exact"])
            self.assertTrue(resume["creative_supplements_allowed"])
            opening = payload["lesson_opening_contract"]
            self.assertTrue(opening["overview_required"])
            self.assertTrue(opening["knowledge_tree_required"])
            self.assertEqual(opening["knowledge_tree_format"], "ascii_text")
            self.assertTrue(opening["creative_composition_allowed"])
            self.assertTrue(opening["creative_opening_questions_allowed"])
            self.assertTrue(
                opening["reaction_and_continue_required_before_first_block"]
            )
            if resume["checkpoint_state"] == "pending":
                self.assertEqual(
                    payload["first_confirmation_question"],
                    resume["exact_stop"],
                )
            if "source_page" in payload:
                page = payload["source_page"]["pdf_page_index"]
                self.assertTrue(payload["source"].endswith(f"page_{page}.md"))
                contract = payload["page_teaching_contract"]
                self.assertTrue(contract["active_boundary"])
                self.assertGreaterEqual(len(contract["teaching_blocks"]), 1)
                self.assertEqual(
                    payload["source_page"]["printed_page_label"],
                    contract["current_page"]["printed_page_label"],
                )
                self.assertTrue(contract["classroom_tree_required"])
                self.assertTrue(
                    contract["coverage_register"][
                        "page_change_requires_all_blocks_accounted"
                    ]
                )
                gates = contract["interaction_gates"]
                self.assertTrue(gates["one_new_teaching_block_per_turn"])
                self.assertTrue(gates["understanding_confirmation_required"])
                self.assertEqual(
                    gates["affect_check_required_after"],
                    ["derivation", "summary"],
                )
                self.assertEqual(
                    gates["continue_authorization_scope"],
                    "single_use_next_block",
                )
                self.assertTrue(gates["correct_answer_is_not_continue_authorization"])
                self.assertTrue(gates["page_turn_announcement_required"])
                self.assertTrue(packet["teaching_gate"]["scope_scan_required"])
                self.assertFalse(packet["teaching_gate"]["may_release_action"])
                self.assertTrue(packet["teaching_gate"]["page_contract_required"])
                self.assertTrue(
                    packet["teaching_gate"]["explicit_continue_gate_required"]
                )
                self.assertTrue(packet["teaching_gate"]["lesson_opening_required"])
                self.assertTrue(
                    packet["teaching_gate"]["creative_supplements_allowed"]
                )
        if packet["route"]["next_action_kind"] == "confirm_close":
            payload = packet["action_payload"]
            self.assertEqual(payload["kind"], "confirm_close")
            self.assertIn("教学复盘", payload["learner_retrospective_markdown"])
            self.assertIn("知识吸收", payload["learner_retrospective_markdown"])
            self.assertIn("学生课程内容反馈", payload["learner_retrospective_markdown"])
            self.assertRegex(
                payload["retrospective_presentation_sha256"], r"^[0-9a-f]{64}$"
            )
            self.assertRegex(payload["pending_event_id"], r"^ALE-\d{6}$")
            self.assertRegex(payload["body_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(payload["binding_tuple"].splitlines()), 3)
            self.assertIn(
                payload["accepted_close_intent"],
                {"结课", "以未完成状态结课"},
            )

    def test_critical_does_not_build_or_wait_for_full_l0(self) -> None:
        with mock.patch.object(
            context,
            "build_packet",
            side_effect=AssertionError("full L0 must not run"),
        ):
            packet = context.build_critical_packet(context.ROOT)
        self.assertIn(packet["status"], {"ready", "first_run_required"})

    def test_background_snapshot_matches_and_mismatch_is_rejected(self) -> None:
        critical = context.build_critical_packet(context.ROOT)
        background = context.build_packet(context.ROOT)
        self.assertEqual(critical["snapshot_id"], background["snapshot_id"])
        if background["route"]["current_activity"] == "lesson":
            consumption = background["source_consumption"]
            if consumption["required"]:
                self.assertEqual(
                    consumption["scope_text_status"],
                    "complete_in_current_packet",
                )
                self.assertEqual(
                    consumption["scope_visual_status"],
                    "external_scan_required",
                )
                self.assertIn(
                    consumption["current_pdf_page_index"],
                    consumption["pdf_page_indices"],
                )
        tool = context.ROOT / "main/70_tools/t2ag_context.py"
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(tool),
                "--format",
                "markdown",
                "--expect-snapshot",
                "CTX-stale",
            ],
            cwd=context.ROOT,
            capture_output=True,
            encoding="utf-8",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snapshot mismatch", result.stdout)

    def test_exercise_statement_stops_before_hint(self) -> None:
        problem = (
            "## exercise01-Q001\n"
            "- 难度：未评估\n"
            "- 题面：证明 A。\n"
            "  继续题面。\n"
            "- 提示：不要泄露。\n"
        )
        self.assertEqual(
            context.problem_statement(problem),
            "证明 A。\n  继续题面。",
        )


class LiveReleaseTests(unittest.TestCase):
    def test_cli_stdout_matches_serialized_cost(self) -> None:
        packet = context.build_packet(context.ROOT)
        if packet["status"] != "ready":
            self.skipTest("uninitialized Skeleton has no current course")
        tool = context.ROOT / "main/70_tools/t2ag_context.py"
        cases = (
            ((), "serialized_l0_markdown_chars"),
            (("--include-l1",), "serialized_l0_plus_l1_markdown_chars"),
        )
        for extra_args, field in cases:
            with self.subTest(field=field):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(tool),
                        "--format",
                        "markdown",
                        *extra_args,
                    ],
                    cwd=context.ROOT,
                    check=True,
                    capture_output=True,
                    encoding="utf-8",
                )
                self.assertEqual(len(result.stdout), packet["cost"][field])

    def test_release_packet_contract(self) -> None:
        packet = context.build_packet(context.ROOT)
        profile = (
            context.ROOT / "main/10_student/profile/profile.md"
        ).read_bytes().decode("utf-8-sig", errors="replace")
        profile_meta = context.frontmatter_text(profile)

        if profile_meta.get("initialization_status") != "initialized":
            self.assertEqual(packet["status"], "first_run_required")
            self.assertEqual(
                packet["next_action"],
                "读取 main/50_playbook/first_run.md",
            )
            return

        self.assertEqual(packet["status"], "ready")
        cost = packet["cost"]
        self.assertLess(
            cost["l0_selected_source_chars"],
            cost["reference_inventory_chars"],
        )
        l0_markdown = context.render_markdown(packet)
        combined_markdown = context.render_markdown(
            packet,
            include_l1=True,
        )
        self.assertEqual(
            len(l0_markdown),
            cost["serialized_l0_markdown_chars"],
        )
        self.assertEqual(
            len(combined_markdown),
            cost["serialized_l0_plus_l1_markdown_chars"],
        )
        self.assertGreater(len(combined_markdown), len(l0_markdown))
        self.assertEqual(
            cost["l0_budget_state"],
            (
                "PASS"
                if len(l0_markdown) <= cost["soft_char_budget"]
                else "REVIEW"
            ),
        )
        self.assertEqual(
            cost["l0_plus_l1_budget_state"],
            (
                "PASS"
                if len(combined_markdown) <= cost["soft_char_budget"]
                else "REVIEW"
            ),
        )

        selections = packet["selections"]
        labels = {item["label"] for item in selections}
        required_labels = {
            "恢复指针",
            "学生教学契约",
            "当前课程组容量",
            "当前时间预算与周期",
            "进度真相源当前切片",
            "未闭合疑问",
            "活跃错题调度摘要",
            "当前教师 overlay",
        }
        self.assertFalse(required_labels - labels)

        progress = next(
            item for item in selections
            if item["label"] == "进度真相源当前切片"
        )
        self.assertIn("## 二、当前进度", progress["content"])
        self.assertNotIn("## 三、教学记录", progress["content"])
        questions = next(
            item for item in selections
            if item["label"] == "未闭合疑问"
        )
        self.assertNotIn("## 已解答", questions["content"])

        if packet["route"]["current_activity"] == "exercise":
            source = next(
                item for item in selections
                if item["label"].startswith("人工校对题面 ")
            )
            problem_headings = [
                line for line in source["content"].splitlines()
                if re.match(r"^## U\d{4}-Q\d{3}$", line)
            ]
            self.assertEqual(len(problem_headings), 1)

        for item in (*selections, *packet["l1_selections"]):
            source = context.ROOT / item["source"]
            self.assertTrue(source.is_file(), item["source"])
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(item["sha256"], digest)

        self.assertIn("不是新的真相源", l0_markdown)
        self.assertIn("不等于端到端 Token 降幅", l0_markdown)
        self.assertIn("## L1 · 当前一步直接证据", combined_markdown)
        self.assertIn("## L2 · 触发式完整读取", l0_markdown)
        self.assertGreaterEqual(len(packet["conditional_reads"]), 6)

    def test_explicit_current_course_matches_auto_route(self) -> None:
        auto = context.build_packet(context.ROOT)
        if auto["status"] != "ready":
            self.skipTest("uninitialized Skeleton has no current course")
        explicit = context.build_packet(
            context.ROOT,
            course_id=auto["course_id"],
        )
        self.assertEqual(auto["course_id"], explicit["course_id"])
        self.assertEqual(auto["context_mode"], "memory_current")
        self.assertEqual(auto["route"], explicit["route"])
        self.assertEqual(auto["cost"], explicit["cost"])

    def test_soft_budget_reviews_without_truncating(self) -> None:
        normal = context.build_packet(context.ROOT)
        if normal["status"] != "ready":
            self.skipTest("uninitialized Skeleton has no current course")
        reviewed = context.build_packet(
            context.ROOT,
            soft_char_budget=1,
        )
        self.assertEqual(reviewed["cost"]["l0_budget_state"], "REVIEW")
        self.assertEqual(
            reviewed["cost"]["l0_plus_l1_budget_state"],
            "REVIEW",
        )
        self.assertEqual(normal["selections"], reviewed["selections"])
        self.assertEqual(
            normal["l1_selections"],
            reviewed["l1_selections"],
        )
        self.assertEqual(
            len(context.render_markdown(reviewed)),
            reviewed["cost"]["serialized_l0_markdown_chars"],
        )

    def test_non_current_same_group_has_explicit_switch_context(self) -> None:
        auto = context.build_packet(context.ROOT)
        if auto["status"] != "ready":
            self.skipTest("uninitialized Skeleton has no current course")
        candidate = context.ROOT / "main/40_course/PY1001/progress.md"
        if auto["course_id"] == "PY1001" or not candidate.is_file():
            self.skipTest("PY1001 is unavailable as a non-current fixture")

        other = context.build_packet(context.ROOT, course_id="PY1001")
        self.assertEqual(other["course_id"], "PY1001")
        self.assertEqual(other["group_id"], auto["group_id"])
        self.assertEqual(
            other["memory_current_course"],
            auto["course_id"],
        )
        self.assertEqual(
            other["context_mode"],
            "explicit_same_active_group",
        )
        labels = {item["label"] for item in other["selections"]}
        self.assertIn("全局指针切换校验", labels)
        self.assertNotIn("恢复指针", labels)
        memory_selection = next(
            item for item in other["selections"]
            if item["label"] == "全局指针切换校验"
        )
        self.assertNotIn("上次课摘要", memory_selection["content"])
        self.assertIn(
            "当前 Lesson 恢复胶囊已在 L0",
            context.render_markdown(other, include_l1=True),
        )

    def test_course_outside_active_group_is_rejected(self) -> None:
        auto = context.build_packet(context.ROOT)
        if auto["status"] != "ready":
            self.skipTest("uninitialized Skeleton has no current course")
        candidate = context.ROOT / "main/40_course/CS1953/progress.md"
        if not candidate.is_file():
            self.skipTest("CS1953 is unavailable as an out-of-group fixture")
        with self.assertRaisesRegex(
            context.ContextPacketError,
            "not a member of active group",
        ):
            context.build_packet(context.ROOT, course_id="CS1953")


if __name__ == "__main__":
    unittest.main(verbosity=2)
