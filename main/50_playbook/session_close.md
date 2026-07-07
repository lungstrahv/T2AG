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

---

## 一、触发条件

- 学生消息包含结束信号（"下课"、"今天到这"、"先这样"、"结束"等）
- 或本 lesson 内容自然讲完
- 或学生长时间未回应、明确要走

> **为什么是仪式不是建议**：开课漏读一个文件损失一节课；结课漏写一个文件，档案从此和现实脱节，且下次开课的 agent 无从察觉。

---

## 二、完整步骤

> **权威链方向**：`course_status.md`（真相源）→ 刷新缓存（memory 指针/速览、course_info 列表）。永远先写真相源，再刷缓存，顺序不可颠倒。

### 步骤 1：更新真相源 `[课程]/course_status.md`
- 「当前进度」：正在学第几课、已完成内容、**精确停顿点**（页码 + 小节 + 一句话说明停在哪个概念，要求下次能直接翻开继续）
- 「教学记录」：追加一条，时间精确到小时，含本次完成内容、学生掌握情况、存在问题
- 累计已投入学习时长（小时）

### 步骤 2：收割本课错误 → `[课程]/mistake_bank.md`
- 扫描本次 `lessonXX.md` 的「错误尝试记录」和问答中暴露的理解偏差
- 每个知识性错误在 `mistake_bank.md` 新增一条，初始权重 3
- 本次开课复测过的旧条目：追加复测记录，答对权重 -1、答错 +1（上限 5）；权重 0 移入「已退役」
- 只收知识性错误；工具/环境问题记 `main/00_core/t2ag_problemlog.md`，两本错题本不混
- 若本次出现工具、环境、文件结构、doctor、权威链或规则执行问题，按 `main/50_playbook/problemlog_maintenance.md` 追加条目；中/高复用价值条目要在步骤 4 同步 memory

### 步骤 3：学生状态写回
- 有情绪触发词（`感受：`/`心情：`等）的内容 → 按 t2ag_emo 规则写入 `10_case/students/Sxxx/` 对应文件
- 无情绪表达则不硬凑，跳过
- 遵守 `teacher_overlay.md` 的「情绪使用红线」：只写行为观察和学生原话，不写心理推断

### 步骤 4：刷新缓存层 `main/00_core/t2ag_memory.md`
- 「当前状态指针」：活跃课程、当前 lesson、temppage 窗口、学生状态，全部以步骤 1 的真相源为准重写
- 「上次课摘要」：重写五项（日期 / 学到哪 / 卡在哪 / 学生状态一句话 / 下次第一件事）。"下次第一件事"必须具体到可直接执行，例如"复测 M-0007，然后从 p.58 例 4 继续"
- 「课程进度速览」表：同步本课程行
- 若本次有 changelog / problemlog 新条目，同步「最近 5 条」摘要；高复用 problemlog 条目还要同步「关键决策索引」
- 检查全文仍 ≤ 150 行

### 步骤 5：刷新缓存层 `main/10_case/course_info.md`
- 「课程列表」表中本课程的「当前进度」列，以真相源为准同步

### 步骤 6：temppage 窗口处理
- 课程未结束：保留 4 页滑动窗口，确认 `temp_page.md` 页面状态跟踪表与实际停顿点一致
- 整门课程结束：按 t2ag.md 规则删除 `temppage/`

### 步骤 7：课后提炼检查
- 扫描本课和本次新增 problemlog 条目是否出现可沉淀的重复操作模式
- 若同类系统问题反复出现，或本次解决方案已形成稳定步骤，询问学生是否固化为新 playbook
- 若已有 playbook 但仍踩坑，优先更新旧 playbook，而不是只追加 problemlog

### 步骤 8：输出写入确认（必须展示给学生）

```text
✅ 结课写入确认
- course_status.md：lesson0X → 停顿点「……」，累计 XX 小时
- mistake_bank.md：新增 X 条 / 复测 X 条（M-00XX ✓，M-00XX ✗）
- t2ag_memory.md：指针已刷新，下次第一件事 =「……」
- t2ag_problemlog.md：新增 X 条 / 本次无系统问题
- course_info.md：进度列已同步
- 学生状态：已记录 / 本次无
- git：commit「……」/ 本次无改动
[案例指定句尾]
```

缺任何一行，学生有权要求补齐后再结束。

### 步骤 9：Git 存档
- 按 `50_playbook/git_workflow.md` 第三节「日常循环」执行：`git add .` → `git commit` → `git push`
- commit 留言 = 步骤 8 确认块首行（人话写本次做了什么）
- 可攒几次课推一次，但 ≥ 每周一推
- Git 尚未初始化时跳过（首次初始化见 git_workflow.md 第一节）

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
- `[课程]/mistake_bank.md` —— 步骤 2
- `main/10_case/students/Sxxx/` 三文件 —— 步骤 3
- `main/00_core/t2ag_memory.md` —— 步骤 4
- `main/10_case/course_info.md` —— 步骤 5
- `[课程]/lessonXX/temppage/` —— 步骤 6
- `main/70_tools/t2ag_doctor.py` —— 中断兜底
- `main/50_playbook/git_workflow.md` —— 步骤 9
