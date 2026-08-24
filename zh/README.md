# T2AG 0.2.3 Skeleton

> 空实例原件。它可复制为新的 T2AG 实例，但自身不得承载真实学生数据。
> 复制到任意新目录后，未初始化 profile 仍按 Skeleton 空模板验收；完成
> `first_run.md` 并把 profile 改为 initialized 后，该副本自动按个人实例验收，
> 不依赖目录名。被维护为发行源的 Skeleton 仓本身永远保持空模板身份。

空模板识别标记：`t2ag-skeleton`。复制后的目录可以自由改名；完成首次初始化后，
系统改由 profile 的 `initialization_status` 识别个人实例。

0.2.3 Skeleton 提供 activity ledger、exerciseNN 模板、原子 activity lifecycle/close 工具，
并保留分类 reading ActivityRecord 空容器和双向 JSON 候选桥接能力；它不含真实课程活动、
AR、书籍、sidecar、候选贡献或消费回执。两个系统始终各写各仓。

本 Skeleton 作为可复用开源基础持续维护，通用教学机制由真实实例反馈验证后再吸收，
但不携带真实学生、课程进度或个人原话。

**使用许可**：从公开 GitHub 仓取得的副本中，代码按 Apache-2.0、散文按
CC BY-SA 4.0 授权；路径边界见 `LICENSING.md`，归属声明见 `NOTICE`。公开之前由授权人
直接交付的邀请包仍按随包的 `INVITED_USE_GRANT.md` 执行。两类副本的适用许可不要混用。

## 一分钟启动与 Agent 偏好

默认可使用三个 Agent：一个主 Agent负责欢迎、用户交互、join 与唯一写回；Runtime
Sentinel 只读检查 runtime Doctor 和 state；Context Prefetcher 只读消费 L0 并回交最小
结构化 handoff。健康实例的时间目标按驱动分档（canonical 在 `startup_orchestration.md` §一）：
critical route ≤10 秒；**非 textbook** 第一条可执行学习内容 ≤15 秒；**textbook** 须先完成同
snapshot 的 Scope 文本与视觉消费，与完整 `recovery-settled` 一并以 45–60 秒为目标。
辅助 Agent 不可用时
降级，但不得跳过闸门。空模板 profile 使用 `agent_collaboration_preferences.v1` 的通用默认
`agent_pool_limit: 6`、`agent_max_active: 3`、`agent_parallel_startup: enabled`；前者是含
Main 的身份池容量，后者是含 Main 的同时运行上限，首次启动时可由学生覆盖。该偏好
还默认 `agent_startup_readiness: learning_ready_first`、后台只播报阻断项；它不授予写入、
结课、迁移或 RT3 权限。启动编队与施工辅助预算不同：日常接管可用两个只读辅助，普通
改系统/验证仍默认一个辅助、三条测试、十分钟。完整规则见
`main/50_playbook/startup_orchestration.md`。

## 快速开始

1. 先进入**包含本 README 的中文版本目录**，再把当前目录复制到一个全新的目标目录，
   排除 `.git/` 与运行缓存。这样既适用于独立 Skeleton checkout，也适用于公开双语仓的
   `zh/` 目录：

   ```powershell
   $target = Join-Path $env:USERPROFILE "Documents\my-t2ag"
   robocopy . $target /E /XD .git __pycache__ .venv .cache .recovery .staging .uploads
   Set-Location $target
   ```

2. 在目标目录按 `startup_orchestration.md` 并行运行三条只读启动支路
   （Main welcome ／ Runtime Sentinel ／ Context Prefetcher）。单 Agent 环境才降级为
   下列顺序执行——**注意五条命令属于上述三条支路，不是五条支路**，且
   **critical 必须先跑**（canonical 健康路径是 critical-first，Markdown 全量在其后）：

   ```powershell
   python -B main/70_tools/t2ag_context.py --format critical
   python -B main/70_tools/t2ag_doctor.py --profile runtime
   python -B main/70_tools/t2ag_state_refresh.py --check
   python -B main/70_tools/t2ag_context.py --format markdown
   python -B main/70_tools/t2ag_context.py --include-l1 --format markdown
   ```

3. 空模板的上下文命令必须返回 `first_run_required`；随后读取 `main/t2ag.md` 和
   `main/50_playbook/first_run.md`。
4. 与用户确认 profile、首门课程和首个 group 后再显式写入。

**预期输出**：全新副本上 `doctor --profile runtime` 应为 **`0 FAIL, 0 WARN`**。
若出现 `EA-0003 …可建文件但不能 unlink`，说明该目录所在的挂载不支持删除
（常见于容器对宿主目录的挂载）——此时**不要在该环境执行任何 git 写操作**，
换到宿主机执行；其余功能不受影响。见 `main/50_playbook/environment_assumptions.md`。
出现任何 **FAIL** 都不是预期，请先修再继续。

初始化后的来源库存比例只说明选择范围；软预算以完整序列化 Markdown（L0 及
L0+首个 L1）为准，不把该比例称为端到端 Token 降幅。

## 发行角色

- Main：规则与真实实例原件。
- Skeleton：通用规则与空实例原件。
- Lite：只能从 Main 单向生成的审查快照。

三个形态都必须携带 runtime/release Doctor 分层、原子检测控制文件、测试选择器、依赖
清单和树形流程。Main/Skeleton 可执行；Lite 只保留字节一致的只读审查副本。基础文件由
`t2ag_doctor.py` 的 `BASE_VALIDATION_FILES` 强制检查，不属于可选发布附件；完整流程见
`main/50_playbook/validation_flow.md`。

普通启动、doctor 和首次启动不得创建、删除、重建或升级 `.venv`，也不得自动
安装依赖、下载教材或生成真实 Engagement。测试按 `main/50_playbook/test_strategy.md`
从持久原子测试组合；现场计划只存在于内存和标准输出，不生成再删除临时 Python suite。
