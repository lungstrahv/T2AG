# T2AG 领域模型（domain_model.md）

> **保护级别**：core（宪法附件，修改需走第五章修宪程序）
> **创建**：2026-07-22 · v0.1.2 第一阶段语义迁移
> **职能**：定义 T2AG 全部领域对象、引用关系和边界规则。
> 本文件是领域语义的唯一真相源；其他文件引用本文件，不复制定义。

---

## 一、对象定义

### 1.1 Case

`Case` 掌管具体学生的整体状态和对象指针：

- 学生档案（`10_case/students/Sxxx/`）
- 当前教师配置（`10_case/teacher_overlay.md`）
- 当前培养方案引用（baseline + references）
- 当前 G/R 执行选择
- 课程运行状态摘要（缓存，真相源在各 CourseRun）
- ActivityRecord（`12_activity_records/<case>/`，见 §1.7）
- FieldPractice（`40_field_practices/<case>/`，见 §1.8）
- 跨会话记忆和下一步（`00_core/t2ag_memory.md`）

Case **不拥有**完整培养方案正文，**不复制**课程定义和课程进度真相源。

### 1.2 CourseDefinition（课程定义）

属于可跨 Case 复用的课程目录，保存：

- **内部稳定 ID**（T2AG 系统内唯一标识，与学校课程代码分开）
- **学校课程代码**（如 MATH1607H、CS1953；自设课程可无学校代码）
- 名称
- 课程类型：mastery / project / praxis
- 学习目标和先修关系
- 默认验收方式
- 教材与来源

内部稳定 ID 与学校课程代码的区别：
- 学校课程代码是外部标识，可能随培养方案版本变化
- 内部稳定 ID 是 T2AG 的引用键，一经分配不复用
- 当前兼容期两者相同（如 `MATH1607H`），第二阶段分离

**当前物理位置（S002 实例已切换，2026-07-23）**：
`30_course_definitions/<definition_id>_<name>/course_definition.md`

兼容期旧混装路径 `30_courses/[代码]_[名]/` 在迁移完成前仍可被 doctor 识别；S002 五门课已迁出后，该路径仅保留 `_shared/` 等兼容用途。

CourseDefinition 拥有字段：

- `course_definition_id`（内部稳定 ID）
- `school_course_code`（外部代码，自设课程可为 `—`）
- `name`
- `course_type`（mastery / project / praxis）
- `default_driver`（textbook / goal / project / praxis）
- `prerequisites`
- `goals`
- `default_evidence`
- `materials`
- `status`（active / retired）

`prerequisites` 引用与无环规则：

- 单行数组，每项是一个稳定 CourseDefinition ID（大小写敏感）
- 不得重复、不得引用自身
- 引用必须存在于新路径正式索引，或兼容期旧 `30_courses/*/course_status.md` 中存在相同课程代码
- 新路径 CourseDefinition 之间不得形成有向循环
- 旧路径兼容引用视为叶节点，不参与新路径图循环检测
- 空数组 `[]` 合法

CourseDefinition **不拥有**学生进度。

### 1.3 CourseRun（课程运行）

属于具体学生 Case，保存：

- case/student ID
- course definition ID
- 生命周期（planned / ongoing / completed / dropped）
- 当前进度和下一步（`course_status.md` 是进度唯一真相源）
- lesson、疑问、错题与学习记录

同一个学生对同一门课程只有一个 CourseRun。
培养方案发现课程不存在时，只建立轻量 CourseDefinition；用户真正选入 G/R 后，才创建 CourseRun。

目标路径：`35_course_runs/<case_id>/CR-<case_id>-<definition_id>/`

CourseRun 拥有字段：

- `course_run_id`（格式 `CR-<case_id>-<definition_id>`）
- `case_id`
- `course_definition_id`
- `lifecycle_status`（planned / ongoing / completed / dropped）
- `course_driver`（textbook / goal / project / praxis）
- 进度、lesson、疑问、错题、下一步

`course_status.md` 继续是进度唯一真相源。

### 1.4 CurriculumPlan（培养方案）

引用课程定义的推荐套餐，不是课程，也不是课程组。

Case 可以引用：

- 一个 `baseline`：学生现实中正在遵循的基准培养方案
- 零到多个 `reference`：用于选课和校准的参考培养方案

培养方案**可以**：

- 引用 CourseDefinition
- 标记课程在该方案中的类别、必修/选修、学分和先修关系
- 对缺少的课程提出或创建轻量 CourseDefinition

培养方案**不能**：

- 自动把课程加入 G
- 自动创建 R
- 自动启动 CourseRun
- 修改课程进度
- 让 reference 覆盖 baseline

物理位置：`15_curricula/baseline/` 和 `15_curricula/references/`。

### 1.5 G（课程组 / Capacity Group）

严格的多课程执行组：

- 统一预算、周期、组级评估和换组规则
- 只引用 CourseRun，不拥有或复制课程内容
- 同一时间只有一个 active G

当前物理位置：`20_groups/Gxx.md`。

目标路径：`20_groups/`

### 1.6 R（弹性执行绑定 / Elastic Binding）

R 是单个 CourseRun 的弹性执行绑定：

- 正式名称：弹性执行绑定（Elastic Binding）
- "通识轨""Reading track""25_general"是兼容期旧名称/旧路径，不是 R 的领域定义
- G/R 表示执行约束（刚性/弹性），不表示通识/专业、必修/选修、兴趣/学位课程等内容类别
- R 只绑定一个 CourseRun，不拥有课程计划、进度、验收记录、lesson 或 mistake_bank
- R 只允许绑定 Project 或 Praxis CourseRun；Mastery 只能进入 G
- 随手读书、习惯记录和无明确验收的探索先进入 ActivityRecord；不能因为"不考试""非学位要求"自动成为 R
- R 本身没有"内部记录诚实"或"外部验证"这种课程成功标准；验收方式由绑定的 CourseRun 类型决定
- 可以同时有多个活跃 R
- 不受 G 的周期、频率红线、预算约束

R 绑定只保存：binding ID、CourseRun ID/路径、binding status、生效时间及必要的执行参数。

R binding status：planned / active / paused / ended
CourseRun lifecycle：planned / ongoing / completed / dropped
两者独立，不用 R 的 done/dropped 复制 CourseRun 生命周期。

当前物理位置：`25_general/[码]r_*.md`（兼容期旧路径，"通识轨"是 legacy 名称）。

目标路径：`20_groups/bindings/`

### 1.7 ActivityRecord（活动记录）

属于 Case，是阅读、习惯、零散实践和兴趣探索的统一低治理记录。

- 稳定 ID：`AR-<case_id>-NNNN`
- 目标路径：`12_activity_records/<case_id>/`
- 状态：recording / paused / closed

ActivityRecord 拥有字段：

- `activity_record_id`（格式 `AR-<case_id>-NNNN`）
- `case_id`
- `record_status`（recording / paused / closed）
- `upgraded_to_course_run`（`—` 或一个 CourseRun ID）

`upgraded_to_course_run` 规则：

- `—` 表示尚未升级
- 非 `—` 时必须引用新路径中存在的正式 CourseRun
- 被引用 CourseRun 的 `case_id` 必须与 ActivityRecord 相同
- 不限制 CourseRun 的课程类型
- 允许多个 ActivityRecord 指向同一 CourseRun
- 不因设置指针自动修改 `record_status`

ActivityRecord 不会因持续时间长而自动成为课程。升级课程必须明确：

- 想系统改善什么
- 主要完成证据
- mastery / project / praxis 类型
- 用户愿意纳入 G 或 R

升级后：

- 保留原始 ActivityRecord 的来源记录和 CourseRun 指针
- 不删除或伪装原始活动记录

### 1.8 FieldPractice（现实实践）

`FieldPractice` 是现实行动及其外部证据，**不是课程**。

- 属于 Case
- 稳定 ID：`FP-<case_id>-NNNN`
- 目标路径：`40_field_practices/<case_id>/`
- 可以不关联课程而独立存在
- 可以关联零到多个 Project/Praxis CourseRun
- CourseRun 只引用并消费证据
- CourseRun 不拥有 FieldPractice
- 课程结课或解除关联不删除实践和证据

FieldPractice 不拥有学习目标、课程进度、课程成功标准。它只记录：

- 行动描述（做什么、频率、规则）
- 原始结果（日志、记录、截图）
- 外部反馈（结果、复盘、证据）
- 关联指针（如关联某个 CourseRun）
- 证据索引（`evidence_index`）

`evidence_index` 规则：

- 指向实例内的 Markdown 索引文件（不是目录）
- 路径相对于当前 FieldPractice 实例目录
- 默认值：`evidence/README.md`
- 使用 POSIX 风格 `/` 分隔符，不得使用反斜杠
- 不得为绝对路径或含 `..` 逃逸
- FieldPractice 实例创建时，该索引文件必须已经存在
- 索引可以暂时记录“暂无证据”；不要求创建时已有原始证据文件

与 Praxis CourseRun 的区别：
- Praxis CourseRun 有明确的学习目标、教学方案和系统性进度
- FieldPractice 只记录行动、结果和反馈；Praxis CourseRun 使用这些证据判断自己的学习目标是否达成
- FieldPractice 可以关联零到多个 Project/Praxis CourseRun（作为证据源），但它本身不是 CourseRun
- 同一 FieldPractice 可以为多门课程提供证据
- Mastery 通常不依赖 FieldPractice
- FieldPractice 不拥有课程进度，不是课程

---

## 二、三种课程类型

顶层课程类型只有三种：

| 类型 | 成功标准 | 现有 course_driver 映射 |
|---|---|---|
| `mastery` | 理解、长期记忆、解题迁移和考试证据 | `textbook`、`goal` |
| `project` | 可运行、可检查的产物和里程碑 | `project` |
| `praxis` | 真实行动、外部反馈和长期行为改善 | `praxis` |

`course_driver` 是推进方式，不是课程类型本身：

- `textbook` 和 `goal` 是 Mastery 的两种推进方式
- `project` 对应 Project 类型
- `praxis` 对应 Praxis 类型

---

## 三、G/R 兼容矩阵

| 课程类型 | 可进入 G | 可进入 R | 说明 |
|---|---|---|---|
| mastery | ✓ | ✗ | Mastery 只能进入 G |
| project | ✓ | ✓ | 可选刚性组或弹性轨 |
| praxis | ✓ | ✓ | 可选刚性组或弹性轨 |

约束：

- 同一个 CourseRun 在同一时间不能同时处于 active G 和 active R
- G/R 只引用 CourseRun，不拥有或复制课程内容

---

## 四、引用关系图

```text
CurriculumPlan ──引用──> CourseDefinition
Case ──拥有──> CourseRun
Case ──拥有──> ActivityRecord
Case ──拥有──> FieldPractice
Case ──引用──> CurriculumPlan (baseline + references)
G/R ──绑定──> CourseRun
CourseRun ──引用──> CourseDefinition
CourseDefinition ──先修──> CourseDefinition (prerequisites, 无环)
ActivityRecord ──升级指针──> CourseRun (upgraded_to_course_run, 同 Case)
FieldPractice ──关联──> CourseRun (Project/Praxis, 0..N)
FieldPractice ──拥有──> 原始证据
FieldPractice ──拥有──> evidence_index (实例内 Markdown 索引文件)
```

**不是**严格父子树。培养方案、Case、G/R、CourseDefinition、CourseRun 之间是引用图，
不存在"培养方案 → 课程组 → 课程"的单一继承链。

---

## 五、唯一真相源与禁止复制

| 对象 | 唯一真相源 | 其他位置只允许 |
|---|---|---|
| 课程进度 | 各课程 `course_status.md` | 指针/缓存 |
| 培养方案正文 | `15_curricula/` 对应文件 | Case 中只留 ID + 指针 |
| 领域语义定义 | 本文件 | 引用，不复制 |
| 当前课程组 | active `Gxx.md` + memory 指针 | 缓存由刷新工具生成 |
| 学生档案 | `10_case/students/Sxxx/` | 不复制 |

---

## 六、培养方案权限边界

- baseline 是当前学生正在遵循的基准方案，Case 恰好引用一个
- reference 是参考方案，可零到多个
- reference 不得覆盖 baseline
- 培养方案中的课程类别（必修/选修/学分）是方案属性，不是课程本体固有类型
- 未知学分、代码、学期不得猜测，标为未知
- 培养方案不得直接改变 G/R 或 CourseRun

---

## 七、ActivityRecord 升级规则

ActivityRecord → 正式课程的升级必须满足：

1. 明确想系统改善什么
2. 明确主要完成证据
3. 确定 mastery / project / praxis 类型
4. 用户明确愿意纳入 G 或 R

升级后：

- 创建 CourseDefinition（如不存在）+ CourseRun
- 保留原始 ActivityRecord 的来源指针
- `upgraded_to_course_run` 设置为新 CourseRun ID（未升级时为 `—`）
- 不删除或伪装原始记录

---

## 八、兼容期与迁移声明

> **2026-07-23 状态**：S002 的五门兼容期课程（MATH1607H / PY1001 / CS1953 / IV1001 / MATH1205H）已切换为
> CourseDefinition + CourseRun live 实例。下列「旧路径」仍被 doctor 支持；「新路径」**已承载**这些实例真相，
> 不再是空骨架。**新建课程默认写入** `30_course_definitions/` + `35_course_runs/`（见 `naming_conventions.md` §5.5）。

### 旧路径（兼容期；迁移完成前仍有效，不得提前删除）

- `20_groups/`：G 执行组当前实例
- `25_general/`：R 绑定文件容器（"通识轨"是 legacy 名称）
- `30_courses/`：兼容期混装路径，已于 2026-07-23 完全清空（C1 迁走 `_shared/`，phase-1 迁走课程目录）；空目录待 C2 删除
- `40_practices/`：已于 2026-07-23 退场（EV-0005 步骤 1b），实例迁入 `40_field_practices/` 与 `12_activity_records/`，历史见 changelog

### 新路径（目标容器；S002 课程实例已 live）

- `12_activity_records/`：ActivityRecord 目标容器（仍可为空骨架）
- `20_groups/`：G 目标容器（课程组主体）
- `20_groups/bindings/`：R 目标容器（执行绑定从属于组）
- `30_course_definitions/`：CourseDefinition **live** 容器
- `35_course_runs/`：CourseRun **live** 容器（进度真相源 `course_status.md`）
- `40_field_practices/`：FieldPractice 目标容器（仍可为空骨架）

### 迁移规则

- 旧路径中的现有文件继续有效，doctor 继续检查
- 同一对象不得同时在新旧路径存在
- 切换时必须先有 main 外 recovery 完整副本，禁止 delete-first
- 迁移完成后才退役旧路径；**recovery 删除须单独用户授权**（且建议待独立模型项目级审查通过后）
