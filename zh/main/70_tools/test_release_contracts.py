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
    contracts.test_constitution_parity_r1_section_drift_fails,
    contracts.test_constitution_parity_r2_stale_exemption_warns,
    contracts.test_constitution_parity_r3_section_set_fork_fails,
    contracts.test_constitution_parity_r4_exempt_fork_and_clean_are_silent,
)


if __name__ == "__main__":
    raise SystemExit(contracts.run_contract_tests(TESTS, suite_name="release_contracts"))
