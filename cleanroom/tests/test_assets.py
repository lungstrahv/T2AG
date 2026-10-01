import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from t2ag_next import assets
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, put


def request(identity):
    return {"request_id": identity, "action": "fixture.install", "payload": {}, "expected": {},
            "actor": {"role": "system", "source": "synthetic unit fixture", "text": identity}}


def png(width=144, height=216, dpi=144, *, pixels=True):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    result = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    result += chunk(b"pHYs", struct.pack(">IIB", round(dpi / .0254), round(dpi / .0254), 1))
    if pixels:
        result += chunk(b"IDAT", zlib.compress((b"\0" + b"\xff" * width * 3) * height))
    return result + chunk(b"IEND", b"")


class Assertions(unittest.TestCase):
    def assertCode(self, code, function, *args, **kwargs):
        with self.assertRaises(DomainError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)


class OptionalAndPpiTests(Assertions):
    def test_core_import_and_dependency_absence_are_explicit(self):
        with patch.object(assets.importlib, "import_module", side_effect=ImportError("absent")):
            self.assertCode("PDF_DEPENDENCY_UNAVAILABLE", assets.inspect_pdf, "unused", "source")
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(Journal(temp).initialize()["revision"], 0)

    def test_real_png_geometry_density_and_pixels(self):
        result = assets.verify_ppi(png(), 72, 108, 144)
        self.assertEqual(result["width_pixels"], 144)
        self.assertEqual(result["effective_ppi_x"], 144)
        self.assertFalse(result["visual_readability_verified"])
        self.assertCode("PPI_MISMATCH", assets.verify_ppi, png(dpi=72), 72, 108, 144)
        self.assertCode("PAGE_RENDER_GEOMETRY", assets.verify_ppi, png(), 144, 216, 144)
        self.assertCode("PNG_INVALID", assets.verify_ppi, png(pixels=False), 72, 108, 144)

    def test_corrupt_truncated_or_trailing_png_is_rejected(self):
        content = png()
        corrupt = bytearray(content); corrupt[-7] ^= 1
        self.assertCode("PNG_INVALID", assets.verify_ppi, bytes(corrupt), 72, 108, 144)
        self.assertCode("PNG_INVALID", assets.verify_ppi, content + b"extra", 72, 108, 144)
        self.assertCode("PNG_INVALID", assets.verify_ppi, content[:-3], 72, 108, 144)

    def test_bad_geometry_inputs_fail_closed(self):
        for value in (None, True, float("nan"), float("inf"), 0, -10):
            with self.subTest(value=value):
                self.assertCode("PPI_INPUT", assets.verify_ppi, png(), value, 108, 144)


@unittest.skipUnless(importlib.util.find_spec("pymupdf"), "optional real PyMuPDF backend not installed in this interpreter")
class PdfAssetsTests(Assertions):
    def setUp(self):
        import pymupdf
        self.temp = tempfile.TemporaryDirectory()
        self.instance = Path(self.temp.name) / "instance"
        self.store = Journal(self.instance)
        self.store.initialize()
        doc = pymupdf.open()
        page = doc.new_page(width=144, height=216)
        page.insert_text((12, 36), "Synthetic source, page 1")
        page.draw_rect(pymupdf.Rect(12, 60, 120, 120))
        page = doc.new_page(width=144, height=216)
        page.insert_text((12, 36), "Synthetic source, page 2")
        page.set_rotation(90)
        content = doc.tobytes()
        doc.close()
        self.blob = self.store.put_blob(content)
        self.store.apply(request("source"), lambda state, req: [put("source", "S", {
            "format": "pdf", "blob_sha256": self.blob["sha256"], "content_sha256": self.blob["sha256"],
            "blob_refs": [self.blob], "page_count": 2})])

    def tearDown(self):
        self.temp.cleanup()

    def prewarm(self, pages=None):
        return assets.prewarm_pages(self.instance, "S", pages or [1, 2])

    def test_inspection_and_layout_do_not_fabricate_scan_or_printed_label(self):
        report = assets.inspect_pdf(self.instance, "S")
        self.assertEqual(report["physical_page_count"], 2)
        self.assertTrue(report["content_hash_verified"])
        self.assertFalse(report["current_session_consumed"])
        layout = assets.layout_scan(self.instance, "S", [1, 2])
        self.assertFalse(layout["teaching_scan_complete"])
        self.assertIn("vector_graphics_or_rules", layout["pages"][0]["layout_hints"])
        self.assertIn("Synthetic", layout["pages"][0]["machine_extracted_text"])
        self.assertIsNone(layout["pages"][0]["printed_page_label"])
        self.assertEqual(layout["pages"][1]["width_points"], 216)
        self.assertTrue(all(page["requires_visual_review"] for page in layout["pages"]))
        self.assertEqual(self.store.read_state()["revision"], 1)

    def test_prewarm_real_backend_reuses_validated_png_without_canonical_changes(self):
        first = self.prewarm()
        self.assertEqual(first["pages"][0]["ppi"]["width_pixels"], 600)
        self.assertEqual(first["pages"][0]["ppi"]["height_pixels"], 900)
        self.assertEqual(first["pages"][1]["ppi"]["width_pixels"], 900)
        self.assertEqual(first["pages"][0]["parameters"]["render_profile"], "pdf-300dpi-rgb-v1")
        self.assertFalse(first["pages"][0]["reused"])
        second = self.prewarm()
        self.assertTrue(all(page["reused"] for page in second["pages"]))
        self.assertEqual(self.store.read_state()["revision"], 1)
        self.assertEqual(len(assets.inspect_cache(self.instance)["entries"]), 2)
        self.assertTrue(self.store.validate()["ok"])

    def test_page_range_duplicate_dpi_and_resource_limit(self):
        self.assertCode("PDF_PAGE_RANGE", assets.prewarm_pages, self.instance, "S", [0])
        self.assertCode("PDF_PAGE_RANGE", assets.layout_scan, self.instance, "S", [3])
        self.assertCode("PDF_DUPLICATE_PAGE", assets.prewarm_pages, self.instance, "S", [1, 1])
        self.assertCode("PPI_RANGE", assets.prewarm_pages, self.instance, "S", [1], dpi=199)
        self.assertCode("PPI_RANGE", assets.prewarm_pages, self.instance, "S", [1], dpi=601)
        self.assertCode("PIXEL_LIMIT", assets.prewarm_pages, self.instance, "S", [1], max_pixels=10)

    def test_actual_source_consumption_rechecks_content(self):
        target = self.instance / "blobs" / self.blob["sha256"]
        # Journal metadata shortcuts are irrelevant: this consumer must invoke
        # read_blob and reject altered PDF bytes before parsing/rendering.
        target.write_bytes(b"x" * target.stat().st_size)
        self.assertCode("BLOB_CORRUPT", assets.inspect_pdf, self.instance, "S")

    def test_cache_corruption_blocks_reuse_and_inspection(self):
        page = self.prewarm([1])["pages"][0]
        Path(page["cache_path"]).write_bytes(b"broken")
        self.assertCode("CACHE_IMAGE_CORRUPT", self.prewarm, [1])
        self.assertCode("CACHE_IMAGE_CORRUPT", assets.inspect_cache, self.instance)
        self.assertTrue(self.store.validate()["ok"])

    def test_high_dpi_has_separate_profile_and_never_overwrites_default(self):
        default = self.prewarm([1])["pages"][0]
        before = Path(default["cache_path"]).read_bytes()
        high = assets.prewarm_pages(self.instance, "S", [1], dpi=600)["pages"][0]
        self.assertEqual(high["parameters"]["render_profile"], "pdf-600dpi-rgb-v1")
        self.assertNotEqual(default["cache_key"], high["cache_key"])
        self.assertEqual(Path(default["cache_path"]).read_bytes(), before)
        self.assertEqual(high["ppi"]["width_pixels"], 1200)

    def test_missing_and_corrupt_derived_cache_has_explicit_verified_repair(self):
        page = self.prewarm([1])["pages"][0]
        image = Path(page["cache_path"])
        for damage in (lambda: image.unlink(), lambda: image.write_bytes(b"bad")):
            damage()
            fixed = assets.prewarm_pages(self.instance, "S", [1], repair=True)["pages"][0]
            self.assertTrue(fixed["repaired"])
            self.assertFalse(fixed["teaching_scan_complete"])
            self.assertEqual(fixed["sha256"], page["sha256"])
            self.assertEqual(self.store.read_state()["revision"], 1)
        image.unlink()
        blob = self.instance / "blobs" / self.blob["sha256"]
        blob.write_bytes(b"x" * blob.stat().st_size)
        self.assertCode("BLOB_CORRUPT", assets.prewarm_pages, self.instance, "S", [1], repair=True)
        self.assertFalse(image.exists())

    def test_gc_dry_run_then_exact_plan_deletes_only_owned_derived_images(self):
        page = self.prewarm([1])["pages"][0]
        cache = Path(page["cache_path"]).parent
        sentinel = cache / "user-note.txt"; sentinel.write_text("keep", encoding="utf-8")
        blob_before = self.store.read_blob(self.blob["sha256"])
        plan = assets.gc_cache(self.instance, older_than_seconds=0)
        self.assertEqual(len(plan["candidates"]), 1)
        self.assertTrue(Path(page["cache_path"]).exists())
        self.assertCode("CACHE_PLAN_CHANGED", assets.gc_cache, self.instance, older_than_seconds=0, dry_run=False)
        done = assets.gc_cache(self.instance, older_than_seconds=0, dry_run=False, expected_plan_sha256=plan["plan_sha256"])
        self.assertEqual(done["deleted"], [page["cache_key"]])
        receipt = json.loads(Path(done["receipt_path"]).read_text())
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(receipt["plan_sha256"], plan["plan_sha256"])
        self.assertEqual(receipt["deleted"], done["deleted"])
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertEqual(self.store.read_blob(self.blob["sha256"]), blob_before)
        self.assertEqual(assets.inspect_cache(self.instance)["entries"], [])
        self.assertIn("user-note.txt", assets.inspect_cache(self.instance)["unmanaged_files"])

    def pin(self):
        self.store.apply(request("pin"), lambda state, req: [
            put("page", "P", {"source_id": "S", "pdf_page_index": 1}),
            put("scope", "Scope", {"page_ids": ["P"]}),
            put("activity", "A", {"scope_id": "Scope", "status": "ongoing"})])

    def test_active_scope_pins_and_explicit_keep_keys_are_respected(self):
        pages = self.prewarm()["pages"]
        self.pin()
        plan = assets.gc_cache(self.instance, older_than_seconds=0)
        self.assertEqual([row["cache_key"] for row in plan["candidates"]], [pages[1]["cache_key"]])
        self.assertEqual(plan["pinned_active_pages"], 1)
        self.assertEqual(assets.gc_cache(self.instance, older_than_seconds=0, keep_keys=[pages[1]["cache_key"]])["candidates"], [])

    def test_stale_reference_plan_cannot_remove_newly_pinned_page(self):
        page = self.prewarm([1])["pages"][0]
        plan = assets.gc_cache(self.instance, older_than_seconds=0)
        self.pin()
        self.assertCode("CACHE_PLAN_CHANGED", assets.gc_cache, self.instance, older_than_seconds=0, dry_run=False,
                        expected_plan_sha256=plan["plan_sha256"])
        self.assertTrue(Path(page["cache_path"]).exists())

    def test_gc_holds_journal_lock_through_selection_and_publication(self):
        self.prewarm([1])
        original = assets._image
        def probe(cache, record):
            self.assertCode("LOCK_BUSY", self.store.apply, request("concurrent"), lambda s, r: [put("course", "C", {})])
            return original(cache, record)
        with patch.object(assets, "_image", side_effect=probe):
            assets.gc_cache(self.instance, older_than_seconds=0)
        self.assertIsNone(self.store.lookup("concurrent"))

    def test_gc_hashes_reconstruction_source_even_when_metadata_appears_unchanged(self):
        page = self.prewarm([1])["pages"][0]
        sha = self.blob["sha256"]
        signature = self.store._blob_stat(sha)
        blob = self.instance / "blobs" / sha
        blob.write_bytes(b"x" * blob.stat().st_size)
        original = Journal._blob_stat
        def unchanged_metadata(store, digest):
            return signature if digest == sha else original(store, digest)
        with patch.object(Journal, "_blob_stat", unchanged_metadata):
            self.assertCode("BLOB_CORRUPT", assets.gc_cache, self.instance, older_than_seconds=0)
        self.assertTrue(Path(page["cache_path"]).exists())

    def test_gc_rechecks_observable_source_drift_before_removing_index(self):
        page = self.prewarm([1])["pages"][0]
        plan = assets.gc_cache(self.instance, older_than_seconds=0)
        original = assets._atomic
        def drift(path, content):
            original(path, content)
            if path.name.startswith("gc-"):
                blob = self.instance / "blobs" / self.blob["sha256"]
                blob.write_bytes(b"bad")
        with patch.object(assets, "_atomic", drift):
            self.assertCode("BLOB_CHANGED", assets.gc_cache, self.instance, older_than_seconds=0, dry_run=False,
                            expected_plan_sha256=plan["plan_sha256"])
        self.assertTrue(Path(page["cache_path"]).exists())
        self.assertEqual(len(assets.inspect_cache(self.instance)["entries"]), 1)

    def test_gc_missing_backend_is_not_proof_of_rebuildability(self):
        page = self.prewarm([1])["pages"][0]
        with patch.object(assets.importlib, "import_module", side_effect=ImportError("absent")):
            self.assertCode("PDF_DEPENDENCY_UNAVAILABLE", assets.gc_cache, self.instance, older_than_seconds=0)
        self.assertTrue(Path(page["cache_path"]).exists())

    def test_malicious_index_path_and_nonfinite_values_fail_without_deletion(self):
        page = self.prewarm([1])["pages"][0]
        path = Path(page["cache_path"]).parent / "index.json"
        original = json.loads(path.read_text())
        original["entries"][page["cache_key"]]["file"] = "../../transactions.jsonl"
        path.write_text(json.dumps(original), encoding="utf-8")
        self.assertCode("CACHE_INDEX_INVALID", assets.gc_cache, self.instance, older_than_seconds=0)
        self.assertTrue(self.store.validate()["ok"])
        path.write_text('{"format":"t2ag.page-cache.v1","entries":{},"bad":NaN}', encoding="utf-8")
        self.assertCode("CACHE_INDEX_INVALID", assets.inspect_cache, self.instance)

    def test_interrupted_gc_leaves_visible_unmanaged_residue_not_false_index(self):
        page = self.prewarm([1])["pages"][0]
        plan = assets.gc_cache(self.instance, older_than_seconds=0)
        original = Path.unlink
        def fail_image(path, *args, **kwargs):
            if str(path) == page["cache_path"]:
                raise OSError("injected unlink failure")
            return original(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail_image):
            self.assertCode("CACHE_GC_PARTIAL", assets.gc_cache, self.instance, older_than_seconds=0, dry_run=False,
                            expected_plan_sha256=plan["plan_sha256"])
        checked = assets.inspect_cache(self.instance)
        self.assertEqual(checked["entries"], [])
        self.assertIn(Path(page["cache_path"]).name, checked["unmanaged_files"])
        self.assertTrue(self.store.validate()["ok"])

    def test_symlink_cache_is_rejected_when_host_permits_creation(self):
        outside = Path(self.temp.name) / "outside"; outside.mkdir()
        derived = self.instance / "derived"; derived.mkdir()
        try:
            (derived / "page-cache").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest("host symlink privilege unavailable: " + str(getattr(exc, "winerror", exc.errno)))
        self.assertCode("CACHE_UNSAFE_PATH", assets.inspect_cache, self.instance)


if __name__ == "__main__":
    unittest.main()
