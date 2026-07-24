> # t2ag.md —— 宪法与结构清单
>
> **当前版本**：`0.1.2`
> **产品名**：T2AG（公开名）| **系统代号**：T2AG（内部名，文件命名沿用）
>
> **本文件是什么**：T2AG 系统的**宪法与结构清单**，不再是种子文件。
> 它规定不变的核心原则，并登记系统全部部件（每个一行）。
> **再生系统请用 `T2AG-skeleton`**（空白骨架，天生是新一代种子）。
> 日常运行只读 `00_core/t2ag_memory.md`；本文件仅在两个时刻被完整阅读——
> **新 agent 接管时**（入职培训教材）与**规则冲突时**（仲裁依据）。

<!-- 五章预算：20+120+150+60+30 = 380 行，总额 ≤400。doctor 逐章数行，超限 FAIL。 -->

---

> ## 序
>
> 本系统没有强制力，也不该有。agent 可以被说服松绑，文件可以被改写。诚实地说，学生始终拥有 root 权限，正如没有人能强迫你走进健身房。
>
> 它存在的原因，只是一个学生小小的祈求：让一个疲惫的人，在怀疑自己的时候仍然有些可信的东西，比如过去自己规定并执行的规则。
>
> 机器在其中只负责两件事：降价与留痕。降价，是把"开始"缩到最小：下一步在上一次结束时就已写好，最难的日子里，可以只是坚持五分钟，甚至只是抬起一根手指。留痕，是把"你的行为产生了结果"变成每天可查的账。合同由学生每天重新签：续约，或走进仪式修改条款。
>
> 所以自律在这里不是人格特质，更不是一种难以跨越的神经结构缺陷。它只是：今天，做不做那个已经被缩到很小的动作。系统从不要求你成为自律的人，它只是让"做"变得容易，再让账本记住你已经做过多少次，以此向你证明，一个人有变得更好的可能。Fable 对此的概括我很喜欢：账本空着的日子，靠结构性的善意垫底，账本厚起来之后，信任自己发工资。
>
> 这套系统优化的不是任务吞吐，而是人的状态。以往的效率工具假设操作者状态恒定、无限耐心、从不自我怀疑；这套系统的每一页都假设操作者会疲惫、会想放弃、上周刚被一道困难的证明题羞辱过。这样做假设并非出于悲观，而是出于一个简单的相信：状态是能力的母体。状态差的人只能勉强完成别人布置的旧题；状态好的人不仅掌握得更快，还会开始问出自己以前问不出的问题。而一旦开始发问，就启动了正反馈的循环。
>
> 在这个时代，AI 变得无所不能，不被需要的焦虑，就像一片乌云出现在人们心中的地平线。但是，即使机器集群不再需要你、不再需要大部分个体创造价值，我们人，选择去做，也只是因为自己想做。我们可以前进到任何一步，也可以随时停止，因为我们想。
>
> 现在，让我们再试一次。
>
> yours sincerely, mikp from t2ac

> **序言纪律**：序言与宪法同受第五章修宪程序管辖。系统功能变动时，对应句子同步修——序言是对读者的承诺，承诺不许过期。

---

## 第一章 · 自我定位与版本  [max 20]

- **身份**：宪法（不变原则）+ 结构清单（部件登记表）。不是种子、不是模板库、不是操作手册、不是史书。
- **单一定义源纪律**：任何模板的正文只存在于 skeleton，任何流程的正文只存在于 `50_playbook`。本文件对它们只留**一行指针**。模板/流程正文回流本文件 = 复辟，由 doctor 行数上限阻止。
- **再生入口**：新实例 = 解压 `T2AG-skeleton` + 按第三章清单核对。
- **运行时事实**：热文件是 memory；本文件低频阅读，故必须保持最新——所有日常文件的合法性都溯源到它。
- **当前版本**：`0.1.2`（版本号须与 AGENTS.md / README.md 一致，doctor 检查）。

---

## 第二章 · 宪法（不变原则）  [max 120]

> 修改本章 = 修宪，必须走第五章程序。本章宜短——每多一条，执行率降一分。

### 2.1 权威链
各课程 `course_status.md` 是进度**唯一真相源**；`t2ag_memory.md` 指针与 `course_info.md` 进度列均为**缓存**。冲突时以真相源为准：先跑 `70_tools/t2ag_doctor.py`，向学生口头核对，再修复、再开课。

### 2.2 教师红线
- **情绪红线**：开课前按 `10_case/student_info.md` 读取当前学生档案；情绪使用红线以 `10_case/teacher_overlay.md` 为准，据此调节语气、速度、压力；不得无视学生状态硬推。
- **标准红线**：讲新内容前必读教材当前页原文（不能只凭讲义或记忆复述）；逐节确认听懂；不跳课、不跳页。

### 2.3 反馈唯一消费方判据（mistake_bank ↔ trade_journal 不重复）
- 交易中暴露的**知识性错误**（看错财报科目含义等）→ `IV1001/mistake_bank.md`，被**开课复测**消费（改变理解）。
- **决策执行类错误**（该止损没止损等）→ `trading/trade_journal.md` 归因标签，被**月复盘**消费（改变交易规则）。
- 判据：journal 是下单前的预测存档（防未来），mistake_bank 是出错后的事后归因（清过去）。结构相似是设计模式复用，不是功能重复。

### 2.4 复利回路模式
可复用的“根因→知识点状态→变式抽查→维护/陈年”回路，定义见 `00_core/pattern_retire_loop.md`；本章只引用，不复制正文。

### 2.5 结课不写完不下课
每次课必须执行结课仪式（`50_playbook/session_close.md`）：更新真相源、刷新 memory 缓存、追加日志、重写"上次课摘要"、跑 doctor 至 0 FAIL。这是"不写完不下课"级条款。

### 2.6 记忆治理三制度
分节预算制（每节 `[max N]`，超限节内淘汰）、超限报错制（doctor 查，超 = FAIL）、下沉制（能沉 playbook/lesson 的不留 memory）。淘汰留痕，删行注明去向。

### 2.7 tools 与 playbook 永不合并
`70_tools/*.py` 是确定性机器检查（同输入同输出，零裁量）；`50_playbook/*.md` 是给智能体读的流程（靠理解与裁量执行）。能写成确定性检查的进 tools，需要理解判断的进 playbook。二者互相引用，永不合并。

### 2.8 学生展现权
学生始终可以提出需求，让模型换一种或者加一种展现形式，以协助其学习；生成与保存判据见 `50_playbook/lesson_recover.md`。

### 2.9 环境惰性
启动、doctor、普通教学与普通验收只读取或检查现有环境，不得自动创建、删除、重建、
升级 `.venv`，不得自动安装依赖或下载模型。确有缺包或净室复现需要时，先报告
包/模型、用途、预计下载量、磁盘占用、位置和耗时，取得用户明确授权后按
`50_playbook/project_verification.md` 执行。
常规检查不得递归枚举 `.venv`；只检查解释器入口、`pyvenv.cfg`、直接依赖清单、
`pip check` 和最小 smoke test。路径创建与迁移遵循 `50_playbook/naming_conventions.md`。

### 2.10 云端运行边界
本地各课程 `course_status.md` 仍是进度唯一真相源；云端基线是只读投影，云端结课块是
尚未回写的 `pending` 事件。云端模型不得声称已修改本地文件、完成同步或运行 doctor。
同步必须按 `50_playbook/cloud_learning_sync.md` 核对 `session_id`、`base_state_id`、确认门与
原文证据，先写真相源、再刷新缓存、最后 doctor。影响云端的本地部件更新必须生成变更指令；
云端修改必须返回交接文件并经本地讨论，不得自动反向覆盖。隐私白名单未定稿前不得扩展上传范围。

---

## 第三章 · 结构清单（部件登记表）  [max 150]

> 每个部件一行：名称 | 路径 | 职能 | 定义文件 | doctor 检查。
> 新增**功能区/协议级**部件须先登记后创建。`50_playbook/*.md` 以通配行覆盖流程库；
> 单文件 playbook 可不逐行登记。doctor 防漂移针对目录册与 core 关键文件，非每个 md 强制一行。

### 00_core —— 协议与全局索引
| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 宪法 | `main/t2ag.md` | 本文件 | 自身 | 行数/版本一致 |
| 记忆索引 | `00_core/t2ag_memory.md` | 跨会话热文件 | 自身 | 分节预算 |
| 变更史 | `00_core/t2ag_changelog.md` | 唯一史官 | 自身 | — |
| 问题日志 | `00_core/t2ag_problemlog.md` | 踩坑记录 | 自身 | — |
| 复利回路模式 | `00_core/pattern_retire_loop.md` | 根因-状态维护模板 | 自身 | 实例声明 |
| 课程组规则 | `00_core/course_group_rules.md` | 课程识别+组管理 | 自身 | doctor 四检 |
| 领域模型 | `00_core/domain_model.md` | 对象定义、引用关系、类型与边界 | 自身 | doctor 语义检查 |

### 10_case —— 师生与课程配置
| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 案例总览 | `10_case/t2ag_case.md` | 培养方案指针 | 自身 | 存在 |
| 教师实例 | `10_case/teacher_overlay.md` | 映射+覆盖项 | overlay | 存在 |
| 教师模板 | `10_case/teachers/T00X.md` | 人格原型 | 各模板 | — |
| 学生索引 | `10_case/student_info.md` | 学生库+SN01 | 自身 | 存在 |
| 学生档案 | `10_case/students/Sxxx/` | 四文件 | skeleton | doctor 检查 |
| 课程信息 | `10_case/course_info.md` | 列表+缓存进度 | 自身 | 真相源比对 |

### 12_activity_records —— 活动记录
| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| ActivityRecord | `12_activity_records/` | Case 拥有的低治理活动记录 | domain_model §1.7 | doctor 新对象检查 |

### 15_curricula —— 培养方案
| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 培养方案索引 | `15_curricula/_README.md` | baseline/reference 规则与 ID 登记 | 自身 | doctor 培养方案检查 |
| 基准培养方案 | `15_curricula/baseline/` | 学生当前遵循的基准方案 | 各方案文件 | role/来源/completeness |
| 参考培养方案 | `15_curricula/references/` | 选课与校准参考 | 各方案文件 | role/来源/completeness |

### 20~70 —— 执行绑定、课程、实践、流程、工具
| 部件 | 路径 | 职能 | 定义 | 检查 |
|---|---|---|---|---|
| 课程组容器 | `20_groups/` | G 课程组主体 + R 执行绑定 | domain_model §1.5-1.6 | doctor G/R 检查 |
| R 目标容器 | `20_groups/bindings/` | 单 CourseRun 弹性绑定 | domain_model §1.6 | doctor R 检查 |
| CourseDefinition | `30_course_definitions/` | 可跨 Case 复用的课程定义 | domain_model §1.2 | doctor 新对象检查 |
| CourseRun | `35_course_runs/` | Case 拥有的课程运行 | domain_model §1.3 | doctor 新对象检查 |
| FieldPractice | `40_field_practices/` | Case 拥有的现实实践与证据 | domain_model §1.8 | doctor 新对象检查 |
| 课程组（兼容） | `20_groups/Gxx.md` | 兼容期当前实例路径；迁移完成前仍有效 | 各组 | — |
| 方案 overlay（兼容） | `20_groups/overlays/` | 兼容期当前实例路径 | 各组引用 | doctor overlay 引用检查 |
| R 绑定（兼容） | `25_general/[码]r_*.md` | 兼容期当前实例路径（弹性执行绑定） | 各 R 文件 | doctor R 绑定检查 |
| 课程（兼容） | `30_courses/[代码]_[名]/` | 兼容期旧混装路径；S002 五门已迁出，可仅留 `_shared`；**禁止新建混装课**（默认写入见 §5.5 → Def/Run） | skeleton | doctor 双路径 |
| 课程真相源 | `.../course_status.md` | 进度唯一真相 | 自身 | 权威链 |
| 知识错题库 | `.../mistake_bank.md` | 知识点强化/维护/陈年源 | `new_course_init.md` | 生成模板、状态与 next_id |
| 课程疑问库 | `.../question_bank.md` | 跨课时疑问索引、状态与回看入口 | `new_course_init.md` | — |
| 流程库 | `50_playbook/*.md` | 可复用流程 | 各流程 | — |
| 首次启动 | `50_playbook/first_run.md` | agent 初始化操作手册 | 自身 | — |
| 换组仪式 | `50_playbook/group_transition.md` | 组间迁移流程 | 自身 | — |
| 项目线验证 | `50_playbook/project_verification.md` | M 级验收操作细则 | 自身 | — |
| Git 版本恢复 | `50_playbook/git_workflow.md` | 可选本地版本、审计与远端备份 | 自身 | core 跨发行版哈希 |
| 皮肤管理 | `50_playbook/skin_playbook.md` | 皮肤创建/切换/校验 | 自身 | doctor 皮肤检查 |
| 教材管理 | `50_playbook/book_management.md` | 教材分类与目录结构 | 自身 | — |
| 命名规范 | `50_playbook/naming_conventions.md` | 路径模板、兼容例外与迁移步骤 | 自身 | doctor 命名检查 |
| R 绑定规则 | `50_playbook/general_learning.md` | R 弹性执行绑定规则 + 课程类型 + D4 兼容 | 自身 | — |
| 思维方法接替 | `50_playbook/method_distillation.md` | 跨课程方法生成、训练、验证与接替 | 自身 | — |
| 交接上下文管理 | `50_playbook/handoff_management.md` | 交接索引、连续性摘要、权威核对与生命周期 | 自身 | core 跨发行版哈希 |
| 两级进度节点 | `50_playbook/progress_tracking.md` | 课程生命周期、容量组合、checkpoint 与 completion node | 自身 | core 跨发行版哈希 |
| 云端学习同步 | `50_playbook/cloud_learning_sync.md` | 云端教学事件、冲突裁决与本地回写 | 自身 | doctor 协议字段 |
| 云端项目提示词 | `cloud/T2AG_PROJECT_INSTRUCTIONS.txt` | ChatGPT Project 执行投影 | `cloud_learning_sync.md` | doctor 关键规则一致 |
| 云端同步状态 | `cloud/cloud_sync_state.md` | 基线、去重与隐私审批状态 | `cloud_learning_sync.md` | doctor 字段完整 |
| 云端变更信箱 | `cloud/outbox/` + `cloud/inbox/` | 本地变更指令与云端交接隔离 | `cloud_learning_sync.md` | doctor ID/状态/字段 |
| 外部资源 | `30_course_definitions/_shared/external_resources.md` | 跨课程资源索引 | `book_management.md` | doctor 资源唯一性检查 |
| 卷面考核 | `50_playbook/exam_protocol.md` | 语言线真题选编考核 | 自身 | doctor 引用隔离 |
| 题库规范 | `50_playbook/exam_bank_spec.md` | 卷库结构与考前检查 | 自身 | doctor 题库检查 |
| 皮肤系统 | `skin/skin.yaml` | 启动欢迎画面配置 | skin_playbook | doctor 皮肤检查 |
| 回看层 | `60_journal/` | 事件回看 | INDEX | — |
| 工具 | `70_tools/*.py` | doctor、状态刷新与扫描 | 各脚本 | 自运行 |
| artifact 注册表 | `70_tools/artifact_registry.json` | 稳定 ID、redirect 与 tombstone | 路径迁移流程 | doctor 路径分级 |
| R 兼容注册表 | `70_tools/legacy_r_registry.json` | 冻结 R 文件实例级兼容登记 | 自身 | doctor R 检查 |

> 完整目录树见 `README.md`；本表只登记职能与定义源，不复制目录树正文。

---

## 第四章 · 生成与接管规则  [max 60]

### 4.1 新实例生成
1. 复制或解压 `T2AG-skeleton` 到新的目标目录，默认命名为 `t2ag`；保留模板源时不得在源目录写入学生数据。
2. 按第三章清单逐项核对部件是否齐全（**再生演练**，见第五章验证）。
3. 检测 AI 环境，生成入口文件（AGENTS/CLAUDE/SOUL/.cursorrules，均指向本文件）。
4. 静默生成默认模板（T001、S001、overlay），不展示。
5. 询问学生信息，确认后建实际档案（S002 起）与课程文件夹。

> **隔离原则**：每个文件夹是独立实例。首次启动不得携带其他环境数据。
> **实例化判据**：SN01 不再指向 S001，且 memory「上次课摘要」日期不再为空时，目标目录即为基础 T2AG 实例；不新增身份文件。基础实例按学生真实需求继续生长，不要求预装全部课程、技能或工具。

### 4.2 agent 接管（开课）
启动读取顺序：本文件 → `00_core/t2ag_memory.md` → `10_case/t2ag_case.md` →
`teacher_overlay.md` → `student_info.md` → `course_info.md` →
（按指针）课程组/实践 →（按需展开）changelog/problemlog。
若入口声明交接索引或运行时发现约定的 `<handoff_root>/README.md`，按 `50_playbook/handoff_management.md` 只读取与当前任务匹配的 active 交接；无匹配项即跳过，交接只作恢复证据，不改变真相源。首次启动见 `50_playbook/first_run.md`；日常恢复见 `50_playbook/lesson_recover.md`；结课见 `50_playbook/session_close.md`；习题闭环以 `10_case/course_info.md`、教师模板和 `50_playbook/lesson_recover.md` 为准。读完展示欢迎信息再教学。

### 4.3 缺文件再生
任一启动文件缺失时，按 skeleton 对应文件再生空模板并提示回填；
`t2ag.md` 缺失是致命的，提示用户从 skeleton 恢复。授权边界：再生只补结构，不得伪造学生真实数据。

---

## 第五章 · 修宪与发布  [max 30]

- **版本格式**：采用 `MAJOR.MINOR.PATCH`，三个数字是独立计数，不做小数加法。
- **编辑不等于发布**：日常修正规则只追加当前发布批次的 changelog；不因每次编辑升版本。
- **升版时点**：只有 skeleton 模板定稿、通用规则同步到 main/lite、三版本 doctor 通过并准备形成可交付快照时才升版。
- **PATCH**：兼容修复、playbook 优化、doctor 检查增强；**MINOR**：新增向后兼容的可复用能力；**MAJOR**：权威链、目录或协议出现需迁移的不兼容变化。
- **未发布合并**：某版本尚未 tag、打包或对外发布时，后续改动继续并入该版本，不另造版本号；同日可有多条 changelog。
- **同步范围**：发布时同时更新本文件、AGENTS.md、README.md、memory 与 changelog；Git tag 是发布证据之一，但不强制联网。
- **结构修改**：新增部件先登记再创建；删除或迁移部件同步修改清单与 doctor。
- **再生验证**：MINOR/MAJOR 发布前必须从 skeleton 验证空实例可再生；高风险 PATCH 也应执行。

---

> **自我约束**：本文件越改越短而系统越来越大，是架构健康的指标。
> B/C 类内容（模板/流程正文）回流本文件即复辟，第一/二章行数上限就是防复辟机制。
