# 15_curricula/ —— 培养方案区域

> **定位**：存放培养方案（CurriculumPlan）的独立区域。
> 培养方案是引用课程定义的推荐套餐，不是课程，也不是课程组。
> 领域模型定义见 `00_core/domain_model.md`。

---

## 目录结构

```
15_curricula/
├── _README.md          ← 本文件：规则与 ID 登记
├── baseline/           ← 基准培养方案（Case 恰好引用一个）
└── references/         ← 参考培养方案（零到多个）
```

---

## baseline 与 reference 定义

| 角色 | 含义 | 数量 | 权限 |
|---|---|---|---|
| `baseline` | 学生现实中正在遵循的基准培养方案 | 恰好 1 个 | Case 的主参照 |
| `reference` | 用于选课和校准的参考培养方案 | 0~N 个 | 只读参照，不覆盖 baseline |

- reference 不得覆盖 baseline
- 培养方案不得直接改变 G/R 或 CourseRun
- 培养方案不得自动把课程加入 G、自动创建 R、自动启动 CourseRun

---

## 培养方案稳定 ID

每份培养方案使用稳定 ID，格式为 `CUR-[机构]-[专业][-版本]`。版本部分在未知时可省略（如 `CUR-SYSU-LOGIC`）。

- 版本年份是培养方案自身的年级版本（如 2025 级方案），与 `verified_date`（核验日期）不同。不得用核验日期冒充版本年份。
- 不以课程代码命名（避免与 CourseDefinition 混淆）
- 不使用类似课程代码的格式（如 `LOGIC1001r`）
- ID 一经分配不复用

### 已登记 ID

| 培养方案 ID | 角色 | 学校 | 专业 | 适用年级/版本 | completeness | 文件 |
|---|---|---|---|---|---|---|
| （首次启动时登记） | — | — | — | — | — | — |

---

## 每份方案必须声明的字段

| 字段 | 说明 | 示例 |
|---|---|---|
| `plan_id` | 稳定 ID | CUR-SJTU-CSACM-2025 |
| `role` | baseline 或 reference | baseline |
| `institution` | 学校 | 上海交通大学 |
| `program` | 专业/项目 | 计算机科学与技术（致远荣誉计划 ACM 班） |
| `applicable_year` | 适用年级/版本 | 2025 级 |
| `source_url` | 官方来源链接 | https://... |
| `verified_date` | 最近核验日期 | 2026-07-14 |
| `completeness` | full / summary / partial | full |
| `total_credits` | 毕业总学分（已知时填写） | 175.0 |

---

## completeness 定义

| 值 | 含义 |
|---|---|
| `full` | 完整逐学期培养方案，含课程代码、学分、学期和先修关系 |
| `summary` | 专业定位、培养目标和课程体系类别已确认，但缺逐学期课表、学分或课程代码 |
| `partial` | 仅部分信息可确认，大量字段未知 |

---

## 课程条目引用规则

- 培养方案中的课程条目引用 CourseDefinition 内部稳定 ID
- 学校课程代码只是外部映射字段，不是 T2AG 的引用键。内部稳定 ID 一经分配不复用。
- 培养方案中的课程类别（必修/选修）是方案属性，不是课程本体固有类型
- 未知学分、代码、学期不得猜测，标为 `—`（未知）
- 培养方案发现课程不存在时，可建议建立轻量 CourseDefinition，但不自动创建 CourseRun

---

## 禁止事项

- 不得用 `r` 课程码伪装培养方案 ID
- 不得把整份培养方案当成一门 R 课程
- 不得把培养方案登记为 R 索引中的条目
- 不得发明学分、学期、课程代码、先修关系或考核方式
- 不得让 reference 方案覆盖 baseline
- 不得自动开课或修改课程进度
