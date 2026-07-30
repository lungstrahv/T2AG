# 课程内习题证据闭环

**保护级别**：core-playbook

> 本流程定义 0.2.0 的最小 ExerciseProblem → Attempt → Review 闭环。它不建立
> KnowledgePoint、OCR 确认状态机或跨课程 AbilitySummary；这些候选能力延期到
> 三轮真实 Attempt/Review 形成后的 0.2.1 设计裁决。

## 一、规则边界、活动连接与身份

- Exercise 的系统对象与共同学习回路由 `00_core/learning_activity_model.md` 定义；本文件
  只负责 ExerciseProblem → Attempt → Review 的运行程序。`activity_map.md` 保存课程内
  ContentGroup 连接；`exercises/<EXERCISE_ID>/exercise.md` 是活动主载体，`problems.md`
  只保存题目、来源和本单元执行路线。
- 禁止把通用 schema、全课程顺序策略或 Lesson–Exercise 连接总表塞进单个 Unit；Unit
  可以声明本单元为何重排，但不能成为管理其他 Unit 的规则源。

教材课程第一次建立 Lesson 或 ExerciseUnit 时创建课程级活动图：

```text
40_course/<COURSE_ID>/
  activity_map.md            # ContentGroup 与 Lesson/Exercise 的课程级连接真相源
  lessons/lessonNN/lessonNN.md
  exercises/<UNIT_ID>/
```

`activity_map.md` 必须包含“内容组连接表”，每行至少有：

```markdown
| content_group_id | source_scope | lesson_ids | exercise_ids |
|---|---|---|---|
| COURSE123-B001-C01-S01 | B001 / 第1章 / §1 | lesson01 | U0001 |
```

- ContentGroup 是教材知识连接点，不是课堂或题目。
- Lesson 与 Exercise 是 Course 内同级 LearningActivity；任何一方都不拥有另一方。
- `lesson_ids` 与 `exercise_ids` 多值时用逗号分隔；没有对应活动时写 `—`。
- 连接表是关系真相源；Lesson 与 Exercise 只声明自身 ContentGroup，并与表一致。任何
  悬空、重复登记或 ContentGroup 漂移均为 FAIL。同一单元格不得重复写同一活动；
  每个已存在的 Lesson/Exercise 都必须至少登记一次，空 `content_group_ids` 不能作为
  漏登豁免。
- Exercise 不得声明 `lesson_id(s)`、Session 引用等所有权字段；不得创建
  `sessions/` 或 `exercise_session` 对象。

第一次出现学生明确表达的习题想法后，课程级增加汇总索引；没有真实想法时不创建空文件：

```text
40_course/<COURSE_ID>/exercises/
  exercise_thoughts.md       # 跨 Unit 汇总索引；原话仍在 Attempt
```

```text
40_course/<COURSE_ID>/exercises/<UNIT_ID>/
  exercise.md
  problems.md
  attempts/
    AT0001/
      attempt.md
      assets/          # image/mixed 模式必需
  reviews/
    RV0001.md
```

- `UNIT_ID`：课程内 `Udddd`。
- 教材驱动 Exercise 的 `exercise.md` 必须声明 `exercise_id` 与 `content_group_ids`；
  `problems.md` 必须声明同一 `exercise_id` 与唯一 `content_group_id`，并以
  `source_artifact_id / source_path / source_locator / source_sha256` 指向 Course
  `book/` 内的持久校对题源。Lesson 与 Exercise
  目录物理分开，只通过活动图归属教材知识组。
- `source_path` 与题源内的 `source_document` 必须是 canonical POSIX 相对路径，解析后
  仍位于同一 Course `book/`，且路径链不得经过 symlink、junction 或 reparse point。
  `problems.source_artifact_id`、active registry canonical、题源 `artifact_id` 必须相同，
  双侧 `source_locator` 必须一致；题源摘要与原文档摘要都必须为实际 SHA-256。Lite
  有意省略原教材二进制时，必须由已哈希绑定的 migration manifest 精确证明 path + SHA。
- 教材驱动单元每道题的依赖字段必须完整写成
  ``- 依赖 completion node：`<content_group_id>-N<数字>` ``。反引号、完整 canonical ID
  与当前 `content_group_id` 三者缺一不可，且完整 ID 必须真实存在于该课程
  `progress.md` 的 `Completion nodes` 表。空值、伪造值、无法解析、同组伪节点或指向另一
  内容组均为 FAIL。
- 活动教材习题单元必须同时声明：
  - `source_order`：教材原始顺序，必须覆盖全部 problem ID 且不得重排题面；
  - `teaching_sequence`：当前执行顺序，必须与题目集合相同且不得重复；未作特别设计时
    等于 `source_order`；
  - `sequence_rationale`：偏离教材顺序时说明先修关系或学生证据。
- 教学时一次只处理 `teaching_sequence` 中最早未闭合题；题内疑问和订正未闭合不得跳到
  下一题。路线可因新证据调整，但须在 `problems.md`、`exercise.md` 与 progress 同步
  记录，不得跨
  `content_group_id` 偷跑。
- `problem_id`：课程内 `<UNIT_ID>-Qddd`。
- `attempt_id`：单元内 `ATdddd`；一次 Attempt 是一次真实提交批次，可以包含多题。
- `review_id`：单元内 `RVdddd`；避免与 Binding 的 `RNNN` 冲突。
- 完整身份是 `course_id / unit_id / local_id`；局部编号只在所属单元内分配且不复用。

没有真实提交时只保留 `_README.md`，不得创建空的 AT/RV 实例来通过检查。

## 二、Attempt schema

`attempts/AT0001/attempt.md`：

```markdown
---
type: exercise_attempt
course_id: COURSE123
exercise_id: U0001
attempt_id: AT0001
problem_ids: [U0001-Q001, U0001-Q002]
mode: mixed
status: submitted
created: 2026-07-26
---
# AT0001 作答

## 作答上下文

- 使用帮助：none

## U0001-Q001

- 作答：见正文；若答案只存在于原图，写“见原始图片”，不得伪造转写。

### 学生想法（可选）

- 原话：仅记录学生明确说出的解题体会、联想或策略；没有则省略本节。

## U0001-Q002

- 作答：...

## 原始证据

- `assets/page01.png`：学生提交原图
```

约束：

- `mode` 仅为 `text / image / mixed`；image/mixed 必须保留至少一个原始图片文件。
- `status` 仅为 `submitted / withdrawn`。第一次真实提交才创建 AT 目录。
- 图片是原始证据；人工转写必须标明来源，OCR 结果不能覆盖或替换原图。
- “学生想法”是 Attempt 内的可选一手证据，必须来自学生明确表达并尽量保留原话；
  教师不得根据答案自行补写。缺少学生想法不是证据缺失，不生成空占位。
- 教师对想法的解释、评价或规范化写在 Review 的“思路观察/学生想法回应”，不得覆盖
  Attempt 原话；跨题重复至少两次且确有迁移性时，才可升级到 `reasoning_patterns.md`。
- 课程级 `exercises/exercise_thoughts.md` 只保存来源链接、短摘、标签和未来使用方式；
  以 `Unit / Attempt / Problem` 来源元组去重，不复制完整作答，不成为第二原话源。
- 汇总中的“学生原话短摘”必须是可回查的直接引文；模型概括只能标成“教师提炼”。
  学生自我修正与教师补充分别署名，不得合并成看似由学生完整提出的结论。
- 本版不记录 OCR confidence 或学生转写确认状态；不得用空字段假装该能力已实现。
- 每个 `problem_id` 必须存在于同单元 `problems.md`，正文须有对应二级标题和作答项。

## 三、Review schema

`reviews/RV0001.md`：

```markdown
---
type: exercise_review
course_id: COURSE123
exercise_id: U0001
review_id: RV0001
attempt_id: AT0001
problem_ids: [U0001-Q001, U0001-Q002]
reviewer: teacher
status: recorded
reviewed: 2026-07-26
---
# RV0001 批改

## U0001-Q001

- 结果：correct
- 思路观察：...
- 学生想法回应：...（仅当 Attempt 存在学生想法时使用）
- 反馈：...
- mistake_refs：[]
- question_refs：[]
```

- `reviewer` 仅为 `teacher / student / joint`；`status` 仅为 `recorded / amended`。
- 每题结果仅为 `correct / partial / incorrect / unresolved`。
- Review 必须引用真实存在的 Attempt，且题目集合必须来自该 Attempt。
- Review 只记录本次证据；跨题重复至少两次后才可升级到 `reasoning_patterns.md`。

## 四、session close 写回

1. 进入 Exercise 时先创建或恢复 `exercise.md`；它保存当前题目、精确停点和证据指针，
   不复制原始作答。
2. 学生提交后创建一个批次级 Attempt；同一批次的多张图片放在同一 `assets/`；学生
   明确表达解题体会时，在对应题目下追加“学生想法”原话。
3. 批改后创建 Review，逐题记录结果、思路观察和反馈。
4. 明确知识错误写入或合并 mistake bank，并在 Review 写 `mistake_refs`。
5. 未闭合疑问写入 question bank，并在 Review 写 `question_refs`。
6. 更新 `problems.md` 的状态和错误级别；不得从 Review 反向复制题面。教材题面只能
   由其持久题源校对后投影；不得读取历史 Lesson 的 `working_pages/` 作为运行依赖。
7. 跨题重复模式达到证据门槛后才更新 reasoning patterns。
8. 更新 `exercise.md` 的精确停点与证据指针，再更新 progress；Lesson 与 Exercise 各写
   自己的学习记录，不互相充当正文。
9. 最后执行 state refresh 与 doctor。

## 五、习题想法汇总

第一次出现真实学生想法时创建：

```markdown
---
type: exercise_thought_index
course_id: COURSE123
updated: 2026-07-26
---
# COURSE123 习题想法

> 本文件是汇总索引；学生原话以所链接 Attempt 为准。

## U0001 / AT0001 / U0001-Q001 / 2026-07-26

- 来源：`U0001/attempts/AT0001/attempt.md`
- 学生原话短摘：...
- 教师提炼：...
- 索引标签：...
- 后续使用：...
- 推理模式：未升级 / `RP-xxxx`
```

- lesson 内由讲授触发的原始灵感仍放 `lessons/lessonXX/lesson_thoughts.md`；习题作答触发的
  想法先放 Attempt，再汇总到本文件。
- 课程体验、节奏、课程感受以及从 lesson/exercise 提炼出的核心内容思考写
  `10_student/course_reflections.md`；生活、哲学、情绪与
  长期元认知写 `10_student/profile.md`；跨题稳定解题模式写 `reasoning_patterns.md`。
- 核心内容思考的提炼门：学生明确标记重要，或内容连接 lesson 与 exercise、连接两个
  以上知识节点、能够指导后续学习中的任一项成立。提炼条目必须回链局部来源；普通局部
  火花继续留在各自文件，不为凑数量上收。
- 恢复习题时读取与当前 Unit/知识点相关的近期条目；“后续使用”必须落到提示、反例、
  复测或方法迁移之一，不能只收藏不消费。

## 六、doctor 契约

- 校验 U/题目/AT/RV ID、文件名、frontmatter 和引用闭合。
- 校验 Skeleton 初始化模板，以及 `activity_map.md`、Lesson、Exercise 的同级连接；活动
  悬空、表格单元内重复、漏登或 ContentGroup 漂移均为 FAIL。
- 拒绝 Lesson/Exercise 互相持有所有权，以及退役 `sessions/ExerciseSession` 结构。
- image/mixed Attempt 缺原图为 FAIL。
- Attempt 引用未知题目、Review 引用未知 Attempt 或题目越界均为 FAIL。
- Review 缺逐题结果或结果枚举非法为 FAIL。
- Skeleton 只携带本 schema，不携带真实 AT/RV 实例。
