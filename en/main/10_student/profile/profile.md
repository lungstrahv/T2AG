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
learning_timezone: UTC
teaching_language: en-US
learning_level: secondary_school
reference_curriculum: pending_generation
learning_day_cutoff: 04:00
lesson_actual_review: on
lesson_student_feedback: on
lesson_knowledge_absorption: on
exercise_problem_review: on
exercise_knowledge_mastery: on
updated: —
---
# Student profile (empty template)

> All five profile items are optional. Never infer a real name, school, course,
> student number, or personality. Unanswered items use the public defaults below.

## Basic information

- Preferred name: Learner
- Learning level: Secondary-school student
- Introduce a reference curriculum: To be generated

## Learning interests

- To be generated

## Self-introduction

Not provided.

## Initialization discipline

1. All five questions are optional. An empty reply keeps the documented defaults;
   do not ask follow-up questions to fill blanks.
2. This repository *is* one student instance; do not create a student-number wrapper layer.
3. Courses, groups, Engagements and dependency downloads must never be generated unilaterally.
4. Only after initialization completes may `initialization_status` become `initialized`.
