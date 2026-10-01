"""Non-overwriting distribution, installation, read-only projection and OKF export."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from . import __version__
from .journal import Journal
from .model import DomainError, require, parse_json
from .support import digest

PUBLIC_DOCS = ("README.md", "docs/user-guide.zh.md", "docs/user-guide.en.md", "docs/protocol.md", "docs/domain-model.md", "docs/runtime-entry.md", "docs/access-authority.md")
PUBLIC_DOCS += ("docs/control-boundaries.md",)
PUBLIC_DOCS += ("docs/task-loops.md",)
PUBLIC_DOCS += ("LICENSE", "LICENSE-DOCS.md", "LICENSING.md", "NOTICE")
REQUIRED_RUNTIME = {"t2ag_next/" + name + ".py" for name in ("__init__", "__main__", "cli", "model", "journal", "support", "learning", "service", "exchange", "reading_bridge", "distribution", "migration", "assets", "groups", "reconciliation", "planning", "cloud")}
REQUIRED_RUNTIME.add("t2ag_next/migration_recovery.py")
REQUIRED_RUNTIME.add("t2ag_next/governance.py")
REQUIRED_RUNTIME.add("t2ag_next/distribution_projection.py")
REQUIRED_RUNTIME.add("t2ag_next/continuity.py")
REQUIRED_RUNTIME.add("t2ag_next/workflows.py")
PRIVACY_PATTERNS = (r"(?i)[a-z]:[\\/]Users[\\/][\w .-]+[\\/]", r"/Users/[\w .-]+/", r"/home/[\w .-]+/",
                    r"(?i)(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*[\"']?[A-Za-z0-9_-]{12,}",
                    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _plain_source(path, root):
    root = Path(root).absolute()
    path = Path(path).absolute()
    require(path == root or root in path.parents, "SOURCE_ESCAPE", "Public source must be inside the declared root.")
    for parent in (path, *path.parents):
        require(parent.exists(), "DISTRIBUTION_SOURCE", "Declared source path does not exist.")
        stat = parent.lstat()
        require(not parent.is_symlink() and not (getattr(stat, "st_file_attributes", 0) & 0x400), "SOURCE_LINK", "Public sources cannot traverse linked or reparse paths.")
    return path


def _safe_name(name):
    p = PurePosixPath(name)
    require(name and not p.is_absolute() and "\\" not in name and all(x not in ("", ".", "..") for x in name.split("/")), "PACKAGE_PATH", "Unsafe package path.")
    require(not any(":" in x or x.endswith((".", " ")) or x.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{n}" for n in range(1, 10)], *[f"LPT{n}" for n in range(1, 10)]} for x in p.parts), "PACKAGE_PATH", "Nonportable package path.")
    return p


def _destination(path, source=None):
    target = Path(path).absolute()
    for p in (target, *target.parents):
        if p.exists():
            info = p.lstat()
            require(not p.is_symlink() and not (getattr(info, "st_file_attributes", 0) & 0x400), "UNSAFE_DESTINATION", "Linked/reparse destinations are rejected.")
    require(not target.exists(), "DESTINATION_EXISTS", "Choose an unused destination; existing data is never merged or overwritten.")
    if source:
        src = Path(source).resolve()
        resolved = target.resolve()
        require(resolved != src and src not in resolved.parents and resolved not in src.parents, "DESTINATION_OVERLAP", "The output must be outside the source tree.")
    require(target.parent.is_dir(), "DESTINATION_PARENT", "Output parent must already exist.")
    return target


def privacy_check(files, forbidden_terms=()):
    findings = []
    for name, data in files.items():
        text = data.decode("utf-8")
        for pattern in PRIVACY_PATTERNS:
            if re.search(pattern, text):
                findings.append({"file": name, "reason": "private_path_or_secret_pattern"})
        for term in forbidden_terms:
            if term and term.casefold() in text.casefold():
                findings.append({"file": name, "reason": "explicit_private_term"})
    require(not findings, "PRIVACY_LEAK", f"Pre-write privacy check rejected {len(findings)} finding(s): {findings}")


def source_files(root):
    root = _plain_source(root, root)
    files = {}
    for file in sorted((root / "t2ag_next").glob("*.py")):
        _plain_source(file, root)
        files[file.relative_to(root).as_posix()] = file.read_bytes()
    for name in ("pyproject.toml", *PUBLIC_DOCS):
        path = root / name
        _plain_source(path, root)
        require(path.is_file() and not path.is_symlink(), "DISTRIBUTION_SOURCE", f"Missing declared distribution source: {name}")
        files[name] = path.read_bytes()
    require(REQUIRED_RUNTIME <= set(files), "INCOMPLETE_RUNTIME", "The public runtime closure is incomplete.")
    files["AGENTS.md"] = files["docs/runtime-entry.md"]
    return files


def build_distribution(root, output, *, forbidden_terms=()):
    target = _destination(output, root)
    files = source_files(root)
    privacy_check(files, forbidden_terms)
    manifest = {"schema": "t2ag.distribution.v1", "version": __version__, "editions": ["zh", "en"],
                "implementation_status": "candidate", "review_status": "not_finalized", "release_status": "unreleased",
                "files": {name: {"sha256": _sha(data), "bytes": len(data)} for name, data in files.items()}}
    manifest["content_sha256"] = digest(manifest["files"])
    fd, temporary = tempfile.mkstemp(prefix=".t2ag-package-", dir=target.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
        with open(temporary, "r+b") as file:
            os.fsync(file.fileno())
        require(not target.exists(), "DESTINATION_EXISTS", "Destination appeared while building; refusing overwrite.")
        os.rename(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"ok": True, "path": str(target), "sha256": _sha(target.read_bytes()), "manifest": manifest}


def verify_distribution(package):
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        require(len({n.casefold() for n in names}) == len(names), "PACKAGE_COLLISION", "Duplicate or case-colliding package entries.")
        for info in infos:
            _safe_name(info.filename)
            require(info.file_size <= 16 * 1024 * 1024 and (info.external_attr >> 16) & 0o170000 != 0o120000, "PACKAGE_ENTRY", "Oversized or linked entry is not a runtime file.")
        require(sum(info.file_size for info in infos) <= 128 * 1024 * 1024, "PACKAGE_SIZE", "Runtime package is unexpectedly large.")
        require("manifest.json" in names, "PACKAGE_MANIFEST", "A runtime package needs its manifest.")
        manifest = parse_json(archive.read("manifest.json"))
        require(isinstance(manifest, dict) and isinstance(manifest.get("files"), dict), "PACKAGE_MANIFEST", "A runtime manifest must describe its files.")
        require(isinstance(manifest.get("version"), str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[.-][A-Za-z0-9.]+)?", manifest["version"]) and manifest.get("editions") == ["zh", "en"], "PACKAGE_PROFILE", "The runtime needs an explicit version and both declared editions.")
        require(REQUIRED_RUNTIME | {"AGENTS.md", "pyproject.toml", *PUBLIC_DOCS} <= set(manifest["files"]), "INCOMPLETE_RUNTIME", "The package cannot run without its declared modules and operating documents.")
        require(manifest.get("schema") == "t2ag.distribution.v1" and manifest.get("content_sha256") == digest(manifest.get("files")), "PACKAGE_MANIFEST", "Invalid distribution manifest.")
        require(set(names) == set(manifest["files"]) | {"manifest.json"}, "PACKAGE_INVENTORY", "Unmanifested or missing runtime entries.")
        allowed_docs = {"AGENTS.md", "pyproject.toml", *PUBLIC_DOCS}
        for name, expected in manifest["files"].items():
            parts = PurePosixPath(name).parts
            require(name in allowed_docs or (len(parts) == 2 and parts[0] == "t2ag_next" and parts[1].endswith(".py")), "PACKAGE_SCOPE", "Manifest includes a file outside the public runtime contract.")
            require(isinstance(expected, dict) and set(expected) == {"sha256", "bytes"}, "PACKAGE_MANIFEST", "Invalid file metadata.")
            data = archive.read(name)
            require(len(data) == expected["bytes"] and _sha(data) == expected["sha256"], "PACKAGE_HASH", "Runtime content changed.")
        require(archive.read("AGENTS.md") == archive.read("docs/runtime-entry.md"), "ENTRY_DRIFT", "The installed entry must derive from the public runtime protocol.")
        return manifest


def install(package, destination, language, *, reuse_instance=None):
    require(language in ("zh", "en"), "LANGUAGE_REQUIRED", "Choose zh or en; there is no default edition.")
    target = _destination(destination)
    frozen_package = Path(package).read_bytes()
    manifest = verify_distribution(io.BytesIO(frozen_package))
    stage = Path(tempfile.mkdtemp(prefix=".t2ag-install-", dir=target.parent))
    with zipfile.ZipFile(io.BytesIO(frozen_package)) as archive:
        for name in manifest["files"]:
            path = stage.joinpath(*_safe_name(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as file:
                file.write(archive.read(name)); file.flush(); os.fsync(file.fileno())
    if reuse_instance is None:
        Journal(stage / "instance").initialize({"language": language, "facts_status": "not_provided"})
        instance_path = target / "instance"
        identity = Journal(stage / "instance").validate()["instance_id"]
    else:
        instance_path = Path(reuse_instance).resolve()
        require(instance_path != target and instance_path not in target.parents and target not in instance_path.parents, "UPGRADE_OVERLAP", "New runtime and existing instance must be separate.")
        validation = Journal(instance_path).validate()
        identity = validation["instance_id"]
        student = Journal(instance_path).read_state()["objects"].get("student/current", {}).get("data", {})
        require(student.get("language", language) == language, "LANGUAGE_CONFLICT", "Upgrade retains the chosen learner language.")
    (stage / "installation.json").write_text(json.dumps({"language": language, "package_sha256": _sha(frozen_package),
        "version": manifest["version"], "content_sha256": manifest["content_sha256"], "instance_path": str(instance_path), "instance_id": identity}, indent=2), encoding="utf-8")
    require(not target.exists(), "DESTINATION_EXISTS", "Destination appeared during installation; staging is retained for inspection.")
    os.rename(stage, target)
    return {"ok": True, "path": str(target), "language": language, "instance": str(instance_path),
            "version": manifest["version"], "source_retained": True}


def upgrade(package, current_installation, destination):
    """Install a separate runtime that points to the same verified instance.

    This performs no data-format conversion and no authority switch. It preserves
    both installations and refuses unsupported instance formats through validate.
    """
    current = Path(current_installation).resolve()
    installation = parse_json((current / "installation.json").read_bytes())
    require(isinstance(installation, dict) and installation.get("language") in ("zh", "en"), "INSTALLATION_PROFILE", "Current installation needs its explicit language.")
    _destination(destination, current)
    instance_path = Path(installation.get("instance_path", current / "instance")).resolve()
    store = Journal(instance_path)
    before = store.validate()
    require(installation.get("instance_id", before["instance_id"]) == before["instance_id"], "INSTANCE_IDENTITY", "The installation points to a different instance.")
    original_log_sha = _sha(store.log_path.read_bytes())
    result = install(package, destination, installation["language"], reuse_instance=instance_path)
    result.update(previous_installation=str(current), instance_id=before["instance_id"],
                  instance_unchanged=original_log_sha == _sha(store.log_path.read_bytes()),
                  authority_switched=False, next_action="Open the new runtime explicitly; keep the previous installation for recovery.")
    return result


def lite_projection(root, destination, *, write=False):
    from .distribution_projection import lite_projection as project
    return project(root, destination, write=write)


def okf_export(root, destination=None, *, course_definition=None, forbidden_terms=(), write=False):
    from .distribution_projection import okf_export as project
    return project(root, destination, course_definition=course_definition,
                   forbidden_terms=forbidden_terms, write=write)


def build_guide(root, destination, language):
    require(language in ("zh", "en"), "LANGUAGE_REQUIRED", "Choose the guide language.")
    target = _destination(destination, root)
    source = _plain_source(Path(root) / f"docs/user-guide.{language}.md", root).read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", source)
    navigation, content = [], []
    for idx, section in enumerate(sections):
        title, _, body = section.partition("\n")
        label = title.lstrip("# ")
        navigation.append(f'<a href="#s{idx}">{html.escape(label)}</a>')
        chunks = re.split(r"(?m)^```[^\n]*\n|^```\s*$", body)
        rendered = []
        for number, chunk in enumerate(chunks):
            if number % 2:
                rendered.append('<pre tabindex="0"><code>' + html.escape(chunk.strip("\n")) + '</code></pre>')
            else:
                for paragraph in re.split(r"\n\s*\n", chunk.strip()):
                    if paragraph.strip():
                        escaped = html.escape(paragraph.strip())
                        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
                        rendered.append("<p>" + escaped.replace("\n", "<br>") + "</p>")
        content.append(f'<section id="s{idx}"><h2>{html.escape(label)}</h2>{"".join(rendered)}</section>')
    document = '<!doctype html><html lang="' + language + '"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>T2AG Guide</title><style>body{max-width:72rem;margin:2rem auto;font:18px/1.8 system-ui;padding:1rem;color:#18212b;background:#f6f8fa}nav{display:flex;gap:.7rem;flex-wrap:wrap}nav a{padding:.35rem .8rem;background:white;border:1px solid #cdd6e0;border-radius:.5rem;color:#174b75;text-decoration:none}section{margin-top:2.2rem;padding:1.6rem 2rem;background:white;border:1px solid #dce2e8;border-radius:.8rem}p{max-width:78ch}pre{white-space:pre;overflow:auto;padding:1.2rem;background:#edf3f8;border-left:4px solid #327b9a;font:15px/1.8 Consolas,monospace}code{font-family:Consolas,monospace}h2{line-height:1.4;color:#153f5f}@media(max-width:600px){body{font-size:16px;margin:.5rem}section{padding:1rem}pre{font-size:13px}}</style><nav aria-label="Guide sections">' + "".join(navigation) + "</nav><main>" + "".join(content) + "</main></html>"
    with target.open("x", encoding="utf-8") as output:
        output.write(document)
        output.flush()
        os.fsync(output.fileno())
    return {"ok": True, "path": str(target), "generated_from": f"docs/user-guide.{language}.md", "authority": False}
