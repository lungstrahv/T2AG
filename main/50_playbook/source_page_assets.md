# 教材页资产、Scope 与有界缓存（source_page_assets.md）

**保护级别**：core-playbook
**EV**：EV-0012（`decided`）
**权威设计**：`docs/adr/0001-textbook-source-assets-and-bounded-cache.md`
**领域**：`main/00_core/domain_model.md` §2.3

> 本文件是 **Course 持有页资产 + LessonScope 消费 + CacheEviction** 的可执行流程。
> 旧路径 `lessons/**/working_pages/**` 在实例迁移（批次 E）完成前仍可作 **legacy** 读取；
> **新建** 核验与缓存不得再以“每 Lesson 复制 PNG/OCR”为权威。

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

Snapshot 的 `content_consumed=true` 与 load receipt 只证明 prepare 当时已消费，不证明新对话
中的当前 Agent 已看过 Scope。每次新对话首次恢复 textbook Lesson，Context Prefetcher 必须：

1. 在 L0 逐页消费 Scope 的全部核验文本；
2. 按 `scope_scan` manifest 从同一 PDF/SHA 以指定 profile 定位或渲染全部页图；
3. 使用视觉工具实际打开每一页，并回报 `pdf_page_index`、实际 `printed_page_label`、标题/连续性
   与 `opened=true`；
4. 仅当页集合与 snapshot 完全相等、当前页一致且无来源冲突时，声明 session scan complete。

该结果只在当前会话内有效，不写成第二真相源；缺页、仅看 OCR/摘要、只验 SHA、只看当前页或
复用历史 Snapshot 都不得宣称“已扫描整个 Scope”。

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
- **不得**用 CacheEviction 删 `working_pages`、PDF、正文 OCR、学习证据。

## 5. 与旧 working_pages 的关系

| 阶段 | 规则 |
|---|---|
| 迁移前（legacy） | 仅当 **完全不存在** preparation/current Snapshot 新路径时，Doctor/Context 可读 legacy `working_pages` |
| 新路径存在但无效 | **必须失败**；禁止静默回退 legacy |
| 新核验 | 写入 Course `source_assets`（权威）；可选写入 `.cache` PNG（派生）；Lesson 只引 Snapshot/Map/指针 |
| 迁移后 | Lesson 目录不长期保存教材 PNG/raw OCR 副本 |

结课：**不**删除持久页资产；可对 `.cache` 做合法 CacheEviction；会话临时区可清。
**legacy `working_pages` 删除始终保留 E 的 exact RT3**，不得因结课/切课自动清理而跳过。

## 6. 关联

- OCR 校对细节：`ocr_correct_flow.md`（产物路径以本文件为准）
- 恢复：`lesson_recover.md`
- 工具：`main/70_tools/t2ag_source_pages.py`
