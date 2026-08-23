# T2AG cloud synchronization state (skeleton template)

> This file stores synchronization protocol metadata only; it stores no course progress and no teaching content.
> The sole source of truth for course progress is still each course's `progress.md`.

- protocol_version: T2AG-CLOUD-1
- privacy_model: two_scope
- existing_project_scope: current_personal_instance_user_uploaded
- automatic_sync_allowlist_status: approved_minimal_low_risk
- automatic_sync_allowlist: course_code, lesson_id, stable_node_ids, exact_stop, rule_version, internal_role_template_ids, non_content_state_summary
- current_cloud_project_mode: generic_skeleton
- cloud_bridge_status: paused
- cloud_bridge_pause_reason: uninitialized_skeleton
- cloud_bridge_resume_condition: instance_initialized_and_user_confirms_resume
- current_base_state_id: UNINITIALIZED
- current_base_exported_at: —
- last_synced_session_id: —
- last_change_directive_id: —
- last_change_directive_status: —
- last_cloud_handoff_id: —
- last_cloud_handoff_status: —

## Processed sessions

| session_id | closed_at | course | result | local_record | note |
|---|---|---|---|---|---|

## Component change directives

| directive_id | created_at | affected_components | status | send_evidence | note |
|---|---|---|---|---|---|

## Cloud handoffs

| handoff_id | directive_id | produced_at | local_decision | local_verification | note |
|---|---|---|---|---|---|

## Maintenance rules

1. When a new `t2ag_mobile_entry.md` is generated, assign that local snapshot a unique `base_state_id` and update this file in step.
2. Before importing a cloud session-close block, search this table and the local course records for the `session_id`, so nothing is written back twice.
3. Append `synced` only after the import is complete and doctor reports `0 FAIL`; a duplicate block is recorded as `duplicate`, and an unadjudicated conflict as `conflict`.
4. Automatic synchronization uses only the minimal low-risk allowlist in this file; nothing may be synchronized before the Skeleton is instantiated.
5. When a local component update affects the cloud, save the change directive in `outbox/` first; without send evidence the status must never be written as `sent`.
6. A handoff returned by the cloud is saved verbatim into `inbox/` first, and only after discussion with the user is accepted / partial / rejected recorded;
   a handoff must never modify a local rule on its own.
7. A formal directive block at `ready_to_send` is immutable; when it is stale or wrong, create a new directive and declare `supersedes`.
