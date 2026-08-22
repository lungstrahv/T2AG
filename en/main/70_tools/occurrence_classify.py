#!/usr/bin/env python3
"""Occurrence-level classification of U1101 / path / current_lesson hits (CR-003)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

PATTERNS = [
    ("U1101_id", re.compile(r"\bU1101\b(?!-Q\d{3})")),
    ("U1101_problem", re.compile(r"\bU1101-Q\d{3}\b")),
    ("path_exercises_U1101", re.compile(r"exercises/U1101")),
    ("current_lesson", re.compile(r"(?m)^current_lesson\s*:")),
    ("activity_status", re.compile(r"(?m)^status\s*:\s*(ongoing|planned|paused|pending_close|completed|closed_incomplete)\s*$")),
]


IMMUTABLE_CLASSES = {
    "immutable_prose",
    "frozen_external_evidence",
    "historical_rule_report",
}


def classify_line(path: str, line: str, kind: str) -> str:
    name = Path(path).name
    if kind in {"U1101_id", "U1101_problem", "path_exercises_U1101"}:
        targets = re.findall(r"\[[^\]]*\]\(([^)]*)\)", line)
        if any("U1101" in target or "exercises/U1101" in target for target in targets):
            return "markdown_link_target"
        if path.endswith("activity_map.md") and "|" in line:
            return "active_index_table"
        if re.match(
            r"^\s*(exercise_id|current_activity_id|next_activity_id|problem_ids|"
            r"resume_path|source_order|teaching_sequence|exercise_ids)\s*:",
            line,
        ):
            return "active_machine_field"
        if (
            re.match(r"^##\s+U\d{4}-Q\d{3}\s*$", line)
            and (
                name in {"problems.md", "attempt.md"}
                or bool(re.fullmatch(r"RV\d{4}\.md", name))
                or "/book/primary/verified_excerpts/" in f"/{path}"
            )
        ):
            return "active_index_table"
        if name == "problems.md" and re.match(
            r"^-\s*题号：\s*U\d{4}-Q\d{3}\s*$", line
        ):
            return "active_index_table"
        if name == "exercise.md" and re.match(
            r"^-\s*当前题目[：:]\s*U\d{4}-Q\d{3}\s*$", line
        ):
            return "active_human_pointer"
        if name in {
            "t2ag_memory.md",
            "plan.md",
            "learning_path.md",
            "course.md",
            "course_reflections.md",
            "exercise_thoughts.md",
        } and ("exercises/U1101" in line or re.search(r"\bexercise:\s*U1101\b", line)):
            return "active_human_pointer"
        if name.endswith(".md") and (path.startswith("main/60_journal") or "changelog" in path or "problemlog" in path):
            return "historical_rule_report"
        return "immutable_prose"
    if kind == "current_lesson":
        return "active_machine_field"
    if kind == "activity_status":
        if name in {"exercise.md"} or re.fullmatch(r"lesson\d+\.md", name or ""):
            return "active_machine_field"
        return "immutable_prose"  # Attempt/Review/Problem own status
    return "immutable_prose"


def scan_documents(documents: dict[str, str]) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for rel, text in sorted(documents.items()):
        for i, line in enumerate(text.splitlines(), start=1):
            for kind, pat in PATTERNS:
                for ordinal, match in enumerate(pat.finditer(line), start=1):
                    klass = classify_line(rel, line, kind)
                    occurrence_seed = f"{rel}\0{i}\0{kind}\0{match.start()}\0{ordinal}"
                    hits.append(
                        {
                            "occurrence_id": "OCC-" + hashlib.sha256(
                                occurrence_seed.encode("utf-8")
                            ).hexdigest()[:16],
                            "path": rel,
                            "line": i,
                            "column": match.start() + 1,
                            "kind": kind,
                            "class": klass,
                            "active": klass not in IMMUTABLE_CLASSES,
                            "match": match.group(0),
                            "excerpt": line[:240],
                        }
                    )
    by_class: dict[str, int] = {}
    for hit in hits:
        by_class[hit["class"]] = by_class.get(hit["class"], 0) + 1
    active = [hit for hit in hits if hit["active"]]
    return {
        "files_scanned": len(documents),
        "occurrence_count": len(hits),
        "active_occurrence_count": len(active),
        "active_file_count": len({hit["path"] for hit in active}),
        "by_class": by_class,
        "hits": hits,
    }


def scan_root(root: Path) -> dict[str, Any]:
    roots = [
        root / "main/40_course",
        root / "main/10_student",
        root / "main/30_group",
        root / "main/00_core/t2ag_memory.md",
    ]
    files: list[Path] = []
    for r in roots:
        if r.is_file():
            files.append(r)
        elif r.is_dir():
            files.extend(p for p in r.rglob("*.md") if p.is_file())
    documents: dict[str, str] = {}
    for path in sorted(files):
        rel = path.relative_to(root).as_posix()
        try:
            documents[rel] = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
    return scan_documents(documents)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()
    report = scan_root(args.root.resolve())
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_bytes((text + "\n").encode("utf-8"))
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
