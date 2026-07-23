# G（刚性课程组）目标容器 目录说明

> **对象职责**：多 CourseRun 刚性绑定（统一预算、周期、组级评估）
> **所有者**：Case
> **ID 格式**：`GNN`
> **真相源**：各 `Gxx.md` 文件自身
> **允许引用**：CourseRun ID；FieldPractice ID（practice_members）
> **禁止**：不拥有课程内容、不复制进度
> **迁移状态**：结构准备批次建立的空骨架；当前实例在 `20_groups/`
> **本批次为空骨架**：是

## Markdown schema

```yaml
type: execution_group
group_id: GNN
case_id: <case_id>
status: planned
course_runs: []
field_practices: []
```

## 约束

- 同一时间只有一个 active G
- G 只引用 CourseRun ID，不拥有或复制课程内容
- 同一 CourseRun 不能同时处于 active G 和 active R

> 本批次为空骨架。当前无实例。迁移完成前旧路径继续有效。
