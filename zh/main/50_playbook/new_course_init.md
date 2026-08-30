# 新课程初始化

**保护级别**：core-playbook

## 前提

- 只有用户明确要建课或把候选课程纳入 T2AG 时才创建。
- 课程目录就是当前实例课程；不创建 Case、Definition/Run 或学生编号包装。
- 建课不等于加入 active group。容量变更另走组激活/结组流程。

## 目录

```text
main/40_course/<COURSE_ID>/
  course.md
  progress.md
  activity_map.md      # 任一 ongoing 课程首次建立 Lesson/Exercise 时创建
  lessons/
  exercises/
  mistake_bank.md
  question_bank.md
  book/
```

结构和字段从 `main/40_course/_templates/course/` 实例化；Core 语义见
`main/00_core/learning_activity_model.md`。Lesson 与 Exercise 是同级学习活动，模板必须
随 Skeleton 发行，不能靠当前模型临时回忆重建。

## 生成入口

```powershell
python -B main/70_tools/t2ag_init.py new-course --course-id <ID> --name <名称> `
  --course-type mastery `
  --learning-mode textbook --lifecycle ongoing --entry lesson|exercise --teacher Tddd `
  --source-language <en|zh-CN|...> `
  --verification-status <human_verified|synthetic_verified> `
  --source-scope <范围> --position <停点> --date YYYY-MM-DD
```

`--learning-mode` 只用于 Mastery 且必须显式给出。Project/Praxis 省略该参数；兼容
`--driver` 只允许旧 Mastery 调用映射到同名 mode，不允许 Project/Praxis 继续写 driver。

`--source-language` **必填、无默认**：它是本课程自身材料的语言（现存课程 en 与 zh-CN
各半），T001 §9 术语纪律读它来决定哪些术语必须保留原词。取错是**静默失败**——教师照常
执行纪律，只是对着错的语言执行。所以在建课时问一次，比事后发现整门课标错便宜。

这一条不是特例，是通则的一个例子：**会改变学习事实的语义参数一律必填，CLI 默认值不得
冒充一次确认**。判据不是「有没有默认值就够安全」，恰恰相反——**危险的正是有默认值的
那些**：无默认值的参数至多让命令失败，有默认值的参数会替学生静默答一次，事后没有任何
痕迹说明那是机器答的。因此除 `--source-language` 外，另有三个参数必填：

- `--course-type`：默认 `mastery` 会静默选定整条推进协议（CP 语义的核心对象）。
- `--entry`：默认 `lesson` 会静默创建第一个学习活动。
- `--verification-status`：默认 `human_verified` 直接断言「有人核验过」——那是关于世界的
  主张，工具无权代学生做出，默认即伪证。三个里它最强。

反过来，两类参数**不**必填：有互锁不变量机械护住的（`--lifecycle` 与 `--entry` 互锁，
静默错值必被拦），以及**没有唯一正确答案、须由建组仪式议定**的（三个容器参数，
`course_group_rules.md` §4.1：给它们设必填参只会逼出一个随手填的假值）。
`--learning-mode` 也不在必填之列——它已有双向运行时强制（Mastery 缺则拒、非 Mastery 给则拒），
再加 argparse 必填会废掉 Project/Praxis 建课。呈现规格见 `progress_governance.md` §8.1。

必填不等于把这些 flag 摆到学生面前问：答案在停顿 B 的方案里已经确认过，命令只是把已确认
内容如实写下来。

Mastery textbook-led + `--entry exercise` 时必须同时给 `--source-document`、`--source-locator`
与 `--problem-text`，工具才建持久校对题源、登记 artifact 并把 SHA 写进 `problems.md`；
缺任一项即拒绝生成，不允许用空题源占位。`--lifecycle planned` 必须配 `--entry none`。

下面的步骤是该命令实现的契约，用于人工复核与反向定位，不是要模型手抄文件。

## 步骤

1. 按 `naming_conventions.md` 校验稳定课程 ID，确认不存在同 ID 目录。
2. 创建 `course.md`：
   - `type: course`
   - `course_id`
   - `school_course_code`、`name`、`course_type`、Mastery-only `learning_mode`、`prerequisites`、
     `status: active`。这里的 status 只表示课程定义可用；学生 lifecycle 只写 progress。
   - 教材、教学原则、课程里程碑；不写里程碑当前状态。
   - 不写当前学生停点。
3. 创建 `progress.md`：
   - `type: course_progress`
   - `course_id`
   - `lifecycle_status: planned | ongoing`（全生命周期词表另含 paused/completed/dropped，见 `progress_tracking.md`；新课只从 planned/ongoing 起步）
   - Mastery：`learning_mode: textbook | goal | project`；Project/Praxis 不写 mode/driver
   - `truth_scope: course_lifecycle,course_frontend,activity_position`
   - planned 课程只写 `updated`、
     `progress_nodes_status: lazy_on_activation` 与下一动作；不得预填
     `current_activity / current_activity_id / resume_path / activity_position`。
   - ongoing 课程按真实入口创建首个 Lesson 或 Exercise，再原子写入
     `current_activity: lesson | exercise`、`current_activity_id`、canonical
     `resume_path`、`activity_position`、completion node、checkpoint 与下一动作；
     目标必须先存在。Exercise 首启不写 `current_lesson`，状态刷新器的
     “Lesson 上下文”必须从 ledger/ContentGroup 得到“无 / 无路径”，不得推断或预造
     `lessons/none/none.md`。
4. 创建 `activity_ledger.md`，`truth_scope: activity_lifecycle`；新课程从空 ledger 开始，
   只有真实创建活动时才追加 genesis ALE，不预造 planned 活动。
5. 创建 question bank V2，状态仅用 `open / answered / closed`；创建 mistake bank。
6. 用模板创建 `book/`、`lessons/`、`exercises/`；空活动域用 `_README.md` 持久化。
   - 首次从讲授进入：建立 `lessons/lesson01/lesson01.md`；教材课同时初始化
     `book/primary/source_assets/`（manifest 模板）与 lesson `preparation/`、`lesson_map` 模板，
     见 `source_page_assets.md`；页资产走 preparation Snapshot，不使用 legacy 路径。
   - 首次从做题进入：建立 `exercises/exercise01/exercise.md`、`problems.md` 与空
     attempts/reviews 说明文件；教材驱动课程还须先在 Course `book/` 内建立持久
     校对题源并登记 artifact，`problems.md` 写入其路径、定位和 SHA。
   - 所有推进协议的 ongoing 课程都建立 `activity_map.md`，按 ContentGroup 登记已有
     Lesson/Exercise；不存在的活动写 `—`，不预造真实活动或证据。ContentGroup 是共同活动
     关系，不是 textbook 专属结构；ledger genesis 引用了它，map 就必须同时拥有它。
7. 在 `20_teacher/overlay.md` 唯一的“课程—教师映射”表中增加一行；“教师模板”
   单元必须精确写成 `` `main/20_teacher/Tddd.md` ``，不得另建速览或从风格文字推断。
8. 若用户明确分配容量，再更新目标 group 的 plan/calendar；否则保持 unallocated。
9. 运行：

```powershell
python -B main/70_tools/t2ag_state_refresh.py --write
python -B main/70_tools/t2ag_state_refresh.py --check
python -B main/70_tools/t2ag_doctor.py --profile runtime
```

## 禁止

- 不创建第二份进度节点文件；节点并入 `progress.md`。
- 不把课程正文或进度塞入 binding。
- 不把 planned 课程自动加入 active group。
- 不自动创建 `.venv`、安装依赖或下载教材；需要时先取得用户授权。
