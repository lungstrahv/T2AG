---
adr_id: ADR-0001
portable_key: textbook-source-assets-and-bounded-cache
status: accepted
authority_project: T2AG
source_evolution: [EV-0012]
supersedes: []
implementation_refs:
  - main/50_playbook/source_page_assets.md
  - main/70_tools/t2ag_source_pages.py
---

# ADR-0001: 教材页资产、短书与有界缓存

**Status:** accepted  
**source_evolution:** EV-0012

EV-0012 将可复用的教材原文证据归入 Course/Book，而不是随每个 Lesson 复制；Lesson 只拥有
自己的范围版本、导航与备课收据。这个边界既保留严格原文教学，也避免同一教材页随 Lesson
线性复制。

## Decision

- `SourceDocument` 是 Course/Book 持有的原版 PDF 权威，`SourcePageAsset` 是该文档版本中
  可复用的单页证据。原始 OCR、核验文本及其来源关系属于持久证据；PNG 仅是可重建的派生页图。
- 可用页少于 5 页的 `SourceDocument` 是短书：它的唯一 `LessonScope` 是全部可用页构成的
  固定连续页集。正常文档的 Scope 则是包含当前页的连续 5–8 页；翻页或扩窗产生新 Scope 版本。
- 派生页图的缓存身份固定为
  `(source_document_sha256, pdf_page_index, render_profile)`。配额按 Course 聚合的去重键计数，
  `quota_n = min(3 * scope_n, 30)`，其中 `scope_n` 是当前有效 Scope 的页数。
- 在拟写入 `.cache` 前或 Scope 变更后，以写入后的聚合计数计算
  `need_free = max(0, projected_cache_n - quota_n)`。候选必须位于登记的
  `40_course/<COURSE_ID>/book/.cache/**` 根、键完整、可由匹配 PDF 与渲染参数重建，且不在
  当前 P0 集合；P0 可以在 cache 或 session_temp，绝不因配额驱逐。
- 候选按 `heat_at = max(last_in_scope_at, last_access_at, created_at)` 升序，随后按距当前页
  更远、document SHA 字典序、物理页索引和 render profile 的稳定次序选择。只有同时满足
  `batch_workorder_spec.md` §1.2.1 的全部条件时，后续工具才可执行 CacheEviction。

## Boundaries

本决策不授权迁移或删除任何现有 `lessons/**/working_pages/**`、PDF、raw OCR、核验文本、
学习证据或 Snapshot；这些对象不属于 CacheEviction，相关真实删除仍为 RT3。Schema、prepare
工具、缓存驱逐与实例迁移分别留给后续已授权批次实现。
