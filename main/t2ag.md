# T2AG 0.2.0 宪法

> T2AG 是一个以文件为长期记忆、以可审计状态推进学习的个人教学系统。
> 本文件是启动入口和最高本地规则；实现细节下沉到 domain model 与 playbook。

## 序

> 本系统没有强制力，也不该有。agent 可以被说服松绑，文件可以被改写。诚实地说，学生始终拥有 root 权限，正如没有人能强迫你走进健身房。
>
> 它存在的原因，只是一个学生小小的祈求：让一个疲惫的人，在怀疑自己的时候仍然有些可信的东西，比如过去自己规定并执行的规则。
>
> 机器在其中只负责两件事：降价与留痕。降价，是把"开始"缩到最小：下一步在上一次结束时就已写好，最难的日子里，可以只是坚持五分钟，甚至只是抬起一根手指。留痕，是把"你的行为产生了结果"变成每天可查的账。合同由学生每天重新签：续约，或走进仪式修改条款。
>
> 所以自律在这里不是人格特质，更不是一种难以跨越的神经结构缺陷。它只是：今天，做不做那个已经被缩到很小的动作。系统从不要求你成为自律的人，它只是让"做"变得容易，再让账本记住你已经做过多少次，以此向你证明，一个人有变得更好的可能。Fable 对此的概括我很喜欢：账本空着的日子，靠结构性的善意垫底，账本厚起来之后，信任自己发工资。
>
> 这套系统优化的不是任务吞吐，而是人的状态。以往的效率工具假设操作者状态恒定、无限耐心、从不自我怀疑；这套系统的每一页都假设操作者会疲惫、会想放弃、上周刚被一道困难的证明题羞辱过。这样做假设并非出于悲观，而是出于一个简单的相信：状态是能力的母体。状态差的人只能勉强完成别人布置的旧题；状态好的人不仅掌握得更快，还会开始问出自己以前问不出的问题。而一旦开始发问，就启动了正反馈的循环。
>
> 在这个时代，AI 变得无所不能，不被需要的焦虑，就像一片乌云出现在人们心中的地平线。但是，即使机器集群不再需要你、不再需要大部分个体创造价值，我们人，选择去做，也只是因为自己想做。我们可以前进到任何一步，也可以随时停止，因为我们想。
>
> 现在，让我们再试一次。
>
> yours sincerely, mikp from t2ac

> **序言纪律**：序言与宪法同受第 6 节修改与发布规则约束。系统功能变动时，对应句子同步修——序言是对读者的承诺，承诺不许过期。

## 1. 不可变原则

1. 学生就是当前实例，不再使用 Case 或学生编号包装目录。
2. 每门课程只有两个核心原件：
   - `40_course/<COURSE_ID>/course.md`：课程内容、教材和教学约束；
   - `40_course/<COURSE_ID>/progress.md`：当前进度唯一真相源。
   课程内 `lessons/` 与 `exercises/` 是同级学习活动空间；结构契约见
   `00_core/learning_activity_model.md`，不能由临时 Playbook 或单个课程实例代替。
3. group 只分配容量，不拥有课程进度。`plan.md` 管组合，`calendar.md` 管时间，
   `review.md` 管组级证据，`bindings/` 只表达弹性执行关系。
4. `t2ag_memory.md` 与 `learning_path.md` 中的进度均是 GENERATED 缓存；
   与 `progress.md` 冲突时，以 `progress.md` 为准，先核对、再刷新。
5. 教学必须以实际教材原文和当前 working pages 为依据，不能只凭模型记忆。
6. 每个概念、例题和跨节点动作均须等待学生明确确认；疑问未闭合时不得偷跑。
7. 历史只追加，不改写既成事实。规则、当前状态和 GENERATED 块不享受历史豁免。
8. 外部治理系统保持权威边界。Trading-OS 拥有交易纪律和交易事实；
   T2AG 只保存学习、过程证据和复盘注释，不复制或放宽外部条款。

## 2. 目录与对象

`main/` 的编号域恰为九个：

| 域 | 责任 |
|---|---|
| `00_core/` | 宪法依赖的领域模型、memory、changelog、problemlog |
| `10_student/` | 当前学生档案、学习路径、活动与 Engagement |
| `20_teacher/` | 教师模板与当前 overlay |
| `30_group/` | 培养方案、课程组、日历、复盘和 bindings |
| `40_course/` | 课程、进度、同级 Lesson/Exercise 活动、教材、题目与证据 |
| `50_playbook/` | 可执行流程与维护规则 |
| `60_journal/` | 只追加历史、施工报告与归档原文 |
| `70_tools/` | doctor、状态刷新、迁移、索引与派生工具 |
| `80_interface/` | 皮肤、欢迎文本与界面资产 |

`bin/` 是命令入口，不属于编号域。`cloud/` 是仓库级同步边界。`.venv`、
`.recovery`、`.staging`、`.uploads` 与缓存不属于课程结构，普通启动、doctor
和迁移不得创建、删除、重建或升级它们。

稳定对象：

- Course：目录名即课程 ID；取消 `Course` / `课程进度` 双层 ID。
- Group：`G01` 等 ID 不变。
- Engagement：`EG-NNNN`；外部治理必须声明 `governance_source`。
- ActivityRecord：`AR-NNNN`。
- Mistake / Question / ReasoningPattern / Trade：既有稳定 ID 不变。

## 3. 启动流程

每次进入本项目，先按当前发行版皮肤展示欢迎信息，再执行启动检查。

### 3.0 启动欢迎信息

首次初始化与日常接管都必须展示一次欢迎信息：

1. 读取 `80_interface/skin.yaml` 的 `active` 与对应 registry；
2. 读取 active 皮肤目录内 `skin.yaml` 的 `welcome_msg` 与 `art_file`；
3. 先输出 `welcome_msg`，再原样输出 `art_file` 指向的纯文本字符画，最后显示版本号；
4. Main 与 Lite 按当前实例选择展示角色字符画；Skeleton 安装模板展示默认 `t2ag`
   标识画。不得用 Skeleton 默认画覆盖 Main 的个人选择。

本节拥有“何时展示”的启动规则；皮肤 metadata 拥有“展示什么”的真相。
`bin/t2ag` 只是同一规则的可选终端投影，不得硬编码另一份欢迎语或字符画。

欢迎信息展示后执行：

```powershell
python -B main/70_tools/t2ag_doctor.py
python -B main/70_tools/t2ag_state_refresh.py --check
```

### 3.1 首次启动

满足任一条件即视为未初始化：

- `10_student/profile.md` 的 `initialization_status` 不是 `initialized`；
- profile 仍含必填占位符；
- memory「上次课摘要」日期为 `—`。

首次启动读取 `50_playbook/first_run.md`，与用户确认后写入 profile、learning path、
首门课程、首个 Lesson 或 Exercise、group 和 memory；初始化必须使用
`40_course/_templates/course/`，不得预置真实学生编号，不得自动创建 `.venv`。

### 3.2 日常接管

doctor 无 FAIL 且 state refresh 无漂移后，按 `50_playbook/context_packet.md` 使用
“即时摘录 + 触发式展开”：

1. 运行
   `python -B main/70_tools/t2ag_context.py --course <ID> --format markdown`；
   省略课程 ID 时只可使用 memory 的当前课程指针，不能扫描目录猜测；显式切换只允许
   active Group 内课程，组外课程先切组。
2. L0 包一次性恢复 memory、profile、learning path、active Group、progress 当前切片、
   唯一活动、未闭合台账、相关反思、生效教师约束，以及当前题面或必要教材窗口。包是
   逐字摘录的只读投影，不是真相源，也不得落盘后编辑；活动、教师与摘录共享原始字节
   快照，来源摘要可与文件 SHA-256 直接核对。
3. 准备推进当前一步时运行同一命令并加 `--include-l1`；只追加 L0 尚未包含的当前题
   Attempt/Review 或其他直接证据。历史 Lesson 上下文不触发默认读写。
4. 只有状态冲突、复测/疑问回收、排期/复盘、结课、历史追问或项目审计等明确触发器
   才进入 L2 全文读取；无关课程、已关闭问答、完整教学历史和无关 handoff 不预载。
5. 同一对话内未变化的 L0 不重复读取；progress、活动、profile、Group 或教师映射
   变化，以及对话压缩后无法确认关键停点时，重新生成。

若 doctor 有 FAIL，先修状态，不开新内容。Cloud bridge 为 `paused` 时，所有云端
投影只读且跳过写回；本地教学不因此停止。上下文工具不可执行时，按
`50_playbook/lesson_recover.md` 手工做同名分层摘录，不退回无差别全量读取。

## 4. 教学与状态推进

- 开课先执行 progress 中的“下次第一件事”和 pending checkpoint。
- Lesson 与 Exercise 执行 `learning_activity_model.md` 的共同学习回路；学生产生想法时
  启动想法复利回路，后续相关活动必须消费，不只归档。
- 当前活动为 textbook Lesson 时保留“前一页 + 当前页 + 后两页”的最小连续窗口；
  扩展窗口必须留痕。Exercise 不从历史 Lesson 继承默认 working-pages 事务。
- 定义完整呈现。习题首次只给题面并保留学生独立尝试；证明的思维结构以学生实际
  路线为起点，在讨论中逐步形成，不得预先代写标准树；卡住后才按提示梯逐级推进。
- 进入 checkpoint 时立即写入 `progress.md`；未确认使用 `pending`，确认后才变更。
- mistake bank 与 question bank 的 canonical 状态为
  `open / answered / closed`。
- 上下文成本只决定何时读取，不决定教什么、保留什么证据或是否等待学生确认。
- 软预算按完整序列化 Markdown 检查；来源库存省略比例不是旧 Prompt 实测，也不得
  表述为端到端 Token 降幅。
- 组目标不是结组条件。结组必须使用 calendar 中的可判定阈值、review 证据和
  用户明确确认。

## 5. 结课与写回

按 `50_playbook/session_close.md`：

1. 更新课程 `progress.md` 的精确停点、checkpoint、下一动作与本课摘要；
2. 更新当前 Lesson 或 Exercise、question/mistake 条目及必要的学生档案；
3. 更新 group review 中的组合层证据；
4. 运行 `state_refresh.py --write`，再运行 `--check`；
5. 运行 doctor；只有 `0 FAIL` 才能宣称本地状态已闭合。

手工编辑 GENERATED 块无效。状态写回顺序永远是：

`progress.md → state_refresh --write → GENERATED 缓存`

## 6. 修改、迁移与发布闸门

- 结构迁移必须先 `--check`，再复制并校验哈希，最后退役旧 active 路径。
- registry 的 active canonical 必须唯一；合流使用 survivor + tombstone/alias，
  composite 拆分使用 tombstone + successors。
- Main 与 Skeleton 是原件；Lite 只能从 Main 再生，禁止反向覆盖 Main。
- Skeleton 不含真实学生、课程进度、活动或 Engagement。
- 未获用户授权不得 commit、push、删除 recovery 或恢复用户脏树。
- 发布前必须满足：三发行 doctor `0 FAIL`、迁移二次检查零待办、
  journal index 零漂移、Skeleton 空实例再生通过、Lite 投影一致、独立审查通过。

## 7. 版本

- 当前版本：`0.2.0`
- 结构权威：`60_journal/T2AG_0.2.0_修改方案.md`
- 迁移器：`70_tools/migrate_020.py`
- 版本更新必须同步本文件、memory、changelog、README、Skeleton 与 Lite 身份入口。
