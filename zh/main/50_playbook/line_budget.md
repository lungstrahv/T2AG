# 节预算与下沉

**保护级别**：core-playbook

> **这里放什么**：`main/00_core/t2ag_memory.md` 与 `main/t2ag.md` 这两个「每次启动都要读」
> 的载体，怎么用行数预算把自己压住；超限时怎么下沉、怎么留墓碑。
> **谁写・谁读**：维护会话写；节预算门与任何要动这两个载体的会话读。
> **什么时候来这里**：门报「节超预算」时；要调某节 `[max N]` 时；要下沉旧条目时。

本文件是节预算机制的 **canonical 正本**。`70_tools/t2ag_doctor.py` 的节预算门 docstring、
同文件 `memory_section_budgets()` 的 docstring、`00_core/t2ag_memory.md` §节预算与下沉 的
机制段，以及 `70_tools/contract_test_support.py` 的严厉度负例 docstring，**都只留指针指回
这里**：机制正文只此一份。多处措辞就有多处会各自漂移，而它们漂开时没有任何机器手段能发现
——本批之前，docstring 的 v0.1.2 沿革段就已在两仓各自漂开（Main 写 `check_line_budget`、
Skeleton 写 `check_constitution_budget()`），无任何机器在报。

**唯一的例外是节范围的定义**（一节从哪行起、到哪行止）：那是 `memory_section_budgets()`
的解析器契约，**归代码不归本文件**，本文件不复述（2026-08-27 裁定二）。分工是：机制归
playbook、函数行为归 docstring，两边各自完整、无交叠。

---

## 一、预算写在载体自身，不写在代码里

**预算是行数**，写成各节标题后的 `[max N]`：

```markdown
## 最近关键决策  [max 100]
```

门**从载体本身读取**这个标记，**不硬编码**。调预算是载体里的一行编辑——不改代码、
不走批次、不做三发行同步。这个价差是有意留的：预算若住在代码里，调它要付一个批次
＋三发行同步＋测试的价钱；价钱一高，人就改成「少写条目」而不是「抬预算」，那正好毁掉
预算本来要保护的东西。

所以分工是固定的：**机制归门、数值归学生**。被门守住的是机制，不是数值。

## 二、两个载体，两种严厉度

| 载体 | 严厉度 | 理由 |
|---|---|---|
| `main/00_core/t2ag_memory.md` | **WARN** | 它是摘要索引。摘要发胖是卫生问题，必须一直可见；但**不得在半节课中间把课卡住**。 |
| `main/t2ag.md` | **FAIL** | 它是每个会话开机都要读的入口。一个发胖的节会向此后**每一次**启动收税。 |

**严厉度按载体分设，不得拉平。** 拉平的两个方向都是净损失：把 memory 抬到 FAIL，
门就获得了中断教学的权力，而它守的只是卫生；把 `t2ag.md` 降到 WARN，开机税就重新变成
一条没人必须处理的提示——v0.1.2 的宪法预算门死于 `4e72556` 之后，幸存的散文引用就正好
退化成这种「无法执行的口号」（EV-0020）。

载体没有 `[max N]` 标记时，门按同一张严厉度表报「机制未生效」：memory 缺标记报 WARN，
`t2ag.md` 缺标记报 FAIL。**不要因为某节是空的就删掉它的标记**——删了，预算机制在这个
实例上就永不生效。

## 三、超限怎么办：下沉最旧条目，原位留墓碑

超限时**下沉最旧的条目**，并在原位留一行**墓碑**注明去向：

```markdown
- D-001 ~ D-011 已下沉 → `t2ag_changelog.md` [2026-07-26] ~ [2026-07-27]（YYYY-MM-DD 下沉）
```

**下沉不是删除**：条目正文本就在 `t2ag_changelog.md` / `t2ag_problemlog.md` 里，
memory 只留指针。**删行必须注明去向**——该纪律承自 v0.1.2 的「淘汰留痕」，它连同
`[max N]` 与当时的宪法预算门一起死于 `4e72556`（0.2.0 快照迁移），后于 0.2.3 重建。

`t2ag.md` 侧超限不走 memory 的下沉，走 `main/t2ag.md` §6.3 `rule_migration`
（或由学生裁决调整该节 `[max N]`）——宪法条文的去向必须逐条证明，不能靠墓碑一行了事。

**下沉的判据**（决策执行后结果「已经有家」才可下沉）与 **memory 自己的编号约定**
（`D-NNN` / `P-NNNN`）不属节预算机制本身：那两段写的是 memory 自己的条目怎么判、
怎么编号，故本文件不复述（2026-08-27 裁定三）。**这两段的去向按发行分述**：在 Main
（`t2ag`）与 Lite（`t2ag-lite`），它们在 `00_core/t2ag_memory.md` §节预算与下沉 内；
在 Skeleton（`t2ag-skeleton` 中文与 `t2ag-skeleton-en` 英文），其 memory **无此两段**，
该节只承载指回本文件的机制指针——在这两个发行里本节没有去向可指，不是断指针。

## 四、门在哪：发行版之间的命名差异

机制只此一份，**门的实现名随发行版不同**，落笔前按仓实取：

| 发行 | 现行 check ID |
|---|---|
| Main（`t2ag`） | `runtime.line_budget`（2026-08-26 DEC-0a-2 第一组，由 `runtime.memory_budget` 与 `runtime.constitution_budget` 合并而来） |
| Skeleton（`t2ag-skeleton`） | 仍为 `runtime.memory_budget` ＋ `runtime.constitution_budget`（合并尚未随发行下沉） |
| Lite（`t2ag-lite`） | 仍为 `runtime.memory_budget` ＋ `runtime.constitution_budget`（合并尚未随发行下沉） |

正因为两侧命名尚未收敛，本文件**不写行首的 `enforcement:` 前向边**：本文件在两仓字节
同源（core-playbook 落在 `release.playbook_taxonomy_parity` 的 SHA 比对面上），任何单一
`check=` 取值都必然在另一仓悬空，而悬空声明＝假保障，是 FAIL 级缺陷。前向边等 Skeleton
的门命名跟上合并后再补——这是一条登记在案的欠账，不是遗漏。

反向边（`rule_binding`）现只在 Main 立着：`70_tools/validation_workflow.json` 的
`runtime.line_budget` 条目指向本文件 §二。Skeleton 的 `doctor_checks` 尚无任何
`rule_binding` 字段（该字段整体尚未随发行下沉），反向边到时一并补。

## 五、来历

- v0.1.2：`t2ag.md` 内联 `[max N]` ＋ 独立的宪法预算门。
- `4e72556`（0.2.0 快照迁移）：两者一并丢失，只剩一句无人执行的散文。
- 0.2.3：机制在 `00_core/t2ag_memory.md` 重建（EV-0020）。
- 2026-08-26（DEC-0a-2 第一组）：Main 侧两个门合并为一个，严厉度改为按载体参数化。
- 2026-08-27（批二）：机制正文自 memory 迁入本文件，memory 与 docstring 双双削成指针。
  迁址理由：`rule_binding` 必须指向文档，而记录区（changelog / problemlog / memory）
  按 `50_playbook/doctor_contracts.md` §十二 不得作为 `rule_binding` 的落点。

## 六、rule_migration

本批对本文件为**新建**，对 `00_core/t2ag_memory.md` 与 `70_tools/t2ag_doctor.py`
为**迁址规范性正文**，按 `main/t2ag.md` §6.3 与 `playbook_management.md` §4.2 逐条登记。
`sink` 行的下沉闭包四项（新 canonical owner／必要入口指针／消费方／验证证据）见下表与其后。

| rule_id | 旧位置/原文锚点 | 动作 | 新 owner/等价门 | 消费方 | 验证 |
|---|---|---|---|---|---|
| LB-001 | `00_core/t2ag_memory.md` §节预算与下沉「预算是行数…被门守住的是机制，不是数值」 | sink | 本文件 §一 | 节预算门；调 `[max N]` 的维护会话 | `grep -n "机制归门、数值归学生" main/50_playbook/line_budget.md` |
| LB-002 | `00_core/t2ag_memory.md` §节预算与下沉「超限时下沉最旧的条目…删行必须注明去向」 | sink | 本文件 §三 | 执行下沉的维护会话 | `grep -n "删行必须注明去向" main/50_playbook/line_budget.md` |
| LB-003 | `70_tools/t2ag_doctor.py` 节预算门 docstring 的双载体严厉度表（Main：`check_line_budget`；Skeleton：`check_memory_budget` ＋ `check_constitution_budget`） | sink | 本文件 §二 | 节预算门；改门严厉度的施工会话 | `grep -n "两个载体，两种严厉度" main/50_playbook/line_budget.md` |
| LB-004 | `00_core/t2ag_memory.md` §节预算与下沉「下沉的判据」表与「编号约定」段（**Main 与 Lite**；Skeleton 的 memory 无此两段） | keep | 原位不动（`00_core/t2ag_memory.md`） | 执行下沉的维护会话 | `grep -n "下沉的判据" main/00_core/t2ag_memory.md` |
| LB-005 | `70_tools/validation_workflow.json` `runtime.line_budget` 的 `rule_binding` 取值（**仅 Main**；Skeleton 无该字段） | sink | 指向本文件 §二 | `rule_binding` 判据一（RULE-BIND-001） | `grep -n "line_budget.md#" main/70_tools/validation_workflow.json` |
| LB-006 | `70_tools/t2ag_doctor.py` `memory_section_budgets()` docstring 三段（段一 `[max N]` 归属论证／段二 节范围定义／段三 v0.1.2 沿革）＋ `70_tools/contract_test_support.py` `test_line_budget_constitution_over_limit_fails` 的严厉度理由段 | sink（段一・段三・严厉度理由）＋ keep（段二） | 段一→本文件 §一；段三→本文件 §五；严厉度理由→本文件 §二；段二→留在 docstring 原位 | 节预算门；改门严厉度的施工会话；改节切分实现的施工会话 | 见其后「LB-006 的下沉闭包四项」 |

**下沉闭包四项**：

1. **新 canonical owner**：本文件（`main/50_playbook/line_budget.md`，core-playbook）。
2. **必要入口指针**：`00_core/t2ag_memory.md` §节预算与下沉 机制段、
   `70_tools/t2ag_doctor.py` 节预算门 docstring、同文件的超限 remedy 文案——三处两仓
   均已改指本文件；`70_tools/validation_workflow.json` 的 `rule_binding` 为 Main 独有，
   亦已改指。
3. **消费方**：Main 的 `runtime.line_budget`；Skeleton 的 `runtime.memory_budget`
   与 `runtime.constitution_budget`；任何要调 `[max N]` 或执行下沉的维护会话。
4. **验证证据**：两仓 `PYTHONUTF8=1 python main/70_tools/t2ag_doctor.py --profile runtime`
   不劣于批前读数；`rule_binding_defect()` 对新取值返回 `None`；本文件内该锚唯一命中；
   两仓本文件 sha256 相同。

**未登记删除审查**：memory 与 docstring 两处均为「削成指针」，非删除；`00_core/t2ag_memory.md`
§节预算与下沉 的下沉判据表与编号约定段（LB-004）逐字未动。

**LB-006 的下沉闭包四项**（2026-08-27 批二·补）：

1. **新 canonical owner**：段一 → 本文件 §一；段三 → 本文件 §五；严厉度理由 → 本文件 §二。
   段二（节范围定义）**不下沉**，owner 仍是 `memory_section_budgets()` 的 docstring——那是
   解析器契约，不是节预算机制本身（2026-08-27 裁定二）。
2. **必要入口指针**：`70_tools/t2ag_doctor.py` `memory_section_budgets()` docstring 两处
   （段一位、段三位）＋ `70_tools/contract_test_support.py`
   `test_line_budget_constitution_over_limit_fails` docstring 一处，**两仓均已改为指针**。
3. **消费方**：节预算门；改门严厉度的施工会话（读 §二）；改 `[max N]` 归属的维护会话（读 §一）；
   改节切分实现的施工会话（读 docstring 段二，不读本文件）。
4. **验证证据**：两仓 `grep -rEn "owns the .mechanism.|the student owns the numbers|taxes every future boot|must stay visible|unenforceable slogan" main/70_tools/` 零命中；
   两仓 `memory_section_budgets()` docstring 逐字相同（段三的两仓漂移已消灭）；
   两仓本文件 sha256 相同。
