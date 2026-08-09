# 跨会话恢复课程上下文流程

**保护级别**：core-playbook

> 本文件是 T2AG「技能固化」文档之一。
> 当学生在新对话中说「继续学 XXX」时，按本流程恢复上次教学上下文，包括进度、教材原文、情绪状态。
>
> **适用场景**：新对话中恢复某门课程的教学上下文。
>
> **路径解析约定**：本流程中“对应课程”固定解析到
> `main/40_course/<COURSE_ID>/`。不得用英文标题或中文显示名猜目录。
>
> **关联文件**：
> - 规则定义：`main/t2ag.md` →「日常接管」
> - 课程列表：`main/10_student/profile/learning_path.md` 的 GENERATED 课程索引
> - 课程状态：对应课程 `progress.md` →「当前进度」
> - 当前活动：由 progress 的 `current_activity / current_activity_id / resume_path` 唯一确定
> - Lesson 笔记：仅在当前活动为 Lesson 时读取 `lessons/lessonXX/lessonXX.md`
> - Exercise 证据：仅在当前活动为 Exercise 时读取 `exercises/exerciseNN/`
> - 课程疑问：对应课程 `question_bank.md` →「待解决 / 需要回看」
> - 课程错题库：对应课程 `mistake_bank.md`
> - 学生状态档案：`main/10_student/profile/profile.md`、`reasoning_patterns.md` 与 `course_reflections.md`
> - 教材缓存：当前活动为 Lesson 时，通过 preparation Snapshot + source_assets 交付（legacy `working_pages/` 已在 0.2.2 批 S3 退役）
> - 交接管理：`main/50_playbook/handoff_management.md` + 运行时 `<handoff_root>/README.md`
> - 自检工具：`main/70_tools/t2ag_doctor.py`

---

## 一、触发条件

满足以下任一条件，即触发跨会话恢复流程：

1. **学生说「继续学 XXX」**：如「继续学 CS1953」「继续学 MATH1607H」。
2. **学生说「读取 progress.md」**：如「读取 main/40_course/CS1953/progress.md」。
3. **学生提及课程名称或代码**：在新对话中提及某门已有课程，意图继续学习。
4. **新对话开始，学生未明确说继续但提及课程内容**：根据上下文判断是否需要恢复。

> **不触发的情况**：
> - 学生要学一门**新课程**（课程列表中不存在）→ 走「新增课程初始化流程」（见 `new_course_init.md`）。
> - 学生只是闲聊或提问，不涉及具体课程进度恢复。

---

## 二、完整步骤

默认入口先运行：

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --format markdown
```

工具成功时，步骤 1–4 说明 L0 包必须拥有的选择语义，不要求 agent 再把同一文件全文
读一遍。工具失败时才按这些步骤手工做逐段摘录；不得把降级理解成全量读取。

### 步骤 1：从 L0 恢复 memory 状态指针

默认当前课程消费 `main/00_core/t2ag_memory.md` 的「上次课摘要」与「当前状态指针」
精确摘录，确定上次课程、LearningActivity 与停点。显式请求同一 active Group 的另一门
课程时，只消费 active Group / 当前课程两条切换校验行，不把上一门课摘要混入目标课程。
组外课程必须先完成课程组切换。memory 只是缓存，不得用其中的 Lesson 指针补写 progress
缺失的显式活动字段；若与 `progress.md` 冲突，以 `progress.md` 为准。

若 memory 缺失或指针无效，停止工具化恢复并读取 learning path 的当前课程行与对应
`progress.md` 当前切片核对；不能扫描目录或按显示名称猜课程。

### 步骤 1.5：条件读取 active 课堂交接

若入口声明交接索引，或运行时存在约定的 `<handoff_root>/README.md`，按 `handoff_management.md` 检查是否有同时满足以下条件的条目：

- `status=active`
- `scope=course_session`
- `applies_to` 与当前课程/当前 LearningActivity 一致
- 上次课堂未完成 `session_close`，或正式来源存在待核对差异

命中时先读“最小状态摘要”，需要恢复用户意图、讨论演化或方案理由时再读“连续性摘要”；无匹配、已 resolved 或无关专题交接一律跳过。交接只作恢复证据，不能覆盖 `progress.md`。

若交接或当前活动显示的精确停点比 `progress.md` 更新，先暂停新内容，核对来源位置、
活动 ID 与学生确认记录，向学生确认后修复 `progress.md`，再刷新
memory/learning_path，最后继续教学。

若 `progress.md` 存在进度节点字段，同时核对当前 completion node、checkpoint 和确认状态。当前活动/云端证据可以作为
待提升证据，但不得静默覆盖真相源；经学生确认后按 `progress_tracking.md` 写回。

### 步骤 2：消费 progress.md 当前切片

L0 只摘录对应课程 `progress.md` 的完整 frontmatter 与「当前进度」节。本文件仍是该
Course 生命周期、唯一前台与精确停点的真相源。Activity 生命周期只来自 ledger；文件头应区分 `lifecycle_status` 与容量状态：Course 生命周期来自本文件，
容量状态从 active G 文件派生。

- **正在学**：当前 Lesson/Exercise、来源范围与精确停点
- **已完成**：已讲完的内容
- **已投入学习时长（小时）**：累计时长
- **下一步计划**：接下来要讲的内容

只有当前切片无法解释冲突、用户追问历史、要做正式复测或要修改掌握判断时，才进入
L2 读取对应「教学记录」与「已掌握知识点」条目；日常恢复不默认装载整段历史。

### 步骤 2.5：消费未闭合 question 摘录

L0 只摘录当前课程 `question_bank.md` 的「待解决」与「需要回看」。恢复课堂时优先处理
阻断当前进度的问题；已解答条目只在当前知识点或学生追问命中时进入 L2，不全量加载。

### 步骤 3：按 current_activity 恢复主载体

先从 `progress.md` 原样读取 `current_activity`、`current_activity_id` 与 `resume_path`。
ongoing 课程缺任一字段、ID 与类型不匹配、路径非 canonical 或目标不存在时，立即停止
恢复并修复 `progress.md` 前台契约；不得从退役的 `current_lesson`、memory 或目录扫描补值。

执行只读路由并以其结果驱动本流程后续所有活动读写：

```powershell
python -B main/70_tools/t2ag_activity.py --course <COURSE_ID> --intent recover
```

命令非零时不得继续。`primary_read` 是唯一当前活动主载体；`working_pages: null` 表示
默认恢复链必须跳过教材缓存。后文任何 Lesson/Exercise 示例都不得覆盖该路由结果。

#### `lesson` 分支

仅当 `current_activity: lesson`：

1. 要求 `current_activity_id` 为真实 `lessonNN`；active progress 不得回填 `current_lesson`；
2. L0 读取 canonical `resume_path` 的 frontmatter 与最近恢复胶囊；
3. textbook Lesson 必须在 L0 拥有与 progress 页码一致、逐页完整的当前教材窗口；缺失时
   命令非零，不得以 `ready` 推进；
4. 新对话本轮还必须按 `source_page_assets.md` §3.1（A1–A6）与 critical 的 `scope_scan`
   manifest 完成本会话 Scope 扫描；已有 Snapshot、历史 load receipt 或「仅路径/仅 SHA」
   不等于本轮 A1 消费；
5. L1 按当前停点读取 L0 尚未包含的必要教学记录、问答、错误尝试、
   completion node/checkpoint；
6. 当前 Lesson 存在 `lesson_thoughts.md` 时，按需读取相关想法。

#### `exercise` 分支

仅当 `current_activity: exercise`：

1. 要求 `current_activity_id` 为真实 `exerciseNN`；旧 `Udddd` 只能通过本课程 ledger alias 解析；
2. L0 从 canonical `resume_path` 摘录「学习范围」，从 `problems.md` 摘录当前
   ExerciseProblem 元数据；教材驱动 Exercise 同时按 registry 与 SHA 验证的
   `source_path` 只摘录当前题面；
3. 当前题已经有提交、批改或订正时，L1 才读取直接相关的 Attempt/Review；首次开题
   不预载其他题历史，更不得向学生泄露提示或答案；
4. 通过 `activity_map.md` 查找同一 ContentGroup 的上下文，不把 Exercise 解释成
   Lesson 的 Session；
5. 历史 Lesson 上下文只按 ledger 事件与 ContentGroup 关系解析，不写回 progress。
6. 从 profile 读取 `exercise_hint_gate`。值为 `enabled` 时，每次回复前运行
   `python -B main/70_tools/t2ag_hint_gate.py --course <COURSE_ID> --problem <PROBLEM_ID>
   --intent <INTENT>`；deny 时不得发送。概念问题使用 `concept_answer`，只答对应概念，
   不把概念自动应用回当前题。

Exercise 首启不得读取或构造 Lesson 路径；不写 `current_lesson`，并让
`resume_path` 直接指向 `exercises/exerciseNN/exercise.md`。历史 Lesson 的
`working_pages/` 可以全部不存在，不能影响 Exercise 恢复。

### 步骤 4：消费学生教学契约

L0 从学生档案做逐段摘录，重点关注：

- **`main/10_student/profile/profile.md`**：frontmatter、基本信息、执行参数、学习目标、辅导偏好、
  特殊要求与个体性格总纲；带日期的历史原话不默认全量读取
- **`course_reflections.md`**：读取当前课程知识点树形图和最近 3 条课程感想
- **`reasoning_patterns.md`**：处理练习、复测或跨课程迁移时，按需读取相关条目

**文件路径**：`main/10_student/`（当前学生实例）

**读取规则**：
1. 消费 L0 的 profile 教学契约，不再次全文读取
2. 排期、调参或解释个人历史时才进入 L2 展开对应 profile 原文
3. 读取 `main/10_student/profile/course_reflections.md` 中当前课程的知识点树形图和最近 3 条感想
4. 处理练习、复测或跨课程迁移时，按需读取 `main/10_student/profile/reasoning_patterns.md`；涉及替代方法训练或状态更新时，同时执行 `method_distillation.md`
5. 当前活动为 Lesson 时按需读取 `lesson_thoughts.md`；当前活动为 Exercise 时按需读取
   `exercises/exercise_thoughts.md` 及当前 Unit 的证据；同时读取
   `course_reflections.md` 中由这些局部来源提炼出的课程核心内容思考。
6. **据此调整教学语气和节奏**：
   - 若学生近期有焦虑、挫败等负面情绪 → 适当放慢节奏、多确认
   - 若学生情绪积极 → 可适当增加挑战

> **情绪状态只调整"怎么教"**：恢复上下文时，必须先确认学生状态再调整节奏，但不得降低课程标准、回避纠错或复测放水。

### 步骤 5：教材原文窗口（Snapshot-only）

默认恢复链路中，教材原文窗口 **仅在 `lesson` + `course_driver: textbook`** 分支读取。
当前活动为 Exercise 时跳过本步；goal / project / praxis Lesson 跳过教材窗口。

**当前路径（EV-0012）**：

1. 读取 **current** `LessonPreparationSnapshot`（`preparation/current_snapshot.json` 指针，
   **禁止**字典序取最后一个 `PREP-*.json`）与 `LessonMap`；
2. 按 Snapshot/Scope 加载 Course `source_assets` 页文本；页图命中 `.cache` 或按 PDF 重建；
3. 工具入口：`t2ag_source_pages.py prepare --course … --current …`（只读）与 critical 中的
   snapshot 字段。

上述三项只证明 prepared 与文本来源（不足 A1）。每个新对话首次进入 textbook Lesson 时，
Prefetcher 还必须按 `source_page_assets.md` §3.1 与 critical 的 `scope_scan` manifest 在本会话
逐页消费 Scope 完整内容本体（现行默认可观察路径见 §3.1.4），并回报：snapshot、PDF SHA、
完整 `pdf_page_index`、每页消费证据（含书内 `printed_page_label`）与冲突。相对 Scope 缺页
（A4 遗漏）或混用两种页码时停止教学。Main 不得把历史 `content_consumed=true`、receipt、
文件哈希、仅 frontmatter、或辅助 Agent 的“无需额外读取”解释成自己/本轮已经满足 A1。
完成声明仅宿主签发（A6）。

**Legacy 路径已退役**：原 `lessons/<current_activity_id>/working_pages/` 路径已在 0.2.2 批 S3 退役。
若 preparation 新路径不存在，上下文工具必须失败，**不得返回缺教材的 `ready`**。
按 `ocr_correct_flow.md` + `source_page_assets.md` 补齐后重跑。

**恢复期只读纪律**：

- 恢复链路对 `book/.cache/`、`preparation/` 与 `source_assets/` 一律只读。超配额、疑似陈旧
  或指针不一致时报告并停止，**不得自动清理**、驱逐、重命名或重建这些目录；当前 Scope 的
  P0 页更不得驱逐。清理是独立的维护动作，须由用户在明确知道删什么的前提下授权。
- 恢复过程中若发现需要写回（补页、改 Snapshot 指针、修真相源），那是另一笔动作：
  取得 **exact RT3** 授权后才执行，且授权只覆盖当轮点名的对象。恢复本身不携带写入授权，
  也不得把"为了继续上课"当作免授权理由。
- 尚未进入学习的 Lesson（ledger 无 `learning_enter`）没有 Snapshot 是正常状态，
  报告"尚未备页"即可，不得为通过检查而预造空 Snapshot 或伪造 receipt。

### 步骤 6：确认健康检查仍有效并执行开课抽查

若本会话入口已经依次通过 `t2ag_state_refresh.py --check` 与 doctor，且生成 L0 后没有
任何写入或外部变化，复用该结果，不重复运行。否则先运行 state check 再运行 doctor。
生成缓存漂移属于当前恢复阻断项：先修真相源或经确认提升证据，再用 `--write` 刷新，
不得直接手抄生成区块。

若环境可执行代码，运行：

```bash
python -B main/70_tools/t2ag_doctor.py --profile runtime
```

- 若有 FAIL：先按提示修复权威链，再开课。

#### 开课抽查预算（分档）

抽查题量由**上次课堂的内容推进量**决定（从 `progress.md` 教学记录末条的推进内容判断）：

| 上次推进量 | 抽查题数 | 构成 |
|---|---|---|
| ≤ 20 min 内容（约 1 个知识点） | 1 题 | 1 个活跃错题或知识点覆盖 |
| 20–40 min 内容（约 2–3 个知识点） | 2 题 | 1 知识点覆盖 + 1 活跃错题 |
| > 40 min 内容（约 4+ 个知识点） | 3 题 | 1 知识点覆盖 + 1 活跃错题 + 1 陈年反刍 |

- 无对应候选时跳过该类槽位，不为了凑题制造记录。
- 具体复测规则仍按 `main/50_playbook/mistake_retest.md` 执行。

#### 跳过与嵌入式切换

- 学生可以跳过抽查：发送"跳过""不做了"或类似表达即视为本次跳过，无惩罚，直接进入步骤 7。
- 在 `progress.md` 文件头记录 `spot_check_skip_streak: N`（连续跳过次数）；完成抽查则重置为 0。
- **连续 3 次跳过后**：agent 静默切换为「嵌入式确认」——不再单独出抽查题，而是在后续教学推进中自然嵌入 1–2 个确认性问题（如"这个概念和上次讲的 XXX 有什么关系？"），不标记为正式复测，不计入 mistake_bank 正式结果。
- 嵌入式确认不限制学生，学生任何时候说"我想做个复测"可恢复正式抽查。

### 步骤 7：向学生确认「上次讲到 XXX，继续?」

综合以上信息，向学生确认恢复点：

1. **简述上次进度**：Lesson 分支说明章节、教材页与具体位置；Exercise 分支说明 Unit、
   当前题目/批次与精确停点，不虚构章节或 Lesson。
2. **确认学生状态**：若 personality_baseline 或 course_reflections 显示学生近期有情绪波动，适当问候
3. **询问是否继续**：若用户本轮尚未明确要求继续，才问「从这里继续？还是想复习一下
   前面的内容？」；用户已经说“继续”时不得重复提问。
4. **权威动作与创造性补充并存**：pending checkpoint 必须逐字复用并标明 `progress.md`
   当前切片的“精确停顿点”；可以另加明确标注的概括题、暖场题、类比或模型生成的探索问题，
   但不得替换权威停点、冒充进度证据或绕过 Exercise 提示闸门。
5. **冲突即停**：route、progress、Activity、当前页 SourcePageAsset、Scope manifest 任一
   不一致时先报告冲突，不向学生展示候选教学动作。
6. **恢复课堂树**：textbook Lesson 在第一条内容前显示字符树，列出当前 PDF/书内页、
   active lesson boundary、本页教材块及各块状态。扫描完成不等于教学覆盖完成。
7. **恢复三门协议**：旧对话中的一次“继续”不跨恢复点复用；正确作答只闭合理解门。
   推导或总结之后必须再询问学生感受/疑问，并为下一个教学块取得一次性继续授权。
8. **恢复 Lesson 开场**：若当前 Lesson 尚无本次会话已展示并确认的开场，先概括本课学习
   内容，再显示 ASCII 知识树。缺少现成树时可依据 Lesson 学习范围和 LessonMap 创造性编排；
   展示后询问路线感受与是否进入第一块，不能把概览记成已讲完。

**确认示例**：

```text
上次我们讲到 MATH1607H 数学分析第 1 章 §1 集合，已经讲完了第 21 页的集合定义和表示法，第 22 页的空集、子集、集合相等、区间等**尚未讲完**。

从这里继续？还是想复习一下前面的内容？
```

> **重要规则**：在学生明确确认「继续」之前，不得跳到后续内容。即使学生问了后续相关的问题，也只能回答该问题本身，不能提前展开尚未讲授的后续内容。

进入新页时，“继续”必须在教师先展示旧页覆盖清单、宣布“翻页：PDF N / 书内 M”并展示
新页字符树之后取得。若教师已经越页但未满足这些门，新页交流只作澄清，不计正式推进；
恢复点退回最近一个完整覆盖并确认的旧页教学块。

---

## 三、展现形式选择与现场生成

> 学生始终可以提出需求，让模型换一种或者加一种展现形式，以协助其学习。学生明确提出的形式要求优先于默认判断。

| 形式 | 优点 | 局限 | 默认场景 |
|---|---|---|---|
| 原图裁切 PNG | 忠于教材、成本低 | 不易修改和交互 | 教材原图清楚可读 |
| SVG | 清晰、轻量、适合结构图 | 不适合照片与复杂纹理 | 集合图、流程图、静态关系 |
| TikZ | 数学排版严谨、可复现 | 编译和查看成本较高 | 几何、论文式数学图 |
| HTML | 可操作、可反馈、可模拟 | 需打开浏览器并维护交互 | 滑块、动画、交互测验 |

默认决策：原图可读则裁切；结构可由正文唯一确定则自动生成最合适的一种格式；比例、数据或几何关系不确定时先询问；纯装饰不生成；需要操纵与即时反馈时才使用 HTML。根据正文重建的图必须标注“AI 根据教材正文重建的示意图，并非教材原图”。

一次性展示可留在课堂；有复用价值的资产按当前活动路由：

- Lesson：保存到 `lessons/<current_activity_id>/illustration/`，并在当前 Lesson 登记来源、
  格式和日期；
- Exercise：通用教学示意资产保存到课程 `book/course_materials/supplements/`，并由当前
  `exercise.md` 回链；学生提交图片只进入对应 Attempt 的 `assets/`，不得混作教学资产。

课程内反复出现的偏好写入 `course_reflections.md`，跨课程稳定偏好写入 `profile.md`。

---

## 四、恢复时的翻页窗口管理

**本节只有在只读活动路由返回 `current_activity: lesson` 且课程 driver 为 textbook 时
执行。Exercise（包括带历史 Lesson 的 Exercise）和其他 driver 直接跳过整节，不解析旧
`textbook_page`，也不据此构造 Lesson 路径。**

恢复上下文后，教材原文通过 preparation Snapshot + source_assets 管理：

### 基准 Scope / TeachingWindow（EV-0012）

- **LessonScope**：含当前页连续 **5–8** 页（短书 = 全部可用页固定）；见 `source_page_assets.md`。
- **TeachingWindow**：投影 current 与驻留；默认偏好相对 `[-1,0,+1,+2,+3]`，书首/末平移。
- 页图优先 `.cache`；配额满时合法 CacheEviction，失败才 session_temp。

### 预加载 / prepared 验收门

**新路径**：进入讲授前须有 valid `LessonPreparationSnapshot`（Scope + Map + load receipts）与足够核验等级（`t2ag.md`）。

**Legacy 路径已退役**：原 `working_pages/source_excerpt.md` + `progress.md` `textbook_page` / `working_pages_window` 路径
已在 0.2.2 批 S3 退役；历史摘录见各课 `archive/`。

翻页原子流程：**渲染 → 目视 → OCR → 校对写入 source_assets → 新 Scope/Snapshot → progress → doctor**。
任一步未完成不得讲新页。

### 窗口管理规则（EV-0012）

| 场景 | 操作 | 结果 |
|---|---|---|
| 正常书开讲 | prepare 连续 Scope **5–8** 页（默认 5） | 新 Snapshot + current 指针 |
| 扩窗 / 翻页 | 新 Scope 版本 → **新** Snapshot；旧 Snapshot 只读保留 | 不改旧 PREP |
| 短书 `N<5` | Scope = 全部可用页固定 | `short_document: true` |
| 页图配额 | `.cache` 内非 P0 可重建项按 CacheEviction | P0 永不删；失败 `cache_quota_blocked` |
| legacy 物理文件 | 已退役（0.2.2 批 S3），历史摘录见各课 `archive/` | — |

**废除**：working_pages_window、结课自动删 `working_pages`、4 页基线 / 6 页上限的旧表述。

> **source_assets**：持久核验文本不做窗口内删除。`.cache` PNG 才是可驱逐派生。
> Legacy `working_pages/` 路径已在 0.2.2 批 S3 退役；历史摘录见各课 `archive/`。

---

## 五、注意事项

### 1. 确认学生情绪状态再调整节奏

- 恢复上下文时，必须先读取 `main/10_student/profile/profile.md` 和近期课程感想；处理练习或复测时按需读取解题思维档案
- 若学生近期有焦虑、挫败等负面情绪 → 适当放慢节奏、多鼓励、降低难度
- 若学生情绪积极 → 可适当增加挑战、加快进度
- **不能只看进度不看人**：教学节奏由学生掌握程度和情绪状态共同决定

### 2. 逐节确认，不得跳内容

- 恢复后，从上次**尚未讲完**的位置继续，不得跳过未讲完的内容
- 讲完当前页/当前节的全部内容后，必须停下来问学生：「确认理解了？继续 / 再讲一遍 / 提问？」
- 学生使用 `问题：` 或 `疑问：` 时按同一触发处理：暂停后续推进、先回答；问题状态写
  `question_bank.md`，活动现场写入只读路由返回的当前 Lesson 或 Exercise 主载体
- 在学生明确确认「继续」之前，不得跳到后续内容
- 即使学生问了后续相关的问题，也只能回答该问题本身，不能提前展开尚未讲授的后续内容

### 2.1 习题闭环门

- 每道习题结束后，检查学生本次回答是否明确表示“没有疑问”
- 若未明确表示：先基于学生实际写出的步骤分析其思维方法，再询问“有无疑问”
- 若只有最终答案、过程证据不足：不得补写或猜测学生思路，应请学生补充方法
- 若学生已在本次回答中明确表示“没有疑问”：可跳过本题的思维分析与疑问询问
- 习题闭环不替代逐节确认；准备进入下一概念、定义或定理时，仍须学生明确表示“继续”

### 3. 教材原文优先

- 恢复后继续教学时，每个概念、定义、定理、证明必须优先引用教材原文
- 教学方案提供框架，教材原文提供内容
- 「看教材原文」意味着真正去扫描、提取原文，而不是凭已有材料复述

### 4. working_pages/ 生命周期（已退役）

- `working_pages/` 是 textbook Lesson 的 legacy 临时工作区，已在 0.2.2 批 S3 退役。
- 新权威为 Course `source_assets` + preparation Snapshot/Map。
- 历史摘录与 OCR 已归档至各课 `archive/`；不得重建或重新使用。
- `illustration/` 是持久保存的，不受课程结束影响

### 5. 状态指针可靠性

- `progress.md` 的前台字段和精确停点是恢复入口；Activity lifecycle 必须从
  `activity_ledger.md` replay
- 当前活动主载体中的局部停点是细粒度证据，用于帮助修复真相源；Lesson 的“最后停点
  快照”与 Exercise 的精确停点都不是 GENERATED 缓存
- 若各文件状态不一致，先运行 `main/70_tools/t2ag_doctor.py --profile runtime`，再以 `progress.md` 为准；
  若当前活动证据更细，需向学生确认后写回 `activity_position`，不得从历史 Lesson 推断
- checkpoint 可静默保存精确停点，但 completion node 只有满足课程既有关闭证据才完成；二者不得混写

### 6. 恢复后同步更新

- 恢复并继续教学后，每次课程结束需更新：
  - 只读路由返回的当前 Lesson 或 Exercise 主载体；Exercise 不更新历史 Lesson
  - `progress.md` 的 `activity_position`、「当前进度」节和「教学记录」、累计学习时长
  - `[课程]/mistake_bank.md` 的新增知识错误与复测结果
  - `main/00_core/t2ag_memory.md` 与 `main/10_student/profile/learning_path.md` 的进度缓存
  - `main/10_student/profile/profile.md` 或 `course_reflections.md`（若有新的状态/感想记录）
  - 若本次由 active 课堂交接恢复，按 `handoff_management.md` 在正式写回验证后关闭交接
