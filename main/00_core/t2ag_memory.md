# T2AG 0.2.1 跨会话记忆索引

> Skeleton 空实例缓存。首次启动前不得填入真实学生、课程或 group。

## 上次课摘要

<!-- T2AG_GENERATED:ACTIVE_PROGRESS:START -->
- **日期**：—
- **学到哪**：—
- **当前完成节点**：`—`
- **当前 checkpoint**：`—`（—）
- **来源**：local
- **下次第一件事**：—
<!-- T2AG_GENERATED:ACTIVE_PROGRESS:END -->

- **学生状态**：—

## 当前状态指针

<!-- T2AG_GENERATED:STATE_POINTERS:START -->
| 项目 | 当前值 | 详情位置 |
|---|---|---|
| 活跃课程组 | — | 首次启动后创建 |
| 当前课程 | — | 首次启动后创建 |
| Lesson 上下文 | 无 | — |
| 当前教学活动 | —: — | — |
| 当前教师 | — | `main/20_teacher/overlay.md` |
| 学生档案 | uninitialized | `main/10_student/profile/profile.md` |
| active binding | 无 | 首次启动后创建 |
| T2AG 版本 | 0.2.1 | `main/t2ag.md` |
| Cloud bridge | paused | `cloud/cloud_sync_state.md` |
<!-- T2AG_GENERATED:STATE_POINTERS:END -->

## 启动提示

1. 读取 `main/10_student/profile/profile.md`。
2. profile 未初始化或仍含必填占位符时，执行 `main/50_playbook/first_run.md`。
3. 不创建、删除、重建或升级 `.venv`。

## 当前治理摘要

- 默认施工模式为 `independent_batch`；只有用户批准冻结、列举且会失效的 authorization
  envelope，才启用 `version_campaign`。
- campaign 只覆盖 envelope 中列明的 RT1/RT2 单元与有限本地 checkpoint；RT3 必须在精确对象
  和正文可见后单独授权。
- evidence/recovery checkpoint 都不是 release snapshot；首次候选完整独立复审与有界
  finalization delta 独立复审均通过后，才能指认正式本地版本边界。
- 当前运行版本仍为 0.2.1；0.2.2 Activity Close amendment 只改变未来调度，不实施 0.2.2。
- 0.2.1 收口候选已提供 reading ActivityRecord 空容器、六份 JSON schema 和双方各写各仓的
  context/contribution/receipt saga；Skeleton 不含真实 AR、书籍、sidecar 或 receipt。
