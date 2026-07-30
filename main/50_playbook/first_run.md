# 首次启动

首次启动只初始化一个学生实例，不创建学生编号层。

## 判据

- `10_student/profile.md` 的 `initialization_status` 不是 `initialized`；或
- profile 仍含必填占位符；或
- memory 上次课摘要日期为 `—`。

## 步骤

1. 按 `main/t2ag.md`「3.0 启动欢迎信息」展示当前发行版的 `welcome_msg`、
   active `art_file` 字符画与版本号。
2. 运行 doctor，确认 Skeleton 结构有效且没有真实实例。
3. 询问并确认学校、年级、方向、目标、可投入时间、已有基础和辅导偏好。
   当前困难与特殊要求是可选信息；未提供时明确写“未提供”，不得保留“待填写”。
4. 将 profile 从模板改为 `initialization_status: initialized`。
5. 与用户确认首门课程及真实入口（先进入 Lesson 还是 Exercise）；从
   `40_course/_templates/course/` 按 `new_course_init.md` 创建 Course 和首个学习活动。
6. 与用户确认第一个 group 的成员、预算和日历，建立 plan/calendar/review，
   并用 `bindings/_README.md` 持久化空 binding 域。
7. 在 `20_teacher/overlay.md` 唯一的“课程—教师映射”表中建课程到教师模板的
   显式行；模板单元使用精确 `` `main/20_teacher/Tddd.md` `` 路径。
8. 完成发行身份切换，但不启动云同步：
   - 把 active skin 的 `art_file` 改为用户确认的个人实例字符画；未另选时使用
     `03_inori_2.txt`，不再保留 Skeleton 专用 `01_welcome.txt`；
   - 将 Cloud project mode 从 `generic_skeleton` 切为 `personal_instance`，在状态中
     明确 `new_cloud_sessions_allowed: false` 与
     `new_component_directives_allowed: false`，并让个人实例提示词携带
     `T2AG_SESSION_CLOSE / T2AG_CLOUD_CHANGE_DIRECTIVE / T2AG_CLOUD_HANDOFF`；
   - `cloud_bridge_status` 继续保持 `paused`，本步骤不授权任何云写回。
9. 更新课程 `progress.md` 的起点与下一动作。
10. 运行 state refresh `--write`，让 memory 的当前 group、课程、LearningActivity、教师与
   `learning_path.md` 同步生成；确认这些指针不再为 `—`。
11. 运行 state refresh `--check` 和 doctor，只有两者都通过才算首次启动完成。

不得自动创建 `.venv`、安装依赖、下载教材、生成真实 Engagement 或替用户选择课程。
