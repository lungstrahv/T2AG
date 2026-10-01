"""Optional PDF inspection/rendering and strictly derived page-cache maintenance.

PyMuPDF is imported only when PDF work is requested. Public API references:
https://pymupdf.readthedocs.io/en/latest/document.html
https://pymupdf.readthedocs.io/en/latest/page.html

No function creates scan/session/permission facts. A PNG and a layout hint are
not evidence that a human or agent consumed a page in the current conversation.
PDF page labels are metadata, distinct from visually verified printed labels.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import time
import uuid
import zlib

from .journal import Journal
from .model import DomainError, get, require

_FORMAT = "t2ag.page-cache.v1"
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_PNG = b"\x89PNG\r\n\x1a\n"


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _backend():
    try:
        return importlib.import_module("pymupdf")
    except ImportError as exc:
        raise DomainError("PDF_DEPENDENCY_UNAVAILABLE", "PDF rendering requires the optional PyMuPDF dependency; core journal operations do not.") from exc


def _plain(path):
    path = Path(path).absolute()
    for ancestor in (path, *path.parents):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
                    "CACHE_UNSAFE_PATH", "Cache/source storage cannot traverse a symlink or reparse point.")
    return path


def _source(instance, source_id):
    store = Journal(_plain(instance))
    state = store.read_state()
    source = get(state, "source", source_id)
    digest = source.get("blob_sha256")
    require(source.get("format", source.get("source_type")) == "pdf" and isinstance(digest, str) and _SHA.fullmatch(digest),
            "PDF_SOURCE_REQUIRED", "Choose a registered immutable PDF source blob.")
    expected = source.get("content_sha256", source.get("source_version"))
    require(expected in (None, digest), "PDF_SOURCE_IDENTITY", "Source content identity differs from its blob.")
    # Actual source consumption always hashes bytes, even after a metadata-only
    # journal/context recovery. This is the asset-validation boundary.
    content = store.read_blob(digest)
    return state, source, content, digest


@contextmanager
def _pdf(instance, source_id):
    backend = _backend()
    state, source, content, digest = _source(instance, source_id)
    try:
        document = backend.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise DomainError("PDF_INVALID", "The verified source bytes cannot be opened as a PDF.") from exc
    try:
        require(document.is_pdf and not document.needs_pass, "PDF_LOCKED", "An unlocked PDF source is required.")
        require(not document.is_repaired, "PDF_REPAIRED", "PDF parser repaired this input; explicit source review is required before caching.")
        require(document.page_count > 0, "PDF_EMPTY", "The PDF has no pages.")
        yield document, backend, state, source, digest
    finally:
        document.close()


def _pages(indices, count):
    require(isinstance(indices, (list, tuple)) and bool(indices) and all(type(i) is int and 1 <= i <= count for i in indices),
            "PDF_PAGE_RANGE", "Use one-based physical PDF page indices within the source.")
    require(len(indices) == len(set(indices)), "PDF_DUPLICATE_PAGE", "Page indices must be unique.")
    return list(indices)


def _geometry(page, index):
    return {"pdf_page_index": index, "pdf_page_label": page.get_label() or None,
            "printed_page_label": None, "printed_label_status": "not_visually_verified",
            "width_points": float(page.rect.width), "height_points": float(page.rect.height),
            "rotation_degrees": int(page.rotation), "rendered_box": "visible PDF crop box after page rotation"}


def inspect_pdf(instance, source_id):
    with _pdf(instance, source_id) as (doc, backend, state, source, digest):
        return {"ok": True, "source_id": source_id, "source_sha256": digest,
                "source_object_version": state["objects"]["source/" + source_id]["version"],
                "physical_page_count": doc.page_count, "registered_page_count": source.get("page_count"),
                "page_count_matches_registered": source.get("page_count") in (None, doc.page_count),
                "backend": "PyMuPDF", "backend_version": backend.VersionBind,
                "content_hash_verified": True, "current_session_consumed": False}


def _layout(page, index):
    text = page.get_text("text")
    blocks = page.get_text("blocks")
    drawings = page.get_drawings()
    images = page.get_images(full=True)
    hints = []
    if images:
        hints.append("embedded_images")
    if drawings:
        hints.append("vector_graphics_or_rules")
    if page.rotation:
        hints.append("rotated_page")
    if not text.strip():
        hints.append("no_extractable_text")
    return {**_geometry(page, index), "machine_extracted_text": text,
            "text_status": "machine_extracted_unverified", "text_block_count": len(blocks),
            "embedded_image_count": len(images), "vector_path_count": len(drawings),
            "layout_hints": hints, "layout_critical": True if hints else "unknown",
            "requires_visual_review": True, "current_session_consumed": False,
            "limitation": "No layout hints does not prove text-only adequacy; equations, reading order and printed labels require source review."}


def layout_scan(instance, source_id, page_indices):
    with _pdf(instance, source_id) as (doc, _, _, _, digest):
        pages = [_layout(doc.load_page(index - 1), index) for index in _pages(page_indices, doc.page_count)]
        return {"ok": True, "source_id": source_id, "source_sha256": digest,
                "content_hash_verified": True, "pages": pages, "teaching_scan_complete": False}


def verify_ppi(image_bytes, page_width_points, page_height_points, requested_dpi):
    """Check real PNG dimensions/DPI against the measured visible PDF rectangle."""
    require(isinstance(image_bytes, bytes) and image_bytes.startswith(_PNG), "PNG_INVALID", "Expected PNG bytes.")
    require(all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x > 0
                for x in (page_width_points, page_height_points, requested_dpi)), "PPI_INPUT", "Positive finite geometry and DPI are required.")
    offset, dimensions, ppm, ended = 8, None, None, False
    compressed, channels = [], None
    while offset + 12 <= len(image_bytes):
        size = struct.unpack(">I", image_bytes[offset:offset + 4])[0]
        kind = image_bytes[offset + 4:offset + 8]
        end = offset + 12 + size
        require(end <= len(image_bytes), "PNG_INVALID", "Truncated PNG chunk.")
        payload = image_bytes[offset + 8:offset + 8 + size]
        checksum = struct.unpack(">I", image_bytes[offset + 8 + size:end])[0]
        require(zlib.crc32(kind + payload) & 0xffffffff == checksum, "PNG_INVALID", "PNG checksum mismatch.")
        if kind == b"IHDR":
            require(offset == 8 and dimensions is None and len(payload) == 13, "PNG_INVALID", "PNG needs one first valid header.")
            dimensions = struct.unpack(">II", payload[:8])
            depth, color, compression, filtering, interlace = payload[8:]
            channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color)
            require(depth == 8 and channels and compression == filtering == interlace == 0,
                    "PNG_UNSUPPORTED", "PPI verification accepts noninterlaced 8-bit grayscale/RGB PNGs.")
            require(0 < dimensions[0] * dimensions[1] <= 40000000, "PIXEL_LIMIT", "PNG dimensions exceed the verifier pixel limit.")
        elif kind == b"pHYs":
            require(len(payload) == 9, "PNG_INVALID", "Invalid PNG density metadata.")
            x, y, unit = struct.unpack(">IIB", payload)
            if unit == 1:
                ppm = (x, y)
        elif kind == b"IDAT":
            require(dimensions is not None, "PNG_INVALID", "PNG image data precedes its header.")
            compressed.append(payload)
        elif kind == b"IEND":
            ended = True
            require(size == 0 and end == len(image_bytes), "PNG_INVALID", "Unexpected trailing PNG content.")
            break
        offset = end
    require(ended and dimensions and min(dimensions) > 0, "PNG_INVALID", "Complete PNG header and end marker are required.")
    require(ppm, "PPI_MISSING", "PNG physical DPI metadata is required.")
    width, height = dimensions
    require(bool(compressed), "PNG_INVALID", "PNG image data is missing.")
    stride = width * channels + 1
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(b"".join(compressed), height * stride + 1)
        require(decoder.eof and not decoder.unused_data and len(pixels) == height * stride
                and all(pixels[row * stride] <= 4 for row in range(height)), "PNG_INVALID", "PNG pixel rows are incomplete or malformed.")
    except zlib.error as exc:
        raise DomainError("PNG_INVALID", "PNG pixel stream cannot be decoded.") from exc
    dpi_x, dpi_y = ppm[0] * .0254, ppm[1] * .0254
    require(abs(dpi_x - requested_dpi) <= .1 and abs(dpi_y - requested_dpi) <= .1,
            "PPI_MISMATCH", "PNG physical density differs from requested DPI.")
    require(abs(width - page_width_points * requested_dpi / 72) <= 1.1 and
            abs(height - page_height_points * requested_dpi / 72) <= 1.1,
            "PAGE_RENDER_GEOMETRY", "PNG does not cover the expected whole visible PDF page at this DPI.")
    return {"ok": True, "width_pixels": width, "height_pixels": height,
            "png_dpi_x": round(dpi_x, 4), "png_dpi_y": round(dpi_y, 4),
            "effective_ppi_x": round(width * 72 / page_width_points, 4),
            "effective_ppi_y": round(height * 72 / page_height_points, 4), "requested_dpi": requested_dpi,
            "whole_visible_page_geometry_verified": True, "visual_readability_verified": False}


def _cache(instance):
    root = _plain(instance)
    cache = _plain(root / "derived/page-cache")
    require(cache.is_relative_to(root), "CACHE_UNSAFE_PATH", "Cache must be inside the selected instance derived directory.")
    return cache


def _atomic(path, content):
    _plain(path)
    temporary = path.with_name(".pending-" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        handle = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)


def _parameters(source_sha256, index, dpi, backend_version):
    return {"source_sha256": source_sha256, "pdf_page_index": index, "dpi": dpi,
            "render_profile": f"pdf-{dpi}dpi-rgb-v1", "backend": "PyMuPDF", "backend_version": backend_version, "colorspace": "RGB", "alpha": False}


def _index(cache):
    path = _plain(cache / "index.json")
    if not path.exists():
        return {"format": _FORMAT, "entries": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, OSError) as exc:
        raise DomainError("CACHE_INDEX_INVALID", "Derived cache index is unreadable; no files were deleted.") from exc
    require(isinstance(value, dict) and value.get("format") == _FORMAT and isinstance(value.get("entries"), dict),
            "CACHE_INDEX_INVALID", "Cache index format differs.")
    for cache_key, record in value["entries"].items():
        require(isinstance(cache_key, str) and _SHA.fullmatch(cache_key) and isinstance(record, dict),
                "CACHE_INDEX_INVALID", "Cache identity is invalid.")
        params = record.get("parameters")
        require(isinstance(params, dict) and set(params) == {"source_sha256", "pdf_page_index", "dpi", "render_profile", "backend", "backend_version", "colorspace", "alpha"}
                and isinstance(params.get("source_sha256"), str) and _SHA.fullmatch(params["source_sha256"])
                and type(params.get("pdf_page_index")) is int and params["pdf_page_index"] > 0
                and type(params.get("dpi")) is int and 200 <= params["dpi"] <= 600
                and params.get("render_profile") == f"pdf-{params['dpi']}dpi-rgb-v1"
                and params.get("backend") == "PyMuPDF" and isinstance(params.get("backend_version"), str)
                and bool(params["backend_version"]) and params.get("colorspace") == "RGB" and params.get("alpha") is False
                and _digest(params) == cache_key and record.get("file") == cache_key + ".png"
                and isinstance(record.get("sha256"), str) and _SHA.fullmatch(record["sha256"])
                and type(record.get("bytes")) is int and record["bytes"] >= 0,
                "CACHE_INDEX_INVALID", "Cache record identity/path/hash metadata differs.")
        require(isinstance(record.get("geometry"), dict), "CACHE_INDEX_INVALID", "Cache page geometry is missing.")
        _plain(cache / record["file"])
    return value


def _image(cache, record):
    path = _plain(cache / record["file"])
    require(path.is_file(), "CACHE_IMAGE_MISSING", "Cached page image is missing.")
    data = path.read_bytes()
    require(len(data) == record["bytes"] and hashlib.sha256(data).hexdigest() == record["sha256"],
            "CACHE_IMAGE_CORRUPT", "Cached page image differs from its manifest.")
    return data


def prewarm_pages(instance, source_id, page_indices, *, dpi=300, max_pixels=40000000, repair=False):
    require(type(dpi) is int and 200 <= dpi <= 600, "PPI_RANGE", "Use 300 DPI by default; explicit profiles may range from 200 to 600 DPI.")
    require(type(max_pixels) is int and 0 < max_pixels <= 40000000, "PIXEL_LIMIT", "Use a render limit of one to forty million pixels.")
    require(type(repair) is bool, "CACHE_REPAIR", "Cache repair must be an explicit boolean.")
    cache = _cache(instance)
    with _pdf(instance, source_id) as (doc, backend, state, _, digest):
        indices = _pages(page_indices, doc.page_count)
        records = []
        # A separate OS-released lock serializes this derived cache only; no
        # journal transaction lock is held throughout slow rendering.
        with Journal(cache)._lock():
            index = _index(cache)
            for number in indices:
                page = doc.load_page(number - 1)
                geometry = _geometry(page, number)
                require(math.ceil(page.rect.width * dpi / 72) * math.ceil(page.rect.height * dpi / 72) <= max_pixels,
                        "PIXEL_LIMIT", "Requested whole-page rendering exceeds the explicit pixel limit.")
                params = _parameters(digest, number, dpi, backend.VersionBind)
                identity = _digest(params)
                old = index["entries"].get(identity)
                repaired = False
                if old:
                    try:
                        data = _image(cache, old)
                        check = verify_ppi(data, page.rect.width, page.rect.height, dpi)
                    except DomainError as exc:
                        repairable = {"CACHE_IMAGE_MISSING", "CACHE_IMAGE_CORRUPT", "PNG_INVALID", "PNG_UNSUPPORTED", "PPI_MISSING", "PPI_MISMATCH", "PAGE_RENDER_GEOMETRY"}
                        if not repair or exc.code not in repairable:
                            raise
                        old, repaired = None, True
                if old:
                    record = deepcopy(old)
                    record["reused"] = True
                else:
                    try:
                        pixmap = page.get_pixmap(dpi=dpi, colorspace=backend.csRGB, alpha=False)
                        data = pixmap.tobytes("png")
                    except Exception as exc:
                        raise DomainError("PDF_RENDER_FAILED", "Whole-page rendering failed; no teaching scan was recorded.") from exc
                    check = verify_ppi(data, page.rect.width, page.rect.height, dpi)
                    record = {"parameters": params, "file": identity + ".png", "sha256": hashlib.sha256(data).hexdigest(),
                              "bytes": len(data), "created_at_unix": time.time(), "geometry": geometry,
                              "ppi": check, "source_object_version": state["objects"]["source/" + source_id]["version"]}
                    _atomic(cache / record["file"], data)
                    index["entries"][identity] = record
                    _atomic(cache / "index.json", json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")
                    record = deepcopy(record)
                    record["reused"] = False
                record.update(cache_key=identity, cache_path=str(cache / record["file"]), ppi=check, repaired=repaired,
                              printed_page_label=None, current_session_consumed=False, teaching_scan_complete=False)
                records.append(record)
        return {"ok": True, "source_sha256": digest, "content_hash_verified": True, "pages": records,
                "authority": "derived_render_cache", "teaching_scan_complete": False,
                "canonical_blob_installation": "not performed; a verified page-registration consumer may install the PNG separately"}


def inspect_cache(instance):
    cache = _cache(instance)
    if not cache.exists():
        return {"ok": True, "cache_root": str(cache), "entries": [], "unmanaged_files": []}
    with Journal(cache)._lock():
        index = _index(cache)
        rows = []
        for identity, record in index["entries"].items():
            data = _image(cache, record)
            geometry = record.get("geometry", {})
            check = verify_ppi(data, geometry.get("width_points"), geometry.get("height_points"), record["parameters"].get("dpi"))
            rows.append({"cache_key": identity, **deepcopy(record), "ppi": check})
        managed = {record["file"] for record in index["entries"].values()} | {"index.json", ".writer.lock"}
        return {"ok": True, "cache_root": str(cache), "entries": rows,
                "unmanaged_files": sorted(path.name for path in cache.iterdir() if path.name not in managed),
                "authority": "derived_render_cache", "teaching_scan_complete": False}


def _pinned_pages(state):
    result = set()
    for entity in state["objects"].values():
        data = entity["data"]
        if entity["kind"] != "activity" or data.get("status") in {"completed", "closed_incomplete"}:
            continue
        require(not data.get("legacy_preparation_id") or data.get("scope_id"), "CACHE_PIN_UNRESOLVED", "Reconcile current legacy preparation before deciding which pages may be evicted.")
        if not data.get("scope_id"):
            continue
        scope = get(state, "scope", data["scope_id"])
        for page_id in scope.get("page_ids", []):
            page = get(state, "page", page_id)
            source = get(state, "source", page["source_id"])
            if source.get("blob_sha256"):
                result.add((source["blob_sha256"], page["pdf_page_index"]))
    return result


def _rebuildable_sources(store, state, selected, index):
    if not selected:
        return []
    backend = _backend()
    sources = {e["data"].get("blob_sha256") for e in state["objects"].values()
               if e["kind"] == "source" and e["data"].get("format", e["data"].get("source_type")) == "pdf"}
    documents, verified = {}, []
    try:
        for row in selected:
            record = index["entries"][row["cache_key"]]
            params = record["parameters"]
            sha = params["source_sha256"]
            require(sha in sources and params["backend_version"] == backend.VersionBind,
                    "CACHE_NOT_REBUILDABLE", "The registered source and exact rendering backend must still be available.")
            if sha not in documents:
                # We hold the journal writer lock already; read_blob would
                # reacquire it. This is its same strong content verifier.
                signature = store._blob_stat(sha)
                content = store._verify_blob(sha, return_bytes=True)
                require(store._blob_stat(sha) == signature, "BLOB_CHANGED", "Source changed during rebuildability validation.")
                try:
                    doc = backend.open(stream=content, filetype="pdf")
                except Exception as exc:
                    raise DomainError("CACHE_NOT_REBUILDABLE", "Cached source cannot be opened for reconstruction.") from exc
                documents[sha] = doc
                require(doc.is_pdf and not doc.needs_pass and not doc.is_repaired, "CACHE_NOT_REBUILDABLE", "Cached source is locked or requires repair.")
                verified.append({"sha256": sha, "bytes": len(content), "stat_signature": signature, "content_hash_verified": True})
            doc = documents[sha]
            number = params["pdf_page_index"]
            require(1 <= number <= doc.page_count, "CACHE_NOT_REBUILDABLE", "Cached physical page no longer resolves.")
            page = doc.load_page(number - 1)
            verify_ppi(_image(store.path / "derived/page-cache", record), page.rect.width, page.rect.height, params["dpi"])
        return sorted(verified, key=lambda row: row["sha256"])
    finally:
        for doc in documents.values():
            doc.close()


def gc_cache(instance, *, keep_keys=(), older_than_seconds=86400, dry_run=True, expected_plan_sha256=None):
    require(type(dry_run) is bool, "CACHE_DRY_RUN", "Cache dry_run must be an explicit boolean.")
    require(isinstance(keep_keys, (list, tuple, set)) and all(isinstance(key, str) and _SHA.fullmatch(key) for key in keep_keys),
            "CACHE_KEEP_KEYS", "Keep identities must be cache SHA-256 keys.")
    require(isinstance(older_than_seconds, (int, float)) and not isinstance(older_than_seconds, bool)
            and math.isfinite(older_than_seconds) and older_than_seconds >= 0, "CACHE_AGE", "Cache age must be nonnegative.")
    cache = _cache(instance)
    if not cache.exists():
        return {"ok": True, "dry_run": dry_run, "deleted": [], "candidates": [], "plan_sha256": None}
    store = Journal(instance)
    # Cache first, then journal: prewarming never holds the journal lock while
    # waiting for the cache lock. Hold both during GC so a concurrent activity
    # cannot acquire a new page pin between selection and physical deletion.
    with Journal(cache)._lock(), store._lock():
        index = _index(cache)
        state, _, _, _ = store._read_locked()
        pinned = _pinned_pages(state)
        now = time.time()
        selected = []
        for identity, record in sorted(index["entries"].items()):
            params = record["parameters"]
            born = record.get("created_at_unix")
            require(isinstance(born, (int, float)) and not isinstance(born, bool) and math.isfinite(born), "CACHE_INDEX_INVALID", "Cache creation time is invalid.")
            if identity not in keep_keys and (params.get("source_sha256"), params.get("pdf_page_index")) not in pinned and now - born >= older_than_seconds:
                _image(cache, record)  # exact owned bytes verified before deletion
                selected.append({"cache_key": identity, "file": record["file"], "sha256": record["sha256"], "bytes": record["bytes"]})
        sources = _rebuildable_sources(store, state, selected, index)
        plan = {"cache_root": str(cache), "index_sha256": _digest(index), "state_revision": state["revision"],
                "keep_keys": sorted(keep_keys), "older_than_seconds": older_than_seconds, "candidates": selected, "verified_sources": sources}
        plan_sha = _digest(plan)
        receipt_path = None
        if not dry_run:
            require(expected_plan_sha256 == plan_sha, "CACHE_PLAN_CHANGED", "Recompute the cache deletion plan after any cache or reference change.")
            receipt_path = cache / ("gc-" + plan_sha + ".json")
            receipt = {"format": "t2ag.cache-eviction.v1", "plan": plan, "plan_sha256": plan_sha,
                       "status": "prepared", "started_at_unix": time.time(), "deleted": [], "canonical_blobs_untouched": True}
            _atomic(receipt_path, json.dumps(receipt, sort_keys=True, indent=2).encode() + b"\n")
            require(all(store._blob_stat(source["sha256"]) == source["stat_signature"] for source in sources),
                    "BLOB_CHANGED", "A reconstruction source changed before cache eviction.")
            # All candidates and containment were validated above. Never recurse,
            # follow links, touch canonical blobs, or remove unmanaged files.
            for row in selected:
                index["entries"].pop(row["cache_key"])
            # Publish removal from the derived index first. An interrupted
            # unlink leaves an unmanaged residue, never an index falsely
            # asserting that a deleted page still exists. inspect_cache reports
            # residues; future GC does not recursively erase unknown files.
            _atomic(cache / "index.json", json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n")
            for row in selected:
                try:
                    _plain(cache / row["file"]).unlink()
                except OSError as exc:
                    raise DomainError("CACHE_GC_PARTIAL", "Cache index updated; an image remains as an unmanaged residue.",
                                      {"file": row["file"], "canonical_blobs_untouched": True}) from exc
                receipt["deleted"].append(row["cache_key"])
            receipt.update(status="completed", completed_at_unix=time.time())
            _atomic(receipt_path, json.dumps(receipt, sort_keys=True, indent=2).encode() + b"\n")
        return {"ok": True, "dry_run": dry_run, "candidates": selected,
                "deleted": [] if dry_run else [row["cache_key"] for row in selected], "plan_sha256": plan_sha,
                "pinned_active_pages": len(pinned), "canonical_blobs_untouched": True, "verified_sources": sources,
                "receipt_path": str(receipt_path) if receipt_path else None}
