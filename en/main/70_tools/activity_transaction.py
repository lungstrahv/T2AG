#!/usr/bin/env python3
"""Root-scoped multi-file activity transaction engine for T2AG 0.2.2.

Guarantees:
- relative paths must stay under root (no .. / absolute / reparse escape)
- write/delete/move stage with durable backup before mutation
- move backs up source so rollback restores source and removes target
- same transaction_id requires identical plan fingerprint
- default check/plan; apply installs with readback
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class TransactionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_tree(path: Path) -> str | None:
    """Aggregate hash of a file or directory tree (path-stable)."""
    if not path.exists():
        return None
    if path.is_file():
        return sha256_file(path)
    items: list[tuple[str, str]] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        rel = child.relative_to(path).as_posix()
        items.append((rel, sha256_file(child) or ""))
    h = hashlib.sha256()
    for rel, digest in items:
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(digest.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def canonical_plan_bytes(plan: dict[str, Any]) -> bytes:
    return (
        json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def plan_fingerprint(plan: dict[str, Any]) -> str:
    body = {k: v for k, v in plan.items() if k != "status"}
    return sha256_bytes(canonical_plan_bytes(body))


@dataclass
class FileOp:
    relative_path: str
    kind: str  # write | delete | move
    content: bytes | None = None
    source_relative: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "kind": self.kind,
            "source_relative": self.source_relative,
            "content_sha256": (
                sha256_bytes(self.content) if self.content is not None else None
            ),
            "content_b64": None,  # filled only in durable plan if needed externally
        }


@dataclass
class TransactionPlan:
    scope_id: str
    transaction_id: str
    ops: list[FileOp] = field(default_factory=list)
    expected_head: dict[str, str | None] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "transaction_id": self.transaction_id,
            "expected_head": self.expected_head,
            "ops": [
                {
                    "relative_path": op.relative_path,
                    "kind": op.kind,
                    "source_relative": op.source_relative,
                    "content_sha256": (
                        sha256_bytes(op.content) if op.content is not None else None
                    ),
                }
                for op in self.ops
            ],
            "metadata": self.metadata,
        }


class ActivityTransaction:
    def __init__(self, root: Path, recovery_root: Path | None = None):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise TransactionError(f"root is not a directory: {self.root}")
        self.recovery_root = (
            recovery_root.resolve()
            if recovery_root
            else self.root / ".activity_txn"
        )
        self.lock_path = self.recovery_root / "scope.lock"
        self.owner_nonce = uuid.uuid4().hex

    @staticmethod
    def _pid_start_identity(pid: int) -> str | None:
        """Return an OS process-start identity so PID reuse is not "alive"."""
        if not isinstance(pid, int) or pid <= 0:
            return None
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenProcess.restype = wintypes.HANDLE
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if not handle:
                    return None
                try:
                    creation = wintypes.FILETIME()
                    exit_time = wintypes.FILETIME()
                    kernel = wintypes.FILETIME()
                    user = wintypes.FILETIME()
                    if not kernel32.GetProcessTimes(
                        handle,
                        ctypes.byref(creation),
                        ctypes.byref(exit_time),
                        ctypes.byref(kernel),
                        ctypes.byref(user),
                    ):
                        return None
                    value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
                    return f"windows-filetime:{value}"
                finally:
                    kernel32.CloseHandle(handle)
            stat_path = Path(f"/proc/{pid}/stat")
            if stat_path.is_file():
                fields = stat_path.read_text(encoding="utf-8").split()
                return f"proc-start:{fields[21]}"
        except (OSError, ValueError, IndexError):
            return None
        return None

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.t2ag-{uuid.uuid4().hex}.tmp")
        try:
            with tmp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()

    @classmethod
    def _atomic_write_json(cls, path: Path, payload: dict[str, Any]) -> None:
        cls._atomic_write_bytes(
            path,
            (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )

    @staticmethod
    def _hard_exit_if_requested(point: str) -> None:
        """Test-only external crash hook; never raises into rollback code."""
        if os.environ.get("T2AG_TXN_HARD_EXIT_AT") == point:
            try:
                import sys

                sys.stdout.flush()
                sys.stderr.flush()
            finally:
                os._exit(97)

    @staticmethod
    def _raise_if_requested(point: str, fail_at: str | None) -> None:
        if fail_at == point:
            raise TransactionError(f"injected failure at {point}")

    def _atomic_install_write(
        self,
        target: Path,
        data: bytes,
        *,
        transaction_id: str,
        operation_index: int,
        fail_at: str | None = None,
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(
            f".{target.name}.t2ag-{transaction_id}-{operation_index:04d}.tmp"
        )
        if tmp.exists():
            raise TransactionError(f"stale install temp exists: {tmp.name}")
        try:
            with tmp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            self._hard_exit_if_requested(
                f"write_after_temp_fsync:{operation_index}"
            )
            self._raise_if_requested(
                f"write_after_temp_fsync:{operation_index}", fail_at
            )
            self._hard_exit_if_requested(f"write_before_replace:{operation_index}")
            self._raise_if_requested(f"write_before_replace:{operation_index}", fail_at)
            os.replace(tmp, target)
            self._hard_exit_if_requested(f"write_after_replace:{operation_index}")
            self._raise_if_requested(f"write_after_replace:{operation_index}", fail_at)
        finally:
            if tmp.exists():
                tmp.unlink()

    def _is_reparse(self, path: Path) -> bool:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        return bool(
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ) or path.is_symlink()

    def resolve_inside(self, relative: str) -> Path:
        if not relative or relative.startswith("/") or relative.startswith("\\"):
            raise TransactionError(f"absolute path refused: {relative}")
        if "\\" in relative:
            raise TransactionError(f"use posix relative paths only: {relative}")
        parts = Path(relative).parts
        if any(part in {"", ".", ".."} for part in parts) or ".." in relative:
            raise TransactionError(f"path escapes root: {relative}")
        candidate = (self.root / relative).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise TransactionError(f"path escapes root: {relative}") from exc
        # refuse reparse on any prefix
        cursor = self.root
        for part in Path(relative).parts:
            cursor = cursor / part
            if cursor.exists() and self._is_reparse(cursor):
                raise TransactionError(f"reparse/symlink refused: {relative}")
        return candidate

    def _lock_payload(self) -> dict[str, Any]:
        if not self.lock_path.is_file():
            return {}
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransactionError(f"corrupt scope lock: {self.lock_path}") from exc
        if not isinstance(payload, dict):
            raise TransactionError("corrupt scope lock: root JSON is not an object")
        return payload

    def _new_lock_payload(self, transaction_id: str, status: str) -> dict[str, Any]:
        return {
            "transaction_id": transaction_id,
            "status": status,
            "owner_nonce": self.owner_nonce,
            "pid": os.getpid(),
            "pid_start_identity": self._pid_start_identity(os.getpid()),
            "created_at": time.time(),
        }

    def _write_lock_exclusive(self, payload: dict[str, Any]) -> None:
        data = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with self.lock_path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    def acquire_lock(self, transaction_id: str) -> None:
        self.recovery_root.mkdir(parents=True, exist_ok=True)
        for _attempt in range(4):
            if not self.lock_path.exists():
                try:
                    self._write_lock_exclusive(
                        self._new_lock_payload(transaction_id, "running")
                    )
                    return
                except FileExistsError:
                    continue
            payload = self._lock_payload()
            same_owner = (
                payload.get("owner_nonce") == self.owner_nonce
                and payload.get("pid") == os.getpid()
                and payload.get("pid_start_identity")
                == self._pid_start_identity(os.getpid())
            )
            if payload.get("transaction_id") == transaction_id and same_owner:
                if payload.get("status") in {"running", "staged", "committed"}:
                    return
            if payload.get("status") == "committed":
                # allow new txn after committed lock left behind
                if payload.get("transaction_id") == transaction_id:
                    return
            reclaim_committed = payload.get("status") == "committed"
            pid = payload.get("pid")
            actual_identity = (
                self._pid_start_identity(pid) if isinstance(pid, int) else None
            )
            stored_identity = payload.get("pid_start_identity")
            alive_same_process = bool(
                not reclaim_committed
                and
                actual_identity
                and stored_identity
                and actual_identity == stored_identity
            )
            if alive_same_process:
                raise TransactionError(
                    f"scope lock held by {payload.get('transaction_id')} "
                    f"status={payload.get('status')} pid={pid}"
                )
            # Dead owner or reused PID: preserve evidence before takeover.
            evidence = self.recovery_root / f"stale-lock-{uuid.uuid4().hex}.json"
            self._atomic_write_json(
                evidence,
                {
                    **payload,
                    "takeover_transaction_id": transaction_id,
                    "observed_pid_start_identity": actual_identity,
                    "preserved_at": time.time(),
                },
            )
            self.lock_path.unlink(missing_ok=True)
        raise TransactionError("concurrent scope-lock acquisition did not converge")

    def release_lock(self, transaction_id: str, *, force: bool = False) -> None:
        if not self.lock_path.exists():
            return
        payload = self._lock_payload()
        if not force and (
            payload.get("transaction_id") not in {None, transaction_id}
            or payload.get("owner_nonce") != self.owner_nonce
        ):
            raise TransactionError("cannot release foreign lock or wrong owner nonce")
        self.lock_path.unlink(missing_ok=True)

    def current_head(self, relative_paths: list[str]) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        for rel in relative_paths:
            path = self.resolve_inside(rel)
            if path.is_dir():
                result[rel] = sha256_tree(path)
            else:
                result[rel] = sha256_file(path)
        return result

    def check_head(self, expected: dict[str, str | None]) -> None:
        actual = self.current_head(list(expected))
        for rel, want in expected.items():
            got = actual.get(rel)
            if got != want:
                raise TransactionError(
                    f"baseline conflict on {rel}: expected={want} actual={got}"
                )

    def plan_dir(self, transaction_id: str) -> Path:
        if not transaction_id or "/" in transaction_id or "\\" in transaction_id:
            raise TransactionError(f"bad transaction_id: {transaction_id}")
        return self.recovery_root / transaction_id

    def _copy_any(self, source: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)

    def stage(self, plan: TransactionPlan) -> Path:
        # validate all paths first
        for op in plan.ops:
            self.resolve_inside(op.relative_path)
            if op.source_relative:
                self.resolve_inside(op.source_relative)
        self.acquire_lock(plan.transaction_id)
        try:
            self.check_head(plan.expected_head)
        except TransactionError:
            self.release_lock(plan.transaction_id)
            raise
        root = self.plan_dir(plan.transaction_id)
        manifest = plan.to_manifest()
        fingerprint = plan_fingerprint(manifest)
        if root.exists():
            existing = root / "plan.json"
            if existing.is_file():
                old = json.loads(existing.read_text(encoding="utf-8"))
                old_fp = plan_fingerprint(old)
                if (
                    old.get("transaction_id") == plan.transaction_id
                    and old_fp == fingerprint
                ):
                    return root
                raise TransactionError(
                    "transaction_id reuse with different plan fingerprint: "
                    f"{old_fp} != {fingerprint}"
                )
            raise TransactionError(f"transaction dir already exists: {root}")
        staging = root / "staging"
        backup = root / "backup"
        staging.mkdir(parents=True)
        backup.mkdir(parents=True)
        for op in plan.ops:
            target = self.resolve_inside(op.relative_path)
            if target.exists():
                self._copy_any(target, backup / op.relative_path)
            staged = staging / op.relative_path
            if op.kind == "write":
                if op.content is None:
                    raise TransactionError(f"write op missing content: {op.relative_path}")
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(op.content)
            elif op.kind == "delete":
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_text("__DELETE__\n", encoding="utf-8")
            elif op.kind == "move":
                if not op.source_relative:
                    raise TransactionError("move requires source_relative")
                source = self.resolve_inside(op.source_relative)
                if not source.exists():
                    raise TransactionError(f"move source missing: {op.source_relative}")
                # backup source always; backup pre-existing target so rollback restores both
                self._copy_any(source, backup / op.source_relative)
                if target.exists():
                    self._copy_any(target, backup / op.relative_path)
                self._copy_any(source, staged)
            else:
                raise TransactionError(f"unknown op kind: {op.kind}")
        durable = {
            **manifest,
            "status": "staged",
            "plan_fingerprint": fingerprint,
        }
        (root / "plan.json").write_text(
            json.dumps(durable, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        # store write payloads beside plan for recoverability
        payloads = root / "payloads"
        payloads.mkdir(exist_ok=True)
        for index, op in enumerate(plan.ops):
            if op.kind == "write" and op.content is not None:
                (payloads / f"{index:04d}.bin").write_bytes(op.content)
        self._atomic_write_json(
            self.lock_path,
            {
                **self._new_lock_payload(plan.transaction_id, "staged"),
                "scope_id": plan.scope_id,
                "campaign_id": plan.metadata.get("campaign_id"),
                "plan_fingerprint": fingerprint,
            },
        )
        return root

    def apply(
        self,
        transaction_id: str,
        *,
        fail_at: str | None = None,
        defer_commit: bool = False,
    ) -> dict[str, Any]:
        root = self.plan_dir(transaction_id)
        plan_path = root / "plan.json"
        if not plan_path.is_file():
            raise TransactionError(f"missing plan: {plan_path}")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("status") == "committed":
            # verify live post-state before claiming already committed
            for op in plan.get("ops") or []:
                if op.get("kind") == "write":
                    got = sha256_file(self.resolve_inside(op["relative_path"]))
                    want = op.get("content_sha256")
                    if got != want:
                        raise TransactionError(
                            f"already_committed post-state drift: {op['relative_path']}"
                        )
                if op.get("kind") == "move":
                    if not self.resolve_inside(op["relative_path"]).exists():
                        raise TransactionError(
                            f"already_committed missing target: {op['relative_path']}"
                        )
                    if self.resolve_inside(op["source_relative"]).exists():
                        raise TransactionError(
                            f"already_committed source still present: {op['source_relative']}"
                        )
            return {
                "status": "already_committed_verified",
                "transaction_id": transaction_id,
            }
        if plan.get("status") in {"installed_pending_postcheck", "postcheck_passed"}:
            return {
                "status": plan["status"],
                "transaction_id": transaction_id,
                "requires_postcheck": True,
            }
        self.acquire_lock(transaction_id)
        self.check_head(plan.get("expected_head") or {})
        staging = root / "staging"
        payloads = root / "payloads"
        installed: list[str] = []
        try:
            plan["status"] = "installing"
            plan["installed_ops"] = []
            self._atomic_write_json(plan_path, plan)
            for index, op in enumerate(plan["ops"], start=1):
                self._hard_exit_if_requested(f"before_install:{index}")
                self._raise_if_requested(f"before_install:{index}", fail_at)
                rel = op["relative_path"]
                kind = op["kind"]
                target = self.resolve_inside(rel)
                staged = staging / rel
                if kind == "write":
                    payload_file = payloads / f"{index-1:04d}.bin"
                    if payload_file.is_file():
                        data = payload_file.read_bytes()
                    elif staged.is_file():
                        data = staged.read_bytes()
                    else:
                        raise TransactionError(f"missing staged write payload: {rel}")
                    self._atomic_install_write(
                        target,
                        data,
                        transaction_id=transaction_id,
                        operation_index=index,
                        fail_at=fail_at,
                    )
                elif kind == "delete":
                    if target.is_dir():
                        shutil.rmtree(target)
                    elif target.exists():
                        target.unlink()
                elif kind == "move":
                    source = self.resolve_inside(op["source_relative"])
                    if not source.exists():
                        raise TransactionError(
                            f"move source missing at apply: {op['source_relative']}"
                        )
                    if target.exists():
                        # replace only after target was backed up at stage
                        self._hard_exit_if_requested(
                            f"move_before_target_remove:{index}"
                        )
                        self._raise_if_requested(
                            f"move_before_target_remove:{index}", fail_at
                        )
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self._hard_exit_if_requested(f"move_before_rename:{index}")
                    self._raise_if_requested(f"move_before_rename:{index}", fail_at)
                    shutil.move(str(source), str(target))
                    self._hard_exit_if_requested(f"move_after_rename:{index}")
                    self._raise_if_requested(f"move_after_rename:{index}", fail_at)
                else:
                    raise TransactionError(f"unknown op kind: {kind}")
                installed.append(rel)
                plan["installed_ops"] = list(installed)
                self._hard_exit_if_requested(f"before_journal:{index}")
                self._raise_if_requested(f"before_journal:{index}", fail_at)
                self._atomic_write_json(plan_path, plan)
                self._hard_exit_if_requested(f"after_journal:{index}")
                self._raise_if_requested(f"after_journal:{index}", fail_at)
                self._raise_if_requested(f"after_install:{index}", fail_at)
                self._hard_exit_if_requested(f"after_install:{index}")
            # read-back
            for index, op in enumerate(plan["ops"]):
                if op["kind"] == "write":
                    got = sha256_file(self.resolve_inside(op["relative_path"]))
                    want = op.get("content_sha256")
                    if got != want:
                        raise TransactionError(
                            f"readback mismatch {op['relative_path']}: {got} != {want}"
                        )
                if op["kind"] == "move":
                    target = self.resolve_inside(op["relative_path"])
                    source = self.resolve_inside(op["source_relative"])
                    if not target.exists():
                        raise TransactionError(f"move readback missing target: {op['relative_path']}")
                    if source.exists():
                        raise TransactionError(
                            f"move readback source still present: {op['source_relative']}"
                        )
            plan["status"] = (
                "installed_pending_postcheck" if defer_commit else "committed"
            )
            self._hard_exit_if_requested("before_installed_state")
            self._raise_if_requested("before_installed_state", fail_at)
            self._atomic_write_json(plan_path, plan)
            self._hard_exit_if_requested("after_installed_state")
            self._raise_if_requested("after_installed_state", fail_at)
            self._atomic_write_json(
                self.lock_path,
                {
                    **self._new_lock_payload(transaction_id, plan["status"]),
                    "plan_fingerprint": plan.get("plan_fingerprint"),
                },
            )
            return {
                "status": plan["status"],
                "transaction_id": transaction_id,
                "installed": installed,
            }
        except Exception as exc:
            self.rollback(transaction_id)
            raise TransactionError(f"apply failed and rolled back: {exc}") from exc

    def mark_postcheck_passed(self, transaction_id: str) -> dict[str, Any]:
        root = self.plan_dir(transaction_id)
        plan_path = root / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("status") != "installed_pending_postcheck":
            raise TransactionError(
                f"cannot pass postcheck from status={plan.get('status')}"
            )
        plan["status"] = "postcheck_passed"
        self._atomic_write_json(plan_path, plan)
        return {"status": "postcheck_passed", "transaction_id": transaction_id}

    def commit(
        self, transaction_id: str, *, fail_at: str | None = None
    ) -> dict[str, Any]:
        root = self.plan_dir(transaction_id)
        plan_path = root / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("status") == "committed":
            return self.apply(transaction_id)
        if plan.get("status") != "postcheck_passed":
            raise TransactionError(f"cannot commit from status={plan.get('status')}")
        plan["status"] = "committed"
        self._hard_exit_if_requested("before_committed_marker")
        self._raise_if_requested("before_committed_marker", fail_at)
        self._atomic_write_json(plan_path, plan)
        self._hard_exit_if_requested("after_committed_marker")
        self._atomic_write_json(
            self.lock_path,
            {
                **self._new_lock_payload(transaction_id, "committed"),
                "plan_fingerprint": plan.get("plan_fingerprint"),
            },
        )
        return {"status": "committed", "transaction_id": transaction_id}

    def rollback(self, transaction_id: str) -> None:
        root = self.plan_dir(transaction_id)
        plan_path = root / "plan.json"
        if not plan_path.is_file():
            return
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        backup = root / "backup"
        for reverse_index, op in reversed(list(enumerate(plan.get("ops") or [], start=1))):
            rel = op["relative_path"]
            target = self.resolve_inside(rel)
            kind = op.get("kind")
            if kind == "write":
                install_tmp = target.with_name(
                    f".{target.name}.t2ag-{transaction_id}-{reverse_index:04d}.tmp"
                )
                install_tmp.unlink(missing_ok=True)
            if kind == "move":
                source_rel = op["source_relative"]
                source = self.resolve_inside(source_rel)
                source_backup = backup / source_rel
                target_backup = backup / rel
                # remove current target
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                # restore pre-existing target if any
                if target_backup.exists():
                    self._copy_any(target_backup, target)
                # restore source from backup
                if source_backup.exists() and not source.exists():
                    self._copy_any(source_backup, source)
                continue
            backed = backup / rel
            if backed.exists():
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                self._copy_any(backed, target)
            else:
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
        plan["status"] = "rolled_back"
        self._atomic_write_json(plan_path, plan)
        self.release_lock(transaction_id, force=True)


def new_transaction_id(prefix: str = "TXN") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def recover(
    engine: ActivityTransaction,
    transaction_id: str,
    *,
    mode: str,
) -> dict[str, Any]:
    """Explicit recover: resume apply or rollback based on durable plan status."""
    root = engine.plan_dir(transaction_id)
    plan_path = root / "plan.json"
    if not plan_path.is_file():
        raise TransactionError(f"no recovery plan for {transaction_id}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    status = plan.get("status")
    if mode == "status":
        return {
            "transaction_id": transaction_id,
            "status": status,
            "plan_fingerprint": plan.get("plan_fingerprint"),
            "ops": len(plan.get("ops") or []),
        }
    if mode == "rollback":
        engine.rollback(transaction_id)
        return {"status": "rolled_back", "transaction_id": transaction_id}
    if mode == "resume":
        if status == "committed":
            return engine.apply(transaction_id)
        if status in {"installed_pending_postcheck", "postcheck_passed"}:
            return {
                "status": status,
                "transaction_id": transaction_id,
                "requires_postcheck": True,
            }
        if status in {"staged", "rolling_back", "rolled_back"}:
            return engine.apply(transaction_id)
        raise TransactionError(f"cannot resume from status={status}")
    raise TransactionError(f"unknown recover mode: {mode}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--transaction-id", default=None)
    parser.add_argument("--check-lock", action="store_true")
    parser.add_argument(
        "--recover",
        choices=["status", "resume", "rollback"],
        default=None,
        help="explicit recovery action for a durable transaction",
    )
    args = parser.parse_args(argv)
    engine = ActivityTransaction(args.root)
    if args.check_lock:
        print(json.dumps(engine._lock_payload(), ensure_ascii=False))
        return 0
    if args.recover:
        if not args.transaction_id:
            print(json.dumps({"ok": False, "error": "--transaction-id required"}))
            return 2
        try:
            result = recover(engine, args.transaction_id, mode=args.recover)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    print(
        json.dumps(
            {
                "root": str(engine.root),
                "transaction_id": args.transaction_id or new_transaction_id(),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
