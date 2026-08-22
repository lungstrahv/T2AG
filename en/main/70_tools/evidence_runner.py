#!/usr/bin/env python3
"""Run one command and persist immutable, machine-verifiable evidence first."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EvidenceError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def parse_unittest_counts(stdout: bytes, stderr: bytes) -> dict[str, int]:
    text = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
    matches = re.findall(r"(?m)^Ran\s+(\d+)\s+tests?\b", text)
    ran = int(matches[-1]) if matches else 0
    tail = text[text.rfind("Ran ") :] if "Ran " in text else text
    def count(label: str) -> int:
        found = re.search(rf"\b{re.escape(label)}=(\d+)\b", tail)
        return int(found.group(1)) if found else 0

    fail = count("failures")
    error = count("errors")
    skip = count("skipped")
    expected_skip = count("expected failures")
    passed = max(0, ran - fail - error - skip - expected_skip)
    return {
        "ran": ran,
        "pass": passed,
        "fail": fail,
        "error": error,
        "skip": skip,
        "expected_skip": expected_skip,
    }


def runtime_descriptor(argv: list[str]) -> dict[str, str]:
    executable = str(Path(argv[0]).resolve()) if argv else ""
    version = ""
    if argv and Path(argv[0]).resolve() == Path(sys.executable).resolve():
        version = sys.version.replace("\n", " ")
    return {
        "executable": executable,
        "implementation": sys.implementation.name,
        "version": version,
    }


def run_evidence(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if not args.command:
        raise EvidenceError("child command is required after --")
    if args.tool_manifest_sha and not re.fullmatch(
        r"[0-9a-f]{64}", args.tool_manifest_sha
    ):
        raise EvidenceError("tool manifest SHA must be 64 lowercase hex")
    report = args.report_file.resolve()
    stdout_path = report.with_suffix(report.suffix + ".stdout")
    stderr_path = report.with_suffix(report.suffix + ".stderr")
    for path in (report, stdout_path, stderr_path):
        if path.exists():
            raise EvidenceError(f"immutable evidence path already exists: {path}")

    child_argv = list(args.command)
    if child_argv and child_argv[0] == "--":
        child_argv = child_argv[1:]
    if not child_argv:
        raise EvidenceError("empty child command")
    cwd = args.cwd.resolve()
    started_at = utc_now()
    started = time.perf_counter_ns()
    timed_out = False
    exit_code: int | None = None
    stdout = b""
    stderr = b""
    try:
        completed = subprocess.run(
            child_argv,
            cwd=cwd,
            capture_output=True,
            timeout=args.timeout_ms / 1000,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
    finished = time.perf_counter_ns()
    finished_at = utc_now()

    if args.schema == "unittest":
        counts = parse_unittest_counts(stdout, stderr)
        valid_assertions = counts["ran"] > 0
    else:
        counts = {
            "ran": int(args.assertion_count),
            "pass": int(args.assertion_count) if exit_code == 0 else 0,
            "fail": 0 if exit_code == 0 else int(args.assertion_count),
            "error": 0,
            "skip": 0,
            "expected_skip": 0,
        }
        valid_assertions = args.assertion_count > 0

    passed = bool(
        not timed_out
        and exit_code == 0
        and valid_assertions
        and counts["fail"] == 0
        and counts["error"] == 0
    )
    write_exclusive(stdout_path, stdout)
    write_exclusive(stderr_path, stderr)
    payload: dict[str, Any] = {
        "schema": "t2ag.evidence_run.v1",
        "campaign_id": args.campaign_id,
        "phase": args.phase,
        "run_id": args.run_id or f"RUN-{uuid.uuid4().hex}",
        "command_schema": args.schema,
        "argv": child_argv,
        "cwd": str(cwd),
        **runtime_descriptor(child_argv),
        "runtime": runtime_descriptor(child_argv),
        "tool_source_manifest_sha256": args.tool_manifest_sha or None,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": (finished - started) // 1_000_000,
        "timeout_ms": args.timeout_ms,
        "exit_code": exit_code,
        "status": "pass" if passed else ("timeout" if timed_out else "fail"),
        **counts,
        "timeout": timed_out,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "failure_injection_point": args.failure_injection_point,
        "child_exit_mode": (
            "timeout" if timed_out else ("normal" if exit_code == 0 else "nonzero")
        ),
        "recover_result": args.recover_result,
        "before_manifest_sha256": args.before_manifest_sha,
        "after_manifest_sha256": args.after_manifest_sha,
    }
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    write_exclusive(report, raw)
    return payload, sha256_bytes(raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--report-file", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--timeout-ms", type=int, default=120_000)
    parser.add_argument("--schema", choices=["unittest", "assertion"], default="unittest")
    parser.add_argument("--assertion-count", type=int, default=0)
    parser.add_argument("--tool-manifest-sha", default=None)
    parser.add_argument("--failure-injection-point", default=None)
    parser.add_argument("--recover-result", default=None)
    parser.add_argument("--before-manifest-sha", default=None)
    parser.add_argument("--after-manifest-sha", default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload, report_sha = run_evidence(args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "ok": payload["status"] == "pass",
                "status": payload["status"],
                "report_file": str(args.report_file.resolve()),
                "report_sha256": report_sha,
                "ran": payload["ran"],
                "pass": payload["pass"],
                "fail": payload["fail"],
                "error": payload["error"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
