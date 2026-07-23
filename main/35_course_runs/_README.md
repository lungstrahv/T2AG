# CourseRun 容器 目录说明

> **对象职责**：某 Case 对某 CourseDefinition 的一次学习运行（进度与课堂状态）
> **所有者**：Case
> **ID 格式**：CR-<case_id>-<definition_id>/
> **真相源**：各 CourseRun 内 course_status.md 是进度唯一真相源
> **允许引用**：CourseDefinition ID；Case ID
> **禁止**：不复制 CourseDefinition 定义内容
> **迁移状态**：目标容器契约已就绪；本 skeleton 无 CourseRun 实例。兼容期旧混装路径 30_courses/ 在迁移完成前仍有效。
> **本批次为空骨架**：是

## 目录结构

`
35_course_runs/
  <case_id>/
    CR-<case_id>-<definition_id>/
      course_status.md
      ...
`

## course_status frontmatter（摘要）

`yaml
type: course_run
course_run_id: CR-<case_id>-<definition_id>
case_id: <case_id>
course_definition_id: <definition_id>
course_driver: textbook
lifecycle_status: planned
`

## 约束

- course_status.md 是进度唯一真相源
- lifecycle_status: planned / ongoing / completed / dropped

> 本 skeleton 保持空骨架、无实例。进度真相源始终是各 Run 内 course_status.md。
