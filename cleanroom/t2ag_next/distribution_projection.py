"""Owned, recoverable projections and optional OKF 0.2 structural conformance.

These outputs never become an authoritative learning instance. Ownership marks
are accident-prevention conventions, not permissions against a same-user writer.
A cooperative OS lock serializes this API. Directory replacement needs two
renames, so observers can briefly see no target. Faults retain old and new bytes;
receipts support explicit recovery. Windows has file fsync but no directory
fsync here; no claim of tested power-loss durability or hostile-race isolation.
PyYAML is required only for OKF operations; no ad-hoc parser substitutes for it.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
from urllib.parse import unquote, urlsplit
import uuid

from . import __version__
from . import distribution as base
from .model import DomainError, require, parse_json

OWNER = ".t2ag-projection.json"
OKF_MARK = ".t2ag-okf-bundle"
SCHEMA = "t2ag.projection.v1"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _inventory(files):
    return {name: {"sha256": _sha(data), "bytes": len(data)} for name, data in sorted(files.items())}


def _plain(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        # lexists detects dangling links too; resolve() would erase that evidence.
        if os.path.lexists(item):
            stat = item.lstat()
            require(not item.is_symlink() and not (getattr(stat, "st_file_attributes", 0) & 0x400),
                    "PROJECTION_LINK", "Projection paths cannot traverse links or reparse points.")
    return path


def _target(destination, source=None):
    target = _plain(destination)
    require(target.parent.is_dir() and target != target.parent, "PROJECTION_PARENT", "Choose an existing external parent.")
    base._safe_name(target.name)
    require(not target.exists() or target.is_dir(), "PROJECTION_TARGET", "The target must be a directory.")
    if source is not None:
        root = _plain(source)
        require(target != root and root not in target.parents and target not in root.parents,
                "DESTINATION_OVERLAP", "The projection must be outside its source and its ancestors.")
    return target


def _tree(root):
    root = _plain(root)
    if not root.exists():
        return {}, set()
    require(root.is_dir(), "PROJECTION_TARGET", "Expected a plain directory.")
    files, dirs = {}, set()
    for parent, directories, names in os.walk(root, followlinks=False):
        for name in directories:
            path = _plain(Path(parent) / name)
            dirs.add(path.relative_to(root).as_posix())
        for name in names:
            path = _plain(Path(parent) / name)
            require(path.is_file(), "PROJECTION_SPECIAL_FILE", "Special files are outside projection scope.")
            relative = path.relative_to(root).as_posix()
            base._safe_name(relative)
            files[relative] = path.read_bytes()
    return files, dirs


def _expected_dirs(names):
    return {str(parent) for name in names for parent in PurePosixPath(name).parents if str(parent) != "."}


def _owned(files, dirs, kind=None):
    require(OWNER in files, "PROJECTION_NOT_OWNED", "Existing targets require this tool's ownership manifest.")
    owner = parse_json(files[OWNER])
    require(isinstance(owner, dict) and owner.get("schema") == SCHEMA and owner.get("kind") in {"lite", "okf"}
            and isinstance(owner.get("generation_id"), str) and isinstance(owner.get("files"), dict),
            "PROJECTION_MANIFEST", "Invalid projection ownership manifest.")
    require(kind is None or owner["kind"] == kind, "PROJECTION_KIND", "Do not replace a different projection kind.")
    expected = owner["files"]
    require(set(files) == set(expected) | {OWNER} and dirs == _expected_dirs(files),
            "PROJECTION_INVENTORY", "Unknown, missing or unmanifested target entries prevent replacement.")
    for name in expected:
        base._safe_name(name)
    require(_inventory({name: files[name] for name in expected}) == expected,
            "PROJECTION_DRIFT", "Owned target bytes changed; preserve and reconcile them before replacement.")
    if owner["kind"] == "okf":
        require(files.get(OKF_MARK) == b"t2ag.okf.projection.v1\n", "PROJECTION_NOT_OWNED", "The OKF ownership marker is required.")
    return owner


def _sync_dir(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _write_file(path, data):
    _plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _receipt(path, value, *, first=False):
    _plain(path)
    if first:
        _write_file(path, _json(value))
    else:
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        _write_file(temporary, _json(value))
        os.replace(temporary, path)
    _sync_dir(path.parent)


@contextmanager
def _lock(target):
    path = _plain(target.parent / (".t2ag-projection-lock-" + _sha(str(target).casefold().encode())[:20]))
    stream = path.open("a+b")
    locked = False
    try:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise DomainError("PROJECTION_BUSY", "Another projection operation holds the OS lock.") from exc
        yield
    finally:
        if locked:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def _fault(point):
    """Private fault-injection seam, never selected by a public request."""


def _diff(current, wanted):
    return {"missing": sorted(set(wanted) - set(current)),
            "different": sorted(name for name in wanted.keys() & current.keys() if wanted[name] != current[name]),
            "orphan": sorted(set(current) - set(wanted) - {OWNER})}


def _publish(root, target, files, kind, supplier):
    """Preserve whole generations; never recursively remove files or directories."""
    with _lock(target):
        target = _target(target, root)
        before, directories = _tree(target)
        existed = target.exists()
        if existed:
            _owned(before, directories, kind)
        generation = uuid.uuid4().hex
        owner = {"schema": SCHEMA, "kind": kind, "generation_id": generation, "authority": False,
                 "reverse_sync": False, "files": _inventory(files)}
        after = {**files, OWNER: _json(owner)}
        stage = target.parent / (".t2ag-projection-stage-" + generation)
        backup = target.parent / (".t2ag-projection-backup-" + generation)
        displaced = target.parent / (".t2ag-projection-displaced-" + generation)
        receipt_path = target.parent / (".t2ag-projection-transaction-" + generation + ".json")
        stage.mkdir()
        for name, data in after.items():
            _write_file(stage.joinpath(*base._safe_name(name).parts), data)
        for directory in sorted(_expected_dirs(after), key=lambda x: x.count("/"), reverse=True):
            _sync_dir(stage / directory)
        _sync_dir(stage); _sync_dir(stage.parent)
        receipt = {"schema": "t2ag.projection.transaction.v1", "generation_id": generation, "kind": kind,
                   "target": target.name, "stage": stage.name, "backup": backup.name, "displaced": displaced.name,
                   "had_previous": existed, "before": _inventory(before), "after": _inventory(after), "phase": "prepared"}
        _receipt(receipt_path, receipt, first=True)
        moved_old = installed = False
        try:
            _fault("after_stage")
            require(supplier() == files, "PROJECTION_SOURCE_DRIFT", "Source changed while preparing; retained stage is not published.")
            _fault("before_publish")
            require(_tree(target) == (before, directories) and target.exists() == existed,
                    "PROJECTION_TARGET_DRIFT", "Target changed after the checked snapshot.")
            require(_tree(stage)[0] == after, "PROJECTION_STAGE_DRIFT", "The checked staging bytes changed.")
            _target(target, root)
            if existed:
                require(not backup.exists(), "PROJECTION_RECOVERY_COLLISION", "Backup destination appeared.")
                os.rename(target, backup); moved_old = True; _sync_dir(target.parent)
                receipt["phase"] = "old_saved"; _receipt(receipt_path, receipt)
            _fault("after_backup")
            require(not target.exists(), "PROJECTION_TARGET_DRIFT", "A target appeared before publication.")
            os.rename(stage, target); installed = True; _sync_dir(target.parent)
            _fault("after_publish")
            require(_tree(target)[0] == after, "PROJECTION_TARGET_DRIFT", "Published bytes changed before acknowledgement.")
            receipt["phase"] = "published"; _receipt(receipt_path, receipt)
        except Exception as exc:
            # Preserve a concurrent writer's changes; in that case require explicit
            # reconciliation instead of claiming automatic recovery succeeded.
            try:
                if installed:
                    require(_tree(target)[0] == after and not displaced.exists(), "PROJECTION_RECOVERY_REQUIRED", "Changed published target needs manual reconciliation.")
                    os.rename(target, displaced)
                if moved_old:
                    require(not target.exists() and _tree(backup)[0] == before,
                            "PROJECTION_RECOVERY_REQUIRED", "Preserved prior generation needs manual reconciliation.")
                    os.rename(backup, target)
                _sync_dir(target.parent)
                receipt["phase"] = "failed_previous_restored" if existed and moved_old else "failed"
                _receipt(receipt_path, receipt)
            except Exception as recovery_error:
                raise DomainError("PROJECTION_RECOVERY_REQUIRED", "No success acknowledged; generations and receipt are retained.",
                                  {"receipt": str(receipt_path), "cause": str(exc), "recovery": str(recovery_error)}) from exc
            raise
        return {"receipt": str(receipt_path), "backup": str(backup) if existed else None,
                "generation_id": generation, "durability": "file_fsync_directory_rename_windows_directory_fsync_unavailable" if os.name == "nt" else "file_and_directory_fsync"}


def _project(root, destination, files, kind, supplier, write):
    target = _target(destination, root)
    current, directories = _tree(target)
    result = {"ok": True, "written": False, "authority": False, **_diff(current, files)}
    if target.exists():
        try:
            _owned(current, directories, kind)
            result["ownership"] = "verified"
        except DomainError as exc:
            result["ownership"] = exc.code
            if write:
                raise
    else:
        result["ownership"] = "new_destination"
    if write:
        result.update(_publish(root, target, files, kind, supplier), written=True)
    return result


def rollback_projection(destination, receipt_path, *, write=False):
    """Undo a successful publication or restore its interrupted two-rename swap.

    Default is a read-only plan. Exact tree inventories must match the receipt;
    a later generation or unrelated files are never overwritten. Newer bytes are
    moved to a retained sibling, not deleted. Receipts are assertions, not secrets.
    """
    target = _target(destination)
    receipt_path = _plain(receipt_path)
    require(receipt_path.parent == target.parent and receipt_path.is_file(), "PROJECTION_RECEIPT", "Use the sibling transaction receipt.")
    receipt = parse_json(receipt_path.read_bytes())
    require(isinstance(receipt, dict) and receipt.get("schema") == "t2ag.projection.transaction.v1"
            and receipt.get("target") == target.name and re.fullmatch(r"[a-f0-9]{32}", str(receipt.get("generation_id", ""))),
            "PROJECTION_RECEIPT", "Receipt does not bind this projection target.")
    generation = receipt["generation_id"]
    for field in ("stage", "backup", "displaced"):
        require(receipt.get(field) == f".t2ag-projection-{field}-{generation}", "PROJECTION_RECEIPT", "Unsafe recovery path.")
    require(receipt_path.name == f".t2ag-projection-transaction-{generation}.json", "PROJECTION_RECEIPT", "Receipt name is not bound to generation.")
    backup = _plain(target.parent / receipt["backup"])
    displaced = _plain(target.parent / receipt["displaced"])

    def checked():
        current, dirs = _tree(target)
        if target.exists():
            _owned(current, dirs, receipt["kind"])
            require(_inventory(current) == receipt["after"], "PROJECTION_ROLLBACK_STALE", "Target advanced or changed after this publication.")
        if receipt["had_previous"]:
            old, old_dirs = _tree(backup)
            _owned(old, old_dirs, receipt["kind"])
            require(_inventory(old) == receipt["before"], "PROJECTION_BACKUP_DRIFT", "The saved generation no longer matches the receipt.")
        else:
            require(target.exists(), "PROJECTION_ROLLBACK_EMPTY", "No published generation remains to undo.")
        require(not displaced.exists(), "PROJECTION_RECOVERY_COLLISION", "The retained-new-generation destination already exists.")
        return current

    checked()
    result = {"ok": True, "written": False, "restore_previous": receipt["had_previous"], "retained_new": str(displaced), "authority": False}
    if write:
        with _lock(target):
            current = checked()
            if target.exists():
                os.rename(target, displaced)
            try:
                if receipt["had_previous"]:
                    os.rename(backup, target)
            except Exception:
                if current and not target.exists():
                    os.rename(displaced, target)
                raise
            _sync_dir(target.parent)
            receipt["phase"] = "rolled_back"; _receipt(receipt_path, receipt)
            result["written"] = True
    return result


def lite_projection(root, destination, *, write=False, forbidden_terms=()):
    root = base._plain_source(root, root)

    def build():
        files = base.source_files(root)
        files["READ_ONLY.json"] = _json({"authority": False, "mode": "source_inspection", "reverse_sync": False})
        base.privacy_check(files, forbidden_terms)
        return files

    files = build()
    return _project(root, destination, files, "lite", build, write)


def _yaml():
    try:
        import yaml
    except ImportError as exc:
        raise DomainError("OKF_DEPENDENCY_REQUIRED", "OKF conformance requires the optional PyYAML parser; install the okf extra.") from exc
    return yaml


def _frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    match = re.search(r"(?m)^---\s*$", text[4:])
    require(match is not None, "OKF_FRONTMATTER", "Unclosed YAML frontmatter.")
    raw = text[4:4 + match.start()]
    yaml = _yaml()
    try:
        metadata = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise DomainError("OKF_FRONTMATTER", "Frontmatter is not parseable YAML.") from exc
    require(isinstance(metadata, dict), "OKF_FRONTMATTER", "Frontmatter must be a YAML mapping.")
    return metadata, text[4 + match.end():].lstrip("\n")


def _decode(data):
    try:
        return data.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise DomainError("OKF_ENCODING", "Markdown concepts must be UTF-8.") from exc


def _conformance(files):
    _yaml()  # No successful check when the parser is unavailable.
    concepts, reserved = [], []
    for name, data in files.items():
        if not name.endswith(".md"):
            continue
        metadata, body = _frontmatter(_decode(data))
        filename = PurePosixPath(name).name
        if filename == "index.md":
            require(metadata is None or (name == "index.md" and set(metadata) <= {"okf_version"}),
                    "OKF_INDEX", "Only the root index may carry an okf_version-only frontmatter.")
            lines = [line for line in body.splitlines() if line.strip()]
            require(lines and re.fullmatch(r"#{1,6} +\S.*", lines[0]), "OKF_INDEX", "An index needs heading sections.")
            for line in lines:
                require(re.fullmatch(r"#{1,6} +\S.*", line) or re.fullmatch(r"[-*+] +\[[^\]]+\]\([^)]+\)(?:\s+.*)?", line),
                        "OKF_INDEX", "Index sections contain flat Markdown link entries.")
            reserved.append(name)
        elif filename == "log.md":
            require(metadata is None, "OKF_LOG", "Log files do not carry frontmatter.")
            lines = [line for line in body.splitlines() if line.strip()]
            require(lines and re.fullmatch(r"# +\S.*", lines[0]), "OKF_LOG", "A log needs a title.")
            dates = []
            for line in lines[1:]:
                if line.startswith("#"):
                    require(re.fullmatch(r"## \d{4}-\d{2}-\d{2}", line), "OKF_LOG", "Log groups must be ISO dates.")
                    try:
                        datetime.strptime(line[3:], "%Y-%m-%d")
                    except ValueError as exc:
                        raise DomainError("OKF_LOG", "Invalid calendar date in log.") from exc
                    dates.append(line[3:])
                else:
                    require(bool(dates), "OKF_LOG", "Log prose must belong to a dated group.")
            require(dates == sorted(dates, reverse=True), "OKF_LOG", "Log groups must be newest first.")
            reserved.append(name)
        else:
            require(metadata is not None and isinstance(metadata.get("type"), str) and bool(metadata["type"].strip()),
                    "OKF_TYPE", "Each concept needs a nonempty type.")
            concepts.append(name)
    return {"ok": True, "okf_version": "0.2", "concepts": sorted(concepts), "reserved": sorted(reserved),
            "scope": "structural_conformance_and_privacy", "epistemic_verification": False}


def _resolve_link(name, link, names, *, basename=False):
    parsed = urlsplit(link)
    if parsed.scheme or parsed.netloc or not parsed.path or "<" in link or ">" in link:
        return None
    path = unquote(parsed.path)
    if "\\" in path:
        return None
    resolved = posixpath.normpath(path.lstrip("/") if path.startswith("/") else posixpath.join(posixpath.dirname(name), path))
    if resolved in names:
        return resolved
    if basename and "/" not in path:
        matches = [item for item in names if PurePosixPath(item).name == path]
        return matches[0] if len(matches) == 1 else None
    return None


def _outside_fences(body, transform):
    result, fence = [], None
    for line in body.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[marker.end():].strip():
                fence = None
            result.append(line)
        else:
            result.append(transform(line) if fence is None and not line.startswith(("    ", "\t")) else line)
    return "".join(result)


_MD_LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\s]+)\)")


def _rewrite(name, body, names):
    seen = set()

    def transform(line):
        code_spans = [(match.start(), match.end()) for match in re.finditer(r"(`+).*?\1", line)]

        def standard(match):
            if any(start <= match.start() < end for start, end in code_spans):
                return match[0]
            target = _resolve_link(name, match[2], names)
            if target is None:
                return match[0]
            parsed = urlsplit(match[2])
            suffix = ("?" + parsed.query if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")
            return f"[{match[1]}](/{target}{suffix})"

        line = _MD_LINK.sub(standard, line)

        def inline(match):
            token = match[1]
            if not token.endswith(".md") or token.startswith("-") or re.search(r"[\s\"'<>|;&$(){}\\]", token):
                return match[0]
            target = _resolve_link(name, token, names, basename=True)
            if target is None or target in seen:
                return match[0]
            seen.add(target)
            return f"[{token}](/{target})"

        # Avoid nested code-link labels and multi-backtick code spans.
        parts = re.split(r"(\[[^\]\n]+\]\([^)]+\))", line)
        return "".join(part if index % 2 else re.sub(r"(?<!`)`([^`\n]+)`(?!`)", inline, part) for index, part in enumerate(parts))

    return _outside_fences(body, transform)


def _edges(files):
    edges = set()
    names = set(files)
    for name, data in files.items():
        if not name.endswith(".md"):
            continue
        _, body = _frontmatter(_decode(data))

        def collect(line):
            # Inline literal code is not a Markdown relationship.
            line = re.sub(r"`+[^`]*`+", "", line)
            for match in _MD_LINK.finditer(line):
                target = _resolve_link(name, match[2], names)
                if target is not None:
                    edges.add((name, target))
            return line

        _outside_fences(body, collect)
    return [{"from": source, "to": target} for source, target in sorted(edges)]


def check_bundle(path, *, forbidden_terms=()):
    files, dirs = _tree(path)
    require(Path(path).is_dir(), "OKF_BUNDLE", "Bundle path must exist.")
    result = _conformance(files)
    base.privacy_check(files, forbidden_terms)
    if "manifest.json" in files:
        manifest = parse_json(files["manifest.json"])
        require(isinstance(manifest, dict) and manifest.get("schema") == "t2ag.okf.manifest.v1", "OKF_MANIFEST", "Unknown exporter manifest.")
        payload = {name: data for name, data in files.items() if name not in {OWNER, "manifest.json"}}
        require(manifest.get("files") == _inventory(payload) and manifest.get("edges") == _edges(payload),
                "OKF_MANIFEST", "Recomputed bytes or graph differ from the export manifest.")
    if OWNER in files:
        _owned(files, dirs, "okf")
    return {**result, "privacy": "checked", "edges": _edges(files), "manifest_checked": "manifest.json" in files}


def _source_time(root, name):
    path = base._plain_source(root / name, root)
    if (root / ".git").exists():
        try:
            run = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%cI", "--", name],
                                 capture_output=True, text=True, timeout=5)
            if run.returncode == 0 and run.stdout.strip():
                value = datetime.fromisoformat(run.stdout.strip())
                if value.tzinfo is not None:
                    return value.astimezone(timezone.utc).isoformat(), "git_last_commit"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(), "source_mtime"


def _title_description(body, fallback):
    heading = re.search(r"(?m)^# +(.+?)\s*$", body)
    title = heading[1] if heading else fallback
    tail = body[heading.end():] if heading else body
    prose = next((line.strip() for line in tail.splitlines() if line.strip() and not line.lstrip().startswith(("#", "```", "~~~", "|", ">"))), "")
    sentence = re.split(r"(?<=[.!?。！？])(?:\s+|$)", prose, maxsplit=1)[0]
    return title, sentence


def _okf_files(root, course_definition, forbidden_terms):
    yaml = _yaml()
    timestamps = {}
    if course_definition is not None:
        require(isinstance(course_definition, dict) and set(course_definition) <= {"id", "title", "course_type", "learning_mode", "goal"}
                and isinstance(course_definition.get("id"), str) and bool(course_definition["id"].strip()),
                "OKF_SCOPE", "Explicit course definitions only; no history or personal fields.")
        require(all(value is None or isinstance(value, str) for value in course_definition.values()), "OKF_SCOPE", "Course definition fields must be scalar text.")
        document = "# " + course_definition.get("title", course_definition["id"]) + "\n\n" + str(course_definition.get("goal") or "Course definition.") + "\n\n```json\n" + _json(course_definition).decode() + "```\n"
        documents = {"course.md": document}
        scope = "course:" + course_definition["id"]
    else:
        documents = {name: _decode(base._plain_source(root / name, root).read_bytes()) for name in base.PUBLIC_DOCS if name != "README.md"}
        timestamps = {name: _source_time(root, name) for name in documents}
        scope = "mechanism"
    files, descriptions, titles = {}, {}, {}
    for name, document in documents.items():
        metadata, body = _frontmatter(document)
        metadata = metadata or {}
        kind = metadata.get("type", "course" if course_definition is not None else "Domain Model" if name == "docs/domain-model.md" else "Governance Doc" if name in {"docs/protocol.md", "docs/runtime-entry.md", "docs/control-boundaries.md"} else "Playbook")
        title, description = _title_description(body, PurePosixPath(name).stem)
        output_metadata = {"type": kind, "title": title, "description": description, "generated": {"by": "t2ag-next/" + __version__}}
        for field in ("status", "sources"):
            if field in metadata:
                output_metadata[field] = metadata[field]
        if name in timestamps:
            output_metadata["generated"]["at"] = timestamps[name][0]
        # Explicit course input is memory-only: no fabricated source timestamp.
        files[name] = ("---\n" + yaml.safe_dump(output_metadata, allow_unicode=True, sort_keys=False) + "---\n\n" + _rewrite(name, body, set(documents))).encode("utf-8")
        titles[name], descriptions[name] = title, description
    dirs = sorted({str(PurePosixPath(name).parent) for name in documents} - {"."})
    for directory in ["", *dirs]:
        names = sorted(name for name in documents if directory == "" or str(PurePosixPath(name).parent) == directory)
        prefix = "---\nokf_version: '0.2'\n---\n\n" if not directory else ""
        text = prefix + "# T2AG knowledge\n\n"
        for name in names:
            title = titles[name].replace("[", "(").replace("]", ")")
            text += f"- [{title}](/{name}) - {descriptions[name]}\n"
        files[(directory + "/" if directory else "") + "index.md"] = text.encode("utf-8")
    # Timestamp reflects source evidence, not an invented historical changelog.
    dates = sorted({stamp[0][:10] for stamp in timestamps.values()}, reverse=True)
    if dates:
        log = "# Update Log\n\n" + "\n".join("## " + date + "\n\nProjection source changes: " + ", ".join(titles[name] for name in documents if timestamps[name][0][:10] == date) + ".\n" for date in dates)
    else:
        log = "# Update Log\n"  # No dated source event was provided for memory-only course input.
    files["log.md"] = log.encode("utf-8")
    files[OKF_MARK] = b"t2ag.okf.projection.v1\n"
    _conformance(files)
    manifest = {"schema": "t2ag.okf.manifest.v1", "okf_version": "0.2", "scope": scope, "files": _inventory(files),
                "edges": _edges(files), "generated_at_basis": {name: basis for name, (_, basis) in timestamps.items()},
                "course_timestamp": "not_available" if course_definition is not None else None, "epistemic_verification": False}
    files["manifest.json"] = _json(manifest)
    base.privacy_check(files, forbidden_terms)
    return files


def okf_export(root, destination=None, *, course_definition=None, forbidden_terms=(), write=False):
    root = base._plain_source(root, root)

    def build():
        return _okf_files(root, course_definition, forbidden_terms)

    files = build()
    result = {"ok": True, "written": False, "manifest": parse_json(files["manifest.json"]),
              "conformance": _conformance(files), "privacy": "checked_before_write", "authority": False}
    if destination is not None:
        result.update(_project(root, destination, files, "okf", build, write))
    else:
        require(not write, "DESTINATION_REQUIRED", "Choose an external output path.")
    return result
