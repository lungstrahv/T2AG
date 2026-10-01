"""Author tests of real named actions; synthetic learners, never agent metrics."""
from copy import deepcopy
import tempfile
import unittest

from t2ag_next import planning as p, support, learning
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, get, key


class PlanningJourneys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.j = Journal(self.tmp.name)
        self.j.initialize({"language": "zh", "facts_status": "not_provided"})
        self.n = 0

    def tearDown(self): self.tmp.cleanup()

    def call(self, action, payload, student=None):
        self.n += 1
        state = self.j.read_state()
        request = {"request_id": f"p-{self.n}", "action": action, "payload": payload,
                   "actor": {"role": "teacher" if student is None else "student", "source": f"synthetic-message-{self.n}", "text": student if student is not None else "Record this attributed observation."},
                   "expected": {k: v["version"] for k, v in state["objects"].items()}}
        module = p if action in p.ACTIONS else learning if action in learning.ACTIONS else support
        return self.j.apply(request, module.plan)

    def data(self, kind, ident): return get(self.j.read_state(), kind, ident)

    def proposal(self, *, language="zh", group=False, mode="goal"):
        if language == "en": self.call("student.update", {"id": "current", "declarations": {"language": "en"}}, "Use English.")
        self.call("planning.conditions.record", {"id": "conditions", "conditions": {"time": {"status": "not_provided"}, "route": {"status": "public_assumption", "value": "Editable beginner route."}}})
        course = {"id": "C", "title": "Course title", "course_type": "mastery", "learning_mode": mode,
                  "goal": "Understand the basic reasoning.", "mode_explanation": "Build understanding in observable steps.",
                  "first_activity": {"id": "C/L1", "title": "First learning step", "activity_type": "lesson"}}
        if mode == "textbook":
            raw = "Synthetic source."
            course["new_sources"] = [{"source_id": "S", "title": "Synthetic textbook", "format": "text", "source_version": "1", "content": raw, "content_sha256": learning.digest(raw)}]
        payload = {"id": "P", "conditions_id": "conditions", "sections": {name: f"Complete {name}." for name in p.SECTIONS}, "courses": [course]}
        if group: payload["group"] = {"id": "G", "capacity": 1, "calendar": {"frequency": 3, "stagnation_days": 6}, "thresholds": {"close_condition": "Every displayed stage is reconciled."}, "goal": "A sustainable start.", "container_mode": "progress", "keystone_ids": ["First understanding", "Independent application"], "presentation": "One course with these two stages."}
        self.call("planning.propose", payload)
        return payload

    def present(self):
        d = self.data("learning_plan", "P")
        self.call("planning.present", {"id": "P", "proposal_sha256": d["proposal_sha256"], "presented_body": d["body"], "presentation_ref": "actual-host-delivery-fixture"})
        return d["proposal_sha256"]

    def test_full_plan_and_group_commits_once_after_display_and_real_acceptance(self):
        self.proposal(group=True)
        before = self.j.read_state()
        self.assertNotIn("course/C", before["objects"])
        sha = self.present(); revision = self.j.read_state()["revision"]
        result = self.call("planning.confirm", {"id": "P", "proposal_sha256": sha}, "按这份方案建立课程，可以开始。")
        self.assertEqual(self.j.read_state()["revision"], revision + 1)
        self.assertEqual(self.data("course", "C")["current_activity_id"], "C/L1")
        self.assertEqual(self.data("group", "G")["status"], "active")
        self.assertEqual(self.data("learning_plan", "P")["status"], "accepted")
        self.assertNotIn("learning_segment", {e["kind"] for e in self.j.read_state()["objects"].values()})

    def test_empty_optional_conditions_never_create_default_student_fact(self):
        self.call("planning.conditions.record", {"id": "C", "conditions": {}})
        self.assertEqual(self.data("planning_conditions", "C")["conditions"], {})
        self.assertEqual(self.data("student", "current")["facts_status"], "not_provided")
        with self.assertRaises(DomainError): self.call("planning.conditions.record", {"id": "bad", "conditions": {"level": {"status": "not_provided", "value": "middle school"}}})
        with self.assertRaises(DomainError): self.call("planning.conditions.record", {"id": "bad", "conditions": {"level": {"status": "provided", "value": "beginner", "student": {"role": "teacher", "text": "beginner", "source": "fixture"}}}})

    def test_summary_refusal_and_changed_conditions_do_not_create_courses(self):
        self.proposal(); d = self.data("learning_plan", "P")
        with self.assertRaises(DomainError): self.call("planning.present", {"id": "P", "proposal_sha256": d["proposal_sha256"], "presented_body": "Summary only", "presentation_ref": "file"})
        sha = self.present()
        with self.assertRaises(DomainError): self.call("planning.confirm", {"id": "P", "proposal_sha256": sha}, "不要建立，只是保存方案。")
        self.call("planning.conditions.record", {"id": "conditions", "conditions": {}})
        with self.assertRaises(DomainError): self.call("planning.confirm", {"id": "P", "proposal_sha256": sha}, "我确认按这份方案建立课程。")
        self.assertNotIn("course/C", self.j.read_state()["objects"])

    def test_revision_preserves_old_body_and_invalidates_old_acceptance(self):
        payload = self.proposal(); sha = self.present()
        payload["sections"]["route"] = "Revised actual route."
        self.call("planning.revise", payload)
        with self.assertRaises(DomainError): self.call("planning.confirm", {"id": "P", "proposal_sha256": sha}, "我确认按这份方案建立课程。")
        self.assertEqual(self.data("learning_plan", "P")["status"], "draft")
        self.assertEqual(sum(e["kind"] == "learning_plan_revision" for e in self.j.read_state()["objects"].values()), 1)

    def test_english_textbook_initial_source_and_activity_are_one_transaction(self):
        self.proposal(language="en", mode="textbook"); sha = self.present()
        self.assertIn("Your goal", self.data("learning_plan", "P")["body"])
        revision = self.j.read_state()["revision"]
        self.call("planning.confirm", {"id": "P", "proposal_sha256": sha}, "Yes, create the course using this plan.")
        self.assertEqual(self.j.read_state()["revision"], revision+1)
        self.assertEqual(self.data("source", "S")["course_ids"], ["C"])
        self.assertEqual(self.data("course", "C")["source_ids"], ["S"])

    def test_late_invalid_group_leaves_no_partial_course(self):
        self.proposal(group=True); sha=self.present()
        # Establish another group via real actions after presentation.
        self.call("course.create", {"id":"D","title":"Other","course_type":"praxis"}, "Create another course.")
        self.call("course.activate", {"id":"D"}, "Activate this course.")
        self.call("group.propose", {"id":"OTHER","members":["D"],"capacity":1,"calendar":{"frequency":1,"stagnation_days":3},"thresholds":{"close_condition":"actual evidence"},"goal":"Other group"})
        self.call("group.activate", {"id":"OTHER","proposal_sha256":self.data("group","OTHER")["proposal_sha256"]}, "Activate this group.")
        revision=self.j.read_state()["revision"]
        with self.assertRaises(DomainError) as caught:
            self.call("planning.confirm", {"id":"P","proposal_sha256":sha}, "我确认按这份方案建立课程。")
        self.assertEqual(caught.exception.code, "ACTIVE_GROUP_EXISTS")
        self.assertEqual(self.j.read_state()["revision"],revision)
        self.assertNotIn("course/C",self.j.read_state()["objects"])

    def test_confirmation_rejects_negation_questions_reports_and_qualified_assent_without_writes(self):
        self.proposal(group=True); sha = self.present()
        before = self.j.read_state()
        for statement in (
            "我不能确认建立这个方案。", "不可以建立。", "I don't approve this plan.",
            "我同意这份方案吗？", "我确认按这份方案建立课程？", "I approve this complete plan?",
            "老师说：我同意这份方案。", '"I approve this complete plan."',
            "She said I approve this plan.", "If the schedule changes, I approve this plan.",
            "我同意这份方案，但先别建立课程。", "I approve this plan, but don't create courses.",
            "只是保存，我同意这份方案。", "I approve this plan. Only save it for now.",
            "假设我说我同意这份方案。", "I do not disagree that I could approve this plan.",
            "I approve this complete plan.\nDo not act yet.",
        ):
            with self.subTest(statement=statement):
                with self.assertRaises(DomainError) as caught:
                    self.call("planning.confirm", {"id":"P", "proposal_sha256":sha}, statement)
                self.assertEqual(caught.exception.code, "PLAN_NOT_ACCEPTED")
                self.assertEqual(self.j.read_state(), before)
        statement = "我确认按这份方案建立课程。"
        self.call("planning.confirm", {"id":"P", "proposal_sha256":sha}, statement)
        self.assertEqual(self.data("learning_plan", "P")["decision"]["text"], statement)
        self.assertEqual(self.j.read_state()["revision"], before["revision"] + 1)

    def test_natural_complete_plan_choice_needs_no_password_and_preserves_attribution_limits(self):
        self.proposal(group=True);sha=self.present()
        original="这个安排很合适，就照你刚展示的完整方案开始吧。"
        self.call("planning.confirm", {"id":"P","proposal_sha256":sha},original)
        decision=self.data("learning_plan","P")["decision"]
        self.assertEqual(decision["text"],original)
        self.assertEqual(decision["decision_basis"]["formal_choice"],"planning.confirm")
        self.assertFalse(decision["decision_basis"]["host_identity_authenticated"])
        self.assertFalse(decision["decision_basis"]["semantic_intent_machine_verified"])

    def test_teacher_versions_and_scoped_overlay_cannot_relax_a_gate(self):
        self.call("teacher.register", {"id":"T","name":"Template","template":"Original style","overlay":{}})
        self.call("teacher.template.revise", {"id":"T","template":"Revised style","reason":"More readable."})
        self.assertTrue(any(e["kind"]=="teacher_revision" and e["data"]["before"]["template"]=="Original style" for e in self.j.read_state()["objects"].values()))
        self.call("course.create", {"id":"C","title":"Course","course_type":"praxis","teacher_id":"T"}, "Create course.")
        with self.assertRaises(DomainError): self.call("teacher.overlay.revise", {"id":"O","course_id":"C","preferences":{"skip_gate":True},"reason":"faster"}, "Skip gates.")
        self.call("teacher.overlay.revise", {"id":"O","course_id":"C","preferences":{"pace":"slower"},"reason":"Explicit preference."}, "Use a slower pace.")
        self.assertEqual(self.data("course","C")["teacher_overlay_id"],"O")

    def test_full_plan_displays_bound_teacher_and_preserved_material_identity(self):
        from t2ag_next.model import put
        self.call("teacher.register", {"id":"T1","name":"Named teaching role","template":"Observable teaching style.","overlay":{}})
        # A preserved imported source may already declare its planned course.
        # Fixture creation is internal; all proposal/presentation/confirmation steps are real named actions.
        state = self.j.read_state()
        self.j.apply({"request_id":"imported-source-fixture", "action":"migration.fixture", "payload":{},
            "actor":{"role":"system","source":"synthetic-import","text":"Preserved material."}, "expected":{}},
            lambda s,r:[put("source","OLD",{"course_ids":["C"],"title":"Preserved textbook title","source_version":"edition-2","format":"text","content":"Synthetic source.","content_sha256":learning.digest("Synthetic source.")})])
        payload = self.proposal(); payload["courses"][0].update(teacher_id="T1", source_ids=["OLD"])
        payload["sections"] = {name: "This is the complete proposed arrangement." for name in p.SECTIONS}
        self.call("planning.revise", payload)
        proposed = self.data("learning_plan", "P")
        body = proposed["body"]
        self.assertIn("Named teaching role", body)
        self.assertIn("Preserved textbook title", body)
        self.assertIn("edition-2", body)
        self.assertNotIn("(T1)", body)
        self.assertNotIn("(OLD;", body)
        self.assertNotIn("goal_and_time", body)
        self.assertEqual(proposed["courses"][0]["teacher_id"], "T1")
        self.assertEqual(proposed["courses"][0]["source_ids"], ["OLD"])
        self.assertIn("teacher/T1", proposed["reference_versions"])
        self.assertIn("source/OLD", proposed["reference_versions"])
        unsigned = {k: deepcopy(v) for k, v in proposed.items() if k != "proposal_sha256"}
        self.assertEqual(p.digest(unsigned), proposed["proposal_sha256"])
        unsigned["courses"][0]["teacher_id"] = "T2"
        self.assertNotEqual(p.digest(unsigned), proposed["proposal_sha256"])
        sha = self.present()
        self.call("teacher.template.revise", {"id":"T1","template":"Changed after display.","reason":"Real revision."})
        with self.assertRaises(DomainError) as caught:
            self.call("planning.confirm", {"id":"P","proposal_sha256":sha}, "我确认按这份方案建立课程。")
        self.assertEqual(caught.exception.code, "PLAN_REFERENCES_CHANGED")
        self.assertNotIn("course/C", self.j.read_state()["objects"])

    def test_reading_without_course_can_keep_notes_and_multiple_resources(self):
        self.call("reading.create", {"id":"AR-0001","intent":"Understand a broad topic."})
        self.call("reading.note.record", {"id":"NOTE1","reading_id":"AR-0001","body":"My exact reading note.","evidence":["page-reference"]}, "My exact reading note.")
        self.call("reading.resources.append", {"id":"append1","reading_id":"AR-0001","resources":[{"identity":"B1","title":"First","locator":"book://first"},{"identity":"B2","title":"Second","locator":"book://second"}]})
        self.assertEqual(len(self.data("reading","AR-0001")["resources"]),2)
        self.assertEqual(self.data("reading","AR-0001")["note_ids"],["NOTE1"])
        self.assertNotIn("course/C",self.j.read_state()["objects"])
        self.call("reading.transition", {"id":"AR-0001","status":"paused"}, "Pause reading.")
        with self.assertRaises(DomainError): self.call("reading.note.record", {"id":"NOTE2","reading_id":"AR-0001","body":"new","evidence":["ref"]}, "new")

    def test_engagement_lifecycle_keeps_external_governance_and_original_evidence(self):
        self.call("engagement.create", {"id":"EG-0001","intent":"Observe practice.","governance":"external","governance_source":"peer-contract"})
        self.call("engagement.transition", {"id":"EG-0001","status":"paused","reason":"A break."}, "Pause practice.")
        self.call("engagement.transition", {"id":"EG-0001","status":"active","reason":"Resume the same record."}, "Resume practice.")
        self.call("engagement.transition", {"id":"EG-0001","status":"archived","reason":"Finished recording."}, "Archive practice.")
        with self.assertRaises(DomainError): self.call("engagement.transition", {"id":"EG-0001","status":"active","reason":"restart"}, "Resume.")
        self.assertEqual(self.data("engagement","EG-0001")["governance_source"],"peer-contract")
        self.assertEqual(len(self.data("engagement","EG-0001")["lifecycle"]),3)

    def test_pattern_heard_explanation_does_not_create_automatic_method(self):
        self.call("course.create", {"id":"C","title":"Course","course_type":"praxis"}, "Create course.")
        self.call("pattern.record", {"id":"RP1","course_id":"C","body":"A candidate observation.","evidence":["actual-question"],"counterevidence":"A retained counterexample.","testable_prediction":"Try another task."})
        self.call("pattern.method.configure", {"id":"RP1", **{n:"Specific observable text." for n in ("trigger","old_path","stop_signal","replacement_action","causal_explanation","training_plan","next_probe","admission_reason")},"admission_kind":"existing_pattern","source_refs":[{"kind":"pattern","id":"RP1"}]})
        with self.assertRaises(DomainError): self.call("pattern.review", {"id":"RP1","method_status":"automatic","reason":"Student said they understood."})
        self.assertEqual(self.data("pattern","RP1")["method_status"],"candidate")

    def test_keystone_review_checks_every_step_without_claiming_proof(self):
        self.call("course.create", {"id":"C","title":"Course","course_type":"praxis"}, "Create course.")
        self.call("keystone.record", {"id":"K1","course_id":"C","body":"Public logic only.","claim":"Claim.","reasons":["Step one.","Step two."],"dependencies":["later-node"],"review_status":"unreviewed","origin_session_id":"old-session","evidence":["real-student-confirmation"]})
        payload={"id":"K1","session_id":"new-session","reviewed_at":"2026-10-01T12:00:00Z","model_label":"unknown-family","steps":[{"step":1,"result":"no_gap_found","analysis":"Step checked."}],"conclusion":"Not a machine proof."}
        with self.assertRaises(DomainError): self.call("keystone.review",payload)
        payload["steps"].append({"step":2,"result":"gap_found","analysis":"Specific missing premise."})
        self.call("keystone.review",payload)
        self.assertEqual(self.data("keystone","K1")["review_status"],"gap_found")
        self.assertFalse(self.data("keystone","K1")["reviews"][0]["argument_correctness_machine_verified"])

    def test_method_transfer_uses_real_reviews_two_variants_and_interval(self):
        self.call("course.create", {"id":"C","title":"Course","course_type":"mastery","learning_mode":"goal"}, "Create course.")
        self.call("course.activate", {"id":"C"}, "Activate course.")
        self.call("activity.create", {"id":"C/E","course_id":"C","activity_type":"exercise","title":"Practice"})
        self.call("activity.start", {"id":"C/E"}, "Start practice.")
        self.call("exercise.configure", {"activity_id":"C/E"})
        for pid in ("Q1","Q2"):
            self.call("problem.add", {"activity_id":"C/E","problem_id":pid,"text":"A different synthetic problem "+pid,"origin":"teacher_generated"}, "extra practice")
        self.call("criterion.create", {"criterion_id":"CR","target_kind":"exercise","target_id":"C/E","rubric":"Show the required condition.","problem_ids":["Q1","Q2"],"max_scores":{"Q1":1,"Q2":1}})
        for n in (1,2):
            self.call("attempt.submit", {"attempt_id":f"AT{n}","activity_id":"C/E","answers":[{"problem_id":f"Q{n}","text":"Actual synthetic answer."}],"submitted_at":f"2026-09-{n+20}T10:00:00Z"}, "Actual synthetic answer.")
            self.call("review.record", {"review_id":f"RV{n}","attempt_id":f"AT{n}","criterion_id":"CR","ratings":[{"problem_id":f"Q{n}","verdict":"correct","score":1,"rationale":"Condition is actually present."}]})
        self.call("pattern.record", {"id":"RP","course_id":"C","body":"A candidate observation.","evidence":["RV1","RV2"],"counterevidence":"Still watching exceptions.","testable_prediction":"Different tasks show the trigger."})
        self.call("pattern.method.configure", {"id":"RP", **{n:"Specific observable text." for n in ("trigger","old_path","stop_signal","replacement_action","causal_explanation","training_plan","next_probe","admission_reason")},"admission_kind":"repeated_problems","source_refs":[{"kind":"review","id":"RV1"},{"kind":"review","id":"RV2"}]})
        self.call("pattern.observe", {"id":"RP","review_id":"RV1","problem_id":"Q1","observed_at":"2026-09-21T11:00:00Z","variant_signature":"set-membership","trigger_before_prompt":True,"old_path_took_over":False,"observation":"Applied before any prompt."})
        self.call("pattern.review", {"id":"RP","method_status":"reinforced","reason":"One real variant succeeded."})
        with self.assertRaises(DomainError): self.call("pattern.review", {"id":"RP","method_status":"automatic","reason":"Only one observation exists."})
        self.call("pattern.observe", {"id":"RP","review_id":"RV2","problem_id":"Q2","observed_at":"2026-09-22T11:00:00Z","variant_signature":"function-domain","trigger_before_prompt":True,"old_path_took_over":False,"observation":"Applied in a different task without a prompt."})
        self.call("pattern.review", {"id":"RP","method_status":"automatic","reason":"Two actual independent spaced variants."})
        self.assertEqual(self.data("pattern","RP")["method_status"],"automatic")
        self.assertEqual(self.data("pattern","RP")["status"],"hypothesis")
        self.call("reflection.record", {"id":"REF","course_id":"C","body":"Original reflection.","evidence":["RV1"]})
        self.call("reflection.review", {"id":"REF","observation":"Teacher follow-up.","source_refs":[{"kind":"review","id":"RV2"}],"student_statement":{"role":"student","text":"My exact later feeling.","source":"synthetic-message-later"}})
        self.assertEqual(self.data("reflection","REF")["body"],"Original reflection.")
        self.assertEqual(self.data("reflection","REF")["reviews"][0]["student_statement"]["text"],"My exact later feeling.")


if __name__ == "__main__": unittest.main()
