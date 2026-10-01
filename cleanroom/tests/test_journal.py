from copy import deepcopy
import hashlib
import json
import multiprocessing
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, get, put


def request(identity, expected=None, **payload):
    return {"request_id": identity, "action": "test.named_action", "payload": payload,
            "actor": {"role": "system", "source": "synthetic unit fixture", "text": "test request"},
            "expected": expected or {}}


def insert(state, req):
    return [put("course", req["payload"].get("id", "A"), {"title": req["payload"].get("title", "A")})]


class FailingJournal(Journal):
    failure = None

    def _fault(self, point):
        if point == self.failure:
            raise OSError("injected failure: " + point)


def hold_lock(path, ready, release):
    with Journal(path)._lock():
        ready.set()
        release.wait(20)


def commit_and_crash(path):
    class CrashJournal(Journal):
        def _fault(self, point):
            if point == "after_commit":
                os._exit(73)
    CrashJournal(path).apply(request("crash-commit"), insert)


def measure_growth(maximum=256):
    """Small reproducible synthetic history probe; not an agent benchmark."""
    milestones = {1, 32, 64, 128, maximum}
    samples, points = [], []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as temporary:
        store = Journal(Path(temporary) / "instance")
        store.initialize()
        for number in range(1, maximum + 1):
            req = request("growth-" + str(number), id="C" + str(number), title="Synthetic " + "x" * 256)
            tick = time.perf_counter()
            store.apply(req, insert)
            samples.append((time.perf_counter() - tick) * 1000)
            if number in milestones:
                recent = sorted(samples[-32:])
                points.append({"committed_transactions_excluding_initialization": number,
                               "last_write_ms": round(samples[-1], 3), "recent_sample_count": len(recent),
                               "recent_p50_ms": round(recent[len(recent) // 2], 3),
                               "recent_p95_ms": round(recent[max(0, (95 * len(recent) + 99) // 100 - 1)], 3),
                               "log_bytes": store.log_path.stat().st_size})
        state = store.read_state()
        valid = store.validate()
        return {"kind": "journal_synthetic_growth", "platform": platform.platform(), "python": platform.python_version(),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "points": points,
                "final_revision": state["revision"], "objects": len(state["objects"]), "validated": valid["ok"],
                "conditions": "single process/worker; synthetic 256-character bodies; no blobs; OS cache unverified; one sequence, not statistical comparison",
                "limitations": "Does not measure large assets, real legacy history, agent latency, or new-vs-old improvement."}


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "instance"
        self.journal = FailingJournal(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def assertCode(self, code, function, *args):
        with self.assertRaises(DomainError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)

    def test_initialize_is_attributed_idempotent_and_profile_conflict_is_rejected(self):
        state = self.journal.initialize({"name": "Synthetic Learner"})
        self.assertEqual(state["objects"]["student/current"]["version"], 0)
        self.assertEqual(self.journal.initialize({"name": "Synthetic Learner"}), state)
        self.assertCode("INITIALIZATION_CONFLICT", self.journal.initialize, {"name": "Other"})
        self.assertEqual(self.journal.validate()["transactions"], 1)

    def test_none_profile_does_not_invent_student(self):
        self.assertEqual(self.journal.initialize()["objects"], {})

    def test_all_effects_publish_at_one_revision_and_slash_id_is_logical(self):
        self.journal.initialize()
        result = self.journal.apply(request("two"), lambda state, req: [put("course", "A", {"n": 1}), put("activity", "A/lesson/../one", {"course_id": "A"})])
        state = self.journal.read_state()
        self.assertEqual(result["revision"], 1)
        self.assertEqual({item["version"] for item in state["objects"].values()}, {1})
        self.assertIn("activity/A/lesson/../one", state["objects"])
        self.assertFalse((self.path / "activity").exists())

    def test_unrelated_updates_do_not_stale_unchanged_entity(self):
        self.journal.initialize()
        self.journal.apply(request("a", id="A"), insert)
        self.journal.apply(request("b", id="B"), insert)
        self.journal.apply(request("a2", {"course/A": 1}, id="A", title="updated"), insert)
        self.assertEqual(self.journal.read_state()["objects"]["course/A"]["version"], 3)

    def test_required_versions_stale_requests_and_missing_objects(self):
        self.journal.initialize()
        self.journal.apply(request("a"), insert)
        self.assertCode("VERSION_REQUIRED", self.journal.apply, request("a2"), insert)
        self.assertCode("STALE_VERSION", self.journal.apply, request("a3", {"course/A": 0}), insert)
        self.assertCode("STALE_VERSION", self.journal.apply, request("a4", {"course/missing": 1}), insert)
        self.assertEqual(self.journal.read_state()["revision"], 1)

    def test_named_read_dependencies_require_versions_but_iteration_does_not(self):
        self.journal.initialize()
        self.journal.apply(request("a"), insert)
        def dependent(state, req):
            course = get(state, "course", "A")
            return [put("note", "n", {"course_title": course["title"]})]
        self.assertCode("VERSION_REQUIRED", self.journal.apply, request("missing"), dependent)
        self.journal.apply(request("bound", {"course/A": 1}), dependent)
        self.journal.apply(request("collection"), lambda state, req: [put("note", "count", {"n": len(list(state["objects"].items()))})])

    def test_idempotency_before_staleness_and_different_request_rejected(self):
        self.journal.initialize()
        self.journal.apply(request("a"), insert)
        update = request("u", {"course/A": 1}, title="new")
        result = self.journal.apply(update, insert)
        replay = self.journal.apply(update, lambda *_: self.fail("replay must not rerun planner"))
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["revision"], result["revision"])
        changed = deepcopy(update)
        changed["actor"]["text"] = "different"
        self.assertCode("REQUEST_ID_REUSED", self.journal.apply, changed, insert)
        self.assertEqual(self.journal.lookup("u")["revision"], 2)
        self.assertIsNone(self.journal.lookup("not present"))

    def test_before_append_failure_is_no_commit(self):
        self.journal.initialize()
        self.journal.failure = "before_append"
        self.assertCode("COMMIT_NOT_PUBLISHED", self.journal.apply, request("a"), insert)
        self.journal.failure = None
        self.assertIsNone(self.journal.lookup("a"))
        self.assertEqual(self.journal.read_state()["revision"], 0)

    def test_after_commit_lost_response_replays_once(self):
        self.journal.initialize()
        self.journal.failure = "after_commit"
        self.assertCode("COMMIT_UNKNOWN", self.journal.apply, request("a"), insert)
        self.journal.failure = None
        self.assertTrue(self.journal.apply(request("a"), insert)["replayed"])
        self.assertEqual(self.journal.validate()["transactions"], 2)

    def test_projection_failure_does_not_remove_committed_fact(self):
        self.journal.initialize()
        self.journal.failure = "before_projection"
        self.assertCode("COMMIT_UNKNOWN", self.journal.apply, request("a"), insert)
        self.journal.failure = None
        self.assertEqual(self.journal.read_state()["objects"]["course/A"]["data"]["title"], "A")
        self.journal.projection_path.write_bytes(b"corrupt cache")
        self.assertEqual(self.journal.read_state()["revision"], 1)

    def test_initialize_failure_before_and_after_commit(self):
        self.journal.failure = "before_append"
        self.assertCode("COMMIT_NOT_PUBLISHED", self.journal.initialize)
        self.assertFalse(self.journal.log_path.exists())
        self.journal.failure = "after_commit"
        self.assertCode("COMMIT_UNKNOWN", self.journal.initialize)
        self.journal.failure = None
        self.assertEqual(self.journal.initialize()["revision"], 0)
        self.assertEqual(self.journal.validate()["transactions"], 1)

    def test_os_lock_is_not_stolen_and_releases_on_exit(self):
        self.journal.initialize()
        with self.journal._lock():
            self.assertCode("LOCK_BUSY", Journal(self.path).initialize)
            self.assertCode("LOCK_BUSY", Journal(self.path).apply, request("a"), insert)
        self.assertEqual(Journal(self.path).apply(request("a"), insert)["revision"], 1)

    def test_terminated_process_lock_is_released_by_os(self):
        self.journal.initialize()
        context = multiprocessing.get_context("spawn")
        ready, release = context.Event(), context.Event()
        child = context.Process(target=hold_lock, args=(str(self.path), ready, release))
        child.start()
        try:
            self.assertTrue(ready.wait(10), "child did not acquire lock")
            self.assertCode("LOCK_BUSY", self.journal.read_state)
        finally:
            child.terminate()
            child.join(10)
        self.assertFalse(child.is_alive())
        self.assertEqual(self.journal.read_state()["revision"], 0)

    def test_real_process_death_after_commit_returns_original_on_retry(self):
        self.journal.initialize()
        child = multiprocessing.get_context("spawn").Process(target=commit_and_crash, args=(str(self.path),))
        child.start()
        child.join(10)
        if child.is_alive():
            child.terminate()
            child.join(10)
            self.fail("crash child did not finish")
        self.assertEqual(child.exitcode, 73)
        self.assertTrue(self.journal.apply(request("crash-commit"), insert)["replayed"])
        self.assertEqual(self.journal.validate()["transactions"], 2)

    def test_torn_tail_is_error_and_not_truncated(self):
        self.journal.initialize()
        with self.journal.log_path.open("ab") as stream:
            stream.write(b'{"torn":')
        before = self.journal.log_path.read_bytes()
        self.assertCode("JOURNAL_TORN", self.journal.read_state)
        self.assertEqual(self.journal.log_path.read_bytes(), before)

    def test_hash_tamper_is_detected(self):
        self.journal.initialize()
        self.journal.apply(request("a"), insert)
        raw = self.journal.log_path.read_bytes().replace(b'"title":"A"', b'"title":"B"')
        self.journal.log_path.write_bytes(raw)
        self.assertCode("JOURNAL_HASH", self.journal.validate)

    def test_blob_precedes_log_reference_and_read_checks_hash(self):
        self.journal.initialize()
        asset = self.journal.put_blob(b"a real immutable asset")
        self.assertEqual(asset["sha256"], hashlib.sha256(b"a real immutable asset").hexdigest())
        self.journal.apply(request("asset"), lambda *_: [put("source", "s", {"blob_refs": [asset], "body_sha256": "not a blob"})])
        self.assertEqual(self.journal.read_blob(asset["sha256"]), b"a real immutable asset")
        self.assertEqual(self.journal.validate()["referenced_blobs"], 1)
        (self.journal.blob_path / asset["sha256"]).write_bytes(b"tamper")
        self.assertCode("BLOB_SIZE_MISMATCH", self.journal.read_state)
        self.assertCode("BLOB_CORRUPT", self.journal.read_blob, asset["sha256"])

    def test_routine_replay_does_not_rehash_unchanged_history_assets(self):
        self.journal.initialize()
        asset = self.journal.put_blob(b"history source")
        self.journal.apply(request("asset"), lambda *_: [put("source", "s", {"blob_refs": [asset]})])
        with patch.object(self.journal, "_verify_blob", wraps=self.journal._verify_blob) as verifier:
            self.journal.read_state()
            self.assertEqual(verifier.call_count, 0)
            self.assertEqual(self.journal.last_verification["scope"], "asset_metadata")
            self.assertTrue(self.journal.last_verification["full_asset_audit_pending"])
            self.journal.apply(request("unrelated", id="B"), insert)
            self.assertEqual(verifier.call_count, 0)
            self.journal.apply(request("same-asset"), lambda *_: [put("note", "n", {"blob_refs": [asset]})])
            self.assertEqual(verifier.call_count, 1, "new effect references must be strongly checked before commit")

    def test_jr_r1_drift_after_asset_hash_cannot_be_registered_as_verified(self):
        self.journal.initialize()
        asset = self.journal.put_blob(b"GOOD")
        path = self.journal.blob_path / asset["sha256"]
        original_entry = self.journal._entry
        def drift_before_entry(*args, **kwargs):
            stat = path.stat()
            path.write_bytes(b"EVIL")
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
            return original_entry(*args, **kwargs)
        self.journal._entry = drift_before_entry
        self.assertCode("BLOB_CHANGED", self.journal.apply, request("race"), lambda *_: [put("source", "s", {"blob_refs": [asset]})])
        self.assertIsNone(self.journal.lookup("race"))
        self.assertEqual(self.journal.read_state()["revision"], 0)

    def test_jr_r1_drift_after_entry_before_append_is_not_acknowledged(self):
        self.journal.initialize()
        asset = self.journal.put_blob(b"GOOD")
        path = self.journal.blob_path / asset["sha256"]
        def drift(point):
            if point == "before_append":
                stat = path.stat()
                path.write_bytes(b"EVIL")
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
        self.journal._fault = drift
        self.assertCode("BLOB_CHANGED", self.journal.apply, request("race"), lambda *_: [put("source", "s", {"blob_refs": [asset]})])
        self.assertIsNone(self.journal.lookup("race"))
        self.assertEqual(self.journal.read_state()["revision"], 0)

    def test_changed_stat_is_rehashed_for_legitimate_copy_or_touch(self):
        self.journal.initialize()
        asset = self.journal.put_blob(b"unchanged content")
        self.journal.apply(request("asset"), lambda *_: [put("source", "s", {"blob_refs": [asset]})])
        path = self.journal.blob_path / asset["sha256"]
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
        with patch.object(self.journal, "_verify_blob", wraps=self.journal._verify_blob) as verifier:
            self.journal.read_state()
            self.assertEqual(verifier.call_count, 1)
        self.assertEqual(self.journal.last_verification["scope"], "metadata_plus_changed_asset_hash")
        self.assertEqual(self.journal.last_verification["changed_assets_rehashed"], [asset["sha256"]])

    def test_same_stat_corruption_model_is_caught_by_consumption_and_full_audit(self):
        self.journal.initialize()
        asset = self.journal.put_blob(b"good-content")
        self.journal.apply(request("asset"), lambda *_: [put("source", "s", {"blob_refs": [asset]})])
        signature = self.journal._blob_stat(asset["sha256"])
        (self.journal.blob_path / asset["sha256"]).write_bytes(b"evil-content")
        # Model storage bit corruption with unchanged observable stat metadata;
        # ordinary program writes may update un-restorable ctime on POSIX.
        with patch.object(self.journal, "_blob_stat", return_value=signature):
            self.journal.read_state()
            self.assertTrue(self.journal.last_verification["full_asset_audit_pending"])
            self.assertCode("BLOB_CORRUPT", self.journal.read_blob, asset["sha256"])
            self.assertCode("BLOB_CORRUPT", self.journal.validate)

    def test_old_entries_missing_asset_metadata_remain_explicitly_partial(self):
        self.journal.initialize()
        asset = self.journal.put_blob(b"legacy-format content")
        self.journal.apply(request("asset"), lambda *_: [put("source", "s", {"blob_sha256": asset["sha256"]})])
        entries = [json.loads(line) for line in self.journal.log_path.read_text(encoding="utf-8").splitlines()]
        previous = None
        for entry in entries:
            entry.pop("assets")
            entry["prev_hash"] = previous
            unsigned = {name: value for name, value in entry.items() if name != "hash"}
            entry["hash"] = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            previous = entry["hash"]
        self.journal.log_path.write_text("\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n", encoding="utf-8")
        self.journal.read_state()
        self.assertEqual(self.journal.last_verification["legacy_assets_without_complete_metadata"], [asset["sha256"]])
        report = self.journal.validate()
        self.assertEqual(report["verification"]["scope"], "full_asset_content_hash")
        self.assertFalse(report["verification"]["full_asset_audit_pending"])

    def test_missing_blob_rejected_before_transaction(self):
        self.journal.initialize()
        self.assertCode("BLOB_MISSING", self.journal.apply, request("missing"), lambda *_: [put("source", "s", {"blob_sha256": "a" * 64})])
        self.assertEqual(self.journal.read_state()["revision"], 0)

    def test_blob_byte_count_mismatch_rejected(self):
        self.journal.initialize()
        asset = self.journal.put_blob(b"abc")
        asset["bytes"] = 10
        self.assertCode("BLOB_SIZE_MISMATCH", self.journal.apply, request("wrongsize"), lambda *_: [put("source", "s", {"blob_refs": [asset]})])

    def test_partial_asset_retained_as_residue_not_fact(self):
        self.journal.initialize()
        self.journal.failure = "asset_partial_write"
        self.assertCode("STORAGE_IO_ERROR", self.journal.put_blob, b"partial")
        self.journal.failure = None
        report = self.journal.validate()
        self.assertEqual(len(report["pending_assets"]), 1)
        self.assertEqual(report["referenced_blobs"], 0)
        self.assertEqual(report["revision"], 0)

    def test_complete_asset_without_log_is_unreferenced_and_retry_is_safe(self):
        self.journal.initialize()
        self.journal.failure = "asset_installed"
        self.assertCode("STORAGE_IO_ERROR", self.journal.put_blob, b"complete")
        self.journal.failure = None
        self.assertEqual(len(self.journal.validate()["unreferenced_blobs"]), 1)
        a = self.journal.put_blob(b"complete")
        b = self.journal.put_blob(b"complete")
        self.assertEqual(a, b)
        self.assertEqual(self.journal.read_state()["revision"], 0)

    def test_put_file_streams_original_and_checks_source_drift(self):
        self.journal.initialize()
        source = Path(self.temp.name) / "input.bin"
        source.write_bytes(b"source")
        result = self.journal.put_file(source)
        self.assertEqual(self.journal.read_blob(result["sha256"]), b"source")
        original = self.journal._fault
        def change(point):
            if point == "asset_installed":
                source.write_bytes(b"changed source length")
            original(point)
        self.journal._fault = change
        self.assertCode("SOURCE_CHANGED", self.journal.put_file, source)

    def test_planner_mutation_and_duplicate_effects_rejected(self):
        self.journal.initialize()
        def mutate(state, req):
            state["revision"] = 100
            return []
        self.assertCode("PLANNER_MUTATED_STATE", self.journal.apply, request("mut"), mutate)
        self.assertCode("DUPLICATE_EFFECT", self.journal.apply, request("dupe"), lambda *_: [put("note", "n", {}), put("note", "n", {})])

    def test_rebind_relocated_assets_appends_full_history_and_new_process_reuses_metadata(self):
        self.journal.initialize()
        old = self.journal.put_blob(b"historical source")
        self.journal.apply(request("with-asset"), lambda *_: [put("source", "S", {"blob_refs": [old]})])
        self.journal.apply(request("removed-current-ref", {"source/S": 1}), lambda *_: [put("source", "S", {"retired": True})])
        source_log = self.journal.log_path.read_bytes()
        copied = Path(self.temp.name) / "relocated"
        shutil.copytree(self.path, copied)
        clone = Journal(copied)
        clone.read_state()
        self.assertEqual(clone.last_verification["asset_content_hash_count"], 1)
        result = clone.rebind_assets("relocation-1")
        self.assertTrue(clone.log_path.read_bytes().startswith(source_log))
        self.assertEqual(self.journal.log_path.read_bytes(), source_log)
        bound = result["effects"][0]["data"]
        self.assertEqual(bound["blob_refs"], [old])
        self.assertEqual(bound["prior_revision"], 2)
        self.assertEqual(result["verification"]["revision"], 3)
        self.assertEqual(result["verification"]["asset_content_hash_count"], 1)
        program = "import json,sys;from t2ag_next.journal import Journal;s=Journal(sys.argv[1]);s.read_state();print(json.dumps(s.last_verification))"
        checked = subprocess.run([sys.executable, "-B", "-c", program, str(copied)], capture_output=True, text=True, check=True)
        report = json.loads(checked.stdout)
        self.assertEqual(report["asset_content_hash_count"], 0)
        self.assertEqual(report["scope"], "asset_metadata")
        self.assertTrue(report["full_asset_audit_pending"])
        self.assertEqual(clone.validate()["verification"]["asset_content_hash_count"], 1)

    def test_rebind_idempotency_never_reuses_other_action_or_expands_old_set(self):
        self.journal.initialize()
        self.journal.apply(request("other-action"), insert)
        self.assertCode("REQUEST_ID_REUSED", self.journal.rebind_assets, "other-action")
        first = self.journal.rebind_assets("empty-binding")
        asset = self.journal.put_blob(b"new later asset")
        self.journal.apply(request("new-ref"), lambda *_: [put("source", "new", {"blob_refs": [asset]})])
        replay = self.journal.rebind_assets("empty-binding")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["revision"], first["revision"])
        self.assertEqual(replay["effects"], first["effects"])
        self.assertEqual(replay["effects"][0]["data"]["blob_refs"], [])
        self.assertEqual(replay["verification"]["revision"], 3)

    def test_rebind_cannot_bless_corrupt_source(self):
        self.journal.initialize()
        blob = self.journal.put_blob(b"GOOD")
        self.journal.apply(request("asset"), lambda *_: [put("source", "S", {"blob_refs": [blob]})])
        original = self.journal.log_path.read_bytes()
        (self.journal.blob_path / blob["sha256"]).write_bytes(b"EVIL")
        self.assertCode("BLOB_CORRUPT", self.journal.rebind_assets, "bad-rebind")
        self.assertEqual(self.journal.log_path.read_bytes(), original)

    def test_rebind_post_hash_drift_is_not_published(self):
        self.journal.initialize()
        blob = self.journal.put_blob(b"GOOD")
        self.journal.apply(request("asset"), lambda *_: [put("source", "S", {"blob_refs": [blob]})])
        original = self.journal.log_path.read_bytes()
        def drift(point):
            if point == "after_asset_verification":
                (self.journal.blob_path / blob["sha256"]).write_bytes(b"EVIL!")
        self.journal._fault = drift
        self.assertCode("BLOB_CHANGED", self.journal.rebind_assets, "drift-rebind")
        self.assertEqual(self.journal.log_path.read_bytes(), original)

    def test_rebind_response_loss_retries_original_maintenance_transaction_once(self):
        self.journal.initialize()
        self.journal.failure = "after_commit"
        self.assertCode("COMMIT_UNKNOWN", self.journal.rebind_assets, "lost-rebind")
        self.journal.failure = None
        again = self.journal.rebind_assets("lost-rebind")
        self.assertTrue(again["replayed"])
        self.assertEqual(again["revision"], 1)
        self.assertEqual(self.journal.validate()["transactions"], 2)


if __name__ == "__main__":
    unittest.main()
