"""Semantic migration and transport failures, using synthetic legacy data."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from t2ag_next import migration as m
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, put


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "legacy"
        self.source.mkdir()
        self.package = self.root / "package"
        self.destination = self.root / "new"
        self.base = "main/40_course/C1"
        self.write(self.base + "/course.md", "---\ncourse_id: C1\nname: Sample\ncourse_type: mastery\nlearning_mode: textbook\n---\n")
        self.write(self.base + "/progress.md", """---
course_id: C1
lifecycle_status: ongoing
current_activity: lesson
current_activity_id: lesson02
activity_position: in_activity
current_checkpoint: none
next_action_kind: confirm_close
next_activity_type: lesson
next_activity_id: lesson02
---
## 当前进度
- **精确停顿点**：已讲完约定范围，待展示复盘后的明确结课确认。
- **下一步计划**：confirm_close lesson:lesson02。
## 当前节点 checkpoints
| checkpoint_id | 状态 |
|---|---|
| C1-P032-N06 | confirmed |
""")
        self.write(self.base + "/activity_ledger.md", """---
course_id: C1
---
## Current index
| activity_type | activity_id | state | binding_status | last_event_id |
|---|---|---|---|---|
| lesson | lesson02 | pending_close | bound | ALE-0002 |
## History
Old consumed permission retained, never made active.
""")
        self.write(self.base + "/lessons/lesson02/lesson02.md", "---\nlesson_id: lesson02\n---\nOriginal lesson evidence.\n")
        self.write(self.base + "/lessons/lesson02/closeout/learner-review.md", "# Review\nOriginal review body; not yet confirmed.\n")
        self.write(self.base + "/lessons/lesson02/preparation/old.json", '{"scan":"historically_complete","permission":"consumed"}')
        self.write(self.base + "/question_bank.md", "## Q-001\nStudent's original question\nStatus: open\n")
        self.write(".uploads/awaiting.bin", b"\x00\xffnot a cache")
        self.write("empty", b"")
        self.write(".venv/ignored", b"runtime is inventoried, not copied")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative, data):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        return path

    def export(self):
        return m.export_legacy(self.source, self.package)

    def test_domain_history_separates_attempt_review_and_system_issue(self):
        exercise=self.base+"/exercises/exercise01"
        self.write(exercise+"/problems.md", "---\nsource_order: [exercise01-Q001]\nteaching_sequence: [exercise01-Q001]\n---\n## exercise01-Q001\n- 题面：Compute.\n- 状态：closed\n")
        self.write(exercise+"/attempts/AT0001/attempt.md", "---\nattempt_id: AT0001\nproblem_ids: [exercise01-Q001]\n---\n## exercise01-Q001\nStudent original answer.\n")
        self.write(exercise+"/attempts/AT0001/answer.png", b"original image bytes")
        self.write(exercise+"/reviews/RV0001.md", "---\nattempt_id: AT0001\nstatus: amended\n---\n## exercise01-Q001\n- 结果：partial\nTeacher feedback, no replacement of answer.\n")
        self.write(self.base+"/mistake_bank.md", "### M-0001\n- 状态：maintenance\n- 知识点键：C1/concept\n- 来源：exercise01\n- 当前周期：2\n- 下次允许复测：2026-10-03\n")
        self.write("main/00_core/t2ag_problemlog.md", "## P-0001\n- closure: open\n- occurrence_count: 3\nSystem failure, not student's knowledge mistake.\n")
        result=self.import_(); state=Journal(self.destination).read_state()["objects"]
        attempt=state["attempt/C1/exercise01/AT0001"]["data"]
        review=state["review/C1/exercise01/RV0001"]["data"]
        self.assertIn("Student original answer",attempt["answers"][0]["text"])
        self.assertEqual(Journal(self.destination).read_blob(attempt["blob_refs"][0]["sha256"]), b"original image bytes")
        self.assertEqual(review["attempt_id"],"C1/exercise01/AT0001")
        self.assertEqual(review["ratings"][0]["legacy_verdict"],"partial")
        self.assertIsNone(review["ratings"][0]["independent"])
        self.assertTrue(review["migration_requires_reconciliation"])
        self.assertTrue(state["exercise/C1/exercise01"]["data"]["migration_requires_reconciliation"])
        self.assertEqual(state["exercise/C1/exercise01"]["data"]["assistance_status"],"unmapped_legacy_evidence_not_no_help")
        self.assertEqual(state["mistake/C1/M-0001"]["data"]["status"],"maintenance")
        self.assertEqual(state["issue/P-0001"]["data"]["legacy_occurrence_count"],"3")
        records=m.migration_history(self.destination,"review","C1")["records"]
        self.assertEqual(len(records),1)
        self.assertEqual(result["coverage"]["data_classes"]["D04"]["objects"],3)

    def test_profile_group_reading_engagement_skin_and_pending_cloud_preserved(self):
        self.write("main/10_student/profile/profile.md", "---\nexercise_hint_gate: enabled\nteaching_language: zh-CN\n---\nPrivate preferences.\n")
        self.write("main/20_teacher/T001.md","# Teacher\nOriginal template")
        self.write("main/20_teacher/overlay.md","| 课程代码 | 教师模板 |\n|---|---|\n| C1 | `main/20_teacher/T001.md` |\n")
        self.write("main/10_student/activities/reading/AR-0003_Book.md","---\nrecord_status: paused\ntitle: Read book\n---\n### 2026-09-30 Note\nOne observation.")
        self.write("main/10_student/engagements/EG-0004_Vocab/engagement.md","---\ngovernance: internal\nstatus: active\nlinked_courses: [C1]\n---\n")
        self.write("main/10_student/engagements/EG-0004_Vocab/vocab.jsonl",'{"id":"word1","status":"settled"}\n')
        self.write("main/30_group/G01/plan.md","---\nstatus: active\ncourse_members: [C1]\ncontainer_mode: schedule\n---\nCurrent group.")
        self.write("main/30_group/G01/calendar.md","---\ncycle: 3-1-3\n---\nOriginal schedule.")
        self.write("main/30_group/G01/bindings/R001_C1.md","---\ncourse_id: C1\nbinding_status: idle\nexecution_mode: flexible\n---\n")
        self.write("main/80_interface/skin.yaml","active: SK001\nregistry.SK001: default\n")
        self.write("main/80_interface/default/skin.yaml","name: My skin\nwelcome_msg: Welcome\nart_file: art.txt\n")
        self.write("main/80_interface/default/art.txt","Display only")
        self.write("cloud/cloud_sync_state.md","- cloud_bridge_status: paused\n- current_base_state_id: OLD\n")
        self.write("cloud/outbox/CD-0001.md","---\nstatus: ready_to_send\n---\nNever send on import.")
        self.import_(); state=Journal(self.destination).read_state()["objects"]
        self.assertEqual(state["student/current"]["data"]["exercise_hint_gate"],"enabled")
        self.assertEqual(state["course/C1"]["data"]["teacher_id"],"T001")
        self.assertEqual(state["reading/AR-0003"]["data"]["status"],"paused")
        self.assertEqual(state["engagement/EG-0004"]["data"]["domain_records"]["vocab.jsonl"]["rows"][0]["value"]["id"],"word1")
        self.assertEqual(state["group/G01"]["data"]["members"],["C1"])
        self.assertEqual(state["binding/R001"]["data"]["status"],"idle")
        self.assertEqual(state["student/current"]["data"]["skin_id"],"SK001")
        self.assertEqual(state["legacy_cloud/current"]["data"]["status"],"paused")
        self.assertFalse(state["legacy_cloud_item/CD-0001"]["data"]["executable"])
        self.assertNotIn("bridge/current",state)

    def test_backups_and_templates_do_not_create_domain_facts(self):
        refl="#### REFL-C1-0001\n- 感想：Original student words.\n"
        self.write("main/10_student/profile/course_reflections.md",refl)
        self.write(".activity_txn/old/backup/main/10_student/profile/course_reflections.md",refl)
        self.write(".activity_txn/old/staging/main/10_student/profile/course_reflections.md",refl)
        self.write(self.base+"/_exam/exam_ledger.md","| 字段 | 值 |\n|---|---|\n| 考核债状态 | `open` |\n```text\n### EX-0001\n- passed: true\n```\n")
        self.write(self.base+"/_exam/index.md","| 卷ID | 状态 |\n|---|---|\n")
        self.import_(); state=Journal(self.destination).read_state()["objects"]
        self.assertEqual(len(m.migration_history(self.destination,"reflection")["records"]),1)
        self.assertEqual(state["exam_debt/C1"]["data"]["status"],"open")
        self.assertTrue(state["exam_bank/C1/legacy"]["data"]["legacy_empty_pool"])
        self.assertFalse(any(e["kind"]=="exam" for e in state.values()))
        self.assertIn("legacy_file/.activity_txn/old/backup/main/10_student/profile/course_reflections.md",state)

    def test_verified_page_identity_is_preserved_without_reviving_scan(self):
        source=b"Synthetic source bytes"; render=b"Synthetic render bytes"
        source_sha=hashlib.sha256(source).hexdigest(); render_sha=hashlib.sha256(render).hexdigest()
        content="# Page 1\n\nVerified statement.\n"; body_sha=hashlib.sha256(content.encode()).hexdigest()
        self.write(self.base+"/book/primary/source.pdf",source)
        self.write(self.base+"/book/.cache/page_1.png",render)
        page=self.base+"/book/primary/source_assets/DOC/pages/page_1.md"
        self.write(page,f"---\nasset_id: DOC-P0001\nsource_document_sha256: {source_sha}\nverified_text_sha256: {body_sha}\nrender_sha256: {render_sha}\nverification_status: verified\nprinted_page_label: 1\n---\n{content}")
        self.import_(); state=Journal(self.destination).read_state()["objects"]
        p=state["page/DOC-P0001"]["data"]
        self.assertEqual(p["verification"]["status"],"verified")
        self.assertEqual(p["verified_text"],content)
        self.assertEqual(p["render_bytes"],len(render))
        self.assertFalse(p["current_session_consumed"])
        self.assertEqual(state["page_head/C1/"+source_sha+"/1"]["data"]["page_id"],"DOC-P0001")
        self.assertFalse(any(e["kind"] in {"scan","ticket","session"} for e in state.values()))

    def test_optional_pdf_backend_measures_physical_pages_not_prepared_count(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("Optional PDF dependency unavailable in this interpreter")
        document=pymupdf.open()
        for _ in range(3): document.new_page()
        raw=document.tobytes(); document.close()
        self.write(self.base+"/book/primary/real.pdf",raw)
        self.write(self.base+"/book/primary/source_assets/D/manifest.json",'{"available_page_count":999}')
        self.import_(); source=m.migration_history(self.destination,"source")["records"][0]["data"]
        self.assertEqual(source["page_count"],3)
        self.assertEqual(source["physical_metadata"]["tool_version"],pymupdf.VersionBind)
        self.assertEqual(source["physical_metadata"]["source_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertFalse(source["physical_metadata"]["current_session_consumed"])

    def test_multiple_page_versions_do_not_select_arbitrary_head(self):
        source=b"source"; render=b"render"; source_sha=hashlib.sha256(source).hexdigest(); render_sha=hashlib.sha256(render).hexdigest()
        self.write(self.base+"/book/source.pdf",source); self.write(self.base+"/book/.cache/page.png",render)
        for i in (1,2):
            content=f"# Page 1\nVersion {i}.\n"
            self.write(self.base+f"/book/primary/source_assets/D{i}/pages/page_1.md",f"---\nasset_id: D{i}-P1\nsource_document_sha256: {source_sha}\nverified_text_sha256: {hashlib.sha256(content.encode()).hexdigest()}\nrender_sha256: {render_sha}\nverification_status: verified\n---\n{content}")
        self.import_(); state=Journal(self.destination).read_state()["objects"]
        self.assertNotIn("page_head/C1/"+source_sha+"/1",state)
        for i in (1,2): self.assertIn("multiple_imported_page_versions_no_current_authority",state[f"page/D{i}-P1"]["data"]["uncertainties"])

    def test_same_snapshot_new_mapper_requires_new_target_without_overwriting(self):
        self.import_()
        log=self.destination/"transactions.jsonl"; before=log.read_bytes()
        changed={**m._mapper_identity(),"mapping_id":"new-mapper-or-new-pdf-backend"}
        with patch.object(m,"_mapper_identity",return_value=changed):
            self.error("MAPPER_CHANGED",lambda:m.import_package(self.package,self.destination))
        self.assertEqual(log.read_bytes(),before)
        self.assertTrue(m.import_package(self.package,self.destination)["replayed"])

    def test_source_mismatch_stays_named_unknown_in_new_consumer(self):
        self.write(self.base+"/book/primary/source_assets/DOC/pages/page_1.md","---\nasset_id: DOC-P0001\nsource_document_sha256: missing\nverified_text_sha256: wrong\nverification_status: verified\n---\nText.\n")
        self.import_(); p=m.migration_history(self.destination,"page")["records"][0]["data"]
        self.assertEqual(p["verification"]["status"],"unresolved")
        self.assertIn("page_source_identity_missing",p["uncertainties"])
        self.assertIn("verified_text_hash_mismatch",p["uncertainties"])

    def test_external_identity_registry_and_rules_have_consumers_not_fake_gates(self):
        self.write("main/10_student/engagements/EG-0001/external_refs.json",json.dumps({"owner_id":"EG-0001","references":[{"reference_id":"r1","peer_system":"peer","peer_relative_path":"facts.csv","usage_rule":"copy_on_use"}]}))
        self.write("main/70_tools/artifact_registry.json",json.dumps({"artifacts":[{"artifact_id":"C1_BODY","canonical_path":self.base+"/course.md","redirects":["old/course.md"]}]}))
        self.write("main/50_playbook/rule.md","enforcement: check=old.check\n# Old rule\nHistorical requirement.")
        self.import_(); state=Journal(self.destination).read_state()["objects"]
        self.assertEqual(state["external/EG-0001/r1"]["data"]["identity"],{"peer_system":"peer","peer_relative_path":"facts.csv"})
        self.assertFalse(state["external/EG-0001/r1"]["data"]["peer_accessed"])
        self.assertIn("course/C1",state["artifact_identity/C1_BODY"]["data"]["target_objects"])
        self.assertFalse(state["rule_contract/rule"]["data"]["machine_enforcement_verified"])
        self.assertEqual(m.migration_history(self.destination,"rule_contract")["count"],1)

    def import_(self):
        self.export()
        return m.import_package(self.package, self.destination)

    def error(self, code, callable_):
        with self.assertRaises(DomainError) as caught:
            callable_()
        self.assertEqual(caught.exception.code, code)

    def rewrite_manifest(self, transform):
        path = self.package / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        transform(manifest)
        manifest["snapshot_id"] = m._digest({k: manifest[k] for k in ("schema", "source_namespace", "files", "exclusions")})
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_exact_bytes_empty_large_and_pending_input_preserved(self):
        original = bytes(range(256)) * 10000
        self.write(self.base + "/book/source.pdf", original)
        result = self.export()
        verified = m.verify_package(self.package)
        manifest = verified["manifest"]
        self.assertEqual((self.package / "originals" / self.base / "book/source.pdf").read_bytes(), original)
        self.assertEqual(result["files"], verified["files"])
        pending = next(r for r in manifest["files"] if r["path"] == ".uploads/awaiting.bin")
        self.assertEqual(pending["classification"], "recovery_or_pending_input")
        self.assertTrue(any(r["path"] == ".venv" for r in manifest["exclusions"]))
        self.assertFalse((self.package / "originals/.venv").exists())

    def test_source_drift_rejects_without_publishing(self):
        def alter(point, _context):
            if point == "before_source_recheck":
                self.write("empty", b"changed by another classroom")
        with patch.object(m, "_fault", alter):
            self.error("SOURCE_DRIFT", self.export)
        self.assertFalse(self.package.exists())
        self.assertEqual((self.source / "empty").read_bytes(), b"changed by another classroom")

    def test_added_file_and_removed_source_detected(self):
        def add(point, _context):
            if point == "before_source_recheck":
                self.write("newer.txt", "new fact")
        with patch.object(m, "_fault", add):
            self.error("SOURCE_DRIFT", self.export)

    def test_overlapping_roots_and_existing_target_do_not_mutate(self):
        self.error("OVERLAPPING_ROOTS", lambda: m.export_legacy(self.source, self.source / "package"))
        self.package.mkdir()
        (self.package / "precious").write_bytes(b"keep")
        self.error("DESTINATION_NOT_EMPTY", self.export)
        self.assertEqual(list(p.name for p in self.package.iterdir()), ["precious"])

    def test_traversal_case_collision_and_tampered_identity(self):
        self.export()
        self.rewrite_manifest(lambda manifest: manifest["files"][0].update(path="../outside"))
        self.error("UNSAFE_PATH", lambda: m.verify_package(self.package))

    def test_duplicate_path_rejected_even_with_new_manifest_hash(self):
        self.export()
        self.rewrite_manifest(lambda manifest: manifest["files"].append(dict(manifest["files"][0])))
        self.error("PATH_COLLISION", lambda: m.verify_package(self.package))

    def test_byte_tamper_and_uninventoried_extra_rejected(self):
        self.export()
        (self.package / "originals/empty").write_bytes(b"tampered")
        self.error("PACKAGE_BYTES_CHANGED", lambda: m.verify_package(self.package))
        (self.package / "originals/empty").write_bytes(b"")
        (self.package / "originals/extra").write_bytes(b"unmanifested")
        self.error("UNEXPECTED_PACKAGE_FILE", lambda: m.verify_package(self.package))

    def test_linked_original_is_never_followed(self):
        self.export()
        original = self.package / "originals/empty"
        original.unlink()
        outside = self.root / "outside"
        outside.write_bytes(b"")
        try:
            original.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"Host does not allow test symlink: {exc}")
        self.error("UNSAFE_PATH", lambda: m.verify_package(self.package))

    def test_semantic_current_and_raw_evidence_consumer_no_permission_revival(self):
        result = self.import_()
        journal = Journal(self.destination)
        state = journal.read_state()["objects"]
        self.assertEqual(state["course/C1"]["data"]["current_activity_id"], "C1/lesson02")
        self.assertEqual(state["activity/C1/lesson02"]["data"]["status"], "pending_close")
        cursor = state["cursor/C1/lesson02"]["data"]
        self.assertEqual(cursor["next_action"]["kind"], "confirm_close")
        self.assertIsNone(cursor["block_id"])
        self.assertIn("Original review body", cursor["pending_body"])
        self.assertIsNone(cursor["current_session_scan"])
        self.assertFalse(any(e["kind"] in {"ticket", "scan", "session"} for e in state.values()))
        evidence = state["legacy_file/.uploads/awaiting.bin"]["data"]
        self.assertEqual(journal.read_blob(evidence["blob_sha256"]), b"\x00\xffnot a cache")
        report = m.migration_report(self.destination, self.source)
        self.assertEqual(report["cursors"][0]["data"]["position"], cursor["position"])
        self.assertTrue(report["rollback"]["may_return_to_unchanged_source"])
        self.assertFalse(result["coverage"]["cutover_ready"])

    def test_narrative_conflict_keeps_both_sources(self):
        path = self.source / self.base / "progress.md"
        raw = path.read_text(encoding="utf-8")
        narrative = "Current scaling stage pending; previous S03 confirmed. " * 4
        path.write_text(raw.replace("activity_position: in_activity", "activity_position: " + narrative)
                       .replace("confirm_close lesson:lesson02。", "S03 开讲，从核标题开始。"), encoding="utf-8")
        self.import_()
        cursor = Journal(self.destination).read_state()["objects"]["cursor/C1/lesson02"]["data"]
        self.assertEqual(cursor["waiting_for"], "resolve_legacy_conflict")
        self.assertEqual(cursor["legacy_activity_position"], narrative.strip())
        self.assertIn("S03", cursor["legacy_body_next_action"])
        self.assertTrue(cursor["uncertainties"])

    def test_duplicate_course_namespace_and_missing_activity_not_guessed(self):
        self.write("40_course/C1/course.md", "---\ncourse_id: C1\n---\n")
        self.export()
        self.error("DUPLICATE_LEGACY_ID", lambda: m.import_package(self.package, self.destination))
        self.assertFalse(self.destination.exists())

    def test_same_package_is_idempotent_and_other_package_refused(self):
        self.import_()
        before = (self.destination / "transactions.jsonl").read_bytes()
        self.assertTrue(m.import_package(self.package, self.destination)["replayed"])
        self.assertEqual((self.destination / "transactions.jsonl").read_bytes(), before)
        self.write("empty", "new source snapshot")
        other = self.root / "package2"
        m.export_legacy(self.source, other)
        self.error("DESTINATION_NOT_EMPTY", lambda: m.import_package(other, self.destination))
        self.assertEqual((self.destination / "transactions.jsonl").read_bytes(), before)

    def test_unrelated_nonempty_destination_unchanged(self):
        self.export()
        self.destination.mkdir()
        (self.destination / "personal.txt").write_bytes(b"precious")
        self.error("DESTINATION_NOT_EMPTY", lambda: m.import_package(self.package, self.destination))
        self.assertEqual([p.name for p in self.destination.iterdir()], ["personal.txt"])

    def test_mid_import_failure_never_publishes_partial_instance(self):
        self.export()
        def fail(point, context):
            if point == "after_import_commit":
                raise RuntimeError("crash before instance publication")
        with patch.object(m, "_fault", fail):
            with self.assertRaisesRegex(RuntimeError, "crash"):
                m.import_package(self.package, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertTrue(m.import_package(self.package, self.destination)["ok"])

    def test_differential_rollback_blocks_on_either_side_advancing(self):
        self.import_()
        journal = Journal(self.destination)
        journal.apply({"request_id": "new-fact", "action": "test.actual_new_fact", "payload": {},
                       "actor": {"role": "student", "source": "fixture", "text": "new answer"}, "expected": {}},
                      lambda _s, _r: [put("attempt", "new", {"raw": "new answer"})])
        self.write("empty", b"legacy progressed too")
        report = m.migration_report(self.destination, self.source)["rollback"]
        self.assertFalse(report["may_return_to_unchanged_source"])
        self.assertEqual(report["new_instance_changed_objects"], ["attempt/new"])
        self.assertIn("empty", report["source_difference"]["changed"])
        self.assertTrue(report["requires_reconciliation"])
        self.assertFalse(report["route_changed"])
        self.assertFalse(m.migration_report(self.destination)["rollback"]["may_return_to_unchanged_source"])

    def test_checkpoint_owner_comes_from_content_group_not_current_activity(self):
        self.write(self.base + "/activity_map.md", "| content_group_id | lesson_ids | exercise_ids |\n|---|---|---|\n| C1-G | lesson02 | — |\n")
        progress = self.source / self.base / "progress.md"
        progress.write_text(progress.read_text(encoding="utf-8").replace(
            "| checkpoint_id | 状态 |\n|---|---|\n| C1-P032-N06 | confirmed |",
            "| checkpoint_id | parent_node | 状态 |\n|---|---|---|\n| C1-P032-N06 | C1-G-N01 | confirmed |"), encoding="utf-8")
        self.import_()
        cp = Journal(self.destination).read_state()["objects"]["checkpoint/C1-P032-N06"]["data"]
        self.assertEqual(cp["activity_id"], "C1/lesson02")
        self.assertEqual(cp["identity_mapping"], "content_group_authority")

    def test_exercise_body_filename_and_fenced_question_templates(self):
        ledger = self.source / self.base / "activity_ledger.md"
        ledger.write_text(ledger.read_text(encoding="utf-8").replace("## History", "| exercise | exercise01 | completed | bound | ALE-0003 |\n## History"), encoding="utf-8")
        self.write(self.base + "/exercises/exercise01/exercise.md", "---\nexercise_id: exercise01\n---\nOriginal exercise.")
        self.write(self.base + "/question_bank.md", "```markdown\n### Q-999\n- 问题：template\n```\n### Q-001｜Actual\n- 问题：Real question\n- 来源：lesson02\n- 状态：open\n```python\nprint('student original')\n```\n")
        self.import_()
        objects = Journal(self.destination).read_state()["objects"]
        self.assertEqual(objects["activity/C1/exercise01"]["data"]["uncertainties"], [])
        self.assertIn("question/C1/Q-001", objects)
        self.assertNotIn("question/C1/Q-999", objects)
        self.assertIn("print('student original')", objects["question/C1/Q-001"]["data"]["original_body"])

    def test_last_question_stops_before_template_and_keeps_multiline_text(self):
        self.write(self.base + "/question_bank.md", "### Q-026｜Actual\n- 问题：First line;\n  second line of the same question.\n- 来源：lesson02\n- 状态：answered\n- 回答摘要：Actual historical answer.\n## 条目模板\n### Q-XXXX｜Template\n- 问题：\n- 状态：open / answered / closed\n")
        self.import_()
        q = Journal(self.destination).read_state()["objects"]["question/C1/Q-026"]["data"]
        self.assertEqual(q["status"], "answered")
        self.assertEqual(q["text"], "First line;\n  second line of the same question.")
        self.assertNotIn("条目模板", q["original_body"])
        self.assertEqual(q["legacy_fields"]["回答摘要"], "Actual historical answer.")


if __name__ == "__main__":
    unittest.main()
