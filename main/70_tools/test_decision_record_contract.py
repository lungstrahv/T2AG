#!/usr/bin/env python3
"""Atomic tests for Evolution Register ↔ ADR contract (pure, temp trees)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import decision_record_contract as drc


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _live_flavor(root: Path) -> str:
    """Same rule as t2ag_doctor.detect_flavor (skeleton ships no profile)."""
    if root.name == "t2ag-skeleton":
        return "skeleton"
    readme = root / "README.md"
    text = (
        readme.read_text(encoding="utf-8-sig", errors="replace")
        if readme.is_file()
        else ""
    )
    return "skeleton" if "t2ag-skeleton" in text else "main"


def _minimal_tree(root: Path) -> None:
    _write(
        root / drc.REDIRECT_REL,
        "---\njournal_index: false\nredirect_to: t2ag_evolution_register.md\n---\n"
        "# Redirect\n\nSee t2ag_evolution_register.md\n",
    )
    _write(
        root / drc.REGISTER_REL,
        "# Register\n\n"
        "### EV-0012｜pages\n\n"
        "- **ID**：EV-0012\n"
        "- **状态**：`archived`\n"
        "- **decision_class**：`architecture`\n"
        "- **adr_refs**：`[ADR-0001]`\n\n"
        "### EV-0013｜egress\n\n"
        "- **ID**：EV-0013\n"
        "- **状态**：`discussing`\n"
        "- **decision_class**：`architecture`\n"
        "- **adr_refs**：`[ADR-0002]`\n",
    )
    _write(
        root / "docs/adr/0001-x.md",
        "---\n"
        "adr_id: ADR-0001\n"
        "portable_key: textbook-source-assets-and-bounded-cache\n"
        "status: accepted\n"
        "source_evolution: [EV-0012]\n"
        "supersedes: []\n"
        "---\n# ADR-0001\n",
    )
    _write(
        root / "docs/adr/0002-x.md",
        "---\n"
        "adr_id: ADR-0002\n"
        "portable_key: host-controlled-textbook-teaching-egress\n"
        "status: proposed\n"
        "source_evolution: [EV-0013]\n"
        "supersedes: []\n"
        "---\n# ADR-0002\n",
    )


class DecisionRecordContractTests(unittest.TestCase):
    def test_live_repo_validates(self) -> None:
        root = Path(__file__).resolve().parents[2]
        errors = drc.validate_decision_records(root, _live_flavor(root))
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_happy_minimal_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            self.assertEqual(drc.validate_decision_records(root), [])

    def test_dangling_ev_to_adr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            reg = (root / drc.REGISTER_REL).read_text(encoding="utf-8")
            reg = reg.replace("[ADR-0001]", "[ADR-0099]")
            (root / drc.REGISTER_REL).write_text(reg, encoding="utf-8")
            errors = drc.validate_decision_records(root)
            self.assertTrue(any("dangling EV→ADR" in e for e in errors), errors)

    def test_dangling_adr_to_ev(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            adr = (root / "docs/adr/0001-x.md").read_text(encoding="utf-8")
            adr = adr.replace("EV-0012", "EV-0099")
            (root / "docs/adr/0001-x.md").write_text(adr, encoding="utf-8")
            errors = drc.validate_decision_records(root)
            self.assertTrue(any("dangling ADR→EV" in e for e in errors), errors)

    def test_accepted_adr_points_at_observing_ev(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            reg = (root / drc.REGISTER_REL).read_text(encoding="utf-8")
            reg = reg.replace(
                "### EV-0012｜pages\n\n- **ID**：EV-0012\n- **状态**：`archived`",
                "### EV-0012｜pages\n\n- **ID**：EV-0012\n- **状态**：`observing`",
            )
            (root / drc.REGISTER_REL).write_text(reg, encoding="utf-8")
            errors = drc.validate_decision_records(root)
            self.assertTrue(any("accepted ADR" in e for e in errors), errors)

    def test_duplicate_portable_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            _write(
                root / "docs/adr/0003-x.md",
                "---\n"
                "adr_id: ADR-0003\n"
                "portable_key: textbook-source-assets-and-bounded-cache\n"
                "status: proposed\n"
                "source_evolution: [EV-0013]\n"
                "supersedes: []\n"
                "---\n# ADR-0003\n",
            )
            errors = drc.validate_decision_records(root)
            self.assertTrue(any("duplicate portable_key" in e for e in errors), errors)

    def test_supersedes_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            a1 = (root / "docs/adr/0001-x.md").read_text(encoding="utf-8")
            a1 = a1.replace("supersedes: []", "supersedes: [ADR-0002]")
            (root / "docs/adr/0001-x.md").write_text(a1, encoding="utf-8")
            a2 = (root / "docs/adr/0002-x.md").read_text(encoding="utf-8")
            a2 = a2.replace("supersedes: []", "supersedes: [ADR-0001]")
            (root / "docs/adr/0002-x.md").write_text(a2, encoding="utf-8")
            errors = drc.validate_decision_records(root)
            self.assertTrue(any("cycle" in e for e in errors), errors)

    def test_redirect_canonical_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            (root / drc.REGISTER_REL).unlink()
            errors = drc.validate_decision_records(root)
            self.assertTrue(any("missing Evolution Register canonical" in e for e in errors), errors)

    def test_legacy_ev_without_adr_not_forced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            reg = (root / drc.REGISTER_REL).read_text(encoding="utf-8")
            reg += (
                "\n### EV-0001｜legacy\n\n"
                "- **ID**：EV-0001\n"
                "- **状态**：`observing`\n"
            )
            (root / drc.REGISTER_REL).write_text(reg, encoding="utf-8")
            self.assertEqual(drc.validate_decision_records(root), [])


class SkeletonFlavorTests(unittest.TestCase):
    """EV-0023: skeleton register is instance-fresh; EV refs are provenance."""

    def test_skeleton_tolerates_external_ev_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            adr = (root / "docs/adr/0001-x.md").read_text(encoding="utf-8")
            adr = adr.replace("EV-0012", "EV-0099")
            (root / "docs/adr/0001-x.md").write_text(adr, encoding="utf-8")
            main_errors = drc.validate_decision_records(root, "main")
            self.assertTrue(any("dangling ADR→EV" in e for e in main_errors), main_errors)
            skel_errors = drc.validate_decision_records(root, "skeleton")
            self.assertFalse(any("dangling ADR→EV" in e for e in skel_errors), skel_errors)

    def test_skeleton_keeps_adr_integrity_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_tree(root)
            adr = (root / "docs/adr/0001-x.md").read_text(encoding="utf-8")
            adr = adr.replace("source_evolution: [EV-0012]", "source_evolution: []")
            (root / "docs/adr/0001-x.md").write_text(adr, encoding="utf-8")
            errors = drc.validate_decision_records(root, "skeleton")
            self.assertTrue(any("missing source_evolution" in e for e in errors), errors)


class DecisionCitationTests(unittest.TestCase):
    """P-0067: live normative prose must not cite nonexistent ADR/EV records."""

    def _tree(self, root: Path) -> None:
        _minimal_tree(root)
        _write(
            root / "main/t2ag.md",
            "# 宪法\n\n扫描判据见 ADR-0001 与 EV-0012。\n",
        )

    def test_live_repo_citations_valid(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            drc.validate_decision_citations(root, _live_flavor(root)), []
        )

    def test_dangling_adr_citation_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            text = (root / "main/t2ag.md").read_text(encoding="utf-8")
            (root / "main/t2ag.md").write_text(
                text + "另见 ADR-0009。\n", encoding="utf-8"
            )
            errors = drc.validate_decision_citations(root, "main")
            self.assertTrue(any("ADR-0009" in e for e in errors), errors)

    def test_dangling_ev_citation_flagged_in_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            text = (root / "main/t2ag.md").read_text(encoding="utf-8")
            (root / "main/t2ag.md").write_text(
                text + "另见 EV-0099。\n", encoding="utf-8"
            )
            errors = drc.validate_decision_citations(root, "main")
            self.assertTrue(any("EV-0099" in e for e in errors), errors)

    def test_skeleton_ev_exempt_but_adr_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            text = (root / "main/t2ag.md").read_text(encoding="utf-8")
            (root / "main/t2ag.md").write_text(
                text + "另见 EV-0099 与 ADR-0009。\n", encoding="utf-8"
            )
            errors = drc.validate_decision_citations(root, "skeleton")
            self.assertFalse(any("EV-0099" in e for e in errors), errors)
            self.assertTrue(any("ADR-0009" in e for e in errors), errors)

    def test_history_files_out_of_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            _write(
                root / "main/00_core/t2ag_changelog.md",
                "# changelog\n\n历史条目曾引用 ADR-0099 与 EV-0099，合法。\n",
            )
            self.assertEqual(drc.validate_decision_citations(root, "main"), [])

    def test_playbook_surface_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            _write(
                root / "main/50_playbook/startup_orchestration.md",
                "# startup\n\n canonical：ADR-0007。\n",
            )
            errors = drc.validate_decision_citations(root, "main")
            self.assertTrue(any("ADR-0007" in e for e in errors), errors)

    def test_adr_body_surface_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            _write(
                root / "docs/adr/0002-live.md",
                "# ADR-0002\n\nThis live decision cites ADR-0007.\n",
            )
            errors = drc.validate_decision_citations(root, "main")
            self.assertTrue(any("ADR-0007" in e for e in errors), errors)

    def test_protocol_surface_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            _write(
                root / "docs/protocol/example.md",
                "# Protocol\n\nCompanion decision: ADR-0007.\n",
            )
            errors = drc.validate_decision_citations(root, "main")
            self.assertTrue(any("ADR-0007" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
