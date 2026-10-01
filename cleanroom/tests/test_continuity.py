"""Author journeys through real Journals; fixture statements are synthetic."""
from copy import deepcopy
from hashlib import sha256
import tempfile
import unittest

from t2ag_next import continuity as c, learning, support
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, get
from test_learning import Instance


class Fixture(Instance):
    def call(self, action, payload, student=None):
        request = self.request(action, payload, student)
        module = c if action in c.ACTIONS else learning if action in learning.ACTIONS else support
        result = self.journal.apply(request, module.plan)
        self.state = self.journal.read_state()
        return result


class ContinuityJourneys(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.j = Journal(self.temp.name)
        self.f = Fixture(self.j)

    def split_ready(self):
        f = self.f
        aid, bids = f.lesson()
        f.ready(); f.ticket(bids[0]); f.present(bids[0]); f.answer(bids[0])
        f.call("feeling.record", {"session_id": "s1", "block_id": bids[0], "disposition": "clear"}, "This part is clear.")
        for status in ("queued", "arrived", "pending", "confirmed"):
            f.call("checkpoint.record", {"id": "old-check", "activity_id": aid, "block_id": bids[0], "position": bids[0], "status": status,
                   "evidence": ["actual synthetic block answer"]}, "I have explained this definition." if status == "confirmed" else None)
        f.ticket(bids[1], tid="old-unused")
        targets = [aid + "/definition-name", aid + "/definition-number"]
        for bid, excerpt in zip(targets, ("Definition", "1.")):
            f.call("block.create", {"block_id": bid, "activity_id": aid, "teacher_title": "Arrangement " + excerpt,
                   "source_role": "definition", "body": "Explain " + excerpt,
                   "source_refs": [{"page_id": "page-1", "source_excerpt": excerpt, "locator": "Definition 1"}]})
        f.call("scope.create", {"scope_id": "scope-v2", "activity_id": aid, "source_id": "book-v1", "page_ids": ["page-1", "page-2"], "current_page_id": "page-1"})
        f.call("lessonmap.create", {"lessonmap_id": "map-v2", "activity_id": aid, "scope_id": "scope-v2", "block_ids": targets + [bids[1]]})
        receipts = f.data("preparation", "prep-v1")["receipts"]
        return {"id": "split-1", "activity_id": aid, "from_lessonmap_id": "map-v1", "to_lessonmap_id": "map-v2",
                "preparation_id": "prep-v2", "receipts": receipts, "reason": "Separate the same source definition for navigation.",
                "resume_block_id": targets[0], "rows": [{"kind": "split", "from_block_ids": [bids[0]], "to_block_ids": targets,
                    "reason": "The two source fragments together name the same definition.",
                    "checkpoint_links": [{"from_ids": ["old-check"], "to_id": "new-check-" + str(n), "to_block_id": bid} for n, bid in enumerate(targets)]}]}

    def test_split_keeps_confirmation_and_source_and_resumes_with_fresh_scan_and_ticket(self):
        p = self.split_ready(); f = self.f
        old_cp, old_block = f.data("checkpoint", "old-check"), f.data("block", "C/lesson/b1")
        revision = f.state["revision"]
        f.call("continuity.remap", p)
        self.assertEqual(f.state["revision"], revision + 1)
        self.assertEqual(f.data("checkpoint", "old-check"), old_cp)
        self.assertEqual(f.data("block", "C/lesson/b1"), old_block)
        self.assertEqual(f.data("checkpoint", "new-check-0")["status"], "confirmed")
        self.assertEqual(f.data("cursor", "C/lesson")["block_id"], p["resume_block_id"])
        self.assertEqual(f.data("ticket", "old-unused")["status"], "expired")
        self.assertEqual(f.data("session", "s1")["status"], "closed")
        self.assertEqual(f.data("activity", "C/lesson")["scope_id"], "scope-v2")
        f.call("session.start", {"session_id": "s2", "activity_id": "C/lesson"})
        with self.assertRaises(DomainError): f.ticket(p["resume_block_id"], "new-ticket", "s2")
        f.call("scan.record", {"scan_id": "scan-s2", "session_id": "s2", "scope_id": "scope-v2", "deliveries": f.deliveries("s2")})
        f.ticket(p["resume_block_id"], "new-ticket", "s2")
        f.call("block.present", {"session_id": "s2", "ticket_id": "new-ticket", "block_id": p["resume_block_id"],
               "body_sha256": f.data("block", p["resume_block_id"])["body_sha256"]})
        self.assertEqual(f.data("cursor", "C/lesson")["waiting_for"], "comprehension")
        self.assertEqual(f.data("ticket", "new-ticket")["status"], "consumed")

    def test_split_requires_explicit_successor_and_does_not_choose_first(self):
        p = self.split_ready(); p.pop("resume_block_id")
        before = self.j.read_state()
        with self.assertRaises(DomainError): self.f.call("continuity.remap", p)
        self.assertEqual(self.j.read_state(), before)

    def test_unmapped_block_and_changed_old_map_are_not_silently_accepted(self):
        p = self.split_ready()
        p["rows"][0]["to_block_ids"].pop(); p["rows"][0]["kind"] = "renumber"; p["rows"][0]["checkpoint_links"].pop()
        with self.assertRaises(DomainError) as error: self.f.call("continuity.remap", p)
        self.assertEqual(error.exception.code, "CONTINUITY_INCOMPLETE")

    def test_new_source_cannot_inherit_a_confirmation(self):
        p = self.split_ready(); target = p["rows"][0]["to_block_ids"][1]
        # A new legitimate block uses another original source fragment.
        self.f.call("block.create", {"block_id": "new-problem", "activity_id": "C/lesson", "teacher_title": "New problem", "source_role": "exercise", "body": "Explain this new problem.",
            "source_refs": [{"page_id": "page-1", "source_excerpt": "Problem 1: explain.", "locator": "Problem 1"}]})
        self.f.call("lessonmap.create", {"lessonmap_id": "different-map", "activity_id": "C/lesson", "scope_id": "scope-v2", "block_ids": [p["resume_block_id"], "new-problem", "C/lesson/b2"]})
        p["to_lessonmap_id"] = "different-map"; p["rows"][0]["to_block_ids"][1] = "new-problem"; p["rows"][0]["checkpoint_links"][1]["to_block_id"] = "new-problem"
        with self.assertRaises(DomainError) as error: self.f.call("continuity.remap", p)
        self.assertEqual(error.exception.code, "CONTINUITY_NEW_CONTENT")

    def test_merge_requires_all_confirmed_predecessors_and_preserves_both_originals(self):
        p = self.split_ready(); self.f.call("continuity.remap", p); f = self.f
        ids = p["rows"][0]["to_block_ids"]
        for bid in ids:
            f.call("coverage.decide", {"block_id": bid, "coverage": "explicitly_deferred", "reason": "Preserved confirmation; reorganize without presenting a second lesson."}, "Keep the recorded understanding and defer repeating these blocks.")
        f.call("block.create", {"block_id": "merged", "activity_id": "C/lesson", "teacher_title": "Merged navigation", "source_role": "definition", "body": "Review the two recorded fragments.",
            "source_refs": [{"page_id": "page-1", "source_excerpt": "Definition", "locator": "Name"}, {"page_id": "page-1", "source_excerpt": "1.", "locator": "Number"}]})
        f.call("scope.create", {"scope_id": "scope-v3", "activity_id": "C/lesson", "source_id": "book-v1", "page_ids": ["page-1", "page-2"], "current_page_id": "page-1"})
        f.call("lessonmap.create", {"lessonmap_id": "map-v3", "activity_id": "C/lesson", "scope_id": "scope-v3", "block_ids": ["merged", "C/lesson/b2"]})
        payload = {**p, "id": "merge-1", "from_lessonmap_id": "map-v2", "to_lessonmap_id": "map-v3", "preparation_id": "prep-v3", "resume_block_id": "merged",
                   "rows": [{"kind": "merge", "from_block_ids": ids, "to_block_ids": ["merged"], "reason": "Reunite the same two source fragments.",
                             "checkpoint_links": [{"from_ids": ["new-check-0"], "to_id": "merged-check", "to_block_id": "merged"}]}]}
        with self.assertRaises(DomainError): f.call("continuity.remap", payload)
        payload["rows"][0]["checkpoint_links"][0]["from_ids"].append("new-check-1")
        f.call("continuity.remap", payload)
        self.assertEqual(f.data("checkpoint", "merged-check")["status"], "confirmed")
        self.assertEqual(f.data("checkpoint", "new-check-0")["status"], "confirmed")
        self.assertEqual(f.data("cursor", "C/lesson")["block_id"], "merged")

    def external(self):
        body = "Original external rule, retained verbatim."
        self.f.call("external.register", {"id": "X", "identity": {"peer_system": "research", "peer_relative_path": "rules/core.md"},
                    "mode": "frozen", "contract": "read_only/manual_only", "content_sha256": sha256(body.encode()).hexdigest(),
                    "root_hints": {"research": {"windows_host": "C:/old-peer"}}})
        self.f.call("external.consume", {"id": "use-old", "reference_id": "X", "body": body, "observed_sha256": sha256(body.encode()).hexdigest(), "used_at": "2026-09-30T12:00:00Z"})
        return body

    def test_relocate_changes_only_host_hint_and_preserves_reference_identity(self):
        self.external(); old = self.f.data("external", "X")
        self.f.call("external.relocate", {"id": "X", "revision_id": "move-1", "reason": "Peer moved by its owner.", "root_hints": {"research": {"windows_host": "D:/new-peer"}}})
        current = self.f.data("external", "X")
        for field in ("identity", "mode", "content_sha256", "contract"):
            self.assertEqual(current[field], old[field])
        self.assertEqual(self.f.data("external_revision", "move-1")["before"], old)

    def test_explicit_rebind_uses_new_original_and_preserves_old_use(self):
        old = self.external(); new = "Explicit new external version."
        with self.assertRaises(DomainError): self.f.call("external.consume", {"id": "drift", "reference_id": "X", "body": new, "observed_sha256": sha256(new.encode()).hexdigest(), "used_at": "2026-10-01T12:00:00Z"})
        self.f.call("external.rebind", {"id": "X", "revision_id": "v2", "reason": "Observed upstream v2, bind explicitly.", "mode": "frozen", "contract": "read_only/manual_only",
            "body": new, "observed_sha256": sha256(new.encode()).hexdigest(), "peer_version": "v2", "effective_at": "2026-10-01T12:00:00Z"})
        self.f.call("external.consume", {"id": "use-new", "reference_id": "X", "body": new, "observed_sha256": sha256(new.encode()).hexdigest(), "used_at": "2026-10-01T12:00:00Z"})
        self.assertEqual(self.f.data("external_use", "use-old")["body"], old)
        self.assertEqual(self.f.data("external_revision", "v2")["change"]["body"], new)
        self.assertFalse(self.f.data("external_revision", "v2")["peer_accessed"])

    def test_imported_t1_location_change_keeps_its_policy_usable_by_normal_consumer(self):
        body = "Frozen imported reference."
        old = {"identity": {"peer_system": "research", "peer_relative_path": "rules/core.md"}, "kind": "frozen_version",
               "integrity_mode": "pinned", "rebind": "manual_only", "peer_version": "1", "content_sha256": sha256(body.encode()).hexdigest()}
        request = self.f.request("fixture.import", {})
        self.j.apply(request, lambda s, r: [support._new(s, "external", "legacy-X", old)])
        self.f.state = self.j.read_state()
        self.f.call("external.relocate", {"id": "legacy-X", "revision_id": "legacy-move", "reason": "Move only the root hint.",
            "root_hints": {"research": {"windows_host": "D:/same-peer"}}})
        self.f.call("external.consume", {"id": "legacy-use", "reference_id": "legacy-X", "body": body,
            "observed_sha256": sha256(body.encode()).hexdigest(), "used_at": "2026-10-01T12:00:00Z"})
        self.assertEqual(self.f.data("external_revision", "legacy-move")["before"], old)
        self.assertEqual(self.f.data("external_use", "legacy-use")["body"], body)

    def test_rebind_bad_body_or_unstable_identity_has_no_effect(self):
        self.external(); before = self.j.read_state()
        with self.assertRaises(DomainError): self.f.call("external.rebind", {"id": "X", "revision_id": "bad", "reason": "test", "mode": "frozen", "contract": "read_only",
            "body": "new", "observed_sha256": "0" * 64, "peer_version": "2", "effective_at": "2026-10-01"})
        self.assertEqual(self.j.read_state(), before)

    def history(self, ident="H1"):
        self.f.call("history.record", {"id": ident, "category": "journal", "body": "# Original retained history\n\nThe complete immutable text.",
            "implementation_status": "implemented", "review_status": "reviewed", "release_status": "not_released"})

    def test_history_navigation_opens_actual_body_and_deduplicates_redirect(self):
        self.history()
        self.f.call("history.redirect.register", {"id": "redirect-1", "locator": "old/journal.md", "target_key": "history/H1", "reason": "Prior path retained."})
        index = c.history_index(self.j.read_state())
        self.assertEqual(len(index["entries"]), 1)
        entry = index["entries"][0]
        self.assertEqual(entry["aliases"], ["old/journal.md"])
        actual = c.resolve_history(self.j.read_state(), entry["open"]["locator"])
        self.assertEqual(actual["record"], self.f.data("history", "H1"))
        redirected = c.resolve_history(self.j.read_state(), "old/journal.md")
        self.assertEqual(redirected["target_key"], actual["target_key"])

    def test_imported_artifact_redirect_has_a_consumer_without_rewriting_import(self):
        self.history("main/60_journal/H.md")
        # Exact imported registry shape; the fixture is not a public generic put.
        request = self.f.request("fixture.import", {})
        self.j.apply(request, lambda s, r: [support._new(s, "artifact_identity", "H", {"canonical_path": "main/60_journal/H.md",
             "redirects": ["archive/H.md"], "target_objects": ["history/main/60_journal/H.md"]})])
        before = self.j.read_state()
        result = c.resolve_history(before, "archive/H.md")
        self.assertEqual(result["id"], "main/60_journal/H.md")
        self.assertEqual(len(c.history_index(before)["entries"]), 1)
        self.assertEqual(self.j.read_state(), before)

    def test_history_broken_redirect_stays_unresolved_and_not_a_fake_record(self):
        request = self.f.request("fixture.import", {})
        self.j.apply(request, lambda s, r: [support._new(s, "legacy_identity", "old.md", {"file": "old.md", "canonical_path": "absent.md"})])
        self.assertEqual(c.history_index(self.j.read_state())["entries"], [])
        self.assertEqual(c.history_index(self.j.read_state())["unresolved_redirects"][0]["code"], "HISTORY_UNRESOLVED")

    def test_existing_bad_alias_cannot_hide_or_replace_a_canonical_fact(self):
        self.history("H1"); self.history("H2")
        request = self.f.request("fixture.import", {})
        self.j.apply(request, lambda s, r: [support._new(s, "history_redirect", "old-bad", {"locator": "H1", "target_key": "history/H2"})])
        state = self.j.read_state()
        self.assertEqual(c.resolve_history(state, "H1")["target_key"], "history/H1")
        self.assertEqual(c.resolve_history(state, "history/H1")["target_key"], "history/H1")
        self.assertEqual({row["id"] for row in c.history_index(state)["entries"]}, {"H1", "H2"})

    def test_imported_explicit_redirect_only_journal_keeps_one_canonical_index_entry(self):
        self.history("main/60_journal/register.md")
        self.f.call("history.record", {"id": "main/60_journal/old-register.md", "category": "journal",
            "body": "---\njournal_index: false\nredirect_to: register.md\n---\n\n# Redirect\nHistorical compatibility path; no original body copy.",
            "implementation_status": "legacy_evidence", "review_status": "not_revalidated", "release_status": "legacy_evidence"})
        state = self.j.read_state()
        target = c.resolve_history(state, "main/60_journal/old-register.md")
        self.assertEqual(target["target_key"], "history/main/60_journal/register.md")
        index = c.history_index(state)
        self.assertEqual(len(index["entries"]), 1)
        self.assertIn("main/60_journal/old-register.md", index["entries"][0]["aliases"])
        self.assertIn("history/main/60_journal/old-register.md", state["objects"])


if __name__ == "__main__":
    unittest.main()
