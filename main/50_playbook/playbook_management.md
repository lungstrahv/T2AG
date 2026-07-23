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

## 四、核心/保护 playbook

T2AG 用 `core-playbook` 语义保护高价值流程。满足任一条件时，在文件顶部写明精确标记 `**保护级别**：core-playbook`：

- 用户明确要求长期保留。
- 管理其他 playbook、journal、memory、problemlog 生命周期，属于 meta-playbook。
- 高复杂度：开发中至少 3 次重大修订，且最终流程至少 12 个关键步骤。
- 13 天内被触发 5 次以上。

核心 playbook 不应被自动归档、合并或大幅改写；如需修改，必须在 `t2ag_changelog.md` 中说明原因。核心保护不等于不可编辑，它只阻止自动清理和随意合并。

## 五、发行版同步纪律

- 每个标记为 `core-playbook` 的文件都必须存在于 main、skeleton 与 lite，文件正文保持一致。
- core-playbook 不得写入真实学生姓名、绝对路径、当前课程进度、固定 commit 或私人远端地址；实例参数从运行时文件读取。
- 新增或重大修改 core-playbook 时，同一批次同步三版本，再分别运行 doctor。
- 三仓同处一个工作区时，doctor 比较 core-playbook 文件集合与 SHA-256；缺失或正文分叉均为 FAIL。独立发行时只检查本地必需文件。
- skeleton 是通用模板和流程的唯一模板源；main 吸收通用规则并保留实例数据。
- lite 是由 main 生成的线上模型审查快照，可省略教材二进制、环境、缓存和生成资产，
  但不得省略审查所需规则、实例状态或 core-playbook。
- lite 不得反向成为规则源；线上模型的修改只能以审查建议返回，再由 skeleton/main 裁决。

---

## 六、维护流程

1. 先查 `main/50_playbook/` 是否已有同类流程。
2. 若已有流程，只更新旧文件，不重复创建。
3. 若来自系统问题，先确保 `t2ag_problemlog.md` 有案例记录。
4. 按本文件门槛判断是否值得提炼。
5. 新增或重大修改 playbook 后，同步更新：
   - `main/t2ag.md` 的当前 playbook 文件表。
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
