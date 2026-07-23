# CourseRun 容器 目录说明

> **对象职责**：Case 拥有的课程运行（含进度、lesson、疑问、错题）
> **所有者**：Case
> **ID 格式**：`CR-<case_id>-<definition_id>`
> **真相源**：各 CourseRun 内 `course_status.md` 是进度唯一真相源
> **允许引用**：CourseDefinition ID；Case ID
> **禁止**：不复制 CourseDefinition 定义内容
> **迁移状态**：结构准备批次建立的空骨架；当前 CourseRun 混装在 `30_courses/`
> **本批次为空骨架**：是

## 目录结构

```
35_course_runs/
└── <case_id>/
    └── CR-<case_id>-<definition_id>/
        ├── course_status.md    ← 进度唯一真相源
        ├── lesson01/
        ├── mistake_bank.md
        └── question_bank.md
```

## Markdown schema（course_status.md frontmatter）

```yaml
type: course_run
course_run_id: CR-<case_id>-<definition_id>
case_id: <case_id>
course_definition_id: <definition_id>
lifecycle_status: planned
course_driver: textbook
```

## 约束

- 同一学生对同一门课程只有一个 CourseRun
- `course_status.md` 是进度唯一真相源
- lifecycle_status: planned / ongoing / completed / dropped

> 本批次为空骨架。当前无实例。迁移完成前旧路径继续有效。
