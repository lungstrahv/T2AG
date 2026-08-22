#!/usr/bin/env python3
"""Deterministic, recoverable T2AG 0.2.1 profile-container migration."""
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


MIGRATION_ID = "T2AG-021-PROFILE-V2"
TRANSFORM_VERSION = "t2ag.profile-path-repairs.v2"
V1_OPERATIONS_PATH = Path("main/60_journal/migration_021_profile_operations.json")
V1_REPORT_PATH = Path("main/60_journal/migration_021_profile_report.json")
OPERATIONS_PATH = Path("main/60_journal/migration_021_profile_operations_v2.json")
REPORT_PATH = Path("main/60_journal/migration_021_profile_report_v2.json")

MOVES = (
    ("main/10_student/profile.md", "main/10_student/profile/profile.md"),
    ("main/10_student/learning_path.md", "main/10_student/profile/learning_path.md"),
    ("main/10_student/course_reflections.md", "main/10_student/profile/course_reflections.md"),
    ("main/10_student/reasoning_patterns.md", "main/10_student/profile/reasoning_patterns.md"),
)

BASELINES = {
    "main": {
        "commit": "4e72556f789fcb5943951657ee17247c0dd4eb12",
        "tree": "7270b5fa7954fec12d2e5ff3f76ee388036dff1b",
    },
    "skeleton": {
        "commit": "3f1a42e0edc305f3253843337a9ec7a107cd79a8",
        "tree": "bab94ab06046b55577dc88908069dfbe1e160419",
    },
}

GOLDEN = {
    "main": {
        "main/10_student/profile.md": (
            8136,
            "9d7d5d53b39b2fce493794f611f0a7cf61d4076ac1862f98606d1fa90669e934",
            8168,
            "a09f9d499aefd1f0198f6d049cb66bc9c3d05f353f583b04837b60d6f07da8db",
        ),
        "main/10_student/learning_path.md": (
            2752,
            "e029dc5a84300870444fe6b2c44be93abab04c576a3703f74439d73c46461be7",
            2760,
            "1dfc95ba52f2c49a77e52b985a182a54d2802ee990ea8ec692004d98aa30e305",
        ),
        "main/10_student/course_reflections.md": (
            7063,
            "7b4da047e84c859c9dfe470af7aba5c343edb45e620efaff00d050e18aad5f16",
            7072,
            "4a6d41854e8a2eaffc1b9da58c4542c16f1c76b5c578b16ded393423a66745bd",
        ),
        "main/10_student/reasoning_patterns.md": (
            4887,
            "cee74c2af76e2d61079e1e881f525354d6b23229eb2711eb23ab3bb41ad31dda",
            4887,
            "cee74c2af76e2d61079e1e881f525354d6b23229eb2711eb23ab3bb41ad31dda",
        ),
    },
    "skeleton": {
        "main/10_student/profile.md": (1040, "88cd1224bb9ad92de8b4e528a74ad80ef71a29555d00ddd40b0e5065336df9cd", 1040, "88cd1224bb9ad92de8b4e528a74ad80ef71a29555d00ddd40b0e5065336df9cd"),
        "main/10_student/learning_path.md": (734, "3fec62a3939b487b74a23819a72ee0599e06be39739df7a414bb5c0a00732f22", 734, "3fec62a3939b487b74a23819a72ee0599e06be39739df7a414bb5c0a00732f22"),
        "main/10_student/course_reflections.md": (978, "43c77bc4f232feff1bbd9def071d9bbf70418d863292c467b6f29bdd86b454c6", 978, "43c77bc4f232feff1bbd9def071d9bbf70418d863292c467b6f29bdd86b454c6"),
        "main/10_student/reasoning_patterns.md": (1665, "b27fc9f3b9c865c608f12f1779bfadad7ce08ec8312ee967e19922d7f94e9390", 1665, "b27fc9f3b9c865c608f12f1779bfadad7ce08ec8312ee967e19922d7f94e9390"),
    },
}


def _replace_exact(content: bytes, old: bytes, new: bytes, expected: int) -> tuple[bytes, int]:
    count = content.count(old)
    if count != expected:
        raise MigrationTransactionError(
            f"replacement count mismatch for {old!r}: expected={expected} actual={count}"
        )
    return content.replace(old, new), count


def apply_allowed_path_repairs(
    source_path: str,
    target_path: str,
    target_kind: str,
    source_bytes: bytes,
) -> tuple[bytes, dict[str, int], str]:
    expected_target = dict(MOVES).get(source_path)
    if expected_target != target_path or target_kind not in BASELINES:
        raise MigrationTransactionError("transform spec does not allow this source/target/kind")
    try:
        source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MigrationTransactionError("profile migration source must be UTF-8") from exc
    if target_kind == "skeleton":
        return source_bytes, {}, f"profile-{Path(source_path).stem}-identity-v2"

    counts: dict[str, int] = {}
    transformed = source_bytes
    if source_path == "main/10_student/profile.md":
        rules = (
            (b"main/10_student/profile.md", b"main/10_student/profile/profile.md", 2, "self_profile"),
            (b"main/10_student/course_reflections.md", b"main/10_student/profile/course_reflections.md", 1, "course_reflections"),
            (b"main/10_student/reasoning_patterns.md", b"main/10_student/profile/reasoning_patterns.md", 1, "reasoning_patterns"),
        )
    elif source_path == "main/10_student/learning_path.md":
        rules = ((b"10_student/profile.md", b"10_student/profile/profile.md", 1, "profile_pointer"),)
    elif source_path == "main/10_student/course_reflections.md":
        rules = ((b"../40_course/", b"../../40_course/", 3, "relative_course_links"),)
    else:
        rules = ()
    for old, new, expected, name in rules:
        transformed, count = _replace_exact(transformed, old, new, expected)
        counts[name] = count
    transform_id = f"profile-{Path(source_path).stem}-path-repairs-v2"
    return transformed, counts, transform_id


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
    current_kind = detect_kind(script_repo)
    if target == "auto":
        repo, kind = script_repo, current_kind
    elif target == current_kind:
        repo, kind = script_repo, target
    else:
        repo = script_repo.parent / ("t2ag-skeleton" if target == "skeleton" else "t2ag")
        kind = target
    if not (repo / "main/10_student").is_dir():
        raise MigrationTransactionError(f"invalid T2AG repository root: {repo}")
    return repo.resolve(), kind


def operations(target_kind: str) -> tuple[MoveOperation, ...]:
    result: list[MoveOperation] = []
    for source, target in MOVES:
        _bytes, _counts, transform_id = apply_allowed_path_repairs(source, target, target_kind, b"") if target_kind == "skeleton" else (b"", {}, f"profile-{Path(source).stem}-path-repairs-v2")

        def transform(content: bytes, source_path: str = source, target_path: str = target) -> bytes:
            return apply_allowed_path_repairs(source_path, target_path, target_kind, content)[0]

        result.append(MoveOperation(source, target, transform_id, transform))
    return tuple(result)


def inspect(repo: Path) -> dict[str, object]:
    """Compatibility view used by the contract suite and external preflight callers."""
    state = inspect_operations(repo.resolve(), operations(detect_kind(repo.resolve())))
    blockers = [str(value) for value in state["blockers"]]
    return {
        "pending_count": len(state["pending"]),
        "pending": state["pending"],
        "missing": [value for value in blockers if value.startswith("missing:") or value == "partial-state"],
        "collisions": [value for value in blockers if value.startswith("collision:")],
        "applied": state["applied"],
    }


def apply(repo: Path) -> int:
    """Apply the transaction; non-Git synthetic fixtures use identity transforms."""
    repo = repo.resolve()
    if (repo / ".git").exists():
        operation_set = operations(detect_kind(repo))
    else:
        operation_set = tuple(
            MoveOperation(source, target, f"synthetic-{index}-identity", lambda content: content)
            for index, (source, target) in enumerate(MOVES, start=1)
        )
    return apply_transaction(repo, MIGRATION_ID, operation_set)


def git_bytes(repo: Path, revision: str, path: str) -> bytes:
    result = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=repo, capture_output=True)
    if result.returncode:
        raise MigrationTransactionError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def git_text(repo: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=repo, capture_output=True, text=True)
    if result.returncode:
        raise MigrationTransactionError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _atomic_json(path: Path, value: dict[str, object]) -> None:
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
    expected = BASELINES[target_kind]
    commit = baseline or expected["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or commit != expected["commit"]:
        raise MigrationTransactionError("baseline commit is not the frozen target baseline")
    tree = git_text(repo, "show", "-s", "--format=%T", commit)
    if tree != expected["tree"]:
        raise MigrationTransactionError("baseline tree does not match frozen oracle")
    if not (repo / V1_OPERATIONS_PATH).is_file() or not (repo / V1_REPORT_PATH).is_file():
        raise MigrationTransactionError("superseded V1 evidence must remain present")

    rows: list[dict[str, object]] = []
    for sequence, (source, target) in enumerate(MOVES, start=1):
        source_bytes = git_bytes(repo, commit, source)
        transformed, counts, transform_id = apply_allowed_path_repairs(source, target, target_kind, source_bytes)
        source_size, source_sha, target_size, target_sha = GOLDEN[target_kind][source]
        if (len(source_bytes), sha256_bytes(source_bytes), len(transformed), sha256_bytes(transformed)) != (
            source_size, source_sha, target_size, target_sha
        ):
            raise MigrationTransactionError(f"independent golden mismatch: {source}")
        blob = git_text(repo, "rev-parse", f"{commit}:{source}")
        rows.append({
            "sequence": sequence,
            "transform_id": transform_id,
            "source": {"path": source, "blob": blob, "bytes": source_size, "sha256": source_sha},
            "target": target,
            "replacement_counts": counts,
            "content_policy": "byte_identical" if not counts else "path_repairs_only",
            "outcome": "applied",
            "post_target": {"path": target, "bytes": target_size, "sha256": target_sha},
        })
    manifest: dict[str, object] = {
        "schema_version": "T2AG-MIGRATION-OPERATIONS-2",
        "migration_id": MIGRATION_ID,
        "supersedes": V1_OPERATIONS_PATH.as_posix(),
        "target_kind": target_kind,
        "baseline_commit": commit,
        "baseline_tree": tree,
        "transform_version": TRANSFORM_VERSION,
        "operation_count": len(rows),
        "operations": rows,
    }
    manifest_path = repo / OPERATIONS_PATH
    _atomic_json(manifest_path, manifest)
    report: dict[str, object] = {
        "schema_version": "T2AG-MIGRATION-REPORT-2",
        "migration_id": MIGRATION_ID,
        "supersedes": V1_REPORT_PATH.as_posix(),
        "status": "applied",
        "target_kind": target_kind,
        "baseline_commit": commit,
        "baseline_tree": tree,
        "transform_version": TRANSFORM_VERSION,
        "operation_manifest": {
            "path": OPERATIONS_PATH.as_posix(),
            "operation_count": len(rows),
            "sha256": sha256_bytes(manifest_path.read_bytes()),
        },
        "current_verification": {"targets_present": all((repo / target).is_file() for _, target in MOVES)},
        "content_policy": "only frozen path repairs; live targets remain mutable after migration",
    }
    _atomic_json(repo / REPORT_PATH, report)


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
        repo, target_kind = resolve_repo(Path(__file__).resolve().parents[2], args.target)
        operation_set = operations(target_kind)
        if args.apply:
            print(f"applied={apply_transaction(repo, MIGRATION_ID, operation_set)}")
        elif args.recover:
            print(f"recover={recover(repo, MIGRATION_ID)}")
        elif args.write_evidence:
            if target_kind != "main":
                raise MigrationTransactionError(
                    "evidence regeneration is Main-only: skeleton/lite 不携带维护者"
                    "迁移证据，历史证据再生能力已在发行面退役（EV-0023）"
                )
            write_evidence(repo, target_kind, args.baseline)
            print(f"evidence={REPORT_PATH.as_posix()}")
        state = inspect_operations(repo, operation_set)
        if args.json:
            print(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2))
        else:
            print(f"target={repo}")
            print(f"pending={len(state['pending'])}")
            print(f"applied={len(state['applied'])}")
            print(f"blockers={len(state['blockers'])}")
        return 1 if state["pending"] or state["blockers"] else 0
    except (OSError, MigrationTransactionError, ValueError) as exc:
        print(f"[FAIL] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
