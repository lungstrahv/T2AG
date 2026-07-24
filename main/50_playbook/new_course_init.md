# 新增课程初始化流程

> 当学生提出新增课程时触发。本文件是课程结构和空白
> `mistake_bank.md` 与 `question_bank.md` 的唯一生成源。
>
> **职责边界**：
> - 本文件：建课程、生成空库、定义同知识点合并键。
> - `mistake_retest.md`：抽查题选择、正式证据和状态迁移。
> - `session_close.md`：把课堂证据写回既有条目。
> - `book_management.md`：教材、外部资料与 ER 编号。

---

## 一、触发与前置确认

满足任一条件时触发：

1. 学生明确提出学习一门尚未登记的课程。
2. 用户参照培养方案或课程组决定启用一门尚未建档的课程。
3. `10_case/course_info.md` 中不存在该课程代码。

课程已经存在时不得重新初始化，改走 `lesson_recover.md`。创建前确认：

- 课程代码与名称
- **课程来源与后缀**（必问，见下方说明）
- 当前学生和学习使命
- 课程驱动：`textbook / goal / project / praxis`
- 已有教材、外部资料、当前基础和期望产物

用户没有提供的信息保留"待确认"，不得编造。

#### 课程码后缀询问（强制）

新建课程时，agent **必须主动询问**：

> “这门课的来源是什么？你想给它什么后缀？”

后缀编码课程的**来源类型**，参考：

| 来源 | 说明 | 示例 |
|---|---|---|
| 培养方案 | 学校教学计划内的课程 | MATH1607**H**（H=荣誉，沿用学校码） |
| 职业培训 | 职业考试或培训体系 | ACCA-F3（自设前缀） |
| 兴趣班 | 生活偶发兴趣 | 无固定后缀，用户自定 |
| 技艺/习惯 | 决心提炼为技艺的持续实践 | 无固定后缀，用户自定 |

- 后缀由用户决定，agent 不猜测、不默认。
- 用户说"不要后缀"则不加。
- 已有后缀语义：`H` = 荣誉（学校码沿用）；`r` = 冻结后缀，不再新发。
- 自设码先登记后使用，在 `naming_conventions.md` 课程码规范节记录。

### 默认两步流程（§5.5；S002 分层迁移后生效）

新建课程**必须**拆成两步，不得再向 `30_courses/` 创建混装课程目录：

1. **创建或复用 CourseDefinition**  
   路径：`main/30_course_definitions/<definition_id>_<PascalName>/`  
   含 `course_definition.md`、`[代码]_book/` 等可复用定义；**禁止**写入学生进度。
2. **创建 CourseRun**  
   路径：`main/35_course_runs/<case_id>/CR-<case_id>-<definition_id>/`  
   `case_id` 默认取 `student_info.md` 的 SN01；含 `course_status.md`（进度唯一真相源）、
   banks、lesson 等运行态文件。

> **兼容**：仅当 §5.2–5.3 解析命中旧路径且无新路径碰撞时，才读/写旧混装树。  
> **禁止**：同一 `definition_id` 新旧 live 并存；禁止为“省事”把新课写回 `30_courses/`。

---

## 二、课程骨架

### 步骤 1：登记课程缓存

课程索引不再手写行。创建 CourseRun 的 `course_status.md` 后运行 `t2ag_state_refresh.py --write`，
由真相源和容量组生成 `course_info.md` 缓存。

### 步骤 2：创建目录（Def + Run）

```text
main/30_course_definitions/[代码]_[英文名]/
|-- course_definition.md
`-- [代码]_book/
    `-- README.md

main/35_course_runs/<case_id>/CR-<case_id>-[代码]/
|-- course_status.md
|-- progress_nodes.md      # 激活/恢复时惰性生成；planned 可暂不创建
|-- question_bank.md
|-- mistake_bank.md
`-- lesson01/                 # 第一次开课时创建
    |-- lesson01.md
    |-- thinking.txt
    |-- practice/
    |   |-- p/
    |   |-- f/
    |   `-- a/
    |-- illustration/
    `-- working_pages/
        `-- source_excerpt.md
```

英文名用 PascalCase，不含空格或特殊符号。`course_definition_id` 兼容期等于课程代码。
创建前按 §5.2 确认新路径无重复目录、且旧路径无同码碰撞。

### 步骤 3：生成 course_definition.md 与 course_status.md

**Definition** 载体至少声明：

```yaml
type: course_definition
course_definition_id: [代码]
school_course_code: [代码或—]
name: [显示名]
course_type: mastery
default_driver: textbook  # textbook / goal / project / praxis
prerequisites: []
status: active
```

**Run** 的 `course_status.md` 文件头必须声明：

```yaml
type: course_run
course_run_id: CR-<case_id>-[代码]
case_id: <case_id>
course_definition_id: [代码]
course_driver: textbook  # textbook / goal / project / praxis
lifecycle_status: planned  # planned / ongoing / completed / dropped
```

若 `course_driver: textbook` 且课程已经进入按页教学，在创建 `working_pages/` 的同一次操作中还必须补充：

```yaml
textbook_page: 23
working_pages_window: [22, 23, 24, 25]
```

未开始按页教学时不写占位数字；首次预加载时再写入真实页码，并由 doctor 与 `source_excerpt.md`、物理页文件交叉检查。

正文至少包含：

1. 课程描述、学习使命、课程目标与完成标准
2. 教材/来源和知识树形图
3. 初步课时估算与 lesson 划分
4. 当前进度、精确停顿点和下一步
5. 教学记录、已掌握知识点与真实行为/产物入口

课程首次开始时将 `lifecycle_status` 改为 `ongoing`。当前 active 容量组合来自 G 文件，
不得在 course_status 复制 `active/paused`。按 `progress_tracking.md` 惰性生成：

```yaml
progress_nodes: progress_nodes.md
current_completion_node: <稳定 completion node ID>
current_checkpoint: <当前到达节点 ID>
checkpoint_state: queued
next_action: <唯一下一步>
```

教材课只为当前 4–6 页生成 checkpoint，最多 12 个；planned/idle 课程不预造细粒度节点。

#### 驱动类型

| 驱动 | 顺序由什么决定 | lesson 来源规则 |
|---|---|---|
| `textbook` | 已登记教材的章节 | 教材是默认主来源；lesson 记录章页范围即可 |
| `goal` | 可验证能力目标 | 每个 lesson 标明一个主要可信来源或 ER 编号 |
| `project` | 真实产物里程碑 | 主要来源可为官方文档、规范、代码库或 ER 编号 |
| `praxis` | 真实行动、反馈与长期养成 | 知识来源和行为证据分开登记 |

`praxis` 课程必须写明：仅靠 T2AG 内部对话不能保证完善，学生自身的真实行动、
承担后果、环境反馈和生命力参与是课程的一部分；人格或判断力不能用答题次数认证。

### 步骤 4：生成教材与外部资料入口

`[代码]_book/README.md` 至少包含：

```markdown
## 教材

| ID | 书名/资料名 | 作者/机构 | 版本 | 本地路径 | 用途 |
|---|---|---|---|---|---|

## 添加外部学习资料

- 课程专属资料登记在本 README。
- 跨课程资料只引用 `main/30_course_definitions/_shared/external_resources.md` 的 ER 编号。
```

分类、路径、查重、本地持有和 ER 编号全部按 `book_management.md` 执行。

### 步骤 5：生成 question_bank.md

创建每门课程时必须原样保留标记 `QUESTION_BANK_TEMPLATE_V1`，再替换占位符。课程知识、证明、术语和学习方法疑问进入本库；系统、工具、文件和流程问题进入 `00_core/t2ag_problemlog.md`。

```markdown
<!-- QUESTION_BANK_TEMPLATE_V1 -->
> 【模式】复利回路·部件（00_core/pattern_retire_loop.md）｜角色=流量台账
> 【服务】所属回路=question_bank 集合层→教师画像（存量=students/[Sxxx]/reasoning_patterns.md）｜结算=answered/closed｜再入=学生复问→转“需要回看”
> 【边界】知识性错误转投同课 mistake_bank；系统问题转投 t2ag_problemlog

# [课程代码] 课程疑问库

> lesson 保存完整问答上下文；本文件提供跨课时汇总、状态与回看入口，不复制整段课堂正文。

next_id: 1

## 待解决

暂无。

## 需要回看

暂无。

## 已解答

暂无。

## 条目模板

### Q-0001｜[简短标题]
- 日期：YYYY-MM-DD
- 来源：lessonXX / 题目或知识点
- 问题：[学生原话或忠实转述]
- 状态：open / answered / revisit / merged
- 回答摘要：[一至三句]
- 完整记录：`lessonXX/lessonXX.md` 的对应问答标题
- 关联：[mistake ID / RP ID / 无]
```

规则：

- 学生使用 `问题：`、`疑问：` 或自然语言提出课程相关问题时，完整上下文实时写入 lesson，并在本库建立或合并条目。
- 同一根问题重复出现时追加来源，不新建同义条目；若新的问法暴露不同根因，可拆分。
- `answered` 表示已有回答，不等于已掌握；需要复习或仍不稳定时标为 `revisit`。
- `next_id` 只增不复用；移动状态区时保留原编号。

---

## 三、mistake_bank.md 唯一生成模板

创建每门课程时必须原样保留标记
`MISTAKE_BANK_TEMPLATE_V1`，再替换方括号占位符。工具或环境错误不得进入本库，
统一写入 `00_core/t2ag_problemlog.md`。

```markdown
<!-- MISTAKE_BANK_TEMPLATE_V1 -->
# [课程代码] 知识点错题库

> 【模式】复利回路·衰减（00_core/pattern_retire_loop.md）实例
> 【参数】域=知识点（[课程代码]）｜时机=事后归因｜归因层=概念层｜消费方=开课抽查→改理解｜退出=maintenance/aged｜再入=陈年卷答错→回强化
> 【边界】工具、环境、文件结构与流程问题转投 `00_core/t2ag_problemlog.md`

next_id: 1

## 条目格式

### M-0001
- 知识点键：[稳定、可复用的知识点名称]
- 首次日期：YYYY-MM-DD
- 来源：[lesson / 练习 / 抽查 / 陈年复习卷]
- 错误证据：[学生原答案、步骤或可定位摘要]
- 根因标签：[概念混淆 / 条件遗漏 / 方法选择 / 计算 / 表达 / 其他]
- 根因：[基于证据的解释]
- 正确理解：[可供下次生成变式探针的最小正确模型]
- 当堂理解：[已复述 / 提示后理解 / 尚未理解；不计正式成功]
- 当前周期：1
- 状态：active
- 当前周期摘要：尝试 0｜独立正确 0｜失败 0｜错后连续正确 0
- 最近正式复测：—
- 下次允许复测：—
- 陈年连续正确：0/2
- 最近陈年复习卷：—
- 下次陈年日历检查：—

| 日期 | 周期 | 探针 | 表面题/来源 | 结果 | 提示 | 判定依据 |
|---|---:|---|---|---|---|---|

## 活跃知识点

（暂无）

## 维护知识点

（暂无）

## 陈年知识点

（暂无）
```

### 建条目与合并规则

1. `知识点键` 是合并主键，描述可迁移的概念或方法，不用题号充当主键。
2. 同一知识点换数字、换题面或换 lesson 再错时，追加错误证据和复测行，不新建 ID。
3. 只有出现新的稳定知识点键才使用 `next_id` 建条目；建后立即递增。
4. 多个独立根因可以拆成多个知识点；一个表面题也可能同时写回多个条目。
5. 新建条目初始为 `active`、周期 1；不得根据当堂讲解直接写成 `maintenance`。
6. 迁移状态、正式复测间隔、六次上限和陈年恢复只引用 `mistake_retest.md`，本模板不复制算法。

---

## 四、课时与来源估算

1. 先确定课程总范围，再分阶段、章节、知识簇，最后拆 lesson。
2. 教材课先实际读取目录、篇幅、定义/定理、例题和习题量；约 2 小时可作为一个
   lesson 的初始尺度，但内容连贯性优先。
3. 标注“初步估算”及证据局限，后续按实际学习速度修正。
4. 需要外部调研时优先学生所在机构的公开大纲，其次选择可比的高质量来源并交叉验证。
5. 学习欲望或时间条件变化时，可以与学生协商调整范围、节奏和拓展内容，并写入
   `course_status.md`；不得根据短期情绪单方面降低正确性标准。

---

## 五、学生档案与 lesson

1. 确保当前学生四文件存在：`basic_info.md`、`personality_baseline.md`、
   `course_reflections.md`、`reasoning_patterns.md`。
2. 在 `course_reflections.md` 新增课程段，段首写当前“学习使命”，下接知识点树和
   带日期、可检索 ID 的感想记录。
3. 第一次开课才创建 `lesson01/`。临时教材页进入 `working_pages/`，持久教学资产进入
   `illustration/`，练习按 `practice/p|f|a/` 分类。
4. 展现形式与现场生成决策走 `lesson_recover.md`；学生始终可以要求换一种或加一种
   展现形式。

---

## 六、完成与验证

1. 更新 `teacher_overlay.md` 的课程映射；未指定时使用 T001。
2. 若课程进入课程组，按 `course_group_rules.md` 登记；未进入时保持 `planned`。
3. 在 `00_core/t2ag_changelog.md` 记录课程代码、路径、驱动、教材/ER 和初始化时间。
4. 运行 `70_tools/t2ag_doctor.py`，0 FAIL 才算初始化完成。
5. 向学生报告创建的文件、保留的待确认项和下一步，不宣称未验证的课程质量。
