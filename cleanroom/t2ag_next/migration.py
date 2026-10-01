"""Frozen, byte-preserving legacy exchange and conservative semantic import.

No legacy code is imported or executed. A package is a read-time snapshot, never
permission to teach, a current-session scan, or a replacement for a live source.
Unparsed evidence remains addressable and explicitly unresolved for cutover.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

from .model import DomainError, put, require

SCHEMA = "t2ag.legacy.exchange.v1"
CHUNK = 1024 * 1024
EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _fault(point, context=None):
    """Internal test seam. Never exposed in a migration request or CLI."""


def _linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _plain_ancestors(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            require(not _linked(part), "UNSAFE_PATH", f"Linked/reparse path is not accepted: {part}")
    return path.resolve()


def _relative(value):
    require(isinstance(value, str) and bool(value), "UNSAFE_PATH", "Expected nonempty relative path.")
    parts = value.split("/")
    require(not value.startswith("/") and "\\" not in value and all(
        p and p not in {".", ".."} and not p.endswith((".", " "))
        and not any(ord(c) < 32 or c in '<>:"|?*' for c in p)
        and p.split(".")[0].upper() not in RESERVED for p in parts),
        "UNSAFE_PATH", f"Unsafe or nonportable package path: {value!r}")
    return PurePosixPath(value)


def _hash_file(path):
    require(not _linked(path), "UNSAFE_PATH", "A source file is a link or reparse point.")
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), "UNSUPPORTED_FILE", "Only regular file bytes can be packaged.")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
            size += len(chunk)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns, before.st_ino) ==
            (after.st_size, after.st_mtime_ns, after.st_ino) and size == after.st_size,
            "SOURCE_DRIFT", f"Source changed while reading: {path.name}")
    return {"bytes": size, "sha256": digest.hexdigest()}


def _classification(relative):
    p = relative.lower()
    if any(x in p.split("/") for x in (".staging", ".recovery", ".uploads", ".activity_txn")):
        return "recovery_or_pending_input"
    if "/.cache/" in f"/{p}/":
        return "derived_cache"
    if "/70_tools/" in f"/{p}/" or p.endswith((".py", ".ps1", ".exe", ".cmd", ".sh")):
        return "legacy_implementation_archive"
    if "/book/" in f"/{p}/" or p.endswith((".pdf", ".epub", ".png", ".jpg", ".jpeg", ".webp")):
        return "source_or_attachment"
    if "receipt" in p or "authorization" in p or "gate" in p or "/preparation/" in p:
        return "historical_evidence_not_permission"
    if p.endswith(("course.md", "progress.md", "activity_ledger.md")):
        return "authority"
    if "/profile/" in f"/{p}/" or "/20_teacher/" in f"/{p}/":
        return "configuration"
    if "/50_playbook/" in f"/{p}/" or "/00_core/" in f"/{p}/":
        return "rule_or_history_evidence"
    return "retained_unclassified"


def _inventory(root):
    rows, excluded, seen = [], [], set()

    def walk(directory):
        for path in sorted(directory.iterdir(), key=lambda p: p.name):
            relative = path.relative_to(root).as_posix()
            _relative(relative)
            folded = relative.casefold()
            require(folded not in seen, "PATH_COLLISION", "Case-colliding legacy paths require explicit mapping.")
            seen.add(folded)
            if path.name in EXCLUDED_DIRS and path.is_dir():
                excluded.append({"path": relative, "reason": "runtime_or_repository_environment",
                                 "retention": "left_unchanged_at_source_not_authority"})
                continue
            require(not _linked(path), "UNSAFE_PATH", f"Linked/reparse source requires explicit mapping: {relative}")
            if path.is_dir():
                walk(path)
            else:
                rows.append({"path": relative, **_hash_file(path),
                             "classification": _classification(relative)})
    walk(root)
    return {"files": rows, "exclusions": excluded}


def _new_target(path, source=None):
    path = _plain_ancestors(path)
    if source is not None:
        require(not path.is_relative_to(source) and not source.is_relative_to(path),
                "OVERLAPPING_ROOTS", "Source and destination trees must not overlap.")
    require(not path.exists() or (path.is_dir() and not any(path.iterdir())),
            "DESTINATION_NOT_EMPTY", "Migration will not overwrite an existing instance/package.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _json_write(path, value):
    with path.open("xb") as stream:
        stream.write(_canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def _publish(stage, destination):
    # A competing publisher must not be silently overwritten. On POSIX rename
    # can replace an empty directory only; never overwrite a populated one.
    if destination.exists():
        require(destination.is_dir() and not any(destination.iterdir()),
                "DESTINATION_NOT_EMPTY", "Destination changed while building migration.")
        destination.rmdir()
    stage.rename(destination)
    if os.name != "nt":
        fd = os.open(str(destination.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def export_legacy(source_root, package_dir):
    source = _plain_ancestors(source_root)
    require(source.is_dir(), "SOURCE_NOT_FOUND", "Legacy root is not a directory.")
    target = _new_target(package_dir, source)
    started = _utc()
    before = _inventory(source)
    require(bool(before["files"]), "EMPTY_SOURCE", "An empty snapshot is not a usable migration.")
    stage = Path(tempfile.mkdtemp(prefix=".t2ag-export-", dir=target.parent))
    _fault("after_inventory", {"source": source, "stage": stage})
    for row in before["files"]:
        original = source / row["path"]
        dest = stage / "originals" / row["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        require(not _linked(original), "SOURCE_DRIFT", "Source became a link during export.")
        sha, count = hashlib.sha256(), 0
        with original.open("rb") as reader, dest.open("xb") as writer:
            for chunk in iter(lambda: reader.read(CHUNK), b""):
                writer.write(chunk)
                sha.update(chunk)
                count += len(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        require((sha.hexdigest(), count) == (row["sha256"], row["bytes"]),
                "SOURCE_DRIFT", f"Source changed while exporting: {row['path']}")
    _fault("before_source_recheck", {"source": source, "stage": stage})
    require(before == _inventory(source), "SOURCE_DRIFT", "Source changed during export; take a fresh snapshot.")
    identity = {"schema": SCHEMA, "source_namespace": _digest({"legacy_root": str(source)}), **before}
    manifest = {**identity, "snapshot_id": _digest(identity), "source_root_hint": str(source),
                "read_started_utc": started, "read_finished_utc": _utc(),
                "scope": "regular bytes; environment exclusions inventoried; no ACL/mtime preservation",
                "session_scan_valid": False, "historical_permissions_active": False}
    _json_write(stage / "manifest.json", manifest)
    verify_package(stage)
    _fault("before_package_publish", {"stage": stage})
    _publish(stage, target)
    return {"ok": True, "package": str(target), "snapshot_id": manifest["snapshot_id"],
            "files": len(before["files"]), "bytes": sum(r["bytes"] for r in before["files"])}


def verify_package(package_dir):
    package = _plain_ancestors(package_dir)
    manifest_path = package / "manifest.json"
    require(manifest_path.is_file() and not _linked(manifest_path), "INVALID_PACKAGE", "Missing regular manifest.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise DomainError("INVALID_PACKAGE", "Manifest is not valid UTF-8 JSON.") from exc
    require(isinstance(manifest, dict) and manifest.get("schema") == SCHEMA,
            "INVALID_PACKAGE", "Unknown exchange schema.")
    require(isinstance(manifest.get("files"), list) and bool(manifest["files"])
            and isinstance(manifest.get("exclusions"), list)
            and isinstance(manifest.get("source_namespace"), str), "INVALID_PACKAGE", "Incomplete manifest.")
    identity = {k: manifest[k] for k in ("schema", "source_namespace", "files", "exclusions")}
    require(_digest(identity) == manifest.get("snapshot_id"), "PACKAGE_ID_MISMATCH", "Snapshot identity does not bind its content.")
    seen = set()
    for row in manifest["files"]:
        require(isinstance(row, dict), "INVALID_PACKAGE", "Invalid file entry.")
        relative = str(_relative(row.get("path")))
        require(relative.casefold() not in seen, "PATH_COLLISION", "Repeated or case-colliding package path.")
        seen.add(relative.casefold())
        require(type(row.get("bytes")) is int and row["bytes"] >= 0 and
                isinstance(row.get("sha256"), str) and re.fullmatch(r"[a-f0-9]{64}", row["sha256"]),
                "INVALID_PACKAGE", "Invalid byte count or digest.")
        path = _plain_ancestors(package / "originals" / relative)
        require(path.is_relative_to(package / "originals") and path.is_file(),
                "MISSING_ORIGINAL", f"Missing preserved original: {relative}")
        require(_hash_file(path) == {"bytes": row["bytes"], "sha256": row["sha256"]},
                "PACKAGE_BYTES_CHANGED", f"Original differs from manifest: {relative}")
    actual = _inventory(package / "originals")
    require(not actual["exclusions"] and {r["path"].casefold() for r in actual["files"]} == seen,
            "UNEXPECTED_PACKAGE_FILE", "Package contains uninventoried files/environment material.")
    return {"ok": True, "manifest": manifest, "files": len(seen),
            "bytes": sum(r["bytes"] for r in manifest["files"])}


def _scalar(value):
    value = value.strip()
    try:
        return json.loads(value)
    except ValueError:
        if value.startswith("[") and value.endswith("]"):
            return [_scalar(item) for item in value[1:-1].split(",") if item.strip()]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            return value[1:-1]
        return value


def _frontmatter(text):
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0] != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line == "---":
            break
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match:
            name, value = match.groups()
            require(name not in fields, "DUPLICATE_FIELD", f"Ambiguous duplicate frontmatter field: {name}")
            fields[name] = _scalar(value)
    return fields


def _tables(text):
    rows, header = [], None
    for line in _without_fences(text).splitlines():
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        if header is None:
            header = cells
        elif len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
    return rows


def _current_text(text):
    match = re.search(r"(?m)^##\s+[^\n]*(?:当前进度|Current progress)[^\n]*\n", text)
    if not match:
        return ""
    remainder = text[match.end():]
    return re.split(r"(?m)^##\s", remainder, maxsplit=1)[0].strip()


def _without_fences(text):
    """Retain line offsets while excluding illustrative record templates."""
    result, fence = [], None
    for line in text.splitlines(keepends=True):
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token[0]
            elif token[0] == fence:
                fence = None
            result.append(re.sub(r"[^\r\n]", " ", line))
        else:
            result.append(re.sub(r"[^\r\n]", " ", line) if fence else line)
    return "".join(result)


def _item_fields(text):
    result = {}
    for line in text.splitlines():
        match = re.match(r"^-\s+([^：:]+)[：:]\s*(.*)$", line)
        if match:
            result[match.group(1).strip("* ")] = match.group(2)
    return result


def _bullet(text, label):
    match = re.search(r"(?m)^-\s+\*\*" + re.escape(label) + r"\*\*[：:]\s*(.*(?:\n(?!- |##)[^\n]+)*)", text)
    return match.group(1).strip() if match else None


def _status(value, allowed=None):
    match = re.match(r"^[\s*`]*(ongoing|planned|pending_close|completed|closed_incomplete|paused|confirmed|pending|queued|arrived|archived)\b", str(value))
    result = match.group(1) if match else "unknown"
    return result if allowed is None or result in allowed else "unknown"


def _sections(body, pattern):
    """Named records only, excluding illustrative fenced templates."""
    masked = _without_fences(body)
    matches = list(re.finditer(r"(?m)^(#{2,4})\s+(" + pattern + r")[^\n]*\n", masked))
    for match in matches:
        level = len(match.group(1))
        end = re.search(r"(?m)^#{1," + str(level) + r"}\s", masked[match.end():])
        stop = match.end() + end.start() if end else len(body)
        yield match.group(2), body[match.end():stop], masked[:match.start()].count("\n") + 1


def _flat_yaml(body):
    return {m.group(1): _scalar(m.group(2)) for m in re.finditer(r"(?m)^([\w.]+):\s*([^\n]*)$", body)}


def _body_after_frontmatter(body):
    match = re.match(r"\ufeff?---\r?\n.*?\r?\n---(?:\r?\n)", body, re.S)
    return body[match.end():] if match else body


def _list_value(value):
    return value if isinstance(value, list) else []


def _source_metadata(path, row):
    """Optional physical metadata, not a visual scan or printed page mapping."""
    result={"method":"physical_pdf_parser","source_sha256":row["sha256"],
            "current_session_consumed":False,"page_count":None,"status":"unknown"}
    if Path(path).suffix.lower()!=".pdf":
        return {**result,"method":"unsupported_container","reason":"non_pdf_physical_page_count_unestablished"}
    try:
        backend=importlib.import_module("pymupdf")
    except ImportError:
        return {**result,"reason":"optional_pdf_dependency_unavailable"}
    result.update(tool="PyMuPDF",tool_version=backend.VersionBind)
    before=path.stat()
    try:
        with backend.open(str(path)) as document:
            if not document.is_pdf or document.needs_pass:
                return {**result,"reason":"pdf_locked_or_invalid"}
            if document.is_repaired:
                return {**result,"reason":"pdf_parser_repaired_source_requires_review"}
            count=document.page_count
            if type(count) is not int or count<1:
                return {**result,"reason":"pdf_has_no_physical_pages"}
    except Exception as exc:
        return {**result,"reason":"pdf_metadata_parse_failed","error_type":type(exc).__name__}
    after=path.stat()
    require((before.st_size,before.st_mtime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ino),
            "PACKAGE_BYTES_CHANGED","Source changed during metadata measurement.")
    return {**result,"page_count":count,"status":"measured","measured_utc":_utc()}


def _mapper_identity():
    try:
        backend=importlib.import_module("pymupdf")
        pdf={"tool":"PyMuPDF","version":backend.VersionBind}
    except ImportError:
        pdf={"tool":"unavailable","version":None}
    value={"schema":"t2ag.semantic-mapper.v2","code_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "pdf_metadata_backend":pdf}
    return {**value,"mapping_id":_digest(value)}


def _semantic_effects(package, manifest, blobs):
    files = {r["path"]: r for r in manifest["files"]}
    effects, issues, course_ids = {}, [], set()

    def add(kind, object_id, data):
        k = f"{kind}/{object_id}"
        require(k not in effects, "DUPLICATE_LEGACY_ID", f"Two legacy objects map to {k}.")
        effects[k] = put(kind, object_id, data)

    def evidence(path):
        return {"legacy_path": path, "source_namespace": manifest["source_namespace"],
                "snapshot_id": manifest["snapshot_id"], "blob_sha256": blobs[path]["sha256"]}

    def text(path):
        raw = (package / "originals" / path).read_bytes()
        try:
            return raw.decode("utf-8-sig")
        except UnicodeError:
            issues.append({"path": path, "reason": "non_utf8_evidence_preserved_unparsed"})
            return ""

    # Every retained byte has an addressable consumer through inspect/evidence.
    # This inventory is explicitly not counted as domain-semantic coverage.
    for path, row in files.items():
        add("legacy_file", path, {**evidence(path), "bytes": row["bytes"],
                                 "classification": row["classification"],
                                 "authority": "historical_evidence"})

    profiles = [p for p in files if re.fullmatch(r"(?:main/)?10_student/profile/profile\.md", p)]
    if len(profiles) == 1:
        path = profiles[0]
        add("student", "current", {"legacy_fields": _frontmatter(text(path)),
            "legacy_profile_body": text(path), "legacy": evidence(path),
            "migration_status": "preferences_require_explicit_mapping"})
    elif len(profiles) > 1:
        raise DomainError("DUPLICATE_LEGACY_ID", "Multiple profile authorities require explicit mapping.")

    for path in sorted(files):
        match = re.fullmatch(r"(?:main/)?40_course/([^/]+)/course\.md", path)
        if not match or match.group(1).startswith("_"):
            continue
        folder_id = match.group(1)
        base = path.rsplit("/", 1)[0]
        c = _frontmatter(text(path))
        course_id = str(c.get("course_id", folder_id))
        require(course_id == folder_id and course_id not in course_ids,
                "DUPLICATE_LEGACY_ID", "Course identity does not match its namespace or is duplicated.")
        course_ids.add(course_id)
        progress_path, ledger_path = base + "/progress.md", base + "/activity_ledger.md"
        progress = text(progress_path) if progress_path in files else ""
        p = _frontmatter(progress)
        require(not p.get("course_id") or p["course_id"] == course_id,
                "REFERENCE_CONFLICT", "Progress belongs to a different course.")
        current = _current_text(progress)
        current_id = p.get("current_activity_id")
        current_kind = p.get("current_activity")
        current_tuple = f"{course_id}/{current_id}" if current_id not in (None, "none", "") else None
        course_issues = []
        if not progress:
            course_issues.append("missing_progress_authority")
        lifecycle = _status(p.get("lifecycle_status", "unknown"), {"ongoing", "planned", "paused", "completed", "closed_incomplete"})
        if lifecycle == "unknown":
            course_issues.append("unknown_course_lifecycle")
        course_type = c.get("course_type", "unknown")
        if course_type not in {"mastery", "project", "praxis"}:
            course_issues.append("unknown_course_type")
        sources = []
        for source_path, row in files.items():
            if source_path.startswith(base + "/book/") and Path(source_path).suffix.lower() in {".pdf", ".epub"}:
                source_id = f"{course_id}/{row['sha256']}"
                if source_id not in sources:
                    sources.append(source_id)
                    measured=_source_metadata(package/"originals"/source_path,row)
                    add("source", source_id, {"title": Path(source_path).name, "source_version": row["sha256"],
                        "content_sha256": row["sha256"], "course_ids": [course_id], "page_count": measured["page_count"],
                        "format": Path(source_path).suffix[1:].lower(), "source_role": "legacy_unclassified",
                        "blob_sha256": row["sha256"], "legacy": evidence(source_path),
                        "verification": "legacy_bytes_only", "session_consumed": False,
                        "physical_metadata":measured,
                        "uncertainties": [] if measured["status"]=="measured" else ["physical_page_count_not_established",measured["reason"]],
                        "migration_state": "metadata_mapped" if measured["status"]=="measured" else "source_pending"})
        add("course", course_id, {"title": str(c.get("name", course_id)), "course_type": course_type,
            "status": lifecycle, "source_ids": sources, "learning_mode": c.get("learning_mode"),
            "current_activity_id": current_tuple, "legacy_fields": c, "legacy_progress": p,
            "legacy": evidence(path), "progress_evidence": evidence(progress_path) if progress_path in files else None,
            "uncertainties": course_issues, "migration_state": "needs_resolution" if course_issues else "mapped"})
        ledger = text(ledger_path) if ledger_path in files else ""
        activity_rows = [r for r in _tables(ledger) if {"activity_type", "activity_id", "state"} <= r.keys()]
        map_path = base + "/activity_map.md"
        content_groups = [r for r in _tables(text(map_path)) if "content_group_id" in r] if map_path in files else []
        seen_activities = set()
        for row in activity_rows:
            local_id, kind = row["activity_id"], row["activity_type"]
            require(local_id not in seen_activities, "DUPLICATE_LEGACY_ID", "Repeated activity identity in authoritative index.")
            seen_activities.add(local_id)
            _relative(local_id)
            require(kind in {"lesson", "exercise"}, "UNKNOWN_ACTIVITY_KIND", "Unknown legacy activity kind needs explicit mapping.")
            activity_id = f"{course_id}/{local_id}"
            activity_path = f"{base}/{kind}s/{local_id}/{local_id}.md"
            if activity_path not in files and kind == "exercise":
                activity_path = f"{base}/exercises/{local_id}/exercise.md"
            atext = text(activity_path) if activity_path in files else ""
            status = _status(row["state"], {"planned", "ongoing", "pending_close", "completed", "closed_incomplete"})
            uncertainties = [] if atext else ["missing_activity_body"]
            if status == "unknown":
                uncertainties.append("unknown_activity_lifecycle")
            pending_paths = [x for x in files if x.startswith(f"{base}/{kind}s/{local_id}/closeout/")]
            pending_bodies = [x for x in pending_paths if x.endswith("learner-review.md")]
            pending_body = text(pending_bodies[0]) if len(pending_bodies) == 1 else None
            if status == "pending_close" and not pending_body:
                uncertainties.append("pending_close_body_unresolved")
            add("activity", activity_id, {"course_id": course_id, "activity_type": kind, "status": status,
                "title": local_id, "original_body": atext, "legacy_fields": _frontmatter(atext), "legacy_lifecycle": row,
                "legacy": evidence(activity_path) if activity_path in files else evidence(ledger_path),
                "ledger_evidence": evidence(ledger_path), "pending_body": pending_body,
                "pending_evidence": [evidence(x) for x in pending_paths],
                "pending_requires_new_presentation": status == "pending_close",
                "uncertainties": uncertainties, "historical_permissions_active": False})
        if current_tuple:
            uncertainty = list(course_issues)
            if current_id not in seen_activities:
                uncertainty.append("current_activity_missing_from_ledger")
            current_activity = effects.get("activity/" + current_tuple, {}).get("data", {})
            if current_kind != current_activity.get("activity_type"):
                uncertainty.append("current_activity_type_conflicts_with_ledger")
            position = p.get("activity_position")
            stop = _bullet(current, "精确停顿点") or _bullet(current, "精确停点")
            if not isinstance(position, (str, type(None))) or position not in {None, "in_activity", "between_activities", "none"}:
                uncertainty.append("narrative_cursor_requires_reconciliation_with_body_and_checkpoint_table")
            body_next = _bullet(current, "下一步计划")
            if body_next and (not p.get("next_action_kind") or str(p["next_action_kind"]) not in body_next):
                uncertainty.append("body_next_action_requires_semantic_reconciliation")
            if p.get("next_action_kind") == "confirm_close" and current_activity.get("status") != "pending_close":
                uncertainty.append("confirm_close_without_pending_lifecycle")
            checkpoints = [r for r in _tables(progress) if "checkpoint_id" in r]
            for row in checkpoints:
                node_id = row["checkpoint_id"].strip("` ")
                parent = row.get("parent_node", "").strip("` ")
                group_matches = [g for g in content_groups if parent.startswith(g["content_group_id"].strip("` ") + "-")]
                owners = {x for g in group_matches for x in re.findall(r"\blesson\d+\b", g.get("lesson_ids", ""))}
                owner = f"{course_id}/{next(iter(owners))}" if len(owners) == 1 else None
                if "activity/" + str(owner) not in effects:
                    owner = None
                add("checkpoint", node_id, {"course_id": course_id, "legacy_fields": row,
                    "activity_id": owner, "identity_mapping": "content_group_authority" if owner else "unresolved_activity_owner",
                    "mapping_evidence": evidence(map_path) if owner else None,
                    "status": _status(row.get("状态", row.get("state", "unknown")), {"queued", "arrived", "pending", "confirmed", "archived"}),
                    "legacy": evidence(progress_path), "authority": "legacy_claim_preserved"})
            next_action = {"kind": p.get("next_action_kind"), "activity_type": p.get("next_activity_type"),
                           "activity_id": p.get("next_activity_id"), "source": "legacy_structured_progress"}
            checkpoint = p.get("current_checkpoint")
            pending = effects.get("activity/" + current_tuple, {}).get("data", {}).get("pending_body")
            add("cursor", current_tuple, {"course_id": course_id, "activity_id": current_tuple,
                "block_id": None if checkpoint in (None, "none", "") else checkpoint,
                "position": stop or position, "waiting_for": "resolve_legacy_conflict" if uncertainty else p.get("next_action_kind", "unknown"),
                "pending_body": pending, "next_action": next_action, "legacy_body_next_action": body_next,
                "legacy_current_section": current, "legacy_activity_position": position,
                "source_version": manifest["snapshot_id"], "legacy": evidence(progress_path),
                "uncertainties": uncertainty, "historical_permissions_active": False,
                "current_session_scan": None, "requires_current_session_revalidation": True})
            issues.extend({"course_id": course_id, "reason": item} for item in uncertainty)
        issues.extend({"course_id": course_id, "reason": item} for item in course_issues)

    # Index historical named evidence for the new inspect/evidence consumer.
    # These are typed historical records, not active permissions/scan/session.
    for path in sorted(files):
        if not path.endswith(".md") or not re.match(r"^(?:main/)?(?:10_student/profile|40_course)/",path) or "/_templates/" in path:
            continue
        if re.search(r"(?:question_bank|mistake_bank|course_reflections|lesson_thoughts|exercise_thoughts|activity_ledger)\.md$", path):
            original_body = text(path)
            body = _without_fences(original_body)
            kind = "legacy_question" if "question_bank" in path else "legacy_mistake" if "mistake_bank" in path else "legacy_record"
            for i, match in enumerate(re.finditer(r"(?m)^#{2,4}\s+([^\n]+)\n", body)):
                start = match.end()
                end = re.search(r"(?m)^#{1,4}\s", body[start:])
                content = original_body[start:start + end.start()] if end else original_body[start:]
                identity = path + "#" + str(i + 1)
                add(kind, identity, {"title": match.group(1), "original_body": content,
                    "legacy": evidence(path), "line": body[:match.start()].count("\n") + 1,
                    "authority": "historical_evidence", "requires_domain_mapping": True})
            course_match = re.fullmatch(r"(?:main/)?40_course/([^/]+)/question_bank\.md", path)
            if course_match:
                cid = course_match.group(1)
                entries = list(re.finditer(r"(?m)^###\s+(Q-\d+)\b([^\n]*)\n", body))
                for n, entry in enumerate(entries):
                    end = entries[n+1].start() if n+1 < len(entries) else len(body)
                    boundary = re.search(r"(?m)^#{1,3}\s", body[entry.end():end])
                    if boundary:
                        end = entry.end() + boundary.start()
                    content = original_body[entry.end():end]
                    values = _item_fields(content)
                    # A question field may continue on indented lines. Preserve
                    # that original text, not merely its first-line summary.
                    question = re.search(r"(?m)^-[ \t]+(?:\*\*)?问题(?:\*\*)?[：:][ \t]*([^\n]*(?:\n(?:[ \t]{2,}|\t)[^\n]*)*)", content)
                    question_text = question.group(1).rstrip() if question else values.get("问题")
                    qid = cid + "/" + entry.group(1)
                    state = values.get("状态", "unknown").strip("` ")
                    state = {"revisit": "open", "merged": "closed"}.get(state, state)
                    if state not in {"open", "answered", "closed"}:
                        state = "unknown"
                    reference = values.get("来源", "")
                    activity_match = re.search(r"\b(lesson\d+|exercise\d+)\b", reference)
                    aid = cid + "/" + activity_match.group(1) if activity_match else None
                    uncertainty = []
                    if not aid or "activity/" + aid not in effects:
                        uncertainty.append("question_activity_reference_unresolved")
                    if state == "unknown":
                        uncertainty.append("question_status_unknown")
                    add("question", qid, {"course_id": cid, "activity_id": aid,
                        "title": entry.group(2).strip("｜| "), "text": question_text,
                        "status": state, "answers": [], "legacy_fields": values,
                        "original_body": content, "legacy": evidence(path),
                        "uncertainties": uncertainty, "attribution": "legacy_question_record_not_new_statement"})
    _extend_semantics(files, text, evidence, add, effects, issues, blobs)
    for effect in effects.values():
        for reason in effect["data"].get("uncertainties", []):
            issue = {"object": effect["kind"] + "/" + effect["id"], "reason": reason}
            if issue not in issues:
                issues.append(issue)
    return list(effects.values()), issues


def _extend_semantics(files, text, evidence, add, effects, issues, blobs):
    """Named domain adapters. Missing knowledge is not a new learner decision.

    Historical records retain their original verdict/assistance evidence; they
    cannot be regraded against a newly invented immutable criterion. Live
    objects expose explicit reconciliation flags where old and new contracts
    cannot be mechanically identified.
    """
    # Snapshot transaction backups and previous migrations are retained bytes,
    # never additional current domain authorities even when their suffix matches.
    paths=sorted(p for p in files if re.match(r"^(?:(?:main/)?(?:00_core|10_student|20_teacher|30_group|40_course|50_playbook|60_journal|70_tools|80_interface)/|cloud/|docs/adr/)",p)
                 and "/_templates/" not in p and "/retired_020_sources/" not in p)

    def record(path, **data):
        body = text(path)
        return {"legacy": evidence(path), "legacy_fields": _frontmatter(body),
                "original_body": body, "evidence": [evidence(path)],
                "provenance": {"role": "legacy_record", "source": path,
                               "text": "Preserved historical attribution, not a new statement."}, **data}

    def entity(kind, identity):
        item = effects.get(kind + "/" + str(identity))
        return item["data"] if item else None

    def json_file(path):
        try:
            return json.loads(text(path))
        except ValueError:
            issues.append({"path": path, "reason": "invalid_json_preserved"})
            return None

    def related(path, prefix):
        return [evidence(p) for p in files if p.startswith(prefix) and p != path]

    # Profile fields already have stable public consumers (hint gate, language,
    # timezone, close preferences); preserve unknown declarations alongside them.
    profile = entity("student", "current")
    if profile:
        profile.update({k: v for k, v in profile["legacy_fields"].items()
                        if k not in {"legacy", "legacy_profile_body", "migration_status"}})
        profile.update(migration_status="mapped_declarations", preferences_body=profile["legacy_profile_body"])
    for path in paths:
        if "/_templates/" in path or "/retired_020_sources/" in path:
            continue
        match = re.fullmatch(r"(?:main/)?20_teacher/(T\d+)\.md", path)
        if match:
            body = text(path)
            name = re.search(r"(?m)^#\s+(.+)$", body)
            add("teacher", match[1], record(path, name=name[1] if name else match[1],
                template=body, overlay={}, identity_kind="template_role"))
        elif re.fullmatch(r"(?:main/)?20_teacher/overlay\.md", path):
            add("teacher_overlay", "current", record(path, sections=list(_sections(text(path), r"[^\n]+")),
                authority="legacy_personal_preferences", machine_enforcement=False))
            for row in _tables(text(path)):
                c=entity("course",row.get("课程代码"))
                teacher=re.search(r"(?:^|/)20_teacher/(T\d+)\.md",row.get("教师模板",""))
                if c and teacher:
                    c["teacher_id"]=teacher[1]
                    c["teacher_overlay_id"]="current"
    for effect in list(effects.values()):
        if effect["kind"] == "course":
            c = effect["data"]
            for name in ("teacher_template", "teacher_template_id", "teacher_id"):
                value = c["legacy_fields"].get(name)
                if value and entity("teacher", value):
                    c["teacher_id"] = value
                    break

    # Reuse persisted verified text only when the frozen source, body and render
    # identities agree. Verification provenance is historical; delivery is not.
    by_sha = {}
    for path, row in files.items(): by_sha.setdefault(row["sha256"], []).append(path)
    for path in paths:
        pm = re.fullmatch(r"(?:main/)?40_course/([^/]+)/book/.*/source_assets/([^/]+)/pages/page_(\d+)\.md", path)
        if not pm: continue
        cid, document, page_number = pm.groups(); body=text(path); fm=_frontmatter(body)
        source_id=cid+"/"+str(fm.get("source_document_sha256")); source=entity("source",source_id)
        page_text=_body_after_frontmatter(body); claimed=fm.get("verified_text_sha256")
        # Some legacy writers normalized CRLF before hashing; bind the exact
        # recognized representation explicitly rather than declaring a mismatch
        # to be verified or discarding the original file's byte identity.
        normalized=page_text.replace("\r\n","\n")
        candidates=[page_text,normalized,normalized.strip()+"\n",
                    re.sub(r"^\s*# Page \d+\s*\n","",normalized).strip()+"\n"]
        matched=next((s for s in candidates if hashlib.sha256(s.encode()).hexdigest()==claimed),None)
        reasons=[]
        if not source: reasons.append("page_source_identity_missing")
        if matched is None: reasons.append("verified_text_hash_mismatch")
        if fm.get("verification_status")!="verified": reasons.append("legacy_page_unverified")
        render=fm.get("render_sha256"); render_paths=by_sha.get(render,[])
        if not render_paths: reasons.append("canonical_page_render_missing")
        if source and type(source.get("page_count")) is int and not 1<=int(page_number)<=source["page_count"]:
            reasons.append("page_index_outside_measured_document")
        page_id=str(fm.get("asset_id",document+"-P"+page_number.zfill(4)))
        add("page",page_id,record(path,course_id=cid,source_id=source_id,pdf_page_index=int(page_number),
            printed_page_label=fm.get("printed_page_label"),verified_text=matched if matched is not None else page_text,
            verified_text_sha256=hashlib.sha256((matched if matched is not None else page_text).encode()).hexdigest(),
            legacy_claimed_text_sha256=claimed,layout_critical=fm.get("layout_critical",True),
            render_blob_sha256=render if render_paths else None,
            render_bytes=files[render_paths[0]]["bytes"] if render_paths else None,
            blob_refs=[blobs[render_paths[0]]] if render_paths else [],
            verification={"status":"verified" if not reasons else "unresolved",
                "reference":path,"source_document_sha256":fm.get("source_document_sha256"),
                "provenance":"inherited_verified_claim_with_frozen_byte_identity"},
            uncertainties=reasons,current_session_consumed=False,migration_requires_reconciliation=bool(reasons)))
    page_groups={}
    for effect in list(effects.values()):
        if effect["kind"]=="page":
            page=effect["data"]
            page_groups.setdefault((page["source_id"],page["pdf_page_index"]),[]).append(effect)
    for (source_id,page_number),versions in page_groups.items():
        if len(versions)!=1:
            for effect in versions:
                effect["data"]["uncertainties"].append("multiple_imported_page_versions_no_current_authority")
                effect["data"]["migration_requires_reconciliation"]=True
        elif not versions[0]["data"]["migration_requires_reconciliation"]:
            add("page_head",source_id+"/"+str(page_number),{
                "page_id":versions[0]["id"],"source_id":source_id,"pdf_page_index":page_number,
                "provenance":"unique_identity_verified_page_in_frozen_snapshot"})
    for path in paths:
        sm=re.fullmatch(r"(?:main/)?40_course/([^/]+)/lessons/([^/]+)/preparation/current_snapshot\.json",path)
        if not sm: continue
        cid,local=sm.groups(); aid=cid+"/"+local; pointer=json_file(path)
        if not isinstance(pointer,dict): continue
        snap_path=path.rsplit("/",1)[0]+"/"+str(pointer.get("snapshot_id"))+".json"
        snapshot=json_file(snap_path) if snap_path in files else None
        reasons=[]
        if not isinstance(snapshot,dict): reasons.append("current_preparation_snapshot_missing")
        elif pointer.get("snapshot_body_sha256")!=snapshot.get("snapshot_body_sha256"):
            reasons.append("current_preparation_pointer_hash_conflict")
        page_ids=[]
        for item in (snapshot or {}).get("page_keys",[]):
            found=[e["id"] for e in effects.values() if e["kind"]=="page" and e["data"].get("source_id")==cid+"/"+str(item.get("source_document_sha256")) and e["data"].get("pdf_page_index")==item.get("pdf_page_index")]
            if len(found)!=1: reasons.append("preparation_page_reference_unresolved")
            else: page_ids.append(found[0])
        map_path=path.rsplit("/preparation/",1)[0]+"/lesson_map.md"
        add("legacy_preparation",aid,record(path,activity_id=aid,course_id=cid,pointer=pointer,
            snapshot=snapshot,page_ids=page_ids,lessonmap_rows=_tables(text(map_path)) if map_path in files else [],
            snapshot_evidence=evidence(snap_path) if snap_path in files else None,
            lessonmap_evidence=evidence(map_path) if map_path in files else None,
            uncertainties=reasons,requires_current_session_delivery=True,permissions_active=False))
        activity=entity("activity",aid)
        if activity: activity["legacy_preparation_id"]=aid

    # Exercise original order, separate authored answers, reviews and assets.
    for path in paths:
        match = re.fullmatch(r"(?:main/)?40_course/([^/]+)/exercises/([^/]+)/problems\.md", path)
        if not match or match[1].startswith("_"):
            continue
        cid, local = match.groups(); aid = cid + "/" + local
        body = text(path); fm = _frontmatter(body); problems = {}
        for pid, content, line in _sections(body, re.escape(local) + r"-Q\d+"):
            values = _item_fields(content)
            problems[pid] = {"text": values.get("题面", content), "original_body": content,
                "origin": "source", "legacy_fields": values, "source_reference": {
                    k: fm.get(k) for k in ("source_path", "source_artifact_id", "source_sha256", "source_locator")},
                "status": values.get("状态", "unknown"), "legacy": evidence(path), "line": line}
        orders = {k: _list_value(fm.get(k)) for k in ("source_order", "teaching_sequence")}
        uncertainty = ["historical_exercise_help_and_criterion_require_reconciliation"]
        if any(set(v) != set(problems) or len(v) != len(set(v)) for v in orders.values()):
            uncertainty.append("exercise_order_or_problem_identity_requires_reconciliation")
        add("exercise", aid, record(path, activity_id=aid, course_id=cid, problems=problems,
            **orders, supplemental_ids=[], assistance=[], attempt_ids=[], review_ids=[],
            assistance_status="unmapped_legacy_evidence_not_no_help",
            uncertainties=uncertainty, migration_requires_reconciliation=True))
    for path in paths:
        match = re.fullmatch(r"(?:main/)?40_course/([^/]+)/exercises/([^/]+)/attempts/([^/]+)/attempt\.md", path)
        if not match or match[1].startswith("_"):
            continue
        cid, local, legacy_id = match.groups(); aid = cid + "/" + local; ident = aid + "/" + legacy_id
        body = text(path); fm = _frontmatter(body)
        require(fm.get("attempt_id", legacy_id) == legacy_id, "REFERENCE_CONFLICT", "Attempt identity conflicts with its folder.")
        answers = [{"problem_id": pid, "text": content, "original_body": content, "line": line}
                   for pid, content, line in _sections(body, re.escape(local) + r"-Q\d+")]
        attachments = related(path, path.rsplit("/", 1)[0] + "/")
        uncertainty = ["historical_criterion_and_help_snapshot_not_machine_equivalent"]
        add("attempt", ident, record(path, activity_id=aid, course_id=cid, answers=answers,
            student={"role": "student_historical", "source": path, "text": body},
            problem_ids=_list_value(fm.get("problem_ids")), assistance={a["problem_id"]: {"status": "unknown", "legacy_context": body} for a in answers},
            hint_gate="legacy_unknown", criterion_id=None, attachments=attachments,
            blob_refs=[blobs[a["legacy_path"]] for a in attachments],
            history_only=True, uncertainties=uncertainty, migration_requires_reconciliation=True))
        exercise = entity("exercise", aid)
        if exercise: exercise["attempt_ids"].append(ident)
    for path in paths:
        match = re.fullmatch(r"(?:main/)?40_course/([^/]+)/exercises/([^/]+)/reviews/(RV\d+)\.md", path)
        if not match or match[1].startswith("_"):
            continue
        cid, local, legacy_id = match.groups(); aid = cid + "/" + local
        body = text(path); fm = _frontmatter(body); atid = aid + "/" + str(fm.get("attempt_id"))
        ratings = [{"problem_id": pid, "legacy_verdict": _item_fields(content).get("结果", "unknown"),
                    "original_body": content, "independent": None, "line": line}
                   for pid, content, line in _sections(body, re.escape(local) + r"-Q\d+")]
        reasons = ["legacy_judgment_not_regraded_against_new_criterion"]
        if not entity("attempt", atid): reasons.append("review_attempt_reference_unresolved")
        ident = aid + "/" + legacy_id
        add("review", ident, record(path, course_id=cid, attempt_id=atid, criterion_id=None,
            ratings=ratings, teacher={"role": "teacher_historical", "source": path, "text": body},
            status=fm.get("status", "unknown"), history_only=True, uncertainties=reasons,
            migration_requires_reconciliation=True))
        exercise = entity("exercise", aid)
        if exercise: exercise["review_ids"].append(ident)

    # Knowledge mistakes, reflection and reasoning are different from incidents.
    for path in paths:
        if not path.endswith(".md") or "/_templates/" in path or "/retired_020_sources/" in path:
            continue
        cm = re.match(r"(?:main/)?40_course/([^/]+)/", path)
        cid = cm[1] if cm else None
        if path.endswith("/mistake_bank.md") and cid and not cid.startswith("_"):
            for mid, content, line in _sections(text(path), r"M-\d+"):
                values = _item_fields(content); reference = values.get("来源", "")
                am = re.search(r"\b(lesson\d+|exercise\d+)\b", reference)
                add("mistake", cid + "/" + mid, record(path, course_id=cid,
                    activity_id=cid + "/" + am[1] if am else None,
                    knowledge_key=values.get("知识点键"), root_cause=values.get("根因"),
                    status=values.get("状态", "unknown").strip("` "),
                    cycle=values.get("当前周期"), next_retest=values.get("下次允许复测"),
                    legacy_retest_rows=_tables(content), original_body=content, legacy_fields=values,
                    retests=[], independent_streak=None, failed_retests=None, line=line,
                    uncertainties=["knowledge_cycle_retest_dates_require_domain_reconciliation"],
                    migration_requires_reconciliation=True))
        if path.endswith("/course_reflections.md"):
            for rid, content, line in _sections(text(path), r"REFL-[A-Za-z0-9]+-\d+"):
                values = _item_fields(content)
                add("reflection", rid, record(path, course_id=rid.split("-")[1], body=content,
                    student_text=values.get("感想"), teacher_observation=values.get("教学提示"),
                    original_body=content, line=line, attribution="preserved_separate_student_and_teacher"))
        if path.endswith("/reasoning_patterns.md"):
            for pid, content, line in _sections(text(path), r"RP-\d+"):
                values = _item_fields(content)
                add("pattern", pid, record(path, body=content, original_body=content, line=line,
                    status=values.get("状态", "unknown"), method_status=values.get("方法接替状态"),
                    evidence_statement=values.get("验证记录"), counterevidence=values.get("反证"),
                    legacy_fields=values, psychological_diagnosis=False))
        if re.search(r"/(?:lesson_thoughts|exercise_thoughts)\.md$", path) and cid:
            for title, content, line in _sections(text(path), r"(?:\[[^\n]+|U\d+[^\n]+|(?:LT|ET)[-A-Za-z0-9]*\d+[^\n]*)"):
                ident=path+"#L"+str(line)
                add("thought", ident, record(path, course_id=cid, title=title, body=content,
                    original_body=content, legacy_fields=_item_fields(content), line=line))
        if cid and re.search(r"/keystones/K-\d+[^/]*\.md$", path):
            ident = re.search(r"/keystones/(K-\d+)", path)[1]
            add("keystone", cid + "/" + ident, record(path, course_id=cid, body=text(path),
                claim=_frontmatter(text(path)).get("claim"), review_status="legacy_preserved"))
        if path.endswith("/t2ag_problemlog.md"):
            for iid, content, line in _sections(text(path), r"P-\d+"):
                values = _item_fields(content); closure = values.get("closure", "legacy_unknown")
                add("issue", iid, record(path, problem=content, original_body=content, line=line,
                    root_cause=values.get("根因", "legacy_unspecified:" + iid), scope="system",
                    status="open" if closure == "open" else "legacy_resolution_claim",
                    closure=closure, occurrences=[], legacy_occurrence_count=values.get("occurrence_count"),
                    legacy_reopen_count=values.get("reopen_count"), remedy_since=values.get("remedy_since"),
                    legacy_fields=values, new_system_enforcement_verified=False))
        if cid and path.endswith("/activity_ledger.md"):
            body=text(path)
            for identity,content,line in _sections(body,r"(?:ALE-\d+|CLR-\d+)"):
                values={**_flat_yaml(content),**_item_fields(content)}
                aid=values.get("activity_id")
                add("lifecycle_event" if identity.startswith("ALE") else "legacy_close",cid+"/"+identity,
                    record(path,course_id=cid,activity_id=cid+"/"+str(aid) if aid else None,
                        original_body=content,legacy_fields=values,line=line,
                        authority="historical_fact_not_future_confirmation"))
            for label,content,line in _sections(body,r"alias [^\n]+"):
                values=_flat_yaml(content); old=values.get("legacy_id"); new=values.get("canonical_id")
                if not old or not new: continue
                if values.get("scope")=="activity" and entity("activity",cid+"/"+new):
                    add("alias","activity/"+cid+"/"+old,{"kind":"activity","target_id":cid+"/"+new,
                        "legacy":evidence(path),"line":line})
                else:
                    add("legacy_identity",cid+"/"+old,{"scope":values.get("scope"),"course_id":cid,
                        "canonical_id":new,"legacy_id":old,"legacy":evidence(path),"line":line})
        if path.endswith("/recommendations.md"):
            for ident,content,line in _sections(text(path),r"R-\d+"):
                values=_item_fields(content)
                add("suggestion",ident,record(path,body=content,original_body=content,line=line,
                    status=values.get("status","unknown"),scope=values.get("scope"),
                    owner="legacy_attribution",legacy_owner=values.get("provenance"),
                    target=values.get("target"),revisit_when=values.get("revisit_when")))
    for path in paths:
        match=re.fullmatch(r"(?:main/)?40_course/([^/]+)/lessons/([^/]+)/(emissions\.jsonl|teaching_log\.md)",path)
        if not match: continue
        cid,local,name=match.groups(); body=text(path)
        if name.endswith(".jsonl"):
            for n,line in enumerate(body.splitlines(),1):
                if not line.strip(): continue
                try: data=json.loads(line)
                except ValueError: data={"raw":line,"uncertainty":"invalid_jsonl_record"}
                add("teaching_event",path+"#"+str(n),{"course_id":cid,"activity_id":cid+"/"+local,
                    "sequence":n,"data":data,"legacy":evidence(path),"current_session_delivery":False})
        else:
            add("teaching_log",cid+"/"+local,record(path,course_id=cid,activity_id=cid+"/"+local,
                body=body,authority="historical_teaching_record"))

    for path in paths:
        if "/_templates/" in path or "/retired_020_sources/" in path:
            continue
        rm = re.fullmatch(r"(?:main/)?10_student/activities/reading/(AR-\d+)[^/]*\.md", path)
        em = re.fullmatch(r"(?:main/)?10_student/engagements/(EG-\d+)[^/]*/engagement\.md", path)
        gm = re.fullmatch(r"(?:main/)?30_group/(G\d+)/plan\.md", path)
        bm = re.fullmatch(r"(?:main/)?30_group/(G\d+)/bindings/(R\d+)[^/]*\.md", path)
        if rm:
            body = text(path); fm = _frontmatter(body)
            add("reading", rm[1], record(path, intent=fm.get("title", rm[1]), kind="reading",
                status=fm.get("record_status", "unknown"), resources=[fm.get("source_description")],
                upgraded_to_course=fm.get("upgraded_to_course"), events=list(_sections(body, r"\d{4}-\d{2}-\d{2}[^\n]*")),
                mastery_asserted=False))
        elif em:
            body = text(path); fm = _frontmatter(body); prefix=path.rsplit("/", 1)[0] + "/"
            entries = {}
            for data_path in files:
                if data_path.startswith(prefix) and data_path.endswith(".jsonl"):
                    rows=[]
                    for n, line in enumerate(text(data_path).splitlines(), 1):
                        if not line.strip(): continue
                        try: rows.append({"line": n, "value": json.loads(line)})
                        except ValueError: rows.append({"line": n, "raw": line, "uncertainty": "invalid_jsonl_record"})
                    entries[Path(data_path).name] = {"rows": rows, "legacy": evidence(data_path)}
            add("engagement", em[1], record(path, intent=fm.get("engagement_id", em[1]),
                governance=fm.get("governance", "unknown"), status=fm.get("status", "unknown"),
                linked_courses=_list_value(fm.get("linked_courses")), annotations=[],
                domain_records=entries, evidence_index=fm.get("evidence_index"),
                attachments=related(path, prefix)))
        elif gm:
            gid=gm[1]; body=text(path); fm=_frontmatter(body); prefix=path.rsplit("/",1)[0]
            calpath=prefix+"/calendar.md"; calendar=text(calpath) if calpath in files else ""
            reviewpath=prefix+"/review.md"; review=text(reviewpath) if reviewpath in files else ""
            members=_list_value(fm.get("course_members"))
            uncertainty=[]
            if any(not entity("course", cid) for cid in members): uncertainty.append("group_member_reference_unresolved")
            add("group", gid, record(path, members=members, engagement_members=_list_value(fm.get("engagement_members")),
                status=fm.get("status", "unknown"), current_course=fm.get("current_course"),
                container_mode=fm.get("container_mode"), capacity=None,
                calendar={"legacy_fields":_frontmatter(calendar), "body":calendar, "tables":_tables(calendar)},
                thresholds={"body":review, "plan_body":body}, goal=body,
                proposal_sha256=None, legacy_calendar=evidence(calpath) if calpath in files else None,
                uncertainties=uncertainty+["group_capacity_thresholds_need_explicit_structured_mapping"],
                migration_requires_reconciliation=True))
            if review:
                add("group_review", gid+"/legacy", record(reviewpath, group_id=gid,
                    frequency_observation=None, progress_observation=None, judgment="legacy_body", body=review))
        elif bm:
            fm=_frontmatter(text(path)); cid=fm.get("course_id")
            add("binding", bm[2], record(path, group_id=bm[1], course_ids=[cid] if cid else [],
                status=fm.get("binding_status", "unknown"), execution_mode=fm.get("execution_mode"),
                budget_weight=0, intent=text(path)))

    # Exam debt and pools are distinct authorities. An empty ledger stays empty;
    # fenced future templates must never create phantom sittings or passed exams.
    for path in paths:
        match=re.fullmatch(r"(?:main/)?40_course/([^/]+)/_exam/(index|exam_ledger)\.md",path)
        if not match or match[1].startswith("_"): continue
        cid, category=match.groups(); body=text(path)
        if category=="index":
            pool_rows=[r for r in _tables(body) if "卷ID" in r]
            add("exam_bank",cid+"/legacy",record(path,course_id=cid,papers={},problems={},batches=[],
                exposures=[],used_papers=[],status="legacy_pending_mapping" if pool_rows else "building",
                legacy_tables=_tables(body),legacy_empty_pool=not pool_rows,
                uncertainties=["legacy_pool_and_official_source_references_require_mapping"] if pool_rows else [],
                migration_requires_reconciliation=bool(pool_rows)))
        else:
            tables=_tables(body); fields={r.get("字段"):r.get("值") for r in tables if "字段" in r}
            add("exam_debt",cid,record(path,course_id=cid,status=str(fields.get("考核债状态","unknown")).strip("` "),
                sittings_used=fields.get("已用场次"),next_sitting=fields.get("下一场次"),
                parameters=[r for r in tables if "参数" in r],settlement_authority="legacy_ledger"))
            for xid,content,line in _sections(body,r"EX-\d+"):
                values=_item_fields(content)
                add("exam",cid+"/"+xid,record(path,course_id=cid,original_body=content,line=line,
                    legacy_fields=values,status="historical",passed=None,independently_eligible=None,
                    history_only=True,uncertainties=["historical_exam_not_regraded"],migration_requires_reconciliation=True))

    # External references preserve identities without accessing any peer root.
    for path in paths:
        if path.endswith("/external_refs.json"):
            data=json_file(path)
            if not isinstance(data,dict): continue
            for ref in data.get("references",[]):
                if not isinstance(ref,dict) or not ref.get("reference_id"): continue
                identity={k:ref.get(k) for k in ("peer_system","peer_relative_path")}
                add("external",str(data.get("owner_id"))+"/"+ref["reference_id"],{
                    **ref,"identity":identity,"owner_id":data.get("owner_id"),
                    "version":ref.get("peer_version"),"pinned_sha256":ref.get("content_sha256"),
                    "root_hints":data.get("peer_root_hints"),"legacy":evidence(path),"peer_accessed":False})
        elif path.endswith("/artifact_registry.json"):
            data=json_file(path)
            if not isinstance(data,dict): continue
            for row in data.get("artifacts",[]):
                if not isinstance(row,dict) or not row.get("artifact_id"): continue
                target=row.get("canonical_path"); mapped=[k for k,e in effects.items() if e["kind"]!="legacy_file" and e["data"].get("legacy",{}).get("legacy_path")==target]
                add("artifact_identity",row["artifact_id"],{**row,"target_objects":mapped,
                    "legacy":evidence(path),"target_present":target in files})
        elif path.endswith("/legacy_r_registry.json"):
            data=json_file(path)
            if isinstance(data,dict):
                for row in data.get("entries",[]):
                    add("legacy_identity",row["file"],{**row,"legacy":evidence(path),"authority":"historical_redirect"})

    # Rule contracts are available to a rule-history consumer, never installed as
    # new hard gates merely because an old Doctor name appears in prose.
    for path in paths:
        if re.fullmatch(r"(?:main/)?50_playbook/[^/]+\.md",path):
            body=text(path); enforcement=re.search(r"(?m)^enforcement:\s*(.+)",body)
            add("rule_contract",Path(path).stem,record(path,owner=path,body=body,
                legacy_enforcement=enforcement[1] if enforcement else "undeclared",
                disposition="reference_contract",machine_enforcement_verified=False))
        elif re.search(r"/(?:60_journal/[^/]+\.md|00_core/(?:t2ag_changelog|t2ag_verdict_ledger)\.md)$",path) or re.fullmatch(r"docs/adr/[^/]+\.md",path):
            category="adr" if "/adr/" in path else "changelog" if "changelog" in path else "verdict" if "verdict" in path else "journal"
            add("history",path,record(path,category=category,body=text(path),
                implementation_status="legacy_evidence",review_status="not_revalidated",release_status="legacy_evidence"))
        elif re.search(r"/(?:t2ag_memory|learning_path)\.md$",path):
            add("legacy_view",path,record(path,authority="derived_reference_not_current_state"))
    skinpath=next((p for p in files if re.fullmatch(r"(?:main/)?80_interface/skin\.yaml",p)),None)
    if skinpath:
        config=_flat_yaml(text(skinpath)); prefix=skinpath.rsplit("/",1)[0]
        for key,folder in config.items():
            if not key.startswith("registry.") or not isinstance(folder,str): continue
            meta_path=prefix+"/"+folder+"/skin.yaml"
            if meta_path not in files: continue
            meta=_flat_yaml(text(meta_path)); art_path=prefix+"/"+folder+"/"+str(meta.get("art_file"))
            sid=key.split(".",1)[1]
            add("skin",sid,{"title":meta.get("name",sid),"welcome":meta.get("welcome_msg",""),
                "art":text(art_path) if art_path in files else "", "private":True,"license":"legacy_unspecified",
                "legacy":evidence(meta_path),"legacy_metadata":meta})
        if profile and entity("skin",config.get("active")): profile["skin_id"]=config["active"]

    # Cloud snapshots and inbox/outbox remain paused; receipt states and processed
    # IDs are queryable, but no imported message is sent or implicitly consumed.
    cloud=next((p for p in files if p.endswith("cloud/cloud_sync_state.md")),None)
    if cloud:
        body=text(cloud); values=_item_fields(body)
        add("legacy_cloud", "current",record(cloud,status=values.get("cloud_bridge_status","unknown"),
            base_state_id=values.get("current_base_state_id"),tables=_tables(body),
            metadata=values,external_messages_sent=False,requires_new_baseline=True))
        for path in paths:
            if re.search(r"(?:^|/)cloud/(inbox|outbox)/[^/]+\.(?:md|txt)$",path) and not path.endswith("README.md"):
                add("legacy_cloud_item",Path(path).stem,record(path,direction="inbox" if "/inbox/" in path else "outbox",
                    status=_frontmatter(text(path)).get("status","legacy_metadata_only"),executable=False))
    for path in paths:
        if re.search(r"\.contributions\.json$|\.context\.json$",path):
            data=json_file(path)
            add("legacy_bridge",path,{"legacy":evidence(path),"data":data,"permissions_active":False,
                "requires_new_identity_binding":True})


def import_package(package_dir, destination):
    from .journal import Journal
    package = _plain_ancestors(package_dir)
    verified = verify_package(package)
    manifest = verified["manifest"]
    mapper = _mapper_identity()
    target = _plain_ancestors(destination)
    require(not target.is_relative_to(package) and not package.is_relative_to(target),
            "OVERLAPPING_ROOTS", "Package and instance must not overlap.")
    require(not target.exists() or target.is_dir(), "DESTINATION_NOT_EMPTY", "Destination is an existing file.")
    if target.exists() and any(target.iterdir()):
        marker = target / "migration.json"
        require(marker.is_file() and not _linked(marker), "DESTINATION_NOT_EMPTY", "Destination is not an imported instance.")
        try:
            receipt = json.loads(marker.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise DomainError("INVALID_IMPORT_RECEIPT", "Invalid import receipt; do not overwrite destination.") from exc
        require(receipt.get("snapshot_id") == manifest["snapshot_id"] and
                receipt.get("manifest_content_sha256") == _digest(manifest),
                "DESTINATION_NOT_EMPTY", "Destination belongs to a different frozen package.")
        require(receipt.get("mapping_id")==mapper["mapping_id"],"MAPPER_CHANGED",
                "This instance used another mapper or PDF backend; import into a new destination, never silently overwrite or report an upgrade.")
        state = Journal(target).read_state()
        previous = state.get("objects", {}).get("migration/" + manifest["snapshot_id"])
        require(previous is not None and previous["data"].get("manifest_content_sha256") == _digest(manifest),
                "DESTINATION_NOT_EMPTY", "Refusing to replace an instance with another package.")
        require(previous["data"].get("mapper")==mapper,"MAPPER_CHANGED","The durable mapper identity differs from the current import configuration.")
        Journal(target).validate()
        return {"ok": True, "replayed": True, "destination": str(target), "snapshot_id": manifest["snapshot_id"]}
    target = _new_target(target)
    stage = Path(tempfile.mkdtemp(prefix=".t2ag-import-", dir=target.parent))
    journal = Journal(stage)
    journal.initialize()
    blobs = {}
    for row in manifest["files"]:
        blob = journal.put_file(package / "originals" / row["path"])
        require(blob["sha256"] == row["sha256"] and blob["bytes"] == row["bytes"],
                "PACKAGE_BYTES_CHANGED", "Package changed during import.")
        blobs[row["path"]] = blob
    _fault("after_assets", {"stage": stage})
    effects, issues = _semantic_effects(package, manifest, blobs)
    manifest_blob = journal.put_blob(_canonical(manifest))
    semantic_kinds = Counter(e["kind"] for e in effects if e["kind"] != "legacy_file")
    classes = _coverage_classes(effects, manifest)
    remaining = sorted({item["reason"] for item in issues})
    coverage = {"byte_preservation": "verified", "mapped_kinds": dict(semantic_kinds),
                "semantic_status": "partial_requires_review" if remaining else "mapped_pending_live_acceptance",
                "cutover_ready": False, "data_classes": classes,
                "unresolved": issues, "unmapped_capabilities": remaining,
                "acceptance_remaining": ["non_author_review_of_this_mapper_revision",
                    "cold_agent_recovery_from_this_snapshot", "explicit_route_cutover_with_concurrent_source_check"],
                "current_session_scans_required": True}
    effects.append(put("migration", manifest["snapshot_id"], {
        "snapshot_id": manifest["snapshot_id"], "manifest_content_sha256": _digest(manifest),
        "mapper":mapper,
        "blob_sha256": manifest_blob["sha256"], "source_namespace": manifest["source_namespace"],
        "source_root_hint": manifest["source_root_hint"], "coverage": coverage,
        "imported_utc": _utc(), "permissions_reactivated": False, "scans_reactivated": False}))
    initial = journal.read_state()
    request = {"request_id": "migration:" + manifest["snapshot_id"], "action": "migration.install.verified",
               "payload": {"snapshot_id": manifest["snapshot_id"], "manifest_content_sha256": _digest(manifest),"mapping_id":mapper["mapping_id"]},
               "actor": {"role": "system", "source": "verified_frozen_exchange", "text": "Import preserved legacy evidence; no new student decisions."},
               "expected": {e["kind"] + "/" + e["id"]: initial["objects"][e["kind"] + "/" + e["id"]]["version"]
                            for e in effects if e["kind"] + "/" + e["id"] in initial["objects"]}}
    journal.apply(request, lambda _state, _request: effects)
    _fault("after_import_commit", {"stage": stage})
    journal.validate()
    verify_package(package)
    _json_write(stage / "migration.json", {"snapshot_id": manifest["snapshot_id"],
                "manifest_content_sha256": _digest(manifest), "source_namespace": manifest["source_namespace"],"mapping_id":mapper["mapping_id"]})
    _fault("before_instance_publish", {"stage": stage})
    _publish(stage, target)
    return {"ok": True, "replayed": False, "destination": str(target),
            "snapshot_id": manifest["snapshot_id"], "coverage": coverage}


DATA_CLASS_KINDS = {
    "D01": {"student", "teacher", "teacher_overlay"},
    "D02": {"course", "cursor", "checkpoint"},
    "D03": {"activity", "thought", "lifecycle_event", "legacy_close", "teaching_event", "teaching_log"},
    "D04": {"exercise", "attempt", "review"},
    "D05": {"source", "page", "page_head", "legacy_preparation"},
    "D06": {"question", "mistake", "reflection", "pattern", "keystone", "exam", "exam_bank", "exam_debt"},
    "D07": {"reading", "engagement", "group", "group_review", "binding", "suggestion"},
    "D08": {"cursor", "activity", "legacy_preparation"},
    "D09": {"external", "external_use", "artifact_identity", "legacy_identity", "alias"},
    "D10": {"issue", "history", "legacy_view"},
    "D11": {"legacy_cloud", "legacy_cloud_item", "legacy_bridge"},
    "D12": {"rule_contract", "artifact_identity"},
    "D13": {"skin"}, "D14": set(), "D15": set(), "D16": set(),
}


def _coverage_classes(effects, manifest):
    result={}
    for label,kinds in DATA_CLASS_KINDS.items():
        rows=[e for e in effects if e["kind"] in kinds]
        unresolved=[e["kind"]+"/"+e["id"] for e in rows if e["data"].get("uncertainties")]
        result[label]={"objects":len(rows),"kinds":dict(Counter(e["kind"] for e in rows)),
            "consumer":"migration_history + inspect; domain actions where contract-compatible",
            "status":"mapped_with_named_ambiguities" if unresolved else "mapped" if rows else "not_present_in_snapshot",
            "unresolved_objects":unresolved}
    result["D14"].update(status="inventoried_not_executed",
        preserved_pending_files=sum(r["classification"]=="recovery_or_pending_input" for r in manifest["files"]),
        excluded_environment=manifest["exclusions"],consumer="manifest inventory and legacy_file byte consumer")
    result["D15"].update(status="private_instance_only",consumer="no automatic publication or external transmission")
    result["D16"].update(status="outside_source_root_not_copied",consumer="workspace-owned work order pointers")
    return result


def migration_history(instance, kind=None, course_id=None):
    """Query usable domain history, not a list of archived source files.

    Returned original text remains private instance data. Uncertainty and
    history-only flags are deliberately returned with records, never filtered
    out to present old evidence as current permission or independent mastery.
    """
    from .journal import Journal
    state=Journal(_plain_ancestors(instance)).read_state()
    kinds=set().union(*DATA_CLASS_KINDS.values())-{"legacy_record"}
    require(kind is None or kind in kinds,"UNKNOWN_HISTORY_KIND","Choose an imported domain kind.")
    rows=[e for e in state["objects"].values() if e["kind"] in kinds
          and (kind is None or e["kind"]==kind)
          and (course_id is None or e["data"].get("course_id")==course_id)]
    return {"revision":state["revision"],"records":rows,"count":len(rows),
            "kinds":dict(Counter(e["kind"] for e in rows)),"historical_permissions_active":False}


def _differences(before, after):
    old = {r["path"]: (r["bytes"], r["sha256"]) for r in before}
    new = {r["path"]: (r["bytes"], r["sha256"]) for r in after}
    return {"added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
            "changed": sorted(p for p in old.keys() & new.keys() if old[p] != new[p])}


def migration_report(instance, source_root=None):
    """New-system consumer and conservative differential rollback assessment.

    No route is changed. With post-import writes or source drift, preserve both
    deltas and reconcile; returning to the old path alone is not a safe rollback.
    """
    from .journal import Journal
    journal = Journal(_plain_ancestors(instance))
    state = journal.read_state()
    imports = [entity for entity in state["objects"].values() if entity["kind"] == "migration"]
    require(len(imports) == 1, "MIGRATION_NOT_FOUND", "Expected exactly one installed frozen exchange.")
    imported = imports[0]
    data = imported["data"]
    manifest = json.loads(journal.read_blob(data["blob_sha256"]))
    require(_digest(manifest) == data["manifest_content_sha256"], "MANIFEST_CHANGED", "Installed manifest does not match import.")
    changed_objects = sorted(k for k, entity in state["objects"].items() if entity["version"] > imported["version"])
    drift = None
    if source_root is not None:
        source = _plain_ancestors(source_root)
        require(_digest({"legacy_root": str(source)}) == manifest["source_namespace"],
                "SOURCE_IDENTITY_MISMATCH", "Source relocation requires explicit identity mapping.")
        current = _inventory(source)
        drift = _differences(manifest["files"], current["files"])
        drift["exclusions_changed"] = manifest["exclusions"] != current["exclusions"]
    unchanged = drift is not None and not any(drift.values())
    return {"ok": True, "snapshot_id": data["snapshot_id"], "import_revision": imported["version"],
            "current_revision": state["revision"], "coverage": data["coverage"],
            "current_courses": [entity for entity in state["objects"].values() if entity["kind"] == "course"],
            "cursors": [entity for entity in state["objects"].values() if entity["kind"] == "cursor"],
            "rollback": {"source_difference": drift, "new_instance_changed_objects": changed_objects,
                         "may_return_to_unchanged_source": unchanged and not changed_objects,
                         "requires_reconciliation": bool(changed_objects) or not unchanged,
                         "last_common_snapshot_id": data["snapshot_id"],
                         "source_check": "verified" if drift is not None else "not_checked",
                         "route_changed": False}}
