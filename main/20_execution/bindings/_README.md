# R（弹性执行绑定）目标容器 目录说明

> **对象职责**：单 CourseRun 弹性执行绑定
> **所有者**：Case
> **ID 格式**：`RNNN`
> **真相源**：各 R binding 文件自身
> **允许引用**：CourseRun ID
> **禁止**：不拥有课程计划、进度、验收记录、lesson 或 mistake_bank
> **迁移状态**：结构准备批次建立的空骨架；当前无正式 R 实例（legacy R frozen 在 `25_general/`）
> **本批次为空骨架**：是

## Markdown schema

```yaml
type: elastic_binding
binding_id: RNNN
case_id: <case_id>
course_run_id: <course_run_id>
binding_status: planned
```

## 约束

- R 只绑定一个 CourseRun
- R 只允许绑定 Project 或 Praxis CourseRun；Mastery 只能进入 G
- 同一 CourseRun 不能同时处于 active G 和 active R
- 第一阶段冻结：当前不得新建或激活 R

> 本批次为空骨架。当前无实例。迁移完成前旧路径继续有效。
