#!/usr/bin/env python3
"""Release-candidate contracts; excluded from ordinary fast validation."""
from __future__ import annotations

import contract_test_support as contracts


TESTS = (
    contracts.test_fixture_mutations_cannot_silently_noop,
    contracts.test_flow_and_offline_guide,
    contracts.test_candidate_replay_isolation_contract,
)


if __name__ == "__main__":
    raise SystemExit(contracts.run_contract_tests(TESTS, suite_name="release_contracts"))
