"""Learning decisions as pure, version-checked plans.

Evidence and actors are attributed assertions, not host authentication. A scan
records a complete, identity-checked delivery receipt; this module cannot observe
the model's eyes or prevent an arbitrary host from sending unrecorded prose.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import math
import random

from .model import DomainError, fields, get, key, put, require, require_student, require_student_decision, version

LEGACY_CYCLE_BASELINE_VERSION = 1

IMMUTABLE_KINDS = frozenset({"source", "page", "scope", "lessonmap", "preparation", "scan", "criterion", "attempt", "review", "exam_selection", "ocr_raw", "ocr_correction", "ocr_verification"})
ENTITY_CONTRACTS = {
    "source": "immutable {course_ids,title,format,content_sha256,source_version,blob_sha256? or content}",
    "page": "immutable {source_id,pdf_page_index,printed_page_label,verified_text,verified_text_sha256,layout_critical,render_blob_sha256?,blob_refs}",
    "scope": "immutable {activity_id,source_id,page_ids,current_page_id}",
    "lessonmap": "immutable {activity_id,scope_id,block_ids,page_ids}",
    "preparation": "immutable {activity_id,scope_id,lessonmap_id,receipts}",
    "scan": "immutable {session_id,scope_id,deliveries,evidence_level}",
    "session": "{activity_id,course_id,status,readiness,scope_id?,preparation_id?,scan_id?}",
    "block": "{activity_id,teacher_title,source_role,source_refs,body,body_sha256,status,responses,judgments,feelings}",
    "ticket": "{purpose,session_id,activity_id,block_id?,body_sha256?,problem_id?,level?,status,decision}",
    "cursor": "activity ID; {block_id,position,waiting_for,pending_body,next_action,judgement?,evidence_refs}",
    "criterion": "immutable {target_kind,target_id,problem_ids,rubric,max_scores,pass_score?}",
    "exercise": "activity ID; {activity_id,course_id,problems,source_order,supplemental_ids,teaching_sequence,assistance,attempt_ids,review_ids}",
    "attempt": "immutable {activity_id,exam_id?,answers,student,assistance,hint_gate}",
    "review": "immutable {attempt_id,criterion_id,ratings,teacher,supersedes?}",
    "exam_bank": "{course_id,papers,problems,batches,exposures,used_papers,status}; original and official solution source IDs, frozen source/pool metadata",
    "exam_selection": "immutable {bank_id,group_id?,exam_type,cycle,seed,problem_ids,rejected,duration_minutes,scope_snapshot}",
    "exam": "{bank_id,selection_id,activity_id,problem_ids,criterion_id,status,attempt_id?,self_assessment?,flags,reminders,settlement?}",
    "page_head": "source_id/pdf_page_index; {source_id,pdf_page_index,page_id}; current verified page revision",
    "learning_structure": "course ID; {course_id,segments:[{segment_id,title,checkpoint_ids,knowledge_keys}],student_confirmation,plan_reference?}",
    "learning_segment": "course/segment ID; frozen named structure and confirmed checkpoints with completed_at",
    "aged_window": "{course_id,status:candidate|reminder|no_window,completed_segment_ids,eligible_mistake_ids,related_segment_id,used_by?}",
    "aged_calendar": "course ID; {reminded_windows,last_sheet_segment_ids?,last_sheet_at?}; dates do not replace named learning segments",
    "aged_review": "{activity_id,variant_ids,mistake_ids,proposal,status:proposed|authorized,duration_minutes,window_id?}",
    "retest_plan": "{session_ids,course_id,slots,status:pending|paused|complete,results,pending_slots?}; result consumes actual review identity",
    "variant": "{mistake_id,activity_id,problem_id,probe,body,self_solution,judgment_basis,safety,admitted_use:daily|informal_quiz}",
    "exam_reinforcement": "exam ID; {course_id,status:planned|active|complete,required_learning_dates:3,activity_ids?,learning_dates,records}",
}


def digest(value):
    raw = value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _text(value, name):
    require(isinstance(value, str) and bool(value.strip()), "INVALID_TEXT", f"Nonempty text required: {name}")
    return value


def _list(value, name, nonempty=True):
    require(isinstance(value, list) and (not nonempty or bool(value)), "INVALID_LIST", f"A list is required: {name}")
    return value


def _number(value, name, minimum=0):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= minimum, "INVALID_NUMBER", f"Invalid {name}")


def _read(state, request, kind, ident, required=True):
    data = get(state, kind, ident, required=required)
    if data is not None:
        require(not data.get("migration_requires_reconciliation"), "MIGRATION_RECONCILIATION_REQUIRED", f"Resolve the preserved legacy uncertainties before changing {key(kind, ident)}.")
    if data is not None and kind not in IMMUTABLE_KINDS:
        require(request.get("expected", {}).get(key(kind, ident)) == version(state, kind, ident), "STALE_OBJECT", f"Expected current version of {key(kind, ident)}")
    return data


def _new(state, kind, ident):
    key(kind, ident)
    require(get(state, kind, ident, required=False) is None, "ID_EXISTS", f"Identity cannot be reused: {key(kind, ident)}")


def _teacher(request):
    actor = request.get("actor", {})
    require(isinstance(actor, dict) and actor.get("role") in {"teacher", "system"}, "TEACHER_REQUIRED", "An attributed teacher judgment is required.")
    fields(actor, "source", "text")
    _text(actor["text"], "actor.text")
    return deepcopy(actor)


def _student_choice(request, verbs):
    """The caller interprets the actual input into the named domain action.

    Retain that attribution; these phrases only identify limited explicit
    contradictions, not an acceptance vocabulary or general intent classifier.
    """
    return require_student_decision(request, verbs, error_code="UNBOUND_DECISION")


def _course_activity(state, request, ident):
    activity = _read(state, request, "activity", ident)
    fields(activity, "course_id", "activity_type", "status")
    course = _read(state, request, "course", activity["course_id"])
    return activity, course


def _textbook(course, activity):
    return course.get("course_type") == "mastery" and course.get("learning_mode") == "textbook" and activity.get("activity_type") == "lesson"


def _cursor(state, request, activity_id):
    return _read(state, request, "cursor", activity_id, required=False) or {"block_id": None, "position": "start", "waiting_for": "authorization", "pending_body": None, "next_action": "select_block", "evidence_refs": []}


def _context(state, request, session_id, ready=True):
    session = _read(state, request, "session", session_id)
    require(session.get("status") == "active", "SESSION_CLOSED", "A current active session is required.")
    activity, course = _course_activity(state, request, session["activity_id"])
    require(course.get("status") == "ongoing" and not course.get("paused") and not course.get("retired"), "COURSE_NOT_ONGOING", "Resume an ongoing course explicitly before teaching.")
    require(activity.get("status") == "ongoing", "ACTIVITY_NOT_ONGOING", "The activity must be ongoing.")
    if ready:
        require(session.get("readiness") == "ready", "SOURCE_SCAN_REQUIRED", "Current-session source delivery is incomplete.")
        if _textbook(course, activity):
            require(activity.get("scope_id") == session.get("scope_id") and activity.get("preparation_id") == session.get("preparation_id"), "SOURCE_CHANGED", "Preparation or Scope changed after session start.")
            scan = get(state, "scan", session.get("scan_id", "missing"))
            require(scan["session_id"] == session_id and scan["scope_id"] == session["scope_id"], "SCAN_SESSION_MISMATCH", "Historical scans cannot authorize this session.")
            for page_id in get(state, "scope", session["scope_id"])["page_ids"]:
                _page_current(state, request, page_id)
    return session, activity, course


def _objects(state, kind):
    return [(v["id"], deepcopy(v["data"])) for v in state.get("objects", {}).values() if v.get("kind") == kind]


def _unclosed_questions(state, activity_id):
    return [(i, q) for i, q in _objects(state, "question") if q.get("activity_id") == activity_id and q.get("status") not in {"closed", "merged"}]


def _source_register(state, request, p):
    fields(p, "source_id", "title", "format", "source_version", "content_sha256")
    _teacher(request); _new(state, "source", p["source_id"])
    require(_sha(p["content_sha256"]), "INVALID_SHA", "Source content SHA-256 is required.")
    require(p["format"] in {"pdf", "epub", "text", "url", "artifact"}, "INVALID_SOURCE_FORMAT", "Unsupported source format.")
    courses = p.get("course_ids", [p.get("course_id")])
    _list(courses, "course_ids")
    require(all(isinstance(x, str) and x for x in courses) and len(courses) == len(set(courses)), "INVALID_COURSES", "Distinct course identities are required.")
    if "content" in p:
        _text(p["content"], "content")
        require(digest(p["content"]) == p["content_sha256"], "SOURCE_HASH_MISMATCH", "Text does not match the declared source hash.")
    else:
        require(p.get("blob_sha256") == p["content_sha256"], "SOURCE_BLOB_REQUIRED", "An immutable source blob or complete text is required.")
    if p["format"] == "pdf":
        require(type(p.get("page_count")) is int and p["page_count"] > 0, "INVALID_PAGE_COUNT", "A PDF needs its physical page count.")
    data = {k: deepcopy(v) for k, v in p.items() if k not in {"source_id", "course_id"}}
    data.update(course_ids=courses, registered_by=deepcopy(request["actor"]))
    effects = [put("source", p["source_id"], data)]
    for cid in courses:
        course = _read(state, request, "course", cid)
        course["source_ids"] = list(dict.fromkeys(course.get("source_ids", []) + [p["source_id"]]))
        effects.append(put("course", cid, course))
    return effects


def _page_register(state, request, p):
    fields(p, "page_id", "source_id", "pdf_page_index", "printed_page_label", "verified_text", "verification")
    _teacher(request); _new(state, "page", p["page_id"])
    source = get(state, "source", p["source_id"])
    require(type(p["pdf_page_index"]) is int and 1 <= p["pdf_page_index"] <= source.get("page_count", 0), "PAGE_OUT_OF_RANGE", "Physical page is outside the source.")
    head_id = f"{p['source_id']}/{p['pdf_page_index']}"
    head = _read(state, request, "page_head", head_id, False)
    previous = [(i, x) for i, x in _objects(state, "page") if x.get("source_id") == p["source_id"] and x.get("pdf_page_index") == p["pdf_page_index"]]
    if previous:
        fields(p, "supersedes_page_id", "correction_reason")
        current = head["page_id"] if head else previous[-1][0]
        require(p["supersedes_page_id"] == current, "PAGE_REVISION_CHANGED", "A correction must name the current immutable page revision.")
        _text(p["correction_reason"], "correction reason")
    else:
        require(not p.get("supersedes_page_id"), "PAGE_PREDECESSOR", "A first page has no predecessor.")
    verification = p["verification"]
    require(isinstance(verification, dict), "INVALID_VERIFICATION", "Verification must identify its evidence.")
    fields(verification, "status", "reference", "source_document_sha256")
    require(verification["status"] == "verified" and verification["source_document_sha256"] == source["content_sha256"], "UNVERIFIED_PAGE", "Page must be verified against this immutable source version.")
    _text(p["verified_text"], "verified_text")
    require("layout_critical" not in p or type(p["layout_critical"]) is bool, "INVALID_LAYOUT_FLAG", "A layout flag is a boolean, never a string or number.")
    data = {k: deepcopy(v) for k, v in p.items() if k != "page_id"}
    data["verified_text_sha256"] = digest(p["verified_text"])
    if "verified_text_sha256" in p:
        require(p["verified_text_sha256"] == data["verified_text_sha256"], "TEXT_HASH_MISMATCH", "Verified text hash differs.")
    render = p.get("render_blob_sha256")
    if render:
        require(_sha(render), "INVALID_SHA", "Invalid render blob hash.")
        fields(p, "render_profile", "pixel_width", "pixel_height", "media_box_points", "ppi", "render_bytes")
        require(type(p["render_bytes"]) is int and p["render_bytes"] >= 0, "INVALID_BLOB_REFERENCE", "Render byte length is required.")
        require(isinstance(p["media_box_points"], list) and len(p["media_box_points"]) == 2, "INVALID_MEDIA_BOX", "MediaBox width and height are required.")
        for val in [p["pixel_width"], p["pixel_height"], p["ppi"], *p["media_box_points"]]: _number(val, "render geometry", 1)
        require(200 <= p["ppi"] <= 600, "PPI_RANGE", "A canonical teaching page requires 200–600 PPI; 300 is the default profile.")
        require(all(abs(px-round(pt/72*p["ppi"])) <= 1 for px, pt in zip([p["pixel_width"], p["pixel_height"]], p["media_box_points"])), "PPI_MISMATCH", "Pixels do not establish the claimed rendering density.")
        data["blob_refs"] = [{"sha256": render, "bytes": p["render_bytes"]}]
    return [put("page", p["page_id"], data), put("page_head", head_id, {"page_id": p["page_id"], "source_id": p["source_id"], "pdf_page_index": p["pdf_page_index"]})]


def _page_current(state, request, page_id):
    page = get(state, "page", page_id)
    require(not page.get("migration_requires_reconciliation"), "MIGRATION_RECONCILIATION_REQUIRED", "This legacy page has unresolved source or text evidence.")
    source = get(state, "source", page["source_id"])
    require(not source.get("migration_requires_reconciliation"), "MIGRATION_RECONCILIATION_REQUIRED", "Reconcile the source identity before using its pages.")
    require(page.get("verification", {}).get("status") == "verified" and page["verification"].get("source_document_sha256") == source.get("content_sha256"), "UNVERIFIED_PAGE", "Only a source-bound verified page may be prepared or taught.")
    require(digest(page.get("verified_text", "")) == page.get("verified_text_sha256"), "TEXT_HASH_MISMATCH", "Verified page text no longer matches its immutable hash.")
    head = _read(state, request, "page_head", f"{page['source_id']}/{page['pdf_page_index']}", False)
    require(head is not None and head["page_id"] == page_id, "PAGE_SUPERSEDED", "A verified current page head is required; reconcile or prepare the corrected revision.")
    return page


def validate_current_page(state, page_id):
    """Read-only snapshot validation shared with recovery/readiness consumers."""
    page = get(state, "page", page_id)
    head_id = f"{page['source_id']}/{page['pdf_page_index']}"
    return _page_current(state, {"expected": {key("page_head", head_id): version(state, "page_head", head_id)}}, page_id)


def _ocr(state, request, p, action):
    teacher = _teacher(request)
    if action == "ocr.capture":
        fields(p, "ocr_id", "source_id", "pdf_page_index", "raw_text", "tool", "reference")
        _new(state, "ocr_raw", p["ocr_id"]); source = get(state, "source", p["source_id"])
        require(type(p["pdf_page_index"]) is int and 1 <= p["pdf_page_index"] <= source.get("page_count", 0), "PAGE_OUT_OF_RANGE", "OCR input names a physical source page.")
        require(isinstance(p["raw_text"], str), "INVALID_TEXT", "Preserve OCR output including an empty failed extraction.")
        data = {k: deepcopy(v) for k, v in p.items() if k != "ocr_id"}
        data.update(source_document_sha256=source["content_sha256"], raw_text_sha256=digest(p["raw_text"]), status="unverified", actor=teacher)
        return [put("ocr_raw", p["ocr_id"], data)]
    if action == "ocr.correct":
        fields(p, "correction_id", "ocr_id", "text", "changes", "unresolved")
        _new(state, "ocr_correction", p["correction_id"]); raw = get(state, "ocr_raw", p["ocr_id"])
        _text(p["text"], "corrected text"); _list(p["changes"], "changes", False); _list(p["unresolved"], "unresolved", False)
        if p.get("previous_correction_id"):
            old = get(state, "ocr_correction", p["previous_correction_id"])
            require(old["ocr_id"] == p["ocr_id"], "OCR_CHAIN", "Corrections retain their original raw OCR and page identity.")
        return [put("ocr_correction", p["correction_id"], {**deepcopy(p), "text_sha256": digest(p["text"]), "source_id": raw["source_id"], "pdf_page_index": raw["pdf_page_index"], "status": "unverified", "actor": teacher})]
    if action == "ocr.verify":
        fields(p, "verification_id", "correction_id", "visual_reference", "source_document_sha256", "line_by_line", "key_symbols_checked")
        _new(state, "ocr_verification", p["verification_id"]); corrected = get(state, "ocr_correction", p["correction_id"])
        source = get(state, "source", corrected["source_id"])
        require(not corrected["unresolved"] and p["line_by_line"] is True and p["key_symbols_checked"] is True, "OCR_UNRESOLVED", "Resolve uncertainty and compare lines and key symbols against the original visual source before verification.")
        require(p["source_document_sha256"] == source["content_sha256"], "SOURCE_HASH_MISMATCH", "Verification is bound to the original source bytes.")
        _text(p["visual_reference"], "original visual reference")
        return [put("ocr_verification", p["verification_id"], {**deepcopy(p), "text_sha256": corrected["text_sha256"], "status": "verified", "actor": teacher, "evidence_level": "attributed_visual_comparison"})]
    fields(p, "page_id", "verification_id", "printed_page_label")
    verified = get(state, "ocr_verification", p["verification_id"]); corrected = get(state, "ocr_correction", verified["correction_id"])
    page = {k: deepcopy(v) for k, v in p.items() if k != "verification_id"}
    page.update(source_id=corrected["source_id"], pdf_page_index=corrected["pdf_page_index"], verified_text=corrected["text"], ocr_id=corrected["ocr_id"], correction_id=verified["correction_id"], ocr_verification_id=p["verification_id"], verification={"status": "verified", "reference": verified["visual_reference"], "source_document_sha256": verified["source_document_sha256"]})
    return _page_register(state, request, page)


def _scope_create(state, request, p):
    fields(p, "scope_id", "activity_id", "source_id", "page_ids", "current_page_id")
    _teacher(request); _new(state, "scope", p["scope_id"])
    activity, course = _course_activity(state, request, p["activity_id"])
    source = get(state, "source", p["source_id"])
    require(activity["course_id"] in source["course_ids"], "SOURCE_COURSE_MISMATCH", "Source does not belong to this course.")
    pages = _list(p["page_ids"], "page_ids")
    require(len(pages) == len(set(pages)) and p["current_page_id"] in pages, "INVALID_SCOPE", "Scope must contain distinct pages and its current page.")
    assets = [_page_current(state, request, i) for i in pages]
    require(all(a["source_id"] == p["source_id"] for a in assets), "SOURCE_IDENTITY_MISMATCH", "Mixed source versions in Scope.")
    indices = [a["pdf_page_index"] for a in assets]
    require(indices == list(range(indices[0], indices[0]+len(indices))), "NONCONTIGUOUS_SCOPE", "Scope must be physically ordered and continuous.")
    total = source["page_count"]
    require(type(total) is int and total > 0, "SOURCE_PENDING", "Resolve the source's physical page count before preparing a scope.")
    require((total < 5 and indices == list(range(1, total+1))) or (total >= 5 and 5 <= len(pages) <= 8), "SCOPE_SIZE", "Scope is five to eight pages, or all pages of a short source.")
    return [put("scope", p["scope_id"], {k: deepcopy(p[k]) for k in ("activity_id", "source_id", "page_ids", "current_page_id")})]


def _block_create(state, request, p):
    fields(p, "block_id", "activity_id", "teacher_title", "source_role", "body")
    opt_in = _student_choice(request, {"请加练", "加练", "我想加练", "request supplement", "extra practice"}) if p["source_role"] == "teacher_generated" else None
    if opt_in is None: _teacher(request)
    _new(state, "block", p["block_id"])
    activity, course = _course_activity(state, request, p["activity_id"])
    _text(p["teacher_title"], "teacher_title"); _text(p["body"], "body")
    require(p["source_role"] in {"definition", "theorem", "proof", "example", "exercise", "explanation", "summary", "background", "teacher_generated"}, "INVALID_SOURCE_ROLE", "Source role is separate from the teacher's chosen title.")
    refs = p.get("source_refs", [])
    _list(refs, "source_refs", nonempty=_textbook(course, activity) and opt_in is None)
    for ref in refs:
        fields(ref, "page_id", "source_excerpt", "locator")
        page = _page_current(state, request, ref["page_id"])
        source = get(state, "source", page["source_id"])
        require(source.get("purpose") not in {"exam_paper", "exam_solution"}, "ASSESSMENT_ISOLATION", "Examination sources do not enter teaching blocks; admitted practice questions use the exercise bank route.")
        require(activity["course_id"] in source["course_ids"], "SOURCE_COURSE_MISMATCH", "Block uses a different course's source.")
        _text(ref["source_excerpt"], "source_excerpt")
        require(ref["source_excerpt"] in page["verified_text"], "EXCERPT_MISMATCH", "The source excerpt must occur verbatim in the verified page text.")
    data = {"activity_id": p["activity_id"], "teacher_title": p["teacher_title"], "source_role": p["source_role"], "source_refs": deepcopy(refs), "body": p["body"], "body_sha256": digest(p["body"]), "status": "planned", "responses": [], "judgments": [], "feelings": [], "coverage": "uncovered"}
    if opt_in is not None: data["opt_in"] = opt_in
    return [put("block", p["block_id"], data)]


def _map_create(state, request, p):
    fields(p, "lessonmap_id", "activity_id", "scope_id", "block_ids")
    _teacher(request); _new(state, "lessonmap", p["lessonmap_id"])
    scope = get(state, "scope", p["scope_id"])
    require(scope["activity_id"] == p["activity_id"], "SCOPE_ACTIVITY_MISMATCH", "Scope belongs to another activity.")
    ids = _list(p["block_ids"], "block_ids")
    require(len(ids) == len(set(ids)), "DUPLICATE_BLOCK", "Map blocks must be distinct.")
    pages = set()
    for bid in ids:
        block = _read(state, request, "block", bid)
        require(block["activity_id"] == p["activity_id"], "BLOCK_ACTIVITY_MISMATCH", "Map includes another activity's block.")
        pages.update(r["page_id"] for r in block["source_refs"])
    require(pages == set(scope["page_ids"]), "MAP_COVERAGE", "LessonMap must cover exactly the whole Scope.")
    return [put("lessonmap", p["lessonmap_id"], {"activity_id": p["activity_id"], "scope_id": p["scope_id"], "block_ids": deepcopy(ids), "page_ids": deepcopy(scope["page_ids"])})]


def _prepare(state, request, p):
    fields(p, "preparation_id", "activity_id", "scope_id", "lessonmap_id", "receipts")
    _teacher(request); _new(state, "preparation", p["preparation_id"])
    activity, course = _course_activity(state, request, p["activity_id"])
    scope = get(state, "scope", p["scope_id"]); lm = get(state, "lessonmap", p["lessonmap_id"])
    require(scope["activity_id"] == lm["activity_id"] == p["activity_id"] and lm["scope_id"] == p["scope_id"], "PREPARATION_IDENTITY", "Scope, map and activity must match.")
    receipts = _list(p["receipts"], "receipts")
    require(len(receipts) == len(scope["page_ids"]) and {r.get("page_id") for r in receipts} == set(scope["page_ids"]), "RECEIPT_COVERAGE", "One preparation receipt is required for every Scope page.")
    for receipt in receipts:
        fields(receipt, "page_id", "reference", "verified_text_sha256", "source_document_sha256")
        page = _page_current(state, request, receipt["page_id"]); source = get(state, "source", page["source_id"])
        require(receipt["verified_text_sha256"] == page["verified_text_sha256"] and receipt["source_document_sha256"] == source["content_sha256"], "RECEIPT_IDENTITY", "Receipt hashes do not bind the canonical content.")
    old_scope = activity.get("scope_id")
    if old_scope and old_scope != p["scope_id"]:
        old_prep = get(state, "preparation", activity["preparation_id"])
        old_map = get(state, "lessonmap", old_prep["lessonmap_id"])
        for bid in set(old_map["block_ids"]) - set(lm["block_ids"]):
            block = _read(state, request, "block", bid)
            require(block.get("coverage") in {"covered", "explicitly_deferred", "outside_active_lesson_boundary"}, "UNCLOSED_SCOPE_BLOCK", "An unfinished block cannot silently leave Scope.")
    data = {k: deepcopy(p[k]) for k in ("activity_id", "scope_id", "lessonmap_id", "receipts")}
    data["prepared_by"] = deepcopy(request["actor"])
    activity.update(scope_id=p["scope_id"], preparation_id=p["preparation_id"])
    return [put("preparation", p["preparation_id"], data), put("activity", p["activity_id"], activity)]


def _session_start(state, request, p):
    fields(p, "session_id", "activity_id")
    _new(state, "session", p["session_id"])
    activity, course = _course_activity(state, request, p["activity_id"])
    require(course.get("status") == "ongoing" and not course.get("paused") and not course.get("retired"), "COURSE_NOT_ONGOING", "Resume the course explicitly before starting teaching.")
    require(activity["status"] == "ongoing", "ACTIVITY_NOT_ONGOING", "Start the activity before starting a session.")
    require(not any(s.get("activity_id") == p["activity_id"] and s.get("status") == "active" for _, s in _objects(state, "session")), "ACTIVE_SESSION", "Close the previous session before starting a fresh one.")
    data = {"activity_id": p["activity_id"], "course_id": activity["course_id"], "status": "active", "readiness": "ready", "opening_presented": False}
    if _textbook(course, activity):
        fields(activity, "preparation_id", "scope_id")
        prep = get(state, "preparation", activity["preparation_id"])
        require(prep["scope_id"] == activity["scope_id"] and prep["activity_id"] == p["activity_id"], "PREPARATION_IDENTITY", "The current preparation does not match this activity.")
        data.update(readiness="source_pending", preparation_id=activity["preparation_id"], scope_id=activity["scope_id"])
    cursor = _cursor(state, request, p["activity_id"])
    cursor["next_action"] = "present_opening" if not activity.get("opening_confirmed") else cursor.get("next_action", "select_block")
    return [put("session", p["session_id"], data), put("cursor", p["activity_id"], cursor)]


def _scan_record(state, request, p):
    fields(p, "scan_id", "session_id", "scope_id", "deliveries")
    _teacher(request); _new(state, "scan", p["scan_id"])
    session, activity, course = _context(state, request, p["session_id"], ready=False)
    require(session.get("scope_id") == activity.get("scope_id") == p["scope_id"], "SCAN_SCOPE_MISMATCH", "This delivery must bind the current session's Scope.")
    scope = get(state, "scope", p["scope_id"])
    deliveries = _list(p["deliveries"], "deliveries")
    consumed_sources = {}
    require({x.get("page_id") for x in deliveries} == set(scope["page_ids"]), "SCAN_COVERAGE", "Delivery must cover the complete Scope, without extra pages.")
    for delivery in deliveries:
        fields(delivery, "page_id", "form", "host_reference", "session_id", "source_document_sha256", "printed_page_label")
        require(delivery["session_id"] == p["session_id"], "SCAN_SESSION_MISMATCH", "A delivery from a previous conversation is not current evidence.")
        page = _page_current(state, request, delivery["page_id"]); source = get(state, "source", page["source_id"])
        if source.get("blob_sha256"):
            consumed_sources[page["source_id"]] = {"source_id": page["source_id"], "blob_sha256": source["blob_sha256"]}
        require(delivery["source_document_sha256"] == source["content_sha256"] and str(delivery["printed_page_label"]) == str(page["printed_page_label"]), "SCAN_IDENTITY", "Source version or printed page label differs.")
        if delivery["form"] == "verified_text":
            require(page.get("layout_critical") is False, "RENDER_REQUIRED", "Layout critical or unknown pages require full-page rendering.")
            require(delivery.get("content") == page["verified_text"], "SCAN_CONTENT", "Metadata or a summary is not the whole verified page body.")
        elif delivery["form"] == "render_png":
            require(page.get("render_blob_sha256") and delivery.get("blob_sha256") == page["render_blob_sha256"], "SCAN_RENDER", "The delivered image must match the complete page render.")
            require(delivery.get("whole_page") is True, "SCAN_CONTENT", "A crop is not a whole-page delivery.")
        elif delivery["form"] == "pdf_direct":
            require(delivery.get("whole_page") is True, "SCAN_CONTENT", "A direct PDF delivery must show the whole page.")
        else:
            raise DomainError("SCAN_FORM", "Unrecognized source-delivery form.")
    data = {k: deepcopy(p[k]) for k in ("session_id", "scope_id", "deliveries")}
    data["consumed_sources"] = list(consumed_sources.values())
    data.update(evidence_level="attributed_host_delivery", duplicate_page_count=len(deliveries)-len(scope["page_ids"]), pdf_direct_is_weaker_proxy=any(x["form"] == "pdf_direct" for x in deliveries))
    session.update(readiness="ready", scan_id=p["scan_id"])
    return [put("scan", p["scan_id"], data), put("session", p["session_id"], session)]


def _opening(state, request, p):
    fields(p, "session_id", "overview", "knowledge_tree")
    _teacher(request); session, activity, course = _context(state, request, p["session_id"])
    _text(p["overview"], "overview"); _text(p["knowledge_tree"], "knowledge_tree")
    session.update(opening_presented=True, opening={"overview": p["overview"], "knowledge_tree": p["knowledge_tree"]})
    return [put("session", p["session_id"], session)]


def _ticket_issue(state, request, p):
    fields(p, "ticket_id", "session_id", "block_id", "body_sha256")
    decision = require_student_decision(request, ("continue", "enter", "present", "继续", "进入", "呈现", "重讲"), error_code="UNBOUND_DECISION")
    require(decision["text"].strip().casefold().rstrip("。.!！ ") not in {"stop", "pause", "停止", "暂停"}, "UNBOUND_DECISION", "An explicit stop does not authorize a next block.")
    _new(state, "ticket", p["ticket_id"])
    session, activity, course = _context(state, request, p["session_id"])
    require(activity.get("opening_confirmed") or session.get("opening_presented"), "OPENING_REQUIRED", "The lesson route must be shown before entering its first block.")
    block = _read(state, request, "block", p["block_id"])
    require(block["activity_id"] == session["activity_id"] and block["status"] == "planned", "BLOCK_NOT_AVAILABLE", "Permission must name one new block of this activity.")
    require(p["body_sha256"] == block["body_sha256"], "BODY_CHANGED", "Permission binds the exact body offered for the next block.")
    cursor = _cursor(state, request, session["activity_id"])
    require(cursor.get("waiting_for") in {"authorization", "ready", "start"}, "PREVIOUS_GATE_OPEN", "Comprehension, feelings and questions must close before the next block.")
    require(not _unclosed_questions(state, session["activity_id"]), "QUESTIONS_OPEN", "Unclosed questions cannot be hidden by moving to another block.")
    require(not any(x.get("session_id") == p["session_id"] and x.get("purpose") == "next_block" and x.get("status") == "issued" for _, x in _objects(state, "ticket")), "TICKET_ALREADY_ISSUED", "Only one unconsumed next-block permission is allowed.")
    if _textbook(course, activity):
        prep = get(state, "preparation", session["preparation_id"]); lm = get(state, "lessonmap", prep["lessonmap_id"])
        require(p["block_id"] in lm["block_ids"], "BLOCK_OUTSIDE_SCOPE", "Block is outside the prepared map.")
    ticket = {"purpose": "next_block", "session_id": p["session_id"], "activity_id": session["activity_id"], "block_id": p["block_id"], "body_sha256": p["body_sha256"], "status": "issued", "decision": decision}
    return [put("ticket", p["ticket_id"], ticket)]


def _block_present(state, request, p):
    fields(p, "session_id", "ticket_id", "block_id", "body_sha256")
    _teacher(request); session, activity, course = _context(state, request, p["session_id"])
    ticket = _read(state, request, "ticket", p["ticket_id"]); block = _read(state, request, "block", p["block_id"])
    require(ticket.get("purpose") == "next_block" and ticket.get("status") == "issued", "TICKET_SPENT", "An unused next-block ticket is required.")
    require(ticket["session_id"] == p["session_id"] and ticket["block_id"] == p["block_id"] and ticket["activity_id"] == session["activity_id"], "TICKET_SCOPE", "Permission does not cover this session and block.")
    require(ticket["body_sha256"] == block["body_sha256"] == p["body_sha256"], "BODY_CHANGED", "Block body differs from the authorized body.")
    require(block["status"] == "planned", "BLOCK_ALREADY_PRESENTED", "This block has already been introduced.")
    cursor = _cursor(state, request, session["activity_id"])
    require(cursor.get("waiting_for") in {"authorization", "ready", "start"} and not _unclosed_questions(state, session["activity_id"]), "PREVIOUS_GATE_OPEN", "An earlier gate is still open.")
    previous = cursor.get("block_id")
    if previous:
        old = _read(state, request, "block", previous)
        old_pages = {x["page_id"] for x in old["source_refs"]}; new_pages = {x["page_id"] for x in block["source_refs"]}
        if new_pages != old_pages and _textbook(course, activity):
            fields(p, "page_turn")
            turn = p["page_turn"]
            fields(turn, "announced_page_id", "classroom_tree", "previous_page_coverage")
            require(turn["announced_page_id"] in new_pages, "PAGE_TURN_IDENTITY", "Announce the actual new page before its body.")
            _text(turn["classroom_tree"], "classroom_tree")
            for bid, candidate in _objects(state, "block"):
                if candidate.get("activity_id") == session["activity_id"] and old_pages.intersection(x["page_id"] for x in candidate.get("source_refs", [])):
                    candidate = _read(state, request, "block", bid)
                    require(candidate.get("coverage") in {"covered", "explicitly_deferred", "outside_active_lesson_boundary"}, "PAGE_COVERAGE_OPEN", "The previous page contains an unaccounted block.")
                    require(turn["previous_page_coverage"].get(bid) == candidate["coverage"], "PAGE_COVERAGE_MISMATCH", "The displayed coverage must match recorded coverage.")
    ticket.update(status="consumed", consumed_by=request.get("request_id"))
    block.update(status="presented", presented_in=p["session_id"])
    activity["opening_confirmed"] = True
    cursor.update(block_id=p["block_id"], position=block["teacher_title"], waiting_for="comprehension", pending_body=None, next_action="student_response", body_sha256=block["body_sha256"])
    return [put("ticket", p["ticket_id"], ticket), put("block", p["block_id"], block), put("cursor", session["activity_id"], cursor), put("activity", session["activity_id"], activity)]


def _current_block(state, request, p):
    session, activity, course = _context(state, request, p["session_id"])
    cursor = _cursor(state, request, session["activity_id"])
    require(cursor.get("block_id") == p["block_id"], "NOT_CURRENT_BLOCK", "Only the current block can receive this interaction.")
    block = _read(state, request, "block", p["block_id"])
    require(block["activity_id"] == session["activity_id"], "BLOCK_ACTIVITY_MISMATCH", "Block belongs to another activity.")
    return session, activity, course, cursor, block


def _comprehension_submit(state, request, p):
    fields(p, "session_id", "block_id", "response_id", "answer")
    student = require_student(request)
    session, activity, course, cursor, block = _current_block(state, request, p)
    require(cursor["waiting_for"] == "comprehension", "WRONG_GATE", "This block is not waiting for a comprehension answer.")
    _text(p["answer"], "answer")
    require(student["text"] == p["answer"], "ANSWER_ATTRIBUTION", "Preserve the student's actual submitted words.")
    require(not any(x["response_id"] == p["response_id"] for x in block["responses"]), "RESPONSE_EXISTS", "A response identity cannot be reused.")
    fields(block, "criterion_id")
    get(state, "criterion", block["criterion_id"])
    block["responses"].append({"response_id": p["response_id"], "answer": p["answer"], "student": student, "criterion_id": block["criterion_id"], "blob_refs": deepcopy(p.get("blob_refs", []))})
    return [put("block", p["block_id"], block)]


def _criterion_create(state, request, p):
    fields(p, "criterion_id", "target_kind", "target_id", "rubric")
    _teacher(request); _new(state, "criterion", p["criterion_id"])
    require(p["target_kind"] in {"block", "exercise", "exam_bank", "course"}, "INVALID_CRITERION_TARGET", "Criterion targets a block, exercise, exam bank or course process assessment.")
    target = _read(state, request, p["target_kind"], p["target_id"])
    _text(p["rubric"], "rubric")
    data = {k: deepcopy(v) for k, v in p.items() if k != "criterion_id"}
    data["created_by"] = deepcopy(request["actor"])
    if p["target_kind"] == "block":
        require(target.get("status") == "planned", "CRITERION_TOO_LATE", "Freeze a comprehension criterion before presenting the block.")
    if p["target_kind"] in {"exercise", "exam_bank"}:
        ids = _list(p.get("problem_ids"), "problem_ids")
        require(len(ids) == len(set(ids)) and set(ids) <= set(target["problems"]), "CRITERION_PROBLEMS", "Criterion must bind existing problems in one exercise.")
        scores = p.get("max_scores")
        require(isinstance(scores, dict) and set(scores) == set(ids), "CRITERION_SCORES", "One maximum score is required per problem.")
        for val in scores.values(): _number(val, "maximum score", 0)
        if "pass_score" in p:
            _number(p["pass_score"], "pass score")
            require(p["pass_score"] <= sum(scores.values()), "INVALID_PASS_SCORE", "Pass score exceeds the rubric maximum.")
    if p["target_kind"] == "exam_bank":
        require(not any(e.get("bank_id") == p["target_id"] and e.get("status") in {"open", "submitted", "flagged"} for _, e in _objects(state, "exam")), "CRITERION_TOO_LATE", "Official scoring points must be frozen before the examination starts.")
        points = _list(p.get("scoring_points"), "scoring_points")
        require(len({x["point_id"] for x in points}) == len(points), "POINT_IDENTITIES", "Every scoring point needs a unique identity.")
        totals = {pid: 0 for pid in ids}
        for point in points:
            fields(point, "point_id", "problem_id", "max_score", "page_id", "source_excerpt", "locator")
            require(point["problem_id"] in totals, "POINT_PROBLEM", "Scoring points must belong to the bound bank problems.")
            _number(point["max_score"], "point maximum", 0.000001)
            problem = target["problems"][point["problem_id"]]
            paper = target["papers"][problem["paper_id"]]
            page = _page_current(state, request, point["page_id"])
            require(page["source_id"] == paper.get("solution_source_id") and bool(point["source_excerpt"]) and point["source_excerpt"] in page["verified_text"], "OFFICIAL_SCORING_SOURCE", "Each scoring point must cite verified official solution text.")
            totals[point["problem_id"]] += point["max_score"]
        require(totals == scores, "POINT_TOTAL", "Problem maxima must equal their frozen official scoring point totals.")
    if p["target_kind"] == "course":
        require(p.get("purpose") == "exam_process", "CRITERION_PURPOSE", "A course criterion here is the independently frozen process-assessment rubric.")
        ids = _list(p.get("metric_ids"), "metric_ids")
        require(len(ids) == len(set(ids)) and isinstance(p.get("max_scores"), dict) and set(p["max_scores"]) == set(ids), "CRITERION_SCORES", "Freeze one maximum per process metric.")
        for score in p["max_scores"].values(): _number(score, "process metric maximum", .000001)
        require(not any(e.get("course_id") == p["target_id"] and e.get("status") in {"open", "submitted", "flagged"} for _, e in _objects(state, "exam")), "CRITERION_TOO_LATE", "Freeze process grading before opening the examination.")
        target["process_criterion_id"] = p["criterion_id"]
    else: target["criterion_id"] = p["criterion_id"]
    return [put("criterion", p["criterion_id"], data), put(p["target_kind"], p["target_id"], target)]


def _comprehension_record(state, request, p):
    fields(p, "session_id", "block_id", "response_id", "criterion_id", "verdict", "rationale")
    teacher = _teacher(request)
    session, activity, course, cursor, block = _current_block(state, request, p)
    require(cursor["waiting_for"] == "comprehension", "WRONG_GATE", "Comprehension is not pending.")
    criterion = get(state, "criterion", p["criterion_id"])
    require(criterion["target_kind"] == "block" and criterion["target_id"] == p["block_id"], "CRITERION_TARGET", "The criterion does not judge this block.")
    response = next((r for r in block["responses"] if r["response_id"] == p["response_id"]), None)
    require(response is not None, "RESPONSE_MISSING", "A judgment must point to an actual student answer.")
    require(response.get("criterion_id") == p["criterion_id"], "CRITERION_CHANGED", "Judge the answer under its frozen criterion, not a later rubric.")
    require(not any(j["response_id"] == p["response_id"] for j in block["judgments"]), "ALREADY_JUDGED", "Do not silently regrade a historical answer.")
    require(p["verdict"] in {"correct", "incorrect", "uncertain"}, "INVALID_VERDICT", "Unsupported comprehension judgment.")
    _text(p["rationale"], "rationale")
    judgment = {k: deepcopy(p[k]) for k in ("response_id", "criterion_id", "verdict", "rationale")}
    judgment["teacher"] = teacher
    block["judgments"].append(judgment)
    if p["verdict"] == "correct":
        block.update(status="understood", coverage="covered")
        cursor.update(waiting_for="feeling", next_action="ask_feeling")
    else:
        cursor.update(waiting_for="comprehension", next_action="address_response")
    cursor["judgement"] = deepcopy(judgment)
    cursor.setdefault("evidence_refs", []).append({"kind": "block_response", "block_id": p["block_id"], "response_id": p["response_id"]})
    return [put("block", p["block_id"], block), put("cursor", session["activity_id"], cursor)]


def _comprehension_assess(state, request, p):
    """One atomic answer+judgment plan; both attributions remain explicit."""
    _teacher(request)
    fields(p, "student", "answer", "response_id", "criterion_id", "verdict", "rationale")
    require(isinstance(p["student"], dict), "STUDENT_DECISION_REQUIRED", "Preserve the actual attributed student response.")
    submitted = _comprehension_submit(state, {**request, "actor": p["student"]}, p)
    working = deepcopy(state)
    for effect in submitted:
        name = key(effect["kind"], effect["id"])
        old = state["objects"].get(name)
        working["objects"][name] = {"kind": effect["kind"], "id": effect["id"], "version": old["version"] if old else state["revision"], "data": deepcopy(effect["data"])}
    judged = _comprehension_record(working, request, p)
    merged = {key(effect["kind"], effect["id"]): effect for effect in submitted + judged}
    return list(merged.values())


def _feeling_record(state, request, p):
    fields(p, "session_id", "block_id", "disposition")
    student = require_student(request)
    session, activity, course, cursor, block = _current_block(state, request, p)
    require(cursor["waiting_for"] == "feeling", "WRONG_GATE", "The comprehension gate must close before the feeling gate.")
    require(p["disposition"] in {"clear", "question"}, "INVALID_FEELING", "Record whether a question remains.")
    block["feelings"].append({"student": student, "disposition": p["disposition"]})
    waiting = "questions" if p["disposition"] == "question" or _unclosed_questions(state, session["activity_id"]) else "authorization"
    block["status"] = "feeling_recorded"
    cursor.update(waiting_for=waiting, next_action="resolve_question" if waiting == "questions" else "name_next_block")
    return [put("block", p["block_id"], block), put("cursor", session["activity_id"], cursor)]


def _coverage_decide(state, request, p):
    fields(p, "block_id", "coverage", "reason")
    student = require_student(request)
    block = _read(state, request, "block", p["block_id"])
    _course_activity(state, request, block["activity_id"])
    require(p["coverage"] in {"explicitly_deferred", "outside_active_lesson_boundary"}, "INVALID_COVERAGE", "Teaching and comprehension, not a coverage command, establish covered.")
    _text(p["reason"], "reason")
    require(block.get("coverage") != "covered", "COVERAGE_HISTORY", "Do not erase completed coverage.")
    block.update(coverage=p["coverage"], coverage_decision={"reason": p["reason"], "student": student})
    return [put("block", p["block_id"], block)]


def _session_close(state, request, p):
    fields(p, "session_id")
    session = _read(state, request, "session", p["session_id"])
    require(session.get("status") == "active", "SESSION_CLOSED", "Only an active session can close.")
    cursor = _cursor(state, request, session["activity_id"])
    session.update(status="closed", saved_cursor=deepcopy(cursor), closed_by=deepcopy(request.get("actor", {})))
    effects = [put("session", p["session_id"], session)]
    for tid, ticket in _objects(state, "ticket"):
        if ticket.get("session_id") == p["session_id"] and ticket.get("status") == "issued":
            ticket = _read(state, request, "ticket", tid); ticket.update(status="revoked", reason="session_closed")
            effects.append(put("ticket", tid, ticket))
    for mid, mistake in _objects(state, "mistake"):
        if mistake.get("pending_settlement", {}).get("session_id") == p["session_id"]:
            mistake = _read(state, request, "mistake", mid)
            pending = mistake.pop("pending_settlement"); mistake.update(pending["changes"])
            for result in mistake["retests"]:
                if result["session_id"] == p["session_id"]: result["settled"] = True
            effects.append(put("mistake", mid, mistake))
    return effects


def _exercise_configure(state, request, p):
    fields(p, "activity_id")
    _teacher(request); _new(state, "exercise", p["activity_id"])
    activity, course = _course_activity(state, request, p["activity_id"])
    require(activity["activity_type"] == "exercise", "NOT_EXERCISE", "Exercise configuration requires an exercise activity.")
    return [put("exercise", p["activity_id"], {"activity_id": p["activity_id"], "course_id": activity["course_id"], "problems": {}, "source_order": [], "supplemental_ids": [], "teaching_sequence": [], "assistance": [], "attempt_ids": [], "review_ids": []})]


def _problem_add(state, request, p):
    fields(p, "activity_id", "problem_id", "text", "origin")
    exercise = _read(state, request, "exercise", p["activity_id"])
    _course_activity(state, request, p["activity_id"])
    require(p["problem_id"] not in exercise["problems"], "PROBLEM_EXISTS", "Problem identity cannot be reused.")
    _text(p["text"], "problem text")
    effects = []
    if p["origin"] == "teacher_generated":
        opt_in = _student_choice(request, {"请加练", "加练", "我想加练", "request supplement", "extra practice"})
        source = {"origin": "teacher_generated", "opt_in": opt_in}
    else:
        _teacher(request)
        require(p["origin"] == "source", "INVALID_PROBLEM_ORIGIN", "A problem is source-backed or explicitly requested supplemental work.")
        fields(p, "page_id", "source_excerpt", "locator")
        page = _page_current(state, request, p["page_id"]); document = get(state, "source", page["source_id"])
        require(exercise["course_id"] in document["course_ids"] and p["source_excerpt"] in page["verified_text"] and bool(p["source_excerpt"]), "PROBLEM_SOURCE", "Problem must trace to the verified course source.")
        source = {k: deepcopy(p[k]) for k in ("origin", "page_id", "source_excerpt", "locator")}
        if document.get("purpose") in {"exam_paper", "exam_solution"}:
            fields(p, "bank_id", "bank_problem_id")
            bank = _read(state, request, "exam_bank", p["bank_id"])
            require(p["bank_problem_id"] in bank["problems"], "PROBLEM_MISSING", "Use the bank's original problem identity.")
            problem = bank["problems"][p["bank_problem_id"]]; paper = bank["papers"][problem["paper_id"]]
            require(paper["pool"] == "practice" and problem["page_id"] == p["page_id"] and problem["source_excerpt"] == p["source_excerpt"], "ASSESSMENT_ISOLATION", "Only practice-pool questions may enter teaching, with their original references.")
            require(not any(e.get("bank_id") == p["bank_id"] and e.get("status") in {"open", "submitted", "flagged"} and any(bank["problems"][qid]["paper_id"] == problem["paper_id"] for qid in e["problem_ids"]) for _, e in _objects(state, "exam")), "EXAM_ISOLATION", "A paper currently being examined cannot enter ordinary teaching.")
            source.update(bank_id=p["bank_id"], bank_problem_id=p["bank_problem_id"])
            bank["exposures"].append({"problem_id": p["bank_problem_id"], "reason": "exercise_import", "reference": p["activity_id"], "actor": deepcopy(request["actor"])})
            effects.append(put("exam_bank", p["bank_id"], bank))
    exercise["problems"][p["problem_id"]] = {"text": p["text"], **source}
    if p.get("coverage_checkpoint_ids"):
        ids = _list(p["coverage_checkpoint_ids"], "coverage checkpoints")
        require(len(ids) == len(set(ids)), "COVERAGE_CHECKPOINT", "Do not repeat checkpoint bindings.")
        for ident in ids:
            checkpoint = _read(state, request, "checkpoint", ident)
            original, _ = _course_activity(state, request, checkpoint["activity_id"])
            require(checkpoint.get("status") == "confirmed" and original["course_id"] == exercise["course_id"], "COVERAGE_CHECKPOINT", "Bind an actual confirmed course checkpoint before asking a coverage probe.")
        exercise["problems"][p["problem_id"]]["coverage_checkpoint_ids"] = deepcopy(ids)
    order = "supplemental_ids" if p["origin"] == "teacher_generated" else "source_order"
    exercise.setdefault(order, []).append(p["problem_id"])
    exercise["teaching_sequence"].append(p["problem_id"])
    return effects + [put("exercise", p["activity_id"], exercise)]


def _exercise_reorder(state, request, p):
    fields(p, "activity_id", "teaching_sequence", "reason")
    _teacher(request); exercise = _read(state, request, "exercise", p["activity_id"])
    sequence = _list(p["teaching_sequence"], "teaching_sequence")
    require(len(sequence) == len(set(sequence)) and set(sequence) == set(exercise["problems"]), "PROBLEM_SEQUENCE", "Reordering cannot drop, duplicate or introduce original or opted-in supplemental problems.")
    _text(p["reason"], "reason")
    exercise["teaching_sequence"] = deepcopy(sequence)
    exercise.setdefault("sequence_history", []).append({"sequence": deepcopy(sequence), "reason": p["reason"], "actor": deepcopy(request["actor"])})
    return [put("exercise", p["activity_id"], exercise)]


def _hint_authorize(state, request, p):
    fields(p, "ticket_id", "session_id", "problem_id", "level")
    choices = {"direction": {"方向", "方向提示", "direction"}, "reference": {"资料", "指定资料", "reference"}, "solution": {"完整讲解", "完整解答", "solution"}}
    require(p["level"] in choices, "HINT_LEVEL", "Specify direction, reference or solution permission.")
    decision = _student_choice(request, choices[p["level"]])
    _new(state, "ticket", p["ticket_id"])
    session, activity, course = _context(state, request, p["session_id"])
    exercise = _read(state, request, "exercise", session["activity_id"])
    require(p["problem_id"] in exercise["problems"], "PROBLEM_MISSING", "Hint target does not belong to this exercise.")
    return [put("ticket", p["ticket_id"], {"purpose": "hint", "session_id": p["session_id"], "activity_id": session["activity_id"], "problem_id": p["problem_id"], "level": p["level"], "status": "issued", "decision": decision})]


def _hint_record(state, request, p):
    fields(p, "session_id", "problem_id", "level", "content")
    _teacher(request); session, activity, course = _context(state, request, p["session_id"])
    exercise = _read(state, request, "exercise", session["activity_id"])
    profile = _read(state, request, "student", "current")
    require(p["problem_id"] in exercise["problems"], "PROBLEM_MISSING", "Unknown exercise problem.")
    require(not any(x.get("activity_id") == session["activity_id"] and x.get("status") in {"open", "submitted"} and p["problem_id"] in x.get("problem_ids", []) for _, x in _objects(state, "exam")), "EXAM_ISOLATION", "No help may enter an open examination of this problem.")
    require(p["level"] in {"concept", "reasoning_feedback", "direction", "reference", "solution"}, "HINT_LEVEL", "Unsupported help level.")
    _text(p["content"], "hint content")
    effects = []; permission = None
    gate = profile.get("exercise_hint_gate", "unconfigured")
    if p["level"] in {"direction", "reference", "solution"} and gate != "disabled":
        fields(p, "ticket_id"); permission = _read(state, request, "ticket", p["ticket_id"])
        require(permission.get("purpose") == "hint" and permission.get("status") == "issued" and permission.get("session_id") == p["session_id"] and permission.get("activity_id") == session["activity_id"] and permission.get("problem_id") == p["problem_id"] and permission.get("level") == p["level"], "HINT_PERMISSION", "This help requires matching current-session and same-level permission.")
        permission["status"] = "consumed"; effects.append(put("ticket", p["ticket_id"], permission))
    if p["level"] in {"concept", "reasoning_feedback"}:
        require(p.get("scope_only") is True, "HINT_SCOPE", "Concept and reasoning feedback must not add problem-specific solution structure.")
    exercise["assistance"].append({"problem_id": p["problem_id"], "level": p["level"], "content": p["content"], "teacher": deepcopy(request["actor"]), "ticket_id": p.get("ticket_id"), "scope_only": p.get("scope_only"), "polluted": p.get("polluted") is True})
    return effects + [put("exercise", session["activity_id"], exercise)]


def _answers(answers, problems):
    _list(answers, "answers")
    require(all(isinstance(a, dict) for a in answers), "INVALID_ANSWER", "Answers must be objects.")
    ids = [a.get("problem_id") for a in answers]
    require(len(ids) == len(set(ids)) and set(ids) <= set(problems), "ATTEMPT_PROBLEMS", "Answers must name distinct problems in this exercise.")
    for answer in answers:
        require(bool(answer.get("text")) or bool(answer.get("blob_refs")), "EMPTY_ANSWER", "Preserve actual answer text or original attachment references.")
        if "text" in answer: _text(answer["text"], "answer text")
        for blob in answer.get("blob_refs", []):
            require(isinstance(blob, dict) and _sha(blob.get("sha256")) and type(blob.get("bytes")) is int and blob["bytes"] >= 0, "INVALID_BLOB_REFERENCE", "Original answer assets require SHA-256 and byte length.")
    return deepcopy(answers)


def _assistance(exercise, ids):
    rank = {"concept": 0, "reasoning_feedback": 0, "direction": 1, "reference": 2, "solution": 3}
    result = {}
    for pid in ids:
        entries = [x for x in exercise["assistance"] if x["problem_id"] == pid]
        unknown = any(x.get("level") == "legacy_unknown" for x in entries)
        result[pid] = {"level": max((x["level"] for x in entries if rank.get(x["level"], 0) > 0), key=lambda x: rank[x], default="legacy_unknown" if unknown else "none"), "polluted": any(x.get("polluted") is True for x in entries), "history_unknown": unknown, "evidence": entries}
    return result


def _attempt_submit(state, request, p):
    fields(p, "attempt_id", "activity_id", "answers")
    student = require_student(request); _new(state, "attempt", p["attempt_id"])
    exercise = _read(state, request, "exercise", p["activity_id"])
    activity, course = _course_activity(state, request, p["activity_id"])
    require(activity["status"] == "ongoing", "ACTIVITY_NOT_ONGOING", "Submit work to an ongoing activity.")
    require(course.get("status") == "ongoing" and not course.get("paused"), "COURSE_NOT_ONGOING", "Resume the course before submitting new work.")
    profile = _read(state, request, "student", "current")
    answers = _answers(p["answers"], exercise["problems"])
    fields(exercise, "criterion_id")
    criterion = get(state, "criterion", exercise["criterion_id"])
    require({a["problem_id"] for a in answers} <= set(criterion["problem_ids"]), "CRITERION_PROBLEMS", "Freeze a criterion for all submitted problems before accepting an attempt.")
    assistance = _assistance(exercise, [a["problem_id"] for a in answers])
    data = {"activity_id": p["activity_id"], "answers": answers, "student": student, "criterion_id": exercise["criterion_id"], "assistance": assistance, "hint_gate": profile.get("exercise_hint_gate", "unconfigured")}
    active = [(sid, s) for sid, s in _objects(state, "session") if s.get("activity_id") == p["activity_id"] and s.get("status") == "active"]
    if p.get("session_id"):
        _context(state, request, p["session_id"])
        require(any(sid == p["session_id"] for sid, _ in active), "ATTEMPT_SESSION", "Answer session belongs to this activity.")
        data["session_id"] = p["session_id"]
    elif len(active) == 1:
        _context(state, request, active[0][0]); data["session_id"] = active[0][0]
    if p.get("submitted_at"):
        _timestamp(p["submitted_at"]); data["submitted_at"] = p["submitted_at"]
    exercise["attempt_ids"].append(p["attempt_id"])
    return [put("attempt", p["attempt_id"], data), put("exercise", p["activity_id"], exercise)]


def _ratings(attempt, criterion, ratings):
    _list(ratings, "ratings")
    ids = [r.get("problem_id") for r in ratings]; answer_ids = {a["problem_id"] for a in attempt["answers"]}
    require(len(ids) == len(set(ids)) and set(ids) == answer_ids and answer_ids <= set(criterion.get("problem_ids", [])), "REVIEW_PROBLEMS", "Review must cover exactly the actual submitted problems under this criterion.")
    result = deepcopy(ratings)
    for rating in result:
        fields(rating, "verdict", "rationale", "score")
        require(rating["verdict"] in {"correct", "incorrect", "partial", "uncertain"}, "INVALID_VERDICT", "Unsupported review judgment.")
        _text(rating["rationale"], "rationale"); _number(rating["score"], "score")
        require(rating["score"] <= criterion["max_scores"][rating["problem_id"]], "SCORE_RANGE", "Score exceeds the frozen criterion.")
        help_ = attempt["assistance"][rating["problem_id"]]
        uncertain_help = help_.get("history_unknown") or help_["level"] == "legacy_unknown"
        independent = rating["verdict"] == "correct" and help_["level"] == "none" and not help_["polluted"] and not uncertain_help
        if "independent" in rating: require(rating["independent"] is independent, "FALSE_INDEPENDENCE", "Helped or polluted work cannot become independent evidence.")
        rating["independent"] = independent
        rating["evidence_class"] = "polluted" if help_["polluted"] else "legacy_uncertain" if uncertain_help else ("independent" if independent else "assisted" if help_["level"] != "none" else "not_yet_correct")
    return result


def _review_record(state, request, p):
    fields(p, "review_id", "attempt_id", "criterion_id", "ratings")
    teacher = _teacher(request); _new(state, "review", p["review_id"])
    attempt = get(state, "attempt", p["attempt_id"])
    require(not attempt.get("history_only") and not attempt.get("migration_requires_reconciliation"), "MIGRATION_RECONCILIATION_REQUIRED", "A legacy answer without a frozen criterion cannot be retrospectively regraded.")
    require(not attempt.get("exam_id"), "EXAM_REVIEW_ROUTE", "Use exam.grade for an exam attempt.")
    exercise = _read(state, request, "exercise", attempt["activity_id"])
    criterion = get(state, "criterion", p["criterion_id"])
    require(criterion["target_kind"] == "exercise" and criterion["target_id"] == attempt["activity_id"], "CRITERION_TARGET", "Criterion belongs to another exercise.")
    require(attempt.get("criterion_id") == p["criterion_id"], "CRITERION_CHANGED", "Do not regrade an answer under a rubric created after submission.")
    prior = [(i, r) for i, r in _objects(state, "review") if r.get("attempt_id") == p["attempt_id"]]
    if prior:
        fields(p, "supersedes", "correction_reason")
        require(p["supersedes"] in {i for i, _ in prior}, "REVIEW_CORRECTION", "A correction must reference a prior review of this same attempt.")
        require(not any(r.get("supersedes") == p["supersedes"] for _, r in prior), "REVIEW_SUPERSEDED", "Correct only the current review leaf; a historical judgment cannot fork a second effective grade.")
        _text(p["correction_reason"], "correction_reason")
    data = {"attempt_id": p["attempt_id"], "criterion_id": p["criterion_id"], "ratings": _ratings(attempt, criterion, p["ratings"]), "teacher": teacher}
    if prior: data.update(supersedes=p["supersedes"], correction_reason=p["correction_reason"])
    exercise["review_ids"].append(p["review_id"])
    return [put("review", p["review_id"], data), put("exercise", attempt["activity_id"], exercise)]


def _post_exam_learning_evidence(state, request, exam, ref):
    """Resolve current learning evidence to the original work identity."""
    require(ref.get("kind") in {"review", "checkpoint"}, "REINFORCEMENT_EVIDENCE", "Use actual checkpoint or review evidence.")
    evidence = _read(state, request, ref["kind"], ref["id"])
    require(not evidence.get("history_only") and not evidence.get("migration_requires_reconciliation"), "MIGRATION_RECONCILIATION_REQUIRED", "Unresolved historical evidence cannot establish new learning.")
    require(version(state, ref["kind"], ref["id"]) > version(state, "review", exam["review_id"]), "REINFORCEMENT_EVIDENCE", "Use learning evidence recorded after the examination judgment.")
    identity = (ref["kind"], ref["id"])
    if ref["kind"] == "review":
        require(not any(r.get("supersedes") == ref["id"] for _, r in _objects(state, "review")), "REVIEW_SUPERSEDED", "Consume the current review, preserving historical judgments only as history.")
        identity = ("attempt", evidence["attempt_id"])
        evidence = _read(state, request, "attempt", evidence["attempt_id"])
        require(not evidence.get("history_only") and not evidence.get("migration_requires_reconciliation") and not evidence.get("exam_id"), "REINFORCEMENT_EVIDENCE", "Use actual subsequent learning, not an old answer regraded later or another examination.")
        require(version(state, "attempt", identity[1]) > version(state, "review", exam["review_id"]), "REINFORCEMENT_EVIDENCE", "A new review identity cannot turn pre-exam work into post-exam learning.")
    else:
        require(evidence.get("status") == "confirmed", "REINFORCEMENT_EVIDENCE", "A queued or pending checkpoint is not completed learning evidence.")
    return identity, evidence


def _question(state, request, p, action):
    fields(p, "question_id")
    if action == "question.open":
        fields(p, "activity_id", "text")
        student = require_student(request); _new(state, "question", p["question_id"])
        _course_activity(state, request, p["activity_id"])
        require(student["text"] == p["text"], "QUESTION_ATTRIBUTION", "Retain the question as the student actually expressed it.")
        data = {"activity_id": p["activity_id"], "text": p["text"], "student": student, "status": "open", "answers": []}
        return [put("question", p["question_id"], data)]
    q = _read(state, request, "question", p["question_id"])
    require(q["status"] != "merged", "QUESTION_MERGED", "Use the retained canonical question identity.")
    if action == "question.merge":
        fields(p, "into_question_id", "reason")
        student = _student_choice(request, {"合并疑问", "merge questions"})
        target = _read(state, request, "question", p["into_question_id"])
        require(p["question_id"] != p["into_question_id"] and q["activity_id"] == target["activity_id"], "QUESTION_MERGE_SCOPE", "Merge distinct questions from the same activity only.")
        require(q["status"] in {"open", "answered"} and target["status"] in {"open", "answered"}, "QUESTION_MERGE_STATE", "A merge cannot silently reopen or confirm a closed question.")
        _text(p["reason"], "merge reason")
        target.setdefault("merged_sources", []).append({"question_id": p["question_id"], "reason": p["reason"], "decision": student})
        q.update(status_before_merge=q["status"], status="merged", merged_into=p["into_question_id"], merge_decision=student)
        # The new combined question still needs an answer and actual closure.
        target["status"] = "open"
        return [put("question", p["question_id"], q), put("question", p["into_question_id"], target)]
    if action == "question.answer":
        fields(p, "answer"); teacher = _teacher(request)
        require(q["status"] != "closed", "QUESTION_CLOSED", "Reopen a question explicitly before answering again.")
        _text(p["answer"], "answer")
        q["answers"].append({"text": p["answer"], "teacher": teacher}); q["status"] = "answered"
    elif action == "question.close":
        student = _student_choice(request, {"明白了", "问题已解决", "理解了", "resolved", "close", "understood"})
        require(q["status"] == "answered", "QUESTION_NOT_ANSWERED", "An answer must precede confirmed closure.")
        q.update(status="closed", closed_by=student)
    elif action == "question.reopen":
        student = require_student(request)
        require(q["status"] == "closed", "QUESTION_NOT_CLOSED", "Only a closed question can be reopened.")
        q.update(status="open"); q.setdefault("reopenings", []).append(student)
    effects = [put("question", p["question_id"], q)]
    if action == "question.close":
        cursor = _cursor(state, request, q["activity_id"])
        remaining = [(i, other) for i, other in _unclosed_questions(state, q["activity_id"]) if i != p["question_id"]]
        if cursor.get("waiting_for") == "questions" and not remaining:
            block = _read(state, request, "block", cursor["block_id"])
            cursor.update(waiting_for="authorization" if block.get("feelings") else "feeling", next_action="name_next_block" if block.get("feelings") else "ask_feeling")
            effects.append(put("cursor", q["activity_id"], cursor))
    return effects


def _legacy_retest_due(state, mistake, learning_date):
    """The first new result consumes the preserved historical due condition."""
    if not mistake.get("legacy_cycle_baseline") or mistake.get("retests"):
        return True
    if mistake.get("recovery_not_before"):
        return learning_date >= mistake["recovery_not_before"]
    anchor, minimum = mistake.get("recovery_learning_date_anchor"), mistake.get("recovery_min_subsequent_learning_dates")
    if not anchor or type(minimum) is not int or minimum <= 0:
        return False
    spans = _objects(state, "timespan")
    replaced = {s["corrects"] for _, s in spans if s.get("corrects")}
    activities = dict(_objects(state, "activity"))
    days = {s["learning_day"] for i, s in spans if i not in replaced and s.get("quality") in {"exact", "estimated"} and s.get("learning_day") and anchor < s["learning_day"] <= learning_date and activities.get(s.get("activity_id"), {}).get("course_id") == mistake["course_id"]}
    return len(days) >= minimum


def _mistake(state, request, p, action):
    fields(p, "mistake_id")
    fields(p, "review_id", "problem_id")
    review = get(state, "review", p["review_id"])
    require(not review.get("history_only") and not review.get("migration_requires_reconciliation"), "MIGRATION_RECONCILIATION_REQUIRED", "Reconcile uncertain legacy grading before using it as a new retest.")
    require(not any(r.get("supersedes") == p["review_id"] for _, r in _objects(state, "review")), "REVIEW_SUPERSEDED", "A corrected historical judgment cannot be consumed as current retest evidence.")
    attempt = get(state, "attempt", review["attempt_id"])
    if action in {"mistake.record", "mistake.recur"}:
        fields(p, "review_id", "problem_id", "root_cause")
        _teacher(request)
        if action == "mistake.record": _new(state, "mistake", p["mistake_id"])
        activity, _ = _course_activity(state, request, attempt["activity_id"])
        ratings = [r for r in review["ratings"] if r["problem_id"] == p["problem_id"]]
        require(ratings and ratings[0]["verdict"] in {"incorrect", "partial"} and ratings[0]["evidence_class"] not in {"polluted", "legacy_uncertain"}, "MISTAKE_EVIDENCE", "A formal mistake needs known unpolluted answer evidence; unknown historical assistance cannot be assumed clean.")
        _text(p["root_cause"], "root_cause")
        knowledge = p.get("knowledge_key", p["root_cause"])
        if action == "mistake.recur":
            mistake = _read(state, request, "mistake", p["mistake_id"])
            require(mistake["course_id"] == activity["course_id"] and mistake["knowledge_key"] == knowledge, "MISTAKE_KEY_MISMATCH", "Recurrence retains the same course and knowledge point.")
            require(not mistake.get("pending_settlement"), "RETEST_PENDING_SETTLEMENT", "Settle pending formal results before merging recurrence.")
            require(not any(x["review_id"] == p["review_id"] and x["problem_id"] == p["problem_id"] for x in mistake.setdefault("recurrences", [])), "MISTAKE_DUPLICATE", "Do not count one source error twice.")
            mistake["recurrences"].append({"review_id": p["review_id"], "problem_id": p["problem_id"], "root_cause": p["root_cause"], "actor": deepcopy(request["actor"])})
            if mistake["status"] == "maintenance":
                mistake.update(status="active", cycle_start=len(mistake["retests"]), independent_streak=0, failed_retests=0, cycle_attempts=0, cycle_successes=0, legacy_cycle_baseline_active=False)
                if mistake.get("cycle") is not None: mistake["cycle"] += 1
            return [put("mistake", p["mistake_id"], mistake)]
        require(not any(m.get("course_id") == activity["course_id"] and m.get("knowledge_key") == knowledge for _, m in _objects(state, "mistake")), "MISTAKE_KEY_EXISTS", "Merge recurrence into the existing knowledge point.")
        require(p.get("knowledge_type", "technical") in {"technical", "factual", "conceptual"}, "PRAXIS_KNOWLEDGE_BOUNDARY", "Knowledge probes cannot certify discipline or practical judgment.")
        return [put("mistake", p["mistake_id"], {"course_id": activity["course_id"], "activity_id": attempt["activity_id"], "problem_id": p["problem_id"], "review_id": p["review_id"], "original_attempt_id": review["attempt_id"], "origin_session_id": attempt.get("session_id"), "knowledge_key": knowledge, "root_cause": p["root_cause"], "status": "active", "retests": [], "independent_streak": 0, "failed_retests": 0, "cycle_start": 0, "recurrences": []})]
    fields(p, "review_id", "problem_id")
    _teacher(request); mistake = _read(state, request, "mistake", p["mistake_id"])
    original_summary = deepcopy(mistake)
    require(not any(r["review_id"] == p["review_id"] and r["problem_id"] == p["problem_id"] for r in mistake["retests"]), "RETEST_DUPLICATE", "One review cannot be counted twice as a retest.")
    require(review["attempt_id"] != mistake.get("original_attempt_id") and not any(r.get("attempt_id") == review["attempt_id"] for r in mistake["retests"]), "RETEST_DUPLICATE", "A corrected grade of the same answer is not a new independent retest.")
    require(not mistake.get("pending_settlement"), "RETEST_PENDING_SETTLEMENT", "Close the preceding session to settle its provisional result.")
    activity, _ = _course_activity(state, request, attempt["activity_id"])
    original, _ = _course_activity(state, request, mistake["activity_id"])
    require(activity["course_id"] == original["course_id"], "RETEST_COURSE", "A knowledge-point retest may cross activities within its original course.")
    rating = next((r for r in review["ratings"] if r["problem_id"] == p["problem_id"]), None)
    require(rating is not None, "RETEST_EVIDENCE", "Review does not judge the proposed retest problem.")
    require(rating.get("evidence_class") != "legacy_uncertain", "RETEST_EVIDENCE", "Unknown historical assistance cannot establish a formal cycle result; use a fresh safety-checked variant.")
    fields(p, "variant_id", "session_id", "happened_at")
    variant = _read(state, request, "variant", p["variant_id"])
    require(variant["mistake_id"] == p["mistake_id"] and variant["activity_id"] == attempt["activity_id"] and variant["problem_id"] == p["problem_id"], "RETEST_VARIANT", "The actual answer must judge this knowledge point's safety-checked variant.")
    require(attempt.get("session_id") == p["session_id"] and attempt.get("submitted_at") == p["happened_at"], "RETEST_ATTRIBUTION", "Retain the original answer's session and timestamp.")
    _context(state, request, p["session_id"])
    when = _timestamp(p["happened_at"]); learning_date = (when-timedelta(hours=4)).date().isoformat()
    require(_legacy_retest_due(state, mistake, learning_date), "RETEST_RECOVERY_DUE", "Respect the preserved absolute date or count of actual subsequent learning dates.")
    previous = mistake["retests"][-1] if mistake["retests"] else None
    require((previous["session_id"] if previous else mistake.get("origin_session_id")) != p["session_id"], "RETEST_SPACING", "Same-session repetition is current understanding, not delayed retrieval.")
    if previous:
        require((when-_timestamp(previous["happened_at"])).total_seconds() >= 3*86400, "RETEST_SPACING", "Formal retests are at least three days apart.")
        require(previous["probe"] != variant["probe"], "RETEST_REPETITION", "Consecutive retests require a different probe.")
    require(not any(x["surface_sha256"] == variant["surface_sha256"] for x in mistake["retests"]), "RETEST_REPETITION", "Repeating the same surface question is not new retrieval.")
    if mistake["status"] == "aged":
        fields(p, "review_sheet_id")
        sheet = _read(state, request, "aged_review", p["review_sheet_id"])
        require(sheet["status"] == "authorized" and sheet["activity_id"] == attempt["activity_id"] and p["mistake_id"] in sheet["mistake_ids"], "AGED_REVIEW_SOURCE", "Aged results belong to an authorized review sheet.")
        require(not any(x.get("review_sheet_id") == p["review_sheet_id"] for x in mistake["retests"]), "AGED_REVIEW_DUPLICATE", "One review sheet supplies at most one result per knowledge point.")
    result = "correct" if rating["independent"] else "wrong" if rating["verdict"] == "incorrect" and rating["evidence_class"] != "polluted" else "partial"
    mistake["retests"].append({"review_id": p["review_id"], "attempt_id": review["attempt_id"], "activity_id": attempt["activity_id"], "problem_id": p["problem_id"], "variant_id": p["variant_id"], "session_id": p["session_id"], "probe": variant["probe"], "surface_sha256": variant["surface_sha256"], "independent": rating["independent"], "verdict": rating["verdict"], "result": result, "cycle": p.get("cycle"), "happened_at": p["happened_at"], "learning_date": learning_date, "review_sheet_id": p.get("review_sheet_id")})
    previous_status = mistake["status"]
    if previous_status == "aged":
        mistake["aged_success_streak"] = mistake.get("aged_success_streak", 0)+1 if result == "correct" else 0
        if mistake["aged_success_streak"] >= 2: mistake["status"] = "maintenance"
    else:
        if previous_status == "maintenance" and result != "correct":
            mistake.update(status="active", cycle_start=len(mistake["retests"])-1, reopen_count=mistake.get("reopen_count", 0)+1, legacy_cycle_baseline_active=False)
            if mistake.get("cycle") is not None: mistake["cycle"] += 1
        current = mistake["retests"][mistake.get("cycle_start", 0):]
        baseline = mistake.get("legacy_cycle_baseline", {}) if mistake.get("legacy_cycle_baseline_active", True) else {}
        require(not baseline or baseline["cycle_start"] == mistake.get("cycle_start", 0), "RETEST_BASELINE_CONFLICT", "A historical baseline belongs only to its preserved cycle.")
        successes = baseline.get("successes", 0) + sum(x["result"] == "correct" for x in current)
        errors = baseline.get("failures", 0) + sum(x["result"] == "wrong" for x in current)
        attempts = baseline.get("attempts", 0) + len(current)
        streak = baseline.get("independent_streak", 0)
        for x in current:
            streak = streak + 1 if x["result"] == "correct" else 0
        mistake.update(independent_streak=streak, failed_retests=errors, cycle_attempts=attempts, cycle_successes=successes)
        if successes >= 3 and (errors == 0 or streak >= 2): mistake["status"] = "maintenance"
        elif attempts >= 6 or errors >= 3: mistake.update(status="aged", aged_success_streak=0)
    summaries = {"status", "independent_streak", "failed_retests", "cycle_start", "reopen_count", "cycle_attempts", "cycle_successes", "aged_success_streak", "legacy_cycle_baseline_active", "cycle"}
    changes = {k: deepcopy(mistake[k]) for k in summaries if k in mistake}
    for name in summaries:
        if name in original_summary: mistake[name] = original_summary[name]
        else: mistake.pop(name, None)
    mistake["retests"][-1]["settled"] = False
    mistake["pending_settlement"] = {"session_id": p["session_id"], "changes": changes}
    return [put("mistake", p["mistake_id"], mistake)]


def _variant(state, request, p, action):
    fields(p, "variant_id"); _teacher(request)
    if action == "variant.create":
        fields(p, "mistake_id", "activity_id", "problem_id", "probe", "body", "self_solution", "judgment_basis", "transformation", "safety")
        _new(state, "variant", p["variant_id"]); mistake = _read(state, request, "mistake", p["mistake_id"])
        activity, _ = _course_activity(state, request, p["activity_id"])
        require(activity["course_id"] == mistake["course_id"], "VARIANT_COURSE", "A controlled variant probes the original course knowledge point.")
        require(p["probe"] in {"P1", "P2", "P3", "P4", "P5", "P6"}, "VARIANT_PROBE", "Use one of six recorded knowledge probes.")
        require(p["transformation"] in {"rephrase", "boundary", "example", "numbers", "condition", "context", "diagnose", "connect"}, "VARIANT_TRANSFORMATION", "Record the controlled transformation.")
        for name in ("body", "self_solution", "judgment_basis"): _text(p[name], name)
        safety = p["safety"]
        require(isinstance(safety, dict) and all(safety.get(k) is True for k in ("self_solved", "solvable", "judgment_clear")) and bool(safety.get("reference")), "VARIANT_SAFETY", "Retain complete self-solution and attributed solvability/judgment checks before use.")
        exercise = _read(state, request, "exercise", p["activity_id"], False)
        if exercise is None:
            require(activity["activity_type"] == "lesson", "NOT_PROBE_CARRIER", "A new knowledge probe carrier is attached to an existing Lesson only.")
            exercise = {"activity_id": p["activity_id"], "course_id": activity["course_id"], "carrier_kind": "lesson_probes", "problems": {}, "source_order": [], "supplemental_ids": [], "teaching_sequence": [], "assistance": [], "attempt_ids": [], "review_ids": []}
        require(p["problem_id"] not in exercise["problems"], "PROBLEM_EXISTS", "A variant cannot overwrite an original question.")
        exercise["problems"][p["problem_id"]] = {"text": p["body"], "origin": "controlled_variant", "variant_id": p["variant_id"], "knowledge_key": mistake["knowledge_key"]}
        exercise.setdefault("retest_ids", []).append(p["problem_id"]); exercise["teaching_sequence"].append(p["problem_id"])
        data = {**deepcopy(p), "surface_sha256": digest(p["body"]), "admitted_use": "daily", "provenance": deepcopy(request["actor"])}
        return [put("variant", p["variant_id"], data), put("exercise", p["activity_id"], exercise)]
    variant = _read(state, request, "variant", p["variant_id"])
    fields(p, "review_id")
    review = _read(state, request, "review", p["review_id"]); attempt = _read(state, request, "attempt", review["attempt_id"])
    require(not review.get("history_only") and not any(r.get("supersedes") == p["review_id"] for _, r in _objects(state, "review")), "VARIANT_TRIAL", "An uncertain or superseded historical judgment cannot admit a variant.")
    require(attempt["activity_id"] == variant["activity_id"] and any(x["problem_id"] == variant["problem_id"] and x["independent"] for x in review["ratings"]), "VARIANT_TRIAL", "An independent daily trial precedes informal quiz use.")
    require(not _unclosed_questions(state, variant["activity_id"]), "VARIANT_DISPUTED", "Resolve questions before advancing variant use.")
    variant.update(admitted_use="informal_quiz", trial_review_id=p["review_id"])
    return [put("variant", p["variant_id"], variant)]


def _aged_review(state, request, p, action):
    if action == "aged_review.window": return _aged_window(state, request, p)
    fields(p, "sheet_id")
    if action == "aged_review.authorize":
        sheet = _read(state, request, "aged_review", p["sheet_id"])
        student = _student_choice(request, {"生成陈年复习卷", "确认复习卷", "generate review", "authorize review"})
        fields(p, "body_sha256")
        require(sheet["status"] == "proposed" and p["body_sha256"] == digest(sheet["proposal"]), "REVIEW_PROPOSAL_CHANGED", "Authorize the actual proposed review sheet.")
        sheet.update(status="authorized", decision=student)
        return [put("aged_review", p["sheet_id"], sheet)] + _use_aged_window(state, request, sheet, p["sheet_id"])
    fields(p, "activity_id", "variant_ids", "context_closure", "as_of")
    _new(state, "aged_review", p["sheet_id"]); activity, _ = _course_activity(state, request, p["activity_id"])
    profile = _read(state, request, "student", "current"); _timestamp(p["as_of"])
    ids = _list(p["variant_ids"], "variant_ids")
    require(len(ids) == len(set(ids)), "REVIEW_VARIANTS", "Each probe appears once in a sheet.")
    variants = [_read(state, request, "variant", i) for i in ids]; mistakes = [v["mistake_id"] for v in variants]
    require(len(mistakes) == len(set(mistakes)), "AGED_REVIEW_DUPLICATE", "Each sheet gives one independent result per knowledge point.")
    for variant in variants:
        mistake = _read(state, request, "mistake", variant["mistake_id"])
        require(variant["activity_id"] == p["activity_id"] and mistake["status"] == "aged" and mistake["course_id"] == activity["course_id"], "AGED_REVIEW_SOURCE", "Aged sheets draw solely from the course's current aged knowledge points.")
    _text(p["context_closure"], "related knowledge-cluster closure")
    estimates = p.get("estimated_minutes", {i: 6 if v["probe"] == "P6" else 3 for i, v in zip(ids, variants)})
    require(set(estimates) == set(ids), "REVIEW_TIMING", "Every probe needs an estimate of smooth correct-answer time.")
    for value in estimates.values(): _number(value, "estimated question time", .1)
    linked = sum(v["probe"] == "P6" for v in variants)
    require(len(ids) < 5 or linked in {len(ids)//5, math.ceil(len(ids)/5)}, "REVIEW_BALANCE", "About one in five probes connects nearby learned concepts.")
    minutes = math.ceil(sum(estimates.values())/.8/5)*5
    require(minutes <= 50, "REVIEW_SPLIT_REQUIRED", "This sheet exceeds 50 minutes; split its probes and recompute each sheet, never compress answer time.")
    mode = profile.get("aged_review_calendar", "suggest")
    require(mode in {"off", "suggest", "auto"}, "REVIEW_CALENDAR_MODE", "Choose off, suggest or explicitly authorized auto.")
    direct = request.get("actor", {}).get("role") == "student"
    if direct: decision = _student_choice(request, {"生成陈年复习卷", "generate review"})
    else:
        _teacher(request); decision = None
        require(mode != "off", "REVIEW_CALENDAR_OFF", "Calendar is off; wait for an actual student request.")
        fields(p, "window_id")
        window = _read(state, request, "aged_window", p["window_id"])
        require(window["status"] == "candidate" and not window.get("used_by") and window["course_id"] == activity["course_id"] and set(mistakes) <= set(window["eligible_mistake_ids"]), "REVIEW_WINDOW", "Automatic suggestions use the actual related learning-segment window.")
        if mode == "auto":
            require(profile.get("last_declaration", {}).get("role") == "student", "REVIEW_AUTO_UNAUTHORIZED", "Automatic generation needs the recorded student profile declaration.")
    proposal = {"activity_id": p["activity_id"], "course_id": activity["course_id"], "variant_ids": ids, "mistake_ids": mistakes, "context_closure": p["context_closure"], "estimated_minutes": estimates, "duration_minutes": minutes, "planning_accuracy": .8, "as_of": p["as_of"], "window_id": p.get("window_id")}
    sheet = {**proposal, "proposal": proposal, "status": "authorized" if direct or mode == "auto" else "proposed", "decision": decision, "calendar_mode": mode}
    return [put("aged_review", p["sheet_id"], sheet)] + (_use_aged_window(state, request, sheet, p["sheet_id"]) if sheet["status"] == "authorized" else [])


def _use_aged_window(state, request, sheet, sheet_id):
    if not sheet.get("window_id"): return []
    window = _read(state, request, "aged_window", sheet["window_id"])
    require(not window.get("used_by"), "REVIEW_WINDOW_USED", "The related closure window already produced an authorized sheet.")
    calendar = _read(state, request, "aged_calendar", sheet["course_id"], False) or {"course_id": sheet["course_id"], "reminded_windows": []}
    require(len(set(window["completed_segment_ids"])-set(calendar.get("last_sheet_segment_ids", []))) >= 3, "REVIEW_WINDOW_USED", "An equivalent named-segment window has already been consumed.")
    calendar.update(last_sheet_segment_ids=window["completed_segment_ids"], last_sheet_at=sheet["as_of"])
    window["used_by"] = sheet_id
    return [put("aged_window", sheet["window_id"], window), put("aged_calendar", sheet["course_id"], calendar)]


def _learning_structure(state, request, p, action):
    fields(p, "course_id"); _read(state, request, "course", p["course_id"])
    if action == "learning_structure.configure":
        fields(p, "segments")
        student = require_student(request)
        segments = _list(p["segments"], "named course segments")
        ids = [s["segment_id"] for s in segments]
        require(len(ids) == len(set(ids)), "SEGMENT_IDENTITY", "Named course segments have stable distinct identities.")
        for segment in segments:
            fields(segment, "segment_id", "title", "checkpoint_ids", "knowledge_keys")
            _text(segment["title"], "segment title"); _list(segment["knowledge_keys"], "planned knowledge keys")
            for ident in _list(segment["checkpoint_ids"], "segment checkpoint references"):
                cp = _read(state, request, "checkpoint", ident)
                activity, _ = _course_activity(state, request, cp["activity_id"])
                require(activity["course_id"] == p["course_id"], "SEGMENT_COURSE", "Plan checkpoints belong to this course.")
        old = _read(state, request, "learning_structure", p["course_id"], False)
        if old:
            require({x["segment_id"] for x in old["segments"]} <= set(ids), "SEGMENT_REMOVAL", "Retain the named structure history; do not erase completed or pending segments.")
            new = {x["segment_id"]: x for x in segments}
            for segment in old["segments"]:
                if get(state, "learning_segment", p["course_id"]+"/"+segment["segment_id"], False):
                    require(new[segment["segment_id"]] == segment, "SEGMENT_COMPLETED", "A completed segment's meaning and evidence binding are frozen.")
        return [put("learning_structure", p["course_id"], {"course_id": p["course_id"], "segments": deepcopy(segments), "student_confirmation": student, "plan_reference": deepcopy(p.get("plan_reference"))})]
    fields(p, "segment_id", "completed_at"); _teacher(request); _timestamp(p["completed_at"])
    identity = p["course_id"]+"/"+p["segment_id"]; _new(state, "learning_segment", identity)
    structure = _read(state, request, "learning_structure", p["course_id"])
    matches = [s for s in structure["segments"] if s["segment_id"] == p["segment_id"]]
    require(len(matches) == 1, "SEGMENT_MISSING", "Complete an existing named plan segment.")
    segment = matches[0]
    for ident in segment["checkpoint_ids"]:
        cp = _read(state, request, "checkpoint", ident)
        require(cp["status"] == "confirmed", "SEGMENT_INCOMPLETE", "Every mapped checkpoint needs actual confirmation.")
    return [put("learning_segment", identity, {**deepcopy(segment), "course_id": p["course_id"], "structure_version": version(state, "learning_structure", p["course_id"]), "completed_at": p["completed_at"], "actor": deepcopy(request["actor"])})]


def _aged_window(state, request, p):
    fields(p, "window_id", "course_id", "as_of"); _teacher(request); _new(state, "aged_window", p["window_id"])
    _read(state, request, "course", p["course_id"])
    profile = _read(state, request, "student", "current")
    require(profile.get("aged_review_calendar", "suggest") != "off", "REVIEW_CALENDAR_OFF", "Do not proactively remind or suggest when this calendar is off.")
    cutoff = _timestamp(p["as_of"])
    calendar = _read(state, request, "aged_calendar", p["course_id"], False) or {"course_id": p["course_id"], "reminded_windows": [], "last_sheet_segment_ids": []}
    segments = [(i, s) for i, s in _objects(state, "learning_segment") if s["course_id"] == p["course_id"] and _timestamp(s["completed_at"]) <= cutoff]
    for ident, _ in segments: _read(state, request, "learning_segment", ident)
    new_segments = {i for i, _ in segments} - set(calendar.get("last_sheet_segment_ids", []))
    aged = [(i, m) for i, m in _objects(state, "mistake") if m.get("course_id") == p["course_id"] and m.get("status") == "aged" and not m.get("migration_requires_reconciliation")]
    related = next((s for i, s in segments if i == p.get("related_segment_id")), None)
    eligible = [i for i, m in aged if related and m["knowledge_key"] in related["knowledge_keys"]]
    spans = _objects(state, "timespan"); replaced = {s["corrects"] for _, s in spans if s.get("corrects")}
    activities = dict(_objects(state, "activity")); cutoff_day = (cutoff-timedelta(hours=4)).date().isoformat()
    start_day = (_timestamp(calendar["last_sheet_at"])-timedelta(hours=4)).date().isoformat() if calendar.get("last_sheet_at") else ""
    days = sorted({s["learning_day"] for i, s in spans if i not in replaced and s.get("quality") != "unknown" and s.get("learning_day") and start_day < s["learning_day"] <= cutoff_day and activities.get(s.get("activity_id"), {}).get("course_id") == p["course_id"]})
    cycle = len(days)//6; reminder_key = digest({"since": calendar.get("last_sheet_at"), "cycle": cycle})
    status = "candidate" if len(new_segments) >= 3 and eligible and p.get("related_segment_id") in new_segments else "reminder" if aged and cycle > 0 and reminder_key not in calendar["reminded_windows"] else "no_window"
    data = {"course_id": p["course_id"], "as_of": p["as_of"], "status": status, "completed_segment_ids": sorted(i for i, _ in segments), "new_segment_ids": sorted(new_segments), "learning_dates": days, "eligible_mistake_ids": eligible if status == "candidate" else [], "related_segment_id": p.get("related_segment_id"), "requires_related_closure": status != "candidate"}
    if status == "reminder": calendar["reminded_windows"].append(reminder_key)
    return [put("aged_window", p["window_id"], data), put("aged_calendar", p["course_id"], calendar)]


def _retest_plan(state, request, p):
    fields(p, "plan_id", "session_id", "as_of", "seed")
    _teacher(request); _new(state, "retest_plan", p["plan_id"])
    session, activity, course = _context(state, request, p["session_id"])
    as_of = _timestamp(p["as_of"]); rng = random.Random(str(p["seed"]))
    due = []; aged = []
    for ident, mistake in _objects(state, "mistake"):
        if mistake.get("course_id") != activity["course_id"] or mistake.get("migration_requires_reconciliation"): continue
        last = mistake.get("retests", [])[-1] if mistake.get("retests") else None
        if not _legacy_retest_due(state, mistake, (as_of-timedelta(hours=4)).date().isoformat()): continue
        if last and (last["session_id"] == p["session_id"] or (as_of-_timestamp(last["happened_at"])).total_seconds() < 3*86400): continue
        if mistake["status"] == "active": due.append((ident, last and last["result"] == "wrong"))
        elif mistake["status"] == "aged": aged.append(ident)
    rng.shuffle(due); due.sort(key=lambda x: not x[1]); rng.shuffle(aged)
    completed = [(i, a) for i, a in _objects(state, "activity") if a.get("course_id") == activity["course_id"] and a.get("status") == "completed"]
    completed.sort(key=lambda x: version(state, "activity", x[0]), reverse=True)
    recent_ids = {i for i, _ in completed[:4]}; far_ids = {i for i, _ in completed[5:]}
    candidates = [(i, c) for i, c in _objects(state, "checkpoint") if c.get("status") == "confirmed"]
    recent = [i for i, c in candidates if c.get("activity_id") in recent_ids]
    far = [i for i, c in candidates if c.get("activity_id") in far_ids]
    rng.shuffle(recent); rng.shuffle(far)
    slots = ([{"kind": "coverage_recent", "checkpoint_id": recent[0]}] if recent else []) + ([{"kind": "coverage_far", "checkpoint_id": far[0]}] if far else [])
    slots += [{"kind": "active_mistake", "mistake_id": i} for i, _ in due[:8]]
    slots += [{"kind": "aged", "mistake_id": aged[0]}] if aged else []
    return [put("retest_plan", p["plan_id"], {"session_id": p["session_id"], "session_ids": [p["session_id"]], "course_id": activity["course_id"], "as_of": p["as_of"], "seed": str(p["seed"]), "slots": slots, "status": "pending" if slots else "complete", "missing_coverage": [k for k, found in (("recent", recent), ("far", far)) if not found], "results": []})]


def _retest_progress(state, request, p, action):
    fields(p, "plan_id")
    plan = _read(state, request, "retest_plan", p["plan_id"])
    require(plan["status"] != "complete", "RETEST_COMPLETE", "The completed check remains historical.")
    if action == "retest.pause":
        student = _student_choice(request, {"分两段", "暂停抽查", "split", "pause checks"})
        require(plan["status"] == "pending", "RETEST_STATE", "Only a pending check can pause.")
        plan.update(status="paused", pause_decision=student)
    elif action == "retest.resume":
        fields(p, "session_id")
        student = _student_choice(request, {"继续抽查", "resume checks"})
        _, activity, _ = _context(state, request, p["session_id"])
        require(plan["status"] == "paused" and activity["course_id"] == plan["course_id"], "RETEST_STATE", "Resume the remaining slots in the same course.")
        plan.update(status="pending", resume_decision=student)
        if p["session_id"] not in plan["session_ids"]: plan["session_ids"].append(p["session_id"])
    else:
        fields(p, "slot_index", "review_id", "problem_id")
        _teacher(request)
        index = p["slot_index"]
        require(plan["status"] == "pending" and type(index) is int and 0 <= index < len(plan["slots"]), "RETEST_SLOT", "Name an unfinished slot in a pending plan.")
        require(not any(x["slot_index"] == index or (x["review_id"], x["problem_id"]) == (p["review_id"], p["problem_id"]) for x in plan["results"]), "RETEST_DUPLICATE", "A result cannot fill the same slot or two slots twice.")
        review = _read(state, request, "review", p["review_id"])
        require(not review.get("history_only") and not any(r.get("supersedes") == p["review_id"] for _, r in _objects(state, "review")), "REVIEW_SUPERSEDED", "Use a current reproducible judgment.")
        attempt = _read(state, request, "attempt", review["attempt_id"])
        require(attempt.get("session_id") in plan["session_ids"], "RETEST_SESSION", "The actual answer must belong to a session running these slots.")
        _, activity, _ = _context(state, request, attempt["session_id"])
        require(activity["course_id"] == plan["course_id"], "RETEST_COURSE", "A result belongs to the course being checked.")
        ratings = [x for x in review["ratings"] if x["problem_id"] == p["problem_id"]]
        require(len(ratings) == 1, "RETEST_PROBLEM", "Use the actually reviewed problem.")
        rating = ratings[0]; slot = plan["slots"][index]
        if slot["kind"] in {"active_mistake", "aged"}:
            mistake = _read(state, request, "mistake", slot["mistake_id"])
            require(any(x["review_id"] == p["review_id"] and x["problem_id"] == p["problem_id"] for x in mistake["retests"]), "RETEST_NOT_RECORDED", "Formal mistake validation precedes slot consumption.")
        else:
            exercise = _read(state, request, "exercise", attempt["activity_id"])
            problem = exercise["problems"][p["problem_id"]]
            require(slot["checkpoint_id"] in problem.get("coverage_checkpoint_ids", []), "RETEST_COVERAGE_BINDING", "The probe must be bound to this checkpoint before the answer.")
            if rating["verdict"] in {"incorrect", "partial"} and rating["evidence_class"] != "polluted":
                fields(p, "mistake_id"); mistake = _read(state, request, "mistake", p["mistake_id"])
                references = [{"review_id": mistake.get("review_id"), "problem_id": mistake.get("problem_id")}]+mistake.get("recurrences", [])
                require(any(x["review_id"] == p["review_id"] and x["problem_id"] == p["problem_id"] for x in references), "RETEST_ERROR_NOT_RECOVERED", "Recover the observed coverage error under its course knowledge key.")
        plan["results"].append({"slot_index": index, "review_id": p["review_id"], "problem_id": p["problem_id"], "rating": deepcopy(rating)})
        if len(plan["results"]) == len(plan["slots"]): plan["status"] = "complete"
    plan["pending_slots"] = [i for i in range(len(plan["slots"])) if not any(x["slot_index"] == i for x in plan["results"])]
    return [put("retest_plan", p["plan_id"], plan)]


def _timestamp(value):
    try: result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError): raise DomainError("INVALID_TIME", "Use an ISO timestamp with timezone.")
    require(result.tzinfo is not None, "INVALID_TIME", "A timezone is required.")
    return result


def _exam_parameters(state, request):
    profile = _read(state, request, "student", "current")
    supplied = profile.get("exam_parameters", {})
    require(isinstance(supplied, dict), "EXAM_PARAMETERS", "Student examination parameters must be an object.")
    params = {"countries": ["CN", "JP", "SG", "GB", "FR", "CH", "US"], "max_subject_rank": 30, "min_source_year": 2018,
              "time_multipliers": {"quiz": 2, "final": 1.2, "retake1": 1.5, "retake2": 1.5}, "pass_percent": {"quiz": 60, "final": 60, "retake1": 60, "retake2": 50}, "review_units": 2, "paper_weight": .7}
    require(set(supplied) <= set(params), "EXAM_PARAMETERS", "Unknown examination parameters are not silently interpreted.")
    for name, value in supplied.items():
        if name in {"time_multipliers", "pass_percent"}:
            require(isinstance(value, dict) and set(value) <= set(params[name]), "EXAM_PARAMETERS", "Unknown examination stage parameters.")
            params[name].update(value)
        else: params[name] = deepcopy(value)
    _list(params["countries"], "source countries")
    require(all(isinstance(x, str) and len(x) == 2 for x in params["countries"]), "EXAM_PARAMETERS", "Countries use explicit ISO alpha-2 identifiers.")
    require(type(params["max_subject_rank"]) is int and params["max_subject_rank"] > 0 and type(params["min_source_year"]) is int, "EXAM_PARAMETERS", "Source year/ranking parameters must be integers.")
    require(type(params["review_units"]) is int and params["review_units"] in {0, 1, 2}, "EXAM_PARAMETERS", "Choose zero, one or two review units.")
    for value in params["time_multipliers"].values(): _number(value, "time multiplier", .01)
    for value in params["pass_percent"].values():
        _number(value, "pass percentage"); require(value <= 100, "EXAM_PARAMETERS", "Pass percentage is at most 100.")
    _number(params["paper_weight"], "paper weight"); require(params["paper_weight"] <= 1, "EXAM_PARAMETERS", "Paper weight is at most one.")
    return params


def _exam_clock(state, request, group_id, course_id, as_of, claimed_cycle=None):
    """Derive triggers from authoritative learning records, never a caller's cycle."""
    # The clock depends on this group's actual calendar. A legacy summary
    # flag about capacity or closing thresholds does not invalidate that data.
    group = get(state, "group", group_id)
    require(request.get("expected", {}).get(key("group", group_id)) == version(state, "group", group_id),
            "STALE_OBJECT", f"Expected current version of group/{group_id}")
    require(group.get("status") == "active" and course_id in group.get("members", []), "EXAM_GROUP", "Use an active group containing the course.")
    now = _timestamp(as_of)
    cutoff = (now - timedelta(hours=4)).date().isoformat()
    calendar = group.get("calendar", {})
    if group.get("container_mode") == "progress":
        interval = calendar.get("exam_keystones_per_bank_build")
        require(type(interval) is int and interval > 0, "EXAM_CALENDAR_PENDING", "Configure the explicit progress bank interval.")
        completed = len(set(group.get("completed_keystone_ids", [])))
        cycle = completed // interval
        result = {"mode": "progress", "cycle": cycle, "completed_keystones": completed, "bank_interval": interval, "as_of": as_of}
    else:
        require(group.get("container_mode") == "schedule", "EXAM_CALENDAR_PENDING", "Declare the examination container mode.")
        anchor = calendar.get("cycle_anchor_learning_day")
        length = calendar.get("cycle_length_learning_days")
        require(isinstance(anchor, str) and type(length) is int and length > 0, "EXAM_CALENDAR_PENDING", "Configure the recorded cycle anchor and learning-date count; do not infer them.")
        try: require(datetime.strptime(anchor, "%Y-%m-%d").date().isoformat() == anchor, "EXAM_CALENDAR_PENDING", "Invalid learning-day anchor.")
        except ValueError as exc: raise DomainError("EXAM_CALENDAR_PENDING", "Invalid learning-day anchor.") from exc
        spans = _objects(state, "timespan")
        replaced = {x["corrects"] for _, x in spans if x.get("corrects")}
        activities = {i: a for i, a in _objects(state, "activity")}
        actual = []
        for sid, span in spans:
            if sid in replaced or span.get("quality") == "unknown" or not span.get("learning_day"): continue
            activity = activities.get(span.get("activity_id"), {})
            day = span["learning_day"]
            if activity.get("course_id") in group["members"] and anchor <= day <= cutoff:
                _read(state, request, "timespan", sid); _read(state, request, "activity", span["activity_id"])
                actual.append((sid, day))
        days = sorted({day for _, day in actual})
        require(bool(days), "EXAM_CALENDAR_PENDING", "No actual learning date exists after the recorded anchor.")
        cycle = (len(days)-1)//length+1
        result = {"mode": "schedule", "cycle": cycle, "cycle_length_learning_days": length, "learning_date_in_cycle": (len(days)-1)%length+1, "learning_dates": days, "timespan_ids": sorted(sid for sid, _ in actual), "anchor": anchor, "as_of": as_of}
    if claimed_cycle is not None:
        require(type(claimed_cycle) is int and claimed_cycle == cycle, "EXAM_CYCLE_MISMATCH", "The supplied cycle differs from actual learning progress.")
    return result, group


def _exam_bank(state, request, p, action):
    fields(p, "bank_id")
    teacher = _teacher(request)
    if action in {"exam_bank.register", "exam_bank.import"}:
        fields(p, "group_id", "cycle", "seed", "imported_at", "papers")
        require(type(p["cycle"]) is int and p["cycle"] > 0, "BANK_CYCLE", "A positive library batch cycle is required.")
        params = _exam_parameters(state, request)
        _timestamp(p["imported_at"]); _text(str(p["seed"]), "seed")
        if action == "exam_bank.register":
            fields(p, "course_id"); _new(state, "exam_bank", p["bank_id"])
            _read(state, request, "course", p["course_id"])
            bank = {"course_id": p["course_id"], "papers": {}, "problems": {}, "batches": [], "exposures": [], "used_papers": [], "status": "building"}
        else:
            bank = _read(state, request, "exam_bank", p["bank_id"])
            require(bank["status"] == "building", "BANK_FROZEN", "The assessment pool is frozen; import into a new bank for a new enrollment.")
            require(p["cycle"] > max((x["cycle"] for x in bank["batches"]), default=0), "BANK_CYCLE", "Library batches advance in cycle order.")
        trigger, group = _exam_clock(state, request, p["group_id"], bank["course_id"], p["imported_at"], p["cycle"])
        if trigger["mode"] == "schedule":
            cycles = group["calendar"].get("exam_bank_build_cycles")
            require(isinstance(cycles, list) and cycles and all(type(c) is int and c > 0 for c in cycles), "EXAM_CALENDAR_PENDING", "Configure the agreed examination bank cycles.")
            require(trigger["cycle"] in cycles and trigger["learning_date_in_cycle"] == trigger["cycle_length_learning_days"], "BANK_CYCLE", "Build on the final learning date of an agreed bank cycle.")
        else:
            require(trigger["cycle"] > 0 and trigger["completed_keystones"] % trigger["bank_interval"] == 0, "BANK_PROGRESS_TRIGGER", "Build only at a completed-keystone bank interval.")
        papers = deepcopy(_list(p["papers"], "papers")); paper_ids = [x["paper_id"] for x in papers]
        require(len(paper_ids) == len(set(paper_ids)) and not set(paper_ids) & set(bank["papers"]), "PAPER_IDENTITY", "Paper identities cannot be reused.")
        eligible = []
        for paper in papers:
            fields(paper, "paper_id", "source_id", "school", "country", "year", "language", "ranking_reference", "subject_rank", "level", "total_minutes", "original_question_count", "problems")
            require(type(paper["year"]) is int and paper["year"] >= params["min_source_year"], "EXAM_SOURCE_YEAR", "Use papers admitted by the frozen student source-year parameter.")
            require(paper["country"] in params["countries"] and type(paper["subject_rank"]) is int and 1 <= paper["subject_rank"] <= params["max_subject_rank"], "EXAM_SOURCE_POLICY", "The source must satisfy the student's recorded country/ranking parameters.")
            require(paper["language"] in {"zh", "en"} or paper.get("official_english_or_bilingual") is True, "EXAM_LANGUAGE", "Use an original Chinese/English paper or its official English/bilingual edition; model translation is not an exam source.")
            _text(paper["ranking_reference"], "ranking reference"); _number(paper["total_minutes"], "source duration", 1)
            require(type(paper["original_question_count"]) is int and paper["original_question_count"] > 0, "SOURCE_QUESTION_COUNT", "The original paper question count calibrates timing.")
            source = get(state, "source", paper["source_id"])
            require(source.get("purpose") == "exam_paper" and source["format"] == "pdf" and bank["course_id"] in source["course_ids"], "EXAM_SOURCE_KIND", "An exam needs a distinct original examination PDF, not a textbook exercise.")
            require(not any(get(state, "source", x["source_id"])["content_sha256"] == source["content_sha256"] for x in bank["papers"].values()), "PAPER_SOURCE_REUSE", "One original source cannot acquire fresh pool identity under an alias.")
            for other_id, other in _objects(state, "exam_bank"):
                require(other_id == p["bank_id"] or not any(get(state, "source", x["source_id"])["content_sha256"] == source["content_sha256"] for x in other["papers"].values()), "PAPER_SOURCE_REUSE", "An existing paper must retain its pool and exposure identity.")
            if paper.get("solution_source_id"):
                solution = get(state, "source", paper["solution_source_id"])
                require(solution.get("purpose") == "exam_solution" and solution.get("official") is True and bank["course_id"] in solution["course_ids"], "OFFICIAL_SOLUTION_REQUIRED", "Use the source institution's attributed official solution.")
                eligible.append(paper["paper_id"])
            questions = _list(paper.pop("problems"), "paper problems")
            require(len(questions) <= paper["original_question_count"], "SOURCE_QUESTION_COUNT", "Imported questions cannot exceed the declared original question count.")
            for q in questions:
                fields(q, "problem_id", "page_id", "source_excerpt", "locator", "kind", "nodes", "dependencies", "difficulty_signals")
                require(q["problem_id"] not in bank["problems"], "PROBLEM_IDENTITY", "Question identities cannot be reused.")
                page = _page_current(state, request, q["page_id"])
                require(page["source_id"] == paper["source_id"] and bool(q["source_excerpt"]) and q["source_excerpt"] in page["verified_text"], "EXAM_PROBLEM_SOURCE", "Keep exact original question references.")
                require(q["kind"] in {"proof", "calculation", "other"}, "EXAM_PROBLEM_KIND", "Identify proof, calculation or other.")
                _list(q["nodes"], "nodes"); _list(q["dependencies"], "dependencies", False)
                signals = q["difficulty_signals"]
                require(isinstance(signals, list) and len(signals) == 3 and all(type(x) is int and x in {0, 1, 2} for x in signals), "DIFFICULTY_SIGNALS", "Freeze three difficulty signals (0 foundation, 1 standard, 2 honors).")
                if paper.get("solution_source_id"):
                    fields(q, "solution_page_id", "solution_locator")
                    require(_page_current(state, request, q["solution_page_id"])["source_id"] == paper["solution_source_id"], "OFFICIAL_SOLUTION_REQUIRED", "Answer location must point into the official solution.")
                q.update(paper_id=paper["paper_id"], difficulty=sorted(signals)[1], imported_cycle=p["cycle"])
                bank["problems"][q["problem_id"]] = q
            paper.update(imported_cycle=p["cycle"], imported_at=p["imported_at"], provenance=teacher)
            bank["papers"][paper["paper_id"]] = paper
        random.Random(str(p["seed"])).shuffle(eligible)
        assessment = set(eligible[:int(len(eligible)*0.3+0.5)])
        for pid in paper_ids:
            bank["papers"][pid]["pool"] = "assessment" if pid in assessment else "practice"
            bank["papers"][pid]["initial_pool"] = bank["papers"][pid]["pool"]
        bank["batches"].append({"cycle": p["cycle"], "seed": str(p["seed"]), "paper_ids": paper_ids, "imported_at": p["imported_at"], "parameters": params, "group_id": p["group_id"], "trigger": trigger})
        return [put("exam_bank", p["bank_id"], bank)]
    bank = _read(state, request, "exam_bank", p["bank_id"])
    if action == "exam_bank.freeze":
        fields(p, "cycle", "group_id", "as_of")
        trigger, group = _exam_clock(state, request, p["group_id"], bank["course_id"], p["as_of"], p["cycle"])
        cycles = group["calendar"].get("exam_bank_build_cycles")
        require((trigger["mode"] == "schedule" and isinstance(cycles, list) and cycles and trigger["cycle"] > max(cycles)) or (trigger["mode"] == "progress" and set(group["completed_keystone_ids"]) == set(group["keystone_ids"])), "FREEZE_CYCLE", "Freeze after the last agreed bank cycle or after all progress-mode keystones.")
        require(bank["status"] == "building", "BANK_FROZEN", "Pool is already frozen.")
        bank.update(status="frozen", frozen_cycle=p["cycle"], frozen_by=teacher, freeze_trigger=trigger)
    else:
        fields(p, "problem_id", "reason", "reference")
        require(p["problem_id"] in bank["problems"], "PROBLEM_MISSING", "Unknown bank problem.")
        bank["exposures"].append({"problem_id": p["problem_id"], "reason": p["reason"], "reference": p["reference"], "actor": teacher})
    return [put("exam_bank", p["bank_id"], bank)]


def _exam_scope(state, request, bank, group_id, exam_type):
    # Validate the exact scope below; unrelated migration summaries do not
    # override a subsequently configured, version-bound examination scope.
    group = get(state, "group", group_id)
    require(request.get("expected", {}).get(key("group", group_id)) == version(state, "group", group_id),
            "STALE_OBJECT", f"Expected current version of group/{group_id}")
    require(group.get("status") == "active" and bank["course_id"] in group["members"], "EXAM_GROUP", "Use the actual active course group.")
    if group.get("container_mode") == "schedule":
        # Schedule containers have no progress-keystone anchor. Preserve the
        # granularity of actual confirmed course records, never parent mastery
        # inferred from a child or knowledge inferred from a bank's questions.
        course_id = bank["course_id"]
        activities = dict(_objects(state, "activity"))
        checkpoints = {}
        for ident, checkpoint in _objects(state, "checkpoint"):
            activity = activities.get(checkpoint.get("activity_id"))
            owner = checkpoint.get("course_id") or (activity or {}).get("course_id")
            if owner != course_id or checkpoint.get("status") != "confirmed":
                continue
            if activity:
                require(activity["course_id"] == course_id, "EXAM_SCOPE_COURSE", "Confirmed scope and activity must belong to the examined course.")
                _read(state, request, "activity", checkpoint["activity_id"])
            checkpoints[ident] = _read(state, request, "checkpoint", ident)
        nodes = set(checkpoints)
        segment_refs = []
        structure = None
        for ident, segment in _objects(state, "learning_segment"):
            if segment.get("course_id") != course_id:
                continue
            segment = _read(state, request, "learning_segment", ident)
            if structure is None:
                structure = _read(state, request, "learning_structure", course_id)
            planned = next((item for item in structure["segments"] if item["segment_id"] == segment["segment_id"]), None)
            require(planned is not None and all(segment.get(field) == planned[field] for field in ("checkpoint_ids", "knowledge_keys")),
                    "EXAM_SCOPE_SEGMENT", "Completed segment must retain its actual course mapping.")
            require(bool(segment["checkpoint_ids"]) and set(segment["checkpoint_ids"]) <= set(checkpoints),
                    "EXAM_SCOPE_SEGMENT", "Every completed-segment checkpoint must still be confirmed for this course.")
            nodes.difference_update(segment["checkpoint_ids"])
            nodes.update(segment["knowledge_keys"])
            segment_refs.append({"id": ident, "version": version(state, "learning_segment", ident)})
        require(bool(nodes), "EMPTY_EXAM_SCOPE", "The course has no recorded confirmed learning scope.")
        snapshot = {"container_mode": "schedule", "course_id": course_id, "learned_node_ids": sorted(nodes),
                    "checkpoint_refs": [{"id": ident, "version": version(state, "checkpoint", ident)} for ident in sorted(checkpoints)],
                    "segment_refs": sorted(segment_refs, key=lambda item: item["id"]),
                    "structure_version": version(state, "learning_structure", course_id) if structure else None}
        return snapshot, nodes
    fields(group, "container_mode", "keystone_ids", "completed_keystone_ids", "keystone_total_frozen", "keystone_change_log")
    require(type(group.get("keystone_total_initial")) is int, "KEYSTONE_RECONCILIATION", "The original scope anchor is unknown; reconcile migration instead of inferring it.")
    ids = group["keystone_ids"]; done = group["completed_keystone_ids"]
    require(group["container_mode"] in {"schedule", "progress"} and len(ids) == len(set(ids)) and set(done) <= set(ids), "EXAM_SCOPE", "Malformed authoritative group scope.")
    ledger = group.get("keystone_scope_ledger", [])
    require(group["keystone_total_frozen"] == len(ids)+sum(len(x["removed"]) for x in ledger), "KEYSTONE_RECONCILIATION", "The retained anchor equals current keystones plus explicitly transferred removals; additions are already included in that anchor.")
    require(group["keystone_total_initial"]+sum(x["delta"] for x in group["keystone_change_log"])+sum(len(x["added"]) for x in ledger) == group["keystone_total_frozen"], "KEYSTONE_RECONCILIATION", "Replay the initial anchor and every explicit scope addition.")
    if exam_type != "quiz" and group["container_mode"] == "progress":
        require(set(done) == set(ids), "EXAM_PROGRESS_GATE", "Progress mode requires every frozen current keystone before a final examination.")
    required = done if group["container_mode"] == "schedule" or exam_type == "quiz" else ids
    require(bool(required), "EMPTY_EXAM_SCOPE", "The group has no completed examination scope.")
    snapshot = {k: deepcopy(group[k]) for k in ("container_mode", "keystone_ids", "completed_keystone_ids", "keystone_total_initial", "keystone_total_frozen", "keystone_change_log")}
    snapshot["keystone_scope_ledger"] = deepcopy(ledger)
    return snapshot, set(required)


def _selection(state, request, p):
    fields(p, "selection_id", "bank_id", "group_id", "exam_type", "cycle", "seed", "as_of")
    _teacher(request); _new(state, "exam_selection", p["selection_id"])
    bank = _read(state, request, "exam_bank", p["bank_id"])
    params = _exam_parameters(state, request)
    require(p["exam_type"] in {"quiz", "final", "retake1", "retake2"}, "EXAM_TYPE", "Unknown examination stage.")
    trigger, group = _exam_clock(state, request, p["group_id"], bank["course_id"], p["as_of"], p["cycle"])
    if trigger["mode"] == "schedule":
        if p["exam_type"] == "quiz": require(trigger["cycle"] in group["calendar"].get("exam_quiz_cycles", []), "EXAM_SCHEDULE", "A quiz belongs to an explicitly configured quiz cycle.")
        elif p["exam_type"] == "final":
            final_cycle = group.get("calendar", {}).get("exam_final_cycle")
            require(type(final_cycle) is int and trigger["cycle"] >= final_cycle, "EXAM_CALENDAR_PENDING", "Reach the explicitly configured final calendar node.")
    elif p["exam_type"] == "quiz":
        interval = group.get("calendar", {}).get("exam_keystones_per_quiz")
        require(type(interval) is int and interval > 0 and trigger["completed_keystones"] > 0 and trigger["completed_keystones"] % interval == 0, "EXAM_PROGRESS_TRIGGER", "A quiz needs its actual completed-keystone interval.")
    if p["exam_type"] != "quiz": require(bank["status"] == "frozen", "BANK_NOT_FROZEN", "Freeze the assessment pool before final or retake selection.")
    snapshot, nodes = _exam_scope(state, request, bank, p["group_id"], p["exam_type"])
    required_pool = "practice" if p["exam_type"] == "quiz" else "assessment"
    exposed = {x["problem_id"] for x in bank["exposures"]}; rejected = {}; eligible = []
    exposed_papers = {bank["problems"][pid]["paper_id"] for pid in exposed}
    used_questions = {pid for _, exam in _objects(state, "exam") if exam.get("bank_id") == p["bank_id"] for pid in exam["problem_ids"]}
    for pid, question in bank["problems"].items():
        paper = bank["papers"][question["paper_id"]]; reasons = []
        if paper["pool"] != required_pool: reasons.append("wrong_pool")
        if paper["imported_cycle"] >= p["cycle"]: reasons.append("not_cooled")
        if not paper.get("solution_source_id"): reasons.append("no_official_solution")
        if not set(question["nodes"]) <= nodes: reasons.append("untaught_node")
        if not set(question["dependencies"]) <= nodes: reasons.append("untaught_dependency")
        if pid in exposed or pid in used_questions or question["paper_id"] in exposed_papers or question["paper_id"] in bank["used_papers"]: reasons.append("exposed_or_used")
        if reasons: rejected[pid] = reasons
        else:
            _page_current(state, request, question["page_id"])
            _page_current(state, request, question["solution_page_id"])
            eligible.append(pid)
    rng = random.Random(str(p["seed"])); rng.shuffle(eligible)
    if p["exam_type"] == "quiz":
        require(len(eligible) >= 2, "EXAM_BANK_SHORTAGE", "Fewer than two eligible source questions: postpone and replenish the bank.")
        chosen = eligible[:min(3, len(eligible))]
    else:
        # Deterministic seed order with bounded search. No caller-selected rescue questions.
        chosen = None
        for count in range(8, 11):
            if len(eligible) < count: continue
            for _ in range(3000):
                candidate = rng.sample(eligible, count); qs = [bank["problems"][i] for i in candidate]
                schools = [bank["papers"][q["paper_id"]]["school"] for q in qs]
                countries = {bank["papers"][q["paper_id"]]["country"] for q in qs}
                coverage = set().union(*(set(q["nodes"]) for q in qs))
                if (nodes <= coverage and sum(q["kind"] == "proof" for q in qs) >= math.ceil(count*.6)
                    and sum(q["kind"] == "calculation" for q in qs) <= math.floor(count*.4)
                    and len(set(schools)) >= 3 and len(countries) >= 2 and max(schools.count(x) for x in set(schools)) <= 3
                    and sum(q["difficulty"] == 2 for q in qs) >= math.ceil(count*.5)):
                    chosen = candidate; break
            if chosen: break
        require(chosen is not None, "EXAM_BANK_SHORTAGE", "No compliant seeded selection was found within the disclosed 3000 trials per size; replenish or try another public seed without relaxing constraints.")
    multiplier = params["time_multipliers"][p["exam_type"]]
    duration = sum(bank["papers"][bank["problems"][i]["paper_id"]]["total_minutes"] / bank["papers"][bank["problems"][i]["paper_id"]]["original_question_count"] for i in chosen) * multiplier
    data = {k: deepcopy(p[k]) for k in ("bank_id", "group_id", "exam_type", "cycle", "seed")}
    course = _read(state, request, "course", bank["course_id"])
    data.update(problem_ids=chosen, rejected=rejected, scope_snapshot=snapshot, trigger=trigger, parameters=params, process_criterion_id=course.get("process_criterion_id"), deferred_node_ids=sorted(set(snapshot.get("keystone_ids", []))-nodes), duration_minutes=duration,
                source_references=[{k: bank["problems"][i].get(k) for k in ("paper_id", "page_id", "locator", "solution_page_id", "solution_locator")} for i in chosen], selection_algorithm="python_random_seeded_bounded_v1")
    return [put("exam_selection", p["selection_id"], data)]


def _exam(state, request, p, action):
    fields(p, "exam_id")
    if action == "exam.create":
        fields(p, "activity_id", "selection_id", "criterion_id", "started_at")
        _teacher(request); _new(state, "exam", p["exam_id"])
        selection = get(state, "exam_selection", p["selection_id"])
        bank = _read(state, request, "exam_bank", selection["bank_id"])
        trigger, _ = _exam_clock(state, request, selection["group_id"], bank["course_id"], p["started_at"], selection["cycle"])
        require({k: v for k, v in trigger.items() if k != "as_of"} == {k: v for k, v in selection["trigger"].items() if k != "as_of"}, "EXAM_TRIGGER_CHANGED", "Recorded learning progress changed after selection; select again.")
        activity, course = _course_activity(state, request, p["activity_id"])
        require(activity["course_id"] == bank["course_id"] and activity["status"] == "ongoing" and course["status"] == "ongoing" and not course.get("paused"), "EXAM_ACTIVITY", "The examination needs an ongoing activity in an active course.")
        require(_exam_parameters(state, request) == selection["parameters"] and course.get("process_criterion_id") == selection.get("process_criterion_id"), "EXAM_PARAMETERS_CHANGED", "Parameters or process rubric changed after selection; select again.")
        if selection["exam_type"] != "quiz" and selection["parameters"]["paper_weight"] < 1:
            fields(selection, "process_criterion_id")
            get(state, "criterion", selection["process_criterion_id"])
        snapshot, _ = _exam_scope(state, request, bank, selection["group_id"], selection["exam_type"])
        require(snapshot == selection["scope_snapshot"], "EXAM_SCOPE_CHANGED", "The authoritative scope changed after selection; select again.")
        criterion = get(state, "criterion", p["criterion_id"])
        ids = selection["problem_ids"]
        require(criterion["target_kind"] == "exam_bank" and criterion["target_id"] == selection["bank_id"] and set(ids) <= set(criterion["problem_ids"]) and bool(criterion.get("scoring_points")), "EXAM_CRITERION", "Freeze official scoring points for the independently selected questions before starting.")
        started = _timestamp(p["started_at"])
        selected_papers = {bank["problems"][pid]["paper_id"] for pid in ids}
        exposed_papers = {bank["problems"][x["problem_id"]]["paper_id"] for x in bank["exposures"]}
        require(not selected_papers & (set(bank["used_papers"]) | exposed_papers), "EXAM_EXPOSURE", "A selected paper was used or exposed after selection.")
        require(all(started > _timestamp(bank["papers"][pid]["imported_at"]) for pid in selected_papers), "EXAM_COOLDOWN", "An examination cannot precede its source import.")
        for _, prior in _objects(state, "exam"):
            require(not (prior.get("bank_id") == selection["bank_id"] and set(prior.get("problem_ids", [])) & set(ids)), "EXAM_EXPOSURE", "Already examined questions cannot become a fresh examination.")
        if selection["exam_type"].startswith("retake"):
            fields(p, "previous_exam_id")
            previous = _read(state, request, "exam", p["previous_exam_id"])
            required_stage = "final" if selection["exam_type"] == "retake1" else "retake1"
            require(previous.get("exam_type") == required_stage and previous.get("bank_id") == selection["bank_id"] and previous.get("settlement") == "retake_ready", "RETAKE_GATE", "Settle the preceding failure and finish its review unit before opening the next retake.")
        data = {k: deepcopy(p[k]) for k in ("activity_id", "selection_id", "criterion_id", "started_at")}
        data.update({k: deepcopy(selection[k]) for k in ("bank_id", "group_id", "exam_type", "problem_ids", "duration_minutes", "scope_snapshot", "source_references", "parameters", "process_criterion_id")})
        data["course_id"] = bank["course_id"]
        data.update(status="open", isolated=True, flags={}, reminders=[], previous_exam_id=p.get("previous_exam_id"), opening_statement="考试不为制造痛苦，选择学习的人，应知自身真实。")
        bank["exposures"].extend({"problem_id": pid, "reason": "exam_started", "reference": p["exam_id"], "actor": deepcopy(request["actor"])} for pid in ids)
        return [put("exam", p["exam_id"], data), put("exam_bank", selection["bank_id"], bank)]
    exam = _read(state, request, "exam", p["exam_id"])
    if action in {"exam.reinforcement.configure", "exam.reinforcement.record"}:
        reinforcement = _read(state, request, "exam_reinforcement", p["exam_id"])
        if action == "exam.reinforcement.configure":
            fields(p, "activity_ids", "purpose")
            student = require_student(request); _text(p["purpose"], "reinforcement purpose")
            require(reinforcement["status"] == "planned", "REINFORCEMENT_STATE", "The reinforcement mapping is already frozen.")
            ids = _list(p["activity_ids"], "reinforcement activities")
            require(len(ids) == len(set(ids)), "REINFORCEMENT_ACTIVITIES", "Do not repeat activity references.")
            for ident in ids:
                activity, _ = _course_activity(state, request, ident)
                require(activity["course_id"] == exam["course_id"], "REINFORCEMENT_COURSE", "Reinforcement stays in the examined course.")
            reinforcement.update(status="active", activity_ids=deepcopy(ids), purpose=p["purpose"], student=student)
        else:
            fields(p, "timespan_id", "evidence_refs"); _teacher(request)
            require(reinforcement["status"] == "active" and exam["status"] == "graded", "REINFORCEMENT_STATE", "Finish the examination and confirm the three-learning-date block first.")
            span = _read(state, request, "timespan", p["timespan_id"])
            require(span["activity_id"] in reinforcement["activity_ids"] and span.get("quality") != "unknown" and bool(span.get("learning_day")), "REINFORCEMENT_TIME", "Use an actual known learning-date record in the agreed activities.")
            require(not any(s.get("corrects") == p["timespan_id"] for _, s in _objects(state, "timespan")), "TIME_SUPERSEDED", "The learning span has been corrected.")
            exam_day = (_timestamp(exam["started_at"])-timedelta(hours=4)).date().isoformat()
            require(span["learning_day"] > exam_day and span["learning_day"] not in reinforcement["learning_dates"], "REINFORCEMENT_DATE", "Count three distinct learning dates after the examination.")
            refs = _list(p["evidence_refs"], "actual reinforcement evidence")
            used = set()
            for record in reinforcement["records"]:
                prior_span = _read(state, request, "timespan", record["timespan_id"])
                require(not any(s.get("corrects") == record["timespan_id"] for _, s in _objects(state, "timespan")), "TIME_SUPERSEDED", "An earlier reinforcement span was corrected; reconcile it before counting more learning dates.")
                require(prior_span.get("learning_day") in reinforcement["learning_dates"] and prior_span.get("quality") != "unknown", "REINFORCEMENT_DATE", "Prior learning dates must still have their actual current time evidence.")
                for prior_ref in record["evidence_refs"]:
                    identity, _ = _post_exam_learning_evidence(state, request, exam, prior_ref)
                    used.add(identity)
            for ref in refs:
                identity, evidence = _post_exam_learning_evidence(state, request, exam, ref)
                require(identity not in used, "REINFORCEMENT_EVIDENCE", "A corrected review of the same original answer is not new reinforcement learning.")
                used.add(identity)
                require(evidence.get("activity_id") == span["activity_id"], "REINFORCEMENT_EVIDENCE", "The evidence must belong to the timed activity.")
            reinforcement["learning_dates"].append(span["learning_day"])
            reinforcement["records"].append({"timespan_id": p["timespan_id"], "evidence_refs": deepcopy(refs), "actor": deepcopy(request["actor"])})
            if len(reinforcement["learning_dates"]) == 3: reinforcement["status"] = "complete"
        return [put("exam_reinforcement", p["exam_id"], reinforcement)]
    if action == "exam.process.record":
        fields(p, "criterion_id", "metrics")
        teacher = _teacher(request)
        require(not exam.get("settlement") and not exam.get("process_assessment"), "PROCESS_ASSESSMENT_STATE", "Preserve one process judgment under the rubric frozen before the exam.")
        require(p["criterion_id"] == exam.get("process_criterion_id"), "CRITERION_CHANGED", "Use the frozen course process rubric.")
        rubric = get(state, "criterion", p["criterion_id"])
        metrics = _list(p["metrics"], "metrics")
        require(len(metrics) == len(rubric["metric_ids"]) and {m["metric_id"] for m in metrics} == set(rubric["metric_ids"]), "PROCESS_METRICS", "Judge every frozen process metric exactly once.")
        for metric in metrics:
            fields(metric, "score", "rationale", "evidence_refs"); _number(metric["score"], "process score")
            require(metric["score"] <= rubric["max_scores"][metric["metric_id"]], "SCORE_RANGE", "Process score exceeds the frozen maximum.")
            for ref in _list(metric["evidence_refs"], "process evidence"):
                require(ref.get("kind") in {"review", "mistake", "checkpoint", "attempt", "completion"}, "PROCESS_EVIDENCE", "Process scoring must cite actual learning evidence.")
                evidence = _read(state, request, ref["kind"], ref["id"])
                if ref["kind"] == "review": evidence = get(state, "attempt", evidence["attempt_id"])
                cid = evidence.get("course_id")
                if not cid and evidence.get("activity_id"): cid = _read(state, request, "activity", evidence["activity_id"])["course_id"]
                require(cid == exam["course_id"], "PROCESS_EVIDENCE", "Process evidence belongs to this course.")
        percentage = sum(m["score"] for m in metrics)/sum(rubric["max_scores"].values())*100
        exam["process_assessment"] = {"criterion_id": p["criterion_id"], "metrics": deepcopy(metrics), "percent": percentage, "teacher": teacher}
        return [put("exam", p["exam_id"], exam)]
    if action == "exam.recover_mistakes":
        fields(p, "roots"); _teacher(request)
        require(exam["status"] == "graded" and not exam.get("settlement"), "EXAM_NOT_GRADED", "Recover actual graded errors before settlement.")
        review = get(state, "review", exam["review_id"])
        failed = {x["problem_id"] for x in review["ratings"] if x["verdict"] in {"incorrect", "partial"} and x["evidence_class"] != "polluted"}
        roots = _list(p["roots"], "roots", False)
        require(len(roots) == len(failed) and {x["problem_id"] for x in roots} == failed, "EXAM_ERROR_COVERAGE", "Recover each real incorrect/partial problem with its attributed root cause, excluding contamination.")
        working = deepcopy(state); merged = {}; links = {}
        for root in roots:
            fields(root, "mistake_id", "knowledge_key", "root_cause", "problem_id")
            payload = {**root, "review_id": exam["review_id"]}
            action_ = "mistake.recur" if get(working, "mistake", root["mistake_id"], False) else "mistake.record"
            local_request = {**request, "expected": {**request.get("expected", {}), **{name: working["objects"][name]["version"] for name in merged}}}
            effects = _mistake(working, local_request, payload, action_)
            for effect in effects:
                name = key(effect["kind"], effect["id"]); old = working["objects"].get(name)
                working["objects"][name] = {"kind": effect["kind"], "id": effect["id"], "version": old["version"] if old else state["revision"], "data": effect["data"]}; merged[name] = effect
            links[root["problem_id"]] = root["mistake_id"]
        exam["mistake_ids"] = links
        return list(merged.values()) + [put("exam", p["exam_id"], exam)]
    if action == "exam.submit":
        fields(p, "attempt_id", "answers", "submitted_at")
        student = require_student(request); _new(state, "attempt", p["attempt_id"])
        require(exam["status"] == "open", "EXAM_NOT_OPEN", "This exam already has a submission.")
        answers = _answers(p["answers"], exam["problem_ids"])
        require({x["problem_id"] for x in answers} == set(exam["problem_ids"]), "EXAM_SUBMISSION_COVERAGE", "Record every exam problem, including explicit blank answers.")
        seconds = (_timestamp(p["submitted_at"])-_timestamp(exam["started_at"])).total_seconds()
        require(seconds >= 0, "INVALID_TIME", "Submission cannot precede the exam start.")
        help_by_id = {pid: {"level": "none", "polluted": False, "evidence": []} for pid in exam["problem_ids"]}
        bank = _read(state, request, "exam_bank", exam["bank_id"])
        for exposure in bank["exposures"]:
            if not (exposure["reason"] == "exam_started" and exposure["reference"] == p["exam_id"]):
                for pid in help_by_id:
                    if bank["problems"][pid]["paper_id"] == bank["problems"][exposure["problem_id"]]["paper_id"]:
                        help_by_id[pid]["polluted"] = True
                        help_by_id[pid]["evidence"].append(exposure)
        for reminder in exam.get("reminders", []):
            if reminder["level"] in {"direction", "reference", "solution"}:
                item = help_by_id[reminder["problem_id"]]; item["level"] = reminder["level"]; item["evidence"].append(reminder)
        attempt = {"activity_id": exam["activity_id"], "exam_id": p["exam_id"], "answers": answers, "student": student, "criterion_id": exam["criterion_id"], "assistance": help_by_id, "hint_gate": "exam_isolation"}
        exam.update(status="submitted", attempt_id=p["attempt_id"], submitted_at=p["submitted_at"], timed_out=seconds > exam["duration_minutes"]*60)
        return [put("attempt", p["attempt_id"], attempt), put("exam", p["exam_id"], exam)]
    if action == "exam.reminder":
        fields(p, "problem_id", "level", "content", "student_request")
        _teacher(request)
        require(exam["status"] == "open" and p["problem_id"] in exam["problem_ids"], "EXAM_NOT_OPEN", "Reminders belong to an open examination question.")
        require(p["level"] in {"time", "clarification", "direction", "reference", "solution"}, "HINT_LEVEL", "Unknown examination reminder level.")
        decision = p["student_request"]; require(isinstance(decision, dict) and decision.get("role") == "student" and bool(decision.get("text")) and bool(decision.get("source")), "STUDENT_DECISION_REQUIRED", "Retain the attributed original request for an examination reminder.")
        exam["reminders"].append({k: deepcopy(p[k]) for k in ("problem_id", "level", "content", "student_request")})
        exam["reinforcement_required"] = len(exam["reminders"])/len(exam["problem_ids"]) > 1
        effects = [put("exam", p["exam_id"], exam)]
        if exam["reinforcement_required"] and not get(state, "exam_reinforcement", p["exam_id"], False):
            effects.append(put("exam_reinforcement", p["exam_id"], {"exam_id": p["exam_id"], "course_id": exam["course_id"], "status": "planned", "required_learning_dates": 3, "trigger": "mean_reminders_above_one", "learning_dates": [], "records": []}))
        return effects
    if action == "exam.self_assess":
        fields(p, "mapping", "statement")
        student = require_student(request, p["statement"])
        require(exam["status"] == "submitted" and "self_assessment" not in exam, "SELF_ASSESSMENT_STATE", "Record one original self-assessment after actual submission and before teacher judgment.")
        criterion = get(state, "criterion", exam["criterion_id"])
        points = {x["point_id"] for x in criterion["scoring_points"] if x["problem_id"] in exam["problem_ids"]}
        mapping = _list(p["mapping"], "mapping")
        require(len(mapping) == len(points) and {x["point_id"] for x in mapping} == points, "SELF_MAP_COVERAGE", "The student's own mapping must cover every frozen scoring point.")
        for x in mapping:
            require(x.get("judgment") in {"hit", "miss", "equivalent"}, "SELF_MAP_VALUE", "Use hit, miss or equivalent.")
            _text(x.get("answer_reference"), "student answer reference")
        exam["self_assessment"] = {"mapping": deepcopy(mapping), "student": student}
        return [put("exam", p["exam_id"], exam)]
    if action == "exam.flag.confirm":
        fields(p, "point_id", "flag_sha256", "decision", "explanation")
        student = require_student(request)
        require(exam["status"] == "flagged" and p["point_id"] in exam["flags"], "FLAG_STATE", "Only an actual unresolved scoring flag can be signed.")
        flag = exam["flags"][p["point_id"]]
        require(flag["status"] == "pending" and p["flag_sha256"] == digest(flag), "FLAG_CHANGED", "Sign the exact current scoring flag.")
        require(p["decision"] in {"accept", "reject"}, "UNBOUND_DECISION", "Decide whether this explained point earns credit.")
        if p["decision"] == "accept":
            student = _student_choice(request, ("accept", "同意", "认可", "计分"))
        # A rejection is a valid non-authorizing outcome; preserve its actual
        # words, including bare 'no', instead of treating them as missing consent.
        _text(p["explanation"], "discussion explanation")
        flag.update(status="resolved", decision=p["decision"], discussion=p["explanation"], student=student)
        if all(x["status"] == "resolved" for x in exam["flags"].values()): exam["status"] = "submitted"
        return [put("exam", p["exam_id"], exam)]
    if action in {"exam.settle", "exam.review.complete"}:
        _teacher(request)
        require(exam["status"] == "graded", "EXAM_NOT_GRADED", "A settled ledger requires a complete reproducible grade.")
        if action == "exam.review.complete":
            fields(p, "evidence", "student", "student_feeling", "dependency_diagnosis")
            require(exam.get("settlement") == "review_required", "REVIEW_UNIT_STATE", "No review unit is pending.")
            _list(p["evidence"], "review evidence"); _text(p["student_feeling"], "student feeling"); _text(p["dependency_diagnosis"], "dependency diagnosis")
            require_student({**request, "actor": p["student"]}, p["student_feeling"])
            for ref in p["evidence"]:
                _, evidence = _post_exam_learning_evidence(state, request, exam, ref)
                activity, _ = _course_activity(state, request, evidence["activity_id"])
                require(activity["course_id"] == exam["course_id"] and not evidence.get("exam_id"), "REVIEW_UNIT_EVIDENCE", "Use actual learning in this course, not another examination as its own review.")
            exam.update(settlement="retake_ready", review_completion={k: deepcopy(p[k]) for k in ("evidence", "student", "student_feeling", "dependency_diagnosis")})
        else:
            require(not exam.get("settlement"), "EXAM_ALREADY_SETTLED", "A historical settlement is not overwritten.")
            require(exam.get("passed") is not None, "UNCERTAIN_GRADE", "Resolve all scoring uncertainty before settlement.")
            review = get(state, "review", exam["review_id"])
            failed = {x["problem_id"] for x in review["ratings"] if x["verdict"] in {"incorrect", "partial"} and x["evidence_class"] != "polluted"}
            require(failed <= set(exam.get("mistake_ids", {})), "EXAM_ERRORS_UNRECOVERED", "Record knowledge-point root causes for actual errors before settling this ledger.")
            if exam.get("exam_type") != "quiz":
                weight = exam["parameters"]["paper_weight"]
                require(weight == 1 or bool(exam.get("process_assessment")), "PROCESS_ASSESSMENT_REQUIRED", "The final course grade needs its separately evidenced process component.")
                exam["overall_percent"] = exam["paper_percent"]*weight + exam.get("process_assessment", {}).get("percent", 0)*(1-weight)
            exam["settlement"] = "monitoring_only" if exam.get("exam_type") == "quiz" else "settled" if exam["passed"] else "failed_final" if exam.get("exam_type") == "retake2" else "review_required"
            required_units = 1 if exam.get("exam_type") == "final" else 2
            if exam["settlement"] == "review_required" and exam["parameters"]["review_units"] < required_units: exam["settlement"] = "retake_ready"
            exam["next_action"] = {"review_required": "review_unit_1" if exam.get("exam_type") == "final" else "review_unit_2", "failed_final": "propose_course_close_incomplete"}.get(exam["settlement"], "none")
        return [put("exam", p["exam_id"], exam)]
    fields(p, "review_id")
    teacher = _teacher(request); _new(state, "review", p["review_id"])
    require(exam["status"] == "submitted", "EXAM_NOT_SUBMITTED", "An actual submission is required before grading.")
    attempt = get(state, "attempt", exam["attempt_id"]); criterion = get(state, "criterion", exam["criterion_id"])
    effects = []
    if exam.get("bank_id"):
        require("self_assessment" in exam, "SELF_ASSESSMENT_REQUIRED", "The student's own scoring-point map must precede teacher checking.")
        fields(p, "point_verdicts")
        points = {x["point_id"]: x for x in criterion["scoring_points"] if x["problem_id"] in exam["problem_ids"]}
        checks = _list(p["point_verdicts"], "point_verdicts")
        require(len(checks) == len(points) and {x["point_id"] for x in checks} == set(points), "POINT_COVERAGE", "Check exactly the frozen official scoring points.")
        if "point_verdicts" in exam: require(exam["point_verdicts"] == checks, "JUDGMENT_CHANGED", "Resolve the original flags; do not replace a historical point judgment.")
        mapping = {x["point_id"]: x for x in exam["self_assessment"]["mapping"]}
        for check in checks:
            fields(check, "point_id", "judgment", "rationale")
            require(check["judgment"] in {"hit", "miss", "equivalent"}, "POINT_VERDICT", "A point is hit, missed or follows an equivalent path.")
            _text(check["rationale"], "point rationale")
            if (check["judgment"] == "equivalent" or check["judgment"] != mapping[check["point_id"]]["judgment"]) and check["point_id"] not in exam["flags"]:
                exam["flags"][check["point_id"]] = {"status": "pending", "point": deepcopy(points[check["point_id"]]), "teacher_judgment": deepcopy(check), "student_mapping": deepcopy(mapping[check["point_id"]])}
        exam["point_verdicts"] = deepcopy(checks)
        if any(x["status"] == "pending" for x in exam["flags"].values()):
            exam.update(status="flagged", passed=None, waiting_for="student_scoring_countersign")
            return [put("exam", p["exam_id"], exam)]
        scores = {pid: 0 for pid in exam["problem_ids"]}
        for check in checks:
            flag = exam["flags"].get(check["point_id"])
            counts = flag["decision"] == "accept" if flag else check["judgment"] == "hit"
            if counts: scores[points[check["point_id"]]["problem_id"]] += points[check["point_id"]]["max_score"]
        ratings = [{"problem_id": pid, "score": score, "verdict": "correct" if score == criterion["max_scores"][pid] else "partial" if score else "incorrect", "rationale": "Replayed frozen official scoring points, student mapping and resolved flags."} for pid, score in scores.items()]
        ratings = _ratings(attempt, criterion, ratings)
        bank = _read(state, request, "exam_bank", exam["bank_id"])
        if exam["exam_type"] != "quiz":
            for pid in {bank["problems"][qid]["paper_id"] for qid in exam["problem_ids"]}:
                if pid not in bank["used_papers"]: bank["used_papers"].append(pid)
                bank["papers"][pid]["pool"] = "practice"
            effects.append(put("exam_bank", exam["bank_id"], bank))
        maximum = sum(criterion["max_scores"][pid] for pid in exam["problem_ids"])
        pass_score = maximum*exam["parameters"]["pass_percent"][exam["exam_type"]]/100
        exam["paper_percent"] = sum(r["score"] for r in ratings)/maximum*100
    else:
        # A historical imported exam can retain a score, but is never upgraded to a source-qualified exam.
        fields(p, "ratings")
        ratings = _ratings(attempt, criterion, p["ratings"])
        pass_score = criterion["pass_score"]
    total = sum(r["score"] for r in ratings)
    eligible = all(r["evidence_class"] not in {"assisted", "polluted"} for r in ratings)
    eligible = eligible and bool(exam.get("bank_id"))
    exam.update(status="graded", review_id=p["review_id"], score=total, pass_score=pass_score, independently_eligible=eligible, passed=total >= pass_score and not exam.get("timed_out") and eligible, uncertain=any(r["verdict"] == "uncertain" for r in ratings), waiting_for="settlement")
    if exam["uncertain"]: exam["passed"] = None
    review = {"attempt_id": exam["attempt_id"], "criterion_id": exam["criterion_id"], "ratings": ratings, "teacher": teacher, "exam_id": p["exam_id"]}
    if exam.get("bank_id"):
        review.update(scoring_points=criterion["scoring_points"], self_assessment=exam["self_assessment"], point_verdicts=exam["point_verdicts"], flags=exam["flags"], optimization_feedback=deepcopy(p.get("optimization_feedback", [])))
    return effects + [put("review", p["review_id"], review), put("exam", p["exam_id"], exam)]


_HANDLERS = {
    "source.register": _source_register, "page.register": _page_register, "scope.create": _scope_create,
    "block.create": _block_create, "lessonmap.create": _map_create, "preparation.create": _prepare,
    "session.start": _session_start, "scan.record": _scan_record, "session.opening": _opening,
    "ticket.issue": _ticket_issue, "block.present": _block_present,
    "comprehension.submit": _comprehension_submit, "criterion.create": _criterion_create,
    "comprehension.record": _comprehension_record, "feeling.record": _feeling_record,
    "comprehension.assess": _comprehension_assess,
    "coverage.decide": _coverage_decide, "session.close": _session_close,
    "exercise.configure": _exercise_configure, "problem.add": _problem_add,
    "exercise.reorder": _exercise_reorder, "hint.authorize": _hint_authorize,
    "hint.record": _hint_record, "attempt.submit": _attempt_submit, "review.record": _review_record,
    "exam.select": _selection,
    "retest.plan": _retest_plan,
}
ACTIONS = frozenset(_HANDLERS) | {"question.open", "question.answer", "question.close", "question.reopen", "mistake.record", "mistake.retest", "exam.create", "exam.submit", "exam.grade", "exam.self_assess", "exam.flag.confirm", "exam.reminder", "exam.settle", "exam.review.complete", "exam_bank.register", "exam_bank.import", "exam_bank.freeze", "exam_bank.expose", "ocr.capture", "ocr.correct", "ocr.verify", "page.from_ocr", "variant.create", "variant.admit", "aged_review.create", "aged_review.authorize"}
ACTIONS = ACTIONS | {"mistake.recur", "exam.process.record", "exam.recover_mistakes", "question.merge", "retest.pause", "retest.resume", "retest.result"}
ACTIONS = ACTIONS | {"learning_structure.configure", "learning_segment.complete", "aged_review.window"}
ACTIONS = ACTIONS | {"exam.reinforcement.configure", "exam.reinforcement.record"}


def plan(state: dict, request: dict) -> list[dict]:
    """Validate one named learning action and return complete atomic effects."""
    fields(request, "action", "payload")
    action = request["action"]; p = request["payload"]
    require(isinstance(p, dict), "INVALID_PAYLOAD", "Payload must be an object.")
    try:
        if action in _HANDLERS:
            return _HANDLERS[action](state, request, p)
        if action.startswith("ocr.") or action == "page.from_ocr": return _ocr(state, request, p, action)
        if action.startswith("variant.") and action in ACTIONS: return _variant(state, request, p, action)
        if action.startswith("aged_review.") and action in ACTIONS: return _aged_review(state, request, p, action)
        if action in {"learning_structure.configure", "learning_segment.complete"}: return _learning_structure(state, request, p, action)
        if action.startswith("retest.") and action in ACTIONS: return _retest_progress(state, request, p, action)
        if action.startswith("question.") and action in ACTIONS: return _question(state, request, p, action)
        if action.startswith("mistake.") and action in ACTIONS: return _mistake(state, request, p, action)
        if action.startswith("exam_bank.") and action in ACTIONS: return _exam_bank(state, request, p, action)
        if action.startswith("exam.") and action in ACTIONS: return _exam(state, request, p, action)
        raise DomainError("UNKNOWN_ACTION", f"Unknown learning action: {action}")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise DomainError("INVALID_PAYLOAD", "Malformed learning request or incomplete imported object.", {"reason": str(exc)}) from exc
