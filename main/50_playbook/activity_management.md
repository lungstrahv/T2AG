# 活动记录管理（activity_management）

> 本文件是 T2AG「技能固化」文档之一。
> 覆盖 ActivityRecord（AR）的完整生命周期：开档、记录、暂停、关闭、升级。
>
> **适用场景**：学生有持续性活动但尚不构成正式课程时。
>
> **关联文件**：
> - 领域定义：`main/00_core/domain_model.md` §1.7 + §七
> - 容器说明：`main/12_activity_records/_README.md`
> - 升级后衔接：`main/50_playbook/new_course_init.md`
> - 命名规范：`main/50_playbook/naming_conventions.md`
>
> **设计哲学**：AR 从持续行为中自然诞生。低治理不等于零流程——
> 开档有判据、ID 有管理、升级有顺序，但日常记录不设门槛。

---

## 一、开档判据

**一句话测试**：

> "这件事我愿意每周看一眼，但不愿意为它写验收标准。"
> → **AR**
>
> "我愿意为它定义完成证据、纳入课程组或绑定执行计划。"
> → 走 `new_course_init.md`（正式课程）

### 适合开 AR 的信号

- 持续性行为（阅读、习惯、零散实践、兴趣探索）
- 不想被课程仪式（结课、抽查、mistake_bank）约束
- 但希望留下可回溯的记录
- 未来**可能**升级为课程，但现在不确定

### 不适合开 AR 的情况

- 一次性事件 → 写 `60_journal/` 日志
- 已有正式课程覆盖 → 写进对应 CourseRun
- 系统/工具问题 → 写 `t2ag_problemlog.md`
- 交易决策记录 → 已有 `trade_journal.md`（复利回路实例），不另开 AR

---

## 二、开档流程

### 步骤 1：分配 ID

- 格式：`AR-<case_id>-NNNN`（如 `AR-S002-0001`）
- `case_id` 取 `student_info.md` 的 SN01 指针
- 序号从当前容器内最大 NNNN + 1；首实例为 0001

### 步骤 2：创建文件

路径：`main/12_activity_records/<case_id>/AR-<case_id>-NNNN_Title.md`

文件头必须包含：

```yaml
type: activity_record
activity_record_id: AR-<case_id>-NNNN
case_id: <case_id>
title: [显示名]
record_status: recording
upgraded_to_course_run: —
created_at: YYYY-MM-DD
source_description: [一句话描述这个活动是什么]
```

### 步骤 3：登记索引

在 `12_activity_records/<case_id>/` 的 `_index.md`（不存在则创建）追加一行：

```markdown
| AR-S002-NNNN | 标题 | recording | YYYY-MM-DD | — |
```

### 步骤 4：确认

向学生确认："已开档 AR-S002-NNNN「XXX」，状态 recording。随时可以暂停或升级。"

---

## 三、日常记录

- AR 文件内部格式**自由**：笔记、清单、链接、摘要均可
- 无结课仪式、无抽查、无 mistake_bank
- 学生随时可以追加内容，agent 不主动催促
- 若学生课中提到 AR 相关内容，agent 可询问"要记到 AR 里吗？"，不强制

---

## 四、状态变更

| 变更 | 触发 | 操作 |
|---|---|---|
| recording → paused | 学生说"先放一放" | 改 `record_status: paused`，索引同步 |
| paused → recording | 学生说"继续那个 XXX" | 改回 `recording`，索引同步 |
| recording/paused → closed | 学生明确说"不做了" | 改为 `closed`，索引同步，不删除文件 |

状态变更只改文件头和索引，不触发其他仪式。

---

## 五、升级为课程

### 触发条件（domain_model §七）

学生**明确**表达以下全部意图：

1. 想系统改善什么
2. 主要完成证据是什么
3. 确定 mastery / project / praxis 类型
4. 愿意纳入 G 或 R

> 持续时间长不自动触发升级。agent 可以观察并**建议**，但决定权在学生。

### 升级仪式（四步，顺序强制）

1. **确认/新建 CourseDefinition**
   按 `new_course_init.md` 步骤 2–4 创建或复用 Definition。

2. **创建 CourseRun**
   按 `new_course_init.md` 步骤 2–6 创建 Run（含 course_status.md、banks 等）。

3. **回填 AR 升级指针**
   在 AR 文件头设置 `upgraded_to_course_run: CR-<case_id>-<code>`。
   `record_status` 由学生决定：继续 recording（AR 和课程并行）或改为 closed（AR 归档）。

4. **刷新缓存**
   运行 `python main/70_tools/t2ag_state_refresh.py --write` 刷新 course_info.md。

> **顺序不可颠倒**：先建 Run 再填指针。否则 doctor 会报 upgraded_to_course_run 引用不存在的 CourseRun。

### 升级后

- AR 文件保留，不删除、不伪装
- 新课程独立运行，走正常开课/结课仪式
- AR 内的历史笔记可作为新课程的首批参考材料，但不自动复制

---

## 六、降级/回退

CourseRun 被 `dropped` 后：

- AR 的 `upgraded_to_course_run` 指针**保留**（历史记录）
- `record_status` **不自动恢复**为 recording
- 由学生裁决：
  - "回到 AR 状态" → 手动改 `record_status: recording`
  - "彻底不做了" → 改 `record_status: closed`
  - "重新开一门课" → 走 new_course_init（新 CourseRun，AR 指针更新）

---

## 七、首实例参考

`12_activity_records/S002/AR-S002-0001_InvestingNotes.md`（投资阅读笔记）是 AR 的首实例：

- 持续行为：睡前阅读 + 高密度笔记
- 低治理：不占学习预算、无验收标准
- 有明确边界："每本只记 5 条以内"
- 未来可能升级：G02 建档后可能成为 IV1001 的补充材料

第二阶段迁移已完成（EV-0005 步骤 1b），验证了：
- 建档流程（本 playbook）
- `40_practices` 拆分
- `12_activity_records/` 容器从空骨架到首实例

> 迁移已完成，`notes.md` 已迁入 `12_activity_records/S002/AR-S002-0001_InvestingNotes.md`。

---

## 八、避坑

- **把 trade_journal 当 AR**：错。trade_journal 是复利回路·衰减实例，有自己的归因/退出/再入机制，不是低治理记录。
- **AR 文件里写课程进度**：错。AR 不复制课程进度，升级后进度在 CourseRun 的 course_status.md。
- **自动升级**：错。持续时间长不等于该升级，必须学生明确表达四条意图。
- **升级时先填指针后建 Run**：顺序错。doctor 会 FAIL。
- **关闭 AR 时删除文件**：错。closed 只改状态，文件永久保留。
