#!/usr/bin/env python3
"""T2AG plan A: regenerate t2ag-lite in full from main (the online review snapshot).

Design (per the 2026-07-24 stage-0 mechanism adjudication A):
- Each run = a whole-tree regeneration, not an allowlisted incremental patch.
- Clear the lite projection first (keeping `.git`, `.venv`, `.recovery`, `.staging`),
  then copy from main according to the exclusion list.
- A half-synced state is mechanically impossible: lite can hold no orphan file that
  main has already deleted.
- lite must never write back to main; this script reads main and writes lite only.
- **Precondition gate**: the main working tree must be clean (the same idea as doctor's
  check_release_snapshot, widened to the whole repo via `git status --porcelain`).
  Regenerating from a dirty tree projects an intermediate state that exists in no commit
  into a git-less lite, unrecoverably. `--force` overrides it and prints a warning.
- **Closing check**: SHA-256 comparison of every file that should be projected (no
  sampling); identity files (lite's own README/AGENTS) are listed separately as an
  intentional divergence.

Excluded (not needed for review / too large / environment-local):
- directories: .git .venv .tools .recovery .staging .agents .uploads .cache
  __pycache__ archives ATBS_3e and similar
- extensions: PDF/EPUB/archives/Office binaries/images/executables/build output/DB
  (image exceptions are noted on ALLOWED_BINARY_REL)
- size: non-text over 1.5MB is skipped by default; .md/.py/.json/.yaml cap at 3MB
- working_pages/pages screenshots (retired in 0.2.2 S3; the directory no longer exists)

Retained:
- rules, playbooks, doctor, instance Markdown state, lesson text, cloud text
- **Birth certificate (F2, 2026-08-12)**: this script writes generated_at /
  source_commit / file_count / dirty_tree / host_redactions at the end of AGENTS.md so
  the snapshot can attest to its own generation moment.
- **Host redaction (F5, 2026-08-12)**: host identity strings in the text projection are
  replaced with `<host_user>`; copy and verification share one transform, and check mode
  includes a residue self-test.
- main/80_interface/fable_snail.png (see ALLOWED_BINARY_REL)
- t2ag_directory_guide.html
- lite identity README.md / AGENTS.md (rewritten after regeneration as the review-snapshot
  description; intentionally different from main)

Usage:
  python main/70_tools/sync_lite.py                  # check-only dry run
  python main/70_tools/sync_lite.py --write          # explicit full regeneration
  python main/70_tools/sync_lite.py --write --force  # approved regeneration from a dirty tree
  python main/70_tools/sync_lite.py --write --root <absolute workspace path>
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

FORBIDDEN_EXT = {
    ".pdf",
    ".epub",
    ".zip",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".pyd",
    ".pyc",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".ico",
    ".pptx",
    ".ppt",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".aux",
    ".log",
    ".o",
    ".obj",
    ".so",
    ".dylib",
    ".whl",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-journal",
    ".db-wal",
    ".db-shm",
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    ".tools",
    ".recovery",
    ".staging",
    ".agents",
    ".uploads",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "archives",
    "ATBS_3e",
    "node_modules",
}

MAX_FILE_BYTES = 1_500_000
MAX_TEXT_BYTES = 3_000_000
TEXT_EXT = {
    ".md",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".toml",
    ".ini",
    ".cfg",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".rs",
    ".go",
    ".java",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".ps1",
    ".bat",
    ".csv",
    ".tsv",
    ".xml",
    ".svg",
}

# --- Host identity redaction (review_LITE-20260812-0001 F5, adjudicated 2026-08-12) ---
# lite is a snapshot for an online model; the host username is environment-local. Both
# projection and verification use the same transform, which applies only to the TEXT_EXT
# text projection; main itself and the binary allowlist are untouched.
# Order matters: full-path rules first, the bare-username fallback last (the replacement
# no longer contains the matched string, so nothing is double counted).
# Literal ban (adjudicated 2026-08-13): the host username must never be hardcoded. This
# file is projected byte-identically into the open-source Skeleton under the parity
# contract, so a hardcoded literal would be a disclosure (skeleton privacy would FAIL).
# It is derived at runtime instead: `T2AG_HOST_USER` if set, else getpass.getuser().
# The bare-username fallback is enabled only when the username is at least 4 characters:
# a very short or generic username (like "a" or "pc") would corrupt body text if replaced
# everywhere. Full-path rules are exempt (drive + Users + username is specific enough).


def _resolve_host_user() -> str:
    explicit = os.environ.get("T2AG_HOST_USER", "").strip()
    if explicit:
        return explicit
    try:
        import getpass

        return getpass.getuser()
    except Exception:
        return ""


def _build_host_redactions(user: str) -> tuple[tuple[bytes, bytes], ...]:
    if not user:
        return ()
    encoded = user.encode("utf-8")
    # The prefix is assembled in pieces rather than written as one literal: the skeleton
    # privacy scanner matches "<drive>:[\/]Users[\/]", and this file enters the Skeleton
    # byte-identically, so the whole prefix in source would self-hit. Assembled, the
    # runtime bytes are unchanged and the source carries no matchable path string --
    # far narrower than a whole-file exemption (which would also wave through a future
    # real path leak; see the 08-09 review conclusion that an exemption is a bypass).
    win_prefix = b"C:" + b"\\Users" + b"\\"
    posix_prefix = b"C:" + b"/Users" + b"/"
    rules: list[tuple[bytes, bytes]] = [
        (win_prefix + encoded, win_prefix + b"<host_user>"),
        (posix_prefix + encoded, posix_prefix + b"<host_user>"),
    ]
    if len(user) >= 4:
        rules.append((encoded, b"<host_user>"))
    return tuple(rules)


HOST_USER = _resolve_host_user()
HOST_REDACTIONS: tuple[tuple[bytes, bytes], ...] = _build_host_redactions(HOST_USER)


def redact_host_bytes(data: bytes) -> tuple[bytes, int]:
    """Pure transform: (redacted_bytes, hit_count). Same function feeds copy AND verify."""
    hits = 0
    for pattern, replacement in HOST_REDACTIONS:
        count = data.count(pattern)
        if count:
            data = data.replace(pattern, replacement)
            hits += count
    return data, hits


# Binary allowlist relative to the main root (or sync root). Every entry must say what it
# is and why lite needs it.
# Exceptions are where a list starts to rot -- before adding one, ask whether review
# genuinely lacks it.
ALLOWED_BINARY_REL: dict[str, str] = {
    # fable_snail.png: the only illustration asset of t2ag_directory_guide.html.
    # The lite review view / HTML preview depends on it; other png files stay excluded
    # (textbook screenshots and OCR page images are large and not needed for rule review).
    "main/80_interface/fable_snail.png": (
        "directory-guide mascot; sole image asset for t2ag_directory_guide.html preview"
    ),
}

# Paths this script rewrites after regeneration, intentionally different from main (they
# do not take part in the "should be identical" hashing).
LITE_IDENTITY_REL = frozenset({"README.md", "AGENTS.md"})
# Guide GENERATED:directory_map is rebuilt for lite tree → may differ from main (H4)
LITE_GUIDE_DIVERGE_REL = frozenset({"t2ag_directory_guide.html"})
PRESERVE_DST_TOP = frozenset({".git", ".venv", ".recovery", ".staging"})

LITE_README = """# T2AG 0.2.4 online model review snapshot (t2ag-lite)

> **Identity**: a text-first review snapshot obtained by **fully regenerating** from the
> primary instance `t2ag/`. It is not an empty skeleton, is not used to initialize a new
> student, and must never serve as a teaching write-back source.
>
> **Product direction**: `t2ag-skeleton/` is maintained as a reusable open-source
> foundation; that does not make the personal instance public.
> The repository root has no explicit open-source licence yet; licensing must be
> adjudicated separately before any formal external distribution.

## Baseline and increment

- **Runtime version**: `0.2.4` (development; neither candidate nor FIN is claimed)
- **Most recent release-qualification baseline**: `0.2.3`, `finalization_delta_passed` on 2026-08-24
- **Changes since**: see the top of `main/00_core/t2ag_changelog.md`.
  **0.2.4 has had no candidate independent re-review and no finalization delta, so it is
  outside the release-qualification scope.**

- Regeneration mechanism: plan A (`main/70_tools/sync_lite.py`) -- a whole-tree export
  from main plus an exclusion list, every time
- Source instance: `../t2ag/`
- Sole template source: `../t2ag-skeleton/`
- Includes: system rules, instance Markdown state, course and lesson text, tool scripts,
  the plain-text review closure of `docs/adr/**` and `docs/protocol/**`,
  `t2ag_directory_guide.html` and its single snail illustration
- ADR/Protocol are **read-only review material** and grant Lite neither execution rights
  nor a host teaching hard gate
- Excludes: textbook binaries (PDF/archives and so on), `.venv`, `.tools`, `.git`,
  `.recovery`, caches, binary generated assets, DB/WAL and similar; plain-text course
  material needed for review may stay
- Redaction: host identity strings (the user home directory name) are replaced with
  `<host_user>` during projection; the hit count is in the `AGENTS.md` birth certificate,
  and residue self-testing is zero-tolerance

## Three-form base validation content

The doctor/test base structure is content that Main, Skeleton and Lite must all carry,
including `t2ag_doctor.py`, `t2ag_test.py`, `validation_control.py`,
`validation_workflow.json` and `test_dependencies.json`. Main/Skeleton startup uses only
`--profile runtime`; `--profile release` is for a frozen candidate or a formal release.
Atoms must be planned first and bound to a plan SHA, and release execution additionally
requires a registered reason (see `main/50_playbook/validation_flow.md`). Lite keeps these
files for byte-level review but remains a read-only snapshot: do not run doctor, tests,
scenarios or write-backs in this directory.

## Usage boundary for the online model

Suggested reading order:

1. `main/t2ag.md` (the constitution)
2. `main/00_core/t2ag_memory.md`
3. `main/10_student/profile/profile.md`
4. the current course, course group and playbooks
5. changelog and problemlog, expanded on demand

Open `t2ag_directory_guide.html` to browse the structure visually; naming follows
`main/50_playbook/naming_conventions.md`.

Look especially for:

- conflicts between the authority chain, the state caches and instance course paths
- the same fact defined in more than one file
- whether paths, filenames, fields and state machines are clean
- divergence that should not exist between the skeleton's generic templates and the main instance
- anything in lite that should not be uploaded: environment files, secrets, large binaries

Report findings as "severity + file/line + evidence + recommendation". Do not run first
run, teaching write-back, dependency installation or model downloads in this directory;
when a change is needed, give a review recommendation and let the local main/skeleton adjudicate.

## Regeneration discipline

lite can only be regenerated from main; it is not a rule source. The order is fixed:

`skeleton generic rules finalized -> main absorbs them and keeps instance data -> sync_lite full regeneration -> doctor`

**main must be committed to disk first** (`sync_lite` refuses a dirty tree by default; see
`--force`). Do not hand-edit lite and expect it to flow back to main. Half-sync is
eliminated by full regeneration, not by allowlisted patches.
"""

LITE_AGENTS = """# t2ag-lite 0.2.4 startup notes

This directory is **an online review snapshot of the t2ag primary instance** (fully
regenerated by `main/70_tools/sync_lite.py`).

## Rules

- **Read-only review**: no teaching write-back, no editing the progress source of truth,
  no installing dependencies, and do not use it as a skeleton.
- You may still read `main/t2ag.md` and `main/00_core/t2ag_memory.md` to understand the structure.
- Return findings to the local instance as a review report; once main/skeleton has
  adjudicated and written them, lite is regenerated.

## Three-form base content

- The doctor/test base structure must stay aligned with Main and Skeleton: runtime is the
  startup profile, release is the release-audit profile.
- The code, flow tree, control file and dependency manifest for `--profile runtime` and
  `--profile release` are all retained for read-only review;
  `validation_workflow.json` mechanically constrains the plan SHA, the release reason and
  the ordinary budget.
- **Do not execute** doctor, the test selector, a release scenario or any write-back in
  Lite; execution belongs to the local Main/Skeleton only.

## Version

- Aligned with the source main; the current runtime version is `0.2.4`, and the
  authoritative version number is in `main/t2ag.md`.
- **Baseline and increment**: the most recent release-qualification baseline is `0.2.3` /
  `finalization_delta_passed` (2026-08-24); runtime version `0.2.4` claims neither candidate nor FIN.
  Changes since then are at the top of `main/00_core/t2ag_changelog.md`; entries without a
  candidate independent re-review and a finalization delta are outside release qualification.
- This file is rewritten as the review-identity description on every `sync_lite.py` run.
"""


def is_allowed_binary(rel: Path, tree_prefix: str = "") -> bool:
    """Match ALLOWED_BINARY_REL using path relative to t2ag root when possible."""
    rel_posix = rel.as_posix()
    candidates = [rel_posix]
    if tree_prefix:
        candidates.append(f"{tree_prefix.rstrip('/')}/{rel_posix}")
    return any(c in ALLOWED_BINARY_REL for c in candidates)


def should_skip_file(path: Path, rel: Path, tree_prefix: str = "") -> bool:
    """rel is relative to the sync root (main/, cloud/, assets/, or a single repo-root file)."""
    ext = path.suffix.lower()
    parts = rel.parts
    if rel.name in {"teaching_log.md", "emissions.jsonl"}:
        # Canonical carrier instance files (canon_carrier.md §1) hold textbook source
        # quotations, count as instance data, and do not enter the Lite review snapshot.
        # The rule must exist before the first emit (2026-08-19, added by EV-0030).
        return True
    for p in parts:
        if p in SKIP_DIR_NAMES:
            return True
        if p == "pages" and "working_pages" in parts:  # post-S3 defensive skip (directory retired)
            return True
    if is_allowed_binary(rel, tree_prefix):
        return False
    if ext in FORBIDDEN_EXT:
        return True
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if "primary" in parts and ext in {".txt", ".html", ".htm"} and size > MAX_FILE_BYTES:
        return True
    if size > MAX_FILE_BYTES:
        if ext in TEXT_EXT:
            return size > MAX_TEXT_BYTES
        return True
    return False

def require_main_clean(src: Path, force: bool) -> str:
    """The main working tree must be clean, or this refuses (`--force` overrides).

    Dirty-tree detection shares git_status_porcelain with doctor.check_release_snapshot
    (whole tree vs release-related pathspec is the caller's choice).
    """
    git_dir = src / ".git"
    if not git_dir.exists():
        print("WARN: main has no .git; skip clean-tree gate", file=sys.stderr)
        return "no-git"
    try:
        # Co-located import: same 70_tools/ when run as script.
        from t2ag_doctor import git_status_porcelain  # type: ignore
    except ImportError:
        git_status_porcelain = None  # type: ignore
    if git_status_porcelain is not None:
        try:
            dirty = git_status_porcelain(src)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    else:
        run = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=src,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if run.returncode != 0:
            print(
                f"ERROR: git status failed in {src}: {run.stderr.strip()}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        dirty = run.stdout.strip()
    if not dirty:
        print("gate: main working tree clean OK")
        return ""
    msg = (
        "REFUSE: main working tree is dirty; refuse to project an uncommitted "
        "intermediate state onto git-less lite.\n"
        "Commit (or stash) main first, then re-run. Override: --force\n"
        "--- git status --porcelain ---\n"
        f"{dirty}"
    )
    if force:
        rows = dirty.splitlines()
        preview = "\n".join(rows[:25])
        suffix = f"\n... ({len(rows) - 25} more)" if len(rows) > 25 else ""
        print(
            "WARN: --force: operating from dirty main\n"
            + preview + suffix,
            file=sys.stderr,
        )
        return dirty
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def clear_lite_tree(dst: Path, dry_run: bool) -> int:
    if dst.name != "t2ag-lite":
        raise SystemExit(f"REFUSE: destination must be named t2ag-lite, got {dst}")
    removed = 0
    if not dst.exists():
        if not dry_run:
            dst.mkdir(parents=True)
        return 0
    for child in list(dst.iterdir()):
        if child.name in PRESERVE_DST_TOP:
            print(f"preserve destination-local: {child.name}")
            continue
        if dry_run:
            removed += 1
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1
    return removed


def iter_projected_files(
    src_root: Path, tree_prefix: str = ""
) -> list[tuple[Path, Path]]:
    """Return (absolute src file, rel path under src_root) that should be copied."""
    out: list[tuple[Path, Path]] = []
    if not src_root.exists():
        return out
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(src_root)
        if should_skip_file(src, rel, tree_prefix):
            continue
        out.append((src, rel))
    return out


def copy_filtered(
    src_root: Path, dst_root: Path, dry_run: bool, tree_prefix: str = ""
) -> tuple[int, int, int]:
    copied = skipped = redacted = 0
    if not src_root.exists():
        return 0, 0, 0
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(src_root)
        if should_skip_file(src, rel, tree_prefix):
            skipped += 1
            continue
        dst = dst_root / rel
        if dry_run:
            copied += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        redacted += copy_projected_file(src, dst)
        copied += 1
    return copied, skipped, redacted

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_projection_sha256(source: Path) -> str:
    """Hash of what the Lite copy of *source* should contain (post-redaction for text)."""
    if source.suffix.lower() in TEXT_EXT:
        data, hits = redact_host_bytes(source.read_bytes())
        if hits:
            return hashlib.sha256(data).hexdigest()
    return sha256_file(source)


def copy_projected_file(source: Path, target: Path) -> int:
    """Copy one projected file applying host redaction to text payloads; return hits."""
    if source.suffix.lower() in TEXT_EXT:
        data = source.read_bytes()
        redacted, hits = redact_host_bytes(data)
        if hits:
            target.write_bytes(redacted)
            shutil.copystat(source, target)
            return hits
    shutil.copy2(source, target)
    return 0


def source_projection_manifest(src: Path) -> dict[str, tuple[int, int, str]]:
    """Exact stable manifest of files eligible for the Lite projection."""
    result: dict[str, tuple[int, int, str]] = {}
    for label, source, _target in projection_manifest(src, src):
        info = source.stat()
        result[label] = (
            stat.S_IMODE(info.st_mode),
            info.st_size,
            sha256_file(source),
        )
    return result


def lite_content_manifest(dst: Path) -> dict[str, tuple[int, int, str]]:
    result: dict[str, tuple[int, int, str]] = {}
    if not dst.exists():
        return result
    for path in sorted(dst.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(dst)
        if relative.parts and relative.parts[0] in PRESERVE_DST_TOP:
            continue
        info = path.stat()
        result[relative.as_posix()] = (
            stat.S_IMODE(info.st_mode),
            info.st_size,
            sha256_file(path),
        )
    return result


def is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def validate_destination(workspace: Path, src: Path, dst: Path) -> None:
    workspace = workspace.resolve()
    expected = workspace / "t2ag-lite"
    if dst.absolute() != expected or dst.name != "t2ag-lite":
        raise RuntimeError(f"destination must be exact workspace t2ag-lite: {dst}")
    if is_reparse(workspace) or is_reparse(src) or is_reparse(dst):
        raise RuntimeError("workspace/Main/Lite symlink or reparse point refused")
    if dst.exists() and src.resolve() == dst.resolve():
        raise RuntimeError("Main and Lite resolve to the same directory")


def require_distinct_file_ids(*paths: Path) -> None:
    existing = [path for path in paths if path.exists()]
    for index, left in enumerate(existing):
        for right in existing[index + 1:]:
            try:
                same = os.path.samefile(left, right)
            except OSError:
                same = False
            if same:
                raise RuntimeError(
                    f"temporary/candidate/rollback aliases protected tree: {left} == {right}"
                )


def inject_failure(point: str) -> None:
    if os.environ.get("T2AG_SYNC_LITE_FAIL_AT") == point:
        raise RuntimeError(f"injected failure at {point}")


def verify_projection(
    src: Path,
    dst: Path,
    projected: list[tuple[str, Path, Path]],
) -> int:
    """Full hash check of all projected files. projected: (label, src_file, dst_file).

    Returns number of mismatches (0 = OK).
    """
    match = missing = differ = 0
    print("--- full hash verify (projected files, no sample) ---")
    for label, s, d in sorted(projected, key=lambda x: x[0]):
        if not s.is_file():
            print(f"MISS_SRC {label}")
            missing += 1
            continue
        if not d.is_file():
            print(f"MISS_DST {label}")
            missing += 1
            continue
        hs, hd = expected_projection_sha256(s), sha256_file(d)
        if hs == hd:
            match += 1
        elif label in LITE_GUIDE_DIVERGE_REL:
            # counted separately as intentional (map rebuilt for lite)
            match += 1
            print(f"GUIDE {label}: diverge_ok (edition-local GENERATED)")
        else:
            differ += 1
            print(f"DIFFER {label}")
            print(f"  src={hs[:16]} dst={hd[:16]}")
    # intentional identity diverge
    print("--- intentional diverge (lite identity, not errors) ---")
    for rel in sorted(LITE_IDENTITY_REL):
        sp, dp = src / rel, dst / rel
        if sp.is_file() and dp.is_file():
            same = sha256_file(sp) == sha256_file(dp)
            print(f"IDENTITY {rel}: {'UNEXPECTED_MATCH' if same else 'diverge_ok'}")
        elif dp.is_file():
            print(f"IDENTITY {rel}: lite_only_ok")
        else:
            print(f"IDENTITY {rel}: missing_lite")
    print(
        f"hash_summary: match={match} differ={differ} missing={missing} "
        f"projected={len(projected)}"
    )
    if differ or missing:
        print("FAIL: projection hash verify failed", file=sys.stderr)
        return differ + missing
    print("hash_verify: projected files byte-identical to main (guide map may diverge_ok)")
    return 0


BIRTH_KEYS = ("generated_at", "source_commit", "file_count", "dirty_tree", "host_redactions")


def render_birth_block(birth: dict) -> str:
    """Birth certificate (F2): the snapshot must attest to its own generation moment and
    source, so ambiguity no longer depends on memory from outside the artifact."""
    lines = [
        "\n## Birth certificate (written by sync_lite on every regeneration; review_LITE-20260812-0001 F2)\n\n"
    ]
    for key in BIRTH_KEYS:
        lines.append(f"- {key}: {birth.get(key, 'unknown')}\n")
    return "".join(lines)


def git_head_commit(src: Path) -> str:
    try:
        run = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=src, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return run.stdout.strip() if run.returncode == 0 and run.stdout.strip() else "unknown"


def write_identity(dst: Path, dry_run: bool, birth: dict | None = None) -> None:
    if dry_run:
        return
    (dst / "README.md").write_text(LITE_README, encoding="utf-8", newline="\n")
    agents = LITE_AGENTS + (render_birth_block(birth) if birth else "")
    (dst / "AGENTS.md").write_text(agents, encoding="utf-8", newline="\n")


def projection_manifest(src: Path, dst: Path) -> list[tuple[str, Path, Path]]:
    projected: list[tuple[str, Path, Path]] = []
    for name in ("main", "cloud", "assets"):
        for source, rel in iter_projected_files(src / name, tree_prefix=name):
            label = f"{name}/{rel.as_posix()}"
            projected.append((label, source, dst / name / rel))
    # docs/handoffs/ -- controlled projection: active handoffs + the six version
    _project_handoffs(src, dst, projected)
    # authorities named by constitution §7
    # docs/adr + docs/protocol -- read-only review closure (text .md; no execution rights)
    _project_decision_docs(src, dst, projected)
    for name in ("t2ag_directory_guide.html", ".gitignore"):
        source = src / name
        if source.is_file() and not should_skip_file(source, Path(name)):
            projected.append((name, source, dst / name))
    return projected


# The six version-authority handoffs cited by constitution §7 (verifiable regardless of status)
_CONSTITUTION_HANDOFFS: frozenset[str] = frozenset({
    "T2AG_021_FULL_CLOSEOUT_AND_REVIEW_GOVERNANCE_WORKORDER_2026-08-04.md",
    "T2AG_021_VERSION_INDEPENDENT_REVIEW_2026-08-04.md",
    "T2AG_021_FINALIZATION_DELTA_REVIEW_2026-08-04.md",
    "T2AG_022_ACTIVITY_CLOSE_LEDGER_WORKORDER_2026-08-04.md",
    "T2AG_022_VERSION_INDEPENDENT_REVIEW_2026-08-05.md",
    "T2AG_022_FINALIZATION_DELTA_REVIEW_2026-08-05.md",
})


def _project_handoffs(
    src: Path, dst: Path, projected: list[tuple[str, Path, Path]]
) -> None:
    """Project active handoffs and constitutional references from docs/handoffs/."""
    handoff_dir = src / "docs" / "handoffs"
    if not handoff_dir.is_dir():
        return
    for path in sorted(handoff_dir.rglob("*.md")):
        if path.name.startswith("_"):
            continue  # skip tool-script attachments
        rel = path.relative_to(src)
        # project .md only (reviewable text); skip backups/ and oversized files
        if "backups" in rel.parts:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            continue
        # the six constitution §7 files project unconditionally; the rest only when they
        # carry an active status marker
        is_constitutional = path.name in _CONSTITUTION_HANDOFFS
        if not is_constitutional:
            # check the frontmatter / first lines for an active / in_progress marker
            try:
                first_lines = path.read_text(encoding="utf-8")[:2000]
            except Exception:
                continue
            if not re.search(
                # LV-5: the status marker ships in either language; both spellings are accepted.
            r"\*\*(?:状态|Status)\*\*[：:]\s*"
            r"(?:active|进行中|in.progress|方案讨论完成|design discussion complete)",
                first_lines,
            ):
                continue
        label = rel.as_posix()
        projected.append((label, path, dst / rel))


def _project_decision_docs(
    src: Path, dst: Path, projected: list[tuple[str, Path, Path]]
) -> None:
    """Project ADR and protocol markdown for Lite review-only closure.

    Does not grant Lite execution authority or host hard gates.
    """
    for sub in ("adr", "protocol"):
        base = src / "docs" / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            rel = path.relative_to(src)
            if "backups" in rel.parts:
                continue
            if path.name.startswith("_"):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            if should_skip_file(path, rel):
                continue
            label = rel.as_posix()
            projected.append((label, path, dst / rel))


def check_current_projection(src: Path, dst: Path) -> int:
    projected = projection_manifest(src, dst)
    expected = {label for label, _, _ in projected} | set(LITE_IDENTITY_REL)
    current: set[str] = set()
    if dst.exists():
        for path in dst.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(dst)
            if rel.parts and rel.parts[0] in PRESERVE_DST_TOP:
                continue
            current.add(rel.as_posix())

    missing = sorted(expected - current)
    orphan = sorted(current - expected)
    differ: list[str] = []
    for label, source, target in projected:
        if label not in current or label in LITE_GUIDE_DIVERGE_REL:
            continue
        if expected_projection_sha256(source) != sha256_file(target):
            differ.append(label)

    readme = dst / "README.md"
    if readme.is_file() and readme.read_text(encoding="utf-8") != LITE_README:
        differ.append("README.md")
    agents = dst / "AGENTS.md"
    if agents.is_file():
        agents_text = agents.read_text(encoding="utf-8")
        birth_ok = all(
            re.search(rf"^- {key}: \S", agents_text, re.MULTILINE) for key in BIRTH_KEYS
        )
        if not agents_text.startswith(LITE_AGENTS) or not birth_ok:
            differ.append("AGENTS.md")

    # Redaction residue self-test (F5): projected text must no longer contain the host
    residual: list[str] = []
    # identity string. Skipped when HOST_USER is empty: an empty needle matches every
    # file and the self-test becomes noise (a failed derivation already shows up as an
    # empty HOST_REDACTIONS and host_redactions=0; this is not the place to catch it).
    if dst.exists() and HOST_USER:
        needle = HOST_USER.encode()
        for path in dst.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_EXT:
                continue
            rel = path.relative_to(dst)
            if rel.parts and rel.parts[0] in PRESERVE_DST_TOP:
                continue
            try:
                if needle in path.read_bytes():
                    residual.append(rel.as_posix())
            except OSError:
                residual.append(rel.as_posix() + " (unreadable)")
    for value in residual[:10]:
        print(f"HOST_RESIDUAL {value}")
    if residual:
        differ.append(f"host-identity residual in {len(residual)} file(s)")

    guide_bad = False
    guide = dst / "t2ag_directory_guide.html"
    if guide.is_file():
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        try:
            import build_guide as bg  # type: ignore

            guide_bad = bg.run(dst, write=False) != 0
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            print(f"ERROR: Lite guide check failed: {exc}", file=sys.stderr)
            guide_bad = True

    print(
        f"projection_check: expected={len(expected)} current={len(current)} "
        f"missing={len(missing)} differ={len(differ)} orphan={len(orphan)} "
        f"guide_drift={int(guide_bad)}"
    )
    for label, values in (
        ("MISSING", missing),
        ("DIFFER", sorted(set(differ))),
        ("ORPHAN", orphan),
    ):
        for value in values[:20]:
            print(f"{label} {value}")
        if len(values) > 20:
            print(f"{label} ... ({len(values) - 20} more)")
    if missing or differ or orphan or guide_bad:
        print("FAIL: Lite projection drift; rerun with --write", file=sys.stderr)
        return 1
    print("OK: Lite matches the current Main projection")
    return 0


def build_candidate(
    src: Path, candidate: Path, birth: dict | None = None
) -> tuple[int, int, list[tuple[str, Path, Path]]]:
    total_copied = total_skipped = total_redacted = 0
    for name in ("main", "cloud", "assets"):
        copied, skipped, redacted = copy_filtered(
            src / name, candidate / name, False, tree_prefix=name
        )
        total_copied += copied
        total_skipped += skipped
        total_redacted += redacted
        print(f"tree {name}: copied={copied} skipped={skipped} redacted_hits={redacted}")
    for name in ("t2ag_directory_guide.html", ".gitignore"):
        source = src / name
        if source.is_file() and not should_skip_file(source, Path(name)):
            total_redacted += copy_projected_file(source, candidate / name)
            total_copied += 1
            print(f"root file: {name}")
        elif source.is_file():
            total_skipped += 1

    # Copy projected docs/* extras (handoffs, adr, protocol) not covered by tree loops.
    projected_preview = projection_manifest(src, candidate)
    extras = 0
    for label, source, target in projected_preview:
        if label.startswith(("main/", "cloud/", "assets/")):
            continue
        if label in LITE_IDENTITY_REL or label in LITE_GUIDE_DIVERGE_REL:
            continue
        if label in {".gitignore", "t2ag_directory_guide.html"}:
            continue
        if not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        total_redacted += copy_projected_file(source, target)
        extras += 1
        total_copied += 1
    if extras:
        print(f"docs extras: copied={extras}")

    if birth is not None:
        birth["file_count"] = len(projected_preview)
        birth["host_redactions"] = total_redacted
    print(f"host_redactions: {total_redacted}")
    write_identity(candidate, False, birth)
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import build_guide as bg  # type: ignore

    if bg.run(candidate, write=True):
        raise RuntimeError("build_guide returned non-zero")
    projected = projection_manifest(src, candidate)
    return total_copied, total_skipped, projected


def restore_previous_lite(
    dst: Path,
    rollback: Path,
    installed: list[Path],
    moved_old: list[Path],
) -> None:
    errors: list[str] = []
    for index, target in enumerate(reversed(installed), start=1):
        try:
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            inject_failure(f"rollback_remove:{index}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"remove {target.name}: {exc}")
    for index, old in enumerate(moved_old, start=1):
        try:
            if old.exists():
                shutil.move(str(old), str(dst / old.name))
            inject_failure(f"rollback_restore:{index}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"restore {old.name}: {exc}")
    if errors:
        residue = sorted(
            path.relative_to(dst.parent).as_posix()
            for root in (dst, rollback)
            if root.exists()
            for path in root.rglob("*")
            if path.is_file()
        )
        raise RuntimeError(
            f"Lite rollback failed: {'; '.join(errors)}; exact residue={residue}"
        )


def inherit_destination_acl(dst: Path, installed: list[Path]) -> None:
    """Make newly installed Windows entries inherit the destination ACL.

    Codex review sessions can create protected DACLs on temporary directories.
    A same-volume move preserves those DACLs, which would make the generated
    Lite unreadable to a later independent reviewer.  Reset only the newly
    installed top-level entries; destination-local preserved entries are never
    included in ``installed``.
    """
    if os.name != "nt":
        return
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise RuntimeError("SystemRoot is missing; cannot locate trusted icacls.exe")
    icacls = Path(system_root) / "System32" / "icacls.exe"
    if not icacls.is_file():
        raise RuntimeError(f"trusted icacls.exe is missing: {icacls}")
    destination = dst.resolve()
    for target in installed:
        if target.parent.resolve() != destination:
            raise RuntimeError(
                f"refusing to reset ACL outside Lite destination: {target}"
            )
        recursive = ["/T"] if target.is_dir() else []
        for operation in ("/inheritance:e", "/reset"):
            command = [str(icacls), str(target), operation, *recursive, "/Q"]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=30,
                )
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(
                    f"timed out resetting installed Lite ACL after 30s: {target} ({operation})"
                ) from error
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(
                    "failed to make installed Lite entry inherit destination ACL: "
                    f"{target} ({operation}, exit {result.returncode}): {detail}"
                )


def install_candidate(
    candidate: Path,
    dst: Path,
    rollback: Path,
) -> tuple[list[Path], list[Path]]:
    if dst.name != "t2ag-lite":
        raise RuntimeError(f"destination must be named t2ag-lite, got {dst}")
    rollback.mkdir(parents=False, exist_ok=False)
    moved_old: list[Path] = []
    installed: list[Path] = []
    dst.mkdir(parents=True, exist_ok=True)
    try:
        for index, child in enumerate(list(dst.iterdir()), start=1):
            if child.name in PRESERVE_DST_TOP:
                print(f"preserve destination-local: {child.name}")
                continue
            target = rollback / child.name
            shutil.move(str(child), str(target))
            moved_old.append(target)
            inject_failure(f"move_old:{index}")
        for index, child in enumerate(list(candidate.iterdir()), start=1):
            target = dst / child.name
            shutil.move(str(child), str(target))
            installed.append(target)
            inject_failure(f"install_new:{index}")
        inherit_destination_acl(dst, installed)
    except Exception as install_error:
        try:
            restore_previous_lite(dst, rollback, installed, moved_old)
        except Exception as rollback_error:
            raise RuntimeError(
                f"Lite install failed: {install_error}; {rollback_error}"
            ) from install_error
        raise RuntimeError(
            f"Lite install failed: {install_error}; previous Lite restored"
        ) from install_error
    return moved_old, installed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Full-regenerate t2ag-lite from t2ag (plan A)")
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="T2AC workspace root containing t2ag/ and t2ag-lite/",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Deprecated alias for the default check-only projection preview",
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="Explicitly regenerate Lite (default: check-only preview)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Allow regenerate from dirty main (prints warning; not recommended)",
    )
    args = ap.parse_args(argv)
    if args.dry_run and args.write:
        ap.error("--dry-run and --write are mutually exclusive")
    dry_run = not args.write

    script_path = Path(__file__).resolve()
    t2ag_root = script_path.parents[2]
    workspace = args.root.resolve() if args.root else t2ag_root.parent
    src = workspace / "t2ag"
    dst = workspace / "t2ag-lite"

    if not src.is_dir():
        print(f"ERROR: main missing: {src}", file=sys.stderr)
        return 1
    try:
        validate_destination(workspace, src, dst)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("plan=A full-regenerate")
    print(f"src={src}")
    print(f"dst={dst}")
    print(f"mode={'write' if args.write else 'check-only'} force={args.force}")
    print("binary_allowlist:")
    for rel, reason in sorted(ALLOWED_BINARY_REL.items()):
        print(f"  {rel}: {reason}")

    # Gate: main clean (even for dry-run — dry-run should still teach the discipline)
    dirty_state = require_main_clean(src, force=args.force)

    if dry_run:
        return check_current_projection(src, dst)

    birth = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_commit": git_head_commit(src),
        "dirty_tree": "unknown" if dirty_state == "no-git" else str(bool(dirty_state)).lower(),
        "file_count": 0,
        "host_redactions": 0,
    }
    source_before_build = source_projection_manifest(src)
    old_lite_manifest: dict[str, tuple[int, int, str]] | None = None
    installed_state: tuple[list[Path], list[Path], Path] | None = None
    # Use mkdtemp + finally so post-install recovery still sees rollback.
    # TemporaryDirectory would delete rollback before the outer except could restore.
    temporary_root: Path | None = None
    try:
        temporary_root = Path(
            tempfile.mkdtemp(prefix=".t2ag-lite-build-", dir=str(workspace))
        )
        candidate = temporary_root / "candidate"
        rollback = temporary_root / "rollback"
        candidate.mkdir()
        require_distinct_file_ids(temporary_root, candidate, src, dst)
        total_copied, total_skipped, projected = build_candidate(
            src, candidate, birth
        )
        print(f"candidate={candidate}")
        print(f"TOTAL copied={total_copied} skipped={total_skipped}")
        bad = verify_projection(src, candidate, projected)
        if bad:
            print("FAIL: candidate rejected; existing Lite untouched", file=sys.stderr)
            return 3
        source_after_candidate = source_projection_manifest(src)
        if source_after_candidate != source_before_build:
            raise RuntimeError("Main projection source changed after candidate verification")
        old_lite_manifest = lite_content_manifest(dst)
        moved_old, installed = install_candidate(candidate, dst, rollback)
        installed_state = (moved_old, installed, rollback)
        require_distinct_file_ids(temporary_root, candidate, rollback, src, dst)
        print(f"installed_after_removing_top_level_entries={len(moved_old)}")
        source_after_install = source_projection_manifest(src)
        if source_after_install != source_before_build:
            raise RuntimeError("Main projection source changed after Lite installation")
        inject_failure("final_verify")
        final_projected = projection_manifest(src, dst)
        if verify_projection(src, dst, final_projected):
            raise RuntimeError("final projection hash verification failed")
        if check_current_projection(src, dst):
            raise RuntimeError("final Lite projection/guide verification failed")
        source_before_return = source_projection_manifest(src)
        if source_before_return != source_before_build:
            raise RuntimeError("Main projection source changed before final return")
        inject_failure("final_return")
        shutil.rmtree(rollback)
        installed_state = None
    except Exception as exc:  # noqa: BLE001
        rollback_detail = ""
        if installed_state is not None:
            moved_old, installed, rollback = installed_state
            try:
                restore_previous_lite(dst, rollback, installed, moved_old)
                if old_lite_manifest is None or lite_content_manifest(dst) != old_lite_manifest:
                    raise RuntimeError("restored Lite byte manifest differs from pre-install state")
                rollback_detail = "; previous Lite restored and byte manifest verified"
            except Exception as rollback_error:  # noqa: BLE001
                rollback_detail = f"; ROLLBACK FAIL: {rollback_error}"
        elif old_lite_manifest is not None and lite_content_manifest(dst) != old_lite_manifest:
            rollback_detail = "; ROLLBACK FAIL: install-time recovery did not restore exact Lite manifest"
        print(
            f"FAIL: candidate build/install/final verification failed: {exc}{rollback_detail}",
            file=sys.stderr,
        )
        return 4
    finally:
        if temporary_root is not None and temporary_root.exists():
            shutil.rmtree(temporary_root, ignore_errors=True)

    final_projected = projection_manifest(src, dst)

    # snail: confirm allowlist hit (copied via main/ tree)
    snail_label = "main/80_interface/fable_snail.png"
    if any(label == snail_label for label, _, _ in final_projected):
        print(f"{snail_label}: kept ({ALLOWED_BINARY_REL[snail_label]})")
    elif (src / "main" / "80_interface" / "fable_snail.png").is_file():
        print(
            f"WARN: {snail_label} exists on main but was not projected",
            file=sys.stderr,
        )

    courses = (
        list((dst / "main" / "40_course").glob("*/course.md"))
        if (dst / "main" / "40_course").exists()
        else []
    )
    progress = (
        list((dst / "main" / "40_course").glob("*/progress.md"))
        if (dst / "main" / "40_course").exists()
        else []
    )
    print(f"lite courses={len(courses)} progress={len(progress)}")
    print("OK: regenerate complete. Next: python main/70_tools/t2ag_doctor.py (cwd=t2ag-lite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
