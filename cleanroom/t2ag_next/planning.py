"""Planning and reflective follow-through, with explicit attributed decisions.

These checks establish document/identity/evidence consistency, not human intent,
psychological truth, mathematical correctness, or delivery outside this API.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import re

from . import learning, support
from .model import DomainError, fields, get, key, put, require, require_student, require_student_decision, version
from .support import _read, _new, _all, _provenance, digest


SECTIONS = ("goal", "conditions", "route", "schedule", "materials_tools", "outputs", "feedback", "assumptions", "open_questions")
LABELS = {"zh": ("你的目标", "当前条件", "建议路线", "时间安排", "材料与工具", "阶段产出", "反馈方式", "方案假设", "待确认问题"),
          "en": ("Your goal", "Current conditions", "Suggested route", "Schedule", "Materials and tools", "Stage outputs", "Feedback", "Assumptions", "Open questions")}
OVERLAY_FIELDS = {"tone", "pace", "language", "display_name", "entry_style", "feedback_frequency", "presentation"}


def _text(value, field):
    require(isinstance(value, str) and bool(value.strip()), "PLANNING_TEXT", f"Provide {field} as actual nonempty text.")


def _time(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as exc:
        raise DomainError("PLANNING_DATE", "Use an ISO timestamp with timezone.") from exc
    require(result.tzinfo is not None, "PLANNING_DATE", "A timezone is required.")
    return result


def _history(s, kind, identity, before, r):
    return _new(s, kind + "_revision", f"{identity}/r{s['revision'] + 1}",
                {"subject_id": identity, "before": before, "actor": _provenance(r)})


def _refs(s, r, refs, allowed=None):
    require(isinstance(refs, list) and bool(refs), "EVIDENCE_REQUIRED", "Keep actual source identities.")
    result = []
    for ref in refs:
        require(isinstance(ref, dict) and set(ref) == {"kind", "id"}, "EVIDENCE_REFERENCE", "Use kind/id source references.")
        require(allowed is None or ref["kind"] in allowed, "EVIDENCE_REFERENCE", "This source kind is not evidence for this judgment.")
        _read(s, r, ref["kind"], ref["id"])
        result.append({**ref, "version": version(s, ref["kind"], ref["id"])})
    require(len({(x['kind'], x['id']) for x in result}) == len(result), "DUPLICATE_EVIDENCE", "Do not duplicate one source into multiple observations.")
    return result


def _accept(r):
    actor = require_student_decision(r, ("同意", "确认", "建立", "创建", "采用", "执行", "开始", "approve", "accept", "create", "proceed", "start", "act"), error_code="PLAN_NOT_ACCEPTED")
    text = actor["text"].strip().casefold()
    # The action is the host/agent-attributed formal choice. These are limited
    # contradictions/non-decisions, never a positive phrase/password detector.
    require(not re.search(r"[?？]|只是保存|仅保存|先别|暂缓|老师说|他说|她说|假设|如果|要是|"
                          r"\b(?:if|assuming|hypothetically|provided that|as long as|she said|he said|teacher said|only save|save only)\b|"
                          r"\b(?:could|might)\s+(?:accept|approve|confirm)\b", text),
            "PLAN_NOT_ACCEPTED", "A question, condition, report, deferral or save-only statement cannot confirm a complete plan.")
    require(not (text[:1] in {'"', "'", "“", "「", "『"} and text.rstrip("。.!！ ")[-1:] in {'"', "'", "”", "」", "』"}),
            "PLAN_NOT_ACCEPTED", "A quoted acceptance is not the student's current decision.")
    return actor


def _condition(s, r, identity):
    return _read(s, r, "planning_conditions", identity)


def _proposal(s, r, p):
    fields(p, "conditions_id", "sections", "courses")
    conditions = _condition(s, r, p["conditions_id"])
    profile = _read(s, r, "student", "current")
    references = {"student/current": version(s, "student", "current")}
    language = "en" if profile.get("language", "zh").startswith("en") else "zh"
    require(isinstance(p["sections"], dict) and set(p["sections"]) == set(SECTIONS), "PLAN_SECTIONS", "The plan needs all nine complete sections, including assumptions and questions.")
    for name in SECTIONS: _text(p["sections"][name], name)
    require(isinstance(p["courses"], list) and bool(p["courses"]), "PLAN_COURSES", "The plan needs at least one named course.")
    ids = set()
    for course in p["courses"]:
        fields(course, "id", "title", "course_type", "mode_explanation", "goal")
        require(course["id"] not in ids and get(s, "course", course["id"], False) is None, "PLAN_COURSE_ID", "Use distinct unused course identities.")
        ids.add(course["id"])
        require(course["course_type"] in {"mastery", "project", "praxis"}, "COURSE_TYPE", "Unknown course type.")
        mode = course.get("learning_mode")
        require((course["course_type"] == "mastery" and mode in {"textbook", "goal", "project"}) or (course["course_type"] != "mastery" and mode is None), "LEARNING_MODE", "Only Mastery has a learning mode.")
        _text(course["mode_explanation"], "mode explanation")
        for sid in course.get("source_ids", []):
            source = _read(s, r, "source", sid)
            require(course["id"] in source.get("course_ids", []), "SOURCE_COURSE", "An existing source must explicitly admit this course.")
            references[key("source", sid)] = version(s, "source", sid)
        if course.get("new_sources"):
            require(isinstance(course["new_sources"], list), "PLAN_SOURCES", "Use attributed source-registration proposals.")
            for source in course["new_sources"]:
                fields(source, "source_id", "title", "format", "source_version", "content_sha256")
                require(get(s, "source", source["source_id"], False) is None, "SOURCE_EXISTS", "New source identity already exists.")
        if course.get("teacher_id"):
            _read(s, r, "teacher", course["teacher_id"])
            references[key("teacher", course["teacher_id"])] = version(s, "teacher", course["teacher_id"])
        if course.get("first_activity"):
            a = course["first_activity"]; fields(a, "id", "title", "activity_type")
            require(a["id"].startswith(course["id"] + "/") and a["activity_type"] in {"lesson", "exercise"}, "PLAN_ACTIVITY", "A first Lesson or Exercise belongs to its course.")
        if course.get("learning_structure_ref"):
            ref = course["learning_structure_ref"]
            require(ref == {"kind": "learning_structure", "id": course["id"], "revision": version(s, "learning_structure", course["id"])}, "LEARNING_STRUCTURE", "Reference the learning domain's existing structure; never create a second completion count.")
            _read(s, r, "learning_structure", course["id"])
    group = p.get("group")
    if group:
        fields(group, "id", "capacity", "calendar", "thresholds", "goal", "container_mode", "keystone_ids", "presentation")
        require(get(s, "group", group["id"], False) is None, "PLAN_GROUP_ID", "Use a new group identity.")
        require(type(group["capacity"]) is int and group["capacity"] >= len(ids), "GROUP_CAPACITY", "The proposed group must fit its actual courses.")
        fields(group["calendar"], "frequency", "stagnation_days"); fields(group["thresholds"], "close_condition")
        require(group["container_mode"] in {"progress", "schedule"} and isinstance(group["keystone_ids"], list) and bool(group["keystone_ids"]), "PLAN_GROUP", "Map the complete calendar and real milestone sequence before asking for acceptance.")
        _text(group["presentation"], "group arrangement")
    body = "\n\n".join(f"## {label}\n{p['sections'][name]}" for name, label in zip(SECTIONS, LABELS[language]))
    statuses = {"provided": "学生已提供" if language == "zh" else "Student provided", "not_provided": "尚未提供" if language == "zh" else "Not provided", "public_assumption": "公开假设，可修改" if language == "zh" else "Explicit assumption, editable"}
    condition_labels = {
        "goal_and_time": ("目标与时间", "Goal and available time"), "grade_level": ("学习阶段", "Learning stage"),
        "textbook": ("教材", "Textbook"), "time": ("可用时间", "Available time"),
        "level": ("当前基础", "Current background"), "route": ("学习路线", "Learning route"),
        "goal": ("学习目标", "Learning goal"), "preferences": ("学习偏好", "Learning preferences"),
    }
    condition_lines = []
    for name, item in conditions["conditions"].items():
        fallback = name.replace("_", " ")
        label = item.get("label") or condition_labels.get(name, (fallback, fallback))[language == "en"]
        condition_lines.append(f"{label}: {statuses[item['status']]} — {item.get('value') or statuses['not_provided']}")
    body += "\n\n" + ("条件的来源：\n" if language == "zh" else "Sources of conditions:\n") + "\n".join(condition_lines)
    body += "\n\n" + ("课程与推进方式：\n" if language == "zh" else "Courses and progression:\n")
    for c in p["courses"]:
        labels = {("mastery", "textbook"): ("按教材推进、以理解为完成依据", "Textbook progression with comprehension-based completion"), ("mastery", "goal"): ("按能力目标推进、以理解为完成依据", "Goal-led mastery with comprehension-based completion"), ("mastery", "project"): ("通过项目学习、以理解为完成依据", "Project-led mastery with comprehension-based completion"), ("project", None): ("按外部可验证交付推进", "Externally verified project delivery"), ("praxis", None): ("按现实行动、反馈与复盘推进", "Real action, feedback and reflection")}
        body += f"\n{c['title']} — {labels[(c['course_type'], c.get('learning_mode'))][language == 'en']}\n{c['mode_explanation']}\n{c['goal']}\n"
        if c.get("teacher_id"):
            teacher = get(s, "teacher", c["teacher_id"])
            body += ("教师：" if language == "zh" else "Teacher: ") + teacher["name"] + "\n"
        if c.get("first_activity"): body += c["first_activity"]["title"] + "\n"
        for sid in c.get("source_ids", []):
            source = get(s, "source", sid)
            body += ("现有材料：" if language == "zh" else "Existing material: ") + f"{source['title']} ({source.get('source_version', 'unknown')})\n"
        for source in c.get("new_sources", []):
            body += ("新增材料：" if language == "zh" else "New material: ") + f"{source['title']} ({source['source_version']})\n"
    if group:
        body += "\n" + group["presentation"] + "\n"
        body += ("课程容量：" if language == "zh" else "Course capacity: ") + str(group["capacity"]) + "\n"
        body += ("日历约定：" if language == "zh" else "Calendar terms: ") + "; ".join(str(v) for v in group["calendar"].values()) + "\n"
        body += ("结组条件：" if language == "zh" else "Group closing condition: ") + str(group["thresholds"]["close_condition"]) + "\n"
        body += ("阶段序列：" if language == "zh" else "Stage sequence: ") + " → ".join(group["keystone_ids"])
    snapshot = {"conditions_id": p["conditions_id"], "conditions_version": version(s, "planning_conditions", p["conditions_id"]),
                "sections": deepcopy(p["sections"]), "courses": deepcopy(p["courses"]), "group": deepcopy(group), "body": body,
                "language": language, "reference_versions": references, "proposed_by": deepcopy(r["actor"]), "status": "draft", "authority": "candidate_not_course_or_progress"}
    snapshot["proposal_sha256"] = digest(snapshot)
    return snapshot


def _commit_plan(s, r, identity, d):
    working = deepcopy(s); effects = {}
    def emit(rows):
        for e in rows:
            name = key(e["kind"], e["id"]); old = working["objects"].get(name)
            working["objects"][name] = {"kind": e["kind"], "id": e["id"], "version": old["version"] if old else s["revision"], "data": deepcopy(e["data"])}
            effects[name] = e
    def act(action, payload, module=support, actor=None):
        request = {**r, "action": action, "payload": payload, "expected": {k: v["version"] for k, v in working["objects"].items()}}
        if actor is not None: request["actor"] = actor
        emit(module.plan(working, request))
    for c in d["courses"]:
        act("course.create", {k: c[k] for k in ("id", "title", "course_type", "learning_mode", "goal", "teacher_id") if k in c})
        course = get(working, "course", c["id"])
        course.update(source_ids=deepcopy(c.get("source_ids", [])), initial_plan_ref={"id": identity, "sha256": d["proposal_sha256"]})
        emit([put("course", c["id"], course)])
        for source in c.get("new_sources", []):
            act("source.register", {**source, "course_ids": [c["id"]]}, learning, d["proposed_by"])
        if c.get("first_activity") or d.get("group"): act("course.activate", {"id": c["id"]})
        if c.get("first_activity"):
            act("activity.create", {**c["first_activity"], "course_id": c["id"]})
            act("activity.start", {"id": c["first_activity"]["id"]})
    if d.get("group"):
        g = d["group"]
        act("group.propose", {k: deepcopy(g[k]) for k in ("id", "capacity", "calendar", "thresholds", "goal")} | {"members": [c["id"] for c in d["courses"]]})
        act("group.keystones.configure", {"id": g["id"], "container_mode": g["container_mode"], "keystone_ids": g["keystone_ids"], "reason": "Mapped from the student's displayed accepted plan."})
        act("group.activate", {"id": g["id"], "proposal_sha256": get(working, "group", g["id"])["proposal_sha256"]})
    d.update(status="accepted", decision=deepcopy(r["actor"]), authority="historical_accepted_proposal_current_state_owned_by_domains")
    emit([put("learning_plan", identity, d)])
    return list(effects.values())


def plan(s, r):
    action, p = r["action"], r["payload"]
    fields(p, "id"); identity = p["id"]; actor = _provenance(r)
    if action == "planning.conditions.record":
        fields(p, "conditions")
        require(isinstance(p["conditions"], dict), "PLANNING_CONDITIONS", "Conditions may be empty; unknown student facts are not defaulted.")
        for name, item in p["conditions"].items():
            require(isinstance(item, dict) and item.get("status") in {"provided", "not_provided", "public_assumption"}, "CONDITION_STATUS", "Distinguish declared facts, unknowns, and public assumptions.")
            if item["status"] == "provided":
                fields(item, "value", "student"); require_student({"actor": item["student"]}, item["value"])
            elif item["status"] == "not_provided":
                require(item.get("value") in (None, "not_provided"), "UNKNOWN_FACT", "A skipped answer cannot acquire a default student fact.")
            else: _text(item.get("value"), "public assumption")
        old = get(s, "planning_conditions", identity, False)
        rows = []
        if old:
            old = _read(s, r, "planning_conditions", identity); rows.append(_history(s, "planning_conditions", identity, old, r))
        return rows + [put("planning_conditions", identity, {"conditions": deepcopy(p["conditions"]), "actor": actor})]
    if action in {"planning.propose", "planning.revise"}:
        require(actor["role"] == "teacher", "PLAN_AUTHOR", "Retain the teacher's proposal attribution separately from student confirmation.")
        rows = []
        if action.endswith("revise"):
            old = _read(s, r, "learning_plan", identity)
            require(old["status"] != "accepted", "PLAN_ALREADY_ACCEPTED", "An accepted plan is history; propose a new change against actual courses.")
            rows.append(_history(s, "learning_plan", identity, old, r))
        else: require(get(s, "learning_plan", identity, False) is None, "IDENTITY_EXISTS", "Plan identity already exists.")
        return rows + [put("learning_plan", identity, _proposal(s, r, p))]
    if action in {"planning.present", "planning.confirm"}:
        d = _read(s, r, "learning_plan", identity)
        fields(p, "proposal_sha256")
        require(p["proposal_sha256"] == d["proposal_sha256"], "PLAN_CHANGED", "Use the complete current proposal.")
        _condition(s, r, d["conditions_id"])
        require(version(s, "planning_conditions", d["conditions_id"]) == d["conditions_version"], "CONDITIONS_CHANGED", "The plan's conditions changed; revise the complete plan.")
        require(all(s["objects"].get(k, {}).get("version") == v for k, v in d["reference_versions"].items()), "PLAN_REFERENCES_CHANGED", "A source, teacher or profile used by this plan changed; revise before confirmation.")
        if action.endswith("present"):
            fields(p, "presented_body", "presentation_ref")
            require(d["status"] in {"draft", "presented"} and p["presented_body"] == d["body"], "PLAN_PRESENTATION", "Present the complete generated plan, not a path or summary.")
            d.update(status="presented", presentation_ref=p["presentation_ref"], presented_by=actor)
            return [put("learning_plan", identity, d)]
        require(d["status"] == "presented", "PLAN_NOT_PRESENTED", "Present the complete plan before asking for acceptance.")
        decision = _accept(r)
        # Re-resolve external references at commit, including teacher/source edits.
        _proposal(s, r, d)
        return _commit_plan(s, {**r,"actor":decision}, identity, d)
    if action == "teacher.template.revise":
        old = _read(s, r, "teacher", identity); fields(p, "template", "reason")
        _text(p["template"], "teacher template")
        d = deepcopy(old); d.update(template=p["template"], revision_reason=p["reason"], revised_by=actor)
        return [_history(s, "teacher", identity, old, r), put("teacher", identity, d)]
    if action == "teacher.overlay.revise":
        require_student(r); fields(p, "course_id", "preferences", "reason")
        course = _read(s, r, "course", p["course_id"])
        require(isinstance(p["preferences"], dict) and set(p["preferences"]) <= OVERLAY_FIELDS, "OVERLAY_AUTHORITY", "Preferences cannot alter factual standards, required content or confirmation gates.")
        old = get(s, "teacher_overlay", identity, False); rows = []
        if old:
            old = _read(s, r, "teacher_overlay", identity)
            require(old.get("course_id") == p["course_id"], "OVERLAY_SCOPE", "Do not rewrite a shared or another course's overlay; create a scoped one.")
            rows.append(_history(s, "teacher_overlay", identity, old, r))
        course["teacher_overlay_id"] = identity
        return rows + [put("teacher_overlay", identity, {"course_id": p["course_id"], "preferences": deepcopy(p["preferences"]), "reason": p["reason"], "student": actor, "authority": "presentation_preferences"}), put("course", p["course_id"], course)]
    if action in {"reading.note.record", "reading.resources.append"}:
        fields(p, "reading_id"); reading = _read(s, r, "reading", p["reading_id"])
        require(reading["status"] == "recording", "READING_STATE", "Paused, archived or upgraded reading does not take new progress; explicitly resume or use its course.")
        if action.endswith("record"):
            fields(p, "body", "evidence"); _text(p["body"], "reading note")
            require(bool(p["evidence"]), "EVIDENCE_REQUIRED", "Retain the note's real source.")
            if actor["role"] == "student": require_student(r, p["body"])
            note = _new(s, "reading_note", identity, {"reading_id": p["reading_id"], "body": p["body"], "evidence": deepcopy(p["evidence"]), "attribution": actor})
            reading.setdefault("note_ids", []).append(identity)
            return [note, put("reading", p["reading_id"], reading)]
        fields(p, "resources")
        require(isinstance(p["resources"], list) and bool(p["resources"]), "READING_RESOURCES", "Append actual resources under this same reading intent.")
        existing = reading.setdefault("resources", [])
        for resource in p["resources"]:
            fields(resource, "identity", "title", "locator")
            require(not any(isinstance(x, dict) and x.get("identity") == resource["identity"] for x in existing), "RESOURCE_EXISTS", "An existing resource identity is not replaced.")
            existing.append(deepcopy(resource))
        return [put("reading", p["reading_id"], reading)]
    if action == "engagement.transition":
        d = _read(s, r, "engagement", identity); fields(p, "status", "reason")
        require_student(r)
        current = d["status"]
        allowed = {"active": {"paused", "archived"}, "ongoing": {"paused", "archived"}, "paused": {"active", "ongoing", "archived"}, "archived": set()}
        require(p["status"] in allowed.get(current, set()), "ENGAGEMENT_STATE", "Preserve the Engagement lifecycle; archived history is terminal.")
        d.setdefault("lifecycle", []).append({"from": current, "to": p["status"], "reason": p["reason"], "student": actor})
        d["status"] = p["status"]
        return [put("engagement", identity, d)]
    if action == "reflection.review":
        d = _read(s, r, "reflection", identity); fields(p, "observation", "source_refs")
        _text(p["observation"], "review observation")
        row = {"observation": p["observation"], "source_refs": _refs(s, r, p["source_refs"]), "reviewer": actor}
        if p.get("student_statement"):
            row["student_statement"] = require_student({"actor": p["student_statement"]})
        d.setdefault("reviews", []).append(row)
        return [put("reflection", identity, d)]
    if action == "pattern.method.configure":
        d = _read(s, r, "pattern", identity)
        names = ("trigger", "old_path", "stop_signal", "replacement_action", "causal_explanation", "training_plan", "next_probe", "admission_reason")
        fields(p, *names, "source_refs", "admission_kind")
        for name in names: _text(p[name], name)
        refs = _refs(s, r, p["source_refs"], {"review", "attempt", "block", "thought", "reflection", "pattern", "method_use"})
        admission = p["admission_kind"]
        require(admission in {"repeated_problems", "student_report", "transfer_case", "existing_pattern"}, "METHOD_ADMISSION", "Use an actual admission condition from the method contract.")
        if admission == "student_report":
            fields(p, "student_statement"); require_student({"actor": p["student_statement"]})
        if admission == "existing_pattern":
            require(any(x["kind"] == "pattern" and x["id"] == identity for x in refs), "METHOD_ADMISSION", "Identify the existing pattern being converted into training.")
        if admission in {"repeated_problems", "transfer_case"}:
            problems = set()
            for ref in refs:
                data = get(s, ref["kind"], ref["id"])
                if ref["kind"] == "review":
                    require(not data.get("history_only") and not data.get("migration_requires_reconciliation"), "METHOD_ADMISSION", "Map historical evidence before interpreting its outcome.")
                    problems.update(x["problem_id"] for x in data.get("ratings", []) if x.get("evidence_class") != "polluted")
                elif ref["kind"] == "attempt": problems.update(x["problem_id"] for x in data.get("answers", []))
            require(len(problems) >= (2 if admission == "repeated_problems" else 1), "METHOD_ADMISSION", "Admission needs distinct actual problems, not repeated pointers to one problem.")
        require(not d.get("method"), "METHOD_EXISTS", "Do not replace an existing method without its supersession record.")
        d.setdefault("status", "hypothesis")
        d.update(method={k: p[k] for k in names}, method_status="candidate", method_evidence=refs, observations=[],
                 method_admission={"kind": admission, "student_statement": deepcopy(p.get("student_statement")), "reviewer": actor})
        return [put("pattern", identity, d)]
    if action == "pattern.observe":
        d = _read(s, r, "pattern", identity); fields(p, "review_id", "problem_id", "observed_at", "variant_signature", "trigger_before_prompt", "old_path_took_over", "observation")
        require(bool(d.get("method")), "METHOD_MISSING", "Configure the explicit replacement method first.")
        review = _read(s, r, "review", p["review_id"])
        rating = next((x for x in review.get("ratings", []) if x.get("problem_id") == p["problem_id"]), None)
        require(rating is not None and not review.get("history_only") and not review.get("migration_requires_reconciliation"), "METHOD_EVIDENCE", "Use an actual mapped problem judgment.")
        attempt = _read(s, r, "attempt", review["attempt_id"])
        require(not attempt.get("history_only") and not attempt.get("migration_requires_reconciliation"), "METHOD_EVIDENCE", "Unknown historical assistance is not independent transfer.")
        _time(p["observed_at"]); _text(p["variant_signature"], "variant identity")
        require(type(p["trigger_before_prompt"]) is bool and type(p["old_path_took_over"]) is bool, "METHOD_OBSERVATION", "Record observed behavior explicitly.")
        row = {k: deepcopy(p[k]) for k in p if k != "id"}
        assistance = attempt.get("assistance", {}).get(p["problem_id"], {})
        row.update(success=rating.get("verdict") == "correct" and rating.get("evidence_class") != "polluted",
                   independent=rating.get("independent") is True and assistance.get("level") == "none" and not assistance.get("polluted"),
                   assistance=deepcopy(assistance), reviewer=actor)
        observations = d.setdefault("observations", [])
        require(not any(x["review_id"] == p["review_id"] and x["problem_id"] == p["problem_id"] for x in observations), "DUPLICATE_OBSERVATION", "One problem judgment is one observation.")
        observations.append(row)
        return [put("pattern", identity, d)]
    if action == "pattern.review":
        d = _read(s, r, "pattern", identity); fields(p, "reason")
        require("method_status" in p or "pattern_status" in p, "PATTERN_REVIEW", "Review the observed pattern and/or its separate replacement method.")
        if "pattern_status" in p:
            require(p["pattern_status"] in {"observing", "confirmed", "retired"}, "PATTERN_STATE", "The observed pattern is observing, confirmed or retired.")
            fields(p, "source_refs")
            refs = _refs(s, r, p["source_refs"], {"review", "attempt", "block", "thought", "reflection", "method_use"})
            if p["pattern_status"] == "confirmed":
                fields(p, "student_statement"); student = require_student({"actor": p["student_statement"]})
            else: student = None
            d.setdefault("pattern_reviews", []).append({"from": d.get("status"), "to": p["pattern_status"], "reason": p["reason"], "source_refs": refs, "student_statement": student, "reviewer": actor})
            d["status"] = p["pattern_status"]
            if "method_status" not in p: return [put("pattern", identity, d)]
        current = d.get("method_status", "candidate"); target = p["method_status"]
        require(bool(d.get("method")), "METHOD_MISSING", "Configure the replacement method before assessing transfer.")
        require(target in {"candidate", "reinforced", "automatic", "superseded"}, "METHOD_STATE", "Unknown replacement-method state.")
        superseded_reviews = {review.get("supersedes") for _, review in _all(s, "review") if review.get("supersedes")}
        observations = [x for x in d.get("observations", []) if x["review_id"] not in superseded_reviews]
        if target == "reinforced": require(any(x["success"] for x in observations), "METHOD_TRANSFER", "A successful variant observation is required.")
        if target == "automatic":
            good = [x for x in observations if x["success"] and x["independent"] and x["trigger_before_prompt"] and not x["old_path_took_over"]]
            require(any(a["problem_id"] != b["problem_id"] and a["variant_signature"] != b["variant_signature"] and abs(_time(a["observed_at"])-_time(b["observed_at"])) >= timedelta(days=1) for a in good for b in good), "METHOD_TRANSFER", "Automatic needs two different unprompted variants separated by at least one day.")
        if target == "superseded":
            fields(p, "replacement_id"); require(p["replacement_id"] != identity, "METHOD_REPLACEMENT", "A method cannot replace itself.")
            replacement = _read(s, r, "pattern", p["replacement_id"])
            require(bool(replacement.get("method")), "METHOD_REPLACEMENT", "The replacing pattern needs an actual configured method.")
        require(current != "superseded", "METHOD_RETIRED", "Superseded methods remain historical.")
        d.setdefault("method_reviews", []).append({"from": current, "to": target, "reason": p["reason"], "replacement_id": p.get("replacement_id"), "reviewer": actor})
        d["method_status"] = target
        return [put("pattern", identity, d)]
    if action == "keystone.review":
        d = _read(s, r, "keystone", identity); fields(p, "session_id", "reviewed_at", "model_label", "steps", "conclusion")
        require(p.get("private_persuasion") is None, "PRIVATE_MATERIAL", "Only the public logical chain may enter this record.")
        _time(p["reviewed_at"])
        require(p["session_id"] != d.get("origin_session_id") and bool(p["session_id"]), "KEYSTONE_REVIEW_SESSION", "Adversarial review belongs to another session.")
        require(isinstance(p["steps"], list) and bool(p["steps"]), "KEYSTONE_REVIEW", "Review the numbered chain step by step.")
        chain = d.get("steps", d.get("reasons", []))
        require(isinstance(chain, list) and bool(chain), "KEYSTONE_CHAIN_PENDING", "Explicitly map the original numbered chain before reviewing imported prose.")
        require({x.get("step") for x in p["steps"]} == set(range(1, len(chain)+1)) and len(p["steps"]) == len(chain), "KEYSTONE_REVIEW", "Every original numbered step needs one review.")
        for step in p["steps"]:
            require(step.get("result") in {"no_gap_found", "gap_found", "uncertain"}, "KEYSTONE_REVIEW", "Record a local result, not a machine proof claim.")
            _text(step.get("analysis"), "step analysis")
        review = {k: deepcopy(p[k]) for k in ("session_id", "reviewed_at", "model_label", "steps", "conclusion")}
        review.update(reviewer=actor, argument_correctness_machine_verified=False)
        d.setdefault("reviews", []).append(review)
        d["review_status"] = "gap_found" if any(x["result"] == "gap_found" for x in p["steps"]) else "reexamined"
        return [put("keystone", identity, d)]
    raise DomainError("UNKNOWN_ACTION", action)


ACTIONS = {"planning.conditions.record", "planning.propose", "planning.revise", "planning.present", "planning.confirm",
           "teacher.template.revise", "teacher.overlay.revise", "reading.note.record", "reading.resources.append", "engagement.transition",
           "reflection.review", "pattern.method.configure", "pattern.observe", "pattern.review", "keystone.review"}
