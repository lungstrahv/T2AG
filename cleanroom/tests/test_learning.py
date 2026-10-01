"""Behavioral learning journeys through the public request/state contract."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import tempfile
import unittest

from t2ag_next import learning, support
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, get, key


class Instance:
    def __init__(self, journal=None):
        self.journal = journal
        self.sequence = 0
        self.state = {"revision": 1, "objects": {"student/current": {"kind": "student", "id": "current", "version": 1, "data": {"exercise_hint_gate": "enabled"}}}}
        if journal:
            journal.initialize({"exercise_hint_gate": "enabled"})
            self.state = journal.read_state()

    def request(self, action, payload, student=None):
        self.sequence += 1
        return {"request_id": f"request-{self.sequence}", "action": action, "payload": payload,
                "actor": {"role": "student" if student is not None else "teacher", "source": f"synthetic-turn-{self.sequence}", "text": student if student is not None else "Record observed evidence."},
                "expected": {k: v["version"] for k, v in self.state["objects"].items()}}

    def call(self, action, payload, student=None):
        request = self.request(action, payload, student)
        planner = learning.plan if action in learning.ACTIONS else support.plan
        if self.journal:
            result = self.journal.apply(request, planner)
            self.state = self.journal.read_state()
            return result["effects"]
        effects = planner(self.state, request)
        self.state["revision"] += 1
        for effect in effects:
            self.state["objects"][key(effect["kind"], effect["id"])] = {"kind": effect["kind"], "id": effect["id"], "version": self.state["revision"], "data": deepcopy(effect["data"])}
        return effects

    def data(self, kind, ident):
        return get(self.state, kind, ident)

    def course(self, mode="textbook"):
        self.call("course.create", {"id": "C", "title": "Synthetic course", "course_type": "mastery", "learning_mode": mode}, "Create this course.")

    def sources(self, page_count=2):
        raw = "Synthetic page fixture; no student or copyrighted material."
        self.call("source.register", {"source_id": "book-v1", "course_id": "C", "title": "Fixture", "format": "pdf", "source_version": "1", "content": raw, "content_sha256": learning.digest(raw), "page_count": page_count})
        for n in range(1, page_count+1):
            self.call("page.register", {"page_id": f"page-{n}", "source_id": "book-v1", "pdf_page_index": n, "printed_page_label": str(n+10), "verified_text": f"Definition {n}. Problem {n}: explain.", "layout_critical": False,
                       "verification": {"status": "verified", "reference": f"synthetic-verification-{n}", "source_document_sha256": learning.digest(raw)}})

    def activity(self, kind="lesson"):
        aid = "C/"+kind
        self.call("course.activate", {"id": "C"}, "Activate course.")
        self.call("activity.create", {"id": aid, "course_id": "C", "activity_type": kind, "title": "Fixture activity"})
        return aid

    def block(self, aid, n):
        bid = f"{aid}/b{n}"
        self.call("block.create", {"block_id": bid, "activity_id": aid, "teacher_title": f"Teacher arrangement {n}", "source_role": "definition", "body": f"Explain definition {n}.",
                   "source_refs": [{"page_id": f"page-{n}", "source_excerpt": f"Definition {n}.", "locator": f"page {n}, first definition"}]})
        self.call("criterion.create", {"criterion_id": f"criterion-{n}", "target_kind": "block", "target_id": bid, "rubric": "The answer must describe the defining condition."})
        return bid

    def lesson(self, page_count=2):
        self.course(); self.sources(page_count); aid = self.activity()
        bids = [self.block(aid, n) for n in range(1, page_count+1)]
        page_ids = [f"page-{n}" for n in range(1, page_count+1)]
        self.call("scope.create", {"scope_id": "scope-v1", "activity_id": aid, "source_id": "book-v1", "page_ids": page_ids, "current_page_id": "page-1"})
        self.call("lessonmap.create", {"lessonmap_id": "map-v1", "activity_id": aid, "scope_id": "scope-v1", "block_ids": bids})
        receipts = [{"page_id": pid, "reference": "prepared-fixture", "verified_text_sha256": self.data("page", pid)["verified_text_sha256"], "source_document_sha256": self.data("source", "book-v1")["content_sha256"]} for pid in page_ids]
        self.call("preparation.create", {"preparation_id": "prep-v1", "activity_id": aid, "scope_id": "scope-v1", "lessonmap_id": "map-v1", "receipts": receipts})
        self.call("activity.start", {"id": aid}, "Start activity.")
        self.call("session.start", {"session_id": "s1", "activity_id": aid})
        return aid, bids

    def deliveries(self, sid="s1"):
        return [{"page_id": pid, "form": "verified_text", "host_reference": f"synthetic-host-delivery-{sid}-{pid}", "session_id": sid,
                 "source_document_sha256": self.data("source", "book-v1")["content_sha256"], "printed_page_label": self.data("page", pid)["printed_page_label"], "content": self.data("page", pid)["verified_text"]}
                for pid in self.data("scope", "scope-v1")["page_ids"]]

    def ready(self, sid="s1"):
        self.call("scan.record", {"scan_id": f"scan-{sid}", "session_id": sid, "scope_id": "scope-v1", "deliveries": self.deliveries(sid)})
        self.call("session.opening", {"session_id": sid, "overview": "Two definitions, then practice.", "knowledge_tree": "Definition 1 -> Definition 2"})

    def ticket(self, bid, tid="t1", sid="s1"):
        self.call("ticket.issue", {"ticket_id": tid, "session_id": sid, "block_id": bid, "body_sha256": self.data("block", bid)["body_sha256"]}, "继续")

    def present(self, bid, tid="t1", **extra):
        return self.call("block.present", {"session_id": "s1", "block_id": bid, "ticket_id": tid, "body_sha256": self.data("block", bid)["body_sha256"], **extra})

    def answer(self, bid, response="answer-1", verdict="correct"):
        self.call("comprehension.submit", {"session_id": "s1", "block_id": bid, "response_id": response, "answer": "My own defining condition."}, "My own defining condition.")
        return self.call("comprehension.record", {"session_id": "s1", "block_id": bid, "response_id": response, "criterion_id": self.data("block", bid)["criterion_id"], "verdict": verdict, "rationale": "Compared the actual stated condition with the frozen rubric."})

    def exercise(self):
        self.course("goal"); self.sources(); aid = self.activity("exercise")
        self.call("exercise.configure", {"activity_id": aid})
        self.call("problem.add", {"activity_id": aid, "problem_id": "q1", "text": "Problem 1: explain.", "origin": "source", "page_id": "page-1", "source_excerpt": "Problem 1: explain.", "locator": "problem 1"})
        self.call("criterion.create", {"criterion_id": "rubric-v1", "target_kind": "exercise", "target_id": aid, "rubric": "Explanation states the condition.", "problem_ids": ["q1"], "max_scores": {"q1": 10}, "pass_score": 6})
        self.call("activity.start", {"id": aid}, "Start exercise.")
        self.call("session.start", {"session_id": "s1", "activity_id": aid})
        return aid

    def attempt(self, aid, name, verdict="correct", independent=None):
        self.call("attempt.submit", {"activity_id": aid, "attempt_id": name, "answers": [{"problem_id": "q1", "text": "My submitted answer."}]}, "Here is my answer.")
        rating = {"problem_id": "q1", "verdict": verdict, "rationale": "Observed this answer under the frozen rubric.", "score": 10 if verdict == "correct" else 0}
        if independent is not None: rating["independent"] = independent
        self.call("review.record", {"review_id": "review-"+name, "attempt_id": name, "criterion_id": "rubric-v1", "ratings": [rating]})
        return "review-"+name

    def exam_bank(self, mode="schedule", paper_count=10):
        aid = self.exercise()
        self.call("group.propose", {"id": "G", "members": ["C"], "capacity": 1, "container_mode": mode, "calendar": {"frequency": "daily", "stagnation_days": 7, "cycle_anchor_learning_day": "2026-01-01", "cycle_length_learning_days": 6, "cycle_count": 14, "exam_final_cycle": 14, "exam_bank_build_cycles": [2, 5, 8, 11], "exam_quiz_cycles": [3, 6, 9, 12], "exam_keystones_per_bank_build": 1, "exam_keystones_per_quiz": 1}, "thresholds": {"close_condition": "verified"}, "goal": "Synthetic examinations"})
        self.call("group.activate", {"id": "G", "proposal_sha256": self.data("group", "G")["proposal_sha256"]}, "Activate this group.")
        if mode == "progress":
            self.call("group.keystones.configure", {"id": "G", "container_mode": mode, "keystone_ids": ["N1"], "reason": "Agreed examination scope."}, "Use this scope.")
        for status in ("queued", "arrived", "pending", "confirmed"):
            self.call("checkpoint.record", {"id": "CP1", "activity_id": aid, "status": status, "position": "N1", "evidence": ["Synthetic checkpoint evidence"]}, "I understand N1." if status == "confirmed" else None)
        self.call("completion.record", {"id": "COMP1", "course_id": "C", "judgment_kind": "comprehension", "evidence_ids": ["CP1"]}, "Confirm this learning result.")
        if mode == "progress":
            self.call("group.keystone.complete", {"id": "G", "keystone_id": "N1", "completion_id": "COMP1"})
        papers = []; points = []; maxima = {}
        for n in range(paper_count):
            for purpose, prefix in (("exam_paper", "paper"), ("exam_solution", "solution")):
                raw = f"Synthetic {prefix} {n}; Q1. Q2. Q3. Official step."
                sid = f"{prefix}-{n}"; page = sid+"-p1"
                self.call("source.register", {"source_id": sid, "course_id": "C", "title": f"Fixture {sid}", "format": "pdf", "source_version": "1", "content": raw, "content_sha256": learning.digest(raw), "page_count": 1, "purpose": purpose, "official": True})
                self.call("page.register", {"page_id": page, "source_id": sid, "pdf_page_index": 1, "printed_page_label": "1", "verified_text": raw, "layout_critical": False, "verification": {"status": "verified", "reference": "synthetic fixture", "source_document_sha256": learning.digest(raw)}})
            qs = []
            for q in range(1, 4):
                pid = f"paper-{n}/Q{q}"
                qs.append({"problem_id": pid, "page_id": f"paper-{n}-p1", "source_excerpt": f"Q{q}.", "locator": f"Q{q}", "kind": "proof", "nodes": ["N1" if mode == "progress" else "CP1"], "dependencies": [], "difficulty_signals": [2, 2, 2], "solution_page_id": f"solution-{n}-p1", "solution_locator": f"Q{q}"})
                points.append({"point_id": pid+"/step", "problem_id": pid, "max_score": 10, "page_id": f"solution-{n}-p1", "source_excerpt": "Official step.", "locator": f"Q{q} step"}); maxima[pid] = 10
            papers.append({"paper_id": f"P{n}", "source_id": f"paper-{n}", "solution_source_id": f"solution-{n}", "school": f"Synthetic school {n}", "country": ["CN", "JP", "SG", "GB", "FR", "CH", "US"][n%7], "year": 2025, "language": "en", "ranking_reference": "Synthetic test attribution; not an actual ranking", "subject_rank": n%30+1, "level": "honors", "total_minutes": 30, "original_question_count": 3, "problems": qs})
        self.exam_days(aid, 12)
        self.call("exam_bank.register", {"bank_id": "BANK", "course_id": "C", "group_id": "G", "cycle": 2 if mode == "schedule" else 1, "seed": "public-fixture", "imported_at": "2026-01-12T18:00:00Z", "papers": papers})
        self.call("criterion.create", {"criterion_id": "exam-rubric", "target_kind": "exam_bank", "target_id": "BANK", "rubric": "Original solution steps.", "problem_ids": list(maxima), "max_scores": maxima, "scoring_points": points})
        self.call("criterion.create", {"criterion_id": "process-rubric", "target_kind": "course", "target_id": "C", "purpose": "exam_process", "rubric": "The recorded retrieval evidence supports this process rating.", "metric_ids": ["retrieval"], "max_scores": {"retrieval": 100}})
        return aid

    def exam_days(self, aid, total):
        for number in range(getattr(self, "exam_day_count", 0)+1, total+1):
            when = (datetime(2026, 1, 1, 12, tzinfo=timezone.utc)+timedelta(days=number-1)).isoformat()
            self.call("time.record", {"id": f"exam-day-{number}", "activity_id": aid, "quality": "exact", "seconds": 60, "started_at": when})
        self.exam_day_count = total

    def retest(self, aid, verdict="correct", settle=True):
        self.retest_sequence = getattr(self, "retest_sequence", 0)+1; n = self.retest_sequence
        for item in list(self.state["objects"].values()):
            if item["kind"] == "session" and item["data"]["status"] == "active": self.call("session.close", {"session_id": item["id"]})
        sid = f"retest-session-{n}"; vid = f"variant-{n}"; pid = f"probe-{n}"; rid = f"retest-rubric-{n}"
        self.call("session.start", {"session_id": sid, "activity_id": aid})
        self.call("variant.create", {"variant_id": vid, "mistake_id": "M1", "activity_id": aid, "problem_id": pid, "probe": "P1" if n%2 else "P2", "body": f"Distinct synthetic surface question {n}.", "self_solution": "Complete synthetic solution with explicit conditions.", "judgment_basis": "States all required conditions.", "transformation": "rephrase", "safety": {"self_solved": True, "solvable": True, "judgment_clear": True, "reference": "synthetic full self-check"}})
        when = (datetime(2026, 1, 1, tzinfo=timezone.utc)+timedelta(days=4*n)).isoformat()
        sheet = None
        if self.data("mistake", "M1")["status"] == "aged":
            sheet = f"sheet-{n}"
            self.call("aged_review.create", {"sheet_id": sheet, "activity_id": aid, "variant_ids": [vid], "context_closure": "Related definitions just reviewed.", "as_of": when}, "generate review")
        self.call("criterion.create", {"criterion_id": rid, "target_kind": "exercise", "target_id": aid, "rubric": "The frozen probe condition.", "problem_ids": [pid], "max_scores": {pid: 10}})
        self.call("attempt.submit", {"attempt_id": f"retest-answer-{n}", "activity_id": aid, "session_id": sid, "submitted_at": when, "answers": [{"problem_id": pid, "text": "Actual delayed answer."}]}, "My delayed answer.")
        review = f"retest-review-{n}"
        self.call("review.record", {"review_id": review, "attempt_id": f"retest-answer-{n}", "criterion_id": rid, "ratings": [{"problem_id": pid, "verdict": verdict, "rationale": "Judged the real answer.", "score": 10 if verdict == "correct" else 5 if verdict == "partial" else 0}]})
        self.last_retest = {"mistake_id": "M1", "review_id": review, "problem_id": pid, "variant_id": vid, "session_id": sid, "happened_at": when}
        if sheet: self.last_retest["review_sheet_id"] = sheet
        self.call("mistake.retest", self.last_retest)
        if settle: self.call("session.close", {"session_id": sid})
        return review

    def select_exam(self, kind="quiz", selection_id="SEL"):
        # Actual synthetic learning records, not fabricated request cycle alone.
        aid = next(e["id"] for e in self.state["objects"].values() if e["kind"] == "exercise")
        self.exam_days(aid, 84 if kind != "quiz" else 18)
        if kind != "quiz" and self.data("exam_bank", "BANK")["status"] != "frozen":
            self.call("exam_bank.freeze", {"bank_id": "BANK", "group_id": "G", "cycle": 14, "as_of": "2026-09-30T12:00:00Z"})
        self.call("exam.select", {"selection_id": selection_id, "bank_id": "BANK", "group_id": "G", "exam_type": kind, "cycle": 14 if kind != "quiz" else 3, "seed": "public-selection", "as_of": "2026-09-30T12:00:00Z"})
        return self.data("exam_selection", selection_id)

    def start_exam(self, aid, kind="quiz"):
        selected = self.select_exam(kind)
        self.call("exam.create", {"exam_id": "E1", "activity_id": aid, "selection_id": "SEL", "criterion_id": "exam-rubric", "started_at": "2026-09-30T18:00:00Z"})
        return selected

    def submit_exam(self):
        exam = self.data("exam", "E1")
        self.call("exam.submit", {"exam_id": "E1", "attempt_id": "exam-answer", "answers": [{"problem_id": pid, "text": "My actual timed solution."} for pid in exam["problem_ids"]], "submitted_at": "2026-09-30T18:08:00Z"}, "My submitted examination answers.")
        points = [x for x in self.data("criterion", "exam-rubric")["scoring_points"] if x["problem_id"] in exam["problem_ids"]]
        self.call("exam.self_assess", {"exam_id": "E1", "statement": "My steps hit these official points.", "mapping": [{"point_id": x["point_id"], "judgment": "hit", "answer_reference": "My written step 1"} for x in points]}, "My steps hit these official points.")
        if exam["exam_type"] != "quiz":
            self.call("exam.process.record", {"exam_id": "E1", "criterion_id": "process-rubric", "metrics": [{"metric_id": "retrieval", "score": 80, "rationale": "Confirmed synthetic retrieval checkpoint.", "evidence_refs": [{"kind": "checkpoint", "id": "CP1"}]}]})
        return [{"point_id": x["point_id"], "judgment": "hit", "rationale": "Matched the actual written step."} for x in points]


class LearningTests(unittest.TestCase):
    def setUp(self): self.i = Instance()

    def rejected(self, code, action, payload, student=None):
        before = deepcopy(self.i.state)
        with self.assertRaises(DomainError) as context:
            self.i.call(action, payload, student)
        self.assertEqual(code, context.exception.code)
        self.assertEqual(before, self.i.state, "Rejected actions must not mutate state")

    def test_preparation_is_not_current_session_source_delivery(self):
        aid, bids = self.i.lesson()
        self.assertEqual("source_pending", self.i.data("session", "s1")["readiness"])
        self.rejected("SOURCE_SCAN_REQUIRED", "ticket.issue", {"ticket_id": "t", "session_id": "s1", "block_id": bids[0], "body_sha256": self.i.data("block", bids[0])["body_sha256"]}, "继续")
        self.rejected("SCAN_COVERAGE", "scan.record", {"scan_id": "bad", "session_id": "s1", "scope_id": "scope-v1", "deliveries": self.i.deliveries()[:1]})

    def test_exam_clock_counts_real_distinct_learning_dates_and_corrections(self):
        aid = self.i.exam_bank()
        self.i.call("time.record", {"id": "duplicate-date", "activity_id": aid, "quality": "exact", "seconds": 15, "started_at": "2026-01-12T20:00:00Z"})
        self.i.call("time.record", {"id": "unknown-date", "activity_id": aid, "quality": "unknown"})
        payload = {"selection_id": "forged", "bank_id": "BANK", "group_id": "G", "exam_type": "quiz", "cycle": 3, "seed": "public", "as_of": "2026-09-30T12:00:00Z"}
        self.rejected("EXAM_CYCLE_MISMATCH", "exam.select", payload)
        self.i.exam_days(aid, 13)
        self.i.call("exam.select", payload)
        self.assertEqual(13, len(self.i.data("exam_selection", "forged")["trigger"]["learning_dates"]))
        self.i.call("time.record", {"id": "correct-date-13", "activity_id": aid, "quality": "unknown", "corrects": "exam-day-13"})
        self.rejected("EXAM_CYCLE_MISMATCH", "exam.select", {**payload, "selection_id": "corrected"})
        self.rejected("EXAM_CYCLE_MISMATCH", "exam.create", {"exam_id": "E", "activity_id": aid, "selection_id": "forged", "criterion_id": "exam-rubric", "started_at": "2026-09-30T18:00:00Z"})

    def test_schedule_exam_uses_confirmed_course_scope_without_progress_anchors(self):
        with tempfile.TemporaryDirectory() as path:
            journal = Journal(path)
            i = Instance(journal)
            aid = i.exam_bank("schedule")
            i.call("checkpoint.record", {"id": "CP-pending", "activity_id": aid, "status": "queued", "position": "Another planned concept", "evidence": ["Not yet learned."]})
            self.assertNotIn("keystone_ids", i.data("group", "G"))
            selection = i.start_exam(aid)
            self.assertEqual(selection["scope_snapshot"]["learned_node_ids"], ["CP1"])
            self.assertEqual([ref["id"] for ref in selection["scope_snapshot"]["checkpoint_refs"]], ["CP1"])
            self.assertEqual(selection["deferred_node_ids"], [])
            replay = Journal(path).read_state()
            self.assertEqual(get(replay, "exam", "E1")["status"], "open")
            self.assertEqual(get(replay, "exam_selection", "SEL")["scope_snapshot"], selection["scope_snapshot"])
            self.assertNotIn("keystone_total_frozen", get(replay, "group", "G"))

    def test_paused_course_rejects_new_attempt_and_supplement_needs_opt_in(self):
        aid = self.i.exercise()
        self.i.call("course.pause", {"id": "C", "reason": "Pause explicitly."}, "Pause this course.")
        self.rejected("COURSE_NOT_ONGOING", "attempt.submit", {"attempt_id": "paused", "activity_id": aid, "answers": [{"problem_id": "q1", "text": "New work"}]}, "My new work.")
        block = {"block_id": "extra", "activity_id": aid, "teacher_title": "Optional exercise", "source_role": "teacher_generated", "body": "A new optional exercise."}
        self.rejected("STUDENT_DECISION_REQUIRED", "block.create", block)
        self.i.call("block.create", block, "extra practice")
        self.assertEqual("extra practice", self.i.data("block", "extra")["opt_in"]["text"])

    def test_duplicate_questions_merge_retains_originals_and_requires_new_closure(self):
        aid = self.i.exercise()
        for ident, text in (("Q1", "Why this condition?"), ("Q2", "Why is that condition necessary?")):
            self.i.call("question.open", {"question_id": ident, "activity_id": aid, "text": text}, text)
        self.i.call("question.answer", {"question_id": "Q1", "answer": "Because of the defining requirement."})
        self.i.call("question.merge", {"question_id": "Q2", "into_question_id": "Q1", "reason": "Both ask about the same necessary condition."}, "merge questions")
        self.assertEqual("Why is that condition necessary?", self.i.data("question", "Q2")["text"])
        self.assertEqual("merged", self.i.data("question", "Q2")["status"])
        self.rejected("QUESTION_NOT_ANSWERED", "question.close", {"question_id": "Q1"}, "resolved")
        self.rejected("QUESTION_MERGED", "question.reopen", {"question_id": "Q2"}, "Ask again.")
        self.i.call("question.answer", {"question_id": "Q1", "answer": "This addresses both retained phrasings."})
        self.i.call("question.close", {"question_id": "Q1"}, "resolved")

    def test_retest_split_preserves_slots_and_consumes_only_actual_formal_results(self):
        aid = self.i.exercise(); review = self.i.attempt(aid, "wrong", "incorrect")
        self.i.call("mistake.record", {"mistake_id": "M1", "review_id": review, "problem_id": "q1", "root_cause": "Missing condition."})
        self.i.call("session.close", {"session_id": "s1"})
        self.i.call("session.start", {"session_id": "checks", "activity_id": aid})
        self.i.call("retest.plan", {"plan_id": "P", "session_id": "checks", "as_of": "2026-01-05T00:00:00Z", "seed": "visible"})
        slots = self.i.data("retest_plan", "P")["slots"]
        self.i.call("retest.pause", {"plan_id": "P"}, "split")
        actual = self.i.retest(aid, settle=False)
        self.i.call("retest.resume", {"plan_id": "P", "session_id": "retest-session-1"}, "resume checks")
        self.assertEqual(slots, self.i.data("retest_plan", "P")["slots"])
        self.rejected("RETEST_SESSION", "retest.result", {"plan_id": "P", "slot_index": 0, "review_id": review, "problem_id": "q1"})
        self.i.call("retest.result", {"plan_id": "P", "slot_index": 0, "review_id": actual, "problem_id": "probe-1"})
        self.assertEqual("complete", self.i.data("retest_plan", "P")["status"])
        self.assertEqual([], self.i.data("retest_plan", "P")["pending_slots"])
        self.rejected("RETEST_COMPLETE", "retest.result", {"plan_id": "P", "slot_index": 0, "review_id": actual, "problem_id": "probe-1"})

    def test_safe_variant_can_attach_to_existing_lesson_without_inventing_activity(self):
        aid = self.i.exercise(); review = self.i.attempt(aid, "wrong", "incorrect")
        self.i.call("mistake.record", {"mistake_id": "M1", "review_id": review, "problem_id": "q1", "knowledge_key": "condition", "root_cause": "Missing condition."})
        self.i.call("activity.create", {"id": "C/existing-lesson", "course_id": "C", "activity_type": "lesson", "title": "Already planned Lesson"})
        payload = {"variant_id": "lesson-probe", "mistake_id": "M1", "activity_id": "C/existing-lesson", "problem_id": "probe", "probe": "P1", "body": "Rephrased definition probe.", "self_solution": "The defining condition stated fully.", "judgment_basis": "Names necessary condition.", "transformation": "rephrase", "safety": {"self_solved": True, "solvable": True, "judgment_clear": True, "reference": "actual synthetic self-check"}}
        self.rejected("VARIANT_SAFETY", "variant.create", {**payload, "safety": {**payload["safety"], "self_solved": False}})
        before = {k for k in self.i.state["objects"] if k.startswith("activity/")}
        self.i.call("variant.create", payload)
        self.assertEqual(before, {k for k in self.i.state["objects"] if k.startswith("activity/")})
        self.assertEqual("lesson_probes", self.i.data("exercise", "C/existing-lesson")["carrier_kind"])

    def test_aged_window_uses_named_segments_and_only_one_reminder_per_cycle(self):
        aid = self.i.exercise(); review = self.i.attempt(aid, "wrong", "incorrect")
        self.i.call("mistake.record", {"mistake_id": "M1", "review_id": review, "problem_id": "q1", "knowledge_key": "condition", "root_cause": "Missing condition."})
        for _ in range(3): self.i.retest(aid, "incorrect")
        self.i.exam_days(aid, 6)
        for wid in ("W1", "W2"):
            self.i.call("aged_review.window", {"window_id": wid, "course_id": "C", "as_of": "2026-02-01T12:00:00Z"})
        self.assertEqual("reminder", self.i.data("aged_window", "W1")["status"])
        self.assertEqual("no_window", self.i.data("aged_window", "W2")["status"])
        segments = []
        for n in range(3):
            cp = f"segment-cp-{n}"
            for status in ("queued", "arrived", "pending", "confirmed"):
                self.i.call("checkpoint.record", {"id": cp, "activity_id": aid, "status": status, "position": f"named cluster {n}", "evidence": ["Actual synthetic checkpoint answer."]}, "Understood this cluster." if status == "confirmed" else None)
            segments.append({"segment_id": f"S{n}", "title": f"Named course cluster {n}", "checkpoint_ids": [cp], "knowledge_keys": ["condition"]})
        self.i.call("learning_structure.configure", {"course_id": "C", "segments": segments}, "Use these named course sections.")
        for n in range(3): self.i.call("learning_segment.complete", {"course_id": "C", "segment_id": f"S{n}", "completed_at": "2026-01-31T12:00:00Z"})
        self.i.call("aged_review.window", {"window_id": "W3", "course_id": "C", "as_of": "2026-02-01T12:00:00Z", "related_segment_id": "C/S2"})
        self.assertEqual("candidate", self.i.data("aged_window", "W3")["status"])
        self.assertEqual(["M1"], self.i.data("aged_window", "W3")["eligible_mistake_ids"])
        self.i.call("variant.create", {"variant_id": "sheet-probe", "mistake_id": "M1", "activity_id": aid, "problem_id": "sheet-q", "probe": "P2", "body": "A fresh boundary condition question.", "self_solution": "Complete self solution.", "judgment_basis": "Checks the required condition.", "transformation": "boundary", "safety": {"self_solved": True, "solvable": True, "judgment_clear": True, "reference": "actual synthetic self check"}})
        p = {"sheet_id": "auto-sheet", "activity_id": aid, "variant_ids": ["sheet-probe"], "context_closure": "Named condition cluster closed.", "as_of": "2026-02-01T12:00:00Z"}
        self.rejected("MISSING_FIELD", "aged_review.create", p)
        self.i.call("aged_review.create", {**p, "window_id": "W3"})
        self.assertEqual("proposed", self.i.data("aged_review", "auto-sheet")["status"])
        self.i.call("aged_review.authorize", {"sheet_id": "auto-sheet", "body_sha256": learning.digest(self.i.data("aged_review", "auto-sheet")["proposal"])}, "authorize review")
        self.assertEqual("auto-sheet", self.i.data("aged_window", "W3")["used_by"])

    def test_exam_three_stage_failure_uses_fresh_papers_and_real_review_units(self):
        aid = self.i.exam_bank(paper_count=90); used = set(); previous = None
        for stage in ("final", "retake1", "retake2"):
            selection = self.i.select_exam(stage, "select-"+stage)
            selected_papers = {self.i.data("exam_bank", "BANK")["problems"][pid]["paper_id"] for pid in selection["problem_ids"]}
            self.assertFalse(used & selected_papers); used |= selected_papers
            payload = {"exam_id": stage, "activity_id": aid, "selection_id": "select-"+stage, "criterion_id": "exam-rubric", "started_at": "2026-09-30T18:00:00Z"}
            if previous: payload["previous_exam_id"] = previous
            self.i.call("exam.create", payload)
            self.i.call("exam.submit", {"exam_id": stage, "attempt_id": "answer-"+stage, "answers": [{"problem_id": pid, "text": "My incorrect solution."} for pid in selection["problem_ids"]], "submitted_at": "2026-09-30T18:08:00Z"}, "These are my actual exam answers.")
            points = [x for x in self.i.data("criterion", "exam-rubric")["scoring_points"] if x["problem_id"] in selection["problem_ids"]]
            self.i.call("exam.self_assess", {"exam_id": stage, "statement": "My answers missed these points.", "mapping": [{"point_id": x["point_id"], "judgment": "miss", "answer_reference": "My incorrect step."} for x in points]}, "My answers missed these points.")
            self.i.call("exam.process.record", {"exam_id": stage, "criterion_id": "process-rubric", "metrics": [{"metric_id": "retrieval", "score": 80, "rationale": "Actual checkpoint evidence.", "evidence_refs": [{"kind": "checkpoint", "id": "CP1"}]}]})
            self.i.call("exam.grade", {"exam_id": stage, "review_id": "grade-"+stage, "point_verdicts": [{"point_id": x["point_id"], "judgment": "miss", "rationale": "Actual written condition is absent."} for x in points]})
            self.i.call("exam.recover_mistakes", {"exam_id": stage, "roots": [{"problem_id": pid, "mistake_id": "exam-root", "knowledge_key": "condition", "root_cause": "Necessary condition omitted."} for pid in selection["problem_ids"]]})
            self.i.call("exam.settle", {"exam_id": stage})
            if stage != "retake2":
                self.assertEqual("review_required", self.i.data("exam", stage)["settlement"])
                review = self.i.attempt(aid, "review-unit-"+stage)
                feeling = "I can now identify the missing condition."
                self.i.call("exam.review.complete", {"exam_id": stage, "evidence": [{"kind": "review", "id": review}], "student": {"role": "student", "source": "actual synthetic review response", "text": feeling}, "student_feeling": feeling, "dependency_diagnosis": "Return to the prerequisite definition."})
                self.assertEqual("retake_ready", self.i.data("exam", stage)["settlement"])
            previous = stage
        self.assertEqual("failed_final", self.i.data("exam", "retake2")["settlement"])
        self.assertEqual("ongoing", self.i.data("course", "C")["status"], "Course closure still requires the explicit lifecycle decision.")
        self.assertTrue(self.i.data("mistake", "exam-root")["recurrences"])

    def test_reminder_threshold_creates_and_consumes_three_distinct_learning_dates(self):
        aid = self.i.exam_bank(); selected = self.i.start_exam(aid)
        for n in range(len(selected["problem_ids"])+1):
            self.i.call("exam.reminder", {"exam_id": "E1", "problem_id": selected["problem_ids"][0], "level": "clarification", "content": "The original statement has this condition.", "student_request": {"role": "student", "source": f"actual request {n}", "text": "Please clarify the statement."}})
        self.assertEqual("planned", self.i.data("exam_reinforcement", "E1")["status"])
        checks = self.i.submit_exam()
        self.i.call("exam.grade", {"exam_id": "E1", "review_id": "exam-judgment", "point_verdicts": checks})
        self.i.call("exam.reinforcement.configure", {"exam_id": "E1", "activity_ids": [aid], "purpose": "Rebuild independent reading of conditions."}, "Use this three-learning-date block.")
        for n in range(1, 4):
            self.i.call("time.record", {"id": f"reinforce-{n}", "activity_id": aid, "quality": "exact", "seconds": 300, "started_at": f"2026-10-0{n}T12:00:00Z"})
            review = self.i.attempt(aid, f"reinforce-answer-{n}")
            p = {"exam_id": "E1", "timespan_id": f"reinforce-{n}", "evidence_refs": [{"kind": "review", "id": review}]}
            self.i.call("exam.reinforcement.record", p)
            if n == 1: self.rejected("REINFORCEMENT_DATE", "exam.reinforcement.record", p)
        self.assertEqual("complete", self.i.data("exam_reinforcement", "E1")["status"])

    def test_summary_wrong_page_and_past_session_do_not_count_as_scan(self):
        self.i.lesson()
        for field, value, code in [("content", "a summary", "SCAN_CONTENT"), ("printed_page_label", "wrong", "SCAN_IDENTITY"), ("session_id", "past", "SCAN_SESSION_MISMATCH")]:
            deliveries = self.i.deliveries(); deliveries[0][field] = value
            self.rejected(code, "scan.record", {"scan_id": "bad", "session_id": "s1", "scope_id": "scope-v1", "deliveries": deliveries})

    def test_review_correction_chain_preserves_original_and_rejects_branch(self):
        aid = self.i.exercise(); original = self.i.attempt(aid, "one-original")
        payload = {"attempt_id": "one-original", "criterion_id": "rubric-v1", "correction_reason": "Clarified rationale for the same answer.", "ratings": [{"problem_id": "q1", "verdict": "correct", "score": 10, "rationale": "The original response meets the fixed criterion."}]}
        self.i.call("review.record", {**payload, "review_id": "second", "supersedes": original})
        self.rejected("REVIEW_SUPERSEDED", "review.record", {**payload, "review_id": "branch", "supersedes": original})
        self.i.call("review.record", {**payload, "review_id": "third", "supersedes": "second"})
        self.assertEqual("second", self.i.data("review", "third")["supersedes"])
        self.assertEqual("one-original", self.i.data("review", original)["attempt_id"])

    def test_recovered_unknown_help_never_becomes_none_or_independent(self):
        aid = self.i.exercise()
        # Synthetic migration input, not a newly fabricated teacher hint.
        self.i.state["objects"][key("exercise", aid)]["data"]["assistance"].append({"problem_id": "q1", "level": "legacy_unknown", "evidence_class": "legacy_uncertain", "evidence_refs": ["frozen original exercise history"]})
        review = self.i.attempt(aid, "recovered-new-answer")
        rating = self.i.data("review", review)["ratings"][0]
        self.assertFalse(rating["independent"])
        self.assertEqual("legacy_uncertain", rating["evidence_class"])
        help_ = self.i.data("attempt", "recovered-new-answer")["assistance"]["q1"]
        self.assertEqual("legacy_unknown", help_["level"])
        self.assertFalse(help_["polluted"], "Unknown history is not proof that a teacher polluted the question.")

    def test_corrected_prior_timespan_blocks_reinforcement_completion(self):
        aid = self.i.exam_bank(); selected = self.i.start_exam(aid)
        for n in range(len(selected["problem_ids"])+1):
            self.i.call("exam.reminder", {"exam_id": "E1", "problem_id": selected["problem_ids"][0], "level": "clarification", "content": "Clarify the condition.", "student_request": {"role": "student", "source": str(n), "text": "Please clarify."}})
        self.i.call("exam.grade", {"exam_id": "E1", "review_id": "exam-judgment", "point_verdicts": self.i.submit_exam()})
        self.i.call("exam.reinforcement.configure", {"exam_id": "E1", "activity_ids": [aid], "purpose": "Independent learning."}, "Use these three dates.")
        for n in (1, 2):
            self.i.call("time.record", {"id": f"day-{n}", "activity_id": aid, "quality": "exact", "seconds": 300, "started_at": f"2026-10-0{n}T12:00:00Z"})
            review = self.i.attempt(aid, f"new-answer-{n}")
            self.i.call("exam.reinforcement.record", {"exam_id": "E1", "timespan_id": f"day-{n}", "evidence_refs": [{"kind": "review", "id": review}]})
        self.i.call("time.record", {"id": "corrected-day-1", "corrects": "day-1", "activity_id": aid, "quality": "exact", "seconds": 300, "started_at": "2026-10-02T12:00:00Z"})
        self.i.call("time.record", {"id": "day-3", "activity_id": aid, "quality": "exact", "seconds": 300, "started_at": "2026-10-03T12:00:00Z"})
        review = self.i.attempt(aid, "new-answer-3")
        self.rejected("TIME_SUPERSEDED", "exam.reinforcement.record", {"exam_id": "E1", "timespan_id": "day-3", "evidence_refs": [{"kind": "review", "id": review}]})
        self.assertEqual("active", self.i.data("exam_reinforcement", "E1")["status"])

    def test_one_block_permission_correct_feedback_and_feeling_are_separate(self):
        aid, bids = self.i.lesson(); self.i.ready(); self.i.ticket(bids[0]); self.i.present(bids[0]); effects = self.i.answer(bids[0])
        cursor = next(e["data"] for e in effects if e["kind"] == "cursor")
        self.assertEqual("correct", cursor["judgement"]["verdict"]); self.assertEqual("feeling", cursor["waiting_for"])
        self.assertEqual("ongoing", self.i.data("activity", aid)["status"])
        self.rejected("PREVIOUS_GATE_OPEN", "ticket.issue", {"ticket_id": "t2", "session_id": "s1", "block_id": bids[1], "body_sha256": self.i.data("block", bids[1])["body_sha256"]}, "继续")
        self.i.call("feeling.record", {"session_id": "s1", "block_id": bids[0], "disposition": "clear"}, "I feel clear now.")
        self.assertEqual("authorization", self.i.data("cursor", aid)["waiting_for"])
        self.assertEqual("consumed", self.i.data("ticket", "t1")["status"])

    def test_ticket_reuse_body_substitution_and_negative_intent_are_rejected(self):
        aid, bids = self.i.lesson(); self.i.ready()
        payload = {"ticket_id": "t", "session_id": "s1", "block_id": bids[0], "body_sha256": self.i.data("block", bids[0])["body_sha256"]}
        self.rejected("UNBOUND_DECISION", "ticket.issue", payload, "stop")
        self.i.ticket(bids[0]); self.rejected("BODY_CHANGED", "block.present", {"session_id": "s1", "block_id": bids[0], "ticket_id": "t1", "body_sha256": "0"*64})
        self.i.present(bids[0]); self.rejected("TICKET_SPENT", "block.present", {"session_id": "s1", "block_id": bids[0], "ticket_id": "t1", "body_sha256": self.i.data("block", bids[0])["body_sha256"]})

    def test_ticket_accepts_attributed_natural_represent_choice_without_claiming_authentication(self):
        _, bids = self.i.lesson(); self.i.ready()
        payload = {"ticket_id": "t", "session_id": "s1", "block_id": bids[0], "body_sha256": self.i.data("block", bids[0])["body_sha256"]}
        self.rejected("UNBOUND_DECISION", "ticket.issue", payload, "不要重讲这一段。")
        self.i.call("ticket.issue", payload, "把保存的这一段重讲一下")
        decision = self.i.data("ticket", "t")["decision"]
        self.assertEqual(decision["text"], "把保存的这一段重讲一下")
        self.assertFalse(decision["decision_basis"]["host_identity_authenticated"])
        self.assertFalse(decision["decision_basis"]["semantic_intent_machine_verified"])

    def test_session_close_revokes_unspent_permission_and_new_scan_is_required(self):
        aid, bids = self.i.lesson(); self.i.ready(); self.i.ticket(bids[0])
        self.i.call("session.close", {"session_id": "s1"})
        self.assertEqual("revoked", self.i.data("ticket", "t1")["status"])
        self.assertEqual("ongoing", self.i.data("activity", aid)["status"])
        self.i.call("session.start", {"session_id": "s2", "activity_id": aid})
        self.assertEqual("source_pending", self.i.data("session", "s2")["readiness"])
        self.rejected("SCAN_SESSION_MISMATCH", "scan.record", {"scan_id": "old-scan-copy", "session_id": "s2", "scope_id": "scope-v1", "deliveries": self.i.deliveries("s1")})

    def test_unanswered_question_blocks_next_block_and_close_restores_gate(self):
        aid, bids = self.i.lesson(); self.i.ready(); self.i.ticket(bids[0]); self.i.present(bids[0]); self.i.answer(bids[0])
        self.i.call("feeling.record", {"session_id": "s1", "block_id": bids[0], "disposition": "question"}, "Why does this follow?")
        self.i.call("question.open", {"question_id": "Q1", "activity_id": aid, "text": "Why does this follow?"}, "Why does this follow?")
        self.rejected("QUESTION_NOT_ANSWERED", "question.close", {"question_id": "Q1"}, "resolved")
        self.i.call("question.answer", {"question_id": "Q1", "answer": "Because of the defining condition."})
        self.i.call("question.close", {"question_id": "Q1"}, "resolved")
        self.assertEqual("authorization", self.i.data("cursor", aid)["waiting_for"])
        self.i.ticket(bids[1], "t2")

    def test_no_comprehension_judgment_without_actual_answer_or_frozen_criterion(self):
        aid, bids = self.i.lesson(); self.i.ready(); self.i.ticket(bids[0]); self.i.present(bids[0])
        self.rejected("RESPONSE_MISSING", "comprehension.record", {"session_id": "s1", "block_id": bids[0], "response_id": "invented", "criterion_id": "criterion-1", "verdict": "correct", "rationale": "The student probably knows."})
        self.rejected("CRITERION_TOO_LATE", "criterion.create", {"criterion_id": "retroactive", "target_kind": "block", "target_id": bids[0], "rubric": "Whatever the answer said."})
        self.i.answer(bids[0]); self.assertEqual("My own defining condition.", self.i.data("block", bids[0])["responses"][0]["answer"])

    def test_page_turn_requires_current_notice_tree_and_actual_coverage(self):
        aid, bids = self.i.lesson(); self.i.ready(); self.i.ticket(bids[0]); self.i.present(bids[0]); self.i.answer(bids[0])
        self.i.call("feeling.record", {"session_id": "s1", "block_id": bids[0], "disposition": "clear"}, "clear")
        self.i.ticket(bids[1], "t2")
        self.rejected("MISSING_FIELD", "block.present", {"session_id": "s1", "block_id": bids[1], "ticket_id": "t2", "body_sha256": self.i.data("block", bids[1])["body_sha256"]})
        self.i.present(bids[1], "t2", page_turn={"announced_page_id": "page-2", "classroom_tree": "Page 12: Definition 2", "previous_page_coverage": {bids[0]: "covered"}})
        self.assertEqual(bids[1], self.i.data("cursor", aid)["block_id"])

    def test_scope_contiguity_and_unfinished_rollover_fail_closed(self):
        self.i.course(); self.i.sources(6); aid = self.i.activity(); bids = [self.i.block(aid,n) for n in range(1,7)]
        self.rejected("NONCONTIGUOUS_SCOPE", "scope.create", {"scope_id": "bad", "activity_id": aid, "source_id": "book-v1", "page_ids": ["page-1","page-2","page-4","page-5","page-6"], "current_page_id": "page-1"})
        for start in (1,2):
            pages = [f"page-{n}" for n in range(start,start+5)]
            self.i.call("scope.create", {"scope_id": f"scope-{start}", "activity_id": aid, "source_id": "book-v1", "page_ids": pages, "current_page_id": pages[0]})
            self.i.call("lessonmap.create", {"lessonmap_id": f"map-{start}", "activity_id": aid, "scope_id": f"scope-{start}", "block_ids": bids[start-1:start+4]})
            payload = {"preparation_id": f"prep-{start}", "activity_id": aid, "scope_id": f"scope-{start}", "lessonmap_id": f"map-{start}", "receipts": [{"page_id": x,"reference":"fixture","verified_text_sha256":self.i.data("page",x)["verified_text_sha256"],"source_document_sha256":self.i.data("source","book-v1")["content_sha256"]} for x in pages]}
            if start == 1: self.i.call("preparation.create",payload)
            else: self.rejected("UNCLOSED_SCOPE_BLOCK","preparation.create",payload)

    def test_teacher_title_does_not_overwrite_source_role_or_original_excerpt(self):
        aid, bids = self.i.lesson()
        block = self.i.data("block", bids[0])
        self.assertEqual("definition", block["source_role"])
        self.assertNotEqual(block["teacher_title"], block["source_refs"][0]["source_excerpt"])
        self.rejected("EXCERPT_MISMATCH", "block.create", {"block_id": "forged", "activity_id": aid, "teacher_title": "Claim", "source_role": "theorem", "body": "Invented claim", "source_refs": [{"page_id": "page-1", "source_excerpt": "Never in the original.", "locator": "somewhere"}]})

    def test_help_level_is_exact_permission_and_never_independent_mastery(self):
        aid = self.i.exercise()
        self.rejected("MISSING_FIELD", "hint.record", {"session_id": "s1", "problem_id": "q1", "level": "direction", "content": "Try the defining condition."})
        self.i.call("hint.authorize", {"ticket_id": "help", "session_id": "s1", "problem_id": "q1", "level": "direction"}, "direction")
        self.rejected("HINT_PERMISSION", "hint.record", {"session_id": "s1", "problem_id": "q1", "level": "solution", "content": "Full answer", "ticket_id": "help"})
        self.i.call("hint.record", {"session_id": "s1", "problem_id": "q1", "level": "direction", "content": "Try the condition.", "ticket_id": "help"})
        review = self.i.attempt(aid, "a1")
        self.assertFalse(self.i.data("review", review)["ratings"][0]["independent"])
        self.assertEqual("direction", self.i.data("attempt", "a1")["assistance"]["q1"]["level"])

    def test_concept_help_requires_scope_only_and_does_not_raise_assistance(self):
        aid = self.i.exercise()
        self.rejected("HINT_SCOPE", "hint.record", {"session_id": "s1", "problem_id": "q1", "level": "concept", "content": "A concept explanation"})
        self.i.call("hint.record", {"session_id": "s1", "problem_id": "q1", "level": "concept", "content": "Only the asked concept.", "scope_only": True})
        review = self.i.attempt(aid, "a1")
        self.assertTrue(self.i.data("review", review)["ratings"][0]["independent"])

    def test_natural_hint_and_supplement_keep_same_level_and_original_source_order(self):
        aid = self.i.exercise()
        hint = {"ticket_id": "natural-help", "session_id": "s1", "problem_id": "q1", "level": "direction"}
        self.rejected("UNBOUND_DECISION", "hint.authorize", hint, "I do not want a direction hint.")
        self.i.call("hint.authorize", hint, "Could you give me a small nudge in the right direction?")
        self.rejected("HINT_PERMISSION", "hint.record", {"session_id": "s1", "problem_id": "q1", "level": "solution", "content": "Full answer", "ticket_id": "natural-help"})
        self.i.call("hint.record", {"session_id": "s1", "problem_id": "q1", "level": "direction", "content": "Inspect the defining condition.", "ticket_id": "natural-help"})
        self.i.call("problem.add", {"activity_id": aid, "problem_id": "extra-natural", "text": "Explain a fresh example.", "origin": "teacher_generated"}, "我想再试一道类似的题，帮我安排吧。")
        exercise = self.i.data("exercise", aid)
        self.assertEqual(exercise["source_order"], ["q1"])
        self.assertEqual(exercise["supplemental_ids"], ["extra-natural"])
        self.assertEqual(self.i.data("ticket", "natural-help")["status"], "consumed")
        self.assertFalse(self.i.data("ticket", "natural-help")["decision"]["decision_basis"]["semantic_intent_machine_verified"])

    def test_attempt_keeps_original_answers_and_rejects_later_rubric(self):
        aid = self.i.exercise()
        self.i.call("attempt.submit", {"activity_id": aid, "attempt_id": "a1", "answers": [{"problem_id": "q1", "text": "Actual first answer."}]}, "My first answer.")
        self.i.call("criterion.create", {"criterion_id": "rubric-v2", "target_kind": "exercise", "target_id": aid, "rubric": "Changed later", "problem_ids": ["q1"], "max_scores": {"q1": 10}})
        self.rejected("CRITERION_CHANGED", "review.record", {"review_id": "wrong-rubric", "attempt_id": "a1", "criterion_id": "rubric-v2", "ratings": [{"problem_id": "q1", "verdict": "correct", "rationale": "Later definition", "score": 10}]})
        self.assertEqual("Actual first answer.", self.i.data("attempt", "a1")["answers"][0]["text"])

    def test_review_cannot_invent_questions_or_independent_evidence(self):
        aid = self.i.exercise()
        self.i.call("attempt.submit", {"activity_id": aid, "attempt_id": "a1", "answers": [{"problem_id": "q1", "text": "Actual answer."}]}, "Answer submitted.")
        self.rejected("REVIEW_PROBLEMS", "review.record", {"review_id": "extra", "attempt_id": "a1", "criterion_id": "rubric-v1", "ratings": [{"problem_id": "invented", "verdict": "correct", "rationale": "No such answer", "score": 1}]})
        self.rejected("FALSE_INDEPENDENCE", "review.record", {"review_id": "wrong", "attempt_id": "a1", "criterion_id": "rubric-v1", "ratings": [{"problem_id": "q1", "verdict": "incorrect", "rationale": "Incorrect condition", "score": 0, "independent": True}]})

    def test_mistake_retests_require_new_actual_evidence_and_reopen_after_retirement(self):
        aid = self.i.exercise(); first = self.i.attempt(aid, "initial", "incorrect")
        self.i.call("mistake.record", {"mistake_id": "M1", "review_id": first, "problem_id": "q1", "root_cause": "Confused necessary and sufficient conditions."})
        for n in range(3):
            rid = self.i.retest(aid)
        self.assertEqual("maintenance", self.i.data("mistake", "M1")["status"])
        self.rejected("RETEST_DUPLICATE", "mistake.retest", self.i.last_retest)
        self.i.retest(aid, "incorrect")
        self.assertEqual("active", self.i.data("mistake", "M1")["status"])

    def test_six_partial_retests_become_aged_and_two_later_sheets_restore_maintenance(self):
        aid = self.i.exercise(); rid = self.i.attempt(aid, "initial", "incorrect")
        self.i.call("mistake.record", {"mistake_id": "M1", "review_id": rid, "problem_id": "q1", "root_cause": "Wrong condition"})
        for n in range(6):
            self.i.retest(aid, "partial")
        self.assertEqual("aged", self.i.data("mistake", "M1")["status"])
        self.i.retest(aid, "incorrect")
        self.assertEqual("aged", self.i.data("mistake", "M1")["status"], "An aged failure does not restart dense reinforcement")
        self.i.retest(aid); self.i.retest(aid)
        self.assertEqual("maintenance", self.i.data("mistake", "M1")["status"])

    def test_three_wrong_retests_age_and_original_same_answer_cannot_count(self):
        aid = self.i.exercise(); rid = self.i.attempt(aid, "initial", "incorrect")
        self.i.call("mistake.record", {"mistake_id": "M1", "review_id": rid, "problem_id": "q1", "root_cause": "Wrong condition"})
        self.rejected("RETEST_DUPLICATE", "mistake.retest", {"mistake_id": "M1", "review_id": rid, "problem_id": "q1"})
        for _ in range(3): self.i.retest(aid, "incorrect")
        self.assertEqual("aged", self.i.data("mistake", "M1")["status"])

    def test_preserved_cycle_attempt_limit_and_new_cycle_do_not_erase_or_reuse_baseline(self):
        for status, attempts, successes, failures, verdict in [("active", 5, 0, 2, "partial"), ("maintenance", 3, 3, 0, "incorrect")]:
            with self.subTest(status=status):
                self.i = Instance(); aid = self.i.exercise(); review = self.i.attempt(aid, "origin", "incorrect")
                self.i.call("mistake.record", {"mistake_id": "M1", "review_id": review, "problem_id": "q1", "root_cause": "Synthetic preserved knowledge point"})
                baseline = {"attempts": attempts, "successes": successes, "failures": failures, "independent_streak": successes, "aged_success_streak": 0, "cycle": 2, "status": status, "last_learning_date": "2026-01-01", "cycle_start": 0, "evidence_refs": ["synthetic preserved summary"]}
                # A recovered historical summary is a fixture, not new review evidence.
                self.i.state["objects"][key("mistake", "M1")]["data"].update(legacy_cycle_baseline=deepcopy(baseline), status=status, cycle=2, cycle_attempts=attempts, cycle_successes=successes, failed_retests=failures, independent_streak=successes, recovery_not_before="2026-01-01")
                self.i.retest(aid, verdict, settle=False)
                pending = self.i.data("mistake", "M1")
                self.assertEqual(status, pending["status"], "The observed new result remains provisional until session close.")
                self.i.call("session.close", {"session_id": self.i.last_retest["session_id"]})
                actual = self.i.data("mistake", "M1")
                self.assertEqual(baseline, actual["legacy_cycle_baseline"])
                if status == "active":
                    self.assertEqual("aged", actual["status"])
                    self.assertEqual(6, actual["cycle_attempts"])
                else:
                    self.assertEqual("active", actual["status"])
                    self.assertEqual((1, 0, 1, 3), (actual["cycle_attempts"], actual["cycle_successes"], actual["failed_retests"], actual["cycle"]))
                    self.assertFalse(actual["legacy_cycle_baseline_active"])

    def test_recovered_due_learning_dates_exclude_replaced_and_unknown_spans(self):
        aid = self.i.exercise(); review = self.i.attempt(aid, "origin", "incorrect")
        self.i.call("mistake.record", {"mistake_id": "M1", "review_id": review, "problem_id": "q1", "root_cause": "Preserved date gate"})
        self.i.state["objects"][key("mistake", "M1")]["data"].update(legacy_cycle_baseline={"attempts": 0, "successes": 0, "failures": 0, "independent_streak": 0, "cycle_start": 0}, recovery_learning_date_anchor="2026-01-01", recovery_min_subsequent_learning_dates=3)
        for day in (2, 3, 4):
            self.i.call("time.record", {"id": f"day-{day}", "activity_id": aid, "quality": "exact", "seconds": 30, "started_at": f"2026-01-0{day}T12:00:00Z"})
        self.i.call("time.record", {"id": "replace-day-4", "corrects": "day-4", "activity_id": aid, "quality": "exact", "seconds": 30, "started_at": "2026-01-03T14:00:00Z"})
        self.i.call("time.record", {"id": "unknown-day-4", "activity_id": aid, "quality": "unknown", "started_at": "2026-01-04T12:00:00Z"})
        with self.assertRaises(DomainError) as caught: self.i.retest(aid)
        self.assertEqual("RETEST_RECOVERY_DUE", caught.exception.code)
        self.assertEqual([], self.i.data("mistake", "M1")["retests"])

    def test_retest_result_is_provisional_until_session_closes(self):
        aid = self.i.exercise(); rid = self.i.attempt(aid, "initial", "incorrect")
        self.i.call("mistake.record", {"mistake_id": "M1", "review_id": rid, "problem_id": "q1", "root_cause": "Wrong condition"})
        self.i.retest(aid); self.i.retest(aid); self.i.retest(aid, settle=False)
        mistake = self.i.data("mistake", "M1")
        self.assertEqual("active", mistake["status"])
        self.assertEqual("maintenance", mistake["pending_settlement"]["changes"]["status"])
        self.assertFalse(mistake["retests"][-1]["settled"])
        self.i.call("session.close", {"session_id": self.i.last_retest["session_id"]})
        self.assertEqual("maintenance", self.i.data("mistake", "M1")["status"])

    def test_atomic_comprehension_keeps_real_answer_and_one_revision(self):
        with tempfile.TemporaryDirectory() as path:
            journal = Journal(path); i = Instance(journal)
            aid, bids = i.lesson(); i.ready(); i.ticket(bids[0]); i.present(bids[0]); before = i.state["revision"]
            payload = {"session_id": "s1", "block_id": bids[0], "response_id": "atomic-answer", "answer": "My exact answer.", "criterion_id": "criterion-1", "verdict": "correct", "rationale": "It states the required condition.", "student": {"role": "student", "source": "actual synthetic student turn", "text": "My exact answer."}}
            i.call("comprehension.assess", payload)
            self.assertEqual(before+1, i.state["revision"])
            self.assertEqual("feeling", i.data("cursor", aid)["waiting_for"])
            self.assertEqual("My exact answer.", i.data("block", bids[0])["responses"][0]["answer"])
            self.assertEqual("correct", i.data("cursor", aid)["judgement"]["verdict"])

    def test_atomic_comprehension_rejects_invented_attribution_without_partial_save(self):
        aid, bids = self.i.lesson(); self.i.ready(); self.i.ticket(bids[0]); self.i.present(bids[0])
        p = {"session_id": "s1", "block_id": bids[0], "response_id": "atomic-answer", "answer": "Actual answer.", "criterion_id": "criterion-1", "verdict": "correct", "rationale": "Teacher judgment.", "student": {"role": "student", "source": "synthetic turn", "text": "A different answer."}}
        self.rejected("ANSWER_ATTRIBUTION", "comprehension.assess", p)
        p["student"]["text"] = p["answer"]; p["criterion_id"] = "criterion-2"
        self.rejected("CRITERION_TARGET", "comprehension.assess", p)

    def test_ocr_raw_correction_verification_are_separate_and_old_scope_is_stale(self):
        aid, bids = self.i.lesson(); self.i.ready()
        self.i.call("ocr.capture", {"ocr_id": "RAW", "source_id": "book-v1", "pdf_page_index": 1, "raw_text": "Definltion 1.", "tool": "synthetic OCR", "reference": "original PDF page"})
        self.i.call("ocr.correct", {"correction_id": "FIX", "ocr_id": "RAW", "text": "Definition 1. Corrected original text.", "changes": ["l to i"], "unresolved": []})
        self.rejected("NOT_FOUND", "page.from_ocr", {"page_id": "corrected", "verification_id": "RAW", "printed_page_label": "11"})
        self.i.call("ocr.verify", {"verification_id": "VER", "correction_id": "FIX", "visual_reference": "Actual synthetic original visual comparison", "source_document_sha256": self.i.data("source", "book-v1")["content_sha256"], "line_by_line": True, "key_symbols_checked": True})
        self.i.call("page.from_ocr", {"page_id": "corrected", "verification_id": "VER", "printed_page_label": "11", "supersedes_page_id": "page-1", "correction_reason": "Verified correction", "layout_critical": False})
        self.assertEqual("Definltion 1.", self.i.data("ocr_raw", "RAW")["raw_text"])
        self.assertEqual("corrected", self.i.data("page_head", "book-v1/1")["page_id"])
        self.rejected("PAGE_SUPERSEDED", "ticket.issue", {"ticket_id": "t", "session_id": "s1", "block_id": bids[0], "body_sha256": self.i.data("block", bids[0])["body_sha256"]}, "继续")

    def test_supplemental_problem_is_opt_in_and_original_order_never_lost(self):
        aid = self.i.exercise()
        payload = {"activity_id": aid, "problem_id": "extra", "text": "A supplemental question", "origin": "teacher_generated"}
        self.rejected("STUDENT_DECISION_REQUIRED", "problem.add", payload)
        self.i.call("problem.add", payload, "extra practice")
        self.i.call("exercise.reorder", {"activity_id": aid, "teaching_sequence": ["extra", "q1"], "reason": "Student asked to begin with the supplement."})
        self.assertEqual(["q1"], self.i.data("exercise", aid)["source_order"])
        self.assertEqual(["extra"], self.i.data("exercise", aid)["supplemental_ids"])

    def test_exam_isolation_actual_submission_frozen_grade_and_cooldown(self):
        aid = self.i.exam_bank(); selected = self.i.start_exam(aid)
        self.rejected("EXAM_NOT_SUBMITTED", "exam.grade", {"exam_id": "E1", "review_id": "R1", "ratings": []})
        checks = self.i.submit_exam()
        self.i.call("exam.grade", {"exam_id": "E1", "review_id": "exam-review", "point_verdicts": checks})
        self.assertTrue(self.i.data("exam", "E1")["passed"])
        self.assertEqual([], self.i.data("exercise", aid)["attempt_ids"], "Exam is not an ordinary exercise attempt statistic")
        self.rejected("EXAM_EXPOSURE", "exam.create", {"exam_id": "E2", "activity_id": aid, "selection_id": "SEL", "criterion_id": "exam-rubric", "started_at": "2026-10-01T18:00:00Z"})
        self.i.call("exam.settle", {"exam_id": "E1"})
        self.assertEqual("monitoring_only", self.i.data("exam", "E1")["settlement"])

    def test_exam_official_points_self_assessment_and_equivalence_countersign(self):
        aid = self.i.exam_bank(); self.i.start_exam(aid, "final")
        checks = self.i.submit_exam(); checks[0].update(judgment="equivalent", rationale="The alternate lemma proves the same missing implication.")
        self.i.call("exam.grade", {"exam_id": "E1", "review_id": "exam-review", "point_verdicts": checks})
        exam = self.i.data("exam", "E1"); self.assertEqual("flagged", exam["status"]); self.assertIsNone(exam["passed"])
        point = checks[0]["point_id"]
        self.rejected("UNBOUND_DECISION", "exam.flag.confirm", {"exam_id": "E1", "point_id": point, "flag_sha256": learning.digest(exam["flags"][point]), "decision": "accept", "explanation": "Discussed the alternate lemma."}, "I do not accept.")
        self.i.call("exam.flag.confirm", {"exam_id": "E1", "point_id": point, "flag_sha256": learning.digest(exam["flags"][point]), "decision": "accept", "explanation": "Discussed why the lemma supplies the implication."}, "accept")
        self.i.call("exam.grade", {"exam_id": "E1", "review_id": "exam-review", "point_verdicts": checks, "optimization_feedback": ["A shorter argument is available; no scoring effect."]})
        self.assertTrue(self.i.data("exam", "E1")["passed"])
        self.assertEqual(3, len(self.i.data("exam_bank", "BANK")["used_papers"]))
        self.i.call("exam.settle", {"exam_id": "E1"}); self.assertEqual("settled", self.i.data("exam", "E1")["settlement"])

    def test_exam_solution_help_keeps_score_but_cannot_pass_independently(self):
        aid = self.i.exam_bank(); selected = self.i.start_exam(aid)
        self.i.call("exam.reminder", {"exam_id": "E1", "problem_id": selected["problem_ids"][0], "level": "solution", "content": "Requested solution discussion.", "student_request": {"role": "student", "source": "actual synthetic student turn", "text": "solution"}})
        checks = self.i.submit_exam(); self.i.call("exam.grade", {"exam_id": "E1", "review_id": "R", "point_verdicts": checks})
        exam = self.i.data("exam", "E1"); self.assertGreater(exam["score"], exam["pass_score"]); self.assertFalse(exam["passed"])

    def test_exam_parameter_snapshot_process_weight_error_recovery_and_no_review_override(self):
        aid = self.i.exam_bank()
        self.i.call("student.update", {"id": "current", "declarations": {"exam_parameters": {"pass_percent": {"final": 100}, "review_units": 0, "time_multipliers": {"final": 2}}}}, "Use these exam parameters.")
        selected = self.i.start_exam(aid, "final")
        self.assertEqual(20*len(selected["problem_ids"]), selected["duration_minutes"])
        checks = self.i.submit_exam(); checks[0].update(judgment="miss", rationale="The actual answer omits the required condition.")
        self.i.call("exam.grade", {"exam_id": "E1", "review_id": "R", "point_verdicts": checks})
        exam = self.i.data("exam", "E1"); point = checks[0]["point_id"]
        self.i.call("exam.flag.confirm", {"exam_id": "E1", "point_id": point, "flag_sha256": learning.digest(exam["flags"][point]), "decision": "reject", "explanation": "The missing condition earns no point."}, "reject")
        self.i.call("exam.grade", {"exam_id": "E1", "review_id": "R", "point_verdicts": checks})
        self.rejected("EXAM_ERRORS_UNRECOVERED", "exam.settle", {"exam_id": "E1"})
        problem = next(x["problem_id"] for x in self.i.data("review", "R")["ratings"] if x["verdict"] == "incorrect")
        self.i.call("exam.recover_mistakes", {"exam_id": "E1", "roots": [{"problem_id": problem, "mistake_id": "M-exam", "knowledge_key": "N1 condition", "root_cause": "Omitted the defining condition."}]})
        self.i.call("exam.settle", {"exam_id": "E1"})
        exam = self.i.data("exam", "E1")
        self.assertFalse(exam["passed"]); self.assertEqual("retake_ready", exam["settlement"])
        self.assertAlmostEqual(exam["paper_percent"]*.7+80*.3, exam["overall_percent"])
        self.assertEqual("active", self.i.data("mistake", "M-exam")["status"])

    def test_exam_scope_and_pool_are_not_caller_selected_or_reused(self):
        aid = self.i.exam_bank("progress")
        self.i.call("exam_bank.freeze", {"bank_id": "BANK", "group_id": "G", "cycle": 1, "as_of": "2026-09-30T12:00:00Z"})
        self.i.call("group.keystones.configure", {"id": "G", "container_mode": "progress", "keystone_ids": ["N1", "N2"], "reason": "A second required milestone."}, "Confirm expanded scope.")
        self.rejected("EXAM_PROGRESS_GATE", "exam.select", {"selection_id": "bad", "bank_id": "BANK", "group_id": "G", "exam_type": "final", "cycle": 1, "seed": "public", "as_of": "2026-09-30T12:00:00Z"})
        self.rejected("MISSING_FIELD", "exam.create", {"exam_id": "old-textbook-pool", "activity_id": aid, "problem_ids": ["q1"], "criterion_id": "rubric-v1", "started_at": "2026-09-30T18:00:00Z"})
        bank = self.i.data("exam_bank", "BANK"); assessment = next(pid for pid, q in bank["problems"].items() if bank["papers"][q["paper_id"]]["pool"] == "assessment")
        q = bank["problems"][assessment]
        self.rejected("ASSESSMENT_ISOLATION", "problem.add", {"activity_id": aid, "problem_id": "leak", "origin": "source", "text": q["source_excerpt"], "page_id": q["page_id"], "source_excerpt": q["source_excerpt"], "locator": q["locator"], "bank_id": "BANK", "bank_problem_id": assessment})

    def test_mutable_read_dependency_is_version_checked(self):
        aid, bids = self.i.lesson(); self.i.ready()
        request = self.i.request("ticket.issue", {"ticket_id": "t", "session_id": "s1", "block_id": bids[0], "body_sha256": self.i.data("block", bids[0])["body_sha256"]}, "继续")
        del request["expected"]["session/s1"]
        with self.assertRaises(DomainError) as exc: learning.plan(self.i.state, request)
        self.assertEqual("STALE_OBJECT", exc.exception.code)

    def test_real_journal_replays_the_durable_comprehension_and_original_assets(self):
        with tempfile.TemporaryDirectory() as path:
            journal = Journal(path); i = Instance(journal)
            aid, bids = i.lesson(); i.ready(); i.ticket(bids[0]); i.present(bids[0]); i.answer(bids[0])
            replay = Journal(path).read_state()
            self.assertEqual("feeling", get(replay,"cursor",aid)["waiting_for"])
            self.assertEqual("correct", get(replay,"cursor",aid)["judgement"]["verdict"])
            self.assertEqual("My own defining condition.",get(replay,"block",bids[0])["responses"][0]["answer"])
            self.assertTrue(journal.validate()["ok"])


if __name__ == "__main__":
    unittest.main()
