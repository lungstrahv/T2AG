#!/usr/bin/env python3
"""RB runtime: pending plan, strict confirm, preference inheritance."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_close as close
import activity_ledger as ledger


class CloseRuntimeTests(unittest.TestCase):
    def test_preference_sources_and_first_prompt_are_durable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-close-prefs-") as tmp:
            root = Path(tmp)
            profile = root / "main/10_student/profile/profile.md"
            profile.parent.mkdir(parents=True)
            profile.write_text(
                "---\ntype: student_profile\ninitialization_status: initialized\n"
                "activity_close_preference_schema: activity_close_preferences.v1\n"
                "activity_close_preferences_initialized_at: 2026-08-05T00:00:00Z\n"
                "activity_close_first_prompt_status: pending\n"
                "activity_close_first_prompt_at: none\n"
                "learning_timezone: Asia/Singapore\nlearning_day_cutoff: 04:00\n"
                "lesson_actual_review: off\nlesson_student_feedback: off\n"
                "lesson_knowledge_absorption: off\n"
                "exercise_problem_review: off\nexercise_knowledge_mastery: off\n"
                "---\n# profile\n",
                encoding="utf-8",
            )
            ledger_path = root / "main/40_course/DEMO/activity_ledger.md"
            ledger_path.parent.mkdir(parents=True)
            ledger_path.write_text(
                ledger.build_ledger_with_events(
                    "DEMO",
                    "",
                    preferences={
                        "lesson_actual_review": "inherit",
                        "lesson_student_feedback": "inherit",
                        "lesson_knowledge_absorption": "inherit",
                        "exercise_problem_review": "on",
                        "exercise_knowledge_mastery": "inherit",
                    },
                ),
                encoding="utf-8",
            )
            context = close.load_preference_context(
                root,
                "DEMO",
                {"exercise_problem_review": "off"},
            )
            self.assertEqual(context["resolved"]["exercise_problem_review"], "off")
            self.assertEqual(context["resolved"]["exercise_knowledge_mastery"], "off")
            self.assertTrue(context["first_prompt_required"])
            marked = close.mark_first_close_prompt(
                profile.read_text(encoding="utf-8"),
                recorded_at="2026-08-05T01:02:03Z",
            )
            self.assertIn("activity_close_first_prompt_status: shown", marked)
            self.assertEqual(
                close.mark_first_close_prompt(
                    marked,
                    recorded_at="2026-08-06T01:02:03Z",
                ),
                marked,
            )

    def test_pref_inheritance_once_over_course_over_global(self) -> None:
        got = close.resolve_prefs(
            {"lesson_actual_review": "off", "lesson_student_feedback": "on",
             "lesson_knowledge_absorption": "on", "exercise_problem_review": "on",
             "exercise_knowledge_mastery": "off"},
            {"lesson_actual_review": "on", "exercise_knowledge_mastery": "inherit"},
            {"lesson_actual_review": "off"},
        )
        self.assertEqual(got["lesson_actual_review"], "off")
        self.assertEqual(got["lesson_student_feedback"], "on")
        self.assertEqual(got["exercise_knowledge_mastery"], "off")

    def test_strict_confirm_requires_binding(self) -> None:
        with self.assertRaises(close.CloseError):
            close.parse_strict_confirmation("可以")
        with self.assertRaises(close.CloseError):
            close.parse_strict_confirmation("继续")
        ok = close.parse_strict_confirmation(
            "pending_event_id=ALE-000003 body_sha256="
            + ("ab" * 32)
            + " result=completed"
        )
        self.assertEqual(ok["result"], "completed")
        self.assertEqual(ok["pending_event_id"], "ALE-000003")

    def test_pending_plan_body_has_fixed_fields(self) -> None:
        plan = close.plan_pending(
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
        )
        self.assertEqual(plan["transition"]["to"], "pending_close")
        self.assertIn("body_sha256", plan["body"])
        self.assertEqual(plan["next_action"]["next_action_kind"], "confirm_close")
        self.assertIn("problem_review", plan["body"]["fixed"])

    def test_blockers_suggest_closed_incomplete(self) -> None:
        body = close.build_close_body(
            activity_type="lesson",
            activity_id="lesson01",
            prefs={k: "on" for k in close.PREF_KEYS},
            blockers=["open checkpoint"],
        )
        self.assertEqual(body["recommendation"], "closed_incomplete")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
