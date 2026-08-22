#!/usr/bin/env python3
"""Build deterministic machine sections for the journal indexes.

The command is read-only by default. Use --write to update the two generated
blocks after adding or changing a journal entry.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import re
import sys
import tempfile


MAIN_DIR = Path(__file__).resolve().parents[1]
JOURNAL_DIR = MAIN_DIR / "60_journal"
INDEX_PATH = JOURNAL_DIR / "INDEX.md"

INDEX_BLOCK = "JOURNAL_INDEX"
MONTH_BLOCK = "JOURNAL_MONTH_LIST"
MONTH_FILE_RE = re.compile(r"^\d{4}-\d{2}\.md$")
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
H1_RE = re.compile(r"^#\s+(.+?)\s*$")
PLAIN_METADATA_RE = re.compile(
    r"^\s*(?:>\s*)?"
    r"(?P<key>日期|创建日期|创建|状态|date|created|created_at|status)"
    r"\s*[：:]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class JournalRecord:
    path: Path
    title: str
    entry_date: str
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check or write generated journal index blocks."
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check",
        action="store_true",
        help="check for drift without writing (default)",
    )
    action.add_argument(
        "--write",
        action="store_true",
        help="rewrite generated blocks atomically",
    )
    parser.add_argument(
        "--month",
        help="month to build as YYYY-MM (default: current calendar month)",
    )
    args = parser.parse_args()
    if args.month and not MONTH_RE.fullmatch(args.month):
        parser.error("--month must use YYYY-MM")
    return args


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return text, newline


def normalize_key(value: str) -> str:
    key = value.strip().rstrip("：:").strip().lower()
    aliases = {
        "日期": "date",
        "创建日期": "date",
        "创建": "date",
        "created": "date",
        "created_at": "date",
        "状态": "status",
        "journal_index": "journal_index",
        "redirect_to": "redirect_to",
        "redirect": "redirect_to",
    }
    return aliases.get(key, key)


def parse_metadata(lines: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}

    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            normalized = normalize_key(key)
            raw_value = value.strip().strip("\"'")
            if normalized in {"date", "status", "journal_index", "redirect_to"} and raw_value:
                metadata.setdefault(normalized, raw_value)

    for line in lines[:80]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break

        candidate = stripped
        if candidate.startswith(">"):
            candidate = candidate[1:].strip()

        if candidate.startswith("**") and "**" in candidate[2:]:
            closing = candidate.find("**", 2)
            key = normalize_key(candidate[2:closing])
            value = candidate[closing + 2 :].lstrip("：: ").strip()
            if key in {"date", "status", "journal_index", "redirect_to"} and value:
                metadata.setdefault(key, value)
                continue

        match = PLAIN_METADATA_RE.match(line)
        if match:
            key = normalize_key(match.group("key"))
            metadata.setdefault(key, match.group("value").strip())

    return metadata


def journal_index_excluded(path: Path) -> bool:
    """True when metadata opts the file out of generated journal indexes.

    Recognizes frontmatter ``journal_index: false`` and blockquote/bold forms.
    Generic: not hard-coded to any single filename.
    """
    try:
        text, _ = read_text(path)
    except OSError:
        return False
    metadata = parse_metadata(text.splitlines())
    flag = str(metadata.get("journal_index", "")).strip().lower()
    return flag in {"false", "0", "no", "off"}


def first_h1(lines: list[str], fallback: str) -> str:
    for line in lines:
        match = H1_RE.match(line.lstrip("\ufeff"))
        if match:
            title = match.group(1).strip()
            title = re.sub(
                r"^\d{4}-\d{2}-\d{2}(?:\s*[-—:：]\s*|\s+)",
                "",
                title,
            ).strip()
            return title or fallback
    return fallback


def preamble_date(lines: list[str]) -> str:
    """Legacy fallback: first ISO date before the first level-two heading."""
    for line in lines[:80]:
        if line.strip().startswith("## "):
            break
        match = ISO_DATE_RE.search(line)
        if match:
            return match.group(1)
    return ""


def parse_record(path: Path) -> JournalRecord:
    text, _ = read_text(path)
    lines = text.splitlines()
    metadata = parse_metadata(lines)
    title = first_h1(lines, path.stem)

    entry_date = ""
    if metadata.get("date"):
        match = ISO_DATE_RE.search(metadata["date"])
        if match:
            entry_date = match.group(1)
    if not entry_date:
        match = ISO_DATE_RE.match(path.name)
        if match:
            entry_date = match.group(1)
    if not entry_date:
        heading = next(
            (
                line.lstrip("\ufeff")[2:].strip()
                for line in lines
                if line.lstrip("\ufeff").startswith("# ")
            ),
            "",
        )
        match = ISO_DATE_RE.match(heading)
        if match:
            entry_date = match.group(1)
    if not entry_date:
        entry_date = preamble_date(lines)

    status = metadata.get("status", "—").strip() or "—"
    return JournalRecord(
        path=path,
        title=title,
        entry_date=entry_date or "—",
        status=status,
    )


def escape_cell(value: str) -> str:
    return " ".join(value.replace("|", r"\|").splitlines()).strip()


def markdown_link(path: Path) -> str:
    name = escape_cell(path.name)
    return f"[{name}]({path.name})"


def journal_records() -> list[JournalRecord]:
    paths = [
        path
        for path in JOURNAL_DIR.glob("*.md")
        if path.name != INDEX_PATH.name
        and not MONTH_FILE_RE.fullmatch(path.name)
        and not journal_index_excluded(path)
    ]
    records = [parse_record(path) for path in paths]
    return sorted(
        records,
        key=lambda item: (
            item.entry_date == "—",
            item.entry_date,
            item.path.name.casefold(),
        ),
    )


def month_files() -> list[Path]:
    return sorted(
        (
            path
            for path in JOURNAL_DIR.glob("*.md")
            if MONTH_FILE_RE.fullmatch(path.name)
        ),
        key=lambda path: path.name,
    )


def render_index_body(records: list[JournalRecord]) -> str:
    lines = [
        "<!-- 由 main/70_tools/build_journal_index.py 生成；请勿手工编辑本块。 -->",
        "",
        "## 月度索引",
        "",
        "| 月份 | 文件 | 标题 |",
        "|---|---|---|",
    ]
    for path in month_files():
        text, _ = read_text(path)
        title = first_h1(text.splitlines(), path.stem)
        lines.append(
            f"| {path.stem} | {markdown_link(path)} | {escape_cell(title)} |"
        )

    lines.extend(
        [
            "",
            "## Journal 文件",
            "",
            "| 日期 | 文件 | 标题 | 状态 |",
            "|---|---|---|---|",
        ]
    )
    for record in records:
        lines.append(
            "| "
            + " | ".join(
                (
                    escape_cell(record.entry_date),
                    markdown_link(record.path),
                    escape_cell(record.title),
                    escape_cell(record.status),
                )
            )
            + " |"
        )
    return "\n".join(lines)


def render_month_body(records: list[JournalRecord], month: str) -> str:
    lines = [
        "<!-- 由 main/70_tools/build_journal_index.py 生成；请勿手工编辑本块。 -->",
        "",
        "## Journal 列表",
        "",
        "| 日期 | 文件 | 主题 | 状态 |",
        "|---|---|---|---|",
    ]
    for record in records:
        if record.entry_date.startswith(f"{month}-"):
            lines.append(
                "| "
                + " | ".join(
                    (
                        escape_cell(record.entry_date),
                        markdown_link(record.path),
                        escape_cell(record.title),
                        escape_cell(record.status),
                    )
                )
                + " |"
            )
    return "\n".join(lines)


def replace_generated_block(
    text: str,
    newline: str,
    block_name: str,
    body: str,
) -> str:
    start = f"<!-- T2AG_GENERATED:{block_name}:START -->"
    end = f"<!-- T2AG_GENERATED:{block_name}:END -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(
            f"expected exactly one {block_name} generated block "
            f"(found START={text.count(start)}, END={text.count(end)})"
        )
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    generated = newline.join(
        (start, body.replace("\n", newline).rstrip("\r\n"), end)
    )
    return before + generated + after


def atomic_write(path: Path, content: str) -> None:
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def build_target(path: Path, block_name: str, body: str) -> tuple[str, str]:
    original, newline = read_text(path)
    expected = replace_generated_block(original, newline, block_name, body)
    return original, expected


def main() -> int:
    args = parse_args()
    month = args.month or date.today().strftime("%Y-%m")
    month_path = JOURNAL_DIR / f"{month}.md"
    if not month_path.is_file():
        print(
            f"ERROR: current month file is missing: {month_path}",
            file=sys.stderr,
        )
        return 2

    records = journal_records()
    try:
        targets = [
            (
                INDEX_PATH,
                *build_target(
                    INDEX_PATH,
                    INDEX_BLOCK,
                    render_index_body(records),
                ),
            ),
            (
                month_path,
                *build_target(
                    month_path,
                    MONTH_BLOCK,
                    render_month_body(records, month),
                ),
            ),
        ]
    except (OSError, UnicodeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    drifted = [path for path, original, expected in targets if original != expected]
    if args.write:
        for path, original, expected in targets:
            if original != expected:
                atomic_write(path, expected)
                print(f"updated: {path.relative_to(MAIN_DIR)}")
            else:
                print(f"unchanged: {path.relative_to(MAIN_DIR)}")
        return 0

    if drifted:
        for path in drifted:
            print(f"DRIFT: {path.relative_to(MAIN_DIR)}")
        print(
            "Run build_journal_index.py --write, then re-run --check.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: journal index blocks are current for {month}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
