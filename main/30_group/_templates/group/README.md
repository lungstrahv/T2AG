# Group 初始化模板

本目录是系统发行模板，不是真实课程组实例。首次启动或新建课程组时，按
`main/50_playbook/course_group_rules.md` 与 `group_transition.md` 复制所需文件到
`main/30_group/Gdd/`，并把大写占位符替换为真实值。

新建的课程组默认 `status: planned`。转 `active` 需要独立的组激活审查，
不得在创建时直接写 `active`——同一实例只允许一个 active 组。

- `plan.md`：成员组合、激活闸门与容量边界。课程进度仍以各课 `progress.md` 为唯一真相源。
- `calendar.md`：容量草案。planned 组的日历不产生课程进度，也不改变任何课程生命周期。
- `review.md`：组合层复盘与结组证据。planned 组只预留位置，不产生完成记录。
- `bindings/_README.md`：持久化空 binding 域。没有弹性执行绑定时保留该说明文件即可。

不得复制 `.template` 后仍保留占位符；不得把课程正文或课程进度塞入 binding；
不得把 planned 课程自动加入 active 组。
