#!/usr/bin/env python3
"""Read-only planner for the 0.2.4 Course Progression field migration.

The tool intentionally has no write/apply flag.  Real Course mutation is an
RT3 operation and must be implemented or enabled only after the user sees and
approves this exact before/after package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from t2ag_activity import ActivityContractError, frontmatter_text, resolve_course_progression


ROOT = Path(__file__).resolve().parents[2]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def set_frontmatter_field(text: str, field: str, value: str | None) -> str:
    """Set or remove one top-level frontmatter field without touching the body.

    The edit is line-structural and byte-conservative: the frontmatter block is
    split on line boundaries, exactly one line is replaced, deleted, or appended,
    and every other byte (including each line's original CR, if any) is carried
    through verbatim.  Only the first matching key is touched, preserving the
    ``count=1`` semantics of the earlier regex implementation.
    """
    match = re.match(r"\A---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        raise ValueError("missing frontmatter")
    body = match.group(1)
    lines = body.split("\n")
    eol = "\r" if lines[-1].endswith("\r") else ""
    idx = next(
        (
            i
            for i, line in enumerate(lines)
            if line.rstrip("\r").startswith(f"{field}:")
        ),
        None,
    )
    if value is None:
        if idx is not None:
            del lines[idx]
    elif idx is not None:
        lines[idx] = f"{field}: {value}" + ("\r" if lines[idx].endswith("\r") else "")
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines.append(f"{field}: {value}" + eol)
    return text[: match.start(1)] + "\n".join(lines) + text[match.end(1) :]


def planned_text(
    text: str,
    *,
    course_type: str,
    learning_mode: str | None,
    is_course: bool,
) -> str:
    result = text
    result = set_frontmatter_field(result, "learning_mode", learning_mode)
    result = set_frontmatter_field(
        result,
        "default_driver" if is_course else "course_driver",
        None,
    )
    return result


def plan(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    courses = root / "main/40_course"
    for folder in sorted(
        path for path in courses.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    ):
        course_path = folder / "course.md"
        progress_path = folder / "progress.md"
        if not course_path.is_file() or not progress_path.is_file():
            continue
        course_text = course_path.read_text(encoding="utf-8-sig")
        progress_text = progress_path.read_text(encoding="utf-8-sig")
        course_meta = frontmatter_text(course_text)
        progress_meta = frontmatter_text(progress_text)
        try:
            progression = resolve_course_progression(course_meta, progress_meta)
        except ActivityContractError as exc:
            raise ValueError(f"{folder.name}: {'; '.join(exc.errors)}") from exc
        new_course = planned_text(
            course_text,
            course_type=progression.course_type,
            learning_mode=progression.learning_mode,
            is_course=True,
        )
        new_progress = planned_text(
            progress_text,
            course_type=progression.course_type,
            learning_mode=progression.learning_mode,
            is_course=False,
        )
        rows.append(
            {
                "course_id": folder.name,
                "before": {
                    "course_type": course_meta.get("course_type"),
                    "default_driver": course_meta.get("default_driver"),
                    "course_driver": progress_meta.get("course_driver"),
                    "learning_mode_course": course_meta.get("learning_mode"),
                    "learning_mode_progress": progress_meta.get("learning_mode"),
                    "course_sha256": sha256_text(course_text),
                    "progress_sha256": sha256_text(progress_text),
                },
                "after": {
                    "course_type": progression.course_type,
                    "learning_mode_course": progression.learning_mode,
                    "learning_mode_progress": progression.learning_mode,
                    "default_driver": None,
                    "course_driver": None,
                    "course_sha256": sha256_text(new_course),
                    "progress_sha256": sha256_text(new_progress),
                },
                "progression_kind": (
                    "mastery_mode" if progression.learning_mode else "course_type"
                ),
                "compatibility_source": progression.compatibility_source,
                "changed": new_course != course_text or new_progress != progress_text,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--expect-courses", type=int, default=8)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        rows = plan(root)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    if len(rows) != args.expect_courses:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "course count mismatch",
                    "expected": args.expect_courses,
                    "actual": len(rows),
                    "courses": [row["course_id"] for row in rows],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "schema": "t2ag.course_progression_migration_plan.v1",
                "mode": "read_only",
                "writes_performed": 0,
                "course_count": len(rows),
                "courses": rows,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
