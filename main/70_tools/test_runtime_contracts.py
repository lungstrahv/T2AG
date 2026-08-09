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
    contracts.test_checkpoint_projection_uses_table_not_frontmatter,
    contracts.test_checkpoint_projection_is_fail_closed,
    contracts.test_checkpoint_projection_scope_is_narrow,
    contracts.test_replace_frontmatter_fields_is_byte_preserving,
    contracts.test_skin_art,
    contracts.test_handoff_assertion_without_source_is_reported,
    contracts.test_handoff_assertion_with_source_is_accepted,
    contracts.test_handoff_assertion_scan_skips_structure_only,
    contracts.test_handoff_required_context_layers_are_enforced,
    contracts.test_handoff_active_lane_absence_contradiction_is_enforced,
    contracts.test_handoff_index_version_drift_is_enforced,
    contracts.test_handoff_shadow_runtime_index_is_enforced,
    contracts.test_resume_authorization_gate_is_enforced,
    contracts.test_environment_probes_report_broken_assumptions,
    contracts.test_environment_probes_silent_when_assumptions_hold,
    contracts.test_environment_registry_must_exist_and_list_every_probe,
    contracts.test_git_unlink_probe_leaves_no_residue,
    contracts.test_git_unlink_probe_residue_is_bounded,
    contracts.test_changelog_anchor_mismatch_warns_with_both_values,
    contracts.test_changelog_missing_anchor_block_warns,
    contracts.test_changelog_stale_evidence_warns_with_title_and_claim,
    contracts.test_memory_budget_over_limit_warns_with_both_numbers,
    contracts.test_memory_budget_missing_markers_warns,
    contracts.test_memory_budget_within_limit_is_silent,
    contracts.test_memory_budget_counts_only_its_own_section,
    contracts.test_changelog_runner_matches_grep_line_semantics,
    contracts.test_changelog_runner_reports_unusable_pattern_as_not_evaluable,
    contracts.test_changelog_matching_anchors_and_evidence_are_silent,
    contracts.test_changelog_pure_functions_mutation_is_killed,
    contracts.test_gate_ledger_missing_transition_row_warns,
    contracts.test_gate_ledger_missing_pageturn_row_warns,
    contracts.test_gate_ledger_placeholder_authorization_warns,
    contracts.test_gate_ledger_duplicate_row_id_warns,
    contracts.test_gate_ledger_missing_review_closure_warns,
    contracts.test_gate_ledger_hint_without_authorization_row_warns,
    contracts.test_gate_ledger_malformed_table_fail_closed,
    contracts.test_gate_ledger_complete_ledger_is_silent,
    contracts.test_gate_ledger_carrier_without_section_is_skipped,
    contracts.test_gate_ledger_blocks_before_anchor_are_exempt,
    contracts.test_gate_ledger_pure_functions_mutation_is_killed,
)


if __name__ == "__main__":
    raise SystemExit(contracts.run_contract_tests(TESTS, suite_name="runtime_contracts"))
