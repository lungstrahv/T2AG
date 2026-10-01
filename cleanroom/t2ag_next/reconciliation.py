"""Explicit interpretation of preserved legacy ambiguities, without regrading history."""
from copy import deepcopy

from .model import DomainError, fields, get, put, require, require_student
from .support import _read, _new, digest

ACTIONS = {"migration.reconcile"}
FIELDS = {
    "course": {"status", "paused", "current_activity_id", "learning_mode"},
    "activity": {"status", "pending_body", "pending_requires_new_presentation"},
    "cursor": {"position", "pending_body", "next_action", "waiting_for"},
    "group": {"members", "capacity", "calendar", "thresholds", "container_mode", "keystone_ids", "keystone_total_initial", "keystone_total_frozen"},
}


def _field(data, dotted):
    require(isinstance(dotted, str) and bool(dotted), "EVIDENCE_FIELD", "Specify an exact preserved field.")
    for name in dotted.split("."):
        require(isinstance(data, dict) and name in data, "EVIDENCE_FIELD", "Preserved evidence field is missing.")
        data = data[name]
    return data


def plan(state, request):
    require(request["action"] == "migration.reconcile", "UNKNOWN_ACTION", "Unknown reconciliation action.")
    p = request["payload"]
    fields(p, "id", "target_kind", "target_id", "changes", "resolves", "evidence", "rationale", "basis")
    kind = p["target_kind"]
    require(kind in FIELDS, "RECONCILIATION_SCOPE", "Historical grades, attempts, source verification and permission objects cannot be rewritten by reconciliation.")
    target = _read(state, request, kind, p["target_id"])
    require(target.get("legacy") is not None or target.get("migration_state") is not None or target.get("migration_requires_reconciliation"), "NOT_MIGRATED", "Only a preserved migrated object can be reconciled.")
    changes = p["changes"]
    require(isinstance(changes, dict) and bool(changes) and set(changes) <= FIELDS[kind], "RECONCILIATION_FIELDS", "Changes must use the named active recovery fields.")
    require(isinstance(p["resolves"], list) and bool(p["resolves"]) and set(p["resolves"]) <= set(target.get("uncertainties", [])), "RECONCILIATION_REASONS", "Resolve exact known uncertainties; do not erase unrelated ones.")
    require(isinstance(p["evidence"], list) and bool(p["evidence"]), "RECONCILIATION_EVIDENCE", "Preserve actual evidence for this interpretation.")
    evidence = []
    for ref in p["evidence"]:
        fields(ref, "kind", "id", "field", "value_sha256", "excerpt")
        original = _read(state, request, ref["kind"], ref["id"])
        value = _field(original, ref["field"])
        require(ref["value_sha256"] == digest(value), "RECONCILIATION_EVIDENCE_CHANGED", "Evidence field no longer matches its displayed content.")
        require(isinstance(value, str) and isinstance(ref["excerpt"], str) and bool(ref["excerpt"].strip()) and ref["excerpt"] in value, "RECONCILIATION_EXCERPT", "Keep the actual preserved source excerpt, not a fabricated label.")
        evidence.append(deepcopy(ref))
    require(p["basis"] in ("source_evidence", "student_resolution"), "RECONCILIATION_BASIS", "Distinguish a literal historical mapping from a new student resolution.")
    if p["basis"] == "student_resolution":
        decision = require_student(request)
    else:
        decision = deepcopy(request["actor"])
        require(all(ref["kind"] == kind and ref["id"] == p["target_id"] for ref in evidence), "RECONCILIATION_SOURCE_SCOPE", "A literal source mapping must use this object's own preserved evidence.")
        joined = "\n".join(ref["excerpt"] for ref in evidence)
        require(all(isinstance(value, str) and value in joined for value in changes.values()), "RECONCILIATION_INFERENCE", "A source-only mapping must preserve literal values; a new interpretation requires the student's specific resolution.")
    updated = deepcopy(target)
    updated.update(deepcopy(changes))
    if kind == "course":
        course_type, mode = updated.get("course_type"), updated.get("learning_mode")
        require((course_type == "mastery" and mode in ("textbook", "goal", "project")) or
                (course_type in ("project", "praxis") and mode is None), "LEARNING_MODE", "Only Mastery has a learning mode; historical interpretation preserves domain type constraints.")
        require(updated["status"] in ("planned", "ongoing", "paused", "completed", "closed_incomplete"), "COURSE_STATE", "Unknown course lifecycle.")
        require(updated["status"] not in ("completed", "closed_incomplete") or target.get("status") == updated["status"], "RECONCILIATION_NOT_CLOSURE", "Use a course closing review to create a new terminal outcome.")
        if "paused" in changes: require(type(changes["paused"]) is bool, "COURSE_STATE", "Paused is an explicit boolean.")
        if updated.get("current_activity_id"):
            activity = _read(state, request, "activity", updated["current_activity_id"])
            require(activity["course_id"] == p["target_id"], "RECONCILIATION_ROUTE", "Foreground activity must belong to this course.")
    elif kind == "activity":
        require(updated["status"] in ("planned", "ongoing", "pending_close", "completed", "closed_incomplete"), "ACTIVITY_STATE", "Unknown activity lifecycle.")
        if "status" in changes:
            require(changes["status"] not in ("completed", "closed_incomplete") or target.get("status") == changes["status"], "RECONCILIATION_NOT_CLOSURE", "Use an actual new closing review to create a terminal learning outcome.")
        if updated.get("status") == "pending_close":
            require(bool(updated.get("pending_body")), "PENDING_BODY_MISSING", "Pending close requires the complete original body.")
            updated["pending_requires_new_presentation"] = True
    elif kind == "cursor":
        require(updated.get("waiting_for") in ("authorization", "comprehension", "feeling", "questions", "confirm_close", "clarify_conflict", "source_scan", "activity_start"), "RECONCILIATION_GATE", "A recovery interpretation cannot grant permission or declare teaching ready.")
        require(updated.get("position") is not None and isinstance(updated["position"], str), "RECONCILIATION_POSITION", "Keep the exact recoverable stopping point.")
        updated.update(historical_permissions_active=False, current_session_scan=None, requires_current_session_revalidation=True)
    elif kind == "group":
        require(isinstance(updated.get("members"), list) and len(set(updated["members"])) == len(updated["members"]), "GROUP_MEMBERS", "Group members must be unique.")
        for course_id in updated["members"]: _read(state, request, "course", course_id)
        require(type(updated.get("capacity")) is int and updated["capacity"] >= len(updated["members"]), "GROUP_CAPACITY", "Mapped capacity must cover the declared composition.")
        require(updated.get("container_mode") in ("schedule", "progress"), "CONTAINER_MODE", "Map the actual time/scope container.")
        require(updated.get("status") != "active" or updated.get("members") == target.get("members"), "GROUP_COMPOSITION", "Active composition changes use a separate explicit group transition.")
        require(set(target.get("completed_keystone_ids", [])) <= set(updated.get("keystone_ids", [])), "COMPLETED_SCOPE", "Reconciliation cannot remove previously completed milestones.")
    updated["uncertainties"] = [reason for reason in target.get("uncertainties", []) if reason not in p["resolves"]]
    updated["migration_requires_reconciliation"] = bool(updated["uncertainties"])
    updated["migration_state"] = "needs_resolution" if updated["uncertainties"] else "reconciled"
    updated.setdefault("reconciliation_ids", []).append(p["id"])
    receipt = {"target_kind": kind, "target_id": p["target_id"], "before_sha256": digest(target), "changes": deepcopy(changes),
               "resolved": deepcopy(p["resolves"]), "remaining": updated["uncertainties"], "evidence": evidence,
               "rationale": p["rationale"], "basis": p["basis"], "decision": decision, "future_permission": "none"}
    return [put(kind, p["target_id"], updated), _new(state, "reconciliation", p["id"], receipt)]
