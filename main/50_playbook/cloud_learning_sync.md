# 云端学习与本地回写协议（cloud_learning_sync）

> **协议标识**：`T2AG-CLOUD-1`
>
> 本流程用于 ChatGPT Project、手机端聊天等不能直接修改本地仓库的教学环境。
> 云端负责教学和产生待同步事件；本地 T2AG 负责裁决、写回和 doctor 验证。

T2AG 云端同步分成两条通道，二者不得混写：

| 通道 | 本地 → 云端 | 云端 → 本地 | 用途 |
|---|---|---|---|
| 教学状态同步 | `t2ag_mobile_entry.md` / 同步基线 | `T2AG_PROGRESS_RECEIPT` / `T2AG_SESSION_CLOSE` | 节点进度、疑问、错误与掌握证据 |
| 部件变更同步 | `T2AG_CLOUD_CHANGE_DIRECTIVE` | `T2AG_CLOUD_HANDOFF` | 规则、提示词、模板、镜像和云端部件修改 |

## 一、四层权威关系

| 层 | 作用 | 权威边界 |
|---|---|---|
| 本地 `progress.md` | 课程进度唯一真相源 | 永远最高；云端记录不得直接覆盖 |
| 云端同步基线 | 某次本地状态的只读投影 | 由 `base_state_id` 标识，只证明导出时状态 |
| `T2AG_SESSION_CLOSE` | 基线之后发生的待回写教学事件 | `sync_status` 在云端只能是 `pending` |
| `t2ag_mobile_entry.md` | 手机端快速恢复缓存 | 不是独立真相源，不得压过本地状态或有效事件块 |

完整文本镜像同样只是只读快照。它可以补规则、lesson 和教材上下文，但不得覆盖更新的
同步基线或有效事件块。云端模型不得声称已经修改本地文件、运行 doctor 或完成同步。

### 1.1 云端项目模式与身份路由

`t2ag_mobile_entry.md` 必须声明 `cloud_project_mode`，只允许以下两种模式：

| 模式 | 用途 | 身份来源 |
|---|---|---|
| `personal_instance` | 已实例化学生的个人云端课堂 | `main/10_student/profile/profile.md` 与 `main/20_teacher/overlay.md` 的已同步只读投影 |
| `generic_skeleton` | 新安装、模板演示或公开骨架 | 空 profile 模板；教师未配置或默认 T001；不得加载实例课程进度 |

- `personal_instance` 中，学生编号、教师角色与模板映射必须来自带 `base_state_id` 的移动端入口；
  完整文本镜像、skeleton 示例和历史 lesson 只能补上下文，不得反向改写身份。
- 教师模板编号不是个人身份。应写成“课程中的教师角色 TRxx 采用 T00x 模板”，不得把模板编号
  当成真实教师实体。
- 模式缺失、身份字段缺失或资料互相矛盾时，身份保持 `UNKNOWN/UNASSIGNED` 并请求最小核对；
  不得从课程示例、lite、历史日志或 skeleton 猜测。
- `generic_skeleton` 永远不得继承 `personal_instance` 的学生档案、课程停点或教师映射。

## 二、云端开课恢复

1. 读取 Project Instructions，确认协议标识为 `T2AG-CLOUD-1`。
2. 读取 `t2ag_mobile_entry.md`，取得 `cloud_project_mode`、课程、lesson、精确停顿点、
   `base_state_id`、下一步动作，以及该模式允许的身份路由字段。
3. 查找该基线之后最新的有效 `T2AG_SESSION_CLOSE`；按 `closed_at` 顺序恢复，重复
   `session_id` 只计算一次。
4. 若看不到旧聊天中的状态块，不得假装已经读取；请学生粘贴最新状态块，或明确只从基线继续。
5. 若基线、状态块、完整镜像或学生口述冲突，暂停新内容，向学生核对；不得静默选一个版本。
6. 讲新内容前读取上传的教材原文、文本层 PDF 或当前补充讲义；缺少所需原文时说明缺口，
   不凭模型记忆把新内容冒充教材讲授。
7. 用一句话报告恢复点并询问是否继续；学生确认后才进入教学。

## 三、云端教学门

- 手机端默认每轮只推进一个概念、定义、定理、证明步骤或例题节点。
- “看过”“讲过”或练习答对只是接触/理解证据，不自动等于掌握，也不自动放行下一概念。
- 概念闭合至少需要学生完成复述，并能给出、判断或解释一个正例和一个反例；不适合反例的
  内容改用边界情形或错误方法辨析。证据不足时保持 `confirmation_state: pending`。
- 每个节点结束都给出“继续 / 再讲一遍 / 提问”门；收到明确“继续”才推进。
- 学生使用 `问题：` 或 `疑问：` 时，立即暂停后续推进，先回答并把问题写入结课事件块。
- 回答习题后，除非学生本轮明确表示没有疑问，否则根据其实际步骤分析方法并询问有无疑问；
  过程证据不足时请学生补充，不猜测思路。
- 教学节奏可依据学生明确表达的状态调整，但不得降低掌握标准、跳课、跳页或漏读教材原文。
- 云端默认不生成 ZIP；只提供当前教学所需内容和待同步事件块。

## 四、云端结课事件块

completion node 完成或学生手动说“保存进度”时，云端先产生紧凑回执；普通 checkpoint 只在
云端内部静默保存，不逐点打扰学生：

```text
T2AG_PROGRESS_RECEIPT
- protocol_version: T2AG-CLOUD-1
- receipt_id: CPR-<COURSE>-<YYYYMMDDTHHMMSS+TZ>-<4CHARS>
- produced_at: <ISO-8601 with timezone>
- base_state_id: <id or UNKNOWN>
- course: <course code>
- current_activity: <lesson | exercise>
- current_activity_id: <lessonNN | Udddd>
- resume_path: <canonical current activity path>
- lesson_context: <lesson id | NONE>
- receipt_kind: <completion_node | manual_save>
- completion_node_id: <stable id or NONE>
- checkpoint_id: <stable id>
- exact_stop: <page / section / action>
- confirmation_state: <pending | confirmed | not_applicable>
- sync_status: pending
END_T2AG_PROGRESS_RECEIPT
```

同一个 `receipt_id` 只能导入一次。`manual_save` 只强制保存当前停点，不得把 completion node
改为 completed。正常结课仍输出下方完整事件块。

学生说“下课”“今天到这”“先这样”“结束”，或课程自然收尾时，云端模型必须输出以下
纯文本块。字段不可省略；未知值写 `UNKNOWN`，不得编造。

```text
T2AG_SESSION_CLOSE
- protocol_version: T2AG-CLOUD-1
- session_id: CLOUD-<COURSE>-<YYYYMMDDTHHMMSS+TZ>-<4CHARS>
- closed_at: <ISO-8601 with timezone>
- t2ag_version: <version or UNKNOWN>
- base_state_id: <id from t2ag_mobile_entry.md or UNKNOWN>
- course: <course code>
- current_activity: <lesson | exercise>
- current_activity_id: <lessonNN | Udddd>
- resume_path: <canonical current activity path>
- lesson_context: <lesson id | NONE>
- duration_minutes: <non-negative integer or UNKNOWN>
- source_evidence: <file / page / section actually used, or NONE>
- covered: <explained or attempted content>
- completed: <only content whose confirmation gate is closed>
- confirmation_state: <pending | confirmed | not_applicable>
- pending_checkpoint: <exact unclosed confirmation, or NONE>
- mastery_evidence: <student-produced evidence only, or NONE>
- open_questions: <questions and status, or NONE>
- mistakes_to_retest: <knowledge-level candidates, or NONE>
- student_state_note: <student-expressed observation only, or NONE>
- exact_stop: <page / section / concept / before-or-after checkpoint>
- next_first_action: <one directly executable action>
- files_to_update: <suggested local relative paths>
- privacy_scope: uploaded_project_only
- sync_status: pending
END_T2AG_SESSION_CLOSE
```

字段纪律：

- `session_id` 在所有云端会话中唯一；一经输出不得改号重发。
- `base_state_id` 标识课程状态快照，不可用 `t2ag_version` 代替；规则版本相同不代表进度相同。
- `covered` 记录讲过什么，`completed` 只记录已过确认门的内容；两者不得混写。
- `mastery_evidence` 只写学生实际复述、举例、证明或解题行为，不写教师推断。
- `source_evidence` 必须能追溯到实际读取的上传材料；没读到原文写 `NONE`。
- 云端无权把 `sync_status` 写成 `synced`，也不得在正文声称已写回本地。
- 事件块只包含本次教学所需信息，不复制与课程无关的个人、情绪、交易或身份资料。

## 五、本地导入与防重复

本地 agent 收到一个或多个事件块后，按以下顺序执行：

1. 原样保存输入用于核对，只解析 `T2AG_SESSION_CLOSE` 与 `END_T2AG_SESSION_CLOSE` 之间的字段；
   普通聊天总结不能替代事件块。
2. 校验协议、必填字段、枚举值、时间和 `duration_minutes`；不合格时停止写回并列出缺项。
3. 在 `main/` 与 `cloud/cloud_sync_state.md` 检索 `session_id` 或 `receipt_id`。已存在即判为重复导入，
   不再次累计课时、疑问或错误记录。
4. 将 `base_state_id` 与 `cloud/cloud_sync_state.md` 的已知基线核对，再校验事件中的
   显式活动三元组，并读取本地 `progress.md`、当前活动主载体和相关 question/mistake
   记录。旧事件若只有 `lesson`，必须进入人工兼容迁移，不能静默推断当前活动。
5. 若基线未知、落后且本地已前进，或精确停点互相矛盾，标记 `conflict`；先向学生核对，
   未确认前不改课程进度。
6. 无冲突时先更新 `progress.md` 真相源，并在教学记录中保留 `session_id`；再依统一
   活动路由更新当前 Lesson/Exercise 主载体、`question_bank.md`、`mistake_bank.md` 和
   学生档案。候选错误仍须按现有门槛归因，
   不能因为云端列出就自动成为正式错题。
7. 从真相源刷新 `t2ag_memory.md` 与 `learning_path.md`；不得从移动端入口反向覆盖真相源。
8. 运行 `main/70_tools/t2ag_doctor.py`。只有写回完成且 doctor 为 `0 FAIL`，才能记为 `synced`。
9. 在 `cloud/cloud_sync_state.md` 追加同步结果，并向用户输出 `T2AG_SYNC_RECEIPT`；若发生冲突，
   状态写 `conflict`，保留原因与待确认项。

```text
T2AG_SYNC_RECEIPT
- protocol_version: T2AG-CLOUD-1
- session_id: <imported session id>
- status: <synced | duplicate | conflict | rejected>
- written_files: <relative paths or NONE>
- doctor: <N FAIL, N WARN | NOT_RUN>
- note: <short result>
END_T2AG_SYNC_RECEIPT
```

## 六、冲突裁决与降级模式

| 情况 | 动作 |
|---|---|
| `session_id` 已出现 | 返回 `duplicate`，零写入 |
| `base_state_id: UNKNOWN` | 人工核对本地停点后才可导入 |
| 本地状态已超过云端基线 | 只合并不冲突的证据；进度变化需学生确认 |
| `covered` 与 `completed` 混淆 | 以确认门证据为准，缺证据则保持 pending |
| 教材来源缺失 | 可记录讨论，不把新知识计为教材驱动的已完成内容 |
| 多个事件块互相冲突 | 按时间列出差异，请学生裁决，不按“最新即正确”自动覆盖 |

规则版本或云端投影不一致时按风险降级，不一律阻断教学：

- 仅显示、措辞、非当前课程辅助字段不同：标记 `safe_degraded`，继续当前教学，不启用缺失功能。
- 进度字段或节点 schema 不同：可只读恢复到共同字段，暂停自动回写节点，要求最小核对。
- 权威链、身份路由、隐私范围、当前停点或确认门冲突：暂停推进与写回，等待本地裁决。

## 七、部件变更双向同步

### 7.1 本地更新后发出变更指令

本地修改规则、提示词、模板、状态块 schema、云端镜像结构或其他会影响云端运行的部件后，
必须在本轮结束前完成以下动作：

1. 识别哪些本地变更会影响云端；普通课程进度变化仍走教学状态同步，不重复发部件指令。
2. 在 `cloud/outbox/` 新建唯一文件 `CD-YYYYMMDD-NNNN.md`，保存完整变更指令。`draft` 可以编辑；
   一旦进入 `ready_to_send` 并分配正式 ID，正文不可改写。需要修正时新建指令并用 `supersedes` 关联。
3. 指令必须列出本地改了什么、云端应该改什么、验收标准、所需附件和隐私影响；不得只写“同步最新版”。
   若变更涉及云端同步协议本身，`main/50_playbook/cloud_learning_sync.md` 必须作为协议定义源随指令发送；
   Project Instructions 只是执行投影，不能替代定义源参与架构审查。
4. 在 `cloud/cloud_sync_state.md` 登记 `directive_id` 与当前状态。
5. 将指令及其列出的附件发送到云端。没有上传工具证据或用户确认时，只能记
   `ready_to_send`，不得声称 `sent`。
6. 云端确认接收后，将状态更新为 `acknowledged`；云端返回交接且本地完成裁决后才可 `closed`。

```text
T2AG_CLOUD_CHANGE_DIRECTIVE
- protocol_version: T2AG-CLOUD-1
- directive_id: CD-<YYYYMMDD>-<NNNN>
- created_at: <ISO-8601 with timezone>
- local_t2ag_version: <version>
- target_cloud: <project name or UNKNOWN>
- affected_components: <component names>
- local_changed_files: <relative paths>
- expected_cloud_changes: <explicit required modifications>
- acceptance_criteria: <observable completion conditions>
- attachments_to_send: <relative paths>
- migration_notes: <compatibility or ordering notes, or NONE>
- privacy_impact: <NONE | REVIEW_REQUIRED | description>
- reply_required: T2AG_CLOUD_HANDOFF
- sent_at: <ISO-8601 with timezone or NONE>
- send_evidence: <upload/message evidence or NONE>
- status: <draft | ready_to_send | sent | acknowledged | closed>
END_T2AG_CLOUD_CHANGE_DIRECTIVE
```

用户确认某个正式指令已经在手机端应用、但本地缺云端回执时，状态记为
`applied_unacknowledged`，保留用户确认时间与证据说明；下一次同步只需返回轻量确认：

```text
T2AG_DIRECTIVE_ACK
- directive_id: <formal id>
- directive_hash: <sha256 of immutable directive block>
- applied_version: <cloud-visible version>
- applied_at: <ISO-8601 with timezone or UNKNOWN>
END_T2AG_DIRECTIVE_ACK
```

### 7.2 云端修改后必须交接

云端收到变更指令后，只执行或生成指令明确列出的云端修改。平台不能直接改 Project Instructions
或既有文件时，应生成完整替换文件，不得假装已在设置中生效。若云端发现指令之外值得修改的内容，
只能作为提案写进交接，不能静默扩大范围。

云端完成任何实际修改、替换文件生成或新增提案后，必须生成可下载/复制的
`CH-YYYYMMDD-NNNN.md`，包含以下完整块：

```text
T2AG_CLOUD_HANDOFF
- protocol_version: T2AG-CLOUD-1
- handoff_id: CH-<YYYYMMDD>-<NNNN>
- directive_id: <source CD id or NONE_FOR_UNSOLICITED_PROPOSAL>
- produced_at: <ISO-8601 with timezone>
- cloud_project: <project name or UNKNOWN>
- cloud_base_state_id: <base_state_id or UNKNOWN>
- changes_applied: <actual cloud-side changes, or NONE>
- generated_files: <downloadable file names, or NONE>
- deviations: <differences from directive, or NONE>
- verification: <checks actually performed, or NOT_RUN>
- open_questions: <items requiring local discussion, or NONE>
- proposed_local_changes: <explicit local proposals, or NONE>
- privacy_impact: <NONE | REVIEW_REQUIRED | description>
- status: proposed_for_local_review
END_T2AG_CLOUD_HANDOFF
```

云端无权把交接状态写成 accepted、merged 或 synced。聊天总结不能替代交接文件；若没有生成文件，
至少输出完整纯文本块供本地保存。

**协议不变量（本地同样遵守）**：块内 `status` 字段**永久**保持云端产出值 `proposed_for_local_review`。
doctor 校验此不变量。本地裁决结果**不得**改写块内 `status`；应写入：
（a）`cloud_sync_state.md`「云端交接」表的 `local_decision` 列；
（b）可选：同一 CH 文件在 `END_T2AG_CLOUD_HANDOFF` **之后**的「本地裁决」节（`sync_completed` 等）。
任何施工单要求修改块内 status 视为工单错误（见 `batch_workorder_spec.md` §三第 9 条）。

### 7.3 本地接收、讨论与裁决

1. 将云端交接原样保存到 `cloud/inbox/CH-YYYYMMDD-NNNN.md`，先校验 `handoff_id`、
   `directive_id`、协议、实际文件和偏差说明。
2. 交接是提案与执行证据，不是本地规则源；不得自动覆盖 `main/`、`cloud/` 或课程文件。
3. 向用户展示“已做修改 / 偏离指令 / 建议本地修改 / 未决问题 / 隐私影响”，逐项讨论。
4. 用户裁决为接受、部分接受或拒绝后，才在本地实施被接受部分；部分接受必须记录未接受项。
5. 本地修改后运行 doctor，并在 `cloud_sync_state.md` 登记裁决、文件和验证结果；
   **不**把 CH 块内 `status` 改为 accepted/synced。
6. 若本地裁决又改变云端应有状态，生成下一份新 `directive_id`；不得改写旧指令伪装闭环。

未被本地接受的云端修改可以继续留在 Project 内供试验，但不得被描述为 T2AG 正式规则。云端
handoff 默认不加入日常启动链，只有当前同步讨论明确指向它时才读取，避免旧提案污染教学恢复。

## 八、隐私与上传边界

隐私范围分为两层：

- `existing_project_scope`：用户已经手动上传到当前个人实例的内容，可继续在该 Project 内使用；
  不追溯清理，也不因此授权二次复制、导出、公开或迁移到其他服务。
- `automatic_sync_allowlist`：agent 自动准备或建议同步的最小低风险字段，默认仅包含课程代码、
  lesson、稳定节点 ID、精确停点、规则版本、内部角色/模板编号和不含正文的状态摘要。

用户可以手动上传个人信息；该授权只适用于当前 personal instance。任何新增自动同步字段都必须
显式登记和审查。skeleton 与 lite 永远不得吸收个人实例内容。
- 缺少可能被隐私规则挡住的上下文时，报告缺口并使用最小必要信息继续；不得诱导用户补充无关身份信息。
- 缺少必要上下文时只请求最小信息，不从已省略材料推断或补齐私人字段。

## 九、提示词一致性

可复制的云端提示词位于 `cloud/T2AG_PROJECT_INSTRUCTIONS.txt`。本文件是协议定义源；提示词是
面向云端模型的执行投影。修改权威链、状态块字段、确认门、变更指令、云端交接、隐私边界或
同步语义时，必须在同一批次同步两者、生成新的 outbox 指令并运行 doctor，防止本地规则与云端
行为分叉。
