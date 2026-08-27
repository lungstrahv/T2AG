# T2AG 版本台账（canonical，自宪法 §7 下沉 2026-08-08/EV-0020）

> **本文件是版本状态三字段（`implementation_status`／`candidate_review`／
> `release_qualification`）的唯一真相源**（CR-1=A 2026-08-23，P-0086）；
> `main/t2ag.md` §7 只指不载，当前运行版本号以 §7 首行为准。
> 旧头行「现行状态见 §7」构成循环指针，已废（08-23 审查改准）。
> **写入归属（08-23 裁、同日收窄为三分层）**：
> ①**源内在状态** `implementation_status`：随三仓源与包发行，重打前写入——
> 实例日后升版时 VER-BUMP 依赖前驱行；
> ②**生成后资格** `candidate_review`／`release_qualification`：权威值归 **Main 台账＋
> 独立评审证据**；Skeleton 与包内的 `not_run`／`not_claimed` 是**构建时快照**，
> 不冒充最终资格——V3 结果是包生成后的事实，要求它预先存在于被审包内即
> 「写通过→重打→新包未受审」的无限循环；
> ③**冻结绑定行** `release_candidate`（含包 commit）：包与来源 commit 确定后、
> **完整 V3 之前**只写 Main 台账并单独提交——Main 不打包无 commit 循环；
> V3 运行时若无绑定行，candidate_binding 走「无行→静默」分支，那次 V3 的绿即
> 缺覆盖的绿。绑定证明「审的是哪两个候选」，不证明「审查通过」。
> 绑定行两端必须 zh/en 各恰一次（CAND-BIND-004..006 强制，写坏/缺端/重复皆 FAIL）。

> **锚的解析根（P-0071 修，2026-08-21）**：下列六份权威 handoff 位于**工作区级**
> `<workspace>/docs/handoffs/archive/v0.2.x/`，**不在仓内** `t2ag/docs/handoffs/`。
> 此前本文件按仓内相对路径书写，两层皆错（根错一层、08-18 归档后又下沉一层），
> 是 review_LITE-20260812-0001 F4「SHA 锚指向不可得文件」的直接成因。SHA-256 值未变，
> 08-21 已逐份复核字节对齐——**错的是路径不是锚**。
>
> **发行面**：这六份**不随 Lite 发行**，校验归 Main 层（见下「Lite 边界」）。在 Lite
> 实例里按本表去找文件必然落空，那是设计而非缺陷。

- 0.2.0 基线结构权威：`60_journal/T2AG_0.2.0_STRUCTURE_PLAN.md`；迁移器：`70_tools/migrate_020.py`
- 0.2.1 增量施工权威：`T2AG-STUDENT-PROFILE-READING-BRIDGE-20260730`
- 0.2.1 完整收口与审查治理权威：
  `<workspace>/docs/handoffs/archive/v0.2.1/T2AG_021_FULL_CLOSEOUT_AND_REVIEW_GOVERNANCE_WORKORDER_2026-08-04.md`
- 0.2.1 `implementation_status`：`complete`；`candidate_review`：`passed`
- 0.2.1 candidate review：
  `<workspace>/docs/handoffs/archive/v0.2.1/T2AG_021_VERSION_INDEPENDENT_REVIEW_2026-08-04.md`，SHA-256
  `92194e00259fe7f5d80b1e458196329fbcfe7bd4e1ec1a15dd01f1383e6dd3ea`
- 0.2.1 release 资格外部权威：
  `<workspace>/docs/handoffs/archive/v0.2.1/T2AG_021_FINALIZATION_DELTA_REVIEW_2026-08-04.md`；该报告出具前不得写 release PASS
- 0.2.2 Activity Close 施工权威：
  `<workspace>/docs/handoffs/archive/v0.2.2/T2AG_022_ACTIVITY_CLOSE_LEDGER_WORKORDER_2026-08-04.md`
- 0.2.2 `implementation_status`：`complete`；`candidate_review`：`passed`
- 0.2.2 candidate review：
  `<workspace>/docs/handoffs/archive/v0.2.2/T2AG_022_VERSION_INDEPENDENT_REVIEW_2026-08-05.md`，SHA-256
  `45548a3d66f717df6d92c8c5ae163bc89ca504c55cb9d1e4867e834a615dcffd`
- 0.2.2 仓内 `release_qualification`：`finalization_delta_passed`；独立结论见
  `<workspace>/docs/handoffs/archive/v0.2.2/T2AG_022_FINALIZATION_DELTA_REVIEW_2026-08-05.md`（`finalization_delta_passed`）
- 0.2.3 范围改判与收口权威：
  `<workspace>/docs/handoffs/T2AG_023_SCOPE_CUT_AND_CLOSEOUT_2026-08-23.md`
- 0.2.3 `implementation_status`：`complete`（宿主 interceptor 已于 2026-08-23
  显式改判出范围，归位为 EV-0013 开放演化项；判据 batch_workorder_spec.md §1.4.1 情形 #3）
- 0.2.3 `candidate_review`：`passed`；仓内 `release_qualification`：`finalization_delta_passed`
- 最近 release 资格版本：`0.2.3`（资格权威在 Main 台账与独立评审证据；上行已按
  2026-08-24 完成的独立复审回填——**回填非预写**：复审先于回填，故不构成
  「写通过→重打→新包未受审」的循环）
- 0.2.4 `implementation_status`：`partial`
- 0.2.4 `candidate_review`：`not_run`；仓内 `release_qualification`：`not_claimed`
- 0.2.4 当前仅为开发基线；未冻结候选、未取得独立复审或发行资格

## Lite 边界（P-0071 收窄，2026-08-21）

**Lite 不随行任何 handoff。** `sync_lite.py` 曾声称「宪法 §7 六份无论 status 必须可校验」
并据此投影，但其投影根是仓内 `docs/handoffs/`，六份一份不在那里——投影结果恒为空集，
且**无任何告警**，再生与校验全绿。缺席不可见，是这条问题真正的毒性所在。

三条修法（改根／收窄声明／附 SHA 清单）里取**收窄**，理由：改根要让 sync_lite 跨出仓
边界，会提前引爆尚未裁决的「Lite 上传边界」——用一个小修复绑架一个大裁决；清单折中则
新造一个需要保鲜的生成物，为修陈旧而引入会陈旧的部件。收窄把承诺降到与现实一致：
**保证变弱，但从假变真**。

现行契约：

1. Lite 侧不存在 `docs/handoffs/`，本表六份锚在 Lite 内**不可解析**，这是声明过的边界。
2. 版本资格校验归 **Main 层**：在工作区级路径上按上表 SHA 逐份核。
3. `sync_lite.py` 每次再生**显式打印** `handoffs: not shipped (P-0071 收窄)`——
   空集必须发声。静默的空投影比缺席本身更危险。
