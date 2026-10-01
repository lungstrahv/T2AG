"""Author recovery tests: private-looking records are synthetic, no actual learner decisions."""
from copy import deepcopy
import tempfile
import unittest

from t2ag_next import migration_recovery as recovery, learning, support
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, put, get
from test_learning import Instance


class RecoveryJourneys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.i = Instance(Journal(self.tmp.name))
        self.aid = self.i.exercise()
        self.n = 0

    def tearDown(self): self.tmp.cleanup()

    def inject_legacy_fixture(self, effects):
        self.n += 1
        r = self.i.request("migration.synthetic_fixture", {})
        self.i.journal.apply(r, lambda s, r: effects)
        self.i.state = self.i.journal.read_state()

    def call(self, action, payload, student=None):
        r = self.i.request(action, payload, student)
        module = recovery if action in recovery.ACTIONS else learning if action in learning.ACTIONS else support
        result = self.i.journal.apply(r, module.plan)
        self.i.state = self.i.journal.read_state()
        return result

    def payload(self, kind, identity, fields, **extra):
        d = self.i.data(kind, identity)
        self.n += 1
        return {"id": f"REC-{self.n}", "target_sha256": support.digest(d),
            "evidence_refs": [{"kind":kind, "id":identity, "field":name, "value_sha256":support.digest(d[name])} for name in fields], **extra}

    def exercise_fixture(self, closed=False):
        old_review = self.i.attempt(self.aid, "old-answer", verdict="incorrect")
        d = self.i.data("exercise", self.aid)
        d.pop("criterion_id")
        d.update(legacy={"path":"synthetic/problems.md"}, legacy_fields={"status":"closed" if closed else "ongoing"},
            original_body="Preserved complete original questions and historical context.", migration_requires_reconciliation=True,
            uncertainties=[recovery.EXERCISE_REASON], assistance_status="unmapped_legacy_evidence_not_no_help")
        effects = [put("exercise", self.aid, d)]
        for kind, ident in (("attempt","old-answer"),("review",old_review)):
            old=self.i.data(kind,ident); old.update(history_only=True,migration_requires_reconciliation=True)
            effects.append(put(kind,ident,old))
        if closed:
            a=self.i.data("activity",self.aid); a["status"]="completed"; effects.append(put("activity",self.aid,a))
        self.inject_legacy_fixture(effects)
        return self.payload("exercise", self.aid, ("legacy_fields","original_body","problems"), exercise_id=self.aid)

    def mistake_fixture(self, attempts=1, relative=False):
        rows=[] if not attempts else [{"周期":"1","日期":"2026-01-01","结果":"△","探针/变式":"Preserved condition probe.","提示":"Original attribution kept.","判定依据":"Preserved original judgment."}]
        f={"当前周期":"1","当前周期摘要":f"尝试 {attempts}/6｜独立正确 0/3｜失败 {attempts}｜错后连续正确 0/2",
            "状态":"active","陈年连续正确":"0/2","下次允许复测":"累计 3 个后续学习日后" if relative else "2026-01-04（跨会话，以实际安排为准）","首次日期":"2026-01-01"}
        d={"activity_id":self.aid,"course_id":"C","status":"active","cycle":"1","knowledge_key":"Synthetic defining condition",
            "root_cause":"Preserved misconception.","legacy":{"path":"synthetic/mistakes.md"},"legacy_fields":f,"legacy_retest_rows":rows,
            "original_body":"Complete preserved historical entry.","retests":[],"failed_retests":None,"independent_streak":None,
            "migration_requires_reconciliation":True,"uncertainties":[recovery.MISTAKE_REASON]}
        self.inject_legacy_fixture([put("mistake","M1",d)])
        return self.payload("mistake","M1",("legacy_fields","legacy_retest_rows","original_body"),mistake_id="M1")

    def test_unknown_old_help_remains_unknown_for_new_answer_and_old_grades_unchanged(self):
        p=self.exercise_fixture()
        old={k:deepcopy(self.i.state["objects"][k]) for k in ("attempt/old-answer","review/review-old-answer")}
        self.call("migration.exercise.recover",p)
        self.call("criterion.create", {"criterion_id":"future-rubric","target_kind":"exercise","target_id":self.aid,"rubric":"Future answers must state the condition.","problem_ids":["q1"],"max_scores":{"q1":1}})
        self.call("attempt.submit", {"activity_id":self.aid,"attempt_id":"new-answer","answers":[{"problem_id":"q1","text":"My actual new answer."}]}, "My actual new answer.")
        self.call("review.record", {"review_id":"new-review","attempt_id":"new-answer","criterion_id":"future-rubric","ratings":[{"problem_id":"q1","verdict":"correct","score":1,"rationale":"Condition is present."}]})
        r=self.i.data("review","new-review")["ratings"][0]
        self.assertFalse(r["independent"]); self.assertEqual(r["evidence_class"],"legacy_uncertain")
        help_=self.i.data("attempt","new-answer")["assistance"]["q1"]
        self.assertTrue(help_["history_unknown"]); self.assertFalse(help_["polluted"])
        for k,v in old.items(): self.assertEqual(self.i.state["objects"][k],v)
        with self.assertRaises(DomainError):
            self.call("review.record", {"review_id":"regrade-old","attempt_id":"old-answer","criterion_id":"future-rubric","ratings":[]})

    def test_new_question_does_not_inherit_another_questions_unknown_help(self):
        self.call("migration.exercise.recover",self.exercise_fixture())
        self.call("problem.add", {"activity_id":self.aid,"problem_id":"new-question","origin":"teacher_generated","text":"An actual different question."}, "extra practice")
        self.call("criterion.create", {"criterion_id":"new-only-rubric","target_kind":"exercise","target_id":self.aid,"rubric":"State a condition.","problem_ids":["new-question"],"max_scores":{"new-question":1}})
        self.call("attempt.submit", {"activity_id":self.aid,"attempt_id":"fresh","answers":[{"problem_id":"new-question","text":"Actual new answer."}]}, "Actual new answer.")
        self.call("review.record", {"review_id":"fresh-review","attempt_id":"fresh","criterion_id":"new-only-rubric","ratings":[{"problem_id":"new-question","verdict":"correct","score":1,"rationale":"The required condition is present."}]})
        self.assertTrue(self.i.data("review","fresh-review")["ratings"][0]["independent"])

    def test_unknown_help_does_not_become_known_unpolluted_mistake_evidence(self):
        self.call("migration.exercise.recover",self.exercise_fixture())
        self.call("criterion.create", {"criterion_id":"future-rubric","target_kind":"exercise","target_id":self.aid,"rubric":"State a condition.","problem_ids":["q1"],"max_scores":{"q1":1}})
        self.call("attempt.submit", {"activity_id":self.aid,"attempt_id":"uncertain-context-answer","answers":[{"problem_id":"q1","text":"New actual incorrect answer."}]}, "New actual incorrect answer.")
        self.call("review.record", {"review_id":"uncertain-context-review","attempt_id":"uncertain-context-answer","criterion_id":"future-rubric","ratings":[{"problem_id":"q1","verdict":"incorrect","score":0,"rationale":"Missing the defining condition."}]})
        with self.assertRaises(DomainError):
            self.call("mistake.record", {"mistake_id":"M-new","review_id":"uncertain-context-review","problem_id":"q1","knowledge_key":"K","root_cause":"Do not infer a clean diagnostic setting from unknown help."})

    def test_closed_exercise_does_not_resume_on_recovery(self):
        self.call("migration.exercise.recover",self.exercise_fixture(closed=True))
        self.assertEqual(self.i.data("activity",self.aid)["status"],"completed")
        with self.assertRaises(DomainError) as caught:
            self.call("attempt.submit", {"activity_id":self.aid,"attempt_id":"forbidden","answers":[{"problem_id":"q1","text":"New."}]}, "New.")
        self.assertEqual(caught.exception.code,"ACTIVITY_NOT_ONGOING")

    def test_changed_snapshot_or_wrong_field_hash_leaves_no_partial_recovery(self):
        p=self.exercise_fixture(); before=self.i.journal.read_state()
        for bad in ({**p,"target_sha256":"0"*64}, {**p,"evidence_refs":[{**x,"value_sha256":"0"*64} for x in p["evidence_refs"]]}):
            with self.assertRaises(DomainError): self.call("migration.exercise.recover",bad)
            self.assertEqual(before,self.i.journal.read_state())

    def test_same_committed_request_is_idempotent_and_new_recovery_cannot_reset(self):
        p=self.exercise_fixture(); request=self.i.request("migration.exercise.recover",p)
        self.i.journal.apply(request,recovery.plan)
        before=self.i.journal.read_state()
        self.i.journal.apply(request,recovery.plan)
        self.assertEqual(before,self.i.journal.read_state())
        self.i.state=before
        with self.assertRaises(DomainError): self.call("migration.exercise.recover",p)

    def test_unavailable_cycle_consumer_does_not_clear_mistake_gate(self):
        from unittest.mock import patch
        p=self.mistake_fixture(); before=self.i.journal.read_state()
        with patch.object(learning,"LEGACY_CYCLE_BASELINE_VERSION",None,create=True):
            with self.assertRaises(DomainError) as caught: self.call("migration.mistake.recover",p)
        self.assertEqual(caught.exception.code,"RECOVERY_CONSUMER_PENDING")
        self.assertEqual(before,self.i.journal.read_state())

    def test_preserved_cycle_counters_are_consumed_by_new_real_retests(self):
        p=self.mistake_fixture()
        original=deepcopy(self.i.data("mistake","M1"))
        self.call("migration.mistake.recover",p)
        self.i.retest(self.aid)
        d=self.i.data("mistake","M1")
        self.assertEqual((d["cycle_attempts"],d["cycle_successes"],d["failed_retests"]),(2,1,1))
        self.assertEqual(d["status"],"active")
        self.i.retest(self.aid); self.i.retest(self.aid)
        d=self.i.data("mistake","M1")
        self.assertEqual((d["cycle_attempts"],d["cycle_successes"],d["failed_retests"]),(4,3,1))
        self.assertEqual(d["status"],"maintenance")
        self.assertEqual(d["legacy_retest_rows"],original["legacy_retest_rows"])
        self.assertEqual(d["original_body"],original["original_body"])
        self.assertEqual(len(d["retests"]),3,"Old summary rows are not fabricated new-system review events.")
        baseline=deepcopy(d["legacy_cycle_baseline"])
        self.call("criterion.create", {"criterion_id":"recurrence-rubric","target_kind":"exercise","target_id":self.aid,"rubric":"State a condition.","problem_ids":["q1"],"max_scores":{"q1":1}})
        self.call("attempt.submit", {"activity_id":self.aid,"attempt_id":"new-recurrence","answers":[{"problem_id":"q1","text":"Actual new incorrect answer."}]}, "Actual new incorrect answer.")
        self.call("review.record", {"review_id":"new-recurrence-review","attempt_id":"new-recurrence","criterion_id":"recurrence-rubric","ratings":[{"problem_id":"q1","verdict":"incorrect","score":0,"rationale":"Actual defining condition omitted."}]})
        self.call("mistake.recur", {"mistake_id":"M1","review_id":"new-recurrence-review","problem_id":"q1","knowledge_key":d["knowledge_key"],"root_cause":"Same observed misconception recurred."})
        self.assertEqual(self.i.data("mistake","M1")["cycle"],2)
        self.i.retest(self.aid)
        d=self.i.data("mistake","M1")
        self.assertEqual((d["cycle_attempts"],d["cycle_successes"],d["failed_retests"]),(1,1,0))
        self.assertEqual(d["status"],"active")
        self.assertEqual(d["legacy_cycle_baseline"],baseline)

    def test_legacy_relative_gate_uses_three_actual_learning_dates(self):
        self.call("migration.mistake.recover",self.mistake_fixture(relative=True))
        before=deepcopy(self.i.data("mistake","M1"))
        with self.assertRaises(DomainError): self.i.retest(self.aid,settle=False)
        self.assertEqual(self.i.data("mistake","M1"),before)
        for n in (1,2,3):
            self.call("time.record", {"id":f"same-date-{n}","activity_id":self.aid,"quality":"exact","seconds":30,"started_at":"2026-01-02T12:00:00Z"})
        with self.assertRaises(DomainError): self.call("mistake.retest",self.i.last_retest)
        for n in (3,4):
            self.call("time.record", {"id":f"different-date-{n}","activity_id":self.aid,"quality":"exact","seconds":30,"started_at":f"2026-01-0{n}T12:00:00Z"})
        self.call("mistake.retest",self.i.last_retest)
        self.call("session.close",{"session_id":self.i.last_retest["session_id"]})
        self.assertEqual(self.i.data("mistake","M1")["cycle_successes"],1)

    def test_legacy_absolute_date_rejects_a_premature_formal_result(self):
        self.mistake_fixture(attempts=0)
        d=self.i.data("mistake","M1");d["legacy_fields"]["下次允许复测"]="2026-01-20"
        self.inject_legacy_fixture([put("mistake","M1",d)])
        p=self.payload("mistake","M1",("legacy_fields","legacy_retest_rows","original_body"),mistake_id="M1")
        self.call("migration.mistake.recover",p)
        with self.assertRaises(DomainError):self.i.retest(self.aid)
        self.assertEqual(self.i.data("mistake","M1")["retests"],[])

    def test_cycle_conflict_or_unrecognized_date_stays_unresolved(self):
        self.mistake_fixture()
        for name,value in (("当前周期摘要","尝试 2/6｜独立正确 0/3｜失败 1｜错后连续正确 0/2"),("下次允许复测","When convenient")):
            d=self.i.data("mistake","M1");original=deepcopy(d);d["legacy_fields"][name]=value
            self.inject_legacy_fixture([put("mistake","M1",d)])
            p=self.payload("mistake","M1",("legacy_fields","legacy_retest_rows","original_body"),mistake_id="M1")
            with self.assertRaises(DomainError) as caught:self.call("migration.mistake.recover",p)
            self.assertIn(caught.exception.code,{"RECOVERY_CYCLE_CONFLICT","RECOVERY_DUE_UNKNOWN"})
            self.assertTrue(self.i.data("mistake","M1")["migration_requires_reconciliation"])
            self.inject_legacy_fixture([put("mistake","M1",original)])

    def test_missing_origin_binds_unique_exact_historical_attempt_without_regrading(self):
        self.mistake_fixture()
        d=self.i.data("mistake","M1");d["activity_id"]=None;d["legacy_fields"]["来源"]="Exercise UNIT1 / Q002(1)"
        old={"activity_id":self.aid,"history_only":True,"original_body":"Original UNIT1-Q002(1) answer, unchanged."}
        self.inject_legacy_fixture([put("mistake","M1",d),put("attempt","legacy-origin",old)])
        p=self.payload("mistake","M1",("legacy_fields","legacy_retest_rows","original_body"),mistake_id="M1")
        with self.assertRaises(DomainError):self.call("migration.mistake.recover",p)
        p["origin_evidence"]={"kind":"attempt","id":"legacy-origin","field":"original_body","value_sha256":support.digest(old["original_body"]),"locator":"UNIT1-Q002(1)"}
        before=deepcopy(self.i.state["objects"]["attempt/legacy-origin"])
        self.call("migration.mistake.recover",p)
        self.assertEqual(self.i.data("mistake","M1")["activity_id"],self.aid)
        self.assertEqual(self.i.state["objects"]["attempt/legacy-origin"],before)

    def test_multiple_historical_origin_matches_are_not_chosen_by_recency(self):
        self.mistake_fixture()
        d=self.i.data("mistake","M1");d["activity_id"]=None;d["legacy_fields"]["来源"]="Exercise UNIT1 / Q002(1)"
        old={"activity_id":self.aid,"history_only":True,"original_body":"Original UNIT1-Q002(1) answer."}
        self.inject_legacy_fixture([put("mistake","M1",d),put("attempt","origin-1",old),put("attempt","origin-2",old)])
        p=self.payload("mistake","M1",("legacy_fields","legacy_retest_rows","original_body"),mistake_id="M1")
        with self.assertRaises(DomainError) as caught:self.call("migration.mistake.recover",p)
        self.assertEqual(caught.exception.code,"RECOVERY_ORIGIN_AMBIGUOUS")

    def test_origin_locator_has_complete_problem_and_subproblem_boundaries(self):
        self.mistake_fixture()
        d=self.i.data("mistake","M1");d["activity_id"]=None;d["legacy_fields"]["来源"]="Exercise UNIT1 / Q002"
        self.inject_legacy_fixture([put("mistake","M1",d)])
        for locator in ("UNIT1-Q0020","UNIT1-Q0021","UNIT1-Q002(1)","OTHERUNIT1-Q002","UNIT1-Q002.1","UNIT1-Q002（1）"):
            old={"activity_id":self.aid,"history_only":True,"original_body":f"Original {locator} answer."}
            self.inject_legacy_fixture([put("attempt","wrong-origin",old)])
            p=self.payload("mistake","M1",("legacy_fields","legacy_retest_rows","original_body"),mistake_id="M1")
            with self.subTest(locator=locator),self.assertRaises(DomainError) as caught:self.call("migration.mistake.recover",p)
            self.assertEqual(caught.exception.code,"RECOVERY_ORIGIN_AMBIGUOUS")

    def test_cursor_recovery_issues_one_new_body_ticket_from_one_current_decision(self):
        a=self.i.data("activity",self.aid); a.update(original_body="Earlier context.\nThe full saved explanation.\nLater context.")
        c={"activity_id":self.aid,"course_id":"C","block_id":None,"position":"Preserved unresolved stop",
            "waiting_for":"resolve_legacy_conflict","legacy":{"path":"synthetic/progress.md"},"legacy_activity_position":"Preserved unresolved stop",
            "legacy_current_section":"The saved explanation was pending.","legacy_body_next_action":"An older next step conflicts.",
            "uncertainties":[recovery.CURSOR_REASON],"migration_requires_reconciliation":True}
        self.inject_legacy_fixture([put("activity",self.aid,a),put("cursor",self.aid,c)])
        self.call("block.create", {"activity_id":self.aid,"block_id":"saved-block","teacher_title":"Saved explanation","source_role":"explanation","body":"The full saved explanation."})
        p=self.payload("cursor",self.aid,("legacy_activity_position","legacy_current_section","legacy_body_next_action"),activity_id=self.aid,
            block_id="saved-block",body_sha256=learning.digest("The full saved explanation."),session_id="s1",ticket_id="new-recovery-ticket",
            body_evidence={"kind":"activity","id":self.aid,"field":"original_body","value_sha256":support.digest(a["original_body"]),"excerpt":"The full saved explanation."})
        with self.assertRaises(DomainError): self.call("migration.cursor.recover",p,"不要重新呈现保存的正文。")
        before=self.i.journal.read_state()
        with self.assertRaises(DomainError) as caught:self.call("migration.cursor.recover",p,"确认重新呈现保存的正文：saved-block")
        self.assertEqual(caught.exception.code,"OPENING_REQUIRED")
        self.assertEqual(before,self.i.journal.read_state())
        self.call("session.opening", {"session_id":"s1","overview":"The preserved pending explanation.","knowledge_tree":"This saved explanation only."})
        # Only the session changed; the exact cursor/body evidence remains bound.
        self.call("migration.cursor.recover",p,"把保存的这一段重讲一下。")
        cursor=self.i.data("cursor",self.aid)
        self.assertEqual(cursor["position"],"Preserved unresolved stop")
        self.assertFalse(cursor["historical_permissions_active"])
        self.assertIsNone(cursor["current_session_scan"])
        with self.assertRaises(DomainError): self.call("block.present", {"session_id":"s1","block_id":"saved-block","ticket_id":"old-ticket","body_sha256":p["body_sha256"]})
        ticket=self.i.data("ticket","new-recovery-ticket")
        self.assertEqual(ticket["status"],"issued")
        self.call("block.present", {"session_id":"s1","block_id":"saved-block","ticket_id":"new-recovery-ticket","body_sha256":p["body_sha256"]})
        self.assertEqual(self.i.data("ticket","new-recovery-ticket")["status"],"consumed")

    def test_same_recovery_decision_cannot_bypass_current_textbook_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            self.i=Instance(Journal(folder)); aid,bids=self.i.lesson()
            body=self.i.data("block",bids[0])["body"]
            a=self.i.data("activity",aid);a["original_body"]="Saved actual body:\n"+body
            c={"activity_id":aid,"course_id":"C","position":"Same saved stop","legacy":{"path":"synthetic/progress.md"},
                "legacy_activity_position":"Same saved stop","legacy_current_section":"Pending saved explanation","legacy_body_next_action":"An old ambiguous direction",
                "waiting_for":"resolve_legacy_conflict","uncertainties":[recovery.CURSOR_REASON],"migration_requires_reconciliation":True}
            self.inject_legacy_fixture([put("activity",aid,a),put("cursor",aid,c)])
            p=self.payload("cursor",aid,("legacy_activity_position","legacy_current_section","legacy_body_next_action"),activity_id=aid,
                block_id=bids[0],body_sha256=learning.digest(body),session_id="s1",ticket_id="recovery-ticket",
                body_evidence={"kind":"activity","id":aid,"field":"original_body","value_sha256":support.digest(a["original_body"]),"excerpt":body})
            text="确认重新呈现保存的正文："+bids[0]
            before=self.i.journal.read_state()
            with self.assertRaises(DomainError) as caught:self.call("migration.cursor.recover",p,text)
            self.assertEqual(caught.exception.code,"SOURCE_SCAN_REQUIRED")
            self.assertEqual(before,self.i.journal.read_state())
            self.i.ready()
            self.call("migration.cursor.recover",p,text)
            self.call("block.present",{"session_id":"s1","block_id":bids[0],"ticket_id":"recovery-ticket","body_sha256":p["body_sha256"]})
            self.assertEqual(self.i.data("block",bids[0])["status"],"presented")


class LiteralMappingJourneys(unittest.TestCase):
    """Known migration shapes, through a real Journal and public dispatch."""
    def setUp(self):
        from t2ag_next import service
        self.service = service
        self.tmp = tempfile.TemporaryDirectory()
        self.i = Instance(Journal(self.tmp.name))

    def tearDown(self): self.tmp.cleanup()

    def seed(self, effects):
        self.i.journal.apply(self.i.request("migration.synthetic_fixture", {}), lambda s, r: effects)
        self.i.state = self.i.journal.read_state()

    def payload(self, kind, ident, names, **extra):
        d = self.i.data(kind, ident)
        return {"id": "recover-" + ident, "target_sha256": support.digest(d),
                "evidence_refs": [{"kind": kind, "id": ident, "field": n, "value_sha256": support.digest(d[n])} for n in names], **extra}

    def call(self, action, p):
        result = self.service.execute(self.tmp.name, self.i.request(action, p))
        self.i.state = self.i.journal.read_state()
        return result

    def cursor(self, cid, position, section, status="ongoing", route=None):
        aid = cid + "/lesson01"
        self.seed([put("course", cid, {"status": status, "current_activity_id": aid}),
                   put("activity", aid, {"course_id": cid, "activity_type": "lesson", "status": "ongoing"}),
                   put("cursor", aid, {"legacy": {"snapshot_id": "synthetic"}, "position": position,
                        "legacy_activity_position": position, "legacy_current_section": section,
                        "legacy_body_next_action": route or "resume lesson:lesson01",
                        "next_action": {"kind": "resume", "activity_type": "lesson", "activity_id": "lesson01"},
                        "block_id": cid + "-historical-checkpoint", "waiting_for": "resolve_legacy_conflict", "uncertainties": [recovery.CURSOR_REASON]})])
        return aid, self.payload("cursor", aid, ("legacy_activity_position", "legacy_current_section", "legacy_body_next_action"), activity_id=aid)

    def test_literal_three_stops_keep_paused_and_do_not_grant_permission(self):
        cases = [("setup", "尚未开讲；第一动作＝宿主机核验 dotnet --version", "- **下一步计划**：resume lesson:lesson01", "ongoing"),
                 ("paused", "编译已完成；练习待检查。", "- **精确停顿点**：sum.cpp 练习待完成或待检查。", "paused"),
                 ("project", "环境已确认；下一步核对已有仓。", "- **精确停顿点**：核对已有仓并补 .gitignore，禁止再次 git init。", "ongoing")]
        for cid, position, section, status in cases:
            with self.subTest(cid=cid):
                aid, p = self.cursor(cid, position, section, status)
                old_course = deepcopy(self.i.data("course", cid))
                old_activity = deepcopy(self.i.data("activity", aid))
                self.call("migration.cursor.map", p)
                cur = self.i.data("cursor", aid)
                self.assertEqual(cur["waiting_for"], "resume")
                self.assertEqual(cur["uncertainties"], [])
                self.assertEqual(cur["legacy_activity_position"], position)
                self.assertEqual(cur["block_id"], cid + "-historical-checkpoint")
                self.assertFalse(cur["historical_permissions_active"])
                self.assertIsNone(cur["current_session_scan"])
                self.assertEqual(self.i.data("course", cid), old_course)
                self.assertEqual(self.i.data("activity", aid), old_activity)
                self.assertFalse(any(e["kind"] in {"ticket", "session", "scan"} for e in self.i.state["objects"].values()))

    def test_elaborated_conflicting_next_step_is_not_plain_resume(self):
        aid, p = self.cursor("conflict", "S03 已完成；当前 scaling 理解确认。", "- **下一步计划**：S03 开讲。",
                             route="resume lesson:lesson01 — S03 开讲，从核标题起")
        before = self.i.journal.read_state()
        with self.assertRaises(DomainError) as caught: self.call("migration.cursor.map", p)
        self.assertEqual(caught.exception.code, "RECOVERY_ROUTE_CONFLICT")
        self.assertEqual(before, self.i.journal.read_state())

    def question(self, ident, fields, status="answered"):
        body = "Complete preserved question and original answer; course-level discussion remains a question."
        self.seed([put("question", ident, {"course_id": "C", "activity_id": None, "status": status,
                    "text": body, "original_body": body, "legacy_fields": fields, "legacy": {"snapshot_id": "synthetic"},
                    "uncertainties": [recovery.QUESTION_REASON]})])
        return self.payload("question", ident, ("legacy_fields", "original_body"), question_id=ident)

    def test_question_paths_and_exact_locator_preserve_answers_and_status(self):
        self.seed([put("activity", "C/lesson01", {"course_id": "C", "status": "completed", "original_body": "Full lesson history"}),
                   put("activity", "C/exercise01", {"course_id": "C", "status": "completed", "original_body": "Full exercise history"}),
                   put("attempt", "C/exercise01/AT0003", {"activity_id": "C/exercise01", "history_only": True, "original_body": "Full UNIT1-Q006(1) historical answer"})])
        cases = [("Q1", {"完整记录": "`lesson01/lesson01.md`"}, "activity", "C/lesson01", "lesson01/lesson01.md", "answered"),
                 ("Q2", {"完整记录": "`exercises/exercise01/attempts/AT0003/attempt.md` 与原Review"}, "attempt", "C/exercise01/AT0003", "exercises/exercise01/attempts/AT0003/attempt.md", "closed"),
                 ("Q3", {"来源": "Exercise UNIT1 / Q006(1)"}, "attempt", "C/exercise01/AT0003", "UNIT1-Q006(1)", "closed")]
        for qid, f, kind, origin_id, locator, status in cases:
            with self.subTest(qid=qid):
                p = self.question("C/" + qid, f, status)
                before = self.i.data("question", "C/" + qid)
                p["origin_evidence"] = {"kind": kind, "id": origin_id, "field": "original_body", "value_sha256": support.digest(self.i.data(kind, origin_id)["original_body"]), "locator": locator}
                self.call("migration.question.recover", p)
                after = self.i.data("question", "C/" + qid)
                self.assertEqual(after["activity_id"], "C/lesson01" if kind == "activity" else "C/exercise01")
                for field in ("status", "text", "original_body", "legacy_fields"):
                    self.assertEqual(after[field], before[field])
                self.assertEqual(after["uncertainties"], [])

    def test_question_origin_binding_rejects_a_substituted_record(self):
        self.seed([put("activity", "C/lesson01", {"course_id": "C", "status": "completed", "original_body": "Full lesson history"})])
        p = self.question("C/Q1", {"完整记录": "`lesson01/lesson01.md`"})
        p["origin_evidence"] = {"kind": "activity", "id": "C/lesson02", "field": "original_body", "value_sha256": support.digest("Full lesson history"), "locator": "lesson01/lesson01.md"}
        before = self.i.journal.read_state()
        with self.assertRaises(DomainError) as caught: self.call("migration.question.recover", p)
        self.assertEqual(caught.exception.code, "RECOVERY_ORIGIN_EVIDENCE")
        self.assertEqual(before, self.i.journal.read_state())


if __name__ == "__main__": unittest.main()
