# T2AG 0.2.3 功能流程图

**保护级别**：core-playbook

> 本文件是 `t2ag.md`、domain model 与各 playbook 的派生视图，不单独立法。
> 每图的 `FLOW` 标记供离线 HTML 指南生成器提取，不能删除或复用。

**全部图使用字符型（```text 围栏）。** 早期版本允许一般系统过程写 Mermaid，动机是希望图
能自动跟着版本走；但流程图编码的是**意图**，不是能从目录结构推导出来的东西，所以那个好处
从未兑现——图照样要手维护，还额外背了一个自制 SVG 布局器。两种视觉语言混排的结果是九张图
里五张一个样、四张另一个样。现在统一为字符图：读者一致，diff 可读，离线指南不需要渲染层。
Mermaid 作为一种格式没有问题，只是这份文件不用它。

能从现实生成的东西才交给生成器：离线指南的**目录树**由 `build_guide.py` 扫真实文件系统产出，
改了结构下次构建自动跟上；流程图不属于这一类，手写并承认它手写。

字符图记号：`●` 起点 · `▼` 动作 · `◇` 判断 · `├─ └─` 分支出口 · `◉` 终点 ·
`·` 后为该步的补充说明。

## 图 0 · 首次启动

<!-- FLOW:first_run -->
```text
● 打开目标实例
│
▼ 读取 active skin：welcome_msg + art_file + 版本号
▼ doctor + state refresh --check
│
◇ 首次启动判据成立？
│  └─ 否 ─→ 日常接管：进入图 1，不做任何初始化
│
▼ 逐项确认身份、时区、目标、已有基础与辅导偏好
▼ 写 answers.json           · 缺任一必答项即拒绝，不代填默认值
▼ t2ag_init.py init         · profile 与发行身份（云仍 paused）
│
◇ 用户已确认首门 Course 与真实入口？
│  └─ 否 ─→ 等待确认；不代选课程，也不代选 Lesson / Exercise 入口
│
▼ t2ag_init.py new-course   · Course、首个活动、teacher 映射
▼ t2ag_init.py new-group    · plan / calendar / review / bindings
▼ state refresh --write + --check
│
◇ doctor 为 0 FAIL？
│  └─ 否 ─→ 修复状态，不开新内容
│
◉ 进入图 1
```
<!-- /FLOW:first_run -->

首次判据是：profile 未初始化、仍有必填占位符，或 memory 上次课日期为 `—`。

实例由 `main/70_tools/t2ag_init.py` 生成，模型不照 `first_run.md` 手抄文件：模型的职责是
提问、把答案写成 `answers.json`、调用工具、复核输出。工具只从 `40_course/_templates/` 与
`30_group/_templates/` 实例化，缺任一必答项即拒绝并一次报全；不代选课程与入口，不装依赖、
不建 `.venv`、不下教材、不生成 Engagement、不做 git 写，也不代跑 doctor 与 state refresh。
前置校验全部先于第一次写盘，失败不留半个课程。

## 图 1 · 一次教学会话

<!-- FLOW:panorama -->
```text
● 学生要求继续课程
│
▼ doctor + state refresh --check
│
◇ 有 FAIL？
│  └─ 是 ─→ 修复状态，不开新内容
│
▼ 生成一次 L0        · 逐字摘录状态、教学契约、当前题面 / 必要教材窗口
▼ 同一原始字节缓存    · 校验 ProgressSnapshot、活动路由与教师路由
│
◇ current_activity
├─ lesson   ─→ L1：只追加 L0 尚未包含的当前活动证据
└─ exercise ─→ L1：当前题已有直接证据才追加 Attempt / Review
│
▼ L2 只由冲突、复测、排期、历史追问或结课触发
▼ 正课循环            · 见图 1b
│
◇ 结课类型（Micro 与完整走同一强制事务）
│
▼ 强制事务            · progress + 当前活动主载体 + 真实台账
│
◇ 完整结课？
│  └─ 是 ─→ 按真实触发补 reflections / reasoning / Group review
│
▼ state refresh --write + --check
▼ 完整 doctor；重读写入目标
│
◉ 会话闭合
```
<!-- /FLOW:panorama -->

Cloud 为 `paused` 时只跳过移动端投影，不跳过本地写回。课程进度只写 `progress.md`，
memory 与 learning path 都由 state refresh 生成。

## 图 1b · 正课循环

<!-- FLOW:teaching_loop -->
```text
课堂入口
├─ 1. 恢复与来源门
│  ├─ 解析唯一 current_activity 与精确停点
│  ├─ Lesson：核对当前 PDF 页 / 书内页、Scope、原文与 active segment
│  └─ Exercise：只呈现当前题面，不泄露未授权思路
├─ 2. 展示本轮课堂树
│  ├─ Lesson 开场：先概括整课学习内容，再显示 ASCII 知识树
│  ├─ 询问学生对路线的感受与是否进入第一块
│  ├─ 当前教材位置或题号
│  ├─ 本页/本题待处理块（只列标题，不提前讲答案）
│  ├─ 当前块
│  └─ 已覆盖 / 待处理 / 明确延后 / 非本课边界
└─ 3. 不可压缩的单步循环
   ├─ 只展开一个新教学块
   │  ├─ 概念/定义：完整呈现原文 → 分句解释
   │  ├─ 推导/证明：一次只走一个逻辑动作
   │  ├─ 例题：题意 → 学生尝试 → 讨论
   │  └─ 总结：只总结刚完成的块，不夹带下一块
   ├─ 理解确认门
   │  ├─ 学生复述、举例、作答或指出疑问
   │  └─ 答对只记理解证据，不自动授权继续
   ├─ 感受门（每次推导或总结之后必问）
   │  ├─ “这一步听起来怎么样？哪里顺、哪里卡？”
   │  └─ 有疑问 → 原地回答 → 再做理解确认与感受门
   ├─ 继续授权门（一次性）
   │  ├─ 明确“继续” → 只授权下一个教学块
   │  └─ 未明确 / 想停 / 只回答了题目 → 停在当前块
   ├─ 创造性互动（默认允许）
   │  ├─ 类比 / 替代表述 / 历史背景 / 字符图 / 学生主导分支
   │  ├─ 不得提前泄露未请求的习题答案或解法结构
   │  └─ 不得借拓展跳过教材必学块
   ├─ 额外习题（opt-in）
   │  ├─ 学生未请求 → 最多询问是否想加练，不生成实际题目
   │  ├─ 学生请求或明确同意 → 可生成并标注“教师生成补充”
   │  └─ 刚讲内容的一句理解确认不算额外习题
   ├─ 页内覆盖门（textbook）
   │  ├─ 仍有未覆盖块 → 更新课堂树，等待下一次继续授权
   │  └─ 全部块有状态 → 才能提出翻页
   ├─ 翻页门（使用新页正文之前）
   │  ├─ 展示上一页覆盖清单
   │  ├─ 宣布“翻页：PDF N / 书内 M”
   │  ├─ 展示新页课堂树
   │  ├─ 明确继续 → 进入新页第一个块
   │  └─ 未明确 → 留在旧页边界
   └─ 活动闭合门
      ├─ 还有教学块或疑问 → 回到单步循环
      └─ 全部闭合且学生确认 → 进入结课
```
<!-- /FLOW:teaching_loop -->

字符知识树必须在每个 Lesson 开始时配合学习内容概览展示；课堂流程树还须在 textbook
Lesson 开始、翻页和学生要求查看流程时展示。长课中当前分支变化后
更新简版树。理解确认、感受反馈与继续授权是三个不同的门，不得用一个“是”、一次正确作答
或会话开头的“继续学习”贯穿授权后续所有块。新 Exercise 的未授权树不得泄露方法或子目标。
开场概览和创造性暖场不计作覆盖或掌握；提示强度可以变化，对错标准不能变化。

## 图 2 · 权威链

<!-- FLOW:authority_chain -->
```text
course.md ─────────────── 课程内容、教材与教学约束
progress.md ───────────── Course 生命周期、唯一前台、精确停点
activity_ledger.md ────── Activity 生命周期、pending/CLR、alias、统计
      │
      └─ state_refresh ──→ memory / learning_path / Group view（GENERATED 缓存）

profile ───────────────── 学生稳定参数与偏好
Group plan/calendar ───── 容量、时间与结组阈值
Group review ──────────── 组合层证据
teacher overlay ───────── 课程到教师模板的当前映射

当前 Lesson / Exercise ─→ question / mistake ─→ reasoning pattern（达到证据门槛后）
activity_map ───────────→ Lesson / Exercise（同级 LearningActivity）
Exercise ─→ ExerciseProblem ─→ Attempt ─→ Review ──────┘
Engagement evidence ───────────────────────→ 外部治理系统消费或核对

冲突裁决：progress > GENERATED 缓存；外部治理事实 > T2AG 过程注释。
```
<!-- /FLOW:authority_chain -->

## 图 3 · 周期回路

<!-- FLOW:cycles -->
```text
每次会话      开课复测 ↔ 结课收割                    mistake/question
做题学习      Exercise → Attempt → Review → 台账回链          exercises/
D3 / D7       小调整；D7 兼循环复盘                   profile + Group review
每 3 循环     大调整窗口；必须留痕                    Group calendar/review
章节闭合点    陈年知识候选卷；按学生授权模式触发       mistake bank
课程结束      课程复盘与用户确认                       progress + reflections
组阈值满足    结组审查与用户确认                       Group plan/calendar/review
结构整改      三轮×三次 → 分类 → 讨论                  remediation_governance
版本发布      闸门 → 独立复审 → 用户授权 Git 快照      doctor + reports
```
<!-- /FLOW:cycles -->

## 图 5 · 皮肤系统

<!-- FLOW:skin -->
```text
main/80_interface/skin.yaml
  active: SK001
  registry.SK001: SK001_default
        │
        ▼
main/80_interface/SK001_default/skin.yaml
  id / name / welcome_msg / art_file / style
        │
        ▼
欢迎语 + art_file 指向的纯文本画面

doctor：active、registry、目录、元数据、art_file、未登记皮肤、指令词边界
批准分叉：Main/Lite 使用 Inori；Skeleton 使用默认 t2ag 字符画。
```
<!-- /FLOW:skin -->

皮肤只改变外观，不能携带教学命令或改变确认门。

## 图 6 · Git 工作流

<!-- FLOW:git -->
```text
● 触发：里程碑、发布或恢复
│
▼ git status --short + diff --check
│
◇ 存在不明改动？
│  └─ 是 ─→ 只处理本次拥有的显式路径，其余原样留下
│
▼ 审阅工作区 diff
│
◇ 发布闸门与独立复审通过？
│  └─ 否 ─→ 禁止建立正式快照
│
◇ 用户明确授权 commit？
│  └─ 否 ─→ 保持未提交；如实报告
│
▼ 显式 add → cached diff → commit
│
◇ 本批改了 Main / Skeleton 共享文件？
│  └─ 是 ─→ cmp 核对两仓字节同源，再各自 commit
│
▼ sync_lite.py --write     · 只从干净 Main 再生；脏树必被拒绝
│
◇ 需要重打包发行物？
│  └─ 是 ─→ 按最终 HEAD 重打包，排除 .git；旧包不可发
│
◇ 需要 push？
│  └─ 是 ─→ 仅展示命令，等待另行授权（RT3）
│
◉ 本地快照完成
```
<!-- /FLOW:git -->

禁止自行使用 `reset --hard`、`clean -fd` 或强推。Git 是保护层，不是课程真相源。

三发行的投影方向不对称，且都排在 commit 之后：

- **Main ↔ Skeleton** 是镜像关系。共享实现、契约与 core-playbook 必须字节同源，改完用
  `cmp` 逐一核对；Skeleton 只保留发行面差异（清零的实例、清零的 EV register、隐私豁免）。
- **Main → Lite** 是单向投影。`sync_lite.py` 在 Main 工作树脏时**拒绝执行**——把不存在于任何
  commit 的中间态投到无 git 的 Lite 不可追回。`--force` 存在但不推荐；正确顺序永远是
  先 commit，再投影。Lite 是只读审查快照，其验收是全量投影哈希，不在 Lite 内跑 doctor。

Git 证据边界分三层：

```text
evidence checkpoint ── 文件清单 / 指纹 / 测试 / WARN；不要求 Git
recovery checkpoint ── 有界授权的本地中间 commit；只提供恢复能力
release snapshot ───── 完整候选复审 + finalization delta 独立复审绑定的最终 HEAD/tree
```

三者不可互换，`clean ≠ reviewed ≠ released`。默认仍逐次授权；冻结且列举的
`version_campaign` envelope 只能连续覆盖其中的有限 RT1/RT2 checkpoint。push、tag、真实
migration apply、terminal lifecycle 和其他 RT3 不由普通 campaign Git 计划推出。

有界 finalization 使用固定序列：operator stage 精确 allowlist → 独立 reviewer 预审
`expected tree` → operator commit 同一 tree → reviewer 核对 parent/tree/diff → 最后生成不可变
外部报告。PASS 不回写目标仓或施工报告。

## 图 7 · 批次整改治理

<!-- FLOW:batch -->
```text
● 登记可复现事实与现行契约
│
▼ 分类：FAIL / REVIEW / WARN / WAIVED
│
◇ 需要整改？
│  └─ 否 ─→ 直接进入「记录证据」
│
├─ 整改轮（一轮最多三次有实质差异的尝试）
│  │
│  ◇ 本轮收敛？
│  │  └─ 是 ─→ 出环，记录证据
│  │
│  ◇ 已完成三轮？
│  ├─ 否 ─→ 依据新证据重新分类 ─→ 回本轮开头
│  └─ 是 ─→ 停止硬凑：分离事实、推断与需求
│           └─→ 与需求提出者讨论变更或撤回（不再自行尝试）
│
▼ 记录证据与验证结果
▼ 完整闸门 + 独立复审
│
◇ 通过？
│  └─ 否 ─→ 返回整改；严重度不自动上升
│
◉ 等待用户授权快照
```
<!-- /FLOW:batch -->

硬发布门不能 waiver；只有不影响仓内正确性的外部环境问题可记录正式 waiver。

批次调度先选择 `execution_mode`：`independent_batch` 是默认；`version_campaign` 只有在用户
批准包含 campaign ID、版本、基线、included/deferred scope、仓/路径/操作、risk tier、Git
计划、RT3 保留项和失效条件的 envelope 后生效。普通单元跑定向测试；RT2 风险边界、跨发行
同步和最终候选跑完整 Doctor。范围扩张、未知仓/路径、风险升级、未知 FAIL/WARN 或无法证明
影响闭包时立即停手。

首次版本候选必须完整独立复审。后续 finding 只有在输入 manifest 未变且影响闭包可证明时，
才可进入 delta re-review；仍须重跑 Doctor、state、migration、journal、Main/Skeleton 同源、
Lite 投影与最终源指纹等不可分割全局门。

## 图 8 · 习题证据闭环

<!-- FLOW:exercise_loop -->
```text
● activity_map           · ContentGroup 连接同级 Lesson / Exercise
│
▼ problems.md            · 稳定题目与教材来源（含 artifact 路径与 SHA）
▼ exerciseNN/exercise.md · 创建或恢复；保存做题停点与证据指针
▼ 学生一次真实提交批次
│
◇ 作答模式
├─ text  ─→ attempt.md 逐题正文
├─ image ─→ assets 保留原图
└─ mixed ─→ 正文 + 原图
│
▼ 创建 ATdddd            · 引用本单元题目，不新造题
▼ 逐题批改
▼ 创建 RVdddd            · 引用真实 Attempt
│
◇ 逐题结果
├─ correct            ─→ 保留证据
├─ partial/incorrect  ─→ 写回 mistake bank
└─ unresolved         ─→ 写回 question bank
│
▼ 重复思路至少跨题两次
│
◇ 达到模式门槛？
│  └─ 是 ─→ 更新 reasoning_patterns
│
▼ 更新 problems、exercise.md 与 progress
▼ 想法满足门槛则进入复利回路
│
◉ session close + doctor
```
<!-- /FLOW:exercise_loop -->

图片是原始证据；本版不伪装实现 OCR 置信度或学生转写确认状态机。

## 维护约定

1. 本文件是视图；与权威冲突时修图。
2. 九个 FLOW ID 必须唯一、开闭配对，并由 doctor 校验；改 ID 集合须同步
   `t2ag_doctor.py` 的 `EXPECTED_FLOWS`。
3. 每个 FLOW 块必须是 ```text 字符图。`build_guide.py` 遇到 ```mermaid 直接报错退出，
   因为指南侧已无渲染层——报错比静默产出一张丑图好。
4. HTML 指南由 `build_guide.py` 生成静态 SVG 与文本回退，不依赖公网 CDN；改完本文件
   必须在两仓各跑一次 `build_guide.py --write`，否则 doctor 会报 SVG 数量漂移。
5. Main/Skeleton 内容一致；Lite 只从 Main 再生，且只从干净树再生。
