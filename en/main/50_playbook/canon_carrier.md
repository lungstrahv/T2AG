# The canonical carrier for teaching body text (canon carrier)

**Protection level**: core-playbook

> In a textbook course, teaching body text only counts once it is written into the course's canonical file; free chat text is never canonical.
> The adjudication and design original: workspace `docs/handoffs/T2AG_CANON_CARRIER_EGRESS_WORKORDER_DRAFT_2026-08-19.md`
> v2 (all six questions adjudicated). This file is the runtime contract and does not restate the design argument.
>
> **Applicability**: `course_type: mastery` with `learning_mode: textbook`; legacy drivers remain readable during migration. The machine criterion is not a course roster.
> **This mechanism is not the ADR-0002 host send boundary**: `canon_append.py` is an in-repo appender; it cannot stop the chat channel,
> and it cannot detect a self-consistent double write (a forger writing both files into a legal chain). It turns **a naive bypass from traceless into traceable**, and no more;
> it must never be advertised as a structural hard gate.

---

## 1. The carrier contract

Two files in each textbook course's lesson directory, both append-only:

| File | Role | Form |
|---|---|---|
| `lessons/<lesson>/teaching_log.md` | canon (C): the body carrier the student reads the lesson from | one section per block: `## <block_id>` + metadata lines + the body |
| `lessons/<lesson>/emissions.jsonl` | event ledger (L): one line per write, SHA-chained | one JSON per line: `seq / block_id / emitted_at / page_refs / content_sha256 / prev_sha256` |

- `page_refs` records the **persistent identity** of a page asset: `asset_id / source_document_sha256 / pdf_page_index /
  render_profile / render_sha256 / verified_text_sha256 / verification_status`.
  The identity must **never** be pinned to `book/.cache` (an evictable derived cache, EV-0012).
- `prev_sha256` = the sha256 of the previous line's raw bytes; the first line writes `GENESIS`.
- The two files are **instance data** and never enter a release surface. The Skeleton naturally carries neither (its `40_course/` holds only `_shared` and
  `_templates`); **Lite excludes them mechanically by filename via `sync_lite.should_skip_file`** (a rule set in advance, existing before any emit did, 2026-08-19) — this is not "the file does not exist so there is nothing to worry about", it is "even if the file exists it cannot get in".

## 2. The sole writer

`main/70_tools/canon_append.py` is the only legal write path to C and L. It validates:

1. the course exists and is Mastery + textbook-led;
2. the lesson directory exists;
3. the `block_id` has not appeared on **either side, C or L**, in that lesson (present in C = rejected as `duplicate_block`;
   present in L but not in C = rejected as `crash_residue`, pointing at `--complete`);
4. each `page_ref`'s page-asset file exists, its frontmatter parses, and the persistent identity is snapshotted into the event line.

It **does not validate** whether this session really consumed that page (A1–A5 belong to withhold / ADR-0003; the two layers each mind their own —
an in-repo CLI sees the disk, not the conversation); and `verification_status` is **not a gate** either — it is recorded honestly, not blocked on.

Write order and crash semantics: **L first, then C**, each atomic via tmp+rename. A crash midway can only leave "a line in L with no block in C",
which doctor judges a WARN (residue); the reverse, "a block in C with no line in L", cannot be produced by a crash and can only be produced by bypassing the writer,
so it is a FAIL. **This asymmetry is by design, not an oversight.**

The **only correct remedy for residue is `--complete`**: it fills C only and does not touch L — hand back that original body text, and once the writer has
checked its hash against the existing event line it appends the C block alone (reusing the seq and emitted_at already on the ledger). An ordinary emit
**refuses** to run while there is "a line in L and no block in C" (`crash_residue`): letting it through would write a second ledger line,
duplicate the block name, and add a phantom segment to the chain — and the ledger would then look greener than the truth. `--complete` does not accept a rewritten body; if the content does not match the ledger,
what was lost is not the file but the body text itself, and it must then be reported honestly as a CANON-004 WARN trace and never patched over.

## 3. Doctor checks

`runtime.canonical_teaching_carrier` (CANON-000..004):

| Code | Situation | Level |
|---|---|---|
| CANON-000 | a block in C with no corresponding line in L | FAIL (the writer was bypassed) |
| CANON-001 | the SHA chain in L is broken | FAIL |
| CANON-002 | an event line's page identity disagrees with the page asset's frontmatter | FAIL |
| CANON-003 | a C block's body hash disagrees with the `content_sha256` recorded in L | FAIL |
| CANON-004 | a line in L with no corresponding block in C | WARN (interrupted-emit residue) |
| — | both files missing or both empty | silent (enabling this is a per-lesson fact, not a debt) |

The body of an old `lesson.md`/`lessonNN.md` is **not canon**, and the check does not go back over it (the D3 adjudication: do not accommodate, do not scan).
What the check proves is **the consistency of the two files with the page assets**; it does not prove "written by the writer" — see the second paragraph of the header.

## 4. Conduct rules (teaching side)

### 4.1 Which layer the canon takes in (adjudicated 2026-08-19)

Only a **teaching body block** enters the canon: definitions, derivations, worked-example explanations — the layer the student re-reads and that quotes textbook source text.

**What stays in chat and does not enter the canon**: comprehension checks, feeling gates, continue authorizations, page-turn announcements, the class tree and the coverage list.
They are the real-time interaction layer and do not quote textbook source text; stuffing them into a file would turn teaching into "please read the file"
and the Socratic rhythm would be gone. The purpose of the canon is "textbook teaching output is auditable", and the boundary follows that purpose, not genre.

### 4.2 The half-finished-lesson enabling rule (adjudicated 2026-08-19)

For a lesson already started but not yet on the canon (a class stopped midway, say): **G2 is enabled from the first new teaching block after resuming**.
The part already taught is not migrated, not backfilled, and not retroactively recognized — its historical status is honestly "a non-canonical record in chat or a prep file" (the same origin as D3,
"an old lesson.md is neither accommodated nor scanned"). On resuming, add a cut-point note in that lesson's **prep file** (`lessonNN.md`)
("this lesson enables the canonical carrier from X onward; everything before is non-canonical"); **the note is never written into the teaching_log header** —
the canonical file keeps its provenance of "touched only by the writer".

### 4.3 Teaching discipline

1. Once a teaching body block has been written into the canon via `canon_append.py`, send **only a pointer** in chat
   (such as "this block is written to teaching_log §B012") and do not repeat the body.
2. The student's reading surface is the canonical file (read directly as markdown); chat is scaffolding.

enforcement: check=runtime.canonical_teaching_carrier
enforcement: prose_accepted (reason: the chat channel has no machine interception — the check on the line above covers file-side consistency only, a chat-side violation leaves no file trace, and failure is mitigated by the withhold layer and found by manual spot-check)

## 5. Related files

- `docs/adr/0002-host-controlled-textbook-teaching-egress.md` — the host send boundary (a future state, not this mechanism)
- `docs/adr/0003-prefetcher-self-certified-scan-admission.md` — A1–A5 scan self-certification (this mechanism does not take it over)
- `main/50_playbook/source_page_assets.md` — page assets and the persistent identity fields
- `main/70_tools/canon_append.py` / `main/70_tools/t2ag_doctor.py`
- `main/50_playbook/host_g1_optional.md` — the optional host pre-write interception (G1); not the floor of this file
