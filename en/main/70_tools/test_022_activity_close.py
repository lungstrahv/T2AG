#!/usr/bin/env python3
"""Unit tests for 0.2.2 activity ledger schema and routing."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_ledger as ledger


class LedgerSchemaTests(unittest.TestCase):
    def test_empty_ledger_validates(self) -> None:
        text = ledger.empty_ledger("DS1001r")
        doc = ledger.parse_ledger_text(text)
        self.assertEqual(doc.validate(), [])
        self.assertEqual(doc.rebuild_index(), {})

    def test_migration_snapshot_null_from_state_allowed_once(self) -> None:
        event = ledger.render_migration_snapshot_event(
            event_id="ALE-000001",
            course_id="CS1953",
            activity_type="lesson",
            activity_id="lesson01",
            observed_state="ongoing",
            recorded_at="2026-08-05T00:00:00Z",
            transaction_id="TXN-1",
            observed_from_refs=["main/40_course/CS1953/progress.md"],
            evidence_refs=["migrate_022"],
        )
        text = ledger.build_ledger_with_events("CS1953", event)
        doc = ledger.parse_ledger_text(text)
        self.assertEqual(doc.validate(), [])
        index = doc.rebuild_index()
        self.assertEqual(index["lesson:lesson01"].state, "ongoing")

    def test_second_migration_snapshot_rejected(self) -> None:
        e1 = ledger.render_migration_snapshot_event(
            event_id="ALE-000001",
            course_id="CS1953",
            activity_type="lesson",
            activity_id="lesson01",
            observed_state="ongoing",
            recorded_at="2026-08-05T00:00:00Z",
            transaction_id="TXN-1",
            observed_from_refs=["p"],
            evidence_refs=["e"],
        )
        e2 = ledger.render_migration_snapshot_event(
            event_id="ALE-000002",
            course_id="CS1953",
            activity_type="lesson",
            activity_id="lesson01",
            observed_state="ongoing",
            recorded_at="2026-08-05T00:00:01Z",
            transaction_id="TXN-1",
            observed_from_refs=["p"],
            evidence_refs=["e"],
        )
        with self.assertRaises(ledger.LedgerError):
            ledger.build_ledger_with_events("CS1953", e1 + "\n" + e2)

    def test_schema_index_stats_and_preference_tampering_rejected(self) -> None:
        text = ledger.empty_ledger("X")
        mutations = {
            "schema": text.replace("schema_version: activity_ledger.v1", "schema_version: bad"),
            "truth": text.replace("truth_scope: activity_lifecycle", "truth_scope: everything"),
            "index": text.replace(
                "_empty — no LearningActivities registered_",
                "| activity_type | activity_id | state | binding_status | last_event_id |\n"
                "|---|---|---|---|---|\n| exercise | exercise99 | completed | bound | ALE-999999 |",
            ),
            "stats": text.replace("completed_exercises: 0", "completed_exercises: 9"),
            "preference": text.replace(
                "exercise_problem_review: inherit",
                "exercise_problem_review: sometimes",
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label):
                self.assertNotEqual(ledger.parse_ledger_text(mutated).validate(), [])

    def test_illegal_transition_bad_time_and_orphan_span_rejected(self) -> None:
        genesis = ledger.render_migration_snapshot_event(
            event_id="ALE-000001",
            course_id="X",
            activity_type="lesson",
            activity_id="lesson01",
            observed_state="ongoing",
            recorded_at="2026-08-05T00:00:00Z",
            transaction_id="TXN",
            observed_from_refs=["p"],
            evidence_refs=["e"],
        )
        illegal = (
            "### ALE-000002\nevent_id: ALE-000002\nevent_kind: transition\n"
            "course_id: X\nactivity_type: lesson\nactivity_id: lesson01\n"
            "from_state: ongoing\nto_state: completed\noccurred_at: not-a-time\n"
            "recorded_at: 2026-08-05T00:01:00Z\ntriggered_by: user\n"
            "trigger: invalid\ntransaction_id: TXN2\nevidence_refs: [e]\n"
        )
        with self.assertRaises(ledger.LedgerError):
            ledger.build_ledger_with_events("X", genesis + "\n" + illegal)
        orphan = (
            "### ALE-000002\nevent_id: ALE-000002\nevent_kind: learning_exit\n"
            "course_id: X\nactivity_type: lesson\nactivity_id: lesson01\n"
            "from_state: ongoing\nto_state: ongoing\nrecorded_at: 2026-08-05T00:01:00Z\n"
            "triggered_by: user\ntrigger: stop\ntransaction_id: TXN2\n"
            "evidence_refs: [e]\nlearning_span_id: SPAN-1\n"
        )
        with self.assertRaises(ledger.LedgerError):
            ledger.build_ledger_with_events("X", genesis + "\n" + orphan)

    def test_illegal_udddd_new_id(self) -> None:
        with self.assertRaises(ledger.LedgerError):
            ledger.reject_new_udddd("U1102")
        with self.assertRaises(ledger.LedgerError):
            ledger.validate_activity_id("exercise", "U1101")

    def test_exercise_canonical_id(self) -> None:
        ledger.validate_activity_id("exercise", "exercise01")
        ledger.validate_activity_id("lesson", "lesson01")

    def test_capacity_lesson_limit(self) -> None:
        blocks = []
        for i in range(1, 5):
            blocks.append(
                ledger.render_migration_snapshot_event(
                    event_id=f"ALE-{i:06d}",
                    course_id="X",
                    activity_type="lesson",
                    activity_id=f"lesson{i:02d}",
                    observed_state="ongoing",
                    recorded_at="2026-08-05T00:00:00Z",
                    transaction_id="TXN",
                    observed_from_refs=["p"],
                    evidence_refs=["e"],
                )
            )
        with self.assertRaises(ledger.LedgerError):
            ledger.build_ledger_with_events("X", "\n".join(blocks))

    def test_capacity_exercise_limit_and_mixed_maximum(self) -> None:
        def snapshot(event_no: int, kind: str, activity_id: str, state: str) -> str:
            return ledger.render_migration_snapshot_event(
                event_id=f"ALE-{event_no:06d}",
                course_id="X",
                activity_type=kind,
                activity_id=activity_id,
                observed_state=state,
                recorded_at="2026-08-05T00:00:00Z",
                transaction_id="TXN",
                observed_from_refs=["p"],
                evidence_refs=["e"],
            )

        allowed = [
            snapshot(1, "lesson", "lesson01", "ongoing"),
            snapshot(2, "lesson", "lesson02", "pending_close"),
            snapshot(3, "lesson", "lesson03", "ongoing"),
            snapshot(4, "exercise", "exercise01", "ongoing"),
            snapshot(5, "exercise", "exercise02", "pending_close"),
            snapshot(6, "exercise", "exercise03", "paused"),
            snapshot(7, "lesson", "lesson04", "completed"),
        ]
        text = ledger.build_ledger_with_events("X", "\n".join(allowed))
        self.assertEqual(
            ledger.parse_ledger_text(text).capacity_usage(),
            {"lesson": 3, "exercise": 2},
        )
        with self.assertRaises(ledger.LedgerError):
            ledger.build_ledger_with_events(
                "X",
                "\n".join(
                    allowed
                    + [snapshot(8, "exercise", "exercise04", "ongoing")]
                ),
            )

    def test_duplicate_alias_rejected(self) -> None:
        event = ledger.render_migration_snapshot_event(
            event_id="ALE-000001",
            course_id="X",
            activity_type="exercise",
            activity_id="exercise01",
            observed_state="ongoing",
            recorded_at="2026-08-05T00:00:00Z",
            transaction_id="TXN",
            observed_from_refs=["p"],
            evidence_refs=["e"],
        )
        aliases = (
            "### alias U1101\nscope: activity\ncourse_id: X\n"
            "legacy_id: U1101\ncanonical_id: exercise01\n"
        )
        with self.assertRaises(ledger.LedgerError):
            ledger.build_ledger_with_events(
                "X",
                event,
                aliases_markdown=aliases
                + "\n### alias U1101\nscope: activity\ncourse_id: X\n"
                "legacy_id: U1101\ncanonical_id: exercise01\n",
            )
        text = ledger.build_ledger_with_events("X", event, aliases_markdown=aliases)
        doc = ledger.parse_ledger_text(text)
        doc.aliases.append(dict(doc.aliases[0]))
        errors = doc.validate()
        self.assertTrue(any("duplicate alias" in e for e in errors))

    def test_course_scoped_alias_resolver(self) -> None:
        aliases = [
            {
                "scope": "activity",
                "course_id": "MATH1607H",
                "legacy_id": "U1101",
                "canonical_id": "exercise01",
            }
        ]
        self.assertEqual(
            ledger.resolve_legacy_id("MATH1607H", "U1101", aliases),
            "exercise01",
        )
        with self.assertRaises(ledger.LedgerError):
            ledger.resolve_legacy_id("OTHER", "U1101", aliases)
        with self.assertRaises(ledger.LedgerError):
            ledger.resolve_legacy_id("MATH1607H", "../U1101", aliases)
        with self.assertRaises(ledger.LedgerError):
            ledger.resolve_legacy_id(
                "MATH1607H",
                "U1101",
                [
                    {
                        "course_id": "MATH1607H",
                        "legacy_id": "U1101",
                        "canonical_id": "U1102",
                    }
                ],
            )

    def test_next_action_matrix(self) -> None:
        idx = {
            "lesson:lesson01": ledger.ActivityIndexEntry(
                "lesson", "lesson01", "ongoing"
            )
        }
        self.assertEqual(
            ledger.resolve_next_action(
                current_activity_type="lesson",
                current_activity_id="lesson01",
                current_state="pending_close",
                index=idx,
            )["next_action_kind"],
            "confirm_close",
        )
        self.assertEqual(
            ledger.resolve_next_action(
                current_activity_type="none",
                current_activity_id="none",
                current_state=None,
                index=idx,
            )["next_action_kind"],
            "resume",
        )
        idx2 = {
            "lesson:lesson01": ledger.ActivityIndexEntry(
                "lesson", "lesson01", "ongoing"
            ),
            "exercise:exercise01": ledger.ActivityIndexEntry(
                "exercise", "exercise01", "pending_close"
            ),
        }
        self.assertEqual(
            ledger.resolve_next_action(
                current_activity_type="none",
                current_activity_id="none",
                current_state=None,
                index=idx2,
            )["next_action_kind"],
            "choose_activity",
        )
        self.assertEqual(
            ledger.resolve_next_action(
                current_activity_type="none",
                current_activity_id="none",
                current_state=None,
                index={},
                planned=[("exercise", "exercise01")],
            )["next_action_kind"],
            "start_activity",
        )
        self.assertEqual(
            ledger.resolve_next_action(
                current_activity_type="none",
                current_activity_id="none",
                current_state=None,
                index={},
                planned=[("lesson", "lesson01"), ("exercise", "exercise01")],
            )["next_action_kind"],
            "choose_activity",
        )
        background_pending = {
            "lesson:lesson01": ledger.ActivityIndexEntry(
                "lesson", "lesson01", "pending_close"
            ),
            "exercise:exercise01": ledger.ActivityIndexEntry(
                "exercise", "exercise01", "ongoing"
            ),
        }
        route = ledger.resolve_next_action(
            current_activity_type="exercise",
            current_activity_id="exercise01",
            current_state="ongoing",
            index=background_pending,
        )
        self.assertEqual(route["next_action_kind"], "resume")
        self.assertEqual(route["next_activity_id"], "exercise01")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
