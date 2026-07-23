# FieldPractice 容器 目录说明

> **对象职责**：Case 拥有的现实实践与外部证据（不是课程）
> **所有者**：Case
> **ID 格式**：`FP-<case_id>-NNNN`
> **真相源**：各 FieldPractice 目录自身
> **允许引用**：CourseRun ID（0..N，Project/Praxis）
> **禁止**：不拥有学习目标、课程进度、课程成功标准
> **迁移状态**：结构准备批次建立的空骨架；当前实践文件混装在 `40_practices/`
> **本批次为空骨架**：是

## Markdown schema

```yaml
type: field_practice
field_practice_id: FP-<case_id>-NNNN
case_id: <case_id>
practice_status: active
linked_course_runs: []
evidence_index: evidence/README.md
```

## 示例目录结构

```text
FP-<case_id>-NNNN_Title/
├── field_practice.md
└── evidence/
    └── README.md
```

## evidence_index 约束

- 指向实例内的 Markdown 索引文件（不是目录）
- 路径相对于当前 FieldPractice 实例目录
- 默认值：`evidence/README.md`
- 使用 POSIX 风格 `/` 分隔符，不得使用反斜杠
- 不得为绝对路径（POSIX、Windows、UNC）
- 不得含 `.`、`..` 空段或路径逃逸
- 规范化后仍位于 FieldPractice 实例目录内
- 最终目标必须是已存在的普通 `.md` 文件
- 不得通过符号链接逃出实例目录
- FieldPractice 实例创建时，该索引文件必须已经存在
- 索引可以暂时记录“暂无证据”

## 约束

- FieldPractice 属于 Case
- 可以不关联课程而独立存在
- 可以关联零到多个 Project/Praxis CourseRun
- CourseRun 只引用并消费证据
- CourseRun 不拥有 FieldPractice
- 课程结课或解除关联不删除实践和证据

> 本批次为空骨架。当前无实例。迁移完成前旧路径继续有效。
