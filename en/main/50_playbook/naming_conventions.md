# T2AG 0.2.2 命名规范

**保护级别**：playbook

## 目录

- 编号域：英文单数，保留 `NN_`，间隔 10。
- `main/` 编号域固定为 `00/10/20/30/40/50/60/70/80`。
- 课程：`40_course/<COURSE_ID>/`，目录名就是稳定课程 ID。
- group：`30_group/GNN/`。
- lesson：`lessons/lessonNN/`。
- 教材页资产（EV-0012 / Course 权威链）：
  - 持久核验文本、raw OCR 与元数据：
    `book/primary/source_assets/<document_id>/pages/page_<pdf_index>.md`、
    `book/primary/source_assets/<document_id>/raw_ocr/page_<pdf_index>_raw.txt` 等；
  - 可重建 PNG 缓存：
    `book/.cache/source_pages/<source_document_sha256>/<render_profile>/page_<pdf_index>.png`；
  - 教材插图重建物（P-0059 恢复；owner 为 `source_page_assets.md` §1.3）：
    `book/primary/source_assets/<document_id>/illustrations/<章号>_<节号>_<图号>_<描述>.{tex,html}`，
    如 `1_1_1_venn_diagram.tex` / `.html`。**只出 TikZ 源与 HTML/SVG 两种，不出 PDF。**
    图形是文档/页的属性，**不放 `lessons/lessonNN/`**；lesson 侧如需引用用指针不用副本；
  - Lesson 只持有 `lesson_map.md`、不可变 preparation Snapshot（`preparation/PREP-*.json`）
    与 current pointer（`preparation/current_snapshot.json`），不复制页图/OCR 正文。
- **已退役**（历史摘录见归档位）：原 `lessons/lessonNN/working_pages/**`
  （含历史 `pages/pageNN.png`、`raw_ocr/page_NN_raw.txt`、`source_excerpt.md`）。
  **不得**作为新课程、新 Lesson 或新备课的 canonical 输出；retained
  `source_excerpt.md` **不是**新建教材权威。

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
| Lesson | `lessonNN`（Course 内；`NN` 至少两位） |
| Exercise | `exerciseNN`（Course 内；`NN` 至少两位） |
| ExerciseProblem | `exerciseNN-Qddd`（Course 内） |
| Attempt | `ATdddd`（Exercise 内；ID 本身不变） |
| Review | `RVdddd`（Exercise 内；ID 本身不变） |
| ActivityLifecycleEvent | `ALE-NNNNNN`（Course 内单调、允许缺号） |
| CloseRecord | `CLR-NNNN`（Course 内单调、允许缺号） |

### Legacy alias（只解析，不输出为 canonical）

| 旧 ID | 说明 |
|---|---|
| `Udddd` | 0.2.1 及更早 Exercise 目录/ID；0.2.2 **禁止新建**；仅通过 `activity_ledger` alias 解析旧输入 |
| `Udddd-Qddd` | 旧 ExerciseProblem；映射到 `exerciseNN-Qddd` |

MATH1607H 的 `U1101` → `exercise01` 是一次 canonical replacement，不是“稳定 ID 可任意改名”的一般规则。

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
