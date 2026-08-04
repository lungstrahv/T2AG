# general_learning.md —— R 绑定规则（弹性执行绑定）

**保护级别**：normal playbook

> R 的正式名称是"弹性执行绑定（Elastic Binding）"。
> 旧“通识轨 / Reading track”只作为归档术语存在，不是 R 的领域定义。

---

## 背景

R（弹性执行绑定）是与 G（Group，刚性课程组）平级的第二种执行约束。
G/R 的差别是执行约束的刚性不同；成功标准属于 课程进度，不属于 G/R 容器本身。

> **领域模型（v0.2.0）**：培养方案、Student、G/R、Course 之间是引用图，
> 不是严格父子树。完整定义见 `00_core/domain_model.md`。

R 共享 t2ag 的教学纪律（教材分类、教师红线、memory 指针），
不共享 G 的执行约束（周期、频率红线、4h 预算、overlay 四层、组内冻结、换组仪式、卷面考核）。

目录位置：`main/30_group/<GID>/bindings/`。binding 属于具体 group，
但只引用 Course，不拥有课程内容或进度。

---

## R 的定义与边界

- R 只允许绑定 Project 或 Praxis 课程进度
- Mastery 只能进入 G
- 随手读书、习惯记录和无明确验收的探索先进入分类后的 ActivityRecord；普通阅读不得自动升级为
  Course、Engagement 或 R binding，也不能因为"不考试""非学位要求"自动成为 R
- R 本身没有课程成功标准；验收方式由绑定的 课程进度 类型决定

---

## R 允许的课程类型

| 课程类型 | 验收方式 | 典型课程 |
|---|---|---|
| Project | 绑定验证模式 A/B/B-K | 数据科学、独立项目 |
| Praxis | 真实行动 + 外部反馈 | 交易纪律、习惯养成 |

**Mastery 不得进入 R**（只能进 G）。

---

## 生命周期

R 可为 `idle / active / paused / closed`。激活前必须确认课程存在、课程类型为
Project 或 Praxis、对应 group 存在，并获得学生确认。迁移保留的
`R002_PHIL1101r` 是唯一 legacy Reading 证据：必须同时保持
`binding_status: idle` 与 `legacy_frozen: true`，不得激活、复制或作为新建先例。
它不是合法可激活 R。除这个 exact 冻结证据外，Mastery binding 一律非法；
其他 binding 也不得声明 `legacy_frozen` 或冒用 registry 的 legacy category。

---

## R 只保存 binding 字段

完整对象分层迁移完成后，R 将只保存 binding 字段：

```yaml
type: binding
binding_id: RNNN
course_id: <COURSE_ID>
group_id: <GID>
binding_status: idle
execution_mode: flexible
```

R 不拥有课程计划、进度、验收记录、lesson 或 mistake bank；这些属于绑定的 Course。

实际 binding 只存在于所属 group 的 `bindings/`；本通用 playbook 不枚举当前实例
的 R 编号、课程或 group。不得重新打开已经否决的 legacy Reading R 语义。

---

## 核心规则

### 第一条：不占 G 预算

R 默认不占 active group 的预算；若用户要分配组内时间，必须显式写入该 group 的
`plan.md` 与 `calendar.md`。

### 第二条：D4 兼容但无 KPI

R 可以使用 group calendar 明确标出的无 KPI 弹性时段，但不自动继承任何旧
overlay 的 D4 或 3-1-3 节奏。

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

## Doctor 对接

| 检查项 | 级别 | 说明 |
|---|---|---|
| binding 引用不存在的 course/group | **FAIL** | 引用必须闭合 |
| Mastery 课程绑定到 R（exact frozen R002 证据除外） | **FAIL** | Mastery 只能进入 G |
| binding 状态不在枚举内 | **FAIL** | 状态必须可判定 |
| legacy Reading binding 不是既有冻结 R002 | **FAIL** | 只保留迁移证据，不恢复旧模型 |

---

## Memory 对接

memory 指针与 G 指针分离：

```
| active binding | 无或 `<RID>` | main/30_group/<GID>/bindings/ |
```

没有活跃 R 时缓存写“无”；激活后由 state refresh 生成真实指针。
