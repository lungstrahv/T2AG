#!/usr/bin/env python3
"""Red tests for the EV-0024 P0 write-path guards and the R-3 promotion criterion.

These cases pin the **specific destruction surface measured by the independent re-review of
2026-08-09**, not generic input validation: each case names which finding of the re-review report it
corresponds to. Remove a guard and its case must turn red.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import okf_export as okf


class SinglePathTokenTests(unittest.TestCase):
    """R-3: promote only when the inline code content is exactly one resolvable path."""

    def test_bare_path_promotes(self) -> None:
        self.assertTrue(okf.is_single_path_token("session_close.md"))
        self.assertTrue(okf.is_single_path_token("main/50_playbook/first_run.md"))

    def test_inline_command_rejected(self) -> None:
        # From the re-review: three `grep ... file.md` commands in the bundle were promoted wholesale to links.
        self.assertFalse(okf.is_single_path_token('grep -rn "x" file.md'))
        self.assertFalse(okf.is_single_path_token("cat a.md | less"))

    def test_multi_target_rejected(self) -> None:
        # From the re-review: a multi-target command was squashed into a single-target edge.
        self.assertFalse(okf.is_single_path_token("a.md b.md"))

    def test_option_flag_rejected(self) -> None:
        self.assertFalse(okf.is_single_path_token("--out a.md"))

    def test_template_placeholder_rejected(self) -> None:
        # A template placeholder such as `<COURSE_ID>` is not a real path; the old regex matched it,
        # then fell back to a bare filename match against some real course.md, manufacturing a wrong
        # edge out of nothing.
        self.assertFalse(okf.is_single_path_token("40_course/<COURSE_ID>/course.md"))

    def test_non_markdown_rejected(self) -> None:
        self.assertFalse(okf.is_single_path_token("okf_export.py"))


class CourseIdValidationTests(unittest.TestCase):
    """P0-1: course_id feeds both the source path and the output relative path, so without validation it traverses both ways."""

    def test_traversal_rejected(self) -> None:
        _, errors = okf.collect_sources("course:../../etc")
        self.assertTrue(any("course ID is invalid" in e for e in errors), errors)

    def test_absolute_path_rejected(self) -> None:
        _, errors = okf.collect_sources("course:/etc/passwd")
        self.assertTrue(any("course ID is invalid" in e for e in errors), errors)

    def test_dot_rejected(self) -> None:
        _, errors = okf.collect_sources("course:.")
        self.assertTrue(any("course ID is invalid" in e for e in errors), errors)

    def test_legal_id_passes_validation(self) -> None:
        # A legal ID must not be rejected by validation; whether the course exists is a different error path.
        _, errors = okf.collect_sources("course:PY1001")
        self.assertFalse([e for e in errors if "course ID is invalid" in e], errors)


class OutDirGateTests(unittest.TestCase):
    """P0-3: `--out` admission. The re-review's "high-risk write path capable of destroying the main repository" is closed here."""

    def test_repo_root_rejected(self) -> None:
        self.assertTrue(okf.validate_out_dir(okf.ROOT))

    def test_main_rejected(self) -> None:
        self.assertTrue(okf.validate_out_dir(okf.MAIN))

    def test_playbook_dir_rejected(self) -> None:
        # This is the deadliest one: `--write --out main/50_playbook` would delete every markdown file
        # there that is not in the manifest. The guard must take effect before any delete action.
        self.assertTrue(okf.validate_out_dir(okf.MAIN / "50_playbook"))

    def test_workspace_root_rejected(self) -> None:
        self.assertTrue(okf.validate_out_dir(okf.ROOT.parent))

    def test_nonempty_unmarked_dir_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "someone-elses-folder"
            target.mkdir()
            (target / "important.md").write_text("x", encoding="utf-8")
            errors = okf.validate_out_dir(target)
            self.assertTrue(any(okf.BUNDLE_MARKER in e for e in errors), errors)

    def test_marked_dir_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bundle"
            target.mkdir()
            (target / "stale.md").write_text("x", encoding="utf-8")
            (target / okf.BUNDLE_MARKER).write_text("", encoding="utf-8")
            self.assertEqual(okf.validate_out_dir(target), [])

    def test_fresh_dir_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(okf.validate_out_dir(Path(tmp) / "brand-new"), [])


class WriteBundleTests(unittest.TestCase):
    """P0-2 / P0-4: a write path must not escape; leftovers and files outside the manifest must FAIL, not WARN."""

    def test_escaping_relative_path_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            errors = okf.write_bundle({"../escaped.md": "x"}, out)
            self.assertTrue(any("escapes the delivery directory" in e for e in errors), errors)
            self.assertFalse((Path(tmp) / "escaped.md").exists())

    def test_stray_file_is_error_not_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            out.mkdir()
            (out / okf.BUNDLE_MARKER).write_text("", encoding="utf-8")
            (out / "leftover.txt").write_text("an old leaked artifact", encoding="utf-8")
            errors = okf.write_bundle({"index.md": "# x\n"}, out)
            # The original implementation scanned only .md, only WARNed, and still exited 0, so an old leaked
# artifact could stay in the delivery directory.
            self.assertTrue(any("outside the manifest" in e for e in errors), errors)

    def test_stale_markdown_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            out.mkdir()
            (out / okf.BUNDLE_MARKER).write_text("", encoding="utf-8")
            (out / "gone.md").write_text("a concept from the previous round", encoding="utf-8")
            errors = okf.write_bundle({"index.md": "# x\n"}, out)
            self.assertEqual(errors, [])
            self.assertFalse((out / "gone.md").exists())
            self.assertTrue((out / "index.md").exists())

    def test_marker_written_for_fresh_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            self.assertEqual(okf.write_bundle({"index.md": "# x\n"}, out), [])
            self.assertTrue((out / okf.BUNDLE_MARKER).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
