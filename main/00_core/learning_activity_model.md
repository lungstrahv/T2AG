# T2AG 课程学习活动模型

**保护级别**：core-contract

> 本契约是 Lesson 与 Exercise 的结构权威，必须随 Main、Skeleton、Lite 一起发行。
> Playbook 只能说明如何运行这些对象，不能代替对象、模板或初始化能力。

## 一、课程内的两个同级学习空间

```text
Course
├── lessons/                 # 讲授、阅读、示例、提问与确认
│   └── lessonNN/
│       ├── lessonNN.md      # Lesson 主载体
│       └── lesson_thoughts.md（有真实想法时惰性创建）
└── exercises/               # 学生持续做题、提交、反馈、订正与复测
    ├── exercise_thoughts.md（有真实想法时惰性创建的课程级索引）
    └── Udddd/
        ├── exercise.md      # Exercise 主载体与精确停点
        ├── problems.md      # 稳定题目及本单元顺序
        ├── attempts/        # 学生原始提交
        └── reviews/         # 逐次反馈
```

- Lesson 与 Exercise 是 Course 内近乎同级的 LearningActivity；任何一方都不拥有另一方。
- Exercise 不是 Lesson 的附属 Session；`Udddd` 目录本身就是一个 Exercise 学习单元。
- ContentGroup 按教材知识内容连接两类活动。课程根 `activity_map.md` 管理连接，但不改变
  二者的同级关系。
- `progress.md` 使用 `current_activity: lesson | exercise`、`current_activity_id`、
  `activity_position` 与 canonical `resume_path` 指向当前活动；ongoing 课程必须显式
  填写这些字段，不得从
  `current_lesson` 默认补值。首个活动可以是 Exercise，此时不要求预造 Lesson。
  `progress.md` 仍是当前停点唯一真相源。
- 消费者必须从同一次 progress 读取建立不可变 `ProgressSnapshot`；统一活动路由返回
  `activity_position`。不得用第二次读取补齐路由字段，避免并发教学写回产生跨版本状态。
- `current_lesson` 仅是兼容上下文字段：当前活动为 Lesson 时必须与
  `current_activity_id` 相同；当前活动为 Exercise 时只能写 `none` / `—`，或指向真实
  存在且 frontmatter 匹配的历史 Lesson。状态刷新器不得据此推断显式活动；无 Lesson
  时 GENERATED 的“Lesson 上下文”必须显示“无”且路径为 `—`；历史 Lesson 必须明确
  标成“历史兼容”，不得与“当前教学活动”并列称为活跃。
- Exercise 不得声明 `lesson_id(s)` 或 Session 所有权字段，也不得恢复已否决的
  `sessions/ExerciseSession` 对象。
- 教材驱动 Exercise 的已校对题源属于 Course/ContentGroup，必须放在持久
  `book/` 域并由 `problems.md` 以 registry artifact、路径、定位和 SHA 显式引用。
  路径解析后仍须位于本 Course `book/`，不得经过 symlink、junction 或 reparse point；
  problems、registry、题源 frontmatter 与原文档 path/SHA 必须形成同一身份链。
  `working_pages/` 只是 Lesson 可清理缓存，不能作为 Exercise 的 active canonical。

### 1.1 状态与默认路由矩阵

| 状态 | 显式活动字段 | Lesson 上下文 | 默认恢复/结课主载体 | working pages |
|---|---|---|---|---|
| `planned` | 不存在 | `none` | 不可恢复或结课 | 跳过 |
| ongoing + Lesson | 完整且互相一致 | 当前 Lesson | 当前 Lesson | 仅 textbook Lesson 校验 |
| ongoing + Exercise-first | 完整且互相一致 | `none` / `—` | 当前 Exercise | 跳过 |
| ongoing + Exercise + 历史 Lesson | 完整且互相一致 | 真实历史 Lesson | 当前 Exercise；历史 Lesson 默认只读且不写 | 跳过 |

活动路由由只读 `70_tools/t2ag_activity.py` 机械解析。恢复、结课、状态刷新与 Doctor
必须消费同一显式活动契约；不得分别实现“猜当前载体”的后备规则。

## 二、共同学习回路

Lesson 与 Exercise 都执行同一骨架：

1. 从 `progress.md` 恢复当前活动和精确停点。
2. 读取该活动所属 ContentGroup 的教材、近期问题、错误和已保存想法。
3. 每次只推进一个可确认步骤。
4. 保存学生真实表达；教师的规范化与判断分开署名。
5. 疑问进入 question bank，明确错误进入 mistake bank。
6. 更新当前活动主载体与 `progress.md`，再刷新 GENERATED 状态。
7. 学生确认后继续；未闭合问题不得被换活动掩盖。

Lesson 的主要证据是讲授记录、提问与确认；Exercise 的主要证据是
ExerciseProblem → Attempt → Review → 订正/复测。证据形态不同，不改变二者同为
LearningActivity。

## 三、想法复利回路

学生在任一活动明确表达想法时才启动，不预造内容：

```text
学生原话
  → Lesson: lesson_thoughts.md
    或 Exercise: Attempt + exercises/exercise_thoughts.md 索引
  → 满足提炼门时进入 course_reflections.md
  → 后续相关 Lesson / Exercise 恢复时主动读取并用于提示、反例、迁移或复测
  → 新作答与新想法形成下一轮证据
```

- 学生原话、教师补充和教师提炼必须分栏，不得混写。
- 普通局部想法不强制上收；跨活动连接、学生明确标记重要或能指导后续学习时才提炼。
- `course_reflections.md` 不是终点；条目必须带来源和后续使用方式，恢复时必须实际消费。

## 四、做题驱动的系统改进回路

真实 Exercise 既服务学习，也为系统机制提供设计证据：

```text
持续做题
  → 暴露新需求/摩擦/边界案例
  → 记录 problemlog 或候选路线图
  → 分离事实、模型推断与需求本身
  → 与学生裁决
  → 更新 Core 契约 / Playbook / Tool / Template
  → 同步 Skeleton
  → 负例与真实下一轮验证
```

- 单次需求先解决当前学习，不急于抽象成系统对象。
- 稳定机制不能只写在某门课、某个 `Udddd` 或一次对话里；必须进入 Skeleton 自带的
  Core、模板和可执行检查。
- Skeleton 不携带真实学生和课程实例，但必须携带创建 Course、Lesson、Exercise 及其
  复利回路所需的完整模板与规则。

## 五、权威分工

| 内容 | 权威载体 |
|---|---|
| Lesson / Exercise 对象与共同回路 | `00_core/learning_activity_model.md` |
| 课程稳定教学约束 | `40_course/<COURSE_ID>/course.md` |
| ContentGroup 与活动关系 | `40_course/<COURSE_ID>/activity_map.md` |
| 当前活动与精确停点 | `40_course/<COURSE_ID>/progress.md` |
| Lesson 正文 | `lessons/lessonNN/lessonNN.md` |
| Exercise 正文 | `exercises/Udddd/exercise.md` |
| 教材题源 | Course `book/` 内持久 verified excerpt；不得放在 `working_pages/` |
| 题目、提交与反馈 | `problems.md` / `attempts/` / `reviews/` |
| 初始化材料 | `40_course/_templates/course/` |
| 运行步骤 | `50_playbook/new_course_init.md`、`lesson_recover.md`、`exercise_evidence.md`、`session_close.md` |
