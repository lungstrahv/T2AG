# 跨仓引用管理（两档标准）

**保护级别**：playbook

> 本文件是 T2AG「技能固化」文档之一。
> 当 T2AG 任何文件需要引用本仓之外的仓库/系统（如交易复盘系统、阅读辅助系统等对端仓），
> 或发现现存仓外引用没有合同保护时触发。
>
> **适用场景**：engagement 挂载仓外权威、课程引用仓外数据、新外部系统接入评估、
> 仓外文件断链/漂移处置、绑定版本升级（重绑）。
>
> **关联文件**：
> - 合同 schema：`main/70_tools/contracts/external_reference_v1/t2ag.external_reference.v1.schema.json`
> - 全桥范例：`docs/design/T2AG_READING_BRIDGE_CONTRACT_V1.md`（saga 档）
> - 首个实例：`main/10_student/engagements/EG-0001_TradingDiscipline/external_refs.json`
> - 溯源：`main/00_core/t2ag_problemlog.md` P-0060
>
> **裁决记忆**（2026-08-08 用户裁决）：外部仓的目录分层是其领域语义，**不因目录美学
> 改造对方仓**；T2AG 只对齐接口方式与治理文件可发现性。

---

## 一、两档标准（先分档，再施工）

| 档 | 适用 | 载体 | 禁止 |
|---|---|---|---|
| **T1 引用合同** | 单向只读引用仓外文件（权威文档、数据源） | 引用方目录下 `external_refs.json`（`t2ag.external_reference.v1`） | 在 T1 场景搭传输 schema、ledger、回执等无消费者设施 |
| **T2 saga 全桥** | 双向数据交换（候选贡献回流、回执） | reading_bridge_v1 式三合同 + 两仓逐字节 schema 副本 | 在只读场景使用；升档须有真实回流需求作为证据 |

**分档判据**：对端是否需要接收 T2AG 产出？否 → T1。是 → 先确认回流需求真实存在
（有具体消费者、具体触发事件），再按阅读桥模式立 T2。**没有任何合同的裸引用是唯一
被禁止的形态**（P-0060 的原罪）。

---

## 二、T1 合同的硬规则

1. **绝对路径只许出现在 `peer_root_hints`**。正文、frontmatter、表格一律用
   逻辑名（`external_refs.json#<reference_id>`）或对端仓内相对路径。
   引用身份 = `peer_system` + `peer_relative_path`；root hint 只是环境解析提示。
2. **frozen_version（权威文档）**：必须 `pinned` + `content_sha256` + `peer_version`。
   SHA 由真实文件计算（`sha256sum`），禁止手填或从记忆复述。
3. **living_data（活数据）**：必须 `existence_only` + `copy_on_use`。不锁 SHA——
   活文件锁 SHA 只会制造永久假警报。
4. **copy_on_use**：任何 T2AG 文件引用活数据中的具体内容时，把用到的行/段原样拷入
   本仓证据，附当日源文件 `sha256` 与日期。禁止只留行号、"见台账"或其他活引用——
   半年后回看时证据必须还是当时的样子。
5. **重绑仅限人工**（`rebind: manual_only`）：doctor 报漂移 ≠ 自动更新 SHA。
   人工确认对端新版本后，同一次提交里更新 `content_sha256` + `peer_version` +
   `bound_at`，并在引用方文件留一行版本变更记录。对端有冷静期条款的（如 Trading-OS
   放宽类修改 7 天冷静期），重绑前先核对冷静期已满。

---

## 三、新增仓外引用步骤

1. 分档（§一）。T2 → 走阅读桥模式，本文件不覆盖。
2. 在引用方目录创建/追加 `external_refs.json`，按 schema 填全字段。
3. `sha256sum` 实算 pinned 文件的 SHA；确认 living_data 文件存在。
4. 引用方正文的仓外提及全部改为逻辑名或对端相对路径；`grep -rn "C:/Users"` 复查
   该目录，命中数应为 0（sidecar 除外）。
5. doctor 跑 `external_references` 检查项确认 0 FAIL。
6. changelog 登记（新引用 = 结构变更）。

## 四、断链/漂移处置

| doctor 结果 | 含义 | 处置 |
|---|---|---|
| FAIL：root 不可达 / 文件不存在 / sidecar 损坏 | 断链 | 先修解析（对端搬家→只改 `peer_root_hints`），不动引用身份 |
| WARN：pinned SHA 不匹配 | 对端已改版，绑定过期 | 读对端变更内容 → 人工决定重绑（§二.5）或回退对端误改 |
| PASS | 绑定健康 | 无动作 |

---

## 五、常见坑

- 在历史档案（`60_journal/` 等）里追杀绝对路径——档案是当时的事实，不改。
- 给 living_data 上 pinned——每次对端追加数据都假警报，最终导致警报疲劳。
- 报 WARN 后顺手把新 SHA 写回 sidecar「让检查变绿」——这等于自动同步，破坏
  显式重绑语义；漂移必须先看对端改了什么。
- 为 T1 场景预建 T2 设施「以后用得上」——无流量基础设施会腐烂（阅读桥 batch C/R/T
  建成后长期无真实写入即为先例）；升档条件是真实回流需求出现。
