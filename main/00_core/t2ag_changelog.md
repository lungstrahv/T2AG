# T2AG 变更历史

> 按需展开。启动时不全量读，由 t2ag_memory.md 的「最近变更摘要」按行号指针索引。
> 追加条目时同步更新 memory 摘要，并对超出 memory 节预算的旧条目做"下沉"处理。

---

## [2026-08-10] release.package_surface：发行物表面检查（不升版）

- **新增 `release.package_surface`**：扫描工作区根下全部 `t2ag-skeleton*.zip`，包内含 `.git`
  即判 FAIL（该包不得对外分发）；`.bak-*` 等非 `*.zip` 后缀视为隔离件，不参与判定。
  这是 `remediation_governance.md` §七 `carrier_mismatch` 家族的一次主动收口——发行物住在
  仓外，仓内检查此前读不到它。
- **原子集变动**：`doctor_checks` 50 → 51；release profile checks 15 → 16；runtime profile
  不变（本检查为 release-only，外部使用者的 runtime 首启不受影响）。
- **本条目补记上一 commit 的锚定断言缺失**：`52df0a6` 改了原子集但未追加 changelog 锚定块，
  导致全新副本 runtime doctor 报「状态漂移无记录」1 WARN。教训与 P-0067 同族：**改
  `validation_workflow.json` 的 commit 必须同批追加锚定块**，否则漂移检查会对着上一条
  历史记录报警，而那条记录并没有说错话。

#### 锚定断言（必填）
- runtime plan sha256 = d7a4eebc1238d5a019349589db9324438177686e86d26d926c7047ead8a2d48a ← `python -B main/70_tools/t2ag_doctor.py --profile runtime | Select-Object -First 1`
- runtime checks = 35 ← 同上
- doctor_checks atom set sha256 = d41fafde87632b191fe35f4659f1b9d87ca4d32ec5d7f8618bddba954bf71fd8 (n=51) ← `python -B -c "import hashlib,json,pathlib; k=sorted(json.loads(pathlib.Path('main/70_tools/validation_workflow.json').read_text(encoding='utf-8'))['doctor_checks']); print(len(k), hashlib.sha256(chr(10).join(k).encode()).hexdigest())"`

#### 佐证断言
- 全新解压副本 runtime 0 FAIL / 0 WARN ← 沙箱解包后执行 `python3 -B main/70_tools/t2ag_doctor.py --profile runtime`
- release profile 计划 sha256 = `25bfb3951a424b202835bb05c7b930d14b664f1f36409231d54a687fa905ea5f`（checks=51）← `--profile release` 首行；**不入锚定块**：锚定解析按「plan sha256」子串取最后一次命中，多写一行会静默改写 runtime 断言（§七 carrier_mismatch 同族，已记入下方教训）
- 工作区三个既有 `t2ag-skeleton*.zip` 均不含 `.git`，新检查不产生存量红 ← `zipfile.namelist()` 实扫

---

## [2026-08-09] 独立复审修复闭合（不升版）

- **隐私检查恢复实质覆盖**：changelog 中维护者绝对路径已脱敏；整文件豁免已撤销，
  `runtime.skeleton_privacy` 现仅豁免 doctor 自检文件，报告「1 项豁免，其余全树无维护者标识」。
- **生产授权回归恢复有效性**：测试改 patch `INSTANCE_ROOT`，负例使用全局合法但生产不允许的
  `test` 模式，并精确断言生产环境必须使用 `direct_user`。
- **文档闭环**：July journal 已移除迁移档案死链；ADR 索引补齐 ADR-0003/0004，并明确
  `source_evolution` 是 Main register 的外部出处。
- **引用扫描闭环**：扫描面新增 `docs/adr/*.md`、`docs/protocol/*.md`，新增 ADR 正文与协议
  正文两条回归；`docs/adr/README.md` 不再重复扫描。
- **验证**：decision_record 19、close_roundtrip 21、migration 10、receipts 12 全绿；
  runtime doctor 0 FAIL / 0 WARN。
- 本批次只修复既有 EV-0022/EV-0023 的复审发现，不产生本实例新决策，故不登记 EV-0024。

#### 锚定断言（必填）
- runtime plan sha256 = d7a4eebc1238d5a019349589db9324438177686e86d26d926c7047ead8a2d48a ← `python -B main/70_tools/t2ag_doctor.py --profile runtime | Select-Object -First 1`
- runtime checks = 35 ← 同上
- doctor_checks atom set sha256 = 54f3d071a3c144d4c3dc0bbeed75fd5c4542b4952faed19caf3849667a29be07 (n=50) ← `python -B -c "import hashlib,json,pathlib; k=sorted(json.loads(pathlib.Path('main/70_tools/validation_workflow.json').read_text(encoding='utf-8'))['doctor_checks']); print(len(k), hashlib.sha256(chr(10).join(k).encode()).hexdigest())"`

#### 佐证断言
- 四组测试通过 ← `python -B main/70_tools/test_decision_record_contract.py`、`python -B main/70_tools/test_022_close_roundtrip.py`、`python -B main/70_tools/test_022_migration.py`、`python -B main/70_tools/test_release_receipts.py`
- runtime 状态复算 ← `python -B main/70_tools/t2ag_doctor.py --profile runtime`
- 共享实现与 Main 同源 ← 本批次 `git diff --no-index` 核对

---

## [2026-08-09] EV-0022/EV-0023 落地：发行边界清洗完成，privacy FAIL 归零（不升版）

- **privacy FAIL 6→0**：三处硬编码路径随 EV-0022/EV-0023 消除（`activity_close` 改
  `INSTANCE_ROOT` 实例派生；`campaign_receipt` 第三仓改 `--reading-root` 入参；
  `migrate_022` 常量派生化）；三处历史档案随 EV-0023 移出（`migration_020_*`、
  `migration_021_profile_*`、`retired_020_sources/`、维护者 register）。
  `runtime.skeleton_privacy` 现报「2 项豁免，其余全树无维护者标识」。
- **register 实例清零**：本实例决策从 EV-0001 自筹（模板含 EV-0023 清零说明）；
  正文 EV-NNNN 引用为维护者出处注释，本 flavor 豁免 EV 链接检查。
- **ADR-0003/0004 补入**：宪法 §7 权威入口不再悬空。
- **新增 `runtime.decision_record_citations`**（P-0067 盲区闭合）：正文引用的
  ADR-NNNN 必须存在。两个 migration evidence check 获 skeleton 分支（证据存在即 FAIL）；
  `migrate_021 --write-evidence` 在本仓拒绝（Main-only）。
- **AGENTS.md 遍历指引**：首启不必全读全仓（README → 宪法 → `t2ag_context.py`）。
- 验证：runtime doctor **0 FAIL**；四组测试两仓各跑全绿（decision_record 17 /
  close_roundtrip 21 / migration 10 / receipts 12）；模板既有漂移已同步。

#### 锚定断言（必填）
- runtime plan sha256 = d7a4eebc1238d5a019349589db9324438177686e86d26d926c7047ead8a2d48a ← `python -B main/70_tools/t2ag_doctor.py --profile runtime | head -1`
- runtime checks = 35 ← 同上
- doctor_checks atom set sha256 = 54f3d071a3c144d4c3dc0bbeed75fd5c4542b4952faed19caf3849667a29be07 (n=50) ← `python -B -c "import hashlib,json,pathlib; k=sorted(json.loads(pathlib.Path('main/70_tools/validation_workflow.json').read_text(encoding='utf-8'))['doctor_checks']); print(len(k), hashlib.sha256(chr(10).join(k).encode()).hexdigest())"`

#### 佐证断言
- privacy 检查通过 ← `python -B main/70_tools/t2ag_doctor.py --profile runtime | grep -c 'skeleton privacy'`
- register 已清零 ← `grep -c '实例清零说明' main/60_journal/t2ag_evolution_register.md`
- ADR-0003/0004 在场 ← `ls docs/adr/000*.md | grep -c '000[34]'`
- 遍历指引已写入 ← `grep -c '遍历指引' AGENTS.md`

---

## [2026-08-08] Skeleton 新手路径修复与节预算脚手架（不升版）

- **`context --include-l1` 在空模板上崩溃已修**：`render_markdown` 的
  `first_run_required` 分支只构造提示行却未 `return`，落入 L1 块读取仅路由包才有的
  `l1_empty_reason`，抛 `KeyError`。该命令是 Skeleton `README.md`「快速开始」第 4 条——
  **新手照文档跑的第一条路径直接抛栈**。改为提前返回并附一句空模板说明；
  新增 `FirstRunRenderTests` 三条回归（含 fall-through 变异守卫）。
- **memory 节预算脚手架**：Skeleton 此前无任何 `[max N]` 标记，
  `runtime.memory_budget` 恒报「节预算机制未生效」。补入「节预算与下沉」说明与
  三节空脚手架（教学检查 30 / 关键决策 100 / 问题摘要 50），内容留空由首次启动后生长。
- **本条自带锚定断言**：Skeleton 此前最新条目无锚定块，`runtime.changelog` 恒 WARN。
- cloud 面复核：`sync_cloud.py` / `cloud_learning_sync.md` /
  `cloud_instructions_template.md` 三文件已与 Main 同源；`cloud/` 目录差异
  （无 `t2ag_mobile_entry.md`、`T2AG_PROJECT_INSTRUCTIONS.txt` 为 13 行空壳）
  **属设计**——该工具自述「模板与 skeleton 永不含实例值」「skeleton 无 mobile_entry，
  无生成对象」，两侧 check 均通过，无欠账。

#### 锚定断言（必填）
- runtime plan sha256 = 7bb4d73404b828450bf4dc773212d6a711d62f4bb8185cb99a82c89793182230 ← `python -B main/70_tools/t2ag_doctor.py --profile runtime | head -1`
- runtime checks = 33 ← 同上
- doctor_checks atom set sha256 = 70fe8ee726b90514481b358c948f1a10d9520b2bf5e701635f2ee01f75eb8de0 (n=48) ← `python -B -c "import hashlib,json,pathlib; k=sorted(json.loads(pathlib.Path('main/70_tools/validation_workflow.json').read_text(encoding='utf-8'))['doctor_checks']); print(len(k), hashlib.sha256(chr(10).join(k).encode()).hexdigest())"`

#### 佐证断言
- first-run 渲染回归已登记 ← `grep -c 'FirstRunRenderTests' main/70_tools/test_context_packet.py`
- memory 三节预算标记已就位 ← `grep -c '\[max ' main/00_core/t2ag_memory.md`
- cloud 生成物在 skeleton 无对象 ← `python -B main/70_tools/sync_cloud.py`

---

## [2026-08-06] 规则反压缩纪律（不升版）

- 宪法新增 §6.3：版本更新默认 diff-patch、强制 `rule_migration`、不可丢集合、废止
  “越改越短=健康”、编辑≠发布；§1 恢复 tools/playbook 永不合并与单一定义源。
- `AGENTS.md`、`batch_workorder_spec.md`、`playbook_management.md` 同步；触碰入口规则的
  campaign 必须附 rule_migration。诊断清单见 Main/工作区 handoff
  `T2AG_RULE_COMPRESSION_INVENTORY_2026-08-06`。
- 运行版本仍为 `0.2.2`；本条目不构成 release。

---

## [2026-08-05] EV-0012 教材页资产与 Lesson Preparation 技术收口

- Course `source_assets` 成为页级核验文本与 raw OCR 的持久权威；PNG 仅作
  `book/.cache/source_pages` 下可重建缓存，不是真相源。
- 消费链已闭合：`LessonMap → LessonPreparationSnapshot → current pointer → Context`
  （source_assets 优先；新路径无效不得静默回退 legacy）。
- prepare、Context、Doctor 对 LessonMap 使用一致的原始文件字节 SHA-256 口径
  （含 CRLF；不得仅以 `read_text` 规范化文本宣称一致）。
- personal_instance 下 activity disk-roundtrip 的 synthetic materialize 幂等；不得 wipe
  多课程 teacher mapping。
- Main 的 MATH1607H 已在独立 RT3 下完成 E0 资产构建与 exact E apply（30 路径删除、
  两份 source_excerpt RETAIN）；Skeleton 不携带真实课程实例数据。
- F-DEEP 独立审计与 U4 playbook delta（Gate A）均通过；技术上 `LEARNING_READY`。
- 本条目不代表 Git、Lite、版本升级、FIN 或公开发布；运行版本仍为 0.2.2。

---

## [2026-08-05] 0.2.2 Activity Close 收口

- 新增课程级 activity ledger，分权保存 Lesson/Exercise 生命周期、pending、CLR、alias、
  学习时长、统计、结课偏好和 next action；progress 继续只拥有 Course 生命周期与唯一前台。
- 旧 Exercise ID 仅通过课程级 alias 兼容；真实 MATH1607H U1101 已迁移为 exercise01，
  AT0001–AT0009、RV0001–RV0009 和历史原话均保留。
- 新增原子 migration、lifecycle、pending/decision/reopen 与 recover 工具；生产 apply 绑定
  不可变 plan、独立复审和连续授权 receipt，失败自动回滚。
- 真实 exercise01 已按空 blocker、完整必做证据和运行时 completed 建议完成 delegated close；
  lesson01 保持后台 ongoing，后续跨题独立迁移继续由 mistake/retest 台账维护。
- Main/Skeleton 新增 V0–V3 最小充分验证规则：普通优化不得自动升级为完整发布审查；未变化
  证据可按 SHA 复用，完整矩阵与独立 V 只在正式冻结候选统一执行。
- `implementation_status=complete`，`candidate_review=passed`。候选独立报告为
  `docs/handoffs/T2AG_022_VERSION_INDEPENDENT_REVIEW_2026-08-05.md`，SHA-256
  `45548a3d66f717df6d92c8c5ae163bc89ca504c55cb9d1e4867e834a615dcffd`。
- 仓内 `release_qualification=finalization_pending`；正式本地资格由外部
  `T2AG_022_FINALIZATION_DELTA_REVIEW_2026-08-05.md` 对 final exact tree 签署。

---


## [2026-08-04] 0.2.1 ActivityRecord 分类与阅读桥接收口候选

- 将 Main `AR-0001` 实体迁移至 `activities/reading/`，保留旧扁平路径 redirect；Skeleton 只含
  reading 空容器。Doctor 现在拒绝根目录遗留、未知 kind、过深嵌套、跨 kind 重号和 orphan sidecar。
- 新增 profile migration V2 correction evidence，以钉死 Git blob/tree 和独立 oracle 纠正 V1
  可重放与证据绑定缺口；V1 保留并由 `supersedes` 显式指向，不覆盖历史。
- profile 与 ActivityRecord migrator 共用仓外 durable journal、backup、同目录原子安装、显式
  recover 和故障回滚协议；重复 apply 为零操作。
- Attempt `created` 改为真实 ISO 日期解析；2026-08-01 起 gate/assistance 字段必须成对且合法，
  既有历史 Attempt 不回写、不伪造。
- 冻结六份 Draft 2020-12 bridge schema 和标准库 fail-closed validator；Main/Skeleton/阅读系统
  三个原件仓逐字节一致，不引入第三方依赖。
- T2AG 增加 context export、candidate contribution import 和 durable receipt outbox；阅读端增加
  owner export、context import 与 note receipt。双方各写各仓，候选不自动晋升为课程或 mastery。
- Lite 再生保留 rollback 到最终 source/projection/guide 复验完成，末段失败恢复旧 Lite 并核对
  精确字节清单。`--force` 仍只作诊断，不产生发布资格。
- `implementation_status=complete`，`candidate_review=passed`。不可变独立报告为
  `docs/handoffs/T2AG_021_VERSION_INDEPENDENT_REVIEW_2026-08-04.md`，SHA-256
  `92194e00259fe7f5d80b1e458196329fbcfe7bd4e1ec1a15dd01f1383e6dd3ea`。
- release 资格仍只由外部
  `docs/handoffs/T2AG_021_FINALIZATION_DELTA_REVIEW_2026-08-04.md` 裁定；该报告通过前不得写
  release PASS。

---

## [2026-08-04] 0.2.1 version campaign 与 delta re-review 治理

- 保留 `independent_batch` 为默认模式；新增显式 `version_campaign`。只有用户批准冻结、列举、
  会失效的 authorization envelope，才可连续覆盖其中列明的 RT1/RT2 单元与有限本地 checkpoint。
- 施工单新增独立 `risk_tier`、campaign envelope 必填字段、授权停止/失效条件和单版本合并报告
  的 delta manifest；上一单元完成对应 evidence/recovery checkpoint 后即可继续，不再机械要求
  每批 commit。
- Git 规则固定 `clean ≠ reviewed ≠ released`，区分 evidence、recovery 与 release snapshot；
  有界 finalization 采用 operator stage → 独立 reviewer 预审 expected tree → commit 同一 tree →
  reviewer 后验核对及不可变外部报告。
- 首次版本候选仍须完整独立复审；finding delta 只有输入 manifest 未变且影响闭包可证明时才可
  局部复审，并必须重跑 Doctor/state/migration/journal/同源/Lite/最终源指纹等全局门。
- 为 0.2.2 Activity Close 新增 campaign amendment：A–D 与条件性 G 不再逐批索权；真实 migration
  apply 与 `exercise01` terminal close 保留为两个分别展示正文后决定的 RT3 门。本次只换代治理，
  没有实施 0.2.2，当前运行版本仍为 0.2.1。
- 治理实现与完整 candidate V 已通过；candidate report SHA-256 为
  `92194e00259fe7f5d80b1e458196329fbcfe7bd4e1ec1a15dd01f1383e6dd3ea`。最终 release 仍等待
  有界 finalization delta 外部复审。

---

## [2026-08-04] 交接体积老化行数门槛调整

- `check_1 / check_2 / old` 的行数门槛由 `400 / 800 / 1,200` 调整为
  `350 / 700 / 1,000`。
- 字符门槛保持 `30,000 / 60,000 / 90,000`；行数或字符任一达到即进入对应状态。
- Playbook、Doctor 与三发行同步；达到 350 行的交接会立即进入 `check_1`，
  并继续执行既有四问语义检查。

---

## [2026-08-04] 多块长篇讲解的地图优先协议

- 真实数学基础讨论暴露出一种通用阅读摩擦：多个概念块、对象层级和替代路线同时展开时，
  局部分节不足以替代先行的全局导航，学生需要一边识别符号类型、一边猜当前证明任务。
- LearningActivity Core 新增“先地图、后逐支”：先给短目录或树形图、对象类型和依赖关系，
  再一次展开一支并等待确认；地图只负责导航，不能替代理解确认。
- 新 Exercise 的未授权地图继续受开题零提示与提示闸门约束，不得泄露方法、子目标、
  关键变形或答案；概念讲授或学生已授权完整讲解时才可展示路线。
- T001–T003、首次启动与功能流程图同步；Doctor 与合同测试阻止 Core、教师模板或首次启动
  丢失关键条款。Skeleton 只吸收通用协议和可配置偏好，个人原话、课程记录与当前
  overlay 只留在实例侧，Lite 由 Main 再生。
- T2AG 按“Skeleton 作为可复用开源基础、个人实例保持本地”的方向持续维护；当前仓库根
  尚无明确开源许可证，正式对外分发前仍须单独裁决许可。
- Doctor 的 0.2.0 迁移身份改为只认仓库名或 README 的精确 Skeleton 一级标题；Main
  README 正常提及 `t2ag-skeleton` 不再被误判，同时保留 Skeleton 临时初始化为 Main
  运行时的历史迁移身份，并增加对应回归测试。

---

## [2026-08-01] 学生可选 Exercise 提示闸门

- profile 新增学生自选 `exercise_hint_gate: enabled | disabled`；Skeleton 首次启动保持
  `ask`，必须由学生选择，关闭 gate 也不撤销开题零提示与独立证据规则。
- 新增只读 `t2ag_hint_gate.py`，将回复分成学生推理检查、概念回答、方向提示、指定资料、
  完整讲解；概念回答只答所问概念，不得桥接回当前题，后三档分别要求同级显式授权。
- 2026-08-01 起的新 Attempt 保存 gate 快照与最高帮助暴露；未经授权泄露关键结构记为
  教师提示污染，不计学生独立掌握，也不归咎学生。
- Core、Playbook、T001–T003、Course 模板、首次启动、恢复、结课和 Doctor 同步；合同
  测试增加无授权 deny、概念 scope-only、错误等级不得升级和 gate 关闭不抹除基础规则。
- 该能力是可执行、可审计 preflight，不声称模型内提示词不可绕过；真正硬阻断仍需模型
  外部响应中介消费 deny 返回码。

---

## [2026-07-30] 0.2.1 学生共享档案容器化（批次 P）

- 将 `profile.md`、`learning_path.md`、`course_reflections.md` 与
  `reasoning_patterns.md` 归拢至 `main/10_student/profile/`；四份档案仍各自承担原有
  权威与正文职责，不做语义合并。
- 更新全部 active 引用、状态刷新、上下文包、Cloud 投影、目录指南与发行入口；
  旧路径仅保留在 registry redirects、历史记录、迁移证据或显式负例中。
- 新增 `migrate_021.py`、独立迁移 manifest/report、Doctor 结构与证据断言，以及
  legacy/duplicate/missing/extra/manifest-tamper/roundtrip 防回归测试。
- 本条只登记批次 P；阅读类 ActivityRecord 分类和双向阅读桥接尚未执行，继续受逐批
  复核与快照闸门约束。

---

## [2026-07-27] 学习会话上下文分层装载（独立复审整改）

- 日常接管由“逐文件全文读取”改为 L0 即时摘录、L1 当前一步、L2 触发式完整展开；
  `progress.md`、profile、Group、教师与活动的权威边界均不改变。
- 首轮独立复审拒绝把 70.4% 的来源选择省略率当作端到端 Token 降幅：旧 `legacy` 并非
  真实 Prompt，且原成本账漏计标题、路径、SHA、路由与 L2 包装。该发布阻断结论成立，
  旧证据已撤回。
- 成本账现分离来源库存与实际序列化 Markdown；当前 MATH1607H 的 L0 / L0+首步为
  19,336 / 19,438 字符，均对 16,000 软预算标 `REVIEW`。没有旧 Prompt 实测时不再给
  端到端降低百分比。
- 活动路由、教师映射和摘录改为共享同一原始字节缓存；`source_sha256` 改为文件字节
  摘要，并在输出前复核文件与已观察目录清单。教材 Exercise 同时核对题源 SHA。
- textbook Lesson 缺页码、窗口文件或任一页时命令失败；显式非当前课程只允许 active
  Group 内切换，组外课程失败；Lesson 的条件读取不再指向 Exercise 目录。
- `context_packet.md`、恢复、结课、流程图、AGENTS 与 doctor 已接入；空 Skeleton 返回
  `first_run_required`，Main/Skeleton/Lite 必须保持工具、测试和 core playbook 同源。
- 上下文专项测试扩为 17 项，覆盖实际 CLI 序列化与非空 L1、并发突变、原始字节 SHA、
  教材缺窗、非当前课程与 Lesson 路由；仍需重新独立复审后才能声明可冻结。

---

## [2026-07-27] 习题开题零提示与学生路线优先

- 真实 `U1101-Q005(1)` 暴露“证明先给思维树”会与四级提示梯冲突：教师虽未直接写
  最终答案，却预发了元素法、逻辑分配律和第一步展开，实际越过独立尝试层。
- 现行规则改为习题首次只给题面；先读取学生自己的对象、翻译、构造与证明路线，
  重点检查逻辑是否成立，不要求与标准思维树一致。
- 思维树改为讨论中逐步形成的可选整理产物；方向提示、参考资料、完整逻辑骨架与
  标准答案严格按提示梯后移，关键等价链与完整方法属于末级信息。
- Main 与 Skeleton 的宪法及 T001–T003 模板同步；实例 overlay、profile 和课程规则
  由初始化后的学生协商结果具体化。

---

## [2026-07-26] LearningActivity 单路由与结课事务链闭合

- `current_activity / current_activity_id / resume_path / activity_position` 是 ongoing
  课程唯一当前活动语义；`current_lesson` 只保留当前、历史或无 Lesson 上下文。
- 新增统一只读路由器；Doctor、状态刷新、恢复与结课不再各自推断活动。
- Lesson / Exercise 分支覆盖 working-pages、资产、问答和写回载体；micro/full close
  共用同一必做事务，Exercise-first 无须预造 Lesson。
- 合同测试包含真实临时工作树的 CLI 写盘、重读、完整 Doctor、恢复和结课往返。
- 独立复审通过且用户授权前，不建立发布快照。

---

## [2026-07-24] 批次 F：Case 结构说明加装

- 批次 F：domain_model §1.1 补登 FieldPractice（原漏列，属登记遗漏非新增规则）并为 AR 补路径；新建/加厚 `10_case/_README.md` 说明 Case 的"拥有 / 掌管但住在别处 / 不拥有"三层关系（视图，非真相源）。纯追加，无路径变更。

---
## [2026-07-20] v0.1.2 执行基线与两级进度

- 分离课程生命周期与 capacity group；新增 checkpoint/completion node 两级进度协议。
- handoff 加入独立老化检查，Git 改为逐次授权且远端上传由用户手动完成。
- doctor 与模板按新生命周期、节点、路径注册表和生成缓存规则升级。

---

## [2026-07-14] v0.1.1 交接上下文 core-playbook 入库

- 新增 `50_playbook/handoff_management.md`，按用户明确要求长期保留，保护级别为 core-playbook，并同步 main、skeleton、lite。
- 交接定位为“任务路由 + 恢复证据”，不得覆盖 `course_status.md`、规则定义文件或实际工作区状态。
- 索引改为先按 active、scope 与 applies_to 匹配，不再跨课程、项目、专题做全局日期优先排序。
- 摘要采用“最小状态摘要 + 连续性摘要 + 操作证据 + 历史入口”四层结构；连续性摘要按最小充分上下文保留多个长对话的核心讨论、理由、被否决方案和未决问题。
- `lesson_recover.md` 增加未闭合课堂的条件读取与权威修复；`session_close.md` 增加匹配交接的 resolved 闭环。

## [2026-07-14] v0.1.1 操作目录册字体系微调

- 三发行版目录册标题改用 `Goudy Old Style` 与楷体回退栈，正文改用 `Noto Sans SC` 优先；主标题略收字号并放松行高，降低尖锐感且不引入外部字体依赖。
- 目录册改为学生体验优先：封面说明按需改造、即时反馈与减摩擦，新增“需求 → 原型 → 使用反馈 → 固化/撤回”路径；反馈调节综合学生陈述、体验档案、学习结果和进度权威链，形成经学生确认的可撤回调整。
- 目录册移除面向维护者的“发行版”首章，改为项目序言与设计理念；安装转换移入启动章节，界面按“拿到什么 → 做什么 → 看到什么 → 哪些内容改变 → 以后如何使用”的学生旅程说明，内部实例化判据留在规则文件。

## [2026-07-13] v0.1.1 知识点掌握、模板治理与发行同步

- 感想记录采用稳定 `REFL-课程代码-NNNN`，目录计数改为 doctor 可重算缓存；每个课程段增加学习使命。
- mistake_bank 从权重题目表改为知识点状态机：三次独立正确、错后连对、六次强化上限、maintenance 与 aged。
- 开课抽查改为 2 个课程覆盖 + 最多 8 个活跃知识点 + 最多 1 个陈年反刍；维护知识点可远期重激活。
- 新增 `praxis` 实践修炼型课程驱动，要求真实行动证据并声明 T2AG 不能替代学生生命力参与。
- 学生获得要求模型换一种或者加一种展现形式的权利；视觉格式优劣表进入 `lesson_recover.md`。
- 陈年复习卷定义手动生成接口，自动触发、题量、时限与状态迁移权限留待专项讨论。
- 新增 `50_playbook/method_distillation.md`，定义跨课程方法生成、训练、验证与接替流程。
- 方法状态采用 `candidate → reinforced → automatic → superseded`，并保护候选综合之外的原始差异。
- 版本采用 MAJOR.MINOR.PATCH 发布批次：日常编辑只记 changelog，未独立发布的 0.1.2 合并回本次 0.1.1。
- `问题：` 与 `疑问：` 设为同效课堂触发词，统一进入当前 lesson 问答记录。
- 新增每课程 `question_bank.md` 模板与初始化、恢复、结课路由。
- 陈年复习卷增加 `off/suggest/auto` 日历并按实际学习日期计数；连续正确后从 `aged` 回到 `maintenance`。
- `git_workflow.md` 改为可选、本地优先和显式路径暂存；7 个 core-playbook 完成三发行版同步与 doctor 哈希检查。
- skeleton 确立为唯一模板源；课程索引、案例总览、教师 overlay、学生模板和课程组入口恢复为无实例数据的通用模板。
- `new_course_init.md` 成为错题库空模板和知识点合并键的唯一生成源；`mistake_retest.md` 管状态迁移，`session_close.md` 管写回。
- 删除重复的 `session_open.md`、`context_scan.md`、过时 REGEN_TEST、实例 journal 和孤立 overlay；main/lite 当前本就未含这两个重复入口。
- 教师模板、首次启动、lesson 路径、S001 与课程组 README 以通用规则并集同步到 main/lite；doctor 新增错题库生成模板检查。
- main、skeleton、lite 身份明确为运行实例 / 唯一模板源 / 线上模型纯文本审查快照。
- 新增“环境惰性”；项目普通验收不再删除重建 venv，净室复现必须授权并使用独立环境。
- OCR 安装与模型下载增加体积、位置和用途报告闸门。
- doctor 阻止 skeleton/lite 混入 venv、`__pycache__`、`*.pyc` 和审查包二进制。
- 新增 core-playbook `naming_conventions.md`；活动教材工作区从 `temppage/temp_page.md` 迁移为 `working_pages/source_excerpt.md`。
- 操作目录册统一为 `t2ag_directory_guide.html`，三发行版同步淡色 Fable 编辑风与普通蜗牛插图。
- 环境约束增加严格冻结、轻重分离、共享缓存三方案；当前冻结现有环境，常规体检禁止递归扫描 venv。

## [2026-07-13] v0.0.07 00_core 单一职责清理

- core 收缩为五文件；考试、学生状态、流程图和项目日程的重复层退役。
- 外部资源索引移至 `30_courses/_shared/`，skeleton 提供登记模板，入库规则统一归 `book_management.md`。
- 有效考试规则并入 `50_playbook/exam_protocol.md`，变式安全规则并入 `mistake_retest.md`。
- 学生路由统一归 `10_case/student_info.md`，流程入口统一归既有 playbook。

## [2026-07-13] v0.0.07 习题闭环门入库

- 每道习题结束后，除非学生在该次回答中明确表示“没有疑问”，否则教师必须依据实际作答分析思维方法并询问有无疑问。
- 思维证据不足时禁止臆测；习题闭环不替代跨概念所需的明确“继续”。
- 主流程、恢复流程和 T001-T003 同步更新，未新增 playbook 或目录层级。
---

## [2026-07-09] v0.0.07 R 子型分立 + Kaggle 转入通识轨 + r 后缀编号

**R 子型裁定**：R 分阅读型（reading）和项目型（project）。判据是"验收是否依赖外部不可控真相源"——周易的真相源是权威译注（可对照不判题）→ 阅读型；Kaggle 的真相源是私榜排名（机器判题不可协商）→ 项目型。规则④⑤分流：阅读型走自测三件套，项目型走绑定验证模式（A/B/B-K），三机制不豁免。

**r 后缀编号**：R 类课程在课程号尾部加 `r` 标注通识属性。`r` 标的是"为什么存在"（通识/兴趣），不是"怎么验收"。交大真实编码原码+r（PHIL1101r），自设编码自设码+r（DS1001r）。

**Kaggle 转入 R**：DS1001 从 G 预划课程（`20_groups/preplans/`）转为 R 项目型通识课（`25_general/DS1001r_Kaggle.md`）。B-K 验证模式保留不变。`overlay_atlas.md` 预划表删除 DS1001 行。

**周易改号**：R01_ZhouYi → PHIL1101r_ZhouYi（PHIL 对齐交大哲学前缀 PHIL1009）。

### 新增文件
- `25_general/DS1001r_Kaggle.md`（R 项目型文件，从 preplan 转化）
- `25_general/PHIL1101r_ZhouYi.md`（从 R01_ZhouYi.md 重命名 + 更新课程码）

### 删除文件
- `25_general/R01_ZhouYi.md`（重命名为 PHIL1101r_ZhouYi.md）
- `20_groups/preplans/DS1001_Kaggle.md`（转入 25_general/）

### 修改文件
- `50_playbook/general_learning.md`：新增「R 子型」节 + 规则④⑤分流 + 项目型 R 文件模板 + r 后缀编号说明
- `25_general/_README.md`：更新命名规范 + 活跃 R 列表含子型列
- `20_groups/overlays/overlay_atlas.md`：删除 DS1001 预划行
- `70_tools/t2ag_doctor.py`：R 文件 glob 从 `R*.md` 改为 `*.md`（排除 _README.md）
- `00_core/t2ag_memory.md`：通识轨指针更新为 PHIL1101r, DS1001r
- `t2ag.md`：通识轨行更新路径格式 + 子型说明
- `00_core/t2ag_flow.md`：图 6 更新为含子型分流

---

## [2026-07-08] v0.0.07 宪法序言定稿 + 教师红线注释

**宪法序言定稿**：t2ag.md 第一章之前新增「序」节，由学生（mikp from t2ac）执笔。七段——
1. 无强制力（root 权限在学生，如无人能强迫你进健身房）
2. 存在原因（一个学生小小的祈求：疲惫时仍有可信的东西）
3. 机器职能（留痕与降价：把"开始"缩到最小，甚至抬起一根手指；把行为产生结果变成可查账事实）
4. 自律重定义（不是人格特质，不是神经结构缺陷，是今天做不做那个被缩小的动作）
5. 状态优化（效率工具假设操作者恒定，本系统假设操作者会受伤；状态是能力的母体；"问"是时代留给人的位置）
6. AI 时代（即使机器集群不再需要你，人选择去做只因自己想做）
7. 收束（现在，让我们再试一次）

**过渡句**：第五段加入"这样的假设听起来悲观，其实是这套系统全部的下注：只要把状态照顾好，其余的东西会自己长出来"，焊接"悲观假设"与"状态是母体"两个论点。

**序言防腐纪律**：序言与宪法同受第五章修宪程序管辖，系统功能变动时对应句子同步修——序言是对读者的承诺，承诺不许过期。

**三层齐备**：宪法管规则，账本管证据，序言管理由。

**教师红线注释**：`teacher_overlay.md` 情绪使用红线节新增「条款存在的理由」注释——本系统拥有操控所需的一切材料（情绪档案、行为记录、亲密的长期关系），正因如此上述红线不是礼貌是隔离墙。检验标准：操控系统害怕被审计，本系统邀请审计。

### 修改文件
- `t2ag.md`：第一章前新增「序」节（7 段 blockquote + 序言纪律）+ 落款 yours sincerely, mikp from t2ac
- `teacher_overlay.md`：情绪使用红线节新增「条款存在的理由」注释
- `00_core/preface_draft_s002.md`：存档用户手写原稿 v3（定稿版）

---

## [2026-07-08] v0.0.07 通识轨（R 系统）入库 + 容器类型裁定

**宪法裁定**：R（Reading track）不违反"最后一个新层"红线。R 不是第六层，是第二层的第二种容器——层级链仍是"培养方案 → 容器 → 内容 → 记录 → 资产"，只是容器现在有 G（刚性组）和 R（弹性轨）两种。判据是"成功标准在性质上不同吗"：G 的成功是外部刚性验证（卷面、红线、仪式），R 的成功是内部记录的诚实（读了什么、混了什么）。性质不同，分容器成立。"容器类型"这个概念从此正式存在，再有人想加第三种容器，判据同一条。

**四条修正**（按重要性排）：
1. **R 不抵账**（第六条规则）：R 永远不得作为 G 未达标周的解释、补偿或替代。周复盘发现"红线破了而 R 读量大增"时，这个组合本身按信号处理——"阴跌中弃仓、去摸感觉好的东西"的学习版
2. **状态枚举补 dropped**：idle/reading/paused/done/dropped。弃读是通识阅读最常见的结局，需一句话原因，不算失败算诚实——失败留痕传统在 R 里的最低配版本
3. **自测即仪式**：完全无写回锚点是档案腐烂的教训，R 的解法是把"每阶段自测三件套"定义为唯一仪式锚。仪式频率从 G 的每课一次降到 R 的每阶段一次，成本贴合密度，机制不缺席
4. **doctor 加 reading R > 2 → WARN**：能机械化的就不该靠自觉

**概念修正**：25_general 的编号注释从"课程组之下、课程之上"改为"与组同级的另一种容器"——R 是自包含孤岛，不在 G → course 依赖链上

**R 的政治功能**：R 最大的贡献不是给周易找了个家，是给 G 的刚性上了保险。R 存在前，每个弹性愿望都只能通过游说 G 放松实现；R 建成后，弹性有了合法居所，再没有理由动刚性的规则。泄压阀保护的是锅炉。

### 新增文件

- `25_general/_README.md`：目录说明 + 活跃 R 列表 + 状态流转（含 dropped）+ 与 G 的关系
- `25_general/R01_ZhouYi.md`：周易通识轨项目（历史/方法/五条纪律/12 循环阅读计划/三件套自测/内联 mistake_bank/教师红线）
- `50_playbook/general_learning.md`：通识轨规则 playbook（六条核心规则 + D4 兼容 + 自测即仪式 + doctor 对接 + R 政治功能）

### 修改文件

- `t2ag.md`：版本升至 0.0.07；结构清单新增"通识轨"行 + "通识轨规则"行
- `t2ag_memory.md`：当前状态指针新增"通识轨活跃项目"行；版本升至 0.0.07；最近变更摘要刷新
- `t2ag_doctor.py`：新增 `check_general_track()`——R 文件状态合法性 WARN + reading R > 2 WARN
- `AGENTS.md` / `README.md`：版本号升至 0.0.07

### 版本号说明

v0.0.07 背后第一次站着三个立法者：用户（共同起草人）、agent（系统执行者）、和写出原始提案的新老师（提案者）。

---

## [2026-07-08] v0.0.06 教材结构统一重构 + book_management.md

- **新增 `50_playbook/book_management.md`**：教材分类规则（primary/reference/course_materials/archives 四分法 + README 必须内容 + OCR 产物管理）
- **CS1953_book 重构**：主教材移入 `primary/`，笔记移入 `reference/`，课件/大纲/代码清单/补充移入 `course_materials/` 子目录，新建 README
- **MATH1607H_book 重构**：陈纪修第三版 4 个 PDF 移入 `primary/`，高数笔谈+习题答案移入 `reference/`，删除 `archives/tmp_toc/`（OCR 临时产物已完成使命），新建 README
- **PY1001_book 重构**：Python Crash Course 3 个文件移入 `primary/`，ATBS+Think Python+Python for Everybody+Docs zip 移入 `reference/`，README 路径更新
- **t2ag.md 结构清单**新增教材管理行
- **doctor 验证**：0 FAIL 0 WARN

---

## [2026-07-08] v0.0.06 overlay 重构 + 宪法 2.7 + doctor 增强 + 全小写统一

- **P1: overlay 重构**：
  - `plan_v2_4h.md` → `overlays/overlay_daily.md`（日维度）
  - `plan_313.md` → `overlays/overlay_cycle.md`（周期维度）
  - `plan_v3.md` → `overlays/overlay_march.md`（组维度）
  - `plan_v4.md` → `overlays/overlay_atlas.md`（全局维度）
  - 四文件移入 `20_groups/overlays/` 子目录，实例与模板分离
  - G01.md / G02.md / _README.md / course_info.md / course_group_rules.md 引用全部更新
  - t2ag.md 结构清单新增「方案 overlay」行
- **P1: doctor 新增 overlay 检查**：
  - 孤儿 overlay（未被任何 Gxx.md 引用）→ WARN
  - 断链引用（Gxx.md 引用不存在的 overlay）→ FAIL
- **P2: 宪法 2.7**：tools 与 playbook 永不合并（确定性归机器，裁量归智能体）
- **P2: doctor 边界声明**：文件头明确职责边界
- **P2: skin welcome_msg 指令词检查**：含疑似教学指令词 → WARN
- **P3: skeleton REGEN_TEST.md**：再生自证清单 5 大类 20 项
- **品牌名修复**：README.md `by T2AG` → `by T2AC`
- **全小写目录名**：t2ag / t2ag-skeleton / t2ag-lite
- **t2ag-lite 重新生成**：79 files, 0.43 MB
- **doctor 验证**：主项目 0 FAIL 0 WARN；skeleton 0 FAIL 1 WARN；lite 0 FAIL 1 WARN

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
- **文件夹重构**：工作区根内含 `T2AG\`（主项目）+ `T2AG-skeleton\`（骨架，独立 git 仓，与主仓同级）
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
- **skeleton 分仓**：T2AG_skeleton 移出主仓 → 与主仓同级的独立目录，独立 git init
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
- 路径：主仓内 `T2AG_skeleton/`（分仓前的嵌套位置）

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
