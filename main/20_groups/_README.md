# 20_groups —— 课程组目录

> **指针**：当前活跃课程组 = **G01**（由 `00_core/t2ag_memory.md`「当前状态指针」节维护）。
> agent 启动时读 memory 指针 → 进入本目录 → 读对应 `Gxx.md`。

## 目录结构

```
20_groups/
  _README.md              ← 本文件
  G01.md                  ← 组定义（active）
  G02.md                  ← 组定义（planned）
  overlays/               ← 方案层（被多组复用的模板）
    overlay_daily.md      ← 日：4h 分配·心理对策·四级梯子
    overlay_cycle.md      ← 周期：3-1-3 循环容器
    overlay_march.md      ← 组：14 周里程碑行军表
    overlay_atlas.md      ← 全局：上下册知识地图·战役预划
```

## 实例与模板分离

- `Gxx.md` 是**实例**：每组一份，随结组增删，定义"做什么"（成员、目标、红线）
- `overlays/overlay_*.md` 是**模板**：被多组复用，定义"怎么做"（时间分配、知识结构、节奏循环）
- 实例与模板分目录存放，顶层只剩"当前有哪些组"这一件事

## overlay 四切面

四个 overlay 是正交切面，覆盖完整无重叠：

| 文件 | 维度 | 作用 |
|---|---|---|
| `overlays/overlay_daily.md` | 日 | 每日 4h 分配、心理摩擦对策、四级梯子 |
| `overlays/overlay_cycle.md` | 周期 | 3-1-3 循环模板（输入→发酵→消化） |
| `overlays/overlay_march.md` | 组 | 14 周里程碑行军表、知识依赖主干 |
| `overlays/overlay_atlas.md` | 全局 | 上下册知识结构与战役规划 |

## 生命周期

planned → active → paused → archived
规则详见 `00_core/course_group_rules.md`，迁移流程见 `50_playbook/group_transition.md`。

## doctor 检查

- active 组数量须 = 1（无 G*.md 文件时 WARN，非 FAIL）
- memory 指针指向的组文件须存在且 active
- overlays/ 下文件必须被至少一个 Gxx.md 引用（孤儿 WARN）
- Gxx.md 引用的 overlay 路径必须存在（断链 FAIL）
