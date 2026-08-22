#!/usr/bin/env python3
"""Integrated non-close lifecycle, routing, learning-day and duration tests."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_close as close
import activity_ledger as ledger
import activity_lifecycle as lifecycle


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


class LifecycleRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="t2ag-022-lifecycle-")
        self.root = Path(self.temp.name) / "t2ag"
        course = self.root / "main/40_course/DEMO"
        events = []
        for number, kind, activity_id in (
            (1, "lesson", "lesson01"),
            (2, "exercise", "exercise01"),
        ):
            events.append(
                ledger.render_migration_snapshot_event(
                    event_id=f"ALE-{number:06d}",
                    course_id="DEMO",
                    activity_type=kind,
                    activity_id=activity_id,
                    observed_state="ongoing",
                    recorded_at="2026-08-05T00:00:00Z",
                    transaction_id="MIG",
                    observed_from_refs=[activity_id],
                    evidence_refs=["migration"],
                )
            )
        write(course / "activity_ledger.md", ledger.build_ledger_with_events("DEMO", "\n".join(events)))
        write(
            course / "progress.md",
            "---\ntype: course_progress\ncourse_id: DEMO\nlifecycle_status: ongoing\n"
            "course_driver: goal\ntruth_scope: course_lifecycle,course_frontend,activity_position\n"
            "current_activity: exercise\ncurrent_activity_id: exercise01\n"
            "resume_path: main/40_course/DEMO/exercises/exercise01/exercise.md\n"
            "activity_position: checkpoint\nnext_action_kind: resume\n"
            "next_activity_type: exercise\nnext_activity_id: exercise01\nupdated: 2026-08-05\n---\n"
            "# progress\n\n- **下一步计划**：resume exercise:exercise01；以结构化 next_action_* 字段为准。\n",
        )
        write(
            self.root / "main/10_student/profile/profile.md",
            "---\nlearning_timezone: Asia/Singapore\nlearning_day_cutoff: 04:00\n---\n# profile\n",
        )
        write(course / "lessons/lesson01/lesson01.md", "# lesson\n")
        write(course / "exercises/exercise01/exercise.md", "# exercise\n")
        os.environ["T2AG_022_CLOSE_TEST"] = "1"
        self.counter = 0

    def tearDown(self) -> None:
        os.environ.pop("T2AG_022_CLOSE_TEST", None)
        self.temp.cleanup()

    def plan_apply(self, **kwargs: object) -> dict:
        self.counter += 1
        plan_path = Path(self.temp.name) / f"plan-{self.counter}.json"
        result = lifecycle.materialize_lifecycle_plan(
            self.root,
            plan_path,
            course_id="DEMO",
            activity_type=str(kwargs.pop("activity_type", "exercise")),
            activity_id=str(kwargs.pop("activity_id", "exercise01")),
            **kwargs,
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        auth = {
            "campaign_id": close.CAMPAIGN_ID,
            "phase": "F_AUTHORIZED",
            "state": "test_authorized",
            "authorization_mode": "test",
            "authorization_source_sha256": "a" * 64,
            "plan_id": plan["plan_id"],
            "transaction_id": plan["transaction_id"],
            "payload_sha256": plan["payload_sha256"],
        }
        raw = (json.dumps(auth, sort_keys=True) + "\n").encode()
        auth_path = Path(self.temp.name) / f"auth-{self.counter}.json"
        auth_path.write_bytes(raw)
        applied = close.apply_close_plan(
            self.root,
            plan_path,
            expect_payload_sha=result["payload_sha256"],
            expect_file_sha=result["file_sha256"],
            authorization_receipt=auth_path,
            expect_authorization_sha=hashlib.sha256(raw).hexdigest(),
        )
        self.assertEqual(applied["status"], "committed")
        return result

    def test_foreground_pause_resume_and_next_action_real_consumer(self) -> None:
        self.plan_apply(
            event_kind="foreground_switch",
            target_activity_type="lesson",
            target_activity_id="lesson01",
        )
        progress = (self.root / "main/40_course/DEMO/progress.md").read_text(encoding="utf-8")
        self.assertIn("current_activity_id: lesson01", progress)
        self.plan_apply(
            activity_type="lesson",
            activity_id="lesson01",
            event_kind="transition",
            to_state="paused",
        )
        progress = (self.root / "main/40_course/DEMO/progress.md").read_text(encoding="utf-8")
        self.assertIn("current_activity: none", progress)
        self.assertIn("next_activity_id: exercise01", progress)
        self.plan_apply(
            activity_type="lesson",
            activity_id="lesson01",
            event_kind="transition",
            to_state="ongoing",
        )
        doc = ledger.load_ledger(self.root / "main/40_course/DEMO/activity_ledger.md")
        self.assertEqual(doc.rebuild_index()["lesson:lesson01"].state, "ongoing")

    def test_learning_enter_exit_persists_cutoff_day_and_duration_stats(self) -> None:
        self.plan_apply(event_kind="learning_enter", learning_span_id="SPAN-1")
        self.plan_apply(
            event_kind="learning_exit",
            learning_span_id="SPAN-1",
            duration_mode="estimated",
            duration_minutes=12,
        )
        doc = ledger.load_ledger(self.root / "main/40_course/DEMO/activity_ledger.md")
        self.assertEqual(doc.validate(), [])
        self.assertEqual(doc.stats["learning_estimated_minutes"], "12")
        exit_event = next(e for e in doc.events if e.get("event_kind") == "learning_exit")
        self.assertRegex(str(exit_event.get("learning_day")), r"^\d{4}-\d{2}-\d{2}$")

    def test_close_transitions_and_invalid_duration_are_zero_write(self) -> None:
        before = (self.root / "main/40_course/DEMO/activity_ledger.md").read_bytes()
        with self.assertRaisesRegex(close.CloseError, "refuses transition"):
            lifecycle.materialize_lifecycle_plan(
                self.root,
                Path(self.temp.name) / "forbidden.json",
                course_id="DEMO",
                activity_type="exercise",
                activity_id="exercise01",
                event_kind="transition",
                to_state="completed",
            )
        with self.assertRaisesRegex(close.CloseError, "unknown duration"):
            lifecycle.materialize_lifecycle_plan(
                self.root,
                Path(self.temp.name) / "duration.json",
                course_id="DEMO",
                activity_type="exercise",
                activity_id="exercise01",
                event_kind="learning_exit",
                learning_span_id="SPAN-X",
                duration_mode="unknown",
                duration_minutes=1,
            )
        self.assertEqual(
            (self.root / "main/40_course/DEMO/activity_ledger.md").read_bytes(), before
        )


if __name__ == "__main__":
    unittest.main()
