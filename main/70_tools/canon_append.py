#!/usr/bin/env python3
"""canon_append — the only legitimate writer of the teaching canon (G2 floor).

Contract: main/50_playbook/canon_carrier.md.  Design record (six adjudicated
questions): workspace docs/handoffs/T2AG_CANON_CARRIER_EGRESS_WORKORDER_DRAFT_2026-08-19.md v2.

What this tool verifies (on-disk identity only — the "narrow E"):
  * the course exists and has ``default_driver: textbook``;
  * the lesson directory exists;
  * ``block_id`` is unique within the lesson's teaching_log.md;
  * every ``--page-ref`` names a source page asset whose frontmatter parses;
    its persistent identity (source_document_sha256 / pdf_page_index /
    render_profile / render_sha256 / verified_text_sha256 / verification_status)
    is snapshotted into the emission record.

What it deliberately does NOT verify:
  * whether this session actually consumed the page (A1–A5) — that belongs to
    the withhold layer (ADR-0003); a repo CLI sees the disk, not the dialogue;
  * ``verification_status`` — recorded as fact, never used as a gate.

Write order and crash semantics: L (emissions.jsonl) first, then C
(teaching_log.md), each via tmp + os.replace.  A crash in between leaves
"L has a row, C lacks the block", which doctor reports as WARN (repairable
residue).  The reverse — C block without an L row — cannot be produced by a
crash, only by bypassing this tool, and is FAIL.  The asymmetry is the design.

This is NOT the ``lesson_emit`` of ADR-0002: no host enforcement, chat cannot
be intercepted, and a forger who writes both files as a consistent chain is
not detectable (G2 catches inconsistency, not consistent forgery).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"
COURSE_ROOT = MAIN / "40_course"

GENESIS = "GENESIS"

PAGE_REF_FIELDS = (
    "asset_id",
    "source_document_sha256",
    "pdf_page_index",
    "render_profile",
    "render_sha256",
    "verified_text_sha256",
    "verification_status",
)


def _fail(reason_code: str, message: str) -> "int":
    print(json.dumps({"ok": False, "reason": reason_code, "message": message},
                     ensure_ascii=False))
    return 1


def _frontmatter(text: str) -> dict[str, str]:
    """Minimal single-level ``key: value`` frontmatter parser."""
    match = re.match(r"\A---\n(.*?)\n---", text, re.S)
    fields: dict[str, str] = {}
    if not match:
        return fields
    for line in match.group(1).splitlines():
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip().strip('"')
    return fields


def find_page_asset(course_dir: Path, asset_id: str) -> Path | None:
    book = course_dir / "book"
    if not book.is_dir():
        return None
    for page in book.rglob("page_*.md"):
        if ".cache" in page.parts:
            continue  # identity must never be pinned to the evictable cache
        try:
            head = page.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if re.search(r"^asset_id:\s*" + re.escape(asset_id) + r"\s*$", head, re.M):
            return page
    return None


def existing_block_ids(log_text: str) -> set[str]:
    return set(re.findall(r"^## (\S+)", log_text, re.M))


def last_line_sha(emissions_text: str) -> str:
    lines = [l for l in emissions_text.split("\n") if l.strip()]
    if not lines:
        return GENESIS
    return hashlib.sha256(lines[-1].encode("utf-8")).hexdigest()


def atomic_append(path: Path, addition: str) -> None:
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(old + addition, encoding="utf-8", newline="\n")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course", required=True)
    ap.add_argument("--lesson", required=True)
    ap.add_argument("--block-id", required=True)
    ap.add_argument("--page-ref", action="append", default=[],
                    help="asset_id of a source page asset; repeatable")
    ap.add_argument("--content-file", help="file with the block body; default stdin")
    ap.add_argument("--complete", action="store_true",
                    help="repair mode: rebuild the missing C block for an existing "
                         "L row (crash residue, CANON-004). Verifies the supplied "
                         "content against the row's content_sha256, appends C only, "
                         "never touches L.")
    args = ap.parse_args()

    course_dir = COURSE_ROOT / args.course
    course_md = course_dir / "course.md"
    if not course_md.is_file():
        return _fail("no_course", f"课程不存在：{args.course}")
    meta = _frontmatter(course_md.read_text(encoding="utf-8", errors="replace"))
    if meta.get("default_driver") != "textbook":
        return _fail("not_textbook",
                     f"{args.course} default_driver={meta.get('default_driver')!r}"
                     "（正典载体只适用 textbook driver 课程，D4）")

    lesson_dir = course_dir / "lessons" / args.lesson
    if not lesson_dir.is_dir():
        return _fail("no_lesson", f"lesson 目录不存在：{lesson_dir.relative_to(ROOT)}")

    log_path = lesson_dir / "teaching_log.md"
    emissions_path = lesson_dir / "emissions.jsonl"
    log_text = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
    emissions_text = (emissions_path.read_text(encoding="utf-8")
                      if emissions_path.is_file() else "")

    ledger_rows: dict[str, dict] = {}
    for raw in emissions_text.split("\n"):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if rec.get("block_id"):
            ledger_rows[str(rec["block_id"])] = rec

    in_canon = args.block_id in existing_block_ids(log_text)
    in_ledger = args.block_id in ledger_rows

    if args.complete:
        # Repair mode: the L row exists (crash left C behind), C block does not.
        # Rebuild C from user-supplied content verified against the row's hash.
        # Never writes L — a second normal emit here would forge a ghost row
        # that a dict-based check reads over, going green on a broken chain.
        if not in_ledger:
            return _fail("no_ledger_row",
                         f"--complete 需要既存事件行，但 L 中无 {args.block_id}")
        if in_canon:
            return _fail("already_complete",
                         f"{args.block_id} 在 C 中已存在，无残留可补")
    else:
        if in_canon:
            return _fail("duplicate_block", f"block_id 已存在：{args.block_id}")
        if in_ledger:
            return _fail("crash_residue",
                         f"L 已有 {args.block_id} 而 C 无块（emit 中断残留）。"
                         "重跑普通 emit 会造出重复账行；请用 --complete 只补 C")

    page_refs: list[dict[str, str]] = []
    for asset_id in args.page_ref:
        asset_path = find_page_asset(course_dir, asset_id)
        if asset_path is None:
            return _fail("no_asset", f"页资产不存在或不可发现：{asset_id}")
        fm = _frontmatter(asset_path.read_text(encoding="utf-8", errors="replace"))
        if not fm.get("source_document_sha256") or not fm.get("render_sha256"):
            return _fail("bad_asset_frontmatter",
                         f"页资产 frontmatter 缺持久身份字段：{asset_id}")
        page_refs.append({k: fm.get(k, "") for k in PAGE_REF_FIELDS} | {"asset_id": asset_id})

    if args.content_file:
        content = Path(args.content_file).read_text(encoding="utf-8")
    else:
        content = sys.stdin.read()
    if not content.strip():
        return _fail("empty_content", "教学块正文为空")
    if re.search(r"^## ", content, re.M):
        return _fail("content_h2_forbidden",
                     "正文内不得使用二级标题——`## ` 是正典块分界，正文标题请用 ### 及以下")
    # Canonical form: exactly one trailing newline.  The hash in L and the
    # bytes in C both use this form, so doctor's recompute is well-defined.
    content = content.rstrip("\n") + "\n"

    if args.complete:
        row = ledger_rows[args.block_id]
        got = hashlib.sha256(content.encode("utf-8")).hexdigest()
        want = row.get("content_sha256")
        if got != want:
            return _fail("content_hash_mismatch",
                         f"补齐内容与事件账不符：账 {str(want)[:12]}… 实供 {got[:12]}…"
                         "（--complete 只接受当初那份正文，不接受重写）")
        header = (f"## {args.block_id}\n\n"
                  f"> seq {row.get('seq')} · emitted_at {row.get('emitted_at')} · pages "
                  + (", ".join(str(r.get("asset_id", "?"))
                               for r in (row.get("page_refs") or [])) or "—")
                  + "\n\n")
        atomic_append(log_path,
                      ("\n" if log_text and not log_text.endswith("\n\n") else "")
                      + header + content)
        print(json.dumps({"ok": True, "mode": "complete",
                          "block_id": args.block_id, "seq": row.get("seq"),
                          "ledger_untouched": True}, ensure_ascii=False))
        return 0

    seq = sum(1 for l in emissions_text.split("\n") if l.strip()) + 1
    record = {
        "seq": seq,
        "block_id": args.block_id,
        "lesson": args.lesson,
        "emitted_at": _dt.datetime.now(_dt.timezone.utc)
                         .isoformat(timespec="seconds"),
        "page_refs": page_refs,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "prev_sha256": last_line_sha(emissions_text),
    }
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)

    # L first, C second — see module docstring for the crash asymmetry.
    atomic_append(emissions_path, line + "\n")
    header = (f"## {args.block_id}\n\n"
              f"> seq {seq} · emitted_at {record['emitted_at']} · pages "
              + (", ".join(r["asset_id"] for r in page_refs) or "—") + "\n\n")
    atomic_append(log_path, ("\n" if log_text and not log_text.endswith("\n\n") else "")
                  + header + content)

    print(json.dumps({"ok": True, "seq": seq, "block_id": args.block_id,
                      "teaching_log": str(log_path.relative_to(ROOT)),
                      "emissions": str(emissions_path.relative_to(ROOT))},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
