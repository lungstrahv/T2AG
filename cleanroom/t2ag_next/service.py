"""Application boundary, recovery views and change-scoped integrity checks."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import os
import tempfile

from . import support, learning, exchange, reading_bridge, groups, reconciliation, planning, cloud, migration_recovery, governance, continuity
from .journal import Journal
from .model import DomainError, get, require, put


MODULES = (support, learning, exchange, reading_bridge, groups, reconciliation, planning, cloud, migration_recovery, governance, continuity)
ENTRY_LANES = {"entry.teach": "teach", "entry.maintain": "maintain", "entry.audit": "audit", "entry.release": "release"}


class _ContextObjects(dict):
    def __init__(self, objects):
        super().__init__(objects)
        self.used = set()

    def get(self, name, default=None):
        if name in self:
            self.used.add(name)
        return super().get(name, default)

    def __getitem__(self, name):
        result = super().__getitem__(name)
        self.used.add(name)
        return result


def actions():
    names = [action for module in MODULES for action in module.ACTIONS if action not in governance.LEGACY_ACTIONS]
    require(len(names) == len(set(names)), "DUPLICATE_ACTION", "Domain action ownership overlaps.")
    return sorted(names)


def dispatch(state, request):
    governance.validate_dispatch(state, request)
    if request.get("campaign_id"):
        campaign = get(state, "campaign", request["campaign_id"])
        require(campaign["status"] == "active", "STOPPED_BUDGET", "Campaign reached its authorized resource limit.")
    matches = [m for m in MODULES if request.get("action") in m.ACTIONS]
    require(len(matches) == 1, "UNKNOWN_ACTION", "Use a registered, unambiguous domain action.")
    return matches[0].plan(state, request)


def execute(instance, request):
    if request.get("action") == "bridge.configure":
        require(request.get("payload", {}).get("instance_id") == Journal(instance).validate()["instance_id"], "INSTANCE_IDENTITY", "Bridge identity must be this actual local instance.")
    result = Journal(instance).apply(request, dispatch)
    # No broad doctor or cache refresh in this critical path. The complete domain
    # transition and journal publication have already been checked under the lock.
    result["persistence"] = "committed"
    result["learner"] = {"saved": True, "message": "Progress saved."}
    judgments = [e["data"].get("judgement") for e in result.get("effects", []) if e["kind"] == "cursor"]
    if any(judgments):
        result["learner"]["judgement"] = next(j for j in judgments if j)
    return result


def _entities(state, kind):
    return {e["id"]: deepcopy(e["data"]) for e in state["objects"].values() if e["kind"] == kind}


def resolve(state, kind, identity):
    item = get(state, kind, identity, False)
    if item is not None:
        return identity, item
    alias = get(state, "alias", f"{kind}/{identity}", False)
    require(alias is not None and alias["kind"] == kind, "NOT_FOUND", f"Missing {kind}: {identity}")
    return alias["target_id"], get(state, kind, alias["target_id"])


def teaching_readiness(state, session_id, activity_id):
    """Validate the current source closure from one immutable read snapshot."""
    errors = []
    def fetch(kind, identity):
        obj = get(state, kind, identity, False) if identity else None
        if obj is None:
            errors.append(f"missing {kind}: {identity}")
        return obj or {}
    session = fetch("session", session_id)
    activity = fetch("activity", activity_id)
    if session.get("status") != "active" or session.get("readiness") != "ready" or session.get("activity_id") != activity_id:
        errors.append("session is not active and ready for this activity")
    scope_id, prep_id = activity.get("scope_id"), activity.get("preparation_id")
    scope, prep = fetch("scope", scope_id), fetch("preparation", prep_id)
    scan = fetch("scan", session.get("scan_id"))
    lm = fetch("lessonmap", prep.get("lessonmap_id"))
    if not (scope_id and prep_id and session.get("scope_id") == scope_id and session.get("preparation_id") == prep_id
            and scope.get("activity_id") == prep.get("activity_id") == lm.get("activity_id") == activity_id
            and prep.get("scope_id") == lm.get("scope_id") == scan.get("scope_id") == scope_id
            and scan.get("session_id") == session_id):
        errors.append("session, preparation, map, Scope and scan identities disagree")
    ids = scope.get("page_ids", [])
    deliveries, receipts = scan.get("deliveries", []), prep.get("receipts", [])
    if not ids or set(lm.get("page_ids", [])) != set(ids) or {d.get("page_id") for d in deliveries} != set(ids) or {d.get("page_id") for d in receipts} != set(ids):
        errors.append("Scope page coverage is incomplete")
    for delivery in deliveries:
        page = fetch("page", delivery.get("page_id"))
        source = fetch("source", page.get("source_id"))
        try:
            learning.validate_current_page(state, delivery.get("page_id"))
        except DomainError as error:
            errors.append(error.message)
        page_head = fetch("page_head", f"{page.get('source_id')}/{page.get('pdf_page_index')}")
        if page_head.get("page_id") != delivery.get("page_id"):
            errors.append("verified page version changed after Scope preparation")
        if delivery.get("session_id") != session_id or delivery.get("source_document_sha256") != source.get("content_sha256"):
            errors.append("page delivery identity differs")
        if delivery.get("form") == "verified_text":
            if page.get("layout_critical") is not False or delivery.get("content") != page.get("verified_text"):
                errors.append("verified text delivery is incomplete or layout-sensitive")
        elif delivery.get("form") == "render_png":
            if not page.get("render_blob_sha256") or delivery.get("blob_sha256") != page.get("render_blob_sha256") or delivery.get("whole_page") is not True:
                errors.append("whole-page image evidence differs")
        elif delivery.get("form") == "pdf_direct":
            if delivery.get("whole_page") is not True:
                errors.append("whole PDF page delivery required")
        else:
            errors.append("unknown page delivery form")
    return {"ready": not errors, "errors": errors}


def context(instance, *, entry, session_lane=None, scope=None, session_id=None, level="critical"):
    require(entry in ENTRY_LANES, "ENTRY_REQUIRED", "Choose entry.teach, entry.maintain, entry.audit or entry.release.")
    require(session_lane in ("teach", "maintain", "audit", "release"), "LANE_REQUIRED", "Declare session_lane independently from the entry axis.")
    require(level in ("critical", "L0", "L1", "L2"), "CONTEXT_LEVEL", "Unknown context level.")
    store = Journal(instance)
    state = store.read_state()
    state["objects"] = _ContextObjects(state["objects"])
    lane = session_lane
    result = {"entry": entry, "lane": lane, "revision": state["revision"], "scope": scope, "level": level,
              "authority": "single_journal_snapshot", "recovery_settled": True,
              "warnings": []}
    result["verification"] = deepcopy(getattr(store, "last_verification", {"scope": "unreported", "full_asset_audit_pending": True}))
    result["handoffs"] = []
    for identity, h in _entities(state, "handoff").items():
        if h.get("status") != "active" or h.get("lane") != lane or h.get("scope") != scope:
            continue
        stale = any(state["objects"].get(k, {}).get("version") != v for k, v in h.get("source_versions", {}).items())
        result["handoffs"].append({"id": identity, **h, "source_stale": stale})
    student = get(state, "student", "current", False) or {}
    preference_keys = {"language", "teaching_language", "learning_language", "exercise_hint_gate", "preferences", "presentation_preferences", "collaboration_preferences", "domain_tiers", "skin_id", "migration_status"}
    result["preferences"] = {k: v for k, v in student.items() if k in preference_keys}
    if level in ("L1", "L2"):
        result["profile"] = student
    elif student.get("legacy_profile_body"):
        result["profile_evidence"] = {"kind": "student", "id": "current", "available_in": "L1 or inspect student current", "mapping_status": student.get("migration_status")}
    if student.get("skin_id"):
        result["skin_display"] = {"untrusted_display_only": True, **get(state, "skin", student["skin_id"])}
    if entry != "entry.teach":
        result["learning_ready"] = False
        result["summary"] = {kind: len(_entities(state, kind)) for kind in ("course", "activity", "issue", "rule")}
        return _size(result, state)
    require(scope is not None, "SCOPE_REQUIRED", "Teaching recovery needs a course identity.")
    course_id, course = resolve(state, "course", scope)
    result["course"] = {"id": course_id, **course}
    result["groups"] = []
    for identity, group in _entities(state, "group").items():
        if group.get("status") == "active" and course_id in group.get("members", []):
            calendar = {k: v for k, v in group.get("calendar", {}).items()
                        if k not in {"body", "legacy", "legacy_fields", "tables"}}
            result["groups"].append({"id": identity, "status": "active",
                "calendar": calendar, "time_plan": group.get("time_plan"),
                "frequency_plan": group.get("frequency_plan"),
                "closing_condition_count": len(group.get("closure_conditions", [])),
                "plan_and_review_available_in": "inspect group " + identity})
    result["bindings"] = []
    for identity, binding in _entities(state, "binding").items():
        if binding.get("status") == "active" and course_id in binding.get("course_ids", []):
            observations = binding.get("observations", [])
            result["bindings"].append({"id": identity, "course_ids": binding["course_ids"],
                "intent": binding.get("intent"), "ritual_anchor": binding.get("ritual_anchor"),
                "budget_weight": 0, "latest_observation": observations[-1] if observations else None,
                "history_available_in": "inspect binding " + identity})
    if course.get("teacher_id"):
        result["teacher"] = get(state, "teacher", course["teacher_id"])
    if course.get("teacher_overlay_id"):
        result["teacher_overlay"] = {"attributed_preferences_not_machine_enforcement": True,
                                     **get(state, "teacher_overlay", course["teacher_overlay_id"])}
    if course.get("status") == "planned":
        result.update(learning_ready=False, waiting_for="course_activation", current_activity=None)
        return _size(result, state)
    activity_id = course.get("current_activity_id")
    require(bool(activity_id), "NO_FRONT_ACTIVITY", "No unambiguous current activity; select a named activity.")
    activity = get(state, "activity", activity_id)
    require(activity.get("course_id") == course_id, "ROUTE_CONFLICT", "Course and current activity disagree.")
    cursor = get(state, "cursor", activity_id, False) or {}
    result.update(current_activity={"id": activity_id, **activity}, cursor=cursor,
                  waiting_for=cursor.get("waiting_for", "activity_start"), learning_ready=False)
    uncertainties = course.get("uncertainties", []) + activity.get("uncertainties", []) + cursor.get("uncertainties", [])
    result["uncertainties"] = uncertainties
    if uncertainties:
        result.update(recovery_settled=False, waiting_for="clarify_conflict")
    elif course.get("status") == "paused" or course.get("paused"):
        result["waiting_for"] = "resume_course"
    elif course.get("status") != "ongoing":
        result["waiting_for"] = "course_closed" if course.get("status") in ("completed", "closed_incomplete") else "clarify_course_state"
    elif activity.get("status") == "pending_close":
        result["waiting_for"] = "confirm_close"
        result["pending_close"] = activity.get("pending_close") or cursor.get("pending_body")
        result["pending_sha256"] = activity.get("pending_sha256")
        if not result["pending_close"]:
            result.update(recovery_settled=False, waiting_for="recover_missing_close_body")
    elif activity.get("status") != "ongoing":
        result["waiting_for"] = "select_or_reopen_activity"
    elif course.get("learning_mode") != "textbook":
        result["learning_ready"] = True
    else:
        readiness = teaching_readiness(state, session_id, activity_id)
        ready = readiness["ready"]
        # Session shape is deliberately checked, never inferred from a historical
        # scan, a preparation snapshot or a caller's assertion of readiness.
        result["learning_ready"] = ready
        result["source_readiness"] = readiness
        if not ready:
            result["warnings"].append("Current-session source consumption must be established before textbook teaching.")
    if result["learning_ready"] and cursor.get("block_id"):
        block = get(state, "block", cursor["block_id"], False)
        if block is None and cursor.get("legacy") and cursor.get("requires_current_session_revalidation"):
            # An imported logical checkpoint is a saved position, not an
            # already prepared teaching body in this runtime.
            result["current_anchor"] = {"id": cursor["block_id"], "position": cursor.get("position"),
                                        "kind": "legacy_saved_position", "requires_preparation": True}
            result.update(learning_ready=False, waiting_for="prepare_saved_position")
        else:
            require(block is not None, "NOT_FOUND", f"Missing block: {cursor['block_id']}")
            result["current_block"] = {"id": cursor["block_id"], **block}
            if block.get("criterion_id"):
                result["current_criterion"] = {"id": block["criterion_id"], **get(state, "criterion", block["criterion_id"])}
    questions = [(qid, q) for qid, q in _entities(state, "question").items()
                 if q.get("course_id") == course_id or q.get("activity_id") == activity_id]
    result["open_questions"] = [{"id": qid, **q} for qid, q in questions if support.question_status(state, qid) not in ("closed", "answered", "merged")]
    result["answered_questions"] = [{"id": qid, "status": "answered", "title": q.get("title"), "inspect": ["question", qid]}
                                    for qid, q in questions if q.get("status") == "answered"]
    notes = [e for e in state["objects"].values() if e["kind"] == "study_note" and e["data"].get("activity_id") == activity_id]
    if notes:
        latest = max(notes, key=lambda e: e["version"])
        result["saved_note"] = {"id": latest["id"], **get(state, "study_note", latest["id"])}
    result["suggestions"] = [{"id": sid, **d} for sid, d in _entities(state, "suggestion").items()
                             if d.get("scope") == course_id and d.get("status") in ("proposed", "deferred")]
    result["methods"] = [{"kind": kind, "id": mid, **d} for kind in ("reflection", "pattern", "keystone")
                         for mid, d in _entities(state, kind).items() if d.get("course_id") == course_id]
    if level in ("L1", "L2"):
        result["checkpoints"] = {cid: c for cid, c in _entities(state, "checkpoint").items() if c.get("activity_id") == activity_id or c.get("course_id") == course_id}
        result["source_manifest"] = [{"id": sid, **get(state, "source", sid)} for sid in course.get("source_ids", [])]
    if level == "L2":
        result["history"] = {k: v for k, v in state["objects"].items()
                             if v["data"].get("course_id") == course_id or v["data"].get("activity_id") == activity_id}
        if not result["learning_ready"] and course.get("learning_mode") == "textbook":
            result["history"] = {k: v for k, v in result["history"].items() if v["kind"] not in ("page", "block", "source", "scan")}
    if level in ("critical", "L0"):
        for name in ("methods", "suggestions"):
            result[name] = [{k: v for k, v in row.items() if k in {"id", "kind", "status", "scope", "course_id", "title", "testable_prediction", "claim", "owner", "confirmation_status"}}
                            for row in result[name]]
    return _size(result, state)


def _size(value, state=None):
    if value.get("level") in ("critical", "L0"):
        # Omit only archival representations, never the current prompt, response,
        # judgment, uncertainty or complete pending confirmation. Originals stay
        # addressable in the same immutable snapshot by their stable identities.
        archived = {"legacy", "legacy_fields", "legacy_progress", "progress_evidence", "ledger_evidence", "legacy_lifecycle", "original_body", "pending_evidence"}
        for field, kind in (("course", "course"), ("current_activity", "activity")):
            obj = value.get(field)
            if isinstance(obj, dict):
                removed = sorted(archived & set(obj))
                value[field] = {k: v for k, v in obj.items() if k not in archived}
                if removed:
                    value[field]["archival_evidence"] = {"inspect": [kind, obj["id"]], "fields": removed}
        cursor = value.get("cursor")
        if isinstance(cursor, dict):
            archives = {"legacy", "legacy_activity_position", "legacy_body_next_action", "legacy_current_section"}
            value["cursor"] = {k: v for k, v in cursor.items() if k not in archives}
            if archives & set(cursor):
                value["cursor"]["archival_evidence"] = {"inspect": ["cursor", value["current_activity"]["id"]], "fields": sorted(archives & set(cursor))}
        # Presentation is loaded once for its version before teaching. It need
        # not accompany every progress save, close decision or reconnect.
        presentation = (
            ("teacher", "teacher", value.get("course", {}).get("teacher_id")),
            ("teacher_overlay", "teacher_overlay", value.get("course", {}).get("teacher_overlay_id")),
            ("skin_display", "skin", value.get("preferences", {}).get("skin_id")),
        )
        for field, kind, identity in presentation:
            obj = value.get(field)
            if identity and isinstance(obj, dict):
                retained = {"name", "display_name", "identity_kind", "language", "tone", "pace",
                            "untrusted_display_only", "attributed_preferences_not_machine_enforcement"}
                value[field] = {k: v for k, v in obj.items() if k in retained}
                value[field].update(inspect=[kind, identity], full_content="L1 or inspect; read once per version before teaching")
        if value.get("pending_close"):
            for field in ("cursor", "current_activity"):
                obj = value.get(field)
                if isinstance(obj, dict) and obj.get("pending_body") == value["pending_close"]:
                    obj.pop("pending_body")
                    obj["pending_body_ref"] = "context.pending_close"
    if state is not None:
        used = set(state["objects"].used)
        for field, kind in (("open_questions", "question"), ("answered_questions", "question"), ("suggestions", "suggestion"), ("handoffs", "handoff")):
            used.update(f"{kind}/{row['id']}" for row in value.get(field, []))
        used.update(f"{row['kind']}/{row['id']}" for row in value.get("methods", []))
        used.update(f"checkpoint/{identity}" for identity in value.get("checkpoints", {}))
        used.update(value.get("history", {}))
        value["versions"] = {k: state["objects"][k]["version"] for k in sorted(used) if k in state["objects"]}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    value["size"] = {"characters_before_size_field": len(encoded), "utf8_bytes_before_size_field": len(encoded.encode())}
    return value


def projection(state):
    courses = _entities(state, "course")
    activities = _entities(state, "activity")
    spans = _entities(state, "timespan")
    corrected = {x["corrects"] for x in spans.values() if x.get("corrects")}
    stats = {}
    for sid, span in spans.items():
        if sid in corrected:
            continue
        item = stats.setdefault(span["activity_id"], {"exact_seconds": 0, "estimated_seconds": 0, "unknown_spans": 0})
        if span["quality"] == "unknown":
            item["unknown_spans"] += 1
        else:
            item[span["quality"] + "_seconds"] += span["seconds"]
    return {"revision": state["revision"], "courses": courses, "activities": activities, "cursors": _entities(state, "cursor"),
            "teachers": _entities(state, "teacher"), "time_statistics": stats,
            "history_index": continuity.history_index(state)}


def refresh(instance, write=False):
    expected = projection(Journal(instance).read_state())
    path = Path(instance) / "derived" / "state.json"
    actual = None
    if path.exists():
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    changed = expected != actual
    if changed and write:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="state-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(expected, f, ensure_ascii=False, sort_keys=True, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {"ok": True, "changed": changed, "written": changed and write, "revision": expected["revision"], "authority": False}


CHECK_INPUTS = {
    "routes": {"course", "activity", "cursor"},
    "references": {"course", "activity", "source", "teacher", "alias", "review", "attempt"},
    "groups": {"course", "group", "activity", "timespan", "group_assessment", "group_progress", "group_observation", "group_triage", "group_keystone_entry"},
    "rules": {"rule", "issue"},
    "teaching": {"course", "activity", "session", "scan", "scope", "preparation", "lessonmap", "page", "page_head", "source", "ocr_raw", "ocr_correction", "ocr_verification"},
    "learning_history": {"attempt", "review", "criterion", "exercise", "mistake", "exam", "exam_bank"},
    "domain_references": {"course", "activity", "checkpoint", "completion", "group", "attempt", "review", "criterion", "mistake", "exam", "exam_bank", "exam_selection", "variant", "retest_plan", "aged_review", "aged_window", "aged_calendar", "learning_structure", "learning_segment", "exam_reinforcement", "reading", "reading_note", "planning_conditions", "learning_plan", "teacher", "teacher_overlay", "reconciliation"},
    "authorization": {"ticket", "session", "block", "course", "activity"},
    "exchange": {"bridge", "contribution", "receipt", "reading_context", "reading_contribution", "reading_event", "reading_receipt"},
    "cloud": {"cloud_baseline", "cloud_event", "cloud_candidate", "cloud_sync_receipt", "cloud_directive", "cloud_handoff", "bridge", "course", "activity", "cursor", "timespan"},
    "lifecycles": {"course", "activity", "reading", "engagement", "timespan", "checkpoint"},
    "projection": set(),
}

KNOWN_KINDS = {"student", "teacher", "teacher_overlay", "course", "activity", "cursor", "checkpoint", "milestone", "praxis", "completion", "close", "course_close", "timespan",
               "reading", "engagement", "engagement_entry", "group", "group_review", "group_assessment", "group_progress", "group_observation", "group_triage", "group_keystone_entry", "binding", "suggestion", "thought", "reflection", "pattern", "keystone", "method_use", "issue", "rule", "history", "alias", "handoff", "skin", "external", "external_use", "campaign",
               "source", "page", "page_head", "ocr_raw", "ocr_correction", "ocr_verification", "scope", "preparation", "scan", "lessonmap", "block", "session", "ticket", "criterion", "attempt", "review", "question", "mistake", "exam", "exam_bank", "exercise",
               "bridge", "contribution", "receipt", "reading_context", "reading_contribution", "reading_event", "reading_receipt", "legacy_file", "migration", "reconciliation", "validation", "asset_verification"}
KNOWN_KINDS.update(learning.ENTITY_CONTRACTS)
KNOWN_KINDS.update({"planning_conditions", "planning_conditions_revision", "learning_plan", "learning_plan_revision", "teacher_revision", "teacher_overlay_revision", "reading_note"})
KNOWN_KINDS.update(CHECK_INPUTS["cloud"])
CHECK_INPUTS["domain_references"].add("migration_recovery")
KNOWN_KINDS.add("migration_recovery")
KNOWN_KINDS.add("study_note")
CHECK_INPUTS["domain_references"].add("study_note")
KNOWN_KINDS.update(governance.ENTITY_KINDS)
KNOWN_KINDS.update(continuity.ENTITY_KINDS)
KNOWN_KINDS.update(groups.ENTITY_KINDS)
CHECK_INPUTS["groups"].update(groups.ENTITY_KINDS)
CHECK_INPUTS["domain_references"].update(continuity.ENTITY_KINDS)
CHECK_INPUTS["governance"] = set(governance.ENTITY_KINDS)


def _validator_fingerprint():
    files = ("model.py", "journal.py", "support.py", "learning.py", "service.py", "exchange.py", "reading_bridge.py", "groups.py", "reconciliation.py", "planning.py", "cloud.py", "migration_recovery.py", "governance.py", "continuity.py")
    root = Path(__file__).resolve().parent
    return support.digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files})


def validate_negative(instance, validation_id, candidate_request, expected_code):
    """Execute a negative domain scenario without applying its candidate effects.

    The recorded evidence covers this exact scenario and validator, not every
    possible execution or host-side tool enforcement.
    """
    require(candidate_request.get("action") in actions(), "UNKNOWN_ACTION", "A negative scenario must target a registered action.")
    require(isinstance(validation_id, str) and bool(validation_id) and isinstance(expected_code, str) and bool(expected_code), "VALIDATION_INPUT", "Name the evidence and exact expected rejection code.")
    store = Journal(instance)
    state = store.read_state()
    fingerprint = _validator_fingerprint()
    request = {"request_id": "validation/" + validation_id, "action": "validation.negative_probe",
               "payload": {"candidate": deepcopy(candidate_request), "expected_code": expected_code, "validator_sha256": fingerprint},
               "actor": {"role": "system", "source": "t2ag_next.service.validate_negative", "text": "Execute the named negative scenario without applying its candidate effects."},
               "expected": {k: v["version"] for k, v in state["objects"].items()}}
    previous = store.lookup(request["request_id"])
    if previous:
        proof = get(state, "validation", validation_id)
        require(proof.get("candidate_sha256") == support.digest(candidate_request) and proof.get("expected_code") == expected_code and proof.get("validator_sha256") == fingerprint, "VALIDATION_ID_REUSED", "Evidence identity already binds another scenario or implementation.")
        return previous
    def probe(current, submitted):
        require(get(current, "validation", validation_id, False) is None, "VALIDATION_ID_REUSED", "Evidence identity already exists.")
        require(_validator_fingerprint() == fingerprint, "VALIDATOR_CHANGED", "Validation code changed before the scenario ran.")
        candidate = deepcopy(submitted["payload"]["candidate"])
        try:
            dispatch(current, candidate)
        except DomainError as error:
            require(error.code == expected_code, "NEGATIVE_WRONG_REJECTION", f"Expected {expected_code}; observed {error.code}.")
        else:
            raise DomainError("NEGATIVE_ACCEPTED", "The candidate was accepted; it is not negative execution evidence.")
        require(_validator_fingerprint() == fingerprint, "VALIDATOR_CHANGED", "Validation code changed during the scenario.")
        return [put("validation", validation_id, {"implementation_ref": "action:" + candidate["action"], "negative_result": "expected_rejection", "expected_code": expected_code,
            "candidate": candidate, "candidate_sha256": support.digest(candidate), "validator_sha256": fingerprint, "evaluated_revision": current["revision"],
            "scope": "one_domain_planner_scenario_no_candidate_effects_applied"})]
    return store.apply(request, probe)


def check_plan(state, changed_kinds=None, full=False):
    if not full:
        require(isinstance(changed_kinds, (list, set, tuple)) and bool(changed_kinds), "CHECK_SCOPE", "Name the changed object kinds or request full validation.")
        require(set(changed_kinds) <= KNOWN_KINDS, "UNKNOWN_CHANGED_KIND", "Affected-check selection contains an unknown object kind.")
    selected = list(CHECK_INPUTS) if full else [n for n, inputs in CHECK_INPUTS.items() if inputs & set(changed_kinds or [])]
    require(full or changed_kinds is not None, "CHECK_SCOPE", "Choose a full check or specify affected object kinds.")
    require(bool(selected), "NO_DOMAIN_CHECKS", "No domain check is registered for these kinds; journal validation alone is not domain validation.")
    body = {"checks": selected, "revision": state["revision"], "changed_kinds": sorted(changed_kinds or []), "full": full}
    body["validator_sha256"] = _validator_fingerprint()
    body["state_sha256"] = support.digest(state)
    body["plan_sha256"] = support.digest(body)
    return body


def doctor(instance, *, changed_kinds=None, full=False, plan=None):
    store = Journal(instance)
    state = store.read_state()
    expected = check_plan(state, changed_kinds, full) if plan is None else plan
    unsigned = {k: v for k, v in expected.items() if k != "plan_sha256"}
    require(expected.get("plan_sha256") == support.digest(unsigned) and expected.get("state_sha256") == support.digest(state),
            "STALE_CHECK_PLAN", "The check plan or its source state changed.")
    rebuilt = check_plan(state, expected.get("changed_kinds"), expected.get("full", False))
    require(expected == rebuilt, "INCOMPLETE_CHECK_PLAN", "The plan must contain the complete selected check set.")
    require(set(expected["checks"]) <= set(CHECK_INPUTS), "UNKNOWN_CHECK", "Check plan contains unknown checks.")
    findings = []
    def finding(code, status, message, obj=None):
        findings.append({"code": code, "status": status, "message": message, "object": obj})
    courses, activities = _entities(state, "course"), _entities(state, "activity")
    for check in expected["checks"]:
        if check == "governance":
            findings.extend(governance.doctor_findings(state))
        elif check == "routes":
            for cid, c in courses.items():
                aid = c.get("current_activity_id")
                if aid and (aid not in activities or activities[aid].get("course_id") != cid):
                    finding("route.invalid", "FAIL", "Current activity does not belong to its course.", cid)
                if c.get("uncertainties"):
                    finding("course.uncertain", "REVIEW", "Imported course needs explicit reconciliation.", cid)
            for aid, cur in _entities(state, "cursor").items():
                if aid not in activities:
                    finding("cursor.orphan", "FAIL", "Cursor has no activity.", aid)
                if cur.get("uncertainties"):
                    finding("cursor.uncertain", "REVIEW", "Pending historical ambiguity must not be guessed.", aid)
        elif check == "references":
            for aid, a in activities.items():
                if a.get("course_id") not in courses:
                    finding("activity.orphan", "FAIL", "Activity references missing course.", aid)
            for cid, c in courses.items():
                for sid in c.get("source_ids", []):
                    if get(state, "source", sid, False) is None:
                        finding("source.missing", "FAIL", "Course source missing.", cid)
                if c.get("teacher_id") and get(state, "teacher", c["teacher_id"], False) is None:
                    finding("teacher.missing", "FAIL", "Course teacher missing.", cid)
            for alias_id, a in _entities(state, "alias").items():
                if get(state, a["kind"], a["target_id"], False) is None:
                    finding("alias.broken", "FAIL", "Alias target is missing.", alias_id)
        elif check == "groups":
            groups = _entities(state, "group")
            if sum(g.get("status") == "active" for g in groups.values()) > 1:
                finding("group.multiple_active", "FAIL", "At most one group can be active.")
            for gid, g in groups.items():
                if any(c not in courses for c in g.get("members", [])):
                    finding("group.missing_member", "FAIL", "A group member is missing.", gid)
                if g.get("capacity") is not None and len(g.get("members", [])) > g["capacity"]:
                    finding("group.capacity", "FAIL", "Group composition exceeds its capacity.", gid)
            for cid in courses:
                for kind, maximum in (("lesson", 3), ("exercise", 2)):
                    count = sum(a.get("course_id") == cid and a.get("activity_type") == kind and a.get("status") in ("ongoing", "pending_close") for a in activities.values())
                    if count > maximum: finding("activity.capacity", "FAIL", f"Active {kind} capacity exceeded.", cid)
        elif check == "rules":
            for rid, rule in _entities(state, "rule").items():
                if rule.get("status") != "active":
                    continue
                if rule.get("enforcement") in ("context", "prose"):
                    finding("rule.soft_guarantee", "WARN", "This rule depends on agent compliance and is not a hard host gate.", rid)
                elif not rule.get("negative_evidence") or not rule.get("implementation_ref"):
                    finding("rule.unbacked", "FAIL", "Machine rule lacks implementation/negative evidence.", rid)
                else:
                    reference = rule["implementation_ref"]
                    known = isinstance(reference, str) and ((reference.startswith("action:") and reference[7:] in actions()) or (reference.startswith("check:") and reference[6:] in CHECK_INPUTS))
                    if not known:
                        finding("rule.broken_implementation", "FAIL", "Machine rule must resolve to an actual registered action or check.", rid)
                    evidence = rule["negative_evidence"]
                    proof = get(state, "validation", evidence, False) if isinstance(evidence, str) else None
                    if not proof or proof.get("implementation_ref") != reference or proof.get("negative_result") != "expected_rejection" or proof.get("validator_sha256") != _validator_fingerprint() or proof.get("expected_code") != rule.get("failure_signal"):
                        finding("rule.unverified_negative_evidence", "REVIEW", "A nonempty evidence label is not verified execution of a negative scenario.", rid)
        elif check == "teaching":
            for sid, session in _entities(state, "session").items():
                activity = activities.get(session.get("activity_id"), {})
                course = courses.get(activity.get("course_id"), {})
                if session.get("status") == "active" and session.get("readiness") == "ready" and course.get("learning_mode") == "textbook":
                    ready = teaching_readiness(state, sid, session.get("activity_id"))
                    for reason in ready["errors"]:
                        finding("teaching.invalid_ready_claim", "FAIL", reason, sid)
        elif check == "learning_history":
            attempts = _entities(state, "attempt")
            criteria = _entities(state, "criterion")
            for rid, review in _entities(state, "review").items():
                if review.get("history_only") or review.get("migration_state") == "history_only":
                    continue
                attempt = attempts.get(review.get("attempt_id"))
                criterion = criteria.get(review.get("criterion_id"))
                if not attempt or not criterion:
                    finding("review.broken_evidence", "FAIL", "Review requires its actual attempt and frozen criterion.", rid)
                    continue
                answers = {a.get("problem_id") for a in attempt.get("answers", [])}
                ratings = review.get("ratings", [])
                if {x.get("problem_id") for x in ratings} != answers or len({x.get("problem_id") for x in ratings}) != len(ratings):
                    finding("review.problem_scope", "FAIL", "Review must cover exactly the submitted problem set.", rid)
                for rating in ratings:
                    help_ = attempt.get("assistance", {}).get(rating.get("problem_id"), {})
                    if rating.get("independent") and (help_.get("polluted") or help_.get("level") != "none"):
                        finding("review.false_independence", "FAIL", "Assisted or unclassified work cannot be independent evidence.", rid)
            for eid, exam in _entities(state, "exam").items():
                if exam.get("history_only"):
                    continue
                if exam.get("status") in ("submitted", "graded", "settled") and exam.get("attempt_id") not in attempts:
                    finding("exam.missing_submission", "FAIL", "Exam judgment has no actual submission.", eid)
        elif check == "domain_references":
            links = {
                "study_note": {"activity_id": "activity", "course_id": "course"},
                "continuity_map": {"activity_id": "activity", "from_lessonmap_id": "lessonmap", "to_lessonmap_id": "lessonmap", "preparation_id": "preparation"},
                "external_revision": {"reference_id": "external"},
                "exam_selection": {"bank_id": "exam_bank", "group_id": "group"},
                "variant": {"mistake_id": "mistake", "activity_id": "activity"},
                "retest_plan": {"course_id": "course", "session_ids": "session"},
                "aged_review": {"activity_id": "activity", "variant_ids": "variant", "mistake_ids": "mistake", "window_id": "aged_window"},
                "aged_window": {"course_id": "course", "completed_segment_ids": "learning_segment", "eligible_mistake_ids": "mistake", "related_segment_id": "learning_segment"},
                "aged_calendar": {"course_id": "course", "last_sheet_segment_ids": "learning_segment"},
                "learning_structure": {"course_id": "course"},
                "learning_segment": {"course_id": "course", "checkpoint_ids": "checkpoint"},
                "exam_reinforcement": {"course_id": "course", "activity_ids": "activity"},
                "reading_note": {"reading_id": "reading"},
                "learning_plan": {"conditions_id": "planning_conditions"},
                "teacher_overlay": {"course_id": "course"},
            }
            for kind, names in links.items():
                for identity, data in _entities(state, kind).items():
                    if data.get("history_only") or data.get("migration_requires_reconciliation"):
                        finding("domain.history_unreconciled", "REVIEW", "Preserved historical evidence has not been promoted to an active domain object.", f"{kind}/{identity}")
                        continue
                    for field, target_kind in names.items():
                        refs = data.get(field)
                        if refs is None: continue
                        if not isinstance(refs, list): refs = [refs]
                        for ref in refs:
                            if not isinstance(ref, str) or get(state, target_kind, ref, False) is None:
                                finding("domain.broken_reference", "FAIL", f"{field} does not resolve to an actual {target_kind}.", f"{kind}/{identity}")
                    if kind == "learning_structure":
                        for segment in data.get("segments", []):
                            for cid in segment.get("checkpoint_ids", []):
                                checkpoint = get(state, "checkpoint", cid, False)
                                activity = get(state, "activity", checkpoint.get("activity_id"), False) if checkpoint and checkpoint.get("activity_id") else None
                                if not activity or activity.get("course_id") != data.get("course_id"):
                                    finding("segment.cross_course", "FAIL", "A named segment must bind actual checkpoints from its course.", identity)
                    elif kind == "retest_plan":
                        results, slots = data.get("results", []), data.get("slots", [])
                        indices = [row.get("slot_index") for row in results]
                        if len(set(indices)) != len(indices) or any(type(index) is not int or not 0 <= index < len(slots) for index in indices):
                            finding("retest.slot_conflict", "FAIL", "Retest results must fill distinct real slots.", identity)
                        if data.get("status") == "complete" and set(indices) != set(range(len(slots))):
                            finding("retest.incomplete", "FAIL", "A complete plan must retain each actual result.", identity)
                        for row in results:
                            review = get(state, "review", row.get("review_id"), False) if row.get("review_id") else None
                            if not review or row.get("problem_id") not in {rating.get("problem_id") for rating in review.get("ratings", [])}:
                                finding("retest.unbacked_result", "FAIL", "A slot result has no actual problem review.", identity)
                    elif kind == "exam_selection":
                        bank = get(state, "exam_bank", data.get("bank_id"), False) if data.get("bank_id") else None
                        ids = data.get("problem_ids", [])
                        if not bank or not ids or len(set(ids)) != len(ids) or not set(ids) <= set(bank.get("problems", {})):
                            finding("exam.invalid_selection", "FAIL", "Selected questions must be distinct members of the actual independent bank.", identity)
                    elif kind == "exam_reinforcement":
                        if get(state, "exam", identity, False) is None:
                            finding("exam.orphan_reinforcement", "FAIL", "Reinforcement needs its actual originating examination.", identity)
                        if data.get("status") == "complete" and len(set(data.get("learning_dates", []))) < data.get("required_learning_dates", 3):
                            finding("exam.incomplete_reinforcement", "FAIL", "Declared reinforcement is missing the required distinct learning dates.", identity)
                    elif kind == "learning_plan":
                        if data.get("status") == "accepted":
                            if not data.get("decision") or not data.get("presentation_ref"):
                                finding("planning.unbacked_acceptance", "FAIL", "Accepted plan requires its actual full presentation and attributed decision.", identity)
                            for item in data.get("courses", []):
                                course = get(state, "course", item.get("id"), False) if item.get("id") else None
                                if not course or course.get("initial_plan_ref", {}).get("id") != identity:
                                    finding("planning.missing_course", "FAIL", "An accepted plan's actual course result is missing.", identity)
                    elif kind == "teacher_overlay":
                        if data.get("preferences") and not set(data["preferences"]) <= planning.OVERLAY_FIELDS:
                            finding("teacher.overlay_scope", "FAIL", "Presentation preferences cannot rewrite learning or governance rules.", identity)
            for identity, data in _entities(state, "reconciliation").items():
                if data.get("target_kind") not in reconciliation.FIELDS or not data.get("target_id") or get(state, data["target_kind"], data["target_id"], False) is None or data.get("future_permission") != "none":
                    finding("migration.invalid_reconciliation", "FAIL", "Reconciliation must retain a valid target and cannot grant future permission.", identity)
            for identity, data in _entities(state, "migration_recovery").items():
                if data.get("target_kind") not in ("exercise", "mistake", "cursor", "question") or not data.get("target_id") or get(state, data["target_kind"], data["target_id"], False) is None or data.get("future_permission") != "none" or data.get("historical_regrading") is not False or not data.get("evidence_refs"):
                    finding("migration.invalid_recovery", "FAIL", "Recovery must bind preserved evidence without regrading history or issuing permission.", identity)
        elif check == "authorization":
            sessions = _entities(state, "session")
            for tid, ticket in _entities(state, "ticket").items():
                if ticket.get("status") != "issued":
                    continue
                session = sessions.get(ticket.get("session_id"), {})
                if session.get("status") != "active" or session.get("activity_id") != ticket.get("activity_id"):
                    finding("ticket.invalid_session", "FAIL", "An issued ticket must bind a current active session.", tid)
                if ticket.get("purpose") == "next_block":
                    block = get(state, "block", ticket.get("block_id"), False) if ticket.get("block_id") else None
                    if not block or block.get("body_sha256") != ticket.get("body_sha256") or block.get("activity_id") != ticket.get("activity_id"):
                        finding("ticket.invalid_body", "FAIL", "Permission does not bind the current block body.", tid)
        elif check == "exchange":
            for cid, candidate in _entities(state, "contribution").items():
                if candidate.get("history_only"):
                    continue
                try: exchange.validate_envelope(candidate.get("envelope"))
                except (DomainError, TypeError, KeyError): finding("exchange.invalid_envelope", "FAIL", "Stored contribution violates its contract.", cid)
            for cid, candidate in _entities(state, "reading_contribution").items():
                try: reading_bridge.contribution(candidate.get("payload"))
                except (DomainError, TypeError, KeyError): finding("reading.invalid_contribution", "FAIL", "Stored reading contribution violates v1 wire contract.", cid)
        elif check == "cloud":
            for kind in ("cloud_event", "cloud_directive", "cloud_handoff"):
                for identity, data in _entities(state, kind).items():
                    try:
                        original = cloud.parse_block(data["block"]["raw"])
                        require(original == data["block"], "CLOUD_HASH", "Parsed data differs from the immutable cloud block.")
                        if kind == "cloud_event":
                            aid = data["activity_id"]
                            require(aid in activities and activities[aid]["course_id"] == data["course_id"], "CLOUD_ROUTE", "Cloud event lost its local activity.")
                            if data["status"] == "synced":
                                receipt = get(state, "cloud_sync_receipt", identity)
                                require(receipt["event_sha256"] == original["sha256"] and receipt["doctor"]["ok"], "CLOUD_RECEIPT", "Synced must retain the actual successful runtime check.")
                            if data["status"] in ("applied", "synced") and original["kind"] == cloud.CLOSE:
                                span = get(state, "timespan", "cloud/" + identity)
                                require(span.get("cloud_event_id") == identity, "CLOUD_DURATION", "Applied session keeps one uniquely identified time record.")
                    except (DomainError, KeyError, TypeError):
                        finding("cloud.invalid_record", "FAIL", "Cloud original, route, application or validation receipt is inconsistent.", kind + "/" + identity)
        elif check == "lifecycles":
            for kind, allowed in (("course", {"planned", "ongoing", "completed", "closed_incomplete"}), ("activity", {"planned", "ongoing", "pending_close", "completed", "closed_incomplete"}), ("reading", {"recording", "paused", "archived", "upgraded"})):
                for oid, obj in _entities(state, kind).items():
                    if obj.get("status") not in allowed:
                        finding("lifecycle.unknown", "REVIEW" if obj.get("legacy") else "FAIL", "Lifecycle requires explicit domain-specific reconciliation.", f"{kind}/{oid}")
            spans = _entities(state, "timespan")
            corrections = {}
            for sid, span in spans.items():
                if span.get("quality") not in ("exact", "estimated", "unknown"):
                    finding("time.quality", "FAIL", "Unknown time quality.", sid)
                if span.get("corrects"):
                    corrections.setdefault(span["corrects"], []).append(sid)
                    if span["corrects"] not in spans: finding("time.missing_original", "FAIL", "Correction references a missing original span.", sid)
            for corrected, replacements in corrections.items():
                if len(replacements) > 1: finding("time.branching_correction", "REVIEW", "Choose the intended correction branch explicitly.", corrected)
        elif check == "projection":
            if refresh(instance)["changed"]:
                finding("projection.stale", "WARN", "Derived view can be rebuilt; learning facts are retained.")
    if expected["full"]:
        store.validate()
    return {"ok": not any(f["status"] == "FAIL" for f in findings), "review_required": any(f["status"] == "REVIEW" for f in findings), "plan": expected, "findings": findings,
            "counts": {status: sum(f["status"] == status for f in findings) for status in ("PASS", "WARN", "FAIL", "REVIEW", "WAIVED")},
            "scope": "full" if expected["full"] else "affected", "unselected_checks": sorted(set(CHECK_INPUTS) - set(expected["checks"]))}
