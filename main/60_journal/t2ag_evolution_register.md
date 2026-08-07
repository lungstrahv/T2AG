# T2AG Evolution Register（t2ag_evolution_register.md）

> **职能**：T2AG **决策生命周期登记簿**——记录观察、讨论、决定与实施归档。
> **保护级别**：journal（回看层，不是真相源）
> **创建**：2026-07-23
> **canonical 改名**：2026-08-07（原 `t2ag_evolution.md`；旧路径 redirect）
> **维护规则**：新增观察条目需用户明确要求；不得自动写入。
> **与 ADR**：本文件拥有 `observing → discussing → decided → archived` 生命周期；
> ADR（`docs/adr/`）是可移植架构决定产物，不复制状态机，须双向回指本 Register。

---

## 边界说明

本文件与其他记录文件的职责划分：

| 文件 | 记录什么 |
|---|---|
| `00_core/t2ag_problemlog.md` | 已经发生的故障、矛盾、根因和修复 |
| `00_core/t2ag_changelog.md` | 已经完成的修改 |
| **本文件（Evolution Register）** | 决策生命周期：观察、取舍、决定、归档 |
| `docs/adr/` | 架构级 EV 提升出的稳定、可移植决策正文 |
| `00_core/domain_model.md` | 当前有效领域定义 |

本文件**不是**：

- 领域模型真相源
- problemlog
- changelog
- ADR 正文仓（ADR 在 `docs/adr/`）
- 已批准的迁移方案
- 自动修改系统的授权

观察条目不改变任何现有规则、结构或文件。只有经过正式批准批次后，观察才可能转化为行动。
不是每个 EV 都生成 ADR；仅跨模块、难逆转、改变责任/信任边界或跨项目可复用的架构决定才提升。

---

## 条目格式

```text
### EV-XXXX｜标题

- ID：EV-XXXX
- 日期：YYYY-MM-DD
- 状态：observing / discussing / decided / archived
- decision_class：observation | architecture | implementation | policy（可选）
- adr_refs：[ADR-0001]（可选；architecture + decided/archived 新条目应有，或填 adr_exception）
- 观察内容：...
- 已有证据：...
- 当前优势：...
- 当前代价或结构张力：...
- 待观察指标：...
- 可能触发调整的条件：...
- 尚未作出的决定：...
- 关联文件：...
```

---

## 状态机与出口条款

| 状态 | 含义 | 出口 |
|---|---|---|
| `observing` | 纯观察，不行动 | → discussing（用户发起讨论） |
| `discussing` | 正在讨论取舍 | → decided / observing（讨论未达成共识回退） |
| `decided` | 已作出决定，待落地 | → archived（落地完成后转化） |
| `archived` | 观察已转化为行动，本条目封存 | 终态 |

### `decided` → `archived` 转化流程（强制）

1. 立 changelog 批次（在 `t2ag_changelog.md` 记录具体修改）
2. 执行对应文件修改
3. EV 条目状态改为 `archived`，追加一行：`- **落地指向**：changelog [YYYY-MM-DD] 批次「XXX」`
4. 当月 `60_journal/YYYY-MM.md` 索引留一行：`EV-XXXX decided → archived，见 changelog`

> `decided` 状态不得无限期停留。若决定后 30 天未落地，doctor 报 WARN。

---

## 月度索引联动

- 新增 EV 条目时：**不强制**在当月 `YYYY-MM.md` 留痕（evolution 自身可检索）。
- `decided` 转化时：**强制**在当月索引留一行（确保决定可追溯）。

---

## 观察条目

### EV-0001｜Markdown 的灵活性与结构复杂度

- **ID**：EV-0001
- **日期**：2026-07-23
- **状态**：`observing`

#### 观察内容

T2AG 全部领域对象、规则、状态和引用关系均以 Markdown 纯文本承载。Markdown 提供了极低的使用门槛和极高的表达灵活性，使得系统可以在没有数据库、没有编译器的情况下由人和 AI 共同维护。随着对象数量增长和引用关系复杂化，Markdown 开始承担 ID 管理、外键引用、状态机、引用完整性和跨文件一致性等职责，这些职责传统上由数据库或类型系统保证。

#### 已有证据

- 第一阶段冻结过程中，一次语义修正（R 定义 + FieldPractice 语义）需要同步修改 domain_model、general_learning、_README、naming_conventions、memory、doctor、legacy_r_registry 共 7 类文件 × 3 发行版。
- doctor 从通用检查脚本演化为包含 R 绑定检查、培养方案检查、命名检查、皮肤检查等多职责的单体文件。
- 三发行版（main/skeleton/lite）的通用文件需要 SHA-256 一致，实例文件需要隔离——这一约束完全靠人工和 doctor 脚本维护，无编译期保障。
- state_refresh 需要遍历多个真相源和缓存，任何新增对象类型都会增加其检查面。

#### 当前优势

- 零依赖：任何文本编辑器和 AI 都可以读写，无需安装数据库或运行时。
- 可审计：Git diff 即可看到全部变更历史。
- 低门槛：学生可以直接阅读和修改任何文件。
- AI 友好：大语言模型可以直接理解和生成 Markdown。
- 快速迭代：无需 schema migration，结构变更即时生效。

#### 当前代价或结构张力

- 一次状态变化可能需要修改多个文件（真相源 + 缓存 + 索引 + 注册表）。
- 引用完整性无编译期保障：删除或重命名文件后，引用方不会自动报错。
- 三发行版同步是人工纪律，漂移只能在 doctor 运行时发现。
- 随着对象类型增加，doctor 单体文件复杂度线性增长。
- Markdown 中嵌入的 YAML frontmatter、JSON 片段和 ID 约定缺乏统一的 schema 验证。
- 新对象类型需要在多处登记（结构清单、doctor、naming_conventions、_README），遗漏不会立即报错。

#### 待观察指标

1. 一次状态变化需要修改多少文件
2. doctor 假绿出现次数（检查通过但实际状态不一致）
3. 新对象需要复制多少份定义
4. main/skeleton/lite 漂移次数（doctor 发现三版不一致）
5. 结构维护是否明显挤压实际教学时间
6. 一次结构变更需要同步多少缓存、索引和注册表
7. Markdown 是否开始承担过多 ID、外键、状态机和引用完整性职责

#### 可能触发调整的条件

- 单次状态变化需修改文件数稳定超过 5 个
- 一个季度内 doctor 假绿 ≥ 2 次
- 三发行版漂移在一个季度内 ≥ 3 次
- 用户反馈结构维护占用教学准备时间超过 20%
- 新增对象类型时登记遗漏导致运行期错误 ≥ 2 次
- 需要跨文件事务性更新（多文件必须原子生效）的场景出现

#### 尚未作出的决定

- 是否引入轻量 schema 验证层（如 JSON Schema 校验 frontmatter）
- 是否将 doctor 拆分为模块化检查器
- 是否引入文件间引用的自动完整性检查
- 是否将部分高频状态迁移到单一状态文件
- 是否引入三发行版自动同步工具（替代人工复制 + hash 比对）
- 是否对 Markdown 中的 ID 和引用关系建立集中索引

#### 关联文件

- `00_core/domain_model.md` —— 领域对象定义
- `50_playbook/general_learning.md` —— R 绑定规则
- `70_tools/t2ag_doctor.py` —— 确定性检查器
- `70_tools/t2ag_state_refresh.py` —— 状态一致性刷新
- `50_playbook/naming_conventions.md` —— 路径与命名约定
- `main/t2ag.md` 第三章 —— 结构清单
- `docs/handoffs/T2AG_HANDOFF_2026-07-22_FINAL.md` —— 第一阶段冻结交接

---

### EV-0002｜完整 Markdown 对象分层迁移

- **ID**：EV-0002
- **日期**：2026-07-23
- **状态**：`decided`

#### 决定内容

1. 继续纯 Markdown 作为领域对象主存储；JSON/YAML/Python 只承担辅助注册、配置、检查和缓存生成。
2. 采用完整对象分层：CourseDefinition、CourseRun、ActivityRecord、FieldPractice、G/R 执行绑定各有独立目标容器。
3. FieldPractice 属于 Case，可不关联课程独立存在，可关联 0..N 个 Project/Praxis CourseRun；CourseRun 只引用并消费证据，不拥有 FieldPractice。
4. 课程只通过指针关联实践；课程结课或解除关联不删除实践和证据。
5. 物理迁移分批执行：本批次只建立结构契约和空骨架，不移动任何现有实例。
6. 同一对象不得同时在新旧路径存在；后续按单对象迁移切换唯一真相源。

#### 已有证据

- 第一阶段冻结完成，R 语义、FieldPractice 定义、G/R 职责已稳定。
- 五场景结构走查确认目标目录结构可行，无破坏性冲突。
- 当前旧路径继续有效，新目录为空骨架。
- doctor 三版已实现按物理位置的对象类型检查、引用完整性、碰撞检测和 ID 唯一性。
- state_refresh（main+skeleton）已支持双路径读取和碰撞守卫；lite 为只读桩。
- doctor 对象分层检查（2A）初版曾存在空索引引用、发现边界、跨 Case 和物理层级假绿；经多轮反例修复后于 2026-07-23 通过 Codex 独立复审。
- 2B 封口完成：state_refresh CourseDefinition 正式载体验证、doctor active handoff 元数据解析与索引一致性检查；经 Codex 独立复审通过。
- 2C 契约落地：CourseDefinition prerequisites（单行数组、无重复/自引用/循环、存在性含旧路径兼容）、ActivityRecord upgraded_to_course_run（— 或同 Case CourseRun）、FieldPractice evidence_index（实例内安全 POSIX 相对路径指向已存在 .md）；三版 domain_model/README/naming/doctor 同步。

#### 尚未作出的决定

- MATH1205H 试迁移的具体时机和范围（待 Codex 审查通过后执行）。
- 旧目录正式退役条件和时间表。
- 其余实例（IV1001/CS1953/PY1001/MATH1607H/G01/G02/PHIL/DS/P001/P002）的迁移顺序。

#### 关联文件

- `00_core/domain_model.md` —— 领域对象定义（第八节兼容期声明）
- `50_playbook/naming_conventions.md` —— 新对象命名规范
- `50_playbook/new_course_init.md` —— CourseDefinition/CourseRun 两步契约
- `70_tools/t2ag_doctor.py` —— 双路径检查
- `70_tools/t2ag_state_refresh.py` —— 碰撞守卫
- `docs/handoffs/README.md` —— 结构准备批次交接

---

### EV-0003｜method_distillation 二阶回路观察

- **ID**：EV-0003
- **日期**：2026-07-23
- **状态**：`observing`

#### 观察内容

`method_distillation.md`（跨课方法提炼）形态上是骑在多个 mistake_bank 之上的**积累型二阶回路**：
它的输入是多门课错题库的根因，产出是可迁移方法卡，存量叠加到学生的跨课解题能力上。

#### 触发条件

当 ≥2 门课的方法卡出现互相引用时，再讨论是否正式入册为积累型回路实例。

#### 关联文件

- `00_core/pattern_retire_loop.md` —— 复利回路模式定义（演化预留节）
- `50_playbook/method_distillation.md` —— 跨课方法生成、训练、验证与接替

---

### EV-0004｜execution 与 groups 的层级关系

- **ID**：EV-0004
- **日期**：2026-07-23
- **状态**：`archived`

#### 观察内容

当前对象分层设计将 G（课程组）和 R（执行绑定）并列为 `20_execution/` 的子目录，暗示“执行”是父概念、“组”是子类型。
用户认为这个层级关系搞反了：**课程组是组织主体，执行绑定是从属于课程组的操作细节**。
语义上应该是 `20_groups/bindings/`（执行绑定在课程组仓库内），而不是 `20_execution/groups/`（课程组在执行容器内）。

#### 裁决结果（2026-07-23）

**方案 A 执行完毕**：
- `20_execution/` 已删除
- G 留在 `20_groups/`（主体），状态字段标 active/planned
- R 目标容器为 `20_groups/bindings/`
- domain_model、宪法表、doctor 已同步更新
- 设计原则确认：状态不编码进路径，换组 = 改状态字段 + 改指针

#### 当前代价

- 迁移目标路径 `20_execution/groups/` 与用户心智模型不符，可能导致后续执行者困惑。
- 当前 G 实例仍在 `20_groups/`（旧路径），尚未迁移，因此没有实际损失。

#### 可能触发调整的条件

- 兼容期迁移实际执行时（必须决定 G 的物理目标路径）
- 或用户明确要求重新设计执行层结构时

#### 尚未作出的决定

- 是否将 `20_execution/` 整体取消，改为 `20_groups/bindings/`
- 或保留 `20_execution/` 但只放 R，G 留在 `20_groups/` 不迁
- 涉及修宪级别（domain_model + naming_conventions + doctor + 迁移契约）

#### 关联文件

- `20_groups/_README.md` —— 课程组目录说明
- `20_groups/bindings/_README.md` —— R 容器说明
- `00_core/domain_model.md` —— 领域对象定义
- `50_playbook/naming_conventions.md` —— 路径规范

---

### EV-0005｜兼容期收尾序列

- **ID**：EV-0005
- **日期**：2026-07-23
- **状态**：`decided`

#### 决定内容

兼容期迁移按以下顺序推进（每步一个批次）：

1. **`40_practices` 拆分**：
   - 1a：写 `activity_management.md` playbook（实例驱动，以 trading/notes.md 为首个消费者）
   - 1b：执行拆分（P002 → 首个 FieldPractice；trading/notes.md → AR-S002-0001）
2. **`20_groups` 迁移**：等 G02 自然启动时顺手迁，不设时限（另见 EV-0004 层级关系疑虑）
3. **`25_general` 冻结 R 文件**：不迁（registry 已托管，收益为零）
4. **`.recovery` 删除**：永远放最后，需宪法 §8 独立授权

#### 设计原则

- 不为了迁移而迁移，收益为零就不动
- 实例驱动：先有真实消费者再写流程
- 不制造截止日期，等自然触发

#### 关联文件

- `12_activity_records/` —— AR 目标容器（AR-S002-0001 已入住）
- `40_field_practices/` —— FieldPractice 目标容器（FP-S002-0001、FP-S002-0002 已入住）
- `20_groups/` —— G 实例当前位置
- `20_execution/` —— 已合并入 20_groups/（EV-0004 落地）

#### 落地进度

- **步骤 1a**（activity_management.md）：已完成，见 changelog [2026-07-23] 批次「D」前置。
- **步骤 1b**（40_practices 拆分）：已完成。
  - **落地指向**：changelog [2026-07-23] 批次「D（EV-0005 步骤 1b）：40_practices 分拣退场」
  - `40_practices/` 已删除；P001→FP-S002-0002、P002→FP-S002-0001、notes→AR-S002-0001、IV1001_plan→归档。
- **步骤 2**（20_groups 迁移）：待 G02 自然启动。
- **步骤 3**（25_general 冻结）：不迁（registry 已托管）。
- **步骤 4**（.recovery 删除）：待宪法 §8 授权。

---

### EV-0006｜顶层目录数量与嵌套深度的取舍

- **ID**：EV-0006
- **日期**：2026-07-23
- **状态**：`observing`

#### 观察内容

批次 C/D/E 执行后，`main/` 下顶层目录已达 12 个（00_core、10_case、12_activity_records、15_curricula、20_groups、25_general、30_course_definitions、35_course_runs、40_field_practices、50_playbook、60_journal、70_tools）+ bin/skin/cloud。

审美张力：
- 扁平化（多顶层目录）降低导航深度，但增加首屏认知负荷；
- 嵌套化（合并同类目录）减少首屏条目，但增加路径长度和规则复杂度。

当前选择扁平化的理由：每个目录对应一个独立职责域，doctor 检查、playbook 指针和 registry 均按顶层目录寻址，合并会触发大面积引用重写。

#### 触发条件

若 0.2.0 立案时目录数量继续增长（如新增 13_activity_archive 或 45_capstones），则重新评估是否引入中间层。当前不行动。

#### 附件

- [v020_candidate_pool.md](v020_candidate_pool.md) — 路径破坏性变更的历史愿望池（W1–W6；2026-07-26 已结池）。
- [T2AG_0.2.0_STRUCTURE_PLAN.md](T2AG_0.2.0_STRUCTURE_PLAN.md) — 当前单学生结构换代的裁决、映射与施工权威。

---

### EV-0007｜批次调度偏好升格为规范

- **ID**：EV-0007
- **日期**：2026-07-23
- **状态**：`archived`

#### 观察内容

批次 C/D/E2 执行中反复出现同一调度偏好：追加类先行、修改类滞后、审计穿插。同时复审暴露三类静默偏离（范围裁剪未声明、执行方式未声明、WARN 不指名），均源于施工单模板不存在。

#### 裁决（2026-07-23）

偏好升格为正式规范：`50_playbook/batch_workorder_spec.md`。三类批次前置条件差异化、双偏离字段、WARN 指名、commit 协议、三版全量同步、复审打回条件一次成文。

#### 落地指向

- 规范文件：`main/50_playbook/batch_workorder_spec.md`
- changelog：[2026-07-23] 「批次调度与施工报告规范成文」

---

### EV-0008｜doctor 发行版角色模型缺失（豁免权宜）

- **ID**：EV-0008
- **日期**：2026-07-24
- **状态**：`observing`

#### 观察内容

STAGE-0 为使 skeleton doctor 归零，在 **main 的** `t2ag_doctor.py` 增加 skeleton 专属分支：
1. 空 `25_general` 时不要求 `legacy_r_registry` 恰好含 PHIL/DS；
2. `30_course_definitions/_shared/external_resources.md` 列入 skeleton 文件白名单。

复审 F1：skeleton 上「实例缺失」FAIL 本可视为正确的骨架状态；缺的是 **发行版角色期望集**，不是骨架有病。if-skeleton-skip 可接受于两条小规模权宜，但会诱导补丁堆。

#### 触发条件

再出现第 3 条及以上 skeleton/lite 专属豁免，或下一批工具迭代时，立案 `release_type: main|lite|skeleton` 期望集，迁移现有豁免进表，禁止继续散落 if。

#### 关联

- `main/70_tools/t2ag_doctor.py`
- `main/00_core/t2ag_problemlog.md` [2026-07-24 14:00]
- 批次 STAGE-0 施工报告补全稿

---

### EV-0009｜学生共享档案、阅读 AR 分类与双向阅读桥接

- **ID**：EV-0009
- **日期**：2026-07-30
- **状态**：`archived`
- **施工权威**：`T2AG-STUDENT-PROFILE-READING-BRIDGE-20260730`

#### 裁决

1. `main/10_student/profile/` 是学生层共享档案容器；四份档案各自保留既有权威与正文职责，
   不合并为单文件。
2. 阅读学习记录属于 ActivityRecord，canonical 容器为
   `main/10_student/activities/reading/`；只有 Project/Praxis Course 的弹性 binding
   使用 R 课程语义。
3. 辅助阅读系统保有书籍、版本、划线、页记、阅读停点、疑问与知识节点的权威；T2AG
   保有 AR 生命周期、课程进度、Group 容量、课程反思与思维模式的权威。两边只通过
   有界、幂等 JSON 事件交换候选上下文、候选贡献与实际使用回执，任何候选都不得自动
   晋升为课程事实或 mastery。

#### 批次状态

- 批次 P-FIX：已生成 V2 correction evidence，V1 保留并被显式 supersede；事务/恢复负例已通过。
- 批次 A：Main AR-0001 已迁移到 `activities/reading/`；Skeleton 保持空容器，独立迁移证据已生成。
- 批次 C/R/T：六份机器合同及双方实现已施工，自检通过；真实 B001/AR sidecar 未被测试写入。
- 批次 I：固定 `no_create`，未创建 `AR-0002`，未猜测关联 B001。
- `implementation_status=complete`，完整 candidate V 已通过；不可变 candidate report 为
  `docs/handoffs/T2AG_021_VERSION_INDEPENDENT_REVIEW_2026-08-04.md`，SHA-256
  `92194e00259fe7f5d80b1e458196329fbcfe7bd4e1ec1a15dd01f1383e6dd3ea`。
- 本条归档只表示演进项已经落地并通过 candidate V，不等于 release；release 资格仍由外部
  `T2AG_021_FINALIZATION_DELTA_REVIEW_2026-08-04.md` 裁定。

#### 关联

- `main/00_core/t2ag_changelog.md` [2026-07-30] 批次 P
- `main/70_tools/migrate_021.py`
- `main/60_journal/migration_021_profile_operations.json`
- `main/60_journal/migration_021_profile_report.json`
- `main/60_journal/migration_021_profile_operations_v2.json`
- `main/60_journal/migration_021_activity_record_operations.json`
- `docs/design/T2AG_READING_BRIDGE_CONTRACT_V1.md`

---

### EV-0010｜有界 version campaign 与 delta re-review

- **ID**：EV-0010
- **日期**：2026-08-04
- **状态**：`archived`
- **施工权威**：`T2AG-021-FULL-CLOSEOUT-REVIEW-GOVERNANCE-20260804`

#### 裁决

1. `independent_batch` 继续作为默认执行模式；同一版本内边界已冻结的多个 RT1/RT2 单元，
   可以在用户一次批准完整 authorization envelope 后按 `version_campaign` 连续执行。
2. envelope 必须列出 campaign ID、版本、基线、included/deferred scope、仓库、文件范围、
   操作、risk tier、有限 Git checkpoint 计划、RT3 保留项和授权失效条件；它不是无限持续授权。
3. 上一单元完成对应 evidence/recovery checkpoint 后可以继续，不再机械要求逐批 commit；
   `clean ≠ reviewed ≠ released`，recovery checkpoint 永远不能冒充 release snapshot。
4. 首次版本候选必须完整独立复审。后续 finding 只有在输入 manifest 未变且影响闭包可证明时
   才可做 delta re-review，并重跑不可分割全局门。
5. finalization 采用 operator 与 reviewer 分离的 expected-tree 协议；最终 PASS 只写最后生成、
   不可变的外部 reviewer report，不回写目标仓或施工报告。
6. 0.2.2 Activity Close 采用独立 campaign amendment：A–D 和条件性 G 不再逐批索权；E 的
   真实 migration apply 与 F 的 `exercise01` terminal close 是两个独立 RT3 门。

#### 当前状态

- 治理规则已落地，完整 0.2.1 candidate V 已通过；candidate report SHA-256 为
  `92194e00259fe7f5d80b1e458196329fbcfe7bd4e1ec1a15dd01f1383e6dd3ea`。
- 本裁决不实施 0.2.2，不改变当前运行版本。只有 021 完整收口后才解除 022 的前置阻断。
- 本条 `archived` 只表示治理演进项已实施并通过 candidate V；release 资格与 022 前置解除仍
  等待外部 `T2AG_021_FINALIZATION_DELTA_REVIEW_2026-08-04.md`。

#### 关联文件

- `main/50_playbook/batch_workorder_spec.md`
- `main/50_playbook/git_workflow.md`
- `main/50_playbook/remediation_governance.md`
- `main/50_playbook/doctor_contracts.md`
- `docs/handoffs/T2AG_022_ACTIVITY_CLOSE_CAMPAIGN_AMENDMENT_2026-08-04.md`

---

### EV-0011｜Activity ledger、真实 Exercise close 与分级验证

- **ID**：EV-0011
- **日期**：2026-08-05
- **状态**：`archived`
- **施工权威**：`T2AG-022-ACTIVITY-CLOSE-V2-20260804`

#### 裁决

1. Course progress 与 activity ledger 分权：前者拥有 Course 与唯一前台，后者拥有
   Lesson/Exercise 生命周期、pending/CLR、alias、统计、偏好和 next action。
2. Exercise 使用 exerciseNN canonical ID；Udddd 仅作为课程级历史 alias。
3. pending 与 terminal decision 分事务执行；delegated decision 必须保存授权来源、原始用户
   连续授权原话、确定性政策输入和 operator 身份，不伪称用户键入未来 hash。
4. Main/Skeleton 使用 V0–V3 最小充分验证；普通优化不得自动升级为完整发布审查，未变化
   evidence 可按 SHA 复用，正式发布候选仍须一次完整独立 V 与有界 FIN delta。

#### 收口状态

- 真实迁移已提交：七门 ledger 建立，U1101 迁移为 exercise01，旧 AT/RV ID 保留。
- 真实 F0/F 已提交：exercise01 为 completed，lesson01 仍为 ongoing。
- exact candidate V 已通过；报告为
  `docs/handoffs/T2AG_022_VERSION_INDEPENDENT_REVIEW_2026-08-05.md`，SHA-256
  `45548a3d66f717df6d92c8c5ae163bc89ca504c55cb9d1e4867e834a615dcffd`。
- 本演进项归档表示实现与候选审查完成；正式本地资格继续由外部 FIN delta 报告裁决。

---

### EV-0012｜Course 教材页资产、窗口备课与可重建缓存驱逐

- **ID**：EV-0012
- **日期**：2026-08-05
- **状态**：`archived`
- **decision_class**：`architecture`
- **adr_refs**：`[ADR-0001]`
- **施工权威（草案）**：`docs/handoffs/T2AG_TEXTBOOK_SOURCE_ASSET_AND_LESSON_PREPARATION_WORKORDER_DRAFT_2026-08-05.md`（状态 `student_confirmed`；≠ campaign 授权）
- **落地指向**：changelog [2026-08-05] 批次「EV-0012 教材页资产与 Lesson Preparation 技术收口」

#### 观察内容

教材原文教学与 `working_pages` 混装导致：跨 Lesson 复制 PNG、结课删除与持久核验冲突、四页窗口与全量备课语义重叠。需要把「严格按原文教」做成可审计证据链，并把页图变为有界可重建缓存。

#### 已有证据

- MATH1607H lesson01/02 窗口 PNG/OCR 哈希重复，单课约 4.2 MiB，PNG≈99%。
- 学生裁决与契约硬化见工单 §0.1–0.2（2026-08-05）。

#### 裁决（历史 decided；保留原文语义）

1. **对象**：`SourceDocument`、`SourcePageAsset`（Course/Book）；`LessonScope`（版本化连续消费页集）、`TeachingWindow`（current + 驻留运行视图）、`LessonMap`（覆盖当前 Scope，禁 mastery）、`LessonPreparationSnapshot`（不可变；Scope 变则新建，可复用 load receipt）。
2. **几何**：正常书含当前页连续 **5–8** 页；默认偏好 `[-1,0,+1,+2,+3]`；书首/末平移。短书 `N<5`：**不阻断**，`short_document`，Scope=全书固定，仅 Window.current 移动。
3. **消费证明**：prepare 工具 load receipt；禁止模型自报。
4. **配额**：Course 聚合 `quota_n=min(3×scope_n,30)` 页图；完整键 `(source_document_sha256,pdf_page_index,render_profile)`；P0=当前 Scope 页图（cache 或 session_temp）不可因配额删。
5. **CacheEviction（方案 B）**：在可重建证明下删除 **Course `book/.cache/**` 内非 P0** 派生页图，**不属于**「真实/受保护资产破坏性删除」RT3；须遵守工单算法（heat_at 排序等）。仍属 RT3 的包括：PDF、核验文本、raw OCR、Lesson 学习证据、`working_pages` 迁移删除、session 外未证明可重建项。
6. **配额满主路径**：B 生效后自动 unlink 非 P0；腾位失败才 session_temp；定义/公式页禁止纯文本默认降级。
7. **路径**：完全改（契约/工具/Doctor）+ MATH1607H 迁移；迁移删除独立 RT3。裁决当时 **未**冻结 campaign；**未**授权批次 A 开工（后续按独立批次施工，见落地结果）。

#### 治理落地（本决定的授权条款）

- `main/50_playbook/batch_workorder_spec.md` §1.2 增加 CacheEviction 例外（Main；Skeleton 同源同步）。
- 自动 unlink **仅在**该条款生效后合法；实现前仍可 dry-run。

#### 落地结果（archived）

已完成（技术闭环，**不**表示 Git/Lite/release）：

1. 产品：domain_model / playbook / prepare（`t2ag_source_pages.py`）/ Context / Doctor / CacheEviction / Main=Skeleton 契约。
2. R1/R2 delta：Snapshot 不可变、Context 新路径不回退、LessonMap 原始字节 hash、activity materialize 幂等等。
3. E0：MATH1607H `source_assets` + Snapshot `PREP-f42fc6760eb7041c` + backup。
4. E apply：exact 30 路径删除；两份 `source_excerpt` RETAIN。
5. F-DEEP：`EV0012_POSTBC_CANDIDATE_01_F_DEEP_CLOSEOUT_REPORT_2026-08-05.md` SHA
   `7E88DE67DAD7D5273B83DA603CC18ED58E9F335108B265071BD7A35FC1899D81`。
6. U4 Gate A：`EV0012_U4_PLAYBOOK_RT2_REPORT_2026-08-05.md` SHA
   `D6A7D178D16FCBC3A5E27B62170CA7E7A65C1888A725030AC5C103A7B8DE884B`。

绑定证据（重算匹配于 Gate B 施工时）：R2 DELTA / E0 / RT3 packet / E apply / F inventory /
F-DEEP 见工单 §1；archived 仅表示决定+实现+实例迁移+技术审计闭环。

#### 关联文件

- `docs/handoffs/T2AG_TEXTBOOK_SOURCE_ASSET_AND_LESSON_PREPARATION_WORKORDER_DRAFT_2026-08-05.md`
- `docs/handoffs/EV0012_U4_AND_GOVERNANCE_TWO_GATE_WORKORDER_2026-08-05.md`
- `main/50_playbook/source_page_assets.md` / `batch_workorder_spec.md`
- `main/00_core/domain_model.md`
- `main/70_tools/t2ag_source_pages.py` / `t2ag_context.py` / `t2ag_doctor.py`

---

### EV-0013｜宿主控制教材教学发送边界

- **ID**：EV-0013
- **日期**：2026-08-06
- **状态**：`discussing`
- **decision_class**：`architecture`
- **adr_refs**：`[ADR-0002]`
- **batch_id**：`T2AG-EVOLUTION-ADR-ADAPTER-20260806`（关联登记；宿主硬门另批）

#### 观察内容

教材教学输出若仅靠 critical 字段与 playbook 自律，模型可忽略 `may_release_action` 等信号直接讲课。真正的决策是宿主级发送边界，而非仅引入 receipt/capability 字段。

#### 已有证据

- critical 曾混响 `ready` + `pending_visual_scan`；0.2.3 已 defense-in-depth：`route_ready` + withhold 可照发正文。
- `host_teaching_egress.py` 与原子测试提供 `lesson_emit` 纯契约（reserve→send→commit），**不是**真实 message interceptor。
- ADR-0002 状态：`proposed` / blocked on host-runtime enforcement。

#### 当前代价或结构张力

- 仓库内字段与 Doctor **不能**拦截对外自由消息。
- 宿主 interceptor / 强制 `lesson_emit` / capability store 尚未落地。
- 不得因本批 EV–ADR 适配把契约锚点误称为已实现硬门。

#### 尚未作出的决定

- 真实宿主 enforcement 是否采用、采用何种接线，须独立决定后才能 `decided`/`archived`。

#### 关联文件

- `docs/adr/0002-host-controlled-textbook-teaching-egress.md`
- `docs/protocol/host-teaching-egress-api.md`
- `docs/protocol/textbook-scope-scan-admission.md`
- `main/70_tools/host_teaching_egress.py`
- `main/70_tools/t2ag_context.py`（route_ready / withhold）

---

### EV-0014｜Evolution Register–ADR 关联适配

- **ID**：EV-0014
- **日期**：2026-08-07
- **状态**：`archived`
- **decision_class**：`policy`
- **adr_exception**：本适配不另立 ADR（不复制决策生命周期；Register 与 ADR README 为契约 owner）
- **batch_id**：`T2AG-EVOLUTION-ADR-ADAPTER-20260806`
- **落地指向**：changelog [2026-08-07] 批次「Evolution Register–ADR 关联适配」

#### 观察内容

仓库已有 ADR-0001/0002 与 Evolution 条目，但缺少统一命名（Register）、双向关联字段、确定性验证与 Lite 对 ADR/Protocol 的审查投影闭包。

#### 裁决（decided）

1. canonical：`t2ag_evolution_register.md`；旧 `t2ag_evolution.md` 仅 redirect（`journal_index: false`）。
2. Register 拥有生命周期；ADR 为可移植架构产物，须 `source_evolution` / `adr_refs` 双向回指。
3. 新增纯验证模块与 Doctor/测试；`sync_lite` 投影 `docs/adr/**` 与 `docs/protocol/**` 文本。
4. 不升版、不宣称宿主硬门已实现；不改写 EV-0001～EV-0011 历史正文。

#### 关联文件

- 工单：`T2AG_EVOLUTION_REGISTER_ADR_ADAPTER_WORKORDER_2026-08-06.md`
- `main/50_playbook/journal_management.md`
- `docs/adr/README.md`
- `main/70_tools/decision_record_contract.py`

---

### EV-0015｜Skeleton 0.2.3 发行卫生（host egress 单元 + memory 版本守卫）

- **ID**：EV-0015
- **日期**：2026-08-07
- **状态**：`archived`
- **decision_class**：`implementation`
- **adr_exception**：发行卫生修补，不另立 ADR（宿主 egress 契约仍归 ADR-0002 / EV-0013）
- **batch_id**：`WO-SKELETON-0203-DISTRIBUTION-HYGIENE`
- **落地指向**：changelog [2026-08-07] 批次「Skeleton 0.2.3 发行卫生」

#### 裁决

1. G1 **B-补**：`host_teaching_egress.py` + 测试整单元同步进 Skeleton（通用契约，非个人实例）。
2. G2：C1 修正 memory 手写 0.2.2→0.2.3；并在 `runtime.version_profile` 增加 memory 当前版本散文守卫。
3. G4：**本单跳过**插图 WebP（D 批延后）；偏好记录为 WebP q85@~1300px。
4. G3（Skeleton 全量再生纪律）未在本单实施。

#### 关联文件

- `main/70_tools/host_teaching_egress.py`、`test_host_teaching_egress.py`
- `main/00_core/t2ag_memory.md`（Skeleton）
- `main/70_tools/t2ag_doctor.py`（`extract_runtime_version` / `check_memory_version_prose`）
