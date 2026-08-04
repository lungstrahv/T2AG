# ActivityRecord 管理

ActivityRecord 用于低治理、可暂停、尚未成为正式课程的活动。

## 创建

路径（0.2.1 初始合法 kind 只有 `reading`）：

`main/10_student/activities/<activity_kind>/AR-NNNN_Title.md`

最小 frontmatter：

```yaml
---
type: activity_record
activity_kind: reading
activity_record_id: AR-NNNN
title: 标题
record_status: recording
upgraded_to_course: —
created_at: YYYY-MM-DD
---
```

ID 在 `10_student/activities/` 的所有 kind 中共享全局编号域，单调递增、不重排、不复用。
新增 kind 必须先修改 schema/registry/Doctor，不能任意创建目录。文件保存事实、短笔记
和升级判断，不保存正式课程停点。

一项稳定阅读意图只使用一条 ActivityRecord；不是每本书创建一条 AR。同一意图可以引用多本书，
普通阅读不得因为出现书名或课程联想就自动升级为 Course、Engagement 或 R binding。

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
