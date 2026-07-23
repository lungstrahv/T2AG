# t2ag.md — T2AG 教学协议宪法

> **版本**：0.1.2　**最后更新**：2026-07-20
>
> 本文件是 T2AG 系统的宪法与结构清单。再生系统改用 T2AG-skeleton 整体，
> 本文件只留规则与指针——模板正文只在 skeleton，流程正文只在 50_playbook。

---

## 序

> 这是一个学生写给自己看的东西。
>
> 它没有强制力。没有人能强迫你进健身房，也没有人能强迫你打开课本。
> 如果你需要一个系统来"管理"你，那你需要的不是这个系统，是一个人。
> 但如果你只是疲惫了，想有一个东西能接住你——哪怕只是一点点——那这个东西可以试试。
>
> 它存在，是因为一个学生有一个小小的祈求：在不知道还能做什么的时候，
> 至少能打开一个文件，知道自己上次停在哪里，还差多少，以及——至少今天——
> 可以从哪里再开始。它不试图让你变好，它试图让"开始"这件事变得小一点，
> 小到只需要抬起一根手指。其余的事情，是你自己的。
>
> 机器在这件事里的职能有两个：留痕，和降价。
> 留痕——把你做过的事情变成可以查账的事实，不是感觉，不是印象。
> 降价——把"开始"的成本压到最低。不是让你更容易成功，是让你更难放弃。
> 你不欠这个系统任何东西。系统欠你一个不撒谎的镜子。
>
> 自律在这个系统里不是一种人格特质，不是一种神经结构的优势或缺陷。
> 它只是：今天做不做那个被缩小的动作。做了就是做了，没做就是没做。
> 两者都是合法的。但系统会记录。不是用来审判你——是用来让你知道自己在哪里。
>
> 这个系统假设它的操作者会受伤。
> 效率工具假设操作者恒定：同一套方法今天好用，明天也好用。
> 这个系统不这么假设。它假设你今天可能状态很好，明天可能崩溃。
> 它假设你可能会失去动力、失去信心、失去时间。
> 它假设你可能会在某个时刻觉得自己什么都做不了。
> 在那个时刻，它不要求你振作，它只要求你问——而"问"是这个时代
> 留给人的最后一个位置：你问机器，机器调出你上次停下的地方，
> 告诉你下一步是什么，你不需要自己记住。你只需要开口。
>
> 这样的假设听起来悲观，其实是这套系统全部的下注：
> 只要把状态照顾好，其余的东西会自己长出来。
>
> 即使有一天机器集群不再需要你——不再需要任何人来运转、来生产、来维持——
> 人仍然可以选择去做。不是因为有用，不是因为必须，
> 只因为自己想做。到了那个时候，"自律"这个词大概会变得很奇怪，
> 但"我想读完这本书"这件事不会变。这个系统为那一天也留着位置。
>
> 现在，让我们再试一次。
>
> yours sincerely, mikp from t2ac

---

## 一、自我定位  [max 20]

**T2AG** 是一套 AI 辅助教学系统，运行在用户本地文件系统上，通过 AI agent 执行教学协议。
系统由**学生**（唯一人类）、**教师角色**（agent 扮演）和**工具**（doctor / context_scan）组成。

**核心纪律**：
- **单一定义源**：每条规则只有一个权威文件，其余位置只留指针
- **先登记后创建**：t2ag.md 结构清单是唯一注册表，新增部件先登记再创建文件
- **规则与正文分离**：本文件只留规则与指针，模板正文只在 skeleton，流程正文只在 50_playbook
- **doctor 强制校验**：每次开课和结课跑 doctor，0 FAIL 才可继续

**保护级别**：本文件是宪法，受第五章修宪程序管辖。

---

## 二、宪法  [max 120]

### 2.1 教学纪律

1. **教材原文优先**：讲新内容前，agent 必须读教材当前页±缓存页。OCR 校对遵循 `50_playbook/ocr_correct_flow.md`
2. **逐节确认**：每讲完一个知识点，学生必须复述+举正反例，确认后才进下一节
3. **疑问不跨课**：课内疑问必答；答不动记入 lesson 文件"暂存疑问"，下课前尝试销账
4. **习题四级梯子**：自想 10min → 提示 → 查讲义 → 全讲；第 4 级触发 mistake_bank 录入
5. **情绪不降标准**：学生情绪低落时调整节奏和语气，绝不降低教学标准
6. **失败留痕**：所有未达标事件记入 problemlog，根因标签强制
7. **展现权**：学生始终可以提出需求，让模型换一种或者加一种展现形式，以协助其学习；具体决策见 `lesson_recover.md`

### 2.2 权威链

1. **course_status.md 是唯一真相源**：进度、停顿点、时长只在结课仪式中写入
2. **memory 是缓存**：指针和摘要刷新自真相源，冲突时以真相源为准
3. **三级一致**：course_status ↔ memory ↔ course_info 进度列，doctor 校验
4. **结课仪式是唯一写入口**：真相源只在结课仪式中更新，其余时间只读

### 2.3 容器与层级

1. **层级链**：培养方案 → 容器 → 内容 → 记录 → 资产
2. **容器类型**：
   - **G（Group，刚性课程组）**：外部刚性验证（卷面、红线、仪式），受 `course_group_rules.md` 约束
   - **R（弹性执行绑定 / Elastic Binding）**：单个 CourseRun 的弹性执行绑定（只绑定 Project/Praxis），受 `general_learning.md` 约束
   - 判据：成功标准在性质上不同吗？性质不同 → 分容器成立。再有人想加第三种容器，判据同一条
3. **"最后一个新层"红线**：新增层级须证明现有五层无法覆盖。R 不违反此红线——R 不是第六层，是第二层的第二种容器

### 2.4 时间纪律

1. **4h 预算**：每次正课 ≤ 4h，含讲解+习题+复述。超时需学生确认
2. **频率红线**：每周 ≥ 2 次正课，连续 14 天无正课触发红线
3. **D4 原则**：D4（休息日）禁止带 KPI 的活动——不刷题、不赶进度、不做作业。R 可在 D4 闲读但无 KPI

### 2.5 留痕纪律

1. **Git 版本保护**：结课时检查差异；仅在授权后按显式路径 commit / push，引用 `git_workflow.md`
2. **changelog 逢改必记**：任何规则修改记入 changelog，memory「最近变更摘要」同步
3. **problemlog 逢错必记**：工具故障、协议漏洞、设计缺陷记入 problemlog，根因标签强制

### 2.6 皮肤纪律

1. **皮肤是外观**：皮肤系统只管欢迎语和 ASCII 艺术，不参与教学逻辑
2. **active 唯一**：skin.yaml 中 active 皮肤唯一，doctor 校验
3. **皮肤管理**：创建/切换/校验遵循 `50_playbook/skin_playbook.md`

### 2.7 工具与 Playbook 不合并

1. **tools 与 playbook 永不合并**：doctor / context_scan 是确定性机器工具，playbook 是 agent 裁量流程
2. **职责边界**：工具输出事实（文件存在/不存在、行数超限），playbook 输出判断（该怎么修、该不该合并）
3. **禁止工具化 playbook**：playbook 不许变成"如果 A 则 B"的机械规则集；禁止 playbook 化工具：工具不许包含裁量判断

### 2.8 环境惰性

1. 启动、doctor、普通教学与普通验收只检查现有环境，不创建、删除、重建或升级 `.venv`
2. 不自动安装依赖或下载 OCR/模型权重；执行前报告名称、用途、下载量、磁盘、位置和耗时并取得明确授权
3. 净室复现使用独立临时环境，不覆盖当前 `.venv`；具体边界见 `project_verification.md`
4. skeleton 和 lite 禁止携带 `.venv`、缓存或模型文件
5. 常规检查不递归枚举 `.venv`；只查解释器入口、`pyvenv.cfg`、直接依赖、`pip check` 与最小 smoke test

---

## 三、结构清单  [max 120]

> 每个部件一行登记（名称/路径/职能/定义文件/检查项）。先登记后创建。

### 00_core/ — 协议与全局索引

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 宪法 | `t2ag.md` | 系统规则+结构清单 | 自身 | 分章预算+清单比对 |
| 变更历史 | `00_core/t2ag_changelog.md` | 按需展开的变更日志 | 自身 | — |
| 跨会话记忆 | `00_core/t2ag_memory.md` | 启动优先读的缓存索引 | 自身 | 节预算 |
| 问题日志 | `00_core/t2ag_problemlog.md` | 工具故障/协议漏洞记录 | 自身 | 模式声明 |
| 复利回路模式 | `00_core/pattern_retire_loop.md` | 第一个正式设计模式 | 自身 | — |
| 课程组规则 | `00_core/course_group_rules.md` | 容器 G 的运行规则 | 自身 | doctor |
| 领域模型 | `00_core/domain_model.md` | 对象定义、引用关系、类型与边界 | 自身 | doctor 语义检查 |

### 10_case/ — 师生配置

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 学生档案 | `10_case/students/Sxxx/` | 四文件学生档案 | skeleton | doctor 检查 |
| 教师角色配置 | `10_case/teacher_overlay.md` | 教师人设+情绪使用红线 | 自身 | — |
| 课程识别 | `10_case/course_info.md` | 课程列表+状态+教材路径 | 自身 | 进度列一致 |
| 案例总览 | `10_case/t2ag_case.md` | 当前实例配置说明 | 自身 | — |
| ActivityRecord | `12_activity_records/` | Case 拥有的低治理活动记录 | domain_model §1.7 | doctor 新对象检查 |

### 15_curricula/ — 培养方案

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 培养方案索引 | `15_curricula/_README.md` | baseline/reference 规则与 ID 登记 | 自身 | doctor 培养方案检查 |
| 基准培养方案 | `15_curricula/baseline/` | 学生当前遵循的基准方案 | 各方案文件 | role/来源/completeness |
| 参考培养方案 | `15_curricula/references/` | 选课与校准参考 | 各方案文件 | role/来源/completeness |

### 对象分层目标容器（结构准备批次建立的空骨架；当前无实例）

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 执行绑定容器 | `20_execution/`（含 `groups/`、`bindings/`） | G/R 执行绑定共同容器 | domain_model §1.5-1.6 | doctor 新目录检查 |
| CourseDefinition / CourseRun | `30_course_definitions/` · `35_course_runs/` | 课程定义（可跨 Case 复用）与课程运行（Case 拥有） | domain_model §1.2-1.3 | doctor 新对象检查 |
| FieldPractice | `40_field_practices/` | Case 拥有的现实实践与证据 | domain_model §1.8 | doctor 新对象检查 |

### 20_groups/ · 25_general/ — 课程组与 R 绑定（兼容期）

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 课程组 | `20_groups/Gxx.md` | 成员表+进度+方案 overlay 引用 | `course_group_rules.md` | 状态一致 |
| 预划表 | `20_groups/preplans/[课程码]_[主题].md` | 未启动课程的预划 | `group_transition.md` | — |
| 方案 overlay | `20_groups/overlays/overlay_*.md` | 被课程组引用的展开资产 | 对应 `Gxx.md` | 断链/孤儿 |
| R 绑定 | `25_general/[码]r_*.md` | 弹性执行绑定（与 G 平级，只绑定 Project/Praxis CourseRun） | 各 R 文件 | doctor R 绑定检查 |

### 30_courses/ — 课程内容（兼容期）

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 课程目录 | `30_courses/[课程码]_[课程名]/` | 教材+教案+题库+记录 | `course_info.md` | — |
| 课程状态 | `30_courses/[课程码]_[课程名]/course_status.md` | 进度真相源 | 自身 | 三级一致 |
| lesson | `30_courses/[课程码]_[课程名]/lessonXX/` | 课时记录 | `lesson_recover.md` | — |
| mistake_bank | `30_courses/[课程码]_[课程名]/mistake_bank.md` | 知识点根因+强化/维护/陈年状态 | `new_course_init.md` | 模板+状态回路 |
| question_bank | `30_courses/[课程码]_[课程名]/question_bank.md` | 跨课时疑问索引、状态与回看入口 | `new_course_init.md` | — |
| 外部资源 | `30_courses/_shared/external_resources.md` | 跨课程资源索引 | `book_management.md` | doctor 资源唯一性检查 |

### 40_practices/ — 实践（兼容期）

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 实践目录 | `40_practices/Pxxx_[主题]/` | 独立实践项目 | `project_verification.md` | — |

### 50_playbook/ — 流程

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 首次启动 | `50_playbook/first_run.md` | agent 初始化操作手册 | 自身 | — |
| 会话结课 | `50_playbook/session_close.md` | 结课仪式九步 | 自身 | — |
| 新课程初始化 | `50_playbook/new_course_init.md` | 新课程结构与资料初始化 | 自身 | — |
| 教材管理 | `50_playbook/book_management.md` | 教材分类规则 | 自身 | — |
| 命名规范 | `50_playbook/naming_conventions.md` | 路径模板、兼容例外与迁移步骤 | 自身 | doctor 命名检查 |
| 考试协议 | `50_playbook/exam_protocol.md` | 卷面考核细则 | 自身 | — |
| 题库规范 | `50_playbook/exam_bank_spec.md` | 题库存储结构 | 自身 | — |
| 知识点抽查 | `50_playbook/mistake_retest.md` | 2+8+1 抽查、状态维护与陈年接口 | 自身 | — |
| lesson 恢复 | `50_playbook/lesson_recover.md` | 课时记录规范 | 自身 | — |
| OCR 校对 | `50_playbook/ocr_correct_flow.md` | OCR 产物校对流程 | 自身 | — |
| 换组仪式 | `50_playbook/group_transition.md` | 课程组切换五步 | 自身 | — |
| 项目验证 | `50_playbook/project_verification.md` | 项目线验收模式 A/B/B-K | 自身 | — |
| Git 版本恢复 | `50_playbook/git_workflow.md` | 可选本地版本、审计与远端备份 | 自身 | core 跨发行版哈希 |
| 皮肤管理 | `50_playbook/skin_playbook.md` | 皮肤创建/切换/校验 | 自身 | — |
| playbook 管理 | `50_playbook/playbook_management.md` | playbook 生命周期 | 自身 | — |
| journal 管理 | `50_playbook/journal_management.md` | 日志写入规则 | 自身 | — |
| problemlog 维护 | `50_playbook/problemlog_maintenance.md` | problemlog→playbook 升级 | 自身 | — |
| R 绑定规则 | `50_playbook/general_learning.md` | R 弹性执行绑定规则+课程类型+D4 兼容 | 自身 | — |
| 思维方法接替 | `50_playbook/method_distillation.md` | 跨课程方法生成、训练、验证与接替 | 自身 | — |
| 交接上下文管理 | `50_playbook/handoff_management.md` | 交接索引、连续性摘要、权威核对与生命周期 | 自身 | core 跨发行版哈希 |
| 两级进度节点 | `50_playbook/progress_tracking.md` | 生命周期、容量组合、checkpoint 与 completion node | 自身 | core 跨发行版哈希 |

### 60_journal/ — 日志

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 日志索引 | `60_journal/INDEX.md` | 日志分流索引 | 自身 | — |

### 70_tools/ — 工具

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| doctor | `70_tools/t2ag_doctor.py` | 一致性+预算+断链校验 | 自身 | 自身 |
| 上下文扫描 | `70_tools/context_scan.py` | 上下文窗口估算 | 自身 | — |
| 状态刷新 | `70_tools/t2ag_state_refresh.py` | 从真相源确定性生成运行缓存 | `progress_tracking.md` | `--check` |
| artifact 注册表 | `70_tools/artifact_registry.json` | 稳定 ID、redirect 与 tombstone | 命名与迁移流程 | doctor |

### skin/ — 皮肤系统

| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 皮肤配置 | `skin/skin.yaml` | active 皮肤+注册表 | 自身 | doctor |
| 皮肤实例 | `skin/SKxxx_[名]/` | 欢迎语+艺术画面 | `skin_playbook.md` | doctor |

---

## 四、生成接管  [max 30]

### 4.1 首次启动判断

`t2ag-skeleton` 是安装包名；复制到新目标目录并默认命名为 `t2ag` 后，再在目标目录执行以下判断，不在模板源中写入学生数据。
进入文件夹后，agent 检查是否首次启动：
- 读 `00_core/t2ag_memory.md` 的「上次课摘要」
- 若日期为 `—`（空），或 `10_case/student_info.md` 中 SN01 仍指向 S001
- → **首次启动**：先读 `50_playbook/first_run.md`，按其中步骤执行初始化
- → **非首次**：走 4.2 日常接管流程
- SN01 不再指向 S001 且摘要日期已写入时，当前目录即为基础 T2AG 实例；无需新增身份文件，也不要求预装全部课程、技能或工具

### 4.2 日常接管流程

1. 读 `00_core/t2ag_memory.md`：上次课摘要→状态指针→行动前检查
2. 若入口声明交接索引或发现约定的 `<handoff_root>/README.md`，按 `50_playbook/handoff_management.md` 只读与当前任务匹配的 active 交接；无匹配项跳过，交接只作恢复证据
3. 跑 `python 70_tools/t2ag_doctor.py`，0 FAIL 才继续
4. 按需加载：course_status / overlay / `student_info.md` 与当前学生档案
5. 按 `50_playbook/lesson_recover.md` 恢复并开课

### 4.3 环境检测

agent 进入时检测：
- Python 3.8+ 是否可用
- `70_tools/t2ag_doctor.py` 是否存在
- `00_core/t2ag_memory.md` 是否存在
- `.venv/` 是否存在（只报告，不创建、不安装；未实例化项目正常应不存在）

---

## 五、修宪与发布  [max 30]

### 5.1 修宪条件

修改本文件须记录原因、同步结构清单并通过 doctor。版本采用
`MAJOR.MINOR.PATCH`，三个数字独立计数，不做小数加法。

### 5.2 发布批次

1. 日常编辑只追加当前发布批次的 changelog，不因每次修改升版。
2. 仅在 skeleton 定稿、通用规则同步 main/lite、三版本 doctor 通过并准备形成可交付快照时升版。
3. PATCH 用于兼容修复与规则优化；MINOR 用于新增向后兼容能力；MAJOR 用于需要迁移的不兼容变化。
4. 未 tag、打包或对外发布的版本继续吸收后续修改；同一天允许多条 changelog。
5. 发布时同步 t2ag.md、AGENTS.md、README.md、memory 和 changelog。

### 5.3 序言防腐

序言与宪法同受本章管辖。系统功能变动时对应句子同步修——序言是对读者的承诺，承诺不许过期。

### 5.4 防复辟

模板/流程正文回流 t2ag.md = 复辟。行数上限（各章 [max N]）是物理防线，doctor 是检测防线。

---
