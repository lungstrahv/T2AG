#!/usr/bin/env python3
"""T2AG 0.2.1 closeout regression and adversarial tests."""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import migrate_021
import migrate_021_activity_records as activity_migration
import migration_txn_021 as migration_txn
import sync_lite
import t2ag_doctor as doctor
import t2ag_reading_bridge as bridge
from contracts.reading_bridge_v1.validator import (
    ContractError,
    canonical_json_bytes,
    load_json_strict,
    semantic_sha256,
    validate_document,
)


TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
CONTRACTS = TOOLS / "contracts/reading_bridge_v1"


def baseline_git_repo(commit: str) -> Path:
    """Resolve a frozen baseline from the current original or Lite's sibling Main."""
    candidates = (REPO, REPO.parent / "t2ag", REPO.parent / "t2ag-skeleton")
    for candidate in candidates:
        if not (candidate / ".git").exists():
            continue
        result = subprocess.run(
            ["git", "-C", str(candidate), "cat-file", "-e", f"{commit}^{{commit}}"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return candidate
    raise AssertionError(f"frozen baseline commit is not locally resolvable: {commit}")


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="\n")


def ar_text(activity_id: str) -> str:
    return (
        "---\ntype: activity_record\nactivity_kind: reading\n"
        f"activity_record_id: {activity_id}\ntitle: fixture\nrecord_status: recording\n"
        "created_at: 2026-08-04\n---\n# fixture\n"
    )


def namespace(**values: object) -> argparse.Namespace:
    return argparse.Namespace(**values)


def make_contribution(
    event_id: str,
    *,
    activity_id: str = "AR-0001",
    question: str = "这个候选可支持什么？",
    receipt_note_uri: str | None = "reading://note/B001/B001-CH00-P001-N01",
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "reading.t2ag_contribution.v1",
        "event_id": event_id,
        "generated_at": "2026-08-04T00:00:00Z",
        "producer": "reading_system",
        "semantic_sha256": "",
        "contribution_id": "",
        "target_activity_record_id": activity_id,
        "book_id": "B001",
        "source_reading_uri": "reading://note/B001/B001-CH00-P001-N01",
        "source_revision": "1" * 64,
        "knowledge_node_id": None,
        "question": question,
        "maturity": "candidate",
        "supports": ["短候选，不复制页记正文"],
        "limits": ["尚未进入知识网络"],
        "evidence_locator": {
            "source_uri": "reading://note/B001/B001-CH00-P001-N01",
            "source_path": "main/10_books/B001/pages/CH00/fixture.md",
            "source_id": "B001-CH00-P001-N01",
            "source_sha256": "2" * 64,
            "receipt_note_uri": receipt_note_uri,
        },
    }
    digest = semantic_sha256(value)
    value["semantic_sha256"] = digest
    value["contribution_id"] = "CON-" + digest
    return value


class ContractValidatorTests(unittest.TestCase):
    def test_all_schemas_use_supported_fail_closed_subset(self) -> None:
        for path in sorted(CONTRACTS.glob("*.schema.json")):
            schema = load_json_strict(path)
            self.assertIsInstance(schema, dict)
            with self.assertRaises(ContractError):
                validate_document({}, schema)

    def test_duplicate_key_non_finite_and_unknown_schema_keyword_fail(self) -> None:
        with self.assertRaises(ContractError):
            load_json_strict('{"x":1,"x":2}')
        with self.assertRaises(ContractError):
            load_json_strict('{"x":NaN}')
        schema = load_json_strict(CONTRACTS / "reading.t2ag_receipt.v1.schema.json")
        broken = copy.deepcopy(schema)
        broken["unevaluatedProperties"] = False
        with self.assertRaises(ContractError):
            validate_document({}, broken)

    def test_relative_path_escape_and_extra_field_fail(self) -> None:
        payload = make_contribution("EVT-CONTRACT-0001")
        schema = load_json_strict(CONTRACTS / "reading.t2ag_contribution.v1.schema.json")
        validate_document(payload, schema)
        for bad_path in ("../secret", "C:/secret", "//server/share", "file://secret", "a%2fb", "a\\b"):
            broken = copy.deepcopy(payload)
            broken["evidence_locator"]["source_path"] = bad_path
            with self.assertRaises(ContractError, msg=bad_path):
                validate_document(broken, schema)
        broken = copy.deepcopy(payload)
        broken["full_profile"] = "forbidden"
        with self.assertRaises(ContractError):
            validate_document(broken, schema)


class BridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="t2ag-021-bridge-")
        self.root = Path(self.temporary.name) / "t2ag"
        shutil.copytree(CONTRACTS, self.root / "main/70_tools/contracts/reading_bridge_v1")
        reading = self.root / "main/10_student/activities/reading"
        write(reading / "AR-0001_Fixture.md", ar_text("AR-0001"))
        write(reading / "AR-0002_Fixture.md", ar_text("AR-0002"))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def payload_file(self, name: str, payload: object) -> Path:
        path = self.root / "exchange" / name
        write(path, canonical_json_bytes(payload) + b"\n")
        return path

    def import_payload(self, payload: dict[str, object]) -> dict[str, object]:
        return bridge.contribution_import(namespace(root=str(self.root), file=str(self.payload_file("contribution.json", payload))))

    def test_empty_context_export_is_read_only_and_stable_semantically(self) -> None:
        before = {
            path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.root.rglob("*") if path.is_file()
        }
        first = bridge.context_export(namespace(root=str(self.root), activity="AR-0001", event_id="EVT-CONTEXT-0001", generated_at="2026-08-04T00:00:00Z"))
        second = bridge.context_export(namespace(root=str(self.root), activity="AR-0001", event_id="EVT-CONTEXT-0002", generated_at="2026-08-04T01:00:00Z"))
        self.assertIsNone(first["target_reading_uri"])
        self.assertEqual(first["export_id"], second["export_id"])
        after = {
            path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.root.rglob("*") if path.is_file()
        }
        self.assertEqual(before, after)

    def test_explicit_context_and_fourth_cue_rejection(self) -> None:
        source = {
            "schema": "t2ag.reading_context_source.v1",
            "activity_record_id": "AR-0001",
            "target_reading_uri": "reading://book/B001",
            "course_id": None,
            "confirmed_by": "student",
            "confirmed_at": "2026-08-04T00:00:00Z",
            "reading_intents": [{"source_id": "AR-0001", "source_path": "main/10_student/activities/reading/AR-0001_Fixture.md", "text": "观察边界"}],
            "questions_or_observation_cues": [],
        }
        context_file = self.root / "main/10_student/activities/reading/AR-0001.context.json"
        write(context_file, canonical_json_bytes(source) + b"\n")
        payload = bridge.context_export(namespace(root=str(self.root), activity="AR-0001", event_id="EVT-CONTEXT-0003", generated_at="2026-08-04T00:00:00Z"))
        self.assertEqual(payload["target_reading_uri"], "reading://book/B001")
        source["questions_or_observation_cues"] = [
            {"source_id": f"Q{index}", "source_path": "main/source.md", "text": "cue"}
            for index in range(4)
        ]
        write(context_file, canonical_json_bytes(source) + b"\n")
        with self.assertRaises(ContractError):
            bridge.context_export(namespace(root=str(self.root), activity="AR-0001", event_id="EVT-CONTEXT-0004", generated_at="2026-08-04T00:00:00Z"))

    def test_import_replay_conflict_new_event_and_failure_rollback(self) -> None:
        first = make_contribution("EVT-CONTRIB-0001")
        result = self.import_payload(first)
        self.assertEqual(result["result"], "imported")
        ledger = self.root / "main/10_student/activities/reading/AR-0001.contributions.json"
        original = ledger.read_bytes()
        original_mtime = ledger.stat().st_mtime_ns
        result = self.import_payload(first)
        self.assertEqual(result["result"], "already_processed")
        self.assertEqual(ledger.read_bytes(), original)
        self.assertEqual(ledger.stat().st_mtime_ns, original_mtime)

        same_object = copy.deepcopy(first)
        same_object["event_id"] = "EVT-CONTRIB-0002"
        same_object["generated_at"] = "2026-08-04T02:00:00Z"
        result = self.import_payload(same_object)
        self.assertEqual(result["result"], "already_present")

        conflict = make_contribution("EVT-CONTRIB-0001", question="conflict")
        before_conflict = ledger.read_bytes()
        with self.assertRaises(bridge.BridgeError):
            self.import_payload(conflict)
        self.assertEqual(ledger.read_bytes(), before_conflict)

        new_value = make_contribution("EVT-CONTRIB-0003", question="fault injection")
        before_fault = ledger.read_bytes()
        for point in ("before_replace", "after_replace"):
            os.environ["T2AG_BRIDGE_FAIL_AT"] = point
            try:
                with self.assertRaises(bridge.BridgeError):
                    self.import_payload(new_value)
            finally:
                os.environ.pop("T2AG_BRIDGE_FAIL_AT", None)
            self.assertEqual(ledger.read_bytes(), before_fault)

    def test_receipt_pending_replay_ack_and_missing_note_locator(self) -> None:
        contribution = make_contribution("EVT-CONTRIB-0100")
        self.import_payload(contribution)
        use_relative = "main/40_course/TEST1001/lessons/lesson01/lesson01.md"
        write(
            self.root / use_relative,
            f"used candidate {contribution['contribution_id']}\n",
        )
        arguments = namespace(
            root=str(self.root),
            activity="AR-0001",
            contribution_id=contribution["contribution_id"],
            receipt_id="RCP-ABCDEFGHIJKLMNOP",
            consumer_uri=f"t2ag://path/{use_relative}",
            used_at="2026-08-04T03:00:00Z",
            purpose="fixture actual use",
            generated_at="2026-08-04T03:00:00Z",
        )
        payload = bridge.receipt_prepare(arguments)
        ledger = self.root / "main/10_student/activities/reading/AR-0001.contributions.json"
        old_bytes, old_mtime = ledger.read_bytes(), ledger.stat().st_mtime_ns
        replay = bridge.receipt_prepare(arguments)
        self.assertEqual(payload, replay)
        self.assertEqual((ledger.read_bytes(), ledger.stat().st_mtime_ns), (old_bytes, old_mtime))
        pending = bridge.receipt_list_pending(namespace(root=str(self.root), activity=None))
        self.assertEqual([row["receipt_id"] for row in pending], ["RCP-ABCDEFGHIJKLMNOP"])

        response = {"receipt_id": payload["receipt_id"], "semantic_sha256": payload["semantic_sha256"], "result": "applied"}
        response_path = self.payload_file("response.json", response)
        result = bridge.receipt_ack(namespace(root=str(self.root), response_file=str(response_path)))
        self.assertEqual(result["result"], "acknowledged")
        acknowledged_bytes, acknowledged_mtime = ledger.read_bytes(), ledger.stat().st_mtime_ns
        result = bridge.receipt_ack(namespace(root=str(self.root), response_file=str(response_path)))
        self.assertEqual(result["result"], "already_acknowledged")
        self.assertEqual((ledger.read_bytes(), ledger.stat().st_mtime_ns), (acknowledged_bytes, acknowledged_mtime))

        missing = make_contribution("EVT-CONTRIB-0101", question="node only", receipt_note_uri=None)
        self.import_payload(missing)
        blocked = copy.copy(arguments)
        blocked.contribution_id = missing["contribution_id"]
        blocked.receipt_id = "RCP-QRSTUVWXYZABCDEF"
        before = ledger.read_bytes()
        with self.assertRaises(bridge.BridgeError):
            bridge.receipt_prepare(blocked)
        self.assertEqual(ledger.read_bytes(), before)

    def test_two_process_concurrent_import_does_not_lose_updates(self) -> None:
        files = [
            self.payload_file(f"concurrent-{index}.json", make_contribution(f"EVT-CONCURRENT-{index:04d}", question=f"q{index}"))
            for index in (1, 2)
        ]
        processes = [
            subprocess.Popen(
                [sys.executable, "-B", str(TOOLS / "t2ag_reading_bridge.py"), "--root", str(self.root), "contribution-import", "--file", str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for path in files
        ]
        outputs = [process.communicate(timeout=20) for process in processes]
        self.assertEqual([process.returncode for process in processes], [0, 0], outputs)
        ledger = load_json_strict(self.root / "main/10_student/activities/reading/AR-0001.contributions.json")
        self.assertEqual(len(ledger["contributions"]), 2)
        self.assertEqual(len(ledger["processed_events"]), 2)


class DoctorBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="t2ag-021-doctor-")
        self.root = Path(self.temporary.name)
        shutil.copytree(CONTRACTS, self.root / "main/70_tools/contracts/reading_bridge_v1")
        reading = self.root / "main/10_student/activities/reading"
        write(reading / "_README.md", "# fixture\n")
        write(reading / "AR-0001_Fixture.md", ar_text("AR-0001"))
        (self.root / "main/10_student/engagements").mkdir(parents=True)
        doctor.ROOT = self.root
        doctor.MAIN = self.root / "main"
        doctor.FLAVOR = "main"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_activity_check(self) -> list[str]:
        doctor.fails.clear(); doctor.warns.clear(); doctor.infos.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            doctor.check_engagements_and_activities()
        return list(doctor.fails)

    def test_root_deep_unknown_kind_duplicate_and_sidecar_impersonation_fail(self) -> None:
        cases: list[tuple[str, callable]] = [
            ("仍在根目录", lambda: write(self.root / "main/10_student/activities/AR-0002_Flat.md", ar_text("AR-0002"))),
            ("嵌套过深", lambda: write(self.root / "main/10_student/activities/reading/deep/AR-0002_Deep.md", ar_text("AR-0002"))),
            ("kind 未登记", lambda: write(self.root / "main/10_student/activities/arbitrary/AR-0002_Bad.md", ar_text("AR-0002"))),
            ("非法旁路文件", lambda: write(self.root / "main/10_student/activities/reading/AR-0001.fake.json", "{}\n")),
        ]
        for token, mutate in cases:
            with self.subTest(token=token):
                shutil.rmtree(self.root / "main/10_student/activities")
                reading = self.root / "main/10_student/activities/reading"
                write(reading / "AR-0001_Fixture.md", ar_text("AR-0001"))
                mutate()
                self.assertTrue(any(token in message for message in self.run_activity_check()), self.run_activity_check())

    def test_attempt_date_parser_and_gate_boundary(self) -> None:
        course = self.root / "main/40_course/TEST1001"
        unit = course / "exercises/U0001"
        write(unit / "exercise.md", "---\ntype: exercise\ncourse_id: TEST1001\nexercise_id: U0001\ncontent_group_ids: []\n---\n")
        write(unit / "problems.md", "---\ntype: exercise_problem_set\ncourse_id: TEST1001\nexercise_id: U0001\n---\n## U0001-Q001\n- 题面：test\n")
        (unit / "reviews").mkdir(parents=True)

        def errors(created: str, gate: str = "", assistance: str = "") -> list[str]:
            shutil.rmtree(unit / "attempts", ignore_errors=True)
            extra = (f"hint_gate: {gate}\n" if gate else "") + (f"assistance_level: {assistance}\n" if assistance else "")
            write(
                unit / "attempts/AT0001/attempt.md",
                "---\ntype: exercise_attempt\ncourse_id: TEST1001\nexercise_id: U0001\nattempt_id: AT0001\n"
                f"problem_ids: [U0001-Q001]\nmode: text\nstatus: submitted\ncreated: {created}\n{extra}---\n"
                "## 作答上下文\n- none\n## U0001-Q001\n- 作答：x\n",
            )
            doctor.fails.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                doctor.check_exercises({"TEST1001": (course, {})})
            return list(doctor.fails)

        for value in ("2026-08-01T00:00:00", "banana", "2026-8-1", "2026-02-30"):
            self.assertTrue(any("created 非法 ISO 日期" in message for message in errors(value)), value)
        self.assertFalse(any("提示闸门快照" in message for message in errors("2026-07-31")))
        self.assertTrue(any("缺提示闸门快照" in message for message in errors("2026-08-01")))
        self.assertFalse(any("created 非法" in message or "提示闸门" in message for message in errors("2026-08-01", "enabled", "none")))
        self.assertTrue(any("字段不成对" in message for message in errors("2026-07-31", "enabled", "")))


class MigrationTransactionTests(unittest.TestCase):
    def profile_fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, bytes]]:
        temporary = tempfile.TemporaryDirectory(prefix="t2ag-021-migration-")
        repo = Path(temporary.name) / "repo"
        contents = {
            "main/10_student/profile.md": (
                b"main/10_student/profile.md\nmain/10_student/profile.md\n"
                b"main/10_student/course_reflections.md\n"
                b"main/10_student/reasoning_patterns.md\n"
            ),
            "main/10_student/learning_path.md": b"10_student/profile.md\n",
            "main/10_student/course_reflections.md": b"../40_course/a\n../40_course/b\n../40_course/c\n",
            "main/10_student/reasoning_patterns.md": b"identity\n",
        }
        for relative, content in contents.items():
            write(repo / relative, content)
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "baseline"],
            check=True,
        )
        return temporary, repo, contents

    def test_profile_install_faults_rollback_and_second_run(self) -> None:
        for point in ("install:1", "install:2", "install:3", "install:4", "retire:1"):
            with self.subTest(point=point):
                temporary, repo, contents = self.profile_fixture()
                try:
                    os.environ["T2AG_MIGRATION_FAIL_AT"] = point
                    with self.assertRaises(migration_txn.MigrationTransactionError):
                        migrate_021.apply(repo)
                    for source, target in migrate_021.MOVES:
                        self.assertEqual((repo / source).read_bytes(), contents[source])
                        self.assertFalse((repo / target).exists())
                    self.assertFalse(migration_txn.transaction_root(repo, migrate_021.MIGRATION_ID).exists())
                finally:
                    os.environ.pop("T2AG_MIGRATION_FAIL_AT", None)
                    temporary.cleanup()

        temporary, repo, _contents = self.profile_fixture()
        try:
            self.assertEqual(migrate_021.apply(repo), 4)
            self.assertEqual(migrate_021.apply(repo), 0)
        finally:
            temporary.cleanup()

    def test_kill_then_interrupted_recovery_is_replayable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t2ag-021-kill-") as temporary:
            repo = Path(temporary) / "repo"
            write(repo / "source.txt", b"before\n")
            code_apply = (
                "import sys; from pathlib import Path; "
                f"sys.path.insert(0,{str(TOOLS)!r}); "
                "from migration_txn_021 import MoveOperation,apply_transaction; "
                "apply_transaction(Path(sys.argv[1]),'KILL-FIXTURE',(MoveOperation('source.txt','target.txt','identity',lambda b:b),))"
            )
            environment = os.environ.copy()
            environment["T2AG_MIGRATION_KILL_AT"] = "install:1"
            first = subprocess.run([sys.executable, "-B", "-c", code_apply, str(repo)], env=environment)
            self.assertEqual(first.returncode, 97)
            self.assertTrue(migration_txn.transaction_root(repo, "KILL-FIXTURE").exists())

            code_recover = (
                "import sys; from pathlib import Path; "
                f"sys.path.insert(0,{str(TOOLS)!r}); "
                "from migration_txn_021 import recover; recover(Path(sys.argv[1]),'KILL-FIXTURE')"
            )
            environment["T2AG_MIGRATION_KILL_AT"] = "rollback:1:source"
            interrupted = subprocess.run([sys.executable, "-B", "-c", code_recover, str(repo)], env=environment)
            self.assertEqual(interrupted.returncode, 97)
            os.environ.pop("T2AG_MIGRATION_KILL_AT", None)
            self.assertEqual(migration_txn.recover(repo, "KILL-FIXTURE"), "rolled_back")
            self.assertEqual((repo / "source.txt").read_bytes(), b"before\n")
            self.assertFalse((repo / "target.txt").exists())
            self.assertFalse(migration_txn.transaction_root(repo, "KILL-FIXTURE").exists())

    def test_dirty_collision_and_invalid_utf8_fail_without_partial_write(self) -> None:
        temporary, repo, contents = self.profile_fixture()
        try:
            write(repo / migrate_021.MOVES[0][0], contents[migrate_021.MOVES[0][0]] + b"dirty")
            with self.assertRaises(migration_txn.MigrationTransactionError):
                migrate_021.apply(repo)
            self.assertFalse(any((repo / target).exists() for _source, target in migrate_021.MOVES))
        finally:
            temporary.cleanup()

        with tempfile.TemporaryDirectory(prefix="t2ag-021-invalid-") as temporary_name:
            repo = Path(temporary_name)
            for source, _target in migrate_021.MOVES:
                write(repo / source, b"\xff")
            with self.assertRaises(migration_txn.MigrationTransactionError):
                migration_txn.apply_transaction(repo, migrate_021.MIGRATION_ID, migrate_021.operations("main"))
            self.assertFalse(any((repo / target).exists() for _source, target in migrate_021.MOVES))

    def test_profile_forward_oracle_matches_frozen_main_golden(self) -> None:
        target_kind = "skeleton" if REPO.name == "t2ag-skeleton" else "main"
        commit = migrate_021.BASELINES[target_kind]["commit"]
        for source, target in migrate_021.MOVES:
            raw = subprocess.check_output(
                ["git", "show", f"{commit}:{source}"], cwd=baseline_git_repo(commit)
            )
            transformed, counts, transform_id = migrate_021.apply_allowed_path_repairs(source, target, target_kind, raw)
            golden = migrate_021.GOLDEN[target_kind][source]
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest(), len(transformed), hashlib.sha256(transformed).hexdigest()), golden)
            self.assertTrue(transform_id)
            self.assertIsInstance(counts, dict)

    def test_activity_forward_oracle_matches_frozen_golden(self) -> None:
        if REPO.name == "t2ag-skeleton":
            raw = (
                b"---\ntype: activity_record\nactivity_record_id: AR-9999\n---\n"
                + activity_migration.SOURCE.encode("utf-8")
                + b"\n"
            )
            transformed = activity_migration.transform_activity_record(raw)
            self.assertEqual(transformed.count(b"activity_kind: reading\n"), 1)
            self.assertEqual(transformed.count(activity_migration.TARGET.encode("utf-8")), 1)
            self.assertNotIn(activity_migration.SOURCE.encode("utf-8"), transformed)
            return
        raw = subprocess.check_output(
            ["git", "show", f"{activity_migration.BASELINE_COMMIT}:{activity_migration.SOURCE}"],
            cwd=baseline_git_repo(activity_migration.BASELINE_COMMIT),
        )
        transformed = activity_migration.transform_activity_record(raw)
        self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (951, activity_migration.SOURCE_SHA256))
        self.assertEqual((len(transformed), hashlib.sha256(transformed).hexdigest()), (982, activity_migration.TARGET_SHA256))


class LiteTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="t2ag-021-lite-")
        self.workspace = Path(self.temporary.name)
        self.src = self.workspace / "t2ag"
        self.dst = self.workspace / "t2ag-lite"
        self.candidate = self.workspace / "candidate"
        self.rollback = self.workspace / "rollback"
        write(self.src / "main/a.txt", "source\n")
        write(self.src / ".venv/ignored.txt", "ignored\n")
        write(self.dst / "old.txt", "old\n")
        write(self.candidate / "main/a.txt", "candidate\n")

    def tearDown(self) -> None:
        os.environ.pop("T2AG_SYNC_LITE_FAIL_AT", None)
        self.temporary.cleanup()

    def test_source_manifest_is_exact_and_excludes_protected_noise(self) -> None:
        before = sync_lite.source_projection_manifest(self.src)
        self.assertIn("main/a.txt", before)
        self.assertFalse(any(".venv" in name for name in before))
        write(self.src / "main/a.txt", "changed\n")
        self.assertNotEqual(before, sync_lite.source_projection_manifest(self.src))

    def test_install_fault_restores_exact_old_lite(self) -> None:
        old = sync_lite.lite_content_manifest(self.dst)
        os.environ["T2AG_SYNC_LITE_FAIL_AT"] = "install_new:1"
        with self.assertRaises(RuntimeError):
            sync_lite.install_candidate(self.candidate, self.dst, self.rollback)
        self.assertEqual(sync_lite.lite_content_manifest(self.dst), old)

    def test_post_install_failure_can_restore_exact_old_lite(self) -> None:
        old = sync_lite.lite_content_manifest(self.dst)
        moved, installed = sync_lite.install_candidate(self.candidate, self.dst, self.rollback)
        self.assertNotEqual(sync_lite.lite_content_manifest(self.dst), old)
        sync_lite.restore_previous_lite(self.dst, self.rollback, installed, moved)
        self.assertEqual(sync_lite.lite_content_manifest(self.dst), old)


class LiteMainTransactionTests(unittest.TestCase):
    """main() path regressions for post-install fault recovery (V-021-001)."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="t2ag-021-lite-main-")
        self.workspace = Path(self.temporary.name)
        self.src = self.workspace / "t2ag"
        self.dst = self.workspace / "t2ag-lite"
        write(self.src / "main/a.txt", "source\n")
        write(self.dst / "old.txt", "old\n")
        self._stable_source = {
            "main/a.txt": (0o644, 7, hashlib.sha256(b"source\n").hexdigest()),
        }
        self._patches: list[tuple[object, str, object]] = []

        def fake_require_main_clean(src: Path, force: bool) -> None:
            return None

        def fake_build_candidate(
            src: Path, candidate: Path
        ) -> tuple[int, int, list[tuple[str, Path, Path]]]:
            target = candidate / "main" / "a.txt"
            write(target, "candidate\n")
            return 1, 0, [("main/a.txt", src / "main/a.txt", target)]

        def fake_verify_projection(
            src: Path,
            dst: Path,
            projected: list[tuple[str, Path, Path]],
        ) -> int:
            return 0

        def fake_check_current_projection(src: Path, dst: Path) -> int:
            return 0

        def fake_projection_manifest(
            src: Path, dst: Path
        ) -> list[tuple[str, Path, Path]]:
            return [("main/a.txt", src / "main/a.txt", dst / "main" / "a.txt")]

        def fake_source_projection_manifest(src: Path) -> dict[str, tuple[int, int, str]]:
            return dict(self._stable_source)

        self._install(
            sync_lite,
            "require_main_clean",
            fake_require_main_clean,
        )
        self._install(sync_lite, "build_candidate", fake_build_candidate)
        self._install(sync_lite, "verify_projection", fake_verify_projection)
        self._install(
            sync_lite, "check_current_projection", fake_check_current_projection
        )
        self._install(sync_lite, "projection_manifest", fake_projection_manifest)
        self._install(
            sync_lite, "source_projection_manifest", fake_source_projection_manifest
        )

    def _install(self, module: object, name: str, value: object) -> None:
        self._patches.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    def tearDown(self) -> None:
        os.environ.pop("T2AG_SYNC_LITE_FAIL_AT", None)
        for module, name, original in reversed(self._patches):
            setattr(module, name, original)
        self.temporary.cleanup()

    def _run_write(self) -> int:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = sync_lite.main(
                ["--write", "--root", str(self.workspace), "--force"]
            )
        self.last_stdout = stdout.getvalue()
        self.last_stderr = stderr.getvalue()
        return code

    def test_main_final_verify_restores_exact_old_lite(self) -> None:
        old = sync_lite.lite_content_manifest(self.dst)
        os.environ["T2AG_SYNC_LITE_FAIL_AT"] = "final_verify"
        code = self._run_write()
        self.assertEqual(code, 4)
        self.assertIn("injected failure at final_verify", self.last_stderr)
        self.assertIn("previous Lite restored and byte manifest verified", self.last_stderr)
        self.assertNotIn("ROLLBACK FAIL", self.last_stderr)
        self.assertEqual(sync_lite.lite_content_manifest(self.dst), old)
        self.assertTrue((self.dst / "old.txt").is_file())
        self.assertFalse((self.dst / "main" / "a.txt").exists())

    def test_main_final_return_restores_exact_old_lite(self) -> None:
        old = sync_lite.lite_content_manifest(self.dst)
        os.environ["T2AG_SYNC_LITE_FAIL_AT"] = "final_return"
        code = self._run_write()
        self.assertEqual(code, 4)
        self.assertIn("injected failure at final_return", self.last_stderr)
        self.assertIn("previous Lite restored and byte manifest verified", self.last_stderr)
        self.assertNotIn("ROLLBACK FAIL", self.last_stderr)
        self.assertEqual(sync_lite.lite_content_manifest(self.dst), old)

    def test_main_source_race_after_install_restores_exact_old_lite(self) -> None:
        old = sync_lite.lite_content_manifest(self.dst)
        calls = {"n": 0}
        stable = dict(self._stable_source)
        raced = {
            "main/a.txt": (0o644, 8, hashlib.sha256(b"changed\n").hexdigest()),
        }

        def racing_source_manifest(src: Path) -> dict[str, tuple[int, int, str]]:
            calls["n"] += 1
            # Calls: before_build, after_candidate, after_install, before_return
            if calls["n"] >= 3:
                return dict(raced)
            return dict(stable)

        self._install(sync_lite, "source_projection_manifest", racing_source_manifest)
        code = self._run_write()
        self.assertEqual(code, 4)
        self.assertIn(
            "Main projection source changed after Lite installation",
            self.last_stderr,
        )
        self.assertIn("previous Lite restored and byte manifest verified", self.last_stderr)
        self.assertNotIn("ROLLBACK FAIL", self.last_stderr)
        self.assertEqual(sync_lite.lite_content_manifest(self.dst), old)

    def test_main_source_race_after_candidate_leaves_old_lite_untouched(self) -> None:
        old = sync_lite.lite_content_manifest(self.dst)
        calls = {"n": 0}
        stable = dict(self._stable_source)
        raced = {
            "main/a.txt": (0o644, 8, hashlib.sha256(b"changed\n").hexdigest()),
        }

        def racing_source_manifest(src: Path) -> dict[str, tuple[int, int, str]]:
            calls["n"] += 1
            if calls["n"] >= 2:
                return dict(raced)
            return dict(stable)

        self._install(sync_lite, "source_projection_manifest", racing_source_manifest)
        code = self._run_write()
        self.assertEqual(code, 4)
        self.assertIn(
            "Main projection source changed after candidate verification",
            self.last_stderr,
        )
        self.assertEqual(sync_lite.lite_content_manifest(self.dst), old)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
