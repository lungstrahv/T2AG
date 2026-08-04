#!/usr/bin/env python3
"""Zero-dependency contract tests plus a real-disk T2AG 0.2.1 CLI roundtrip."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import t2ag_activity as activity
import t2ag_hint_gate as hint_gate


SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parents[2]
spec = importlib.util.spec_from_file_location("t2ag_doctor_under_test", SCRIPT.with_name("t2ag_doctor.py"))
doctor = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(doctor)

state_spec = importlib.util.spec_from_file_location(
    "t2ag_state_refresh_under_test",
    SCRIPT.with_name("t2ag_state_refresh.py"),
)
state_refresh = importlib.util.module_from_spec(state_spec)
assert state_spec and state_spec.loader
sys.modules[state_spec.name] = state_refresh
state_spec.loader.exec_module(state_refresh)

candidate_spec = importlib.util.spec_from_file_location(
    "t2ag_candidate_replay_under_test",
    SCRIPT.with_name("t2ag_candidate_replay.py"),
)
candidate_replay = importlib.util.module_from_spec(candidate_spec)
assert candidate_spec and candidate_spec.loader
sys.modules[candidate_spec.name] = candidate_replay
candidate_spec.loader.exec_module(candidate_replay)

migration_021_spec = importlib.util.spec_from_file_location(
    "migrate_021_under_test",
    SCRIPT.with_name("migrate_021.py"),
)
migration_021 = importlib.util.module_from_spec(migration_021_spec)
assert migration_021_spec and migration_021_spec.loader
migration_021_spec.loader.exec_module(migration_021)


def write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_teacher_mapping(root: Path, course_ids: tuple[str, ...]) -> None:
    for template_id in ("T001", "T002", "T003"):
        template = root / f"main/20_teacher/{template_id}.md"
        if not template.is_file():
            write(
                template,
                "---\ntype: teacher_template\n"
                f"template_id: {template_id}\nstatus: active\n---\n"
                f"# {template_id}\n",
            )
    rows = "\n".join(
        f"| {course_id} | Test Course | `main/20_teacher/T001.md` | test |"
        for course_id in course_ids
    )
    write(
        root / "main/20_teacher/overlay.md",
        "# Teacher overlay\n\n## 课程—教师映射\n\n"
        "| 课程代码 | 课程名称 | 教师模板 | 教师风格 |\n"
        "|---|---|---|---|\n"
        f"{rows}\n"
        "| (默认) | 其他/未指定课程 | `main/20_teacher/T001.md` | default |\n",
    )


def write_textbook_source_contract(
    root: Path,
    course_id: str,
    exercise_id: str,
    content_group_id: str,
    statement: str,
) -> str:
    artifact_id = f"{course_id}_{exercise_id}_SOURCE"
    relative = (
        f"main/40_course/{course_id}/book/primary/verified_excerpts/"
        f"{exercise_id.lower()}_source.md"
    )
    document_relative = (
        f"main/40_course/{course_id}/book/primary/source_documents/"
        f"{exercise_id.lower()}_document.txt"
    )
    document = root / document_relative
    write(document, f"synthetic source document for {course_id}/{exercise_id}\n")
    document_sha = hashlib.sha256(document.read_bytes()).hexdigest()
    source = root / relative
    write(
        source,
        "---\ntype: verified_source_excerpt\n"
        f"artifact_id: {artifact_id}\ncourse_id: {course_id}\n"
        f"content_group_id: {content_group_id}\n"
        f"source_document: {document_relative}\n"
        f"source_document_sha256: {document_sha}\n"
        "source_locator: synthetic problem 1\n"
        "verification_status: synthetic_verified\nverified: 2026-07-26\n"
        "lifecycle: persistent\n---\n# Source\n\n"
        f"## {exercise_id}-Q001\n\n- 教材题号：1\n- 来源页：1\n"
        f"- 题面：{statement}\n",
    )
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    registry_path = root / "main/70_tools/artifact_registry.json"
    payload = (
        json.loads(registry_path.read_text(encoding="utf-8"))
        if registry_path.is_file()
        else {"schema_version": 2, "artifacts": []}
    )
    artifacts = [
        item for item in payload.setdefault("artifacts", [])
        if item.get("artifact_id") != artifact_id
    ]
    artifacts.append({
        "artifact_id": artifact_id,
        "canonical_path": relative,
        "redirects": [],
        "status": "active",
        "migration_reason": "component test",
    })
    payload["artifacts"] = artifacts
    write(
        registry_path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    return (
        f"source_artifact_id: {artifact_id}\n"
        f"source_path: {relative}\n"
        "source_locator: synthetic problem 1\n"
        f"source_sha256: {source_sha}\n"
    )


def write_formal_lite_migration_evidence(
    root: Path,
    document_relative: str,
    document_sha: str,
) -> tuple[Path, Path]:
    manifest_path = root / "main/60_journal/migration_020_operations.json"
    report_path = root / "main/60_journal/migration_020_report.json"
    manifest = {
        "schema_version": "T2AG-MIGRATION-OPERATIONS-1",
        "target_kind": "main",
        "evidence_source": "synthetic formal migration evidence",
        "operation_count": 1,
        "operations": [{
            "sequence": 1,
            "kind": "copy",
            "sources": [{
                "path": "legacy/source_document.txt",
                "bytes": 1,
                "sha256": "1" * 64,
            }],
            "target": document_relative,
            "disposition": "copy verified source document",
            "outcome": "applied",
            "post_target": {
                "path": document_relative,
                "bytes": 1,
                "sha256": document_sha,
            },
        }],
    }
    write(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    report = {
        "status": "applied",
        "applied_count": 1,
        "operation_manifest": {
            "path": "main/60_journal/migration_020_operations.json",
            "operation_count": 1,
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        },
        "current_verification": {
            "pending_count": 0,
            "missing": [],
            "collisions": [],
            "duplicate_active_canonicals": [],
            "unknown_binaries": [],
        },
        "post_apply_duplicate_active_canonicals": [],
    }
    write(
        report_path,
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest_path, report_path


def replace_frontmatter_field(
    content: str,
    field: str,
    value: str,
    *,
    expected: str | None = None,
) -> str:
    old_value = re.escape(expected) if expected is not None else r".*"
    pattern = rf"^{re.escape(field)}:\s*{old_value}\s*$"
    return replace_regex_exactly_once(
        content,
        pattern,
        f"{field}: {value}",
        label=f"frontmatter {field}",
        flags=re.MULTILINE,
    )


def replace_regex_exactly_once(
    content: str,
    pattern: str,
    replacement: str,
    *,
    label: str,
    flags: int = 0,
) -> str:
    matches = list(re.finditer(pattern, content, flags))
    if len(matches) != 1:
        raise AssertionError(
            f"regex replacement must match exactly once: {label}; "
            f"actual={len(matches)}"
        )
    return re.sub(pattern, replacement, content, count=1, flags=flags)


def replace_exactly_once(
    content: str,
    old: str,
    new: str,
    *,
    label: str,
) -> str:
    if content.count(old) != 1:
        raise AssertionError(
            f"text replacement must match exactly once: {label}"
        )
    return content.replace(old, new, 1)


def reset(root: Path, flavor: str = "main") -> None:
    doctor.ROOT = root
    doctor.MAIN = root / "main"
    doctor.FLAVOR = flavor
    doctor.COURSE_SNAPSHOTS.clear()
    doctor.COURSE_ROUTES.clear()
    doctor.fails.clear()
    doctor.warns.clear()
    doctor.infos.clear()


def reset_state(root: Path) -> None:
    state_refresh.ROOT = root
    state_refresh.MAIN = root / "main"


def run_silently(function, *args) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        function(*args)


def assert_message(collection: list[str], token: str) -> None:
    if not any(token in message for message in collection):
        raise AssertionError(f"expected diagnostic containing {token!r}; actual={collection}")


def test_profile_placeholder(root: Path) -> None:
    reset(root)
    write(root / "README.md", "0.2.1\n")
    write(root / "AGENTS.md", "0.2.1\n")
    write(root / "main/bin/t2ag", "0.2.1\n")
    write(root / "main/t2ag.md", "0.2.1\n")
    write(root / "main/00_core/t2ag_memory.md", "0.2.1\n")
    write(
        root / "main/10_student/profile/profile.md",
        "---\ninitialization_status: initialized\n---\n"
        "## 每周可投入学习时间\n- （待填写）\n"
        "## 学习目标\n- [ ] （待填写）\n"
        "## 编程基础\n- （待填写）\n"
        "## 期望的辅导方式\n- （待填写）\n",
    )
    run_silently(doctor.check_version_and_profile)
    assert_message(doctor.fails, "必填占位符")
    assert_message(doctor.fails, "必填信息未确认")


def test_profile_container_contract(root: Path) -> None:
    def build(case_root: Path) -> None:
        for domain in doctor.EXPECTED_DOMAINS:
            (case_root / "main" / domain).mkdir(parents=True, exist_ok=True)
        write(case_root / "main/t2ag.md", "0.2.1\n")
        write(case_root / "main/80_interface/fable_snail.png", "fixture\n")
        for name in ("profile.md", "learning_path.md", "course_reflections.md", "reasoning_patterns.md"):
            write(case_root / "main/10_student/profile" / name, f"# {name}\n")
        (case_root / "main/10_student/activities").mkdir(parents=True, exist_ok=True)
        (case_root / "main/10_student/engagements").mkdir(parents=True, exist_ok=True)

    valid = root / "valid"
    build(valid)
    reset(valid)
    run_silently(doctor.check_structure)
    if doctor.fails:
        raise AssertionError(f"valid profile container rejected: {doctor.fails}")

    legacy = root / "legacy"
    build(legacy)
    write(legacy / "main/10_student/profile.md", "# legacy\n")
    reset(legacy)
    run_silently(doctor.check_structure)
    assert_message(doctor.fails, "旧学生档案顶层文件仍存在")
    assert_message(doctor.fails, "必须且只能存在一份")

    duplicate = root / "duplicate"
    build(duplicate)
    write(duplicate / "main/10_student/activities/profile.md", "# duplicate\n")
    reset(duplicate)
    run_silently(doctor.check_structure)
    assert_message(doctor.fails, "必须且只能存在一份")

    missing = root / "missing"
    build(missing)
    (missing / "main/10_student/profile/reasoning_patterns.md").unlink()
    reset(missing)
    run_silently(doctor.check_structure)
    assert_message(doctor.fails, "reasoning_patterns.md")

    extra = root / "extra"
    build(extra)
    (extra / "main/10_student/misc").mkdir()
    reset(extra)
    run_silently(doctor.check_structure)
    assert_message(doctor.fails, "10_student 顶层目录不等于")


def test_resume_path(root: Path) -> None:
    reset(root)
    write(
        root / "main/40_course/TEST1001/course.md",
        "---\ntype: course\ncourse_id: TEST1001\ncourse_type: mastery\n"
        "default_driver: textbook\nstatus: active\n---\n",
    )
    write(
        root / "main/40_course/TEST1001/progress.md",
        "---\ntype: course_progress\ncourse_id: TEST1001\nlifecycle_status: ongoing\n"
        "course_driver: textbook\ntruth_source: true\ncurrent_lesson: lesson01\n"
        "current_activity: exercise\ncurrent_activity_id: U0001\n"
        "resume_path: main/40_course/TEST1001/exercises/U0001/missing.md\n"
        "activity_position: start\nupdated: 2026-07-26\n"
        "current_completion_node: TEST1001-N01\n"
        "current_checkpoint: TEST1001-N01-S01\ncheckpoint_state: queued\n"
        "next_action: continue\n---\n",
    )
    run_silently(doctor.discover_courses)
    assert_message(doctor.fails, "resume_path 非 canonical")
    assert_message(doctor.fails, "resume_path 悬空")


def test_explicit_activity_pointer_required(root: Path) -> None:
    reset(root)
    course = root / "main/40_course/TEST1001"
    write(
        course / "course.md",
        "---\ntype: course\ncourse_id: TEST1001\nschool_course_code: TEST1001\n"
        "name: Test Course\ncourse_type: mastery\ndefault_driver: goal\n"
        "prerequisites: []\nstatus: active\n---\n",
    )
    write(
        course / "progress.md",
        "---\ntype: course_progress\ncourse_id: TEST1001\nlifecycle_status: ongoing\n"
        "course_driver: goal\ntruth_source: true\ncurrent_lesson: lesson01\n"
        "resume_path: main/40_course/TEST1001/lessons/lesson01/lesson01.md\n"
        "activity_position: start\nupdated: 2026-07-26\n"
        "current_completion_node: TEST1001-N01\ncurrent_checkpoint: TEST1001-N01-S01\n"
        "checkpoint_state: queued\nnext_action: continue\n---\n",
    )
    write(
        course / "lessons/lesson01/lesson01.md",
        "---\ntype: lesson\ncourse_id: TEST1001\nlesson_id: lesson01\n---\n"
        "# lesson01\n",
    )
    write(course / "exercises/_README.md", "placeholder\n")
    write(course / "book/README.md", "placeholder\n")
    write(course / "mistake_bank.md", "# Mistakes\n")
    write(course / "question_bank.md", "# Questions\n")
    run_silently(doctor.discover_courses)
    assert_message(doctor.fails, "current_activity")
    assert_message(doctor.fails, "current_activity_id")


def test_exercise_first_course_resume(root: Path) -> None:
    reset(root)
    course = root / "main/40_course/TEST1001"
    write(
        course / "course.md",
        "---\ntype: course\ncourse_id: TEST1001\nschool_course_code: TEST1001\n"
        "name: Test Course\ncourse_type: mastery\ndefault_driver: goal\n"
        "prerequisites: []\nstatus: active\n---\n",
    )
    write(
        course / "progress.md",
        "---\ntype: course_progress\ncourse_id: TEST1001\nlifecycle_status: ongoing\n"
        "course_driver: goal\ntruth_source: true\ncurrent_lesson: none\n"
        "current_activity: exercise\ncurrent_activity_id: U0001\n"
        "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n"
        "activity_position: first exercise\nupdated: 2026-07-26\n"
        "current_completion_node: TEST1001-N01\ncurrent_checkpoint: TEST1001-N01-S01\n"
        "checkpoint_state: queued\nnext_action: solve\n---\n",
    )
    write(course / "lessons/_README.md", "placeholder\n")
    write(
        course / "exercises/U0001/exercise.md",
        "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\n---\n",
    )
    write(
        course / "exercises/U0001/problems.md",
        "---\ntype: exercise_problem_set\ncourse_id: TEST1001\n"
        "exercise_id: U0001\n---\n# Problems\n",
    )
    write(course / "book/README.md", "placeholder\n")
    write(course / "mistake_bank.md", "# Mistakes\n")
    write(course / "question_bank.md", "# Questions\n")
    run_silently(doctor.discover_courses)
    if doctor.fails:
        raise AssertionError(f"valid exercise-first course rejected: {doctor.fails}")


def test_progress_identity_is_shared(root: Path) -> None:
    def build(case_root: Path, lifecycle: str = "ongoing") -> Path:
        course = case_root / "main/40_course/TEST1001"
        write(
            course / "course.md",
            "---\ntype: course\ncourse_id: TEST1001\n"
            "school_course_code: TEST1001\nname: Test Course\n"
            "course_type: mastery\ndefault_driver: goal\n"
            "prerequisites: []\nstatus: active\n---\n",
        )
        if lifecycle == "ongoing":
            activity = (
                "current_lesson: none\ncurrent_activity: exercise\n"
                "current_activity_id: U0001\n"
                "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n"
                "activity_position: start\n"
            )
        else:
            activity = "current_lesson: none\nprogress_nodes_status: lazy_on_activation\n"
        write(
            course / "progress.md",
            "---\ntype: course_progress\ncourse_id: TEST1001\n"
            f"lifecycle_status: {lifecycle}\ncourse_driver: goal\ntruth_source: true\n"
            f"{activity}updated: 2026-07-26\n"
            "current_completion_node: TEST1001-N01\n"
            "current_checkpoint: TEST1001-N01-S01\ncheckpoint_state: queued\n"
            "next_action: continue\n---\n",
        )
        write(
            course / "exercises/U0001/exercise.md",
            "---\ntype: exercise\ncourse_id: TEST1001\n"
            "exercise_id: U0001\n---\n",
        )
        write(
            course / "exercises/U0001/problems.md",
            "---\ntype: exercise_problem_set\ncourse_id: TEST1001\n"
            "exercise_id: U0001\n---\n",
        )
        write(course / "lessons/_README.md", "empty\n")
        write(course / "book/README.md", "book\n")
        write(course / "mistake_bank.md", "# Mistakes\n")
        write(course / "question_bank.md", "# Questions\n")
        return course / "progress.md"

    valid = root / "valid"
    valid_progress = build(valid)
    write(
        valid / "main/10_student/profile/profile.md",
        "---\ninitialization_status: initialized\n---\n",
    )
    write(
        valid / "main/30_group/G01/plan.md",
        "---\ngroup_id: G01\nstatus: active\ncurrent_course: TEST1001\n---\n",
    )
    write(
        valid / "main/00_core/t2ag_memory.md",
        "- **日期**：2026-07-26\n- **学到哪**：single snapshot test\n\n"
        "| 项目 | 当前值 | 详情位置 |\n|---|---|---|\n"
        "| 活跃课程组 | G01 | test |\n"
        "| 当前课程 | TEST1001 | test |\n"
        "| Lesson 上下文 | 无 | test |\n"
        "| 当前教学活动 | exercise: U0001 | test |\n",
    )
    reset(valid)
    original_doctor_read = doctor.read
    progress_reads = 0
    progress_readers: list[str] = []

    def counted_doctor_read(path: Path) -> str:
        nonlocal progress_reads
        if Path(path).resolve() == valid_progress.resolve():
            progress_reads += 1
            progress_readers.append(sys._getframe(1).f_code.co_name)
        return original_doctor_read(path)

    doctor.read = counted_doctor_read
    try:
        courses = doctor.discover_courses()
        run_silently(doctor.check_project_verification, courses)
        run_silently(doctor.check_exercises, courses)
        run_silently(
            doctor.check_memory_pointers,
            courses,
            {"TEST1001": ("T001", "main/20_teacher/T001.md")},
        )
    finally:
        doctor.read = original_doctor_read
    if progress_reads != 1:
        raise AssertionError(
            f"Doctor read one progress {progress_reads} times in a single run: "
            f"{progress_readers}"
        )
    doctor.resolve_activity(valid, "TEST1001")
    reset_state(valid)
    if set(state_refresh.discover_courses()) != {"TEST1001"}:
        raise AssertionError("valid progress identity was not keyed by directory course ID")

    mutations = (
        ("type", "lesson"),
        ("course_id", "OTHER1001"),
        ("truth_source", "false"),
    )
    for field, value in mutations:
        case_root = root / f"invalid_{field}"
        progress = build(case_root)
        content = progress.read_text(encoding="utf-8")
        progress.write_text(
            replace_frontmatter_field(content, field, value),
            encoding="utf-8",
            newline="\n",
        )
        try:
            doctor.resolve_activity(case_root, "TEST1001")
        except doctor.ActivityContractError:
            pass
        else:
            raise AssertionError(f"activity resolver accepted invalid progress {field}")
        reset_state(case_root)
        try:
            state_refresh.discover_courses()
        except ValueError:
            pass
        else:
            raise AssertionError(f"state refresh accepted invalid progress {field}")
        reset(case_root)
        run_silently(doctor.discover_courses)
        assert_message(doctor.fails, "progress 身份契约")

    missing_truth = root / "missing_truth"
    missing_progress = build(missing_truth)
    missing_content = replace_regex_exactly_once(
        missing_progress.read_text(encoding="utf-8"),
        r"^truth_source:.*\n",
        "",
        label="remove truth_source",
        flags=re.MULTILINE,
    )
    missing_progress.write_text(missing_content, encoding="utf-8", newline="\n")
    reset_state(missing_truth)
    try:
        state_refresh.discover_courses()
    except ValueError:
        pass
    else:
        raise AssertionError("state refresh accepted missing truth_source")

    planned = root / "planned_alias"
    planned_progress = build(planned, "planned")
    planned_progress.write_text(
        replace_frontmatter_field(
            planned_progress.read_text(encoding="utf-8"),
            "course_id",
            "OTHER1001",
        ),
        encoding="utf-8",
        newline="\n",
    )
    reset_state(planned)
    try:
        state_refresh.discover_courses()
    except ValueError:
        pass
    else:
        raise AssertionError("planned progress polluted state with an alias course_id")


def test_teacher_mapping_is_strict(root: Path) -> None:
    valid = root / "valid"
    write_teacher_mapping(valid, ("TEST1001",))
    mapping = doctor.resolve_teacher_mapping(valid, {"TEST1001"})
    if mapping["TEST1001"] != ("T001", "main/20_teacher/T001.md"):
        raise AssertionError(f"teacher mapping resolved incorrectly: {mapping}")

    smuggled = root / "smuggled"
    write_teacher_mapping(smuggled, ("TEST1001",))
    overlay = smuggled / "main/20_teacher/overlay.md"
    overlay.write_text(
        replace_exactly_once(
            overlay.read_text(encoding="utf-8"),
            "`main/20_teacher/T001.md` | test",
            "`main/20_teacher/T001.md.bak` | style mentions T001",
            label="teacher token-smuggling fixture",
        ),
        encoding="utf-8",
        newline="\n",
    )
    try:
        doctor.resolve_teacher_mapping(smuggled, {"TEST1001"})
    except doctor.TeacherContractError:
        pass
    else:
        raise AssertionError("teacher resolver accepted a token smuggled through style")

    duplicate = root / "duplicate"
    write_teacher_mapping(duplicate, ("TEST1001",))
    overlay = duplicate / "main/20_teacher/overlay.md"
    overlay.write_text(
        replace_exactly_once(
            overlay.read_text(encoding="utf-8"),
            "| (默认)",
            "| TEST1001 | Duplicate | `main/20_teacher/T002.md` | duplicate |\n"
            "| (默认)",
            label="duplicate teacher mapping fixture",
        ),
        encoding="utf-8",
        newline="\n",
    )
    try:
        doctor.resolve_teacher_mapping(duplicate, {"TEST1001"})
    except doctor.TeacherContractError:
        pass
    else:
        raise AssertionError("teacher resolver accepted a duplicate course row")

    wrong_identity = root / "wrong_identity"
    write_teacher_mapping(wrong_identity, ("TEST1001",))
    template = wrong_identity / "main/20_teacher/T001.md"
    template.write_text(
        replace_frontmatter_field(
            template.read_text(encoding="utf-8"),
            "template_id",
            "T002",
        ),
        encoding="utf-8",
        newline="\n",
    )
    try:
        doctor.resolve_teacher_mapping(wrong_identity, {"TEST1001"})
    except doctor.TeacherContractError:
        pass
    else:
        raise AssertionError("teacher resolver accepted a self-misidentified template")


def test_teacher_presentation_contract(root: Path) -> None:
    write_teacher_mapping(root, ())
    reset(root)
    run_silently(doctor.check_teacher_contract, {})
    assert_message(doctor.fails, "教师模板缺地图优先讲解协议")


def test_fixture_mutations_cannot_silently_noop(root: Path) -> None:
    content = "---\nactivity_position: before\n---\n"
    updated = replace_frontmatter_field(
        content,
        "activity_position",
        "after",
        expected="before",
    )
    if updated == content or "activity_position: after" not in updated:
        raise AssertionError("strict frontmatter replacement did not mutate its target")
    for field, expected in (("missing", None), ("activity_position", "stale")):
        try:
            replace_frontmatter_field(content, field, "after", expected=expected)
        except AssertionError:
            pass
        else:
            raise AssertionError("strict fixture mutation accepted a zero-match edit")
    for old in ("missing token", "activity_position: stale"):
        try:
            replace_exactly_once(
                content,
                old,
                "activity_position: after",
                label="generic zero-match fixture",
            )
        except AssertionError:
            pass
        else:
            raise AssertionError("generic fixture mutation accepted a zero-match edit")
    duplicate_frontmatter = (
        "---\nactivity_position: before\nactivity_position: before\n---\n"
    )
    try:
        replace_frontmatter_field(
            duplicate_frontmatter,
            "activity_position",
            "after",
            expected="before",
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(
            "strict frontmatter replacement accepted duplicate matches"
        )
    duplicate_text = "cloud_project_mode: generic_skeleton\n" * 2
    try:
        replace_exactly_once(
            duplicate_text,
            "cloud_project_mode: generic_skeleton",
            "cloud_project_mode: personal_instance",
            label="generic duplicate fixture",
        )
    except AssertionError:
        pass
    else:
        raise AssertionError("generic replacement accepted duplicate matches")
    try:
        replace_regex_exactly_once(
            duplicate_text,
            r"^cloud_project_mode:\s*generic_skeleton\s*$",
            "cloud_project_mode: personal_instance",
            label="regex duplicate fixture",
            flags=re.MULTILINE,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError("regex replacement accepted duplicate matches")


def test_state_refresh_activity_roundtrip(root: Path) -> None:
    reset_state(root)
    course = root / "main/40_course/TEST1001"
    write(
        course / "course.md",
        "---\ntype: course\ncourse_id: TEST1001\nname: Test Course\n---\n",
    )
    write(
        course / "lessons/lesson01/lesson01.md",
        "---\ntype: lesson\ncourse_id: TEST1001\nlesson_id: lesson01\n---\n"
        "# lesson01\n",
    )
    write(
        root / "main/30_group/G01/plan.md",
        "---\ngroup_id: G01\nstatus: active\ncourse_members: [TEST1001]\n"
        "engagement_members: []\ncurrent_course: TEST1001\n---\n"
        "<!-- T2AG_GENERATED:GROUP_VIEW:START -->\nold\n"
        "<!-- T2AG_GENERATED:GROUP_VIEW:END -->\n",
    )
    write(root / "main/10_student/profile/profile.md", "---\ninitialization_status: initialized\n---\n")
    write(
        root / "main/00_core/t2ag_memory.md",
        "<!-- T2AG_GENERATED:ACTIVE_PROGRESS:START -->\nold\n"
        "<!-- T2AG_GENERATED:ACTIVE_PROGRESS:END -->\n"
        "<!-- T2AG_GENERATED:STATE_POINTERS:START -->\nold\n"
        "<!-- T2AG_GENERATED:STATE_POINTERS:END -->\n",
    )
    write(
        root / "main/10_student/profile/learning_path.md",
        "<!-- T2AG_GENERATED:COURSE_INDEX:START -->\nold\n"
        "<!-- T2AG_GENERATED:COURSE_INDEX:END -->\n"
        "<!-- T2AG_GENERATED:GROUP_INDEX:START -->\nold\n"
        "<!-- T2AG_GENERATED:GROUP_INDEX:END -->\n",
    )
    write(root / "cloud/cloud_sync_state.md", "- cloud_bridge_status: paused\n")
    write_teacher_mapping(root, ("TEST1001",))

    def progress(
        lifecycle: str,
        current_lesson: str,
        activity_fields: str,
        position: str,
    ) -> str:
        position_line = (
            f"activity_position: {position}\n" if lifecycle == "ongoing" else ""
        )
        return (
            "---\ntype: course_progress\ncourse_id: TEST1001\n"
            f"lifecycle_status: {lifecycle}\ncourse_driver: goal\ntruth_source: true\n"
            f"current_lesson: {current_lesson}\n{activity_fields}"
            f"{position_line}updated: 2026-07-26\n"
            "current_completion_node: TEST1001-N01\n"
            "current_checkpoint: TEST1001-N01-S01\ncheckpoint_state: queued\n"
            "next_action: continue\n---\n"
        )

    def rendered() -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): content
            for path, content in state_refresh.planned_updates()
        }

    write(course / "progress.md", progress("ongoing", "lesson01", "", "start"))
    try:
        rendered()
    except ValueError as exc:
        if "显式活动字段" not in str(exc):
            raise AssertionError(f"unexpected state refresh error: {exc}") from exc
    else:
        raise AssertionError("state refresh accepted missing explicit activity fields")

    write(
        course / "exercises/U0001/exercise.md",
        "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\n---\n"
        "# U0001\n",
    )
    write(
        course / "exercises/U0001/problems.md",
        "---\ntype: exercise_problem_set\ncourse_id: TEST1001\n"
        "exercise_id: U0001\n---\n# Problems\n",
    )
    write(
        course / "progress.md",
        progress(
            "ongoing",
            "none",
            "current_activity: exercise\ncurrent_activity_id: U0001\n"
            "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n",
            "first exercise",
        ),
    )
    progress_reads = 0
    original_state_read = state_refresh.read
    original_activity_read = activity.read

    def counting_read(path: Path) -> str:
        nonlocal progress_reads
        if path == course / "progress.md":
            progress_reads += 1
        return path.read_text(encoding="utf-8-sig")

    state_refresh.read = counting_read
    activity.read = counting_read
    try:
        exercise = rendered()
    finally:
        state_refresh.read = original_state_read
        activity.read = original_activity_read
    if progress_reads != 1:
        raise AssertionError(
            f"state refresh read one progress snapshot {progress_reads} times"
        )
    memory = exercise["main/00_core/t2ag_memory.md"]
    if "| Lesson 上下文 | 无 | — |" not in memory:
        raise AssertionError(f"exercise-first lesson pointer rendered incorrectly:\n{memory}")
    if "lessons/none/none.md" in memory:
        raise AssertionError(f"exercise-first state contains dangling lesson path:\n{memory}")
    if (
        "| 当前教学活动 | exercise: U0001 | "
        "`main/40_course/TEST1001/exercises/U0001/exercise.md` |"
    ) not in memory:
        raise AssertionError(f"exercise pointer missing from generated state:\n{memory}")
    if "- **学到哪**：TEST1001 exercise U0001，first exercise" not in memory:
        raise AssertionError(f"active summary still derives from current_lesson:\n{memory}")
    group_view = exercise["main/30_group/G01/plan.md"]
    if "| 课程 | 当前活动 | 停点 |" not in group_view or "exercise: U0001" not in group_view:
        raise AssertionError(f"group view still assumes Lesson:\n{group_view}")

    write(
        course / "progress.md",
        progress(
            "ongoing",
            "—",
            "current_activity: exercise\ncurrent_activity_id: U0001\n"
            "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n",
            "first exercise",
        ),
    )
    dash = rendered()["main/00_core/t2ag_memory.md"]
    if "| Lesson 上下文 | 无 | — |" not in dash:
        raise AssertionError(f"dash Lesson sentinel rendered incorrectly:\n{dash}")

    write(
        course / "progress.md",
        progress(
            "ongoing",
            "lesson01",
            "current_activity: exercise\ncurrent_activity_id: U0001\n"
            "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n",
            "first exercise",
        ),
    )
    historical = rendered()["main/00_core/t2ag_memory.md"]
    if "| Lesson 上下文 | lesson01（历史兼容） |" not in historical:
        raise AssertionError(f"historical Lesson mislabeled as active:\n{historical}")

    write(
        course / "progress.md",
        progress(
            "ongoing",
            "lesson999",
            "current_activity: exercise\ncurrent_activity_id: U0001\n"
            "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n",
            "first exercise",
        ),
    )
    try:
        rendered()
    except ValueError as exc:
        if "兼容 current_lesson 悬空" not in str(exc):
            raise AssertionError(f"unexpected stale Lesson error: {exc}") from exc
    else:
        raise AssertionError("state refresh accepted a dangling historical Lesson")

    write(course / "progress.md", progress("planned", "none", "", "not started"))
    planned = rendered()["main/00_core/t2ag_memory.md"]
    if "| 当前教学活动 | —: — | — |" not in planned:
        raise AssertionError(f"planned course received inferred activity fields:\n{planned}")


def test_exercise_current_lesson_driver_matrix(root: Path) -> None:
    drivers = ("textbook", "goal", "project", "praxis")

    def build(case_root: Path, driver: str, lesson_value: str | None, real_lesson: bool) -> None:
        course = case_root / "main/40_course/TEST1001"
        write(
            course / "course.md",
            "---\ntype: course\ncourse_id: TEST1001\nschool_course_code: TEST1001\n"
            f"name: Test Course\ncourse_type: mastery\ndefault_driver: {driver}\n"
            "prerequisites: []\nstatus: active\n---\n",
        )
        lesson_line = (
            f"current_lesson: {lesson_value}\n"
            if lesson_value is not None else ""
        )
        write(
            course / "progress.md",
            "---\ntype: course_progress\ncourse_id: TEST1001\nlifecycle_status: ongoing\n"
            f"course_driver: {driver}\ntruth_source: true\n{lesson_line}"
            "current_activity: exercise\ncurrent_activity_id: U0001\n"
            "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n"
            "activity_position: first exercise\nupdated: 2026-07-26\n"
            "current_completion_node: TEST1001-N01\n"
            "current_checkpoint: TEST1001-N01-S01\ncheckpoint_state: queued\n"
            "next_action: solve\n---\n",
        )
        write(
            course / "exercises/U0001/exercise.md",
            "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\n---\n",
        )
        source_fields = (
            write_textbook_source_contract(
                case_root,
                "TEST1001",
                "U0001",
                "TEST1001-B001-C01-S01",
                "test",
            )
            if driver == "textbook"
            else ""
        )
        write(
            course / "exercises/U0001/problems.md",
            "---\ntype: exercise_problem_set\ncourse_id: TEST1001\n"
            f"exercise_id: U0001\n{source_fields}---\n# Problems\n",
        )
        write(course / "lessons/_README.md", "placeholder\n")
        if real_lesson:
            write(
                course / "lessons/lesson01/lesson01.md",
                "---\ntype: lesson\ncourse_id: TEST1001\nlesson_id: lesson01\n---\n",
            )
        write(course / "book/README.md", "placeholder\n")
        write(course / "mistake_bank.md", "# Mistakes\n")
        write(course / "question_bank.md", "# Questions\n")

    for driver in drivers:
        missing_root = root / f"{driver}_missing"
        build(missing_root, driver, None, False)
        reset(missing_root)
        run_silently(doctor.discover_courses)
        assert_message(doctor.fails, "current_lesson")

        stale_root = root / f"{driver}_stale"
        build(stale_root, driver, "lesson999", False)
        reset(stale_root)
        run_silently(doctor.discover_courses)
        assert_message(doctor.fails, "兼容 current_lesson 悬空")

        none_root = root / f"{driver}_none"
        build(none_root, driver, "none", False)
        reset(none_root)
        run_silently(doctor.discover_courses)
        if doctor.fails:
            raise AssertionError(f"{driver} exercise-first course rejected: {doctor.fails}")

        dash_root = root / f"{driver}_dash"
        build(dash_root, driver, "—", False)
        reset(dash_root)
        run_silently(doctor.discover_courses)
        if doctor.fails:
            raise AssertionError(f"{driver} dash Lesson sentinel rejected: {doctor.fails}")

        real_root = root / f"{driver}_real"
        build(real_root, driver, "lesson01", True)
        reset(real_root)
        run_silently(doctor.discover_courses)
        if doctor.fails:
            raise AssertionError(f"{driver} real compatibility Lesson rejected: {doctor.fails}")


def test_planned_activity_fields_rejected(root: Path) -> None:
    def build(case_root: Path, extra: str) -> None:
        course = case_root / "main/40_course/TEST1001"
        write(
            course / "course.md",
            "---\ntype: course\ncourse_id: TEST1001\nschool_course_code: TEST1001\n"
            "name: Test Course\ncourse_type: mastery\ndefault_driver: goal\n"
            "prerequisites: []\nstatus: active\n---\n",
        )
        write(
            course / "progress.md",
            "---\ntype: course_progress\ncourse_id: TEST1001\n"
            "lifecycle_status: planned\ncourse_driver: goal\ntruth_source: true\n"
            "current_lesson: none\nprogress_nodes_status: lazy_on_activation\n"
            f"{extra}updated: 2026-07-26\nnext_action: wait\n---\n",
        )
        write(course / "lessons/_README.md", "placeholder\n")
        write(course / "exercises/_README.md", "placeholder\n")
        write(course / "book/README.md", "placeholder\n")
        write(course / "mistake_bank.md", "# Mistakes\n")
        write(course / "question_bank.md", "# Questions\n")

    illegal = root / "illegal"
    build(
        illegal,
        "current_activity: exercise\ncurrent_activity_id: U0001\n"
        "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n"
        "activity_position: prefilled\n",
    )
    reset(illegal)
    run_silently(doctor.discover_courses)
    assert_message(doctor.fails, "planned 课程不得携带活动字段")

    legal = root / "legal"
    build(legal, "")
    reset(legal)
    run_silently(doctor.discover_courses)
    if doctor.fails:
        raise AssertionError(f"legal planned course rejected: {doctor.fails}")


def test_working_pages_activity_matrix(root: Path) -> None:
    exercise = root / "main/40_course/EXER1001"
    lesson = root / "main/40_course/LESS1001"
    write(
        exercise / "lessons/lesson01/lesson01.md",
        "---\ntype: lesson\ncourse_id: EXER1001\nlesson_id: lesson01\n---\n",
    )
    write(
        lesson / "lessons/lesson01/lesson01.md",
        "---\ntype: lesson\ncourse_id: LESS1001\nlesson_id: lesson01\n---\n",
    )
    courses = {
        "EXER1001": (
            exercise,
            {
                "course_driver": "textbook",
                "current_activity": "exercise",
                "current_activity_id": "U0001",
                "current_lesson": "lesson01",
                "textbook_page": "not-a-number",
                "working_pages_window": "[broken]",
            },
        ),
        "LESS1001": (
            lesson,
            {
                "course_driver": "textbook",
                "current_activity": "lesson",
                "current_activity_id": "lesson01",
                "current_lesson": "lesson01",
                "textbook_page": "1",
                "working_pages_window": "[1]",
            },
        ),
    }
    reset(root)
    run_silently(doctor.check_working_pages, courses)
    if any("EXER1001" in message for message in doctor.fails):
        raise AssertionError(f"Exercise inherited working-pages validation: {doctor.fails}")
    assert_message(doctor.fails, "LESS1001")
    assert_message(doctor.fails, "缺 working page PNG")

    write(
        lesson / "progress.md",
        "---\ntype: course_progress\ncourse_id: LESS1001\n"
        "lifecycle_status: ongoing\ncourse_driver: goal\ntruth_source: true\n"
        "current_lesson: lesson01\ncurrent_activity: lesson\n"
        "current_activity_id: lesson01\n"
        "resume_path: main/40_course/LESS1001/lessons/lesson01/lesson01.md\n"
        "activity_position: first goal lesson\n---\n",
    )
    route = state_refresh.resolve_activity(root, "LESS1001")
    if route.recovery_plan()["working_pages"] is not None:
        raise AssertionError("non-textbook Lesson inherited working-pages routing")
    try:
        state_refresh.resolve_activity(root, "../escape")
    except state_refresh.ActivityContractError as exc:
        if "course_id 非法" not in str(exc):
            raise AssertionError(f"unexpected course-id error: {exc}") from exc
    else:
        raise AssertionError("activity route accepted a path-like course_id")


def test_skin_art(root: Path) -> None:
    reset(root)
    write(
        root / "main/80_interface/skin.yaml",
        "active: SK001\nregistry.SK001: SK001_default\n",
    )
    write(
        root / "main/80_interface/SK001_default/skin.yaml",
        "id: SK001\nname: default\nversion: 1\nwelcome_msg: hello\n"
        "art_file: missing.txt\nstyle: default\n",
    )
    write(root / "main/80_interface/SK001_default/01_welcome.txt", "t2AG\n")
    run_silently(doctor.check_skin_system)
    assert_message(doctor.fails, "art_file 悬空")
    write(
        root / "main/80_interface/SK001_default/skin.yaml",
        "id: SK001\nname: default\nversion: 1\nwelcome_msg: hello\n"
        "art_file: 01_welcome.txt\nstyle: default\n",
    )
    write(root / "main/80_interface/SK001_default/01_welcome.txt", "t2ag\n")
    reset(root, "skeleton")
    run_silently(doctor.check_skin_system)
    assert_message(doctor.fails, "未明确显示 t2AG")


def test_course_activity_templates(root: Path) -> None:
    reset(root)
    run_silently(doctor.check_course_activity_templates)
    assert_message(doctor.fails, "系统模板缺失")
    assert_message(doctor.fails, "缺课程学习活动 Core 契约")
    assert_message(doctor.fails, "课程学习活动 Core 缺地图优先讲解协议")
    assert_message(doctor.fails, "首次启动未采集长篇讲解地图与分支确认偏好")
    assert_message(doctor.fails, "课程恢复流程未先按 current_activity 分支")


def test_flow_and_offline_guide(root: Path) -> None:
    reset(root)
    write(
        root / "main/50_playbook/t2ag_flow.md",
        "<!-- FLOW:first_run -->\n```mermaid\nflowchart TD\nA[\"A\"]\n```\n"
        "<!-- /FLOW:first_run -->\n",
    )
    write(
        root / "t2ag_directory_guide.html",
        '<script src="https://cdn.jsdelivr.net/npm/mermaid"></script>\n'
        '<svg class="flow-svg"></svg>\n'
        '<details class="flow-source"></details>\n',
    )
    run_silently(doctor.check_flow_and_guide)
    assert_message(doctor.fails, "FLOW 集合")
    assert_message(doctor.fails, "外部运行时")
    assert_message(doctor.fails, "未按需折叠")
    assert_message(doctor.fails, "缺响应式尺寸")
    assert_message(doctor.fails, "缺受控滚动视窗")


def test_hint_gate_contract(root: Path) -> None:
    enabled_concept = hint_gate.evaluate_gate("enabled", "concept_answer")
    if not enabled_concept.allowed:
        raise AssertionError("enabled concept_answer should be allowed")
    for marker in (
        "answer_the_explicitly_requested_concept_only",
        "do_not_apply_the_concept_to_the_active_problem",
    ):
        if marker not in enabled_concept.constraints:
            raise AssertionError(f"concept scope guard missing: {marker}")

    enabled_feedback = hint_gate.evaluate_gate("enabled", "reasoning_feedback")
    if not enabled_feedback.allowed or (
        "do_not_introduce_new_solution_objects_subgoals_or_steps"
        not in enabled_feedback.constraints
    ):
        raise AssertionError("reasoning feedback leaked a new-step capability")

    denied = hint_gate.evaluate_gate("enabled", "direction_hint")
    if denied.allowed or denied.decision != "deny":
        raise AssertionError("unrequested direction hint was not denied")
    wrong_level = hint_gate.evaluate_gate(
        "enabled", "full_solution", "direction"
    )
    if wrong_level.allowed:
        raise AssertionError("direction authorization escalated to full solution")
    allowed = hint_gate.evaluate_gate(
        "enabled", "full_solution", "solution"
    )
    if not allowed.allowed:
        raise AssertionError("explicit full-solution authorization was rejected")

    disabled = hint_gate.evaluate_gate("disabled", "full_solution")
    if (
        not disabled.allowed
        or disabled.decision != "defer_to_base_rules"
        or not disabled.as_dict()["base_teaching_rules_remain"]
    ):
        raise AssertionError("disabled gate erased the base teaching contract")

    try:
        hint_gate.evaluate_gate("ask", "concept_answer")
    except hint_gate.HintGateContractError:
        pass
    else:
        raise AssertionError("unresolved first-run hint-gate choice was accepted")


def test_exercise_evidence(root: Path) -> None:
    reset(root)
    unit = root / "main/40_course/TEST1001/exercises/U0001"
    write(
        unit / "exercise.md",
        "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\n"
        "content_group_ids: []\nstatus: ongoing\ncreated: 2026-07-26\n---\n",
    )
    write(
        unit / "problems.md",
        "---\ntype: exercise_problem_set\ncourse_id: TEST1001\nexercise_id: U0001\n---\n"
        "## U0001-Q001\n- 题号：1\n- 来源页：1\n- 难度：L1\n"
        "- 依赖 completion node：TEST1001-N01\n- 状态：open\n- 错误级别：none\n- 题面：test\n",
    )
    write(
        unit / "attempts/AT0001/attempt.md",
        "---\ntype: exercise_attempt\ncourse_id: TEST1001\nexercise_id: U0001\n"
        "attempt_id: AT0001\nproblem_ids: [U0001-Q001]\nmode: image\n"
        "status: submitted\ncreated: 2026-08-01\n---\n"
        "## 作答上下文\n- test\n## U0001-Q001\n- 作答：见图\n",
    )
    write(
        unit / "reviews/RV0001.md",
        "---\ntype: exercise_review\ncourse_id: TEST1001\nexercise_id: U0001\n"
        "review_id: RV0001\nattempt_id: AT9999\nproblem_ids: [U0001-Q001]\n"
        "reviewer: teacher\nstatus: recorded\nreviewed: 2026-07-26\n---\n"
        "## U0001-Q001\n- 结果：correct\n- 思路观察：—\n- 反馈：—\n"
        "- mistake_refs：[]\n- question_refs：[]\n",
    )
    courses = {"TEST1001": (root / "main/40_course/TEST1001", {})}
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "缺原始图片")
    assert_message(doctor.fails, "未知 Attempt")
    assert_message(doctor.fails, "缺提示闸门快照")


def test_exercise_activity_links(root: Path) -> None:
    reset(root)
    course = root / "main/40_course/TEST1001"
    write(
        course / "progress.md",
        "---\ntype: course_progress\ncourse_id: TEST1001\n"
        "lifecycle_status: ongoing\ncourse_driver: textbook\ntruth_source: true\n"
        "current_lesson: none\ncurrent_activity: exercise\n"
        "current_activity_id: U0001\n"
        "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n"
        "activity_position: synthetic source contract\nupdated: 2026-07-26\n"
        "current_completion_node: TEST1001-B001-C01-S01-N01\n"
        "current_checkpoint: TEST1001-B001-C01-S01-N01-S01\n"
        "checkpoint_state: queued\nnext_action: verify source\n---\n"
        "## Completion nodes\n\n"
        "| node_id | 标题 | 来源范围 | 状态 | 完成证据 |\n"
        "|---|---|---|---|---|\n"
        "| TEST1001-B001-C01-S01-N01 | test | page 1 | queued | — |\n",
    )
    write(
        course / "lessons/lesson01/lesson01.md",
        "---\ntype: lesson\ncourse_id: TEST1001\nlesson_id: lesson01\n"
        "content_group_ids: [TEST1001-B001-C01-S01]\n---\n",
    )
    write(
        course / "activity_map.md",
        "---\ntype: course_activity_map\ncourse_id: TEST1001\n---\n"
        "## 内容组连接表\n\n"
        "| content_group_id | source_scope | lesson_ids | exercise_ids |\n"
        "|---|---|---|---|\n"
        "| TEST1001-B001-C01-S01 | B001 / C01 / S01 | lesson01 | U0001 |\n",
    )
    unit = course / "exercises/U0001"
    write(
        unit / "exercise.md",
        "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\n"
        "content_group_ids: [TEST1001-B001-C01-S02]\nstatus: ongoing\ncreated: 2026-07-26\n---\n",
    )
    source_fields = write_textbook_source_contract(
        root,
        "TEST1001",
        "U0001",
        "TEST1001-B001-C01-S01",
        "test",
    )
    write(
        unit / "problems.md",
        "---\ntype: exercise_problem_set\ncourse_id: TEST1001\nexercise_id: U0001\n"
        "content_group_id: TEST1001-B001-C01-S01\n"
        f"{source_fields}"
        "source_order: [U0001-Q001]\nteaching_sequence: [U0001-Q001]\n---\n"
        "## U0001-Q001\n- 题号：1\n- 来源页：1\n- 难度：L1\n"
        "- 依赖 completion node：`TEST1001-B001-C01-S01-N01`\n"
        "- 状态：open\n- 错误级别：none\n- 题面：test\n",
    )
    write(unit / "attempts/_README.md", "placeholder\n")
    write(unit / "reviews/_README.md", "placeholder\n")
    courses = {"TEST1001": (course, {"course_driver": "textbook"})}
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "Exercise 与活动连接表 ContentGroup 漂移")


def test_project_completion_evidence(root: Path) -> None:
    reset(root)
    course = root / "main/40_course/PROJ1001"
    write(course / "course.md", "---\ncourse_type: project\n---\n")
    write(
        course / "progress.md",
        "## Completion nodes\n\n| node_id | 状态 | 验证模式 | 验收标准 | 关闭证据 |\n"
        "|---|---|---|---|---|\n"
        "| PROJ1001-M0 | completed | A | main.py 输出 taste.md | — |\n",
    )
    run_silently(
        doctor.check_project_verification,
        {"PROJ1001": (course, {"lifecycle_status": "ongoing"})},
    )
    assert_message(doctor.fails, "缺关闭证据")
    reset(root)
    pointer = "`main/40_course/PROJ1001/progress.md#VER-PROJ1001-M0-20260726`"
    write(
        course / "progress.md",
        "## Completion nodes\n\n| node_id | 状态 | 验证模式 | 验收标准 | 关闭证据 |\n"
        "|---|---|---|---|---|\n"
        f"| PROJ1001-M0 | completed | A | main.py 输出 taste.md | {pointer} |\n",
    )
    run_silently(
        doctor.check_project_verification,
        {"PROJ1001": (course, {"lifecycle_status": "ongoing"})},
    )
    assert_message(doctor.fails, "验收记录不存在")
    reset(root)
    write(
        course / "progress.md",
        "## Completion nodes\n\n| node_id | 状态 | 验证模式 | 验收标准 | 关闭证据 |\n"
        "|---|---|---|---|---|\n"
        f"| PROJ1001-M0 | completed | A | main.py 输出 taste.md | {pointer} |\n\n"
        "## 项目验收记录\n\n### VER-PROJ1001-M0-20260726\n\n"
        "- 节点：`PROJ1001-M0`\n- 验证模式：`A`\n- 结论：passed\n"
        "- 验收日期：2026-07-26\n- 可复现性检查：passed · smoke\n"
        "- 客观验收：passed · standard\n- 讲解口试：passed · oral\n"
        "- 盲改挑战：passed · change\n- 留档：passed · archived\n",
    )
    run_silently(
        doctor.check_project_verification,
        {"PROJ1001": (course, {"lifecycle_status": "ongoing"})},
    )
    if doctor.fails:
        raise AssertionError(f"valid project verification record rejected: {doctor.fails}")


def test_project_completion_step_summary_required(root: Path) -> None:
    reset(root)
    course = root / "main/40_course/PROJ1001"
    write(course / "course.md", "---\ncourse_type: project\n---\n")
    pointer = "`main/40_course/PROJ1001/progress.md#VER-PROJ1001-M0-20260726`"

    def record(step_value: str) -> str:
        return (
            "## Completion nodes\n\n| node_id | 状态 | 验证模式 | 验收标准 | 关闭证据 |\n"
            "|---|---|---|---|---|\n"
            f"| PROJ1001-M0 | completed | A | main.py 输出 taste.md | {pointer} |\n\n"
            "## 项目验收记录\n\n### VER-PROJ1001-M0-20260726\n\n"
            "- 节点：`PROJ1001-M0`\n- 验证模式：`A`\n- 结论：passed\n"
            "- 验收日期：2026-07-26\n"
            f"- 可复现性检查：{step_value}\n- 客观验收：{step_value}\n"
            f"- 讲解口试：{step_value}\n- 盲改挑战：{step_value}\n"
            f"- 留档：{step_value}\n"
        )

    for invalid in ("passed", "passed ·", "passed：   ", "passed · :"):
        reset(root)
        write(course / "progress.md", record(invalid))
        run_silently(
            doctor.check_project_verification,
            {"PROJ1001": (course, {"lifecycle_status": "ongoing"})},
        )
        assert_message(doctor.fails, "缺 passed + 实际结果摘要")

    reset(root)
    write(course / "progress.md", record("passed · smoke produced taste.md"))
    run_silently(
        doctor.check_project_verification,
        {"PROJ1001": (course, {"lifecycle_status": "ongoing"})},
    )
    if doctor.fails:
        raise AssertionError(f"project verification summary rejected: {doctor.fails}")


def test_textbook_dependency_contract(root: Path) -> None:
    course = root / "main/40_course/TEST1001"
    unit = course / "exercises/U0001"
    write(
        course / "progress.md",
        "## Completion nodes\n\n"
        "| node_id | 标题 | 来源范围 | 状态 | 完成证据 |\n"
        "|---|---|---|---|---|\n"
        "| TEST1001-B001-C01-S01-N01 | test | page 1 | queued | — |\n",
    )
    write(
        course / "lessons/lesson01/lesson01.md",
        "---\ntype: lesson\ncourse_id: TEST1001\nlesson_id: lesson01\n"
        "content_group_ids: [TEST1001-B001-C01-S01]\n---\n",
    )
    write(
        course / "activity_map.md",
        "---\ntype: course_activity_map\ncourse_id: TEST1001\n---\n"
        "## 内容组连接表\n\n"
        "| content_group_id | source_scope | lesson_ids | exercise_ids |\n"
        "|---|---|---|---|\n"
        "| TEST1001-B001-C01-S01 | B001 / C01 / S01 | lesson01 | U0001 |\n",
    )
    write(
        unit / "exercise.md",
        "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\n"
        "content_group_ids: [TEST1001-B001-C01-S01]\nstatus: ongoing\ncreated: 2026-07-26\n---\n",
    )
    write(unit / "attempts/_README.md", "placeholder\n")
    write(unit / "reviews/_README.md", "placeholder\n")
    source_fields = write_textbook_source_contract(
        root,
        "TEST1001",
        "U0001",
        "TEST1001-B001-C01-S01",
        "test",
    )

    def problems(dependency: str) -> str:
        return (
            "---\ntype: exercise_problem_set\ncourse_id: TEST1001\nexercise_id: U0001\n"
            "content_group_id: TEST1001-B001-C01-S01\n"
            f"{source_fields}"
            "source_order: [U0001-Q001]\nteaching_sequence: [U0001-Q001]\n---\n"
            "## U0001-Q001\n- 题号：1\n- 来源页：1\n- 难度：L1\n"
            f"- 依赖 completion node：{dependency}\n"
            "- 状态：open\n- 错误级别：none\n- 题面：test\n"
        )

    for malformed in ("MALFORMED-OUTSIDE-GROUP", "", "`NOT-A-NODE`"):
        reset(root)
        write(unit / "problems.md", problems(malformed))
        run_silently(
            doctor.check_exercises,
            {"TEST1001": (course, {"course_driver": "textbook"})},
        )
        assert_message(doctor.fails, "依赖 completion node 格式非法")

    reset(root)
    write(unit / "problems.md", problems("`TEST1001-B001-C01-S02-N01`"))
    run_silently(
        doctor.check_exercises,
        {"TEST1001": (course, {"course_driver": "textbook"})},
    )
    assert_message(doctor.fails, "教材习题依赖越出内容组")

    reset(root)
    write(unit / "problems.md", problems("`TEST1001-B001-C01-S01-N9999`"))
    run_silently(
        doctor.check_exercises,
        {"TEST1001": (course, {"course_driver": "textbook"})},
    )
    assert_message(doctor.fails, "教材习题依赖 completion node 不存在")

    reset(root)
    write(unit / "problems.md", problems("`TEST1001-B001-C01-S01-N01`"))
    run_silently(
        doctor.check_exercises,
        {"TEST1001": (course, {"course_driver": "textbook"})},
    )
    if doctor.fails:
        raise AssertionError(f"canonical textbook dependency rejected: {doctor.fails}")


def test_persistent_exercise_source_contract(root: Path) -> None:
    course = root / "main/40_course/TEST1001"
    unit = course / "exercises/U0001"
    content_group = "TEST1001-B001-C01-S01"
    write(
        course / "progress.md",
        "---\ntype: course_progress\ncourse_id: TEST1001\n"
        "lifecycle_status: ongoing\ncourse_driver: textbook\ntruth_source: true\n"
        "current_lesson: none\ncurrent_activity: exercise\n"
        "current_activity_id: U0001\n"
        "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n"
        "activity_position: synthetic source contract\nupdated: 2026-07-26\n"
        "current_completion_node: TEST1001-B001-C01-S01-N01\n"
        "current_checkpoint: TEST1001-B001-C01-S01-N01-S01\n"
        "checkpoint_state: queued\nnext_action: verify source\n---\n"
        "## Completion nodes\n\n"
        "| node_id | 标题 | 来源范围 | 状态 | 完成证据 |\n"
        "|---|---|---|---|---|\n"
        f"| {content_group}-N01 | test | page 1 | queued | — |\n",
    )
    write(
        course / "activity_map.md",
        "---\ntype: course_activity_map\ncourse_id: TEST1001\n---\n"
        "## 内容组连接表\n\n"
        "| content_group_id | source_scope | lesson_ids | exercise_ids |\n"
        "|---|---|---|---|\n"
        f"| {content_group} | synthetic | — | U0001 |\n",
    )
    write(course / "lessons/_README.md", "empty\n")
    write(
        unit / "exercise.md",
        "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\n"
        f"content_group_ids: [{content_group}]\nstatus: ongoing\n"
        "created: 2026-07-26\n---\n",
    )
    (unit / "attempts").mkdir(parents=True, exist_ok=True)
    (unit / "reviews").mkdir(parents=True, exist_ok=True)

    def problems(source_fields: str, statement: str = "test") -> str:
        return (
            "---\ntype: exercise_problem_set\ncourse_id: TEST1001\n"
            f"exercise_id: U0001\ncontent_group_id: {content_group}\n"
            f"{source_fields}"
            "source_order: [U0001-Q001]\nteaching_sequence: [U0001-Q001]\n"
            "status: active\n---\n# Problems\n\n## U0001-Q001\n\n"
            "- 题号：1\n- 来源页：1\n- 难度：L1\n"
            f"- 依赖 completion node：`{content_group}-N01`\n"
            f"- 状态：open\n- 错误级别：none\n- 题面：{statement}\n"
        )

    source_fields = write_textbook_source_contract(
        root, "TEST1001", "U0001", content_group, "test",
    )
    write(unit / "problems.md", problems(source_fields))
    courses = {"TEST1001": (course, {"course_driver": "textbook"})}

    def source_from(fields: str) -> Path:
        match = re.search(r"^source_path:\s*(.+)$", fields, re.MULTILINE)
        if not match:
            raise AssertionError("source fixture lacks source_path")
        return root / match.group(1)

    def refresh_source_sha(fields: str, source_file: Path) -> str:
        current = re.search(r"^source_sha256:\s*(.+)$", fields, re.MULTILINE)
        if not current:
            raise AssertionError("source fixture lacks source_sha256")
        return replace_frontmatter_field(
            fields,
            "source_sha256",
            hashlib.sha256(source_file.read_bytes()).hexdigest(),
            expected=current.group(1),
        )

    reset(root)
    run_silently(doctor.check_exercises, courses)
    if doctor.fails:
        raise AssertionError(f"valid persistent Exercise source rejected: {doctor.fails}")
    source_path = re.search(r"^source_path:\s*(.+)$", source_fields, re.MULTILINE)
    assert source_path
    route = doctor.resolve_activity(root, "TEST1001")
    if route.source_path != source_path.group(1):
        raise AssertionError("valid activity route lost its persistent source")
    if (
        route.activity_position != "synthetic source contract"
        or route.recovery_plan()["activity_position"] != route.activity_position
        or route.close_plan()["activity_position"] != route.activity_position
    ):
        raise AssertionError("activity position was not captured in one route snapshot")

    source = root / source_path.group(1)
    source.unlink()
    reset(root)
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "持久题源不存在")

    source_fields = write_textbook_source_contract(
        root, "TEST1001", "U0001", content_group, "test",
    )
    write(unit / "problems.md", problems(source_fields, "changed"))
    reset(root)
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "题面与持久题源不一致")

    source_fields = write_textbook_source_contract(
        root, "TEST1001", "U0001", content_group, "test",
    )
    source = source_from(source_fields)
    outside = unit / "outside_source.md"
    shutil.copy2(source, outside)
    traversal = (
        "main/40_course/TEST1001/book/../exercises/U0001/"
        "outside_source.md"
    )
    source_fields = replace_frontmatter_field(
        source_fields,
        "source_path",
        traversal,
        expected=source.relative_to(root).as_posix(),
    )
    source_fields = refresh_source_sha(source_fields, outside)
    registry_path = root / "main/70_tools/artifact_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    artifact = next(
        item for item in registry["artifacts"]
        if item["artifact_id"] == "TEST1001_U0001_SOURCE"
    )
    artifact["canonical_path"] = traversal
    write(registry_path, json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    write(unit / "problems.md", problems(source_fields))
    try:
        doctor.resolve_activity(root, "TEST1001")
    except doctor.ActivityContractError:
        pass
    else:
        raise AssertionError("activity resolver accepted a book/../ path escape")
    reset(root)
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "持久题源路径非法")

    source_fields = write_textbook_source_contract(
        root, "TEST1001", "U0001", content_group, "test",
    )
    source = source_from(source_fields)
    source.write_text(
        replace_frontmatter_field(
            source.read_text(encoding="utf-8"),
            "artifact_id",
            "WRONG_SOURCE",
            expected="TEST1001_U0001_SOURCE",
        ),
        encoding="utf-8",
        newline="\n",
    )
    source_fields = refresh_source_sha(source_fields, source)
    write(unit / "problems.md", problems(source_fields))
    reset(root)
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "frontmatter 不匹配")

    source_fields = write_textbook_source_contract(
        root, "TEST1001", "U0001", content_group, "test",
    )
    source = source_from(source_fields)
    source.write_text(
        replace_frontmatter_field(
            source.read_text(encoding="utf-8"),
            "source_locator",
            "wrong locator",
            expected="synthetic problem 1",
        ),
        encoding="utf-8",
        newline="\n",
    )
    source_fields = refresh_source_sha(source_fields, source)
    write(unit / "problems.md", problems(source_fields))
    reset(root)
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "frontmatter 不匹配")

    source_fields = write_textbook_source_contract(
        root, "TEST1001", "U0001", content_group, "test",
    )
    source = source_from(source_fields)
    source_content = source.read_text(encoding="utf-8")
    document_sha = re.search(
        r"^source_document_sha256:\s*(.+)$", source_content, re.MULTILINE,
    )
    assert document_sha
    source.write_text(
        replace_frontmatter_field(
            source_content,
            "source_document_sha256",
            "0" * 64,
            expected=document_sha.group(1),
        ),
        encoding="utf-8",
        newline="\n",
    )
    source_fields = refresh_source_sha(source_fields, source)
    write(unit / "problems.md", problems(source_fields))
    reset(root)
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "源文档 SHA 漂移")

    source_fields = write_textbook_source_contract(
        root, "TEST1001", "U0001", content_group, "test",
    )
    source = source_from(source_fields)
    outside_document = unit / "outside_document.txt"
    write(outside_document, "outside source document\n")
    source_content = source.read_text(encoding="utf-8")
    original_document = re.search(
        r"^source_document:\s*(.+)$", source_content, re.MULTILINE,
    )
    original_document_sha = re.search(
        r"^source_document_sha256:\s*(.+)$", source_content, re.MULTILINE,
    )
    assert original_document and original_document_sha
    source_content = replace_frontmatter_field(
        source_content,
        "source_document",
        "main/40_course/TEST1001/book/../exercises/U0001/outside_document.txt",
        expected=original_document.group(1),
    )
    source_content = replace_frontmatter_field(
        source_content,
        "source_document_sha256",
        hashlib.sha256(outside_document.read_bytes()).hexdigest(),
        expected=original_document_sha.group(1),
    )
    source.write_text(source_content, encoding="utf-8", newline="\n")
    source_fields = refresh_source_sha(source_fields, source)
    write(unit / "problems.md", problems(source_fields))
    reset(root)
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "源文档路径非法")

    source_fields = write_textbook_source_contract(
        root, "TEST1001", "U0001", content_group, "test",
    )
    source = source_from(source_fields)
    original_link_check = activity._is_link_or_reparse
    activity._is_link_or_reparse = lambda path: (
        path == source or original_link_check(path)
    )
    try:
        try:
            doctor.resolve_activity(root, "TEST1001")
        except doctor.ActivityContractError:
            pass
        else:
            raise AssertionError("activity resolver accepted a linked source path")
    finally:
        activity._is_link_or_reparse = original_link_check

    source_fields = write_textbook_source_contract(
        root, "TEST1001", "U0001", content_group, "test",
    )
    source = source_from(source_fields)
    source_meta = activity.frontmatter(source)
    source_document = root / source_meta["source_document"]
    source_document.unlink()
    manifest_path, report_path = write_formal_lite_migration_evidence(
        root,
        source_meta["source_document"],
        source_meta["source_document_sha256"],
    )
    write(unit / "problems.md", problems(source_fields))
    reset(root, flavor="lite")
    run_silently(doctor.check_exercises, courses)
    if doctor.fails:
        raise AssertionError(f"Lite manifest-backed source rejected: {doctor.fails}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["operations"][0]["kind"]
    write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_payload["operation_manifest"]["sha256"] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    write(report_path, json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n")
    reset(root, flavor="lite")
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "哈希绑定 manifest")

    manifest_path, report_path = write_formal_lite_migration_evidence(
        root,
        source_meta["source_document"],
        source_meta["source_document_sha256"],
    )
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_payload["status"] = "draft"
    write(report_path, json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n")
    reset(root, flavor="lite")
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "哈希绑定 manifest")

    manifest_path, report_path = write_formal_lite_migration_evidence(
        root,
        source_meta["source_document"],
        source_meta["source_document_sha256"],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["operations"][0]["post_target"]["sha256"] = "0" * 64
    write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_payload["operation_manifest"]["sha256"] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    write(report_path, json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n")
    reset(root, flavor="lite")
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "哈希绑定 manifest")

    temporary_source = (
        "main/40_course/TEST1001/lessons/lesson01/"
        "working_pages/source_excerpt.md"
    )
    write(root / temporary_source, "temporary\n")
    registry_path = root / "main/70_tools/artifact_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["artifacts"][0]["canonical_path"] = temporary_source
    write(
        registry_path,
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
    )
    reset(root)
    run_silently(doctor.check_registry)
    assert_message(doctor.fails, "临时生命周期域")


def test_activity_map_strict_bidirectionality(root: Path) -> None:
    def lesson(course_id: str, groups: str, units: str) -> str:
        return (
            f"---\ntype: lesson\ncourse_id: {course_id}\nlesson_id: lesson01\n"
            f"content_group_ids: [{groups}]\n"
            + (f"exercise_unit_ids: [{units}]\n" if units else "")
            + "---\n"
        )

    def activity_map(course_id: str) -> str:
        return (
            f"---\ntype: course_activity_map\ncourse_id: {course_id}\n---\n"
            "## 内容组连接表\n\n"
            "| content_group_id | source_scope | lesson_ids | exercise_ids |\n"
            "|---|---|---|---|\n"
            f"| {course_id}-B001-C01-S01 | B001 / C01 / S01 | lesson01 | — |\n"
        )

    courses: dict[str, tuple[Path, dict[str, str]]] = {}
    extra_group_id = "EXTRA1001"
    extra_group = root / f"main/40_course/{extra_group_id}"
    write(
        extra_group / "lessons/lesson01/lesson01.md",
        lesson(
            extra_group_id,
            f"{extra_group_id}-B001-C01-S01, {extra_group_id}-B001-C01-S99",
            "",
        ),
    )
    write(extra_group / "exercises/_README.md", "placeholder\n")
    write(extra_group / "activity_map.md", activity_map(extra_group_id))
    courses[extra_group_id] = (extra_group, {"course_driver": "textbook"})

    dangling_unit_id = "EXTRA1002"
    dangling_unit = root / f"main/40_course/{dangling_unit_id}"
    write(
        dangling_unit / "lessons/lesson01/lesson01.md",
        lesson(dangling_unit_id, f"{dangling_unit_id}-B001-C01-S01", "U9999"),
    )
    write(dangling_unit / "exercises/_README.md", "placeholder\n")
    write(dangling_unit / "activity_map.md", activity_map(dangling_unit_id))
    courses[dangling_unit_id] = (dangling_unit, {"course_driver": "textbook"})

    missing_map_id = "EXTRA1003"
    missing_map = root / f"main/40_course/{missing_map_id}"
    write(
        missing_map / "lessons/lesson01/lesson01.md",
        lesson(missing_map_id, f"{missing_map_id}-B001-C01-S01", ""),
    )
    write(missing_map / "exercises/_README.md", "placeholder\n")
    courses[missing_map_id] = (missing_map, {"course_driver": "textbook"})

    reset(root)
    run_silently(doctor.check_exercises, courses)
    assert_message(doctor.fails, "Lesson 与活动连接表 ContentGroup 漂移")
    assert_message(doctor.fails, "Lesson 使用退役活动所有权字段")
    assert_message(doctor.fails, "教材课程有 Lesson/Exercise 但缺活动连接表")


def test_activity_map_duplicate_and_complete_coverage(root: Path) -> None:
    def lesson(course_id: str, lesson_id: str, groups: str) -> str:
        return (
            f"---\ntype: lesson\ncourse_id: {course_id}\nlesson_id: {lesson_id}\n"
            f"content_group_ids: [{groups}]\n---\n"
        )

    duplicate_id = "DUPL1001"
    duplicate = root / f"main/40_course/{duplicate_id}"
    write(
        duplicate / "lessons/lesson01/lesson01.md",
        lesson(duplicate_id, "lesson01", f"{duplicate_id}-B001-C01-S01"),
    )
    write(duplicate / "exercises/_README.md", "placeholder\n")
    write(
        duplicate / "activity_map.md",
        f"---\ntype: course_activity_map\ncourse_id: {duplicate_id}\n---\n"
        "## 内容组连接表\n\n"
        "| content_group_id | source_scope | lesson_ids | exercise_ids |\n"
        "|---|---|---|---|\n"
        f"| {duplicate_id}-B001-C01-S01 | B001 / C01 / S01 | lesson01, lesson01 | — |\n",
    )

    uncovered_id = "DUPL1002"
    uncovered = root / f"main/40_course/{uncovered_id}"
    write(
        uncovered / "lessons/lesson01/lesson01.md",
        lesson(uncovered_id, "lesson01", f"{uncovered_id}-B001-C01-S01"),
    )
    write(
        uncovered / "lessons/lesson02/lesson02.md",
        lesson(uncovered_id, "lesson02", ""),
    )
    write(uncovered / "exercises/_README.md", "placeholder\n")
    write(
        uncovered / "activity_map.md",
        f"---\ntype: course_activity_map\ncourse_id: {uncovered_id}\n---\n"
        "## 内容组连接表\n\n"
        "| content_group_id | source_scope | lesson_ids | exercise_ids |\n"
        "|---|---|---|---|\n"
        f"| {uncovered_id}-B001-C01-S01 | B001 / C01 / S01 | lesson01 | — |\n",
    )

    reset(root)
    run_silently(
        doctor.check_exercises,
        {
            duplicate_id: (duplicate, {"course_driver": "textbook"}),
            uncovered_id: (uncovered, {"course_driver": "textbook"}),
        },
    )
    assert_message(doctor.fails, "lesson_ids 重复")
    assert_message(doctor.fails, "Lesson 未在活动连接表中出现")


def test_retired_exercise_ownership_and_sessions(root: Path) -> None:
    reset(root)
    course = root / "main/40_course/TEST1001"
    unit = course / "exercises/U0001"
    write(
        unit / "exercise.md",
        "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\n"
        "lesson_ids: [lesson01]\ncontent_group_ids: []\n---\n",
    )
    write(
        unit / "problems.md",
        "---\ntype: exercise_problem_set\ncourse_id: TEST1001\nexercise_id: U0001\n---\n"
        "## U0001-Q001\n- 题号：1\n- 来源页：1\n- 难度：L1\n"
        "- 依赖 completion node：TEST1001-N01\n- 状态：open\n"
        "- 错误级别：none\n- 题面：test\n",
    )
    write(unit / "attempts/_README.md", "placeholder\n")
    write(unit / "reviews/_README.md", "placeholder\n")
    write(
        unit / "sessions/ES9999.md",
        "---\ntype: exercise_session\ncourse_id: TEST1001\n"
        "exercise_id: U0001\nsession_id: ES9999\n---\n",
    )
    run_silently(
        doctor.check_exercises,
        {"TEST1001": (course, {"course_driver": "goal"})},
    )
    assert_message(doctor.fails, "Exercise 使用退役活动所有权字段")
    assert_message(doctor.fails, "Exercise 包含退役 ExerciseSession")


def test_lesson_retired_ownership_all_drivers(root: Path) -> None:
    courses: dict[str, tuple[Path, dict[str, str]]] = {}
    for index, driver in enumerate(("textbook", "goal", "project", "praxis"), start=1):
        course_id = f"DRIVER{index:04d}"
        course = root / f"main/40_course/{course_id}"
        group_id = f"{course_id}-B001-C01-S01"
        write(
            course / "lessons/lesson01/lesson01.md",
            "---\ntype: lesson\n"
            f"course_id: {course_id}\nlesson_id: lesson01\n"
            f"content_group_ids: [{group_id if driver == 'textbook' else ''}]\n"
            "exercise_unit_ids: [U0001]\n---\n",
        )
        write(course / "exercises/_README.md", "placeholder\n")
        if driver == "textbook":
            write(
                course / "activity_map.md",
                "---\ntype: course_activity_map\n"
                f"course_id: {course_id}\n---\n"
                "## 内容组连接表\n\n"
                "| content_group_id | source_scope | lesson_ids | exercise_ids |\n"
                "|---|---|---|---|\n"
                f"| {group_id} | B001 / C01 / S01 | lesson01 | — |\n",
            )
        courses[course_id] = (course, {"course_driver": driver})

    reset(root)
    run_silently(doctor.check_exercises, courses)
    messages = [
        message for message in doctor.fails
        if "Lesson 使用退役活动所有权字段" in message
    ]
    if len(messages) != 4:
        raise AssertionError(f"retired Lesson ownership not driver-independent: {doctor.fails}")


def test_activity_workflows_share_executable_route(root: Path) -> None:
    content = (REPO / "main/50_playbook/lesson_recover.md").read_text(encoding="utf-8")
    close = (REPO / "main/50_playbook/session_close.md").read_text(encoding="utf-8")
    flow = (REPO / "main/50_playbook/t2ag_flow.md").read_text(encoding="utf-8")
    branch = content.find("### 步骤 3：按 current_activity 恢复主载体")
    lesson = content.find("#### `lesson` 分支")
    exercise = content.find("#### `exercise` 分支")
    working = content.find("### 步骤 5：条件读取 working_pages")
    if not (0 <= branch < lesson < exercise < working):
        raise AssertionError("lesson_recover does not branch before Lesson/working-pages consumers")
    required = (
        "Exercise 首启不得读取或构造 Lesson 路径",
        "current_lesson: none",
        "working_pages 仅在 `lesson` 分支",
        "t2ag_activity.py --course <COURSE_ID> --intent recover",
    )
    missing = [token for token in required if token not in content]
    if missing:
        raise AssertionError(f"lesson_recover missing Exercise-first guards: {missing}")
    forbidden_recovery = (
        "close_type: micro",
        "写入当前 lesson 问答记录",
        "`lessonXX.md` 的「当前教学进度」",
        "步骤 1.5 核对 question_bank",
    )
    leaked = [token for token in forbidden_recovery if token in content]
    if leaked:
        raise AssertionError(f"lesson_recover retains unconditional Lesson/deferred consumers: {leaked}")
    close_required = (
        "t2ag_activity.py --course <COURSE_ID> --intent close",
        "Micro close 和完整结课都必须原子完成",
        "Exercise 结课不得顺手",
        "不使用 `close_type: micro`",
    )
    missing_close = [token for token in close_required if token not in close]
    if missing_close:
        raise AssertionError(f"session_close missing atomic activity routing: {missing_close}")
    if (
        'G{"current_activity"}' not in flow
        or "共同强制事务：progress + 当前活动主载体 + 真实台账" not in flow
    ):
        raise AssertionError("flow view does not branch before activity consumers")

    for lesson_file in (REPO / "main/40_course").glob(
        "*/lessons/lesson*/lesson*.md"
    ):
        if "T2AG_GENERATED:LESSON_PROGRESS" in lesson_file.read_text(
            encoding="utf-8-sig"
        ):
            raise AssertionError(f"unowned Lesson GENERATED block: {lesson_file}")


def copy_release_without_links(source: Path, fixture: Path) -> None:
    excluded_parts = {
        ".git", ".venv", ".recovery", ".staging", ".uploads", "__pycache__",
        ".pytest_cache", ".mypy_cache", ".ruff_cache",
    }
    large_binary_suffixes = {".pdf", ".zip", ".docx", ".xlsx", ".pptx", ".exe"}
    required_source_documents: set[str] = set()
    for excerpt in source.glob(
        "main/40_course/*/book/primary/verified_excerpts/*.md"
    ):
        match = re.search(
            r"^source_document:\s*(.+?)\s*$",
            excerpt.read_text(encoding="utf-8-sig"),
            re.MULTILINE,
        )
        if match:
            required_source_documents.add(match.group(1).strip().strip('"'))
    for source_path in source.rglob("*"):
        relative = source_path.relative_to(source)
        if any(part in excluded_parts for part in relative.parts):
            continue
        target = fixture / relative
        if source_path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source_path.is_file() and (
            source_path.suffix.lower() not in large_binary_suffixes
            or relative.as_posix() in required_source_documents
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)


def materialize_synthetic_exercise_first(fixture: Path) -> str:
    course_id = "TEST1001"
    content_group = "TEST1001-B001-C01-S01"
    source_relative = (
        "main/40_course/TEST1001/book/primary/verified_excerpts/"
        "test1001_b001_c01_s01.md"
    )
    source = fixture / source_relative
    write(
        fixture / "main/10_student/profile/profile.md",
        "---\ntype: student_profile\ninitialization_status: initialized\n"
        "exercise_hint_gate: enabled\nupdated: 2026-07-26\n---\n"
        "# Synthetic profile\n\n"
        "## 每周可投入学习时间\n- 1 小时\n\n"
        "## 学习目标\n- 验证 Exercise-first 往返\n\n"
        "## 辅导与展现偏好\n- 逐步确认\n\n"
        "## 个体基线\n- 已有基础：合成测试\n",
    )
    skin = fixture / "main/80_interface/SK001_default/skin.yaml"
    skin.write_text(
        replace_frontmatter_field(
            skin.read_text(encoding="utf-8-sig"),
            "art_file",
            "03_inori_2.txt",
        ),
        encoding="utf-8",
        newline="\n",
    )
    cloud_state = fixture / "cloud/cloud_sync_state.md"
    state_content = cloud_state.read_text(encoding="utf-8-sig")
    state_content = replace_regex_exactly_once(
        state_content,
        r"^-\s*current_cloud_project_mode:\s*generic_skeleton\s*$",
        "- current_cloud_project_mode: personal_instance",
        label="Skeleton current_cloud_project_mode",
        flags=re.MULTILINE,
    )
    state_content = replace_exactly_once(
        state_content,
        "- cloud_bridge_status: paused\n",
        "- cloud_bridge_status: paused\n"
        "- new_cloud_sessions_allowed: false\n"
        "- new_component_directives_allowed: false\n",
        label="Skeleton cloud pause gates",
    )
    cloud_state.write_text(state_content, encoding="utf-8", newline="\n")
    cloud_prompt = fixture / "cloud/T2AG_PROJECT_INSTRUCTIONS.txt"
    prompt_content = cloud_prompt.read_text(encoding="utf-8-sig")
    prompt_content = replace_exactly_once(
        prompt_content,
        "cloud_project_mode: generic_skeleton",
        "cloud_project_mode: personal_instance",
        label="Skeleton cloud prompt flavor",
    )
    prompt_content += (
        "\n\npersonal_instance_protocol_markers:\n"
        "- T2AG_SESSION_CLOSE\n"
        "- T2AG_CLOUD_CHANGE_DIRECTIVE\n"
        "- T2AG_CLOUD_HANDOFF\n"
    )
    cloud_prompt.write_text(prompt_content, encoding="utf-8", newline="\n")
    write_teacher_mapping(fixture, (course_id,))
    document_relative = (
        "main/40_course/TEST1001/book/primary/source_documents/"
        "test1001_b001_c01_s01.txt"
    )
    document = fixture / document_relative
    write(document, "synthetic Exercise-first source document\n")
    document_sha = hashlib.sha256(document.read_bytes()).hexdigest()
    write(
        source,
        "---\ntype: verified_source_excerpt\n"
        "artifact_id: TEST1001_U0001_SOURCE\ncourse_id: TEST1001\n"
        f"content_group_id: {content_group}\n"
        f"source_document: {document_relative}\n"
        f"source_document_sha256: {document_sha}\n"
        "source_locator: synthetic problem 1\n"
        "verification_status: synthetic_verified\nverified: 2026-07-26\n"
        "lifecycle: persistent\n---\n# Synthetic source\n\n"
        "## U0001-Q001\n\n- 教材题号：1\n- 来源页：1\n"
        "- 题面：证明 1 = 1。\n",
    )
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    registry_path = fixture / "main/70_tools/artifact_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    registry.setdefault("artifacts", []).append({
        "artifact_id": "TEST1001_U0001_SOURCE",
        "canonical_path": source_relative,
        "redirects": [],
        "status": "active",
        "migration_reason": "synthetic contract fixture",
    })
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    course = fixture / f"main/40_course/{course_id}"
    write(
        course / "course.md",
        "---\ntype: course\ncourse_id: TEST1001\n"
        "school_course_code: TEST1001\nname: Synthetic Course\n"
        "course_type: mastery\ndefault_driver: textbook\n"
        "prerequisites: []\nstatus: active\n---\n# Synthetic Course\n",
    )
    write(
        course / "progress.md",
        "---\ntype: course_progress\ncourse_id: TEST1001\n"
        "lifecycle_status: ongoing\ncourse_driver: textbook\ntruth_source: true\n"
        "current_lesson: none\ncurrent_activity: exercise\n"
        "current_activity_id: U0001\n"
        "resume_path: main/40_course/TEST1001/exercises/U0001/exercise.md\n"
        "activity_position: synthetic start\nupdated: 2026-07-26\n"
        f"current_completion_node: {content_group}-N01\n"
        "current_checkpoint: TEST1001-B001-P001-N01\n"
        "checkpoint_state: queued\nnext_action: solve synthetic problem\n---\n"
        "# TEST1001 progress\n\n- **下一步计划**：solve synthetic problem\n\n"
        "## Completion nodes\n\n"
        "| node_id | 标题 | 来源范围 | 状态 | 完成证据 |\n"
        "|---|---|---|---|---|\n"
        f"| {content_group}-N01 | identity | synthetic | queued | — |\n",
    )
    write(
        course / "activity_map.md",
        "---\ntype: course_activity_map\ncourse_id: TEST1001\n"
        "updated: 2026-07-26\n---\n# Activity map\n\n"
        "## 内容组连接表\n\n"
        "| content_group_id | source_scope | lesson_ids | exercise_ids |\n"
        "|---|---|---|---|\n"
        f"| {content_group} | synthetic | — | U0001 |\n",
    )
    write(course / "lessons/_README.md", "No Lesson: Exercise-first fixture.\n")
    write(course / "book/README.md", "Synthetic persistent source.\n")
    write(
        course / "exercises/U0001/exercise.md",
        "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\n"
        f"content_group_ids: [{content_group}]\nstatus: ongoing\n"
        "created: 2026-07-26\n---\n# U0001\n\n## 学习记录\n",
    )
    write(
        course / "exercises/U0001/problems.md",
        "---\ntype: exercise_problem_set\ncourse_id: TEST1001\n"
        "exercise_id: U0001\n"
        f"content_group_id: {content_group}\n"
        "source_artifact_id: TEST1001_U0001_SOURCE\n"
        f"source_path: {source_relative}\n"
        "source_locator: synthetic problem 1\n"
        f"source_sha256: {source_sha}\n"
        "source_order: [U0001-Q001]\nteaching_sequence: [U0001-Q001]\n"
        "status: active\n---\n# Problems\n\n## U0001-Q001\n\n"
        "- 题号：1\n- 来源页：1\n- 难度：未评估\n"
        f"- 依赖 completion node：`{content_group}-N01`\n"
        "- 状态：open\n- 错误级别：—\n- 题面：证明 1 = 1。\n",
    )
    (course / "exercises/U0001/attempts").mkdir(parents=True, exist_ok=True)
    (course / "exercises/U0001/reviews").mkdir(parents=True, exist_ok=True)
    write(
        course / "question_bank.md",
        "---\ntype: question_bank\ncourse_id: TEST1001\nnext_id: 1\n---\n"
        "<!-- QUESTION_BANK_TEMPLATE_V2 -->\n# Questions\n",
    )
    write(
        course / "mistake_bank.md",
        "---\ntype: mistake_bank\ncourse_id: TEST1001\nnext_id: 1\n---\n"
        "# Mistakes\n\n## 活跃知识点\n\n## 维护知识点\n\n## 陈年知识点\n",
    )
    group = fixture / "main/30_group/G01"
    write(
        group / "plan.md",
        "---\ntype: group\ngroup_id: G01\nstatus: active\n"
        "course_members: [TEST1001]\nengagement_members: []\n"
        "current_course: TEST1001\nupdated: 2026-07-26\n---\n# G01\n",
    )
    write(
        group / "calendar.md",
        "---\ntype: group_calendar\ngroup_id: G01\nstatus: active\n"
        "updated: 2026-07-26\n---\n# Calendar\n",
    )
    write(
        group / "review.md",
        "---\ntype: group_review\ngroup_id: G01\nstatus: open\n"
        "updated: 2026-07-26\n---\n# Review\n",
    )
    (group / "bindings").mkdir(parents=True, exist_ok=True)
    return course_id


def test_activity_cli_disk_roundtrip(root: Path) -> None:
    source = REPO
    fixture_name = "t2ag-lite" if source.name == "t2ag-lite" else "release-under-test"
    fixture = root / fixture_name
    copy_release_without_links(source, fixture)
    if (source / ".git/objects").is_dir():
        subprocess.run(
            ["git", "init", "--quiet", str(fixture)],
            check=True,
            capture_output=True,
        )
        write(
            fixture / ".git/objects/info/alternates",
            str((source / ".git/objects").resolve()) + "\n",
        )

    def detached_write(path: Path, content: str) -> None:
        temporary = path.with_name(path.name + ".e2e-tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)

    def cli(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [
                sys.executable, "-B", str(fixture / f"main/70_tools/{script}"),
                *arguments,
            ],
            cwd=fixture,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )
        if result.returncode:
            raise AssertionError(
                f"CLI failed: {script} {' '.join(arguments)}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def assert_doctor_flavor(
        result: subprocess.CompletedProcess[str],
        expected: str,
    ) -> None:
        marker = f"[INFO] release_flavor: {expected}"
        if marker not in result.stdout:
            raise AssertionError(
                f"Doctor flavor mismatch; expected {expected}:\n{result.stdout}"
            )

    profile = fixture / "main/10_student/profile/profile.md"
    uninitialized = "initialization_status: uninitialized" in profile.read_text(
        encoding="utf-8-sig"
    )
    if uninitialized:
        cli("t2ag_state_refresh.py", "--check")
        skeleton_doctor = cli("t2ag_doctor.py")
        assert_doctor_flavor(skeleton_doctor, "skeleton")
        cli("migrate_020.py", "--check", "--target", "skeleton")
        if list((fixture / "main/40_course").glob("*/progress.md")):
            raise AssertionError("Skeleton release E2E unexpectedly contains a course")
        course_id = materialize_synthetic_exercise_first(fixture)
        expected_runtime_flavor = "main"
    else:
        expected_runtime_flavor = "lite" if source.name == "t2ag-lite" else "main"
        candidates = []
        for candidate in sorted((fixture / "main/40_course").glob("*/progress.md")):
            content = candidate.read_text(encoding="utf-8-sig")
            if (
                re.search(r"^lifecycle_status:\s*ongoing\s*$", content, re.MULTILINE)
                and re.search(r"^current_activity:\s*exercise\s*$", content, re.MULTILINE)
            ):
                candidates.append(candidate.parent.name)
        if not candidates:
            raise AssertionError("initialized release has no ongoing Exercise for disk E2E")
        course_id = candidates[0]

    progress_path = fixture / f"main/40_course/{course_id}/progress.md"
    source_progress = source / progress_path.relative_to(fixture)
    if source_progress.is_file() and os.path.samefile(source_progress, progress_path):
        raise AssertionError("release fixture reused a hardlink to the source progress")

    progress = progress_path.read_text(encoding="utf-8-sig")
    current_lesson = re.search(
        r"^current_lesson:\s*(.*?)\s*$",
        progress,
        re.MULTILINE,
    )
    if not current_lesson:
        raise AssertionError("E2E fixture progress lacks current_lesson")
    progress = replace_frontmatter_field(
        progress,
        "current_lesson",
        "none",
        expected=current_lesson.group(1),
    )
    detached_write(progress_path, progress)

    course_root = fixture / f"main/40_course/{course_id}"
    historical_lessons = {
        lesson: hashlib.sha256(lesson.read_bytes()).hexdigest()
        for lesson in course_root.glob("lessons/lesson*/lesson*.md")
    }
    for working_root in course_root.glob("lessons/lesson*/working_pages"):
        if fixture.resolve() not in working_root.resolve().parents:
            raise AssertionError(f"refusing to clear cache outside fixture: {working_root}")
        shutil.rmtree(working_root)

    cli("t2ag_state_refresh.py", "--write")
    memory_path = fixture / "main/00_core/t2ag_memory.md"
    memory = memory_path.read_text(encoding="utf-8-sig")
    activity_id_match = re.search(
        r"^current_activity_id:\s*(U\d{4})\s*$",
        progress,
        re.MULTILINE,
    )
    if not activity_id_match:
        raise AssertionError("E2E fixture is not an Exercise activity")
    activity_id = activity_id_match.group(1)
    if "| Lesson 上下文 | 无 | — |" not in memory:
        raise AssertionError(f"disk refresh retained an active Lesson:\n{memory}")
    if f"| 当前教学活动 | exercise: {activity_id} |" not in memory:
        raise AssertionError(f"disk refresh lost the Exercise pointer:\n{memory}")
    cli("t2ag_state_refresh.py", "--check")
    doctor_after_write = cli("t2ag_doctor.py")
    assert_doctor_flavor(doctor_after_write, expected_runtime_flavor)

    recover = json.loads(
        cli(
            "t2ag_activity.py", "--course", course_id, "--intent", "recover",
        ).stdout
    )
    expected_carrier = (
        f"main/40_course/{course_id}/exercises/{activity_id}/exercise.md"
    )
    if recover["primary_read"] != expected_carrier:
        raise AssertionError(f"recover routed away from Exercise: {recover}")
    if recover["working_pages"] is not None:
        raise AssertionError(f"Exercise recover inherited working pages: {recover}")
    for relative in recover["activity_read_targets"]:
        if not (fixture / relative).is_file():
            raise AssertionError(f"recover target was not read-resolvable: {relative}")

    close = json.loads(
        cli(
            "t2ag_activity.py", "--course", course_id, "--intent", "close",
        ).stdout
    )
    activity_target = fixture / close["activity_write_target"]
    if "lessons/" in close["activity_write_target"]:
        raise AssertionError(f"Exercise close routed into Lesson: {close}")
    for relative in close["mandatory_write_targets"]:
        if not (fixture / relative).is_file():
            raise AssertionError(f"mandatory close target missing: {relative}")

    progress_before_close = progress_path.read_bytes()
    current_position = re.search(
        r"^activity_position:\s*(.*?)\s*$",
        progress_before_close.decode("utf-8-sig"),
        re.MULTILINE,
    )
    if not current_position:
        raise AssertionError("E2E close fixture lacks activity_position")
    new_position = f"E2E Micro close；{course_id}/{activity_id}"
    closed_progress = replace_frontmatter_field(
        progress_before_close.decode("utf-8-sig"),
        "activity_position",
        new_position,
        expected=current_position.group(1),
    )
    detached_write(progress_path, closed_progress)
    if progress_path.read_bytes() == progress_before_close:
        raise AssertionError("Exercise close progress write was a silent no-op")
    if f"activity_position: {new_position}" not in progress_path.read_text(
        encoding="utf-8-sig"
    ):
        raise AssertionError("Exercise close progress field was not persisted")

    activity_content = activity_target.read_text(encoding="utf-8-sig")
    detached_write(
        activity_target,
        activity_content + "\n\n- E2E Micro close：已保存精确停点；无新增提交。\n",
    )
    refresh = cli("t2ag_state_refresh.py", "--write")
    changed = re.search(r"state refresh:\s*(\d+)\s+changed", refresh.stdout)
    if not changed or int(changed.group(1)) < 1:
        raise AssertionError(f"close refresh did not persist GENERATED state:\n{refresh.stdout}")
    cli("t2ag_state_refresh.py", "--check")
    doctor_after_close = cli("t2ag_doctor.py")
    assert_doctor_flavor(doctor_after_close, expected_runtime_flavor)

    memory_after = memory_path.read_text(encoding="utf-8-sig")
    if new_position not in memory_after:
        raise AssertionError("GENERATED memory did not roundtrip the new progress stop")
    for lesson, before_hash in historical_lessons.items():
        if hashlib.sha256(lesson.read_bytes()).hexdigest() != before_hash:
            raise AssertionError(f"Exercise close modified historical Lesson: {lesson}")
    if "E2E Micro close" not in activity_target.read_text(encoding="utf-8-sig"):
        raise AssertionError("Exercise close did not persist to the routed carrier")
    if "close_type:" in progress_path.read_text(encoding="utf-8-sig"):
        raise AssertionError("Micro close created a deferred close marker")


def test_candidate_replay_isolation_contract(root: Path) -> None:
    polluted = {
        "PATH": os.environ.get("PATH", ""),
        "Git_Dir": "C:/poison",
        "GIT_OBJECT_DIRECTORY": "C:/objects",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.worktree",
        "GIT_CONFIG_VALUE_0": "C:/outside",
    }
    clean = candidate_replay.sanitized_git_environment(polluted)
    leaked = [key for key in clean if key.upper().startswith("GIT_") and key not in {
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_ATTR_NOSYSTEM",
        "GIT_NO_LAZY_FETCH",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_TERMINAL_PROMPT",
    }]
    if leaked or clean.get("GIT_CONFIG_NOSYSTEM") != "1":
        raise AssertionError(f"candidate Git environment was not sanitized: {leaked}")

    source = root / "source"
    source.mkdir(parents=True)
    env = candidate_replay.sanitized_git_environment()

    def git(*arguments: str) -> None:
        result = subprocess.run(
            ["git", "-C", str(source), *arguments],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if result.returncode:
            raise AssertionError(
                f"synthetic Git setup failed: {arguments}\n"
                f"{result.stdout}\n{result.stderr}"
            )

    git("init")
    write(source / "tracked.txt", "base\n")
    write(source / "outside.txt", "old outside content\n")
    git("add", "--", "tracked.txt", "outside.txt")
    git(
        "-c", "user.name=T2AG Contract",
        "-c", "user.email=contract@example.invalid",
        "commit", "-m", "base",
    )
    write(source / "candidate.txt", "candidate\n")
    result = candidate_replay.replay_candidate(source, root / "workspace")
    if (
        not result["source_unchanged"]
        or not result["file_ids_disjoint"]
        or not result["whitespace_ok"]
        or result["file_count"] != 3
    ):
        raise AssertionError(f"isolated synthetic replay failed: {result}")

    gitfile = root / "gitfile"
    gitfile.mkdir()
    write(gitfile / ".git", "gitdir: C:/outside\n")
    try:
        candidate_replay.validate_repository_layout(gitfile)
    except candidate_replay.CandidateIsolationError:
        pass
    else:
        raise AssertionError("candidate preflight accepted a gitfile")

    for label, relative in (
        ("commondir", ".git/commondir"),
        ("alternates", ".git/objects/info/alternates"),
        ("http-alternates", ".git/objects/info/http-alternates"),
    ):
        poisoned = root / f"poison-{label}"
        shutil.copytree(source, poisoned, copy_function=shutil.copy2)
        write(poisoned / relative, "C:/outside\n")
        try:
            candidate_replay.validate_repository_layout(poisoned)
        except candidate_replay.CandidateIsolationError:
            pass
        else:
            raise AssertionError(f"candidate preflight accepted {label}")

    external_worktree = root / "poison-worktree"
    shutil.copytree(source, external_worktree, copy_function=shutil.copy2)
    with (external_worktree / ".git/config").open("a", encoding="utf-8") as handle:
        handle.write("\n[core]\n\tworktree = C:/outside\n")
    try:
        candidate_replay.validate_repository_layout(external_worktree)
    except candidate_replay.CandidateIsolationError:
        pass
    else:
        raise AssertionError("candidate preflight accepted external core.worktree")

    fsmonitor_false = root / "allow-fsmonitor-false"
    shutil.copytree(source, fsmonitor_false, copy_function=shutil.copy2)
    with (fsmonitor_false / ".git/config").open("a", encoding="utf-8") as handle:
        handle.write("\n[core]\n\tfsmonitor = false\n")
    candidate_replay.validate_repository_layout(fsmonitor_false)

    fsmonitor_true = root / "reject-fsmonitor-true"
    shutil.copytree(source, fsmonitor_true, copy_function=shutil.copy2)
    with (fsmonitor_true / ".git/config").open("a", encoding="utf-8") as handle:
        handle.write("\n[core]\n\tfsmonitor = true\n")
    try:
        candidate_replay.validate_repository_layout(fsmonitor_true)
    except candidate_replay.CandidateIsolationError:
        pass
    else:
        raise AssertionError("candidate preflight accepted core.fsmonitor=true")

    for label, section, key in (
        ("core-sparse", "core", "sparseCheckout"),
        ("core-sparse-cone", "core", "sparseCheckoutCone"),
        ("index-sparse", "index", "sparse"),
    ):
        sparse_config = root / f"reject-{label}"
        shutil.copytree(source, sparse_config, copy_function=shutil.copy2)
        with (sparse_config / ".git/config").open(
            "a", encoding="utf-8",
        ) as handle:
            handle.write(f"\n[{section}]\n\t{key} = true\n")
        try:
            candidate_replay.validate_repository_layout(sparse_config)
        except candidate_replay.CandidateIsolationError:
            pass
        else:
            raise AssertionError(
                f"candidate preflight accepted sparse setting {section}.{key}"
            )

    sparse_file = root / "reject-sparse-file"
    shutil.copytree(source, sparse_file, copy_function=shutil.copy2)
    write(sparse_file / ".git/info/sparse-checkout", "/tracked.txt\n")
    try:
        candidate_replay.validate_repository_layout(sparse_file)
    except candidate_replay.CandidateIsolationError:
        pass
    else:
        raise AssertionError("candidate preflight accepted info/sparse-checkout")

    sparse_silent_loss = root / "reject-sparse-silent-loss"
    shutil.copytree(source, sparse_silent_loss, copy_function=shutil.copy2)
    with (sparse_silent_loss / ".git/config").open(
        "a", encoding="utf-8",
    ) as handle:
        handle.write(
            "\n[core]\n\tsparseCheckout = true\n"
            "\tsparseCheckoutCone = true\n[index]\n\tsparse = true\n"
        )
    write(sparse_silent_loss / ".git/info/sparse-checkout", "/tracked.txt\n")
    write(sparse_silent_loss / "outside.txt", "modified outside sparse cone\n")
    try:
        candidate_replay.replay_candidate(
            sparse_silent_loss,
            root / "sparse-silent-loss-workspace",
        )
    except candidate_replay.CandidateIsolationError:
        pass
    else:
        raise AssertionError(
            "candidate replay accepted a sparse worktree with an outside modification"
        )

    one = root / "identity-one"
    two = root / "identity-two"
    shutil.copytree(source, one, copy_function=shutil.copy2)
    shutil.copytree(source, two, copy_function=shutil.copy2)
    one_records = candidate_replay.inspect_tree(one)
    two_records = candidate_replay.inspect_tree(two)
    candidate_replay.assert_byte_manifest_equal(one_records, two_records, "clean copy")
    write(two / "candidate.txt", "different\n")
    two_records = candidate_replay.inspect_tree(two)
    try:
        candidate_replay.assert_byte_manifest_equal(
            one_records, two_records, "mutated copy",
        )
    except candidate_replay.CandidateIsolationError:
        pass
    else:
        raise AssertionError("candidate manifest accepted a byte difference")

    hardlink_copy = root / "hardlink-copy"
    shutil.copytree(source, hardlink_copy, copy_function=shutil.copy2)
    hardlink_target = hardlink_copy / "candidate.txt"
    hardlink_target.unlink()
    os.link(source / "candidate.txt", hardlink_target)
    try:
        candidate_replay.inspect_tree(hardlink_copy)
    except candidate_replay.CandidateIsolationError:
        pass
    else:
        raise AssertionError("candidate preflight accepted a shared File ID")

    race_source = root / "race-source"
    shutil.copytree(source, race_source, copy_function=shutil.copy2)
    original_inspect_tree = candidate_replay.inspect_tree
    copy_two_scans = 0

    def race_inspect_tree(path: Path) -> dict[str, candidate_replay.FileRecord]:
        nonlocal copy_two_scans
        records = original_inspect_tree(path)
        if Path(path).name == "copy-2":
            copy_two_scans += 1
            if copy_two_scans == 2:
                write(
                    race_source / "candidate.txt",
                    "teaching write after all A/B replay work\n",
                )
        return records

    candidate_replay.inspect_tree = race_inspect_tree
    try:
        try:
            candidate_replay.replay_candidate(
                race_source,
                root / "race-workspace",
            )
        except candidate_replay.CandidateIsolationError:
            pass
        else:
            raise AssertionError(
                "candidate replay missed a source write during final A/B checks"
            )
    finally:
        candidate_replay.inspect_tree = original_inspect_tree


def test_migration_manifest_tamper(root: Path) -> None:
    reset(root)
    write(
        root / "main/60_journal/migration_020_operations.json",
        '{"operation_count":1,"operations":[{"sequence":1,"kind":"copy",'
        '"sources":[{"path":"a","bytes":1,"sha256":"' + "1" * 64 + '"}],'
        '"target":"b","disposition":"test","post_target":{"path":"b",'
        '"bytes":1,"sha256":"' + "2" * 64 + '"}}]}\n',
    )
    write(
        root / "main/60_journal/migration_020_report.json",
        '{"status":"applied","applied_count":1,"post_apply_duplicate_active_canonicals":[],'
        '"operation_manifest":{"operation_count":1,"sha256":"' + "0" * 64 + '"}}\n',
    )
    run_silently(doctor.check_migration_evidence)
    assert_message(doctor.fails, "SHA 漂移")


def test_migration_manifest_missing_reference(root: Path) -> None:
    reset(root)
    write(
        root / "main/60_journal/migration_020_operations.json",
        '{"operation_count":1,"operations":[{"sequence":1,"kind":"copy",'
        '"sources":[{"path":"a","bytes":1,"sha256":"' + "1" * 64 + '"}],'
        '"target":"b","disposition":"test","post_target":{"path":"b",'
        '"bytes":1,"sha256":"' + "2" * 64 + '"}}]}\n',
    )
    write(
        root / "main/60_journal/migration_020_report.json",
        '{"status":"applied","applied_count":1,'
        '"post_apply_duplicate_active_canonicals":[]}\n',
    )
    run_silently(doctor.check_migration_evidence)
    assert_message(doctor.fails, "缺 operation_manifest 引用块")


def test_main_readme_skeleton_reference_does_not_change_migration_kind(root: Path) -> None:
    reset(root, flavor="main")
    write(
        root / "README.md",
        "# T2AG\n\n通用能力在 ../t2ag-skeleton/ 收敛。\n",
    )
    write_formal_lite_migration_evidence(
        root,
        "main/example.bin",
        "a" * 64,
    )
    run_silently(doctor.check_migration_evidence)
    if doctor.fails:
        raise AssertionError(
            f"Main README cross-reference changed migration identity: {doctor.fails}"
        )


def test_profile_migration_manifest_tamper(root: Path) -> None:
    reset(root)
    write(
        root / "main/60_journal/migration_021_profile_operations.json",
        '{"schema_version":"T2AG-MIGRATION-OPERATIONS-1",'
        '"target_kind":"main","operation_count":4,"operations":[]}\n',
    )
    write(
        root / "main/60_journal/migration_021_profile_report.json",
        '{"status":"applied","applied_count":4,'
        '"operation_manifest":{"path":'
        '"main/60_journal/migration_021_profile_operations.json",'
        '"operation_count":4,"sha256":"' + "0" * 64 + '"}}\n',
    )
    run_silently(doctor.check_migration_021_evidence)
    assert_message(doctor.fails, "V1/V2 迁移操作清单或报告")


def test_profile_migration_roundtrip(root: Path) -> None:
    for index, (source, target) in enumerate(migration_021.MOVES, start=1):
        write(root / source, f"profile fixture {index}\n")
        if (root / target).exists():
            raise AssertionError("fixture unexpectedly contains migration target")
    state = migration_021.inspect(root)
    if state["pending_count"] != 4 or state["missing"] or state["collisions"]:
        raise AssertionError(f"invalid migration preflight: {state}")
    if migration_021.apply(root) != 4:
        raise AssertionError("profile migration did not apply all four moves")
    for index, (source, target) in enumerate(migration_021.MOVES, start=1):
        if (root / source).exists():
            raise AssertionError(f"legacy profile path survived: {source}")
        if (root / target).read_text(encoding="utf-8") != f"profile fixture {index}\n":
            raise AssertionError(f"profile content changed: {target}")
    if migration_021.apply(root) != 0:
        raise AssertionError("profile migration is not idempotent")

    collision = root / "collision"
    source, target = migration_021.MOVES[0]
    write(collision / source, "source\n")
    write(collision / target, "different\n")
    if not migration_021.inspect(collision)["collisions"]:
        raise AssertionError("profile migration missed a target collision")
    try:
        migration_021.apply(collision)
    except RuntimeError:
        pass
    else:
        raise AssertionError("profile migration applied across a collision")


def main() -> int:
    tests = (
        test_profile_placeholder,
        test_profile_container_contract,
        test_resume_path,
        test_explicit_activity_pointer_required,
        test_exercise_first_course_resume,
        test_progress_identity_is_shared,
        test_teacher_mapping_is_strict,
        test_teacher_presentation_contract,
        test_fixture_mutations_cannot_silently_noop,
        test_state_refresh_activity_roundtrip,
        test_exercise_current_lesson_driver_matrix,
        test_planned_activity_fields_rejected,
        test_working_pages_activity_matrix,
        test_skin_art,
        test_course_activity_templates,
        test_flow_and_offline_guide,
        test_hint_gate_contract,
        test_exercise_evidence,
        test_exercise_activity_links,
        test_project_completion_evidence,
        test_project_completion_step_summary_required,
        test_textbook_dependency_contract,
        test_persistent_exercise_source_contract,
        test_activity_map_strict_bidirectionality,
        test_activity_map_duplicate_and_complete_coverage,
        test_retired_exercise_ownership_and_sessions,
        test_lesson_retired_ownership_all_drivers,
        test_activity_workflows_share_executable_route,
        test_activity_cli_disk_roundtrip,
        test_candidate_replay_isolation_contract,
        test_migration_manifest_tamper,
        test_migration_manifest_missing_reference,
        test_main_readme_skeleton_reference_does_not_change_migration_kind,
        test_profile_migration_manifest_tamper,
        test_profile_migration_roundtrip,
    )
    with tempfile.TemporaryDirectory(prefix="t2ag_contracts_") as tmp:
        base = Path(tmp)
        for index, test in enumerate(tests, start=1):
            root = base / f"case_{index}"
            test(root)
            print(f"PASS {test.__name__}")
    print(f"result: {len(tests)}/{len(tests)} contract/integration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
