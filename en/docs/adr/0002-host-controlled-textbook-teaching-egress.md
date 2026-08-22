---
adr_id: ADR-0002
portable_key: host-controlled-textbook-teaching-egress
status: proposed
authority_project: T2AG
source_evolution: [EV-0013]
supersedes: []
implementation_refs:
  - docs/protocol/host-teaching-egress-api.md
  - docs/protocol/textbook-scope-scan-admission.md
  - main/70_tools/host_teaching_egress.py
  - main/70_tools/t2ag_context.py
---

# ADR-0002: 宿主控制的教材教学发送边界

**Status:** proposed  
**source_evolution:** EV-0013  
**Also:** accepted in principle for the architectural shape — **blocked on host-runtime
enforcement** (no claim of a structural hard gate until that exists)

## Context

真正的决策不是“引入 receipt 和 capability”，而是：

> **教材教学输出必须经过模型无法绕过的宿主级发送边界。**

`ScopeVisualScanReceipt` 与 `TeachingAdmissionCapability` 是实现该边界的**协议对象**，
不是边界本身。上一版以 capability 为标题、并标 `accepted` 的写法会误导读者：仓库里若
只有字段与 playbook，就等于宣称已有硬门。

当前实现曾长期只有**策略门**，没有**执行门**：

- （历史）critical 可同时返回 `status: ready`、`blocking_teach: false` 与
  `scope_scan_status: pending_visual_scan`、`may_release_action: false`（混合信号）。
- Learning-ready 条件由 Main Conductor 裁决，Main 又是对外发言者；信任链是
  `读字段 → 模型判断 → 同一模型发言`。
- Context Prefetcher 在 handoff 中写 `opened=true` / scan complete 仍是 Agent 文本声明，
  不是不可伪造的工具事件。
- 备课 `LoadReceipt` 只证明 prepare 时加载过页面，**不能**冒充本会话 Scope 视觉扫描
  （见 `source_page_assets.md`）。

**Defense-in-depth（已落地，仍非硬门）**：`t2ag_context.py` 在 Scope scan pending 时输出
`status: route_ready`、`blocking_teach: true`、`admission_status: unavailable`、
`egress_mode: status_only`，并 withhold 可照发教学正文；负向测试见
`test_context_packet.py`。这 **reduces accidental policy bypass but does not establish a
structural teaching-output gate. Host-runtime enforcement remains required.**

在尚未存在宿主 message interceptor、强制 `lesson_emit`、会话输出事件日志、不可伪造
capability store 之前，不得将本决策标为已实现的 hard gate。

## Decision

### 架构决策（本 ADR 的唯一硬承诺）

1. **宿主拥有最终发送权。** Agent（含 Main Conductor 与 Prefetcher）不属于教学 egress
   的可信计算基（TCB）。
2. **教材教学正文只能经宿主控制的 emission boundary 出站**（规范名：`lesson_emit` 或
   等价宿主 API）。验证、reserve、发送与事件写入由宿主执行。
3. **在 textbook gated session 中，普通 assistant 出口必须关闭，或仅允许宿主固定模板**
   （例如“正在核对教材页面”）。模型不得经自由文本通道承载教材教学正文。
   “建议用 `lesson_emit`”或事后语义分类是否教学 **不构成**硬门。
4. **Runtime Join Gate 是宿主运行时中的确定性验证器**，不是 Main 的推理步骤。Agent 不得
   同时持有：请求权限、判断证据、批准权限、发送权限。
5. Packet / playbook 字段**只用于可观察性与诊断，不构成授权**。发送层只承认当前有效的
   **服务器端** admission；模型可见 JSON 永远不是权限源。

### 协议实现（非本 ADR 的替代决策）

边界之上的对象、事件与失效规则见：

- `docs/protocol/textbook-scope-scan-admission.md` — receipt / admission 协议
- `docs/protocol/host-teaching-egress-api.md` — `lesson_emit` / 通道模式 / 返回码 / 原子流程
- `main/70_tools/host_teaching_egress.py` — 纯状态机与契约测试锚点（**不**发送消息）

摘要（防止只读 ADR 时断章）：

| 对象 | 角色 |
|---|---|
| Host Scan Orchestrator | 聚合 PageViewOpened → ScanJobCompleted；签发 receipt |
| ScopeVisualScanReceipt | 可验证的**访问与呈现**证明，非“模型已理解” |
| Runtime Join Gate | 宿主验证器；签发 server-side TeachingAdmissionCapability |
| TeachingAdmissionCapability | 宿主侧一次性、绑 **block_id**（可选 **block_version**）的对象；模型只调 `lesson_emit`，不持有令牌正文 |
| lesson_emit | 再验 snapshot、绑 block、**原子** validate→reserve→send→commit consumed + event |

`learning-ready` 与 `recovery-settled` 的区分**保持**。fail-closed 的“后台仍在运行”仅指
与 admission 直接相关的工作（Scope scan job、receipt 聚合、admission 验证），**不**把
Runtime Sentinel / 完整 L0 / Doctor 并回同一闸门；后者仍走既有 settled 规则。

### 设计收口（接口结论，2026-08-06）

1. **Admission 绑定**：必选 `teaching_block_id`；可选 `teaching_block_version` 作为内容谱系钉。
   有 version 则 emit 必须匹配；无 version 则仅 id。不是整页/整课通行证。
2. **Capability 状态**：`issued → reserved → consumed`，失败可 `aborted`，另有 `revoked` /
   expired。禁止 `validate → mark used → send`。
3. **审计落账**：`TeachingBlockEmitted` 仅在**发送成功之后** commit；reserve 可有宿主私有日志。
4. **固定状态模板**：与教学共用 egress 边界，经 `status_emit`；模板正文宿主持有，模型不得
   填自由散文。
5. **textbook gated 通道**：
   `freeform_egress: disabled` · `status_template_egress: host_only` ·
   `teaching_egress: lesson_emit_only`。

### 仓库内 defense-in-depth（已做，仍非硬门）

- critical 扫描前：`status: route_ready`、`blocking_teach: true`、
  `admission_status: unavailable`、`egress_mode: status_only`；
- withhold 可照发的 `textbook_excerpt`、first teaching candidate、可复制开场正文、`prompt`；
- 负向测试：`PendingScopeScanWithholdTests`；宿主契约测试：`test_host_teaching_egress.py`。

这些**不得**被宣传为“已实现结构性硬门”。

## Considered Options

| 方案 | 结论 |
|---|---|
| 再加 `teaching_released` 等布尔 + Doctor | 拒绝：可忽略、事后、无 TCB 边界 |
| receipt → Join Gate → capability，但 Join Gate 仍由 Main 执行 | 拒绝：信任边界未变 |
| 模型可见 capability JSON / 模型自带令牌正文 | 拒绝：可复制伪造；须 server-side 或发送层验证的 opaque 句柄，且最好模型不可见 |
| 有 `lesson_emit` 但普通 assistant 仍自由 | 拒绝：可绕过；须关闭或固定模板 |
| 语义分类器过滤自由文本是否“像教学” | 拒绝作为硬门：漏判 + 伪装 |
| 宿主控制 egress + 普通通道关闭/模板化 | **选用**（架构） |
| 把全部后台（含 Doctor）并入 teaching fail-closed | 拒绝隐含并入：会取消 `learning_ready_first`；另立决策 |

## Consequences

- **硬门依赖宿主运行时**，不在纯 Markdown + 无约束 chat 出口内闭合。在宿主能力落地前，
  状态保持 **proposed / blocked on host enforcement**。
- 需会话内事件日志（至少 receipt、capability 签发/消费、TeachingBlockEmitted）与
  emission 幂等键，否则无法 audit 与原子消费。
- 与现有 Startup Formation / Prefetcher 兼容：Prefetcher 可触发扫描任务，但**不得**自报
  complete 作为授权依据。
- 后续块（理解 / 感受 / 继续 / 翻页）可复用“宿主签发 block-scoped capability +
  `lesson_emit`”模式；每块新 capability，不是整页/整课通行证。
- 上一版 capability 中心表述作废；以本文件与协议规格为准。
