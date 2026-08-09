# T2AG 0.2.3 Domain Model

## 1. Student

当前仓库就是一个学生实例。Student 拥有 profile、learning path、reasoning
patterns、reflections、activities 与 engagements；不再存在 Case、SN 路由或
`students/<id>/` 包装层。

权威：

- 身份与执行参数：`10_student/profile/profile.md`
- 课程清单缓存：`10_student/profile/learning_path.md`
- 解题模式：`10_student/profile/reasoning_patterns.md`
- 课程感想与课程核心内容思考：`10_student/profile/course_reflections.md`
- Agent 协作偏好：`10_student/profile/profile.md` 的
  `agent_collaboration_schema / agent_pool_limit / agent_max_active / agent_parallel_startup /
  agent_startup_readiness / agent_background_reporting`。它只表达学生允许的最大计算拓扑、
  启动就绪策略与后台播报偏好。`agent_pool_limit` 是含 Main 的可保留身份池容量；
  `agent_max_active` 是含 Main 的同时运行上限。完成态释放并发槽但仍可复用，不是写权限、
  terminal lifecycle 或 RT3 授权。

## 2. Course

Course 是课程定义和当前实例进度的唯一聚合根：

```text
40_course/<COURSE_ID>/
  course.md       # 稳定内容、教材、教学约束
  progress.md     # Course 生命周期、唯一前台与精确停点
  activity_ledger.md # Activity 生命周期、pending/CLR、alias、统计
  activity_map.md # ContentGroup ↔ Lesson/Exercise 结构
  lessons/
  exercises/
  mistake_bank.md
  question_bank.md
  book/
```

`course.md` 不保存当前学生停点；`progress.md` 不复制全册课程方案，也不拥有
LearningActivity 生命周期。Course 生命周期/前台/停点与 Activity 生命周期分别由
`progress.md`、`activity_ledger.md` 拥有，不得用“最后写入者”覆盖冲突。

### 2.0 两根正交轴：`course_type` 与 `default_driver`

- **`course_type` = 完成语义**：什么证据能把这门课关到 completed（**停止条件**）。
- **`default_driver` = 推进依据**：什么决定下一课教什么（**排序函数**）。两者回答不同问题，**正交、可独立取值**；四值定义与来源规则由 `book_management.md` §三 拥有。

`course_type` 三值的区别在**裁判是谁**：

| 值 | 裁判 | 可复现 | 关课证据 | 权威 |
|---|---|---|---|---|
| `mastery` | 系统内：师生确认门 | — | 逐块理解闭合、无悬空疑问 | 确认门机制（全课通用） |
| `project` | 系统外，可复现判定 | 是 | 每个里程碑绑验证模式 A/B/B-K 并满足三机制 | `project_verification.md` §〇 |
| `praxis` | 系统外，开放世界后果 | 否 | 真实行动入口 + 行为证据束 | `book_management.md` §三 |

**「有产物」不是 `project` 的判据**——mastery 课也可有产物，产物是理解的证据；`project` 要求产物被**不听解释的外部裁判**判定（现实运行 / OJ 评测机 / Kaggle 私榜）。`praxis` 与 `project` 同在系统外，区别是其裁判**不可复现**，故须携带免责声明。

### 2.1 ContentGroup / Lesson / Exercise

- Lesson 与 Exercise 是 Course 内近乎同级的 LearningActivity：前者以讲授、阅读、示例
  和确认推进，后者以持续做题、提交、反馈、订正和复测推进；任何一方都不拥有另一方。
- `lessons/lessonNN/lessonNN.md` 是 Lesson 主载体；`exercises/exerciseNN/exercise.md` 是
  Exercise 主载体，`problems.md`、Attempt 与 Review 是它的题目和证据结构。
- ContentGroup 按 `Book → 章 → 节/知识组` 连接两类活动。课程级 `activity_map.md` 是
  连接真相源；叶子只声明自身 ContentGroup，不互相持有所有权指针。
- `progress.md` 的 `current_activity / current_activity_id / resume_path /
  activity_position` 指向唯一前台 Lesson 或 Exercise；`current_lesson` 已从 active 契约
  退役，历史 Lesson 上下文由 ledger 事件和 ContentGroup 关系解析。完整共同回路与
  Skeleton 发行契约见 `learning_activity_model.md`。
- ExerciseUnit 同时区分 `source_order` 与 `teaching_sequence`：前者忠实保存教材题号
  顺序，后者保存当前教学执行路线。教学路线可按先修依赖与学生真实证据调整，但不改题号，
  不跨内容组，且必须记录调整理由。
- lesson/exercise 局部想法保留上下文；具有章节主线、跨活动连接或后续复用价值的核心
  内容思考，再提炼进 `10_student/profile/course_reflections.md`，并保留局部来源指针。
- 汇总条目必须区分证据归属：学生明确说出的内容写“学生原话/学生自我修正”，教师的
  形式化、扩展和解释写“教师补充/教师提炼”；两者可以相邻，但不得混写成共同原话。

### 2.2 ExerciseProblem / Attempt / Review

- ExerciseProblem 是 `exercises/<EXERCISE_ID>/problems.md` 中的稳定题目条目；教材仍是来源，
  不复制题目建立第二个题库。
- Attempt 是一次真实提交批次，可以包含多道题与多张原始图片；载体为
  `attempts/ATdddd/attempt.md`，完整身份由 Course、Unit 与局部 Attempt ID 组成。
- 学生想法是 Attempt 内可选的一手证据：只保存学生本人明确表达的解题体会、联想或
  策略，不由教师推断代写，也不建立独立稳定 ID。
- Review 是对一个 Attempt 的逐题批改与当次思路观察；载体为 `reviews/RVdddd.md`。
- “学生想法”属于 Attempt；“思路观察”属于 Review。前者是学生原话，后者是教师判断，
  两者不得互相覆盖。一次学生想法不自动成为 ReasoningPattern。
- `exercises/exercise_thoughts.md` 是课程内跨 Exercise 的习题想法汇总索引，不是新的原话
  真相源。它以 `Exercise / Attempt / Problem` 来源元组去重，保存短摘、索引标签与后续用途；
  原话仍以 Attempt 为准。
- Review 只引用 mistake/question/reasoning 证据，不拥有这些反馈台账。
- `profile.md` 的 `exercise_hint_gate` 保存学生是否启用提示闸门；启用时，回复意图先由
  `t2ag_hint_gate.py` 检查。概念问答只答所问概念，不自动应用到当前题；方向、资料与
  完整讲解分别需要学生显式授权。Attempt 保存 gate 快照和最高帮助暴露，但不把概念
  问答或教师越级提示冒充学生独立证据。
- KnowledgePoint 与 AbilitySummary 尚未成为 0.2.0 活动对象。OCR 核验是
  SourcePageAsset 的来源证据，不是独立的 LearningActivity 或学生 mastery。

### 2.3 Textbook source and lesson preparation

教材原文证据由 Course/Book 持久持有，Lesson 只持有消费范围、导航和备课收据；同一页资产
可被多个 Lesson 引用，但任何 Lesson 的进度、Snapshot 或学生学习证据都不得共享。

- **SourceDocument**：Course/Book 持有的原版教材文档及其版本，是教材原文的最终权威；它不因
  Lesson 关闭而失效。
- **SourcePageAsset**：某一 SourceDocument 版本中一个物理页的持久逻辑资产，锚定其原文定位、
  OCR 与核验来源证据；“已核验”不等于学生已学习或已掌握。
- **LessonScope**：Lesson 拥有的版本化、不可变的有序页资产集，是该版本必须消费的范围真相。
  正常文档为包含当前页的连续 5–8 页；可用页少于 5 的短书固定为全部可用页。翻页或扩窗新建
  Scope 版本，不改写旧版本。
- **TeachingWindow**：Lesson Progress 拥有的可变运行视图，投影当前 LessonScope 的 current
  page、相对展示与驻留；它不是第二份可独立裁剪的教学范围。
- **LessonMap**：Lesson 随 Scope 版本派生的导航图，必须覆盖当前 Scope 的每个
  SourcePageAsset；不拥有 mastery、completion 或学生确认。
- **LessonPreparationSnapshot**：Lesson 拥有的不可变备课收据，绑定一个 Scope 版本、其
  LessonMap 与逐页消费收据。Scope 变化须新建 Snapshot；不原地修改旧 Snapshot，也不把它当作
  学生学习证据。

关系链为 `SourceDocument → SourcePageAsset`、`LessonScope → 有序页资产`、
`TeachingWindow → 当前 Scope 投影`、`LessonMap → Scope 全覆盖`、
`LessonPreparationSnapshot → Scope + Map + 消费收据`。

## 3. Group

Group 是容量组合，不是课程生命周期：

```text
30_group/<GID>/
  plan.md
  calendar.md
  review.md
  bindings/
```

- plan：成员、预算边界、跨课接口、激活闸门；
- calendar：可执行时间表和可判定结组阈值；
- review：循环证据、欠债处置和用户确认；
- binding：某门课程的弹性执行关系，不拥有课程正文或进度。

组外课程可以保持 ongoing；加入或退出 group 不自动改变课程 lifecycle。

## 4. Teacher

`20_teacher/T00X.md` 是稳定模板，`20_teacher/overlay.md` 是当前学生和课程的
显式覆盖。overlay 可以改变语气、入口、节奏和反馈频率，不得改变事实标准、
课程必学内容或学生确认门。

- **TR01**：由 `t2ag_state_refresh.py` 生成、`t2ag_doctor.py` 校验的教师身份
  事实标准。语义定义：`overlay.md` §教师事实标准。GENERATED 字面量，不可手写。
  格式：`"TR01 → {teacher_id}"`。

## 5. ActivityRecord

ActivityRecord 保存低治理、可暂停、尚未升级为正式课程的活动：

- ID：`AR-NNNN`
- 路径：`10_student/activities/<activity_kind>/AR-NNNN_Title.md`
- `activity_kind` 由受控 registry 决定；0.2.1 初始只登记 `reading`
- 不拥有课程进度；升级后只保存指向 Course 的链接和历史记录。

## 6. Engagement

Engagement 保存持续现实实践和证据：

- ID：`EG-NNNN`
- 载体：`10_student/engagements/EG-NNNN_Title/engagement.md`
- 必填：`type`、`engagement_id`、`status`、`governance`
- `governance: external` 时必须有 `governance_source`
- evidence 只保存证据索引，不成为外部纪律或事实源的替代品。

## 7. State and feedback ledgers

- memory / learning path：从原件生成的缓存；
- mistake bank：知识错误存量；
- question bank：疑问存量，状态 `open / answered / closed`；
- problemlog：系统问题流量台账，提炼到 playbook 后结算；
- changelog / journal：纯追加历史，不进入 retire loop；
- trade journal：T2AG 学习和过程证据，不拥有 Trading-OS 纪律或成交事实。

## 8. Registry

`70_tools/artifact_registry.json` 保存稳定 artifact ID：

- active：canonical 必须存在且全局唯一；
- tombstone：旧 composite 或被 survivor 吸收的 artifact，必须有
  `successors` 或 `alias_to`；
- archived：可读取的历史原文，不参与 active 路由；
- redirects：只追加且必须一跳到 canonical、tombstone 或 archive 记录。

## 9. Invariants

1. `main/` 只有九个编号域，另允许 `bin/`。
2. 旧 0.1.x active 域不得复活。
3. 每门实例课程至多一个 `course.md` 和一个 `progress.md`。
4. 恰有一个 active group；Skeleton 可为零。
5. active group 的课程成员必须存在，planned/completed/dropped 课程不得被误作 active 容量。
6. 稳定 ID 在迁移后不因改名重造。
7. GENERATED 缓存不得领先或覆盖真相源。
8. Lite 只从 Main 派生；Skeleton 不含真实实例数据。
9. Attempt 引用的题目必须属于同单元；Review 必须引用真实 Attempt，且不得越过
   Attempt 的题目集合。
10. 教材课程的 Lesson/Exercise 连接必须由课程级 `activity_map.md` 管理；两类活动叶子
    的 ContentGroup 声明必须与表一致，且引用不得悬空。
11. Main、Skeleton、Lite 必须携带同一套 Course/Lesson/Exercise 初始化模板；Skeleton
    不含真实实例，但不能缺少创建和运行两类活动所需的系统能力。
