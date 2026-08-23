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

# ADR-0001: textbook page assets, short books, and a bounded cache

**Status:** accepted  
**source_evolution:** EV-0012

EV-0012 assigns reusable textbook source evidence to the Course/Book rather than copying it with every
Lesson; a Lesson owns only its own scope version, its navigation, and its preparation receipts. This
boundary keeps strict source-text teaching while stopping the same textbook page from being copied
linearly per Lesson.

## Decision

- `SourceDocument` is the original-PDF authority held by the Course/Book, and `SourcePageAsset` is the
  reusable single-page evidence within that document version. Raw OCR, the verified text, and their
  provenance relations are persistent evidence; a PNG is only a rebuildable derived page image.
- A `SourceDocument` with fewer than 5 usable pages is a short book: its only `LessonScope` is the fixed
  contiguous page set of all usable pages. A normal document's Scope is a contiguous 5–8 pages including
  the current page; turning a page or widening the window produces a new Scope version.
- A derived page image's cache identity is fixed as
  `(source_document_sha256, pdf_page_index, render_profile)`. The quota counts deduplicated keys
  aggregated per Course, `quota_n = min(3 * scope_n, 30)`, where `scope_n` is the page count of the
  currently valid Scope.
- Before a write into `.cache` is attempted, or after a Scope change, compute
  `need_free = max(0, projected_cache_n - quota_n)` from the post-write aggregate count. A candidate must
  lie under the registered `40_course/<COURSE_ID>/book/.cache/**` root, have a complete key, be
  rebuildable from the matching PDF and render parameters, and be outside the current P0 set; P0 may live
  in the cache or in session_temp and is never evicted for quota.
- Candidates are ordered ascending by `heat_at = max(last_in_scope_at, last_access_at, created_at)`, then
  by a stable order of distance from the current page, document SHA lexicographic order, physical page
  index, and render profile. A later tool may perform a CacheEviction only when every condition in
  `batch_workorder_spec.md` §1.2.1 holds at once.

## Boundaries

This decision authorizes no migration or deletion of any existing `lessons/**/working_pages/**`, PDF,
raw OCR, verified text, learning evidence, or Snapshot; those objects are not CacheEviction subjects, and
really deleting them is still RT3. The schema, the prepare tool, cache eviction, and instance migration
are each left to a later authorized batch.
