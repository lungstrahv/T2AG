#!/usr/bin/env python3
"""Resolve the one authoritative current LearningActivity for a course.

This module is deliberately read-only.  It turns the explicit activity fields
in ``progress.md`` into concrete recovery and close targets.  Consumers must
not route through the compatibility-only ``current_lesson`` field.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Mapping

import activity_ledger as ledger_contract


ROOT = Path(__file__).resolve().parents[2]
NO_LESSON = {"", "none", "—"}
COURSE_TYPES = {"mastery", "project", "praxis"}
MASTERY_LEARNING_MODES = {"textbook", "goal", "project"}
LEGACY_COURSE_DRIVERS = MASTERY_LEARNING_MODES | {"praxis"}
TEACHER_MAPPING_HEADING = "课程—教师映射"
TEACHER_MAPPING_COLUMNS = ("课程代码", "课程名称", "教师模板", "教师风格")


class ActivityContractError(ValueError):
    """One or more explicit activity invariants are invalid."""

    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


class TeacherContractError(ValueError):
    """The one teacher mapping table is missing, ambiguous, or malformed."""

    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


TextReader = Callable[[Path], str]


def frontmatter_text(content: str) -> dict[str, str]:
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


def frontmatter(path: Path, *, reader: TextReader = read) -> dict[str, str]:
    if not path.is_file():
        return {}
    return frontmatter_text(reader(path))


@dataclass(frozen=True)
class ProgressSnapshot:
    path: Path
    content: str
    meta: Mapping[str, str]


@dataclass(frozen=True)
class CourseProgression:
    """Resolved course-owned progression semantics.

    ``learning_mode`` exists only for Mastery.  ``effective_key`` is an
    internal compatibility projection for old consumers; it is not a driver
    field owned by Project or Praxis.
    """

    course_type: str
    learning_mode: str | None
    compatibility_source: str

    @property
    def effective_key(self) -> str:
        return self.learning_mode or self.course_type

    @property
    def is_textbook_led(self) -> bool:
        return self.course_type == "mastery" and self.learning_mode == "textbook"


def resolve_course_progression(
    course_meta: Mapping[str, str],
    progress_meta: Mapping[str, str] | None = None,
) -> CourseProgression:
    """Resolve canonical fields, with read-only support for 0.2.3 drivers.

    New truth is ``course_type`` plus Mastery-only ``learning_mode``.  The old
    ``default_driver`` / ``course_driver`` pair remains readable while real
    course instances await their separately authorized migration, but it may
    not contradict the type-owned model.
    """
    progress_meta = progress_meta or {}
    errors: list[str] = []
    course_type = str(course_meta.get("course_type") or "")
    if course_type not in COURSE_TYPES:
        errors.append(f"course_type 非法：{course_type or '缺失'}")

    course_mode = str(course_meta.get("learning_mode") or "")
    progress_mode = str(progress_meta.get("learning_mode") or "")
    legacy_course = str(course_meta.get("default_driver") or "")
    legacy_progress = str(progress_meta.get("course_driver") or "")

    for label, value in (
        ("default_driver", legacy_course),
        ("course_driver", legacy_progress),
    ):
        if value and value not in LEGACY_COURSE_DRIVERS:
            errors.append(f"{label} 兼容值非法：{value}")

    mode: str | None = None
    source = "canonical"
    if course_type == "mastery":
        declared = [value for value in (course_mode, progress_mode) if value]
        if declared and len(set(declared)) != 1:
            errors.append(
                "Mastery learning_mode 在 course/progress 间不一致："
                f"{course_mode or '缺失'} != {progress_mode or '缺失'}"
            )
        if declared:
            mode = declared[0]
        else:
            legacy = [value for value in (legacy_course, legacy_progress) if value]
            if legacy and len(set(legacy)) != 1:
                errors.append(
                    "Mastery legacy driver 在 course/progress 间不一致："
                    f"{legacy_course or '缺失'} != {legacy_progress or '缺失'}"
                )
            if legacy:
                mode = legacy[0]
                source = "legacy_driver"
        if mode not in MASTERY_LEARNING_MODES:
            errors.append(
                "Mastery 缺合法 learning_mode："
                f"{mode or '缺失'}（允许 {sorted(MASTERY_LEARNING_MODES)}）"
            )
        for label, value in (
            ("default_driver", legacy_course),
            ("course_driver", legacy_progress),
        ):
            if value and mode and value != mode:
                errors.append(f"{label} 与 Mastery learning_mode 冲突：{value} != {mode}")
    elif course_type in {"project", "praxis"}:
        if course_mode or progress_mode:
            errors.append(f"{course_type} Course 不得声明 learning_mode")
        for label, value in (
            ("default_driver", legacy_course),
            ("course_driver", legacy_progress),
        ):
            if value and value != course_type:
                errors.append(
                    f"{course_type} Course 的 {label} 兼容值必须为 {course_type}，实际 {value}"
                )
        if legacy_course or legacy_progress:
            source = "legacy_driver"

    if errors:
        raise ActivityContractError(errors)
    return CourseProgression(course_type, mode, source)


def validate_progress_identity(
    meta: dict[str, str],
    expected_course_id: str,
) -> None:
    """Reject a progress carrier before any consumer trusts its identity."""
    errors: list[str] = []
    if meta.get("type") != "course_progress":
        errors.append(
            "progress type 必须为 course_progress："
            f"{meta.get('type') or '缺失'}"
        )
    if meta.get("course_id") != expected_course_id:
        errors.append(
            "progress course_id 必须等于目录课程 ID："
            f"{meta.get('course_id') or '缺失'} != {expected_course_id}"
        )
    # 0.2.2: truth_scope is preferred; truth_source:true remains accepted for 0.2.1.
    truth_scope = (meta.get("truth_scope") or "").strip()
    if truth_scope:
        required_bits = {
            "course_lifecycle",
            "course_frontend",
            "activity_position",
        }
        bits = {part.strip() for part in truth_scope.split(",") if part.strip()}
        if not required_bits.issubset(bits):
            errors.append(
                "progress truth_scope 必须包含 course_lifecycle,course_frontend,"
                f"activity_position：{truth_scope or '缺失'}"
            )
    elif meta.get("truth_source") != "true":
        errors.append(
            "progress 必须声明 truth_scope 或 truth_source: true："
            f"truth_scope={meta.get('truth_scope') or '缺失'} "
            f"truth_source={meta.get('truth_source') or '缺失'}"
        )
    if errors:
        raise ActivityContractError(errors)


def _is_link_or_reparse(path: Path) -> bool:
    """Return true for symlinks, junctions, or other Windows reparse points."""
    try:
        info = path.lstat()
    except OSError:
        return False
    return bool(
        stat.S_ISLNK(info.st_mode)
        or (
            os.name == "nt"
            and getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
    )


def resolve_course_book_path(
    root: Path,
    course_id: str,
    raw_path: str,
    *,
    must_exist: bool = True,
) -> Path:
    """Resolve a canonical, non-linked path inside one Course's persistent book.

    Lexical prefix checks are insufficient because ``book/../exercises`` still
    starts with ``book``.  This helper rejects non-canonical components first,
    then verifies the resolved path remains under the resolved book root.
    """
    errors: list[str] = []
    expected_root = PurePosixPath("main", "40_course", course_id, "book")
    try:
        relative = PurePosixPath(raw_path)
    except (TypeError, ValueError):
        relative = PurePosixPath("__invalid__")
        errors.append(f"课程 book 路径非法：{raw_path or '缺失'}")

    if (
        not raw_path
        or "\\" in raw_path
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != raw_path
    ):
        errors.append(f"课程 book 路径必须为 canonical POSIX 相对路径：{raw_path or '缺失'}")
    try:
        relative.relative_to(expected_root)
    except ValueError:
        errors.append(
            f"课程持久题源越出 book 域：{raw_path or '缺失'}"
        )

    target = root.joinpath(*relative.parts)
    book_root = root.joinpath(*expected_root.parts)
    if not book_root.is_dir():
        errors.append(f"课程 book 根不存在：{expected_root.as_posix()}")
    else:
        try:
            resolved_book = book_root.resolve(strict=True)
            resolved_target = target.resolve(strict=must_exist)
            resolved_target.relative_to(resolved_book)
        except (OSError, RuntimeError, ValueError):
            errors.append(
                f"课程持久题源解析后越出 book 域或不可解析：{raw_path or '缺失'}"
            )

    current = root
    for part in relative.parts:
        current = current / part
        if (current.exists() or current.is_symlink()) and _is_link_or_reparse(current):
            errors.append(f"课程持久题源路径不得经过链接或 reparse point：{raw_path}")
            break

    if must_exist and not target.is_file():
        errors.append(f"课程持久题源不存在：{raw_path or '缺失'}")
    if errors:
        raise ActivityContractError(list(dict.fromkeys(errors)))
    return target


def _teacher_mapping_table(content: str) -> tuple[list[str], list[list[str]]]:
    heading = rf"^##\s+{re.escape(TEACHER_MAPPING_HEADING)}\s*$"
    matches = list(re.finditer(heading, content, re.MULTILINE))
    if len(matches) != 1:
        raise TeacherContractError(
            [f"overlay 必须且只能有一个“{TEACHER_MAPPING_HEADING}”表"]
        )
    start = matches[0].end()
    next_heading = re.search(r"^##\s+", content[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(content)
    table_lines = [
        line.strip()
        for line in content[start:end].splitlines()
        if line.strip().startswith("|")
    ]
    if len(table_lines) < 3:
        raise TeacherContractError(["课程—教师映射表缺表头、分隔行或数据行"])

    def cells(line: str) -> list[str]:
        return [value.strip() for value in line.strip().strip("|").split("|")]

    headers = cells(table_lines[0])
    separators = cells(table_lines[1])
    if tuple(headers) != TEACHER_MAPPING_COLUMNS:
        raise TeacherContractError(
            [
                "课程—教师映射表列必须精确为："
                + " | ".join(TEACHER_MAPPING_COLUMNS)
            ]
        )
    if (
        len(separators) != len(headers)
        or any(not re.fullmatch(r":?-{3,}:?", value) for value in separators)
    ):
        raise TeacherContractError(["课程—教师映射表分隔行非法"])
    rows = [cells(line) for line in table_lines[2:]]
    if any(len(row) != len(headers) for row in rows):
        raise TeacherContractError(["课程—教师映射表存在列数不匹配的数据行"])
    return headers, rows


def resolve_teacher_mapping(
    root: Path,
    known_course_ids: set[str] | None = None,
    *,
    reader: TextReader = read,
    teacher_paths: Iterable[Path] | None = None,
) -> dict[str, tuple[str, str]]:
    """Resolve the strict, unique course-to-teacher mapping table.

    The template cell is the only place from which a template ID may be
    derived.  Tokens in course names, styles, prose, or duplicate summary
    sections never participate in routing.
    """
    overlay = root / "main/20_teacher/overlay.md"
    if not overlay.is_file():
        raise TeacherContractError(["教师 overlay 不存在"])
    _, rows = _teacher_mapping_table(reader(overlay))
    errors: list[str] = []
    mapping: dict[str, tuple[str, str]] = {}
    for row in rows:
        course_id, _course_name, template_cell, _style = row
        if course_id in mapping:
            errors.append(f"课程—教师映射重复：{course_id}")
            continue
        if course_id != "(默认)" and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]*", course_id
        ):
            errors.append(f"课程—教师映射 course_id 非法：{course_id or '缺失'}")
        template_match = re.fullmatch(
            r"`(main/20_teacher/(T\d{3})\.md)`",
            template_cell,
        )
        if not template_match:
            errors.append(
                "教师模板单元必须精确为 "
                f"`main/20_teacher/Tddd.md`：{course_id} -> "
                f"{template_cell or '缺失'}"
            )
            continue
        template_path, template_id = template_match.groups()
        carrier = root / template_path
        carrier_meta = frontmatter(carrier, reader=reader)
        if (
            not carrier.is_file()
            or carrier_meta.get("type") != "teacher_template"
            or carrier_meta.get("template_id") != template_id
        ):
            errors.append(
                "教师模板载体不存在或 frontmatter 身份不匹配："
                f"{course_id} -> {template_path}"
            )
        mapping[course_id] = (template_id, template_path)

    if "(默认)" not in mapping:
        errors.append("课程—教师映射必须恰有一个 (默认) 行")
    if known_course_ids is not None:
        declared = set(mapping) - {"(默认)"}
        missing = sorted(known_course_ids - declared)
        unknown = sorted(declared - known_course_ids)
        if missing:
            errors.append(f"课程缺显式教师映射：{missing}")
        if unknown:
            errors.append(f"教师映射引用未知课程：{unknown}")

    teacher_root = root / "main/20_teacher"
    if teacher_root.is_dir():
        carriers = (
            sorted(teacher_root.glob("T*.md"))
            if teacher_paths is None
            else sorted(teacher_paths)
        )
        for carrier in carriers:
            match = re.fullmatch(r"(T\d{3})\.md", carrier.name)
            if not match:
                errors.append(f"教师模板文件名非法：{carrier.name}")
                continue
            meta = frontmatter(carrier, reader=reader)
            if (
                meta.get("type") != "teacher_template"
                or meta.get("template_id") != match.group(1)
            ):
                errors.append(f"教师模板自报身份不匹配：{carrier.name}")

    if errors:
        raise TeacherContractError(errors)
    return mapping


@dataclass(frozen=True)
class ActivityRoute:
    course_id: str
    course_type: str
    learning_mode: str | None
    progression_compatibility_source: str
    activity_type: str
    activity_id: str
    activity_position: str
    resume_path: str
    carrier: Path
    progress: Path
    lesson_context_kind: str
    lesson_context_id: str
    lesson_context_path: str
    source_path: str

    @property
    def course_driver(self) -> str:
        """Compatibility projection; never persist this for Project/Praxis."""
        return self.learning_mode or self.course_type

    @property
    def is_textbook_led(self) -> bool:
        return self.course_type == "mastery" and self.learning_mode == "textbook"

    def progression_payload(self) -> dict[str, object]:
        return {
            "course_type": self.course_type,
            "learning_mode": self.learning_mode,
            "progression_kind": "mastery_mode" if self.learning_mode else "course_type",
            "compatibility_source": self.progression_compatibility_source,
        }

    @property
    def lesson_context_label(self) -> str:
        if self.lesson_context_kind == "current":
            return f"{self.lesson_context_id}（当前活动）"
        if self.lesson_context_kind == "historical":
            return f"{self.lesson_context_id}（历史兼容）"
        return "无"

    def relative(self, path: Path) -> str:
        return path.relative_to(ROOT).as_posix()

    def recovery_plan(self) -> dict[str, object]:
        activity_reads = [] if self.activity_type == "none" else [self.resume_path]
        if self.activity_type == "exercise":
            activity_reads.append(
                f"main/40_course/{self.course_id}/exercises/"
                f"{self.activity_id}/problems.md"
            )
            if self.source_path:
                activity_reads.append(self.source_path)
        return {
            "intent": "recover",
            "course_id": self.course_id,
            **self.progression_payload(),
            "current_activity": self.activity_type,
            "current_activity_id": self.activity_id,
            "activity_position": self.activity_position,
            "primary_read": (
                f"main/40_course/{self.course_id}/progress.md"
                if self.activity_type == "none"
                else self.resume_path
            ),
            "activity_read_targets": activity_reads,
            "lesson_context": {
                "kind": self.lesson_context_kind,
                "id": self.lesson_context_id or None,
                "path": self.lesson_context_path or None,
            },
        }

    def close_plan(self) -> dict[str, object]:
        if self.activity_type == "none":
            raise ActivityContractError(["当前没有前台 Activity 可结课"])
        course_root = f"main/40_course/{self.course_id}"
        illustration_root = (
            f"{course_root}/lessons/{self.activity_id}/illustration"
            if self.activity_type == "lesson"
            else f"{course_root}/book/course_materials/supplements"
        )
        return {
            "intent": "close",
            "course_id": self.course_id,
            **self.progression_payload(),
            "current_activity": self.activity_type,
            "current_activity_id": self.activity_id,
            "activity_position": self.activity_position,
            "activity_write_target": self.resume_path,
            "mandatory_write_targets": [
                f"{course_root}/progress.md",
                self.resume_path,
            ],
            "conditional_write_targets": [
                f"{course_root}/question_bank.md",
                f"{course_root}/mistake_bank.md",
            ],
            "illustration_root": illustration_root,
            "lesson_context": {
                "kind": self.lesson_context_kind,
                "id": self.lesson_context_id or None,
                "path": self.lesson_context_path or None,
            },
        }


def resolve_activity(
    root: Path,
    course_id: str,
    snapshot: ProgressSnapshot | None = None,
    *,
    reader: TextReader = read,
    exists: Callable[[Path], bool] | None = None,
) -> ActivityRoute:
    """Validate and resolve an ongoing course's explicit activity pointer."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", course_id):
        raise ActivityContractError([f"course_id 非法：{course_id!r}"])
    course_root = root / "main/40_course" / course_id
    course_path = course_root / "course.md"
    progress = course_root / "progress.md"
    errors: list[str] = []
    is_file = exists or (lambda path: path.is_file())

    if not is_file(progress):
        raise ActivityContractError([f"progress.md 不存在：{course_id}"])
    if not is_file(course_path):
        raise ActivityContractError([f"course.md 不存在：{course_id}"])
    if snapshot is None:
        progress_content = reader(progress)
        snapshot = ProgressSnapshot(
            path=progress,
            content=progress_content,
            meta=frontmatter_text(progress_content),
        )
    elif snapshot.path != progress:
        raise ActivityContractError(
            [f"progress snapshot 路径不匹配：{snapshot.path} != {progress}"]
        )
    meta = snapshot.meta
    validate_progress_identity(meta, course_id)
    if meta.get("lifecycle_status") != "ongoing":
        raise ActivityContractError([f"课程不是 ongoing：{course_id}"])

    required = (
        "current_activity", "current_activity_id", "resume_path",
        "activity_position",
    )
    missing = [field for field in required if not meta.get(field)]
    if missing:
        errors.append(f"ongoing progress 缺显式活动字段：{missing}")

    activity_type = meta.get("current_activity", "")
    activity_id = meta.get("current_activity_id", "")
    course_meta = frontmatter_text(reader(course_path))
    try:
        progression = resolve_course_progression(course_meta, meta)
    except ActivityContractError as exc:
        errors.extend(exc.errors)
        progression = CourseProgression("", None, "invalid")
    resume_path = meta.get("resume_path", "")
    # current_lesson is retired in 0.2.2; if present it is compatibility-only.
    current_lesson = meta.get("current_lesson", "")
    expected_resume = ""
    source_path = ""
    carrier = root / "__invalid_activity__"
    carrier_fields: tuple[str, str, str] | None = None
    if activity_type == "lesson":
        if not re.fullmatch(r"lesson\d+", activity_id):
            errors.append(f"current_activity_id 非法：lesson -> {activity_id or '缺失'}")
        else:
            expected_resume = (
                f"main/40_course/{course_id}/lessons/{activity_id}/{activity_id}.md"
            )
            carrier = root / expected_resume
            carrier_fields = ("lesson", "lesson_id", activity_id)
        if current_lesson and current_lesson not in NO_LESSON and current_lesson != activity_id:
            errors.append(
                "兼容 current_lesson 与显式活动指针不一致："
                f"{current_lesson} != {activity_id or '缺失'}"
            )
    elif activity_type == "exercise":
        # Before E, Udddd remains readable. Once this Course has a ledger,
        # progress itself must already be canonical; aliases are for explicit
        # legacy lookup, never a second physical/current namespace.
        ledger_path = course_root / "activity_ledger.md"
        post_022 = is_file(ledger_path)
        if post_022 and re.fullmatch(r"U\d{4}", activity_id):
            try:
                doc = ledger_contract.parse_ledger_text(reader(ledger_path))
                ledger_errors = doc.validate()
                if ledger_errors:
                    raise ledger_contract.LedgerError("; ".join(ledger_errors))
                canonical = ledger_contract.resolve_legacy_id(
                    course_id, activity_id, doc.aliases
                )
            except ledger_contract.LedgerError as exc:
                errors.append(f"legacy Exercise 无有效 course-scoped alias：{exc}")
            else:
                errors.append(
                    "0.2.2 progress 不得直接路由 legacy Exercise："
                    f"{activity_id} -> {canonical}"
                )
        if not (
            re.fullmatch(r"exercise\d{2,}", activity_id)
            or (not post_022 and re.fullmatch(r"U\d{4}", activity_id))
        ):
            errors.append(f"current_activity_id 非法：exercise -> {activity_id or '缺失'}")
        else:
            expected_resume = (
                f"main/40_course/{course_id}/exercises/{activity_id}/exercise.md"
            )
            carrier = root / expected_resume
            carrier_fields = ("exercise", "exercise_id", activity_id)
            problems = course_root / "exercises" / activity_id / "problems.md"
            problems_meta = (
                frontmatter_text(reader(problems)) if is_file(problems) else {}
            )
            if not is_file(problems):
                errors.append(
                    "当前 Exercise 缺 problems.md："
                    f"main/40_course/{course_id}/exercises/{activity_id}/problems.md"
                )
            elif progression.is_textbook_led:
                source_path = problems_meta.get("source_path", "")
                try:
                    resolve_course_book_path(root, course_id, source_path)
                except ActivityContractError as exc:
                    errors.extend(
                        f"textbook Exercise source_path：{message}"
                        for message in exc.errors
                    )
    elif activity_type == "none":
        if activity_id != "none":
            errors.append("current_activity:none requires current_activity_id:none")
        if resume_path != "none":
            errors.append("current_activity:none requires resume_path:none")
        if meta.get("activity_position") != "between_activities":
            errors.append(
                "current_activity:none requires activity_position:between_activities"
            )
        carrier = progress
    elif activity_type:
        errors.append(f"current_activity 非法：{activity_type}")

    if expected_resume and resume_path != expected_resume:
        errors.append(
            f"resume_path 非 canonical：{resume_path or '缺失'} expected={expected_resume}"
        )
    if activity_type != "none" and resume_path and not is_file(root / resume_path):
        errors.append(f"resume_path 悬空：{resume_path}")

    if carrier_fields and is_file(carrier):
        carrier_type, id_field, expected_id = carrier_fields
        carrier_meta = frontmatter_text(reader(carrier))
        if (
            carrier_meta.get("type") != carrier_type
            or carrier_meta.get("course_id") != course_id
            or carrier_meta.get(id_field) != expected_id
        ):
            errors.append(f"当前活动主载体 frontmatter 不匹配：{resume_path}")
    elif expected_resume and not is_file(carrier):
        errors.append(f"当前活动主载体不存在：{expected_resume}")

    lesson_kind = "none"
    lesson_id = ""
    lesson_path = ""
    if activity_type == "lesson" and re.fullmatch(r"lesson\d+", activity_id):
        lesson_kind = "current"
        lesson_id = activity_id
        lesson_path = expected_resume
    elif activity_type == "exercise" and current_lesson not in NO_LESSON:
        if not re.fullmatch(r"lesson\d+", current_lesson):
            errors.append(
                f"Exercise 兼容 current_lesson 非法：{current_lesson or '缺失'}"
            )
        else:
            historical = (
                course_root / "lessons" / current_lesson / f"{current_lesson}.md"
            )
            historical_meta = frontmatter(historical, reader=reader)
            if (
                not historical.is_file()
                or historical_meta.get("type") != "lesson"
                or historical_meta.get("course_id") != course_id
                or historical_meta.get("lesson_id") != current_lesson
            ):
                errors.append(
                    "Exercise 兼容 current_lesson 悬空或 frontmatter 不匹配："
                    f"{current_lesson}"
                )
            else:
                lesson_kind = "historical"
                lesson_id = current_lesson
                lesson_path = (
                    f"main/40_course/{course_id}/lessons/{current_lesson}/"
                    f"{current_lesson}.md"
                )

    if errors:
        raise ActivityContractError(errors)

    return ActivityRoute(
        course_id=course_id,
        course_type=progression.course_type,
        learning_mode=progression.learning_mode,
        progression_compatibility_source=progression.compatibility_source,
        activity_type=activity_type,
        activity_id=activity_id,
        activity_position=meta.get("activity_position", ""),
        resume_path=resume_path,
        carrier=carrier,
        progress=progress,
        lesson_context_kind=lesson_kind,
        lesson_context_id=lesson_id,
        lesson_context_path=lesson_path,
        source_path=source_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve explicit LearningActivity recovery/close targets."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument(
        "--intent", choices=("recover", "close"), default="recover",
    )
    args = parser.parse_args()
    try:
        route = resolve_activity(ROOT, args.course)
    except ActivityContractError as exc:
        for error in exc.errors:
            print(f"[FAIL] {args.course}: {error}")
        return 1
    payload = (
        route.recovery_plan() if args.intent == "recover" else route.close_plan()
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
