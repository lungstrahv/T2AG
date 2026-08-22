# 云端交接收件箱

将云端返回的 `CH-YYYYMMDD-NNNN.md` 原样保存到本目录。

- 收到不等于接受；初始状态必须是 `proposed_for_local_review`。
- 先核对来源 `directive_id`、实际修改、偏差、验证、未决问题和隐私影响。
- 与用户讨论后，才能把接受的部分写入本地并运行 doctor。
- 不改写云端原始交接；本地裁决记录在 `../cloud_sync_state.md`。

