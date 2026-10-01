"""Non-author migration semantic conflict regressions, synthetic source only."""
from pathlib import Path
import hashlib
import importlib.util
import tempfile
import unittest

from t2ag_next import migration, learning
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError


class MigrationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def import_fixture(self, lifecycle="ongoing", current_kind="lesson", body_next="confirm_close lesson:L1。", extra_files=None):
        source = self.root / "legacy"
        base = source / "main/40_course/C"
        base.mkdir(parents=True)
        (base / "course.md").write_text("---\ncourse_id: C\nname: Synthetic\ncourse_type: mastery\nlearning_mode: goal\n---\n", encoding="utf-8")
        (base / "progress.md").write_text(
            "---\ncourse_id: C\nlifecycle_status: " + lifecycle + "\ncurrent_activity: " + current_kind +
            "\ncurrent_activity_id: L1\nactivity_position: in_activity\ncurrent_checkpoint: none\n"
            "next_action_kind: confirm_close\nnext_activity_type: lesson\nnext_activity_id: L1\n---\n"
            "## 当前进度\n- **精确停顿点**：等待下一次确认。\n- **下一步计划**：" + body_next + "\n", encoding="utf-8")
        (base / "activity_ledger.md").write_text(
            "| activity_type | activity_id | state |\n|---|---|---|\n| lesson | L1 | pending_close |\n", encoding="utf-8")
        lesson = base / "lessons/L1/L1.md"
        lesson.parent.mkdir(parents=True)
        lesson.write_text("---\nlesson_id: L1\n---\nSynthetic activity body.\n", encoding="utf-8")
        review = lesson.parent / "closeout/learner-review.md"
        review.parent.mkdir()
        review.write_text("# Synthetic pending review\nAwaiting actual confirmation.\n", encoding="utf-8")
        for relative, body in (extra_files or {}).items():
            extra = source / relative
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_bytes(body.encode("utf-8") if isinstance(body, str) else body)
        package, destination = self.root / "package", self.root / "destination"
        migration.export_legacy(source, package)
        migration.import_package(package, destination)
        return Journal(destination).read_state()["objects"]

    def test_mig_r1_course_queued_is_not_silently_known_course_state(self):
        objects = self.import_fixture(lifecycle="queued")
        course = objects["course/C"]["data"]
        self.assertIn("unknown_course_lifecycle", course["uncertainties"])
        self.assertEqual(course["legacy_progress"]["lifecycle_status"], "queued")

    def test_mig_r2_short_next_action_conflict_is_explicit(self):
        objects = self.import_fixture(body_next="S03 开讲，从核标题开始。")
        cursor = objects["cursor/C/L1"]["data"]
        self.assertIn("body_next_action_requires_semantic_reconciliation", cursor["uncertainties"])
        self.assertIn("S03", cursor["legacy_body_next_action"])
        self.assertEqual(cursor["next_action"]["kind"], "confirm_close")

    def test_mig_r3_structured_current_activity_kind_conflict_is_explicit(self):
        objects = self.import_fixture(current_kind="exercise")
        cursor = objects["cursor/C/L1"]["data"]
        self.assertIn("current_activity_type_conflicts_with_ledger", cursor["uncertainties"])
        self.assertEqual(objects["course/C"]["data"]["legacy_progress"]["current_activity"], "exercise")
        self.assertEqual(objects["activity/C/L1"]["data"]["activity_type"], "lesson")

    def test_mig_r4_unmapped_historical_help_cannot_become_clean_exercise_state(self):
        base = "main/40_course/C/exercises/exercise01"
        objects = self.import_fixture(extra_files={
            base + "/problems.md": "---\nsource_order: [exercise01-Q001]\nteaching_sequence: [exercise01-Q001]\n---\n## exercise01-Q001\n- 题面：Compute.\n",
            base + "/attempts/AT1/attempt.md": "---\nattempt_id: AT1\nproblem_ids: [exercise01-Q001]\n---\n## exercise01-Q001\nWorked after the teacher supplied the full solution.\n"})
        exercise = objects["exercise/C/exercise01"]["data"]
        self.assertTrue(exercise.get("migration_requires_reconciliation"),
                        "An empty new assistance list is not proof that historical help was absent.")
        state = {"revision": 1, "objects": objects}
        request = {"request_id": "late-criterion", "action": "criterion.create",
                   "payload": {"criterion_id": "new", "target_kind": "exercise", "target_id": "C/exercise01",
                               "rubric": "New rubric", "problem_ids": ["exercise01-Q001"], "max_scores": {"exercise01-Q001": 1}},
                   "actor": {"role": "teacher", "source": "synthetic reviewer", "text": "New grading"},
                   "expected": {key: entity["version"] for key, entity in objects.items()}}
        with self.assertRaises(DomainError) as caught:
            learning.plan(state, request)
        self.assertEqual(caught.exception.code, "MIGRATION_RECONCILIATION_REQUIRED")

    def test_mig_r5_unresolved_imported_page_cannot_be_consumed_as_verified_source(self):
        source = b"Synthetic immutable source"
        sha = hashlib.sha256(source).hexdigest()
        base = "main/40_course/C/book/primary"
        objects = self.import_fixture(extra_files={
            base + "/source.pdf": source,
            base + "/source_assets/DOC/pages/page_1.md":
                "---\nasset_id: PAGE1\nsource_document_sha256: " + sha + "\nverified_text_sha256: wrong\nverification_status: verified\n---\nUnverified claim.\n"})
        page = objects["page/PAGE1"]["data"]
        self.assertEqual(page["verification"]["status"], "unresolved")
        objects["activity/C/exercise01"] = {"kind": "activity", "id": "C/exercise01", "version": 1,
            "data": {"course_id": "C", "activity_type": "exercise", "status": "ongoing"}}
        objects["exercise/C/exercise01"] = {"kind": "exercise", "id": "C/exercise01", "version": 1,
            "data": {"course_id": "C", "problems": {}, "source_order": [], "teaching_sequence": []}}
        request = {"request_id": "bad-source", "action": "problem.add",
                   "payload": {"activity_id": "C/exercise01", "problem_id": "Q1", "text": "Question",
                               "origin": "source", "page_id": "PAGE1", "source_excerpt": "Unverified claim.", "locator": "p1"},
                   "actor": {"role": "teacher", "source": "synthetic reviewer", "text": "Import source"},
                   "expected": {key: entity["version"] for key, entity in objects.items()}}
        with self.assertRaises(DomainError) as caught:
            learning.plan({"revision": 1, "objects": objects}, request)
        self.assertIn(caught.exception.code, {"UNVERIFIED_PAGE", "MIGRATION_RECONCILIATION_REQUIRED", "PAGE_MIGRATION_UNRESOLVED"})

    def test_mig_r4_no_saved_attempt_is_not_proof_of_no_historical_help(self):
        objects = self.import_fixture(extra_files={
            "main/40_course/C/exercises/exercise01/problems.md":
            "---\nsource_order: [exercise01-Q001]\nteaching_sequence: [exercise01-Q001]\n---\n## exercise01-Q001\n- 题面：Compute.\n"})
        exercise = objects["exercise/C/exercise01"]["data"]
        self.assertTrue(exercise["migration_requires_reconciliation"])
        self.assertEqual(exercise["assistance_status"], "unmapped_legacy_evidence_not_no_help")

    @unittest.skipUnless(importlib.util.find_spec("pymupdf"), "actual physical PDF metadata requires optional backend")
    def test_verified_page_is_usable_under_new_consumer_hash_convention(self):
        import pymupdf
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((30, 30), "Verified statement")
            render = page.get_pixmap(dpi=300).tobytes("png")
            source = doc.tobytes()
        sha, render_sha = hashlib.sha256(source).hexdigest(), hashlib.sha256(render).hexdigest()
        text = "# Page 1\n\nVerified statement.\n"
        claimed = hashlib.sha256(text.encode()).hexdigest()
        base = "main/40_course/C/book/primary"
        objects = self.import_fixture(extra_files={
            base + "/source.pdf": source, base + "/render.png": render,
            base + "/source_assets/DOC/pages/page_1.md":
            f"---\nasset_id: PAGE1\nsource_document_sha256: {sha}\nverified_text_sha256: {claimed}\nrender_sha256: {render_sha}\nverification_status: verified\nprinted_page_label: 1\n---\n{text}"})
        state = {"revision": 1, "objects": objects}
        request = {"expected": {key: value["version"] for key, value in objects.items()}}
        page = learning._page_current(state, request, "PAGE1")
        self.assertEqual(page["verified_text"], text)
        self.assertEqual(page["legacy_claimed_text_sha256"], claimed)
        self.assertEqual(page["verified_text_sha256"], learning.digest(text))
        self.assertEqual(objects["page_head/C/" + sha + "/1"]["data"]["page_id"], "PAGE1")

    def test_mig_r6_last_question_does_not_consume_following_template_fields(self):
        body = "### Q-0026｜Real question\n- 问题：First line\n  continuation stays in the real question.\n- 来源：L1\n- 状态：answered\n## 条目模板\n### Q-XXXX｜Template\n- 问题：\n- 状态：open\n"
        objects = self.import_fixture(extra_files={"main/40_course/C/question_bank.md": body})
        question = objects["question/C/Q-0026"]["data"]
        self.assertEqual(question["status"], "answered")
        self.assertIn("First line", question["text"])
        self.assertIn("continuation stays", question["text"])
        self.assertNotIn("Q-XXXX", question["original_body"])
        self.assertNotIn("question/C/Q-XXXX", objects)


if __name__ == "__main__":
    unittest.main()
