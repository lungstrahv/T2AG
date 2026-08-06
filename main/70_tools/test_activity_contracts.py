#!/usr/bin/env python3
"""Contracts for durable learning activities, evidence, and executable routes."""
from __future__ import annotations

import contract_test_support as contracts


TESTS = (
    contracts.test_exercise_first_course_resume,
    contracts.test_exercise_current_lesson_driver_matrix,
    contracts.test_planned_activity_fields_rejected,
    contracts.test_working_pages_activity_matrix,
    contracts.test_course_activity_templates,
    contracts.test_hint_gate_contract,
    contracts.test_exercise_evidence,
    contracts.test_exercise_activity_links,
    contracts.test_project_completion_evidence,
    contracts.test_project_completion_step_summary_required,
    contracts.test_textbook_dependency_contract,
    contracts.test_persistent_exercise_source_contract,
    contracts.test_activity_map_strict_bidirectionality,
    contracts.test_activity_map_duplicate_and_complete_coverage,
    contracts.test_retired_exercise_ownership_and_sessions,
    contracts.test_lesson_retired_ownership_all_drivers,
    contracts.test_activity_workflows_share_executable_route,
    contracts.test_activity_cli_disk_roundtrip,
)


if __name__ == "__main__":
    raise SystemExit(contracts.run_contract_tests(TESTS, suite_name="activity_contracts"))
