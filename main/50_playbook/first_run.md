# 首次启动

首次启动只初始化一个学生实例，不创建学生编号层。

## 判据

- `10_student/profile/profile.md` 的 `initialization_status` 不是 `initialized`；或
- profile 仍含必填占位符；或
- memory 上次课摘要日期为 `—`。

## 生成入口

实例由 `main/70_tools/t2ag_init.py` 生成，不由模型照本文手抄文件：

```powershell
python -B main/70_tools/t2ag_init.py init --answers answers.json
python -B main/70_tools/t2ag_init.py new-course --course-id <ID> --name <名称> ... --date YYYY-MM-DD
python -B main/70_tools/t2ag_init.py new-group --group-id G01 --members <ID> --status active --date YYYY-MM-DD
```

`answers.json` 保存第 3 步逐项确认的结果。工具缺任一必答项即拒绝执行，不代填默认值；
也不创建 `.venv`、不装依赖、不下教材、不生成 Engagement、不做 git 写入。
模型的职责是提问、把答案写成 `answers.json`、调用工具、复核输出，而不是发明 schema。

## 步骤

1. 按 `main/t2ag.md`「3.0 启动欢迎信息」展示当前发行版的 `welcome_msg`、
   active `art_file` 字符画与版本号。
2. 运行 doctor，确认 Skeleton 结构有效且没有真实实例。
3. 询问并确认学校、年级、方向、目标、可投入时间、已有基础和辅导偏好；告知启动协作
   默认是一个主 Agent 加两个只读辅助 Agent；Agent 池容量默认 6，同时运行上限默认 3，
   两者都包含 Main。默认使用 `agent_pool_limit: 6`、`agent_max_active: 3` 与
   `agent_parallel_startup: enabled`；学生可将池容量设为 1–6、并发设为 1–3（并发不得超过
   池容量），或关闭并行。默认 `agent_startup_readiness: learning_ready_first`、
   `agent_background_reporting: blockers_only`；学生也可选择等待 recovery-settled 后开课或
   播报全部后台结果。未要求覆盖时不追加阻断问题。辅导偏好还包括
   多块长篇讲解是否沿用默认的“先地图、后逐支”，以及学生希望怎样确认后再继续。同时让
   学生选择 `exercise_hint_gate: enabled | disabled`，不得由模型代选。
   当前困难与特殊要求是可选信息；未提供时明确写“未提供”，不得保留“待填写”。
4. 运行 `t2ag_init.py init`（对应本步与第 8 步）。它将 profile 从模板改为
   `initialization_status: initialized`，并写入
   `agent_collaboration_preferences.v1`、`agent_pool_limit`、`agent_max_active`、`agent_parallel_startup`、
   `agent_startup_readiness`、`agent_background_reporting`、
   `activity_close_preferences.v1`、五项全局结课偏好、学习时区/cutoff、
   `activity_close_preferences_initialized_at`。首次结课提示 marker 初始化为
   `pending` / `none`；真正展示一次后才原子改为 `shown` / 带时区时间。
5. 与用户确认首门课程及真实入口（先进入 Lesson 还是 Exercise）；用
   `t2ag_init.py new-course` 按 `new_course_init.md` 创建 Course 和首个学习活动。
6. 与用户确认第一个 group 的成员、预算和日历；用 `t2ag_init.py new-group` 建立
   plan/calendar/review，并用 `bindings/_README.md` 持久化空 binding 域。
   多成员 active 组必须由用户指定 `--current-course`。
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
