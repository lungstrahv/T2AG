---
type: student_profile
initialization_status: uninitialized
exercise_hint_gate: ask
agent_collaboration_schema: agent_collaboration_preferences.v1
agent_pool_limit: 6
agent_max_active: 3
agent_parallel_startup: enabled
agent_startup_readiness: learning_ready_first
agent_background_reporting: blockers_only
activity_close_preference_schema: activity_close_preferences.v1
activity_close_preferences_initialized_at: <set-on-initialization>
activity_close_first_prompt_status: pending
activity_close_first_prompt_at: none
learning_timezone: <confirm-IANA-timezone>
learning_day_cutoff: <confirm-HH:MM>
lesson_actual_review: <on|off>
lesson_student_feedback: <on|off>
lesson_knowledge_absorption: <on|off>
exercise_problem_review: <on|off>
exercise_knowledge_mastery: <on|off>
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

- 一般辅导偏好：<required>
- 多块长篇讲解：<map-first | continuous | user-defined>
- 分支间确认方式：<confirm>

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
