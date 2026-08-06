#!/usr/bin/env python3
"""Fast contracts for local runtime, routing, profile, teacher, and skin state."""
from __future__ import annotations

import contract_test_support as contracts


TESTS = (
    contracts.test_profile_placeholder,
    contracts.test_profile_container_contract,
    contracts.test_resume_path,
    contracts.test_explicit_activity_pointer_required,
    contracts.test_progress_identity_is_shared,
    contracts.test_teacher_mapping_is_strict,
    contracts.test_teacher_presentation_contract,
    contracts.test_state_refresh_activity_roundtrip,
    contracts.test_skin_art,
)


if __name__ == "__main__":
    raise SystemExit(contracts.run_contract_tests(TESTS, suite_name="runtime_contracts"))
