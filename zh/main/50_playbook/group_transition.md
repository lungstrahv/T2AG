# 换组仪式（group_transition）

**保护级别**：core-playbook

> **触发条件**：期末评估完成时，且仅此时。
> **定义来源**：`main/50_playbook/course_group_rules.md` 第五节。

---

## 五步流程

1. 旧组状态 archived，期末评估表为结组档案
2. 新组**此刻才建档**（预划表禁止提前建档案——防僵尸文件）：成员表、线别、预算、本期目标
3. 在新 group `plan.md` 写明状态、成员与当前课程；它是容量唯一真相源
4. 课程生命周期与容量组合分开处理：延续课保持 ongoing；完成课改 completed；
   用户明确终止的课程改 dropped；未入新组的 ongoing 课程只失去保留容量，不自动 paused
5. 运行 state refresh 生成 memory/learning_path 缓存，再跑 doctor → changelog 记录

---

## 预划表 ≠ 组文件

- **planned 组文件/预划表**是下一容量组合草案，任何时刻可写，不改变课程生命周期，也不占用当前预算。
- **active 组文件**是正式容量承诺；同一时刻只能有一个 active 组。
- planned 组中的课程可以是 planned 或 ongoing；激活时必须核对成员课程已可实际执行，planned 课程需经用户确认后转 ongoing。
- 区别本质：planned 是意图，active 是容量承诺；二者都不等于课程生命周期。

---

## 权限与建议边界

- 系统可以根据实际时长、学习能力、启动失败、截止期、依赖和项目限制提出换组或降频建议。
- 组成员变更、课程生命周期变化和预算重分配必须由用户确认；不得自动执行。
- 组外 ongoing 课程可由用户临时推进，但不得静默占用 active 组预算。

---

## G 的课程引用契约

G 的 `course_members` 直接引用稳定 `COURSE_ID`；每个 ID 唯一对应
`main/40_course/<COURSE_ID>/course.md` 与 `progress.md`。不得恢复 Case、
CourseDefinition/CourseRun 或 `CR-<case_id>-*` 包装。
