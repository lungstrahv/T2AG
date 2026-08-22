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

**再生判据**（验证推论）：从 skeleton 抽走即不可再生。项目围绕 meta 再生；
skeleton 必含全部 meta，三发行字节同源。

两判据不一致时必须裁决并登记，不得静默沿用。

meta 的保护语义：skeleton 必含 + 三仓字节全同 + 大改默认 diff-patch + 语义迁移须
`rule_migration`。

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

## 五、发行版同步纪律

- 每个标记为 `core-playbook` 的文件都必须存在于 main、skeleton 与 lite，文件正文保持一致。
- 每个标记为 `meta-playbook` 的文件都必须存在于 skeleton，且 main / skeleton / lite
  三仓字节全同。
- 宪法与 00_core 模型**不走文件级字节同源，走分节同源**：`main/t2ag.md` 与
  `00_core/` 三模型按 `## ` 节比对 SHA（Skeleton 宪法 §6 去实例化是合法分叉，以
  节级豁免带理由登记；`AGENTS.md` 受众不同走文件级豁免；2026-08-21 D1–D3 裁）。
  owner=`70_tools/t2ag_doctor.py` `check_constitution_parity`。
  enforcement: check=release.constitution_parity
- core-playbook 不得写入真实学生姓名、绝对路径、当前课程进度、固定 commit 或私人远端地址；实例参数从运行时文件读取。
- 新增或重大修改 core-playbook 时，同一批次同步三版本，再分别运行 doctor。
- 三仓同处一个工作区时，doctor 比较 core-playbook 文件集合与 SHA-256；缺失或正文分叉均为 FAIL。独立发行时只检查本地必需文件。
- skeleton 是通用模板和流程的唯一模板源；main 吸收通用规则并保留实例数据。
- lite 是由 main 生成的线上模型审查快照，可省略教材二进制、环境、缓存和生成资产，
  但不得省略审查所需规则、实例状态或 core-playbook / meta-playbook。
- **一致性预演**：`python -B main/70_tools/sync_lite.py`（默认只读）。
- **再生机制（A 案）**：`python -B main/70_tools/sync_lite.py --write`
  （可选 `--root <T2AC>`）。全量清空后重建；**main 工作区必须干净**
  （工具默认拒绝脏树；施工期只有经明确裁决才可追加 `--force`）。
  再生结束全量哈希核对投影文件。禁止手改 lite 当长期维护面。
- lite 不得反向成为规则源；线上模型的修改只能以审查建议返回，再由 skeleton/main 裁决。

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

| rule_id | 旧位置/原文锚点 | 动作 | 新 owner/等价门 | 消费方 | 验证 |
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
