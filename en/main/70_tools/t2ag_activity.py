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
# LV-5 (2026-08-20): the overlay ships in translated editions, so the mapping table's
# heading, columns and default-row marker each have one canonical identity plus the
# spellings other editions use. Recognising only zh-CN would make a correctly-built
# English overlay report "the mapping table is missing" -- the table is there and the
# parser is blind.
TEACHER_MAPPING_HEADING = "课程—教师映射"
TEACHER_MAPPING_HEADINGS = (TEACHER_MAPPING_HEADING, "Course-to-teacher mapping")
TEACHER_MAPPING_COLUMNS = ("课程代码", "课程名称", "教师模板", "教师风格")
TEACHER_MAPPING_COLUMNS_EN = ("Course code", "Course name", "Teacher template", "Teacher style")
TEACHER_MAPPING_COLUMN_SETS = (TEACHER_MAPPING_COLUMNS, TEACHER_MAPPING_COLUMNS_EN)
DEFAULT_ROW_KEYS = ("(默认)", "(default)")


def is_default_row(course_id: str) -> bool:
    """True when this mapping row is the catch-all default, in any edition."""
    return course_id.strip().lower() in {k.lower() for k in DEFAULT_ROW_KEYS}


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
    alternatives = "|".join(re.escape(h) for h in TEACHER_MAPPING_HEADINGS)
    heading = rf"^##\s+(?:{alternatives})\s*$"
    matches = list(re.finditer(heading, content, re.MULTILINE))
    if len(matches) != 1:
        raise TeacherContractError(
            [f"the overlay must contain exactly one '{TEACHER_MAPPING_HEADING}' table"]
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
        raise TeacherContractError(
            ["the course-to-teacher mapping table lacks a header, separator or data row"]
        )

    def cells(line: str) -> list[str]:
        return [value.strip() for value in line.strip().strip("|").split("|")]

    headers = cells(table_lines[0])
    separators = cells(table_lines[1])
    if tuple(headers) not in TEACHER_MAPPING_COLUMN_SETS:
        raise TeacherContractError(
            [
                "the course-to-teacher mapping columns must be exactly: "
                + " | ".join(TEACHER_MAPPING_COLUMNS)
                + "  (or, in a translated edition: "
                + " | ".join(TEACHER_MAPPING_COLUMNS_EN)
                + ")"
            ]
        )
    if (
        len(separators) != len(headers)
        or any(not re.fullmatch(r":?-{3,}:?", value) for value in separators)
    ):
        raise TeacherContractError(
            ["the course-to-teacher mapping separator row is invalid"]
        )
    rows = [cells(line) for line in table_lines[2:]]
    if any(len(row) != len(headers) for row in rows):
        raise TeacherContractError(
            ["the course-to-teacher mapping has a data row with a mismatched column count"]
        )
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
        raise TeacherContractError(["the teacher overlay does not exist"])
    _, rows = _teacher_mapping_table(reader(overlay))
    errors: list[str] = []
    mapping: dict[str, tuple[str, str]] = {}
    for row in rows:
        course_id, _course_name, template_cell, _style = row
        if course_id in mapping:
            errors.append(f"duplicate course-to-teacher mapping: {course_id}")
            continue
        if not is_default_row(course_id) and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]*", course_id
        ):
            errors.append(f"course-to-teacher mapping course_id is invalid: {course_id or 'missing'}")
        template_match = re.fullmatch(
            r"`(main/20_teacher/(T\d{3})\.md)`",
            template_cell,
        )
        if not template_match:
            errors.append(
                "the teacher template cell must be exactly "
                f"`main/20_teacher/Tddd.md`：{course_id} -> "
                f"{template_cell or 'missing'}"
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
                "the teacher template carrier does not exist, or its frontmatter identity does not match: "
                f"{course_id} -> {template_path}"
            )
        mapping[course_id] = (template_id, template_path)

    if not any(is_default_row(key) for key in mapping):
        errors.append(
            "the course-to-teacher mapping must have exactly one default row "
            f"({' / '.join(DEFAULT_ROW_KEYS)})"
        )
    if known_course_ids is not None:
        declared = {k for k in mapping if not is_default_row(k)}
        missing = sorted(known_course_ids - declared)
        unknown = sorted(declared - known_course_ids)
        if missing:
            errors.append(f"course lacks an explicit teacher mapping: {missing}")
        if unknown:
            errors.append(f"teacher mapping references an unknown course: {unknown}")

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
                errors.append(f"teacher template filename is invalid: {carrier.name}")
                continue
            meta = frontmatter(carrier, reader=reader)
            if (
                meta.get("type") != "teacher_template"
                or meta.get("template_id") != match.group(1)
            ):
                errors.append(f"teacher template self-declared identity does not match: {carrier.name}")

    if errors:
        raise TeacherContractError(errors)
    return mapping


@dataclass(frozen=True)
class ActivityRoute:
    course_id: str
    course_driver: str
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
            "course_driver": self.course_driver,
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
            raise ActivityContractError(["there is no foreground Activity to close"])
        course_root = f"main/40_course/{self.course_id}"
        illustration_root = (
            f"{course_root}/lessons/{self.activity_id}/illustration"
            if self.activity_type == "lesson"
            else f"{course_root}/book/course_materials/supplements"
        )
        return {
            "intent": "close",
            "course_id": self.course_id,
            "course_driver": self.course_driver,
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
        raise ActivityContractError([f"course_id is invalid: {course_id!r}"])
    course_root = root / "main/40_course" / course_id
    progress = course_root / "progress.md"
    errors: list[str] = []
    is_file = exists or (lambda path: path.is_file())

    if not is_file(progress):
        raise ActivityContractError([f"progress.md 不存在：{course_id}"])
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
        errors.append(f"ongoing progress lacks explicit activity fields: {missing}")

    activity_type = meta.get("current_activity", "")
    activity_id = meta.get("current_activity_id", "")
    course_driver = meta.get("course_driver", "")
    resume_path = meta.get("resume_path", "")
    # current_lesson is retired in 0.2.2; if present it is compatibility-only.
    current_lesson = meta.get("current_lesson", "")
    expected_resume = ""
    source_path = ""
    carrier = root / "__invalid_activity__"
    carrier_fields: tuple[str, str, str] | None = None
    if course_driver not in {"textbook", "goal", "project", "praxis"}:
        errors.append(f"course_driver 非法：{course_driver or '缺失'}")

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
                "compatibility current_lesson disagrees with the explicit activity pointer: "
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
                    "0.2.2 progress must not route a legacy Exercise directly: "
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
            elif course_driver == "textbook":
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
            f"resume_path is not canonical: {resume_path or 'missing'} expected={expected_resume}"
        )
    if activity_type != "none" and resume_path and not is_file(root / resume_path):
        errors.append(f"resume_path is dangling: {resume_path}")

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
                f"Exercise compatibility current_lesson is invalid: {current_lesson or 'missing'}"
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
                    "Exercise compatibility current_lesson is dangling or its frontmatter does not match: "
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
        course_driver=course_driver,
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
