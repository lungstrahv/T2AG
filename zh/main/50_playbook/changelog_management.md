# Changelog 管理（漂移留痕与不腐烂）

> **职能**：规定 `main/00_core/t2ag_changelog.md` 的**验证层**——条目必须可复算，状态漂移必须留痕。  
> **保护级别**：meta-playbook（与 `handoff_management.md` 同级；约束跨会话、跨平台的记录纪律）。
> **不做什么**：不证明「该记的都记了」（完整性 / L5 不可达）。记录的输入是人的判断，不是仓库状态，故 L4「可确定性再生成」路线天然不通。  
> **Canonical owner（验证层）**：本文件。出单方义务与执行方硬规则仍分别保留在 `batch_workorder_spec.md`（见文末 rule_migration）。

---

## 一、要证明什么

两条独立目标，**不得与「哪些形式算数」混写**：

1. **漂移留痕**  
   仓库的**锚定状态**变了，就必须有对应 changelog 条目记录这次变化（或显式说明为何不记——后者仍是一条可审计记录，不是沉默）。

2. **不腐烂**  
   条目里写下的**可复算断言**，在日后抽验时仍然成立。

明确**不证明**：

- 不证明「该记的都记了」；
- 不证明条目叙事是否完整、教学判断是否正确；
- 不把「有 changelog」等同于「发布合格」或「已复审」。

---

## 二、哪些形式算数

复算来源的**形式清单直接复用** `handoff_management.md` §5.6.2，**不另造第二张表**。  
接手方只需学一套 `断言 ← 命令` 语法。

### 2.1 与交接断言的差异约束（changelog 专用）

| 断言类 | 约束 |
|---|---|
| **锚定断言** | 只接受「**repo + python 即可复算**」的形式（零 git 依赖：不得用 `git log` / `git status` / commit hash 作为锚定量）。默认候选见施工单 U2 裁决；落地后由 doctor 对照**最新条目**的声明值与实测值。 |
| **佐证断言** | 条目特有、指向仓库的可复算断言（典型：`grep` 命中、路径存在、工具子命令输出）。形式仍落在 §5.6.2 清单内。 |

格式与交接相同：`断言 ← 复算命令`，命令须可在接管方环境直接粘贴执行。

---

## 三、条目结构

每条 changelog 条目（`## [日期] …` 及以下正文）在叙事之外，携带一个影响面块：

```markdown
#### 锚定断言（必填）
- runtime plan sha256 = <值> ← `python -B main/70_tools/t2ag_doctor.py --profile runtime | head -1`
- runtime checks = <值>      ← 同上

#### 佐证断言（选填，条目特有）
- <断言> ← <复算命令>
```

> 锚定块字段集合（学生 2026-08-07 已批）：**A+B+C**（runtime plan sha256、runtime checks、doctor_checks 键集合 sha）；**排除 D/E**。完整复算命令见 U2 报告。U3 落地前本结构为规范性约定，doctor 尚未自动对照。

### 3.1 判定语义（分写）

| 类 | 谁判定（U3 后） | 失败时 |
|---|---|---|
| **锚定** | doctor 取**最新** changelog 条目的声明值，与当轮实测比对 | 不等 → WARN「状态漂移无记录」，消息须含**声明值与实测值两个数**（WARN 不指名等于没报） |
| **佐证** | doctor 抽验条目中的 `grep` 类（或其它已登记）复算命令 | 命中为零 → WARN「条目已腐烂」，须指名**条目标题与失效断言原文** |

### 3.2 与既有前言义务的关系

`t2ag_changelog.md` 前言仍要求：按需展开；追加条目时同步更新 `t2ag_memory.md` 摘要；并对超出 memory 节预算的旧条目做下沉。  
本 playbook **复述为规范性条款**（keep，不 sink 前言原文）：

- 新条目写入后，须同步更新 memory「最近变更摘要」指针；
- 历史 changelog 行、memory 历史摘要行**不改**（`batch_workorder_spec.md` 硬规则 4）。

---

## 四、rule_migration（本批执行表）

新建本文件成为 changelog **验证层** canonical owner；既有约定分布在出单方与执行方两侧，**全部 keep**，不 sink 到单一文件。

| rule_id | 旧位置/原文锚点 | 动作 | 新 owner/等价门 | 消费方 | 验证 |
|---|---|---|---|---|---|
| changelog 前言「按需展开 / 追加条目时同步更新 memory 摘要」 | `grep -n "追加条目时同步更新" main/00_core/t2ag_changelog.md` | **keep**（前言留原文，不动历史行）+ 在本文件 §3.2 复述 | `changelog_management.md` | 全体维护会话 | `grep -n "memory 摘要" main/50_playbook/changelog_management.md` |
| `batch_workorder_spec.md` §二.5「登记节：changelog 草稿」 | `grep -n "changelog 草稿" main/50_playbook/batch_workorder_spec.md` | **keep**（出单方义务留在原处）+ 反向指针（步骤 3b） | `batch_workorder_spec.md` | 出单方 | 双向 grep 命中 |
| 硬规则 4「changelog 历史行不改」 | `grep -n "历史行不改" main/50_playbook/batch_workorder_spec.md` | **keep** + 反向指针（步骤 3b） | `batch_workorder_spec.md` §三.4 | 执行方 | 双向 grep 命中 |
| spec 自身修改纪律「修改本文件走批次 + changelog」 | `grep -n "修改本文件走批次" main/50_playbook/batch_workorder_spec.md` | **keep** + 反向指针（步骤 3b） | `batch_workorder_spec.md` §六 | 出单方 | 双向 grep 命中 |

> 收口扩展：工单原表 3 行；收口 grep 在 `batch_workorder_spec.md` 命中 3 处 changelog 相关句，表扩为 4 行（裁决单【工单缺陷 2】）。

---

## 五、本机制的外借面

本机制（**锚定断言 + 佐证断言**分层）**载体无关**。适用判据如下。

| 判据 | 锚定断言可用 | 佐证断言可用 |
|---|---|---|
| **条件** | 存在廉价、确定性的全局不变量，且它会随该载体所记之事而变 | 条目正文中含**指向仓库的可复算断言** |
| `t2ag_changelog.md` | ✔（如 runtime plan sha 等，以 U2 裁决为准） | ✔ |
| `t2ag_problemlog.md` | ✘ 无对应全局不变量 | **✔** 正文含 `playbook_status: extracted:<path>` 等路径断言（会悬空；现测以 `grep -c` 为准） |
| `course_reflections.md` | ✘ | 视条目是否引用课程/活动 ID 而定，需先实测 |
| `lesson_thoughts.md` / `exercise_thoughts.md` | ✘ | ✘ 记录的是思路，几乎不含仓库断言。**这两个载体要的是另一种门（L1.5 触发式存在检测），不在本单范围** |
| 已有 L2–L4 门的载体 | 已有更强机制 | ✔ 可叠加，专防条目腐烂 |

**本表是判据，不是待办清单。** 给任一载体实际立门都需要**单独工单**，不得据本表直接施工。

### 5.1 对 problemlog 的分层更正（写入施工报告；不改历史 survey 正文）

前序普查曾写「`problemlog` 找不到可行触发条件，建议接受它长期停在 L0」——**该结论错误**。  
`problemlog` **上不了锚定**，但**上得了佐证**；应停在「佐证可用、锚定不可用」，而非 L0。

---

## 六、与 doctor 的衔接

| 阶段 | 状态 |
|---|---|
| U1+U4 | 规范与判据落地；`doctor_contracts.md` 登记「changelog 漂移与腐烂」行 |
| U3（已实现） | `runtime.changelog` → `check_changelog_contract`；纯函数 + 正反测试 + 变异验证；锚定字段 = U2 批准的 A+B+C |

---

## 七、相关文件

- 载体：`main/00_core/t2ag_changelog.md`（Main / Skeleton **各自分叉**，不得互拷）
- 形式清单：`handoff_management.md` §5.6.2
- 出单 / 硬规则：`batch_workorder_spec.md` §二.5、§三.4、§六
- 契约矩阵：`doctor_contracts.md`
- 工单：`docs/handoffs/T2AG_CHANGELOG_VERIFICATION_WORKORDER_2026-08-07.md`
- 裁决：`docs/handoffs/T2AG_CHANGELOG_VERIFICATION_AUTHORIZATION_2026-08-07.md`
- EV：`EV-0017`（Register）
