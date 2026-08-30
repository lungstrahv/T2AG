# playbook 管理流程

**保护级别**：meta-playbook

> 本文件是 T2AG「技能固化」文档之一。
> 当模型准备新增、重写、合并或保护某个 `main/50_playbook/*.md` 时触发。
>
> **适用场景**：从 problemlog 提炼流程、维护现有 playbook、判断是否需要新增 playbook、判断某个 playbook 是否属于核心/保护流程。

---

## 一、核心原则

- playbook 是**程序性记忆**，不是事实、日志或记录。
- playbook 保存的是“怎么做一件事的方法”，尤其是经过试错、修订、验证后的流程。
- 能写入 `t2ag_memory.md` 的事实，不等于应该写成 playbook。
- 能写进 `t2ag_problemlog.md` 的案例，也不等于应该立刻写成 playbook。

---

## 二、创建门槛

新增普通 playbook 前，必须同时满足：

1. 不是一次性、临时、实验任务。
2. 至少 6 个关键步骤。
3. 至少 6 次工具调用。
4. 至少经历 1 次纠错、调整或验证反馈。
5. 可泛化，不绑定某个单一课程、文件或临时环境。
6. 7 天内不太可能过时，不能依赖 PR 编号、issue 编号、commit SHA 或当前任务状态。
7. 没有现成 playbook 覆盖同一流程。
8. 能写清楚触发条件、输入输出、复用价值和常见坑。

不满足时，只写入 `t2ag_problemlog.md` 或 `t2ag_memory.md`，不要强行新增 playbook。

---

## 三、关键步骤定义

关键步骤必须满足以下至少一项：

- 产生持久状态变化：写入文件、修改配置、创建资源、更新索引。
- 做出不可逆或高影响的设计决策。
- 执行并验证真实结果。

以下动作默认不算关键步骤：

- 只打开或读取文件。
- 只查询资料、确认用户输入、解释概念。
- 用户取名、头脑风暴、普通讨论。
- 记录、归档、索引、备份；除非记录本身重塑后续决策。

---

## 四、保护级别（三级）

合法标记值只有三个：`meta-playbook`、`core-playbook`、`playbook`。写在文件顶部，
精确形式为 `**保护级别**：<值>`。三值以外即为非法。

### 4.1 meta-playbook（功能判据为主，再生判据为验证推论）

**功能判据**（主）：管理治理对象的生命周期——playbook、journal、memory、
problemlog、changelog、门与规则准入、流程。这是开放式列举，不是封闭枚举。

**再生判据**（验证推论）：从发行投影抽走且没有 canonical owner 即不可再生。项目围绕 meta
再生；共享 meta 必须有唯一 Main 真相源和可验证的下游投影，具体机制只由 §五拥有。

两判据不一致时必须裁决并登记，不得静默沿用。

meta 的保护语义：发行投影按 §五闭合 + 大改默认 diff-patch + 语义迁移须 `rule_migration`。

### 4.2 core-playbook

满足任一条件时标 `core-playbook`：

- 用户明确要求长期保留。
- 高复杂度：开发中至少 3 次重大修订，且最终流程至少 12 个关键步骤。
- 13 天内被触发 5 次以上。

core 与 meta 都不应被自动归档、合并或大幅改写；如需修改，必须在
`t2ag_changelog.md` 中说明原因。保护不等于不可编辑，它只阻止自动清理和随意合并。

对 core-playbook、meta-playbook 与承载硬边界的治理文，版本更新或大改默认
**diff-patch**。删除、合并、概括、迁址、退役规范性正文或改变具名硬边界语义时，
必须登记 `rule_migration`；纯追加、格式与保义澄清可写 `not_applicable`。整文件
重写须先冻结完整迁移表。下沉必须证明新 canonical owner、必要入口指针、消费者与
验证闭包；文件长度、关键词或历史清单只触发复核，不单独构成 finding。完整纪律见
`main/t2ag.md` §6.3 与 `batch_workorder_spec.md` §三第 11 条。

### 4.3 playbook

其余流程手册标 `playbook`。修改走批次，不享受 core/meta 的三仓全同义务
（distribution 轴另单）。

**普通级折旧（2026-08-20 裁，Hermes 前身规则首次着床）**：仅普通级参与——
14 天无带日期引用＝冷门标记（WARN），40 天＝归档候选（WARN）；审查随 doctor
每跑即审，不设独立定时。终点＝归档候选**报告**，处置归宿主（`git mv` 入
`archive/`），**唯一副本不删、永不自动删除**（`batch_workorder_spec.md` §三.5）。
使用率数据源双轨：机器侧＝引用扫描（changelog 节日期／journal 行内日期游标／
handoffs 文件名日期）；会话侧＝结课时在 journal 记
`playbooks_consulted:`（见 `session_close.md` 步骤 1）。从无引用记录＝观测态
INFO，不判冷门——静默阅读测不到，是诚实边界不是证据。meta/core 由上文 keep
条款豁免自动归档；带 `managed_by:` 的受管数据文件与显式豁免清单
（`PLAYBOOK_USAGE_EXEMPT`，豁免即数据）不参与。

```text
enforcement: check=runtime.playbook_usage
```

规范行的机器落点（示例，围栏内）：

```text
enforcement: check=runtime.playbook_taxonomy
enforcement: check=release.playbook_taxonomy_parity
```

## 五、发行投影纪律（唯一操作 owner）

本节是 Main → zh Skeleton / Lite 的唯一操作 owner。宪法只保留单一真相源与可验证投影的
硬边界，流程图只画调用关系；不得在其他载体复制命令、顺序或“镜像仓”规则。

### 5.1 当前 0.2.4 边界

- **Main 是唯一 canonical source**。zh Skeleton 是通用机制投影，不是反向模板源；Lite 是
  Main 的单向脱敏审查投影，也不得反向成为规则源。
- **zh 机制投影**没有全仓 generator。跨发行 H5 必须逐批具名、从已提交的 Main 取显式路径，
  只同步低隐私共享机制与已登记的宪法分节；完成后对具名路径做 byte/SHA 核对。真实实例、
  宿主日志和合法发行身份分叉不得复制。
- **Lite 投影**只由 `main/70_tools/sync_lite.py` 生成：默认命令做 check-only；`--write`
  只接受干净 Main 并全量再生、脱敏、哈希复核。禁止长期手改 Lite。
- **EN 不在本节的 0.2.4 target 集合**；其内容同步另走具名发行批。
- 类级 machine-query artifact manifest 明确列入 **0.2.5**，0.2.4 不新建第二 registry，
  也不得把设计文书冒充已生效机器真相。当前机制以本节、`sync_lite.py` 与既有 Doctor 门闭合。

### 5.2 投影门与顺序

#### 5.2.1 宪法与 00_core 分节同源

`main/t2ag.md` 与 `00_core` 三模型按 `## ` 节比对 SHA；Skeleton 宪法 §6 去实例化是登记分叉，
`AGENTS.md` 因受众不同走文件级豁免。owner=`t2ag_doctor.py` `check_constitution_parity`。
enforcement: check=release.constitution_parity

#### 5.2.2 core/meta 发行完整性

core/meta-playbook 的具名投影集合与应同源正文须完整；低隐私共享文件不得夹带学生姓名、
宿主绝对路径、当前课程进度、固定 commit 或私人远端。enforcement: check=release.core_playbooks

#### 5.2.3 顺序

1. Main 变更先通过定向测试、runtime Doctor 与 state check，再提交具名源路径。
2. 同一具名 H5 内补齐 zh 机制路径；宪法与 `00_core` 按登记分节比对，core/meta-playbook
   按文件比对；`AGENTS.md`、发行身份和脱敏输出只接受已登记分叉。
3. Main clean 后先运行 `python -B main/70_tools/sync_lite.py` 预演；需要更新时再运行
   `python -B main/70_tools/sync_lite.py --write`（可选 `--root <T2AC>`）。
4. `runtime.skeleton_privacy` 与 Lite 全量投影哈希是独立门，任一失败都不得宣称投影闭合。
5. 新增或重大修改 core/meta-playbook 时，完成上述投影与各发行适用 Doctor；线上建议只能
   返回 Main 裁决，不能直接改 Lite 或从 zh 反灌 Main。

### 5.3 DEC-4 A8 rule_migration

| rule_id | 旧位置/动作 | 新 owner/等价门 | 消费方 | 验证 |
|---|---|---|---|---|
| DEC4-PROJ-01 | 宪法 §1.9 “三发行字节同源” → keep 硬边界、sink 操作细节 | 本节 §5.1；宪法只指针 | 所有发行批 | 宪法含 `playbook_management.md` §五指针 |
| DEC4-PROJ-02 | `t2ag_flow.md` 的镜像/cmp 手工路径 → sink | 本节 §5.1–§5.2 | Git/发行流程图 | 流程图含“发行投影 owner”且无“Main ↔ Skeleton” |
| DEC4-PROJ-03 | 本文件原 §五多条分散同步纪律 → rewrite | 本节 §5.1–§5.2；`sync_lite.py`；`runtime.skeleton_privacy` | Main/zh/Lite | A9 mutation + 具名 H5 probe |

未登记删除审查：没有退役单一真相源、隐私、宪法分节同源、core/meta 完整性或 Main clean
硬门；只退役重复的手工镜像表述，并把机器 manifest 的新能力显式切到 0.2.5。

---

## 六、维护流程

1. 先查 `main/50_playbook/` 是否已有同类流程。
2. 若已有流程，只更新旧文件，不重复创建。
3. 若来自系统问题，先确保 `t2ag_problemlog.md` 有案例记录。
4. 按本文件门槛判断是否值得提炼。
5. 新增或重大修改 playbook 后，同步更新：
   - `main/50_playbook/_README.md` 的当前 playbook 文件表。
   - `main/00_core/t2ag_changelog.md`。
   - 必要时更新 `main/00_core/t2ag_memory.md` 的关键决策索引。
6. 若涉及 journal 写入规则，同时检查 `main/50_playbook/journal_management.md`。

### 清理与归档

T2AG 沿用以下治理原则：

- 清理前先预览，不直接删除。
- 优先归档到人工指定位置，而不是永久删除。
- 有复用价值但范围重叠的流程，优先合并成更宽的 umbrella playbook。
- 核心 playbook 不参与自动归档或合并。

---

## 七、关联文件

- `main/t2ag.md` —— playbook 总规则与种子说明。
- `main/00_core/t2ag_problemlog.md` —— 系统/流程案例来源。
- `main/50_playbook/problemlog_maintenance.md` —— problemlog 到 playbook 的升级流程。
- `main/50_playbook/journal_management.md` —— journal 记录边界。
- `main/50_playbook/naming_conventions.md` —— 文件、目录、资产和迁移命名边界。
- `main/00_core/t2ag_changelog.md` —— playbook 规则变更记录。

## 八、rule_migration（W0 冻结件落地）

本批对 §四 为语义扩张（三级着床；无删除条款）。表与工单 §六 同构，行数冻结。

| rule_id | rule_id | 动作 | 新 owner/等价门 | 消费方 | 验证 |
|---|---|---|---|---|---|
| PB-TAX-001 | §四 首句「用 core-playbook 语义保护高价值流程」 | keep（改写为三级总述） | 本文件 §四 | 维护会话 / doctor 分级仪器 | `grep -n "合法标记值只有三个" 50_playbook/playbook_management.md` |
| PB-TAX-002 | §四 条件「用户明确要求长期保留」 | keep | 本文件 §4.2 | 升 core 裁决 | `grep -n "用户明确要求长期保留" 50_playbook/playbook_management.md` |
| PB-TAX-003 | §四 条件「管理…生命周期，属于 meta-playbook」 | keep（升格为独立 meta 定义） | 本文件 §4.1 | 升 meta 裁决 / U-0 | `grep -n "功能判据" 50_playbook/playbook_management.md` |
| PB-TAX-004 | §四 条件「高复杂度 3 次修订+12 步」 | keep | 本文件 §4.2 | 升 core 裁决 | `grep -n "12 个关键步骤" 50_playbook/playbook_management.md` |
| PB-TAX-005 | §四 条件「13 天内触发 5 次以上」 | keep | 本文件 §4.2 | 升 core 裁决 | `grep -n "13 天内" 50_playbook/playbook_management.md` |
| PB-TAX-006 | §四「不应被自动归档…」段 | keep（适用面扩 core+meta） | 本文件 §4.2 | 归档/合并闸 | `grep -n "core 与 meta 都不应被自动归档" 50_playbook/playbook_management.md` |
| PB-TAX-007 | §四 diff-patch / rule_migration 段 | keep（适用面明确 core+meta） | 本文件 §4.2 | 施工单 / 复审 | `grep -n "core-playbook、meta-playbook 与承载硬边界" 50_playbook/playbook_management.md` |
| PB-TAX-008 | §五 六条发行纪律 | keep；新增 meta 条款 | 本文件 §五 | 三发行同步 / doctor | `grep -n "meta-playbook" 50_playbook/playbook_management.md` |
| PB-TAX-009 | §六「t2ag.md 当前 playbook 文件表」 | keep（改指 `_README.md`） | 本文件 §六 | 维护会话 | `grep -n "_README.md" 50_playbook/playbook_management.md` |
