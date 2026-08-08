# 进度节点与自动存档流程（progress_tracking）

**保护级别**：core-playbook

> 本流程定义课程生命周期、容量组合、细粒度恢复点与粗粒度完成节点。
> `progress.md` 只拥有 Course 生命周期、唯一前台与精确停点；`activity_ledger.md` 拥有
> Lesson/Exercise 生命周期。课程组只决定容量，不覆盖任何一类真相源。

## 一、两组彼此独立的状态

### 1.0 当前学习活动

`progress.md` 必须把课程生命周期与当前学习活动分开：

```yaml
current_activity: lesson       # lesson / exercise
current_activity_id: lesson01  # lessonNN / exerciseNN
resume_path: main/40_course/COURSE_ID/lessons/lesson01/lesson01.md
activity_position: 精确停点
next_action_kind: resume
next_activity_type: lesson
next_activity_id: lesson01
```

- 切换到 Exercise 时，`resume_path` 改指 `exercises/exerciseNN/exercise.md`。
- 显式前台与 next_action 字段不得由 memory、目录扫描或退役的 `current_lesson` 补值。
  历史 Lesson 上下文只能从 ledger 事件与 ContentGroup 关系按需解析，不能触发默认
  Lesson/working-pages 恢复。
- Lesson 与 Exercise 是同级活动；切换只改变当前恢复入口，不改变 ContentGroup 关系或
  擅自关闭另一活动的未决问题。
- `activity_position` 是两类活动共用的精确停点字段；不得继续用
  `lesson_position` 保存 Exercise 或新 Lesson 状态。
- planned 课程只写 `progress_nodes_status: lazy_on_activation`，
  不携带 `current_activity / current_activity_id / resume_path / activity_position`。
  激活时先创建真实载体，再原子写入完整活动字段。

### 1.1 课程生命周期

每门课程在 `progress.md` 文件头使用：

```yaml
lifecycle_status: planned  # planned / ongoing / completed / dropped
```

- `planned`：已有方案或档案，但尚未进入实际学习。
- `ongoing`：课程已经开始且尚未结束；即使不在当前容量组合中，也可保持 ongoing。
- `completed`：课程完成标准已经闭合。
- `dropped`：用户明确终止，保留原因和历史。

### 1.2 当前容量组合

当前 active 的 `Gxx.md` 是用户确认的重点执行组合：组内课程获得时间预算、最低频率和里程碑承诺。
组外 `ongoing` 课程仍可在用户明确提出时临时推进，但不得自动挤占组内预算，也不得因一次临时学习自动换组。
系统可依据实际时长、启动失败、学习能力、截止期、依赖和项目限制提出调组建议；成员变更仍须用户确认。

## 二、两层进度节点

### 2.1 checkpoint：到达节点

checkpoint 是细粒度恢复点，用来回答“具体讲到哪一句、哪个证明步骤或哪个项目动作”。

- 教材课以当前 5–8 页工作窗口为范围；一页可有多个 checkpoint。Scope 规格 owner 为
  `50_playbook/source_page_assets.md` §2 LessonScope，本文件不重复定义。
- 项目/实践课按当前时间表、里程碑或项目顺序表的细步骤生成。
- checkpoint 使用来源定位 ID，例如 `MATH1607H-B001-P026-N02`。
- checkpoint 挂在 LessonMap 块下：一个块可有多个 checkpoint（学生可能在同一块内多次停顿）。
  块引用使用稳定 ID `page_key#block_id`；同一 SourcePageAsset 的同一教材块跨 Scope 版本保持同 ID。
- 到达 checkpoint 时静默自动保存，不要求学生说“保存进度”。
- 状态至少区分 `queued / arrived / pending / confirmed / archived`。
- checkpoint 只证明到达位置与确认状态，不等于完成一个教材小节或项目节点。
- checkpoint 表格是权威真相源；frontmatter 的 `current_checkpoint` / `checkpoint_state`
  由 `t2ag_state_refresh.py --write` 从表格生成（GENERATED 投影），手写无效。

### 2.2 completion node：完成节点

completion node 是粗粒度、永久稳定的正式进度单元，通常跨若干 checkpoint 或若干页。

- 教材课通常对应教材目录中的一个小节、完整定理链或其他自然内容边界。
- 项目课对应项目计划中的稳定步骤或里程碑。
- 实践课对应时间表中的行动/复盘单元。
- ID 一经生成不得重排或复用；标题、页码或说明可修订。
- 状态使用 `queued / in_progress / completed / superseded`。
- 临时补充内容挂在父 completion node 下，不擅自改变主线顺序。

## 三、生成与滚动窗口

1. completion node 先从已核验教材目录、项目顺序表或实践时间表生成；不凭模型记忆猜结构。
2. 教材课只为当前 Scope（5–8 页）生成 checkpoint。Scope 换版时：
   (1) 当前 LessonMap 块成员关系派生路由，「离开块」= 新旧 Map 块 ID 集合差判定；
   (2) `confirmed` checkpoint 保持 `confirmed`，Scope 换版不改写既有确认事实；
   (3) 即将离开 Scope 的块若仍有 `queued / arrived / pending` checkpoint → fail-closed，
       必须先确认闭合或学生明确 defer/retire；
   (4) `archived` 只表示 checkpoint 本身被明确判定为重复、失效、被替代或不再恢复，
       退役原因必须在对应 Lesson/活动记录中留痕；`archived` 不再是 Scope rollover 的自动清退机制。

### 重分块与 block migration

教材的块划分不是静态的。同一个 SourcePageAsset 在后续 Scope 版本中可能被重新分块
（如定义与例子拆成不同块、教材修订导致块边界移动）。块 ID 变更必须通过 **block migration 表**
显式记录，不得静默覆盖旧 ID 或凭空创建新 ID 而不建立对应关系。

block migration 表至少记录：

| 字段 | 说明 |
|---|---|
| page_key | 不变的页级 ID |
| old_block_id | 旧版块的短 ID（如 B02） |
| new_block_id | 新版块的短 ID（如 B03） |
| kind | `split / merge / renumber / boundary_shift / retired / new` |
| successor_of | 旧块是否被完全包含或替代；一对多或多对一时必须解释 |
| decision | 学生或教师确认的裁决（如「B03 替代 B02，旧 B03→B04」） |

规则：
- 同一次 Scope 换版中，同一 `page_key` 下**存在一对多 successor 映射且无精确 successor
  判定时，doctor 必须 fail-closed**（CKP-SCOPE-003），要求教师在迁移表中明确 successor。
- `kind: retired` 的块：旧 checkpoint 可标 `archived`，并在对应 Lesson 记录退役原因。
- `kind: new` 的块：未在任何已确认 completion node 出现过的新增内容，不继承任何旧 checkpoint。

3. 非活跃课程只保留最小生命周期字段，首次激活或真正恢复时惰性生成节点。
4. `node_id` 绑定来源身份；文件改名通过 artifact registry 解析，不重造节点 ID。

## 三·五、学习日归属（04:00 边界）

> **本节是 memory 决策段第 14 条（2026-07-31 暂定）的 canonical 落点。**
> 该规则自 2026-07-31 起在治理行为，但直至 2026-08-07 全仓
> `grep -rln "04:00\|凌晨" main/50_playbook/ main/00_core/ main/t2ag.md` **零命中**
> ——它只活在 memory 里、无任何规范性载体，因而被墓碑挡住无法下沉。
> 迁移登记见本文件 §六末 `rule_migration`。

**规则**：**本地凌晨 04:00 之前产生的任务进度，归属前一个学习日。**

例：实际保存于 2026-08-01 01 时的进度，归入 2026-07-31，并作为该学习日的最后一个任务关闭。

**作用域切割（这半句与规则本体同等重要，不得省略）**：

| 对象 | 用哪个日期 |
|---|---|
| **学习进度**（checkpoint、completion node、progress 记录、学习日收尾） | **04:00 学习日** |
| **系统日志、月志、发行取证**（changelog、journal、release evidence、doctor 月度门） | **自然日期** |

把 04:00 边界外推到取证链上是**错误**的——两套日期概念共用一个名字，正是 `P-0045`
冲突的来源。

**跨月归属：双记 + 显式标注（`P-0045` 裁决，学生 2026-08-07）**

当一条记录的**学习日与自然日期不同**（即产生于本地 00:00–04:00）时，
**必须同时写两个日期**，不得只写其一：

```
学习日 2026-07-31（自然 2026-08-01 01:12）
```

两者相同时只写一个——**不为不跨界的记录制造噪声**，双记只在实际分叉时出现。

**任何做周度/月度聚合的消费方，必须在自身文档里声明它用哪个日历。**
未声明即为契约缺失，不得由读者猜测。

> **为什么选双记而非「二选一」**：学生的理由是**长期降低各模型的使用成本**。
> 只记一个日期，每个新接手的模型遇到跨界记录都要重新推导一遍「这里该用哪个日历」；
> 双记把那次推导一次性消掉，写在记录里。这不是防错，是**防重复推导**——
> 与本文件其它规则「让真相可直接读出而非反复重算」的取向一致。
>
> 代价是跨界记录多一个括号。该情形约每月至多一次（学习会话恰好收尾于某日 00:00–04:00），
> 成本可忽略。

**这不改变作用域切割**：上表仍然有效——学习进度的**归属**按 04:00 学习日，
系统日志/月志/取证的**归属**按自然日期。双记解决的是「记录上写什么」，
不是「归属算哪个」。两者不得混淆。

## 四、保存与正式提升入口

### 4.1 自动 checkpoint

进入 checkpoint 时立即更新 `progress.md` 的当前 checkpoint、精确停点和确认状态，并刷新机器生成缓存。
这只保存位置，不得把父 completion node 写成 completed。

### 4.2 自动完成节点

completion node 的既有完成证据满足后，自动把该节点标为 completed，并把下一节点标为 in_progress。

- 教材课：内容讲完，且没有悬空确认或未回答问题；不额外强制生成习题。额外习题默认
  不自动生成，只在学生请求或明确 opt-in 后创建；课堂理解确认不算额外习题。
- 教材原有例题/习题：继续执行习题闭环，但习题闭环不是每个完成节点的附加考试。
- 项目课：以计划中已有的代码运行、文件产出或功能结果关闭。
- 实践课：以计划中已有的行动记录或复盘结果关闭。
- 错题复测、章节卷与陈年卷保持独立，不与每个 completion node 捆绑。

### 4.3 学生手动“保存进度”

学生说“保存进度”时，无论是否处于节点边界，都立即强制保存当前 checkpoint、pending 状态和课堂要点。
手动保存不自动完成父节点，也不替代结课仪式。

### 4.4 结课与恢复确认

正常结课按 `session_close.md` 完成正式写回。异常中断后恢复时，若当前 Lesson/Exercise、云端事件或学生陈述比真相源更新，
先暂停新内容并核对；经学生确认后更新 `progress.md`，再统一刷新缓存。

## 五、云端检查点

- 手机端 checkpoint 在云端内部静默记录。
- 每完成一个 completion node，云端自动生成紧凑的 `T2AG_PROGRESS_RECEIPT`。
- 学生说“保存进度”时立即生成回执；正常结课仍生成完整 `T2AG_SESSION_CLOSE`。
- 本地按事件 ID 去重；已被后续结课块包含的回执不重复计入。
- 云端不能直接把本地 `progress.md` 写成已同步；回执在本地核对前保持 pending。

## 六、机器生成缓存

`70_tools/t2ag_state_refresh.py` 只拥有以下本地 GENERATED 区块：

- memory 的 `ACTIVE_PROGRESS` 与 `STATE_POINTERS`；
- `learning_path.md` 的 `COURSE_INDEX` 与 `GROUP_INDEX`；
- active group plan 的 `GROUP_VIEW`。

Lesson/Exercise 的局部停点由 `session_close.md` 写成活动证据，不是 GENERATED 缓存，
也不能覆盖 progress。移动端入口由 Cloud 同步协议单独拥有；bridge 为 `paused` 时不写。
任何没有明确生成器负责的 GENERATED anchor 都属于契约错误。

执行顺序固定为：

```text
progress.md / active group 文件
  → t2ag_state_refresh.py --write
  → t2ag_state_refresh.py --check
  → t2ag_doctor.py --profile runtime
```

工具失败时不得用手抄结果冒充生成成功。

---

## rule_migration

按 `main/t2ag.md` §6.3.1 登记本文件承接的规则迁移。

| rule_id | 旧位置/原文锚点 | 动作 | 新 owner/等价门 | 消费方 | 验证 |
|---|---|---|---|---|---|
| 04:00 学习日边界 | `grep -n "04:00 学习日边界" main/00_core/t2ag_memory.md` → 决策段第 14 条（2026-07-31 暂定），**无 playbook 载体** | **sink** | 本文件 §三·五 | 结课流程（`session_close.md` §四指针）、进度写入方、月度取证方（按作用域切割走自然日期） | `grep -rln "04:00" main/50_playbook/` 命中本文件；memory #14 的 `⚠` 墓碑可摘除并下沉 |

**下沉闭包检查（§6.3.3 四项）**：新 canonical owner = 本文件 §三·五 ✅；
入口指针 = `session_close.md` §四 ✅；消费方 = 上表第五列 ✅；
验证 = 上表第六列的 grep ✅。

**`P-0045` 已随本次迁移裁定并落地**（学生 2026-08-07，方案 C：双记 + 显式标注）。
规则见 §三·五末段。该条的 problemlog 条目可据此转为 resolved——
本文件不代改 problemlog 状态，由维护方按 `problemlog_maintenance.md` 执行。
