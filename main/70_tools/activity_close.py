#!/usr/bin/env python3
"""Transactional Lesson/Exercise close runtime for T2AG 0.2.2."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, time as wall_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_ledger as ledger  # noqa: E402
import activity_transaction as txn  # noqa: E402
import campaign_receipt as campaign  # noqa: E402
import t2ag_state_refresh as state_refresh  # noqa: E402

CAMPAIGN_ID = campaign.CAMPAIGN_ID
# EV-0022：生产根不再绑定维护者机器字面量，派生自代码所在仓根——
# 任何安装实例的仓根就是它自己的生产根，direct_user 授权闸门在所有实例上生效；
# 显式 --root 指向其它路径时仍落入 test/shadow guard 分支（fail-closed 语义不变）。
INSTANCE_ROOT = Path(__file__).resolve().parents[2]
# 兼容 alias：旧消费方（activity_lifecycle、doctor 环境探测、测试 patch）仍读此名。
PRODUCTION_ROOT = INSTANCE_ROOT
KNOWLEDGE_STATES = ledger.KNOWLEDGE_STATES
PREF_KEYS = (
    "lesson_actual_review",
    "lesson_student_feedback",
    "lesson_knowledge_absorption",
    "exercise_problem_review",
    "exercise_knowledge_mastery",
)
CLOSE_BODY_SCHEMA = "activity_close_body.v2"
RETROSPECTIVE_TREE: dict[str, tuple[str, ...]] = {
    "actual_teaching_process": (
        "taught_content",
        "teaching_sequence",
        "expanded_or_skipped",
        "plan_difference",
    ),
    "content_completion": (
        "completed_content",
        "unfinished_content",
        "out_of_scope_content",
        "next_lesson_boundary",
    ),
    "knowledge_absorption": (
        "initial_understanding",
        "reasoning_difficulties",
        "turning_points",
        "self_correction",
        "independent_reconstruction_or_transfer",
        "current_mastery",
        "remaining_retests",
    ),
    "course_content_feedback": (
        "valuable_content",
        "difficult_content",
        "content_sequence",
        "example_effectiveness",
        "redundancy_or_omission",
        "requested_course_adjustment",
    ),
    "teacher_reflection": (
        "effective_explanations",
        "overcompressed_expressions",
        "over_assistance",
        "next_teaching_improvement",
    ),
    "learning_transition": (
        "spaced_retests",
        "next_lesson_entry",
        "learner_thought_followup",
    ),
}
REVIEW_STATUSES = frozenset({"applicable", "not_applicable", "missing"})
BOUND_COMPLETED_INTENTS = frozenset({"结课", "确认结课", "愿意结课"})
BOUND_INCOMPLETE_INTENTS = frozenset({"以未完成状态结课", "确认以未完成状态结课"})
RETROSPECTIVE_SECTION_LABELS = {
    "actual_teaching_process": "实际教学过程",
    "content_completion": "课程内容完成情况",
    "knowledge_absorption": "知识吸收",
    "course_content_feedback": "学生课程内容反馈",
    "teacher_reflection": "教师教学反思",
    "learning_transition": "后续学习衔接",
}
RETROSPECTIVE_ITEM_LABELS = {
    "taught_content": "实际讲授",
    "teaching_sequence": "教学顺序",
    "expanded_or_skipped": "展开或跳过",
    "plan_difference": "计划差异",
    "completed_content": "已完成内容",
    "unfinished_content": "未完成内容",
    "out_of_scope_content": "越界内容",
    "next_lesson_boundary": "下一 Lesson 边界",
    "initial_understanding": "最初理解",
    "reasoning_difficulties": "思维困难",
    "turning_points": "理解转折点",
    "self_correction": "自我修正",
    "independent_reconstruction_or_transfer": "独立复述或迁移",
    "current_mastery": "当前掌握",
    "remaining_retests": "仍需复测",
    "valuable_content": "有价值的内容",
    "difficult_content": "难懂内容",
    "content_sequence": "内容顺序",
    "example_effectiveness": "例子效果",
    "redundancy_or_omission": "冗余或缺失",
    "requested_course_adjustment": "希望怎样调整课程",
    "effective_explanations": "有效讲解",
    "overcompressed_expressions": "过度压缩的表达",
    "over_assistance": "帮助边界",
    "next_teaching_improvement": "下次教学改进",
    "spaced_retests": "间隔复测",
    "next_lesson_entry": "下一 Lesson 入口",
    "learner_thought_followup": "学生想法后续消费",
}
TERMINAL_DECISIONS = {
    "confirm_completed": "completed",
    "confirm_closed_incomplete": "closed_incomplete",
}
DIRECT_USER_AUTHORITY = ("user", "direct_user")
PRODUCTION_DECISION_AUTHORITIES = frozenset({DIRECT_USER_AUTHORITY})
PRODUCTION_APPLY_AUTHORIZATION_MODES = frozenset({"direct_user"})


class CloseError(RuntimeError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str | None:
    return txn.sha256_file(path)


def line_ending_drift(raw: bytes | None, expected_sha: str) -> str:
    """Name the line-ending variant that would satisfy ``expected_sha``.

    T2AG binds evidence to the SHA-256 of file bytes: frozen plans, executor
    manifests, preparation snapshots and receipt chains.  A host that rewrites
    LF to CRLF therefore invalidates all of it while changing nothing that
    matters.  A bare "hash mismatch" does not say so, and during the 0.2.2
    campaign that ambiguity cost a full exact-plan shadow re-run before the
    cause was identified.

    This does not prevent the drift -- ``.gitattributes`` does.  It converts a
    two-hour misdiagnosis into one line of output.  Returns "" when the bytes
    differ for any reason other than line endings, so a real content change is
    never explained away as a formatting artifact.
    """
    if not raw or not expected_sha:
        return ""
    lf = raw.replace(b"\r\n", b"\n")
    for label, data in (("LF", lf), ("CRLF", lf.replace(b"\n", b"\r\n"))):
        if data != raw and sha256_bytes(data) == expected_sha:
            return (
                f" -- LINE ENDING DRIFT, not a content change: the bytes match"
                f" once normalised to {label}. A host rewrote line endings and"
                f" T2AG hashes file bytes. Restore the file (.gitattributes"
                f" pins '* text=auto eol=lf'); do NOT regenerate the plan or"
                f" re-run the evidence matrices."
            )
    return ""


def text_line_ending_drift(content: str, expected_sha: str) -> str:
    """``line_ending_drift`` for content already decoded to str."""
    return line_ending_drift(content.encode("utf-8"), expected_sha)


def now_tz() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def b64_json(value: object) -> str:
    return base64.b64encode(canonical_json(value).encode("utf-8")).decode("ascii")


def resolve_prefs(
    global_prefs: dict[str, str],
    course_prefs: dict[str, str],
    once_prefs: dict[str, str] | None = None,
) -> dict[str, str]:
    once_prefs = once_prefs or {}
    result: dict[str, str] = {}
    for key in PREF_KEYS:
        g = global_prefs.get(key, "on")
        c = course_prefs.get(key, "inherit")
        o = once_prefs.get(key, "inherit")
        if o in {"on", "off"}:
            result[key] = o
        elif c in {"on", "off"}:
            result[key] = c
        else:
            result[key] = g if g in {"on", "off"} else "on"
    return result


def _review_item(value: Any) -> dict[str, Any]:
    """Normalize one closeout-tree leaf without inventing lesson content."""
    if value is None:
        return {"status": "missing"}
    if isinstance(value, str):
        value = {"status": "applicable", "summary": value}
    if not isinstance(value, dict):
        raise CloseError("retrospective item must be an object, string, or null")
    item = dict(value)
    status = str(item.get("status") or "applicable")
    if status not in REVIEW_STATUSES:
        raise CloseError(f"illegal retrospective status: {status}")
    item["status"] = status
    if status == "applicable" and not str(item.get("summary") or "").strip():
        raise CloseError("applicable retrospective item requires summary")
    if status == "not_applicable" and not str(item.get("reason") or "").strip():
        raise CloseError("not_applicable retrospective item requires reason")
    refs = item.get("evidence_refs")
    if refs is not None and (
        not isinstance(refs, list)
        or any(not str(ref).strip() for ref in refs)
    ):
        raise CloseError("retrospective evidence_refs must be nonempty strings")
    return item


def _simple_review_node(value: Any, *, default_refs: list[str] | None = None) -> dict[str, Any]:
    node = _review_item(value)
    if node["status"] == "applicable" and default_refs and "evidence_refs" not in node:
        node["evidence_refs"] = list(default_refs)
    return node


def build_teaching_retrospective(
    supplied: Any,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Traverse every approved retrospective leaf and aggregate applicable content."""
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict):
        raise CloseError("teaching_retrospective must be an object")
    unknown_sections = set(supplied) - set(RETROSPECTIVE_TREE)
    if unknown_sections:
        if "system_feedback" in unknown_sections:
            raise CloseError(
                "system_feedback must be routed outside course_content_feedback"
            )
        raise CloseError(
            f"unknown teaching_retrospective sections: {sorted(unknown_sections)}"
        )
    tree: dict[str, Any] = {}
    visible: dict[str, Any] = {}
    complete = True
    for section_name, leaf_names in RETROSPECTIVE_TREE.items():
        raw_section = supplied.get(section_name) or {}
        if not isinstance(raw_section, dict):
            raise CloseError(f"retrospective section must be an object: {section_name}")
        declared_status = raw_section.get("status")
        declared_reason = str(raw_section.get("reason") or "").strip()
        raw_items = raw_section.get("items") or {}
        if not isinstance(raw_items, dict):
            raise CloseError(f"retrospective items must be an object: {section_name}")
        items: dict[str, Any] = {}
        for leaf_name in leaf_names:
            if declared_status == "not_applicable" and leaf_name not in raw_items:
                raw_value: Any = {
                    "status": "not_applicable",
                    "reason": declared_reason,
                }
            else:
                raw_value = raw_items.get(leaf_name)
            items[leaf_name] = _review_item(raw_value)
        statuses = [item["status"] for item in items.values()]
        if "missing" in statuses:
            section_status = "missing"
            complete = False
        elif all(status == "not_applicable" for status in statuses):
            section_status = "not_applicable"
        else:
            section_status = "applicable"
        applicable_summaries = [
            str(item["summary"]).strip()
            for item in items.values()
            if item["status"] == "applicable"
        ]
        section: dict[str, Any] = {"status": section_status, "items": items}
        if section_status == "not_applicable":
            section["reason"] = declared_reason or next(
                str(item["reason"]) for item in items.values()
            )
        if applicable_summaries:
            section["summary"] = str(raw_section.get("summary") or "；".join(applicable_summaries)).strip()
            visible[section_name] = {
                "summary": section["summary"],
                "items": {
                    key: value
                    for key, value in items.items()
                    if value["status"] == "applicable"
                },
            }
        tree[section_name] = section
    return tree, visible, complete


def learner_retrospective_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Return the exact student-facing closeout object bound to dialogue delivery."""
    if body.get("schema") != CLOSE_BODY_SCHEMA:
        raise CloseError("learner-facing retrospective requires activity_close_body.v2")
    visible = body.get("learner_visible_retrospective")
    if not isinstance(visible, dict) or not visible:
        raise CloseError("learner-facing retrospective is missing")
    return {
        "activity_type": body.get("activity_type"),
        "activity_id": body.get("activity_id"),
        "close_scope": body.get("close_scope"),
        "learner_visible_retrospective": visible,
        "knowledge": body.get("knowledge") or [],
        "completion_assessment": body.get("completion_assessment") or {},
        "recommendation": body.get("recommendation"),
    }


def learner_retrospective_sha256(body: dict[str, Any]) -> str:
    return sha256_text(canonical_json(learner_retrospective_payload(body)))


def render_learner_retrospective(body: dict[str, Any]) -> str:
    """Render the complete applicable-item summary for direct dialogue display."""
    payload = learner_retrospective_payload(body)
    lines = [
        f"# {payload['activity_id']} 教学复盘",
        "",
        "## 结课范围",
        "",
        str((payload.get("close_scope") or {}).get("summary") or "未提供范围摘要"),
    ]
    visible = payload["learner_visible_retrospective"]
    for section_name in RETROSPECTIVE_TREE:
        section = visible.get(section_name)
        if not isinstance(section, dict):
            continue
        lines.extend(["", f"## {RETROSPECTIVE_SECTION_LABELS[section_name]}", ""])
        for item_name in RETROSPECTIVE_TREE[section_name]:
            item = (section.get("items") or {}).get(item_name)
            if not isinstance(item, dict) or item.get("status") != "applicable":
                continue
            lines.append(
                f"- **{RETROSPECTIVE_ITEM_LABELS[item_name]}**：{item['summary']}"
            )
    lines.extend(["", "## 掌握层级", ""])
    for item in payload["knowledge"]:
        lines.append(f"- `{item.get('state')}`：{item.get('topic')}")
    assessment = payload["completion_assessment"]
    lines.extend(
        [
            "",
            "## 完成性判定",
            "",
            f"- completion blockers：{assessment.get('completion_blockers') or '无'}",
            f"- scope change：{assessment.get('scope_change') or '无'}",
            f"- 判定理由：{assessment.get('reason') or '未提供'}",
            f"- 推荐结果：`{payload.get('recommendation')}`",
            "",
            "---",
            f"复盘展示 SHA-256：`{learner_retrospective_sha256(body)}`",
        ]
    )
    return "\n".join(lines)


def build_close_body(
    *,
    activity_type: str,
    activity_id: str,
    prefs: dict[str, str],
    knowledge: list[dict[str, str]] | None = None,
    blockers: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    student_feedback_ref: str | None = None,
    content_sections: dict[str, Any] | None = None,
    scope_change: dict[str, Any] | None = None,
    scope_change_confirmed: bool = False,
) -> dict[str, Any]:
    ledger.validate_activity_id(activity_type, activity_id)
    knowledge = knowledge or []
    blockers = blockers or []
    if scope_change and not scope_change_confirmed:
        blockers = [*blockers, "unconfirmed_scope_change"]
    evidence_refs = evidence_refs or []
    content_sections = content_sections or {}
    for item in knowledge:
        if item.get("state") not in KNOWLEDGE_STATES:
            raise CloseError(f"illegal knowledge state: {item.get('state')}")
        if not str(item.get("topic") or "").strip():
            raise CloseError("knowledge item requires topic")
    close_scope = _simple_review_node(content_sections.get("close_scope"))
    evidence_collection = _simple_review_node(
        content_sections.get("evidence_collection"),
        default_refs=evidence_refs,
    )
    retrospective, learner_visible, tree_complete = build_teaching_retrospective(
        content_sections.get("teaching_retrospective")
    )
    knowledge_section = retrospective["knowledge_absorption"]
    feedback_section = retrospective["course_content_feedback"]
    mandatory_evidence = {
        "evidence_refs_present": bool(evidence_refs),
        "knowledge_evidence_present": bool(knowledge),
        "scope_review_complete": close_scope["status"] != "missing",
        "evidence_collection_complete": evidence_collection["status"] != "missing",
        "retrospective_tree_complete": tree_complete,
        "knowledge_absorption_narrative_present": knowledge_section["status"]
        != "missing",
        "course_content_feedback_assessed": feedback_section["status"]
        != "missing",
    }
    completion_reason = (
        "无 blocker，范围、证据与结课树均已逐项检查；not_applicable 节点不阻断完成。"
        if not blockers and all(mandatory_evidence.values())
        else "仍有 blocker 或结课树中的 missing 节点，不能推荐 completed。"
    )
    body: dict[str, Any] = {
        "schema": CLOSE_BODY_SCHEMA,
        "activity_type": activity_type,
        "activity_id": activity_id,
        "close_scope": close_scope,
        "evidence_collection": evidence_collection,
        "teaching_retrospective": retrospective,
        "learner_visible_retrospective": learner_visible,
        "preferences_snapshot": {key: prefs.get(key, "on") for key in PREF_KEYS},
        "knowledge": knowledge,
        "completion_blockers": blockers,
        "evidence_refs": evidence_refs,
        "course_content_feedback_ref": student_feedback_ref,
        # Kept only as a read-compatible alias for v1 callers and ledger history.
        "student_feedback_ref": student_feedback_ref,
        "scope_change": scope_change,
        "scope_change_confirmed": bool(scope_change and scope_change_confirmed),
        "mandatory_evidence": mandatory_evidence,
        "completion_assessment": {
            "mandatory_evidence": mandatory_evidence,
            "completion_blockers": blockers,
            "scope_change": scope_change,
            "scope_change_confirmed": bool(scope_change and scope_change_confirmed),
            "reason": completion_reason,
        },
        "recommendation": (
            "completed"
            if not blockers and all(mandatory_evidence.values())
            else "closed_incomplete"
        ),
    }
    body["body_sha256"] = sha256_text(canonical_json(body))
    return body


def deterministic_decision(body: dict[str, Any]) -> str:
    blockers = list(body.get("completion_blockers") or [])
    mandatory = body.get("mandatory_evidence") or {}
    recommendation = body.get("recommendation")
    if (
        not blockers
        and mandatory
        and all(bool(value) for value in mandatory.values())
        and recommendation == "completed"
    ):
        return "confirm_completed"
    return "confirm_closed_incomplete"


def parse_strict_confirmation(text: str) -> dict[str, str]:
    match = re.fullmatch(
        r"pending_event_id=(ALE-\d{6})\r?\n"
        r"body_sha256=([0-9a-f]{64})\r?\n"
        r"result=(completed|closed_incomplete)",
        text or "",
    )
    if not match:
        raise CloseError(
            "exact confirmation must contain exactly three bound lines: "
            "pending_event_id=ALE-…, body_sha256=…, "
            "result=completed|closed_incomplete"
        )
    return {
        "pending_event_id": match.group(1),
        "body_sha256": match.group(2),
        "result": match.group(3),
    }


def parse_bound_close_confirmation(
    text: str,
    *,
    pending_event_id: str,
    body_sha256: str,
    result: str,
) -> dict[str, str]:
    """Bind concise learner intent to the one tuple already shown by the system."""
    raw = text or ""
    try:
        parsed = parse_strict_confirmation(raw)
    except CloseError:
        parsed = None
    if parsed is not None:
        return {**parsed, "confirmation_mode": "exact_tuple"}

    normalized = raw.strip().rstrip("。！!").strip()
    if result == "completed" and normalized in BOUND_COMPLETED_INTENTS:
        return {
            "pending_event_id": pending_event_id,
            "body_sha256": body_sha256,
            "result": result,
            "confirmation_mode": "bound_close_intent",
        }
    if result == "closed_incomplete" and normalized in BOUND_INCOMPLETE_INTENTS:
        return {
            "pending_event_id": pending_event_id,
            "body_sha256": body_sha256,
            "result": result,
            "confirmation_mode": "bound_incomplete_close_intent",
        }

    tuple_with_comment = re.fullmatch(
        r"pending_event_id=(ALE-\d{6})\r?\n"
        r"body_sha256=([0-9a-f]{64})\r?\n"
        r"result=(completed|closed_incomplete)([\s\S]*)",
        raw,
    )
    if tuple_with_comment:
        tail = tuple_with_comment.group(4).strip()
        intent_matches = (
            result == "completed" and "结课" in tail
        ) or (
            result == "closed_incomplete" and "以未完成状态结课" in tail
        )
        if intent_matches:
            return {
                "pending_event_id": tuple_with_comment.group(1),
                "body_sha256": tuple_with_comment.group(2),
                "result": tuple_with_comment.group(3),
                "confirmation_mode": "tuple_with_close_intent",
            }
    raise CloseError(
        "close confirmation must be the shown exact tuple, or a bound close intent "
        "such as 结课 after the complete retrospective has been presented"
    )


def plan_pending(
    *,
    course_id: str,
    activity_type: str,
    activity_id: str,
    from_state: str = "ongoing",
    prefs: dict[str, str] | None = None,
) -> dict[str, Any]:
    prefs = prefs or {key: "on" for key in PREF_KEYS}
    body = build_close_body(
        activity_type=activity_type,
        activity_id=activity_id,
        prefs=prefs,
    )
    return {
        "mode": "plan",
        "course_id": course_id,
        "transition": {"from": from_state, "to": "pending_close"},
        "body": body,
        "next_action": ledger.resolve_next_action(
            current_activity_type=activity_type,
            current_activity_id=activity_id,
            current_state="pending_close",
            index={
                f"{activity_type}:{activity_id}": ledger.ActivityIndexEntry(
                    activity_type, activity_id, "pending_close"
                )
            },
        ),
    }


def learning_day(timestamp: str, timezone_name: str, cutoff: str) -> str:
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    try:
        zone = ZoneInfo(timezone_name)
    except Exception as exc:  # Windows stdlib may not ship the IANA database.
        fixed_offsets = {
            "Asia/Singapore": timezone(timedelta(hours=8)),
            "Asia/Shanghai": timezone(timedelta(hours=8)),
            "Asia/Hong_Kong": timezone(timedelta(hours=8)),
            "UTC": timezone.utc,
        }
        if timezone_name not in fixed_offsets:
            raise CloseError(f"timezone unavailable: {timezone_name}") from exc
        zone = fixed_offsets[timezone_name]
    local = moment.astimezone(zone)
    hour, minute = (int(part) for part in cutoff.split(":", 1))
    boundary = datetime.combine(local.date(), wall_time(hour, minute), tzinfo=zone)
    return (local.date() if local >= boundary else local.date() - timedelta(days=1)).isoformat()


def duration_totals(spans: list[dict[str, Any]]) -> dict[str, Any]:
    exact = 0
    estimated = 0
    unknown = 0
    for span in spans:
        mode = span.get("duration_mode")
        minutes = span.get("minutes")
        if mode not in {"exact", "estimated", "unknown"}:
            raise CloseError(f"illegal duration_mode: {mode}")
        if mode == "unknown":
            if minutes not in {None, "", 0}:
                raise CloseError("unknown duration cannot carry minutes")
            unknown += 1
            continue
        if not isinstance(minutes, int) or minutes < 0:
            raise CloseError(f"{mode} duration requires nonnegative integer minutes")
        if mode == "exact":
            exact += minutes
        else:
            estimated += minutes
    return {
        "exact_minutes": exact,
        "estimated_minutes": estimated,
        "unknown_spans": unknown,
    }


def frontmatter_split(text: str) -> tuple[dict[str, str], list[str], str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        raise CloseError("progress missing frontmatter")
    meta: dict[str, str] = {}
    order: list[str] = []
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        meta[key] = value.strip()
        order.append(key)
    return meta, order, text[match.end() :]


def rebuild_frontmatter(meta: dict[str, str], order: list[str]) -> str:
    keys = [key for key in order if key in meta]
    keys.extend(key for key in meta if key not in keys)
    return "---\n" + "\n".join(f"{key}: {meta[key]}" for key in keys) + "\n---\n"


def load_preference_context(
    root: Path,
    course_id: str,
    once_prefs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve one-shot > course > global preferences with legacy defaults."""
    profile_path = root / "main/10_student/profile/profile.md"
    global_prefs = {key: "on" for key in PREF_KEYS}
    profile_meta: dict[str, str] = {}
    if profile_path.is_file():
        profile_meta, _, _ = frontmatter_split(
            profile_path.read_text(encoding="utf-8-sig")
        )
        schema = profile_meta.get("activity_close_preference_schema")
        if schema and schema != "activity_close_preferences.v1":
            raise CloseError(f"unsupported preference schema: {schema}")
        for key in PREF_KEYS:
            value = profile_meta.get(key, "on")
            if value not in {"on", "off"}:
                raise CloseError(f"illegal global preference {key}={value}")
            global_prefs[key] = value

    ledger_path = root / f"main/40_course/{course_id}/activity_ledger.md"
    course_prefs = {key: "inherit" for key in PREF_KEYS}
    if ledger_path.is_file():
        doc = ledger.load_ledger(ledger_path)
        errors = doc.validate()
        if errors:
            raise CloseError("preference ledger invalid: " + "; ".join(errors))
        course_prefs.update(doc.preferences)
    once = once_prefs or {}
    for key, value in once.items():
        if key not in PREF_KEYS or value not in {"on", "off", "inherit"}:
            raise CloseError(f"illegal one-shot preference {key}={value}")
    return {
        "schema": "activity_close_preferences.v1",
        "global": global_prefs,
        "course": course_prefs,
        "once": {key: once.get(key, "inherit") for key in PREF_KEYS},
        "resolved": resolve_prefs(global_prefs, course_prefs, once),
        "first_prompt_required": profile_meta.get(
            "activity_close_first_prompt_status", "pending"
        )
        != "shown",
        "learning_timezone": profile_meta.get("learning_timezone", "Asia/Singapore"),
        "learning_day_cutoff": profile_meta.get("learning_day_cutoff", "04:00"),
    }


def mark_first_close_prompt(text: str, *, recorded_at: str) -> str:
    meta, order, body = frontmatter_split(text)
    if meta.get("activity_close_first_prompt_status") == "shown":
        return text
    meta["activity_close_first_prompt_status"] = "shown"
    meta["activity_close_first_prompt_at"] = recorded_at
    for key in (
        "activity_close_first_prompt_status",
        "activity_close_first_prompt_at",
    ):
        if key not in order:
            order.append(key)
    return rebuild_frontmatter(meta, order) + body


def next_numeric_id(values: list[str], prefix: str, width: int) -> str:
    numbers = [
        int(value.split("-", 1)[1])
        for value in values
        if re.fullmatch(rf"{re.escape(prefix)}-\d{{{width}}}", value)
    ]
    return f"{prefix}-{(max(numbers, default=0) + 1):0{width}d}"


def render_event(fields: dict[str, Any]) -> str:
    event_id = str(fields["event_id"])
    lines = [f"### {event_id}"]
    for key, value in fields.items():
        if isinstance(value, list):
            rendered = "[" + ", ".join(str(item) for item in value) + "]"
        elif value is None:
            rendered = "null"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    return "\n".join(lines) + "\n"


def render_close(fields: dict[str, Any]) -> str:
    close_id = str(fields["close_id"])
    lines = [f"### {close_id}"]
    for key, value in fields.items():
        if isinstance(value, list):
            rendered = "[" + ", ".join(str(item) for item in value) + "]"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    return "\n".join(lines) + "\n"


def replace_section(text: str, title: str, body: str) -> str:
    pattern = re.compile(
        rf"(?ms)(^##\s+{re.escape(title)}\s*\n)(.*?)(?=^##\s+|\Z)"
    )
    match = pattern.search(text)
    if not match:
        raise CloseError(f"ledger section missing: {title}")
    return text[: match.start(2)] + "\n" + body.strip() + "\n\n" + text[match.end(2) :]


def append_section_record(text: str, title: str, record: str) -> str:
    current = ledger.section(text, title)
    if not current or current.strip() in {"_none_", "_rebuild_"}:
        body = record.strip()
    else:
        body = current.rstrip() + "\n\n" + record.strip()
    return replace_section(text, title, body)


def compute_stats(doc: ledger.LedgerDocument) -> dict[str, int]:
    index = doc.rebuild_index()
    stats = {
        "completed_lessons": 0,
        "completed_exercises": 0,
        "closed_incomplete_lessons": 0,
        "closed_incomplete_exercises": 0,
        "historical_completed_lessons": 0,
        "historical_completed_exercises": 0,
        "historical_closed_incomplete_lessons": 0,
        "historical_closed_incomplete_exercises": 0,
    }
    for entry in index.values():
        if entry.state in {"completed", "closed_incomplete"}:
            key = f"{entry.state}_{entry.activity_type}s"
            stats[key] += 1
    for close in doc.closes:
        result = str(close.get("result") or "")
        kind = str(close.get("activity_type") or "")
        key = f"historical_{result}_{kind}s"
        if key in stats:
            stats[key] += 1
    stats.update(ledger.duration_stats(doc.events))
    return stats


def refresh_ledger_views(text: str, recorded_at: str) -> str:
    doc = ledger.parse_ledger_text(text)
    errors = doc.validate(validate_views=False)
    if errors:
        raise CloseError("ledger invalid: " + "; ".join(errors))
    text = replace_section(text, "Current index", ledger.render_index(doc.rebuild_index()))
    stats = compute_stats(doc)
    text = replace_section(
        text,
        "Stats",
        "\n".join(f"{key}: {value}" for key, value in stats.items()),
    )
    text = re.sub(r"(?m)^updated:\s*.*$", f"updated: {recorded_at}", text, count=1)
    final = ledger.parse_ledger_text(text)
    errors = final.validate()
    if errors:
        raise CloseError("refreshed ledger invalid: " + "; ".join(errors))
    return text


def update_progress(
    text: str,
    *,
    activity_type: str,
    activity_id: str,
    state: str,
    next_action: dict[str, str],
) -> str:
    meta, order, body = frontmatter_split(text)
    if state in {"completed", "closed_incomplete"}:
        updates = {
            "current_activity": "none",
            "current_activity_id": "none",
            "resume_path": "none",
            "activity_position": "between_activities",
            "textbook_page": "none",
            "current_completion_node": "none",
            "current_checkpoint": "none",
            "checkpoint_state": "none",
        }
    else:
        updates = {
            "current_activity": activity_type,
            "current_activity_id": activity_id,
            "resume_path": (
                f"main/40_course/{meta.get('course_id')}/"
                + (
                    f"lessons/{activity_id}/{activity_id}.md"
                    if activity_type == "lesson"
                    else f"exercises/{activity_id}/exercise.md"
                )
            ),
        }
    updates.update(next_action)
    for key, value in updates.items():
        meta[key] = value
        if key not in order:
            order.append(key)
    kind = next_action.get("next_action_kind", "none")
    next_type = next_action.get("next_activity_type", "none")
    next_id = next_action.get("next_activity_id", "none")
    if kind in {"resume", "confirm_close", "start_activity"}:
        body_text = f"{kind} {next_type}:{next_id}；以结构化 next_action_* 字段为准。"
    elif kind == "choose_activity":
        body_text = "从多个可用活动中选择下一项；以结构化 next_action_* 字段为准。"
    else:
        body_text = "当前没有自动选择的下一活动；以结构化 next_action_* 字段为准。"
    next_pattern = re.compile(
        r"(?ms)^-\s+\*\*(?:下一步计划|下一步|下次第一件事)\*\*[：:].*?"
        r"(?=^-\s+\*\*|^##\s|\Z)"
    )
    replacement = f"- **下一步计划**：{body_text}\n"
    if next_pattern.search(body):
        body = next_pattern.sub(replacement, body, count=1)
    elif "## 二、当前进度" in body:
        body = body.replace(
            "## 二、当前进度\n",
            "## 二、当前进度\n\n" + replacement,
            1,
        )
    if state in {"completed", "closed_incomplete"}:
        terminal_summary = {
            "当前讲授页": (
                f"本次 {activity_type}:{activity_id} 已原子关闭；"
                f"恢复路线为 {body_text.split('；', 1)[0]}，尚未开始新的教学推进。"
            ),
            "当前教学活动": (
                "当前无前台 LearningActivity；"
                f"{activity_type}:{activity_id} 的 ledger 终态为 `{state}`。"
            ),
            "精确停顿点": (
                f"{activity_type}:{activity_id} 的关闭正文、授权与下一活动快照已写入 ledger；"
                f"{body_text}"
            ),
            "活动结论": (
                f"{activity_type}:{activity_id} 已记录为 `{state}`；"
                "完整结论与证据边界以 activity_ledger.md 的 CLR 为准。"
            ),
        }
        if activity_type == "lesson":
            terminal_summary["Lesson 上下文"] = (
                "无；当前处于活动之间，尚未创建或激活下一 Lesson。"
            )
        for label, summary in terminal_summary.items():
            pattern = re.compile(
                rf"(?ms)^-\s+\*\*{re.escape(label)}\*\*[：:].*?"
                r"(?=^-\s+\*\*|^##\s|\Z)"
            )
            rendered = f"- **{label}**：{summary}\n"
            if pattern.search(body):
                body = pattern.sub(rendered, body, count=1)
    return rebuild_frontmatter(meta, order) + body


def include_generated_state(
    root: Path,
    files: dict[str, str],
) -> dict[str, str]:
    """Project state-refresh outputs from the candidate progress atomically.

    Close planning remains read-only: ``planned_updates`` consumes in-memory
    overrides and returns the exact generated-cache bytes that would otherwise
    drift after the ledger/progress transaction.
    """
    generated_carriers = (
        root / "main/00_core/t2ag_memory.md",
        root / "main/10_student/profile/learning_path.md",
        root / "main/30_group",
    )
    if not any(path.exists() for path in generated_carriers):
        return dict(files)
    overrides = {root / rel: content for rel, content in files.items()}
    try:
        updates = state_refresh.planned_updates(root=root, overrides=overrides)
    except ValueError as exc:
        raise CloseError(f"cannot project generated state: {exc}") from exc
    enriched = dict(files)
    for path, content in updates:
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise CloseError(f"generated state escaped root: {path}") from exc
        current = overrides.get(path)
        if current is None:
            current = path.read_text(encoding="utf-8-sig")
        if content != current:
            enriched[rel] = content
    return enriched


def build_plan_core(
    *,
    root: Path,
    mode: str,
    course_id: str,
    activity_type: str,
    activity_id: str,
    files: dict[str, str],
    details: dict[str, Any],
    transaction_id: str | None = None,
) -> dict[str, Any]:
    expected_head = {rel: sha256_file(root / rel) for rel in files}
    return {
        "schema": "t2ag.activity_close.plan.v1",
        "campaign_id": CAMPAIGN_ID,
        "mode": mode,
        "plan_id": f"CLOSEPLAN-{uuid.uuid4().hex}",
        "transaction_id": transaction_id or f"CLOSE022-{uuid.uuid4().hex}",
        "recorded_at": now_tz(),
        "course_id": course_id,
        "activity_type": activity_type,
        "activity_id": activity_id,
        "expected_head": expected_head,
        "files": files,
        "post_sha256": {rel: sha256_text(content) for rel, content in files.items()},
        "details": details,
    }


def write_plan(path: Path, core: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        raise CloseError(f"immutable close plan already exists: {path}")
    payload_sha = sha256_text(canonical_json(core))
    durable = {**core, "payload_sha256": payload_sha}
    raw = (canonical_json(durable) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "plan_file": str(path.resolve()),
        "payload_sha256": payload_sha,
        "file_sha256": sha256_bytes(raw),
        "plan_id": core["plan_id"],
        "transaction_id": core["transaction_id"],
        "details": core["details"],
    }


def load_plan(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    plan = json.loads(raw.decode("utf-8"))
    if plan.get("schema") != "t2ag.activity_close.plan.v1":
        raise CloseError("wrong close plan schema")
    core = {key: value for key, value in plan.items() if key != "payload_sha256"}
    if plan.get("payload_sha256") != sha256_text(canonical_json(core)):
        raise CloseError("close plan payload SHA mismatch")
    for rel, content in (plan.get("files") or {}).items():
        if Path(rel).is_absolute() or ".." in Path(rel).parts or "\\" in rel:
            raise CloseError(f"unsafe close plan path: {rel}")
        want = plan["post_sha256"].get(rel)
        if want != sha256_text(content):
            raise CloseError(
                f"close plan content hash mismatch: {rel}"
                + text_line_ending_drift(content, want or "")
            )
    return plan, sha256_bytes(raw)


def materialize_pending_plan(
    root: Path,
    plan_path: Path,
    *,
    course_id: str,
    activity_type: str,
    activity_id: str,
    prefs: dict[str, str],
    knowledge: list[dict[str, str]],
    blockers: list[str],
    evidence_refs: list[str],
    student_feedback_ref: str,
    content_sections: dict[str, Any] | None = None,
    scope_change: dict[str, Any] | None = None,
    scope_change_confirmed: bool = False,
) -> dict[str, Any]:
    ledger_rel = f"main/40_course/{course_id}/activity_ledger.md"
    progress_rel = f"main/40_course/{course_id}/progress.md"
    ledger_text = (root / ledger_rel).read_text(encoding="utf-8")
    progress_text = (root / progress_rel).read_text(encoding="utf-8")
    doc = ledger.parse_ledger_text(ledger_text)
    errors = doc.validate()
    if errors:
        raise CloseError("source ledger invalid: " + "; ".join(errors))
    key = f"{activity_type}:{activity_id}"
    index = doc.rebuild_index()
    if key not in index or index[key].state != "ongoing":
        raise CloseError(f"pending requires ongoing activity: {key}")
    pending_id = next_numeric_id(
        [str(event.get("event_id") or "") for event in doc.events], "ALE", 6
    )
    preference_context = load_preference_context(root, course_id, prefs)
    body = build_close_body(
        activity_type=activity_type,
        activity_id=activity_id,
        prefs=preference_context["resolved"],
        knowledge=knowledge,
        blockers=blockers,
        evidence_refs=evidence_refs,
        student_feedback_ref=student_feedback_ref,
        content_sections=content_sections,
        scope_change=scope_change,
        scope_change_confirmed=scope_change_confirmed,
    )
    recorded_at = now_tz()
    transaction_id = f"CLOSE022-{uuid.uuid4().hex}"
    event = render_event(
        {
            "event_id": pending_id,
            "event_kind": "transition",
            "course_id": course_id,
            "activity_type": activity_type,
            "activity_id": activity_id,
            "from_state": "ongoing",
            "to_state": "pending_close",
            "occurred_at": recorded_at,
            "recorded_at": recorded_at,
            "triggered_by": "activity_close_tool",
            "trigger": "activity_close_pending",
            "transaction_id": transaction_id,
            "evidence_refs": evidence_refs,
            "pending_body_sha256": body["body_sha256"],
            "pending_body_b64": b64_json(body),
            "preferences_snapshot_b64": b64_json(body["preferences_snapshot"]),
        }
    )
    candidate_ledger = append_section_record(
        ledger_text, "Activity lifecycle events", event
    )
    candidate_ledger = refresh_ledger_views(candidate_ledger, recorded_at)
    candidate_doc = ledger.parse_ledger_text(candidate_ledger)
    next_action = ledger.resolve_next_action(
        current_activity_type=activity_type,
        current_activity_id=activity_id,
        current_state="pending_close",
        index=candidate_doc.rebuild_index(),
    )
    candidate_progress = update_progress(
        progress_text,
        activity_type=activity_type,
        activity_id=activity_id,
        state="pending_close",
        next_action=next_action,
    )
    candidate_files = {
        ledger_rel: candidate_ledger,
        progress_rel: candidate_progress,
    }
    profile_rel = "main/10_student/profile/profile.md"
    profile_path = root / profile_rel
    if profile_path.is_file() and preference_context["first_prompt_required"]:
        candidate_files[profile_rel] = mark_first_close_prompt(
            profile_path.read_text(encoding="utf-8-sig"),
            recorded_at=recorded_at,
        )
    core = build_plan_core(
        root=root,
        mode="pending",
        course_id=course_id,
        activity_type=activity_type,
        activity_id=activity_id,
        transaction_id=transaction_id,
        files=include_generated_state(
            root,
            candidate_files,
        ),
        details={
            "pending_event_id": pending_id,
            "body": body,
            "body_sha256": body["body_sha256"],
            "decision_recommendation": deterministic_decision(body),
            "preference_resolution": preference_context,
        },
    )
    return write_plan(plan_path, core)


def pending_event(doc: ledger.LedgerDocument, event_id: str) -> dict[str, Any]:
    matches = [event for event in doc.events if event.get("event_id") == event_id]
    if len(matches) != 1:
        raise CloseError(f"pending event must resolve exactly once: {event_id}")
    event = matches[0]
    if event.get("to_state") != "pending_close":
        raise CloseError(f"event is not pending_close: {event_id}")
    return event


def decode_body(event: dict[str, Any]) -> dict[str, Any]:
    try:
        body = json.loads(base64.b64decode(str(event["pending_body_b64"])).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CloseError("pending body is not decodable") from exc
    body_sha = body.pop("body_sha256", None)
    recomputed = sha256_text(canonical_json(body))
    body["body_sha256"] = body_sha
    if body_sha != recomputed or event.get("pending_body_sha256") != body_sha:
        raise CloseError("pending body SHA mismatch")
    return body


def materialize_decision_plan(
    root: Path,
    plan_path: Path,
    *,
    course_id: str,
    activity_type: str,
    activity_id: str,
    pending_event_id: str,
    body_sha256: str,
    decision: str,
    authorization_source_sha256: str,
    delegated_quote: str,
    decision_actor: str | None = None,
    authorization_mode: str | None = None,
    strict_confirmation_text: str | None = None,
    presented_retrospective_sha256: str | None = None,
    revision_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if decision not in {*TERMINAL_DECISIONS, "refuse", "revise"}:
        raise CloseError(f"unsupported decision: {decision}")
    if decision_actor is None or authorization_mode is None:
        raise CloseError("decision actor and authorization mode must be explicit")
    if (decision_actor, authorization_mode) not in PRODUCTION_DECISION_AUTHORITIES:
        raise CloseError("terminal lifecycle decisions require user + direct_user")
    if not re.fullmatch(r"[0-9a-f]{64}", authorization_source_sha256 or ""):
        raise CloseError("direct user authorization source SHA missing")
    if not delegated_quote:
        raise CloseError("direct user authorization quote missing")
    ledger_rel = f"main/40_course/{course_id}/activity_ledger.md"
    progress_rel = f"main/40_course/{course_id}/progress.md"
    ledger_text = (root / ledger_rel).read_text(encoding="utf-8")
    progress_text = (root / progress_rel).read_text(encoding="utf-8")
    doc = ledger.parse_ledger_text(ledger_text)
    event = pending_event(doc, pending_event_id)
    body = decode_body(event)
    if body["body_sha256"] != body_sha256:
        raise CloseError("decision body SHA does not match pending")
    key = f"{activity_type}:{activity_id}"
    index = doc.rebuild_index()
    if key not in index or index[key].state != "pending_close":
        raise CloseError("decision requires current pending_close")
    expected = deterministic_decision(body)
    if decision in TERMINAL_DECISIONS and decision != expected:
        raise CloseError(f"decision violates deterministic policy: expected={expected}")
    recorded_at = now_tz()
    transaction_id = f"CLOSE022-{uuid.uuid4().hex}"
    event_id = next_numeric_id(
        [str(item.get("event_id") or "") for item in doc.events], "ALE", 6
    )
    close_record_fields: dict[str, Any] | None = None
    confirmation_mode: str | None = None
    if decision == "revise":
        if not revision_patch:
            raise CloseError("revision requires substantive revision_patch")
        if body.get("schema") == CLOSE_BODY_SCHEMA:
            content_sections = {
                "close_scope": body.get("close_scope"),
                "evidence_collection": body.get("evidence_collection"),
                "teaching_retrospective": body.get("teaching_retrospective"),
            }
        else:
            # v1 pending bodies remain readable and can be revised into v2.
            content_sections = dict(body.get("fixed") or {})
            content_sections.update(body.get("optional") or {})
        content_sections.update(revision_patch.get("content_sections") or {})
        new_body = build_close_body(
            activity_type=activity_type,
            activity_id=activity_id,
            prefs=dict(body.get("preferences_snapshot") or {}),
            knowledge=list(revision_patch.get("knowledge", body.get("knowledge") or [])),
            blockers=list(revision_patch.get("blockers", body.get("completion_blockers") or [])),
            evidence_refs=list(revision_patch.get("evidence_refs", body.get("evidence_refs") or [])),
            student_feedback_ref=str(
                revision_patch.get("student_feedback_ref", body.get("student_feedback_ref") or "")
            ),
            content_sections=content_sections,
            scope_change=revision_patch.get("scope_change", body.get("scope_change")),
            scope_change_confirmed=bool(
                revision_patch.get(
                    "scope_change_confirmed", body.get("scope_change_confirmed")
                )
            ),
        )
        original_compare = dict(body)
        original_compare.pop("body_sha256", None)
        revised_compare = dict(new_body)
        revised_compare.pop("body_sha256", None)
        if original_compare == revised_compare:
            raise CloseError("revision_patch does not change pending body")
        new_body.pop("body_sha256", None)
        new_body["revision_of"] = pending_event_id
        new_body["body_sha256"] = sha256_text(canonical_json(new_body))
        transition = render_event(
            {
                "event_id": event_id,
                "event_kind": "pending_revision",
                "course_id": course_id,
                "activity_type": activity_type,
                "activity_id": activity_id,
                "from_state": "pending_close",
                "to_state": "pending_close",
                "occurred_at": recorded_at,
                "recorded_at": recorded_at,
                "triggered_by": decision_actor,
                "trigger": "activity_close_revision",
                "transaction_id": transaction_id,
                "evidence_refs": body.get("evidence_refs") or [],
                "revises_event_id": pending_event_id,
                "pending_body_sha256": new_body["body_sha256"],
                "pending_body_b64": b64_json(new_body),
            }
        )
        terminal_state = "pending_close"
        chosen_pending = event_id
        chosen_body = new_body
    elif decision == "refuse":
        transition = render_event(
            {
                "event_id": event_id,
                "event_kind": "transition",
                "course_id": course_id,
                "activity_type": activity_type,
                "activity_id": activity_id,
                "from_state": "pending_close",
                "to_state": "ongoing",
                "occurred_at": recorded_at,
                "recorded_at": recorded_at,
                "triggered_by": decision_actor,
                "trigger": "activity_close_refused",
                "transaction_id": transaction_id,
                "evidence_refs": body.get("evidence_refs") or [],
                "refused_pending_event_id": pending_event_id,
            }
        )
        terminal_state = "ongoing"
        chosen_pending = pending_event_id
        chosen_body = body
    else:
        terminal_state = TERMINAL_DECISIONS[decision]
        expected_retrospective_sha = learner_retrospective_sha256(body)
        if presented_retrospective_sha256 != expected_retrospective_sha:
            raise CloseError(
                "terminal decision requires the complete learner retrospective "
                "to be presented in dialogue first"
            )
        if strict_confirmation_text is None:
            raise CloseError("direct user decision requires confirmation text")
        strict_text = strict_confirmation_text
        parsed = parse_bound_close_confirmation(
            strict_text,
            pending_event_id=pending_event_id,
            body_sha256=body_sha256,
            result=terminal_state,
        )
        if (
            parsed["pending_event_id"] != pending_event_id
            or parsed["body_sha256"] != body_sha256
            or parsed["result"] != terminal_state
        ):
            raise CloseError("strict confirmation binding mismatch")
        if delegated_quote != strict_text:
            raise CloseError("authorization quote must equal direct confirmation text")
        confirmation_mode = parsed["confirmation_mode"]
        transition = render_event(
            {
                "event_id": event_id,
                "event_kind": "transition",
                "course_id": course_id,
                "activity_type": activity_type,
                "activity_id": activity_id,
                "from_state": "pending_close",
                "to_state": terminal_state,
                "occurred_at": recorded_at,
                "recorded_at": recorded_at,
                "triggered_by": decision_actor,
                "trigger": "activity_close_confirmed",
                "transaction_id": transaction_id,
                "evidence_refs": body.get("evidence_refs") or [],
                "confirmed_pending_event_id": pending_event_id,
            }
        )
        close_id = next_numeric_id(
            [str(item.get("close_id") or "") for item in doc.closes], "CLR", 4
        )
        close_record_fields = {
                "close_id": close_id,
                "course_id": course_id,
                "activity_type": activity_type,
                "activity_id": activity_id,
                "pending_event_id": pending_event_id,
                "terminal_event_id": event_id,
                "body_sha256": body_sha256,
                "body_json_b64": b64_json(body),
                "result": terminal_state,
                "strict_confirmation_sha256": sha256_text(strict_text),
                "confirmation_mode": confirmation_mode,
                "strict_confirmation_b64": base64.b64encode(
                    strict_text.encode("utf-8")
                ).decode("ascii"),
                "decision_actor": decision_actor,
                "authorization_mode": authorization_mode,
                "authorization_procedure_status": "valid_direct_user",
                "authorization_source_sha256": authorization_source_sha256,
                "authorization_quote_b64": base64.b64encode(
                    delegated_quote.encode("utf-8")
                ).decode("ascii"),
                "authorization_quote_sha256": sha256_text(delegated_quote),
                "retrospective_presentation_sha256": expected_retrospective_sha,
                "recorded_at": recorded_at,
                "transaction_id": transaction_id,
                "evidence_refs": body.get("evidence_refs") or [],
            }
        chosen_pending = pending_event_id
        chosen_body = body

    candidate_ledger = append_section_record(
        ledger_text, "Activity lifecycle events", transition
    )
    candidate_ledger = refresh_ledger_views(candidate_ledger, recorded_at)
    candidate_doc = ledger.parse_ledger_text(candidate_ledger)
    candidate_index = candidate_doc.rebuild_index()
    next_action = ledger.resolve_next_action(
        current_activity_type=(
            "none" if terminal_state in {"completed", "closed_incomplete"} else activity_type
        ),
        current_activity_id=(
            "none" if terminal_state in {"completed", "closed_incomplete"} else activity_id
        ),
        current_state=(
            None if terminal_state in {"completed", "closed_incomplete"} else terminal_state
        ),
        index=candidate_index,
    )
    if close_record_fields is not None:
        next_snapshot = {
            "current_activity": "none",
            "current_activity_id": "none",
            "activity_position": "between_activities",
            **next_action,
        }
        close_record_fields["next_activity_at_close_b64"] = b64_json(next_snapshot)
        close_record_fields["next_activity_at_close_sha256"] = sha256_text(
            canonical_json(next_snapshot)
        )
        candidate_ledger = append_section_record(
            candidate_ledger,
            "Close records",
            render_close(close_record_fields),
        )
        candidate_ledger = refresh_ledger_views(candidate_ledger, recorded_at)
    candidate_progress = update_progress(
        progress_text,
        activity_type=activity_type,
        activity_id=activity_id,
        state=terminal_state,
        next_action=next_action,
    )
    core = build_plan_core(
        root=root,
        mode="decision",
        course_id=course_id,
        activity_type=activity_type,
        activity_id=activity_id,
        transaction_id=transaction_id,
        files=include_generated_state(
            root,
            {ledger_rel: candidate_ledger, progress_rel: candidate_progress},
        ),
        details={
            "pending_event_id": chosen_pending,
            "body_sha256": chosen_body["body_sha256"],
            "decision": decision,
            "result": terminal_state,
            "deterministic_policy_result": expected,
            "decision_actor": decision_actor,
            "authorization_mode": authorization_mode,
            "authorization_procedure_status": "valid_direct_user",
            "authorization_source_sha256": authorization_source_sha256,
            "authorization_quote_sha256": sha256_text(delegated_quote),
            "strict_confirmation_sha256": (
                sha256_text(strict_text) if decision in TERMINAL_DECISIONS else None
            ),
            "confirmation_mode": confirmation_mode,
            "retrospective_presentation_sha256": (
                learner_retrospective_sha256(chosen_body)
                if decision in TERMINAL_DECISIONS
                else None
            ),
        },
    )
    return write_plan(plan_path, core)


def close_history(doc: ledger.LedgerDocument) -> list[dict[str, Any]]:
    reopened = {
        str(event.get("reopens_close_id"))
        for event in doc.events
        if event.get("reopens_close_id")
    }
    return [
        {
            **close,
            "historical": str(close.get("close_id")) in reopened,
            "reopened": str(close.get("close_id")) in reopened,
        }
        for close in doc.closes
    ]


def materialize_reopen_plan(
    root: Path,
    plan_path: Path,
    *,
    course_id: str,
    activity_type: str,
    activity_id: str,
) -> dict[str, Any]:
    ledger_rel = f"main/40_course/{course_id}/activity_ledger.md"
    progress_rel = f"main/40_course/{course_id}/progress.md"
    ledger_text = (root / ledger_rel).read_text(encoding="utf-8")
    progress_text = (root / progress_rel).read_text(encoding="utf-8")
    doc = ledger.parse_ledger_text(ledger_text)
    key = f"{activity_type}:{activity_id}"
    index = doc.rebuild_index()
    if key not in index or index[key].state not in {
        "completed",
        "closed_incomplete",
    }:
        raise CloseError("reopen requires terminal activity")
    matching_closes = [
        close
        for close in doc.closes
        if close.get("activity_type") == activity_type
        and close.get("activity_id") == activity_id
    ]
    if not matching_closes:
        raise CloseError("reopen requires preserved CLR")
    close_id = str(matching_closes[-1].get("close_id") or "")
    recorded_at = now_tz()
    transaction_id = f"CLOSE022-{uuid.uuid4().hex}"
    event_id = next_numeric_id(
        [str(item.get("event_id") or "") for item in doc.events], "ALE", 6
    )
    event = render_event(
        {
            "event_id": event_id,
            "event_kind": "transition",
            "course_id": course_id,
            "activity_type": activity_type,
            "activity_id": activity_id,
            "from_state": index[key].state,
            "to_state": "ongoing",
            "occurred_at": recorded_at,
            "recorded_at": recorded_at,
            "triggered_by": "activity_close_tool",
            "trigger": "activity_reopened",
            "transaction_id": transaction_id,
            "evidence_refs": [close_id],
            "reopens_close_id": close_id,
        }
    )
    candidate_ledger = append_section_record(
        ledger_text, "Activity lifecycle events", event
    )
    candidate_ledger = refresh_ledger_views(candidate_ledger, recorded_at)
    candidate_doc = ledger.parse_ledger_text(candidate_ledger)
    next_action = ledger.resolve_next_action(
        current_activity_type=activity_type,
        current_activity_id=activity_id,
        current_state="ongoing",
        index=candidate_doc.rebuild_index(),
    )
    candidate_progress = update_progress(
        progress_text,
        activity_type=activity_type,
        activity_id=activity_id,
        state="ongoing",
        next_action=next_action,
    )
    core = build_plan_core(
        root=root,
        mode="reopen",
        course_id=course_id,
        activity_type=activity_type,
        activity_id=activity_id,
        transaction_id=transaction_id,
        files=include_generated_state(
            root,
            {ledger_rel: candidate_ledger, progress_rel: candidate_progress},
        ),
        details={"reopens_close_id": close_id, "event_id": event_id},
    )
    return write_plan(plan_path, core)


def validate_authorization(
    root: Path,
    plan: dict[str, Any],
    *,
    auth_path: Path,
    expect_auth_sha: str,
) -> dict[str, Any]:
    raw = auth_path.read_bytes()
    got = sha256_bytes(raw)
    if got != expect_auth_sha:
        raise CloseError(
            "close authorization file SHA mismatch"
            + line_ending_drift(raw, expect_auth_sha)
        )
    auth = json.loads(raw.decode("utf-8"))
    required = {
        "campaign_id": CAMPAIGN_ID,
        "plan_id": plan["plan_id"],
        "transaction_id": plan["transaction_id"],
        "payload_sha256": plan["payload_sha256"],
    }
    for key, value in required.items():
        if auth.get(key) != value:
            raise CloseError(f"close authorization binding mismatch: {key}")
    expected_phase = "F0_PENDING" if plan["mode"] == "pending" else "F_AUTHORIZED"
    if auth.get("phase") != expected_phase:
        raise CloseError(f"close authorization phase must be {expected_phase}")
    if auth.get("authorization_mode") not in {"direct_user", "test", "shadow"}:
        raise CloseError("unsupported close authorization mode")
    if root.resolve() == INSTANCE_ROOT:
        if not auth.get("authorization_source_sha256"):
            raise CloseError("production close authorization source missing")
        if auth.get("authorization_mode") not in PRODUCTION_APPLY_AUTHORIZATION_MODES:
            raise CloseError("production close requires direct_user authority")
        if plan["mode"] != "pending":
            if auth.get("decision_actor") != "user":
                raise CloseError("production lifecycle apply requires user decision actor")
            if auth.get("authorization_procedure_status") != "valid_direct_user":
                raise CloseError("production lifecycle apply lacks valid direct-user procedure")
        if plan["mode"] == "decision":
            for key in (
                "authorization_source_sha256",
                "authorization_procedure_status",
                "strict_confirmation_sha256",
                "authorization_quote_sha256",
            ):
                if auth.get(key) != plan["details"].get(key):
                    raise CloseError(f"direct close authorization mismatch: {key}")
    elif os.environ.get("T2AG_022_CLOSE_TEST") != "1":
        raise CloseError("non-production close apply requires test/shadow guard")
    return auth


def run_postchecks(root: Path, plan: dict[str, Any]) -> None:
    ledger_path = root / f"main/40_course/{plan['course_id']}/activity_ledger.md"
    doc = ledger.load_ledger(ledger_path)
    errors = doc.validate()
    if errors:
        raise CloseError("post-close ledger invalid: " + "; ".join(errors))
    for rel, want in plan["post_sha256"].items():
        got = sha256_file(root / rel)
        if got != want:
            target = root / rel
            raw = target.read_bytes() if target.is_file() else None
            raise CloseError(
                f"post-close hash mismatch: {rel}"
                + line_ending_drift(raw, want)
            )
    if root.resolve() == INSTANCE_ROOT:
        commands = [
            [sys.executable, "-B", str(root / "main/70_tools/t2ag_doctor.py")],
            [
                sys.executable,
                "-B",
                str(root / "main/70_tools/t2ag_state_refresh.py"),
                "--check",
            ],
        ]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["T2AG_022_EXPECT_TRANSACTION_ID"] = plan["transaction_id"]
        for command in commands:
            run = subprocess.run(
                command,
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )
            if run.returncode != 0:
                raise CloseError(
                    f"close consumer failed: {Path(command[2]).name}: "
                    + (run.stdout + run.stderr)[-6000:]
                )


def apply_close_plan(
    root: Path,
    plan_path: Path,
    *,
    expect_payload_sha: str,
    expect_file_sha: str,
    authorization_receipt: Path,
    expect_authorization_sha: str,
) -> dict[str, Any]:
    plan, file_sha = load_plan(plan_path)
    if file_sha != expect_file_sha or plan["payload_sha256"] != expect_payload_sha:
        raise CloseError(
            "close plan hash binding mismatch"
            + line_ending_drift(plan_path.read_bytes(), expect_file_sha)
        )
    validate_authorization(
        root,
        plan,
        auth_path=authorization_receipt,
        expect_auth_sha=expect_authorization_sha,
    )
    for rel, want in plan["expected_head"].items():
        if sha256_file(root / rel) != want:
            # A committed retry is allowed only when every post hash matches.
            if all(
                sha256_file(root / post_rel) == post_sha
                for post_rel, post_sha in plan["post_sha256"].items()
            ):
                return {
                    "status": "already_committed_verified",
                    "transaction_id": plan["transaction_id"],
                }
            raise CloseError(f"close plan baseline drift: {rel}")
    engine = txn.ActivityTransaction(root)
    transaction_plan = txn.TransactionPlan(
        scope_id=f"course:{plan['course_id']}",
        transaction_id=plan["transaction_id"],
        ops=[
            txn.FileOp(rel, "write", content=content.encode("utf-8"))
            for rel, content in sorted(plan["files"].items())
        ],
        expected_head=plan["expected_head"],
        metadata={
            "campaign_id": CAMPAIGN_ID,
            "plan_id": plan["plan_id"],
            "payload_sha256": plan["payload_sha256"],
            "authorization_sha256": expect_authorization_sha,
        },
    )
    engine.stage(transaction_plan)
    try:
        installed = engine.apply(plan["transaction_id"], defer_commit=True)
        if installed["status"] == "installed_pending_postcheck":
            run_postchecks(root, plan)
            engine.mark_postcheck_passed(plan["transaction_id"])
            engine.commit(plan["transaction_id"])
        elif installed["status"] == "postcheck_passed":
            run_postchecks(root, plan)
            engine.commit(plan["transaction_id"])
        elif installed["status"] != "already_committed_verified":
            raise CloseError(f"unexpected close transaction status: {installed['status']}")
        run_postchecks(root, plan)
        return {
            "status": "committed",
            "transaction_id": plan["transaction_id"],
            "mode": plan["mode"],
            "details": plan["details"],
        }
    except Exception:
        engine.rollback(plan["transaction_id"])
        raise


def load_json_file(path: Path | None, default: Any) -> Any:
    if path is None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=INSTANCE_ROOT)
    parser.add_argument("--course-id", default="MATH1607H")
    parser.add_argument("--activity-type", choices=["lesson", "exercise"], default="exercise")
    parser.add_argument("--activity-id", default="exercise01")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan-pending", action="store_true")
    action.add_argument("--plan-decision", action="store_true")
    action.add_argument("--plan-reopen", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--parse-confirm", default=None)
    parser.add_argument("--plan-out", type=Path)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--prefs-json", type=Path)
    parser.add_argument("--knowledge-json", type=Path)
    parser.add_argument("--blocker", action="append", default=[])
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--student-feedback-ref", default="")
    parser.add_argument("--content-json", type=Path)
    parser.add_argument("--scope-change-json", type=Path)
    parser.add_argument("--confirm-scope-change", action="store_true")
    parser.add_argument("--pending-event-id")
    parser.add_argument("--body-sha256")
    parser.add_argument(
        "--decision",
        choices=["confirm_completed", "confirm_closed_incomplete", "refuse", "revise"],
    )
    parser.add_argument("--authorization-source-sha256", default="")
    parser.add_argument("--authorization-quote", default="")
    parser.add_argument(
        "--decision-actor",
        choices=["user"],
        default=None,
    )
    parser.add_argument(
        "--authorization-mode",
        choices=["direct_user"],
        default=None,
    )
    parser.add_argument("--strict-confirmation-text")
    parser.add_argument("--presented-retrospective-sha256")
    parser.add_argument("--revision-json", type=Path)
    parser.add_argument("--expect-payload-sha")
    parser.add_argument("--expect-file-sha")
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--expect-authorization-sha")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.parse_confirm is not None:
            result = parse_strict_confirmation(args.parse_confirm)
        elif args.plan_pending:
            if not args.plan_out:
                raise CloseError("--plan-out required")
            result = materialize_pending_plan(
                root,
                args.plan_out.resolve(),
                course_id=args.course_id,
                activity_type=args.activity_type,
                activity_id=args.activity_id,
                prefs=load_json_file(args.prefs_json, {}),
                knowledge=load_json_file(args.knowledge_json, []),
                blockers=args.blocker,
                evidence_refs=args.evidence_ref,
                student_feedback_ref=args.student_feedback_ref,
                content_sections=load_json_file(args.content_json, {}),
                scope_change=load_json_file(args.scope_change_json, None),
                scope_change_confirmed=args.confirm_scope_change,
            )
        elif args.plan_decision:
            if not all(
                [
                    args.plan_out,
                    args.pending_event_id,
                    args.body_sha256,
                    args.decision,
                    args.authorization_source_sha256,
                    args.authorization_quote,
                    args.decision_actor,
                    args.authorization_mode,
                ]
            ):
                raise CloseError("decision plan requires pending/body/decision/authorization fields")
            result = materialize_decision_plan(
                root,
                args.plan_out.resolve(),
                course_id=args.course_id,
                activity_type=args.activity_type,
                activity_id=args.activity_id,
                pending_event_id=args.pending_event_id,
                body_sha256=args.body_sha256,
                decision=args.decision,
                authorization_source_sha256=args.authorization_source_sha256,
                delegated_quote=args.authorization_quote,
                decision_actor=args.decision_actor,
                authorization_mode=args.authorization_mode,
                strict_confirmation_text=args.strict_confirmation_text,
                presented_retrospective_sha256=args.presented_retrospective_sha256,
                revision_patch=load_json_file(args.revision_json, None),
            )
        elif args.plan_reopen:
            if not args.plan_out:
                raise CloseError("--plan-out required")
            result = materialize_reopen_plan(
                root,
                args.plan_out.resolve(),
                course_id=args.course_id,
                activity_type=args.activity_type,
                activity_id=args.activity_id,
            )
        else:
            if not all(
                [
                    args.plan_file,
                    args.expect_payload_sha,
                    args.expect_file_sha,
                    args.authorization_receipt,
                    args.expect_authorization_sha,
                ]
            ):
                raise CloseError("apply requires exact plan and authorization hashes")
            result = apply_close_plan(
                root,
                args.plan_file.resolve(),
                expect_payload_sha=args.expect_payload_sha,
                expect_file_sha=args.expect_file_sha,
                authorization_receipt=args.authorization_receipt.resolve(),
                expect_authorization_sha=args.expect_authorization_sha,
            )
    except Exception as exc:  # noqa: BLE001
        print(canonical_json({"ok": False, "error": str(exc)}))
        return 1
    print(canonical_json({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
