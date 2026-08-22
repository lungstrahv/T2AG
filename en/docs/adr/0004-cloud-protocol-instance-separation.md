---
adr_id: ADR-0004
portable_key: cloud-protocol-instance-separation
status: accepted
authority_project: T2AG
source_evolution: [EV-0021]
supersedes: []
implementation_refs: [main/70_tools/sync_cloud.py, main/50_playbook/cloud_instructions_template.md, main/50_playbook/cloud_learning_sync.md]
---

# ADR-0004：Cloud 协议/实例分离与开源边界

## 背景

T2AG 的 cloud 块由五种功能混居一个目录：协议定义（`cloud_learning_sync.md`）、执行投影
（`T2AG_PROJECT_INSTRUCTIONS.txt`）、基线缓存（`t2ag_mobile_entry.md`）、同步账本
（`cloud_sync_state.md`）、信道存档（`outbox/` `inbox/`）。其中执行投影是**手工维护的
双身份文件**：协议规则（可开源）与实例身份路由（课程、教师映射、防冒充句尾标记）逐行
交织。协议 playbook §九要求"提示词一致性"，但只有散文，没有任何机器检查——与 2026-08-08
全面审查结论一致：漏洞产地在散文强制层。

开源压力使该混编从"维护不便"升级为"泄漏面"：句尾标记是防冒充共享秘密，开源即失效；
t2ag-lite 因 `sync_lite` 有意保留 cloud 文本而完整携带实例账本与信道存档。

## 决定（2026-08-09 用户三连裁决）

1. **协议/实例分离，投影可再生**：`T2AG_PROJECT_INSTRUCTIONS.txt` 降格为生成物。
   协议模板 `main/50_playbook/cloud_instructions_template.md`（parity 覆盖、含占位符、零实例值）
   + `t2ag_mobile_entry.md` 实例字段，经 `sync_cloud.py` 组装。手工直接编辑生成物视为漂移，
   由 doctor 报 FAIL。
2. **开源边界仅 skeleton**：cloud 块唯一开源面是 t2ag-skeleton（generic_skeleton 模式，
   已验证零个人痕迹）。t2ag-lite 是审查快照，不是开源底稿。实例层（mobile_entry、账本、
   信道存档）永不进入开源面。
3. **reply_suffix 写机制不写值**：防冒充句尾标记的**机制**进入协议层与开源面（使用者知道
   有此防线），**具体值**只存在于实例文件。泄漏扫描把"值出现在 skeleton 或模板"定为 FAIL。

## 信任边界变化

之前：云端提示词内容的正确性依赖维护者每次手改时人肉对齐 playbook 与实例状态。
之后：协议内容的真相源是 parity 覆盖的模板（skeleton 同步天然成立），实例内容的真相源是
mobile_entry；投影文件本身不再承载任何独立事实。

## 后果

- 0.2.0 桥恢复时，重发基线只需再生（mobile_entry 更新 → `sync_cloud.py --write`），
  不再手工重写 188 行提示词。
- skeleton 的 cloud 隔离从"当前恰好干净"变为"有扫描闸门的不变量"。
- 代价：新增一个模板文件与一个工具；模板修改需经 parity 同步，比直接改提示词多一步。
