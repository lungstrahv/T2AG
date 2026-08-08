# 学习会话上下文包

**保护级别**：core-playbook

> 本流程减少开课与续课时的重复上下文装载。它优化的是“读取选择”，不是把长期证据
> 改写成更短的第二份真相源。

## 一、目标与边界

日常教学采用“即时摘录 + 触发式展开”：

1. `t2ag_context.py` 每次从当前权威文件生成只读上下文包；
2. 包内正文必须是源文件的逐字摘录或机械路由字段，不生成事实性改写；
3. 包只输出到标准输出，不落盘、不拥有状态、不参与写回；
4. `progress.md` 只读 Course 生命周期、唯一前台与停点；Activity 生命周期必须从
   `activity_ledger.md` replay，profile、Group、教师与活动证据各守自身权威边界；
5. 字符数只作为跨 tokenizer 的成本代理，不用近似 token 数冒充精确账单；
6. 软预算只能触发审查，不能截断定义、题面、确认门或安全边界。

若上下文包与源文件冲突，以源文件为准并停止推进。活动解析、教师映射和摘录必须共享
同一个原始字节缓存；结束前按文件字节及已观察目录清单复核全部来源未发生变化。
`source_sha256` 必须是原始文件字节摘要，可直接与 `Get-FileHash` 对照；展示文本只把
CRLF / CR 统一为 LF，以固定跨平台序列化字符数，不改变摘要口径。

日常三 Agent 启动时，Context Prefetcher 必须先独立运行 `--format critical`，立即回交
L0-critical，再在同一轮后台生成完整 Markdown L0。critical 只读取 route 与首轮动作真正
依赖的来源，不等待反思、非当前错题、Group 细节或成本账；Main 收到可信 handoff 后，
非 textbook 可进入 `learning-ready`。textbook critical 只到 `route-ready`，还须等待同一
snapshot 的 Scope 会话扫描（`source_page_assets.md` §3.1 A1–A6）。后台包必须回报同一个 `snapshot_id`，Doctor/state 与完整来源核对
也收敛后才进入 `recovery-settled`。handoff 不落盘；Main 收到 critical 后不得再次运行
Markdown L0、搜索 ledger、解码 pending body 或拼装结课确认。完整后台超时仍为 45 秒；
critical 目标不超过 10 秒；15 秒首条动作目标只适用于无需 Scope 视觉扫描的路由。

> **Packet 不授权（2026-08-06）**：textbook 且 `scope_scan` pending 时，critical 顶层应为
> `status=route_ready`、`blocking_teach=true`，`teaching_gate.admission_status=unavailable`、
> `egress_mode=status_only`，并 withhold 可照发教材正文/开场正文。这些字段与
> `may_release_action` **只用于可观察性**，不构成发送授权。结构性硬门依赖宿主
> `lesson_emit`（见 `docs/adr/0002-host-controlled-textbook-teaching-egress.md` 与
> `docs/protocol/host-teaching-egress-api.md`）。仓库层 withhold **不**等于已拦截对外输出。

## 二、三层读取模型

### L0-critical：关键路径包

启动关键路径运行：

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --format critical
```

输出是最多 12,000 字符的 JSON，只含 status、course、snapshot、route、blocker、四类公开
来源 SHA、`teaching_gate` 与 `action_payload`。Lesson 的权威 pending prompt 必须逐字来自
`progress.md` 当前切片的“精确停顿点”并标明来源；模型可以附加明确标注的概括、暖场、
类比或探索问题，但不得替换权威停点或绕过 Exercise 提示闸门。当前教材片段必须来自当前
`pdf_page_index` 的实际页资产，不得使用 Scope 首文件路径。若存在
`LessonPreparationSnapshot`，critical/`action_payload` 可附带 `preparation_snapshot_id`、
`lesson_scope_version`、当前页 `source_page` 和 `scope_scan` manifest（PDF 路径/SHA、完整
页索引、render profile），并必须附带 `page_teaching_contract`。该合同给出 PDF/书内页、
字符课堂树、页内逐块覆盖寄存器和不可压缩的理解/感受/继续/翻页门。manifest 只声明待扫描
输入，不能自报扫描完成。Exercise 只给题面；`confirm_close` 直接给出最新 pending ID、
正文 SHA、完整学生版复盘 Markdown、presentation SHA、建议结论、系统绑定 tuple 与简短
回复词；首次启动给出 `first_run.md` 路由。状态冲突返回 `status=blocked` 与明确 blocker，
不猜测 route。

critical 还必须携带 `classroom_creativity_policy`：创造性互动默认允许；硬边界仅为不提前
泄露未请求的习题答案/解法结构与不跳过必学教材块；额外习题仅在学生请求或明确 opt-in 后
生成。理解确认题不归入额外习题。

每个 Lesson action payload 还必须有 `lesson_opening_contract`：开场内容概览、ASCII 字符
知识树、来源或 `creative_composition_required` 状态，以及“询问路线感受并取得进入第一块的
继续授权”门。开场概览不计作教材页覆盖或掌握证据。

`snapshot_id` 是 `CTX-<COURSE_ID>-<SHA256>`；末段 SHA 对 course_id 与 critical 实际观察的
memory、learning path、progress、activity ledger、当前 activity、profile 和 teacher overlay
原始字节 SHA 做 canonical 绑定。相同 snapshot 不得重复启动 context 工作。

### L0-background：完整会话恢复包

新对话恢复已有课程时，运行：

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --format markdown
```

Prefetcher 应将 critical 的 snapshot 绑定到后台核对：

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --format markdown --expect-snapshot <SNAPSHOT_ID>
```

匹配才可回交 `background-settled`；不匹配时丢弃旧候选，重新生成 critical 与后台包一次。
第二次仍不一致则返回 blocker，不得 settled。

省略 `--course` 时，只允许从 memory 的“当前课程”指针解析，不扫描目录猜测。显式指定
非当前课程时，该课程必须仍属于 memory 指向的 active Group；包须标记
`explicit_same_active_group`，且不得把上一门课摘要当成目标课程恢复指针。组外课程直接
失败，先完成课程组切换。L0 包含：

- memory 的上次课摘要与当前指针；
- profile 的初始化状态、`exercise_hint_gate`、学习目标、辅导偏好、执行参数和个体总纲；
- learning path 中当前课程与 active Group 的精确表格行；
- active Group 的当前预算、成员与周期安排；
- `progress.md` frontmatter 与「当前进度」；
- 显式 LearningActivity 的恢复胶囊；
- open / 需要回看的疑问、活跃错题调度摘要；
- 当前课程相关感想、活跃思维模式和生效教师约束；
- 当前 Exercise 的唯一题面，或当前 Lesson 的完整 Scope 核验文本窗口；同时以
  `source_consumption.scope_text_status=complete_in_current_packet` 明示本轮文本消费，视觉
  状态保持 `external_scan_required`，直到 Prefetcher 实际逐页打开页图。

完整 Scope 文本进入 L0 只证明“本轮可读”，不证明“课堂已逐块讲完”。Main 必须维护
session-local 页覆盖寄存器；每个 active lesson block 只能是 `covered`、
`explicitly_deferred` 或 `outside_active_lesson_boundary`。在所有块都有状态且学生单独授权翻页
之前，不得消费下一页正文。正确作答不会自动生成继续授权。

L0 不加载完整教学历史、全部已关闭问答、全部 Attempt/Review、无关课程、无关交接或
完整 journal。

### L1：当前一步

准备实际推进一个步骤时，只展开 L0 尚未包含、且该步骤直接需要的证据。可运行：

```powershell
python -B main/70_tools/t2ag_context.py --course <COURSE_ID> --include-l1
```

- Exercise：当前题面与人工校对题源已在 L0；若当前题已有提交，再追加与该题直接相关的
  Attempt/Review；
- textbook Lesson：优先 current `LessonPreparationSnapshot` + LessonMap +
  `source_assets`（连续 Scope 5–8，短书固定全书）；legacy `working_pages` 路径已在 0.2.2 批 S3 退役，无 preparation Snapshot 时不得返回 `ready`。
- 当前疑问或复测：对应 question / mistake 条目及其回链；
- 学生明确提出的想法：对应 thoughts 与已提炼反思。

首次呈现习题仍只给题面。上下文包可以让教师读取必要状态，但不得把内部提示、答案、
历史他人解法或思维树提前展示给学生。

当前活动为 Exercise 且 `exercise_hint_gate: enabled` 时，每次教学回复先以当前题目运行
`t2ag_hint_gate.py`。`concept_answer` 只回答学生明确问到的概念，不将定义、例子或结论
继续应用回题目；帮助等级只由学生显式授权提升。

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

同一对话内，Main 对同一 `snapshot_id` 只接收一次 critical，Prefetcher 对它只启动一次后台
核对。以下任一情况使其失效：

1. `progress.md`、当前活动、profile、active Group 或教师映射被写入；
2. 外部同步、另一 agent 或用户编辑了包内来源；
3. 对话压缩后无法确认仍保留当前停点与关键约束；
4. current activity 或当前题目发生切换；
5. 工具报告来源在生成期间变化。
6. 后台包的 `snapshot_id` 与已释放的 critical 不同。
7. textbook 的 session-local Scope 扫描缺页、snapshot/PDF SHA 不同，或
   `pdf_page_index` 与 `printed_page_label` 被混用。

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

1. 当前指针、唯一活动、下一动作、学生约束、教师红线和当前教材/题面均可恢复；Lesson
   pending prompt 与 progress 精确停点逐字一致，当前页路径与页索引一致；
2. packet 不含完整 progress 历史、全部 closed question 或无关课程正文；
3. packet 生成过程只读，且不会创建 `.venv`、缓存状态文件或第二真相源；
4. 两个 `serialized_*` 数值必须分别等于实际渲染结果长度；
5. Main、Skeleton、Lite 的 core playbook 与工具保持同源；
6. critical 不超过 4,096 字符，且不调用完整 L0 构建路径；
7. `confirm_close` 一次返回完整待展示内容，Exercise 不泄露提示；
8. 任何压缩收益不得以降低确认、证据或安全标准换取。
9. textbook 的 Snapshot/receipt/哈希不得表述成“本轮已扫描”；只有同 snapshot 的完整 L0
   文本消费和逐页视觉打开记录都存在，才可释放第一条教学动作。

默认软预算为 16,000 个实际序列化 Markdown 字符，分别检查 L0 与 L0+首个 L1。超过时
只输出 `REVIEW`，由维护者检查是否存在新的重复存量；不得静默丢字段。

## 六、降级

- profile 未初始化、仍含必填占位符或 memory 日期为 `—`：输出
  `first_run_required`，转 `first_run.md`，不生成伪课程包。
- critical 的当前课程不存在、不是 `ongoing`、不属于 active Group、活动路由失败、ledger /
  progress 冲突或来源在读取期间变化：返回 `status=blocked`；后台命令仍非零，先修权威链。
- 工具不可执行：按 `lesson_recover.md` 的同名章节手工做分层摘录；不得退回无差别
  全仓读取。

## 七、关联文件

- `main/t2ag.md`：启动入口与日常接管。
- `main/50_playbook/lesson_recover.md`：课程恢复及 L1/L2 触发。
- `main/50_playbook/session_close.md`：写回与回读。
- `main/50_playbook/startup_orchestration.md`：三 Agent 启动、join 与降级。
- `main/70_tools/t2ag_context.py`：只读上下文包生成器。
- `main/70_tools/t2ag_activity.py`：唯一活动路由器。

## Main 消费纪律与课程选择（canonical，自宪法 §3.2 下沉 2026-08-08/EV-0020）

标准两段命令（critical 先行，markdown 兜底核对）：

```powershell
python -B main/70_tools/t2ag_context.py --course <ID> --format critical
python -B main/70_tools/t2ag_context.py --course <ID> --format markdown
```

- 省略课程 ID 时只可使用 memory 的当前课程指针，不得扫描目录猜测；显式切换只允许
  active Group 内课程，组外课程先切组。
- Main 收到 critical 后 context 调用次数为 0：不得运行 Markdown L0、搜索 ledger、解码
  pending、拼装结课确认或重读完整 L0。仅 critical 10 秒超时且分支已终止时，Main 可降级
  运行一次 `--format critical`。
- 同一 snapshot 不重复派发；后台 snapshot 不同则由 Prefetcher 丢弃候选并重跑一次；
  同一对话内未变化的 L0 不重复读取。
- critical 只恢复 route、停点、next action、必要来源 SHA 与首轮 action payload；包是逐字
  摘录的只读投影，不是真相源，不得落盘后编辑；权威 pending prompt 必须逐字来自
  `progress.md` 当前切片并标明来源，补充内容不得替换权威停点或绕过提示闸门。
- 推进当前一步需要追加直接证据时用 `--include-l1`；只有状态冲突、复测/疑问回收、
  排期/复盘、结课、历史追问或项目审计等明确触发器才进入 L2 全文读取。

