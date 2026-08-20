# 规则准入门（R-GATE）

**保护级别**：meta-playbook

> 本文件是 T2AG「技能固化」文档之一。
> 当有新规则要写进 `00_core/` 或 `50_playbook/` 时触发。
>
> **适用场景**：新增行为约束、修改既有条款的强制方式、旧条款回填强制落点、
> 判断一条建议该不该变成规则。
>
> **机器落点**：`runtime.rule_enforcement_integrity`（`70_tools/t2ag_doctor.py`）。

## 一、Q0 拒收线

准入的第一问不是「这条规则对不对」，而是「**它有没有失败可见性**」。

以下一类条款**不收**：要求模型「安全」「向善」「诚实」「不要偷懒」一类的品性祈使。
不是因为它们错，而是因为它们**失败时不产生任何可观测差异**——写与不写，仓库看起来
一模一样。这类条款的真实作用是让写的人安心，不是让系统变好；写进宪法或 playbook 只会
稀释真正有落点的条款的密度（注意力过载线，见 `doctor_contracts.md` §八第 1 条）。

本线自身的强制方式如实声明如下（它是本文件唯一的真实标注，也是 R-GATE 的首个样本）：

enforcement: prose_accepted（理由：语义识别无机器手段，失败由学生评审抓）

写下这一行的意思是：**本线自己也没有机器落点，如实认了**。R-GATE 不要求每条规则都有
机器强制，只要求每条规则**说清自己有没有**。假保障比没有保障更毒（P-0067 家族）。

这条线只在本文件生效，**不进宪法**（D5-A）。宪法节有 `[max N]` 行预算，容不下解释性
条款；把判据放在这里、宪法保持精简，是同一个决定的两面。

## 二、`enforcement:` 字段规范

一条规则的强制方式取四值之一。**示例一律在围栏内**（见 §四）：

```text
enforcement: check=runtime.problemlog_closure
enforcement: tool=70_tools/t2ag_hint_gate.py
enforcement: context=50_playbook/session_close.md#结课五步
enforcement: prose_accepted（理由：写清为什么没有机器手段）
```

| 取值 | 含义 | 机检 | 悬空时 |
|---|---|---|---|
| `check=<doctor 检查 ID>` | 由 doctor 某原子检查强制 | ID 必须存在 | **FAIL** |
| `tool=<相对 MAIN 的路径>` | 由某工具代码强制 | 文件必须存在 | **FAIL** |
| `context=<路径>#<锚文本>` | 靠上下文投喂，规则本身不自执行 | 文件存在且含锚 | **WARN** |
| `prose_accepted（理由）` | 认了没有机器手段 | 括号理由非空 | **WARN** |

**`check=` 的取值必须是 `validation_workflow.json` 的 `doctor_checks` 完整键名**，
含 profile 前缀（如 `runtime.gate_ledger`），**不是** finding 码（`GATE-LEDGER-007`
是 finding 码，不是检查 ID）。problemlog 的 `closure: check=` 与本字段**共用同一命名
空间**；两处只许有一套 ID，见 `00_core/t2ag_problemlog.md` 头部回灌契约。

**`context=` 的解析语义**（三条，散文与代码同源）：

1. **路径相对 `MAIN/` 根**——与 `tool=` 同一份心智模型；两套基准就是两套 bug。
2. **按第一个 `#` 切分**，其后全部归锚文本，故锚文本自身可含 `#`。
3. **精确子串匹配，零规范化**（不做空白折叠、不做大小写归一）。这条只报 WARN，
   模糊匹配 + 不阻断等于没有——规范化是给一个只报警的检查装消音器。

**锚文本选取指引**：选**短而稳定的短语**，不要选整句。锚断掉是常态不是异常，
所以设计目标是**让重新锚定便宜**，不是让锚不断。

**`model_dependent:` 字段（2026-08-19 增，HARNESS Q3 裁决）**：新规则准入时声明
该规则在低模型壳下是否仍被遵守——`yes`（实测低模型也守）｜`no`（实测只有高模型
守得住，刚性有理由）｜`unknown`（未测，默认）。**存量规则不回填**，一律视同
`unknown`（声明语义，不做批量编辑）。取值唯一合法来源＝DP 记分卡实测
（`batch_workorder_spec.md` §二.8），不接受凭感觉填 yes/no。本字段现阶段无机检
（prose_accepted 同族），随记分卡数据积累逐步填充；差为 0 的规则是放松刚性的候选。

## 三、位置纪律

`enforcement:` **只许出现在下列文件**（doctor 白名单，与代码同源）：

- `50_playbook/*.md` 全部；
- `00_core/domain_model.md`、`00_core/learning_activity_model.md`、
  `00_core/pattern_retire_loop.md`。

`closure:` **只许出现在** `00_core/t2ag_problemlog.md`。两个字段各有各的地界，
互相出现在对方的文件里是 **FAIL**。

**排除名单及理由**（不是遗漏，是决定）：

- `00_core/t2ag_changelog.md`、`00_core/t2ag_problemlog.md` 正文、
  `00_core/t2ag_memory.md`——**只追加的记录，历史不得回改**。若把它们纳入扫描，
  一条被引述的历史标注会因为它引用的检查后来改名或退役而变成 FAIL，
  于是「修复」等于回改历史。记录区不入扫。
- GENERATED 区块——是投影不是来源，改它没有意义。
- **宪法 `main/t2ag.md` 显式豁免**。理由有二：D5-A 裁决（判据不进宪法）；
  宪法各节有 `[max N]` 行预算，加标注行会撑爆预算。
  **这是决定，不是漏洞**——写在这里就是为了不被半年后的自己当成漏洞重开一轮。

## 四、自指逃逸（硬约束，先于一切示例）

本文件在 `50_playbook/` 内，而它满纸都是 `enforcement:` 的示例——**文档会触发自己
要建的检查**。两侧各担一半：

- **文档侧义务**：本文件及任何文档里的 `enforcement:` / `closure:` **示例必须放进
  fenced code block**。围栏外顶行首写的，一律按真实标注受检。
- **代码侧义务**：findings 纯函数**先剥掉全部围栏**，再只匹配行首
  （容忍列表符与缩进）的字段行。

两道保险缺一不可：只有文档纪律，一次疏忽就误报；只有代码剥围栏，行内引述照样中招。

## 五、两振出局与升级压力

`occurrence_count >= 2` 的问题不得再以散文收尾——**契约正文在
`00_core/t2ag_problemlog.md` 头部回灌契约，此处不复制**，只记指针。复制一份就会漂移，
漂移之后没人知道哪份算数。

`context=` 类虽然只报 WARN，**升级压力照旧**：同一条 context 锚反复失效，说明它靠的
那份上下文本身不稳定，两振之后应当换成 `check=` / `tool=`，或如实降为
`prose_accepted` 并写清理由。WARN 是「不阻断」，不是「可以一直这样」。

## 六、旧条款回填

存量条款**不强制**回填，无截止线（D3-A′）。愿意回填时：

- 调查底本见 `../../docs/handoffs/T2AG_RGATE_OLD_RULE_SURVEY_2026-08-15.md`；
- 回填结果写进该文件 §四表，滚动更新；
- 回填即受检——写上 `enforcement:` 的那一刻，本文的判定全部生效。

不回填的条款保持现状，doctor **不检查「该声明而未声明」**（草案 §二 R4：那是自指账，
已按 `prose_accepted` 认下）。R-GATE 管的是**说了的话必须算数**，不管**没说的话**。
