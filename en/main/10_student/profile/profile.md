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
teaching_language: <confirm-single-value-eg-en-US>
learning_day_cutoff: <confirm-HH:MM>
lesson_actual_review: <on|off>
lesson_student_feedback: <on|off>
lesson_knowledge_absorption: <on|off>
exercise_problem_review: <on|off>
exercise_knowledge_mastery: <on|off>
updated: —
---
# Student profile (empty template)

> Confirm every item with the user at first run. Never pre-fill a real name,
> school, course or student number, and never infer personality.

## Basic information

- Name or nickname: <required>
- School or institution: <required>
- Year or stage: <required>
- Field of study: <required>
- Time available per week: <required>

## Learning goals

- <required>

## Tutoring and presentation preferences

- General tutoring preference: <required>
- Long multi-block explanations: <map-first | continuous | user-defined>
- How to confirm between branches: <confirm>

## Execution parameters

- Cycle structure: <confirm>
- Minor-adjustment frequency: <confirm>
- Major-adjustment window: <confirm>
- Aged review-set mode: <off | suggest | auto>

## Individual baseline

- Existing foundation: <required>
- Current difficulties: <required>
- Standing teaching considerations: <confirm-or-none>

## Initialization discipline

1. Anything the user has not confirmed stays a placeholder.
2. This repository *is* one student instance; do not create a student-number wrapper layer.
3. Courses, groups, Engagements and dependency downloads must never be generated unilaterally.
4. Only after initialization completes may `initialization_status` become `initialized`.
