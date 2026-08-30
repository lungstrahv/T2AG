#!/usr/bin/env python3
"""Canonical learner-surface renderer for deterministic journey results."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class LearnerJourneyError(ValueError):
    """Structured results that cannot be rendered safely."""


SCENARIO_COPY: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "install_ready": (
        "安装准备完成",
        "学习工作区已经可以开始使用。",
        ("进入首次设置。",),
    ),
    "project_ready": (
        "项目学习入口已准备好",
        "下一步会从你确认的项目目标开始，不会替你补造个人事实。",
        ("确认项目目标与当前基础。", "进入第一项已确认的工作。"),
    ),
    "continue_ready": (
        "已接回当前进度",
        "本轮明确的继续意图已被消费，不会重复询问一般继续授权。",
        ("进入权威停点后的下一项动作。",),
    ),
    "route_conflict": (
        "发现进度冲突，尚未继续",
        "继续前需要先选择采用哪条恢复路线；当前学习状态没有被改写。",
        ("查看两条路线各自的影响。", "选择要保留的恢复路线。"),
    ),
    "activity_close_ready": (
        "结课复盘已准备好",
        "确认前只展示复盘、结果含义与可选动作；内部绑定信息仍留在操作面。",
        ("阅读复盘。", "确认结课、提出修订，或继续补齐。"),
    ),
    "group_preflight_blocked": (
        "建组尚未激活",
        "前置核对发现计划与碑账不一致；系统已在写入 active 状态前停止。",
        ("先对齐里程碑计划与变更记录。", "修正后重新运行激活前核对。"),
    ),
}

LEARNER_KNOWLEDGE_LABELS = {
    "independent_confirmed": "可以独立完成",
    "assisted_confirmed": "在帮助下完成",
    "partial": "部分掌握，仍需补齐",
    "unverified": "尚未验证",
}

RETROSPECTIVE_SECTION_LABELS = {
    "actual_teaching_process": "实际教学过程",
    "content_completion": "课程内容完成情况",
    "knowledge_absorption": "知识吸收",
    "course_content_feedback": "学生课程内容反馈",
    "teacher_reflection": "教师教学反思",
    "learning_transition": "后续学习衔接",
    "actual_exercise_process": "实际做题过程",
    "question_coverage": "题目覆盖轧账（对 source_order）",
    "mastery_ledger": "掌握分账",
    "byproduct_audit": "副产物审计",
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
    "attempted_questions": "实际做了哪些题",
    "sequence_vs_source_order": "教学重排与题序对照",
    "hint_gate_usage": "提示闸门使用",
    "completed_questions": "闭合题目",
    "partial_questions": "部分完成题目",
    "untouched_questions": "未触达题目",
    "independent_correct": "独立正确",
    "assisted_correct": "提示后正确",
    "contaminated_or_not_counted": "污染或不计（越级提示/当堂理解）",
    "mistake_bank_updates": "错题库更新",
    "open_question_chains": "未闭讨论链",
    "retest_hooks": "复测钩子",
    "thought_routing": "想法路由",
    "attempt_review_completeness": "Attempt/Review 完备性",
    "return_to_lesson_entry": "返回 Lesson 入口",
}


def _render_scenario_outcome(result: Mapping[str, Any]) -> str:
    code = str(result.get("outcome_code") or "")
    try:
        outcome, impact, actions = SCENARIO_COPY[code]
    except KeyError:
        raise LearnerJourneyError(f"unsupported learner outcome: {code}") from None
    if len(actions) > 3:
        raise LearnerJourneyError("learner summary may expose at most three actions")
    lines = ["# 结果", "", outcome, "", "## 影响", "", impact, "", "## 下一步", ""]
    lines.extend(f"- {action}" for action in actions)
    return "\n".join(lines)


def _render_activity_close(result: Mapping[str, Any]) -> str:
    payload = result.get("payload")
    section_order = result.get("section_order")
    item_order = result.get("item_order")
    if not isinstance(payload, Mapping) or not isinstance(section_order, list):
        raise LearnerJourneyError("activity close result is incomplete")
    if not isinstance(item_order, Mapping):
        raise LearnerJourneyError("activity close item order is missing")
    lines = [
        "# 教学复盘",
        "",
        "## 结课范围",
        "",
        str((payload.get("close_scope") or {}).get("summary") or "未提供范围摘要"),
    ]
    visible = payload.get("learner_visible_retrospective") or {}
    for section_name in section_order:
        section = visible.get(section_name)
        if not isinstance(section, Mapping):
            continue
        lines.extend(["", f"## {RETROSPECTIVE_SECTION_LABELS[section_name]}", ""])
        for item_name in item_order.get(section_name, []):
            item = (section.get("items") or {}).get(item_name)
            if not isinstance(item, Mapping) or item.get("status") != "applicable":
                continue
            lines.append(f"- **{RETROSPECTIVE_ITEM_LABELS[item_name]}**：{item['summary']}")
    lines.extend(["", "## 掌握层级", ""])
    for item in payload.get("knowledge") or []:
        state = str(item.get("state") or "")
        lines.append(f"- {LEARNER_KNOWLEDGE_LABELS.get(state, '状态待核对')}：{item.get('topic')}")
    assessment = payload.get("completion_assessment") or {}
    reason = str(assessment.get("reason") or "未提供")
    for internal, learner_wording in (
        ("not_applicable", "不适用"),
        ("missing", "尚未检查"),
        ("completed", "完成状态"),
        ("blocker", "未完成项"),
    ):
        reason = reason.replace(internal, learner_wording)
    blockers = assessment.get("completion_blockers") or "无"
    if isinstance(blockers, list):
        blockers = [
            "范围变化尚未确认" if item == "unconfirmed_scope_change" else item
            for item in blockers
        ] or "无"
    if str(payload.get("recommendation") or "") == "completed":
        result_meaning = "现有证据支持完成本次活动；确认后，本活动进入已完成状态。"
        third_action = "暂不结课，继续学习或补充证据。"
        confirm_action = "确认按完成状态结束本次活动。"
    else:
        result_meaning = "当前仍有未完成内容；确认后，本活动会以未完成状态结束并保留缺口。"
        third_action = "继续补齐缺口，完成后再结课。"
        confirm_action = "确认以未完成状态结束本次活动。"
    lines.extend([
        "", "## 完成性判定", "", f"- 未完成项：{blockers}",
        f"- 范围变化：{assessment.get('scope_change') or '无'}", f"- 判定理由：{reason}",
        "", "## 结果含义", "", result_meaning, "", "## 你可以选择", "",
        f"1. {confirm_action}", "2. 指出需要修订的复盘内容。", f"3. {third_action}",
    ])
    return "\n".join(lines)


def render_learner_summary(
    structured_operator_result: Mapping[str, Any],
    scenario_context: Mapping[str, Any],
) -> str:
    """Render learner wording without consuming Operator messages or receipts."""
    if scenario_context.get("audience") != "learner":
        raise LearnerJourneyError("learner renderer requires audience=learner")
    result_type = structured_operator_result.get("result_type", "scenario_outcome")
    if result_type == "activity_close_retrospective":
        return _render_activity_close(structured_operator_result)
    if result_type == "scenario_outcome":
        return _render_scenario_outcome(structured_operator_result)
    raise LearnerJourneyError(f"unsupported structured result type: {result_type}")
