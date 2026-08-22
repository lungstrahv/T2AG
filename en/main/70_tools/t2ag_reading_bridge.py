#!/usr/bin/env python3
"""T2AG-owned side of the JSON-only reading bridge V1 saga."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterator

from contracts.reading_bridge_v1.validator import (
    ContractError,
    canonical_json_bytes,
    load_json_strict,
    semantic_sha256,
    validate_document,
)


class BridgeError(RuntimeError):
    pass


AR_RE = re.compile(r"AR-[0-9]{4}")
RECEIPT_RE = re.compile(r"RCP-[A-Z0-9]{16,64}")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def project_root(value: str | None) -> Path:
    root = Path(value).resolve() if value else Path(__file__).resolve().parents[2]
    if not (root / "main/10_student/activities").is_dir():
        raise BridgeError(f"invalid T2AG root: {root}")
    return root


def schema_root(root: Path) -> Path:
    return root / "main/70_tools/contracts/reading_bridge_v1"


def schema_for(root: Path, name: str) -> dict[str, Any]:
    value = load_json_strict(schema_root(root) / f"{name}.schema.json")
    if not isinstance(value, dict):
        raise BridgeError(f"schema is not an object: {name}")
    return value


def frontmatter(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---(?:\n|$)", content, re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def find_reading_ar(root: Path, activity_id: str) -> Path:
    if AR_RE.fullmatch(activity_id) is None:
        raise BridgeError(f"invalid ActivityRecord ID: {activity_id}")
    matches = sorted((root / "main/10_student/activities/reading").glob(f"{activity_id}_*.md"))
    if len(matches) != 1:
        raise BridgeError(f"reading ActivityRecord must resolve exactly once: {activity_id}")
    carrier = matches[0]
    if carrier.is_symlink():
        raise BridgeError("symlink/reparse ActivityRecord refused")
    meta = frontmatter(carrier)
    if (
        meta.get("type") != "activity_record"
        or meta.get("activity_kind") != "reading"
        or meta.get("activity_record_id") != activity_id
    ):
        raise BridgeError(f"ActivityRecord identity mismatch: {activity_id}")
    return carrier


def context_path(carrier: Path, activity_id: str) -> Path:
    return carrier.with_name(f"{activity_id}.context.json")


def ledger_path(carrier: Path, activity_id: str) -> Path:
    return carrier.with_name(f"{activity_id}.contributions.json")


def consumer_path(root: Path, uri: str) -> Path:
    prefix = "t2ag://path/"
    if not uri.startswith(prefix):
        raise BridgeError("consumer_uri must use t2ag://path/<repository-relative-path>")
    relative = uri[len(prefix):]
    if (
        not relative
        or "\\" in relative
        or "%" in relative
        or ":" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise BridgeError("consumer_uri contains an invalid repository-relative path")
    path = root.joinpath(*relative.split("/"))
    if not path.is_file() or path.is_symlink():
        raise BridgeError("consumer_uri local use position does not exist")
    return path


def empty_ledger(activity_id: str) -> dict[str, Any]:
    return {
        "schema": "t2ag.reading_contribution_ledger.v1",
        "activity_record_id": activity_id,
        "processed_events": [],
        "contributions": [],
        "receipt_outbox": [],
    }


def _lock_name(root: Path, carrier: str) -> Path:
    key = hashlib.sha256(f"{root.resolve()}\0{carrier}".encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / f"t2ag-reading-bridge-{key}.lock"


@contextlib.contextmanager
def file_lock(root: Path, carrier: str) -> Iterator[None]:
    path = _lock_name(root, carrier)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _fault(point: str) -> None:
    if os.environ.get("T2AG_BRIDGE_FAIL_AT") == point:
        raise BridgeError(f"injected failure at {point}")


def atomic_store(path: Path, value: dict[str, Any]) -> bool:
    content = canonical_json_bytes(value) + b"\n"
    old = path.read_bytes() if path.exists() else None
    old_stat = path.stat() if path.exists() else None
    if old == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _fault("before_replace")
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            _fault("after_replace")
        except BridgeError:
            if old is None:
                path.unlink(missing_ok=True)
            else:
                rollback = path.with_name(f".{path.name}.{uuid.uuid4().hex}.rollback")
                with rollback.open("xb") as handle:
                    handle.write(old)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(rollback, path)
                if old_stat is not None:
                    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
            raise
        return True
    finally:
        temporary.unlink(missing_ok=True)


def validate_semantic(document: dict[str, Any], object_field: str | None = None, prefix: str = "") -> None:
    actual = semantic_sha256(document)
    if document.get("semantic_sha256") != actual:
        raise BridgeError("semantic_sha256 mismatch")
    if object_field and document.get(object_field) != prefix + actual:
        raise BridgeError(f"{object_field} is not derived from semantic_sha256")


def read_ledger(root: Path, carrier: Path, activity_id: str) -> dict[str, Any]:
    path = ledger_path(carrier, activity_id)
    if not path.exists():
        return empty_ledger(activity_id)
    value = load_json_strict(path)
    if not isinstance(value, dict):
        raise BridgeError("contribution ledger must be an object")
    validate_document(value, schema_for(root, "t2ag.reading_contribution_ledger.v1"))
    if value.get("activity_record_id") != activity_id:
        raise BridgeError("contribution ledger ActivityRecord mismatch")
    event_ids: set[str] = set()
    contribution_ids: set[str] = set()
    for event in value["processed_events"]:
        if event["event_id"] in event_ids:
            raise BridgeError("duplicate processed event")
        event_ids.add(event["event_id"])
    for row in value["contributions"]:
        if row["contribution_id"] in contribution_ids or row["contribution_id"] != row["payload"]["contribution_id"]:
            raise BridgeError("duplicate or mismatched contribution")
        contribution_ids.add(row["contribution_id"])
        validate_semantic(row["payload"], "contribution_id", "CON-")
        if row["payload"]["target_activity_record_id"] != activity_id:
            raise BridgeError("contribution target ActivityRecord mismatch")
    if any(event["contribution_id"] not in contribution_ids for event in value["processed_events"]):
        raise BridgeError("dangling processed event")
    payload_by_contribution = {
        row["contribution_id"]: row["payload"]
        for row in value["contributions"]
    }
    if any(
        event["semantic_sha256"]
        != payload_by_contribution[event["contribution_id"]]["semantic_sha256"]
        for event in value["processed_events"]
    ):
        raise BridgeError("processed event semantic digest mismatch")
    receipt_ids: set[str] = set()
    for row in value["receipt_outbox"]:
        if row["receipt_id"] in receipt_ids or row["receipt_id"] != row["payload"]["receipt_id"]:
            raise BridgeError("duplicate or mismatched receipt outbox")
        receipt_ids.add(row["receipt_id"])
        validate_semantic(row["payload"])
        if row["payload"]["event_id"] != row["receipt_id"]:
            raise BridgeError("receipt event_id must equal receipt_id")
        if row["payload"]["target_activity_record_id"] != activity_id:
            raise BridgeError("receipt target ActivityRecord mismatch")
        if row["payload"]["contribution_id"] not in contribution_ids:
            raise BridgeError("receipt contribution is dangling")
        if (row["status"] == "pending") != (row["ack_result"] is None):
            raise BridgeError("receipt status/ack mismatch")
    return value


def context_export(args: argparse.Namespace) -> dict[str, Any]:
    root = project_root(args.root)
    carrier = find_reading_ar(root, args.activity)
    source_path = context_path(carrier, args.activity)
    if source_path.exists():
        source = load_json_strict(source_path)
        if not isinstance(source, dict):
            raise BridgeError("context source must be an object")
        validate_document(source, schema_for(root, "t2ag.reading_context_source.v1"))
        if source["activity_record_id"] != args.activity:
            raise BridgeError("context source ActivityRecord mismatch")
        if source["target_reading_uri"] is None and (
            source["reading_intents"] or source["questions_or_observation_cues"] or source["course_id"] is not None
        ):
            raise BridgeError("context without reading URI must be empty")
        target_uri = source["target_reading_uri"]
        course_id = source["course_id"]
        intents = source["reading_intents"]
        cues = source["questions_or_observation_cues"]
    else:
        target_uri, course_id, intents, cues = None, None, [], []
    payload: dict[str, Any] = {
        "schema": "t2ag.reading_context.v1",
        "event_id": args.event_id,
        "generated_at": args.generated_at or utc_now(),
        "producer": "t2ag",
        "semantic_sha256": "",
        "export_id": "",
        "activity_record_id": args.activity,
        "target_reading_uri": target_uri,
        "course_id": course_id,
        "reading_intents": intents,
        "questions_or_observation_cues": cues,
    }
    digest = semantic_sha256(payload)
    payload["semantic_sha256"] = digest
    payload["export_id"] = f"CTX-{digest}"
    validate_document(payload, schema_for(root, "t2ag.reading_context.v1"))
    validate_semantic(payload, "export_id", "CTX-")
    return payload


def contribution_import(args: argparse.Namespace) -> dict[str, Any]:
    root = project_root(args.root)
    payload = load_json_strict(Path(args.file))
    if not isinstance(payload, dict):
        raise BridgeError("contribution payload must be an object")
    validate_document(payload, schema_for(root, "reading.t2ag_contribution.v1"))
    validate_semantic(payload, "contribution_id", "CON-")
    activity_id = payload["target_activity_record_id"]
    carrier = find_reading_ar(root, activity_id)
    if payload["source_reading_uri"] != payload["evidence_locator"]["source_uri"]:
        raise BridgeError("source URI/evidence locator mismatch")
    path = ledger_path(carrier, activity_id)
    with file_lock(root, path.as_posix()):
        ledger = read_ledger(root, carrier, activity_id)
        existing_event = next((row for row in ledger["processed_events"] if row["event_id"] == payload["event_id"]), None)
        if existing_event:
            if existing_event["semantic_sha256"] != payload["semantic_sha256"]:
                raise BridgeError("ID_CONFLICT")
            return {"event_id": payload["event_id"], "contribution_id": existing_event["contribution_id"], "result": "already_processed"}
        existing_object = next((row for row in ledger["contributions"] if row["contribution_id"] == payload["contribution_id"]), None)
        if existing_object and existing_object["payload"]["semantic_sha256"] != payload["semantic_sha256"]:
            raise BridgeError("ID_CONFLICT")
        result = "already_present" if existing_object else "imported"
        if not existing_object:
            ledger["contributions"].append({"contribution_id": payload["contribution_id"], "payload": payload})
            ledger["contributions"].sort(key=lambda row: row["contribution_id"])
        ledger["processed_events"].append({
            "event_id": payload["event_id"],
            "semantic_sha256": payload["semantic_sha256"],
            "contribution_id": payload["contribution_id"],
        })
        ledger["processed_events"].sort(key=lambda row: row["event_id"])
        validate_document(ledger, schema_for(root, "t2ag.reading_contribution_ledger.v1"))
        atomic_store(path, ledger)
        return {"event_id": payload["event_id"], "contribution_id": payload["contribution_id"], "result": result}


def all_ledgers(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    result: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted((root / "main/10_student/activities/reading").glob("AR-[0-9][0-9][0-9][0-9].contributions.json")):
        activity_id = path.name.split(".", 1)[0]
        carrier = find_reading_ar(root, activity_id)
        result.append((path, read_ledger(root, carrier, activity_id)))
    return result


def receipt_prepare(args: argparse.Namespace) -> dict[str, Any]:
    root = project_root(args.root)
    if RECEIPT_RE.fullmatch(args.receipt_id) is None:
        raise BridgeError("invalid receipt_id")
    carrier = find_reading_ar(root, args.activity)
    path = ledger_path(carrier, args.activity)
    with file_lock(root, "repository-global-receipts"):
        ledger = read_ledger(root, carrier, args.activity)
        existing_global: list[dict[str, Any]] = []
        for _ledger_path, candidate in all_ledgers(root):
            existing_global.extend(row for row in candidate["receipt_outbox"] if row["receipt_id"] == args.receipt_id)
        if len(existing_global) > 1:
            raise BridgeError("repository-global duplicate receipt_id")
        contribution = next((row["payload"] for row in ledger["contributions"] if row["contribution_id"] == args.contribution_id), None)
        if contribution is None:
            raise BridgeError("contribution not imported for this ActivityRecord")
        receipt_note_uri = contribution["evidence_locator"]["receipt_note_uri"]
        if not receipt_note_uri or not receipt_note_uri.startswith("reading://note/"):
            raise BridgeError("contribution lacks owner-verified receipt_note_uri")
        use_path = consumer_path(root, args.consumer_uri)
        use_text = use_path.read_text(encoding="utf-8")
        if args.contribution_id not in use_text and receipt_note_uri not in use_text:
            raise BridgeError("local use position does not reference the imported contribution/note")
        business = {
            "receipt_id": args.receipt_id,
            "contribution_id": args.contribution_id,
            "target_activity_record_id": args.activity,
            "receipt_target_uri": receipt_note_uri,
            "consumer_uri": args.consumer_uri,
            "used_at": args.used_at,
            "purpose": args.purpose,
        }
        if existing_global:
            existing_payload = existing_global[0]["payload"]
            if any(existing_payload[key] != value for key, value in business.items()):
                raise BridgeError("ID_CONFLICT")
            return existing_payload
        payload: dict[str, Any] = {
            "schema": "reading.t2ag_receipt.v1",
            "event_id": args.receipt_id,
            "generated_at": args.generated_at or utc_now(),
            "producer": "t2ag",
            "semantic_sha256": "",
            **business,
        }
        payload["semantic_sha256"] = semantic_sha256(payload)
        validate_document(payload, schema_for(root, "reading.t2ag_receipt.v1"))
        validate_semantic(payload)
        ledger["receipt_outbox"].append({"receipt_id": args.receipt_id, "status": "pending", "payload": payload, "ack_result": None})
        ledger["receipt_outbox"].sort(key=lambda row: row["receipt_id"])
        validate_document(ledger, schema_for(root, "t2ag.reading_contribution_ledger.v1"))
        atomic_store(path, ledger)
        return payload


def receipt_list_pending(args: argparse.Namespace) -> list[dict[str, Any]]:
    root = project_root(args.root)
    result: list[dict[str, Any]] = []
    for _path, ledger in all_ledgers(root):
        if args.activity and ledger["activity_record_id"] != args.activity:
            continue
        result.extend(row["payload"] for row in ledger["receipt_outbox"] if row["status"] == "pending")
    return sorted(result, key=lambda row: (row["used_at"], row["receipt_id"]))


def receipt_ack(args: argparse.Namespace) -> dict[str, Any]:
    root = project_root(args.root)
    response = load_json_strict(Path(args.response_file))
    if not isinstance(response, dict) or set(response) != {"receipt_id", "semantic_sha256", "result"}:
        raise BridgeError("receipt owner response fields are invalid")
    if response["result"] not in {"applied", "already_applied"}:
        raise BridgeError("receipt owner response result is invalid")
    with file_lock(root, "repository-global-receipts"):
        matches: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
        for path, ledger in all_ledgers(root):
            for row in ledger["receipt_outbox"]:
                if row["receipt_id"] == response["receipt_id"]:
                    matches.append((path, ledger, row))
        if len(matches) != 1:
            raise BridgeError("receipt outbox must resolve exactly once")
        path, ledger, row = matches[0]
        if response["semantic_sha256"] != row["payload"]["semantic_sha256"]:
            raise BridgeError("receipt owner response SHA mismatch")
        ack = {
            **response,
            "response_sha256": hashlib.sha256(canonical_json_bytes(response)).hexdigest(),
        }
        if row["status"] == "acknowledged":
            if row["ack_result"] != ack:
                raise BridgeError("ID_CONFLICT")
            return {"receipt_id": response["receipt_id"], "result": "already_acknowledged"}
        row["status"] = "acknowledged"
        row["ack_result"] = ack
        validate_document(ledger, schema_for(root, "t2ag.reading_contribution_ledger.v1"))
        atomic_store(path, ledger)
        return {"receipt_id": response["receipt_id"], "result": "acknowledged"}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--root")
    commands = result.add_subparsers(dest="command", required=True)
    export = commands.add_parser("context-export")
    export.add_argument("--activity", required=True)
    export.add_argument("--event-id", required=True)
    export.add_argument("--generated-at")
    imported = commands.add_parser("contribution-import")
    imported.add_argument("--file", required=True)
    prepare = commands.add_parser("receipt-prepare")
    prepare.add_argument("--activity", required=True)
    prepare.add_argument("--contribution-id", required=True)
    prepare.add_argument("--receipt-id", required=True)
    prepare.add_argument("--consumer-uri", required=True)
    prepare.add_argument("--used-at", required=True)
    prepare.add_argument("--purpose", required=True)
    prepare.add_argument("--generated-at")
    pending = commands.add_parser("receipt-list-pending")
    pending.add_argument("--activity")
    ack = commands.add_parser("receipt-ack")
    ack.add_argument("--response-file", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        value: Any
        if args.command == "context-export":
            value = context_export(args)
        elif args.command == "contribution-import":
            value = contribution_import(args)
        elif args.command == "receipt-prepare":
            value = receipt_prepare(args)
        elif args.command == "receipt-list-pending":
            value = receipt_list_pending(args)
        else:
            value = receipt_ack(args)
        print(canonical_json_bytes(value).decode("utf-8"))
        return 0
    except (BridgeError, ContractError, OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
