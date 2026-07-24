#!/usr/bin/env python3
"""从 course_status 与容量组生成 T2AG 运行缓存。

默认只检查；--write 才写入。零第三方依赖，不读取或修改 .venv。
"""
from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"


def scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def list_value(value: str) -> list[str]:
    value = scalar(value).strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    return [item.strip().strip('"\'') for item in value[1:-1].split(",") if item.strip()]


def parse_key_values(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^([a-z][a-z0-9_]*):\s*(.*?)\s*$", line)
        if match:
            result[match.group(1)] = scalar(match.group(2))
    return result


def metadata(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return parse_key_values(text[4:end])
    block = re.search(r"<!-- T2AG_CAPACITY_GROUP\s*(.*?)-->", text, re.DOTALL)
    return parse_key_values(block.group(1)) if block else {}


def generated_block(name: str, body: str) -> str:
    return (
        f"<!-- T2AG_GENERATED:{name}:START -->\n"
        f"{body.rstrip()}\n"
        f"<!-- T2AG_GENERATED:{name}:END -->"
    )


def replace_block(text: str, name: str, body: str) -> str:
    pattern = re.compile(
        rf"<!-- T2AG_GENERATED:{re.escape(name)}:START -->.*?"
        rf"<!-- T2AG_GENERATED:{re.escape(name)}:END -->",
        re.DOTALL,
    )
    replacement = generated_block(name, body)
    if not pattern.search(text):
        raise ValueError(f"missing generated block: {name}")
    return pattern.sub(lambda _: replacement, text, count=1)


def atomic_write(path: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def old_course_records() -> list[dict[str, str]]:
    """扫描旧路径 30_courses/*/course_status.md。"""
    records: list[dict[str, str]] = []
    courses = MAIN / "30_courses"
    if not courses.exists():
        return records
    for path in sorted(courses.glob("*/course_status.md")):
        meta = metadata(path)
        code = meta.get("course", "")
        if not code:
            continue
        meta["_path"] = str(path.relative_to(MAIN)).replace("\\", "/")
        meta["_folder"] = path.parent.name
        meta["_run_dir"] = str(path.parent.relative_to(MAIN)).replace("\\", "/")
        meta["_source"] = "old"
        meta.setdefault("course_definition_id", code)
        meta.setdefault("course_run_id", f"legacy-{code}")
        meta.setdefault("case_id", "")
        records.append(meta)
    return records


def new_course_records() -> list[dict[str, str]]:
    """扫描新路径 35_course_runs/<case_id>/CR-<case_id>-<definition_id>/course_status.md。

    保留载体原始字段，同时记录物理路径值供身份一致性验证。
    """
    records: list[dict[str, str]] = []
    runs_root = MAIN / "35_course_runs"
    if not runs_root.exists():
        return records
    for status_path in sorted(runs_root.glob("*/CR-*/course_status.md")):
        meta = metadata(status_path)
        run_dir = status_path.parent
        phys_case = run_dir.parent.name
        cr_name = run_dir.name  # CR-<case_id>-<definition_id>
        parts = cr_name.split("-", 2)
        phys_def_id = parts[2] if len(parts) >= 3 else ""
        # 物理路径值（不使用 setdefault 或回退值掩盖载体缺失）
        meta["_phys_case"] = phys_case
        meta["_phys_run_id"] = cr_name
        meta["_phys_def_id"] = phys_def_id
        meta["_path"] = str(status_path.relative_to(MAIN)).replace("\\", "/")
        meta["_folder"] = cr_name
        meta["_run_dir"] = str(run_dir.relative_to(MAIN)).replace("\\", "/")
        meta["_source"] = "new"
        # 保存原始兼容字段供身份验证，然后强制 course = canonical Definition ID
        meta["_raw_course"] = meta.get("course", "")
        meta["course"] = phys_def_id
        # 尝试从 CourseDefinition 获取 course_name
        def_id = meta.get("course_definition_id", phys_def_id)
        if def_id:
            defs_root = MAIN / "30_course_definitions"
            if defs_root.exists():
                valid, _, def_meta = validate_definition(def_id, defs_root)
                if valid and def_meta:
                    meta.setdefault("course_name", def_meta.get("name", ""))
        records.append(meta)
    return records


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
        def_meta = metadata(carrier)
    except Exception:
        return False, f"CourseDefinition 载体无法解析：{matches[0].name}/course_definition.md", None
    if not def_meta:
        return False, f"CourseDefinition 载体无法解析：{matches[0].name}/course_definition.md", None
    actual_id = def_meta.get("course_definition_id", "")
    if actual_id != def_id:
        return False, f"CourseDefinition 载体 ID 不匹配：期望 {def_id}，实际 {actual_id or 'MISSING'}", None
    return True, "", def_meta


def validate_identity_consistency(new_recs: list[dict[str, str]]) -> list[str]:
    """验证载体身份字段与物理路径一致。缺失或不一致均 FAIL。

    同时验证兼容字段 course 不得与正式 course_definition_id 冲突。
    """
    errors: list[str] = []
    for rec in new_recs:
        phys_case = rec["_phys_case"]
        phys_run_id = rec["_phys_run_id"]
        phys_def_id = rec["_phys_def_id"]
        carrier_case = rec.get("case_id", "")
        carrier_run_id = rec.get("course_run_id", "")
        carrier_def_id = rec.get("course_definition_id", "")
        # case_id
        if not carrier_case:
            errors.append(f"CourseRun {phys_run_id}：载体缺少 case_id")
        elif carrier_case != phys_case:
            errors.append(f"CourseRun {phys_run_id}：载体 case_id={carrier_case} ≠ 物理路径 {phys_case}")
        # course_run_id
        if not carrier_run_id:
            errors.append(f"CourseRun {phys_run_id}：载体缺少 course_run_id")
        elif carrier_run_id != phys_run_id:
            errors.append(f"CourseRun {phys_run_id}：载体 course_run_id={carrier_run_id} ≠ 物理路径 {phys_run_id}")
        # course_definition_id
        if not carrier_def_id:
            errors.append(f"CourseRun {phys_run_id}：载体缺少 course_definition_id")
        elif carrier_def_id != phys_def_id:
            errors.append(f"CourseRun {phys_run_id}：载体 course_definition_id={carrier_def_id} ≠ 路径 Definition {phys_def_id}")
        # 组合：course_run_id == CR-<case_id>-<course_definition_id>
        if carrier_case and carrier_def_id and carrier_run_id:
            expected_id = f"CR-{carrier_case}-{carrier_def_id}"
            if carrier_run_id != expected_id:
                errors.append(
                    f"CourseRun {phys_run_id}：course_run_id 与 CR-<case_id>-<definition_id> 不一致"
                    f"（期望 {expected_id}）")
        # 兼容字段 course：缺失合法；存在则必须等于 canonical Definition ID
        compat_course = rec.get("_raw_course", "")
        canonical_def = carrier_def_id or phys_def_id
        if compat_course and canonical_def and compat_course != canonical_def:
            errors.append(
                f"CourseRun {phys_run_id}：兼容字段 course={compat_course} "
                f"与正式 course_definition_id={canonical_def} 不一致")
    return errors


def validate_new_records(new_recs: list[dict[str, str]]) -> list[str]:
    """验证新 CourseRun 引用完整性。返回错误列表。"""
    errors: list[str] = []
    defs_root = MAIN / "30_course_definitions"
    students_root = MAIN / "10_case" / "students"
    for rec in new_recs:
        def_id = rec.get("course_definition_id", rec.get("_phys_def_id", ""))
        case_id = rec.get("case_id", rec.get("_phys_case", ""))
        run_id = rec.get("course_run_id", rec.get("_phys_run_id", ""))
        # Definition 正式载体存在性
        if def_id:
            valid, err, _ = validate_definition(def_id, defs_root)
            if not valid:
                errors.append(f"CourseRun {run_id}：{err}")
        # Case 存在性
        if case_id and students_root.exists():
            if not (students_root / case_id).is_dir():
                errors.append(f"CourseRun {run_id} 引用的 Case 不存在：{case_id}")
        elif case_id and not students_root.exists():
            errors.append(f"CourseRun {run_id} 引用的 Case 目录不存在：10_case/students/")
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
            # SN01 必须指向正式 Case 目录
            if not (students_root / sn01).is_dir():
                return "", f"SN01 指向的 Case 不存在：{sn01}"
            return sn01, ""
    # 无 SN01：检查是否存在多个 Case
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


def filter_records_for_case(
    records: list[dict[str, str]], current_case: str
) -> list[dict[str, str]]:
    """过滤记录：旧课程（无 case_id 或 student 匹配）+ 当前 Case 的新 Run。"""
    result: list[dict[str, str]] = []
    for rec in records:
        source = rec.get("_source", "")
        if source == "old":
            # 旧课程使用 frontmatter student 字段识别 Case
            student = rec.get("student", "")
            if not student or student == current_case:
                result.append(rec)
        elif source == "new":
            if rec.get("case_id", "") == current_case:
                result.append(rec)
    return result


def course_records() -> list[dict[str, str]]:
    """统一返回旧+新课程记录（全库，用于验证）。"""
    return old_course_records() + new_course_records()


def group_records() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    folder = MAIN / "20_groups"
    if not folder.exists():
        return records
    for path in sorted(folder.glob("G*.md")):
        meta = metadata(path)
        if not meta:
            continue
        meta["_path"] = str(path.relative_to(MAIN)).replace("\\", "/")
        records.append(meta)
    return records


def capacity_state(code: str, groups: list[dict[str, str]]) -> str:
    active = [
        group.get("group", "")
        for group in groups
        if group.get("status") == "active" and code in list_value(group.get("course_members", "[]"))
    ]
    if active:
        return f"focused_in_{active[0]}"
    queued = [
        group.get("group", "")
        for group in groups
        if group.get("status") == "planned" and code in list_value(group.get("course_members", "[]"))
    ]
    return f"queued_for_{'+'.join(queued)}" if queued else "unallocated"


def active_context(
    courses: list[dict[str, str]], groups: list[dict[str, str]]
) -> tuple[dict[str, str], dict[str, str]] | None:
    active_groups = [group for group in groups if group.get("status") == "active"]
    if not active_groups:
        return None
    group = active_groups[0]
    code = group.get("current_course", "")
    if not code:
        members = list_value(group.get("course_members", "[]"))
        code = members[0] if members else ""
    course = next((item for item in courses if item.get("course") == code), None)
    return (group, course) if course else None


def render_course_index(courses: list[dict[str, str]], groups: list[dict[str, str]]) -> str:
    lines = [
        "| 课程代码 | 课程名称 | 路径 | 生命周期 | 容量状态 | 当前进度 | 恢复关键词 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in courses:
        code = item.get("course", item.get("course_definition_id", ""))
        run_dir = item.get("_run_dir", f"30_courses/{item['_folder']}")
        lines.append(
            f"| {code} | {item.get('course_name', '—')} | "
            f"`main/{run_dir}/` | {item.get('lifecycle_status', 'UNKNOWN')} | "
            f"{capacity_state(code, groups)} | {item.get('lesson_position', '—')} | "
            f"读取 main/{run_dir}/course_status.md |"
        )
    return "\n".join(lines)


def render_group_index(groups: list[dict[str, str]]) -> str:
    lines = [
        "| 课程组 | 路径 | 课程成员 | 实践成员 | 状态 |",
        "|---|---|---|---|---|",
    ]
    for group in groups:
        courses = " + ".join(list_value(group.get("course_members", "[]"))) or "—"
        practices = " + ".join(list_value(group.get("practice_members", "[]"))) or "—"
        lines.append(
            f"| {group.get('group', '—')} | `main/{group['_path']}` | "
            f"{courses} | {practices} | {group.get('status', 'UNKNOWN')} |"
        )
    return "\n".join(lines)


def render_memory_progress(course: dict[str, str]) -> str:
    return "\n".join(
        [
            f"- **日期**：{course.get('updated', '—')}",
            f"- **学到哪**：{course.get('course', '—')} {course.get('current_lesson', '—')}，"
            f"{course.get('lesson_position', '—')}",
            f"- **当前完成节点**：`{course.get('current_completion_node', '—')}`",
            f"- **当前 checkpoint**：`{course.get('current_checkpoint', '—')}`"
            f"（{course.get('checkpoint_state', '—')}）",
            f"- **来源**：{course.get('progress_provenance', 'local')}",
            f"- **下次第一件事**：{course.get('next_action', '—')}",
        ]
    )


def render_lesson_progress(course: dict[str, str]) -> str:
    return (
        f"> **当前教学进度（机器生成）**：{course.get('lesson_position', '—')}"
        f"\n> completion node：`{course.get('current_completion_node', '—')}`；"
        f"checkpoint：`{course.get('current_checkpoint', '—')}`"
        f"（{course.get('checkpoint_state', '—')}）。"
    )


def render_mobile_state(course: dict[str, str], group: dict[str, str]) -> str:
    run_dir = course.get("_run_dir", f"30_courses/{course['_folder']}")
    lesson = course.get("current_lesson", "—")
    return "\n".join(
        [
            f"- base_state_id: {course.get('state_id', 'UNINITIALIZED')}",
            f"- exported_at: {course.get('updated', '—')}",
            f"- course: {course.get('course', '—')}",
            f"- lesson: {lesson}",
            f"- active_capacity_group: {group.get('group', '—')}",
            f"- lifecycle_status: {course.get('lifecycle_status', 'UNKNOWN')}",
            f"- current_completion_node: {course.get('current_completion_node', '—')}",
            f"- current_checkpoint: {course.get('current_checkpoint', '—')}",
            f"- confirmation_state: {course.get('checkpoint_state', '—')}",
            f"- exact_stop: {course.get('lesson_position', '—')}",
            f"- next_first_action: {course.get('next_action', '—')}",
            f"- progress_provenance: {course.get('progress_provenance', 'local')}",
            f"- truth_source: `main/{run_dir}/course_status.md`",
            f"- lesson_source: `main/{run_dir}/{lesson}/{lesson}.md`",
        ]
    )


def expected_updates(current_case: str = "") -> tuple[list[tuple[Path, str, str]], str]:
    """返回 (updates, error)。error 非空表示必须 FAIL。"""
    all_courses = course_records()
    groups = group_records()
    # 缓存生成只使用当前 Case 的记录
    if current_case:
        courses = filter_records_for_case(all_courses, current_case)
    else:
        courses = all_courses
    # 区分「无 active G」和「active G 但当前课程不在当前 Case」
    active_groups = [g for g in groups if g.get("status") == "active"]
    if not active_groups:
        return [], ""  # 无 active G → 安全跳过
    group = active_groups[0]
    code = group.get("current_course", "")
    if not code:
        members = list_value(group.get("course_members", "[]"))
        code = members[0] if members else ""
    course = next((item for item in courses if item.get("course") == code), None)
    if not course:
        return [], (
            f"active G（{group.get('group', '?')}）当前课程 {code} "
            f"在当前 Case（{current_case or '未确定'}）中不存在")
    lesson = course.get("current_lesson", "")
    run_dir = course.get("_run_dir", f"30_courses/{course['_folder']}")
    return [
        (
            MAIN / "10_case" / "course_info.md",
            "COURSE_INDEX",
            render_course_index(courses, groups),
        ),
        (
            MAIN / "10_case" / "course_info.md",
            "GROUP_INDEX",
            render_group_index(groups),
        ),
        (
            MAIN / "00_core" / "t2ag_memory.md",
            "ACTIVE_PROGRESS",
            render_memory_progress(course),
        ),
        (
            MAIN / run_dir / lesson / f"{lesson}.md",
            "LESSON_PROGRESS",
            render_lesson_progress(course),
        ),
        (
            ROOT / "cloud" / "t2ag_mobile_entry.md",
            "MOBILE_STATE",
            render_mobile_state(course, group),
        ),
    ], ""


def run(write: bool) -> int:
    old_recs = old_course_records()
    new_recs = new_course_records()
    # 1. 载体身份与物理路径一致性验证（全库，先于碰撞检查）
    identity_errors = validate_identity_consistency(new_recs)
    if identity_errors:
        for err in identity_errors:
            print(f"[FAIL] {err}")
        return 1
    # 2. 身份验证通过后，强制规范化字段（canonical Definition ID）
    for rec in new_recs:
        rec["case_id"] = rec["_phys_case"]
        rec["course_run_id"] = rec["_phys_run_id"]
        rec["course_definition_id"] = rec["_phys_def_id"]
        # course 字段强制为已验证的 canonical ID，不信任原始载体值
        rec["course"] = rec["_phys_def_id"]
    # 3. 碰撞检测：使用已验证的 canonical Definition ID
    old_defs = {rec.get("course_definition_id", rec.get("course", "")) for rec in old_recs}
    new_defs = {rec["_phys_def_id"] for rec in new_recs}
    collision = sorted(old_defs & new_defs - {""})
    if collision:
        for code in collision:
            print(f"[FAIL] 同一课程新旧 CourseRun 同时存在：{code}（30_courses/ 与 35_course_runs/）")
        return 1
    # 新 CourseRun 引用验证（全库，不按 Case 过滤）
    validation_errors = validate_new_records(new_recs)
    if validation_errors:
        for err in validation_errors:
            print(f"[FAIL] {err}")
        return 1
    # 解析当前 Case
    current_case, case_err = resolve_current_case()
    if case_err:
        print(f"[FAIL] {case_err}")
        return 1
    updates, cache_err = expected_updates(current_case)
    if cache_err:
        print(f"[FAIL] {cache_err}")
        return 1
    if not updates:
        print("state refresh: no active capacity group; skipped")
        return 0
    errors: list[str] = []
    staged: dict[Path, str] = {}
    for path, name, body in updates:
        if not path.exists():
            errors.append(f"missing target: {path}")
            continue
        current = staged.get(path, path.read_text(encoding="utf-8", errors="ignore"))
        try:
            expected = replace_block(current, name, body)
        except ValueError as exc:
            errors.append(f"{path}: {exc}")
            continue
        staged[path] = expected
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    changed = [path for path, expected in staged.items() if path.read_text(encoding="utf-8") != expected]
    if changed and not write:
        for path in changed:
            print(f"[FAIL] generated cache drift: {path.relative_to(ROOT)}")
        return 1
    if write:
        for path in changed:
            atomic_write(path, staged[path])
            print(f"[WRITE] {path.relative_to(ROOT)}")
    print(f"state refresh: {len(changed)} changed, {len(staged)} checked")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="refresh generated blocks")
    parser.add_argument("--check", action="store_true", help="explicit read-only check (default)")
    args = parser.parse_args()
    return run(write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
