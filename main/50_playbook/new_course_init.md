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
  activity_map.md      # 教材课程首次建立 Lesson/Exercise 时创建
  lessons/
  exercises/
  mistake_bank.md
  question_bank.md
  book/
```

结构和字段从 `main/40_course/_templates/course/` 实例化；Core 语义见
`main/00_core/learning_activity_model.md`。Lesson 与 Exercise 是同级学习活动，模板必须
随 Skeleton 发行，不能靠当前模型临时回忆重建。

## 步骤

1. 按 `naming_conventions.md` 校验稳定课程 ID，确认不存在同 ID 目录。
2. 创建 `course.md`：
   - `type: course`
   - `course_id`
   - `school_course_code`、`name`、`course_type`、`default_driver`、`prerequisites`、
     `status: active`。这里的 status 只表示课程定义可用；学生 lifecycle 只写 progress。
   - 教材、教学原则、课程里程碑；不写里程碑当前状态。
   - 不写当前学生停点。
3. 创建 `progress.md`：
   - `type: course_progress`
   - `course_id`
   - `lifecycle_status: planned | ongoing`
   - `course_driver: textbook | goal | project | praxis`
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
   - 首次从讲授进入：建立 `lessons/lesson01/lesson01.md`；教材课同时建立 working pages。
   - 首次从做题进入：建立 `exercises/exercise01/exercise.md`、`problems.md` 与空
     attempts/reviews 说明文件；教材驱动课程还须先在 Course `book/` 内建立持久
     校对题源并登记 artifact，`problems.md` 写入其路径、定位和 SHA。
   - 教材课建立 `activity_map.md`，按 ContentGroup 登记已有 Lesson/Exercise；不存在的
     活动写 `—`，不预造真实活动或证据。
7. 在 `20_teacher/overlay.md` 唯一的“课程—教师映射”表中增加一行；“教师模板”
   单元必须精确写成 `` `main/20_teacher/Tddd.md` ``，不得另建速览或从风格文字推断。
8. 若用户明确分配容量，再更新目标 group 的 plan/calendar；否则保持 unallocated。
9. 运行：

```powershell
python -B main/70_tools/t2ag_state_refresh.py --write
python -B main/70_tools/t2ag_state_refresh.py --check
python -B main/70_tools/t2ag_doctor.py
```

## 禁止

- 不创建第二份进度节点文件；节点并入 `progress.md`。
- 不把课程正文或进度塞入 binding。
- 不把 planned 课程自动加入 active group。
- 不自动创建 `.venv`、安装依赖或下载教材；需要时先取得用户授权。
