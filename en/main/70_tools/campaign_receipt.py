#!/usr/bin/env python3
"""Machine-readable campaign receipts for T2AG-022 V3 (RT2).

Receipts are append-only new files (temp + fsync + atomic replace).
Never overwrite a failed receipt with PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CAMPAIGN_ID = "T2AG-022-ACTIVITY-CLOSE-V2-20260804"
PHASES = [
    "AD_REMEDIATING",
    "D_PACKAGE_FROZEN",
    "D_INDEPENDENT_PASSED",
    "E_AUTHORIZED",
    "E_APPLYING",
    "E_INSTALLED_PENDING_POSTCHECK",
    "E_COMMITTED",
    "F0_PENDING",
    "F_AUTHORIZED",
    "F_APPLIED",
    "G_PROPOSED_CANDIDATE",
    "G_CANDIDATE_FROZEN",
    "V_PASSED",
    "FIN_PROPOSED",
    "FIN_FINALIZING",
    "COMPLETE_022",
]


def now_tz() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(cwd: Path, *args: str) -> str:
    run = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if run.returncode != 0:
        return ""
    # Git porcelain uses the first two columns as data.  Stripping the whole
    # stream destroys a leading space on the first row (for example
    # `` M AGENTS.md`` becomes ``M AGENTS.md``), which in turn shifts the path
    # column and can silently omit a dirty candidate file from a manifest.
    # Only remove the process line terminator; callers that consume ordinary
    # one-line Git output still receive the same value.
    return (run.stdout or "").rstrip("\r\n")


def worktree_manifest_sha(root: Path) -> str:
    """Hash of porcelain -uall + blob hashes of dirty paths (stable)."""
    porcelain = git(root, "status", "--porcelain=v1", "-uall")
    lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    rows: list[str] = []
    for ln in lines:
        path = ln[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        p = root / path
        if p.is_file():
            rows.append(f"{ln}\t{p.stat().st_size}\t{sha256_file(p)}")
        else:
            rows.append(f"{ln}\tMISSING")
    body = "\n".join(rows) + "\n"
    return sha256_bytes(body.encode("utf-8"))


def executor_bundle_sha(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: str(p).replace("\\", "/")):
        if not path.is_file():
            continue
        rel = path.name
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update((sha256_file(path) or "").encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def receipt_dir(workspace: Path) -> Path:
    return workspace / "docs" / "handoffs" / "receipts"


def receipt_records(workspace: Path) -> list[dict[str, Any]]:
    """Read immutable campaign receipts and attach their byte digests.

    Ordering is deliberately not inferred from filenames or mtimes.  The
    previous-SHA graph is the only ordering authority.
    """
    d = receipt_dir(workspace)
    if not d.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(d.glob("*.json"), key=lambda p: p.name):
        try:
            raw = path.read_bytes()
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"invalid receipt {path}: {exc}") from exc
        if data.get("campaign_id") != CAMPAIGN_ID:
            continue
        records.append(
            {
                "path": path,
                "sha256": sha256_bytes(raw),
                "data": data,
            }
        )
    return records


def validate_receipt_chain(
    workspace: Path,
) -> tuple[Path | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """Return the unique valid graph head and the ordered active chain.

    A rejected side branch is allowed only when an active receipt explicitly
    names its digest in ``rejected_receipt_sha256``.  This preserves failed
    evidence without letting it become an authorization ancestor.
    """
    records = receipt_records(workspace)
    if not records:
        return None, None, []
    by_sha = {r["sha256"]: r for r in records}
    if len(by_sha) != len(records):
        raise RuntimeError("duplicate receipt bytes in campaign")
    rejected: set[str] = set()
    for record in records:
        values = record["data"].get("rejected_receipt_sha256") or []
        if isinstance(values, str):
            values = [values]
        rejected.update(str(v) for v in values)
    unknown_rejected = rejected - set(by_sha)
    if unknown_rejected:
        raise RuntimeError(f"unknown rejected receipt(s): {sorted(unknown_rejected)}")
    active = {sha: r for sha, r in by_sha.items() if sha not in rejected}
    referenced: set[str] = set()
    for sha, record in active.items():
        data = record["data"]
        phase = data.get("phase")
        if phase not in PHASES:
            raise RuntimeError(f"unknown receipt phase {phase!r}: {record['path']}")
        prev = data.get("previous_receipt_sha256")
        if prev:
            if prev not in active:
                raise RuntimeError(f"missing/rejected predecessor {prev} for {sha}")
            referenced.add(prev)
            prev_phase = active[prev]["data"].get("phase")
            if PHASES.index(phase) < PHASES.index(prev_phase):
                raise RuntimeError(f"invalid phase regression {prev_phase}->{phase}")
            if PHASES.index(phase) > PHASES.index(prev_phase) + 1:
                raise RuntimeError(f"invalid phase skip {prev_phase}->{phase}")
    # Detect cycles explicitly before head selection; a pure cycle has no head.
    for start in active:
        local: set[str] = set()
        cursor: str | None = start
        while cursor:
            if cursor in local:
                raise RuntimeError(f"receipt cycle at {cursor}")
            local.add(cursor)
            cursor = active[cursor]["data"].get("previous_receipt_sha256")
    heads = sorted(set(active) - referenced)
    if len(heads) != 1:
        raise RuntimeError(f"receipt graph must have one head, got {heads}")
    head_sha = heads[0]
    ordered_rev: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor: str | None = head_sha
    while cursor:
        if cursor in seen:
            raise RuntimeError(f"receipt cycle at {cursor}")
        seen.add(cursor)
        record = active[cursor]
        ordered_rev.append(record)
        cursor = record["data"].get("previous_receipt_sha256")
    if seen != set(active):
        missing = sorted(set(active) - seen)
        raise RuntimeError(f"receipt chain skips active receipt(s): {missing}")
    ordered = list(reversed(ordered_rev))
    head = active[head_sha]
    return head["path"], head["data"], ordered


def latest_receipt(workspace: Path) -> tuple[Path | None, dict[str, Any] | None]:
    path, data, _ = validate_receipt_chain(workspace)
    return path, data


def write_receipt(workspace: Path, payload: dict[str, Any]) -> tuple[Path, str]:
    d = receipt_dir(workspace)
    d.mkdir(parents=True, exist_ok=True)
    name = (
        f"{payload.get('phase', 'PHASE')}_"
        f"{payload.get('state', 'STATE')}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    )
    path = d / name
    if path.exists():
        raise RuntimeError(f"receipt path exists: {path}")
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if tmp.read_bytes() != raw:
        raise RuntimeError("receipt temp verify failed")
    os.replace(tmp, path)
    return path, sha256_bytes(raw)


def build_r0_receipt(
    workspace: Path, main: Path, skel: Path, reading: Path | None
) -> dict[str, Any]:
    prev_path, prev = latest_receipt(workspace)
    tools = main / "main" / "70_tools"
    bundle_paths = [
        tools / "activity_ledger.py",
        tools / "activity_transaction.py",
        tools / "activity_close.py",
        tools / "migrate_022_activity_close.py",
        tools / "t2ag_activity.py",
        tools / "t2ag_doctor.py",
        tools / "campaign_receipt.py",
    ]
    u1101 = main / "main/40_course/MATH1607H/exercises/U1101"
    payload = {
        "campaign_id": CAMPAIGN_ID,
        "phase": "AD_REMEDIATING",
        "state": "R0_completed",
        "previous_receipt_path": str(prev_path) if prev_path else None,
        "previous_receipt_sha256": (
            sha256_file(prev_path) if prev_path and prev_path.is_file() else None
        ),
        "started_at": now_tz(),
        "recorded_at": now_tz(),
        "finished_at": now_tz(),
        "repos": {
            "main": {
                "head": git(main, "rev-parse", "HEAD"),
                "tree": git(main, "show", "-s", "--format=%T", "HEAD"),
                "worktree_manifest_sha256": worktree_manifest_sha(main),
            },
            "skeleton": {
                "head": git(skel, "rev-parse", "HEAD"),
                "tree": git(skel, "show", "-s", "--format=%T", "HEAD"),
                "worktree_manifest_sha256": worktree_manifest_sha(skel),
            },
            "reading": (
                {
                    "head": git(reading, "rev-parse", "HEAD"),
                    "tree": git(reading, "show", "-s", "--format=%T", "HEAD"),
                    "porcelain_empty": git(reading, "status", "--porcelain=v1", "-uall")
                    == "",
                }
                if reading is not None
                else None
            ),
        },
        "executor_bundle_sha256": executor_bundle_sha(
            [p for p in bundle_paths if p.is_file()]
        ),
        "instance": {
            "u1101_exists": u1101.is_dir(),
            "u1101_files": (
                sum(1 for p in u1101.rglob("*") if p.is_file()) if u1101.is_dir() else 0
            ),
            "exercise01_exists": (
                main / "main/40_course/MATH1607H/exercises/exercise01"
            ).exists(),
            "ledger_count": len(
                list((main / "main/40_course").rglob("activity_ledger.md"))
            ),
            "activity_txn_exists": (main / ".activity_txn").exists(),
            "T2AG_022_ALLOW_APPLY": os.environ.get("T2AG_022_ALLOW_APPLY"),
        },
        "revoked_plans": [
            {
                "payload_sha256": "d897e665d1f8813767c5113839127b3a3d2d70c7bd381f317118498cbe9b3e4f",
                "file_sha256": "22795758372e493b8cb285b8838055eff869aa553555662c15460abeec9d2069",
                "status": "revoked",
            },
            {
                "payload_sha256": "4affe7c0466ef0175e99cfc3c1c5cffad83c5072837599f4dacd6e802519a790",
                "file_sha256": "197c685ffd18c78d4f3c06ead8c76fb8b844496e014f4caa473cf81b8e35537b",
                "status": "revoked",
            },
        ],
        "evidence": [
            "docs/handoffs/archive/v0.2.2/T2AG_022_EXECUTION_REPORT_2026-08-04.md#R0",
            "docs/handoffs/archive/v0.2.2/T2AG_022_MIGRATION_PLAN_2026-08-04.md#REVOKED",
        ],
        "argv": sys.argv,
        "cwd": str(Path.cwd()),
        "python": sys.version.split()[0],
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--validate-chain", action="store_true")
    parser.add_argument("--emit-r0", action="store_true")
    parser.add_argument("--emit-json", default=None, help="path to payload json to wrap")
    parser.add_argument(
        "--reading-root",
        type=Path,
        default=None,
        help="the optional root path of the third repository (the reading system); without it the receipt carries no reading binding",
    )
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    main_root = workspace / "t2ag"
    skel = workspace / "t2ag-skeleton"
    # EV-0023: the third repository's path is no longer a hard-coded maintainer machine literal; the caller
    # passes it explicitly.
    reading = args.reading_root.resolve() if args.reading_root else None
    if args.validate_chain:
        head_path, head_data, chain = validate_receipt_chain(workspace)
        if not head_path or head_data is None:
            print(json.dumps({"ok": False, "error": "receipt chain is empty"}))
            return 2
        print(
            json.dumps(
                {
                    "ok": True,
                    "status": "pass",
                    "head_path": str(head_path.resolve()),
                    "head_sha256": sha256_file(head_path),
                    "head_phase": head_data.get("phase"),
                    "chain_length": len(chain),
                    "assertions": [
                        "unique_active_head",
                        "sha_linked_predecessors",
                        "no_phase_skip_or_regression",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if args.emit_r0:
        payload = build_r0_receipt(workspace, main_root, skel, reading)
        path, digest = write_receipt(workspace, payload)
        print(
            json.dumps(
                {"ok": True, "path": str(path), "sha256": digest, "phase": payload["phase"], "state": payload["state"]},
                ensure_ascii=False,
            )
        )
        return 0
    if args.emit_json:
        payload = json.loads(Path(args.emit_json).read_bytes().decode("utf-8"))
        path, digest = write_receipt(workspace, payload)
        print(json.dumps({"ok": True, "path": str(path), "sha256": digest}, ensure_ascii=False))
        return 0
    print(json.dumps({"ok": False, "error": "no action"}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
