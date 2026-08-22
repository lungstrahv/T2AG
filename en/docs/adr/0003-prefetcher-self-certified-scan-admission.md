---
adr_id: ADR-0003
portable_key: prefetcher-self-certified-scan-admission
status: accepted
authority_project: T2AG
source_evolution: [EV-0019]
supersedes: []
implementation_refs:
  - main/50_playbook/source_page_assets.md
  - main/50_playbook/startup_orchestration.md
  - main/70_tools/t2ag_context.py
---

# ADR-0003: 扫描准入的宿主可观察自证

**Status:** accepted　**source_evolution:** EV-0019

教材课准入原设计要求宿主 Scan Orchestrator 聚合 PageViewOpened 事件签发 receipt
（ADR-0002 族）。该组件在现宿主（Cowork/WorkBuddy）不存在且短期不会有（EA-0004、
P-0056），致 textbook critical 恒 `route_ready + blocking_teach=true`：「降级路径」成为
唯一路径，却被当临时态维护——每次教材启动都以一个永不满足的条件挂账。

**决定**：session scan complete 的正式判据改为——`source_page_assets.md` §3.1 的 **A1–A5
经宿主可观察的工具调用投递在本会话内证成**。证成前 pending 状态不得清除；无投递的自报
opened/complete、Snapshot、历史 receipt、哈希核对均不构成证成（§3.1.3 A 层「不得冒充」
条款原样有效）。A2/A4 全量预载语义不变。

**未来态**：宿主获得 orchestrator / interceptor 能力时回收签发权，恢复宿主签发判据并
supersede 本 ADR；ADR-0002 的 `lesson_emit` egress 边界同样保留为未来态。

**防线**：投递宿主可观察、SHA 链可复算、boot 恒 pending（编译器结构保证）、规范锚点
测试（`test_context_packet.py::ScanEvidenceSpecTests`）。留痕不防捏造，防发现延迟
（EV-0018 同判据）。

**裁决来源**：学生 2026-08-08 当轮三连裁决；施工单
`docs/handoffs/T2AG_SCAN_CONTRACT_NORMALIZATION_WORKORDER_2026-08-08.md`（工作区侧）。
