# 过程管理（process_governance）

**保护级别**：meta-playbook

> **职能**：过程对象（门 + 流程 + 有向图）的准入、修订、退役，以及图维护纪律。
> **不做什么**：不吞 R-GATE（`rule_admission_gate.md` 独立在位，本文件以指针引用）；
> 不写各门、各流程的规则正文（只放指针）。
> **本版**：骨架。三流程小节扩全文属第二阶段，本文件不改结构。

## 一、范围

本文件管理的过程对象：

- 门（Main-only `main/00_core/gate_index.md` 所载）
- 流程（`t2ag_flow.md` 的九项流程形态：`first_run`、`panorama`、`teaching_loop`、
  `authority_chain`、`cycles`、`skin`、`git`、`batch`、`exercise_loop`）
- 有向图（门与流程的关系图）

职责：上述对象的准入 / 修订 / 退役 + 图维护纪律（改门或改流程必改图；图只放指针）
+ 门台账指针（`learning_activity_model.md` §2.4）。`t2ag_flow.md` 自身仍是
core-playbook，正文不迁入本文件。

## 二、准入（第二阶段扩）

占位。第二阶段写：新门 / 新流程进入管辖的条件、登记位置与图更新。

## 三、修订（第二阶段扩）

占位。第二阶段写：改门、改流程的修订程序，以及与图、管辖清单的同批义务。

## 四、退役（第二阶段扩）

占位。第二阶段写：门 / 流程退役条件、图删除与指针失效的可见性。

## 五、有向图纪律

1. 改门或改流程，必须改图。
2. 图只放指针，不复制正文。

## 六、管辖清单

- `main/00_core/gate_index.md`（Main-only 数据；头部 `managed_by` 指向本文件）
- `50_playbook/t2ag_flow.md` 九流程形态（文件自身仍 core，正文不动）

## 七、强制声明与 Q0

骨架期没有机器手段。失败可见性路径留给第二阶段验收：届时图与管辖清单不一致
必须能被指定检查抓到（机器落点候选 `runtime.gate_index`）。骨架期如实声明：

```text
enforcement: prose_accepted（理由：骨架期无机器手段；机器落点候选 runtime.gate_index 留栏）
```
