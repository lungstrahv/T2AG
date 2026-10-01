"""Named support-domain transitions. This module does not perform I/O."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import re

from .model import DomainError, fields, get, key, put, require, require_student, require_student_decision, version


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _read(s, r, kind, identity):
    data = get(s, kind, identity)
    require(r.get("expected", {}).get(key(kind, identity)) == version(s, kind, identity),
            "STALE_OBJECT", f"Read dependency needs its current version: {kind}/{identity}")
    return data


def _new(s, kind, identity, data):
    require(get(s, kind, identity, False) is None, "IDENTITY_EXISTS", f"Identity cannot be reused: {kind}/{identity}")
    return put(kind, identity, data)


def _all(s, kind):
    # Constraints are evaluated against the current locked state, not an old client count.
    return [(e["id"], e["data"]) for e in s["objects"].values() if e["kind"] == kind]


def question_status(state, identity):
    """Validate merge lineage without dropping the original question history."""
    original = get(state, "question", identity)
    current, seen = original, {identity}
    while current.get("status") == "merged":
        target_id = current.get("merged_into")
        if not target_id or target_id in seen:
            return "invalid_merge"
        target = get(state, "question", target_id, False)
        if not target or target.get("activity_id") != original.get("activity_id") or not any(x.get("question_id") == identity for x in target.get("merged_sources", [])):
            return "invalid_merge"
        seen.add(target_id)
        identity, current = target_id, target
    return "merged" if original.get("status") == "merged" else current.get("status")


def _evidence(p):
    fields(p, "evidence")
    require(isinstance(p["evidence"], list) and bool(p["evidence"]), "EVIDENCE_REQUIRED", "Provide actual evidence references.")


def _provenance(r):
    a = r.get("actor", {})
    fields(a, "role", "source", "text")
    return deepcopy(a)


def _contributions(s, r, p):
    """Bind consumed candidates while creating the actual local result."""
    refs = p.get("contribution_refs", [])
    require(isinstance(refs, list), "CONTRIBUTION_REFS", "Contribution references must be a list.")
    for ref in refs:
        require(isinstance(ref, dict) and set(ref) == {"kind", "id", "sha256"} and ref["kind"] in ("contribution", "reading_contribution"), "CONTRIBUTION_REFS", "Use an exact candidate identity and semantic hash.")
        candidate = _read(s, r, ref["kind"], ref["id"])
        actual = candidate["envelope"]["content_sha256"] if ref["kind"] == "contribution" else candidate["payload"]["semantic_sha256"]
        require(ref["sha256"] == actual, "CONTRIBUTION_CHANGED", "Consumption must refer to the actual imported candidate.")


def learning_day(timestamp):
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    require(dt.tzinfo is not None, "TIMEZONE_REQUIRED", "Learning time needs an explicit timezone.")
    return (dt - timedelta(hours=4)).date().isoformat()


def _course(s, r, identity):
    data = _read(s, r, "course", identity)
    require(not data.get("retired"), "COURSE_RETIRED", "Retired course identity is historical.")
    return data


def _activity(s, r, identity):
    data = _read(s, r, "activity", identity)
    require(not data.get("retired"), "ACTIVITY_RETIRED", "Retired activity identity is historical.")
    return data


def _capacity(s, course_id, activity_type, excluding=None):
    limit = {"lesson": 3, "exercise": 2}.get(activity_type)
    if limit:
        active = [i for i, a in _all(s, "activity") if i != excluding and a.get("course_id") == course_id
                  and a.get("activity_type") == activity_type and a.get("status") in ("ongoing", "pending_close")]
        require(len(active) < limit, "ACTIVITY_CAPACITY", f"Active {activity_type} capacity is {limit}.")


def _bound(p, proposal):
    fields(p, "body_sha256")
    require(p["body_sha256"] == digest(proposal), "BODY_CHANGED", "Decision is not bound to the current complete proposal.")


def _close_intent(request, outcome, course=False):
    actor = require_student_decision(request, ("close", "end", "complete", "confirm", "结课", "结束", "关闭", "完成", "确认"), error_code="CLOSE_INTENT_REQUIRED")
    statement = actor["text"].casefold()
    require(re.search(r"(?:only|just)\s+(?:save|saving)|(?:仅|只是|只要|只需)保存", statement) is None, "CLOSE_INTENT_REQUIRED", "A save-only instruction does not close an activity.")
    if outcome == "completed":
        require(re.search(r"\b(?:unfinished|incomplete|not\s+completed)\b|未完成", statement) is None, "CLOSE_INTENT_REQUIRED", "The student's incomplete outcome cannot become completed.")
    else:
        require(re.search(r"\bconfirm\s+(?:course\s+)?completed\b|确认(?:课程)?完成", statement) is None, "CLOSE_INTENT_REQUIRED", "The stated complete outcome differs from the displayed incomplete result.")
    return actor


def plan(s, r):
    action, p = r.get("action"), r.get("payload")
    fields(p, "id")
    i = p["id"]
    actor = _provenance(r)
    decision_verbs = {
        "course.create": ("create", "建立", "创建", "建课"),
        "course.activate": ("activate", "start", "启动", "激活", "开始"),
        "course.pause": ("pause", "暂停"), "course.resume": ("resume", "恢复", "继续"),
        "course.teacher": ("change", "assign", "换", "更改", "分配"),
        "activity.start": ("start", "开始", "启动"), "activity.reopen": ("reopen", "重新打开", "重新开启"),
        "group.activate": ("activate", "start", "激活", "开始", "启动"),
        "group.close": ("close", "结组", "关闭", "结束"),
    }
    if action == "student.update":
        require_student(r)
        d = _read(s, r, "student", i)
        fields(p, "declarations")
        require(isinstance(p["declarations"], dict), "INVALID_DECLARATIONS", "Declarations must be an object.")
        d.update(deepcopy(p["declarations"]))
        d["last_declaration"] = actor
        return [put("student", i, d)]

    if action == "teacher.register":
        fields(p, "name", "template", "overlay")
        require(isinstance(p["overlay"], dict), "INVALID_OVERLAY", "Use presentation-only overlay fields.")
        require(set(p["overlay"]) <= {"tone", "pace", "language", "display_name"}, "OVERLAY_AUTHORITY", "A teacher overlay cannot modify gates or standards.")
        return [_new(s, "teacher", i, {"name": p["name"], "template": p["template"], "overlay": p["overlay"], "identity_kind": "template_role", "provenance": actor})]

    if action == "course.create":
        fields(p, "title", "course_type")
        require(p["course_type"] in ("mastery", "project", "praxis"), "COURSE_TYPE", "Unknown course type.")
        mode = p.get("learning_mode")
        require((p["course_type"] == "mastery" and mode in ("textbook", "goal", "project")) or
                (p["course_type"] != "mastery" and mode is None), "LEARNING_MODE", "Only Mastery has a learning mode.")
        actor = require_student_decision(r, decision_verbs[action])
        d = {"title": p["title"], "course_type": p["course_type"], "learning_mode": mode,
             "source_ids": [], "status": "planned", "goal": p.get("goal"), "provenance": actor}
        if p.get("teacher_id"):
            _read(s, r, "teacher", p["teacher_id"])
            d["teacher_id"] = p["teacher_id"]
        return [_new(s, "course", i, d)]

    if action in ("course.activate", "course.pause", "course.resume", "course.teacher"):
        d = _course(s, r, i)
        actor = require_student_decision(r, decision_verbs[action])
        d["last_transition_decision"] = deepcopy(actor)
        if action == "course.teacher":
            fields(p, "teacher_id")
            _read(s, r, "teacher", p["teacher_id"])
            d["teacher_id"] = p["teacher_id"]
        elif action == "course.pause":
            require(d["status"] == "ongoing", "COURSE_STATE", "Only an ongoing course can be paused.")
            require(not d.get("paused"), "COURSE_STATE", "The course is already paused.")
            d["paused"] = True
            d.setdefault("pause_history", []).append({"transition": "pause", "learning_day": learning_day(p["happened_at"]) if p.get("happened_at") else None, "decision": actor})
        elif action == "course.resume":
            require(d.get("paused") is True or d.get("status") == "paused", "COURSE_STATE", "Course is not paused.")
            require(d.get("status") in ("ongoing", "paused"), "COURSE_STATE", "A terminal course cannot be resumed by a pause flag.")
            d["paused"] = False
            d["status"] = "ongoing"
            if not d.get("pause_history"):
                d["pause_history"] = [{"transition": "pause", "learning_day": None, "source": "historical_pause_start_unknown"}]
            d["pause_history"].append({"transition": "resume", "learning_day": learning_day(p["happened_at"]) if p.get("happened_at") else None, "decision": actor})
        else:
            require(d["status"] == "planned", "COURSE_STATE", "Course must be planned.")
            if d.get("learning_mode") == "textbook":
                require(bool(d["source_ids"]), "SOURCE_REQUIRED", "Register a textbook source before activation.")
            d["status"] = "ongoing"
        return [put("course", i, d)]

    if action == "activity.create":
        fields(p, "course_id", "activity_type", "title")
        c = _course(s, r, p["course_id"])
        require(p["activity_type"] in ("lesson", "exercise", "adhoc"), "ACTIVITY_TYPE", "Unknown activity type.")
        require(i.startswith(p["course_id"] + "/"), "ACTIVITY_NAMESPACE", "Activity identity must be namespaced by course.")
        d = {"course_id": p["course_id"], "activity_type": p["activity_type"], "title": p["title"], "status": "planned"}
        require(c["status"] not in ("completed", "closed_incomplete"), "COURSE_TERMINAL", "Course is terminal.")
        return [_new(s, "activity", i, d)]

    if action in ("activity.start", "activity.route", "activity.reopen"):
        d = _activity(s, r, i)
        c = _course(s, r, d["course_id"])
        actor = require_student_decision(r, decision_verbs.get(action, ("route", "进入", "切换")))
        require(c["status"] == "ongoing" and not c.get("paused"), "COURSE_NOT_ACTIVE", "Activate or resume the course first.")
        if action != "activity.route":
            allowed = ("completed", "closed_incomplete") if action == "activity.reopen" else ("planned",)
            require(d["status"] in allowed, "ACTIVITY_STATE", "Invalid activity transition.")
            _capacity(s, d["course_id"], d["activity_type"], i)
            d["status"] = "ongoing"
            if action == "activity.reopen":
                fields(p, "reason")
                d["reopened_reason"] = p["reason"]
                d.pop("pending_close", None)
        else:
            require(d["status"] in ("ongoing", "pending_close"), "ACTIVITY_STATE", "Route only to an active activity.")
        c["current_activity_id"] = i
        return [put("activity", i, d), put("course", d["course_id"], c)]

    if action == "activity.save":
        activity = _activity(s, r, i)
        fields(p, "note_id", "body")
        cursor = get(s, "cursor", i, False)
        if cursor is not None:
            cursor = _read(s, r, "cursor", i)
        note = {"activity_id": i, "course_id": activity["course_id"], "body": p["body"],
                "pending_text": p.get("pending_text"), "saved_cursor": cursor,
                "provenance": actor, "advances_learning": False}
        return [_new(s, "study_note", p["note_id"], note)]

    if action == "checkpoint.record":
        fields(p, "activity_id", "status", "position", "evidence")
        _activity(s, r, p["activity_id"])
        require(p["status"] in ("queued", "arrived", "pending", "confirmed", "archived"), "CHECKPOINT_STATE", "Unknown checkpoint state.")
        old = get(s, "checkpoint", i, False)
        if old:
            old = _read(s, r, "checkpoint", i)
            require(old["activity_id"] == p["activity_id"], "CHECKPOINT_IDENTITY", "Checkpoint cannot change activity.")
            transitions = {"queued": {"arrived", "archived"}, "arrived": {"pending", "archived"}, "pending": {"confirmed", "archived"}, "confirmed": {"archived"}, "archived": set()}
            require(p["status"] in transitions[old["status"]], "CHECKPOINT_STATE", "Invalid checkpoint transition.")
        else:
            require(p["status"] == "queued", "CHECKPOINT_STATE", "A new checkpoint starts queued; arrival and confirmation are distinct events.")
        if p["status"] == "confirmed":
            require_student(r)
        if old and old["status"] in ("pending", "confirmed") and p["status"] == "archived":
            fields(p, "successor_ids", "reason")
        return [put("checkpoint", i, {**deepcopy(p), "provenance": actor})]

    if action == "milestone.record":
        fields(p, "course_id", "mode", "result", "verification")
        c = _course(s, r, p["course_id"])
        require(c["course_type"] == "project", "COURSE_SEMANTICS", "External milestone is a Project judgment.")
        require(p["mode"] in ("A", "B", "B-K"), "VERIFICATION_MODE", "Unknown verification mode.")
        require(p["result"] in ("pass", "fail", "environment_failure"), "VERIFICATION_RESULT", "Unknown result.")
        fields(p["verification"], "procedure", "artifact", "independent_check", "failure_ladder")
        _evidence(p)
        return [_new(s, "milestone", i, {**deepcopy(p), "provenance": actor})]

    if action == "praxis.record":
        fields(p, "course_id", "action_taken", "feedback", "uncertainty", "governance_source")
        c = _course(s, r, p["course_id"])
        require(c["course_type"] == "praxis", "COURSE_SEMANTICS", "Real-world action belongs to a Praxis course.")
        _evidence(p)
        return [_new(s, "praxis", i, {**deepcopy(p), "provenance": actor})]

    if action == "completion.record":
        fields(p, "course_id", "judgment_kind", "evidence_ids")
        c = _course(s, r, p["course_id"])
        require_student(r)
        expected_kind = {"mastery": "comprehension", "project": "external_milestone", "praxis": "action_feedback"}[c["course_type"]]
        require(p["judgment_kind"] == expected_kind, "COURSE_SEMANTICS", "Completion judge cannot be substituted across course types.")
        require(bool(p["evidence_ids"]), "EVIDENCE_REQUIRED", "Completion needs evidence.")
        evidence_kind = {"mastery": "checkpoint", "project": "milestone", "praxis": "praxis"}[c["course_type"]]
        for evidence_id in p["evidence_ids"]:
            e = _read(s, r, evidence_kind, evidence_id)
            if evidence_kind == "checkpoint":
                require(e["status"] == "confirmed", "UNCONFIRMED_EVIDENCE", "Checkpoint must be confirmed.")
                a = _activity(s, r, e["activity_id"])
                require(a["course_id"] == p["course_id"], "CROSS_COURSE_EVIDENCE", "Completion evidence belongs to another course.")
            else:
                require(e["course_id"] == p["course_id"], "CROSS_COURSE_EVIDENCE", "Completion evidence belongs to another course.")
                if evidence_kind == "milestone":
                    require(e["result"] == "pass", "MILESTONE_NOT_PASSED", "Environment failure is not a pass.")
        return [_new(s, "completion", i, {**deepcopy(p), "provenance": actor})]

    if action == "activity.close.propose":
        d = _activity(s, r, i)
        fields(p, "body", "outcome", "presentation_ref", "reconciliation")
        require(d["status"] in ("ongoing", "pending_close"), "ACTIVITY_STATE", "Activity is not open.")
        require(p["outcome"] in ("completed", "closed_incomplete"), "CLOSE_OUTCOME", "Specify the actual outcome.")
        require(isinstance(p["body"], str) and p["body"].strip(), "EMPTY_REVIEW", "Present the full review.")
        for qid, q in _all(s, "question"):
            require(not (q.get("activity_id") == i and question_status(s, qid) not in ("closed", "merged") and p["outcome"] == "completed"), "OPEN_QUESTIONS", "Resolve or explicitly close incomplete with open questions retained.")
        if d["activity_type"] == "exercise":
            require(p["reconciliation"].get("order") == "source_order", "EXERCISE_ORDER", "Exercise review must reconcile source order.")
        if p["outcome"] == "completed":
            if d["activity_type"] == "exercise":
                exercise = _read(s, r, "exercise", i)
                problem_ids = {x for x in exercise.get("source_order", [])}
                if not problem_ids:
                    problem_ids = {pid for pid, problem in _all(s, "problem") if problem.get("activity_id") == i}
                reviewed = set()
                for rid, review in _all(s, "review"):
                    attempt_id = review.get("attempt_id")
                    attempt = get(s, "attempt", attempt_id, False) if attempt_id else None
                    if attempt and attempt.get("activity_id") == i:
                        _read(s, r, "attempt", attempt_id)
                        _read(s, r, "review", rid)
                        reviewed.update(x.get("problem_id") for x in review.get("ratings", []))
                require(bool(problem_ids) and problem_ids <= reviewed, "UNREVIEWED_PROBLEMS", "Every source problem needs an actual review before completed.")
            else:
                blocks = [(bid, b) for bid, b in _all(s, "block") if b.get("activity_id") == i]
                if blocks:
                    for bid, b in blocks:
                        _read(s, r, "block", bid)
                        require(b.get("coverage") in ("covered", "explicitly_deferred", "outside_active_lesson_boundary"), "UNCOVERED_BLOCK", "Reconcile every teaching block before completed.")
                else:
                    fields(p["reconciliation"], "checkpoint_ids")
                    require(bool(p["reconciliation"]["checkpoint_ids"]), "COMPLETION_EVIDENCE", "A completed activity needs actual learning evidence.")
                    for checkpoint_id in p["reconciliation"]["checkpoint_ids"]:
                        checkpoint = _read(s, r, "checkpoint", checkpoint_id)
                        require(checkpoint["activity_id"] == i and checkpoint["status"] == "confirmed", "COMPLETION_EVIDENCE", "Completion references a confirmed checkpoint of this activity.")
        proposal = {"activity_id": i, "activity_type": d["activity_type"], "body": p["body"], "outcome": p["outcome"],
                    "presentation_ref": p["presentation_ref"], "reconciliation": p["reconciliation"]}
        d.update(status="pending_close", pending_close=proposal, pending_sha256=digest(proposal))
        return [put("activity", i, d)]

    if action in ("activity.close.confirm", "activity.close.withdraw"):
        d = _activity(s, r, i)
        require(d["status"] == "pending_close", "NO_PENDING_CLOSE", "There is no pending close.")
        require_student(r)
        _bound(p, d["pending_close"])
        proposal = d.pop("pending_close")
        d.pop("pending_sha256", None)
        if action.endswith("withdraw"):
            d["status"] = "ongoing"
            return [put("activity", i, d)]
        fields(p, "outcome")
        require(p["outcome"] == proposal["outcome"], "OUTCOME_MISMATCH", "Confirm the exact proposed result.")
        actor = _close_intent(r, proposal["outcome"])
        if proposal["outcome"] == "completed":
            # Re-evaluate completion constraints under the same writer lock: new
            # questions or blocks since presentation cannot bypass closing gates.
            plan(s, {**r, "action": "activity.close.propose", "payload": {"id": i, **proposal}})
        d["status"] = proposal["outcome"]
        d["last_close_id"] = r["request_id"]
        return [put("activity", i, d), _new(s, "close", r["request_id"], {"proposal": proposal, "decision": actor})]

    if action == "course.close.propose":
        d = _course(s, r, i)
        fields(p, "body", "outcome", "presentation_ref", "completion_ids")
        require(d["status"] == "ongoing", "COURSE_STATE", "Only an ongoing course can propose closure.")
        require(p["outcome"] in ("completed", "closed_incomplete"), "CLOSE_OUTCOME", "Specify the course outcome.")
        if p["outcome"] == "completed":
            require(bool(p["completion_ids"]), "COMPLETION_EVIDENCE", "Course completion needs type-specific completion nodes.")
            for cid in p["completion_ids"]:
                node = _read(s, r, "completion", cid)
                require(node["course_id"] == i, "CROSS_COURSE_EVIDENCE", "Completion node belongs to another course.")
            require(not any(a.get("course_id") == i and a.get("status") in ("ongoing", "pending_close") for _, a in _all(s, "activity")), "OPEN_ACTIVITIES", "Conclude ongoing activities before completing the course.")
        proposal = {"course_id": i, "body": p["body"], "outcome": p["outcome"], "presentation_ref": p["presentation_ref"], "completion_ids": p["completion_ids"]}
        d.update(pending_close=proposal, pending_sha256=digest(proposal))
        return [put("course", i, d)]

    if action in ("course.close.confirm", "course.close.withdraw"):
        d = _course(s, r, i)
        require_student(r)
        require(bool(d.get("pending_close")), "NO_PENDING_CLOSE", "There is no course close proposal.")
        _bound(p, d["pending_close"])
        proposal = d.pop("pending_close")
        d.pop("pending_sha256", None)
        if action.endswith("withdraw"):
            return [put("course", i, d)]
        fields(p, "outcome")
        require(p["outcome"] == proposal["outcome"], "OUTCOME_MISMATCH", "Confirm the exact course outcome.")
        actor = _close_intent(r, proposal["outcome"], course=True)
        if proposal["outcome"] == "completed":
            require(not any(a.get("course_id") == i and a.get("status") in ("ongoing", "pending_close") for _, a in _all(s, "activity")), "OPEN_ACTIVITIES", "An activity advanced after this proposal.")
        d["status"] = proposal["outcome"]
        return [put("course", i, d), _new(s, "course_close", r["request_id"], {"proposal": proposal, "decision": actor})]

    if action == "time.record":
        fields(p, "activity_id", "quality")
        _activity(s, r, p["activity_id"])
        require(p["quality"] in ("exact", "estimated", "unknown"), "TIME_QUALITY", "Specify time quality.")
        if p["quality"] != "unknown":
            fields(p, "seconds", "started_at")
            require(isinstance(p["seconds"], (float, int)) and not isinstance(p["seconds"], bool) and p["seconds"] >= 0, "DURATION", "Duration must be nonnegative.")
            day = learning_day(p["started_at"])
        else:
            require(p.get("seconds") is None, "UNKNOWN_DURATION", "Unknown duration has no numeric seconds.")
            day = None
        if p.get("corrects"):
            old = _read(s, r, "timespan", p["corrects"])
            require(old["activity_id"] == p["activity_id"], "SPAN_IDENTITY", "Correction must remain in its activity.")
            require(not any(span.get("corrects") == p["corrects"] for _, span in _all(s, "timespan")), "SPAN_ALREADY_CORRECTED", "Correct the latest replacement, not an already replaced historical span.")
        if p.get("session_id"):
            session = _read(s, r, "session", p["session_id"])
            require(session["activity_id"] == p["activity_id"], "SPAN_SESSION", "Session time must belong to this activity.")
        return [_new(s, "timespan", i, {**deepcopy(p), "learning_day": day, "provenance": actor})]

    if action in ("reading.create", "engagement.create"):
        fields(p, "intent")
        if action == "reading.create":
            require(p.get("kind", "reading") == "reading", "READING_KIND", "Only reading is a current ActivityRecord kind.")
            used = [int(m.group(1)) for a, _ in _all(s, "reading") if (m := re.fullmatch(r"AR-?(\d+)", a))]
            number = max(used, default=0) + 1
            require(i in {f"AR{number:04d}", f"AR-{number:04d}"}, "READING_SEQUENCE", "ActivityRecord IDs are monotonic across legacy and current spellings.")
            return [_new(s, "reading", i, {"intent": p["intent"], "resources": p.get("resources", []), "status": "recording", "kind": "reading", "provenance": actor})]
        fields(p, "governance", "governance_source")
        require(p["governance"] in ("external", "internal"), "ENGAGEMENT_GOVERNANCE", "Identify the actual governance owner.")
        return [_new(s, "engagement", i, {**deepcopy(p), "status": "ongoing", "provenance": actor})]

    if action in ("reading.transition", "engagement.record"):
        kind = action.split(".")[0]
        d = _read(s, r, kind, i)
        if kind == "engagement":
            fields(p, "annotation")
            _evidence(p)
            d.setdefault("annotations", []).append({"text": p["annotation"], "evidence": p["evidence"], "provenance": actor})
        else:
            fields(p, "status")
            allowed = {"recording": {"paused", "archived", "upgraded"}, "paused": {"recording", "archived", "upgraded"}, "archived": set(), "upgraded": set()}
            require(p["status"] in allowed[d["status"]], "READING_STATE", "Invalid reading transition.")
            require_student(r)
            if p["status"] == "upgraded":
                fields(p, "course_id", "scope")
                _course(s, r, p["course_id"])
                d.update(course_id=p["course_id"], scope=p["scope"])
            d["status"] = p["status"]
        return [put(kind, i, d)]

    if action == "engagement.entry.record":
        fields(p, "engagement_id", "entry_kind", "body")
        engagement = _read(s, r, "engagement", p["engagement_id"])
        require(engagement["governance"] == "internal", "EXTERNAL_FACT_OWNERSHIP", "Externally governed facts can only be indexed or annotated here.")
        _evidence(p)
        return [_new(s, "engagement_entry", i, {**deepcopy(p), "provenance": actor})]

    if action == "group.propose":
        fields(p, "members", "capacity", "calendar", "thresholds", "goal")
        require(isinstance(p["members"], list) and len(set(p["members"])) == len(p["members"]), "GROUP_MEMBERS", "Members must be a unique list.")
        require(isinstance(p["capacity"], int) and len(p["members"]) <= p["capacity"], "GROUP_CAPACITY", "Too many group members.")
        for member in p["members"]:
            _course(s, r, member)
        fields(p["calendar"], "frequency", "stagnation_days")
        fields(p["thresholds"], "close_condition")
        return [_new(s, "group", i, {**deepcopy(p), "status": "planned", "proposal_sha256": digest(p), "provenance": actor})]

    if action in ("group.activate", "group.close"):
        d = _read(s, r, "group", i)
        actor = require_student_decision(r, decision_verbs[action])
        if action == "group.activate" or not d.get("closure_conditions"):
            fields(p, "proposal_sha256")
            require(p["proposal_sha256"] == d["proposal_sha256"], "GROUP_PROPOSAL_CHANGED", "Confirm the current complete group proposal.")
        if action.endswith("activate"):
            require(d["status"] == "planned", "GROUP_STATE", "Group is not planned.")
            require(not any(g.get("status") == "active" for gid, g in _all(s, "group") if gid != i), "ACTIVE_GROUP_EXISTS", "Close the current active group before activating another.")
            for member in d["members"]:
                c = _course(s, r, member)
                require(c["status"] == "ongoing", "GROUP_MEMBER_STATE", "Activate each planned course first.")
            d["status"] = "active"
        else:
            require(d["status"] == "active", "GROUP_STATE", "Only an active group can close.")
            _evidence(p)
            fields(p, "assessment_id")
            report = _read(s, r, "group_assessment", p["assessment_id"])
            require(report["group_id"] == i, "GROUP_THRESHOLD", "Assessment belongs to another group.")
            from .groups import validate_close
            validate_close(s, r, d, report)
            d.update(status="closed", close_evidence=p["evidence"], decision=actor)
            if d.get("requires_next_group_choice"):
                d["next_group_choice"] = deepcopy(p["next_group_choice"])
        return [put("group", i, d)]

    if action == "binding.create":
        fields(p, "course_ids", "intent")
        for course_id in p["course_ids"]:
            _course(s, r, course_id)
        return [_new(s, "binding", i, {**deepcopy(p), "status": "active", "budget_weight": 0})]

    if action == "binding.retire":
        d = _read(s, r, "binding", i)
        require_student(r)
        require(d["status"] == "active", "BINDING_STATE", "Binding is not active.")
        d["status"] = "retired"
        return [put("binding", i, d)]

    if action == "binding.record":
        d = _read(s, r, "binding", i)
        require(d["status"] == "active", "BINDING_STATE", "Record execution only for an active binding.")
        fields(p, "observation", "evidence_refs")
        refs = []
        for ref in p["evidence_refs"]:
            require(ref.get("kind") in {"attempt", "review", "checkpoint", "completion", "praxis", "study_note"},
                    "BINDING_EVIDENCE", "Binding evidence refers to actual course work, not another binding.")
            evidence = _read(s, r, ref["kind"], ref["id"])
            if ref["kind"] == "review":
                evidence = _read(s, r, "attempt", evidence["attempt_id"])
            course_id = evidence.get("course_id")
            if not course_id and evidence.get("activity_id"):
                course_id = _activity(s, r, evidence["activity_id"])["course_id"]
            require(course_id in d["course_ids"], "BINDING_EVIDENCE", "Evidence must belong to one of the linked courses.")
            refs.append({"kind": ref["kind"], "id": ref["id"], "version": version(s, ref["kind"], ref["id"])})
        d.setdefault("observations", []).append({"request_id": r["request_id"], "observation": p["observation"],
            "evidence_refs": refs, "provenance": actor, "mastery_or_budget_credit": False})
        return [put("binding", i, d)]

    if action == "group.review":
        fields(p, "group_id", "frequency_observation", "progress_observation", "judgment")
        _read(s, r, "group", p["group_id"])
        _evidence(p)
        return [_new(s, "group_review", i, {**deepcopy(p), "provenance": actor})]

    if action == "group.schedule.configure":
        d = _read(s, r, "group", i)
        fields(p, "calendar", "reason")
        allowed = {"cycle_anchor_learning_day", "cycle_length_learning_days", "cycle_count", "keystone_dwell_budget_cycles", "exam_keystones_per_quiz", "exam_keystones_per_bank_build", "exam_bank_build_cycles", "exam_quiz_cycles", "exam_final_cycle"}
        proposed = p["calendar"]
        require(isinstance(proposed, dict) and bool(proposed) and set(proposed) <= allowed, "CALENDAR_FIELDS", "Use the agreed canonical calendar fields; missing values stay unknown.")
        basis = p.get("basis", "student_decision")
        if basis == "source_evidence":
            original = d.get("calendar", {}).get("legacy_fields", {})
            require(d.get("legacy") and original and p.get("source_calendar_sha256") == digest(original)
                    and all(name in original and value == original[name] for name, value in proposed.items()),
                    "CALENDAR_SOURCE_EVIDENCE", "A mechanical mapping must copy the frozen original calendar values exactly.")
        else:
            require(basis == "student_decision", "CALENDAR_BASIS", "Use a current decision or exact preserved calendar values.")
            require_student(r)
        for name, value in proposed.items():
            if value is None or value == "TBD":
                continue
            if name == "cycle_anchor_learning_day":
                require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, "CALENDAR_ANCHOR", "Use an explicit ISO learning date.")
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError as error:
                    raise DomainError("CALENDAR_ANCHOR", "Invalid calendar date.") from error
            elif name in ("exam_bank_build_cycles", "exam_quiz_cycles"):
                require(isinstance(value, list) and len(set(value)) == len(value) and all(type(x) is int and x > 0 for x in value), "EXAM_CYCLES", "Use explicitly agreed, distinct positive cycle numbers; an empty list means no such examinations.")
            else:
                require(type(value) is int and value > 0, "CALENDAR_PARAMETER", "An agreed count must be positive; TBD is allowed when not decided.")
        require(not any(x.get("group_id") == i and x.get("status") in ("open", "submitted", "flagged") for _, x in _all(s, "exam")), "OPEN_EXAM", "Settle the active examination before changing its calendar.")
        old = deepcopy(d.get("calendar", {}))
        if d.get("status") == "active":
            require(all(old.get(k) in (None, "TBD") or old[k] == v for k, v in proposed.items()), "GROUP_CALENDAR_FROZEN", "An active group's agreed time and scope anchors cannot silently move.")
        d.setdefault("calendar_history", []).append({"previous": old, "decision": actor, "reason": p["reason"],
                                                     "basis": basis, "source_calendar_sha256": p.get("source_calendar_sha256")})
        d["calendar"] = {**old, **deepcopy(proposed)}
        return [put("group", i, d)]

    if action == "group.keystones.configure":
        d = _read(s, r, "group", i)
        require_student(r)
        fields(p, "container_mode", "keystone_ids", "reason")
        require(p["container_mode"] in ("schedule", "progress"), "CONTAINER_MODE", "Choose schedule or progress semantics.")
        require(isinstance(p["keystone_ids"], list) and p["keystone_ids"] and len(set(p["keystone_ids"])) == len(p["keystone_ids"]), "KEYSTONE_IDS", "Use a nonempty unique milestone sequence.")
        old = d.get("keystone_ids", [])
        require(not d.get("container_mode") or d.get("container_mode") == p["container_mode"] or d.get("status") == "planned", "CONTAINER_MODE_FROZEN", "An active group retains its agreed time/scope container.")
        if old:
            require(set(old) <= set(p["keystone_ids"]), "KEYSTONE_SCOPE_SHRINK", "Do not silently shrink a frozen milestone sequence; record a separate reviewed plan change.")
        d.setdefault("keystone_change_log", [])
        if old:
            d["keystone_change_log"].append({"old": old, "new": p["keystone_ids"], "delta": len(p["keystone_ids"]) - len(old), "reason": p["reason"], "decision": actor})
            d["keystone_total_frozen"] = d.get("keystone_total_frozen", len(old)) + len(p["keystone_ids"]) - len(old)
        else:
            d["keystone_total_frozen"] = len(p["keystone_ids"])
            d["keystone_total_initial"] = len(p["keystone_ids"])
        d.update(container_mode=p["container_mode"], keystone_ids=p["keystone_ids"])
        if "keystone_courses" in p:
            mapping = p["keystone_courses"]
            require(isinstance(mapping, dict) and set(mapping) <= set(p["keystone_ids"]) and set(mapping.values()) <= set(d["members"]), "KEYSTONE_COURSES", "Milestone owners must be actual group members.")
            d["keystone_courses"] = deepcopy(mapping)
        if "keystone_bindings" in p:
            bindings = p["keystone_bindings"]
            require(isinstance(bindings, dict) and set(bindings) <= set(p["keystone_ids"]), "KEYSTONE_BINDINGS", "Bindings must name declared milestones.")
            for milestone_id, refs in bindings.items():
                require(isinstance(refs, list) and bool(refs), "KEYSTONE_BINDINGS", "An explicit mapping needs actual evidence identities.")
                for ref in refs:
                    require(isinstance(ref, dict) and set(ref) == {"kind", "id"} and ref["kind"] in {"checkpoint", "milestone", "praxis"}, "KEYSTONE_BINDINGS", "Map domain evidence, not arbitrary text labels.")
                    item = _read(s, r, ref["kind"], ref["id"])
                    cid = _activity(s, r, item["activity_id"])["course_id"] if ref["kind"] == "checkpoint" else item["course_id"]
                    require(cid in d["members"], "GROUP_EVIDENCE", "Mapped evidence must belong to a member course.")
            previous = d.get("keystone_bindings", {})
            require(all(bindings.get(k, v) == v for k, v in previous.items() if k in d.get("completed_keystone_ids", [])), "KEYSTONE_BINDING_FROZEN", "Completed milestone mappings cannot be rewritten.")
            d["keystone_bindings"] = {**previous, **deepcopy(bindings)}
        d.setdefault("completed_keystone_ids", [])
        return [put("group", i, d)]

    if action == "group.keystone.complete":
        d = _read(s, r, "group", i)
        fields(p, "keystone_id", "completion_id")
        require(p["keystone_id"] in d.get("keystone_ids", []) and p["keystone_id"] not in d.get("completed_keystone_ids", []), "KEYSTONE_SEQUENCE", "Complete an existing, unfinished group milestone.")
        completion = _read(s, r, "completion", p["completion_id"])
        require(completion["course_id"] in d["members"], "GROUP_EVIDENCE", "Milestone evidence must belong to a member course.")
        evidence_kind = {"comprehension": "checkpoint", "external_milestone": "milestone", "action_feedback": "praxis"}.get(completion.get("judgment_kind"))
        require(evidence_kind is not None and bool(completion.get("evidence_ids")), "GROUP_EVIDENCE", "Completion needs its domain evidence.")
        named = set(completion["evidence_ids"])
        bindings = d.get("keystone_bindings", {}).get(p["keystone_id"])
        if bindings:
            require(all(ref["kind"] == evidence_kind and ref["id"] in named for ref in bindings), "KEYSTONE_EVIDENCE", "Completion does not cover the student-confirmed milestone mapping.")
        else:
            evidence = [_read(s, r, evidence_kind, eid) for eid in named]
            require(any(eid == p["keystone_id"] or e.get("position") == p["keystone_id"] or e.get("keystone_id") == p["keystone_id"] for eid, e in zip(named, evidence)), "KEYSTONE_EVIDENCE", "This completion has no evidence for the named milestone; an unrelated completion cannot advance it.")
        d["completed_keystone_ids"].append(p["keystone_id"])
        d.setdefault("keystone_evidence", {})[p["keystone_id"]] = p["completion_id"]
        return [put("group", i, d)]

    if action == "suggestion.propose":
        fields(p, "body", "owner", "scope")
        require(p["owner"] in ("student", "teacher"), "SUGGESTION_OWNER", "Identify the suggestion's author.")
        return [_new(s, "suggestion", i, {**deepcopy(p), "status": "proposed", "provenance": actor})]

    if action == "suggestion.decide":
        d = _read(s, r, "suggestion", i)
        require_student(r)
        fields(p, "status")
        require(d["status"] != "retired" and p["status"] in ("deferred", "adopted", "retired", "proposed"), "SUGGESTION_STATE", "Invalid suggestion transition.")
        if p["status"] == "adopted":
            fields(p, "implementation_kind", "implementation_id")
            _read(s, r, p["implementation_kind"], p["implementation_id"])
            d["implementation_ref"] = {"kind": p["implementation_kind"], "id": p["implementation_id"]}
        d.update(status=p["status"], decision=actor)
        return [put("suggestion", i, d)]

    if action in ("thought.record", "reflection.record", "pattern.record", "keystone.record"):
        kind = action.split(".")[0]
        fields(p, "body")
        require(bool(p.get("course_id")) != bool(p.get("reading_id")), "METHOD_SCOPE",
                "Record this result in one course or reading activity.")
        if p.get("reading_id"):
            reading = _read(s, r, "reading", p["reading_id"])
            require(reading.get("status") in ("recording", "paused", "upgraded"), "READING_STATE",
                    "An archived reading activity cannot receive new learning content.")
        else:
            _course(s, r, p["course_id"])
        _evidence(p)
        _contributions(s, r, p)
        if kind == "thought":
            require_student(r, p["body"])
        if kind == "pattern":
            fields(p, "counterevidence", "testable_prediction")
            require(p.get("status", "hypothesis") == "hypothesis", "PATTERN_CERTAINTY", "A newly proposed pattern remains a hypothesis.")
        if kind == "keystone":
            fields(p, "claim", "reasons", "dependencies", "review_status")
            require("private_persuasion" not in p, "PRIVATE_MATERIAL", "Private persuasion content is excluded.")
            if p.get("course_id"):
                require(len([1 for _, e in _all(s, "keystone") if e.get("course_id") == p["course_id"]]) < 3, "KEYSTONE_CAPACITY", "A course has at most three keystone nodes.")
        record = {**deepcopy(p), "provenance": actor}
        if kind == "keystone":
            record["confirmation_status"] = "draft"
            record["chain_sha256"] = digest(p.get("steps", p["reasons"]))
        return [_new(s, kind, i, record)]

    if action == "keystone.confirm":
        node = _read(s, r, "keystone", i)
        actor = require_student_decision(r, ("confirm", "accept", "确认", "认可"))
        fields(p, "chain_sha256", "steps")
        chain = node.get("steps", node["reasons"])
        require(isinstance(chain, list) and chain, "KEYSTONE_CHAIN_PENDING", "First organize the actual reasoning into numbered steps.")
        require(p["chain_sha256"] == digest(chain), "KEYSTONE_CHAIN_CHANGED", "Confirm the current displayed reasoning chain.")
        confirmations = p["steps"]
        require(isinstance(confirmations, list) and len(confirmations) == len(chain)
                and {x.get("step") for x in confirmations} == set(range(1, len(chain) + 1))
                and all(isinstance(x.get("statement"), str) and x["statement"].strip() for x in confirmations),
                "KEYSTONE_STEP_CONFIRMATION", "Retain the student's actual confirmation for each numbered step.")
        node.update(confirmation_status="student_confirmed", chain_sha256=p["chain_sha256"],
                    step_confirmations=deepcopy(confirmations), confirmation=actor)
        return [put("keystone", i, node)]

    if action == "method.consume":
        fields(p, "method_kind", "method_id", "activity_id", "effect")
        require(p["method_kind"] in ("reflection", "pattern", "keystone"), "METHOD_KIND", "Unknown method source.")
        method = _read(s, r, p["method_kind"], p["method_id"])
        if p["method_kind"] == "keystone":
            require(method.get("confirmation_status") == "student_confirmed", "KEYSTONE_NOT_CONFIRMED", "A draft is not yet the student's confirmed reasoning path.")
        _activity(s, r, p["activity_id"])
        _evidence(p)
        return [_new(s, "method_use", i, {**deepcopy(p), "provenance": actor})]

    if action == "issue.open":
        fields(p, "problem", "root_cause", "scope")
        require(not any(d.get("root_cause") == p["root_cause"] for _, d in _all(s, "issue")), "ISSUE_ALREADY_EXISTS", "Record recurrence against the existing issue identity.")
        return [_new(s, "issue", i, {**deepcopy(p), "status": "open", "occurrences": [{"provenance": actor, "evidence": p.get("evidence", [])}]})]

    if action in ("issue.recur", "issue.resolve"):
        d = _read(s, r, "issue", i)
        _evidence(p)
        if action.endswith("recur"):
            d["status"] = "open"
            d["occurrences"].append({"provenance": actor, "evidence": p["evidence"]})
        else:
            fields(p, "resolution", "enforcement", "verification")
            require(p["enforcement"] in ("check", "tool", "context", "prose", "not_applicable"), "ENFORCEMENT", "Unknown enforcement type.")
            d.update(status="resolved", resolution=p["resolution"], enforcement=p["enforcement"], verification=p["verification"], evidence=p["evidence"])
        return [put("issue", i, d)]

    if action == "rule.register":
        fields(p, "body", "owner", "failure_signal", "enforcement", "consumer")
        require(p["enforcement"] in ("check", "tool", "context", "prose"), "ENFORCEMENT", "Unknown rule enforcement.")
        require(not any(d.get("owner") == p["owner"] and d.get("body") == p["body"] for _, d in _all(s, "rule")), "RULE_DUPLICATE", "A rule has one canonical owner.")
        if p["enforcement"] in ("check", "tool"):
            fields(p, "negative_evidence", "implementation_ref")
        return [_new(s, "rule", i, {**deepcopy(p), "status": "active", "provenance": actor})]

    if action in ("rule.retire", "rule.use"):
        d = _read(s, r, "rule", i)
        if action.endswith("retire"):
            fields(p, "semantic_disposition", "replacement_ids", "consumer_evidence")
            for replacement in p["replacement_ids"]:
                _read(s, r, "rule", replacement)
            d.update(status="retired", disposition=deepcopy(p))
        else:
            fields(p, "use_ref")
            d.setdefault("uses", [])
            require(p["use_ref"] not in d["uses"], "DUPLICATE_USE", "A use cannot be counted twice.")
            d["uses"].append(p["use_ref"])
        return [put("rule", i, d)]

    if action == "history.record":
        fields(p, "category", "body", "implementation_status", "review_status", "release_status")
        require(p["category"] in ("adr", "evolution", "changelog", "journal"), "HISTORY_CATEGORY", "Unknown history category.")
        for ref in p.get("references", []):
            _read(s, r, "history", ref)
        return [_new(s, "history", i, {**deepcopy(p), "provenance": actor})]

    if action in ("registry.alias", "registry.retire"):
        fields(p, "kind", "target_id")
        d = _read(s, r, p["kind"], p["target_id"])
        if action.endswith("alias"):
            require(get(s, p["kind"], i, False) is None, "ALIAS_SHADOW", "Alias cannot shadow an actual identity.")
            return [_new(s, "alias", f"{p['kind']}/{i}", {"kind": p["kind"], "target_id": p["target_id"]})]
        fields(p, "reason", "successor_ids")
        for target in p["successor_ids"]:
            require(target != p["target_id"], "SELF_SUCCESSOR", "A successor must have a different identity.")
            _read(s, r, p["kind"], target)
        d.update(retired=True, retirement=deepcopy(p))
        return [put(p["kind"], p["target_id"], d)]

    if action == "handoff.create":
        fields(p, "lane", "scope", "body", "source_versions", "completion_condition")
        require(p["lane"] in ("teach", "maintain", "audit", "release"), "LANE", "Unknown lane.")
        for object_key, v in p["source_versions"].items():
            entity = s["objects"].get(object_key)
            require(entity and entity["version"] == v, "HANDOFF_STALE", "Handoff source has changed.")
        return [_new(s, "handoff", i, {**deepcopy(p), "status": "active", "provenance": actor})]

    if action == "handoff.resolve":
        d = _read(s, r, "handoff", i)
        fields(p, "condition_evidence")
        d.update(status="resolved", condition_evidence=p["condition_evidence"])
        return [put("handoff", i, d)]

    if action == "skin.register":
        fields(p, "title", "art", "welcome")
        require(isinstance(p["art"], str) and isinstance(p["welcome"], str), "SKIN_TEXT", "Skin content is plain display text.")
        require(set(p) <= {"id", "title", "art", "welcome", "license", "private"}, "SKIN_INSTRUCTIONS", "Skin has no instruction or executable fields.")
        return [_new(s, "skin", i, deepcopy(p))]

    if action == "skin.select":
        _read(s, r, "skin", i)
        require_student(r)
        d = _read(s, r, "student", "current")
        d["skin_id"] = i
        return [put("student", "current", d)]

    if action == "external.register":
        fields(p, "identity", "mode", "contract", "content_sha256")
        require(p["mode"] in ("frozen", "copy_on_use"), "REFERENCE_MODE", "External source needs a reference policy.")
        return [_new(s, "external", i, {**deepcopy(p), "provenance": actor})]

    if action == "external.consume":
        fields(p, "reference_id", "body", "observed_sha256", "used_at")
        d = _read(s, r, "external", p["reference_id"])
        actual = hashlib.sha256(p["body"].encode()).hexdigest()
        require(actual == p["observed_sha256"], "CONTENT_HASH", "Observed content hash does not match bytes.")
        require(d["mode"] != "frozen" or actual == d["content_sha256"], "EXTERNAL_DRIFT", "Frozen external source changed; explicit rebind is required.")
        return [_new(s, "external_use", i, {**deepcopy(p), "identity": d["identity"], "provenance": actor})]

    if action == "campaign.create":
        fields(p, "scope", "token_limit", "repair_limit")
        require(isinstance(p["token_limit"], int) and p["token_limit"] > 0 and isinstance(p["repair_limit"], int) and p["repair_limit"] >= 0, "BUDGET", "Use explicit valid budgets.")
        return [_new(s, "campaign", i, {**deepcopy(p), "tokens": 0, "repairs": 0, "status": "active"})]

    if action == "campaign.observe":
        d = _read(s, r, "campaign", i)
        fields(p, "tokens", "repairs", "measurement_source")
        require(p["tokens"] >= d["tokens"] and p["repairs"] >= d["repairs"], "BUDGET_COUNTER", "Counters cannot be reset to escape a limit.")
        d.update(tokens=p["tokens"], repairs=p["repairs"], measurement_source=p["measurement_source"])
        if d["tokens"] >= d["token_limit"] or d["repairs"] > d["repair_limit"]:
            d["status"] = "stopped_budget"
        return [put("campaign", i, d)]

    raise DomainError("UNKNOWN_ACTION", f"Unknown support action: {action}")


ACTIONS = {
    "student.update", "teacher.register", "course.create", "course.activate", "course.pause", "course.resume", "course.teacher",
    "activity.create", "activity.start", "activity.route", "activity.reopen", "activity.save", "checkpoint.record", "milestone.record", "praxis.record", "completion.record",
    "activity.close.propose", "activity.close.confirm", "activity.close.withdraw", "time.record",
    "course.close.propose", "course.close.confirm", "course.close.withdraw",
    "reading.create", "reading.transition", "engagement.create", "engagement.record", "group.propose", "group.activate", "group.close", "group.review",
    "engagement.entry.record",
    "binding.create", "binding.retire", "binding.record", "suggestion.propose", "suggestion.decide", "thought.record", "reflection.record", "pattern.record", "keystone.record", "keystone.confirm", "method.consume",
    "group.keystones.configure", "group.keystone.complete", "group.schedule.configure",
    "issue.open", "issue.recur", "issue.resolve", "rule.register", "rule.retire", "rule.use", "history.record", "registry.alias", "registry.retire",
    "handoff.create", "handoff.resolve", "skin.register", "skin.select", "external.register", "external.consume", "campaign.create", "campaign.observe",
}
