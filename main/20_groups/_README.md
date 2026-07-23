# 课程组目录

> 活跃课程组只由 `00_core/t2ag_memory.md` 的“活跃课程组”字段指向。
> skeleton 不预设 G01，也不携带实例课程组或 overlay。

```text
20_groups/
|-- _README.md
|-- Gxx.md                 # 课程组定义，按需生成
|-- overlays/              # 被某个 Gxx.md 明确引用的展开资产
`-- preplans/             # 尚未激活的预案
    `-- _README.md
```

## 边界

- 课程组管理成员、时间预算、跨课接口、组级红线和结组条件。
- 单课进度只写在课程 `course_status.md`，课程组不得复制。
- overlay 不能孤立存在，必须由某个 Gxx 文件明确引用。
- preplan 不等于 active，不得提前占用当前预算。
- 创建、切换和结组按 `00_core/course_group_rules.md` 与
  `50_playbook/group_transition.md` 执行。

## 实例与展开资产

- `Gxx.md` 是实例，定义成员、目标、预算、红线和生命周期。
- `overlays/overlay_*.md` 是被一个或多个实例引用的展开资产，只保存确有复用价值的
  时间结构、知识地图或执行方案。
- 是否按日、周期、组或全局拆 overlay 由实例复杂度决定，不预建固定四件套。

## 生命周期与检查

`planned -> active -> paused -> archived`

- 实例已存在时只能有一个 active 组；空 skeleton 允许没有 active 组。
- memory 指向的组文件必须存在且状态为 active。
- Gxx 引用的 overlay 不得断链；未被任何 Gxx 引用的 overlay 应报告为孤儿。
