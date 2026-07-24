# T2AG 命名规范

**保护级别**：core-playbook

> **触发**：创建、移动或重命名 T2AG 的目录、规则、课程、课时、资产和发行入口时。
>
> **目标**：路径可预测、可检索、适合跨平台，同时保护已经承担引用键的稳定标识。

---

## 一、基本原则

1. **稳定 ID 优先于表面整齐**：S、T、G、P、课程码、lesson 编号一旦被引用，就是外键。
2. **机器路径与显示名称分开**：路径用 ASCII；中文名称、空格和标点写在 Markdown 标题或字段里。
3. **同类同式**：同一目录层级只采用一种命名模板，不混用空格、连字符、驼峰和下划线。
4. **先定名后创建**：名称不能说明职责时，先修改设计，不用 `new`、`final`、`copy` 掩盖不确定性。
5. **来源材料少动**：教材、外部资料和原始样品保留来源文件名；系统生成的索引与旁路文件仍遵守本规范。

## 二、固定目录

| 层级 | 规范 | 示例 |
|---|---|---|
| 发行版 | 固定名称 | `t2ag/`、`t2ag-skeleton/`、`t2ag-lite/` |
| 功能区 | 两位序号 + 小写复数名 | `00_core/`、`10_case/`、`30_courses/`、`50_playbook/` |
| 共享保留目录 | 前导下划线 + 小写 snake_case | `_shared/`、`_exam/` |
| 学生 | `S` + 三位数字 | `S002/` |
| 课程组 | `G` + 两位数字 | `G02.md` |
| 教师 | `T` + 三位数字 | `T001.md` |
| 课时 | `lesson` + 两位数字 | `lesson01/`、`lesson01.md` |
| 课程 | `课程码_PascalCaseTitle` | `MATH1607H_MathematicalAnalysis/` |
| R 绑定（兼容路径） | `课程码r_PascalCaseTitle.md` | （实例化后登记） |
| 实践（旧） | Pxxx 前缀已退役，现役为 `FP-<case>-NNNN` / `AR-<case>-NNNN` | 见 domain_model §1.7-1.8 |
| ActivityRecord | `AR-<case_id>-NNNN_Title.md` | `AR-S002-0001_ReadingLogic.md` |
| FieldPractice | `FP-<case_id>-NNNN_Title/` | `FP-S002-0001_TradingDiscipline/` |
| FieldPractice 证据索引 | `evidence/README.md`（实例内 POSIX 相对路径） | `FP-S002-0001_*/evidence/README.md` |
| CourseDefinition 目录 | `<definition_id>_PascalCaseTitle/` | `MATH1607H_MathematicalAnalysis/` |
| CourseRun 目录 | `CR-<case_id>-<definition_id>/` | `CR-S002-MATH1607H/` |
| R binding | `RNNN_PascalCaseTitle.md` | `R001_ReadingLogic.md` |

课程码、`r` 后缀和实体 ID 保留既有大小写语义；描述部分不使用空格。

> **FP/AR 目录名后缀说明**：CourseRun 目录用裸 ID（`CR-S002-MATH1607H/`），因为课程码自带语义；FP/AR 的序号无语义，因此目录名追加 `_Title` 后缀助记（如 `FP-S002-0001_TradingDiscipline/`）。AR 为单文件，后缀直接在文件名上（`AR-S002-0001_InvestingNotes.md`）。

稳定 ID 不因路径迁移而变化。现有课程代码继续作为当前 CourseDefinition ID，不创建第二套 ID。

## 三、文件与资产

- 规则、状态、索引和工具使用小写 `snake_case`：`course_status.md`、`mistake_bank.md`、`context_scan.py`。
- ID 本身就是文件名时保留大写：`T001.md`、`G02.md`。
- 目录说明统一使用 `README.md`；需要排序到目录首部时允许既有保留名 `_README.md`。
- 课时教材工作区固定为 `lessonNN/working_pages/`；校对后的当前原文固定为
  `working_pages/source_excerpt.md`。原图、原始 OCR 与脚本分别进入 `pages/`、
  `raw_ocr/`、`scripts/`。
- 图像、代码和生成资产使用小写 `snake_case`；教材图可带有数字前缀：
  `1_1_1_venn_diagram.png`。
- 根目录操作手册固定为 `t2ag_directory_guide.html`，配套插图固定放在
  `assets/fable_snail.png`。
- FieldPractice `evidence_index` 使用实例内 POSIX 风格相对路径（默认 `evidence/README.md`）；
  原始证据文件继续存放在同一实例的 `evidence/` 下。
- 不在持久目录使用 `tmp`、`temp`、`new`、`final`、`copy`、日期尾缀或
  `v2`。确属临时内容时进入已定义生命周期的 `working_pages/`，任务结束按规则清理。

## 四、兼容例外

以下名称虽然不是新规范的理想形式，但已是协议入口，不做装饰性重命名：

- `t2ag.md`、`t2ag_memory.md`、`t2ag_changelog.md`、`t2ag_problemlog.md`
- `t2ag_case.md`
- 已登记的课程、学生、教师、课程组、R 绑定和实践 ID

历史 lesson、journal、changelog 和 problemlog 可以保留旧路径文字作为当时事实；活动规则、
当前状态与真实目录必须使用现名。

## 五、兼容期课程路径解析（双路径）

> **权威约定**：所有 playbook 在定位课程对象时必须使用本节规则，不得各自把
> `main/30_courses/[课程]/...` 写成唯一位置。doctor / state_refresh 已对旧/新路径做同构
> 检查；本节是人工与 agent 流程的同一语义。

### 5.1 输入

| 输入 | 必填 | 说明 |
|---|---|---|
| `course_definition_id` | 是 | 稳定 Definition ID（兼容期 = 课程码，如 `MATH1607H`） |
| `case_id` | 解析 Run 时必填 | 默认取 `10_case/student_info.md` 的 SN01 指针 |
| `course_run_id` | 否 | 省略时规范为 `CR-<case_id>-<definition_id>` |

禁止用英文标题、中文显示名或模糊别名猜目录。

### 5.2 解析 CourseDefinition

1. 在 `30_course_definitions/` 查找**唯一**目录 `{definition_id}_*`，且含正式载体
   `course_definition.md`；frontmatter 的 `course_definition_id` 必须等于输入。
2. 匹配目录数 > 1 → **停止**（Definition 目录重复）。
3. 若新路径已命中，再检查旧路径是否存在 `30_courses/{definition_id}_*/`：
   若旧路径也存在 → **停止**（新旧碰撞，不得择一忽略）。
4. 若新路径不存在，回退旧路径 `30_courses/{definition_id}_*/` 作为兼容期
   Definition+Run 混装载体（进度真相源仍是其中的 `course_status.md`）。
5. 新旧皆无 → **停止**（Definition/课程不存在）。

### 5.3 解析 CourseRun（进度真相源）

1. 确定 `case_id`（SN01）与 `course_run_id`（见 §5.1）。
2. 新路径候选：`35_course_runs/<case_id>/<course_run_id>/course_status.md`。
3. 旧路径候选：`30_courses/{definition_id}_*/course_status.md`。
4. 判定：
   - 仅新 → 使用新路径；
   - 仅旧 → 先执行 **Case 归属校验**（见下），通过后方可使用旧路径；
   - 两者皆有且同 `definition_id` → **停止**（碰撞）；
   - 皆无 → **停止**（CourseRun 不存在）。
5. **旧路径 Case 归属校验**（仅当判定为“仅旧”时触发）：
   1. 解析旧路径 `course_status.md` 的 YAML frontmatter。
   2. 读取 Case 归属字段，优先级固定：
      - 若存在 `case_id` → 用 `case_id`；
      - 否则若存在 `student` → 用 `student`（兼容期 MATH1205H 等现况）；
      - 若两者皆缺失 → **FAIL**（缺少 Case 归属，不得静默当作当前 Case）。
   3. 若解析出的归属 ≠ 当前 `case_id` → **FAIL / 停止**：
      - 诊断必须同时包含：期望 `case_id`、实际归属字段名与值、旧路径；
      - 禁止继续把该旧文件当作当前 Case 的写回目标。
   4. 归属一致 → 允许「仅旧 → 使用旧路径」。
6. 非当前 Case 的新 Run 仍接受全库工具验证，但不得写入当前 Case 的 state_refresh 缓存。

### 5.4 对象归属（拆分后路径）

| 内容 | 所有者 | 新路径位置 |
|---|---|---|
| 课程定义、先修、默认 driver、教材定义与 `[代码]_book/` | CourseDefinition | `30_course_definitions/<id>_<name>/` |
| lifecycle、进度、checkpoint、lesson、question/mistake、`_exam/`、working_pages | CourseRun | `35_course_runs/<case>/CR-<case>-<id>/` |
| 跨课共享资源索引 | 共享层 | 兼容期：`30_courses/_shared/`；目标：`30_course_definitions/_shared/` |

兼容期旧 `30_courses/` 仍可混装 Definition 与 Run 内容；拆分迁移后按上表归属，不得把学生进度写进 Definition，也不得把可复用定义正文复制进 Run。

### 5.5 默认写入（S002 分层迁移后）

- **读取 / 恢复 / 结课写回**：一律按 §5.2–5.3 解析出的**当前唯一** `course_status.md` 及其旁路文件。
- **新建课程默认 live 写入**（见 `new_course_init.md`）：
  1. **CourseDefinition** → `30_course_definitions/<definition_id>_<PascalName>/`
     （含 `course_definition.md`、`[代码]_book/` 等可复用定义；**不**写学生进度）
  2. **CourseRun** → `35_course_runs/<case_id>/CR-<case_id>-<definition_id>/`
     （含 `course_status.md` 进度真相源、mistake/question bank、lesson 等）
- **`30_courses/`**：仅兼容读回与共享层（如 `_shared/`）。**禁止**再向 `30_courses/` 新建混装课程目录。
- **禁止**：同一 `definition_id` 新旧路径同时 live；禁止为“让 doctor 变绿”而删除 recovery 或旧路径唯一副本（recovery 删除须另文授权）。

## 六、重命名迁移

1. 用 `rg` 列出旧名称的活动引用与历史引用，分开处理。
2. 确认目标名称符合本规范，且目标路径不存在。
3. 在同一文件系统内移动，不复制出两个并行真相源。
4. 更新宪法结构清单、活动 playbook、当前状态、README 和工具检查。
5. 历史记录不改写；必要时追加“旧名 → 新名”迁移说明。
6. main 的实例数据只做所需迁移；skeleton 先收敛通用规则，再同步 main/lite。
7. 运行三版本 doctor，并检查旧活动名称命中为 0。

## 七、禁止事项

- 不批量美化来源教材文件名。
- 不只改文件名而遗漏引用。
- 不用大小写差异创建两个目录。
- 不让 lite 或 main 反向覆盖 skeleton 的通用模板。
- 不为了统一而改变课程码、学生 ID 或历史事实。

