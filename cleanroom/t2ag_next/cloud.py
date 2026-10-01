"""T2AG-CLOUD-1 events and component handoffs, preserved as untrusted inputs.

Cloud text is never executed. Local progress application and verified sync
receipts are separate: an interrupted sync can resume without double-counting.
"""
from copy import deepcopy
from datetime import datetime
import re

from .model import DomainError, fields, get, put, require, require_student
from .support import _read, _new, digest, learning_day

PROTOCOL = "T2AG-CLOUD-1"
CLOSE = "T2AG_SESSION_CLOSE"
PROGRESS = "T2AG_PROGRESS_RECEIPT"
DIRECTIVE = "T2AG_CLOUD_CHANGE_DIRECTIVE"
HANDOFF = "T2AG_CLOUD_HANDOFF"
REQUIRED = {
    CLOSE: "protocol_version session_id closed_at t2ag_version base_state_id course current_activity current_activity_id resume_path lesson_context duration_minutes source_evidence covered completed confirmation_state pending_checkpoint mastery_evidence open_questions mistakes_to_retest student_state_note exact_stop next_first_action files_to_update privacy_scope sync_status".split(),
    PROGRESS: "protocol_version receipt_id produced_at base_state_id course current_activity current_activity_id resume_path lesson_context receipt_kind completion_node_id checkpoint_id exact_stop confirmation_state sync_status".split(),
    DIRECTIVE: "protocol_version directive_id created_at local_t2ag_version target_cloud affected_components local_changed_files expected_cloud_changes acceptance_criteria attachments_to_send migration_notes privacy_impact reply_required sent_at send_evidence status".split(),
    HANDOFF: "protocol_version handoff_id directive_id produced_at cloud_project cloud_base_state_id changes_applied generated_files deviations verification open_questions proposed_local_changes privacy_impact status".split(),
}
ACTIONS = {"cloud.compatibility.configure", "cloud.baseline.create", "cloud.event.import", "cloud.event.apply", "cloud.directive.create", "cloud.directive.transition", "cloud.handoff.import", "cloud.handoff.decide"}


def _when(value):
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        raise DomainError("CLOUD_TIME", "Use an actual ISO timestamp with timezone.")
    require(timestamp.tzinfo is not None, "CLOUD_TIME", "Timestamp must include timezone.")
    return value


def parse_block(raw):
    require(isinstance(raw, str), "CLOUD_BLOCK", "Keep the original complete text block.")
    lines = raw.splitlines()
    starts = [(i, line.strip()) for i, line in enumerate(lines) if line.strip() in REQUIRED]
    require(len(starts) == 1, "CLOUD_BLOCK", "Import exactly one explicitly delimited protocol block.")
    start, kind = starts[0]
    ends = [i for i, line in enumerate(lines) if line.strip() == "END_" + kind]
    require(len(ends) == 1 and ends[0] > start, "CLOUD_BLOCK", "Block needs one matching end marker.")
    data, current = {}, None
    for line in lines[start+1:ends[0]]:
        match = re.fullmatch(r"- ([a-z][a-z0-9_]*):\s*(.*)", line)
        if match:
            current, value = match.groups()
            require(current not in data, "CLOUD_DUPLICATE_FIELD", "Duplicate fields are ambiguous.")
            data[current] = value
        elif line.strip():
            require(current is not None and line.startswith("  "), "CLOUD_FIELD", "Multiline field continuation must be indented.")
            data[current] += "\n" + line[2:]
    require(set(REQUIRED[kind]) <= set(data) and all(data[k].strip() for k in REQUIRED[kind]), "CLOUD_FIELDS", "Required values may be UNKNOWN or NONE but cannot be omitted.")
    require(data["protocol_version"] == PROTOCOL, "CLOUD_PROTOCOL", "Unsupported protocol.")
    if kind in (CLOSE, PROGRESS):
        require(data["sync_status"] == "pending", "CLOUD_AUTHORITY", "Cloud cannot claim a local sync.")
        require(data["current_activity"] in ("lesson", "exercise"), "CLOUD_ACTIVITY", "Keep the explicit activity type and identity; old lesson-only events need manual migration.")
        require(data["confirmation_state"] in ("pending", "confirmed", "not_applicable"), "CLOUD_CONFIRMATION", "Unknown confirmation state.")
        _when(data["closed_at" if kind == CLOSE else "produced_at"])
        if kind == CLOSE:
            require(data["privacy_scope"] == "uploaded_project_only", "CLOUD_PRIVACY", "Event is confined to the existing personal project.")
            require(data["duration_minutes"] == "UNKNOWN" or re.fullmatch(r"[0-9]+", data["duration_minutes"]), "CLOUD_DURATION", "Duration is nonnegative whole minutes or UNKNOWN.")
        else:
            require(data["receipt_kind"] in ("completion_node", "manual_save"), "CLOUD_RECEIPT", "Unknown progress receipt kind.")
    elif kind == DIRECTIVE:
        _when(data["created_at"])
        require(data["status"] == "ready_to_send" and data["sent_at"] == "NONE" and data["send_evidence"] == "NONE", "CLOUD_SEND_EVIDENCE", "Freeze a ready directive; transport transitions require later evidence.")
        require(data["reply_required"] == HANDOFF, "CLOUD_REPLY", "A formal directive requests the separate component handoff.")
    else:
        _when(data["produced_at"])
        require(data["status"] == "proposed_for_local_review", "CLOUD_AUTHORITY", "The cloud proposal status remains immutable.")
    return {"kind": kind, "fields": data, "raw": raw, "sha256": digest(raw)}


def route_basis(state, course_id):
    course = get(state, "course", course_id)
    aid = course.get("current_activity_id")
    require(bool(aid), "CLOUD_ROUTE", "A baseline requires the actual foreground activity.")
    activity = get(state, "activity", aid)
    require(activity["course_id"] == course_id, "CLOUD_ROUTE", "Foreground activity belongs to another course.")
    return {"course": deepcopy(course), "activity": deepcopy(activity), "cursor": get(state, "cursor", aid, False)}


def _config(state, request, personal=True):
    config = _read(state, request, "bridge", "current")
    require(config.get("independent_exchange_enabled") is True, "CLOUD_COMPATIBILITY_DISABLED", "Shared-instance remote access needs no cloud sync. Enable independent exchange explicitly only for a separate classroom.")
    require(not config["paused"], "BRIDGE_PAUSED", "Paused means no projection, event, or component sync.")
    require(not personal or config["instance_kind"] == "personal_instance", "SKELETON_PRIVATE_IMPORT", "Personal events cannot enter a generic skeleton.")
    return config


def plan(state, request):
    action, p = request["action"], request["payload"]
    if action == "cloud.compatibility.configure":
        config = _read(state, request, "bridge", "current")
        decision = require_student(request)
        require(type(p.get("enabled")) is bool, "CLOUD_MODE", "Choose independent exchange explicitly; device type never enables it.")
        config.update(independent_exchange_enabled=p["enabled"], independent_exchange_decision=decision)
        return [put("bridge", "current", config)]
    config = _config(state, request, action.startswith("cloud.event") or action == "cloud.baseline.create")
    if action == "cloud.baseline.create":
        fields(p, "id", "course_id", "created_at")
        _when(p["created_at"])
        basis = route_basis(state, p["course_id"])
        data = {"protocol_version": PROTOCOL, "base_state_id": p["id"], "cloud_project_mode": config["instance_kind"], "instance_id": config["instance_id"],
            "course": p["course_id"], "current_activity_id": basis["course"]["current_activity_id"], "current_activity": basis["activity"]["activity_type"],
            "exact_stop": (basis["cursor"] or {}).get("position", "UNKNOWN"), "next_first_action": (basis["cursor"] or {}).get("next_action", "UNKNOWN"),
            "created_at": p["created_at"], "basis_sha256": digest(basis), "source_revision": state["revision"], "permission": "none", "authority": "read_only_context"}
        return [_new(state, "cloud_baseline", p["id"], data)]
    if action in ("cloud.event.import", "cloud.handoff.import", "cloud.directive.create"):
        fields(p, "raw", "source_identity")
        require(p["source_identity"] in config["trusted_sources"] or (action == "cloud.directive.create" and p["source_identity"] == config["instance_id"]), "CLOUD_IDENTITY", "Source identity must be explicitly configured.")
        block = parse_block(p["raw"])
        data, kind = block["fields"], block["kind"]
        expected = {"cloud.event.import": {CLOSE, PROGRESS}, "cloud.handoff.import": {HANDOFF}, "cloud.directive.create": {DIRECTIVE}}[action]
        require(kind in expected, "CLOUD_CHANNEL", "Teaching events and component proposals use separate channels.")
        identity_field = {CLOSE: "session_id", PROGRESS: "receipt_id", HANDOFF: "handoff_id", DIRECTIVE: "directive_id"}[kind]
        identity = data[identity_field]
        require(identity not in ("UNKNOWN", "NONE") and bool(re.fullmatch(r"[A-Za-z0-9_.:+-]+", identity)), "CLOUD_ID", "An event needs its stable identity.")
        entity = {CLOSE: "cloud_event", PROGRESS: "cloud_event", HANDOFF: "cloud_handoff", DIRECTIVE: "cloud_directive"}[kind]
        previous = get(state, entity, identity, False)
        if previous:
            require(previous["block"]["sha256"] == block["sha256"] and previous["source_identity"] == p["source_identity"], "CLOUD_ID_REUSED", "An existing identity cannot carry altered input.")
            return []
        result = {"block": block, "source_identity": p["source_identity"], "status": "candidate", "imported_revision": state["revision"]}
        if entity == "cloud_event":
            basis = route_basis(state, data["course"])
            aid = basis["course"]["current_activity_id"]
            # Legacy leaf IDs are accepted only as an unambiguous exact suffix.
            require(data["current_activity_id"] in (aid, aid.split("/")[-1]) and data["current_activity"] == basis["activity"]["activity_type"], "CLOUD_ROUTE", "Event's explicit activity triple differs from the local route.")
            baseline = get(state, "cloud_baseline", data["base_state_id"], False)
            conflict = not baseline or baseline["course"] != data["course"] or baseline["basis_sha256"] != digest(basis)
            result.update(status="conflict" if conflict else "candidate", course_id=data["course"], activity_id=aid, import_basis_sha256=digest(basis))
        elif entity == "cloud_directive":
            require_student(request)
            result["status"] = "ready_to_send"
        return [_new(state, entity, identity, result)]
    if action == "cloud.event.apply":
        fields(p, "id", "event_sha256", "local_basis_sha256", "mode")
        decision = require_student(request)
        require(decision["text"].strip().rstrip("。.!！").casefold() in {"确认云端进度回写", "confirm cloud progress import"}, "CLOUD_DECISION", "Confirm the presented cloud event and local reconciliation explicitly.")
        event = _read(state, request, "cloud_event", p["id"])
        require(event["block"]["sha256"] == p["event_sha256"], "CLOUD_EVENT_CHANGED", "Apply exactly the preserved event.")
        if event["status"] in ("applied", "synced"):
            require(event["application"]["mode"] == p["mode"], "CLOUD_APPLY_CHANGED", "Existing application cannot be silently changed.")
            return []
        require(p["mode"] in ("progress", "evidence_only"), "CLOUD_APPLY_MODE", "Choose progress reconciliation or evidence-only retention.")
        data, kind = event["block"]["fields"], event["block"]["kind"]
        basis = route_basis(state, event["course_id"])
        require(digest(basis) == p["local_basis_sha256"], "CLOUD_LOCAL_CHANGED", "Local progress changed after the reconciliation was presented.")
        if event["status"] == "conflict" or digest(basis) != event["import_basis_sha256"]:
            fields(p, "reconciliation")
            require(isinstance(p["reconciliation"], str) and bool(p["reconciliation"].strip()), "CLOUD_CONFLICT", "Preserve the student's explicit resolution; latest is not automatically authoritative.")
        effects = []
        when = data["closed_at" if kind == CLOSE else "produced_at"]
        if p["mode"] == "progress":
            require(basis["course"].get("status") == "ongoing" and not basis["course"].get("paused") and basis["activity"]["status"] == "ongoing", "CLOUD_LOCAL_GATE", "A cloud event cannot reopen, resume or close an activity.")
            require(not any(e["kind"] == "session" and e["data"].get("activity_id") == event["activity_id"] and e["data"].get("status") == "active" for e in state["objects"].values()), "CLOUD_LOCAL_SESSION", "Finish the actual local session before replacing its foreground cursor.")
            cursor = deepcopy(basis["cursor"] or {})
            cursor.update(position=data["exact_stop"], next_action=data.get("next_first_action", "revalidate_sources_and_resume"),
                waiting_for="source_scan" if basis["course"].get("learning_mode") == "textbook" else "authorization", cloud_event_id=p["id"],
                current_session_scan=None, requires_current_session_revalidation=True, historical_permissions_active=False)
            effects.append(put("cursor", event["activity_id"], cursor))
        if kind == CLOSE:
            minutes = data["duration_minutes"]
            span = {"activity_id": event["activity_id"], "quality": "unknown" if minutes == "UNKNOWN" else "estimated", "source": "cloud_reported_duration", "cloud_event_id": p["id"]}
            if minutes != "UNKNOWN":
                span.update(seconds=int(minutes)*60, ended_at=when, learning_day=learning_day(when), date_basis="reported_session_close")
            effects.append(_new(state, "timespan", "cloud/"+p["id"], span))
            for label in ("covered", "completed", "mastery_evidence", "open_questions", "mistakes_to_retest", "student_state_note"):
                if data[label] not in ("NONE", "UNKNOWN"):
                    effects.append(_new(state, "cloud_candidate", p["id"]+"/"+label, {"course_id": event["course_id"], "activity_id": event["activity_id"], "event_id": p["id"], "kind": label, "body": data[label], "status": "unreviewed", "authority": "reported_evidence_not_local_mastery_or_confirmation"}))
        event.update(status="applied", application={"mode": p["mode"], "decision": decision, "reconciliation": p.get("reconciliation"), "local_basis_sha256": p["local_basis_sha256"], "completion_effect": "none", "request_id": request["request_id"]})
        effects.append(put("cloud_event", p["id"], event))
        return effects
    if action == "cloud.directive.transition":
        fields(p, "id", "directive_sha256", "status", "evidence")
        directive = _read(state, request, "cloud_directive", p["id"])
        require(directive["block"]["sha256"] == p["directive_sha256"], "CLOUD_DIRECTIVE_CHANGED", "The formal directive body is immutable.")
        transitions = {"ready_to_send": {"sent", "applied_unacknowledged"}, "sent": {"acknowledged", "applied_unacknowledged"}, "acknowledged": {"closed"}, "applied_unacknowledged": {"acknowledged"}}
        require(p["status"] in transitions.get(directive["status"], set()) and bool(p["evidence"]), "CLOUD_DIRECTIVE_STATE", "A status transition needs its actual transport or applied evidence.")
        if p["status"] == "applied_unacknowledged": require_student(request)
        if p["status"] == "closed":
            fields(p, "handoff_id")
            handoff = _read(state, request, "cloud_handoff", p["handoff_id"])
            require(handoff["block"]["fields"]["directive_id"] == p["id"] and handoff.get("local_decision", {}).get("status") in ("accepted", "partially_accepted", "rejected"), "CLOUD_HANDOFF_REQUIRED", "Close only after the actual returned handoff was locally decided.")
        directive.setdefault("transitions", []).append({**deepcopy(p), "actor": deepcopy(request["actor"])})
        directive["status"] = p["status"]
        return [put("cloud_directive", p["id"], directive)]
    if action == "cloud.handoff.decide":
        fields(p, "id", "handoff_sha256", "status", "accepted", "rejected", "rationale")
        decision = require_student(request)
        handoff = _read(state, request, "cloud_handoff", p["id"])
        require(handoff["block"]["sha256"] == p["handoff_sha256"] and not handoff.get("local_decision"), "CLOUD_HANDOFF_CHANGED", "Decide the immutable original proposal once.")
        require(p["status"] in ("accepted", "partially_accepted", "rejected"), "CLOUD_HANDOFF_DECISION", "Choose an explicit local outcome.")
        require(isinstance(p["accepted"], list) and isinstance(p["rejected"], list), "CLOUD_HANDOFF_SCOPE", "List accepted and unaccepted parts separately.")
        require((p["status"] == "rejected" and not p["accepted"] and bool(p["rejected"])) or (p["status"] == "accepted" and bool(p["accepted"]) and not p["rejected"]) or (p["status"] == "partially_accepted" and bool(p["accepted"]) and bool(p["rejected"])), "CLOUD_HANDOFF_SCOPE", "The scope must agree with the decision.")
        handoff["local_decision"] = {**deepcopy(p), "actor": decision, "implementation_status": "not_applied_by_this_decision"}
        return [put("cloud_handoff", p["id"], handoff)]
    raise DomainError("UNKNOWN_ACTION", action)


def sync_event(instance, request):
    """Apply once; run current runtime checks; publish a separately bound receipt."""
    from . import service
    from .journal import Journal
    require(request.get("action") == "cloud.event.apply", "CLOUD_APPLY_REQUEST", "Sync needs the explicit local application request.")
    applied = service.execute(instance, request)
    store = Journal(instance)
    event_id = request["payload"]["id"]
    state = store.read_state()
    existing = get(state, "cloud_sync_receipt", event_id, False)
    if existing:
        return {"status": "duplicate", "receipt": existing, "application": applied}
    diagnostic = service.doctor(instance, full=True)
    if not diagnostic["ok"]:
        return {"status": "applied_needs_validation", "application": applied, "doctor": diagnostic}
    frozen = store.read_state()
    require(frozen["revision"] == diagnostic["plan"]["revision"], "CLOUD_VALIDATION_STALE", "State changed after runtime validation.")
    fingerprint = service._validator_fingerprint()
    require(fingerprint == diagnostic["plan"]["validator_sha256"], "CLOUD_VALIDATION_STALE", "Validator changed after runtime validation.")
    receipt_request = {"request_id": "cloud-sync/"+event_id, "action": "cloud.receipt.finalize", "payload": {"event_id": event_id, "revision": frozen["revision"], "validator_sha256": fingerprint}, "actor": {"role": "system", "source": "runtime-doctor", "text": "Publish only the actual checked local result."}, "expected": {k: v["version"] for k, v in frozen["objects"].items()}}
    def finalize(current, submitted):
        require(current["revision"] == frozen["revision"] and service._validator_fingerprint() == fingerprint, "CLOUD_VALIDATION_STALE", "Verification basis changed before receipt publication.")
        event = _read(current, submitted, "cloud_event", event_id)
        require(event["status"] == "applied", "CLOUD_APPLY_REQUIRED", "Only actual local application can be synced.")
        event["status"] = "synced"
        receipt = {"protocol_version": PROTOCOL, "session_id": event_id, "status": "synced", "event_sha256": event["block"]["sha256"], "written_objects": [e["kind"]+"/"+e["id"] for e in applied.get("effects", [])], "doctor": diagnostic, "validator_sha256": fingerprint, "permission": "none"}
        return [put("cloud_event", event_id, event), _new(current, "cloud_sync_receipt", event_id, receipt)]
    committed = store.apply(receipt_request, finalize)
    return {"status": "synced", "receipt": get(store.read_state(), "cloud_sync_receipt", event_id), "application": applied, "commit": committed}
