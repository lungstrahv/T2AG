import copy
import unittest

from t2ag_next import support
from t2ag_next.model import DomainError


class SupportJourneys(unittest.TestCase):
    def setUp(self):
        self.state = {"revision": 0, "objects": {"student/current": {"kind": "student", "id": "current", "version": 0, "data": {"language": "zh"}}}}
        self.serial = 0

    def request(self, action, payload, role="student", text="明确作出本次具体选择"):
        self.serial += 1
        return {"request_id": f"r{self.serial}", "action": action, "payload": payload,
                "actor": {"role": role, "text": text, "source": f"test-message-{self.serial}"},
                "expected": {k: v["version"] for k, v in self.state["objects"].items()}}

    def act(self, action, payload, **kw):
        request = self.request(action, payload, **kw)
        effects = support.plan(copy.deepcopy(self.state), request)
        self.state["revision"] += 1
        for effect in effects:
            self.state["objects"][f"{effect['kind']}/{effect['id']}"] = {
                "kind": effect["kind"], "id": effect["id"], "version": self.state["revision"], "data": effect["data"]}
        return effects

    def data(self, kind, identity):
        return self.state["objects"][f"{kind}/{identity}"]["data"]

    def course(self, identity="C", kind="mastery", mode="goal"):
        self.act("course.create", {"id": identity, "title": identity, "course_type": kind, "learning_mode": mode})
        self.act("course.activate", {"id": identity})

    def activity(self, identity="C/L1", kind="lesson"):
        self.act("activity.create", {"id": identity, "course_id": identity.split("/")[0], "activity_type": kind, "title": identity})
        self.act("activity.start", {"id": identity})

    def close(self, body="实际学习的完整复盘"):
        self.act("activity.close.propose", {"id": "C/L1", "body": body, "outcome": "closed_incomplete", "presentation_ref": "shown-in-message-1", "reconciliation": {"remaining": ["x"]}}, role="teacher")
        return self.data("activity", "C/L1")["pending_sha256"]

    def test_course_semantics_do_not_confuse_mastery_project_with_project(self):
        self.course(kind="mastery", mode="project")
        with self.assertRaisesRegex(DomainError, "Project judgment"):
            self.act("milestone.record", {"id": "m", "course_id": "C", "mode": "A", "result": "pass", "verification": {}})
        self.assertEqual(self.data("course", "C")["course_type"], "mastery")

    def test_project_modes_and_environment_failure_do_not_complete(self):
        self.course(kind="project", mode=None)
        for mode in ("A", "B", "B-K"):
            self.act("milestone.record", {"id": mode, "course_id": "C", "mode": mode, "result": "environment_failure", "verification": {
                "procedure": "run acceptance", "artifact": "artifact-sha", "independent_check": "external-verifier", "failure_ladder": "retry infrastructure"}, "evidence": ["log-ref"]})
            with self.assertRaisesRegex(DomainError, "not a pass"):
                self.act("completion.record", {"id": "CP" + mode, "course_id": "C", "judgment_kind": "external_milestone", "evidence_ids": [mode]})

    def test_praxis_requires_action_not_chat_answer(self):
        self.course(kind="praxis", mode=None)
        with self.assertRaises(DomainError):
            self.act("completion.record", {"id": "CP", "course_id": "C", "judgment_kind": "comprehension", "evidence_ids": ["answer"]})
        self.act("praxis.record", {"id": "P", "course_id": "C", "action_taken": "observed experiment", "feedback": "failed", "uncertainty": "one sample", "governance_source": "external-policy", "evidence": ["observation"]})
        self.act("completion.record", {"id": "CP", "course_id": "C", "judgment_kind": "action_feedback", "evidence_ids": ["P"]})
        self.assertEqual(self.data("course", "C")["status"], "ongoing")

    def test_routing_leaves_previous_activity_open_and_enforces_capacity(self):
        self.course()
        for n in range(1, 4):
            self.activity(f"C/L{n}")
        self.assertEqual(self.data("activity", "C/L1")["status"], "ongoing")
        self.act("activity.create", {"id": "C/L4", "course_id": "C", "activity_type": "lesson", "title": "four"})
        with self.assertRaisesRegex(DomainError, "capacity"):
            self.act("activity.start", {"id": "C/L4"})
        self.assertEqual(self.data("course", "C")["current_activity_id"], "C/L3")

    def test_close_revision_invalidates_old_intent_and_rejects_teacher_confirmation(self):
        self.course()
        self.activity()
        old = self.close()
        latest = self.close("修订的完整复盘与未完内容")
        self.assertNotEqual(old, latest)
        with self.assertRaisesRegex(DomainError, "current complete proposal"):
            self.act("activity.close.confirm", {"id": "C/L1", "body_sha256": old, "outcome": "closed_incomplete"})
        with self.assertRaisesRegex(DomainError, "student decision"):
            self.act("activity.close.confirm", {"id": "C/L1", "body_sha256": latest, "outcome": "closed_incomplete"}, role="teacher")
        self.act("activity.close.confirm", {"id": "C/L1", "body_sha256": latest, "outcome": "closed_incomplete"}, text="确认未完成关闭")
        self.assertEqual(self.data("activity", "C/L1")["status"], "closed_incomplete")
        self.act("activity.reopen", {"id": "C/L1", "reason": "补做余下部分"})
        self.assertEqual(len([e for e in self.state["objects"].values() if e["kind"] == "close"]), 1)

    def test_withdraw_close_produces_no_close_fact(self):
        self.course()
        self.activity()
        sha = self.close()
        self.act("activity.close.withdraw", {"id": "C/L1", "body_sha256": sha})
        self.assertEqual(self.data("activity", "C/L1")["status"], "ongoing")
        self.assertFalse(any(e["kind"] == "close" for e in self.state["objects"].values()))

    def test_checkpoint_and_time_facts_are_distinct(self):
        self.course()
        self.activity()
        for status in ("queued", "arrived", "pending", "confirmed"):
            self.act("checkpoint.record", {"id": "N1", "activity_id": "C/L1", "status": status, "position": "page 1", "evidence": ["student-expression"]})
        self.assertEqual(self.data("activity", "C/L1")["status"], "ongoing")
        self.act("time.record", {"id": "span", "activity_id": "C/L1", "quality": "estimated", "seconds": 120, "started_at": "2026-09-30T03:59:00-04:00"})
        self.assertEqual(self.data("timespan", "span")["learning_day"], "2026-09-29")
        with self.assertRaises(DomainError):
            self.act("time.record", {"id": "span", "activity_id": "C/L1", "quality": "unknown"})

    def test_group_candidate_requires_actual_activation_and_one_active_group(self):
        self.course()
        for identity in ("G1", "G2"):
            self.act("group.propose", {"id": identity, "members": ["C"], "capacity": 1, "calendar": {"frequency": "weekly", "stagnation_days": 14}, "thresholds": {"close_condition": "milestone verified"}, "goal": "learn"})
        self.assertEqual(self.data("group", "G1")["status"], "planned")
        sha = self.data("group", "G1")["proposal_sha256"]
        self.act("group.activate", {"id": "G1", "proposal_sha256": sha})
        with self.assertRaises(DomainError):
            self.act("group.activate", {"id": "G2", "proposal_sha256": self.data("group", "G2")["proposal_sha256"]})
        with self.assertRaises(DomainError):
            self.act("group.close", {"id": "G1", "proposal_sha256": sha, "threshold_judgment": "met", "evidence": ["actual-group-review"]})
        self.assertEqual(self.data("group", "G1")["status"], "active")
        self.assertEqual(self.data("course", "C")["status"], "ongoing")

    def test_reading_upgrade_and_flexible_binding_do_not_duplicate_progress(self):
        self.course()
        self.act("reading.create", {"id": "AR0001", "intent": "survey", "resources": ["book-a", "book-b"]})
        self.act("reading.transition", {"id": "AR0001", "status": "upgraded", "course_id": "C", "scope": "chosen chapter"})
        self.act("binding.create", {"id": "R1", "course_ids": ["C"], "intent": "flexible practice"})
        self.assertNotIn("progress", self.data("reading", "AR0001"))
        self.assertEqual(self.data("binding", "R1")["budget_weight"], 0)

    def test_retired_ids_and_aliases_do_not_shadow_history(self):
        self.course()
        self.act("registry.alias", {"id": "old-C", "kind": "course", "target_id": "C"})
        self.act("registry.retire", {"id": "retire-C", "kind": "course", "target_id": "C", "reason": "reorganized", "successor_ids": []})
        with self.assertRaises(DomainError):
            self.act("course.create", {"id": "C", "title": "new", "course_type": "mastery", "learning_mode": "goal"})

    def test_suggestion_is_not_adopted_without_implementation(self):
        self.act("suggestion.propose", {"id": "S1", "body": "add course", "owner": "teacher", "scope": "plan"})
        with self.assertRaises(DomainError):
            self.act("suggestion.decide", {"id": "S1", "status": "adopted"})
        self.assertEqual(self.data("suggestion", "S1")["status"], "proposed")

    def test_thoughts_cannot_be_relabelled_teacher_text(self):
        self.course()
        with self.assertRaises(DomainError):
            self.act("thought.record", {"id": "T", "course_id": "C", "body": "teacher rewrite", "evidence": ["answer"]}, text="actual student expression")

    def test_rule_and_issue_recurrence_keep_history(self):
        self.act("issue.open", {"id": "P1", "problem": "wrong source", "root_cause": "source substitution", "scope": "teach"})
        self.act("issue.resolve", {"id": "P1", "resolution": "source gate", "enforcement": "tool", "verification": "negative scenario", "evidence": ["test-result"]})
        self.act("issue.recur", {"id": "P1", "evidence": ["second-incident"]})
        self.assertEqual(len(self.data("issue", "P1")["occurrences"]), 2)
        with self.assertRaises(DomainError):
            self.act("rule.register", {"id": "R", "body": "verify source", "owner": "source", "failure_signal": "mismatch", "enforcement": "tool", "consumer": "present"})

    def test_external_copy_and_frozen_drift_are_not_silently_rebased(self):
        body = "frozen bytes"
        sha = support.hashlib.sha256(body.encode()).hexdigest()
        self.act("external.register", {"id": "E", "identity": "external-contract-v1", "mode": "frozen", "contract": "T1", "content_sha256": sha})
        changed = "new bytes"
        with self.assertRaisesRegex(DomainError, "changed"):
            self.act("external.consume", {"id": "U", "reference_id": "E", "body": changed, "observed_sha256": support.hashlib.sha256(changed.encode()).hexdigest(), "used_at": "2026-09-30"})

    def test_budget_does_not_reset_or_reactivate_on_lower_observation(self):
        self.act("campaign.create", {"id": "B", "scope": "repair-P1", "token_limit": 100, "repair_limit": 2})
        self.act("campaign.observe", {"id": "B", "tokens": 100, "repairs": 1, "measurement_source": "receipt"})
        self.assertEqual(self.data("campaign", "B")["status"], "stopped_budget")
        with self.assertRaises(DomainError):
            self.act("campaign.observe", {"id": "B", "tokens": 50, "repairs": 1, "measurement_source": "reset"})


if __name__ == "__main__":
    unittest.main()
