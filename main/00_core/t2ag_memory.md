# T2AG 跨会话记忆索引（短版缓存）

> 启动时优先读取；只保存恢复所需指针、摘要和行动检查。
> 详细规则下沉到 `50_playbook/`，系统历史见 `t2ag_changelog.md`，问题历史见 `t2ag_problemlog.md`。
> 最后更新：—

---

## 上次课摘要  [max 12]

- **日期**：—
- **学到哪**：—
- **卡在哪**：—
- **学生状态**：—
- **下次第一件事**：—

## 当前状态指针  [max 20]

| 项目 | 当前值 | 详情位置 |
|---|---|---|
| 活跃课程组 | — | 首次启动后创建 |
| 活跃 lesson | — | — |
| 当前教师 | — | 首次启动后配置 |
| 当前学生 | S001 | `10_case/students/S001/`（模板） |
| R 活跃绑定 | — | `25_general/_README.md` |
| T2AG 版本 | 0.1.2 | `t2ag.md` 顶部 |

> 课程进度以各课程 `course_status.md` 为唯一真相源；本表只缓存恢复指针。

## 记忆治理与下一次教学前检查  [max 18]

1. 先读当前状态指针，确认课程、lesson、页码、学生和教师。
2. 若存在约定的交接索引，按 `handoff_management.md` 只读匹配当前任务的 active 交接；无匹配即跳过，交接不覆盖真相源。
3. 有课程组先读 `20_groups/Gxx.md`，再读对应 `course_status.md`。
4. 讲新内容前读教材当前页与 working_pages 缓存，逐节确认，不跳页。
5. 重复流程先查 `50_playbook/`；相似历史问题按索引展开 `t2ag_problemlog.md`。
6. 读 `student_info.md` 与当前学生四文件；处理练习/复测时按需读 `reasoning_patterns.md`。
7. 按 `mistake_retest.md` 做近期/远期覆盖、活跃知识点和陈年反刍；结课按 `session_close.md` 写回。
8. 环境可执行代码则跑 `70_tools/t2ag_doctor.py`。

## 关键决策索引  [max 12]

| 主题 | 关键词 | 位置 |
|---|---|---|
| 学生档案路由 | 四文件、证据门槛 | `10_case/student_info.md` |
| 知识点掌握 | 2+8+1、maintenance、aged | `50_playbook/mistake_retest.md` |
| 陈年复习日历 | 3-1-3=6 学习日、关联闭合、跨日连对 2 次 | `50_playbook/mistake_retest.md` |
| 发行同步 | core-playbook 三版本 SHA-256 一致 | `50_playbook/playbook_management.md` |
| 交接上下文 | active/scope 路由、最小充分上下文、真相源核对 | `50_playbook/handoff_management.md` |
| 环境惰性 | 不自动重建 venv / 安装依赖 / 下载模型 | `50_playbook/project_verification.md` |
| 路径命名 | 稳定 ID、snake_case、working_pages | `50_playbook/naming_conventions.md` |
| 卷面考核 | 真题选编、隔离池、补考 | `50_playbook/exam_protocol.md` |

## 最近变更摘要  [max 8]

1. **[2026-07-23]** v0.1.2 第二阶段：完整 Markdown 对象分层迁移结构契约与空骨架——新增 7 类对象目标目录、领域契约、命名规范、三版 README、doctor 物理位置检查+引用完整性、state_refresh 双路径读取（main+skeleton）。尚未迁移任何实例。
2. **[2026-07-20]** v0.1.2：生命周期与容量组合分离，建立 checkpoint/completion 两级进度、确定性缓存刷新、路径注册表、handoff 老化与云端双范围。
3. **[2026-07-17]** v0.1.1：lessonXX 进度行纳入结课写回，新增课中手动存档规则。
4. **[2026-07-17]** v0.1.1：句尾改为字面标记 `md.imurs`；教材窗口增加物理页/OCR/校对/course_status 一致性 doctor 门。
5. **[2026-07-16]** v0.1.1：云端项目确认为 `personal_instance`，加入 S002 / `TR01→T003` 只读身份路由与 skeleton 隔离。

## 最近问题摘要  [max 8]

1. （骨架为空）
