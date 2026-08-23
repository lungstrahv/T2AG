#!/usr/bin/env python3
"""Release-candidate contracts; excluded from ordinary fast validation."""
from __future__ import annotations

import contract_test_support as contracts


TESTS = (
    contracts.test_fixture_mutations_cannot_silently_noop,
    contracts.test_flow_and_offline_guide,
    contracts.test_offline_guide_version_drift_is_enforced,
    contracts.test_skeleton_package_surface_is_enforced,
    contracts.test_release_package_surface_severity_split,
    contracts.test_candidate_replay_isolation_contract,
    contracts.test_cross_edition_parity_r1_numbering_styles_are_silent,
    contracts.test_cross_edition_parity_r2_identifier_fork_fails,
    contracts.test_cross_edition_parity_r3_section_fork_fails,
    contracts.test_cross_edition_parity_r4_debt_reports_info_then_goes_stale,
    contracts.test_cross_edition_parity_r5_unreadable_source_fails_loudly,
    contracts.test_cross_edition_parity_r6_peer_resolution_is_symmetric,
    contracts.test_init_example_payload_is_documented_and_rejected,
)


if __name__ == "__main__":
    raise SystemExit(contracts.run_contract_tests(TESTS, suite_name="release_contracts"))
