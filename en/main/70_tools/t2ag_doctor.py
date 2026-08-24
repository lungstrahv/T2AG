#!/usr/bin/env python3
"""Deterministic doctor for the T2AG 0.2.3 object model."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import hashlib
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import activity_close as activity_close_contract
import activity_ledger as activity_ledger_contract
import migrate_022_activity_close as migration_022_contract
import validation_control

from t2ag_activity import (
    ActivityContractError,
    ActivityRoute,
    ProgressSnapshot,
    TeacherContractError,
    frontmatter_text,
    resolve_activity,
    resolve_course_book_path,
    resolve_teacher_mapping,
    validate_progress_identity,
)
from contracts.reading_bridge_v1.validator import (
    ContractError,
    canonical_json_bytes,
    load_json_strict,
    semantic_sha256,
    validate_document,
)


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"
COURSE_SNAPSHOTS: dict[str, ProgressSnapshot] = {}
COURSE_ROUTES: dict[str, ActivityRoute] = {}


def detect_flavor() -> str:
    if ROOT.name == "t2ag-lite":
        return "lite"
    if ROOT.name == "t2ag-skeleton":
        return "skeleton"
    profile = MAIN / "10_student/profile/profile.md"
    readme = ROOT / "README.md"
    profile_text = (
        profile.read_text(encoding="utf-8-sig", errors="replace")
        if profile.is_file() else ""
    )
    readme_text = (
        readme.read_text(encoding="utf-8-sig", errors="replace")
        if readme.is_file() else ""
    )
    initialized = bool(re.search(
        r"^initialization_status:\s*initialized\s*$",
        profile_text,
        re.MULTILINE,
    ))
    if not initialized and "t2ag-skeleton" in readme_text:
        return "skeleton"
    return "main"


FLAVOR = detect_flavor()


def distribution_release_names(
    root: Path = ROOT,
    environ: dict[str, str] | None = None,
) -> tuple[str, ...]:
    """Select cross-release peers for a transaction-bound Doctor run.

    Lite is derived only after a clean candidate exists.  During the exact
    migration transaction Main may therefore be ahead of Lite, but never of
    Skeleton.  The exception is enabled only by the exact transaction ID and
    a matching on-disk transaction plan in an installed/checked/committed
    state.  Ordinary Doctor invocations continue to compare all releases.
    """
    env = os.environ if environ is None else environ
    expected = str(env.get("T2AG_022_EXPECT_TRANSACTION_ID") or "")
    all_releases = ("t2ag", "t2ag-skeleton", "t2ag-lite")
    if not re.fullmatch(
        r"(?:MIG022-[0-9a-f]{16}|CLOSE022-[0-9a-f]{32}|LIFECYCLE022-[0-9a-f]{32})",
        expected,
    ):
        return all_releases
    plan_path = root / ".activity_txn" / expected / "plan.json"
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return all_releases
    if (
        payload.get("transaction_id") == expected
        and payload.get("status")
        in {"installed_pending_postcheck", "postcheck_passed", "committed"}
    ):
        return ("t2ag", "t2ag-skeleton")
    return all_releases
EXPECTED_DOMAINS = {
    "00_core", "10_student", "20_teacher", "30_group", "40_course",
    "50_playbook", "60_journal", "70_tools", "80_interface",
}
BASE_VALIDATION_FILES = (
    "main/50_playbook/doctor_contracts.md",
    "main/50_playbook/test_strategy.md",
    "main/50_playbook/validation_flow.md",
    "main/70_tools/t2ag_doctor.py",
    "main/70_tools/answers.example.json",
    "main/70_tools/answers.schema.json",
    "main/70_tools/t2ag_test.py",
    "main/70_tools/sync_lite.py",
    "main/70_tools/test_dependencies.json",
    "main/70_tools/validation_control.py",
    "main/70_tools/validation_workflow.json",
    "main/70_tools/contract_test_support.py",
    "main/70_tools/migration_test_support.py",
    "main/70_tools/test_distribution_foundation.py",
    "main/70_tools/scenarios/__init__.py",
)
BASE_DOCTOR_PROFILE_MARKERS = (
    "def run_runtime_checks(",
    "def run_release_audit_checks(",
    'parser.add_argument("--check"',
    'parser.add_argument("--execute-plan"',
    'choices=("runtime", "release")',
    'default="runtime"',
)
SUPPORTED_DOCTOR_HANDLERS = {
    "check_structure", "check_version_and_profile", "check_version_bump_precondition",
    "check_skin_system",
    "check_authorization_governance", "discover_courses", "check_groups",
    "check_activity_ledgers", "check_engagements_and_activities",
    "check_question_banks", "check_knowledge_ledgers", "check_exam_banks",
    "check_project_verification",
    "check_exercises", "check_teacher_contract", "check_memory_pointers",
    "check_registry", "check_textbook_preparation", "check_canonical_teaching_carrier",
    "check_scope_page_cache",
    "check_checkpoint_block_routing", "check_gate_ledger",
    "check_recommendation_ledger", "check_gate_visibility",
    "check_problemlog_closure", "check_rule_enforcement_integrity",
    "check_external_source_backlink",
    "check_trading_boundary", "check_external_references",
    "check_legacy_references", "check_retired_instance_ids", "check_cloud_pause",
    "check_context_packet_contract", "check_test_management_contract",
    "check_decision_records",
    "check_course_activity_templates", "check_environment_assumptions",
    "check_memory_budget",
    "check_constitution_budget",
    "check_changelog_contract",
    "check_flow_and_guide", "check_handoff_contract",
    "check_cloud_contract", "check_derived_tools", "check_migration_evidence",
    "check_migration_021_evidence", "check_activity_migration_021_evidence",
    "check_reading_bridge_contract", "check_core_playbooks",
    "check_playbook_taxonomy", "check_playbook_taxonomy_parity",
    "check_playbook_usage", "check_domain_tier_reconciliation",
    "check_candidate_replay_contract", "check_tracked_environment", "check_dirty_tree",
    "check_skeleton_textbook", "check_distribution_parity", "check_constitution_parity",
    "check_cross_edition_parity",
    "check_skeleton_privacy", "check_release_package_surface",
    "check_release_candidate_binding",
    "check_decision_record_citations",
    "check_line_endings", "check_release_line_endings",
}
LEGACY_DOMAINS = {
    "10_case", "12_activity_records", "15_curricula", "20_groups",
    "25_general", "30_courses", "30_course_definitions", "35_course_runs",
    "40_field_practices", "skin",
}
LEGACY_REFERENCES = (
    "10_case/", "12_activity_records/", "15_curricula/", "20_groups/",
    "25_general/", "30_courses/", "30_course_definitions/",
    "35_course_runs/", "40_field_practices/", "main/skin/",
    "assets/fable_snail.png", "course_status.md", "field_practice.md",
    "student_info.md", "course_info.md", "teacher_overlay.md",
    "course_definition.md", "progress_nodes.md", "preplans/",
)
ALLOWED_QUESTION_STATES = {"open", "answered", "closed"}
ALLOWED_REGISTRY_STATES = {"active", "tombstone", "archived"}
ALLOWED_COURSE_LIFECYCLES = {"planned", "ongoing", "paused", "completed", "dropped"}
ALLOWED_COURSE_TYPES = {"mastery", "project", "praxis"}
ALLOWED_COURSE_DRIVERS = {"textbook", "goal", "project", "praxis"}
ALLOWED_BINDING_STATES = {"idle", "active", "paused", "closed"}
ALLOWED_CONTAINER_MODES = {"schedule", "progress"}
# A coarse criterion carries a light consequence: a stall only triggers one triage
# question (no points lost, nothing blocked), so calendar days are threshold enough.
# The precise learning-day cursor is left to the rulings that *do* count toward the
# evaluation — that is where it is needed.
STALL_TRIAGE_DAYS = 14
ALLOWED_ATTEMPT_MODES = {"text", "image", "mixed"}
ALLOWED_ATTEMPT_STATES = {"submitted", "withdrawn"}
ALLOWED_HINT_GATE_MODES = {"enabled", "disabled"}
ALLOWED_ASSISTANCE_LEVELS = {"none", "direction", "reference", "solution"}
HINT_GATE_SCHEMA_DATE = dt.date(2026, 8, 1)
ALLOWED_ACTIVITY_KINDS = {"reading"}
ALLOWED_REVIEWERS = {"teacher", "student", "joint"}
ALLOWED_REVIEW_STATES = {"recorded", "amended"}
ALLOWED_REVIEW_RESULTS = {"correct", "partial", "incorrect", "unresolved"}
ALLOWED_MISTAKE_STATES = {"active", "maintenance", "aged"}
ALLOWED_EXAM_DEBT_STATES = {"open", "in_remediation", "settled", "archived"}
RETIRE_LOOP_DECAY_KEYS = ("domain", "timing", "attribution layer", "consumer", "exit", "re-entry")
EXAM_META_COLUMNS = (
    ("Problem no.", "题号"),
    ("Type", "类型"),
    ("Knowledge node", "知识节点"),
    ("Difficulty tier", "难度档"),
    ("Used in teaching", "已用于教学"),
    ("Sat", "已考"),
    ("Solution page", "解答页码"),
    ("Pre-exam check note", "考前检查备注"),
)
ALLOWED_PROJECT_MODES = {"A", "B", "B-K"}
EXPECTED_FLOWS = {
    "first_run", "panorama", "teaching_loop", "authority_chain", "cycles",
    "skin", "git", "batch", "exercise_loop",
}
# LV-5: both spellings of the core-playbook protection marker.
CORE_PLAYBOOK_MARKERS = (
    "**保护级别**：core-playbook",
    "**Protection level**: core-playbook",
)
CORE_PLAYBOOK_MARKER = CORE_PLAYBOOK_MARKERS[0]
# ---------------------------------------------------------------------------
# LV-5 (2026-08-20): prose-marker language registry.
#
# Many gates prove a rule is present by grepping a literal phrase out of a
# playbook.  That works until the playbook ships in a second language, at which
# point a correctly-built edition fails closed for the wrong reason: the rule is
# there and the checker is blind.  Deleting the greps would be worse -- a
# declared constraint with no checker is the `carrier_mismatch` pattern these
# gates exist to prevent.
#
# So the marker keeps ONE canonical identity (its zh-CN spelling, which is the
# historical one) and gains a table of accepted spellings per language edition.
# Adding a language is a data change, not a code change; forgetting to register a
# translation still fails closed, which is the correct direction.
MARKER_VARIANTS: dict[str, tuple[str, ...]] = {
    # --- teaching contract (20_teacher, context_packet) ---
    "统一只读活动路由": ("unified read-only activity route",),
    "当前 Lesson/Exercise 主载体": ("current Lesson/Exercise main carrier",),
    "不把概念桥接回当前题": ("does not bridge the concept back to the current problem",),
    "先给短目录、树形地图": ("give a short table of contents or tree map first",),
    "对象类型表": ("object type table",),
    "新 Exercise 未授权阶段": ("unauthorized stage of a new Exercise",),
    # --- context packet / workflow ---
    "不是新的真相源": ("is not a new source of truth",),
    "## L1 · 当前一步直接证据": ("## L1 · direct evidence for the current step",),
    "## L2 · 触发式完整读取": ("## L2 · trigger-based full reads",),
    "完整序列化 Markdown": ("fully serialized Markdown",),
    "即时摘录 + 触发式展开": ("immediate excerpt + triggered expansion",),
    "同一对话内未变化的 L0 不重复读取": (
        "an unchanged L0 is not re-read within the same conversation",),
    "Main 消费纪律": ("Main consumption discipline",),
    "先建依赖树，再分配 Agent": ("build the dependency tree first, then assign agents",),
    "不得只展示 ID/SHA 让学生盲签": (
        "never show only an ID/SHA and have the student sign blind",),
    "步骤 2：消费 progress.md 当前切片": (
        "Step 2: consume the current slice of progress.md",),
    "L2 读取对应「教学记录」": ("L2 reads the corresponding teaching record",),
    "不得返回缺教材的 `ready`": ("never return `ready` without the textbook",),
    "只回读这些实际目标": ("read back only these actual targets",),
    "原 L0 上下文包立即失效": ("the previous L0 context packet expires immediately",),
    # --- authorization governance ---
    "授权不可放大与闭环止损": (
        "Authorization is non-amplifying and budget stop-loss closes the loop",),
    "授权不可放大": ("Authorization is non-amplifying",),
    "尚未生成的对象不可预授权": ("an object not yet generated cannot be pre-authorized",),
    "receipt 只记录授权证据": ("a receipt records only authorization evidence",),
    "默认最多两轮 finding 整改": (
        "at most two rounds of finding remediation by default",),
    "恢复后动作授权门": ("post-recovery action authorization gate",),
    "概括性认可只覆盖当轮已具体列出的动作": (
        "a general acknowledgement covers only the actions specifically listed this round",),
    "不构成当轮许可": ("does not constitute permission for this round",),
    # --- course / activity templates ---
    "### 2.2 多块长篇讲解的地图优先协议": (
        "### 2.2 Map-first protocol for long multi-block explanations",),
    "一次只深入一个分支": ("go deep into one branch at a time",),
    "无法在不泄露的前提下制作有用总览时，宁可省略总览": (
        "when no useful overview can be made without leaking, omit the overview",),
    "先地图、后逐支": ("map first, then branch by branch",),
    "学生希望怎样确认后再继续": (
        "how the student wants to confirm before continuing",),
    "### 步骤 3：按 current_activity 恢复主载体": (
        "### Step 3: restore the main carrier per current_activity",),
    "#### `lesson` 分支": ("#### `lesson` branch",),
    "#### `exercise` 分支": ("#### `exercise` branch",),
    "Exercise 首启不得读取或构造 Lesson 路径": (
        "an Exercise first start must not read or construct a Lesson path",),
    "教材原文窗口 **仅在 `lesson` + `course_driver: textbook`**": (
        "the textbook source window applies **only to `lesson` + `course_driver: textbook`**",),
    "Micro close 和完整结课都必须原子完成": (
        "both a Micro close and a full close must complete atomically",),
    "Exercise 结课不得顺手": ("an Exercise close must never be done casually",),
    # --- cloud contract ---
    "## 已处理会话": ("## Processed sessions",),
    "## 部件变更指令": ("## Component change directives",),
    "## 云端交接": ("## Cloud handoffs",),
    "不得生成教学 receipt": ("must not generate teaching receipts",),
    # --- test management / candidate replay ---
    "runtime（默认、启动安全）": ("runtime (default, startup-safe)",),
    "不得越级": ("no level skipping",),
    "逐文件相对路径、大小、SHA-256": (
        "per-file relative path, size and SHA-256",),
    "symlink、junction、mount/reparse point": (
        "symlink, junction, or mount/reparse point",),
    "0.2.0 冻结验收边界": ("0.2.0 frozen acceptance boundary",),
    "清单外新提出的理论攻击面": (
        "a theoretical attack surface newly raised outside the manifest",),
    # --- handoff index ---
    "下一版本 Backlog": ("Next-version backlog",),
    # --- profile sections ---
    "每周可投入学习时间": ("Time available per week",),
    "学习目标": ("Learning goals",),
    "期望的辅导方式": ("Preferred tutoring style",),
    "辅导与展现偏好": ("Tutoring and presentation preferences",),
    "个体基线": ("Individual baseline",),
    "已有基础": ("Existing foundation",),
    "编程基础": ("Programming background",),
    "未提供": ("not provided",),
    # --- knowledge ledgers ---
    "## 活跃知识点": ("## Active knowledge points",),
    "## 维护知识点": ("## Maintenance knowledge points",),
    "## 陈年知识点": ("## Aged knowledge points",),
    "当前周期": ("Current cycle",),
    "当前周期摘要": ("Current cycle summary",),
    "知识点键": ("Knowledge point key",),
    "陈年连续正确": ("Aged consecutive correct",),
    "下次陈年日历检查": ("Next aged calendar check",),
    "最近陈年复习卷": ("Latest aged review set",),
    # --- exercises / project verification ---
    "题号": ("Problem number",),
    "题面": ("Problem statement",),
    "状态": ("Status",),
    "难度": ("Difficulty",),
    "来源页": ("Source page",),
    "错误级别": ("Error level",),
    "依赖 completion node": ("Depends on completion node",),
    "思路观察": ("Reasoning observation",),
    "反馈": ("Feedback",),
    "页码": ("Page",),
    "可复现性检查": ("Reproducibility check",),
    "客观验收": ("Objective acceptance",),
    "留档": ("Archived",),
    "盲改挑战": ("Blind-modification challenge",),
    "讲解口试": ("Oral explanation",),
    "指标对账": ("Metric reconciliation",),
    "现场独立验证": ("Live independent verification",),
    "关闭证据": ("Closure evidence",),
    "验收标准": ("Acceptance criteria",),
    # --- memory pointers ---
    "活跃课程组": ("Active course group",),
    "当前课程": ("Current course",),
    "Lesson 上下文": ("Lesson context",),
    "当前教学活动": ("Current teaching activity",),
    "当前教师": ("Current teacher",),
    "日期": ("Date",),
    "学到哪": ("Got to",),
    # --- trading boundary ---
    "交易行为唯一真相源": ("single source of truth for trading behaviour",),
    "纪律唯一真相源": ("single source of truth for discipline",),
    # --- record fields and headings consumed by field_line_re / heading_re (L3) ---
    "作答": ("Answer",),
    "结果": ("Result",),
    "最小状态摘要": ("Minimum state summary",),
    "连续性摘要": ("Continuity summary",),
    "零命中": ("zero hits",),
    # --- source_page_assets prose rules asserted by test_context_packet (L3.5) ---
    "B 层不算数": ("Layer B does not count",),
    "宿主能观察到内容本体进入本轮模型上下文这一事件本身": (
        "the host can observe the event of the content body entering this round's\nmodel context",
    ),
    "A1–A5 经**宿主可观察投递**在本会话内证成": (
        "A1–A5 proven within this session through **host-observable delivery**",
    ),
    "因此「只读 frontmatter」能满足全部前置而**正文一字未投递**": (
        "So \"reading frontmatter only\" can satisfy every precondition while **not one\nword of the body has been delivered**",
    ),
    "等 pending 状态**不得清除**": (
        "pending states such as `pending_visual_scan` **must not be cleared**",
    ),
    "（§3.1.3 A 层「不得冒充」条款原样有效）": (
        "(the §3.1.3 Layer A \"must never pose as\" clause stands unchanged)",
    ),
    "故 A1 要求**完整正文段**投递，宿主观察事件须能区分「正文投递」与「仅 frontmatter 投递」": (
        "Hence A1 requires a **complete body segment** delivery, and the\nhost-observed event must distinguish \"body delivered\" from \"frontmatter only\"",
    ),
    "**子进程摘要**": ("a **subprocess summary**",),
    "证明脚本读过文件，**不**证明本轮模型上下文收到了内容本体": (
        "that proves the script read the file, and **not** that this round's model context received the content body",
    ),
    # --- instance-template structural labels (batch E) ---
    # Every one of these is a heading, a field label, or a table header that some
    # tool greps.  They are registered before the templates are translated, not
    # after: a translated template with an unregistered label is a silent false
    # negative, which is the whole defect family this registry exists to close.
    "Lesson 开场概览": ("Lesson opening overview",),
    "一、解题思维总纲": ("1. General principles of solving",),
    "二、活跃思维模式": ("2. Active thinking patterns",),
    "下一步计划": ("Next-step plan",),
    "下次允许复测": ("Next retest allowed",),
    "最近正式复测": ("Last formal retest",),
    "活跃知识点": ("Active knowledge points",),
    "开场知识树": ("Opening knowledge tree",),
    "知识点树形图": ("Knowledge-point tree",),
    "教材块清单": ("Textbook block list",),
    "学习范围": ("Study scope",),
    "精确停顿点": ("Exact stop",),
    "当前题目": ("Current problem",),
    "当前进度": ("Current progress",),
    "当前值": ("Current value",),
    "详情位置": ("Details location",),
    "项目": ("Item",),
    "生命周期": ("Lifecycle",),
    "容量状态": ("Capacity status",),
    "恢复入口": ("Recovery entry",),
    "学生档案": ("Student profile",),
    "时间预算": ("Time budget",),
    "课程代码": ("Course code",),
    "课程名称": ("Course name",),
    "课程成员": ("Course members",),
    "课程组": ("Course group",),
    "待解决": ("open",),
    "需要回看": ("needs review",),
    "主题": ("Topic",),
    "月份": ("Month",),
    "标题": ("Title",),
    "路径": ("Path",),
    "提示": ("Hint",),
    "答案": ("Answer key",),
    "解答": ("Solution",),
    "讲解": ("Explanation",),
    "暂无": ("None yet",),
    # gate-ledger row columns (learning_activity_model §2.4)
    "行ID": ("Row ID",),
    "块ID": ("Block ID",),
    "门类型": ("Gate type",),
    "闭合依据": ("Basis of closure",),
    "感受回应": ("Response to feeling",),
    "消费于": ("Consumed at",),
    # cloud ledger section labels used without the "## " prefix
    "云端交接": ("Cloud handoffs",),
    "已处理会话": ("Processed sessions",),
    "部件变更指令": ("Component change directives",),
    "首次启动后创建": ("created after first run",),
    "维护知识点": ("Maintenance knowledge points",),
    "陈年知识点": ("Aged knowledge points",),
    "已解答": ("Answered",),
    "回看原因": ("Reason to revisit",),
    "下一步": ("Next step",),
    "下次第一件事": ("First thing next time",),
    "学到哪": ("Reached",),
    "课程": ("Course",),
    "当前活动": ("Current activity",),
    "停点": ("Stop",),
    "历史兼容": ("historical compatibility",),
    # --- t2ag_memory.md section headings read by t2ag_context ---
    "上次课摘要": ("Last session summary",),
    "当前状态指针": ("Current state pointers",),
    # --- profile sections a completed first run must carry an answer in ---
    # The tuple already held historical zh-CN spellings; the English edition's
    # generated headings join the same list rather than a second lookup table.
    "每周可投入学习时间": ("Time available per week",),
    "学习目标": ("Learning goals",),
    "辅导与展现偏好": ("期望的辅导方式", "Tutoring and presentation preferences"),
    "已有基础": ("编程基础", "个体基线", "Individual baseline"),
    # --- changelog verification-layer block headings (changelog_management.md §3) ---
    "锚定断言": ("Anchored assertions",),
    "佐证断言": ("Corroborating assertions",),
    # --- overlay default-row anchor (read AND written by t2ag_init) ---
    "(默认)": ("(default)",),
    # --- activity-route prose rules asserted by test_activity_contracts (L3.5) ---
    "不写 `current_lesson`": ("does not write `current_lesson`",),
    "连续 Scope **5–8**": ("contiguous Scope of **5–8**",),
    "不得自动清理": ("never clean up automatically",),
    "不产生 pending、CLR 或自动 pause": (
        "produces no pending, no CLR and no automatic pause",
    ),
    "progress + 当前活动主载体 + 真实台账": (
        "progress + current activity's main carrier + the real ledger",
    ),
    # --- gate-ledger row kinds and section headings ---
    "块过渡": ("block transition",),
    "翻页": ("page turn",),
    "题目闭环": ("problem closure",),
    "提示授权": ("hint authorization",),
    "## 门台账": ("## Gate ledger",),
    # --- table headings and record fields ---
    "文件": ("File", "file"),
    "内容组连接表": ("Content group map",),
    "作答上下文": ("Answer context",),
    "节点": ("Node",),
    "验证模式": ("Verification mode",),
    "结论": ("Conclusion",),
    "验收日期": ("Acceptance date",),
    # --- progress inline markers ---
    "mistake_bank（内联）": ("mistake_bank (inline)",),
    "待填": ("to be filled in",),
    "无": ("none",),
}


def _normalize_surface(text: str) -> str:
    """Surface-normalized view of `text`, for marker matching.

    Strips blockquote continuation prefixes, collapses whitespace, and strips Markdown
    emphasis runs.  Four surface properties have now been found to move independently
    of the rule: line wrap, letter case, emphasis placement (the registry stores
    `applies **only to X**` while prose bolds the whole phrase), and the `> ` a
    blockquote puts at the start of every continuation line.  Each was found the same
    way -- a document that states the rule failing the gate that checks for it.

    That four kept appearing is itself the argument for giving a rule a machine-owned
    anchor: normalization can only chase surface properties already discovered.
    """
    without_quotes = re.sub(r"(?m)^[ \t]*>[ \t]?", "", text)
    return re.sub(r"[*_]{1,3}", "", re.sub(r"\s+", " ", without_quotes))


def _collapse_ws(text: str) -> str:
    """Whitespace-collapsed view of `text` (kept for callers that need only this)."""
    return re.sub(r"\s+", " ", text)


def has_marker(content: str, marker: str) -> bool:
    """True when `content` carries this marker in ANY shipped language edition.

    Matching is wrap-tolerant.  A marker is a phrase, and prose gets re-wrapped: a
    marker that happens to straddle a line break is still present to a reader and
    still absent to a naive substring search, so the gate would FAIL on a document
    that satisfies it.  That failure mode is invisible in zh-CN (no spaces to wrap
    on) and constant in English -- it bit this translation on the first playbook.
    Collapsing whitespace on both sides costs nothing and removes the whole class.
    """
    candidates = (marker,) + MARKER_VARIANTS.get(marker, ())
    if any(c in content for c in candidates):
        return True
    # Fallback: whitespace-collapsed and case-insensitive.  A marker is a phrase, and
    # English capitalizes at the start of a sentence or a bold run, so the registry
    # spelling and the prose spelling differ by case for no meaningful reason.  For a
    # multi-word phrase the false-positive risk of ignoring case is negligible, while
    # the false-negative it removes is a gate failing on a document that satisfies it.
    flat = _normalize_surface(content).casefold()
    return any(_normalize_surface(c).casefold() in flat for c in candidates)


def marker_spellings(marker: str) -> tuple[str, ...]:
    """Every accepted spelling of a marker, canonical first (LV-5)."""
    return (marker,) + MARKER_VARIANTS.get(marker, ())


def heading_rows(text: str, heading: str):
    """table_after_heading, tried against every language spelling of `heading`."""
    for name in marker_spellings(heading):
        rows = table_after_heading(text, name)
        if rows:
            return rows
    return []


def section_text(text: str, heading: str):
    """markdown_section, tried against every language spelling of `heading`."""
    for name in marker_spellings(heading):
        found = markdown_section(text, name)
        if found:
            return found
    return None


def cell_index(cells, name: str) -> int:
    """Index of a header cell by any of its language spellings; -1 when absent."""
    for spelling in marker_spellings(name):
        if spelling in cells:
            return cells.index(spelling)
    return -1


def row_value(row: dict, name: str, default: str = "") -> str:
    """dict.get across every language spelling of the key."""
    for spelling in marker_spellings(name):
        if spelling in row:
            return row[spelling]
    return default


def gate_is(row: dict, kind: str) -> bool:
    """True when a gate-ledger row is of `kind` in any language edition."""
    return row.get("gate") in marker_spellings(kind)


def gate_starts(row: dict, kind: str) -> bool:
    """True when a gate-ledger row's kind starts with `kind` in any edition."""
    return any(str(row.get("gate", "")).startswith(k) for k in marker_spellings(kind))


def marker_alternation(canonical: str) -> str:
    """Regex alternation over every registered spelling of `canonical`.

    L3 (2026-08-20).  Before this, a bilingual gate was written by hand as an inline
    `(?:状态|Status)` alternation at each call site.  That put the spelling list in
    18 scattered places instead of the registry, with three consequences: a third
    language means editing 18 regexes; the canonical identity exists nowhere; and
    `test_marker_robustness` -- which walks MARKER_VARIANTS -- could not see any of
    them.  The gate built to catch surface-tracking defects protected 111 markers and
    none of these.  Measured at the time: 5 of 5 sampled sites still failed under a
    case change, the same defect that had just been fixed elsewhere.
    """
    return "|".join(re.escape(sp) for sp in marker_spellings(canonical))


def field_line_re(canonical: str, value: str = r"(.+)") -> re.Pattern[str]:
    """`- **Label**: value` / `- Label: value` in any edition, case-insensitively.

    A record field label is a phrase, so it is subject to exactly the surface drift
    that `doctor_contracts.md` §8.4 governs: case at the start of a line, optional
    bold, and either colon width.  Building it from the registry means one identity,
    one place to add a language, and coverage by the mutation test.
    """
    return re.compile(
        rf"^-\s*(?:\*\*)?(?:{marker_alternation(canonical)})(?:\*\*)?\s*[：:]\s*{value}\s*$",
        re.MULTILINE | re.IGNORECASE,
    )


def heading_re(canonical: str) -> re.Pattern[str]:
    """A heading naming `canonical`, in any edition, case-insensitively.

    Registry keys for headings carry their own `##` prefix, so strip the leading
    hashes off each spelling before building the alternation: the prefix belongs to
    the pattern, not to the phrase.  Heading depth is deliberately not pinned --
    promoting a section from `###` to `##` does not change which rule is stated.
    """
    stripped = "|".join(
        re.escape(sp.lstrip("# ").strip()) for sp in marker_spellings(canonical)
    )
    return re.compile(rf"^#+\s+.*(?:{stripped})", re.MULTILINE | re.IGNORECASE)


def marker_position(content: str, marker: str) -> int:
    """Offset of `marker` in `content`, or -1 -- registry-aware and surface-tolerant.

    Some gates assert not just presence but ORDER (a document must branch on
    `current_activity` before it details each branch).  Those sites used raw
    `content.find(literal)`, which bypasses the registry entirely: a translated
    edition scores -1 on every marker and the ordering assertion collapses into
    "missing", naming the wrong defect.  Positions are computed against one
    surface-normalized view so they stay mutually comparable.
    """
    flat = _normalize_surface(content).casefold()
    best = -1
    for spelling in marker_spellings(marker):
        at = flat.find(_normalize_surface(spelling).casefold())
        if at >= 0 and (best < 0 or at < best):
            best = at
    return best


def marker_offset(content: str, marker: str) -> int:
    """Exact offset of `marker` in `content` as given, or -1.

    Companion to `marker_position`, which returns a position in the SURFACE-NORMALIZED
    view -- comparable with another `marker_position`, but **not** an index into
    `content`.  Slicing with a normalized-view offset takes a wrong-but-plausible span
    and the caller sees a truncated block rather than an error, so the two are separate
    functions with separate names.  This one matches a spelling verbatim: real index,
    no surface tolerance.
    """
    best = -1
    for spelling in marker_spellings(marker):
        at = content.find(spelling)
        if at >= 0 and (best < 0 or at < best):
            best = at
    return best


def missing_markers(content: str, markers) -> list[str]:
    """Canonical spellings of the markers absent from `content`, in order."""
    return [m for m in markers if not has_marker(content, m)]


fails: list[str] = []
warns: list[str] = []
infos: list[str] = []


def report(level: str, message: str) -> None:
    {"FAIL": fails, "WARN": warns, "INFO": infos}[level].append(message)
    print(f"[{level}] {message}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def frontmatter(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    content = read(path)
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", content, re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def list_value(raw: str) -> list[str]:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        return [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
    return [part for part in re.split(r"[\s,+]+", value) if part]


def reference_list(raw: str) -> list[str]:
    if raw.strip().strip("`'") in {"", "-", "—", "NONE"}:
        return []
    return [value.strip().strip("`'") for value in list_value(raw)]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def markdown_section(content: str, title: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(title)}\s*$\n(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    return match.group(1).strip() if match else ""


def profile_section_has_answer(content: str, titles: tuple[str, ...]) -> bool:
    for title in titles:
        body = markdown_section(content, title)
        if not body:
            continue
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith(">") or line.startswith("<!--"):
                continue
            checkbox = re.match(r"^-\s*\[([ xX])\]\s*(.*)$", line)
            if checkbox:
                if checkbox.group(1).lower() == "x" and checkbox.group(2).strip():
                    return True
                continue
            if line.startswith("-"):
                value = line[1:].strip()
                if "：" in value:
                    value = value.split("：", 1)[1].strip()
                elif ":" in value:
                    value = value.split(":", 1)[1].strip()
                if value and value not in {"—", "未提供"}:
                    return True
            elif line not in {"—", "未提供"}:
                return True
    return False


def flat_yaml(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in read(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def without_fenced_code(content: str) -> str:
    return re.sub(r"```.*?```", "", content, flags=re.DOTALL)


def table_after_heading(content: str, heading: str) -> list[dict[str, str]]:
    marker = re.search(
        rf"^##+\s+{re.escape(heading)}\s*$",
        content,
        re.MULTILINE,
    )
    if not marker:
        return []
    lines = content[marker.end():].splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip().startswith("|")), None)
    if start is None or start + 1 >= len(lines):
        return []
    headers = [cell.strip() for cell in lines[start].strip().strip("|").split("|")]
    if not all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in lines[start + 1].strip().strip("|").split("|")):
        return []
    rows: list[dict[str, str]] = []
    for line in lines[start + 2:]:
        if not line.strip().startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def check_structure() -> None:
    actual = {
        path.name for path in MAIN.iterdir()
        if path.is_dir() and re.match(r"^\d\d_", path.name)
    } if MAIN.exists() else set()
    if actual != EXPECTED_DOMAINS:
        report("FAIL", f"numbered domains are not the 0.2.0 nine: actual={sorted(actual)}")
    for name in EXPECTED_DOMAINS:
        if not (MAIN / name).is_dir():
            report("FAIL", f"missing numbered domain: main/{name}")
    for name in LEGACY_DOMAINS:
        if (MAIN / name).exists():
            report("FAIL", f"the old active domain still exists: main/{name}")
    if not (MAIN / "t2ag.md").is_file():
        report("FAIL", "missing main/t2ag.md")
    missing_base = [
        relative for relative in BASE_VALIDATION_FILES
        if not (ROOT / relative).is_file()
    ]
    if missing_base:
        report("FAIL", f"the three-form base validation structure is missing: {missing_base}")
    else:
        doctor_content = read(ROOT / "main/70_tools/t2ag_doctor.py")
        missing_markers = [
            marker for marker in BASE_DOCTOR_PROFILE_MARKERS
            if not has_marker(doctor_content, marker)
        ]
        if missing_markers:
            report("FAIL", f"Doctor runtime/release base layering is missing: {missing_markers}")
    if not (MAIN / "80_interface/fable_snail.png").is_file():
        report("FAIL", "missing the interface asset main/80_interface/fable_snail.png")
    if (ROOT / "assets/fable_snail.png").exists():
        report("FAIL", "the old root assets/fable_snail.png is still active")
    student = MAIN / "10_student"
    expected_student_dirs = {"profile", "activities", "engagements"}
    actual_student_dirs = {
        path.name for path in student.iterdir() if path.is_dir()
    } if student.is_dir() else set()
    if actual_student_dirs != expected_student_dirs:
        report(
            "FAIL",
            "10_student top-level directories are not exactly profile/activities/engagements: "
            f"actual={sorted(actual_student_dirs)}",
        )
    profile_root = student / "profile"
    if not profile_root.is_dir():
        report("FAIL", "missing the shared student profile container: main/10_student/profile/")
    expected_profile_files = {
        "profile.md",
        "learning_path.md",
        "course_reflections.md",
        "reasoning_patterns.md",
    }
    for filename in sorted(expected_profile_files):
        canonical = profile_root / filename
        matches = sorted(student.rglob(filename)) if student.is_dir() else []
        if matches != [canonical]:
            report(
                "FAIL",
                "exactly one shared student profile must exist: "
                f"{filename} -> {[rel(path) for path in matches]}",
            )
        if (student / filename).exists():
            report("FAIL", f"the old top-level student profile file still exists: main/10_student/{filename}")


def extract_runtime_version(constitution_text: str) -> str | None:
    """Parse the declared runtime version from t2ag.md prose/heading."""
    patterns = (
        r"当前运行版本[：:]\s*`?(0\.\d+\.\d+)`?",
        r"-\s*当前版本[：:]\s*`?(0\.\d+\.\d+)`?",
        # LV-5 (2026-08-20): translated editions carry the same anchor in English.
        r"(?i)runtime version[：:]\s*`?(0\.\d+\.\d+)`?",
        r"(?i)-\s*current version[：:]\s*`?(0\.\d+\.\d+)`?",
        r"^#\s+T2AG\s+(0\.\d+\.\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, constitution_text, re.MULTILINE)
        if match:
            return match.group(1)
    return None


def check_memory_version_prose(memory_text: str, runtime_version: str) -> None:
    """Fail when hand-written current-version markers disagree with t2ag.md.

    Historical mentions of older releases (e.g. closing out 0.2.1) are allowed;
    only title-line and "the current version is ..." markers count as live identity.
    """
    title = re.search(r"^#\s+T2AG\s+(0\.\d+\.\d+)\b", memory_text, re.MULTILINE)
    if title and title.group(1) != runtime_version:
        report(
            "FAIL",
            f"t2ag_memory.md title version {title.group(1)} and the runtime version "
            f"{runtime_version} mismatch",
        )
    # blockquote / bullet "Version: 0.x.y" near the file head (Main style)
    head = "\n".join(memory_text.splitlines()[:12])
    for match in re.finditer(r"(?:版本|[Vv]ersion)[：:]\s*`?(0\.\d+\.\d+)`?", head):
        if match.group(1) != runtime_version:
            report(
                "FAIL",
                f"t2ag_memory.md head version {match.group(1)} and the runtime version "
                f"{runtime_version} mismatch",
            )
    for match in re.finditer(r"(?:当前版本为|the current version is)\s*(0\.\d+\.\d+)", memory_text):
        if match.group(1) != runtime_version:
            report(
                "FAIL",
                f"t2ag_memory.md hand-written 「the current version is {match.group(1)}」 and the runtime version "
                f"{runtime_version} mismatch",
            )


def check_memory_version_pointer(memory_text: str, runtime_version: str) -> None:
    """Fail when the GENERATED state-pointer row disagrees with t2ag.md.

    EV-0015 memory version guard.  The row is produced by t2ag_state_refresh; if that
    generator ever hardcodes a literal again, ``state_refresh --check`` cannot
    see the drift because it compares its own constant with itself.  Doctor is
    the independent observer, so the guard belongs here.
    """
    matches = list(
        re.finditer(r"^\|\s*T2AG (?:版本|version)\s*\|\s*(\S+)\s*\|", memory_text, re.MULTILINE)
    )
    if not matches and "T2AG_GENERATED:STATE_POINTERS" in memory_text:
        # Guarding only the value would be a false negative: a generator that
        # stopped emitting the row entirely would slip through silently, and
        # state_refresh --check cannot see it either (it would omit the row on
        # both sides).  Require the row whenever the block itself exists.
        report("FAIL", "the t2ag_memory.md STATE_POINTERS block lacks a T2AG version row")
    for match in matches:
        if match.group(1) != runtime_version:
            report(
                "FAIL",
                f"t2ag_memory.md GENERATED state pointer version {match.group(1)} and the runtime version "
                f"{runtime_version} mismatch (fix the version source in t2ag_state_refresh "
                f"first, then run --write)",
            )


VERSION_LEDGER_REL = "main/60_journal/t2ag_version_ledger.md"


def version_bump_precondition_findings(
    constitution_text: str, ledger_text: str
) -> list[tuple[str, str, str]]:
    """VER-BUMP-000..002 — a predecessor that never closed out blocks the bump.

    Judges **this transition only**: the immediate predecessor of the running
    version must be recorded `complete` in the version ledger.  It deliberately
    does not walk the whole history — the three-field convention began at 0.2.1,
    and retro-applying it to older versions would report defects that were never
    defects.  The criterion governs the next bump, not the past.

    Known coverage hole (declared, not silently absent): only patch-level bumps
    are checked.  A minor/major bump (patch == 0) has no arithmetic predecessor
    this function can name, so it reports nothing — the judgement half of the
    criterion (`batch_workorder_spec.md`, version-bump criteria) is prose_accepted there.

    ``ledger_text`` lines look like::

        - 0.2.2 `implementation_status`：`complete`；`candidate_review`：`passed`
    """
    findings: list[tuple[str, str, str]] = []
    current = extract_runtime_version(constitution_text)
    if not current:
        return findings
    parts = current.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return findings
    major, minor, patch = (int(p) for p in parts)
    if patch == 0:
        return findings
    predecessor = f"{major}.{minor}.{patch - 1}"

    def field(name: str) -> str | None:
        # Line-scoped on purpose: the ledger puts several fields on one line
        # (``- 0.2.2 `implementation_status`：`complete`；`candidate_review`：…``),
        # so a version-then-field regex over the whole text only ever matches
        # the first field.  Require the version to appear before the field on
        # the same line, which also stops a neighbouring version's record from
        # answering for this one.
        token = re.compile(r"`" + re.escape(name) + r"`\s*[：:]\s*`([A-Za-z_]+)`")
        for line in ledger_text.splitlines():
            position = line.find(predecessor)
            if position < 0:
                continue
            match = token.search(line, position)
            if match:
                return match.group(1)
        return None

    status = field("implementation_status")
    if status is None:
        findings.append(
            (
                "VER-BUMP-001",
                "FAIL",
                f"runtime version {current} whose predecessor {predecessor} has no "
                f"row in the version ledger ({VERSION_LEDGER_REL} is the single "
                f"source of truth for version status, CR-1=A; constitution §7 "
                f"points, it does not carry): the bump left the previous version "
                f"with no closure evidence",
            )
        )
    elif status != "complete":
        findings.append(
            (
                "VER-BUMP-000",
                "FAIL",
                f"runtime version {current} whose predecessor {predecessor} "
                f"`implementation_status`={status} (should be complete): starting a new "
                f"version number before the previous one closed out permanently "
                f"leaves an unclosed version in the history",
            )
        )
    review = field("candidate_review")
    if review is not None and review != "passed":
        findings.append(
            (
                "VER-BUMP-002",
                "WARN",
                f"predecessor {predecessor} `candidate_review`={review} (not passed): this "
                f"version was never independently reviewed; re-check before citing "
                f"it as a release-qualification basis",
            )
        )
    return findings


def check_version_bump_precondition() -> None:
    """VER-BUMP-000..002: the previous version must have closed out.

    The judgement half of the bump criterion — *whether a new version is worth
    opening* — has no machine handle and is declared `prose_accepted` in
    `batch_workorder_spec.md`.  This check carries only the factual half, which
    is exactly the half that can be verified: whether the version being left
    behind was ever finished.  It fires on the bad action itself rather than
    accumulating as a standing complaint, so it stays silent until someone bumps.
    """
    constitution = MAIN / "t2ag.md"
    ledger = MAIN / "60_journal/t2ag_version_ledger.md"
    if not constitution.is_file():
        report("FAIL", "missing main/t2ag.md (the version-bump precondition cannot be checked)")
        return
    if not ledger.is_file():
        report("WARN", f"the version ledger is missing: {VERSION_LEDGER_REL}(the version-bump precondition cannot be checked)")
        return
    for code, severity, message in version_bump_precondition_findings(
        read(constitution), read(ledger)
    ):
        report(severity, f"{code} {message}")


def check_version_and_profile() -> None:
    constitution = MAIN / "t2ag.md"
    memory = MAIN / "00_core/t2ag_memory.md"
    if not constitution.exists():
        report("FAIL", "missing main/t2ag.md")
        return
    constitution_text = read(constitution)
    runtime_version = extract_runtime_version(constitution_text)
    if not runtime_version:
        report("FAIL", "main/t2ag.md: the current runtime version cannot be parsed")
        return
    for path in (constitution, memory):
        if path.exists() and runtime_version not in read(path):
            report(
                "FAIL",
                f"version is not updated to {runtime_version}：{rel(path)}",
            )
    for path in (ROOT / "README.md", ROOT / "AGENTS.md", MAIN / "bin/t2ag"):
        if not path.exists() or runtime_version not in read(path):
            report(
                "FAIL",
                f"release entry version is not updated to {runtime_version}：{rel(path)}",
            )
    if memory.exists():
        memory_text = read(memory)
        check_memory_version_prose(memory_text, runtime_version)
        check_memory_version_pointer(memory_text, runtime_version)
    launcher = MAIN / "bin/t2ag"
    if launcher.exists():
        content = read(launcher)
        if "main/skin" in content:
            report("FAIL", "the launcher still points at the retired main/skin")
        if re.search(r"/[a-zA-Z]/Users/|[A-Za-z]:[\\/]Users[\\/]", content):
            report("FAIL", "the launcher contains a machine-specific user absolute path")
    profile = MAIN / "10_student/profile/profile.md"
    if not profile.exists():
        report("FAIL", "missing 10_student/profile/profile.md")
        return
    meta = frontmatter(profile)
    collaboration_values = {
        "agent_collaboration_schema": meta.get("agent_collaboration_schema"),
        "agent_parallel_startup": meta.get("agent_parallel_startup"),
        "agent_startup_readiness": meta.get("agent_startup_readiness"),
        "agent_background_reporting": meta.get("agent_background_reporting"),
    }
    if collaboration_values["agent_collaboration_schema"] != "agent_collaboration_preferences.v1":
        report("FAIL", "profile lacks agent_collaboration_preferences.v1")
    try:
        agent_pool_limit = int(meta.get("agent_pool_limit", ""))
    except (TypeError, ValueError):
        agent_pool_limit = 0
    if agent_pool_limit not in {1, 2, 3, 4, 5, 6}:
        report("FAIL", "profile agent_pool_limit must be 1..6")
    try:
        agent_max_active = int(meta.get("agent_max_active", ""))
    except (TypeError, ValueError):
        agent_max_active = 0
    if agent_max_active not in {1, 2, 3}:
        report("FAIL", "profile agent_max_active must be 1..3")
    if agent_max_active > agent_pool_limit:
        report("FAIL", "profile agent_max_active must not exceed agent_pool_limit")
    if collaboration_values["agent_parallel_startup"] not in {"enabled", "disabled"}:
        report("FAIL", "profile agent_parallel_startup must be enabled|disabled")
    if collaboration_values["agent_startup_readiness"] not in {
        "learning_ready_first", "recovery_settled_first"
    }:
        report("FAIL", "profile agent_startup_readiness is invalid")
    if collaboration_values["agent_background_reporting"] not in {"blockers_only", "all"}:
        report("FAIL", "profile agent_background_reporting must be blockers_only|all")
    if FLAVOR == "skeleton":
        if (
            agent_pool_limit != 6
            or agent_max_active != 3
            or collaboration_values["agent_parallel_startup"] != "enabled"
            or collaboration_values["agent_startup_readiness"] != "learning_ready_first"
            or collaboration_values["agent_background_reporting"] != "blockers_only"
        ):
            report("FAIL", "Skeleton agent collaboration preferences must retain the 6-agent pool / 3-agent concurrency defaults")
        if meta.get("initialization_status") == "initialized":
            report("FAIL", "Skeleton profile must not be marked initialized")
        if meta.get("exercise_hint_gate") != "ask":
            report("FAIL", "Skeleton profile hint gate must wait for the student to choose: ask")
        content = read(profile)
        if re.search(r"\bS00[2-9]\b|MikeChen|上海交通大学", content):
            report("FAIL", "Skeleton profile carries a real instance identifier")
    else:
        content = read(profile)
        if meta.get("initialization_status") != "initialized":
            report("FAIL", f"{FLAVOR} profile is uninitialized")
            return
        if meta.get("exercise_hint_gate") not in ALLOWED_HINT_GATE_MODES:
            report(
                "FAIL",
                f"{FLAVOR} profile lacks the student-confirmed exercise_hint_gate: enabled|disabled",
            )
        if re.search(
            r"<(?:required|confirm|confirm-or-none|off\s*\|\s*suggest\s*\|\s*auto)>"
            r"|[（(](?:待填写|to be filled in)[）)]",
            content,
            re.IGNORECASE,
        ):
            report("FAIL", "an initialized profile still contains first-run required placeholders")
        # LV-5: these four were a private lookup table duplicating what
        # MARKER_VARIANTS already models (one canonical label, several accepted
        # spellings). A translated edition's generated profile would have failed
        # this check for the one reason that is intended, so the list now lives in
        # the registry and a new language is a data change here too.
        required_sections = (
            "每周可投入学习时间", "学习目标", "辅导与展现偏好", "已有基础",
        )
        missing = [
            label for label in required_sections
            if not profile_section_has_answer(content, marker_spellings(label))
        ]
        if missing:
            report("FAIL", f"initialized profile has unconfirmed required information: {missing}")


def check_skin_system() -> None:
    interface = MAIN / "80_interface"
    global_config = interface / "skin.yaml"
    if not global_config.is_file():
        report("FAIL", "missing the global skin configuration: main/80_interface/skin.yaml")
        return
    config = flat_yaml(global_config)
    active = config.get("active", "")
    if not active:
        report("FAIL", "the global skin configuration lacks active")
        return
    registry = {
        key.split(".", 1)[1]: value
        for key, value in config.items()
        if key.startswith("registry.") and "." in key
    }
    if active not in registry:
        report("FAIL", f"active skin is not registered: {active}")
        return
    folder_name = registry[active]
    if not re.fullmatch(r"SK\d{3}_[A-Za-z0-9_]+", folder_name):
        report("FAIL", f"skin registry directory name is invalid: {active} -> {folder_name}")
    folder = interface / folder_name
    metadata_path = folder / "skin.yaml"
    if not folder.is_dir() or not metadata_path.is_file():
        report("FAIL", f"active skin carrier does not exist: {active} -> {folder_name}")
        return
    metadata = flat_yaml(metadata_path)
    missing = [
        key for key in ("id", "name", "version", "welcome_msg", "art_file", "style")
        if not metadata.get(key)
    ]
    if missing:
        report("FAIL", f"active skin metadata lacks a field: {missing}")
    if metadata.get("id") != active or not folder_name.startswith(active + "_"):
        report("FAIL", f"active skin ID/directory mismatch: {active} -> {folder_name}")
    art_file = metadata.get("art_file", "")
    if not art_file or Path(art_file).name != art_file:
        report("FAIL", f"skin art_file must be a filename inside the directory: {art_file}")
    elif not (folder / art_file).is_file():
        report("FAIL", f"skin art_file is dangling: {folder_name}/{art_file}")
    welcome = metadata.get("welcome_msg", "")
    if re.search(r"必须|规则|禁止|不得|\bmust\b|\bshall\b", welcome, re.IGNORECASE):
        report("WARN", f"skin welcome_msg may carry teaching instructions: {active}")
    registered_folders = set(registry.values())
    for candidate in sorted(interface.glob("SK*")):
        if candidate.is_dir() and candidate.name not in registered_folders:
            report("WARN", f"the skin directory is not registered: {rel(candidate)}")
    default_welcome = interface / "SK001_default/01_welcome.txt"
    if not default_welcome.is_file() or "t2AG" not in read(default_welcome):
        report("FAIL", "the default welcome character art does not clearly display t2AG")
    if active == "SK001" and folder_name == "SK001_default":
        expected_art = "01_welcome.txt" if FLAVOR == "skeleton" else "03_inori_2.txt"
        if art_file != expected_art:
            report(
                "FAIL",
                f"SK001 default divergence is wrong: {FLAVOR} expected={expected_art} actual={art_file}",
            )


def discover_courses() -> dict[str, tuple[Path, dict[str, str]]]:
    COURSE_SNAPSHOTS.clear()
    COURSE_ROUTES.clear()
    result: dict[str, tuple[Path, dict[str, str]]] = {}
    course_metas: dict[str, dict[str, str]] = {}
    root = MAIN / "40_course"
    post_022 = any(root.glob("*/activity_ledger.md")) if root.exists() else False
    if not root.exists():
        return result
    for folder in sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("_")):
        course = folder / "course.md"
        progress = folder / "progress.md"
        if not course.exists():
            report("FAIL", f"course lacks course.md: {folder.name}")
            continue
        if not progress.exists():
            report("FAIL", f"course lacks progress.md: {folder.name}")
            continue
        cmeta = frontmatter(course)
        progress_content = read(progress)
        pmeta = frontmatter_text(progress_content)
        progress_snapshot = ProgressSnapshot(progress, progress_content, pmeta)
        COURSE_SNAPSHOTS[folder.name] = progress_snapshot
        if cmeta.get("type") != "course" or cmeta.get("course_id") != folder.name:
            report("FAIL", f"course frontmatter does not match: {rel(course)}")
        required_course_fields = {
            "school_course_code", "name", "course_type", "default_driver",
            "prerequisites", "status",
        }
        missing_course_fields = sorted(required_course_fields - set(cmeta))
        if missing_course_fields:
            report("FAIL", f"course schema lacks a field: {folder.name} -> {missing_course_fields}")
        if cmeta.get("course_type") not in ALLOWED_COURSE_TYPES:
            report("FAIL", f"course_type is invalid: {folder.name} -> {cmeta.get('course_type', 'missing')}")
        if cmeta.get("default_driver") not in ALLOWED_COURSE_DRIVERS:
            report("FAIL", f"default_driver is invalid: {folder.name} -> {cmeta.get('default_driver', 'missing')}")
        if cmeta.get("status") != "active":
            report("FAIL", f"Course definition carrier status must be active: {folder.name}")
        try:
            validate_progress_identity(pmeta, folder.name)
        except ActivityContractError as exc:
            for error in exc.errors:
                report("FAIL", f"progress identity contract: {rel(progress)} -> {error}")
        if post_022:
            if pmeta.get("truth_scope") != "course_lifecycle,course_frontend,activity_position":
                report("FAIL", f"0.2.2 progress truth_scope is invalid: {folder.name}")
            if "truth_source" in pmeta:
                report("FAIL", f"0.2.2 progress must not retain truth_source: {folder.name}")
            if "current_lesson" in pmeta:
                report("FAIL", f"0.2.2 progress must not retain current_lesson: {folder.name}")
        lifecycle = pmeta.get("lifecycle_status", "")
        if lifecycle not in ALLOWED_COURSE_LIFECYCLES:
            report("FAIL", f"course lifecycle is invalid: {folder.name} -> {lifecycle}")
        if pmeta.get("course_driver") not in ALLOWED_COURSE_DRIVERS:
            report("FAIL", f"course_driver is invalid: {folder.name} -> {pmeta.get('course_driver', 'missing')}")
        if not pmeta.get("updated") or pmeta.get("updated") == "—":
            report("FAIL", f"progress lacks a non-empty updated: {folder.name}")
        next_action = pmeta.get("next_action") or re.search(
            rf"^\s*-\s*\*\*(?:{next_action_label_alternation()})\*\*[：:]\s*(.+)$",
            progress_content,
            re.MULTILINE,
        )
        if not next_action:
            report("FAIL", f"progress lacks a next action: {folder.name}")
        if "mistake_bank（内联）" in progress_content:
            report("FAIL", f"progress contains a duplicate inline mistake_bank ledger: {folder.name}")
        if lifecycle == "planned":
            # 0.2.2: current_lesson retired; if present must be none.
            if "current_lesson" in pmeta and pmeta.get("current_lesson") != "none":
                report("FAIL", f"planned course current_lesson must be none: {folder.name}")
            if pmeta.get("progress_nodes_status") != "lazy_on_activation":
                report("FAIL", f"planned course lacks lazy_on_activation: {folder.name}")
            if post_022:
                expected_none = {
                    "current_activity": "none",
                    "current_activity_id": "none",
                    "resume_path": "none",
                    "activity_position": "between_activities",
                    "next_action_kind": "none",
                    "next_activity_type": "none",
                    "next_activity_id": "none",
                }
                bad = {key: pmeta.get(key) for key, value in expected_none.items() if pmeta.get(key) != value}
            else:
                bad = {
                    field: pmeta.get(field)
                    for field in (
                        "current_activity", "current_activity_id", "resume_path",
                        "activity_position", "lesson_position",
                    )
                    if field in pmeta
                    and pmeta.get(field) not in {"none", "—", "", "between_activities"}
                }
            if bad:
                report(
                    "FAIL",
                    f"planned course canonical-none is invalid: {folder.name} -> {bad}",
                )
        elif lifecycle == "ongoing":
            required_progress = (
                "current_activity", "current_activity_id",
                "activity_position", "current_completion_node",
                "current_checkpoint", "checkpoint_state", "resume_path",
            )
            missing_progress = [
                field for field in required_progress if not pmeta.get(field)
            ]
            if missing_progress:
                report("FAIL", f"ongoing progress lacks a field: {folder.name} -> {missing_progress}")
            else:
                try:
                    COURSE_ROUTES[folder.name] = resolve_activity(
                        ROOT, folder.name, progress_snapshot,
                    )
                except ActivityContractError as exc:
                    for error in exc.errors:
                        report("FAIL", f"current activity contract: {folder.name} -> {error}")
            if "lesson_position" in pmeta:
                report("FAIL", f"ongoing progress uses the retired lesson_position: {folder.name}")
            for navigation in (progress, folder / "lessons/README.md"):
                if not navigation.is_file():
                    continue
                navigation_content = (
                    progress_content if navigation == progress else read(navigation)
                )
                if re.search(
                    r"/[a-zA-Z]/Users/|[A-Za-z]:[\\/]Users[\\/]",
                    navigation_content,
                ):
                    report("FAIL", f"the activity course recovery note contains a machine absolute path: {rel(navigation)}")
        if (folder / "progress_nodes.md").exists():
            report("FAIL", f"progress_nodes are not folded into progress: {folder.name}")
        for required in ("lessons", "exercises", "book"):
            if not (folder / required).is_dir():
                report("FAIL", f"course lacks {required}/：{folder.name}")
        for required in ("mistake_bank.md", "question_bank.md"):
            if not (folder / required).is_file():
                report("FAIL", f"course lacks {required}：{folder.name}")
        result[folder.name] = (folder, pmeta)
        course_metas[folder.name] = cmeta

    for course_id, meta in course_metas.items():
        prerequisites = list_value(meta.get("prerequisites", "[]"))
        if len(prerequisites) != len(set(prerequisites)):
            report("FAIL", f"course prerequisites duplicated: {course_id}")
        if course_id in prerequisites:
            report("FAIL", f"course prerequisites are self-referential: {course_id}")
        for prerequisite in prerequisites:
            if prerequisite not in course_metas:
                report("FAIL", f"course prerequisite does not exist: {course_id} -> {prerequisite}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(course_id: str) -> None:
        if course_id in visiting:
            report("FAIL", f"course prerequisites contain a cycle: {course_id}")
            return
        if course_id in visited:
            return
        visiting.add(course_id)
        for prerequisite in list_value(course_metas[course_id].get("prerequisites", "[]")):
            if prerequisite in course_metas:
                visit(prerequisite)
        visiting.remove(course_id)
        visited.add(course_id)

    for course_id in course_metas:
        visit(course_id)
    return result


def cached_progress_content(course_id: str, folder: Path) -> str:
    """Use the run-scoped snapshot; direct component tests may supply a fixture."""
    snapshot = COURSE_SNAPSHOTS.get(course_id)
    if snapshot is not None:
        return snapshot.content
    return read(folder / "progress.md")


# ---------------------------------------------------------------------------
# P-0068: the audit-zero-loss check for the gate-visibility switch (2026-08-21)
#
# `gate_visibility: quiet` moves the four beats from the conversational rhythm
# into the ledger; it **removes no evidence**. So a quiet course has to prove its
# audit actually landed on disk -- otherwise quiet is a covert loosening of
# authority, and that is one of the three floor gates, not an experience knob.
#
# Only the whole-course two-value form is recognised. Per-domain tiering
# (P-0073 N6) is unauthorised this round, and writing it is judged invalid rather
# than silently accepted: an unimplemented syntax quietly swallowed belongs to the
# "the guarantee is narrower than the claim" family (P-0067).
# ---------------------------------------------------------------------------

GATE_VISIBILITY_VALUES: frozenset[str] = frozenset({"explicit", "quiet"})
GATE_LEDGER_ROW_RE = re.compile(r"^\|\s*GT-\d+\s*\|", re.MULTILINE)

RECOMMENDATION_STATUSES: frozenset[str] = frozenset(
    {"proposed", "deferred", "adopted", "retired"}
)
RECOMMENDATION_SCOPES: frozenset[str] = frozenset({"system", "group", "course"})
RECOMMENDATION_REQUIRED_FIELDS: tuple[str, ...] = (
    "scope",
    "target",
    "status",
    "provenance",
    "revisit_when",
)


def gate_visibility_findings(
    courses: dict[str, tuple[str, list[str]]],
) -> list[tuple[str, str, str]]:
    """Verdict over ``course_id -> (declared_value, lesson_texts)``.

    Absent value means ``explicit`` (the default), which needs no evidence beyond
    what the ordinary gate-ledger check already requires.
    """
    findings: list[tuple[str, str, str]] = []
    quiet: list[str] = []
    for course_id, (declared, lessons) in sorted(courses.items()):
        value = (declared or "explicit").strip()
        if value not in GATE_VISIBILITY_VALUES:
            findings.append(
                (
                    "GV-001",
                    "WARN",
                    f"{course_id} gate_visibility value is invalid: {value!r} (the two "
                    f"legal values are {sorted(GATE_VISIBILITY_VALUES)}; per-domain "
                    "tiering = P-0073 N6, unauthorised this round, and an extended "
                    "syntax must not be drawn on in advance)",
                )
            )
            continue
        if value != "quiet":
            continue
        quiet.append(course_id)
        if not any(GATE_LEDGER_ROW_RE.search(text) for text in lessons):
            findings.append(
                (
                    "GV-002",
                    "WARN",
                    f"{course_id} declares quiet but its lesson gate ledger holds no GT "
                    "row: quiet moves the four beats from the conversation into the "
                    "ledger, so an empty ledger is a net audit loss -- that is a covert "
                    "loosening of authority (a floor gate, not an experience knob)",
                )
            )
    if quiet:
        findings.append(
            (
                "GV-000",
                "INFO",
                f"gate-visibility experiment in progress (P-0068 arrangement B): "
                f"{', '.join(quiet)}; friction evidence goes into lesson_thoughts, and "
                "whether the protocol text itself changes is still the student's final call",
            )
        )
    return findings


def check_gate_visibility() -> None:
    """P-0068: a quiet course's audit must land on disk (WARN-only)."""
    course_root = MAIN / "40_course"
    if not course_root.is_dir():
        return
    courses: dict[str, tuple[str, list[str]]] = {}
    for folder in sorted(course_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        course_file = folder / "course.md"
        if not course_file.is_file():
            continue
        declared = frontmatter(course_file).get("gate_visibility", "")
        if not declared:
            continue  # undeclared = the explicit default; no extra evidence needed
        lessons = [
            read(path) for path in sorted(folder.glob("lessons/*/lesson*.md"))
        ]
        courses[folder.name] = (declared, lessons)
    for _code, severity, message in gate_visibility_findings(courses):
        report(severity, message)


def recommendation_entries(text: str) -> list[tuple[str, dict[str, str], str]]:
    """Parse ``## R-NNNN`` blocks into ``(id, fields, body)``, fenced-block safe."""
    body = strip_fenced_blocks(text)
    entries: list[tuple[str, dict[str, str], str]] = []
    matches = list(re.finditer(r"^## (R-\d{4})\b(.*)$", body, re.MULTILINE))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        block = body[start:end]
        fields: dict[str, str] = {}
        for line in block.splitlines():
            field = re.fullmatch(r"-\s*([a-z_]+):\s*(.*)", line.strip())
            if field:
                fields.setdefault(field.group(1), field.group(2).strip())
        entries.append((match.group(1), fields, block))
    return entries


def recommendation_findings(
    entries: list[tuple[str, dict[str, str], str]],
    *,
    ledger_present: bool,
) -> list[tuple[str, str, str]]:
    """Pure format verdict for the recommendation ledger (WARN-only)."""
    findings: list[tuple[str, str, str]] = []
    if not ledger_present:
        # No ledger = an instance that never built one (Skeleton, a new trial
        # user); that is not a defect.
        return findings
    if not entries:
        findings.append(
            (
                "REC-000",
                "INFO",
                "the recommendation ledger is present but holds no entry (observational "
                "state; an empty ledger is not judged a defect)",
            )
        )
        return findings
    seen: set[str] = set()
    for entry_id, fields, block in entries:
        if entry_id in seen:
            findings.append(
                (
                    "REC-004",
                    "WARN",
                    f"{entry_id} entry ID is duplicated (references become ambiguous, "
                    "same as P-0072)",
                )
            )
        seen.add(entry_id)
        missing = [
            name for name in RECOMMENDATION_REQUIRED_FIELDS if not fields.get(name)
        ]
        if missing:
            findings.append(
                (
                    "REC-001",
                    "WARN",
                    f"{entry_id} is missing required fields: {', '.join(missing)} "
                    "(a missing revisit_when = a dead entry; a missing provenance = "
                    "ownerless accumulation)",
                )
            )
        status = fields.get("status", "")
        if status and status not in RECOMMENDATION_STATUSES:
            findings.append(
                (
                    "REC-002",
                    "WARN",
                    f"{entry_id} status is invalid: {status!r} is not in the four legal "
                    f"values {sorted(RECOMMENDATION_STATUSES)}",
                )
            )
        scope = fields.get("scope", "")
        if scope and scope not in RECOMMENDATION_SCOPES:
            findings.append(
                (
                    "REC-005",
                    "WARN",
                    f"{entry_id} scope is invalid: {scope!r} is not in "
                    f"{sorted(RECOMMENDATION_SCOPES)}",
                )
            )
        provenance = fields.get("provenance", "")
        if provenance and not re.match(r"(student|model)\b", provenance):
            findings.append(
                (
                    "REC-006",
                    "WARN",
                    f"{entry_id} provenance must start with student or model (got "
                    f"{provenance!r}): model suggestions accumulating unmarked is a "
                    "known failure mode",
                )
            )
        if status == "adopted" and not re.search(r"main/\S+\.md", block):
            findings.append(
                (
                    "REC-003",
                    "WARN",
                    f"{entry_id} is marked adopted but the block names no plan/progress "
                    "landing reference: claiming adoption while unable to point at the "
                    "corresponding change = adoption on paper only",
                )
            )
    return findings


def check_recommendation_ledger() -> None:
    """P-0069: format check for the recommendation ledger (WARN-only; semantics stay human)."""
    ledger = MAIN / "30_group/recommendations.md"
    if not ledger.is_file():
        return
    for _code, severity, message in recommendation_findings(
        recommendation_entries(read(ledger)), ledger_present=True
    ):
        report(severity, message)


def check_container_mode(
    group_id: str,
    folder: Path,
    meta: dict[str, str],
    members: list[str],
    courses: dict[str, tuple[Path, dict[str, str]]],
) -> None:
    """Runtime: container anchors present, and stalled progress gets triaged.

    Two container shapes are legal (schedule / progress); having *no* container
    is not.  So the stop-loss anchor of whichever shape the group declared must
    exist -- for ``progress`` that is the per-keystone dwell budget, which is the
    only thing standing between "paced by ability" and "never ends".

    The stall probe deliberately does **not** judge fault.  Pausing is legitimate
    (a training camp, a bad month), and the adjudicated consequence is one triage
    question that costs the student nothing.  What gets a WARN is the third
    outcome: neither ``paused`` nor a review -- drifting silently.
    """
    calendar = folder / "calendar.md"
    cal = frontmatter(calendar) if calendar.is_file() else {}
    mode = meta.get("container_mode", "")

    if mode == "progress":
        if not cal.get("keystone_dwell_budget_cycles"):
            report(
                "FAIL",
                f"{group_id} progress container lacks the stop-loss anchor"
                " keystone_dwell_budget_cycles: a by-progress mode without a budget has no"
                " container (course_group_rules.md §4.1)",
            )
    elif mode == "schedule":
        if "cycle_anchor_learning_day" not in cal:
            report(
                "WARN",
                f"{group_id} schedule container lacks the cycle_anchor_learning_day field"
                " (TBD is a legal value; a missing field is not)",
            )

    if mode != "progress" or meta.get("status") != "active":
        return

    check_keystone_ledger(group_id, folder, meta)

    today = dt.date.today()
    for course_id in members:
        if course_id not in courses:
            continue
        _course_folder, course_meta = courses[course_id]
        if course_meta.get("lifecycle_status", "") != "ongoing":
            continue  # paused/completed is already a triage outcome; do not ask again
        raw = str(course_meta.get("updated", ""))[:10]
        try:
            last = dt.date.fromisoformat(raw)
        except ValueError:
            continue
        idle = (today - last).days
        if idle >= STALL_TRIAGE_DAYS:
            report(
                "WARN",
                f"STALL-TRIAGE-001 {group_id}/{course_id} has not moved for {idle} days,"
                " awaiting triage: stuck → emergency review | no time → switch to paused and"
                " record the resumption condition | the triage counts toward neither the grade"
                " nor the mastery evaluation (course_group_rules.md §4.2)",
            )


def check_keystone_ledger(group_id: str, folder: Path, meta: dict[str, str]) -> None:
    """Scope-drift ledger reconciliation (course_group_rules.md §4.3).

    §4.2 guards against silent drift in *time*; this guards against silent
    drift in *scope* -- same invariant: changes are fine, unlogged changes are
    not.  The machine never judges whether a cut was right (that adjudication
    lives in the review the ledger row came from).  It only enforces "no cut
    without a ledger row": current keystones plus logged cuts must equal the
    frozen anchor.  Deliberately coarse -- no review-ID binding, same judgment
    call as the 14-day stall probe.
    """
    plan = folder / "plan.md"
    text = read(plan) if plan.is_file() else ""

    raw_frozen = meta.get("keystone_total_frozen", "")
    if not raw_frozen:
        report(
            "FAIL",
            f"{group_id} is an active progress group but lacks the keystone count anchor"
            " keystone_total_frozen: the freeze happens at the group-forming ritual, and"
            " without the anchor there is nothing to reconcile against"
            " (course_group_rules.md §4.3)",
        )
        return
    try:
        frozen = int(raw_frozen)
    except ValueError:
        report(
            "FAIL",
            f"{group_id} keystone_total_frozen is invalid: {raw_frozen} (must be an integer)",
        )
        return

    def section(title: str) -> str:
        match = re.search(rf"^#+\s.*{title}.*$", text, flags=re.M)
        if not match:
            return ""
        rest = text[match.end():]
        nxt = re.search(r"^#+\s", rest, flags=re.M)
        return rest[: nxt.start()] if nxt else rest

    keystones = re.findall(r"^-\s+K\d+\b", section("Keystone sequence"), flags=re.M)
    if not keystones:
        report(
            "FAIL",
            f"{group_id} plan.md has no \"Keystone sequence\" section, or the section holds no"
            " `- Knn` rows (course_group_rules.md §4.3: for a progress group that table is the"
            " container)",
        )
        return
    ledger = section("Keystone change ledger")
    cut_rows = [
        row for row in re.findall(r"^\|.*\d{4}-\d{2}-\d{2}.*\|$", ledger, flags=re.M)
        if re.search(r"\|\s*cut\s*\|", row, flags=re.I)
    ]
    if len(keystones) + len(cut_rows) != frozen:
        report(
            "FAIL",
            f"{group_id} keystone sequence does not reconcile: {len(keystones)} current"
            f" keystones + {len(cut_rows)} logged cut rows ≠ the anchor {frozen}"
            " (§4.3: the only legal entry for a cut is one ledger row; adding a keystone must"
            " raise the anchor and leave an \"add\" row)",
        )


def check_groups(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    root = MAIN / "30_group"
    groups: list[tuple[str, Path, dict[str, str]]] = []
    if root.exists():
        for folder in sorted(path for path in root.iterdir() if path.is_dir() and re.fullmatch(r"G\d+", path.name)):
            plan = folder / "plan.md"
            if not plan.exists():
                report("FAIL", f"course group lacks plan.md: {folder.name}")
                continue
            for required in ("calendar.md", "review.md", "bindings"):
                if not (folder / required).exists():
                    report("FAIL", f"course group lacks {required}：{folder.name}")
            meta = frontmatter(plan)
            if meta.get("type") != "group" or meta.get("group_id") != folder.name:
                report("FAIL", f"group frontmatter does not match: {rel(plan)}")
            groups.append((folder.name, folder, meta))
    active = [item for item in groups if item[2].get("status") == "active"]
    expected = 0 if FLAVOR == "skeleton" else 1
    if len(active) != expected:
        report("FAIL", f"active group count should be {expected}, actual {len(active)}")
    for group_id, active_folder, meta in active:
        members = list_value(meta.get("course_members", "[]"))
        if not members:
            report("FAIL", f"active group has no course member: {group_id}")
        for course_id in members:
            if course_id not in courses:
                report("FAIL", f"{group_id} references a non-existent course: {course_id}")
                continue
            lifecycle = courses[course_id][1].get("lifecycle_status", "")
            if lifecycle in {"planned", "completed", "dropped"}:
                report("FAIL", f"{group_id} contains {lifecycle} course: {course_id}")
        current = meta.get("current_course", "")
        if current and current not in members:
            report("FAIL", f"{group_id} current_course is not among the members: {current}")
        check_container_mode(group_id, active_folder, meta, members, courses)
    for group_id, folder, meta in groups:
        mode = meta.get("container_mode", "")
        if not mode:
            report(
                "FAIL",
                f"{group_id} plan.md lacks container_mode (course_group_rules.md §4.1: the"
                " container shape is a choice, having a container is not)",
            )
        elif mode not in ALLOWED_CONTAINER_MODES:
            report(
                "FAIL",
                f"{group_id} container_mode is invalid: {mode}"
                f" (legal values are {sorted(ALLOWED_CONTAINER_MODES)})",
            )
        calendar = folder / "calendar.md"
        if calendar.is_file():
            cal_mode = frontmatter(calendar).get("container_mode", "")
            if mode and cal_mode and cal_mode != mode:
                report(
                    "FAIL",
                    f"{group_id} container_mode disagrees in two places:"
                    f" plan={mode} calendar={cal_mode}",
                )
            elif mode and not cal_mode:
                report(
                    "WARN",
                    f"{group_id} calendar.md does not declare container_mode (the trigger"
                    " anchor cannot decide which field set applies)",
                )
    group_ids = {group_id for group_id, _, _ in groups}
    binding_ids: set[str] = set()
    for binding in sorted(root.glob("G*/bindings/*.md")) if root.exists() else []:
        if binding.name.startswith("_"):
            continue
        meta = frontmatter(binding)
        required = {
            "type", "binding_id", "course_id", "group_id",
            "binding_status", "execution_mode",
        }
        if meta.get("type") != "binding" or not required.issubset(meta):
            report("FAIL", f"binding schema is incomplete: {rel(binding)}")
            continue
        binding_id = meta.get("binding_id", "")
        course_id = meta.get("course_id", "")
        group_id = meta.get("group_id", "")
        status = meta.get("binding_status", "")
        if not re.fullmatch(r"R\d{3}", binding_id):
            report("FAIL", f"binding_id is invalid: {rel(binding)} -> {binding_id}")
        if binding_id in binding_ids:
            report("FAIL", f"binding_id duplicated: {binding_id}")
        binding_ids.add(binding_id)
        if binding.name != f"{binding_id}_{course_id}.md":
            report("FAIL", f"binding filename disagrees with ID/course: {rel(binding)}")
        if group_id != binding.parents[1].name or group_id not in group_ids:
            report("FAIL", f"binding group reference does not close: {rel(binding)} -> {group_id}")
        if status not in ALLOWED_BINDING_STATES:
            report("FAIL", f"binding status is invalid: {rel(binding)} -> {status}")
        if meta.get("execution_mode") != "flexible":
            report("FAIL", f"binding execution_mode is invalid: {rel(binding)}")
        if course_id not in courses:
            report("FAIL", f"binding references a non-existent course: {rel(binding)}")
            continue
        course_type = frontmatter(courses[course_id][0] / "course.md").get("course_type", "")
        frozen_r002 = (
            binding_id == "R002"
            and course_id == "PHIL1101r"
            and group_id == "G01"
            and binding.name == "R002_PHIL1101r.md"
            and status == "idle"
            and meta.get("legacy_frozen") == "true"
            and course_type == "mastery"
        )
        if course_type not in {"project", "praxis"} and not frozen_r002:
            report("FAIL", f"binding binds an illegal course type: {rel(binding)} -> {course_type}")
        if meta.get("legacy_frozen") and not frozen_r002:
            report("FAIL", f"binding falsely claims legacy_frozen: {rel(binding)}")


def check_engagements_and_activities() -> None:
    engagements = MAIN / "10_student/engagements"
    if FLAVOR == "skeleton":
        for root in (MAIN / "10_student/engagements",):
            if not root.is_dir():
                report("FAIL", f"Skeleton lacks an empty-template domain: {rel(root)}")
                continue
            leaked = [
                path for path in root.iterdir()
                if not path.name.startswith("_")
            ]
            if leaked:
                report("FAIL", f"Skeleton empty-template domain contains an instance: {rel(root)}")
    if engagements.exists():
        for folder in sorted(path for path in engagements.iterdir() if path.is_dir()):
            carrier = folder / "engagement.md"
            if not carrier.exists():
                report("FAIL", f"Engagement lacks engagement.md: {rel(folder)}")
                continue
            meta = frontmatter(carrier)
            if meta.get("type") != "engagement" or meta.get("engagement_id") not in folder.name:
                report("FAIL", f"Engagement schema/ID mismatch: {rel(carrier)}")
            governance = meta.get("governance")
            if governance not in {"internal", "external"}:
                report("FAIL", f"Engagement governance is invalid: {rel(carrier)}")
            if governance == "external" and not meta.get("governance_source"):
                report("FAIL", f"externally governed Engagement lacks governance_source: {rel(carrier)}")
            if (folder / "field_practice.md").exists():
                report("FAIL", f"the old field_practice.md still exists: {rel(folder)}")
    activities = MAIN / "10_student/activities"
    if not activities.is_dir():
        report("FAIL", f"missing ActivityRecord domain: {rel(activities)}")
        return
    records: dict[str, Path] = {}
    sidecars: list[tuple[Path, str, str]] = []
    for entry in sorted(activities.iterdir()):
        if entry.is_symlink():
            report("FAIL", f"ActivityRecord domain forbids symlink/reparse: {rel(entry)}")
            continue
        if entry.is_file():
            if re.fullmatch(r"AR-.*\.md", entry.name):
                report("FAIL", f"ActivityRecord is still in the root directory: {rel(entry)}")
            elif not entry.name.startswith("_"):
                report("FAIL", f"ActivityRecord root directory has an illegal sidecar file: {rel(entry)}")
            continue
        if not entry.is_dir():
            report("FAIL", f"ActivityRecord root directory has an illegal object: {rel(entry)}")
            continue
        kind = entry.name
        if kind not in ALLOWED_ACTIVITY_KINDS:
            report("FAIL", f"ActivityRecord kind is not registered: {rel(entry)}")
            continue
        for path in sorted(entry.iterdir()):
            if path.is_symlink():
                report("FAIL", f"ActivityRecord kind forbids symlink/reparse: {rel(path)}")
                continue
            if path.is_dir():
                report("FAIL", f"ActivityRecord is nested too deeply: {rel(path)}")
                continue
            record_match = re.fullmatch(r"(AR-\d{4})_[^/\\]+\.md", path.name)
            sidecar_match = re.fullmatch(
                r"(AR-\d{4})\.(context|contributions)\.json",
                path.name,
            )
            if record_match:
                artifact_id = record_match.group(1)
                meta = frontmatter(path)
                if meta.get("type") != "activity_record":
                    report("FAIL", f"ActivityRecord type is invalid: {rel(path)}")
                if meta.get("activity_record_id") != artifact_id:
                    report("FAIL", f"ActivityRecord filename and frontmatter ID disagree: {rel(path)}")
                if meta.get("activity_kind") != kind:
                    report("FAIL", f"ActivityRecord parent directory and kind disagree: {rel(path)}")
                if artifact_id in records:
                    report(
                        "FAIL",
                        f"ActivityRecord ID repeats across kinds: {artifact_id} -> "
                        f"{rel(records[artifact_id])}, {rel(path)}",
                    )
                else:
                    records[artifact_id] = path
                if FLAVOR == "skeleton":
                    report("FAIL", f"Skeleton ActivityRecord empty container holds a real instance: {rel(path)}")
            elif sidecar_match:
                sidecars.append((path, sidecar_match.group(1), sidecar_match.group(2)))
                if FLAVOR == "skeleton":
                    report("FAIL", f"Skeleton ActivityRecord empty container holds a real sidecar: {rel(path)}")
            elif not path.name.startswith("_"):
                report("FAIL", f"ActivityRecord kind has an illegal sidecar file: {rel(path)}")
    for path, artifact_id, _sidecar_kind in sidecars:
        if artifact_id not in records:
            report("FAIL", f"ActivityRecord orphan sidecar：{rel(path)}")
    schema_dir = MAIN / "70_tools/contracts/reading_bridge_v1"
    schema_names = {
        "context": "t2ag.reading_context_source.v1",
        "contributions": "t2ag.reading_contribution_ledger.v1",
    }
    schemas: dict[str, dict[str, object]] = {}
    for sidecar_kind, schema_name in schema_names.items():
        schema_path = schema_dir / f"{schema_name}.schema.json"
        try:
            schema = load_json_strict(schema_path)
            if not isinstance(schema, dict):
                raise ContractError("schema must be an object")
            schemas[sidecar_kind] = schema
        except (ContractError, OSError) as exc:
            report("FAIL", f"reading bridge storage schema cannot be read: {rel(schema_path)} -> {exc}")
    global_contribution_ids: dict[str, Path] = {}
    global_receipt_ids: dict[str, Path] = {}
    for path, artifact_id, sidecar_kind in sidecars:
        if artifact_id not in records or sidecar_kind not in schemas:
            continue
        try:
            value = load_json_strict(path)
            validate_document(value, schemas[sidecar_kind])
            if not isinstance(value, dict):
                raise ContractError("storage carrier must be an object")
        except (ContractError, OSError) as exc:
            report("FAIL", f"ActivityRecord sidecar contract is invalid: {rel(path)} -> {exc}")
            continue
        if value.get("activity_record_id") != artifact_id:
            report("FAIL", f"ActivityRecord sidecar internal ID is inconsistent: {rel(path)}")
        if sidecar_kind == "context":
            if value.get("confirmed_by") != "student":
                report("FAIL", f"reading context source lacks manual confirmation: {rel(path)}")
            if value.get("target_reading_uri") is None and (
                value.get("course_id") is not None
                or value.get("reading_intents")
                or value.get("questions_or_observation_cues")
            ):
                report("FAIL", f"a context with no reading URI must be empty: {rel(path)}")
            continue
        processed = value.get("processed_events", [])
        contributions = value.get("contributions", [])
        outbox = value.get("receipt_outbox", [])
        event_ids: set[str] = set()
        local_contributions: set[str] = set()
        for row in contributions:
            contribution_id = row.get("contribution_id", "")
            payload = row.get("payload", {})
            if contribution_id in local_contributions:
                report("FAIL", f"reading contribution ledger has a duplicate object: {rel(path)} -> {contribution_id}")
            local_contributions.add(contribution_id)
            if contribution_id in global_contribution_ids:
                report(
                    "FAIL",
                    f"reading contribution ID repeats across ARs: {contribution_id} -> "
                    f"{rel(global_contribution_ids[contribution_id])}, {rel(path)}",
                )
            else:
                global_contribution_ids[contribution_id] = path
            if (
                not isinstance(payload, dict)
                or payload.get("contribution_id") != contribution_id
                or payload.get("target_activity_record_id") != artifact_id
                or payload.get("semantic_sha256") != semantic_sha256(payload)
                or contribution_id != "CON-" + semantic_sha256(payload)
                or payload.get("source_reading_uri") != payload.get("evidence_locator", {}).get("source_uri")
            ):
                report("FAIL", f"reading contribution payload/digest/target is invalid: {rel(path)} -> {contribution_id}")
        for row in processed:
            event_id = row.get("event_id", "")
            if event_id in event_ids:
                report("FAIL", f"reading contribution processed event is duplicated: {rel(path)} -> {event_id}")
            event_ids.add(event_id)
            matching = [
                item.get("payload", {})
                for item in contributions
                if item.get("contribution_id") == row.get("contribution_id")
            ]
            if (
                len(matching) != 1
                or row.get("semantic_sha256") != matching[0].get("semantic_sha256")
            ):
                report("FAIL", f"reading contribution processed event is dangling: {rel(path)} -> {event_id}")
        local_receipts: set[str] = set()
        for row in outbox:
            receipt_id = row.get("receipt_id", "")
            payload = row.get("payload", {})
            ack = row.get("ack_result")
            if receipt_id in local_receipts:
                report("FAIL", f"reading receipt outbox has a duplicate ID: {rel(path)} -> {receipt_id}")
            local_receipts.add(receipt_id)
            if receipt_id in global_receipt_ids:
                report(
                    "FAIL",
                    f"reading receipt ID repeats across ARs: {receipt_id} -> "
                    f"{rel(global_receipt_ids[receipt_id])}, {rel(path)}",
                )
            else:
                global_receipt_ids[receipt_id] = path
            if (
                not isinstance(payload, dict)
                or payload.get("receipt_id") != receipt_id
                or payload.get("event_id") != receipt_id
                or payload.get("target_activity_record_id") != artifact_id
                or payload.get("semantic_sha256") != semantic_sha256(payload)
                or payload.get("contribution_id") not in local_contributions
                or not str(payload.get("receipt_target_uri", "")).startswith("reading://note/")
            ):
                report("FAIL", f"reading receipt outbox payload/digest/target is invalid: {rel(path)} -> {receipt_id}")
            if (row.get("status") == "pending") != (ack is None):
                report("FAIL", f"reading receipt outbox status/ack disagree: {rel(path)} -> {receipt_id}")
            if isinstance(ack, dict):
                response = {
                    key: ack.get(key)
                    for key in ("receipt_id", "semantic_sha256", "result")
                }
                if (
                    response["receipt_id"] != receipt_id
                    or response["semantic_sha256"] != payload.get("semantic_sha256")
                    or ack.get("response_sha256")
                    != hashlib.sha256(canonical_json_bytes(response)).hexdigest()
                ):
                    report("FAIL", f"reading receipt ack binding is invalid: {rel(path)} -> {receipt_id}")


def check_question_banks(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    for course_id, (folder, _) in courses.items():
        bank = folder / "question_bank.md"
        if not bank.exists():
            continue
        content = read(bank)
        if "QUESTION_BANK_TEMPLATE_V2" not in content:
            report("FAIL", f"question bank is not upgraded to V2: {course_id}")
        for match in field_line_re("状态", r"([A-Za-z_]+)").finditer(content):
            if match.group(1) not in ALLOWED_QUESTION_STATES:
                report("FAIL", f"question status is invalid: {course_id} -> {match.group(1)}")


def check_knowledge_ledgers(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    for course_id, (folder, _) in courses.items():
        question_bank = folder / "question_bank.md"
        if question_bank.is_file():
            content = read(question_bank)
            body = without_fenced_code(content)
            ids = [int(value) for value in re.findall(r"^###\s+Q-(\d{4})(?:\s*｜.*)?$", body, re.MULTILINE)]
            if len(ids) != len(set(ids)):
                report("FAIL", f"question ID duplicated: {course_id}")
            next_id = re.search(r"^next_id:\s*(\d+)\s*$", content, re.MULTILINE)
            if not next_id:
                report("FAIL", f"question bank lacks next_id: {course_id}")
            elif ids and int(next_id.group(1)) <= max(ids):
                report("FAIL", f"question bank next_id does not exceed the largest Q ID: {course_id}")

        mistake_bank = folder / "mistake_bank.md"
        if not mistake_bank.is_file():
            continue
        content = read(mistake_bank)
        # LV-5: the three section headings are prose and are spelled per edition.
        for section in ("活跃知识点", "维护知识点", "陈年知识点"):
            if not any(f"## {sp}" in content for sp in marker_spellings(section)):
                report("FAIL", f"mistake bank lacks the section ## {section}: {course_id}")
        body = without_fenced_code(content)
        entries = list(re.finditer(r"^###\s+M-(\d{4})\s*$", body, re.MULTILINE))
        ids = [int(match.group(1)) for match in entries]
        if len(ids) != len(set(ids)):
            report("FAIL", f"mistake ID duplicated: {course_id}")
        next_id = re.search(r"^next_id:\s*(\d+)\s*$", content, re.MULTILINE)
        if not next_id:
            report("FAIL", f"mistake bank lacks next_id: {course_id}")
        elif ids and int(next_id.group(1)) <= max(ids):
            report("FAIL", f"mistake bank next_id does not exceed the largest M ID: {course_id}")
        for index, match in enumerate(entries):
            end = entries[index + 1].start() if index + 1 < len(entries) else len(body)
            block = body[match.end():end]
            state = field_line_re("状态", r"([a-z_]+)").search(block)
            if not state or state.group(1) not in ALLOWED_MISTAKE_STATES:
                report("FAIL", f"mistake status is missing or invalid: {course_id}/M-{match.group(1)}")
            for field in (
                "知识点键", "当前周期", "当前周期摘要", "陈年连续正确",
                "最近陈年复习卷", "下次陈年日历检查",
            ):
                if not re.search(rf"^-\s*{re.escape(field)}[：:]\s*.+$", block, re.MULTILINE):
                    report("FAIL", f"mistake entry lacks{field}：{course_id}/M-{match.group(1)}")

    reasoning = MAIN / "10_student/profile/reasoning_patterns.md"
    if reasoning.is_file():
        body = without_fenced_code(read(reasoning))
        ids = re.findall(r"^###\s+(RP-\d{4})(?:\s+.*)?$", body, re.MULTILINE)
        if len(ids) != len(set(ids)):
            report("FAIL", "reasoning pattern ID duplicated")
        entries = list(re.finditer(r"^###\s+(RP-\d{4})(?:\s+.*)?$", body, re.MULTILINE))
        for index, match in enumerate(entries):
            end = entries[index + 1].start() if index + 1 < len(entries) else len(body)
            block = body[match.end():end]
            state = field_line_re(
                "状态", r"(观察中|已确认|已退役|observing|confirmed|retired)"
            ).search(block)
            if not state:
                report("FAIL", f"reasoning pattern lacks a valid status: {match.group(1)}")


def check_exam_banks(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    """Runtime: enforce exam-ledger shape and assessment-pool isolation.

    Empty banks are a valid cold-start state.  Isolation is FAIL because a leaked
    assessment problem burns the paper; registration and metadata drift are WARN.
    """
    decay_keys = (
        ("domain", "域"), ("timing", "时机"),
        ("attribution layer", "归因层"), ("consumer", "消费方"),
        ("exit", "退出"), ("re-entry", "再入"),
    )
    for course_id, (folder, _) in courses.items():
        exam_root = folder / "_exam"
        if not exam_root.is_dir():
            continue
        ledger = exam_root / "exam_ledger.md"
        if not ledger.is_file():
            report("FAIL", f"_exam/ exists but exam_ledger.md is missing: {course_id}")
        else:
            meta = frontmatter(ledger)
            if meta.get("truth_scope") != "exam_settlement":
                report("FAIL", f"exam_ledger truth_scope must be exam_settlement: {course_id}")
            content = read(ledger)
            body = without_fenced_code(content)
            has_decay = "【模式】复利回路·衰减" in body or "retire loop" in body.lower() and "decay" in body.lower()
            if not has_decay:
                report("FAIL", f"exam_ledger lacks the retire-loop decay marker: {course_id}")
            else:
                missing = [aliases[0] for aliases in decay_keys if not any(f"{key}=" in body for key in aliases)]
                if missing:
                    report("FAIL", f"exam_ledger decay parameters lack keys {missing}: {course_id}")
            state = re.search(
                r"^\|\s*(?:Exam debt status|考核债状态)\s*\|\s*`([a-z_]+)`",
                body, re.MULTILINE | re.IGNORECASE,
            )
            if not state:
                report("FAIL", f"exam_ledger lacks exam-debt status: {course_id}")
            elif state.group(1) not in ALLOWED_EXAM_DEBT_STATES:
                report("FAIL", f"illegal exam-debt status: {course_id} -> {state.group(1)}")
            ids = [int(value) for value in re.findall(r"^###\s+EX-(\d{4})", body, re.MULTILINE)]
            if len(ids) != len(set(ids)):
                report("FAIL", f"duplicate exam sitting ID: {course_id}")
            next_id = re.search(r"^next_id:\s*(\d+)\s*$", content, re.MULTILINE)
            if not next_id:
                report("FAIL", f"exam_ledger lacks next_id: {course_id}")
            elif ids and int(next_id.group(1)) <= max(ids):
                report("FAIL", f"exam_ledger next_id does not exceed the largest EX ID: {course_id}")

        index_file = exam_root / "index.md"
        if not index_file.is_file():
            report("FAIL", f"_exam/ exists but index.md is missing: {course_id}")
            continue
        registered: dict[str, str] = {}
        for line in without_fenced_code(read(index_file)).splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 10:
                continue
            paper_id = cells[0]
            if not paper_id or paper_id in {"Paper ID", "卷ID"} or set(paper_id) <= set("-: "):
                continue
            registered[paper_id] = cells[8]
        papers_root = exam_root / "papers"
        folders = sorted(entry.name for entry in papers_root.iterdir() if entry.is_dir()) if papers_root.is_dir() else []
        if not registered and not folders:
            continue
        for name in folders:
            if name not in registered:
                report("WARN", f"paper folder is not registered in index.md: {course_id}/{name}")
                continue
            meta_file = papers_root / name / "meta.md"
            if not meta_file.is_file():
                report("WARN", f"paper folder lacks meta.md: {course_id}/{name}")
                continue
            meta_text = read(meta_file)
            absent = [aliases[0] for aliases in EXAM_META_COLUMNS if not any(label in meta_text for label in aliases)]
            if absent:
                report("WARN", f"meta.md lacks columns {absent}: {course_id}/{name}")
        for paper_id in registered:
            if paper_id not in folders:
                report("WARN", f"registered paper has no paper folder: {course_id}/{paper_id}")
        assessment = {
            paper_id for paper_id, pool in registered.items()
            if "assessment" in pool.lower() or "考核" in pool
        }
        for space in ("lessons", "exercises"):
            space_root = folder / space
            if not space_root.is_dir():
                continue
            for path in sorted(space_root.rglob("*.md")):
                text = without_fenced_code(read(path))
                for paper_id in sorted(assessment):
                    if re.search(rf"{re.escape(paper_id)}\s*#\s*\S", text):
                        report(
                            "FAIL",
                            f"assessment-pool problem reference leaked into teaching: "
                            f"{course_id} -> {paper_id} @ {path.relative_to(folder)}",
                        )


def _validate_project_closure_record(
    course_id: str,
    node_id: str,
    mode: str,
    evidence: str,
) -> None:
    reference = evidence.strip().strip("` ")
    match = re.fullmatch(
        r"(main/[^#`\s]+\.md)#(VER-[A-Za-z0-9][A-Za-z0-9-]*)",
        reference,
    )
    if not match:
        report("FAIL", f"a completed project node's closure evidence does not reference an actual acceptance record: {node_id or course_id}")
        return
    target = (ROOT / match.group(1)).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        report("FAIL", f"the project acceptance record reference goes outside the release root: {node_id or course_id}")
        return
    if not target.is_file():
        report("FAIL", f"the project acceptance record file does not exist: {node_id or course_id} -> {match.group(1)}")
        return
    record_id = match.group(2)
    record_match = re.search(
        rf"^#{{3,6}}[ \t]+{re.escape(record_id)}(?:[ \t]+[^\r\n]*)?[ \t]*\r?\n"
        rf"(.*?)(?=^#{{1,6}}[ \t]+|\Z)",
        read(target),
        re.MULTILINE | re.DOTALL,
    )
    if not record_match:
        report("FAIL", f"the acceptance record referenced by the closure evidence does not exist: {node_id or course_id} -> {record_id}")
        return
    body = record_match.group(1)

    def field(label: str) -> str:
        value = re.search(
            rf"^-\s*{re.escape(label)}[：:]\s*(\S.*)$",
            body,
            re.MULTILINE,
        )
        return value.group(1).strip() if value else ""

    def field_any(label: str) -> str:
        """`field`, tried against every language spelling of the label (LV-5)."""
        for spelling in marker_spellings(label):
            found = field(spelling)
            if found:
                return found
        return ""

    if field_any("节点").strip("` ") != node_id:
        report("FAIL", f"the project acceptance record node does not match: {node_id or course_id} -> {record_id}")
    if field_any("验证模式").strip("` ") != mode:
        report("FAIL", f"the project acceptance record mode does not match: {node_id or course_id} -> {record_id}")
    if field_any("结论") != "passed":
        report("FAIL", f"the project acceptance record did not pass: {node_id or course_id} -> {record_id}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", field_any("验收日期")):
        report("FAIL", f"the project acceptance record lacks a valid date: {node_id or course_id} -> {record_id}")
    required_steps = (
        ("可复现性检查", "客观验收", "讲解口试", "盲改挑战", "留档")
        if mode == "A"
        else ("指标对账", "现场独立验证", "留档")
    )

    def has_actual_summary(value: str) -> bool:
        result = re.fullmatch(r"passed\s*[·；;:：]\s*(.+?)\s*", value)
        return bool(result and any(character.isalnum() for character in result.group(1)))

    incomplete = [
        label
        for label in required_steps
        if not has_actual_summary(field(label))
    ]
    if incomplete:
        report(
            "FAIL",
            f"a project acceptance record step is not closed (missing passed + an actual-result summary): "
            f"{node_id or course_id} -> {incomplete}",
        )


def check_project_verification(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    for course_id, (folder, progress_meta) in courses.items():
        if frontmatter(folder / "course.md").get("course_type") != "project":
            continue
        if progress_meta.get("lifecycle_status") == "planned":
            continue
        rows = table_after_heading(
            cached_progress_content(course_id, folder),
            "Completion nodes",
        )
        if not rows:
            report("FAIL", f"the project course lacks a Completion nodes table: {course_id}")
            continue
        # LV-5: the column may be spelled in any shipped edition.  `issubset` on the
        # raw header keys would pass zh-CN and FAIL a correctly-translated table, so
        # presence is resolved through the registry exactly as `row_value` below is.
        required_columns = ("验收标准", "关闭证据")
        if any(cell_index(list(rows[0]), name) < 0 for name in required_columns):
            report("FAIL", f"project-course Completion nodes do not separate acceptance criteria from closure evidence: {course_id}")
            continue
        for row in rows:
            node_id = row.get("node_id", "")
            status = row_value(row, "状态")
            mode = row_value(row, "验证模式")
            standard = row_value(row, "验收标准")
            evidence = row_value(row, "关闭证据")
            if standard.strip("` ") in {"", "-", "—", "NONE"}:
                report("FAIL", f"the project node lacks acceptance criteria: {node_id or course_id}")
            if status in {"in_progress", "completed"} and mode not in ALLOWED_PROJECT_MODES:
                report("WARN", f"a started project node lacks a verification mode: {node_id or course_id}")
            elif mode and mode not in ALLOWED_PROJECT_MODES:
                report("FAIL", f"the project node verification mode is invalid: {node_id or course_id} -> {mode}")
            if status == "completed" and evidence.strip("` ") in {"", "-", "—", "NONE"}:
                report("FAIL", f"a completed project node lacks closure evidence: {node_id or course_id}")
            elif status == "completed":
                _validate_project_closure_record(course_id, node_id, mode, evidence)
            elif evidence.strip("` ") not in {"", "-", "—", "NONE"}:
                report("FAIL", f"an unfinished project node has pre-filled closure evidence: {node_id or course_id}")


def exercise_problem_statements(
    content: str,
    exercise_id: str,
) -> dict[str, str]:
    """Return the final problem-statement field of each stable problem section."""
    headings = list(re.finditer(
        rf"^##\s+({re.escape(exercise_id)}-Q\d{{3}})\s*$",
        content,
        re.MULTILINE,
    ))
    result: dict[str, str] = {}
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        body = content[heading.end():end]
        statement = re.search(
            r"^-\s*(?:题面|Problem statement)[：:]\s*(.*)\Z",
            body,
            re.MULTILINE | re.DOTALL,
        )
        if statement:
            result[heading.group(1)] = re.sub(
                r"\s+",
                " ",
                statement.group(1).strip(),
            )
    return result


def artifact_registry_by_id() -> dict[str, dict[str, object]]:
    path = MAIN / "70_tools/artifact_registry.json"
    try:
        payload = json.loads(read(path))
    except (OSError, json.JSONDecodeError):
        return {}
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        return {}
    return {
        str(item.get("artifact_id")): item
        for item in artifacts
        if isinstance(item, dict) and item.get("artifact_id")
    }


def validated_migration_evidence(
    expected_target_kind: str,
) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    """Load the complete, report-bound 0.2.0 migration operation manifest."""
    manifest_path = MAIN / "60_journal/migration_020_operations.json"
    report_path = MAIN / "60_journal/migration_020_report.json"
    errors: list[str] = []
    try:
        manifest = json.loads(read(manifest_path))
        migration_report = json.loads(read(report_path))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [], [f"the formal migration evidence cannot be read: {exc}"]
    if not isinstance(manifest, dict) or not isinstance(migration_report, dict):
        return {}, [], ["the top level of the formal migration evidence must be an object"]

    if migration_report.get("status") != "applied":
        errors.append("migration report status must be applied")
    applied_count = migration_report.get("applied_count")
    if not isinstance(applied_count, int) or applied_count <= 0:
        errors.append("migration report applied_count is missing or invalid")
    duplicates = migration_report.get("post_apply_duplicate_active_canonicals")
    if not isinstance(duplicates, list) or duplicates:
        errors.append("migration report post-apply canonical evidence is missing or non-empty")

    manifest_ref = migration_report.get("operation_manifest")
    if not isinstance(manifest_ref, dict):
        errors.append("the migration report lacks the operation_manifest reference block")
        manifest_ref = {}
    if manifest_ref.get("path") != "main/60_journal/migration_020_operations.json":
        errors.append("the operation_manifest path in the migration report is missing or invalid")
    if not isinstance(manifest_ref.get("operation_count"), int):
        errors.append("the operation_manifest operation_count in the migration report is missing or invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest_ref.get("sha256", ""))):
        errors.append("the operation_manifest sha256 in the migration report is missing or invalid")
    elif (
        manifest_ref.get("sha256")
        != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ):
        errors.append("operation_manifest SHA drift in the migration report")

    if manifest.get("schema_version") != "T2AG-MIGRATION-OPERATIONS-1":
        errors.append("migration per-operation manifest schema_version is missing or invalid")
    if manifest.get("target_kind") != expected_target_kind:
        errors.append(
            "migration per-operation manifest target_kind drift: "
            f"expected={expected_target_kind} actual={manifest.get('target_kind')}"
        )
    if not isinstance(manifest.get("evidence_source"), str) or not str(
        manifest.get("evidence_source", "")
    ).strip():
        errors.append("the migration per-operation manifest lacks evidence_source")

    rows_value = manifest.get("operations")
    rows = (
        rows_value
        if isinstance(rows_value, list)
        and all(isinstance(row, dict) for row in rows_value)
        else []
    )
    if rows_value != rows:
        errors.append("migration per-operation manifest operations must be a list of objects")
    manifest_count = manifest.get("operation_count")
    if (
        not isinstance(manifest_count, int)
        or manifest_count <= 0
        or manifest_count != len(rows)
        or manifest_count != applied_count
        or manifest_count != manifest_ref.get("operation_count")
    ):
        errors.append("the migration per-operation manifest count disagrees with apply/report")
    if [row.get("sequence") for row in rows] != list(range(1, len(rows) + 1)):
        errors.append("migration per-operation manifest sequence is not contiguous")

    for row in rows:
        sequence = row.get("sequence")
        for key in ("kind", "target", "disposition"):
            if not isinstance(row.get(key), str) or not str(row.get(key)).strip():
                errors.append(
                    f"migration per-operation manifest fields are incomplete: sequence={sequence} key={key}"
                )
        sources = row.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(
                f"migration per-operation manifest sources are missing: sequence={sequence}"
            )
        else:
            for source in sources:
                if (
                    not isinstance(source, dict)
                    or not isinstance(source.get("path"), str)
                    or not source.get("path")
                    or not isinstance(source.get("bytes"), int)
                    or source.get("bytes", -1) < 0
                    or not re.fullmatch(
                        r"[0-9a-f]{64}", str(source.get("sha256", "")),
                    )
                ):
                    errors.append(
                        f"migration per-operation manifest source is invalid: sequence={sequence}"
                    )
                    break
        if row.get("outcome") != "applied":
            errors.append(
                f"migration per-operation manifest outcome is not applied: sequence={sequence}"
            )
        post = row.get("post_target")
        if (
            not isinstance(post, dict)
            or post.get("path") != row.get("target")
            or not isinstance(post.get("bytes"), int)
            or post.get("bytes", -1) < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(post.get("sha256", "")))
        ):
            errors.append(
                f"migration per-operation manifest post_target is invalid: sequence={sequence}"
            )
    return manifest, rows, errors


def lite_manifest_sha_for_path(relative: str) -> str:
    """Resolve an intentionally omitted Lite binary through a bound manifest."""
    _, rows, errors = validated_migration_evidence("main")
    if errors:
        return ""
    matches = [
        operation.get("post_target", {})
        for operation in rows
        if operation.get("post_target", {}).get("path") == relative
    ]
    if len(matches) != 1:
        return ""
    sha = matches[0].get("sha256", "")
    return sha if re.fullmatch(r"[0-9a-f]{64}", sha) else ""


def check_exercises(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    registry = artifact_registry_by_id()
    for course_id, (folder, progress_meta) in courses.items():
        post_022 = (folder / "activity_ledger.md").is_file()
        exercise_root = folder / "exercises"
        if not exercise_root.is_dir():
            continue
        units = sorted(
            path for path in exercise_root.iterdir()
            if path.is_dir() and not path.name.startswith("_")
        )
        unit_names = {
            unit.name
            for unit in units
            if re.fullmatch(r"exercise\d{2,}", unit.name)
            or (not post_022 and re.fullmatch(r"U\d{4}", unit.name))
        }
        lesson_root = folder / "lessons"
        lessons = {
            lesson_dir.name: lesson_dir / f"{lesson_dir.name}.md"
            for lesson_dir in sorted(lesson_root.iterdir())
            if (
                lesson_root.is_dir()
                and lesson_dir.is_dir()
                and re.fullmatch(r"lesson\d+", lesson_dir.name)
                and (lesson_dir / f"{lesson_dir.name}.md").is_file()
            )
        } if lesson_root.is_dir() else {}
        activity_rows: list[dict[str, str]] = []
        rows_by_lesson: dict[str, list[dict[str, str]]] = {}
        rows_by_unit: dict[str, list[dict[str, str]]] = {}
        activity_map_ready = False
        if progress_meta.get("course_driver") == "textbook" and (lessons or units):
            activity_map = folder / "activity_map.md"
            activity_meta = frontmatter(activity_map)
            if not activity_map.is_file():
                report("FAIL", f"a textbook course has Lesson/Exercise but lacks an activity map: {course_id}")
            elif (
                activity_meta.get("type") != "course_activity_map"
                or activity_meta.get("course_id") != course_id
            ):
                report("FAIL", f"course activity map frontmatter does not match: {rel(activity_map)}")
            else:
                activity_rows = heading_rows(read(activity_map), "内容组连接表")
                required_columns = {
                    "content_group_id", "source_scope", "lesson_ids",
                    "exercise_ids",
                }
                if not activity_rows or not required_columns.issubset(activity_rows[0]):
                    report("FAIL", f"the course activity map cannot be parsed or lacks a column: {rel(activity_map)}")
                    activity_rows = []
                else:
                    activity_map_ready = True
                seen_groups: set[str] = set()
                for row in activity_rows:
                    group_id = row.get("content_group_id", "").strip("` ")
                    if not re.fullmatch(rf"{re.escape(course_id)}-B\d+-C\d+-S\d+", group_id):
                        report("FAIL", f"activity map ContentGroup ID is invalid: {course_id} -> {group_id}")
                    if group_id in seen_groups:
                        report("FAIL", f"activity map ContentGroup duplicated: {course_id} -> {group_id}")
                    seen_groups.add(group_id)
                    lesson_ids = reference_list(row.get("lesson_ids", ""))
                    exercise_ids = reference_list(row.get("exercise_ids", ""))
                    if len(lesson_ids) != len(set(lesson_ids)):
                        report(
                            "FAIL",
                            f"activity map lesson_ids duplicated: {course_id} -> {group_id}",
                        )
                    if len(exercise_ids) != len(set(exercise_ids)):
                        report(
                            "FAIL",
                            f"activity map exercise_ids duplicated: {course_id} -> {group_id}",
                        )
                    if not lesson_ids and not exercise_ids:
                        report("FAIL", f"an activity map content group has no learning activity at all: {course_id} -> {group_id}")
                    for lesson_id in lesson_ids:
                        rows_by_lesson.setdefault(lesson_id, []).append(row)
                        lesson = folder / "lessons" / lesson_id / f"{lesson_id}.md"
                        lesson_meta = frontmatter(lesson)
                        if (
                            not lesson.is_file()
                            or lesson_meta.get("type") != "lesson"
                            or lesson_meta.get("course_id") != course_id
                            or lesson_meta.get("lesson_id") != lesson_id
                        ):
                            report("FAIL", f"activity map Lesson is dangling or its frontmatter does not match: {course_id} -> {lesson_id}")
                    for exercise_id in exercise_ids:
                        rows_by_unit.setdefault(exercise_id, []).append(row)
                        if exercise_id not in unit_names:
                            report("FAIL", f"activity map Exercise is dangling: {course_id} -> {exercise_id}")
        for lesson_id, lesson in lessons.items():
            lesson_meta = frontmatter(lesson)
            lesson_content = read(lesson)
            if (
                lesson_meta.get("type") != "lesson"
                or lesson_meta.get("course_id") != course_id
                or lesson_meta.get("lesson_id") != lesson_id
            ):
                report("FAIL", f"Lesson frontmatter does not match: {rel(lesson)}")
            if "T2AG_GENERATED:LESSON_PROGRESS" in lesson_content:
                report("FAIL", f"Lesson contains an ownerless GENERATED progress block: {rel(lesson)}")
            retired_fields = sorted(
                field
                for field in (
                    "exercise_id", "exercise_ids", "exercise_ref",
                    "exercise_refs", "exercise_unit_id",
                    "exercise_unit_ids", "exercise_session_id",
                    "exercise_session_ids", "exercise_session_ref",
                    "exercise_session_refs", "session_id", "session_ids",
                )
                if field in lesson_meta
            )
            if retired_fields:
                report(
                    "FAIL",
                    f"Lesson uses a retired activity-ownership field: {rel(lesson)} -> {retired_fields}",
                )
            declared_group_ids = reference_list(lesson_meta.get("content_group_ids", ""))
            if len(declared_group_ids) != len(set(declared_group_ids)):
                report("FAIL", f"Lesson content_group_ids duplicated: {rel(lesson)}")
            if progress_meta.get("course_driver") != "textbook":
                continue
            if not activity_map_ready:
                continue
            link_rows = rows_by_lesson.get(lesson_id, [])
            if not link_rows:
                report("FAIL", f"Lesson does not appear in the activity map: {rel(lesson)}")
            expected_groups = {
                row.get("content_group_id", "").strip("` ")
                for row in link_rows
            }
            declared_groups = set(declared_group_ids)
            if declared_groups != expected_groups:
                report(
                    "FAIL",
                    f"Lesson drifts from the activity map ContentGroup: {lesson_id} -> "
                    f"declared={sorted(declared_groups)} expected={sorted(expected_groups)}",
                )

        completion_rows = (
            table_after_heading(
                cached_progress_content(course_id, folder),
                "Completion nodes",
            )
            if (folder / "progress.md").is_file()
            else []
        )
        completion_node_ids = {
            row.get("node_id", "").strip("` ")
            for row in completion_rows
            if row.get("node_id", "").strip("` ")
        }
        for unit in units:
            if not (
                re.fullmatch(r"exercise\d{2,}", unit.name)
                or (not post_022 and re.fullmatch(r"U\d{4}", unit.name))
            ):
                report("FAIL", f"exercise unit ID is invalid: {rel(unit)}")
                continue
            exercise = unit / "exercise.md"
            exercise_meta = frontmatter(exercise)
            if (
                not exercise.is_file()
                or exercise_meta.get("type") != "exercise"
                or exercise_meta.get("course_id") != course_id
                or exercise_meta.get("exercise_id") != unit.name
            ):
                report("FAIL", f"Exercise main carrier is missing or its frontmatter does not match: {rel(unit)}")
            retired_fields = sorted(
                field
                for field in (
                    "lesson_id", "lesson_ids", "exercise_session_id",
                    "exercise_session_ids", "exercise_session_refs",
                    "lesson_ref", "lesson_refs", "exercise_session_ref",
                    "session_id", "session_ids",
                )
                if field in exercise_meta
            )
            if retired_fields:
                report(
                    "FAIL",
                    f"Exercise uses a retired activity-ownership field: {unit.name} -> {retired_fields}",
                )
            sessions = unit / "sessions"
            session_objects = [
                path for path in unit.rglob("*.md")
                if path != exercise and frontmatter(path).get("type") == "exercise_session"
            ]
            if sessions.is_dir() or session_objects:
                location = sessions if sessions.is_dir() else session_objects[0]
                report("FAIL", f"Exercise contains a retired ExerciseSession: {rel(location)}")
            declared_group_ids = reference_list(exercise_meta.get("content_group_ids", ""))
            if len(declared_group_ids) != len(set(declared_group_ids)):
                report("FAIL", f"Exercise content_group_ids duplicated: {unit.name}")
            declared_groups = set(declared_group_ids)
            problems = unit / "problems.md"
            if not problems.is_file():
                report("FAIL", f"exercise unit lacks problems.md: {rel(unit)}")
                continue
            meta = frontmatter(problems)
            if (
                meta.get("type") != "exercise_problem_set"
                or meta.get("course_id") != course_id
                or meta.get("exercise_id") != unit.name
            ):
                report("FAIL", f"Exercise problem-set frontmatter does not match: {rel(problems)}")
            content_group_id = meta.get("content_group_id", "")
            source = ROOT / "__missing__"
            if progress_meta.get("course_driver") == "textbook":
                if not re.fullmatch(rf"{re.escape(course_id)}-B\d+-C\d+-S\d+", content_group_id):
                    report("FAIL", f"textbook exercise unit content_group_id is invalid: {rel(problems)}")
                link_rows = rows_by_unit.get(unit.name, [])
                linked_groups = {row.get("content_group_id", "").strip("` ") for row in link_rows}
                if not link_rows:
                    report("FAIL", f"Exercise does not appear in the activity map: {rel(problems)}")
                if linked_groups != declared_groups:
                    report("FAIL", f"Exercise drifts from the activity map ContentGroup: {unit.name}")
                if content_group_id not in declared_groups:
                    report("FAIL", f"the problem set content_group_id is not declared by the Exercise: {unit.name}")
                source_fields = (
                    "source_artifact_id", "source_path", "source_locator",
                    "source_sha256",
                )
                missing_source_fields = [
                    field for field in source_fields if not meta.get(field)
                ]
                if missing_source_fields:
                    report(
                        "FAIL",
                        f"textbook exercise lacks the persistent problem source field: {rel(problems)} -> "
                        f"{missing_source_fields}",
                    )
                source_artifact_id = meta.get("source_artifact_id", "")
                source_path = meta.get("source_path", "")
                source_locator = meta.get("source_locator", "")
                source_sha = meta.get("source_sha256", "")
                source: Path | None = None
                try:
                    source = resolve_course_book_path(
                        ROOT, course_id, source_path, must_exist=True,
                    )
                except ActivityContractError as exc:
                    for message in exc.errors:
                        report(
                            "FAIL",
                            f"textbook exercise persistent problem source path is invalid: {unit.name} -> {message}",
                        )
                if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
                    report("FAIL", f"textbook exercise source_sha256 is invalid: {unit.name}")
                elif source is not None and hashlib.sha256(
                    source.read_bytes()
                ).hexdigest() != source_sha:
                    report("FAIL", f"textbook exercise persistent problem source SHA drift: {unit.name}")
                artifact = registry.get(source_artifact_id, {})
                if (
                    artifact.get("status") != "active"
                    or artifact.get("canonical_path") != source_path
                ):
                    report(
                        "FAIL",
                        f"textbook exercise problem source does not resolve to an active registry canonical: "
                        f"{unit.name} -> {source_artifact_id or 'missing'}",
                    )
                if source is not None:
                    source_meta = frontmatter(source)
                    if (
                        source_meta.get("type") != "verified_source_excerpt"
                        or source_meta.get("artifact_id") != source_artifact_id
                        or source_meta.get("course_id") != course_id
                        or source_meta.get("content_group_id") != content_group_id
                        or source_meta.get("source_locator") != source_locator
                        or source_meta.get("lifecycle") != "persistent"
                    ):
                        report(
                            "FAIL",
                            f"textbook exercise persistent problem source frontmatter does not match: {rel(source)}",
                        )
                    source_document = source_meta.get("source_document", "")
                    source_document_sha = source_meta.get(
                        "source_document_sha256", ""
                    )
                    if not re.fullmatch(r"[0-9a-f]{64}", source_document_sha):
                        report(
                            "FAIL",
                            f"textbook exercise source document source_document_sha256 is invalid: {unit.name}",
                        )
                    document: Path | None = None
                    try:
                        document = resolve_course_book_path(
                            ROOT,
                            course_id,
                            source_document,
                            must_exist=FLAVOR != "lite",
                        )
                    except ActivityContractError as exc:
                        for message in exc.errors:
                            report(
                                "FAIL",
                                f"textbook exercise source document path is invalid: {unit.name} -> {message}",
                            )
                    if (
                        document is not None
                        and document.is_file()
                        and re.fullmatch(r"[0-9a-f]{64}", source_document_sha)
                        and hashlib.sha256(document.read_bytes()).hexdigest()
                        != source_document_sha
                    ):
                        report(
                            "FAIL",
                            f"textbook exercise source document SHA drift: {unit.name}",
                        )
                    if (
                        FLAVOR == "lite"
                        and document is not None
                        and not document.is_file()
                        and lite_manifest_sha_for_path(source_document)
                        != source_document_sha
                    ):
                        report(
                            "FAIL",
                            "A textbook source document omitted from Lite is not proven by a hash-bound manifest: "
                            f"{unit.name}",
                        )
            content = read(problems)
            problem_heading = (
                r"(?:U\d{4}-Q\d{3}|exercise\d{2,}-Q\d{3})"
            )
            entries = re.split(
                rf"^##\s+{problem_heading}\s*$", content, flags=re.MULTILINE
            )[1:]
            headings = re.findall(
                rf"^##\s+({problem_heading})\s*$", content, re.MULTILINE
            )
            if not entries or len(entries) != len(headings):
                report("FAIL", f"exercise entry structure cannot be parsed: {rel(problems)}")
                continue
            if len(headings) != len(set(headings)):
                report("FAIL", f"exercise problem_id duplicated: {rel(problems)}")
            if progress_meta.get("course_driver") == "textbook":
                source_order = list_value(meta.get("source_order", "[]"))
                teaching_sequence = list_value(meta.get("teaching_sequence", "[]"))
                for label, sequence in (
                    ("source_order", source_order),
                    ("teaching_sequence", teaching_sequence),
                ):
                    if len(sequence) != len(set(sequence)) or set(sequence) != set(headings):
                        report("FAIL", f"textbook exercise {label} does not fully cover the problems: {rel(problems)}")
                if source_order and source_order != headings:
                    report("FAIL", f"textbook exercise source_order disagrees with the problem-statement order: {rel(problems)}")
                if teaching_sequence != source_order and not meta.get("sequence_rationale"):
                    report("FAIL", f"textbook exercise reordering lacks sequence_rationale: {rel(problems)}")
            bare_numbers: list[int] = []
            for heading, entry in zip(headings, entries):
                required = (
                    "题号", "来源页", "难度", "依赖 completion node",
                    "状态", "错误级别", "题面",
                )
                # LV-5: each label is spelled per edition; resolve through the registry.
                missing = [
                    field for field in required
                    if not re.search(
                        rf"^-\s*(?:{marker_alternation(field)})[：:]", entry, re.MULTILINE
                    )
                ]
                if missing:
                    report("FAIL", f"exercise field is missing: {heading} -> {missing}")
                number = field_line_re("题号", r"(\d+)").search(entry)
                if not number:
                    report("FAIL", f"exercise problem number is not a bare integer: {heading}")
                else:
                    bare_numbers.append(int(number.group(1)))
                state = field_line_re("状态", r"([A-Za-z_]+)").search(entry)
                if not state or state.group(1) not in ALLOWED_QUESTION_STATES:
                    report("FAIL", f"exercise status is invalid: {heading}")
                dependency_line = re.search(
                    r"^-\s*(?:依赖|Depends on) completion node[：:]\s*(.*?)\s*$",
                    entry,
                    re.MULTILINE,
                )
                if progress_meta.get("course_driver") == "textbook":
                    raw_dependency = dependency_line.group(1).strip() if dependency_line else ""
                    dependency = re.fullmatch(r"`([^`\s]+)`", raw_dependency)
                    dependency_id = dependency.group(1) if dependency else ""
                    canonical_dependency = bool(
                        dependency
                        and re.fullmatch(
                            rf"{re.escape(course_id)}-B\d+-C\d+-S\d+-N\d+",
                            dependency_id,
                        )
                    )
                    if not canonical_dependency:
                        report(
                            "FAIL",
                            f"textbook exercise completion-node dependency format is invalid: "
                            f"{heading} -> {raw_dependency or '(empty)'}",
                        )
                    elif not re.fullmatch(
                        rf"{re.escape(content_group_id)}-N\d+",
                        dependency_id,
                    ):
                        report(
                            "FAIL",
                            f"textbook exercise dependency crosses out of the content group: {heading} -> {dependency_id}",
                        )
                    elif dependency_id not in completion_node_ids:
                        report(
                            "FAIL",
                            f"textbook exercise depends on a completion node that does not exist: "
                            f"{heading} -> {dependency_id}",
                        )
            if len(bare_numbers) != len(set(bare_numbers)):
                report("FAIL", f"exercise bare problem number duplicated: {rel(problems)}")
            if (
                progress_meta.get("course_driver") == "textbook"
                and source is not None
                and source.is_file()
            ):
                source_statements = exercise_problem_statements(
                    read(source),
                    unit.name,
                )
                problem_statements = exercise_problem_statements(content, unit.name)
                if set(source_statements) != set(headings):
                    report(
                        "FAIL",
                        f"the persistent problem source does not fully cover the textbook exercises: {unit.name} -> "
                        f"source={sorted(source_statements)} "
                        f"problems={sorted(headings)}",
                    )
                mismatched = sorted(
                    problem_id
                    for problem_id in set(source_statements) & set(problem_statements)
                    if source_statements[problem_id] != problem_statements[problem_id]
                )
                if mismatched:
                    report(
                        "FAIL",
                        f"textbook exercise problem statement disagrees with the persistent problem source: {unit.name} -> "
                        f"{mismatched}",
                    )
            for required_dir in ("attempts", "reviews"):
                if not (unit / required_dir).is_dir():
                    report("FAIL", f"exercise unit lacks {required_dir}/：{rel(unit)}")

            problem_ids = set(headings)
            attempts: dict[str, set[str]] = {}
            attempt_root = unit / "attempts"
            if attempt_root.is_dir():
                for attempt_dir in sorted(
                    path for path in attempt_root.iterdir()
                    if path.is_dir() and not path.name.startswith("_")
                ):
                    if not re.fullmatch(r"AT\d{4}", attempt_dir.name):
                        report("FAIL", f"Attempt ID is invalid: {rel(attempt_dir)}")
                        continue
                    carrier = attempt_dir / "attempt.md"
                    if not carrier.is_file():
                        report("FAIL", f"Attempt lacks attempt.md: {rel(attempt_dir)}")
                        continue
                    ameta = frontmatter(carrier)
                    attempt_problem_ids = set(list_value(ameta.get("problem_ids", "[]")))
                    attempts[attempt_dir.name] = attempt_problem_ids
                    if (
                        ameta.get("type") != "exercise_attempt"
                        or ameta.get("course_id") != course_id
                        or ameta.get("exercise_id") != unit.name
                        or ameta.get("attempt_id") != attempt_dir.name
                    ):
                        report("FAIL", f"Attempt frontmatter does not match: {rel(carrier)}")
                    if not attempt_problem_ids:
                        report("FAIL", f"Attempt does not reference a problem: {rel(carrier)}")
                    unknown = sorted(attempt_problem_ids - problem_ids)
                    if unknown:
                        report("FAIL", f"Attempt references an unknown problem: {rel(carrier)} -> {unknown}")
                    mode = ameta.get("mode", "")
                    if mode not in ALLOWED_ATTEMPT_MODES:
                        report("FAIL", f"Attempt mode is invalid: {rel(carrier)} -> {mode}")
                    if ameta.get("status") not in ALLOWED_ATTEMPT_STATES:
                        report("FAIL", f"Attempt status is invalid: {rel(carrier)}")
                    created = ameta.get("created", "")
                    created_date: dt.date | None = None
                    try:
                        created_date = dt.date.fromisoformat(created)
                    except (TypeError, ValueError):
                        pass
                    if created_date is None or created_date.isoformat() != created:
                        report("FAIL", f"Attempt created is not a valid ISO date: {rel(carrier)} -> {created or '—'}")
                    gate_snapshot = ameta.get("hint_gate", "")
                    assistance_level = ameta.get("assistance_level", "")
                    requires_gate_snapshot = bool(
                        created_date is not None
                        and created_date >= HINT_GATE_SCHEMA_DATE
                    )
                    if requires_gate_snapshot and (
                        not gate_snapshot or not assistance_level
                    ):
                        report("FAIL", f"Attempt lacks a hint-gate snapshot: {rel(carrier)}")
                    if gate_snapshot and gate_snapshot not in ALLOWED_HINT_GATE_MODES:
                        report(
                            "FAIL",
                            f"Attempt hint_gate is invalid: {rel(carrier)} -> {gate_snapshot}",
                        )
                    if (
                        assistance_level
                        and assistance_level not in ALLOWED_ASSISTANCE_LEVELS
                    ):
                        report(
                            "FAIL",
                            "Attempt assistance_level is invalid: "
                            f"{rel(carrier)} -> {assistance_level}",
                        )
                    if bool(gate_snapshot) != bool(assistance_level):
                        report("FAIL", f"Attempt hint-gate snapshot fields are not paired: {rel(carrier)}")
                    attempt_text = read(carrier)
                    if not section_text(attempt_text, "作答上下文"):
                        report("FAIL", f"Attempt lacks answer context: {rel(carrier)}")
                    for problem_id in sorted(attempt_problem_ids):
                        response = markdown_section(attempt_text, problem_id)
                        answer = field_line_re("作答", r"(\S.*)").search(response)
                        if not answer:
                            report("FAIL", f"Attempt lacks per-problem answers: {attempt_dir.name} -> {problem_id}")
                    if mode in {"image", "mixed"}:
                        assets = attempt_dir / "assets"
                        images = (
                            [
                                path for path in assets.iterdir()
                                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                            ]
                            if assets.is_dir() else []
                        )
                        if not images:
                            report("FAIL", f"image/mixed Attempt lacks the original images: {rel(attempt_dir)}")

            review_root = unit / "reviews"
            if review_root.is_dir():
                for review in sorted(
                    path for path in review_root.iterdir()
                    if path.is_file() and not path.name.startswith("_")
                ):
                    if not re.fullmatch(r"RV\d{4}\.md", review.name):
                        report("FAIL", f"Review filename is invalid: {rel(review)}")
                        continue
                    rmeta = frontmatter(review)
                    review_id = review.stem
                    attempt_id = rmeta.get("attempt_id", "")
                    review_problem_ids = set(list_value(rmeta.get("problem_ids", "[]")))
                    if (
                        rmeta.get("type") != "exercise_review"
                        or rmeta.get("course_id") != course_id
                        or rmeta.get("exercise_id") != unit.name
                        or rmeta.get("review_id") != review_id
                    ):
                        report("FAIL", f"Review frontmatter does not match: {rel(review)}")
                    if attempt_id not in attempts:
                        report("FAIL", f"Review references an unknown Attempt: {rel(review)} -> {attempt_id}")
                    elif not review_problem_ids or not review_problem_ids.issubset(attempts[attempt_id]):
                        report("FAIL", f"Review problems exceed the Attempt: {rel(review)}")
                    if rmeta.get("reviewer") not in ALLOWED_REVIEWERS:
                        report("FAIL", f"Review reviewer is invalid: {rel(review)}")
                    if rmeta.get("status") not in ALLOWED_REVIEW_STATES:
                        report("FAIL", f"Review status is invalid: {rel(review)}")
                    if not rmeta.get("reviewed") or rmeta.get("reviewed") == "—":
                        report("FAIL", f"Review lacks reviewed: {rel(review)}")
                    review_text = read(review)
                    for problem_id in sorted(review_problem_ids):
                        body = markdown_section(review_text, problem_id)
                        result = field_line_re("结果", r"([a-z_]+)").search(body)
                        if not result or result.group(1) not in ALLOWED_REVIEW_RESULTS:
                            report("FAIL", f"Review per-problem result is invalid: {review_id} -> {problem_id}")
                        for field in ("思路观察", "反馈", "mistake_refs", "question_refs"):
                            if not re.search(rf"^-\s*{re.escape(field)}[：:]", body, re.MULTILINE):
                                report("FAIL", f"Review lacks per-problem fields: {review_id}/{problem_id} -> {field}")

    if FLAVOR != "skeleton" and "MATH1607H" in courses:
        math_root = courses["MATH1607H"][0]
        has_legacy = (math_root / "exercises/U1101/problems.md").is_file()
        has_canonical = (math_root / "exercises/exercise01/problems.md").is_file()
        if not (has_legacy or has_canonical):
            report(
                "FAIL",
                "MATH1607H lacks an Exercise problem set (U1101 or exercise01)",
            )


def memory_pointer_values() -> dict[str, str]:
    path = MAIN / "00_core/t2ag_memory.md"
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for key, value in re.findall(
        r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|[^|]*\|$",
        read(path),
        re.MULTILINE,
    ):
        values[key.strip()] = value.strip()
    return values


def check_teacher_contract(
    courses: dict[str, tuple[Path, dict[str, str]]],
) -> dict[str, tuple[str, str]]:
    for template in sorted((MAIN / "20_teacher").glob("T*.md")):
        content = read(template)
        if re.search(r"记录错误.*lessonXX|错误.*写入.*lessonXX"
        r"|record(?:ing)? (?:the )?error.*lessonXX|error.*writ.*lessonXX", content):
            report(
                "FAIL",
                f"the teacher template bypasses the current activity route to write a Lesson: {rel(template)}",
            )
        required_route_markers = (
            "统一只读活动路由",
            "当前 Lesson/Exercise 主载体",
            "mistake_bank.md",
            "t2ag_hint_gate.py",
            "不把概念桥接回当前题",
        )
        missing = [
            marker for marker in required_route_markers if not has_marker(content, marker)
        ]
        if missing:
            report(
                "FAIL",
                f"the teacher template lacks the unified error routing contract: {rel(template)} -> {missing}",
            )
        required_presentation_markers = (
            "先给短目录、树形地图",
            "对象类型表",
            "新 Exercise 未授权阶段",
        )
        missing = [
            marker for marker in required_presentation_markers
            if not has_marker(content, marker)
        ]
        if missing:
            report(
                "FAIL",
                f"the teacher template lacks the map-first explanation protocol: {rel(template)} -> {missing}",
            )
    try:
        return resolve_teacher_mapping(ROOT, set(courses))
    except TeacherContractError as exc:
        for error in exc.errors:
            report("FAIL", f"teacher mapping contract: {error}")
        return {}


def check_memory_pointers(
    courses: dict[str, tuple[Path, dict[str, str]]],
    teacher_mapping: dict[str, tuple[str, str]],
) -> None:
    profile = frontmatter(MAIN / "10_student/profile/profile.md")
    if profile.get("initialization_status") != "initialized":
        return
    groups = []
    for plan in (MAIN / "30_group").glob("G*/plan.md"):
        meta = frontmatter(plan)
        if meta.get("status") == "active":
            groups.append((meta.get("group_id", plan.parent.name), meta))
    if len(groups) != 1:
        return
    group_id, group = groups[0]
    course_id = group.get("current_course", "")
    course = courses.get(course_id)
    values = memory_pointer_values()
    route = (
        COURSE_ROUTES.get(course_id)
        if course and course[1].get("lifecycle_status") == "ongoing"
        else None
    )
    expected = {
        "活跃课程组": group_id,
        "当前课程": course_id,
        "Lesson 上下文": route.lesson_context_label if route else "",
        "当前教学活动": (
            f"{route.activity_type}: {route.activity_id}" if route else ""
        ),
    }
    for key, value in expected.items():
        if not value or row_value(values, key) != value:
            report("FAIL", f"memory current-state pointer drift: {key}={values.get(key, 'missing')} expected={value or 'non-empty'}")
    teacher = teacher_mapping.get(course_id)
    if not teacher:
        report("FAIL", f"the current course lacks a teacher overlay mapping: {course_id}")
    else:
        teacher_id = teacher[0]
        expected_teacher = f"TR01 → {teacher_id}"
        if row_value(values, "当前教师") != expected_teacher:
            report(
                "FAIL",
                f"memory current-teacher pointer drift: "
                f"{row_value(values, '当前教师', 'missing')} "
                f"expected={expected_teacher}",
            )
    memory = read(MAIN / "00_core/t2ag_memory.md")
    for label in ("日期", "学到哪"):
        # LV-5: the label is emitted by t2ag_state_refresh and is spelled per edition.
        match = re.search(
            rf"^-\s*\*\*(?:{marker_alternation(label)})\*\*[：:]\s*(.+)$",
            memory,
            re.MULTILINE,
        )
        if not match or match.group(1).strip() == "—":
            report("FAIL", f"initialized instance memory last-lesson summary {label} is empty")


def path_exists(canonical: str) -> bool:
    path = ROOT / canonical.rstrip("/")
    return path.exists()


def check_registry() -> None:
    path = MAIN / "70_tools/artifact_registry.json"
    try:
        data = json.loads(read(path))
    except (OSError, json.JSONDecodeError) as exc:
        report("FAIL", f"artifact registry cannot be read: {exc}")
        return
    artifacts = data.get("artifacts", [])
    by_id = {item.get("artifact_id"): item for item in artifacts}
    if len(by_id) != len(artifacts):
        report("FAIL", "artifact_id is duplicated or empty")
    active: dict[str, list[str]] = {}
    temporary_segments = {
        "working_pages", "temppage", "__pycache__", ".staging", ".recovery",  # working_pages: defensive skip retained (retired in 0.2.2 S3)
    }
    for item in artifacts:
        artifact_id = item.get("artifact_id", "<?>")
        status = item.get("status")
        canonical = item.get("canonical_path", "")
        if status not in ALLOWED_REGISTRY_STATES:
            report("FAIL", f"artifact status is invalid: {artifact_id}={status}")
            continue
        redirects = item.get("redirects", [])
        if len(redirects) != len(set(redirects)):
            report("FAIL", f"redirects duplicated: {artifact_id}")
        if canonical in redirects:
            report("FAIL", f"redirect points at its own canonical: {artifact_id}")
        canonical_parts = set(Path(canonical.rstrip("/")).parts)
        if (
            status in {"active", "archived"}
            and canonical_parts & temporary_segments
        ):
            report(
                "FAIL",
                f"{status} canonical landed in a temporary lifecycle domain: "
                f"{artifact_id} -> {canonical}",
            )
        if status == "active":
            active.setdefault(canonical, []).append(artifact_id)
            if not path_exists(canonical):
                report("FAIL", f"active canonical does not exist: {artifact_id} -> {canonical}")
        elif status == "archived":
            if not path_exists(canonical):
                report("FAIL", f"archived canonical does not exist: {artifact_id} -> {canonical}")
        else:
            alias = item.get("alias_to")
            successors = item.get("successors", [])
            if not alias and not successors:
                report("FAIL", f"tombstone lacks alias_to/successors: {artifact_id}")
            if alias and alias not in by_id:
                report("FAIL", f"tombstone alias does not exist: {artifact_id} -> {alias}")
            for successor in successors:
                if set(Path(successor.rstrip("/")).parts) & temporary_segments:
                    report(
                        "FAIL",
                        f"tombstone successor landed in a temporary lifecycle domain: "
                        f"{artifact_id} -> {successor}",
                    )
                if not path_exists(successor):
                    report("FAIL", f"tombstone successor does not exist: {artifact_id} -> {successor}")
    for canonical, ids in active.items():
        if len(ids) > 1:
            report("FAIL", f"several active artifacts share one canonical: {canonical} -> {ids}")


def activity_has_been_entered(folder: Path, activity_type: str, activity_id: str) -> bool:
    """True once the ledger records a learning_enter for this activity.

    Used to separate "created" from "taught". Reading the ledger keeps the answer
    on the lifecycle authority instead of guessing from carrier file contents,
    which a generator could accidentally satisfy.
    """
    ledger_path = folder / "activity_ledger.md"
    if not ledger_path.is_file():
        return False
    try:
        doc = activity_ledger_contract.load_ledger(ledger_path)
    except Exception:  # a broken ledger is reported by its own check
        return True
    return any(
        event.get("event_kind") == "learning_enter"
        and event.get("activity_type") == activity_type
        and event.get("activity_id") == activity_id
        for event in doc.events
    )


CANON_PAGE_IDENTITY_FIELDS = (
    "source_document_sha256", "pdf_page_index", "render_profile", "render_sha256",
)


def canonical_carrier_findings(
    log_text: str,
    emission_lines: list[str],
    assets: dict[str, dict[str, str]],
    label: str,
) -> list[tuple[str, str, str]]:
    """CANON-000..004 — the teaching canon and its emissions ledger must agree.

    Contract: 50_playbook/canon_carrier.md.  This verifies **consistency**
    between teaching_log.md (C), emissions.jsonl (L) and the persistent page
    asset identity — it does NOT prove a block was written by canon_append.py.
    A forger who writes both files as one consistent chain passes; only the
    clumsy bypass is caught (G2 floor, declared in the playbook header).

    Crash asymmetry (by design, not oversight): canon_append writes L first,
    so "L row without C block" is repairable residue → WARN (CANON-004), while
    "C block without L row" cannot come from a crash → FAIL (CANON-000).

    Empty state: both sides missing/empty is silence — adoption is a
    per-lesson fact, not a debt.  Legacy lesson.md prose is not C (D3) and is
    never scanned.  ``verified_text_sha256`` / ``verification_status`` are
    snapshots, not compared: a page legitimately moving unverified→verified
    must not rot old emissions.
    """
    findings: list[tuple[str, str, str]] = []
    lines = [l for l in emission_lines if l.strip()]
    if not log_text.strip() and not lines:
        return findings

    records: list[dict | None] = []
    prev = "GENESIS"
    for index, raw in enumerate(lines, 1):
        try:
            rec = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            findings.append((
                "CANON-001", "FAIL",
                f"{label} emissions line {index} line is not valid JSON: the chain cannot be verified",
            ))
            rec = None
        if rec is not None and rec.get("prev_sha256") != prev:
            findings.append((
                "CANON-001", "FAIL",
                f"{label} SHA chain broken at line {index} "
                f"(declared prev={str(rec.get('prev_sha256'))[:12]}... expected {prev[:12]}...)",
            ))
        prev = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        records.append(rec)

    ledger_blocks: dict[str, dict] = {}
    for rec in records:
        if rec and rec.get("block_id"):
            ledger_blocks[str(rec["block_id"])] = rec

    canon_blocks: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in log_text.split("\n"):
        match = re.match(r"^## (\S+)\s*$", line)
        if match:
            if current is not None:
                canon_blocks[current] = "\n".join(buffer)
            current = match.group(1)
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        canon_blocks[current] = "\n".join(buffer)

    for block_id in canon_blocks:
        if block_id not in ledger_blocks:
            findings.append((
                "CANON-000", "FAIL",
                f"{label} canonical block {block_id} has no matching event line: the single writer was bypassed",
            ))

    for block_id, rec in ledger_blocks.items():
        if block_id not in canon_blocks:
            findings.append((
                "CANON-004", "WARN",
                f"{label} event line {block_id} has no matching canonical block (interrupted emit residue; replay can complete it)",
            ))
        else:
            body_lines = canon_blocks[block_id].split("\n")
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
            while body_lines and body_lines[0].startswith(">"):
                body_lines.pop(0)
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
            canonical = "\n".join(body_lines).rstrip("\n") + "\n"
            got = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            want = rec.get("content_sha256")
            if want != got:
                findings.append((
                    "CANON-003", "FAIL",
                    f"{label} canonical block {block_id} content hash disagrees with the event "
                    f"ledger (ledger {str(want)[:12]}... measured {got[:12]}...)",
                ))
        for ref in rec.get("page_refs") or []:
            asset_id = str(ref.get("asset_id", ""))
            asset = assets.get(asset_id)
            if asset is None:
                findings.append((
                    "CANON-002", "FAIL",
                    f"{label} event line {block_id} references a page asset that cannot be found: {asset_id}"
                    "(an asset is a permanent identity, not an evictable cache)",
                ))
                continue
            for field in CANON_PAGE_IDENTITY_FIELDS:
                if str(ref.get(field, "")) != str(asset.get(field, "")):
                    findings.append((
                        "CANON-002", "FAIL",
                        f"{label} event line {block_id} page identity disagrees with the asset: {asset_id}"
                        f".{field} ledger {str(ref.get(field))[:12]}… "
                        f"asset {str(asset.get(field))[:12]}...",
                    ))
    return findings


def check_canonical_teaching_carrier(
    courses: dict[str, tuple[Path, dict[str, str]]]
) -> None:
    """CANON-000..004: teaching canon ↔ emissions ledger ↔ page assets agree.

    Applies to courses whose course.md declares ``default_driver: textbook``
    (D4: the machine criterion is the driver field, not a course roster).
    """
    for course_id, (folder, _meta) in sorted(courses.items()):
        course_md = folder / "course.md"
        if not course_md.is_file():
            continue
        if frontmatter(course_md).get("default_driver") != "textbook":
            continue
        lessons = folder / "lessons"
        if not lessons.is_dir():
            continue
        assets: dict[str, dict[str, str]] | None = None
        for lesson_dir in sorted(p for p in lessons.iterdir() if p.is_dir()):
            log_path = lesson_dir / "teaching_log.md"
            emissions_path = lesson_dir / "emissions.jsonl"
            if not log_path.is_file() and not emissions_path.is_file():
                continue
            if assets is None:
                assets = {}
                book = folder / "book"
                if book.is_dir():
                    for page in book.rglob("page_*.md"):
                        if ".cache" in page.parts:
                            continue
                        fields = frontmatter(page)
                        if fields.get("asset_id"):
                            assets[fields["asset_id"]] = fields
            log_text = read(log_path) if log_path.is_file() else ""
            lines = read(emissions_path).split("\n") if emissions_path.is_file() else []
            for code, severity, message in canonical_carrier_findings(
                log_text, lines, assets, f"{course_id}/{lesson_dir.name}"
            ):
                report(severity, f"{code} {message}")


def check_textbook_preparation(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    """Textbook lesson evidence: EV-0012 current Snapshot path (legacy working_pages retired in 0.2.2)."""
    for course_id, (folder, meta) in courses.items():
        if (
            meta.get("current_activity") != "lesson"
            or meta.get("course_driver") != "textbook"
        ):
            continue
        lesson = meta.get("current_activity_id", "")
        if not re.fullmatch(r"lesson\d+", lesson):
            if meta.get("textbook_page"):
                report(
                    "FAIL",
                    f"working pages lack the current Lesson activity: {course_id} -> {lesson or 'missing'}",
                )
            continue
        prep_dir = folder / "lessons" / lesson / "preparation"
        pointer_path = prep_dir / "current_snapshot.json"
        has_prep = prep_dir.is_dir() and (
            pointer_path.is_file() or any(prep_dir.glob("PREP-*.json"))
        )
        if has_prep:
            # Never use lexical-last PREP-*.json as "current".
            if not pointer_path.is_file():
                report(
                    "FAIL",
                    f"preparation exists but the current_snapshot pointer is missing: {course_id}/{lesson}",
                )
                continue
            try:
                pointer = json.loads(read(pointer_path))
            except (OSError, json.JSONDecodeError) as exc:
                report(
                    "FAIL",
                    f"the current Snapshot pointer is unreadable: {course_id}/{lesson} {exc}",
                )
                continue
            snap_id = str(pointer.get("snapshot_id") or "")
            snap_path = prep_dir / f"{snap_id}.json"
            if not snap_id.startswith("PREP-") or not snap_path.is_file():
                report(
                    "FAIL",
                    f"the current Snapshot pointer target is invalid: {course_id}/{lesson} -> {snap_id}",
                )
                continue
            try:
                payload = json.loads(read(snap_path))
            except (OSError, json.JSONDecodeError) as exc:
                report(
                    "FAIL",
                    f"preparation Snapshot is unreadable: {course_id}/{snap_path.name} {exc}",
                )
                continue
            if payload.get("snapshot_id") != snap_id:
                report("FAIL", f"Snapshot id disagrees with the pointer: {course_id}/{lesson}")
            if payload.get("state") != "valid":
                report("FAIL", f"preparation Snapshot is not valid: {course_id}/{snap_path.name}")
            if not payload.get("load_receipt_ids") and not payload.get("load_receipts"):
                report("FAIL", f"preparation Snapshot lacks load receipts: {course_id}")
            if payload.get("scope_coverage") != "complete":
                report("FAIL", f"preparation Snapshot scope is not complete: {course_id}")
            if not payload.get("content_consumed"):
                report("FAIL", f"preparation Snapshot content_consumed is false: {course_id}")
            page_keys = payload.get("page_keys") or []
            indices = [
                int(k.get("pdf_page_index"))
                for k in page_keys
                if isinstance(k, dict) and k.get("pdf_page_index") is not None
            ]
            if not indices:
                report("FAIL", f"preparation Snapshot lacks page_keys: {course_id}")
            elif indices != list(range(min(indices), max(indices) + 1)):
                report(
                    "FAIL",
                    f"preparation Snapshot Scope is not contiguous: {course_id} -> {indices}",
                )
            short = bool(payload.get("short_document"))
            if not short and indices and not (5 <= len(indices) <= 8):
                report(
                    "FAIL",
                    f"preparation Snapshot scope_n out of range (must be 5-8): {course_id} n={len(indices)}",
                )
            if short and indices and len(indices) >= 5:
                report(
                    "FAIL",
                    f"the short_document marker conflicts with scope_n: {course_id}",
                )
            receipts = payload.get("load_receipts") or []
            if page_keys and len(receipts) != len(page_keys):
                report(
                    "FAIL",
                    f"preparation Snapshot receipts and page_keys differ in count: {course_id}",
                )
            doc_sha = str(payload.get("source_document_sha256") or "").lower()
            document_id = str(payload.get("document_id") or "")
            for receipt in receipts:
                if not isinstance(receipt, dict):
                    report("FAIL", f"load receipt is invalid: {course_id}")
                    continue
                if not receipt.get("source_page_asset_sha256"):
                    report("FAIL", f"load receipt lacks the SourcePageAsset SHA: {course_id}")
                rdoc = str(receipt.get("source_document_sha256") or "").lower()
                if doc_sha and rdoc and rdoc != doc_sha:
                    report("FAIL", f"load receipt SourceDocument SHA mismatch: {course_id}")
            map_path = folder / "lessons" / lesson / "lesson_map.md"
            if not map_path.is_file():
                report("FAIL", f"missing LessonMap: {course_id}/{lesson}")
            else:
                # Raw file bytes only — must match prepare/Context (no read_text rewrite).
                map_raw = map_path.read_bytes()
                map_sha = hashlib.sha256(map_raw).hexdigest()
                map_text = map_raw.decode("utf-8", errors="replace")
                expected_map = str(payload.get("lesson_map_sha256") or "")
                if expected_map and expected_map != map_sha:
                    report("FAIL", f"LessonMap hash disagrees with the Snapshot: {course_id}/{lesson}")
                for value in indices:
                    if not re.search(rf"\|\s*{value}\s*\|", map_text) and (
                        f"page_{value}" not in map_text
                    ):
                        report(
                            "FAIL",
                            f"LessonMap does not cover the Scope pages: {course_id} page {value}",
                        )
            if document_id and doc_sha:
                manifest = (
                    folder
                    / "book/primary/source_assets"
                    / document_id
                    / "manifest.json"
                )
                if manifest.is_file():
                    try:
                        man = json.loads(read(manifest))
                        man_sha = str(man.get("source_document_sha256") or "").lower()
                        if man_sha and man_sha != doc_sha:
                            report(
                                "FAIL",
                                f"Snapshot PDF SHA disagrees with the manifest: {course_id}",
                            )
                        source_path = str(man.get("source_path") or "")
                        if source_path:
                            pdf = Path(source_path)
                            if not pdf.is_absolute():
                                pdf = (ROOT / source_path) if (ROOT / source_path).is_file() else folder / source_path
                            if pdf.is_file():
                                actual = hashlib.sha256(pdf.read_bytes()).hexdigest().lower()
                                if actual != doc_sha:
                                    report(
                                        "FAIL",
                                        f"SourceDocument PDF SHA disagrees with the Snapshot: {course_id}",
                                    )
                            else:
                                report(
                                    "FAIL",
                                    f"SourceDocument/PDF is missing: {course_id} {source_path}",
                                )
                    except (OSError, json.JSONDecodeError) as exc:
                        report(
                            "FAIL",
                            f"source_assets manifest is unreadable: {course_id}/{document_id} {exc}",
                        )
                for value in indices:
                    asset = (
                        folder
                        / "book/primary/source_assets"
                        / document_id
                        / "pages"
                        / f"page_{value}.md"
                    )
                    if not asset.is_file():
                        report(
                            "FAIL",
                            f"missing SourcePageAsset: {course_id} page_{value}",
                        )
                    else:
                        asset_text = read(asset)
                        status_m = re.search(
                            r"^verification_status:\s*(\S+)",
                            asset_text,
                            re.MULTILINE,
                        )
                        status = (status_m.group(1) if status_m else "").lower()
                        if status not in {
                            "verified",
                            "verified_human",
                            "verified_ok",
                            "ok",
                        }:
                            report(
                                "FAIL",
                                f"SourcePageAsset is unverified: {course_id} page_{value}",
                            )
            scope_n = len(indices) if indices else 0
            quota_n = min(3 * scope_n, 30) if scope_n else 0
            cache_root = folder / "book" / ".cache" / "source_pages"
            cache_n = 0
            if cache_root.is_dir():
                cache_n = sum(1 for _ in cache_root.rglob("page_*.png"))
            # Informational: P0 = current scope page keys; quota is course-aggregated.
            if scope_n and cache_n > quota_n:
                report(
                    "WARN",
                    f"cache exceeds quota: {course_id} cache_n={cache_n} quota_n={quota_n} "
                    f"scope_n={scope_n}（P0={scope_n} pages must not be evicted)",
                )
            continue
        if not activity_has_been_entered(folder, "lesson", lesson):
            # Created but never taught. A Snapshot asserts prepared pages, load
            # receipts and complete scope coverage, so demanding one here forced a
            # freshly generated Lesson into a state no honest tool could produce:
            # fabricate evidence, or fail Doctor on the user's first run. Entering
            # learning is the point where a Snapshot becomes mandatory.
            report(
                "INFO",
                f"textbook lesson pages are not prepared yet (no learning_enter in the ledger): {course_id}/{lesson}",
            )
            continue
        # Legacy working_pages window retired in 0.2.2 S3.
        # Textbook lessons must use preparation Snapshots exclusively.
        report(
            "FAIL",
            f"textbook lesson lacks a preparation Snapshot, and the legacy path is retired: "
            f"{course_id}/{lesson}",
        )


def check_scope_page_cache(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    """SCOPE-CACHE-001: warn when the current Scope's page images are not prewarmed.

    The textbook visual scan requires actually opening every Scope page image.
    A cold cache does not make teaching wrong, but it forces live rendering at
    lesson start and has repeatedly delayed the first block. This check is
    read-only: it reports the gap and the prewarm command, and never renders.
    Snapshot shape problems are left to check_textbook_preparation.
    """
    for course_id, (folder, meta) in courses.items():
        if (
            meta.get("current_activity") != "lesson"
            or meta.get("course_driver") != "textbook"
        ):
            continue
        lesson = meta.get("current_activity_id", "")
        if not re.fullmatch(r"lesson\d+", lesson):
            continue
        pointer_path = (
            folder / "lessons" / lesson / "preparation" / "current_snapshot.json"
        )
        if not pointer_path.is_file():
            continue
        try:
            pointer = json.loads(read(pointer_path))
            snap_id = str(pointer.get("snapshot_id") or "")
            payload = json.loads(read(pointer_path.parent / f"{snap_id}.json"))
        except (OSError, json.JSONDecodeError):
            continue
        cache_root = folder / "book" / ".cache" / "source_pages"
        missing: list[int] = []
        for key in payload.get("page_keys") or []:
            if not isinstance(key, dict) or key.get("pdf_page_index") is None:
                continue
            sha = str(key.get("source_document_sha256") or "")
            profile = str(key.get("render_profile") or "pdf-300dpi-rgb-v1")
            index = int(key["pdf_page_index"])
            if not sha:
                continue
            if not (cache_root / sha / profile / f"page_{index}.png").is_file():
                missing.append(index)
        if missing:
            report(
                "WARN",
                f"SCOPE-CACHE-001 Scope page images are not pre-warmed: {course_id}/{lesson} "
                f"missing pages {sorted(missing)}; this round's visual scan must render them "
                f"on the spot first. Pre-warm: "
                f"python -B main/70_tools/t2ag_source_pages.py prewarm "
                f"--course {course_id} --lesson {lesson} --render",
            )


# LV-5: the gate-ledger section heading in every shipped language edition.
GATE_LEDGER_SECTIONS = ("## 门台账", "## Gate ledger")
GATE_LEDGER_SECTION = GATE_LEDGER_SECTIONS[0]
GATE_LEDGER_PLACEHOLDERS = {
    "", "-", "—", "待填", "无", "?", "？", "to be filled in", "none", "TBD",
}
GATE_LEDGER_HINT_LEVELS = {"direction_hint", "specified_reference", "full_solution"}


def parse_gate_ledger(text: str) -> dict[str, object] | None:
    """Parse one carrier's gate-ledger section; None when the section is absent.

    A present section with an unreadable anchor line or a row of wrong arity is
    malformed — fail-closed, surfaced as GATE-LEDGER-000
    (learning_activity_model.md §2.4).  Deterministic parse only.
    """
    marker = text.find(GATE_LEDGER_SECTION)
    if marker == -1:
        return None
    section = text[marker:]
    nxt = section.find("\n## ", 1)
    if nxt != -1:
        section = section[:nxt]
    errors: list[str] = []
    anchor = None
    match = re.search(
        r"^ledger_since:.*?(?:起算块|起算证据|starting block|starting evidence):\s*(\S+)", section, re.MULTILINE
    )
    if match:
        anchor = match.group(1).strip()
    else:
        errors.append("the anchor row is missing or unreadable (it must contain the starting block / starting evidence)")
    rows: list[dict[str, str]] = []
    for line in section.splitlines():
        if not line.lstrip().startswith("| GT-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            errors.append(f"abnormal column count ({len(cells)} ≠ 7）：{line.strip()[:60]}")
            continue
        rows.append({
            "gid": cells[0], "block": cells[1], "gate": cells[2],
            "closure": cells[3], "feeling": cells[4],
            "authorization": cells[5], "consumed": cells[6],
        })
    return {"anchor": anchor, "rows": rows, "errors": errors}


def checkpoint_rows_from(progress_text: str, anchor_id: str) -> list[tuple[str, str, str]] | None:
    """Ordered (id, page, status) checkpoint rows from the anchor row on.

    Anchor-inclusive: the anchor block itself needs no incoming transition, but
    the crossing anchor→next is in scope.  None when the anchor is not in the
    table (the ledger then fails closed, not open).

    Two deterministic table shapes are accepted:
    - header-driven: a header row naming `checkpoint_id` and the status column
      declares the layout for the rows beneath it; the page column is optional (goal-driver
      courses legitimately have no page column — the AIF false 000 of
      2026-08-10 came from rejecting this shape);
    - headerless legacy: fixed 6-column rows whose id matches
      `-B\\d+-P\\d+-N\\d+`.
    """
    rows: list[tuple[str, str, str]] = []
    header: dict[str, int] | None = None
    width = 0
    for line in progress_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells and all(set(c) <= {"-", ":", " "} for c in cells):
            continue  # markdown separator row
        if "checkpoint_id" in cells:
            if cell_index(cells, "状态") >= 0:
                header = {
                    "id": cells.index("checkpoint_id"),
                    "page": cell_index(cells, "页码"),
                    "status": cell_index(cells, "状态"),
                }
                width = len(cells)
            else:
                header = None
            continue
        if header is not None and len(cells) == width:
            cid = cells[header["id"]]
            if re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+", cid):
                page = cells[header["page"]] if header["page"] >= 0 else ""
                rows.append((cid, page, cells[header["status"]]))
            continue
        if len(cells) >= 6 and re.fullmatch(r"[A-Za-z0-9]+-B\d+-P\d+-N\d+", cells[0]):
            rows.append((cells[0], cells[2], cells[5]))
    ids = [row[0] for row in rows]
    if anchor_id not in ids:
        return None
    return rows[ids.index(anchor_id):]


def gate_ledger_findings(
    ledger: dict[str, object],
    checkpoints: list[tuple[str, str, str]] | None,
    *,
    carrier: str,
    rv_ids: tuple[str, ...] = (),
    attempt_hints: tuple[tuple[str, str], ...] = (),
) -> list[tuple[str, str]]:
    """Pure verdicts for one ledger — codes 000–006 of §2.4, deterministic only.

    The teaching protocol's semantics stay in main/t2ag.md; this function only
    answers whether gate crossings left their rows.  `checkpoints` is the
    anchor-inclusive slice for Lesson carriers (None = anchor unresolved);
    `rv_ids` / `attempt_hints` are the post-anchor evidence for Exercise ones.
    """
    findings: list[tuple[str, str]] = []
    errors = list(ledger.get("errors") or [])
    if errors:
        for issue in errors:
            findings.append(("GATE-LEDGER-000", f"{carrier} gate ledger corrupted (fail-closed): {issue}"))
        return findings
    rows = list(ledger.get("rows") or [])

    numbers: list[int] = []
    for row in rows:
        gid = re.fullmatch(r"GT-(\d+)", row["gid"])
        if not gid:
            findings.append(("GATE-LEDGER-004", f"{carrier} invalid row ID: {row['gid']}"))
            continue
        numbers.append(int(gid.group(1)))
    if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
        findings.append(("GATE-LEDGER-004", f"{carrier} row IDs are not monotonically increasing, or repeat"))

    for row in rows:
        if row["authorization"].strip("*` ") in GATE_LEDGER_PLACEHOLDERS:
            findings.append((
                "GATE-LEDGER-003",
                f"{carrier} {row['gid']}（{row['block']}) authorization text is empty or a placeholder: it must be the student's verbatim quotation",
            ))

    if checkpoints is None:
        findings.append(("GATE-LEDGER-000", f"{carrier} the starting block does not exist in the progress checkpoint table"))
        return findings

    confirmed = [(cid, page) for cid, page, status in checkpoints if status == "confirmed"]
    transition_rows = [r for r in rows if gate_is(r, "块过渡")]

    def _names(cell: str, cp_id: str) -> bool:
        """A cell names a checkpoint by full id, or by its terminal token.

        Teaching may legally detour through off-tree blocks (constitution §4,
        student-led branches), so a crossing a->b is satisfied by an exit row for a plus an
        entry row for b — not only by one direct a→b row.  Token match is
        boundary-guarded so S01 never matches S011.
        """
        if cp_id in cell:
            return True
        token = cp_id.rsplit("-", 1)[-1]
        return bool(re.search(
            rf"(?<![A-Za-z0-9]){re.escape(token)}(?![0-9])", cell
        ))

    pageturns = {r["consumed"] for r in rows if gate_is(r, "翻页")}
    for (a_id, a_page), (b_id, b_page) in zip(confirmed, confirmed[1:]):
        has_exit = any(_names(r["block"], a_id) for r in transition_rows)
        has_entry = any(_names(r["consumed"], b_id) for r in transition_rows)
        if not (has_exit and has_entry):
            findings.append((
                "GATE-LEDGER-001",
                f"{carrier} adjacent confirmed blocks {a_id} → {b_id} lacks a block-transition row",
            ))
        if a_page != b_page and b_id not in pageturns:
            findings.append((
                "GATE-LEDGER-002",
                f"{carrier} page {a_page}→{b_page} change point ({b_id}) lacks a page-turn row",
            ))

    closure_text = " ".join(
        f"{r['consumed']} {r['closure']}" for r in rows if gate_is(r, "题目闭环")
    )
    for rv in rv_ids:
        if rv not in closure_text:
            findings.append(("GATE-LEDGER-005", f"{carrier} new review {rv} lacks a problem-closure row"))
    hint_text = " ".join(
        f"{r['consumed']} {r['closure']}" for r in rows if gate_starts(r, "提示授权")
    )
    for attempt_id, level in attempt_hints:
        if level in GATE_LEDGER_HINT_LEVELS and attempt_id not in hint_text:
            findings.append((
                "GATE-LEDGER-006",
                f"{carrier} {attempt_id} recorded {level}-level hint but the hint-authorization row is missing",
            ))
    return findings


def check_gate_ledger(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    """GATE-LEDGER-000..007: teaching-gate ledger completeness (§2.4).

    Scans every Lesson/Exercise carrier that HAS a gate-ledger section; historical
    carriers without one are skipped (deployment transition — sections arrive
    with the ledger_since anchor, history before the anchor is exempt).
    Completeness findings are WARN-only: an incomplete ledger is a
    record-keeping breach, not a state error, and must not block a lesson
    mid-session.  The one FAIL is GATE-LEDGER-007: the course's CURRENT
    textbook Lesson missing its gate-ledger section entirely -- then the prose
    gates have no machine landing at all (the P-0054 hole), and closure
    claims must not be made until the section exists.
    """
    for course_id, (folder, meta) in courses.items():
        progress_text = ""
        progress_path = folder / "progress.md"
        if progress_path.is_file():
            try:
                progress_text = read(progress_path)
            except OSError:
                progress_text = ""
        driver = str(meta.get("course_driver") or "")
        current_activity = str(meta.get("current_activity") or "")
        current_id = str(meta.get("current_activity_id") or "")
        if (
            driver == "textbook"
            and current_activity == "lesson"
            and re.fullmatch(r"lesson\d+", current_id)
        ):
            active_carrier = folder / "lessons" / current_id / f"{current_id}.md"
            try:
                active_text = read(active_carrier)
            except OSError:
                active_text = ""
            if GATE_LEDGER_SECTION not in active_text:
                report(
                    "FAIL",
                    f"GATE-LEDGER-007 {course_id}/{current_id} the current textbook Lesson "
                    "lacks a gate-ledger section: the prose gates have no machine "
                    "landing point (§2.4); closure may be claimed only after the "
                    "section is added",
                )
        for carrier_path in sorted(folder.glob("lessons/lesson*/lesson*.md")):
            if not re.fullmatch(r"lesson\d+\.md", carrier_path.name):
                continue
            try:
                ledger = parse_gate_ledger(read(carrier_path))
            except OSError:
                continue
            if ledger is None:
                continue
            checkpoints = None
            anchor = ledger.get("anchor")
            if anchor and progress_text:
                checkpoints = checkpoint_rows_from(progress_text, str(anchor))
            carrier = f"{course_id}/{carrier_path.parent.name}"
            for code, message in gate_ledger_findings(ledger, checkpoints, carrier=carrier):
                report("WARN", f"{code} {message}")
        for carrier_path in sorted(folder.glob("exercises/exercise*/exercise.md")):
            try:
                ledger = parse_gate_ledger(read(carrier_path))
            except OSError:
                continue
            if ledger is None:
                continue
            exercise_dir = carrier_path.parent
            anchor = str(ledger.get("anchor") or "")
            rv_floor = at_floor = 0
            span = re.fullmatch(r"RV(\d+)/AT(\d+)", anchor)
            if span:
                rv_floor, at_floor = int(span.group(1)), int(span.group(2))
            rv_ids = tuple(
                p.stem for p in sorted(exercise_dir.glob("reviews/RV*.md"))
                if re.fullmatch(r"RV\d+", p.stem) and int(p.stem[2:]) > rv_floor
            )
            hints: list[tuple[str, str]] = []
            for attempt in sorted(exercise_dir.glob("attempts/AT*/attempt.md")):
                attempt_id = attempt.parent.name
                if not re.fullmatch(r"AT\d+", attempt_id) or int(attempt_id[2:]) <= at_floor:
                    continue
                try:
                    head = read(attempt)[:2000]
                except OSError:
                    continue
                hint = re.search(r"^hint_level:\s*(\S+)", head, re.MULTILINE)
                if hint:
                    hints.append((attempt_id, hint.group(1)))
            carrier = f"{course_id}/{exercise_dir.name}"
            for code, message in gate_ledger_findings(
                ledger, [], carrier=carrier, rv_ids=rv_ids, attempt_hints=tuple(hints),
            ):
                report("WARN", f"{code} {message}")


PLOG_ANCHOR = re.compile(r"^closure_fields_since:\s*(P-\d{4})\s*$", re.MULTILINE)
PLOG_ENTRY = re.compile(r"^## (P-\d{4})\b", re.MULTILINE)
PLOG_CLOSURE_FIELD = re.compile(r"^-\s*closure:\s*(.+?)\s*$", re.MULTILINE)
PLOG_OCCURRENCE = re.compile(r"^-\s*occurrence_count:\s*(\d+)\s*$", re.MULTILINE)
PLOG_CLOSURE_VALUE = re.compile(
    r"^(open|check=\S+|tool=\S+|prose_accepted[（(].+[）)])$"
)

# --- R-GATE: the enforcement/closure landing vocabulary ----------------------
# One vocabulary, two hosts: `enforcement:` in rule files (rule_admission_gate.md
# §2) and `closure:` in the problemlog.  Severity differs by host -- a dangling
# landing in a rule is a false guarantee that must block (P-0067 family), the
# same defect in the incident log is a record-keeping breach that must not block
# teaching.  The verdict logic is shared; the severity mapping is not.

FENCE_LINE = re.compile(r"^[ \t]*(?:```|~~~)")
ENFORCEMENT_FIELD = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?enforcement:[ \t]*(.+?)[ \t]*$", re.MULTILINE
)
CLOSURE_FIELD_ANY = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?closure:[ \t]*(.+?)[ \t]*$", re.MULTILINE
)
# 00_core files that may carry `enforcement:`.  The rest of 00_core — changelog,
# problemlog body, memory — is append-only record: a quoted historical landing
# must not become a live contract that FAILs when its target is later renamed.
# NOTE: a new rule-bearing file under 00_core must be added here by hand.
RULE_ENFORCEMENT_CORE_FILES = (
    "domain_model.md",
    "learning_activity_model.md",
    "pattern_retire_loop.md",
)


def edition_language(tree: Path) -> str:
    """Which language edition a distribution tree is, read from its constitution.

    LV-5 (2026-08-20): byte parity is asserted *within* a language edition, never
    across two.  A translated edition is a fourth distribution, and demanding it be
    byte-identical to the zh-CN one is not a contract anyone can satisfy -- it would
    make a correctly-built English tree permanently red for the one reason that is
    intended.  Parity still has teeth: it holds between same-edition siblings, and
    the marker assertions hold in every edition.

    Kept here rather than in one test file so every sibling-comparison test resolves
    the edition the same way; two copies of this rule would be two sets of bugs.
    """
    constitution = tree / "main/t2ag.md"
    if not constitution.is_file():
        return "unknown"
    text = constitution.read_text(encoding="utf-8", errors="replace")
    if re.search(r"^##\s+Preface\b", text, re.MULTILINE):
        return "en"
    if re.search(r"^##\s+序\b", text, re.MULTILINE):
        return "zh-CN"
    return "unknown"


def next_action_label_alternation() -> str:
    """Regex alternation over every accepted next-action bullet label.

    LV-5: this was written by hand in two places as
    `下一步计划|下一步|下次第一件事|Next step plan|Next step|First thing next time`.
    The hand-written English said "Next step plan" while the registry (and the
    templates generated from it) say "Next-step plan", so a correctly generated
    English progress file failed both checks. One list, one place.
    """
    return "|".join(
        marker_alternation(canonical)
        for canonical in ("下一步计划", "下一步", "下次第一件事")
    )

def strip_fenced_blocks(text: str) -> str:
    """Blank out fenced code blocks, preserving line numbering.

    R-GATE §4, code side: the playbook that defines `enforcement:` is itself a
    rule file full of examples.  Without this, the document that creates the
    check is the first thing the check fires on.  Line count is preserved so
    findings can still name a real line number.
    """
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if FENCE_LINE.match(line):
            inside = not inside
            lines.append("")
            continue
        lines.append("" if inside else line)
    return "\n".join(lines)


PLAYBOOK_LEVEL_LINE = re.compile(
    # LV-5 (2026-08-20): translated editions spell the marker "Protection level".
    r"^(?:>\s*)?\*\*(?:保护级别|Protection level)\*\*[：:]\s*"
    r"(meta-playbook|core-playbook|playbook)\b"
)
PLAYBOOK_LEVEL_ANY = re.compile(
    r"^(?:>\s*)?\*\*(?:保护级别|Protection level)\*\*[：:]\s*(.*)$"
)
LEGAL_PLAYBOOK_LEVELS = frozenset({"meta-playbook", "core-playbook", "playbook"})
TAXONOMY_README_EXEMPT = "_README.md"


def parse_playbook_protection_levels(
    text: str,
) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (legal_matches, illegal_marker_rows). Line numbers are 1-based.

    Fences are stripped first, so quoted examples do not count. Blockquote
    prefixes are accepted. Every match is returned, not just the first.
    """
    stripped = strip_fenced_blocks(text)
    legal: list[tuple[int, str]] = []
    illegal: list[tuple[int, str]] = []
    for lineno, line in enumerate(stripped.splitlines(), 1):
        matched = PLAYBOOK_LEVEL_LINE.match(line)
        if matched:
            legal.append((lineno, matched.group(1)))
            continue
        any_match = PLAYBOOK_LEVEL_ANY.match(line)
        if any_match:
            illegal.append((lineno, any_match.group(1).strip()))
    return legal, illegal


def playbook_taxonomy_findings(
    documents: dict[str, str],
    *,
    exempt_unmarked: frozenset[str] | None = None,
) -> list[tuple[str, str, str]]:
    """Local taxonomy findings: ``(code, severity, message)``."""
    exempt = exempt_unmarked or frozenset({TAXONOMY_README_EXEMPT})
    findings: list[tuple[str, str, str]] = []
    for name in sorted(documents):
        legal, illegal = parse_playbook_protection_levels(documents[name])
        for lineno, raw in illegal:
            findings.append((
                "PB-TAXO-001",
                "FAIL",
                f"{name}:{lineno} invalid protection-level value: {raw}",
            ))
        values = [value for _, value in legal]
        if not legal and not illegal and name not in exempt:
            findings.append(("PB-TAXO-002", "WARN", f"{name} has no protection-level marker"))
        unique = set(values)
        if len(unique) > 1:
            findings.append((
                "PB-TAXO-005",
                "FAIL",
                f"{name} conflicting protection levels: {sorted(unique)}",
            ))
        elif len(values) > 1 and len(unique) == 1:
            findings.append((
                "PB-TAXO-005",
                "WARN",
                f"{name} duplicate marker with the same value: {values[0]} x{len(values)}",
            ))
    return findings


PLAYBOOK_USAGE_MARK_DAYS = 14
PLAYBOOK_USAGE_ARCHIVE_DAYS = 40
PLAYBOOK_USAGE_EXEMPT = {
    "host_g1_optional.md": "optional host dormancy document; dormancy is normal",
}
USAGE_DATE_TOKEN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
USAGE_MANAGED_BY = re.compile(r"^(?:>\s*)?managed_by:", re.MULTILINE)


def playbook_usage_last_seen(
    sources: list[tuple[str, str, "dt.date | None"]],
    names: frozenset[str],
) -> dict[str, "dt.date"]:
    """Return the latest dated reference to each playbook filename."""
    last: dict[str, dt.date] = {}
    for _label, body, seed in sources:
        cursor = seed
        for line in body.splitlines():
            tokens = USAGE_DATE_TOKEN.findall(line)
            if tokens:
                try:
                    cursor = max(dt.date.fromisoformat(token) for token in tokens)
                except ValueError:
                    pass
            if cursor is None:
                continue
            for name in names:
                if name in line and (name not in last or cursor > last[name]):
                    last[name] = cursor
    return last


def playbook_usage_findings(
    names: frozenset[str],
    last_seen: dict[str, "dt.date"],
    today: "dt.date",
) -> list[tuple[str, str, str]]:
    """WARN-only depreciation verdict; never removes the sole copy."""
    findings: list[tuple[str, str, str]] = []
    unseen = sorted(name for name in names if name not in last_seen)
    if unseen:
        findings.append((
            "PB-USE-003", "INFO",
            "no dated reference data (observing, not calling cold): " + ", ".join(unseen),
        ))
    for name in sorted(names):
        seen = last_seen.get(name)
        if seen is None:
            continue
        age = (today - seen).days
        if age > PLAYBOOK_USAGE_ARCHIVE_DAYS:
            findings.append((
                "PB-USE-002", "WARN",
                f"archive candidate: {name}, last referenced {seen} ({age} days ago); "
                "the host may git-move it into archive/, but must not delete the sole copy",
            ))
        elif age > PLAYBOOK_USAGE_MARK_DAYS:
            findings.append((
                "PB-USE-001", "WARN",
                f"cold marker: {name}, last referenced {seen} ({age} days ago)",
            ))
    return findings


def playbook_level_sets(
    playbook_dir: Path,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(meta_name_to_sha, core_name_to_sha)`` for ``*.md`` in dir."""
    meta: dict[str, str] = {}
    core: dict[str, str] = {}
    if not playbook_dir.is_dir():
        return meta, core
    for path in sorted(playbook_dir.glob("*.md")):
        legal, _illegal = parse_playbook_protection_levels(read(path))
        values = {value for _, value in legal}
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if "meta-playbook" in values:
            meta[path.name] = digest
        if "core-playbook" in values:
            core[path.name] = digest
    return meta, core


def playbook_taxonomy_parity_findings(
    edition_playbook_dirs: dict[str, Path],
    *,
    skeleton_name: str = "t2ag-skeleton",
) -> list[tuple[str, str, str]]:
    """Cross-edition findings for meta+core set/SHA and skeleton meta presence."""
    findings: list[tuple[str, str, str]] = []
    collected: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
    for name, directory in edition_playbook_dirs.items():
        collected[name] = playbook_level_sets(directory)
    if skeleton_name in collected:
        skeleton_meta, _skeleton_core = collected[skeleton_name]
        expected_meta: set[str] = set()
        for meta, _core in collected.values():
            expected_meta |= set(meta)
        missing = sorted(expected_meta - set(skeleton_meta))
        if missing:
            findings.append((
                "PB-TAXO-004",
                "FAIL",
                f"Skeleton lacks a meta-playbook: {missing}",
            ))
    if not collected:
        return findings
    reference_name = (
        skeleton_name if skeleton_name in collected else next(iter(collected))
    )
    reference_meta, reference_core = collected[reference_name]
    reference = {**reference_core, **reference_meta}
    for name, (meta, core) in collected.items():
        if name == reference_name:
            continue
        combo = {**core, **meta}
        if set(combo) != set(reference):
            findings.append((
                "PB-TAXO-003",
                "FAIL",
                f"meta+core file set divergence: {name}",
            ))
            continue
        drift = [filename for filename in reference if combo[filename] != reference[filename]]
        if drift:
            findings.append((
                "PB-TAXO-003",
                "FAIL",
                f"meta+core SHA divergence: {name} -> {drift}",
            ))
    return findings


def check_playbook_taxonomy() -> None:
    playbook_dir = MAIN / "50_playbook"
    if not playbook_dir.is_dir():
        return
    documents = {
        path.name: read(path)
        for path in sorted(playbook_dir.glob("*.md"))
    }
    for _code, severity, message in playbook_taxonomy_findings(documents):
        report(severity, message)


def check_playbook_taxonomy_parity() -> None:
    parent = ROOT.parent
    edition_dirs = {
        name: parent / name / "main/50_playbook"
        for name in distribution_release_names()
        if (parent / name / "main/50_playbook").is_dir()
    }
    if len(edition_dirs) != len(distribution_release_names()):
        return
    for _code, severity, message in playbook_taxonomy_parity_findings(edition_dirs):
        report(severity, message)


def check_playbook_usage() -> None:
    """Runtime: WARN-only depreciation scan for ordinary playbooks."""
    playbook_dir = MAIN / "50_playbook"
    course_dir = MAIN / "40_course"
    if not playbook_dir.is_dir():
        return
    has_courses = course_dir.is_dir() and any(
        child.is_dir() and not child.name.startswith("_") for child in course_dir.iterdir()
    )
    if not has_courses:
        report("INFO", "PB-USE-000 no course instance; skipping playbook depreciation (cold-start guard)")
        return
    names: set[str] = set()
    for path in sorted(playbook_dir.glob("*.md")):
        if path.name == TAXONOMY_README_EXEMPT or path.name in PLAYBOOK_USAGE_EXEMPT:
            continue
        body = read(path)
        legal, _illegal = parse_playbook_protection_levels(body)
        if {value for _, value in legal} != {"playbook"}:
            continue
        if USAGE_MANAGED_BY.search(strip_fenced_blocks(body)):
            continue
        names.add(path.name)
    if not names:
        return
    sources: list[tuple[str, str, dt.date | None]] = []
    changelog = MAIN / "00_core/t2ag_changelog.md"
    if changelog.is_file():
        sources.append(("changelog", read(changelog), None))
    journal_dir = MAIN / "60_journal"
    if journal_dir.is_dir():
        for path in sorted(journal_dir.glob("*.md")):
            sources.append((f"journal:{path.name}", read(path), None))
    handoffs = ROOT.parent / "docs" / "handoffs"
    if handoffs.is_dir():
        for path in sorted(handoffs.glob("*.md")):
            token = USAGE_DATE_TOKEN.search(path.name)
            seed = None
            if token:
                try:
                    seed = dt.date.fromisoformat(token.group(1))
                except ValueError:
                    pass
            sources.append((f"handoff:{path.name}", read(path), seed))
    last_seen = playbook_usage_last_seen(sources, frozenset(names))
    for _code, severity, message in playbook_usage_findings(
        frozenset(names), last_seen, dt.date.today()
    ):
        report(severity, message)


TIER_LEGAL_VALUES: frozenset[str] = frozenset(
    {"distant", "semi-familiar", "mastered", "远", "半熟", "精熟"}
)
TIER_TOP_VALUES: frozenset[str] = frozenset({"mastered", "精熟"})
TIER_DEFAULT_VALUES: frozenset[str] = frozenset({"distant", "远"})
TIER_TABLE_HEADINGS = ("Domain trust tiers", "领域信任档位")


def domain_tier_rows(profile_text: str) -> list[tuple[str, str, str, str]]:
    """Parse (domain, tier, evidence_ref, updated) from the profile table."""
    body = strip_fenced_blocks(profile_text)
    starts = [body.find(f"## {heading}") for heading in TIER_TABLE_HEADINGS]
    starts = [start for start in starts if start >= 0]
    if not starts:
        return []
    section = body[min(starts):]
    nxt = section.find("\n## ", 1)
    if nxt > 0:
        section = section[:nxt]
    aliases = {
        "domain": ("Domain", "领域"),
        "tier": ("Tier", "档位"),
        "evidence": ("Evidence pointer", "证据指针"),
        "updated": ("Updated", "更新日"),
    }
    header: list[str] | None = None
    rows: list[tuple[str, str, str, str]] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if header is None:
            if any(label in cells for label in aliases["domain"]) and any(
                label in cells for label in aliases["tier"]
            ):
                header = cells
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells if cell):
            continue
        record = dict(zip(header, cells))
        value = lambda key: next((record.get(label, "") for label in aliases[key] if label in record), "")
        domain = value("domain")
        if not domain or domain.startswith("<"):
            continue
        rows.append((domain, value("tier"), value("evidence").strip("`"), value("updated")))
    return rows


def domain_tier_findings(
    rows: list[tuple[str, str, str, str]],
    evidence: dict[str, str | None],
) -> list[tuple[str, str, str]]:
    """WARN-only reconciliation of declared trust tiers against evidence."""
    if not rows:
        return [(
            "TIER-000", "INFO",
            "the profile has no domain trust-tier table; skipping reconciliation (cold-start guard)",
        )]
    findings: list[tuple[str, str, str]] = []
    for domain, tier, ref, _updated in rows:
        if tier not in TIER_LEGAL_VALUES:
            findings.append(("TIER-003", "WARN", f"{domain} has an illegal tier value: {tier!r}"))
            continue
        if tier in TIER_DEFAULT_VALUES:
            continue
        body = evidence.get(ref)
        if not ref or body is None:
            detail = "empty" if not ref else f"unresolvable ({ref})"
            findings.append((
                "TIER-002", "WARN",
                f"{domain} is self-rated {tier}, but its evidence pointer is {detail}; "
                "the registration is currently an assertion with nothing to reconcile",
            ))
            continue
        if tier in TIER_TOP_VALUES and domain not in body:
            findings.append((
                "TIER-001", "WARN",
                f"{domain} is self-rated {tier}, but evidence {ref} never mentions the domain; "
                "the top-tier claim does not reconcile with the cited record",
            ))
    return findings


def check_domain_tier_reconciliation() -> None:
    """Runtime: reconcile domain trust self-ratings against their cited evidence."""
    profile_path = MAIN / "10_student/profile/profile.md"
    if not profile_path.is_file():
        return
    rows = domain_tier_rows(read(profile_path))
    evidence: dict[str, str | None] = {}
    for _domain, _tier, ref, _updated in rows:
        if not ref or ref in evidence:
            continue
        target = ROOT / ref
        evidence[ref] = read(target) if target.is_file() else None
    for _code, severity, message in domain_tier_findings(rows, evidence):
        report(severity, message)


def landing_defect(
    value: str,
    *,
    allow_open: bool,
    allow_context: bool,
    known_checks: frozenset[str] | None = None,
    main: Path | None = None,
) -> tuple[str, str] | None:
    """Verdict for one landing value; ``None`` means sound.

    Returns ``(kind, detail)`` where kind is one of ``malformed`` /
    ``dangling_check`` / ``missing_tool`` / ``broken_context`` /
    ``empty_reason``.  Existence probes are skipped when their input is
    ``None``, which keeps the function usable as a pure form checker.
    """
    value = value.strip()
    if allow_open and value == "open":
        return None
    if value.startswith("check="):
        target = value[len("check="):].strip()
        if not target:
            return ("malformed", "check= value is empty")
        if known_checks is not None and target not in known_checks:
            return (
                "dangling_check",
                f"check={target} is not in the doctor_checks key set (the value must be "
                "the full key name including the profile prefix, not a finding code)",
            )
        return None
    if value.startswith("tool="):
        target = value[len("tool="):].strip()
        if not target:
            return ("malformed", "tool= value is empty")
        if main is not None and not (main / target).is_file():
            return ("missing_tool", f"tool={target} does not exist under main/")
        return None
    if allow_context and value.startswith("context="):
        # U-1: path is relative to MAIN, split on the FIRST '#', anchor matched
        # as an exact substring (only the value's own edge whitespace is
        # stripped — no folding, no case normalisation).
        relative, separator, anchor = value[len("context="):].partition("#")
        relative, anchor = relative.strip(), anchor.strip()
        if not separator or not relative or not anchor:
            return ("malformed", "context= must be `path-relative-to-main#anchor-text`")
        if main is not None:
            target = main / relative
            if not target.is_file():
                return ("broken_context", f"the file context= points at does not exist: {relative}")
            try:
                body = read(target)
            except OSError:
                return ("broken_context", f"the file context= points at is unreadable: {relative}")
            if anchor not in body:
                return (
                    "broken_context",
                    f"the context= anchor text is no longer valid: {relative}#{anchor[:40]}",
                )
        return None
    if value.startswith("prose_accepted"):
        reason = value[len("prose_accepted"):].strip()
        if not re.fullmatch(r"[（(]\s*\S.*[）)]", reason, re.DOTALL):
            return ("empty_reason", "prose_accepted must state in parentheses why no machine means exists")
        return None
    return ("malformed", f"value is not one of the four permitted values: {value[:60]}")


RULE_ENFORCEMENT_SEVERITY = {
    "malformed": ("RULE-ENF-000", "FAIL"),
    "dangling_check": ("RULE-ENF-001", "FAIL"),
    "missing_tool": ("RULE-ENF-002", "FAIL"),
    "broken_context": ("RULE-ENF-003", "WARN"),
    "empty_reason": ("RULE-ENF-004", "WARN"),
}


def rule_enforcement_findings(
    documents: dict[str, str],
    *,
    known_checks: frozenset[str] | None = None,
    main: Path | None = None,
) -> list[tuple[str, str, str]]:
    """RULE-ENF-000..005 -- declared enforcement must be real (R-GATE §2/§3).

    ``documents`` maps a path relative to ``main/`` to its text.  Whitelisted
    rule files (``50_playbook/*.md`` plus the three 00_core model files) are
    checked for landing soundness; anything else in the mapping is only probed
    for misplacement.  Returns ``(code, severity, message)``.

    Existence-of-declaration only: this never asks "should this rule have
    declared something" — that is R4's self-referential account, already
    accepted as prose (rule_admission_gate.md §6).
    """
    findings: list[tuple[str, str, str]] = []
    for relative in sorted(documents):
        text = strip_fenced_blocks(documents[relative])
        whitelisted = relative.startswith("50_playbook/") or relative in {
            f"00_core/{name}" for name in RULE_ENFORCEMENT_CORE_FILES
        }
        for match in ENFORCEMENT_FIELD.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            if not whitelisted:
                findings.append((
                    "RULE-ENF-005",
                    "FAIL",
                    f"{relative}:{line} `enforcement:` appears in a non-rule file (the record "
                    "area is append-only and history must not be edited back; the "
                    "boundary is in rule_admission_gate.md §3)",
                ))
                continue
            defect = landing_defect(
                match.group(1),
                allow_open=False,
                allow_context=True,
                known_checks=known_checks,
                main=main,
            )
            if defect is None:
                continue
            kind, detail = defect
            code, severity = RULE_ENFORCEMENT_SEVERITY[kind]
            findings.append((code, severity, f"{relative}:{line} {detail}"))
        if whitelisted:
            for match in CLOSURE_FIELD_ANY.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append((
                    "RULE-ENF-005",
                    "FAIL",
                    f"{relative}:{line} `closure:` belongs to the problemlog only and must not appear in a rule file",
                ))
    return findings


def doctor_check_ids() -> frozenset[str] | None:
    """The `doctor_checks` key set — the one namespace `check=` may name.

    Returns ``None`` when the control file is unreadable: an unreadable
    registry is already a FAIL elsewhere, and inventing dangling-landing
    failures on top of it would just bury the real cause.
    """
    try:
        workflow = validation_control.load_workflow(
            ROOT / "main/70_tools/validation_workflow.json"
        )
    except (validation_control.ValidationControlError, OSError, ValueError):
        return None
    checks = workflow.get("doctor_checks")
    return frozenset(checks) if isinstance(checks, dict) else None


def problemlog_closure_findings(
    text: str,
    *,
    known_checks: frozenset[str] | None = None,
    main: Path | None = None,
) -> list[tuple[str, str]]:
    """PLOG-CLOSURE-000..002 — the problemlog→doctor backfill contract.

    The problemlog is this system's eval set: every entry is one recorded
    check failure.  The contract makes the conversion step mandatory —
    each new entry must declare where its enforcement landed.

    000: P-entries exist but the header lacks a readable
         `closure_fields_since: P-NNNN` anchor (fail-closed, mirrors
         GATE-LEDGER-000).  A fresh instance with no entries is silent.
    001: an entry at/after the anchor has no `- closure:` field, or the
         field value is not one of
         open / check=<doctor check ID> / tool=<tool path> / prose_accepted (reason).
    002: two-strike rule -- an entry with occurrence_count >= 2
         that lands on prose_accepted: a repeat offender may only land on
         machine enforcement (check= / tool=).  Applies wherever the field
         appears; legacy entries without the field stay exempt until the
         backfill reaches them.
    003: the same `P-NNNN` heading appears more than once.  A stable ID that
         names two different incidents makes every citation of it ambiguous
         (remediation_governance.md §3 lists stable-ID conflict and
         contradictory authorities among the non-waivable release gates).
         WARN here: runtime must not block teaching over it, and the repair
         touches history, so it is an adjudication rather than a fix.
    004: a `closure:` landing that names a check or tool which does not exist
         (R-GATE 4A).  Same defect class as RULE-ENF-001/002 but WARN, because
         this check's whole stance is WARN-only — a new check must not be used
         to quietly harden an old one.
    """
    findings: list[tuple[str, str]] = []
    entries = list(PLOG_ENTRY.finditer(text))
    if not entries:
        return findings
    seen: dict[str, list[int]] = {}
    for match in entries:
        seen.setdefault(match.group(1), []).append(
            text.count("\n", 0, match.start()) + 1
        )
    for pid, lines in seen.items():
        if len(lines) > 1:
            findings.append((
                "PLOG-CLOSURE-003",
                f"{pid} stable ID repeated {len(lines)} times (line "
                + "、".join(str(line) for line in lines)
                + "): the prose citing that ID can no longer be resolved to one entry",
            ))
    anchor = PLOG_ANCHOR.search(text)
    if not anchor:
        findings.append((
            "PLOG-CLOSURE-000",
            "problemlog lacks the closure_fields_since anchor (fail-closed): the backfill contract has no starting point",
        ))
        return findings
    anchor_num = int(anchor.group(1)[2:])
    for index, match in enumerate(entries):
        pid = match.group(1)
        pid_num = int(pid[2:])
        end = entries[index + 1].start() if index + 1 < len(entries) else len(text)
        body = text[match.start():end]
        closure_match = PLOG_CLOSURE_FIELD.search(body)
        closure = closure_match.group(1) if closure_match else None
        if closure is None:
            if pid_num >= anchor_num:
                findings.append((
                    "PLOG-CLOSURE-001",
                    f"{pid} lacks a closure field: it must declare a landing point "
                    "open/check=<ID>/tool=<path>/prose_accepted (reason)",
                ))
            continue
        if not PLOG_CLOSURE_VALUE.fullmatch(closure):
            findings.append((
                "PLOG-CLOSURE-001",
                f"{pid} closure field value is invalid: {closure[:60]}",
            ))
            continue
        defect = landing_defect(
            closure,
            allow_open=True,
            allow_context=False,
            known_checks=known_checks,
            main=main,
        )
        if defect is not None and defect[0] in ("dangling_check", "missing_tool"):
            findings.append(("PLOG-CLOSURE-004", f"{pid} {defect[1]}"))
        occurrence = PLOG_OCCURRENCE.search(body)
        if (
            occurrence
            and int(occurrence.group(1)) >= 2
            and closure.startswith("prose_accepted")
        ):
            findings.append((
                "PLOG-CLOSURE-002",
                f"{pid} two strikes: an entry with occurrence_count>=2 must not end in prose"
                f"（closure={closure[:40]}), so it must land on check= or tool=",
            ))
    return findings


def check_problemlog_closure() -> None:
    """PLOG-CLOSURE-000..002: problemlog entries must name their enforcement.

    WARN-only, same philosophy as the gate ledger: a missing landing is a
    record-keeping breach that must be visible at every doctor run, without
    blocking teaching.  The severity lives in what it protects: without this
    check, the incident log and the check registry drift apart — the same
    gate then fails a third time (P-0014 → P-0041 → P-0054).
    """
    problemlog = MAIN / "00_core/t2ag_problemlog.md"
    if not problemlog.is_file():
        return
    try:
        text = read(problemlog)
    except OSError:
        return
    for code, message in problemlog_closure_findings(
        text, known_checks=doctor_check_ids(), main=MAIN
    ):
        report("WARN", f"{code} {message}")


SOURCE_CATALOG_HEAD = re.compile(r"^source_catalog:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
SOURCE_CATALOG_ITEM = re.compile(r"^[ \t]+([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)[ \t]*$")


def source_catalog_declaration(
    text: str,
) -> tuple[str, str | dict[str, str]] | None:
    """Read the `source_catalog:` declaration; None when the course made none.

    Returns ``("inline", value)`` for the scalar form (`none (reason)`) or
    ``("block", fields)`` for the mapping form.  Hand-rolled rather than
    YAML-parsed for the same reason as the rest of this file: the frontmatter
    dialect is a small fixed subset, and a real parser would accept shapes the
    contract does not.
    """
    head = SOURCE_CATALOG_HEAD.search(text)
    if not head:
        return None
    inline = head.group(1)
    if inline:
        return ("inline", inline)
    fields: dict[str, str] = {}
    for line in text[head.end():].splitlines():
        if not line.strip():
            continue
        item = SOURCE_CATALOG_ITEM.match(line)
        if not item:
            break
        fields[item.group(1)] = item.group(2)
    return ("block", fields)


def external_source_findings(
    courses: dict[str, tuple[str, str]],
    *,
    main: Path | None = None,
) -> list[tuple[str, str, str]]:
    """EXTSRC-001..002 -- did fetching the catalogue leave a diff behind (doctor_contracts.md §9).

    ``courses`` maps course_id -> (lifecycle_status, course.md text).
    Returns ``(code, severity, message)``.

    001 (WARN): an ongoing course with no `source_catalog:`.  Deliberately NOT
        a FAIL: the predicted structure is a falsifiable prediction whose value
        is the diff produced the day the real catalogue is fetched.  Failing it
        would force "fetch on day one" and the diff would never exist — trading
        the information away for enforcement (EV-0026).
    002 (FAIL): `source_catalog:` present but `diff_recorded` missing or
        unresolvable.  Being present *claims* the comparison happened; a claim
        whose evidence cannot be found is worse than no claim (P-0067 family).
    004 (WARN): `source_catalog: none` with no reason.  `none` says "this
        course has no external catalogue to compare against" — legitimate for
        textbook- and project-driven courses, whose authority is the printed
        table of contents already in the repo.  Without it those courses would
        carry a 001 that can never be legitimately cleared, and permanent noise
        trains the reader to ignore the channel.  The reason is what keeps
        `none` from becoming a mute button, exactly as with `prose_accepted`.

    003 is a retired slot (the seed↔course edge, moved to the T1 cross-repo
    contract before implementation).  It is never reused — a reused stable ID
    makes every citation of it ambiguous (P-0072).

    Anchor semantics are not re-implemented here — `landing_defect` owns them,
    so `diff_recorded` and `enforcement: context=` can never drift apart.
    """
    findings: list[tuple[str, str, str]] = []
    for course_id in sorted(courses):
        lifecycle, text = courses[course_id]
        declaration = source_catalog_declaration(text)
        if declaration is None:
            if lifecycle == "ongoing":
                findings.append((
                    "EXTSRC-001",
                    "WARN",
                    f"{course_id} has no source_catalog: the official catalogue has not been "
                    "compared yet (a legitimate 'not yet checked' state, not a to-do; "
                    "the value is the diff produced the round you compare. If this "
                    "course has no external catalogue at all, write "
                    "`source_catalog: none (reason)`)",
                ))
            continue
        shape, payload = declaration
        if shape == "inline":
            value = str(payload).strip()
            if not value.startswith("none"):
                findings.append((
                    "EXTSRC-002",
                    "FAIL",
                    f"{course_id} source_catalog value is invalid: the inline form allows only "
                    f"`none (reason)`, actual value {value[:40]}",
                ))
                continue
            reason = value[len("none"):].strip()
            if not re.fullmatch(r"[（(]\s*\S.*[）)]", reason, re.DOTALL):
                findings.append((
                    "EXTSRC-004",
                    "WARN",
                    f"{course_id} source_catalog: none without a reason: `none` is a refutable "
                    "assertion, not an exemption pass -- state why this course has no "
                    "external catalogue to compare against",
                ))
            continue
        fields = payload if isinstance(payload, dict) else {}
        recorded = fields.get("diff_recorded", "").strip()
        if not recorded:
            findings.append((
                "EXTSRC-002",
                "FAIL",
                f"{course_id} has source_catalog but lacks diff_recorded: it claims a "
                "comparison happened with nowhere for the evidence to land "
                "(a dangling claim)",
            ))
            continue
        defect = landing_defect(
            f"context={recorded}",
            allow_open=False,
            allow_context=True,
            main=main,
        )
        if defect is not None:
            findings.append((
                "EXTSRC-002",
                "FAIL",
                f"{course_id} diff_recorded cannot be parsed: {defect[1]}",
            ))
    return findings


def check_external_source_backlink(
    courses: dict[str, tuple[Path, dict[str, str]]],
) -> None:
    """EXTSRC-001..002: declared catalogue comparisons must leave evidence.

    Empty input is silent — a distribution without course instances
    (skeleton / lite) has nothing to say here, mirroring the problemlog's
    empty-log silence and gate_ledger's skip-when-absent.

    The seed↔course edge is NOT here: it is a T1 cross-repo reference whose
    sidecar lives on the course side and is checked by
    `runtime.external_references`.  Re-implementing it would create a second
    source of truth for the same edge.
    """
    payload: dict[str, tuple[str, str]] = {}
    for course_id, (folder, meta) in courses.items():
        course_file = folder / "course.md"
        if not course_file.is_file():
            continue
        try:
            payload[course_id] = (meta.get("lifecycle_status", ""), read(course_file))
        except OSError:
            continue
    if not payload:
        return
    for code, severity, message in external_source_findings(payload, main=MAIN):
        report(severity, f"{code} {message}")


def check_rule_enforcement_integrity() -> None:
    """RULE-ENF-000..005: a declared enforcement must be a real one.

    The rule files say how each rule is enforced; this check verifies the
    saying, not the rule.  A dangling `check=`/`tool=` is a false guarantee —
    strictly worse than declaring nothing, because it buys confidence without
    buying enforcement (P-0067 family) — so those FAIL.  A stale `context=`
    anchor only means a citation rotted while the rule stands, so it WARNs:
    rewording a sentence must not block a lesson.
    """
    documents: dict[str, str] = {}
    playbook = MAIN / "50_playbook"
    if playbook.is_dir():
        for path in sorted(playbook.glob("*.md")):
            try:
                documents[f"50_playbook/{path.name}"] = read(path)
            except OSError:
                continue
    probe_targets = list(RULE_ENFORCEMENT_CORE_FILES) + ["t2ag_problemlog.md"]
    for name in probe_targets:
        path = MAIN / "00_core" / name
        if not path.is_file():
            continue
        try:
            documents[f"00_core/{name}"] = read(path)
        except OSError:
            continue
    if not documents:
        return
    for code, severity, message in rule_enforcement_findings(
        documents, known_checks=doctor_check_ids(), main=MAIN
    ):
        report(severity, f"{code} {message}")


def check_checkpoint_block_routing(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    """CKP-SCOPE-002: verify active checkpoint block_id appears in LessonMap.

    Also emits CKP-SCOPE-001 (WARN) and CKP-SCOPE-003 (WARN) as informational
    gates whose full enforcement requires multi-session comparison or a formal
    block successor model.
    """
    for course_id, (folder, meta) in courses.items():
        if meta.get("current_activity") != "lesson":
            continue
        lesson = meta.get("current_activity_id", "")
        if not re.fullmatch(r"lesson\d+", lesson):
            continue
        progress_path = folder / "progress.md"
        if not progress_path.is_file():
            continue
        try:
            progress_content = read(progress_path)
        except OSError:
            continue

        # CKP-SCOPE-002: extract current pending checkpoint and verify block_id
        ckpt_id = None
        ckpt_block = None
        in_table = False
        for line in progress_content.splitlines():
            stripped = line.strip()
            if stripped.startswith("| checkpoint_id "):
                in_table = True
                continue
            if not in_table:
                continue
            if stripped.startswith("|---"):
                continue
            if not stripped.startswith("| "):
                break
            cols = [c.strip() for c in stripped.split("|")]
            if len(cols) < 6:
                continue
            status = cols[-1] if cols[-1] else cols[-2] if len(cols) >= 7 else ""
            if status in ("pending", "arrived", "queued"):
                ckpt_id = cols[1]
                ckpt_block = cols[4] if len(cols) >= 7 else ""
                break

        if not ckpt_id:
            continue  # No active checkpoint to verify

        if not ckpt_block:
            report(
                "FAIL",
                f"CKP-SCOPE-002: the current checkpoint lacks block_id: "
                f"{course_id}/{lesson} {ckpt_id}",
            )
            continue

        # block_id format: page_key#BNN
        if "#" not in ckpt_block:
            report(
                "FAIL",
                f"CKP-SCOPE-002: block_id format is invalid (missing #): "
                f"{course_id}/{lesson} {ckpt_id} -> {ckpt_block}",
            )
            continue

        page_key = ckpt_block.split("#")[0]
        map_path = folder / "lessons" / lesson / "lesson_map.md"
        if not map_path.is_file():
            report(
                "FAIL",
                f"CKP-SCOPE-002: LessonMap is missing, so block routing cannot be verified: "
                f"{course_id}/{lesson}",
            )
            continue

        try:
            map_text = read(map_path)
        except OSError:
            report(
                "FAIL",
                f"CKP-SCOPE-002: LessonMap is unreadable: {course_id}/{lesson}",
            )
            continue

        if page_key not in map_text:
            report(
                "FAIL",
                f"CKP-SCOPE-002: the page_key of the current checkpoint block_id is not in "
                f"the LessonMap: {course_id}/{lesson} {ckpt_id} -> {page_key}",
            )
            continue

        trg = "outside_active_lesson_boundary"
        page_block_lines = [
            ln for ln in map_text.splitlines()
            if page_key in ln and "|" in ln
        ]
        if page_block_lines and trg in page_block_lines[0]:
            report(
                "FAIL",
                f"CKP-SCOPE-002: the page_key of the current checkpoint is marked "
                f"outside_active_lesson_boundary in the LessonMap: "
                f"{course_id}/{lesson} {ckpt_id} -> {page_key}",
            )

        # CKP-SCOPE-001 (WARN): multi-session comparison not available
        report(
            "WARN",
            f"CKP-SCOPE-001: verifying cross-Scope invariance of a confirmed checkpoint "
            f"needs a multi-session snapshot comparison (only a single session is "
            f"running, so it cannot be performed): {course_id}",
        )

        # CKP-SCOPE-003 (WARN): block successor model not formalised
        report(
            "WARN",
            f"CKP-SCOPE-003: exact successor mapping of LessonMap blocks needs a formal "
            f"block model plus a block migration table (only an informal block list "
            f"exists): {course_id}/{lesson}",
        )


def check_trading_boundary() -> None:
    carrier = MAIN / "10_student/engagements/EG-0001_TradingDiscipline/engagement.md"
    journal = MAIN / "10_student/engagements/EG-0001_TradingDiscipline/trade_journal.md"
    if not carrier.exists() or not journal.exists():
        return
    content = read(carrier) + "\n" + read(journal)
    required = (
        "external_refs.json#trading_os.discipline_constitution",
        "external_refs.json#trading_os.trade_event_ledger",
    )
    for pointer in required:
        if pointer not in content:
            report("FAIL", f"Trading-OS authority pointer is missing (it should point at the reference contract): {pointer}")
    if "C:/Users" in content or "C:\\Users" in content:
        report("FAIL", "Engagement body contains a host absolute path; out-of-repo paths may exist only in external_refs.json")
    if "交易行为唯一真相源" in content or "纪律唯一真相源" in content:
        report("FAIL", "A T2AG Engagement oversteps by claiming to be the Trading-OS source of truth")


EXTERNAL_REFERENCE_SCHEMA = "t2ag.external_reference.v1"
EXTERNAL_REFERENCE_KINDS = {"frozen_version", "living_data"}


def resolve_external_peer_root(hint: str) -> Path | None:
    """Resolve a peer-repo root from its host hint; fall back to sandbox mounts by basename."""
    direct = Path(hint)
    if direct.is_dir():
        return direct
    basename = hint.rstrip("/").rsplit("/", 1)[-1]
    if basename:
        for candidate in sorted(Path("/sessions").glob(f"*/mnt/{basename}")):
            if candidate.is_dir():
                return candidate
    return None


def describe_mount_surface() -> str:
    """List what this environment actually has mounted, for unresolvable-root reports.

    A root that will not resolve is the one place doctor knows least: "peer repo
    moved", "peer repo deleted" and "host has not mounted it" all land here and are
    indistinguishable from inside.  Printing the mount surface lets the reader tell
    them apart in one glance instead of guessing -- and guessing here has a known
    bad outcome, because the plausible guess ("it moved") invites deleting a
    reference whose binding is in fact healthy.  See EA-0005.
    """
    names: list[str] = []
    sessions = Path("/sessions")
    if sessions.is_dir():
        names = sorted(
            {
                p.name
                for p in sessions.glob("*/mnt/*")
                if p.is_dir() and not p.name.startswith(".")
            }
        )
    return "、".join(names) if names else "(this environment has no /sessions mount surface, or is a native host)"


def check_external_references() -> None:
    """T1 reference contract (cross_repo_reference.md): broken link = FAIL, pinned drift = WARN."""
    sidecars = sorted(MAIN.rglob("external_refs.json"))
    for sidecar in sidecars:
        try:
            payload = json.loads(read(sidecar))
        except json.JSONDecodeError as error:
            report("FAIL", f"external reference sidecar cannot be parsed: {rel(sidecar)}（{error}）")
            continue
        if not isinstance(payload, dict) or payload.get("schema") != EXTERNAL_REFERENCE_SCHEMA:
            report("FAIL", f"external reference sidecar does not match the schema: {rel(sidecar)}")
            continue
        hints = payload.get("peer_root_hints")
        references = payload.get("references")
        if not isinstance(hints, dict) or not hints or not isinstance(references, list) or not references:
            report("FAIL", f"external reference sidecar lacks peer_root_hints or references: {rel(sidecar)}")
            continue
        roots: dict[str, Path | None] = {}
        hint_by_system: dict[str, str] = {}
        for system, entry in hints.items():
            hint = entry.get("windows_host") if isinstance(entry, dict) else None
            if isinstance(hint, str) and hint:
                hint_by_system[system] = hint
            roots[system] = (
                resolve_external_peer_root(hint) if isinstance(hint, str) and hint else None
            )
        for reference in references:
            if not isinstance(reference, dict):
                report("FAIL", f"external reference entry is not an object: {rel(sidecar)}")
                continue
            label = f"{rel(sidecar)}#{reference.get('reference_id', '<missing>')}"
            peer_system = reference.get("peer_system")
            relative = reference.get("peer_relative_path")
            kind = reference.get("kind")
            integrity = reference.get("integrity_mode")
            if not isinstance(peer_system, str) or not isinstance(relative, str) or not relative:
                report("FAIL", f"external reference lacks peer_system/peer_relative_path: {label}")
                continue
            if "\\" in relative or ":" in relative or relative.startswith("/") or ".." in relative.split("/"):
                report("FAIL", f"external reference relative path violates the lexical rules (drive letter / backslash / ../ / absolute path): {label}")
                continue
            if kind not in EXTERNAL_REFERENCE_KINDS:
                report("FAIL", f"external reference kind is invalid: {label}")
                continue
            if kind == "frozen_version" and (
                integrity != "pinned"
                or not reference.get("content_sha256")
                or not reference.get("peer_version")
            ):
                report("FAIL", f"frozen_version requires pinned + content_sha256 + peer_version: {label}")
                continue
            if kind == "living_data" and (
                integrity != "existence_only" or reference.get("usage_rule") != "copy_on_use"
            ):
                report("FAIL", f"living_data requires existence_only + copy_on_use: {label}")
                continue
            if peer_system not in roots:
                report("FAIL", f"external reference peer_system has no matching root hint: {label}")
                continue
            root = roots[peer_system]
            if root is None:
                # State the fact, not a conclusion: from here "moved", "deleted" and
                # "not mounted" are the same observation.  Severity stays FAIL — a
                # peer repo that is gone entirely also lands in this branch, and
                # demoting it would turn total peer loss into an ignorable WARN.
                report(
                    "FAIL",
                    f"external reference root cannot be resolved: {label}"
                    f"; hint path {hint_by_system.get(peer_system, '(windows_host missing)')} "
                    f"does not exist in this environment; current mounts: "
                    f"{describe_mount_surface()}"
                    "; -> first confirm whether the peer is mounted (declared "
                    "connected != actually mounted; mounting can be lazy, see EA-0005)"
                    "; only if it is still unreachable after mounting may you judge it "
                    "moved or gone"
                    "; in neither case may you delete the reference identity "
                    "(cross_repo_reference.md §4)",
                )
                continue
            target = root / relative
            if not target.is_file():
                report("FAIL", f"external reference is broken; the target does not exist: {label} → {relative}")
                continue
            if integrity == "pinned":
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                pinned = str(reference.get("content_sha256"))
                if digest != pinned:
                    report(
                        "WARN",
                        f"external reference drift: {label} binding {pinned[:12]}... actual {digest[:12]}…；"
                        "the peer may have been revised and needs an explicit manual rebind "
                        "(cross_repo_reference.md §4)",
                    )


def is_historical_lesson_body(path: Path) -> bool:
    return "lessons" in path.parts and (
        re.fullmatch(r"lesson\d+\.md", path.name) is not None
        or path.name in {"thinking.txt", "lesson_thoughts.md"}
    )


def active_scan_paths() -> list[Path]:
    roots = [
        MAIN / "t2ag.md", MAIN / "00_core/domain_model.md",
        MAIN / "00_core/learning_activity_model.md",
        MAIN / "00_core/t2ag_memory.md", MAIN / "10_student",
        MAIN / "20_teacher", MAIN / "30_group", MAIN / "40_course",
        MAIN / "50_playbook", MAIN / "70_tools", MAIN / "80_interface",
        MAIN / "bin",
        ROOT / "README.md", ROOT / "AGENTS.md",
        ROOT / "cloud/cloud_sync_state.md", ROOT / "cloud/t2ag_mobile_entry.md",
    ]
    result: list[Path] = []
    for root in roots:
        if root.is_file():
            result.append(root)
        elif root.exists():
            for path in root.rglob("*"):
                if not path.is_file() or (
                    path.suffix.lower() not in {".md", ".py", ".ps1", ".json", ".yaml", ".yml"}
                    and path.name != "t2ag"
                ):
                    continue
                if path.name in {
                    "artifact_registry.json", "legacy_r_registry.json",
                    "migrate_020.py", "t2ag_doctor.py",
                }:
                    continue
                if is_historical_lesson_body(path):
                    # Lesson bodies are append-only classroom evidence and may
                    # quote historical paths; active lesson routing is checked
                    # through progress/frontmatter invariants instead.
                    continue
                result.append(path)
    return result


def check_legacy_references() -> None:
    hits = 0
    for path in active_scan_paths():
        content = read(path)
        found = [token for token in LEGACY_REFERENCES if token in content]
        if found:
            hits += len(found)
            report("FAIL", f"active old-path residue: {rel(path)} -> {found[:3]}")
    report("INFO", f"legacy_path_hits_total: {hits}")


def check_retired_instance_ids() -> None:
    roots = [
        MAIN / "10_student", MAIN / "20_teacher", MAIN / "30_group",
        MAIN / "40_course", MAIN / "50_playbook",
        ROOT / "README.md", ROOT / "AGENTS.md",
        ROOT / "cloud/T2AG_PROJECT_INSTRUCTIONS.txt",
        ROOT / "cloud/t2ag_mobile_entry.md",
    ]
    pattern = re.compile(r"\b(?:S001|S002|CR-S002|FP-S002|AR-S002)\b")
    hits = 0
    for root in roots:
        paths = [root] if root.is_file() else (
            [p for p in root.rglob("*") if p.is_file()] if root.exists() else []
        )
        for path in paths:
            if is_historical_lesson_body(path):
                continue
            if path.suffix.lower() not in {".md", ".txt", ".yaml", ".yml"}:
                continue
            found = sorted(set(pattern.findall(read(path))))
            if found:
                hits += len(found)
                report(
                    "FAIL",
                    f"active retired instance ID: {rel(path)} -> {found}",
                )
    report("INFO", f"retired_instance_id_hits_total: {hits}")


def run_check(script: str, args: list[str], label: str) -> None:
    path = MAIN / "70_tools" / script
    if not path.exists():
        report("FAIL", f"missing tool: {script}")
        return
    proc = subprocess.run(
        [sys.executable, "-B", str(path), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode:
        detail = (proc.stdout + proc.stderr).strip().splitlines()
        report("FAIL", f"{label} failed: " + ("；".join(detail[-3:]) if detail else f"exit {proc.returncode}"))


def check_flow_and_guide() -> None:
    flow_path = MAIN / "50_playbook/t2ag_flow.md"
    guide = ROOT / "t2ag_directory_guide.html"
    if not flow_path.is_file() or not guide.is_file():
        report("FAIL", "the flow source or the offline guide is missing")
        return
    content = read(flow_path)
    opens = re.findall(r"^<!-- FLOW:([a-z0-9_]+) -->\s*$", content, re.MULTILINE)
    closes = re.findall(r"^<!-- /FLOW:([a-z0-9_]+) -->\s*$", content, re.MULTILINE)
    if len(opens) != len(set(opens)) or set(opens) != EXPECTED_FLOWS:
        report("FAIL", f"FLOW set is not the agreed nine diagrams: actual={sorted(opens)}")
    if opens != closes:
        report("FAIL", "FLOW open/close markers are not paired in order")
    blocks = re.findall(
        r"^<!-- FLOW:([a-z0-9_]+) -->\s*$(.*?)^<!-- /FLOW:\1 -->\s*$",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if len(blocks) != len(EXPECTED_FLOWS):
        report("FAIL", f"FLOW parsable block count is wrong: {len(blocks)}")
    # All nine figures are character diagrams. The previous rule counted Mermaid
    # blocks and required a matching static-SVG count — which went vacuous the
    # moment the count reached zero. Assert the intended state directly instead:
    # every block is ```text, and no rendering scaffolding survives in the guide.
    non_text = sorted(
        flow_id
        for flow_id, block in blocks
        if not block.strip().startswith("```text")
    )
    if non_text:
        report(
            "FAIL",
            f"FLOW block is not a ```text character figure (the guide side has no rendering layer): {non_text}",
        )
    html_text = read(guide)
    forbidden = (
        "cdn.jsdelivr.net/npm/mermaid",
        "mermaid.initialize(",
        'class="mermaid"',
        '<svg class="flow-svg"',
        '<details class="flow-diagram"',
        '<details class="flow-source"',
    )
    present = [token for token in forbidden if token in html_text]
    if present:
        report("FAIL", f"the offline guide still contains a Mermaid/SVG rendering layer: {present}")
    ascii_count = html_text.count('<pre class="flow-ascii"')
    if ascii_count < len(EXPECTED_FLOWS):
        report(
            "FAIL",
            f"the offline guide has too few character figures: expected>={len(EXPECTED_FLOWS)} actual={ascii_count}",
        )
    for flow_id in EXPECTED_FLOWS:
        if f"FLOW:{flow_id}" not in content:
            report("FAIL", f"the flow source lacks FLOW:{flow_id}")
    for anchor in ("preface", "directory_map", "flow_first_run", "flow_panorama", "flow_catalog"):
        if html_text.count(f"T2AG_GENERATED:{anchor}") != 2:
            report("FAIL", f"an offline guide generation anchor is not closed: {anchor}")
    # The guide's kicker and footer sit outside every T2AG_GENERATED anchor, so
    # build_guide.py never touches them and a version bump silently leaves them
    # behind. Skeleton shipped 0.2.2 there while its constitution already said
    # 0.2.3 — the one number an external reader checks first.
    constitution = MAIN / "t2ag.md"
    runtime_version = (
        extract_runtime_version(read(constitution)) if constitution.is_file() else None
    )
    if runtime_version:
        stale = sorted(
            {
                found
                for found in re.findall(r"T2AG[^0-9\n]{0,24}?(\d+\.\d+\.\d+)", html_text)
                if found != runtime_version
            }
        )
        if stale:
            report(
                "FAIL",
                f"offline guide version drift: guide={stale} runtime={runtime_version}"
                "(the kicker/footer sit outside the generation anchors and must be synchronized by hand)",
            )
        if f"T2AG / Directory Guide / {runtime_version}" not in html_text:
            report("FAIL", f"the offline guide lacks the current version marker: {runtime_version}")
    flow_title = re.match(r"#\s*T2AG\s+(\d+\.\d+\.\d+)\s", content)
    if runtime_version and flow_title and flow_title.group(1) != runtime_version:
        report(
            "FAIL",
            f"flow source title version drift: flow={flow_title.group(1)} runtime={runtime_version}",
        )
    # Character diagrams are wide monospace blocks; on a phone they must scroll
    # inside their own box rather than stretch the page.
    # Selector-list tolerant on purpose: the flow diagrams and the directory tree
    # share one rule, so the pattern must not assume `.flow-ascii` stands alone.
    scrollable_ascii = bool(
        re.search(
            r"\.flow-ascii[^{}]*\{[^}]*overflow-x\s*:\s*auto",
            html_text,
            re.DOTALL,
        )
    )
    if ascii_count and not scrollable_ascii:
        report("FAIL", "offline guide character figures lack controlled horizontal scrolling (.flow-ascii overflow-x: auto)")


RECOMPUTE_SOURCE_MARKER = "←"
VERIFIABLE_ASSERTION_PATTERNS = (
    # LV-5: a counted claim in either edition -- "89 个脏文件" / "89 dirty files".
    re.compile(
        r"\d+\s*个|\b\d+\s+(?:\w+\s+){0,2}"
        r"(?:files?|items?|entries|lines?|rows?|hits?|occurrences?)\b"
    ),
    # LV-5: a stale-claim marker written in either language edition.
    re.compile(marker_alternation("零命中"), re.IGNORECASE),
    re.compile(r"sha256\s*[:：]"),
)


def unsourced_handoff_assertions(content: str) -> list[tuple[int, str]]:
    """Return (1-based line, text) for quantity/existence/hash assertions with no source.

    handoff_management.md §5.6 requires that a taker can *replay* the number, not
    merely that the writer once saw it.  The gate therefore proves one thing only:
    a recompute command is adjacent to the claim.  Which command forms count is
    declared in §5.6.2, not here — this function does not judge command quality.

    Deliberately mechanical: fenced code and ATX headings are skipped because they
    are structure rather than claims, but quoted or retrospective prose is NOT
    exempt (§5.6.4).  A gate that guesses at tone is a gate nobody can predict.
    """
    lines = content.splitlines()
    fenced = False
    hits: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or re.match(r"^#{1,6}\s", line):
            continue
        if not any(pattern.search(line) for pattern in VERIFIABLE_ASSERTION_PATTERNS):
            continue
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if RECOMPUTE_SOURCE_MARKER in line or RECOMPUTE_SOURCE_MARKER in following:
            continue
        hits.append((index + 1, line.strip()))
    return hits


def check_handoff_contract() -> None:
    if FLAVOR != "main":
        return
    handoff_root = ROOT.parent / "docs/handoffs"
    index = handoff_root / "README.md"
    if not index.is_file():
        return
    index_content = read(index)
    shadow_index = ROOT / "docs/handoffs/README.md"
    if shadow_index.is_file() and shadow_index.resolve() != index.resolve():
        shadow_content = read(shadow_index)
        if re.search(r"^##\s+Active Handoffs\s*$", shadow_content, re.MULTILINE):
            report(
                "FAIL",
                "the in-instance docs/handoffs/README.md duplicates Active Handoffs; the "
                "workspace already registers the single runtime index, so the "
                "instance may keep only a non-runtime locator page",
            )
    declared_version = re.search(r"(?:当前版本为|the current version is)\s*`?([0-9]+(?:\.[0-9]+)+)`?", index_content)
    constitution = ROOT / "main/t2ag.md"
    runtime_version = extract_runtime_version(read(constitution)) if constitution.is_file() else None
    if declared_version and runtime_version and declared_version.group(1) != runtime_version:
        report(
            "FAIL",
            "handoff index version drift: "
            f"index={declared_version.group(1)} runtime={runtime_version}",
        )
    required_headings = (
        "Active Handoffs",
        "下一版本 Backlog",
        "Workorders / Plans",
        "Evidence / Reviews",
        "Resolved / Archive Handoffs",
    )
    for heading in required_headings:
        # Registry-aware: a translated index carries the same section under its own
        # heading, and pinning one spelling here would FAIL a valid index (L3).
        if not heading_re(heading).search(index_content):
            report("FAIL", f"handoff index lacks a classification section: {heading}")
    rows = table_after_heading(index_content, "Active Handoffs")
    active_lanes = {row.get("lane", "") for row in rows}
    for absent_lane in re.findall(r"(?:当前没有 active|there is currently no active)\s+`([^`]+)`", index_content):
        if absent_lane in active_lanes:
            report("FAIL", f"handoff index is self-contradictory: {absent_lane} registered active while also declaring non-existence")
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    seen_scopes: set[tuple[str, str]] = set()
    required = {
        "handoff_id", "scope", "lane", "artifact_role", "applies_to", "status",
        "aging_state", "task_match", "created_at", "updated_at", "version_context",
        "supersedes", "superseded_by", "close_condition", "canonical_sources",
        "next_action", "semantic_check",
    }
    allowed_scopes = {"course_session", "project", "topic", "implementation"}
    allowed_lanes = {"learning", "maintenance", "topic_design", "version_campaign"}
    for row in rows:
        handoff_id = row.get("handoff_id", "")
        filename = row_value(row, "文件").strip("` ")
        key = (row.get("scope", ""), row.get("applies_to", ""))
        if (
            not handoff_id
            or not filename
            or not all(key)
            or row.get("lane") not in allowed_lanes
            or row.get("artifact_role") != "handoff"
            or row.get("status") != "active"
        ):
            report("FAIL", f"active handoff index lacks a required cell: {handoff_id or filename or '?'}")
            continue
        if row["scope"] not in allowed_scopes:
            report("FAIL", f"active handoff scope is invalid: {handoff_id} -> {row['scope']}")
        if handoff_id in seen_ids or filename in seen_files or key in seen_scopes:
            report("FAIL", f"active handoff index has duplicates: {handoff_id}")
        seen_ids.add(handoff_id)
        seen_files.add(filename)
        seen_scopes.add(key)
        path = handoff_root / filename
        if not path.is_file():
            report("FAIL", f"active handoff file is dangling: {filename}")
            continue
        content = read(path)
        metadata = {
            field: match.group(1).strip()
            for field in required
            if (match := re.search(rf"^>\s*\*\*{re.escape(field)}\*\*[：:]\s*(.*?)\s*$", content, re.MULTILINE))
        }
        missing = sorted(required - set(metadata))
        if missing:
            report("FAIL", f"active handoff lacks metadata {missing}：{filename}")
            continue
        if metadata["status"] != "active":
            report("FAIL", f"the active index points at a non-active document: {filename}")
        if metadata["artifact_role"] != "handoff":
            report("FAIL", f"the active index points at a non-handoff role: {filename}")
        if metadata["lane"] not in allowed_lanes:
            report("FAIL", f"active handoff lane is invalid: {filename} -> {metadata['lane']}")
        if metadata["scope"] == "course_session" and metadata["lane"] != "learning":
            report("FAIL", f"a course_session handoff must belong to the learning lane: {filename}")
        if not heading_re("最小状态摘要").search(content):
            report("FAIL", f"active handoff lacks the minimum-state-summary layer: {filename}")
        if not heading_re("连续性摘要").search(content):
            report("FAIL", f"active handoff lacks the continuity-summary layer: {filename}")
        for field in (
            "handoff_id", "scope", "lane", "artifact_role", "status", "applies_to", "updated_at"
        ):
            index_field = row.get(field, "")
            if index_field and metadata[field] != index_field:
                report("FAIL", f"handoff index and document {field} mismatch: {filename}")
        line_count = len(content.splitlines())
        char_count = len(content)
        expected_aging = (
            "old" if line_count >= 1000 or char_count >= 90000 else
            "check_2" if line_count >= 700 or char_count >= 60000 else
            "check_1" if line_count >= 350 or char_count >= 30000 else
            "normal"
        )
        if metadata["aging_state"] != expected_aging:
            report(
                "FAIL",
                f"handoff aging_state drift: {filename} expected={expected_aging} actual={metadata['aging_state']}",
            )
        for line_number, text in unsourced_handoff_assertions(content):
            excerpt = text if len(text) <= 80 else f"{text[:80]}…"
            report(
                "WARN",
                f"handoff assertion has no recomputation source (handoff_management.md §5.6): {filename}:{line_number} -> {excerpt}",
            )

    backlog_rows = heading_rows(index_content, "下一版本 Backlog")
    for row in backlog_rows:
        item_id = row.get("id", "")
        filename = row_value(row, "文件").strip("` ")
        role = row.get("artifact_role", "")
        if (
            not item_id
            or not filename
            or row.get("lane") != "version_campaign"
            or "release_backlog" not in {part.strip() for part in role.split("+")}
            or row.get("status") != "pending_next_candidate"
        ):
            report("FAIL", f"next-version backlog classification is invalid: {item_id or filename or '?'}")
            continue
        if filename in seen_files:
            report("FAIL", f"release backlog is also registered as an active handoff: {filename}")
        if not (handoff_root / filename).is_file():
            report("FAIL", f"release backlog file is dangling: {filename}")

    closed_rows = table_after_heading(index_content, "Resolved / Archive Handoffs")
    for row in closed_rows:
        handoff_id = row.get("handoff_id", "")
        filename = row_value(row, "文件").strip("` ")
        if (
            not handoff_id
            or not filename
            or row.get("artifact_role") != "handoff"
            or row.get("status") == "active"
            or row.get("lane") not in allowed_lanes
        ):
            report("FAIL", f"historical handoff classification is invalid: {handoff_id or filename or '?'}")
            continue
        if handoff_id in seen_ids or filename in seen_files:
            report("FAIL", f"a handoff appears in both the active and the historical index: {handoff_id}")
        if not (handoff_root / filename).is_file():
            report("FAIL", f"historical handoff file is dangling: {filename}")


def check_cloud_contract() -> None:
    cloud = ROOT / "cloud"
    state = cloud / "cloud_sync_state.md"
    components = (
        MAIN / "50_playbook/cloud_learning_sync.md",
        cloud / "T2AG_PROJECT_INSTRUCTIONS.txt",
        state,
        cloud / "README.md",
        cloud / "outbox",
        cloud / "inbox",
        cloud / "inbox/README.md",
    )
    missing = [rel(path) for path in components if not path.exists()]
    if missing:
        report("FAIL", f"Cloud protocol component is missing: {missing}")
        return
    state_text = read(state)
    required = (
        "protocol_version: T2AG-CLOUD-1", "privacy_model: two_scope",
        "automatic_sync_allowlist_status: approved_minimal_low_risk",
        "current_cloud_project_mode:", "cloud_bridge_status: paused",
        "current_base_state_id:", "## 已处理会话", "## 部件变更指令", "## 云端交接",
    )
    absent = missing_markers(state_text, required)
    if absent:
        report("FAIL", f"Cloud paused state lacks a contract field: {absent}")
    prompt = read(cloud / "T2AG_PROJECT_INSTRUCTIONS.txt")
    playbook = read(MAIN / "50_playbook/cloud_learning_sync.md")
    for token in ("T2AG-CLOUD-1", "T2AG_SESSION_CLOSE", "T2AG_CLOUD_CHANGE_DIRECTIVE", "T2AG_CLOUD_HANDOFF"):
        if token not in playbook:
            report("FAIL", f"Cloud protocol lacks a shared identifier: {token}")
        if FLAVOR != "skeleton" and token not in prompt:
            report("FAIL", f"Cloud personal-instance prompt lacks a shared identifier: {token}")
    if FLAVOR == "skeleton":
        # LV-5 (2026-08-20): the entry surface ships in translated editions.  A
        # boundary marker is satisfied by ANY accepted language variant; this is a
        # widening only -- the original zh-CN literal still passes unchanged.  The
        # alternative (grepping one language) fails closed on the wrong axis: a
        # correctly-bounded English Skeleton would report a missing boundary.
        for token in (
            "cloud_project_mode: generic_skeleton",
            "不得生成教学 receipt",
            "paused",
        ):
            if not has_marker(prompt, token):
                report("FAIL", f"Cloud Skeleton prompt lacks an isolation boundary: {token}")
    if FLAVOR == "main":
        for token in ("new_cloud_sessions_allowed: false", "new_component_directives_allowed: false"):
            if token not in state_text:
                report("FAIL", f"Cloud pause gate lacks a field: {token}")
        registered_cd = set(re.findall(r"\|\s*(CD-\d{8}-\d{4})\s*\|", state_text))
        registered_ch = set(re.findall(r"\|\s*(CH-\d{8}-\d{4})\s*\|", state_text))
        outbox_ids = {path.stem for path in (cloud / "outbox").glob("CD-*.md")}
        inbox_ids = {path.stem for path in (cloud / "inbox").glob("CH-*.md")}
        if outbox_ids - registered_cd:
            report("FAIL", f"Cloud outbox directive is not registered: {sorted(outbox_ids - registered_cd)}")
        if inbox_ids - registered_ch:
            report("FAIL", f"Cloud inbox handoff is not registered: {sorted(inbox_ids - registered_ch)}")
        _check_cloud_ledger_invariants(state_text, outbox_ids, inbox_ids)
        _check_cloud_instructions_regeneration()
        _check_cloud_skeleton_leak()


def _check_cloud_ledger_invariants(
    state_text: str, outbox_ids: set[str], inbox_ids: set[str]
) -> None:
    """EV-0021: ledger frontmatter matches the three tables, no new events after paused, and every table registration has a backing file."""
    from datetime import datetime

    def front(field: str) -> str | None:
        m = re.search(rf"^-\s*{field}:\s*(.+?)\s*$", state_text, re.MULTILINE)
        return m.group(1) if m else None

    def table_rows(header: str) -> list[list[str]]:
        # LV-5: `header` arrives in its canonical zh-CN spelling; a translated
        # ledger carries the same section under its English heading.
        alt = "|".join(
            re.escape(name.lstrip("# ")) for name in marker_spellings(f"## {header}")
        )
        m = re.search(rf"^##\s+(?:{alt})\s*$([\s\S]*?)(?=^##\s|\Z)", state_text, re.MULTILINE)
        rows = []
        if m:
            for line in m.group(1).splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) >= 4 and re.match(r"(CD|CH|CLOUD)-", cells[0]):
                    rows.append(cells)
        return rows

    cd_rows = table_rows("部件变更指令")
    ch_rows = table_rows("云端交接")
    session_rows = table_rows("已处理会话")

    # 1) frontmatter last_* agrees with the tables
    last_cd, last_cd_status = front("last_change_directive_id"), front("last_change_directive_status")
    if last_cd:
        row = next((r for r in cd_rows if r[0] == last_cd), None)
        if row is None:
            report("FAIL", f"Cloud ledger: last_change_directive_id {last_cd} is not in the directive table")
        elif last_cd_status and last_cd_status not in row[3]:
            report("FAIL", f"Cloud ledger: {last_cd} frontmatter status {last_cd_status} and table {row[3]} mismatch")
    last_ch, last_ch_status = front("last_cloud_handoff_id"), front("last_cloud_handoff_status")
    if last_ch:
        row = next((r for r in ch_rows if r[0] == last_ch), None)
        if row is None:
            report("FAIL", f"Cloud ledger: last_cloud_handoff_id {last_ch} is not in the handoff table")
        elif last_ch_status and last_ch_status not in row[3]:
            report("FAIL", f"Cloud ledger: {last_ch} frontmatter adjudication {last_ch_status} and table {row[3]} mismatch")
    last_session = front("last_synced_session_id")
    if last_session and not any(r[0] == last_session for r in session_rows):
        report("FAIL", f"Cloud ledger: last_synced_session_id {last_session} is not in the session table")

    # 2) table registrations -> reverse-checked against the channel files
    for row in cd_rows:
        if row[0] not in outbox_ids:
            report("FAIL", f"Cloud ledger registers a directive with no outbox file: {row[0]}")
    for row in ch_rows:
        if row[0] not in inbox_ids:
            report("FAIL", f"Cloud ledger registers a handoff with no inbox file: {row[0]}")

    # 3) no new events after paused
    paused_at = front("cloud_bridge_paused_at")
    if front("cloud_bridge_status") == "paused" and paused_at:
        try:
            pause_dt = datetime.fromisoformat(paused_at)
        except ValueError:
            report("FAIL", f"Cloud ledger: cloud_bridge_paused_at is not an ISO time: {paused_at}")
            return
        for rows, col, label in ((session_rows, 1, "会话"), (cd_rows, 1, "指令"), (ch_rows, 2, "交接")):
            for row in rows:
                try:
                    event_dt = datetime.fromisoformat(row[col])
                except (ValueError, IndexError):
                    continue
                if event_dt > pause_dt:
                    report("FAIL", f"Cloud pause invariant is broken: {label} {row[0]} is later than paused_at")


def _check_cloud_instructions_regeneration() -> None:
    """EV-0021: instructions must equal the regeneration of template + mobile_entry."""
    import sync_cloud

    for level, message in sync_cloud.run_checks(ROOT):
        if level != "INFO":
            report(level, message)


def _check_cloud_skeleton_leak() -> None:
    """EV-0021: the Skeleton open-source surface (cloud/ and protocol templates) must carry no instance traces."""
    skeleton = ROOT.parent / "t2ag-skeleton"
    if not skeleton.is_dir():
        report("INFO", "cloud leak scan: t2ag-skeleton is not mounted, skipping")
        return
    entry = ROOT / "cloud/t2ag_mobile_entry.md"
    state = ROOT / "cloud/cloud_sync_state.md"
    tokens: set[str] = set()
    corpus = ""
    if entry.exists():
        corpus += read(entry)
    if state.exists():
        corpus += read(state)
    for field in ("reply_suffix", "course"):
        m = re.search(rf"^-\s*{field}:\s*(\S+)\s*$", corpus, re.MULTILINE)
        if m:
            tokens.add(m.group(1))
    tokens.update(re.findall(r"\bBS-[A-Z0-9]+-\d{8}-\d{4}\b", corpus))
    tokens.update(re.findall(r"\bCLOUD-[A-Z0-9]+-\d{8}T\d{6}[+-]\d{4}-[A-Z0-9]{4}\b", corpus))
    tokens.update(re.findall(r"\b(?:CD|CH)-\d{8}-\d{4}\b", corpus))
    targets = [skeleton / "main/50_playbook/cloud_instructions_template.md"]
    targets += [p for p in (skeleton / "cloud").rglob("*") if p.is_file()]
    for path in targets:
        if not path.exists() or path.suffix not in {".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = sorted(tok for tok in tokens if tok and tok in text)
        if hits:
            report("FAIL", f"Cloud leak: the Skeleton open-source surface {path.name} carries instance traces {hits}")


def check_derived_tools() -> None:
    run_check("t2ag_state_refresh.py", ["--check"], "state refresh")
    run_check("build_journal_index.py", ["--check"], "journal index")
    if FLAVOR != "lite":
        run_check("build_guide.py", [], "offline guide")
    if FLAVOR != "lite":
        args = ["--check"] if FLAVOR == "main" else ["--check", "--target", "skeleton"]
        run_check("migrate_020.py", args, "migration idempotence")
        run_check("migrate_021.py", ["--check"], "0.2.1 profile migration idempotence")
        run_check(
            "migrate_021_activity_records.py",
            ["--check"],
            "0.2.1 ActivityRecord migration idempotence",
        )


def check_migration_evidence() -> None:
    if FLAVOR == "lite":
        return
    if FLAVOR == "skeleton":
        # EV-0023: the Skeleton is a new-instance starting point and carries no
        # maintainer 0.2.0 migration archive (same precedent as :3793).
        for rel in (
            "main/60_journal/migration_020_operations.json",
            "main/60_journal/migration_020_report.json",
            "main/60_journal/migration_020_review.md",
            "main/60_journal/retired_020_sources",
        ):
            if (ROOT / rel).exists():
                report("FAIL", f"Skeleton must not copy Main 0.2.0 migration evidence: {rel}")
        return
    readme_content = read(ROOT / "README.md") if (ROOT / "README.md").is_file() else ""
    migration_target_kind = (
        "skeleton"
        if ROOT.name == "t2ag-skeleton"
        or re.search(r"^# T2AG .* Skeleton\s*$", readme_content, re.MULTILINE)
        else "main"
    )
    _, _, errors = validated_migration_evidence(migration_target_kind)
    for error in errors:
        report("FAIL", error)


def check_migration_021_evidence() -> None:
    if FLAVOR == "lite":
        return
    if FLAVOR == "skeleton":
        # EV-0023: the Skeleton carries no maintainer 0.2.1 profile migration
        # archive (same precedent as :3793).
        for rel in (
            "main/60_journal/migration_021_profile_operations.json",
            "main/60_journal/migration_021_profile_report.json",
            "main/60_journal/migration_021_profile_operations_v2.json",
            "main/60_journal/migration_021_profile_report_v2.json",
        ):
            if (ROOT / rel).exists():
                report("FAIL", f"Skeleton must not copy Main 0.2.1 profile migration evidence: {rel}")
        return
    def strict_json(path: Path) -> object:
        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if key in result:
                    raise ValueError(f"duplicate key: {key}")
                result[key] = value
            return result

        def constant(value: str) -> object:
            raise ValueError(f"non-finite number: {value}")

        raw = path.read_bytes()
        if b"\x00" in raw:
            raise ValueError("NUL")
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )

    def exact_keys(value: object, expected: set[str], where: str) -> bool:
        if not isinstance(value, dict) or set(value) != expected:
            report("FAIL", f"0.2.1 profile V2 evidence field is invalid: {where}")
            return False
        return True

    v1_manifest_path = MAIN / "60_journal/migration_021_profile_operations.json"
    v1_report_path = MAIN / "60_journal/migration_021_profile_report.json"
    manifest_path = MAIN / "60_journal/migration_021_profile_operations_v2.json"
    report_path = MAIN / "60_journal/migration_021_profile_report_v2.json"
    required_paths = (v1_manifest_path, v1_report_path, manifest_path, report_path)
    if any(not path.is_file() for path in required_paths):
        report("FAIL", "missing the 0.2.1 profile V1/V2 migration operation manifest or report")
        return
    try:
        v1_manifest = strict_json(v1_manifest_path)
        v1_report = strict_json(v1_report_path)
        manifest = strict_json(manifest_path)
        migration_report = strict_json(report_path)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        report("FAIL", f"0.2.1 profile migration evidence strict JSON is invalid: {exc}")
        return
    readme_content = read(ROOT / "README.md") if (ROOT / "README.md").is_file() else ""
    expected_kind = (
        "skeleton"
        if ROOT.name == "t2ag-skeleton"
        or re.search(r"^# T2AG .* Skeleton\s*$", readme_content, re.MULTILINE)
        else "main"
    )
    baseline_oracle = {
        "main": (
            "4e72556f789fcb5943951657ee17247c0dd4eb12",
            "7270b5fa7954fec12d2e5ff3f76ee388036dff1b",
        ),
        "skeleton": (
            "3f1a42e0edc305f3253843337a9ec7a107cd79a8",
            "bab94ab06046b55577dc88908069dfbe1e160419",
        ),
    }
    expected_commit, expected_tree = baseline_oracle[expected_kind]
    if not exact_keys(
        manifest,
        {
            "schema_version", "migration_id", "supersedes", "target_kind",
            "baseline_commit", "baseline_tree", "transform_version",
            "operation_count", "operations",
        },
        "manifest",
    ) or not exact_keys(
        migration_report,
        {
            "schema_version", "migration_id", "supersedes", "status",
            "target_kind", "baseline_commit", "baseline_tree", "transform_version",
            "operation_manifest", "current_verification", "content_policy",
        },
        "report",
    ):
        return
    summary = migration_report["operation_manifest"]
    verification = migration_report["current_verification"]
    if not exact_keys(summary, {"path", "operation_count", "sha256"}, "report.operation_manifest"):
        return
    if not exact_keys(verification, {"targets_present"}, "report.current_verification"):
        return
    common_expected = (
        "T2AG-021-PROFILE-V2",
        expected_kind,
        expected_commit,
        expected_tree,
        "t2ag.profile-path-repairs.v2",
    )
    if (
        manifest.get("schema_version") != "T2AG-MIGRATION-OPERATIONS-2"
        or migration_report.get("schema_version") != "T2AG-MIGRATION-REPORT-2"
        or (
            manifest.get("migration_id"), manifest.get("target_kind"),
            manifest.get("baseline_commit"), manifest.get("baseline_tree"),
            manifest.get("transform_version"),
        ) != common_expected
        or (
            migration_report.get("migration_id"), migration_report.get("target_kind"),
            migration_report.get("baseline_commit"), migration_report.get("baseline_tree"),
            migration_report.get("transform_version"),
        ) != common_expected
        or manifest.get("supersedes") != "main/60_journal/migration_021_profile_operations.json"
        or migration_report.get("supersedes") != "main/60_journal/migration_021_profile_report.json"
        or migration_report.get("status") != "applied"
        or verification.get("targets_present") is not True
    ):
        report("FAIL", "0.2.1 profile V2 baseline/target/schema binding is invalid")
    try:
        resolved_tree = subprocess.run(
            ["git", "show", "-s", "--format=%T", expected_commit],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        report("FAIL", f"0.2.1 profile baseline cannot be parsed live: {exc}")
        return
    if resolved_tree != expected_tree:
        report("FAIL", "0.2.1 profile baseline tree disagrees with live Git resolution")
    if (
        summary.get("path") != "main/60_journal/migration_021_profile_operations_v2.json"
        or summary.get("sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        or summary.get("operation_count") != 4
    ):
        report("FAIL", "0.2.1 profile V2 report is not bound to the canonical manifest")
    operations = manifest.get("operations")
    if not isinstance(operations, list) or manifest.get("operation_count") != 4 or len(operations) != 4:
        report("FAIL", "0.2.1 profile V2 migration count is invalid")
        return
    expected_moves = (
        ("main/10_student/profile.md", "main/10_student/profile/profile.md"),
        ("main/10_student/learning_path.md", "main/10_student/profile/learning_path.md"),
        (
            "main/10_student/course_reflections.md",
            "main/10_student/profile/course_reflections.md",
        ),
        (
            "main/10_student/reasoning_patterns.md",
            "main/10_student/profile/reasoning_patterns.md",
        ),
    )
    v1_operations = v1_manifest.get("operations", []) if isinstance(v1_manifest, dict) else []
    if (
        not isinstance(v1_manifest, dict)
        or not isinstance(v1_report, dict)
        or v1_manifest.get("schema_version") != "T2AG-MIGRATION-OPERATIONS-1"
        or v1_manifest.get("baseline_commit") != expected_commit
        or v1_manifest.get("target_kind") != expected_kind
        or not isinstance(v1_operations, list)
        or len(v1_operations) != 4
        or v1_report.get("schema_version") != "T2AG-MIGRATION-REPORT-1"
        or v1_report.get("baseline_commit") != expected_commit
        or v1_report.get("target_kind") != expected_kind
        or v1_report.get("operation_manifest", {}).get("sha256")
        != hashlib.sha256(v1_manifest_path.read_bytes()).hexdigest()
    ):
        report("FAIL", "the superseded 0.2.1 profile V1 evidence is missing or has been rewritten")

    def baseline_bytes(path: str) -> bytes:
        result = subprocess.run(
            ["git", "show", f"{expected_commit}:{path}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise ValueError(path)
        return result.stdout

    def oracle(source_path: str, content: bytes) -> tuple[bytes, dict[str, int], str]:
        if expected_kind == "skeleton":
            return content, {}, f"profile-{Path(source_path).stem}-identity-v2"
        rules: tuple[tuple[bytes, bytes, int, str], ...]
        if source_path == "main/10_student/profile.md":
            rules = (
                (b"main/10_student/profile.md", b"main/10_student/profile/profile.md", 2, "self_profile"),
                (b"main/10_student/course_reflections.md", b"main/10_student/profile/course_reflections.md", 1, "course_reflections"),
                (b"main/10_student/reasoning_patterns.md", b"main/10_student/profile/reasoning_patterns.md", 1, "reasoning_patterns"),
            )
        elif source_path == "main/10_student/learning_path.md":
            rules = ((b"10_student/profile.md", b"10_student/profile/profile.md", 1, "profile_pointer"),)
        elif source_path == "main/10_student/course_reflections.md":
            rules = ((b"../40_course/", b"../../40_course/", 3, "relative_course_links"),)
        else:
            rules = ()
        counts: dict[str, int] = {}
        transformed = content
        for old, new, expected_count, name in rules:
            actual_count = transformed.count(old)
            if actual_count != expected_count:
                raise ValueError(f"count:{source_path}:{name}")
            transformed = transformed.replace(old, new)
            counts[name] = actual_count
        return transformed, counts, f"profile-{Path(source_path).stem}-path-repairs-v2"

    for sequence, (source_path, target_path) in enumerate(expected_moves, start=1):
        row = operations[sequence - 1]
        if not exact_keys(
            row,
            {
                "sequence", "transform_id", "source", "target", "replacement_counts",
                "content_policy", "outcome", "post_target",
            },
            f"operations[{sequence - 1}]",
        ):
            continue
        source = row.get("source")
        post_target = row.get("post_target")
        if not exact_keys(source, {"path", "blob", "bytes", "sha256"}, f"operations[{sequence - 1}].source"):
            continue
        if not exact_keys(post_target, {"path", "bytes", "sha256"}, f"operations[{sequence - 1}].post_target"):
            continue
        try:
            source_content = baseline_bytes(source_path)
            expected_post, expected_counts, expected_transform = oracle(source_path, source_content)
            expected_blob = subprocess.run(
                ["git", "rev-parse", f"{expected_commit}:{source_path}"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (ValueError, subprocess.CalledProcessError) as exc:
            report("FAIL", f"0.2.1 profile independent oracle failed: {exc}")
            continue
        if (
            row.get("sequence") != sequence
            or source.get("path") != source_path
            or source.get("blob") != expected_blob
            or source.get("bytes") != len(source_content)
            or source.get("sha256") != hashlib.sha256(source_content).hexdigest()
            or row.get("target") != target_path
            or row.get("transform_id") != expected_transform
            or row.get("replacement_counts") != expected_counts
            or row.get("outcome") != "applied"
            or row.get("content_policy") != ("byte_identical" if not expected_counts else "path_repairs_only")
            or post_target.get("path") != target_path
            or post_target.get("bytes") != len(expected_post)
            or post_target.get("sha256") != hashlib.sha256(expected_post).hexdigest()
        ):
            report("FAIL", f"0.2.1 profile V2 migration operations disagree with the independent oracle: sequence={sequence}")
            continue
        if sequence <= len(v1_operations):
            v1_source = v1_operations[sequence - 1].get("sources", [{}])[0]
            if (
                v1_source.get("path") != source_path
                or v1_source.get("bytes") != len(source_content)
                or v1_source.get("sha256") != hashlib.sha256(source_content).hexdigest()
            ):
                report("FAIL", f"0.2.1 profile V1/V2 source binding diverges: sequence={sequence}")
        target = ROOT / target_path
        if not target.is_file():
            report("FAIL", f"0.2.1 profile migration target does not exist: {target_path}")
            continue
        if (ROOT / source_path).exists():
            report("FAIL", f"0.2.1 profile old path still exists: {source_path}")
        # These four targets are live student records.  Their migration-time
        # hashes remain report-bound evidence, not permanent content locks.


def check_activity_migration_021_evidence() -> None:
    if FLAVOR == "lite":
        return
    manifest_path = MAIN / "60_journal/migration_021_activity_record_operations.json"
    report_path = MAIN / "60_journal/migration_021_activity_record_report.json"
    source_path = "main/10_student/activities/AR-0001_InvestingNotes.md"
    target_path = "main/10_student/activities/reading/AR-0001_InvestingNotes.md"
    if FLAVOR == "skeleton":
        if manifest_path.exists() or report_path.exists():
            report("FAIL", "Skeleton must not copy Main ActivityRecord real migration evidence")
        if (ROOT / source_path).exists() or (ROOT / target_path).exists():
            report("FAIL", "Skeleton must not contain the real AR-0001 instance")
        return
    if (
        not manifest_path.exists()
        and not report_path.exists()
        and not (ROOT / source_path).exists()
        and not (ROOT / target_path).exists()
    ):
        # A fresh instance initialized from Skeleton has no historical AR-0001
        # migration.  Real Main remains bound by its registry entry and evidence.
        return
    if not manifest_path.is_file() or not report_path.is_file():
        report("FAIL", "missing 0.2.1 ActivityRecord migration evidence")
        return

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    def constant(value: str) -> object:
        raise ValueError(f"non-finite number: {value}")

    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
        activity_report = json.loads(
            report_path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        report("FAIL", f"0.2.1 ActivityRecord migration strict JSON is invalid: {exc}")
        return
    manifest_keys = {
        "schema_version", "migration_id", "target_kind", "baseline_commit",
        "baseline_tree", "transform_version", "operation_count", "operations",
    }
    report_keys = {
        "schema_version", "migration_id", "status", "target_kind", "baseline_commit",
        "baseline_tree", "transform_version", "operation_manifest",
        "current_verification", "content_policy",
    }
    if not isinstance(manifest, dict) or set(manifest) != manifest_keys:
        report("FAIL", "0.2.1 ActivityRecord manifest field is invalid")
        return
    if not isinstance(activity_report, dict) or set(activity_report) != report_keys:
        report("FAIL", "0.2.1 ActivityRecord report field is invalid")
        return
    expected_common = (
        "T2AG-021-ACTIVITY-RECORDS-V1",
        "main",
        "4e72556f789fcb5943951657ee17247c0dd4eb12",
        "7270b5fa7954fec12d2e5ff3f76ee388036dff1b",
        "t2ag.activity-record-kind.v1",
    )
    if (
        manifest.get("schema_version") != "T2AG-ACTIVITY-MIGRATION-OPERATIONS-1"
        or activity_report.get("schema_version") != "T2AG-ACTIVITY-MIGRATION-REPORT-1"
        or (
            manifest.get("migration_id"), manifest.get("target_kind"),
            manifest.get("baseline_commit"), manifest.get("baseline_tree"),
            manifest.get("transform_version"),
        ) != expected_common
        or (
            activity_report.get("migration_id"), activity_report.get("target_kind"),
            activity_report.get("baseline_commit"), activity_report.get("baseline_tree"),
            activity_report.get("transform_version"),
        ) != expected_common
        or activity_report.get("status") != "applied"
    ):
        report("FAIL", "0.2.1 ActivityRecord baseline/target/schema binding is invalid")
    try:
        tree = subprocess.run(
            ["git", "show", "-s", "--format=%T", expected_common[2]],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        source = subprocess.run(
            ["git", "show", f"{expected_common[2]}:{source_path}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        blob = subprocess.run(
            ["git", "rev-parse", f"{expected_common[2]}:{source_path}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        report("FAIL", f"0.2.1 ActivityRecord baseline cannot be parsed live: {exc}")
        return
    marker = b"type: activity_record\n"
    old_path = source_path.encode("utf-8")
    if source.count(marker) != 1 or source.count(old_path) != 1:
        report("FAIL", "0.2.1 ActivityRecord baseline does not satisfy the independent transform oracle")
        return
    expected_post = source.replace(marker, marker + b"activity_kind: reading\n", 1).replace(
        old_path,
        target_path.encode("utf-8"),
        1,
    )
    operations = manifest.get("operations")
    if not isinstance(operations, list) or len(operations) != 1 or manifest.get("operation_count") != 1:
        report("FAIL", "0.2.1 ActivityRecord migration operand is invalid")
        return
    row = operations[0]
    expected_row_keys = {
        "sequence", "transform_id", "source", "target", "replacement_counts",
        "outcome", "post_target",
    }
    if not isinstance(row, dict) or set(row) != expected_row_keys:
        report("FAIL", "0.2.1 ActivityRecord operation field is invalid")
        return
    source_evidence = row.get("source")
    target_evidence = row.get("post_target")
    if not isinstance(source_evidence, dict) or set(source_evidence) != {"path", "blob", "bytes", "sha256"}:
        report("FAIL", "0.2.1 ActivityRecord source evidence field is invalid")
        return
    if not isinstance(target_evidence, dict) or set(target_evidence) != {"path", "bytes", "sha256"}:
        report("FAIL", "0.2.1 ActivityRecord target evidence field is invalid")
        return
    if (
        tree != expected_common[3]
        or blob != "79eeee83bc28be3e3f315e4458b8b9e23b0163eb"
        or len(source) != 951
        or hashlib.sha256(source).hexdigest() != "86cda835dac82d8ad235e01205e25aef5bcaea4e701b62f7db06f6e4842ec9b0"
        or len(expected_post) != 982
        or hashlib.sha256(expected_post).hexdigest() != "75c6b766df611312d84e8fa6f56d1f47237e5fcafaf08e01e045f273c4687ddb"
        or row.get("sequence") != 1
        or row.get("transform_id") != "activity-record-reading-kind-v1"
        or source_evidence != {"path": source_path, "blob": blob, "bytes": len(source), "sha256": hashlib.sha256(source).hexdigest()}
        or row.get("target") != target_path
        or row.get("replacement_counts") != {"activity_kind_insert": 1, "self_path": 1}
        or row.get("outcome") != "applied"
        or target_evidence != {"path": target_path, "bytes": len(expected_post), "sha256": hashlib.sha256(expected_post).hexdigest()}
    ):
        report("FAIL", "0.2.1 ActivityRecord evidence disagrees with the independent oracle")
    summary = activity_report.get("operation_manifest")
    verification = activity_report.get("current_verification")
    if (
        not isinstance(summary, dict)
        or set(summary) != {"path", "operation_count", "sha256"}
        or summary.get("path") != "main/60_journal/migration_021_activity_record_operations.json"
        or summary.get("operation_count") != 1
        or summary.get("sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        or verification != {"source_absent": True, "target_present": True}
    ):
        report("FAIL", "0.2.1 ActivityRecord report is not bound to the manifest/live structure")
    if (ROOT / source_path).exists() or not (ROOT / target_path).is_file():
        report("FAIL", "0.2.1 ActivityRecord canonical/legacy path state is invalid")


def check_reading_bridge_contract(*, check_release_parity: bool = True) -> None:
    contract_relative = Path("main/70_tools/contracts/reading_bridge_v1")
    expected = {
        "__init__.py",
        "validator.py",
        "t2ag.reading_context.v1.schema.json",
        "reading.t2ag_contribution.v1.schema.json",
        "reading.t2ag_receipt.v1.schema.json",
        "reading.t2ag_context_store.v1.schema.json",
        "t2ag.reading_context_source.v1.schema.json",
        "t2ag.reading_contribution_ledger.v1.schema.json",
    }
    local = ROOT / contract_relative
    present = {path.name for path in local.iterdir() if path.is_file()} if local.is_dir() else set()
    if present != expected:
        report("FAIL", f"reading bridge V1 contract file set is invalid: missing={sorted(expected - present)} extra={sorted(present - expected)}")
        return
    for schema_path in sorted(local.glob("*.schema.json")):
        try:
            schema = load_json_strict(schema_path)
            if not isinstance(schema, dict):
                raise ContractError("schema must be an object")
            validate_document({}, schema)
        except ContractError as exc:
            # A valid contract rejects the empty object for missing required
            # fields; unsupported keywords and malformed schema are distinct.
            if "missing fields" not in str(exc):
                report("FAIL", f"reading bridge schema/validator is invalid: {rel(schema_path)} -> {exc}")
        except OSError as exc:
            report("FAIL", f"reading bridge schema cannot be read: {rel(schema_path)} -> {exc}")
    tool = MAIN / "70_tools/t2ag_reading_bridge.py"
    test = MAIN / "70_tools/test_021_closeout.py"
    saga_test = MAIN / "70_tools/scenarios/release_reading_bridge_saga.py"
    migration = MAIN / "70_tools/migrate_021_activity_records.py"
    if not tool.is_file() or not test.is_file() or not saga_test.is_file() or not migration.is_file():
        report("FAIL", "reading bridge tools/tests/saga/ActivityRecord migrator are incomplete")
    elif "subprocess" in read(tool) or "辅助阅读系统" in read(tool):
        report("FAIL", "T2AG reading bridge tools must not spawn or bind the peer reading system")
    if not check_release_parity:
        return
    release_roots = {
        name: ROOT.parent / name
        for name in distribution_release_names()
        if (ROOT.parent / name).is_dir()
    }
    if len(release_roots) != len(distribution_release_names()):
        return
    names = sorted(expected) + [
        "../../t2ag_reading_bridge.py",
        "../../test_021_closeout.py",
        "../../scenarios/release_reading_bridge_saga.py",
        "../../migrate_021_activity_records.py",
        "../../migration_txn_021.py",
    ]
    manifests: dict[str, tuple[str, ...]] = {}
    for release_name, release_root in release_roots.items():
        values: list[str] = []
        missing: list[str] = []
        for name in names:
            path = release_root / contract_relative / name
            if not path.is_file():
                missing.append((contract_relative / name).as_posix())
            else:
                values.append(hashlib.sha256(path.read_bytes()).hexdigest())
        if missing:
            report("FAIL", f"reading bridge release capability is incomplete: {release_name} -> {missing}")
        else:
            manifests[release_name] = tuple(values)
    if len(manifests) == len(distribution_release_names()) and len(set(manifests.values())) != 1:
        report("FAIL", "reading bridge schema/validator/tool/test diverge across the three releases")


def check_core_playbooks() -> None:
    roots = {
        name: ROOT.parent / name
        for name in distribution_release_names()
        if (ROOT.parent / name / "main/50_playbook").is_dir()
    }
    if len(roots) != len(distribution_release_names()):
        return
    manifests: dict[str, dict[str, str]] = {}
    for name, root in roots.items():
        manifest: dict[str, str] = {}
        for path in sorted((root / "main/50_playbook").glob("*.md")):
            legal, _illegal = parse_playbook_protection_levels(read(path))
            if any(value == "core-playbook" for _lineno, value in legal):
                manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifests[name] = manifest
    reference = manifests["t2ag-skeleton"]
    for name, manifest in manifests.items():
        if set(manifest) != set(reference):
            report(
                "FAIL",
                f"core-playbook file set divergence: {name}",
            )
            continue
        drift = [file for file in reference if manifest[file] != reference[file]]
        if drift:
            report("FAIL", f"core-playbook SHA divergence: {name} -> {drift}")


def check_context_packet_contract(*, check_release_parity: bool = True) -> None:
    tool_relative = "main/70_tools/t2ag_context.py"
    activity_relative = "main/70_tools/t2ag_activity.py"
    test_relative = "main/70_tools/test_context_packet.py"
    playbook_relative = "main/50_playbook/context_packet.md"
    startup_relative = "main/50_playbook/startup_orchestration.md"
    tool = ROOT / tool_relative
    activity = ROOT / activity_relative
    test = ROOT / test_relative
    playbook = ROOT / playbook_relative
    startup = ROOT / startup_relative
    missing = [
        path
        for path, carrier in (
            (tool_relative, tool),
            (activity_relative, activity),
            (test_relative, test),
            (playbook_relative, playbook),
            (startup_relative, startup),
        )
        if not carrier.is_file()
    ]
    if missing:
        report("FAIL", f"learning context packet capability is missing: {missing}")
        return

    tool_markers = (
        "ProgressSnapshot",
        "resolve_activity",
        "assert_unchanged",
        "read_bytes",
        "reader=cache.read",
        "reference_inventory_chars",
        "serialized_l0_markdown_chars",
        "serialized_l0_plus_l1_markdown_chars",
        "textbook_lesson_window",
        "explicit_same_active_group",
        "first_run_required",
        "不是新的真相源",
    )
    tool_content = read(tool)
    absent = missing_markers(tool_content, tool_markers)
    if absent:
        report("FAIL", f"the learning context packet tool lacks a read-only/cost contract: {absent}")

    activity_content = read(activity)
    activity_markers = (
        "TextReader",
        "reader: TextReader = read",
        "exists: Callable[[Path], bool] | None = None",
        "teacher_paths: Iterable[Path] | None = None",
        "frontmatter_text(reader(problems))",
        "frontmatter_text(reader(carrier))",
        "frontmatter(historical, reader=reader)",
    )
    absent = [
        marker for marker in activity_markers
        if not has_marker(activity_content, marker)
    ]
    if absent:
        report("FAIL", f"the activity router lacks the shared snapshot injection contract: {absent}")

    test_content = read(test)
    test_markers = (
        "test_cli_stdout_matches_serialized_cost",
        "test_digest_uses_original_file_bytes",
        "test_activity_router_uses_same_cache_and_detects_mutation",
        "test_textbook_lesson_without_preparation_returns_none",
        "test_non_current_same_group_has_explicit_switch_context",
        "test_course_outside_active_group_is_rejected",
        "test_lesson_conditional_reads_never_point_to_exercise_tree",
        "test_exercise_first_step_selects_only_current_problem",
        "test_nonempty_l1_is_included_in_serialized_combined_cost",
        "test_initialized_requires_hint_gate_choice",
        "serialized_l0_plus_l1_markdown_chars",
    )
    absent = missing_markers(test_content, test_markers)
    if absent:
        report("FAIL", f"learning context packet negative tests are missing: {absent}")

    workflow_markers = {
        MAIN / "t2ag.md": (
            # EV-0020 Batch A: takeover detail sank into context_packet.md; the
            # constitution keeps the pointer anchor
            "context_packet.md",
            "完整序列化 Markdown",
            "t2ag_hint_gate.py",
            "learning-ready",
            "recovery-settled",
            "startup_orchestration.md",
        ),
        playbook: (
            "t2ag_context.py --course <ID> --format markdown",
            "即时摘录 + 触发式展开",
            "同一对话内未变化的 L0 不重复读取",
            "--include-l1",
            "Main 消费纪律",
        ),
        startup: (
            "先建依赖树，再分配 Agent",
            "learning-ready",
            "recovery-settled",
            "不得只展示 ID/SHA 让学生盲签",
            "Task Assist Budget",
        ),
        MAIN / "50_playbook/lesson_recover.md": (
            "t2ag_context.py --course <COURSE_ID> --format markdown",
            "步骤 2：消费 progress.md 当前切片",
            "L2 读取对应「教学记录」",
            "不得返回缺教材的 `ready`",
            "--intent <INTENT>",
        ),
        MAIN / "50_playbook/session_close.md": (
            "只回读这些实际目标",
            "原 L0 上下文包立即失效",
        ),
    }
    for path, markers in workflow_markers.items():
        content = read(path) if path.is_file() else ""
        absent_markers = missing_markers(content, markers)
        if absent_markers:
            report(
                "FAIL",
                f"the learning context packet is not wired into {rel(path)}：{absent_markers}",
            )

    if not check_release_parity:
        return
    release_roots = {
        name: ROOT.parent / name
        for name in distribution_release_names()
        if (ROOT.parent / name).is_dir()
    }
    if len(release_roots) != len(distribution_release_names()):
        return
    manifests: dict[str, tuple[str, str, str]] = {}
    for name, release_root in release_roots.items():
        release_tool = release_root / tool_relative
        release_activity = release_root / activity_relative
        release_test = release_root / test_relative
        if (
            not release_tool.is_file()
            or not release_activity.is_file()
            or not release_test.is_file()
        ):
            report("FAIL", f"the release lacks learning context packet/activity tools or tests: {name}")
            continue
        manifests[name] = (
            hashlib.sha256(release_tool.read_bytes()).hexdigest(),
            hashlib.sha256(release_activity.read_bytes()).hexdigest(),
            hashlib.sha256(release_test.read_bytes()).hexdigest(),
        )
    if len(manifests) == len(distribution_release_names()) and len(set(manifests.values())) != 1:
        report("FAIL", "the learning context packet/activity tools or tests diverge across the three releases")


def check_test_management_contract(*, check_release_parity: bool = True) -> None:
    """Validate the persistent inventory without executing or expanding tests."""
    required = BASE_VALIDATION_FILES + (
        "main/70_tools/test_runtime_contracts.py",
        "main/70_tools/test_activity_contracts.py",
        "main/70_tools/test_release_contracts.py",
        "main/70_tools/test_release_receipts.py",
        "main/70_tools/test_release_evidence.py",
        "main/70_tools/test_release_gates.py",
        "main/70_tools/test_release_fault_contracts.py",
        "main/70_tools/test_release_shadow_contracts.py",
        "main/70_tools/test_legacy_migrations.py",
        "main/70_tools/test_022_close_roundtrip.py",
        "main/70_tools/scenarios/__init__.py",
        "main/70_tools/scenarios/release_reading_bridge_saga.py",
        "main/70_tools/scenarios/release_shadow_apply.py",
    )
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    if missing:
        report("FAIL", f"test management capability is missing: {missing}")
        return
    retired = (
        "main/70_tools/test_020_contracts.py",
        "main/70_tools/test_021_saga.py",
        "main/70_tools/test_022_close_runtime.py",
        "main/70_tools/test_022_campaign_receipt.py",
        "main/70_tools/test_022_evidence_runner.py",
        "main/70_tools/test_022_gate_matrix.py",
        "main/70_tools/test_022_exact_plan_kill_matrix.py",
        "main/70_tools/test_022_exact_plan_shadow.py",
        "main/70_tools/test_022_shadow_apply.py",
    )
    survivors = [relative for relative in retired if (ROOT / relative).exists()]
    if survivors:
        report("FAIL", f"a retired test entry point still exists: {survivors}")

    manifest_path = ROOT / "main/70_tools/test_dependencies.json"
    try:
        manifest = load_json_strict(manifest_path)
    except (OSError, ContractError) as exc:
        report("FAIL", f"the test dependency manifest cannot be parsed: {exc}")
        return
    if not isinstance(manifest, dict) or manifest.get("schema") != "t2ag.test_dependencies.v2":
        report("FAIL", "the test dependency manifest schema is invalid")
        return
    if manifest.get("tiers") != ["fast", "deep", "release_only"]:
        report("FAIL", "test tiers must be fixed at fast/deep/release_only")
    tests = manifest.get("tests")
    components = manifest.get("components")
    if not isinstance(tests, dict) or not isinstance(components, dict):
        report("FAIL", "the test dependency manifest lacks tests/components")
        return
    required_components = {
        "distribution_foundation", "doctor", "context", "activity_close", "transaction",
        "release_candidate_contracts", "release_receipts", "release_evidence",
        "release_gates", "release_faults", "release_shadow", "release_suite",
    }
    if not required_components.issubset(components):
        report("FAIL", f"the test dependency manifest lacks a component: {sorted(required_components - set(components))}")
    registered = {
        spec.get("path")
        for spec in tests.values()
        if isinstance(spec, dict) and isinstance(spec.get("path"), str)
    }
    discovered = {
        path.relative_to(ROOT).as_posix()
        for path in (MAIN / "70_tools").glob("test_*.py")
        if path.is_file()
    }
    registered_discovery = {
        relative
        for relative in registered
        if isinstance(relative, str)
        and Path(relative).parent == Path("main/70_tools")
        and Path(relative).name.startswith("test_")
    }
    if discovered != registered_discovery:
        report(
            "FAIL",
            "ordinary test files diverge from the dependency manifest: "
            f"missing={sorted(discovered - registered_discovery)} "
            f"stale={sorted(registered_discovery - discovered)}",
        )
    scenario = tests.get("reading.release_saga")
    if (
        not isinstance(scenario, dict)
        or scenario.get("kind") != "scenario"
        or scenario.get("automatic") is not False
    ):
        report("FAIL", "the full physical-root reading saga is not marked as an explicit release scenario")
    shadow_scenario = tests.get("release.shadow_apply_scenario")
    if (
        not isinstance(shadow_scenario, dict)
        or shadow_scenario.get("kind") != "scenario"
        or shadow_scenario.get("automatic") is not False
    ):
        report("FAIL", "shadow apply is not moved out of the ordinary test discovery scope")
    release_ids = (
        "contracts.release",
        "release.receipts",
        "release.gates",
        "release.evidence",
        "release.fault_contracts",
        "release.shadow_contracts",
        "release.shadow_apply_scenario",
        "reading.release_saga",
    )
    invalid_release = [
        test_id
        for test_id in release_ids
        if not isinstance(tests.get(test_id), dict)
        or tests[test_id].get("tier") != "release_only"
    ]
    if invalid_release:
        report("FAIL", f"release evidence tests are not isolated into release_only: {invalid_release}")
    release_suite = components.get("release_suite")
    if (
        not isinstance(release_suite, dict)
        or release_suite.get("aggregate") is not True
        or release_suite.get("plan_only") is not True
        or release_suite.get("sources") != []
        or set(release_suite.get("tests", [])) != set(release_ids)
    ):
        report("FAIL", "release_suite must be an explicit aggregate component with no changed-path mapping")

    workflow_path = ROOT / "main/70_tools/validation_workflow.json"
    try:
        workflow = validation_control.load_workflow(workflow_path)
    except validation_control.ValidationControlError as exc:
        report("FAIL", f"the standard check-flow control file is invalid: {exc}")
        workflow = None
    if workflow is not None:
        handlers = {
            spec["handler"]
            for spec in workflow["doctor_checks"].values()
        }
        if handlers != SUPPORTED_DOCTOR_HANDLERS:
            report(
                "FAIL",
                "the Doctor control file and the executor atom handlers diverge: "
                f"missing={sorted(SUPPORTED_DOCTOR_HANDLERS - handlers)} "
                f"unknown={sorted(handlers - SUPPORTED_DOCTOR_HANDLERS)}",
            )
        flow_content = read(ROOT / "main/50_playbook/validation_flow.md")
        # LV-5: two of these four markers are prose and are spelled differently in a
        # translated edition; a bare `not in` pins zh-CN and FAILs a correct English
        # flow tree.  `flowchart TD` / `plan SHA` are language-neutral and resolve to
        # themselves through the registry.
        for marker in missing_markers(flow_content, (
            "flowchart TD", "runtime（默认、启动安全）", "不得越级", "plan SHA",
        )):
            report("FAIL", f"the standard check-flow tree lacks a marker: {marker}")

    runner_content = read(ROOT / "main/70_tools/t2ag_test.py")
    runner_markers = (
        "t2ag.test_plan.v1",
        'parser.add_argument("--component"',
        'parser.add_argument("--test"',
        'parser.add_argument("--changed"',
        'parser.add_argument("--plan-only"',
        'parser.add_argument("--execute-plan"',
        'parser.add_argument("--release-reason"',
        "ordinary test inventory differs from manifest",
        "aggregate component",
        "selected aggregate is plan-only",
        "scenario must be outside ordinary test discovery",
        "three-test-command budget",
    )
    absent = missing_markers(runner_content, runner_markers)
    if absent:
        report("FAIL", f"the test selector lacks the in-memory plan / manifest constraint: {absent}")
    close_content = read(ROOT / "main/70_tools/test_022_close_roundtrip.py")
    close_markers = (
        "test_preference_sources_and_first_prompt_are_durable",
        "test_pending_plan_body_has_full_tree_and_exposes_missing",
        "test_five_knowledge_states_scope_confirmation_and_v2_body",
        "test_learner_retrospective_is_complete_dialogue_payload",
        "test_bound_close_intent_uses_shown_tuple_without_copying",
        "test_blockers_suggest_closed_incomplete",
    )
    absent = missing_markers(close_content, close_markers)
    if absent:
        report("FAIL", f"close runtime-only assertions are not folded into the roundtrip: {absent}")
    migrator_content = read(ROOT / "main/70_tools/migrate_022_activity_close.py")
    if '.glob("test_022_*.py")' in migrator_content:
        report("FAIL", "0.2.2 the migrator still widens the test boundary automatically by glob")

    if not check_release_parity:
        return
    release_roots = {
        name: ROOT.parent / name
        for name in distribution_release_names()
        if (ROOT.parent / name).is_dir()
    }
    if len(release_roots) != len(distribution_release_names()):
        return
    manifests: dict[str, tuple[str, ...]] = {}
    for name, release_root in release_roots.items():
        missing_release = [relative for relative in required if not (release_root / relative).is_file()]
        if missing_release:
            report("FAIL", f"the release lacks test management files: {name} -> {missing_release}")
            continue
        manifests[name] = tuple(
            hashlib.sha256((release_root / relative).read_bytes()).hexdigest()
            for relative in required
        )
    if len(manifests) == len(distribution_release_names()) and len(set(manifests.values())) != 1:
        report("FAIL", "test management rules, manifest or entry point diverge across the three releases")


def check_candidate_replay_contract() -> None:
    tool_relative = "main/70_tools/t2ag_candidate_replay.py"
    test_relative = "main/70_tools/test_release_contracts.py"
    tool = ROOT / tool_relative
    test = ROOT / test_relative
    workflow = MAIN / "50_playbook/git_workflow.md"
    if not tool.is_file() or not test.is_file():
        report("FAIL", "the release candidate isolation tool or its negative tests are missing")
        return
    markers = (
        "sanitized_git_environment",
        "validate_repository_layout",
        "assert_byte_manifest_equal",
        "assert_file_ids_disjoint",
        "replay_candidate",
        'key.upper().startswith("GIT_")',
        "GIT_NO_REPLACE_OBJECTS",
        "--git-dir=",
        "sparsecheckout",
        "source_after_all_candidate_checks",
    )
    tool_content = read(tool)
    missing = missing_markers(tool_content, markers)
    if missing:
        report("FAIL", f"the release candidate isolation tool lacks a mandatory contract: {missing}")
    workflow_content = read(workflow) if workflow.is_file() else ""
    workflow_markers = (
        "t2ag_candidate_replay.py --preflight",
        "--authorization-token CANDIDATE_REPLAY_AUTHORIZED",
        "symlink、junction、mount/reparse point",
        "File ID",
        "逐文件相对路径、大小、SHA-256",
        "0.2.0 冻结验收边界",
        "清单外新提出的理论攻击面",
    )
    missing_workflow = [
        marker for marker in workflow_markers if not has_marker(workflow_content, marker)
    ]
    if missing_workflow:
        report("FAIL", f"the release candidate process is not bound to a mechanical isolation tool: {missing_workflow}")

    release_roots = {
        name: ROOT.parent / name
        for name in distribution_release_names()
        if (ROOT.parent / name).is_dir()
    }
    if len(release_roots) != len(distribution_release_names()):
        return
    manifests: dict[str, tuple[str, str]] = {}
    for name, release_root in release_roots.items():
        release_tool = release_root / tool_relative
        release_test = release_root / test_relative
        if not release_tool.is_file() or not release_test.is_file():
            report("FAIL", f"the release lacks the candidate isolation tool/tests: {name}")
            continue
        manifests[name] = (
            hashlib.sha256(release_tool.read_bytes()).hexdigest(),
            hashlib.sha256(release_test.read_bytes()).hexdigest(),
        )
    if len(manifests) == len(distribution_release_names()) and len(set(manifests.values())) != 1:
        report("FAIL", "the release candidate isolation tool or its negative tests diverge across the three releases")


def check_course_activity_templates(*, check_release_parity: bool = True) -> None:
    required = {
        "README.md", "course.md.template", "progress.md.template",
        "activity_map.md.template", "activity_ledger.md.template",
        "question_bank.md.template", "mistake_bank.md.template",
        "book/README.md.template",
        "lessons/lessonNN/lessonNN.md.template",
        "lessons/lessonNN/lesson_thoughts.md.template",
        "exercises/exercise_thoughts.md.template",
        "exercises/exerciseNN/exercise.md.template",
        "exercises/exerciseNN/problems.md.template",
        "book/primary/verified_excerpts/source.md.template",
        "exercises/exerciseNN/attempts/ATdddd/attempt.md.template",
        "exercises/exerciseNN/reviews/RVdddd.md.template",
    }
    template_root = MAIN / "40_course/_templates/course"
    missing = sorted(path for path in required if not (template_root / path).is_file())
    if missing:
        report("FAIL", f"Course/Lesson/Exercise system template is missing: {missing}")
    question_bank_template = template_root / "question_bank.md.template"
    if (
        question_bank_template.is_file()
        and "QUESTION_BANK_TEMPLATE_V2" not in read(question_bank_template)
    ):
        report("FAIL", "the question bank template lacks the V2 version marker; once instantiated it will be judged not upgraded")
    group_required = {
        "README.md", "plan.md.template", "calendar.md.template",
        "review.md.template", "bindings/_README.md.template",
    }
    group_template_root = MAIN / "30_group/_templates/group"
    missing_group = sorted(
        path for path in group_required if not (group_template_root / path).is_file()
    )
    if missing_group:
        report("FAIL", f"Group system template is missing: {missing_group}")
    group_plan_template = group_template_root / "plan.md.template"
    if group_plan_template.is_file():
        plan_meta = frontmatter(group_plan_template)
        if plan_meta.get("status") != "planned":
            report("FAIL", "The Group plan template default status must be planned; active must not be preset")
    core_contract = MAIN / "00_core/learning_activity_model.md"
    if not core_contract.is_file():
        report("FAIL", "missing the course learning-activity Core contract: main/00_core/learning_activity_model.md")
    core_content = read(core_contract) if core_contract.is_file() else ""
    map_first_markers = (
        "### 2.2 多块长篇讲解的地图优先协议",
        "一次只深入一个分支",
        "无法在不泄露的前提下制作有用总览时，宁可省略总览",
    )
    missing_map_first = [
        marker for marker in map_first_markers if not has_marker(core_content, marker)
    ]
    if missing_map_first:
        report(
            "FAIL",
            f"the course learning-activity Core lacks the map-first explanation protocol: {missing_map_first}",
        )
    first_run = MAIN / "50_playbook/first_run.md"
    first_run_content = read(first_run) if first_run.is_file() else ""
    if missing_markers(
        first_run_content, ("先地图、后逐支", "学生希望怎样确认后再继续")
    ):
        report("FAIL", "first run did not collect the long-explanation map and branch-confirmation preferences")
    route_tool = MAIN / "70_tools/t2ag_activity.py"
    if not route_tool.is_file():
        report("FAIL", "missing the unified LearningActivity router: main/70_tools/t2ag_activity.py")
    hint_gate_tool = MAIN / "70_tools/t2ag_hint_gate.py"
    if not hint_gate_tool.is_file():
        report("FAIL", "missing the student-selectable hint gate: main/70_tools/t2ag_hint_gate.py")
    recovery = MAIN / "50_playbook/lesson_recover.md"
    recovery_content = read(recovery) if recovery.is_file() else ""
    recovery_markers = (
        "### 步骤 3：按 current_activity 恢复主载体",
        "#### `lesson` 分支",
        "#### `exercise` 分支",
        "Exercise 首启不得读取或构造 Lesson 路径",
        "教材原文窗口 **仅在 `lesson` + `course_driver: textbook`**",
        "t2ag_activity.py --course <COURSE_ID> --intent recover",
    )
    marker_positions = [
        marker_position(recovery_content, marker) for marker in recovery_markers
    ]
    if (
        any(position < 0 for position in marker_positions)
        or not marker_positions[0] < marker_positions[1] < marker_positions[2]
    ):
        report("FAIL", "the course recovery flow does not branch on current_activity first")
    close = MAIN / "50_playbook/session_close.md"
    close_content = read(close) if close.is_file() else ""
    close_markers = (
        "t2ag_activity.py --course <COURSE_ID> --intent close",
        "Micro close 和完整结课都必须原子完成",
        "Exercise 结课不得顺手",
    )
    if missing_markers(close_content, close_markers):
        report("FAIL", "the session close flow does not share the unified activity route and atomic write-back")
    if not check_release_parity:
        return
    release_roots = {
        name: ROOT.parent / name
        for name in distribution_release_names()
        if (ROOT.parent / name).is_dir()
    }
    # A standalone unpacked Skeleton has no sibling releases, so only validate itself.
    # In the development workspace all three release roots exist and must carry an
    # identical, complete contract/template bundle.
    if len(release_roots) != len(distribution_release_names()):
        return
    reference: dict[str, str] | None = None
    for name, release_root in release_roots.items():
        release_template_root = release_root / "main/40_course/_templates/course"
        release_missing = sorted(
            path for path in required if not (release_template_root / path).is_file()
        )
        release_contract = release_root / "main/00_core/learning_activity_model.md"
        release_route_tool = release_root / "main/70_tools/t2ag_activity.py"
        release_hint_gate_tool = release_root / "main/70_tools/t2ag_hint_gate.py"
        if (
            release_missing
            or not release_contract.is_file()
            or not release_route_tool.is_file()
            or not release_hint_gate_tool.is_file()
        ):
            details = []
            if release_missing:
                details.append(f"templates={release_missing}")
            if not release_contract.is_file():
                details.append("contract=missing")
            if not release_route_tool.is_file():
                details.append("route_tool=missing")
            if not release_hint_gate_tool.is_file():
                details.append("hint_gate_tool=missing")
            report(
                "FAIL",
                f"Course/Lesson/Exercise release capability is incomplete: {name} -> {'; '.join(details)}",
            )
            continue
        files = {
            f"template/{path}": hashlib.sha256(
                (release_template_root / path).read_bytes()
            ).hexdigest()
            for path in required
        }
        files["contract/learning_activity_model.md"] = hashlib.sha256(
            release_contract.read_bytes()
        ).hexdigest()
        files["tool/t2ag_activity.py"] = hashlib.sha256(
            release_route_tool.read_bytes()
        ).hexdigest()
        files["tool/t2ag_hint_gate.py"] = hashlib.sha256(
            release_hint_gate_tool.read_bytes()
        ).hexdigest()
        if reference is None:
            reference = files
        elif files != reference:
            report("FAIL", f"Course/Lesson/Exercise Core template or contract diverges: {name}")


def check_tracked_environment() -> None:
    if not (ROOT / ".git").exists():
        return
    proc = subprocess.run(
        ["git", "ls-files", "--", ".venv", ".env", "*.env"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout.strip():
        report("FAIL", "Git tracks an environment directory or .env: " + proc.stdout.strip().replace("\n", ", "))


def check_decision_records() -> None:
    """Deterministic Evolution Register ↔ ADR linkage (no value judgment)."""
    import decision_record_contract as drc  # local tools path already on sys.path

    for level, message in drc.validate_decision_records_as_report(ROOT, FLAVOR):
        report(level, message)


def check_decision_record_citations() -> None:
    """ADR/EV tokens cited by live normative prose must name real records.

    Closes the blind spot found 2026-08-09: Skeleton shipped constitution,
    playbooks, code and tests citing ADR-0003/EV-0019 while carrying neither
    the ADR nor the register entries -- every existing check passed because
    they only validated relations *among present records*, never citations
    *from consuming prose* (P-0067).
    """
    if FLAVOR == "lite":
        return
    import decision_record_contract as drc  # local tools path already on sys.path

    for message in drc.validate_decision_citations(ROOT, FLAVOR):
        report("FAIL", message)


def check_cloud_pause() -> None:
    state = ROOT / "cloud/cloud_sync_state.md"
    if state.exists() and not re.search(
        r"^-\s*cloud_bridge_status:\s*paused\s*$", read(state), re.MULTILINE
    ):
        report("FAIL", "Cloud bridge is not being kept paused")


# Files exempt from Main<->Skeleton byte parity, with the reason in the value.
# The reason is mandatory: an exclusion list without reasons becomes a permanent
# blind spot, which is the failure this check exists to prevent (P-0065).
DISTRIBUTION_PARITY_EXEMPT = {
    "main/70_tools/legacy_r_registry.json":
        "the Skeleton copy declares entries empty by design; the Main copy is the "
        "primary instance-level compatibility registry",
    "main/70_tools/artifact_registry.json":
        "Main holds real artifact entries; forcing parity would pour instance data "
        "into the Skeleton",
    "main/50_playbook/gate_index.md":
        "main-only (META D4, adjudicated 2026-08-18: contains instance references and "
        "does not enter the Skeleton until de-instantiated); once the D12 "
        "distribution axis lands this moves to the frontmatter mechanism and this "
        "entry is withdrawn with it",
    "main/50_playbook/host_g1_optional.md":
        "main-only (the file declares itself out of the Skeleton/Lite/release surface, "
        "2026-08-19); once the D12 distribution axis lands this moves to the "
        "frontmatter mechanism and this entry is withdrawn with it",
}
DISTRIBUTION_PARITY_ROOTS = ("main/50_playbook", "main/70_tools")
DISTRIBUTION_PARITY_SUFFIXES = (".md", ".py", ".json")


def check_distribution_parity() -> None:
    """Release profile: `50_playbook/` and `70_tools/` must be byte-identical in Skeleton.

    That requirement has been stated in work orders since 0.2.2 but nothing enforced
    it, and twelve files had silently diverged by 2026-08-08 (P-0065).  A declared
    constraint with no checker is the `carrier_mismatch` pattern -- see
    `remediation_governance.md` §7.

    Release rather than runtime, per `t2ag.md` §3.2: distribution FAILs block the
    release candidate, not the day's teaching.  Parity is a distribution property; a
    Skeleton drift should never stop a lesson.

    Exemptions are data, not silence: a file that is exempt but has become identical
    is reported as a stale exemption, so the list cannot quietly grow into a hole.
    """
    if FLAVOR != "main":
        return
    skeleton = ROOT.parent / "t2ag-skeleton"
    if not skeleton.is_dir():
        report("INFO", "distribution parity: t2ag-skeleton is not mounted, skipping the parity comparison")
        return

    drifted: list[str] = []
    missing: list[str] = []
    stale_exempt: list[str] = []
    for root_rel in DISTRIBUTION_PARITY_ROOTS:
        base = ROOT / root_rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in DISTRIBUTION_PARITY_SUFFIXES:
                continue
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            other = skeleton / rel
            if rel in DISTRIBUTION_PARITY_EXEMPT:
                # An exemption covers both drift and main-only absence (2026-08-19:
                # gate_index/host_g1 were the first cases; once the D12 distribution
                # axis lands this semantics moves to the frontmatter mechanism).
                # An exempt file that IS present in the Skeleton and byte-identical
                # is still reported stale.
                if other.is_file() and path.read_bytes() == other.read_bytes():
                    stale_exempt.append(rel)
                continue
            if not other.is_file():
                missing.append(rel)
                continue
            if path.read_bytes() != other.read_bytes():
                drifted.append(rel)

    for rel in drifted:
        report("FAIL", f"Main<->Skeleton parity drift: {rel}")
    for rel in missing:
        report("FAIL", f"Main<->Skeleton parity missing (no such file in Skeleton): {rel}")
    for rel in stale_exempt:
        report(
            "WARN",
            f"the parity exemption is stale (both sides are now identical; remove it from DISTRIBUTION_PARITY_EXEMPT): {rel}",
        )
    if not (drifted or missing):
        report(
            "INFO",
            "distribution parity: "
            f"{len(DISTRIBUTION_PARITY_EXEMPT)} exemption(s); everything else is byte-identical",
        )


CONSTITUTION_PARITY_TARGETS = (
    "main/t2ag.md",
    "main/00_core/domain_model.md",
    "main/00_core/learning_activity_model.md",
    "main/00_core/pattern_retire_loop.md",
)
CONSTITUTION_PARITY_EXEMPT = {
    ("main/t2ag.md", "6. 修改、迁移与发布闸门"):
        "the Skeleton de-instantiates the handoff-inventory pointer (H4)",
}
CONSTITUTION_PARITY_FILE_EXEMPT = {
    "AGENTS.md": "Main and Skeleton address different audiences",
}
CONSTITUTION_SECTION_MARKER = re.compile(
    r"^## +(?P<title>.+?)(?:\s+\[max \d+\])?\s*$"
)


def constitution_section_digests(data: bytes) -> tuple[dict[str, str], list[str]]:
    """Split a constitution-family file into byte-hashed level-two sections."""
    chunks: list[tuple[str, list[bytes]]] = [("<preamble>", [])]
    for line in data.splitlines(keepends=True):
        text_line = line.decode("utf-8", errors="replace").rstrip("\r\n")
        match = CONSTITUTION_SECTION_MARKER.match(text_line)
        if match:
            chunks.append((match.group("title").strip(), [line]))
        else:
            chunks[-1][1].append(line)
    merged: dict[str, bytes] = {}
    duplicates: list[str] = []
    for title, lines in chunks:
        if title == "<preamble>" and not lines:
            continue
        if title in merged:
            duplicates.append(title)
            merged[title] += b"".join(lines)
        else:
            merged[title] = b"".join(lines)
    return (
        {title: hashlib.sha256(blob).hexdigest() for title, blob in merged.items()},
        sorted(set(duplicates)),
    )


def constitution_parity_findings(
    main_root: Path,
    skeleton_root: Path,
    *,
    targets: tuple[str, ...] = CONSTITUTION_PARITY_TARGETS,
    exempt: dict[tuple[str, str], str] | None = None,
    file_exempt: dict[str, str] | None = None,
) -> list[tuple[str, str, str]]:
    """Compare Main and Skeleton by constitution-family section bytes."""
    if exempt is None:
        exempt = CONSTITUTION_PARITY_EXEMPT
    if file_exempt is None:
        file_exempt = CONSTITUTION_PARITY_FILE_EXEMPT
    findings: list[tuple[str, str, str]] = []
    for rel in sorted(file_exempt):
        main_file, skeleton_file = main_root / rel, skeleton_root / rel
        if (
            main_file.is_file() and skeleton_file.is_file()
            and main_file.read_bytes() == skeleton_file.read_bytes()
        ):
            findings.append((
                "CONST-PAR-003", "WARN",
                f"whole-file exemption is stale; both sides now agree: {rel}",
            ))
        else:
            findings.append((
                "CONST-PAR-000", "INFO",
                f"whole-file exemption: {rel} — {file_exempt[rel]}",
            ))
    seen_exempt: set[tuple[str, str]] = set()
    for rel in targets:
        main_file, skeleton_file = main_root / rel, skeleton_root / rel
        if not main_file.is_file() or not skeleton_file.is_file():
            side = "Main" if not main_file.is_file() else "Skeleton"
            findings.append((
                "CONST-PAR-004", "FAIL",
                f"constitution-parity target missing from {side}: {rel}",
            ))
            continue
        main_digests, main_dupes = constitution_section_digests(main_file.read_bytes())
        skeleton_digests, skeleton_dupes = constitution_section_digests(skeleton_file.read_bytes())
        for edition, duplicates in (("Main", main_dupes), ("Skeleton", skeleton_dupes)):
            if duplicates:
                findings.append((
                    "CONST-PAR-005", "FAIL",
                    f"duplicate section titles make parity undecidable: {rel} ({edition}) -> {duplicates}",
                ))
        for title in sorted(set(main_digests) | set(skeleton_digests)):
            key = (rel, title)
            one_sided = (title in main_digests) != (title in skeleton_digests)
            drifted = not one_sided and main_digests[title] != skeleton_digests[title]
            if key in exempt:
                seen_exempt.add(key)
                if not one_sided and not drifted:
                    findings.append((
                        "CONST-PAR-003", "WARN",
                        f"section exemption is stale; both sides now agree: {rel} § {title}",
                    ))
                continue
            if one_sided:
                side = "Skeleton lacks section" if title in main_digests else "Skeleton has extra section"
                findings.append((
                    "CONST-PAR-002", "FAIL",
                    f"Main/Skeleton section-set fork ({side}): {rel} § {title}",
                ))
            elif drifted:
                findings.append((
                    "CONST-PAR-001", "FAIL",
                    f"Main/Skeleton constitution-section drift: {rel} § {title}",
                ))
    for rel, title in sorted(set(exempt) - seen_exempt):
        if rel in targets:
            findings.append((
                "CONST-PAR-003", "WARN",
                f"dangling section exemption; neither side has it: {rel} § {title}",
            ))
    return findings


def check_constitution_parity() -> None:
    """Release: keep Main and the Chinese Skeleton section-identical."""
    if FLAVOR != "main":
        return
    skeleton = ROOT.parent / "t2ag-skeleton"
    if not skeleton.is_dir():
        report("INFO", "constitution parity: t2ag-skeleton is not mounted; skipping")
        return
    findings = constitution_parity_findings(ROOT, skeleton)
    for _code, severity, message in findings:
        report(severity, message)
    if not any(severity == "FAIL" for _code, severity, _message in findings):
        report(
            "INFO",
            "constitution parity: "
            f"{len(CONSTITUTION_PARITY_TARGETS)} sectioned targets, "
            f"{len(CONSTITUTION_PARITY_EXEMPT)} section exemption(s) + "
            f"{len(CONSTITUTION_PARITY_FILE_EXEMPT)} whole-file exemption(s)",
        )


# --- Cross-edition (translated fork) parity: CE, 2026-08-22 ------------------
# check_distribution_parity compares bytes; check_constitution_parity compares
# section *titles*.  A translated edition can satisfy neither, and this repo's own
# foundation test says so out loud before calling skipTest: "cross-edition byte
# parity is not a satisfiable contract".  Meanwhile check_distribution_parity only
# ever runs the Chinese Main against the Chinese Skeleton.  Net effect: this
# English edition shipped with **no** parity gate at all.  It was generated from
# a347bcd, hand-translated, and then nothing watched it.  By 2026-08-22 it had
# silently lost 8 doctor handlers, 6 registered checks and 14 numbered sections
# while reporting `0 FAIL` against its own frozen contract -- the
# carrier_mismatch family of P-0065/P-0074 one layer up: a declared constraint
# ("the English edition is mechanically equivalent") that no checker could
# falsify.
#
# The unit is neither bytes nor prose titles but the two things a translation is
# obliged to preserve:
#   * machine identifiers -- handler names, check ids, profile membership.  These
#     compare directly because identifiers are carried over verbatim by standing
#     ruling; translating one would itself be the defect.
#   * section *numbers* -- `## 一、`, `## 1.`, `### 二·一` and `### 2.1` all
#     normalise to the same key, so a whole subsection cannot vanish quietly.
# Prose is deliberately out of scope: this gate proves the mechanism is present,
# not that the wording is faithful.  Adjudicated CE-1..CE-6, 2026-08-22.
CROSS_EDITION_ENGLISH_NAME = "t2ag-skeleton-en"
# Which sibling each edition compares itself against.  Deliberately a table of
# directory names rather than anything inferred: the peer is read from where the
# repo actually sits, and an edition whose directory is not listed simply has no
# peer and stays silent.  Both sides carry this same table, so one file behaves
# correctly whichever edition it was shipped in.
CROSS_EDITION_PEERS = {
    "t2ag": (CROSS_EDITION_ENGLISH_NAME,),
    "t2ag-skeleton": (CROSS_EDITION_ENGLISH_NAME,),
    CROSS_EDITION_ENGLISH_NAME: ("t2ag", "t2ag-skeleton"),
}
CROSS_EDITION_SECTION_ROOTS = ("main/50_playbook",)
CROSS_EDITION_SECTION_FILES = (
    "main/t2ag.md",
    "main/00_core/domain_model.md",
    "main/00_core/learning_activity_model.md",
    "main/00_core/pattern_retire_loop.md",
)

CROSS_EDITION_CJK_DIGITS = {
    "〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
# `·` and `．` join CJK section numbers (`二·一`); `点` is the spoken decimal
# point (`二点五`).  All three mean the same thing as the ASCII `.` in `2.1`.
CROSS_EDITION_CJK_SEPARATORS = "·．点"
_CE_CJK_CLASS = "[〇零一二三四五六七八九十]"
CROSS_EDITION_HEADING = re.compile(
    r"^#{2,6}[ \t]*(?:§[ \t]*)?"
    r"(?P<number>"
    r"[0-9]+(?:\.[0-9]+)*"
    rf"|{_CE_CJK_CLASS}+(?:[{CROSS_EDITION_CJK_SEPARATORS}]{_CE_CJK_CLASS}+)*"
    r")"
    r"(?:[、．.。]|[ \t])"
)


def cross_edition_cjk_number(token: str) -> int | None:
    """`三` -> 3, `十` -> 10, `十二` -> 12, `二十` -> 20.  Pure; None if unparsable."""
    if "十" not in token:
        value = 0
        for char in token:
            if char not in CROSS_EDITION_CJK_DIGITS:
                return None
            value = value * 10 + CROSS_EDITION_CJK_DIGITS[char]
        return value
    head, _, tail = token.partition("十")
    high = 1 if head == "" else CROSS_EDITION_CJK_DIGITS.get(head)
    low = 0 if tail == "" else CROSS_EDITION_CJK_DIGITS.get(tail)
    if high is None or low is None:
        return None
    return high * 10 + low


def cross_edition_section_number(line: str) -> tuple[int, str] | None:
    """Normalise one heading line to (depth, dotted number), or None. Pure.

    `## 一、核心原则` and `## 1. Core principles` both return (2, "1"); `### 二·一 …`
    and `### 2.1 …` both return (3, "2.1").  A heading whose number is not leading
    (`### 步骤 1：…` / `### Step 1: …`) returns None on *both* sides, so it drops
    out symmetrically rather than manufacturing a one-sided finding.
    """
    match = CROSS_EDITION_HEADING.match(line)
    if not match:
        return None
    depth = len(line) - len(line.lstrip("#"))
    token = match.group("number")
    if token[0].isdigit():
        return depth, token.rstrip(".")
    parts = [
        cross_edition_cjk_number(part)
        for part in re.split(f"[{CROSS_EDITION_CJK_SEPARATORS}]", token)
    ]
    if any(part is None for part in parts):
        return None
    return depth, ".".join(str(part) for part in parts)


def cross_edition_section_numbers(text: str) -> tuple[set[str], list[str]]:
    """({fully-qualified section numbers}, [numbers appearing twice]).  Pure.

    Subsection numbering is written two ways across the corpus -- bare under its
    parent (`## 五、` then `### 1.`) and fully qualified (`## 5.` then `### 5.1`)
    -- and this edition re-rooted several trees to the second form while
    translating.  Both are anchored to the same parent, so a bare child (no dot)
    is qualified with the nearest `##` number, while an already-dotted child is
    left alone.  The test is the dot rather than "does it lead with the parent's
    number", because the fifth child of §5 is written `### 5.` and would
    otherwise be read as a repeat of its own parent.  Without any of this,
    identical structures written in the two styles read as a total fork, and bare
    children repeating under different parents collide into undecidable
    duplicates.

    A number that still appears twice after qualification makes the comparison
    undecidable for that key, so it is surfaced rather than swallowed.
    """
    seen: list[str] = []
    parent: str | None = None
    for line in text.splitlines():
        parsed = cross_edition_section_number(line)
        if parsed is None:
            continue
        depth, number = parsed
        if depth <= 2:
            parent, key = number, number
        elif parent is None or "." in number:
            key = number
        else:
            key = f"{parent}.{number}"
        seen.append(key)
    duplicates = sorted({n for n in seen if seen.count(n) > 1})
    return set(seen), duplicates


def cross_edition_identifiers(root: Path) -> tuple[dict[str, set[str]], list[str]]:
    """Language-invariant machine identifiers of one edition, plus unreadable sources.

    An unreadable source is returned, never swallowed: losing a comparator
    silently is how this whole blind spot started.
    """
    identifiers: dict[str, set[str]] = {
        "doctor_handler": set(), "doctor_check": set(), "profile_check": set(),
    }
    unreadable: list[str] = []
    doctor = root / "main/70_tools/t2ag_doctor.py"
    if doctor.is_file():
        identifiers["doctor_handler"] = set(
            re.findall(r"^def (check_\w+)", doctor.read_text(encoding="utf-8"), re.M)
        )
    else:
        unreadable.append("main/70_tools/t2ag_doctor.py (missing)")
    workflow = root / "main/70_tools/validation_workflow.json"
    if not workflow.is_file():
        unreadable.append("main/70_tools/validation_workflow.json (missing)")
        return identifiers, unreadable
    try:
        data = json.loads(workflow.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        unreadable.append(f"main/70_tools/validation_workflow.json (unparsable: {exc})")
        return identifiers, unreadable
    checks = data.get("doctor_checks")
    if isinstance(checks, dict):
        identifiers["doctor_check"] = set(checks)
    profiles = data.get("profiles")
    if isinstance(profiles, dict):
        for profile_name, profile in profiles.items():
            for check in (profile or {}).get("checks") or []:
                identifiers["profile_check"].add(f"{profile_name}:{check}")
    return identifiers, unreadable


# Known gaps, grouped by the work that created them.  The reason is mandatory and
# carries the *refill condition*, so the table reads as a ledger of outstanding
# backport debt rather than as permission to stay behind: every entry reports
# INFO while the gap stands and flips to a stale WARN the moment both editions
# agree again.  All of it is one fact -- this edition is frozen at a347bcd and
# the Chinese edition kept moving between 2026-08-18 and 2026-08-22.
_CE_EXEMPT_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "The EX exam system (adjudicated 08-21, built 08-22 as 28ed652/2bc517c) landed "
    "on the Chinese side and was never backported; refill condition: the BACKPORT "
    "work order is executed": (
        ("doctor_handler", "check_exam_banks"),
        ("doctor_check", "runtime.exam_banks"),
        ("profile_check", "runtime:runtime.exam_banks"),
        ("section", "main/50_playbook/exam_bank_spec.md#6"),
        ("section", "main/50_playbook/exam_protocol.md#8.1"),
        ("section", "main/50_playbook/exam_protocol.md#8.2"),
        ("section", "main/50_playbook/exam_protocol.md#8.3"),
        ("section", "main/50_playbook/exam_protocol.md#8.4"),
        ("section", "main/50_playbook/exam_protocol.md#13.1"),
        ("section", "main/50_playbook/exam_protocol.md#13.2"),
        ("section", "main/50_playbook/exam_protocol.md#13.3"),
        ("section", "main/50_playbook/exam_protocol.md#13.4"),
        ("section", "main/50_playbook/exam_protocol.md#14"),
    ),
    "Course-group §4: container shapes and the keystone sequence anchor "
    "(adjudicated 08-18, built 08-22 as 28ed652/1bb3433); refill condition: the "
    "BACKPORT work order is executed": (
        ("doctor_handler", "check_container_mode"),
        ("doctor_handler", "check_keystone_ledger"),
        ("section", "main/50_playbook/course_group_rules.md#4.1"),
        ("section", "main/50_playbook/course_group_rules.md#4.2"),
        ("section", "main/50_playbook/course_group_rules.md#4.3"),
    ),
    "The ELI5 on-ramp (built 08-22 as 082de2f, context_packet §7/§8); refill "
    "condition: the BACKPORT work order is executed": (
        ("section", "main/50_playbook/context_packet.md#8"),
    ),
    "The full Exercise close tree (EXERCISE-CLOSE adjudication 2026-08-21 D1-D5, "
    "session_close §0); refill condition: the BACKPORT work order is executed": (
        ("section", "main/50_playbook/session_close.md#0"),
    ),
    "The constitution-parity blind spot EV-0032 and the META observation "
    "instruments (built 08-20/08-21 as eccdbc1/91a90f3); refill condition: the "
    "BACKPORT work order is executed, and this edition additionally needs a "
    "comparable Skeleton counterpart of its own before release.constitution_parity "
    "has anything to compare": (
        ("doctor_handler", "check_constitution_parity"),
        ("doctor_handler", "check_playbook_usage"),
        ("doctor_handler", "check_domain_tier_reconciliation"),
        ("doctor_handler", "check_recommendation_ledger"),
        ("doctor_handler", "check_gate_visibility"),
        ("doctor_check", "release.constitution_parity"),
        ("doctor_check", "runtime.playbook_usage"),
        ("doctor_check", "runtime.domain_tier_reconciliation"),
        ("doctor_check", "runtime.recommendation_ledger"),
        ("doctor_check", "runtime.gate_visibility"),
        ("profile_check", "release:release.constitution_parity"),
        ("profile_check", "runtime:runtime.playbook_usage"),
        ("profile_check", "runtime:runtime.domain_tier_reconciliation"),
        ("profile_check", "runtime:runtime.recommendation_ledger"),
        ("profile_check", "runtime:runtime.gate_visibility"),
    ),
}
CROSS_EDITION_EXEMPT: dict[tuple[str, str], str] = {}
# Whole files excluded from the section comparator, with the reason.  Two are
# Chinese-side-only by the same ruling that exempts them from byte parity; the
# third is the one place where translation legitimately re-rooted the numbering
# tree, and an honest INFO beats fourteen per-section entries pretending to be
# debt.
CROSS_EDITION_FILE_EXEMPT = {
    "main/50_playbook/gate_index.md":
        "Chinese-side only (META D4, adjudicated 2026-08-18); same origin as "
        "DISTRIBUTION_PARITY_EXEMPT",
    "main/50_playbook/host_g1_optional.md":
        "Chinese-side only (the file declares itself out of the release surface, "
        "2026-08-19); same origin as DISTRIBUTION_PARITY_EXEMPT",
    "main/50_playbook/lesson_recover.md":
        "The Chinese edition mixes bare and dotted numbering under §5 (`### 2.` sits "
        "beside its own child `### 2.1`); the translation re-rooted the whole subtree "
        "as fully-qualified 5.x.  Parenthood cannot be recovered from the numbers "
        "themselves, so the two are semantically equal but their number trees are "
        "undecidable",
}


def cross_edition_parity_findings(
    main_root: Path,
    edition_root: Path,
    *,
    exempt: dict[tuple[str, str], str] | None = None,
    file_exempt: dict[str, str] | None = None,
    section_roots: tuple[str, ...] = CROSS_EDITION_SECTION_ROOTS,
    section_files: tuple[str, ...] = CROSS_EDITION_SECTION_FILES,
) -> list[tuple[str, str, str]]:
    """Cross-edition findings: CE-PAR-001 identifier fork / 002 section-number fork
    / 003 stale-or-dangling exemption / 004 unreadable comparison source
    / 005 duplicate section number / 000 registered backport debt (INFO)."""
    if exempt is None:
        exempt = CROSS_EDITION_EXEMPT
    if file_exempt is None:
        file_exempt = CROSS_EDITION_FILE_EXEMPT
    findings: list[tuple[str, str, str]] = []
    seen_exempt: set[tuple[str, str]] = set()

    def judge(kind: str, key: str, label: str, in_main: bool, in_edition: bool) -> None:
        entry = (kind, key)
        if entry in exempt:
            seen_exempt.add(entry)
            if in_main and in_edition:
                findings.append((
                    "CE-PAR-003", "WARN",
                    "cross-edition exemption is stale (both sides now agree; remove it "
                    f"from CROSS_EDITION_EXEMPT): {label}",
                ))
            else:
                findings.append(("CE-PAR-000", "INFO", f"registered backport debt: {label}"))
            return
        if in_main and not in_edition:
            findings.append((
                "CE-PAR-00" + ("1" if kind != "section" else "2"), "FAIL",
                f"missing from the English edition (Chinese side has it, "
                f"{CROSS_EDITION_ENGLISH_NAME} does not): {label}",
            ))
        elif in_edition and not in_main:
            findings.append((
                "CE-PAR-00" + ("1" if kind != "section" else "2"), "FAIL",
                f"extra in the English edition (Chinese side has no such thing, "
                f"{CROSS_EDITION_ENGLISH_NAME} does): {label}",
            ))

    main_ids, main_unreadable = cross_edition_identifiers(main_root)
    edition_ids, edition_unreadable = cross_edition_identifiers(edition_root)
    for edition_label, sources in (
        ("Chinese edition", main_unreadable),
        (CROSS_EDITION_ENGLISH_NAME, edition_unreadable),
    ):
        for source in sources:
            findings.append((
                "CE-PAR-004", "FAIL",
                f"comparison source unreadable ({edition_label}): {source}",
            ))
    kind_labels = {
        "doctor_handler": "doctor handler",
        "doctor_check": "doctor check id",
        "profile_check": "profile check registration",
    }
    for kind, label_prefix in kind_labels.items():
        mine, theirs = main_ids[kind], edition_ids[kind]
        for key in sorted(mine | theirs):
            judge(kind, key, f"{label_prefix} `{key}`", key in mine, key in theirs)

    targets: list[str] = []
    for root_rel in section_roots:
        base = main_root / root_rel
        if base.is_dir():
            targets.extend(
                path.relative_to(main_root).as_posix()
                for path in sorted(base.rglob("*.md"))
                if path.is_file()
            )
    targets.extend(rel for rel in section_files if rel.endswith(".md"))
    for rel in sorted(dict.fromkeys(targets)):
        main_file, edition_file = main_root / rel, edition_root / rel
        if rel in file_exempt:
            if main_file.is_file() and edition_file.is_file():
                main_numbers, _ = cross_edition_section_numbers(
                    main_file.read_text(encoding="utf-8")
                )
                edition_numbers, _ = cross_edition_section_numbers(
                    edition_file.read_text(encoding="utf-8")
                )
                if main_numbers == edition_numbers:
                    findings.append((
                        "CE-PAR-003", "WARN",
                        "file-level cross-edition exemption is stale (the number sets "
                        f"now agree; remove it or bring the file under the gate): {rel}",
                    ))
                    continue
            findings.append((
                "CE-PAR-000", "INFO",
                f"file-level cross-edition exemption: {rel} -- {file_exempt[rel]}",
            ))
            continue
        if not main_file.is_file() or not edition_file.is_file():
            side = (
                "Chinese edition" if not main_file.is_file()
                else CROSS_EDITION_ENGLISH_NAME
            )
            findings.append((
                "CE-PAR-004", "FAIL",
                f"section-comparison target missing ({side} has no such file): {rel}",
            ))
            continue
        main_numbers, main_dupes = cross_edition_section_numbers(
            main_file.read_text(encoding="utf-8")
        )
        edition_numbers, edition_dupes = cross_edition_section_numbers(
            edition_file.read_text(encoding="utf-8")
        )
        for edition_label, dupes in (
            ("Chinese edition", main_dupes),
            (CROSS_EDITION_ENGLISH_NAME, edition_dupes),
        ):
            if dupes:
                findings.append((
                    "CE-PAR-005", "FAIL",
                    f"duplicate section number, comparison undecidable: {rel} "
                    f"({edition_label}) -> {dupes}",
                ))
        for number in sorted(main_numbers | edition_numbers, key=_ce_sort_key):
            judge(
                "section", f"{rel}#{number}", f"{rel} §{number}",
                number in main_numbers, number in edition_numbers,
            )

    for entry in sorted(set(exempt) - seen_exempt):
        findings.append((
            "CE-PAR-003", "WARN",
            f"cross-edition exemption dangles (neither side has it): {entry[0]} `{entry[1]}`",
        ))
    return findings


def _ce_sort_key(number: str) -> tuple[int, ...]:
    """Sort `4.10` after `4.9`, not before it.  Pure."""
    return tuple(int(part) for part in number.split(".") if part.isdigit())


def cross_edition_peer(root: Path) -> Path | None:
    """The mounted sibling edition to compare against, or None.  Pure.

    None is the ordinary case for anyone holding a single edition -- a trial user
    has no peer and never will -- and the caller turns it into silence rather
    than a finding.  That is what keeps this gate invisible during ordinary use.
    """
    for name in CROSS_EDITION_PEERS.get(root.name, ()):
        candidate = root.parent / name
        if candidate.is_dir():
            return candidate
    return None


def cross_edition_orient(root: Path, peer: Path) -> tuple[Path, Path]:
    """(Chinese side, English side), whichever side invoked the check.  Pure.

    The exemption table names gaps as "the English edition lacks X", so the two
    arguments must mean the same thing no matter which repo the run started
    from.  Without this the same table would read backwards on the English side
    and every entry would dangle.
    """
    if root.name == CROSS_EDITION_ENGLISH_NAME:
        return peer, root
    return root, peer


def check_cross_edition_parity() -> None:
    """Release: the translated edition keeps the mechanism, identifier by identifier.

    Release rather than runtime, for the same reason as its neighbour
    (`t2ag.md` §3.2): a distribution property must never stop the day's teaching.

    Runs from either side.  Unlike check_distribution_parity there is no flavour
    gate, because the comparison is symmetric: whoever holds both editions should
    be told, and the orientation is fixed by cross_edition_orient so the
    exemption table reads the same either way.  What replaces the flavour gate is
    peer resolution -- with a single edition mounted there is nothing to compare
    and the check says so once and returns.  That is the ordinary state for
    anyone using a Skeleton, so this gate costs them exactly one INFO line during
    a release run and nothing at all while teaching.
    """
    peer = cross_edition_peer(ROOT)
    if peer is None:
        report("INFO", "cross-edition parity: no peer edition mounted; comparison skipped")
        return
    main_root, edition = cross_edition_orient(ROOT, peer)
    findings = cross_edition_parity_findings(main_root, edition)
    for _code, severity, message in findings:
        report(severity, message)
    if not any(severity == "FAIL" for _code, severity, _message in findings):
        debt = sum(1 for code, _s, _m in findings if code == "CE-PAR-000")
        report(
            "INFO",
            "cross-edition parity: no unregistered fork in identifiers or section "
            f"numbers; {debt} registered backport debt item(s), "
            f"{len(CROSS_EDITION_FILE_EXEMPT)} file-level exemption(s)",
        )


# Personal identifiers that must never ship inside the open-source Skeleton.
# The pattern list lives here; the *scope* is the whole repo, which is the point --
# an identical check already existed inside check_version_and_profile but read only
# `profile.md`, so nine other files leaked past it for months (P-0067).
SKELETON_PRIVACY_PATTERNS = (
    (r"[A-Za-z]:[\\/]Users[\\/]", "Windows user-directory absolute path"),
    (r"/(?:home|Users)/[A-Za-z0-9_.-]+/", "POSIX user-directory absolute path"),
    (r"MikeChen", "maintainer's username"),
    (r"上海交通大学", "maintainer's institution"),
    (r"辅助阅读系统", "maintainer's peer private repository name"),
)
# Files allowed to contain the patterns, with the reason as the value.  A bare
# allowlist would hollow the check out; the reason is what makes it reviewable.
SKELETON_PRIVACY_EXEMPT = {
    "main/70_tools/t2ag_doctor.py":
        "this check itself carries the literals it matches; without the exemption it would necessarily hit itself",
}
# 2026-08-09 independent review: the changelog was once exempt as a whole file,
# while its body still carried three maintainer home paths -- the exemption turned
# "privacy 0 FAIL" into a way around the check. All three were redacted in place
# (event kept, identity removed; see the changelog [2026-08-09] review approval)
# and the exemption was withdrawn. Historical entries are redacted or trimmed by
# version from now on; no more whole-file exemptions.


def package_root_prefix(names: list[str]) -> str:
    """Read the archive's own root directory from its entries. Pure."""
    roots = {name.split("/", 1)[0] for name in names if name.strip()}
    if len(roots) != 1:
        return ""
    root = roots.pop()
    if not any(name.startswith(f"{root}/") for name in names):
        return ""
    return f"{root}/"


PACKAGE_UNREADABLE_PREFIX = (
    "the release package is unreadable, so release-surface cleanliness cannot be judged"
)


def manifest_package_drift(archive: Path) -> str:
    """Cross-check a package against the manifest that claims to describe it. Pure."""
    for candidate in sorted(archive.parent.glob("*.manifest.json")):
        try:
            claim = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return f"release manifest is unreadable: {candidate.name} {error}"
        if not isinstance(claim, dict) or claim.get("package") != archive.name:
            continue
        declared = str(claim.get("zip_sha256", ""))
        if not declared:
            return f"{candidate.name} claims {archive.name} but has no zip_sha256"
        try:
            archive_bytes = archive.read_bytes()
        except OSError as error:
            return (
                f"{PACKAGE_UNREADABLE_PREFIX}, and its manifest cannot be checked: "
                f"{archive.name} {error}"
            )
        actual = hashlib.sha256(archive_bytes).hexdigest()
        if declared != actual:
            return (
                f"release package and manifest disagree: {archive.name} actual sha256 "
                f"{actual[:12]}…, {candidate.name} declares {declared[:12]}…. "
                "One is stale; confirm the intended release bytes and align the other."
            )
        return ""
    return ""


PACKAGE_ROOT_ANCHORS = ("README.md", "main/")


def package_shape_finding(names: list[str]) -> str:
    """"" for the supported single-repository shape, otherwise the reason. Pure."""
    if not [name for name in names if name.strip()]:
        return "the release package is empty; its shape cannot be determined"
    prefix = package_root_prefix(names)
    stripped = [
        name[len(prefix):] if prefix and name.startswith(prefix) else name
        for name in names
    ]
    missing = [
        anchor for anchor in PACKAGE_ROOT_ANCHORS
        if not any(
            entry == anchor if not anchor.endswith("/") else entry.startswith(anchor)
            for entry in stripped
        )
    ]
    if not missing:
        return ""
    interposed = sorted({
        entry.split("/", 1)[0] for entry in stripped if "/" in entry
    })[:4]
    root_note = f"top-level root `{prefix.rstrip('/')}`" if prefix else "no single top-level root (flat package)"
    return (
        f"unsupported release package shape: {root_note} does not directly contain "
        f"repository anchors {missing}; its next level is {interposed}. Repo-relative "
        "policy (including privacy exemptions) is unreliable for this shape, so the "
        "scanner refuses to issue a cleanliness verdict (P-0084)"
    )


def skeleton_package_findings(archive: Path) -> list[str]:
    """Policy findings for one built Skeleton package. Pure; caller reports.

    The tree scan below stops at the checked-out files, but what strangers
    actually receive is the zip. The 2026-08-09 package shipped `.git/`, so every
    pre-redaction blob stayed reachable via `git show` and the tree-level privacy
    cleanup bought nothing: a guard narrower than its carrier, the same
    `carrier_mismatch` family the tree scan was built to fix.
    """
    findings: list[str] = []
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            shape = package_shape_finding(names)
            if shape:
                return [f"{shape}: {archive.name}"]
            prefix = package_root_prefix(names)
            if any(part in name for name in names for part in ("/.git/", "/__pycache__/", "/.cache/")):
                # Subsumes the per-file scan: once history ships, every redacted
                # blob is reachable, so listing each .git file adds noise only.
                return [
                    f"the release package carries .git or a cache directory; pre-cleanup blobs remain retrievable via git show: {archive.name}"
                ]
            for name in names:
                if name.endswith("/") or Path(name).suffix.lower() in {
                    ".png", ".jpg", ".jpeg", ".pdf", ".zip",
                }:
                    continue
                relative = name[len(prefix):] if name.startswith(prefix) else name
                if relative in SKELETON_PRIVACY_EXEMPT:
                    continue
                try:
                    text = bundle.read(name).decode("utf-8", errors="ignore")
                except (OSError, KeyError, zipfile.BadZipFile):
                    continue
                for pattern, label in SKELETON_PRIVACY_PATTERNS:
                    if re.search(pattern, text):
                        findings.append(
                            f"the release package contains maintainer personal information: {archive.name}!{relative} -> {label}"
                        )
                        break
    except (OSError, zipfile.BadZipFile) as error:
        findings.append(f"{PACKAGE_UNREADABLE_PREFIX}: {archive.name} {error}")
    return findings


SKELETON_RELEASE_NAME = "t2ag-skeleton"


PACKAGE_SEARCH_ROOTS = (".", "artifacts/releases")


RELEASE_CANDIDATE_MANIFEST_PATTERN = (
    f"{SKELETON_RELEASE_NAME}*.manifest.json"
)


def collect_release_candidate_manifests(
    workspace: Path, *, search_roots: list[Path] | tuple[Path, ...] | None = None
) -> list[dict[str, object]]:
    """Read each manifest on the invited release surface exactly once.

    Candidate binding has a narrower serving surface than package hygiene. Even
    when callers supply overlapping roots for a regression probe, a manifest is
    admitted only when its resolved path is exactly under
    ``artifacts/releases/t2ag/<version>/invited/``. Resolved-path de-duplication
    happens before JSON parsing, so the same serving identity cannot be counted
    twice (P-0090).
    """
    release_root = (workspace / "artifacts/releases/t2ag").resolve()
    roots = list(search_roots) if search_roots is not None else [release_root]
    candidates: set[Path] = set()
    for search_root in roots:
        try:
            base = search_root.resolve()
        except OSError:
            continue
        if not base.is_dir():
            continue
        for candidate in base.rglob(RELEASE_CANDIDATE_MANIFEST_PATTERN):
            try:
                resolved = candidate.resolve()
                relative = resolved.relative_to(release_root)
            except (OSError, ValueError):
                continue
            if len(relative.parts) != 3 or relative.parts[1] != "invited":
                continue
            candidates.add(resolved)

    manifests: list[dict[str, object]] = []
    for candidate in sorted(candidates):
        try:
            claim = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            report(
                "WARN",
                "Release manifest unreadable, freeze binding cannot be "
                f"verified: {candidate.name} {error}",
            )
            continue
        if isinstance(claim, dict):
            manifests.append(claim)
    return manifests


def built_skeleton_packages(root: Path) -> list[Path]:
    """Every built Skeleton archive in the workspace. Pure.

    Deliberately independent of the current flavor: a Main-side release review is
    exactly when someone should be told the Skeleton package carries history.
    `.bak-*` suffixes fall outside `*.zip` and are left alone — a quarantined
    package is evidence of what was shipped before, not a thing to re-flag.
    Searches the workspace root and the canonical artifact tree, so moving a
    package cannot silently empty the guard's scope (P-0085).
    """
    workspace = root.parent
    pattern = f"{SKELETON_RELEASE_NAME}*.zip"
    # The workspace root is scanned flat and `artifacts/releases` recursively, on
    # purpose: recursing from the root would walk every checked-out repo (minutes,
    # not milliseconds), and a check nobody waits for is a check nobody runs.
    found: set[Path] = set(workspace.glob(pattern))
    releases = workspace / "artifacts/releases"
    if releases.is_dir():
        found.update(releases.rglob(pattern))
    return sorted(found)


RELEASE_CANDIDATE_LINE = re.compile(
    r"^-\s*(\d+\.\d+\.\d+)\s+`release_candidate`\s*[：:]\s*(.+)$"
)
RELEASE_CANDIDATE_PAIR = re.compile(r"\b(zh|en)\s*`([0-9a-f]{7,40}(?:\+wt)?)`")
RELEASE_CANDIDATE_EDITIONS = ("zh", "en")
PACKAGE_VERSION_TOKEN = re.compile(r"-(\d+\.\d+\.\d+)-")


def release_candidate_binding_findings(
    ledger_text: str, manifests: list[dict[str, object]]
) -> list[tuple[str, str, str]]:
    """CAND-BIND-001..003 — the commit frozen at closeout must be the commit served. Pure.

    CR-3=B (2026-08-23, reopening RP-2=c with new evidence: two recurrences
    within twelve hours, the second *after* the package generator was already in
    service).  The generator only guarantees the package matches its source at
    pack time; this check guarantees the ledger's frozen closeout commit matches
    the package still being served.  Both ends of the assertion are frozen at
    closeout, so ordinary commits after closeout never redden anything — that
    standing-red failure mode is exactly why a package==HEAD assertion was
    rejected when RP-2 was first adjudicated.

    Serving identity is machine-read: a manifest without `superseded_by` is the
    serving one; the edition is judged name-first with the manifest field as
    fallback (hand-written edition fields are prose).  No frozen line → silent
    (nothing is bound yet).  Frozen but no manifest → INFO, not WARN: release
    manifests are gitignored, a fresh clone legitimately has none, and a
    standing red in every clean environment is the noise machine this repo has
    already paid for.  The empty set still speaks.

    Completeness contract (review addition, 2026-08-23, CAND-BIND-004..006):
    the assertion must not rest on optimistic parsing.  Any ledger data row
    (a line beginning `-`) that mentions `release_candidate` must parse into a
    binding — a corrupted freeze
    is not a freeze, and silently downgrading it to "not frozen yet" is exactly
    the direction this check exists to eliminate (FAIL).  Once a version is
    frozen, every edition in `RELEASE_CANDIDATE_EDITIONS` must appear exactly
    once: a missing edition leaves that delivery surface unbound (FAIL), and a
    duplicated edition is self-contradictory (FAIL).
    """
    findings: list[tuple[str, str, str]] = []
    counts: dict[str, dict[str, list[str]]] = {}
    for line in ledger_text.splitlines():
        stripped = line.strip()
        # Only ledger data rows can claim a freeze.  Explanatory prose in the
        # ledger header legitimately names the field and must not self-trigger.
        if "release_candidate" not in stripped or not stripped.startswith("-"):
            continue
        match = RELEASE_CANDIDATE_LINE.match(stripped)
        pairs = RELEASE_CANDIDATE_PAIR.findall(match.group(2)) if match else []
        if not match or not pairs:
            findings.append((
                "CAND-BIND-004", "FAIL",
                "A ledger line mentioning release_candidate cannot be parsed as a "
                f"freeze binding: {stripped!r} — a corrupted freeze is not a "
                "freeze and must not silently downgrade to \"not frozen yet\" "
                "(format is frozen by RELEASE_CANDIDATE_LINE/RELEASE_CANDIDATE_PAIR)",
            ))
            continue
        version = match.group(1)
        for edition, commit in pairs:
            counts.setdefault(version, {}).setdefault(edition, []).append(commit)
    if not counts:
        return findings  # no freeze lines (and none corrupted): silence is the design
    frozen: dict[tuple[str, str], str] = {}
    for version, editions in sorted(counts.items()):
        for required in RELEASE_CANDIDATE_EDITIONS:
            got = editions.get(required, [])
            if not got:
                findings.append((
                    "CAND-BIND-005", "FAIL",
                    f"The freeze binding for {version} lacks its {required} end: "
                    "CR-3=B requires both ends frozen — a one-sided freeze leaves "
                    "the other edition's delivery surface unbound",
                ))
            elif len(got) > 1:
                findings.append((
                    "CAND-BIND-006", "FAIL",
                    f"The {required} end of {version} is frozen {len(got)} times "
                    f"({', '.join(got)}): duplicated freezes contradict each other "
                    "and nothing can be asserted",
                ))
            else:
                frozen[(version, required)] = got[0]
    if not frozen:
        return findings
    serving: dict[tuple[str, str], list[str]] = {}
    for claim in manifests:
        if not isinstance(claim, dict) or claim.get("superseded_by"):
            continue
        package = str(claim.get("package", ""))
        version_match = PACKAGE_VERSION_TOKEN.search(package)
        if not version_match:
            continue
        if package.startswith(f"{SKELETON_RELEASE_NAME}-en-"):
            edition = "en"
        elif package.startswith(f"{SKELETON_RELEASE_NAME}-"):
            edition = "zh"
        else:
            edition = str(claim.get("edition", "")) or "zh"
        commit = str(claim.get("source_commit_short", ""))
        serving.setdefault((version_match.group(1), edition), []).append(commit)
    for (version, edition), commit in sorted(frozen.items()):
        active = serving.get((version, edition), [])
        if not active:
            findings.append((
                "CAND-BIND-002", "INFO",
                f"The ledger froze {version} {edition}=`{commit}` but no serving "
                "manifest for that edition is available to verify — manifests are "
                "not tracked, so a clean environment is legitimately empty; if the "
                "release directory should hold a package, this is a gap, not "
                "cleanliness",
            ))
        elif len(active) > 1:
            findings.append((
                "CAND-BIND-003", "WARN",
                f"{version} {edition} has {len(active)} unretired manifests "
                f"({', '.join(sorted(active))}): the serving identity is ambiguous "
                "and the freeze binding cannot be asserted; old packages should "
                "carry superseded_by or move to a retired directory",
            ))
        elif active[0] != commit:
            findings.append((
                "CAND-BIND-001", "WARN",
                f"Serving {edition} package commit `{active[0]}` != the closeout "
                f"commit `{commit}` frozen in the ledger ({version}): the delivery "
                "surface drifted from the closeout point — either the package was "
                "rebuilt without updating the ledger, or the ledger froze and the "
                "package was never rebuilt",
            ))
    return findings


def check_release_candidate_binding() -> None:
    """CAND-BIND-001..003: the serving package must match the frozen closeout commit."""
    ledger = ROOT / VERSION_LEDGER_REL
    if not ledger.is_file():
        return  # a missing ledger is already reported by check_version_bump_precondition
    workspace = ROOT.parent
    manifests = collect_release_candidate_manifests(workspace)
    for code, severity, message in release_candidate_binding_findings(
        read(ledger), manifests
    ):
        report(severity, f"{code} {message}")


def check_release_package_surface() -> None:
    """FAIL on any built package that would disclose history or identity.

    Runtime reports the same facts as WARN so a stale archive never blocks a
    lesson. That severity turned out to be wrong for the moment that matters:
    the risk window is the instant a *new* package is built, and a new package
    lands in the same directory as the old one. The 2026-08-09 repack shipped
    `.git` again and the WARN was read as ordinary noise — the operator even
    reported "the commit objects are there" as a healthy sign. Release review is where this has
    to be unskippable.
    """
    packages = built_skeleton_packages(ROOT)
    if not packages:
        searched = ", ".join(PACKAGE_SEARCH_ROOTS)
        report(
            "INFO",
            "release package surface: no Skeleton package found; searched "
            f"{searched} relative to the workspace root. A package elsewhere means "
            "the search roots are stale, not that the release surface is clean",
        )
        return
    clean = 0
    for archive in packages:
        findings = skeleton_package_findings(archive)
        for finding in findings:
            report("FAIL", f"{finding}(this package must not be distributed)")
        unreadable = any(
            finding.startswith(PACKAGE_UNREADABLE_PREFIX) for finding in findings
        )
        drift = "" if unreadable else manifest_package_drift(archive)
        if drift:
            report("FAIL", drift)
        if not findings and not drift:
            clean += 1
    report(
        "INFO",
        f"release package surface: {clean}/{len(packages)} release packages clean",
    )


def check_skeleton_privacy() -> None:
    """Skeleton must not ship the maintainer's identity or local paths.

    Scope is the whole tracked tree, deliberately.  The pre-existing leak guard
    (`check_version_and_profile`) applied the same patterns to `profile.md` alone,
    so it reported clean while `activity_close.PRODUCTION_ROOT`, two migration
    scripts, a receipt tool and a migration report all carried
    `C:\\Users\\<maintainer>\\...`.  A guard whose scope is narrower than the risk
    is the `carrier_mismatch` family -- see `remediation_governance.md` §7.

    FAIL rather than WARN: the Skeleton is the artifact handed to strangers, and a
    hardcoded maintainer path is not only a disclosure but a functional blocker
    (EA-0001: the production authorization gate never fires outside that path).
    """
    if FLAVOR != "skeleton":
        return
    skip_dirs = {".git", "__pycache__", ".venv", ".cache", ".recovery", ".staging"}
    hits: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".pdf", ".zip"}:
            continue
        if skip_dirs & set(path.parts):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in SKELETON_PRIVACY_EXEMPT:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern, label in SKELETON_PRIVACY_PATTERNS:
            match = re.search(pattern, content)
            if match:
                line = content[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line} -> {label}")
                break
    for hit in hits:
        report("FAIL", f"Skeleton contains maintainer personal information: {hit}")
    if not hits:
        report(
            "INFO",
            "skeleton privacy: "
            f"{len(SKELETON_PRIVACY_EXEMPT)} exemption(s); no maintainer identifier anywhere else in the tree",
        )
    # WARN, not FAIL: a stale archive sitting in the workspace is a release-surface
    # problem, not a state error, and must not block a lesson mid-session (same
    # rule as check_gate_ledger). It still has to be visible — the whole point is
    # that nobody notices the package until it is already in someone else's hands.
    for archive in built_skeleton_packages(ROOT):
        for finding in skeleton_package_findings(archive):
            report("WARN", f"{finding}(this package must not be distributed; release.package_surface judges it FAIL)")


def check_skeleton_textbook_gate() -> None:
    """Release profile: inside the Skeleton, 40_course/**/book/** may hold only template skeletons and must contain no actual textbook content."""
    if FLAVOR != "skeleton":
        return
    book_root = ROOT / "main/40_course"
    if not book_root.exists():
        return
    # Allowed directories: _templates/ and everything under it
    allowed_prefix = str(book_root / "_templates")
    # Disallowed substantive-content patterns
    forbidden_patterns = [
        "book/reference/",
        "book/course_materials/",
        "book/primary/",
        "book/book_notes/",
    ]
    for course_dir in book_root.iterdir():
        if not course_dir.is_dir():
            continue
        if str(course_dir) == allowed_prefix:
            continue
        for pattern in forbidden_patterns:
            check_path = course_dir / pattern
            if check_path.exists() and check_path.is_dir():
                # the directory exists and is non-empty
                contents = list(check_path.iterdir())
                if contents:
                    report("FAIL", f"Skeleton textbook gate: {rel(check_path)} contains substantive textbook content")


def check_dirty_tree() -> None:
    if not (ROOT / ".git").exists():
        return
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True,
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if proc.stdout.strip():
        report("WARN", "the working tree has unsnapshotted changes; work may continue, but do not claim it is releasable")


def check_authorization_governance(*, include_external_handoffs: bool = True) -> None:
    """Fail closed when Agent, runtime, or active workorders can amplify RT3."""
    if activity_close_contract.PRODUCTION_DECISION_AUTHORITIES != frozenset(
        {("user", "direct_user")}
    ):
        report("FAIL", "RT3 authorization contract drift: terminal decision is not user + direct_user")
    if activity_close_contract.PRODUCTION_APPLY_AUTHORIZATION_MODES != frozenset(
        {"direct_user"}
    ):
        report("FAIL", "RT3 authorization contract drift: production close apply still accepts a non-direct_user")
    if migration_022_contract.PRODUCTION_MIGRATION_APPLY_ENABLED is not False:
        report("FAIL", "RT3 authorization contract drift: the released 0.2.2 production migration apply is not retired")

    instruction_paths = [ROOT / "AGENTS.md", MAIN / "t2ag.md"]
    workspace_agents = ROOT.parent / "AGENTS.md"
    if workspace_agents.is_file():
        instruction_paths.append(workspace_agents)
    for path in instruction_paths:
        if not path.is_file():
            report("FAIL", f"the authorization governance entry is missing: {path}")
            continue
        content = read(path)
        if not has_marker(content, "授权不可放大与闭环止损"):
            report("FAIL", f"the authorization governance entry lacks the non-amplification rule: {path}")
        if "stopped_budget" not in content or "token" not in content:
            report("FAIL", f"the authorization governance entry lacks closed-loop budget stop-loss: {path}")

    playbook_markers = {
        MAIN / "50_playbook/batch_workorder_spec.md": (
            "授权不可放大",
            "尚未生成的对象不可预授权",
        ),
        MAIN / "50_playbook/session_close.md": (
            "user + direct_user",
            "receipt 只记录授权证据",
        ),
        MAIN / "50_playbook/remediation_governance.md": (
            "stopped_budget",
            "默认最多两轮 finding 整改",
        ),
        MAIN / "50_playbook/handoff_management.md": (
            "恢复后动作授权门",
            "概括性认可只覆盖当轮已具体列出的动作",
            "不构成当轮许可",
        ),
    }
    for path, markers in playbook_markers.items():
        content = read(path) if path.is_file() else ""
        if missing_markers(content, markers):
            report("FAIL", f"authorization/stop-loss playbook contract is missing: {path}")

    if FLAVOR != "main":
        return
    if include_external_handoffs:
        handoffs = ROOT.parent / "docs/handoffs"
        v4 = handoffs / (
            "T2AG_022_ACTIVITY_CLOSE_AUTONOMOUS_COMPLETION_WORKORDER_V4_2026-08-05.md"
        )
        v2 = handoffs / (
            "T2AG_022_ACTIVITY_CLOSE_EXECUTION_WORKORDER_V2_2026-08-04.md"
        )
        if v4.is_file() and "**status**: `superseded_for_authorization`" not in read(v4):
            report("FAIL", "the current V4 work order can still be read as continuous RT3 authorization")
        if v2.is_file() and "authorization supersession notice" not in read(v2):
            report("FAIL", "The V2 continuation notice still points V4 at the current authorization entry")

    ledger_path = MAIN / "40_course/MATH1607H/activity_ledger.md"
    if ledger_path.is_file():
        doc = activity_ledger_contract.load_ledger(ledger_path)
        for close in doc.closes:
            if not activity_ledger_contract.is_known_invalid_legacy_delegated_close(
                doc.course_id, close
            ):
                continue
            settled = direct_user_reconfirmation_event(doc, close)
            if settled is None:
                report(
                    "WARN",
                    "0.2.2 historical CLR-0001 retains an invalid legacy delegation; it must "
                    "not serve as a template for new authorization, and disposing of "
                    "the real state requires separate RT3",
                )
            else:
                report(
                    "INFO",
                    f"{close.get('close_id')} invalid legacy delegation has been "
                    f"{settled.get('event_id')} re-confirmed by the direct user; the original "
                    "record is retained permanently per §1.7 and still must not serve "
                    "as a template for new authorization",
                )


def direct_user_reconfirmation_event(doc, close) -> dict | None:
    """Return the correction that closes a known-invalid legacy delegated close.

    §6.2 only accepts a re-confirmation made after the exact object, body, ID,
    SHA and result were presented to the user in-turn.  The durable proof of
    that presentation is a user-triggered ``activity_correction`` whose summary
    actually carries those exact values, so the predicate is on the values —
    not on a hand-maintained event id, and not on a correction that merely
    asserts consent without showing what was consented to.

    A matching correction downgrades the finding to INFO.  It never rewrites
    the close: the invalid authorization fields stay in the ledger forever
    (§1.7) and the record must never be reused as an authorization template.
    Remove the correction and the WARN comes back on the next run.
    """
    required = (
        str(close.get("body_sha256") or ""),
        str(close.get("pending_event_id") or ""),
        str(close.get("result") or ""),
    )
    if not all(required):
        return None
    for event in doc.events:
        if event.get("corrects_close_id") != close.get("close_id"):
            continue
        if event.get("triggered_by") != "user":
            continue
        if event.get("trigger") != "activity_correction":
            continue
        summary = str(event.get("correction_summary") or "")
        if all(token in summary for token in required):
            return event
    return None


LINE_ENDING_BINARY_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".exe", ".dll",
    ".traineddata", ".xlsx", ".docx", ".pptx", ".ttf", ".woff", ".woff2",
})

# Bounded on purpose: control files, entry points and the teaching-state core.
# The ordinary budget forbids scanning .venv, Lite, retired staging, textbooks
# and images (section 6.1); the exhaustive sweep belongs to the release profile.
LINE_ENDING_RUNTIME_GLOBS = (
    "t2ag.md",
    "00_core/*.md",
    "50_playbook/*.md",
    "70_tools/*.py",
    "70_tools/*.json",
)
LINE_ENDING_RUNTIME_ROOT_FILES = ("AGENTS.md", "README.md")


def crlf_offenders(paths) -> list[str]:
    """Return repo-relative paths of text files containing CRLF."""
    hits: list[str] = []
    for path in sorted(set(paths)):
        if not path.is_file() or path.suffix.lower() in LINE_ENDING_BINARY_SUFFIXES:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:8000]:
            continue
        if b"\r\n" in data:
            hits.append(rel(path))
    return hits


def check_gitattributes_policy() -> None:
    """Fail when the line-ending pin is missing or too weak.

    Only meaningful where Git manages the working tree. Lite is a derived
    read-only projection with no repository of its own -- its byte integrity is
    proven by sync_lite's direct hash comparison against Main, not by an
    attributes file that nothing would apply. Requiring one there would be a
    check that cannot be satisfied, which is worse than no check.
    """
    if not (ROOT / ".git").is_dir():
        return
    policy = ROOT / ".gitattributes"
    if not policy.is_file():
        report(
            "FAIL",
            "missing .gitattributes: line endings are not pinned, so evidence hashes "
            "drift with the host (see 50_playbook/git_workflow.md §11)",
        )
        return
    text = read(policy)
    if "eol=lf" not in text:
        report(
            "FAIL",
            ".gitattributes does not set eol=lf: text=auto normalizes the blob only, "
            "while the working tree still follows the host -- and the working tree "
            "is exactly what gets hashed",
        )


ENVIRONMENT_ASSUMPTIONS_REL = "main/50_playbook/environment_assumptions.md"
REQUIRED_ENVIRONMENT_ASSUMPTION_IDS = ("EA-0001", "EA-0002", "EA-0003")
CHANGELOG_REL = "main/00_core/t2ag_changelog.md"
CHANGELOG_ENTRY_HEADING = re.compile(
    r"^## \[(\d{4}-\d{2}-\d{2})\]\s*(.+?)\s*$",
    re.MULTILINE,
)
# L3: built from the registry, not from a hand-written alternation. These two were
# the last inline bilingual pairs in this file, and they were also the pair the
# translated `changelog_management.md` got wrong -- the playbook taught
# "Anchoring claims" while the gate only accepted "Anchored assertions", so an entry
# written by the book would have been invisible to the checker. One spelling list,
# one place.
CHANGELOG_ANCHOR_HEADING = re.compile(
    rf"^#{{2,4}}\s*(?:{marker_alternation('锚定断言')})[^\n]*$",
    re.MULTILINE,
)
CHANGELOG_EVIDENCE_HEADING = re.compile(
    rf"^#{{2,4}}\s*(?:{marker_alternation('佐证断言')})[^\n]*$",
    re.MULTILINE,
)
CHANGELOG_EVIDENCE_LINE = re.compile(
    r"^[-*]\s*(.+?)\s*←\s*`([^`]+)`\s*$",
    re.MULTILINE,
)
# Student-approved U2 set: A plan sha, B checks, C atom-set sha (keys only).
# Order matters: "doctor_checks …" must not be captured by the checks key.
CHANGELOG_ANCHOR_SPECS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("plan_sha256", re.compile(r"runtime\s*plan\s*sha256|plan\s*sha256", re.I)),
    (
        "atom_set_sha256",
        re.compile(
            r"doctor_checks\s*atom\s*set|atom\s*set\s*sha|原子项(?:集合)?\s*sha",
            re.I,
        ),
    ),
    # Intentionally narrow — bare "checks" would also match "doctor_checks".
    ("checks", re.compile(r"runtime\s*checks\b|^\s*checks(?:\s*数|\s*count)?\s*$", re.I)),
)


def find_changelog_title(text: str) -> int:
    """Offset of the changelog main title in any shipped language edition.

    LV-5: the title splits the file into an ignored front zone and the body, and
    both the checker and the reader resolve "latest" as the first body entry.
    Hardcoding one spelling meant a translated changelog had no title at all, so
    the whole file became body and a legacy front-matter note could win as the
    newest entry -- the exact resolution failure this convention exists to stop.
    """
    for title in ("# T2AG 变更历史", "# T2AG changelog", "# T2AG Changelog"):
        at = text.find(title)
        if at != -1:
            return at
    return -1


def parse_changelog_entries(text: str) -> list[dict[str, str]]:
    """Split changelog into dated entries.

    Convention: after the changelog main title, entries are newest-first.
    Entries that appear only above that title (legacy front-matter notes) are ignored
    when the title is present, so "latest" means the first body entry.
    """
    body = text
    title_at = find_changelog_title(text)
    if title_at >= 0:
        body = text[title_at:]
    matches = list(CHANGELOG_ENTRY_HEADING.finditer(body))
    entries: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        entries.append(
            {
                "date": match.group(1),
                "title": match.group(2).strip(),
                "heading": match.group(0).strip(),
                "body": body[match.end() : end],
            }
        )
    return entries


def changelog_order_violations(text: str) -> list[str]:
    """Order contract for the changelog (F1, review_LITE-20260812-0001).

    The main title splits the file into an ignored front zone and the body;
    checker and readers both resolve "latest" as the first body entry. Two ways that
    resolution silently breaks: a dated entry parked above the title, and a body
    that is not newest-first. Both were hit for real in the 2026-08-12 online
    review (stale anchor picked up first → one drafted misjudgment), so both are
    named violations here rather than prose conventions.
    """
    violations: list[str] = []
    title_at = find_changelog_title(text)
    if title_at > 0:
        for match in CHANGELOG_ENTRY_HEADING.finditer(text[:title_at]):
            violations.append(
                f"the ignored front zone contains a dated entry: {match.group(0).strip()}"
                "(above the main title nothing is checked, so the newest anchor gets buried; move it to its correct place in the body zone)"
            )
    entries = parse_changelog_entries(text)
    for above, below in zip(entries, entries[1:]):
        if above["date"] < below["date"]:
            violations.append(
                f"body-zone dates are out of order: {above['heading']}（{above['date']}) is located above "
                f"{below['heading']}（{below['date']}), breaking the newest-first convention"
            )
    return violations


def _section_after(heading_re: re.Pattern[str], body: str) -> str | None:
    match = heading_re.search(body)
    if not match:
        return None
    rest = body[match.end() :]
    next_heading = re.search(r"^#{2,4}\s+\S", rest, re.MULTILINE)
    if next_heading:
        rest = rest[: next_heading.start()]
    return rest


def parse_changelog_anchors(text: str) -> dict[str, str]:
    """Parse the latest entry's anchored-assertions block into normalized keys.

    Pure: text in, dict out. Missing block or missing fields yield a partial/empty
    dict so the caller can WARN with both declared and measured values.
    """
    entries = parse_changelog_entries(text)
    if not entries:
        return {}
    section = _section_after(CHANGELOG_ANCHOR_HEADING, entries[0]["body"])
    if section is None:
        return {}
    found: dict[str, str] = {}
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # "- key = value ← cmd" or "- key = value"
        payload = re.sub(r"^[-*]\s*", "", stripped)
        payload = re.split(r"\s*←\s*", payload, maxsplit=1)[0].strip()
        if "=" not in payload and "：" not in payload and ":" not in payload:
            continue
        if "=" in payload:
            label, raw_value = payload.split("=", 1)
        elif "：" in payload:
            label, raw_value = payload.split("：", 1)
        else:
            label, raw_value = payload.split(":", 1)
        label = label.strip()
        value = raw_value.strip().strip("`").strip()
        # Drop trailing ellipsis truncations used in prose; require full tokens later.
        value = value.rstrip("…").rstrip(".")
        for key, pattern in CHANGELOG_ANCHOR_SPECS:
            if pattern.search(label):
                # Prefer first full-looking token on the line.
                token = re.search(r"([a-fA-F0-9]{16,64}|\d+)", value)
                if token:
                    found[key] = token.group(1).lower() if key != "checks" else token.group(1)
                break
    return found


def extract_evidence_claims(entry_body: str) -> list[tuple[str, str]]:
    """Return (claim_text, command) pairs from an explicit corroborating-assertions section only.

    Anchoring lines also use ``←``; scanning the whole entry would false-stale
    them. No corroborating section means no evidence claims (not an error by itself).
    """
    section = _section_after(CHANGELOG_EVIDENCE_HEADING, entry_body)
    if section is None:
        return []
    claims: list[tuple[str, str]] = []
    for match in CHANGELOG_EVIDENCE_LINE.finditer(section):
        claims.append((match.group(1).strip(), match.group(2).strip()))
    return claims


def stale_changelog_claims(
    entries: list[dict[str, str]],
    runner,
) -> list[tuple[str, str, str]]:
    """Recompute evidence claims; runner(command) -> hit_count | None.

    Pure w.r.t. filesystem: all I/O goes through ``runner``. A claim is stale when
    the runner returns an int that is <= 0. None means "skip / not evaluable".
    Returns (entry_title, claim_text, command) for each stale claim.
    """
    stale: list[tuple[str, str, str]] = []
    for entry in entries:
        title = entry.get("heading") or entry.get("title") or "(untitled)"
        for claim_text, command in extract_evidence_claims(entry.get("body", "")):
            # Only claims that sit under an explicit corroborating heading, or any claim
            # when the section exists: extract already scoped when section present.
            hits = runner(command)
            if hits is None:
                continue
            if int(hits) <= 0:
                stale.append((title, claim_text, command))
    return stale


def measure_runtime_changelog_anchors(
    workflow_path: Path | None = None,
) -> dict[str, str]:
    """Repo+python recompute of the student-approved U2 anchor set (A+B+C)."""
    path = workflow_path or validation_control.DEFAULT_WORKFLOW
    workflow = validation_control.load_workflow(path)
    plan = validation_control.build_doctor_plan(
        workflow,
        profile="runtime",
        requested_checks=[],
    )
    keys = sorted(workflow["doctor_checks"])
    atom_blob = "\n".join(keys).encode("utf-8")
    return {
        "plan_sha256": str(plan["plan_sha256"]),
        "checks": str(len(plan["checks"])),
        "atom_set_sha256": hashlib.sha256(atom_blob).hexdigest(),
        "atom_n": str(len(keys)),
    }


def count_grep_matching_lines(pattern: str, text: str) -> int | None:
    """Count lines matching `pattern`, the way grep does. None = pattern unusable.

    Two properties of grep that a naive re.findall over the whole file does not
    reproduce, and both of them silently mislabel healthy claims as rotten:

    1. grep is **line oriented**, so `^` and `$` bind to line boundaries.  Scanning
       the joined text without re.MULTILINE makes every `^`-anchored claim return
       zero — the claim looks rotten while the same command passes in a shell.
    2. grep -c counts **matching lines**, not matches.  re.findall counts matches,
       so a line hit twice inflates the count.  That direction hides rot instead of
       inventing it, which is worse.

    Regression: on 2026-08-07 this gate flagged a freshly written, correct claim
    (`grep -c "^27\\. ..."`) as rotten.  A gate that punishes precise patterns
    trains people to write loose ones — destroying what it exists to protect.
    """
    try:
        regex = re.compile(pattern)
    except re.error:
        return None
    return sum(1 for line in text.splitlines() if regex.search(line))


def default_changelog_evidence_runner(command: str, *, root: Path) -> int | None:
    """Evaluate a narrow class of evidence commands (grep -c / grep -n).

    Accepts a *subset* of grep syntax: the pattern is handed to Python `re`, so
    BRE-only constructs (`\\|`, `\\+`, `\\{n\\}`) are not translated.  Patterns that
    do not compile return None (not evaluable) rather than 0, because "unusable
    command" and "claim no longer true" are different findings and only the second
    one should read as rot.
    """
    cmd = command.strip().strip("`").strip()
    for flag in ("-c", "-n"):
        match = re.match(
            rf"""^grep\s+{flag}\s+(?P<q>['"])(?P<pat>.+?)(?P=q)\s+(?P<path>\S+)\s*$""",
            cmd,
        )
        if not match:
            continue
        path = root / match.group("path")
        if not path.is_file():
            return 0
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return 0
        return count_grep_matching_lines(match.group("pat"), text)
    return None


def check_changelog_contract() -> None:
    """Runtime: drift trail + non-rot for the latest changelog entry (A+B+C).

    Measures anchors via validation_control (no git). Evidence claims use an
    injected-style runner over grep -c/-n only. Does not prove completeness.
    """
    path = ROOT / CHANGELOG_REL
    if not path.is_file():
        report("WARN", f"changelog is missing: {CHANGELOG_REL}(anchored/corroborating assertions cannot be checked)")
        return
    text = read(path)
    entries = parse_changelog_entries(text)
    if not entries:
        report("WARN", f"changelog has no dated entry: {CHANGELOG_REL}")
        return
    for violation in changelog_order_violations(text):
        report("WARN", f"changelog order contract: {violation}")
    latest = entries[0]
    latest_title = latest["heading"]
    declared = parse_changelog_anchors(text)
    measured = measure_runtime_changelog_anchors()
    if not declared:
        report(
            "WARN",
            f"the latest changelog entry lacks an anchor block: {latest_title}；"
            f"measured plan_sha256={measured['plan_sha256']} checks={measured['checks']} "
            f"atom_set_sha256={measured['atom_set_sha256']}",
        )
    else:
        for key, label in (
            ("plan_sha256", "runtime plan sha256"),
            ("checks", "runtime checks"),
            ("atom_set_sha256", "doctor_checks atom set sha256"),
        ):
            want = measured[key]
            got = declared.get(key)
            if got is None:
                report(
                    "WARN",
                    f"state drift with no record: {latest_title} lacks the anchored field {label}; "
                    f"declared=(missing) measured={want}",
                )
            elif got != want:
                report(
                    "WARN",
                    f"state drift with no record: {latest_title} {label} "
                    f"declared={got} measured={want}",
                )
    # Evidence: only the latest entry is required to stay non-rot for this gate;
    # older entries are historical and must not be rewritten (hard rule 4).
    def runner(command: str):
        return default_changelog_evidence_runner(command, root=ROOT)

    for title, claim_text, command in stale_changelog_claims([latest], runner):
        report(
            "WARN",
            f"the claim has rotted: {title}; assertion text={claim_text}; recomputation command=`{command}` had zero hits",
        )


MEMORY_BUDGET_MARKER = re.compile(r"^##\s+(?P<title>.+?)\s+\[max\s+(?P<cap>\d+)\]\s*$")


def memory_section_budgets(text: str) -> list[tuple[str, int, int]]:
    """Return (title, budget, actual_lines) for every `## …  [max N]` section.

    The numbers live in t2ag_memory.md, not here.  If a budget lived in this
    module, adjusting it would cost a batch + three-release sync + tests; that
    price is high enough that people stop writing entries instead of raising the
    budget — which destroys exactly what the budget exists to protect.  This gate
    owns the *mechanism*; the student owns the numbers.

    A section spans its own heading line through the line before the next `## `
    heading (or EOF), so the count matches what `sed -n '/^## X/,/^## /p | wc -l`
    would report.

    Precedent: v0.1.2 had inline `[max N]` in t2ag.md plus
    check_constitution_budget(); both were lost in 4e72556 (0.2.0 snapshot
    migration) and the surviving prose reference became an unenforceable slogan.
    """
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("## ")]
    bounds = starts + [len(lines)]
    out: list[tuple[str, int, int]] = []
    for index, start in enumerate(starts):
        match = MEMORY_BUDGET_MARKER.match(lines[start])
        if not match:
            continue
        out.append((
            match.group("title").strip(),
            int(match.group("cap")),
            bounds[index + 1] - start,
        ))
    return out


def check_memory_budget() -> None:
    """Runtime: memory section line budgets, read from the file's own markers.

    WARN, not FAIL: memory is a summary index, not the constitution.  An oversized
    summary is a hygiene problem that must stay visible; it must not block a lesson
    mid-session.  (v0.1.2 used FAIL for t2ag.md — correct there, wrong here.)
    """
    path = MAIN / "00_core/t2ag_memory.md"
    if not path.is_file():
        return
    budgets = memory_section_budgets(read(path))
    if not budgets:
        report("WARN", "t2ag_memory.md has no [max N] section budget markers at all: the section budget mechanism is inactive")
        return
    for title, cap, actual in budgets:
        if actual > cap:
            report(
                "WARN",
                f"memory section over budget: '{title}' measured {actual} lines > budget "
                f"{cap}; sink the oldest entries per the t2ag_memory.md section-budget "
                f"and sinking rules, leaving a tombstone",
            )



def check_constitution_budget() -> None:
    """Runtime: constitution section line budgets (v0.1.2 mechanism, restored by EV-0020).

    FAIL, not WARN: t2ag.md is the startup entry every session reads, so an
    oversized section taxes every future conversation at boot.  Same division of
    labour as check_memory_budget: this gate owns the mechanism, the student owns
    the `[max N]` numbers inline in t2ag.md.  Precedent: v0.1.2 had this exact
    gate; it died in 4e72556 with no replacement (see EV-0020).
    """
    path = MAIN / "t2ag.md"
    if not path.is_file():
        report("FAIL", "main/t2ag.md is missing")
        return
    budgets = memory_section_budgets(read(path))
    if not budgets:
        report("FAIL", "t2ag.md has no [max N] section budget markers at all: the constitution budget gate is inactive (EV-0020)")
        return
    for title, cap, actual in budgets:
        if actual > cap:
            report(
                "FAIL",
                f"constitution section over budget: '{title}' measured {actual} lines > "
                f"budget {cap}; sink per t2ag.md §6.3 rule_migration, or adjust that "
                f"section's [max N] by student adjudication",
            )


def module_available(name: str) -> bool:
    """Read-only import probe: does not import, does not install (EA-0002)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


GIT_UNLINK_PROBE_NAME = ".t2ag_env_probe"


def probe_git_unlink(root: Path) -> bool | None:
    """Can this mount delete a file it just created under .git/?

    Returns None when there is no .git to probe.  Git's lock protocol assumes
    create-then-delete; a mount that only honours the create half lets `git
    commit` report success while stranding HEAD.lock, which breaks the *host's*
    next ref update.

    The probe name is FIXED, not per-PID.  A per-PID name looks tidier but is
    wrong here: on exactly the environment this probe exists to detect, the
    residue cannot be removed, so every doctor run would strand one more file
    inside .git — the check would become the disease.  With a fixed name the
    residue is capped at one, and an existing residue is itself evidence, so the
    probe retries deleting it before writing anything new.

    Never touches a pre-existing git lock: EA-0003 requires that clearing
    HEAD.lock stay a deliberate human act on a healthy repo, not a doctor habit.
    """
    git_dir = root / ".git"
    if not git_dir.is_dir():
        return None
    probe = git_dir / GIT_UNLINK_PROBE_NAME
    if probe.exists():
        try:
            probe.unlink()
        except OSError:
            return False
    try:
        probe.write_text("t2ag environment probe\n", encoding="utf-8")
    except OSError:
        return False
    try:
        probe.unlink()
    except OSError:
        return False
    return True


def environment_probe_results(
    *,
    root: Path,
    production_root: Path,
    fitz_available: bool,
    git_unlink: bool | None,
) -> list[tuple[str, str]]:
    """Turn three environment facts into doctor findings.

    Pure: every input is injected, so both the holds and the does-not-hold branch
    of each assumption are reachable from a fixture.  Reports facts only — never
    installs, never cleans up, never rewrites a path (environment_assumptions.md §1).
    """
    findings: list[tuple[str, str]] = []
    if root.resolve() != production_root:
        findings.append((
            "INFO",
            f"EA-0001 instance root mismatch: current {root.resolve()}；"
            "activity_close.INSTANCE_ROOT derives from the repo root of the code "
            "(EV-0022), so a mismatch means the code tree and the running root are "
            "misaligned. The direct_user authorization gate is keyed on the instance "
            "root and is in force on every installed instance; never set "
            "T2AG_022_CLOSE_TEST=1 just to make apply pass",
        ))
    if not fitz_available:
        findings.append((
            "INFO",
            "EA-0002 PyMuPDF (fitz) unavailable: the PPI back-calculation path of "
            "t2ag_source_pages.py (source_pages prepare) fails in this environment. "
            "Run it on a host that has .venv; do not auto-install",
        ))
    if git_unlink is False:
        findings.append((
            "WARN",
            "EA-0003 this environment can create files under .git but cannot unlink: "
            "run no git write operation here (commit/add/tag/gc), commit on the host "
            "instead. Lock files such as HEAD.lock already left behind must be "
            "deleted manually by the user; the probing party must not clean up on "
            "their behalf. "
            f"This probe's own residue is fixed at .git/{GIT_UNLINK_PROBE_NAME} "
            f"(at most one, safe to delete)",
        ))
    return findings


def check_environment_assumptions() -> None:
    """Runtime: read-only probes for the host assumptions registered as EA-XXXX.

    These assumptions used to travel by handoff prose only, which is why each of
    them bit a taker at least once.  The check proves the assumption is *visible*,
    not that the environment is correct — a wrong environment stays wrong and
    stays reported (see environment_assumptions.md §1).
    """
    registry = ROOT / ENVIRONMENT_ASSUMPTIONS_REL
    if not registry.is_file():
        report("FAIL", f"the environment assumptions registry is missing: {ENVIRONMENT_ASSUMPTIONS_REL}")
        return
    registry_text = read(registry)
    missing = [
        ea_id for ea_id in REQUIRED_ENVIRONMENT_ASSUMPTION_IDS
        if ea_id not in registry_text
    ]
    if missing:
        report("FAIL", f"the environment assumptions registry lacks an entry: {missing}")
    for level, message in environment_probe_results(
        root=ROOT,
        production_root=activity_close_contract.PRODUCTION_ROOT,
        fitz_available=module_available("fitz"),
        git_unlink=probe_git_unlink(ROOT),
    ):
        report(level, message)


def check_line_endings() -> None:
    """Runtime: bounded CRLF scan over control files and teaching-state core.

    T2AG binds evidence to the SHA-256 of file bytes, so a host that rewrites
    line endings silently invalidates frozen plans and receipt chains while
    changing nothing semantic. .gitattributes removes the source; this check
    proves it actually held, because a policy nobody verifies is not a control.
    """
    check_gitattributes_policy()
    targets = [ROOT / name for name in LINE_ENDING_RUNTIME_ROOT_FILES]
    targets.extend(ROOT / relative for relative in BASE_VALIDATION_FILES)
    for pattern in LINE_ENDING_RUNTIME_GLOBS:
        targets.extend(MAIN.glob(pattern))
    offenders = crlf_offenders(targets)
    for path in offenders[:20]:
        report("FAIL", f"CRLF line endings: {path}(git_workflow.md §11.3: restore, do not commit)")
    if len(offenders) > 20:
        report("FAIL", f"plus {len(offenders) - 20} CRLF files not listed individually")


def check_release_line_endings() -> None:
    """Release: exhaustive CRLF sweep over every tracked text file."""
    if not (ROOT / ".git").exists():
        report("WARN", "not a Git repository; skipping the full line-ending check")
        return
    proc = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, text=True,
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        report("WARN", "cannot enumerate tracked files; skipping the full line-ending check")
        return
    targets = [ROOT / name for name in proc.stdout.split("\0") if name]
    offenders = crlf_offenders(targets)
    for path in offenders[:20]:
        report("FAIL", f"CRLF line endings (tracked): {path}")
    if len(offenders) > 20:
        report("FAIL", f"plus {len(offenders) - 20} tracked CRLF files not listed individually")
    if not offenders:
        report("INFO", f"tracked text files have consistent line endings: {len(targets)} verified")


def check_activity_ledgers(
    courses: dict[str, tuple[Path, dict[str, str]]],
) -> None:
    """Validate 0.2.2 lifecycle authority when migration ledgers exist."""
    ledger_paths = sorted((MAIN / "40_course").glob("*/activity_ledger.md"))
    if not ledger_paths:
        return  # pre-E 0.2.1 baseline
    if len(ledger_paths) != len(courses):
        report(
            "FAIL",
            f"Activity ledger migration is incomplete: {len(ledger_paths)}/{len(courses)}",
        )
    profile_meta = frontmatter(MAIN / "10_student/profile/profile.md")
    required_profile = {
        "activity_close_preference_schema": "activity_close_preferences.v1",
        "learning_timezone": "Asia/Singapore",
        "learning_day_cutoff": "04:00",
    }
    for key, expected in required_profile.items():
        if profile_meta.get(key) != expected:
            report(
                "FAIL",
                f"Activity close global preference contract is missing: {key}="
                f"{profile_meta.get(key)} expected={expected}",
            )
    for key in activity_ledger_contract.PREF_KEYS:
        if profile_meta.get(key) not in {"on", "off"}:
            report("FAIL", f"Activity close global preference is invalid: {key}")
    prompt_status = profile_meta.get("activity_close_first_prompt_status")
    prompt_at = profile_meta.get("activity_close_first_prompt_at")
    if prompt_status not in {"pending", "shown"}:
        report("FAIL", "Activity close first-prompt marker is invalid")
    elif prompt_status == "pending" and prompt_at != "none":
        report("FAIL", "Activity close first-prompt pending must not carry a display time")
    elif prompt_status == "shown" and not activity_ledger_contract.TZ_TIME_RE.match(
        str(prompt_at or "")
    ):
        report("FAIL", "Activity close first-prompt shown lacks a timezone-bearing time")
    by_course = {path.parent.name: path for path in ledger_paths}
    for course_id, (folder, pmeta) in courses.items():
        path = by_course.get(course_id)
        if path is None:
            report("FAIL", f"course lacks activity_ledger.md: {course_id}")
            continue
        try:
            doc = activity_ledger_contract.load_ledger(path)
        except activity_ledger_contract.LedgerError as exc:
            report("FAIL", f"Activity ledger cannot be read: {course_id} -> {exc}")
            continue
        errors = doc.validate()
        for error in errors:
            report("FAIL", f"Activity ledger is invalid: {course_id} -> {error}")
        if errors:
            continue
        # new correction / migration_snapshot gate
        for event in doc.events:
            kind = event.get("event_kind")
            eid = event.get("event_id", "?")
            if kind == "migration_snapshot" and event.get("triggered_by") != "migration":
                if eid == "ALE-000011" and course_id == "MATH1607H":
                    # known historical fingerprint: one named compatibility WARN is
                    # allowed until a legitimate correction closes it
                    has_correction = any(
                        ce.get("event_kind") == "correction"
                        and ce.get("corrects_event_id") == "ALE-000011"
                        for ce in doc.events
                    )
                    if not has_correction:
                        report(
                            "WARN",
                            f"ALE-000011 (migration_snapshot + user trigger) is a known historical "
                            "fingerprint awaiting correction closure; it must not serve "
                            "as a template for new events",
                        )
                else:
                    report(
                        "FAIL",
                        f"migration_snapshot requires triggered_by=migration: {course_id}/{eid}",
                    )
            if kind == "correction":
                corrects = event.get("corrects_event_id")
                if corrects == "ALE-000011" and course_id == "MATH1607H":
                    # once the correction closes, the matching WARN drops out (handled
                    # by the WARN condition above)
                    pass
        index = doc.rebuild_index()
        physical = {
            *(f"lesson:{path.parent.name}" for path in folder.glob("lessons/lesson*/lesson*.md")),
            *(f"exercise:{path.parent.name}" for path in folder.glob("exercises/exercise*/exercise.md")),
        }
        missing_index = sorted(physical - set(index))
        if missing_index:
            report(
                "FAIL",
                f"a physical Activity is not registered in the ledger index: {course_id} -> {missing_index}",
            )
        declared_groups: set[str] = set()
        activity_map = folder / "activity_map.md"
        if activity_map.is_file():
            declared_groups = {
                row.get("content_group_id", "").strip("` ")
                for row in heading_rows(read(activity_map), "内容组连接表")
                if row.get("content_group_id", "").strip("` ")
            }
        for entry in index.values():
            dangling = sorted(set(entry.content_group_ids) - declared_groups)
            if dangling:
                report(
                    "FAIL",
                    f"Activity ledger ContentGroup is dangling: {course_id}/"
                    f"{entry.activity_id} -> {dangling}",
                )
        if pmeta.get("lifecycle_status") != "ongoing":
            continue
        route = COURSE_ROUTES.get(course_id)
        if route is None:
            report("FAIL", f"ongoing course lacks an Activity route: {course_id}")
            continue
        if route.activity_type == "none":
            current_state = None
        else:
            entry = index.get(f"{route.activity_type}:{route.activity_id}")
            if entry is None:
                report(
                    "FAIL",
                    f"the progress foreground is not in the ledger index: {course_id} -> "
                    f"{route.activity_type}:{route.activity_id}",
                )
                continue
            current_state = entry.state
        expected = activity_ledger_contract.resolve_next_action(
            current_activity_type=route.activity_type,
            current_activity_id=route.activity_id,
            current_state=current_state,
            index=index,
        )
        for key, value in expected.items():
            if pmeta.get(key) != value:
                report(
                    "FAIL",
                    f"progress next_action drifts from the ledger: {course_id}/{key} "
                    f"actual={pmeta.get(key)} expected={value}",
                )
        progress_body = cached_progress_content(course_id, folder)
        body_next_matches = list(re.finditer(
            rf"(?m)^-\s+\*\*(?:{next_action_label_alternation()})\*\*[：:]\s*(.+)$",
            progress_body,
        ))
        kind = expected["next_action_kind"]
        if kind in {"resume", "confirm_close", "start_activity"}:
            required_body = (
                f"{kind} {expected['next_activity_type']}:{expected['next_activity_id']}"
            )
        elif kind == "choose_activity":
            required_body = "choose the next item from several available activities"
        else:
            required_body = "there is no automatically selected next activity"
        if (
            len(body_next_matches) != 1
            or required_body not in body_next_matches[0].group(1)
        ):
            report(
                "FAIL",
                f"progress body next action drifts from the structured field: {course_id} "
                f"expected one entry containing {required_body}; "
                f"actual_count={len(body_next_matches)}",
            )
    recovery = ROOT / ".activity_txn"
    lock = recovery / "scope.lock"
    if recovery.exists() and lock.is_file():
        try:
            lock_payload = json.loads(read(lock))
            state = lock_payload.get("status")
        except (OSError, json.JSONDecodeError) as exc:
            report("FAIL", f"Activity transaction lock is corrupted: {exc}")
        else:
            expected_txn = os.environ.get("T2AG_022_EXPECT_TRANSACTION_ID")
            in_bound_postcheck = bool(
                expected_txn
                and lock_payload.get("transaction_id") == expected_txn
                and state in {"installed_pending_postcheck", "postcheck_passed"}
            )
            if state not in {"committed", "rolled_back"} and not in_bound_postcheck:
                report("FAIL", f"Activity transaction did not close: status={state}")


def execute_doctor_checks(
    rows: list[dict[str, object]],
    *,
    include_release_parity: bool,
) -> None:
    """Execute one ordered Doctor plan without widening its declared scope."""
    context: dict[str, object] = {}
    no_argument_handlers = {
        "check_structure": check_structure,
        "check_version_and_profile": check_version_and_profile,
        "check_version_bump_precondition": check_version_bump_precondition,
        "check_skin_system": check_skin_system,
        "check_engagements_and_activities": check_engagements_and_activities,
        "check_registry": check_registry,
        "check_trading_boundary": check_trading_boundary,
        "check_external_references": check_external_references,
        "check_legacy_references": check_legacy_references,
        "check_retired_instance_ids": check_retired_instance_ids,
        "check_cloud_pause": check_cloud_pause,
        "check_problemlog_closure": check_problemlog_closure,
        "check_rule_enforcement_integrity": check_rule_enforcement_integrity,
        "check_decision_records": check_decision_records,
        "check_environment_assumptions": check_environment_assumptions,
        "check_memory_budget": check_memory_budget,
        "check_constitution_budget": check_constitution_budget,
        "check_changelog_contract": check_changelog_contract,
        "check_flow_and_guide": check_flow_and_guide,
        "check_handoff_contract": check_handoff_contract,
        "check_cloud_contract": check_cloud_contract,
        "check_derived_tools": check_derived_tools,
        "check_migration_evidence": check_migration_evidence,
        "check_migration_021_evidence": check_migration_021_evidence,
        "check_activity_migration_021_evidence": check_activity_migration_021_evidence,
        "check_core_playbooks": check_core_playbooks,
        "check_playbook_taxonomy": check_playbook_taxonomy,
        "check_playbook_taxonomy_parity": check_playbook_taxonomy_parity,
        "check_playbook_usage": check_playbook_usage,
        "check_domain_tier_reconciliation": check_domain_tier_reconciliation,
        "check_recommendation_ledger": check_recommendation_ledger,
        "check_gate_visibility": check_gate_visibility,
        "check_candidate_replay_contract": check_candidate_replay_contract,
        "check_tracked_environment": check_tracked_environment,
        "check_dirty_tree": check_dirty_tree,
        "check_skeleton_textbook": check_skeleton_textbook_gate,
        "check_distribution_parity": check_distribution_parity,
        "check_constitution_parity": check_constitution_parity,
        "check_cross_edition_parity": check_cross_edition_parity,
        "check_skeleton_privacy": check_skeleton_privacy,
        "check_release_package_surface": check_release_package_surface,
        "check_release_candidate_binding": check_release_candidate_binding,
        "check_decision_record_citations": check_decision_record_citations,
        "check_line_endings": check_line_endings,
        "check_release_line_endings": check_release_line_endings,
    }
    course_handlers = {
        "check_groups": check_groups,
        "check_activity_ledgers": check_activity_ledgers,
        "check_question_banks": check_question_banks,
        "check_knowledge_ledgers": check_knowledge_ledgers,
        "check_exam_banks": check_exam_banks,
        "check_project_verification": check_project_verification,
        "check_exercises": check_exercises,
        "check_textbook_preparation": check_textbook_preparation,
        "check_canonical_teaching_carrier": check_canonical_teaching_carrier,
        "check_scope_page_cache": check_scope_page_cache,
        "check_checkpoint_block_routing": check_checkpoint_block_routing,
        "check_gate_ledger": check_gate_ledger,
        "check_external_source_backlink": check_external_source_backlink,
    }
    for row in rows:
        handler = str(row["handler"])
        if handler in no_argument_handlers:
            no_argument_handlers[handler]()
        elif handler == "check_authorization_governance":
            check_authorization_governance(
                include_external_handoffs=include_release_parity,
            )
        elif handler == "discover_courses":
            courses = discover_courses()
            context["courses"] = courses
            if FLAVOR == "skeleton" and courses:
                report("FAIL", "Skeleton must not contain a course instance")
            if FLAVOR == "skeleton" and not courses:
                check_skeleton_textbook_gate()
        elif handler in course_handlers:
            course_handlers[handler](context["courses"])
        elif handler == "check_teacher_contract":
            context["teacher_mapping"] = check_teacher_contract(context["courses"])
        elif handler == "check_memory_pointers":
            check_memory_pointers(context["courses"], context["teacher_mapping"])
        elif handler == "check_context_packet_contract":
            check_context_packet_contract(check_release_parity=include_release_parity)
        elif handler == "check_test_management_contract":
            check_test_management_contract(check_release_parity=include_release_parity)
        elif handler == "check_course_activity_templates":
            check_course_activity_templates(check_release_parity=include_release_parity)
        elif handler == "check_reading_bridge_contract":
            check_reading_bridge_contract(check_release_parity=True)
        else:
            raise validation_control.ValidationControlError(
                f"Doctor handler is not registered by the executor: {handler}"
            )


def print_doctor_plan(plan: dict[str, object]) -> None:
    rows = plan["checks"]
    assert isinstance(rows, list)
    print(
        "doctor_plan: "
        f"schema={plan['schema']} profile={plan['profile']} scope={plan['scope']} checks={len(rows)} "
        f"sha256={plan['plan_sha256']}"
    )
    for phase in ("runtime", "release"):
        ids = [str(row["id"]) for row in rows if row["phase"] == phase]
        if ids:
            print(f"  {phase}: {', '.join(ids)}")


def run_runtime_checks(*, include_release_parity: bool = False) -> None:
    """Check the full local teaching runtime from the shared control file."""
    workflow = validation_control.load_workflow()
    plan = validation_control.build_doctor_plan(
        workflow,
        profile="runtime",
        requested_checks=[],
    )
    report("INFO", f"release_flavor: {FLAVOR}")
    execute_doctor_checks(
        plan["checks"],
        include_release_parity=include_release_parity,
    )


def run_release_audit_checks() -> None:
    """Add only the release extension declared by the shared control file."""
    workflow = validation_control.load_workflow()
    release_ids = workflow["profiles"]["release"]["checks"]
    rows = [
        {
            "id": check_id,
            "phase": workflow["doctor_checks"][check_id]["phase"],
            "handler": workflow["doctor_checks"][check_id]["handler"],
            "depends_on": workflow["doctor_checks"][check_id]["depends_on"],
        }
        for check_id in release_ids
    ]
    execute_doctor_checks(rows, include_release_parity=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="T2AG local runtime check or explicit release audit",
    )
    parser.add_argument(
        "--profile",
        choices=("runtime", "release"),
        default="runtime",
        help="runtime is startup-safe; release adds cross-distribution and release gates",
    )
    parser.add_argument("--workflow", type=Path, default=validation_control.DEFAULT_WORKFLOW)
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--list-checks", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--execute-plan")
    parser.add_argument("--release-reason")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        workflow = validation_control.load_workflow(args.workflow.resolve())
        if args.list_checks:
            print(json.dumps({
                "schema": workflow["schema"],
                "profiles": workflow["profiles"],
                "doctor_checks": workflow["doctor_checks"],
                "validation_levels": workflow["validation_levels"],
                "guards": workflow["guards"],
                "ordinary_budget": workflow["ordinary_budget"],
                "release_execution_reasons": workflow["release_execution_reasons"],
            }, ensure_ascii=False, indent=2))
            return 0
        plan = validation_control.build_doctor_plan(
            workflow,
            profile=args.profile,
            requested_checks=args.check,
        )
    except validation_control.ValidationControlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_doctor_plan(plan)
    if args.plan_only and args.execute_plan:
        print("ERROR: --plan-only and --execute-plan cannot be combined", file=sys.stderr)
        return 2
    needs_bound_execution = args.profile == "release" or bool(args.check)
    if args.plan_only or (needs_bound_execution and not args.execute_plan):
        print("PLAN ONLY: review the list, then rerun with --execute-plan <plan_sha256>.")
        return 0
    if args.execute_plan and args.execute_plan != plan["plan_sha256"]:
        print("ERROR: --execute-plan does not match the current Doctor plan", file=sys.stderr)
        return 2
    if args.profile == "release":
        if args.release_reason not in workflow["release_execution_reasons"]:
            print(
                "ERROR: release execution requires --release-reason from validation_workflow.json",
                file=sys.stderr,
            )
            return 2
    elif args.release_reason:
        print("ERROR: --release-reason is valid only for the release profile", file=sys.stderr)
        return 2
    fails.clear()
    warns.clear()
    report("INFO", f"doctor_profile: {args.profile}")
    report("INFO", f"release_flavor: {FLAVOR}")
    try:
        execute_doctor_checks(
            plan["checks"],
            include_release_parity=args.profile == "release",
        )
    except validation_control.ValidationControlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print()
    print(f"result: {len(fails)} FAIL, {len(warns)} WARN")
    if fails:
        if args.profile == "runtime" and plan["claimable_profile_result"]:
            print("Startup runtime check failed; repair local teaching state first and open no new content.")
        elif args.profile == "release" and plan["claimable_profile_result"]:
            print("Release audit failed; do not claim that the candidate or the formal release passed.")
        else:
            print("Targeted doctor check failed; the conclusion is limited to this plan.")
    else:
        if args.profile == "runtime" and plan["claimable_profile_result"]:
            print("Local teaching runtime check passed.")
        elif args.profile == "release" and plan["claimable_profile_result"]:
            print("Release audit mechanical gates passed; this is not equivalent to independent re-review or release approval.")
        else:
            print("Targeted doctor check passed; do not extrapolate it to a full profile conclusion.")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
