# Case 档案目录

> **这里放什么**：一个学生（Case）的整体状态与全部对象指针——档案、教师配置、培养方案引用、课程状态缓存。
> **谁写・谁读**：档案由教学 agent 在结课/里程碑时写入；开课恢复与教学决策时读取。
> **什么时候来这里**：想知道"这个学生是谁、现在挂着哪些课程与实践、教师配置是什么"，从这里出发找指针。

## Case 拥有什么

| 内容 | 位置 | 备注 |
|---|---|---|
| 学生档案 | `students/<case>/` | basic_info / personality_baseline / reasoning_patterns / course_reflections |
| 教师配置 | `teacher_overlay.md` + `teachers/` | 当前教师覆盖 |
| 课程状态缓存 | `course_info.md` | **GENERATED 块，永不手写**；由 state_refresh 从各真相源再生 |
| Case 主档 | `t2ag_case.md` | 培养方案引用与整体指针 |

## Case 掌管、但住在别处的对象

**所有权与住址是两回事**：下列对象在领域模型上属于本 Case，但各自住在专门容器里，真相源也在那里。本表只给指针。

| 对象 | 住址 | 与 Case 的关系 |
|---|---|---|
| CourseRun | `35_course_runs/<case>/` | Case 的课程实例；进度真相源在各 `course_status.md`，Case 只缓存摘要 |
| ActivityRecord | `12_activity_records/<case>/` | 低治理持续活动；条件满足时可升级为 CourseRun（见 `activity_management.md`） |
| FieldPractice | `40_field_practices/<case>/` | 真实行动与外部证据；**课程结课不删除**；可同时挂多门课（`linked_course_runs` 是列表） |
| G / R 执行结构 | `20_groups/` | 临时执行编组；只引用 CourseRun，不拥有课程内容；同一时间只有一个 active G |

## Case 不拥有

培养方案正文、课程定义（`30_course_definitions/`）、课程进度真相源——一律只存引用，不复制。

> 细则见 `00_core/domain_model.md` §1.1（Case）、§1.7（ActivityRecord）、§1.8（FieldPractice）。
> 本文件是**视图**：住址列若因目录重构变化，只改本表住址列，关系列不变。
