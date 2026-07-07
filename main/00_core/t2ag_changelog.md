# T2AG 变更历史

> 按需展开。启动时不全量读，由 t2ag_memory.md 的「最近变更摘要」按行号指针索引。
> 追加条目时同步更新 memory 摘要，并对超出 memory 节预算的旧条目做"下沉"处理。

---
---
---

## [2026-07-08] v0.0.06 20_groups 整治 + 大小写修复 + T2AG-lite

- **20_groups 整治**：
  - 新增 `20_groups/_README.md`：指针说明 + 目录结构 + 方案 overlay 定位
  - G01.md 头部新增指针声明和方案 overlay 引用列表
  - G02.md 头部新增指针声明和方案 overlay 引用列表
  - plan_v2_4h.md / plan_v3.md / plan_313.md / plan_v4.md 头部新增 overlay 层声明
  - 方案层 = 课程组的 overlay：Gxx.md 定义"做什么"，plan_*.md 定义"怎么做"
- **大小写修复**（11 处）：
  - 主项目 README.md：`T2AG.md` → `t2ag.md`，`T2AG_skeleton` → `T2AG-skeleton`
  - skeleton README.md：`T2AG.md` → `t2ag.md`
  - skeleton AGENTS.md：全面重写，修复 5 处大小写引用
- **T2AG-lite 生成**：去除库/教材/生成程序的轻量版，放入工作区

---

## [2026-07-08] v0.0.06 功能完备化：skin 系统 + skeleton 预建 + core-playbook 提升

- **git_workflow.md → core-playbook**：保护级别从 normal 提升为 core-playbook
- **skin 系统升级**：
  - 新增 `skin/skin.yaml`（全局配置，扁平 YAML 零依赖）
  - 新增 `skin/SK001_default/skin.yaml`（皮肤元数据）
  - 艺术文件迁移至 `SK001_default/` 子目录
  - 新增 `50_playbook/skin_playbook.md`（core-playbook：创建/切换/校验/纪律）
  - doctor 新增 3 项皮肤检查（active 存在/艺术文件存在/未登记 WARN）
  - t2ag.md 结构清单新增皮肤系统和皮肤管理两行
  - first_run.md 步骤 7 改用 skin.yaml 读取逻辑
  - t2ag_flow.md 新增图 0（骨架结构）和图 5（皮肤数据流）
- **skeleton 功能完备化**：
  - 预建 `20_groups/`、`30_courses/`、`40_practices/` 目录 + `_README.md` 说明文件
  - first_run.md 更新：agent 职责从"创建目录"改为"填充内容"
  - doctor 豁免逻辑更新：检查 G*.md 文件存在而非目录存在
- **Hermes 引用清除**：playbook_management.md / journal_management.md / memory / journal INDEX 移除 Hermes 来源引用
- **doctor 验证**：主项目 0 FAIL 0 WARN；skeleton 0 FAIL 1 WARN（预期）

---

## [2026-07-08] v0.0.06 全局改名 + 文件夹重构 + skeleton 整治

- **全局改名 T2AC → T2AG**：所有文件名（t2ac.md → t2ag.md 等 9 个/仓）、文件内容、路径引用统一为 T2AG
- **版本号**：0.0.05 → 0.0.06（AGENTS / README / t2ag.md / doctor 一致性检查通过）
- **文件夹重构**：`C:\Users\MikeChen\T2AC\` 为工作区根，内含 `T2AG\`（主项目）+ `T2AG-skeleton\`（骨架，独立 git 仓）
- **skin 文件夹**：welpic → skin，文件加编号（01_welcome.txt 等），创建 README 索引
- **skeleton 整治**：
  - 补缺失 playbook 文件（exam_protocol / exam_bank_spec / lesson_recover / ocr_correct_flow）
  - 清理数据污染（changelog / git_workflow / course_group_rules / pattern_retire_loop 去实例化）
  - 删除空目录（20_groups / 30_courses / 40_practices——首次启动时创建）
  - 修路径前缀 bug（50_50_ → 50_ 等）
  - 修 doctor 豁免逻辑：空 20_groups 目录 → WARN 而非 FAIL
  - 修 doctor 文件名大小写（t2ag.md → t2ag.md，跨平台兼容）
- **doctor 验证**：主项目 0 FAIL 0 WARN；skeleton 0 FAIL 1 WARN（空 20_groups 预期 WARN）
---

## [2026-07-07] 产品改名 T2AC → T2AG + skeleton 分仓 + 项目日程表

- **产品改名**：T2AC → T2AG（公开名），内部代号统一为 T2AG（文件命名沿用 t2ag.*）
- 全称：T2AG by T2AG——T2AG 是产品名，T2AG 是系统代号（v0.0.06 起统一为 T2AG）
- 改名范围：README/AGENTS/t2ag.md 头部/git_workflow.md 示例文本
- v0.0.06 追加：文件名（t2ac.md → t2ag.md 等）、文件夹路径全部统一为 T2AG
- **skeleton 分仓**：T2AG_skeleton 移出主仓 → `C:\Users\MikeChen\T2AG-skeleton\`，独立 git init
  - 理由：主仓 Private（学生档案）× skeleton 将来 Public（分发资产）= 可见性冲突，物理隔离
  - 同步纪律：主仓结构性变更当天同步 skeleton 仓并打相同版本 tag
- **项目日程表**：新增 `00_core/project_schedule.md`——向前看路线图（版本/课程组/里程碑/系统节点/公开前审计清单）
- t2ag.md 结构清单登记 project_schedule.md
---

## [2026-07-07] Git 操作手册入库 + 仓库初始化

- 新增 `50_playbook/git_workflow.md`：12 命令最小集（日常 3 条 + 安全后悔药 3 种 + 灾难恢复），reset --hard / push --force 明文禁止
- 两处引用挂钩：PY1001 M0 验收项加「git 仓库建好」；session_close 新增第九步「Git 存档」引用第三节
- t2ag.md 结构清单登记
- 按第一节执行仓库初始化，首个 commit = 系统第一张正式快照
---

## [2026-07-07] 项目线验证 v1.1 定稿

- 新增 `50_playbook/project_verification.md`：模式 A（产品验收五步）+ 模式 B（评测机型对账）+ M 级绑定规则 + doctor 四检
- `00_core/course_group_rules.md` 第三节加项目线验证条款（宪法级一句话）
- t2ag.md 结构清单登记
- 前两份旧文件（project_rules / project_rules_amendment）未找到，无需废止
---

## [2026-07-07] 考试子系统 v1.0 定稿

- 新增 `00_core/exam_rules_final.md`：考试规则总纲（题库时间线+小测开场语+mistake变形+规则总表）
- 真题源限定 2018 年及以后
- 所有小测开始时展示：「考试不为制造痛苦，选择学习的人，应该知道自己学会了没有。」
- `50_playbook/exam_protocol.md` 和 `exam_bank_spec.md` 保留为细则，冲突旧条款废弃
- t2ag.md 结构清单登记
---

## [2026-07-07] 题库存储与考前检查规范入库

**变更概述**：为语言线卷面考核补充物理题库存储、题级登记和考前机械检查规范。

### 新增

- `50_playbook/exam_bank_spec.md`：规定 `_exam/index.md`、`papers/[卷ID]/paper.pdf`、`solution.pdf`、`meta.md` 结构；池别是登记表元数据，不搬文件

### 修改

- `50_playbook/exam_protocol.md`：题库建设部分改为引用 `exam_bank_spec.md`
- `t2ag.md` 第三章：登记 `50_playbook/exam_bank_spec.md`
- `00_core/course_group_rules.md`：doctor 检查项补充题号隔离和 meta 完整性 WARN
- `70_tools/t2ag_doctor.py`：新增 `papers/` 卷夹未登记、`meta.md` 缺列/缺解答页码 WARN；考核池卷题号出现在 lesson/practice 中 FAIL

---

## [2026-07-07] 语言线卷面考核协议入库

**变更概述**：将语言线考核从待讨论的神经测得方向，落为真题选编式卷面考核协议。

### 新增

- `50_playbook/exam_protocol.md`：规定“选编，不生成”、题库建设、练习池/考核池隔离、机械组卷、评分阈值和循环级小测

### 修改

- `00_core/course_group_rules.md`：语言线验收改为卷面 70% + 过程指标 30%，并引用 exam_protocol；保留执行参数化和 S001 3-1-3 默认
- `10_case/students/S001/basic_info.md`：同步默认 3-1-3、每周两小调/四周一大调、语言线卷面考核默认
- `10_case/students/S002/basic_info.md`：加入 S002 卷源范围、语言规则、权重与隔离规则
- `70_tools/t2ag_doctor.py`：新增考核池隔离检查；考核池卷目文件名出现在 lesson/practice 文件即 FAIL
- `t2ag.md` 第三章：登记 `50_playbook/exam_protocol.md`
- `20_groups/G01.md`、`20_groups/plan_313.md`：语言线评估改为引用 exam_protocol

---

## [2026-07-07] G01 执行参数化与 3-1-3 节奏接入

**变更概述**：将课程组调整机制参数化，区分 S001 模板默认值与 S002 实例参数；语言线考核后续由 exam_protocol 定稿。

### 修改

- `00_core/course_group_rules.md`：协议层只规定机制；S001 默认改为每周两次小调整、每四周一次大调整
- `20_groups/plan_313.md`：新增 3-1-3 节奏容器（块 A 输入、D4 休息、块 B 整合）
- `20_groups/G01.md`：执行方案改为 `plan_v3.md` 里程碑表 + `plan_313.md` 节奏容器；周复盘改为 D7 循环复盘
- `10_case/students/S002/basic_info.md`：新增「执行参数（S002）」节，记录 3-1-3、小调整、大调整、配方级边界
- `20_groups/plan_v2_4h.md`、`20_groups/plan_v3.md`、`00_core/t2ag_flow.md`、`10_case/course_info.md`、`10_case/t2ag_case.md`：清理旧的周日 / 期中硬编码表述
- `00_core/t2ag_memory.md`：刷新最近变更摘要，并修正当前学生、教师与版本缓存

---

## [2026-07-07] 课程识别与课程组规则入库

**变更概述**：解决 S002 档案与课程组的引用冲突，建立课程识别唯一真相源，固化课程组运行规则。

### 新增文件

- `00_core/course_group_rules.md`（宪法附件）：六节——状态枚举、引用纪律、双线性质、刚性/流动边界、换组仪式指针、doctor 增检四条
- `50_playbook/group_transition.md`（core-playbook）：换组仪式五步 + 预划表 ≠ 组文件注释

### 修改

- `t2ag.md` 第三章结构清单：登记 course_group_rules.md + group_transition.md
- `S002/basic_info.md`：「当前课程」枚举清单 → 纯指针「见 memory 指针」
- `course_info.md`：课程列表加状态列（CS1953=paused, MATH1607H/PY1001=active, IV1001=planned）
- `G01.md`：加显式 `状态：active` 字段
- `t2ag_memory.md`：加活跃课程组指针（G01）
- `t2ag_problemlog.md`：永久定律入档——凡手写两遍的信息必然不一致
- `t2ag_doctor.py`：新增 `check_course_group_rules()`（组文件状态/memory 指针/active 课程一致性/枚举清单 WARN）

### 数据修正

- CS1953 状态从 active 改为 paused（不在 G01 成员表中）
- G01 成员 = MATH1607H + PY1001，CS1953 和 IV1001 不在当前组

### 同步

- T2AG_skeleton 同步更新（course_group_rules.md + group_transition.md + doctor + changelog）
---

## [2026-07-07] playbook 三级保护体系

**变更概述**：将原有"核心 playbook"概念升级为三级体系：meta-playbook > core-playbook > 普通。

### 三级定义

- **meta-playbook**（最高级）：管理其他 playbook/journal/memory/problemlog 生命周期的 playbook，是"管理 playbook 的 playbook"
- **core-playbook**（高级）：高价值长期保留的具体流程，不可自动归档或合并
- **普通 playbook**：常规流程，可被合并/归档/重写

### 标记实例

| 文件 | 级别 | 理由 |
|---|---|---|
| playbook_management.md | meta-playbook | 管理其他 playbook 的创建/保护/清理 |
| problemlog_maintenance.md | meta-playbook | 管理 problemlog → playbook 升级流程 |
| journal_management.md | meta-playbook | 管理 journal 写入规则与分流 |
| first_run.md | core-playbook | 系统初始化入口流程 |

### 文件变更

- `playbook_management.md` 第四章重写为三级体系定义
- 4 个文件顶部加 `**保护级别**` 声明
- T2AG_skeleton 同步更新
---

## [2026-07-07] 首次启动流程明确化

**变更概述**：解决"agent 进入 skeleton 文件夹后如何初始化"的模糊问题。

### 新增

- `50_playbook/first_run.md`：agent 首次启动操作手册（7 步：读宪法→检测环境→跑 doctor→询问用户→创建档案→验证→欢迎信息）
- 首次启动判断条件：memory「上次课摘要」为空 OR SN01 仍指向 S001

### 增强

- `AGENTS.md`：新增「首次启动判断」节，指向 first_run.md（pin 效果——TRAE 自动读 AGENTS.md 时即触发）
- `README.md`：快速开始从三句话扩展为三步详细指引（解压→打开→发指令），含各 AI 环境差异说明
- `t2ag.md` 第三章结构清单：登记 first_run.md

### 同步

- T2AG_skeleton 同步更新（AGENTS.md 路径为通用 `<解压目标路径>`，T2AG 主项目为具体路径）
---

## [2026-07-07] README 边界清理

**变更概述**：清理 README 中两处 0.1.0 遗留话术，使 README 与 t2ag.md 宪法版定位一致。

- `00_core/` 描述：`种子规则` → `宪法`（与 t2ag.md 0.0.06 五章结构一致）
- 删除结尾 `> 本骨架采用数字前缀命名规范，旧版扁平命名已废弃。`（0.1.0 迁移期话术，宪法版不需要再提旧版）
- 确认 README 与 t2ag.md 不合并：README 管入门（介绍+快速开始+目录树），t2ag.md 管规则（宪法+结构清单+修宪程序），互相只留指针，零重叠正文
- T2AG_skeleton 同步更新

---

## [2026-07-07] T2AG_lite 改名为 T2AG_skeleton

**变更概述**：T2AG_lite 改名为 T2AG_skeleton，与上传的 v0.0.06 命名一致。

- 改名原因：skeleton 是骨架/种子的标准称谓，lite 暗示"功能阉割版"语义不准
- 33 个文件完好，含 t2ag_flow.md 和 pattern_retire_loop.md 等全部新增内容
- 路径：`C:\Users\MikeChen\T2AG\T2AG_skeleton`

---

## [2026-07-07] 0.0.06 — skeleton v0.0.06 合并落地

**变更概述**：将上传的 T2AG_skeleton v0.0.06 合并到 T2AG_skeleton 和 T2AG 主项目。

### t2ag.md 宪法化

- t2ag.md 从"种子文件"升级为"宪法+结构清单"（五章结构，各章 [max N] 预算，总额400行）
- 第三章结构清单：每个部件一行登记（名称/路径/职能/定义/检查），先登记后创建
- 第五章修宪程序：改宪法须 changelog 大版本 + doctor 验证
- 防复辟机制：模板/流程正文回流 t2ag.md = 复辟，行数上限阻止

### doctor 增强

- 新增 check_constitution_budget()：t2ag.md 分章预算检查
- 新增 check_manifest_registration()：仓库有而清单无则 WARN（防漂移）

### 文档同步

- AGENTS.md / README.md 版本号统一至 0.0.06
- README.md 数字前缀编号修正（20_groups / 30_courses / 40_practices）
- T2AG_skeleton 和 T2AG 主项目核心文件同步更新

## [0.0.06] 种子 → 宪法：t2ag.md 身份转变

- **t2ag.md 自我定位**从「唯一种子文件」改为「宪法 + 结构清单」；再生系统改用 T2AG_skeleton 整体
- 重写为五章结构（自我定位 / 宪法 / 结构清单 / 生成接管 / 修宪程序），总额 ≤400 行，各章设分章预算
- **结构清单节**：每个部件一行登记（名称/路径/职能/定义文件/检查项），先登记后创建
- **doctor 增检**：宪法分章预算（超限 FAIL）、结构清单双向比对（仓库有而清单无 → WARN）
- 版本号统一至 0.0.06（t2ag.md / AGENTS.md / README.md 三处一致）
- 明确单一定义源纪律：模板正文只在 skeleton，流程正文只在 50_playbook，本文件只留指针（防复辟）

## [2026-07-07] t2ag_flow.md 功能流程图入库

- 新增 `00_core/t2ag_flow.md`：四张 ASCII 流程图（会话生命周期/权威链数据流/周期性回路/角色视角）
- 纯 ASCII，冲突时以 t2ag.md 为准并修图

## [2026-07-07] 0.0.06 — 复利回路模式 + 文件恢复

**变更概述**：建立 T2AG 第一个正式设计模式（复利回路），给实例加头部声明，doctor 加检；从回收站恢复全部课程内容。

### 复利回路模式

- 新建 `00_core/pattern_retire_loop.md`：五要素定义 + 四实例登记表 + 头部声明模板 + 演化预留
- 给 `00_core/t2ag_problemlog.md` 加三行头部声明（【模式】【参数】【边界】）
- doctor 新增 `check_pattern_declarations()`：检查声明了模式的文件五参数齐全，登记实例缺声明则 WARN
- mistake_bank / trade_journal / taste 反馈环：实例在课程/实践创建时按模板实例化，不在骨架中预建

### 文件恢复

从回收站恢复以下内容到原始 T2AG 项目：
- PY1001_book（8 文件 + ATBS_3e/ 27 文件）
- MATH1607H_book（教材 PDF + OCR 产物）
- CS1953_book（C++ Primer + 代码清单 + 课件）
- .venv/Lib/site-packages（207 包含 pandas）
- .tools（tesseract_setup.exe + tessdata + ocr_temp）
- CS1953 lesson01 编译产物
---

## [0.1.0] <日期> 骨架初始化
- 采用数字前缀命名规范（00_core ~ 70_tools）
- memory 改为分节预算制
- doctor 预留 venv/env 与版本一致性检查位
