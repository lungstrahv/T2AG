# ActivityRecord 管理

ActivityRecord 用于低治理、可暂停、尚未成为正式课程的活动。

## 创建

路径：

`main/10_student/activities/AR-NNNN_Title.md`

最小 frontmatter：

```yaml
---
type: activity_record
activity_record_id: AR-NNNN
title: 标题
record_status: recording
upgraded_to_course: —
created_at: YYYY-MM-DD
---
```

ID 在 `10_student/activities/` 中单调递增，不重排、不复用。文件保存事实、短笔记
和升级判断，不保存正式课程停点。

## 状态

- `recording`：持续记录；
- `paused`：用户暂停；
- `archived`：结束且不再推进；
- `upgraded`：已升级为 Course，必须填写 `upgraded_to_course`。

## 升级

1. 与用户确认稳定课程 ID 和范围。
2. 按 `new_course_init.md` 建 Course。
3. 将可复用内容并入 `course.md`，当前状态写 `progress.md`。
4. ActivityRecord 标为 `upgraded` 并指向 Course；不复制后续课程进度。
5. 刷新状态并运行 doctor。

ActivityRecord 不自动加入 group，也不占用 group 预算。
