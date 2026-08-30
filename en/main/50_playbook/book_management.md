# Textbook management flow (book_management.md)

**Protection level**: playbook

> Placement: `50_playbook/`. It governs the structure and content organization of each course's `book/` directory.
>
> **Triggers**: initializing the textbook directory of a new course, reorganizing an existing textbook structure, adding a new textbook.
>
> **Path resolution convention**: a course's textbook directory is always
> `main/40_course/<COURSE_ID>/book/`.

---

## 1. The uniform directory structure

Every course's `book/` directory follows this structure (subdirectories are created as needed; an empty directory is not created):

```
book/
  README.md                      ← the textbook inventory (mandatory)
  primary/                       ← primary textbooks (books read in every class)
  reference/                     ← auxiliary references (another way to explain, filling a concept gap)
  course_materials/              ← course-issued material (not "books")
    slides/                      ← slide decks
    syllabus/                    ← the syllabus
    code_samples/                ← code listings
    supplements/                 ← supplementary material (problem lists, summaries, etc.)
    exercises/                   ← exercises
    ocr/                         ← OCR working artifacts (in progress)
  archives/                      ← the original download bundle / temporary artifacts that have served their purpose
```

## 2. Classification rules

### primary/ — the primary textbook

- **Criterion**: a book read in every class of the teaching flow, from which the agent explains the source text
- **Marker**: the textbook named in the "Teaching plan" section of progress.md
- **Format**: PDF / EPUB / plain text (if an OCR text layer exists, put it in a `_text.pdf` or `.txt` of the same name)
- **A course may have several primary textbooks**: for instance a Chinese and an English edition side by side, both in primary/

### reference/ — auxiliary references

- **Criterion**: a book for "explaining it a different way" when a concept will not land; not read every class
- **Marker**: its purpose is noted in the README (for example "supplement on programming thinking", "introduction to networking concepts")
- **Difference from primary**: reference is something the agent may consult optionally; primary is something to advance through page by page

### course_materials/ — course-issued material

- **Criterion**: not a "book", but teaching material issued by the school or the teacher
- **Create subdirectories by what actually exists**: create a directory when there is content for it; never pre-create empty ones
- **Common subdirectories**:
  - `slides/` — PPT/PPTX/TXT decks
  - `syllabus/` — the syllabus
  - `code_samples/` — the textbook's code listings
  - `supplements/` — supplementary material (problem lists, summaries, notes)
  - `exercises/` — exercise sets
  - `ocr/` — OCR working artifacts (in progress; move to archives or delete when done)

### archives/ — archived

- **Criterion**: the original download bundle (zip), and temporary artifacts that have served their purpose
- **Rule**: a file in archives may be deleted at any time without affecting teaching; it is kept only for provenance

## 3. Course Type, Mastery Learning Mode, and source use

Course Type owns the completion judge and the top-level progression protocol. Only a Mastery Course declares the same `learning_mode` in course and progress; Project and Praxis do not carry a driver.

| Course Type / Learning Mode | Basis for advancing | Source rule |
|---|---|---|
| Mastery / `textbook` | textbook chapters and page numbers | `progress.md` names the primary textbook; lessons record exact pages |
| Mastery / `goal` | an explicit capability goal | each lesson names one main trustworthy source |
| Mastery / `project` | runnable artifacts serving mastery | the completion judge remains the Mastery confirmation gate |
| Project | the next open Goal/Milestone in the Project Plan | milestones bind reproducible external verification |
| Praxis | real action → feedback → reflection → next action | behavioral records and sources form an evidence bundle |

No second ProjectPlan file is created: `course.md` owns the plan definition, Completion nodes in `progress.md` own node state, and progress/activity ledger owns the single frontend. Legacy drivers are read-only compatibility fields.

`course_type: praxis` is a practice-cultivation course. It is not a general-education course, and it is not `course_type: project` (whose judge is reproducible, whereas praxis is judged by open-world consequences — the axis definitions are in `00_core/domain_model.md` §2.0). It must keep the following declaration in its course description:

> This course faces uncertainty in the open world. Studying it through T2AG alone still leaves its effect wanting; T2AG can supply structure, material, records, feedback and review, but it cannot substitute for real action, risk-taking, time invested, and lived experience. Completing this course requires the student's own vitality.

A praxis course must declare a real action entry point and behavioural evidence; understanding the concepts in conversation alone cannot prove the course is complete. The sources are evidence of action, not the course order itself.

## 4. Admitting external learning material

External material is first classified by its reuse scope, and only then assigned a registration location. The resource index is the registration source of truth; a course README keeps only course-specific material and shared-resource IDs, and never copies the shared description.

### 1. Online resources

- **A cross-course online resource**: one serving two or more courses, one whose target course does not exist yet but may be reused later, or one belonging to the system's general library, a public course, or a public tool, is registered in `main/40_course/_shared/external_resources.md`. In principle only the URL and usage information are registered; the full text is not downloaded.
- **A single-course online resource**: registered in that course's `book/README.md`, and never also in the shared index.

### 2. Downloaded files

- **A single-course file**: stored in that course's `book/` per section 1 of this file:

```text
book/
  primary/ reference/
  course_materials/{slides,syllabus,code_samples,supplements,exercises,ocr}/
  archives/
```

- **A cross-course file**: only when offline storage is genuinely needed and two or more courses share it is it stored in `main/40_course/_shared/library/[resource-ID]/`. It must never be copied into several courses' `_book/`; the other courses reference it through the local relative path in the shared index.
- **Textbook page evidence (EV-0012)**: verified text and raw OCR are held **persistently by the Course** in
  `book/primary/source_assets/<document_id>/`; the rebuildable PNG lives in
  `book/.cache/source_pages/` (CacheEviction; see `source_page_assets.md` and
  `batch_workorder_spec` §1.2.1). A Lesson does **not** hold a long-term copy of a textbook binary.
- **Legacy, retired**: the former `lessons/lessonXX/working_pages/` path was retired in 0.2.2 batch S3; historical excerpts are in each course's `archive/`.
- An Exercise answer image goes into the matching Attempt's `assets/`; reusable teaching material goes into
  `book/course_materials/supplements/`. Move it into `_shared/library/` only after long-term cross-course use is confirmed.
- **The lite review snapshot**: it packages no PDF, textbook, archive, environment, cache, generated asset, or
  `_shared/library/` binary; an excluded file is marked "held by the main project" in the index.

### 3. Fields registered in the shared index

Each item in `external_resources.md` registers at least one row:

| Resource ID | Name | Type | URL/local path | Applicable courses | Applicable knowledge points | Purpose | How it is used | Source and licence | Last verified date |
|---|---|---|---|---|---|---|---|---|---|
| globally unique | material name | site / public course / textbook / problem bank / tool | a unique URL or a local relative path | list of course codes | chapter or topic | primary textbook / auxiliary explanation / practice / fact-checking | read online / download / consult as needed | the publisher and its public-use status | the most recent verification date |

The same URL or local file may be registered only once. An online URL only has to be well-formed; doctor is not required to go online. A local relative path must really exist (except for files excluded from lite because the main project holds them).

## 5. Mandatory contents of README.md

Every `book/README.md` must contain:

1. **The textbook inventory table**: filename / material / source / purpose
2. **Instructions for using the primary textbook**: how to advance by page, how to use the OCR text layer
3. **A purpose note for each reference**: "in what situation do I consult this one"
4. **Usage rules**: textbook priority, consultation order

## 6. Initialization when creating a new course

1. Create the `book/` directory
2. Write `README.md` (even with no textbook yet, write "no textbook at present, to be added")
3. Do not pre-create primary/, reference/ and the rest — create a subdirectory when there is a file for it
4. When a textbook is downloaded or placed, file it into the right subdirectory per the classification rules

## 7. Managing OCR / page-asset artifacts

- **The authority chain**: the `SourceDocument`/original PDF + the Course `source_assets` (verified text / raw OCR and their metadata).
  **A `.cache` PNG is not a source of truth**: it is only a derivative **rebuildable from the PDF at a given `render_profile`** and may be evicted by CacheEviction; its absence must never rewrite a teaching fact. The flow is in `source_page_assets.md` and ADR-0001.
- `course_materials/ocr/` is an optional working scratch area only; when finished it should be merged into `source_assets` or archives, and must never become a second source of truth.
- The final readable text layer may also be saved as a `_text.pdf` next to the primary textbook; **page-level verification** is governed by `source_assets/pages/`.
- `archives/tmp_*` may be deleted once finished; archive cleanup must **never** be used in place of the CacheEviction rule.
- At session close: do **not** delete persistent `source_assets` or the PDF; a legitimate eviction from `.cache` is permitted.

## 8. Discipline

- **Do not copy a textbook binary per Lesson** as the authority; a Lesson holds a reference and a Snapshot.
- **archives is deletable**: it takes no part in the doctor authority chain (page assets excepted).
- **File naming**: a primary textbook keeps its original filename; a page asset uses the stable `page_<pdf_index>`.
- **Size limit**: for a textbook file over 100MB, consider splitting it, or keeping only the text layer + the page assets.

## 9. Related files

- The course textbook directory: `main/40_course/<COURSE_ID>/book/`
- The course teaching plan: the `progress.md` resolved per §5
- `main/50_playbook/first_run.md` — step 5b, creating the course folder
- `main/50_playbook/new_course_init.md` — the new-course initialization flow
