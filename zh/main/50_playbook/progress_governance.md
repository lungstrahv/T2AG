# 进度呈现治理（progress_governance）

**保护级别**：meta-playbook

> **职能**：Learner Surface / Operator Surface 分界与 Meaningful Pause 的呈现治理正本
> （EV-0034；PG-D0=A，2026-08-24 用户裁决）。管「学生看见什么、以什么顺序、何时必须
> 停顿、内部信息何时可见」。
> **不做什么**：进度事实归 `progress_tracking.md`；门语义与门索引归
> `main/00_core/gate_index.md`；
> 过程对象（门/流程/图）的准入、修订、退役归 `process_governance.md`；各旅程的流程正文
> 归原 playbook。本文件禁止复制状态真相或门语义正文。
> **保护级别裁决**：PG9 三 Edition 投影批已升为 meta-playbook；Main／中文 Skeleton／
> 英文 Skeleton 同步维护，翻译保持概念等价（2026-08-25）。
> **本版**：PG1–PG8 现行呈现规则已着床；PG9 完成三 Edition 投影与公开入口收口。

## 一、领域语言（消费，不再定义）

四个术语的 canonical 定义在根 `CONTEXT.md`，本文件是其规则消费者，不写第二定义：
**Learner Surface**、**Operator Surface**、**Meaningful Pause**、**Learner Journey
Contract**。任何与 `CONTEXT.md` 的措辞分叉以 `CONTEXT.md` 为准并须修订本文件。

## 二、呈现铁律（现行地板）

1. **学生决定体验，机器实现决定**：已确认方案的内部映射、公证、刷新与检查不是新决定，
   不得为其另立确认门。
2. **事实无默认**：学习水平、基础、目标、时间、工具习惯、Course Type、Learning Mode 与
   真实入口不得由机器默认值冒充学生事实或已确认选择；学生事实只有三态——已提供 /
   尚未提供 / 公开假设。昵称式称呼可以有中性 fallback。
3. **绑定不等于展示**：event ID、SHA、schema、内部状态码可以是完整性条件，但不是默认
   学生文案；学生主动要求诊断或发生冲突时，先自然语言解释影响与可选动作，必要时再展开
   技术附录。
4. **停顿必须答得出**「学生此刻的不同回答会改变什么」；答不出的停顿删除或降为内部步骤。
5. **恢复服从本轮意图**：学生本轮已明确说「继续」时，不重复索取一般继续授权；只有冲突、
   新范围或尚未表达的实际选择才构成 Meaningful Pause。
6. **诊断渐进披露**：默认只报结果、影响与可采取动作；内部 ID、文件清单、测试数、WARN
   全文仅在阻断处理、审计或学生主动要求时展开。
7. **一个用户旅程一个 canonical owner**：README/INSTALL/Edition 文档对本文件管辖的旅程
   只能投影或指向，不得各自拥有停顿顺序与默认值。
8. **安全门与交互轮次分开审计**：保留语义门不自动推出必须增加一条机械问答；现行宪法
   明确要求的独立等待，未经 PG-D1 裁决不得合并（见 §四）。删除、外部写入、发布与
   terminal RT3 的 exact authorization 不因体验优化降低。

## 三、管辖面与指针

八个旅程面（PG-S01..S08：安装 / 首启 / 建课建组 / 恢复 / 教学 / 结课 / 云同步 / 维护
回执）的证据矩阵与 finding 基线在工作区 PG0 报告
`docs/handoffs/T2AG_PROGRESS_GOVERNANCE_LEARNER_JOURNEY_REPORT_2026-08-24.md`。流程正文
owner 不变：

- 首启：`first_run.md`（+ `t2ag_flow.md`）
- 恢复：`lesson_recover.md`、`startup_orchestration.md`
- 结课：`session_close.md`
- 云同步：`cloud_learning_sync.md`
- 建课建组：`new_course_init.md`、`course_group_rules.md`

上述文件遇**呈现问题**（学生该看什么、何时必须停顿、内部 token 是否可见）以本文件为
裁决正本；遇**流程问题**（这件事怎么做）以各自正文为准。Meaningful Pause 的逐旅程预算
数字仍是假说（PG0 复算多项不满足），未经产品裁决不升规则，本文件不复制该表。

## 四、裁决结果

- **PG-D1＝甲**：保持教学块间三门及独立等待；未提问不等于无问题。`main/t2ag.md` 块间协议、
  门语义与 `gate_visibility` 现行边界不放宽。
- **PG-D2＝甲＋庚**：覆盖清单完整性不变，默认采用渐进展示；profile 的
  `lesson_tree_display_mode` 可选 `progressive | full`。摘要由同一完整树确定性派生游标，
  两种模式都须按序遍历到全部块取得终态；PDF／书内双页码与翻页四拍不变。

## 五、强制声明

PG8 已建立 renderer 面机器落点：`70_tools/learner_journey.py` 是学生措辞唯一 canonical owner，
`70_tools/learner_journey_scenarios.json` 固定六场景，atomic test
`contracts.learner_journey` 检查结构事件、pause owner、状态与磁盘结果、零半写和 Operator token
泄漏。工具只产结构结果与 Operator message；活模型对话仍属 `model_dependent`，不得由本测试冒充。

enforcement: check=runtime.playbook_taxonomy
enforcement: context=50_playbook/first_run.md#用户可见状态与停顿
enforcement: context=50_playbook/lesson_recover.md#询问是否继续
enforcement: context=50_playbook/session_close.md#结课领域树与适用性
enforcement: context=50_playbook/cloud_learning_sync.md#冲突裁决与降级模式
enforcement: context=50_playbook/course_group_rules.md#误当成第二次用户决策
enforcement: tool=70_tools/learner_journey.py

§七（PG2）不同：安装与首启面的两条判据已有真实机器载体——缺省态由 `t2ag_init.py` 的
`PROFILE_DEFAULTS` / `ANSWER_ENUMS` / `LEARNING_LEVEL_LABELS` 三处同源持有，两停顿结构与
「无现开始门」由 `contract_test_support.py` 的 `test_init_example_payload_is_documented_and_rejected`
与 `test_first_run_user_experience_contract` 断言。仅安装器本体的行为层无仓内载体（installer
不随本仓分发），如实按 prose 声明，不冒充已有 check。

enforcement: tool=70_tools/t2ag_init.py
enforcement: tool=70_tools/contract_test_support.py
enforcement: prose_accepted（理由：安装面行为层——installer 不在仓内）

§八（PG3）的机器面比前两节厚：参数必填由 `t2ag_init.py` 的 argparse 持有，激活判据由
同文件的 `group_activation_preflight` 持有并与 `t2ag_doctor.py` 同源，两者的期望值由
`contract_test_support.py` 断言，落地形态由 `runtime.groups` 复核。只有 §8.4 的学生对话面
（模型说了什么、有没有把内部回执念给学生）由 PG8 的
`contracts.learner_journey` 覆盖 renderer 面；活模型对话仍不冒充机器已覆盖。

enforcement: check=runtime.groups
enforcement: tool=70_tools/t2ag_init.py
enforcement: tool=70_tools/contract_test_support.py
enforcement: context=50_playbook/course_group_rules.md#误当成第二次用户决策
enforcement: prose_accepted（理由：§8.4 Operator-only 呈现只有工具 stdout 标记面有机器载体，学生对话面黑盒断言属 PG8=A9）

§九（PG4）的机器面只覆盖本地真载体：`lesson_recover.md` 持有既有恢复动作，
`contract_test_support.py` 锁词表、指针与条件句。活模型是否按本轮意图少问一次仍无仓内黑盒
载体，且云恢复已明确让渡 C4；本批不冒充两者已有行为检查。

enforcement: tool=70_tools/contract_test_support.py
enforcement: context=50_playbook/lesson_recover.md#询问是否继续
enforcement: context=50_playbook/lesson_recover.md#冲突即停
enforcement: prose_accepted（理由：本地活模型呈现与云端 C4 行为均无本批仓内黑盒载体）

§十（PG6）的机器面由 `activity_close.py` 持有学生复盘 renderer、内部绑定与 plan 前置校验，
`test_022_close_roundtrip.py` 锁定学生正文零 ID/SHA、结果含义、可选动作、显式 tuple 及 route
冲突写前失败；`contract_test_support.py` 锁 canonical 载体与 Operator/Learner 边界。活模型是否
把 Operator payload 另行念给学生仍属活模型边界，不冒充机器已经覆盖。

enforcement: tool=70_tools/activity_close.py
enforcement: tool=70_tools/test_022_close_roundtrip.py
enforcement: tool=70_tools/contract_test_support.py
enforcement: context=50_playbook/session_close.md#生成 pending、严格决策并事务写回
enforcement: prose_accepted（理由：工具 renderer 可机验；活模型是否另行泄漏 Operator payload 留 A9）

## 六、rule_migration

本批纯追加（canonical 新建 + 五文件最小指针 + 登记），无删除、合并、迁址或退役条款：
`not_applicable`。未来把各流程文件中的停顿描述下沉到本文件（工单 PG-R001 sink）时，
须先提交精确迁移表 amendment，不得引用本节作概括授权。

## 七、安装与首启呈现规格（PG2）

本节治理**安装与首次规划**这一段学生旅程「怎样被看见」。流程正文仍归 `first_run.md`
（＋派生视图 `t2ag_flow.md`），安装器本体不在本仓内；本节只裁受众分界、停顿归属与缺省态
的呈现，不复制流程做法。

### 7.1 学生事实的三态判据

学生事实（学习水平、已有基础、目标、可投入时间、工具习惯、Course Type、Learning Mode、
真实入口）只有三态，任何呈现与落盘都必须能判到其中一态：

| 态 | 判据 | 内部形状 | 学生可见措辞 |
|---|---|---|---|
| 已提供 | 学生本人自述过 | 学生原话的映射值 | 直接复述其内容 |
| 尚未提供 | 学生未自述，系统也不需要为推进先行假定 | `not_provided` | 「尚未提供」 |
| 公开假设 | 学生未自述，但推进需要一个先行假定 | 具体值＋在方案中标注为假设 | 进方案「假设」栏并说明可改 |

机器边界：**机器默认值只能充当运行参数**（时区、cutoff、Agent 编队、提示闸门、结课偏好
等「机器怎么运行」的字段），不得占据「已提供」态，也不得被复述成学生自述。一个字段若
既无自述又被系统填了值，它要么是运行参数，要么必须以公开假设的身份出现——不存在第三种
合法形态。缺省态的落盘形状由 `70_tools/answers.schema.json` 与 `70_tools/t2ag_init.py`
拥有（三处同源：enum、默认值、可见标签）；本节只裁「什么算已提供」与「未提供如何被看见」。

### 7.2 安装与首启的停顿结构

- **停顿 A｜补充条件**：注册资料与规划条件是**同一次**自然对话，不得拆成两轮阻断问答。
  学生给够信息或明确让系统先拟方案即结束该停顿；空回复不得触发追问，也不得回到本停顿补问。
- **停顿 B｜审阅方案**：完整方案正文（含公开假设）与课程类型、适用模式一次展示后等待
  确认或修改。
- 其间与其后的内部落盘（`init` → `new-course` → `new-group` → 方案映射 → `activate-group`
  → refresh → doctor）**不产生学生停顿**：命令成功回执、planned→active 迁移与非阻断
  Doctor 警告都不是确认门（铁律 §二.1）。
- **完成呈现不是又一个停顿**：回执直接给出并就地开始第一件事，不再设「是否现在开始」——
  该等待答不出铁律 §二.4 的「不同回答会改变什么」，学生已在停顿 B 确认过同一件事。

本节**不规定**任何旅程的停顿数量预算：PG0 的逐旅程预算表仍是产品假说，未经产品裁决不升
规则，本文件不复制该表。本节同样不触碰教学块间等待（PG-D1）与来源展示层级（PG-D2）：
现行宪法明确要求的独立等待在 PG-D1 裁决前一律保持，施工方不得私自合并。

### 7.3 发行源保留契约（F09）

安装器复制出的发行源目录**默认保留**。首启完成回执用一句话告知它可以稍后自行清理，
**不主动询问是否删除**；删除只在学生自己提出时发生，届时走一次明确的破坏性确认——
安全门的强度不因体验优化下降（铁律 §二.8）。面向陌生学生的公开入口（仓根 `README.md`
与各 Edition 入口）对本契约只能投影同一句话，不得各自规定不同的默认或另设询问
（铁律 §二.7）。

**本节 rule_migration**：`not_applicable`——纯追加，无删除、合并、迁址或退役条款；
`first_run.md` 与 `t2ag_flow.md` 的对应正文在同批内同步为一致表述，不留旧默认档位。

## 八、建课与建组呈现规格（PG3）

本节治理**建课与建组**这一段学生旅程「怎样被看见」。流程正文仍归 `new_course_init.md` 与
`course_group_rules.md`，容器语义归后者 §4.1–§4.3；本节只裁哪些参数必须由学生说出口、
`planned → active` 算不算一次停顿、拒绝与提示以谁的身份出现。

### 8.1 语义参数必填、无默认（通则）

铁律 §二.2「事实无默认」在 CLI 面的落法：**会改变学习事实的语义参数不得有 CLI 默认值**。
判据不是「这个参数有没有被填过」，而是**默认值会不会替学生答一次**——所以危险的恰恰是
**有默认值的那些**，无默认值的参数至多让命令失败，不会伪造一次确认。

| 判据 | 通则 | 现行落点 |
|---|---|---|
| 有唯一正确答案、模型猜不出 | **必填、无默认** | `--source-language`、`--container-mode` |
| 默认值会替学生答一次学习事实 | **必填**（默认值即冒充确认） | `--course-type`、`--entry`、`--verification-status` |
| 没有唯一正确答案、须仪式议定 | **不设参数**，模板留可见 `TBD` | 三个容器参数（`course_group_rules.md` §4.1） |
| 有互锁不变量机械护住 | 可留默认 | `--lifecycle`（与 `--entry` 互锁即拦） |

`--verification-status` 是其中最强的一条：它的默认值直接断言「有人核验过」，那是关于世界的
主张，工具无权代学生做出——默认即伪证。`--learning-mode` **不在此列**：它已有双向运行时
强制（Mastery 缺则拒、非 Mastery 给则拒），argparse 再设必填会废掉 Project/Praxis 建课。

必填不等于把参数摆到学生面前：**这些答案在停顿 B 的方案里已经确认过**，命令只是把已确认
内容如实写下来。学生看不到 flag 名，看到的是方案里的课程类型、入口与题源来历。

### 8.2 `planned → active` 是内部公证，不是第二次决策（F07）

`planned → active` 是**已确认方案的内部公证**，不构成 Meaningful Pause（铁律 §二.1）。
preflight 拒绝时的默认出口是**内部修正**——把不合格的证据改对再跑一次，仍然不是停顿。
只有当拒绝原因是「已确认方案缺少会实质改变路线的信息」时，才回到**停顿 B｜审阅方案**，
并且以**方案修订**的形式呈现：给出改动后的方案正文请学生审阅，
**不得表述为「请确认激活」或「同意激活」**——那是把内部公证伪装成学生决策
（判例见 `course_group_rules.md`「误当成第二次用户决策」）。

### 8.3 拒绝一次报全，不挤牙膏

激活前置检查**一次求值、一次报全**：所有不合格判据在同一次拒绝里列全，而不是首条即抛。
理由是呈现的：逐条抛出会把一次拒绝拆成三轮「改一处—再跑—又红」，每一轮在学生侧都像
一次新的失败。判据与 Doctor **严格同源，不加严不放宽**——preflight 加严会拦下 Doctor
本会放行的组，放宽则只是把同一个 FAIL 推迟到下一次 Doctor。

判据前移的准入是两段测试，两段都过才收：**(a) 只在 active 态点火**，
**(b) 激活时点可判**（不依赖流逝时间或运行史）。因此止损锚与碑账对账两条前移
——它们原本要等激活后的下一次 Doctor 才点火，也就是「今天成功、明天必 FAIL」；
而全组循环里的条款（planned 组照报）与 14 天停滞分诊都不收。
**排除不是放宽**：未前移的条款强制面原样留在常驻 Doctor。

三份文件的落盘顺序是**倒置**的：`review.md` → `calendar.md` → `plan.md` 最后，
因为 `plan.md` 的 `status: active` 是 Doctor 判定「本组已激活」的唯一依据，最后写意味着
中途失败留下的仍是一个诚实的 `planned` 组。**这不是事务原子性**：崩在两次写之间仍会留下
写了一半的组。它买到的东西更窄，也只该照这个窄度声称——**失败不会留下一个自称 active 的组**。

### 8.4 拒绝与提示是 Operator 面

preflight 的判据代号（`dwell_budget_missing` 之类）、路径清单、blocker/notice 分级都是
**Operator Surface**，按铁律 §二.3 与 §二.6 处理：默认不进学生文案，学生看到的是「方案里
的这一项还缺一个数，需要在方案里定下来」这类自然语言，只有学生主动要诊断或发生阻断处理时
才展开内部形态。工具 stdout 一律走内部回执标记；**notice 不是停顿**，它连拒绝都不是。

**本节 rule_migration**：`not_applicable`——纯追加，无删除、合并、迁址或退役条款。
§8.1 的通则是把 `new_course_init.md` 已有的 `--source-language` 单例升为判据表，
原文保留、未删未改址。

## 九、本地恢复呈现规格（PG4）

本节拥有本轮恢复意图的 canonical 分类；流程动作仍归 `lesson_recover.md`。分类键固定为
`turn_intent`，不得与活动 CLI 的 `--intent {recover, close}` 或 Context 的
`explicit_continue_*_required` 门旗混称。合法 value 恰为：

| `turn_intent` value | 判据 | 本地 Meaningful Pause 与出口 |
|---|---|---|
| `explicit_continue` | 学生本轮已明确要求从权威恢复点继续 | 不再索取一般继续授权；简述恢复点后执行下一权威动作 |
| `ambiguous_resume` | 学生要求恢复，但尚未表达继续还是复习 | 停一次，一次给全「继续／复习」两个会改变结果的选择 |
| `conflict_resolution` | route、progress、Activity、当前页资产或 Scope 身份冲突 | 冲突必停；先用自然语言解释可选动作及影响，内部 ID/schema 按需展开 |
| `new_scope` | 请求离开当前恢复范围，进入新的课程、活动或内容范围 | 不复用旧继续授权，转入该新范围的正常授权门 |

本表只治理**本地**恢复。云恢复的共享 pause owner 与冲突翻译为 PG-F06 的
`dependency_closed → C4`，本批不得写成已经跨层闭合。恢复停顿属于真实授权边界，
`gate_visibility: quiet` 不豁免；旧对话授权也不跨恢复点复用。

**本节 rule_migration**：`not_applicable`——给既有本地行为建立分类与 owner，零删除、
零迁址；`lesson_recover.md` 只保留映射指针，不复制本表定义。

## 十、结课 Learner Surface 与显式安全对象（PG6）

结课学生版只展示完整复盘正文、结果含义与学生可选动作。`pending_event_id`、body SHA、
presentation SHA、authorization receipt、schema 与内部状态码仍由系统严格绑定，但默认留在
Operator Surface；学生主动要求诊断或发生绑定冲突时，才按 §二.3／§二.6 渐进展开。

学生版必须把完成态翻译成自然语言，不直接展示 `completed` / `closed_incomplete`；末尾动作
不超过三项：确认相应终态、指出需要修订的复盘内容、继续补齐或暂不结课。学生简短说“结课”
仍只能绑定当前唯一、已完整展示且无漂移的 pending；隐藏 tuple 不降低歧义、漂移、修订失效或
direct-user terminal 授权检查。

`activity_close.py` 的 `--plan-pending` 与 `--plan-decision` 必须显式给齐 course/type/id，并在
任何 plan 文件产生前复用唯一现行 route；缺项、部分 tuple、课程或 route 非法、type/id 与
route 冲突均写前失败，不扫描全仓猜候选。`--plan-reopen` 同样须显式给齐 tuple，但可指向同一
课程 ledger 中的历史终态活动，不强制等于当前 route。`--parse-confirm` 与 `--apply` 不消费
course tuple；真实课程 terminal apply 仍是 RT3，本节不构成执行授权。

**本节 rule_migration**：`PG-R003 = narrow`。旧载体 `session_close.md` 步骤 4 的 exact tuple
默认展示收窄为内部绑定；新 owner 为本节，流程消费方仍为 `session_close.md` / `activity_close.py`，
等价门由完整学生复盘、严格内部 tuple 与 `test_022_close_roundtrip.py` 写前负例共同闭合。

## 十一、Operator Result Envelope（PG7）

会进入 Agent 上下文的 init、Doctor、state refresh、context、activity close 与 cloud sync 六类
CLI，在原 stdout 之外统一输出中性 `t2ag.operator_result.v1` sidecar：`audience` 固定为
`operator`，机器码、Operator message 与 `structured_result` 分字段。sidecar 走 stderr，既有
machine-readable stdout 保持兼容；不得把 stdout 或整个 envelope 原样送给学生。

中性 envelope owner 是 `70_tools/operator_result.py`，它不持有学生措辞，也不 import journey
renderer。需要学生回执时，上层编排只把 `structured_result` 交给
`70_tools/learner_journey.py`；Doctor 保持纯 Operator producer，不调用、消费或拥有 renderer。
错误 family 在六个 CLI 边界稳定为 `T2AG.<TOOL>.ERROR`，内部 finding code 仍由各领域 owner
持有，不在本节重建第二套枚举。

enforcement: tool=70_tools/operator_result.py
enforcement: tool=70_tools/test_operator_result_contracts.py

**本节 rule_migration**：`not_applicable`——只为既有 CLI 输出增加并行 sidecar；原 stdout、
内部算法、写序、check 集与学生文案均不删除、不迁址。
