#!/usr/bin/env python3
"""Recoverable 0.2.1 ActivityRecord kind migration and Main-only evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

from migration_txn_021 import (
    MigrationTransactionError,
    MoveOperation,
    apply_transaction,
    inspect_operations,
    recover,
    sha256_bytes,
)


MIGRATION_ID = "T2AG-021-ACTIVITY-RECORDS-V1"
TRANSFORM_VERSION = "t2ag.activity-record-kind.v1"
SOURCE = "main/10_student/activities/AR-0001_InvestingNotes.md"
TARGET = "main/10_student/activities/reading/AR-0001_InvestingNotes.md"
BASELINE_COMMIT = "4e72556f789fcb5943951657ee17247c0dd4eb12"
BASELINE_TREE = "7270b5fa7954fec12d2e5ff3f76ee388036dff1b"
SOURCE_BLOB = "79eeee83bc28be3e3f315e4458b8b9e23b0163eb"
SOURCE_BYTES = 951
SOURCE_SHA256 = "86cda835dac82d8ad235e01205e25aef5bcaea4e701b62f7db06f6e4842ec9b0"
TARGET_BYTES = 982
TARGET_SHA256 = "75c6b766df611312d84e8fa6f56d1f47237e5fcafaf08e01e045f273c4687ddb"
MANIFEST_PATH = Path("main/60_journal/migration_021_activity_record_operations.json")
REPORT_PATH = Path("main/60_journal/migration_021_activity_record_report.json")


def transform_activity_record(content: bytes) -> bytes:
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MigrationTransactionError("ActivityRecord source must be UTF-8") from exc
    marker = b"type: activity_record\n"
    old_path = SOURCE.encode("utf-8")
    if content.count(marker) != 1 or content.count(old_path) != 1:
        raise MigrationTransactionError("ActivityRecord transform replacement count mismatch")
    transformed = content.replace(marker, marker + b"activity_kind: reading\n", 1)
    return transformed.replace(old_path, TARGET.encode("utf-8"), 1)


OPERATION = MoveOperation(SOURCE, TARGET, "activity-record-reading-kind-v1", transform_activity_record)


def detect_kind(repo: Path) -> str:
    readme = repo / "README.md"
    heading = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""
    return (
        "skeleton"
        if repo.name == "t2ag-skeleton"
        or re.search(r"^# T2AG .* Skeleton\s*$", heading, re.MULTILINE)
        else "main"
    )


def resolve_repo(script_repo: Path, target: str) -> tuple[Path, str]:
    if target == "lite":
        raise MigrationTransactionError("Lite is derived and cannot be a migration input")
    current = detect_kind(script_repo)
    if target == "auto":
        repo, kind = script_repo, current
    elif target == current:
        repo, kind = script_repo, target
    else:
        repo = script_repo.parent / ("t2ag-skeleton" if target == "skeleton" else "t2ag")
        kind = target
    if not (repo / "main/10_student/activities").is_dir():
        raise MigrationTransactionError(f"invalid T2AG repository root: {repo}")
    return repo.resolve(), kind


def inspect(repo: Path, target_kind: str | None = None) -> dict[str, object]:
    kind = target_kind or detect_kind(repo)
    if kind == "skeleton":
        blockers: list[str] = []
        if (repo / SOURCE).exists() or (repo / TARGET).exists():
            blockers.append("Skeleton contains real AR-0001")
        if not (repo / "main/10_student/activities/reading").is_dir():
            blockers.append("Skeleton missing reading container")
        return {"applicable": False, "pending": [], "applied": [], "blockers": blockers}
    return {"applicable": True, **inspect_operations(repo, (OPERATION,))}


def git_text(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if result.returncode:
        raise MigrationTransactionError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def git_bytes(repo: Path, revision: str, path: str) -> bytes:
    result = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=repo, capture_output=True)
    if result.returncode:
        raise MigrationTransactionError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def atomic_json(path: Path, value: dict[str, object]) -> None:
    content = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_evidence(repo: Path, target_kind: str, baseline: str | None) -> None:
    if target_kind != "main":
        raise MigrationTransactionError("Skeleton has no real ActivityRecord migration evidence")
    commit = baseline or BASELINE_COMMIT
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or commit != BASELINE_COMMIT:
        raise MigrationTransactionError("baseline commit is not the frozen Main baseline")
    tree = git_text(repo, "show", "-s", "--format=%T", commit)
    source_blob = git_text(repo, "rev-parse", f"{commit}:{SOURCE}")
    source = git_bytes(repo, commit, SOURCE)
    target = transform_activity_record(source)
    if (
        tree != BASELINE_TREE
        or source_blob != SOURCE_BLOB
        or len(source) != SOURCE_BYTES
        or sha256_bytes(source) != SOURCE_SHA256
        or len(target) != TARGET_BYTES
        or sha256_bytes(target) != TARGET_SHA256
    ):
        raise MigrationTransactionError("ActivityRecord independent golden mismatch")
    manifest: dict[str, object] = {
        "schema_version": "T2AG-ACTIVITY-MIGRATION-OPERATIONS-1",
        "migration_id": MIGRATION_ID,
        "target_kind": "main",
        "baseline_commit": commit,
        "baseline_tree": tree,
        "transform_version": TRANSFORM_VERSION,
        "operation_count": 1,
        "operations": [{
            "sequence": 1,
            "transform_id": OPERATION.transform_id,
            "source": {"path": SOURCE, "blob": source_blob, "bytes": len(source), "sha256": sha256_bytes(source)},
            "target": TARGET,
            "replacement_counts": {"activity_kind_insert": 1, "self_path": 1},
            "outcome": "applied",
            "post_target": {"path": TARGET, "bytes": len(target), "sha256": sha256_bytes(target)},
        }],
    }
    manifest_path = repo / MANIFEST_PATH
    atomic_json(manifest_path, manifest)
    report: dict[str, object] = {
        "schema_version": "T2AG-ACTIVITY-MIGRATION-REPORT-1",
        "migration_id": MIGRATION_ID,
        "status": "applied",
        "target_kind": "main",
        "baseline_commit": commit,
        "baseline_tree": tree,
        "transform_version": TRANSFORM_VERSION,
        "operation_manifest": {
            "path": MANIFEST_PATH.as_posix(),
            "operation_count": 1,
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        },
        "current_verification": {"target_present": (repo / TARGET).is_file(), "source_absent": not (repo / SOURCE).exists()},
        "content_policy": "insert activity_kind once and replace exact self-path once",
    }
    atomic_json(repo / REPORT_PATH, report)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--recover", action="store_true")
    mode.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--target", choices=("auto", "main", "skeleton", "lite"), default="auto")
    parser.add_argument("--baseline")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        repo, kind = resolve_repo(Path(__file__).resolve().parents[2], args.target)
        if args.apply:
            if kind == "skeleton":
                print("applied=0")
            else:
                print(f"applied={apply_transaction(repo, MIGRATION_ID, (OPERATION,))}")
        elif args.recover:
            print(f"recover={recover(repo, MIGRATION_ID)}")
        elif args.write_evidence:
            write_evidence(repo, kind, args.baseline)
            print(f"evidence={REPORT_PATH.as_posix()}")
        state = inspect(repo, kind)
        print(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) if args.json else f"target={kind} pending={len(state['pending'])} applied={len(state['applied'])} blockers={len(state['blockers'])}")
        return 1 if state["pending"] or state["blockers"] else 0
    except (OSError, MigrationTransactionError, ValueError) as exc:
        print(f"[FAIL] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
