# general_learning.md —— R 绑定规则（弹性执行绑定）

**保护级别**：normal playbook

> R 的正式名称是"弹性执行绑定（Elastic Binding）"。
> "通识轨""Reading track""25_general"是兼容期旧名称/旧路径，不是 R 的领域定义。

---

## 背景

R（弹性执行绑定）是与 G（Group，刚性课程组）平级的第二种执行约束。
G/R 的差别是执行约束的刚性不同；成功标准属于 CourseRun，不属于 G/R 容器本身。

> **领域模型（v0.1.2）**：培养方案、Case、G/R、CourseDefinition、CourseRun 之间是引用图，
> 不是严格父子树。完整定义见 `00_core/domain_model.md`。

R 共享 t2ag 的教学纪律（教材分类、教师红线、memory 指针），
不共享 G 的执行约束（周期、频率红线、4h 预算、overlay 四层、组内冻结、换组仪式、卷面考核）。

目录位置：`25_general/`（兼容期旧路径），与 `20_groups/` 平级。

---

## R 的定义与边界

- R 只允许绑定 Project 或 Praxis CourseRun
- Mastery 只能进入 G
- 随手读书、习惯记录和无明确验收的探索先进入 ActivityRecord；不能因为"不考试""非学位要求"自动成为 R
- R 本身没有课程成功标准；验收方式由绑定的 CourseRun 类型决定

---

## R 允许的课程类型

| 课程类型 | 验收方式 | 典型课程 |
|---|---|---|
| Project | 绑定验证模式 A/B/B-K | 数据科学、独立项目 |
| Praxis | 真实行动 + 外部反馈 | 交易纪律、习惯养成 |

**Mastery 不得进入 R**（只能进 G）。

---

## 第一阶段冻结声明

第一阶段不得新建或激活 R。现有兼容文件全部冻结。

- 不得新建任何 R 文件
- 不得将现有 R 文件从 idle/paused 转为 active/reading
- 不得作为模板使用
- 若用户希望继续其内容，应先转为 ActivityRecord，或建立具有明确类型和验收证据的正式课程

---

## 未来 R 只保存 binding 字段（结构契约，待迁移批次切换）

完整对象分层迁移完成后，R 将只保存 binding 字段：

```yaml
type: elastic_binding
binding_id: RNNN
case_id: <case_id>
course_run_id: <course_run_id>
binding_status: planned
```

R 不拥有课程计划、进度、验收记录、lesson 或 mistake_bank；这些属于绑定的 CourseRun。

> **当前状态**：仍保持第一阶段冻结。当前无正式 R；legacy R frozen 在 `25_general/`。
> 本批次不得新建或激活 R。不得重新打开第一阶段已经否决的 legacy Reading R 语义。

---

## 核心规则

### 第一条：不占 G 预算

R 的时间从 G 的 4h 之外挤。R 不进入 `overlay_daily.md` 的时间分配表。

### 第二条：D4 兼容但无 KPI

R 可以在 D4 做，但不设进度 KPI。D4 原则禁止的是"带 KPI 的活动"，
不是"翻书"本身。

### 第三条：多 R 并行

不限活跃 R 数量，但建议同时不超过 2 个。

### 第四条：仪式锚

**Project R**：里程碑即仪式。按绑定的验证模式（A/B/B-K）执行验收。

**Praxis R**：行动记录即仪式。按频率记录行动证据和外部反馈，定期复盘。

### 第五条：验收方式

**Project R**：绑定模式验收。验证模式定义见 `50_playbook/project_verification.md`。

**Praxis R**：行动证据验收。

### 第六条：R 不抵账

R 永远不得作为 G 未达标周的解释、补偿或替代。

---

## Doctor 对接（第一阶段）

| 检查项 | 级别 | 说明 |
|---|---|---|
| 25_general/ 出现未登记的新 R 文件 | **FAIL** | 第一阶段冻结 |
| 已登记 legacy 文件状态为 active/reading | **FAIL** | 不得激活 |
| memory 把 frozen 文件列为 active | **FAIL** | 指针必须反映冻结 |

---

## Memory 对接

memory 指针与 G 指针分离：

```
| R 活跃绑定 | 无 | 25_general/_README.md |
```

第一阶段无活跃 R，始终写"无"。
