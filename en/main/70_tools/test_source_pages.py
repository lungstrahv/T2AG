#!/usr/bin/env python3
"""Unit contracts for EV-0012 source page scope, heat, eviction, snapshots, CLI."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import t2ag_source_pages as sp

PPI_MEDIA = (477.071, 727.148)
PPI_PIXELS = (1988, 3030)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _page_asset(
    *,
    document_id: str,
    course_id: str,
    page: int,
    doc_sha: str,
    body: str = "verified body",
    status: str = "verified",
) -> str:
    return (
        "---\n"
        "schema: t2ag.source_page_asset.v1\n"
        f"asset_id: {document_id}-P{page:04d}\n"
        f"course_id: {course_id}\n"
        f"source_document_id: {document_id}\n"
        f"source_document_sha256: {doc_sha}\n"
        f"pdf_page_index: {page}\n"
        f"render_profile: {sp.RENDER_PROFILE_DEFAULT}\n"
        f"verification_status: {status}\n"
        "lifecycle: persistent\n"
        "---\n\n"
        f"# Page {page}\n\n{body}\n"
    )


def _map_for(pages: list[int], document_id: str) -> str:
    rows = "\n".join(
        f"| {i + 1} | {p} | {document_id}-P{p:04d} | node {p} |"
        for i, p in enumerate(pages)
    )
    return (
        "# Lesson Map\n\n"
        "| 序 | pdf_page_index | asset_id / page_key | 节点摘要 |\n"
        "|---:|---:|---|---|\n"
        f"{rows}\n"
    )


def _png_bytes(width: int, height: int) -> bytes:
    """Minimal valid PNG header (IHDR only) with the given pixel dimensions."""
    return (
        sp.PNG_SIGNATURE
        + b"\x00\x00\x00\x0d"
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def _ppi_evidence(key: sp.PageKey) -> dict[str, object]:
    evidence: dict[str, object] = {
        "schema": sp.PPI_EVIDENCE_SCHEMA,
        "page_key": key.as_dict(),
        "target_ppi": 300,
        "mediabox_pt": [round(PPI_MEDIA[0], 3), round(PPI_MEDIA[1], 3)],
        "expected_pixels": list(PPI_PIXELS),
        "actual_pixels": list(PPI_PIXELS),
        "tolerance_px": 1,
        "back_calculated_ppi": [300.03, 300.02],
        "png_sha256": "f" * 64,
        "ppi_ok": True,
    }
    evidence["evidence_sha256"] = sp.ppi_evidence_digest(evidence)
    return evidence


def _fixture_course(root: Path, *, pages: list[int], verified: bool = True) -> tuple[str, str, str]:
    course_id = "MATH_T"
    document_id = "DOC1"
    lesson = "lesson01"
    pdf_bytes = b"%PDF-1.4 fixture for prepare tests\n"
    doc_sha = _sha(pdf_bytes)
    course = root / "main" / "40_course" / course_id
    pdf_path = course / "book" / "primary" / "book.pdf"
    _write(pdf_path, "")  # placeholder; rewrite bytes
    pdf_path.write_bytes(pdf_bytes)
    manifest = {
        "schema": "t2ag.source_document_manifest.v1",
        "document_id": document_id,
        "course_id": course_id,
        "source_path": str(pdf_path.relative_to(root)).replace("\\", "/"),
        "source_document_sha256": doc_sha,
        "render_profile": sp.RENDER_PROFILE_DEFAULT,
        "available_page_count": max(pages),
        "pages": pages,
    }
    man_path = (
        course / "book/primary/source_assets" / document_id / "manifest.json"
    )
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    status = "verified" if verified else "unverified"
    for p in pages:
        asset = course / "book/primary/source_assets" / document_id / "pages" / f"page_{p}.md"
        _write(
            asset,
            _page_asset(
                document_id=document_id,
                course_id=course_id,
                page=p,
                doc_sha=doc_sha,
                status=status,
            ),
        )
        png = (
            course
            / sp.CACHE_REL
            / doc_sha
            / sp.RENDER_PROFILE_DEFAULT
            / f"page_{p}.png"
        )
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(_png_bytes(*PPI_PIXELS))
    _write(
        course / "lessons" / lesson / "lesson_map.md",
        _map_for(pages, document_id),
    )
    return course_id, document_id, doc_sha


class PpiBackCalcTests(unittest.TestCase):
    """Profile strings never prove resolution; only MediaBox-vs-pixel geometry does."""

    MEDIA = PPI_MEDIA  # textbook page 28 example

    def test_ppi_from_profile(self) -> None:
        self.assertEqual(sp.ppi_from_profile("pdf-300dpi-rgb-v1"), 300)
        self.assertEqual(sp.ppi_from_profile("pdf-400dpi-rgb-v1"), 400)
        with self.assertRaises(sp.PrepareError):
            sp.ppi_from_profile("no-claim-here")

    def test_expected_pixels_at_ppi(self) -> None:
        self.assertEqual(sp.expected_pixels_at_ppi(self.MEDIA, 300), (1988, 3030))

    def test_png_dimensions_reads_ihdr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "page_28.png"
            png.write_bytes(_png_bytes(1988, 3030))
            self.assertEqual(sp.png_dimensions(png), (1988, 3030))
            bad = Path(tmp) / "bad.png"
            bad.write_bytes(b"not a png at all, long enough to read 24 bytes!")
            with self.assertRaises(sp.PrepareError):
                sp.png_dimensions(bad)

    def test_verify_png_ppi_pass_and_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok_png = Path(tmp) / "ok.png"
            ok_png.write_bytes(_png_bytes(1988, 3030))
            row = sp.verify_png_ppi(
                ok_png, mediabox_pt=self.MEDIA, target_ppi=300
            )
            self.assertTrue(row["ppi_ok"])
            self.assertEqual(row["back_calculated_ppi"], [300.03, 300.02])

            low_png = Path(tmp) / "low.png"
            low_png.write_bytes(_png_bytes(1193, 1818))  # ~180 dpi render
            row = sp.verify_png_ppi(
                low_png, mediabox_pt=self.MEDIA, target_ppi=300
            )
            self.assertFalse(row["ppi_ok"])

    def test_cli_verify_ppi_geometry_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, doc_sha = _fixture_course(
                root, pages=list(range(25, 31))
            )
            cache = (
                root
                / "main/40_course"
                / course_id
                / "book/.cache/source_pages"
                / doc_sha
                / sp.RENDER_PROFILE_DEFAULT
            )
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "page_28.png").write_bytes(_png_bytes(1988, 3030))
            argv = [
                "verify-ppi",
                "--course",
                course_id,
                "--document-id",
                document_id,
                "--pages",
                "28",
            ]
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ), mock.patch.object(
                sp, "pdf_page_mediabox_pt", return_value=self.MEDIA
            ):
                out = io.StringIO()
                with redirect_stdout(out):
                    code = sp.main(argv)
                self.assertEqual(code, 0)
                payload = json.loads(out.getvalue())
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["results"][0]["actual_pixels"], [1988, 3030])

                # Under-resolution must fail closed: no receipt on name alone.
                (cache / "page_28.png").write_bytes(_png_bytes(1193, 1818))
                out2 = io.StringIO()
                with redirect_stdout(out2):
                    code = sp.main(argv)
                self.assertEqual(code, 2)
                payload = json.loads(out2.getvalue())
                self.assertFalse(payload["ok"])
                self.assertIn("back-calc", payload["results"][0]["error"])

                # Missing PNG also fails closed.
                (cache / "page_28.png").unlink()
                out3 = io.StringIO()
                with redirect_stdout(out3):
                    code = sp.main(argv)
                self.assertEqual(code, 2)
                payload = json.loads(out3.getvalue())
                self.assertFalse(payload["ok"])
                self.assertIn("PNG missing", payload["results"][0]["error"])


class SourcePagesTests(unittest.TestCase):
    def test_continuous_scope_default_five(self) -> None:
        window, short = sp.continuous_scope(28, range(20, 40), target=5)
        self.assertFalse(short)
        self.assertEqual(len(window), 5)
        self.assertIn(28, window)
        self.assertEqual(window, list(range(min(window), max(window) + 1)))

    def test_continuous_scope_book_end_pans(self) -> None:
        pages = list(range(1, 31))
        window, short = sp.continuous_scope(30, pages, target=5)
        self.assertFalse(short)
        self.assertEqual(window, [26, 27, 28, 29, 30])

    def test_short_document_fixed_all_pages(self) -> None:
        window, short = sp.continuous_scope(2, [1, 2, 3], target=5)
        self.assertTrue(short)
        self.assertEqual(window, [1, 2, 3])

    def test_sparse_available_pages_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "sparse"):
            sp.continuous_scope(5, [1, 3, 5, 7, 9, 11], target=5)

    def test_heat_at_uses_max(self) -> None:
        self.assertEqual(
            sp.heat_at(last_in_scope_at=1.0, last_access_at=5.0, created_at=2.0),
            5.0,
        )
        self.assertEqual(
            sp.heat_at(last_in_scope_at=None, last_access_at=None, created_at=None),
            0.0,
        )

    def test_eviction_skips_p0_and_orders_cold_first(self) -> None:
        doc = "a" * 64
        keys = [sp.PageKey(doc, i) for i in (10, 20, 30)]
        p0 = {keys[1]}
        entries = [
            sp.CacheEntry(keys[0], Path("x10"), last_access_at=100.0, created_at=1.0),
            sp.CacheEntry(keys[1], Path("x20"), last_access_at=1.0, created_at=1.0),
            sp.CacheEntry(keys[2], Path("x30"), last_access_at=1.0, created_at=1.0),
        ]
        planned = sp.plan_eviction(entries, p0, scope_n=5, current_page=20, need_free=2)
        self.assertEqual(len(planned), 2)
        self.assertNotIn(keys[1], {e.key for e in planned})
        self.assertEqual(planned[0].key.pdf_page_index, 30)

    def test_snapshot_immutable_ids_differ_on_scope_change(self) -> None:
        doc = "b" * 64
        k1 = [sp.PageKey(doc, i) for i in (1, 2, 3, 4, 5)]
        k2 = [sp.PageKey(doc, i) for i in (2, 3, 4, 5, 6)]
        r1 = [
            sp.make_receipt(
                k,
                f"t{k.pdf_page_index}",
                source_page_asset_sha256="a" * 64,
                source_document_sha256=doc,
                ppi_evidence=_ppi_evidence(k),
            )
            for k in k1
        ]
        r2 = [
            sp.make_receipt(
                k,
                f"t{k.pdf_page_index}",
                source_page_asset_sha256="b" * 64,
                source_document_sha256=doc,
                ppi_evidence=_ppi_evidence(k),
            )
            for k in k2
        ]
        s1 = sp.build_snapshot(
            lesson_id="lesson02",
            scope_version="SCOPE-a",
            page_keys=k1,
            receipts=r1,
            lesson_map_text="map-a",
            source_document_sha256=doc,
            document_id="DOC",
            short_document=False,
        )
        s2 = sp.build_snapshot(
            lesson_id="lesson02",
            scope_version="SCOPE-b",
            page_keys=k2,
            receipts=r2,
            lesson_map_text="map-b",
            source_document_sha256=doc,
            document_id="DOC",
            short_document=False,
            previous_snapshot_id=s1["snapshot_id"],
        )
        self.assertNotEqual(s1["snapshot_id"], s2["snapshot_id"])
        self.assertTrue(s1["content_consumed"])
        self.assertEqual(s2["previous_snapshot_id"], s1["snapshot_id"])
        self.assertEqual(s1["source_document_sha256"], doc)

    def test_make_receipt_rejects_tampered_ppi_evidence(self) -> None:
        key = sp.PageKey("b" * 64, 1)
        evidence = _ppi_evidence(key)
        evidence["actual_pixels"] = [100, 100]
        with self.assertRaisesRegex(sp.PrepareError, "PPI evidence"):
            sp.make_receipt(
                key,
                "verified text",
                source_page_asset_sha256="a" * 64,
                source_document_sha256=key.source_document_sha256,
                ppi_evidence=evidence,
            )

    def test_cache_gc_refuses_non_cache_path(self) -> None:
        entry = sp.CacheEntry(
            sp.PageKey("c" * 64, 1),
            Path("main/40_course/X/book/primary/nope.png"),
        )
        with self.assertRaises(sp.PrepareError):
            sp.apply_eviction(
                [entry],
                dry_run=False,
                course_id="X",
                pdf_by_doc_sha={},
                p0=set(),
            )

    def test_cache_gc_refuses_p0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = "C1"
            # monkeypatch course paths via absolute path in entry under a fake cache
            cache = root / "book" / ".cache" / "source_pages" / ("d" * 64) / sp.RENDER_PROFILE_DEFAULT
            png = cache / "page_1.png"
            png.parent.mkdir(parents=True, exist_ok=True)
            png.write_bytes(b"png")
            key = sp.PageKey("d" * 64, 1)
            entry = sp.CacheEntry(key, png)
            with mock.patch.object(sp, "course_dir", return_value=root):
                with mock.patch.object(sp, "cache_root", return_value=root / "book" / ".cache"):
                    with self.assertRaisesRegex(sp.PrepareError, "P0"):
                        sp.apply_eviction(
                            [entry],
                            dry_run=False,
                            course_id=course,
                            pdf_by_doc_sha={"d" * 64: root / "book.pdf"},
                            p0={key},
                        )

    def test_cli_scope_json(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sp.main(
                ["scope", "--current", "5", "--available", "1,2,3,4,5,6,7,8", "--target", "5"]
            )
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["scope_n"], 5)

    def test_cli_prepare_requires_current_not_current_page(self) -> None:
        parser = sp.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "prepare",
                    "--course",
                    "X",
                    "--lesson",
                    "lesson01",
                    "--current-page",
                    "1",
                    "--document-id",
                    "DOC",
                ]
            )
        args = parser.parse_args(
            [
                "prepare",
                "--course",
                "X",
                "--lesson",
                "lesson01",
                "--current",
                "1",
                "--document-id",
                "DOC",
            ]
        )
        self.assertEqual(args.current, 1)

    def test_cli_cache_gc_accepts_dry_run_flag(self) -> None:
        parser = sp.build_parser()
        args = parser.parse_args(
            [
                "cache-gc",
                "--course",
                "X",
                "--lesson",
                "lesson01",
                "--dry-run",
            ]
        )
        self.assertTrue(args.dry_run)
        self.assertFalse(args.apply)

    def test_cache_gc_discovers_real_course_cache_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, doc_sha = _fixture_course(
                root, pages=list(range(1, 6))
            )
            snap = {
                "snapshot_id": "PREP-test",
                "document_id": document_id,
                "page_keys": [
                    sp.PageKey(doc_sha, page).as_dict() for page in range(1, 6)
                ],
            }
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ), mock.patch.object(sp, "load_current_snapshot", return_value=snap):
                out = io.StringIO()
                with redirect_stdout(out):
                    code = sp.main(
                        [
                            "cache-gc",
                            "--course",
                            course_id,
                            "--lesson",
                            "lesson01",
                            "--dry-run",
                        ]
                    )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["cache_n"], 5)

    def test_prepare_fail_closed_missing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ):
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    code = sp.main(
                        [
                            "prepare",
                            "--course",
                            "NOPE",
                            "--lesson",
                            "lesson01",
                            "--current",
                            "1",
                            "--document-id",
                            "DOC",
                            "--available",
                            "1,2,3,4,5",
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertIn("manifest", err.getvalue().lower())

    def test_prepare_fail_closed_pdf_sha_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, doc_sha = _fixture_course(
                root, pages=list(range(1, 6))
            )
            # Corrupt PDF after hashing into manifest
            pdf = root / "main/40_course" / course_id / "book/primary/book.pdf"
            pdf.write_bytes(b"%PDF-1.4 corrupted different bytes\n")
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ):
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    code = sp.main(
                        [
                            "prepare",
                            "--course",
                            course_id,
                            "--lesson",
                            "lesson01",
                            "--current",
                            "3",
                            "--document-id",
                            document_id,
                            "--available",
                            "1,2,3,4,5",
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertIn("SHA mismatch", err.getvalue())

    def test_prepare_fail_closed_unverified_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, _ = _fixture_course(
                root, pages=list(range(1, 6)), verified=False
            )
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ):
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    code = sp.main(
                        [
                            "prepare",
                            "--course",
                            course_id,
                            "--lesson",
                            "lesson01",
                            "--current",
                            "3",
                            "--document-id",
                            document_id,
                            "--available",
                            "1,2,3,4,5",
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertIn("not verified", err.getvalue())

    def test_prepare_fail_closed_map_missing_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, _ = _fixture_course(
                root, pages=list(range(1, 6))
            )
            map_path = (
                root / "main/40_course" / course_id / "lessons/lesson01/lesson_map.md"
            )
            # Map only covers 1-4
            _write(map_path, _map_for([1, 2, 3, 4], document_id))
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ):
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    code = sp.main(
                        [
                            "prepare",
                            "--course",
                            course_id,
                            "--lesson",
                            "lesson01",
                            "--current",
                            "3",
                            "--document-id",
                            document_id,
                            "--available",
                            "1,2,3,4,5",
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertIn("LessonMap", err.getvalue())

    def test_prepare_write_idempotent_and_refuses_body_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, _ = _fixture_course(
                root, pages=list(range(1, 6))
            )
            argv = [
                "prepare",
                "--course",
                course_id,
                "--lesson",
                "lesson01",
                "--current",
                "3",
                "--document-id",
                document_id,
                "--available",
                "1,2,3,4,5",
                "--write",
            ]
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ), mock.patch.object(
                sp, "pdf_page_mediabox_pt", return_value=PPI_MEDIA
            ):
                out1 = io.StringIO()
                with redirect_stdout(out1):
                    self.assertEqual(sp.main(argv), 0)
                p1 = json.loads(out1.getvalue())
                self.assertEqual(
                    p1["snapshot"]["schema"], sp.SNAPSHOT_SCHEMA_CURRENT
                )
                for receipt in p1["snapshot"]["load_receipts"]:
                    self.assertIsNone(
                        sp.validate_ppi_evidence(
                            receipt["ppi_evidence"],
                            sp.PageKey(**receipt["page_key"]),
                        )
                    )
                snap_id = p1["snapshot"]["snapshot_id"]
                path = (
                    root
                    / "main/40_course"
                    / course_id
                    / "lessons/lesson01/preparation"
                    / f"{snap_id}.json"
                )
                self.assertTrue(path.is_file())
                pointer = (
                    root
                    / "main/40_course"
                    / course_id
                    / "lessons/lesson01/preparation"
                    / sp.CURRENT_POINTER_NAME
                )
                self.assertTrue(pointer.is_file())

                out2 = io.StringIO()
                with redirect_stdout(out2):
                    self.assertEqual(sp.main(argv), 0)
                p2 = json.loads(out2.getvalue())
                self.assertTrue(p2.get("idempotent"))

                # Corrupt body with same id file
                corrupt = json.loads(path.read_text(encoding="utf-8"))
                corrupt["prepared_by"] = "attacker"
                path.write_text(json.dumps(corrupt, indent=2) + "\n", encoding="utf-8")
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    code = sp.main(argv)
                self.assertEqual(code, 2)
                self.assertIn("overwrite", err.getvalue().lower())

    def test_prepare_refuses_missing_ppi_image_before_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, doc_sha = _fixture_course(
                root, pages=list(range(1, 6))
            )
            missing = (
                root
                / "main/40_course"
                / course_id
                / sp.CACHE_REL
                / doc_sha
                / sp.RENDER_PROFILE_DEFAULT
                / "page_3.png"
            )
            missing.unlink()
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ), mock.patch.object(
                sp, "pdf_page_mediabox_pt", return_value=PPI_MEDIA
            ):
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    code = sp.main(
                        [
                            "prepare",
                            "--course",
                            course_id,
                            "--lesson",
                            "lesson01",
                            "--current",
                            "3",
                            "--document-id",
                            document_id,
                            "--available",
                            "1,2,3,4,5",
                        ]
                    )
            self.assertEqual(code, 2)
            self.assertIn("page_3.png", err.getvalue())

    def test_prepare_can_refresh_receipts_without_changing_current_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, _ = _fixture_course(
                root, pages=list(range(1, 7))
            )
            base = [
                "prepare",
                "--course",
                course_id,
                "--lesson",
                "lesson01",
                "--document-id",
                document_id,
                "--available",
                "1,2,3,4,5,6",
            ]
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ), mock.patch.object(
                sp, "pdf_page_mediabox_pt", return_value=PPI_MEDIA
            ):
                first = io.StringIO()
                with redirect_stdout(first):
                    self.assertEqual(sp.main([*base, "--current", "6", "--write"]), 0)
                self.assertEqual(json.loads(first.getvalue())["scope_pages"], [2, 3, 4, 5, 6])

                refreshed = io.StringIO()
                with redirect_stdout(refreshed):
                    self.assertEqual(
                        sp.main(
                            [
                                *base,
                                "--current",
                                "3",
                                "--preserve-current-scope",
                            ]
                        ),
                        0,
                    )
                self.assertEqual(
                    json.loads(refreshed.getvalue())["scope_pages"],
                    [2, 3, 4, 5, 6],
                )

    def test_prepare_does_not_write_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, _ = _fixture_course(
                root, pages=list(range(1, 6)), verified=False
            )
            prep = root / "main/40_course" / course_id / "lessons/lesson01/preparation"
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ):
                with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                    code = sp.main(
                        [
                            "prepare",
                            "--course",
                            course_id,
                            "--lesson",
                            "lesson01",
                            "--current",
                            "3",
                            "--document-id",
                            document_id,
                            "--available",
                            "1,2,3,4,5",
                            "--write",
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertFalse(prep.exists() and any(prep.glob("PREP-*.json")))

    def test_lesson_map_hash_uses_raw_file_bytes_crlf(self) -> None:
        """prepare must hash LessonMap file bytes, not read_text-normalized text."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_id, document_id, _ = _fixture_course(
                root, pages=list(range(1, 6))
            )
            map_path = (
                root / "main/40_course" / course_id / "lessons/lesson01/lesson_map.md"
            )
            # Force CRLF on disk (Windows write_text may also do this).
            crlf_body = _map_for(list(range(1, 6)), document_id).replace("\n", "\r\n")
            map_path.write_bytes(crlf_body.encode("utf-8"))
            raw_sha = _sha(map_path.read_bytes())
            # Text-normalized hash differs when CRLF is present.
            text_norm = map_path.read_text(encoding="utf-8").encode("utf-8")
            text_sha = _sha(text_norm)
            self.assertNotEqual(
                raw_sha,
                text_sha,
                "fixture must demonstrate CRLF raw vs text-normalized divergence",
            )
            with mock.patch.object(sp, "ROOT", root), mock.patch.object(
                sp, "MAIN", root / "main"
            ), mock.patch.object(
                sp, "pdf_page_mediabox_pt", return_value=PPI_MEDIA
            ):
                out = io.StringIO()
                with redirect_stdout(out):
                    code = sp.main(
                        [
                            "prepare",
                            "--course",
                            course_id,
                            "--lesson",
                            "lesson01",
                            "--current",
                            "3",
                            "--document-id",
                            document_id,
                            "--available",
                            "1,2,3,4,5",
                            "--write",
                        ]
                    )
                self.assertEqual(code, 0)
                payload = json.loads(out.getvalue())
                self.assertEqual(
                    payload["snapshot"]["lesson_map_sha256"],
                    raw_sha,
                )
                self.assertNotEqual(
                    payload["snapshot"]["lesson_map_sha256"],
                    text_sha,
                )


class LayoutCriticalDetectorTests(unittest.TestCase):
    """C5 detector contracts (criterion report §7.4, A2 decision §7.1).

    Images are synthesised rather than taken from the corpus so the thresholds are
    tested, not the textbook.
    """

    @staticmethod
    def _text_line(draw, top: int) -> None:
        """Glyph-like marks with gaps -- never a solid bar.

        A solid 360px rule would read as a figure axis to the straight-run term,
        which is exactly what real text does not contain.
        """
        for left in range(20, 380, 24):
            draw.rectangle([left, top, left + 16, top + 20], fill=0)

    @classmethod
    def _page(cls, figure: bool) -> "object":
        from PIL import Image, ImageDraw

        img = Image.new("L", (400, 800), 255)
        draw = ImageDraw.Draw(img)
        for top in range(20, 700, 40):          # 20px text lines, 40px pitch
            cls._text_line(draw, top)
        if figure:                               # one block ~7x a text line
            draw.rectangle([60, 720, 340, 860], fill=0)
        return img

    def _scan(self, figure: bool) -> dict:
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "page_1.png"
            self._page(figure).save(png)
            return sp.layout_metrics(png)

    def test_figure_page_exceeds_threshold(self) -> None:
        metrics = self._scan(figure=True)
        self.assertGreater(metrics["ratio"], sp.LAYOUT_CRITICAL_THRESHOLD)
        self.assertTrue(sp.layout_critical_verdict(metrics))

    def test_text_only_page_stays_below_threshold(self) -> None:
        metrics = self._scan(figure=False)
        self.assertLessEqual(metrics["ratio"], sp.LAYOUT_CRITICAL_THRESHOLD)
        self.assertFalse(sp.layout_critical_verdict(metrics))

    def test_threshold_actually_discriminates(self) -> None:
        """Mutation guard: a verdict that ignores the ratio must fail these."""
        figure = self._scan(figure=True)
        text = self._scan(figure=False)
        self.assertNotEqual(
            sp.layout_critical_verdict(figure),
            sp.layout_critical_verdict(text),
            "detector returns the same verdict for figure and text pages",
        )
        # Raising the bar above the figure ratio must flip it -- proves the
        # threshold is read rather than hard-coded.
        self.assertFalse(
            sp.layout_critical_verdict(figure, threshold=figure["ratio"] + 1)
        )

    @staticmethod
    def _flat_figure() -> "object":
        """A wide, short figure: too short to trip `ratio`, but it has an axis.

        This is the p200 case -- a circle-and-polygon inset beside body text.  Its
        block is not tall relative to a text line, so the tallest-block metric alone
        would miss it; the long horizontal rule is the only signal.
        """
        from PIL import Image, ImageDraw

        img = Image.new("L", (400, 800), 255)
        draw = ImageDraw.Draw(img)
        for top in range(20, 700, 40):
            LayoutCriticalDetectorTests._text_line(draw, top)
        draw.line([30, 730, 370, 730], fill=0, width=3)   # 340px axis, ~17x line height
        return img

    def _metrics_of(self, image) -> dict:
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "page_1.png"
            image.save(png)
            return sp.layout_metrics(png)

    def test_thin_standalone_rule_is_a_known_blind_spot(self) -> None:
        """Documents the miss rather than pretending it is covered.

        A 3px axis under the text forms its own short row span and is filtered by
        LAYOUT_MIN_LINE_PX, so neither `ratio` nor the block-local straight-run
        metrics see it.  This is the small-inline-figure case; it is currently a
        false negative and C4 override is the only backstop.  If a future
        discriminator fixes it, this test should start failing -- update it then.
        """
        metrics = self._metrics_of(self._flat_figure())
        self.assertLessEqual(metrics["ratio"], sp.LAYOUT_CRITICAL_THRESHOLD)
        self.assertFalse(
            sp.layout_critical_verdict(metrics),
            "blind spot closed -- revisit this test and the C5 definition",
        )

    def test_line_metrics_are_reported_but_do_not_decide(self) -> None:
        """`hline`/`vline` must stay out of the verdict until validated."""
        metrics = self._metrics_of(self._page(figure=True))
        for key in ("hline", "vline"):
            self.assertIn(key, metrics)
        loud = {"ratio": 1.0, "hline": 99.0, "vline": 99.0}
        self.assertFalse(
            sp.layout_critical_verdict(loud),
            "straight-run metrics must not decide: both designs failed measurement",
        )

    MANIFEST = {
        "document_id": "DOC1",
        "course_id": "C1",
        "pages": [
            {"pdf_page_index": 1, "verification_status": "unverified"},
            {"pdf_page_index": 2, "verification_status": "verified",
             "layout_critical": False},
            {"pdf_page_index": 3, "verification_status": "verified"},
        ],
    }

    def test_advisory_lists_only_verified_pages_missing_the_flag(self) -> None:
        advisory = sp.layout_critical_advisory(self.MANIFEST, [1, 2, 3])
        self.assertEqual(advisory["pending_pages"], [3])
        self.assertIn("layout-scan", advisory["command"])
        self.assertIn("--course C1", advisory["command"])

    def test_advisory_ignores_unverified_and_stays_silent_when_complete(self) -> None:
        # Page 1 is unverified: it always falls back to rendering, so a missing
        # flag there is not a gap.
        self.assertEqual(sp.layout_critical_advisory(self.MANIFEST, [1])["pending_pages"], [])
        done = sp.layout_critical_advisory(self.MANIFEST, [2])
        self.assertEqual(done["pending_pages"], [])
        self.assertNotIn("command", done)

    def test_advisory_treats_false_as_decided(self) -> None:
        """A decided `false` must not be re-reported as pending.

        `false` and 'absent' are different states (§3.1.4 fail-closed); conflating
        them would make the advisory fire forever on correctly-decided pages.
        """
        self.assertEqual(sp.layout_critical_advisory(self.MANIFEST, [2])["pending_pages"], [])

    def test_blank_page_fails_closed(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "page_1.png"
            Image.new("L", (400, 800), 255).save(png)
            with self.assertRaises(sp.PrepareError):
                sp.layout_metrics(png)


if __name__ == "__main__":
    unittest.main(verbosity=2)
