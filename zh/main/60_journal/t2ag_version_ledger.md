# T2AG 版本台账（canonical，自宪法 §7 下沉 2026-08-08/EV-0020）

> 当前运行版本与现行状态见 `main/t2ag.md` §7；本文件持有历史版本的权威锚与 SHA。

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
- 最近 release 资格版本：`0.2.2`（保留）

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
