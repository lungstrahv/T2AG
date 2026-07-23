# CourseDefinition 容器 目录说明

> **对象职责**：可跨 Case 复用的课程定义（不含学生进度）
> **所有者**：系统级（可被多个 Case 引用）
> **ID 格式**：`<definition_id>_PascalCaseTitle/`（当前兼容期 definition_id = 课程代码）
> **真相源**：各 `course_definition.md` 文件自身
> **允许引用**：先修 CourseDefinition ID
> **禁止**：不拥有学生进度、不复制 CourseRun 数据
> **迁移状态**：结构准备批次建立的空骨架；当前课程定义混装在 `30_courses/`
> **本批次为空骨架**：是

## Markdown schema

```yaml
type: course_definition
course_definition_id: <stable_id>
school_course_code: <external_code_or_dash>
name: <display_name>
course_type: mastery
default_driver: textbook
prerequisites: []
status: active
```

## 字段说明

- `course_definition_id`：内部稳定 ID（当前兼容期与学校课程代码同值）
- `school_course_code`：外部代码（自设课程可为 `—`）
- `course_type`：mastery / project / praxis
- `default_driver`：textbook / goal / project / praxis
- `prerequisites`：单行数组，每项是一个稳定 CourseDefinition ID
- `status`：active / retired

## prerequisites 约束

- 必须使用单行数组格式：`[ID1, ID2]` 或 `[]`
- ID 大小写敏感，不得重复，不得引用自身
- 引用必须存在于新路径正式索引，或兼容期旧 `30_courses/*/course_status.md` 中存在相同课程代码
- 新路径 CourseDefinition 之间不得形成有向循环
- 旧路径兼容引用视为叶节点
- 空数组 `[]` 合法

> 本批次为空骨架。当前无实例。迁移完成前旧路径继续有效。
