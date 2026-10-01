"""Explicit JSON exchange. Transport and external execution remain host duties."""
from copy import deepcopy
import hashlib

from .model import DomainError, fields, get, put, require, require_student, version
from .support import _read, _new, digest

ENVELOPE_SCHEMA = "t2ag.exchange.v1"
ACTIONS = {"bridge.configure", "bridge.pause", "bridge.import", "bridge.receipt.prepare", "bridge.receipt.ack", "bridge.reject"}


def envelope(kind, identity, source_identity, target_identity, scope, base_revision, body):
    value = {"schema": ENVELOPE_SCHEMA, "kind": kind, "id": identity, "source_identity": source_identity,
             "target_identity": target_identity, "scope": scope, "base_revision": base_revision, "body": deepcopy(body)}
    value["content_sha256"] = digest(value)
    return value


def validate_envelope(value):
    fields(value, "schema", "kind", "id", "source_identity", "target_identity", "scope", "base_revision", "body", "content_sha256")
    require(value["schema"] == ENVELOPE_SCHEMA, "EXCHANGE_SCHEMA", "Unsupported exchange schema version.")
    require(value["kind"] in ("reading_contribution", "cloud_pending"), "EXCHANGE_KIND", "Unsupported exchange kind.")
    require(isinstance(value["base_revision"], int) and value["base_revision"] >= 0, "EXCHANGE_REVISION", "Invalid source baseline.")
    unsigned = {k: v for k, v in value.items() if k != "content_sha256"}
    require(digest(unsigned) == value["content_sha256"], "EXCHANGE_HASH", "Exchange body or identity changed.")
    require(isinstance(value["body"], dict), "EXCHANGE_BODY", "Exchange body must be an object.")
    return deepcopy(value)


def context_export(state, identity, scope):
    config = get(state, "bridge", "current")
    require(not config.get("paused"), "BRIDGE_PAUSED", "Export is paused.")
    course = get(state, "course", scope)
    activity_id = course.get("current_activity_id")
    data = {"course": course, "activity": get(state, "activity", activity_id, False) if activity_id else None,
            "cursor": get(state, "cursor", activity_id, False) if activity_id else None}
    return {"schema": "t2ag.context_exchange.v1", "id": identity, "source_identity": config["instance_id"],
            "instance_kind": config["instance_kind"], "scope": scope, "base_revision": state["revision"],
            "body": data, "body_sha256": digest(data), "authority": "read_only_context", "permission": "none"}


def plan(state, request):
    action, p = request["action"], request["payload"]
    if action == "bridge.configure":
        require_student(request)
        fields(p, "instance_id", "instance_kind", "trusted_sources")
        require(p["instance_kind"] in ("personal_instance", "generic_skeleton"), "INSTANCE_KIND", "Explicitly identify this instance.")
        require(isinstance(p["trusted_sources"], list) and p["trusted_sources"], "EXCHANGE_SOURCES", "Name each allowed sending identity.")
        require(type(p.get("independent_exchange_enabled", False)) is bool, "CLOUD_MODE", "Independent exchange is an explicit boolean choice.")
        return [_new(state, "bridge", "current", {**deepcopy(p), "independent_exchange_enabled": p.get("independent_exchange_enabled", False), "paused": True})]
    config = _read(state, request, "bridge", "current")
    if action == "bridge.pause":
        require_student(request)
        require(isinstance(p.get("paused"), bool), "PAUSE_VALUE", "Use an explicit pause decision.")
        config["paused"] = p["paused"]
        return [put("bridge", "current", config)]
    require(not config["paused"], "BRIDGE_PAUSED", "Exchange is paused; no import, projection or receipt is performed.")
    if action == "bridge.import":
        fields(p, "envelope")
        e = validate_envelope(p["envelope"])
        require(e["source_identity"] in config["trusted_sources"] and e["target_identity"] == config["instance_id"], "EXCHANGE_IDENTITY", "Source or target identity is not authorized.")
        require(config["instance_kind"] == "personal_instance" or e["kind"] != "cloud_pending", "SKELETON_PRIVATE_IMPORT", "Personal cloud events cannot enter a generic template.")
        course = _read(state, request, "course", e["scope"])
        old = get(state, "contribution", e["id"], False)
        require(old is None, "CONTRIBUTION_EXISTS", "Lookup the original receipt; an existing contribution identity cannot be reused.")
        conflict = e["base_revision"] != state["revision"]
        activity_id = course.get("current_activity_id")
        if e["kind"] == "cloud_pending":
            require(config.get("independent_exchange_enabled") is True, "CLOUD_COMPATIBILITY_DISABLED", "Mobile remote access uses the same local instance; independent cloud exchange must be explicitly enabled.")
            fields(e["body"], "session_id", "proposed_cursor")
            current_cursor = _read(state, request, "cursor", activity_id) if activity_id else None
            conflict = conflict or e["body"].get("local_cursor_sha256") != digest(current_cursor)
        return [_new(state, "contribution", e["id"], {"envelope": e, "status": "conflict" if conflict else "candidate", "imported_at_revision": state["revision"], "scope": e["scope"], "consumption": None})]
    fields(p, "id")
    contribution = _read(state, request, "contribution", p["id"])
    if action == "bridge.reject":
        require_student(request)
        fields(p, "reason")
        require(contribution["status"] in ("candidate", "conflict"), "CONTRIBUTION_STATE", "Only a pending candidate can be rejected.")
        contribution.update(status="rejected", reason=p["reason"], decision=deepcopy(request["actor"]))
        return [put("contribution", p["id"], contribution)]
    if action == "bridge.receipt.prepare":
        require_student(request)
        fields(p, "target_kind", "target_id", "target_sha256", "content_sha256", "consumption_ref")
        require(contribution["status"] in ("candidate", "conflict"), "CONTRIBUTION_STATE", "Contribution has already been settled.")
        require(p["content_sha256"] == contribution["envelope"]["content_sha256"], "EXCHANGE_HASH", "Confirm exactly the imported candidate.")
        target = _read(state, request, p["target_kind"], p["target_id"])
        require(digest(target) == p["target_sha256"], "CONSUMPTION_CHANGED", "The actual locally consumed result changed.")
        bound_ref = {"kind": "contribution", "id": p["id"], "sha256": p["content_sha256"]}
        require(bound_ref in target.get("contribution_refs", []) and version(state, p["target_kind"], p["target_id"]) > contribution["imported_at_revision"] + 1,
                "CONTRIBUTION_NOT_CONSUMED", "Receipt requires a subsequent local result explicitly bound to this candidate's identity and content.")
        if contribution["status"] == "conflict":
            fields(p, "reconciliation")
        target_course = target.get("course_id")
        if not target_course and target.get("activity_id"):
            target_course = _read(state, request, "activity", target["activity_id"])["course_id"]
        require(target_course == contribution["scope"], "CONSUMPTION_SCOPE", "Receipt must reference actual consumption in the same course.")
        receipt_id = contribution["envelope"]["id"]
        receipt = {"schema": "t2ag.receipt.v1", "contribution_id": p["id"], "content_sha256": p["content_sha256"], "source_identity": config["instance_id"],
                   "target_identity": contribution["envelope"]["source_identity"], "scope": contribution["scope"], "status": "prepared",
                   "consumption": {k: deepcopy(p[k]) for k in ("target_kind", "target_id", "target_sha256", "consumption_ref")}, "decision": deepcopy(request["actor"])}
        contribution.update(status="consumed", consumption=receipt["consumption"])
        return [put("contribution", p["id"], contribution), _new(state, "receipt", receipt_id, receipt)]
    if action == "bridge.receipt.ack":
        receipt = _read(state, request, "receipt", p["id"])
        fields(p, "receipt_sha256", "transport_evidence")
        require(p["receipt_sha256"] == digest(receipt), "RECEIPT_CHANGED", "Transport acknowledgment binds the complete receipt.")
        require(receipt["status"] == "prepared", "RECEIPT_STATE", "Receipt has already been acknowledged.")
        receipt.update(status="acknowledged", transport_evidence=p["transport_evidence"])
        return [put("receipt", p["id"], receipt)]
    raise DomainError("UNKNOWN_ACTION", action)
