#!/usr/bin/env python3
"""Plan/apply non-close LearningActivity lifecycle and learning-span events."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_close as close
import activity_ledger as ledger


ALLOWED_NON_CLOSE_TRANSITIONS = {
    ("planned", "ongoing"),
    ("ongoing", "paused"),
    ("paused", "ongoing"),
}


def materialize_lifecycle_plan(
    root: Path,
    plan_path: Path,
    *,
    course_id: str,
    activity_type: str,
    activity_id: str,
    event_kind: str,
    to_state: str | None = None,
    target_activity_type: str | None = None,
    target_activity_id: str | None = None,
    learning_span_id: str | None = None,
    duration_mode: str | None = None,
    duration_minutes: int | None = None,
    evidence_refs: list[str] | None = None,
    corrects_event_id: str | None = None,
    corrects_close_id: str | None = None,
    correction_summary: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    evidence_refs = evidence_refs or []
    ledger_rel = f"main/40_course/{course_id}/activity_ledger.md"
    progress_rel = f"main/40_course/{course_id}/progress.md"
    ledger_text = (root / ledger_rel).read_text(encoding="utf-8")
    progress_text = (root / progress_rel).read_text(encoding="utf-8")
    doc = ledger.parse_ledger_text(ledger_text)
    errors = doc.validate()
    if errors:
        raise close.CloseError("source ledger invalid: " + "; ".join(errors))
    key = f"{activity_type}:{activity_id}"
    index = doc.rebuild_index()
    if key not in index:
        raise close.CloseError(f"unknown activity: {key}")
    current_state = index[key].state
    event_id = close.next_numeric_id(
        [str(item.get("event_id") or "") for item in doc.events], "ALE", 6
    )
    recorded_at = close.now_tz()
    transaction_id = f"LIFECYCLE022-{uuid.uuid4().hex}"
    fields: dict[str, Any] = {
        "event_id": event_id,
        "event_kind": event_kind,
        "course_id": course_id,
        "activity_type": activity_type,
        "activity_id": activity_id,
        "from_state": current_state,
        "to_state": current_state,
        "occurred_at": recorded_at,
        "recorded_at": recorded_at,
        "triggered_by": "user",
        "trigger": f"activity_{event_kind}",
        "transaction_id": transaction_id,
        "evidence_refs": evidence_refs,
    }
    progress_mode = "unchanged"
    if event_kind == "transition":
        pair = (current_state, str(to_state or ""))
        if pair not in ALLOWED_NON_CLOSE_TRANSITIONS:
            raise close.CloseError(
                f"non-close lifecycle refuses transition {pair[0]}->{pair[1]}"
            )
        fields["to_state"] = pair[1]
        progress_mode = "target" if pair[1] == "ongoing" else "none"
    elif event_kind == "foreground_switch":
        target_type = str(target_activity_type or "")
        target_id = str(target_activity_id or "")
        target = index.get(f"{target_type}:{target_id}")
        if target is None or target.state not in {"ongoing", "pending_close"}:
            raise close.CloseError("foreground target must be ongoing or pending_close")
        fields.update(
            {
                "activity_type": target_type,
                "activity_id": target_id,
                "from_activity_type": activity_type,
                "from_activity_id": activity_id,
                "to_activity_type": target_type,
                "to_activity_id": target_id,
            }
        )
        activity_type, activity_id, current_state = target_type, target_id, target.state
        progress_mode = "target"
    elif event_kind in {"learning_enter", "learning_exit"}:
        if not learning_span_id:
            raise close.CloseError("learning event requires learning_span_id")
        fields["learning_span_id"] = learning_span_id
        if event_kind == "learning_exit":
            if duration_mode not in {"exact", "estimated", "unknown"}:
                raise close.CloseError("learning exit requires exact/estimated/unknown duration")
            if duration_mode == "unknown" and duration_minutes is not None:
                raise close.CloseError("unknown duration cannot carry minutes")
            if duration_mode != "unknown" and (
                not isinstance(duration_minutes, int) or duration_minutes < 0
            ):
                raise close.CloseError("known duration requires nonnegative integer minutes")
            profile = root / "main/10_student/profile/profile.md"
            profile_meta = (
                close.frontmatter_split(profile.read_text(encoding="utf-8-sig"))[0]
                if profile.is_file()
                else {}
            )
            fields.update(
                {
                    "duration_mode": duration_mode,
                    "duration_minutes": "none" if duration_mode == "unknown" else duration_minutes,
                    "learning_timezone": profile_meta.get("learning_timezone", "Asia/Singapore"),
                    "learning_day_cutoff": profile_meta.get("learning_day_cutoff", "04:00"),
                    "learning_day": close.learning_day(
                        recorded_at,
                        profile_meta.get("learning_timezone", "Asia/Singapore"),
                        profile_meta.get("learning_day_cutoff", "04:00"),
                    ),
                }
            )
    elif event_kind == "correction":
        # Non-state, append-only. from_state/to_state stay null; correction_effect mandatory.
        if not corrects_event_id:
            raise close.CloseError("correction requires --corrects-event-id")
        if not correction_summary or not correction_summary.strip():
            raise close.CloseError("correction requires non-empty --correction-summary")
        if not fields.get("evidence_refs"):
            raise close.CloseError("correction requires evidence_refs")
        fields["from_state"] = None
        fields["to_state"] = None
        fields["corrects_event_id"] = corrects_event_id
        fields["correction_summary"] = correction_summary
        fields["correction_effect"] = "record_only_no_state_change"
        if corrects_close_id:
            fields["corrects_close_id"] = corrects_close_id
        progress_mode = "none"
    else:
        raise close.CloseError(f"unsupported lifecycle event_kind: {event_kind}")

    event = close.render_event(fields)
    candidate_ledger = close.append_section_record(
        ledger_text, "Activity lifecycle events", event
    )
    candidate_ledger = close.refresh_ledger_views(candidate_ledger, recorded_at)
    candidate_doc = ledger.parse_ledger_text(candidate_ledger)
    files = {ledger_rel: candidate_ledger}
    if progress_mode != "unchanged":
        current_type = activity_type if progress_mode == "target" else "none"
        current_id = activity_id if progress_mode == "target" else "none"
        state = current_state if progress_mode == "target" else None
        next_action = ledger.resolve_next_action(
            current_activity_type=current_type,
            current_activity_id=current_id,
            current_state=state,
            index=candidate_doc.rebuild_index(),
        )
        files[progress_rel] = close.update_progress(
            progress_text,
            activity_type=activity_type,
            activity_id=activity_id,
            state=current_state if progress_mode == "target" else "completed",
            next_action=next_action,
        )
    core = close.build_plan_core(
        root=root,
        mode="lifecycle",
        course_id=course_id,
        activity_type=activity_type,
        activity_id=activity_id,
        transaction_id=transaction_id,
        files=close.include_generated_state(root, files),
        details={
            "event_id": event_id,
            "event_kind": event_kind,
            "from_state": fields.get("from_state"),
            "to_state": fields.get("to_state"),
            "learning_span_id": learning_span_id,
        },
    )
    return close.write_plan(plan_path, core)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=close.PRODUCTION_ROOT)
    parser.add_argument("--course-id", required=True)
    parser.add_argument("--activity-type", choices=["lesson", "exercise"], required=True)
    parser.add_argument("--activity-id", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan", action="store_true")
    action.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--event-kind",
        choices=["transition", "foreground_switch", "learning_enter", "learning_exit", "correction"],
    )
    parser.add_argument("--to-state")
    parser.add_argument("--target-activity-type")
    parser.add_argument("--target-activity-id")
    parser.add_argument("--learning-span-id")
    parser.add_argument("--duration-mode", choices=["exact", "estimated", "unknown"])
    parser.add_argument("--duration-minutes", type=int)
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--corrects-event-id")
    parser.add_argument("--corrects-close-id")
    parser.add_argument("--correction-summary")
    parser.add_argument("--plan-out", type=Path)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--expect-payload-sha")
    parser.add_argument("--expect-file-sha")
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--expect-authorization-sha")
    args = parser.parse_args(argv)
    try:
        if args.plan:
            if not args.plan_out or not args.event_kind:
                raise close.CloseError("--plan-out and --event-kind required")
            result = materialize_lifecycle_plan(
                args.root,
                args.plan_out,
                course_id=args.course_id,
                activity_type=args.activity_type,
                activity_id=args.activity_id,
                event_kind=args.event_kind,
                to_state=args.to_state,
                target_activity_type=args.target_activity_type,
                target_activity_id=args.target_activity_id,
                learning_span_id=args.learning_span_id,
                duration_mode=args.duration_mode,
                duration_minutes=args.duration_minutes,
                evidence_refs=args.evidence_ref,
                corrects_event_id=args.corrects_event_id,
                corrects_close_id=args.corrects_close_id,
                correction_summary=args.correction_summary,
            )
        else:
            required = (
                args.plan_file,
                args.expect_payload_sha,
                args.expect_file_sha,
                args.authorization_receipt,
                args.expect_authorization_sha,
            )
            if not all(required):
                raise close.CloseError("apply requires exact plan/authorization bindings")
            result = close.apply_close_plan(
                args.root,
                args.plan_file,
                expect_payload_sha=args.expect_payload_sha,
                expect_file_sha=args.expect_file_sha,
                authorization_receipt=args.authorization_receipt,
                expect_authorization_sha=args.expect_authorization_sha,
            )
    except Exception as exc:  # noqa: BLE001
        print(close.canonical_json({"ok": False, "error": str(exc)}))
        return 1
    print(close.canonical_json({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
