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
teaching_language: zh-CN
learning_day_cutoff: <confirm-HH:MM>
lesson_actual_review: <on|off>
lesson_student_feedback: <on|off>
lesson_knowledge_absorption: <on|off>
exercise_problem_review: <on|off>
exercise_knowledge_mastery: <on|off>
updated: —
---
# 学生档案（空模板）

> 首次启动只展示五项可选资料；不得预填真实姓名、学校、课程、学生编号或推断性格。

## 基本信息

- 称呼：同学
- 学习水平：secondary_school
- 是否引入参考培养方案：pending_generation

## 学习兴趣

- 有待生成

## 自我介绍

- 未提供

## 初始化纪律

1. 五项资料都可跳过；未回答时使用上述公开默认值。
2. 当前仓库就是一个学生实例，不创建学生编号包装层。
3. 课程、group、Engagement 与依赖下载均不得擅自生成。
4. 初始化完成后才将 `initialization_status` 改为 `initialized`。
