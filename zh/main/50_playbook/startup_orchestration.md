# 日常启动多 Agent 编排

**保护级别**：core-playbook

> 本流程优化健康实例从用户提出继续学习到出现第一条可执行学习内容的等待时间。
> 它把“可先进行只读教学”与“恢复检查已经收敛”分开，但不降低来源一致性、学生确认、
> Activity 生命周期或写回标准。

## 零、启动欢迎信息（canonical，自宪法 §3.0 下沉 2026-08-08/EV-0020）

首次初始化与日常接管都必须展示一次欢迎信息，且与恢复分支并行、不互相等待：

1. 读取 `80_interface/skin.yaml` 的 `active` 与对应 registry；
2. 读取 active 皮肤目录内 `skin.yaml` 的 `welcome_msg` 与 `art_file`；
3. 先输出 `welcome_msg`，再原样输出 `art_file` 指向的纯文本字符画，最后显示版本号；
4. Main 与 Lite 按当前实例选择展示角色字符画；Skeleton 安装模板展示默认 `t2ag`
   标识画。不得用 Skeleton 默认画覆盖 Main 的个人选择。

本节拥有「何时展示」的启动规则；皮肤 metadata 拥有「展示什么」的真相。`bin/t2ag`
只是同一规则的可选终端投影，不得硬编码另一份欢迎语或字符画。

## 一、目标与默认拓扑

- 健康路径目标：critical route ≤10 秒；非 textbook 第一条可执行学习内容 ≤15 秒；
  textbook 必须先完成同 snapshot 的 Scope 文本与视觉消费，和完整
  `recovery-settled` 一并以 45–60 秒为目标。
- Agent 池最多保留 6 个身份，同时最多运行 3 个（均包含 Main）；默认活跃编队仍是一个
  Main Conductor 与两个辅助 Agent。完成态释放并发槽；池未满可新建，池满优先复用。
- 辅助 Agent 能力不可用时允许单 Agent 降级；降级不改变任何安全或授权边界。
- 多 Agent 是日常启动偏好，不是强制并发数，也不授权扩大读取、测试或写入范围。
- Startup Formation 是日常接管的一主两辅；Task Assist Budget 是改系统/验证时默认一个
  辅助、三条测试、十分钟。二者不得混成同一预算。

两个状态不得混称：

- `learning-ready`：当前 route、停点、必要内容和来源身份可信，没有已知教学阻断；允许
  Main Conductor 进行只读讲解、提问、反馈或展示待确认正文。
- `recovery-settled`：runtime Doctor、state check 与完整来源核对均已收敛；只有此后才允许
  写进度、确认 checkpoint、切换前台、执行 terminal/RT3 或宣称本地状态全绿。

默认角色：

| 角色 | 职责 | 启动阶段权限 |
|---|---|---|
| Main Conductor | 展示欢迎信息、汇合两个辅助分支、与学生交互 | 收到 critical 后 context 调用次数必须为 0 |
| Runtime Sentinel | 验证本地教学运行状态 | 只读运行 runtime Doctor 与 state refresh `--check` |
| Context Prefetcher | 生成并消费当前课程上下文，准备一份暂不发送的首轮候选 | 只读运行 context；不得写回、不得自行进入 L2 |

<!-- rule: CTX-PACKET-005 -->
## 二、先建依赖树，再分配 Agent

Main Conductor 在派发前先画最小依赖树并估算关键路径；固定启动可直接复用下图，不能先
派 Agent 再临时寻找职责：

```text
用户继续学习
├─ Main：welcome + 读取协作偏好（约 0.2–2 秒）
├─ Runtime Sentinel（并行，程序约 1 秒；含调度约 3–15 秒）
│  ├─ runtime Doctor
│  └─ state --check
└─ Context Prefetcher（精简 Agent 上下文）
   ├─ --format critical → 立即 handoff（目标 ≤10 秒）
   └─ 完整 Markdown L0
      └─ textbook：按 scope_scan manifest 打开全部页图 → background-settled
        ↓
Main 汇合 L0-critical → learning-ready（健康目标 ≤15 秒）
        ↓
Runtime + L0-background 收敛 → recovery-settled
```

只有无依赖且只读的支路可以并行。用户确认、所有写回、checkpoint、terminal/RT3 与最终
裁决始终留在 Main Conductor 的串行路径。若任务不是固定启动，Main 也必须先列出依赖、
预计耗时与写集合，再分配辅助 Agent；不得让两个 Agent 同时拥有同一真相源。

## 三、并行启动

Main Conductor 按 `main/t2ag.md` 展示当前皮肤欢迎信息，并同时派发两个只读分支：

两个辅助分支都必须使用干净或最小上下文。宿主支持上下文分叉策略时，优先使用不继承
历史的模式（例如 `fork_turns=none`）；确需带入最近消息时，只能携带完成本分支所需的
最小轮次，不得继承整段教学或施工对话。任务说明直接写明角色、工作目录、精确命令、
回交字段、读写边界与超时行为，不得要求辅助 Agent 重新阅读本文件、`context_packet.md`
或完整 profile 来自行推导契约。Startup Formation 的两个只读身份也不继承 Task Assist、
迁移、发布或 RT3 授权。

### 分支 A：Runtime Sentinel

并行执行：

```powershell
python -B main/70_tools/t2ag_doctor.py --profile runtime
python -B main/70_tools/t2ag_state_refresh.py --check
```

返回最小结构化结果：

- Doctor 退出码、FAIL 数与 WARN 摘要；
- state refresh 退出码与 drift 数；
- 两项各自耗时；
- 是否满足 `runtime_ready`。

WARN 依现行 Doctor 契约处理；只有 FAIL 或非零退出码阻断。Runtime Sentinel 不修复、
不运行 release profile，也不把候选、Lite、Git 或发布卫生加入日常启动门。

### 分支 B：Context Prefetcher

同一 Agent 轮内按两阶段执行并回交两次：

```powershell
python -B main/70_tools/t2ag_context.py --format critical
python -B main/70_tools/t2ag_context.py --format markdown --expect-snapshot <SNAPSHOT_ID>
```

第一条命令完成后立即发送 critical handoff，不等待完整 L0；随后继续核对并发送
background-settled。textbook Lesson 的 critical 只是 `route-ready`，不得直接释放课堂动作；
Prefetcher 必须按 `action_payload.scope_scan` 与 `source_page_assets.md` §3.1（A1–A6）在本会话
逐页消费整个 Scope 的完整内容本体（宿主可观察投递）。**现行默认可观察路径**（U2 形式清单
冻结前）见 `source_page_assets.md` §3.1.4：L0 消费已核验正文 + 按 manifest/profile 投递整页
画面并回报页索引与 `printed_page_label`。完成按 A6（ADR-0003）由宿主可观察投递证成；
不得以 Snapshot `content_consumed` 或历史 receipt 冒充本轮。任务说明直接嵌入字段契约，不继承完整历史，
不重读本文件或 `context_packet.md`，也不在 route 前消费课程反思、非当前错题和成本账。
handoff 包含：

- `status`、course、current activity、精确停点与 next action；
  textbook scan pending 时 critical JSON 的 `status` 为 `route_ready`（不是 `ready`），
  `blocking_teach=true`；字段不授权发送（见 ADR-0002）。
- 本轮必需的学生约束与教师红线；
- 第一条可执行学习内容候选（scan pending 时由编译器 withhold 正文；身份与 manifest 仍在）；
- Lesson 开场合同：结构门与是否已展示；scan pending 时概览/知识树**正文**由 critical
  withhold。缺失开场来源时，admission 之后才允许创造性编排，不得把 withheld 当成已授权。
- `snapshot_id` 与公开 `source_sha256`；
- `sources_unchanged` 结论。
- textbook 时还须回交 `scope_scan`：snapshot、PDF SHA、全部 `pdf_page_index`、每页消费
  证据（现行路径下含 `opened=true` / 书内页码/标题）、当前页、发现的页码或内容冲突；
  相对 Scope **缺一页即不 complete**（A4 遗漏 FAIL；重复只 WARN）。**注意**：**无投递的**
  文本声明 `opened=true` / complete 不构成证成；证成＝逐页内容本体的宿主可观察投递
  （A6/ADR-0003）。宿主 Scan Orchestrator receipt 保留为未来态，落地后回收签发权。
- textbook 时还须回交 `page_teaching_contract`：当前 PDF/书内页、字符课堂树要求、页内
  覆盖寄存器，以及理解确认、感受反馈、单次继续授权和翻页通知四类门。不得把本轮入口的
  “继续学习”解释成整节课持续授权。

<!-- rule: CTX-PACKET-006 -->
候选在 Main 裁决前必须保持 withheld。宿主落地后，教材教学正文只经 `lesson_emit`；
textbook gated 会话中普通 freeform assistant 出口关闭或仅宿主固定模板（见
`docs/protocol/host-teaching-egress-api.md`）。`confirm_close` 的 latest pending 解码属于 critical
生成器固定职责，一次返回完整学生版复盘 Markdown、presentation SHA、建议、ID、body SHA、
系统绑定 tuple 与可接受的简短结课意图。Main 必须把完整 Markdown 直接发给学生；
不得只展示 ID/SHA 让学生盲签；也不得要求学生抄写 tuple。
Lesson 的 action payload 必须逐字投影并标明 `progress.md` 当前切片的权威精确停点/下一步；
同时允许附加明确标注的复述题、暖场题、类比或探索问题。补充不得替换权威停点、制造虚假
进度或绕过 Exercise 提示闸门。当前页 `source` 必须精确落到当前
`pdf_page_index` 的 `SourcePageAsset`，不得回传 Scope 第一页路径。Main 收到 critical 后严禁运行 Markdown L0、搜索 ledger、解码 pending、拼装结课确认或
重读完整 L0；已收到的同一 `snapshot_id` 不得再次派发。

## 四、两阶段汇合

### 4.1 Learning-ready

满足以下条件即可释放第一条只读学习动作，不必等待 Runtime Sentinel 全部返回：

```text
context_status ∈ { ready, route_ready }   # textbook scan pending 时为 route_ready
AND sources_unchanged == true
AND critical snapshot_id 尚未消费
AND route / source identity 无冲突
AND current activity / next action / 必要内容齐备
AND 已返回报告中没有 blocking_teach == true   # textbook pending 时 blocking_teach 仍为 true → 不可释放
AND （非 textbook OR scope_text_status == complete_in_current_packet）
AND （非 textbook OR scope_visual_scan == complete_for_same_snapshot）  # A1–A5 经宿主可观察投递在本会话证成（ADR-0003），非无投递自报
AND （非 textbook OR page_teaching_contract 完整且已向学生显示当前课堂树）
```

宿主 TeachingAdmissionCapability / `lesson_emit` 为未来态（ADR-0002/ADR-0003）：宿主落地后
该能力回收签发权并恢复为释放条件；落地前按 ADR-0003 以上式为正式判据，不再作为
永不满足的 defense-in-depth 挂账。

`LessonPreparationSnapshot.content_consumed=true`、历史 receipt、manifest/文件哈希一致只证明
准备与身份（A3 链上的部分环节），**不**满足本会话 A1 消费，也不构成 A6 证成（ADR-0003）。
route、progress 精确停点、action payload、当前页路径、Scope manifest 任一冲突时停止
（A5）；禁止 Main 自选一个版本继续。
学习动作释放只允许一个教学块。学生答题、复述或说“是”只闭合理解门；推导/总结后的感受门
和下一块的一次性继续授权仍须分别取得。进入新页前还须通过页内覆盖门并先宣布页码。

此时必须明确内部状态仍可能是 `recovery_pending`；不得宣称 Doctor 全绿或状态已闭合。
Runtime Sentinel 迟到后若报告真正教学阻断，Main 在下一逻辑动作前暂停并说明；WARN、
release/Lite/Git 卫生或施工 dirty 不得追溯抹掉已经发生的真实课堂交流。

### 4.2 Recovery-settled

以下条件全部成立后才进入 `recovery-settled`：

```text
doctor_exit == 0
AND doctor_fail_count == 0
AND state_refresh_exit == 0
AND state_drift_count == 0
AND context sources / route 仍有效
AND background snapshot_id == critical snapshot_id
```

任何写入、checkpoint 结果、切换前台、terminal/RT3 或“启动检查全部完成”宣称都必须等待
该状态。Main Conductor 负责两个阶段的最终裁决；辅助 Agent 不得各自向学生发布答案。

若当前活动处于 `pending_close` 或 next action 为 `confirm_close`，第一条可执行内容必须是
对应精确对象、正文、ID、SHA 与结果的结课确认，不得把“15 秒内开始”解释为跳过结课、
自动写成 `completed` 或提前创建下一 Lesson。

## 五、超时与降级

- critical 单独等待上限为 10 秒；完整后台、textbook Scope 视觉扫描与 Runtime Sentinel 的
  等待上限仍为 45 秒。
- Runtime Sentinel 超时：若 L0-critical 已满足 `learning-ready`，可先进行只读教学并标记
  hygiene pending；不得写回或宣称 settled。若返回 FAIL/drift，再按是否 `blocking_teach`
  暂停下一动作并报告具体阻断项。
- Context Prefetcher 在 10 秒内连 critical 都未返回：Main 必须先确认该分支已终止，才可
  运行一次 `--format critical` 降级；不得运行 Markdown 或生成重复 snapshot。
- 辅助 Agent 不可用：Main Conductor 按 `t2ag.md` 依次完成同一只读检查与上下文恢复。
- 后台 snapshot 不同：丢弃旧候选，由 Prefetcher 重跑 critical + background 一次；仍不同
  则停止推进。Main 不参与重跑。
- `first_run_required`：转 `first_run.md`，不构造伪课程内容。

故障路径可以超过健康目标，也可以只报告阻断；禁止为了满足时间目标猜测 route、写状态或
把 recovery pending 说成 settled。

## 六、并发与写回边界

启动并行区严格只读。以下动作不得与 Doctor、state `--check` 或 context 预取并发：

- 修改 `progress.md`、Activity 主载体、ledger、profile、Group 或教师映射；
- `state_refresh.py --write`；
- Activity close、迁移、同步、提交、发布或其他真实状态处置；
- 任何 RT3、terminal lifecycle 或需要学生严格确认的动作。

进入 recovery-settled 后仍实行 single-writer：只有 Main Conductor 可以协调写回，辅助
Agent 只提供证据或草稿。写回仍按 `session_close.md` 的权威顺序串行执行；多 Agent 不改变
`progress.md → 真实活动/台账 → state_refresh --write → --check → runtime Doctor → 回读`
的闭环。

L2 仍只由 `context_packet.md` 列出的明确触发器开启。辅助 Agent 不得以并行预取为理由
提前读取 L2；实现者、复审者或 Prefetcher 也不得替学生作 RT3 决策。对话压缩、恢复或
handoff 后，既有授权只能保持或缩小。

## 七、可观察结果

一次健康启动至少应留下以下会话内结果，不要求落盘成第二真相源：

- 欢迎信息已展示；
- Runtime Sentinel 的 gate 结论与耗时；
- Context Prefetcher 的 route、来源摘要和 withheld/released 状态；
- Main Conductor 的 `learning-ready` 与 `recovery-settled` 结论及各自时间；
- 从用户请求到第一条可执行学习内容的总耗时。
- Main 健康路径 context 调用次数（必须为 `0`）与降级次数（最多 `1`）。

这些结果只用于本次编排与诊断，不拥有课程状态，不替代权威文件，也不自动形成发布证据。

## 八、健康启动体感检查

每次启动用以下五问做会话内快速验收；它们是可观察性检查，不另建状态文件：

1. 欢迎信息是否几乎立即出现，并且来自当前 active 皮肤；
2. 非 textbook 健康路径是否在 15 秒内出现第一条课堂内容；textbook 是否先在 45–60 秒内
   完成全 Scope 逐页扫描，再出现与精确停点相同的课堂动作；
3. Main 收到 critical 后是否保持 context 调用 `0` 次，且没有搜索 ledger、解码 pending；
4. 两个辅助分支是否真正并行，Prefetcher 是否先交付 critical、再核对同 snapshot 的 L0；
5. `recovery-settled` 前是否始终没有写回、checkpoint 结果、terminal/RT3 或“全绿”宣称。

若 critical 的权威 route 明确为 `none`，第 2 项改为在同一时间目标内如实告知“当前没有
可执行学习动作”，不得为满足指标虚构课程内容。体感项未达标时记录本轮观察与具体耗时；
只有命中前文的 FAIL、drift、来源冲突或 `blocking_teach` 才升级为教学阻断。

## 九、Agent 生命周期操作口令

- 开课：按 Startup Formation 启动，critical-first，Main 不重做 context；
- 收工：辅助 Agent 正常结束运行，立即释放 `agent_max_active` 槽位，身份可保留在池中；
- 再开同类工作：优先复用已完成的同职责 Agent；
- 新领域或需要干净上下文：池未满时新建，仍受 `agent_max_active` 限制；
- 改系统或验证：使用 Task Assist Budget，默认一个辅助 Agent、三条测试命令、十分钟，
  不得把日常启动的两个辅助身份自动扩张为施工预算。

池容量与活跃并发必须分开理解：`agent_pool_limit=6` 表示可保留的身份数，
`agent_max_active=3` 表示同时运行数（含 Main）。效率来自关键路径上的首个足够小的交付，
不是把池内身份全部同时唤醒。

## 十、权威索引与提效公式

| 主题 | 权威路径 |
|---|---|
| 启动编排 | `main/50_playbook/startup_orchestration.md` |
| 宪法入口 | `main/t2ag.md` 第 3 节 |
| 工作区入口 | 工作区与当前形态的 `AGENTS.md` |
| 协作偏好 | `main/10_student/profile/profile.md` 的 `agent_collaboration_preferences.v1` |
| 池与活跃语义 | `main/00_core/domain_model.md` |
| critical 工具 | `main/70_tools/t2ag_context.py --format critical` |

操作速记：

```text
并行只读分支 × 首交付足够小 × Main 零重复 × 用完释放槽
≠ 再堆 Agent
```

## 十一、入口轴合同（entry.*）

宪法 `main/t2ag.md` §3 只留指针；入口轴合同正文只在本文件。本轴 **不是** `session_lane` 正本（0a-4／closeout §14.66／§14.81）：词面同四名，轴独立演化。本文件不拥有 `session_lane`。

前缀 token 写死为 **`entry.`**（AS-8；能裁则裁）。四入口：

| 入口 | I/O | 禁止 |
|---|---|---|
| `entry.teach` | 课程恢复 + Scope | 不得绕过 kernel |
| `entry.maintain` | 不触发课程恢复 | 不得绕过 kernel |
| `entry.audit` | 只读取证；不触发恢复 | 不得绕过 kernel |
| `entry.release` | 不获发布授权 | 不得绕过 kernel |

四入口共用前缀只有三项：读取 `main/t2ag.md`、按 §零展示欢迎信息、经过既有
`runtime.authorization` kernel（closeout §14.80；**不**新增 check ID）。分流后，只有 `entry.teach`
运行课程恢复、Context Prefetcher 与 textbook Scope scan，并产出
`learning-ready`；各入口在发生写动作前分别取得其适用的 `recovery-settled`。本轴不调度代码、
不新建 dispatcher。

## 十二、rule_migration（DEC-3 A3 · 宪法 §3 子约束）

分母＝子约束 ≥18（closeout §14.77 AS-5；能裁：S3-10 拆 4、S3-13 拆 2、S3-09 拆 4 条时间/halt 子句）。本表 20 行（S3-01..08 + S3-09a..d + S3-10a..d + S3-11 + S3-12 + S3-13a..b）。无 retire。S3-03／S3-12 未判定已裁为 sink。不新增 check ID。A3 冻结批未改 `main/t2ag.md`；收口修复将 §3 压为入口指针与不可变门，不改变本表 keep/sink 裁决。

| rule_id | 旧位置/原文锚点 | 动作 | 新 owner/等价门 | 消费方 | 验证 |
|---|---|---|---|---|---|
| S3-01 | `main/t2ag.md` §3 L85–86「每次进入本项目：立即按当前皮肤展示欢迎信息」 | sink | `50_playbook/startup_orchestration.md` §零 | `main/bin/t2ag`；`80_interface/README.md`；`skin_playbook.md`；`first_run.md`（E1：Doctor 零消费） | `grep -n "自宪法 §3.0 下沉" main/50_playbook/startup_orchestration.md` |
| S3-02 | `main/t2ag.md` §3 L85–87「同时并行启动只读恢复分支（Runtime Sentinel + Context Prefetcher）」 | sink | `startup_orchestration.md` §一／§三 | `AGENTS.md`「启动」条目（E1：Doctor 零消费） | `grep -n "python -B main/70_tools/t2ag_doctor.py --profile runtime" main/50_playbook/startup_orchestration.md` |
| S3-03 | `main/t2ag.md` §3 L87–88「不得等全部恢复检查串行结束后才给学生第一条反馈」 | sink | `startup_orchestration.md` §三／§四.1（E1：等价正文已在；能裁：未判定→sink） | Main Conductor 汇合（E1 T-08）；Doctor 零消费 | `grep -n "不必等待 Runtime Sentinel 全部返回" main/50_playbook/startup_orchestration.md` |
| S3-04 | `main/t2ag.md` §3 L90「两个可观察状态（判据 canonical：startup_orchestration.md §4.1/§4.2）」 | keep | 宪法留指针；等价门 `startup_orchestration.md` §4.1／§4.2 | 启动会话；Doctor 零消费 | `grep -n "两个可观察状态" main/t2ag.md` |
| S3-05 | `main/t2ag.md` §3 L92–93 `learning-ready` 定义（critical 来源未变、route 唯一精确停点、无教学阻断；textbook Scope 扫描 A1–A5／A6） | sink | `startup_orchestration.md` §4.1 | ADR-0003；`source_page_assets.md` §3.1（E1：Doctor 零消费） | `grep -n "### 4.1 Learning-ready" main/50_playbook/startup_orchestration.md` |
| S3-06 | `main/t2ag.md` §3 L93–94「Snapshot、content_consumed、历史 receipt 均不得冒充本轮」 | sink | `startup_orchestration.md` §4.1 | `AGENTS.md`「textbook 扫描门」（E1：Doctor 零消费） | `grep -n "content_consumed" main/50_playbook/startup_orchestration.md` |
| S3-07 | `main/t2ag.md` §3 L95 `recovery-settled` 定义（Doctor 0 FAIL、state 无漂移、完整来源核对完成） | sink | `startup_orchestration.md` §4.2 | `t2ag_doctor.py --profile runtime`；`t2ag_state_refresh.py --check`（E1） | `grep -n "doctor_exit == 0" main/50_playbook/startup_orchestration.md` |
| S3-08 | `main/t2ag.md` §3 L95–96「任何进度写入、checkpoint 确认、terminal/RT3、切换前台或『状态已闭合』宣称必须等待该状态」 | keep | 宪法级正本（closeout §14.80）；机器 leftover＝既有 `runtime.authorization`（§6.2）；无新 check | 写回路径；A1 kernel（E1：Doctor 零消费本句） | `grep -n "runtime.authorization" main/70_tools/validation_workflow.json` |
| S3-09a | `main/t2ag.md` §3 L98「critical ≤10 秒」 | sink | `startup_orchestration.md` §一／§五 | 启动编排（E1：Doctor 零消费） | `grep -n "critical 单独等待上限为 10 秒" main/50_playbook/startup_orchestration.md` |
| S3-09b | `main/t2ag.md` §3 L98「首条内容 ≤15 秒」 | sink | `startup_orchestration.md` §一／§五 | 启动编排（E1：Doctor 零消费） | `grep -n "第一条可执行学习内容 ≤15 秒" main/50_playbook/startup_orchestration.md` |
| S3-09c | `main/t2ag.md` §3 L98「完整后台 ≤45–60 秒」 | sink | `startup_orchestration.md` §五（机器上限＝已写 45 秒，**不是**宪法 45–60） | 启动编排（E1：Doctor 零消费） | `grep -n "等待上限仍为 45 秒" main/50_playbook/startup_orchestration.md` |
| S3-09d | `main/t2ag.md` §3 L98「迟到阻断暂停后续推进」 | sink | `startup_orchestration.md` §五 | Main Conductor（E1） | `grep -n "暂停下一动作" main/50_playbook/startup_orchestration.md` |
| S3-10a | `main/t2ag.md` §3 L100–101「未初始化判据与初始化流程 canonical：first_run.md」 | sink | `50_playbook/first_run.md`（`## 判据`／`## 步骤`） | `t2ag_init.py`（E1） | `grep -n "^## 判据" main/50_playbook/first_run.md` |
| S3-10b | `main/t2ag.md` §3 L100–101「模板须用 40_course/_templates/course/」 | sink | `40_course/_templates/course/`（能裁拆条；E1 复合 owner 原为 `first_run.md`，该路径为 E1 原文已点名） | `t2ag_init.py`／`first_run.md`（E1） | `grep -n "不是真实课程实例" main/40_course/_templates/course/README.md` |
| S3-10c | `main/t2ag.md` §3 L101「不预置真实学生编号」 | sink | `50_playbook/first_run.md` | `t2ag_init.py`（E1） | `grep -n "不创建学生编号层" main/50_playbook/first_run.md` |
| S3-10d | `main/t2ag.md` §3 L101「不自动创建 .venv」 | sink | `50_playbook/first_run.md` | `t2ag_init.py`（E1） | `grep -n "venv" main/50_playbook/first_run.md` |
| S3-11 | `main/t2ag.md` §3 L102–103 日常接管 canonical `context_packet.md` | keep | `50_playbook/context_packet.md`；enforcement 既有 `runtime.context_packet`（rule_binding → `context_packet.md#九、规则层按 session_lane 加载`） | `runtime.context_packet`（E1：唯一有 Doctor 强制的日常接管条） | `runtime.context_packet` |
| S3-12 | `main/t2ag.md` §3 L104「runtime doctor FAIL：先修本地教学状态，不开新内容；release 侧 FAIL 只阻断候选与发布」 | sink | `50_playbook/doctor_contracts.md`（FAIL 语义正本；能裁：未判定→sink；无新 doctor check） | runtime／release 启动路径（E1） | `grep -n "Doctor 返回 FAIL 后必须阻断" main/50_playbook/doctor_contracts.md` |
| S3-13a | `main/t2ag.md` §3 L105「Cloud bridge paused 时云端投影只读」 | keep | `doctor_contracts.md#Cloud 暂停态`；enforcement 既有 `runtime.cloud_pause` | `runtime.cloud_pause`（E1） | `runtime.cloud_pause` |
| S3-13b | `main/t2ag.md` §3 L105–106「上下文工具不可执行时按 lesson_recover.md 手工分层摘录，不退回无差别全量读取」 | sink | `50_playbook/lesson_recover.md` | 降级路径（E1 T-13）；`startup_orchestration.md` §五 | `grep -n "工具失败时才按这些步骤手工做逐段摘录" main/50_playbook/lesson_recover.md` |

**下沉闭包四项**（整表共用）：

1. **新 canonical owner**：sink 行见上表；keep 行正本仍在宪法或既有 playbook／既有 check。
2. **必要入口指针**：宪法 §3 现只保留显式入口声明、公共前缀、状态硬门与下沉 owner 指针。
3. **消费方**：见上表。Doctor 强制面仍仅 S3-11（`runtime.context_packet`）与 S3-13a（`runtime.cloud_pause`）。S3-08 机器 leftover＝既有 `runtime.authorization`。
4. **验证证据**：上表「验证」列；全部为既有 grep 或既有 check ID，无新 ID。

**未登记删除审查**：无 retire。E1 初判 sink／keep 的条目均 follow；S3-03／S3-12 按能裁 sink，不 retire。

## 十三、入口 cutover（DEC-3 A6）

合同正文见 §十一；宪法 §3 子约束迁移表见 §十二（20 行，本批不复制）。本 cutover 只改启动调用面：不调度代码、不新建 dispatcher、不新增 check ID。

### 13.1 两轴声明（调用方必填）

凡调用「启动」者必须**同时、分别**声明：

1. **入口轴** token：`entry.teach` | `entry.maintain` | `entry.audit` | `entry.release`（§十一）。
2. **`session_lane`**（本文件不拥有；0a-4／closeout §14.66／§14.81）。两轴独立，不得用一词顶两轴。

`--profile runtime` / `--profile release` **不是**入口。那是 Doctor 档位轴（AS-7：`--profile release`＝59 条；与入口轴正交）。不得把档位词读成 `entry.*`。

### 13.2 四入口 I/O（cutover）

| 入口 | 允许 | 禁止 |
|---|---|---|
| `entry.teach` | **仅此入口**可启动课程恢复 + textbook Scope 扫描（`first_run.md` / `t2ag_init.py`） | 不得绕过 kernel |
| `entry.maintain` | runtime Doctor + `state --check`；**不**启动课程恢复 | 不得绕过 kernel |
| `entry.audit` | 只读取证；**不**启动课程恢复 | 不得绕过 kernel |
| `entry.release` | **不**授予发布授权 | 不得把本入口当成 publish 许可；Doctor `--profile release` 是另一轴 |

四入口写动作一律等 `recovery-settled`（§4.2）。kernel＝既有 `runtime.authorization`（§十一／closeout §14.80；不新增 check ID）。

### 13.3 协议退役

隐式「每次进入跑全套启动」**在此协议退役**。调用方必须显式给入口轴 token；缺 token 不得默认为 `entry.teach` 全套恢复。

### 13.4 A6 原批未改的 3.0 leftover 锚点

A6 原批未编辑下列当时仍指向宪法「3.0 启动欢迎信息」的 dangling 锚点；A8 已在后续批
全部改准为本文件 §零：

- `main/50_playbook/first_run.md:152`
- `main/50_playbook/skin_playbook.md:153`
- `main/80_interface/README.md:44`
- `main/bin/t2ag:6`

A6 原批写面仅 `startup_orchestration.md`。当前收口修复另行改准 `t2ag.md` 与活跃
`AGENTS.md` 调用点；仍不改 doctor、`--profile` 调用点、zh/EN/Lite。

## 十四、正负矩阵（DEC-3 A7）

合同／cutover／rule_migration 正文见 §十一–十三；本表不复写那三节，只记极性。

| 极性 | 命题 |
|---|---|
| + | `entry.teach` 启动课程恢复 + Scope |
| − | `entry.maintain`／`entry.audit` 不启动课程恢复 |
| − | `entry.release` 不授予发布授权 |
| − | `--profile` 不是入口（Doctor 档位轴，与入口轴正交） |
| − | 缺入口 token 不得默认 teach 全套恢复 |
| − | 写动作一律等 `recovery-settled` |
| − | kernel＝既有 `runtime.authorization`（不新增 check ID） |
