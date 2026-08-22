#!/usr/bin/env python3
"""Validate the 0.2.2 gate matrix and freeze a hash-bound D package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


SCHEMA = "t2ag.022.gate_matrix.v1"
PACKAGE_SCHEMA = "t2ag.022.frozen_package.v1"
SHA_RE = re.compile(r"[0-9a-f]{64}")

REQUIRED_GATE_IDS = tuple(
    [f"EREV-{i:03d}" for i in range(1, 13)]
    + [f"CR-{i:03d}" for i in range(1, 19)]
    + [f"V4-{i:03d}" for i in range(1, 16)]
    + [
        "V2-6-ID_ALIAS",
        "V2-6-SCHEMA_SNAPSHOT",
        "V2-6-STATE",
        "V2-6-CAPACITY",
        "V2-6-PENDING",
        "V2-6-CLR",
        "V2-6-ROUTING",
        "V2-6-PREFERENCES_BODY",
        "V2-6-KNOWLEDGE_COMPLETION",
        "V2-6-TIME",
        "V2-6-TRANSACTION",
        "V2-6-MIGRATION",
        "V2-6-REAL_ROUNDTRIP",
        "V2-6-RELEASE",
    ]
)

REQUIRED_ROW_LISTS = (
    "implementation_symbols",
    "positive_tests",
    "negative_tests",
    "real_consumers",
    "recovery_evidence",
)

REQUIRED_PACKAGE_ROLES = {
    "workorder_v4",
    "e_rejection_review",
    "valid_receipt_chain_head",
    "revoked_plan_registry",
    "frozen_plan",
    "closure_matrix",
    "occurrence_report",
    "source_manifest",
    "projected_manifest",
    "executor_manifest",
    "shadow_report",
    "exception_matrix_report",
    "hard_kill_matrix_report",
    "pre_e_instance_report",
    "suite_index",
}


class GateError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise GateError(f"missing evidence file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def safe_member_path(workspace: Path, value: str) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        path = raw.resolve()
    else:
        path = (workspace / raw).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError as exc:
        raise GateError(f"evidence escapes workspace: {value}") from exc
    return path


def checked_report(
    workspace: Path,
    value: dict[str, Any],
    evidence_map: dict[str, str],
    *,
    gate_id: str,
) -> tuple[Path, dict[str, Any], bytes]:
    report_value = str(value.get("report_path") or "")
    declared = str(value.get("report_sha256") or "")
    if not report_value or not SHA_RE.fullmatch(declared):
        raise GateError(f"gate report binding incomplete: {gate_id}")
    report = safe_member_path(workspace, report_value)
    actual = sha256_file(report)
    rel = report.relative_to(workspace.resolve()).as_posix()
    if actual != declared or evidence_map.get(rel) != declared:
        raise GateError(f"gate report is not bound by evidence_files: {gate_id}: {rel}")
    raw = report.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise GateError(f"gate report is invalid JSON: {gate_id}: {report}") from exc
    if not isinstance(payload, dict) or payload.get("status") != "pass":
        raise GateError(f"gate report is not PASS: {gate_id}: {report}")
    if payload.get("schema") == "t2ag.evidence_run.v1" and not SHA_RE.fullmatch(
        str(payload.get("tool_source_manifest_sha256") or "")
    ):
        raise GateError(
            f"durable evidence lacks tool source manifest binding: {gate_id}: {report}"
        )
    return report, payload, raw


def checked_consumer_run(
    payload: dict[str, Any], item: dict[str, Any], *, gate_id: str
) -> dict[str, Any]:
    """Select one operational run; help/smoke-only evidence is never enough."""
    run_id = str(item.get("run_id") or "")
    if not run_id:
        raise GateError(f"real consumer lacks run_id: {gate_id}")
    candidates: list[dict[str, Any]] = []
    if payload.get("run_id") == run_id:
        candidates.append(payload)
    for field in ("consumer_runs", "consumers"):
        values = payload.get(field) or []
        if isinstance(values, list):
            candidates.extend(
                value
                for value in values
                if isinstance(value, dict) and value.get("run_id") == run_id
            )
    if len(candidates) != 1:
        raise GateError(
            f"real consumer run_id must resolve exactly once: {gate_id}: {run_id}"
        )
    run = candidates[0]
    argv = [str(part) for part in run.get("argv") or []]
    if not argv or "--help" in argv or "-h" in argv:
        raise GateError(f"real consumer is help-only/non-operational: {gate_id}: {run_id}")
    expected_failure = bool(run.get("expected_failure"))
    exit_code = run.get("exit_code", 0)
    exit_ok = exit_code != 0 if expected_failure else exit_code == 0
    if run.get("status") not in {None, "pass"} or not exit_ok:
        raise GateError(f"real consumer run did not PASS: {gate_id}: {run_id}")
    required_assertion = str(item.get("assertion") or "")
    assertions = [str(value) for value in run.get("assertions") or []]
    if not required_assertion or required_assertion not in assertions:
        raise GateError(
            f"real consumer lacks bound operational assertion: {gate_id}: {run_id}"
        )
    return run


def validate_gate_matrix(workspace: Path, matrix: dict[str, Any]) -> dict[str, Any]:
    if matrix.get("schema") != SCHEMA:
        raise GateError(f"unsupported gate matrix schema: {matrix.get('schema')!r}")
    rows = matrix.get("rows")
    if not isinstance(rows, list):
        raise GateError("gate matrix rows must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    evidence_count = 0
    proof_fingerprints: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise GateError("gate matrix row must be an object")
        gate_id = str(row.get("gate_id") or "")
        if gate_id in by_id:
            raise GateError(f"duplicate gate id: {gate_id}")
        by_id[gate_id] = row
        if row.get("status") != "closed":
            raise GateError(f"gate is not closed: {gate_id}={row.get('status')!r}")
        if not str(row.get("requirement") or "").strip():
            raise GateError(f"gate lacks requirement text: {gate_id}")
        evidence = row.get("evidence_files")
        if not isinstance(evidence, list) or not evidence:
            raise GateError(f"gate lacks evidence_files: {gate_id}")
        evidence_map: dict[str, str] = {}
        for item in evidence:
            if not isinstance(item, dict):
                raise GateError(f"invalid evidence entry: {gate_id}")
            declared = str(item.get("sha256") or "")
            if not SHA_RE.fullmatch(declared):
                raise GateError(f"invalid evidence sha: {gate_id}")
            path = safe_member_path(workspace, str(item.get("path") or ""))
            actual = sha256_file(path)
            if actual != declared:
                raise GateError(f"evidence sha mismatch: {gate_id}: {path}")
            rel = path.relative_to(workspace.resolve()).as_posix()
            if rel in evidence_map:
                raise GateError(f"duplicate evidence path: {gate_id}: {rel}")
            evidence_map[rel] = declared
            evidence_count += 1
        symbols = row.get("implementation_symbols")
        if not isinstance(symbols, list) or not symbols:
            raise GateError(f"gate lacks implementation_symbols: {gate_id}")
        for item in symbols:
            if not isinstance(item, dict):
                raise GateError(f"implementation symbol must be an object: {gate_id}")
            path = safe_member_path(workspace, str(item.get("path") or ""))
            symbol = str(item.get("symbol") or "")
            if not symbol or symbol in {"module.symbol", "implemented"}:
                raise GateError(f"placeholder implementation symbol: {gate_id}")
            if symbol not in path.read_text(encoding="utf-8", errors="replace"):
                raise GateError(f"unresolved implementation symbol: {gate_id}: {symbol}")
        for field in ("positive_tests", "negative_tests"):
            tests = row.get(field)
            if not isinstance(tests, list) or not tests:
                raise GateError(f"gate lacks {field}: {gate_id}")
            for item in tests:
                if not isinstance(item, dict):
                    raise GateError(f"gate test must be an object: {gate_id}")
                test_path = safe_member_path(workspace, str(item.get("path") or ""))
                test_name = str(item.get("test") or "")
                if not test_name.startswith("test_") or test_name not in test_path.read_text(
                    encoding="utf-8", errors="replace"
                ):
                    raise GateError(f"unresolved test name: {gate_id}: {test_name}")
                _, report, _ = checked_report(
                    workspace, item, evidence_map, gate_id=gate_id
                )
                stdout = safe_member_path(workspace, str(report.get("stdout_path") or ""))
                if (
                    report.get("command_schema") != "unittest"
                    or not stdout.is_file()
                    or test_name not in stdout.read_text(encoding="utf-8", errors="replace")
                ):
                    raise GateError(f"test is not present in durable PASS output: {gate_id}: {test_name}")
        consumers = row.get("real_consumers")
        if not isinstance(consumers, list) or not consumers:
            raise GateError(f"gate lacks real_consumers: {gate_id}")
        for item in consumers:
            if not isinstance(item, dict):
                raise GateError(f"real consumer must be an object: {gate_id}")
            consumer = safe_member_path(workspace, str(item.get("path") or ""))
            if not consumer.is_file():
                raise GateError(f"real consumer missing: {gate_id}: {consumer}")
            _, report, _ = checked_report(workspace, item, evidence_map, gate_id=gate_id)
            run = checked_consumer_run(report, item, gate_id=gate_id)
            needle = str(item.get("argv_contains") or consumer.name)
            if needle not in " ".join(str(part) for part in run.get("argv") or []):
                raise GateError(f"real consumer absent from durable argv: {gate_id}: {needle}")
        recovery = row.get("recovery_evidence")
        if not isinstance(recovery, list) or not recovery:
            raise GateError(f"gate lacks recovery_evidence: {gate_id}")
        for item in recovery:
            if not isinstance(item, dict):
                raise GateError(f"recovery evidence must be an object: {gate_id}")
            _, _, raw = checked_report(workspace, item, evidence_map, gate_id=gate_id)
            assertion = str(item.get("assertion_contains") or "")
            if not assertion or assertion not in raw.decode("utf-8", errors="replace"):
                raise GateError(f"recovery assertion absent: {gate_id}: {assertion}")
        proof = sha256_bytes(
            canonical_bytes(
                {
                    "symbols": symbols,
                    "positive": row["positive_tests"],
                    "negative": row["negative_tests"],
                    "consumers": consumers,
                    "recovery": recovery,
                }
            )
        )
        if proof in proof_fingerprints:
            raise GateError(f"unrelated gates reuse an identical proof envelope: {gate_id}")
        proof_fingerprints.add(proof)
    actual_ids = set(by_id)
    expected_ids = set(REQUIRED_GATE_IDS)
    missing = sorted(expected_ids - actual_ids)
    extra = sorted(actual_ids - expected_ids)
    if missing or extra:
        raise GateError(f"gate id set mismatch: missing={missing}, extra={extra}")
    return {
        "status": "closed",
        "gate_count": len(rows),
        "evidence_reference_count": evidence_count,
        "gate_ids_sha256": sha256_bytes("\n".join(sorted(actual_ids)).encode("utf-8")),
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise GateError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GateError(f"JSON root must be an object: {path}")
    return value


def write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise GateError(f"immutable output already exists: {path}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        raise GateError(f"stale package temp exists: {tmp}")
    try:
        with tmp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if tmp.read_bytes() != raw:
            raise GateError("package temp readback mismatch")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def freeze_package(
    workspace: Path,
    matrix_path: Path,
    members_path: Path,
    output_path: Path,
) -> tuple[dict[str, Any], str]:
    matrix = load_json(matrix_path)
    matrix_summary = validate_gate_matrix(workspace, matrix)
    members_doc = load_json(members_path)
    members = members_doc.get("members")
    if not isinstance(members, list):
        raise GateError("package members must be a list")
    roles: set[str] = set()
    paths: set[str] = set()
    frozen: list[dict[str, Any]] = []
    for member in members:
        if not isinstance(member, dict):
            raise GateError("package member must be an object")
        role = str(member.get("role") or "")
        rel = str(member.get("path") or "")
        if not role or role in roles:
            raise GateError(f"missing/duplicate package role: {role!r}")
        if not rel or rel in paths:
            raise GateError(f"missing/duplicate package path: {rel!r}")
        roles.add(role)
        paths.add(rel)
        path = safe_member_path(workspace, rel)
        actual = sha256_file(path)
        declared = member.get("sha256")
        if declared is not None and declared != actual:
            raise GateError(f"package member sha mismatch: {role}: {path}")
        frozen.append(
            {
                "role": role,
                "path": path.relative_to(workspace.resolve()).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": actual,
            }
        )
    missing_roles = sorted(REQUIRED_PACKAGE_ROLES - roles)
    if missing_roles:
        raise GateError(f"package missing required roles: {missing_roles}")
    matrix_resolved = matrix_path.resolve()
    matrix_roles = [
        row for row in frozen if safe_member_path(workspace, row["path"]) == matrix_resolved
    ]
    if len(matrix_roles) != 1 or matrix_roles[0]["role"] != "closure_matrix":
        raise GateError("closure_matrix member does not bind validated matrix bytes")
    payload = {
        "schema": PACKAGE_SCHEMA,
        "campaign_id": matrix.get("campaign_id"),
        "package_id": members_doc.get("package_id"),
        "closure": matrix_summary,
        "member_count": len(frozen),
        "members": sorted(frozen, key=lambda row: (row["role"], row["path"])),
    }
    raw = canonical_bytes(payload)
    write_exclusive(output_path, raw)
    return payload, sha256_bytes(raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--workspace", type=Path, required=True)
    validate.add_argument("--matrix", type=Path, required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--workspace", type=Path, required=True)
    freeze.add_argument("--matrix", type=Path, required=True)
    freeze.add_argument("--members", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workspace = args.workspace.resolve()
        if args.command == "validate":
            summary = validate_gate_matrix(workspace, load_json(args.matrix))
            result = {"ok": True, **summary}
        else:
            package, digest = freeze_package(
                workspace, args.matrix, args.members, args.output.resolve()
            )
            result = {
                "ok": True,
                "package": str(args.output.resolve()),
                "package_sha256": digest,
                "member_count": package["member_count"],
                **package["closure"],
            }
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
