#!/usr/bin/env python3
"""Refresh T2AG 0.2.2 derived state.

Default and ``--check`` are read-only.  Only ``--write`` changes GENERATED
blocks.  Cloud projections are always skipped while the bridge is paused.
"""
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import operator_result

from t2ag_activity import (
    ActivityContractError,
    ProgressSnapshot,
    TeacherContractError,
    resolve_activity,
    resolve_teacher_mapping,
    validate_progress_identity,
)


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"
START = "<!-- T2AG_GENERATED:{name}:START -->"
END = "<!-- T2AG_GENERATED:{name}:END -->"


@dataclass
class Course:
    course_id: str
    name: str
    lifecycle: str
    current_activity: str
    activity_id: str
    resume_path: str
    lesson_context: str
    lesson_context_path: str
    position: str
    updated: str
    node: str
    checkpoint: str
    checkpoint_state: str
    next_action: str
    path: Path
    # Raw progress.md text from the single read in discover_courses.  Carried on
    # the dataclass so planned_progress_projections never re-reads the file:
    # test_state_refresh_activity_roundtrip asserts exactly one read per
    # planned_updates() call, and a second read could tear against a concurrent
    # classroom write (observed 2026-08-07 13:54, see P-0058).
    content: str = ""


@dataclass
class Group:
    group_id: str
    status: str
    courses: list[str]
    engagements: list[str]
    current_course: str
    path: Path


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_atomic(path: Path, content: str) -> None:
    tmp = path.with_name(path.name + ".tmp-state")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def frontmatter(content: str) -> dict[str, str]:
    if not content.startswith("---"):
        return {}
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


def course_name(
    course_md: Path,
    course_id: str,
    *,
    reader: Callable[[Path], str] = read,
) -> str:
    if not course_md.exists():
        return course_id
    content = reader(course_md)
    meta = frontmatter(content)
    if meta.get("name"):
        return meta["name"]
    h1 = re.search(r"^#\s+(?:\S+\s+)?(.+?)(?:\s+Course)?\s*$", content, re.MULTILINE)
    return h1.group(1).strip() if h1 else course_id


def next_action(content: str) -> str:
    for pattern in (
        r"^\s*-\s*\*\*下一步计划\*\*[：:]\s*(.+)$",
        r"^\s*-\s*\*\*下次第一件事\*\*[：:]\s*(.+)$",
        r"^next_action:\s*(.+)$",
    ):
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return "—"


CHECKPOINT_TABLE_HEADER = "| checkpoint_id "
OPEN_CHECKPOINT_STATES = ("pending", "arrived", "queued")


def has_checkpoint_table(progress_content: str) -> bool:
    """True when progress.md carries a checkpoint table header."""
    return any(
        line.strip().startswith(CHECKPOINT_TABLE_HEADER)
        for line in progress_content.splitlines()
    )


def derive_current_checkpoint(
    progress_content: str,
    *,
    strict: bool = False,
) -> tuple[str, str]:
    """Derive (current_checkpoint, checkpoint_state) from the checkpoint table.

    The checkpoint table inside progress.md is the authoritative source.
    Frontmatter values are GENERATED projections and are overwritten by
    ``--write``.

    Rules:
    - Scan the checkpoint table rows in order.
    - Return the first checkpoint whose status is ``pending``, ``arrived``,
      or ``queued``.
    - If no such row exists, return ``("none", "none")``.
    - ``confirmed`` and ``archived`` checkpoints are never selected as current.

    ``strict`` makes parse failures fail closed (P-0058).  Without it, "table
    missing or unparseable" and "table present, zero open rows" both collapse to
    ``("none", "none")`` -- harmless while the value only fed display caches, but
    unsafe now that ``--write`` projects it into the progress frontmatter: a
    parser regression would silently blank the pointer instead of failing the
    run.  Callers that are about to *write* the result must pass ``strict=True``
    and gate on :func:`has_checkpoint_table` first, because a freshly
    initialised course legitimately has the frontmatter keys (from
    ``_templates/course/progress.md.template``) before any table exists.

    A header with zero data rows is *not* an error -- that is the legitimate
    bootstrap state before the first checkpoint is recorded.
    """
    in_table = False
    header_seen = False
    malformed: list[str] = []
    for line in progress_content.splitlines():
        stripped = line.strip()
        if stripped.startswith(CHECKPOINT_TABLE_HEADER):
            in_table = True
            header_seen = True
            continue
        if not in_table:
            continue
        if stripped.startswith("|---"):
            continue
        if not stripped.startswith("| "):
            in_table = False
            continue
        cols = [c.strip() for c in stripped.split("|")]
        if len(cols) < 6:
            malformed.append(stripped[:80])
            continue
        ckpt_id = cols[1]
        status = cols[-1] if cols[-1] else cols[-2]
        if status in OPEN_CHECKPOINT_STATES:
            return (ckpt_id, status)
    if strict:
        if not header_seen:
            raise ValueError(
                "checkpoint 表缺失：未找到以 "
                f"`{CHECKPOINT_TABLE_HEADER}` 开头的表头"
            )
        if malformed:
            raise ValueError(
                f"checkpoint 表有 {len(malformed)} 行列数异常（需 ≥6 列），"
                f"首行：{malformed[0]}"
            )
    return ("none", "none")


def replace_frontmatter_fields(content: str, fields: dict[str, str]) -> str:
    """Replace whole frontmatter lines for ``fields``, byte-preserving elsewhere.

    Only the matched key lines change; order, indentation, comments, blank lines
    and every other field survive untouched.  A missing key raises instead of
    being appended -- absent required keys are a doctor FAIL
    (``check_course_routes`` ongoing branch), not something this tool backfills.
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("progress.md 缺少 frontmatter 起始分隔符")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("progress.md 缺少 frontmatter 结束分隔符")
    remaining = dict(fields)
    for index in range(1, end):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):", lines[index])
        if not match:
            continue
        key = match.group(1)
        if key in remaining:
            lines[index] = f"{key}: {remaining.pop(key)}"
    if remaining:
        raise ValueError(
            f"progress.md frontmatter 缺少字段：{sorted(remaining)}"
        )
    return "\n".join(lines)


def explicit_or_dash(value: str | None) -> str:
    normalized = (value or "").strip()
    return normalized if normalized else "—"


def activity_label(course: Course | None, separator: str = ": ") -> str:
    if course is None:
        return f"—{separator}—"
    return f"{course.current_activity}{separator}{course.activity_id}"


def discover_courses(
    root: Path | None = None,
    *,
    reader: Callable[[Path], str] = read,
    exists: Callable[[Path], bool] | None = None,
) -> dict[str, Course]:
    root = (root or ROOT).resolve()
    result: dict[str, Course] = {}
    course_root = root / "main/40_course"
    if not course_root.exists():
        return result
    for folder in sorted(path for path in course_root.iterdir() if path.is_dir() and not path.name.startswith("_")):
        progress = folder / "progress.md"
        if not progress.exists():
            continue
        content = reader(progress)
        meta = frontmatter(content)
        snapshot = ProgressSnapshot(progress, content, meta)
        course_id = folder.name
        try:
            validate_progress_identity(meta, course_id)
        except ActivityContractError as exc:
            raise ValueError(
                f"{course_id} progress identity contract: {'; '.join(exc.errors)}"
            ) from exc
        lifecycle = meta.get("lifecycle_status", "unknown")
        if lifecycle == "ongoing":
            try:
                route = resolve_activity(
                    root,
                    folder.name,
                    snapshot,
                    reader=reader,
                    exists=exists,
                )
            except ActivityContractError as exc:
                raise ValueError(
                    f"{folder.name} explicit activity contract: {'; '.join(exc.errors)}"
                ) from exc
            current_activity = route.activity_type
            activity_id = route.activity_id
            resume_path = route.resume_path
            lesson_context = route.lesson_context_label
            lesson_context_path = route.lesson_context_path
        else:
            current_activity = explicit_or_dash(meta.get("current_activity"))
            activity_id = explicit_or_dash(meta.get("current_activity_id"))
            resume_path = meta.get("resume_path", "")
            lesson_context = "无"
            lesson_context_path = ""
        derived_ckpt, derived_state = derive_current_checkpoint(content)
        result[course_id] = Course(
            course_id=course_id,
            name=course_name(folder / "course.md", course_id, reader=reader),
            lifecycle=lifecycle,
            current_activity=current_activity,
            activity_id=activity_id,
            resume_path=resume_path,
            lesson_context=lesson_context,
            lesson_context_path=lesson_context_path,
            position=(
                route.activity_position
                if lifecycle == "ongoing"
                else meta.get("activity_position", "—")
            ),
            updated=meta.get("updated", "—"),
            node=meta.get("current_completion_node", "—"),
            checkpoint=derived_ckpt if derived_ckpt != "none" else "—",
            checkpoint_state=derived_state if derived_state != "none" else "—",
            next_action=next_action(content),
            path=progress,
            content=content,
        )
    return result


def discover_groups(
    root: Path | None = None,
    *,
    reader: Callable[[Path], str] = read,
) -> dict[str, Group]:
    root = (root or ROOT).resolve()
    result: dict[str, Group] = {}
    group_root = root / "main/30_group"
    if not group_root.exists():
        return result
    for folder in sorted(path for path in group_root.iterdir() if path.is_dir() and re.fullmatch(r"G\d+", path.name)):
        plan = folder / "plan.md"
        if not plan.exists():
            continue
        meta = frontmatter(reader(plan))
        group_id = meta.get("group_id", folder.name)
        result[group_id] = Group(
            group_id=group_id,
            status=meta.get("status", "unknown"),
            courses=list_value(meta.get("course_members", "[]")),
            engagements=list_value(meta.get("engagement_members", "[]")),
            current_course=meta.get("current_course", ""),
            path=plan,
        )
    return result


def active_group(groups: dict[str, Group]) -> Group | None:
    active = [group for group in groups.values() if group.status == "active"]
    return active[0] if len(active) == 1 else None


def render_active(course: Course | None) -> str:
    if course is None:
        return (
            "- **日期**：—\n- **学到哪**：—\n- **当前完成节点**：`—`\n"
            "- **当前 checkpoint**：`—`（—）\n- **来源**：local\n"
            "- **下次第一件事**：—"
        )
    activity = activity_label(course, " ")
    return "\n".join([
        f"- **日期**：{course.updated}",
        f"- **学到哪**：{course.course_id} {activity}，{course.position}",
        f"- **当前完成节点**：`{course.node}`",
        f"- **当前 checkpoint**：`{course.checkpoint}`（{course.checkpoint_state}）",
        "- **来源**：local",
        f"- **下次第一件事**：{course.next_action}",
    ])


def teacher_template(
    course: Course | None,
    mapping: dict[str, tuple[str, str]],
) -> str:
    if course is None:
        return "—"
    resolved = mapping.get(course.course_id)
    return f"TR01 → {resolved[0]}" if resolved else "—"


# Keep in sync with t2ag_doctor.extract_runtime_version: main/t2ag.md §7 is the
# single truth source for the running version.  Never hardcode a literal here —
# a hardcoded value would be written and re-checked from the same constant, so
# `--check` could never observe the drift.
RUNTIME_VERSION_PATTERNS = (
    r"当前运行版本[：:]\s*`?(0\.\d+\.\d+)`?",
    r"-\s*当前版本[：:]\s*`?(0\.\d+\.\d+)`?",
    r"^#\s+T2AG\s+(0\.\d+\.\d+)\b",
)


def runtime_version(
    main: Path,
    *,
    reader: Callable[[Path], str] = read,
) -> str:
    """Parse the declared runtime version from main/t2ag.md, else '—'."""
    constitution = main / "t2ag.md"
    if not constitution.exists():
        return "—"
    text = reader(constitution)
    for pattern in RUNTIME_VERSION_PATTERNS:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(1)
    return "—"


def render_state_pointers(
    group: Group | None,
    course: Course | None,
    teacher_mapping: dict[str, tuple[str, str]],
    *,
    root: Path | None = None,
    reader: Callable[[Path], str] = read,
) -> str:
    root = (root or ROOT).resolve()
    main = root / "main"
    profile = main / "10_student/profile/profile.md"
    profile_status = (
        frontmatter(reader(profile)).get("initialization_status", "—")
        if profile.exists() else "—"
    )
    group_id = group.group_id if group else "—"
    group_path = (
        f"`main/30_group/{group_id}/plan.md`"
        if group else "首次启动后创建"
    )
    course_id = course.course_id if course else "—"
    course_path = (
        f"`main/40_course/{course_id}/progress.md`"
        if course else "首次启动后创建"
    )
    activity = course.current_activity if course else "—"
    activity_value = course.activity_id if course else "—"
    activity_path = f"`{course.resume_path}`" if course and course.resume_path else "—"
    lesson_context = course.lesson_context if course else "无"
    lesson_context_path = (
        f"`{course.lesson_context_path}`"
        if course and course.lesson_context_path else "—"
    )
    bindings: list[str] = []
    if group:
        binding_root = main / f"30_group/{group.group_id}/bindings"
        for path in sorted(binding_root.glob("*.md")) if binding_root.exists() else []:
            if path.name.startswith("_"):
                continue
            if frontmatter(reader(path)).get("binding_status") == "active":
                bindings.append(path.stem)
    binding_value = ", ".join(bindings) or "无"
    binding_path = (
        f"`main/30_group/{group.group_id}/bindings/`"
        if group else "首次启动后创建"
    )
    cloud = "paused" if cloud_paused(root, reader=reader) else "not-paused"
    return "\n".join((
        "| 项目 | 当前值 | 详情位置 |",
        "|---|---|---|",
        f"| 活跃课程组 | {group_id} | {group_path} |",
        f"| 当前课程 | {course_id} | {course_path} |",
        f"| Lesson 上下文 | {lesson_context} | {lesson_context_path} |",
        f"| 当前教学活动 | {activity}: {activity_value} | {activity_path} |",
        f"| 当前教师 | {teacher_template(course, teacher_mapping)} | `main/20_teacher/overlay.md` |",
        f"| 学生档案 | {profile_status} | `main/10_student/profile/profile.md` |",
        f"| active binding | {binding_value} | {binding_path} |",
        f"| T2AG 版本 | {runtime_version(main, reader=reader)} | `main/t2ag.md` |",
        f"| Cloud bridge | {cloud} | `cloud/cloud_sync_state.md` |",
    ))


def capacity(course_id: str, groups: dict[str, Group]) -> str:
    memberships = [
        (group.group_id, group.status)
        for group in groups.values() if course_id in group.courses
    ]
    active = [gid for gid, status in memberships if status == "active"]
    planned = [gid for gid, status in memberships if status == "planned"]
    if active:
        return f"focused_in_{active[0]}"
    if planned:
        return f"queued_for_{planned[0]}"
    return "unallocated"


def render_course_index(courses: dict[str, Course], groups: dict[str, Group]) -> str:
    rows = [
        "| 课程代码 | 课程名称 | 路径 | 生命周期 | 容量状态 | 当前进度 | 恢复入口 |",
        "|---|---|---|---|---|---|---|",
    ]
    for course in courses.values():
        rows.append(
            f"| {course.course_id} | {course.name} | `main/40_course/{course.course_id}/` "
            f"| {course.lifecycle} | {capacity(course.course_id, groups)} "
            f"| {course.position.replace('|', '｜')} "
            f"| `main/40_course/{course.course_id}/progress.md` |"
        )
    return "\n".join(rows)


def render_group_index(groups: dict[str, Group]) -> str:
    rows = [
        "| 课程组 | 路径 | 课程成员 | Engagement 成员 | 状态 |",
        "|---|---|---|---|---|",
    ]
    for group in groups.values():
        rows.append(
            f"| {group.group_id} | `main/30_group/{group.group_id}/plan.md` "
            f"| {' + '.join(group.courses) or '—'} "
            f"| {' + '.join(group.engagements) or '—'} | {group.status} |"
        )
    return "\n".join(rows)


def render_group_view(group: Group, courses: dict[str, Course]) -> str:
    rows = [
        "### 组视图（GENERATED）", "",
        "| 课程 | 当前活动 | 停点 |", "|---|---|---|",
    ]
    for course_id in group.courses:
        course = courses.get(course_id)
        if course:
            rows.append(
                f"| {course_id} | {activity_label(course)} "
                f"| {course.position.replace('|', '｜')} |"
            )
        else:
            rows.append(f"| {course_id} | — | progress.md 不存在 |")
    return "\n".join(rows)


def replace_block(content: str, name: str, body: str) -> str:
    start = START.format(name=name)
    end = END.format(name=name)
    block = f"{start}\n{body.rstrip()}\n{end}"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    matches = pattern.findall(content)
    if len(matches) != 1:
        raise ValueError(f"{name} generated block count must be 1, got {len(matches)}")
    return pattern.sub(lambda _: block, content)


def cloud_paused(
    root: Path | None = None,
    *,
    reader: Callable[[Path], str] = read,
) -> bool:
    root = (root or ROOT).resolve()
    state = root / "cloud/cloud_sync_state.md"
    if not state.exists():
        return False
    content = reader(state)
    return bool(re.search(
        r"^(?:-\s*)?(?:cloud_bridge_status|bridge_status|status):\s*paused\s*$",
        content,
        re.MULTILINE,
    ))


def planned_updates(
    root: Path | None = None,
    *,
    overrides: dict[Path, str] | None = None,
) -> list[tuple[Path, str]]:
    root = (root or ROOT).resolve()
    main = root / "main"
    override_map = {
        path.resolve(): content for path, content in (overrides or {}).items()
    }

    def source_read(path: Path) -> str:
        resolved = path.resolve()
        if resolved in override_map:
            return override_map[resolved]
        return read(path)

    def source_exists(path: Path) -> bool:
        return path.resolve() in override_map or path.is_file()

    courses = discover_courses(root, reader=source_read, exists=source_exists)
    try:
        teacher_mapping = resolve_teacher_mapping(
            root,
            set(courses),
            reader=source_read,
        )
    except TeacherContractError as exc:
        raise ValueError(
            f"teacher mapping contract: {'; '.join(exc.errors)}"
        ) from exc
    groups = discover_groups(root, reader=source_read)
    group = active_group(groups)
    current = None
    if group:
        current_id = group.current_course or (group.courses[0] if group.courses else "")
        current = courses.get(current_id)

    memory = main / "00_core/t2ag_memory.md"
    learning = main / "10_student/profile/learning_path.md"
    updates: list[tuple[Path, str]] = []
    if memory.exists():
        content = replace_block(
            source_read(memory), "ACTIVE_PROGRESS", render_active(current)
        )
        if START.format(name="STATE_POINTERS") in content:
            content = replace_block(
                content,
                "STATE_POINTERS",
                render_state_pointers(
                    group,
                    current,
                    teacher_mapping,
                    root=root,
                    reader=source_read,
                ),
            )
        updates.append((
            memory,
            content,
        ))
    if learning.exists():
        content = source_read(learning)
        content = replace_block(content, "COURSE_INDEX", render_course_index(courses, groups))
        content = replace_block(content, "GROUP_INDEX", render_group_index(groups))
        updates.append((learning, content))
    if group and group.path.exists():
        content = source_read(group.path)
        if START.format(name="GROUP_VIEW") in content:
            updates.append((
                group.path,
                replace_block(content, "GROUP_VIEW", render_group_view(group, courses)),
            ))
    updates.extend(planned_progress_projections(courses))
    return updates


def planned_progress_projections(
    courses: dict[str, Course],
) -> list[tuple[Path, str]]:
    """Project the checkpoint table into each ongoing course's frontmatter.

    Closes P-0058: ``progress_tracking.md`` §2.1 declares
    ``current_checkpoint`` / ``checkpoint_state`` to be GENERATED projections of
    the checkpoint table ("手写无效"), but nothing generated them -- so
    ``--write`` never refreshed them and ``--check`` could not see them drift.
    Adding them to ``updates`` gives the declaration a producer and hands the
    existing ``--check`` its coverage for free.

    Scope rules:
    - ``ongoing`` only.  Non-ongoing progress files carry neither the checkpoint
      table nor the two frontmatter keys (doctor requires them only for
      ``ongoing``).
    - Courses without a checkpoint table are skipped: a freshly initialised
      course has the template's frontmatter keys before any table exists.
    - The literal written for "no open checkpoint" is ``none``, matching
      ``activity_close.py``.  The display-only ``—`` from :func:`discover_courses`
      must never reach the frontmatter, or the two writers would each treat the
      other's value as drift and oscillate forever.

    Uses ``course.content`` from the single read in :func:`discover_courses`
    rather than re-reading, keeping the one-read-per-run contract intact.
    """
    projections: list[tuple[Path, str]] = []
    for course in sorted(courses.values(), key=lambda item: item.course_id):
        if course.lifecycle != "ongoing":
            continue
        content = course.content
        if not has_checkpoint_table(content):
            continue
        derived_ckpt, derived_state = derive_current_checkpoint(content, strict=True)
        projections.append((
            course.path,
            replace_frontmatter_fields(
                content,
                {
                    "current_checkpoint": derived_ckpt,
                    "checkpoint_state": derived_state,
                },
            ),
        ))
    return projections


def _main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()

    try:
        updates = planned_updates()
    except ValueError as exc:
        print(f"[FAIL] generated cache structure: {exc}")
        return 1
    drift = [(path, content) for path, content in updates if read(path) != content]
    if cloud_paused():
        print("state refresh: cloud bridge paused; mobile cache skipped")
    else:
        print("state refresh: cloud bridge not paused; this tool still updates local caches only")
    if args.write:
        for path, content in drift:
            write_atomic(path, content)
        print(f"state refresh: {len(drift)} changed, {len(updates)} checked")
        return 0
    if drift:
        for path, _ in drift:
            print(f"[FAIL] generated cache drift: {path.relative_to(ROOT)}")
        return 1
    print(f"state refresh: 0 changed, {len(updates)} checked")
    return 0


def main() -> int:
    code = _main()
    operator_result.emit_exit(
        tool="state_refresh",
        operation="refresh_or_check",
        exit_code=code,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
