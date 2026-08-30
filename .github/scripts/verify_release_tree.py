#!/usr/bin/env python3
"""Verify the actual public bilingual release tree.

The default mode reads a committed Git tree. It never treats an untracked empty
directory or a convenient outer workspace as proof of what GitHub ZIP/clone ships.
``--worktree`` exists only for pre-commit construction checks and is labelled as
such in its output.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EDITIONS = ("zh", "en")

REQUIRED_ROOT_FILES = frozenset(
    {
        ".gitattributes",
        ".github/scripts/test_verify_release_tree.py",
        ".github/scripts/verify_release_tree.py",
        ".github/workflows/release-structure.yml",
        ".gitignore",
        "AGENTS.md",
        "INSTALL.md",
        "LICENSE",
        "LICENSE-DOCS.md",
        "LICENSING.md",
        "NOTICE",
        "README.md",
    }
)

REQUIRED_EDITION_FILES = frozenset(
    {
        "AGENTS.md",
        "README.md",
        "LICENSE",
        "LICENSE-DOCS.md",
        "LICENSING.md",
        "NOTICE",
        "main/t2ag.md",
        "cloud/README.md",
        "cloud/T2AG_PROJECT_INSTRUCTIONS.txt",
        "cloud/cloud_sync_state.md",
        "cloud/inbox/README.md",
        "cloud/outbox/README.md",
        "main/40_course/_templates/course/_exam/exam_ledger.md.template",
        "main/40_course/_templates/course/_exam/index.md.template",
        "main/40_course/_templates/course/_exam/papers/_README.md.template",
    }
)

FORBIDDEN_EDITION_FILES = frozenset(
    {
        # Historical private grants do not ship in current public GitHub copies.
        "INVITED_USE_GRANT.md",
        # The 2026-08-21 Skeleton boundary explicitly keeps this instance ledger out.
        "main/30_group/recommendations.md",
    }
)

ROOT_AGENTS_MARKERS = (
    "Choose your language / 选择你的语言",
    "There is no default",
    "sibling target named `t2ag`",
    "language choice is not deletion authorization",
    "语言无默认值",
    "Authorization is non-amplifying",
    "stopped_budget",
    "token",
)

ROOT_INSTALL_MARKERS = (
    "Choose your language / 选择你的语言",
    "There is **no default language**",
    "named exactly `t2ag`",
    "Only after successful initialization and verification",
    "Do not delete it without explicit confirmation",
    "目标已存在即停止",
)


def _git(*args: str) -> str:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(ROOT), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def committed_tree(treeish: str) -> tuple[str, set[str]]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", treeish):
        raise ValueError(f"invalid tree name: {treeish!r}")
    tree = _git("rev-parse", "--verify", f"{treeish}^{{tree}}").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", tree):
        raise RuntimeError(f"git returned an invalid tree object: {tree!r}")
    paths = {
        line.strip().replace("\\", "/")
        for line in _git("ls-tree", "-r", "--name-only", tree).splitlines()
        if line.strip()
    }
    return tree, paths


def worktree_paths() -> set[str]:
    tracked = {
        line.strip().replace("\\", "/")
        for line in _git("ls-files", "--cached").splitlines()
        if line.strip()
    }
    deleted = {
        line.strip().replace("\\", "/")
        for line in _git("ls-files", "--deleted").splitlines()
        if line.strip()
    }
    untracked = {
        line.strip().replace("\\", "/")
        for line in _git("ls-files", "--others", "--exclude-standard").splitlines()
        if line.strip()
    }
    return (tracked - deleted) | untracked


def split_surface(paths: set[str]) -> tuple[set[str], dict[str, set[str]]]:
    editions: dict[str, set[str]] = {edition: set() for edition in EDITIONS}
    root: set[str] = set()
    for path in paths:
        matched = False
        for edition in EDITIONS:
            prefix = f"{edition}/"
            if path.startswith(prefix):
                editions[edition].add(path[len(prefix) :])
                matched = True
                break
        if not matched:
            root.add(path)
    return root, editions


def validate_paths(paths: set[str]) -> list[str]:
    findings: list[str] = []
    root, editions = split_surface(paths)

    missing_root = sorted(REQUIRED_ROOT_FILES - root)
    unexpected_root = sorted(root - REQUIRED_ROOT_FILES)
    if missing_root:
        findings.append(f"root missing required files: {missing_root}")
    if unexpected_root:
        findings.append(f"root has unregistered files: {unexpected_root}")

    for edition in EDITIONS:
        surface = editions[edition]
        missing = sorted(REQUIRED_EDITION_FILES - surface)
        forbidden = sorted(FORBIDDEN_EDITION_FILES & surface)
        if missing:
            findings.append(f"{edition} missing required files: {missing}")
        if forbidden:
            findings.append(f"{edition} contains forbidden instance files: {forbidden}")
        outbox = sorted(path for path in surface if path.startswith("cloud/outbox/"))
        if outbox != ["cloud/outbox/README.md"]:
            findings.append(
                f"{edition} Skeleton outbox must contain only its tracked README: {outbox}"
            )

    zh_only = sorted(editions["zh"] - editions["en"])
    en_only = sorted(editions["en"] - editions["zh"])
    if en_only:
        findings.append(
            "en has files absent from zh (orphans not allowed): "
            f"en_only={en_only[:20]}"
        )
    if zh_only:
        # zh 正本可先行：跨发行逐文件 parity 已裁为不可满足契约（J3, T2AC
        # closeout workorder 14.95）；EN 同步在途期间 zh 领先属常态（14.130）。
        # zh 领先的文件只记 NOTE，不构成 FAIL。
        print(f"NOTE: zh leads en by {len(zh_only)} files (allowed): {zh_only[:20]}")
    return findings


def validate_root_agents(content: str) -> list[str]:
    missing = [marker for marker in ROOT_AGENTS_MARKERS if marker not in content]
    return [f"root AGENTS.md lacks governance markers: {missing}"] if missing else []


def validate_root_install(content: str) -> list[str]:
    missing = [marker for marker in ROOT_INSTALL_MARKERS if marker not in content]
    return [f"root INSTALL.md lacks language-selection markers: {missing}"] if missing else []


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--tree", default="HEAD", help="committed Git tree to verify")
    source.add_argument(
        "--worktree",
        action="store_true",
        help="pre-commit preview only; never proves GitHub contents",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.worktree:
            identity = "WORKTREE_PREVIEW_ONLY"
            paths = worktree_paths()
            agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
            install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        else:
            identity, paths = committed_tree(args.tree)
            agents = _git("show", f"{identity}:AGENTS.md")
            install = _git("show", f"{identity}:INSTALL.md")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: unable to read release surface: {exc}", file=sys.stderr)
        return 2

    findings = (
        validate_paths(paths)
        + validate_root_agents(agents)
        + validate_root_install(install)
    )
    if findings:
        for finding in findings:
            print(f"FAIL: {finding}")
        print(f"result: {len(findings)} FAIL ({identity})")
        return 1

    _root, editions = split_surface(paths)
    print(
        "PASS: public release tree "
        f"{identity}; zh={len(editions['zh'])} files; en={len(editions['en'])} files"
    )
    if args.worktree:
        print("NOTE: worktree preview does not prove committed or GitHub contents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
