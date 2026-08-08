# 教材页资产、Scope 与有界缓存（source_page_assets.md）

**保护级别**：core-playbook
**EV**：EV-0012（`decided`）
**权威设计**：`docs/adr/0001-textbook-source-assets-and-bounded-cache.md`
**领域**：`main/00_core/domain_model.md` §2.3

> 本文件是 **Course 持有页资产 + LessonScope 消费 + CacheEviction** 的可执行流程。
> Legacy `lessons/**/working_pages/**` 路径已在 0.2.2 批 S3 退役；历史摘录见各课 `archive/`。
> **新建** 核验与缓存走 preparation Snapshot + source_assets。

---

## 1. 对象与目录

```text
40_course/<COURSE_ID>/book/primary/source_assets/<document_id>/
  manifest.json
  pages/page_<pdf_index>.md      # 核验文本 + 元数据
  raw_ocr/page_<pdf_index>_raw.txt

40_course/<COURSE_ID>/book/.cache/source_pages/
  <document_sha>/<render_profile>/page_<pdf_index>.png

lessons/lessonNN/
  lesson_map.md                       # 覆盖当前 Scope
  preparation/PREP-<id>.json          # 不可变 Snapshot
  preparation/current_snapshot.json   # 显式 current 指针（禁止字典序猜最新）
```

- **权威**：`book/primary/` 中的 `SourceDocument`（PDF）与 `source_assets`（核验文本/raw OCR）。
- **`.cache` 非权威**：PNG 仅可重建缓存，默认可不入库；可被 CacheEviction 删除而不改变教学事实。
- 缓存完整键：`(source_document_sha256, pdf_page_index, render_profile)`。
- 配额：Course 聚合 `quota_n = min(3 * scope_n, 30)`（ADR-0001）。

### 1.1 渲图 DPI 与 `render_profile` 纪律

| 规则 | 要求 |
|---|---|
| **默认** | 全书 / 同一 `SourceDocument` 的常规页图统一 **300dpi RGB**；默认 profile 为 `pdf-300dpi-rgb-v1` |
| **例外** | 难页（小字、密排、污迹、300 仍不清）可另存 **400–600dpi**，必须使用 **另一个** profile（如 `pdf-400dpi-rgb-v1` / `pdf-600dpi-rgb-v1`），不得静默覆盖默认 300 键 |
| **禁止** | 同一课、同一默认 profile 下 **无标记混用** 180 与 300（或其它 DPI）；历史混档不得当作新核验标准 |

说明：

- 页身份绑定 PDF 的 **1-based `pdf_page_index`**（实现层 `page[N-1]`），不得仅凭文件名臆测。
- `printed_page_label` 是页图上实际印刷的页码，必须通过视觉核对填写；它可与
  `pdf_page_index` 不同。用户界面和 handoff 同时给出两者（如“PDF 28／书内 9”），不得
  把 PDF 索引复制进 `printed_page_label` 或笼统称作“第 28 页”。
- 新建 `.cache` / 新对照渲染以默认 300 为准；难页高 DPI 是附加派生，不是第二套权威。
- 历史 `working_pages` 若混用 DPI，迁移前预检可按 **匹配几何的 DPI** 证明「PNG ≡ PDF 第 N 页」，但 **新资产与默认 profile 仍记 300**；混档本身须在 E0/E 报告中列明，不得再扩大。

### 1.2 像素反算闸门（PPI back-calc）

`render_profile` 字符串、PNG 自带 DPI 元数据、「按 300 DPI 渲染」的口头声明都不是分辨率证明。`verify-ppi` 可用于写入前独立预检：

```powershell
python -B main/70_tools/t2ag_source_pages.py verify-ppi --course <ID> --document-id <DOC> --pages 28,29
# 核验缓存外的临时渲染结果（单页）：追加 --png <路径>
```

- 判定式：`expected = round(MediaBox_pt ÷ 72 × target_ppi)`；PNG 实际像素两轴必须与理论值一致（默认容差 ±1px，覆盖渲染器取整差异）。
- `target_ppi` 默认从 profile 派生（`pdf-<N>dpi`）；像素反算达不到声称 PPI 时，**禁止为该 profile 签发有效扫描收据**，exit 2 即 fail-closed。
- PNG 缺失、非合法 PNG、MediaBox 不可读同样 fail-closed；不得以模型自报尺寸补开收据。
- `prepare` 必须对 Scope 每页内建执行同一几何闸门，不提供跳过参数；通过后才可生成
  `t2ag.lesson_preparation_snapshot.v2`。每份 load receipt 都携带内容寻址的
  `ppi_evidence`（page key、MediaBox、理论/实际像素、PNG SHA 与 evidence SHA），并进入 receipt ID、
  Snapshot ID 与 body SHA。既有 v1 Snapshot 仅作兼容读取，不得冒充新收据的 PPI 证据。

## 2. LessonScope 构造

| 文档 | Scope |
|---|---|
| 可用页 `N ≥ 5` | 含当前页的连续 **5–8** 页；默认偏好相对 `[-1,0,+1,+2,+3]`；书首/末平移 |
| 短书 `N < 5` | `short_document: true`；Scope = **全部 N 页固定**；仅 `TeachingWindow.current` 移动 |

- 可用页集合本身必须是 **连续 PDF 索引**；稀疏 available pages **失败**，不得拼成伪连续 Scope。
- 翻页/扩窗 → **新** Scope 版本；不改旧版本。超过 8 页须学生当轮授权。

## 3. prepare 与消费证明

```powershell
# 默认只读差异（不写盘）
python -B main/70_tools/t2ag_source_pages.py prepare --course <ID> --lesson lesson02 --current 28 --document-id <DOC>

# 显式写入 Snapshot + current 指针（须用户或任务授权写盘）
python -B main/70_tools/t2ag_source_pages.py prepare --course <ID> --lesson lesson02 --current 28 --document-id <DOC> --write

# 只修正文/元数据/receipt，必须保持 current Snapshot 的 Scope 页集合不变
python -B main/70_tools/t2ag_source_pages.py prepare --course <ID> --lesson lesson02 --current 28 --document-id <DOC> --preserve-current-scope --write
```

CLI 参数名为 **`--current`**（不是 `--current-page`）。
`--preserve-current-scope` 仅用于同一 PDF、同一 current page 下的页资产元数据或 receipt
刷新；它从显式 current pointer 读取并复用完整 page keys。正常翻页/扩窗不得使用该参数。

进入 `prepared` 前（**任一失败：非零退出且零 Snapshot 写入**）：

1. SourceDocument/PDF 存在；
2. PDF SHA 与 `source_assets` manifest 一致；
3. 合法连续当前 Scope；Scope 内每页有 **已核验** `SourcePageAsset`；
4. `LessonMap` 覆盖整个 Scope，并绑定 Map SHA；
5. 每页 **load receipt** 绑定 page key、SourceAsset SHA、SourceDocument SHA（禁止模型自报；禁止 `missing:<page>` 占位后仍标 `complete`/`content_consumed`）；
6. **新** `LessonPreparationSnapshot`：ID/body 覆盖 Scope、Map、receipts、source/document 核验；
7. 写盘：禁止覆盖已有不同正文的同路径 PREP；同 ID 同正文可幂等返回；更新 `current_snapshot.json` 指针。

### 3.1 会话扫描：要证明什么（A1–A6）

Snapshot 的 `content_consumed=true` 与 load receipt 只证明 prepare 当时已消费，**不证明**
新对话中的当前 Agent 已在本会话消费过 Scope。该句保留：A1 仍须每会话证明。

每次新对话首次恢复 **textbook** Lesson，Context Prefetcher 必须使下列证明目标全部成立
（`goal` / `project` / `praxis` 不适用本门；见 `startup_orchestration.md` 的
「非 textbook OR …」闸门）：

| # | 证明目标 |
|---|---|
| **A1** | 消费发生在**本会话内**，且消费的是**该页完整内容本体**——经宿主可观察的投递进入本轮上下文。路径存在、元数据/frontmatter 已读、截断摘要，**均不构成消费**。「内容本体」按证据形式解释（文本资产=其正文段；渲染形式=整页画面），**不要求是 Unicode 文本**；逐形式操作化见 §3.1.2 |
| **A2** | **逐页**，非抽样、非只看当前页 |
| **A3** | 所消费内容的来源身份可**逐环追溯**至 manifest 中的 canonical `SourceDocument`，链上每一环均有 SHA 绑定，且 canonical 文件的实际 SHA 与 manifest 逐位相符 |
| **A4** | 实际消费的页集合与 snapshot Scope **完全相等**；混合证据形式下按各形式覆盖页集合之**并集**判定。**遗漏为 FAIL；重复只报 WARN（成本提示），不判失败** |
| **A5** | 当前页一致，无来源冲突 |
| **A6** | 完成由**宿主签发**；agent / Prefetcher 自报 `opened` 或 complete **不构成授权** |

该结果只在当前会话内有效，不写成第二真相源。

#### 3.1.1 A3 一次核验 / A1 每会话消费

**A3（canonical 来源身份）由一次性核验证明，A1（本会话消费）由每会话读取证明。**

页资产一经 `verification_status: verified`，在身份未漂移时其 A3 成立即为持久事实，
**不因换会话而失效**。失效条件只有：

- `source_document_sha256` 与实际 PDF 不符；或
- `verified_text_sha256` 与页资产正文不符。

任一不符则该 `SourceDocument` 下**全部**页资产失效，强制重新核验（不是“跳过 A1”）。

每会话仍须证明 A1：方式是把该页**完整内容本体**经宿主可观察投递进入本轮上下文
（例如读取已核验页资产正文），**不是**每会话重新做一次视觉核验。视觉核验属于
prepare / 首次核验成本，与每会话 A1 证明分离。

#### 3.1.2 A1「完整内容本体」的逐形式操作化

每种被承认的证据形式必须声明**用什么机械参考值**证明「完整」。下列形式 ID 与参考值
是 A1 的操作化（**不新增证明目标编号**）。完整「哪些形式算数 / 保证等级 / pending 状态名」
清单由后续工单 U2 冻结；在 U2 落地前，§3.1.4 给出**现行默认可观察路径**。

| 形式（参照 ID） | 完整性参考值 | 存量 |
|---|---|---|
| 已核验页资产（`EF-VERIFIED-ASSET`） | 投递体与 `verified_text_sha256` 绑定的正文段一致，**或为其完整超集且含该正文** | 已存于 `page_NN.md` frontmatter |
| 预渲染页图（`EF-RENDER-PNG`） | 投递图与 `render_sha256` 一致 | 已存于页资产 / 缓存键 |
| PDF 直读渲染（`EF-PDF-DIRECT`） | **无预存完整哈希参考**（宿主当场渲染，参数不固定） | —— |

**`EF-PDF-DIRECT` 的完整性代理**：以**页脚版心号可辨读**为准——回报的实际
`printed_page_label` 须与该页资产的 `printed_page_label` 一致。裁切条与缩略图不会稳定
携带版心号，故该回报**同时**承担页身份核对与 A1 完整性代理两个职责。

> **诚实声明**：页脚版心号是**代理指标**，不是等价于全页哈希的证明——理论上可构造
> 保留页脚的裁切。该路径在 A1 完整性一项上的保证**弱于**另两种；不得抹平为「三种完全等同」。
> 保证等级列的正式标注属 U2 形式清单。

**四条不得误读的边界**（仍属 A1，不增编号）：

1. A1 只要求**投递**进入上下文，不要求理解、记忆或当轮测验。
2. 允许**多次投递**，并集覆盖该页完整内容本体即可；不强制单次 tool call 吐出全文。
3. frontmatter / 元数据**可读但不能替代**正文段；仅读 frontmatter 不构成 A1
   （四个前置字段均可住在 frontmatter 里，是现成捷径，必须挡住）。
4. 渲染形式的「完整」= 整页画面投递，**不要求再 OCR 一遍**抽出全部文字。

#### 3.1.3 不得宣称「已扫描整个 Scope」

按层分列（不得再把「覆盖不足」与「证据形式不合格」混写）：

**A 层违反（覆盖不足 —— 直接违反 A2/A4/A1 会话边界）**

- 缺页（并集相对 Scope 有遗漏）
- 只看当前页或抽样
- 复用历史 Snapshot、历史 load receipt、或其它会话的扫描结果冒充本轮

**B 层不算数（证据形式不合格 —— 即使页号齐全也不构成消费证明）**

- 仅看**未核验**的机器 OCR 或摘要
- 只验 SHA / 路径存在，未投递内容本体
- **子进程摘要**（如 `fitz.get_text()` 的哈希或脚本 stdout）——证明脚本读过文件，
  **不**证明本轮模型上下文收到了内容本体
- **未核验机器 OCR** 与 **已核验 `SourcePageAsset`** 必须分开：后者带
  `verification_status: verified` + `verified_text_sha256` + `source_document_sha256`，
  是核验**产物**，在满足 A1（完整正文投递）时可参与证明；前者仍不算数

#### 3.1.4 当前生效路径（由 §3.2 清单派生）

形式清单见 §3.2。**当前生效的默认组合**取决于 `layout_critical` 是否已由 prepare 阶段写入：

| `layout_critical` 状态 | 该页默认形式 | 说明 |
|---|---|---|
| 字段存在且为 `false` | `EF-VERIFIED-ASSET` | 最便宜路径 |
| 字段存在且为 `true` | `EF-PDF-DIRECT` 或 `EF-RENDER-PNG` | 文本资产丢版式 |
| **字段缺失（当前全仓状态）** | **回落渲染形式** | **fail-closed**，见下 |

**fail-closed 声明（重要）**：`layout_critical` 的确定性判据尚未裁决（见施工单步骤 6 差异
报告），因此当前**没有任何页条目携带该字段**。按 fail-closed，字段缺失一律视为「未知 →
不适用文本资产」，故 **`EF-VERIFIED-ASSET` 当前处于惰性**，实际路径仍是文本 + 整页画面。
**判据裁决并由 prepare 写入该字段之前，本单声明的开销下降不会兑现。** 这是刻意的：
宁可暂不省，也不让图形页在无判据情况下走纯文本路径。

**A6**：session scan complete **仅由宿主签发**；Prefetcher/Agent 自报不构成授权。
本节不宣称、也不实现清除 `pending_visual_scan`。

---

### 3.2 哪些证据形式算数

#### 3.2.1 准入判据

> **一种证据形式可被承认，当且仅当宿主能观察到内容本体进入本轮模型上下文这一事件本身。**
> agent 回报的任何摘要、哈希或自述**都不是**观察，无论它多么可复算。

推论：只能证明「打开过」而不能证明内容本体到场的形式，**不得进入本清单**。
新增形式必须**先声明宿主观察什么**，否则登记为 `EF-OTHER`（待定）且不得使用。

#### 3.2.2 形式清单（可扩展）

| 形式 ID | 手段 | 派生层数 | 宿主观察什么 | 保证等级 | pending 状态名 |
|---|---|---|---|---|---|
| `EF-RENDER-PNG` | prepare 阶段预渲染 `pdf-300dpi-rgb-v1` 到 `book/.cache/`，教学时逐页打开 | 两层 | 页图投递事件 | **完全**（A1 完整性参考 `render_sha256`） | `pending_visual_scan` |
| `EF-PDF-DIRECT` | 教学时直接读 canonical PDF 指定页，由宿主渲染进上下文 | 一层 | 读取调用与页范围 | **A1 完整性为代理指标**（页脚版心号），**弱于另两种**；A2–A5 完全 | `pending_source_read` |
| `EF-VERIFIED-ASSET` | 读已核验 `SourcePageAsset`（`pages/page_NN.md`）**正文段**；适用前置见 §3.2.4 | 零 | 读取调用与页集合，**须能区分正文投递与仅 frontmatter 投递** | **完全**（限 `layout_critical` 为假的页） | `pending_asset_read` |
| `EF-OTHER` | 其它经批准形式 | 待定 | **必须先声明** | 待定 | 待定 |

**保证等级不得抹平。** `EF-PDF-DIRECT` 的 A1 完整性依赖页脚版心号这一**代理指标**，
理论上可构造保留页脚的裁切；它与另两种**不等强**，任何把三者一律写成「完全」的表述
都是错误。降级是明账，不是瑕疵。

#### 3.2.3 逐页回报要求（三形式一致，不放宽）

`pdf_page_index`、实际 `printed_page_label`、标题/连续性。
`printed_page_label` 必须与该页资产的同名字段一致——它是三种形式都能验的共同锚，
并对 `EF-PDF-DIRECT` **兼任 A1 完整性代理**。

#### 3.2.4 `EF-VERIFIED-ASSET` 的适用前置与回落

**四个前置必须同时成立**，缺一即不适用：

| # | 前置 | 复算 |
|---|---|---|
| 1 | 该页 `verification_status: verified` | manifest 页条目 + `page_NN.md` frontmatter |
| 2 | `source_document_sha256` 与实际 PDF 相符 | `sha256sum <canonical pdf>` |
| 3 | `verified_text_sha256` 与 `page_NN.md` 正文相符 | 重算正文 sha |
| 4 | 该页 `layout_critical` **存在且为假** | manifest 页条目（缺失 = 不成立，见 §3.1.4） |

**回落逐页判定，不按 Scope 整体判定**：任一前置不成立的页，**该页**回落 `EF-PDF-DIRECT`
或 `EF-RENDER-PNG`；其余页仍走 `EF-VERIFIED-ASSET`。
**禁止因个别页回落而把整个 Scope 拉回渲染形式**——那会让成本改善归零。

混合形式下的 A4 判定见 §3.1 A4 行（并集；遗漏 FAIL、重复只 WARN），本节不重复。

> **⚠ frontmatter 陷阱**：上表四个前置**全部**可从 `page_NN.md` 的 frontmatter 读到。
> 因此「只读 frontmatter」能满足全部前置而**正文一字未投递**——这不是理论漏洞，是当前
> 文件结构下现成可走的路径。故 A1 要求**完整正文段**投递，宿主观察事件须能区分
> 「正文投递」与「仅 frontmatter 投递」。同型判例见 P-0058（元数据满足检查、内容从未到场）。

### 会话扫描不等于课堂覆盖

- session scan 证明教师看过来源；page coverage 证明学生课堂已经逐块走过，两者不得互换。
- 每页开讲前根据 `LessonMap` active segment 与完整 `SourcePageAsset` 建立字符树覆盖清单。
  定义、定理、证明步骤、例题、公式、编号说明和教材总结都必须进入清单。
- 页内属于上一节/下一节的正文必须显式标成 `outside_active_lesson_boundary`；其余教材块只能
  标成 `covered` 或经学生知情后的 `explicitly_deferred`，禁止静默省略。
- 翻页前先展示旧页清单；所有块有状态后，宣布“翻页：PDF N / 书内 M”，展示新页字符树，
  再取得一次性继续授权。不得先消费新页正文、事后补报翻页。

## 4. 缓存与 CacheEviction（方案 B only）

```powershell
# dry-run 为默认（未带 --apply 时不 unlink）；也可显式 --dry-run
python -B main/70_tools/t2ag_source_pages.py cache-gc --course <ID> --lesson lesson02 --dry-run
python -B main/70_tools/t2ag_source_pages.py cache-gc --course <ID> --lesson lesson02 --apply
```

- P0、Scope、quota **只**从合法 **current Snapshot** 派生；调用者不得用随意 `--p0` 覆盖权威集合。
- 缓存枚举基准必须是课程目录；唯一实际根为 `<course>/book/.cache/source_pages`，不得把
  已含 `book/` 的 `CACHE_REL` 再拼到 `<course>/book` 后形成 `book/book/.cache`。
- 仅删除 **该课** `book/.cache` 内、完整键可重建、**非 P0** 的 PNG（`batch_workorder_spec` §1.2.1）。
- 删除前验证：PDF 存在、SHA 相同、render profile 一致且可重建。
- P0 永不删除。不满足条件：`cache_quota_blocked` / 安全失败，**不** unlink。
- `--apply` 产生驱逐审计 receipt；dry-run 不修改文件。
- **不得**用 CacheEviction 删 PDF、正文 OCR、学习证据。

## 5. Legacy working_pages（已退役）

`working_pages/` 路径已在 0.2.2 批 S3 退役。历史摘录、OCR 与旧 cache 已归档至各课 `archive/`。
新核验写入 Course `source_assets`（权威）；可选写入 `.cache` PNG（派生）；Lesson 只引 Snapshot/Map/指针。
Lesson 目录不长期保存教材 PNG/raw OCR 副本。

结课：**不**删除持久页资产；可对 `.cache` 做合法 CacheEviction；会话临时区可清。

## 6. 关联

- OCR 校对细节：`ocr_correct_flow.md`（产物路径以本文件为准）
- 恢复：`lesson_recover.md`
- 工具：`main/70_tools/t2ag_source_pages.py`
