#!/usr/bin/env python3
"""T2AG 0.2.1 profile-container migration and evidence writer.

The default mode is a read-only check.  ``--apply`` copies each legacy flat
profile file, verifies the byte hash, and only then retires the old path.
``--write-evidence`` binds the applied targets to an explicit Git baseline.
Lite is derived and is never accepted as a migration input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


MOVES = (
    (
        "main/10_student/profile.md",
        "main/10_student/profile/profile.md",
    ),
    (
        "main/10_student/learning_path.md",
        "main/10_student/profile/learning_path.md",
    ),
    (
        "main/10_student/course_reflections.md",
        "main/10_student/profile/course_reflections.md",
    ),
    (
        "main/10_student/reasoning_patterns.md",
        "main/10_student/profile/reasoning_patterns.md",
    ),
)
OPERATIONS_PATH = Path("main/60_journal/migration_021_profile_operations.json")
REPORT_PATH = Path("main/60_journal/migration_021_profile_report.json")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-021")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def detect_kind(repo: Path) -> str:
    if repo.name == "t2ag-lite":
        return "lite"
    if repo.name == "t2ag-skeleton":
        return "skeleton"
    return "main"


def resolve_repo(script_repo: Path, target: str) -> tuple[Path, str]:
    if target == "lite":
        raise ValueError("Lite is derived and cannot be a migration input")
    current_kind = detect_kind(script_repo)
    if target == "auto":
        repo = script_repo
        kind = current_kind
    elif target == current_kind:
        repo = script_repo
        kind = target
    else:
        repo = script_repo.parent / (
            "t2ag-skeleton" if target == "skeleton" else "t2ag"
        )
        kind = target
    if detect_kind(repo) == "lite":
        raise ValueError("Lite is derived and cannot be a migration input")
    if not (repo / "main/10_student").is_dir():
        raise ValueError(f"invalid T2AG repository root: {repo}")
    return repo.resolve(), kind


def inspect(repo: Path) -> dict[str, object]:
    pending: list[dict[str, str]] = []
    missing: list[str] = []
    collisions: list[dict[str, str]] = []
    applied: list[str] = []
    for source_relative, target_relative in MOVES:
        source = repo / source_relative
        target = repo / target_relative
        if source.is_file() and not target.exists():
            pending.append({"source": source_relative, "target": target_relative})
        elif source.is_file() and target.is_file():
            if sha256(source) != sha256(target):
                collisions.append({
                    "source": source_relative,
                    "target": target_relative,
                })
            else:
                pending.append({
                    "source": source_relative,
                    "target": target_relative,
                })
        elif not source.exists() and target.is_file():
            applied.append(target_relative)
        else:
            missing.append(f"{source_relative} -> {target_relative}")
    return {
        "pending_count": len(pending),
        "pending": pending,
        "missing": missing,
        "collisions": collisions,
        "applied": applied,
    }


def apply(repo: Path) -> int:
    before = inspect(repo)
    if before["missing"] or before["collisions"]:
        raise RuntimeError(
            "migration preflight blockers: "
            f"missing={before['missing']} collisions={before['collisions']}"
        )
    moved = 0
    for source_relative, target_relative in MOVES:
        source = repo / source_relative
        target = repo / target_relative
        if not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source_hash = sha256(source)
        if not target.exists():
            shutil.copy2(source, target)
        if not target.is_file() or sha256(target) != source_hash:
            raise RuntimeError(
                f"hash verification failed: {source_relative} -> {target_relative}"
            )
        source.unlink()
        moved += 1
    after = inspect(repo)
    if after["pending_count"] or after["missing"] or after["collisions"]:
        raise RuntimeError(f"post-apply verification failed: {after}")
    return moved


def git_show(repo: Path, revision: str, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"baseline source unavailable: {revision}:{relative}: {message}"
        )
    return result.stdout


def reverse_allowed_path_repairs(target_relative: str, content: str) -> str:
    replacements = (
        ("main/10_student/profile/profile.md", "main/10_student/profile.md"),
        ("main/10_student/profile/learning_path.md", "main/10_student/learning_path.md"),
        (
            "main/10_student/profile/course_reflections.md",
            "main/10_student/course_reflections.md",
        ),
        (
            "main/10_student/profile/reasoning_patterns.md",
            "main/10_student/reasoning_patterns.md",
        ),
        ("10_student/profile/profile.md", "10_student/profile.md"),
        ("10_student/profile/learning_path.md", "10_student/learning_path.md"),
        (
            "10_student/profile/course_reflections.md",
            "10_student/course_reflections.md",
        ),
        (
            "10_student/profile/reasoning_patterns.md",
            "10_student/reasoning_patterns.md",
        ),
    )
    normalized = content
    for new, old in replacements:
        normalized = normalized.replace(new, old)
    if target_relative.endswith("/course_reflections.md"):
        normalized = normalized.replace("../../40_course/", "../40_course/")
    return normalized


def write_evidence(repo: Path, target_kind: str, baseline: str) -> None:
    state = inspect(repo)
    if state["pending_count"] or state["missing"] or state["collisions"]:
        raise RuntimeError(f"migration is not fully applied: {state}")
    rows: list[dict[str, object]] = []
    for sequence, (source_relative, target_relative) in enumerate(MOVES, start=1):
        source_bytes = git_show(repo, baseline, source_relative)
        target = repo / target_relative
        target_bytes = target.read_bytes()
        source_hash = sha256_bytes(source_bytes)
        target_hash = sha256_bytes(target_bytes)
        source_text = source_bytes.decode("utf-8-sig")
        target_text = target_bytes.decode("utf-8-sig")
        normalized_target = reverse_allowed_path_repairs(
            target_relative,
            target_text,
        )
        if source_text != normalized_target:
            raise RuntimeError(
                "content changed beyond allowed path repairs: "
                f"{source_relative} -> {target_relative}"
            )
        rows.append({
            "sequence": sequence,
            "kind": "move",
            "sources": [{
                "path": source_relative,
                "bytes": len(source_bytes),
                "sha256": source_hash,
            }],
            "target": target_relative,
            "disposition": "move shared student profile file into profile container",
            "outcome": "applied",
            "content_check": (
                "byte_identical"
                if source_text == target_text
                else "path_repairs_only"
            ),
            "post_target": {
                "path": target_relative,
                "bytes": len(target_bytes),
                "sha256": target_hash,
            },
        })
    manifest = {
        "schema_version": "T2AG-MIGRATION-OPERATIONS-1",
        "target_kind": target_kind,
        "evidence_source": f"git baseline {baseline}",
        "baseline_commit": baseline,
        "operation_count": len(rows),
        "operations": rows,
    }
    manifest_path = repo / OPERATIONS_PATH
    atomic_write(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    report = {
        "schema_version": "T2AG-MIGRATION-REPORT-1",
        "status": "applied",
        "target_kind": target_kind,
        "baseline_commit": baseline,
        "applied_count": len(rows),
        "operation_manifest": {
            "path": OPERATIONS_PATH.as_posix(),
            "operation_count": len(rows),
            "sha256": sha256(manifest_path),
        },
        "current_verification": {
            "pending_count": 0,
            "missing": [],
            "collisions": [],
        },
        "content_preservation": "byte-identical or normalized path repairs only",
    }
    atomic_write(
        repo / REPORT_PATH,
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only check (default)")
    mode.add_argument("--apply", action="store_true", help="copy, verify, and retire old paths")
    mode.add_argument(
        "--write-evidence",
        action="store_true",
        help="write report bound to an explicit pre-migration Git baseline",
    )
    parser.add_argument(
        "--target",
        choices=("auto", "main", "skeleton", "lite"),
        default="auto",
    )
    parser.add_argument("--baseline", help="pre-migration commit for evidence mode")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        repo, target_kind = resolve_repo(
            Path(__file__).resolve().parents[2],
            args.target,
        )
        if args.apply:
            moved = apply(repo)
            print(f"applied={moved}")
        if args.write_evidence:
            if not args.baseline:
                raise ValueError("--write-evidence requires --baseline")
            write_evidence(repo, target_kind, args.baseline)
            print(f"evidence={REPORT_PATH.as_posix()}")
        state = inspect(repo)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[FAIL] {exc}")
        return 2

    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(f"target={repo}")
        print(f"pending={state['pending_count']}")
        print(f"missing={len(state['missing'])}")
        print(f"collisions={len(state['collisions'])}")
    return 1 if state["pending_count"] or state["missing"] or state["collisions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
