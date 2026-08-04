#!/usr/bin/env python3
"""Deterministic doctor for the T2AG 0.2.1 object model."""
from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
from pathlib import Path

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
EXPECTED_DOMAINS = {
    "00_core", "10_student", "20_teacher", "30_group", "40_course",
    "50_playbook", "60_journal", "70_tools", "80_interface",
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
HINT_GATE_SCHEMA_DATE = "2026-08-01"
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


def check_version_and_profile() -> None:
    constitution = MAIN / "t2ag.md"
    memory = MAIN / "00_core/t2ag_memory.md"
    for path in (constitution, memory):
        if path.exists() and "0.2.1" not in read(path):
            report("FAIL", f"版本未更新为 0.2.1：{rel(path)}")
    for path in (ROOT / "README.md", ROOT / "AGENTS.md", MAIN / "bin/t2ag"):
        if not path.exists() or "0.2.1" not in read(path):
            report("FAIL", f"发行入口版本未更新为 0.2.1：{rel(path)}")
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
    if FLAVOR == "skeleton":
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
            if pmeta.get("current_lesson") != "none":
                report("FAIL", f"planned 课程 current_lesson 必须为 none：{folder.name}")
            if pmeta.get("progress_nodes_status") != "lazy_on_activation":
                report("FAIL", f"planned 课程缺 lazy_on_activation：{folder.name}")
            planned_activity_fields = [
                field for field in (
                    "current_activity", "current_activity_id", "resume_path",
                    "activity_position", "lesson_position",
                )
                if field in pmeta
            ]
            if planned_activity_fields:
                report(
                    "FAIL",
                    f"planned 课程不得携带活动字段：{folder.name} -> "
                    f"{planned_activity_fields}",
                )
        elif lifecycle == "ongoing":
            required_progress = (
                "current_lesson", "current_activity", "current_activity_id",
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
        for root in (
            MAIN / "10_student/activities",
            MAIN / "10_student/engagements",
        ):
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
    if activities.exists():
        for path in activities.glob("AR-*.md"):
            meta = frontmatter(path)
            if meta.get("type") != "activity_record":
                report("FAIL", f"ActivityRecord type 非法：{rel(path)}")
            artifact_id = meta.get("activity_record_id", "")
            if not re.fullmatch(r"AR-\d{4}", artifact_id):
                report("FAIL", f"ActivityRecord ID 非法：{rel(path)} -> {artifact_id}")


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
        exercise_root = folder / "exercises"
        if not exercise_root.is_dir():
            continue
        units = sorted(
            path for path in exercise_root.iterdir()
            if path.is_dir() and not path.name.startswith("_")
        )
        unit_names = {unit.name for unit in units if re.fullmatch(r"U\d{4}", unit.name)}
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
            if not re.fullmatch(r"U\d{4}", unit.name):
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
            entries = re.split(r"^##\s+U\d{4}-Q\d{3}\s*$", content, flags=re.MULTILINE)[1:]
            headings = re.findall(r"^##\s+(U\d{4}-Q\d{3})\s*$", content, re.MULTILINE)
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
                    if not ameta.get("created") or ameta.get("created") == "—":
                        report("FAIL", f"Attempt 缺 created：{rel(carrier)}")
                    created = ameta.get("created", "")
                    gate_snapshot = ameta.get("hint_gate", "")
                    assistance_level = ameta.get("assistance_level", "")
                    requires_gate_snapshot = bool(
                        re.fullmatch(r"\d{4}-\d{2}-\d{2}", created)
                        and created >= HINT_GATE_SCHEMA_DATE
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
        if not (courses["MATH1607H"][0] / "exercises/U1101/problems.md").is_file():
            report("FAIL", "MATH1607H 缺 0.2.0 U1101 习题册")


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
        "working_pages", "temppage", "__pycache__", ".staging", ".recovery",
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


def check_working_pages(courses: dict[str, tuple[Path, dict[str, str]]]) -> None:
    for course_id, (folder, meta) in courses.items():
        if (
            meta.get("current_activity") != "lesson"
            or meta.get("course_driver") != "textbook"
        ):
            continue
        raw = meta.get("working_pages_window")
        page = meta.get("textbook_page")
        if not raw and not page:
            continue
        try:
            window = [int(value) for value in re.findall(r"\d+", raw or "")]
            current = int(page or "0")
        except ValueError:
            report("FAIL", f"working pages 字段不可解析：{course_id}")
            continue
        if not window or current not in window:
            report("FAIL", f"working pages 不含当前页：{course_id}")
            continue
        if window != list(range(min(window), max(window) + 1)):
            report("FAIL", f"working pages 窗口不连续：{course_id} -> {window}")
        lesson = meta.get("current_activity_id", "")
        if not re.fullmatch(r"lesson\d+", lesson):
            report("FAIL", f"working pages 缺当前 Lesson 活动：{course_id} -> {lesson or '缺失'}")
            continue
        working = folder / "lessons" / lesson / "working_pages"
        for value in window:
            if (
                FLAVOR != "lite"
                and not (working / f"pages/page{value}.png").exists()
            ):
                report("FAIL", f"缺 working page PNG：{course_id} page{value}")
            if not (working / f"raw_ocr/page_{value}_raw.txt").exists():
                report("FAIL", f"缺 OCR 原文：{course_id} page{value}")
        if not (working / "source_excerpt.md").exists():
            report("FAIL", f"缺 source_excerpt：{course_id}")


def check_trading_boundary() -> None:
    carrier = MAIN / "10_student/engagements/EG-0001_TradingDiscipline/engagement.md"
    journal = MAIN / "10_student/engagements/EG-0001_TradingDiscipline/trade_journal.md"
    if not carrier.exists() or not journal.exists():
        return
    content = read(carrier) + "\n" + read(journal)
    required = (
        "C:/Users/MikeChen/Documents/操作复盘系统/01-宪法层/交易纪律.md",
        "C:/Users/MikeChen/Documents/操作复盘系统/04-数据层/交易事件台账.csv",
    )
    for pointer in required:
        if pointer not in content:
            report("FAIL", f"Trading-OS 权威指针缺失：{pointer}")
    if "交易行为唯一真相源" in content or "纪律唯一真相源" in content:
        report("FAIL", "T2AG Engagement 越权自称 Trading-OS 真相源")


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
    if html_text.count('<svg class="flow-svg"') != mermaid_count:
        report(
            "FAIL",
            f"离线指南静态 SVG 数量漂移：expected={mermaid_count} actual={html_text.count('<svg class=\"flow-svg\"')}",
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


def check_handoff_contract() -> None:
    if FLAVOR != "main":
        return
    handoff_root = ROOT.parent / "docs/handoffs"
    index = handoff_root / "README.md"
    if not index.is_file():
        return
    rows = table_after_heading(read(index), "Active 交接")
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    seen_scopes: set[tuple[str, str]] = set()
    required = {
        "handoff_id", "scope", "applies_to", "status", "aging_state", "task_match",
        "created_at", "updated_at", "version_context", "supersedes", "superseded_by",
        "close_condition", "canonical_sources", "next_action", "semantic_check",
    }
    for row in rows:
        handoff_id = row.get("handoff_id", "")
        filename = row.get("文件", "").strip("` ")
        key = (row.get("scope", ""), row.get("applies_to", ""))
        if not handoff_id or not filename or not all(key):
            report("FAIL", f"active handoff 索引缺必填单元格：{handoff_id or filename or '?'}")
            continue
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
        for field in ("handoff_id", "scope", "applies_to", "updated_at"):
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
    manifest_path = MAIN / "60_journal/migration_021_profile_operations.json"
    report_path = MAIN / "60_journal/migration_021_profile_report.json"
    if not manifest_path.is_file() or not report_path.is_file():
        report("FAIL", "缺少 0.2.1 profile 迁移操作清单或报告")
        return
    try:
        manifest = json.loads(read(manifest_path))
        migration_report = json.loads(read(report_path))
    except json.JSONDecodeError as exc:
        report("FAIL", f"0.2.1 profile 迁移证据 JSON 非法：{exc}")
        return
    summary = migration_report.get("operation_manifest", {})
    if summary.get("path") != "main/60_journal/migration_021_profile_operations.json":
        report("FAIL", "0.2.1 profile 迁移报告未绑定 canonical manifest")
    if summary.get("sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
        report("FAIL", "0.2.1 profile 迁移 manifest SHA 漂移")
    operations = manifest.get("operations", [])
    if (
        manifest.get("schema_version") != "T2AG-MIGRATION-OPERATIONS-1"
        or manifest.get("operation_count") != 4
        or len(operations) != 4
        or summary.get("operation_count") != 4
        or migration_report.get("applied_count") != 4
        or migration_report.get("status") != "applied"
    ):
        report("FAIL", "0.2.1 profile 迁移计数或状态非法")
        return
    readme_content = read(ROOT / "README.md") if (ROOT / "README.md").is_file() else ""
    expected_kind = (
        "skeleton"
        if ROOT.name == "t2ag-skeleton"
        or re.search(r"^# T2AG .* Skeleton\s*$", readme_content, re.MULTILINE)
        else "main"
    )
    if manifest.get("target_kind") != expected_kind:
        report("FAIL", f"0.2.1 profile 迁移 target_kind 非法：{manifest.get('target_kind')}")
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
    for sequence, (source_path, target_path) in enumerate(expected_moves, start=1):
        row = operations[sequence - 1]
        sources = row.get("sources", [])
        post_target = row.get("post_target", {})
        if (
            row.get("sequence") != sequence
            or row.get("kind") != "move"
            or len(sources) != 1
            or sources[0].get("path") != source_path
            or row.get("target") != target_path
            or row.get("outcome") != "applied"
            or row.get("content_check") not in {"byte_identical", "path_repairs_only"}
            or post_target.get("path") != target_path
        ):
            report("FAIL", f"0.2.1 profile 迁移操作非法：sequence={sequence}")
            continue
        target = ROOT / target_path
        if not target.is_file():
            report("FAIL", f"0.2.1 profile 迁移目标不存在：{target_path}")
            continue
        if (ROOT / source_path).exists():
            report("FAIL", f"0.2.1 profile 旧路径仍存在：{source_path}")
        evidence_bytes = post_target.get("bytes")
        evidence_sha = post_target.get("sha256")
        if (
            not isinstance(evidence_bytes, int)
            or evidence_bytes < 0
            or not isinstance(evidence_sha, str)
            or re.fullmatch(r"[0-9a-f]{64}", evidence_sha) is None
        ):
            report("FAIL", f"0.2.1 profile 迁移目标证据非法：{target_path}")
        # These four targets are live student records.  Their migration-time
        # hashes remain report-bound evidence, not permanent content locks.
    verification = migration_report.get("current_verification", {})
    if (
        verification.get("pending_count") != 0
        or verification.get("missing") != []
        or verification.get("collisions") != []
    ):
        report("FAIL", "0.2.1 profile 迁移报告仍有待办或冲突")


def check_core_playbooks() -> None:
    roots = {
        name: ROOT.parent / name
        for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")
        if (ROOT.parent / name / "main/50_playbook").is_dir()
    }
    if len(roots) != 3:
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


def check_context_packet_contract() -> None:
    tool_relative = "main/70_tools/t2ag_context.py"
    activity_relative = "main/70_tools/t2ag_activity.py"
    test_relative = "main/70_tools/test_context_packet.py"
    playbook_relative = "main/50_playbook/context_packet.md"
    tool = ROOT / tool_relative
    activity = ROOT / activity_relative
    test = ROOT / test_relative
    playbook = ROOT / playbook_relative
    missing = [
        path
        for path, carrier in (
            (tool_relative, tool),
            (activity_relative, activity),
            (test_relative, test),
            (playbook_relative, playbook),
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
        "teacher_paths: Iterable[Path] | None = None",
        "frontmatter(problems, reader=reader)",
        "frontmatter(carrier, reader=reader)",
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
        "test_textbook_lesson_requires_window_metadata_and_file",
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
            "t2ag_context.py --course <ID> --format markdown",
            "即时摘录 + 触发式展开",
            "同一对话内未变化的 L0 不重复读取",
            "--include-l1",
            "完整序列化 Markdown",
            "t2ag_hint_gate.py",
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

    release_roots = {
        name: ROOT.parent / name
        for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")
        if (ROOT.parent / name).is_dir()
    }
    if len(release_roots) != 3:
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
    if len(manifests) == 3 and len(set(manifests.values())) != 1:
        report("FAIL", "学习上下文包/活动工具或测试在三发行分叉")


def check_candidate_replay_contract() -> None:
    tool_relative = "main/70_tools/t2ag_candidate_replay.py"
    test_relative = "main/70_tools/test_020_contracts.py"
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
        for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")
        if (ROOT.parent / name).is_dir()
    }
    if len(release_roots) != 3:
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
    if len(manifests) == 3 and len(set(manifests.values())) != 1:
        report("FAIL", "发布候选隔离工具或负例测试在三发行分叉")


def check_course_activity_templates() -> None:
    required = {
        "README.md", "course.md.template", "progress.md.template",
        "activity_map.md.template", "lessons/lessonNN/lessonNN.md.template",
        "exercises/Udddd/exercise.md.template",
        "exercises/Udddd/problems.md.template",
        "book/primary/verified_excerpts/source.md.template",
        "exercises/Udddd/attempts/ATdddd/attempt.md.template",
        "exercises/Udddd/reviews/RVdddd.md.template",
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
        "working_pages 仅在 `lesson` 分支",
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
    release_roots = {
        name: ROOT.parent / name
        for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")
        if (ROOT.parent / name).is_dir()
    }
    # A standalone unpacked Skeleton has no sibling releases, so only validate itself.
    # In the development workspace all three release roots exist and must carry an
    # identical, complete contract/template bundle.
    if len(release_roots) != 3:
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


def check_cloud_pause() -> None:
    state = ROOT / "cloud/cloud_sync_state.md"
    if state.exists() and not re.search(
        r"^-\s*cloud_bridge_status:\s*paused\s*$", read(state), re.MULTILINE
    ):
        report("FAIL", "Cloud bridge 未保持 paused")


def check_dirty_tree() -> None:
    if not (ROOT / ".git").exists():
        return
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True,
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if proc.stdout.strip():
        report("WARN", "工作树存在未快照改动；可继续施工，但不得宣称可发布")


def main() -> int:
    report("INFO", f"release_flavor: {FLAVOR}")
    check_structure()
    check_version_and_profile()
    check_skin_system()
    courses = discover_courses()
    if FLAVOR == "skeleton" and courses:
        report("FAIL", "Skeleton 不得包含课程实例")
    check_groups(courses)
    check_engagements_and_activities()
    check_question_banks(courses)
    check_knowledge_ledgers(courses)
    check_project_verification(courses)
    check_exercises(courses)
    teacher_mapping = check_teacher_contract(courses)
    check_memory_pointers(courses, teacher_mapping)
    check_registry()
    check_working_pages(courses)
    check_trading_boundary()
    check_legacy_references()
    check_retired_instance_ids()
    check_flow_and_guide()
    check_handoff_contract()
    check_cloud_contract()
    check_derived_tools()
    check_migration_evidence()
    check_migration_021_evidence()
    check_course_activity_templates()
    check_core_playbooks()
    check_context_packet_contract()
    check_candidate_replay_contract()
    check_tracked_environment()
    check_dirty_tree()
    print()
    print(f"result: {len(fails)} FAIL, {len(warns)} WARN")
    if fails:
        print("先修 FAIL；课程 progress.md 是进度唯一真相源。")
    else:
        print("结构与状态检查通过。")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
