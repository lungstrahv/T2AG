# 施工单与施工报告规范（batch_workorder_spec.md）

> **职能**：结构批次的施工单编写、执行、报告与复审的统一规范。凡涉及文件移动、规则修改、容器增删的批次，一律按本规范出单与交付。
> **保护级别**：playbook（修改走批次）。
> **起源**：批次 C / D / E2 的复审教训汇编（FP 目录名静默偏离、WARN 不指名、范围裁剪未声明、commit 假设冲突、三版同步抽样不全）。首发时在 evolution 以 EV 条目记录"批次调度偏好升格为规则"，并回填本文件指针。
> **默认执行模式**：`independent_batch`。只有用户批准了冻结、列举且会失效的 authorization envelope，才启用 `version_campaign`。

---

## 一、执行模式、风险等级与批次分类

每份施工单必须同时声明 `execution_mode` 与 `risk_tier`；批次分类描述文件操作形态，
风险等级决定 checkpoint 与复审强度，二者不得互相替代。

### 1.1 执行模式

| `execution_mode` | 适用范围 | 授权规则 |
|---|---|---|
| `independent_batch` | 默认；单批或边界尚未冻结的工作 | 每批按实际操作单独授权 |
| `version_campaign` | 同一版本内已冻结、可列举、影响闭包可证明的多个 RT1/RT2 单元 | 用户一次批准完整 authorization envelope 后，按 envelope 连续执行；不是无限持续授权 |

### 1.2 风险等级

| `risk_tier` | 典型范围 | 最低 checkpoint |
|---|---|---|
| `RT0` | 只读检查、哈希、测试、报告 | evidence checkpoint |
| `RT1` | 局部、可逆、不改 active 权威/schema/真实实例 | 定向验证 + evidence checkpoint |
| `RT2` | Core/Playbook/Tool/Schema/Registry、跨发行同步、迁移 dry-run、候选生成 | 风险边界 recovery checkpoint + 完整 Doctor |
| `RT3` | 真实或受保护数据 migration apply、terminal lifecycle、严格学生确认、跨边界外部写入、破坏性操作、push/发布 | 正文与精确对象可见后单独明确授权；campaign envelope 不得预授权未知事实 |

### 1.3 批次分类（出单时必须标注）

| 类别 | 定义 | 风险 | 前置条件 |
|---|---|---|---|
| **审计批** | 只读：grep / 哈希比对 / doctor / 差异报告。**不改任何字节** | 零 | 无。任何时刻可跑；**任何修改批完成后必须跟随一次审计批**（或将同等审计并入该批验证节） |
| **追加批** | 只新增文件或在现有文件追加文本；不改动、不移动、不删除既有内容 | 低 | 上一单元已完成其风险等级要求的 evidence/recovery checkpoint |
| **修改批** | 移动、改写、删除既有内容或结构 | 高 | 上一单元已完成其风险等级要求的 checkpoint，且最近一次适用审计通过（或本单元步骤 0 内嵌同等审计）；人工闸门逐项列明 |

混合批次**拆分优先**；确实拆不开的，整批按修改批管理。执行方对批次做范围裁剪（只执行其中一类）是允许的，但必须在报告"范围偏离"字段声明——**裁剪的理由几乎总是好的，静默才是问题**。

### 1.4 version campaign authorization envelope

`version_campaign` 只有在用户批准的 envelope 至少冻结以下字段后生效：

```text
campaign_id / target_version / baseline
included_scope / deferred_scope
repositories / file_scope / allowed_operations
risk_tier / Git checkpoint plan
reserved_RT3_gates
stop_conditions / invalidation_conditions
```

envelope 只能覆盖其中列明的仓、路径、操作和有限本地 checkpoint。范围扩张、基线变化、
风险升级、未知 FAIL/WARN、跨仓边界变化，或无法证明影响闭包时，连续授权立即失效并停手。
未列路径、未知仓和 RT3 操作不得用“同版本”推定已授权。

## 二、施工单必备结构（出单单方义务）

1. **头部**：职能｜基线快照声明（版本/日期，行号是否可信）｜EV 关联（本单是哪条 EV 的施工细化，冲突时以已批 EV 为准）｜`execution_mode`｜`risk_tier`｜批次分类｜与其他批次的依赖关系；`version_campaign` 还须给出完整 envelope；
2. **硬规则节**：一行引用「硬规则按本规范 §三」，另列**本单领域铁律**（如"evidence 索引先于实例主文件"），不复制通用规则正文；
3. **编号步骤**：每步给锚点定位 + 验证命令；闸门步骤显式标注「前置：学生一句话批准」，内容裁决类步骤显式标注「agent 出差异报告，不自行判定」；
4. **引用面收口表**：基于实测 grep，并注明「**清单是下限不是上限**，收口 grep 发现超出清单的活动引用时，执行方应扩展处理并在报告列明」；
5. **登记节**：changelog 草稿（占位符标注清楚）｜EV 推进动作（decided→changelog→archived 回填）｜skeleton 同步范围；
6. **风险登记与回滚粒度**：每段的 checkpoint 单元、Git 计划、RT3 保留项与授权失效条件。

## 三、硬规则标准集（各施工单引用，不复制）

1. 定位一律内容锚点（`grep -n`），禁止按行号操作；
2. 普通 RT1/RT2 单元先跑定向测试；RT2 风险边界、跨发行同步和最终候选必须跑完整 doctor。出现**本单未预告**的 FAIL/WARN → 停手，贴原文报告；
3. registry 条目只新增或 tombstone，永不删除；redirects 数组只追加；
4. `60_journal/`、changelog、memory、problemlog 中的历史行不改；
5. 唯一副本不删；文件迁移一律 `git mv`；
6. 「移动 + 全部引用更新」构成一个提交单元，不留中间态；
7. **checkpoint / commit 协议**：默认模式下 agent 每次 Git 写操作仍须逐次明确授权；经批准的 `version_campaign` 可按列明的有限 Git 计划建立 recovery checkpoint。每次都须使用显式路径、展示实际状态与 cached diff；不得使用 `git add .`。checkpoint 不包含 push、tag、reset、checkout、stash、历史改写、删除 recovery 或发布；
8. 内容裁决归学生（agent 出差异报告 → 学生批准 → 执行）；结构裁决按单执行。
9. **云端 CH 块 status 不变量**（M4 判例，2026-07-24）：`cloud/inbox/CH-*.md` 的 `T2AG_CLOUD_HANDOFF` 块内 `status` 必须恒为云端产出值 `proposed_for_local_review`（见 `cloud_learning_sync.md` §7.2 + doctor）。**本地终态**（accepted / partial_accept / rejected + sync_completed）只写 `cloud_sync_state.md` 交接表与 CH 文件**块外**本地裁决节。施工单若要求改块内 status = **工单错误**，执行方应拒改并声明偏离，不得静默改写或静默跳过闭环。
10. `clean ≠ reviewed ≠ released`。evidence checkpoint 只证明证据，recovery checkpoint 只提供恢复点；release snapshot 必须绑定已通过的候选完整复审与 finalization delta 独立复审，不能由工作树干净或普通 commit 推出。

## 四、施工报告模板（执行方义务，字段不可省略）

```markdown
# 批次 <X> 施工报告
**batch_id** / **执行方** / **日期** / **execution_mode** / **risk_tier** / **campaign_id（如适用）** / **批次分类** / **状态**

## 基线
doctor 施工前后对照；**每个 WARN 必须指名对象并附原文**——"已知提示"不是指名。

## 学生裁决
闸门 → 裁决，逐项。

## 实际修改文件
编号｜文件｜对应步骤｜修改内容。

## Delta manifest
每个单元记录前后指纹、修改文件、消费者、生成物、三发行影响闭包与 checkpoint；同一版本
使用一份合并施工报告持续追加，不按单元机械复制多份报告。

## 范围偏离：无 / 有（列出 + 理由）
未执行的步骤、批次裁剪、顺序调整。

## 执行偏离：无 / 有（列出 + 理由）
与单内规定不同的做法（命名、豁免、绕行），含中途改变的决定。

## 三版同步
**本批触碰的全部** core / playbook / tools 文件逐一列哈希核对结果——全量列举，不抽样。

## 收口 grep 验证
残留引用逐类归因（历史行 / redirects / 归档内部 / 历史时态说明）。

## 禁止事项确认 与 完成定义
逐项勾选。

## 遗留开放项
条件分支走了 else 的待办、延后项、需下批处理的发现。
```

「范围偏离」与「执行偏离」分设两栏：前者是"做了单子的哪个子集"，后者是"做的方式与单子哪里不同"——D 批的 FP 目录名属后者，E2 的批次裁剪属前者，混在一栏就都归不了零。

## 五、复审规范（复审方义务）

1. 逐节拿报告对施工单；产出 F 编号发现项，按严重度排序，每项给处置动作；
2. **偏离字段为空、复审却发现偏离 → 直接打回**，不论偏离本身是否合理——本规范的设计意图是让诚实声明成为成本最低的选项；
3. WARN 未指名 → 打回补充后再审；
4. 通过条件在复审意见末尾显式给出（"F_x 补完即通过"），不留开放式结论；
5. 复审方与执行方必须是不同模型或不同会话。
6. 首次版本候选必须完整复审；只有输入 manifest 未变且影响闭包可证明时，后续 finding
   才可按 `remediation_governance.md` 做 delta re-review。

## 六、本规范的维护

- 修改本文件走批次 + changelog；
- 新教训入编的门槛：同类问题**出现第二次**——出现一次记复审意见即可，第二次才值得成文（防规范膨胀）。
