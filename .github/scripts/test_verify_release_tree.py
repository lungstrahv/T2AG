#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import verify_release_tree as verifier  # noqa: E402


def valid_surface() -> set[str]:
    paths = set(verifier.REQUIRED_ROOT_FILES)
    for edition in verifier.EDITIONS:
        paths.update(f"{edition}/{path}" for path in verifier.REQUIRED_EDITION_FILES)
    return paths


class ReleaseTreeTests(unittest.TestCase):
    def test_minimal_registered_surface_passes(self) -> None:
        self.assertEqual(verifier.validate_paths(valid_surface()), [])

    def test_missing_file_fails_even_when_both_editions_match(self) -> None:
        paths = valid_surface()
        relative = "cloud/outbox/README.md"
        for edition in verifier.EDITIONS:
            paths.remove(f"{edition}/{relative}")
        findings = verifier.validate_paths(paths)
        self.assertTrue(any("missing required files" in row for row in findings))

    def test_cross_edition_path_drift_fails(self) -> None:
        paths = valid_surface()
        relative = "main/40_course/_templates/course/_exam/index.md.template"
        paths.remove(f"en/{relative}")
        findings = verifier.validate_paths(paths)
        self.assertTrue(any("edition path sets differ" in row for row in findings))

    def test_instance_ledger_in_skeleton_fails(self) -> None:
        paths = valid_surface()
        paths.add("zh/main/30_group/recommendations.md")
        findings = verifier.validate_paths(paths)
        self.assertTrue(any("forbidden instance files" in row for row in findings))

    def test_historical_invited_grant_in_current_editions_fails(self) -> None:
        paths = valid_surface()
        for edition in verifier.EDITIONS:
            paths.add(f"{edition}/INVITED_USE_GRANT.md")
        findings = verifier.validate_paths(paths)
        self.assertTrue(any("forbidden instance files" in row for row in findings))

    def test_unregistered_root_file_fails(self) -> None:
        paths = valid_surface()
        paths.add("mystery.txt")
        findings = verifier.validate_paths(paths)
        self.assertTrue(any("unregistered files" in row for row in findings))

    def test_root_governance_markers_are_mandatory(self) -> None:
        complete = "\n".join(verifier.ROOT_AGENTS_MARKERS)
        self.assertEqual(verifier.validate_root_agents(complete), [])
        findings = verifier.validate_root_agents("stopped_budget token")
        self.assertTrue(findings)


if __name__ == "__main__":
    unittest.main(verbosity=2)
