# 教学正文正典载体（canon carrier）

**保护级别**：core-playbook

> 教材课的教学正文只有写进课程正典文件才算数；聊天自由文本一律非正典。
> 裁决与设计正本：工作区 `docs/handoffs/T2AG_CANON_CARRIER_EGRESS_WORKORDER_DRAFT_2026-08-19.md`
> v2（六问全裁）。本文件是运行时契约，不复述设计论证。
>
> **适用面**：`default_driver: textbook` 的课程。机器判据是 driver 字段，不是课程名单。
> **本机制不是 ADR-0002 的宿主发送边界**：`canon_append.py` 是仓内追加器，聊天通道拦不住，
> 自洽双写（伪造者把两文件一起写成合法链）也查不出。它把**笨的绕过从无痕变有痕**，仅此而已，
> 不得宣传为结构性硬门。

---

## 一、载体契约

每个教材课 lesson 目录下两份文件，均 append-only：

| 文件 | 角色 | 形制 |
|---|---|---|
| `lessons/<lesson>/teaching_log.md` | 正典（C）：学生读课的正文载体 | 每块一节：`## <block_id>` + 元数据行 + 正文 |
| `lessons/<lesson>/emissions.jsonl` | 事件账（L）：每次写入一行，SHA 链 | 每行 JSON：`seq / block_id / emitted_at / page_refs / content_sha256 / prev_sha256` |

- `page_refs` 记录页资产的**持久身份**：`asset_id / source_document_sha256 / pdf_page_index /
  render_profile / render_sha256 / verified_text_sha256 / verification_status`。
  身份**不得**钉在 `book/.cache`（可驱逐派生缓存，EV-0012）。
- `prev_sha256` = 前一行原始字节的 sha256；首行写 `GENESIS`。
- 两文件是**实例数据**，不进发行面。Skeleton 天然不带（其 `40_course/` 只有 `_shared` 与
  `_templates`）；**Lite 由 `sync_lite.should_skip_file` 按文件名机械排除**（先手规则，先于
  任何 emit 存在，2026-08-19）——不是「文件不存在所以没事」，是「文件存在也进不去」。

## 二、唯一写入器

`main/70_tools/canon_append.py` 是 C 与 L 的唯一合法写入路径。它验证：

1. 课程存在且 `default_driver: textbook`；
2. lesson 目录存在；
3. `block_id` 在该 lesson 的 **C 与 L 双侧**均未出现（C 有＝`duplicate_block` 拒；
   L 有 C 无＝`crash_residue` 拒并指路 `--complete`）；
4. 每个 `page_ref` 的页资产文件存在、frontmatter 可解析，并把持久身份快照进事件行。

它**不验证**：本会话是否真消费过该页（A1–A5 归 withhold / ADR-0003，两层各管各的；
仓内 CLI 看见的是盘不是对话）；`verification_status` 也**不是门**——如实记录，不拦。

写序与崩溃语义：**先 L 后 C**，各自 tmp+rename 原子。中途崩溃只会留下「L 有行、C 无块」，
doctor 判 WARN（残留）；反向的「C 有块、L 无行」不可能由崩溃产生，只能由绕过写入器产生，
判 FAIL。**这个不对称是设计，不是疏漏。**

残留的**唯一正确药方是 `--complete`**：只补 C、不动 L——供回当初那份正文，写入器核对
其哈希与既存事件行一致后仅追加 C 块（沿用账上的 seq 与 emitted_at）。普通 emit 在
「L 有行 C 无块」时会**拒绝**执行（`crash_residue`）：若放行，会写出第二条账行，
块名重复、链上多一截幽灵——账面反而变绿。`--complete` 不接受重写正文；内容对不上账，
说明丢的不是文件是正文本身，此时按 CANON-004 的 WARN 留痕如实报告，不得硬补。

## 三、doctor 检查

`runtime.canonical_teaching_carrier`（CANON-000..004）：

| 码 | 情形 | 级 |
|---|---|---|
| CANON-000 | C 有块、L 无对应行 | FAIL（绕过写入器） |
| CANON-001 | L 的 SHA 链断裂 | FAIL |
| CANON-002 | 事件行的页身份与页资产 frontmatter 不符 | FAIL |
| CANON-003 | C 块正文哈希与 L 记录的 `content_sha256` 不符 | FAIL |
| CANON-004 | L 有行、C 无对应块 | WARN（emit 中断残留） |
| — | 双文件均缺或均空 | 静默（启用是逐 lesson 的事实，不是欠账） |

旧 `lesson.md`/`lessonNN.md` 正文**不是正典**，检查不追溯（D3 裁决：不迁就不扫）。
检查证明的是**两文件与页资产的一致性**，不证明「经写入器写出」——见头部第二段。

## 四、行为准则（教学侧）

### 4.1 正典收哪一层（2026-08-19 裁决）

进正典的只有**教学正文块**：定义、推导、例题讲解——会被学生回读、引用教材原文的层。

**留在聊天、不进正典的**：理解确认题、感受门、继续授权、翻页宣告、课堂树与覆盖清单。
它们是实时互动层，不引教材原文；把它们塞进文件会把授课改型成「请读文件」，
苏格拉底节奏就没了。正典的目的就是「教材教学输出可审计」，边界按目的划，不按体裁划。

### 4.2 半截课启用规则（2026-08-19 裁决）

已开课但尚未启用正典的 lesson（如停在中途的课堂）：**G2 从复课后的第一个新教学块启用**。
已讲部分不迁、不补录、不追认——其历史地位如实是「聊天/备课件中的非正典记录」（与 D3
「旧 lesson.md 不迁就不扫」同源）。复课时在该 lesson 的**备课件**（`lessonNN.md`）里加一行
切点注记（「本课自 X 之后启用正典载体，此前内容非正典」）；**注记不写 teaching_log 头部**——
正典文件保持「只被写入器碰过」的出身。

### 4.3 授课纪律

1. 教学正文块经 `canon_append.py` 写入正典后，聊天里**只发指路语**
   （如「本块已写入 teaching_log §B012」），不重复正文。
2. 学生阅读面是正典文件（markdown 直读）；聊天是脚手架。

enforcement: check=runtime.canonical_teaching_carrier
enforcement: prose_accepted（理由：聊天通道无机器拦截手段——上一行的 check 只覆盖文件侧一致性，聊天侧违规不产生文件痕迹，失败由 withhold 层缓解与人工抽查发现）

## 五、关联文件

- `docs/adr/0002-host-controlled-textbook-teaching-egress.md` —— 宿主发送边界（未来态，非本机制）
- `docs/adr/0003-prefetcher-self-certified-scan-admission.md` —— A1–A5 扫描自证（本机制不接手）
- `main/50_playbook/source_page_assets.md` —— 页资产与持久身份字段
- `main/70_tools/canon_append.py` / `main/70_tools/t2ag_doctor.py`
