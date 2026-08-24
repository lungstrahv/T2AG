# 首次启动

**保护级别**：playbook

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
python -B main/70_tools/t2ag_init.py new-group --group-id G01 --members <ID> --container-mode <progress|schedule> --date YYYY-MM-DD
python -B main/70_tools/t2ag_init.py activate-group --group-id G01 --date YYYY-MM-DD
```

组**只能生为 planned**（2026-08-22 用户裁决）：`active` 是建组仪式之后的状态，
`new-group` 不收它。仪式内容——议定 `calendar.md` 容量参数、progress 组把
`plan.md`「主干碑序列」的模板行替换为逐碑确认的真实碑行——发生在两条命令之间；
`activate-group` 只做公证：验真实碑行、数碑落锚 `keystone_total_frozen`、翻状态。
碑行仍是模板占位（`碑描述`）时它会拒绝执行——那不是刁难，是防「状态先出现、
判断没发生」（P-0077 同族）。

`answers.json` 只保存第 3 步中用户愿意提供的资料；五项均可省略，工具按公开 schema 补默认值；
也不创建 `.venv`、不装依赖、不下教材、不生成 Engagement、不做 git 写入。
模型的职责是提问、把答案写成 `answers.json`、调用工具、复核输出，而不是发明 schema。

## 新手界面边界

首次启动必须区分两层：

- **学生层**：想学什么、希望达到什么结果、已有基础、每周大约能投入多少时间，以及现在
  想直接开始学习还是先做一道题看看水平；
- **实现层**：`course_type`、`course_driver`、`entry`、`group_id`、`container_mode`、
  `cycle_structure`、教师模板 ID 等落盘字段。

实现层字段默认不向首次使用者展示，也不逐项要求确认。特别禁止：

- 把“入口”“首个课程组”“`G01`”“目标驱动”“`progress / schedule`”“`3-1-3`”等术语
  放进默认设置清单；
- 询问“是否接受上一条列出的全部默认设置”或同义的整包确认；
- 仅仅因为命令需要参数，就把参数名变成学生必须理解的问题。

需要学生作真实选择时，先问可感知的后果。例如问“现在从第一小节开始，还是先做一道题
看看目前水平？”，不得问“入口选 Lesson 还是 Exercise？”；问“通常哪几天学习、每次大约
多久、要不要固定留一天休息？”，不得让新用户选择节奏码。只有学生主动追问技术细节或
明确要自定义高级设置时，才展示实现层术语并当场解释。

最终确认只回读学生说过的事实和马上会发生的动作，例如“建立《小说写作基础》，现在从
第一小节开始，每周约 4 小时”。然后问“这些是否准确，现在开始创建吗？”。内部 ID、枚举、
默认节奏与教师映射不进入该确认。

## 步骤

1. 按 `main/t2ag.md`「3.0 启动欢迎信息」展示当前发行版的 `welcome_msg`、
   active `art_file` 字符画与版本号。
2. 运行 doctor，确认 Skeleton 结构有效且没有真实实例。
3. 一次性展示下面五项可选资料，不得拆成一长串阻断问答，也不得追加学校、年级、专业、
   每周时间、学习目标、已有基础、困难、辅导偏好、Agent 数量或提示闸门问题：
   - 称呼（自由文本）；
   - 学习水平（参考选项：`中学在读 / 大学在读 / 学士`）；
   - 是否引入参考培养方案（参考选项：`是 / 否`）；
   - 学习兴趣（自由文本）；
   - 自我介绍（自由文本）。
   五项都可跳过；空回复不得继续追问。默认值依次为 `同学`、`中学在读`、`有待生成`、
   `有待生成`、`未提供`。内部值与字段形状见 `main/70_tools/answers.schema.json`；
   `answers.example.json` 只展示五项真实形状，带 `example_only: true`，工具必须拒绝直接消费。
   启动协作、结课记录、长篇组织、提示闸门、时区和 cutoff 全部使用 schema 默认值，用户日后
   可在 profile 中修改。讲解语言不在本步询问：安装阶段的无默认语言选择已经决定 Edition，
   中文版模板为 `zh-CN`，英文版模板为 `en-US`，`init` 只保留该值。
4. 运行 `t2ag_init.py init`（对应本步与第 8 步）。它将 profile 从模板改为
   `initialization_status: initialized`，并写入
   `agent_collaboration_preferences.v1`、`agent_pool_limit`、`agent_max_active`、`agent_parallel_startup`、
   `agent_startup_readiness`、`agent_background_reporting`、
   `activity_close_preferences.v1`、五项全局结课偏好、学习时区/cutoff、
   `activity_close_preferences_initialized_at`。首次结课提示 marker 初始化为
   `pending` / `none`；真正展示一次后才原子改为 `shown` / 带时区时间。
5. 与学生确认首门课程的主题、想达到的结果，以及马上要做的第一件事。只用“从第一小节
   开始学习”或“先做一道题看看水平”等自然语言；模型在内部映射为 Course 类型、driver 与
   `lesson | exercise`，不得把“类型”“入口”枚举交给新用户选择。用
   `t2ag_init.py new-course` 按 `new_course_init.md` 创建 Course 和首个学习活动。
6. 第一组在内部使用下一个合法 Group ID；首次只有一门课时，成员就是刚创建的课程，不再
   询问“首个课程组”或要求确认 `G01`。仅询问尚未从对话得知的实际容量与日历事实：通常
   哪几天学习、每次多久、是否固定休息。模型把回答映射成预算、日历、容器与循环字段；
   `3-1-3` 等节奏码默认不展示。用 `t2ag_init.py new-group` 建立 plan/calendar/review，并用
   `bindings/_README.md` 持久化空 binding 域。只有学生明确同时建立多门课程时，才用自然
   语言确认先学哪一门，并在内部传给 `--current-course`。
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
