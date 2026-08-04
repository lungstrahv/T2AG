# T2AG 0.2.0 功能流程图

**保护级别**：core-playbook

> 本文件是 `t2ag.md`、domain model 与各 playbook 的派生视图，不单独立法。
> 有分支、循环和闸门的过程使用 Mermaid；静态权威拓扑使用 ASCII。
> 每图的 `FLOW` 标记供离线 HTML 指南生成器提取，不能删除或复用。

## 图 0 · 首次启动

<!-- FLOW:first_run -->
```mermaid
flowchart TD
A(["打开目标实例"])
B["doctor + state refresh --check"]
C{"首次启动判据成立？"}
D["日常接管：进入图 1"]
E["逐项确认身份、时间、目标、基础与偏好"]
F["写 profile；可选项写未提供"]
G["确认首门 Course 与首个 Group"]
  H["建立 progress、首个 Lesson 或 Exercise 与 teacher 映射"]
I["state refresh --write + --check"]
J{"doctor 为 0 FAIL？"}
K["修复状态，不开新内容"]
L["读取 active skin；显示 welcome_msg + art_file + 版本"]
M(["进入图 1"])
A --> L
L --> B
B --> C
C -- "否" --> D
C -- "是" --> E
E --> F
F --> G
G --> H
H --> I
I --> J
J -- "否" --> K
J -- "是" --> M
```
<!-- /FLOW:first_run -->

首次判据是：profile 未初始化、仍有必填占位符，或 memory 上次课日期为 `—`。
Skeleton 不预填真实实例，也不自动创建 `.venv`、课程或 Engagement。

## 图 1 · 一次教学会话

<!-- FLOW:panorama -->
```mermaid
flowchart TD
A(["学生要求继续课程"])
B["doctor + state refresh --check"]
C{"有 FAIL？"}
D["修复状态，不开新内容"]
E["生成一次 L0：逐字摘录状态、教学契约及当前题面/必要教材窗口"]
  F["同一原始字节缓存校验 ProgressSnapshot、活动与教师路由"]
  G{"current_activity"}
  H["Lesson L1：只追加 L0 尚未包含的当前活动证据"]
  I["Exercise L1：当前题已有直接证据才追加 Attempt/Review"]
  J["L2 仅由冲突、复测、排期、历史追问或结课触发"]
  K["正课循环：见图 1b"]
  L{"结课类型"}
  M["共同强制事务：progress + 当前活动主载体 + 真实台账"]
  N{"完整结课？"}
  O["按真实触发补 reflections / reasoning / Group review"]
  P["state refresh --write + --check"]
  Q["完整 doctor；重读写入目标"]
  R(["会话闭合"])
A --> B
B --> C
C -- "是" --> D
C -- "否" --> E
E --> F
  F --> G
  G -- "lesson" --> H
  G -- "exercise" --> I
  H --> J
  I --> J
  J --> K
  K --> L
  L -- "Micro" --> M
  L -- "完整" --> M
  M --> N
  N -- "否" --> P
  N -- "是" --> O
  O --> P
  P --> Q
  Q --> R
```
<!-- /FLOW:panorama -->

Cloud 为 `paused` 时只跳过移动端投影，不跳过本地写回。课程进度只写 `progress.md`，
memory 与 learning path 都由 state refresh 生成。

## 图 1b · 正课循环

<!-- FLOW:teaching_loop -->
```mermaid
flowchart TD
  A["复用未失效的 L0；解析唯一 current_activity"]
  B{"活动类型"}
  C["Lesson：复用 L0 必要教材窗口；L1 只追加当前证据"]
  D["Exercise：复用 L0 当前题面；L1 只追加直接证据"]
  E["复杂讲解先给目录/树形地图；再推进一个可确认分支"]
  F["学生复述、举例或作答"]
  G{"出现什么？"}
  H["疑问：当场回答"]
  I{"当前能闭合？"}
  J["写 question bank，保留回收节点"]
  K["习题：四级提示梯"]
  L{"独立完成？"}
  M["提示 → 指定资料 → 完整讲解"]
  N["按当前活动保留真实作答；必要时进入 mistake"]
  O["状态信号：调节节奏，不降低标准"]
  P{"学生确认继续？"}
  Q(["进入结课"])
  A --> B
  B -- "lesson" --> C
  B -- "exercise" --> D
  C --> E
  D --> E
  E --> F
  F --> G
  G -- "疑问" --> H
  H --> I
  I -- "否" --> J
  I -- "是" --> P
  J --> P
  G -- "习题" --> K
  K --> L
  L -- "否" --> M
  L -- "是" --> P
  M --> N
  N --> P
  G -- "状态变化" --> O
  O --> P
  P -- "是" --> A
  P -- "否" --> Q
```
<!-- /FLOW:teaching_loop -->

每个概念、例题和跨节点动作等待学生确认。多块讲解的地图标明目标、对象类型、依赖关系
和当前分支，但不替代理解确认；新 Exercise 的未授权地图不得泄露方法或子目标。提示
强度可以变化，对错标准不能变化。

## 图 2 · 权威链

<!-- FLOW:authority_chain -->
```text
course.md ─────────────── 课程内容、教材与教学约束
progress.md ───────────── 当前课程进度唯一真相源
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
```mermaid
flowchart TD
A(["触发：里程碑、发布或恢复"])
B["git status --short + diff --check"]
C{"存在不明改动？"}
D["只处理本次拥有的显式路径"]
E["审阅工作区 diff"]
F{"发布闸门与独立复审通过？"}
G["禁止建立正式快照"]
H{"用户明确授权 commit？"}
I["保持未提交；如实报告"]
J["显式 add → cached diff → commit"]
K{"需要 push？"}
L["仅展示命令，等待另行授权"]
M(["本地快照完成"])
A --> B
B --> C
C -- "是" --> D
C -- "否" --> E
D --> E
E --> F
F -- "否" --> G
F -- "是" --> H
H -- "否" --> I
H -- "是" --> J
J --> K
K -- "否" --> M
K -- "是" --> L
```
<!-- /FLOW:git -->

禁止自行使用 `reset --hard`、`clean -fd` 或强推。Git 是保护层，不是课程真相源。

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
```mermaid
flowchart TD
A(["登记可复现事实与现行契约"])
B["分类：FAIL / REVIEW / WARN / WAIVED"]
C{"需要整改？"}
D["一轮最多三次有实质差异的尝试"]
E{"本轮收敛？"}
F["记录证据与验证结果"]
G{"已完成三轮？"}
H["依据新证据重新分类"]
I["停止硬凑；分离事实、推断、需求"]
J["与需求提出者讨论变更或撤回"]
K["完整闸门 + 独立复审"]
L{"通过？"}
M["返回整改；严重度不自动上升"]
N(["等待用户授权快照"])
A --> B
B --> C
C -- "否" --> F
C -- "是" --> D
D --> E
E -- "是" --> F
E -- "否" --> G
G -- "否" --> H
H --> D
G -- "是" --> I
I --> J
F --> K
K --> L
L -- "否" --> M
L -- "是" --> N
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
```mermaid
flowchart TD
Z["activity_map：ContentGroup 连接同级 Lesson / Exercise"]
A["problems.md：稳定题目与教材来源"]
T["创建/恢复 Udddd/exercise.md；保存做题停点与证据指针"]
B["学生一次真实提交批次"]
C{"作答模式"}
D["text：attempt.md 逐题正文"]
E["image：assets 保留原图"]
F["mixed：正文 + 原图"]
G["创建 ATdddd；引用本单元题目"]
H["逐题批改"]
I["创建 RVdddd；引用真实 Attempt"]
J{"逐题结果"}
K["correct：保留证据"]
L["partial/incorrect：写回 mistake"]
M["unresolved：写回 question"]
N["重复思路至少跨题两次"]
O{"达到模式门槛？"}
P["更新 reasoning_patterns"]
Q["更新 problems、exercise.md 与 progress；想法满足门槛则进入复利回路"]
R(["session close + doctor"])
Z --> A
A --> T
T --> B
B --> C
C -- "text" --> D
C -- "image" --> E
C -- "mixed" --> F
D --> G
E --> G
F --> G
G --> H
H --> I
I --> J
J -- "correct" --> K
J -- "partial/incorrect" --> L
J -- "unresolved" --> M
K --> N
L --> N
M --> N
N --> O
O -- "是" --> P
O -- "否" --> Q
P --> Q
Q --> R
```
<!-- /FLOW:exercise_loop -->

图片是原始证据；0.2.0 不伪装实现 OCR 置信度或学生转写确认状态机。

## 维护约定

1. 本文件是视图；与权威冲突时修图。
2. 九个 FLOW ID 必须唯一、开闭配对，并由 doctor 校验。
3. HTML 指南由 `build_guide.py` 生成静态 SVG 与文本回退，不依赖公网 CDN。
4. Main/Skeleton 内容一致；Lite 只从 Main 再生。
