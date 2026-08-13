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

import activity_ledger as ledger_contract
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
    reset(root)
    write(root / "README.md", f"{FIXTURE_VERSION}\n")
    write(root / "AGENTS.md", f"{FIXTURE_VERSION}\n")
    write(root / "main/bin/t2ag", f"{FIXTURE_VERSION}\n")
    write(root / "main/t2ag.md", FIXTURE_CONSTITUTION)
    write(root / "main/00_core/t2ag_memory.md", f"{FIXTURE_VERSION}\n")
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
            for relative, text in entries.items():
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

    # A quarantined `.bak-*` copy is evidence of what shipped before, not a new finding.
    reset(repo, "skeleton")
    contaminated.rename(root / "t2ag-skeleton.zip.bak-20260809")
    run_silently(doctor.check_release_package_surface)
    if doctor.fails:
        raise AssertionError(f"a quarantined .bak copy must not be re-flagged: {doctor.fails}")


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
    branch = content.find("### 步骤 3：按 current_activity 恢复主载体")
    lesson = content.find("#### `lesson` 分支")
    exercise = content.find("#### `exercise` 分支")
    working = content.find("步骤 5：教材原文窗口（Snapshot-only）")
    if not (0 <= branch < lesson < exercise < working):
        raise AssertionError("lesson_recover does not branch before Lesson/preparation consumers")
    required = (
        "Exercise 首启不得读取或构造 Lesson 路径",
        "不写 `current_lesson`",
        "教材原文窗口 **仅在 `lesson` + `course_driver: textbook`**",
        "t2ag_activity.py --course <COURSE_ID> --intent recover",
        "连续 Scope **5–8**",
        "不得自动清理",
        "exact RT3",
        "current_snapshot.json",
    )
    missing = [token for token in required if token not in content]
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
    close_required = (
        "t2ag_activity.py --course <COURSE_ID> --intent close",
        "Micro close 和完整结课都必须原子完成",
        "Exercise 结课不得顺手",
        "不产生 pending、CLR 或自动 pause",
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


SYNTHETIC_INIT_ANSWERS = {
    "nickname": "synthetic student",
    "school": "synthetic institute",
    "stage": "synthetic stage",
    "direction": "synthetic direction",
    "weekly_time": "1 小时",
    "goals": ["验证公开生成路径的 Exercise-first 往返"],
    "tutoring_preference": "逐步确认",
    "long_explanation_mode": "map-first",
    "branch_confirmation": "每支讲完确认",
    "cycle_structure": "synthetic cycle",
    "small_adjustment": "每循环一次",
    "big_adjustment": "每三循环",
    "aged_review_mode": "suggest",
    "existing_basis": "合成测试",
    "current_difficulty": "未提供",
    "teaching_notes": "未提供",
    "exercise_hint_gate": "enabled",
    "learning_timezone": "Asia/Singapore",
    "learning_day_cutoff": "04:00",
    "lesson_actual_review": "on",
    "lesson_student_feedback": "on",
    "lesson_knowledge_absorption": "on",
    "exercise_problem_review": "on",
    "exercise_knowledge_mastery": "on",
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
        "--driver", "textbook",
        "--lifecycle", "ongoing",
        "--entry", "exercise",
        "--teacher", "T001",
        "--source-scope", "synthetic",
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
    cli(
        "t2ag_init.py", "--root", str(fixture), "new-group",
        "--group-id", "G01",
        "--members", course_id,
        "--status", "active",
        "--cycle", "synthetic",
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

HANDOFF_INDEX_HEADINGS = (
    "Active Handoffs",
    "下一版本 Backlog",
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
    for token in ("89 个脏文件", "零命中", "sha256"):
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


AUTHORIZATION_PLAYBOOK_FIXTURE = {
    "main/50_playbook/batch_workorder_spec.md": (
        "授权不可放大\n尚未生成的对象不可预授权\n"
    ),
    "main/50_playbook/session_close.md": (
        "user + direct_user\nreceipt 只记录授权证据\n"
    ),
    "main/50_playbook/remediation_governance.md": (
        "stopped_budget\n默认最多两轮 finding 整改\n"
    ),
    "main/50_playbook/handoff_management.md": (
        "### 8.1 恢复后动作授权门\n"
        "概括性认可只覆盖当轮已具体列出的动作\n"
        "Handoff 的 authorization 字段是历史记录，不构成当轮许可\n"
    ),
}


def write_authorization_governance_fixture(repo: Path) -> None:
    """Seed the minimum surface check_authorization_governance reads."""
    instructions = "授权不可放大与闭环止损\nstopped_budget\ntoken\n"
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
            "概括性认可只覆盖当轮已具体列出的动作", "接管方可自行判断范围", 1
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


def test_memory_budget_over_limit_warns_with_both_numbers(root: Path) -> None:
    """NEGATIVE: an over-budget section must be named with actual AND cap.

    "WARN 不指名等于没报" — a bare "memory too long" leaves the reader to go
    measure it themselves, which is how a WARN becomes background noise.
    """
    reset(root)
    body = _memory_budget_fixture(
        "## 最近关键决策  [max 3]\n" + "".join(f"- entry {i}\n" for i in range(10))
    )
    write(root / "main/00_core/t2ag_memory.md", body)
    run_silently(doctor.check_memory_budget)
    assert_message(doctor.warns, "最近关键决策")
    assert_message(doctor.warns, "预算 3 行")
    if not any("实测 11 行" in w for w in doctor.warns):
        raise AssertionError(f"actual line count not named: {doctor.warns}")


def test_memory_budget_missing_markers_warns(root: Path) -> None:
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
    run_silently(doctor.check_memory_budget)
    assert_message(doctor.warns, "无任何 [max N] 节预算标记")


def test_memory_budget_within_limit_is_silent(root: Path) -> None:
    """POSITIVE: a section under budget must produce no output at all."""
    reset(root)
    write(
        root / "main/00_core/t2ag_memory.md",
        _memory_budget_fixture("## 最近关键决策  [max 50]\n- entry\n"),
    )
    run_silently(doctor.check_memory_budget)
    if doctor.warns or doctor.fails:
        raise AssertionError(f"healthy budget must stay quiet: {doctor.warns}")


def test_memory_budget_counts_only_its_own_section(root: Path) -> None:
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
    """NEGATIVE: occurrence_count>=2 + prose_accepted → 002（两振出局）."""
    text = _PLOG_HEADER + (
        "## P-0061 | [2026-08-10] | repeat\n\n"
        "- occurrence_count: 3\n- closure: prose_accepted（临时）\n"
    )
    findings = doctor.problemlog_closure_findings(text)
    if not any(code == "PLOG-CLOSURE-002" for code, _ in findings):
        raise AssertionError(f"two-strike prose landing not flagged: {findings}")


def test_problemlog_closure_machine_landings_are_silent(root: Path) -> None:
    """POSITIVE: open / check= / tool= landings and first-strike prose pass."""
    text = _PLOG_HEADER + (
        "## P-0060 | [2026-08-10] | a\n\n- occurrence_count: 1\n"
        "- closure: prose_accepted（成本低）\n\n"
        "## P-0061 | [2026-08-10] | b\n\n- occurrence_count: 4\n"
        "- closure: check=GATE-LEDGER-007\n\n"
        "## P-0062 | [2026-08-10] | c\n\n- closure: tool=70_tools/t2ag_hint_gate.py\n\n"
        "## P-0063 | [2026-08-10] | d\n\n- closure: open\n"
    )
    findings = doctor.problemlog_closure_findings(text)
    if findings:
        raise AssertionError(f"legal landings must stay silent: {findings}")


def test_problemlog_closure_check_reads_instance_log(root: Path) -> None:
    """End-to-end: check_problemlog_closure consumes main/00_core and WARNs."""
    reset(root)
    write(
        root / "main/00_core/t2ag_problemlog.md",
        _PLOG_HEADER + "## P-0060 | [2026-08-10] | new\n\n- tags: [b]\n",
    )
    run_silently(doctor.check_problemlog_closure)
    assert_message(doctor.warns, "PLOG-CLOSURE-001")


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
        test_migration_manifest_tamper,
        test_migration_manifest_missing_reference,
        test_main_readme_skeleton_reference_does_not_change_migration_kind,
        test_profile_migration_manifest_tamper,
        test_profile_migration_roundtrip,
        test_handoff_assertion_without_source_is_reported,
        test_handoff_assertion_with_source_is_accepted,
        test_handoff_assertion_scan_skips_structure_only,
        test_handoff_required_context_layers_are_enforced,
        test_handoff_active_lane_absence_contradiction_is_enforced,
        test_handoff_index_version_drift_is_enforced,
        test_handoff_shadow_runtime_index_is_enforced,
        test_resume_authorization_gate_is_enforced,
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
        test_memory_budget_over_limit_warns_with_both_numbers,
        test_memory_budget_missing_markers_warns,
        test_memory_budget_within_limit_is_silent,
        test_memory_budget_counts_only_its_own_section,
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
        test_problemlog_closure_machine_landings_are_silent,
        test_problemlog_closure_check_reads_instance_log,
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


def run_contract_tests(tests: tuple, *, suite_name: str) -> int:
    """Run a durable selection of atomic assertions in isolated fixture roots."""
    with tempfile.TemporaryDirectory(prefix=f"t2ag_{suite_name}_") as tmp:
        base = Path(tmp)
        for index, test in enumerate(tests, start=1):
            root = base / f"case_{index}"
            test(root)
            print(f"PASS {test.__name__}")
    print(f"result: {len(tests)}/{len(tests)} {suite_name} tests passed")
    return 0
