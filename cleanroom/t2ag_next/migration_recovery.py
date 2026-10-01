"""Narrow, evidence-bound recovery of imported carriers for future learning.

Historical answers, grades, help and permissions are never rewritten. Recovery
does not start an activity, present content or count a new success. A current
student decision may issue one normal ticket to present the exact saved body
again, after normal session preparation. Unrecognized semantics stay unresolved.
"""
from copy import deepcopy
from datetime import date
import re

from .model import fields, get, key, put, require, require_student_decision
from .support import _read, _new, digest


ACTIONS = {"migration.exercise.recover", "migration.mistake.recover", "migration.cursor.recover",
           "migration.cursor.map", "migration.question.recover"}
EXERCISE_REASON = "historical_exercise_help_and_criterion_require_reconciliation"
MISTAKE_REASON = "knowledge_cycle_retest_dates_require_domain_reconciliation"
CURSOR_REASON = "narrative_cursor_requires_reconciliation_with_body_and_checkpoint_table"
QUESTION_REASON = "question_activity_reference_unresolved"


def _date(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "RECOVERY_DATE", "Use an exact preserved ISO learning date.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        require(False, "RECOVERY_DATE", "Invalid preserved learning date.")
    return parsed.isoformat()


def _begin(state, request, kind, identity, required_fields):
    p = request["payload"]
    fields(p, "id", "target_sha256", "evidence_refs")
    actor = request.get("actor", {})
    require(actor.get("role") in {"teacher", "student"}, "RECOVERY_ATTRIBUTION", "Keep the actual recovery interpreter's attribution.")
    fields(actor, "source", "text")
    target = _read(state, request, kind, identity)
    require(target.get("legacy") is not None and bool(target.get("uncertainties")), "RECOVERY_NOT_PENDING", "Only a preserved, unresolved imported object uses this recovery route.")
    require(p["target_sha256"] == digest(target), "RECOVERY_TARGET_CHANGED", "Re-read the complete current object before recovering it.")
    refs = p["evidence_refs"]
    require(isinstance(refs, list) and len(refs) == len(required_fields), "RECOVERY_EVIDENCE", "Bind all required preserved fields once.")
    require({r.get("field") for r in refs if isinstance(r, dict)} == set(required_fields), "RECOVERY_EVIDENCE", "Do not substitute another field for the required original evidence.")
    for ref in refs:
        require(isinstance(ref, dict) and set(ref) == {"kind", "id", "field", "value_sha256"}, "RECOVERY_EVIDENCE", "Use exact kind/id/field/value_sha256 evidence references.")
        require(ref["kind"] == kind and ref["id"] == identity and ref["field"] in target and ref["value_sha256"] == digest(target[ref["field"]]), "RECOVERY_EVIDENCE_CHANGED", "Recovery binds the target's own preserved source fields.")
    require(get(state, "migration_recovery", p["id"], False) is None, "IDENTITY_EXISTS", "Use a distinct recovery receipt identity.")
    return target, {"target_kind": kind, "target_id": identity, "before_sha256": digest(target), "evidence_refs": deepcopy(refs), "actor": deepcopy(actor), "historical_regrading": False, "future_permission": "none"}


def _finish(state, p, kind, identity, target, receipt, resolved):
    require(set(resolved) <= set(target["uncertainties"]), "RECOVERY_REASON", "Resolve only the known supported ambiguity.")
    target["uncertainties"] = [r for r in target["uncertainties"] if r not in resolved]
    target["migration_requires_reconciliation"] = bool(target["uncertainties"])
    target["migration_state"] = "needs_resolution" if target["uncertainties"] else "recovered_for_future_use"
    target.setdefault("recovery_ids", []).append(p["id"])
    receipt.update(resolved=list(resolved), remaining=deepcopy(target["uncertainties"]), after_sha256=digest(target))
    return [put(kind, identity, target), _new(state, "migration_recovery", p["id"], receipt)]


def _exercise(state, request, p):
    fields(p, "exercise_id")
    identity = p["exercise_id"]
    target, receipt = _begin(state, request, "exercise", identity, ("legacy_fields", "original_body", "problems"))
    require(EXERCISE_REASON in target["uncertainties"], "RECOVERY_REASON", "This action handles unmapped historical help and criterion only.")
    activity = _read(state, request, "activity", target["activity_id"])
    require(activity["course_id"] == target["course_id"], "RECOVERY_COURSE", "The carrier still belongs to its original activity and course.")
    problems = target.get("problems")
    require(isinstance(problems, dict) and bool(problems), "RECOVERY_PROBLEMS", "Recover actual preserved questions, not an empty carrier.")
    source_order, supplemental, sequence = target.get("source_order", []), target.get("supplemental_ids", []), target.get("teaching_sequence", [])
    require(all(isinstance(v,list) and all(isinstance(i,str) for i in v) for v in (source_order,supplemental,sequence)), "RECOVERY_ORDER", "Preserved order must contain explicit question identities.")
    require(len(source_order) == len(set(source_order)) and len(sequence) == len(set(sequence)) and set(source_order).isdisjoint(supplemental) and set(source_order) | set(supplemental) == set(problems) == set(sequence), "RECOVERY_ORDER", "Original and teaching order must completely identify the preserved questions.")
    require(not target.get("criterion_id"), "RECOVERY_CRITERION", "Do not replace an already installed new-system criterion.")
    require(not target.get("assistance"), "RECOVERY_HELP_CHANGED", "Do not overwrite a mapped or newly recorded help history.")
    for pid, problem in problems.items():
        require(isinstance(problem.get("text"), str) and bool(problem["text"].strip()), "RECOVERY_PROBLEMS", "The full preserved question must remain readable.")
    for kind, ids in (("attempt", target.get("attempt_ids", [])), ("review", target.get("review_ids", []))):
        for ident in ids:
            old = _read(state, request, kind, ident)
            require(old.get("history_only") is True, "RECOVERY_NEW_WORK", "A carrier with new-system judgments cannot be reset as a legacy import.")
    target["assistance"] = [{"problem_id": pid, "level": "legacy_unknown", "evidence_class": "legacy_uncertain", "polluted": False,
        "content": "Historical help was not mapped; this question cannot certify new independent mastery.", "evidence_refs": deepcopy(receipt["evidence_refs"])} for pid in problems]
    target.update(assistance_status="historical_help_unknown_explicitly_carried", future_criterion_required=True)
    receipt.update(consumer="criterion.create then new attempt.submit/review.record; activity lifecycle remains unchanged", historical_question_ids=list(problems), old_activity_status=activity["status"])
    return _finish(state, p, "exercise", identity, target, receipt, [EXERCISE_REASON])


def _mistake(state, request, p):
    fields(p, "mistake_id")
    from . import learning
    require(getattr(learning, "LEGACY_CYCLE_BASELINE_VERSION", None) == 1, "RECOVERY_CONSUMER_PENDING", "The learning consumer must support preserved cycle counters and learning-date gates before this ambiguity can be cleared.")
    identity = p["mistake_id"]
    target, receipt = _begin(state, request, "mistake", identity, ("legacy_fields", "legacy_retest_rows", "original_body"))
    require(MISTAKE_REASON in target["uncertainties"], "RECOVERY_REASON", "This action maps preserved cycle counters and dates only.")
    require(not target.get("retests") and not target.get("pending_settlement") and not target.get("legacy_cycle_baseline"), "RECOVERY_NEW_WORK", "Do not reset a knowledge point after new-system retesting begins.")
    f = target["legacy_fields"]
    require(isinstance(f,dict), "RECOVERY_FIELDS", "Keep recognized preserved key/value fields.")
    if not target.get("activity_id"):
        # Older entries may retain only an Exercise unit/subproblem locator.
        # A unique actual historical answer can bind that locator to its carrier.
        source = re.fullmatch(r"Exercise\s+([A-Za-z0-9_-]+)\s*/\s*(Q\d+(?:\(\d+\))?)", f.get("来源", ""))
        require(source is not None, "RECOVERY_ORIGIN_UNKNOWN", "The missing original activity needs an exact supported Exercise locator.")
        locator = source[1] + "-" + source[2]
        locator_pattern = re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(locator) + r"(?![A-Za-z0-9_-]|\s*[（(]|\.\d)")
        matches = [e for e in state["objects"].values() if e["kind"] == "attempt" and e["data"].get("history_only") is True
            and locator_pattern.search(e["data"].get("original_body", "")) and e["data"].get("activity_id")]
        candidates = []
        for e in matches:
            a = _read(state, request, "activity", e["data"]["activity_id"])
            if a["course_id"] == target["course_id"]: candidates.append(e)
        require(len(candidates) == 1, "RECOVERY_ORIGIN_AMBIGUOUS", "The original locator must identify one historical answer in this course; never select by recency.")
        fields(p, "origin_evidence")
        ref = p["origin_evidence"]; candidate = candidates[0]
        old = _read(state, request, "attempt", candidate["id"])
        require(ref == {"kind":"attempt", "id":candidate["id"], "field":"original_body", "value_sha256":digest(old["original_body"]), "locator":locator}, "RECOVERY_ORIGIN_EVIDENCE", "Bind the exact unique preserved answer locator without regrading that answer.")
        target["activity_id"] = old["activity_id"]
        receipt["origin_evidence"] = deepcopy(ref)
    activity = _read(state, request, "activity", target["activity_id"])
    require(activity["course_id"] == target["course_id"], "RECOVERY_COURSE", "The original knowledge-point course must agree.")
    fields(f, "当前周期", "当前周期摘要", "状态", "陈年连续正确", "下次允许复测", "首次日期")
    require(all(isinstance(f[name],str) for name in ("当前周期摘要","状态","陈年连续正确","下次允许复测","首次日期")), "RECOVERY_FIELDS", "Unrecognized legacy field types remain unresolved.")
    require(f["状态"] == target["status"] and target["status"] in {"active", "aged", "maintenance"}, "RECOVERY_STATUS", "Keep the actual recorded state; recovery does not promote or reopen it.")
    require(re.fullmatch(r"[1-9]\d*", str(f["当前周期"])) is not None and str(f["当前周期"]) == str(target["cycle"]), "RECOVERY_CYCLE", "Preserved cycle identities conflict.")
    m = re.fullmatch(r"尝试\s*(\d+)/6\s*[｜|]\s*独立正确\s*(\d+)/3\s*[｜|]\s*失败\s*(\d+)\s*[｜|]\s*错后连续正确\s*(\d+)/2", f["当前周期摘要"].strip())
    require(m is not None, "RECOVERY_CYCLE_SUMMARY", "The exact historical counter form is not recognized; retain the uncertainty.")
    attempts, successes, failures, streak = map(int, m.groups())
    require(0 <= successes + failures <= attempts <= 6 and 0 <= streak <= successes, "RECOVERY_CYCLE_CONFLICT", "Historical counters are internally inconsistent.")
    aged = re.fullmatch(r"(\d+)/2", f["陈年连续正确"].strip())
    require(aged is not None and int(aged[1]) <= 2, "RECOVERY_AGED_COUNT", "Keep the explicit aged-review streak.")
    rows = target["legacy_retest_rows"]
    require(isinstance(rows, list), "RECOVERY_RETEST_ROWS", "Preserve actual historical rows.")
    current = []
    for row in rows:
        fields(row, "周期", "日期", "结果", "探针/变式", "提示", "判定依据")
        _date(row["日期"])
        require(row["结果"] in {"✓", "✔", "✗", "×", "△"}, "RECOVERY_RESULT", "An unrecognized legacy result remains unresolved.")
        if str(row["周期"]) == str(f["当前周期"]): current.append(row)
    require(len(current) == attempts, "RECOVERY_CYCLE_CONFLICT", "Counter and preserved current-cycle row count must agree.")
    require(sum(r["结果"] in {"✓", "✔"} for r in current) >= successes and sum(r["结果"] in {"✗", "×"} for r in current) <= failures, "RECOVERY_CYCLE_CONFLICT", "Do not manufacture successes or erase explicit failures from old rows.")
    first = _date(f["首次日期"])
    last = max([first] + [r["日期"] for r in rows])
    due = f["下次允许复测"].strip()
    absolute = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:（[^\n]*）|\([^\n]*\))?", due)
    if absolute:
        target["recovery_not_before"] = _date(absolute[1])
        require(target["recovery_not_before"] >= last, "RECOVERY_DATE_CONFLICT", "The next allowed date precedes preserved history.")
    else:
        relative = re.fullmatch(r"累计\s*(\d+)\s*个后续学习日后", due)
        require(relative is not None and int(relative[1]) > 0, "RECOVERY_DUE_UNKNOWN", "Unknown timing remains blocked; do not substitute elapsed days for learning dates.")
        target.update(recovery_learning_date_anchor=last, recovery_min_subsequent_learning_dates=int(relative[1]))
    baseline = {"attempts": attempts, "successes": successes, "failures": failures, "independent_streak": streak,
        "aged_success_streak": int(aged[1]), "cycle": int(f["当前周期"]), "status": target["status"], "last_learning_date": last,
        "cycle_start": 0, "evidence_refs": deepcopy(receipt["evidence_refs"]), "interpretation": "preserved_declared_counters_not_regraded_answers"}
    target.update(legacy_cycle_baseline=baseline, legacy_cycle_baseline_active=True, cycle=int(f["当前周期"]), cycle_start=0, cycle_attempts=attempts, cycle_successes=successes,
        failed_retests=failures, independent_streak=streak, aged_success_streak=int(aged[1]), recurrences=[])
    receipt.update(consumer="learning retest scheduling and new formal results; old rows remain historical only", baseline=deepcopy(baseline))
    return _finish(state, p, "mistake", identity, target, receipt, [MISTAKE_REASON])


def _cursor(state, request, p):
    fields(p, "activity_id", "block_id", "body_sha256", "body_evidence", "session_id", "ticket_id")
    identity = p["activity_id"]
    target, receipt = _begin(state, request, "cursor", identity, ("legacy_activity_position", "legacy_current_section", "legacy_body_next_action"))
    require(CURSOR_REASON in target["uncertainties"], "RECOVERY_REASON", "This action binds the exact preserved pending body, not a new future curriculum choice.")
    activity = _read(state, request, "activity", identity)
    require(activity["status"] == "ongoing", "RECOVERY_ACTIVITY", "Pending close and terminal activities use their own closing review.")
    block = _read(state, request, "block", p["block_id"])
    require(block["activity_id"] == identity and block["status"] == "planned" and not block.get("responses") and not block.get("judgments"), "RECOVERY_BLOCK", "Use a fresh normally prepared block of this activity; never rewrite an already answered block.")
    from .learning import digest as text_digest
    require(p["body_sha256"] == block["body_sha256"] == text_digest(block["body"]), "RECOVERY_BODY_CHANGED", "Bind the complete actual body to be presented again.")
    ref = p["body_evidence"]
    require(isinstance(ref, dict) and set(ref) == {"kind", "id", "field", "value_sha256", "excerpt"}, "RECOVERY_BODY_EVIDENCE", "Bind the pending body to preserved full activity text.")
    require(ref["kind"] == "activity" and ref["id"] == identity and ref["field"] in {"original_body", "pending_body"}, "RECOVERY_BODY_EVIDENCE", "Use this activity's preserved body, not a teacher title or unrelated source.")
    original = activity.get(ref["field"])
    require(isinstance(original, str) and ref["value_sha256"] == digest(original) and ref["excerpt"] == block["body"] and block["body"] in original, "RECOVERY_BODY_EVIDENCE", "The complete repeated block must actually occur in preserved text.")
    student = require_student_decision(request, ("恢复", "呈现", "重讲", "继续", "restore", "present", "explain", "repeat", "continue"), error_code="RECOVERY_STUDENT_SCOPE")
    target.update(block_id=p["block_id"], waiting_for="authorization", next_action="represent_recovered_body", pending_body=block["body"],
        body_sha256=block["body_sha256"], historical_permissions_active=False, current_session_scan=None, requires_current_session_revalidation=True)
    receipt.update(consumer="block.present consumes the new current-session ticket without asking the same decision twice", body_evidence=deepcopy(ref), student=student, position_preserved=target.get("position"),
        future_permission={"ticket_id":p["ticket_id"], "session_id":p["session_id"], "block_id":p["block_id"], "body_sha256":p["body_sha256"], "scope":"present_this_saved_body_again_only"})
    effects = _finish(state, p, "cursor", identity, target, receipt, [CURSOR_REASON])
    working = deepcopy(state)
    for effect in effects:
        name = key(effect["kind"],effect["id"]); old = working["objects"].get(name)
        working["objects"][name] = {"kind":effect["kind"],"id":effect["id"],"version":old["version"] if old else state["revision"],"data":deepcopy(effect["data"])}
    from . import learning
    ticket_request = {**request, "action":"ticket.issue", "actor":student, "payload":{name:p[name] for name in ("session_id","ticket_id","block_id","body_sha256")}}
    # The same attributed words and existing gate implementation apply to both
    # operations. Any source/readiness/previous-gate failure commits neither.
    return effects + learning.plan(working,ticket_request)


def _cursor_map(state, request, p):
    """Map a literal saved stop with a plain resume route; grant no permission.

    Elaborated next-step narratives, such as the conflicting AIF record, do not
    use this route. The interpreter remains responsible for the source meaning;
    hashes bind evidence and do not authenticate a semantic judgment.
    """
    fields(p, "activity_id")
    identity = p["activity_id"]
    target, receipt = _begin(state, request, "cursor", identity,
        ("legacy_activity_position", "legacy_current_section", "legacy_body_next_action"))
    require(CURSOR_REASON in target["uncertainties"], "RECOVERY_REASON", "Map the known narrative cursor ambiguity only.")
    activity = _read(state, request, "activity", identity)
    course = _read(state, request, "course", activity["course_id"])
    require(course.get("current_activity_id") == identity and activity["status"] == "ongoing", "RECOVERY_ROUTE", "Keep the actual current, unfinished activity.")
    route = re.fullmatch(r"resume\s+(lesson|exercise):([A-Za-z0-9_-]+)(?:；以结构化 next_action_\* 字段为准。)?",
                        target["legacy_body_next_action"].strip())
    next_action = target.get("next_action", {})
    require(route is not None and isinstance(next_action, dict) and next_action.get("kind") == "resume"
            and next_action.get("activity_type") == route[1] and next_action.get("activity_id") == route[2]
            and identity == activity["course_id"] + "/" + route[2], "RECOVERY_ROUTE_CONFLICT",
            "Only a plain matching resume route can be mapped; conflicting or elaborated next steps remain unresolved.")
    current = target["legacy_current_section"]
    stops = re.findall(r"^-\s*\*\*精确停顿点\*\*[：:]\s*(.+)$", current, re.M)
    require(len(stops) <= 1, "RECOVERY_POSITION", "Preserved stopping point must be unique.")
    position = stops[0] if stops else target["legacy_activity_position"]
    live_block = get(state, "block", target["block_id"], False) if target.get("block_id") else None
    require(isinstance(position, str) and bool(position.strip()) and not target.get("pending_body")
            and live_block is None, "RECOVERY_POSITION", "Keep the imported checkpoint anchor, but do not replace a prepared or pending teaching body.")
    target.update(position=position, waiting_for="resume", historical_permissions_active=False,
                  current_session_scan=None, requires_current_session_revalidation=True)
    receipt.update(consumer="context recovery; normal session preparation and actual learning decisions still apply",
                   position_field="legacy_current_section" if stops else "legacy_activity_position",
                   course_status_preserved=course["status"], activity_status_preserved=activity["status"],
                   evidence_interpretation="literal_saved_stop_and_matching_plain_resume_route")
    return _finish(state, p, "cursor", identity, target, receipt, [CURSOR_REASON])


def _question(state, request, p):
    """Restore provenance, without turning a question into a new exercise."""
    fields(p, "question_id", "origin_evidence")
    identity = p["question_id"]
    target, receipt = _begin(state, request, "question", identity, ("legacy_fields", "original_body"))
    require(QUESTION_REASON in target["uncertainties"] and not target.get("activity_id"), "RECOVERY_REASON", "Only restore a missing historical activity reference.")
    f = target["legacy_fields"]
    cid = target["course_id"]
    record = f.get("完整记录", "")
    attempt_path = re.search(r"exercises/(exercise\d+)/attempts/(AT\d+)/attempt\.md", record)
    lesson_path = re.search(r"(?:lessons/)?(lesson\d+)/\1\.md", record)
    locator = None
    if attempt_path:
        origin_kind, origin_id = "attempt", cid + "/" + attempt_path[1] + "/" + attempt_path[2]
        locator = attempt_path[0]
    elif lesson_path:
        origin_kind, origin_id = "activity", cid + "/" + lesson_path[1]
        locator = lesson_path[0]
    else:
        source = re.fullmatch(r"Exercise\s+([A-Za-z0-9_-]+)\s*/\s*(Q\d+(?:\(\d+\))?)", f.get("来源", ""))
        require(source is not None, "RECOVERY_ORIGIN_UNKNOWN", "A question needs an explicit record path or exact Exercise locator.")
        locator = source[1] + "-" + source[2]
        pattern = re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(locator) + r"(?![A-Za-z0-9_-]|\s*[（(]|\.\d)")
        matches = []
        for e in state["objects"].values():
            if e["kind"] != "attempt" or not e["data"].get("history_only") or not pattern.search(e["data"].get("original_body", "")):
                continue
            activity = _read(state, request, "activity", e["data"]["activity_id"])
            if activity["course_id"] == cid:
                matches.append(e["id"])
        require(len(matches) == 1, "RECOVERY_ORIGIN_AMBIGUOUS", "The exact locator must identify one preserved answer in this course.")
        origin_kind, origin_id = "attempt", matches[0]
    original = _read(state, request, origin_kind, origin_id)
    require(isinstance(original.get("original_body"), str) and bool(original["original_body"]), "RECOVERY_ORIGIN_EVIDENCE", "Keep the full preserved destination record.")
    ref = {"kind": origin_kind, "id": origin_id, "field": "original_body", "value_sha256": digest(original["original_body"]), "locator": locator}
    require(p["origin_evidence"] == ref, "RECOVERY_ORIGIN_EVIDENCE", "Bind the identified historical destination, not a selected substitute.")
    aid = original["activity_id"] if origin_kind == "attempt" else origin_id
    if origin_kind == "attempt":
        require(original.get("history_only") is True, "RECOVERY_ORIGIN_EVIDENCE", "Use preserved historical work.")
    activity = _read(state, request, "activity", aid)
    require(activity["course_id"] == cid, "RECOVERY_COURSE", "Question and referenced activity must belong to the same course.")
    target["activity_id"] = aid
    receipt.update(origin_evidence=deepcopy(ref), consumer="question history and existing activity question views",
                   status_preserved=target["status"], historical_question_only=True)
    return _finish(state, p, "question", identity, target, receipt, [QUESTION_REASON])


def plan(state, request):
    action = request["action"]
    require(action in ACTIONS, "UNKNOWN_ACTION", "Unknown named migration recovery action.")
    return {"migration.exercise.recover": _exercise, "migration.mistake.recover": _mistake,
            "migration.cursor.recover": _cursor, "migration.cursor.map": _cursor_map,
            "migration.question.recover": _question}[action](state, request, request["payload"])
