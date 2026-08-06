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
        errors = drc.validate_decision_records(root)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
