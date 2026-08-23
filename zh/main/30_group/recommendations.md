---
type: recommendation_ledger
schema_version: recommendation_ledger.v1
truth_scope: undecided_recommendations
authority: non_authoritative_outflow_only
updated: 2026-08-22
---

# 建议登记册（recommendations）

> **本文件解决什么**：T2AG 能保存「已经做了什么」，此前不能规范保存「以后可能做什么、
> 以及为何尚未做」。P-0069 由一次真实事故暴露该缺口——外部对话为一条课程路线建议开出
> 四条工单，本地实查后**无一可按字面执行**（problemlog 格式想象错、evolution register
> 状态机对不上、review 单元格容不下十行块、handoff 根指错且验收要求跑 release 本身即
> 越级）。缺口与格式失配是两个独立问题，本文件只解决前者。
>
> **空模板状态**：本册**无条目**（`## 四、登记册` 空）。这是正确初始态，不是缺陷——
> `runtime.recommendation_ledger` 对空册报 REC-000 INFO（观测态）。首条建议出现时
> 按 §三 形制新建 `## R-0001`。

## 一、权威边界（四条约束，各防一种已知死法）

1. **严格非权威、单向流出。** `plan.md` / `progress.md` / `review.md` **永不读取本文件**。
   条目转 `adopted` 后由人写入 plan/progress，本文件只保留指向那次改动的引用。
   —— 防台账反向污染真相源。
2. **`revisit_when` 必填。** 没有重启条件的 `deferred` 是死条目。本条有前科：原提案的
   重启条件挂在一个从未建成的人工累加器上，条件永不可能触发。
   —— 防死条目。
3. **`provenance` 必填，且必须区分 `student` / `model`。** 模型建议无标记地累积是这类
   系统的已知失败模式：三十条看起来都有道理的建议堆积，没有一条是学生本人想要的。
   模型提出项的采纳门槛应高于学生提出项。
   —— 防无主堆积。
4. **`adopted` 必须有落地引用。** 声明采纳却指不出对应的 plan/progress 改动，是纸面
   采纳。（本轮只建格式检查；语义验收留待条目真有 `adopted` 时再裁。）
   —— 防假采纳。

## 二、状态机

```text
proposed ──→ adopted   ──→（写入 plan/progress，本条留引用）
    │
    ├──→ deferred ──（revisit_when 触发）──→ proposed
    │
    └──→ retired（明确不做；理由必填，不删除条目）
```

四值合法集：`proposed` / `deferred` / `adopted` / `retired`。**永不物理删除条目**——
撤回的建议本身是判例（同 §1.7 无效授权记录永久保留的纪律）。

## 三、条目形制

每条一个 `## R-NNNN` 块，块内五个必填字段（`scope` / `target` / `status` /
`provenance` / `revisit_when`），随后是理由正文。`scope` 三值：`system` / `group` /
`course`。

## 四、登记册

（空。首条建议按 §三 形制新建 `## R-0001`。）

---

> **与课程组「未入组候选课程」栏的分界**：那一栏收**已建 planned 课程档案、等待入组**
> 的课程（准入问题）；本文件收**尚未决定要不要做**的建议（未决问题）。没有课程档案的
> 建议进不了那一栏——这正是 P-0069 实查发现的真门槛。两者不重叠；条目从本文件毕业进
> 那一栏时，状态转 `adopted` 并留引用。
