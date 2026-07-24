# T2AG 功能流程图（t2ag_flow.md v2）

**保护级别**：core-playbook（跨发行版保留）

> 本文件回答**"系统跑起来是什么样"**，与 `t2ag.md`（规则）、`domain_model.md`（对象）、
> `pattern_retire_loop.md`（复利模式）互补。
> **规则与本图冲突时以权威文件为准，并修本图。**
> **本文件是视图，不是真相源**：任一步骤的权威描述在对应 playbook。
>
> **格式双轨（判据）**：有分支/循环/闸门的**过程** → mermaid；表达层级或权威的**静态拓扑** → ASCII（位置即语义，mermaid 自动布局做不到）。
> **提取标记**：每图以 `<!-- FLOW:xxx -->` 开始、`<!-- /FLOW:xxx -->` 结束，供 HTML 生成器按块提取。标记行勿删。

---

## 图 0 · 骨架解压与首次启动

<!-- FLOW:first_run -->
```mermaid
flowchart TD
    A[T2AG-skeleton 解压到目标目录] --> B[👤 人类前置<br/>不在 skeleton 源目录写学生数据<br/>用 AI 环境打开目标目录]
    B --> C{首次判定<br/>memory 摘要日期为空<br/>且 SN01 仍指向 S001?}
    C -->|否| D[非首次<br/>走 t2ag.md 4.2 + lesson_recover]
    C -->|是| E[步骤1 读宪法 t2ag.md 五章]

    E --> F[步骤2 检测 AI 环境<br/>只生成当前入口，不全生成]
    F --> G[步骤3 doctor 基线<br/>0 FAIL]
    G --> H[🔒 步骤4 询问用户 5 问<br/>一问一答 · 复述确认再建档]
    H --> I[步骤5 创建实际档案]

    I --> I1[5a 学生<br/>S001→S002 四文件<br/>SN01 改指向 · 索引加行]
    I1 --> I2[5b 课程<br/>每门课完整跑 new_course_init]
    I2 --> I2A[CourseDefinition<br/>30_course_definitions/&lt;id&gt;_&lt;Name&gt;/]
    I2 --> I2B[CourseRun<br/>35_course_runs/&lt;case&gt;/CR-&lt;case&gt;-&lt;id&gt;/<br/>含 course_status 真相源]
    I2A --> I3
    I2B --> I3[state_refresh --write<br/>生成 course_info 缓存]
    I3 --> I4[5c 配置<br/>overlay · t2ag_case · memory 指针]
    I4 --> I5[5d 实例化判据<br/>SN01≠S001 且摘要非空<br/>→ 已是基础实例]

    I5 --> J[步骤6 再跑 doctor<br/>0 FAIL · WARN 逐条评估]
    J --> K[步骤7 展示欢迎<br/>见图 5 皮肤数据流]
    K --> L([进入日常：见图 1])

    M[⛔ 禁止：新建混装 30_courses/]

    style B fill:#3d2a4a,color:#fff
    style H fill:#4a3d1a,color:#fff
    style I2B fill:#4a2d2d,color:#fff
    style M fill:#5a2a2a,color:#fff
```
<!-- /FLOW:first_run -->

> **agent 职责 = 填充内容，不是创建目录**（骨架已预建全部容器）。
> 现顶层结构：`00_core` `10_case` `12_activity_records` `15_curricula` `20_groups` `25_general`（冻结）`30_course_definitions` `35_course_runs` `40_field_practices` `50_playbook` `60_journal` `70_tools` `skin` `cloud` `bin`。
> （`30_courses/` 仅空壳兼容，待 M5 拆除；`40_practices/` 已退场。）

---

## 图 1 · 一次教学会话的完整生命周期

<!-- FLOW:panorama -->
```mermaid
flowchart TD
    START([学生：继续学 XXX]) --> R1[步骤1 读 memory<br/>获取当前状态指针]
    R1 --> R15{有 active<br/>课堂交接?}
    R15 -->|是| R15A[步骤1.5 条件读取交接]
    R15 -->|否| R2
    R15A --> R2[步骤2 读 course_status<br/>当前进度 ← 真相源]

    R2 --> R25[步骤2.5 读 question_bank]
    R25 --> R3[步骤3 读 lessonXX 最后记录]
    R3 --> R4[步骤4 读学生四文件档案<br/>据此调整语气与节奏]
    R4 --> R5[步骤5 读 working_pages<br/>恢复教材上下文]

    R5 --> R55{上次是<br/>micro close?}
    R55 -->|是| R55A[步骤5.5 静默补齐<br/>错题收割 · 缓存刷新]
    R55 -->|否| R6
    R55A --> R6[步骤6 跑 doctor]

    R6 --> R6A{◆ 抽查预算<br/>按上次推进量分档}
    R6A -->|少/中/多| Q[1 / 2 / 3 题]
    R6A -->|学生跳过| QS[无惩罚跳过<br/>连续3次→嵌入式确认]
    Q --> R7
    QS --> R7[步骤7 确认<br/>上次讲到 XXX，继续?]

    R7 --> TEACH[[正课循环<br/>详见图 1b]]
    TEACH --> CLOSE{结课方式?}

    CLOSE -->|完整| C1[步骤1 更新 course_status ← 真相源]
    CLOSE -->|◆ 状态不佳/短课| MICRO[Micro close<br/>①精确停点 + close_type: micro<br/>②memory 一行]
    CLOSE -->|云端会话| CLOUD[云端只读分支<br/>不写本地真相源]

    MICRO --> MEND([整理顺延至下次开课])
    CLOUD --> CEND([生成回写指令<br/>待本地裁决])

    C1 --> C15[步骤1.5 核对 question_bank]
    C15 --> C2[步骤2 收割错误 → mistake_bank]
    C2 --> C3[步骤3 学生状态写回]
    C3 --> C4[步骤4 刷新 memory 缓存]
    C4 --> C5[步骤5 刷新 course_info 缓存]
    C5 --> C6[步骤6 working_pages 窗口处理]
    C6 --> C7[步骤7 课后提炼检查]
    C7 --> C75[步骤7.5 关闭匹配的课堂交接]
    C75 --> C8[🔒 步骤8 输出写入确认<br/>必须展示给学生]
    C8 --> C9[步骤9 Git 存档<br/>详见图 6]
    C9 --> END([下次开课从 memory 指针接续])

    MEND -.下次开课.-> START
    END -.下次开课.-> START
    CEND -.本地裁决后.-> START

    style R55A fill:#3a3a3a,color:#fff
    style QS fill:#4a3d1a,color:#fff
    style MICRO fill:#2d4a3d,color:#fff
    style CLOUD fill:#2d3d4a,color:#fff
    style C8 fill:#4a3d1a,color:#fff
    style C1 fill:#4a2d2d,color:#fff
    style R2 fill:#4a2d2d,color:#fff
```
<!-- /FLOW:panorama -->

> **中断兜底**：仪式没走完 → 下次开课 doctor 必报不一致。
> **三条设计原则的可视化**：红色两格＝`course_status` 唯一真相源（一读一写）｜Micro close 是一等分支不是例外（"五分钟也算数"）｜跳过无惩罚但连续 3 次触发确认（弹性有底）。

---

## 图 1b · 正课循环内部（教学法）

<!-- FLOW:teaching_loop -->
```mermaid
flowchart TD
    A[working_pages 读教材原文] --> B[讲解]
    B --> C[学生复述 + 举正反例]
    C --> D{出现什么?}

    D -->|疑问| E[必答]
    E --> E1{答得动?}
    E1 -->|是| C
    E1 -->|否| E2[记入 question_bank<br/>待销账，不装懂]
    E2 --> C

    D -->|习题| F[四级梯子]
    F --> F1[① 自己想]
    F1 -->|卡住| F2[② 给提示]
    F2 -->|仍卡| F3[③ 查讲义]
    F3 -->|仍卡| F4[④ 全讲]
    F4 --> F5[该题标记<br/>待入 mistake_bank]
    F1 -->|通过| C
    F2 -->|通过| C
    F3 -->|通过| C
    F5 --> C

    D -->|情绪触发词| G[标记待写学生状态档<br/>⛔ 红线：调节奏，不降标准]
    G --> C

    D -->|自然结束/下课| H([进入结课，回图 1])

    style E2 fill:#2d3d4a,color:#fff
    style F5 fill:#4a2d2d,color:#fff
    style G fill:#5a2a2a,color:#fff
```
<!-- /FLOW:teaching_loop -->

> 四级梯子的意义：**第 4 级被触发本身就是信号**——该题必入错题库，因为学生独立走不完。
> 疑问答不动时记入 `question_bank` 待销账，而不是含糊带过——这条是台账机制的入口（见 `pattern_retire_loop.md` 部件节）。

---

## 图 2 · 权威链数据流（谁是源，谁是缓存）

<!-- FLOW:authority_chain -->
```text
                    结课仪式步骤1（唯一人工写入口）
                              │
                              ▼
        ┌──── course_status.md（真相源 / 每个 CourseRun 一份）────┐
        │  35_course_runs/<case>/CR-<case>-<id>/course_status.md   │
        │  只在结课时写；任何冲突一切以它为准                       │
        └──────────┬─────────────────────────────┬────────────────┘
                   │                             │
          仪式步骤4 │                             │ 仪式步骤5
                   ▼                             ▼
        memory 指针/速览（缓存）        course_info 进度列（缓存）
        00_core/t2ag_memory.md          10_case/course_info.md
                   │                             ▲
                   │                             │ state_refresh --write
                   │                             │ （机器写，GENERATED 块）
          开课步骤1 │                    ┌────────┴────────┐
              被读取 │                    │ 块内永不手写      │
                   ▼                    │ 块外永不脚本改    │
              doctor 校验三级一致 ────────┴─────────────────┘
              （不一致 = 上次仪式未走完）

  ── 旁路数据流（各自独立的复利回路，见 pattern_retire_loop.md）──

  lesson 错误 ──仪式步骤2──→ mistake_bank ──开课步骤6──→ 抽查复测
  课堂疑问   ──随时────────→ question_bank ─开课步骤2.5─→ 销账
                                    └──集合层沉淀──→ reasoning_patterns（积累）
  工具故障   ──随时────────→ problemlog ────→ 修 playbook / 工具
  情绪触发词 ──仪式步骤3──→ students 档案 ──开课步骤4──→ 调节奏语气
  真实行动   ──随时────────→ FieldPractice evidence ──→ Praxis 课程消费
```
<!-- /FLOW:authority_chain -->

> **为什么这张图用 ASCII**：源在中、缓存在下、旁路横走——**位置即语义**，"谁是源"不靠读标签靠看位置。这是 mermaid 自动布局做不到的。

---

## 图 3 · 周期性回路（会话之外的心跳）

<!-- FLOW:cycles -->
```text
频率          回路                                          载体
────────────────────────────────────────────────────────────────────────
每次会话      开课抽查 ←──→ 结课收割                        mistake_bank
              （衰减型复利回路，日频）

随时          疑问记入 ──→ 销账 ──→ 集合层沉淀              question_bank
              （台账 → 积累型回路）                          → reasoning_patterns

按执行参数    小调整 / 循环复盘 → 五问自查                   G 组文件
              （防方案漂移）

每月末+20min  交易月复盘 → 归因标签统计 → 改交易系统         FP-S002-0001
              （衰减型，事前存证）

每月          memory「长期事实」节淘汰                       t2ag_memory.md
              （三周未用 → 下沉留痕）

大调整/期末   课程组评估 → 结组仪式 → 归档 G01 → 建 G02      20_groups/

里程碑末      环境重建验证（按需，非默认删 .venv）           .venv / .tools

版本变更      规则修改 → changelog → memory「最近变更」同步  00_core/

结构批次      工单 → 执行 → 报告 → 复审 → commit            见图 7
```
<!-- /FLOW:cycles -->

---

## 图 5 · 皮肤系统数据流（外观层，非教学层）

<!-- FLOW:skin -->
```text
  skin/skin.yaml（全局配置）
    │  active: SK001
    │  registry.SK001: SK001_default
    ▼
  skin/SK001_default/skin.yaml（皮肤元数据）
    │  welcome_msg / art_file / style
    ▼
  输出：欢迎语 + ASCII 艺术画面        ← first_run 步骤7 / 首次会话

  doctor check_skin_system（七条）
  ┌───────────────────────────────────────────┬──────┐
  │ 无全局 skin.yaml（未初始化）              │ WARN │
  │ 缺 active                                 │ FAIL │
  │ active 未在 registry.*                    │ FAIL │
  │ 文件夹或皮肤 skin.yaml 不存在             │ FAIL │
  │ art_file 指向文件不存在                   │ FAIL │
  │ SK* 目录未登记 registry                   │ WARN │
  │ welcome_msg 含指令词（必须/规则/禁止…）   │ WARN │  ← 防外观后门
  └───────────────────────────────────────────┴──────┘

  注：main 与 skeleton 的 art_file 允许分叉（骨架默认欢迎图 vs 主实例个人 art），
      属 H4 期望分叉清单登记项，非漂移。
```
<!-- /FLOW:skin -->

> 最后一条检查值得单说：**皮肤是外观，不得携带指令**——`welcome_msg` 里出现"必须/规则/进度/禁止"等词即 WARN，防止有人（或某个模型）借外观层夹带行为指令。

---

## 图 6 · Git 工作流

<!-- FLOW:git -->
```mermaid
flowchart TD
    A[触发：结课 / 里程碑 / 发布 / 恢复] --> B{在 Git 仓库内?}
    B -->|否| C[disabled<br/>跳过并如实报告]
    C --> Z([教学写回照常完成])

    B -->|是| D{有远端且本次联网?}
    D -->|否| E[local 模式]
    D -->|是| F[remote 模式]
    E --> G[git status --short<br/>git diff --check]
    F --> G
    G --> H[git diff -- 显式路径<br/>路径来自写入确认，不猜]
    H --> I{工作区有不明改动?}
    I -->|是| J[⛔ 不暂存不还原<br/>只处理本次拥有的文件]
    J --> H
    I -->|否| K[git add -- 显式路径]
    K --> L[git diff --cached]
    L --> M{混入无关内容?}
    M -->|是| N[git restore --staged<br/>不改工作区]
    N -.重来.-> H
    M -->|否| O[🔒 本次明确授权<br/>不接受持续授权]
    O --> P[git commit -m 对象+实际变化]
    P --> Q{需远端同步?}
    Q -->|否| R([本地存档完成])
    Q -->|是| S[agent 只展示命令]
    S --> T[👤 学生手动执行 push]
    T --> U[commit 与上传结果<br/>分开记录]
    U --> R

    V[恢复请求] --> W[git log / show<br/>先展示目标版本]
    W --> X[🔒 学生确认]
    X --> Y[git restore --source<br/>→ add → commit]
    Y --> AA[恢复做成新 commit<br/>保留完整审计链]

    style C fill:#2d3d4a,color:#fff
    style J fill:#5a2a2a,color:#fff
    style O fill:#4a3d1a,color:#fff
    style X fill:#4a3d1a,color:#fff
    style T fill:#3d2a4a,color:#fff
```
<!-- /FLOW:git -->

> **三条永不出现在图上的命令**：`git reset --hard`｜`git clean -fd`｜`git push --force`——agent 禁止自行使用，冲突与历史改写一律停下说明。
> **核心不变式**：Git 是保护层不是真相源。disabled / 无网络 / 无快照都不阻断开课、教学写回或结课。

---

## 图 7 · 批次治理流程（系统自身的修改流程）

<!-- FLOW:batch -->
```mermaid
flowchart TD
    A[出单方：编写施工单] --> B{批次分类}
    B -->|审计批·只读| C[无落盘前置<br/>随时可开工]
    B -->|追加批| D{上批已 commit?}
    B -->|修改批| E{上批已 commit<br/>且最近审计通过?}
    D -->|否| STOP1[⛔ 不开工，先落盘]
    E -->|否| STOP1
    C --> F[执行方开工]
    D -->|是| F
    E -->|是| F

    F --> G{遇到闸门?}
    G -->|内容裁决| H[🔒 出差异报告<br/>等学生批准]
    G -->|结构裁决| I[按单执行]
    H --> I
    I --> J{每步跑 doctor}
    J -->|未预告 FAIL/WARN| STOP2[⛔ 停手，贴原文报告]
    J -->|通过| K{还有步骤?}
    K -->|是| I
    K -->|否| L[收口 grep 逐类归因]

    L --> M[写施工报告]
    M --> N[/双偏离字段<br/>范围偏离 · 执行偏离/]
    N --> O[/WARN 逐条指名附原文/]
    O --> P[/三版哈希全量列举/]
    P --> Q[复审方独立核对]
    Q -->|偏离字段为空却发现偏离| R[⛔ 打回<br/>不论偏离是否合理]
    Q -->|WARN 未指名| R
    R -.补正.-> M
    Q -->|通过| S[🔒 学生亲手 commit]
    S --> T{lite 需同步?}
    T -->|是| U[sync_lite<br/>干净树闸门校验]
    T -->|否| V[批次关闭]
    U --> V
    V --> W[/changelog + EV 回填<br/>+ skeleton 同步/]
    W --> X([下一批可开工])

    style STOP1 fill:#5a2a2a,color:#fff
    style STOP2 fill:#5a2a2a,color:#fff
    style R fill:#5a2a2a,color:#fff
    style H fill:#4a3d1a,color:#fff
    style S fill:#4a3d1a,color:#fff
    style U fill:#4a3d1a,color:#fff
```
<!-- /FLOW:batch -->

> 细则见 `50_playbook/batch_workorder_spec.md`。
> **打回条件的设计意图**：让诚实声明成为成本最低的选项——偏离几乎总有好理由，静默才是问题。

---

## 角色视角速查

| 角色 | 负责 |
|---|---|
| **学生** | 说"继续学 X" / 提问 / 说"下课" / 内容裁决与授权 / 亲手 commit |
| **agent** | 图 0 首次启动 + 图 1、1b 全流程 + 图 3 中除学生评价外的一切 |
| **doctor** | 图 2 一致性 + memory 节预算 + 断链 + venv/env + 版本号 + 图 5 皮肤七检 |
| **文件** | 记住一切——**agent 可以换，图 0–7 不变** |

---

## 维护约定

1. **本图是视图**：与权威文件冲突时改本图，不改权威文件；
2. **提取标记勿删**：`<!-- FLOW:xxx -->` 供 HTML 生成器按块提取，删除会导致 guide 页面缺块；
3. **数字勿写死**：不再写"15 个 playbook""9 个文件"等会过期的计数（旧版教训）；
4. **图号即成稿**：changelog 曾记"图 6 含子型分流"，删除前最终文件实际只有图 0–5，属登记与现实脱节；**v2 以本文件实际图号为准**（0、1、1b、2、3、5、6、7；无图 4，其内容并入"角色视角速查"）。
