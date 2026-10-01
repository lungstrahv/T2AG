"""Hash-linked local transaction journal, with immutable content-addressed blobs.

The operating-system lock is nonblocking and released when its handle/process
closes. POSIX uses flock and fsyncs containing directories after publication.
Windows uses msvcrt byte-range locking and FlushFileBuffers via os.fsync; Python
does not expose a portable directory fsync there. Filesystem/device guarantees
still apply: this is not a distributed lock or protection against an attacker
who can replace the journal and its validation code.

state.json is a rebuildable projection. transactions.jsonl is authoritative.
A write/fsync error after append begins has an unknown result: read/lookup before
retrying with the SAME request. Torn tails are never automatically truncated.

Routine replay checks the chain, asset-reference identities, existence, sizes
and committed stat signatures. Changed signatures trigger content revalidation.
It does not detect same-size corruption whose stat signature is unchanged; every
actual blob consumption and full validate hashes content. last_verification
reports this boundary and never promotes metadata checks to full asset health.
New commits hash their own referenced assets before publication. Legacy entries
without committed metadata remain readable with their reduced scope disclosed.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from .model import DomainError, key, require

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FORMAT = "t2ag.journal.v1"
_ENTRY_FIELDS = {"format", "instance_id", "sequence", "timestamp", "prev_hash", "request", "request_sha256", "effects", "hash"}


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise DomainError("INVALID_JSON", "Only finite UTF-8 JSON data is supported.") from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate JSON key")
        result[name] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant")


def _storage_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except OSError as exc:
            raise DomainError("STORAGE_IO_ERROR", "Local persistence I/O failed; inspect state before retrying a write.",
                              {"operation": function.__name__, "errno": exc.errno}) from exc
    return wrapped


class _ReadObjects(dict):
    """Named get/[] reads require versions; collection checks run under lock.

    Iteration/items/values intentionally do not bind every unrelated object.
    Domain planners must explicitly get named mutable decision dependencies.
    """
    def __init__(self, objects):
        super().__init__(objects)
        self.read_keys = set()

    def __getitem__(self, name):
        result = super().__getitem__(name)
        self.read_keys.add(name)
        return result

    def get(self, name, default=None):
        result = super().get(name, default)
        if super().__contains__(name):
            self.read_keys.add(name)
        return result


class Journal:
    def __init__(self, path):
        self.path = Path(path).absolute()
        self.log_path = self.path / "transactions.jsonl"
        self.blob_path = self.path / "blobs"
        self.projection_path = self.path / "state.json"
        self.last_verification = None

    def _fault(self, point):
        """Private fault-injection seam; production requests cannot select it."""

    @contextmanager
    def _lock(self):
        new_root = not self.path.exists()
        self.path.mkdir(parents=True, exist_ok=True)
        if new_root:
            self._directory_sync(self.path.parent)
        lock_path = self.path / ".writer.lock"
        require(not lock_path.is_symlink(), "UNSAFE_STORE", "Lock path must not be a symlink.")
        stream = lock_path.open("a+b")
        locked = False
        try:
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"0")
                stream.flush()
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
                raise DomainError("LOCK_BUSY", "Another writer/reader holds the instance lock; retry later.") from exc
            yield
        finally:
            if locked:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()

    def _directory_sync(self, path):
        if os.name != "nt":
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def _validate_request(self, request, initialization=False):
        require(isinstance(request, dict), "INVALID_REQUEST", "Request must be an object.")
        require(isinstance(request.get("request_id"), str) and bool(request["request_id"].strip()),
                "INVALID_REQUEST", "A stable request_id is required.")
        require(isinstance(request.get("action"), str) and bool(request["action"].strip()),
                "INVALID_REQUEST", "An action is required.")
        require(initialization or not request["request_id"].startswith("__journal_"),
                "RESERVED_REQUEST", "The journal initialization identity is reserved.")
        require(isinstance(request.get("payload"), dict), "INVALID_REQUEST", "Payload must be an object.")
        actor = request.get("actor")
        require(isinstance(actor, dict) and actor.get("role") in {"student", "teacher", "system", "external"},
                "INVALID_ACTOR", "An attributed actor role is required.")
        require(all(isinstance(actor.get(field), str) for field in ("source", "text")),
                "INVALID_ACTOR", "Actor source and text must be strings.")
        expected = request.get("expected")
        require(isinstance(expected, dict), "INVALID_EXPECTED", "Object version expectations are required.")
        for name, value in expected.items():
            require(isinstance(name, str) and "/" in name and type(value) is int and value >= 0,
                    "INVALID_EXPECTED", "Expected versions use kind/id keys and nonnegative integers.")
        _canonical(request)

    def _validate_effects(self, effects):
        require(isinstance(effects, list), "INVALID_EFFECTS", "Planner must return a list of put effects.")
        names = set()
        for effect in effects:
            require(isinstance(effect, dict) and set(effect) == {"op", "kind", "id", "data"}
                    and effect["op"] == "put" and isinstance(effect["data"], dict),
                    "INVALID_EFFECTS", "Only complete put effects are supported.")
            name = key(effect["kind"], effect["id"])
            require(name not in names, "DUPLICATE_EFFECT", "A transaction cannot put the same object twice.")
            names.add(name)
        _canonical(effects)
        return names

    def _check_expected(self, state, request, required_keys=()):
        expected = request["expected"]
        for name, number in expected.items():
            entity = state["objects"].get(name)
            require(entity is not None and entity["version"] == number,
                    "STALE_VERSION", f"Object version no longer matches: {name}")
        for name in required_keys:
            if name in state["objects"]:
                require(name in expected, "VERSION_REQUIRED", f"Expected version is required for: {name}")

    def _blob_refs(self, value):
        if isinstance(value, dict):
            if "blob_sha256" in value:
                digest = value["blob_sha256"]
                require(isinstance(digest, str) and _SHA.fullmatch(digest),
                        "INVALID_BLOB_REF", "blob_sha256 must be a lowercase SHA-256 digest.")
                ref = {"sha256": digest}
                if "bytes" in value:
                    require(type(value["bytes"]) is int and value["bytes"] >= 0,
                            "INVALID_BLOB_REF", "Asset byte count must be a nonnegative integer.")
                    ref["bytes"] = value["bytes"]
                yield ref
            if "blob_refs" in value:
                refs = value["blob_refs"]
                require(isinstance(refs, list), "INVALID_BLOB_REF", "blob_refs must be a list.")
                for ref in refs:
                    require(isinstance(ref, dict) and isinstance(ref.get("sha256"), str)
                            and _SHA.fullmatch(ref["sha256"]) and type(ref.get("bytes")) is int and ref["bytes"] >= 0,
                            "INVALID_BLOB_REF", "Each blob_refs item requires sha256 and byte count.")
                    yield ref
            for name, child in value.items():
                if name not in {"blob_sha256", "blob_refs"}:
                    yield from self._blob_refs(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._blob_refs(child)

    def _blob_stat(self, digest):
        require(isinstance(digest, str) and _SHA.fullmatch(digest),
                "INVALID_BLOB_REF", "A lowercase SHA-256 digest is required.")
        require(not self.blob_path.is_symlink(), "UNSAFE_STORE", "Blob directory must not be a symlink.")
        path = self.blob_path / digest
        require(path.is_file() and not path.is_symlink(), "BLOB_MISSING", f"Required asset is missing: {digest}")
        value = path.stat()
        return {"size": value.st_size, "mtime_ns": value.st_mtime_ns, "ctime_ns": value.st_ctime_ns,
                "inode": value.st_ino, "device": value.st_dev}

    def _verify_blob(self, digest, expected_bytes=None, return_bytes=False, return_snapshot=False):
        before = self._blob_stat(digest)
        path = self.blob_path / digest
        hasher = hashlib.sha256()
        size = 0
        content = bytearray() if return_bytes else None
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                hasher.update(chunk)
                if content is not None:
                    content.extend(chunk)
        require(hasher.hexdigest() == digest, "BLOB_CORRUPT", f"Asset hash mismatch: {digest}")
        require(expected_bytes is None or size == expected_bytes, "BLOB_SIZE_MISMATCH", f"Asset size mismatch: {digest}")
        require(self._blob_stat(digest) == before, "BLOB_CHANGED", "Asset metadata changed during content verification.")
        if return_snapshot:
            return {"bytes": size, "stat_signature": before}
        return bytes(content) if content is not None else size

    def _check_assets(self, effects, verified=None):
        verified = {} if verified is None else verified
        for effect in effects:
            for ref in self._blob_refs(effect["data"]):
                digest = ref["sha256"]
                if digest not in verified:
                    verified[digest] = self._verify_blob(digest, return_snapshot=True)
                require("bytes" not in ref or verified[digest]["bytes"] == ref["bytes"],
                        "BLOB_SIZE_MISMATCH", f"Asset size mismatch: {digest}")
        return verified

    def _asset_requirements(self, entry, requirements):
        refs = [ref for effect in entry["effects"] for ref in self._blob_refs(effect["data"])]
        for ref in refs:
            digest = ref["sha256"]
            requirement = requirements.setdefault(digest, {"bytes": None, "signature": None})
            if "bytes" in ref:
                require(requirement["bytes"] in (None, ref["bytes"]), "BLOB_SIZE_MISMATCH", "Conflicting historical asset byte counts.")
                requirement["bytes"] = ref["bytes"]
        if "assets" not in entry:
            return
        require(isinstance(entry["assets"], list), "JOURNAL_ASSETS", "Asset metadata must be a list.")
        declared = set()
        for asset in entry["assets"]:
            require(isinstance(asset, dict) and set(asset) == {"sha256", "bytes", "stat_signature"},
                    "JOURNAL_ASSETS", "Invalid committed asset metadata.")
            digest = asset["sha256"]
            require(isinstance(digest, str) and _SHA.fullmatch(digest) and digest not in declared,
                    "JOURNAL_ASSETS", "Invalid or duplicate committed asset identity.")
            declared.add(digest)
            signature = asset["stat_signature"]
            require(type(asset["bytes"]) is int and asset["bytes"] >= 0 and isinstance(signature, dict)
                    and set(signature) == {"size", "mtime_ns", "ctime_ns", "inode", "device"}
                    and all(type(value) is int and value >= 0 for value in signature.values())
                    and signature["size"] == asset["bytes"],
                    "JOURNAL_ASSETS", "Invalid asset size/stat signature.")
            require(digest in requirements and requirements[digest]["bytes"] in (None, asset["bytes"]),
                    "JOURNAL_ASSETS", "Committed asset identity/size conflicts with references.")
            requirements[digest].update(bytes=asset["bytes"], signature=signature)
        require(declared == {ref["sha256"] for ref in refs}, "JOURNAL_ASSETS", "Committed metadata must cover exactly the transaction asset references.")

    def _inspect_assets(self, requirements, full, verified_snapshots=None):
        sizes, changed, missing_metadata = {}, [], []
        hashed_bytes = 0
        hashed_count = 0
        for digest, requirement in requirements.items():
            signature = self._blob_stat(digest)
            require(requirement["bytes"] is None or signature["size"] == requirement["bytes"],
                    "BLOB_SIZE_MISMATCH", f"Asset size changed: {digest}")
            if requirement["bytes"] is None or requirement["signature"] is None:
                missing_metadata.append(digest)
            metadata_changed = requirement["signature"] is not None and signature != requirement["signature"]
            if metadata_changed:
                changed.append(digest)
            if full or metadata_changed:
                snapshot = self._verify_blob(digest, requirement["bytes"], return_snapshot=True)
                if verified_snapshots is not None:
                    verified_snapshots[digest] = snapshot
                hashed_count += 1
                hashed_bytes += signature["size"]
            sizes[digest] = signature["size"]
        self.last_verification = {
            "scope": "full_asset_content_hash" if full else "metadata_plus_changed_asset_hash" if changed else "asset_metadata",
            "log_chain": "verified", "reference_identities": "verified",
            "referenced_asset_count": len(requirements), "asset_content_hash_count": hashed_count,
            "asset_content_hash_bytes": hashed_bytes, "changed_assets_rehashed": changed,
            "legacy_assets_without_complete_metadata": missing_metadata,
            "full_asset_audit_pending": bool(requirements) and not full,
            "limitation": "Metadata checks cannot detect same-size/stat corruption; actual read_blob and full validate verify content.",
        }
        return sizes

    @staticmethod
    def _apply_effects(state, effects, sequence):
        for effect in effects:
            state["objects"][key(effect["kind"], effect["id"])] = {
                "kind": effect["kind"], "id": effect["id"], "version": sequence,
                "data": deepcopy(effect["data"]),
            }
        state["revision"] = sequence

    @staticmethod
    def _result(entry, replayed=False):
        return {"ok": True, "request_id": entry["request"]["request_id"],
                "revision": entry["sequence"], "replayed": replayed, "effects": deepcopy(entry["effects"])}

    def _read_locked(self, full_assets=False, verified_snapshots=None):
        require(not self.log_path.is_symlink(), "UNSAFE_STORE", "Transaction log must not be a symlink.")
        require(self.log_path.is_file(), "NOT_INITIALIZED", "Initialize this instance before use.")
        raw = self.log_path.read_bytes()
        require(bool(raw) and raw.endswith(b"\n"), "JOURNAL_TORN", "Transaction log has an empty or torn tail; explicit recovery is required.")
        state = {"revision": 0, "objects": {}}
        entries = []
        requests = {}
        previous = None
        identity = None
        requirements = {}
        for sequence, line in enumerate(raw.splitlines()):
            try:
                entry = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object,
                                   parse_constant=_reject_constant)
            except (ValueError, UnicodeError) as exc:
                raise DomainError("JOURNAL_CORRUPT", "Invalid UTF-8 JSON transaction.", {"sequence": sequence}) from exc
            require(isinstance(entry, dict) and set(entry) in (_ENTRY_FIELDS, _ENTRY_FIELDS | {"assets"}),
                    "JOURNAL_CORRUPT", "Unexpected transaction schema.")
            require(entry["format"] == _FORMAT and type(entry["sequence"]) is int and entry["sequence"] == sequence,
                    "JOURNAL_SEQUENCE", "Transaction sequence/format mismatch.")
            require(isinstance(entry["instance_id"], str) and bool(entry["instance_id"]),
                    "JOURNAL_IDENTITY", "Missing instance identity.")
            identity = entry["instance_id"] if identity is None else identity
            require(entry["instance_id"] == identity, "JOURNAL_IDENTITY", "Instance identity changed within journal.")
            require(entry["prev_hash"] == previous, "JOURNAL_CHAIN", "Previous transaction hash mismatch.")
            body = {name: value for name, value in entry.items() if name != "hash"}
            require(entry["hash"] == _sha(body), "JOURNAL_HASH", "Transaction hash mismatch.")
            self._validate_request(entry["request"], initialization=sequence == 0)
            require(entry["request_sha256"] == _sha(entry["request"]), "JOURNAL_REQUEST_HASH", "Request fingerprint mismatch.")
            request_id = entry["request"]["request_id"]
            require(request_id not in requests, "JOURNAL_DUPLICATE_REQUEST", "Duplicate committed request identity.")
            if sequence == 0:
                require(request_id == "__journal_initialize__" and entry["request"]["action"] == "__journal_initialize__",
                        "JOURNAL_GENESIS", "First transaction must initialize the instance.")
            names = self._validate_effects(entry["effects"])
            self._check_expected(state, entry["request"], names)
            self._asset_requirements(entry, requirements)
            self._apply_effects(state, entry["effects"], sequence)
            entries.append(entry)
            requests[request_id] = entry
            previous = entry["hash"]
        verified = self._inspect_assets(requirements, full_assets, verified_snapshots)
        self.last_verification.update(instance_id=identity, revision=state["revision"])
        return state, entries, requests, verified

    def _entry(self, state, entries, request, effects, verified_assets):
        for digest, snapshot in verified_assets.items():
            require(self._blob_stat(digest) == snapshot["stat_signature"], "BLOB_CHANGED", "Asset changed after its content verification; transaction not published.")
        entry = {
            "format": _FORMAT,
            "instance_id": entries[0]["instance_id"] if entries else str(uuid.uuid4()),
            "sequence": state["revision"] + 1 if entries else 0,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "prev_hash": entries[-1]["hash"] if entries else None,
            "request": deepcopy(request), "request_sha256": _sha(request), "effects": deepcopy(effects),
            "assets": [{"sha256": digest, **deepcopy(snapshot)}
                       for digest, snapshot in sorted(verified_assets.items())],
        }
        entry["hash"] = _sha(entry)
        return entry

    def _project(self, state):
        self._fault("before_projection")
        temp = self.path / (".state-" + uuid.uuid4().hex + ".tmp")
        with temp.open("xb") as stream:
            stream.write(_canonical(state) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.projection_path)
        self._directory_sync(self.path)

    def _commit(self, state, entry):
        try:
            self._fault("before_append")
        except OSError as exc:
            raise DomainError("COMMIT_NOT_PUBLISHED", "Transaction append was not started.",
                              {"request_id": entry["request"]["request_id"]}) from exc
        for asset in entry["assets"]:
            require(self._blob_stat(asset["sha256"]) == asset["stat_signature"],
                    "BLOB_CHANGED", "Asset changed before transaction append; transaction not published.")
        started = False
        try:
            raw = _canonical(entry) + b"\n"
            mode = "xb" if entry["sequence"] == 0 else "ab"
            with self.log_path.open(mode) as stream:
                started = True
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self._directory_sync(self.path)
            self._fault("after_commit")
            self._apply_effects(state, entry["effects"], entry["sequence"])
            self._project(state)
        except Exception as exc:
            if started:
                raise DomainError("COMMIT_UNKNOWN", "Transaction publication may have succeeded; lookup or retry the same request after validation.",
                                  {"request_id": entry["request"]["request_id"], "candidate_revision": entry["sequence"]}) from exc
            raise

    @_storage_errors
    def initialize(self, profile=None):
        require(profile is None or isinstance(profile, dict), "INVALID_PROFILE", "Initial profile must be an object or null.")
        _canonical(profile)
        with self._lock():
            if self.log_path.exists():
                state, entries, _, _ = self._read_locked()
                if profile is not None:
                    require(entries[0]["request"]["payload"]["profile"] == profile,
                            "INITIALIZATION_CONFLICT", "This instance was initialized with a different profile.")
                return deepcopy(state)
            request = {"request_id": "__journal_initialize__", "action": "__journal_initialize__",
                       "payload": {"profile": deepcopy(profile)},
                       "actor": {"role": "system", "source": "Journal.initialize caller",
                                 "text": "Caller supplied initialization data; no student agreement is inferred."},
                       "expected": {}}
            effects = [{"op": "put", "kind": "student", "id": "current", "data": deepcopy(profile)}] if profile is not None else []
            verified_assets = self._check_assets(effects)
            state = {"revision": 0, "objects": {}}
            entry = self._entry(state, [], request, effects, verified_assets)
            self._commit(state, entry)
            return deepcopy(state)

    @_storage_errors
    def read_state(self):
        with self._lock():
            return deepcopy(self._read_locked()[0])

    @_storage_errors
    def lookup(self, request_id):
        require(isinstance(request_id, str) and bool(request_id), "INVALID_REQUEST", "Request ID is required.")
        with self._lock():
            entry = self._read_locked()[2].get(request_id)
            return self._result(entry, replayed=True) if entry else None

    @_storage_errors
    def apply(self, request, planner):
        self._validate_request(request)
        request = deepcopy(request)
        with self._lock():
            state, entries, requests, _ = self._read_locked()
            previous = requests.get(request["request_id"])
            if previous is not None:
                require(previous["request_sha256"] == _sha(request),
                        "REQUEST_ID_REUSED", "A request ID cannot be reused with a different request.")
                return self._result(previous, replayed=True)
            self._check_expected(state, request)
            planned_state = deepcopy(state)
            tracked = _ReadObjects(planned_state["objects"])
            planned_state["objects"] = tracked
            effects = planner(planned_state, deepcopy(request))
            require(_canonical(planned_state) == _canonical(state), "PLANNER_MUTATED_STATE", "Planner must return effects without changing input state.")
            names = self._validate_effects(effects)
            self._check_expected(state, request, names | tracked.read_keys)
            verified_assets = self._check_assets(effects)
            entry = self._entry(state, entries, request, effects, verified_assets)
            self._commit(state, entry)
            return self._result(entry)

    @_storage_errors
    def rebind_assets(self, request_id):
        """Explicit relocation maintenance: hash every historical reference.

        Publish the verified current stat signatures in one normal chained
        transaction. Old journal bytes and learning objects are preserved.
        Nothing from a disk cache or caller-supplied asset list is trusted.
        Actual blob reads and full validation continue to hash content.
        """
        request = {"request_id": request_id, "action": "maintenance.rebind_assets",
                   "payload": {"scope": "all_historical_asset_references"},
                   "actor": {"role": "system", "source": "Journal.rebind_assets caller",
                             "text": "Explicitly verify and bind current asset metadata; no learning or permission decision."},
                   "expected": {}}
        self._validate_request(request)
        with self._lock():
            snapshots = {}
            # One pass verifies the chain, complete historical reference union,
            # bytes and exact stat snapshots. Even a retry validates current
            # storage health; it never expands or replaces the prior binding.
            state, entries, requests, sizes = self._read_locked(full_assets=True, verified_snapshots=snapshots)
            previous = requests.get(request_id)
            if previous is not None:
                require(previous["request_sha256"] == _sha(request), "REQUEST_ID_REUSED", "A request ID cannot be reused with a different maintenance request.")
                return {**self._result(previous, replayed=True), "verification": deepcopy(self.last_verification)}
            require(set(snapshots) == set(sizes), "ASSET_VERIFICATION_INCOMPLETE", "Every historical asset must have a verified current snapshot.")
            refs = [{"sha256": digest, "bytes": snapshots[digest]["bytes"]} for digest in sorted(snapshots)]
            data = {"purpose": "relocation_metadata_rebind", "instance_id": entries[0]["instance_id"],
                    "prior_revision": state["revision"], "prior_head_sha256": entries[-1]["hash"],
                    "scope": "all_historical_asset_references", "blob_refs": refs,
                    "reference_set_sha256": _sha(refs), "verified_asset_count": len(refs),
                    "verified_asset_bytes": sum(ref["bytes"] for ref in refs),
                    "content_verification": "full_sha256", "authorization_effects": False}
            effects = [{"op": "put", "kind": "asset_verification", "id": request_id, "data": data}]
            names = self._validate_effects(effects)
            self._check_expected(state, request, names)
            self._fault("after_asset_verification")
            entry = self._entry(state, entries, request, effects, snapshots)
            self._commit(state, entry)
            self.last_verification.update(revision=state["revision"])
            return {**self._result(entry), "verification": deepcopy(self.last_verification)}

    @_storage_errors
    def validate(self):
        with self._lock():
            state, entries, _, verified = self._read_locked(full_assets=True)
            installed = {path.name for path in self.blob_path.iterdir() if path.is_file() and _SHA.fullmatch(path.name)} if self.blob_path.exists() else set()
            pending = sorted(path.name for path in self.blob_path.glob(".pending-*")) if self.blob_path.exists() else []
            return {"ok": True, "instance_id": entries[0]["instance_id"], "revision": state["revision"],
                    "transactions": len(entries), "objects": len(state["objects"]), "head_sha256": entries[-1]["hash"],
                    "referenced_blobs": len(verified), "unreferenced_blobs": sorted(installed - verified.keys()),
                    "pending_assets": pending,
                    "verification": deepcopy(self.last_verification),
                    "durability": "file fsync + atomic blob replace; directory fsync on POSIX; Windows directory persistence not portable"}

    def _put_stream(self, source):
        with self._lock():
            require(not self.blob_path.is_symlink(), "UNSAFE_STORE", "Blob directory must not be a symlink.")
            self.blob_path.mkdir(exist_ok=True)
            temp = self.blob_path / (".pending-" + uuid.uuid4().hex)
            hasher = hashlib.sha256()
            count = 0
            with temp.open("xb") as target:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)
                    count += len(chunk)
                    hasher.update(chunk)
                    self._fault("asset_partial_write")
                target.flush()
                os.fsync(target.fileno())
            digest = hasher.hexdigest()
            # Re-read the complete flushed temporary file before installation.
            check = hashlib.sha256()
            checked_bytes = 0
            with temp.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    check.update(chunk)
                    checked_bytes += len(chunk)
            require(check.hexdigest() == digest and checked_bytes == count, "BLOB_WRITE_CORRUPT", "Temporary asset failed readback verification.")
            self._fault("asset_flushed")
            destination = self.blob_path / digest
            if destination.exists():
                self._verify_blob(digest, count)
                temp.unlink()
            else:
                os.replace(temp, destination)
            self._directory_sync(self.blob_path)
            self._directory_sync(self.path)
            self._fault("asset_installed")
            return {"sha256": digest, "bytes": count}

    @_storage_errors
    def put_blob(self, content):
        import io
        require(isinstance(content, bytes), "INVALID_BLOB", "put_blob requires bytes.")
        return self._put_stream(io.BytesIO(content))

    @_storage_errors
    def put_file(self, path):
        path = Path(path)
        before = path.stat()
        with path.open("rb") as source:
            result = self._put_stream(source)
        after = path.stat()
        require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
                "SOURCE_CHANGED", "Source file changed during asset installation; installed blob is unreferenced residue.")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        final = path.stat()
        require(digest.hexdigest() == result["sha256"] and
                (after.st_size, after.st_mtime_ns) == (final.st_size, final.st_mtime_ns),
                "SOURCE_CHANGED", "Source no longer matches installed bytes; installed blob is unreferenced residue.")
        return result

    @_storage_errors
    def read_blob(self, sha256):
        with self._lock():
            content = self._verify_blob(sha256, return_bytes=True)
            self.last_verification = {"scope": "single_asset_content_hash", "sha256": sha256,
                                      "bytes": len(content), "full_asset_audit_pending": True}
            return content
