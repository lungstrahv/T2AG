"""Reading bridge v1 wire compatibility, implemented from its public contract.

Incoming contributions are candidates. No other repository is opened or mutated.
"""
from copy import deepcopy
from datetime import datetime
import re

from .model import DomainError, fields, get, put, require, require_student
from .support import _new, _read, digest

ACTIONS = {"reading.context.confirm", "reading.contribution.import", "reading.receipt.prepare", "reading.receipt.ack"}


def _text(value, maximum=500):
    require(isinstance(value, str) and 0 < len(value) <= maximum and "\0" not in value, "READING_TEXT", "Invalid bounded reading text.")


def _match(value, pattern):
    require(isinstance(value, str) and re.fullmatch(pattern, value) is not None, "READING_IDENTITY", "Reading wire identity is invalid.")


def _date(value):
    _text(value, 64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None, "READING_DATE", "A timezone is required.")
    except ValueError as exc:
        raise DomainError("READING_DATE", "Invalid ISO timestamp.") from exc


def _path(value):
    _text(value, 512)
    require(not value.startswith("/") and "\\" not in value and ":" not in value and all(x not in ("", ".", "..") for x in value.split("/")), "READING_PATH", "Only safe relative source locators are accepted.")


def semantic_hash(value):
    omitted = {"semantic_sha256", "generated_at", "event_id", "export_id"}
    if value.get("schema") != "reading.t2ag_receipt.v1":
        omitted.add("contribution_id")
    return digest({k: v for k, v in value.items() if k not in omitted})


def _context_source(value):
    names = {"schema", "activity_record_id", "target_reading_uri", "course_id", "confirmed_by", "confirmed_at", "reading_intents", "questions_or_observation_cues"}
    require(isinstance(value, dict) and set(value) == names and value["schema"] == "t2ag.reading_context_source.v1", "READING_SCHEMA", "Unexpected reading context fields.")
    _match(value["activity_record_id"], r"AR-\d{4}")
    require(value["confirmed_by"] == "student", "READING_CONFIRMATION", "Reading context must be student-confirmed.")
    _date(value["confirmed_at"])
    if value["target_reading_uri"] is not None: _match(value["target_reading_uri"], r"reading://book/[A-Z][A-Z0-9_-]{0,31}")
    if value["course_id"] is not None: _match(value["course_id"], r"[A-Z][A-Z0-9_-]{1,63}")
    for name in ("reading_intents", "questions_or_observation_cues"):
        require(isinstance(value[name], list) and len(value[name]) <= 3, "READING_ITEMS", "Context holds at most three items per category.")
        for row in value[name]:
            require(isinstance(row, dict) and set(row) == {"source_id", "source_path", "text"}, "READING_ITEM", "Invalid reading context item.")
            _match(row["source_id"], r"[A-Za-z0-9._:-]{1,128}"); _path(row["source_path"]); _text(row["text"])


def context_export(state, activity_id, event_id, generated_at):
    source = get(state, "reading_context", activity_id)["source"]
    _context_source(source); _match(event_id, r"[A-Za-z0-9._:-]{8,128}"); _date(generated_at)
    value = {"schema": "t2ag.reading_context.v1", "event_id": event_id, "generated_at": generated_at, "producer": "t2ag",
             **{k: deepcopy(source[k]) for k in ("activity_record_id", "target_reading_uri", "course_id", "reading_intents", "questions_or_observation_cues")}}
    sha = semantic_hash(value)
    value.update(semantic_sha256=sha, export_id="CTX-" + sha)
    return value


def contribution(value):
    names = {"schema", "event_id", "generated_at", "producer", "semantic_sha256", "contribution_id", "target_activity_record_id", "book_id", "source_reading_uri", "source_revision", "knowledge_node_id", "question", "maturity", "supports", "limits", "evidence_locator"}
    require(isinstance(value, dict) and set(value) == names and value["schema"] == "reading.t2ag_contribution.v1" and value["producer"] == "reading_system", "READING_SCHEMA", "Unexpected contribution schema or producer.")
    _match(value["event_id"], r"[A-Za-z0-9._:-]{8,128}"); _date(value["generated_at"])
    _match(value["target_activity_record_id"], r"AR-\d{4}")
    _match(value["book_id"], r"[A-Z][A-Z0-9_-]{0,31}")
    _match(value["source_reading_uri"], r"reading://(?:note|node)/[A-Za-z0-9._~:/-]{1,240}")
    _match(value["source_revision"], r"[0-9a-f]{64}")
    if value["knowledge_node_id"] is not None: _match(value["knowledge_node_id"], r"K-[A-Z][A-Z0-9_-]{0,31}-\d{4}")
    _text(value["question"]); _text(value["maturity"], 64)
    for name in ("supports", "limits"):
        require(isinstance(value[name], list) and len(value[name]) <= 5, "READING_ITEMS", "At most five bounded statements are allowed.")
        for item in value[name]: _text(item)
    locator = value["evidence_locator"]
    require(isinstance(locator, dict) and set(locator) == {"source_uri", "source_path", "source_id", "source_sha256", "receipt_note_uri"}, "READING_LOCATOR", "Invalid evidence locator.")
    _path(locator["source_path"]); _match(locator["source_id"], r"[A-Za-z0-9._:-]{1,128}"); _match(locator["source_sha256"], r"[0-9a-f]{64}")
    _match(locator["source_uri"], r"reading://(?:note|node)/[A-Za-z0-9._~:/-]{1,240}")
    if locator["receipt_note_uri"] is not None: _match(locator["receipt_note_uri"], r"reading://note/[A-Za-z0-9._~:/-]{1,240}")
    sha = semantic_hash(value)
    require(value["semantic_sha256"] == sha and value["contribution_id"] == "CON-" + sha, "READING_HASH", "Contribution identity must bind its semantic content.")
    return deepcopy(value)


def plan(state, request):
    action, p = request["action"], request["payload"]
    if action == "reading.context.confirm":
        fields(p, "source")
        require_student(request); source = p["source"]; _context_source(source)
        activity = _read(state, request, "reading", source["activity_record_id"])
        require(activity["status"] in ("recording", "paused", "upgraded"), "READING_STATE", "Archived reading cannot receive a new context.")
        if source["course_id"] is not None: _read(state, request, "course", source["course_id"])
        return [put("reading_context", source["activity_record_id"], {"source": deepcopy(source), "decision": deepcopy(request["actor"])})]
    if action == "reading.contribution.import":
        fields(p, "document"); doc = contribution(p["document"])
        _read(state, request, "reading", doc["target_activity_record_id"])
        identity = doc["contribution_id"]
        existing = get(state, "reading_contribution", identity, False)
        event = get(state, "reading_event", doc["event_id"], False)
        if event:
            require(event["semantic_sha256"] == doc["semantic_sha256"], "READING_EVENT_CONFLICT", "An event ID cannot be reused with different content.")
        if existing:
            require(existing["payload"]["semantic_sha256"] == doc["semantic_sha256"], "READING_CONTENT_CONFLICT", "Contribution content differs.")
            return [] if event else [_new(state, "reading_event", doc["event_id"], {"semantic_sha256": doc["semantic_sha256"], "contribution_id": identity})]
        return [_new(state, "reading_contribution", identity, {"payload": doc, "status": "candidate", "receipt_ids": []}),
                _new(state, "reading_event", doc["event_id"], {"semantic_sha256": doc["semantic_sha256"], "contribution_id": identity})]
    fields(p, "contribution_id", "receipt_id")
    c = _read(state, request, "reading_contribution", p["contribution_id"])
    if action == "reading.receipt.prepare":
        fields(p, "consumer_kind", "consumer_id", "consumer_sha256", "used_at", "purpose", "generated_at")
        require(p["consumer_kind"] in ("thought", "reflection", "pattern", "keystone"), "READING_CONSUMER_KIND", "A receipt requires a named learning consumer, not profile metadata.")
        _match(p["receipt_id"], r"RCP-[A-Z0-9]{16,64}"); _date(p["used_at"]); _date(p["generated_at"]); _text(p["purpose"])
        target = _read(state, request, p["consumer_kind"], p["consumer_id"])
        require(p["consumer_sha256"] == digest(target), "READING_CONSUMER_CHANGED", "Actual local consumption changed.")
        bound_ref = {"kind": "reading_contribution", "id": p["contribution_id"], "sha256": c["payload"]["semantic_sha256"]}
        require(bound_ref in target.get("contribution_refs", []), "READING_NOT_CONSUMED", "The actual consumer must retain a structured reference to this exact candidate.")
        require(isinstance(target.get("body"), str) and bool(target["body"].strip()) and bool(target.get("evidence")), "READING_NOT_CONSUMED", "The consumer needs its actual learning content and evidence.")
        ar_id = c["payload"]["target_activity_record_id"]
        context = get(state, "reading_context", ar_id, False) or {}
        course_id = context.get("source", {}).get("course_id")
        require(target.get("reading_id") == ar_id or (course_id is not None and target.get("course_id") == course_id), "READING_CONSUMER_SCOPE", "Consumption must belong to this reading activity or its explicitly bound course.")
        uri = c["payload"]["evidence_locator"]["receipt_note_uri"]
        require(uri is not None, "READING_RECEIPT_TARGET", "The source did not provide an addressable receipt note.")
        doc = {"schema": "reading.t2ag_receipt.v1", "event_id": p["receipt_id"], "generated_at": p["generated_at"], "producer": "t2ag",
               "receipt_id": p["receipt_id"], "contribution_id": p["contribution_id"], "target_activity_record_id": c["payload"]["target_activity_record_id"],
               "receipt_target_uri": uri, "consumer_uri": f"t2ag://object/{p['consumer_kind']}/{p['consumer_id']}", "used_at": p["used_at"], "purpose": p["purpose"]}
        _match(doc["consumer_uri"], r"t2ag://[A-Za-z0-9._~:/-]{1,240}")
        doc["semantic_sha256"] = semantic_hash(doc)
        old = get(state, "reading_receipt", p["receipt_id"], False)
        if old:
            require(old["payload"] == doc, "READING_RECEIPT_CONFLICT", "Receipt ID already binds different consumption.")
            return []
        c["receipt_ids"].append(p["receipt_id"])
        return [put("reading_contribution", p["contribution_id"], c), _new(state, "reading_receipt", p["receipt_id"], {"payload": doc, "status": "prepared", "consumer_sha256": p["consumer_sha256"]})]
    if action == "reading.receipt.ack":
        fields(p, "response")
        receipt = _read(state, request, "reading_receipt", p["receipt_id"])
        response = p["response"]
        require(isinstance(response, dict) and set(response) == {"receipt_id", "semantic_sha256", "result"}, "READING_ACK", "Unexpected acknowledgment shape.")
        require(receipt["payload"]["contribution_id"] == p["contribution_id"], "READING_ACK", "Receipt belongs to another contribution.")
        require(response["receipt_id"] == p["receipt_id"] and response["semantic_sha256"] == receipt["payload"]["semantic_sha256"] and response["result"] in ("applied", "already_applied"), "READING_ACK", "Acknowledgment does not bind this receipt.")
        if receipt["status"] == "acknowledged":
            # Both contract values assert the same successful remote application.
            # The receipt identity/hash were checked above; keep the first record.
            return []
        receipt.update(status="acknowledged", response=deepcopy(response))
        return [put("reading_receipt", p["receipt_id"], receipt)]
    raise DomainError("UNKNOWN_ACTION", action)
