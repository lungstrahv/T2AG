"""Non-author semantic regression cases. Synthetic inputs, not agent metrics."""
from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch

from t2ag_next import learning, support, service, exchange, reconciliation
from t2ag_next.model import DomainError
from t2ag_next.journal import Journal


class DomainReviewTests(unittest.TestCase):
    def setUp(self):
        self.state = {"revision": 1, "objects": {}}
        self.obj("course", "C", {"course_type": "mastery", "learning_mode": "goal", "status": "ongoing"})
        self.obj("activity", "C/L", {"course_id": "C", "activity_type": "lesson", "status": "ongoing"})

    def obj(self, kind, identity, data):
        self.state["objects"][kind + "/" + identity] = {"kind": kind, "id": identity, "version": 1, "data": deepcopy(data)}

    def request(self, action, payload, text="确认结课", role="student"):
        return {"request_id": "review-case", "action": action, "payload": payload,
                "actor": {"role": role, "source": "synthetic-review-message", "text": text},
                "expected": {k: e["version"] for k, e in self.state["objects"].items()}}

    def proposal(self, outcome="completed"):
        proposal = {"activity_id": "C/L", "activity_type": "lesson", "body": "Complete review shown",
                    "outcome": outcome, "presentation_ref": "prior-message", "reconciliation": {"checkpoint_ids": ["cp"]}}
        self.obj("checkpoint", "cp", {"activity_id": "C/L", "status": "confirmed"})
        self.obj("activity", "C/L", {"course_id": "C", "activity_type": "lesson", "status": "pending_close",
                                      "pending_close": proposal, "pending_sha256": support.digest(proposal)})
        return {"id": "C/L", "body_sha256": support.digest(proposal), "outcome": outcome}

    def test_sup_r1_new_open_question_invalidates_old_completed_proposal(self):
        payload = self.proposal()
        self.obj("question", "Q-new", {"activity_id": "C/L", "status": "open", "text": "New unresolved question"})
        with self.assertRaises(DomainError):
            support.plan(self.state, self.request("activity.close.confirm", payload))

    def test_sup_r1_new_uncovered_block_invalidates_old_completed_proposal(self):
        payload = self.proposal()
        self.obj("block", "new", {"activity_id": "C/L", "status": "planned", "coverage": "uncovered"})
        with self.assertRaises(DomainError):
            support.plan(self.state, self.request("activity.close.confirm", payload))

    def test_sup_r2_explicit_refusal_is_not_close_consent(self):
        payload = self.proposal("closed_incomplete")
        with self.assertRaises(DomainError):
            support.plan(self.state, self.request("activity.close.confirm", payload, text="不要结课，只是保存"))

    def test_sup_r3_learning_review_is_consumed_through_attempt(self):
        self.obj("activity", "C/E", {"course_id": "C", "activity_type": "exercise", "status": "ongoing"})
        self.obj("exercise", "C/E", {"activity_id": "C/E", "source_order": ["P1"], "problems": {"P1": {}},
                                      "review_ids": ["R1"]})
        self.obj("attempt", "A1", {"activity_id": "C/E", "answers": [{"problem_id": "P1", "text": "actual answer"}]})
        self.obj("review", "R1", {"attempt_id": "A1", "criterion_id": "rubric", "ratings": [{"problem_id": "P1", "verdict": "correct"}]})
        payload = {"id": "C/E", "body": "Actual reviewed exercise", "outcome": "completed",
                   "presentation_ref": "shown", "reconciliation": {"order": "source_order"}}
        effects = support.plan(self.state, self.request("activity.close.propose", payload, role="teacher"))
        self.assertEqual(effects[0]["data"]["status"], "pending_close")

    def test_sup_r8_merged_question_does_not_block_closed_canonical_question(self):
        payload=self.proposal()
        self.obj("question","Q-old",{"activity_id":"C/L","status":"merged","merged_into":"Q-main","text":"Original question retained."})
        self.obj("question","Q-main",{"activity_id":"C/L","status":"closed","text":"Canonical question.","merged_sources":[{"question_id":"Q-old"}]})
        effects=support.plan(self.state,self.request("activity.close.confirm",payload))
        self.assertEqual(effects[0]["data"]["status"],"completed")

    def test_learn_r1_supplement_does_not_rewrite_original_source_order(self):
        self.obj("activity", "C/E", {"course_id": "C", "activity_type": "exercise", "status": "ongoing"})
        self.obj("exercise", "C/E", {"course_id": "C", "activity_id": "C/E", "problems": {},
                                      "source_order": [], "teaching_sequence": [], "assistance": []})
        effects = learning.plan(self.state, self.request("problem.add", {"activity_id": "C/E", "problem_id": "extra",
            "origin": "teacher_generated", "text": "Teacher supplemental problem"}, text="请加练"))
        exercise = next(e["data"] for e in effects if e["kind"] == "exercise")
        self.assertEqual(exercise["source_order"], [])
        self.assertIn("extra", exercise["teaching_sequence"])

    def test_learn_r2_assisted_exam_cannot_be_reported_independent_pass(self):
        self.obj("exam", "EX", {"activity_id": "C/E", "status": "submitted", "attempt_id": "A",
                                "criterion_id": "CR", "timed_out": False, "problem_ids": ["P"]})
        self.obj("attempt", "A", {"activity_id": "C/E", "exam_id": "EX", "criterion_id": "CR",
            "answers": [{"problem_id": "P", "text": "previously supplied solution"}],
            "assistance": {"P": {"level": "solution", "polluted": False}}})
        self.obj("criterion", "CR", {"problem_ids": ["P"], "max_scores": {"P": 1}, "pass_score": 1})
        request = self.request("exam.grade", {"exam_id": "EX", "review_id": "R", "ratings": [
            {"problem_id": "P", "verdict": "correct", "rationale": "Correct after seeing solution", "score": 1}]}, role="teacher")
        try:
            effects = learning.plan(self.state, request)
        except DomainError:
            return  # Explicit isolation rejection is also an acceptable result.
        result = next(e["data"] for e in effects if e["kind"] == "exam")
        self.assertIsNot(result["passed"], True)

    def test_svc_r1_unknown_or_zero_domain_selection_is_not_green(self):
        for kinds,code in [(["coures"],"UNKNOWN_CHANGED_KIND"),(["skin"],"NO_DOMAIN_CHECKS")]:
            with self.assertRaises(DomainError) as caught:
                service.check_plan(self.state,kinds)
            self.assertEqual(caught.exception.code,code)

    def test_svc_r3_real_but_unrelated_rejection_is_not_rule_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Journal(folder); store.initialize({"language":"en"})
            candidate={"request_id":"negative-candidate","action":"course.activate","payload":{"id":"absent-course"},
                "actor":{"role":"teacher","source":"synthetic-negative","text":"Try activation."},"expected":{}}
            service.validate_negative(folder,"wrong-precondition",candidate,"NOT_FOUND")
            state=store.read_state()
            request={"request_id":"register-rule","action":"gov.rule.register","payload":{"id":"R",
                "body":"Course activation requires an explicit student decision.","owner":"course","failure_signal":"STUDENT_DECISION_REQUIRED","protection":"ordinary",
                "clauses":{"permission":"A teacher cannot substitute for the actual student activation decision."},
                "enforcement":"tool","consumer_refs":[{"kind":"student","id":"current"}],"implementation_ref":"action:course.activate","negative_validation_id":"wrong-precondition",
                "enforcement_type":["gate","program"],"decision_owner":"student","actual_executor":"action:course.activate",
                "evidence":[{"kind":"student","id":"current"}],"wake":"Code or protected object changes.","stale":["object_change","validator_change"],"bypass":"Attributed input is not host identity authentication."},
                "actor":{"role":"teacher","source":"synthetic-rule","text":"Register this precise rule."},
                "expected":{k:v["version"] for k,v in state["objects"].items()}}
            with self.assertRaises(DomainError) as caught:service.execute(folder,request)
            self.assertEqual(caught.exception.code,"GOVERNANCE_NEGATIVE",
                "NOT_FOUND before the authorization branch does not prove STUDENT_DECISION_REQUIRED; reject for that mismatch, not a retired action.")
            self.assertEqual(store.read_state(),state)

    def test_svc_r2_paused_status_cannot_be_learning_ready(self):
        self.state["objects"]["course/C"]["data"].update(status="paused",current_activity_id="C/L")
        with patch.object(service.Journal,"read_state",return_value=self.state):
            result=service.context("unused-review-fixture",entry="entry.teach",session_lane="teach",scope="C")
        self.assertFalse(result["learning_ready"])
        self.assertEqual(result["waiting_for"],"resume_course")

    def test_learn_r3_unverified_imported_page_cannot_form_scope(self):
        self.obj("source","S",{"course_ids":["C"],"page_count":5,"content_sha256":"a"*64})
        ids=[]
        for n in range(1,6):
            pid="p"+str(n);ids.append(pid)
            self.obj("page",pid,{"source_id":"S","pdf_page_index":n,"verification":{"status":"unresolved"},"migration_requires_reconciliation":True})
        with self.assertRaises(DomainError):
            learning.plan(self.state,self.request("scope.create",{"scope_id":"scope","activity_id":"C/L","source_id":"S","page_ids":ids,"current_page_id":"p1"},role="teacher"))

    def test_learn_r4_paused_course_cannot_start_teaching_session(self):
        self.state["objects"]["course/C"]["data"]["status"]="paused"
        with self.assertRaises(DomainError):
            learning.plan(self.state,self.request("session.start",{"session_id":"new-session","activity_id":"C/L"},role="teacher"))

    def test_sup_r6_imported_paused_course_can_explicitly_resume(self):
        self.state["objects"]["course/C"]["data"]["status"] = "paused"
        effects = support.plan(self.state,self.request("course.resume",{"id":"C"},text="明确恢复课程"))
        self.assertEqual(effects[0]["data"]["status"], "ongoing")
        self.assertFalse(effects[0]["data"].get("paused", False))

    def test_sup_r7_correction_cannot_fork_an_already_corrected_timespan(self):
        self.obj("timespan","T1",{"activity_id":"C/L","quality":"exact","seconds":60,"learning_day":"2026-09-30"})
        self.obj("timespan","T2",{"activity_id":"C/L","quality":"exact","seconds":120,"learning_day":"2026-09-30","corrects":"T1"})
        with self.assertRaises(DomainError):
            support.plan(self.state,self.request("time.record",{"id":"T3","activity_id":"C/L","quality":"exact","seconds":180,
                "started_at":"2026-09-30T12:00:00-04:00","corrects":"T1"}))

    def test_rec_r1_source_mapping_cannot_assign_mastery_mode_to_project_course(self):
        data={"course_type":"project","status":"ongoing","learning_mode":None,"legacy":{"path":"frozen/course.md"},
              "original_body":"course_type: project; project delivery uses external verification.","uncertainties":["legacy_driver_conflict"]}
        self.obj("course","P",data)
        payload={"id":"RC1","target_kind":"course","target_id":"P","changes":{"learning_mode":"project"},
            "resolves":["legacy_driver_conflict"],"basis":"source_evidence","rationale":"Literal word occurs in the original.",
            "evidence":[{"kind":"course","id":"P","field":"original_body","value_sha256":support.digest(data["original_body"]),"excerpt":data["original_body"]}]}
        with self.assertRaises(DomainError): reconciliation.plan(self.state,self.request("migration.reconcile",payload,role="teacher"))

    def test_rec_r2_group_mapping_cannot_manufacture_completed_keystones(self):
        data={"status":"active","members":["C"],"capacity":1,"container_mode":"progress","keystone_ids":["N1"],
            "completed_keystone_ids":[],"keystone_total_frozen":1,"legacy":{"path":"frozen/group.md"},
            "original_body":"One course with a future milestone N1.","uncertainties":["capacity_mapping_unknown"]}
        self.obj("group","G",data)
        payload={"id":"RC2","target_kind":"group","target_id":"G","changes":{"completed_keystone_ids":["N1"]},
            "resolves":["capacity_mapping_unknown"],"basis":"student_resolution","rationale":"Resolve capacity.",
            "evidence":[{"kind":"group","id":"G","field":"original_body","value_sha256":support.digest(data["original_body"]),"excerpt":data["original_body"]}]}
        with self.assertRaises(DomainError): reconciliation.plan(self.state,self.request("migration.reconcile",payload,text="确认组容量为一门课程。"))

    def test_sup_reading_numbering_accounts_for_legacy_hyphenated_ids(self):
        self.obj("reading","AR-0003",{"status":"paused","kind":"reading"})
        with self.assertRaises(DomainError):
            support.plan(self.state,self.request("reading.create",{"id":"AR0001","intent":"new"}))
        effects=support.plan(self.state,self.request("reading.create",{"id":"AR0004","intent":"new"}))
        self.assertEqual(effects[0]["id"],"AR0004")

    def test_sup_internal_engagement_records_do_not_take_external_governance(self):
        for governance in ("internal","external"):
            self.obj("engagement",governance,{"governance":governance,"status":"active"})
        payload={"id":"entry","engagement_id":"internal","entry_kind":"word","body":"A vocabulary record","evidence":["actual input"]}
        effects=support.plan(self.state,self.request("engagement.entry.record",payload))
        self.assertEqual(effects[0]["data"]["engagement_id"],"internal")
        payload["engagement_id"]="external"
        with self.assertRaises(DomainError): support.plan(self.state,self.request("engagement.entry.record",payload))

    def test_sup_r5_one_completion_cannot_claim_unrelated_group_milestone(self):
        self.obj("checkpoint","CP1",{"course_id":"C","activity_id":"C/L","position":"N1","status":"confirmed"})
        self.obj("completion","DONE1",{"course_id":"C","judgment_kind":"comprehension","evidence_ids":["CP1"]})
        self.obj("group","G",{"status":"active","members":["C"],"keystone_ids":["N1","N2"],
            "completed_keystone_ids":["N1"],"keystone_evidence":{"N1":"DONE1"}})
        with self.assertRaises(DomainError):
            support.plan(self.state,self.request("group.keystone.complete",{"id":"G","keystone_id":"N2","completion_id":"DONE1"}))

    def test_sup_r5_new_completion_identity_cannot_relabel_old_checkpoint(self):
        self.obj("checkpoint","CP1",{"course_id":"C","activity_id":"C/L","position":"N1","status":"confirmed"})
        for cid in ("DONE1", "DONE2"):
            self.obj("completion",cid,{"course_id":"C","judgment_kind":"comprehension","evidence_ids":["CP1"]})
        self.obj("group","G",{"status":"active","members":["C"],"keystone_ids":["N1","N2"],
            "completed_keystone_ids":["N1"],"keystone_evidence":{"N1":"DONE1"}})
        with self.assertRaises(DomainError):
            support.plan(self.state,self.request("group.keystone.complete",{"id":"G","keystone_id":"N2","completion_id":"DONE2"}))

    def test_sup_contribution_reference_requires_current_real_candidate_hash(self):
        env=exchange.envelope("reading_contribution","con","reader","local","C",1,{"note":"new"})
        self.obj("contribution","con",{"envelope":env,"status":"candidate","scope":"C"})
        payload={"id":"thought","course_id":"C","body":"My actual statement","evidence":["student input"],
            "contribution_refs":[{"kind":"contribution","id":"con","sha256":"0"*64}]}
        with self.assertRaises(DomainError):
            support.plan(self.state,self.request("thought.record",payload,text=payload["body"]))

    def test_sup_r4_rule_strings_are_not_execution_evidence(self):
        self.obj("rule","R",{"status":"active","enforcement":"tool",
            "implementation_ref":"action:nonexistent.action","negative_evidence":"made-up"})
        with patch.object(service.Journal,"read_state",return_value=self.state):
            result=service.doctor("unused-review-fixture",changed_kinds=["rule"])
        self.assertFalse(result["ok"])
        self.assertTrue(any(f["code"]=="rule.broken_implementation" for f in result["findings"]))
        self.state["objects"]["rule/R"]["data"]["implementation_ref"]="action:student.update"
        with patch.object(service.Journal,"read_state",return_value=self.state):
            result=service.doctor("unused-review-fixture",changed_kinds=["rule"])
        self.assertTrue(result["review_required"])
        self.assertTrue(any(f["code"]=="rule.unverified_negative_evidence" for f in result["findings"]))

    def test_exch_r1_preexisting_unrelated_thought_is_not_consumption(self):
        self.obj("bridge","current",{"paused":False,"instance_id":"local","instance_kind":"personal_instance","trusted_sources":["reader"]})
        self.obj("thought","old",{"course_id":"C","body":"Unrelated earlier student thought","evidence":["another-source"]})
        env=exchange.envelope("reading_contribution","new","reader","local","C",1,{"note":"New contribution"})
        self.obj("contribution","new",{"envelope":env,"status":"candidate","scope":"C","imported_at_revision":1,"consumption":None})
        payload={"id":"new","target_kind":"thought","target_id":"old",
            "target_sha256":support.digest(self.state["objects"]["thought/old"]["data"]),
            "content_sha256":env["content_sha256"],"consumption_ref":"mere fabricated label"}
        with self.assertRaises(DomainError):
            exchange.plan(self.state,self.request("bridge.receipt.prepare",payload))

    def test_learn_r5_corrected_review_is_not_new_reinforcement_answer(self):
        from test_learning import Instance
        i = Instance(); aid = i.exam_bank(); selected = i.start_exam(aid)
        for n in range(len(selected["problem_ids"])+1):
            i.call("exam.reminder", {"exam_id":"E1", "problem_id":selected["problem_ids"][0],
                "level":"clarification", "content":"Clarify the original condition.",
                "student_request":{"role":"student","source":f"request-{n}","text":"Please clarify the condition."}})
        checks = i.submit_exam()
        i.call("exam.grade", {"exam_id":"E1","review_id":"exam-grade","point_verdicts":checks})
        i.call("exam.reinforcement.configure", {"exam_id":"E1","activity_ids":[aid],"purpose":"Practice independent reading."}, "Use these three learning dates.")
        review = i.attempt(aid, "one-answer")
        for n in (1,2):
            i.call("time.record", {"id":f"day-{n}","activity_id":aid,"quality":"exact","seconds":300,"started_at":f"2026-10-0{n}T12:00:00Z"})
        i.call("exam.reinforcement.record", {"exam_id":"E1","timespan_id":"day-1","evidence_refs":[{"kind":"review","id":review}]})
        i.call("review.record", {"review_id":"correction-of-same-answer","attempt_id":"one-answer","criterion_id":"rubric-v1",
            "supersedes":review,"correction_reason":"Clarified grading rationale; no new student work.",
            "ratings":[{"problem_id":"q1","verdict":"correct","score":10,"rationale":"The condition is stated in the same original answer."}]})
        with self.assertRaises(DomainError):
            i.call("exam.reinforcement.record", {"exam_id":"E1","timespan_id":"day-2","evidence_refs":[{"kind":"review","id":"correction-of-same-answer"}]})

    def test_learn_r6_grading_correction_cannot_fork_an_existing_correction(self):
        from test_learning import Instance
        i=Instance(); aid=i.exercise(); review=i.attempt(aid,"answer")
        payload={"attempt_id":"answer","criterion_id":"rubric-v1","supersedes":review,"correction_reason":"Clarify rationale.",
            "ratings":[{"problem_id":"q1","verdict":"correct","score":10,"rationale":"Actual original answer states the condition."}]}
        i.call("review.record", {**payload,"review_id":"correction-1"})
        with self.assertRaises(DomainError):
            i.call("review.record", {**payload,"review_id":"fork-from-old"})


if __name__ == "__main__":
    unittest.main()
