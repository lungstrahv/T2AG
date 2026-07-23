#!/usr/bin/env python3
"""从实例真相源检查/刷新生成缓存；空 skeleton 安全跳过。"""
from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"


def meta(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    block = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not block:
        html = re.search(r"<!-- T2AG_CAPACITY_GROUP(.*?)-->", text, re.DOTALL)
        block_text = html.group(1) if html else ""
    else:
        block_text = block.group(1)
    return dict(re.findall(r"^([a-z_]+):[ \t]*[\"']?(.*?)[\"']?[ \t]*$", block_text, re.MULTILINE))


def values(raw: str) -> list[str]:
    return [x.strip().strip("'\"") for x in raw.strip("[]").split(",") if x.strip()]


def block(name: str, body: str) -> str:
    return f"<!-- T2AG_GENERATED:{name}:START -->\n{body.rstrip()}\n<!-- T2AG_GENERATED:{name}:END -->"


def replace(text: str, name: str, body: str) -> str:
    pattern = re.compile(
        rf"<!-- T2AG_GENERATED:{re.escape(name)}:START -->.*?<!-- T2AG_GENERATED:{re.escape(name)}:END -->",
        re.DOTALL,
    )
    if len(pattern.findall(text)) != 1:
        raise ValueError(f"generated block count must be 1: {name}")
    return pattern.sub(lambda _: block(name, body), text)


def atomic_write(path: Path, text: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def new_path_collision() -> list[str]:
    """同一课程的新旧 CourseRun 同时存在时返回冲突的定义 ID。"""
    new_defs: set[str] = set()
    runs_root = MAIN / "35_course_runs"
    if runs_root.exists():
        for status_path in runs_root.glob("*/CR-*/course_status.md"):
            cr_name = status_path.parent.name
            parts = cr_name.split("-", 2)
            if len(parts) >= 3:
                new_defs.add(parts[2])
    if not new_defs:
        return []
    old_codes: set[str] = set()
    courses_dir = MAIN / "30_courses"
    if courses_dir.exists():
        for path in courses_dir.glob("*/course_status.md"):
            code = meta(path).get("course", "")
            if code:
                old_codes.add(code)
    return sorted(new_defs & old_codes)


def validate_definition(def_id: str, defs_root: Path) -> tuple[bool, str, dict[str, str] | None]:
    """验证 CourseDefinition 正式载体存在性。

    返回 (valid, error_message, parsed_frontmatter_or_None)。
    """
    if not def_id or not defs_root.exists():
        return False, f"CourseDefinition 目录不存在：30_course_definitions/", None
    prefix = f"{def_id}_"
    matches = [dd for dd in defs_root.iterdir() if dd.is_dir() and dd.name.startswith(prefix)]
    if not matches:
        return False, f"CourseDefinition 不存在：{def_id}", None
    if len(matches) > 1:
        return False, f"CourseDefinition 匹配目录重复：{def_id}（{len(matches)} 个目录）", None
    carrier = matches[0] / "course_definition.md"
    if not carrier.exists():
        return False, f"CourseDefinition 缺少正式载体 course_definition.md：{matches[0].name}", None
    try:
        def_meta = meta(carrier)
    except Exception:
        return False, f"CourseDefinition 载体无法解析：{matches[0].name}/course_definition.md", None
    if not def_meta:
        return False, f"CourseDefinition 载体无法解析：{matches[0].name}/course_definition.md", None
    actual_id = def_meta.get("course_definition_id", "")
    if actual_id != def_id:
        return False, f"CourseDefinition 载体 ID 不匹配：期望 {def_id}，实际 {actual_id or 'MISSING'}", None
    return True, "", def_meta


def validate_new_runs() -> list[str]:
    """验证新 CourseRun 身份一致性与引用完整性（全库，不按 Case 过滤）。"""
    errors: list[str] = []
    runs_root = MAIN / "35_course_runs"
    if not runs_root.exists():
        return errors
    defs_root = MAIN / "30_course_definitions"
    students_root = MAIN / "10_case" / "students"
    for status_path in sorted(runs_root.glob("*/CR-*/course_status.md")):
        carrier = meta(status_path)
        cr_name = status_path.parent.name
        phys_case = status_path.parent.parent.name
        parts = cr_name.split("-", 2)
        phys_def_id = parts[2] if len(parts) >= 3 else ""
        # --- 身份一致性验证 ---
        carrier_case = carrier.get("case_id", "")
        carrier_run_id = carrier.get("course_run_id", "")
        carrier_def_id = carrier.get("course_definition_id", "")
        if not carrier_case:
            errors.append(f"CourseRun {cr_name}：载体缺少 case_id")
        elif carrier_case != phys_case:
            errors.append(f"CourseRun {cr_name}：载体 case_id={carrier_case} ≠ 物理路径 {phys_case}")
        if not carrier_run_id:
            errors.append(f"CourseRun {cr_name}：载体缺少 course_run_id")
        elif carrier_run_id != cr_name:
            errors.append(f"CourseRun {cr_name}：载体 course_run_id={carrier_run_id} ≠ 物理路径 {cr_name}")
        if not carrier_def_id:
            errors.append(f"CourseRun {cr_name}：载体缺少 course_definition_id")
        elif carrier_def_id != phys_def_id:
            errors.append(f"CourseRun {cr_name}：载体 course_definition_id={carrier_def_id} ≠ 路径 Definition {phys_def_id}")
        if carrier_case and carrier_def_id and carrier_run_id:
            expected_id = f"CR-{carrier_case}-{carrier_def_id}"
            if carrier_run_id != expected_id:
                errors.append(
                    f"CourseRun {cr_name}：course_run_id 与 CR-<case_id>-<definition_id> 不一致"
                    f"（期望 {expected_id}）")
        # --- 兼容字段 course 验证 ---
        compat_course = carrier.get("course", "")
        canonical_def = carrier_def_id or phys_def_id
        if compat_course and canonical_def and compat_course != canonical_def:
            errors.append(
                f"CourseRun {cr_name}：兼容字段 course={compat_course} "
                f"与正式 course_definition_id={canonical_def} 不一致")
        # --- 引用完整性验证 ---
        def_id = carrier_def_id or phys_def_id
        if def_id:
            valid, err, _ = validate_definition(def_id, defs_root)
            if not valid:
                errors.append(f"CourseRun {cr_name}：{err}")
        case_to_check = carrier_case or phys_case
        if case_to_check and students_root.exists():
            if not (students_root / case_to_check).is_dir():
                errors.append(f"CourseRun {cr_name} 引用的 Case 不存在：{case_to_check}")
    return errors


def resolve_current_case() -> tuple[str, str]:
    """从 student_info.md 解析 SN01 指向的当前 Case。

    返回 (case_id, error)。error 非空表示必须 FAIL。
    """
    si_path = MAIN / "10_case" / "student_info.md"
    students_root = MAIN / "10_case" / "students"
    if si_path.exists():
        content = si_path.read_text(encoding="utf-8-sig", errors="ignore")
        m = re.search(r"指向学生库编号[*\s]*[：:]\s*(S\d+)", content)
        if m:
            sn01 = m.group(1)
            if not (students_root / sn01).is_dir():
                return "", f"SN01 指向的 Case 不存在：{sn01}"
            return sn01, ""
    runs_root = MAIN / "35_course_runs"
    cases: set[str] = set()
    if runs_root.exists():
        for d in runs_root.iterdir():
            if d.is_dir() and not d.name.startswith("_"):
                cases.add(d.name)
    if len(cases) > 1:
        return "", f"无 SN01 且存在多个 Case（{', '.join(sorted(cases))}），无法确定当前 Case"
    if len(cases) == 1:
        return next(iter(cases)), ""
    return "", ""


def expected(current_case: str = "") -> tuple[list[tuple[Path, str, str]], str]:
    """返回 (targets, error)。error 非空表示必须 FAIL。"""
    # 扫描旧路径
    courses = []
    courses_dir = MAIN / "30_courses"
    if courses_dir.exists():
        for path in sorted(courses_dir.glob("*/course_status.md")):
            item = meta(path)
            if item.get("course"):
                item["_folder"] = path.parent.name
                item["_run_dir"] = str(path.parent.relative_to(MAIN)).replace("\\", "/")
                item["_source"] = "old"
                courses.append(item)
    # 扫描新路径
    runs_root = MAIN / "35_course_runs"
    if runs_root.exists():
        for status_path in sorted(runs_root.glob("*/CR-*/course_status.md")):
            item = meta(status_path)
            run_dir = status_path.parent
            cr_name = run_dir.name
            case_id = run_dir.parent.name
            parts = cr_name.split("-", 2)
            def_id = parts[2] if len(parts) >= 3 else ""
            item.setdefault("course", def_id)
            item["_folder"] = cr_name
            item["_run_dir"] = str(run_dir.relative_to(MAIN)).replace("\\", "/")
            item["_source"] = "new"
            item["_case_id"] = case_id
            item["_canonical_def"] = def_id
            courses.append(item)
    # 按当前 Case 过滤
    if current_case:
        filtered = []
        for c in courses:
            if c.get("_source") == "old":
                student = c.get("student", "")
                if not student or student == current_case:
                    filtered.append(c)
            elif c.get("_source") == "new":
                if c.get("_case_id", "") == current_case:
                    filtered.append(c)
        courses = filtered
    groups = []
    groups_dir = MAIN / "20_groups"
    if groups_dir.exists():
        for path in sorted(groups_dir.glob("G*.md")):
            item = meta(path)
            if item.get("group"):
                groups.append(item)
    active = next((g for g in groups if g.get("status") == "active"), None)
    if not active:
        return [], ""  # 无 active G → 安全跳过
    code = active.get("current_course") or (values(active.get("course_members", "")) or [""])[0]
    # 使用 canonical Definition ID 匹配（新 Run 用 _canonical_def，旧课程用 course）
    course = next(
        (c for c in courses
         if (c.get("_canonical_def") or c.get("course", "")) == code),
        None)
    if not course:
        return [], (
            f"active G（{active.get('group', '?')}）当前课程 {code} "
            f"在当前 Case（{current_case or '未确定'}）中不存在")
    course_rows = [
        "| 课程代码 | 课程名称 | 路径 | 生命周期 | 当前进度 |",
        "|---|---|---|---|---|",
    ]
    for item in courses:
        run_dir = item.get("_run_dir", f"30_courses/{item['_folder']}")
        course_rows.append(
            f"| {item['course']} | {item.get('course_name', '—')} | "
            f"`main/{run_dir}/` | {item.get('lifecycle_status', 'UNKNOWN')} | "
            f"{item.get('lesson_position', '—')} |"
        )
    group_rows = ["| 课程组 | 课程成员 | 状态 |", "|---|---|---|"]
    for item in groups:
        group_rows.append(
            f"| {item['group']} | {' + '.join(values(item.get('course_members', ''))) or '—'} | "
            f"{item.get('status', 'UNKNOWN')} |"
        )
    progress = "\n".join(
        [
            f"- **日期**：{course.get('updated', '—')}",
            f"- **学到哪**：{course.get('lesson_position', '—')}",
            f"- **当前完成节点**：`{course.get('current_completion_node', '—')}`",
            f"- **当前 checkpoint**：`{course.get('current_checkpoint', '—')}`（{course.get('checkpoint_state', '—')}）",
            f"- **下次第一件事**：{course.get('next_action', '—')}",
        ]
    )
    lesson = course.get("current_lesson", "")
    lesson_body = (
        f"> **当前教学进度（机器生成）**：{course.get('lesson_position', '—')}\n"
        f"> completion node：`{course.get('current_completion_node', '—')}`；"
        f"checkpoint：`{course.get('current_checkpoint', '—')}`（{course.get('checkpoint_state', '—')}）。"
    )
    run_dir = course.get("_run_dir", f"30_courses/{course['_folder']}")
    return [
        (MAIN / "10_case" / "course_info.md", "COURSE_INDEX", "\n".join(course_rows)),
        (MAIN / "10_case" / "course_info.md", "GROUP_INDEX", "\n".join(group_rows)),
        (MAIN / "00_core" / "t2ag_memory.md", "ACTIVE_PROGRESS", progress),
        (MAIN / run_dir / lesson / f"{lesson}.md", "LESSON_PROGRESS", lesson_body),
    ], ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    # 1. 身份验证先于碰撞检查
    validation_errors = validate_new_runs()
    if validation_errors:
        for err in validation_errors:
            print(f"[FAIL] {err}")
        return 1
    # 2. 碰撞检测（身份已验证，使用物理路径 Definition ID）
    collision = new_path_collision()
    if collision:
        for code in collision:
            print(f"[FAIL] 同一课程新旧 CourseRun 同时存在：{code}（30_courses/ 与 35_course_runs/）")
        return 1
    # 解析当前 Case
    current_case, case_err = resolve_current_case()
    if case_err:
        print(f"[FAIL] {case_err}")
        return 1
    changed = 0
    targets, cache_err = expected(current_case)
    if cache_err:
        print(f"[FAIL] {cache_err}")
        return 1
    for path, name, body in targets:
        if not path.exists():
            print(f"missing target: {path.relative_to(ROOT)}")
            return 1
        old = path.read_text(encoding="utf-8-sig", errors="ignore")
        try:
            new = replace(old, name, body)
        except ValueError as exc:
            print(exc)
            return 1
        if new != old:
            changed += 1
            if args.write:
                atomic_write(path, new)
            else:
                print(f"drift: {path.relative_to(ROOT)}#{name}")
    print(f"state refresh: {changed} changed, {len(targets)} checked")
    return 1 if changed and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
