#!/usr/bin/env python3
"""Build an ephemeral, exact-excerpt context packet for one learning session.

The packet is a read-only projection.  It never writes a cache and never owns
state.  Activity and teacher routing consume the same byte-backed SourceCache
as excerpt selection; every file and directory listing observed during the
build is checked again before output so a mixed-version packet is rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import activity_close
import activity_ledger
import t2ag_doctor as doctor  # LV-5: MARKER_VARIANTS is the one spelling list
from t2ag_activity import (
    ActivityContractError,
    ProgressSnapshot,
    TeacherContractError,
    frontmatter_text,
    resolve_activity,
    resolve_teacher_mapping,
)


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"
DEFAULT_SOFT_CHAR_BUDGET = 16_000
CRITICAL_MAX_CHARS = 12_000
CRITICAL_EXCERPT_CHARS = 1_200
PLACEHOLDER_RE = re.compile(
    r"<(?:required|confirm|confirm-or-none|off\s*\|\s*suggest\s*\|\s*auto)>"
    r"|[（(]待填写[）)]",
    re.IGNORECASE,
)
COURSE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
PROBLEM_ID_RE = re.compile(r"(?:U\d{4}|exercise\d{2,})-Q\d{3}")
NEXT_ACTION_KINDS = frozenset(
    {"confirm_close", "resume", "choose_activity", "start_activity", "none"}
)


class ContextPacketError(ValueError):
    """The packet cannot be built without guessing or mixing source states."""


class SourceCache:
    """Read bytes once and reject file or directory changes before output."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._raw: dict[Path, bytes] = {}
        self._content: dict[Path, str] = {}
        self._directory_entries: dict[
            tuple[Path, str],
            tuple[Path, ...],
        ] = {}

    def _checked(self, path: Path) -> Path:
        candidate = path.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ContextPacketError(f"source escapes repository root: {path}") from exc
        return candidate

    def read_bytes(self, path: Path, *, required: bool = True) -> bytes:
        checked = self._checked(path)
        if checked in self._raw:
            return self._raw[checked]
        if not checked.is_file():
            if required:
                raise ContextPacketError(
                    f"required context source missing: {self.relative(checked)}"
                )
            return b""
        try:
            raw = checked.read_bytes()
        except OSError as exc:
            raise ContextPacketError(
                f"cannot read context source: {self.relative(checked)}"
            ) from exc
        self._raw[checked] = raw
        return raw

    def read(self, path: Path, *, required: bool = True) -> str:
        checked = self._checked(path)
        if checked in self._content:
            return self._content[checked]
        raw = self.read_bytes(checked, required=required)
        if not raw and not checked.is_file() and not required:
            return ""
        content = (
            raw.decode("utf-8-sig", errors="replace")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
        self._content[checked] = content
        return content

    def glob(self, directory: Path, pattern: str) -> list[Path]:
        checked = self._checked(directory)
        key = (checked, pattern)
        if key not in self._directory_entries:
            entries = tuple(
                sorted(
                    (
                        self._checked(path)
                        for path in checked.glob(pattern)
                        if path.is_file()
                    ),
                    key=lambda path: path.as_posix(),
                )
            )
            self._directory_entries[key] = entries
        return list(self._directory_entries[key])

    def relative(self, path: Path) -> str:
        return self._checked(path).relative_to(self.root).as_posix()

    def digest(self, path: Path) -> str:
        return hashlib.sha256(self.read_bytes(path)).hexdigest()

    def assert_unchanged(self) -> None:
        changed: list[str] = []
        for path, before in self._raw.items():
            try:
                after = path.read_bytes()
            except OSError:
                changed.append(self.relative(path))
                continue
            if after != before:
                changed.append(self.relative(path))
        for (directory, pattern), before in self._directory_entries.items():
            after = tuple(
                sorted(
                    (
                        self._checked(path)
                        for path in directory.glob(pattern)
                        if path.is_file()
                    ),
                    key=lambda path: path.as_posix(),
                )
            )
            if after != before:
                changed.append(f"{self.relative(directory)}/{pattern}")
        if changed:
            raise ContextPacketError(
                "context sources changed during packet build; rerun: "
                + ", ".join(sorted(changed))
            )


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    start: int
    body_start: int
    end: int


@dataclass(frozen=True)
class Selection:
    source: str
    label: str
    content: str
    sha256: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "label": self.label,
            "sha256": self.sha256,
            "content": self.content,
        }


def headings(content: str) -> list[Heading]:
    matches = list(re.finditer(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", content, re.MULTILINE))
    result: list[Heading] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        end = len(content)
        for later in matches[index + 1 :]:
            if len(later.group(1)) <= level:
                end = later.start()
                break
        body_start = match.end()
        if body_start < len(content) and content[body_start] == "\n":
            body_start += 1
        result.append(
            Heading(
                level=level,
                title=match.group(2).strip(),
                start=match.start(),
                body_start=body_start,
                end=end,
            )
        )
    return result


def raw_frontmatter(content: str) -> str:
    match = re.match(r"^---\s*\n.*?\n---\s*(?:\n|$)", content, re.DOTALL)
    return match.group(0).strip() if match else ""


def section(
    content: str,
    title: str,
    *,
    level: int | None = None,
    prefix: bool = False,
    required: bool = True,
) -> str:
    found = [
        item
        for item in headings(content)
        if (level is None or item.level == level)
        and (
            item.title.startswith(title)
            if prefix
            else item.title == title
        )
    ]
    if len(found) != 1:
        if required:
            raise ContextPacketError(
                f"expected one heading {title!r}, found {len(found)}"
            )
        return ""
    item = found[0]
    return content[item.start : item.end].strip()


def section_any(
    content: str,
    title: str,
    *,
    level: int | None = None,
    required: bool = True,
) -> str:
    """`section`, tried against every registered spelling of `title`.

    LV-5: memory section headings are prose and are translated per edition, while
    the reader here named one spelling. Renaming `## 上次课摘要` to
    `## Last session summary` in the English memory file silently made
    `has_active_progress` return False — the state was there and the reader was
    blind, the same carrier_mismatch family this registry exists to close.
    """
    for spelling in doctor.marker_spellings(title):
        found = section(content, spelling, level=level, required=False)
        if found:
            return found
    if required:
        raise ContextPacketError(
            f"expected one heading {title!r} in any registered edition, found none"
        )
    return ""


def sections_by_prefix(
    content: str,
    prefix: str,
    *,
    level: int | None = None,
) -> list[str]:
    return [
        content[item.start : item.end].strip()
        for item in headings(content)
        if (level is None or item.level == level) and item.title.startswith(prefix)
    ]


def join_exact(parts: Iterable[str]) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def markdown_table_row(content: str, first_cell: str) -> str:
    pattern = re.compile(
        rf"^\|\s*{re.escape(first_cell)}\s*\|.*\|\s*$",
        re.MULTILINE,
    )
    matches = pattern.findall(content)
    if len(matches) != 1:
        raise ContextPacketError(
            f"expected one table row for {first_cell!r}, found {len(matches)}"
        )
    return matches[0].strip()


def markdown_table_cells(row: str) -> list[str]:
    return [cell.strip().strip("`") for cell in row.strip().strip("|").split("|")]


def group_course_ids(group_row: str) -> set[str]:
    cells = markdown_table_cells(group_row)
    if len(cells) < 5:
        raise ContextPacketError("the learning_path course-group index row has too few columns")
    return set(re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", cells[2]))


def memory_value(memory: str, label: str) -> str:
    row = markdown_table_row(memory, label)
    cells = markdown_table_cells(row)
    if len(cells) < 2 or not cells[1] or cells[1] == "—":
        raise ContextPacketError(f"memory pointer missing: {label}")
    return cells[1]


def initialized(profile: str, memory: str) -> bool:
    meta = frontmatter_text(profile)
    if meta.get("initialization_status") != "initialized":
        return False
    if meta.get("exercise_hint_gate") not in {"enabled", "disabled"}:
        return False
    if PLACEHOLDER_RE.search(profile):
        return False
    summary = section_any(memory, "上次课摘要", level=2, required=False)
    return bool(summary) and not re.search(r"\*\*日期\*\*[：:]\s*—", summary)


def build_snapshot_id(
    cache: SourceCache,
    course_id: str,
    sources: dict[str, Path],
) -> str:
    """Bind a handoff to one course and one byte-identical critical source set."""
    material = {
        "course_id": course_id,
        "source_sha256": {
            name: cache.digest(path)
            for name, path in sorted(sources.items())
        },
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"CTX-{course_id}-{hashlib.sha256(encoded).hexdigest()}"


def public_source_sha256(
    cache: SourceCache,
    *,
    progress_path: Path | None,
    activity_path: Path | None,
    profile_path: Path,
    overlay_path: Path | None,
) -> dict[str, str | None]:
    return {
        "progress": cache.digest(progress_path) if progress_path else None,
        "activity": cache.digest(activity_path) if activity_path else None,
        "profile": cache.digest(profile_path),
        "teacher_overlay": cache.digest(overlay_path) if overlay_path else None,
    }


def progress_next_action(meta: dict[str, str]) -> dict[str, str]:
    result = {
        "next_action_kind": meta.get("next_action_kind", "").strip(),
        "next_activity_type": meta.get("next_activity_type", "").strip(),
        "next_activity_id": meta.get("next_activity_id", "").strip(),
    }
    if result["next_action_kind"] not in NEXT_ACTION_KINDS:
        raise ContextPacketError(
            "progress 缺合法 next_action_kind："
            f"{result['next_action_kind'] or '缺失'}"
        )
    if not result["next_activity_type"] or not result["next_activity_id"]:
        raise ContextPacketError("progress lacks next_activity_type / next_activity_id")
    return result


def load_ledger_route(
    cache: SourceCache,
    main: Path,
    course_id: str,
    route: object,
    progress_meta: dict[str, str],
) -> tuple[Path, activity_ledger.LedgerDocument, dict[str, str]]:
    """Validate ledger replay and bind progress next_action to that replay."""
    ledger_path = main / "40_course" / course_id / "activity_ledger.md"
    document = activity_ledger.parse_ledger_text(
        cache.read(ledger_path),
        path=ledger_path,
    )
    errors = document.validate()
    if errors:
        raise ContextPacketError("activity ledger invalid: " + "; ".join(errors))
    try:
        index = document.rebuild_index()
    except activity_ledger.LedgerError as exc:
        raise ContextPacketError(f"activity ledger replay failed: {exc}") from exc

    actual = progress_next_action(progress_meta)
    if route.activity_type != "none":
        key = f"{route.activity_type}:{route.activity_id}"
        entry = index.get(key)
        if entry is None:
            raise ContextPacketError(f"the activity ledger lacks the current activity: {key}")
        expected = activity_ledger.resolve_next_action(
            current_activity_type=route.activity_type,
            current_activity_id=route.activity_id,
            current_state=entry.state,
            index=index,
        )
        if actual != expected:
            raise ContextPacketError(
                "progress next_action 与 activity ledger replay 冲突："
                f"progress={actual} ledger={expected}"
            )
    return ledger_path, document, actual


def exact_excerpt(content: str, limit: int = CRITICAL_EXCERPT_CHARS) -> str:
    """Return a bounded exact prefix, preferring a paragraph boundary."""
    text = content.strip()
    if len(text) <= limit:
        return text
    boundary = text.rfind("\n\n", 0, limit)
    if boundary < limit // 2:
        boundary = limit
    return text[:boundary].rstrip()


def problem_statement(problem: str) -> str:
    lines = problem.splitlines()
    selected: list[str] = []
    collecting = False
    for raw in lines:
        if not collecting:
            # LV-5: the label is spelled per edition; resolve through the registry.
            match = re.match(
                rf"^-\s*(?:{doctor.marker_alternation('题面')})[：:]\s*(.*)$", raw.strip()
            )
            if match:
                collecting = True
                selected.append(match.group(1).rstrip())
            continue
        # LV-5: this is the answer-leak guard -- every edition's spelling of these four
        # labels must stop the collection, or a translated problems.md would leak the
        # solution into the packet.
        leak_labels = "|".join(
            doctor.marker_alternation(label) for label in ("提示", "答案", "解答", "讲解")
        )
        if re.match(r"^#{1,6}\s+", raw) or re.match(
            rf"^-\s*(?:{leak_labels})[：:]", raw.strip()
        ):
            break
        selected.append(raw.rstrip())
    result = "\n".join(selected).strip()
    if not result:
        raise ContextPacketError("the current Exercise has no problem statement that can be shown safely")
    return result


def latest_pending_event(
    document: activity_ledger.LedgerDocument,
    route: object,
) -> dict[str, object]:
    candidates = [
        event
        for event in document.events
        if event.get("activity_type") == route.activity_type
        and event.get("activity_id") == route.activity_id
        and event.get("to_state") == "pending_close"
        and event.get("event_kind") in {"transition", "pending_revision"}
    ]
    if not candidates:
        raise ContextPacketError(
            f"confirm_close 缺 pending event：{route.activity_type}:{route.activity_id}"
        )
    return candidates[-1]


def retrospective_summary(body: dict[str, object], name: str) -> str:
    visible = body.get("learner_visible_retrospective")
    if not isinstance(visible, dict):
        raise ContextPacketError("the pending body lacks learner_visible_retrospective")
    node = visible.get(name)
    if not isinstance(node, dict) or not str(node.get("summary") or "").strip():
        raise ContextPacketError(f"the pending body lacks the {name} summary")
    return str(node["summary"]).strip()


def confirm_close_payload(
    document: activity_ledger.LedgerDocument,
    route: object,
) -> dict[str, object]:
    event = latest_pending_event(document, route)
    try:
        body = activity_close.decode_body(event)
    except activity_close.CloseError as exc:
        raise ContextPacketError(f"pending body invalid: {exc}") from exc
    if (
        body.get("activity_type") != route.activity_type
        or body.get("activity_id") != route.activity_id
    ):
        raise ContextPacketError("the pending body does not match the current Activity")
    pending_id = str(event.get("event_id") or "")
    body_sha = str(body.get("body_sha256") or "")
    recommendation = str(body.get("recommendation") or "")
    if recommendation not in {"completed", "closed_incomplete"}:
        raise ContextPacketError("the pending body lacks a legal recommendation")
    confirmation = (
        f"pending_event_id={pending_id}\n"
        f"body_sha256={body_sha}\n"
        f"result={recommendation}"
    )
    return {
        "kind": "confirm_close",
        "pending_event_id": pending_id,
        "body_sha256": body_sha,
        "learner_retrospective_markdown": activity_close.render_learner_retrospective(
            body
        ),
        "retrospective_presentation_sha256": (
            activity_close.learner_retrospective_sha256(body)
        ),
        "recommended_result": recommendation,
        "binding_tuple": confirmation,
        "accepted_close_intent": (
            "结课" if recommendation == "completed" else "以未完成状态结课"
        ),
    }


def selected_field_lines(content: str, field_names: Iterable[str]) -> str:
    names = tuple(field_names)
    lines: list[str] = []
    for raw in content.splitlines():
        stripped = raw.strip()
        if any(
            re.match(rf"^-\s*{re.escape(name)}[：:]", stripped)
            or re.match(rf"^{re.escape(name)}[：:]", stripped)
            for name in names
        ):
            lines.append(raw.rstrip())
    return "\n".join(lines).strip()


def mistake_schedule_snapshot(content: str) -> str:
    active = section_any(content, "活跃知识点", level=2, required=False)
    if not active:
        return f"## {doctor.marker_spellings('活跃知识点')[-1]}\n\n{doctor.marker_spellings('暂无')[-1]}"
    snapshots: list[str] = [f"## {doctor.marker_spellings('活跃知识点')[-1]}"]
    entries = [
        item
        for item in headings(active)
        if item.level == 3 and re.fullmatch(r"M-\d{4}", item.title)
    ]
    for item in entries:
        block = active[item.start : item.end].strip()
        fields = selected_field_lines(
            block,
            (
                "知识点键",
                "状态",
                "当前周期摘要",
                "最近正式复测",
                "下次允许复测",
            ),
        )
        snapshots.append(join_exact((f"### {item.title}", fields)))
    if len(snapshots) == 1:
        snapshots.append("暂无。")
    return "\n\n".join(snapshots)


def course_reflection_snapshot(content: str, course_id: str, count: int = 3) -> str:
    course = section(content, course_id, level=2, prefix=True)
    course_heading = next(item for item in headings(course) if item.level == 2)
    first_child = next(
        (item for item in headings(course) if item.start > course_heading.start),
        None,
    )
    preamble_end = first_child.start if first_child else len(course)
    preamble = course[:preamble_end].strip()
    tree = section_any(course, "知识点树形图", level=3, required=False)
    records = sections_by_prefix(course, "REFL-", level=4)[-count:]
    return join_exact((preamble, tree, *records))


def current_problem_id(exercise_scope: str) -> str:
    match = re.search(
        r"^-\s*当前题目[：:]\s*`?([A-Za-z0-9_-]+)`?\s*[。.]?\s*$",
        exercise_scope,
        re.MULTILINE,
    )
    if not match or not PROBLEM_ID_RE.fullmatch(match.group(1)):
        raise ContextPacketError("the Exercise study scope lacks a legal current problem")
    return match.group(1)


def parse_int_list(raw: str) -> list[int]:
    value = raw.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    result: list[int] = []
    for part in value[1:-1].split(","):
        token = part.strip()
        if token.isdigit():
            result.append(int(token))
    return result


def markdown_bold_value(markdown: str, label: str) -> str:
    """Return one exact ``- **label**: value`` field without inventing text."""
    match = re.search(
        rf"^-\s*\*\*{re.escape(label)}\*\*[：:]\s*(.+?)\s*$",
        markdown,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def add_selection(
    selections: list[Selection],
    cache: SourceCache,
    path: Path,
    label: str,
    content: str,
) -> None:
    if not content.strip():
        raise ContextPacketError(f"empty required selection: {label}")
    selections.append(
        Selection(
            source=cache.relative(path),
            label=label,
            content=content.strip(),
            sha256=cache.digest(path),
        )
    )


def _textbook_lesson_ids(route: object) -> tuple[str, str]:
    """Return (course_id, lesson_id) from resume route path."""
    activity_id = str(getattr(route, "activity_id", "") or "").strip()
    candidates = [
        str(getattr(route, "resume_path", "") or ""),
    ]
    course_id = ""
    lesson_id = activity_id if re.fullmatch(r"lesson\d+", activity_id) else ""
    for raw in candidates:
        parts = Path(raw.replace("\\", "/")).parts
        if "40_course" in parts:
            i = parts.index("40_course")
            if i + 1 < len(parts):
                course_id = parts[i + 1]
        if "lessons" in parts:
            j = parts.index("lessons")
            if j + 1 < len(parts) and re.fullmatch(r"lesson\d+", parts[j + 1]):
                lesson_id = parts[j + 1]
    if not course_id or not lesson_id:
        raise ContextPacketError(
            "textbook Lesson 无法从路由解析 course_id/lesson_id"
        )
    return course_id, lesson_id


def _preparation_dir(cache: SourceCache, course_id: str, lesson_id: str) -> Path:
    return cache.root / "main" / "40_course" / course_id / "lessons" / lesson_id / "preparation"


def _new_source_path_presence(prep_dir: Path) -> bool:
    """True when EV-0012 preparation artifacts exist (must not silent-fallback)."""
    if not prep_dir.is_dir():
        return False
    if (prep_dir / "current_snapshot.json").is_file():
        return True
    return any(prep_dir.glob("PREP-*.json"))


def _load_current_preparation(
    cache: SourceCache,
    course_id: str,
    lesson_id: str,
) -> dict[str, object]:
    prep_dir = _preparation_dir(cache, course_id, lesson_id)
    pointer_path = prep_dir / "current_snapshot.json"
    if not pointer_path.is_file():
        raise ContextPacketError(
            "preparation 新路径存在但缺 current_snapshot 指针；"
            "不得回退 legacy working_pages"
        )
    try:
        pointer = json.loads(cache.read(pointer_path))
    except (json.JSONDecodeError, ContextPacketError) as exc:
        raise ContextPacketError(
            f"current Snapshot 指针不可读：{cache.relative(pointer_path)}"
        ) from exc
    snap_id = str(pointer.get("snapshot_id") or "")
    if not snap_id.startswith("PREP-"):
        raise ContextPacketError(f"the current Snapshot pointer id is illegal: {snap_id}")
    snap_path = prep_dir / f"{snap_id}.json"
    if not snap_path.is_file():
        raise ContextPacketError(
            f"current Snapshot 目标缺失：{cache.relative(snap_path)}"
        )
    try:
        payload = json.loads(cache.read(snap_path))
    except (json.JSONDecodeError, ContextPacketError) as exc:
        raise ContextPacketError(
            f"current Snapshot 不可读：{cache.relative(snap_path)}"
        ) from exc
    if payload.get("snapshot_id") != snap_id:
        raise ContextPacketError("the current Snapshot id does not match the pointer")
    if payload.get("state") != "valid":
        raise ContextPacketError("the current Snapshot is not valid")
    if payload.get("scope_coverage") != "complete":
        raise ContextPacketError("the current Snapshot scope is not complete")
    if not payload.get("content_consumed"):
        raise ContextPacketError("the current Snapshot has content_consumed false")
    expected_body = pointer.get("snapshot_body_sha256")
    stored_body = payload.get("snapshot_body_sha256")
    if expected_body and stored_body and expected_body != stored_body:
        raise ContextPacketError("the current Snapshot body hash does not match the pointer")
    return payload


def _snapshot_scope_pages(snap: dict[str, object]) -> list[int]:
    page_keys = snap.get("page_keys") or []
    if not isinstance(page_keys, list) or not page_keys:
        raise ContextPacketError("the current Snapshot lacks page_keys")
    pages: list[int] = []
    for key in page_keys:
        if not isinstance(key, dict) or "pdf_page_index" not in key:
            raise ContextPacketError("the current Snapshot page_keys are illegal")
        pages.append(int(key["pdf_page_index"]))
    if len(pages) != len(set(pages)):
        raise ContextPacketError(f"the current Snapshot Scope contains duplicate pages: {pages}")
    if pages != list(range(min(pages), max(pages) + 1)):
        raise ContextPacketError(f"the current Snapshot Scope is not contiguous: {pages}")
    return pages


def _scope_asset_path(
    cache: SourceCache,
    course_id: str,
    document_id: str,
    page: int,
) -> Path:
    return (
        cache.root
        / "main"
        / "40_course"
        / course_id
        / "book"
        / "primary"
        / "source_assets"
        / document_id
        / "pages"
        / f"page_{page}.md"
    )


def _read_snapshot_scope_asset(
    cache: SourceCache,
    course_id: str,
    snap: dict[str, object],
    page: int,
) -> tuple[Path, str]:
    pages = _snapshot_scope_pages(snap)
    if page not in pages:
        raise ContextPacketError(f"requested page {page} is not in the current Snapshot Scope {pages}")
    document_id = str(snap.get("document_id") or "").strip()
    if not document_id:
        raise ContextPacketError("the current Snapshot lacks document_id")
    asset_path = _scope_asset_path(cache, course_id, document_id, page)
    if not asset_path.is_file():
        raise ContextPacketError(f"a Scope page asset is missing: {cache.relative(asset_path)}")
    text = cache.read(asset_path)
    meta = frontmatter_text(text)
    if meta.get("pdf_page_index") != str(page):
        raise ContextPacketError(f"SourcePageAsset page index mismatch: {cache.relative(asset_path)}")
    if meta.get("source_document_id") != document_id:
        raise ContextPacketError(f"SourcePageAsset document_id mismatch: {cache.relative(asset_path)}")
    if meta.get("source_document_sha256") != snap.get("source_document_sha256"):
        raise ContextPacketError(f"SourcePageAsset document SHA mismatch: {cache.relative(asset_path)}")
    if meta.get("verification_status") != "verified":
        raise ContextPacketError(f"SourcePageAsset is not verified: {cache.relative(asset_path)}")
    receipts = snap.get("load_receipts") or []
    receipt = next(
        (
            item
            for item in receipts
            if isinstance(item, dict)
            and isinstance(item.get("page_key"), dict)
            and int(item["page_key"].get("pdf_page_index", -1)) == page
        ),
        None,
    )
    if not isinstance(receipt, dict):
        raise ContextPacketError(f"the current Snapshot lacks the load receipt for page {page}")
    expected_asset_sha = str(receipt.get("source_page_asset_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_asset_sha):
        raise ContextPacketError(f"the load receipt for page {page} lacks a legal asset SHA")
    if cache.digest(asset_path) != expected_asset_sha:
        raise ContextPacketError(f"SourcePageAsset SHA mismatches the Snapshot: page {page}")
    return asset_path, text


def textbook_page_teaching_contract(
    source_text: str,
    current_page: int,
    page_inventory: dict[str, object],
) -> dict[str, object]:
    """Return the non-compressible classroom gates for one textbook page."""
    meta = frontmatter_text(source_text)
    printed_page_label = meta.get("printed_page_label", "").strip()
    if not printed_page_label:
        raise ContextPacketError(
            f"SourcePageAsset 页 {current_page} 缺 printed_page_label"
        )
    return {
        "schema": "t2ag.page_teaching_contract.v1",
        "current_page": {
            "pdf_page_index": current_page,
            "printed_page_label": printed_page_label,
            "announcement": (
                f"当前教材位置：PDF {current_page} / 书内 {printed_page_label}"
            ),
        },
        "active_boundary": page_inventory["active_boundary"],
        "teaching_blocks": page_inventory["teaching_blocks"],
        "classroom_tree_required": True,
        "coverage_register": {
            "basis": "LessonMap active segment + full verified SourcePageAsset",
            "status": "session_local_required",
            "allowed_block_states": [
                "covered",
                "explicitly_deferred",
                "outside_active_lesson_boundary",
            ],
            "silent_skip_forbidden": True,
            "page_change_requires_all_blocks_accounted": True,
        },
        "interaction_gates": {
            "one_new_teaching_block_per_turn": True,
            "understanding_confirmation_required": True,
            "affect_check_required_after": ["derivation", "summary"],
            "explicit_continue_authorization_required": True,
            "continue_authorization_scope": "single_use_next_block",
            "correct_answer_is_not_continue_authorization": True,
            "page_turn_announcement_required": True,
            "page_turn_requires_separate_continue_authorization": True,
        },
    }


def lesson_map_page_inventory(
    cache: SourceCache,
    course_id: str,
    lesson_id: str,
    snap: dict[str, object],
    current_page: int,
) -> dict[str, object]:
    """Read the Snapshot-bound LessonMap row used for the visible page tree."""
    map_path = (
        cache.root
        / "main"
        / "40_course"
        / course_id
        / "lessons"
        / lesson_id
        / "lesson_map.md"
    )
    map_raw = cache.read_bytes(map_path)
    expected_sha = str(snap.get("lesson_map_sha256") or "")
    if not expected_sha or hashlib.sha256(map_raw).hexdigest() != expected_sha:
        raise ContextPacketError("the LessonMap hash does not match the Snapshot")
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in map_raw.decode("utf-8").splitlines()
        if line.lstrip().startswith("|")
    ]
    header_index = next(
        (index for index, row in enumerate(rows) if "pdf_page_index" in row),
        None,
    )
    if header_index is None:
        raise ContextPacketError("LessonMap 缺 pdf_page_index 表头")
    header = rows[header_index]
    required = {"pdf_page_index", "active boundary", "教材块清单"}
    if not required.issubset(set(header)):
        raise ContextPacketError("LessonMap 缺 active boundary 或教材块清单列")
    page_col = header.index("pdf_page_index")
    boundary_col = header.index("active boundary")
    blocks_col = header.index("教材块清单")
    matches = [
        row
        for row in rows[header_index + 1 :]
        if len(row) > max(page_col, boundary_col, blocks_col)
        and row[page_col].isdigit()
        and int(row[page_col]) == current_page
    ]
    if len(matches) != 1:
        raise ContextPacketError(f"LessonMap 页 {current_page} 必须恰有一条覆盖清单")
    boundary = matches[0][boundary_col].strip()
    blocks = [
        block.strip()
        for block in re.split(r"[；;]", matches[0][blocks_col])
        if block.strip()
    ]
    if not boundary or not blocks:
        raise ContextPacketError(f"LessonMap 页 {current_page} 覆盖清单为空")
    return {"active_boundary": boundary, "teaching_blocks": blocks}


def lesson_opening_contract(
    cache: SourceCache,
    lesson_path: Path,
) -> dict[str, object]:
    """Expose the overview/tree that every Lesson must present before content."""
    content = cache.read(lesson_path)
    learning_range = section(content, "学习范围", level=2, required=False)
    overview = section(content, "Lesson 开场概览", level=2, required=False)
    knowledge_tree = section(content, "开场知识树", level=2, required=False)
    ready = bool(overview and knowledge_tree and "```text" in knowledge_tree)
    if "```mermaid" in knowledge_tree:
        raise ContextPacketError("Lesson 开场知识树必须是字符树，不得使用 Mermaid")
    return {
        "schema": "t2ag.lesson_opening_contract.v1",
        "presentation_required_at": [
            "lesson_start",
            "first_resume_without_confirmed_opening",
        ],
        "status": "source_ready" if ready else "creative_composition_required",
        "overview_required": True,
        "knowledge_tree_required": True,
        "knowledge_tree_format": "ascii_text",
        "source": cache.relative(lesson_path),
        "learning_range": exact_excerpt(learning_range, limit=1_200),
        "overview_markdown": exact_excerpt(overview, limit=1_800) if overview else "",
        "knowledge_tree_markdown": (
            exact_excerpt(knowledge_tree, limit=2_400) if knowledge_tree else ""
        ),
        "creative_composition_allowed": True,
        "creative_opening_questions_allowed": True,
        "overview_does_not_count_as_page_coverage": True,
        "reaction_and_continue_required_before_first_block": True,
    }


def classroom_creativity_policy() -> dict[str, object]:
    """Return the instance-wide creativity boundary for classroom actions."""
    return {
        "schema": "t2ag.classroom_creativity_policy.v1",
        "creative_interaction_default": "allowed",
        "allowed_modes": [
            "analogy",
            "alternative_explanation",
            "historical_context",
            "visual_or_ascii_model",
            "student_led_branch",
            "labeled_warmup_or_exploration",
        ],
        "hard_limits": [
            "do_not_reveal_unrequested_exercise_answers_or_solution_structure",
            "do_not_skip_required_textbook_blocks",
        ],
        "automatic_extra_exercise_generation": False,
        "extra_exercise_trigger": "student_request_or_explicit_opt_in",
        "understanding_check_counts_as_extra_exercise": False,
        "generated_supplement_must_not_impersonate_textbook_or_exam_source": True,
    }


SCAN_FORM_RENDER_PNG = "EF-RENDER-PNG"
SCAN_FORM_PDF_DIRECT = "EF-PDF-DIRECT"
SCAN_FORM_VERIFIED_ASSET = "EF-VERIFIED-ASSET"
SCAN_FORMS_REQUIRING_RENDER = frozenset({SCAN_FORM_RENDER_PNG, SCAN_FORM_PDF_DIRECT})
SCAN_FORM_PENDING_STATUS = {
    SCAN_FORM_RENDER_PNG: "pending_visual_scan",
    SCAN_FORM_PDF_DIRECT: "pending_source_read",
    SCAN_FORM_VERIFIED_ASSET: "pending_asset_read",
}


def admissible_scan_form(page_entry: dict[str, object]) -> str:
    """Cheapest admissible evidence form for one page — fail closed.

    source_page_assets.md §3.2.4 lets a page use EF-VERIFIED-ASSET only when it is
    `verified` AND `layout_critical` is present and false.

    A *missing* layout_critical is deliberately not treated as false.  The
    deterministic prepare-stage detector that would set the flag has not been
    adjudicated yet (workorder step 6), so absence means "unknown", and routing an
    unknown page through a text-only form would silently strip figures, arrows and
    tables from a page the teacher is about to teach from.  Falling back to a
    rendering form costs tokens; guessing costs correctness.
    """
    if page_entry.get("verification_status") != "verified":
        return SCAN_FORM_RENDER_PNG
    if page_entry.get("layout_critical") is False:
        return SCAN_FORM_VERIFIED_ASSET
    return SCAN_FORM_RENDER_PNG


def scope_scan_pending_status(forms) -> str:
    """Scope-level pending status for a possibly mixed set of per-page forms.

    Mixed Scopes report the status of the *most* demanding form present, so a
    single page that fell back to rendering cannot be hidden behind the cheap
    status of its neighbours.
    """
    present = set(forms)
    for form in (SCAN_FORM_RENDER_PNG, SCAN_FORM_PDF_DIRECT, SCAN_FORM_VERIFIED_ASSET):
        if form in present:
            return SCAN_FORM_PENDING_STATUS[form]
    return "pending_visual_scan"


def textbook_scope_scan_manifest(
    cache: SourceCache,
    course_id: str,
    snap: dict[str, object],
    current_page: int,
) -> dict[str, object]:
    """Return exact inputs for a session-local full-Scope scan (any admissible form)."""
    pages = _snapshot_scope_pages(snap)
    if current_page not in pages:
        raise ContextPacketError("textbook_page 不在 current Snapshot Scope 内")
    document_id = str(snap.get("document_id") or "").strip()
    manifest_path = (
        cache.root
        / "main"
        / "40_course"
        / course_id
        / "book"
        / "primary"
        / "source_assets"
        / document_id
        / "manifest.json"
    )
    try:
        manifest = json.loads(cache.read(manifest_path))
    except (json.JSONDecodeError, ContextPacketError) as exc:
        raise ContextPacketError("SourceDocument manifest 不可读") from exc
    if manifest.get("source_document_sha256") != snap.get("source_document_sha256"):
        raise ContextPacketError("SourceDocument manifest SHA 与 Snapshot 错配")
    source_path_raw = str(manifest.get("source_path") or "").strip()
    source_path = cache.root / source_path_raw
    if not source_path_raw or not source_path.is_file():
        raise ContextPacketError("SourceDocument PDF 缺失")
    manifest_pages = {
        int(item.get("pdf_page_index"))
        for item in (manifest.get("pages") or [])
        if isinstance(item, dict) and item.get("verification_status") == "verified"
    }
    if not set(pages).issubset(manifest_pages):
        raise ContextPacketError("SourceDocument manifest 未 verified 覆盖整个 Scope")
    entries = {
        int(item["pdf_page_index"]): item
        for item in (manifest.get("pages") or [])
        if isinstance(item, dict) and item.get("pdf_page_index") is not None
    }
    forms = {page: admissible_scan_form(entries.get(page) or {}) for page in pages}
    needs_render = any(
        form in SCAN_FORMS_REQUIRING_RENDER for form in forms.values()
    )
    payload = {
        "required_this_session": True,
        "status": scope_scan_pending_status(forms.values()),
        "source_document": cache.relative(source_path),
        "source_document_sha256": snap.get("source_document_sha256"),
        "document_id": document_id,
        "pdf_page_indices": pages,
        "current_pdf_page_index": current_page,
        "scan_forms": {str(page): form for page, form in sorted(forms.items())},
        "preparation_snapshot_id": snap.get("snapshot_id"),
        "lesson_scope_version": snap.get("lesson_scope_version"),
        "completion_semantics": (
            "完成判据（ADR-0003）：Scope 全部页的内容本体经宿主可观察投递在本会话内"
            "证成（A1–A5，见 source_page_assets.md §3.1）即为 session scan complete；"
            "无投递的自报 opened、read 或 complete 不构成证成。宿主 Scan Orchestrator "
            "签发保留为未来态，落地后回收签发权。"
            "Snapshot/content_consumed/备课 LoadReceipt/哈希核对均不得冒充本轮扫描。"
        ),
        "agent_self_report_is_not_authorization": True,
    }
    if needs_render:
        # §3.2: render_profile is a property of the rendering forms only.  Emitting
        # it unconditionally is what made "render a PNG" look like part of the
        # proof target rather than one admissible way to meet it.
        payload["render_profile"] = (
            (snap.get("page_keys") or [{}])[0].get("render_profile")
        )
    return payload


# Critical textbook statuses. Boot-time compiler cannot see session state, so a
# textbook packet always starts pending; completion is certified in-session by the
# Prefetcher after observable delivery of A1–A5 (ADR-0003). Host capability = future.
CRITICAL_STATUS_ROUTE_READY = "route_ready"
CRITICAL_STATUS_SCAN_PENDING = "scan_pending"
CRITICAL_STATUS_SCAN_ATTESTED = "scan_attested"
CRITICAL_STATUS_READY = "ready"
SCOPE_SCAN_PENDING_STATUSES = frozenset(
    {
        "pending_visual_scan",
        "pending_source_read",
        "pending_asset_read",
        "pending",
        "scan_pending",
    }
)
# Copy-ready teaching keys withheld while scope scan / admission is unavailable.
WITHHELD_TEACHING_BODY_KEYS = frozenset(
    {
        "textbook_excerpt",
        "first_teaching_candidate",
        "first_confirmation_question",
    }
)
WITHHELD_OPENING_BODY_KEYS = frozenset(
    {
        "overview_markdown",
        "knowledge_tree_markdown",
        "learning_range",
    }
)


def scope_scan_required(action_payload: dict[str, object]) -> bool:
    """True when action_payload declares a session-local scope visual scan."""
    scan = action_payload.get("scope_scan")
    return isinstance(scan, dict) and bool(scan.get("required_this_session"))


def scope_scan_pending(action_payload: dict[str, object]) -> bool:
    """True when a required scope scan is not host-attested complete."""
    if not scope_scan_required(action_payload):
        return False
    scan = action_payload["scope_scan"]
    assert isinstance(scan, dict)
    status = str(scan.get("status") or "").strip()
    if status in SCOPE_SCAN_PENDING_STATUSES or not status:
        return True
    # Context compiler never issues complete: it runs at boot, before any delivery.
    # Completion is certified in-session after observable delivery (ADR-0003).
    return status not in {
        "complete",
        "complete_for_same_snapshot",
        "scan_attested",
        "attested",
    }


def withhold_pending_scope_scan_teaching_payload(
    action_payload: dict[str, object],
) -> dict[str, object]:
    """Strip copy-ready teaching prose until the session-local scan is certified.

    ADR-0003: Prefetcher self-certification after observable delivery is the formal
    completion path; the withhold here keeps packet fields from being replayed as a
    script before that happens. Host-runtime enforcement (ADR-0002) is future state.
    """
    if not scope_scan_pending(action_payload):
        return action_payload
    withheld = dict(action_payload)
    body_note = {
        "withheld": True,
        "reason": "scope_scan_pending_this_session",
        "authorization": "packet_fields_do_not_authorize_emission",
    }
    for key in WITHHELD_TEACHING_BODY_KEYS:
        if key in withheld:
            del withheld[key]
    if "source" in withheld or "source_sha256" in withheld:
        withheld["teaching_body_ref"] = {
            **body_note,
            "source": withheld.get("source"),
            "source_sha256": withheld.get("source_sha256"),
        }
    opening = withheld.get("lesson_opening_contract")
    if isinstance(opening, dict):
        opening_out = dict(opening)
        for key in WITHHELD_OPENING_BODY_KEYS:
            if key in opening_out:
                del opening_out[key]
        opening_out["body_withheld"] = True
        opening_out["body_withheld_reason"] = "scope_scan_pending_this_session"
        withheld["lesson_opening_contract"] = opening_out
    resume = withheld.get("resume_contract")
    if isinstance(resume, dict):
        resume_out = dict(resume)
        # Keep stop identity; drop the copy-ready prompt field.
        if "prompt" in resume_out:
            resume_out["prompt"] = None
            resume_out["prompt_withheld"] = True
            resume_out["prompt_withheld_reason"] = "scope_scan_pending_this_session"
        withheld["resume_contract"] = resume_out
    # page_teaching_contract keeps structural gates/block labels only (no page prose).
    withheld["teaching_payload_withheld"] = True
    withheld["teaching_payload_withheld_reason"] = "scope_scan_pending_this_session"
    withheld["packet_fields_do_not_authorize_emission"] = True
    return withheld


def admission_era_key(packet: dict[str, object]) -> tuple[object, ...]:
    """Identity tuple that must match for a pending scan era to remain valid."""
    payload = packet.get("action_payload")
    scan: dict[str, object] = {}
    if isinstance(payload, dict) and isinstance(payload.get("scope_scan"), dict):
        scan = payload["scope_scan"]  # type: ignore[assignment]
    return (
        packet.get("snapshot_id"),
        scan.get("preparation_snapshot_id"),
        scan.get("lesson_scope_version"),
        scan.get("source_document_sha256"),
        tuple(scan.get("pdf_page_indices") or ()),
    )


def admission_eras_compatible(
    left: dict[str, object],
    right: dict[str, object],
) -> bool:
    """False when critical/prep/scope identity drifted between two packets."""
    return admission_era_key(left) == admission_era_key(right)


def build_teaching_gate(
    action_payload: dict[str, object],
    *,
    scan_pending: bool,
) -> dict[str, object]:
    """Observability-only teaching gate; never grants emission authority."""
    scope_required = scope_scan_required(action_payload)
    scan_status = "not_required"
    if scope_required:
        scan = action_payload.get("scope_scan")
        raw = (
            str(scan.get("status") or "pending")
            if isinstance(scan, dict)
            else "pending"
        )
        if scan_pending:
            scan_status = "pending"
        elif raw in {"complete", "complete_for_same_snapshot", "scan_attested", "attested"}:
            scan_status = "attested"
        else:
            scan_status = raw
    return {
        "route_payload_consistent": True,
        "scope_scan_required": scope_required,
        "scope_scan_status": scan_status,
        "admission_status": "unavailable" if scan_pending else "not_managed_by_context",
        "egress_mode": "status_only" if scan_pending else "unmanaged",
        # Observability: context never authorizes release. False while scan pending;
        # still not a host capability when true would be set by a future host path.
        "may_release_action": False if scan_pending else (not scope_required),
        "page_contract_required": bool(action_payload.get("page_teaching_contract")),
        "explicit_continue_gate_required": bool(
            action_payload.get("page_teaching_contract")
        ),
        "lesson_opening_required": bool(action_payload.get("lesson_opening_contract")),
        "creative_supplements_allowed": bool(
            isinstance(action_payload.get("resume_contract"), dict)
            and action_payload["resume_contract"].get("creative_supplements_allowed")
        ),
        "packet_fields_do_not_authorize_emission": True,
        "host_admission_required_for_textbook_teaching": scope_required,
    }


def _textbook_window_from_snapshot(
    cache: SourceCache,
    course_id: str,
    lesson_id: str,
    progress_snapshot: ProgressSnapshot,
    snap: dict[str, object],
) -> tuple[Path, str]:
    pages = _snapshot_scope_pages(snap)
    current_raw = progress_snapshot.meta.get("textbook_page", "").strip()
    if current_raw.isdigit():
        current = int(current_raw)
        if current not in pages:
            raise ContextPacketError(
                "textbook_page 不在 current Snapshot Scope 内"
            )
    document_id = str(snap.get("document_id") or "").strip()
    if not document_id:
        raise ContextPacketError("the current Snapshot lacks document_id")
    map_path = (
        cache.root
        / "main"
        / "40_course"
        / course_id
        / "lessons"
        / lesson_id
        / "lesson_map.md"
    )
    if not map_path.is_file():
        raise ContextPacketError(f"缺 LessonMap：{cache.relative(map_path)}")
    # Authoritative digest = raw file bytes (same as prepare/Doctor). Never hash
    # Path.read_text / UTF-8 re-encode of normalized newlines.
    map_raw = cache.read_bytes(map_path)
    map_text = map_raw.decode("utf-8")
    expected_map = str(snap.get("lesson_map_sha256") or "")
    if expected_map:
        actual_map = hashlib.sha256(map_raw).hexdigest()
        if actual_map != expected_map:
            raise ContextPacketError("the LessonMap hash does not match the Snapshot")
    for page in pages:
        if not re.search(rf"\|\s*{page}\s*\|", map_text) and f"page_{page}" not in map_text:
            raise ContextPacketError(f"LessonMap 未覆盖 Scope 页 {page}")

    page_sections: list[str] = []
    primary_path: Path | None = None
    for page in pages:
        asset_path, text = _read_snapshot_scope_asset(cache, course_id, snap, page)
        if primary_path is None:
            primary_path = asset_path
        page_sections.append(text.strip())
    assert primary_path is not None
    header = (
        f"# LessonScope from {snap.get('snapshot_id')}\n"
        f"document_id: {document_id}\n"
        f"scope_pages: {pages}\n"
    )
    return primary_path, join_exact((header, *page_sections))


def textbook_lesson_window(
    cache: SourceCache,
    progress_snapshot: ProgressSnapshot,
    route: object,
) -> tuple[Path, str] | None:
    if (
        route.activity_type != "lesson"
        or not route.is_textbook_led
    ):
        return None
    course_id, lesson_id = _textbook_lesson_ids(route)
    prep_dir = _preparation_dir(cache, course_id, lesson_id)
    if _new_source_path_presence(prep_dir):
        # New path present: must succeed from Snapshot/source_assets; never legacy.
        snap = _load_current_preparation(cache, course_id, lesson_id)
        return _textbook_window_from_snapshot(
            cache,
            course_id,
            lesson_id,
            progress_snapshot,
            snap,
        )
    # Legacy working_pages path retired in 0.2.2 S3.
    return None


def exercise_first_step_selections(
    cache: SourceCache,
    main: Path,
    course_id: str,
    activity_id: str,
    problem_id: str,
) -> list[Selection]:
    selections: list[Selection] = []
    exercise_root = (
        main / "40_course" / course_id / "exercises" / activity_id
    )
    candidates = (
        (
            cache.glob(exercise_root / "attempts", "*/attempt.md"),
            "当前题直接相关 Attempt",
        ),
        (
            cache.glob(exercise_root / "reviews", "RV*.md"),
            "当前题直接相关 Review",
        ),
    )
    for paths, label in candidates:
        for path in paths:
            content = cache.read(path)
            problem_ids = set(
                PROBLEM_ID_RE.findall(
                    frontmatter_text(content).get("problem_ids", "")
                )
            )
            if problem_id in problem_ids:
                add_selection(
                    selections,
                    cache,
                    path,
                    f"{label} {path.stem}",
                    content,
                )
    return selections


def first_step_empty_reason(route: object) -> str:
    if route.activity_type == "none":
        return "当前处于活动间隙；没有前台 Activity 的首步追加证据。"
    if route.activity_type == "exercise":
        return "当前题面已在 L0；当前题没有既有 Attempt/Review 需要追加。"
    if route.is_textbook_led:
        return "当前教材窗口已在 L0；当前停点没有另行声明的直接证据。"
    return "当前 Lesson 恢复胶囊已在 L0；当前停点未声明标准化的首步追加证据。"


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen and resolved.is_file():
            seen.add(resolved)
            result.append(resolved)
    return result


def conditional_reads(course_id: str, route: object, group_id: str) -> list[dict[str, str]]:
    course_root = f"main/40_course/{course_id}"
    if route.activity_type == "none":
        direct_evidence_trigger = "选择或恢复下一 Activity"
        direct_evidence_read = (
            f"{course_root}/activity_ledger.md 与 progress.md 的 next_action"
        )
    elif route.activity_type == "exercise":
        direct_evidence_trigger = "当前题已有提交、反馈或订正"
        direct_evidence_read = (
            f"{course_root}/exercises/{route.activity_id}/attempts/ "
            "与 reviews/ 的当前题相关条目"
        )
    else:
        direct_evidence_trigger = "当前 Lesson 已有练习、产物或待核对记录"
        direct_evidence_read = (
            f"{course_root}/lessons/{route.activity_id}/"
            f"{route.activity_id}.md 中与当前停点直接相关的记录"
        )
        direct_evidence_read += (
            "；教材原文通过 preparation Snapshot + source_assets 获取"
        )
    return [
        {
            "trigger": "状态冲突、历史追问或进度审计",
            "read": f"{course_root}/progress.md 的完整教学记录及对应活动证据",
        },
        {
            "trigger": direct_evidence_trigger,
            "read": direct_evidence_read,
        },
        {
            "trigger": "正式复测、疑问回收或模式裁决",
            "read": f"{course_root}/mistake_bank.md、question_bank.md 与证据回链",
        },
        {
            "trigger": "排期、调参、组复盘或结组",
            "read": f"main/30_group/{group_id}/plan.md、calendar.md、review.md 完整相关节",
        },
        {
            "trigger": "教师规则冲突或教师配置修改",
            "read": "main/20_teacher/overlay.md 与当前教师模板全文",
        },
        {
            "trigger": "结课或手动保存",
            "read": "运行 t2ag_activity.py --intent close，并按 session_close.md 回读实际写入目标",
        },
        {
            "trigger": "项目维护、迁移或发布",
            "read": "只读匹配的 active project handoff、合同、测试与实际 Git 状态",
        },
    ]


def lesson_critical_payload(
    cache: SourceCache,
    progress_snapshot: ProgressSnapshot,
    route: object,
) -> dict[str, object]:
    current_slice = section(progress_snapshot.content, "二、当前进度", level=2)
    exact_stop = markdown_bold_value(current_slice, "精确停顿点")
    next_plan = markdown_bold_value(current_slice, "下一步计划")
    checkpoint_state = progress_snapshot.meta.get("checkpoint_state", "").strip()
    if checkpoint_state == "pending" and not exact_stop:
        raise ContextPacketError("pending checkpoint 缺 progress 当前切片的精确停顿点")
    resume_contract = {
        "kind": "pending_checkpoint" if checkpoint_state == "pending" else "next_action",
        "checkpoint_state": checkpoint_state or "none",
        "exact_stop": exact_stop or str(getattr(route, "activity_position", "")),
        "next_plan": next_plan,
        "prompt": exact_stop if checkpoint_state == "pending" else next_plan,
        "source": f"{cache.relative(progress_snapshot.path)}#二、当前进度",
        "authoritative_prompt_must_remain_exact": True,
        "creative_supplements_allowed": True,
        "creative_supplement_policy": (
            "可以加入明确标注的概括、暖场、类比或探索问题；不得替换或伪装成权威停点，"
            "也不得绕过 Exercise 提示闸门。"
        ),
    }
    if route.is_textbook_led:
        current_page = progress_snapshot.meta.get("textbook_page", "").strip()
        if not current_page.isdigit():
            raise ContextPacketError("textbook Lesson 缺合法 textbook_page")
        course_id, lesson_id = _textbook_lesson_ids(route)
        prep_dir = _preparation_dir(cache, course_id, lesson_id)
        if _new_source_path_presence(prep_dir):
            snap = _load_current_preparation(cache, course_id, lesson_id)
            source_path, current_text = _read_snapshot_scope_asset(
                cache,
                course_id,
                snap,
                int(current_page),
            )
            scan_manifest = textbook_scope_scan_manifest(
                cache,
                course_id,
                snap,
                int(current_page),
            )
            page_inventory = lesson_map_page_inventory(
                cache,
                course_id,
                lesson_id,
                snap,
                int(current_page),
            )
        else:
            raise ContextPacketError(
                "textbook Lesson 缺 preparation Snapshot，"
                "legacy working_pages 路径已退役"
            )
        page_contract = textbook_page_teaching_contract(
            current_text,
            int(current_page),
            page_inventory,
        )
        payload: dict[str, object] = {
            "kind": "lesson",
            "source": cache.relative(source_path),
            "source_sha256": cache.digest(source_path),
            "textbook_excerpt": exact_excerpt(current_text),
            "resume_contract": resume_contract,
            "scope_scan": scan_manifest,
            "lesson_opening_contract": lesson_opening_contract(
                cache,
                cache.root
                / "main"
                / "40_course"
                / course_id
                / "lessons"
                / lesson_id
                / f"{lesson_id}.md",
            ),
            "page_teaching_contract": page_contract,
            "teaching_constraint": (
                "一次只推进一个教学块；理解确认、感受反馈与继续授权是三个独立门。"
            ),
        }
        if resume_contract["kind"] == "pending_checkpoint":
            payload["first_confirmation_question"] = resume_contract["prompt"]
        if snap is not None:
            payload["preparation_snapshot_id"] = snap.get("snapshot_id")
            payload["lesson_scope_version"] = snap.get("lesson_scope_version")
            payload["source_page"] = {
                "document_id": snap.get("document_id"),
                "pdf_page_index": int(current_page),
                "printed_page_label": page_contract["current_page"][
                    "printed_page_label"
                ],
            }
        return payload
    source_path = cache.root / route.resume_path
    source = cache.read(source_path)
    candidates = [item for item in headings(source) if item.level == 2]
    if not candidates:
        raise ContextPacketError("当前 Lesson 缺可恢复的教材片段")
    excerpt = source[candidates[0].start : candidates[0].end].strip()
    payload = {
        "kind": "lesson",
        "source": cache.relative(source_path),
        "source_sha256": cache.digest(source_path),
        "textbook_excerpt": exact_excerpt(excerpt),
        "resume_contract": resume_contract,
        "lesson_opening_contract": lesson_opening_contract(cache, source_path),
        "teaching_constraint": "一次只推进一个逻辑动作，等待学生明确确认。",
    }
    if resume_contract["kind"] == "pending_checkpoint":
        payload["first_confirmation_question"] = resume_contract["prompt"]
    return payload


def exercise_critical_payload(
    cache: SourceCache,
    main: Path,
    course_id: str,
    route: object,
) -> dict[str, object]:
    carrier = cache.read(cache.root / route.resume_path)
    problem_id = current_problem_id(section(carrier, "学习范围", level=2))
    problems_path = (
        main
        / "40_course"
        / course_id
        / "exercises"
        / route.activity_id
        / "problems.md"
    )
    problems = cache.read(problems_path)
    statement = problem_statement(section(problems, problem_id, level=2))
    return {
        "kind": "exercise",
        "problem_id": problem_id,
        "source": cache.relative(problems_path),
        "source_sha256": cache.digest(problems_path),
        "problem_statement": statement,
        "teaching_constraint": "首次只展示题面；不得展示提示、思维树、答案或历史解法。",
    }


def build_critical_packet(
    root: Path = ROOT,
    *,
    course_id: str | None = None,
) -> dict[str, object]:
    """Build the bounded critical handoff without constructing the full L0 packet."""
    cache = SourceCache(root)
    main = root / "main"
    profile_path = main / "10_student/profile/profile.md"
    memory_path = main / "00_core/t2ag_memory.md"
    profile = cache.read(profile_path)
    memory = cache.read(memory_path)

    if not initialized(profile, memory):
        snapshot_id = build_snapshot_id(
            cache,
            "FIRST-RUN",
            {"memory": memory_path, "profile": profile_path},
        )
        packet: dict[str, object] = {
            "status": "first_run_required",
            "course_id": None,
            "snapshot_id": snapshot_id,
            "route": {
                "current_activity": "none",
                "current_activity_id": "none",
                "activity_position": "first_run",
                "next_action_kind": "first_run",
            },
            "blocking_teach": True,
            "sources_unchanged": True,
            "source_sha256": public_source_sha256(
                cache,
                progress_path=None,
                activity_path=None,
                profile_path=profile_path,
                overlay_path=None,
            ),
            "action_payload": {
                "kind": "first_run",
                "playbook": "main/50_playbook/first_run.md",
                "next_action": "Collect and confirm the first-run initialization fields, then create the course state.",
            },
        }
        cache.assert_unchanged()
        return packet

    memory_current_course = memory_value(memory, "当前课程")
    resolved_course = course_id or memory_current_course
    if not COURSE_ID_RE.fullmatch(resolved_course):
        raise ContextPacketError(f"illegal course_id: {resolved_course!r}")
    group_id = memory_value(memory, "活跃课程组")
    if not re.fullmatch(r"G\d{2,}", group_id):
        raise ContextPacketError(f"illegal active group id: {group_id!r}")

    learning_path_path = main / "10_student/profile/learning_path.md"
    learning_path = cache.read(learning_path_path)
    markdown_table_row(learning_path, resolved_course)
    group_row = markdown_table_row(learning_path, group_id)
    if resolved_course not in group_course_ids(group_row):
        raise ContextPacketError(
            f"requested course {resolved_course} is not a member of "
            f"active group {group_id}; activate its group before teaching"
        )

    progress_path = main / "40_course" / resolved_course / "progress.md"
    progress = cache.read(progress_path)
    progress_meta = frontmatter_text(progress)
    progress_snapshot = ProgressSnapshot(
        path=progress_path,
        content=progress,
        meta=progress_meta,
    )
    route = resolve_activity(
        root,
        resolved_course,
        snapshot=progress_snapshot,
        reader=cache.read,
    )
    ledger_path, document, next_action = load_ledger_route(
        cache,
        main,
        resolved_course,
        route,
        progress_meta,
    )
    activity_path = (
        progress_path if route.activity_type == "none" else root / route.resume_path
    )
    cache.read(activity_path)
    overlay_path = main / "20_teacher/overlay.md"
    cache.read(overlay_path)

    if next_action["next_action_kind"] == "confirm_close":
        action_payload = confirm_close_payload(document, route)
    elif route.activity_type == "exercise":
        action_payload = exercise_critical_payload(
            cache,
            main,
            resolved_course,
            route,
        )
    elif route.activity_type == "lesson":
        action_payload = lesson_critical_payload(
            cache,
            progress_snapshot,
            route,
        )
    else:
        action_payload = {
            "kind": next_action["next_action_kind"],
            "next_activity_type": next_action["next_activity_type"],
            "next_activity_id": next_action["next_activity_id"],
        }

    critical_sources = {
        "activity": activity_path,
        "ledger": ledger_path,
        "learning_path": learning_path_path,
        "memory": memory_path,
        "profile": profile_path,
        "progress": progress_path,
        "teacher_overlay": overlay_path,
    }
    # Textbook Scope scan pending: withhold copy-ready teaching body and never
    # advertise status=ready / blocking_teach=false (mixed signal). Boot invariant
    # under ADR-0003: every fresh session starts pending until the Prefetcher
    # certifies A1–A5 via observable delivery; host enforcement is future state.
    scan_pending = (
        isinstance(action_payload, dict) and scope_scan_pending(action_payload)
    )
    if scan_pending:
        action_payload = withhold_pending_scope_scan_teaching_payload(action_payload)
        critical_status = CRITICAL_STATUS_ROUTE_READY
        blocking_teach = True
    else:
        critical_status = CRITICAL_STATUS_READY
        blocking_teach = False
    packet = {
        "status": critical_status,
        "course_id": resolved_course,
        "snapshot_id": build_snapshot_id(
            cache,
            resolved_course,
            critical_sources,
        ),
        "route": {
            "current_activity": route.activity_type,
            "current_activity_id": route.activity_id,
            "activity_position": route.activity_position,
            **next_action,
        },
        "blocking_teach": blocking_teach,
        "teaching_gate": build_teaching_gate(
            action_payload if isinstance(action_payload, dict) else {},
            scan_pending=scan_pending,
        ),
        "classroom_creativity_policy": classroom_creativity_policy(),
        "sources_unchanged": True,
        "source_sha256": public_source_sha256(
            cache,
            progress_path=progress_path,
            activity_path=activity_path,
            profile_path=profile_path,
            overlay_path=overlay_path,
        ),
        "action_payload": action_payload,
    }
    cache.assert_unchanged()
    return packet


def critical_blocker_packet(
    error: Exception,
    *,
    course_id: str | None,
) -> dict[str, object]:
    errors = list(getattr(error, "errors", (str(error),)))
    return {
        "status": "blocked",
        "course_id": course_id,
        "snapshot_id": None,
        "route": {},
        "blocking_teach": True,
        "sources_unchanged": False,
        "source_sha256": {},
        "action_payload": {},
        "blockers": errors,
    }


def render_critical(packet: dict[str, object]) -> str:
    rendered = json.dumps(
        packet,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    if len(rendered) > CRITICAL_MAX_CHARS:
        raise ContextPacketError(
            "critical packet exceeds hard character budget: "
            f"{len(rendered)} > {CRITICAL_MAX_CHARS}"
        )
    return rendered


def build_packet(
    root: Path = ROOT,
    *,
    course_id: str | None = None,
    soft_char_budget: int = DEFAULT_SOFT_CHAR_BUDGET,
) -> dict[str, object]:
    cache = SourceCache(root)
    main = root / "main"
    profile_path = main / "10_student/profile/profile.md"
    memory_path = main / "00_core/t2ag_memory.md"
    profile = cache.read(profile_path)
    memory = cache.read(memory_path)

    if not initialized(profile, memory):
        selections: list[Selection] = []
        add_selection(
            selections,
            cache,
            profile_path,
            "initialization state",
            raw_frontmatter(profile) or profile[:400],
        )
        summary = section_any(memory, "上次课摘要", level=2, required=False)
        if summary:
            add_selection(selections, cache, memory_path, "上次课摘要", summary)
        snapshot_id = build_snapshot_id(
            cache,
            "FIRST-RUN",
            {"memory": memory_path, "profile": profile_path},
        )
        cache.assert_unchanged()
        return {
            "schema_version": 2,
            "status": "first_run_required",
            "course_id": None,
            "snapshot_id": snapshot_id,
            "sources_unchanged": True,
            "source_sha256": public_source_sha256(
                cache,
                progress_path=None,
                activity_path=None,
                profile_path=profile_path,
                overlay_path=None,
            ),
            "next_action": "Read main/50_playbook/first_run.md",
            "selections": [item.as_dict() for item in selections],
        }

    memory_current_course = memory_value(memory, "当前课程")
    resolved_course = course_id or memory_current_course
    if not COURSE_ID_RE.fullmatch(resolved_course):
        raise ContextPacketError(f"illegal course_id: {resolved_course!r}")
    group_id = memory_value(memory, "活跃课程组")
    if not re.fullmatch(r"G\d{2,}", group_id):
        raise ContextPacketError(f"illegal active group id: {group_id!r}")
    context_mode = (
        "memory_current"
        if resolved_course == memory_current_course
        else "explicit_same_active_group"
    )

    learning_path_path = main / "10_student/profile/learning_path.md"
    learning_path = cache.read(learning_path_path)
    course_row = markdown_table_row(learning_path, resolved_course)
    group_row = markdown_table_row(learning_path, group_id)
    if resolved_course not in group_course_ids(group_row):
        raise ContextPacketError(
            f"requested course {resolved_course} is not a member of "
            f"active group {group_id}; activate its group before teaching"
        )

    progress_path = main / "40_course" / resolved_course / "progress.md"
    progress = cache.read(progress_path)
    progress_snapshot = ProgressSnapshot(
        path=progress_path,
        content=progress,
        meta=frontmatter_text(progress),
    )
    route = resolve_activity(
        root,
        resolved_course,
        snapshot=progress_snapshot,
        reader=cache.read,
    )
    ledger_path, _ledger_document, next_action = load_ledger_route(
        cache,
        main,
        resolved_course,
        route,
        progress_snapshot.meta,
    )
    selections = []

    if context_mode == "memory_current":
        add_selection(
            selections,
            cache,
            memory_path,
            "恢复指针",
            join_exact(
                (
                    section_any(memory, "上次课摘要", level=2),
                    section_any(memory, "当前状态指针", level=2),
                )
            ),
        )
    else:
        add_selection(
            selections,
            cache,
            memory_path,
            "全局指针切换校验",
            join_exact(
                (
                    markdown_table_row(memory, "活跃课程组"),
                    markdown_table_row(memory, "当前课程"),
                )
            ),
        )
    profile_parts = [raw_frontmatter(profile)]
    for title in (
        "基本信息",
        "执行参数",
        "学习目标",
        "期望的辅导方式",
        "特殊要求（可选）",
        "一、总纲",
    ):
        profile_parts.append(section(profile, title, required=False))
    add_selection(
        selections,
        cache,
        profile_path,
        "学生教学契约",
        join_exact(profile_parts),
    )

    add_selection(
        selections,
        cache,
        learning_path_path,
        "当前课程与课程组索引行",
        join_exact(
            (
                course_row,
                group_row,
            )
        ),
    )

    group_root = main / "30_group" / group_id
    plan_path = group_root / "plan.md"
    plan = cache.read(plan_path)
    plan_meta = frontmatter_text(plan)
    if plan_meta.get("status") != "active":
        raise ContextPacketError(f"active group is not active: {group_id}")
    add_selection(
        selections,
        cache,
        plan_path,
        "当前课程组容量",
        join_exact(
            (
                raw_frontmatter(plan),
                section(plan, "1. 基本信息", level=2),
                section(plan, "2. 成员课程", level=2),
            )
        ),
    )
    calendar_path = group_root / "calendar.md"
    calendar = cache.read(calendar_path)
    add_selection(
        selections,
        cache,
        calendar_path,
        "当前时间预算与周期",
        join_exact(
            (
                raw_frontmatter(calendar),
                section(calendar, "时间预算", level=2),
                section(calendar, "3-1-3 周期", level=2),
            )
        ),
    )

    add_selection(
        selections,
        cache,
        progress_path,
        "进度真相源当前切片",
        join_exact(
            (
                raw_frontmatter(progress),
                section(progress, "二、当前进度", level=2),
            )
        ),
    )

    carrier_path = (
        progress_path if route.activity_type == "none" else root / route.resume_path
    )
    carrier = cache.read(carrier_path)
    baseline_activity_paths: list[Path] = (
        [] if route.activity_type == "none" else [carrier_path]
    )
    l1_selections: list[Selection] = []
    source_consumption: dict[str, object] = {
        "required": False,
        "scope_text_status": "not_required",
        "scope_visual_status": "not_required",
    }
    if route.activity_type == "exercise":
        scope = section(carrier, "学习范围", level=2)
        add_selection(
            selections,
            cache,
            carrier_path,
            "当前 Exercise 恢复胶囊",
            join_exact((raw_frontmatter(carrier), scope)),
        )
        problem_id = current_problem_id(scope)
        problems_path = (
            main
            / "40_course"
            / resolved_course
            / "exercises"
            / route.activity_id
            / "problems.md"
        )
        problems = cache.read(problems_path)
        problems_meta = frontmatter_text(problems)
        problem = section(problems, problem_id, level=2)
        problem_fields = selected_field_lines(
            problem,
            (
                "题号",
                "来源页",
                "难度",
                "依赖 completion node",
                "状态",
                "错误级别",
            ),
        )
        add_selection(
            selections,
            cache,
            problems_path,
            f"当前题元数据 {problem_id}",
            join_exact((f"## {problem_id}", problem_fields)),
        )
        baseline_activity_paths.append(problems_path)
        if route.source_path:
            source_path = root / route.source_path
            source = cache.read(source_path)
            expected_source_sha = problems_meta.get("source_sha256", "")
            actual_source_sha = cache.digest(source_path)
            if not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha):
                raise ContextPacketError(
                    "textbook Exercise problems.md 缺合法 source_sha256"
                )
            if actual_source_sha != expected_source_sha:
                raise ContextPacketError(
                    "textbook Exercise 题源 SHA 与 problems.md 不一致："
                    f"{cache.relative(source_path)}"
                )
            source_identity = selected_field_lines(
                raw_frontmatter(source),
                (
                    "artifact_id",
                    "source_document",
                    "source_document_sha256",
                    "source_locator",
                    "verification_status",
                    "verified",
                ),
            )
            add_selection(
                selections,
                cache,
                source_path,
                f"人工校对题面 {problem_id}",
                join_exact(
                    (
                        source_identity,
                        section(source, problem_id, level=2),
                    )
                ),
            )
            baseline_activity_paths.append(source_path)
        l1_selections = exercise_first_step_selections(
            cache,
            main,
            resolved_course,
            route.activity_id,
            problem_id,
        )
        baseline_activity_paths.extend(
            root / item.source for item in l1_selections
        )
    elif route.activity_type == "lesson":
        carrier_h2 = [item for item in headings(carrier) if item.level == 2]
        preferred: Heading | None = None
        for keyword in ("当前状态", "学习范围", "恢复快照", "本课概览"):
            preferred = next(
                (item for item in carrier_h2 if keyword in item.title),
                None,
            )
            if preferred:
                break
        recovery_capsule = (
            carrier[preferred.start : preferred.end].strip()
            if preferred
            else ""
        )
        add_selection(
            selections,
            cache,
            carrier_path,
            "当前 Lesson 恢复胶囊",
            join_exact((raw_frontmatter(carrier), recovery_capsule)),
        )
        lesson_window = textbook_lesson_window(
            cache,
            progress_snapshot,
            route,
        )
        if lesson_window is not None:
            working_path, excerpt = lesson_window
            add_selection(
                selections,
                cache,
                working_path,
                "当前教材窗口",
                excerpt,
            )
            baseline_activity_paths.append(working_path)
            if route.is_textbook_led:
                course_id, lesson_id = _textbook_lesson_ids(route)
                prep_dir = _preparation_dir(cache, course_id, lesson_id)
                if _new_source_path_presence(prep_dir):
                    snap = _load_current_preparation(cache, course_id, lesson_id)
                    current_page = int(progress_snapshot.meta["textbook_page"])
                    scan_manifest = textbook_scope_scan_manifest(
                        cache,
                        course_id,
                        snap,
                        current_page,
                    )
                    source_consumption = {
                        "required": True,
                        "scope_text_status": "complete_in_current_packet",
                        "scope_visual_status": "external_scan_required",
                        **scan_manifest,
                    }
                else:
                    source_consumption = {
                        "required": True,
                        "scope_text_status": "unavailable_legacy_retired",
                        "scope_visual_status": "unavailable_legacy_retired",
                    }

    course_root = main / "40_course" / resolved_course
    question_path = course_root / "question_bank.md"
    question = cache.read(question_path)
    add_selection(
        selections,
        cache,
        question_path,
        "未闭合疑问",
        join_exact(
            (
                section_any(question, "待解决", level=2),
                section_any(question, "需要回看", level=2),
            )
        ),
    )
    mistake_path = course_root / "mistake_bank.md"
    mistake = cache.read(mistake_path)
    add_selection(
        selections,
        cache,
        mistake_path,
        "活跃错题调度摘要",
        mistake_schedule_snapshot(mistake),
    )

    reflections_path = main / "10_student/profile/course_reflections.md"
    reflections = cache.read(reflections_path)
    add_selection(
        selections,
        cache,
        reflections_path,
        "当前课程感想与最近提炼",
        course_reflection_snapshot(reflections, resolved_course),
    )

    reasoning_path = main / "10_student/profile/reasoning_patterns.md"
    reasoning = cache.read(reasoning_path)
    if route.activity_type == "exercise":
        add_selection(
            selections,
            cache,
            reasoning_path,
            "活跃解题思维模式",
            join_exact(
                (
                    section_any(reasoning, "一、解题思维总纲", level=2),
                    section_any(reasoning, "二、活跃思维模式", level=2),
                )
            ),
        )

    overlay_path = main / "20_teacher/overlay.md"
    overlay = cache.read(overlay_path)
    teacher_paths = cache.glob(main / "20_teacher", "T*.md")
    mapping = resolve_teacher_mapping(
        root,
        reader=cache.read,
        teacher_paths=teacher_paths,
    )
    teacher_id, teacher_relative = mapping.get(
        resolved_course,
        mapping["(默认)"],
    )
    overlay_parts = [markdown_table_row(overlay, resolved_course)]
    for title in (
        "回复格式",
        "教学节奏",
        "启动摩擦与疑问处置",
        "情绪使用红线（不可违反，优先级高于模板默认行为）",
        "学生协商结果",
    ):
        overlay_parts.append(section(overlay, title, required=False))
    add_selection(
        selections,
        cache,
        overlay_path,
        "当前教师 overlay",
        join_exact(overlay_parts),
    )

    teacher_path = root / teacher_relative
    teacher = cache.read(teacher_path)
    activity_module = section(
        teacher,
        (
            "模块三:解题流程"
            if route.activity_type == "exercise"
            else "模块一:渐进式教学"
        ),
        level=3,
        prefix=True,
        required=False,
    )
    add_selection(
        selections,
        cache,
        teacher_path,
        f"生效教师模板 {teacher_id}",
        join_exact(
            (
                raw_frontmatter(teacher),
                section(teacher, "核心人格", level=2),
                activity_module,
                section(teacher, "互动方式", level=2, required=False),
                section(teacher, "纠错方式", level=2, required=False),
                section(teacher, "行为准则(不可违反)", level=2),
                section(teacher, "教学节奏与互动原则", level=2),
                section(teacher, "默认回复格式", level=2),
            )
        ),
    )

    baseline_paths = unique_paths(
        (
            memory_path,
            profile_path,
            learning_path_path,
            plan_path,
            calendar_path,
            progress_path,
            ledger_path,
            *baseline_activity_paths,
            question_path,
            mistake_path,
            reflections_path,
            reasoning_path,
            overlay_path,
            teacher_path,
        )
    )
    reference_chars = sum(len(cache.read(path)) for path in baseline_paths)
    l0_source_chars = sum(len(item.content) for item in selections)
    l1_source_chars = sum(len(item.content) for item in l1_selections)
    selected_source_chars = l0_source_chars + l1_source_chars
    source_ratio = (
        selected_source_chars / reference_chars
        if reference_chars
        else 1.0
    )
    critical_sources = {
        "activity": carrier_path,
        "ledger": ledger_path,
        "learning_path": learning_path_path,
        "memory": memory_path,
        "profile": profile_path,
        "progress": progress_path,
        "teacher_overlay": overlay_path,
    }
    packet: dict[str, object] = {
        "schema_version": 2,
        "status": "ready",
        "course_id": resolved_course,
        "snapshot_id": build_snapshot_id(
            cache,
            resolved_course,
            critical_sources,
        ),
        "sources_unchanged": True,
        "source_sha256": public_source_sha256(
            cache,
            progress_path=progress_path,
            activity_path=carrier_path,
            profile_path=profile_path,
            overlay_path=overlay_path,
        ),
        "memory_current_course": memory_current_course,
        "context_mode": context_mode,
        "group_id": group_id,
        "route": {
            "course_type": route.course_type,
            "learning_mode": route.learning_mode,
            "progression_kind": "mastery_mode" if route.learning_mode else "course_type",
            "current_activity": route.activity_type,
            "current_activity_id": route.activity_id,
            "activity_position": route.activity_position,
            "primary_read": route.resume_path,
            "lesson_context": {
                "kind": route.lesson_context_kind,
                "id": route.lesson_context_id or None,
            },
            **next_action,
        },
        "teacher": {
            "template_id": teacher_id,
            "template_path": teacher_relative,
        },
        "source_consumption": source_consumption,
        "cost": {
            "metric": (
                "Unicode characters in LF-normalized Markdown; exact for "
                "this serializer, source selection is a separate inventory proxy"
            ),
            "reference_inventory_chars": reference_chars,
            "l0_selected_source_chars": l0_source_chars,
            "l1_selected_source_chars": l1_source_chars,
            "source_selection_ratio": round(source_ratio, 4),
            "source_inventory_omitted_percent": round(
                (1.0 - source_ratio) * 100.0,
                1,
            ),
            "serialized_l0_markdown_chars": 0,
            "serialized_l0_plus_l1_markdown_chars": 0,
            "soft_char_budget": soft_char_budget,
            "l0_budget_state": "PENDING",
            "l0_plus_l1_budget_state": "PENDING",
        },
        "selections": [item.as_dict() for item in selections],
        "l1_selections": [item.as_dict() for item in l1_selections],
        "l1_empty_reason": first_step_empty_reason(route),
        "conditional_reads": conditional_reads(
            resolved_course,
            route,
            group_id,
        ),
    }
    finalize_serialized_cost(packet)
    cache.assert_unchanged()
    return packet


def render_markdown(
    packet: dict[str, object],
    *,
    include_l1: bool = False,
) -> str:
    if packet["status"] == "first_run_required":
        # Return here, do not fall through.  A first-run packet has no route, no
        # cost and no `l1_empty_reason`; the L1 block below reads that key
        # unconditionally, so falling through made the documented empty-skeleton
        # quick-start command
        #   t2ag_context.py --include-l1 --format markdown
        # die with KeyError instead of printing the first-run notice.
        return "\n".join(
            [
                "# T2AG context packet",
                "",
                "- status: `first_run_required`",
                f"- snapshot_id: `{packet['snapshot_id']}`",
                "- sources_unchanged: `true`",
                f"- next_action: `{packet['next_action']}`",
                "",
                "> The empty template is not initialized: there is no L0/L1 to project, and `--include-l1` adds nothing in this state.",
            ]
        )
    else:
        route = packet["route"]
        cost = packet["cost"]
        consumption = packet.get("source_consumption", {})
        lines = [
            (
                "# T2AG L0 + first L1 learning-session context packet"
                if include_l1
                else "# T2AG L0 learning-session context packet"
            ),
            "",
            "> Read-only immediate projection; the body is a verbatim excerpt of source files or a mechanical routing field, and is not a new source of truth.",
            "",
            f"- status: `{packet['status']}`",
            f"- course: `{packet['course_id']}`",
            f"- snapshot_id: `{packet['snapshot_id']}`",
            f"- sources_unchanged: `{str(packet['sources_unchanged']).lower()}`",
            f"- memory_current_course: `{packet['memory_current_course']}`",
            f"- context_mode: `{packet['context_mode']}`",
            f"- active_group: `{packet['group_id']}`",
            (
                "- current_activity: "
                f"`{route['current_activity']}: {route['current_activity_id']}`"
            ),
            f"- activity_position: {route['activity_position']}",
            f"- next_action_kind: `{route['next_action_kind']}`",
            (
                "- next_activity: "
                f"`{route['next_activity_type']}:{route['next_activity_id']}`"
            ),
            f"- primary_read: `{route['primary_read']}`",
            (
                "- scope_text_status: "
                f"`{consumption.get('scope_text_status', 'not_required')}`"
            ),
            (
                "- scope_visual_status: "
                f"`{consumption.get('scope_visual_status', 'not_required')}`"
            ),
            (
                "- scope_pdf_page_indices: "
                f"`{consumption.get('pdf_page_indices', [])}`"
            ),
            "",
            "## Cost account",
            "",
            (
                "- reference_inventory_chars: "
                f"`{cost['reference_inventory_chars']}`"
            ),
            (
                "- l0_selected_source_chars: "
                f"`{cost['l0_selected_source_chars']}`"
            ),
            (
                "- l1_selected_source_chars: "
                f"`{cost['l1_selected_source_chars']}`"
            ),
            (
                "- source_selection_ratio: "
                f"`{cost['source_selection_ratio']}`"
            ),
            (
                "- source_inventory_omitted_percent: "
                f"`{cost['source_inventory_omitted_percent']}%`"
            ),
            (
                "- serialized_l0_markdown_chars: "
                f"`{cost['serialized_l0_markdown_chars']}`"
            ),
            (
                "- serialized_l0_plus_l1_markdown_chars: "
                f"`{cost['serialized_l0_plus_l1_markdown_chars']}`"
            ),
            (
                "- l0_soft_budget: "
                f"`{cost['l0_budget_state']} / {cost['soft_char_budget']}`"
            ),
            (
                "- l0_plus_l1_soft_budget: "
                f"`{cost['l0_plus_l1_budget_state']} / "
                f"{cost['soft_char_budget']}`"
            ),
            "",
            (
                "> `reference_inventory_chars` compares the current source inventory; it is not a "
                "measurement against the old prompt, and you must never call that ratio an "
                "end-to-end token reduction."
            ),
        ]
    for index, item in enumerate(packet.get("selections", []), start=1):
        lines.extend(
            (
                "",
                f"## L0.{index} · {item['label']}",
                "",
                f"- source: `{item['source']}`",
                f"- source_sha256: `{item['sha256']}`",
                "",
                "<!-- exact-source-excerpt:start -->",
                item["content"],
                "<!-- exact-source-excerpt:end -->",
            )
        )
    if include_l1:
        l1_selections = packet.get("l1_selections", [])
        lines.extend(("", "## L1 · direct evidence for the current step"))
        if l1_selections:
            for index, item in enumerate(l1_selections, start=1):
                lines.extend(
                    (
                        "",
                        f"### L1.{index} · {item['label']}",
                        "",
                        f"- source: `{item['source']}`",
                        f"- source_sha256: `{item['sha256']}`",
                        "",
                        "<!-- exact-source-excerpt:start -->",
                        item["content"],
                        "<!-- exact-source-excerpt:end -->",
                    )
                )
        else:
            lines.extend(
                (
                    "",
                    "- additional_read: `none`",
                    f"- reason: {packet['l1_empty_reason']}",
                )
            )
    conditional = packet.get("conditional_reads", [])
    if conditional:
        lines.extend(
            (
                "",
                "## L2 · trigger-based full reads",
                "",
                "| Trigger | Read |",
                "|---|---|",
            )
        )
        for item in conditional:
            lines.append(f"| {item['trigger']} | {item['read']} |")
    return "\n".join(lines).rstrip() + "\n"


def finalize_serialized_cost(packet: dict[str, object]) -> None:
    cost = packet["cost"]
    budget = cost["soft_char_budget"]
    for _ in range(12):
        l0_chars = len(render_markdown(packet, include_l1=False))
        combined_chars = len(render_markdown(packet, include_l1=True))
        l0_state = "PASS" if l0_chars <= budget else "REVIEW"
        combined_state = "PASS" if combined_chars <= budget else "REVIEW"
        before = (
            cost["serialized_l0_markdown_chars"],
            cost["serialized_l0_plus_l1_markdown_chars"],
            cost["l0_budget_state"],
            cost["l0_plus_l1_budget_state"],
        )
        after = (
            l0_chars,
            combined_chars,
            l0_state,
            combined_state,
        )
        cost["serialized_l0_markdown_chars"] = l0_chars
        cost["serialized_l0_plus_l1_markdown_chars"] = combined_chars
        cost["l0_budget_state"] = l0_state
        cost["l0_plus_l1_budget_state"] = combined_state
        if after == before:
            return
    raise ContextPacketError("serialized Markdown cost did not converge")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    parser = argparse.ArgumentParser(
        description="Build a read-only exact-excerpt learning context packet.",
    )
    parser.add_argument(
        "--course",
        help="Course ID. Omit to use memory's 当前课程 pointer.",
    )
    parser.add_argument(
        "--format",
        choices=("critical", "markdown", "json", "stats"),
        default="markdown",
    )
    parser.add_argument(
        "--expect-snapshot",
        help="Reject a background packet that does not match this critical snapshot.",
    )
    parser.add_argument(
        "--soft-char-budget",
        type=int,
        default=DEFAULT_SOFT_CHAR_BUDGET,
    )
    parser.add_argument(
        "--include-l1",
        action="store_true",
        help="Append direct evidence for the first teaching step.",
    )
    args = parser.parse_args()
    if args.soft_char_budget <= 0:
        print("[FAIL] --soft-char-budget must be positive")
        return 2
    critical_output: str | None = None
    try:
        packet = (
            build_critical_packet(ROOT, course_id=args.course)
            if args.format == "critical"
            else build_packet(
                ROOT,
                course_id=args.course,
                soft_char_budget=args.soft_char_budget,
            )
        )
        if (
            args.expect_snapshot
            and packet.get("snapshot_id") != args.expect_snapshot
        ):
            raise ContextPacketError(
                "snapshot mismatch: "
                f"expected={args.expect_snapshot} actual={packet.get('snapshot_id')}"
            )
        if args.format == "critical":
            critical_output = render_critical(packet)
    except (
        ActivityContractError,
        ContextPacketError,
        TeacherContractError,
    ) as exc:
        if args.format == "critical":
            blocker = critical_blocker_packet(exc, course_id=args.course)
            print(render_critical(blocker), end="")
            return 0
        errors = getattr(exc, "errors", (str(exc),))
        for error in errors:
            print(f"[FAIL] context packet: {error}")
        return 1
    if args.format == "critical":
        print(critical_output, end="")
    elif args.format == "json":
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2))
    elif args.format == "stats":
        payload = {
            "status": packet["status"],
            "course_id": packet.get("course_id"),
            "snapshot_id": packet.get("snapshot_id"),
            "sources_unchanged": packet.get("sources_unchanged"),
            "source_sha256": packet.get("source_sha256"),
            "memory_current_course": packet.get("memory_current_course"),
            "context_mode": packet.get("context_mode"),
            "group_id": packet.get("group_id"),
            "route": packet.get("route"),
            "cost": packet.get("cost"),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(
            render_markdown(packet, include_l1=args.include_l1),
            end="",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
