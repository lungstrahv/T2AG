# T2AG 云端同步状态（skeleton 模板）

> 本文件只保存同步协议元数据，不保存课程进度或教学内容。
> 课程进度唯一真相源仍是各课程 `course_status.md`。

- protocol_version: T2AG-CLOUD-1
- privacy_model: two_scope
- existing_project_scope: current_personal_instance_user_uploaded
- automatic_sync_allowlist_status: approved_minimal_low_risk
- automatic_sync_allowlist: course_code, lesson_id, stable_node_ids, exact_stop, rule_version, internal_role_template_ids, non_content_state_summary
- current_cloud_project_mode: generic_skeleton
- current_base_state_id: UNINITIALIZED
- current_base_exported_at: —
- last_synced_session_id: —
- last_change_directive_id: —
- last_change_directive_status: —
- last_cloud_handoff_id: —
- last_cloud_handoff_status: —

## 已处理会话

| session_id | closed_at | course | result | local_record | note |
|---|---|---|---|---|---|

## 部件变更指令

| directive_id | created_at | affected_components | status | send_evidence | note |
|---|---|---|---|---|---|

## 云端交接

| handoff_id | directive_id | produced_at | local_decision | local_verification | note |
|---|---|---|---|---|---|

## 维护规则

1. 生成新的 `t2ag_mobile_entry.md` 时，为该本地快照分配唯一 `base_state_id`，同步更新本文件。
2. 导入云端结课块前，先检索本表和本地课程记录中的 `session_id`，避免重复写回。
3. 导入完成且 doctor 为 `0 FAIL` 后追加 `synced`；重复块记 `duplicate`；未裁决冲突记 `conflict`。
4. 自动同步只使用本文件的最小低风险 allowlist；用户已上传内容仅限当前个人实例使用。
5. 本地部件更新影响云端时，先在 `outbox/` 保存变更指令；没有发送证据不得把状态写成 `sent`。
6. 云端返回的交接先原样保存到 `inbox/`，经用户讨论后再记录 accepted / partial / rejected；
   交接本身不得自动修改本地规则。
7. `ready_to_send` 的正式指令块不可改写；过时或有误时新建指令并声明 supersedes。
