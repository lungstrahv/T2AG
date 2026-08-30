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
    └── exerciseNN/
        ├── exercise.md      # Exercise 主载体与精确停点
        ├── problems.md      # 稳定题目及本单元顺序
        ├── attempts/        # 学生原始提交
        └── reviews/         # 逐次反馈
└── activity_ledger.md       # 0.2.2+ Activity 生命周期唯一真相源
└── activity_map.md          # ContentGroup ↔ Lesson/Exercise 结构（按需）
```

- Lesson 与 Exercise 是 Course 内近乎同级的 LearningActivity；任何一方都不拥有另一方。
- Exercise 不是 Lesson 的附属 Session；canonical 目录/ID 为 `exerciseNN`（至少两位）。
  旧 `Udddd` 仅作 legacy alias，**禁止新建**。
- ContentGroup 按教材知识内容连接两类活动。课程根 `activity_map.md` 管理连接，但不改变
  二者的同级关系。合法 `binding_status: unbound` 须空 `content_group_ids` + 非空 reason。
- **分权（0.2.2）**：
  - `activity_ledger.md`：`truth_scope: activity_lifecycle`（ALE/CLR/alias/stats/课程偏好覆盖）
  - `progress.md`：`truth_scope: course_lifecycle,course_frontend,activity_position`
  - 活动主文件删除人工 `status`；不得再把 Activity lifecycle 写回 progress 或主文件。
- `progress.md` 使用唯一前台 `current_activity` / `current_activity_id` / `resume_path` /
  `activity_position` 与结构化 `next_action_kind|type|id`。`current_lesson` 在 active 契约中
  **退役**。全课程只有一个前台；`ongoing+pending_close` 容量为 Lesson≤3、Exercise≤2。
- 消费者必须从同一次 progress 读取建立不可变 `ProgressSnapshot`；统一活动路由返回
  `activity_position`。不得用第二次读取补齐路由字段，避免并发教学写回产生跨版本状态。
- Exercise 不得声明 `lesson_id(s)` 或 Session 所有权字段，也不得恢复已否决的
  `sessions/ExerciseSession` 对象。
- 教材驱动 Exercise 的已校对题源属于 Course/ContentGroup，必须放在持久
  `book/` 域并由 `problems.md` 以 registry artifact、路径、定位和 SHA 显式引用。
  路径解析后仍须位于本 Course `book/`，不得经过 symlink、junction 或 reparse point；
  problems、registry、题源 frontmatter 与原文档 path/SHA 必须形成同一身份链。
  `working_pages/` 路径已在 0.2.2 批 S3 退役，历史摘录见各课 `archive/`。

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

### 2.1 学生可选提示闸门

`10_student/profile/profile.md` 的 `exercise_hint_gate: enabled | disabled` 是学生是否
启用可执行提示闸门的唯一持久设置。未初始化 Skeleton 使用 `ask`，首次启动必须让学生
选择后才能改为 `initialized`；学生之后可随时改选，改选不抹除既有帮助暴露。

闸门只管理 Exercise 教学回复，不声称仅靠提示词形成不可绕过的安全边界：

- `reasoning_feedback`：只检查学生已经写出的命题、对象与推理，不新增解题对象、子目标、
  引理、构造或下一步；
- `concept_answer`：只回答学生明确提出的概念，不把概念桥接回当前题，不生成题目专属的
  子目标、引理或关键步骤；回答后回到提问前的精确停点；
- `direction_hint / specified_reference / full_solution`：分别要求学生显式授权
  `direction / reference / solution`，教师不能根据“似乎卡住”自行升级；
- 新 Attempt 保存创建时的 gate 快照与最高帮助暴露；概念问答本身不升级帮助等级，未经
  授权泄露关键结构时标记教师提示污染，不能计作学生独立掌握或学生错误。

回复前检查由只读 `70_tools/t2ag_hint_gate.py` 给出 allow/deny 与范围约束。若产品层需要
硬阻断，必须由模型外部的响应中介消费 deny 返回码；Doctor 和 Markdown 契约只能验证、
审计与防回归，不能诚实地宣称自己能拦截所有未来模型输出。

<!-- rule: TEACH-MAP-001 -->
### 2.2 多块长篇讲解的地图优先协议

当一次讲解预计同时包含三个以上概念块，或符号会在数字、函数、集合、函数集合等多个
对象层级间切换时，先给导航，再进入推导：

1. 用短目录或树形图标明目标、主要分支、依赖关系和本轮只展开的分支。
2. 在首次出现时标注关键符号的对象类型；同一符号族跨层使用时给出简短类型表。
<!-- rule: TEACH-MAP-002 -->
3. 一次只深入一个分支；完成该分支后等待学生确认、复述或追问，再进入下一支。
4. 总览只承担导航功能，不能把全部细节压缩成另一种形式一次性倾倒。
<!-- rule: TEACH-MAP-003 -->
5. 概念讲授或学生已授权完整讲解时，总览可以展示证明或实现路线；新 Exercise 的
   未授权阶段仍受开题零提示与提示闸门约束，不得借目录、思维树或类型表泄露方法、
   子目标、关键变形或答案。无法在不泄露的前提下制作有用总览时，宁可省略总览。

地图不是理解确认。学生仍须对当前分支明确表示理解或继续，系统不能因已经展示全局
结构就跨过确认门。

### 2.3 消息记录路由

本节是消息记录路由的**唯一 owner**。学生每发一条消息，教师按下列顺序判断成分并
**当轮**落盘；一条消息可命中多行，每行独立写入。记录是追加，不是判断。

Lesson 与 Exercise 共用同一判断骨架，但「哪几行改变课程真相源」不同，因此分两个变体表；
模板与实例载体只保留指向本节的指针，不得复制表正文（防两份正文漂移）。

#### Lesson 变体

只有第 1 行改变课程真相源，须理解确认门真正闭合才写；第 2–6 行无需授权、不等课后。

| # | 消息成分 | 去向 | 说明 |
|---|---|---|---|
| 1 | 理解确认的回答 | `progress.md` | 答对翻 checkpoint confirmed + 更新精确停点 + 教学记录一条（含答对要点）；答错不翻 checkpoint |
| 2 | 学生原创表述（顿悟、自造模型、新得概念） | `lesson_thoughts.md` | 学生原话与教师回应分栏，不混写；有跨课价值再挂 `10_student/profile/reasoning_patterns.md` |
| 3 | 疑问 | `question_bank.md` | 当场答完 → answered；推迟 → open + 备注 |
| 4 | 知识性错误 | `mistake_bank.md` | 根因标签 + 迁移预警；判为回滑则在 `progress.md` 挂复核项 |
| 5 | 学习感受（审美、卡点、状态、元认知） | 课堂原话进 `lesson_thoughts.md`；达提炼门上收 `10_student/profile/course_reflections.md`；哲学/人生/长期情绪进 `10_student/profile/profile.md` 个体性格基调节 | 提炼门见本契约 §三；纯「没问题」并入当轮闭合记录，不单列 |
| 6 | 流程/系统问题或建议 | 课程层进 `progress.md` 教学记录；系统层进 `t2ag_problemlog.md` | |
| 7 | 继续授权 | `progress.md` 精确停点 | 一次性，用后即失效 |
| 8 | 闲聊/题外话 | 不记 | — |

不另存：教师讲解正文（教材原文在 source assets，块覆盖状态在 lesson 主载体与
`lesson_map.md`）；理解确认题干（在 checkpoint 表）。

#### Exercise 变体

只有第 1–2 行改变课程真相源，须按 Exercise 状态机真实发生后才写；第 3–7 行无需授权、
不等课后。

| # | 消息成分 | 去向 | 说明 |
|---|---|---|---|
| 1 | 正式作答 | `attempts/ATdddd/attempt.md` + exercise 主载体状态与精确停点 | 一次作答一份编号 Attempt；写入时机由结构定死 |
| 2 | 作答后的教师反馈与判定 | `reviews/RVdddd.md` | 与 Attempt 一一对应 |
| 3 | 学生原创表述（顿悟、自造模型、新得概念） | Attempt 内保留原话 + `exercises/exercise_thoughts.md` 索引 | 学生原话与教师回应分栏；有跨课价值再挂 `10_student/profile/reasoning_patterns.md` |
| 4 | 疑问 / 概念提问 | `question_bank.md`；涉及当前 Exercise 的走提示闸门 | 当场答完 → answered；推迟 → open + 备注；提示级别按授权记入 Attempt frontmatter |
| 5 | 知识性错误 | `mistake_bank.md` | 根因标签 + 迁移预警；进入复测周期 |
| 6 | 学习感受（审美、卡点、状态、元认知） | 原话进 Attempt / `exercise_thoughts.md`；达提炼门上收 `10_student/profile/course_reflections.md`；哲学/人生/长期情绪进 `10_student/profile/profile.md` 个体性格基调节 | 提炼门见本契约 §三；纯「没问题」并入当轮闭合记录，不单列 |
| 7 | 流程/系统问题或建议 | 课程层进 `progress.md` 教学记录；系统层进 `t2ag_problemlog.md` | |
| 8 | 继续授权 | exercise 主载体精确停点 | 一次性，用后即失效 |
| 9 | 闲聊/题外话 | 不记 | — |

不另存：教师讲解与提示正文（题面在 `problems.md`，证据指针在 exercise 主载体
「证据索引」）。

### 2.4 门台账（教学门留痕）

> 起源：P-0054「宣布不等于交接」与三次同门失效（P-0014/P-0041/P-0054）。对话层的门
> 此前只活在散文里，跳过不留痕；本节把**过门**变成**落行**，使 doctor
> （`runtime.gate_ledger`，WARN 级）第一次够得着教学门。GL-1 施工单：
> `docs/design/T2AG_GATE_LEDGER_WORKORDER_DRAFT_2026-08-08.md`。

**边界（先说清它不是什么）**：门台账是**留痕投影，不是第二真相源**。块/活动生命周期
真相仍归 `progress.md` checkpoint 表与 `activity_ledger.md`（§1.2 分权不变）；台账与
真相源冲突时以真相源为准，台账缺行 = 留痕违规，不 = 状态错误。它与 §2.3 行 7/8
（继续授权 → 精确停点，一次性用后即失效）的关系：停点记**当前授权态**，台账记**历史行**。

**载体与锚**：Lesson / Exercise 主载体各持有一节 `## 门台账`，首行锚：

```
ledger_since: <ISO 日期> | 起算块: <checkpoint ID>        （Lesson）
ledger_since: <ISO 日期> | 起算证据: RVdddd/ATdddd        （Exercise）
```

锚用 ID 不用日期做 join（checkpoint 表无日期列）；doctor 只对锚**之后**的
confirmed 行 / 新证据生效——**向前生效，历史不补写、不检查**。

**行式**（七列，追加式，历史行不改，写错追加更正行并指向被更正行 ID）：

```
| 行ID | 块ID | 门类型 | 闭合依据 | 感受回应 | 授权原文 | 消费于 |
```

- `行ID`：`GT-NNNN`，载体内单调递增，不跨载体编号。
- `授权原文`：**学生逐字引语 + 时刻**（如 `"继续"(21:14)`）。留痕不防捏造，防的是
  发现延迟：配合课堂 footer，伪造引语 = 当轮当面撒谎；偷懒不写行 = 文件层可查缺行。
- 纯「没问题」类回应照 §2.3 既有约定并入当轮行，不单列。

**落件义务（门类型枚举）**：

| 变体 | 门类型 | 何时落行 | `消费于` 写什么 |
|---|---|---|---|
| Lesson | `开场确认` | 概览 + 知识树 + 路线感受后，学生授权进入第一块 | 第一块 checkpoint ID |
| Lesson | `块过渡` | §1.6 三门闭合、学生授权进入下一块 | 下一块 checkpoint ID |
| Lesson | `翻页` | 旧页清单 → 宣布「PDF N / 书内 M」→ 新页树 → 单独授权 | 新页首块 ID（`块ID` 列写 `PDF N→N+1`） |
| Lesson | `结课确认` | session close 学生确认 | `close` |
| Exercise | `开题` | 只给题面、保留独立尝试 | 题号（如 `Q005`） |
| Exercise | `提示授权(级别)` | 学生显式授权某级提示（§2.1） | 对应 `ATdddd`；`闭合依据` 填学生逐字请求 |
| Exercise | `题目闭环` | 讲解/复盘后感受与疑问门闭合 | 对应 `RVdddd` |
| Exercise | `下一题授权` | 学生授权进入下一题 | 下一题号 |
| Exercise | `结课确认` | 同 Lesson | `close` |

**课堂 footer（派生规则）**：每轮教学回复末尾固定一行，内容必须可从台账末行 +
progress 停点派生，不得凭空声称：

```
⛩ 块: <当前块> | 门: <开着的门/等待什么> | 本轮授权: <未消费/已消费于X> | 页: PDF N/书内 M
```

Exercise 变体：`块`→`题`，`页`→`提示: 当前已授出级别`。行首符号与字段顺序学生可改；
改样式属 V0。

**doctor 检查范围（如实声明）**：`runtime.gate_ledger` 只实现确定性子集——
`000` 表损坏 fail-closed、`001` 锚后相邻 confirmed 块缺块过渡行、`002` 页码变化处缺
翻页行、`003` 授权原文空/占位、`004` 行ID 重复或非递增、`005` 锚后新 RV 缺题目闭环行、
`006` Attempt frontmatter 高级提示缺提示授权行、`007` 当前教材 Lesson 整节缺失
`## 门台账`。`开场确认`/`结课确认`/`下一题授权`
目前只是契约义务，机器未检查。WARN 逐条指名载体与块/题 ID。

2026-08-10 更新（学生裁决，随检验体系施工）：

- `001` 判定语义为**出行有痕 + 入行有痕**：a→b 过门由「a 有块过渡出行」加「b 有块过渡
  入行」共同满足，允许中途经过树外/学生主导分支节点（宪法 §4 允许的绕行不再误报）。
- checkpoint 表接受两种确定形制：带 `checkpoint_id`/`状态` 表头的表（`页码` 可缺，
  goal-driver 课程合法无页）与无表头 `-B-P-N` 六列旧形制。
- **历史载体**无本节 → 跳过（部署过渡期不变）；但**当前教材 Lesson**（progress 指向的
  `current_activity`）缺整节 → `007`，**FAIL 级**：散文门失去唯一机器落点时不得宣称闭合。
  完整性缺行仍为 WARN，不打断课中。

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
| 消息记录路由（Lesson / Exercise 两个变体表） | `00_core/learning_activity_model.md` §2.3 |
| 门台账留痕与课堂 footer（Lesson / Exercise 两个变体） | `00_core/learning_activity_model.md` §2.4；检查 `runtime.gate_ledger` |
| 课程稳定教学约束 | `40_course/<COURSE_ID>/course.md` |
| ContentGroup 与活动关系 | `40_course/<COURSE_ID>/activity_map.md` |
| 当前活动与精确停点 | `40_course/<COURSE_ID>/progress.md` |
| Lesson 正文 | `lessons/lessonNN/lessonNN.md` |
| Exercise 正文 | `exercises/exerciseNN/exercise.md` |
| 教材题源 | Course `book/` 内持久 verified excerpt；不得放在临时缓存路径 |
| 题目、提交与反馈 | `problems.md` / `attempts/` / `reviews/` |
| 初始化材料 | `40_course/_templates/course/` |
| 运行步骤 | `50_playbook/new_course_init.md`、`lesson_recover.md`、`exercise_evidence.md`、`session_close.md` |
