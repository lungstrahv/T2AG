#!/usr/bin/env python3
"""Course-owned source page assets, LessonScope, snapshots, and CacheEviction (EV-0012).

Fail-closed prepare, immutable Snapshot + current pointer, and safe CacheEviction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"
RENDER_PROFILE_DEFAULT = "pdf-300dpi-rgb-v1"
CACHE_REL = Path("book/.cache/source_pages")
CURRENT_POINTER_NAME = "current_snapshot.json"
VERIFIED_STATUSES = frozenset({"verified", "verified_human", "verified_ok", "ok"})
PPI_EVIDENCE_SCHEMA = "t2ag.source_page_ppi_evidence.v1"
SNAPSHOT_SCHEMA_CURRENT = "t2ag.lesson_preparation_snapshot.v2"


class PrepareError(RuntimeError):
    """Fail-closed preparation or CacheEviction safety failure."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, order=True)
class PageKey:
    source_document_sha256: str
    pdf_page_index: int
    render_profile: str = RENDER_PROFILE_DEFAULT

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_document_sha256": self.source_document_sha256,
            "pdf_page_index": self.pdf_page_index,
            "render_profile": self.render_profile,
        }

    def cache_path(self, course: Path) -> Path:
        return (
            course
            / CACHE_REL
            / self.source_document_sha256
            / self.render_profile
            / f"page_{self.pdf_page_index}.png"
        )


def continuous_scope(
    current: int,
    available: Iterable[int],
    *,
    target: int = 5,
) -> tuple[list[int], bool]:
    """Build a continuous scope containing *current*.

    Available pages must themselves form a contiguous PDF index block.
    Sparse availability fails closed (no pseudo-continuous Scope).
    Normal docs: 5..8 pages (target clamped to available length).
    Short docs (N<5): all pages fixed.
    """
    pages = sorted({int(p) for p in available})
    if not pages:
        raise ValueError("available page list is empty")
    if current not in pages:
        raise ValueError(f"current page {current} not in available pages {pages}")
    if pages != list(range(pages[0], pages[-1] + 1)):
        raise ValueError(
            f"sparse available pages cannot form continuous scope: {pages}"
        )
    n = len(pages)
    short = n < 5
    if short:
        return pages, True
    size = max(5, min(8, int(target), n))
    lo, hi = pages[0], pages[-1]
    # Prefer start = current-1 (relative -1), then pan to stay in range.
    start = current - 1
    end = start + size - 1
    if end > hi:
        end = hi
        start = end - size + 1
    if start < lo:
        start = lo
        end = start + size - 1
        if end > hi:
            end = hi
            start = max(lo, end - size + 1)
    window = list(range(start, end + 1))
    if current not in window:
        raise ValueError(
            f"continuous scope {window} does not contain current page {current}"
        )
    if window != list(range(window[0], window[-1] + 1)):
        raise ValueError(f"scope window is not continuous: {window}")
    return window, False


def heat_at(
    *,
    last_in_scope_at: float | None,
    last_access_at: float | None,
    created_at: float | None,
) -> float:
    values = [v for v in (last_in_scope_at, last_access_at, created_at) if v is not None]
    return max(values) if values else 0.0


@dataclass
class CacheEntry:
    key: PageKey
    path: Path
    last_in_scope_at: float | None = None
    last_access_at: float | None = None
    created_at: float | None = None

    @property
    def heat(self) -> float:
        return heat_at(
            last_in_scope_at=self.last_in_scope_at,
            last_access_at=self.last_access_at,
            created_at=self.created_at,
        )


def list_cache_entries(course: Path) -> list[CacheEntry]:
    """List entries under <course>/book/.cache/source_pages."""
    root = course / CACHE_REL
    if not root.is_dir():
        return []
    entries: list[CacheEntry] = []
    for png in root.rglob("page_*.png"):
        try:
            profile = png.parent.name
            doc_sha = png.parent.parent.name
            m = re.fullmatch(r"page_(\d+)\.png", png.name)
            if not m:
                continue
            idx = int(m.group(1))
            st = png.stat()
            entries.append(
                CacheEntry(
                    key=PageKey(doc_sha, idx, profile),
                    path=png,
                    created_at=st.st_ctime,
                    last_access_at=st.st_atime,
                    last_in_scope_at=None,
                )
            )
        except OSError:
            continue
    return entries


def eviction_candidates(
    entries: list[CacheEntry],
    p0: set[PageKey],
    *,
    current_page: int,
) -> list[CacheEntry]:
    """Coldest first, then farther from current page, then stable full key."""
    cand = [e for e in entries if e.key not in p0]
    cand.sort(
        key=lambda e: (
            e.heat,
            -abs(e.key.pdf_page_index - current_page),
            e.key.source_document_sha256,
            e.key.pdf_page_index,
            e.key.render_profile,
        )
    )
    return cand


def plan_eviction(
    entries: list[CacheEntry],
    p0: set[PageKey],
    *,
    scope_n: int,
    current_page: int,
    need_free: int | None = None,
) -> list[CacheEntry]:
    quota = min(3 * scope_n, 30)
    cache_n = len(entries)
    free = need_free if need_free is not None else max(0, cache_n - quota)
    if free <= 0:
        return []
    out: list[CacheEntry] = []
    for e in eviction_candidates(entries, p0, current_page=current_page):
        out.append(e)
        if len(out) >= free:
            break
    return out


def course_dir(course_id: str) -> Path:
    return MAIN / "40_course" / course_id


def course_book(course_id: str) -> Path:
    return course_dir(course_id) / "book"


def cache_root(course_id: str) -> Path:
    return course_book(course_id) / ".cache"


def assert_path_under_course_cache(course_id: str, path: Path) -> None:
    root = cache_root(course_id).resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise PrepareError(
            f"cache_quota_blocked: path escapes Course book/.cache: {path}"
        ) from exc
    if ".cache" not in path.parts:
        raise PrepareError(f"cache_quota_blocked: path not under .cache: {path}")


def resolve_pdf_path(course: Path, manifest: dict[str, Any]) -> Path:
    source_path = str(manifest.get("source_path") or "").strip()
    if not source_path:
        raise PrepareError("manifest missing source_path")
    candidate = Path(source_path)
    if not candidate.is_absolute():
        # Prefer repo-relative, then course-relative.
        repo_cand = ROOT / source_path
        if repo_cand.is_file():
            return repo_cand
        course_cand = course / source_path
        if course_cand.is_file():
            return course_cand
        # Common layout: book/primary/<file>.pdf relative to course
        primary = course / "book" / "primary" / Path(source_path).name
        if primary.is_file():
            return primary
        return repo_cand
    return candidate


def load_manifest(course: Path, document_id: str) -> dict[str, Any]:
    path = course / "book/primary/source_assets" / document_id / "manifest.json"
    if not path.is_file():
        raise PrepareError(f"missing source_assets manifest: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrepareError(f"unreadable manifest: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PrepareError(f"manifest must be object: {path}")
    return data


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def page_asset_path(course: Path, document_id: str, page_index: int) -> Path:
    return (
        course
        / "book/primary/source_assets"
        / document_id
        / "pages"
        / f"page_{page_index}.md"
    )


def verify_page_asset(
    course: Path,
    document_id: str,
    page_index: int,
    *,
    expected_doc_sha: str,
    render_profile: str,
) -> tuple[str, str, dict[str, str]]:
    """Return (text, asset_sha256, frontmatter). Fail if missing/unverified."""
    path = page_asset_path(course, document_id, page_index)
    if not path.is_file():
        raise PrepareError(
            f"scope page asset missing or unverified: page_{page_index} "
            f"(path {path})"
        )
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    meta = parse_frontmatter(text)
    status = (meta.get("verification_status") or "").strip().lower()
    if status not in VERIFIED_STATUSES:
        raise PrepareError(
            f"scope page asset not verified: page_{page_index} "
            f"status={status or 'missing'}"
        )
    doc_sha = (meta.get("source_document_sha256") or "").strip().lower()
    if doc_sha and doc_sha != expected_doc_sha.lower():
        raise PrepareError(
            f"page asset document SHA mismatch: page_{page_index}"
        )
    profile = (meta.get("render_profile") or render_profile).strip()
    if profile != render_profile:
        raise PrepareError(
            f"page asset render_profile mismatch: page_{page_index} "
            f"got {profile} expected {render_profile}"
        )
    return text, sha256_bytes(raw), meta


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def ppi_from_profile(render_profile: str) -> int:
    """Derive target PPI claim from a profile name like pdf-300dpi-rgb-v1."""
    m = re.search(r"pdf-(\d+)dpi", render_profile or "")
    if not m:
        raise PrepareError(
            f"cannot derive target PPI from render_profile: {render_profile}"
        )
    return int(m.group(1))


def png_dimensions(path: Path) -> tuple[int, int]:
    """Read PNG width/height from IHDR without image libraries. Fail-closed."""
    try:
        with path.open("rb") as fh:
            header = fh.read(24)
    except OSError as exc:
        raise PrepareError(f"PNG unreadable: {path}: {exc}") from exc
    if len(header) < 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise PrepareError(f"not a valid PNG (IHDR): {path}")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    if width <= 0 or height <= 0:
        raise PrepareError(f"invalid PNG dimensions: {path}")
    return width, height


def pdf_page_mediabox_pt(
    pdf_path: Path, pdf_page_index: int
) -> tuple[float, float]:
    """MediaBox (pt) of 1-based pdf_page_index. Fail-closed if reader unavailable."""
    try:
        import fitz  # lazy: only the PPI back-calc path needs a PDF reader
    except ImportError as exc:
        raise PrepareError(
            "PyMuPDF (fitz) unavailable; cannot read PDF MediaBox for PPI back-calc"
        ) from exc
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 — PDF reader raises many types
        raise PrepareError(f"PDF unreadable for MediaBox: {pdf_path}: {exc}") from exc
    try:
        if pdf_page_index < 1 or pdf_page_index > doc.page_count:
            raise PrepareError(
                f"pdf_page_index {pdf_page_index} outside PDF page count "
                f"{doc.page_count}"
            )
        rect = doc[pdf_page_index - 1].mediabox
    finally:
        doc.close()
    width, height = float(rect.width), float(rect.height)
    if width <= 0 or height <= 0:
        raise PrepareError(f"non-positive MediaBox: page {pdf_page_index}")
    return width, height


def expected_pixels_at_ppi(
    mediabox_pt: tuple[float, float], target_ppi: int
) -> tuple[int, int]:
    """expected = round(MediaBox_pt / 72 * target_ppi) per axis."""
    return (
        round(mediabox_pt[0] / 72.0 * target_ppi),
        round(mediabox_pt[1] / 72.0 * target_ppi),
    )


def verify_png_ppi(
    png_path: Path,
    *,
    mediabox_pt: tuple[float, float],
    target_ppi: int,
    tolerance_px: int = 1,
) -> dict[str, Any]:
    """Back-calc PPI from actual pixels vs MediaBox. PNG DPI metadata is ignored:
    it can be missing or forged; only geometry is authoritative."""
    width, height = png_dimensions(png_path)
    exp_w, exp_h = expected_pixels_at_ppi(mediabox_pt, target_ppi)
    delta_w, delta_h = abs(width - exp_w), abs(height - exp_h)
    inches_w = mediabox_pt[0] / 72.0
    inches_h = mediabox_pt[1] / 72.0
    return {
        "png": str(png_path),
        "actual_pixels": [width, height],
        "expected_pixels": [exp_w, exp_h],
        "delta_pixels": [delta_w, delta_h],
        "tolerance_px": tolerance_px,
        "back_calculated_ppi": [
            round(width / inches_w, 2),
            round(height / inches_h, 2),
        ],
        "target_ppi": target_ppi,
        "ppi_ok": delta_w <= tolerance_px and delta_h <= tolerance_px,
    }


def ppi_evidence_digest(evidence: dict[str, Any]) -> str:
    core = dict(evidence)
    core.pop("evidence_sha256", None)
    return sha256_text(canonical_json(core))


def validate_ppi_evidence(
    evidence: dict[str, Any], page_key: PageKey
) -> str | None:
    """Validate content-addressed PPI evidence against its receipt page key."""
    if evidence.get("schema") != PPI_EVIDENCE_SCHEMA:
        return "PPI evidence schema invalid"
    if evidence.get("page_key") != page_key.as_dict():
        return "PPI evidence page_key mismatch"
    if evidence.get("ppi_ok") is not True:
        return "PPI evidence is not passing"
    digest = str(evidence.get("evidence_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return "PPI evidence digest missing or invalid"
    if ppi_evidence_digest(evidence) != digest:
        return "PPI evidence digest mismatch"
    png_sha = str(evidence.get("png_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", png_sha):
        return "PPI evidence PNG digest missing or invalid"
    expected = evidence.get("expected_pixels")
    actual = evidence.get("actual_pixels")
    tolerance = evidence.get("tolerance_px")
    if (
        not isinstance(expected, list)
        or len(expected) != 2
        or not all(isinstance(v, int) and v > 0 for v in expected)
        or not isinstance(actual, list)
        or len(actual) != 2
        or not all(isinstance(v, int) and v > 0 for v in actual)
        or not isinstance(tolerance, int)
        or tolerance < 0
    ):
        return "PPI evidence geometry invalid"
    if any(abs(a - e) > tolerance for a, e in zip(actual, expected)):
        return "PPI evidence geometry does not meet tolerance"
    try:
        claimed_ppi = ppi_from_profile(page_key.render_profile)
    except PrepareError as exc:
        return str(exc)
    if evidence.get("target_ppi") != claimed_ppi:
        return "PPI evidence target does not match render_profile"
    return None


def build_page_ppi_evidence(
    pdf_path: Path,
    png_path: Path,
    page_key: PageKey,
    *,
    tolerance_px: int = 1,
) -> dict[str, Any]:
    """Build portable, content-addressed evidence from PDF and PNG geometry."""
    target_ppi = ppi_from_profile(page_key.render_profile)
    mediabox = pdf_page_mediabox_pt(pdf_path, page_key.pdf_page_index)
    check = verify_png_ppi(
        png_path,
        mediabox_pt=mediabox,
        target_ppi=target_ppi,
        tolerance_px=tolerance_px,
    )
    if not check["ppi_ok"]:
        raise PrepareError(
            f"pixel back-calc does not reach claimed PPI: page "
            f"{page_key.pdf_page_index}"
        )
    evidence: dict[str, Any] = {
        "schema": PPI_EVIDENCE_SCHEMA,
        "page_key": page_key.as_dict(),
        "target_ppi": target_ppi,
        "mediabox_pt": [round(mediabox[0], 3), round(mediabox[1], 3)],
        "expected_pixels": check["expected_pixels"],
        "actual_pixels": check["actual_pixels"],
        "tolerance_px": tolerance_px,
        "back_calculated_ppi": check["back_calculated_ppi"],
        "png_sha256": sha256_file(png_path),
        "ppi_ok": True,
    }
    evidence["evidence_sha256"] = ppi_evidence_digest(evidence)
    return evidence


def lesson_map_covers(map_text: str, pages: list[int], document_id: str) -> list[int]:
    missing: list[int] = []
    for p in pages:
        markers = (
            f"page_{p}",
            f"| {p} |",
            f"|{p}|",
            f"-P{p:04d}",
            f"pdf_page_index: {p}",
            f" {p} ",
        )
        # Require explicit page index presence in a map row / marker, not bare digits alone.
        if not any(m in map_text for m in markers):
            # also accept table cell with just the index as own cell after leading |
            if not re.search(rf"\|\s*{p}\s*\|", map_text):
                missing.append(p)
    return missing


def rebuildable(
    course: Path,
    key: PageKey,
    *,
    pdf_path: Path | None,
    expected_pdf_sha: str | None,
) -> tuple[bool, str]:
    if pdf_path is None or not pdf_path.is_file():
        return False, "source PDF missing"
    try:
        actual = sha256_file(pdf_path)
    except OSError as exc:
        return False, f"source PDF unreadable: {exc}"
    if expected_pdf_sha and actual.lower() != expected_pdf_sha.lower():
        return False, "source PDF SHA mismatch"
    if actual.lower() != key.source_document_sha256.lower():
        return False, "page key document SHA does not match PDF"
    if not key.render_profile:
        return False, "render_profile missing"
    return True, "ok"


def apply_eviction(
    to_delete: list[CacheEntry],
    *,
    dry_run: bool,
    course_id: str,
    pdf_by_doc_sha: dict[str, Path],
    p0: set[PageKey],
) -> list[str]:
    deleted: list[str] = []
    for e in to_delete:
        if e.key in p0:
            raise PrepareError(
                f"cache_quota_blocked: refusing to delete P0 page "
                f"{e.key.pdf_page_index}"
            )
        assert_path_under_course_cache(course_id, e.path)
        pdf = pdf_by_doc_sha.get(e.key.source_document_sha256)
        ok, reason = rebuildable(
            course_dir(course_id),
            e.key,
            pdf_path=pdf,
            expected_pdf_sha=e.key.source_document_sha256,
        )
        if not ok:
            raise PrepareError(
                f"cache_quota_blocked: not rebuildable ({reason}): {e.path}"
            )
        rel = str(e.path)
        if dry_run:
            deleted.append(f"DRY_RUN {rel}")
            continue
        e.path.unlink(missing_ok=True)
        deleted.append(rel)
    return deleted


@dataclass
class LoadReceipt:
    receipt_id: str
    page_key: PageKey
    verified_text_sha256: str
    source_page_asset_sha256: str
    source_document_sha256: str
    ppi_evidence: dict[str, Any]
    loaded_at: str
    by: str = "t2ag_source_pages"

    def as_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "page_key": self.page_key.as_dict(),
            "verified_text_sha256": self.verified_text_sha256,
            "source_page_asset_sha256": self.source_page_asset_sha256,
            "source_document_sha256": self.source_document_sha256,
            "ppi_evidence": dict(self.ppi_evidence),
            "loaded_at": self.loaded_at,
            "by": self.by,
        }


def make_receipt(
    page_key: PageKey,
    verified_text: str,
    *,
    source_page_asset_sha256: str,
    source_document_sha256: str,
    ppi_evidence: dict[str, Any],
    now: float | None = None,
) -> LoadReceipt:
    evidence_error = validate_ppi_evidence(ppi_evidence, page_key)
    if evidence_error:
        raise PrepareError(f"cannot issue load receipt: {evidence_error}")
    if source_document_sha256.lower() != page_key.source_document_sha256.lower():
        raise PrepareError("cannot issue load receipt: source document SHA mismatch")
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now or time.time()))
    body = sha256_text(verified_text)
    # Receipt id is content-addressed (no wall clock) so identical prepare is idempotent.
    rid = "RCP-" + sha256_text(
        f"{canonical_json(page_key.as_dict())}|{body}|"
        f"{source_page_asset_sha256}|{source_document_sha256}|"
        f"{ppi_evidence['evidence_sha256']}"
    )[:16]
    return LoadReceipt(
        receipt_id=rid,
        page_key=page_key,
        verified_text_sha256=body,
        source_page_asset_sha256=source_page_asset_sha256,
        source_document_sha256=source_document_sha256,
        ppi_evidence=dict(ppi_evidence),
        loaded_at=ts,
    )


def snapshot_body_core(
    *,
    lesson_id: str,
    scope_version: str,
    page_keys: list[PageKey],
    receipts: list[LoadReceipt],
    lesson_map_sha256: str,
    source_document_sha256: str,
    document_id: str,
    short_document: bool,
    previous_snapshot_id: str | None,
    prepared_by: str,
    prepared_at: str,
) -> dict[str, Any]:
    return {
        "schema": SNAPSHOT_SCHEMA_CURRENT,
        "lesson_id": lesson_id,
        "lesson_scope_version": scope_version,
        "previous_snapshot_id": previous_snapshot_id,
        "lesson_scope_sha256": sha256_text(
            canonical_json([k.as_dict() for k in page_keys])
        ),
        "page_keys": [k.as_dict() for k in page_keys],
        "load_receipt_ids": [r.receipt_id for r in receipts],
        "load_receipts": [r.as_dict() for r in receipts],
        "lesson_map_sha256": lesson_map_sha256,
        "source_document_sha256": source_document_sha256,
        "document_id": document_id,
        "scope_coverage": "complete",
        "content_consumed": True,
        "short_document": short_document,
        "prepared_by": prepared_by,
        "prepared_at": prepared_at,
        "state": "valid",
    }


def lesson_map_file_sha256(path: Path) -> str:
    """Authoritative LessonMap digest: raw file bytes only (no text newline rewrite)."""
    return sha256_file(path)


def build_snapshot(
    *,
    lesson_id: str,
    scope_version: str,
    page_keys: list[PageKey],
    receipts: list[LoadReceipt],
    source_document_sha256: str,
    document_id: str,
    short_document: bool,
    lesson_map_sha256: str | None = None,
    lesson_map_bytes: bytes | None = None,
    lesson_map_text: str | None = None,
    previous_snapshot_id: str | None = None,
    prepared_by: str = "t2ag_source_pages",
    prepared_at: str | None = None,
) -> dict[str, Any]:
    if len(receipts) != len(page_keys):
        raise PrepareError("receipt count must equal scope page count")
    for key, receipt in zip(page_keys, receipts):
        if receipt.page_key != key:
            raise PrepareError("load receipt page_key does not match scope order")
        if receipt.source_document_sha256.lower() != source_document_sha256.lower():
            raise PrepareError("load receipt source_document_sha256 mismatch")
        if not receipt.source_page_asset_sha256:
            raise PrepareError("load receipt missing source_page_asset_sha256")
        evidence_error = validate_ppi_evidence(receipt.ppi_evidence, key)
        if evidence_error:
            raise PrepareError(f"load receipt PPI evidence invalid: {evidence_error}")
    ts = prepared_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # LessonMap hash is always raw bytes. Prefer explicit sha / bytes; text is only
    # a unit-test helper (UTF-8 encode of the given string, not Path.read_text).
    if lesson_map_sha256:
        map_sha = lesson_map_sha256.lower()
    elif lesson_map_bytes is not None:
        map_sha = sha256_bytes(lesson_map_bytes)
    elif lesson_map_text is not None:
        map_sha = sha256_bytes(lesson_map_text.encode("utf-8"))
    else:
        raise PrepareError("lesson map bytes or sha required for Snapshot")
    core = snapshot_body_core(
        lesson_id=lesson_id,
        scope_version=scope_version,
        page_keys=page_keys,
        receipts=receipts,
        lesson_map_sha256=map_sha,
        source_document_sha256=source_document_sha256,
        document_id=document_id,
        short_document=short_document,
        previous_snapshot_id=previous_snapshot_id,
        prepared_by=prepared_by,
        prepared_at=ts,
    )
    # ID covers scope, map, receipts, and source/document verification — not wall clock
    # or chain pointer (previous_snapshot_id is metadata only).
    id_material = {
        "lesson_id": lesson_id,
        "lesson_scope_version": scope_version,
        "page_keys": core["page_keys"],
        "load_receipts": [
            {
                "page_key": r["page_key"],
                "verified_text_sha256": r["verified_text_sha256"],
                "source_page_asset_sha256": r["source_page_asset_sha256"],
                "source_document_sha256": r["source_document_sha256"],
                "ppi_evidence_sha256": r["ppi_evidence"]["evidence_sha256"],
            }
            for r in core["load_receipts"]
        ],
        "lesson_map_sha256": map_sha,
        "source_document_sha256": source_document_sha256,
        "document_id": document_id,
        "short_document": short_document,
    }
    snap_id = "PREP-" + sha256_text(canonical_json(id_material))[:16]
    # Body hash excludes wall-clock and chain metadata so same evidence is stable.
    durable = {**core, "snapshot_id": snap_id}
    durable.pop("prepared_at", None)
    durable.pop("previous_snapshot_id", None)
    durable_receipts: list[dict[str, Any]] = []
    for receipt in durable.get("load_receipts") or []:
        if isinstance(receipt, dict):
            item = dict(receipt)
            item.pop("loaded_at", None)
            durable_receipts.append(item)
        else:
            durable_receipts.append(receipt)
    durable["load_receipts"] = durable_receipts
    body_sha = sha256_text(canonical_json(durable))
    return {
        **core,
        "snapshot_id": snap_id,
        "snapshot_body_sha256": body_sha,
    }


def durable_snapshot_payload(snap: dict[str, Any]) -> dict[str, Any]:
    """Snapshot fields that must not change for a given snapshot_id."""
    out = dict(snap)
    out.pop("prepared_at", None)
    out.pop("previous_snapshot_id", None)
    out.pop("snapshot_body_sha256", None)
    durable_receipts: list[dict[str, Any]] = []
    for receipt in out.get("load_receipts") or []:
        if isinstance(receipt, dict):
            item = dict(receipt)
            item.pop("loaded_at", None)
            durable_receipts.append(item)
        else:
            durable_receipts.append(receipt)
    out["load_receipts"] = durable_receipts
    return out


def prep_dir(course: Path, lesson: str) -> Path:
    return course / "lessons" / lesson / "preparation"


def current_pointer_path(course: Path, lesson: str) -> Path:
    return prep_dir(course, lesson) / CURRENT_POINTER_NAME


def snapshot_path(course: Path, lesson: str, snapshot_id: str) -> Path:
    return prep_dir(course, lesson) / f"{snapshot_id}.json"


def write_current_pointer(
    course: Path,
    lesson: str,
    *,
    snapshot_id: str,
    body_sha256: str,
) -> Path:
    pointer = {
        "schema": "t2ag.preparation_current_pointer.v1",
        "lesson_id": lesson,
        "snapshot_id": snapshot_id,
        "snapshot_body_sha256": body_sha256,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = current_pointer_path(course, lesson)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_current_snapshot(course: Path, lesson: str) -> dict[str, Any]:
    pointer_path = current_pointer_path(course, lesson)
    if not pointer_path.is_file():
        raise PrepareError(
            f"missing current Snapshot pointer: {pointer_path.name}"
        )
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrepareError(f"unreadable current pointer: {exc}") from exc
    snap_id = str(pointer.get("snapshot_id") or "")
    if not snap_id.startswith("PREP-"):
        raise PrepareError(f"invalid current pointer snapshot_id: {snap_id}")
    path = snapshot_path(course, lesson, snap_id)
    if not path.is_file():
        raise PrepareError(f"current pointer target missing: {path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrepareError(f"unreadable current Snapshot: {exc}") from exc
    if payload.get("snapshot_id") != snap_id:
        raise PrepareError("current Snapshot id does not match pointer")
    if payload.get("state") != "valid":
        raise PrepareError("current Snapshot is not valid")
    expected_body = pointer.get("snapshot_body_sha256")
    if expected_body:
        # Recompute body hash excluding nothing critical — use stored field if present.
        stored = payload.get("snapshot_body_sha256")
        if stored and stored != expected_body:
            raise PrepareError("current Snapshot body hash does not match pointer")
    return payload


def validate_snapshot_closure(
    course: Path,
    lesson: str,
    snap: dict[str, Any],
    *,
    map_text: str | None = None,
) -> list[str]:
    """Return list of human-readable failures (empty if ok)."""
    fails: list[str] = []
    if snap.get("state") != "valid":
        fails.append("state != valid")
    if snap.get("scope_coverage") != "complete":
        fails.append("scope_coverage != complete")
    if not snap.get("content_consumed"):
        fails.append("content_consumed is false")
    page_keys = snap.get("page_keys") or []
    if not page_keys:
        fails.append("empty page_keys")
    indices = [int(k["pdf_page_index"]) for k in page_keys if "pdf_page_index" in k]
    if indices and indices != list(range(min(indices), max(indices) + 1)):
        fails.append(f"scope not continuous: {indices}")
    receipts = snap.get("load_receipts") or []
    if len(receipts) != len(page_keys):
        fails.append("receipt count != page_keys count")
    doc_sha = str(snap.get("source_document_sha256") or "")
    for r in receipts:
        pk = r.get("page_key") or {}
        if not r.get("source_page_asset_sha256"):
            fails.append(f"receipt missing asset sha for page {pk.get('pdf_page_index')}")
        if str(r.get("source_document_sha256") or "").lower() != doc_sha.lower():
            fails.append(
                f"receipt document sha mismatch page {pk.get('pdf_page_index')}"
            )
        if snap.get("schema") == SNAPSHOT_SCHEMA_CURRENT:
            try:
                key = PageKey(
                    str(pk["source_document_sha256"]),
                    int(pk["pdf_page_index"]),
                    str(pk["render_profile"]),
                )
            except (KeyError, TypeError, ValueError):
                fails.append("receipt page_key invalid for PPI-bound Snapshot")
                continue
            evidence = r.get("ppi_evidence")
            if not isinstance(evidence, dict):
                fails.append(
                    f"receipt missing PPI evidence page {key.pdf_page_index}"
                )
                continue
            evidence_error = validate_ppi_evidence(evidence, key)
            if evidence_error:
                fails.append(
                    f"receipt PPI evidence invalid page {key.pdf_page_index}: "
                    f"{evidence_error}"
                )
    map_path = course / "lessons" / lesson / "lesson_map.md"
    map_raw: bytes | None = None
    if map_path.is_file():
        map_raw = map_path.read_bytes()
        map_sha = sha256_bytes(map_raw)
        if map_text is None:
            map_text = map_raw.decode("utf-8")
    else:
        map_sha = ""
        if map_text is None:
            fails.append("lesson_map.md missing")
            map_text = ""
    if snap.get("lesson_map_sha256") and map_sha and snap["lesson_map_sha256"] != map_sha:
        fails.append("lesson_map_sha256 mismatch")
    missing = lesson_map_covers(
        map_text or "",
        indices,
        str(snap.get("document_id") or ""),
    )
    if missing:
        fails.append(f"LessonMap missing pages: {missing}")
    return fails


def cmd_scope(args: argparse.Namespace) -> int:
    pages = [int(x) for x in args.available.split(",")]
    window, short = continuous_scope(args.current, pages, target=args.target)
    print(
        json.dumps(
            {
                "scope_pages": window,
                "scope_n": len(window),
                "short_document": short,
                "quota_n": min(3 * len(window), 30),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def derive_scope_from_snapshot(snap: dict[str, Any]) -> tuple[list[PageKey], int, int]:
    keys = [
        PageKey(
            str(k["source_document_sha256"]),
            int(k["pdf_page_index"]),
            str(k.get("render_profile") or RENDER_PROFILE_DEFAULT),
        )
        for k in snap.get("page_keys") or []
    ]
    if not keys:
        raise PrepareError("current Snapshot has empty page_keys")
    current_page = keys[0].pdf_page_index
    # Prefer middle-ish: if teaching window current stored, use progress later; default first+1 if len>=2
    if len(keys) >= 2:
        current_page = keys[min(1, len(keys) - 1)].pdf_page_index
    return keys, len(keys), current_page


def cmd_cache_gc(args: argparse.Namespace) -> int:
    course_id = args.course
    course = course_dir(course_id)
    if not args.lesson:
        raise PrepareError(
            "cache-gc requires --lesson to derive P0/Scope from current Snapshot"
        )
    snap = load_current_snapshot(course, args.lesson)
    p0_keys, scope_n, derived_current = derive_scope_from_snapshot(snap)
    p0 = set(p0_keys)
    # Caller may not override P0/scope; optional current_page only for sort distance.
    current_page = (
        args.current_page if args.current_page is not None else derived_current
    )
    # Build rebuildability map: document sha -> pdf path from snapshot document_id
    document_id = str(snap.get("document_id") or args.document_id or "")
    pdf_by_doc: dict[str, Path] = {}
    if document_id:
        try:
            manifest = load_manifest(course, document_id)
            pdf = resolve_pdf_path(course, manifest)
            doc_sha = str(manifest.get("source_document_sha256") or "")
            if pdf.is_file() and doc_sha:
                pdf_by_doc[doc_sha.lower()] = pdf
                pdf_by_doc[doc_sha] = pdf
        except PrepareError:
            pass
    for key in p0_keys:
        if key.source_document_sha256 not in pdf_by_doc:
            # Still record expected sha for rebuild checks
            pass

    entries = list_cache_entries(course)
    planned = plan_eviction(
        entries,
        p0,
        scope_n=scope_n,
        current_page=current_page,
    )
    # Explicit dry-run: default True unless --apply. --dry-run forces dry even if both set incorrectly.
    dry = True
    if args.apply and not args.dry_run:
        dry = False
    if args.dry_run:
        dry = True

    deleted: list[str] = []
    error: str | None = None
    try:
        deleted = apply_eviction(
            planned,
            dry_run=dry,
            course_id=course_id,
            pdf_by_doc_sha=pdf_by_doc,
            p0=p0,
        )
    except PrepareError as exc:
        error = str(exc)
        deleted = []

    audit = {
        "schema": "t2ag.cache_eviction_receipt.v1",
        "course_id": course_id,
        "lesson_id": args.lesson,
        "snapshot_id": snap.get("snapshot_id"),
        "dry_run": dry,
        "cache_n": len(entries),
        "quota_n": min(3 * scope_n, 30),
        "scope_n": scope_n,
        "p0_count": len(p0),
        "p0_page_indices": [k.pdf_page_index for k in p0_keys],
        "planned_deletes": deleted,
        "error": error,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not dry and error is None:
        audit_dir = course / "book" / ".cache" / "eviction_receipts"
        audit_dir.mkdir(parents=True, exist_ok=True)
        rid = "EVICT-" + sha256_text(canonical_json(audit))[:12]
        audit["receipt_id"] = rid
        (audit_dir / f"{rid}.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if error:
        return 2
    return 0


def cmd_verify_ppi(args: argparse.Namespace) -> int:
    """Fail-closed pixel back-calc: PNG pixels must equal MediaBox/72*PPI.

    A render_profile string alone never proves resolution; a scan/load receipt
    claiming pdf-<N>dpi is only credible after this geometry check passes.
    """
    course = course_dir(args.course)
    document_id = args.document_id
    render_profile = args.render_profile
    target_ppi = args.target_ppi or ppi_from_profile(render_profile)

    manifest = load_manifest(course, document_id)
    expected_sha = str(manifest.get("source_document_sha256") or "").strip().lower()
    if not expected_sha or len(expected_sha) != 64:
        raise PrepareError("manifest source_document_sha256 missing or invalid")
    pdf_path = resolve_pdf_path(course, manifest)
    if not pdf_path.is_file():
        raise PrepareError(f"SourceDocument/PDF missing: {pdf_path}")
    actual_sha = sha256_file(pdf_path).lower()
    if actual_sha != expected_sha:
        raise PrepareError(
            f"PDF SHA mismatch: file={actual_sha} manifest={expected_sha}"
        )

    pages = [int(x) for x in args.pages.split(",") if x.strip()]
    if not pages:
        raise PrepareError("--pages must list at least one pdf_page_index")
    if args.png and len(pages) != 1:
        raise PrepareError("--png checks a single page; pass exactly one --pages value")

    results: list[dict[str, Any]] = []
    all_ok = True
    for page in pages:
        if args.png:
            png = Path(args.png).expanduser().resolve()
        else:
            # CACHE_REL already starts with book/; base must be the course dir.
            png = PageKey(expected_sha, page, render_profile).cache_path(
                course_dir(args.course)
            )
        row: dict[str, Any] = {
            "pdf_page_index": page,
            "render_profile": render_profile,
            "png": str(png),
        }
        if not png.is_file():
            row["ok"] = False
            row["error"] = "cached PNG missing; render then re-verify"
            all_ok = False
            results.append(row)
            continue
        try:
            mediabox = pdf_page_mediabox_pt(pdf_path, page)
            row["mediabox_pt"] = [round(mediabox[0], 3), round(mediabox[1], 3)]
            check = verify_png_ppi(
                png,
                mediabox_pt=mediabox,
                target_ppi=target_ppi,
                tolerance_px=args.tolerance_px,
            )
        except PrepareError as exc:
            row["ok"] = False
            row["error"] = str(exc)
            all_ok = False
            results.append(row)
            continue
        row.update(check)
        row["ok"] = bool(check["ppi_ok"])
        if not row["ok"]:
            row["error"] = (
                "pixel back-calc does not reach claimed PPI; "
                "refusing scan receipt for this profile"
            )
            all_ok = False
        results.append(row)

    print(
        json.dumps(
            {
                "schema": "t2ag.source_page_ppi_check.v1",
                "course_id": args.course,
                "document_id": document_id,
                "source_document_sha256": expected_sha,
                "pdf_path": str(pdf_path),
                "target_ppi": target_ppi,
                "render_profile": render_profile,
                "ok": all_ok,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_ok else 2


def cmd_prepare(args: argparse.Namespace) -> int:
    """Fail-closed prepare: validate PDF/assets/map before any Snapshot write."""
    course = course_dir(args.course)
    lesson = args.lesson
    document_id = args.document_id
    render_profile = args.render_profile

    # 1) Manifest + PDF + SHA
    manifest = load_manifest(course, document_id)
    expected_sha = str(manifest.get("source_document_sha256") or "").strip().lower()
    if args.document_sha:
        if args.document_sha.strip().lower() != expected_sha:
            raise PrepareError("CLI --document-sha does not match manifest")
    if not expected_sha or len(expected_sha) != 64:
        raise PrepareError("manifest source_document_sha256 missing or invalid")
    pdf_path = resolve_pdf_path(course, manifest)
    if not pdf_path.is_file():
        raise PrepareError(f"SourceDocument/PDF missing: {pdf_path}")
    actual_sha = sha256_file(pdf_path).lower()
    if actual_sha != expected_sha:
        raise PrepareError(
            f"PDF SHA mismatch: file={actual_sha} manifest={expected_sha}"
        )

    # 2) Available pages: explicit or manifest.pages or fail
    if args.available:
        pages = [int(x) for x in args.available.split(",") if x.strip()]
    else:
        raw_pages = manifest.get("pages") or []
        if isinstance(raw_pages, list) and raw_pages:
            pages = []
            for item in raw_pages:
                if isinstance(item, dict) and "pdf_page_index" in item:
                    pages.append(int(item["pdf_page_index"]))
                else:
                    pages.append(int(item))
        else:
            count = int(manifest.get("available_page_count") or 0)
            if count <= 0:
                raise PrepareError(
                    "no --available and manifest has no pages/available_page_count"
                )
            pages = list(range(1, count + 1))

    if args.preserve_current_scope:
        current_snap = load_current_snapshot(course, lesson)
        if current_snap.get("document_id") != document_id:
            raise PrepareError("current Snapshot document_id does not match prepare target")
        if str(current_snap.get("source_document_sha256") or "").lower() != expected_sha:
            raise PrepareError("current Snapshot document SHA does not match manifest")
        current_keys = current_snap.get("page_keys") or []
        window = [int(item["pdf_page_index"]) for item in current_keys]
        if not window or window != list(range(min(window), max(window) + 1)):
            raise PrepareError("current Snapshot Scope is empty or non-continuous")
        if args.current not in window:
            raise PrepareError("--current is not inside the preserved current Scope")
        if not set(window).issubset(set(pages)):
            raise PrepareError("preserved current Scope is not available in manifest")
        profiles = {str(item.get("render_profile") or "") for item in current_keys}
        if profiles != {render_profile}:
            raise PrepareError("preserved current Scope render profile does not match CLI")
        short = bool(current_snap.get("short_document"))
    else:
        window, short = continuous_scope(args.current, pages, target=args.target)
    keys = [PageKey(expected_sha, p, render_profile) for p in window]

    # 3) Every scope page: verified SourcePageAsset (no missing: placeholders)
    verified_pages: list[tuple[PageKey, str, str]] = []
    for key in keys:
        text, asset_sha, _meta = verify_page_asset(
            course,
            document_id,
            key.pdf_page_index,
            expected_doc_sha=expected_sha,
            render_profile=render_profile,
        )
        if text.startswith("missing:") or f"missing:{key.pdf_page_index}" in text:
            raise PrepareError(
                f"refusing missing-page placeholder as verified asset: "
                f"page_{key.pdf_page_index}"
            )
        verified_pages.append((key, text, asset_sha))

    # 4) LessonMap must exist and cover entire Scope (no auto-forge rows)
    map_path = course / "lessons" / lesson / "lesson_map.md"
    if not map_path.is_file():
        raise PrepareError(f"LessonMap missing: {map_path}")
    # Hash raw file bytes only — never Path.read_text (Windows may rewrite newlines).
    map_raw = map_path.read_bytes()
    map_text = map_raw.decode("utf-8")
    map_sha = sha256_bytes(map_raw)
    missing_map = lesson_map_covers(map_text, window, document_id)
    if missing_map:
        raise PrepareError(f"LessonMap does not cover Scope pages: {missing_map}")

    # 5) Pixel geometry is mandatory for every new receipt. A profile string
    # alone cannot authorize prepare or Snapshot creation.
    receipts: list[LoadReceipt] = []
    for key, text, asset_sha in verified_pages:
        png = key.cache_path(course)
        evidence = build_page_ppi_evidence(pdf_path, png, key)
        receipts.append(
            make_receipt(
                key,
                text,
                source_page_asset_sha256=asset_sha,
                source_document_sha256=expected_sha,
                ppi_evidence=evidence,
            )
        )

    scope_version = "SCOPE-" + sha256_text(
        canonical_json([k.as_dict() for k in keys])
    )[:12]
    prev_id = None
    pointer_path = current_pointer_path(course, lesson)
    if pointer_path.is_file():
        try:
            prev = json.loads(pointer_path.read_text(encoding="utf-8"))
            prev_id = prev.get("snapshot_id")
        except (OSError, json.JSONDecodeError):
            prev_id = None

    snap = build_snapshot(
        lesson_id=lesson,
        scope_version=scope_version,
        page_keys=keys,
        receipts=receipts,
        lesson_map_sha256=map_sha,
        lesson_map_bytes=map_raw,
        source_document_sha256=expected_sha,
        document_id=document_id,
        short_document=short,
        previous_snapshot_id=prev_id,
        prepared_by=args.prepared_by,
    )
    # Pass map_text for coverage only; hash re-checked from file bytes inside.
    closure = validate_snapshot_closure(course, lesson, snap, map_text=None)
    if closure:
        raise PrepareError(f"snapshot closure failed: {closure}")

    result: dict[str, Any] = {
        "write": bool(args.write),
        "short_document": short,
        "scope_pages": window,
        "quota_n": min(3 * len(window), 30),
        "snapshot": snap,
        "source_document_sha256": expected_sha,
        "pdf_path": str(pdf_path),
    }

    if args.write:
        out = snapshot_path(course, lesson, snap["snapshot_id"])
        out.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(snap, ensure_ascii=False, indent=2) + "\n"
        if out.is_file():
            try:
                existing_obj = json.loads(out.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PrepareError(
                    f"existing Snapshot unreadable, refusing overwrite: {out.name}: {exc}"
                ) from exc
            if (
                durable_snapshot_payload(existing_obj)
                == durable_snapshot_payload(snap)
            ):
                write_current_pointer(
                    course,
                    lesson,
                    snapshot_id=snap["snapshot_id"],
                    body_sha256=snap["snapshot_body_sha256"],
                )
                result["written"] = str(out.relative_to(ROOT))
                result["idempotent"] = True
            else:
                raise PrepareError(
                    f"refusing overwrite of existing Snapshot with different body: "
                    f"{out.name}"
                )
        else:
            # Exclusive create: write only if absent
            fd = None
            try:
                fd = out.open("x", encoding="utf-8")
                fd.write(body)
            except FileExistsError as exc:
                raise PrepareError(
                    f"Snapshot file raced into existence: {out.name}"
                ) from exc
            finally:
                if fd is not None:
                    fd.close()
            write_current_pointer(
                course,
                lesson,
                snapshot_id=snap["snapshot_id"],
                body_sha256=snap["snapshot_body_sha256"],
            )
            result["written"] = str(out.relative_to(ROOT))
            result["idempotent"] = False
        result["current_pointer"] = str(
            current_pointer_path(course, lesson).relative_to(ROOT)
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="EV-0012 source page prepare / cache-gc")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scope", help="Compute continuous LessonScope")
    s.add_argument("--current", type=int, required=True)
    s.add_argument("--available", required=True, help="comma-separated pdf page indices")
    s.add_argument("--target", type=int, default=5)
    s.set_defaults(func=cmd_scope)

    g = sub.add_parser("cache-gc", help="CacheEviction dry-run or apply")
    g.add_argument("--course", required=True)
    g.add_argument(
        "--lesson",
        required=True,
        help="Lesson id whose current Snapshot derives P0/Scope/quota",
    )
    g.add_argument("--document-id", default="")
    g.add_argument(
        "--current-page",
        type=int,
        default=None,
        help="optional sort distance hint only; does not redefine P0",
    )
    g.add_argument(
        "--dry-run",
        action="store_true",
        help="plan only (default when --apply is absent)",
    )
    g.add_argument(
        "--apply",
        action="store_true",
        help="actually unlink rebuildable non-P0 cache files",
    )
    g.set_defaults(func=cmd_cache_gc)

    vp = sub.add_parser(
        "verify-ppi",
        help="Back-calc PNG pixels vs PDF MediaBox to prove claimed PPI",
    )
    vp.add_argument("--course", required=True)
    vp.add_argument("--document-id", required=True)
    vp.add_argument(
        "--pages",
        required=True,
        help="comma-separated 1-based pdf_page_index values",
    )
    vp.add_argument("--render-profile", default=RENDER_PROFILE_DEFAULT)
    vp.add_argument(
        "--target-ppi",
        type=int,
        default=0,
        help="default: derived from render_profile (pdf-<N>dpi)",
    )
    vp.add_argument(
        "--tolerance-px",
        type=int,
        default=1,
        help="allowed per-axis rounding delta vs round(MediaBox/72*ppi)",
    )
    vp.add_argument(
        "--png",
        default="",
        help="explicit PNG path instead of the cache key path (single page only)",
    )
    vp.set_defaults(func=cmd_verify_ppi)

    pr = sub.add_parser("prepare", help="Build scope + load receipts + snapshot")
    pr.add_argument("--course", required=True)
    pr.add_argument("--lesson", required=True)
    pr.add_argument(
        "--current",
        type=int,
        required=True,
        help="current teaching page (pdf index)",
    )
    pr.add_argument("--available", default="")
    pr.add_argument("--target", type=int, default=5)
    pr.add_argument("--document-id", required=True)
    pr.add_argument("--document-sha", default="")
    pr.add_argument("--render-profile", default=RENDER_PROFILE_DEFAULT)
    pr.add_argument(
        "--preserve-current-scope",
        action="store_true",
        help=(
            "reuse the exact page_keys of the valid current Snapshot; for metadata/"
            "receipt refresh only, never for page turns"
        ),
    )
    pr.add_argument("--prepared-by", default="t2ag_source_pages")
    pr.add_argument("--write", action="store_true")
    pr.set_defaults(func=cmd_prepare)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
