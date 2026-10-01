"""Main projection journeys and recoverable failure boundaries; synthetic data."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from t2ag_next import distribution as base
from t2ag_next import distribution_projection as p
from t2ag_next.model import DomainError


class ProjectionFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.source = self.parent / "source"
        (self.source / "t2ag_next").mkdir(parents=True)
        for name in base.REQUIRED_RUNTIME:
            (self.source / name).write_text("# synthetic public runtime\n", encoding="utf-8")
        (self.source / "pyproject.toml").write_text('[project]\nname="synthetic"\n', encoding="utf-8")
        for name in base.PUBLIC_DOCS:
            path = self.source / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("# Synthetic Guide\n\nThis is public guidance. Another sentence.\n", encoding="utf-8")
        (self.source / "instance").mkdir()
        (self.source / "instance/private.txt").write_text("Synthetic private learning history", encoding="utf-8")
        self.target = self.parent / "projection"

    def error(self, code, operation, *args, **kwargs):
        with self.assertRaises(DomainError) as caught:
            operation(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def tree(self, root):
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


class LiteProjection(ProjectionFixture):
    def test_check_only_new_and_existing_never_writes(self):
        before = self.tree(self.parent)
        result = p.lite_projection(self.source, self.target)
        self.assertFalse(result["written"])
        self.assertTrue(result["missing"])
        self.assertEqual(self.tree(self.parent), before)
        p.lite_projection(self.source, self.target, write=True)
        before = self.tree(self.parent)
        result = p.lite_projection(self.source, self.target)
        self.assertEqual(result["missing"] + result["different"] + result["orphan"], [])
        self.assertEqual(self.tree(self.parent), before)
        self.assertFalse((self.target / "instance").exists())
        self.assertFalse(json.loads((self.target / "READ_ONLY.json").read_bytes())["authority"])

    def test_owned_regeneration_and_explicit_rollback_preserve_both_generations(self):
        original_source = self.tree(self.source)
        p.lite_projection(self.source, self.target, write=True)
        original = self.tree(self.target)
        (self.source / "README.md").write_text("# New public guide\n", encoding="utf-8")
        report = p.lite_projection(self.source, self.target)
        self.assertEqual(report["different"], ["README.md"])
        result = p.lite_projection(self.source, self.target, write=True)
        newer = self.tree(self.target)
        self.assertEqual(self.tree(Path(result["backup"])), original)
        planned = p.rollback_projection(self.target, result["receipt"])
        self.assertFalse(planned["written"])
        self.assertEqual(self.tree(self.target), newer)
        undone = p.rollback_projection(self.target, result["receipt"], write=True)
        self.assertEqual(self.tree(self.target), original)
        self.assertEqual(self.tree(Path(undone["retained_new"])), newer)
        self.assertEqual((self.source / "instance/private.txt").read_bytes(), original_source["instance/private.txt"])

    def test_non_owned_and_unrelated_files_are_retained(self):
        self.target.mkdir(); (self.target / "unrelated.txt").write_bytes(b"keep")
        self.error("PROJECTION_NOT_OWNED", p.lite_projection, self.source, self.target, write=True)
        self.assertEqual(self.tree(self.target), {"unrelated.txt": b"keep"})
        owned = self.parent / "owned"
        p.lite_projection(self.source, owned, write=True)
        (owned / "unrelated.txt").write_bytes(b"also keep")
        before = self.tree(owned)
        self.error("PROJECTION_INVENTORY", p.lite_projection, self.source, owned, write=True)
        self.assertEqual(self.tree(owned), before)

    def test_owned_edits_are_not_silently_discarded(self):
        p.lite_projection(self.source, self.target, write=True)
        (self.target / "README.md").write_text("important manual edit", encoding="utf-8")
        report = p.lite_projection(self.source, self.target)
        self.assertEqual(report["ownership"], "PROJECTION_DRIFT")
        self.error("PROJECTION_DRIFT", p.lite_projection, self.source, self.target, write=True)
        self.assertEqual((self.target / "README.md").read_text(), "important manual edit")

    def test_swap_faults_restore_old_and_retain_recovery_receipt(self):
        p.lite_projection(self.source, self.target, write=True)
        old = self.tree(self.target)
        (self.source / "README.md").write_text("new", encoding="utf-8")
        for fail_at in ("after_stage", "after_backup", "after_publish"):
            with self.subTest(point=fail_at):
                def fault(point):
                    if point == fail_at:
                        raise RuntimeError("synthetic failure")
                with patch.object(p, "_fault", fault), self.assertRaises(RuntimeError):
                    p.lite_projection(self.source, self.target, write=True)
                self.assertEqual(self.tree(self.target), old)
        result = p.lite_projection(self.source, self.target, write=True)
        self.assertTrue(result["written"])
        self.assertGreaterEqual(len(list(self.parent.glob(".t2ag-projection-transaction-*.json"))), 5)

    def test_source_or_target_changed_during_build_never_overwrites_changes(self):
        p.lite_projection(self.source, self.target, write=True)
        old = self.tree(self.target)
        def source_change(point):
            if point == "after_stage":
                (self.source / "README.md").write_text("concurrent source edit", encoding="utf-8")
        with patch.object(p, "_fault", source_change):
            self.error("PROJECTION_SOURCE_DRIFT", p.lite_projection, self.source, self.target, write=True)
        self.assertEqual(self.tree(self.target), old)
        def target_change(point):
            if point == "before_publish":
                (self.target / "new-user-file.txt").write_bytes(b"keep")
        with patch.object(p, "_fault", target_change):
            self.error("PROJECTION_TARGET_DRIFT", p.lite_projection, self.source, self.target, write=True)
        self.assertEqual((self.target / "new-user-file.txt").read_bytes(), b"keep")

    def test_lock_is_os_released_and_not_stolen(self):
        with p._lock(self.target):
            self.error("PROJECTION_BUSY", p.lite_projection, self.source, self.target, write=True)
        self.assertTrue(p.lite_projection(self.source, self.target, write=True)["written"])

    def test_privacy_is_checked_before_any_output_and_overlap_is_rejected(self):
        (self.source / "README.md").write_text("Synthetic Private Institution", encoding="utf-8")
        before = self.tree(self.parent)
        self.error("PRIVACY_LEAK", p.lite_projection, self.source, self.target, write=True, forbidden_terms=["Synthetic Private Institution"])
        self.assertEqual(before, self.tree(self.parent))
        self.error("DESTINATION_OVERLAP", p.lite_projection, self.source, self.source / "derived", write=True)

    def test_interrupted_swap_can_restore_preserved_backup_from_receipt(self):
        p.lite_projection(self.source, self.target, write=True)
        old = self.tree(self.target)
        (self.source / "README.md").write_text("newer", encoding="utf-8")
        def abrupt(point):
            if point == "after_backup":
                raise KeyboardInterrupt("simulated process interruption; not power loss")
        with patch.object(p, "_fault", abrupt), self.assertRaises(KeyboardInterrupt):
            p.lite_projection(self.source, self.target, write=True)
        self.assertFalse(self.target.exists())
        receipts = [path for path in self.parent.glob(".t2ag-projection-transaction-*.json") if json.loads(path.read_bytes())["phase"] == "old_saved"]
        self.assertEqual(len(receipts), 1)
        p.rollback_projection(self.target, receipts[0], write=True)
        self.assertEqual(self.tree(self.target), old)

    def test_rollback_rejects_later_generation(self):
        first = p.lite_projection(self.source, self.target, write=True)
        second = p.lite_projection(self.source, self.target, write=True)
        current = self.tree(self.target)
        self.error("PROJECTION_ROLLBACK_STALE", p.rollback_projection, self.target, first["receipt"], write=True)
        self.assertEqual(self.tree(self.target), current)
        self.assertTrue(Path(second["backup"]).exists())


@unittest.skipUnless(importlib.util.find_spec("yaml"), "Install the optional okf/PyYAML dependency for real conformance tests.")
class OKFProjection(ProjectionFixture):
    def test_real_yaml_export_conformance_manifest_and_owned_regeneration(self):
        import yaml
        text = "---\ntype: Synthetic Custom Type\nstatus: draft\nsources:\n  - resource: https://example.org/reference\nverified: {by: 'human:not-exported'}\nstale_after: 2026-01-01\n---\n# Protocol\n\nThe first sentence. The second sentence.\n"
        (self.source / "docs/protocol.md").write_text(text, encoding="utf-8")
        before = self.tree(self.parent)
        report = p.okf_export(self.source, self.target)
        self.assertFalse(report["written"])
        self.assertEqual(before, self.tree(self.parent))
        p.okf_export(self.source, self.target, write=True)
        checked = p.check_bundle(self.target)
        self.assertTrue(checked["ok"]); self.assertTrue(checked["manifest_checked"])
        metadata, body = p._frontmatter((self.target / "docs/protocol.md").read_text(encoding="utf-8"))
        self.assertEqual(metadata["type"], "Synthetic Custom Type")
        self.assertEqual(metadata["description"], "The first sentence.")
        self.assertNotIn("verified", metadata); self.assertNotIn("stale_after", metadata)
        self.assertEqual(metadata["status"], "draft")
        self.assertEqual(metadata["sources"], [{"resource": "https://example.org/reference"}])
        self.assertIn("Protocol](/docs/protocol.md) - The first sentence.", (self.target / "index.md").read_text())
        self.assertIn("## ", (self.target / "log.md").read_text())
        self.assertTrue(p.okf_export(self.source, self.target, write=True)["backup"])

    def test_reference_graph_uses_included_targets_without_rewriting_commands_or_fences(self):
        document = "# Protocol\n\nA public rule.\n\n[Model](domain-model.md#terms) and `domain-model.md` then `domain-model.md`.\n[Not included](missing.md) and [Network](https://example.org/domain-model.md).\n`grep -rn \"x\" domain-model.md` and `40_course/<COURSE_ID>/course.md`.\n```sh\n`domain-model.md` [Example](domain-model.md)\n```\n"
        (self.source / "docs/protocol.md").write_text(document, encoding="utf-8")
        p.okf_export(self.source, self.target, write=True)
        output = (self.target / "docs/protocol.md").read_text(encoding="utf-8")
        self.assertIn("[Model](/docs/domain-model.md#terms)", output)
        self.assertIn("[domain-model.md](/docs/domain-model.md) then `domain-model.md`", output)
        self.assertIn('`grep -rn "x" domain-model.md`', output)
        self.assertIn("```sh\n`domain-model.md` [Example](domain-model.md)\n```", output)
        self.assertIn("[Not included](missing.md)", output)
        self.assertIn({"from": "docs/protocol.md", "to": "docs/domain-model.md"}, p.check_bundle(self.target)["edges"])
        self.assertEqual(p._rewrite("docs/protocol.md", "Literal `[Example](domain-model.md)` remains.\n", {"docs/domain-model.md"}), "Literal `[Example](domain-model.md)` remains.\n")

    def test_generic_conformance_tolerates_unknown_type_optional_absence_and_broken_links(self):
        self.target.mkdir()
        (self.target / "concept.md").write_text("---\ntype: Unknown Extension\nunfamiliar_key: [one, two]\n---\n# A\n[Missing](missing.md)\n", encoding="utf-8")
        report = p.check_bundle(self.target)
        self.assertTrue(report["ok"]); self.assertFalse(report["manifest_checked"])
        self.assertEqual(report["reserved"], [])

    def test_unparseable_yaml_empty_type_and_bad_reserved_structure_reject(self):
        self.target.mkdir()
        concept = self.target / "concept.md"
        for text, code in (("---\ntype: [broken\n---\n# A", "OKF_FRONTMATTER"), ("---\ntype: ''\n---\n# A", "OKF_TYPE")):
            concept.write_text(text, encoding="utf-8")
            self.error(code, p.check_bundle, self.target)
        concept.write_text("---\ntype: Valid\n---\n# A", encoding="utf-8")
        (self.target / "log.md").write_text("# Updates\n## 2026-02-30\nEntry", encoding="utf-8")
        self.error("OKF_LOG", p.check_bundle, self.target)
        (self.target / "log.md").write_text("# Updates\n## 2026-01-02\nEntry\n## 2026-01-01\nEarlier", encoding="utf-8")
        (self.target / "nested").mkdir()
        (self.target / "nested/index.md").write_text("---\nokf_version: '0.2'\n---\n# Index", encoding="utf-8")
        self.error("OKF_INDEX", p.check_bundle, self.target)

    def test_manifest_recomputes_graph_and_bytes(self):
        p.okf_export(self.source, self.target, write=True)
        manifest = json.loads((self.target / "manifest.json").read_bytes())
        manifest["edges"] = []
        (self.target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.error("OKF_MANIFEST", p.check_bundle, self.target)

    def test_course_whitelist_and_privacy_before_write_without_fake_timestamp(self):
        self.error("OKF_SCOPE", p.okf_export, self.source, self.target, course_definition={"id": "C", "progress": "private"}, write=True)
        before = self.tree(self.parent)
        self.error("PRIVACY_LEAK", p.okf_export, self.source, self.target, course_definition={"id": "C", "title": "Private School"}, forbidden_terms=["Private School"], write=True)
        self.assertEqual(self.tree(self.parent), before)
        report = p.okf_export(self.source, self.target, course_definition={"id": "C", "title": "Public course", "goal": "Understand the public concept."}, write=True)
        self.assertEqual(report["manifest"]["scope"], "course:C")
        self.assertEqual(report["manifest"]["course_timestamp"], "not_available")
        metadata, body = p._frontmatter((self.target / "course.md").read_text())
        self.assertNotIn("at", metadata["generated"])
        self.assertEqual(p.check_bundle(self.target)["concepts"], ["course.md"])


class MissingParser(ProjectionFixture):
    def test_missing_parser_is_never_reported_as_success(self):
        with patch.dict("sys.modules", {"yaml": None}):
            self.error("OKF_DEPENDENCY_REQUIRED", p.okf_export, self.source, self.target, write=True)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
