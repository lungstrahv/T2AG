# T2AG 0.2.3 跨会话记忆索引

> Skeleton 空实例缓存。首次启动前不得填入真实学生、课程或 group。

## 节预算与下沉

本文件每次启动都要读。**预算是行数**，写成各节标题后的 `[max N]`，doctor
`runtime.memory_budget` **从本文件读取**该标记，不硬编码——调预算是这里一行编辑，
不需要改代码、不需要走批次。被门守住的是**机制**，不是数值。

超限时**下沉最旧的条目**，并在原位留一行**墓碑**注明去向：

```markdown
- D-001 ~ D-011 已下沉 → `t2ag_changelog.md` [2026-07-26] ~ [2026-07-27]（YYYY-MM-DD 下沉）
```

**下沉不是删除**：条目正文本就在 changelog / problemlog 里，memory 只留指针。
**删行必须注明去向**。

下面三节是空模板脚手架：**标题与 `[max N]` 预留，内容从首次启动后自然生长**。
不要因为它们是空的就删掉标记——删了预算机制在这个实例上就永不生效。

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
| T2AG 版本 | 0.2.3 | `main/t2ag.md` |
| Cloud bridge | paused | `cloud/cloud_sync_state.md` |
<!-- T2AG_GENERATED:STATE_POINTERS:END -->

## 下一次教学前检查  [max 30]

- —（首次启动后填写）

## 最近关键决策  [max 100]

- —（首次启动后填写；超限按「节预算与下沉」下沉最旧条目并留墓碑）

## 最近问题摘要  [max 50]

- —（首次启动后填写；正文在 `t2ag_problemlog.md`，本节只留指针）

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
- 当前版本为 0.2.3；Course progress 与 activity ledger 已分权，Skeleton 提供空 ledger、
  exerciseNN、原子 lifecycle/close 和 recover 通用能力，但不携带真实迁移或结课实例。
- 0.2.1 收口候选已提供 reading ActivityRecord 空容器、六份 JSON schema 和双方各写各仓的
  context/contribution/receipt saga；Skeleton 不含真实 AR、书籍、sidecar 或 receipt。
- EV-0012 通用能力：Course `source_assets` + `.cache/source_pages` + Lesson
  Map/Snapshot/pointer/Context 契约已落地；playbook 不再把 `working_pages` 当作新建权威输出。
  Skeleton 只含通用契约与空模板，不携带 MATH1607H、学生或其他实例数据。见 changelog
  `[2026-08-05] EV-0012 教材页资产与 Lesson Preparation 技术收口`。
