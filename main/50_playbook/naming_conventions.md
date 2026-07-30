# T2AG 0.2.0 命名规范

## 目录

- 编号域：英文单数，保留 `NN_`，间隔 10。
- `main/` 编号域固定为 `00/10/20/30/40/50/60/70/80`。
- 课程：`40_course/<COURSE_ID>/`，目录名就是稳定课程 ID。
- group：`30_group/GNN/`。
- lesson：`lessons/lessonNN/`。
- working pages：`working_pages/pages/pageNN.png` 与
  `working_pages/raw_ocr/page_NN_raw.txt`。

## 稳定 ID

| 对象 | 格式 |
|---|---|
| Course | 学校/自设课程代码，如 `MATH1607H`、`PY1001`、`PHIL1101r` |
| Group | `GNN` |
| Binding | `RNNN` |
| ActivityRecord | `AR-NNNN` |
| Engagement | `EG-NNNN` |
| Mistake | `M-NNNN` |
| Question | `Q-NNNN` |
| ReasoningPattern | `RP-NNNN` |
| ContentGroup | `<COURSE_ID>-Bddd-Cdd-Sdd`（Course 内） |
| Exercise | `Udddd`（Course 内） |
| ExerciseProblem | `<UNIT_ID>-Qddd`（Course 内） |
| Attempt | `ATdddd`（Exercise 内） |
| Review | `RVdddd`（Exercise 内） |

课程尾标 `r` 表示通识内容属性；弹性执行语义只由 group `bindings/` 的位置和字段
表达，不能从尾标反推当前 binding 状态。

Attempt 与 Review 是 Exercise 内局部稳定 ID；完整身份为
`course_id / exercise_id / local_id`。
Review 不使用 `RNNN`，避免与 Binding 命名空间冲突。

## 文件

- Course：`course.md` + `progress.md`
- Engagement：`engagement.md`
- Group：`plan.md` + `calendar.md` + `review.md`
- Python/脚本：`snake_case`
- 人类展示名可以中文；canonical 路径、ID、frontmatter 和工具参数只用 ASCII。

## 迁移与 registry

- 改路径不改稳定 ID。
- active canonical 全局唯一。
- 多源合流：保留 survivor，其他 artifact 用 tombstone + alias。
- composite 拆分：旧 artifact 用 tombstone + successors。
- redirects 只追加并压成一跳；历史原文不机械改写。
