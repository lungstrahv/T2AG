# Tools 工具脚本目录

> **这里放什么**：确定性检查脚本——doctor 体检、state_refresh 缓存刷新、artifact_registry 迁移登记。
> **谁写・谁读**：系统演进时维护；每次验收和结课时自动运行。
> **什么时候来这里**：想跑体检（doctor）、刷新缓存（state_refresh），或查迁移登记。

tools = 确定性检查，playbook = 裁量流程（宪法 2.7）。

0.2.1 收口新增：

- `migration_txn_021.py`：profile/ActivityRecord 迁移共用的 durable transaction 协议；
- `migrate_021_activity_records.py`：reading ActivityRecord 分类迁移与 Main-only 证据；
- `t2ag_reading_bridge.py`：T2AG owner 的 context export、candidate import 与 receipt outbox；
- `contracts/reading_bridge_v1/`：与 Skeleton、辅助阅读系统逐字节一致的六份 schema 和严格校验器。
- `test_021_closeout.py`：迁移事务、ActivityRecord、Attempt、桥接与 Lite 回滚反例；
- `test_021_saga.py`：只在显式临时根运行的双仓 LOOP 与三类中断恢复验收。

桥接工具只写本仓 sidecar，不读取或启动辅助阅读系统；跨仓调用由外部 saga 编排层完成。
