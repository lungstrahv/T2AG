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


def exact_confirmation(pending: dict, result: str) -> str:
    return (
        f"pending_event_id={pending['details']['pending_event_id']}\n"
        f"body_sha256={pending['details']['body_sha256']}\n"
        f"result={result}"
    )


def presented_retrospective_sha(pending: dict) -> str:
    return close.learner_retrospective_sha256(pending["details"]["body"])


def fully_assessed_content() -> dict:
    retrospective = {}
    for section, leaves in close.RETROSPECTIVE_TREE.items():
        retrospective[section] = {
            "items": {
                leaf: {
                    "status": "applicable",
                    "summary": f"evidence-backed {section}.{leaf}",
                    "evidence_refs": ["evidence"],
                }
                for leaf in leaves
            }
        }
    return {
        "close_scope": {
            "status": "applicable",
            "summary": "activity scope frozen",
        },
        "evidence_collection": {
            "status": "applicable",
            "summary": "evidence collected",
        },
        "teaching_retrospective": retrospective,
    }


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


def production_authorization(
    plan_path: Path, directory: Path, *, mode: str = "direct_user"
) -> tuple[Path, str]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    details = plan["details"]
    payload = {
        "campaign_id": close.CAMPAIGN_ID,
        "phase": "F_AUTHORIZED",
        "state": "direct_user_authorized",
        "authorization_mode": mode,
        "decision_actor": "user",
        "authorization_procedure_status": "valid_direct_user",
        "authorization_source_sha256": details["authorization_source_sha256"],
        "authorization_quote_sha256": details["authorization_quote_sha256"],
        "strict_confirmation_sha256": details["strict_confirmation_sha256"],
        "plan_id": plan["plan_id"],
        "transaction_id": plan["transaction_id"],
        "payload_sha256": plan["payload_sha256"],
    }
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"production-auth-{mode}.json"
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
            content_sections=fully_assessed_content(),
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
        self.assertEqual(doc.events[-1]["triggered_by"], "activity_close_tool")
        decision_path = Path(self.tmp.name) / "decision.json"
        strict = exact_confirmation(pending, "completed")
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
            delegated_quote=strict,
            decision_actor="user",
            authorization_mode="direct_user",
            strict_confirmation_text=strict,
            presented_retrospective_sha256=presented_retrospective_sha(pending),
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
        self.assertEqual(doc.closes[0]["decision_actor"], "user")
        self.assertEqual(
            doc.closes[0]["authorization_procedure_status"],
            "valid_direct_user",
        )
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
        self.assertEqual(reopened_doc.events[-1]["triggered_by"], "activity_close_tool")
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
                delegated_quote="direct user request",
                decision_actor="user",
                authorization_mode="direct_user",
            )

    def test_direct_user_confirmation_is_exact_and_preserved(self) -> None:
        _, pending = self.make_pending()
        strict = exact_confirmation(pending, "completed")
        common = {
            "course_id": "DEMO",
            "activity_type": "exercise",
            "activity_id": "exercise01",
            "pending_event_id": pending["details"]["pending_event_id"],
            "body_sha256": pending["details"]["body_sha256"],
            "decision": "confirm_completed",
            "authorization_source_sha256": "b" * 64,
            "delegated_quote": strict,
            "presented_retrospective_sha256": presented_retrospective_sha(pending),
        }
        with self.assertRaisesRegex(close.CloseError, "must be explicit"):
            close.materialize_decision_plan(
                self.root, Path(self.tmp.name) / "missing-authority.json", **common
            )
        with self.assertRaisesRegex(close.CloseError, "require user"):
            close.materialize_decision_plan(
                self.root,
                Path(self.tmp.name) / "delegated-authority.json",
                **common,
                decision_actor="delegated_operator",
                authorization_mode="user_continuous_delegation",
            )
        with self.assertRaisesRegex(close.CloseError, "confirmation text"):
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
                presented_retrospective_sha256=presented_retrospective_sha(pending),
            )
        with self.assertRaisesRegex(close.CloseError, "presented in dialogue first"):
            close.materialize_decision_plan(
                self.root,
                Path(self.tmp.name) / "direct-not-presented.json",
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
        with self.assertRaisesRegex(close.CloseError, "bound close intent"):
            close.materialize_decision_plan(
                self.root,
                Path(self.tmp.name) / "direct-extra-text.json",
                course_id="DEMO",
                activity_type="exercise",
                activity_id="exercise01",
                pending_event_id=pending["details"]["pending_event_id"],
                body_sha256=pending["details"]["body_sha256"],
                decision="confirm_completed",
                authorization_source_sha256="b" * 64,
                delegated_quote=strict + "\n用户直接确认",
                decision_actor="user",
                authorization_mode="direct_user",
                strict_confirmation_text=strict + "\n用户直接确认",
                presented_retrospective_sha256=presented_retrospective_sha(pending),
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
            presented_retrospective_sha256=presented_retrospective_sha(pending),
        )
        direct_auth, direct_auth_sha = production_authorization(
            plan_path, Path(self.tmp.name) / "production-direct"
        )
        delegated_auth, delegated_auth_sha = production_authorization(
            plan_path,
            Path(self.tmp.name) / "production-delegated",
            mode="user_continuous_delegation",
        )
        with patch.object(close, "PRODUCTION_ROOT", self.root.resolve()):
            validated = close.validate_authorization(
                self.root,
                json.loads(plan_path.read_text(encoding="utf-8")),
                auth_path=direct_auth,
                expect_auth_sha=direct_auth_sha,
            )
            self.assertEqual(validated["authorization_mode"], "direct_user")
            with self.assertRaisesRegex(close.CloseError, "unsupported"):
                close.validate_authorization(
                    self.root,
                    json.loads(plan_path.read_text(encoding="utf-8")),
                    auth_path=delegated_auth,
                    expect_auth_sha=delegated_auth_sha,
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
        self.assertNotIn("delegated_quote_sha256", doc.closes[0])
        self.assertEqual(
            __import__("base64").b64decode(doc.closes[0]["authorization_quote_b64"]).decode(),
            strict,
        )

    def test_bound_close_intent_uses_shown_tuple_without_copying(self) -> None:
        _, pending = self.make_pending()
        plan_path = Path(self.tmp.name) / "bound-close-intent.json"
        result = close.materialize_decision_plan(
            self.root,
            plan_path,
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
            pending_event_id=pending["details"]["pending_event_id"],
            body_sha256=pending["details"]["body_sha256"],
            decision="confirm_completed",
            authorization_source_sha256="c" * 64,
            delegated_quote="结课",
            decision_actor="user",
            authorization_mode="direct_user",
            strict_confirmation_text="结课",
            presented_retrospective_sha256=presented_retrospective_sha(pending),
        )
        self.assertEqual(result["details"]["confirmation_mode"], "bound_close_intent")

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
            delegated_quote="direct user refusal",
            decision_actor="user",
            authorization_mode="direct_user",
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
                delegated_quote="direct user revision request",
                decision_actor="user",
                authorization_mode="direct_user",
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
            delegated_quote="direct user revision request",
            decision_actor="user",
            authorization_mode="direct_user",
            revision_patch={
                "content_sections": {
                    "teaching_retrospective": {
                        **fully_assessed_content()["teaching_retrospective"],
                        "actual_teaching_process": {
                            **fully_assessed_content()["teaching_retrospective"]["actual_teaching_process"],
                            "summary": "学生补充了 Q002 的证明回顾",
                        },
                    }
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
            revised_body["teaching_retrospective"]["actual_teaching_process"]["summary"],
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
            content_sections=fully_assessed_content(),
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
        strict = exact_confirmation(pending, "completed")
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
            delegated_quote=strict,
            decision_actor="user",
            authorization_mode="direct_user",
            strict_confirmation_text=strict,
            presented_retrospective_sha256=presented_retrospective_sha(pending),
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
    def test_preference_sources_and_first_prompt_are_durable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-close-prefs-") as tmp:
            root = Path(tmp)
            profile = root / "main/10_student/profile/profile.md"
            write(
                profile,
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
            )
            ledger_path = root / "main/40_course/DEMO/activity_ledger.md"
            write(
                ledger_path,
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

    def test_preference_precedence_does_not_change_applicability(self) -> None:
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
            content_sections=fully_assessed_content(),
        )
        self.assertEqual(body["schema"], close.CLOSE_BODY_SCHEMA)
        self.assertEqual(body["preferences_snapshot"], resolved)
        self.assertEqual(
            body["teaching_retrospective"]["course_content_feedback"]["status"],
            "applicable",
        )
        self.assertEqual(body["recommendation"], "completed")

    def test_learner_retrospective_is_complete_dialogue_payload(self) -> None:
        body = close.build_close_body(
            activity_type="lesson",
            activity_id="lesson01",
            prefs={key: "on" for key in close.PREF_KEYS},
            knowledge=[{"topic": "sets", "state": "partial"}],
            evidence_refs=["lesson evidence"],
            content_sections=fully_assessed_content(),
        )
        rendered = close.render_learner_retrospective(body)
        for marker in (
            "# lesson01 教学复盘",
            "## 知识吸收",
            "## 学生课程内容反馈",
            "## 完成性判定",
            close.learner_retrospective_sha256(body),
        ):
            self.assertIn(marker, rendered)
        self.assertNotIn("规定范围内没有未完成内容", rendered)

    def test_vague_confirmation_rejected(self) -> None:
        with self.assertRaises(close.CloseError):
            close.parse_strict_confirmation("可以")
        with self.assertRaises(close.CloseError):
            close.parse_strict_confirmation("继续")
        parsed = close.parse_strict_confirmation(
            "pending_event_id=ALE-000003\nbody_sha256="
            + ("ab" * 32)
            + "\nresult=completed"
        )
        self.assertEqual(parsed["pending_event_id"], "ALE-000003")
        self.assertEqual(parsed["result"], "completed")
        bound = close.parse_bound_close_confirmation(
            "结课",
            pending_event_id="ALE-000003",
            body_sha256="ab" * 32,
            result="completed",
        )
        self.assertEqual(bound["confirmation_mode"], "bound_close_intent")
        with self.assertRaisesRegex(close.CloseError, "bound close intent"):
            close.parse_bound_close_confirmation(
                "结课",
                pending_event_id="ALE-000003",
                body_sha256="ab" * 32,
                result="closed_incomplete",
            )
        incomplete = close.parse_bound_close_confirmation(
            "以未完成状态结课",
            pending_event_id="ALE-000003",
            body_sha256="ab" * 32,
            result="closed_incomplete",
        )
        self.assertEqual(
            incomplete["confirmation_mode"],
            "bound_incomplete_close_intent",
        )
        commented = close.parse_bound_close_confirmation(
            "pending_event_id=ALE-000003\nbody_sha256="
            + ("ab" * 32)
            + "\nresult=completed我为什么不能回复结课",
            pending_event_id="ALE-000003",
            body_sha256="ab" * 32,
            result="completed",
        )
        self.assertEqual(commented["confirmation_mode"], "tuple_with_close_intent")

    def test_pending_plan_body_has_full_tree_and_exposes_missing(self) -> None:
        plan = close.plan_pending(
            course_id="DEMO",
            activity_type="exercise",
            activity_id="exercise01",
        )
        self.assertEqual(plan["transition"]["to"], "pending_close")
        self.assertIn("body_sha256", plan["body"])
        self.assertEqual(plan["next_action"]["next_action_kind"], "confirm_close")
        self.assertEqual(plan["body"]["schema"], close.CLOSE_BODY_SCHEMA)
        self.assertEqual(
            set(plan["body"]["teaching_retrospective"]),
            set(close.RETROSPECTIVE_TREE),
        )
        self.assertFalse(
            plan["body"]["mandatory_evidence"]["retrospective_tree_complete"]
        )

    def test_terminal_progress_clears_lesson_page_state(self) -> None:
        progress = (
            "---\n"
            "type: course_progress\n"
            "course_id: DEMO\n"
            "current_activity: lesson\n"
            "current_activity_id: lesson01\n"
            "resume_path: main/40_course/DEMO/lessons/lesson01/lesson01.md\n"
            "activity_position: page 28\n"
            "textbook_page: 28\n"
            "working_pages_window: [25, 26, 27, 28]\n"
            "current_completion_node: DEMO-N01\n"
            "current_checkpoint: DEMO-P01\n"
            "checkpoint_state: confirmed\n"
            "---\n"
            "# progress\n\n"
            "## 二、当前进度\n\n"
            "- **Lesson 上下文**：当前前台为 `lesson01`；恢复与写回均使用其 canonical 主载体。\n"
            "- **下一步计划**：confirm_close lesson:lesson01\n"
        )
        updated = close.update_progress(
            progress,
            activity_type="lesson",
            activity_id="lesson01",
            state="completed",
            next_action={
                "next_action_kind": "choose_activity",
                "next_activity_type": "none",
                "next_activity_id": "none",
            },
        )
        meta, _order, _body = close.frontmatter_split(updated)
        for key in (
            "current_activity",
            "current_activity_id",
            "resume_path",
            "textbook_page",
            "current_completion_node",
            "current_checkpoint",
            "checkpoint_state",
        ):
            self.assertEqual(meta[key], "none")
        self.assertEqual(meta["activity_position"], "between_activities")
        self.assertEqual(meta["working_pages_window"], "[]")
        self.assertIn(
            "- **Lesson 上下文**：无；当前处于活动之间，尚未创建或激活下一 Lesson。",
            updated,
        )
        self.assertNotIn("当前前台为 `lesson01`", updated)

    def test_blockers_suggest_closed_incomplete(self) -> None:
        body = close.build_close_body(
            activity_type="lesson",
            activity_id="lesson01",
            prefs={key: "on" for key in close.PREF_KEYS},
            blockers=["open checkpoint"],
        )
        self.assertEqual(body["recommendation"], "closed_incomplete")

    def test_system_feedback_cannot_satisfy_course_feedback(self) -> None:
        content = fully_assessed_content()
        content["teaching_retrospective"]["system_feedback"] = {
            "items": {"startup_speed": "启动太慢"}
        }
        with self.assertRaisesRegex(
            close.CloseError,
            "system_feedback must be routed outside course_content_feedback",
        ):
            close.build_close_body(
                activity_type="lesson",
                activity_id="lesson01",
                prefs={key: "on" for key in close.PREF_KEYS},
                knowledge=[{"topic": "sets", "state": "partial"}],
                evidence_refs=["lesson evidence"],
                content_sections=content,
            )

    def test_production_authority_is_direct_user_only(self) -> None:
        self.assertEqual(
            close.PRODUCTION_DECISION_AUTHORITIES,
            frozenset({("user", "direct_user")}),
        )
        self.assertEqual(
            close.PRODUCTION_APPLY_AUTHORIZATION_MODES,
            frozenset({"direct_user"}),
        )

    def test_only_exact_published_delegated_close_is_legacy_compatible(self) -> None:
        historical = {
            **ledger.KNOWN_INVALID_LEGACY_DELEGATED_CLOSE,
            "decision_actor": "delegated_operator",
            "authorization_mode": "user_continuous_delegation",
        }
        course_id = historical.pop("course_id")
        self.assertTrue(
            ledger.is_known_invalid_legacy_delegated_close(course_id, historical)
        )
        historical["transaction_id"] = "CLOSE022-new"
        self.assertFalse(
            ledger.is_known_invalid_legacy_delegated_close(course_id, historical)
        )

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

    def test_five_knowledge_states_scope_confirmation_and_v2_body(self) -> None:
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
            content_sections=fully_assessed_content(),
            scope_change={"from": "chapter", "to": "section"},
        )
        self.assertEqual(unconfirmed["recommendation"], "closed_incomplete")
        self.assertIn("unconfirmed_scope_change", unconfirmed["completion_blockers"])
        self.assertEqual(
            set(unconfirmed["teaching_retrospective"]),
            set(close.RETROSPECTIVE_TREE),
        )
        confirmed = close.build_close_body(
            activity_type="exercise",
            activity_id="exercise01",
            prefs=all_off,
            knowledge=knowledge,
            evidence_refs=["exercise evidence"],
            student_feedback_ref="feedback",
            content_sections=fully_assessed_content(),
            scope_change={"from": "chapter", "to": "section"},
            scope_change_confirmed=True,
        )
        self.assertEqual(confirmed["recommendation"], "completed")
        self.assertEqual(confirmed["schema"], close.CLOSE_BODY_SCHEMA)
        self.assertEqual(
            confirmed["completion_assessment"]["reason"],
            "无 blocker，范围、证据与结课树均已逐项检查；not_applicable 节点不阻断完成。",
        )
        content = fully_assessed_content()
        content["teaching_retrospective"]["teacher_reflection"] = {
            "status": "not_applicable",
            "reason": "本次没有教学干预",
        }
        not_applicable = close.build_close_body(
            activity_type="exercise",
            activity_id="exercise01",
            prefs=all_off,
            knowledge=knowledge,
            evidence_refs=["exercise evidence"],
            content_sections=content,
        )
        self.assertEqual(not_applicable["recommendation"], "completed")
        self.assertEqual(
            not_applicable["teaching_retrospective"]["teacher_reflection"]["status"],
            "not_applicable",
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
