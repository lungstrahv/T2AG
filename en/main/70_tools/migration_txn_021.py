#!/usr/bin/env python3
"""Durable, recoverable file-move transaction used by 0.2.1 migrators."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class MigrationTransactionError(RuntimeError):
    pass


@dataclass(frozen=True)
class MoveOperation:
    source: str
    target: str
    transform_id: str
    transform: Callable[[bytes], bytes]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    content = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _repo_key(repo: Path) -> str:
    return hashlib.sha256(str(repo.resolve()).encode("utf-8")).hexdigest()[:24]


def transaction_root(repo: Path, migration_id: str) -> Path:
    base = Path(tempfile.gettempdir()) / "t2ag-migration-021"
    return base / _repo_key(repo) / migration_id


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _resolve_relative(repo: Path, relative: str) -> Path:
    if not relative or "\\" in relative:
        raise MigrationTransactionError(f"path must be POSIX relative: {relative}")
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise MigrationTransactionError(f"path escapes repository: {relative}")
    result = repo.joinpath(*relative.split("/"))
    current = repo
    for part in relative.split("/")[:-1]:
        current = current / part
        if current.exists() and _is_reparse(current):
            raise MigrationTransactionError(f"symlink/reparse path refused: {relative}")
    if result.exists() and _is_reparse(result):
        raise MigrationTransactionError(f"symlink/reparse path refused: {relative}")
    return result


def _git_dirty(repo: Path, paths: list[str]) -> list[str]:
    if not (repo / ".git").exists():
        return []
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", *paths],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise MigrationTransactionError(
            result.stderr.decode("utf-8", errors="replace").strip()
            or "git pathspec check failed"
        )
    return [line for line in result.stdout.decode("utf-8", errors="replace").splitlines() if line]


def _inject(point: str) -> None:
    requested = os.environ.get("T2AG_MIGRATION_FAIL_AT", "")
    if requested == point:
        raise MigrationTransactionError(f"injected failure at {point}")
    requested_kill = os.environ.get("T2AG_MIGRATION_KILL_AT", "")
    if requested_kill == point:
        os._exit(97)


def inspect_operations(repo: Path, operations: tuple[MoveOperation, ...]) -> dict[str, object]:
    pending: list[str] = []
    applied: list[str] = []
    blockers: list[str] = []
    for operation in operations:
        source = _resolve_relative(repo, operation.source)
        target = _resolve_relative(repo, operation.target)
        if source.is_file() and not target.exists():
            pending.append(operation.transform_id)
        elif not source.exists() and target.is_file():
            applied.append(operation.transform_id)
        elif source.exists() and target.exists():
            blockers.append(f"collision:{operation.source}->{operation.target}")
        else:
            blockers.append(f"missing:{operation.source}->{operation.target}")
    if pending and applied:
        blockers.append("partial-state")
    return {"pending": pending, "applied": applied, "blockers": blockers}


def _remove_empty_created_dirs(repo: Path, directories: list[str]) -> None:
    for relative in sorted(directories, key=lambda value: len(value.split("/")), reverse=True):
        path = repo.joinpath(*relative.split("/"))
        try:
            path.rmdir()
        except (FileNotFoundError, OSError):
            pass


def _rollback(repo: Path, journal: dict[str, object], txn_dir: Path) -> None:
    rows = journal.get("operations")
    if not isinstance(rows, list):
        raise MigrationTransactionError("invalid transaction journal")
    errors: list[str] = []
    for rollback_index, row in enumerate(reversed(rows), start=1):
        if not isinstance(row, dict):
            errors.append("invalid operation row")
            continue
        source_relative = str(row.get("source", ""))
        target_relative = str(row.get("target", ""))
        backup_relative = str(row.get("backup", ""))
        try:
            source = _resolve_relative(repo, source_relative)
            target = _resolve_relative(repo, target_relative)
            backup = txn_dir / backup_relative
            expected = str(row.get("source_sha256", ""))
            content = backup.read_bytes()
            if sha256_bytes(content) != expected:
                raise MigrationTransactionError(f"backup digest mismatch: {backup}")
            if source.exists() and sha256_bytes(source.read_bytes()) != expected:
                raise MigrationTransactionError(f"source changed during recovery: {source_relative}")
            if not source.exists():
                _atomic_bytes(source, content)
            _inject(f"rollback:{rollback_index}:source")
            if target.exists():
                target.unlink()
                _fsync_dir(target.parent)
            _inject(f"rollback:{rollback_index}:target")
        except (OSError, MigrationTransactionError) as exc:
            errors.append(str(exc))
    _remove_empty_created_dirs(repo, [str(item) for item in journal.get("created_dirs", [])])
    if errors:
        raise MigrationTransactionError("rollback failed: " + "; ".join(errors))


def recover(repo: Path, migration_id: str) -> str:
    repo = repo.resolve()
    txn_dir = transaction_root(repo, migration_id)
    journal_path = txn_dir / "journal.json"
    if not journal_path.is_file():
        return "nothing_to_recover"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal.get("repo") != str(repo) or journal.get("migration_id") != migration_id:
        raise MigrationTransactionError("journal binding mismatch")
    if journal.get("phase") != "committed":
        _rollback(repo, journal, txn_dir)
        result = "rolled_back"
    else:
        result = "committed_cleanup"
    shutil.rmtree(txn_dir)
    return result


def apply_transaction(
    repo: Path,
    migration_id: str,
    operations: tuple[MoveOperation, ...],
) -> int:
    repo = repo.resolve()
    txn_dir = transaction_root(repo, migration_id)
    journal_path = txn_dir / "journal.json"
    if journal_path.exists():
        raise MigrationTransactionError("unfinished transaction exists; run --recover")
    state = inspect_operations(repo, operations)
    if state["blockers"]:
        raise MigrationTransactionError(f"migration preflight blockers: {state['blockers']}")
    if not state["pending"]:
        return 0
    pathspec = [item for operation in operations for item in (operation.source, operation.target)]
    dirty = _git_dirty(repo, pathspec)
    if dirty:
        raise MigrationTransactionError(f"migration pathspec is dirty: {dirty}")

    txn_dir.mkdir(parents=True, exist_ok=False)
    backup_dir = txn_dir / "backup"
    backup_dir.mkdir()
    created_dirs: list[str] = []
    rows: list[dict[str, object]] = []
    try:
        for index, operation in enumerate(operations, start=1):
            source = _resolve_relative(repo, operation.source)
            source_bytes = source.read_bytes()
            transformed = operation.transform(source_bytes)
            backup = backup_dir / f"{index:04d}.bin"
            with backup.open("xb") as handle:
                handle.write(source_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            rows.append({
                "sequence": index,
                "transform_id": operation.transform_id,
                "source": operation.source,
                "target": operation.target,
                "backup": f"backup/{backup.name}",
                "source_sha256": sha256_bytes(source_bytes),
                "target_sha256": sha256_bytes(transformed),
                "installed": False,
                "source_retired": False,
            })
        journal: dict[str, object] = {
            "schema": "T2AG-MIGRATION-TXN-1",
            "migration_id": migration_id,
            "repo": str(repo),
            "phase": "prepared",
            "created_dirs": created_dirs,
            "operations": rows,
        }
        _atomic_json(journal_path, journal)
        _inject("prepared")
        journal["phase"] = "installing"
        _atomic_json(journal_path, journal)
        for index, (operation, row) in enumerate(zip(operations, rows), start=1):
            target = _resolve_relative(repo, operation.target)
            missing: list[Path] = []
            current = target.parent
            while current != repo and not current.exists():
                missing.append(current)
                current = current.parent
            for directory in reversed(missing):
                directory.mkdir()
                created_dirs.append(directory.relative_to(repo).as_posix())
            source_bytes = (txn_dir / str(row["backup"])).read_bytes()
            _atomic_bytes(target, operation.transform(source_bytes))
            row["installed"] = True
            _atomic_json(journal_path, journal)
            _inject(f"install:{index}")
        journal["phase"] = "retiring"
        _atomic_json(journal_path, journal)
        for index, (operation, row) in enumerate(zip(operations, rows), start=1):
            source = _resolve_relative(repo, operation.source)
            source.unlink()
            _fsync_dir(source.parent)
            row["source_retired"] = True
            _atomic_json(journal_path, journal)
            _inject(f"retire:{index}")
        journal["phase"] = "committed"
        _atomic_json(journal_path, journal)
        _inject("committed")
        shutil.rmtree(txn_dir)
        return len(operations)
    except BaseException:
        if journal_path.is_file():
            try:
                active = json.loads(journal_path.read_text(encoding="utf-8"))
                _rollback(repo, active, txn_dir)
                shutil.rmtree(txn_dir)
            except Exception as rollback_error:
                raise MigrationTransactionError(
                    f"apply failed and rollback failed; run --recover: {rollback_error}"
                )
        else:
            shutil.rmtree(txn_dir, ignore_errors=True)
        raise
