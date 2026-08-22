# Textbook page assets, Scope and the bounded cache (source_page_assets.md)

**Protection level**: core-playbook
**EV**: EV-0012 (`decided`)
**Authoritative design**: `docs/adr/0001-textbook-source-assets-and-bounded-cache.md`
**Domain**: `main/00_core/domain_model.md` §2.3

> This file is the executable process for **the Course holding page assets + LessonScope consuming
> them + CacheEviction**.
> The legacy `lessons/**/working_pages/**` path was retired in 0.2.2 batch S3; historical excerpts
> are in each course's `archive/`.
> **New** verification and caching go through the preparation Snapshot + source_assets.

---

## 1. Objects and directories

```text
40_course/<COURSE_ID>/book/primary/source_assets/<document_id>/
  manifest.json
  pages/page_<pdf_index>.md      # verified text + metadata
  raw_ocr/page_<pdf_index>_raw.txt
  illustrations/<chapter>_<section>_<figure>_<description>.{tex,html}   # rebuilt textbook figures (§1.3)

40_course/<COURSE_ID>/book/.cache/source_pages/
  <document_sha>/<render_profile>/page_<pdf_index>.png

lessons/lessonNN/
  lesson_map.md                       # covers the current Scope
  preparation/PREP-<id>.json          # immutable Snapshot
  preparation/current_snapshot.json   # the explicit current pointer (guessing the newest lexicographically is forbidden)
```

- **Authoritative**: the `SourceDocument` (PDF) and `source_assets` (verified text / raw OCR) in `book/primary/`.
- **`.cache` is not authoritative**: the PNGs are a rebuildable cache only, need not be committed by default, and may be removed by CacheEviction without changing any teaching fact.
- The full cache key: `(source_document_sha256, pdf_page_index, render_profile)`.
- Quota: the Course aggregate `quota_n = min(3 * scope_n, 30)` (ADR-0001).

### 1.1 Render DPI and `render_profile` discipline

| Rule | Requirement |
|---|---|
| **Default** | ordinary page images for the whole book / one `SourceDocument` are uniformly **300dpi RGB**; the default profile is `pdf-300dpi-rgb-v1` |
| **Exception** | a difficult page (small type, dense setting, staining, still unclear at 300) may additionally be stored at **400–600dpi**, and must use **a different** profile (such as `pdf-400dpi-rgb-v1` / `pdf-600dpi-rgb-v1`); it must never silently overwrite the default 300 key |
| **Forbidden** | **unmarked mixing** of 180 and 300 (or other DPI) within one course under one default profile; a historical mixed set must never be treated as a new verification standard |

Notes:

- Page identity is bound to the PDF's **1-based `pdf_page_index`** (`page[N-1]` at the implementation layer); never infer it from a filename.
- `printed_page_label` is the page number actually printed on the page image and must be filled in by visual verification; it may differ from `pdf_page_index`. The user interface and handoffs give both (such as "PDF 28 / in-book 9"), and must never copy the PDF index into `printed_page_label` or say "page 28" ambiguously.
- New `.cache` entries and new comparison renders use the default 300; a high-DPI difficult page is an additional derivative, not a second authority.
- If a historical `working_pages` set mixed DPI, a pre-migration check may prove "PNG == PDF page N" by **the DPI whose geometry matches**, but **new assets and the default profile still record 300**; the mixed set itself must be listed in the E0/E report and must not grow.

### 1.2 The pixel back-calculation gate (PPI back-calc)

The `render_profile` string, the PNG's own DPI metadata, and a verbal claim of "rendered at 300 DPI"
are none of them proof of resolution. `verify-ppi` can pre-check independently before a write:

```powershell
python -B main/70_tools/t2ag_source_pages.py verify-ppi --course <ID> --document-id <DOC> --pages 28,29
# to verify a temporary render outside the cache (single page): add --png <path>
```

- The criterion: `expected = round(MediaBox_pt / 72 * target_ppi)`; the PNG's actual pixels must match the theoretical value on both axes (default tolerance ±1px, covering renderer rounding).
- `target_ppi` is derived from the profile by default (`pdf-<N>dpi`); when the back-calculation does not reach the claimed PPI, **issuing a valid scan receipt for that profile is forbidden**, and exit 2 is fail-closed.
- A missing PNG, an invalid PNG, or an unreadable MediaBox are equally fail-closed; a model's self-reported dimensions must never be used to issue a receipt.
- `prepare` must run the same geometry gate internally for every page of Scope, and offers no skip parameter; only after it passes may `t2ag.lesson_preparation_snapshot.v2` be generated. Every load receipt carries content-addressed `ppi_evidence` (page key, MediaBox, theoretical/actual pixels, PNG SHA and evidence SHA), which enters the receipt ID, the Snapshot ID and the body SHA. An existing v1 Snapshot is read for compatibility only and must never pose as PPI evidence for a new receipt.

### 1.3 Rebuilding textbook figures (restored from P-0059)

**This section is the landing point restoring a rule the student set on 2026-07-04, which was lost
outright along with the old course configuration carrier during the 0.2.0 refactor.**
Historical anchor: `grep -n "textbook figure generation and naming rules" main/40_course/MATH1607H/lessons/lesson01/lesson01.md`
(now :496). How it was lost, the old owner path and the full `rule_migration` table are in
`00_core/t2ag_problemlog.md` P-0059.

- **Trigger**: when a figure number is recognized while verifying a textbook page (such as "Figure 1.1.1"), **rebuild the corresponding figure from context as far as possible**. "As far as possible" is honest: a figure in a scan cannot be reproduced losslessly, and the rebuild is a **teaching substitute**, not a facsimile.
- **Output formats**: **both** `LaTeX/TikZ` source and `HTML/SVG`. **No PDF is generated** (the student required this explicitly on 2026-07-04, and deleted previously generated PDFs on that basis).
- **Naming**: `<chapter>_<section>_<figure>_<description>`, such as `1_1_1_venn_diagram`.
- **Location**: `book/primary/source_assets/<document_id>/illustrations/`.
  **Not in `lessons/lessonNN/`** — a figure is a property of the page/document, not of a lesson. Putting it in a lesson duplicates it on cross-lesson reuse and contradicts §1's placement ("a Lesson holds only lesson_map and the Snapshot"). Where the lesson side needs it, use a pointer, not a copy.
- **Use**: classroom reference material the student opens themselves as HTML/SVG. **It does not enter the conversation context**, so it counts toward no token account and takes no part in the §3 A1 consumption proof.
- **Relationship to `layout_critical`**: the two govern **different sides** and can never substitute for each other. `layout_critical` decides whether the **teacher** can get the page image (§3.2.4); this section decides whether the **student** can get the figure. One page may need both: `layout_critical: true` lets the teacher see the figure, and this section lets the student see it.

> **Existing debt**: figure 1.1.1 of `MATH1607H-B001-CHEN-VOL1` has a rebuild but is still in the
> old location `lessons/lesson01/illustration/`; figure 1.1.2 (pdf 27) has **no rebuild**.
> The migration and catch-up scope is in P-0059.

## 2. Constructing the LessonScope

| Document | Scope |
|---|---|
| available pages `N >= 5` | a contiguous **5–8** pages including the current page; default preference relative `[-1,0,+1,+2,+3]`; shifted at the start/end of the book |
| short book `N < 5` | `short_document: true`; Scope = **all N pages, fixed**; only `TeachingWindow.current` moves |

- The available-page set itself must be **contiguous PDF indices**; sparse available pages **fail**, and must never be stitched into a pseudo-contiguous Scope.
- A page turn or widening produces a **new** Scope version; the old version is never modified. Beyond 8 pages requires the student's authorization in that round.

## 3. `prepare` and the consumption proof

```powershell
# read-only diff by default (nothing written)
python -B main/70_tools/t2ag_source_pages.py prepare --course <ID> --lesson lesson02 --current 28 --document-id <DOC>

# explicitly write the Snapshot + current pointer (requires user or task authorization to write)
python -B main/70_tools/t2ag_source_pages.py prepare --course <ID> --lesson lesson02 --current 28 --document-id <DOC> --write

# fix only body text / metadata / receipts, keeping the current Snapshot's Scope page set unchanged
python -B main/70_tools/t2ag_source_pages.py prepare --course <ID> --lesson lesson02 --current 28 --document-id <DOC> --preserve-current-scope --write
```

The CLI parameter is **`--current`** (not `--current-page`).
`--preserve-current-scope` is only for refreshing page-asset metadata or receipts under the same
PDF and the same current page; it reads and reuses the full page keys from the explicit current
pointer. An ordinary page turn or widening must never use it.

Before entering `prepared` (**any failure: non-zero exit and zero Snapshot written**):

1. the SourceDocument/PDF exists;
2. the PDF SHA agrees with the `source_assets` manifest;
3. a valid contiguous current Scope, with a **verified** `SourcePageAsset` for every page in it;
4. the `LessonMap` covers the whole Scope and is bound by the Map SHA;
5. every page has a **load receipt** binding the page key, the SourceAsset SHA and the SourceDocument SHA (a model's self-report is forbidden; a `missing:<page>` placeholder still marked `complete`/`content_consumed` is forbidden);
6. a **new** `LessonPreparationSnapshot`: the ID/body covers Scope, Map, receipts and source/document verification;
7. writing: overwriting an existing PREP at the same path with different content is forbidden; the same ID with the same content may return idempotently; the `current_snapshot.json` pointer is updated.

### 3.1 The session scan: what must be proven (A1–A6)

A Snapshot's `content_consumed=true` and its load receipts prove only that consumption happened at
prepare time; they **do not prove** that the current agent in a new conversation has consumed the
Scope in this session. That sentence stands: A1 must still be proven per session.

The first time each new conversation recovers a **textbook** Lesson, the Context Prefetcher must
make all of the following proof targets hold (`goal` / `project` / `praxis` are out of scope; see
the "non-textbook OR ..." gate in `startup_orchestration.md`):

| # | Proof target |
|---|---|
| **A1** | consumption happened **within this session**, and what was consumed is **that page's complete content body** — entering this round's context through host-observable delivery. A path existing, metadata/frontmatter having been read, and a truncated summary **are none of them consumption**. "Content body" is interpreted per evidence form (a text asset = its body segment; a rendered form = the whole page image), and **is not required to be Unicode text**; the per-form operationalization is in §3.1.2 |
| **A2** | **page by page**, not sampled and not the current page only |
| **A3** | the source identity of what was consumed is traceable **link by link** to the canonical `SourceDocument` in the manifest, with a SHA binding on every link, and the canonical file's actual SHA matching the manifest bit for bit |
| **A4** | the page set actually consumed **equals** the snapshot Scope exactly; with mixed evidence forms, judge by the **union** of the page sets each form covers. **An omission is FAIL; a duplicate is only a WARN (a cost notice), not a failure** |
| **A5** | the current page agrees, with no source conflict |
| **A6** | the completion criterion (ADR-0003): A1–A5 proven within this session through **host-observable delivery** is session scan complete; a self-reported `opened` / complete **with no delivery** does **not** constitute completion. Issuance by a host orchestrator is reserved as a future state, and the issuing right is reclaimed once it lands |

That result is valid only within the current session and is never written as a second source of truth.

#### 3.1.1 A3 is verified once; A1 is consumed every session

**A3 (canonical source identity) is proven by a one-off verification; A1 (consumption in this
session) is proven by reading in each session.**

Once a page asset is `verification_status: verified`, its A3 holding is a durable fact while the
identity has not drifted, and **does not lapse when the session changes**. The only lapse
conditions are:

- `source_document_sha256` disagreeing with the actual PDF; or
- `verified_text_sha256` disagreeing with the page asset's body.

Either disagreement invalidates **every** page asset under that `SourceDocument` and forces
re-verification (this is not "skip A1").

A1 must still be proven each session: by delivering that page's **complete content body** into this
round's context through host-observable delivery (for example reading the verified page asset's
body), **not** by redoing a visual verification each session. Visual verification is a prepare /
first-verification cost and is separate from the per-session A1 proof.

#### 3.1.2 Operationalizing A1's "complete content body" per form

Every recognized evidence form must declare **what mechanical reference value** proves
"complete". The form IDs and reference values below are A1's operationalization (**no new proof
target number is introduced**). The full list of which forms count, their guarantee levels and
their pending-state names is frozen by the later work order U2; until U2 lands, §3.1.4 gives the
**current default observable path**.

| Form (reference ID) | Completeness reference | Where it already exists |
|---|---|---|
| verified page asset (`EF-VERIFIED-ASSET`) | the delivered body matches the body segment bound by `verified_text_sha256`, **or is a complete superset containing it** | already in `page_NN.md` frontmatter |
| pre-rendered page image (`EF-RENDER-PNG`) | the delivered image matches `render_sha256` | already in the page asset / cache key |
| direct PDF render (`EF-PDF-DIRECT`) | **no pre-stored complete hash reference** (the host renders on the spot with unfixed parameters) | — |

**The completeness proxy for `EF-PDF-DIRECT`**: the legible printed page number in the footer —
the reported actual `printed_page_label` must match that page asset's `printed_page_label`. A
cropped strip or a thumbnail does not reliably carry the footer number, so that report carries
**both** page-identity verification and the A1 completeness proxy.

> **Honest statement**: the footer page number is a **proxy indicator**, not a proof equivalent to
> a whole-page hash — a crop preserving the footer is constructible in theory. On A1 completeness
> this path is **weaker** than the other two; it must never be flattened into "all three are
> equivalent". The formal annotation of the guarantee-level column belongs to the U2 form list.

**Four boundaries that must not be misread** (still A1; no new numbering):

1. A1 requires **delivery** into the context only, not understanding, memory, or a quiz in that round.
2. **Multiple deliveries** are allowed; the union covering that page's complete content body suffices, and a single tool call is not required to emit the whole text.
3. Frontmatter / metadata **may be read but never substitutes** for the body segment; reading frontmatter alone does not constitute A1 (all four preconditions can live in frontmatter, which is a ready-made shortcut and must be blocked).
4. "Complete" for a rendered form = the whole page image delivered; **re-running OCR** to extract every word is not required.

#### 3.1.3 Never claim "the whole Scope has been scanned"

Listed by layer (coverage shortfalls and unqualified evidence forms must not be written together
any more):

**Layer A violations (insufficient coverage — a direct violation of A2/A4/the A1 session boundary)**

- a missing page (the union has an omission relative to Scope)
- looking only at the current page, or sampling
- reusing a historical Snapshot, a historical load receipt, or another session's scan result as though it were this round's

**Layer B does not count (unqualified evidence form — even with every page number present, it is not proof of consumption)**

- looking only at **unverified** machine OCR or a summary
- verifying only a SHA / a path's existence, without delivering the content body
- a **subprocess summary** (such as the hash of `fitz.get_text()` or a script's stdout) — that proves the script read the file, and **not** that this round's model context received the content body
- **unverified machine OCR** and a **verified `SourcePageAsset`** must be kept apart: the latter carries `verification_status: verified` + `verified_text_sha256` + `source_document_sha256`, is a **product** of verification, and may take part in the proof when A1 (complete body delivery) is satisfied; the former still does not count

#### 3.1.4 The currently effective path (derived from the §3.2 list)

The form list is in §3.2. **The currently effective default combination** depends on whether
`layout_critical` has been written by the prepare stage:

| `layout_critical` state | Default form for that page | Note |
|---|---|---|
| present and `false` | `EF-VERIFIED-ASSET` | the cheapest path |
| present and `true` | `EF-PDF-DIRECT` or `EF-RENDER-PNG` | a text asset loses the layout |
| **absent** | **fall back to a rendered form** | **fail-closed**, see below |

**Fail-closed declaration (important)**: an absent field is always treated as "unknown -> a text
asset does not apply", and **must not** be read as `false`. This is deliberate: better to pay the
render cost than to let a figure page take the pure-text path with no criterion. The determination
is implemented in `admissible_scan_form()` in `t2ag_context.py` (a strict `is False` comparison; the
string `"false"` and `0` are both refused).

**The criterion is adjudicated and has landed (2026-08-07, correcting this section's earlier
wording)**: this section previously carried four sentences — "the criterion is not yet adjudicated",
"no page entry carries the field", "`EF-VERIFIED-ASSET` is currently dormant", "the cost reduction
will not materialize" — **all of them are now out of date**:

| Old wording | Current state | Recomputation |
|---|---|---|
| the criterion is not yet adjudicated | adjudicated: **C5 as the primary decision + C4 bidirectional override**, see §3.2.5 | criterion report §7.1 |
| no page entry carries the field | all 6 verified pages of `MATH1607H-B001-CHEN-VOL1` carry it | `grep -c layout_critical_source <manifest>` -> 6 |
| `EF-VERIFIED-ASSET` dormant | activated: 5 of Scope pages 25–30 take that form; only p27 falls back | `scan_forms` in `t2ag_context.py --format critical` |
| the cost reduction will not materialize | materialized: page images `6x4760 -> 1x4760`, saving **23,800** per startup | same as above |

**Two statements that still hold, unaffected by the correction above**:

1. **A document or page that has not yet had the field written is always fail-closed to a rendered form** — `prepare` does not yet call the criterion automatically, so a new page, a new Scope or another textbook must run `layout-scan` first (§3.2.5).
2. **A cost reduction is not a teaching unlock**, see A6 below.

**A6 (ADR-0003, re-adjudicated 2026-08-08)**: the formal criterion for session scan complete is
A1–A5 proven within this session through **host-observable delivery**. Until that is proven,
pending states such as `pending_visual_scan` **must not be cleared**; a self-reported `opened` /
complete **with no delivery**, a Snapshot, a historical receipt and a hash comparison none of them
constitute proof (the §3.1.3 Layer A "must never pose as" clause stands unchanged). Issuance by a
host Scan Orchestrator is reserved as a **future state**: once the host has that capability the
issuing right is reclaimed, and this paragraph updates per ADR-0003's supersede clause.
**The cost reduction in the table above happened in work preceding that proof**; after it, teaching
unlocks per this criterion and is no longer permanently blocked on "a host component is absent"
(that was the structural cause of P-0056; EV-0019 closed).

---

### 3.2 Which evidence forms count

#### 3.2.1 The admission criterion

> **An evidence form may be recognized if and only if the host can observe the event of the content
> body entering this round's model context.**
> Any summary, hash or self-description an agent reports back **is not** an observation, however
> recomputable it may be.

Corollary: a form that can prove only "it was opened", and not that the content body arrived,
**must not enter this list**. A new form must **first declare what the host observes**; otherwise it
is registered as `EF-OTHER` (undetermined) and must not be used.

#### 3.2.2 The form list (extensible)

| Form ID | Means | Derivation layers | What the host observes | Guarantee level | Pending state name |
|---|---|---|---|---|---|
| `EF-RENDER-PNG` | prepare pre-renders `pdf-300dpi-rgb-v1` into `book/.cache/`, opened page by page while teaching | two | the page-image delivery event | **complete** (A1 completeness reference `render_sha256`) | `pending_visual_scan` |
| `EF-PDF-DIRECT` | while teaching, read the named page of the canonical PDF directly, rendered into context by the host | one | the read call and the page range | **A1 completeness is a proxy indicator** (the footer page number), **weaker than the other two**; A2–A5 complete | `pending_source_read` |
| `EF-VERIFIED-ASSET` | read the **body segment** of a verified `SourcePageAsset` (`pages/page_NN.md`); applicability preconditions in §3.2.4 | zero | the read call and the page set, **and must distinguish a body delivery from a frontmatter-only delivery** | **complete** (only for pages whose `layout_critical` is false) | `pending_asset_read` |
| `EF-OTHER` | another approved form | undetermined | **must be declared first** | undetermined | undetermined |

**The guarantee levels must not be flattened.** `EF-PDF-DIRECT`'s A1 completeness rests on the
footer page number, a **proxy indicator**, and a crop preserving the footer is constructible in
theory; it is **not as strong** as the other two, and any wording that writes all three as
"complete" is wrong. The downgrade is an open account, not a blemish.

#### 3.2.3 Per-page reporting requirements (identical for all three forms; not relaxed)

`pdf_page_index`, the actual `printed_page_label`, and the heading/continuity.
`printed_page_label` must match the field of the same name on that page asset — it is the common
anchor all three forms can verify, and for `EF-PDF-DIRECT` it **doubles as the A1 completeness
proxy**.

#### 3.2.4 `EF-VERIFIED-ASSET`'s applicability preconditions and fallback

**All four preconditions must hold simultaneously**; missing one means it does not apply:

| # | Precondition | Recomputation |
|---|---|---|
| 1 | that page is `verification_status: verified` | the manifest page entry + `page_NN.md` frontmatter |
| 2 | `source_document_sha256` matches the actual PDF | `sha256sum <canonical pdf>` |
| 3 | `verified_text_sha256` matches the body of `page_NN.md` | recompute the body sha |
| 4 | that page's `layout_critical` is **present and false** | the manifest page entry (absent = does not hold, see §3.1.4) |

**The fallback is decided per page, not for Scope as a whole**: a page failing any precondition
falls back to `EF-PDF-DIRECT` or `EF-RENDER-PNG` **for that page**; the rest still take
`EF-VERIFIED-ASSET`.
**Pulling the whole Scope back to a rendered form because individual pages fell back is
forbidden** — that would zero out the cost improvement.

A4 under mixed forms is decided by the A4 row in §3.1 (union; an omission FAILs, a duplicate only
WARNs); it is not repeated here.

> **The frontmatter trap**: **all four** preconditions above can be read from `page_NN.md`'s
> frontmatter. So "reading frontmatter only" can satisfy every precondition while **not one word of
> the body has been delivered** — this is not a theoretical hole but a shortcut readily available
> under the current file structure. Hence A1 requires a **complete body segment** delivery, and the
> host-observed event must distinguish "body delivered" from "frontmatter only". The same-shaped
> precedent is P-0058 (metadata satisfied the check while the content never arrived).

#### 3.2.5 The criterion for `layout_critical` (C5 primary + C4 bidirectional override)

Adjudicated by the student on 2026-08-07 (based on
`docs/handoffs/T2AG_LAYOUT_CRITICAL_CRITERION_REPORT_2026-08-07.md`):

```
layout_critical(page) := C5(page)            <- the default, machine-produced, covering every verified page
                         C4 may override C5 bidirectionally   <- both false->true and true->false
                                               a reason must be recorded, and the teaching agent of
                                               the round must never exercise it
```

**Why not a PDF object inspection**: this class of textbook is a pure scan — each page is exactly
one full-page 300dpi greyscale JPEG, with no fonts and no text layer, so figure pages and
pure-text pages are **field-for-field identical at the PDF object layer**. The three criteria
"any image object means true", "an image area threshold", and "image + table objects" therefore
**all degenerate** on a scan (they would judge every page in the book true, so
`EF-VERIFIED-ASSET` would never activate). Recomputation is in §1–§3 of that report.

**The formal C5 definition (a deterministic raster criterion)**:

| Item | Value |
|---|---|
| metric | `tallest contiguous ink block height / median text line height` |
| decision | a ratio **> 2.2** means `layout_critical: true` |
| ink threshold | greyscale `< 128` counts as ink; a row needs `>= 15 px` of ink to count as a valid line (filtering scan noise) |
| line threshold | a contiguous ink-row run `> 8 px` counts as a text line |
| dependencies | `PIL` + `numpy`. **No `fitz` dependency** (EA-0002's scope covers only the PPI back-calculation path) |
| implementation | `python -B main/70_tools/t2ag_source_pages.py layout-scan --course <ID> --document-id <DOC> [--write]` |

**The threshold `2.2` has not been validated across the whole book and has a known systematic
source of false positives. It must not be used as a calibrated criterion.**

The initial basis was measurements of pages 25–30 (`1.08 / 1.08 / 1.14 / 1.26 / 1.54` for pure text
vs `7.45` for the page holding figure 1.1.2), which made 2.2 look like the middle of a gap.
**That gap was an artefact of chapter 1's content.**

A 14-page sample across the book (pages 40–375, rendered at 300dpi) measured:

```
1.09  1.15  1.21  1.34  1.84  1.85  2.00  2.16 | 2.32  2.33  2.73  2.81  2.94   14.53
                              threshold 2.2 ---^  margin only 0.16, mid-way through a dense run
```

6 of the 14 pages (43%) exceed the threshold. Visual inspection of the tallest ink block on the two
pages straddling it:

| Page | ratio | What the tallest ink block actually is | Verdict |
|---|---|---|---|
| 70 | 2.32 | a large display formula `lim(1/(n+1)+…+1/(2n)) = ln 2` | **false positive** (judged true, actually a formula) |
| 375 | 2.16 | the large "Index" heading | judged false correctly, but because it is a heading rather than a figure |

**Root cause: this criterion measures "a typographic block taller than a normal line" and cannot
distinguish a figure from a display formula or a large heading.** And a large display formula is
the most common feature of a mathematics textbook — **the false-positive direction is triggered
systematically**.

**Current consequence and response**: a false positive does not harm correctness (it pays for a
page image, the fail-safe direction), but it makes the C5 primary decision produce a flood of
`true` values needing manual downgrade — exactly the workload C5 was meant to remove. Until a
second discriminator is added:

- **do not generalize this criterion to a new document on its own**; the 6 pages already decided have visual inspection behind them and may continue to be used;
- for a new document, run `layout-scan` first (without `--write`) to see the distribution, then confirm page by page via C4;
- the threshold can be overridden with `--threshold`, but **after any change the whole book must be recomputed for that document** — the threshold is not a per-page property, and mixing produces two criteria within one book;
- **raising the threshold to dodge formulas is the wrong direction**: it would also miss genuinely small figures, and a false negative is the only direction that harms correctness.

**A second discriminator: two designs were tried, both rejected by measurement, and neither takes
part in the decision.**

`layout-scan` now additionally measures and records `hline` / `vline` (the longest contiguous
horizontal/vertical run divided by the median line height), written into the provenance stamp as
`C5:ratio_7.45_thr_2.2|h_11.8|v_7.5`. **They only record; they do not decide.**

| Design | Reason for rejection (measured) |
|---|---|
| **within-block measurement** | a lone thin coordinate axis forms its own short row span and is filtered as noise by `LAYOUT_MIN_LINE_PX` — **and that is exactly the small figure this discriminator was meant to catch**. It only sees segments that happen to fall inside the tallest block |
| **whole-page measurement** | it picks up scan edges and decorative rules: the printed vertical bar on index page p375 gives `v=56.8`, and the page edge of p320 gives `h=55.5`, both far beyond any real figure |

**The usable direction**: an edge mask or connected-component analysis, which is not a threshold
adjustment. It is an unfinished item; see `T2AG_OUTSTANDING_WORK_PLAN_2026-08-07.md`.

**The known false negative until it lands**: a standalone figure small enough not to produce a tall
ink block is judged `false`.
`test_source_pages.py::test_thin_standalone_rule_is_a_known_blind_spot` **pins that blind spot as a
test** — once the discriminator lands that test will start failing, at which point both the test and
this section should be updated. **The only current backstop is a C4 override.**

**The provenance field (a precondition of bidirectional override; already implemented)**: whenever
`layout_critical` is written, `layout_critical_source` must be written alongside it:

- `C5:ratio_<r>x_thr_<t>` — a machine decision;
- `C4:override:<reason>` — a human override.

`layout-scan` **skips** and reports any page entry whose `layout_critical_source` starts with
`C4:`; the machine must never override human judgement. Without that field a bare boolean is
unauditable — there is no way to tell "a false C5 decided", "a false C4 overrode" and "a false not
yet evaluated" apart.

**Three fail-closed rules**: an unverified page is skipped (it already falls back to rendering); if
the page image is not cached, **no value is written** (an absent field = unknown -> fall back, see
§3.1.4); if the page image has no recognizable text line, report an error rather than defaulting to
false.

**Not yet landed**: `prepare` does not call this criterion automatically, so a new page, a new Scope
or another textbook still needs `layout-scan` run by hand, and until then they are all fail-closed
to a rendered form.

### A session scan is not classroom coverage

- A session scan proves the teacher looked at the source; page coverage proves the student walked through it block by block in class. The two must never be interchanged.
- Before teaching each page, build the character-tree coverage checklist from the `LessonMap` active segment and the complete `SourcePageAsset`. Definitions, theorems, proof steps, worked examples, formulas, numbered remarks and textbook summaries must all enter the checklist.
- Body text on the page belonging to the previous or next section must be explicitly marked `outside_active_lesson_boundary`; every other textbook block may only be marked `covered`, or `explicitly_deferred` with the student informed. Silent omission is forbidden.
- Show the old page's checklist before turning the page; once every block has a status, announce "page turn: PDF N / in-book M", show the new page's character tree, and then obtain a one-shot continuation authorization. Consuming the new page's body first and reporting the page turn afterwards is forbidden.

## 4. The cache and CacheEviction (plan B only)

```powershell
# dry-run is the default (nothing is unlinked without --apply); --dry-run may also be explicit
python -B main/70_tools/t2ag_source_pages.py cache-gc --course <ID> --lesson lesson02 --dry-run
python -B main/70_tools/t2ag_source_pages.py cache-gc --course <ID> --lesson lesson02 --apply
```

- P0, Scope and the quota are derived **only** from a valid **current Snapshot**; a caller must never override the authoritative set with an arbitrary `--p0`.
- Cache enumeration must be based on the course directory; the only real root is `<course>/book/.cache/source_pages`, and a `CACHE_REL` that already contains `book/` must never be joined onto `<course>/book` to form `book/book/.cache`.
- Delete only PNGs inside **that course's** `book/.cache` that are rebuildable from a complete key and are **not P0** (`batch_workorder_spec` §1.2.1).
- Verify before deleting: the PDF exists, the SHA matches, the render profile agrees and it is rebuildable.
- P0 is never deleted. When the conditions do not hold: `cache_quota_blocked` / a safe failure, and **no** unlink.
- `--apply` produces an eviction audit receipt; a dry run modifies no file.
- CacheEviction must **never** be used to delete a PDF, body OCR, or learning evidence.

## 5. Legacy working_pages (retired)

The `working_pages/` path was retired in 0.2.2 batch S3. Historical excerpts, OCR and the old cache
are archived in each course's `archive/`.
New verification writes into the Course `source_assets` (authoritative); an optional `.cache` PNG is
a derivative; a Lesson only references the Snapshot/Map/pointer.
A Lesson directory does not keep long-term copies of textbook PNGs or raw OCR.

At session close: persistent page assets are **not** deleted; a legitimate CacheEviction may run
over `.cache`; the session scratch area may be cleared.

## 6. Related

- OCR proofreading detail: `ocr_correct_flow.md` (artifact paths follow this file)
- Recovery: `lesson_recover.md`
- Tool: `main/70_tools/t2ag_source_pages.py`
