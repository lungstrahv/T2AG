#!/usr/bin/env python3
"""Neutral Operator result envelope shared by CLI boundaries.

This module owns no learner wording and never imports the learner renderer.
The envelope is emitted to stderr so existing machine-readable stdout remains
byte-compatible for callers that already consume it.
"""
from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from typing import Any, TextIO


SCHEMA = "t2ag.operator_result.v1"
AUDIENCE = "operator"
LINE_PREFIX = "OPERATOR_RESULT "
_TOOL = re.compile(r"[A-Z][A-Z0-9_]*\Z")


class OperatorResultError(ValueError):
    pass


def build_envelope(
    *,
    tool: str,
    operation: str,
    exit_code: int,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_tool = tool.strip().upper().replace("-", "_")
    if not _TOOL.fullmatch(normalized_tool):
        raise OperatorResultError(f"invalid tool family: {tool}")
    ok = exit_code == 0
    outcome = "succeeded" if ok else "failed"
    return {
        "schema": SCHEMA,
        "audience": AUDIENCE,
        "ok": ok,
        "code": f"T2AG.{normalized_tool}.{'OK' if ok else 'ERROR'}",
        "operator_message": f"{operation} {outcome} with exit_code={exit_code}",
        "structured_result": {
            "tool": normalized_tool.lower(),
            "operation": operation,
            "outcome": outcome,
            "impact": "inspect_result" if ok else "operation_not_claimable",
            "next_action": "continue" if ok else "inspect_operator_message",
            "exit_code": exit_code,
            **dict(details or {}),
        },
    }


def emit_exit(
    *,
    tool: str,
    operation: str,
    exit_code: int,
    details: Mapping[str, Any] | None = None,
    stream: TextIO | None = None,
) -> dict[str, Any]:
    envelope = build_envelope(
        tool=tool,
        operation=operation,
        exit_code=exit_code,
        details=details,
    )
    target = stream or sys.stderr
    print(LINE_PREFIX + json.dumps(envelope, ensure_ascii=False, sort_keys=True), file=target)
    return envelope


def parse_line(line: str) -> dict[str, Any]:
    if not line.startswith(LINE_PREFIX):
        raise OperatorResultError("operator result prefix missing")
    value = json.loads(line[len(LINE_PREFIX):])
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise OperatorResultError("operator result schema mismatch")
    if value.get("audience") != AUDIENCE:
        raise OperatorResultError("operator result audience mismatch")
    return value
