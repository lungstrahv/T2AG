# 结课仪式（session_close）

> 本文件是 T2AG「技能固化」文档之一。
> 学生发出任何结束信号（"今天到这"、"下课"、"先这样"等）或课程自然收尾时触发。
>
> **适用场景**：每一次教学会话的结束。不完成本流程不算下课。
>
> **关联文件**：
> - 规则定义：`main/t2ag.md` → 「course_status.md 的作用 → 生成与更新规则」
> - 权威链定义：`main/00_core/t2ag_memory.md` → 「进度权威链」
> - 复测流程：`main/50_playbook/mistake_retest.md`
> - 系统问题收割：`main/50_playbook/problemlog_maintenance.md`
> - 云端只读环境：`main/50_playbook/cloud_learning_sync.md`
>
> **路径解析约定**：本流程中课程 `course_status.md`、lesson、question/mistake 等路径按
> `naming_conventions.md` §5 解析；兼容期多数课程仍在 `30_courses/`；迁移后 Run 在
> `35_course_runs/`。结课写回必须写到 §5.3 解析出的当前唯一真相源，不得硬编码单一旧路径。

---

## 一、触发条件

- 学生消息包含结束信号（"下课"、"今天到这"、"先这样"、"结束"等）
- 或本 lesson 内容自然讲完
- 或学生长时间未回应、明确要走

> **为什么是仪式不是建议**：开课漏读一个文件损失一节课；结课漏写一个文件，档案从此和现实脱节，且下次开课的 agent 无从察觉。

### 云端只读分支

若当前模型只能使用 ChatGPT Project/手机聊天，不能直接访问和修改本地仓库，则不得假装执行下方
步骤 1-9，也不得声称 doctor 已通过。此时按 `cloud_learning_sync.md` 输出完整
`T2AG_SESSION_CLOSE`，并保持 `sync_status: pending`；待本地 agent 校验和写回后，才算完成
本地结课仪式。云端事件块不是 `course_status.md` 的替代品。

---

### 课中手动存档（学生随时可触发）

学生课中随时可以要求"保存进度"。此时按 `progress_tracking.md` 立即把当前 checkpoint、
pending 状态和课堂要点写入 `course_status.md` 与 lesson，再运行状态刷新工具。手动存档是强制快照，
不自动把父 completion node 标为完成，也不替代结课仪式。

---

## 二、完整步骤

> **权威链方向**：`course_status.md`（真相源）→ 刷新缓存（memory 指针/速览、course_info 列表）。永远先写真相源，再刷缓存，顺序不可颠倒。

### 步骤 1：更新真相源 `[课程]/course_status.md`

> **前置解析**：按 `naming_conventions.md` §5.1–5.3 取得当前课程的唯一 `course_status.md` 路径。
> 若解析 FAIL（碰撞、缺载体、Case 归属不一致）→ 停止结课写回，不得猜路径。
> 兼容期示例（旧混装，仅当该课尚未迁移时）：`30_courses/MATH1607H_MathematicalAnalysis/course_status.md`；
> 迁移后示例（真实 case_id，勿写字面 SN01）：`35_course_runs/S002/CR-S002-MATH1607H/course_status.md`。

- 「当前进度」：正在学第几课、已完成内容、**精确停顿点**（页码 + 小节 + 一句话说明停在哪个概念，要求下次能直接翻开继续）
- 更新 `lifecycle_status`、`current_completion_node`、`current_checkpoint`、`checkpoint_state` 与 `next_action`
- 教材 completion node 只在内容讲完且无悬空确认/问题时关闭；不额外强制生成习题
- 项目/实践 completion node 只使用其既有计划中的产物、行动或复盘证据
- 「教学记录」：追加一条，时间精确到小时，含本次完成内容、学生掌握情况、存在问题
- 累计已投入学习时长（小时）
- 同步刷新本 lesson `lessonXX.md` 头部「当前教学进度」行：它是本文件的附属缓存，必须与停顿点一致，不得领先或滞后

### 步骤 1.5：核对课程疑问汇总 → `[课程]/question_bank.md`
- 扫描本次 lesson 的课程相关问答，确认均已建立或合并 `Q-XXXX` 条目
- 更新 `open / answered / revisit / merged` 状态；已有回答但尚不稳定的疑问不得冒充掌握，标为 `revisit`
- 系统、工具、文件与流程问题不进入课程疑问库，按 `problemlog_maintenance.md` 路由

### 步骤 2：收割本课错误 → `[课程]/mistake_bank.md`
- 扫描本次 `lessonXX.md` 的「错误尝试记录」和问答中暴露的理解偏差
- 按“知识点键”合并：同一根因再次出现只追加证据，不为不同表面题重复建条目
- 新知识点建立 `active` 周期；当堂理解单独记录，不计正式正确
- 本次正式抽查结果按 `✓/△/✗` 追加，并从记录重算尝试、独立正确、失败和错后连续正确缓存
- 满足三次独立正确且错后连续正确要求 → `maintenance`；六次未过或第 3 次失败 → `aged`
- 陈年复习卷中，同一知识点每张卷最多写入 1 次正式结果；在两个不同学习日期连续 2 次 `✓` → `maintenance`，答错则“陈年连续正确”归零
- 若学生启用了陈年复习日历，从活动课程 `course_status.md` 的实际教学日期去重计数；3-1-3 每周期计 6 个学习日期，D4 不计。关联章节/模块刚闭合时优先按 `off/suggest/auto` 处理，并更新“最近陈年复习卷 / 下次陈年日历检查”
- `maintenance` 远期抽查失败时开启新强化周期并转回 `active`；历史周期保留
- 只收知识性错误；工具/环境问题记 `main/00_core/t2ag_problemlog.md`，两本错题本不混
- 若本次出现工具、环境、文件结构、doctor、权威链或规则执行问题，按 `main/50_playbook/problemlog_maintenance.md` 追加条目；中/高复用价值条目要在步骤 4 同步 memory

### 步骤 3：学生状态写回
- 有情绪触发词（`感受：`/`心情：`等）的内容 → 按 `student_info.md` 路由写入 `10_case/students/Sxxx/` 对应文件
- 新增课程感想时分配唯一 `REFL-[课程代码]-NNNN`，随后从正文重算课程目录中的数量、最近记录和最近日期；不得手工只做 `+1`
- 学习使命变化时更新课程段开头的当前句，并追加一条“使命变化”感想保留历史
- 结课前检查本次是否出现达到门槛的可观察解题思维模式，若有则按 `student_info.md` 路由写入 `reasoning_patterns.md`；若生成替代方法或更新接替状态，执行 `method_distillation.md`，没有则不硬凑。
- 无情绪表达则不硬凑，跳过
- 遵守 `teacher_overlay.md` 的「情绪使用红线」：只写行为观察和学生原话，不写心理推断

### 步骤 4：刷新缓存层 `main/00_core/t2ag_memory.md`
- 运行 `python main/70_tools/t2ag_state_refresh.py --write` 生成当前课程、lesson、completion node、checkpoint 与下一步
- 学生状态叙述仍按实际证据人工维护，不放入机器生成区
- 若本次有 changelog / problemlog 新条目，同步「最近 5 条」摘要；高复用 problemlog 条目还要同步「关键决策索引」
- 检查全文仍 ≤ 150 行

### 步骤 5：刷新缓存层 `main/10_case/course_info.md`
- 由同一刷新工具从全部 `course_status.md` 和 active/planned G 文件生成生命周期、容量状态和当前进度
- 禁止手写 `T2AG_GENERATED` 区块；随后运行 `python main/70_tools/t2ag_state_refresh.py --check`

### 步骤 6：working_pages 窗口处理
- 课程未结束：保留 4 页滑动窗口，确认 `source_excerpt.md` 页面状态跟踪表与实际停顿点一致
- 整门课程结束：按 t2ag.md 规则删除 `working_pages/`

### 步骤 7：课后提炼检查
- 扫描本课和本次新增 problemlog 条目是否出现可沉淀的重复操作模式
- 若同类系统问题反复出现，或本次解决方案已形成稳定步骤，询问学生是否固化为新 playbook
- 若已有 playbook 但仍踩坑，优先更新旧 playbook，而不是只追加 problemlog

### 步骤 7.5：关闭匹配的课堂交接

- 按 `main/50_playbook/handoff_management.md` 检查运行时交接索引中是否有匹配当前课程/lesson 的 active `course_session` 交接。
- 只有步骤 1-7 的正式来源与缓存已经写回、所需验证通过时，才把交接改为 `resolved` 并从索引 active 表移出；尚有冲突或未验证事项则保持 active，并写明原因。
- 没有匹配交接时直接跳过，不为了完成结课而新建交接。

### 步骤 8：输出写入确认（必须展示给学生）

```text
✅ 结课写入确认
- course_status.md：lesson0X → 停顿点「……」，累计 XX 小时
- question_bank.md：新增/合并 X 个疑问；open X，revisit X
- mistake_bank.md：新增/合并 X 个知识点；抽查 X 个（active/maintenance/aged 变化）
- t2ag_memory.md：指针已刷新，下次第一件事 =「……」
- t2ag_problemlog.md：新增 X 条 / 本次无系统问题
- course_info.md：进度列已同步
- 学生状态：已记录 / 本次无；感想索引已重算 / 本次无新增
- 交接：已 resolved「handoff_id」/ 仍 active（原因）/ 无匹配交接
- git：未启用 / 待提交「文件清单」/ commit「……」/ push 已同步（按实际状态填写）
[案例指定句尾]
```

缺任何一行，学生有权要求补齐后再结束。

### 步骤 9：Git 存档
- 先按 `50_playbook/git_workflow.md` 检查 `git status --short`、`git diff --check` 和本次明确写入文件的差异
- 禁止默认 `git add .`；只用显式路径暂存步骤 8 写入确认中的 T2AG 文件，不处理工作区中的其他改动
- 每次 `git add` 与本地 `git commit` 都必须就本次明确路径取得用户确认；文件修改授权不等于 Git 授权
- agent 不执行远端上传或 push；远端仓库始终由用户手动上传
- Git 尚未初始化时记录“未启用”并跳过；未提交不阻断教学，但不能宣称已有正式发布快照

---

## 三、常见问题与避坑

- **只更新了 memory 没更新 course_status**：方向反了。缓存永远不能领先真相源，发现时以 course_status 为准回滚 memory。
- **停顿点写成"讲完了第三章"**：不合格。必须精确到页码和概念，标准是"下次能直接翻开继续"。
- **把 OCR 踩坑写进 mistake_bank**：错本。工具问题归 `main/00_core/t2ag_problemlog.md`。
- **对话意外中断没走完仪式**：下次开课时 doctor 会报缓存与真相源不一致；先向学生口头确认实际进度，修复真相源，再刷缓存，然后才开课。
- **为了凑记录编造学生情绪**：无情绪表达就跳过步骤 3，宁缺勿滥。

---

## 四、关联文件

- `[课程]/course_status.md` —— 真相源，步骤 1
- `[课程]/lessonXX/lessonXX.md` —— 头部进度行附属缓存，步骤 1 同步刷新；课中手动存档
- `[课程]/question_bank.md` —— 课程疑问汇总，步骤 1.5
- `[课程]/mistake_bank.md` —— 步骤 2
- `main/10_case/students/Sxxx/` 四文件 —— 步骤 3
- `main/00_core/t2ag_memory.md` —— 步骤 4
- `main/10_case/course_info.md` —— 步骤 5
- `[课程]/lessonXX/working_pages/` —— 步骤 6
- `main/50_playbook/handoff_management.md` —— 步骤 7.5
- `main/70_tools/t2ag_doctor.py` —— 中断兜底
- `main/50_playbook/git_workflow.md` —— 步骤 9
