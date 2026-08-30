#!/usr/bin/env python3
"""Historical migration compatibility tests; run only for affected migrations."""
from __future__ import annotations

import contract_test_support as contracts


TESTS = (
    contracts.test_profile_migration_roundtrip,
)


if __name__ == "__main__":
    raise SystemExit(contracts.run_contract_tests(TESTS, suite_name="legacy_migrations"))
