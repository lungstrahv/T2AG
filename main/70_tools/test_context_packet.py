#!/usr/bin/env python3
"""Regression checks for the read-only learning context packet."""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
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
            working_pages_path=(
                "main/40_course/TEST100/lessons/lesson01/"
                "working_pages/source_excerpt.md"
            ),
        )

    def test_textbook_lesson_requires_window_metadata_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = context.SourceCache(root)
            progress_path = root / "main/40_course/TEST100/progress.md"
            snapshot = context.ProgressSnapshot(
                path=progress_path,
                content="",
                meta={},
            )
            with self.assertRaisesRegex(
                context.ContextPacketError,
                "working_pages_window",
            ):
                context.textbook_lesson_window(
                    cache,
                    snapshot,
                    self.route(),
                )

            snapshot = context.ProgressSnapshot(
                path=progress_path,
                content="",
                meta={"working_pages_window": "[9, 10, 11, 12]"},
            )
            with self.assertRaisesRegex(
                context.ContextPacketError,
                "textbook_page",
            ):
                context.textbook_lesson_window(
                    cache,
                    snapshot,
                    self.route(),
                )

            snapshot = context.ProgressSnapshot(
                path=progress_path,
                content="",
                meta={
                    "textbook_page": "10",
                    "working_pages_window": "[9, 10, 11, 12]",
                },
            )
            with self.assertRaisesRegex(
                context.ContextPacketError,
                "required context source missing",
            ):
                context.textbook_lesson_window(
                    cache,
                    snapshot,
                    self.route(),
                )

    def test_textbook_lesson_rejects_missing_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            working = (
                root
                / "main/40_course/TEST100/lessons/lesson01/"
                "working_pages/source_excerpt.md"
            )
            write_utf8(
                working,
                "# Excerpt\n\n"
                "## 第 9 页\n\nnine\n\n"
                "## 第 10 页\n\nten\n\n"
                "## 第 11 页\n\neleven\n",
            )
            snapshot = context.ProgressSnapshot(
                path=root / "main/40_course/TEST100/progress.md",
                content="",
                meta={
                    "textbook_page": "10",
                    "working_pages_window": "[9, 10, 11, 12]",
                },
            )
            with self.assertRaisesRegex(
                context.ContextPacketError,
                "教材窗口缺页",
            ):
                context.textbook_lesson_window(
                    context.SourceCache(root),
                    snapshot,
                    self.route(),
                )

    def test_textbook_lesson_accepts_complete_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            working = (
                root
                / "main/40_course/TEST100/lessons/lesson01/"
                "working_pages/source_excerpt.md"
            )
            write_utf8(
                working,
                "# Excerpt\n\n"
                + "\n\n".join(
                    f"## 第 {page} 页\n\npage {page}"
                    for page in (9, 10, 11, 12)
                )
                + "\n",
            )
            snapshot = context.ProgressSnapshot(
                path=root / "main/40_course/TEST100/progress.md",
                content="",
                meta={
                    "textbook_page": "10",
                    "working_pages_window": "[9, 10, 11, 12]",
                },
            )
            path, excerpt = context.textbook_lesson_window(
                context.SourceCache(root),
                snapshot,
                self.route(),
            )
            self.assertEqual(path, working)
            self.assertIn("## 第 12 页", excerpt)


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
            working_pages_path=(
                "main/40_course/TEST100/lessons/lesson01/"
                "working_pages/source_excerpt.md"
            ),
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
            "memory_current_course": "TEST100",
            "context_mode": "memory_current",
            "group_id": "G01",
            "route": {
                "current_activity": "exercise",
                "current_activity_id": "U0001",
                "activity_position": "start",
                "primary_read": "main/example.md",
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
