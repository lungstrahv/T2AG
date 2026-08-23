# Doctor 现行契约清单（doctor_contracts）

**保护级别**：core-playbook

> 本文件界定 `t2ag_doctor.py` 在 0.2.2 中承诺机械验证的范围。只有可复现、可定位、违反明确现行契约的事实才能成为 FAIL；语义判断不得伪装成机械闸门。

## 三形态基础能力

Doctor/测试结构是 Main、Skeleton、Lite 的共同基础内容，不是 Main 的实例附加项，也不是
正式发布时临时生成的证据包。`t2ag_doctor.py`、`t2ag_test.py`、
`test_dependencies.json`、`validation_control.py`、`validation_workflow.json`、本契约、
`test_strategy.md` 与 `validation_flow.md` 必须在三形态中存在；共享文件由 release profile
做 SHA 对照。Main/Skeleton 执行这些能力，Lite 只保留字节一致的审查副本。

`BASE_VALIDATION_FILES` 是机械基础清单；任一形态缺文件、Doctor 不再以 runtime 为默认档，
或 runtime/release 实现合并，均属于基础结构 FAIL。Lite 的只读身份不允许执行脚本，但不
允许删减这些基础文件。

## 零、运行档位

- `--profile runtime` 是默认档位，也是启动、恢复、同步与结课入口。它只检查当前发行的
  本地教学状态、活动/台账、权威链、上下文能力、皮肤与授权安全。日常启动可在 Doctor
  尚未返回时凭可信 L0-critical 进入只读 `learning-ready`；Doctor 返回 FAIL 后必须阻断
  下一教学动作与全部写入，`recovery-settled` 更要求 `0 FAIL`。
- `--profile release` 先运行全部 runtime 检查，再追加跨发行 SHA、Core/Template 同源、
  migration/journal/guide 派生证据、handoff、候选隔离、Git 环境与 dirty tree 检查。
- Doctor 原子项、顺序、依赖和 profile 继承只由 `validation_workflow.json` 定义。每次运行先
  输出 `t2ag.doctor_plan.v1` 的检查列表与 plan SHA；`--check` 可组合定向项并自动包含依赖。
- 完整 runtime 是启动例外：打印固定计划后可直接执行一次。定向 Doctor 和全部 release
  执行必须绑定 `--execute-plan`；release 还必须提供清单登记的 `--release-reason`。
- Lite、Git、候选、历史迁移证据或跨发行分叉不得由 runtime profile 报为启动 FAIL；这些
  事实只阻断候选与发布。release profile 通过也不等于独立复审或发布批准。
- Doctor 不是测试调度器。定向测试由 `test_dependencies.json` 和 `t2ag_test.py` 选择；
  `fast / deep / release_only` 的边界见 `test_strategy.md`，Doctor 不得因测试文件数量增长而
  扩大默认启动检查。
- release-only 测试按 receipt/evidence/gate/fault/shadow 分域；`release_suite` 没有
  changed-path 映射，只能在冻结候选或正式发布时显式选择。

完整树形流程及防越级分支见 `validation_flow.md`。控制文件中 runtime 为唯一默认 profile，
release 必须显式继承 runtime；任一工具绕过计划 SHA、release reason、三测试命令预算或
plan-only 聚合门，均属于基础结构 FAIL。

## 一、结果分类

| 分类 | 含义 | doctor 行为 |
|---|---|---|
| FAIL | 可复现、可定位，违反明确现行契约 | 返回非零 |
| REVIEW | 需求含糊、模型判断不稳定，或存在多种合理设计 | 不由 doctor 自动定级；转入讨论 |
| WARN | 事实成立，但不阻断当前目标 | 返回零并报告 |
| WAIVED | 与需求提出者讨论后，明确延期或接受风险 | 不隐藏原事实；记录 waiver 证据 |

三轮、每轮最多三次实质尝试及重新分类规则见 `remediation_governance.md`。

## 二、0.2.0 自动检查矩阵

| 契约 | 自动入口 | 失败边界 |
|---|---|---|
| 九域与发行身份 | runtime 本地 + release 跨发行 | 本地目录/版本不闭合，或 release 时 Main/Skeleton/Lite 身份不闭合 |
| profile 初始化与 Agent 偏好 | doctor 内建 | initialized 仍有占位符或缺时间、目标、基础、偏好；Agent schema、1..3 上限、并行/ready/播报枚举非法 |
| Course/Group/Binding/AR/EG | doctor 内建 | schema、稳定 ID、引用或生命周期冲突 |
| progress 身份 | 统一活动路由器 + state + doctor | `type/course_id/truth_scope` 缺失、冒名或在任何 GENERATED 写入前未被拒绝；迁移后不接受 truth_source-only |
| 学习活动发行能力 | runtime 本地 + release 跨发行 | 本地 Core/Template 缺失，或 release 时 Main/Skeleton/Lite 内容分叉 |
| 恢复路径 | 统一活动路由器 + doctor | ongoing Course 缺显式 `current_activity`、`current_activity_id`、canonical `resume_path`、`activity_position`，或目标悬空；Exercise 首启不得依赖预造 Lesson |
| 学习上下文包 | runtime 本地 + release 跨发行 | 本地工具/合同缺失或行为错误；三发行分叉只在 release profile 阻断 |
| Evolution Register ↔ ADR 关联 | runtime `decision_records` | EV/ADR ID 重复、悬空双向引用、accepted 指向非 decided EV、portable_key 冲突、supersedes 环、redirect 失效；**不做**“是否值得成为 ADR”的价值裁决。skeleton 侧 register 为实例清零（EV-0023），EV 链接检查豁免、ADR 文件完整性不变 |
| 正文 ADR/EV 引用存在性 | runtime `decision_record_citations` | 现行规范性正文（宪法、AGENTS、README、`50_playbook/`、`docs/adr/`（含 ADR 正文）、`docs/protocol/`）引用的 ADR-NNNN 必须存在；Main 侧 EV-NNNN 必须存在于 register，skeleton 侧 EV 引用为维护者出处注释豁免（EV-0023）。扫描面不含 changelog/problemlog/journal 等只追加历史档（P-0067）；ADR 正文与 protocol 于 2026-08-09 复审后纳入 |
| 状态快照组件边界 | `test_progress_identity_is_shared` + `test_state_refresh_activity_roundtrip` | state 或 Doctor 推断缺失活动、把历史 Lesson 标成活跃、为 sentinel 构造路径、组视图假定当前活动必为 Lesson，或一次运行对同一 ongoing progress 二次读取而混合状态版本 |
| 活动事务落盘往返 | `test_activity_cli_disk_roundtrip` | 从当前发行自身建立无 hardlink 的临时完整工作树，并断言 Doctor 实际检测到本发行 flavor；真实执行 `--write → 重读 → --check → 完整 Doctor → recover route → close route`，按路由结果落盘 progress 与当前主载体后再次执行 state/Doctor；写入零命中、任一步失败或 Exercise 修改历史 Lesson |
| Lesson 上下文退役 | `test_exercise_current_lesson_driver_matrix` | 四种 driver 下 active progress 不依赖或回填 `current_lesson`；遗留非法/悬空值不得驱动路由，历史 Lesson 只从 ledger/ContentGroup 解析 |
| planned/ongoing 边界 | `test_planned_activity_fields_rejected` + doctor | planned 预填活动字段，或 ongoing 缺完整活动事务字段 |
| preparation snapshot 活动边界 | `test_textbook_preparation_activity_matrix` + doctor | textbook Lesson 缺 preparation Snapshot，或非 textbook Lesson 持有残余页缓存引用 |
| GENERATED owner | doctor + `test_activity_workflows_share_executable_route` | Lesson 保留无主 `LESSON_PROGRESS` anchor，或恢复/结课未共享统一活动路由 |
| 活动边界 | doctor 内建 | 活动图单元内 ID 重复、任一 Lesson/Exercise 漏登或 ContentGroup 漂移；活动持有另一活动或恢复 ExerciseSession |
| 非教材活动边界 | `test_lesson_retired_ownership_all_drivers` | goal/project/praxis 的 Lesson 借 driver 绕过基础 schema 或退役所有权字段检查 |
| 教师模板路由 | 统一教师映射解析器 + doctor | 映射表不唯一、列 schema 漂移、重复/漏登课程、令牌走私、模板身份不符，或模板绕过当前活动主载体 |
| 教材 Exercise 持久题源 | 统一活动路由器 + doctor | Exercise 依赖 Lesson working-pages 等可清理缓存；`source_path/source_document` 不是解析后仍在本 Course book 内的 canonical 非链接路径；artifact ID、ContentGroup、locator、源文档 SHA、registry 生命周期或逐题题面不闭合；Lite 省略二进制未由完整正式 migration manifest（报告状态/路径/SHA、schema/target kind/count/sequence 和完整 operation 字段）证明 |
| Lesson/Exercise 与习题证据 | doctor 内建 | Lesson/Exercise 主载体、ContentGroup/activity map 双向关系、U/AT/RV schema、引用、图片证据或逐题结果冲突；textbook completion node 依赖无法完整解析、越出 ContentGroup 或不在 Completion nodes 表 |
| 知识台账 | doctor 内建 | question/mistake/reasoning ID、状态或 `next_id` 冲突 |
| 项目验证 | doctor 内建 | 标准/证据未拆分、未完成节点预填证据、completed M 无有效 `VER-*` 记录，或步骤缺 `passed + 含字母/数字的实际结果摘要`（纯标点不计）为 FAIL；已启动 M 缺模式为 WARN |
| 皮肤 | doctor 内建 | registry、metadata、art_file 或发行分叉错误 |
| 序言、九张流程与离线指南 | release + `build_guide.py --check` | 序言生成锚点、FLOW 集合/配对或 guide drift |
| Cloud 暂停态 | doctor 内建 | 组件缺失、协议字段冲突、暂停门失效或 CD/CH 登记悬空 |
| handoff 分类与恢复路由 | release 内建 | Active 缺 lane/artifact_role、支撑材料混入 Active、release backlog 未隔离、索引/文件/元数据/唯一性或体积老化状态冲突 |
| handoff 断言复算来源 | release `handoff` + `unsourced_handoff_assertions` | active 交接正文中数量/存在性/哈希断言（`N 个`、`零命中`、`sha256:`）同行及下一行均无 `←` 复算来源为 WARN，逐条指名文件与行号；围栏代码与标题不扫描，**引述与散文不豁免**（`handoff_management.md` §5.6.4）。门只证明「来源相邻」，**不判定**命令质量 |
| 宿主环境假设 | runtime `environment` + `environment_probe_results` | `environment_assumptions.md` 缺失或缺 `EA-0001`~`EA-0003` 为 FAIL；`INSTANCE_ROOT` 与运行根不一致（代码树错位）、`fitz` 不可用为 INFO；`.git` 可建不可 unlink 为 WARN。探测**只读且只报事实**——不安装、不清理锁文件、不改路径 |
| changelog 漂移与腐烂 | runtime `changelog` + `check_changelog_contract`（`parse_changelog_anchors` / `stale_changelog_claims`） | **锚定**（U2 已批 A+B+C）：最新条目声明的 plan sha / checks / atom-set sha 与实测不等 → WARN，须含声明值与实测值两者。**佐证**：最新条目 `佐证断言` 节内 `grep -c/-n` 命中为零 → WARN，须指名条目标题与断言原文。**缺锚定块** → WARN。不证明完整性；形式复用 `handoff_management.md` §5.6.2；锚定量零 git 依赖 |
| state/journal/migration/Lite | release 派生工具 | 缓存漂移、证据缺失、迁移非幂等或投影差异 |
| 发布候选隔离 | `t2ag_candidate_replay.py` + `test_candidate_replay_isolation_contract` | 有效 sparse checkout/sparse index，Git 环境/拓扑污染，Main/Skeleton 安全配置无法 preflight，源/A/B 字节清单或副本结果不一致，或全部 A/B 复核之后的末次源指纹发生变化 |
| Git/环境卫生 | release 内建 | 跟踪环境文件为 FAIL；未提交工作树为 WARN |
| 教学正典载体一致性（G2） | runtime `canonical_teaching_carrier`（`canonical_carrier_findings`） | textbook driver 课程的 `teaching_log.md`（C）与 `emissions.jsonl`（L）必须一致：C 有块 L 无行 **FAIL**（CANON-000，绕过写入器）；L SHA 链断 **FAIL**（001）；页身份与 SourcePageAsset 持久字段不符 **FAIL**（002）；正文哈希与账不符 **FAIL**（003）；L 有行 C 无块 **WARN**（004，emit 中断残留）。双缺/双空静默（祖父条款）。旧 `lesson.md` 不扫。证明的是一致性，不证明「经 `canon_append.py` 写出」（自洽双写过门，见 `canon_carrier.md` 头部） |
| 规则强制声明的真实性（R-GATE） | runtime `rule_enforcement_integrity`（`rule_enforcement_findings` / `landing_defect`） | 白名单规则文件（`50_playbook/*.md` + `00_core` 三个模型文件）内 `enforcement:` 的声明必须兑现：`check=` 不在 `doctor_checks` 键集、`tool=` 文件缺失、取值不属四取值、字段错位（`enforcement:` 落记录区 / `closure:` 落规则文件）为 **FAIL**（悬空声明=假保障，P-0067 家族）；`context=` 锚失效、`prose_accepted` 空理由为 **WARN**（改措辞不阻断教学）。示例先剥 fenced block 再按行首匹配（自指逃逸，`rule_admission_gate.md` §四）。**不检查「该声明而未声明」**。记录区（changelog/problemlog 正文/memory）与宪法 `t2ag.md` 显式豁免，理由见 `rule_admission_gate.md` §三 |
| **Main↔Skeleton 批准同源面** | release `distribution_parity`（`check_distribution_parity`） | 同源面内文件字节不一致或 Skeleton 缺失为 **FAIL**；**豁免项两侧已一致为 WARN**（提示移除，防止名单长成盲区）。同源面定义见 §二·一 |
| **跨语言发行面（Main↔英文版）** | release `cross_edition_parity`（`cross_edition_parity_findings`） | 翻译版与 Main 的**机器标识符**（handler 名／检查 ID／profile 登记）与**分节编号**必须同集：未登记的缺失或多出为 **FAIL**（CE-PAR-001／002）；比对源缺失或不可解析为 **FAIL**（004，宁可红也不缩覆盖面）；同一版内节编号重复致不可判为 **FAIL**（005）；已登记回移欠账为 **INFO**（000，理由必须含回填条件）；豁免项两侧已一致或悬空为 **WARN**（003）。字节同源在跨语言下不可满足（英文面自陈 `skipTest`），故比对单位抬到标识符与编号；**散文措辞不在射程内**——本闸门证明机制在位，不证明译文忠实。未挂载对端时静默 |

### 二·一 「批准同源面」的定义（P-0065）

§七 第 4 条自 0.2.x 起要求「Main/Skeleton 批准同源面逐文件一致」，
但**该同源面从未被定义**——没有清单，也就没有任何检查够得到它，
12 个文件因此静默分叉至 2026-08-08 才被发现。本节补上定义。

**同源面** = Main 与 Skeleton 下列目录中扩展名为 `.md` / `.py` / `.json` 的全部文件
（`__pycache__` 除外）：

```
main/50_playbook/
main/70_tools/
```

**豁免名单**（写在 `t2ag_doctor.py` 的 `DISTRIBUTION_PARITY_EXEMPT`，**理由为必填值**）：

| 文件 | 豁免理由 |
|---|---|
| `main/70_tools/legacy_r_registry.json` | Skeleton 版正文自述 entries empty by design；Main 版为主实例级兼容登记 |
| `main/70_tools/artifact_registry.json` | Main 含真实 artifact 条目；强制同源等于把实例数据灌进 Skeleton |

**三条纪律**：

1. **豁免必须带理由**。无理由的豁免等于把检查挖空——那正是本条要防的失败。
2. **豁免失效要报**。已豁免但两侧实际一致的项报 WARN 提示移除，名单不得只增不减。
3. **同源不是单向覆盖**。修复漂移前须逐文件判断方向：「A 有 B 无」既可能 A 领先，
   也可能 **B 保留了 A 已删除的退役内容**。2026-08-08 一次差点因行数方向读反而
   把 Main 主动删除的退役字段当成 Skeleton 领先内容保留。

**归 release 不归 runtime**：按 `t2ag.md` §3.2，发行属性的 FAIL 阻断候选与发布，
不阻断日常教学。Skeleton 漂移不应停掉一节课。

## 三、人工检查

以下判断必须由 agent 给出证据并在必要时与需求提出者讨论，doctor 只验证其载体是否存在：

- 教学解释是否准确、反馈是否足够好；
- handoff 四问是否在语义上真的可恢复；
- 项目验收内容是否达到产品质量，而不只是记录齐全；
- 习题思路观察、错因归纳和掌握推断是否合理；
- REVIEW 与 WAIVED 的裁决是否符合当前目标。

## 四、未激活与退役

- 跨课程考试系统明确不属于 0.2.0；`exam_protocol.md` 与 `exam_bank_spec.md` 只保存延期设计，不触发本版 doctor。
- 0.1.x 的 Case、CourseDefinition/CourseRun、Curriculum、FieldPractice、旧 `skin/` 与旧题库路径已经退役；doctor 只检查其不得重新进入 active 树。
- KnowledgePoint 与 AbilitySummary 仍非正式活动对象。OCR/页核验属于 **SourcePageAsset**
  来源证据（EV-0012 / `source_page_assets.md`），不是独立 LearningActivity 或 mastery。
- Doctor runtime 对 textbook Lesson 验收：
  1. **current** preparation Snapshot 指针（`current_snapshot.json`，禁止字典序猜最新）
     + LessonMap 覆盖/hash + load receipts + 页资产核验 + PDF SHA + Scope 连续性/长度 +
     P0/quota 告警；缺 preparation 时 FAIL（legacy `working_pages` 路径已退役）。

## 五、Waiver 边界

数据完整性、路径悬空、schema、权威冲突和投影差异在契约仍生效时不得豁免。只有外部环境造成、且不影响仓内正确性的检查可写正式 waiver；记录必须包含事实证据、风险、责任人、批准人和失效时间。

## 六、0.2.0 最终复审冻结

0.2.0 最终复审的新增阻断范围只认 `git_workflow.md` 9.1 的六项；此外只复核本表已经存在的
三发行闸门。清单外新发现进入 backlog，不能仅因提高威胁模型而把它升级成本代 FAIL。
日常学习链已经单独验收，可以继续；候选生成和 Git 快照仍分别需要后续明确授权。

## 七、Version campaign 与 delta review 全局门

authorization envelope、reviewer 独立性与 release 资格属于人工治理，不由 Doctor 单独裁决。
Doctor 只验证已登记且可机械复现的载体；通过 Doctor 不等于 `reviewed` 或 `released`。

无论是完整候选复审还是 delta re-review，以下现行门不可拆分，也不可用 campaign envelope、
报告声明或 waiver 跳过：

1. 数据完整性、稳定 ID、schema 与引用闭合；
2. 活动入口、恢复路径与权威链唯一性；
3. migration evidence、journal/index 和未完成 transaction；
4. Main/Skeleton 批准同源面逐文件一致（同源面与豁免名单的定义见 §二·一；
   自 2026-08-08 起由 release `distribution_parity` 自动执行，不再只靠人工核对）；
5. Main → Lite 投影无 missing/differ/orphan/guide drift；
6. 最终源、候选 tree、index 与输入 docs manifest 指纹稳定。

delta review 只有在旧证据的输入 manifest SHA 未变、范围外文件指纹未变且影响闭包可证明时
才可复用旧结果；否则拒绝复用。权威链、schema、registry 生命周期、migration apply 语义、
事务引擎、候选生成、安全/隐私边界变化，或无法证明影响闭包时，必须退回完整独立复审。

recovery checkpoint 只证明存在恢复点，不进入 release 资格判断。release snapshot 必须由外部
独立报告绑定完整 candidate review 和有界 finalization delta review；`clean ≠ reviewed ≠ released`。

## 八、检验的产生纪律（2026-08-10，随检验体系施工确立）

新增或修改任何 Doctor 检验时：

1. **四卡点原则**：检验只许挂在四个既有卡点——启动（runtime doctor）、结课
   （session_close 第 5 步）、施工（V0–V3 / t2ag_test）、发布（release profile）。
   不得新增依赖"模型记得去跑"的散文义务；需要模型记得才会执行的检验视同不存在
   （问题根源见 2026-08-08 审查 A3：注意力过载线）。
2. **红测夹具**：新增/修改检验必须附至少一个会触发它的最小夹具（contracts 测试组
   NEGATIVE 用例）。从不触发的检验与不能触发的检验无法区分。存量检验按 problemlog
   回放命中顺序逐步补齐；覆盖率 = 有红测的检验数 / 总检验数。
3. **回灌契约与两振出局**：problemlog 条目须声明强制落点（`closure` 字段，机检
   `runtime.problemlog_closure`）；`occurrence_count >= 2` 的问题不得再以散文修复收尾，
   必须落 `check=`（doctor 检查）或 `tool=`（代码强制）。字段语义 canonical：
   `00_core/t2ag_problemlog.md` 头部回灌契约。

## 九、外部来源回指契约（`source_catalog`，2026-08-16，EV-0026）

课程的教学结构常常先由模型**预画**，再在某一轮取到官方目录时对表。本契约管的
**不是「有没有去取」，而是「取了之后有没有留下 diff」**。

enforcement: check=runtime.external_source_backlink

### 九·一 字段结构

`40_course/<ID>/course.md` frontmatter 内的一个块（示例在围栏内，非真实标注）：

```yaml
source_catalog:
  url: https://example.org/course/catalog
  fetched_at: 2026-08-16
  predicted_count: 8
  actual_count: 13
  diff_recorded: 40_course/<ID>/lessons/lesson01/lesson01.md#官方目录核实
```

`diff_recorded` 的**锚语义与 `enforcement: context=` 完全一致**（R-GATE
`rule_admission_gate.md` §二，同一实现 `landing_defect`，不另起解析）：
路径相对 `main/` 根、按**第一个** `#` 切分、精确子串零规范化。
锚文本选短而稳定的短语，别选整句。

### 九·二 判定与严厉度

| finding | 条件 | 级别 |
|---|---|---|
| `EXTSRC-001` | 课程 `lifecycle_status: ongoing` 且无 `source_catalog:` | **WARN** |
| `EXTSRC-002` | 有 `source_catalog:` 但 `diff_recorded` 缺失/解析不开，或行内取值不是 `none` | **FAIL** |
| `EXTSRC-004` | `source_catalog: none` 未写理由 | **WARN** |

> `EXTSRC-003` 是**已退役槽位**（种子↔课程边，实现前已改由 T1 跨仓合同承担）。
> **永不复用**——复用的稳定 ID 会让此后每一次引用都无法确定指向哪条（P-0072 的教训）。

### 九·二·一 `none`：没有外部目录可对的课程

教材驱动与 project 驱动的课程，其权威目录是**已在仓内的纸质教材目录**，没有外部目录
可取。这类课程写：

```yaml
source_catalog: none（理由：教材驱动，权威目录是纸质书目录，仓内 book/ 已有）
```

**为什么必须有这一支**：否则这类课程会永久挂着一条**无法被合法清除**的 001——
而永久噪音会把整个告警通道训练成可以忽略的东西。

**为什么 `none` 必须带理由**：理由是防止 `none` 变成消音键的唯一东西，与
`prose_accepted（理由）` 同型。**`none` 不是免检牌，是一句可被反驳的断言**——
谁发现这门课其实有官方目录页，就该把它改掉。

**为什么缺失只判 WARN**：预画本身**合法且有价值**——它是一次可证伪的预测，价值恰在
取目录当轮的 diff（首例实测：预画 8 节 / 实际 13 节，且指得出漏在哪几处）。判 FAIL
会逼出「开课即抓目录」，那个 diff 就永远不会产生——**等于用强制力换掉了信息**。
故缺失是**合法的「尚未检验」态**，不是待办。

**为什么悬空判 FAIL**：`source_catalog` 在场即**声称已经对过表**；`diff_recorded`
指不到东西，就是声称有证据而证据不在——悬空声称，P-0067 同型，比不声称更毒。

与 R-GATE 同一句纪律：**管的是说了的话必须算数，不管没说的话。**

### 九·三 限度（必须与机制同写）

1. **不保证目录是最新的**，只保证「声称取过就必须留下 diff」。八天没取，本检查
   仍然只出 WARN——**强制力是知情换掉的，不是漏掉的**（EV-0026 代价节）。
2. **不覆盖时间维**（挂载缓存陈旧，P-0070）。新鲜度的真值源仍只有 Read 工具。
3. **不检查「该声明而未声明」**：`planned` 课程、以及没有外部目录可对的课程，
   不在判定面内。

### 九·四 种子↔课程的边不在本检查内

课程与 `docs/seeds/` 的回指走 **T1 引用合同**（`cross_repo_reference.md`），
sidecar 落在**课程侧** `40_course/<ID>/external_refs.json`，由**已有的**
`runtime.external_references` 校验。本检查**零参与**。

理由：`check_external_references` 只 `MAIN.rglob("external_refs.json")`，
放在 `docs/seeds/` 的 sidecar doctor 永远看不见、静默零 finding——那是假保障。
故边的方向定为**课程 ──► 种子**（引用方=课程，住 `main/` 内，可达）。

> **这与 `docs/SEEDS.md`「不存在 seed → 课程 的通道」不冲突。**
> 那条禁的是**升格通道**（种子不得因为「想学」就变成课程）；这里建的是
> **回溯引用边**（课程记录「本课堂外溢出了这颗种子」）。**是决定，不是漏洞**。

## 十、playbook 分级仪器（两档）

| 档 | 检查 ID | handler | finding | 级别 |
|---|---|---|---|---|
| runtime（本地） | `runtime.playbook_taxonomy` | `check_playbook_taxonomy` | PB-TAXO-001 非法值 | FAIL |
| runtime | 同上 | 同上 | PB-TAXO-002 无标记 | WARN（白名单仅 `_README.md`） |
| runtime | 同上 | 同上 | PB-TAXO-005 同文件不同合法值 | FAIL；同值重复为 WARN |
| release（跨发行） | `release.playbook_taxonomy_parity` | `check_playbook_taxonomy_parity` | PB-TAXO-003 meta+core 集合或 SHA 分叉 | FAIL |
| release | 同上 | 同上 | PB-TAXO-004 Skeleton 缺任一 meta | FAIL |

共享解析器：先 `strip_fenced_blocks`，再匹配
`^(?:>\s*)?\*\*保护级别\*\*：(meta-playbook|core-playbook|playbook)\b`，
返回全部匹配（不是首个）。围栏内引用不算。blockquote 前缀要认。

**诚实边界**：不检查「该标而未标的语义正确性」——本检查只验证标记形式与跨发行
集合/SHA，不判断一份 playbook 按 §四 功能判据该是 meta 还是 core。

| runtime | `runtime.playbook_usage` | `check_playbook_usage` | PB-USE-000 无课程实例跳过（冷启动护栏） | INFO |
| runtime | 同上 | 同上 | PB-USE-001 冷门标记（>14 天无带日期引用） | WARN |
| runtime | 同上 | 同上 | PB-USE-002 归档候选（>40 天；处置归宿主 git mv，唯一副本不删） | WARN |
| runtime | 同上 | 同上 | PB-USE-003 无引用数据（观测态，不判冷门） | INFO |

**折旧检查的诚实边界**：测的是**带日期的引用痕迹**（changelog/journal/handoffs＋
会话自报行），不是阅读事实——文件制系统读文件无拦截点，静默阅读不可观测。
仅普通级参与；meta/core、`managed_by:` 受管数据、`PLAYBOOK_USAGE_EXEMPT`
显式豁免（豁免即数据）不参与。skeleton 无 `docs/handoffs` 时该数据源自动缺席，
不报错。

既有 `check_core_playbooks`（`release.core_playbooks`）本批只换同一解析器，
注册位不动；其与 parity 检查的分工归并另池。
