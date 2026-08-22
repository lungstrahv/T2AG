#!/usr/bin/env python3
"""Generate release candidate trees only inside byte-verified physical copies.

The source repository is read-only.  Git is never invoked against it during a
candidate replay; all object and index writes happen in two independent copies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION_TOKEN = "CANDIDATE_REPLAY_AUTHORIZED"
class CandidateIsolationError(RuntimeError):
    """The source or a candidate copy is not mechanically isolated."""


@dataclass(frozen=True)
class FileRecord:
    relative: str
    size: int
    sha256: str
    device: int
    file_id: int
    link_count: int
    mode: int
    mtime_ns: int

    @property
    def byte_identity(self) -> tuple[int, str]:
        return self.size, self.sha256

    @property
    def filesystem_identity(self) -> tuple[int, int]:
        return self.device, self.file_id

    @property
    def source_state(self) -> tuple[int, str, int, int]:
        return self.size, self.sha256, self.mode, self.mtime_ns


@dataclass(frozen=True)
class CandidateResult:
    file_count: int
    tree_sha: str
    whitespace_ok: bool


def sanitized_git_environment(
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Remove every inherited repository/config override before Git runs."""
    clean = dict(os.environ if base is None else base)
    for key in list(clean):
        if key.upper().startswith("GIT_"):
            clean.pop(key, None)
    clean["GIT_CONFIG_GLOBAL"] = os.devnull
    clean["GIT_CONFIG_NOSYSTEM"] = "1"
    clean["GIT_ATTR_NOSYSTEM"] = "1"
    clean["GIT_NO_LAZY_FETCH"] = "1"
    clean["GIT_NO_REPLACE_OBJECTS"] = "1"
    clean["GIT_TERMINAL_PROMPT"] = "0"
    return clean


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as exc:
        raise CandidateIsolationError(f"cannot lstat {path}: {exc}") from exc
    return bool(
        stat.S_ISLNK(info.st_mode)
        or (
            os.name == "nt"
            and getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
    )


def _assert_no_reparse_ancestors(path: Path) -> None:
    current = Path(os.path.abspath(path))
    for candidate in (current, *current.parents):
        if candidate.exists() and _is_link_or_reparse(candidate):
            raise CandidateIsolationError(
                f"path or ancestor is a link/reparse point: {candidate}"
            )


def _local_config_hazards(config: Path) -> list[str]:
    if not config.is_file():
        return ["missing .git/config"]
    section = ""
    hazards: list[str] = []
    for raw in config.read_text(
        encoding="utf-8-sig", errors="replace",
    ).splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            if section == "include" or section.startswith("includeif "):
                hazards.append(f"local config includes another file: [{section}]")
            continue
        parts = line.split("=", 1)
        key = parts[0].strip().lower()
        value = parts[1].strip().strip('"').lower() if len(parts) == 2 else "true"
        explicitly_false = value in {"false", "no", "off", "0"}
        if section == "core" and key == "worktree":
            hazards.append("local core.worktree is set")
        if section == "core" and key == "bare" and not explicitly_false:
            hazards.append("core.bare=true is forbidden")
        if section == "core" and key == "hookspath":
            hazards.append(f"core.{key} is forbidden")
        if section == "core" and key == "fsmonitor" and not explicitly_false:
            hazards.append("core.fsmonitor must be explicitly false")
        if (
            section == "core"
            and key in {"sparsecheckout", "sparsecheckoutcone"}
            and not explicitly_false
        ):
            hazards.append(f"core.{key} enables sparse checkout")
        if section == "index" and key == "sparse" and not explicitly_false:
            hazards.append("index.sparse enables a sparse index")
        if section == "extensions" and key == "worktreeconfig":
            hazards.append("extensions.worktreeConfig is set")
        if section == "extensions" and key == "partialclone":
            hazards.append("partial clone configuration is forbidden")
        if section.startswith("remote ") and key == "promisor":
            hazards.append("promisor remote is forbidden")
        if section.startswith("filter ") and key in {"clean", "process"}:
            hazards.append(f"working-tree filter is forbidden: [{section}] {key}")
    return hazards


def validate_repository_layout(root: Path) -> None:
    """Reject shared/linked Git layouts before a source or copy is trusted."""
    if not root.is_absolute():
        raise CandidateIsolationError(f"repository root must be absolute: {root}")
    _assert_no_reparse_ancestors(root)
    if not root.is_dir() or _is_link_or_reparse(root):
        raise CandidateIsolationError(f"repository root is missing or linked: {root}")
    git_dir = root / ".git"
    if not git_dir.is_dir() or _is_link_or_reparse(git_dir):
        raise CandidateIsolationError(".git must be a physical directory, not a gitfile/link")

    forbidden = (
        git_dir / "commondir",
        git_dir / "gitdir",
        git_dir / "worktrees",
        git_dir / "modules",
        git_dir / "config.worktree",
        git_dir / "objects/info/alternates",
        git_dir / "objects/info/http-alternates",
        git_dir / "info/sparse-checkout",
    )
    present = [path.relative_to(root).as_posix() for path in forbidden if path.exists()]
    if present:
        raise CandidateIsolationError(
            f"shared/external Git metadata is forbidden: {present}"
        )
    nested_git = [
        path.relative_to(root).as_posix()
        for path in root.rglob(".git")
        if path != git_dir
    ]
    if nested_git:
        raise CandidateIsolationError(f"nested gitfile/repository is forbidden: {nested_git}")
    locks = [
        path.relative_to(root).as_posix()
        for path in git_dir.rglob("*.lock")
    ]
    if locks:
        raise CandidateIsolationError(f"Git lock files are forbidden: {locks}")
    hazards = _local_config_hazards(git_dir / "config")
    if hazards:
        raise CandidateIsolationError("; ".join(hazards))


def inspect_tree(root: Path) -> dict[str, FileRecord]:
    """Hash every byte and capture filesystem IDs without following links."""
    validate_repository_layout(root)
    records: dict[str, FileRecord] = {}
    identities: dict[tuple[int, int], str] = {}
    normalized_paths: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if _is_link_or_reparse(path):
            raise CandidateIsolationError(
                f"symlink/junction/reparse point is forbidden: "
                f"{path.relative_to(root).as_posix()}"
            )
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise CandidateIsolationError(
                f"non-regular file is forbidden: {path.relative_to(root).as_posix()}"
            )
        if info.st_ino == 0:
            raise CandidateIsolationError(
                f"filesystem did not expose a usable File ID: {path}"
            )
        relative = path.relative_to(root).as_posix()
        normalized = unicodedata.normalize("NFC", relative).casefold()
        if normalized in normalized_paths:
            raise CandidateIsolationError(
                "case/Unicode-normalized path collision: "
                f"{normalized_paths[normalized]} <-> {relative}"
            )
        normalized_paths[normalized] = relative
        identity = (info.st_dev, info.st_ino)
        if info.st_nlink != 1 or identity in identities:
            other = identities.get(identity, relative)
            raise CandidateIsolationError(
                f"hardlink/shared File ID is forbidden: {other} <-> {relative}"
            )
        identities[identity] = relative
        records[relative] = FileRecord(
            relative=relative,
            size=info.st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            device=info.st_dev,
            file_id=info.st_ino,
            link_count=info.st_nlink,
            mode=stat.S_IMODE(info.st_mode),
            mtime_ns=info.st_mtime_ns,
        )
    return records


def manifest_digest(records: Mapping[str, FileRecord]) -> str:
    digest = hashlib.sha256()
    for relative, record in sorted(records.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record.size).encode("ascii"))
        digest.update(b"\0")
        digest.update(record.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def assert_byte_manifest_equal(
    expected: Mapping[str, FileRecord],
    actual: Mapping[str, FileRecord],
    label: str,
) -> None:
    expected_bytes = {
        path: record.byte_identity for path, record in expected.items()
    }
    actual_bytes = {
        path: record.byte_identity for path, record in actual.items()
    }
    if expected_bytes != actual_bytes:
        missing = sorted(set(expected_bytes) - set(actual_bytes))
        extra = sorted(set(actual_bytes) - set(expected_bytes))
        differ = sorted(
            path for path in set(expected_bytes) & set(actual_bytes)
            if expected_bytes[path] != actual_bytes[path]
        )
        raise CandidateIsolationError(
            f"{label} byte manifest mismatch: "
            f"missing={missing} extra={extra} differ={differ}"
        )


def assert_source_state_equal(
    expected: Mapping[str, FileRecord],
    actual: Mapping[str, FileRecord],
) -> None:
    before = {path: record.source_state for path, record in expected.items()}
    after = {path: record.source_state for path, record in actual.items()}
    if before != after:
        raise CandidateIsolationError(
            "source tree/HEAD/refs/index/object metadata changed during replay"
        )


def assert_file_ids_disjoint(
    *trees: tuple[str, Mapping[str, FileRecord]],
) -> None:
    owners: dict[tuple[int, int], tuple[str, str]] = {}
    for label, records in trees:
        for relative, record in records.items():
            identity = record.filesystem_identity
            if identity in owners:
                other_label, other_relative = owners[identity]
                raise CandidateIsolationError(
                    "source/candidate copies share a File ID: "
                    f"{other_label}:{other_relative} <-> {label}:{relative}"
                )
            owners[identity] = (label, relative)


def create_physical_copy(source: Path, destination: Path) -> dict[str, FileRecord]:
    if destination.exists():
        raise CandidateIsolationError(f"candidate destination already exists: {destination}")
    _assert_no_reparse_ancestors(destination.parent)
    shutil.copytree(source, destination, copy_function=shutil.copy2, symlinks=False)
    _assert_no_reparse_ancestors(destination)
    return inspect_tree(destination)


def resolve_git_executable() -> tuple[Path, str]:
    raw = shutil.which("git")
    if not raw:
        raise CandidateIsolationError("git executable not found")
    raw_path = Path(os.path.abspath(raw))
    if not raw_path.is_file() or _is_link_or_reparse(raw_path):
        raise CandidateIsolationError(f"git executable is missing or linked: {raw_path}")
    executable = raw_path.resolve(strict=True)
    if not executable.is_file():
        raise CandidateIsolationError(f"git executable is missing or linked: {executable}")
    return executable, hashlib.sha256(executable.read_bytes()).hexdigest()


def _git(
    root: Path,
    control: Path,
    executable: Path,
    env: Mapping[str, str],
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    command = [
        str(executable),
        "-c", f"safe.directory={root}",
        "-c", "core.autocrlf=true",
        "-c", "core.filemode=false",
        "-c", "core.symlinks=false",
        "-c", "core.ignorecase=true",
        "-c", f"core.excludesFile={control / 'exclude'}",
        "-c", f"core.attributesFile={control / 'attributes'}",
        "-c", f"core.hooksPath={control / 'hooks'}",
        f"--git-dir={root / '.git'}",
        f"--work-tree={root}",
        *arguments,
    ]
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=dict(env),
        cwd=control,
    )
    if result.returncode:
        raise CandidateIsolationError(
            f"candidate Git command failed: {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def replay_in_copy(root: Path, control: Path, executable: Path) -> CandidateResult:
    """Write an index and objects only below this already-verified copy."""
    validate_repository_layout(root)
    if control.exists():
        raise CandidateIsolationError(f"candidate control directory exists: {control}")
    control.mkdir(parents=True)
    (control / "hooks").mkdir()
    for name in ("global.gitconfig", "exclude", "attributes"):
        (control / name).write_text("", encoding="utf-8")
    env = sanitized_git_environment()
    env["GIT_CONFIG_GLOBAL"] = str(control / "global.gitconfig")
    env["GIT_INDEX_FILE"] = str(control / "index")
    _git(root, control, executable, env, "read-tree", "HEAD")
    _git(root, control, executable, env, "add", "-A", "--", ".")
    tree_sha = _git(root, control, executable, env, "write-tree").stdout.strip()
    if not tree_sha or len(tree_sha) != 40:
        raise CandidateIsolationError(f"invalid candidate tree SHA: {tree_sha!r}")
    files = [
        line for line in _git(
            root, control, executable, env, "ls-files", "--cached",
        ).stdout.splitlines()
        if line
    ]
    whitespace = _git(
        root, control, executable, env, "diff", "--cached", "--check",
    )
    return CandidateResult(
        file_count=len(files),
        tree_sha=tree_sha,
        whitespace_ok=whitespace.returncode == 0,
    )


def replay_candidate(source: Path, workspace: Path) -> dict[str, object]:
    """Create two independent copies, replay Git, and recheck the source."""
    source = Path(os.path.abspath(source))
    workspace = Path(os.path.abspath(workspace))
    if workspace == source or workspace in source.parents or source in workspace.parents:
        raise CandidateIsolationError("workspace and source must be disjoint trees")
    if workspace.exists() and any(workspace.iterdir()):
        raise CandidateIsolationError("candidate workspace must be empty")

    source_before = inspect_tree(source)
    git_executable, git_executable_sha = resolve_git_executable()
    workspace.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_ancestors(workspace)
    if _is_link_or_reparse(workspace):
        raise CandidateIsolationError("candidate workspace must not be linked/reparse")
    copy_one = workspace / "copy-1"
    copy_two = workspace / "copy-2"
    one_before = create_physical_copy(source, copy_one)
    two_before = create_physical_copy(source, copy_two)
    assert_byte_manifest_equal(source_before, one_before, "copy-1")
    assert_byte_manifest_equal(source_before, two_before, "copy-2")
    assert_file_ids_disjoint(
        ("source", source_before),
        ("copy-1", one_before),
        ("copy-2", two_before),
    )

    source_after_copy = inspect_tree(source)
    assert_source_state_equal(source_before, source_after_copy)
    one_worktree_before = {
        path: record
        for path, record in one_before.items()
        if not path.startswith(".git/")
    }
    two_worktree_before = {
        path: record
        for path, record in two_before.items()
        if not path.startswith(".git/")
    }
    control_root = workspace / "control"
    control_root.mkdir()
    result_one = replay_in_copy(
        copy_one, control_root / "copy-1", git_executable,
    )
    result_two = replay_in_copy(
        copy_two, control_root / "copy-2", git_executable,
    )
    if result_one != result_two:
        raise CandidateIsolationError(
            f"independent candidate results differ: {result_one} != {result_two}"
        )
    one_after = inspect_tree(copy_one)
    two_after = inspect_tree(copy_two)
    assert_byte_manifest_equal(
        one_worktree_before,
        {
            path: record
            for path, record in one_after.items()
            if not path.startswith(".git/")
        },
        "copy-1 worktree after Git replay",
    )
    assert_byte_manifest_equal(
        two_worktree_before,
        {
            path: record
            for path, record in two_after.items()
            if not path.startswith(".git/")
        },
        "copy-2 worktree after Git replay",
    )
    source_after_all_candidate_checks = inspect_tree(source)
    assert_source_state_equal(source_before, source_after_all_candidate_checks)
    return {
        "source": str(source),
        "source_manifest_sha256": manifest_digest(source_before),
        "copy_1": str(copy_one),
        "copy_2": str(copy_two),
        "file_count": result_one.file_count,
        "tree_sha": result_one.tree_sha,
        "git_executable": str(git_executable),
        "git_executable_sha256": git_executable_sha,
        "whitespace_ok": result_one.whitespace_ok,
        "source_unchanged": True,
        "file_ids_disjoint": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strictly isolated T2AG release-candidate replay.",
    )
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--authorization-token", default="")
    args = parser.parse_args()
    if args.preflight == args.generate:
        parser.error("choose exactly one of --preflight or --generate")
    try:
        if args.preflight:
            source = args.source.resolve(strict=True)
            records = inspect_tree(source)
            print(json.dumps(
                {
                    "source": str(source),
                    "files": len(records),
                    "byte_manifest_sha256": manifest_digest(records),
                    "layout": "physical_git_dir_no_links_no_shared_file_ids",
                    "candidate": "not_generated",
                },
                ensure_ascii=False,
                indent=2,
            ))
            return 0
        if args.authorization_token != AUTHORIZATION_TOKEN:
            raise CandidateIsolationError(
                "candidate generation requires the explicit authorization token"
            )
        if args.workspace is None:
            raise CandidateIsolationError("--workspace is required with --generate")
        print(json.dumps(
            replay_candidate(args.source, args.workspace),
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    except (CandidateIsolationError, OSError) as exc:
        print(f"FAIL: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
