# The standard OCR proofreading flow

**Protection level**: playbook

> This file is one of T2AG's "skill consolidation" documents.
> When a textbook Text PDF has a damaged text layer, and `pdftotext` / PyMuPDF extraction comes out garbled, follow this flow to extract the source text from an Image Container PDF with OCR and proofread it.
>
> **Applies to**: source-text extraction for every course (MATH1607H, CS1953, and so on).
>
> **Related files**:
> - Rule definition: `main/t2ag.md` → "OCR text extraction and verification rules"
> - **Artifact authority (EV-0012)**: `main/50_playbook/source_page_assets.md` — proofread text/OCR is written into the Course
>   `source_assets` (authoritative); the PNG may optionally be written to `book/.cache` (a rebuildable derivative, not a source of truth); a Lesson stores only Snapshot/Map references.
> - General requirements: `main/10_student/profile/learning_path.md` → "OCR tool choice and result proofreading"
> - Problem log: `main/00_core/t2ag_problemlog.md`
> - Course commands: the course's own `progress.md` → "Common commands"
>
> **Retired**: the `lessonXX/working_pages/` path was retired in 0.2.2 batch S3; historical excerpts are in each course's `archive/`.
> **New** proofreading goes through the preparation Snapshot + source_assets and does not reuse the legacy path.

---

## 0. Dependency and model-download gate

1. By default, prefer reading with a tool or model vision capability that already exists; do not
   auto-install a package because a course started, because doctor or OCR failed, or because
   "the result might be better".
2. `pip install`, a package upgrade, OCR weights, and any first model download must be explained to
   the user first: the package/model name, the purpose, the expected download size, the expected
   disk footprint, the install/cache location, and whether it is reusable.
3. Only after the user explicitly approves this particular action may the project
   `.venv\Scripts\python.exe -m pip` install a pinned version; installing repeatedly into the global
   Python is forbidden, and deleting and rebuilding the whole `.venv` is forbidden.
4. If the dependency tree would pull in a large component such as Torch, Transformers, ONNX, or
   OpenCV, it must be listed in the size explanation; you must not describe `pix2text` as "pure
   Python, fairly light on dependencies".
5. Lite exists only for online model review; any installation or model-download suggestion may only
   be returned as a review finding and must not be executed.

---

## 1. When OCR is triggered

Any one of the following triggers the OCR flow:

1. **The Text PDF text layer is damaged**: check the fonts with PyMuPDF; if `GlyphLessFont` + `Identity-H` appear, the text-layer encoding map is missing, and `pdftotext` / PyMuPDF extraction comes out almost entirely garbled.
2. **Formulas are images**: the mathematical formulas in the textbook are embedded as images and the text layer cannot yield them.
3. **Only an Image Container PDF exists**: the downloaded textbook is an image-only PDF, with no Text PDF and no DjVuTXT.
4. **The extraction result is unreadable**: directly extracted text contains so much garbling, dropped characters, and wrong characters that it cannot be used for teaching.

> **When OCR is not triggered**: when the Text PDF text layer is intact and readable text can be extracted directly, prefer `pdftotext` or PyMuPDF direct extraction; there is no need for the OCR flow.
>
> **Decision order**: if a structured source exists (Text PDF / LaTeX source / EPUB+MathML), use the structured source; when only a PDF exists, first check whether it is a Text PDF, and go to OCR only if it is not.

---

## 2. OCR tool priority

| Priority | Tool | Applies to | How to obtain | Note |
|---|---|---|---|---|
| 1 | **Model vision reading of the original image** | formula-dense mathematics textbooks, symbol recognition | no installation; read the rendered PNG directly | zero install, most accurate on formulas, transcribes symbol by symbol |
| 2 | **PaddleOCR** | general-purpose OCR for Chinese textbooks | install a pinned version after user authorization | open source, runs locally; may download extra models |
| 3 | **Pix2Text** | textbooks with many mathematical formulas | install a pinned version after user authorization | pulls in large ML dependencies and a model cache |
| 4 | **MathPix API** | precise recognition of mathematical formulas | mathpix.com (needs an API key) | an online service, best formula recognition, needs the network |
| 5 | **Tesseract** | the fallback when none of the above is available | `C:\Program Files\Tesseract-OCR` | poor at mathematical symbols, needs a lot of manual proofreading |

### Why model vision reading of the original image ranks first

1. **Zero install**: no pip install, no environment variables to configure, no language pack to download — just read the original PNG.
2. **Most accurate on formulas**: the model has multimodal vision and can recognize a mathematical formula symbol by symbol (sub/superscripts, union, infinity, membership, set braces, and so on), with a far lower error rate than Tesseract.
3. **Symbol-by-symbol transcription**: the model can transcribe line by line and symbol by symbol against the original image, completing the first proofreading round in the process and reducing the later manual proofreading load.
4. **Context understanding**: the model can use textbook context (chapter, definition, theorem numbering) to infer a symbol OCR struggles with, lowering the misrecognition rate.

> **Degradation strategy**: when there are too many formulas or the page is too long for convenient model vision reading (it exceeds the context or recognition efficiency drops), degrade to Pix2Text batch recognition; when Pix2Text is unavailable, degrade to Tesseract as the fallback.

---

## 3. The complete steps

### Step 1: render PNGs into the Course `.cache` (300 DPI by default)

Use PyMuPDF (`fitz`) or an equivalent tool to render the target **SourceDocument PDF** pages as PNGs.

| Rule | Requirement |
|---|---|
| **Default** | a uniform **300 DPI, RGB** for the whole book; consistent with `render_profile` `pdf-300dpi-rgb-v1` |
| **Floor** | never below **200 DPI** (blurred glyphs, OCR collapse) |
| **Hard-page exception** | small type / dense formulas / smudges may be re-rendered at **400–600 DPI** into **another** `render_profile`, without overwriting the default 300 key |
| **Forbidden** | mixing 180 and 300 unlabelled within one course; new verification must not produce mixed-tier default images |

Page numbering: PDF **1-based page N** ↔ rendered `page[N-1]`; the index in the filename must match `pdf_page_index=N`.

**The canonical output path for new work**:

```text
40_course/<COURSE_ID>/book/.cache/source_pages/
  <source_document_sha256>/<render_profile>/page_<pdf_index>.png
```

The tool-neutral contract (creating a Lesson-local `ocr_page.py` or any `working_pages/scripts` is **forbidden**):

```text
input:  the SourceDocument PDF under book/primary; pdf_page_index = N (the human page number)
render: page[N-1] → PNG, default pdf-300dpi-rgb-v1
output: writes only to the Course .cache key path listed above
forbid: writing to lessons/**/working_pages/pages|raw_ocr|scripts
```

Example (a placeholder; substitute the path for the course and the document SHA):

```powershell
# Conceptual example: render page 21 of a PDF into the Course .cache with PyMuPDF
# (writing to disk requires user/task authorization first)
# page index: human N=21 → fitz page 20
# out: main/40_course/<COURSE_ID>/book/.cache/source_pages/<doc_sha>/pdf-300dpi-rgb-v1/page_21.png
```

> **Paths and environment**: the textbook PDF is read from the course root `book/primary/`. Tesseract
> is located through PATH, `TESSERACT_CMD`, or `--tesseract`; never save an absolute path containing
> a username in a script, and never auto-install a dependency or rebuild the `.venv`.

### Step 2: prefer model vision reading of the original image, transcribing symbol by symbol

Read the PNG just rendered (or already present) in the **Course `.cache`** directly with the model's vision capability, transcribing it to text line by line and symbol by symbol.

**Key points**:
- Read page by page, transcribing each page completely against the original image
- Check mathematical formulas symbol by symbol: sub/superscripts, union ∪, intersection ∩, membership ∈, inclusion ⊂, infinity ∞, braces {}, and so on
- The first proofreading round is completed during transcription; confirm any suspicious symbol against the original image immediately
- When a character is uncertain, infer it from context

> The text this step produces is of the highest quality and can serve directly as the proofread base
> text. For **persistent writing**, see step 6 (`source_assets`); it must never land in a Lesson
> `working_pages`.

### Step 3: if there are too many formulas for convenient vision reading, use Pix2Text

When a page is dense with formulas and model vision reading becomes inefficient, use Pix2Text for batch recognition:

```python
from pix2text import Pix2Text

p2t = Pix2Text()
# the input must be a page image in the Course .cache, not lessons/**/working_pages/pages
text = p2t.recognize(
    "main/40_course/<COURSE_ID>/book/.cache/source_pages/"
    "<source_document_sha256>/pdf-300dpi-rgb-v1/page_21.png"
)
print(text)
```

> Pix2Text specializes in recognizing mathematical formulas, supports LaTeX symbols well, and suits batch processing of a mathematics textbook.
>
> First use usually downloads a model. Before running it, you must report the size and cache location per the "dependency and model-download gate" and obtain authorization;
> without authorization, stop here and carry on with model vision reading or an existing tool.

### Step 4: Tesseract as the fallback

When neither model vision reading nor Pix2Text is available, use Tesseract as the fallback:

```bash
# make sure Tesseract is on PATH
export PATH="$PATH:/c/Program Files/Tesseract-OCR"
export TESSDATA_PREFIX="$HOME/tessdata"

# input: the Course .cache PNG; output: the Course source_assets raw OCR (working_pages forbidden)
tesseract \
  "main/40_course/<COURSE_ID>/book/.cache/source_pages/<doc_sha>/pdf-300dpi-rgb-v1/page_21.png" \
  "main/40_course/<COURSE_ID>/book/primary/source_assets/<document_id>/raw_ocr/page_21_raw" \
  -l chi_sim+eng
```

> The `pytesseract` Python interface also works, but calling it from Bash with file output is more stable (it avoids subprocess stdout encoding problems).
>
> Tesseract is poor at mathematical symbols, so step 5 **must** proofread those carefully.
> Writing the output to `lessons/**/working_pages/raw_ocr/` is **forbidden**.

### Step 5: proofread line by line against the original image

Whichever OCR tool was used, **manual line-by-line proofreading against the original image is mandatory**.

**The proofreading flow**:
1. Put the OCR result side by side with the original PNG in the **Course `.cache`**
2. Check the text line by line, focusing on mathematical symbols
3. For an unintelligible character combination, a dropped character, or a suspected wrong character, **search the web** — the textbook's table of contents, official publication information, an online problem bank, or Wikipedia — and cross-verify
4. Key definitions, theorem numbers, and formulas must get a final check against the Image Container PDF images
5. Error patterns found while proofreading go into the "Common error reference table" (below) and accumulate over time

### Step 6: after proofreading, write into the Course page assets (authoritative)

**The preferred path (EV-0012)** — see `source_page_assets.md` for detail:

- **Proofread text** → `book/primary/source_assets/<document_id>/pages/page_<pdf_index>.md` (persistent)
- **raw OCR** → `book/primary/source_assets/<document_id>/raw_ocr/page_<pdf_index>_raw.txt`
- **Page image PNG** → `book/.cache/source_pages/<doc_sha>/<render_profile>/page_<pdf_index>.png` (a rebuildable cache)
- **Lesson** → update `LessonScope` / `LessonMap` / the **new** `LessonPreparationSnapshot` + load receipts
- Tool: `python -B main/70_tools/t2ag_source_pages.py prepare ...`
- The validation prepare / Context performs on the LessonMap and the assets uses the **raw file bytes**
  (including CRLF); never claim the hashes match on the basis of text normalized by `read_text` alone.

**Legacy Compatibility** (retired, 0.2.2 batch S3):

- Historically readable: the tombstone archive files in each course's `archive/`.
- **New verification is forbidden** to write to a `working_pages` path; new output goes only to `source_assets` / `.cache`.
- **Session close must not delete** persistent evidence already promoted to the Course `source_assets`.
- Cleaning up the `working_pages` directory is no longer needed; the historical excerpts are archived.
```

New fields (optional, tool-writable): `lesson_scope_version`, `preparation_snapshot_id`, `short_document`.

---

## 4. Common error reference table

OCR has a very high error rate on mathematical symbols; check every item in this table while proofreading:

| Real symbol | Common OCR misrecognition | Example |
|---|---|---|
| `A` / `B` / `C` | `4` / `8` / `(` | `A_n` → `4,` |
| `∪` (union) | `U` / `J` / `L` | `⋃ A_n` → `U 4` |
| `∞` (infinity) | `o` / `ce` / `8` | `+∞` → `+o` |
| `∈` (membership) | `s` / `e` | `n ∈ Z` → `nsZ` |
| `⊂` / `⊃` | `C` / `D` | `S ⊂ T` → `SC T` |
| `{}` (braces) | `\|` or dropped | `{x \| ...}` → `\|x...\|` |
| subscript `x_{ij}` | garbled CJK or dropped | `x_{12}` → `X12` or `氛 1` |
| ellipsis `…` | dropped or `...` | `0,1,-1,…` → `0 T2 2 r` |
| comma `,` | a space or dropped | `0, 1, -1` → `0 1 1` |
| `≥` / `≤` | `乏` / `《` | `x ≥ 0` → `x 乏 0` |
| `≠` | `三` / `门` | `i ≠ j` → `i 三 门` |
| `∅` (empty set) | `么` / `0` | `∅` → `么` |

> **How to use it**: check against this table while proofreading and restore each suspicious character in the OCR result. As proofreading experience accumulates, add new error patterns to the table.

---

## 5. Proofreading focus points

### Check mathematical formulas symbol by symbol

- **Sub/superscripts**: `x_{ij}`, `a_n`, `x^2` and the like are very easily recognized as inline text or as garbling
- **Set symbols**: `∪`, `∩`, `∈`, `∉`, `⊂`, `⊃`, `⊆`, `∅` must be checked one by one
- **Logic symbols**: `∀`, `∃`, `⇒`, `⇔`, `∧`, `∨` are easily misrecognized as letters or dropped
- **Greek letters**: `ε`, `δ`, `α`, `β`, `λ`, `∞` and the like are easily confused with Latin letters or CJK characters
- **Braces and vertical bars**: the braces and separating bar in `{x | P(x)}` are very easily misrecognized

### Cross-verify uncertain terms online

- For an unintelligible character combination, a dropped character, or a suspected wrong character, search the web — the textbook's table of contents, official publication information, an online problem bank, or Wikipedia — and cross-verify
- Key definitions, theorem numbers, and formulas must get a final check against the Image Container PDF images
- If the textbook has a public table of contents or chapter titles, use them to confirm which chapter the OCR result belongs to

### Other proofreading points

- **Page-number continuity**: check that the page numbers in the OCR result match the textbook's real page numbers
- **Theorem numbering**: theorem, lemma, and example numbers (such as "Theorem 1.1.1" or "Example 1.1.1") must be accurate
- **Paragraph completeness**: check for a dropped or truncated paragraph
- **Punctuation**: the Chinese comma, full stop, and enumeration comma are easily misrecognized as a space or dropped

---

## 6. Recording and consolidation

- **Problem log**: OCR pitfalls and successful experience go into `main/00_core/t2ag_problemlog.md`
- **Environment configuration**: a stable OCR environment configuration (PATH, `TESSDATA_PREFIX`, and so on) goes into the course's `progress.md` "Common commands" and into `~/.bashrc`
- **Error patterns**: a newly discovered OCR error pattern is added to the "Common error reference table" in this file

---

## 7. Cautions

1. **OCR cannot replace manual proofreading**: no OCR tool can guarantee 100% accuracy, and the mathematical formulas must be checked symbol by symbol by hand.
2. **Keep the raw result for auditing**: `page_XX_raw.txt` keeps the raw OCR result unmodified, so the proofreading process can be traced.
3. **Verified text accumulates continuously**: prefer writing into the Course `source_assets`; a legacy
   `source_excerpt.md` may still be appended to where one exists, but **must not be deleted automatically at the end of a course**; deletion requires E's exact RT3.
4. **Prefer model vision reading**: where conditions allow, prefer model vision reading of the original image; it cuts the proofreading workload substantially.
5. **DPI discipline**: **300 DPI** for the whole book by default; never below 200; a hard page may go to a separate 400–600 tier; mixing 180/300 unlabelled within one course is **forbidden** (see `source_page_assets.md` §1.1).
6. **Batch efficiency**: for multi-page OCR, render the PNGs in a batch first and then read and proofread page by page, so the PDF need not be reopened repeatedly.
