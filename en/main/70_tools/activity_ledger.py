#!/usr/bin/env python3
"""T2AG 0.2.2 activity ledger schema, validation, and current-index rebuild.

Ledger is the sole authority for LearningActivity lifecycle within a Course.
progress.md owns course lifecycle + frontend pointer only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]

ACTIVITY_STATES = frozenset(
    {
        "planned",
        "ongoing",
        "paused",
        "pending_close",
        "completed",
        "closed_incomplete",
    }
)
ACTIVE_CAPACITY_STATES = frozenset({"ongoing", "pending_close"})
ACTIVITY_TYPES = frozenset({"lesson", "exercise"})
EVENT_KINDS = frozenset(
    {
        "transition",
        "migration_snapshot",
        "pending_revision",
        "foreground_switch",
        "learning_enter",
        "learning_exit",
        "correction",
    }
)
LEGAL_TRANSITIONS = frozenset(
    {
        ("planned", "ongoing"),
        ("ongoing", "paused"),
        ("paused", "ongoing"),
        ("ongoing", "pending_close"),
        ("pending_close", "ongoing"),
        ("pending_close", "completed"),
        ("pending_close", "closed_incomplete"),
        ("completed", "ongoing"),
        ("closed_incomplete", "ongoing"),
    }
)
CAPACITY = {"lesson": 3, "exercise": 2}
LESSON_ID_RE = re.compile(r"^lesson\d{2,}$")
EXERCISE_ID_RE = re.compile(r"^exercise\d{2,}$")
LEGACY_EXERCISE_RE = re.compile(r"^U\d{4}$")
PROBLEM_ID_RE = re.compile(r"^exercise\d{2,}-Q\d{3}$")
LEGACY_PROBLEM_RE = re.compile(r"^U\d{4}-Q\d{3}$")
ALE_ID_RE = re.compile(r"^ALE-\d{6}$")
CLR_ID_RE = re.compile(r"^CLR-\d{4}$")
TZ_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

# Read-only compatibility for the single CLR already published by 0.2.2 before
# the authorization-boundary defect was found.  Matching this fingerprint does
# not make the delegation valid and must never be used to authorize a new write.
KNOWN_INVALID_LEGACY_DELEGATED_CLOSE = {
    "course_id": "MATH1607H",
    "close_id": "CLR-0001",
    "pending_event_id": "ALE-000003",
    "terminal_event_id": "ALE-000004",
    "body_sha256": "0aec0b19b8b89b984f5d05c30d783a222c2cb7b4f3843b035118462324abb840",
    "result": "completed",
    "transaction_id": "CLOSE022-3869134a25a54209a66f60545675f0d1",
    "authorization_source_sha256": "0bd59bd88f29b83ff9153e8b5360991f854398b77235f0b90c50690eb21624ae",
    "authorization_quote_sha256": "3ee10c4af2c0847f24ea080e74e1b4a570c5bff020ce35d7d6102c2e2e172a80",
    "strict_confirmation_sha256": "324f776c31cb4384a0bb9274280869b5f9e6009e0898f93d02fe2a3aa4073fbf",
}

KNOWLEDGE_STATES = frozenset(
    {
        "independent_confirmed",
        "assisted_confirmed",
        "partial",
        "unverified",
        "unresolved",
    }
)
PREF_VALUES = frozenset({"on", "off", "inherit"})
PREF_KEYS = (
    "lesson_actual_review",
    "lesson_student_feedback",
    "lesson_knowledge_absorption",
    "exercise_problem_review",
    "exercise_knowledge_mastery",
)
NEXT_ACTION_KINDS = frozenset(
    {"confirm_close", "resume", "choose_activity", "start_activity", "none"}
)


class LedgerError(ValueError):
    def __init__(self, errors: list[str] | str):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_known_invalid_legacy_delegated_close(
    course_id: str, close: dict[str, Any]
) -> bool:
    if (
        close.get("decision_actor"),
        close.get("authorization_mode"),
    ) != ("delegated_operator", "user_continuous_delegation"):
        return False
    actual = {"course_id": course_id}
    for key in KNOWN_INVALID_LEGACY_DELEGATED_CLOSE:
        if key == "course_id":
            continue
        value = close.get(key)
        if key == "close_id" and not value:
            value = close.get("_header_id")
        actual[key] = str(value or "")
    return actual == KNOWN_INVALID_LEGACY_DELEGATED_CLOSE


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_pending_body(event: dict[str, Any]) -> str | None:
    event_id = str(event.get("event_id") or "")
    want = str(event.get("pending_body_sha256") or "")
    encoded = str(event.get("pending_body_b64") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", want) or not encoded:
        return f"{event_id}: pending body binding missing"
    try:
        body = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return f"{event_id}: pending body is not valid base64 JSON"
    embedded = body.pop("body_sha256", None)
    got = sha256_text(canonical_json(body))
    if embedded != want or got != want:
        return f"{event_id}: pending body SHA mismatch"
    return None


def parse_simple_yaml_block(text: str) -> dict[str, Any]:
    """Parse a shallow YAML-like mapping used in ledger sections (no nested maps)."""
    result: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value in {"null", "Null", "NULL", "~"}:
            result[key] = None
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                result[key] = []
            else:
                result[key] = [part.strip().strip("'\"") for part in inner.split(",")]
        else:
            result[key] = value.strip("'\"")
    return result


def split_records(section_body: str, marker: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    chunks = re.split(rf"(?m)^###\s+{re.escape(marker)}\s+", section_body)
    for chunk in chunks[1:]:
        lines = chunk.splitlines()
        if not lines:
            continue
        header = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        # body may contain free text after a --- fence; only parse YAML-ish head
        yaml_part = body
        if "\n```" in body:
            yaml_part = body.split("\n```", 1)[0]
        if "\n## " in yaml_part:
            yaml_part = yaml_part.split("\n## ", 1)[0]
        data = parse_simple_yaml_block(yaml_part)
        data["_header_id"] = header
        data["_raw"] = chunk
        records.append(data)
    return records


def section(text: str, title: str) -> str:
    pattern = rf"(?ms)^##\s+{re.escape(title)}\s*\n(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""



# ---------------------------------------------------------------------------
# LV-5 (2026-08-20): the close-intent vocabulary is an RT3 authorization boundary.
# It used to be written out twice -- here and in activity_close.py -- with no shared
# source, so widening one side silently desynced the other and every direct-user
# confirmation started failing its binding check. Same fact, two definitions, is the
# defect this system's own rules name; the sets now live here and activity_close
# imports them.
#
# Adjudicated: accept BOTH language editions rather than replacing one with the other.
# The set stays closed and every member expresses one single intent, so widening does
# not widen what is being authorized -- only how the student may say it.
#
# Incomplete markers are always tested FIRST: "close" is a substring of
# "close as incomplete" (and 结课 of 以未完成状态结课). Getting that order wrong would
# silently upgrade an incomplete close into a completed one.
BOUND_COMPLETED_INTENTS = frozenset({
    "结课", "确认结课", "愿意结课",
    "close", "confirm close", "close this activity",
})
BOUND_INCOMPLETE_INTENTS = frozenset({
    "以未完成状态结课", "确认以未完成状态结课",
    "close as incomplete", "confirm close as incomplete",
})
BOUND_INCOMPLETE_MARKERS = ("以未完成状态结课", "close as incomplete")
BOUND_COMPLETED_MARKERS = ("结课", "close")


def close_intent_in(text: str, *, completed: bool) -> bool:
    """Does `text` carry the close intent, in any shipped language edition?

    `completed=True` additionally requires that the text does NOT carry an
    incomplete-close phrase, because the completed marker is a substring of it.
    """
    says_incomplete = any(m in text for m in BOUND_INCOMPLETE_MARKERS)
    if not completed:
        return says_incomplete
    return not says_incomplete and any(m in text for m in BOUND_COMPLETED_MARKERS)


@dataclass
class ActivityIndexEntry:
    activity_type: str
    activity_id: str
    state: str
    binding_status: str = "bound"
    binding_reason: str = ""
    content_group_ids: list[str] = field(default_factory=list)
    last_event_id: str = ""


@dataclass
class LedgerDocument:
    path: Path | None
    course_id: str
    schema_version: str
    truth_scope: str
    events: list[dict[str, Any]]
    closes: list[dict[str, Any]]
    preferences: dict[str, str]
    aliases: list[dict[str, Any]]
    stats: dict[str, Any]
    current_index_text: str = ""
    raw: str = ""

    def rebuild_index(self) -> dict[str, ActivityIndexEntry]:
        index: dict[str, ActivityIndexEntry] = {}
        snapshot_seen: set[str] = set()
        for event in self.events:
            kind = event.get("event_kind")
            if kind == "foreground_switch":
                continue
            if kind in {"learning_enter", "learning_exit", "pending_revision", "correction"}:
                key = f"{event.get('activity_type')}:{event.get('activity_id')}"
                if key in index:
                    index[key].last_event_id = str(event.get("event_id") or "")
                continue
            a_type = str(event.get("activity_type") or "")
            a_id = str(event.get("activity_id") or "")
            key = f"{a_type}:{a_id}"
            if kind == "migration_snapshot":
                if key in snapshot_seen:
                    raise LedgerError(f"second migration_snapshot forbidden for {key}")
                snapshot_seen.add(key)
                if event.get("from_state") is not None:
                    raise LedgerError(
                        f"migration_snapshot from_state must be null for {key}"
                    )
                to_state = event.get("to_state") or event.get("observed_state")
                if to_state not in ACTIVITY_STATES:
                    raise LedgerError(f"invalid migration to_state for {key}: {to_state}")
                index[key] = ActivityIndexEntry(
                    activity_type=a_type,
                    activity_id=a_id,
                    state=str(to_state),
                    binding_status=str(event.get("binding_status") or "bound"),
                    binding_reason=str(event.get("binding_reason") or ""),
                    content_group_ids=list(event.get("content_group_ids") or []),
                    last_event_id=str(event.get("event_id") or ""),
                )
                continue
            if kind == "transition":
                frm = event.get("from_state")
                to = event.get("to_state")
                if key not in index:
                    # Genesis (2026-08-08, P-0062): planned is the implicit
                    # pre-existence state ("不预造 planned 活动"), so an activity's
                    # first transition may depart from it — this is the only legal
                    # post-migration birth. Any other origin still fails closed.
                    if frm != "planned":
                        raise LedgerError(f"transition without prior state for {key}")
                    if (frm, to) not in LEGAL_TRANSITIONS:
                        raise LedgerError(f"illegal transition {frm}->{to} for {key}")
                    index[key] = ActivityIndexEntry(
                        activity_type=a_type,
                        activity_id=a_id,
                        state=str(to),
                        binding_status=str(event.get("binding_status") or "unbound"),
                        binding_reason=str(event.get("binding_reason") or ""),
                        content_group_ids=list(event.get("content_group_ids") or []),
                        last_event_id=str(event.get("event_id") or ""),
                    )
                    continue
                if index[key].state != frm:
                    raise LedgerError(
                        f"transition discontinuity for {key}: "
                        f"index={index[key].state} from={frm}"
                    )
                if (frm, to) not in LEGAL_TRANSITIONS:
                    raise LedgerError(f"illegal transition {frm}->{to} for {key}")
                index[key].state = str(to)
                index[key].last_event_id = str(event.get("event_id") or "")
        return index

    def capacity_usage(self) -> dict[str, int]:
        index = self.rebuild_index()
        usage = {"lesson": 0, "exercise": 0}
        for entry in index.values():
            if entry.state in ACTIVE_CAPACITY_STATES and entry.activity_type in usage:
                usage[entry.activity_type] += 1
        return usage

    def assert_capacity(self) -> None:
        usage = self.capacity_usage()
        for kind, limit in CAPACITY.items():
            if usage[kind] > limit:
                raise LedgerError(
                    f"{kind} active capacity exceeded: {usage[kind]} > {limit}"
                )

    def validate(self, *, validate_views: bool = True) -> list[str]:
        errors: list[str] = []
        try:
            if not self.course_id:
                errors.append("course_id missing")
            if self.schema_version != "activity_ledger.v1":
                errors.append(f"unsupported schema_version: {self.schema_version}")
            if self.truth_scope != "activity_lifecycle":
                errors.append(f"unsupported truth_scope: {self.truth_scope}")
            missing_prefs = sorted(set(PREF_KEYS) - set(self.preferences))
            extra_prefs = sorted(set(self.preferences) - set(PREF_KEYS))
            if missing_prefs:
                errors.append(f"missing preferences: {missing_prefs}")
            if extra_prefs:
                errors.append(f"unknown preferences: {extra_prefs}")
            for key, value in self.preferences.items():
                if value not in {"on", "off", "inherit"}:
                    errors.append(f"illegal preference {key}={value}")
            for key, value in self.stats.items():
                if key.startswith("_"):
                    continue
                try:
                    if int(str(value)) < 0:
                        errors.append(f"negative stats {key}={value}")
                except ValueError:
                    errors.append(f"non-integer stats {key}={value}")
            seen_ale: set[str] = set()
            last_ale_num = 0
            spans: dict[str, str] = {}
            latest_pending: dict[str, str] = {}
            event_by_id = {
                str(event.get("event_id") or ""): event for event in self.events
            }
            for event in self.events:
                eid = str(event.get("event_id") or "")
                if not ALE_ID_RE.match(eid):
                    errors.append(f"bad ALE id: {eid}")
                if eid in seen_ale:
                    errors.append(f"duplicate ALE id: {eid}")
                seen_ale.add(eid)
                try:
                    num = int(eid.split("-", 1)[1])
                    if num < last_ale_num:
                        errors.append(f"ALE id regresses: {eid}")
                    last_ale_num = max(last_ale_num, num)
                except (IndexError, ValueError):
                    pass
                if event.get("course_id") and str(event.get("course_id")) != self.course_id:
                    errors.append(f"{eid}: course_id mismatch")
                kind = event.get("event_kind")
                if kind not in EVENT_KINDS:
                    errors.append(f"bad event_kind: {kind}")
                for field_name in (
                    "course_id",
                    "recorded_at",
                    "triggered_by",
                    "trigger",
                    "transaction_id",
                ):
                    if not event.get(field_name):
                        errors.append(f"{eid}: missing base field {field_name}")
                if not isinstance(event.get("evidence_refs"), list):
                    errors.append(f"{eid}: evidence_refs must be a list")
                a_type = event.get("activity_type")
                a_id = event.get("activity_id")
                if kind != "foreground_switch":
                    if a_type not in ACTIVITY_TYPES:
                        errors.append(f"{eid}: bad activity_type {a_type}")
                    if a_type == "lesson" and not LESSON_ID_RE.match(str(a_id or "")):
                        errors.append(f"{eid}: bad lesson id {a_id}")
                    if a_type == "exercise" and not EXERCISE_ID_RE.match(str(a_id or "")):
                        errors.append(f"{eid}: bad exercise id {a_id}")
                if kind == "transition":
                    if event.get("from_state") not in ACTIVITY_STATES:
                        errors.append(f"{eid}: bad from_state")
                    if event.get("to_state") not in ACTIVITY_STATES:
                        errors.append(f"{eid}: bad to_state")
                    if not TZ_TIME_RE.match(str(event.get("occurred_at") or "")):
                        errors.append(f"{eid}: transition requires timezone occurred_at")
                    if not TZ_TIME_RE.match(str(event.get("recorded_at") or "")):
                        errors.append(f"{eid}: transition requires timezone recorded_at")
                    frm = event.get("from_state")
                    to = event.get("to_state")
                    if frm == "ongoing" and to == "pending_close":
                        body_error = validate_pending_body(event)
                        if body_error:
                            errors.append(body_error)
                        latest_pending[f"{a_type}:{a_id}"] = eid
                    if frm == "pending_close" and to in {
                        "completed",
                        "closed_incomplete",
                    }:
                        pending_id = str(event.get("confirmed_pending_event_id") or "")
                        pending = event_by_id.get(pending_id)
                        if (
                            not pending
                            or pending.get("to_state") != "pending_close"
                            or pending.get("course_id") != self.course_id
                            or pending.get("activity_type") != a_type
                            or pending.get("activity_id") != a_id
                            or latest_pending.get(f"{a_type}:{a_id}") != pending_id
                        ):
                            errors.append(f"{eid}: terminal transition needs valid pending")
                        latest_pending.pop(f"{a_type}:{a_id}", None)
                    if frm == "pending_close" and to == "ongoing" and not event.get(
                        "refused_pending_event_id"
                    ):
                        errors.append(f"{eid}: refusal needs refused_pending_event_id")
                    if frm == "pending_close" and to == "ongoing":
                        refused = str(event.get("refused_pending_event_id") or "")
                        prior = event_by_id.get(refused)
                        if (
                            not prior
                            or prior.get("to_state") != "pending_close"
                            or prior.get("course_id") != self.course_id
                            or prior.get("activity_type") != a_type
                            or prior.get("activity_id") != a_id
                            or latest_pending.get(f"{a_type}:{a_id}") != refused
                        ):
                            errors.append(f"{eid}: refusal linkage invalid")
                        latest_pending.pop(f"{a_type}:{a_id}", None)
                    if frm in {"completed", "closed_incomplete"} and to == "ongoing":
                        if not event.get("reopens_close_id"):
                            errors.append(f"{eid}: reopen needs reopens_close_id")
                if kind == "migration_snapshot":
                    if event.get("from_state") is not None:
                        errors.append(f"{eid}: migration_snapshot from_state must be null")
                    if event.get("occurred_at") is not None:
                        errors.append(f"{eid}: migration_snapshot occurred_at must be null")
                    if not TZ_TIME_RE.match(str(event.get("recorded_at") or "")):
                        errors.append(f"{eid}: migration_snapshot requires recorded_at")
                    to_state = event.get("to_state") or event.get("observed_state")
                    if to_state not in ACTIVITY_STATES:
                        errors.append(f"{eid}: migration_snapshot bad to/observed state")
                if kind == "pending_revision":
                    if event.get("from_state") != "pending_close" or event.get("to_state") != "pending_close":
                        errors.append(f"{eid}: pending_revision must stay pending_close")
                    if not event.get("revises_event_id"):
                        errors.append(f"{eid}: pending_revision needs revises_event_id")
                    rev = str(event.get("revises_event_id") or "")
                    prior = event_by_id.get(rev)
                    key = f"{a_type}:{a_id}"
                    if (
                        not prior
                        or prior.get("to_state") != "pending_close"
                        or prior.get("course_id") != self.course_id
                        or prior.get("activity_type") != a_type
                        or prior.get("activity_id") != a_id
                        or latest_pending.get(key) != rev
                    ):
                        errors.append(f"{eid}: revision linkage is not current same-activity pending")
                    body_error = validate_pending_body(event)
                    if body_error:
                        errors.append(body_error)
                    latest_pending[key] = eid
                if kind in {"learning_enter", "learning_exit"}:
                    span = str(event.get("learning_span_id") or "")
                    if not span:
                        errors.append(f"{eid}: learning span missing id")
                    elif kind == "learning_enter":
                        if span in spans:
                            errors.append(f"{eid}: overlapping/duplicate enter span {span}")
                        spans[span] = "open"
                    else:
                        if spans.get(span) != "open":
                            errors.append(f"{eid}: exit without enter for span {span}")
                        else:
                            spans[span] = "closed"
                    if not TZ_TIME_RE.match(str(event.get("recorded_at") or "")):
                        errors.append(f"{eid}: learning span requires timezone recorded_at")
                    if event.get("from_state") != event.get("to_state"):
                        errors.append(f"{eid}: learning span must be state-holding")
                    if kind == "learning_exit":
                        mode = str(event.get("duration_mode") or "")
                        minutes = event.get("duration_minutes")
                        if mode not in {"exact", "estimated", "unknown"}:
                            errors.append(f"{eid}: illegal duration_mode")
                        elif mode == "unknown":
                            if minutes not in {None, "", "none"}:
                                errors.append(f"{eid}: unknown duration cannot carry minutes")
                        else:
                            try:
                                if int(str(minutes)) < 0:
                                    raise ValueError
                            except ValueError:
                                errors.append(f"{eid}: {mode} duration requires nonnegative integer minutes")
                        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(event.get("learning_day") or "")):
                            errors.append(f"{eid}: learning_day missing or invalid")
                if kind == "correction":
                    # Non-state, append-only event. Must reference earlier event, same activity.
                    if "correction_summary" not in event or not str(event.get("correction_summary", "")).strip():
                        errors.append(f"{eid}: correction requires non-empty correction_summary")
                    if not isinstance(event.get("evidence_refs"), list) or not event.get("evidence_refs"):
                        errors.append(f"{eid}: correction requires evidence_refs")
                    corrects = str(event.get("corrects_event_id") or "")
                    prior = event_by_id.get(corrects)
                    if not prior:
                        errors.append(f"{eid}: corrects_event_id {corrects} not found")
                    elif (
                        prior.get("course_id") != self.course_id
                        or prior.get("activity_type") != a_type
                        or prior.get("activity_id") != a_id
                    ):
                        errors.append(f"{eid}: correction must target same Course/Activity")
                    # Ensure correction doesn't claim state change
                    if event.get("from_state") is not None or event.get("to_state") is not None:
                        errors.append(f"{eid}: correction must have null from_state and to_state")
                    corrects_close = event.get("corrects_close_id")
                    if corrects_close:
                        if str(corrects_close) not in {str(c.get("close_id") or c.get("_header_id") or "")
                                                       for c in self.closes}:
                            errors.append(f"{eid}: corrects_close_id {corrects_close} not found")
                        # Must be same activity
                        matching = [c for c in self.closes
                                    if str(c.get("close_id") or c.get("_header_id") or "") == str(corrects_close)]
                        if matching:
                            close_act = (matching[0].get("activity_type"), matching[0].get("activity_id"))
                            if close_act != (a_type, a_id):
                                errors.append(f"{eid}: corrects_close_id must be same Activity")
                if str(event.get("binding_status") or "bound") == "unbound":
                    if not str(event.get("binding_reason") or "").strip() or str(
                        event.get("binding_reason")
                    ) in {"none", "None"}:
                        # migration renderer may put none; treat empty reason as error only when unbound and no groups
                        if not event.get("content_group_ids"):
                            if not str(event.get("binding_reason") or "").strip():
                                errors.append(f"{eid}: unbound requires reason")
            seen_clr: set[str] = set()
            closed_pending: set[str] = set()
            for close in self.closes:
                cid = str(close.get("close_id") or close.get("_header_id") or "")
                if not CLR_ID_RE.match(cid):
                    errors.append(f"bad CLR id: {cid}")
                if cid in seen_clr:
                    errors.append(f"duplicate CLR: {cid}")
                seen_clr.add(cid)
                pend = str(close.get("pending_event_id") or "")
                if pend and pend not in {e.get("event_id") for e in self.events}:
                    errors.append(f"CLR {cid} dangling pending_event_id {pend}")
                if pend in closed_pending:
                    errors.append(f"duplicate CLR pending_event_id: {pend}")
                closed_pending.add(pend)
                pending = event_by_id.get(pend)
                if not pending or pending.get("to_state") != "pending_close":
                    errors.append(f"CLR {cid} must reference pending_close event")
                elif (
                    pending.get("course_id") != self.course_id
                    or pending.get("activity_type") != close.get("activity_type")
                    or pending.get("activity_id") != close.get("activity_id")
                ):
                    errors.append(f"CLR {cid} pending ownership mismatch")
                result = str(close.get("result") or "")
                if result not in {"completed", "closed_incomplete"}:
                    errors.append(f"CLR {cid} has illegal result {result}")
                terminal_id = str(close.get("terminal_event_id") or "")
                terminal = event_by_id.get(terminal_id)
                if (
                    not terminal
                    or terminal.get("to_state") != result
                    or terminal.get("confirmed_pending_event_id") != pend
                ):
                    errors.append(f"CLR {cid} terminal event linkage invalid")
                elif (
                    terminal.get("course_id") != self.course_id
                    or terminal.get("activity_type") != close.get("activity_type")
                    or terminal.get("activity_id") != close.get("activity_id")
                ):
                    errors.append(f"CLR {cid} terminal ownership mismatch")
                body_sha = str(close.get("body_sha256") or "")
                if not pending or pending.get("pending_body_sha256") != body_sha:
                    errors.append(f"CLR {cid} body SHA differs from pending")
                if not pending or close.get("body_json_b64") != pending.get("pending_body_b64"):
                    errors.append(f"CLR {cid} body snapshot differs from pending bytes")
                else:
                    try:
                        body = json.loads(
                            base64.b64decode(str(close.get("body_json_b64")), validate=True).decode("utf-8")
                        )
                        embedded = body.pop("body_sha256", None)
                    except Exception:  # noqa: BLE001
                        embedded = None
                        body = {}
                    if embedded != body_sha or sha256_text(canonical_json(body)) != body_sha:
                        errors.append(f"CLR {cid} body snapshot SHA mismatch")
                try:
                    next_snapshot = json.loads(
                        base64.b64decode(
                            str(close.get("next_activity_at_close_b64") or ""), validate=True
                        ).decode("utf-8")
                    )
                except Exception:  # noqa: BLE001
                    next_snapshot = {}
                if sha256_text(canonical_json(next_snapshot)) != str(
                    close.get("next_activity_at_close_sha256") or ""
                ):
                    errors.append(f"CLR {cid} next activity snapshot SHA mismatch")
                terminal_position = next(
                    (i for i, item in enumerate(self.events) if item.get("event_id") == terminal_id),
                    -1,
                )
                if terminal_position >= 0:
                    partial = LedgerDocument(
                        path=self.path,
                        course_id=self.course_id,
                        schema_version=self.schema_version,
                        truth_scope=self.truth_scope,
                        events=self.events[: terminal_position + 1],
                        closes=[],
                        preferences=self.preferences,
                        aliases=self.aliases,
                        stats={},
                    )
                    expected_next = {
                        "current_activity": "none",
                        "current_activity_id": "none",
                        "activity_position": "between_activities",
                        **resolve_next_action(
                            current_activity_type="none",
                            current_activity_id="none",
                            current_state=None,
                            index=partial.rebuild_index(),
                        ),
                    }
                    if next_snapshot != expected_next:
                        errors.append(f"CLR {cid} next activity snapshot is not replay-derived")
                authority = (
                    close.get("decision_actor"),
                    close.get("authorization_mode"),
                )
                procedure_status = close.get("authorization_procedure_status")
                known_invalid_legacy = is_known_invalid_legacy_delegated_close(
                    self.course_id, close
                )
                if authority == ("user", "direct_user"):
                    if procedure_status != "valid_direct_user":
                        errors.append(
                            f"CLR {cid} direct authorization procedure status missing"
                        )
                elif known_invalid_legacy:
                    # Preserve and audit the published bytes without treating
                    # this historical record as a valid authorization example.
                    pass
                else:
                    errors.append(f"CLR {cid} authorization authority invalid")
                if not re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(close.get("authorization_source_sha256") or ""),
                ):
                    errors.append(f"CLR {cid} authorization source missing")
                try:
                    authorization_quote = base64.b64decode(
                        str(close.get("authorization_quote_b64") or ""),
                        validate=True,
                    ).decode("utf-8")
                except Exception:  # noqa: BLE001
                    authorization_quote = ""
                if sha256_text(authorization_quote) != str(
                    close.get("authorization_quote_sha256") or ""
                ):
                    errors.append(f"CLR {cid} authorization quote SHA mismatch")
                if not authorization_quote:
                    errors.append(f"CLR {cid} authorization quote missing")
                try:
                    strict = base64.b64decode(
                        str(close.get("strict_confirmation_b64") or ""),
                        validate=True,
                    ).decode("utf-8")
                except Exception:  # noqa: BLE001
                    strict = ""
                if sha256_text(strict) != str(
                    close.get("strict_confirmation_sha256") or ""
                ):
                    errors.append(f"CLR {cid} strict confirmation SHA mismatch")
                exact_strict = (
                    f"pending_event_id={pend}\n"
                    f"body_sha256={body_sha}\n"
                    f"result={result}"
                )
                confirmation_mode = str(close.get("confirmation_mode") or "exact_tuple")
                normalized_intent = strict.strip().rstrip("。！!").strip()
                mode_valid = confirmation_mode == "exact_tuple" and strict == exact_strict
                if confirmation_mode == "bound_close_intent":
                    mode_valid = (
                        result == "completed"
                        and normalized_intent in BOUND_COMPLETED_INTENTS
                    )
                elif confirmation_mode == "bound_incomplete_close_intent":
                    mode_valid = (
                        result == "closed_incomplete"
                        and normalized_intent in BOUND_INCOMPLETE_INTENTS
                    )
                elif confirmation_mode == "tuple_with_close_intent":
                    tail = strict[len(exact_strict):]
                    mode_valid = strict.startswith(exact_strict) and (
                        (result == "completed" and close_intent_in(tail, completed=True))
                        or (
                            result == "closed_incomplete"
                            and close_intent_in(tail, completed=False)
                        )
                    )
                if authority == ("user", "direct_user") and (
                    not mode_valid or authorization_quote != strict
                ):
                    errors.append(f"CLR {cid} direct confirmation binding invalid")
                elif known_invalid_legacy and (
                    f"pending_event_id={pend}" not in strict
                    or f"body_sha256={body_sha}" not in strict
                    or f"result={result}" not in strict
                ):
                    errors.append(f"CLR {cid} strict confirmation binding invalid")
            seen_legacy: set[str] = set()
            for alias in self.aliases:
                legacy = str(alias.get("legacy_id") or "")
                can = str(alias.get("canonical_id") or "")
                scope = str(alias.get("scope") or "activity")
                if legacy in seen_legacy:
                    errors.append(f"duplicate alias legacy_id: {legacy}")
                seen_legacy.add(legacy)
                if scope == "activity":
                    if not LEGACY_EXERCISE_RE.match(legacy):
                        errors.append(f"illegal legacy activity id output/alias: {legacy}")
                    if not EXERCISE_ID_RE.match(can):
                        errors.append(f"alias canonical must be exerciseNN: {can}")
                elif scope == "problem":
                    if not LEGACY_PROBLEM_RE.match(legacy):
                        errors.append(f"illegal legacy problem id: {legacy}")
                    if not PROBLEM_ID_RE.match(can):
                        errors.append(f"alias problem canonical must be exerciseNN-Qddd: {can}")
            rebuilt = self.rebuild_index()
            close_by_id = {
                str(close.get("close_id") or close.get("_header_id") or ""): close
                for close in self.closes
            }
            for event in self.events:
                if event.get("from_state") not in {"completed", "closed_incomplete"}:
                    continue
                close = close_by_id.get(str(event.get("reopens_close_id") or ""))
                if (
                    not close
                    or close.get("course_id") != self.course_id
                    or close.get("activity_type") != event.get("activity_type")
                    or close.get("activity_id") != event.get("activity_id")
                    or close.get("result") != event.get("from_state")
                ):
                    errors.append(
                        f"{event.get('event_id')}: reopen linkage is not same-activity terminal CLR"
                    )
            if validate_views:
                expected_index = render_index(rebuilt).strip()
                if self.current_index_text.strip() != expected_index:
                    errors.append("current index does not match append-only replay")
                for key, expected in current_stats(rebuilt).items():
                    try:
                        actual = int(str(self.stats.get(key, "missing")))
                    except ValueError:
                        continue
                    if actual != expected:
                        errors.append(
                            f"stats do not match replay: {key}={actual} expected={expected}"
                        )
                for key, expected in duration_stats(self.events).items():
                    try:
                        actual = int(str(self.stats.get(key, "missing")))
                    except ValueError:
                        continue
                    if actual != expected:
                        errors.append(
                            f"stats do not match duration replay: {key}={actual} expected={expected}"
                        )
            self.assert_capacity()
        except LedgerError as exc:
            errors.extend(exc.errors)
        return errors


def empty_ledger(course_id: str) -> str:
    return (
        f"---\n"
        f"type: activity_ledger\n"
        f"course_id: {course_id}\n"
        f"schema_version: activity_ledger.v1\n"
        f"truth_scope: activity_lifecycle\n"
        f"updated: unknown\n"
        f"---\n"
        f"# {course_id} activity ledger\n\n"
        f"> Lifecycle authority for Lesson/Exercise LearningActivities in this Course.\n"
        f"> Rebuild current index only from append-only ALE facts.\n\n"
        f"## Current index\n\n"
        f"_empty — no LearningActivities registered_\n\n"
        f"## Course preferences\n\n"
        f"lesson_actual_review: inherit\n"
        f"lesson_student_feedback: inherit\n"
        f"lesson_knowledge_absorption: inherit\n"
        f"exercise_problem_review: inherit\n"
        f"exercise_knowledge_mastery: inherit\n\n"
        f"## Aliases\n\n"
        f"_none_\n\n"
        f"## Stats\n\n"
        f"completed_lessons: 0\n"
        f"completed_exercises: 0\n"
        f"closed_incomplete_lessons: 0\n"
        f"closed_incomplete_exercises: 0\n\n"
        f"learning_exact_minutes: 0\n"
        f"learning_estimated_minutes: 0\n"
        f"learning_unknown_spans: 0\n\n"
        f"## Activity lifecycle events\n\n"
        f"_none_\n\n"
        f"## Close records\n\n"
        f"_none_\n"
    )


def render_index(index: dict[str, ActivityIndexEntry]) -> str:
    if not index:
        return "_empty — no LearningActivities registered_\n"
    lines = [
        "| activity_type | activity_id | state | binding_status | last_event_id |",
        "|---|---|---|---|---|",
    ]
    for key in sorted(index):
        e = index[key]
        lines.append(
            f"| {e.activity_type} | {e.activity_id} | {e.state} | "
            f"{e.binding_status} | {e.last_event_id} |"
        )
    return "\n".join(lines) + "\n"


def current_stats(index: dict[str, ActivityIndexEntry]) -> dict[str, int]:
    result = {
        "completed_lessons": 0,
        "completed_exercises": 0,
        "closed_incomplete_lessons": 0,
        "closed_incomplete_exercises": 0,
    }
    for entry in index.values():
        if entry.state in {"completed", "closed_incomplete"}:
            result[f"{entry.state}_{entry.activity_type}s"] += 1
    return result


def duration_stats(events: list[dict[str, Any]]) -> dict[str, int]:
    result = {
        "learning_exact_minutes": 0,
        "learning_estimated_minutes": 0,
        "learning_unknown_spans": 0,
    }
    for event in events:
        if event.get("event_kind") != "learning_exit":
            continue
        mode = str(event.get("duration_mode") or "")
        if mode == "unknown":
            result["learning_unknown_spans"] += 1
        elif mode in {"exact", "estimated"}:
            try:
                result[f"learning_{mode}_minutes"] += int(str(event.get("duration_minutes")))
            except ValueError:
                pass
    return result


def parse_ledger_text(text: str, *, path: Path | None = None) -> LedgerDocument:
    meta = {}
    body = text
    fm = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if fm:
        meta = parse_simple_yaml_block(fm.group(1))
        body = text[fm.end() :]
    course_id = str(meta.get("course_id") or "")
    events = split_records(section(body, "Activity lifecycle events"), "ALE")
    # also accept ### ALE-000001 style where header is the id
    if not events:
        events = []
        for match in re.finditer(
            r"(?ms)^###\s+(ALE-\d{6})\s*\n(.*?)(?=^###\s+ALE-|\Z)",
            section(body, "Activity lifecycle events"),
        ):
            data = parse_simple_yaml_block(match.group(2))
            data["event_id"] = match.group(1)
            data["_header_id"] = match.group(1)
            data["_raw"] = match.group(0)
            events.append(data)
    for event in events:
        if "event_id" not in event and event.get("_header_id"):
            event["event_id"] = event["_header_id"]
    closes = []
    for match in re.finditer(
        r"(?ms)^###\s+(CLR-\d{4})\s*\n(.*?)(?=^###\s+CLR-|\Z)",
        section(body, "Close records"),
    ):
        data = parse_simple_yaml_block(match.group(2))
        data["close_id"] = match.group(1)
        data["_header_id"] = match.group(1)
        closes.append(data)
    preferences = parse_simple_yaml_block(section(body, "Course preferences"))
    aliases = []
    alias_body = section(body, "Aliases")
    for match in re.finditer(
        r"(?ms)^###\s+alias\s+(\S+)\s*\n(.*?)(?=^###\s+alias|\Z)", alias_body
    ):
        data = parse_simple_yaml_block(match.group(2))
        data["legacy_id"] = data.get("legacy_id") or match.group(1)
        aliases.append(data)
    stats = parse_simple_yaml_block(section(body, "Stats"))
    return LedgerDocument(
        path=path,
        course_id=course_id,
        schema_version=str(meta.get("schema_version") or ""),
        truth_scope=str(meta.get("truth_scope") or ""),
        events=events,
        closes=closes,
        preferences={k: str(v) for k, v in preferences.items()},
        aliases=aliases,
        stats=stats,
        current_index_text=section(body, "Current index"),
        raw=text,
    )


def load_ledger(path: Path) -> LedgerDocument:
    if not path.is_file():
        raise LedgerError(f"ledger missing: {path}")
    return parse_ledger_text(path.read_text(encoding="utf-8"), path=path)


def validate_activity_id(activity_type: str, activity_id: str, *, allow_legacy: bool = False) -> None:
    if activity_type == "lesson":
        if not LESSON_ID_RE.match(activity_id):
            raise LedgerError(f"illegal lesson id: {activity_id}")
        return
    if activity_type == "exercise":
        if EXERCISE_ID_RE.match(activity_id):
            return
        if allow_legacy and LEGACY_EXERCISE_RE.match(activity_id):
            return
        raise LedgerError(f"illegal exercise id (need exerciseNN): {activity_id}")
    raise LedgerError(f"illegal activity_type: {activity_type}")


def reject_new_udddd(activity_id: str) -> None:
    if LEGACY_EXERCISE_RE.match(activity_id):
        raise LedgerError(f"new Udddd exercise ids are forbidden: {activity_id}")


def resolve_legacy_id(
    course_id: str,
    legacy_id: str,
    aliases: list[dict[str, Any]] | dict[str, str],
    *,
    expected_course_id: str | None = None,
) -> str:
    """Resolve course-scoped legacy id to canonical. Output is always canonical.

    Rejects path traversal, cross-course alias rows, and alias chains/cycles.
    """
    if not course_id or not legacy_id:
        raise LedgerError("resolve_legacy_id requires course_id and legacy_id")
    if ".." in legacy_id or "/" in legacy_id or "\\" in legacy_id:
        raise LedgerError(f"legacy id traversal refused: {legacy_id}")
    if expected_course_id is not None and expected_course_id != course_id:
        raise LedgerError(
            f"cross-course resolve refused: {expected_course_id} != {course_id}"
        )
    table: dict[str, tuple[str, str]] = {}
    if isinstance(aliases, dict):
        for leg, can in aliases.items():
            table[leg] = (course_id, can)
    else:
        for row in aliases:
            leg = str(row.get("legacy_id") or "")
            can = str(row.get("canonical_id") or "")
            row_course = str(row.get("course_id") or course_id)
            if not leg:
                continue
            if row_course != course_id:
                raise LedgerError(
                    f"cross-course alias refused: {leg} belongs to {row_course}"
                )
            table[leg] = (row_course, can)
    if legacy_id not in table:
        # already canonical?
        if EXERCISE_ID_RE.match(legacy_id) or LESSON_ID_RE.match(legacy_id) or PROBLEM_ID_RE.match(legacy_id):
            return legacy_id
        raise LedgerError(f"unknown legacy id for {course_id}: {legacy_id}")
    _, canonical = table[legacy_id]
    if canonical in table:
        raise LedgerError(f"alias chain/cycle refused: {legacy_id} -> {canonical}")
    if LEGACY_EXERCISE_RE.match(canonical) or LEGACY_PROBLEM_RE.match(canonical):
        raise LedgerError(f"alias must resolve to canonical, got {canonical}")
    return canonical


def resolve_next_action(
    *,
    current_activity_type: str,
    current_activity_id: str,
    current_state: str | None,
    index: dict[str, ActivityIndexEntry],
    planned: Iterable[tuple[str, str]] = (),
) -> dict[str, str]:
    """Return structured next_action fields per V2 §1.6 matrix."""
    cur_type = current_activity_type if current_activity_type not in {"", "none"} else "none"
    cur_id = current_activity_id if current_activity_id not in {"", "none"} else "none"
    if cur_type != "none" and current_state == "pending_close":
        return {
            "next_action_kind": "confirm_close",
            "next_activity_type": cur_type,
            "next_activity_id": cur_id,
        }
    if cur_type != "none" and current_state == "ongoing":
        return {
            "next_action_kind": "resume",
            "next_activity_type": cur_type,
            "next_activity_id": cur_id,
        }
    actives = [
        e
        for e in index.values()
        if e.state in ACTIVE_CAPACITY_STATES
    ]
    if cur_type == "none" and len(actives) == 1:
        e = actives[0]
        return {
            "next_action_kind": "resume",
            "next_activity_type": e.activity_type,
            "next_activity_id": e.activity_id,
        }
    if cur_type == "none" and len(actives) > 1:
        return {
            "next_action_kind": "choose_activity",
            "next_activity_type": "none",
            "next_activity_id": "none",
        }
    planned_list = list(planned)
    if cur_type == "none" and not actives and len(planned_list) == 1:
        t, i = planned_list[0]
        return {
            "next_action_kind": "start_activity",
            "next_activity_type": t,
            "next_activity_id": i,
        }
    if cur_type == "none" and not actives and len(planned_list) > 1:
        return {
            "next_action_kind": "choose_activity",
            "next_activity_type": "none",
            "next_activity_id": "none",
        }
    return {
        "next_action_kind": "none",
        "next_activity_type": "none",
        "next_activity_id": "none",
    }


def render_migration_snapshot_event(
    *,
    event_id: str,
    course_id: str,
    activity_type: str,
    activity_id: str,
    observed_state: str,
    recorded_at: str,
    transaction_id: str,
    observed_from_refs: list[str],
    evidence_refs: list[str],
    binding_status: str = "bound",
    binding_reason: str = "",
    content_group_ids: list[str] | None = None,
) -> str:
    validate_activity_id(activity_type, activity_id)
    if observed_state not in ACTIVITY_STATES:
        raise LedgerError(f"bad observed_state: {observed_state}")
    cgs = content_group_ids or []
    lines = [
        f"### {event_id}",
        f"event_id: {event_id}",
        "event_kind: migration_snapshot",
        f"course_id: {course_id}",
        f"activity_type: {activity_type}",
        f"activity_id: {activity_id}",
        f"observed_state: {observed_state}",
        "from_state: null",
        f"to_state: {observed_state}",
        "occurred_at: null",
        f"recorded_at: {recorded_at}",
        "historical_effective_at: unknown",
        "history_completeness: partial",
        "triggered_by: migration",
        "trigger: 0.2.1_to_0.2.2_snapshot",
        f"transaction_id: {transaction_id}",
        f"binding_status: {binding_status}",
        f"binding_reason: {binding_reason or 'none'}",
        f"content_group_ids: [{', '.join(cgs)}]",
        f"observed_from_refs: [{', '.join(observed_from_refs)}]",
        f"evidence_refs: [{', '.join(evidence_refs)}]",
        "",
    ]
    return "\n".join(lines)


def build_ledger_with_events(
    course_id: str,
    events_markdown: str,
    *,
    aliases_markdown: str = "_none_\n",
    preferences: dict[str, str] | None = None,
) -> str:
    prefs = preferences or {
        "lesson_actual_review": "inherit",
        "lesson_student_feedback": "inherit",
        "lesson_knowledge_absorption": "inherit",
        "exercise_problem_review": "inherit",
        "exercise_knowledge_mastery": "inherit",
    }
    pref_lines = "\n".join(f"{k}: {v}" for k, v in prefs.items())
    events_body = events_markdown.strip() if events_markdown.strip() else "_none_"
    draft = (
        f"---\n"
        f"type: activity_ledger\n"
        f"course_id: {course_id}\n"
        f"schema_version: activity_ledger.v1\n"
        f"truth_scope: activity_lifecycle\n"
        f"updated: pending\n"
        f"---\n"
        f"# {course_id} activity ledger\n\n"
        f"## Current index\n\n"
        f"_rebuild_\n\n"
        f"## Course preferences\n\n"
        f"{pref_lines}\n\n"
        f"## Aliases\n\n"
        f"{aliases_markdown.strip()}\n\n"
        f"## Stats\n\n"
        f"completed_lessons: 0\n"
        f"completed_exercises: 0\n"
        f"closed_incomplete_lessons: 0\n"
        f"closed_incomplete_exercises: 0\n\n"
        f"learning_exact_minutes: 0\n"
        f"learning_estimated_minutes: 0\n"
        f"learning_unknown_spans: 0\n\n"
        f"## Activity lifecycle events\n\n"
        f"{events_body}\n\n"
        f"## Close records\n\n"
        f"_none_\n"
    )
    initial = parse_ledger_text(draft)
    index = initial.rebuild_index()
    rendered = draft.replace("_rebuild_\n", render_index(index))
    stats_body = "\n".join(
        f"{key}: {value}"
        for key, value in {**current_stats(index), **duration_stats(initial.events)}.items()
    )
    rendered = re.sub(
        r"(?ms)(^##\s+Stats\s*\n).*?(?=^##\s+)",
        lambda match: match.group(1) + "\n" + stats_body + "\n\n",
        rendered,
        count=1,
    )
    errors = parse_ledger_text(rendered).validate()
    if errors:
        raise LedgerError(errors)
    return rendered


def cmd_validate(path: Path) -> int:
    try:
        doc = load_ledger(path)
    except LedgerError as exc:
        print(json.dumps({"ok": False, "errors": exc.errors}, ensure_ascii=False))
        return 1
    errors = doc.validate()
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False))
        return 1
    index = doc.rebuild_index()
    print(
        json.dumps(
            {
                "ok": True,
                "course_id": doc.course_id,
                "events": len(doc.events),
                "index": {
                    k: {
                        "state": v.state,
                        "type": v.activity_type,
                        "id": v.activity_id,
                    }
                    for k, v in index.items()
                },
                "capacity": doc.capacity_usage(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_val = sub.add_parser("validate")
    p_val.add_argument("path", type=Path)
    p_empty = sub.add_parser("empty")
    p_empty.add_argument("course_id")
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        return cmd_validate(args.path)
    if args.cmd == "empty":
        sys.stdout.write(empty_ledger(args.course_id))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
