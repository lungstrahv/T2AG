#!/usr/bin/env python3
"""Shared atomic contract assertions; selected by domain-specific test runners."""
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
import zipfile
import sys
import tempfile
from pathlib import Path
from unittest import mock

import activity_ledger as ledger_contract
import t2ag_activity as activity
import t2ag_hint_gate as hint_gate


SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parents[2]
spec = importlib.util.spec_from_file_location("t2ag_doctor_under_test", SCRIPT.with_name("t2ag_doctor.py"))
doctor = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(doctor)

lite_spec = importlib.util.spec_from_file_location(
    "sync_lite_under_test", SCRIPT.with_name("sync_lite.py")
)
sync_lite = importlib.util.module_from_spec(lite_spec)
assert lite_spec and lite_spec.loader
lite_spec.loader.exec_module(sync_lite)

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


# Doctor parses the running version out of main/t2ag.md.  A bare version string
# is NOT parseable by extract_runtime_version, and check_version_and_profile
# bails out early when parsing fails — which silently skips every assertion that
# comes after it in the same check.  Fixture constitutions must therefore use a
# shape the parser can actually read, otherwise a green-looking fixture hides the
# behaviour under test.
FIXTURE_VERSION = "0.2.2"
FIXTURE_CONSTITUTION = (
    f"# T2AG {FIXTURE_VERSION}\n\n- 当前运行版本：`{FIXTURE_VERSION}`\n"
)


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


def ensure_teacher_mapping_row(
    root: Path,
    course_id: str,
    existing_course_ids: set[str],
) -> None:
    """Add one synthetic mapping without rewriting any existing course route."""
    overlay = root / "main/20_teacher/overlay.md"
    if not overlay.is_file():
        write_teacher_mapping(root, (course_id,))
        return

    before = doctor.resolve_teacher_mapping(root, existing_course_ids)
    raw = overlay.read_bytes()
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    content = raw[len(bom):].decode("utf-8")
    course_rows = list(re.finditer(
        rf"(?m)^\|\s*{re.escape(course_id)}\s*\|",
        content,
    ))
    if len(course_rows) > 1:
        raise AssertionError(f"duplicate teacher mapping row: {course_id}")
    if not course_rows:
        default_rows = list(re.finditer(r"(?m)^\|\s*\([^|\r\n]+\)\s*\|", content))
        if len(default_rows) != 1:
            raise AssertionError(
                "teacher overlay must contain exactly one default mapping row"
            )
        newline = "\r\n" if "\r\n" in content else "\n"
        row = (
            f"| {course_id} | Synthetic Course | "
            "`main/20_teacher/T001.md` | test |" + newline
        )
        content = content[:default_rows[0].start()] + row + content[default_rows[0].start():]
        overlay.write_bytes(bom + content.encode("utf-8"))

    after = doctor.resolve_teacher_mapping(root, existing_course_ids | {course_id})
    changed = {
        existing_id: (before[existing_id], after.get(existing_id))
        for existing_id in existing_course_ids
        if after.get(existing_id) != before[existing_id]
    }
    if changed:
        raise AssertionError(f"materialize changed existing teacher mappings: {changed}")


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


def write_validation_foundation_fixture(root: Path) -> None:
    """Seed the structural minimum required by Doctor's base-profile check."""
    for relative in doctor.BASE_VALIDATION_FILES:
        content = "# validation foundation fixture\n"
        if relative == "main/70_tools/t2ag_doctor.py":
            content = "\n".join(doctor.BASE_DOCTOR_PROFILE_MARKERS) + "\n"
        write(root / relative, content)


def run_silently(function, *args) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        function(*args)


def assert_message(collection: list[str], token: str) -> None:
    if not any(token in message for message in collection):
        raise AssertionError(f"expected diagnostic containing {token!r}; actual={collection}")


def test_profile_placeholder(root: Path) -> None:
    del root
    errors = doctor.initialized_profile_content_errors(
        "## 学习兴趣\n\n- （待填写）\n"
    )
    assert errors == ["initialized profile 仍含首次启动必填占位符"], errors
    optional = doctor.initialized_profile_content_errors(
        "## 学习兴趣\n\n- 有待生成\n\n## 自我介绍\n\n未提供\n"
    )
    assert optional == [], optional


def test_profile_container_contract(root: Path) -> None:
    def build(case_root: Path) -> None:
        for domain in doctor.EXPECTED_DOMAINS:
            (case_root / "main" / domain).mkdir(parents=True, exist_ok=True)
        write_validation_foundation_fixture(case_root)
        write(case_root / "main/t2ag.md", FIXTURE_CONSTITUTION)
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


def _checkpoint_progress(rows: str, *, ckpt: str = "X", state: str = "queued") -> str:
    """Minimal progress.md text for checkpoint-projection contracts (P-0058)."""
    return (
        "---\n"
        "type: course_progress\n"
        "course_id: TEST1001\n"
        "lifecycle_status: ongoing\n"
        f"current_checkpoint: {ckpt}\n"
        f"checkpoint_state: {state}\n"
        "truth_scope: course_lifecycle\n"
        "---\n"
        "\n"
        "## 当前窗口 checkpoints\n"
        "\n"
        "| checkpoint_id | parent_node | 页码 | block_id | 到达内容 | 状态 |\n"
        "|---|---|---:|---|---|---|\n"
        f"{rows}"
        "\n"
        "## 维护规则\n"
    )


def _projection_course(root: Path, content: str, lifecycle: str = "ongoing"):
    return state_refresh.Course(
        course_id="TEST1001",
        name="Test",
        lifecycle=lifecycle,
        current_activity="lesson",
        activity_id="lesson01",
        resume_path="",
        lesson_context="",
        lesson_context_path="",
        position="",
        updated="",
        node="",
        checkpoint="",
        checkpoint_state="",
        next_action="",
        path=root / "main/40_course/TEST1001/progress.md",
        content=content,
    )


def test_checkpoint_projection_uses_table_not_frontmatter(root: Path) -> None:
    """P-0058: the table is authoritative; the frontmatter is its projection."""
    open_row = "| C-N02 | P01 | 30 | B#02 | 讲 | pending |\n"
    content = _checkpoint_progress(
        "| C-N01 | P01 | 30 | B#01 | 讲 | confirmed |\n" + open_row,
        ckpt="stale",
        state="confirmed",
    )
    projected = state_refresh.planned_progress_projections(
        {"TEST1001": _projection_course(root, content)}
    )
    if len(projected) != 1:
        raise AssertionError(f"expected one projection, got {len(projected)}")
    text = projected[0][1]
    if "current_checkpoint: C-N02" not in text or "checkpoint_state: pending" not in text:
        raise AssertionError(f"open row not projected into frontmatter:\n{text}")

    # All confirmed -> `none / none`, never the last confirmed id.  This is the
    # exact value a human hand-wrote wrongly on 2026-08-07 13:54.
    all_confirmed = _checkpoint_progress(
        "| C-N01 | P01 | 30 | B#01 | 讲 | confirmed |\n"
        "| C-N02 | P01 | 30 | B#02 | 讲 | confirmed |\n",
        ckpt="C-N02",
        state="confirmed",
    )
    text = state_refresh.planned_progress_projections(
        {"TEST1001": _projection_course(root, all_confirmed)}
    )[0][1]
    if "current_checkpoint: none" not in text or "checkpoint_state: none" not in text:
        raise AssertionError(f"all-confirmed table must project none/none:\n{text}")

    # Idempotent: projecting the projection changes nothing.
    again = state_refresh.planned_progress_projections(
        {"TEST1001": _projection_course(root, text)}
    )[0][1]
    if again != text:
        raise AssertionError("checkpoint projection is not idempotent")


def test_checkpoint_projection_is_fail_closed(root: Path) -> None:
    """P-0058 §3.3: a parse failure must fail the run, not blank the pointer."""
    malformed = _checkpoint_progress("| C-N01 | 讲 |\n")
    try:
        state_refresh.planned_progress_projections(
            {"TEST1001": _projection_course(root, malformed)}
        )
    except ValueError as exc:
        if "列数异常" not in str(exc):
            raise AssertionError(f"unexpected fail-closed error: {exc}") from exc
    else:
        raise AssertionError("malformed checkpoint row silently projected none")

    try:
        state_refresh.derive_current_checkpoint("no table here", strict=True)
    except ValueError as exc:
        if "表头" not in str(exc):
            raise AssertionError(f"unexpected missing-table error: {exc}") from exc
    else:
        raise AssertionError("missing checkpoint table accepted under strict")

    # Non-strict keeps the legacy display behaviour for planned courses.
    if state_refresh.derive_current_checkpoint("no table here") != ("none", "none"):
        raise AssertionError("non-strict derive must stay backward compatible")


def test_checkpoint_projection_scope_is_narrow(root: Path) -> None:
    """Only ongoing courses that already have a table get a projection."""
    fresh = (
        "---\ntype: course_progress\ncourse_id: TEST1001\n"
        "lifecycle_status: ongoing\ncurrent_checkpoint: CHECKPOINT\n"
        "checkpoint_state: queued\n---\n# no table yet\n"
    )
    if state_refresh.planned_progress_projections(
        {"TEST1001": _projection_course(root, fresh)}
    ):
        raise AssertionError(
            "freshly initialised course (template frontmatter, no table) "
            "must not be projected"
        )
    planned = _checkpoint_progress("| C-N01 | P01 | 30 | B#01 | 讲 | pending |\n")
    if state_refresh.planned_progress_projections(
        {"TEST1001": _projection_course(root, planned, lifecycle="planned")}
    ):
        raise AssertionError("non-ongoing course must not be projected")


def test_replace_frontmatter_fields_is_byte_preserving(root: Path) -> None:
    """Only the targeted key lines may change; a missing key must raise."""
    content = _checkpoint_progress("| C-N01 | P01 | 30 | B#01 | 讲 | pending |\n")
    updated = state_refresh.replace_frontmatter_fields(
        content, {"checkpoint_state": "none"}
    )
    changed = [
        (before, after)
        for before, after in zip(content.split("\n"), updated.split("\n"))
        if before != after
    ]
    if changed != [("checkpoint_state: queued", "checkpoint_state: none")]:
        raise AssertionError(f"frontmatter rewrite was not byte-preserving: {changed}")
    if len(content.split("\n")) != len(updated.split("\n")):
        raise AssertionError("frontmatter rewrite changed the line count")

    try:
        state_refresh.replace_frontmatter_fields(content, {"absent_key": "x"})
    except ValueError as exc:
        if "缺少字段" not in str(exc):
            raise AssertionError(f"unexpected missing-key error: {exc}") from exc
    else:
        raise AssertionError("missing frontmatter key was silently appended")


def test_state_refresh_activity_roundtrip(root: Path) -> None:
    reset_state(root)
    course = root / "main/40_course/TEST1001"
    write(
        course / "course.md",
        "---\ntype: course\ncourse_id: TEST1001\nname: Test Course\n"
        "course_type: mastery\ndefault_driver: goal\n---\n",
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
    # Legacy read compatibility covers the three Mastery modes.  Praxis is a
    # Course Type now, not a fourth Mastery driver.
    drivers = ("textbook", "goal", "project")

    for course_meta, progress_meta, expected in (
        ({"course_type": "mastery", "learning_mode": "textbook"}, {}, ("mastery", "textbook")),
        ({"course_type": "project"}, {}, ("project", None)),
        ({"course_type": "praxis"}, {}, ("praxis", None)),
        ({"course_type": "mastery", "default_driver": "goal"}, {"course_driver": "goal"}, ("mastery", "goal")),
    ):
        progression = activity.resolve_course_progression(course_meta, progress_meta)
        assert (progression.course_type, progression.learning_mode) == expected
    for course_meta, progress_meta in (
        ({"course_type": "mastery", "learning_mode": "praxis"}, {}),
        ({"course_type": "project", "learning_mode": "project"}, {}),
        ({"course_type": "praxis"}, {"course_driver": "goal"}),
    ):
        try:
            activity.resolve_course_progression(course_meta, progress_meta)
        except activity.ActivityContractError:
            pass
        else:
            raise AssertionError(
                f"illegal type/mode pairing accepted: {course_meta} {progress_meta}"
            )

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
        if doctor.fails:
            raise AssertionError(
                f"{driver} retired current_lesson omission rejected: {doctor.fails}"
            )

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
    assert_message(doctor.fails, "planned 课程 canonical-none 非法")

    legal = root / "legal"
    build(legal, "")
    reset(legal)
    run_silently(doctor.discover_courses)
    if doctor.fails:
        raise AssertionError(f"legal planned course rejected: {doctor.fails}")


def test_textbook_preparation_activity_matrix(root: Path) -> None:
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
    write(
        lesson / "course.md",
        "---\ntype: course\ncourse_id: LESS1001\ncourse_type: mastery\n"
        "learning_mode: goal\n---\n",
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
            },
        ),
    }
    reset(root)
    # Created but never entered: no ledger learning_enter, so a Snapshot cannot
    # exist honestly and Doctor must not demand one. Without this the first thing
    # a real user does — generate a Course — fails runtime Doctor.
    run_silently(doctor.check_textbook_preparation, courses)
    if any("LESS1001" in message for message in doctor.fails):
        raise AssertionError(
            f"never-entered Lesson must not require a Snapshot: {doctor.fails}"
        )

    # Once learning was entered, the Snapshot becomes mandatory again.
    write(
        lesson / "activity_ledger.md",
        ledger_contract.build_ledger_with_events(
            "LESS1001",
            "### ALE-000001\n"
            "event_id: ALE-000001\nevent_kind: transition\ncourse_id: LESS1001\n"
            "activity_type: lesson\nactivity_id: lesson01\n"
            "from_state: planned\nto_state: ongoing\n"
            "occurred_at: 2026-07-26T00:00:00Z\nrecorded_at: 2026-07-26T00:00:00Z\n"
            "triggered_by: user\ntrigger: activity_created\n"
            "transaction_id: INIT-LESS1001-lesson01\n"
            "evidence_refs: [main/40_course/LESS1001/lessons/lesson01/lesson01.md]\n\n"
            "### ALE-000002\n"
            "event_id: ALE-000002\nevent_kind: learning_enter\ncourse_id: LESS1001\n"
            "activity_type: lesson\nactivity_id: lesson01\n"
            "from_state: ongoing\nto_state: ongoing\n"
            "learning_span_id: LS-LESS1001-0001\n"
            "occurred_at: 2026-07-26T01:00:00Z\nrecorded_at: 2026-07-26T01:00:00Z\n"
            "triggered_by: user\ntrigger: lesson_start\n"
            "transaction_id: ENTER-LESS1001-lesson01\n"
            "evidence_refs: [main/40_course/LESS1001/lessons/lesson01/lesson01.md]\n",
        ),
    )
    reset(root)
    run_silently(doctor.check_textbook_preparation, courses)
    if any("EXER1001" in message for message in doctor.fails):
        raise AssertionError(f"Exercise inherited working-pages validation: {doctor.fails}")
    assert_message(doctor.fails, "LESS1001")
    assert_message(doctor.fails, "缺 preparation Snapshot")

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
    if "working_pages" in route.recovery_plan():
        raise AssertionError("recovery_plan must not include retired working_pages key")
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
    assert_message(doctor.fails, "首次体验缺少方案先行与双停顿契约")
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
    # All nine figures are character diagrams now; the guide must carry no
    # rendering scaffolding at all, and a Mermaid block is itself a failure.
    assert_message(doctor.fails, "不是 ```text 字符图")
    assert_message(doctor.fails, "仍残留 Mermaid/SVG 渲染层")
    assert_message(doctor.fails, "字符图数量不足")


def test_offline_guide_version_drift_is_enforced(root: Path) -> None:
    """NEGATIVE: the guide's hand-maintained kicker/footer must track the version.

    They sit outside every `T2AG_GENERATED` anchor, so `build_guide.py --write`
    never corrects them. Skeleton shipped `0.2.2` there while its constitution
    already said `0.2.3` — the first number an external reader checks.
    """
    flows = "\n".join(
        f"<!-- FLOW:{flow_id} -->\nprose only\n<!-- /FLOW:{flow_id} -->"
        for flow_id in sorted(doctor.EXPECTED_FLOWS)
    )

    def seed(guide_version: str, flow_version: str) -> None:
        write(root / "main/t2ag.md", f"# T2AG {flow_version} 宪法\n\n- 当前运行版本：`0.2.3`\n")
        write(
            root / "main/50_playbook/t2ag_flow.md",
            f"# T2AG {flow_version} 功能流程图\n\n{flows}\n",
        )
        write(
            root / "t2ag_directory_guide.html",
            f'<span class="kicker">T2AG / Directory Guide / {guide_version}</span>\n'
            + "".join(
                f"<!-- T2AG_GENERATED:{anchor} --><!-- /T2AG_GENERATED:{anchor} -->\n"
                for anchor in (
                    "preface", "directory_map", "flow_first_run",
                    "flow_panorama", "flow_catalog",
                )
            )
            + f'<span>T2AG {guide_version} · footer</span>\n',
        )

    reset(root)
    seed("0.2.3", "0.2.3")
    run_silently(doctor.check_flow_and_guide)
    drifted = [f for f in doctor.fails if "版本漂移" in f or "缺当前版本标识" in f]
    if drifted:
        raise AssertionError(f"aligned versions must not report drift: {drifted}")

    reset(root)
    seed("0.2.2", "0.2.3")
    run_silently(doctor.check_flow_and_guide)
    assert_message(doctor.fails, "离线指南版本漂移")
    assert_message(doctor.fails, "缺当前版本标识")

    reset(root)
    seed("0.2.3", "0.2.0")
    run_silently(doctor.check_flow_and_guide)
    assert_message(doctor.fails, "流程源标题版本漂移")


def test_lite_redaction_preserves_privacy_detector_literal(root: Path) -> None:
    """Detector data stays executable while real host paths remain redacted.

    The full-regenerate Lite path once replaced the Doctor's own bare
    maintainer-name pattern with ``<host_user>``.  That both weakened privacy
    scanning and made the test-management byte contract fail after every clean
    regeneration.  The exception is intentionally narrower than a file
    exemption: only the bare rule is preserved; path-shaped identity still
    redacts.
    """
    old_user = sync_lite.HOST_USER
    old_rules = sync_lite.HOST_REDACTIONS
    try:
        sync_lite.HOST_USER = "FixtureUser"
        sync_lite.HOST_REDACTIONS = sync_lite._build_host_redactions("FixtureUser")
        payload = (
            b"regex=|FixtureUser|\n"
            b'entry=(r"FixtureUser", "username")\n'
            b"stray=FixtureUser\n"
            b"path=C:\\Users\\FixtureUser\\T2AC\n"
        )
        detector = root / "main/70_tools/t2ag_doctor.py"
        ordinary = root / "main/50_playbook/notes.md"
        detector_bytes, detector_hits = sync_lite.redact_projected_text(detector, payload)
        ordinary_bytes, ordinary_hits = sync_lite.redact_projected_text(ordinary, payload)
    finally:
        sync_lite.HOST_USER = old_user
        sync_lite.HOST_REDACTIONS = old_rules

    if detector_bytes.count(b"FixtureUser") != 2:
        raise AssertionError("Lite must preserve exactly the two executable detector literals")
    if b"stray=FixtureUser" in detector_bytes or b"C:\\Users\\FixtureUser" in detector_bytes:
        raise AssertionError("privacy-detector prose and paths must still be redacted")
    if detector_hits != 2:
        raise AssertionError(f"expected path + stray redactions, got {detector_hits}")
    masked = sync_lite.mask_privacy_detector_literals(detector_bytes, b"FixtureUser")
    if b"FixtureUser" in masked:
        raise AssertionError("the final residual scan must reject non-detector occurrences")
    if b"FixtureUser" in ordinary_bytes or ordinary_hits != 4:
        raise AssertionError("ordinary projected text must retain full host redaction")


def test_skeleton_package_surface_is_enforced(root: Path) -> None:
    """NEGATIVE: what strangers receive is the zip, not the checked-out tree.

    The 2026-08-09 package shipped `.git/`, so `git show e3f7632^:…changelog` still
    returned the pre-redaction maintainer paths. The tree scan reported clean the
    whole time — a guard narrower than its carrier.
    """
    def build(name: str, entries: dict[str, str]) -> Path:
        archive = root / name
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w") as bundle:
            shaped = {"README.md": "# skeleton\n", **entries}
            for relative, text in shaped.items():
                bundle.writestr(f"t2ag-skeleton/{relative}", text)
        return archive

    clean = build(
        "t2ag-skeleton-0.9.9-abcdef1.zip",
        {"README.md": "# skeleton\n", "main/t2ag.md": "# 宪法\n"},
    )
    findings = doctor.skeleton_package_findings(clean)
    if findings:
        raise AssertionError(f"clean package must produce no finding: {findings}")

    with_history = build(
        "t2ag-skeleton-history.zip",
        {"README.md": "# skeleton\n", ".git/config": "user = anyone\n"},
    )
    findings = doctor.skeleton_package_findings(with_history)
    if not any(".git" in item for item in findings):
        raise AssertionError(f"shipping .git must be reported: {findings}")
    if len(findings) != 1:
        raise AssertionError(f"the .git finding must subsume the file scan: {findings}")

    leaky = build(
        "t2ag-skeleton-leak.zip",
        {"main/50_playbook/x.md": "见 C:\\Users\\someone\\T2AC\n"},
    )
    findings = doctor.skeleton_package_findings(leaky)
    if not any("维护者个人信息" in item for item in findings):
        raise AssertionError(f"packaged local path must be reported: {findings}")

    exempt = build(
        "t2ag-skeleton-exempt.zip",
        {"main/70_tools/t2ag_doctor.py": r"(r'[A-Za-z]:[\\/]Users[\\/]', 'x')" + "\n"},
    )
    if doctor.skeleton_package_findings(exempt):
        raise AssertionError("the detector's own literals must stay exempt inside packages")

    nested = root / "t2ag-skeleton-bundle.zip"
    with zipfile.ZipFile(nested, "w") as bundle:
        bundle.writestr("t2ag-skeleton-bundle/zh/README.md", "# zh\n")
        bundle.writestr("t2ag-skeleton-bundle/zh/main/t2ag.md", "# t2ag\n")
        bundle.writestr("t2ag-skeleton-bundle/en/README.md", "# en\n")
        bundle.writestr("t2ag-skeleton-bundle/en/main/t2ag.md", "# t2ag\n")
    findings = doctor.skeleton_package_findings(nested)
    if len(findings) != 1 or "形制不受支持" not in findings[0]:
        raise AssertionError(f"nested bilingual bundle must fail fast on shape: {findings}")

    broken = root / "t2ag-skeleton-broken.zip"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_bytes(b"not a zip")
    if not any("不可读" in item for item in doctor.skeleton_package_findings(broken)):
        raise AssertionError("an unreadable package must fail closed, not pass silently")


def test_release_package_surface_severity_split(root: Path) -> None:
    """The same fact must be WARN at runtime and FAIL at release.

    Shipping `.git` was WARN-only once, and the operator read it as noise while
    reporting "commit 对象在" as healthy — the package went out with full history.
    Runtime must stay non-blocking (a stale archive is not a teaching fault);
    release must be unskippable, because that is the moment a package is built.
    """
    repo = root / "t2ag-skeleton"
    reset(repo, "skeleton")
    write(repo / "main/t2ag.md", FIXTURE_CONSTITUTION)
    contaminated = root / "t2ag-skeleton-0.9.9-deadbee.zip"
    with zipfile.ZipFile(contaminated, "w") as bundle:
        bundle.writestr("t2ag-skeleton/README.md", "# skeleton\n")
        bundle.writestr("t2ag-skeleton/.git/config", "user = anyone\n")

    if doctor.built_skeleton_packages(repo) != [contaminated]:
        raise AssertionError(
            f"package discovery must be flavor-independent: {doctor.built_skeleton_packages(repo)}"
        )

    run_silently(doctor.check_release_package_surface)
    assert_message(doctor.fails, "不得对外分发")
    if doctor.warns:
        raise AssertionError(f"release must not downgrade the finding: {doctor.warns}")

    # Moving the package into the canonical artifact tree must not empty discovery.
    artifact = root / "artifacts/releases/t2ag/0.9.9/t2ag-skeleton-0.9.9-deadbee.zip"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    contaminated.rename(artifact)
    if doctor.built_skeleton_packages(repo) != [artifact]:
        raise AssertionError(
            f"artifact-tree package discovery failed: {doctor.built_skeleton_packages(repo)}"
        )
    run_silently(doctor.check_release_package_surface)
    assert_message(doctor.fails, "不得对外分发")

    # A quarantined `.bak-*` copy is evidence of what shipped before, not a new finding.
    reset(repo, "skeleton")
    artifact.rename(root / "t2ag-skeleton.zip.bak-20260809")
    run_silently(doctor.check_release_package_surface)
    if doctor.fails:
        raise AssertionError(f"a quarantined .bak copy must not be re-flagged: {doctor.fails}")


def test_unreadable_package_fails_closed_without_aborting_surface(root: Path) -> None:
    """An unreadable archive must FAIL without aborting the remaining surface."""
    race = root / "race"
    archive = race / "t2ag-skeleton-0.9.9-deadbee.zip"
    payload = b"release bytes"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(payload)
    write(
        race / "release.manifest.json",
        json.dumps(
            {
                "package": archive.name,
                "zip_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        + "\n",
    )
    original_read_bytes = Path.read_bytes

    def locked_read_bytes(path: Path) -> bytes:
        if path == archive:
            raise PermissionError("locked by fixture")
        return original_read_bytes(path)

    # The package may become locked after the scanner succeeds. Manifest
    # reconciliation must convert that race into a finding, never an exception.
    with mock.patch.object(Path, "read_bytes", locked_read_bytes):
        finding = doctor.manifest_package_drift(archive)
    if not finding.startswith(doctor.PACKAGE_UNREADABLE_PREFIX):
        raise AssertionError(f"the manifest race must fail closed: {finding!r}")

    # If the scanner already found the lock, do not reopen the same archive;
    # continue checking later packages and retain an accurate clean count.
    known_locked = root / "t2ag-skeleton-0.9.9-locked.zip"
    clean = root / "t2ag-skeleton-0.9.9-clean.zip"
    reports: list[tuple[str, str]] = []
    manifest_calls: list[Path] = []
    original_packages = doctor.built_skeleton_packages
    original_findings = doctor.skeleton_package_findings
    original_drift = doctor.manifest_package_drift
    original_report = doctor.report
    try:
        doctor.built_skeleton_packages = lambda _root: [known_locked, clean]
        doctor.skeleton_package_findings = lambda item: (
            [f"{doctor.PACKAGE_UNREADABLE_PREFIX}：{item.name} locked by fixture"]
            if item == known_locked
            else []
        )

        def record_manifest(item: Path) -> str:
            manifest_calls.append(item)
            return ""

        doctor.manifest_package_drift = record_manifest
        doctor.report = lambda level, message: reports.append((level, message))
        doctor.check_release_package_surface()
    finally:
        doctor.built_skeleton_packages = original_packages
        doctor.skeleton_package_findings = original_findings
        doctor.manifest_package_drift = original_drift
        doctor.report = original_report

    if manifest_calls != [clean]:
        raise AssertionError(f"known unreadable archives must not be reopened: {manifest_calls}")
    if not any(level == "FAIL" and known_locked.name in message for level, message in reports):
        raise AssertionError(f"the unreadable archive must remain a FAIL: {reports}")
    if not any(level == "INFO" and "1/2" in message for level, message in reports):
        raise AssertionError(f"later packages must still be checked: {reports}")


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
        course / "course.md",
        "---\ntype: course\ncourse_id: TEST1001\ncourse_type: mastery\n"
        "learning_mode: textbook\n---\n",
    )
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
        # Post-S3 defense: working_pages 路径用于验证 registry 对不存在文件的 FAIL 检查
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
    branch = doctor.rule_position(content, "ACT-ROUTE-001")
    lesson = doctor.rule_position(content, "ACT-ROUTE-002")
    exercise = doctor.rule_position(content, "ACT-ROUTE-003")
    working = content.find("步骤 5：教材原文窗口（Snapshot-only）")
    if not (0 <= branch < lesson < exercise < working):
        raise AssertionError("lesson_recover does not branch before Lesson/preparation consumers")
    missing = doctor.missing_requirements(content, (
        "ACT-ROUTE-004",
        "ACT-ROUTE-008",
        "ACT-ROUTE-005",
        "t2ag_activity.py --course <COURSE_ID> --intent recover",
        "ACT-ROUTE-009",
        "ACT-ROUTE-010",
        "exact RT3",
        "current_snapshot.json",
    ))
    if missing:
        raise AssertionError(f"lesson_recover missing Exercise-first guards: {missing}")
    forbidden_recovery = (
        "close_type: micro",
        "写入当前 lesson 问答记录",
        "`lessonXX.md` 的「当前教学进度」",
        "步骤 1.5 核对 question_bank",
        "保留 4 页",
        "6 页，达到上限",
        "4 页基准",
    )
    leaked = [token for token in forbidden_recovery if token in content]
    if leaked:
        raise AssertionError(f"lesson_recover retains unconditional Lesson/deferred consumers: {leaked}")
    missing_close = doctor.missing_requirements(close, (
        "t2ag_activity.py --course <COURSE_ID> --intent close",
        "ACT-ROUTE-006",
        "ACT-ROUTE-007",
        "ACT-ROUTE-011",
    ))
    if missing_close:
        raise AssertionError(f"session_close missing atomic activity routing: {missing_close}")
    # These anchors are carrier-bound on purpose, but the carrier changed once
    # already: c543891 rewrote the panorama from mermaid to a character digraph,
    # and this assertion kept looking for the mermaid literals
    # 'G{"current_activity"}' / "共同强制事务：…". The branch and the transaction
    # line were both still there — only the bytes had moved. The suite stayed red
    # from 2026-08-09 to 2026-08-21, and a suite that is always red stops being
    # read: the SOURCE_LANGUAGE break in new-course sat next to it unnoticed.
    # So: match the smallest span that carries the meaning, not the drawing
    # characters around it. If the panorama is redrawn again, update these two
    # anchors in the same commit.
    # Match per line, not on padded literals: the digraph pads arm labels to
    # align the arrows, so "lesson" gets three spaces and "exercise" one. Byte
    # counting on cosmetic whitespace is exactly how this assertion rotted.
    branches_before_consumers = "current_activity" in flow and all(
        any(arm in line and "─→ L1" in line for line in flow.splitlines())
        for arm in ("lesson", "exercise")
    )
    forces_shared_transaction = doctor.has_rule(flow, "ACT-ROUTE-012")
    if not branches_before_consumers or not forces_shared_transaction:
        raise AssertionError(
            "flow view does not branch before activity consumers "
            f"(branch={branches_before_consumers}, transaction={forces_shared_transaction})"
        )

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


SYNTHETIC_INIT_ANSWERS = {
    "nickname": "synthetic student",
    "learning_level": "university",
    "reference_curriculum": "no",
    "learning_interests": "验证公开生成路径的 Exercise-first 往返",
    "self_introduction": "合成测试实例",
    "updated": "2026-07-26",
}


def generate_synthetic_exercise_first(fixture: Path, cli) -> str:
    """Build the roundtrip instance through the PUBLIC generation path only.

    The previous helper wrote profile, Course, verified excerpt, ledger and Group
    from hardcoded strings. That proved the runtime kernel could process a
    complete instance and nothing else: a missing release template or a drifted
    schema left the test green, because the test *was* the schema. Everything
    below goes through `t2ag_init.py`, so the same three failures a real user
    would hit — absent template, unfilled placeholder, contract-invalid ledger —
    now fail here first.

    Inputs stay synthetic (a one-line source document, a trivial problem); only
    the *path* is real. The tool still refuses to invent any of them.
    """
    course_id = "TEST1001"
    scratch = fixture.parent
    answers_path = scratch / "synthetic_answers.json"
    answers_path.write_text(
        json.dumps(SYNTHETIC_INIT_ANSWERS, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    document = scratch / "synthetic_source_document.txt"
    document.write_text(
        "synthetic Exercise-first source document\n", encoding="utf-8", newline="\n"
    )

    profile = fixture / "main/10_student/profile/profile.md"
    profile_text = profile.read_text(encoding="utf-8-sig")
    if re.search(r"^initialization_status:\s*initialized\s*$", profile_text, re.MULTILINE):
        pass  # already a personal instance; init would (correctly) refuse
    elif re.search(r"^initialization_status:\s*uninitialized\s*$", profile_text, re.MULTILINE):
        cli("t2ag_init.py", "--root", str(fixture), "init", "--answers", str(answers_path))
    else:
        raise AssertionError("profile has no recognized initialization_status")

    cli(
        "t2ag_init.py", "--root", str(fixture), "new-course",
        "--course-id", course_id,
        "--name", "Synthetic Course",
        # `--course-type` became required with `--entry` and `--verification-status`
        # (PG3 #1): a default may not stand in for a confirmation. `mastery` is not
        # a choice here — this fixture passes `--learning-mode textbook`, which the
        # tool rejects on any non-mastery course type.
        "--course-type", "mastery",
        "--learning-mode", "textbook",
        "--lifecycle", "ongoing",
        "--entry", "exercise",
        "--teacher", "T001",
        "--source-scope", "synthetic",
        # Matches the fixture's own problem text, which is zh-CN. The value is not
        # incidental: `--source-language` is required with no default on purpose
        # (see t2ag_init), so the fixture has to state it like any real course.
        "--source-language", "zh-CN",
        "--position", "synthetic start",
        "--node-title", "identity",
        "--source-document", str(document),
        "--source-locator", "synthetic problem 1",
        "--source-page", "1",
        "--problem-text", "证明 1 = 1。",
        "--verification-status", "synthetic_verified",
        "--date", "2026-07-26",
    )

    # The foreground group must point at the generated course. Clearing the
    # release's own groups is fixture setup, not generation: only new-group may
    # create one, so a broken group template still fails the test.
    group_root = fixture / "main/30_group"
    for existing in sorted(group_root.glob("G*")):
        if not existing.is_dir():
            continue
        if fixture.resolve() not in existing.resolve().parents:
            raise AssertionError(f"refusing to remove a group outside the fixture: {existing}")
        shutil.rmtree(existing)
    # Birth and activation are separate public-path steps (user ruling
    # 2026-08-22): new-group only births planned; active requires the ritual.
    # The keystone edit below stands in for the ritual's human judgment — the
    # one step that is *supposed* to be an edit, not a command. activate-group
    # then notarizes it (counts rows, writes keystone_total_frozen, flips
    # status), so both the refusal surface (template rows would be rejected)
    # and the anchor arithmetic run through the same code a real user hits.
    cli(
        "t2ag_init.py", "--root", str(fixture), "new-group",
        "--group-id", "G01",
        "--members", course_id,
        "--container-mode", "progress",
        "--cycle", "synthetic",
        "--date", "2026-07-26",
    )
    plan_path = fixture / "main/30_group/G01/plan.md"
    plan_text = plan_path.read_text(encoding="utf-8-sig")
    plan_text = plan_text.replace(
        "- K01 碑描述（属哪门课、达成判据指向该课 progress.md 哪一行）\n- K02 碑描述\n",
        f"- K01 {course_id} exercise01 结课（判据：{course_id}/progress.md 当前完成节点行）\n",
    )
    if re.search(r"^-\s+K\d+\s+碑描述", plan_text, re.MULTILINE):
        raise AssertionError("synthetic keystone substitution missed the template rows")
    plan_path.write_text(plan_text, encoding="utf-8", newline="\n")
    cli(
        "t2ag_init.py", "--root", str(fixture), "activate-group",
        "--group-id", "G01",
        "--date", "2026-07-26",
    )
    # Main's artifact_registry keeps 0.2.0 tombstones whose successors still
    # pointed at G02 (and other pre-wipe groups). After the rmtree those paths
    # are gone; doctor.check_registry would FAIL for reasons the synthetic
    # course never caused. Prune missing successors (and empty tombstones) so
    # the fixture's registry matches the fixture's group surface — same rule
    # a human would apply after deleting a group by hand.
    reconcile_registry_after_group_wipe(fixture)
    return course_id


def test_line_ending_drift_names_the_variant(root: Path) -> None:
    """C3/L3 正向：只差行尾的字节必须被指名，而不是报一句 hash mismatch。

    HOST_BYTE_DRIFT 计划 §L3：0.2.2 campaign 的真实代价几乎全在误判上——
    重跑了一整轮 exact-plan shadow 才发现只是 LF→CRLF。本断言锁的是
    「诊断说得出是哪个变体」，不是「漂移不发生」（后者归 .gitattributes）。
    """
    spec_close = importlib.util.spec_from_file_location(
        "activity_close_drift", SCRIPT.with_name("activity_close.py")
    )
    close = importlib.util.module_from_spec(spec_close)
    assert spec_close and spec_close.loader
    spec_close.loader.exec_module(close)

    lf_bytes = b"plan: frozen\nsha: bound\n"
    crlf_bytes = lf_bytes.replace(b"\n", b"\r\n")
    lf_sha = hashlib.sha256(lf_bytes).hexdigest()
    crlf_sha = hashlib.sha256(crlf_bytes).hexdigest()

    # A host rewrote LF -> CRLF; the expectation still holds the LF hash.
    message = close.line_ending_drift(crlf_bytes, lf_sha)
    if "LINE ENDING DRIFT" not in message or "normalised to LF" not in message:
        raise AssertionError(f"CRLF drift must be named as LF-normalising: {message!r}")
    if "gitattributes" not in message or "do NOT regenerate" not in message:
        raise AssertionError(f"diagnosis must carry the remedy, not just a label: {message!r}")

    # The mirror direction must work too, or half the hosts get a bare mismatch.
    message = close.line_ending_drift(lf_bytes, crlf_sha)
    if "normalised to CRLF" not in message:
        raise AssertionError(f"LF drift must be named as CRLF-normalising: {message!r}")

    # The str wrapper must agree with the bytes function.
    if close.text_line_ending_drift(crlf_bytes.decode(), lf_sha) != close.line_ending_drift(
        crlf_bytes, lf_sha
    ):
        raise AssertionError("text_line_ending_drift diverged from line_ending_drift")


def test_line_ending_drift_never_excuses_content_change(root: Path) -> None:
    """C3/L3 反向：真内容变更不得被解释成格式假象。

    This is the load-bearing half. A diagnosis that fires on real edits would
    teach the operator to dismiss genuine SHA mismatches as "just line endings"
    — strictly worse than the bare mismatch it replaced.
    """
    spec_close = importlib.util.spec_from_file_location(
        "activity_close_drift2", SCRIPT.with_name("activity_close.py")
    )
    close = importlib.util.module_from_spec(spec_close)
    assert spec_close and spec_close.loader
    spec_close.loader.exec_module(close)

    original = b"plan: frozen\nsha: bound\n"
    edited = b"plan: frozen\nsha: tampered\n"
    original_sha = hashlib.sha256(original).hexdigest()

    if close.line_ending_drift(edited, original_sha) != "":
        raise AssertionError("a real content change must not be named line-ending drift")
    # Content change *and* a line-ending rewrite at once is still a content change.
    if close.line_ending_drift(edited.replace(b"\n", b"\r\n"), original_sha) != "":
        raise AssertionError("content change masked by CRLF must still not be excused")
    # Degenerate inputs stay silent rather than inventing a diagnosis.
    for raw, sha in ((b"", original_sha), (original, ""), (None, original_sha)):
        if close.line_ending_drift(raw, sha) != "":
            raise AssertionError(f"empty input must yield no diagnosis: {raw!r}/{sha!r}")
    # Byte-identical input is not drift either.
    if close.line_ending_drift(original, original_sha) != "":
        raise AssertionError("matching bytes must yield no diagnosis")


def test_package_root_prefix_read_from_archive_not_filename(root: Path) -> None:
    """C9：包内相对路径必须由包自身的根目录求出，不由文件名推。

    2026-08-20 实测的假阳性（`t2ag_doctor.py` 自身的隐私模式字面量自匹配）只是
    症状；病灶是 prefix 曾按 `archive.stem.split('-0.')[0]` 推导，而
    `t2ag-skeleton-en-*.zip` 的条目根是 `t2ag-skeleton/`。前缀对不上时**每一条**
    路径键策略都静默失效，`SKELETON_PRIVACY_EXEMPT` 只是第一个被发现的。
    """
    # The en-package shape: archive named -en, entries rooted at the zh name.
    names = ["t2ag-skeleton/.gitattributes", "t2ag-skeleton/main/70_tools/t2ag_doctor.py"]
    prefix = doctor.package_root_prefix(names)
    if prefix != "t2ag-skeleton/":
        raise AssertionError(f"root must come from the entries: {prefix!r}")
    relative = names[1][len(prefix):]
    if relative not in doctor.SKELETON_PRIVACY_EXEMPT:
        raise AssertionError(
            f"exemption is keyed on repo-relative paths and must match: {relative!r}"
        )
    # No single root, or a flat archive: strip nothing rather than mis-strip.
    if doctor.package_root_prefix(["x/a.md", "y/b.md"]) != "":
        raise AssertionError("archives with several roots must not be stripped")
    if doctor.package_root_prefix(["a.md", "b.md"]) != "":
        raise AssertionError("flat archives must not be stripped")


def test_manifest_package_drift_pairs_by_claim_not_filename(root: Path) -> None:
    """乙：包与其 manifest 的 sha256 交叉核对（2026-08-22 用户裁决，范围刻意只此一字段）。

    Four surfaces: (1) a stale manifest beside a repacked zip is caught — the
    predicted failure once the unified repo and the EN regen change the packing
    pipeline; (2) pairing follows the manifest's declared `package`, never the
    filename, or the check would repeat `package_root_prefix`'s own defect;
    (3) no manifest is silent, because release manifests are gitignored and a
    clean clone has none; (4) an unreadable manifest is NOT silent — quiet loss
    of coverage is the P-0071 family.
    """
    def pack(path: Path, payload: str) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("t2ag-skeleton/main/t2ag.md", payload)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def manifest(path: Path, package: str, sha: str) -> None:
        write(path, json.dumps({"package": package, "zip_sha256": sha}, indent=2) + "\n")

    # (3) no manifest at all -> silent.
    bare = root / "bare"
    archive = bare / "t2ag-skeleton-0.9.9-aaaaaaa.zip"
    pack(archive, "one")
    if doctor.manifest_package_drift(archive) != "":
        raise AssertionError("a package with no manifest must not be flagged")

    # (1) manifest describes the pre-repack bytes -> caught.
    stale = root / "stale"
    archive = stale / "t2ag-skeleton-0.9.9-bbbbbbb.zip"
    original = pack(archive, "before repack")
    manifest(stale / "t2ag-skeleton-0.9.9-bbbbbbb.manifest.json", archive.name, original)
    if doctor.manifest_package_drift(archive) != "":
        raise AssertionError("a matching manifest must stay silent")
    pack(archive, "after repack")  # repacked; manifest not regenerated
    message = doctor.manifest_package_drift(archive)
    if "不符" not in message or "manifest 未同步" not in message:
        raise AssertionError(f"stale manifest must be reported: {message!r}")

    # (2) pairing is by the declared `package`, not by filename similarity.
    paired = root / "paired"
    archive = paired / "t2ag-skeleton-en-0.9.9-ccccccc.zip"
    sha = pack(archive, "en package")
    # A same-prefixed manifest that describes a *different* package must be ignored…
    manifest(paired / "t2ag-skeleton-en-0.9.9-ddddddd.manifest.json",
             "t2ag-skeleton-en-0.9.9-ddddddd.zip", "0" * 64)
    if doctor.manifest_package_drift(archive) != "":
        raise AssertionError("a manifest claiming another package must not be paired")
    # …and a manifest whose *filename* shares nothing must still pair by claim.
    manifest(paired / "unrelated-name.manifest.json", archive.name, "1" * 64)
    if "不符" not in doctor.manifest_package_drift(archive):
        raise AssertionError("pairing must follow the declared package field")

    # (4) an unreadable manifest must speak rather than silently drop coverage.
    broken = root / "broken"
    archive = broken / "t2ag-skeleton-0.9.9-eeeeeee.zip"
    pack(archive, "content")
    write(broken / "t2ag-skeleton-0.9.9-eeeeeee.manifest.json", "{not json")
    if "不可解析" not in doctor.manifest_package_drift(archive):
        raise AssertionError("a malformed manifest must be reported, not skipped")


def test_release_candidate_binding_freezes_both_ends(root: Path) -> None:
    """CR-3=B（2026-08-23 用户裁决，重开 RP-2=c）：冻结绑定的四个面。纯函数直调。

    (1) 台账无 `release_candidate` 行 → 静默（尚无绑定对象，不得预支断言）；
    (2) 冻结 commit == 现役包 commit → 静默（收口后的普通提交不点红——断言两端
        都冻结在收口那一刻，这正是当年拒绝「包==HEAD」的理由）；
    (3) 现役包 ≠ 冻结 commit → CAND-BIND-001 WARN（十二小时两次复发的那个病）；
    (4) 同版别两份未退役 manifest → CAND-BIND-003 WARN（「现役是谁」含混）；
        带 `superseded_by` 的 manifest 不参与现役身份。
    (5) 单边冻结（只写 zh 漏 en）→ CAND-BIND-005 FAIL——「两端皆冻」不许静默缺端；
    (6) 含 release_candidate 但解析不出绑定的行 → CAND-BIND-004 FAIL——
        断言不得建在乐观解析上，写坏的冻结不是冻结；
    (7) 同版别重复冻结 → CAND-BIND-006 FAIL（互相矛盾无从断言）。
    (8) 头部说明文字可提字段名但不是数据行，不得自触发 CAND-BIND-004。
    """
    frozen_line = "- 0.2.3 `release_candidate`：zh `c602f6f`／en `a539db7`\n"

    def manifest(package: str, commit: str, **extra: object) -> dict[str, object]:
        claim: dict[str, object] = {
            "package": package, "source_commit_short": commit,
        }
        claim.update(extra)
        return claim

    zh = manifest("t2ag-skeleton-0.2.3-c602f6f.zip", "c602f6f")
    en = manifest("t2ag-skeleton-en-0.2.3-a539db7.zip", "a539db7")

    # Collector regression (P-0090): exercise the production collector against
    # a real directory tree. Overlapping roots discover invited files twice, but
    # resolved-path de-duplication admits each once; tmp and retired copies stay
    # outside the serving set, and superseded invited history is collected then
    # excluded by the unchanged pure-function rule.
    workspace = root / "candidate-binding-workspace"
    release_root = workspace / "artifacts/releases/t2ag"
    invited = release_root / "0.2.3/invited"
    retired = release_root / "0.2.3/retired"
    tmp_copy = workspace / "tmp/en-pack-out"
    stale = manifest(
        "t2ag-skeleton-0.2.3-f27a431.zip", "f27a431",
        superseded_by="t2ag-skeleton-0.2.3-c602f6f.zip",
    )
    for path, claim in (
        (invited / "t2ag-skeleton-0.2.3-c602f6f.manifest.json", zh),
        (invited / "t2ag-skeleton-en-0.2.3-a539db7.manifest.json", en),
        (invited / "t2ag-skeleton-0.2.3-f27a431.manifest.json", stale),
        (retired / "t2ag-skeleton-en-0.2.3-deadbee.manifest.json",
         manifest("t2ag-skeleton-en-0.2.3-deadbee.zip", "deadbee")),
        (tmp_copy / "t2ag-skeleton-en-0.2.3-badf00d.manifest.json",
         manifest("t2ag-skeleton-en-0.2.3-badf00d.zip", "badf00d")),
    ):
        write(path, json.dumps(claim, ensure_ascii=False))
    collected = doctor.collect_release_candidate_manifests(
        workspace, search_roots=[workspace, release_root]
    )
    commits = [str(claim.get("source_commit_short", "")) for claim in collected]
    if sorted(commits) != ["a539db7", "c602f6f", "f27a431"]:
        raise AssertionError(
            "collector must de-duplicate overlapping roots and admit only exact "
            f"invited manifests, got {commits}"
        )
    if doctor.release_candidate_binding_findings(frozen_line, collected):
        raise AssertionError(
            "one serving zh/en pair plus superseded invited history must be clean"
        )
    broken = invited / "t2ag-skeleton-0.2.3-broken.manifest.json"
    write(broken, "{not json")
    with mock.patch.object(doctor, "report") as report_mock:
        doctor.collect_release_candidate_manifests(workspace)
    if not report_mock.called or report_mock.call_args.args[0] != "WARN":
        raise AssertionError("an unreadable invited manifest must remain fail-closed WARN")

    # (1) nothing frozen -> silent even with manifests present.
    if doctor.release_candidate_binding_findings("- 0.2.2 …\n", [zh, en]):
        raise AssertionError("no release_candidate line must mean no findings")

    # (2) frozen and matching -> silent.
    if doctor.release_candidate_binding_findings(frozen_line, [zh, en]):
        raise AssertionError("matching frozen commit must stay silent")

    # (3) serving package drifted from the frozen commit -> WARN.
    drifted = manifest("t2ag-skeleton-0.2.3-16f1642.zip", "16f1642")
    codes = [c for c, _, _ in doctor.release_candidate_binding_findings(
        frozen_line, [drifted, en])]
    if codes != ["CAND-BIND-001"]:
        raise AssertionError(f"drift must raise CAND-BIND-001, got {codes}")

    # (4) two unretired manifests for one edition -> ambiguity WARN; a
    #     superseded manifest drops out of the serving identity.
    stale = manifest("t2ag-skeleton-0.2.3-f27a431.zip", "f27a431")
    codes = [c for c, _, _ in doctor.release_candidate_binding_findings(
        frozen_line, [zh, stale, en])]
    if codes != ["CAND-BIND-003"]:
        raise AssertionError(f"ambiguous serving identity must warn, got {codes}")
    stale["superseded_by"] = "t2ag-skeleton-0.2.3-c602f6f.zip"
    if doctor.release_candidate_binding_findings(frozen_line, [zh, stale, en]):
        raise AssertionError("a superseded manifest must not contest serving identity")

    # (5) one-sided freeze: zh only, en missing -> FAIL, never silent.
    one_sided = "- 0.2.3 `release_candidate`：zh `c602f6f`\n"
    rows = doctor.release_candidate_binding_findings(one_sided, [zh, en])
    codes = [c for c, _, _ in rows]
    severities = [s for _, s, _ in rows]
    if "CAND-BIND-005" not in codes or "FAIL" not in severities:
        raise AssertionError(f"a one-sided freeze must FAIL with CAND-BIND-005, got {rows}")

    # (6) a line that mentions release_candidate but cannot be parsed -> FAIL.
    for broken_line in (
        "- 0.2.3 release_candidate：zh c602f6f／en a539db7\n",   # no backticks anywhere
        "- 0.2.3 `release_candidate`：见下一行\n",                # parses, zero pairs
    ):
        rows = doctor.release_candidate_binding_findings(broken_line, [zh, en])
        codes = [c for c, _, _ in rows]
        if codes != ["CAND-BIND-004"]:
            raise AssertionError(
                f"a malformed freeze line must FAIL with CAND-BIND-004, got {rows} "
                f"for {broken_line!r}"
            )

    # (7) the same version frozen twice -> contradictory, FAIL per doubled edition.
    doubled = frozen_line + "- 0.2.3 `release_candidate`：zh `16f1642`／en `71ddbc2`\n"
    codes = [c for c, _, _ in doctor.release_candidate_binding_findings(doubled, [zh, en])]
    if codes != ["CAND-BIND-006", "CAND-BIND-006"]:
        raise AssertionError(f"a duplicated freeze must FAIL per edition, got {codes}")

    # (8) The real ledger header documents ownership using the field name.
    prose = "> `release_candidate` 冻结绑定行在重打之后只写 Main 台账。\n"
    if doctor.release_candidate_binding_findings(prose, [zh, en]):
        raise AssertionError("explanatory ledger prose must not impersonate a data row")


def test_group_activation_notary(root: Path) -> None:
    """activate-group 公证面（2026-08-22 用户裁决）：状态只能跟在凭据后面。

    Five surfaces, all through the public entry: (1) template keystone rows are
    not evidence — refuse; (2) a hand-written anchor on a planned group is
    refused (锚不得手写，只有公证人可写); (3) real rows notarize — anchor equals
    the row count doctor will reconcile against, status flips; (4) an already
    active group cannot be activated again; (5) schedule groups activate
    without an anchor (§4.3 does not apply to them).
    """
    spec_init = importlib.util.spec_from_file_location(
        "t2ag_init_under_test", SCRIPT.with_name("t2ag_init.py")
    )
    init_mod = importlib.util.module_from_spec(spec_init)
    assert spec_init and spec_init.loader
    spec_init.loader.exec_module(init_mod)

    def instance(tag: str) -> Path:
        base = root / tag
        write(base / "main/t2ag.md", "# t2ag\n")
        write(
            base / "main/40_course/C01/progress.md",
            "---\nlifecycle_status: ongoing\n---\n",
        )
        return base

    def plan(
        base: Path, mode: str, keystones: str, extra: str = "", *, calendar: str | None = None
    ) -> Path:
        path = base / "main/30_group/G01/plan.md"
        write(
            path,
            "---\n"
            "type: group\ngroup_id: G01\nstatus: planned\n"
            "course_members: [C01]\nengagement_members: []\n"
            "current_course: none\n"
            f"container_mode: {mode}\n{extra}"
            "updated: 2026-08-01\n---\n\n"
            "## 4. 主干碑序列\n\n" + keystones + "\n## 5. 碑变更台账\n\n| |\n",
        )
        # A calendar.md carrying the stop-loss anchor is what the real templates
        # ship (`keystone_dwell_budget_cycles: TBD`), and since PG3 the preflight
        # blocks activation without it — same criterion Doctor already enforced on
        # active groups, just moved to the moment the group becomes active. These
        # fixtures had no calendar at all, which was only ever survivable because
        # the criterion fired a whole Doctor run too late.
        write(
            base / "main/30_group/G01/calendar.md",
            "---\ntype: group_calendar\ngroup_id: G01\nstatus: planned\n"
            f"container_mode: {mode}\n"
            + (calendar if calendar is not None else "keystone_dwell_budget_cycles: TBD\n")
            + "updated: 2026-08-01\n---\n",
        )
        return path

    def activate(base: Path) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return init_mod.main(
                ["--root", str(base), "activate-group",
                 "--group-id", "G01", "--date", "2026-08-22"]
            )

    base = instance("tpl")
    plan(base, "progress", "- K01 碑描述（属哪门课、达成判据指向该课 progress.md 哪一行）\n- K02 碑描述\n")
    assert activate(base) == 1, "template keystone rows must be refused"

    base = instance("hand")
    plan(base, "progress", "- K01 C01 真实碑（判据：progress.md 当前节点行）\n",
         extra="keystone_total_frozen: 1\n")
    assert activate(base) == 1, "hand-written anchor must be refused"

    base = instance("ok")
    path = plan(
        base, "progress",
        "- K01 C01 节点甲（判据：progress.md 当前节点行）\n"
        "- K02 C01 结课（判据：lifecycle_status 行）\n",
    )
    assert activate(base) == 0, "real keystone rows must notarize"
    text = path.read_text(encoding="utf-8")
    assert re.search(r"^status: active$", text, re.MULTILINE), text
    assert re.search(r"^keystone_total_frozen: 2$", text, re.MULTILINE), text
    assert re.search(r"^current_course: C01$", text, re.MULTILINE), text
    assert activate(base) == 1, "re-activation of an active group must be refused"

    base = instance("sched")
    path = plan(base, "schedule", "", calendar="cycle_anchor_learning_day: TBD\n")
    assert activate(base) == 0, "schedule groups must activate without an anchor"
    text = path.read_text(encoding="utf-8")
    assert "keystone_total_frozen" not in text, text
    assert re.search(r"^status: active$", text, re.MULTILINE), text


def reconcile_registry_after_group_wipe(fixture: Path) -> None:
    """Drop registry successors that no longer exist after fixture group surgery.

    Fixture-only. Never rewrite the source release's registry.
    """
    reg_path = fixture / "main/70_tools/artifact_registry.json"
    if not reg_path.is_file():
        return
    data = json.loads(reg_path.read_text(encoding="utf-8"))
    artifacts = data.get("artifacts", [])
    kept_artifacts = []
    for item in artifacts:
        if item.get("status") == "tombstone":
            successors = [
                s for s in item.get("successors", [])
                if (fixture / s).exists()
            ]
            item = {**item, "successors": successors}
            if not successors and not item.get("alias_to"):
                # tombstone with nowhere left to point — drop for this fixture
                continue
        elif item.get("status") in {"active", "archived"}:
            canonical = item.get("canonical_path", "")
            if canonical and not (fixture / canonical).exists():
                continue
        kept_artifacts.append(item)
    data["artifacts"] = kept_artifacts
    reg_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


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
        course_id = generate_synthetic_exercise_first(fixture, cli)
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
            between = []
            for candidate in sorted((fixture / "main/40_course").glob("*/progress.md")):
                content = candidate.read_text(encoding="utf-8-sig")
                if (
                    re.search(r"^lifecycle_status:\s*ongoing\s*$", content, re.MULTILINE)
                    and re.search(r"^current_activity:\s*none\s*$", content, re.MULTILINE)
                    and re.search(r"^activity_position:\s*between_activities\s*$", content, re.MULTILINE)
                ):
                    between.append(candidate.parent.name)
            if between:
                course_id = between[0]
                cli("t2ag_state_refresh.py", "--check")
                doctor = cli("t2ag_doctor.py")
                assert_doctor_flavor(doctor, expected_runtime_flavor)
                recover = json.loads(
                    cli(
                        "t2ag_activity.py", "--course", course_id, "--intent", "recover",
                    ).stdout
                )
                expected_progress = f"main/40_course/{course_id}/progress.md"
                if (
                    recover["current_activity"] != "none"
                    or recover["current_activity_id"] != "none"
                    or recover["primary_read"] != expected_progress
                    or recover["activity_read_targets"]
                    or "working_pages" in recover
                ):
                    raise AssertionError(
                        f"between-activities recover invented an active activity: {recover}"
                    )
                return
            # Initialized Main may only have ongoing textbook Lessons (no Exercise /
            # between_activities). Do not depend on mutable instance shape: synthesize
            # an Exercise-first course inside the fixture for the disk roundtrip.
            course_id = generate_synthetic_exercise_first(fixture, cli)
        else:
            course_id = candidates[0]

    progress_path = fixture / f"main/40_course/{course_id}/progress.md"
    source_progress = source / progress_path.relative_to(fixture)
    if source_progress.is_file() and os.path.samefile(source_progress, progress_path):
        raise AssertionError("release fixture reused a hardlink to the source progress")

    progress = progress_path.read_text(encoding="utf-8-sig")
    if re.search(r"^current_lesson:", progress, re.MULTILINE):
        raise AssertionError("0.2.2 E2E fixture retained retired current_lesson")

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
        r"^current_activity_id:\s*((?:U\d{4}|exercise\d{2,}))\s*$",
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
    # working_pages was retired in 0.2.2 S3: the key must be absent, not null.
    # Asserting `is not None` raised KeyError instead of checking anything.
    if "working_pages" in recover:
        raise AssertionError(f"Exercise recover inherited retired working_pages: {recover}")
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

HANDOFF_INDEX_HEADINGS = (
    "Active Handoffs",
    doctor.marker_spellings("下一版本 Backlog")[0],
    "Workorders / Plans",
    "Evidence / Reviews",
    "Resolved / Archive Handoffs",
)
HANDOFF_METADATA_FIELDS = (
    ("handoff_id", "HO-FIXTURE-0001"),
    ("scope", "implementation"),
    ("lane", "maintenance"),
    ("artifact_role", "handoff"),
    ("applies_to", "fixture"),
    ("status", "active"),
    ("aging_state", "normal"),
    ("task_match", "fixture"),
    ("created_at", "2026-08-07"),
    ("updated_at", "2026-08-07"),
    ("version_context", "0.2.3"),
    ("supersedes", "none"),
    ("superseded_by", "none"),
    ("close_condition", "fixture closed"),
    ("canonical_sources", "main/t2ag.md"),
    ("next_action", "none"),
    ("semantic_check", "pass"),
)


def write_handoff_fixture(repo: Path, body: str) -> None:
    """Seed the minimum a handoff index + document needs to reach the body scan.

    check_handoff_contract resolves its root as ROOT.parent/docs/handoffs, so the
    caller must point doctor.ROOT at a *subdirectory* of the case root; otherwise
    sibling cases share one handoff root and the isolation is fake.
    """
    filename = "FIXTURE_HANDOFF.md"
    handoff_root = repo.parent / "docs/handoffs"
    headings = "\n\n".join(f"## {heading}" for heading in HANDOFF_INDEX_HEADINGS[1:])
    write(
        handoff_root / "README.md",
        "# handoff fixture index\n\n"
        "## Active Handoffs\n\n"
        "| handoff_id | scope | lane | artifact_role | status | applies_to | updated_at | 文件 |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| HO-FIXTURE-0001 | implementation | maintenance | handoff | active | fixture "
        f"| 2026-08-07 | `{filename}` |\n\n"
        f"{headings}\n",
    )
    write(repo / "main/t2ag.md", FIXTURE_CONSTITUTION)
    metadata = "\n".join(
        f"> **{field}**：{value}" for field, value in HANDOFF_METADATA_FIELDS
    )
    write(
        handoff_root / filename,
        f"# fixture handoff\n\n{metadata}\n\n"
        "## 最小状态摘要\n\nfixture state\n\n"
        "## 连续性摘要\n\n无需要恢复的额外主线。\n\n"
        f"{body}\n",
    )


def test_handoff_assertion_without_source_is_reported(root: Path) -> None:
    """NEGATIVE: an unsourced count/existence/hash claim must make the gate speak.

    Written before the positive case on purpose.  A checker that has only ever
    been shown passing input is indistinguishable from an empty function — the
    standing precedent is check_memory_version_pointer, which had no positive
    regression at all and nobody noticed.
    """
    repo = root / "t2ag"
    reset(repo)
    write_handoff_fixture(
        repo,
        "## 状态\n\n"
        "- 工作树有 89 个脏文件\n"
        "- 全仓 grep 该符号，零命中\n"
        "- canonical PDF sha256：730d8220\n",
    )
    run_silently(doctor.check_handoff_contract)
    if doctor.fails:
        raise AssertionError(f"fixture handoff should be structurally valid: {doctor.fails}")
    assert_message(doctor.warns, "交接断言无复算来源")
    assert_message(doctor.warns, "FIXTURE_HANDOFF.md")
    for token in ("89 个脏文件", doctor.marker_spellings("零命中")[0], "sha256"):
        assert_message(doctor.warns, token)
    located = [warn for warn in doctor.warns if "FIXTURE_HANDOFF.md:" in warn]
    if len(located) != 3:
        raise AssertionError(f"expected one located WARN per claim; actual={doctor.warns}")


def test_handoff_assertion_with_source_is_accepted(root: Path) -> None:
    """POSITIVE: the same claims stay silent once a recompute source is adjacent."""
    repo = root / "t2ag"
    reset(repo)
    write_handoff_fixture(
        repo,
        "## 状态\n\n"
        "- 工作树有 89 个脏文件 ← `git status --porcelain | wc -l`\n"
        "- 全仓 grep 该符号，零命中\n"
        "  ← `grep -rn \"符号\" main/`\n"
        "- canonical PDF sha256：730d8220\n"
        "  ← `sha256sum main/40_course/book.pdf`\n",
    )
    run_silently(doctor.check_handoff_contract)
    if doctor.fails:
        raise AssertionError(f"sourced handoff rejected: {doctor.fails}")
    offenders = [warn for warn in doctor.warns if "交接断言无复算来源" in warn]
    if offenders:
        raise AssertionError(f"sourced assertions must not warn: {offenders}")


def test_handoff_assertion_scan_skips_structure_only(root: Path) -> None:
    """Fenced code and headings are structure; quoted prose is NOT exempt (§5.6.4)."""
    fenced = doctor.unsourced_handoff_assertions(
        "```\ngit status --porcelain | wc -l  # 3 个\n```\n"
    )
    if fenced:
        raise AssertionError(f"fenced code must not be scanned: {fenced}")
    heading = doctor.unsourced_handoff_assertions("## 未提交 3 个文件\n")
    if heading:
        raise AssertionError(f"headings must not be scanned: {heading}")
    quoted = doctor.unsourced_handoff_assertions("上一轮误报「零命中」，实际索引存在\n")
    if len(quoted) != 1 or quoted[0][0] != 1:
        raise AssertionError(f"quoted prose must still be reported: {quoted}")


def test_handoff_required_context_layers_are_enforced(root: Path) -> None:
    repo = root / "t2ag"
    reset(repo)
    write_handoff_fixture(repo, "## 状态\n\nfixture\n")
    handoff = repo.parent / "docs/handoffs/FIXTURE_HANDOFF.md"
    write(
        handoff,
        handoff.read_text(encoding="utf-8").replace("## 连续性摘要", "## 讨论记录", 1),
    )
    run_silently(doctor.check_handoff_contract)
    assert_message(doctor.fails, "缺连续性摘要层")


def test_handoff_active_lane_absence_contradiction_is_enforced(root: Path) -> None:
    repo = root / "t2ag"
    reset(repo)
    write_handoff_fixture(repo, "## 状态\n\nfixture\n")
    index = repo.parent / "docs/handoffs/README.md"
    write(
        index,
        index.read_text(encoding="utf-8") + "\n当前没有 active `maintenance` Handoff。\n",
    )
    run_silently(doctor.check_handoff_contract)
    assert_message(doctor.fails, "同时登记 active 又声明不存在")


def test_handoff_index_version_drift_is_enforced(root: Path) -> None:
    repo = root / "t2ag"
    reset(repo)
    write_handoff_fixture(repo, "## 状态\n\nfixture\n")
    index = repo.parent / "docs/handoffs/README.md"
    write(index, index.read_text(encoding="utf-8") + "\n- 当前版本为 0.1.0。\n")
    run_silently(doctor.check_handoff_contract)
    assert_message(doctor.fails, "handoff 索引版本漂移")


def test_handoff_shadow_runtime_index_is_enforced(root: Path) -> None:
    repo = root / "t2ag"
    reset(repo)
    write_handoff_fixture(repo, "## 状态\n\nfixture\n")
    write(repo / "docs/handoffs/README.md", "# shadow\n\n## Active Handoffs\n")
    run_silently(doctor.check_handoff_contract)
    assert_message(doctor.fails, "复制了 Active Handoffs")


def _authorization_rule_fixture(rule_id: str) -> str:
    return doctor.rule_anchor(rule_id) + "\n" + doctor.rule_marker(rule_id) + "\n"


AUTHORIZATION_PLAYBOOK_FIXTURE = {
    "main/50_playbook/batch_workorder_spec.md": (
        _authorization_rule_fixture("AUTH-NONAMP-002")
        + _authorization_rule_fixture("AUTH-NONAMP-003")
    ),
    "main/50_playbook/session_close.md": (
        "user + direct_user\n" + _authorization_rule_fixture("AUTH-NONAMP-004")
    ),
    "main/50_playbook/remediation_governance.md": (
        "stopped_budget\n" + _authorization_rule_fixture("AUTH-NONAMP-005")
    ),
    "main/50_playbook/handoff_management.md": (
        _authorization_rule_fixture("AUTH-NONAMP-006")
        + _authorization_rule_fixture("AUTH-NONAMP-007")
        + _authorization_rule_fixture("AUTH-NONAMP-008")
    ),
}


def write_authorization_governance_fixture(repo: Path) -> None:
    """Seed the minimum surface check_authorization_governance reads."""
    instructions = _authorization_rule_fixture("AUTH-NONAMP-001") + "stopped_budget\ntoken\n"
    write(repo / "AGENTS.md", instructions)
    write(repo / "main/t2ag.md", FIXTURE_CONSTITUTION + instructions)
    for relative, content in AUTHORIZATION_PLAYBOOK_FIXTURE.items():
        write(repo / relative, content)


def test_resume_authorization_gate_is_enforced(root: Path) -> None:
    """NEGATIVE: dropping the resume gate from handoff_management must FAIL.

    G1 guards cross-conversation resumption: a taker must not turn a historical
    `authorization` field or a generic "go ahead" into fresh construction rights.
    The rule only binds if Doctor refuses the playbook that lost it.
    """
    repo = root / "t2ag"
    reset(repo)
    write_authorization_governance_fixture(repo)
    write(
        repo / "main/50_playbook/handoff_management.md",
        AUTHORIZATION_PLAYBOOK_FIXTURE["main/50_playbook/handoff_management.md"].replace(
            doctor.rule_marker("AUTH-NONAMP-007"), "接管方可自行判断范围", 1
        ),
    )
    run_silently(
        lambda: doctor.check_authorization_governance(include_external_handoffs=False)
    )
    assert_message(doctor.fails, "handoff_management.md")

    reset(repo)
    write_authorization_governance_fixture(repo)
    run_silently(
        lambda: doctor.check_authorization_governance(include_external_handoffs=False)
    )
    surviving = [message for message in doctor.fails if "handoff_management.md" in message]
    if surviving:
        raise AssertionError(f"complete resume gate must pass: {surviving}")


def test_authorization_gate_evidence_surface_reachability(root: Path) -> None:
    """NEGATIVE: 取不到取证面时本门必须出声，不得静默通过。

    该门断言两个 0.2.2 具名工单仍带作废注；取不到文件时两条断言都跳过，而
    「跳过了」与「守住了」在输出上不可区分——2026-08-18 的迁档正是这样让门
    fail-open 十天（§14.63）。rglob 修法只清了「归档使门失明」一路；「文书仓
    根本不在旁边」与「树内取不到具名件」是第二路，§14.67 要求它显式可见。
    """
    repo = root / "t2ag"
    handoffs = root / "docs/handoffs"
    v4_name = "T2AG_022_ACTIVITY_CLOSE_AUTONOMOUS_COMPLETION_WORKORDER_V4_2026-08-05.md"
    v2_name = "T2AG_022_ACTIVITY_CLOSE_EXECUTION_WORKORDER_V2_2026-08-04.md"

    def run() -> None:
        reset(repo)
        write_authorization_governance_fixture(repo)
        run_silently(doctor.check_authorization_governance)

    # R1：文书仓未挂载 ⇒ 一条「取证面未挂载」
    run()
    assert_message(doctor.warns, "授权门取证面未挂载")

    # R2：目录在而具名件取不到 ⇒ 逐件出声，且必须报出文件名
    handoffs.mkdir(parents=True, exist_ok=True)
    run()
    assert_message(doctor.warns, v4_name)
    assert_message(doctor.warns, v2_name)

    # G1：件落在 archive/ 子树且合规 ⇒ 完全静默（兼作 rglob 修法的回归位）
    archive = handoffs / "archive/v0.2.2"
    write(archive / v4_name, "**status**: `superseded_for_authorization`\n")
    write(archive / v2_name, "authorization supersession notice\n")
    run()
    noise = [
        message
        for message in doctor.warns + doctor.fails
        if "授权门取证" in message or "V4 工单" in message
    ]
    if noise:
        raise AssertionError(f"可达且合规的取证面必须静默：{noise}")

    # R3：件取得到但内容不合规 ⇒ 仍走原 FAIL，可达性 WARN 不得顶替它
    write(archive / v4_name, "no supersession notice here\n")
    run()
    assert_message(doctor.fails, "当前 V4 工单仍可被解释为 continuous RT3 授权")
    misreport = [message for message in doctor.warns if "授权门取证" in message]
    if misreport:
        raise AssertionError(f"已取到的文件不得报成不可达：{misreport}")


def test_environment_probes_report_broken_assumptions(root: Path) -> None:
    """NEGATIVE: each EA that does not hold must produce its own finding."""
    findings = doctor.environment_probe_results(
        root=root,
        production_root=Path("/definitely/not/this/root"),
        fitz_available=False,
        git_unlink=False,
    )
    levels = {message.split(" ")[0]: level for level, message in findings}
    if levels != {"EA-0001": "INFO", "EA-0002": "INFO", "EA-0003": "WARN"}:
        raise AssertionError(f"unexpected environment findings: {findings}")
    assert_message([m for _, m in findings], "不得为通过 apply 而设置 T2AG_022_CLOSE_TEST=1")
    assert_message([m for _, m in findings], "不得自动安装")
    assert_message([m for _, m in findings], "不得代清理")


def test_environment_probes_silent_when_assumptions_hold(root: Path) -> None:
    """POSITIVE: a host where all three hold must stay quiet — no INFO spam."""
    root.mkdir(parents=True, exist_ok=True)
    findings = doctor.environment_probe_results(
        root=root,
        production_root=root.resolve(),
        fitz_available=True,
        git_unlink=True,
    )
    if findings:
        raise AssertionError(f"healthy environment must produce no findings: {findings}")
    absent = doctor.environment_probe_results(
        root=root,
        production_root=root.resolve(),
        fitz_available=True,
        git_unlink=None,
    )
    if absent:
        raise AssertionError(f"a repo without .git must not be reported: {absent}")


def test_environment_registry_must_exist_and_list_every_probe(root: Path) -> None:
    """NEGATIVE: doctor must not probe assumptions the playbook never registered."""
    reset(root)
    run_silently(doctor.check_environment_assumptions)
    assert_message(doctor.fails, "环境假设登记缺失")

    reset(root)
    write(
        root / doctor.ENVIRONMENT_ASSUMPTIONS_REL,
        "# 环境假设登记\n\n**保护级别**：playbook\n\n### EA-0001\n",
    )
    run_silently(doctor.check_environment_assumptions)
    assert_message(doctor.fails, "环境假设登记缺条目")
    if "EA-0001" in str(doctor.fails):
        raise AssertionError(f"registered EA must not be reported missing: {doctor.fails}")


def _changelog_fixture_body(
    *,
    plan_sha: str,
    checks: str,
    atom_sha: str,
    evidence_line: str | None = None,
    include_anchor_block: bool = True,
) -> str:
    """Minimal newest-first changelog with one dated entry (U2 A+B+C shape)."""
    lines = [
        "# T2AG 变更历史\n",
        "\n",
        "---\n",
        "\n",
        "## [2026-08-07] Fixture changelog entry\n",
        "\n",
        "- narrative only\n",
        "\n",
    ]
    if include_anchor_block:
        lines.extend(
            [
                "#### 锚定断言（必填）\n",
                f"- runtime plan sha256 = {plan_sha} "
                f"← `python -B main/70_tools/t2ag_doctor.py --profile runtime | head -1`\n",
                f"- runtime checks = {checks} ← 同上\n",
                f"- doctor_checks atom set sha256 = {atom_sha} (n=42) "
                f"← `python -B -c \"...atom set...\"`\n",
                "\n",
            ]
        )
    if evidence_line is not None:
        lines.extend(
            [
                "#### 佐证断言（选填）\n",
                evidence_line if evidence_line.endswith("\n") else evidence_line + "\n",
            ]
        )
    return "".join(lines)


def test_changelog_anchor_mismatch_warns_with_both_values(root: Path) -> None:
    """NEGATIVE: declared anchors ≠ measured must WARN with both numbers."""
    declared = doctor.parse_changelog_anchors(
        _changelog_fixture_body(
            plan_sha="a" * 64,
            checks="1",
            atom_sha="b" * 64,
        )
    )
    measured = {
        "plan_sha256": "c" * 64,
        "checks": "29",
        "atom_set_sha256": "d" * 64,
    }
    # Pure compare path used by the checker.
    warns: list[str] = []
    for key, label in (
        ("plan_sha256", "runtime plan sha256"),
        ("checks", "runtime checks"),
        ("atom_set_sha256", "doctor_checks atom set sha256"),
    ):
        got, want = declared.get(key), measured[key]
        if got != want:
            warns.append(f"状态漂移无记录：Fixture {label} 声明值={got} 实测值={want}")
    if len(warns) != 3:
        raise AssertionError(f"expected three mismatch WARNs, got {warns}")
    assert_message(warns, "声明值=" + "a" * 64)
    assert_message(warns, "实测值=" + "c" * 64)
    assert_message(warns, "声明值=1")
    assert_message(warns, "实测值=29")


def test_changelog_missing_anchor_block_warns(root: Path) -> None:
    """NEGATIVE: deleting the anchor block must not silence the gate."""
    text = _changelog_fixture_body(
        plan_sha="a" * 64,
        checks="1",
        atom_sha="b" * 64,
        include_anchor_block=False,
    )
    anchors = doctor.parse_changelog_anchors(text)
    if anchors:
        raise AssertionError(f"missing block must parse empty, got {anchors}")
    entries = doctor.parse_changelog_entries(text)
    if not entries:
        raise AssertionError("fixture must still yield an entry")
    # Mirror check_changelog_contract's missing-block branch message shape.
    message = (
        f"changelog 最新条目缺锚定块：{entries[0]['heading']}；"
        f"实测 plan_sha256={'c' * 64} checks=29 atom_set_sha256={'d' * 64}"
    )
    if "缺锚定块" not in message or entries[0]["heading"] not in message:
        raise AssertionError(message)
    if "声明" in message and "实测" not in message:
        raise AssertionError("missing-block WARN must still expose measured values")


def test_changelog_entry_above_title_warns(root: Path) -> None:
    """NEGATIVE (F1): a dated entry parked above the main title must be named.

    2026-08-12 线上审查按「顶部=最新」自顶向下读，先取到忽略区的过期锚，
    产生一次真实误判草稿——忽略区不是理论风险，缺口必须具名。
    """
    text = (
        "## [2026-08-11] Parked above title\n\n- body\n\n---\n"
        + _changelog_fixture_body(plan_sha="a" * 64, checks="1", atom_sha="b" * 64)
    )
    violations = doctor.changelog_order_violations(text)
    if len(violations) != 1:
        raise AssertionError(f"expected exactly one violation, got {violations}")
    assert_message(violations, "忽略区有日期条目")
    assert_message(violations, "Parked above title")
    # 「最新」解析必须继续忽略前置区（既有约定不因新断言而改变）。
    entries = doctor.parse_changelog_entries(text)
    if "Fixture changelog entry" not in entries[0]["heading"]:
        raise AssertionError(f"front-zone entry must not become latest: {entries[0]}")
    # POSITIVE: clean fixture stays silent.
    clean = _changelog_fixture_body(plan_sha="a" * 64, checks="1", atom_sha="b" * 64)
    if doctor.changelog_order_violations(clean):
        raise AssertionError("clean fixture must yield zero violations")


def test_changelog_body_date_disorder_warns(root: Path) -> None:
    """NEGATIVE (F1): an older body entry above a newer one must name both ends."""
    text = _changelog_fixture_body(
        plan_sha="a" * 64, checks="1", atom_sha="b" * 64
    ) + "\n## [2026-08-09] Newer but buried\n\n- body\n"
    violations = doctor.changelog_order_violations(text)
    if len(violations) != 1:
        raise AssertionError(f"expected exactly one violation, got {violations}")
    assert_message(violations, "日期乱序")
    assert_message(violations, "2026-08-07")
    assert_message(violations, "2026-08-09")


def test_changelog_stale_evidence_warns_with_title_and_claim(root: Path) -> None:
    """NEGATIVE: evidence grep with zero hits must name title and claim text."""
    text = _changelog_fixture_body(
        plan_sha="a" * 64,
        checks="1",
        atom_sha="b" * 64,
        evidence_line=(
            "- playbook 含漂移留痕 ← "
            '`grep -c "漂移留痕" main/50_playbook/changelog_management.md`\n'
        ),
    )
    entries = doctor.parse_changelog_entries(text)
    stale = doctor.stale_changelog_claims(entries, runner=lambda _cmd: 0)
    if len(stale) != 1:
        raise AssertionError(f"expected one stale claim, got {stale}")
    title, claim, command = stale[0]
    if "Fixture changelog entry" not in title:
        raise AssertionError(f"title not named: {title}")
    if "漂移留痕" not in claim:
        raise AssertionError(f"claim text not named: {claim}")
    if "grep -c" not in command:
        raise AssertionError(f"command lost: {command}")


def _memory_budget_fixture(sections: str) -> str:
    return "# T2AG 跨会话记忆索引\n\n> 版本：0.2.3\n\n" + sections


def _seed_constitution_budget(root: Path, cap: int = 50, lines: int = 1) -> None:
    """Seed a t2ag.md whose only marked section is comfortably under budget.

    check_line_budget covers BOTH carriers, so a memory-carrier test that leaves
    t2ag.md absent would collect an unrelated FAIL and stop being a test of what
    it names.
    """
    body = "# T2AG\n\n" + f"## 宪法节  [max {cap}]\n" + "".join(
        f"- c{i}\n" for i in range(lines)
    )
    write(root / "main/t2ag.md", body)


def _run_line_budget_on_memory(root: Path) -> None:
    """Run the merged check with the constitution carrier held silent."""
    _seed_constitution_budget(root)
    run_silently(doctor.check_line_budget)


def test_line_budget_memory_over_limit_warns_with_both_numbers(root: Path) -> None:
    """NEGATIVE: an over-budget section must be named with actual AND cap.

    "WARN 不指名等于没报" — a bare "memory too long" leaves the reader to go
    measure it themselves, which is how a WARN becomes background noise.
    """
    reset(root)
    body = _memory_budget_fixture(
        "## 最近关键决策  [max 3]\n" + "".join(f"- entry {i}\n" for i in range(10))
    )
    write(root / "main/00_core/t2ag_memory.md", body)
    _run_line_budget_on_memory(root)
    assert_message(doctor.warns, "最近关键决策")
    assert_message(doctor.warns, "预算 3 行")
    if not any("实测 11 行" in w for w in doctor.warns):
        raise AssertionError(f"actual line count not named: {doctor.warns}")


def test_line_budget_memory_missing_markers_warns(root: Path) -> None:
    """NEGATIVE: no [max N] anywhere means the mechanism is silently off.

    This is the failure mode that actually happened: v0.1.2's markers vanished in
    the 0.2.0 snapshot migration and only the prose reference survived, so the
    rule looked alive for months while enforcing nothing.
    """
    reset(root)
    write(
        root / "main/00_core/t2ag_memory.md",
        _memory_budget_fixture("## 最近关键决策\n- entry\n"),
    )
    _run_line_budget_on_memory(root)
    assert_message(doctor.warns, "无任何 [max N] 节预算标记")


def test_line_budget_memory_within_limit_is_silent(root: Path) -> None:
    """POSITIVE: a section under budget must produce no output at all."""
    reset(root)
    write(
        root / "main/00_core/t2ag_memory.md",
        _memory_budget_fixture("## 最近关键决策  [max 50]\n- entry\n"),
    )
    _run_line_budget_on_memory(root)
    if doctor.warns or doctor.fails:
        raise AssertionError(f"healthy budget must stay quiet: {doctor.warns}")


def test_line_budget_memory_counts_only_its_own_section(root: Path) -> None:
    """Section spans to the NEXT `## `, so a long neighbour must not spill in."""
    body = _memory_budget_fixture(
        "## 短节  [max 5]\n- a\n- b\n\n"
        "## 长节\n" + "".join(f"- x{i}\n" for i in range(40))
    )
    budgets = doctor.memory_section_budgets(body)
    if len(budgets) != 1:
        raise AssertionError(f"only marked sections count: {budgets}")
    title, cap, actual = budgets[0]
    if title != "短节" or cap != 5 or actual != 4:
        raise AssertionError(f"boundary wrong: {budgets[0]}")


def test_changelog_runner_matches_grep_line_semantics(root: Path) -> None:
    """NEGATIVE: the runner must reproduce grep, not re.findall over the file.

    Regression for a live false positive (2026-08-07): a correct, freshly written
    claim `grep -c "^27\\. ..."` was reported 已腐烂 because the runner scanned the
    joined text without MULTILINE, so every `^`-anchored pattern returned zero.
    A gate that punishes precise patterns teaches people to write loose ones.
    """
    target = root / "sample.md"
    write(
        target,
        "27. alpha beta\n"
        "not 27. this line does not start with it\n"
        "gamma gamma\n",
    )

    anchored = doctor.default_changelog_evidence_runner(
        'grep -c "^27\\. alpha" sample.md', root=root
    )
    if anchored != 1:
        raise AssertionError(f"^-anchored grep -c must find the line; got {anchored}")

    # grep counts matching LINES; re.findall would count 2 for this pattern.
    repeated = doctor.default_changelog_evidence_runner(
        'grep -c "gamma" sample.md', root=root
    )
    if repeated != 1:
        raise AssertionError(f"grep -c counts lines, not matches; got {repeated}")

    dollar = doctor.default_changelog_evidence_runner(
        'grep -c "beta$" sample.md', root=root
    )
    if dollar != 1:
        raise AssertionError(f"$ must bind to line end; got {dollar}")

    absent = doctor.default_changelog_evidence_runner(
        'grep -c "^nope" sample.md', root=root
    )
    if absent != 0:
        raise AssertionError(f"genuinely absent pattern must be 0; got {absent}")


def test_changelog_runner_reports_unusable_pattern_as_not_evaluable(root: Path) -> None:
    """NEGATIVE: a pattern that will not compile is not the same as 'no hits'.

    Returning 0 would label the entry 已腐烂 — wrong finding, wrong fix. None means
    'not evaluable' so the claim is skipped rather than slandered.
    """
    target = root / "sample.md"
    write(target, "anything\n")
    result = doctor.default_changelog_evidence_runner(
        'grep -c "unclosed(" sample.md', root=root
    )
    if result is not None:
        raise AssertionError(f"unusable pattern must be None, got {result}")


def test_changelog_matching_anchors_and_evidence_are_silent(root: Path) -> None:
    """POSITIVE: matching anchors + hits must stay quiet (no INFO noise)."""
    measured = {
        "plan_sha256": "e" * 64,
        "checks": "29",
        "atom_set_sha256": "f" * 64,
    }
    text = _changelog_fixture_body(
        plan_sha=measured["plan_sha256"],
        checks=measured["checks"],
        atom_sha=measured["atom_set_sha256"],
        evidence_line='- 门名存在 ← `grep -c "changelog_management" main/50_playbook/_README.md`\n',
    )
    declared = doctor.parse_changelog_anchors(text)
    if declared != {
        "plan_sha256": measured["plan_sha256"],
        "checks": measured["checks"],
        "atom_set_sha256": measured["atom_set_sha256"],
    }:
        raise AssertionError(f"parse mismatch: {declared}")
    entries = doctor.parse_changelog_entries(text)
    stale = doctor.stale_changelog_claims(entries, runner=lambda _cmd: 3)
    if stale:
        raise AssertionError(f"healthy evidence must not be stale: {stale}")
    # No doctor.infos / warns path here — pure functions only, by design.


def test_changelog_pure_functions_mutation_is_killed(root: Path) -> None:
    """Mutation: empty stubs must fail the reverse tests (iron rule 3)."""
    text_mismatch = _changelog_fixture_body(
        plan_sha="a" * 64, checks="1", atom_sha="b" * 64
    )
    text_evidence = _changelog_fixture_body(
        plan_sha="a" * 64,
        checks="1",
        atom_sha="b" * 64,
        evidence_line='- x ← `grep -c "x" main/y.md`\n',
    )
    # Live functions must surface the faults.
    if not doctor.parse_changelog_anchors(text_mismatch):
        raise AssertionError("live parse must return anchors for mismatch fixture")
    live_stale = doctor.stale_changelog_claims(
        doctor.parse_changelog_entries(text_evidence),
        runner=lambda _cmd: 0,
    )
    if not live_stale:
        raise AssertionError("live stale_changelog_claims must flag zero hits")

    real_parse = doctor.parse_changelog_anchors
    real_stale = doctor.stale_changelog_claims
    try:
        doctor.parse_changelog_anchors = lambda _text: {}  # type: ignore[assignment]
        if doctor.parse_changelog_anchors(text_mismatch):
            raise AssertionError("stub parse should return empty")
        # Reverse test oracle: mismatch detection depends on non-empty parse.
        declared = doctor.parse_changelog_anchors(text_mismatch)
        measured = {"plan_sha256": "c" * 64, "checks": "29", "atom_set_sha256": "d" * 64}
        warns = []
        for key in measured:
            got = declared.get(key)
            if got is not None and got != measured[key]:
                warns.append("mismatch")
        if warns:
            raise AssertionError(
                "MUTATION SURVIVED: empty parse_changelog_anchors still produced "
                "mismatch WARNs — reverse test is blind"
            )

        doctor.stale_changelog_claims = lambda _entries, runner=None: []  # type: ignore[assignment]
        if doctor.stale_changelog_claims(
            doctor.parse_changelog_entries(text_evidence),
            runner=lambda _cmd: 0,
        ):
            raise AssertionError(
                "MUTATION SURVIVED: empty stale_changelog_claims returned hits"
            )
    finally:
        doctor.parse_changelog_anchors = real_parse  # type: ignore[assignment]
        doctor.stale_changelog_claims = real_stale  # type: ignore[assignment]


def test_git_unlink_probe_leaves_no_residue(root: Path) -> None:
    """The probe that detects EA-0003 must not itself become an EA-0003 victim."""
    repo = root / "repo"
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    before = sorted(path.name for path in (repo / ".git").iterdir())
    result = doctor.probe_git_unlink(repo)
    after = sorted(path.name for path in (repo / ".git").iterdir())
    if result is not True:
        raise AssertionError(f"tmpfs .git should be unlinkable; actual={result}")
    if before != after:
        raise AssertionError(f"probe left residue in .git: {before} -> {after}")
    if doctor.probe_git_unlink(root / "no_such_repo") is not None:
        raise AssertionError("probe must return None when there is no .git")


def test_git_unlink_probe_residue_is_bounded(root: Path) -> None:
    """NEGATIVE: on an unlink-hostile mount the probe must not accumulate residue.

    Regression for a real defect found in this batch: the first implementation
    used a per-PID probe name, so on the very environment EA-0003 describes every
    doctor run stranded one more undeletable file inside .git.  A per-run name is
    only safe where deletion works — that is, exactly where the probe is pointless.
    """
    repo = root / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD.lock").write_text("pre-existing lock\n", encoding="utf-8")

    real_unlink = Path.unlink

    def refuse_unlink(self, *args, **kwargs):
        if self.parent == git_dir:
            raise PermissionError("Operation not permitted")
        return real_unlink(self, *args, **kwargs)

    Path.unlink = refuse_unlink
    try:
        for _ in range(5):
            if doctor.probe_git_unlink(repo) is not False:
                raise AssertionError("probe must report False when unlink is refused")
    finally:
        Path.unlink = real_unlink

    residue = sorted(path.name for path in git_dir.iterdir())
    if residue != sorted([doctor.GIT_UNLINK_PROBE_NAME, "HEAD.lock"]):
        raise AssertionError(f"residue must stay capped at one probe file: {residue}")
    if not (git_dir / "HEAD.lock").is_file():
        raise AssertionError("probe must never remove a pre-existing git lock")


def _gate_ledger_fixture(
    *,
    anchor: str = "C1-B001-P029-N01",
    anchor_label: str = "起算块",
    rows: str = "",
) -> str:
    return (
        "# lesson01\n\n## 门台账\n\n"
        f"ledger_since: 2026-08-08 | {anchor_label}: {anchor}\n\n"
        "| 行ID | 块ID | 门类型 | 闭合依据 | 感受回应 | 授权原文 | 消费于 |\n"
        "|---|---|---|---|---|---|---|\n" + rows
    )


_GATE_CKPT = (
    "| C1-B001-P029-N01 | G | 29 | A | d | confirmed |\n"
    "| C1-B001-P029-N02 | G | 29 | A | d | confirmed |\n"
    "| C1-B001-P030-N01 | G | 30 | A | d | confirmed |\n"
)

_GATE_OK_ROWS = (
    "| GT-0001 | C1-B001-P029-N01 | 块过渡 | 答对确认题 | \"没问题\" | \"继续\"(10:00) | C1-B001-P029-N02 |\n"
    "| GT-0002 | C1-B001-P029-N02 | 块过渡 | 答对确认题 | \"没问题\" | \"继续\"(10:05) | C1-B001-P030-N01 |\n"
    "| GT-0003 | PDF 29→30 | 翻页 | 旧页清单已报 | \"好\" | \"进入\"(10:06) | C1-B001-P030-N01 |\n"
)


def test_gate_ledger_missing_transition_row_warns(root: Path) -> None:
    """NEGATIVE: a confirmed crossing without its 块过渡 row must be named.

    P-0054 made mechanical: 宣布不等于交接 — from now on a skipped gate is a
    missing row in file space, not a memory-reconstruction exercise a week later.
    """
    reset(root)
    course = root / "main/40_course/C1"
    write(course / "progress.md", "# p\n\n" + _GATE_CKPT)
    write(course / "lessons/lesson01/lesson01.md", _gate_ledger_fixture())
    run_silently(lambda: doctor.check_gate_ledger({"C1": (course, {})}))
    assert_message(doctor.warns, "GATE-LEDGER-001")
    assert_message(doctor.warns, "C1-B001-P029-N01 → C1-B001-P029-N02")


def test_gate_ledger_missing_pageturn_row_warns(root: Path) -> None:
    """NEGATIVE: page change covered by transitions but no 翻页 row → 002 only."""
    ledger = doctor.parse_gate_ledger(_gate_ledger_fixture(rows=(
        "| GT-0001 | C1-B001-P029-N01 | 块过渡 | ok | ok | \"继续\"(10:00) | C1-B001-P029-N02 |\n"
        "| GT-0002 | C1-B001-P029-N02 | 块过渡 | ok | ok | \"继续\"(10:05) | C1-B001-P030-N01 |\n"
    )))
    checkpoints = doctor.checkpoint_rows_from("x\n" + _GATE_CKPT, "C1-B001-P029-N01")
    findings = doctor.gate_ledger_findings(ledger, checkpoints, carrier="C1/lesson01")
    codes = [code for code, _ in findings]
    if "GATE-LEDGER-002" not in codes or "GATE-LEDGER-001" in codes:
        raise AssertionError(f"want exactly the pageturn gap: {findings}")


def test_gate_ledger_placeholder_authorization_warns(root: Path) -> None:
    """NEGATIVE: 授权原文 must be a verbatim quote, not a placeholder token."""
    ledger = doctor.parse_gate_ledger(_gate_ledger_fixture(rows=(
        "| GT-0001 | C1-B001-P029-N01 | 块过渡 | ok | ok | 待填 | C1-B001-P029-N02 |\n"
    )))
    checkpoints = doctor.checkpoint_rows_from("x\n" + _GATE_CKPT, "C1-B001-P029-N01")
    findings = doctor.gate_ledger_findings(ledger, checkpoints, carrier="C1/lesson01")
    if not any(code == "GATE-LEDGER-003" for code, _ in findings):
        raise AssertionError(f"placeholder authorization not flagged: {findings}")


def test_gate_ledger_duplicate_row_id_warns(root: Path) -> None:
    """NEGATIVE: GT ids must be strictly increasing and unique → 004."""
    ledger = doctor.parse_gate_ledger(_gate_ledger_fixture(rows=(
        "| GT-0002 | a | 块过渡 | ok | ok | \"继续\"(10:00) | b |\n"
        "| GT-0002 | b | 块过渡 | ok | ok | \"继续\"(10:05) | c |\n"
    )))
    findings = doctor.gate_ledger_findings(ledger, [], carrier="C1/lesson01")
    if not any(code == "GATE-LEDGER-004" for code, _ in findings):
        raise AssertionError(f"duplicate row id not flagged: {findings}")


def test_gate_ledger_missing_review_closure_warns(root: Path) -> None:
    """NEGATIVE (Exercise): a post-anchor RV without its 题目闭环 row → 005."""
    ledger = doctor.parse_gate_ledger(
        _gate_ledger_fixture(anchor="RV0001/AT0001", anchor_label="起算证据")
    )
    findings = doctor.gate_ledger_findings(
        ledger, [], carrier="C1/exercise01", rv_ids=("RV0002",)
    )
    if not any(code == "GATE-LEDGER-005" for code, _ in findings):
        raise AssertionError(f"missing closure row not flagged: {findings}")


def test_gate_ledger_hint_without_authorization_row_warns(root: Path) -> None:
    """NEGATIVE (Exercise): a recorded direction_hint without its row → 006."""
    ledger = doctor.parse_gate_ledger(
        _gate_ledger_fixture(anchor="RV0001/AT0001", anchor_label="起算证据")
    )
    findings = doctor.gate_ledger_findings(
        ledger, [], carrier="C1/exercise01",
        attempt_hints=(("AT0002", "direction_hint"),),
    )
    if not any(code == "GATE-LEDGER-006" for code, _ in findings):
        raise AssertionError(f"unauthorized hint not flagged: {findings}")


def test_gate_ledger_malformed_table_fail_closed(root: Path) -> None:
    """NEGATIVE: wrong arity or a missing anchor line is 000, nothing else.

    Fail-closed means a broken ledger never silently passes as an empty one.
    """
    bad_row = doctor.parse_gate_ledger(_gate_ledger_fixture(rows=(
        "| GT-0001 | a | 块过渡 | ok | \"继续\"(10:00) | b |\n"
    )))
    findings = doctor.gate_ledger_findings(bad_row, [], carrier="C1/lesson01")
    if [code for code, _ in findings] != ["GATE-LEDGER-000"]:
        raise AssertionError(f"malformed row must be 000 only: {findings}")
    no_anchor = doctor.parse_gate_ledger(
        "# lesson01\n\n## 门台账\n\n| 行ID |\n"
    )
    findings = doctor.gate_ledger_findings(no_anchor, [], carrier="C1/lesson01")
    if not any(code == "GATE-LEDGER-000" for code, _ in findings):
        raise AssertionError(f"missing anchor must be 000: {findings}")


def test_gate_ledger_complete_ledger_is_silent(root: Path) -> None:
    """POSITIVE: a fully-logged crossing sequence must produce no findings."""
    ledger = doctor.parse_gate_ledger(_gate_ledger_fixture(rows=_GATE_OK_ROWS))
    checkpoints = doctor.checkpoint_rows_from("x\n" + _GATE_CKPT, "C1-B001-P029-N01")
    findings = doctor.gate_ledger_findings(ledger, checkpoints, carrier="C1/lesson01")
    if findings:
        raise AssertionError(f"complete ledger must stay quiet: {findings}")


def test_gate_ledger_carrier_without_section_is_skipped(root: Path) -> None:
    """POSITIVE: no 门台账 section means no check — deployment stays gradual."""
    reset(root)
    course = root / "main/40_course/C1"
    write(course / "progress.md", "# p\n\n" + _GATE_CKPT)
    write(course / "lessons/lesson01/lesson01.md", "# lesson01\n\n## 教学记录\n")
    run_silently(lambda: doctor.check_gate_ledger({"C1": (course, {})}))
    if doctor.warns or doctor.fails:
        raise AssertionError(f"carrier without section must be skipped: {doctor.warns}")


def test_gate_ledger_blocks_before_anchor_are_exempt(root: Path) -> None:
    """POSITIVE: crossings before ledger_since are history — never checked."""
    ledger = doctor.parse_gate_ledger(_gate_ledger_fixture(
        anchor="C1-B001-P029-N02",
        rows=(
            "| GT-0001 | C1-B001-P029-N02 | 块过渡 | ok | ok | \"继续\"(10:05) | C1-B001-P030-N01 |\n"
            "| GT-0002 | PDF 29→30 | 翻页 | 旧页清单已报 | \"好\" | \"进入\"(10:06) | C1-B001-P030-N01 |\n"
        ),
    ))
    checkpoints = doctor.checkpoint_rows_from("x\n" + _GATE_CKPT, "C1-B001-P029-N02")
    findings = doctor.gate_ledger_findings(ledger, checkpoints, carrier="C1/lesson01")
    if findings:
        raise AssertionError(f"pre-anchor history must be exempt: {findings}")


def test_gate_ledger_pure_functions_mutation_is_killed(root: Path) -> None:
    """Mutation: an always-empty verdict function must blind the reverse tests."""
    ledger = doctor.parse_gate_ledger(_gate_ledger_fixture())
    checkpoints = doctor.checkpoint_rows_from("x\n" + _GATE_CKPT, "C1-B001-P029-N01")
    live = doctor.gate_ledger_findings(ledger, checkpoints, carrier="C1/lesson01")
    if not any(code == "GATE-LEDGER-001" for code, _ in live):
        raise AssertionError("live findings must flag the missing transition")
    real = doctor.gate_ledger_findings
    try:
        doctor.gate_ledger_findings = (  # type: ignore[assignment]
            lambda *args, **kwargs: []
        )
        if doctor.gate_ledger_findings(ledger, checkpoints, carrier="C1/lesson01"):
            raise AssertionError("MUTATION SURVIVED: stub still produced findings")
    finally:
        doctor.gate_ledger_findings = real  # type: ignore[assignment]


def test_gate_ledger_header_driven_checkpoint_table(root: Path) -> None:
    """POSITIVE: a header table without 页码 (goal-driver) resolves the anchor.

    2026-08-10: AIF1001r's ledger drew a false 000 only because its
    checkpoint table has no page column — the parser now follows the
    header row instead of assuming one fixed shape.
    """
    progress = (
        "# p\n\n## 当前节点 checkpoints\n\n"
        "| checkpoint_id | parent_node | 到达内容 | 状态 |\n"
        "|---|---|---|---|\n"
        "| A1-L1-S00 | A1-L1 | 定标 | confirmed |\n"
        "| A1-L1-S01 | A1-L1 | 对表 | confirmed |\n"
    )
    checkpoints = doctor.checkpoint_rows_from(progress, "A1-L1-S00")
    if checkpoints is None or [c[0] for c in checkpoints] != ["A1-L1-S00", "A1-L1-S01"]:
        raise AssertionError(f"header-driven table not parsed: {checkpoints}")
    if any(page != "" for _, page, _ in checkpoints):
        raise AssertionError("pageless table must yield empty page fields")


def test_gate_ledger_detour_transition_chain_is_accepted(root: Path) -> None:
    """POSITIVE: a→X→b detour rows satisfy the a→b crossing（学生主导分支）."""
    ledger = doctor.parse_gate_ledger(_gate_ledger_fixture(rows=(
        "| GT-0001 | C1-B001-P029-N01 | 块过渡 | ok | ok | \"继续\"(10:00) | 0c 复述门 |\n"
        "| GT-0002 | 0c（树外节点） | 块过渡 | ok | ok | \"继续\"(10:05) | 消费于 N02 对表 |\n"
    )))
    ckpt = (
        "| C1-B001-P029-N01 | G | 29 | A | d | confirmed |\n"
        "| C1-B001-P029-N02 | G | 29 | A | d | confirmed |\n"
    )
    checkpoints = doctor.checkpoint_rows_from("x\n" + ckpt, "C1-B001-P029-N01")
    findings = doctor.gate_ledger_findings(ledger, checkpoints, carrier="C1/lesson01")
    if any(code == "GATE-LEDGER-001" for code, _ in findings):
        raise AssertionError(f"detour chain wrongly flagged: {findings}")


def test_gate_ledger_active_textbook_lesson_without_section_fails(root: Path) -> None:
    """NEGATIVE: the CURRENT textbook Lesson missing 门台账 → 007 FAIL.

    The bridge from prose gates to machine landing must not be opt-in
    exactly where teaching is happening (the P-0054 hole).
    """
    reset(root)
    course = root / "main/40_course/C1"
    write(course / "progress.md", "# p\n")
    write(course / "lessons/lesson01/lesson01.md", "# lesson01\n\n正文，无台账节。\n")
    meta = {
        "course_driver": "textbook",
        "current_activity": "lesson",
        "current_activity_id": "lesson01",
    }
    run_silently(lambda: doctor.check_gate_ledger({"C1": (course, meta)}))
    assert_message(doctor.fails, "GATE-LEDGER-007")


def test_gate_ledger_inactive_or_nontextbook_lesson_is_exempt(root: Path) -> None:
    """POSITIVE: 007 guards only the active textbook lesson."""
    for meta in (
        {},
        {"course_driver": "goal", "current_activity": "lesson",
         "current_activity_id": "lesson01"},
        {"course_driver": "textbook", "current_activity": "none",
         "current_activity_id": "none"},
    ):
        reset(root)
        course = root / "main/40_course/C1"
        write(course / "progress.md", "# p\n")
        write(course / "lessons/lesson01/lesson01.md", "# lesson01\n\n无台账节。\n")
        run_silently(lambda: doctor.check_gate_ledger({"C1": (course, meta)}))
        if any("GATE-LEDGER-007" in message for message in doctor.fails):
            raise AssertionError(f"007 fired outside its scope: meta={meta}")


_PLOG_HEADER = "next_id: P-0068\nclosure_fields_since: P-0060\n\n"


def test_problemlog_closure_missing_anchor_fail_closed(root: Path) -> None:
    """NEGATIVE: entries without a header anchor → 000; empty log is silent."""
    findings = doctor.problemlog_closure_findings(
        "## P-0001 | [2026-08-10] | x\n\n- closure: open\n"
    )
    if not any(code == "PLOG-CLOSURE-000" for code, _ in findings):
        raise AssertionError(f"missing anchor not fail-closed: {findings}")
    if doctor.problemlog_closure_findings("# 空实例，无条目\n"):
        raise AssertionError("a fresh instance without entries must stay silent")


def test_problemlog_closure_missing_field_after_anchor_warns(root: Path) -> None:
    """NEGATIVE: post-anchor entry without `- closure:` → 001; legacy exempt."""
    text = _PLOG_HEADER + (
        "## P-0059 | [2026-08-01] | legacy\n\n- tags: [a]\n\n"
        "## P-0060 | [2026-08-10] | new\n\n- tags: [b]\n"
    )
    findings = doctor.problemlog_closure_findings(text)
    if [code for code, _ in findings] != ["PLOG-CLOSURE-001"]:
        raise AssertionError(f"want exactly one 001 for P-0060: {findings}")
    if "P-0060" not in findings[0][1]:
        raise AssertionError(f"001 must name the entry: {findings}")
    bad_value = _PLOG_HEADER + "## P-0061 | [2026-08-10] | v\n\n- closure: 已修\n"
    findings = doctor.problemlog_closure_findings(bad_value)
    if not any(code == "PLOG-CLOSURE-001" for code, _ in findings):
        raise AssertionError(f"illegal closure value not flagged: {findings}")


def test_problemlog_closure_two_strike_prose_landing_warns(root: Path) -> None:
    """NEGATIVE: 补救在位期间复发 >= STRIKE_LIMIT + prose_accepted → 002（出局）。

    2026-08-22 改判：数 strike 不数 occurrence。这里 occ=5、基线=3 → strikes=2，
    即「补救落地后又坏了两次」，才是真正的出局。
    """
    text = _PLOG_HEADER + (
        "## P-0061 | [2026-08-10] | repeat\n\n"
        "- occurrence_count: 5\n- remedy_since: 3\n"
        "- closure: prose_accepted（临时）\n"
    )
    findings = doctor.problemlog_closure_findings(text)
    hits = [m for code, m in findings if code == "PLOG-CLOSURE-002"]
    if not hits:
        raise AssertionError(f"strike-limit prose landing not flagged: {findings}")
    if "出局" not in hits[0] or "2" not in hits[0]:
        raise AssertionError(f"出局讯息须报出 strike 数与推导: {hits}")


def test_problemlog_closure_strikes_count_remedies_not_sightings(root: Path) -> None:
    """POSITIVE: 补救从未在位时，出现多少次都不剥夺散文——这是本次改判的全部理由。

    P-0078 是纯粹形态：三次全部发生在条目存在之前，从未有任何散文补救在位。旧规则
    （occurrence_count>=2 即出局）会判一个**没人试过用散文修**的问题永久失去散文。
    第 1 次时执行模型与用户都不知情，那不是一次挥空，是击球员还没站上打击区。
    """
    never_remedied = _PLOG_HEADER + (
        "## P-0078 | [2026-08-22] | 一夜三次，开账前无补救\n\n"
        "- occurrence_count: 3\n- closure: open\n"
    )
    if doctor.problemlog_closure_findings(never_remedied):
        raise AssertionError("从无补救在位的条目不得被判出局")
    just_landed = _PLOG_HEADER + (
        "## P-0079 | [2026-08-22] | 补救刚落地\n\n"
        "- occurrence_count: 3\n- remedy_since: 3\n"
        "- closure: prose_accepted（首次尝试散文）\n"
    )
    if doctor.problemlog_closure_findings(just_landed):
        raise AssertionError("strikes=0 时散文合法：机会要真给过才算数")
    one_strike = just_landed.replace("occurrence_count: 3", "occurrence_count: 4")
    if doctor.problemlog_closure_findings(one_strike):
        raise AssertionError(
            f"strikes=1 仍在容许内（阈值 {doctor.STRIKE_LIMIT}），"
            "旧规则等价于 1 即出局，本次改判正是要多给这一次"
        )


def test_problemlog_closure_prose_without_baseline_is_dangling_counter(
    root: Path,
) -> None:
    """NEGATIVE: prose_accepted 缺 remedy_since → 002。

    缺基线则 strike 永远算不起来——计数器悬空、出局条件永不可能触发。P-0069 那个
    「手工累积 5–10 条」的重启条件正是这么死的：累加器从未建成，条件不可能成立。
    机制性禁止重演，不靠谁记得填。
    """
    text = _PLOG_HEADER + (
        "## P-0061 | [2026-08-10] | no baseline\n\n"
        "- occurrence_count: 9\n- closure: prose_accepted（就这样吧）\n"
    )
    findings = doctor.problemlog_closure_findings(text)
    hits = [m for code, m in findings if code == "PLOG-CLOSURE-002"]
    if not hits or "remedy_since" not in hits[0]:
        raise AssertionError(f"缺基线必须点名 remedy_since: {findings}")


def test_problemlog_closure_baseline_after_fact_is_malformed(root: Path) -> None:
    """NEGATIVE: remedy_since > occurrence_count → 002（基线不能晚于事实）。"""
    text = _PLOG_HEADER + (
        "## P-0061 | [2026-08-10] | impossible\n\n"
        "- occurrence_count: 2\n- remedy_since: 5\n"
        "- closure: prose_accepted（x）\n"
    )
    findings = doctor.problemlog_closure_findings(text)
    if not any(
        code == "PLOG-CLOSURE-002" and "大于" in m for code, m in findings
    ):
        raise AssertionError(f"基线晚于事实必须报: {findings}")


def test_problemlog_closure_machine_landings_are_silent(root: Path) -> None:
    """POSITIVE: open / check= / tool= landings and first-strike prose pass."""
    text = _PLOG_HEADER + (
        "## P-0060 | [2026-08-10] | a\n\n- occurrence_count: 1\n"
        "- remedy_since: 1\n- closure: prose_accepted（成本低）\n\n"
        "## P-0061 | [2026-08-10] | b\n\n- occurrence_count: 4\n"
        "- closure: check=GATE-LEDGER-007\n\n"
        "## P-0062 | [2026-08-10] | c\n\n- closure: tool=70_tools/t2ag_hint_gate.py\n\n"
        "## P-0063 | [2026-08-10] | d\n\n- closure: open\n"
    )
    findings = doctor.problemlog_closure_findings(text)
    if findings:
        raise AssertionError(f"legal landings must stay silent: {findings}")


_RGATE_CHECKS = frozenset({"runtime.structure", "runtime.gate_ledger"})


def _rule_docs(body: str, path: str = "50_playbook/rule_admission_gate.md") -> dict:
    return {path: body}


def _rgate_fixture(root: Path) -> Path:
    """A minimal tree whose landings actually resolve; returns its main/."""
    reset(root)
    write(root / "main/70_tools/t2ag_doctor.py", "# fixture tool\n")
    write(
        root / "main/50_playbook/doctor_contracts.md",
        "# 契约\n\n## 一、结果分类\n\n表格在此。\n",
    )
    write(root / "main/t2ag.md", "# 宪法\n\n## 1. 不可变原则\n")
    return root / "main"


def test_rule_enforcement_sound_landings_are_silent(root: Path) -> None:
    """POSITIVE: the four legal landings, all resolvable, stay silent."""
    main = _rgate_fixture(root)
    body = (
        "enforcement: check=runtime.gate_ledger\n"
        "- enforcement: tool=70_tools/t2ag_doctor.py\n"
        "enforcement: context=50_playbook/doctor_contracts.md#一、结果分类\n"
        "enforcement: prose_accepted（理由：语义识别无机器手段）\n"
    )
    findings = doctor.rule_enforcement_findings(
        _rule_docs(body), known_checks=_RGATE_CHECKS, main=main
    )
    if findings:
        raise AssertionError(f"sound landings must stay silent: {findings}")


def test_rule_enforcement_dangling_check_fails(root: Path) -> None:
    """NEGATIVE: `check=` naming no registered check → RULE-ENF-001 FAIL.

    A finding code (GATE-LEDGER-007) is the tempting wrong answer here: the
    namespace is the `doctor_checks` key set, not the finding vocabulary.
    """
    main = _rgate_fixture(root)
    for value in ("check=runtime.not_a_check", "check=GATE-LEDGER-007"):
        findings = doctor.rule_enforcement_findings(
            _rule_docs(f"enforcement: {value}\n"),
            known_checks=_RGATE_CHECKS,
            main=main,
        )
        if [(code, severity) for code, severity, _ in findings] != [
            ("RULE-ENF-001", "FAIL")
        ]:
            raise AssertionError(f"{value} must fail as dangling: {findings}")


def test_rule_enforcement_missing_tool_fails(root: Path) -> None:
    """NEGATIVE: `tool=` pointing at no file → RULE-ENF-002 FAIL."""
    main = _rgate_fixture(root)
    findings = doctor.rule_enforcement_findings(
        _rule_docs("enforcement: tool=70_tools/no_such_tool.py\n"),
        known_checks=_RGATE_CHECKS,
        main=main,
    )
    if not any(code == "RULE-ENF-002" for code, _, _ in findings):
        raise AssertionError(f"missing tool not flagged: {findings}")
    if any(severity != "FAIL" for _, severity, _ in findings):
        raise AssertionError(f"missing tool must be FAIL: {findings}")


def test_rule_enforcement_broken_context_anchor_warns(root: Path) -> None:
    """NEGATIVE: stale `context=` anchor → RULE-ENF-003 WARN, not FAIL.

    U-1: rewording prose must not block a lesson; the rule still stands, only
    the citation rotted.  Also pins the split-on-first-# rule — the anchor
    itself may contain '#'.
    """
    main = _rgate_fixture(root)
    findings = doctor.rule_enforcement_findings(
        _rule_docs("enforcement: context=t2ag.md#不再存在的锚#带井号\n"),
        known_checks=_RGATE_CHECKS,
        main=main,
    )
    if [(code, severity) for code, severity, _ in findings] != [
        ("RULE-ENF-003", "WARN")
    ]:
        raise AssertionError(f"stale anchor must WARN once: {findings}")
    if "不再存在的锚#带井号" not in findings[0][2]:
        raise AssertionError(f"anchor must survive the first-# split: {findings}")


def test_rule_enforcement_empty_prose_reason_warns(root: Path) -> None:
    """NEGATIVE: `prose_accepted` without a reason → RULE-ENF-004 WARN."""
    main = _rgate_fixture(root)
    for value in ("prose_accepted", "prose_accepted（）", "prose_accepted()"):
        findings = doctor.rule_enforcement_findings(
            _rule_docs(f"enforcement: {value}\n"),
            known_checks=_RGATE_CHECKS,
            main=main,
        )
        if [(code, severity) for code, severity, _ in findings] != [
            ("RULE-ENF-004", "WARN")
        ]:
            raise AssertionError(f"{value!r} must warn on empty reason: {findings}")
    kept = doctor.rule_enforcement_findings(
        _rule_docs("enforcement: prose_accepted(reason in halfwidth)\n"),
        known_checks=_RGATE_CHECKS,
        main=main,
    )
    if kept:
        raise AssertionError(f"halfwidth parens must be accepted too: {kept}")


def test_rule_enforcement_misplaced_fields_fail(root: Path) -> None:
    """NEGATIVE: `enforcement:` in the record area / `closure:` in a rule file."""
    main = _rgate_fixture(root)
    findings = doctor.rule_enforcement_findings(
        {
            "00_core/t2ag_problemlog.md": "enforcement: check=runtime.structure\n",
            "50_playbook/rule_admission_gate.md": "- closure: open\n",
        },
        known_checks=_RGATE_CHECKS,
        main=main,
    )
    codes = [(code, severity) for code, severity, _ in findings]
    if codes != [("RULE-ENF-005", "FAIL"), ("RULE-ENF-005", "FAIL")]:
        raise AssertionError(f"both misplacements must FAIL: {findings}")


def test_rule_enforcement_fenced_examples_are_silent(root: Path) -> None:
    """POSITIVE (2A self-reference escape): examples inside fences never fire.

    Without this the playbook that defines the field is the first document the
    check fails on — the document about the checker tripping the checker.
    """
    main = _rgate_fixture(root)
    body = (
        "```text\n"
        "enforcement: check=runtime.utterly_missing\n"
        "enforcement: tool=70_tools/ghost.py\n"
        "- closure: open\n"
        "```\n"
        "enforcement: check=runtime.structure\n"
    )
    findings = doctor.rule_enforcement_findings(
        _rule_docs(body), known_checks=_RGATE_CHECKS, main=main
    )
    if findings:
        raise AssertionError(f"fenced examples must not fire: {findings}")
    unfenced = doctor.rule_enforcement_findings(
        _rule_docs(body.replace("```text\n", "").replace("```\n", "")),
        known_checks=_RGATE_CHECKS,
        main=main,
    )
    if len(unfenced) != 3:
        raise AssertionError(
            f"same lines outside the fence must fire (fixture cannot no-op): {unfenced}"
        )


def _bind_checks(**bindings: str) -> dict:
    """A doctor_checks-shaped dict; named ids get a rule_binding, others don't."""
    spec = {"phase": "runtime", "handler": "h", "path_prefixes": ["*"]}
    checks = {}
    for check_id, binding in bindings.items():
        entry = dict(spec)
        if binding:
            entry["rule_binding"] = binding
        checks[check_id.replace("__", ".")] = entry
    return checks


def test_rule_binding_r1_resolvable_binding_is_silent(root: Path) -> None:
    """POSITIVE 判据一: a bare `path#anchor` that resolves stays silent."""
    main = _rgate_fixture(root)
    checks = _bind_checks(runtime__gate_ledger="50_playbook/doctor_contracts.md#一、结果分类")
    findings = doctor.rule_binding_findings(checks, frozenset(), main=main)
    if [code for code, _, _ in findings] != []:
        raise AssertionError(f"resolvable binding must stay silent: {findings}")


def test_rule_binding_r1_unresolvable_binding_fails(root: Path) -> None:
    """NEGATIVE 判据一: every shape of an unsound value → RULE-BIND-001 FAIL.

    The `context=`-prefixed case is the interesting one: F-A fixes the value as
    BARE `path#anchor`, so a prefixed value is a shape error, not a missing
    file.  Reporting it as "file not found: context=50_playbook/..." would
    disguise the shape error as a landing error and send the reader hunting for
    a file that was never meant to exist.
    """
    main = _rgate_fixture(root)
    for value in (
        "50_playbook/doctor_contracts.md#锚已不存在",   # anchor rotted
        "50_playbook/no_such_file.md#一、结果分类",      # file gone
        "50_playbook/doctor_contracts.md",              # no '#'
        "#一、结果分类",                                 # no path
        "context=50_playbook/doctor_contracts.md#一、结果分类",  # prefix leaked in
        "",
        None,
        12,
    ):
        checks = _bind_checks(runtime__gate_ledger="x")
        checks["runtime.gate_ledger"]["rule_binding"] = value
        findings = doctor.rule_binding_findings(checks, frozenset(), main=main)
        if [(code, severity) for code, severity, _ in findings] != [
            ("RULE-BIND-001", "FAIL")
        ]:
            raise AssertionError(f"{value!r} must fail as unsound: {findings}")


def test_rule_binding_r2_full_coverage_is_silent(root: Path) -> None:
    """POSITIVE 判据二: when every entry declares a binding, no 002."""
    main = _rgate_fixture(root)
    anchor = "50_playbook/doctor_contracts.md#一、结果分类"
    checks = _bind_checks(runtime__structure=anchor, runtime__gate_ledger=anchor)
    findings = doctor.rule_binding_findings(checks, frozenset(), main=main)
    if findings:
        raise AssertionError(f"full coverage must stay silent: {findings}")


def test_rule_binding_r2_missing_aggregates_into_one_warn(root: Path) -> None:
    """NEGATIVE 判据二: absent bindings → exactly ONE WARN carrying the total.

    Per-entry reporting is the tempting wrong answer: 61 lines would drown the
    reading surface, and coverage is one quantity, not 61 independent events.
    The total must survive into the message, and the sample must be bounded.
    """
    main = _rgate_fixture(root)
    checks = _bind_checks(**{f"runtime__c{n:02d}": "" for n in range(9)})
    checks["runtime.bound"] = {
        "phase": "runtime",
        "handler": "h",
        "path_prefixes": ["*"],
        "rule_binding": "50_playbook/doctor_contracts.md#一、结果分类",
    }
    findings = doctor.rule_binding_findings(checks, frozenset(), main=main)
    if [(code, severity) for code, severity, _ in findings] != [
        ("RULE-BIND-002", "WARN")
    ]:
        raise AssertionError(f"missing bindings must aggregate to one WARN: {findings}")
    message = findings[0][2]
    if "9/10" not in message:
        raise AssertionError(f"aggregate WARN must carry the total: {message}")
    # The bound is asserted as a literal, not read back from the module: taking
    # it from RULE_BINDING_SAMPLE_LIMIT would make the assertion move with the
    # code it is supposed to hold still, and widening the limit would pass.
    if message.count("runtime.c") != 5 or "…" not in message:
        raise AssertionError(f"sample must be truncated at 5 and say so: {message}")


def test_rule_binding_r3_bidirectional_edges_leave_no_orphan(root: Path) -> None:
    """POSITIVE 判据三: a check both named by a rule and self-declaring → ∅."""
    orphans = doctor.rule_binding_orphans(
        {"runtime.gate_ledger"}, {"runtime.gate_ledger", "runtime.structure"}
    )
    if orphans:
        raise AssertionError(f"a bidirectional edge is not an orphan: {orphans}")


def test_rule_binding_r3_one_way_edge_is_an_orphan(root: Path) -> None:
    """NEGATIVE 判据三: named by a rule, no self-declaration → orphan.

    The negative lives on the PURE FUNCTION, and it has to: orphan(literal) =
    {named} ∩ {unbound} ⊆ {unbound} = the 002 set, so after "002 wins" dedup
    the 003-only set is ∅ *by identity*, for any repository state — the
    aggregate RULE-BIND-003 line is unreachable, not merely quiet today.  A
    negative asserted at the aggregate layer could therefore never go red, and
    判据三 would ship with no falsifiable test at all.  This pins both layers:
    the judgement itself discriminates, and the publishing layer suppresses.
    """
    orphans = doctor.rule_binding_orphans(
        {"runtime.gate_ledger", "runtime.skin"}, {"runtime.structure"}
    )
    if orphans != frozenset({"runtime.gate_ledger", "runtime.skin"}):
        raise AssertionError(f"one-way edges must be orphans: {orphans}")
    # Same data through the aggregate: 002 absorbs it, so 003 does not fire.
    main = _rgate_fixture(root)
    checks = _bind_checks(runtime__gate_ledger="", runtime__skin="")
    findings = doctor.rule_binding_findings(
        checks, {"runtime.gate_ledger", "runtime.skin"}, main=main
    )
    if [code for code, _, _ in findings] != ["RULE-BIND-002"]:
        raise AssertionError(f"002 must absorb the orphans at the aggregate: {findings}")


def test_rule_binding_named_set_ignores_fenced_examples(root: Path) -> None:
    """The naming side reuses the fence rule: examples are not live edges.

    Counting without `strip_fenced_blocks` inflates this repository's naming
    set from 9 IDs to 12 — the fenced specimens in the very playbook that
    defines the field.
    """
    named = doctor.enforcement_named_checks(
        _rule_docs(
            "```text\nenforcement: check=runtime.only_an_example\n```\n"
            "enforcement: check=runtime.gate_ledger\n"
        )
    )
    if named != frozenset({"runtime.gate_ledger"}):
        raise AssertionError(f"fenced specimens must not be named edges: {named}")
    outside = doctor.enforcement_named_checks(
        _rule_docs("enforcement: check=runtime.only_an_example\n")
    )
    if outside != frozenset({"runtime.only_an_example"}):
        raise AssertionError(f"fixture cannot no-op: {outside}")


def test_problemlog_closure_dangling_landing_warns(root: Path) -> None:
    """NEGATIVE (4A): closure naming a missing check/tool → 004, WARN not FAIL.

    Same defect as RULE-ENF-001/002; the severity stays WARN because a new
    check must not be used to quietly harden an old one's stance.
    """
    main = _rgate_fixture(root)
    text = _PLOG_HEADER + (
        "## P-0068 | [2026-08-15] | a\n\n- closure: check=runtime.not_a_check\n\n"
        "## P-0069 | [2026-08-15] | b\n\n- closure: tool=70_tools/ghost.py\n"
    )
    findings = doctor.problemlog_closure_findings(
        text, known_checks=_RGATE_CHECKS, main=main
    )
    if [code for code, _ in findings] != ["PLOG-CLOSURE-004", "PLOG-CLOSURE-004"]:
        raise AssertionError(f"both dangling landings must warn: {findings}")
    if doctor.problemlog_closure_findings(text):
        raise AssertionError("without injected inputs it must stay a form checker")


def test_problemlog_closure_duplicate_stable_id_warns(root: Path) -> None:
    """NEGATIVE (4A′): one `P-NNNN` naming two incidents → 003, with lines."""
    text = _PLOG_HEADER + (
        "## P-0068 | [2026-07-31] | first\n\n- closure: open\n\n"
        "## P-0069 | [2026-08-01] | other\n\n- closure: open\n\n"
        "## P-0068 | [2026-08-09] | second, same id\n\n- closure: open\n"
    )
    findings = doctor.problemlog_closure_findings(text)
    duplicates = [message for code, message in findings if code == "PLOG-CLOSURE-003"]
    if len(duplicates) != 1 or "P-0068" not in duplicates[0]:
        raise AssertionError(f"duplicate id must warn exactly once: {findings}")
    expected = [
        index + 1
        for index, line in enumerate(text.splitlines())
        if line.startswith("## P-0068")
    ]
    if any(str(line) not in duplicates[0] for line in expected):
        raise AssertionError(
            f"003 must name every line {expected}: {duplicates}"
        )


def _extsrc_fixture(root: Path) -> Path:
    """Tree where a diff_recorded anchor can actually resolve; returns main/."""
    reset(root)
    write(
        root / "main/40_course/C1/lessons/lesson01/lesson01.md",
        "# lesson01\n\n### 官方目录核实（2026-08-16，教师实取）\n\n预画 8 / 实际 13。\n",
    )
    return root / "main"


def _course_md(catalog: str = "") -> str:
    return "---\ntype: course\ncourse_id: C1\n" + catalog + "---\n# C1\n"


_EXTSRC_GOOD = (
    "source_catalog:\n"
    "  url: https://example.org/catalog\n"
    "  fetched_at: 2026-08-16\n"
    "  predicted_count: 8\n"
    "  actual_count: 13\n"
    "  diff_recorded: 40_course/C1/lessons/lesson01/lesson01.md#官方目录核实\n"
)


def test_external_source_missing_catalog_warns_only_when_ongoing(root: Path) -> None:
    """NEGATIVE+POSITIVE: ongoing → 001 WARN; planned → silent（不是待办）."""
    main = _extsrc_fixture(root)
    findings = doctor.external_source_findings(
        {"C1": ("ongoing", _course_md())}, main=main
    )
    if [(code, severity) for code, severity, _ in findings] != [
        ("EXTSRC-001", "WARN")
    ]:
        raise AssertionError(f"ongoing without catalog must warn once: {findings}")
    for lifecycle in ("planned", "completed", ""):
        quiet = doctor.external_source_findings(
            {"C1": (lifecycle, _course_md())}, main=main
        )
        if quiet:
            raise AssertionError(f"{lifecycle!r} must stay silent: {quiet}")


def test_external_source_resolvable_diff_anchor_is_silent(root: Path) -> None:
    """POSITIVE: catalogue declared and its diff anchor resolves → silent."""
    main = _extsrc_fixture(root)
    findings = doctor.external_source_findings(
        {"C1": ("ongoing", _course_md(_EXTSRC_GOOD))}, main=main
    )
    if findings:
        raise AssertionError(f"a resolvable diff anchor must stay silent: {findings}")


def test_external_source_dangling_diff_anchor_fails(root: Path) -> None:
    """NEGATIVE: present-but-unresolvable → 002 FAIL（悬空声称比不声称更毒）.

    Three shapes: missing field, missing file, missing anchor text.
    """
    main = _extsrc_fixture(root)
    cases = {
        "缺字段": _EXTSRC_GOOD.replace(
            "  diff_recorded: 40_course/C1/lessons/lesson01/lesson01.md#官方目录核实\n",
            "",
        ),
        "文件不存在": _EXTSRC_GOOD.replace("lesson01.md#", "lesson99.md#"),
        "锚失效": _EXTSRC_GOOD.replace("#官方目录核实", "#从未写过的锚"),
    }
    for label, catalog in cases.items():
        findings = doctor.external_source_findings(
            {"C1": ("ongoing", _course_md(catalog))}, main=main
        )
        if [(code, severity) for code, severity, _ in findings] != [
            ("EXTSRC-002", "FAIL")
        ]:
            raise AssertionError(f"{label} must fail as 002: {findings}")


def test_external_source_none_needs_a_reason(root: Path) -> None:
    """`none（理由）` 静默；裸 `none` → 004 WARN；行内非 none → 002 FAIL.

    Without the `none` branch, textbook- and project-driven courses carry a 001
    that can never be legitimately cleared — permanent noise, which is how a
    channel gets trained into being ignored.
    """
    main = _extsrc_fixture(root)
    quiet = doctor.external_source_findings(
        {"C1": ("ongoing", _course_md("source_catalog: none（理由：教材驱动，权威目录是纸质书）\n"))},
        main=main,
    )
    if quiet:
        raise AssertionError(f"none with a reason must stay silent: {quiet}")
    for bare in ("source_catalog: none\n", "source_catalog: none（）\n"):
        findings = doctor.external_source_findings(
            {"C1": ("ongoing", _course_md(bare))}, main=main
        )
        if [(code, severity) for code, severity, _ in findings] != [
            ("EXTSRC-004", "WARN")
        ]:
            raise AssertionError(f"{bare!r} must warn as 004: {findings}")
    junk = doctor.external_source_findings(
        {"C1": ("ongoing", _course_md("source_catalog: 待办\n"))}, main=main
    )
    if [(code, severity) for code, severity, _ in junk] != [("EXTSRC-002", "FAIL")]:
        raise AssertionError(f"an inline value other than none must fail: {junk}")


def test_external_source_empty_input_is_silent(root: Path) -> None:
    """POSITIVE (净室): a distribution with no course instances says nothing."""
    reset(root)
    if doctor.external_source_findings({}, main=root / "main"):
        raise AssertionError("empty course set must produce no findings")
    run_silently(lambda: doctor.check_external_source_backlink({}))
    if doctor.fails or doctor.warns:
        raise AssertionError(
            f"cleanroom must stay silent: fails={doctor.fails} warns={doctor.warns}"
        )


def test_problemlog_closure_check_reads_instance_log(root: Path) -> None:
    """End-to-end: check_problemlog_closure consumes main/00_core and WARNs."""
    reset(root)
    write(
        root / "main/00_core/t2ag_problemlog.md",
        _PLOG_HEADER + "## P-0060 | [2026-08-10] | new\n\n- tags: [b]\n",
    )
    run_silently(doctor.check_problemlog_closure)
    assert_message(doctor.warns, "PLOG-CLOSURE-001")


def _real_playbook_snapshot() -> dict[str, str]:
    parent = doctor.ROOT.parent
    out: dict[str, str] = {}
    for edition in ("t2ag", "t2ag-skeleton", "t2ag-lite"):
        playbook = parent / edition / "main/50_playbook"
        if not playbook.is_dir():
            continue
        for path in playbook.glob("*.md"):
            out[f"{edition}:{path.name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _assert_real_playbooks_untouched(before: dict[str, str]) -> None:
    after = _real_playbook_snapshot()
    if after != before:
        raise AssertionError(f"real playbook trees mutated: {before} vs {after}")
    parent = doctor.ROOT.parent
    for edition in ("t2ag", "t2ag-skeleton"):
        repo = parent / edition
        if not (repo / ".git").exists():
            continue
        extra = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "--", "main/50_playbook"],
            cwd=repo,
            text=True,
        ).strip()
        leftover = [
            line for line in extra.splitlines()
            if line and not line.endswith((
                "gate_index.md",
                "okf_adaptation.md",
                "process_governance.md",
                "rule_admission_gate.md",
            ))
        ]
        if leftover:
            raise AssertionError(f"{edition} new untracked playbook files: {leftover}")


def _taxonomy_editions(root: Path) -> dict[str, Path]:
    """Minimal three-edition playbook dirs under a temp physical root."""
    reset(root)
    editions = {}
    body = "# X\n\n**保护级别**：meta-playbook\n\nbody\n"
    for name in ("t2ag", "t2ag-skeleton", "t2ag-lite"):
        playbook = root / name / "main/50_playbook"
        write(playbook / "playbook_management.md", body)
        write(playbook / "journal_management.md", "# J\n\n**保护级别**：meta-playbook\n")
        write(playbook / "handoff_management.md", "# H\n\n**保护级别**：core-playbook\n")
        write(playbook / "_README.md", "# index\n")
        editions[name] = playbook
    return editions


def test_playbook_taxonomy_r1_byte_drift_fails_parity(root: Path) -> None:
    """R1: one edition's meta file changes one byte → PB-TAXO-003 FAIL."""
    before = _real_playbook_snapshot()
    try:
        editions = _taxonomy_editions(root)
        target = editions["t2ag"] / "playbook_management.md"
        target.write_text(target.read_text(encoding="utf-8") + "x", encoding="utf-8")
        findings = doctor.playbook_taxonomy_parity_findings(editions)
        if not any(code == "PB-TAXO-003" and severity == "FAIL" for code, severity, _ in findings):
            raise AssertionError(f"byte drift must FAIL 003: {findings}")
        gate_index = REPO / "main/00_core/gate_index.md"
        old_gate_index = REPO / "main/50_playbook/gate_index.md"
        if not gate_index.is_file() or old_gate_index.exists():
            raise AssertionError("gate index must live only at main/00_core/gate_index.md")
        pointer_files = (
            REPO / "main/50_playbook/process_governance.md",
            REPO / "main/50_playbook/_README.md",
            REPO / "main/50_playbook/progress_governance.md",
        )
        for pointer_file in pointer_files:
            if "main/00_core/gate_index.md" not in pointer_file.read_text(encoding="utf-8"):
                raise AssertionError(f"stale gate-index consumer: {pointer_file}")
        if "main/50_playbook/gate_index.md" in doctor.DISTRIBUTION_PARITY_EXEMPT:
            raise AssertionError("distribution parity still exempts the retired gate-index path")
        if "main/50_playbook/gate_index.md" in doctor.CROSS_EDITION_FILE_EXEMPT:
            raise AssertionError("cross-edition parity still exempts the retired gate-index path")
    finally:
        _assert_real_playbooks_untouched(before)


def test_playbook_taxonomy_r2_illegal_value_fails(root: Path) -> None:
    """R2: `**保护级别**：normal playbook` → PB-TAXO-001 FAIL."""
    before = _real_playbook_snapshot()
    try:
        documents = {"sample.md": "# S\n\n**保护级别**：normal playbook\n"}
        findings = doctor.playbook_taxonomy_findings(documents)
        if [(code, severity) for code, severity, _ in findings] != [("PB-TAXO-001", "FAIL")]:
            raise AssertionError(f"illegal value must FAIL 001: {findings}")
    finally:
        _assert_real_playbooks_untouched(before)


def test_playbook_taxonomy_r3_fenced_marker_is_silent(root: Path) -> None:
    """R3: fenced marker is neither collected nor illegal."""
    before = _real_playbook_snapshot()
    try:
        documents = {
            "sample.md": (
                "# S\n\n**保护级别**：playbook\n\n"
                "```text\n**保护级别**：normal playbook\n```\n"
            ),
        }
        legal, illegal = doctor.parse_playbook_protection_levels(documents["sample.md"])
        if [value for _, value in legal] != ["playbook"] or illegal:
            raise AssertionError(f"fence leaked: legal={legal} illegal={illegal}")
        findings = doctor.playbook_taxonomy_findings(documents)
        if findings:
            raise AssertionError(f"fenced illegal must not fire: {findings}")
    finally:
        _assert_real_playbooks_untouched(before)


def test_playbook_taxonomy_r4_blockquote_prefix_counts(root: Path) -> None:
    """R4: `> **保护级别**：meta-playbook` joins the set."""
    before = _real_playbook_snapshot()
    try:
        documents = {"sample.md": "# S\n\n> **保护级别**：meta-playbook\n"}
        legal, illegal = doctor.parse_playbook_protection_levels(documents["sample.md"])
        if [value for _, value in legal] != ["meta-playbook"] or illegal:
            raise AssertionError(f"blockquote not accepted: legal={legal} illegal={illegal}")
    finally:
        _assert_real_playbooks_untouched(before)


def test_playbook_taxonomy_r5_missing_marker_warns_readme_exempt(root: Path) -> None:
    """R5: missing marker WARNs; `_README.md` is silent."""
    before = _real_playbook_snapshot()
    try:
        findings = doctor.playbook_taxonomy_findings({"sample.md": "# S\n\nno marker\n"})
        if [(code, severity) for code, severity, _ in findings] != [("PB-TAXO-002", "WARN")]:
            raise AssertionError(f"missing marker must WARN 002: {findings}")
        readme = doctor.playbook_taxonomy_findings({"_README.md": "# index\n"})
        if readme:
            raise AssertionError(f"_README.md must be exempt: {readme}")
    finally:
        _assert_real_playbooks_untouched(before)


def test_playbook_taxonomy_r6_conflicting_values_fail(root: Path) -> None:
    """R6: two different legal values in one file → PB-TAXO-005 FAIL."""
    before = _real_playbook_snapshot()
    try:
        documents = {
            "sample.md": (
                "# S\n\n**保护级别**：playbook\n\n"
                "> **保护级别**：core-playbook\n"
            ),
        }
        findings = doctor.playbook_taxonomy_findings(documents)
        if [(code, severity) for code, severity, _ in findings] != [("PB-TAXO-005", "FAIL")]:
            raise AssertionError(f"conflict must FAIL 005: {findings}")
    finally:
        _assert_real_playbooks_untouched(before)


def test_playbook_usage_r1_stale_reference_is_archive_candidate(root: Path) -> None:
    """USE-R1: >40 天引用 → PB-USE-002 WARN；同行日期与来源种子日期都要配对。"""
    import datetime as dt
    names = frozenset({"sample.md"})
    same_line = doctor.playbook_usage_last_seen(
        [("j", "2026-01-05 本会话用了 sample.md", None)], names
    )
    seeded = doctor.playbook_usage_last_seen(
        [("h", "提到 sample.md（无同行日期）", dt.date(2026, 1, 5))], names
    )
    if same_line != {"sample.md": dt.date(2026, 1, 5)} or seeded != same_line:
        raise AssertionError(f"日期配对失败: same_line={same_line} seeded={seeded}")
    findings = doctor.playbook_usage_findings(names, same_line, dt.date(2026, 8, 20))
    if not any(c == "PB-USE-002" and s == "WARN" for c, s, _ in findings):
        raise AssertionError(f"40 天线必须出归档候选: {findings}")


def test_playbook_usage_r2_mark_window_cursor_and_recent_silent(root: Path) -> None:
    """USE-R2: 游标日期作数；15–40 天 → PB-USE-001；14 天内静默。"""
    import datetime as dt
    names = frozenset({"cold.md", "warm.md"})
    text = "2026-08-01 会话甲\n参考了 cold.md\n2026-08-18 会话乙\n参考了 warm.md"
    last = doctor.playbook_usage_last_seen([("j", text, None)], names)
    findings = doctor.playbook_usage_findings(names, last, dt.date(2026, 8, 20))
    warns = [(c, m) for c, s, m in findings if s == "WARN"]
    if len(warns) != 1 or warns[0][0] != "PB-USE-001" or "cold.md" not in warns[0][1]:
        raise AssertionError(f"应当且仅当 cold.md 冷门标记: {findings}")
    if any("warm.md" in m for _, m in warns):
        raise AssertionError(f"14 天内不得标记: {findings}")


def test_playbook_usage_r3_no_data_is_info_not_warn(root: Path) -> None:
    """USE-R3: 从无引用记录 → 仅 PB-USE-003 INFO 观测态，不判冷门。"""
    import datetime as dt
    names = frozenset({"ghost.md"})
    findings = doctor.playbook_usage_findings(names, {}, dt.date(2026, 8, 20))
    if [c for c, s, _ in findings if s == "WARN"]:
        raise AssertionError(f"无数据不得 WARN: {findings}")
    if not any(c == "PB-USE-003" and s == "INFO" for c, s, _ in findings):
        raise AssertionError(f"必须报观测态 INFO: {findings}")


def _live_main_tree() -> Path | None:
    """Repo root of the tree these tests actually live in, **or None if it has no
    student instance** (Skeleton / Lite / a fresh trial copy).

    Two traps this closes at once:

    1. `doctor.MAIN` is redirected to a temp fixture by ``reset()``. Any "the real
       file must exist" assertion written against it silently passes — a false green.
    2. Instance facts (a course, a student profile row, a group ledger) legitimately
       do **not** exist in the empty template. Asserting them there turns a correct
       distribution into a red — which is how a flavor-blind test teaches people to
       ignore the suite.

    So: resolve the live tree from ``__file__``, then answer "does this distribution
    carry instances at all?" by flavor, not by whether one file happens to be missing.
    """
    live_main = Path(__file__).resolve().parents[1]
    root = live_main.parent
    if root.name in {"t2ag-lite", "t2ag-skeleton"}:
        return None
    profile = live_main / "10_student/profile/profile.md"
    text = profile.read_text(encoding="utf-8-sig", errors="replace") if profile.is_file() else ""
    if not re.search(r"^initialization_status:\s*initialized\s*$", text, re.MULTILINE):
        return None  # 未初始化实例（空模板/新试用者）：实例事实不适用
    return live_main


_EXAM_LEDGER_OK = """---
type: exam_ledger
course_id: C01
schema_version: exam_ledger.v1
truth_scope: exam_settlement
updated: 2026-08-22T00:00:00Z
---
> 【模式】复利回路·衰减（00_core/pattern_retire_loop.md）实例
> 【参数】域=课程级考核债｜时机=事前存证｜归因层=流程层｜消费方=结算闸｜退出=settled/archived｜再入=重修立项

# C01 考核台账

next_id: 1

| 参数 | 值 |
|---|---|
| 考核债状态 | `open` |
"""

_EXAM_INDEX_HEAD = """---
type: exam_index
course_id: C01
schema_version: exam_index.v1
truth_scope: exam_pool_state
updated: 2026-08-22T00:00:00Z
---
# C01 题库卷级登记表

| 卷ID | 校 | 年 | 课程层级 | 总时长 | 题数 | 单题基准时长 | 解答 | 池别 | 状态 |
|---|---|---|---|---|---|---|---|---|---|
"""


def _exam_fixture(
    root: Path,
    *,
    ledger: str = _EXAM_LEDGER_OK,
    pool: str = "考核",
    teaching: str | None = None,
) -> dict[str, tuple[Path, dict[str, str]]]:
    """Build one course with an `_exam/` root; return the `courses` mapping."""
    course = root / "main/40_course/C01"
    write(course / "_exam/exam_ledger.md", ledger)
    write(
        course / "_exam/index.md",
        _EXAM_INDEX_HEAD
        + f"| P001 | 校 | 2026 | 本科 | 120 | 10 | 12 | 有 | {pool} | 在库 |\n",
    )
    write(
        course / "_exam/papers/P001/meta.md",
        "| " + " | ".join(EXAM_META_COLUMNS_FIXTURE) + " |\n",
    )
    if teaching is not None:
        write(course / "lessons/lesson01/lesson01.md", teaching)
    reset(root)
    return {"C01": (course, {})}


EXAM_META_COLUMNS_FIXTURE = (
    doctor.marker_spellings("题号")[0],
    "类型", "知识节点", "难度档", "已用于教学", "已考", "解答页码", "考前检查备注",
)


def _container_fixture(
    root: Path,
    *,
    plan_mode: str = "progress",
    calendar: str | None = "keystone_dwell_budget_cycles: 3\n",
    status: str = "planned",
) -> tuple[str, Path, dict[str, str]]:
    """One group folder; returns the (group_id, folder, meta) triple."""
    folder = root / "main/30_group/G01"
    plan = (
        "---\ntype: group\ngroup_id: G01\n"
        f"status: {status}\ncourse_members: [C01]\n"
        + (f"container_mode: {plan_mode}\n" if plan_mode else "")
        + "keystone_total_frozen: 1\nupdated: 2026-08-22\n---\n\n"
        "## 4. 主干碑序列\n\n- K01 C01 节点甲\n\n## 5. 碑变更台账\n\n| |\n"
    )
    write(folder / "plan.md", plan)
    if calendar is not None:
        write(
            folder / "calendar.md",
            "---\ntype: group_calendar\ngroup_id: G01\n"
            + (f"container_mode: {plan_mode}\n" if plan_mode else "")
            + calendar
            + "---\n",
        )
    reset(root)
    return "G01", folder, doctor.frontmatter(folder / "plan.md")


def _load_init_module(tag: str):
    """Load `t2ag_init.py` under a private name (same pattern as the other tests)."""
    spec_init = importlib.util.spec_from_file_location(tag, SCRIPT.with_name("t2ag_init.py"))
    module = importlib.util.module_from_spec(spec_init)
    assert spec_init and spec_init.loader
    spec_init.loader.exec_module(module)
    return module


def _preflight_fixture(
    root: Path,
    *,
    mode: str = "progress",
    calendar: str | None = "keystone_dwell_budget_cycles: TBD\n",
    keystones: str = "- K01 C01 节点甲（判据：progress.md 当前完成节点行）\n",
    ledger_rows: str = "",
    lifecycle: str = "ongoing",
) -> Path:
    """A planned group activation should accept, with one knob per criterion.

    The default is deliberately the *passing* shape: every assertion below breaks
    exactly one thing, so a blocker that fires for the wrong reason shows up as
    an extra code rather than hiding inside a fixture that was broken anyway.
    """
    write(root / "main/t2ag.md", FIXTURE_CONSTITUTION)
    write(
        root / "main/40_course/C01/progress.md",
        f"---\ntype: course_progress\ncourse_id: C01\nlifecycle_status: {lifecycle}\n---\n",
    )
    write(
        root / "main/30_group/G01/plan.md",
        "---\ntype: group\ngroup_id: G01\nstatus: planned\n"
        "course_members: [C01]\nengagement_members: []\ncurrent_course: none\n"
        f"container_mode: {mode}\nupdated: 2026-08-01\n---\n\n"
        "## 4. 主干碑序列\n\n" + keystones + "\n## 5. 碑变更台账\n\n"
        "| 日期 | 碑号 | 类型（砍/加） | 触发来源 | 去向组或说明 |\n"
        "|---|---|---|---|---|\n" + ledger_rows,
    )
    if calendar is not None:
        write(
            root / "main/30_group/G01/calendar.md",
            "---\ntype: group_calendar\ngroup_id: G01\nstatus: planned\n"
            f"container_mode: {mode}\n" + calendar + "updated: 2026-08-01\n---\n",
        )
    return root


def test_container_mode_r1_missing_illegal_and_split_brain_fail(root: Path) -> None:
    """CM-R1：容器形状三条 FAIL——缺失、非法、plan↔calendar 不一致。

    `course_group_rules.md` §4.1：两种容器合法，**没有容器不合法**。缺 `container_mode`
    的组既不限时也不限范围，那不是模式是没有容器；两处声明不一致则「用哪组字段」无法
    判定，触发锚失去意义。三条都是 FAIL 而非 WARN，因为它们让后续所有容器判定失去前提。
    """
    gid, folder, meta = _container_fixture(root / "missing", plan_mode="")
    doctor.check_container_mode(gid, folder, meta, [], {})
    # 缺字段由 check_groups 主体判定；此处只确认 check_container_mode 不吞掉空模式
    if any("keystone_dwell_budget_cycles" in m for m in doctor.fails):
        raise AssertionError(f"无 container_mode 时不应判 progress 专属锚: {doctor.fails}")

    gid, folder, meta = _container_fixture(root / "illegal", plan_mode="hybrid")
    doctor.check_container_mode(gid, folder, meta, [], {})
    if doctor.fails:
        raise AssertionError(f"非法模式不归本函数判（归 check_groups）: {doctor.fails}")

    # --- PG3：激活 preflight 的判据正典清单与「一次报全」（2026-08-25）-------------
    init_mod = _load_init_module("t2ag_init_preflight_r1")
    # 结构断言，不是总数断言：写成 `16 + 1 == 17` 时，一条 blocker 被静默降级成
    # notice 照样让 17 成立——正好放过本节最该拦的那种改动。
    shape = (
        len(init_mod.GROUP_ACTIVATION_BLOCKER_CRITERIA),
        len(init_mod.GROUP_ACTIVATION_NOTICE_CRITERIA),
    )
    if shape != (16, 1):
        raise AssertionError(f"激活判据清单形状变了（应 16 阻断 + 1 提示）：{shape}")
    catalog = set(init_mod.GROUP_ACTIVATION_BLOCKER_CRITERIA)
    if len(catalog) != 16:
        raise AssertionError("判据代号有重号：合并判据即放宽，逐 raise 点一条")

    # 一次报全：三处同时坏，一次拒绝里必须三条都在。
    broken = _preflight_fixture(
        root / "manybad", calendar=None, keystones="", lifecycle="planned"
    )
    blockers, notices, _ = init_mod.group_activation_preflight(broken, "G01", "")
    codes = [code for code, _ in blockers]
    for expected in ("member_lifecycle_ineligible", "keystone_rows_absent", "dwell_budget_missing"):
        if expected not in codes:
            raise AssertionError(f"一次报全缺 {expected}：{codes}")
    stray = [code for code in codes if code not in catalog]
    if stray or notices:
        raise AssertionError(f"报出了清单外的代号或多余提示：{stray}/{notices}")

    # `--date` 由调用方求值，但必须并进**同一次**拒绝，否则「一次报全」只是函数内部的性质。
    with contextlib.redirect_stdout(io.StringIO()) as captured:
        rc = init_mod.main(
            ["--root", str(broken), "activate-group", "--group-id", "G01", "--date", "8/22"]
        )
    printed = captured.getvalue()
    if rc == 0:
        raise AssertionError("坏日期 + 三条不合格判据竟然激活成功了")
    for expected in ("date_format", "dwell_budget_missing", "keystone_rows_absent"):
        if expected not in printed:
            raise AssertionError(f"拒绝文案没有一次报全 {expected}：{printed}")

    # 写序倒置的可观测后果：被拒绝的组不留下「自称 active」的 plan.md。
    plan_text = (broken / "main/30_group/G01/plan.md").read_text(encoding="utf-8")
    if "status: active" in plan_text:
        raise AssertionError("激活被拒绝后 plan.md 仍自称 active")


def test_container_mode_r2_progress_needs_dwell_budget_but_tbd_is_legal(
    root: Path,
) -> None:
    """CM-R2：progress 缺止损锚 → FAIL；但字面 `TBD` 必须放行。

    后半条是本组夹具里**最该钉死的语义**。`course_group_rules.md`「容器参数由建组仪式
    产生」裁定这三个参数模板留字面 `TBD`、由仪式议定；判据取「空即 FAIL」正是为了让
    `TBD` 这个**可见欠账**能合法存在。哪天有人把判据收紧成「必须是整数」，新建的每个
    progress 组都会在议定前恒 FAIL——那不是修 bug 是改判，本条会先红。
    """
    gid, folder, meta = _container_fixture(root / "nobudget", calendar="")
    doctor.check_container_mode(gid, folder, meta, [], {})
    if not any("缺止损锚 keystone_dwell_budget_cycles" in m for m in doctor.fails):
        raise AssertionError(f"progress 缺预算必须 FAIL: {doctor.fails}")

    gid, folder, meta = _container_fixture(
        root / "tbd", calendar="keystone_dwell_budget_cycles: TBD\n"
    )
    doctor.check_container_mode(gid, folder, meta, [], {})
    if doctor.fails:
        raise AssertionError(f"`TBD` 是合法占位，不得 FAIL: {doctor.fails}")

    gid, folder, meta = _container_fixture(root / "nocal", calendar=None)
    doctor.check_container_mode(gid, folder, meta, [], {})
    if not any("缺止损锚" in m for m in doctor.fails):
        raise AssertionError(f"无 calendar.md 等同缺锚: {doctor.fails}")

    # --- PG3：同一条判据前移到激活时点，语义必须逐字相同（2026-08-25）--------------
    # 前移的价值全在「同源」两个字上：加严会拦下 doctor 本会放行的组，放宽只是把同一个
    # FAIL 推迟到下一次 doctor。所以这里复用 CM-R2 的三个形态，只换求值者。
    init_mod = _load_init_module("t2ag_init_preflight_r2")

    passing = _preflight_fixture(root / "pf_tbd")
    blockers, notices, resolved = init_mod.group_activation_preflight(passing, "G01", "")
    if blockers or notices:
        raise AssertionError(f"字面 TBD 必须放行（与 doctor 同源）：{blockers}/{notices}")
    # 单次求值：apply 吃的是 preflight 读到的那一份，不回盘取第二次。
    if resolved["current_course"] != "C01" or len(resolved["keystones"]) != 1:
        raise AssertionError(f"resolved 不足以直接喂给 apply：{resolved}")

    empty = _preflight_fixture(root / "pf_empty", calendar="keystone_dwell_budget_cycles:\n")
    blockers, _, _ = init_mod.group_activation_preflight(empty, "G01", "")
    if [code for code, _ in blockers] != ["dwell_budget_missing"]:
        raise AssertionError(f"空止损锚必须且只须阻断一条：{blockers}")

    nocal_pf = _preflight_fixture(root / "pf_nocal", calendar=None)
    blockers, _, _ = init_mod.group_activation_preflight(nocal_pf, "G01", "")
    if [code for code, _ in blockers] != ["dwell_budget_missing"]:
        raise AssertionError(f"无 calendar.md 等同缺锚：{blockers}")

    # 判据 16（本批前移的第二条）：planned 组带砍碑行 = 今天激活成功、下次 doctor 必 FAIL。
    cut = _preflight_fixture(
        root / "pf_cut", ledger_rows="| 2026-08-01 | K02 | 砍 | 复盘 | 移入下一组 |\n"
    )
    blockers, _, _ = init_mod.group_activation_preflight(cut, "G01", "")
    if [code for code, _ in blockers] != ["keystone_ledger_mismatch"]:
        raise AssertionError(f"planned 阶段砍碑行必须在激活前拦下：{blockers}")


def test_container_mode_r3_schedule_is_not_judged_by_progress_anchors(
    root: Path,
) -> None:
    """CM-R3：schedule 组不查 dwell budget；缺 `cycle_anchor_learning_day` 判 WARN 不判 FAIL。

    两种容器各有各的止损锚，拿 progress 的锚去量 schedule 是把两条轴混成一条。
    WARN 而非 FAIL 的理由同 §4.1：`TBD` 是合法值、缺字段才是问题，而缺字段只影响
    触发锚判定，不影响当天教学。
    """
    gid, folder, meta = _container_fixture(
        root / "sched", plan_mode="schedule", calendar="cycle_anchor_learning_day: TBD\n"
    )
    doctor.check_container_mode(gid, folder, meta, [], {})
    if doctor.fails or doctor.warns:
        raise AssertionError(f"schedule 且锚字段在位应静默: {doctor.fails}/{doctor.warns}")

    gid, folder, meta = _container_fixture(
        root / "sched_bare", plan_mode="schedule", calendar=""
    )
    doctor.check_container_mode(gid, folder, meta, [], {})
    if doctor.fails:
        raise AssertionError(f"schedule 缺锚字段是 WARN 不是 FAIL: {doctor.fails}")
    if not any("cycle_anchor_learning_day" in m for m in doctor.warns):
        raise AssertionError(f"schedule 缺锚字段必须 WARN: {doctor.warns}")

    # --- PG3：WARN 前移后必须仍是 WARN 语义（2026-08-25）---------------------------
    # 通用映射规则 FAIL→blocker、WARN→notice。把这条 WARN 前移成 blocker 就是加严，
    # 会让每个还没定锚的 schedule 组无法激活——而 doctor 从来只是提醒它。
    init_mod = _load_init_module("t2ag_init_preflight_r3")
    sched = _preflight_fixture(
        root / "pf_sched", mode="schedule", calendar="cycle_length_learning_days: TBD\n",
        keystones="",
    )
    blockers, notices, _ = init_mod.group_activation_preflight(sched, "G01", "")
    if blockers:
        raise AssertionError(f"schedule 缺 cycle_anchor 不得阻断激活：{blockers}")
    if [code for code, _ in notices] != ["cycle_anchor_missing"]:
        raise AssertionError(f"schedule 缺 cycle_anchor 必须出提示：{notices}")

    # 拿 progress 的止损锚去量 schedule，同样是把两条轴混成一条。
    anchored = _preflight_fixture(
        root / "pf_sched_ok", mode="schedule", calendar="cycle_anchor_learning_day: TBD\n",
        keystones="",
    )
    blockers, notices, _ = init_mod.group_activation_preflight(anchored, "G01", "")
    if blockers or notices:
        raise AssertionError(f"schedule 且锚字段在位应静默：{blockers}/{notices}")


def test_exam_banks_r1_assessment_pool_id_leak_into_teaching_fails(root: Path) -> None:
    """EX-R1：考核池题号出现在教学正文 → FAIL。**本条不可等**。

    池隔离是考试规则里唯一事后无法修复的一条——`check_exam_banks` 自己的 docstring
    写着「引用进教学就烧卷，事后改不回来」。而活树上这条 FAIL **结构上不可能响**：
    库空短路 PASS（EX-4「骨架优先，库留空」是已裁初始态），于是一个守着不可逆伤害的
    FAIL 级门，至今没有任何证据证明它能开火。没有 NEGATIVE 夹具，它与「不能触发的
    检验」无法区分（`doctor_contracts.md` §八.2）——正是 P-0077 那一族。
    """
    courses = _exam_fixture(root / "leak", teaching="见 P001 # 3 的解法。\n")
    doctor.check_exam_banks(courses)
    if not any("考核池题号引用泄漏进教学文件" in message for message in doctor.fails):
        raise AssertionError(f"考核池题号泄漏必须 FAIL: {doctor.fails} / {doctor.warns}")

    # 围栏内的同一串不算泄漏——引用泄漏判据必须跟着 without_fenced_code 的语义走，
    # 否则协议文档里举例都会被判泄漏。
    courses = _exam_fixture(
        root / "fenced", teaching="```\n见 P001 # 3\n```\n"
    )
    doctor.check_exam_banks(courses)
    if any("泄漏" in message for message in doctor.fails):
        raise AssertionError(f"围栏内示例不得判泄漏: {doctor.fails}")

    # 非考核池（复习池）同一串不触发——隔离制只护考核池。
    courses = _exam_fixture(
        root / "review", pool="复习", teaching="见 P001 # 3 的解法。\n"
    )
    doctor.check_exam_banks(courses)
    if any("泄漏" in message for message in doctor.fails):
        raise AssertionError(f"复习池不归隔离制管: {doctor.fails}")

    # 干净的考核池课程必须静默，否则每门课开机就红。
    courses = _exam_fixture(root / "clean", teaching="本节讲极限的定义。\n")
    doctor.check_exam_banks(courses)
    if doctor.fails:
        raise AssertionError(f"无泄漏时不得 FAIL: {doctor.fails}")


def test_exam_banks_r2_ledger_meta_defects_fail(root: Path) -> None:
    """EX-R2：台账元数据两条负例——`truth_scope` 错、复利回路衰减缺键。

    这两条是 FAIL 而非 WARN，因为它们决定 exam_ledger 是不是「考核结算唯一真相源」：
    truth_scope 错则它不是那个真相源，衰减参数缺则退出/再入无判据。
    """
    wrong_scope = _EXAM_LEDGER_OK.replace(
        "truth_scope: exam_settlement", "truth_scope: exam_pool_state"
    )
    courses = _exam_fixture(root / "scope", ledger=wrong_scope)
    doctor.check_exam_banks(courses)
    if not any("truth_scope 必须为 exam_settlement" in m for m in doctor.fails):
        raise AssertionError(f"truth_scope 错必须 FAIL: {doctor.fails}")

    missing_key = _EXAM_LEDGER_OK.replace("｜再入=重修立项", "")
    courses = _exam_fixture(root / "decay", ledger=missing_key)
    doctor.check_exam_banks(courses)
    if not any("复利回路参数缺键" in m for m in doctor.fails):
        raise AssertionError(f"衰减缺键必须 FAIL: {doctor.fails}")

    no_marker = _EXAM_LEDGER_OK.replace("> 【模式】复利回路·衰减（00_core/pattern_retire_loop.md）实例", "")
    courses = _exam_fixture(root / "marker", ledger=no_marker)
    doctor.check_exam_banks(courses)
    if not any("缺复利回路·衰减子型标记" in m for m in doctor.fails):
        raise AssertionError(f"缺子型标记必须 FAIL: {doctor.fails}")

    # 正例：完好的台账不得报任何 FAIL。
    courses = _exam_fixture(root / "ok")
    doctor.check_exam_banks(courses)
    if doctor.fails:
        raise AssertionError(f"完好台账不得 FAIL: {doctor.fails}")


def test_exam_banks_r3_empty_bank_short_circuits_and_absent_root_is_silent(
    root: Path,
) -> None:
    """EX-R3：空库短路 PASS、无 `_exam/` 完全静默——已裁初始态不得变成开机噪音。

    正向锚。写下来是因为它是**故意的**：EX-4 裁「骨架优先，库留空」，若哪天有人
    给空库加 WARN，本条会红，提醒那是改判不是修 bug。
    """
    course = root / "empty/main/40_course/C01"
    write(course / "_exam/exam_ledger.md", _EXAM_LEDGER_OK)
    write(course / "_exam/index.md", _EXAM_INDEX_HEAD)
    reset(root / "empty")
    doctor.check_exam_banks({"C01": (course, {})})
    if doctor.fails or doctor.warns:
        raise AssertionError(f"空库必须短路 PASS: {doctor.fails} / {doctor.warns}")

    bare = root / "bare/main/40_course/C02"
    bare.mkdir(parents=True, exist_ok=True)
    reset(root / "bare")
    doctor.check_exam_banks({"C02": (bare, {})})
    if doctor.fails or doctor.warns or doctor.infos:
        raise AssertionError(f"无 _exam/ 的课程必须完全静默: {doctor.fails}/{doctor.warns}")


def test_gate_visibility_r1_quiet_without_ledger_rows_warns(root: Path) -> None:
    """GV-R1: 声明 quiet 但门台账空 → 审计净损失，必须 WARN。

    这是 W6 的**硬验收**：quiet 只把四拍从对话移到台账，证据一字不少。台账空的 quiet
    等于变相放宽授权——三门底线，不是体验参数。砍掉这条，开关就成了后门。
    """
    empty = doctor.gate_visibility_findings(
        {"AIF1001r": ("quiet", ["## 门台账\n\n（还没写）\n"])}
    )
    if not any(c == "GV-002" and s == "WARN" for c, s, _ in empty):
        raise AssertionError(f"quiet 且台账空必须 WARN: {empty}")
    kept = doctor.gate_visibility_findings(
        {
            "AIF1001r": (
                "quiet",
                ["## 门台账\n\n| 行ID | 块ID |\n|---|---|\n| GT-0001 | S00 |\n"],
            )
        }
    )
    if any(c == "GV-002" for c, _, _ in kept):
        raise AssertionError(f"台账有 GT 行即应静默: {kept}")
    if not any(c == "GV-000" and s == "INFO" for c, s, _ in kept):
        raise AssertionError(f"实验中的课必须可观测: {kept}")


def test_gate_visibility_r2_default_is_explicit_and_needs_no_extra_evidence(
    root: Path,
) -> None:
    """GV-R2: 未声明＝explicit 默认，不额外举证；explicit 课台账空也不由本检查管。"""
    absent = doctor.gate_visibility_findings({})
    if absent:
        raise AssertionError(f"无声明课程时本检查静默: {absent}")
    explicit = doctor.gate_visibility_findings({"MATH1607H": ("explicit", [""])})
    if explicit:
        raise AssertionError(f"explicit 课不归本检查管（另有 gate_ledger）: {explicit}")


def test_gate_visibility_r3_per_domain_syntax_is_rejected_not_swallowed(
    root: Path,
) -> None:
    """GV-R3: per-domain 分档＝P-0073 N6，本轮未授权，必须判非法而非静默接受。

    未实现的语法被悄悄吞掉，是「保证比宣称的窄」那一族（P-0067）。留扩展位的意思是
    留位置，不是留一个看起来能用的入口。
    """
    for illegal in ("quiet@ai_fluency", "QUIET", "backstage", ""):
        findings = doctor.gate_visibility_findings({"X": (illegal, [""])})
        if illegal == "":
            if findings:
                raise AssertionError(f"空值＝未声明，应静默: {findings}")
            continue
        if not any(c == "GV-001" and s == "WARN" for c, s, _ in findings):
            raise AssertionError(f"{illegal!r} 必须判非法: {findings}")


def test_gate_visibility_r4_live_aif_is_quiet_and_audit_intact(root: Path) -> None:
    """GV-R4: 真实 AIF1001r 在实验中，且其门台账实际有 GT 行（审计零损失现证）。"""
    live_main = _live_main_tree()
    if live_main is None:
        return  # 空模板无课程实例，本条不适用（flavor 感知，非「文件不在就跳过」）
    course_file = live_main / "40_course/AIF1001r/course.md"
    if not course_file.is_file():
        raise AssertionError("AIF1001r 必须在位")
    text = course_file.read_text(encoding="utf-8")
    if not re.search(r"^gate_visibility:\s*quiet\s*$", text, re.MULTILINE):
        raise AssertionError("W6 已施工：AIF1001r 应在 quiet 试跑中（改回 explicit 请同步本测试）")
    lessons = [
        path.read_text(encoding="utf-8")
        for path in sorted((live_main / "40_course/AIF1001r").glob("lessons/*/lesson*.md"))
    ]
    findings = doctor.gate_visibility_findings({"AIF1001r": ("quiet", lessons)})
    if [c for c, s, _ in findings if s == "WARN"]:
        raise AssertionError(f"真实 quiet 课不得有审计损失: {findings}")


def test_recommendation_r1_missing_required_fields_warn(root: Path) -> None:
    """REC-R1: revisit_when 缺失＝死条目；provenance 缺失＝无主堆积。两者必报。

    这两个字段不是形式主义：原提案的重启条件曾挂在一个从未建成的人工累加器上，条件
    永不可能触发；而模型建议无标记地累积，是这类系统的已知失败模式。
    """
    entries = doctor.recommendation_entries(
        "## R-0001 | 某建议\n\n- scope: group\n- target: G02\n- status: deferred\n"
    )
    findings = doctor.recommendation_findings(entries, ledger_present=True)
    missing = [m for c, s, m in findings if c == "REC-001" and s == "WARN"]
    if not missing:
        raise AssertionError(f"缺必填字段必须 WARN: {findings}")
    if "provenance" not in missing[0] or "revisit_when" not in missing[0]:
        raise AssertionError(f"两个字段都要点名: {missing}")


def test_recommendation_r2_illegal_status_scope_and_provenance(root: Path) -> None:
    """REC-R2: 状态/scope 四值三值合法集、provenance 必须 student|model 起头。"""
    block = (
        "## R-0001 | x\n\n- scope: universe\n- target: t\n- status: 在议\n"
        "- provenance: 某人转述\n- revisit_when: 下次\n"
    )
    findings = doctor.recommendation_findings(
        doctor.recommendation_entries(block), ledger_present=True
    )
    codes = {c for c, _, _ in findings}
    for expected in ("REC-002", "REC-005", "REC-006"):
        if expected not in codes:
            raise AssertionError(f"{expected} 未报: {findings}")
    if any(s == "FAIL" for _, s, _ in findings):
        raise AssertionError(f"建议台账是 WARN-only，语义归人: {findings}")


def test_recommendation_r3_adopted_without_landing_reference_warns(root: Path) -> None:
    """REC-R3: 声称 adopted 却指不出 plan/progress 改动＝纸面采纳。"""
    paper = (
        "## R-0002 | y\n\n- scope: course\n- target: t\n- status: adopted\n"
        "- provenance: student\n- revisit_when: n/a\n\n已经采纳了。\n"
    )
    findings = doctor.recommendation_findings(
        doctor.recommendation_entries(paper), ledger_present=True
    )
    if not any(c == "REC-003" for c, _, _ in findings):
        raise AssertionError(f"纸面采纳必须 WARN: {findings}")
    landed = paper.replace(
        "已经采纳了。", "已写入 `main/30_group/G02/plan.md` 成员表。"
    )
    findings2 = doctor.recommendation_findings(
        doctor.recommendation_entries(landed), ledger_present=True
    )
    if any(c == "REC-003" for c, _, _ in findings2):
        raise AssertionError(f"有落地引用即应静默: {findings2}")


def test_recommendation_r4_absent_ledger_and_empty_ledger(root: Path) -> None:
    """REC-R4: 无台账＝未施工实例（Skeleton/新试用者），静默；有台账无条目＝观测态。"""
    absent = doctor.recommendation_findings([], ledger_present=False)
    if absent:
        raise AssertionError(f"无台账不得有任何 finding: {absent}")
    empty = doctor.recommendation_findings([], ledger_present=True)
    if [c for c, s, _ in empty if s == "WARN"]:
        raise AssertionError(f"空台账不得 WARN: {empty}")
    if not any(c == "REC-000" and s == "INFO" for c, s, _ in empty):
        raise AssertionError(f"空台账必须报观测态: {empty}")


def test_recommendation_r5_live_ledger_is_wellformed_and_keeps_ca_deferred(
    root: Path,
) -> None:
    """REC-R5: 真实台账零 WARN，且首条 C-A 必须仍是 deferred。

    后半条守的是「迁入是引用不是重裁」：C-A 的归宿 08-19 已裁「留结组」，本台账把它
    搬了个家，**不得顺手改判**。哪天有人在这里把它改成 adopted，这条会先红。
    """
    live_main = _live_main_tree()
    if live_main is None:
        return  # 空模板不持有建议台账（检查侧同样静默：无台账＝未施工实例）
    ledger = live_main / "30_group/recommendations.md"
    if not ledger.is_file():
        raise AssertionError("W5 已施工，台账必须在位")
    entries = doctor.recommendation_entries(ledger.read_text(encoding="utf-8"))
    findings = doctor.recommendation_findings(entries, ledger_present=True)
    warns = [(c, m) for c, s, m in findings if s == "WARN"]
    if warns:
        raise AssertionError(f"真实台账应零 WARN: {warns}")
    first = {entry_id: fields for entry_id, fields, _ in entries}.get("R-0001")
    if not first:
        raise AssertionError("首条 R-0001（C-A 迁入）缺失")
    if first.get("status") != "deferred":
        raise AssertionError(
            f"C-A 归宿 08-19 已裁『留结组』，本台账不得重裁：status={first.get('status')}"
        )
    if not first.get("provenance", "").startswith("model"):
        raise AssertionError("C-A 来自外部对话，provenance 必须标 model")


def test_domain_tier_r1_top_claim_without_evidence_warns(root: Path) -> None:
    """TIER-R1: 自评精熟但证据文件不提该领域 → TIER-001 虚高 WARN。

    这条是 P-0073 的病灶本身：学生 2026-08-08 自诊「档位误判无校验」，档位只升不降
    必然虚高。没有这条，N1 的表就只是自述。
    """
    rows = [("compute_governance", "精熟", "evidence/e3.md", "2026-08-21")]
    findings = doctor.domain_tier_findings(
        rows, {"evidence/e3.md": "本文件只记 ai_fluency 的辨别样本"}
    )
    if not any(c == "TIER-001" and s == "WARN" for c, s, _ in findings):
        raise AssertionError(f"顶档主张对不上实绩必须 WARN: {findings}")
    if any(s == "FAIL" for _, s, _ in findings):
        raise AssertionError(f"档位是学生自判，机器只呈证据差，永不 FAIL: {findings}")


def test_domain_tier_r2_dangling_or_missing_pointer_warns(root: Path) -> None:
    """TIER-R2: 证据指针不可解析或为空 → TIER-002；「远」档无主张故豁免。"""
    dangling = doctor.domain_tier_findings(
        [("ai_fluency", "半熟", "evidence/gone.md", "2026-08-21")],
        {"evidence/gone.md": None},
    )
    if not any(c == "TIER-002" and s == "WARN" for c, s, _ in dangling):
        raise AssertionError(f"悬空指针必须 WARN: {dangling}")
    empty = doctor.domain_tier_findings(
        [("ai_fluency", "半熟", "", "2026-08-21")], {}
    )
    if not any(c == "TIER-002" for c, _, _ in empty):
        raise AssertionError(f"空指针必须 WARN: {empty}")
    far = doctor.domain_tier_findings([("quantum", "远", "", "2026-08-21")], {})
    if far:
        raise AssertionError(f"「远」是默认档位，无主张即无需举证: {far}")


def test_domain_tier_r3_illegal_value_and_cold_start(root: Path) -> None:
    """TIER-R3: 非三值合法集 → TIER-003；无表 → TIER-000 INFO 冷启动，不判虚高。"""
    illegal = doctor.domain_tier_findings(
        [("x", "熟练", "e.md", "2026-08-21")], {"e.md": "x"}
    )
    if not any(c == "TIER-003" and s == "WARN" for c, s, _ in illegal):
        raise AssertionError(f"非法档位值必须 WARN: {illegal}")
    cold = doctor.domain_tier_findings([], {})
    if [c for c, s, _ in cold if s == "WARN"]:
        raise AssertionError(f"空表不得 WARN（冷启动护栏，同 PB-USE-000）: {cold}")
    if not any(c == "TIER-000" and s == "INFO" for c, s, _ in cold):
        raise AssertionError(f"空表必须报观测态 INFO: {cold}")


def test_domain_tier_r4_table_parse_is_header_driven(root: Path) -> None:
    """TIER-R4: 表头驱动解析，围栏块内的示例表不得被当成真实登记。

    GATE-LEDGER 曾因假定列序而产出幻影行（AIF1001r 假 000）；同一个坑不踩第二次。
    """
    profile = (
        "# 档案\n\n## 领域信任档位（domain→tier）\n\n"
        "| 领域 | 档位 | 证据指针 | 更新日 |\n|---|---|---|---|\n"
        "| ai_fluency | 半熟 | `evidence/e3.md` | 2026-08-21 |\n\n"
        "```\n| 领域 | 档位 | 证据指针 | 更新日 |\n"
        "| fake_domain | 精熟 | `nope.md` | 2026-01-01 |\n```\n\n"
        "## 下一节\n\n| 领域 | 档位 |\n|---|---|\n| after_section | 精熟 |\n"
    )
    rows = doctor.domain_tier_rows(profile)
    domains = [row[0] for row in rows]
    if domains != ["ai_fluency"]:
        raise AssertionError(f"只应解析出真实登记行，实得: {domains}")
    if rows[0][1] != "半熟" or rows[0][2] != "evidence/e3.md":
        raise AssertionError(f"列取值错位: {rows[0]}")
    if not doctor.domain_tier_rows("# 档案\n\n## 别的节\n\n无表\n") == []:
        raise AssertionError("无该节时必须返回空表，交给冷启动护栏判定")


def test_domain_tier_r5_live_profile_registers_and_resolves(root: Path) -> None:
    """TIER-R5: 真实 profile 的 N1 表必须存在、合法、且证据指针真能解析开。

    防的是「表写了但指针是想象的」——P-0069 那类按想象格式书写的同族毛病。
    """
    live_main = _live_main_tree()
    if live_main is None:
        return  # 空模板 profile 无档位表，走 TIER-000 冷启动护栏，非缺陷
    live_root = live_main.parent
    profile_path = live_main / "10_student/profile/profile.md"
    if not profile_path.is_file():
        raise AssertionError("W1 已施工，真实 profile 必须在位")
    rows = doctor.domain_tier_rows(profile_path.read_text(encoding="utf-8"))
    if not rows:
        raise AssertionError("N1 表已施工，真实 profile 必须解析出至少一行")
    for domain, tier, ref, _updated in rows:
        if tier not in doctor.TIER_LEGAL_VALUES:
            raise AssertionError(f"{domain} 档位非法: {tier}")
        if tier == "远":
            continue
        if not (live_root / ref).is_file():
            raise AssertionError(f"{domain} 证据指针不可解析: {ref}")



def _constitution_editions(root: Path) -> tuple[Path, Path]:
    """Two minimal editions whose constitution files start byte-identical."""
    reset(root)
    constitution = (
        "# T2AG\n\n宪法前言。\n\n"
        "## 1. 原则  [max 9]\n\nalpha\n\n"
        "## 6. 修改、迁移与发布闸门  [max 9]\n\nbeta\n"
    )
    for name in ("t2ag", "t2ag-skeleton"):
        write(root / name / "main/t2ag.md", constitution)
    return root / "t2ag", root / "t2ag-skeleton"


_CONSTITUTION_TEST_TARGETS = ("main/t2ag.md",)


def test_constitution_parity_r1_section_drift_fails(root: Path) -> None:
    """R1: one section's bytes change in one edition → CONST-PAR-001 FAIL."""
    main_root, skel_root = _constitution_editions(root)
    path = skel_root / "main/t2ag.md"
    write(path, path.read_text(encoding="utf-8").replace("alpha", "alpha-x"))
    findings = doctor.constitution_parity_findings(
        main_root, skel_root,
        targets=_CONSTITUTION_TEST_TARGETS, exempt={}, file_exempt={},
    )
    if [(code, severity) for code, severity, _ in findings] != [("CONST-PAR-001", "FAIL")]:
        raise AssertionError(f"section drift must FAIL 001 only: {findings}")
    if "1. 原则" not in findings[0][2] or "[max" in findings[0][2]:
        raise AssertionError(
            f"finding must name the section without its [max N] marker: {findings}"
        )


def test_constitution_parity_r2_stale_exemption_warns(root: Path) -> None:
    """R2: exempt section identical on both sides → CONST-PAR-003 WARN (stale)."""
    main_root, skel_root = _constitution_editions(root)
    findings = doctor.constitution_parity_findings(
        main_root, skel_root,
        targets=_CONSTITUTION_TEST_TARGETS,
        exempt={("main/t2ag.md", "6. 修改、迁移与发布闸门"): "test reason"},
        file_exempt={},
    )
    if [(code, severity) for code, severity, _ in findings] != [("CONST-PAR-003", "WARN")]:
        raise AssertionError(f"stale exemption must WARN 003: {findings}")


def test_constitution_parity_r3_section_set_fork_fails(root: Path) -> None:
    """R3: Skeleton loses a whole section → CONST-PAR-002 FAIL naming the side."""
    main_root, skel_root = _constitution_editions(root)
    path = skel_root / "main/t2ag.md"
    head, _sep, _tail = path.read_text(encoding="utf-8").partition("## 6. ")
    write(path, head)
    findings = doctor.constitution_parity_findings(
        main_root, skel_root,
        targets=_CONSTITUTION_TEST_TARGETS, exempt={}, file_exempt={},
    )
    if not any(
        code == "CONST-PAR-002" and severity == "FAIL" and "Skeleton 缺节" in message
        for code, severity, message in findings
    ):
        raise AssertionError(f"set fork must FAIL 002 naming the side: {findings}")


def _cross_edition_editions(root: Path) -> tuple[Path, Path]:
    """Two editions carrying the same mechanism in two numbering styles.

    The playbook bodies are deliberately written the way the real corpus is: the
    Chinese edition numbers its top sections `一、` and lets the child sit bare
    (`### 1.`), the English edition writes `1.` and fully qualifies the child
    (`### 1.1`).  A comparator that reads these as different structures would
    drown the gate in false forks, so the fixture asserts the normalisation
    rather than assuming it.
    """
    reset(root)
    workflow = json.dumps(
        {
            "doctor_checks": {"runtime.alpha": {"handler": "check_alpha"}},
            "profiles": {"runtime": {"checks": ["runtime.alpha"]}},
        },
        ensure_ascii=False,
    )
    bodies = {
        "t2ag": "# 手册\n\n## 一、总则\n\n甲\n\n### 1. 子条\n\n乙\n\n## 二、边界\n\n丙\n",
        "t2ag-skeleton-en": (
            "# Handbook\n\n## 1. General\n\na\n\n### 1.1 Sub-clause\n\nb\n\n"
            "## 2. Boundary\n\nc\n"
        ),
    }
    for name, body in bodies.items():
        write(
            root / name / "main/70_tools/t2ag_doctor.py",
            "def check_alpha() -> None:\n    pass\n",
        )
        write(
            root / name / "main/70_tools/t2ag_init.py",
            'sub.add_parser("alpha")\nparser.add_argument("--root")\n',
        )
        write(root / name / "main/70_tools/validation_workflow.json", workflow)
        write(root / name / "main/50_playbook/handbook.md", body)
    return root / "t2ag", root / "t2ag-skeleton-en"


def _cross_edition_findings(main_root: Path, edition_root: Path, **kwargs):
    kwargs.setdefault("exempt", {})
    kwargs.setdefault("file_exempt", {})
    kwargs.setdefault("section_roots", ("main/50_playbook",))
    kwargs.setdefault("section_files", ())
    return doctor.cross_edition_parity_findings(main_root, edition_root, **kwargs)


def test_cross_edition_parity_r1_numbering_styles_are_silent(root: Path) -> None:
    """R1: `一、`+bare child vs `1.`+qualified child is the same structure.

    This is the whole premise of the gate.  If it were false the check would be
    unusable and the honest move would be to delete it rather than to bury the
    noise under exemptions.
    """
    main_root, edition_root = _cross_edition_editions(root)
    findings = _cross_edition_findings(main_root, edition_root)
    if findings:
        raise AssertionError(f"equivalent editions must be silent: {findings}")


def test_cross_edition_parity_r2_identifier_fork_fails(root: Path) -> None:
    """R2: the edition loses a handler and a registered check → CE-PAR-001 FAIL."""
    main_root, edition_root = _cross_edition_editions(root)
    write(edition_root / "main/70_tools/t2ag_doctor.py", "def helper() -> None:\n    pass\n")
    write(
        edition_root / "main/70_tools/validation_workflow.json",
        json.dumps({"doctor_checks": {}, "profiles": {"runtime": {"checks": []}}}),
    )
    findings = _cross_edition_findings(main_root, edition_root)
    codes = [(code, severity) for code, severity, _ in findings]
    if codes != [("CE-PAR-001", "FAIL")] * 3:
        raise AssertionError(f"identifier fork must FAIL 001 three times: {findings}")
    if not any("check_alpha" in message for _c, _s, message in findings):
        raise AssertionError(f"finding must name the lost handler: {findings}")


def test_cross_edition_parity_r3_section_fork_fails(root: Path) -> None:
    """R3: a numbered subsection disappears from the edition → CE-PAR-002 FAIL."""
    main_root, edition_root = _cross_edition_editions(root)
    path = edition_root / "main/50_playbook/handbook.md"
    head, _sep, _tail = path.read_text(encoding="utf-8").partition("### 1.1")
    write(path, head + "## 2. Boundary\n\nc\n")
    findings = _cross_edition_findings(main_root, edition_root)
    if [(code, severity) for code, severity, _ in findings] != [("CE-PAR-002", "FAIL")]:
        raise AssertionError(f"section fork must FAIL 002 only: {findings}")
    if "§1.1" not in findings[0][2]:
        raise AssertionError(f"finding must name the section number: {findings}")


def test_cross_edition_parity_r4_debt_reports_info_then_goes_stale(root: Path) -> None:
    """R4: a registered gap is INFO debt; once refilled the same entry WARNs stale.

    The transition is the point of CE-2: the exemption table is a ledger that
    nags when it is paid off, not a place for a gap to retire quietly.
    """
    main_root, edition_root = _cross_edition_editions(root)
    write(edition_root / "main/70_tools/t2ag_doctor.py", "def helper() -> None:\n    pass\n")
    exempt = {("doctor_handler", "check_alpha"): "test debt; 回填条件=backport"}
    debt = _cross_edition_findings(main_root, edition_root, exempt=exempt)
    if not any(code == "CE-PAR-000" and severity == "INFO" for code, severity, _ in debt):
        raise AssertionError(f"registered gap must report INFO debt: {debt}")
    if any(severity == "FAIL" and "check_alpha" in message for _c, severity, message in debt):
        raise AssertionError(f"registered gap must not also FAIL: {debt}")
    write(
        edition_root / "main/70_tools/t2ag_doctor.py",
        "def check_alpha() -> None:\n    pass\n",
    )
    paid = _cross_edition_findings(main_root, edition_root, exempt=exempt)
    if [(code, severity) for code, severity, _ in paid] != [("CE-PAR-003", "WARN")]:
        raise AssertionError(f"refilled gap must WARN 003 stale: {paid}")


def test_cross_edition_parity_r5_unreadable_source_fails_loudly(root: Path) -> None:
    """R5: an unparsable comparison source FAILs 004 instead of shrinking coverage.

    A corrupt `validation_workflow.json` would otherwise yield an empty
    identifier set on one side, which reads as "the edition lost everything" or,
    worse, as silence.  Losing a comparator quietly is how the blind spot this
    check exists for was created in the first place.
    """
    main_root, edition_root = _cross_edition_editions(root)
    write(edition_root / "main/70_tools/validation_workflow.json", "{not json")
    findings = _cross_edition_findings(main_root, edition_root)
    if not any(
        code == "CE-PAR-004" and severity == "FAIL" and "不可解析" in message
        for code, severity, message in findings
    ):
        raise AssertionError(f"unreadable source must FAIL 004: {findings}")
    dangling = _cross_edition_findings(
        main_root, edition_root, exempt={("section", "main/50_playbook/gone.md#9"): "r"}
    )
    if not any(
        code == "CE-PAR-003" and severity == "WARN" and "悬空" in message
        for code, severity, message in dangling
    ):
        raise AssertionError(f"dangling exemption must WARN 003: {dangling}")


def test_cross_edition_parity_r6_peer_resolution_is_symmetric(root: Path) -> None:
    """R6: either side finds the other; a lone edition finds nobody and stays silent.

    The silence is the fluency contract: whoever holds one edition -- which is
    every trial user, always -- must never be shown this gate's findings, and the
    orientation must not flip when the run starts from the English side, or the
    exemption table would read backwards and every entry would dangle.
    """
    main_root, edition_root = _cross_edition_editions(root)
    if doctor.cross_edition_peer(main_root) != edition_root:
        raise AssertionError("Chinese side must resolve the English edition as peer")
    if doctor.cross_edition_peer(edition_root) != main_root:
        raise AssertionError("English side must resolve the Chinese edition as peer")
    lone = root / "t2ag-somebody-renamed-it"
    lone.mkdir(parents=True, exist_ok=True)
    if doctor.cross_edition_peer(lone) is not None:
        raise AssertionError("an unlisted directory must have no peer, hence no findings")
    for invoked_from in (main_root, edition_root):
        if doctor.cross_edition_orient(invoked_from, main_root if invoked_from is edition_root else edition_root) != (
            main_root, edition_root
        ):
            raise AssertionError(f"orientation must not depend on caller: {invoked_from}")
    write(edition_root / "main/70_tools/t2ag_doctor.py", "def helper() -> None:\n    pass\n")
    oriented = doctor.cross_edition_orient(edition_root, main_root)
    findings = _cross_edition_findings(*oriented)
    if not any(
        "英文面缺失" in message and "check_alpha" in message
        for _code, _severity, message in findings
    ):
        raise AssertionError(f"run from the English side must still name it 英文面缺失: {findings}")


def test_constitution_parity_r4_exempt_fork_and_clean_are_silent(root: Path) -> None:
    """R4: identical editions are silent; a forked exempt section stays silent."""
    main_root, skel_root = _constitution_editions(root)
    clean = doctor.constitution_parity_findings(
        main_root, skel_root,
        targets=_CONSTITUTION_TEST_TARGETS, exempt={}, file_exempt={},
    )
    if clean:
        raise AssertionError(f"identical editions must be silent: {clean}")
    path = skel_root / "main/t2ag.md"
    write(path, path.read_text(encoding="utf-8").replace("beta", "beta-fork"))
    forked = doctor.constitution_parity_findings(
        main_root, skel_root,
        targets=_CONSTITUTION_TEST_TARGETS,
        exempt={("main/t2ag.md", "6. 修改、迁移与发布闸门"): "H4-style lawful fork"},
        file_exempt={},
    )
    if forked:
        raise AssertionError(f"exempt fork must be silent: {forked}")




# ---------------------------------------------------------------------------
# DEC-0a-2 / C8 -- positive and negative examples for the four merges.
# Every negative below is written to be verified RED by mutation: reverting the
# merge constraint it guards must make it fail.
# ---------------------------------------------------------------------------


def test_line_budget_constitution_over_limit_fails(root: Path) -> None:
    """NEGATIVE: severity must stay per-carrier -- t2ag.md is FAIL, not WARN.

    Merging two checks into one handler is exactly where severity gets levelled
    by accident.  Why the two carriers keep different severities is canonical
    in 50_playbook/line_budget.md §二 and not restated here.
    """
    reset(root)
    write(root / "main/00_core/t2ag_memory.md",
          _memory_budget_fixture("## 最近关键决策  [max 50]\n- entry\n"))
    _seed_constitution_budget(root, cap=3, lines=10)
    run_silently(doctor.check_line_budget)
    assert_message(doctor.fails, "宪法节超预算")
    if any("宪法节超预算" in w for w in doctor.warns):
        raise AssertionError("constitution overflow was levelled down to WARN")


def test_line_budget_severity_is_not_levelled_across_carriers(root: Path) -> None:
    """NEGATIVE: both carriers over budget in one run -> one WARN and one FAIL."""
    reset(root)
    write(root / "main/00_core/t2ag_memory.md",
          _memory_budget_fixture("## 最近关键决策  [max 2]\n- a\n- b\n- c\n- d\n"))
    _seed_constitution_budget(root, cap=2, lines=9)
    run_silently(doctor.check_line_budget)
    assert_message(doctor.warns, "memory 节超预算")
    assert_message(doctor.fails, "宪法节超预算")


def test_line_budget_missing_constitution_fails_but_memory_absence_is_silent(
    root: Path,
) -> None:
    """The two carriers keep their pre-merge presence semantics.

    check_constitution_budget FAILed on a missing t2ag.md; check_memory_budget
    returned silently on a missing memory index.  The merge must not homogenise
    that -- doing so would either invent a FAIL or swallow a real one.
    """
    reset(root)
    run_silently(doctor.check_line_budget)
    assert_message(doctor.fails, "main/t2ag.md 缺失")
    if any("t2ag_memory" in message for message in doctor.fails):
        raise AssertionError("absent memory index must not FAIL")


def _seed_line_ending_repo(root: Path, *, git: bool = True,
                           gitattributes: bool = True) -> None:
    write_validation_foundation_fixture(root)
    if gitattributes:
        write(root / ".gitattributes", "* text=auto eol=lf\n")
    if git:
        subprocess.run(["git", "init", "--quiet", str(root)],
                       check=True, capture_output=True)


def _write_crlf(path: Path, body: str = "line one\r\nline two\r\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode("utf-8"))


def test_line_endings_runtime_profile_does_not_enumerate_tracked(root: Path) -> None:
    """POSITIVE (正-1): runtime runs policy + bounded scan, and stops there."""
    reset(root)
    _seed_line_ending_repo(root)
    run_silently(doctor.check_line_endings)
    if any("tracked 文本文件行尾一致" in message for message in doctor.infos):
        raise AssertionError("runtime profile must not run the tracked sweep")


def test_line_endings_release_profile_runs_tracked_sweep(root: Path) -> None:
    """POSITIVE (正-2): release adds the tracked sweep and its INFO counter."""
    reset(root)
    _seed_line_ending_repo(root)
    run_silently(lambda: doctor.check_line_endings(check_release_parity=True))
    assert_message(doctor.infos, "tracked 文本文件行尾一致")


def test_line_endings_release_path_is_reached_through_the_executor(
    root: Path,
) -> None:
    """NEGATIVE (负-1): leaving the handler zero-argument loses the sweep.

    Before the merge both line-ending handlers sat in ``no_argument_handlers``,
    so neither could see the profile.  If the merged handler is put back there,
    the release path silently degrades to the bounded scan and this INFO line
    disappears -- which is precisely the damage that is invisible in a green run.
    """
    reset(root)
    _seed_line_ending_repo(root)
    run_silently(
        lambda: doctor.execute_doctor_checks(
            [{"handler": "check_line_endings"}], include_release_parity=False
        )
    )
    if any("tracked 文本文件行尾一致" in message for message in doctor.infos):
        raise AssertionError("runtime dispatch must not run the tracked sweep")
    doctor.infos.clear()
    run_silently(
        lambda: doctor.execute_doctor_checks(
            [{"handler": "check_line_endings"}], include_release_parity=True
        )
    )
    assert_message(doctor.infos, "tracked 文本文件行尾一致")


def test_line_endings_release_keeps_the_gitattributes_policy_segment(
    root: Path,
) -> None:
    """NEGATIVE (负-2): dropping segment (1) lowers severity on the release path."""
    reset(root)
    _seed_line_ending_repo(root, gitattributes=False)
    run_silently(lambda: doctor.check_line_endings(check_release_parity=True))
    assert_message(doctor.fails, "缺少 .gitattributes")


def test_line_endings_release_still_covers_untracked_control_files(
    root: Path,
) -> None:
    """NEGATIVE (负-3): segment (3) is NOT a superset of segment (2).

    The bounded scan enumerates the filesystem, the exhaustive sweep enumerates
    ``git ls-files``.  A control file that is not tracked yet therefore exists
    for (2) and does not exist for (3).  Running only (3) on the release path
    loses line-ending verification for exactly the files most likely to be new.

    The untracked file is created inside a throw-away git repository under the
    test root -- never in the product tree (precedent: test_activity_cli_disk_roundtrip).
    """
    reset(root)
    _seed_line_ending_repo(root)
    offender = root / "main/00_core/untracked_control.md"
    _write_crlf(offender)
    proc = subprocess.run(["git", "ls-files", "-z"], cwd=root, text=True,
                          capture_output=True, encoding="utf-8", errors="replace")
    tracked = [name for name in proc.stdout.split("\0") if name]
    if "main/00_core/untracked_control.md" in tracked:
        raise AssertionError("fixture invalid: the offender must stay untracked")
    tracked_only = doctor.crlf_offenders([root / name for name in tracked])
    if any("untracked_control" in hit for hit in tracked_only):
        raise AssertionError("fixture invalid: tracked sweep should not see it")
    run_silently(lambda: doctor.check_line_endings(check_release_parity=True))
    assert_message(doctor.fails, "untracked_control.md")


def test_line_endings_outside_git_still_runs_policy_and_bounded_scan(
    root: Path,
) -> None:
    """NEGATIVE (负-4): only segment (3) may degrade outside a repository.

    The pre-merge check_release_line_endings returned wholesale when ``.git``
    was absent.  Carrying that early return into the merged handler would take
    the policy check and the bounded scan down with it -- a CRLF file would go
    unreported on the release path purely because the tree is not a repository.
    """
    reset(root)
    _seed_line_ending_repo(root, git=False)
    _write_crlf(root / "main/00_core/control.md")
    run_silently(lambda: doctor.check_line_endings(check_release_parity=True))
    assert_message(doctor.fails, "control.md")
    assert_message(doctor.warns, "非 Git 仓库")


def test_stale_identifiers_keeps_both_counter_lines_separate(root: Path) -> None:
    """NEGATIVE (组三): the two INFO counters must not be summed into one.

    Both counter lines are output-surface literals that corroborating assertions
    grep for.  Merging them into a single total silently breaks every one of
    those assertions while the run stays green.
    """
    reset(root)
    write_validation_foundation_fixture(root)
    run_silently(doctor.check_stale_identifiers)
    assert_message(doctor.infos, "legacy_path_hits_total:")
    assert_message(doctor.infos, "retired_instance_id_hits_total:")


def test_stale_identifiers_retired_ids_can_still_fail(root: Path) -> None:
    """NEGATIVE (组三): severity must not drop -- the retired-ID segment still FAILs."""
    reset(root)
    write_validation_foundation_fixture(root)
    write(root / "main/50_playbook/sample.md", "见 S002 的处理\n")
    run_silently(doctor.check_stale_identifiers)
    assert_message(doctor.fails, "active 退役实例 ID")


class _RecordingDecisionContract:
    """Stub for decision_record_contract that records segment call order."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def validate_decision_records_as_report(self, root, flavor):
        self.calls.append("linkage")
        return []

    def validate_decision_citations(self, root, flavor):
        self.calls.append("citations")
        return []


def _run_decision_records_with_stub(root: Path, flavor: str):
    stub = _RecordingDecisionContract()
    previous = sys.modules.get("decision_record_contract")
    sys.modules["decision_record_contract"] = stub
    try:
        reset(root, flavor=flavor)
        run_silently(doctor.check_decision_records)
    finally:
        if previous is None:
            sys.modules.pop("decision_record_contract", None)
        else:
            sys.modules["decision_record_contract"] = previous
    return stub.calls


def test_decision_records_runs_linkage_before_citations(root: Path) -> None:
    """NEGATIVE (组四): ordering lost its registry carrier and now lives in code.

    Before the merge the order was guaranteed by the registry edge
    ``runtime.decision_record_citations depends_on runtime.decision_records``.
    The merge deleted that edge, so nothing but this assertion stands between a
    future edit and citations running against unvalidated linkage.
    """
    calls = _run_decision_records_with_stub(root, "main")
    if calls != ["linkage", "citations"]:
        raise AssertionError(f"linkage must run first: {calls}")


def test_decision_records_lite_skips_citations_only(root: Path) -> None:
    """NEGATIVE (组四): Lite narrows to the citation segment, it does not skip both."""
    calls = _run_decision_records_with_stub(root, "lite")
    if calls != ["linkage"]:
        raise AssertionError(f"Lite must still run linkage: {calls}")


ALL_CONTRACT_TESTS = (
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
        test_textbook_preparation_activity_matrix,
        test_skin_art,
        test_course_activity_templates,
        test_flow_and_offline_guide,
        test_offline_guide_version_drift_is_enforced,
        test_skeleton_package_surface_is_enforced,
        test_release_package_surface_severity_split,
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
        test_profile_migration_roundtrip,
        test_handoff_assertion_without_source_is_reported,
        test_handoff_assertion_with_source_is_accepted,
        test_handoff_assertion_scan_skips_structure_only,
        test_handoff_required_context_layers_are_enforced,
        test_handoff_active_lane_absence_contradiction_is_enforced,
        test_handoff_index_version_drift_is_enforced,
        test_handoff_shadow_runtime_index_is_enforced,
        test_resume_authorization_gate_is_enforced,
        test_authorization_gate_evidence_surface_reachability,
        test_environment_probes_report_broken_assumptions,
        test_environment_probes_silent_when_assumptions_hold,
        test_environment_registry_must_exist_and_list_every_probe,
        test_git_unlink_probe_leaves_no_residue,
        test_git_unlink_probe_residue_is_bounded,
        test_changelog_anchor_mismatch_warns_with_both_values,
        test_changelog_missing_anchor_block_warns,
        test_changelog_entry_above_title_warns,
        test_changelog_body_date_disorder_warns,
        test_changelog_stale_evidence_warns_with_title_and_claim,
        test_line_budget_memory_over_limit_warns_with_both_numbers,
        test_line_budget_memory_missing_markers_warns,
        test_line_budget_memory_within_limit_is_silent,
        test_line_budget_memory_counts_only_its_own_section,
        test_line_budget_constitution_over_limit_fails,
        test_line_budget_severity_is_not_levelled_across_carriers,
        test_line_budget_missing_constitution_fails_but_memory_absence_is_silent,
        test_line_endings_runtime_profile_does_not_enumerate_tracked,
        test_line_endings_release_profile_runs_tracked_sweep,
        test_line_endings_release_path_is_reached_through_the_executor,
        test_line_endings_release_keeps_the_gitattributes_policy_segment,
        test_line_endings_release_still_covers_untracked_control_files,
        test_line_endings_outside_git_still_runs_policy_and_bounded_scan,
        test_stale_identifiers_keeps_both_counter_lines_separate,
        test_stale_identifiers_retired_ids_can_still_fail,
        test_decision_records_runs_linkage_before_citations,
        test_decision_records_lite_skips_citations_only,
        test_changelog_runner_matches_grep_line_semantics,
        test_changelog_runner_reports_unusable_pattern_as_not_evaluable,
        test_changelog_matching_anchors_and_evidence_are_silent,
        test_changelog_pure_functions_mutation_is_killed,
        test_gate_ledger_missing_transition_row_warns,
        test_gate_ledger_missing_pageturn_row_warns,
        test_gate_ledger_placeholder_authorization_warns,
        test_gate_ledger_duplicate_row_id_warns,
        test_gate_ledger_missing_review_closure_warns,
        test_gate_ledger_hint_without_authorization_row_warns,
        test_gate_ledger_malformed_table_fail_closed,
        test_gate_ledger_complete_ledger_is_silent,
        test_gate_ledger_carrier_without_section_is_skipped,
        test_gate_ledger_blocks_before_anchor_are_exempt,
        test_gate_ledger_pure_functions_mutation_is_killed,
        test_gate_ledger_header_driven_checkpoint_table,
        test_gate_ledger_detour_transition_chain_is_accepted,
        test_gate_ledger_active_textbook_lesson_without_section_fails,
        test_gate_ledger_inactive_or_nontextbook_lesson_is_exempt,
        test_problemlog_closure_missing_anchor_fail_closed,
        test_problemlog_closure_missing_field_after_anchor_warns,
        test_problemlog_closure_two_strike_prose_landing_warns,
        test_problemlog_closure_strikes_count_remedies_not_sightings,
        test_problemlog_closure_prose_without_baseline_is_dangling_counter,
        test_problemlog_closure_baseline_after_fact_is_malformed,
        test_problemlog_closure_machine_landings_are_silent,
        test_problemlog_closure_check_reads_instance_log,
        test_rule_enforcement_sound_landings_are_silent,
        test_rule_enforcement_dangling_check_fails,
        test_rule_enforcement_missing_tool_fails,
        test_rule_enforcement_broken_context_anchor_warns,
        test_rule_enforcement_empty_prose_reason_warns,
        test_rule_enforcement_misplaced_fields_fail,
        test_rule_enforcement_fenced_examples_are_silent,
        test_problemlog_closure_dangling_landing_warns,
        test_problemlog_closure_duplicate_stable_id_warns,
        test_external_source_missing_catalog_warns_only_when_ongoing,
        test_external_source_resolvable_diff_anchor_is_silent,
        test_external_source_dangling_diff_anchor_fails,
        test_external_source_none_needs_a_reason,
        test_external_source_empty_input_is_silent,
        test_playbook_taxonomy_r1_byte_drift_fails_parity,
        test_playbook_taxonomy_r2_illegal_value_fails,
        test_playbook_taxonomy_r3_fenced_marker_is_silent,
        test_playbook_taxonomy_r4_blockquote_prefix_counts,
        test_playbook_taxonomy_r5_missing_marker_warns_readme_exempt,
        test_playbook_taxonomy_r6_conflicting_values_fail,
        test_playbook_usage_r1_stale_reference_is_archive_candidate,
        test_playbook_usage_r2_mark_window_cursor_and_recent_silent,
        test_playbook_usage_r3_no_data_is_info_not_warn,
        test_gate_visibility_r1_quiet_without_ledger_rows_warns,
        test_gate_visibility_r2_default_is_explicit_and_needs_no_extra_evidence,
        test_gate_visibility_r3_per_domain_syntax_is_rejected_not_swallowed,
        test_gate_visibility_r4_live_aif_is_quiet_and_audit_intact,
        test_recommendation_r1_missing_required_fields_warn,
        test_recommendation_r2_illegal_status_scope_and_provenance,
        test_recommendation_r3_adopted_without_landing_reference_warns,
        test_recommendation_r4_absent_ledger_and_empty_ledger,
        test_recommendation_r5_live_ledger_is_wellformed_and_keeps_ca_deferred,
        test_domain_tier_r1_top_claim_without_evidence_warns,
        test_domain_tier_r2_dangling_or_missing_pointer_warns,
        test_domain_tier_r3_illegal_value_and_cold_start,
        test_domain_tier_r4_table_parse_is_header_driven,
        test_domain_tier_r5_live_profile_registers_and_resolves,
        test_constitution_parity_r1_section_drift_fails,
        test_constitution_parity_r2_stale_exemption_warns,
        test_constitution_parity_r3_section_set_fork_fails,
        test_constitution_parity_r4_exempt_fork_and_clean_are_silent,
)


def _genesis_ledger_text(first_event_lines: str) -> str:
    """Minimal valid ledger whose only event is the parameterized first event (P-0062)."""
    return (
        "---\ntype: activity_ledger\ncourse_id: TESTG001\n"
        "schema_version: activity_ledger.v1\ntruth_scope: activity_lifecycle\n"
        "updated: 2026-08-08\n---\n# TESTG001 activity ledger\n\n"
        "## Current index\n\n"
        "| activity_type | activity_id | state | binding_status | last_event_id |\n"
        "|---|---|---|---|---|\n"
        "| lesson | lesson01 | ongoing | unbound | ALE-000001 |\n\n"
        "## Course preferences\n\n"
        "lesson_actual_review: inherit\nlesson_student_feedback: inherit\n"
        "lesson_knowledge_absorption: inherit\nexercise_problem_review: inherit\n"
        "exercise_knowledge_mastery: inherit\n\n"
        "## Aliases\n\n_none_\n\n"
        "## Stats\n\ncompleted_lessons: 0\ncompleted_exercises: 0\n"
        "closed_incomplete_lessons: 0\nclosed_incomplete_exercises: 0\n\n"
        "## Activity lifecycle events\n\n"
        "### ALE-000001\n"
        "event_id: ALE-000001\nevent_kind: transition\ncourse_id: TESTG001\n"
        "activity_type: lesson\nactivity_id: lesson01\n"
        f"{first_event_lines}"
        "occurred_at: 2026-08-08T02:00:00-04:00\n"
        "recorded_at: 2026-08-08T02:00:00-04:00\n"
        "triggered_by: user\ntrigger: activity_created\n"
        "transaction_id: MANUAL-GENESIS-testcase\n"
        "evidence_refs: [main/40_course/TESTG001/lessons/lesson01/lesson01.md]\n\n"
        "## Close records\n\n_none_\n"
    )


def test_activity_genesis_rejects_nonplanned_origin(root: Path) -> None:
    """反向（P-0062）：出生只许从 planned 出发；其他起点与非法转换对保持 fail-closed。"""
    doc = ledger_contract.parse_ledger_text(
        _genesis_ledger_text("from_state: ongoing\nto_state: paused\n")
    )
    errors = doc.validate()
    assert any("without prior state" in error for error in errors), errors
    doc = ledger_contract.parse_ledger_text(
        _genesis_ledger_text("from_state: planned\nto_state: paused\n")
    )
    errors = doc.validate()
    assert any(
        "illegal transition" in error or "without prior state" in error
        for error in errors
    ), errors


def test_activity_genesis_transition_from_planned(root: Path) -> None:
    """正向（P-0062）：post-migration 出生 = 首事件 transition planned→ongoing。

    planned 是「存在之前」的默认态（不预造 planned 活动），首次离开它即出生；
    迁移期之外不再需要 migration_snapshot（ALE-000011 型冒用自此无必要）。
    """
    doc = ledger_contract.parse_ledger_text(
        _genesis_ledger_text("from_state: planned\nto_state: ongoing\n")
    )
    errors = doc.validate()
    assert errors == [], errors
    index = doc.rebuild_index()
    entry = index.get("lesson:lesson01")
    assert entry is not None and entry.state == "ongoing", index
    assert entry.binding_status == "unbound", entry.binding_status
    assert entry.last_event_id == "ALE-000001", entry.last_event_id


def test_init_example_payload_is_documented_and_rejected(root: Path) -> None:
    """The five-question example is optional, documented, and never consent."""
    del root
    spec_init = importlib.util.spec_from_file_location(
        "t2ag_init_example_contract", SCRIPT.with_name("t2ag_init.py")
    )
    init_mod = importlib.util.module_from_spec(spec_init)
    assert spec_init and spec_init.loader
    spec_init.loader.exec_module(init_mod)
    example = SCRIPT.with_name("answers.example.json")
    schema_path = SCRIPT.with_name("answers.schema.json")
    payload = json.loads(example.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("required") != [] or init_mod.PROFILE_REQUIRED_ANSWERS:
        raise AssertionError("all five first-run profile questions must remain optional")
    allowed = set(init_mod.default_answers())
    if schema.get("additionalProperties") is not False:
        raise AssertionError("answers.schema.json must reject misspelled/unknown fields")
    if set(schema.get("properties", {})) != allowed | {"example_only"}:
        raise AssertionError("answers.schema.json properties drifted from public defaults")
    if set(payload) != set(init_mod.PROFILE_QUESTION_FIELDS) | {"example_only"}:
        raise AssertionError("answers.example.json must show exactly five questions plus refusal marker")
    if payload["example_only"] is not True:
        raise AssertionError("answers.example.json lost the refusal marker")
    args = type("Args", (), {"answers": str(example), "answers_json": None})()
    try:
        init_mod.load_answers(args)
    except init_mod.GenerationError as exc:
        if "example_only" not in str(exc):
            raise AssertionError(f"the refusal must name the marker: {exc}") from exc
    else:
        raise AssertionError("the example payload was accepted as user-confirmed answers")
    defaults_args = type("Args", (), {"answers": None, "answers_json": "{}"})()
    defaults = init_mod.load_answers(defaults_args)
    if defaults["learning_level"] != "not_provided":
        raise AssertionError(
            "empty answers must leave the learner fact unstated (not_provided), "
            f"never a machine-chosen level: {defaults['learning_level']!r}"
        )
    if init_mod.LEARNING_LEVEL_LABELS.get("not_provided") != "尚未提供":
        raise AssertionError("not_provided must render as the three-state 尚未提供 label")
    if "- 学习水平：尚未提供" not in init_mod.render_profile(defaults):
        raise AssertionError("an unstated learning level must render as 尚未提供")
    if defaults["learning_interests"] != "有待生成":
        raise AssertionError("empty answers must retain the pending interest marker")
    if defaults["reference_curriculum"] != "pending_generation":
        raise AssertionError("empty answers must keep reference curriculum pending")
    customized = {key: value for key, value in payload.items() if key != "example_only"}
    customized.update({"agent_pool_limit": 2, "agent_max_active": 1})
    custom_args = type(
        "Args", (), {"answers": None, "answers_json": json.dumps(customized)}
    )()
    rendered = init_mod.render_profile(init_mod.load_answers(custom_args))
    if "agent_pool_limit: 2" not in rendered or "agent_max_active: 1" not in rendered:
        raise AssertionError("documented optional agent overrides were silently ignored")
    if "- 学习水平：大学在读" not in rendered:
        raise AssertionError("the selected learning level was not rendered")


def test_first_run_portable_profile_contract(root: Path) -> None:
    """Initialized state outranks archive names; learner locale is not author locale."""
    release = root / "t2ag-skeleton"
    profile = release / "main/10_student/profile/profile.md"
    write(
        profile,
        "---\ninitialization_status: uninitialized\n---\n# 学生档案\n",
    )
    write(release / "README.md", "# T2AG 中文 Skeleton\n")
    assert doctor.detect_flavor(release) == "skeleton"
    write(
        profile,
        "---\ninitialization_status: initialized\n---\n"
        "# 学生档案\n\n## 学习兴趣\n\n- 有待生成\n\n"
        "## 自我介绍\n\n未提供\n",
    )
    assert doctor.detect_flavor(release) == "main"
    assert doctor.initialized_profile_content_errors(profile.read_text(encoding="utf-8")) == []

    for timezone_name, cutoff in (
        ("Asia/Shanghai", "00:00"),
        ("America/New_York", "04:00"),
        ("UTC", "23:59"),
    ):
        errors = doctor.activity_close_profile_errors(
            {
                "activity_close_preference_schema": "activity_close_preferences.v1",
                "learning_timezone": timezone_name,
                "learning_day_cutoff": cutoff,
            }
        )
        assert errors == [], (timezone_name, cutoff, errors)
    errors = doctor.activity_close_profile_errors(
        {
            "activity_close_preference_schema": "activity_close_preferences.v1",
            "learning_timezone": "New York",
            "learning_day_cutoff": "24:00",
        }
    )
    assert len(errors) == 2 and all("非法" in error for error in errors), errors

    # A6 庚旋钮：缺字段兼容默认；两个合法值通过；空值与未知值 fail-closed。
    for profile_meta in (
        {},
        {"lesson_tree_display_mode": "progressive"},
        {"lesson_tree_display_mode": "full"},
    ):
        assert doctor.lesson_tree_display_mode_errors(profile_meta) == [], profile_meta
    for illegal in ("", "compact"):
        errors = doctor.lesson_tree_display_mode_errors(
            {"lesson_tree_display_mode": illegal}
        )
        assert len(errors) == 1 and "progressive|full" in errors[0], errors

    spec_init = importlib.util.spec_from_file_location(
        "t2ag_init_lesson_tree_knob_contract", SCRIPT.with_name("t2ag_init.py")
    )
    init_mod = importlib.util.module_from_spec(spec_init)
    assert spec_init and spec_init.loader
    spec_init.loader.exec_module(init_mod)
    defaults = init_mod.default_answers()
    assert defaults["lesson_tree_display_mode"] == "progressive", defaults
    assert "lesson_tree_display_mode: progressive" in init_mod.render_profile(defaults)
    full_args = type(
        "Args",
        (),
        {
            "answers": None,
            "answers_json": json.dumps({"lesson_tree_display_mode": "full"}),
        },
    )()
    assert (
        "lesson_tree_display_mode: full"
        in init_mod.render_profile(init_mod.load_answers(full_args))
    )
    illegal_args = type(
        "Args",
        (),
        {
            "answers": None,
            "answers_json": json.dumps({"lesson_tree_display_mode": "compact"}),
        },
    )()
    try:
        init_mod.load_answers(illegal_args)
    except init_mod.GenerationError as exc:
        assert "lesson_tree_display_mode" in str(exc), exc
    else:
        raise AssertionError("illegal lesson_tree_display_mode was accepted")


def test_first_run_user_experience_contract(root: Path) -> None:
    """The learner sees two meaningful pauses; generator chatter stays internal."""
    del root
    first_run = (REPO / "main/50_playbook/first_run.md").read_text(encoding="utf-8")
    flow = (REPO / "main/50_playbook/t2ag_flow.md").read_text(encoding="utf-8")
    init_source = SCRIPT.with_name("t2ag_init.py").read_text(encoding="utf-8")
    for marker in (
        "## 用户可见状态与停顿",
        "停顿 A｜补充条件",
        "停顿 B｜审阅方案",
        "无停顿的内部落盘",
        "### 面向学生的标准回应骨架",
        "禁止用“全部同意”“同意激活”",
    ):
        if marker not in first_run:
            raise AssertionError(f"first-run user experience marker missing: {marker}")
    for marker in (
        "完整展示参考学习方案",
        "无第三次用户确认",
        "隐藏内部 ID、测试数和维护提示",
    ):
        if marker not in flow:
            raise AssertionError(f"first-run flow regressed: {marker}")
    if init_source.count("print_internal_receipt(") < 5:
        raise AssertionError("not every initialization transition uses an internal receipt")
    for marker in (
        "不得原样展示给学生",
        "课程尚未创建",
        "不要发送中间成功消息或索取新确认",
        "planned 不是新的用户决策",
        "按 first_run.md“完成呈现”回复学生",
    ):
        if marker not in init_source:
            raise AssertionError(f"operator receipt boundary missing: {marker}")
    # PG2/C2: the completion receipt hands over the first task; no separate start gate.
    if "不再另设“是否现在开始”的确认门" not in first_run:
        raise AssertionError("first_run lost the explicit removal of the start gate")
    if "现在开始吗？" in first_run or "询问是否现在开始" in flow:
        raise AssertionError("the removed 「是否现在开始」 pause is back in the learner surface")
    # PG2/PG-F02: learner facts are three-state; a machine default is never a stated fact.
    for marker in ("已提供", "尚未提供", "公开假设", "not_provided"):
        if marker not in first_run:
            raise AssertionError(f"three-state learner-fact wording missing: {marker}")

    # --- PG3（2026-08-25）：建课建组呈现规格的真载体面 ---------------------------
    governance = (REPO / "main/50_playbook/progress_governance.md").read_text(encoding="utf-8")
    group_rules = (REPO / "main/50_playbook/course_group_rules.md").read_text(encoding="utf-8")
    course_init = (REPO / "main/50_playbook/new_course_init.md").read_text(encoding="utf-8")
    plan_template = (
        REPO / "main/30_group/_templates/group/plan.md.template"
    ).read_text(encoding="utf-8")
    calendar_template = (
        REPO / "main/30_group/_templates/group/calendar.md.template"
    ).read_text(encoding="utf-8")

    # §五 的 enforcement 取值按**块**计数，不按文件：`prose_accepted` 全文件已有三条，
    # 一个 `count(...) == 1` 的全文件断言会在下一个批次追加第四条时红，而它红的原因
    # 与它想守的东西无关。块的身份由 `check=runtime.groups` 唯一确定。
    section_five = governance.split("## 五、强制声明", 1)[-1].split("\n## ", 1)[0]
    pg3_blocks = [
        block
        for block in section_five.split("\n\n")
        if block.startswith("enforcement:") and "check=runtime.groups" in block
    ]
    if len(pg3_blocks) != 1:
        raise AssertionError(f"§五 里带 runtime.groups 的 enforcement 块不唯一：{len(pg3_blocks)}")
    values = [
        line[len("enforcement: "):]
        for line in pg3_blocks[0].splitlines()
        if line.startswith("enforcement: ")
    ]
    for value in (
        "check=runtime.groups",
        "tool=70_tools/t2ag_init.py",
        "tool=70_tools/contract_test_support.py",
        "context=50_playbook/course_group_rules.md#误当成第二次用户决策",
    ):
        if values.count(value) != 1:
            raise AssertionError(f"PG3 enforcement 块内 {value} 计数应为 1：{values}")
    if sum(1 for value in values if value.startswith("prose_accepted")) != 1:
        raise AssertionError(f"PG3 enforcement 块应恰有一条 prose_accepted：{values}")
    # context 锚必须真的落在判例上——锚断了，规则就只剩一句自述。
    if "误当成第二次用户决策" not in group_rules:
        raise AssertionError("course_group_rules 判例字面量丢失，§五 的 context 锚将悬空")

    # F07：planned → active 是内部公证；拒绝的默认出口是内部修正，不是问学生要一次同意。
    # 写序倒置只买到「失败不留 active 假状态」，正文必须照这个窄度声称，不得称 atomic。
    section_eight = governance.split("## 八、", 1)[-1]
    for marker in ("内部公证", "不得表述为", "请确认激活", "同意激活", "不是事务原子性"):
        if marker not in section_eight:
            raise AssertionError(f"§八 缺 PG3 规则句成分：{marker}")

    # 语义参数必填：判据、正文与 argparse 三面同步，示例命令行必须能照抄就跑。
    for flag in ("--course-type", "--entry", "--verification-status"):
        if flag not in course_init:
            raise AssertionError(f"new_course_init 未把 {flag} 写进必填通则")
    example = course_init.split("```powershell", 1)[-1].split("```", 1)[0]
    if "--verification-status" not in example:
        raise AssertionError("new_course_init 示例命令行缺 --verification-status，照抄即报错")
    # 必填性按行为判，不按 argparse 私有属性判：缺一个就该解析失败。
    init_mod = _load_init_module("t2ag_init_required_flags")
    complete = [
        "--root", str(REPO), "new-course",
        "--course-id", "REQ1001", "--name", "Req",
        "--course-type", "mastery", "--learning-mode", "textbook",
        "--source-language", "zh-CN", "--lifecycle", "planned", "--entry", "none",
        "--verification-status", "human_verified", "--date", "2026-08-25",
    ]
    with contextlib.redirect_stderr(io.StringIO()):
        init_mod.build_parser().parse_args(complete)  # 完整 argv 仍须可解析
        for flag in ("--course-type", "--entry", "--verification-status", "--source-language"):
            index = complete.index(flag)
            try:
                init_mod.build_parser().parse_args(complete[:index] + complete[index + 2:])
            except SystemExit:
                continue
            raise AssertionError(f"{flag} 缺席仍被接受：默认值又能替学生答一次了")

    # 首组分支：两个模板四处空指全部有出口，且碑行打桩点逐字节不动。
    if plan_template.count("首组分支") != 1 or calendar_template.count("首组分支") != 1:
        raise AssertionError("首组分支段应各模板一处")
    for marker in ("上一组 `review.md`", "上一组 `calendar.md`", "而不是延长上一组或换其他组合"):
        if marker not in plan_template:
            raise AssertionError(f"plan 模板的空指原文被改写了：{marker}")
    if "激活时必须依据上一组结组证据和用户确认重新核定预算" not in calendar_template:
        raise AssertionError("calendar 模板的空指原文被改写了")
    if (
        "- K01 碑描述（属哪门课、达成判据指向该课 progress.md 哪一行）\n- K02 碑描述\n"
        not in plan_template
    ):
        raise AssertionError("碑行打桩点必须逐字节相邻不动（夹具用整串 replace 打桩）")

    # --- PG4（2026-08-25）：本地恢复的 turn_intent 词表与既有行为映射 ----------
    lesson_recover = (REPO / "main/50_playbook/lesson_recover.md").read_text(
        encoding="utf-8"
    )
    section_nine = governance.split("## 九、本地恢复呈现规格（PG4）", 1)
    if len(section_nine) != 2:
        raise AssertionError("progress_governance 缺唯一 PG4 canonical owner 节")
    pg4 = section_nine[1]
    for value in (
        "explicit_continue",
        "ambiguous_resume",
        "conflict_resolution",
        "new_scope",
    ):
        if pg4.count(f"`{value}`") != 1:
            raise AssertionError(f"PG4 turn_intent value 应在 owner 表中恰出现一次：{value}")
        if value not in lesson_recover:
            raise AssertionError(f"lesson_recover 缺 PG4 行为映射：{value}")
    if lesson_recover.count("若用户本轮尚未明确要求继续") != 1:
        raise AssertionError("lesson_recover 的 explicit_continue 条件句被改写或复制")
    for marker in (
        "progress_governance.md` §九的 canonical `turn_intent` 四态",
        "turn_intent=conflict_resolution",
        "内部 ID、schema 与状态码仅按需展开",
    ):
        if marker not in lesson_recover:
            raise AssertionError(f"lesson_recover 缺 PG4 真载体锚：{marker}")
    if "dependency_closed → C4" not in pg4 or "本批不得写成已经跨层闭合" not in pg4:
        raise AssertionError("PG4 owner 未守住云面让渡 C4 的诚实边界")

    # --- PG6（2026-08-25）：结课 Learner Surface 与显式安全对象 ----------------
    session_close = (REPO / "main/50_playbook/session_close.md").read_text(encoding="utf-8")
    activity_close_source = SCRIPT.with_name("activity_close.py").read_text(encoding="utf-8")
    close_roundtrip = SCRIPT.with_name("test_022_close_roundtrip.py").read_text(encoding="utf-8")
    section_ten = governance.split("## 十、结课 Learner Surface 与显式安全对象（PG6）", 1)
    if len(section_ten) != 2:
        raise AssertionError("progress_governance 缺唯一 PG6 canonical owner 节")
    pg6 = section_ten[1]
    for marker in (
        "学生版只展示完整复盘正文、结果含义与学生可选动作",
        "--plan-pending",
        "--plan-decision",
        "--plan-reopen",
        "真实课程 terminal apply 仍是 RT3",
        "PG-R003 = narrow",
    ):
        if marker not in pg6:
            raise AssertionError(f"PG6 owner 缺呈现或授权边界：{marker}")
    for marker in (
        "不得默认展示",
        "presentation SHA 只在内部计算和绑定",
        "系统在 Operator Surface 内绑定 exact tuple",
    ):
        if marker not in session_close:
            raise AssertionError(f"session_close 缺 PG6 流程投影：{marker}")
    if "terminal decision 必须先展示 exact" in session_close:
        raise AssertionError("session_close 仍要求向学生展示 exact tuple")
    for marker in (
        "def require_explicit_plan_tuple(",
        "def require_current_route_match(",
        'parser.add_argument("--course-id")',
        'parser.add_argument("--activity-type", choices=["lesson", "exercise"])',
        'parser.add_argument("--activity-id")',
    ):
        if marker not in activity_close_source:
            raise AssertionError(f"activity_close 缺 PG6 显式对象锁：{marker}")
    for marker in (
        "test_plan_cli_requires_tuple_and_rejects_route_conflict_before_write",
        "pending_event_id",
        "SHA-256",
        "explicit-route.json",
    ):
        if marker not in close_roundtrip:
            raise AssertionError(f"close roundtrip 缺 PG6 持久断言：{marker}")


def test_goal_lesson_first_generation_contract(root: Path) -> None:
    """Real first-user shape: goal + lesson-first closes before Doctor/Context."""
    instance = root / "instance"
    write(instance / "main/t2ag.md", "# T2AG 0.2.3\n")
    shutil.copytree(
        REPO / "main/40_course/_templates/course",
        instance / "main/40_course/_templates/course",
    )
    (instance / "main/20_teacher").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPO / "main/20_teacher/T001.md",
        instance / "main/20_teacher/T001.md",
    )
    shutil.copy2(
        REPO / "main/20_teacher/overlay.md",
        instance / "main/20_teacher/overlay.md",
    )
    spec_init = importlib.util.spec_from_file_location(
        "t2ag_init_goal_lesson_contract", SCRIPT.with_name("t2ag_init.py")
    )
    init_mod = importlib.util.module_from_spec(spec_init)
    assert spec_init and spec_init.loader
    spec_init.loader.exec_module(init_mod)

    invalid = [
        "--root", str(instance), "new-course",
        "--course-id", "BROKEN1001",
        "--name", "Broken",
        "--course-type", "个人创作",
        "--source-language", "zh-CN",
        "--driver", "goal",
        "--entry", "lesson",
        # Present so that the *only* illegal thing left in this argv is the
        # natural-language course type. Without it argparse would exit for a
        # missing required flag instead, and the test would pass while proving
        # nothing about `choices`.
        "--verification-status", "human_verified",
        "--date", "2026-08-24",
    ]
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            init_mod.build_parser().parse_args(invalid)
        except SystemExit as exc:
            assert exc.code != 0
        else:
            raise AssertionError("invalid natural-language course_type reached the writer")
    assert not (instance / "main/40_course/BROKEN1001").exists()

    with contextlib.redirect_stdout(io.StringIO()):
        result = init_mod.main(
            [
                "--root", str(instance), "new-course",
                "--course-id", "NOVEL1001",
                "--name", "小说写作基础",
                "--course-type", "mastery",
                "--source-language", "zh-CN",
                "--learning-mode", "goal",
                "--entry", "lesson",
                "--source-scope", "参考学习方案第一阶段",
                "--position", "课程刚建立，尚未推进",
                "--node-title", "明确类型、主题、主角与核心冲突",
                "--verification-status", "human_verified",
                "--date", "2026-08-24",
            ]
        )
    assert result == 0
    course = instance / "main/40_course/NOVEL1001"
    course_text = (course / "course.md").read_text(encoding="utf-8")
    progress_text = (course / "progress.md").read_text(encoding="utf-8")
    assert "learning_mode: goal" in course_text and "default_driver:" not in course_text
    assert "learning_mode: goal" in progress_text and "course_driver:" not in progress_text
    activity_map = course / "activity_map.md"
    assert activity_map.is_file(), "goal Lesson genesis must own its ContentGroup"
    rows = doctor.heading_rows(
        activity_map.read_text(encoding="utf-8"), "内容组连接表"
    )
    declared = {
        row.get("content_group_id", "").strip("` ")
        for row in rows
        if row.get("content_group_id", "").strip("` ")
    }
    ledger = ledger_contract.parse_ledger_text(
        (course / "activity_ledger.md").read_text(encoding="utf-8")
    )
    entry = ledger.rebuild_index()["lesson:lesson01"]
    assert set(entry.content_group_ids) == declared, (entry.content_group_ids, declared)

    for course_id, course_type in (("BUILD1001", "project"), ("TRADE1001", "praxis")):
        with contextlib.redirect_stdout(io.StringIO()):
            result = init_mod.main(
                [
                    "--root", str(instance), "new-course",
                    "--course-id", course_id,
                    "--name", f"Synthetic {course_type}",
                    "--course-type", course_type,
                    "--source-language", "zh-CN",
                    "--lifecycle", "planned",
                    "--entry", "none",
                    "--verification-status", "human_verified",
                    "--date", "2026-08-24",
                ]
            )
        assert result == 0
        type_course = instance / f"main/40_course/{course_id}"
        combined = (
            (type_course / "course.md").read_text(encoding="utf-8")
            + (type_course / "progress.md").read_text(encoding="utf-8")
        )
        assert "learning_mode:" not in combined
        assert "default_driver:" not in combined and "course_driver:" not in combined

    with contextlib.redirect_stdout(io.StringIO()):
        rejected = init_mod.main(
            [
                "--root", str(instance), "new-course",
                "--course-id", "BADPROJ1001",
                "--name", "Bad Project",
                "--course-type", "project",
                "--source-language", "zh-CN",
                "--learning-mode", "project",
                "--lifecycle", "planned",
                "--entry", "none",
                "--verification-status", "human_verified",
                "--date", "2026-08-24",
            ]
        )
    assert rejected != 0, "Project Course accepted a selectable learning mode"
    assert not (instance / "main/40_course/BADPROJ1001").exists()



def run_contract_tests(tests: tuple, *, suite_name: str) -> int:
    """Run a durable selection of atomic assertions in isolated fixture roots."""
    total = len(tests)
    with tempfile.TemporaryDirectory(prefix=f"t2ag_{suite_name}_") as tmp:
        base = Path(tmp)
        for index, test in enumerate(tests, start=1):
            root = base / f"case_{index}"
            try:
                test(root)
            except BaseException:
                # 分母护栏（P-0077）：中止路径必须自报规模。原实现只在成功路径打
                # `result:` 行，于是崩溃时分母消失——屏幕上只剩「跑到第 N 个红了」，
                # 没有任何一处说明本该跑几个，未执行的测试因此不成像（2026-08-09 起
                # 第 18 个之后 4 个测试两周零执行，13 天无人知）。
                # 本刀只补可见性：traceback 与退出码保持原样。是否「记错续跑」及
                # 长红时效属 A/C 裁决面，不在此处施工。
                print(
                    f"result: {index - 1}/{total} {suite_name} tests passed before "
                    f"ABORT at #{index} {test.__name__}; "
                    f"{total - index} never executed",
                    file=sys.stderr,
                    flush=True,
                )
                raise
            print(f"PASS {test.__name__}")
    print(f"result: {total}/{total} {suite_name} tests passed")
    return 0


_VER_CUR = "## 7. 版本  [max 14]\n\n- 当前运行版本：`{}`；`implementation_status`：`partial`\n"
_VER_LEDGER_OK = (
    "- 0.2.3 `implementation_status`：`complete`；`candidate_review`：`passed`\n"
)


def test_version_bump_r1_partial_predecessor_fails(root: Path) -> None:
    """R1: predecessor `implementation_status=partial` → VER-BUMP-000 FAIL."""
    findings = doctor.version_bump_precondition_findings(
        _VER_CUR.format("0.2.4"),
        "- 0.2.3 `implementation_status`：`partial`；`candidate_review`：`not_run`\n",
    )
    codes = [code for code, _, _ in findings]
    if "VER-BUMP-000" not in codes:
        raise AssertionError(f"partial predecessor must FAIL 000: {findings}")


def test_version_bump_r2_missing_ledger_record_fails(root: Path) -> None:
    """R2: predecessor absent from the ledger → VER-BUMP-001 FAIL.

    A neighbouring version's record must not answer for the missing one.
    """
    findings = doctor.version_bump_precondition_findings(
        _VER_CUR.format("0.2.4"),
        "- 0.2.2 `implementation_status`：`complete`；`candidate_review`：`passed`\n",
    )
    codes = [code for code, _, _ in findings]
    if "VER-BUMP-001" not in codes:
        raise AssertionError(f"missing predecessor record must FAIL 001: {findings}")


def test_version_bump_r3_unreviewed_predecessor_warns(root: Path) -> None:
    """R3: predecessor complete but `candidate_review != passed` → 002 WARN."""
    findings = doctor.version_bump_precondition_findings(
        _VER_CUR.format("0.2.4"), _VER_LEDGER_OK.replace("passed", "not_run")
    )
    pairs = [(code, severity) for code, severity, _ in findings]
    if ("VER-BUMP-002", "WARN") not in pairs:
        raise AssertionError(f"unreviewed predecessor must WARN 002: {findings}")


def test_version_bump_g1_closed_predecessor_is_silent(root: Path) -> None:
    """G1: a closed-out predecessor produces nothing — the gate stays quiet."""
    findings = doctor.version_bump_precondition_findings(
        _VER_CUR.format("0.2.4"), _VER_LEDGER_OK
    )
    if findings:
        raise AssertionError(f"closed predecessor must be silent: {findings}")


def test_version_bump_g2_minor_bump_is_declared_hole(root: Path) -> None:
    """G2: patch==0 reports nothing — the coverage hole is declared, not hidden.

    Pinning it keeps the silence deliberate: if someone later teaches the check
    to walk minor bumps, this fixture fails and forces the docstring to change
    with it.
    """
    findings = doctor.version_bump_precondition_findings(
        _VER_CUR.format("0.3.0"),
        "- 0.2.3 `implementation_status`：`partial`；`candidate_review`：`not_run`\n",
    )
    if findings:
        raise AssertionError(f"minor bump is out of scope by design: {findings}")


def _canon_log_block(block_id: str, content: str) -> str:
    """A teaching_log.md block exactly as canon_append.py writes it."""
    return f"## {block_id}\n\n> seq 1 · emitted_at X · pages A\n\n{content}"


def _canon_line(block_id: str, content: str, prev: str = "GENESIS",
                page_refs: list | None = None) -> str:
    import hashlib as _h
    return json.dumps({
        "seq": 1, "block_id": block_id, "lesson": "lesson01",
        "emitted_at": "X", "page_refs": page_refs or [],
        "content_sha256": _h.sha256(content.encode("utf-8")).hexdigest(),
        "prev_sha256": prev,
    }, ensure_ascii=False, sort_keys=True)


_CANON_ASSETS = {"A1": {
    "asset_id": "A1", "source_document_sha256": "aaa", "pdf_page_index": "1",
    "render_profile": "rp", "render_sha256": "bbb",
}}


def test_canon_r1_block_without_ledger_row_fails(root: Path) -> None:
    """R1: canon block with no emissions row → CANON-000 FAIL (bypass).

    Tests the clumsy bypass only.  A forger writing C and L together as one
    consistent chain is out of scope for G2 by declared design
    (canon_carrier.md header) — no fixture pretends otherwise.
    """
    findings = doctor.canonical_carrier_findings(
        _canon_log_block("B001", "你好。\n"), [], _CANON_ASSETS, "T/l1")
    if [(c, s) for c, s, _ in findings] != [("CANON-000", "FAIL")]:
        raise AssertionError(f"bypass must FAIL 000: {findings}")


def test_canon_r2_broken_chain_fails(root: Path) -> None:
    """R2: second row's prev_sha256 does not hash-link to the first → 001."""
    l1 = _canon_line("B001", "你好。\n")
    l2 = _canon_line("B002", "再见。\n", prev="not-the-real-hash")
    findings = doctor.canonical_carrier_findings(
        _canon_log_block("B001", "你好。\n") + _canon_log_block("B002", "再见。\n"),
        [l1, l2], _CANON_ASSETS, "T/l1")
    if ("CANON-001", "FAIL") not in [(c, s) for c, s, _ in findings]:
        raise AssertionError(f"broken chain must FAIL 001: {findings}")


def test_canon_r3_page_identity_mismatch_fails(root: Path) -> None:
    """R3: ledger page identity differs from the asset frontmatter → 002."""
    refs = [dict(_CANON_ASSETS["A1"], render_sha256="TAMPERED")]
    line = _canon_line("B001", "你好。\n", page_refs=refs)
    findings = doctor.canonical_carrier_findings(
        _canon_log_block("B001", "你好。\n"), [line], _CANON_ASSETS, "T/l1")
    if ("CANON-002", "FAIL") not in [(c, s) for c, s, _ in findings]:
        raise AssertionError(f"identity mismatch must FAIL 002: {findings}")


def test_canon_r4_content_hash_mismatch_fails(root: Path) -> None:
    """R4: canon body was edited after emit → 003."""
    line = _canon_line("B001", "你好。\n")
    findings = doctor.canonical_carrier_findings(
        _canon_log_block("B001", "被改过的正文。\n"), [line], _CANON_ASSETS, "T/l1")
    if ("CANON-003", "FAIL") not in [(c, s) for c, s, _ in findings]:
        raise AssertionError(f"edited canon must FAIL 003: {findings}")


def test_canon_r5_ledger_row_without_block_warns(root: Path) -> None:
    """R5: L row with no C block → 004 WARN (crash residue, by design)."""
    line = _canon_line("B001", "你好。\n")
    findings = doctor.canonical_carrier_findings("", [line], _CANON_ASSETS, "T/l1")
    if [(c, s) for c, s, _ in findings] != [("CANON-004", "WARN")]:
        raise AssertionError(f"crash residue must WARN 004: {findings}")


def test_canon_g1_empty_state_is_silent(root: Path) -> None:
    """G1: both sides absent/empty → silence (adoption is a fact, not a debt)."""
    if doctor.canonical_carrier_findings("", [], {}, "T/l1"):
        raise AssertionError("empty state must be silent")


def test_canon_g2_valid_chain_is_silent(root: Path) -> None:
    """G2: a fully consistent C+L+asset triple produces nothing."""
    refs = [dict(_CANON_ASSETS["A1"])]
    l1 = _canon_line("B001", "你好。\n", page_refs=refs)
    import hashlib as _h
    l2 = _canon_line("B002", "再见。\n",
                     prev=_h.sha256(l1.encode("utf-8")).hexdigest())
    findings = doctor.canonical_carrier_findings(
        _canon_log_block("B001", "你好。\n") + _canon_log_block("B002", "再见。\n"),
        [l1, l2], _CANON_ASSETS, "T/l1")
    if findings:
        raise AssertionError(f"valid chain must be silent: {findings}")


def _course_progression_migration():
    """Load the read-only 0.2.4 progression planner under test."""
    spec = importlib.util.spec_from_file_location(
        "course_progression_migration_under_test",
        SCRIPT.with_name("t2ag_course_progression_migration.py"),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_course_progression_migration_real_carriers_are_byte_stable(root: Path) -> None:
    """真载体主证：0.2.4 progression 迁移在仓内实课上必须字节稳定。

    断言的是**不动点性质**（planned_text 幂等、等值写入零改动），不是
    「当前这些课必须 changed=False」。后者会把断言绑死在实例的迁移状态上：
    将来新增一门尚未迁移的课程就误红，是编组正本明令禁止的形态。

    本函数不出现任何课程 ID 字面量——载体由 main/40_course 的目录走查产生，
    被测值由文件自身的 frontmatter 产生，无任何可供「改断言迁就输出」的常量。
    """
    migration = _course_progression_migration()
    courses = REPO / "main/40_course"
    folders = sorted(
        path for path in (courses.iterdir() if courses.is_dir() else ())
        if path.is_dir() and not path.name.startswith("_")
    )
    scanned = 0
    with_mode = 0
    for folder in folders:
        course_path = folder / "course.md"
        progress_path = folder / "progress.md"
        if not course_path.is_file() or not progress_path.is_file():
            continue
        course_text = course_path.read_text(encoding="utf-8-sig")
        progress_text = progress_path.read_text(encoding="utf-8-sig")
        progression = activity.resolve_course_progression(
            activity.frontmatter_text(course_text),
            activity.frontmatter_text(progress_text),
        )
        scanned += 1
        for path, text, is_course in (
            (course_path, course_text, True),
            (progress_path, progress_text, False),
        ):
            rel = path.relative_to(REPO).as_posix()
            p1 = migration.planned_text(
                text,
                course_type=progression.course_type,
                learning_mode=progression.learning_mode,
                is_course=is_course,
            )
            p2 = migration.planned_text(
                p1,
                course_type=progression.course_type,
                learning_mode=progression.learning_mode,
                is_course=is_course,
            )
            if p2 != p1:
                raise AssertionError(
                    f"planned_text is not a fixed point on {rel}: {p1!r} -> {p2!r}"
                )
            current = activity.frontmatter_text(text).get("learning_mode")
            if current is None:
                continue
            with_mode += 1
            after = migration.set_frontmatter_field(text, "learning_mode", current)
            if after != text:
                raise AssertionError(
                    f"equal-value write changed {rel}: {len(after) - len(text)} byte delta"
                )
    if scanned == 0:
        raise AssertionError(f"no real course carrier was scanned under {courses}")
    if with_mode == 0:
        raise AssertionError(
            "no real carrier carried learning_mode; T-2 degenerated to a vacuous pass"
        )


def test_course_progression_migration_field_edit_boundaries(root: Path) -> None:
    """set_frontmatter_field 的替换/删除/追加三分支边界矩阵。

    本函数使用**构造样本，仅作边界覆盖**；幂等主证由 T-1/T-2 的真载体承担。
    构造样本的期望值是字面量，可被「改断言迁就输出」弯折，因此每个样本
    除逐字节比对外还叠一层不依赖字面量的性质断言（行数增量、行尾一致性、
    再次施加同一操作不变），弯折字面量并不能让性质断言变绿。

    覆盖：字段位于首行/中间/末行、frontmatter 仅一行、字段缺失走追加分支、
    frontmatter 尾部原有空行、同名键出现两次（count=1 首个匹配语义）、
    value=None 且被删字段在末行、空值键跨行吞噬、全 LF 与全 CRLF 两套行尾。
    """
    migration = _course_progression_migration()
    edit = migration.set_frontmatter_field
    samples = (
        ("S-01", "---\ntype: course\nlearning_mode: goal\n---\n# body\n",
         "learning_mode", "textbook",
         "---\ntype: course\nlearning_mode: textbook\n---\n# body\n", "replace"),
        ("S-02", "---\nlearning_mode: goal\ntype: course\n---\n# body\n",
         "learning_mode", "textbook",
         "---\nlearning_mode: textbook\ntype: course\n---\n# body\n", "replace"),
        ("S-03", "---\ntype: course\nlearning_mode: goal\nstatus: ongoing\n---\n# body\n",
         "learning_mode", "textbook",
         "---\ntype: course\nlearning_mode: textbook\nstatus: ongoing\n---\n# body\n", "replace"),
        ("S-04", "---\nlearning_mode: goal\n---\n# body\n",
         "learning_mode", "goal",
         "---\nlearning_mode: goal\n---\n# body\n", "replace"),
        ("S-05", "---\ntype: course\n---\n# body\n",
         "learning_mode", "goal",
         "---\ntype: course\nlearning_mode: goal\n---\n# body\n", "append"),
        ("S-06", "---\ntype: course\n\n---\n# body\n",
         "learning_mode", "goal",
         "---\ntype: course\nlearning_mode: goal\n---\n# body\n", "append-absorb"),
        ("S-07", "---\nlearning_mode: goal\n\n---\n# body\n",
         "learning_mode", "textbook",
         "---\nlearning_mode: textbook\n\n---\n# body\n", "replace"),
        ("S-08", "---\ntype: course\ndefault_driver: lesson\n---\n# body\n",
         "default_driver", None,
         "---\ntype: course\n---\n# body\n", "delete-present"),
        ("S-09", "---\ntype: course\ncourse_driver: lesson\nstatus: ongoing\n---\n# body\n",
         "course_driver", None,
         "---\ntype: course\nstatus: ongoing\n---\n# body\n", "delete-present"),
        ("S-10", "---\ntype: course\n---\n# body\n",
         "default_driver", None,
         "---\ntype: course\n---\n# body\n", "no-op"),
        ("S-11", "---\nlearning_mode: goal\nlearning_mode: project\n---\n# body\n",
         "learning_mode", "textbook",
         "---\nlearning_mode: textbook\nlearning_mode: project\n---\n# body\n", "replace"),
        ("S-12", "---\ndefault_driver: lesson\ndefault_driver: exercise\n---\n# body\n",
         "default_driver", None,
         "---\ndefault_driver: exercise\n---\n# body\n", "delete-present"),
        ("S-13", "---\r\ntype: course\r\nlearning_mode: goal\r\n---\r\n# body\r\n",
         "learning_mode", "goal",
         "---\r\ntype: course\r\nlearning_mode: goal\r\n---\r\n# body\r\n", "replace"),
        ("S-14", "---\r\ntype: course\r\nlearning_mode: goal\r\nstatus: ongoing\r\n---\r\n# body\r\n",
         "learning_mode", "textbook",
         "---\r\ntype: course\r\nlearning_mode: textbook\r\nstatus: ongoing\r\n---\r\n# body\r\n", "replace"),
        ("S-15", "---\r\ntype: course\r\ndefault_driver: lesson\r\n---\r\n# body\r\n",
         "default_driver", None,
         "---\r\ntype: course\r\n---\r\n# body\r\n", "delete-present"),
        ("S-16", "---\r\ntype: course\r\n---\r\n# body\r\n",
         "learning_mode", "goal",
         "---\r\ntype: course\r\nlearning_mode: goal\r\n---\r\n# body\r\n", "append"),
        ("S-17", "---\nlearning_mode:\ntype: course\n---\n# body\n",
         "learning_mode", "goal",
         "---\nlearning_mode: goal\ntype: course\n---\n# body\n", "replace"),
    )
    expected_line_delta = {
        "replace": 0,
        "delete-present": -1,
        "append": 1,
        "append-absorb": 0,
        "no-op": 0,
    }
    if len(samples) != 17:
        raise AssertionError(f"boundary matrix shrank to {len(samples)} samples")
    for sid, inp, field, value, expected, kind in samples:
        actual = edit(inp, field, value)
        if actual != expected:
            raise AssertionError(f"{sid}: expected {expected!r}, got {actual!r}")
        delta = len(actual.split("\n")) - len(inp.split("\n"))
        want = expected_line_delta[kind]
        if delta != want:
            raise AssertionError(f"{sid}: line count moved by {delta}, expected {want}")
        if actual.count("\r") != actual.count("\r\n"):
            raise AssertionError(f"{sid}: bare CR left outside a CRLF pair: {actual!r}")
        crlf_document = "\r\n" in inp and inp.count("\n") == inp.count("\r\n")
        if crlf_document and actual.count("\n") != actual.count("\r\n"):
            raise AssertionError(f"{sid}: bare LF introduced into a CRLF document: {actual!r}")
        again = edit(actual, field, value)
        if sid == "S-12":
            # 该样本的不幂等系 count=1 首匹配语义（§1.3 冻结条款）之推论，非缺陷；
            # 此处把该冻结语义正面锁死，若有人把删除改为全删，此断言当场报红。
            if again != "---\n\n---\n# body\n":
                raise AssertionError(
                    f"{sid}: count=1 delete no longer matches its frozen "
                    f"second-application value: {again!r}"
                )
        elif again != actual:
            raise AssertionError(
                f"{sid}: second application was not a no-op: {actual!r} -> {again!r}"
            )
    try:
        result = edit("# body only\n", "learning_mode", "goal")
    except ValueError as exc:
        if "missing frontmatter" not in str(exc):
            raise AssertionError(f"unexpected error text: {exc}")
    else:
        raise AssertionError(f"missing frontmatter must raise, got {result!r}")
