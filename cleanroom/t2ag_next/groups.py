"""Course-group observations and evidence-derived evaluation.

Frequency and stagnation are separate outcomes. Unknown time and missing anchors
remain unknown; neither is turned into a learner failure or a mastery judgment.
"""
from copy import deepcopy
from datetime import date as calendar_date, datetime, timedelta
import math

from .model import DomainError, fields, get, put, require, require_student, require_student_decision, version
from .support import _read, _new, _all, digest, learning_day

ACTIONS = {"group.thresholds.configure", "group.observation.record", "group.assess", "group.triage", "group.scope.change", "group.keystone.enter",
           "group.time_plan.configure", "group.frequency.configure", "group.closure.configure", "group.condition.record"}
ENTITY_KINDS = {"group_condition_evidence"}
CONDITION_KINDS = {"course_outcome", "artifact", "debt_disposition", "group_review"}


def _agreement(group, request, payload):
    """A frozen historical fact needs evidence, not another student decision."""
    fields(payload, "basis", "reason")
    if payload["basis"] == "student_decision":
        return {"basis": payload["basis"], "decision": require_student_decision(request, ("configure", "agree", "adopt", "同意", "采用"))}
    require(payload["basis"] == "source_evidence" and group.get("legacy"),
            "GROUP_PLAN_BASIS", "Use a current decision or this migrated group's frozen evidence.")
    refs = payload.get("source_refs")
    require(isinstance(refs, list) and bool(refs), "GROUP_PLAN_EVIDENCE", "Historical mapping needs preserved source excerpts.")
    for ref in refs:
        fields(ref, "field", "value_sha256", "excerpt")
        value = group
        for part in ref["field"].split("."):
            require(isinstance(value, dict) and part in value, "GROUP_PLAN_EVIDENCE", "The preserved source field is missing.")
            value = value[part]
        require(isinstance(value, str) and ref["value_sha256"] == digest(value)
                and isinstance(ref["excerpt"], str) and bool(ref["excerpt"].strip()) and ref["excerpt"] in value,
                "GROUP_PLAN_EVIDENCE", "The excerpt must match this frozen group's source and hash.")
    return {"basis": "source_evidence", "source_refs": deepcopy(refs),
            "legacy": deepcopy(group["legacy"]), "mapping_actor": deepcopy(request["actor"]),
            "interpretation": "agent_attributed; source identity verified, semantic interpretation not machine certified"}


def _seconds(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _configure_time(group, request, payload):
    fields(payload, "time_plan")
    plan = payload["time_plan"]
    required = {"period", "week_starts_on", "course_weekly_seconds", "daily_total_max_seconds",
                "course_daily_seconds", "other_daily_seconds"}
    require(isinstance(plan, dict) and set(plan) == required, "GROUP_TIME_PLAN", "Specify weekly course budgets and daily allocations separately from member capacity.")
    require(plan["period"] == "calendar_week" and type(plan["week_starts_on"]) is int
            and 0 <= plan["week_starts_on"] <= 6, "GROUP_TIME_PLAN", "Calendar weeks need an explicit weekday anchor (Monday=0).")
    for name in ("course_weekly_seconds", "course_daily_seconds"):
        require(isinstance(plan[name], dict) and set(plan[name]) == set(group["members"])
                and all(_seconds(v) for v in plan[name].values()), "GROUP_TIME_PLAN", "Every member needs its own nonnegative time budget.")
    require(_seconds(plan["daily_total_max_seconds"]) and plan["daily_total_max_seconds"] > 0,
            "GROUP_TIME_PLAN", "The daily total maximum must be positive.")
    require(isinstance(plan["other_daily_seconds"], dict)
            and all(isinstance(k, str) and k.strip() and _seconds(v) for k, v in plan["other_daily_seconds"].items()),
            "GROUP_TIME_PLAN", "Name any non-course daily allocations, such as review.")
    require(sum(plan["course_daily_seconds"].values()) + sum(plan["other_daily_seconds"].values()) <= plan["daily_total_max_seconds"],
            "GROUP_TIME_PLAN", "Daily allocations cannot exceed the agreed total.")
    require(not group.get("time_plan") or group["time_plan"] == plan,
            "GROUP_TIME_PLAN_FROZEN", "Keep the agreed plan; a changed agreement needs its own explicit transition.")
    group.update(time_plan=deepcopy(plan), time_plan_agreement=_agreement(group, request, payload))
    return group


def _time_budget(group, activities, spans, as_of):
    plan = group.get("time_plan")
    if not plan:
        return {"status": "not_configured", "reason": "Member capacity is not a time budget."}
    known, unknown = [], []
    for identity, span in spans.items():
        if span.get("learning_day") and span["learning_day"] > as_of:
            continue
        if span.get("quality") not in ("exact", "estimated") or not span.get("learning_day"):
            unknown.append(identity)
        else:
            known.append((identity, span))
    days, weeks = {}, {}
    for identity, span in known:
        day = span["learning_day"]
        course = activities[span["activity_id"]]["course_id"]
        dt = calendar_date.fromisoformat(day)
        week = (dt - timedelta(days=(dt.weekday() - plan["week_starts_on"]) % 7)).isoformat()
        days.setdefault(day, {})[course] = days.get(day, {}).get(course, 0) + span["seconds"]
        weeks.setdefault(week, {})[course] = weeks.get(week, {}).get(course, 0) + span["seconds"]

    def course_rows(actual, budget):
        return [{"course_id": cid, "actual_seconds": actual.get(cid, 0), "budget_seconds": seconds,
                 "difference_seconds": actual.get(cid, 0) - seconds} for cid, seconds in budget.items()]

    return {"status": "partial_unknown_time" if unknown else "observed", "unit": "seconds",
            "period": "calendar_week", "week_starts_on": plan["week_starts_on"],
            "unknown_span_ids": unknown, "source_span_ids": [identity for identity, _ in known],
            "weeks": [{"week_start": week, "courses": course_rows(actual, plan["course_weekly_seconds"])}
                      for week, actual in sorted(weeks.items())],
            "days": [{"learning_day": day, "courses": course_rows(actual, plan["course_daily_seconds"]),
                      "course_actual_seconds": sum(actual.values()), "total_max_seconds": plan["daily_total_max_seconds"],
                      "other_allocations_seconds": deepcopy(plan["other_daily_seconds"]),
                      "other_actual_seconds": None, "total_actual_seconds": sum(actual.values()) if not plan["other_daily_seconds"] else None,
                      "course_time_exceeds_total_max": sum(actual.values()) > plan["daily_total_max_seconds"]}
                     for day, actual in sorted(days.items())],
            "interpretation": "Observed dates only; a partial week is not a failed week. Unknown time and unrecorded non-course review are not zero. Budgets do not alter mastery or block saving."}


def _evidence_course(state, kind, item):
    if item.get("course_id"):
        return item["course_id"]
    if item.get("activity_id"):
        return get(state, "activity", item["activity_id"])["course_id"]
    return None


def _debts(state, group, condition):
    courses = [condition["course_id"]] if condition.get("course_id") else group["members"]
    return {kind + "/" + identity: item for kind in ("mistake", "exam", "exam_debt")
            for identity, item in _all(state, kind) if _evidence_course(state, kind, item) in courses}


def _condition_record(state, request, group, payload):
    fields(payload, "id", "condition_id", "verdict", "rationale", "evidence_refs")
    condition = next((c for c in group.get("closure_conditions", []) if c["id"] == payload["condition_id"]), None)
    require(condition is not None, "GROUP_CONDITION", "Name a condition in the frozen closing plan.")
    require(payload["verdict"] in ("met", "not_met", "unknown"), "GROUP_CONDITION_VERDICT", "A condition judgment must preserve uncertainty.")
    refs = payload["evidence_refs"]
    require(isinstance(refs, list) and (bool(refs) or condition["kind"] == "debt_disposition"),
            "GROUP_CONDITION_EVIDENCE", "Cite actual persisted evidence for this judgment.")
    allowed = {"course_outcome": {"completion", "checkpoint", "milestone", "praxis"},
               "artifact": {"source"}, "debt_disposition": {"mistake", "exam", "exam_debt"}, "group_review": {"group_review"}}[condition["kind"]]
    bound, data = [], []
    for ref in refs:
        fields(ref, "kind", "id")
        require(ref["kind"] in allowed, "GROUP_CONDITION_EVIDENCE", "Use domain evidence appropriate to this condition.")
        item = _read(state, request, ref["kind"], ref["id"])
        cid = condition.get("course_id")
        if ref["kind"] == "source":
            require(cid in item.get("course_ids", []), "GROUP_CONDITION_SCOPE", "Artifact evidence must belong to the named course.")
            require(bool(item.get("content")) or bool(item.get("blob_sha256")), "GROUP_CONDITION_EVIDENCE", "A title alone is not artifact evidence.")
        elif ref["kind"] == "group_review":
            require(item.get("group_id") == payload["group_id"], "GROUP_CONDITION_SCOPE", "Review belongs to a different group.")
        else:
            require(_evidence_course(state, ref["kind"], item) in ([cid] if cid else group["members"]),
                    "GROUP_CONDITION_SCOPE", "Evidence belongs to a different course.")
        if payload["verdict"] == "met" and condition["kind"] == "course_outcome":
            if ref["kind"] == "checkpoint":
                require(item.get("status") == "confirmed", "GROUP_CONDITION_EVIDENCE", "Queued or pending knowledge is not completion.")
            if ref["kind"] == "milestone":
                require(item.get("result") == "pass", "GROUP_CONDITION_EVIDENCE", "A failed or unavailable external check is not completion.")
        if payload["verdict"] == "met" and ref["kind"] == "group_review":
            judgment = item.get("judgment", {})
            require(isinstance(judgment, dict) and judgment.get("phase") == "final" and judgment.get("verdict") == "met",
                    "GROUP_FINAL_REVIEW", "The group review must explicitly be a final, satisfied assessment.")
        bound.append({"kind": ref["kind"], "id": ref["id"], "version": version(state, ref["kind"], ref["id"]), "data_sha256": digest(item)})
        data.append((ref, item))
    decision = deepcopy(request["actor"])
    if condition["kind"] == "debt_disposition" and payload["verdict"] == "met":
        require({ref["kind"] + "/" + ref["id"] for ref in bound} == set(_debts(state, group, condition)),
                "GROUP_DEBT_COVERAGE", "Disposition must cover all existing debts in the declared member scope.")
        dispositions = payload.get("dispositions", [])
        require(isinstance(dispositions, list) and len(dispositions) == len(bound), "GROUP_DEBT_DISPOSITION", "Record the disposition of each cited debt.")
        choices = {(x.get("kind"), x.get("id")): x for x in dispositions}
        require(set(choices) == {(ref["kind"], ref["id"]) for ref, _ in data}, "GROUP_DEBT_DISPOSITION", "Debt dispositions must cover the exact evidence set.")
        for ref, item in data:
            row = choices[(ref["kind"], ref["id"])]
            if row.get("choice") == "closed":
                require(item.get("status") == "closed"
                        or (ref["kind"] == "exam" and item.get("settlement") in ("settled", "monitoring_only"))
                        or (ref["kind"] == "exam_debt" and item.get("status") == "settled"),
                        "GROUP_DEBT_OPEN", "A closed disposition needs an actual closed or settled domain record.")
            else:
                require(row.get("choice") in ("carry_forward", "waived"), "GROUP_DEBT_DISPOSITION", "Keep an explicit carry-forward or waiver decision.")
                fields(row, "reason", "destination")
                decision = require_student_decision(request, ("waive", "carry", "defer", "豁免", "顺延", "保留"))
    record = {**deepcopy(payload), "evidence_refs": bound, "closure_plan_sha256": group["closure_plan_sha256"],
              "decision": decision, "semantic_judgment": "agent_attributed; program verifies referenced evidence and versions, not semantic truth or host identity"}
    if condition["kind"] == "debt_disposition":
        record["debt_scope_sha256"] = digest(_debts(state, group, condition))
    group.setdefault("condition_evidence_ids", {})[condition["id"]] = payload["id"]
    return [put("group", payload["group_id"], group), _new(state, "group_condition_evidence", payload["id"], record)]


def _closure_assessment(state, group_id, group, as_of, basis, time_budget):
    rows, records, evidence = [], {}, {}
    for condition in group["closure_conditions"]:
        record_id = group.get("condition_evidence_ids", {}).get(condition["id"])
        record = get(state, "group_condition_evidence", record_id) if record_id else None
        status = "unknown"
        reason = "condition_evidence_missing"
        if record:
            records[record_id] = record
            fresh = record.get("closure_plan_sha256") == group["closure_plan_sha256"]
            for ref in record["evidence_refs"]:
                item = get(state, ref["kind"], ref["id"], required=False)
                evidence[ref["kind"] + "/" + ref["id"]] = item
                fresh &= item is not None and version(state, ref["kind"], ref["id"]) == ref["version"] and digest(item) == ref["data_sha256"]
            if condition["kind"] == "debt_disposition":
                debts = _debts(state, group, condition)
                evidence.update(debts)
                fresh &= record.get("debt_scope_sha256") == digest(debts)
            status = record["verdict"] if fresh else "unknown"
            reason = "attributed_judgment_on_current_evidence" if fresh else "condition_evidence_changed"
        rows.append({"id": condition["id"], "kind": condition["kind"], "description": condition["description"],
                     "status": status, "reason": reason, "record_id": record_id})
    basis.update(condition_records=records, condition_evidence=evidence)
    return {"group_id": group_id, "as_of": as_of, "basis_sha256": digest(basis),
            "closure_plan_sha256": group["closure_plan_sha256"], "closure_conditions": rows,
            "status": "met" if all(row["status"] == "met" for row in rows) else "unknown" if any(row["status"] == "unknown" for row in rows) else "not_met",
            "unresolved": [row["id"] for row in rows if row["status"] == "unknown"],
            "time_budget": time_budget, "frequency": [], "stagnation": [], "threshold_results": {},
            "interpretation": "Explicit frozen closing criteria take precedence. Judgment is attributed; evidence identity and freshness are checked. Generic numeric thresholds are not substituted."}


def validate_close(state, request, group, report):
    """Hook for support.group.close; no second confirmation action is created."""
    if group.get("closure_conditions"):
        fields(request["payload"], "closure_plan_sha256")
        require(request["payload"]["closure_plan_sha256"] == group["closure_plan_sha256"],
                "GROUP_CLOSURE_CHANGED", "Close against the complete current closing plan.")
    if group.get("requires_next_group_choice"):
        fields(request["payload"], "next_group_choice")
        choice = request["payload"]["next_group_choice"]
        require(isinstance(choice, dict) and choice.get("kind") in ("group", "none", "later"),
                "GROUP_NEXT_CHOICE", "Preserve the actual next-group choice or an explicit choice of none.")
        if choice["kind"] == "group":
            require(choice.get("id") != request["payload"]["id"], "GROUP_NEXT_CHOICE", "The next group is a different group.")
            _read(state, request, "group", choice.get("id"))
        else:
            fields(choice, "reason")
    fresh = assessment(state, request["payload"]["id"], report["as_of"])
    require(report["group_id"] == request["payload"]["id"] and report["basis_sha256"] == fresh["basis_sha256"] and fresh["status"] == "met",
            "GROUP_THRESHOLD", "Closing needs the complete fresh assessment of this group's actual criteria.")
    return fresh


def _with_closing_observations(process, closing):
    if closing is None:
        return process
    # Closing criteria do not replace independent operating observations.
    closing.update(process_status=process["status"], process_unresolved=process["unresolved"])
    for name in ("frequency", "frequency_plan", "stagnation", "threshold_results", "learning_dates", "source_span_ids", "complete_cycles", "stagnation_scope"):
        if name in process:
            closing[name] = process[name]
    return closing


def _active_dates(course, dates):
    history = course.get("pause_history", [])
    if any(not row.get("learning_day") for row in history):
        return None
    if not history:
        return None if course.get("paused") or course.get("status") == "paused" else dates
    if [row["learning_day"] for row in history] != sorted(row["learning_day"] for row in history):
        return None
    active = []
    for day in dates:
        paused = False
        for row in history:
            if row["learning_day"] > day:
                break
            paused = row["transition"] == "pause"
        if not paused:
            active.append(day)
    return active


def assessment(state, group_id, as_of):
    group = get(state, "group", group_id)
    date = learning_day(as_of)
    calendar, limits = group.get("calendar", {}), group.get("evaluation_thresholds", {})
    frequency = group.get("frequency_plan") or limits
    unresolved = []
    anchor = calendar.get("cycle_anchor_learning_day")
    length = calendar.get("cycle_length_learning_days")
    if not isinstance(anchor, str) or anchor == "TBD" or type(length) is not int or length <= 0:
        unresolved.append("cycle_anchor_or_length_not_agreed")
    if not limits and not group.get("closure_conditions"):
        unresolved.append("evaluation_thresholds_not_agreed")
    if not frequency:
        unresolved.append("frequency_minima_not_agreed")
    activities = {i: a for i, a in _all(state, "activity") if a.get("course_id") in group["members"]}
    all_spans = dict(_all(state, "timespan"))
    corrected = {span.get("corrects") for span in all_spans.values() if span.get("corrects")}
    spans = {i: span for i, span in all_spans.items() if span.get("activity_id") in activities and i not in corrected}
    known = {i: span for i, span in spans.items() if span.get("learning_day") and span["learning_day"] <= date and span.get("quality") in ("exact", "estimated")}
    if any(span.get("quality") == "unknown" for span in spans.values()):
        unresolved.append("unknown_time_spans_not_counted_as_zero")
    if anchor and anchor != "TBD":
        known = {i: span for i, span in known.items() if span["learning_day"] >= anchor}
    days = sorted({span["learning_day"] for span in known.values()})
    observations = {i: obs for i, obs in _all(state, "group_observation") if obs.get("group_id") == group_id and obs["learning_day"] <= date and (not anchor or anchor == "TBD" or obs["learning_day"] >= anchor)}
    courses = {course_id: get(state, "course", course_id) for course_id in group["members"]}
    entries = {i: entry for i, entry in _all(state, "group_keystone_entry") if entry.get("group_id") == group_id}
    basis = {"group": group, "courses": courses, "activities": activities, "timespans": spans, "observations": observations, "milestone_entries": entries}
    # Completion records are progress evidence, not a substitute for frequency.
    all_progress = {i: obj for i, obj in _all(state, "group_progress") if obj.get("group_id") == group_id}
    progress = {i: obj for i, obj in all_progress.items() if obj["learning_day"] <= date}
    basis["progress"] = all_progress
    time_budget = _time_budget(group, activities, spans, date)
    closing = _closure_assessment(state, group_id, group, as_of, basis, time_budget) if group.get("closure_conditions") else None
    result = {"group_id": group_id, "as_of": as_of, "basis_sha256": digest(basis), "unresolved": unresolved,
              "learning_dates": days, "source_span_ids": sorted(known), "frequency": [], "stagnation": [], "threshold_results": {}, "status": "unknown", "time_budget": time_budget,
              "frequency_plan": {name: deepcopy(frequency[name]) for name in ("count_unit", "minimum_per_cycle") if name in frequency}}
    if "cycle_anchor_or_length_not_agreed" in unresolved:
        return _with_closing_observations(result, closing)
    complete_cycles = len(days) // length
    counts = {}
    for cycle in range(complete_cycles):
        cycle_days = set(days[cycle * length:(cycle + 1) * length])
        counts[cycle + 1] = {}
        for course_id, minimum in frequency.get("minimum_per_cycle", {}).items():
            course = get(state, "course", course_id)
            active_dates = _active_dates(course, sorted(cycle_days))
            if active_dates is None:
                result["unresolved"].append(f"historical_pause_interval_not_established:{course_id}")
                result["frequency"].append({"cycle": cycle + 1, "course_id": course_id, "status": "pause_interval_unknown", "grade_effect": "none"})
                continue
            if len(active_dates) != len(cycle_days):
                status = "paused_excluded" if not active_dates else "partial_pause_cycle"
                if active_dates:
                    result["unresolved"].append(f"partial_pause_cycle_minimum_not_agreed:{course_id}:{cycle+1}")
                result["frequency"].append({"cycle": cycle + 1, "course_id": course_id, "status": status, "grade_effect": "none"})
                continue
            selected = [span for span in known.values() if span["learning_day"] in cycle_days and activities[span["activity_id"]]["course_id"] == course_id]
            if frequency["count_unit"] == "learning_days":
                actual = len({span["learning_day"] for span in selected})
            else:
                if any(not span.get("session_id") for span in selected):
                    result["unresolved"].append(f"session_identity_missing:{course_id}:{cycle+1}")
                actual = len({span["session_id"] for span in selected if span.get("session_id")})
            available = any(obs.get("kind") == "available_but_not_done" and obs.get("course_id") == course_id and obs["learning_day"] in cycle_days for obs in observations.values())
            status = "met" if actual >= minimum else "breach" if available else "needs_capacity_triage"
            counts[cycle + 1][course_id] = status
            result["frequency"].append({"cycle": cycle + 1, "course_id": course_id, "actual": actual, "minimum": minimum, "status": status,
                "grade_effect": "frequency_only" if status == "breach" else "none", "emergency_review": status == "breach" and counts.get(cycle, {}).get(course_id) == "breach"})
    measured = [row for row in result["frequency"] if row["status"] in ("met", "breach")]
    if any(row["status"] == "needs_capacity_triage" for row in result["frequency"]):
        result["unresolved"].append("frequency_shortfall_cause_not_attributed")
    attainment = sum(row["status"] == "met" for row in measured) / len(measured) if measured else None
    tests = {}
    if limits:
        total_seconds = sum(span["seconds"] for span in known.values())
        deviation = abs(total_seconds - limits["time_budget_seconds"]) / limits["time_budget_seconds"]
        failed_dates = {obs["learning_day"] for obs in observations.values() if obs["kind"] == "start_failure"}
        adjustments = [obs for obs in observations.values() if obs["kind"] == "major_adjustment"]
        values = {"frequency_attainment": attainment, "time_budget_deviation": deviation, "start_failure_days": len(failed_dates), "major_adjustments": len(adjustments)}
        tests = {"frequency_attainment": attainment is not None and attainment >= limits["minimum_frequency_attainment"],
                 "time_budget_deviation": deviation <= limits["maximum_time_deviation"],
                 "start_failure_days": len(failed_dates) <= limits["maximum_start_failure_days"],
                 "major_adjustments": len(adjustments) >= limits["minimum_major_adjustments"]}
        result["threshold_results"] = {name: {"actual": values[name], "met": met} for name, met in tests.items()}
    result["complete_cycles"] = complete_cycles
    if not complete_cycles:
        result["unresolved"].append("no_complete_learning_cycle")
    budget = calendar.get("keystone_dwell_budget_cycles") if group.get("container_mode", "progress") == "progress" else 2
    if type(budget) is not int or budget <= 0:
        result["stagnation_scope"] = {"status": "unknown", "reason": "keystone_dwell_budget_not_agreed"}
    elif complete_cycles >= budget:
        current = next((kid for kid in group.get("keystone_ids", []) if kid not in group.get("completed_keystone_ids", [])), None)
        mapping = group.get("keystone_courses", {})
        course_id = mapping.get(current) or (group["members"][0] if current and len(group["members"]) == 1 else None)
        if current is None or course_id is None:
            result["stagnation_scope"] = {"status": "unknown", "reason": "current_milestone_or_member_not_mapped"}
        else:
            entry = entries.get(group_id + "/" + current)
            first = group.get("keystone_ids", [None])[0] == current
            entered = entry["learning_day"] if entry else anchor if first else None
            eligible = [day for day in days if entered and entered <= day]
            if entered is None:
                result["stagnation_scope"] = {"status": "unknown", "reason": "current_milestone_entry_date_unknown", "keystone_id": current}
                eligible = []
            recent = set(eligible[-budget*length:])
            course = get(state, "course", course_id)
            active_dates = _active_dates(course, eligible)
            if active_dates is None:
                result["stagnation_scope"] = {"status": "unknown", "reason": "historical_pause_interval_not_established", "course_id": course_id}
                eligible = []
            else:
                eligible = active_dates
            recent = set(eligible[-budget*length:])
            if len(eligible) >= budget*length and not course.get("paused") and course.get("status") != "paused" and not any(x.get("course_id") == course_id and x.get("keystone_id") == current and x["learning_day"] in recent for x in progress.values()):
                result["stagnation"].append({"course_id": course_id, "keystone_id": current, "budget_cycles": budget, "status": "triage_needed", "grade_effect": "none", "choices": ["stuck", "no_time", "no_statement"]})
    result["status"] = "unknown" if result["unresolved"] else ("met" if all(tests.values()) else "not_met") if tests else "observed"
    return _with_closing_observations(result, closing)


def plan(state, request):
    action, p = request["action"], request["payload"]
    fields(p, "group_id")
    group = _read(state, request, "group", p["group_id"])
    if action == "group.time_plan.configure":
        group = _configure_time(group, request, p)
        return [put("group", p["group_id"], group)]
    if action == "group.frequency.configure":
        fields(p, "frequency_plan")
        frequency = p["frequency_plan"]
        require(isinstance(frequency, dict) and set(frequency) == {"count_unit", "minimum_per_cycle"}
                and frequency["count_unit"] in ("sessions", "learning_days"),
                "GROUP_FREQUENCY_PLAN", "Name the count unit and only the members with agreed cycle minima.")
        minima = frequency["minimum_per_cycle"]
        require(isinstance(minima, dict) and bool(minima) and set(minima) <= set(group["members"])
                and all(type(v) is int and v >= 0 for v in minima.values()),
                "GROUP_FREQUENCY_PLAN", "Unknown member frequency is omitted, never filled with zero.")
        require(not group.get("frequency_plan") or group["frequency_plan"] == frequency,
                "GROUP_FREQUENCY_FROZEN", "Keep the agreed frequency plan rather than lowering it after results.")
        group.update(frequency_plan=deepcopy(frequency), frequency_agreement=_agreement(group, request, p))
        return [put("group", p["group_id"], group)]
    if action == "group.closure.configure":
        fields(p, "conditions", "requires_next_group_choice")
        require(isinstance(p["conditions"], list) and bool(p["conditions"]), "GROUP_CLOSURE_PLAN", "Keep the complete explicit closing criteria.")
        require(type(p["requires_next_group_choice"]) is bool, "GROUP_CLOSURE_PLAN", "State whether the agreement requires a next-group choice.")
        identities = set()
        for condition in p["conditions"]:
            fields(condition, "id", "kind", "description")
            require(condition["id"] not in identities and condition["kind"] in CONDITION_KINDS,
                    "GROUP_CLOSURE_PLAN", "Conditions need unique names and one of the supported domain evidence types.")
            identities.add(condition["id"])
            if condition["kind"] in ("course_outcome", "artifact"):
                require(condition.get("course_id") in group["members"], "GROUP_CLOSURE_PLAN", "A course condition belongs to a declared member.")
            if condition.get("course_id"):
                require(condition["course_id"] in group["members"], "GROUP_CLOSURE_PLAN", "A condition cannot select another group's course.")
        plan_hash = digest({"conditions": p["conditions"], "requires_next_group_choice": p["requires_next_group_choice"]})
        require(not group.get("closure_conditions") or group.get("closure_plan_sha256") == plan_hash,
                "GROUP_CLOSURE_FROZEN", "Do not replace frozen criteria after observing results.")
        group.update(closure_conditions=deepcopy(p["conditions"]), requires_next_group_choice=p["requires_next_group_choice"],
                     closure_plan_sha256=plan_hash, closure_agreement=_agreement(group, request, p))
        return [put("group", p["group_id"], group)]
    if action == "group.condition.record":
        return _condition_record(state, request, group, p)
    if action == "group.keystone.enter":
        fields(p, "keystone_id", "activity_id", "happened_at", "evidence")
        current = next((kid for kid in group.get("keystone_ids", []) if kid not in group.get("completed_keystone_ids", [])), None)
        require(p["keystone_id"] == current, "GROUP_PROGRESS_SCOPE", "Enter the actual next unfinished milestone.")
        activity = _read(state, request, "activity", p["activity_id"])
        expected_course = group.get("keystone_courses", {}).get(current) or (group["members"][0] if len(group["members"]) == 1 else None)
        require(activity["course_id"] == expected_course and activity["status"] == "ongoing" and bool(p["evidence"]), "GROUP_PROGRESS_SCOPE", "Milestone entry needs its active member activity and actual observation.")
        return [_new(state, "group_keystone_entry", p["group_id"] + "/" + current, {**deepcopy(p), "learning_day": learning_day(p["happened_at"]), "actor": deepcopy(request["actor"])})]
    if action == "group.thresholds.configure":
        require_student(request)
        fields(p, "thresholds", "reason")
        limits = p["thresholds"]
        required = {"count_unit", "minimum_per_cycle", "minimum_frequency_attainment", "time_budget_seconds", "maximum_time_deviation", "maximum_start_failure_days", "minimum_major_adjustments"}
        require(isinstance(limits, dict) and set(limits) == required, "GROUP_THRESHOLDS", "Specify all four measurable closing criteria and the frequency unit.")
        require(limits["count_unit"] in ("sessions", "learning_days") and isinstance(limits["minimum_per_cycle"], dict) and set(limits["minimum_per_cycle"]) == set(group["members"]), "GROUP_THRESHOLDS", "Frequency minima must cover every member with an explicit unit.")
        require(all(type(x) is int and x >= 0 for x in limits["minimum_per_cycle"].values()), "GROUP_THRESHOLDS", "Frequency counts must be nonnegative integers.")
        for field in ("minimum_frequency_attainment", "time_budget_seconds", "maximum_time_deviation"):
            value = limits[field]
            require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "GROUP_THRESHOLDS", "Threshold values must be finite nonnegative numbers.")
        require(limits["time_budget_seconds"] > 0 and limits["minimum_frequency_attainment"] <= 1, "GROUP_THRESHOLDS", "Use a positive time budget and an attainment ratio in [0,1].")
        require(all(type(limits[k]) is int and limits[k] >= 0 for k in ("maximum_start_failure_days", "minimum_major_adjustments")), "GROUP_THRESHOLDS", "Failure/adjustment limits are nonnegative integers.")
        require(group.get("status") == "planned" or not group.get("evaluation_thresholds"), "GROUP_THRESHOLDS_FROZEN", "Thresholds cannot be lowered after an active group has been evaluated against them.")
        group.update(evaluation_thresholds=deepcopy(limits), threshold_decision=deepcopy(request["actor"]))
        return [put("group", p["group_id"], group)]
    if action == "group.observation.record":
        fields(p, "id", "course_id", "kind", "happened_at", "evidence")
        require(p["course_id"] in group["members"] and p["kind"] in ("available_but_not_done", "start_failure", "major_adjustment", "progress"), "GROUP_OBSERVATION", "Observation must describe a member and named outcome.")
        require(bool(p["evidence"]), "EVIDENCE_REQUIRED", "Preserve actual observation evidence.")
        require_student(request)
        data = {**deepcopy(p), "learning_day": learning_day(p["happened_at"]), "decision": deepcopy(request["actor"])}
        if p["kind"] == "progress":
            fields(p, "keystone_id")
            require(p["keystone_id"] in group.get("keystone_ids", []), "GROUP_PROGRESS_SCOPE", "Progress names an actual group milestone.")
            if p.get("completion_id"):
                completion = _read(state, request, "completion", p["completion_id"])
                require(completion["course_id"] == p["course_id"], "GROUP_EVIDENCE", "Progress needs actual member completion evidence.")
                evidence_kind = {"comprehension": "checkpoint", "external_milestone": "milestone", "action_feedback": "praxis"}.get(completion.get("judgment_kind"))
                require(evidence_kind is not None, "GROUP_EVIDENCE", "Unknown completion evidence kind.")
                refs = [(evidence_kind, identity) for identity in completion["evidence_ids"]]
            else:
                fields(p, "checkpoint_id")
                refs = [("checkpoint", p["checkpoint_id"])]
            matched = False
            bindings = group.get("keystone_bindings", {}).get(p["keystone_id"], [])
            for evidence_kind, identity in refs:
                item = _read(state, request, evidence_kind, identity)
                if evidence_kind == "checkpoint":
                    require(item["status"] == "confirmed", "GROUP_EVIDENCE", "Progress checkpoints must be actually confirmed.")
                    activity = _read(state, request, "activity", item["activity_id"])
                    require(activity["course_id"] == p["course_id"], "GROUP_EVIDENCE", "Checkpoint belongs to a different member.")
                matched |= identity == p["keystone_id"] or item.get("position") == p["keystone_id"] or item.get("keystone_id") == p["keystone_id"] or {"kind": evidence_kind, "id": identity} in bindings
            require(matched, "GROUP_PROGRESS_SCOPE", "An unrelated completion cannot hide the current milestone's stagnation.")
            return [_new(state, "group_progress", p["id"], data)]
        return [_new(state, "group_observation", p["id"], data)]
    if action == "group.assess":
        fields(p, "id", "as_of")
        result = assessment(state, p["group_id"], p["as_of"])
        return [_new(state, "group_assessment", p["id"], result)]
    if action == "group.triage":
        fields(p, "id", "assessment_id", "course_id", "choice")
        decision = require_student(request)
        report = _read(state, request, "group_assessment", p["assessment_id"])
        fresh = assessment(state, p["group_id"], report["as_of"])
        require(report["basis_sha256"] == fresh["basis_sha256"], "STALE_TRIAGE", "The evidence changed after this stagnation assessment.")
        require(not any(x.get("group_id") == p["group_id"] and x.get("course_id") == p["course_id"] and x.get("basis_sha256") == report["basis_sha256"] for _, x in _all(state, "group_triage")), "TRIAGE_ALREADY_RECORDED", "This evidence window already has an attributed triage answer.")
        require(report["group_id"] == p["group_id"] and any(x["course_id"] == p["course_id"] for x in fresh["stagnation"]), "TRIAGE_SCOPE", "This course must have the current actual stagnation observation.")
        require(p["choice"] in ("stuck", "no_time", "no_statement"), "TRIAGE_CHOICE", "Triage preserves the student's actual answer.")
        result = [_new(state, "group_triage", p["id"], {**deepcopy(p), "basis_sha256": report["basis_sha256"], "decision": decision, "grade_effect": "none"})]
        if p["choice"] == "no_time":
            fields(p, "resume_condition")
            course = _read(state, request, "course", p["course_id"])
            require(course["status"] == "ongoing", "COURSE_STATE", "Pause an ongoing course while retaining its cursor.")
            course.update(paused=True, resume_condition=p["resume_condition"])
            course.setdefault("pause_history", []).append({"transition": "pause", "learning_day": learning_day(p.get("happened_at", report["as_of"])), "decision": decision})
            result.append(put("course", p["course_id"], course))
        return result
    if action == "group.scope.change":
        fields(p, "keystone_ids", "reason", "trigger", "destination")
        decision = require_student(request)
        require(group["status"] == "active" and p["trigger"] in ("review", "triage", "group_transition"), "GROUP_SCOPE_GATE", "An active scope change needs its explicit review/triage/transition decision.")
        old, new = group.get("keystone_ids", []), p["keystone_ids"]
        require(isinstance(new, list) and len(set(new)) == len(new), "KEYSTONE_IDS", "Milestone identities are unique.")
        removed, added = sorted(set(old)-set(new)), sorted(set(new)-set(old))
        require(bool(removed or added), "NO_SCOPE_CHANGE", "Scope did not change.")
        require(not (set(removed) & set(group.get("completed_keystone_ids", []))), "COMPLETED_SCOPE", "Completed milestone facts cannot be removed from the group.")
        group.setdefault("keystone_scope_ledger", []).append({"removed": removed, "added": added, "reason": p["reason"], "trigger": p["trigger"], "destination": p["destination"], "decision": decision})
        group["keystone_total_frozen"] = group.get("keystone_total_frozen", len(old)) + len(added)
        group["keystone_ids"] = deepcopy(new)
        return [put("group", p["group_id"], group)]
    raise DomainError("UNKNOWN_ACTION", action)
