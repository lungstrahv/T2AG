# T2AG 0.2.2 Skeleton 启动指令

本目录是空实例原件。进入后先读 `main/t2ag.md`。Agent 池上限为 6、同时运行上限为 3
（均包含 Main）；默认启动一个主 Agent与两个辅助 Agent。完成态释放并发槽，池满时优先
复用。主 Agent立即展示欢迎并保持唯一用户界面；Runtime Sentinel 只读并行运行：

```powershell
python -B main/70_tools/t2ag_doctor.py --profile runtime
python -B main/70_tools/t2ag_state_refresh.py --check
```

Context Prefetcher 同时运行 `python -B main/70_tools/t2ag_context.py --format critical`，立即
回交后再以相同 snapshot 运行完整 Markdown L0。
三路按 `main/50_playbook/startup_orchestration.md` 分两阶段汇合；L0-critical 可信且没有
已知教学阻断时，非 textbook 可进入 `learning-ready`；textbook 必须再完成同 snapshot 的
全 Scope 文本消费与本轮逐页视觉扫描。Snapshot、历史 receipt 或哈希不得冒充本轮扫描。
Lesson 权威 pending prompt 必须逐字来自 progress 精确停点并标明来源；模型可以附加明确
标注的概括、暖场、类比或探索问题，但不得替换权威停点、掩盖冲突或绕过 Exercise 提示闸门。
当前页 source 必须与 `pdf_page_index` 一致；冲突即停。每个 Lesson 首次开讲或尚未完成开场
确认时，先概括学习内容、显示 ASCII 知识树，并询问路线感受与是否进入第一块；概览不计覆盖
或掌握。写入、checkpoint、terminal 与“状态全绿”宣称必须等待
`recovery-settled`。critical 目标 ≤10 秒、非 textbook 首条内容 ≤15 秒、完整收敛 ≤45–60 秒。
课堂创造性互动默认允许；硬边界只有不提前泄露未请求的习题答案/解法结构、不跳过必学
内容。额外习题默认不自动生成，只在学生请求或明确 opt-in 后生成；即时理解确认不算额外习题。
Main 收到 critical 后不重复调用 context；仅 critical 超时且分支终止时降级一次。空模板必须返回
`status=first_run_required`，再执行 `main/50_playbook/first_run.md`；初始化后使用
同一只读 L0 上下文包，禁止把包落盘为第二真相源。推进当前一步需要追加已有直接证据
时使用 `--include-l1`；成本账以完整序列化 Markdown 为预算口径。
textbook 第一条内容前必须消费 `page_teaching_contract`，显示字符课堂树与当前页覆盖清单。
每轮只引入一个新教学块；理解确认、推导/总结后的感受反馈和下一块的一次性继续授权不得
合并。正确作答或开场“继续学习”不授权后续所有块。翻页须先展示旧页清单，再宣布
“PDF N / 书内 M”、展示新页树并单独取得继续授权。

首次判据仍是 profile 未初始化、含必填占位符，或 memory 上次课日期为 `—`。不得创建
学生编号包装层，不得预填真实实例，也不得自动创建、删除、重建或升级 `.venv`。

## 最小充分验证

除非用户明确要求“正式版本升级、发布、完整审查”，所有调整默认采用最低足够级别：

- V0 文档或课程内容：只检查改动文件。
- V1 局部实现：只跑直接相关测试；最多运行一次 runtime Doctor。
- V2 schema、核心契约或 Main/Skeleton 同源实现：相关测试、contracts 与同源检查。
- V3 真实迁移或正式发布：完整测试、exact shadow、故障矩阵、独立复审、Lite 与 FIN。

禁止把普通优化自动升级为 V3。finding 修复先做后续路径静态审查与针对性回归；SHA
未变且依赖未受影响的证据允许复用。启动编队不改变施工预算；普通任务默认预算为一个辅助 agent、三个测试命令
和十分钟；普通验收不扫描 .venv、Lite、旧 recovery/staging、教材或图片。默认 Doctor
profile 是 `runtime`；只有正式候选、跨发行同步或发布审计显式使用 `--profile release`。

## 测试组合规则

`main/70_tools/validation_workflow.json` 是 Doctor profile、V0–V3、普通预算与防越级门的
唯一控制文件。完整 runtime Doctor 是启动例外，先列固定计划后可直接执行一次；定向
Doctor 和全部 release 执行必须先核对 plan SHA。release 还必须登记明确 reason，不能以
“更保险”为由从普通任务自动进入。流程树见 `main/50_playbook/validation_flow.md`。

测试能力长期保存，现场组合临时生成。以 `main/70_tools/test_dependencies.json` 为唯一测试
库存与依赖清单，用 `main/70_tools/t2ag_test.py` 按 component、changed path 或稳定 test ID
生成内存执行计划；不得生成并删除一次性 Python 测试文件。先用 `--plan-only` 列出组合，
再以完全相同的选择参数和 `--execute-plan <PLAN_SHA>` 执行。普通任务只选 `fast`，核心事务或受影响迁移才选
`deep`，冻结候选或正式发布才选 `release_only`。完整规则见
`main/50_playbook/test_strategy.md`。

发布测试同样按 receipt、evidence、gate、fault、shadow 分域选择；普通 changed-path 映射
不得指向完整发布集合。只有用户明确要求冻结候选或正式发布时，才可显式选择无自动映射的
`release_suite` 聚合组件生成只读计划；领域测试与物理根 scenario 再按该计划分别显式执行。

runtime/release Doctor 分层、测试选择器、依赖清单及其契约是 Main、Skeleton、Lite 的共同
基础内容；控制文件与树形流程也属于同一基础面。Main/Skeleton 执行，Lite 只读携带；不得
把它们降为某个形态的可选附件。

## 授权不可放大与闭环止损

验证级别与授权级别相互独立；V0–V3 只决定证据成本，不改变批准权。

- `continuous execution`、`version_campaign` 或概括性的持续许可只覆盖明确列举的 RT1/RT2，
  不覆盖任何 RT3。
- 真实迁移、terminal lifecycle、严格学生确认和跨边界写入，必须在 exact object、exact
  body、ID、SHA 和结果均已展示后，由用户当轮重新直接确认。
- 旧对话、连续委托、委托收据、确定性 policy、模型推荐及技术复审结论均不得替用户生成
  未来 E/F 授权；尚未生成的 ID、正文、结果或 hash 不可预授权。
- 对话压缩、恢复或交接后，授权范围只能保持或缩小；无法重建精确边界时停止在 RT3 前。
- 实现者和复审者只能判断技术证据，不得替用户作 RT3 决策；RT1/RT2 施工授权不包含真实
  记录、课程状态或 terminal result 的处置权。

正式 campaign 开始前冻结验收规范及版本、完成定义、最大整改轮数、完整复审次数，以及
测试、时间与 token 预算。默认最多两轮 finding 整改和两次完整候选复审。达到任一预算
上限即输出已有证据与未闭合项，状态记为 `stopped_budget`，等待用户决定；不得换 RD 编号、
重冻同类 package、新建续单或拆分同一 finding 规避上限。新增标准若揭示既有安全或核心
契约违反，应停止并报告，不得自动扩张完成定义或生成下一轮 RD。

## 规则语义迁移

版本更新或治理面大改删除、合并、概括、迁址、退役现行规范性正文，或改变具名硬边界的
owner/触发/授权/结果时，必须登记 rule_migration；纯追加、格式和保义澄清可写
`not_applicable`。默认 diff-patch；整文件重写须先冻结完整迁移表并复核未登记删除。
文件长度、历史清单和模型建议只是复核信号，不是规则或授权源。完整契约见
`main/t2ag.md` §6.3。
