# T2AG 0.2.1 Domain Model

## 1. Student

当前仓库就是一个学生实例。Student 拥有 profile、learning path、reasoning
patterns、reflections、activities 与 engagements；不再存在 Case、SN 路由或
`students/<id>/` 包装层。

权威：

- 身份与执行参数：`10_student/profile/profile.md`
- 课程清单缓存：`10_student/profile/learning_path.md`
- 解题模式：`10_student/profile/reasoning_patterns.md`
- 课程感想与课程核心内容思考：`10_student/profile/course_reflections.md`

## 2. Course

Course 是课程定义和当前实例进度的唯一聚合根：

```text
40_course/<COURSE_ID>/
  course.md       # 稳定内容、教材、教学约束
  progress.md     # 当前进度唯一真相源
  lessons/
  exercises/
  mistake_bank.md
  question_bank.md
  book/
```

`course.md` 不保存当前学生停点；`progress.md` 不复制全册课程方案。进度节点必须
并入 progress 的“进度节点”节，不建立第二份进度载体。

### 2.1 ContentGroup / Lesson / Exercise

- Lesson 与 Exercise 是 Course 内近乎同级的 LearningActivity：前者以讲授、阅读、示例
  和确认推进，后者以持续做题、提交、反馈、订正和复测推进；任何一方都不拥有另一方。
- `lessons/lessonNN/lessonNN.md` 是 Lesson 主载体；`exercises/Udddd/exercise.md` 是
  Exercise 主载体，`problems.md`、Attempt 与 Review 是它的题目和证据结构。
- ContentGroup 按 `Book → 章 → 节/知识组` 连接两类活动。课程级 `activity_map.md` 是
  连接真相源；叶子只声明自身 ContentGroup，不互相持有所有权指针。
- `progress.md` 的 `current_activity / current_activity_id / resume_path /
  activity_position` 指向唯一当前 Lesson 或 Exercise；`current_lesson` 只保存 Lesson
  上下文。完整共同回路与 Skeleton 发行契约见 `learning_activity_model.md`。
- ExerciseUnit 同时区分 `source_order` 与 `teaching_sequence`：前者忠实保存教材题号
  顺序，后者保存当前教学执行路线。教学路线可按先修依赖与学生真实证据调整，但不改题号，
  不跨内容组，且必须记录调整理由。
- lesson/exercise 局部想法保留上下文；具有章节主线、跨活动连接或后续复用价值的核心
  内容思考，再提炼进 `10_student/profile/course_reflections.md`，并保留局部来源指针。
- 汇总条目必须区分证据归属：学生明确说出的内容写“学生原话/学生自我修正”，教师的
  形式化、扩展和解释写“教师补充/教师提炼”；两者可以相邻，但不得混写成共同原话。

### 2.2 ExerciseProblem / Attempt / Review

- ExerciseProblem 是 `exercises/<UNIT_ID>/problems.md` 中的稳定题目条目；教材仍是来源，
  不复制题目建立第二个题库。
- Attempt 是一次真实提交批次，可以包含多道题与多张原始图片；载体为
  `attempts/ATdddd/attempt.md`，完整身份由 Course、Unit 与局部 Attempt ID 组成。
- 学生想法是 Attempt 内可选的一手证据：只保存学生本人明确表达的解题体会、联想或
  策略，不由教师推断代写，也不建立独立稳定 ID。
- Review 是对一个 Attempt 的逐题批改与当次思路观察；载体为 `reviews/RVdddd.md`。
- “学生想法”属于 Attempt；“思路观察”属于 Review。前者是学生原话，后者是教师判断，
  两者不得互相覆盖。一次学生想法不自动成为 ReasoningPattern。
- `exercises/exercise_thoughts.md` 是课程内跨单元的习题想法汇总索引，不是新的原话
  真相源。它以 `Unit / Attempt / Problem` 来源元组去重，保存短摘、索引标签与后续用途；
  原话仍以 Attempt 为准。
- Review 只引用 mistake/question/reasoning 证据，不拥有这些反馈台账。
- `profile.md` 的 `exercise_hint_gate` 保存学生是否启用提示闸门；启用时，回复意图先由
  `t2ag_hint_gate.py` 检查。概念问答只答所问概念，不自动应用到当前题；方向、资料与
  完整讲解分别需要学生显式授权。Attempt 保存 gate 快照和最高帮助暴露，但不把概念
  问答或教师越级提示冒充学生独立证据。
- KnowledgePoint、OCR 确认链与 AbilitySummary 尚未成为 0.2.0 活动对象。

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
