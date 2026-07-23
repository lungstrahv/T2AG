# ActivityRecord 容器 目录说明

> **对象职责**：Case 拥有的低治理活动记录（阅读、习惯、零散实践、兴趣探索）
> **所有者**：Case
> **ID 格式**：`AR-<case_id>-NNNN`
> **真相源**：各 ActivityRecord 文件自身
> **允许引用**：Case ID；升级后可保留 CourseRun 指针
> **禁止**：不复制课程进度、不复制培养方案、不承载 G/R 绑定
> **迁移状态**：结构准备批次建立的空骨架；当前无实例
> **本批次为空骨架**：是

## Markdown schema

```yaml
type: activity_record
activity_record_id: AR-<case_id>-NNNN
case_id: <case_id>
record_status: recording
upgraded_to_course_run: —
```

## 状态枚举

- `recording`：正在记录
- `paused`：暂停
- `closed`：关闭

## 升级规则

ActivityRecord 升级为 CourseRun 后保留来源记录和 CourseRun 指针，不删除或伪装原始记录。
升级条件见 domain_model §七。

## upgraded_to_course_run 约束

- 值只能是 `—` 或一个 CourseRun ID
- `—` 表示尚未升级
- 非 `—` 时必须引用新路径中存在的正式 CourseRun
- 被引用 CourseRun 的 `case_id` 必须与 ActivityRecord 相同
- 不限制 CourseRun 的课程类型
- 允许多个 ActivityRecord 指向同一 CourseRun
- 不因设置指针自动修改 `record_status`

> 本批次为空骨架。当前无实例。迁移完成前旧路径继续有效。
