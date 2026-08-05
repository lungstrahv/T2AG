#!/usr/bin/env python3
"""Integrated pending/decision/CLR/reopen-policy round-trip tests."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_close as close
import activity_ledger as ledger


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def authorization(plan_path: Path, directory: Path, phase: str) -> tuple[Path, str]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    payload = {
        "campaign_id": close.CAMPAIGN_ID,
        "phase": phase,
        "state": "test_authorized",
        "authorization_mode": "test",
        "plan_id": plan["plan_id"],
        "transaction_id": plan["transaction_id"],
        "payload_sha256": plan["payload_sha256"],
        "authorization_source_sha256": "a" * 64,
    }
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"auth-{phase}.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


class CloseRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="t2ag-close-roundtrip-")
        self.root = Path(self.tmp.name) / "t2ag"
        course = self.root / "main/40_course/DEMO"
        lesson = ledger.render_migration_snapshot_event(
            event_id="ALE-000001",
            course_id="DEMO",
            activity_type="lesson",
            activity_id="lesson01",
            observed_state="ongoing",
            recorded_at="2026-08-05T00:00:00Z",
            transaction_id="MIG",
            observed_from_refs=["lesson"],
            evidence_refs=["migration"],
        )
        exercise = ledger.render_migration_snapshot_event(
            event_id="ALE-000002",
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
            observed_state="ongoing",
            recorded_at="2026-08-05T00:00:00Z",
            transaction_id="MIG",
            observed_from_refs=["exercise"],
            evidence_refs=["migration"],
        )
        write(
            course / "activity_ledger.md",
            ledger.build_ledger_with_events("DEMO", lesson + "\n" + exercise),
        )
        write(
            course / "progress.md",
            "---\ntype: course_progress\ncourse_id: DEMO\n"
            "lifecycle_status: ongoing\ncourse_driver: textbook\n"
            "truth_scope: course_lifecycle,course_frontend,activity_position\n"
            "current_activity: exercise\ncurrent_activity_id: exercise01\n"
            "resume_path: main/40_course/DEMO/exercises/exercise01/exercise.md\n"
            "activity_position: finished-evidence\n"
            "next_action_kind: resume\nnext_activity_type: exercise\n"
            "next_activity_id: exercise01\nupdated: 2026-08-05\n"
            "current_completion_node: N1\ncurrent_checkpoint: C1\n"
            "checkpoint_state: confirmed\n---\n# progress\n",
        )
        write(course / "exercises/exercise01/exercise.md", "# exercise\n")
        os.environ["T2AG_022_CLOSE_TEST"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("T2AG_022_CLOSE_TEST", None)
        self.tmp.cleanup()

    def make_pending(self, *, blockers: list[str] | None = None) -> tuple[Path, dict]:
        plan_path = Path(self.tmp.name) / f"pending-{len(list(Path(self.tmp.name).glob('pending-*')))}.json"
        result = close.materialize_pending_plan(
            self.root,
            plan_path,
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
            prefs={key: "on" for key in close.PREF_KEYS},
            knowledge=[{"topic": "sets", "state": "independent_confirmed"}],
            blockers=blockers or [],
            evidence_refs=["attempts/AT0001", "reviews/RV0001"],
            student_feedback_ref="exercise_thoughts.md#ET-1",
        )
        auth_path, auth_sha = authorization(plan_path, Path(self.tmp.name), "F0_PENDING")
        applied = close.apply_close_plan(
            self.root,
            plan_path,
            expect_payload_sha=result["payload_sha256"],
            expect_file_sha=result["file_sha256"],
            authorization_receipt=auth_path,
            expect_authorization_sha=auth_sha,
        )
        self.assertEqual(applied["status"], "committed")
        return plan_path, result

    def test_completed_round_trip_keeps_background_lesson(self) -> None:
        pending_path, pending = self.make_pending()
        self.assertTrue(pending["details"]["body_sha256"])
        doc = ledger.load_ledger(
            self.root / "main/40_course/DEMO/activity_ledger.md"
        )
        self.assertEqual(doc.rebuild_index()["exercise:exercise01"].state, "pending_close")
        self.assertEqual(
            pending["details"]["decision_recommendation"], "confirm_completed"
        )
        decision_path = Path(self.tmp.name) / "decision.json"
        decision = close.materialize_decision_plan(
            self.root,
            decision_path,
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
            pending_event_id=pending["details"]["pending_event_id"],
            body_sha256=pending["details"]["body_sha256"],
            decision="confirm_completed",
            authorization_source_sha256="a" * 64,
            delegated_quote="continuous delegation",
        )
        auth_path, auth_sha = authorization(
            decision_path, Path(self.tmp.name), "F_AUTHORIZED"
        )
        applied = close.apply_close_plan(
            self.root,
            decision_path,
            expect_payload_sha=decision["payload_sha256"],
            expect_file_sha=decision["file_sha256"],
            authorization_receipt=auth_path,
            expect_authorization_sha=auth_sha,
        )
        self.assertEqual(applied["details"]["result"], "completed")
        doc = ledger.load_ledger(
            self.root / "main/40_course/DEMO/activity_ledger.md"
        )
        index = doc.rebuild_index()
        self.assertEqual(index["exercise:exercise01"].state, "completed")
        self.assertEqual(index["lesson:lesson01"].state, "ongoing")
        self.assertEqual(len(doc.closes), 1)
        self.assertEqual(doc.closes[0]["decision_actor"], "delegated_operator")
        progress = (
            self.root / "main/40_course/DEMO/progress.md"
        ).read_text(encoding="utf-8")
        self.assertIn("current_activity: none", progress)
        self.assertIn("activity_position: between_activities", progress)
        self.assertIn("next_activity_id: lesson01", progress)

        reopen_path = Path(self.tmp.name) / "reopen.json"
        reopen = close.materialize_reopen_plan(
            self.root,
            reopen_path,
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
        )
        reopen_auth, reopen_auth_sha = authorization(
            reopen_path, Path(self.tmp.name) / "reopen-auth", "F_AUTHORIZED"
        )
        close.apply_close_plan(
            self.root,
            reopen_path,
            expect_payload_sha=reopen["payload_sha256"],
            expect_file_sha=reopen["file_sha256"],
            authorization_receipt=reopen_auth,
            expect_authorization_sha=reopen_auth_sha,
        )
        reopened_doc = ledger.load_ledger(
            self.root / "main/40_course/DEMO/activity_ledger.md"
        )
        self.assertEqual(
            reopened_doc.rebuild_index()["exercise:exercise01"].state,
            "ongoing",
        )
        history = close.close_history(reopened_doc)
        self.assertEqual(len(history), 1)
        self.assertTrue(history[0]["historical"])
        self.assertTrue(history[0]["reopened"])
        self.assertEqual(reopened_doc.stats["completed_exercises"], "0")
        self.assertEqual(
            reopened_doc.stats["historical_completed_exercises"], "1"
        )

    def test_blocker_forces_closed_incomplete_policy(self) -> None:
        _, pending = self.make_pending(blockers=["required checkpoint unresolved"])
        self.assertEqual(
            pending["details"]["decision_recommendation"],
            "confirm_closed_incomplete",
        )
        with self.assertRaisesRegex(close.CloseError, "deterministic policy"):
            close.materialize_decision_plan(
                self.root,
                Path(self.tmp.name) / "wrong.json",
                course_id="DEMO",
                activity_type="exercise",
                activity_id="exercise01",
                pending_event_id=pending["details"]["pending_event_id"],
                body_sha256=pending["details"]["body_sha256"],
                decision="confirm_completed",
                authorization_source_sha256="a" * 64,
                delegated_quote="continuous delegation",
            )

    def test_direct_user_confirmation_is_exact_and_preserved(self) -> None:
        _, pending = self.make_pending()
        strict = (
            f"pending_event_id={pending['details']['pending_event_id']}\n"
            f"body_sha256={pending['details']['body_sha256']}\n"
            "result=completed\n用户直接确认"
        )
        with self.assertRaisesRegex(close.CloseError, "exact confirmation"):
            close.materialize_decision_plan(
                self.root,
                Path(self.tmp.name) / "direct-missing.json",
                course_id="DEMO",
                activity_type="exercise",
                activity_id="exercise01",
                pending_event_id=pending["details"]["pending_event_id"],
                body_sha256=pending["details"]["body_sha256"],
                decision="confirm_completed",
                authorization_source_sha256="b" * 64,
                delegated_quote=strict,
                decision_actor="user",
                authorization_mode="direct_user",
            )
        plan_path = Path(self.tmp.name) / "direct.json"
        result = close.materialize_decision_plan(
            self.root,
            plan_path,
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
            pending_event_id=pending["details"]["pending_event_id"],
            body_sha256=pending["details"]["body_sha256"],
            decision="confirm_completed",
            authorization_source_sha256="b" * 64,
            delegated_quote=strict,
            decision_actor="user",
            authorization_mode="direct_user",
            strict_confirmation_text=strict,
        )
        auth_path, auth_sha = authorization(
            plan_path, Path(self.tmp.name) / "direct-auth", "F_AUTHORIZED"
        )
        close.apply_close_plan(
            self.root,
            plan_path,
            expect_payload_sha=result["payload_sha256"],
            expect_file_sha=result["file_sha256"],
            authorization_receipt=auth_path,
            expect_authorization_sha=auth_sha,
        )
        doc = ledger.load_ledger(self.root / "main/40_course/DEMO/activity_ledger.md")
        self.assertEqual(doc.closes[0]["decision_actor"], "user")
        self.assertEqual(doc.closes[0]["authorization_mode"], "direct_user")
        self.assertEqual(
            __import__("base64").b64decode(doc.closes[0]["authorization_quote_b64"]).decode(),
            strict,
        )

    def test_refusal_returns_ongoing_without_clr(self) -> None:
        _, pending = self.make_pending()
        plan_path = Path(self.tmp.name) / "refuse.json"
        result = close.materialize_decision_plan(
            self.root,
            plan_path,
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
            pending_event_id=pending["details"]["pending_event_id"],
            body_sha256=pending["details"]["body_sha256"],
            decision="refuse",
            authorization_source_sha256="a" * 64,
            delegated_quote="continuous delegation",
        )
        auth_path, auth_sha = authorization(plan_path, Path(self.tmp.name), "F_AUTHORIZED")
        close.apply_close_plan(
            self.root,
            plan_path,
            expect_payload_sha=result["payload_sha256"],
            expect_file_sha=result["file_sha256"],
            authorization_receipt=auth_path,
            expect_authorization_sha=auth_sha,
        )
        doc = ledger.load_ledger(self.root / "main/40_course/DEMO/activity_ledger.md")
        self.assertEqual(doc.rebuild_index()["exercise:exercise01"].state, "ongoing")
        self.assertEqual(doc.closes, [])

    def test_revision_appends_new_pending_version(self) -> None:
        _, pending = self.make_pending()
        with self.assertRaisesRegex(close.CloseError, "substantive revision_patch"):
            close.materialize_decision_plan(
                self.root,
                Path(self.tmp.name) / "empty-revision.json",
                course_id="DEMO",
                activity_type="exercise",
                activity_id="exercise01",
                pending_event_id=pending["details"]["pending_event_id"],
                body_sha256=pending["details"]["body_sha256"],
                decision="revise",
                authorization_source_sha256="a" * 64,
                delegated_quote="continuous delegation",
            )
        plan_path = Path(self.tmp.name) / "revise.json"
        result = close.materialize_decision_plan(
            self.root,
            plan_path,
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
            pending_event_id=pending["details"]["pending_event_id"],
            body_sha256=pending["details"]["body_sha256"],
            decision="revise",
            authorization_source_sha256="a" * 64,
            delegated_quote="continuous delegation",
            revision_patch={
                "content_sections": {
                    "problem_review": {"summary": "学生补充了 Q002 的证明回顾"}
                }
            },
        )
        auth_path, auth_sha = authorization(plan_path, Path(self.tmp.name), "F_AUTHORIZED")
        close.apply_close_plan(
            self.root,
            plan_path,
            expect_payload_sha=result["payload_sha256"],
            expect_file_sha=result["file_sha256"],
            authorization_receipt=auth_path,
            expect_authorization_sha=auth_sha,
        )
        doc = ledger.load_ledger(self.root / "main/40_course/DEMO/activity_ledger.md")
        revisions = [e for e in doc.events if e.get("event_kind") == "pending_revision"]
        self.assertEqual(len(revisions), 1)
        self.assertEqual(
            revisions[0]["revises_event_id"], pending["details"]["pending_event_id"]
        )
        revised_body = close.decode_body(revisions[0])
        self.assertEqual(
            revised_body["fixed"]["problem_review"]["summary"],
            "学生补充了 Q002 的证明回顾",
        )
        plain = ledger.load_ledger(self.root / "main/40_course/DEMO/activity_ledger.md")
        next(e for e in plain.events if e.get("event_kind") == "pending_revision")[
            "event_kind"
        ] = "transition"
        self.assertTrue(any("illegal transition" in error for error in plain.validate()))
        cross = ledger.load_ledger(self.root / "main/40_course/DEMO/activity_ledger.md")
        next(e for e in cross.events if e.get("event_kind") == "pending_revision")[
            "activity_id"
        ] = "exercise02"
        self.assertTrue(any("revision linkage" in error for error in cross.validate()))

    def test_postcheck_failure_rolls_back_both_files(self) -> None:
        plan_path = Path(self.tmp.name) / "rollback.json"
        result = close.materialize_pending_plan(
            self.root,
            plan_path,
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
            prefs={key: "on" for key in close.PREF_KEYS},
            knowledge=[{"topic": "sets", "state": "partial"}],
            blockers=[],
            evidence_refs=["AT"],
            student_feedback_ref="feedback",
        )
        auth_path, auth_sha = authorization(plan_path, Path(self.tmp.name), "F0_PENDING")
        ledger_path = self.root / "main/40_course/DEMO/activity_ledger.md"
        progress_path = self.root / "main/40_course/DEMO/progress.md"
        before = (ledger_path.read_bytes(), progress_path.read_bytes())
        with patch.object(close, "run_postchecks", side_effect=close.CloseError("boom")):
            with self.assertRaisesRegex(close.CloseError, "boom"):
                close.apply_close_plan(
                    self.root,
                    plan_path,
                    expect_payload_sha=result["payload_sha256"],
                    expect_file_sha=result["file_sha256"],
                    authorization_receipt=auth_path,
                    expect_authorization_sha=auth_sha,
                )
        self.assertEqual(
            (ledger_path.read_bytes(), progress_path.read_bytes()),
            before,
        )

    def test_tampered_pending_and_duplicate_close_are_rejected(self) -> None:
        _, pending = self.make_pending()
        decision_path = Path(self.tmp.name) / "tamper-decision.json"
        decision = close.materialize_decision_plan(
            self.root,
            decision_path,
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
            pending_event_id=pending["details"]["pending_event_id"],
            body_sha256=pending["details"]["body_sha256"],
            decision="confirm_completed",
            authorization_source_sha256="a" * 64,
            delegated_quote="continuous delegation",
        )
        auth_path, auth_sha = authorization(
            decision_path, Path(self.tmp.name) / "tamper-auth", "F_AUTHORIZED"
        )
        close.apply_close_plan(
            self.root,
            decision_path,
            expect_payload_sha=decision["payload_sha256"],
            expect_file_sha=decision["file_sha256"],
            authorization_receipt=auth_path,
            expect_authorization_sha=auth_sha,
        )
        ledger_path = self.root / "main/40_course/DEMO/activity_ledger.md"

        tampered = ledger.load_ledger(ledger_path)
        pending_event = next(
            event
            for event in tampered.events
            if event.get("event_id") == pending["details"]["pending_event_id"]
        )
        pending_event["pending_body_sha256"] = "0" * 64
        self.assertTrue(any("pending body SHA mismatch" in error for error in tampered.validate()))

        duplicated = ledger.load_ledger(ledger_path)
        duplicate_close = dict(duplicated.closes[0])
        duplicate_close["close_id"] = "CLR-0002"
        duplicate_close["_header_id"] = "CLR-0002"
        duplicated.closes.append(duplicate_close)
        self.assertTrue(
            any("duplicate CLR pending_event_id" in error for error in duplicated.validate())
        )

        broken_link = ledger.load_ledger(ledger_path)
        terminal = next(
            event
            for event in broken_link.events
            if event.get("to_state") == "completed"
        )
        terminal["confirmed_pending_event_id"] = "ALE-999999"
        self.assertTrue(
            any("terminal event linkage invalid" in error for error in broken_link.validate())
        )
        body_tamper = ledger.load_ledger(ledger_path)
        body_tamper.closes[0]["body_json_b64"] = close.b64_json({"body_sha256": "0" * 64})
        self.assertTrue(any("body snapshot" in error for error in body_tamper.validate()))
        next_tamper = ledger.load_ledger(ledger_path)
        next_tamper.closes[0]["next_activity_at_close_b64"] = close.b64_json(
            {"current_activity": "exercise"}
        )
        self.assertTrue(any("next activity snapshot" in error for error in next_tamper.validate()))


class ClosePureContractTests(unittest.TestCase):
    def test_preference_precedence_and_optional_sections(self) -> None:
        global_prefs = {key: "on" for key in close.PREF_KEYS}
        course_prefs = {key: "inherit" for key in close.PREF_KEYS}
        course_prefs["exercise_problem_review"] = "off"
        once = {"exercise_problem_review": "on", "exercise_knowledge_mastery": "off"}
        resolved = close.resolve_prefs(global_prefs, course_prefs, once)
        self.assertEqual(resolved["exercise_problem_review"], "on")
        self.assertEqual(resolved["exercise_knowledge_mastery"], "off")
        body = close.build_close_body(
            activity_type="exercise",
            activity_id="exercise01",
            prefs=resolved,
            knowledge=[{"topic": "x", "state": "unverified"}],
            evidence_refs=["e"],
            student_feedback_ref="f",
        )
        self.assertIn("practice_evaluation", body["optional"])
        self.assertNotIn("study_suggestions", body["optional"])
        self.assertEqual(body["fixed"]["student_feedback"]["status"], "captured")

    def test_vague_confirmation_rejected(self) -> None:
        with self.assertRaises(close.CloseError):
            close.parse_strict_confirmation("可以")

    def test_learning_day_cutoff_endpoint(self) -> None:
        self.assertEqual(
            close.learning_day("2026-08-05T02:59:59+08:00", "Asia/Singapore", "03:00"),
            "2026-08-04",
        )
        self.assertEqual(
            close.learning_day("2026-08-05T03:00:00+08:00", "Asia/Singapore", "03:00"),
            "2026-08-05",
        )

    def test_duration_modes_stay_separate(self) -> None:
        totals = close.duration_totals(
            [
                {"duration_mode": "exact", "minutes": 20},
                {"duration_mode": "estimated", "minutes": 30},
                {"duration_mode": "unknown", "minutes": None},
            ]
        )
        self.assertEqual(totals, {
            "exact_minutes": 20,
            "estimated_minutes": 30,
            "unknown_spans": 1,
        })
        with self.assertRaisesRegex(close.CloseError, "unknown duration"):
            close.duration_totals(
                [{"duration_mode": "unknown", "minutes": 5}]
            )

    def test_five_knowledge_states_scope_confirmation_and_fixed_body(self) -> None:
        knowledge = [
            {"topic": state, "state": state}
            for state in sorted(close.KNOWLEDGE_STATES)
        ]
        all_off = {key: "off" for key in close.PREF_KEYS}
        unconfirmed = close.build_close_body(
            activity_type="lesson",
            activity_id="lesson01",
            prefs=all_off,
            knowledge=knowledge,
            evidence_refs=["lesson evidence"],
            student_feedback_ref="feedback",
            scope_change={"from": "chapter", "to": "section"},
        )
        self.assertEqual(unconfirmed["recommendation"], "closed_incomplete")
        self.assertIn("unconfirmed_scope_change", unconfirmed["completion_blockers"])
        self.assertEqual(unconfirmed["optional"], {})
        self.assertEqual(
            set(unconfirmed["fixed"]),
            {"actual_review", "student_feedback", "knowledge_absorption"},
        )
        confirmed = close.build_close_body(
            activity_type="exercise",
            activity_id="exercise01",
            prefs=all_off,
            knowledge=knowledge,
            evidence_refs=["exercise evidence"],
            student_feedback_ref="feedback",
            scope_change={"from": "chapter", "to": "section"},
            scope_change_confirmed=True,
        )
        self.assertEqual(confirmed["recommendation"], "completed")
        self.assertEqual(
            set(confirmed["fixed"]),
            {"problem_review", "knowledge_mastery", "student_feedback"},
        )
        with self.assertRaisesRegex(close.CloseError, "illegal knowledge state"):
            close.build_close_body(
                activity_type="exercise",
                activity_id="exercise01",
                prefs=all_off,
                knowledge=[{"topic": "x", "state": "correct_rate_100"}],
            )


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
