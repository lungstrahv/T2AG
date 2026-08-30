#!/usr/bin/env python3
"""Atomic contracts for the neutral Operator result envelope."""
from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path
from unittest import mock

import activity_close
import operator_result
import sync_cloud
import t2ag_context
import t2ag_doctor
import t2ag_init
import t2ag_state_refresh


TOOLS = Path(__file__).resolve().parent
MODULES = (
    ("init", t2ag_init, True),
    ("doctor", t2ag_doctor, True),
    ("state_refresh", t2ag_state_refresh, False),
    ("context", t2ag_context, False),
    ("activity_close", activity_close, True),
    ("sync_cloud", sync_cloud, True),
)


class OperatorResultContracts(unittest.TestCase):
    def _invoke(self, tool: str, module: object, takes_argv: bool, exit_code: int) -> tuple[str, dict]:
        stdout = io.StringIO()
        stderr = io.StringIO()

        def legacy_cli(*_args: object, **_kwargs: object) -> int:
            print("legacy stdout remains unchanged")
            return exit_code

        with mock.patch.object(module, "_main", side_effect=legacy_cli):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                returned = module.main([]) if takes_argv else module.main()
        self.assertEqual(returned, exit_code)
        self.assertEqual(stdout.getvalue(), "legacy stdout remains unchanged\n")
        line = stderr.getvalue().strip().splitlines()[-1]
        envelope = operator_result.parse_line(line)
        self.assertEqual(envelope["structured_result"]["tool"], tool)
        return line, envelope

    def test_six_cli_boundaries_emit_success_and_failure_envelopes(self) -> None:
        for tool, module, takes_argv in MODULES:
            _, success = self._invoke(tool, module, takes_argv, 0)
            self.assertTrue(success["ok"])
            self.assertEqual(success["audience"], "operator")
            self.assertEqual(success["code"], f"T2AG.{tool.upper()}.OK")
            self.assertEqual(success["structured_result"]["next_action"], "continue")
            _, failure = self._invoke(tool, module, takes_argv, 1)
            self.assertFalse(failure["ok"])
            self.assertEqual(failure["code"], f"T2AG.{tool.upper()}.ERROR")
            self.assertEqual(
                failure["structured_result"]["next_action"],
                "inspect_operator_message",
            )

    def test_envelope_has_stable_operator_shape(self) -> None:
        value = operator_result.build_envelope(
            tool="doctor",
            operation="validation",
            exit_code=1,
            details={"fail_count": 2},
        )
        self.assertEqual(
            set(value),
            {"schema", "audience", "ok", "code", "operator_message", "structured_result"},
        )
        self.assertEqual(value["structured_result"]["fail_count"], 2)
        with self.assertRaises(operator_result.OperatorResultError):
            operator_result.build_envelope(tool="bad tool", operation="x", exit_code=0)

    def test_doctor_and_envelope_do_not_depend_on_learner_renderer(self) -> None:
        for name in ("operator_result.py", "t2ag_doctor.py"):
            source = (TOOLS / name).read_text(encoding="utf-8")
            self.assertNotIn("import learner_journey", source)
            self.assertNotIn("render_learner_summary", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
