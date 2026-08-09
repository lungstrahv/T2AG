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
    "check_structure", "check_version_and_profile", "check_skin_system",
    "check_authorization_governance", "discover_courses", "check_groups",
    "check_activity_ledgers", "check_engagements_and_activities",
    "check_question_banks", "check_knowledge_ledgers", "check_project_verification",
    "check_exercises", "check_teacher_contract", "check_memory_pointers",
    "check_registry", "check_textbook_preparation", "check_scope_page_cache",
    "check_checkpoint_block_routing", "check_gate_ledger",
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
    "check_candidate_replay_contract", "check_tracked_environment", "check_dirty_tree",
    "check_skeleton_textbook", "check_distribution_parity",
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
ALLOWED_COURSE_LIFECYCLES = {"planned", "ongoing", "completed", "dropped"}
ALLOWED_COURSE_TYPES = {"mastery", "project", "praxis"}
ALLOWED_COURSE_DRIVERS = {"textbook", "goal", "project", "praxis"}
ALLOWED_BINDING_STATES = {"idle", "active", "paused", "closed"}
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
ALLOWED_PROJECT_MODES = {"A", "B", "B-K"}
EXPECTED_FLOWS = {
    "first_run", "panorama", "teaching_loop", "authority_chain", "cycles",
    "skin", "git", "batch", "exercise_loop",
}
CORE_PLAYBOOK_MARKER = "**保护级别**：core-playbook"
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
        report("FAIL", f"编号域不等于 0.2.0 九域：actual={sorted(actual)}")
    for name in EXPECTED_DOMAINS:
        if not (MAIN / name).is_dir():
            report("FAIL", f"缺少编号域：main/{name}")
    for name in LEGACY_DOMAINS:
        if (MAIN / name).exists():
            report("FAIL", f"旧 active 域仍存在：main/{name}")
    if not (MAIN / "t2ag.md").is_file():
        report("FAIL", "缺少 main/t2ag.md")
    missing_base = [
        relative for relative in BASE_VALIDATION_FILES
        if not (ROOT / relative).is_file()
    ]
    if missing_base:
        report("FAIL", f"三形态基础验证结构缺失：{missing_base}")
    else:
        doctor_content = read(ROOT / "main/70_tools/t2ag_doctor.py")
        missing_markers = [
            marker for marker in BASE_DOCTOR_PROFILE_MARKERS
            if marker not in doctor_content
        ]
        if missing_markers:
            report("FAIL", f"Doctor runtime/release 基础分层缺失：{missing_markers}")
    if not (MAIN / "80_interface/fable_snail.png").is_file():
        report("FAIL", "缺少界面资产 main/80_interface/fable_snail.png")
    if (ROOT / "assets/fable_snail.png").exists():
        report("FAIL", "旧根 assets/fable_snail.png 仍 active")
    student = MAIN / "10_student"
    expected_student_dirs = {"profile", "activities", "engagements"}
    actual_student_dirs = {
        path.name for path in student.iterdir() if path.is_dir()
    } if student.is_dir() else set()
    if actual_student_dirs != expected_student_dirs:
        report(
            "FAIL",
            "10_student 顶层目录不等于 profile/activities/engagements："
            f"actual={sorted(actual_student_dirs)}",
        )
    profile_root = student / "profile"
    if not profile_root.is_dir():
        report("FAIL", "缺少学生共享档案容器：main/10_student/profile/")
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
                "学生共享档案必须且只能存在一份："
                f"{filename} -> {[rel(path) for path in matches]}",
            )
        if (student / filename).exists():
            report("FAIL", f"旧学生档案顶层文件仍存在：main/10_student/{filename}")


def extract_runtime_version(constitution_text: str) -> str | None:
    """Parse the declared runtime version from t2ag.md prose/heading."""
    patterns = (
        r"当前运行版本[：:]\s*`?(0\.\d+\.\d+)`?",
        r"-\s*当前版本[：:]\s*`?(0\.\d+\.\d+)`?",
        r"^#\s+T2AG\s+(0\.\d+\.\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, constitution_text, re.MULTILINE)
        if match:
            return match.group(1)
    return None


def check_memory_version_prose(memory_text: str, runtime_version: str) -> None:
    """Fail when hand-written current-version markers disagree with t2ag.md.

    Historical mentions of older releases (e.g. 0.2.1 收口) are allowed; only
    title-line and '当前版本为 …' markers are treated as live identity.
    """
    title = re.search(r"^#\s+T2AG\s+(0\.\d+\.\d+)\b", memory_text, re.MULTILINE)
    if title and title.group(1) != runtime_version:
        report(
            "FAIL",
            f"t2ag_memory.md 标题版本 {title.group(1)} 与运行版本 "
            f"{runtime_version} 不一致",
        )
    # blockquote / bullet "版本：0.x.y" near file head (Main style)
    head = "\n".join(memory_text.splitlines()[:12])
    for match in re.finditer(r"版本[：:]\s*`?(0\.\d+\.\d+)`?", head):
        if match.group(1) != runtime_version:
            report(
                "FAIL",
                f"t2ag_memory.md 文首版本 {match.group(1)} 与运行版本 "
                f"{runtime_version} 不一致",
            )
    for match in re.finditer(r"当前版本为\s*(0\.\d+\.\d+)", memory_text):
        if match.group(1) != runtime_version:
            report(
                "FAIL",
                f"t2ag_memory.md 手写「当前版本为 {match.group(1)}」与运行版本 "
                f"{runtime_version} 不一致",
            )


def check_memory_version_pointer(memory_text: str, runtime_version: str) -> None:
    """Fail when the GENERATED state-pointer row disagrees with t2ag.md.

    EV-0015 memory 版本守卫.  The row is produced by t2ag_state_refresh; if that
    generator ever hardcodes a literal again, ``state_refresh --check`` cannot
    see the drift because it compares its own constant with itself.  Doctor is
    the independent observer, so the guard belongs here.
    """
    matches = list(
        re.finditer(r"^\|\s*T2AG 版本\s*\|\s*(\S+)\s*\|", memory_text, re.MULTILINE)
    )
    if not matches and "T2AG_GENERATED:STATE_POINTERS" in memory_text:
        # Guarding only the value would be a false negative: a generator that
        # stopped emitting the row entirely would slip through silently, and
        # state_refresh --check cannot see it either (it would omit the row on
        # both sides).  Require the row whenever the block itself exists.
        report("FAIL", "t2ag_memory.md STATE_POINTERS 块缺 T2AG 版本行")
    for match in matches:
        if match.group(1) != runtime_version:
            report(
                "FAIL",
                f"t2ag_memory.md GENERATED 状态指针版本 {match.group(1)} 与运行版本 "
                f"{runtime_version} 不一致（先修 t2ag_state_refresh 的版本来源，"
                f"再跑 --write）",
            )


def check_version_and_profile() -> None:
    constitution = MAIN / "t2ag.md"
    memory = MAIN / "00_core/t2ag_memory.md"
    if not constitution.exists():
        report("FAIL", "缺少 main/t2ag.md")
        return
    constitution_text = read(constitution)
    runtime_version = extract_runtime_version(constitution_text)
    if not runtime_version:
        report("FAIL", "main/t2ag.md 无法解析当前运行版本")
        return
    for path in (constitution, memory):
        if path.exists() and runtime_version not in read(path):
            report(
                "FAIL",
                f"版本未更新为 {runtime_version}：{rel(path)}",
            )
    for path in (ROOT / "README.md", ROOT / "AGENTS.md", MAIN / "bin/t2ag"):
        if not path.exists() or runtime_version not in read(path):
            report(
                "FAIL",
                f"发行入口版本未更新为 {runtime_version}：{rel(path)}",
            )
    if memory.exists():
        memory_text = read(memory)
        check_memory_version_prose(memory_text, runtime_version)
        check_memory_version_pointer(memory_text, runtime_version)
    launcher = MAIN / "bin/t2ag"
    if launcher.exists():
        content = read(launcher)
        if "main/skin" in content:
            report("FAIL", "launcher 仍指向退役 main/skin")
        if re.search(r"/[a-zA-Z]/Users/|[A-Za-z]:[\\/]Users[\\/]", content):
            report("FAIL", "launcher 含机器专属用户绝对路径")
    profile = MAIN / "10_student/profile/profile.md"
    if not profile.exists():
        report("FAIL", "缺少 10_student/profile/profile.md")
        return
    meta = frontmatter(profile)
    collaboration_values = {
        "agent_collaboration_schema": meta.get("agent_collaboration_schema"),
        "agent_parallel_startup": meta.get("agent_parallel_startup"),
        "agent_startup_readiness": meta.get("agent_startup_readiness"),
        "agent_background_reporting": meta.get("agent_background_reporting"),
    }
    if collaboration_values["agent_collaboration_schema"] != "agent_collaboration_preferences.v1":
        report("FAIL", "profile 缺 agent_collaboration_preferences.v1")
    try:
        agent_pool_limit = int(meta.get("agent_pool_limit", ""))
    except (TypeError, ValueError):
        agent_pool_limit = 0
    if agent_pool_limit not in {1, 2, 3, 4, 5, 6}:
        report("FAIL", "profile agent_pool_limit 必须为 1..6")
    try:
        agent_max_active = int(meta.get("agent_max_active", ""))
    except (TypeError, ValueError):
        agent_max_active = 0
    if agent_max_active not in {1, 2, 3}:
        report("FAIL", "profile agent_max_active 必须为 1..3")
    if agent_max_active > agent_pool_limit:
        report("FAIL", "profile agent_max_active 不得超过 agent_pool_limit")
    if collaboration_values["agent_parallel_startup"] not in {"enabled", "disabled"}:
        report("FAIL", "profile agent_parallel_startup 必须为 enabled|disabled")
    if collaboration_values["agent_startup_readiness"] not in {
        "learning_ready_first", "recovery_settled_first"
    }:
        report("FAIL", "profile agent_startup_readiness 非法")
    if collaboration_values["agent_background_reporting"] not in {"blockers_only", "all"}:
        report("FAIL", "profile agent_background_reporting 必须为 blockers_only|all")
    if FLAVOR == "skeleton":
        if (
            agent_pool_limit != 6
            or agent_max_active != 3
            or collaboration_values["agent_parallel_startup"] != "enabled"
            or collaboration_values["agent_startup_readiness"] != "learning_ready_first"
            or collaboration_values["agent_background_reporting"] != "blockers_only"
        ):
            report("FAIL", "Skeleton Agent 协作偏好必须保留 6 Agent 池 / 3 Agent 并发默认值")
        if meta.get("initialization_status") == "initialized":
            report("FAIL", "Skeleton profile 不得标为 initialized")
        if meta.get("exercise_hint_gate") != "ask":
            report("FAIL", "Skeleton profile 提示闸门必须等待学生选择：ask")
        content = read(profile)
        if re.search(r"\bS00[2-9]\b|MikeChen|上海交通大学", content):
            report("FAIL", "Skeleton profile 含真实实例标识")
    else:
        content = read(profile)
        if meta.get("initialization_status") != "initialized":
            report("FAIL", f"{FLAVOR} profile 未初始化")
            return
        if meta.get("exercise_hint_gate") not in ALLOWED_HINT_GATE_MODES:
            report(
                "FAIL",
                f"{FLAVOR} profile 缺学生确认的 exercise_hint_gate: enabled|disabled",
            )
        if re.search(
            r"<(?:required|confirm|confirm-or-none|off\s*\|\s*suggest\s*\|\s*auto)>|[（(]待填写[）)]",
            content,
            re.IGNORECASE,
        ):
            report("FAIL", "initialized profile 仍含首次启动必填占位符")
        required_sections = {
            "每周可投入学习时间": ("每周可投入学习时间",),
            "学习目标": ("学习目标",),
            "辅导与展现偏好": ("期望的辅导方式", "辅导与展现偏好"),
            "已有基础": ("编程基础", "个体基线"),
        }
        missing = [
            label for label, titles in required_sections.items()
            if not profile_section_has_answer(content, titles)
        ]
        if missing:
            report("FAIL", f"initialized profile 必填信息未确认：{missing}")


def check_skin_system() -> None:
    interface = MAIN / "80_interface"
    global_config = interface / "skin.yaml"
    if not global_config.is_file():
        report("FAIL", "缺少皮肤全局配置：main/80_interface/skin.yaml")
        return
    config = flat_yaml(global_config)
    active = config.get("active", "")
    if not active:
        report("FAIL", "皮肤全局配置缺 active")
        return
    registry = {
        key.split(".", 1)[1]: value
        for key, value in config.items()
        if key.startswith("registry.") and "." in key
    }
    if active not in registry:
        report("FAIL", f"active 皮肤未登记：{active}")
        return
    folder_name = registry[active]
    if not re.fullmatch(r"SK\d{3}_[A-Za-z0-9_]+", folder_name):
        report("FAIL", f"皮肤 registry 目录名非法：{active} -> {folder_name}")
    folder = interface / folder_name
    metadata_path = folder / "skin.yaml"
    if not folder.is_dir() or not metadata_path.is_file():
        report("FAIL", f"active 皮肤载体不存在：{active} -> {folder_name}")
        return
    metadata = flat_yaml(metadata_path)
    missing = [
        key for key in ("id", "name", "version", "welcome_msg", "art_file", "style")
        if not metadata.get(key)
    ]
    if missing:
        report("FAIL", f"active 皮肤 metadata 缺字段：{missing}")
    if metadata.get("id") != active or not folder_name.startswith(active + "_"):
        report("FAIL", f"active 皮肤 ID/目录不匹配：{active} -> {folder_name}")
    art_file = metadata.get("art_file", "")
    if not art_file or Path(art_file).name != art_file:
        report("FAIL", f"皮肤 art_file 必须是目录内文件名：{art_file}")
    elif not (folder / art_file).is_file():
        report("FAIL", f"皮肤 art_file 悬空：{folder_name}/{art_file}")
    welcome = metadata.get("welcome_msg", "")
    if re.search(r"必须|规则|禁止|不得|\bmust\b|\bshall\b", welcome, re.IGNORECASE):
        report("WARN", f"皮肤 welcome_msg 可能携带教学指令：{active}")
    registered_folders = set(registry.values())
    for candidate in sorted(interface.glob("SK*")):
        if candidate.is_dir() and candidate.name not in registered_folders:
            report("WARN", f"皮肤目录未登记：{rel(candidate)}")
    default_welcome = interface / "SK001_default/01_welcome.txt"
    if not default_welcome.is_file() or "t2AG" not in read(default_welcome):
        report("FAIL", "默认欢迎字符画未明确显示 t2AG")
    if active == "SK001" and folder_name == "SK001_default":
        expected_art = "01_welcome.txt" if FLAVOR == "skeleton" else "03_inori_2.txt"
        if art_file != expected_art:
            report(
                "FAIL",
                f"SK001 默认分叉错误：{FLAVOR} expected={expected_art} actual={art_file}",
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
            report("FAIL", f"课程缺 course.md：{folder.name}")
            continue
        if not progress.exists():
            report("FAIL", f"课程缺 progress.md：{folder.name}")
            continue
        cmeta = frontmatter(course)
        progress_content = read(progress)
        pmeta = frontmatter_text(progress_content)
        progress_snapshot = ProgressSnapshot(progress, progress_content, pmeta)
        COURSE_SNAPSHOTS[folder.name] = progress_snapshot
        if cmeta.get("type") != "course" or cmeta.get("course_id") != folder.name:
            report("FAIL", f"course frontmatter 不匹配：{rel(course)}")
        required_course_fields = {
            "school_course_code", "name", "course_type", "default_driver",
            "prerequisites", "status",
        }
        missing_course_fields = sorted(required_course_fields - set(cmeta))
        if missing_course_fields:
            report("FAIL", f"course schema 缺字段：{folder.name} -> {missing_course_fields}")
        if cmeta.get("course_type") not in ALLOWED_COURSE_TYPES:
            report("FAIL", f"course_type 非法：{folder.name} -> {cmeta.get('course_type', '缺失')}")
        if cmeta.get("default_driver") not in ALLOWED_COURSE_DRIVERS:
            report("FAIL", f"default_driver 非法：{folder.name} -> {cmeta.get('default_driver', '缺失')}")
        if cmeta.get("status") != "active":
            report("FAIL", f"Course 定义载体 status 必须为 active：{folder.name}")
        try:
            validate_progress_identity(pmeta, folder.name)
        except ActivityContractError as exc:
            for error in exc.errors:
                report("FAIL", f"progress 身份契约：{rel(progress)} -> {error}")
        if post_022:
            if pmeta.get("truth_scope") != "course_lifecycle,course_frontend,activity_position":
                report("FAIL", f"0.2.2 progress truth_scope 非法：{folder.name}")
            if "truth_source" in pmeta:
                report("FAIL", f"0.2.2 progress 不得保留 truth_source：{folder.name}")
            if "current_lesson" in pmeta:
                report("FAIL", f"0.2.2 progress 不得保留 current_lesson：{folder.name}")
        lifecycle = pmeta.get("lifecycle_status", "")
        if lifecycle not in ALLOWED_COURSE_LIFECYCLES:
            report("FAIL", f"课程生命周期非法：{folder.name} -> {lifecycle}")
        if pmeta.get("course_driver") not in ALLOWED_COURSE_DRIVERS:
            report("FAIL", f"course_driver 非法：{folder.name} -> {pmeta.get('course_driver', '缺失')}")
        if not pmeta.get("updated") or pmeta.get("updated") == "—":
            report("FAIL", f"progress 缺非空 updated：{folder.name}")
        next_action = pmeta.get("next_action") or re.search(
            r"^\s*-\s*\*\*(?:下一步计划|下一步|下次第一件事)\*\*[：:]\s*(.+)$",
            progress_content,
            re.MULTILINE,
        )
        if not next_action:
            report("FAIL", f"progress 缺下一动作：{folder.name}")
        if "mistake_bank（内联）" in progress_content:
            report("FAIL", f"progress 含重复 mistake_bank 内联账本：{folder.name}")
        if lifecycle == "planned":
            # 0.2.2: current_lesson retired; if present must be none.
            if "current_lesson" in pmeta and pmeta.get("current_lesson") != "none":
                report("FAIL", f"planned 课程 current_lesson 必须为 none：{folder.name}")
            if pmeta.get("progress_nodes_status") != "lazy_on_activation":
                report("FAIL", f"planned 课程缺 lazy_on_activation：{folder.name}")
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
                    f"planned 课程 canonical-none 非法：{folder.name} -> {bad}",
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
                report("FAIL", f"ongoing progress 缺字段：{folder.name} -> {missing_progress}")
            else:
                try:
                    COURSE_ROUTES[folder.name] = resolve_activity(
                        ROOT, folder.name, progress_snapshot,
                    )
                except ActivityContractError as exc:
                    for error in exc.errors:
                        report("FAIL", f"当前活动契约：{folder.name} -> {error}")
            if "lesson_position" in pmeta:
                report("FAIL", f"ongoing progress 使用退役 lesson_position：{folder.name}")
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
                    report("FAIL", f"活动课程恢复说明含机器绝对路径：{rel(navigation)}")
        if (folder / "progress_nodes.md").exists():
            report("FAIL", f"progress_nodes 未并入 progress：{folder.name}")
        for required in ("lessons", "exercises", "book"):
            if not (folder / required).is_dir():
                report("FAIL", f"课程缺 {required}/：{folder.name}")
        for required in ("mistake_bank.md", "question_bank.md"):
            if not (folder / required).is_file():
                report("FAIL", f"课程缺 {required}：{folder.name}")
        result[folder.name] = (folder, pmeta)
        course_metas[folder.name] = cmeta

    for course_id, meta in course_metas.items():
        prerequisites = list_value(meta.get("prerequisites", "[]"))
        if len(prerequisites) != len(set(prerequisites)):
            report("FAIL", f"课程 prerequisites 重复：{course_id}")
        if course_id in prerequisites:
            report("FAIL", f"课程 prerequisites 自引用：{course_id}")
        for prerequisite in prerequisites:
            if prerequisite not in course_metas:
                report("FAIL", f"课程 prerequisite 不存在：{course_id} -> {prerequisite}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(course_id: str) -> None:
        if course_id in visiting:
            report("FAIL", f"课程 prerequisites 存在循环：{course_id}")
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


def check_groups(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    root = MAIN / "30_group"
    groups: list[tuple[str, Path, dict[str, str]]] = []
    if root.exists():
        for folder in sorted(path for path in root.iterdir() if path.is_dir() and re.fullmatch(r"G\d+", path.name)):
            plan = folder / "plan.md"
            if not plan.exists():
                report("FAIL", f"课程组缺 plan.md：{folder.name}")
                continue
            for required in ("calendar.md", "review.md", "bindings"):
                if not (folder / required).exists():
                    report("FAIL", f"课程组缺 {required}：{folder.name}")
            meta = frontmatter(plan)
            if meta.get("type") != "group" or meta.get("group_id") != folder.name:
                report("FAIL", f"group frontmatter 不匹配：{rel(plan)}")
            groups.append((folder.name, folder, meta))
    active = [item for item in groups if item[2].get("status") == "active"]
    expected = 0 if FLAVOR == "skeleton" else 1
    if len(active) != expected:
        report("FAIL", f"active group 数量应为 {expected}，实际 {len(active)}")
    for group_id, _, meta in active:
        members = list_value(meta.get("course_members", "[]"))
        if not members:
            report("FAIL", f"active group 无课程成员：{group_id}")
        for course_id in members:
            if course_id not in courses:
                report("FAIL", f"{group_id} 引用不存在课程：{course_id}")
                continue
            lifecycle = courses[course_id][1].get("lifecycle_status", "")
            if lifecycle in {"planned", "completed", "dropped"}:
                report("FAIL", f"{group_id} 包含 {lifecycle} 课程：{course_id}")
        current = meta.get("current_course", "")
        if current and current not in members:
            report("FAIL", f"{group_id} current_course 不在成员中：{current}")
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
            report("FAIL", f"binding schema 不完整：{rel(binding)}")
            continue
        binding_id = meta.get("binding_id", "")
        course_id = meta.get("course_id", "")
        group_id = meta.get("group_id", "")
        status = meta.get("binding_status", "")
        if not re.fullmatch(r"R\d{3}", binding_id):
            report("FAIL", f"binding_id 非法：{rel(binding)} -> {binding_id}")
        if binding_id in binding_ids:
            report("FAIL", f"binding_id 重复：{binding_id}")
        binding_ids.add(binding_id)
        if binding.name != f"{binding_id}_{course_id}.md":
            report("FAIL", f"binding 文件名与 ID/course 不一致：{rel(binding)}")
        if group_id != binding.parents[1].name or group_id not in group_ids:
            report("FAIL", f"binding group 引用不闭合：{rel(binding)} -> {group_id}")
        if status not in ALLOWED_BINDING_STATES:
            report("FAIL", f"binding 状态非法：{rel(binding)} -> {status}")
        if meta.get("execution_mode") != "flexible":
            report("FAIL", f"binding execution_mode 非法：{rel(binding)}")
        if course_id not in courses:
            report("FAIL", f"binding 引用不存在课程：{rel(binding)}")
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
            report("FAIL", f"binding 绑定非法课程类型：{rel(binding)} -> {course_type}")
        if meta.get("legacy_frozen") and not frozen_r002:
            report("FAIL", f"binding 冒用 legacy_frozen：{rel(binding)}")


def check_engagements_and_activities() -> None:
    engagements = MAIN / "10_student/engagements"
    if FLAVOR == "skeleton":
        for root in (MAIN / "10_student/engagements",):
            if not root.is_dir():
                report("FAIL", f"Skeleton 缺空模板域：{rel(root)}")
                continue
            leaked = [
                path for path in root.iterdir()
                if not path.name.startswith("_")
            ]
            if leaked:
                report("FAIL", f"Skeleton 空模板域含实例：{rel(root)}")
    if engagements.exists():
        for folder in sorted(path for path in engagements.iterdir() if path.is_dir()):
            carrier = folder / "engagement.md"
            if not carrier.exists():
                report("FAIL", f"Engagement 缺 engagement.md：{rel(folder)}")
                continue
            meta = frontmatter(carrier)
            if meta.get("type") != "engagement" or meta.get("engagement_id") not in folder.name:
                report("FAIL", f"Engagement schema/ID 不匹配：{rel(carrier)}")
            governance = meta.get("governance")
            if governance not in {"internal", "external"}:
                report("FAIL", f"Engagement governance 非法：{rel(carrier)}")
            if governance == "external" and not meta.get("governance_source"):
                report("FAIL", f"外部治理 Engagement 缺 governance_source：{rel(carrier)}")
            if (folder / "field_practice.md").exists():
                report("FAIL", f"旧 field_practice.md 仍存在：{rel(folder)}")
    activities = MAIN / "10_student/activities"
    if not activities.is_dir():
        report("FAIL", f"缺 ActivityRecord 域：{rel(activities)}")
        return
    records: dict[str, Path] = {}
    sidecars: list[tuple[Path, str, str]] = []
    for entry in sorted(activities.iterdir()):
        if entry.is_symlink():
            report("FAIL", f"ActivityRecord 域禁止 symlink/reparse：{rel(entry)}")
            continue
        if entry.is_file():
            if re.fullmatch(r"AR-.*\.md", entry.name):
                report("FAIL", f"ActivityRecord 仍在根目录：{rel(entry)}")
            elif not entry.name.startswith("_"):
                report("FAIL", f"ActivityRecord 根目录非法旁路文件：{rel(entry)}")
            continue
        if not entry.is_dir():
            report("FAIL", f"ActivityRecord 根目录非法对象：{rel(entry)}")
            continue
        kind = entry.name
        if kind not in ALLOWED_ACTIVITY_KINDS:
            report("FAIL", f"ActivityRecord kind 未登记：{rel(entry)}")
            continue
        for path in sorted(entry.iterdir()):
            if path.is_symlink():
                report("FAIL", f"ActivityRecord kind 禁止 symlink/reparse：{rel(path)}")
                continue
            if path.is_dir():
                report("FAIL", f"ActivityRecord 嵌套过深：{rel(path)}")
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
                    report("FAIL", f"ActivityRecord type 非法：{rel(path)}")
                if meta.get("activity_record_id") != artifact_id:
                    report("FAIL", f"ActivityRecord 文件名/frontmatter ID 不一致：{rel(path)}")
                if meta.get("activity_kind") != kind:
                    report("FAIL", f"ActivityRecord 父目录/kind 不一致：{rel(path)}")
                if artifact_id in records:
                    report(
                        "FAIL",
                        f"ActivityRecord ID 跨 kind 重复：{artifact_id} -> "
                        f"{rel(records[artifact_id])}, {rel(path)}",
                    )
                else:
                    records[artifact_id] = path
                if FLAVOR == "skeleton":
                    report("FAIL", f"Skeleton ActivityRecord 空容器含真实实例：{rel(path)}")
            elif sidecar_match:
                sidecars.append((path, sidecar_match.group(1), sidecar_match.group(2)))
                if FLAVOR == "skeleton":
                    report("FAIL", f"Skeleton ActivityRecord 空容器含真实 sidecar：{rel(path)}")
            elif not path.name.startswith("_"):
                report("FAIL", f"ActivityRecord kind 非法旁路文件：{rel(path)}")
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
            report("FAIL", f"reading bridge storage schema 无法读取：{rel(schema_path)} -> {exc}")
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
            report("FAIL", f"ActivityRecord sidecar 合同非法：{rel(path)} -> {exc}")
            continue
        if value.get("activity_record_id") != artifact_id:
            report("FAIL", f"ActivityRecord sidecar 内部 ID 不一致：{rel(path)}")
        if sidecar_kind == "context":
            if value.get("confirmed_by") != "student":
                report("FAIL", f"reading context source 缺人工确认：{rel(path)}")
            if value.get("target_reading_uri") is None and (
                value.get("course_id") is not None
                or value.get("reading_intents")
                or value.get("questions_or_observation_cues")
            ):
                report("FAIL", f"无 reading URI 的 context 必须为空：{rel(path)}")
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
                report("FAIL", f"reading contribution ledger 重复对象：{rel(path)} -> {contribution_id}")
            local_contributions.add(contribution_id)
            if contribution_id in global_contribution_ids:
                report(
                    "FAIL",
                    f"reading contribution ID 跨 AR 重复：{contribution_id} -> "
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
                report("FAIL", f"reading contribution payload/digest/target 非法：{rel(path)} -> {contribution_id}")
        for row in processed:
            event_id = row.get("event_id", "")
            if event_id in event_ids:
                report("FAIL", f"reading contribution processed event 重复：{rel(path)} -> {event_id}")
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
                report("FAIL", f"reading contribution processed event 悬空：{rel(path)} -> {event_id}")
        local_receipts: set[str] = set()
        for row in outbox:
            receipt_id = row.get("receipt_id", "")
            payload = row.get("payload", {})
            ack = row.get("ack_result")
            if receipt_id in local_receipts:
                report("FAIL", f"reading receipt outbox 重复 ID：{rel(path)} -> {receipt_id}")
            local_receipts.add(receipt_id)
            if receipt_id in global_receipt_ids:
                report(
                    "FAIL",
                    f"reading receipt ID 跨 AR 重复：{receipt_id} -> "
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
                report("FAIL", f"reading receipt outbox payload/digest/target 非法：{rel(path)} -> {receipt_id}")
            if (row.get("status") == "pending") != (ack is None):
                report("FAIL", f"reading receipt outbox status/ack 不一致：{rel(path)} -> {receipt_id}")
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
                    report("FAIL", f"reading receipt ack 绑定非法：{rel(path)} -> {receipt_id}")


def check_question_banks(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    for course_id, (folder, _) in courses.items():
        bank = folder / "question_bank.md"
        if not bank.exists():
            continue
        content = read(bank)
        if "QUESTION_BANK_TEMPLATE_V2" not in content:
            report("FAIL", f"question bank 未升级 V2：{course_id}")
        for match in re.finditer(r"^-\s*状态[：:]\s*([A-Za-z_]+)\s*$", content, re.MULTILINE):
            if match.group(1) not in ALLOWED_QUESTION_STATES:
                report("FAIL", f"question 状态非法：{course_id} -> {match.group(1)}")


def check_knowledge_ledgers(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    for course_id, (folder, _) in courses.items():
        question_bank = folder / "question_bank.md"
        if question_bank.is_file():
            content = read(question_bank)
            body = without_fenced_code(content)
            ids = [int(value) for value in re.findall(r"^###\s+Q-(\d{4})(?:\s*｜.*)?$", body, re.MULTILINE)]
            if len(ids) != len(set(ids)):
                report("FAIL", f"question ID 重复：{course_id}")
            next_id = re.search(r"^next_id:\s*(\d+)\s*$", content, re.MULTILINE)
            if not next_id:
                report("FAIL", f"question bank 缺 next_id：{course_id}")
            elif ids and int(next_id.group(1)) <= max(ids):
                report("FAIL", f"question bank next_id 未超过最大 Q ID：{course_id}")

        mistake_bank = folder / "mistake_bank.md"
        if not mistake_bank.is_file():
            continue
        content = read(mistake_bank)
        for section in ("## 活跃知识点", "## 维护知识点", "## 陈年知识点"):
            if section not in content:
                report("FAIL", f"mistake bank 缺分区 {section}：{course_id}")
        body = without_fenced_code(content)
        entries = list(re.finditer(r"^###\s+M-(\d{4})\s*$", body, re.MULTILINE))
        ids = [int(match.group(1)) for match in entries]
        if len(ids) != len(set(ids)):
            report("FAIL", f"mistake ID 重复：{course_id}")
        next_id = re.search(r"^next_id:\s*(\d+)\s*$", content, re.MULTILINE)
        if not next_id:
            report("FAIL", f"mistake bank 缺 next_id：{course_id}")
        elif ids and int(next_id.group(1)) <= max(ids):
            report("FAIL", f"mistake bank next_id 未超过最大 M ID：{course_id}")
        for index, match in enumerate(entries):
            end = entries[index + 1].start() if index + 1 < len(entries) else len(body)
            block = body[match.end():end]
            state = re.search(r"^-\s*状态[：:]\s*([a-z_]+)\s*$", block, re.MULTILINE)
            if not state or state.group(1) not in ALLOWED_MISTAKE_STATES:
                report("FAIL", f"mistake 状态缺失或非法：{course_id}/M-{match.group(1)}")
            for field in (
                "知识点键", "当前周期", "当前周期摘要", "陈年连续正确",
                "最近陈年复习卷", "下次陈年日历检查",
            ):
                if not re.search(rf"^-\s*{re.escape(field)}[：:]\s*.+$", block, re.MULTILINE):
                    report("FAIL", f"mistake 条目缺{field}：{course_id}/M-{match.group(1)}")

    reasoning = MAIN / "10_student/profile/reasoning_patterns.md"
    if reasoning.is_file():
        body = without_fenced_code(read(reasoning))
        ids = re.findall(r"^###\s+(RP-\d{4})(?:\s+.*)?$", body, re.MULTILINE)
        if len(ids) != len(set(ids)):
            report("FAIL", "reasoning pattern ID 重复")
        entries = list(re.finditer(r"^###\s+(RP-\d{4})(?:\s+.*)?$", body, re.MULTILINE))
        for index, match in enumerate(entries):
            end = entries[index + 1].start() if index + 1 < len(entries) else len(body)
            block = body[match.end():end]
            state = re.search(r"^-\s*状态[：:]\s*(观察中|已确认|已退役)\s*$", block, re.MULTILINE)
            if not state:
                report("FAIL", f"reasoning pattern 缺合法状态：{match.group(1)}")


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
        report("FAIL", f"已完成项目节点关闭证据未引用实际验收记录：{node_id or course_id}")
        return
    target = (ROOT / match.group(1)).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        report("FAIL", f"项目验收记录引用越出发行根：{node_id or course_id}")
        return
    if not target.is_file():
        report("FAIL", f"项目验收记录文件不存在：{node_id or course_id} -> {match.group(1)}")
        return
    record_id = match.group(2)
    record_match = re.search(
        rf"^#{{3,6}}[ \t]+{re.escape(record_id)}(?:[ \t]+[^\r\n]*)?[ \t]*\r?\n"
        rf"(.*?)(?=^#{{1,6}}[ \t]+|\Z)",
        read(target),
        re.MULTILINE | re.DOTALL,
    )
    if not record_match:
        report("FAIL", f"关闭证据引用的验收记录不存在：{node_id or course_id} -> {record_id}")
        return
    body = record_match.group(1)

    def field(label: str) -> str:
        value = re.search(
            rf"^-\s*{re.escape(label)}[：:]\s*(\S.*)$",
            body,
            re.MULTILINE,
        )
        return value.group(1).strip() if value else ""

    if field("节点").strip("` ") != node_id:
        report("FAIL", f"项目验收记录节点不匹配：{node_id or course_id} -> {record_id}")
    if field("验证模式").strip("` ") != mode:
        report("FAIL", f"项目验收记录模式不匹配：{node_id or course_id} -> {record_id}")
    if field("结论") != "passed":
        report("FAIL", f"项目验收记录未通过：{node_id or course_id} -> {record_id}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", field("验收日期")):
        report("FAIL", f"项目验收记录缺合法日期：{node_id or course_id} -> {record_id}")
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
            f"项目验收记录步骤未闭合（缺 passed + 实际结果摘要）："
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
            report("FAIL", f"项目课缺 Completion nodes 表：{course_id}")
            continue
        required_columns = {"验收标准", "关闭证据"}
        if not required_columns.issubset(rows[0]):
            report("FAIL", f"项目课 Completion nodes 未拆分验收标准与关闭证据：{course_id}")
            continue
        for row in rows:
            node_id = row.get("node_id", "")
            status = row.get("状态", "")
            mode = row.get("验证模式", "")
            standard = row.get("验收标准", "")
            evidence = row.get("关闭证据", "")
            if standard.strip("` ") in {"", "-", "—", "NONE"}:
                report("FAIL", f"项目节点缺验收标准：{node_id or course_id}")
            if status in {"in_progress", "completed"} and mode not in ALLOWED_PROJECT_MODES:
                report("WARN", f"已启动项目节点缺验证模式：{node_id or course_id}")
            elif mode and mode not in ALLOWED_PROJECT_MODES:
                report("FAIL", f"项目节点验证模式非法：{node_id or course_id} -> {mode}")
            if status == "completed" and evidence.strip("` ") in {"", "-", "—", "NONE"}:
                report("FAIL", f"已完成项目节点缺关闭证据：{node_id or course_id}")
            elif status == "completed":
                _validate_project_closure_record(course_id, node_id, mode, evidence)
            elif evidence.strip("` ") not in {"", "-", "—", "NONE"}:
                report("FAIL", f"未完成项目节点预填关闭证据：{node_id or course_id}")


def exercise_problem_statements(
    content: str,
    exercise_id: str,
) -> dict[str, str]:
    """Return the final 题面 field of each stable problem section."""
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
            r"^-\s*题面[：:]\s*(.*)\Z",
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
        return {}, [], [f"迁移正式证据无法读取：{exc}"]
    if not isinstance(manifest, dict) or not isinstance(migration_report, dict):
        return {}, [], ["迁移正式证据顶层必须为对象"]

    if migration_report.get("status") != "applied":
        errors.append("迁移报告 status 必须为 applied")
    applied_count = migration_report.get("applied_count")
    if not isinstance(applied_count, int) or applied_count <= 0:
        errors.append("迁移报告 applied_count 缺失或非法")
    duplicates = migration_report.get("post_apply_duplicate_active_canonicals")
    if not isinstance(duplicates, list) or duplicates:
        errors.append("迁移报告 post-apply canonical 证据缺失或非空")

    manifest_ref = migration_report.get("operation_manifest")
    if not isinstance(manifest_ref, dict):
        errors.append("迁移报告缺 operation_manifest 引用块")
        manifest_ref = {}
    if manifest_ref.get("path") != "main/60_journal/migration_020_operations.json":
        errors.append("迁移报告中的 operation_manifest 路径缺失或非法")
    if not isinstance(manifest_ref.get("operation_count"), int):
        errors.append("迁移报告中的 operation_manifest operation_count 缺失或非法")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest_ref.get("sha256", ""))):
        errors.append("迁移报告中的 operation_manifest sha256 缺失或非法")
    elif (
        manifest_ref.get("sha256")
        != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ):
        errors.append("迁移报告中的 operation_manifest SHA 漂移")

    if manifest.get("schema_version") != "T2AG-MIGRATION-OPERATIONS-1":
        errors.append("迁移逐操作 manifest schema_version 缺失或非法")
    if manifest.get("target_kind") != expected_target_kind:
        errors.append(
            "迁移逐操作 manifest target_kind 漂移："
            f"expected={expected_target_kind} actual={manifest.get('target_kind')}"
        )
    if not isinstance(manifest.get("evidence_source"), str) or not str(
        manifest.get("evidence_source", "")
    ).strip():
        errors.append("迁移逐操作 manifest 缺 evidence_source")

    rows_value = manifest.get("operations")
    rows = (
        rows_value
        if isinstance(rows_value, list)
        and all(isinstance(row, dict) for row in rows_value)
        else []
    )
    if rows_value != rows:
        errors.append("迁移逐操作 manifest operations 必须为对象列表")
    manifest_count = manifest.get("operation_count")
    if (
        not isinstance(manifest_count, int)
        or manifest_count <= 0
        or manifest_count != len(rows)
        or manifest_count != applied_count
        or manifest_count != manifest_ref.get("operation_count")
    ):
        errors.append("迁移逐操作 manifest 与 apply/report 数量不一致")
    if [row.get("sequence") for row in rows] != list(range(1, len(rows) + 1)):
        errors.append("迁移逐操作 manifest sequence 不连续")

    for row in rows:
        sequence = row.get("sequence")
        for key in ("kind", "target", "disposition"):
            if not isinstance(row.get(key), str) or not str(row.get(key)).strip():
                errors.append(
                    f"迁移逐操作 manifest 字段不完整：sequence={sequence} key={key}"
                )
        sources = row.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(
                f"迁移逐操作 manifest sources 缺失：sequence={sequence}"
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
                        f"迁移逐操作 manifest source 非法：sequence={sequence}"
                    )
                    break
        if row.get("outcome") != "applied":
            errors.append(
                f"迁移逐操作 manifest outcome 非 applied：sequence={sequence}"
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
                f"迁移逐操作 manifest post_target 非法：sequence={sequence}"
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
                report("FAIL", f"教材课程有 Lesson/Exercise 但缺活动连接表：{course_id}")
            elif (
                activity_meta.get("type") != "course_activity_map"
                or activity_meta.get("course_id") != course_id
            ):
                report("FAIL", f"课程活动连接表 frontmatter 不匹配：{rel(activity_map)}")
            else:
                activity_rows = table_after_heading(read(activity_map), "内容组连接表")
                required_columns = {
                    "content_group_id", "source_scope", "lesson_ids",
                    "exercise_ids",
                }
                if not activity_rows or not required_columns.issubset(activity_rows[0]):
                    report("FAIL", f"课程活动连接表不可解析或缺列：{rel(activity_map)}")
                    activity_rows = []
                else:
                    activity_map_ready = True
                seen_groups: set[str] = set()
                for row in activity_rows:
                    group_id = row.get("content_group_id", "").strip("` ")
                    if not re.fullmatch(rf"{re.escape(course_id)}-B\d+-C\d+-S\d+", group_id):
                        report("FAIL", f"活动连接表 ContentGroup ID 非法：{course_id} -> {group_id}")
                    if group_id in seen_groups:
                        report("FAIL", f"活动连接表 ContentGroup 重复：{course_id} -> {group_id}")
                    seen_groups.add(group_id)
                    lesson_ids = reference_list(row.get("lesson_ids", ""))
                    exercise_ids = reference_list(row.get("exercise_ids", ""))
                    if len(lesson_ids) != len(set(lesson_ids)):
                        report(
                            "FAIL",
                            f"活动连接表 lesson_ids 重复：{course_id} -> {group_id}",
                        )
                    if len(exercise_ids) != len(set(exercise_ids)):
                        report(
                            "FAIL",
                            f"活动连接表 exercise_ids 重复：{course_id} -> {group_id}",
                        )
                    if not lesson_ids and not exercise_ids:
                        report("FAIL", f"活动连接表内容组没有任何学习活动：{course_id} -> {group_id}")
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
                            report("FAIL", f"活动连接表 Lesson 悬空或 frontmatter 不匹配：{course_id} -> {lesson_id}")
                    for exercise_id in exercise_ids:
                        rows_by_unit.setdefault(exercise_id, []).append(row)
                        if exercise_id not in unit_names:
                            report("FAIL", f"活动连接表 Exercise 悬空：{course_id} -> {exercise_id}")
        for lesson_id, lesson in lessons.items():
            lesson_meta = frontmatter(lesson)
            lesson_content = read(lesson)
            if (
                lesson_meta.get("type") != "lesson"
                or lesson_meta.get("course_id") != course_id
                or lesson_meta.get("lesson_id") != lesson_id
            ):
                report("FAIL", f"Lesson frontmatter 不匹配：{rel(lesson)}")
            if "T2AG_GENERATED:LESSON_PROGRESS" in lesson_content:
                report("FAIL", f"Lesson 含无主 GENERATED 进度块：{rel(lesson)}")
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
                    f"Lesson 使用退役活动所有权字段：{rel(lesson)} -> {retired_fields}",
                )
            declared_group_ids = reference_list(lesson_meta.get("content_group_ids", ""))
            if len(declared_group_ids) != len(set(declared_group_ids)):
                report("FAIL", f"Lesson content_group_ids 重复：{rel(lesson)}")
            if progress_meta.get("course_driver") != "textbook":
                continue
            if not activity_map_ready:
                continue
            link_rows = rows_by_lesson.get(lesson_id, [])
            if not link_rows:
                report("FAIL", f"Lesson 未在活动连接表中出现：{rel(lesson)}")
            expected_groups = {
                row.get("content_group_id", "").strip("` ")
                for row in link_rows
            }
            declared_groups = set(declared_group_ids)
            if declared_groups != expected_groups:
                report(
                    "FAIL",
                    f"Lesson 与活动连接表 ContentGroup 漂移：{lesson_id} -> "
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
                report("FAIL", f"习题单元 ID 非法：{rel(unit)}")
                continue
            exercise = unit / "exercise.md"
            exercise_meta = frontmatter(exercise)
            if (
                not exercise.is_file()
                or exercise_meta.get("type") != "exercise"
                or exercise_meta.get("course_id") != course_id
                or exercise_meta.get("exercise_id") != unit.name
            ):
                report("FAIL", f"Exercise 主载体缺失或 frontmatter 不匹配：{rel(unit)}")
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
                    f"Exercise 使用退役活动所有权字段：{unit.name} -> {retired_fields}",
                )
            sessions = unit / "sessions"
            session_objects = [
                path for path in unit.rglob("*.md")
                if path != exercise and frontmatter(path).get("type") == "exercise_session"
            ]
            if sessions.is_dir() or session_objects:
                location = sessions if sessions.is_dir() else session_objects[0]
                report("FAIL", f"Exercise 包含退役 ExerciseSession：{rel(location)}")
            declared_group_ids = reference_list(exercise_meta.get("content_group_ids", ""))
            if len(declared_group_ids) != len(set(declared_group_ids)):
                report("FAIL", f"Exercise content_group_ids 重复：{unit.name}")
            declared_groups = set(declared_group_ids)
            problems = unit / "problems.md"
            if not problems.is_file():
                report("FAIL", f"习题单元缺 problems.md：{rel(unit)}")
                continue
            meta = frontmatter(problems)
            if (
                meta.get("type") != "exercise_problem_set"
                or meta.get("course_id") != course_id
                or meta.get("exercise_id") != unit.name
            ):
                report("FAIL", f"Exercise 题目集 frontmatter 不匹配：{rel(problems)}")
            content_group_id = meta.get("content_group_id", "")
            source = ROOT / "__missing__"
            if progress_meta.get("course_driver") == "textbook":
                if not re.fullmatch(rf"{re.escape(course_id)}-B\d+-C\d+-S\d+", content_group_id):
                    report("FAIL", f"教材习题单元 content_group_id 非法：{rel(problems)}")
                link_rows = rows_by_unit.get(unit.name, [])
                linked_groups = {row.get("content_group_id", "").strip("` ") for row in link_rows}
                if not link_rows:
                    report("FAIL", f"Exercise 未在活动连接表中出现：{rel(problems)}")
                if linked_groups != declared_groups:
                    report("FAIL", f"Exercise 与活动连接表 ContentGroup 漂移：{unit.name}")
                if content_group_id not in declared_groups:
                    report("FAIL", f"题目集 content_group_id 未由 Exercise 声明：{unit.name}")
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
                        f"教材习题缺持久题源字段：{rel(problems)} -> "
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
                            f"教材习题持久题源路径非法：{unit.name} -> {message}",
                        )
                if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
                    report("FAIL", f"教材习题 source_sha256 非法：{unit.name}")
                elif source is not None and hashlib.sha256(
                    source.read_bytes()
                ).hexdigest() != source_sha:
                    report("FAIL", f"教材习题持久题源 SHA 漂移：{unit.name}")
                artifact = registry.get(source_artifact_id, {})
                if (
                    artifact.get("status") != "active"
                    or artifact.get("canonical_path") != source_path
                ):
                    report(
                        "FAIL",
                        f"教材习题题源未解析到 active registry canonical："
                        f"{unit.name} -> {source_artifact_id or '缺失'}",
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
                            f"教材习题持久题源 frontmatter 不匹配：{rel(source)}",
                        )
                    source_document = source_meta.get("source_document", "")
                    source_document_sha = source_meta.get(
                        "source_document_sha256", ""
                    )
                    if not re.fullmatch(r"[0-9a-f]{64}", source_document_sha):
                        report(
                            "FAIL",
                            f"教材习题源文档 source_document_sha256 非法：{unit.name}",
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
                                f"教材习题源文档路径非法：{unit.name} -> {message}",
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
                            f"教材习题源文档 SHA 漂移：{unit.name}",
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
                            "Lite 省略的教材源文档未由哈希绑定 manifest 证明："
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
                report("FAIL", f"习题条目结构不可解析：{rel(problems)}")
                continue
            if len(headings) != len(set(headings)):
                report("FAIL", f"习题 problem_id 重复：{rel(problems)}")
            if progress_meta.get("course_driver") == "textbook":
                source_order = list_value(meta.get("source_order", "[]"))
                teaching_sequence = list_value(meta.get("teaching_sequence", "[]"))
                for label, sequence in (
                    ("source_order", source_order),
                    ("teaching_sequence", teaching_sequence),
                ):
                    if len(sequence) != len(set(sequence)) or set(sequence) != set(headings):
                        report("FAIL", f"教材习题 {label} 未完整覆盖题目：{rel(problems)}")
                if source_order and source_order != headings:
                    report("FAIL", f"教材习题 source_order 与题面顺序不一致：{rel(problems)}")
                if teaching_sequence != source_order and not meta.get("sequence_rationale"):
                    report("FAIL", f"教材习题重排缺 sequence_rationale：{rel(problems)}")
            bare_numbers: list[int] = []
            for heading, entry in zip(headings, entries):
                required = (
                    "题号", "来源页", "难度", "依赖 completion node",
                    "状态", "错误级别", "题面",
                )
                missing = [
                    field for field in required
                    if not re.search(rf"^-\s*{re.escape(field)}[：:]", entry, re.MULTILINE)
                ]
                if missing:
                    report("FAIL", f"习题字段缺失：{heading} -> {missing}")
                number = re.search(r"^-\s*题号[：:]\s*(\d+)\s*$", entry, re.MULTILINE)
                if not number:
                    report("FAIL", f"习题题号不是裸整数：{heading}")
                else:
                    bare_numbers.append(int(number.group(1)))
                state = re.search(r"^-\s*状态[：:]\s*([A-Za-z_]+)\s*$", entry, re.MULTILINE)
                if not state or state.group(1) not in ALLOWED_QUESTION_STATES:
                    report("FAIL", f"习题状态非法：{heading}")
                dependency_line = re.search(
                    r"^-\s*依赖 completion node[：:]\s*(.*?)\s*$",
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
                            f"教材习题依赖 completion node 格式非法："
                            f"{heading} -> {raw_dependency or '（空）'}",
                        )
                    elif not re.fullmatch(
                        rf"{re.escape(content_group_id)}-N\d+",
                        dependency_id,
                    ):
                        report(
                            "FAIL",
                            f"教材习题依赖越出内容组：{heading} -> {dependency_id}",
                        )
                    elif dependency_id not in completion_node_ids:
                        report(
                            "FAIL",
                            f"教材习题依赖 completion node 不存在："
                            f"{heading} -> {dependency_id}",
                        )
            if len(bare_numbers) != len(set(bare_numbers)):
                report("FAIL", f"习题裸题号重复：{rel(problems)}")
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
                        f"持久题源未完整覆盖教材习题：{unit.name} -> "
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
                        f"教材习题题面与持久题源不一致：{unit.name} -> "
                        f"{mismatched}",
                    )
            for required_dir in ("attempts", "reviews"):
                if not (unit / required_dir).is_dir():
                    report("FAIL", f"习题单元缺 {required_dir}/：{rel(unit)}")

            problem_ids = set(headings)
            attempts: dict[str, set[str]] = {}
            attempt_root = unit / "attempts"
            if attempt_root.is_dir():
                for attempt_dir in sorted(
                    path for path in attempt_root.iterdir()
                    if path.is_dir() and not path.name.startswith("_")
                ):
                    if not re.fullmatch(r"AT\d{4}", attempt_dir.name):
                        report("FAIL", f"Attempt ID 非法：{rel(attempt_dir)}")
                        continue
                    carrier = attempt_dir / "attempt.md"
                    if not carrier.is_file():
                        report("FAIL", f"Attempt 缺 attempt.md：{rel(attempt_dir)}")
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
                        report("FAIL", f"Attempt frontmatter 不匹配：{rel(carrier)}")
                    if not attempt_problem_ids:
                        report("FAIL", f"Attempt 未引用题目：{rel(carrier)}")
                    unknown = sorted(attempt_problem_ids - problem_ids)
                    if unknown:
                        report("FAIL", f"Attempt 引用未知题目：{rel(carrier)} -> {unknown}")
                    mode = ameta.get("mode", "")
                    if mode not in ALLOWED_ATTEMPT_MODES:
                        report("FAIL", f"Attempt mode 非法：{rel(carrier)} -> {mode}")
                    if ameta.get("status") not in ALLOWED_ATTEMPT_STATES:
                        report("FAIL", f"Attempt status 非法：{rel(carrier)}")
                    created = ameta.get("created", "")
                    created_date: dt.date | None = None
                    try:
                        created_date = dt.date.fromisoformat(created)
                    except (TypeError, ValueError):
                        pass
                    if created_date is None or created_date.isoformat() != created:
                        report("FAIL", f"Attempt created 非法 ISO 日期：{rel(carrier)} -> {created or '—'}")
                    gate_snapshot = ameta.get("hint_gate", "")
                    assistance_level = ameta.get("assistance_level", "")
                    requires_gate_snapshot = bool(
                        created_date is not None
                        and created_date >= HINT_GATE_SCHEMA_DATE
                    )
                    if requires_gate_snapshot and (
                        not gate_snapshot or not assistance_level
                    ):
                        report("FAIL", f"Attempt 缺提示闸门快照：{rel(carrier)}")
                    if gate_snapshot and gate_snapshot not in ALLOWED_HINT_GATE_MODES:
                        report(
                            "FAIL",
                            f"Attempt hint_gate 非法：{rel(carrier)} -> {gate_snapshot}",
                        )
                    if (
                        assistance_level
                        and assistance_level not in ALLOWED_ASSISTANCE_LEVELS
                    ):
                        report(
                            "FAIL",
                            "Attempt assistance_level 非法："
                            f"{rel(carrier)} -> {assistance_level}",
                        )
                    if bool(gate_snapshot) != bool(assistance_level):
                        report("FAIL", f"Attempt 提示闸门快照字段不成对：{rel(carrier)}")
                    attempt_text = read(carrier)
                    if not markdown_section(attempt_text, "作答上下文"):
                        report("FAIL", f"Attempt 缺作答上下文：{rel(carrier)}")
                    for problem_id in sorted(attempt_problem_ids):
                        response = markdown_section(attempt_text, problem_id)
                        answer = re.search(r"^-\s*作答[：:]\s*(\S.*)$", response, re.MULTILINE)
                        if not answer:
                            report("FAIL", f"Attempt 缺逐题作答：{attempt_dir.name} -> {problem_id}")
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
                            report("FAIL", f"image/mixed Attempt 缺原始图片：{rel(attempt_dir)}")

            review_root = unit / "reviews"
            if review_root.is_dir():
                for review in sorted(
                    path for path in review_root.iterdir()
                    if path.is_file() and not path.name.startswith("_")
                ):
                    if not re.fullmatch(r"RV\d{4}\.md", review.name):
                        report("FAIL", f"Review 文件名非法：{rel(review)}")
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
                        report("FAIL", f"Review frontmatter 不匹配：{rel(review)}")
                    if attempt_id not in attempts:
                        report("FAIL", f"Review 引用未知 Attempt：{rel(review)} -> {attempt_id}")
                    elif not review_problem_ids or not review_problem_ids.issubset(attempts[attempt_id]):
                        report("FAIL", f"Review 题目越过 Attempt：{rel(review)}")
                    if rmeta.get("reviewer") not in ALLOWED_REVIEWERS:
                        report("FAIL", f"Review reviewer 非法：{rel(review)}")
                    if rmeta.get("status") not in ALLOWED_REVIEW_STATES:
                        report("FAIL", f"Review status 非法：{rel(review)}")
                    if not rmeta.get("reviewed") or rmeta.get("reviewed") == "—":
                        report("FAIL", f"Review 缺 reviewed：{rel(review)}")
                    review_text = read(review)
                    for problem_id in sorted(review_problem_ids):
                        body = markdown_section(review_text, problem_id)
                        result = re.search(r"^-\s*结果[：:]\s*([a-z_]+)\s*$", body, re.MULTILINE)
                        if not result or result.group(1) not in ALLOWED_REVIEW_RESULTS:
                            report("FAIL", f"Review 逐题结果非法：{review_id} -> {problem_id}")
                        for field in ("思路观察", "反馈", "mistake_refs", "question_refs"):
                            if not re.search(rf"^-\s*{re.escape(field)}[：:]", body, re.MULTILINE):
                                report("FAIL", f"Review 缺逐题字段：{review_id}/{problem_id} -> {field}")

    if FLAVOR != "skeleton" and "MATH1607H" in courses:
        math_root = courses["MATH1607H"][0]
        has_legacy = (math_root / "exercises/U1101/problems.md").is_file()
        has_canonical = (math_root / "exercises/exercise01/problems.md").is_file()
        if not (has_legacy or has_canonical):
            report(
                "FAIL",
                "MATH1607H 缺 Exercise 习题册（U1101 或 exercise01）",
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
        if re.search(r"记录错误.*lessonXX|错误.*写入.*lessonXX", content):
            report(
                "FAIL",
                f"教师模板绕过当前活动路由写 Lesson：{rel(template)}",
            )
        required_route_markers = (
            "统一只读活动路由",
            "当前 Lesson/Exercise 主载体",
            "mistake_bank.md",
            "t2ag_hint_gate.py",
            "不把概念桥接回当前题",
        )
        missing = [
            marker for marker in required_route_markers if marker not in content
        ]
        if missing:
            report(
                "FAIL",
                f"教师模板缺统一错误路由契约：{rel(template)} -> {missing}",
            )
        required_presentation_markers = (
            "先给短目录、树形地图",
            "对象类型表",
            "新 Exercise 未授权阶段",
        )
        missing = [
            marker for marker in required_presentation_markers
            if marker not in content
        ]
        if missing:
            report(
                "FAIL",
                f"教师模板缺地图优先讲解协议：{rel(template)} -> {missing}",
            )
    try:
        return resolve_teacher_mapping(ROOT, set(courses))
    except TeacherContractError as exc:
        for error in exc.errors:
            report("FAIL", f"教师映射契约：{error}")
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
        if not value or values.get(key) != value:
            report("FAIL", f"memory 当前状态指针漂移：{key}={values.get(key, '缺失')} expected={value or '非空'}")
    teacher = teacher_mapping.get(course_id)
    if not teacher:
        report("FAIL", f"当前课程缺教师 overlay 映射：{course_id}")
    else:
        teacher_id = teacher[0]
        expected_teacher = f"TR01 → {teacher_id}"
        if values.get("当前教师") != expected_teacher:
            report(
                "FAIL",
                f"memory 当前教师指针漂移：{values.get('当前教师', '缺失')} "
                f"expected={expected_teacher}",
            )
    memory = read(MAIN / "00_core/t2ag_memory.md")
    for label in ("日期", "学到哪"):
        match = re.search(rf"^-\s*\*\*{label}\*\*[：:]\s*(.+)$", memory, re.MULTILINE)
        if not match or match.group(1).strip() == "—":
            report("FAIL", f"initialized 实例 memory 上次课摘要 {label} 为空")


def path_exists(canonical: str) -> bool:
    path = ROOT / canonical.rstrip("/")
    return path.exists()


def check_registry() -> None:
    path = MAIN / "70_tools/artifact_registry.json"
    try:
        data = json.loads(read(path))
    except (OSError, json.JSONDecodeError) as exc:
        report("FAIL", f"artifact registry 无法读取：{exc}")
        return
    artifacts = data.get("artifacts", [])
    by_id = {item.get("artifact_id"): item for item in artifacts}
    if len(by_id) != len(artifacts):
        report("FAIL", "artifact_id 重复或为空")
    active: dict[str, list[str]] = {}
    temporary_segments = {
        "working_pages", "temppage", "__pycache__", ".staging", ".recovery",  # working_pages: 保留防御性 skip（0.2.2 S3 退役）
    }
    for item in artifacts:
        artifact_id = item.get("artifact_id", "<?>")
        status = item.get("status")
        canonical = item.get("canonical_path", "")
        if status not in ALLOWED_REGISTRY_STATES:
            report("FAIL", f"artifact 状态非法：{artifact_id}={status}")
            continue
        redirects = item.get("redirects", [])
        if len(redirects) != len(set(redirects)):
            report("FAIL", f"redirects 重复：{artifact_id}")
        if canonical in redirects:
            report("FAIL", f"redirect 指向自身 canonical：{artifact_id}")
        canonical_parts = set(Path(canonical.rstrip("/")).parts)
        if (
            status in {"active", "archived"}
            and canonical_parts & temporary_segments
        ):
            report(
                "FAIL",
                f"{status} canonical 落入临时生命周期域："
                f"{artifact_id} -> {canonical}",
            )
        if status == "active":
            active.setdefault(canonical, []).append(artifact_id)
            if not path_exists(canonical):
                report("FAIL", f"active canonical 不存在：{artifact_id} -> {canonical}")
        elif status == "archived":
            if not path_exists(canonical):
                report("FAIL", f"archived canonical 不存在：{artifact_id} -> {canonical}")
        else:
            alias = item.get("alias_to")
            successors = item.get("successors", [])
            if not alias and not successors:
                report("FAIL", f"tombstone 缺 alias_to/successors：{artifact_id}")
            if alias and alias not in by_id:
                report("FAIL", f"tombstone alias 不存在：{artifact_id} -> {alias}")
            for successor in successors:
                if set(Path(successor.rstrip("/")).parts) & temporary_segments:
                    report(
                        "FAIL",
                        f"tombstone successor 落入临时生命周期域："
                        f"{artifact_id} -> {successor}",
                    )
                if not path_exists(successor):
                    report("FAIL", f"tombstone successor 不存在：{artifact_id} -> {successor}")
    for canonical, ids in active.items():
        if len(ids) > 1:
            report("FAIL", f"多个 active artifact 共用 canonical：{canonical} -> {ids}")


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
                    f"working pages 缺当前 Lesson 活动：{course_id} -> {lesson or '缺失'}",
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
                    f"preparation 存在但缺 current_snapshot 指针：{course_id}/{lesson}",
                )
                continue
            try:
                pointer = json.loads(read(pointer_path))
            except (OSError, json.JSONDecodeError) as exc:
                report(
                    "FAIL",
                    f"current Snapshot 指针不可读：{course_id}/{lesson} {exc}",
                )
                continue
            snap_id = str(pointer.get("snapshot_id") or "")
            snap_path = prep_dir / f"{snap_id}.json"
            if not snap_id.startswith("PREP-") or not snap_path.is_file():
                report(
                    "FAIL",
                    f"current Snapshot 指针目标无效：{course_id}/{lesson} -> {snap_id}",
                )
                continue
            try:
                payload = json.loads(read(snap_path))
            except (OSError, json.JSONDecodeError) as exc:
                report(
                    "FAIL",
                    f"preparation Snapshot 不可读：{course_id}/{snap_path.name} {exc}",
                )
                continue
            if payload.get("snapshot_id") != snap_id:
                report("FAIL", f"Snapshot id 与指针不一致：{course_id}/{lesson}")
            if payload.get("state") != "valid":
                report("FAIL", f"preparation Snapshot 非 valid：{course_id}/{snap_path.name}")
            if not payload.get("load_receipt_ids") and not payload.get("load_receipts"):
                report("FAIL", f"preparation Snapshot 缺 load receipts：{course_id}")
            if payload.get("scope_coverage") != "complete":
                report("FAIL", f"preparation Snapshot scope 未 complete：{course_id}")
            if not payload.get("content_consumed"):
                report("FAIL", f"preparation Snapshot content_consumed 为 false：{course_id}")
            page_keys = payload.get("page_keys") or []
            indices = [
                int(k.get("pdf_page_index"))
                for k in page_keys
                if isinstance(k, dict) and k.get("pdf_page_index") is not None
            ]
            if not indices:
                report("FAIL", f"preparation Snapshot 缺 page_keys：{course_id}")
            elif indices != list(range(min(indices), max(indices) + 1)):
                report(
                    "FAIL",
                    f"preparation Snapshot Scope 不连续：{course_id} -> {indices}",
                )
            short = bool(payload.get("short_document"))
            if not short and indices and not (5 <= len(indices) <= 8):
                report(
                    "FAIL",
                    f"preparation Snapshot scope_n 越界（须 5–8）：{course_id} n={len(indices)}",
                )
            if short and indices and len(indices) >= 5:
                report(
                    "FAIL",
                    f"short_document 标记与 scope_n 冲突：{course_id}",
                )
            receipts = payload.get("load_receipts") or []
            if page_keys and len(receipts) != len(page_keys):
                report(
                    "FAIL",
                    f"preparation Snapshot receipts 与 page_keys 数量不一致：{course_id}",
                )
            doc_sha = str(payload.get("source_document_sha256") or "").lower()
            document_id = str(payload.get("document_id") or "")
            for receipt in receipts:
                if not isinstance(receipt, dict):
                    report("FAIL", f"load receipt 非法：{course_id}")
                    continue
                if not receipt.get("source_page_asset_sha256"):
                    report("FAIL", f"load receipt 缺 SourcePageAsset SHA：{course_id}")
                rdoc = str(receipt.get("source_document_sha256") or "").lower()
                if doc_sha and rdoc and rdoc != doc_sha:
                    report("FAIL", f"load receipt SourceDocument SHA 不一致：{course_id}")
            map_path = folder / "lessons" / lesson / "lesson_map.md"
            if not map_path.is_file():
                report("FAIL", f"缺 LessonMap：{course_id}/{lesson}")
            else:
                # Raw file bytes only — must match prepare/Context (no read_text rewrite).
                map_raw = map_path.read_bytes()
                map_sha = hashlib.sha256(map_raw).hexdigest()
                map_text = map_raw.decode("utf-8", errors="replace")
                expected_map = str(payload.get("lesson_map_sha256") or "")
                if expected_map and expected_map != map_sha:
                    report("FAIL", f"LessonMap hash 与 Snapshot 不一致：{course_id}/{lesson}")
                for value in indices:
                    if not re.search(rf"\|\s*{value}\s*\|", map_text) and (
                        f"page_{value}" not in map_text
                    ):
                        report(
                            "FAIL",
                            f"LessonMap 未覆盖 Scope 页：{course_id} page {value}",
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
                                f"Snapshot PDF SHA 与 manifest 不一致：{course_id}",
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
                                        f"SourceDocument PDF SHA 与 Snapshot 不一致：{course_id}",
                                    )
                            else:
                                report(
                                    "FAIL",
                                    f"SourceDocument/PDF 缺失：{course_id} {source_path}",
                                )
                    except (OSError, json.JSONDecodeError) as exc:
                        report(
                            "FAIL",
                            f"source_assets manifest 不可读：{course_id}/{document_id} {exc}",
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
                            f"缺 SourcePageAsset：{course_id} page_{value}",
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
                                f"SourcePageAsset 未核验：{course_id} page_{value}",
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
                    f"cache 超过配额：{course_id} cache_n={cache_n} quota_n={quota_n} "
                    f"scope_n={scope_n}（P0={scope_n} 页不得驱逐）",
                )
            continue
        # Legacy working_pages window retired in 0.2.2 S3.
        # Textbook lessons must use preparation Snapshots exclusively.
        report(
            "FAIL",
            f"textbook lesson 缺 preparation Snapshot，legacy 路径已退役："
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
                f"SCOPE-CACHE-001 Scope 页图未预热：{course_id}/{lesson} "
                f"缺页 {sorted(missing)}；本轮视觉扫描前须现场渲染。预热："
                f"python -B main/70_tools/t2ag_source_pages.py prewarm "
                f"--course {course_id} --lesson {lesson} --render",
            )


GATE_LEDGER_SECTION = "## 门台账"
GATE_LEDGER_PLACEHOLDERS = {"", "-", "—", "待填", "无", "?", "？"}
GATE_LEDGER_HINT_LEVELS = {"direction_hint", "specified_reference", "full_solution"}


def parse_gate_ledger(text: str) -> dict[str, object] | None:
    """Parse one carrier's 门台账 section; None when the section is absent.

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
        r"^ledger_since:.*?(?:起算块|起算证据):\s*(\S+)", section, re.MULTILINE
    )
    if match:
        anchor = match.group(1).strip()
    else:
        errors.append("锚行缺失或不可读（须含 起算块/起算证据）")
    rows: list[dict[str, str]] = []
    for line in section.splitlines():
        if not line.lstrip().startswith("| GT-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            errors.append(f"行列数异常（{len(cells)} ≠ 7）：{line.strip()[:60]}")
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
    """
    rows: list[tuple[str, str, str]] = []
    for line in progress_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 6 or not re.fullmatch(r"[A-Za-z0-9]+-B\d+-P\d+-N\d+", cells[0]):
            continue
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
            findings.append(("GATE-LEDGER-000", f"{carrier} 门台账损坏（fail-closed）：{issue}"))
        return findings
    rows = list(ledger.get("rows") or [])

    numbers: list[int] = []
    for row in rows:
        gid = re.fullmatch(r"GT-(\d+)", row["gid"])
        if not gid:
            findings.append(("GATE-LEDGER-004", f"{carrier} 行ID 非法：{row['gid']}"))
            continue
        numbers.append(int(gid.group(1)))
    if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
        findings.append(("GATE-LEDGER-004", f"{carrier} 行ID 未单调递增或重复"))

    for row in rows:
        if row["authorization"].strip("*` ") in GATE_LEDGER_PLACEHOLDERS:
            findings.append((
                "GATE-LEDGER-003",
                f"{carrier} {row['gid']}（{row['block']}）授权原文为空或占位：须学生逐字引语",
            ))

    if checkpoints is None:
        findings.append(("GATE-LEDGER-000", f"{carrier} 起算块在 progress checkpoint 表中不存在"))
        return findings

    confirmed = [(cid, page) for cid, page, status in checkpoints if status == "confirmed"]
    transitions = {(r["block"], r["consumed"]) for r in rows if r["gate"] == "块过渡"}
    pageturns = {r["consumed"] for r in rows if r["gate"] == "翻页"}
    for (a_id, a_page), (b_id, b_page) in zip(confirmed, confirmed[1:]):
        if (a_id, b_id) not in transitions:
            findings.append((
                "GATE-LEDGER-001",
                f"{carrier} 相邻 confirmed 块 {a_id} → {b_id} 缺块过渡行",
            ))
        if a_page != b_page and b_id not in pageturns:
            findings.append((
                "GATE-LEDGER-002",
                f"{carrier} 页码 {a_page}→{b_page} 变化处（{b_id}）缺翻页行",
            ))

    closure_text = " ".join(
        f"{r['consumed']} {r['closure']}" for r in rows if r["gate"] == "题目闭环"
    )
    for rv in rv_ids:
        if rv not in closure_text:
            findings.append(("GATE-LEDGER-005", f"{carrier} 新评审 {rv} 缺题目闭环行"))
    hint_text = " ".join(
        f"{r['consumed']} {r['closure']}" for r in rows if r["gate"].startswith("提示授权")
    )
    for attempt_id, level in attempt_hints:
        if level in GATE_LEDGER_HINT_LEVELS and attempt_id not in hint_text:
            findings.append((
                "GATE-LEDGER-006",
                f"{carrier} {attempt_id} 记录了 {level} 级提示但缺提示授权行",
            ))
    return findings


def check_gate_ledger(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    """GATE-LEDGER-000..006: teaching-gate ledger completeness (WARN, §2.4).

    Scans every Lesson/Exercise carrier that HAS a 门台账 section; carriers
    without one are skipped (deployment transition — sections arrive with the
    ledger_since anchor, history before the anchor is exempt by design).
    Read-only and WARN-only: an incomplete ledger is a record-keeping breach,
    not a state error, and must not block a lesson mid-session.
    """
    for course_id, (folder, _meta) in courses.items():
        progress_text = ""
        progress_path = folder / "progress.md"
        if progress_path.is_file():
            try:
                progress_text = read(progress_path)
            except OSError:
                progress_text = ""
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
                f"CKP-SCOPE-002: 当前 checkpoint 缺 block_id："
                f"{course_id}/{lesson} {ckpt_id}",
            )
            continue

        # block_id format: page_key#BNN
        if "#" not in ckpt_block:
            report(
                "FAIL",
                f"CKP-SCOPE-002: block_id 格式无效（缺 #）："
                f"{course_id}/{lesson} {ckpt_id} -> {ckpt_block}",
            )
            continue

        page_key = ckpt_block.split("#")[0]
        map_path = folder / "lessons" / lesson / "lesson_map.md"
        if not map_path.is_file():
            report(
                "FAIL",
                f"CKP-SCOPE-002: LessonMap 缺失，无法验证 block routing："
                f"{course_id}/{lesson}",
            )
            continue

        try:
            map_text = read(map_path)
        except OSError:
            report(
                "FAIL",
                f"CKP-SCOPE-002: LessonMap 不可读：{course_id}/{lesson}",
            )
            continue

        if page_key not in map_text:
            report(
                "FAIL",
                f"CKP-SCOPE-002: 当前 checkpoint block_id 的 page_key 不在 "
                f"LessonMap 中：{course_id}/{lesson} {ckpt_id} -> {page_key}",
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
                f"CKP-SCOPE-002: 当前 checkpoint 的 page_key 在 LessonMap 中 "
                f"标记为 outside_active_lesson_boundary："
                f"{course_id}/{lesson} {ckpt_id} -> {page_key}",
            )

        # CKP-SCOPE-001 (WARN): multi-session comparison not available
        report(
            "WARN",
            f"CKP-SCOPE-001: confirmed checkpoint 跨 Scope 不变性校验需多 session "
            f"snapshot 对比（当前仅单 session 运行，无法执行）：{course_id}",
        )

        # CKP-SCOPE-003 (WARN): block successor model not formalised
        report(
            "WARN",
            f"CKP-SCOPE-003: LessonMap 块 successor 精确映射需正式块模型 + "
            f"block migration 表（当前仅有非正式块清单）：{course_id}/{lesson}",
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
            report("FAIL", f"Trading-OS 权威指针缺失（应指向引用合同）：{pointer}")
    if "C:/Users" in content or "C:\\Users" in content:
        report("FAIL", "Engagement 正文出现宿主绝对路径；仓外路径只许存在于 external_refs.json")
    if "交易行为唯一真相源" in content or "纪律唯一真相源" in content:
        report("FAIL", "T2AG Engagement 越权自称 Trading-OS 真相源")


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
    return "、".join(names) if names else "(本环境无 /sessions 挂载面，或为原生宿主)"


def check_external_references() -> None:
    """T1 引用合同（cross_repo_reference.md）：断链=FAIL，pinned 漂移=WARN。"""
    sidecars = sorted(MAIN.rglob("external_refs.json"))
    for sidecar in sidecars:
        try:
            payload = json.loads(read(sidecar))
        except json.JSONDecodeError as error:
            report("FAIL", f"外部引用 sidecar 无法解析：{rel(sidecar)}（{error}）")
            continue
        if not isinstance(payload, dict) or payload.get("schema") != EXTERNAL_REFERENCE_SCHEMA:
            report("FAIL", f"外部引用 sidecar schema 不符：{rel(sidecar)}")
            continue
        hints = payload.get("peer_root_hints")
        references = payload.get("references")
        if not isinstance(hints, dict) or not hints or not isinstance(references, list) or not references:
            report("FAIL", f"外部引用 sidecar 缺 peer_root_hints 或 references：{rel(sidecar)}")
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
                report("FAIL", f"外部引用条目不是对象：{rel(sidecar)}")
                continue
            label = f"{rel(sidecar)}#{reference.get('reference_id', '<missing>')}"
            peer_system = reference.get("peer_system")
            relative = reference.get("peer_relative_path")
            kind = reference.get("kind")
            integrity = reference.get("integrity_mode")
            if not isinstance(peer_system, str) or not isinstance(relative, str) or not relative:
                report("FAIL", f"外部引用缺 peer_system/peer_relative_path：{label}")
                continue
            if "\\" in relative or ":" in relative or relative.startswith("/") or ".." in relative.split("/"):
                report("FAIL", f"外部引用相对路径违反词法（盘符/反斜杠/../绝对路径）：{label}")
                continue
            if kind not in EXTERNAL_REFERENCE_KINDS:
                report("FAIL", f"外部引用 kind 非法：{label}")
                continue
            if kind == "frozen_version" and (
                integrity != "pinned"
                or not reference.get("content_sha256")
                or not reference.get("peer_version")
            ):
                report("FAIL", f"frozen_version 必须 pinned + content_sha256 + peer_version：{label}")
                continue
            if kind == "living_data" and (
                integrity != "existence_only" or reference.get("usage_rule") != "copy_on_use"
            ):
                report("FAIL", f"living_data 必须 existence_only + copy_on_use：{label}")
                continue
            if peer_system not in roots:
                report("FAIL", f"外部引用 peer_system 无对应 root hint：{label}")
                continue
            root = roots[peer_system]
            if root is None:
                # State the fact, not a conclusion: from here "moved", "deleted" and
                # "not mounted" are the same observation.  Severity stays FAIL — a
                # peer repo that is gone entirely also lands in this branch, and
                # demoting it would turn total peer loss into an ignorable WARN.
                report(
                    "FAIL",
                    f"外部引用 root 无法解析：{label}"
                    f"；提示路径 {hint_by_system.get(peer_system, '(缺 windows_host)')} 在本环境不存在"
                    f"；当前挂载：{describe_mount_surface()}"
                    "；→ 先确认对端是否已挂载（声明已连接 ≠ 已实际挂载，挂载可能是惰性的，见 EA-0005）"
                    "；挂上仍不可达才判搬家或消失"
                    "；无论哪种都不得删除引用身份（cross_repo_reference.md §四）",
                )
                continue
            target = root / relative
            if not target.is_file():
                report("FAIL", f"外部引用断链，目标不存在：{label} → {relative}")
                continue
            if integrity == "pinned":
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                pinned = str(reference.get("content_sha256"))
                if digest != pinned:
                    report(
                        "WARN",
                        f"外部引用漂移：{label} 绑定 {pinned[:12]}… 实际 {digest[:12]}…；"
                        "对端可能已改版，需人工显式重绑（cross_repo_reference.md §四）",
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
            report("FAIL", f"active 旧路径残留：{rel(path)} -> {found[:3]}")
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
                    f"active 退役实例 ID：{rel(path)} -> {found}",
                )
    report("INFO", f"retired_instance_id_hits_total: {hits}")


def run_check(script: str, args: list[str], label: str) -> None:
    path = MAIN / "70_tools" / script
    if not path.exists():
        report("FAIL", f"缺工具：{script}")
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
        report("FAIL", f"{label} 失败：" + ("；".join(detail[-3:]) if detail else f"exit {proc.returncode}"))


def check_flow_and_guide() -> None:
    flow_path = MAIN / "50_playbook/t2ag_flow.md"
    guide = ROOT / "t2ag_directory_guide.html"
    if not flow_path.is_file() or not guide.is_file():
        report("FAIL", "流程源或离线指南缺失")
        return
    content = read(flow_path)
    opens = re.findall(r"^<!-- FLOW:([a-z0-9_]+) -->\s*$", content, re.MULTILINE)
    closes = re.findall(r"^<!-- /FLOW:([a-z0-9_]+) -->\s*$", content, re.MULTILINE)
    if len(opens) != len(set(opens)) or set(opens) != EXPECTED_FLOWS:
        report("FAIL", f"FLOW 集合不等于 0.2.0 九图：actual={sorted(opens)}")
    if opens != closes:
        report("FAIL", "FLOW 开闭标记未按顺序配对")
    blocks = re.findall(
        r"^<!-- FLOW:([a-z0-9_]+) -->\s*$(.*?)^<!-- /FLOW:\1 -->\s*$",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if len(blocks) != len(EXPECTED_FLOWS):
        report("FAIL", f"FLOW 可解析块数量错误：{len(blocks)}")
    mermaid_count = sum(1 for _, block in blocks if block.strip().startswith("```mermaid"))
    html_text = read(guide)
    forbidden = ("cdn.jsdelivr.net/npm/mermaid", "mermaid.initialize(", 'class="mermaid"')
    if any(token in html_text for token in forbidden):
        report("FAIL", "离线指南仍依赖 Mermaid 外部运行时")
    static_svg_count = html_text.count('<svg class="flow-svg"')
    if static_svg_count != mermaid_count:
        report(
            "FAIL",
            f"离线指南静态 SVG 数量漂移：expected={mermaid_count} actual={static_svg_count}",
        )
    if mermaid_count and html_text.count('<details class="flow-source"') != mermaid_count:
        report("FAIL", "离线指南 Mermaid 文本回退数量漂移")
    if mermaid_count and html_text.count('<details class="flow-diagram"') != mermaid_count:
        report("FAIL", "离线指南 Mermaid 流程图未按需折叠")
    for flow_id in EXPECTED_FLOWS:
        if f"FLOW:{flow_id}" not in content:
            report("FAIL", f"流程源缺 FLOW:{flow_id}")
    for anchor in ("preface", "directory_map", "flow_first_run", "flow_panorama", "flow_catalog"):
        if html_text.count(f"T2AG_GENERATED:{anchor}") != 2:
            report("FAIL", f"离线指南生成锚点不闭合：{anchor}")
    responsive_inline = 'style="width:100%;height:auto;display:block"' in html_text
    responsive_css = bool(
        re.search(
            r"\.flow-svg\s*\{[^}]*max-width\s*:\s*100%[^}]*height\s*:\s*auto",
            html_text,
            re.DOTALL,
        )
    )
    if '<svg class="flow-svg"' in html_text and not (responsive_inline or responsive_css):
        report("FAIL", "离线指南静态 SVG 缺响应式尺寸")
    capped_viewport = bool(
        re.search(
            r"\.flow-viewport\s*\{[^}]*max-height\s*:[^;}]+;[^}]*overflow\s*:\s*auto",
            html_text,
            re.DOTALL,
        )
    )
    if mermaid_count and not capped_viewport:
        report("FAIL", "离线指南流程图缺受控滚动视窗")


RECOMPUTE_SOURCE_MARKER = "←"
VERIFIABLE_ASSERTION_PATTERNS = (
    re.compile(r"\d+\s*个"),
    re.compile(r"零命中"),
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
    required_headings = (
        "Active Handoffs",
        "下一版本 Backlog",
        "Workorders / Plans",
        "Evidence / Reviews",
        "Resolved / Archive Handoffs",
    )
    for heading in required_headings:
        if not re.search(rf"^##\s+{re.escape(heading)}\s*$", index_content, re.MULTILINE):
            report("FAIL", f"handoff 索引缺分类区：{heading}")
    rows = table_after_heading(index_content, "Active Handoffs")
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
        filename = row.get("文件", "").strip("` ")
        key = (row.get("scope", ""), row.get("applies_to", ""))
        if (
            not handoff_id
            or not filename
            or not all(key)
            or row.get("lane") not in allowed_lanes
            or row.get("artifact_role") != "handoff"
            or row.get("status") != "active"
        ):
            report("FAIL", f"active handoff 索引缺必填单元格：{handoff_id or filename or '?'}")
            continue
        if row["scope"] not in allowed_scopes:
            report("FAIL", f"active handoff scope 非法：{handoff_id} -> {row['scope']}")
        if handoff_id in seen_ids or filename in seen_files or key in seen_scopes:
            report("FAIL", f"active handoff 索引存在重复：{handoff_id}")
        seen_ids.add(handoff_id)
        seen_files.add(filename)
        seen_scopes.add(key)
        path = handoff_root / filename
        if not path.is_file():
            report("FAIL", f"active handoff 文件悬空：{filename}")
            continue
        content = read(path)
        metadata = {
            field: match.group(1).strip()
            for field in required
            if (match := re.search(rf"^>\s*\*\*{re.escape(field)}\*\*[：:]\s*(.*?)\s*$", content, re.MULTILINE))
        }
        missing = sorted(required - set(metadata))
        if missing:
            report("FAIL", f"active handoff 缺元数据 {missing}：{filename}")
            continue
        if metadata["status"] != "active":
            report("FAIL", f"active 索引指向非 active 文档：{filename}")
        if metadata["artifact_role"] != "handoff":
            report("FAIL", f"active 索引指向非 handoff 角色：{filename}")
        if metadata["lane"] not in allowed_lanes:
            report("FAIL", f"active handoff lane 非法：{filename} -> {metadata['lane']}")
        for field in (
            "handoff_id", "scope", "lane", "artifact_role", "status", "applies_to", "updated_at"
        ):
            index_field = row.get(field, "")
            if index_field and metadata[field] != index_field:
                report("FAIL", f"handoff 索引与文档 {field} 不一致：{filename}")
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
                f"handoff aging_state 漂移：{filename} expected={expected_aging} actual={metadata['aging_state']}",
            )
        for line_number, text in unsourced_handoff_assertions(content):
            excerpt = text if len(text) <= 80 else f"{text[:80]}…"
            report(
                "WARN",
                f"交接断言无复算来源（handoff_management.md §5.6）：{filename}:{line_number} -> {excerpt}",
            )

    backlog_rows = table_after_heading(index_content, "下一版本 Backlog")
    for row in backlog_rows:
        item_id = row.get("id", "")
        filename = row.get("文件", "").strip("` ")
        role = row.get("artifact_role", "")
        if (
            not item_id
            or not filename
            or row.get("lane") != "version_campaign"
            or "release_backlog" not in {part.strip() for part in role.split("+")}
            or row.get("status") != "pending_next_candidate"
        ):
            report("FAIL", f"下一版本 backlog 分类非法：{item_id or filename or '?'}")
            continue
        if filename in seen_files:
            report("FAIL", f"release backlog 被同时登记为 active handoff：{filename}")
        if not (handoff_root / filename).is_file():
            report("FAIL", f"release backlog 文件悬空：{filename}")

    closed_rows = table_after_heading(index_content, "Resolved / Archive Handoffs")
    for row in closed_rows:
        handoff_id = row.get("handoff_id", "")
        filename = row.get("文件", "").strip("` ")
        if (
            not handoff_id
            or not filename
            or row.get("artifact_role") != "handoff"
            or row.get("status") == "active"
            or row.get("lane") not in allowed_lanes
        ):
            report("FAIL", f"历史 handoff 分类非法：{handoff_id or filename or '?'}")
            continue
        if handoff_id in seen_ids or filename in seen_files:
            report("FAIL", f"handoff 同时进入 active 与历史索引：{handoff_id}")
        if not (handoff_root / filename).is_file():
            report("FAIL", f"历史 handoff 文件悬空：{filename}")


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
        report("FAIL", f"Cloud 协议部件缺失：{missing}")
        return
    state_text = read(state)
    required = (
        "protocol_version: T2AG-CLOUD-1", "privacy_model: two_scope",
        "automatic_sync_allowlist_status: approved_minimal_low_risk",
        "current_cloud_project_mode:", "cloud_bridge_status: paused",
        "current_base_state_id:", "## 已处理会话", "## 部件变更指令", "## 云端交接",
    )
    absent = [token for token in required if token not in state_text]
    if absent:
        report("FAIL", f"Cloud 暂停状态缺契约字段：{absent}")
    prompt = read(cloud / "T2AG_PROJECT_INSTRUCTIONS.txt")
    playbook = read(MAIN / "50_playbook/cloud_learning_sync.md")
    for token in ("T2AG-CLOUD-1", "T2AG_SESSION_CLOSE", "T2AG_CLOUD_CHANGE_DIRECTIVE", "T2AG_CLOUD_HANDOFF"):
        if token not in playbook:
            report("FAIL", f"Cloud 协议缺共享标识：{token}")
        if FLAVOR != "skeleton" and token not in prompt:
            report("FAIL", f"Cloud 个人实例提示词缺共享标识：{token}")
    if FLAVOR == "skeleton":
        for token in ("cloud_project_mode: generic_skeleton", "不得生成教学 receipt", "paused"):
            if token not in prompt:
                report("FAIL", f"Cloud Skeleton 提示词缺隔离边界：{token}")
    if FLAVOR == "main":
        for token in ("new_cloud_sessions_allowed: false", "new_component_directives_allowed: false"):
            if token not in state_text:
                report("FAIL", f"Cloud pause 门缺字段：{token}")
        registered_cd = set(re.findall(r"\|\s*(CD-\d{8}-\d{4})\s*\|", state_text))
        registered_ch = set(re.findall(r"\|\s*(CH-\d{8}-\d{4})\s*\|", state_text))
        outbox_ids = {path.stem for path in (cloud / "outbox").glob("CD-*.md")}
        inbox_ids = {path.stem for path in (cloud / "inbox").glob("CH-*.md")}
        if outbox_ids - registered_cd:
            report("FAIL", f"Cloud outbox 指令未登记：{sorted(outbox_ids - registered_cd)}")
        if inbox_ids - registered_ch:
            report("FAIL", f"Cloud inbox 交接未登记：{sorted(inbox_ids - registered_ch)}")


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
            report("FAIL", f"0.2.1 profile V2 证据字段非法：{where}")
            return False
        return True

    v1_manifest_path = MAIN / "60_journal/migration_021_profile_operations.json"
    v1_report_path = MAIN / "60_journal/migration_021_profile_report.json"
    manifest_path = MAIN / "60_journal/migration_021_profile_operations_v2.json"
    report_path = MAIN / "60_journal/migration_021_profile_report_v2.json"
    required_paths = (v1_manifest_path, v1_report_path, manifest_path, report_path)
    if any(not path.is_file() for path in required_paths):
        report("FAIL", "缺少 0.2.1 profile V1/V2 迁移操作清单或报告")
        return
    try:
        v1_manifest = strict_json(v1_manifest_path)
        v1_report = strict_json(v1_report_path)
        manifest = strict_json(manifest_path)
        migration_report = strict_json(report_path)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        report("FAIL", f"0.2.1 profile 迁移证据严格 JSON 非法：{exc}")
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
        report("FAIL", "0.2.1 profile V2 baseline/target/schema 绑定非法")
    try:
        resolved_tree = subprocess.run(
            ["git", "show", "-s", "--format=%T", expected_commit],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        report("FAIL", f"0.2.1 profile baseline 无法现场解析：{exc}")
        return
    if resolved_tree != expected_tree:
        report("FAIL", "0.2.1 profile baseline tree 与 Git 现场解析不一致")
    if (
        summary.get("path") != "main/60_journal/migration_021_profile_operations_v2.json"
        or summary.get("sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        or summary.get("operation_count") != 4
    ):
        report("FAIL", "0.2.1 profile V2 report 未绑定 canonical manifest")
    operations = manifest.get("operations")
    if not isinstance(operations, list) or manifest.get("operation_count") != 4 or len(operations) != 4:
        report("FAIL", "0.2.1 profile V2 迁移计数非法")
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
        report("FAIL", "被 supersede 的 0.2.1 profile V1 证据缺失或已改写")

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
            report("FAIL", f"0.2.1 profile independent oracle 失败：{exc}")
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
            report("FAIL", f"0.2.1 profile V2 迁移操作与独立 oracle 不一致：sequence={sequence}")
            continue
        if sequence <= len(v1_operations):
            v1_source = v1_operations[sequence - 1].get("sources", [{}])[0]
            if (
                v1_source.get("path") != source_path
                or v1_source.get("bytes") != len(source_content)
                or v1_source.get("sha256") != hashlib.sha256(source_content).hexdigest()
            ):
                report("FAIL", f"0.2.1 profile V1/V2 source 绑定分叉：sequence={sequence}")
        target = ROOT / target_path
        if not target.is_file():
            report("FAIL", f"0.2.1 profile 迁移目标不存在：{target_path}")
            continue
        if (ROOT / source_path).exists():
            report("FAIL", f"0.2.1 profile 旧路径仍存在：{source_path}")
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
            report("FAIL", "Skeleton 不得复制 Main ActivityRecord 真实迁移证据")
        if (ROOT / source_path).exists() or (ROOT / target_path).exists():
            report("FAIL", "Skeleton 不得包含 AR-0001 真实实例")
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
        report("FAIL", "缺少 0.2.1 ActivityRecord 迁移证据")
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
        report("FAIL", f"0.2.1 ActivityRecord 迁移严格 JSON 非法：{exc}")
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
        report("FAIL", "0.2.1 ActivityRecord manifest 字段非法")
        return
    if not isinstance(activity_report, dict) or set(activity_report) != report_keys:
        report("FAIL", "0.2.1 ActivityRecord report 字段非法")
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
        report("FAIL", "0.2.1 ActivityRecord baseline/target/schema 绑定非法")
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
        report("FAIL", f"0.2.1 ActivityRecord baseline 无法现场解析：{exc}")
        return
    marker = b"type: activity_record\n"
    old_path = source_path.encode("utf-8")
    if source.count(marker) != 1 or source.count(old_path) != 1:
        report("FAIL", "0.2.1 ActivityRecord baseline 不满足独立 transform oracle")
        return
    expected_post = source.replace(marker, marker + b"activity_kind: reading\n", 1).replace(
        old_path,
        target_path.encode("utf-8"),
        1,
    )
    operations = manifest.get("operations")
    if not isinstance(operations, list) or len(operations) != 1 or manifest.get("operation_count") != 1:
        report("FAIL", "0.2.1 ActivityRecord 迁移操作数非法")
        return
    row = operations[0]
    expected_row_keys = {
        "sequence", "transform_id", "source", "target", "replacement_counts",
        "outcome", "post_target",
    }
    if not isinstance(row, dict) or set(row) != expected_row_keys:
        report("FAIL", "0.2.1 ActivityRecord 操作字段非法")
        return
    source_evidence = row.get("source")
    target_evidence = row.get("post_target")
    if not isinstance(source_evidence, dict) or set(source_evidence) != {"path", "blob", "bytes", "sha256"}:
        report("FAIL", "0.2.1 ActivityRecord source 证据字段非法")
        return
    if not isinstance(target_evidence, dict) or set(target_evidence) != {"path", "bytes", "sha256"}:
        report("FAIL", "0.2.1 ActivityRecord target 证据字段非法")
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
        report("FAIL", "0.2.1 ActivityRecord 证据与独立 oracle 不一致")
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
        report("FAIL", "0.2.1 ActivityRecord report 未绑定 manifest/live 结构")
    if (ROOT / source_path).exists() or not (ROOT / target_path).is_file():
        report("FAIL", "0.2.1 ActivityRecord canonical/legacy 路径状态非法")


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
        report("FAIL", f"reading bridge V1 合同文件集合非法：missing={sorted(expected - present)} extra={sorted(present - expected)}")
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
                report("FAIL", f"reading bridge schema/validator 非法：{rel(schema_path)} -> {exc}")
        except OSError as exc:
            report("FAIL", f"reading bridge schema 无法读取：{rel(schema_path)} -> {exc}")
    tool = MAIN / "70_tools/t2ag_reading_bridge.py"
    test = MAIN / "70_tools/test_021_closeout.py"
    saga_test = MAIN / "70_tools/scenarios/release_reading_bridge_saga.py"
    migration = MAIN / "70_tools/migrate_021_activity_records.py"
    if not tool.is_file() or not test.is_file() or not saga_test.is_file() or not migration.is_file():
        report("FAIL", "reading bridge 工具/测试/saga/ActivityRecord migrator 不完整")
    elif "subprocess" in read(tool) or "辅助阅读系统" in read(tool):
        report("FAIL", "T2AG reading bridge 工具不得 spawn 或绑定辅助阅读系统")
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
            report("FAIL", f"reading bridge 发行能力不完整：{release_name} -> {missing}")
        else:
            manifests[release_name] = tuple(values)
    if len(manifests) == len(distribution_release_names()) and len(set(manifests.values())) != 1:
        report("FAIL", "reading bridge schema/validator/tool/test 在三发行分叉")


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
            if CORE_PLAYBOOK_MARKER in read(path):
                manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifests[name] = manifest
    reference = manifests["t2ag-skeleton"]
    for name, manifest in manifests.items():
        if set(manifest) != set(reference):
            report(
                "FAIL",
                f"core-playbook 文件集合分叉：{name}",
            )
            continue
        drift = [file for file in reference if manifest[file] != reference[file]]
        if drift:
            report("FAIL", f"core-playbook SHA 分叉：{name} -> {drift}")


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
        report("FAIL", f"学习上下文包能力缺失：{missing}")
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
    absent = [marker for marker in tool_markers if marker not in tool_content]
    if absent:
        report("FAIL", f"学习上下文包工具缺只读/成本合同：{absent}")

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
        if marker not in activity_content
    ]
    if absent:
        report("FAIL", f"活动路由器缺共享快照注入合同：{absent}")

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
    absent = [marker for marker in test_markers if marker not in test_content]
    if absent:
        report("FAIL", f"学习上下文包负例测试缺失：{absent}")

    workflow_markers = {
        MAIN / "t2ag.md": (
            # EV-0020 Batch A：接管细则 sink 至 context_packet.md，宪法持指针锚
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
        missing_markers = [marker for marker in markers if marker not in content]
        if missing_markers:
            report(
                "FAIL",
                f"学习上下文包未接入 {rel(path)}：{missing_markers}",
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
            report("FAIL", f"发行版缺学习上下文包/活动工具或测试：{name}")
            continue
        manifests[name] = (
            hashlib.sha256(release_tool.read_bytes()).hexdigest(),
            hashlib.sha256(release_activity.read_bytes()).hexdigest(),
            hashlib.sha256(release_test.read_bytes()).hexdigest(),
        )
    if len(manifests) == len(distribution_release_names()) and len(set(manifests.values())) != 1:
        report("FAIL", "学习上下文包/活动工具或测试在三发行分叉")


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
        report("FAIL", f"测试管理能力缺失：{missing}")
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
        report("FAIL", f"已退役测试入口仍存在：{survivors}")

    manifest_path = ROOT / "main/70_tools/test_dependencies.json"
    try:
        manifest = load_json_strict(manifest_path)
    except (OSError, ContractError) as exc:
        report("FAIL", f"测试依赖清单无法解析：{exc}")
        return
    if not isinstance(manifest, dict) or manifest.get("schema") != "t2ag.test_dependencies.v2":
        report("FAIL", "测试依赖清单 schema 非法")
        return
    if manifest.get("tiers") != ["fast", "deep", "release_only"]:
        report("FAIL", "测试档位必须固定为 fast/deep/release_only")
    tests = manifest.get("tests")
    components = manifest.get("components")
    if not isinstance(tests, dict) or not isinstance(components, dict):
        report("FAIL", "测试依赖清单缺 tests/components")
        return
    required_components = {
        "distribution_foundation", "doctor", "context", "activity_close", "transaction",
        "release_candidate_contracts", "release_receipts", "release_evidence",
        "release_gates", "release_faults", "release_shadow", "release_suite",
    }
    if not required_components.issubset(components):
        report("FAIL", f"测试依赖清单缺组件：{sorted(required_components - set(components))}")
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
            "普通测试文件与依赖清单分叉："
            f"missing={sorted(discovered - registered_discovery)} "
            f"stale={sorted(registered_discovery - discovered)}",
        )
    scenario = tests.get("reading.release_saga")
    if (
        not isinstance(scenario, dict)
        or scenario.get("kind") != "scenario"
        or scenario.get("automatic") is not False
    ):
        report("FAIL", "完整物理根 reading saga 未标记为显式 release scenario")
    shadow_scenario = tests.get("release.shadow_apply_scenario")
    if (
        not isinstance(shadow_scenario, dict)
        or shadow_scenario.get("kind") != "scenario"
        or shadow_scenario.get("automatic") is not False
    ):
        report("FAIL", "shadow apply 未移出普通测试发现范围")
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
        report("FAIL", f"发布证据测试未隔离到 release_only：{invalid_release}")
    release_suite = components.get("release_suite")
    if (
        not isinstance(release_suite, dict)
        or release_suite.get("aggregate") is not True
        or release_suite.get("plan_only") is not True
        or release_suite.get("sources") != []
        or set(release_suite.get("tests", [])) != set(release_ids)
    ):
        report("FAIL", "release_suite 必须是无 changed-path 映射的显式聚合组件")

    workflow_path = ROOT / "main/70_tools/validation_workflow.json"
    try:
        workflow = validation_control.load_workflow(workflow_path)
    except validation_control.ValidationControlError as exc:
        report("FAIL", f"标准检测流程控制文件非法：{exc}")
        workflow = None
    if workflow is not None:
        handlers = {
            spec["handler"]
            for spec in workflow["doctor_checks"].values()
        }
        if handlers != SUPPORTED_DOCTOR_HANDLERS:
            report(
                "FAIL",
                "Doctor 控制文件与执行器原子 handler 分叉："
                f"missing={sorted(SUPPORTED_DOCTOR_HANDLERS - handlers)} "
                f"unknown={sorted(handlers - SUPPORTED_DOCTOR_HANDLERS)}",
            )
        flow_content = read(ROOT / "main/50_playbook/validation_flow.md")
        for marker in ("flowchart TD", "runtime（默认、启动安全）", "不得越级", "plan SHA"):
            if marker not in flow_content:
                report("FAIL", f"标准检测流程树缺标记：{marker}")

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
    absent = [marker for marker in runner_markers if marker not in runner_content]
    if absent:
        report("FAIL", f"测试选择器缺内存计划/清单约束：{absent}")
    close_content = read(ROOT / "main/70_tools/test_022_close_roundtrip.py")
    close_markers = (
        "test_preference_sources_and_first_prompt_are_durable",
        "test_pending_plan_body_has_full_tree_and_exposes_missing",
        "test_five_knowledge_states_scope_confirmation_and_v2_body",
        "test_learner_retrospective_is_complete_dialogue_payload",
        "test_bound_close_intent_uses_shown_tuple_without_copying",
        "test_blockers_suggest_closed_incomplete",
    )
    absent = [marker for marker in close_markers if marker not in close_content]
    if absent:
        report("FAIL", f"close runtime 独有断言未并入 roundtrip：{absent}")
    migrator_content = read(ROOT / "main/70_tools/migrate_022_activity_close.py")
    if '.glob("test_022_*.py")' in migrator_content:
        report("FAIL", "0.2.2 迁移器仍以 glob 自动扩大测试边界")

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
            report("FAIL", f"发行版缺测试管理文件：{name} -> {missing_release}")
            continue
        manifests[name] = tuple(
            hashlib.sha256((release_root / relative).read_bytes()).hexdigest()
            for relative in required
        )
    if len(manifests) == len(distribution_release_names()) and len(set(manifests.values())) != 1:
        report("FAIL", "测试管理规则、清单或入口在三发行分叉")


def check_candidate_replay_contract() -> None:
    tool_relative = "main/70_tools/t2ag_candidate_replay.py"
    test_relative = "main/70_tools/test_release_contracts.py"
    tool = ROOT / tool_relative
    test = ROOT / test_relative
    workflow = MAIN / "50_playbook/git_workflow.md"
    if not tool.is_file() or not test.is_file():
        report("FAIL", "发布候选隔离工具或负例测试缺失")
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
    missing = [marker for marker in markers if marker not in tool_content]
    if missing:
        report("FAIL", f"发布候选隔离工具缺强制合同：{missing}")
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
        marker for marker in workflow_markers if marker not in workflow_content
    ]
    if missing_workflow:
        report("FAIL", f"发布候选流程未绑定机械隔离工具：{missing_workflow}")

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
            report("FAIL", f"发行版缺候选隔离工具/测试：{name}")
            continue
        manifests[name] = (
            hashlib.sha256(release_tool.read_bytes()).hexdigest(),
            hashlib.sha256(release_test.read_bytes()).hexdigest(),
        )
    if len(manifests) == len(distribution_release_names()) and len(set(manifests.values())) != 1:
        report("FAIL", "发布候选隔离工具或负例测试在三发行分叉")


def check_course_activity_templates(*, check_release_parity: bool = True) -> None:
    required = {
        "README.md", "course.md.template", "progress.md.template",
        "activity_map.md.template", "activity_ledger.md.template",
        "lessons/lessonNN/lessonNN.md.template",
        "exercises/exerciseNN/exercise.md.template",
        "exercises/exerciseNN/problems.md.template",
        "book/primary/verified_excerpts/source.md.template",
        "exercises/exerciseNN/attempts/ATdddd/attempt.md.template",
        "exercises/exerciseNN/reviews/RVdddd.md.template",
    }
    template_root = MAIN / "40_course/_templates/course"
    missing = sorted(path for path in required if not (template_root / path).is_file())
    if missing:
        report("FAIL", f"Course/Lesson/Exercise 系统模板缺失：{missing}")
    core_contract = MAIN / "00_core/learning_activity_model.md"
    if not core_contract.is_file():
        report("FAIL", "缺课程学习活动 Core 契约：main/00_core/learning_activity_model.md")
    core_content = read(core_contract) if core_contract.is_file() else ""
    map_first_markers = (
        "### 2.2 多块长篇讲解的地图优先协议",
        "一次只深入一个分支",
        "无法在不泄露的前提下制作有用总览时，宁可省略总览",
    )
    missing_map_first = [
        marker for marker in map_first_markers if marker not in core_content
    ]
    if missing_map_first:
        report(
            "FAIL",
            f"课程学习活动 Core 缺地图优先讲解协议：{missing_map_first}",
        )
    first_run = MAIN / "50_playbook/first_run.md"
    first_run_content = read(first_run) if first_run.is_file() else ""
    if (
        "先地图、后逐支" not in first_run_content
        or "学生希望怎样确认后再继续" not in first_run_content
    ):
        report("FAIL", "首次启动未采集长篇讲解地图与分支确认偏好")
    route_tool = MAIN / "70_tools/t2ag_activity.py"
    if not route_tool.is_file():
        report("FAIL", "缺统一 LearningActivity 路由器：main/70_tools/t2ag_activity.py")
    hint_gate_tool = MAIN / "70_tools/t2ag_hint_gate.py"
    if not hint_gate_tool.is_file():
        report("FAIL", "缺学生可选提示闸门：main/70_tools/t2ag_hint_gate.py")
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
    marker_positions = [recovery_content.find(marker) for marker in recovery_markers]
    if (
        any(position < 0 for position in marker_positions)
        or not marker_positions[0] < marker_positions[1] < marker_positions[2]
    ):
        report("FAIL", "课程恢复流程未先按 current_activity 分支")
    close = MAIN / "50_playbook/session_close.md"
    close_content = read(close) if close.is_file() else ""
    close_markers = (
        "t2ag_activity.py --course <COURSE_ID> --intent close",
        "Micro close 和完整结课都必须原子完成",
        "Exercise 结课不得顺手",
    )
    if any(marker not in close_content for marker in close_markers):
        report("FAIL", "结课流程未共享统一活动路由与原子写回")
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
                f"Course/Lesson/Exercise 发行能力不完整：{name} -> {'; '.join(details)}",
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
            report("FAIL", f"Course/Lesson/Exercise Core 模板或契约分叉：{name}")


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
        report("FAIL", "Git 跟踪了环境目录或 .env：" + proc.stdout.strip().replace("\n", ", "))


def check_decision_records() -> None:
    """Deterministic Evolution Register ↔ ADR linkage (no value judgment)."""
    import decision_record_contract as drc  # local tools path already on sys.path

    for level, message in drc.validate_decision_records_as_report(ROOT):
        report(level, message)


def check_cloud_pause() -> None:
    state = ROOT / "cloud/cloud_sync_state.md"
    if state.exists() and not re.search(
        r"^-\s*cloud_bridge_status:\s*paused\s*$", read(state), re.MULTILINE
    ):
        report("FAIL", "Cloud bridge 未保持 paused")


# Files exempt from Main<->Skeleton byte parity, with the reason in the value.
# The reason is mandatory: an exclusion list without reasons becomes a permanent
# blind spot, which is the failure this check exists to prevent (P-0065).
DISTRIBUTION_PARITY_EXEMPT = {
    "main/70_tools/legacy_r_registry.json":
        "Skeleton 版正文自述 entries empty by design；Main 版为主实例级兼容登记",
    "main/70_tools/artifact_registry.json":
        "Main 含真实 artifact 条目；强制同源等于把实例数据灌进 Skeleton",
}
DISTRIBUTION_PARITY_ROOTS = ("main/50_playbook", "main/70_tools")
DISTRIBUTION_PARITY_SUFFIXES = (".md", ".py", ".json")


def check_distribution_parity() -> None:
    """Release profile: `50_playbook/` and `70_tools/` must be byte-identical in Skeleton.

    That requirement has been stated in work orders since 0.2.2 but nothing enforced
    it, and twelve files had silently diverged by 2026-08-08 (P-0065).  A declared
    constraint with no checker is the `carrier_mismatch` pattern -- see
    `remediation_governance.md` §七.

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
        report("INFO", "distribution parity: 未挂载 t2ag-skeleton，跳过同源比对")
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
            if not other.is_file():
                missing.append(rel)
                continue
            identical = path.read_bytes() == other.read_bytes()
            if rel in DISTRIBUTION_PARITY_EXEMPT:
                if identical:
                    stale_exempt.append(rel)
                continue
            if not identical:
                drifted.append(rel)

    for rel in drifted:
        report("FAIL", f"Main↔Skeleton 同源漂移：{rel}")
    for rel in missing:
        report("FAIL", f"Main↔Skeleton 同源缺失（Skeleton 无此文件）：{rel}")
    for rel in stale_exempt:
        report(
            "WARN",
            f"同源豁免已失效（两侧已一致，应从 DISTRIBUTION_PARITY_EXEMPT 移除）：{rel}",
        )
    if not (drifted or missing):
        report(
            "INFO",
            "distribution parity: "
            f"{len(DISTRIBUTION_PARITY_EXEMPT)} 项豁免，其余全部字节一致",
        )


def check_skeleton_textbook_gate() -> None:
    """Release profile: Skeleton 内 40_course/**/book/** 只允许模板骨架，不得含实际教材内容。"""
    if FLAVOR != "skeleton":
        return
    book_root = ROOT / "main/40_course"
    if not book_root.exists():
        return
    # 允许的目录：_templates/ 及其子内容
    allowed_prefix = str(book_root / "_templates")
    # 不允许的实质性内容模式
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
                # 目录存在且非空
                contents = list(check_path.iterdir())
                if contents:
                    report("FAIL", f"Skeleton 教材门：{rel(check_path)} 含实质教材内容")


def check_dirty_tree() -> None:
    if not (ROOT / ".git").exists():
        return
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True,
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if proc.stdout.strip():
        report("WARN", "工作树存在未快照改动；可继续施工，但不得宣称可发布")


def check_authorization_governance(*, include_external_handoffs: bool = True) -> None:
    """Fail closed when Agent, runtime, or active workorders can amplify RT3."""
    if activity_close_contract.PRODUCTION_DECISION_AUTHORITIES != frozenset(
        {("user", "direct_user")}
    ):
        report("FAIL", "RT3 授权契约漂移：terminal decision 非 user + direct_user")
    if activity_close_contract.PRODUCTION_APPLY_AUTHORIZATION_MODES != frozenset(
        {"direct_user"}
    ):
        report("FAIL", "RT3 授权契约漂移：生产 close apply 仍接受非 direct_user")
    if migration_022_contract.PRODUCTION_MIGRATION_APPLY_ENABLED is not False:
        report("FAIL", "RT3 授权契约漂移：已发布的 0.2.2 production migration apply 未退役")

    instruction_paths = [ROOT / "AGENTS.md", MAIN / "t2ag.md"]
    workspace_agents = ROOT.parent / "AGENTS.md"
    if workspace_agents.is_file():
        instruction_paths.append(workspace_agents)
    for path in instruction_paths:
        if not path.is_file():
            report("FAIL", f"授权治理入口缺失：{path}")
            continue
        content = read(path)
        if "授权不可放大与闭环止损" not in content:
            report("FAIL", f"授权治理入口缺不可放大规则：{path}")
        if "stopped_budget" not in content or "token" not in content:
            report("FAIL", f"授权治理入口缺闭环预算止损：{path}")

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
    }
    for path, markers in playbook_markers.items():
        content = read(path) if path.is_file() else ""
        if not all(marker in content for marker in markers):
            report("FAIL", f"授权/止损 playbook 契约缺失：{path}")

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
            report("FAIL", "当前 V4 工单仍可被解释为 continuous RT3 授权")
        if v2.is_file() and "authorization supersession notice" not in read(v2):
            report("FAIL", "V2 continuation notice 仍把 V4 指向当前授权入口")

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
                    "0.2.2 历史 CLR-0001 保留 invalid legacy delegation；"
                    "不得作为新授权模板，真实状态处置须另获 RT3",
                )
            else:
                report(
                    "INFO",
                    f"{close.get('close_id')} invalid legacy delegation 已由 "
                    f"{settled.get('event_id')} 直接用户补确认；原记录按 §1.7 永久保留，"
                    "仍不得作为新授权模板",
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
            "缺少 .gitattributes：行尾未钉死，证据哈希会随宿主漂移"
            "（见 50_playbook/git_workflow.md §11）",
        )
        return
    text = read(policy)
    if "eol=lf" not in text:
        report(
            "FAIL",
            ".gitattributes 未写 eol=lf：text=auto 只规范化 blob，"
            "工作树仍随宿主变，而被哈希的正是工作树",
        )


ENVIRONMENT_ASSUMPTIONS_REL = "main/50_playbook/environment_assumptions.md"
REQUIRED_ENVIRONMENT_ASSUMPTION_IDS = ("EA-0001", "EA-0002", "EA-0003")
CHANGELOG_REL = "main/00_core/t2ag_changelog.md"
CHANGELOG_ENTRY_HEADING = re.compile(
    r"^## \[(\d{4}-\d{2}-\d{2})\]\s*(.+?)\s*$",
    re.MULTILINE,
)
CHANGELOG_ANCHOR_HEADING = re.compile(
    r"^#{2,4}\s*锚定断言[^\n]*$",
    re.MULTILINE,
)
CHANGELOG_EVIDENCE_HEADING = re.compile(
    r"^#{2,4}\s*佐证断言[^\n]*$",
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


def parse_changelog_entries(text: str) -> list[dict[str, str]]:
    """Split changelog into dated entries.

    Convention: after the main title ``# T2AG 变更历史``, entries are newest-first.
    Entries that appear only above that title (legacy front-matter notes) are ignored
    when the title is present, so "latest" means the first body entry.
    """
    body = text
    title_at = text.find("# T2AG 变更历史")
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
    """Parse the latest entry's 锚定断言 block into normalized keys.

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
    """Return (claim_text, command) pairs from an explicit 佐证断言 section only.

    Anchoring lines also use ``←``; scanning the whole entry would false-stale
    them. No 佐证 section means no evidence claims (not an error by itself).
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
            # Only claims that sit under an explicit 佐证 heading, or any claim
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
    (`grep -c "^27\\. ..."`) as 已腐烂.  A gate that punishes precise patterns
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
        report("WARN", f"changelog 缺失：{CHANGELOG_REL}（无法核对锚定/佐证）")
        return
    text = read(path)
    entries = parse_changelog_entries(text)
    if not entries:
        report("WARN", f"changelog 无日期条目：{CHANGELOG_REL}")
        return
    latest = entries[0]
    latest_title = latest["heading"]
    declared = parse_changelog_anchors(text)
    measured = measure_runtime_changelog_anchors()
    if not declared:
        report(
            "WARN",
            f"changelog 最新条目缺锚定块：{latest_title}；"
            f"实测 plan_sha256={measured['plan_sha256']} checks={measured['checks']} "
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
                    f"状态漂移无记录：{latest_title} 缺锚定字段 {label}；"
                    f"声明值=(missing) 实测值={want}",
                )
            elif got != want:
                report(
                    "WARN",
                    f"状态漂移无记录：{latest_title} {label} "
                    f"声明值={got} 实测值={want}",
                )
    # Evidence: only the latest entry is required to stay non-rot for this gate;
    # older entries are historical and must not be rewritten (hard rule 4).
    def runner(command: str):
        return default_changelog_evidence_runner(command, root=ROOT)

    for title, claim_text, command in stale_changelog_claims([latest], runner):
        report(
            "WARN",
            f"条目已腐烂：{title}；断言原文={claim_text}；复算命令=`{command}` 命中为零",
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
        report("WARN", "t2ag_memory.md 无任何 [max N] 节预算标记：节预算机制未生效")
        return
    for title, cap, actual in budgets:
        if actual > cap:
            report(
                "WARN",
                f"memory 节超预算：「{title}」实测 {actual} 行 > 预算 {cap} 行；"
                f"按 t2ag_memory.md §节预算与下沉 下沉最旧条目并留墓碑",
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
        report("FAIL", "main/t2ag.md 缺失")
        return
    budgets = memory_section_budgets(read(path))
    if not budgets:
        report("FAIL", "t2ag.md 无任何 [max N] 节预算标记：宪法预算门未生效（EV-0020）")
        return
    for title, cap, actual in budgets:
        if actual > cap:
            report(
                "FAIL",
                f"宪法节超预算：「{title}」实测 {actual} 行 > 预算 {cap} 行；"
                f"按 t2ag.md §6.3 rule_migration 下沉，或经学生裁决调整该节 [max N]",
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
    installs, never cleans up, never rewrites a path (environment_assumptions.md §一).
    """
    findings: list[tuple[str, str]] = []
    if root.resolve() != production_root:
        findings.append((
            "INFO",
            f"EA-0001 生产根路径不匹配：当前 {root.resolve()}；"
            "期望值见 grep -n \"PRODUCTION_ROOT\" main/70_tools/activity_close.py"
            "（该常量是 Windows 字面量，在非 Windows 宿主上 resolve 后不可读，故不复制）。"
            "activity_close 的直接用户授权闸门在本环境不生效，"
            "且不得为通过 apply 而设置 T2AG_022_CLOSE_TEST=1",
        ))
    if not fitz_available:
        findings.append((
            "INFO",
            "EA-0002 PyMuPDF (fitz) 不可用：t2ag_source_pages.py 的 PPI 反算路径"
            "（source_pages prepare）在本环境失败，请在有 .venv 的宿主机执行；不得自动安装",
        ))
    if git_unlink is False:
        findings.append((
            "WARN",
            "EA-0003 本环境可在 .git 下建文件但不能 unlink："
            "本环境不得执行 git 写操作（commit/add/tag/gc），请在宿主机提交；"
            "已遗留的 HEAD.lock 等锁文件由用户手动删除，探测方不得代清理；"
            f"本探测自身的残留固定为 .git/{GIT_UNLINK_PROBE_NAME}（至多一个，可安全删除）",
        ))
    return findings


def check_environment_assumptions() -> None:
    """Runtime: read-only probes for the host assumptions registered as EA-XXXX.

    These assumptions used to travel by handoff prose only, which is why each of
    them bit a taker at least once.  The check proves the assumption is *visible*,
    not that the environment is correct — a wrong environment stays wrong and
    stays reported (see environment_assumptions.md §一).
    """
    registry = ROOT / ENVIRONMENT_ASSUMPTIONS_REL
    if not registry.is_file():
        report("FAIL", f"环境假设登记缺失：{ENVIRONMENT_ASSUMPTIONS_REL}")
        return
    registry_text = read(registry)
    missing = [
        ea_id for ea_id in REQUIRED_ENVIRONMENT_ASSUMPTION_IDS
        if ea_id not in registry_text
    ]
    if missing:
        report("FAIL", f"环境假设登记缺条目：{missing}")
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
        report("FAIL", f"CRLF 行尾：{path}（git_workflow.md §11.3：还原，不要提交）")
    if len(offenders) > 20:
        report("FAIL", f"另有 {len(offenders) - 20} 个 CRLF 文件未逐一列出")


def check_release_line_endings() -> None:
    """Release: exhaustive CRLF sweep over every tracked text file."""
    if not (ROOT / ".git").exists():
        report("WARN", "非 Git 仓库，跳过全量行尾核对")
        return
    proc = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, text=True,
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        report("WARN", "无法枚举 tracked 文件，跳过全量行尾核对")
        return
    targets = [ROOT / name for name in proc.stdout.split("\0") if name]
    offenders = crlf_offenders(targets)
    for path in offenders[:20]:
        report("FAIL", f"CRLF 行尾（tracked）：{path}")
    if len(offenders) > 20:
        report("FAIL", f"另有 {len(offenders) - 20} 个 tracked CRLF 文件未逐一列出")
    if not offenders:
        report("INFO", f"tracked 文本文件行尾一致：{len(targets)} 个已核对")


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
            f"Activity ledger 迁移不完整：{len(ledger_paths)}/{len(courses)}",
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
                f"Activity close 全局偏好契约缺失：{key}="
                f"{profile_meta.get(key)} expected={expected}",
            )
    for key in activity_ledger_contract.PREF_KEYS:
        if profile_meta.get(key) not in {"on", "off"}:
            report("FAIL", f"Activity close 全局偏好非法：{key}")
    prompt_status = profile_meta.get("activity_close_first_prompt_status")
    prompt_at = profile_meta.get("activity_close_first_prompt_at")
    if prompt_status not in {"pending", "shown"}:
        report("FAIL", "Activity close 首次提示 marker 非法")
    elif prompt_status == "pending" and prompt_at != "none":
        report("FAIL", "Activity close 首次提示 pending 不得有显示时间")
    elif prompt_status == "shown" and not activity_ledger_contract.TZ_TIME_RE.match(
        str(prompt_at or "")
    ):
        report("FAIL", "Activity close 首次提示 shown 缺带时区时间")
    by_course = {path.parent.name: path for path in ledger_paths}
    for course_id, (folder, pmeta) in courses.items():
        path = by_course.get(course_id)
        if path is None:
            report("FAIL", f"课程缺 activity_ledger.md：{course_id}")
            continue
        try:
            doc = activity_ledger_contract.load_ledger(path)
        except activity_ledger_contract.LedgerError as exc:
            report("FAIL", f"Activity ledger 无法读取：{course_id} -> {exc}")
            continue
        errors = doc.validate()
        for error in errors:
            report("FAIL", f"Activity ledger 非法：{course_id} -> {error}")
        if errors:
            continue
        # 新增 correction / migration_snapshot 门
        for event in doc.events:
            kind = event.get("event_kind")
            eid = event.get("event_id", "?")
            if kind == "migration_snapshot" and event.get("triggered_by") != "migration":
                if eid == "ALE-000011" and course_id == "MATH1607H":
                    # 已知历史指纹：允许一条具名兼容 WARN，直到合法 correction 闭合
                    has_correction = any(
                        ce.get("event_kind") == "correction"
                        and ce.get("corrects_event_id") == "ALE-000011"
                        for ce in doc.events
                    )
                    if not has_correction:
                        report(
                            "WARN",
                            f"ALE-000011 (migration_snapshot + user trigger) 已知历史指纹，"
                            "待 correction 闭合；不得作为新事件模板",
                        )
                else:
                    report(
                        "FAIL",
                        f"migration_snapshot 必须 triggered_by=migration: {course_id}/{eid}",
                    )
            if kind == "correction":
                corrects = event.get("corrects_event_id")
                if corrects == "ALE-000011" and course_id == "MATH1607H":
                    # correction 闭合后移除对应 WARN（由上述 WARN 条件自行处理）
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
                f"实体 Activity 未登记 ledger index：{course_id} -> {missing_index}",
            )
        declared_groups: set[str] = set()
        activity_map = folder / "activity_map.md"
        if activity_map.is_file():
            declared_groups = {
                row.get("content_group_id", "").strip("` ")
                for row in table_after_heading(read(activity_map), "内容组连接表")
                if row.get("content_group_id", "").strip("` ")
            }
        for entry in index.values():
            dangling = sorted(set(entry.content_group_ids) - declared_groups)
            if dangling:
                report(
                    "FAIL",
                    f"Activity ledger ContentGroup 悬空：{course_id}/"
                    f"{entry.activity_id} -> {dangling}",
                )
        if pmeta.get("lifecycle_status") != "ongoing":
            continue
        route = COURSE_ROUTES.get(course_id)
        if route is None:
            report("FAIL", f"ongoing 课程缺 Activity route：{course_id}")
            continue
        if route.activity_type == "none":
            current_state = None
        else:
            entry = index.get(f"{route.activity_type}:{route.activity_id}")
            if entry is None:
                report(
                    "FAIL",
                    f"progress 前台未在 ledger index：{course_id} -> "
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
                    f"progress next_action 与 ledger 漂移：{course_id}/{key} "
                    f"actual={pmeta.get(key)} expected={value}",
                )
        progress_body = cached_progress_content(course_id, folder)
        body_next_matches = list(re.finditer(
            r"(?m)^-\s+\*\*(?:下一步计划|下一步|下次第一件事)\*\*[：:]\s*(.+)$",
            progress_body,
        ))
        kind = expected["next_action_kind"]
        if kind in {"resume", "confirm_close", "start_activity"}:
            required_body = (
                f"{kind} {expected['next_activity_type']}:{expected['next_activity_id']}"
            )
        elif kind == "choose_activity":
            required_body = "从多个可用活动中选择下一项"
        else:
            required_body = "当前没有自动选择的下一活动"
        if (
            len(body_next_matches) != 1
            or required_body not in body_next_matches[0].group(1)
        ):
            report(
                "FAIL",
                f"progress 正文 next action 与结构化字段漂移：{course_id} "
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
            report("FAIL", f"Activity transaction lock 损坏：{exc}")
        else:
            expected_txn = os.environ.get("T2AG_022_EXPECT_TRANSACTION_ID")
            in_bound_postcheck = bool(
                expected_txn
                and lock_payload.get("transaction_id") == expected_txn
                and state in {"installed_pending_postcheck", "postcheck_passed"}
            )
            if state not in {"committed", "rolled_back"} and not in_bound_postcheck:
                report("FAIL", f"Activity transaction 未收口：status={state}")


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
        "check_skin_system": check_skin_system,
        "check_engagements_and_activities": check_engagements_and_activities,
        "check_registry": check_registry,
        "check_trading_boundary": check_trading_boundary,
        "check_external_references": check_external_references,
        "check_legacy_references": check_legacy_references,
        "check_retired_instance_ids": check_retired_instance_ids,
        "check_cloud_pause": check_cloud_pause,
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
        "check_candidate_replay_contract": check_candidate_replay_contract,
        "check_tracked_environment": check_tracked_environment,
        "check_dirty_tree": check_dirty_tree,
        "check_skeleton_textbook": check_skeleton_textbook_gate,
        "check_distribution_parity": check_distribution_parity,
        "check_line_endings": check_line_endings,
        "check_release_line_endings": check_release_line_endings,
    }
    course_handlers = {
        "check_groups": check_groups,
        "check_activity_ledgers": check_activity_ledgers,
        "check_question_banks": check_question_banks,
        "check_knowledge_ledgers": check_knowledge_ledgers,
        "check_project_verification": check_project_verification,
        "check_exercises": check_exercises,
        "check_textbook_preparation": check_textbook_preparation,
        "check_scope_page_cache": check_scope_page_cache,
        "check_checkpoint_block_routing": check_checkpoint_block_routing,
        "check_gate_ledger": check_gate_ledger,
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
                report("FAIL", "Skeleton 不得包含课程实例")
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
            print("启动运行检查失败；先修本地教学状态，不开新内容。")
        elif args.profile == "release" and plan["claimable_profile_result"]:
            print("发布审计失败；不得宣称候选或正式发布通过。")
        else:
            print("定向 Doctor 检查失败；结论仅限本计划。")
    else:
        if args.profile == "runtime" and plan["claimable_profile_result"]:
            print("本地教学运行检查通过。")
        elif args.profile == "release" and plan["claimable_profile_result"]:
            print("发布审计机械门通过；不等同于独立复审或发布批准。")
        else:
            print("定向 Doctor 检查通过；不得外推为完整 profile 结论。")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
