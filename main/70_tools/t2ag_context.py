#!/usr/bin/env python3
"""Build an ephemeral, exact-excerpt context packet for one learning session.

The packet is a read-only projection.  It never writes a cache and never owns
state.  Activity and teacher routing consume the same byte-backed SourceCache
as excerpt selection; every file and directory listing observed during the
build is checked again before output so a mixed-version packet is rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from t2ag_activity import (
    ActivityContractError,
    ProgressSnapshot,
    TeacherContractError,
    frontmatter_text,
    resolve_activity,
    resolve_teacher_mapping,
)


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"
DEFAULT_SOFT_CHAR_BUDGET = 16_000
PLACEHOLDER_RE = re.compile(
    r"<(?:required|confirm|confirm-or-none|off\s*\|\s*suggest\s*\|\s*auto)>"
    r"|[（(]待填写[）)]",
    re.IGNORECASE,
)
COURSE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
PROBLEM_ID_RE = re.compile(r"(?:U\d{4}|exercise\d{2,})-Q\d{3}")


class ContextPacketError(ValueError):
    """The packet cannot be built without guessing or mixing source states."""


class SourceCache:
    """Read bytes once and reject file or directory changes before output."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._raw: dict[Path, bytes] = {}
        self._content: dict[Path, str] = {}
        self._directory_entries: dict[
            tuple[Path, str],
            tuple[Path, ...],
        ] = {}

    def _checked(self, path: Path) -> Path:
        candidate = path.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ContextPacketError(f"source escapes repository root: {path}") from exc
        return candidate

    def read_bytes(self, path: Path, *, required: bool = True) -> bytes:
        checked = self._checked(path)
        if checked in self._raw:
            return self._raw[checked]
        if not checked.is_file():
            if required:
                raise ContextPacketError(
                    f"required context source missing: {self.relative(checked)}"
                )
            return b""
        try:
            raw = checked.read_bytes()
        except OSError as exc:
            raise ContextPacketError(
                f"cannot read context source: {self.relative(checked)}"
            ) from exc
        self._raw[checked] = raw
        return raw

    def read(self, path: Path, *, required: bool = True) -> str:
        checked = self._checked(path)
        if checked in self._content:
            return self._content[checked]
        raw = self.read_bytes(checked, required=required)
        if not raw and not checked.is_file() and not required:
            return ""
        content = (
            raw.decode("utf-8-sig", errors="replace")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
        self._content[checked] = content
        return content

    def glob(self, directory: Path, pattern: str) -> list[Path]:
        checked = self._checked(directory)
        key = (checked, pattern)
        if key not in self._directory_entries:
            entries = tuple(
                sorted(
                    (
                        self._checked(path)
                        for path in checked.glob(pattern)
                        if path.is_file()
                    ),
                    key=lambda path: path.as_posix(),
                )
            )
            self._directory_entries[key] = entries
        return list(self._directory_entries[key])

    def relative(self, path: Path) -> str:
        return self._checked(path).relative_to(self.root).as_posix()

    def digest(self, path: Path) -> str:
        return hashlib.sha256(self.read_bytes(path)).hexdigest()

    def assert_unchanged(self) -> None:
        changed: list[str] = []
        for path, before in self._raw.items():
            try:
                after = path.read_bytes()
            except OSError:
                changed.append(self.relative(path))
                continue
            if after != before:
                changed.append(self.relative(path))
        for (directory, pattern), before in self._directory_entries.items():
            after = tuple(
                sorted(
                    (
                        self._checked(path)
                        for path in directory.glob(pattern)
                        if path.is_file()
                    ),
                    key=lambda path: path.as_posix(),
                )
            )
            if after != before:
                changed.append(f"{self.relative(directory)}/{pattern}")
        if changed:
            raise ContextPacketError(
                "context sources changed during packet build; rerun: "
                + ", ".join(sorted(changed))
            )


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    start: int
    body_start: int
    end: int


@dataclass(frozen=True)
class Selection:
    source: str
    label: str
    content: str
    sha256: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "label": self.label,
            "sha256": self.sha256,
            "content": self.content,
        }


def headings(content: str) -> list[Heading]:
    matches = list(re.finditer(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", content, re.MULTILINE))
    result: list[Heading] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        end = len(content)
        for later in matches[index + 1 :]:
            if len(later.group(1)) <= level:
                end = later.start()
                break
        body_start = match.end()
        if body_start < len(content) and content[body_start] == "\n":
            body_start += 1
        result.append(
            Heading(
                level=level,
                title=match.group(2).strip(),
                start=match.start(),
                body_start=body_start,
                end=end,
            )
        )
    return result


def raw_frontmatter(content: str) -> str:
    match = re.match(r"^---\s*\n.*?\n---\s*(?:\n|$)", content, re.DOTALL)
    return match.group(0).strip() if match else ""


def section(
    content: str,
    title: str,
    *,
    level: int | None = None,
    prefix: bool = False,
    required: bool = True,
) -> str:
    found = [
        item
        for item in headings(content)
        if (level is None or item.level == level)
        and (
            item.title.startswith(title)
            if prefix
            else item.title == title
        )
    ]
    if len(found) != 1:
        if required:
            raise ContextPacketError(
                f"expected one heading {title!r}, found {len(found)}"
            )
        return ""
    item = found[0]
    return content[item.start : item.end].strip()


def sections_by_prefix(
    content: str,
    prefix: str,
    *,
    level: int | None = None,
) -> list[str]:
    return [
        content[item.start : item.end].strip()
        for item in headings(content)
        if (level is None or item.level == level) and item.title.startswith(prefix)
    ]


def join_exact(parts: Iterable[str]) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def markdown_table_row(content: str, first_cell: str) -> str:
    pattern = re.compile(
        rf"^\|\s*{re.escape(first_cell)}\s*\|.*\|\s*$",
        re.MULTILINE,
    )
    matches = pattern.findall(content)
    if len(matches) != 1:
        raise ContextPacketError(
            f"expected one table row for {first_cell!r}, found {len(matches)}"
        )
    return matches[0].strip()


def markdown_table_cells(row: str) -> list[str]:
    return [cell.strip().strip("`") for cell in row.strip().strip("|").split("|")]


def group_course_ids(group_row: str) -> set[str]:
    cells = markdown_table_cells(group_row)
    if len(cells) < 5:
        raise ContextPacketError("learning_path 课程组索引行列数不足")
    return set(re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", cells[2]))


def memory_value(memory: str, label: str) -> str:
    row = markdown_table_row(memory, label)
    cells = markdown_table_cells(row)
    if len(cells) < 2 or not cells[1] or cells[1] == "—":
        raise ContextPacketError(f"memory pointer missing: {label}")
    return cells[1]


def initialized(profile: str, memory: str) -> bool:
    meta = frontmatter_text(profile)
    if meta.get("initialization_status") != "initialized":
        return False
    if meta.get("exercise_hint_gate") not in {"enabled", "disabled"}:
        return False
    if PLACEHOLDER_RE.search(profile):
        return False
    summary = section(memory, "上次课摘要", level=2, required=False)
    return bool(summary) and not re.search(r"\*\*日期\*\*[：:]\s*—", summary)


def selected_field_lines(content: str, field_names: Iterable[str]) -> str:
    names = tuple(field_names)
    lines: list[str] = []
    for raw in content.splitlines():
        stripped = raw.strip()
        if any(
            re.match(rf"^-\s*{re.escape(name)}[：:]", stripped)
            or re.match(rf"^{re.escape(name)}[：:]", stripped)
            for name in names
        ):
            lines.append(raw.rstrip())
    return "\n".join(lines).strip()


def mistake_schedule_snapshot(content: str) -> str:
    active = section(content, "活跃知识点", level=2, required=False)
    if not active:
        return "## 活跃知识点\n\n暂无。"
    snapshots: list[str] = ["## 活跃知识点"]
    entries = [
        item
        for item in headings(active)
        if item.level == 3 and re.fullmatch(r"M-\d{4}", item.title)
    ]
    for item in entries:
        block = active[item.start : item.end].strip()
        fields = selected_field_lines(
            block,
            (
                "知识点键",
                "状态",
                "当前周期摘要",
                "最近正式复测",
                "下次允许复测",
            ),
        )
        snapshots.append(join_exact((f"### {item.title}", fields)))
    if len(snapshots) == 1:
        snapshots.append("暂无。")
    return "\n\n".join(snapshots)


def course_reflection_snapshot(content: str, course_id: str, count: int = 3) -> str:
    course = section(content, course_id, level=2, prefix=True)
    course_heading = next(item for item in headings(course) if item.level == 2)
    first_child = next(
        (item for item in headings(course) if item.start > course_heading.start),
        None,
    )
    preamble_end = first_child.start if first_child else len(course)
    preamble = course[:preamble_end].strip()
    tree = section(course, "知识点树形图", level=3, required=False)
    records = sections_by_prefix(course, "REFL-", level=4)[-count:]
    return join_exact((preamble, tree, *records))


def current_problem_id(exercise_scope: str) -> str:
    match = re.search(
        r"^-\s*当前题目[：:]\s*`?([A-Za-z0-9_-]+)`?\s*[。.]?\s*$",
        exercise_scope,
        re.MULTILINE,
    )
    if not match or not PROBLEM_ID_RE.fullmatch(match.group(1)):
        raise ContextPacketError("Exercise 学习范围缺合法的当前题目")
    return match.group(1)


def parse_int_list(raw: str) -> list[int]:
    value = raw.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    result: list[int] = []
    for part in value[1:-1].split(","):
        token = part.strip()
        if token.isdigit():
            result.append(int(token))
    return result


def add_selection(
    selections: list[Selection],
    cache: SourceCache,
    path: Path,
    label: str,
    content: str,
) -> None:
    if not content.strip():
        raise ContextPacketError(f"empty required selection: {label}")
    selections.append(
        Selection(
            source=cache.relative(path),
            label=label,
            content=content.strip(),
            sha256=cache.digest(path),
        )
    )


def textbook_lesson_window(
    cache: SourceCache,
    progress_snapshot: ProgressSnapshot,
    route: object,
) -> tuple[Path, str] | None:
    if (
        route.activity_type != "lesson"
        or route.course_driver != "textbook"
    ):
        return None
    if not route.working_pages_path:
        raise ContextPacketError("textbook Lesson 缺 canonical working pages 路由")
    pages = parse_int_list(
        progress_snapshot.meta.get("working_pages_window", "")
    )
    if not pages or len(pages) != len(set(pages)):
        raise ContextPacketError(
            "textbook Lesson 缺合法且不重复的 working_pages_window"
        )
    current_page_raw = progress_snapshot.meta.get("textbook_page", "").strip()
    if not current_page_raw.isdigit() or int(current_page_raw) not in pages:
        raise ContextPacketError(
            "textbook Lesson 的 textbook_page 缺失或不在 working_pages_window"
        )
    working_path = cache.root / route.working_pages_path
    working = cache.read(working_path)
    page_sections: list[str] = []
    for page in pages:
        excerpt = section(
            working,
            f"第 {page} 页",
            level=2,
            required=False,
        )
        if not excerpt:
            raise ContextPacketError(
                "textbook Lesson 教材窗口缺页："
                f"{cache.relative(working_path)}#第 {page} 页"
            )
        page_sections.append(excerpt)
    return (
        working_path,
        join_exact((raw_frontmatter(working), *page_sections)),
    )


def exercise_first_step_selections(
    cache: SourceCache,
    main: Path,
    course_id: str,
    activity_id: str,
    problem_id: str,
) -> list[Selection]:
    selections: list[Selection] = []
    exercise_root = (
        main / "40_course" / course_id / "exercises" / activity_id
    )
    candidates = (
        (
            cache.glob(exercise_root / "attempts", "*/attempt.md"),
            "当前题直接相关 Attempt",
        ),
        (
            cache.glob(exercise_root / "reviews", "RV*.md"),
            "当前题直接相关 Review",
        ),
    )
    for paths, label in candidates:
        for path in paths:
            content = cache.read(path)
            problem_ids = set(
                PROBLEM_ID_RE.findall(
                    frontmatter_text(content).get("problem_ids", "")
                )
            )
            if problem_id in problem_ids:
                add_selection(
                    selections,
                    cache,
                    path,
                    f"{label} {path.stem}",
                    content,
                )
    return selections


def first_step_empty_reason(route: object) -> str:
    if route.activity_type == "none":
        return "当前处于活动间隙；没有前台 Activity 的首步追加证据。"
    if route.activity_type == "exercise":
        return "当前题面已在 L0；当前题没有既有 Attempt/Review 需要追加。"
    if route.course_driver == "textbook":
        return "当前教材窗口已在 L0；当前停点没有另行声明的直接证据。"
    return "当前 Lesson 恢复胶囊已在 L0；当前停点未声明标准化的首步追加证据。"


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen and resolved.is_file():
            seen.add(resolved)
            result.append(resolved)
    return result


def conditional_reads(course_id: str, route: object, group_id: str) -> list[dict[str, str]]:
    course_root = f"main/40_course/{course_id}"
    if route.activity_type == "none":
        direct_evidence_trigger = "选择或恢复下一 Activity"
        direct_evidence_read = (
            f"{course_root}/activity_ledger.md 与 progress.md 的 next_action"
        )
    elif route.activity_type == "exercise":
        direct_evidence_trigger = "当前题已有提交、反馈或订正"
        direct_evidence_read = (
            f"{course_root}/exercises/{route.activity_id}/attempts/ "
            "与 reviews/ 的当前题相关条目"
        )
    else:
        direct_evidence_trigger = "当前 Lesson 已有练习、产物或待核对记录"
        direct_evidence_read = (
            f"{course_root}/lessons/{route.activity_id}/"
            f"{route.activity_id}.md 中与当前停点直接相关的记录"
        )
        if route.working_pages_path:
            direct_evidence_read += (
                f"；教材原文仅使用 {route.working_pages_path} 的当前窗口"
            )
    return [
        {
            "trigger": "状态冲突、历史追问或进度审计",
            "read": f"{course_root}/progress.md 的完整教学记录及对应活动证据",
        },
        {
            "trigger": direct_evidence_trigger,
            "read": direct_evidence_read,
        },
        {
            "trigger": "正式复测、疑问回收或模式裁决",
            "read": f"{course_root}/mistake_bank.md、question_bank.md 与证据回链",
        },
        {
            "trigger": "排期、调参、组复盘或结组",
            "read": f"main/30_group/{group_id}/plan.md、calendar.md、review.md 完整相关节",
        },
        {
            "trigger": "教师规则冲突或教师配置修改",
            "read": "main/20_teacher/overlay.md 与当前教师模板全文",
        },
        {
            "trigger": "结课或手动保存",
            "read": "运行 t2ag_activity.py --intent close，并按 session_close.md 回读实际写入目标",
        },
        {
            "trigger": "项目维护、迁移或发布",
            "read": "只读匹配的 active project handoff、合同、测试与实际 Git 状态",
        },
    ]


def build_packet(
    root: Path = ROOT,
    *,
    course_id: str | None = None,
    soft_char_budget: int = DEFAULT_SOFT_CHAR_BUDGET,
) -> dict[str, object]:
    cache = SourceCache(root)
    main = root / "main"
    profile_path = main / "10_student/profile/profile.md"
    memory_path = main / "00_core/t2ag_memory.md"
    profile = cache.read(profile_path)
    memory = cache.read(memory_path)

    if not initialized(profile, memory):
        selections: list[Selection] = []
        add_selection(
            selections,
            cache,
            profile_path,
            "初始化状态",
            raw_frontmatter(profile) or profile[:400],
        )
        summary = section(memory, "上次课摘要", level=2, required=False)
        if summary:
            add_selection(selections, cache, memory_path, "上次课摘要", summary)
        cache.assert_unchanged()
        return {
            "schema_version": 2,
            "status": "first_run_required",
            "next_action": "读取 main/50_playbook/first_run.md",
            "selections": [item.as_dict() for item in selections],
        }

    memory_current_course = memory_value(memory, "当前课程")
    resolved_course = course_id or memory_current_course
    if not COURSE_ID_RE.fullmatch(resolved_course):
        raise ContextPacketError(f"illegal course_id: {resolved_course!r}")
    group_id = memory_value(memory, "活跃课程组")
    if not re.fullmatch(r"G\d{2,}", group_id):
        raise ContextPacketError(f"illegal active group id: {group_id!r}")
    context_mode = (
        "memory_current"
        if resolved_course == memory_current_course
        else "explicit_same_active_group"
    )

    learning_path_path = main / "10_student/profile/learning_path.md"
    learning_path = cache.read(learning_path_path)
    course_row = markdown_table_row(learning_path, resolved_course)
    group_row = markdown_table_row(learning_path, group_id)
    if resolved_course not in group_course_ids(group_row):
        raise ContextPacketError(
            f"requested course {resolved_course} is not a member of "
            f"active group {group_id}; activate its group before teaching"
        )

    progress_path = main / "40_course" / resolved_course / "progress.md"
    progress = cache.read(progress_path)
    progress_snapshot = ProgressSnapshot(
        path=progress_path,
        content=progress,
        meta=frontmatter_text(progress),
    )
    route = resolve_activity(
        root,
        resolved_course,
        snapshot=progress_snapshot,
        reader=cache.read,
    )
    selections = []

    if context_mode == "memory_current":
        add_selection(
            selections,
            cache,
            memory_path,
            "恢复指针",
            join_exact(
                (
                    section(memory, "上次课摘要", level=2),
                    section(memory, "当前状态指针", level=2),
                )
            ),
        )
    else:
        add_selection(
            selections,
            cache,
            memory_path,
            "全局指针切换校验",
            join_exact(
                (
                    markdown_table_row(memory, "活跃课程组"),
                    markdown_table_row(memory, "当前课程"),
                )
            ),
        )
    profile_parts = [raw_frontmatter(profile)]
    for title in (
        "基本信息",
        "执行参数",
        "学习目标",
        "期望的辅导方式",
        "特殊要求（可选）",
        "一、总纲",
    ):
        profile_parts.append(section(profile, title, required=False))
    add_selection(
        selections,
        cache,
        profile_path,
        "学生教学契约",
        join_exact(profile_parts),
    )

    add_selection(
        selections,
        cache,
        learning_path_path,
        "当前课程与课程组索引行",
        join_exact(
            (
                course_row,
                group_row,
            )
        ),
    )

    group_root = main / "30_group" / group_id
    plan_path = group_root / "plan.md"
    plan = cache.read(plan_path)
    plan_meta = frontmatter_text(plan)
    if plan_meta.get("status") != "active":
        raise ContextPacketError(f"active group is not active: {group_id}")
    add_selection(
        selections,
        cache,
        plan_path,
        "当前课程组容量",
        join_exact(
            (
                raw_frontmatter(plan),
                section(plan, "1. 基本信息", level=2),
                section(plan, "2. 成员课程", level=2),
            )
        ),
    )
    calendar_path = group_root / "calendar.md"
    calendar = cache.read(calendar_path)
    add_selection(
        selections,
        cache,
        calendar_path,
        "当前时间预算与周期",
        join_exact(
            (
                raw_frontmatter(calendar),
                section(calendar, "时间预算", level=2),
                section(calendar, "3-1-3 周期", level=2),
            )
        ),
    )

    add_selection(
        selections,
        cache,
        progress_path,
        "进度真相源当前切片",
        join_exact(
            (
                raw_frontmatter(progress),
                section(progress, "二、当前进度", level=2),
            )
        ),
    )

    carrier_path = (
        progress_path if route.activity_type == "none" else root / route.resume_path
    )
    carrier = cache.read(carrier_path)
    baseline_activity_paths: list[Path] = (
        [] if route.activity_type == "none" else [carrier_path]
    )
    l1_selections: list[Selection] = []
    if route.activity_type == "exercise":
        scope = section(carrier, "学习范围", level=2)
        add_selection(
            selections,
            cache,
            carrier_path,
            "当前 Exercise 恢复胶囊",
            join_exact((raw_frontmatter(carrier), scope)),
        )
        problem_id = current_problem_id(scope)
        problems_path = (
            main
            / "40_course"
            / resolved_course
            / "exercises"
            / route.activity_id
            / "problems.md"
        )
        problems = cache.read(problems_path)
        problems_meta = frontmatter_text(problems)
        problem = section(problems, problem_id, level=2)
        problem_fields = selected_field_lines(
            problem,
            (
                "题号",
                "来源页",
                "难度",
                "依赖 completion node",
                "状态",
                "错误级别",
            ),
        )
        add_selection(
            selections,
            cache,
            problems_path,
            f"当前题元数据 {problem_id}",
            join_exact((f"## {problem_id}", problem_fields)),
        )
        baseline_activity_paths.append(problems_path)
        if route.source_path:
            source_path = root / route.source_path
            source = cache.read(source_path)
            expected_source_sha = problems_meta.get("source_sha256", "")
            actual_source_sha = cache.digest(source_path)
            if not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha):
                raise ContextPacketError(
                    "textbook Exercise problems.md 缺合法 source_sha256"
                )
            if actual_source_sha != expected_source_sha:
                raise ContextPacketError(
                    "textbook Exercise 题源 SHA 与 problems.md 不一致："
                    f"{cache.relative(source_path)}"
                )
            source_identity = selected_field_lines(
                raw_frontmatter(source),
                (
                    "artifact_id",
                    "source_document",
                    "source_document_sha256",
                    "source_locator",
                    "verification_status",
                    "verified",
                ),
            )
            add_selection(
                selections,
                cache,
                source_path,
                f"人工校对题面 {problem_id}",
                join_exact(
                    (
                        source_identity,
                        section(source, problem_id, level=2),
                    )
                ),
            )
            baseline_activity_paths.append(source_path)
        l1_selections = exercise_first_step_selections(
            cache,
            main,
            resolved_course,
            route.activity_id,
            problem_id,
        )
        baseline_activity_paths.extend(
            root / item.source for item in l1_selections
        )
    elif route.activity_type == "lesson":
        carrier_h2 = [item for item in headings(carrier) if item.level == 2]
        preferred: Heading | None = None
        for keyword in ("当前状态", "学习范围", "恢复快照", "本课概览"):
            preferred = next(
                (item for item in carrier_h2 if keyword in item.title),
                None,
            )
            if preferred:
                break
        recovery_capsule = (
            carrier[preferred.start : preferred.end].strip()
            if preferred
            else ""
        )
        add_selection(
            selections,
            cache,
            carrier_path,
            "当前 Lesson 恢复胶囊",
            join_exact((raw_frontmatter(carrier), recovery_capsule)),
        )
        lesson_window = textbook_lesson_window(
            cache,
            progress_snapshot,
            route,
        )
        if lesson_window is not None:
            working_path, excerpt = lesson_window
            add_selection(
                selections,
                cache,
                working_path,
                "当前教材窗口",
                excerpt,
            )
            baseline_activity_paths.append(working_path)

    course_root = main / "40_course" / resolved_course
    question_path = course_root / "question_bank.md"
    question = cache.read(question_path)
    add_selection(
        selections,
        cache,
        question_path,
        "未闭合疑问",
        join_exact(
            (
                section(question, "待解决", level=2),
                section(question, "需要回看", level=2),
            )
        ),
    )
    mistake_path = course_root / "mistake_bank.md"
    mistake = cache.read(mistake_path)
    add_selection(
        selections,
        cache,
        mistake_path,
        "活跃错题调度摘要",
        mistake_schedule_snapshot(mistake),
    )

    reflections_path = main / "10_student/profile/course_reflections.md"
    reflections = cache.read(reflections_path)
    add_selection(
        selections,
        cache,
        reflections_path,
        "当前课程感想与最近提炼",
        course_reflection_snapshot(reflections, resolved_course),
    )

    reasoning_path = main / "10_student/profile/reasoning_patterns.md"
    reasoning = cache.read(reasoning_path)
    if route.activity_type == "exercise":
        add_selection(
            selections,
            cache,
            reasoning_path,
            "活跃解题思维模式",
            join_exact(
                (
                    section(reasoning, "一、解题思维总纲", level=2),
                    section(reasoning, "二、活跃思维模式", level=2),
                )
            ),
        )

    overlay_path = main / "20_teacher/overlay.md"
    overlay = cache.read(overlay_path)
    teacher_paths = cache.glob(main / "20_teacher", "T*.md")
    mapping = resolve_teacher_mapping(
        root,
        reader=cache.read,
        teacher_paths=teacher_paths,
    )
    teacher_id, teacher_relative = mapping.get(
        resolved_course,
        mapping["(默认)"],
    )
    overlay_parts = [markdown_table_row(overlay, resolved_course)]
    for title in (
        "回复格式",
        "教学节奏",
        "启动摩擦与疑问处置",
        "情绪使用红线（不可违反，优先级高于模板默认行为）",
        "学生协商结果",
    ):
        overlay_parts.append(section(overlay, title, required=False))
    add_selection(
        selections,
        cache,
        overlay_path,
        "当前教师 overlay",
        join_exact(overlay_parts),
    )

    teacher_path = root / teacher_relative
    teacher = cache.read(teacher_path)
    activity_module = section(
        teacher,
        (
            "模块三:解题流程"
            if route.activity_type == "exercise"
            else "模块一:渐进式教学"
        ),
        level=3,
        prefix=True,
        required=False,
    )
    add_selection(
        selections,
        cache,
        teacher_path,
        f"生效教师模板 {teacher_id}",
        join_exact(
            (
                raw_frontmatter(teacher),
                section(teacher, "核心人格", level=2),
                activity_module,
                section(teacher, "互动方式", level=2, required=False),
                section(teacher, "纠错方式", level=2, required=False),
                section(teacher, "行为准则(不可违反)", level=2),
                section(teacher, "教学节奏与互动原则", level=2),
                section(teacher, "默认回复格式", level=2),
            )
        ),
    )

    baseline_paths = unique_paths(
        (
            memory_path,
            profile_path,
            learning_path_path,
            plan_path,
            calendar_path,
            progress_path,
            *baseline_activity_paths,
            question_path,
            mistake_path,
            reflections_path,
            reasoning_path,
            overlay_path,
            teacher_path,
        )
    )
    reference_chars = sum(len(cache.read(path)) for path in baseline_paths)
    l0_source_chars = sum(len(item.content) for item in selections)
    l1_source_chars = sum(len(item.content) for item in l1_selections)
    selected_source_chars = l0_source_chars + l1_source_chars
    source_ratio = (
        selected_source_chars / reference_chars
        if reference_chars
        else 1.0
    )
    packet: dict[str, object] = {
        "schema_version": 2,
        "status": "ready",
        "course_id": resolved_course,
        "memory_current_course": memory_current_course,
        "context_mode": context_mode,
        "group_id": group_id,
        "route": {
            "course_driver": route.course_driver,
            "current_activity": route.activity_type,
            "current_activity_id": route.activity_id,
            "activity_position": route.activity_position,
            "primary_read": route.resume_path,
            "lesson_context": {
                "kind": route.lesson_context_kind,
                "id": route.lesson_context_id or None,
            },
            "working_pages": route.working_pages_path or None,
        },
        "teacher": {
            "template_id": teacher_id,
            "template_path": teacher_relative,
        },
        "cost": {
            "metric": (
                "Unicode characters in LF-normalized Markdown; exact for "
                "this serializer, source selection is a separate inventory proxy"
            ),
            "reference_inventory_chars": reference_chars,
            "l0_selected_source_chars": l0_source_chars,
            "l1_selected_source_chars": l1_source_chars,
            "source_selection_ratio": round(source_ratio, 4),
            "source_inventory_omitted_percent": round(
                (1.0 - source_ratio) * 100.0,
                1,
            ),
            "serialized_l0_markdown_chars": 0,
            "serialized_l0_plus_l1_markdown_chars": 0,
            "soft_char_budget": soft_char_budget,
            "l0_budget_state": "PENDING",
            "l0_plus_l1_budget_state": "PENDING",
        },
        "selections": [item.as_dict() for item in selections],
        "l1_selections": [item.as_dict() for item in l1_selections],
        "l1_empty_reason": first_step_empty_reason(route),
        "conditional_reads": conditional_reads(
            resolved_course,
            route,
            group_id,
        ),
    }
    finalize_serialized_cost(packet)
    cache.assert_unchanged()
    return packet


def render_markdown(
    packet: dict[str, object],
    *,
    include_l1: bool = False,
) -> str:
    if packet["status"] == "first_run_required":
        lines = [
            "# T2AG 上下文包",
            "",
            "- status: `first_run_required`",
            f"- next_action: `{packet['next_action']}`",
        ]
    else:
        route = packet["route"]
        cost = packet["cost"]
        lines = [
            (
                "# T2AG L0 + 首个 L1 学习会话上下文包"
                if include_l1
                else "# T2AG L0 学习会话上下文包"
            ),
            "",
            "> 只读即时投影；正文为源文件逐字摘录或机械路由字段，不是新的真相源。",
            "",
            f"- status: `{packet['status']}`",
            f"- course: `{packet['course_id']}`",
            f"- memory_current_course: `{packet['memory_current_course']}`",
            f"- context_mode: `{packet['context_mode']}`",
            f"- active_group: `{packet['group_id']}`",
            (
                "- current_activity: "
                f"`{route['current_activity']}: {route['current_activity_id']}`"
            ),
            f"- activity_position: {route['activity_position']}",
            f"- primary_read: `{route['primary_read']}`",
            "",
            "## 成本账",
            "",
            (
                "- reference_inventory_chars: "
                f"`{cost['reference_inventory_chars']}`"
            ),
            (
                "- l0_selected_source_chars: "
                f"`{cost['l0_selected_source_chars']}`"
            ),
            (
                "- l1_selected_source_chars: "
                f"`{cost['l1_selected_source_chars']}`"
            ),
            (
                "- source_selection_ratio: "
                f"`{cost['source_selection_ratio']}`"
            ),
            (
                "- source_inventory_omitted_percent: "
                f"`{cost['source_inventory_omitted_percent']}%`"
            ),
            (
                "- serialized_l0_markdown_chars: "
                f"`{cost['serialized_l0_markdown_chars']}`"
            ),
            (
                "- serialized_l0_plus_l1_markdown_chars: "
                f"`{cost['serialized_l0_plus_l1_markdown_chars']}`"
            ),
            (
                "- l0_soft_budget: "
                f"`{cost['l0_budget_state']} / {cost['soft_char_budget']}`"
            ),
            (
                "- l0_plus_l1_soft_budget: "
                f"`{cost['l0_plus_l1_budget_state']} / "
                f"{cost['soft_char_budget']}`"
            ),
            "",
            (
                "> `reference_inventory_chars` 是当前来源库存对照，不是旧 Prompt "
                "实测；库存省略比例不等于端到端 Token 降幅。"
            ),
        ]
    for index, item in enumerate(packet.get("selections", []), start=1):
        lines.extend(
            (
                "",
                f"## L0.{index} · {item['label']}",
                "",
                f"- source: `{item['source']}`",
                f"- source_sha256: `{item['sha256']}`",
                "",
                "<!-- exact-source-excerpt:start -->",
                item["content"],
                "<!-- exact-source-excerpt:end -->",
            )
        )
    if include_l1:
        l1_selections = packet.get("l1_selections", [])
        lines.extend(("", "## L1 · 当前一步直接证据"))
        if l1_selections:
            for index, item in enumerate(l1_selections, start=1):
                lines.extend(
                    (
                        "",
                        f"### L1.{index} · {item['label']}",
                        "",
                        f"- source: `{item['source']}`",
                        f"- source_sha256: `{item['sha256']}`",
                        "",
                        "<!-- exact-source-excerpt:start -->",
                        item["content"],
                        "<!-- exact-source-excerpt:end -->",
                    )
                )
        else:
            lines.extend(
                (
                    "",
                    "- additional_read: `none`",
                    f"- reason: {packet['l1_empty_reason']}",
                )
            )
    conditional = packet.get("conditional_reads", [])
    if conditional:
        lines.extend(
            (
                "",
                "## L2 · 触发式完整读取",
                "",
                "| 触发器 | 读取 |",
                "|---|---|",
            )
        )
        for item in conditional:
            lines.append(f"| {item['trigger']} | {item['read']} |")
    return "\n".join(lines).rstrip() + "\n"


def finalize_serialized_cost(packet: dict[str, object]) -> None:
    cost = packet["cost"]
    budget = cost["soft_char_budget"]
    for _ in range(12):
        l0_chars = len(render_markdown(packet, include_l1=False))
        combined_chars = len(render_markdown(packet, include_l1=True))
        l0_state = "PASS" if l0_chars <= budget else "REVIEW"
        combined_state = "PASS" if combined_chars <= budget else "REVIEW"
        before = (
            cost["serialized_l0_markdown_chars"],
            cost["serialized_l0_plus_l1_markdown_chars"],
            cost["l0_budget_state"],
            cost["l0_plus_l1_budget_state"],
        )
        after = (
            l0_chars,
            combined_chars,
            l0_state,
            combined_state,
        )
        cost["serialized_l0_markdown_chars"] = l0_chars
        cost["serialized_l0_plus_l1_markdown_chars"] = combined_chars
        cost["l0_budget_state"] = l0_state
        cost["l0_plus_l1_budget_state"] = combined_state
        if after == before:
            return
    raise ContextPacketError("serialized Markdown cost did not converge")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    parser = argparse.ArgumentParser(
        description="Build a read-only exact-excerpt learning context packet.",
    )
    parser.add_argument(
        "--course",
        help="Course ID. Omit to use memory's 当前课程 pointer.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json", "stats"),
        default="markdown",
    )
    parser.add_argument(
        "--soft-char-budget",
        type=int,
        default=DEFAULT_SOFT_CHAR_BUDGET,
    )
    parser.add_argument(
        "--include-l1",
        action="store_true",
        help="Append direct evidence for the first teaching step.",
    )
    args = parser.parse_args()
    if args.soft_char_budget <= 0:
        print("[FAIL] --soft-char-budget must be positive")
        return 2
    try:
        packet = build_packet(
            ROOT,
            course_id=args.course,
            soft_char_budget=args.soft_char_budget,
        )
    except (
        ActivityContractError,
        ContextPacketError,
        TeacherContractError,
    ) as exc:
        errors = getattr(exc, "errors", (str(exc),))
        for error in errors:
            print(f"[FAIL] context packet: {error}")
        return 1
    if args.format == "json":
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2))
    elif args.format == "stats":
        payload = {
            "status": packet["status"],
            "course_id": packet.get("course_id"),
            "memory_current_course": packet.get("memory_current_course"),
            "context_mode": packet.get("context_mode"),
            "group_id": packet.get("group_id"),
            "route": packet.get("route"),
            "cost": packet.get("cost"),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(
            render_markdown(packet, include_l1=args.include_l1),
            end="",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
