# T2AG 云端桥接目录

> **这里放什么**：本地和云端（手机/网页版）之间的桥接文件——提示词、同步状态、交接件。
> **谁写・谁读**：云端同步时写入；本地接管时读取。
> **什么时候来这里**：手机端学了东西要同步回本地，或本地要推送变更给云端。

本目录保存云端运行提示词和双向同步凭证，不替代 `main/` 中的任何课程或规则真相源。

```text
cloud/
├── T2AG_PROJECT_INSTRUCTIONS.txt
├── cloud_sync_state.md
├── outbox/   # 本地发给云端的部件变更指令
└── inbox/    # 云端返回、等待本地讨论的交接文件
```

## 两条同步通道

- 教学状态：云端输出 `T2AG_SESSION_CLOSE`，本地校验并写回课程文件。
- 部件变更：本地输出 `T2AG_CLOUD_CHANGE_DIRECTIVE`，云端修改或提案后返回
  `T2AG_CLOUD_HANDOFF`，本地与用户讨论后裁决。

指令文件状态为 `ready_to_send` 不等于已经发送；必须有上传工具证据或用户确认才能标为 `sent`。
云端交接始终从 `proposed_for_local_review` 开始，不自动成为本地规则。

首轮建立或修改同步架构时发送三项：协议定义源 `cloud_learning_sync.md`、Project Instructions
执行投影和对应 `CD-*.md` 指令。普通教学只使用 Project Instructions 与既有项目资料，不必每课重传协议。
