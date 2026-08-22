# T2AG 0.2.3 agent 入口

进入本仓库先读 `main/t2ag.md`（宪法）：不可变原则、各域结构与全部 canonical 指针都在那里。
本文件只做仓内引导，不复述规则；与宪法冲突时以宪法为准。

- **启动**：欢迎信息与两条只读恢复分支并行；编队、命令、handoff 字段与两阶段汇合
  canonical：`main/50_playbook/startup_orchestration.md`（§零–§五）。
- **接管**：即时摘录、L0/L1/L2 分层、课程选择与 Main 消费纪律 canonical：
  `main/50_playbook/context_packet.md`。
- **textbook 扫描门**：开讲前须完成本会话 Scope 扫描（A1–A6，ADR-0003：宿主可观察投递
  证成）；Snapshot、历史 receipt、哈希、仅 frontmatter 不得冒充本轮。canonical：
  `main/50_playbook/source_page_assets.md` §3.1。
- **教学门**：三门协议与块间过渡、翻页、开场、提示闸门见宪法 §1.6/§4 与门台账机制
  （EV-0018）；每轮最多一个新教学块，「继续」用后即失效。
- **验证与授权**：V0–V3 与测试组合按宪法 §6.1 所引 canonical；授权不可放大与闭环止损
  canonical：宪法 §6.2（含 `stopped_budget` 状态与测试/时间/token 预算上限）。
- **状态宣称**：runtime doctor `0 FAIL` 且 state 无漂移后才可宣称本地闭合；写回顺序
  见宪法 §5。

角色差异：本文件面向已进入仓库的 agent。**单实例安装时本文件即全部入口**——
把本仓解压/复制为一个目录后，该目录就是工作区，不存在上一级引导文件。
只有维护多发行版的工作区（同级并列 `t2ag/` / `t2ag-skeleton/` / `t2ag-lite/` / `docs/`）
才另有一份 `../AGENTS.md` 负责跨仓路由；单实例用户不需要它，也不应去找。

首次启动不依赖本文件：`t2ag_context.py` 返回 `first_run_required` 时，
其 `next_action` 字段会机械指向 `main/50_playbook/first_run.md`。

## 遍历指引（首启不必全读）

首次进入**不必遍历全仓**（全仓约 220 文件 / 4.5 MB）。只读 `README.md` →
`main/t2ag.md`（宪法），再跑 `python -B main/70_tools/t2ag_context.py`，
按返回的 `next_action` 走即可。以下目录在首启阶段**不需要读**：

- `main/70_tools/`（实现与测试，工具由命令行调用而非通读）
- `main/60_journal/`（本实例决策登记簿，起步为空模板）
- `docs/`（架构决定与设计协议记录，需要审计决策来源时再查）
