#!/usr/bin/env python3
"""Tests for immutable structured evidence runner."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
RUNNER = TOOLS / "evidence_runner.py"


class EvidenceRunnerTests(unittest.TestCase):
    def invoke(
        self,
        root: Path,
        body: str,
        *,
        schema: str = "unittest",
        assertion_count: int = 0,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        child = root / "child.py"
        child.write_text(body, encoding="utf-8")
        report = root / "report.json"
        run = subprocess.run(
            [
                sys.executable,
                "-B",
                str(RUNNER),
                "--campaign-id",
                "TEST-CAMPAIGN",
                "--phase",
                "TEST",
                "--report-file",
                str(report),
                "--cwd",
                str(root),
                "--schema",
                schema,
                "--assertion-count",
                str(assertion_count),
                "--",
                sys.executable,
                "-B",
                str(child),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return run, report

    def test_singular_unittest_is_counted_and_bytes_are_bound(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-evidence-") as tmp:
            root = Path(tmp)
            run, report = self.invoke(
                root,
                "import sys\nsys.stderr.write('Ran 1 test in 0.001s\\n\\nOK\\n')\n",
            )
            self.assertEqual(run.returncode, 0, msg=run.stdout + run.stderr)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["ran"], 1)
            self.assertEqual(payload["pass"], 1)
            self.assertEqual(payload["status"], "pass")
            self.assertTrue(Path(payload["stdout_path"]).is_file())
            self.assertTrue(Path(payload["stderr_path"]).is_file())

    def test_zero_test_false_green_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-evidence-zero-") as tmp:
            root = Path(tmp)
            run, report = self.invoke(root, "print('OK')\n")
            self.assertEqual(run.returncode, 1)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["ran"], 0)
            self.assertEqual(payload["status"], "fail")

    def test_assertion_command_requires_explicit_positive_count(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-evidence-assert-") as tmp:
            root = Path(tmp)
            run, report = self.invoke(
                root,
                "print('checked')\n",
                schema="assertion",
                assertion_count=3,
            )
            self.assertEqual(run.returncode, 0)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["pass"], 3)

    def test_immutable_paths_are_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-evidence-immutable-") as tmp:
            root = Path(tmp)
            first, report = self.invoke(
                root,
                "import sys\nsys.stderr.write('Ran 1 test in 0s\\nOK\\n')\n",
            )
            self.assertEqual(first.returncode, 0)
            before = report.read_bytes()
            second, _ = self.invoke(
                root,
                "import sys\nsys.stderr.write('Ran 1 test in 0s\\nOK\\n')\n",
            )
            self.assertEqual(second.returncode, 2)
            self.assertEqual(report.read_bytes(), before)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
