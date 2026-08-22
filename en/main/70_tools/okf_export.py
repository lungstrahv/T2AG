#!/usr/bin/env python3
"""T2AG -> OKF v0.2 knowledge-bundle exporter (EV-0024 / protocol `T2AG-OKF-1`).

The specification source of truth is `main/50_playbook/okf_adaptation.md`; this file is
its recomputable implementation. On conflict the playbook wins and this file gets fixed
-- that is how "a prose claim must have a machine landing point" (the EV-0016 / EV-0018
family) lands on this protocol.

Where the three invariants (playbook §1) live in the code:
1. Zero change to the main library -- the whole flow reads it only; the sole write path
   is the out-of-repo directory `--write` points at.
2. Mechanism is exchangeable, instances stay home -- `collect_sources()` is a
   directory-level positive-enumeration allowlist, and no code path leads past it.
3. Never forge trust -- `verified` is never written: structural verification is not
   content verification.

The leak gate runs **after in-memory rendering and before anything reaches disk**
(`leak_findings`); a hit means zero writes. The pattern list is imported from
`t2ag_doctor.SKELETON_PRIVACY_PATTERNS` as a shared source of truth, and a failed import
exits rather than degrading to a weaker list -- "if the list is missing, skip the scan"
is the classic shape of a gate that has quietly stopped working.

Usage:
  python main/70_tools/okf_export.py                      # check-only (default): render + full check
  python main/70_tools/okf_export.py --write              # on pass, write to <workspace>/t2ag-okf/
  python main/70_tools/okf_export.py --check-bundle <dir> # recompute conformance for an existing bundle

Exit codes: 0 pass; 1 a FAIL (leak hit, conformance failure, empty scope).
This tool is **not registered in the doctor runtime**: the bundle is an optional artifact
and its absence must not block the day's teaching (same as `t2ag.md` §3.2).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"

TOOL_VERSION = "0.1.0"
ACTOR = f"t2ag/okf_export-{TOOL_VERSION}"
OKF_VERSION = "0.2"
# The output directory derives from the repo name rather than hardcoding `t2ag-okf`:
# Main and Skeleton share one workspace, so a fixed name would make the two exports
# overwrite each other (EV-0022 family: landing point derived from the repo root).
DEFAULT_OUT = ROOT.parent / f"{ROOT.name}-okf"

# EV-0024 R-1 / P0-3: the identity marker of a delivery directory. `--write` writes only
# into an empty directory or one carrying this marker, and refuses everything else.
# Without it, `--out` is just an arbitrary path while write_bundle deletes any .md in the
# target outside the manifest -- exactly the high-risk write path the review measured.
BUNDLE_MARKER = ".t2ag-okf-bundle"

# EV-0024 R-1 / P0-1: the ID allowlist for a course scope. Only alphanumerics and `_-`,
# so `..`, `/`, `\`, absolute paths and whitespace all land on the reject side without
# enumerating dangerous characters one by one.
COURSE_ID_RE = re.compile(r"\A[A-Za-z0-9_-]+\Z")

# EV-0024 R-3: the inline-code shape allowed to become a link -- a single path token, no
# whitespace, no quotes, no shell metacharacters. Criterion: `is_single_path_token()`.
SINGLE_PATH_RE = re.compile(r"\A[A-Za-z0-9._/-]+\Z")

RESERVED_NAMES = {"index.md", "log.md"}
CHANGELOG_REL = "00_core/t2ag_changelog.md"
LOG_ENTRY_LIMIT = 25

# playbook §2: directory-level positive enumeration of the mechanism scope. The three
# ledgers (changelog/memory/problemlog) and every course are deliberately absent; see §2.
MECHANISM_CORE_FILES = (
    "domain_model.md",
    "learning_activity_model.md",
    "pattern_retire_loop.md",
)

# playbook §3.1: the type-injection table. A file that already has frontmatter passes its
# own type through and never enters this table.
TYPE_DOMAIN_MODEL = "Domain Model"
TYPE_GOVERNANCE = "Governance Doc"
TYPE_PLAYBOOK = "Playbook"
TYPE_REFERENCE = "Reference"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\]\(([^)]+)\)")
CHANGELOG_HEADING_RE = re.compile(r"^##\s*\[(\d{4}-\d{2}-\d{2})\]\s*(.+?)\s*$", re.MULTILINE)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------- helpers


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def privacy_patterns() -> tuple[tuple[str, str], ...]:
    """The leak pattern list has exactly one source, doctor; stop if unavailable, never degrade."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import t2ag_doctor  # noqa: PLC0415 - deferred import: only needed when exporting
    except Exception as error:  # pragma: no cover - honest failure on a broken environment
        raise SystemExit(
            f"okf_export: cannot load the leak pattern list from t2ag_doctor; refusing to export with no gate: {error}"
        ) from error
    return tuple(t2ag_doctor.SKELETON_PRIVACY_PATTERNS)


def split_frontmatter(text: str) -> tuple[dict | None, str]:
    """Split YAML frontmatter from the body. Returns (None, original) when there is none."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None, text
    if not isinstance(data, dict):
        return None, text
    return data, text[match.end():]


def first_h1(body: str) -> str | None:
    match = H1_RE.search(body)
    return match.group(1).strip() if match else None


def lead_description(body: str) -> str | None:
    """First sentence of the first readable prose paragraph after H1, for index.md (OKF §8)."""
    match = H1_RE.search(body)
    tail = body[match.end():] if match else body
    for raw in tail.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "|", "-", "*", "```", "<!--")):
            continue
        line = line.lstrip("> ").strip()
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"`(.+?)`", r"\1", line)
        if not line:
            continue
        for stop in ("。", "；", ". "):
            if stop in line:
                line = line.split(stop)[0] + (stop.strip() if stop != ". " else ".")
                break
        return line[:160]
    return None


def git_committed_at(rel: str) -> str | None:
    """Time of this file's last commit. Read-only; --no-optional-locks keeps .git locks untouched."""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "log", "-1", "--format=%cI", "--", rel],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    stamp = result.stdout.strip()
    return stamp or None


def timestamp_for(path: Path) -> str:
    """playbook §3.2: prefer the git commit time, fall back to mtime. Always UTC."""
    rel = path.relative_to(ROOT).as_posix()
    stamp = git_committed_at(rel)
    if stamp:
        try:
            return _dt.datetime.fromisoformat(stamp).astimezone(
                _dt.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    return _dt.datetime.fromtimestamp(
        path.stat().st_mtime, tz=_dt.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- collection


def collect_sources(scope: str) -> tuple[list[tuple[Path, str, str | None]], list[str]]:
    """Positively enumerate source files for a scope.

    Returns (entries, errors). An entry is (source path, path inside the bundle, injected
    type|None); `None` means the file carries its own frontmatter and its type passes
    through uninjected.
    """
    items: list[tuple[Path, str, str | None]] = []
    errors: list[str] = []

    if scope == "mechanism":
        constitution = MAIN / "t2ag.md"
        if constitution.is_file():
            items.append((constitution, "t2ag.md", TYPE_GOVERNANCE))
        else:
            errors.append("mechanism scope is missing a file: main/t2ag.md")

        for name in MECHANISM_CORE_FILES:
            path = MAIN / "00_core" / name
            if not path.is_file():
                errors.append(f"mechanism scope is missing a file: main/00_core/{name}")
                continue
            injected = TYPE_DOMAIN_MODEL if name == "domain_model.md" else TYPE_GOVERNANCE
            items.append((path, f"00_core/{name}", injected))

        for path in sorted((MAIN / "50_playbook").glob("*.md")):
            if path.name == "_README.md":
                continue
            items.append((path, f"50_playbook/{path.name}", TYPE_PLAYBOOK))

        for path in sorted((MAIN / "70_tools").glob("*.md")):
            if path.name == "_README.md":
                continue
            items.append((path, f"70_tools/{path.name}", TYPE_REFERENCE))

    elif scope.startswith("course:"):
        course_id = scope.split(":", 1)[1].strip()
        if not course_id:
            errors.append("course scope was given no course ID")
            return items, errors
        # P0-1: validate before joining paths. course_id enters both the source path and
        # the output relative path; unvalidated, `..` forms a read and a write traversal
        # at once (the review's §1 "no reachable path at the instance layer" finding).
        if not COURSE_ID_RE.match(course_id):
            errors.append(
                f"course ID is invalid: {course_id!r} (letters, digits, underscore and hyphen only; "
                "path separators, `.`, `..` and absolute paths are all refused)"
            )
            return items, errors
        path = MAIN / "40_course" / course_id / "course.md"
        if not path.is_file():
            errors.append(f"course definition does not exist: main/40_course/{course_id}/course.md")
            return items, errors
        # course.md carries its own frontmatter (type: course); passed through uninjected.
        items.append((path, f"40_course/{course_id}/course.md", None))

    else:
        errors.append(f"unknown scope: {scope} (available: mechanism, course:<COURSE_ID>)")

    return items, errors


# --------------------------------------------------------------------------- rendering


def basename_index(known: set[str]) -> dict[str, str]:
    """Bare filename -> bundle path. Names occurring in several places are skipped, to avoid guessing wrong."""
    seen: dict[str, list[str]] = {}
    for rel in known:
        seen.setdefault(Path(rel).name, []).append(rel)
    return {name: rels[0] for name, rels in seen.items() if len(rels) == 1}


def is_single_path_token(raw: str) -> bool:
    """Is this inline-code content exactly one resolvable `.md` path (EV-0024 R-3)?

    Only inline code passing this criterion may be promoted to a link. The criterion is
    deliberately conservative: better to miss a few real references than to rewrite
    commands, argument strings and examples into links -- the former loses one edge, the
    latter forges meaning.

    Reject cases (one example each):
    - contains whitespace: `` `grep -rn "x" file.md` ``, `` `a.md b.md` ``
    - contains shell metacharacters or quotes: `` `cat a.md | less` ``
    - starts with `-`: `` `--out a.md` `` (a command option, not a path)
    - does not end in `.md`: `` `okf_export.py` ``
    """
    token = raw.strip()
    if not token or token.startswith("-"):
        return False
    if not token.endswith(".md"):
        return False
    return bool(SINGLE_PATH_RE.match(token))


def resolve_reference(raw: str, known: set[str], by_name: dict[str, str]) -> str | None:
    """Resolve a file reference in main-library prose to a bundle path; None when unresolvable."""
    target = raw.strip().lstrip("./")
    if target.startswith("main/"):
        target = target[len("main/"):]
    if target in known:
        return target
    return by_name.get(Path(target).name)


def link_references(
    body: str, source_rel: str, known: set[str], by_name: dict[str, str]
) -> str:
    """Promote backticked file references to markdown links, so the bundle is a real graph.

    T2AG prose references other files with inline backticks (`` `session_close.md` ``)
    rather than markdown links: measured across the mechanism layer, 0 of 1266 references
    were markdown links. Copying that verbatim would export a pile of unconnected files --
    OKF expresses its graph through links (§6.1), and with no links there are no edges, so
    the "knowledge bundle" degrades into a folder.

    Three restraint rules:
    - **Promote only the first occurrence of each target per file.** Repeat promotion is
      noisy and is the same edge on the graph anyway.
    - **Promote only targets that resolve inside the bundle.** References to the instance
      layer (`progress.md` and the like) stay backticked, forging neither an edge nor a
      broken link.
    - **Promote only when the inline-code content is exactly one resolvable path**
      (EV-0024 R-3). The original matched a whole inline-code span, so a full command such
      as `` `grep -rn "x" file.md` `` was promoted wholesale and a multi-target command was
      squashed into one edge -- not a display problem but a rewrite of meaning. Criterion:
      `is_single_path_token()`.
    """
    linked: set[str] = set()
    pattern = re.compile(r"`([^`\n]+)`")

    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        if not is_single_path_token(raw):
            return match.group(0)
        target = resolve_reference(raw, known, by_name)
        if target is None or target == source_rel or target in linked:
            return match.group(0)
        linked.add(target)
        return f"[`{raw}`](/{target})"

    # No rewriting inside fenced code blocks: filenames there are examples or commands.
    parts = body.split("```")
    for index in range(0, len(parts), 2):
        parts[index] = pattern.sub(replace, parts[index])
    return "```".join(parts)


def rewrite_links(body: str, source_rel: str, known: set[str]) -> str:
    """Rewrite existing markdown links into bundle-absolute form (OKF §6.1).

    Links to files that were not collected are kept as they are: OKF states explicitly that
    a broken link represents knowledge not yet written, not an error.
    """
    source_dir = (MAIN / source_rel).parent

    def replace(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        if not target or target.startswith(("http://", "https://", "#", "mailto:", "/")):
            return match.group(0)
        anchor = ""
        if "#" in target:
            target, anchor = target.split("#", 1)
            anchor = "#" + anchor
        if not target:
            return match.group(0)
        try:
            resolved = (source_dir / target).resolve()
            rel = resolved.relative_to(MAIN.resolve()).as_posix()
        except (ValueError, OSError):
            return match.group(0)
        if rel in known:
            return f"](/{rel}{anchor})"
        return match.group(0)

    return LINK_RE.sub(replace, body)


def render_concept(
    path: Path,
    bundle_rel: str,
    injected_type: str | None,
    known: set[str],
    by_name: dict[str, str],
) -> tuple[str, str, str | None]:
    """Render one concept file; returns (text, title, description)."""
    original = read(path)
    existing, body = split_frontmatter(original)

    front: dict = {}
    if existing:
        # Pass every existing key through: OKF asks consumers to preserve unknown keys,
        # so a producer certainly must not drop them.
        front.update(existing)
    if injected_type is not None:
        front["type"] = injected_type
    if not str(front.get("type", "")).strip():
        front["type"] = TYPE_REFERENCE

    title = str(front.get("title") or "").strip() or first_h1(body) or path.stem
    front["title"] = title

    description = str(front.get("description") or "").strip() or lead_description(body)
    if description:
        front["description"] = description

    front["generated"] = {"by": ACTOR, "at": timestamp_for(path)}
    # `verified` is deliberately never written (playbook §1 invariant 3): structural
    # verification is not content verification.
    front.pop("verified", None)

    ordered_keys = ["type", "title", "description", "status", "tags", "generated"]
    ordered = {k: front[k] for k in ordered_keys if k in front}
    ordered.update({k: v for k, v in front.items() if k not in ordered})

    dumped = yaml.safe_dump(
        ordered, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).rstrip("\n")
    rendered = rewrite_links(body, bundle_rel, known)
    rendered = link_references(rendered, bundle_rel, known, by_name)
    text = f"---\n{dumped}\n---\n\n{rendered.lstrip()}"
    return text, title, description


def build_directory_index(
    dir_rel: str, entries: list[tuple[str, str, str | None]], readme: Path | None
) -> str:
    """A directory index.md (OKF §8): each entry description comes from the linked concept itself."""
    lines: list[str] = [f"# {dir_rel}", ""]
    if readme and readme.is_file():
        lead = lead_description(split_frontmatter(read(readme))[1])
        if lead:
            lines += [lead, ""]
    for name, title, description in sorted(entries):
        suffix = f" - {description}" if description else ""
        lines.append(f"* [{title}]({name}){suffix}")
    lines.append("")
    return "\n".join(lines)


def build_root_index(scope: str, groups: dict[str, list[tuple[str, str, str | None]]]) -> str:
    """The root index.md: the only index allowed frontmatter, and only okf_version (OKF §12)."""
    lines = [
        "---",
        f'okf_version: "{OKF_VERSION}"',
        "---",
        "",
        "# T2AG knowledge bundle",
        "",
        f"An OKF v{OKF_VERSION} knowledge bundle exported from the T2AG main library under `T2AG-OKF-1`.",
        f"Scope `{scope}`: mechanism-layer files describing how the system runs -- no student profile,",
        "no learning progress, no teaching transcripts, no logs. Specification: `main/50_playbook/okf_adaptation.md`.",
        "",
        "This bundle is an artifact, not a source of truth: change the main library and re-export.",
        "",
    ]
    root_entries = groups.get(".", [])
    if root_entries:
        lines.append("# Entry points")
        lines.append("")
        for name, title, description in sorted(root_entries):
            suffix = f" - {description}" if description else ""
            lines.append(f"* [{title}]({name}){suffix}")
        lines.append("")
    for dir_rel in sorted(k for k in groups if k != "."):
        lines += [f"# {dir_rel}", "", f"* [{dir_rel}/]({dir_rel}/) - see that directory's index.md", ""]
    return "\n".join(lines)


def build_log() -> str | None:
    """The root log.md (OKF §9): transcribes only the **heading layer** of the changelog; bodies stay home."""
    changelog = MAIN / CHANGELOG_REL
    if not changelog.is_file():
        return None
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for date, title in CHANGELOG_HEADING_RE.findall(read(changelog))[:LOG_ENTRY_LIMIT]:
        if date not in grouped:
            grouped[date] = []
            order.append(date)
        grouped[date].append(title)
    if not order:
        return None
    lines = ["# T2AG Update Log", ""]
    for date in order:
        lines.append(f"## {date}")
        for title in grouped[date]:
            lines.append(f"* **Update**: {title}")
        lines.append("")
    return "\n".join(lines)


def render_bundle(scope: str) -> tuple[dict[str, str], list[str]]:
    """Render the whole bundle into memory. Every check before disk runs on this artifact."""
    items, errors = collect_sources(scope)
    if errors:
        return {}, errors
    if not items:
        return {}, [f"scope `{scope}` has no exportable files"]

    known = {rel for _, rel, _ in items}
    by_name = basename_index(known)
    files: dict[str, str] = {}
    groups: dict[str, list[tuple[str, str, str | None]]] = {}

    for path, bundle_rel, injected in items:
        text, title, description = render_concept(path, bundle_rel, injected, known, by_name)
        files[bundle_rel] = text
        dir_rel = str(Path(bundle_rel).parent).replace("\\", "/")
        groups.setdefault(dir_rel, []).append((Path(bundle_rel).name, title, description))

    for dir_rel, entries in groups.items():
        if dir_rel == ".":
            continue  # root-level concepts are collected by the root index.md
        readme = MAIN / dir_rel / "_README.md"
        files[f"{dir_rel}/index.md"] = build_directory_index(dir_rel, entries, readme)

    files["index.md"] = build_root_index(scope, groups)
    log = build_log()
    if log:
        files["log.md"] = log
    return files, []


# --------------------------------------------------------------------------- checks


def leak_findings(files: dict[str, str]) -> list[str]:
    """The leak gate (playbook §5). A hit cannot be waived: the correct response is to fix the main library."""
    findings: list[str] = []
    for pattern, label in privacy_patterns():
        compiled = re.compile(pattern)
        for rel, text in sorted(files.items()):
            if compiled.search(text):
                findings.append(f"personal information leak: {rel} -> {label}")
    return findings


def conformance_findings(files: dict[str, str]) -> list[str]:
    """The three hard conditions of OKF §11 plus index/log structure (§8/§9)."""
    findings: list[str] = []
    for rel, text in sorted(files.items()):
        name = Path(rel).name
        if name in RESERVED_NAMES:
            if name == "index.md":
                front, _ = split_frontmatter(text)
                if rel == "index.md":
                    if not front or set(front) != {"okf_version"}:
                        findings.append("the root index.md frontmatter may contain only okf_version")
                elif front is not None:
                    findings.append(f"a non-root index.md must not carry frontmatter: {rel}")
            else:
                for line in text.splitlines():
                    if line.startswith("## ") and not ISO_DATE_RE.match(line[3:].strip()):
                        findings.append(f"log.md date heading is not ISO 8601: {rel} -> {line.strip()}")
            continue
        front, _ = split_frontmatter(text)
        if front is None:
            findings.append(f"missing parsable YAML frontmatter: {rel}")
            continue
        if not str(front.get("type", "")).strip():
            findings.append(f"frontmatter lacks a non-empty type: {rel}")
    return findings


def load_bundle(path: Path) -> dict[str, str]:
    return {
        p.relative_to(path).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(path.rglob("*.md"))
    }


# --------------------------------------------------------------------------- writing


def validate_out_dir(out: Path) -> list[str]:
    """Admission check on the target directory before `--write` touches disk (EV-0024 P0-3).

    `write_bundle()` deletes any `.md` in the target that is not in the manifest. Before
    this function existed `--out` was a bare `Path` with no repo-boundary validation, so one
    typo (say `--write --out main/50_playbook`) would recursively delete every markdown file
    there that was not in this export. The independent review listed it as a high-risk write
    path able to destroy the main library; this function is that finding's machine landing.

    Reject cases:
    1. the repo root, `main/`, the workspace root, and any of their ancestors;
    2. any subdirectory inside the main library or the Skeleton (an ancestor holding `.git`,
       or anything under ROOT);
    3. an existing, non-empty directory **without** a `BUNDLE_MARKER` file -- "not a bundle
       I wrote last time" means do not touch it.
    """
    errors: list[str] = []
    try:
        target = out.resolve()
    except OSError as error:
        return [f"--out cannot be resolved: {out} ({error.strerror})"]

    root = ROOT.resolve()
    forbidden = {root, MAIN.resolve(), root.parent}
    if target in forbidden or target in root.parents or target in root.parent.parents:
        return [f"--out points at the repo root / main library / workspace root; refusing: {target}"]
    if root == target or root in target.parents:
        return [f"--out lands inside the repo ({root}); a bundle must be written outside: {target}"]
    if (target / ".git").exists() or any((p / ".git").exists() for p in target.parents if p != target.anchor):
        # Anything inside a git working tree is refused: Skeleton, Lite and foreign repos.
        if not (target / BUNDLE_MARKER).exists():
            errors.append(f"--out lands in a git working tree with no {BUNDLE_MARKER} marker; refusing: {target}")

    if target.exists():
        if not target.is_dir():
            errors.append(f"--out already exists and is not a directory: {target}")
        elif any(target.iterdir()) and not (target / BUNDLE_MARKER).exists():
            errors.append(
                f"--out is a non-empty existing directory with no {BUNDLE_MARKER} marker; refusing: {target}"
                f" (if it really is a bundle directory, create an empty {BUNDLE_MARKER} by hand and retry)"
            )
    return errors


def write_bundle(files: dict[str, str], out: Path) -> list[str]:
    """Call only after every check passed and `validate_out_dir()` passed. Returns fatal errors.

    Delete before writing, so a concept from a previous export cannot linger in the bundle
    and pose as current knowledge after the scope narrowed.

    Three hard constraints after EV-0024 P0-2/P0-4:
    - every write target must resolve strictly inside `out` (guards against a `..` in rel);
    - an undeletable stale file **returns an error** rather than a WARN -- the original only
      WARNed and still exited 0, so old leaked material could stay in the delivery directory
      while the caller could not tell delivery had failed;
    - the post-write scan covers the **whole delivery directory** (not just `.md`) and
      reports anything outside the manifest.
    """
    errors: list[str] = []
    out.mkdir(parents=True, exist_ok=True)
    marker = out / BUNDLE_MARKER
    if not marker.exists():
        marker.write_text(
            "T2AG OKF bundle directory marker (generated by okf_export.py). Deleting it makes the next --write refuse.\n",
            encoding="utf-8",
        )

    out_resolved = out.resolve()
    for stale in sorted(out.rglob("*.md"), reverse=True):
        if stale.relative_to(out).as_posix() in files:
            continue  # about to be rewritten; no need to delete first
        try:
            stale.unlink()
        except OSError as error:
            errors.append(f"stale file could not be deleted: {stale} ({error.strerror})")
    if errors:
        return errors  # if it cannot be cleaned, do not write: a half-old bundle is worse than none

    for rel, text in sorted(files.items()):
        target = out / rel
        try:
            resolved = target.resolve()
        except OSError as error:
            errors.append(f"write path cannot be resolved: {rel} ({error.strerror})")
            continue
        if resolved != out_resolved and out_resolved not in resolved.parents:
            errors.append(f"write path escapes the delivery directory; refusing: {rel} -> {resolved}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    if errors:
        return errors

    # P0-4 post-write scan: not limited to .md; anything outside the manifest is reported.
    expected = set(files) | {BUNDLE_MARKER}
    for item in sorted(out.rglob("*")):
        if item.is_dir():
            continue
        rel = item.relative_to(out).as_posix()
        if rel not in expected:
            errors.append(f"delivery directory contains a file outside the manifest: {rel}")
    return errors


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T2AG -> OKF v0.2 exporter (protocol T2AG-OKF-1)")
    parser.add_argument("--scope", default="mechanism", help="mechanism (default) or course:<COURSE_ID>")
    parser.add_argument("--write", action="store_true", help="write to disk after all checks pass; default check-only")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output directory (default {DEFAULT_OUT.name}/)")
    parser.add_argument("--check-bundle", type=Path, help="recompute conformance and leak checks for an existing bundle")
    args = parser.parse_args(argv)

    if args.check_bundle:
        target = args.check_bundle
        if not target.is_dir():
            print(f"FAIL bundle directory does not exist: {target}")
            return 1
        files = load_bundle(target)
        if not files:
            print(f"FAIL no markdown files inside the bundle: {target}")
            return 1
        findings = conformance_findings(files) + leak_findings(files)
        for item in findings:
            print(f"FAIL {item}")
        print(f"{'FAIL' if findings else 'OK  '} check-bundle: {len(files)} files, {len(findings)} findings")
        return 1 if findings else 0

    files, errors = render_bundle(args.scope)
    for item in errors:
        print(f"FAIL {item}")
    if errors:
        return 1

    findings = conformance_findings(files) + leak_findings(files)
    for item in findings:
        print(f"FAIL {item}")
    if findings:
        print(f"FAIL rendered {len(files)} files, {len(findings)} findings; per the gate convention nothing was written")
        return 1

    concepts = sum(1 for rel in files if Path(rel).name not in RESERVED_NAMES)
    print(f"OK   scope={args.scope} | concepts {concepts} | {len(files)} files total | leaks 0 | conformance 0 FAIL")
    if args.write:
        # P0-3: the admission check runs before any delete or write. It is how "the gate
        # comes before disk and cannot be waived" lands on the **target directory** -- the
        # original put the gate on the content only, never on the landing point.
        gate = validate_out_dir(args.out)
        for item in gate:
            print(f"FAIL {item}")
        if gate:
            print("FAIL --out failed the delivery-directory admission check; zero deletes, zero writes")
            return 1
        write_errors = write_bundle(files, args.out)
        for item in write_errors:
            print(f"FAIL {item}")
        if write_errors:
            print(f"FAIL delivery incomplete: {args.out} ({len(write_errors)} errors)")
            return 1
        print(f"OK   wrote {args.out}")
    else:
        print("INFO check-only: nothing written. Add --write to generate the bundle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
