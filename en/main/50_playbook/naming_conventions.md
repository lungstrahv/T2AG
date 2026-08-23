# T2AG 0.2.2 naming conventions

**Protection level**: playbook

## Directories

- Numbered domains: English, singular, keeping the `NN_` prefix, spaced by 10.
- The `main/` numbered domains are fixed at `00/10/20/30/40/50/60/70/80`.
- A course: `40_course/<COURSE_ID>/`, where the directory name is the stable course ID.
- A group: `30_group/GNN/`.
- A lesson: `lessons/lessonNN/`.
- Textbook page assets (EV-0012 / the Course authority chain):
  - persistent verified text, raw OCR, and metadata:
    `book/primary/source_assets/<document_id>/pages/page_<pdf_index>.md`,
    `book/primary/source_assets/<document_id>/raw_ocr/page_<pdf_index>_raw.txt`, and so on;
  - the rebuildable PNG cache:
    `book/.cache/source_pages/<source_document_sha256>/<render_profile>/page_<pdf_index>.png`;
  - reconstructed textbook illustrations (the P-0059 recovery; the owner is `source_page_assets.md` §1.3):
    `book/primary/source_assets/<document_id>/illustrations/<chapter>_<section>_<figure>_<description>.{tex,html}`,
    for example `1_1_1_venn_diagram.tex` / `.html`. **Only TikZ source and HTML/SVG are produced, never PDF.**
    A figure is a property of the document/page and **does not go in `lessons/lessonNN/`**; when the lesson side needs it, use a pointer rather than a copy;
  - a Lesson holds only `lesson_map.md`, the immutable preparation Snapshot (`preparation/PREP-*.json`)
    and the current pointer (`preparation/current_snapshot.json`); it never copies page images or OCR body text.
- **Retired** (historical excerpts are in the archive): the former `lessons/lessonNN/working_pages/**`
  (including the historical `pages/pageNN.png`, `raw_ocr/page_NN_raw.txt`, `source_excerpt.md`).
  It must **never** be the canonical output of a new course, a new Lesson, or new preparation; a retained
  `source_excerpt.md` is **not** a new textbook authority.

## Stable IDs

| Object | Format |
|---|---|
| Course | the school's or a self-assigned course code, such as `MATH1607H`, `PY1001`, `PHIL1101r` |
| Group | `GNN` |
| Binding | `RNNN` |
| ActivityRecord | `AR-NNNN` |
| Engagement | `EG-NNNN` |
| Mistake | `M-NNNN` |
| Question | `Q-NNNN` |
| ReasoningPattern | `RP-NNNN` |
| ContentGroup | `<COURSE_ID>-Bddd-Cdd-Sdd` (within a Course) |
| Lesson | `lessonNN` (within a Course; `NN` at least two digits) |
| Exercise | `exerciseNN` (within a Course; `NN` at least two digits) |
| ExerciseProblem | `exerciseNN-Qddd` (within a Course) |
| Attempt | `ATdddd` (within an Exercise; the ID itself never changes) |
| Review | `RVdddd` (within an Exercise; the ID itself never changes) |
| ActivityLifecycleEvent | `ALE-NNNNNN` (monotonic within a Course; gaps allowed) |
| CloseRecord | `CLR-NNNN` (monotonic within a Course; gaps allowed) |

### Legacy aliases (resolved only, never emitted as canonical)

| Old ID | Note |
|---|---|
| `Udddd` | the Exercise directory/ID in 0.2.1 and earlier; **creating new ones is forbidden** in 0.2.2; old input is resolved only through the `activity_ledger` alias |
| `Udddd-Qddd` | the old ExerciseProblem; maps to `exerciseNN-Qddd` |

MATH1607H's `U1101` → `exercise01` was a one-off canonical replacement, not a general rule that "a stable ID may be renamed at will".

A trailing `r` on a course code marks general-education content; elastic execution semantics are expressed
solely by a binding's location and fields under the group's `bindings/`, and the current binding state must
never be inferred back from the suffix.

Attempt and Review are locally stable IDs within an Exercise; the full identity is
`course_id / exercise_id / local_id`.
Review does not use `RNNN`, to avoid colliding with the Binding namespace.

## Files

- Course: `course.md` + `progress.md`
- Engagement: `engagement.md`
- Group: `plan.md` + `calendar.md` + `review.md`
- Python/scripts: `snake_case`
- A human display name may be in any language; canonical paths, IDs, frontmatter, and tool arguments use ASCII only.

## Migration and the registry

- Changing a path does not change a stable ID.
- An active canonical is globally unique.
- Merging several sources: keep the survivor, and give the other artifacts a tombstone + alias.
- Splitting a composite: give the old artifact a tombstone + successors.
- Redirects are append-only and are collapsed to one hop; historical text is never rewritten mechanically.
