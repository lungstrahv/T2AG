# Course 初始化模板

本目录是系统发行模板，不是真实课程实例。首次初始化或新增课程时，按
`main/50_playbook/new_course_init.md` 复制所需文件，并把大写占位符替换为真实 ID。

Lesson 与 Exercise 是同级学习活动；先创建哪一种取决于学生的真实学习入口。
不得复制 `.template` 后仍保留占位符，也不得预造 Attempt、Review 或想法证据。
教材 Exercise 还须复制 `book/primary/verified_excerpts/source.md.template`，校对后
登记 artifact，并让 `problems.md` 以路径、定位和 SHA 引用；不得引用 Lesson cache。
新 Attempt 的 `HINT_GATE_MODE` 必须取创建时 profile 的 `exercise_hint_gate` 快照。
