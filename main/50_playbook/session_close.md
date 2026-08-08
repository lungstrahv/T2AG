# 结课与手动存档

**保护级别**：core-playbook

`progress.md` 拥有 Course 生命周期、唯一前台与精确停点；`activity_ledger.md` 拥有
Lesson/Exercise 生命周期、pending/CLR、alias 与统计。结课必须由显式前台路由并通过
`activity_close.py` 的 immutable plan + transactional apply；退役的 `current_lesson`
不得参与路由或写回。

## 结课领域树与适用性

完整结课先逐节点检查，再汇总适用项；不是要求每堂课为每个节点编造内容。每个叶节点只能是：

- `applicable`：本课确有对应事实，必须提供面向学生的摘要，必要时附证据；
- `not_applicable`：本课没有触发该项，必须说明理由，不阻断 Lesson 完成；
- `missing`：尚未检查或缺少应有内容，保留为显式缺口，可能阻断 `completed`。

五项展示偏好只控制呈现，不决定节点是否适用，也不能创造、删除或替代证据。学生可见的
教学复盘只汇总 `applicable` 项；pending body 同时保存整棵树的逐节点状态，便于核对没有漏项。

教学复盘有两个缺一不可的交付面：同一份复盘既要写入 Lesson 主载体形成持久记录，也要在
结课前直接展开到学生当前对话中。只给文件路径、链接、摘要、event ID 或 SHA 均不算完成
对话呈现。学生阅读后可以纠正；没有修订时，学生回复“结课”即可确认刚展示的唯一
`completed` pending。event ID、body SHA、result 与 presentation SHA 的绑定由系统承担，
不要求学生抄写。若结果为 `closed_incomplete`，须明确说“以未完成状态结课”。未先展示、
存在多个候选、发生漂移或展示了另一版本时，简短意图无效并拒绝写回。

```text
Lesson 完整结课流程
│
├── 0. 结课范围冻结
│   ├── 确认当前 Lesson
│   ├── 确认教材/知识范围
│   ├── 排除下一 Lesson 内容
│   └── 确认配套 Exercise 是否独立结课
│
├── 1. 学习证据归集
│   ├── 讲授与问答记录
│   ├── 学生原始回答
│   ├── 学生自我修正
│   ├── checkpoint / completion node
│   ├── Attempt / Review
│   └── question / mistake / thoughts
│
├── 2. 教学复盘
│   ├── 2.1 实际教学过程
│   │   ├── 实际讲了什么
│   │   ├── 实际采用的教学顺序
│   │   ├── 哪些地方展开或跳过
│   │   └── 与原计划有什么差异
│   ├── 2.2 课程内容完成情况
│   │   ├── 已完成内容
│   │   ├── 未完成内容
│   │   ├── 越界内容
│   │   └── 与下一 Lesson 的边界
│   ├── 2.3 知识吸收（面向学生）
│   │   ├── 学生最初怎样理解
│   │   ├── 出现过哪些思维困难
│   │   ├── 哪个例子或追问促成转变
│   │   ├── 学生怎样自我修正
│   │   ├── 最终能否独立复述或迁移
│   │   ├── 当前掌握情况
│   │   └── 仍需复测的薄弱点
│   ├── 2.4 学生课程内容反馈（只谈课程内容）
│   │   ├── 哪些内容有价值
│   │   ├── 哪些内容难懂
│   │   ├── 内容顺序是否合适
│   │   ├── 例子是否有效
│   │   ├── 哪些地方冗余或缺失
│   │   └── 学生希望怎样调整本课程
│   ├── 2.5 教师教学反思
│   │   ├── 哪些讲解有效
│   │   ├── 哪些表达过度压缩
│   │   ├── 哪里给了过多帮助
│   │   └── 下一次怎样改进
│   └── 2.6 后续学习衔接
│       ├── 间隔复测
│       ├── 下一 Lesson 入口
│       └── 后续需要消费的学生想法
│
├── 3. 完成性判定
│   ├── evidence 是否充分
│   ├── blockers 是否存在
│   ├── scope change 是否确认
│   ├── completed / closed_incomplete 建议
│   └── 判定理由
│
├── 4. 学生核对与修订
│   ├── Lesson 主载体保存完整教学复盘
│   ├── 当前对话直接展示完整学生版复盘
│   ├── 学生纠正事实或评价
│   ├── 必要时生成 pending revision
│   └── 冻结最终待确认正文
│
├── 5. 终态确认
│   ├── pending event ID
│   ├── body SHA
│   └── completed / closed_incomplete
│
└── 6. 写回与验证
    ├── ledger terminal event / CLR
    ├── progress 清除当前活动与页窗口
    ├── state refresh
    ├── runtime Doctor
    └── 回读实际写入结果
```

反馈按对象分流，不能把系统体验混入课程内容反馈：

```text
学生表达的反馈
├── 对学科内容、难度、顺序、例子的反馈
│   └── Course-content Feedback → 教学复盘 2.4
└── 对界面、启动速度、Agent、台账、输入方式的反馈
    └── System Feedback
        ├── profile 偏好
        ├── problem log
        └── 系统改进任务
```

## 一、结课前解析唯一活动

先执行只读路由：

```powershell
python -B main/70_tools/t2ag_activity.py --course <COURSE_ID> --intent close
```

命令非零时停止结课并修复 `progress.md`。输出中的 `activity_write_target` 是本次唯一活动
主载体：

- `lesson`：写 `lessons/<current_activity_id>/<current_activity_id>.md`；
- `exercise`：写 `exercises/<current_activity_id>/exercise.md`，真实提交和批改再分别写
  Attempt / Review；
- 历史 Lesson 上下文从 ledger/ContentGroup 解析，不是默认写入目标；
- planned 课程没有当前活动，不得执行结课。

## 二、Micro 与完整结课共享的强制事务

Micro close 和完整结课都必须原子完成各自声明的写入集合；只有用户明确启动
Activity close 才进入 `ongoing -> pending_close`。普通切课、跨天、
session 保存、聊天中断和 Micro 保存都不自动 pending/terminal/pause。正式结课必须把
ledger、progress、首次提示 marker 与 GENERATED 缓存放入同一事务；任何后检查失败均回滚。

### 步骤 1：先固化本次过程证据

按真实变化更新 `main/40_course/<COURSE_ID>/progress.md` 的前台停点与 next_action，但不在
progress 或活动主文件写 Activity lifecycle：

- `updated`；
- `current_activity`、`current_activity_id` 与 canonical `resume_path`；
- `activity_position`、completion node、checkpoint 与
  `queued / arrived / pending / confirmed / archived` 状态；
- 下次第一件事与当次教学摘要；
- active progress 不写 `current_lesson`；历史 Lesson 上下文只从 ledger 事件解析。

### 步骤 2：写当前活动主载体

- Lesson：追加本次讲授、问答、确认和错误尝试；“Lesson 最后停点快照”是局部证据，
  不使用 `T2AG_GENERATED`，也不覆盖 progress。
- Exercise：更新 `exercise.md` 的当前题目、精确停点和证据指针；有真实提交才按
  `exercise_evidence.md` 创建 Attempt，有真实批改才创建 Review；新 Attempt 同时保存
  创建时的 `hint_gate` 快照、最高 `assistance_level` 和真实授权/污染记录。概念问答若
  遵守 scope-only 不升级帮助等级；未经授权泄露关键结构时不得计作独立掌握。
- 两类活动都只写自己的正文。跨活动关系只写 `activity_map.md`；Exercise 结课不得顺手
  改历史 Lesson。

### 步骤 3：闭合本次真实产生的台账

- 疑问写或合并 `question_bank.md`；
- 明确知识错误与正式复测写或合并 `mistake_bank.md`；
- Exercise 的学生原图只进入对应 Attempt 的 `assets/`，不得放入教学示意图目录；
- 学生明确表达的想法按 Lesson thoughts 或 Attempt/Exercise thoughts 路由；没有真实证据
  不创建空对象。

### 步骤 4：生成 pending、严格决策并事务写回

先用 `activity_close.py --plan-pending --plan-out <new-file>` 生成不可变 pending 正文。新正文
使用 `activity_close_body.v2`，绑定范围、证据归集、完整教学复盘树、面向学生的适用项汇总、
知识五态、blocker、偏好快照、event ID 与 body SHA。旧 v1 pending 可读，但发生修订时必须
升级成 v2；不得继续生成三个平级的 `actual_review / student_feedback / knowledge_absorption`。
terminal decision 必须先展示 exact `pending_event_id`、`body_sha256` 和 `result`，但这些是
系统的完整性绑定，不是学生抄写作业。完整复盘和 tuple 已在当前对话展示、唯一 pending
无漂移时，`completed` 可由学生回复“结课/确认结课/愿意结课”直接确认；未完成态必须回复
“以未完成状态结课”。旧对话、持续委托、receipt、policy、模型推荐以及未绑定的
“可以/继续/嗯”均无效。

请求终态确认之前，必须用 pending body 的 `learner_visible_retrospective` 生成完整学生版
正文并直接发送到当前对话，同时计算 presentation SHA。学生表达简短结课意图后，工具负责
把意图绑定到已展示 tuple 与 terminal result；若复盘在展示后发生任何修订，旧 presentation
SHA 与旧意图立即失效，必须重新展示修订后的完整正文。

- 修订：追加 `pending_close -> pending_close`，旧 pending 不覆盖；
- 拒绝：追加 `pending_close -> ongoing`，不生成 CLR；
- terminal：`--plan-decision` 必须绑定 pending ID、body SHA、result、`user + direct_user` 与当前轮
  授权来源，apply 后才生成带 `valid_direct_user` 程序状态的 CLR；
- authorization receipt 只记录授权证据，不能创造授权；任何 plan 只能由匹配 payload/file SHA
  和 exact direct-user 正文的 receipt 安装。

### 步骤 5：验证落盘结果

```powershell
python -B main/70_tools/t2ag_state_refresh.py --write
python -B main/70_tools/t2ag_state_refresh.py --check
python -B main/70_tools/t2ag_doctor.py --profile runtime
```

`--write` 不可省，且必须在 `--check` 之前——顺序与 `progress_tracking.md` §三「执行顺序
固定为 `progress.md → --write → --check → doctor`」一致。P-0058 之后 `--check` 覆盖了
`progress.md` frontmatter 的 checkpoint 投影，本次会话若新增或闭合任何 checkpoint，
跳过 `--write` 会使本步骤必然报 `[FAIL] generated cache drift`，而本步骤的判据正是
「state 无 drift」。

随后重新读取 progress、`activity_write_target`、命令输出中的
`mandatory_write_targets`，以及本次实际变化的 `conditional_write_targets`。只有全部
写入可回读、state 无 drift、runtime Doctor 为 `0 FAIL`，
才能宣称本次结课已闭合。只回读这些实际目标，不因验证重载全部历史。当前活动为
Exercise 时，还要确认历史 Lesson 未被本事务修改。

写回使本会话原 L0 上下文包立即失效；若结课后继续同一课堂，按
`context_packet.md` 重新生成一次，不编辑或沿用旧包。

### 步骤 6：处理 working pages 与课堂交接

- 仅当前活动为 textbook Lesson 时，working pages 才属于默认结课范围。
- Lesson 仍在继续时保留所需窗口；关闭 Lesson 或切换到 Exercise 时，可清理物理缓存，
  但必须同时正确处理 Lesson 专用页窗口字段。
- Exercise 不读取或写入历史 Lesson 的 working pages，即使 progress 暂时保留旧页字段。
- 若存在匹配本次 `course_session` 的 active handoff，按其 `close_condition` 核对正式写回；
  只有核对通过后才标 `resolved` 并登记验证结果。项目级施工交接不随课堂结课关闭。

## 三、Micro close

适用于五分钟热身、短复测、手动“保存进度”或学生中途停止。它只原子保存真实过程证据、
前台停点与 next_action，不产生 pending、CLR 或自动 pause；可跳过本次没有新证据触发的
课程反思、组合层总结等可选综合。

Micro close 不生成欠账、不写 deferred marker。若因信息或权限不足无法完成强制事务，
本次就不是已闭合的 Micro close；应保留/建立匹配的 active `course_session` handoff，
明确缺口和恢复入口。

## 四、完整结课的附加综合

在强制事务之外，按真实触发补充：

1. 检查 `lesson_thoughts.md` 与 `exercise_thoughts.md`；满足提炼门时更新
   `10_student/profile/course_reflections.md` 并保留来源回链。
2. 跨题重复模式达到证据门槛后才更新 `reasoning_patterns.md`。
3. 组合层频率、时间偏差与欠债处置写 group `review.md`，不复制单课掌握度。
4. Cloud bridge 为 `paused` 时跳过移动端投影；云端 handoff 不能覆盖本地 progress。
5. **学习日归属按 04:00 边界，不按自然日**：本地凌晨 04:00 之前收尾的进度归前一学习日。
   canonical 规则与作用域切割（学习进度走 04:00 学习日；系统日志/月志/发行取证走自然日期）
   见 `progress_tracking.md` §三·五。本节只是消费方指针，**不重复正文**。

## 五、手动存档

学生说“保存进度”时立即执行 Micro 保存；成功后可以继续同一课堂。不得只改 memory、
learning path 或历史 Lesson，也不得把“保存”解释为结课确认。
