# 学习会话上下文包

**保护级别**：core-playbook

> 本流程减少开课与续课时的重复上下文装载。它优化的是“读取选择”，不是把长期证据
> 改写成更短的第二份真相源。

## 一、目标与边界

日常教学采用“即时摘录 + 触发式展开”：

1. `t2ag_context.py` 每次从当前权威文件生成只读上下文包；
2. 包内正文必须是源文件的逐字摘录或机械路由字段，不生成事实性改写；
3. 包只输出到标准输出，不落盘、不拥有状态、不参与写回；
4. `progress.md` 仍是进度唯一真相源，profile、Group、教师与活动各自权威边界不变；
5. 字符数只作为跨 tokenizer 的成本代理，不用近似 token 数冒充精确账单；
6. 软预算只能触发审查，不能截断定义、题面、确认门或安全边界。

若上下文包与源文件冲突，以源文件为准并停止推进。活动解析、教师映射和摘录必须共享
同一个原始字节缓存；结束前按文件字节及已观察目录清单复核全部来源未发生变化。
`source_sha256` 必须是原始文件字节摘要，可直接与 `Get-FileHash` 对照；展示文本只把
CRLF / CR 统一为 LF，以固定跨平台序列化字符数，不改变摘要口径。

## 二、三层读取模型

### L0：会话恢复包

新对话恢复已有课程时，运行：

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --format markdown
```

省略 `--course` 时，只允许从 memory 的“当前课程”指针解析，不扫描目录猜测。显式指定
非当前课程时，该课程必须仍属于 memory 指向的 active Group；包须标记
`explicit_same_active_group`，且不得把上一门课摘要当成目标课程恢复指针。组外课程直接
失败，先完成课程组切换。L0 包含：

- memory 的上次课摘要与当前指针；
- profile 的初始化状态、学习目标、辅导偏好、执行参数和个体总纲；
- learning path 中当前课程与 active Group 的精确表格行；
- active Group 的当前预算、成员与周期安排；
- `progress.md` frontmatter 与「当前进度」；
- 显式 LearningActivity 的恢复胶囊；
- open / 需要回看的疑问、活跃错题调度摘要；
- 当前课程相关感想、活跃思维模式和生效教师约束；
- 当前 Exercise 的唯一题面，或当前 Lesson 的必要教材窗口。

L0 不加载完整教学历史、全部已关闭问答、全部 Attempt/Review、无关课程、无关交接或
完整 journal。

### L1：当前一步

准备实际推进一个步骤时，只展开 L0 尚未包含、且该步骤直接需要的证据。可运行：

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --include-l1
```

- Exercise：当前题面与人工校对题源已在 L0；若当前题已有提交，再追加与该题直接相关的
  Attempt/Review；
- textbook Lesson：“前一页 + 当前页 + 后两页”窗口已在 L0；窗口缺失、缺页或进度
  未声明页码时不得返回 `ready`；
- 当前疑问或复测：对应 question / mistake 条目及其回链；
- 学生明确提出的想法：对应 thoughts 与已提炼反思。

首次呈现习题仍只给题面。上下文包可以让教师读取必要状态，但不得把内部提示、答案、
历史他人解法或思维树提前展示给学生。

### L2：触发式完整展开

仅在下列触发器出现时读取完整来源：

| 触发器 | 展开内容 |
|---|---|
| 状态冲突、指针悬空、并发变化 | 完整 progress、活动主载体与相关细粒度证据 |
| 用户询问历史、设计理由或原话 | 对应历史记录、交接或 journal |
| 排期、调参、组复盘或结组 | 完整 profile 执行参数、Group plan/calendar/review |
| 正式复测、订正或思维模式裁决 | 完整 mistake/question/reasoning 条目与证据回链 |
| 教师规则冲突或修改教师 | 完整 overlay、模板与变更来源 |
| session close | `session_close.md` 指定的全部写入与回读目标 |
| 项目审计、迁移或发布 | 匹配的 project handoff、合同、测试和实际 Git 状态 |

“可能有用”不是展开理由；必须能说出当前触发器。

## 三、会话内复用与失效

同一对话内，未变化的 L0 包只读一次。以下任一情况使其失效：

1. `progress.md`、当前活动、profile、active Group 或教师映射被写入；
2. 外部同步、另一 agent 或用户编辑了包内来源；
3. 对话压缩后无法确认仍保留当前停点与关键约束；
4. current activity 或当前题目发生切换；
5. 工具报告来源在生成期间变化。

失效后重新运行上下文工具。普通问答轮次不得机械重读所有文件。

## 四、写回纪律

上下文包永远不可编辑或写回。结课仍按：

```text
progress.md
→ 当前 Lesson / Exercise 与真实台账
→ state_refresh --write
→ state_refresh --check
→ doctor
→ 重读本次实际写入目标
```

结课回读只覆盖实际写入目标；不因验证而重载全部历史。下一次会话再从新状态生成新包。

## 五、成本账与验收

工具把两个不同问题分开报告：

- `reference_inventory_chars`：本轮涉及来源文件的当前全文字符库存，仅作选择对照；不是
  旧流程 Prompt 实测；
- `l0_selected_source_chars` / `l1_selected_source_chars`：逐字摘录正文字符；
- `source_selection_ratio` / `source_inventory_omitted_percent`：源内容选择率；不得表述为
  端到端 Token 降幅；
- `serialized_l0_markdown_chars`：默认 Markdown 的完整字符数，包含标题、路径、原始字节
  SHA、路由与 L2 表；
- `serialized_l0_plus_l1_markdown_chars`：附加首个 L1 后的完整 Markdown 字符数；
- 每个来源的原始文件字节 SHA-256 与选择标签。

若没有保存旧 Prompt 的真实序列化结果，本工具不得给出端到端降低百分比。字符数仍是
tokenizer 无关的代理，不等于模型 Token 或账单。验收必须同时满足：

1. 当前指针、唯一活动、下一动作、学生约束、教师红线和当前教材/题面均可恢复；
2. packet 不含完整 progress 历史、全部 closed question 或无关课程正文；
3. packet 生成过程只读，且不会创建 `.venv`、缓存状态文件或第二真相源；
4. 两个 `serialized_*` 数值必须分别等于实际渲染结果长度；
5. Main、Skeleton、Lite 的 core playbook 与工具保持同源；
6. 任何压缩收益不得以降低确认、证据或安全标准换取。

默认软预算为 16,000 个实际序列化 Markdown 字符，分别检查 L0 与 L0+首个 L1。超过时
只输出 `REVIEW`，由维护者检查是否存在新的重复存量；不得静默丢字段。

## 六、降级

- profile 未初始化、仍含必填占位符或 memory 日期为 `—`：输出
  `first_run_required`，转 `first_run.md`，不生成伪课程包。
- 当前课程不存在、不是 `ongoing`、不属于 active Group、活动路由失败、textbook Lesson
  缺教材窗口，或来源在读取期间变化：命令非零，先修权威链，不开新内容。
- 工具不可执行：按 `lesson_recover.md` 的同名章节手工做分层摘录；不得退回无差别
  全仓读取。

## 七、关联文件

- `main/t2ag.md`：启动入口与日常接管。
- `main/50_playbook/lesson_recover.md`：课程恢复及 L1/L2 触发。
- `main/50_playbook/session_close.md`：写回与回读。
- `main/70_tools/t2ag_context.py`：只读上下文包生成器。
- `main/70_tools/t2ag_activity.py`：唯一活动路由器。
