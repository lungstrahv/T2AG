#!/usr/bin/env python3
"""EV-0024 P0 写路径护栏与 R-3 升格判据的红测。

这些用例锁的是**独立复审 2026-08-09 实测到的具体破坏面**，不是泛化的输入校验：
每个用例注明它对应复审报告的哪一条 finding。删掉护栏时，对应用例必须转红。
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
    """R-3：只升格「内联代码内容恰为单一可解析路径」的情况。"""

    def test_bare_path_promotes(self) -> None:
        self.assertTrue(okf.is_single_path_token("session_close.md"))
        self.assertTrue(okf.is_single_path_token("main/50_playbook/first_run.md"))

    def test_inline_command_rejected(self) -> None:
        # 复审原文举例：bundle 中三条 `grep ... file.md` 被整体升格成链接。
        self.assertFalse(okf.is_single_path_token('grep -rn "x" file.md'))
        self.assertFalse(okf.is_single_path_token("cat a.md | less"))

    def test_multi_target_rejected(self) -> None:
        # 复审原文：多目标命令被压成一个目标边。
        self.assertFalse(okf.is_single_path_token("a.md b.md"))

    def test_option_flag_rejected(self) -> None:
        self.assertFalse(okf.is_single_path_token("--out a.md"))

    def test_template_placeholder_rejected(self) -> None:
        # `<COURSE_ID>` 一类模板占位不是真路径；旧正则会命中它，再经裸文件名回退
        # 匹配到某个真 course.md，凭空造出一条错边。
        self.assertFalse(okf.is_single_path_token("40_course/<COURSE_ID>/course.md"))

    def test_non_markdown_rejected(self) -> None:
        self.assertFalse(okf.is_single_path_token("okf_export.py"))


class CourseIdValidationTests(unittest.TestCase):
    """P0-1：course_id 同时进源路径与输出相对路径，未校验时可双向穿越。"""

    def test_traversal_rejected(self) -> None:
        _, errors = okf.collect_sources("course:../../etc")
        self.assertTrue(any("course ID 非法" in e for e in errors), errors)

    def test_absolute_path_rejected(self) -> None:
        _, errors = okf.collect_sources("course:/etc/passwd")
        self.assertTrue(any("course ID 非法" in e for e in errors), errors)

    def test_dot_rejected(self) -> None:
        _, errors = okf.collect_sources("course:.")
        self.assertTrue(any("course ID 非法" in e for e in errors), errors)

    def test_legal_id_passes_validation(self) -> None:
        # 合法 ID 不应因校验被拒；课程是否存在是另一条错误路径。
        _, errors = okf.collect_sources("course:PY1001")
        self.assertFalse([e for e in errors if "course ID 非法" in e], errors)


class OutDirGateTests(unittest.TestCase):
    """P0-3：`--out` 准入。复审判定的「可破坏主库的高危写路径」正在此处收口。"""

    def test_repo_root_rejected(self) -> None:
        self.assertTrue(okf.validate_out_dir(okf.ROOT))

    def test_main_rejected(self) -> None:
        self.assertTrue(okf.validate_out_dir(okf.MAIN))

    def test_playbook_dir_rejected(self) -> None:
        # 这是最要命的一条：`--write --out main/50_playbook` 会删掉那里清单外的
        # 全部 markdown。护栏必须在任何删除动作之前生效。
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
    """P0-2 / P0-4：写入路径不得逃逸；残留与清单外文件必须 FAIL 而非 WARN。"""

    def test_escaping_relative_path_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            errors = okf.write_bundle({"../escaped.md": "x"}, out)
            self.assertTrue(any("逃出交付目录" in e for e in errors), errors)
            self.assertFalse((Path(tmp) / "escaped.md").exists())

    def test_stray_file_is_error_not_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            out.mkdir()
            (out / okf.BUNDLE_MARKER).write_text("", encoding="utf-8")
            (out / "leftover.txt").write_text("旧泄漏物", encoding="utf-8")
            errors = okf.write_bundle({"index.md": "# x\n"}, out)
            # 原实现只扫 .md 且只 WARN，最终仍 exit 0，旧泄漏物可留在交付目录。
            self.assertTrue(any("清单外文件" in e for e in errors), errors)

    def test_stale_markdown_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            out.mkdir()
            (out / okf.BUNDLE_MARKER).write_text("", encoding="utf-8")
            (out / "gone.md").write_text("上一轮的概念", encoding="utf-8")
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
