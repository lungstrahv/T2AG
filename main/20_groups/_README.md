# 20_groups —— 课程组目录

> **指针**：当前活跃课程组 = **G01**（由 `00_core/t2ag_memory.md`「当前状态指针」节维护）。
> agent 启动时读 memory 指针 → 进入本目录 → 读对应 `Gxx.md`。

## 目录结构与文件作用

| 文件 | 类型 | 作用 |
|---|---|---|
| `G01.md` | 课程组定义 | 当前活跃组（active）：成员课程、周期、预算、跨课接口 |
| `G02.md` | 课程组定义 | 预备组（planned）：G01 结组后激活 |
| `plan_v2_4h.md` | 方案层（overlay） | 地基：每日 4h 分配、心理摩擦对策、四级梯子 |
| `plan_v3.md` | 方案层（overlay） | 行军表：14 周里程碑表、知识依赖主干 |
| `plan_313.md` | 方案层（overlay） | 节奏容器：3-1-3 循环模板（输入→发酵→消化） |
| `plan_v4.md` | 方案层（overlay） | 全册地图：陈纪修上下册知识结构与战役规划 |

## 方案层 = 课程组的 overlay

`plan_*.md` 文件是课程组的**方案 overlay**——它们不是独立文档，而是 Gxx.md 的展开层：
- `Gxx.md` 定义**做什么**（成员、目标、红线）
- `plan_*.md` 定义**怎么做**（时间分配、知识结构、节奏循环）
- 方案层文件被 `Gxx.md` 的「执行方案分层」节引用，不独立存在

## 生命周期

planned → active → paused → archived
规则详见 `00_core/course_group_rules.md`，迁移流程见 `50_playbook/group_transition.md`。

## doctor 检查

- active 组数量须 = 1（无 G*.md 文件时 WARN，非 FAIL）
- memory 指针指向的组文件须存在且 active
