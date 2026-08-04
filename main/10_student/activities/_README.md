# ActivityRecord 空模板域

首次启动前不创建真实 `AR-*`。只有发生了实际活动且用户确认记录时，
才按 `activity_management.md` 创建稳定 ID 文件。

合法结构为 `activities/<activity_kind>/AR-NNNN_Title.md`；0.2.1 初始只登记 `reading/`。
Skeleton 不得保存真实 AR 或 sidecar。
