#!/usr/bin/env python3
"""Regression checks for the read-only learning context packet."""
from __future__ import annotations

import hashlib
import marker_assertions
import t2ag_doctor as doctor
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
        self.assertIn(
            packet["status"],
            {
                context.CRITICAL_STATUS_READY,
                context.CRITICAL_STATUS_ROUTE_READY,
                context.CRITICAL_STATUS_SCAN_PENDING,
                context.CRITICAL_STATUS_SCAN_ATTESTED,
            },
        )
        gate = packet["teaching_gate"]
        self.assertTrue(gate["packet_fields_do_not_authorize_emission"])
        if gate.get("scope_scan_required") and gate.get("scope_scan_status") == "pending":
            self.assertEqual(packet["status"], context.CRITICAL_STATUS_ROUTE_READY)
            self.assertTrue(packet["blocking_teach"])
            self.assertEqual(gate["admission_status"], "unavailable")
            self.assertEqual(gate["egress_mode"], "status_only")
            self.assertFalse(gate["may_release_action"])
        else:
            self.assertEqual(packet["status"], context.CRITICAL_STATUS_READY)
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
            scan_pending = context.scope_scan_pending(payload)
            if scan_pending:
                self.assertNotIn("textbook_excerpt", payload)
                self.assertNotIn("first_teaching_candidate", payload)
                self.assertNotIn("first_confirmation_question", payload)
                self.assertTrue(payload.get("teaching_payload_withheld"))
                self.assertTrue(opening.get("body_withheld"))
                for key in context.WITHHELD_OPENING_BODY_KEYS:
                    self.assertNotIn(key, opening)
                self.assertIsNone(resume.get("prompt"))
            elif resume["checkpoint_state"] == "pending":
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
            self.assertIn("teaching retrospective", payload["learner_retrospective_markdown"])
            self.assertIn("knowledge absorption", payload["learner_retrospective_markdown"])
            self.assertIn("student course content feedback", payload["learner_retrospective_markdown"])
            self.assertRegex(
                payload["retrospective_presentation_sha256"], r"^[0-9a-f]{64}$"
            )
            self.assertRegex(payload["pending_event_id"], r"^ALE-\d{6}$")
            self.assertRegex(payload["body_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(payload["binding_tuple"].splitlines()), 3)
            self.assertIn(
                payload["accepted_close_intent"],
                {"close", "closed_incomplete"},
            )

    def test_critical_does_not_build_or_wait_for_full_l0(self) -> None:
        with mock.patch.object(
            context,
            "build_packet",
            side_effect=AssertionError("full L0 must not run"),
        ):
            packet = context.build_critical_packet(context.ROOT)
        self.assertIn(
            packet["status"],
            {
                context.CRITICAL_STATUS_READY,
                context.CRITICAL_STATUS_ROUTE_READY,
                "first_run_required",
            },
        )

    def test_background_snapshot_matches_critical(self) -> None:
        """Both builders share one snapshot; the lesson-branch assertions follow.

        Split out of `test_background_snapshot_matches_and_mismatch_is_rejected` on
        2026-08-22.  The original test bundled two unrelated things -- "the snapshots
        agree" and "a stale snapshot is rejected" -- and read `background["route"]`
        with no guard.  On an uninitialized instance the background packet has no
        `route` by design (see the first-run comment in `render_markdown`), so it died
        with a KeyError on an empty Skeleton.  A skipTest at the top of the original
        would have taken the second half down with it, and that half is perfectly valid
        on an empty instance -- trading a loud crash for a silent loss of coverage, the
        same defect family wearing different clothes.  Hence two tests: this one guards
        per the idiom already used six times in this file, the other runs unconditionally.
        """
        critical = context.build_critical_packet(context.ROOT)
        background = context.build_packet(context.ROOT)
        self.assertEqual(critical["snapshot_id"], background["snapshot_id"])
        if background.get("status") == "first_run_required":
            self.skipTest("uninitialized instance")
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

    def test_snapshot_mismatch_is_rejected(self) -> None:
        """A stale snapshot must be rejected -- equally true on an empty instance,
        so this one carries no guard."""
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

    def test_first_run_packet_shape_is_deliberately_special(self) -> None:
        """A first-run packet has **no** route/cost/l1_empty_reason. Feature, not defect.

        `status: first_run_required` is the signal that says "this packet has a
        different shape, branch on it", and the absent keys make a consumer that
        forgot to branch fail loudly -- fail-fast.  On 2026-08-22 it was proposed to
        "just fill in the three empty keys so the shape is uniform"; the proposal was
        refused on the spot: filling them in disguises the special case as an ordinary
        packet, so a consumer that forgets to check `status` no longer crashes but
        quietly renders an empty lesson -- trading a loud crash for a silent wrong
        output.  This test promotes that comment in `render_markdown` into an
        executable assertion, precisely to block the next well-meaning "fix".

        The two builders differ here by role, not by accident: the critical packet is
        the routing packet and always carries a route (pointing at first run here);
        the background packet is the selection packet, and with no course there is
        nothing to select from.

        The first-run branch is forced with mock rather than by happening to run on an
        uninitialized instance: the Chinese Main can never be empty, so this path was
        previously reachable only from the two Skeletons -- and the empty instance is
        where every new user starts.
        """
        with mock.patch.object(context, "initialized", return_value=False):
            background = context.build_packet(context.ROOT)
            critical = context.build_critical_packet(context.ROOT)
        self.assertEqual(background["status"], "first_run_required")
        self.assertEqual(critical["status"], "first_run_required")
        for absent in ("route", "cost", "l1_empty_reason"):
            self.assertNotIn(
                absent,
                background,
                msg=f"the first-run background packet must not carry {absent!r}; "
                "filling it in lets a consumer that forgot to branch pass silently "
                "(adjudicated 2026-08-22)",
            )
        self.assertIn("next_action", background)
        self.assertIn("route", critical)
        self.assertEqual(critical["route"]["activity_position"], "first_run")
        self.assertEqual(critical["route"]["next_action_kind"], "first_run")
        self.assertEqual(background["snapshot_id"], critical["snapshot_id"])
        self.assertTrue(background["snapshot_id"].startswith("CTX-FIRST-RUN-"))

    def test_first_run_render_survives_include_l1(self) -> None:
        """Markdown rendering with `--include-l1` must not crash on an empty instance.

        The first-run early return in `render_markdown` was bought by an earlier
        incident: control used to fall through to the L1 block below, which reads
        `l1_empty_reason` unconditionally, so the empty-skeleton quick-start command
        documented as `t2ag_context.py --include-l1 --format markdown` ended in a
        KeyError.  The fix has had **zero** test cover ever since -- an invariant held
        up by a comment alone, which is the family this repo keeps paying for.  Pinned
        here while it is green.
        """
        with mock.patch.object(context, "initialized", return_value=False):
            packet = context.build_packet(context.ROOT)
            text = context.render_markdown(packet, include_l1=True)
        self.assertIn("first_run_required", text)
        self.assertIn(packet["snapshot_id"], text)

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
                "Read main/50_playbook/first_run.md",
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
            "recovery pointer",
            "学生教学契约",
            "当前课程组容量",
            "当前时间预算与周期",
            "current slice of the progress source of truth",
            "unclosed question",
            "活跃错题调度摘要",
            "当前教师 overlay",
        }
        self.assertFalse(required_labels - labels)

        progress = next(
            item for item in selections
            if item["label"] == "current slice of the progress source of truth"
        )
        self.assertIn("## 二、当前进度", progress["content"])
        self.assertNotIn("## 三、教学记录", progress["content"])
        questions = next(
            item for item in selections
            if item["label"] == "unclosed question"
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

        marker_assertions.assert_states_rule(
            self, l0_markdown, "不是新的真相源", name="the L0 markdown"
        )
        self.assertIn("never call that ratio an end-to-end token reduction", l0_markdown)
        marker_assertions.assert_states_rule(
            self,
            combined_markdown,
            "## L1 · 当前一步直接证据",
            name="the combined markdown",
        )
        marker_assertions.assert_states_rule(
            self,
            l0_markdown,
            "## L2 · 触发式完整读取",
            name="the L0 markdown",
        )
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
        self.assertIn("global pointer switch check", labels)
        self.assertNotIn("recovery pointer", labels)
        memory_selection = next(
            item for item in other["selections"]
            if item["label"] == "global pointer switch check"
        )
        self.assertNotIn("last lesson summary", memory_selection["content"])
        self.assertIn(
            "the current Lesson recovery capsule is already in L0",
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


class PendingScopeScanWithholdTests(unittest.TestCase):
    """Repo-level contracts for pending Scope scan payloads.

    These tests fix defense-in-depth only. They do **not** prove host egress
    interception or structural teaching-output gates (ADR-0002).
    """

    def _pending_payload(self) -> dict[str, object]:
        return {
            "kind": "lesson",
            "source": "main/40_course/MATH1607H/book/primary/source_assets/X/pages/page_26.md",
            "source_sha256": "a" * 64,
            "textbook_excerpt": "定理 2.1 的完整正文，可直接照发。",
            "first_teaching_candidate": "先讲定义，再举例。",
            "first_confirmation_question": "请复述刚才的定义。",
            "resume_contract": {
                "kind": "next_action",
                "checkpoint_state": "none",
                "exact_stop": "PDF 26 / 书内 22",
                "next_plan": "继续覆盖块 B1",
                "prompt": "可直接照发的下一问",
                "authoritative_prompt_must_remain_exact": True,
                "creative_supplements_allowed": True,
            },
            "scope_scan": {
                "required_this_session": True,
                "status": "pending_visual_scan",
                "source_document_sha256": "b" * 64,
                "pdf_page_indices": [25, 26, 27],
                "preparation_snapshot_id": "PREP-1",
                "lesson_scope_version": "lsv-1",
            },
            "lesson_opening_contract": {
                "schema": "t2ag.lesson_opening_contract.v1",
                "overview_required": True,
                "knowledge_tree_required": True,
                "knowledge_tree_format": "ascii_text",
                "overview_markdown": "整段开场概览，可直接发给学生。",
                "knowledge_tree_markdown": "```text\n树\n```",
                "learning_range": "第 2 章全部可照发范围。",
                "creative_composition_allowed": True,
                "creative_opening_questions_allowed": True,
                "reaction_and_continue_required_before_first_block": True,
            },
            "page_teaching_contract": {
                "schema": "t2ag.page_teaching_contract.v1",
                "active_boundary": "B1-B3",
                "teaching_blocks": ["B1 定义", "B2 例题"],
                "classroom_tree_required": True,
            },
            "source_page": {
                "document_id": "DOC",
                "pdf_page_index": 26,
                "printed_page_label": "22",
            },
            "preparation_snapshot_id": "PREP-1",
            "lesson_scope_version": "lsv-1",
        }

    def test_pending_scope_scan_withholds_teaching_payload(self) -> None:
        raw = self._pending_payload()
        out = context.withhold_pending_scope_scan_teaching_payload(raw)
        self.assertTrue(out["teaching_payload_withheld"])
        self.assertNotIn("textbook_excerpt", out)
        self.assertNotIn("first_teaching_candidate", out)
        self.assertNotIn("first_confirmation_question", out)
        opening = out["lesson_opening_contract"]
        self.assertTrue(opening["body_withheld"])
        self.assertNotIn("overview_markdown", opening)
        self.assertNotIn("knowledge_tree_markdown", opening)
        self.assertNotIn("learning_range", opening)
        # Structural identities remain for route / host scan inputs.
        self.assertEqual(out["source_page"]["pdf_page_index"], 26)
        self.assertEqual(out["scope_scan"]["status"], "pending_visual_scan")
        self.assertIsNone(out["resume_contract"]["prompt"])
        self.assertEqual(out["resume_contract"]["exact_stop"], "PDF 26 / 书内 22")

    def test_route_ready_does_not_imply_teaching_admission(self) -> None:
        payload = context.withhold_pending_scope_scan_teaching_payload(
            self._pending_payload()
        )
        gate = context.build_teaching_gate(payload, scan_pending=True)
        # Simulated critical top-level shape used by build_critical_packet.
        status = context.CRITICAL_STATUS_ROUTE_READY
        blocking_teach = True
        self.assertEqual(status, "route_ready")
        self.assertTrue(blocking_teach)
        self.assertEqual(gate["scope_scan_status"], "pending")
        self.assertEqual(gate["admission_status"], "unavailable")
        self.assertEqual(gate["egress_mode"], "status_only")
        self.assertFalse(gate["may_release_action"])
        # Mixed signal forbidden: ready + pending scan must not co-occur.
        self.assertNotEqual(status, context.CRITICAL_STATUS_READY)

    def test_agent_visible_fields_do_not_authorize_emission(self) -> None:
        payload = context.withhold_pending_scope_scan_teaching_payload(
            self._pending_payload()
        )
        gate = context.build_teaching_gate(payload, scan_pending=True)
        self.assertTrue(gate["packet_fields_do_not_authorize_emission"])
        self.assertTrue(payload["packet_fields_do_not_authorize_emission"])
        self.assertTrue(gate["host_admission_required_for_textbook_teaching"])
        # No field path may claim release while scan is pending.
        self.assertFalse(gate["may_release_action"])
        self.assertNotEqual(gate["admission_status"], "issued")
        self.assertNotEqual(gate["admission_status"], "available")

    def test_snapshot_change_invalidates_pending_scan_state(self) -> None:
        base_payload = self._pending_payload()
        left = {
            "snapshot_id": "CTX-MATH1607H-" + ("1" * 64),
            "action_payload": base_payload,
        }
        right_same = {
            "snapshot_id": left["snapshot_id"],
            "action_payload": dict(base_payload),
        }
        right_snapshot = {
            "snapshot_id": "CTX-MATH1607H-" + ("2" * 64),
            "action_payload": dict(base_payload),
        }
        drifted_scan = dict(base_payload)
        drifted_scan["scope_scan"] = dict(base_payload["scope_scan"])
        drifted_scan["scope_scan"]["preparation_snapshot_id"] = "PREP-OTHER"
        right_prep = {
            "snapshot_id": left["snapshot_id"],
            "action_payload": drifted_scan,
        }
        self.assertTrue(context.admission_eras_compatible(left, right_same))
        self.assertFalse(context.admission_eras_compatible(left, right_snapshot))
        self.assertFalse(context.admission_eras_compatible(left, right_prep))

    def test_live_textbook_critical_uses_route_ready_when_scan_pending(self) -> None:
        """When live route is textbook+scope_scan, mixed ready signal is gone."""
        packet = context.build_critical_packet(context.ROOT)
        if packet.get("status") == "first_run_required":
            self.skipTest("uninitialized instance")
        payload = packet.get("action_payload") or {}
        if not isinstance(payload, dict) or not context.scope_scan_required(payload):
            self.skipTest("current critical route is not textbook scope_scan")
        self.assertTrue(context.scope_scan_pending(payload))
        self.assertEqual(packet["status"], context.CRITICAL_STATUS_ROUTE_READY)
        self.assertTrue(packet["blocking_teach"])
        self.assertNotIn("textbook_excerpt", payload)
        self.assertNotIn("first_teaching_candidate", payload)
        gate = packet["teaching_gate"]
        self.assertEqual(gate["admission_status"], "unavailable")
        self.assertEqual(gate["egress_mode"], "status_only")
        self.assertFalse(gate["may_release_action"])


class ScanEvidenceFormTests(unittest.TestCase):
    """source_page_assets.md §3.2 — which evidence forms count, per page.

    Negative cases first: the fail-closed branches are the ones that keep a
    figure-heavy page off the text-only path, so a stubbed-out selector must
    break these before it breaks anything else.
    """

    def test_missing_layout_critical_falls_back_to_rendering(self) -> None:
        """NEGATIVE: absent flag means unknown, never 'false'."""
        entry = {"pdf_page_index": 29, "verification_status": "verified"}
        self.assertEqual(
            context.admissible_scan_form(entry), context.SCAN_FORM_RENDER_PNG
        )

    def test_layout_critical_true_falls_back_to_rendering(self) -> None:
        """NEGATIVE: a figure page must not be served as text only."""
        entry = {
            "pdf_page_index": 29,
            "verification_status": "verified",
            "layout_critical": True,
        }
        self.assertEqual(
            context.admissible_scan_form(entry), context.SCAN_FORM_RENDER_PNG
        )

    def test_unverified_page_falls_back_to_rendering(self) -> None:
        """NEGATIVE: unverified asset text is machine OCR, which does not count."""
        entry = {
            "pdf_page_index": 21,
            "verification_status": "unverified",
            "layout_critical": False,
        }
        self.assertEqual(
            context.admissible_scan_form(entry), context.SCAN_FORM_RENDER_PNG
        )

    def test_verified_non_layout_critical_uses_asset(self) -> None:
        """POSITIVE: both preconditions present -> cheapest admissible form."""
        entry = {
            "pdf_page_index": 29,
            "verification_status": "verified",
            "layout_critical": False,
        }
        self.assertEqual(
            context.admissible_scan_form(entry), context.SCAN_FORM_VERIFIED_ASSET
        )

    def test_mixed_scope_reports_most_demanding_status(self) -> None:
        """One fallback page must not hide behind its neighbours' cheap status."""
        self.assertEqual(
            context.scope_scan_pending_status(
                [context.SCAN_FORM_VERIFIED_ASSET, context.SCAN_FORM_RENDER_PNG]
            ),
            "pending_visual_scan",
        )
        self.assertEqual(
            context.scope_scan_pending_status([context.SCAN_FORM_VERIFIED_ASSET]),
            "pending_asset_read",
        )

    def test_every_form_has_a_distinct_pending_status(self) -> None:
        statuses = set(context.SCAN_FORM_PENDING_STATUS.values())
        self.assertEqual(len(statuses), len(context.SCAN_FORM_PENDING_STATUS))
        self.assertTrue(statuses <= context.SCOPE_SCAN_PENDING_STATUSES)


def normalise_spec_text(text: str) -> str:
    """Collapse line wrapping and blockquote markers so anchors can span lines.

    Pure function: the assertions below run it over the real playbook, and a
    mutation check can run it over a doctored string without touching the file.
    """
    return "".join(
        line.lstrip().lstrip(">").strip() for line in text.splitlines()
    )


def b_layer_exclusions(body: str) -> str:
    """The `B 层不算数` block only, normalised.

    Scoping matters: an anchor matched against the whole document would still
    pass if a clause were *moved out* of the exclusion list into the admissible
    one.  Matching inside this block means relocation fails the test too.
    """
    start = doctor.marker_offset(body, "B 层不算数")
    if start < 0:
        raise AssertionError(
            "source_page_assets.md no longer has the Layer-B exclusion block "
            f"(accepted spellings: {doctor.marker_spellings('B 层不算数')})"
        )
    end = body.find("####", start)
    return normalise_spec_text(body[start : end if end != -1 else len(body)])


class FirstRunRenderTests(unittest.TestCase):
    """The empty-skeleton quick-start path documented in Skeleton `README.md`.

    Step 4 of that quick-start is `t2ag_context.py --include-l1 --format markdown`.
    On an uninitialised Skeleton it used to die with `KeyError: 'l1_empty_reason'`:
    `render_markdown` built the short first-run notice but then fell through into
    the L1 block, which reads a key that only a routed packet carries.  The very
    first command a new user is told to run therefore crashed.
    """

    PACKET = {
        "status": "first_run_required",
        "snapshot_id": "CTX-FIRST-RUN-abc123",
        "next_action": "Read main/50_playbook/first_run.md",
    }

    def test_first_run_renders_without_l1(self) -> None:
        text = context.render_markdown(dict(self.PACKET), include_l1=False)
        self.assertIn("first_run_required", text)
        self.assertIn("first_run.md", text)

    def test_first_run_renders_with_l1_flag(self) -> None:
        """NEGATIVE-turned-positive: the flag must not require a routed packet."""
        text = context.render_markdown(dict(self.PACKET), include_l1=True)
        self.assertIn("first_run_required", text)
        self.assertNotIn("l1_empty_reason", text)

    def test_first_run_packet_needs_no_routed_keys(self) -> None:
        """Guards the fall-through: rendering must not touch route/cost/L1 keys.

        If someone re-introduces the fall-through, this fails with KeyError rather
        than silently producing a half-packet.
        """
        for flag in (False, True):
            with self.subTest(include_l1=flag):
                context.render_markdown(dict(self.PACKET), include_l1=flag)


class ScanEvidenceSpecTests(unittest.TestCase):
    """The clauses U5 cannot test behaviourally must at least be present in text.

    The two cross-form reverse cases the workorder asks for -- submitting a
    subprocess digest, and delivering only a page asset's frontmatter -- cannot be
    exercised here: this repository *emits* the scan payload and never receives or
    adjudicates evidence.  Under ADR-0003 (EV-0019) completion is certified
    in-session by the Prefetcher after observable delivery; the host Scan
    Orchestrator is a future state.  The guard is the normative text, so these
    assertions fail if the clauses are edited away.

    Anchors deliberately include the **negating** half of each clause.  An earlier
    revision asserted only that the term "子进程摘要" appeared somewhere in the
    file, which would have passed unchanged had the clause been inverted to say a
    subprocess digest *does* count -- the test name promised an exclusion while the
    assertion only proved a mention.  Per workorder step 13 a guard whose mutation
    survives is an empty guard.
    """

    PLAYBOOK = Path(__file__).resolve().parents[2] / "main/50_playbook/source_page_assets.md"

    def test_admission_criterion_is_stated(self) -> None:
        body = self.PLAYBOOK.read_text(encoding="utf-8")
        marker_assertions.assert_states_rule(
            self, body, "宿主能观察到内容本体进入本轮模型上下文这一事件本身",
            name="source_page_assets.md",
        )

    def test_adr0003_self_certification_is_stated(self) -> None:
        """EV-0019: completion = in-session observable delivery, not host signing."""
        body = self.PLAYBOOK.read_text(encoding="utf-8")
        marker_assertions.assert_states_rule(
            self, body, "A1–A5 经**宿主可观察投递**在本会话内证成", name="source_page_assets.md"
        )
        # Pending must survive until certification -- the boot invariant.
        marker_assertions.assert_states_rule(
            self, body, "等 pending 状态**不得清除**", name="source_page_assets.md"
        )
        # The user-preserved anti-impersonation clause must survive verbatim.
        marker_assertions.assert_states_rule(
            self, body, "（§3.1.3 A 层「不得冒充」条款原样有效）", name="source_page_assets.md"
        )

    def test_host_signing_monopoly_is_retired(self) -> None:
        """The old 'only the host signs' clause must not resurface (ADR-0003)."""
        body = self.PLAYBOOK.read_text(encoding="utf-8")
        self.assertNotIn("issued by the host only", body)
        self.assertNotIn("完成由**宿主签发**", body)

    def test_subprocess_digest_is_excluded(self) -> None:
        block = b_layer_exclusions(self.PLAYBOOK.read_text(encoding="utf-8"))
        marker_assertions.assert_states_rule(
            self, block, "**子进程摘要**", name="the Layer-B exclusion block"
        )
        # The negation is the rule; without it the term alone proves nothing.
        marker_assertions.assert_states_rule(
            self, block, "证明脚本读过文件，**不**证明本轮模型上下文收到了内容本体",
            name="the Layer-B exclusion block",
        )

    def test_frontmatter_trap_is_named(self) -> None:
        body = self.PLAYBOOK.read_text(encoding="utf-8")
        marker_assertions.assert_states_rule(
            self, body, "因此「只读 frontmatter」能满足全部前置而**正文一字未投递**",
            name="source_page_assets.md",
        )
        # Naming the trap is not enough; the countermeasure must survive too.
        marker_assertions.assert_states_rule(
            self, body,
            "故 A1 要求**完整正文段**投递，宿主观察事件须能区分「正文投递」与「仅 frontmatter 投递」",
            name="source_page_assets.md",
        )

    def test_assurance_downgrade_is_not_flattened(self) -> None:
        body = self.PLAYBOOK.read_text(encoding="utf-8")
        self.assertIn("weaker than the other two", body)

    def test_spec_anchors_are_mutation_sensitive(self) -> None:
        """Step 13 in-repo: doctoring the clauses must break the anchors above.

        Runs the same pure helpers over mutated copies, so the guard is proven
        rather than asserted.  No file is written.
        """
        body = self.PLAYBOOK.read_text(encoding="utf-8")

        inverted = body
        for spelling in doctor.marker_spellings(
            "证明脚本读过文件，**不**证明本轮模型上下文收到了内容本体"
        ):
            inverted = inverted.replace(spelling, "the subprocess digest is admissible after all")
        self.assertNotEqual(inverted, body, "mutation had no effect: the subprocess-digest anchor drifted")
        marker_assertions.assert_does_not_state_rule(
            self, b_layer_exclusions(inverted),
            "证明脚本读过文件，**不**证明本轮模型上下文收到了内容本体",
            name="the mutated Layer-B block",
        )

        relocated = body
        for spelling in doctor.marker_spellings("B 层不算数"):
            relocated = relocated.replace(spelling, "the exclusion list moved away")
        with self.assertRaises(AssertionError):
            b_layer_exclusions(relocated)

        # Mutate a short contiguous fragment the rule depends on.  A whole-marker
        # replace cannot work here: the registered spelling spans a wrapped,
        # blockquoted line, so it exists in the normalized view and not verbatim --
        # the same distinction marker_position/marker_offset was split over.
        dropped = body.replace("正文一字未投递", "正文已全部投递")
        dropped = dropped.replace("not one word of", "every word of")
        self.assertNotEqual(dropped, body, "mutation had no effect: the frontmatter-trap anchor drifted")
        marker_assertions.assert_does_not_state_rule(
            self, dropped, "因此「只读 frontmatter」能满足全部前置而**正文一字未投递**",
            name="the mutated playbook",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
