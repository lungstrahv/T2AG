---
type: student_profile
initialization_status: uninitialized
updated: —
---
# 学生档案（空模板）

> 首次启动时与用户逐项确认。不得预填真实姓名、学校、课程、学生编号或推断性格。

## 基本信息

- 姓名或昵称：<required>
- 学校或机构：<required>
- 年级或阶段：<required>
- 学习方向：<required>
- 每周可投入时间：<required>

## 学习目标

- <required>

## 辅导与展现偏好

- <required>

## 执行参数

- 周期结构：<confirm>
- 小调整频率：<confirm>
- 大调整窗口：<confirm>
- 陈年复习卷模式：<off | suggest | auto>

## 个体基线

- 已有基础：<required>
- 当前困难：<required>
- 稳定教学注意事项：<confirm-or-none>

## 初始化纪律

1. 用户未确认的信息保持占位符。
2. 当前仓库就是一个学生实例，不创建学生编号包装层。
3. 课程、group、Engagement 与依赖下载均不得擅自生成。
4. 初始化完成后才将 `initialization_status` 改为 `initialized`。
