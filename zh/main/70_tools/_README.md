# Tools 工具脚本目录

> **这里放什么**：确定性检查脚本——doctor 体检、state_refresh 缓存刷新、artifact_registry 迁移登记。
> **谁写・谁读**：系统演进时维护；每次验收和结课时自动运行。
> **什么时候来这里**：想跑体检（doctor）、刷新缓存（state_refresh），或查迁移登记。

tools = 确定性检查，playbook = 裁量流程（宪法 2.7）。

0.2.1 收口新增：

- `migration_txn_021.py`：profile/ActivityRecord 迁移共用的 durable transaction 协议；
- `migrate_021_activity_records.py`：reading ActivityRecord 分类迁移与 Main-only 证据；
- `t2ag_reading_bridge.py`：T2AG owner 的 context export、candidate import 与 receipt outbox；
- `contracts/reading_bridge_v1/`：与 Skeleton 及对端阅读系统逐字节一致的六份 schema 和严格校验器。
- `test_021_closeout.py`：迁移事务、ActivityRecord、Attempt、桥接与 Lite 回滚反例；
- `scenarios/release_reading_bridge_saga.py`：release-only 双仓 LOOP 与三类中断恢复场景；
- `contract_test_support.py` 与四个领域测试入口：共享原子断言，不再由单个聚合文件全量调用；
- `validation_workflow.json` + `validation_control.py`：Doctor 原子项/profile、V0–V3、预算、
  plan SHA 与防越级控制。
- `test_dependencies.json` + `t2ag_test.py`：持久测试库存、依赖清单与计划绑定执行器。
- `test_release_*.py`：按 candidate、receipt、evidence、gate、fault、shadow 分域的发布原子契约；
- `scenarios/release_shadow_apply.py`：不进入普通发现的完整物理根 shadow 场景。
- `test_distribution_foundation.py`：三形态 Doctor/测试/流程控制基础内容的原子自检。
- `t2ag_source_pages.py`：EV-0012 页资产 Scope / load receipt / 不可变 Snapshot +
  `current_snapshot.json` 指针 / fail-closed prepare / 安全 CacheEviction
 （`prepare --current`、`cache-gc --dry-run|--apply`、`scope`）。
- `test_source_pages.py`：Scope 几何、稀疏失败、heat_at、P0/越界驱逐、Snapshot 幂等与
  覆写拒绝、CLI 参数、prepare 负向用例。
- `50_playbook/source_page_assets.md`：页资产与缓存的可执行流程。
- `host_teaching_egress.py` + `test_host_teaching_egress.py`：宿主教材教学 egress 纯契约
  （`lesson_emit` / freeform 关闭 / status 模板 / reserve→commit）。**不**发送消息、
  **不**构成结构性硬门；设计见 `docs/protocol/host-teaching-egress-api.md` 与 ADR-0002。
- critical packet withhold（`t2ag_context.py`）：scope scan pending 时 `route_ready` +
  剥离可照发正文；见 `PendingScopeScanWithholdTests`。
- `decision_record_contract.py` + `test_decision_record_contract.py`：Evolution Register
  ↔ ADR 确定性关联（无 CLI）；Doctor `runtime.decision_records` 调用。
- `build_journal_index.py`：支持通用 `journal_index: false`（redirect 不进生成索引）。

- `okf_export.py`：T2AG → OKF v0.2 知识包导出器（EV-0024，协议 `T2AG-OKF-1`）。默认
  check-only，`--write` 落盘到仓外 `t2ag-okf/`；`--scope mechanism|course:<ID>`；泄漏闸门
  在落盘前运行且词表复用 `t2ag_doctor.SKELETON_PRIVACY_PATTERNS`；`--check-bundle` 复算
  OKF §11 conformance。规范在 `50_playbook/okf_adaptation.md`，本工具是它的可复算实现。
  **不注册进 doctor**：bundle 是可选生成物，缺席不该阻断教学。

桥接工具只写本仓 sidecar，不读取或启动对端阅读系统；跨仓调用由外部 saga 编排层完成。
