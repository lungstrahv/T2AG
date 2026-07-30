# journal 管理流程

**保护级别**：meta-playbook

> 本文件是 T2AG「技能固化」文档之一。
> 当用户明确要求保存重要对话、关键决策、待办或跨课程事件记录时触发。
>
> **适用场景**：记录不属于课程进度、不属于系统故障、不属于规则变更、但未来值得主动回看的事件与决策。

---

## 一、核心原则

- journal 保存**事件、决策、待办**，不是事实注入、不是错题本、不是规则源。
- 默认不自动写入；只有用户明确要求“记入 journal / 保存这段 / 这段很重要”时才写。
- 每篇只保留非 trivial 的决策和结论，删除闲聊、重复确认和无意义过程。
- 默认每次有非平凡结果的对话新建一篇 `YYYY-MM-DD-<topic>.md`。
- 只有新内容是旧 journal 的直接延续或更正时，才追加到旧文件。
- 不确定是否合并时，先读当月和上月索引，再问用户是新建还是追加。

---

## 二、与现有文件的分流

| 内容类型 | 写入位置 |
|---|---|
| 规则、结构、模板、工具变更 | `main/00_core/t2ag_changelog.md` |
| 系统/流程问题与解决 | `main/00_core/t2ag_problemlog.md` |
| 课程进度、停顿点、教学记录 | `[课程]/progress.md` / 当前 Lesson 或 Exercise 主载体 |
| 学生知识错误 | `[课程]/mistake_bank.md` |
| 学生情绪、性格、课程感受 | `main/10_student/profile.md` / `course_reflections.md` |
| Lesson 局部想法 | `lessons/lessonNN/lesson_thoughts.md`（真实出现时创建） |
| Exercise 学生原话与跨题索引 | 对应 Attempt / `exercises/exercise_thoughts.md` |
| 跨 lesson / exercise 的课程核心内容思考 | `main/10_student/course_reflections.md` 当前课程段，并回链局部来源 |
| 跨课程、跨实践、非故障类的重要事件/决策/待办 | `main/60_journal/` |

journal 是回看层，不覆盖任何真相源。

---

## 三、目录与命名

```text
main/60_journal/
├── INDEX.md
├── YYYY-MM.md
└── YYYY-MM-DD-<主题关键词>.md
```

- `INDEX.md`：总索引。
- `YYYY-MM.md`：月度索引/报告。
- `YYYY-MM-DD-<主题关键词>.md`：单篇 journal。

索引表由 `main/70_tools/build_journal_index.py` 维护。新增或修改 journal 后：

```powershell
python -B main/70_tools/build_journal_index.py --write
python -B main/70_tools/build_journal_index.py --check
```

- 无参数与显式 `--check` 都只读检查；只有 `--write` 会改写生成块。
- `INDEX.md` 与当前 `YYYY-MM.md` 的 `T2AG_GENERATED` 块不得手工编辑；块外正文仍由人维护。
- 新月份先创建对应 `YYYY-MM.md` 并安装一个月度列表生成块，再运行生成器。

---

## 四、单篇模板

```markdown
# YYYY-MM-DD 主题

> **日期**：YYYY-MM-DD
> **状态**：进行中 / 待验证 / 已完成 / 已归档

## 主题

1. ...

## 使用到的 Skill

| Skill 名称 | 次数 | 用途 |
|---|---|---|
| `skill-name` | 1 | ... |

> 若本次没有加载 skill，写：本次对话未加载 skill。

## 关键决策

- ...

## 待办

- [ ] ...

## 关联文件

- ...
```

### 最小索引 metadata schema

- 第一条一级标题（`# ...`）是索引标题。
- `日期` 和 `状态` 使用模板中的引用行；日期格式为 `YYYY-MM-DD`。
- 为兼容现有 journal，缺少 `日期` 时依次回退到文件名前缀、一级标题日期、标题前导区出现的首个 ISO 日期；缺少 `状态` 时显示 `—`。
- 这是兼容旧文件的最小 schema。生成器不反向改写 journal 正文；新文件应显式填写日期和状态，避免依赖回退。

---

## 五、常见问题

- **把 journal 当自动流水账**：错。默认不自动写，用户明确要求才写。
- **把系统故障写进 journal**：错。系统故障进入 `problemlog`。
- **把规则变更只写 journal**：错。规则变更必须进入 `changelog`。
- **默认把新对话并入旧 journal**：错。只有直接延续或更正才合并；否则新建。
- **漏掉使用到的 Skill 表**：不合格。即使没有加载 skill，也要写明“本次对话未加载 skill”。
- **手改索引生成块**：错。修改 journal 的标题或 metadata，再运行生成器。

---

## 六、关联文件

- `main/60_journal/INDEX.md` —— journal 总索引。
- `main/60_journal/YYYY-MM.md` —— 月度索引。
- `main/00_core/t2ag_changelog.md` —— 规则变更。
- `main/00_core/t2ag_problemlog.md` —— 系统/流程问题。
- `main/50_playbook/playbook_management.md` —— 程序性记忆管理。
