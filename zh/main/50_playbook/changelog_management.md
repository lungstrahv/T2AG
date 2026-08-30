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

> 锚定块字段集合（学生 2026-08-07 已批）：**A+B+C**（runtime plan sha256、runtime checks、doctor_checks 键集合 sha）；**排除 D/E**。完整复算命令见 U2 报告。U3 已落地（见 §六）：本结构由 `runtime.changelog` → `check_changelog_contract` 对**最新条目**自动对照。

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

## 三之二、读写机制（写四条、读一条）

> **本节治的是增长率与读法，不治存量。** 历史条目一行不改（`batch_workorder_spec.md` 硬规则 4）；
> 本节只约束**新条目怎么写**与**旧条目怎么查**。编号取「三之二」而非顺延，是为不改动
> 既有 §四–§七 编号（外部已按号引用 §三、§3.1、§3.2）。

### 3b.1 四条机制

| 条 | 内容 | 机器可判 |
|---|---|---|
| **写-粒度** | **一个 campaign 一条**；不逐 action 落痕，同一 campaign 的多个 action 合并进同一条 | 是（§3b.3 判据二） |
| **写-正文** | 正文只含 `change` / `reason` / `validation_entry` 三字段；详细读数（逐项测试输出、耗时、findings 明细、子集规模）一律进 receipt | 是（§3b.3 判据一） |
| **写-方式** | **newest-first 插入、既有条目只增不改**（新条目插在文件头部，不是追加到末尾）；格式由 §3b.2 模板保证，**不为对齐格式而整读全文** | 否（行为约束，靠模板可判性间接约束） |
| **读-查历史** | 查历史用定向 `grep`（按 `campaign_id`、日期或条目标题定位），**不加载全文件** | 否（同上） |

**同型先例（引其形制，不另造措辞）**：「不全量读取」在本仓已有三处同族条款。本节**显式指向**下列三处，
不发明第二套措辞、不另立第二张判据表：

| 出处（文件＋节号） | 原文 |
|---|---|
| `handoff_management.md` §5.4「第四层：详细历史与原始材料入口」 | 「本层提供链接和展开条件，**不要求每次接管全量读取**。」 |
| `handoff_management.md` §八「读取与恢复流程」第 1 条 | 「识别当前任务，**不先全量读取 handoff root**。」 |
| `lesson_recover.md` §二「完整步骤」（工具成功/失败两分支的说明段） | 「……**不得把降级理解成全量读取**。」 |

三处的共同形制是：**上层承担定位与展开条件，下层原文按需展开**。本节「读-查历史」是同一形制在
changelog 载体上的落点——`t2ag_memory.md`「最近变更摘要」与 §3b.2 模板的三字段正文承担定位，
详细读数留在 receipt 里按需展开。

### 3b.2 三字段模板（normative example，不现场发明）

模板不由写位现场设计。`t2ag_changelog.md` 中 **`## [2026-08-25] DEC-0a-1 · Doctor changed-file
selector（不升版）`** 那条即现成的 reference implementation；新条目照抄其结构，
**值可替换，字段名与层级不得改**：

```markdown
## [YYYY-MM-DD] <campaign_id> · <一句话标题>（不升版｜或版本串）

- **change**：<改了什么，客观动作，不含评价>
- **reason**：<为何改，指向被解决的问题>
- **validation_entry**：<测试计划 SHA ＋ 定向测试读数 ＋ receipt 路径>

#### 锚定断言（必填）

- runtime plan sha256 = <值>
- runtime checks = <值>
- doctor_checks atom set sha256 = <值> (n=<数>)
```

**三字段之外的一切详细读数进 receipt，不进 changelog。** 锚定块沿用 §三 既有 A+B+C，本节不改；
佐证断言仍按 §三 选填，语义仍归 §3.1。

### 3b.3 机器落点（`check_changelog_contract` 扩三判据）

三判据**只对最新条目生效**：历史条目豁免——硬规则 4「changelog 历史行不改」优先于模板齐整，
不得为了让旧条目合模板而改写它们。

| 判据 | 内容 | 级别 |
|---|---|---|
| 一·模板合规 | 最新条目正文含 `change` / `reason` / `validation_entry` 三字段 | WARN |
| 二·单条粒度 | 与最新条目**同日期**的条目中，其 `campaign_id` 只出现一条 `## [日期]` 条目 | WARN |
| 三·receipt 可定位 | `validation_entry` 的 receipt 指针写成 `<carrier>:<相对路径>`（`carrier ∈ {repo, workspace}`），且能在该载体根下解析到实际文件 | WARN |

**为何三条全是 WARN 不是 FAIL**：机制落地首轮，既有条目与新模板不齐属预期；用 FAIL 会把 runtime
变红并阻断后续批次。级别是否升 FAIL 属 verdict 机制的裁量面，本节不预判。

**判据二的扫描面是「同日期」不是「全库」**：一个 campaign 跨批次续写属正常形态（`EV-0034`
2026-08-24 当日即分三条），全库口径会把后来的续写条目连坐判违规，而救济手段——改早先的条目——
撞硬规则 4，无解。同日口径既判死「同一批里逐 action 落痕」（正是写-粒度要禁的形态），
又放行跨日续写。

**判据三用显式载体前缀，不用路径约定**：receipt 指针必须自报由哪个根解析它。

| 写法 | 解析根 | 语义 |
|---|---|---|
| `repo:<相对路径>` | `ROOT`（＝产品仓 `t2ag/`） | 产品仓内证据 |
| `workspace:<相对路径>` | `ROOT.parent`（＝工作区 evidence root） | 工作区证据（施工报告、receipt 常在此侧） |

**判定表（显式前缀 fail-closed）**：

| 载体 | 条件 | 判定 |
|---|---|---|
| `repo:` | 落在 `ROOT` 内且文件存在 | 通过 |
| `repo:` | 落在 `ROOT` 内但文件缺失 | **WARN** |
| `repo:` | 逃逸 `ROOT` | **WARN** |
| `workspace:` | evidence root **已挂载**且文件存在 | 通过 |
| `workspace:` | evidence root **已挂载**但文件缺失 | **WARN** |
| `workspace:` | evidence root **已挂载**但逃逸该根 | **WARN** |
| `workspace:` | evidence root **未挂载** | **不判**（唯一的跨仓豁免） |
| 裸路径（有路径、无载体前缀） | — | **WARN**，提示补 `repo:`／`workspace:` |
| `validation_entry` 完全无路径 | — | **不判**（无可判对象） |

**挂载判定用 canonical marker，不用目录存在性**：evidence root 视为已挂载 ⟺
`ROOT.parent/docs/handoffs/README.md`（handoff 索引正本，见 `handoff_management.md`）存在。
只判目录存在会把任意同名空目录误认成 evidence root，对着空根判 WARN 造假信号。
外发的 Skeleton／Lite／EN 解包后既无该目录也无该 marker，`workspace:` 指针全部走「不判」，零跨仓假信号。

**为何显式前缀不再 fail-open**：旧实现按 `docs/handoffs/` 前缀豁免，且「存在」分支排在前缀分支之前，
于是同一前缀下**存在→通过、缺失→不判**——真实 receipt 与拼错路径**同样不受判**，
判据三在它唯一该管的形态上恰好空转。载体既然由写位显式声明，就必须为该声明负责：能解析的一律判死。
逃逸各自根按写错处理（WARN），不按「对象在别处」放行。

---

## 三之三、发布事实的写入时点（与版本台账三分层同源）

某事实若只在**包生成之后**才为真，而承载它的载体又**在包内**，写入即使包过期——
`60_journal/t2ag_version_ledger.md` 的三分层写入归属已两次解过该循环
（`candidate_review` 层②、`release_candidate` 层③，原文自陈「写通过→重打→新包未受审」）。
changelog 条目是**同一形状的第三例**，本节按同一解法处置。

- 描述本批改动的 change entry ── 属**构建前事实**，在候选构建**之前**冻结并随包发行
  （同三分层①「源内在状态」）。
- 发布产生的远端事实（push/tag/Release 的 commit、tag、asset name/size/hash）
  ── 属**构建后事实**，写 release receipt 或 `60_journal/t2ag_version_ledger.md`，
  **不得回改已冻结的产品树**（同三分层③「不打包载体，单独提交」）。

⚠ 违反的可观测后果（2026-08-27 实测）：改动后不刷新 changelog 锚定块，
doctor 三仓各悬一条「状态漂移无记录」WARN，其中骨架侧会打破自陈的
「空模板与新试用者的 doctor 必须保持 0 WARN」冷启动护栏。

---

## 四、rule_migration（本批执行表）

新建本文件成为 changelog **验证层** canonical owner；既有约定分布在出单方与执行方两侧，**全部 keep**，不 sink 到单一文件。

| rule_id | rule_id | 动作 | 新 owner/等价门 | 消费方 | 验证 |
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
