# OKF knowledge-bundle adaptation (okf_adaptation)

**Protection level**: playbook

> **Protocol identifier**: `T2AG-OKF-1` | Target format: Open Knowledge Format **v0.2**
>
> This handbook specifies how the T2AG main repository is expressed as an OKF knowledge bundle, and
> under what conditions an external OKF bundle may enter T2AG. It is a **behavioural specification**:
> the machine landing point is `70_tools/okf_export.py`, but the specification itself lives here and
> the tool is only its recomputable implementation. When the two disagree, this file governs and the
> tool gets fixed.

OKF is an open specification for writing knowledge as "directories + markdown + YAML frontmatter".
Its one hard requirement is that every concept file's frontmatter carries a non-empty `type`; the
trust family (`sources` / `generated` / `verified` / `status` / `stale_after`) is entirely optional,
and **absence carries meaning** — no `verified` means the "unverified" tier, not "unknown". The
consumer side is lenient: a missing optional field, an unrecognized `type`, and a broken link may
none of them be grounds for rejection.

## 1. Position and three invariants

The T2AG main repository is already "markdown + frontmatter + mutual links", so adapting it is not a
rebuild, it is a **translation**.

| # | Invariant | Reason |
|---|---|---|
| 1 | **Zero change to the main repository** | The exporter is read-only. A bundle is an out-of-repo artifact; deleting the whole directory rolls it back completely |
| 2 | **The mechanism is exchangeable, the instance never leaves** | The default scope contains only files describing "how the system runs"; the student profile, logs, progress and cloud never enter a bundle |
| 3 | **Never fabricate trust** | Without a real verification event, do not write `verified`. OKF's trust tiers work through field absence, and inventing one collapses three tiers into one |

The concrete consequence of invariant 3: this protocol **issues no** `verified`. A doctor pass or a
test pass is not a verification of "this knowledge is true", only a verification of structure;
writing it as `verified` would make a consumer believe somebody read the content. Should issuance
ever be wanted, it needs its own adjudication and must state whether the issuer is a `process:` or a
`human:`.

## 2. Scope

| scope | Included | Purpose |
|---|---|---|
| `mechanism` (default) | the constitution `main/t2ag.md` + the three mechanism files of `00_core/` (`domain_model.md`, `learning_activity_model.md`, `pattern_retire_loop.md`) + all of `50_playbook/` + `70_tools/*.md` | external exchange, the open-source display surface |
| `course:<COURSE_ID>` | that course's `course.md` (the course definition) | exchanging a single course design; must be named explicitly each time |

**There is no scope that exports the personal layer.** `10_student/`, `60_journal/`, `progress.md`,
`activity_ledger.md`, `mistake_bank.md`, `lessons/`, `exercises/`, and `cloud/` have no code path
reaching the exporter at all — the privacy boundary is guaranteed by absence, not by a switch. If a
local consumption need ever appears (letting a local agent read the full learning history, say), it
needs its own work order, and that order must independently answer three questions: the landing
point, the retention period, and the packaging accident surface.

Two things that **look as though they should be included but are not**; the reason must be written
down, or the next person will restore them as an oversight:

- **The three ledger files of `00_core/`** (`t2ag_changelog.md`, `t2ag_memory.md`,
  `t2ag_problemlog.md`) do not enter a bundle. They record "what this instance has been through",
  not "how the system runs" — the changelog and the problem log contain host paths and the private
  repository names of counterparties, and memory is itself a derived cache of student state. The
  changelog is transcribed at the **heading level only** into `log.md` (§4); the body does not
  leave.
- **A course does not enter `mechanism`.** `course.md` is a course design and is exchangeable, but
  it names real textbooks, a real curriculum plan and a real institution, which is an
  instance-identifying surface. To exchange it, go through `course:<ID>` by explicit name, and pass
  the leak gate all the same — the correct response when the gate stops it is to admit "the
  definition of this course really does carry my institution", not to grant it an exemption.

The allowlist is a **directory-level positive enumeration**, not an exclusion rule. New content stays
out of the bundle by default unless a row is added to this table.

The constitution `main/t2ag.md` enters `mechanism`: it is the entry point of the whole mechanism, and
measurement confirms it is the most-referenced node (14 in-edges inside the bundle). It lands at the
bundle root with `type: Governance Doc`.

## 3. The mapping table (T2AG → OKF frontmatter)

### 3.0 Overview

| Source | Bundle landing point |
|---|---|
| `main/t2ag.md` | `/t2ag.md` |
| `main/<domain>/<file>.md` | `/<domain>/<file>.md` (the `main/` prefix is dropped) |

### 3.1 `type`: required, injected by source

Most prose files in the main repository have no frontmatter; on export it is injected by directory.
A file that already has a `type` passes its original value through unchanged.

| Source | Injected `type` | Note |
|---|---|---|
| `00_core/domain_model.md` | `Domain Model` | listed separately: it is the authority for domain vocabulary |
| the rest of `00_core/` mechanism files | `Governance Doc` | the domain-model layer the constitution depends on |
| `50_playbook/` | `Playbook` | an OKF-native example type |
| `70_tools/*.md` | `Reference` | the tool documentation surface |
| `40_course/*/course.md` | passed through (currently `course`) | existing frontmatter is not rewritten |
| each directory's `_README.md` | transcribed into that directory's `index.md`, not treated as a concept | see §4 |

The style of a `type` value follows the capitalized phrases of the OKF examples (`Playbook`,
`Reference`), alongside the lowercase `course` already present in the main repository. OKF has no
central registry, so two styles coexisting is legal; a consumer must degrade gracefully on an
unknown `type`.

### 3.2 The trust family

| OKF field | Value | Note |
|---|---|---|
| `generated.by` | `t2ag/okf_export-<tool version>` | follows the OKF §7 actor convention |
| `generated.at` | the file's last git commit time; falls back to file mtime when unavailable | ISO 8601 UTC |
| `verified` | **not written** | see invariant 3 in §1 |
| `status` | passes through an existing main-repository `status` | the default is `stable`; it is not written proactively |
| `stale_after` | **not written** | see below |
| `sources` | passed through only when the main-repository file already has a machine-recognizable source field | never invent a source just to fill the field |
| `title` / `description` | the first H1 of the body and the first sentence after it | used to compile `index.md` |

`stale_after` is not written because nothing in the exportable scope expires: a mechanism-layer rule
stays valid until it is rewritten, and there is no "automatically invalid on some date" semantics.
The GENERATED caches named in constitution §1.4 (`t2ag_memory.md`, `learning_path.md`) are outside
the scope anyway (§2), so the "a derived cache should be marked stale" case does not arise either.
If the collected scope is ever widened to content that does expire, add a row to this table first,
then change the tool.

### 3.3 Links and graph structure

- An internal relative link in the main repository is rewritten to the bundle-absolute form
  (`/xxx.md`, the OKF §6.1 recommended form, which stays stable after a file moves).
- A link to a file that was not collected is **kept as-is and is not an error**: OKF §6.1 states
  explicitly that a broken link represents "knowledge not yet written", not a format error.
- A link out of the repository or onto the network is kept verbatim.

**A backtick reference is promoted to a link.** T2AG prose references another file with inline
backticks (`` `session_close.md` ``) rather than a markdown link — measured across the mechanism
layer, of 1266 file references, markdown links number **0**. Yet OKF's graph structure is expressed
entirely through links (§6.1: a consumer treats every link as one directed edge). Exporting as-is
would therefore ship a pile of unconnected files, the "knowledge bundle" would degrade into a
"folder", and precisely the whole value of OKF over an ordinary wiki would be lost. So on export, a
backtick reference that resolves to a target inside the bundle is promoted to a link, under **three**
restraining rules:

1. **Promote only the first occurrence of each target per file.** Repeated promotion makes the body
   noisy and adds nothing to the graph but the same edge.
2. **Promote only a reference that resolves to a target inside the bundle.** A reference to the
   instance layer (`progress.md`, `profile.md` and the like) stays a backtick — neither fabricating
   an edge nor manufacturing a broken link.
3. **Promote only when the inline code content is exactly a single path token** (EV-0024 R-3, added
   2026-08-18). The criterion: no whitespace, no quotes or shell metacharacters, does not start with
   `-`, ends in `.md`. The machine landing point is `is_single_path_token()` in `okf_export.py`, and
   the red test is in `test_okf_export.py`.

Rule 3 came out of an independent re-review measurement: the original implementation matched a whole
inline code span with `` `([^`\n]+\.md)` ``, so a complete command like
`` `grep -rn "x" file.md` `` was promoted wholesale into a link, and a multi-target command was
squashed into one edge. That is not a display problem, it is a **substantive semantic rewrite** — a
bundle consumer would read a shell command as a knowledge edge. A template placeholder
(`` `40_course/<COURSE_ID>/course.md` ``) is especially dangerous: the old implementation would fall
back to a bare filename match, hit some real `course.md`, and manufacture a wrong edge out of thin
air. After the fix, 64 inline code spans in the mechanism layer left the promotion surface.

Nothing inside a fenced code block is rewritten: a filename there is an example or a command, not a
reference. When the same filename appears in several places, do not guess; treat it as unresolvable.
Measured, the mechanism layer exports 157 edges (re-measured 2026-08-18; it was 133 during the
re-review, the difference coming mostly from playbook files added in between), and the constitution
has the most in-edges.

## 4. Reserved files

| File | Generated from |
|---|---|
| the bundle root `index.md` | compiled from the entries of each directory; the **only** index allowed to carry frontmatter, and it carries only `okf_version: "0.2"` |
| each directory's `index.md` | compiled from that directory's `_README.md` plus each concept's `title`/`description` |
| the root `log.md` | recent entries of `00_core/t2ag_changelog.md` transcribed into the reverse-date format of OKF §9 |

The purpose of `index.md` is **progressive disclosure** — letting a person or an agent first see what
exists and then decide what to open — so an entry description must come from the linked concept's own
`description` and must never be written a second time by hand.

## 5. The leak gate (before writing to disk, not after)

An export **renders the complete bundle in memory first and lands on disk only after the scan
passes**; on a hit it writes nothing and lists every hit site. Scanning after writing means the
accident has already happened.

The scan reuses `SKELETON_PRIVACY_PATTERNS` from `t2ag_doctor.py` (host user-directory absolute
paths, the maintainer's username, institution names, the private repository names of counterparties).
That word list is a **shared source of truth**: a new pattern is added in doctor in exactly one
place and takes effect in the exporter automatically; never copy a second list into the exporter.

A hit cannot be exempted. A personal trace appearing inside the `mechanism` scope means that
main-repository file itself needs redacting, and the correct response is to fix the main repository,
not to add an exporter allowlist — an exemption list hollows the gate out (the same-family lesson as
P-0065 / P-0067).

### 5.1 Delivery-directory admission (EV-0024 P0, added 2026-08-18)

The gate above is mounted on **content**, but the independent re-review of 2026-08-09 pointed out
that no gate was mounted on the **landing point**. `write_bundle()` deletes any `.md` in the target
directory that is not in the manifest, and `--out` was originally a bare path with no repository
boundary validation at all — a single `--write --out main/50_playbook` would recursively delete every
markdown file in the playbook that was not in that export's manifest. The finding was judged "a
high-risk write path capable of destroying the main repository", and the whole batch was held back
from commit for nine days because of it.

The admission rules (machine landing point `validate_out_dir()`, run before any delete action):

| # | Rule | What it rejects |
|---|---|---|
| 1 | `--out` must not be the repository root, `main/`, the workspace root, or an ancestor of any of them | a slip that points inside the repository |
| 2 | `--out` must not land inside the repository | a bundle is an out-of-repo artifact (invariant 1 restated on the landing-point side) |
| 3 | When it lands inside any git working tree it must carry the `.t2ag-okf-bundle` marker | Skeleton, Lite, a foreign repository |
| 4 | An existing non-empty directory must carry that marker | "not a bundle I wrote last time" is not touched |

The marker file `.t2ag-okf-bundle` is created by the exporter itself when it writes a brand-new
directory. It is a **statement of the directory's identity**, not configuration: delete it and the
next `--write` will refuse to write that directory.

Two more items closed in the same batch (P0-2 / P0-4):

- Every write target must, after `resolve()`, lie strictly inside `--out` (guarding against a `..`
  slipped into a relative path);
- When a leftover file cannot be deleted, or a file outside the manifest appears in the delivery
  directory (**not limited to `.md`**), **return an error with exit code 1**. The original
  implementation only WARNed and exited 0 in the end, so an old leaked artifact could stay in the
  delivery directory while the caller could not tell the delivery had failed — "cannot clean up and
  says nothing about it" is exactly the shape this protocol must never have.

## 6. Self-check (conformance)

`okf_export.py --check-bundle <path>` recomputes the three hard conditions of OKF §11:

1. every non-reserved `.md` has parseable YAML frontmatter;
2. every frontmatter has a non-empty `type`;
3. `index.md` / `log.md` conform to the §8 / §9 structure.

Plus a re-scan for leaks. It is **not registered in the doctor runtime**: a bundle is an optional
artifact, and its absence or staleness must not FAIL that day's teaching; this has the same
orientation as `t2ag.md` §3.2, "a release problem does not block teaching".

## 7. Phase two: the import boundary (not implemented in this phase)

The constraints on an external OKF bundle entering T2AG — set the rules first, discuss implementation
later:

1. **A read-only reference layer.** An external concept maps to a `SourceDocument` candidate or a
   reference material, and **never** directly produces a T2AG object (Course / progress / ledger).
   External content must never become a progress fact.
2. **Do not cross constitution §1.5.** Teaching must still rest on source text traceable to a
   `SourceDocument`, and must consume the `SourcePageAsset` evidence of the current `LessonScope`.
   Imported content may serve as reference; it cannot replace the source text.
3. **A trust gate.** Only human-reviewed concepts (`verified` containing a `human:` actor) are
   accepted by default; unverified and machine-confirmed ones are released one at a time.
   `status: deprecated` is never accepted; a concept with `today >= stale_after` is disabled on the
   teaching side.
4. **Do not execute Attested Computation.** The `executor` / `attester` of OKF §10 point at runnable
   code, which amounts to importing external code-execution rights into the main repository; that
   requires its own adjudication and this protocol does not grant it.
5. Implementation gets its own work order. This section only sets the boundary and is not a
   construction authorization.

## 8. Version and drift

The bundle root `index.md` declares `okf_version`, letting a consumer degrade on its own for a
version it does not recognize (OKF §12). OKF is a young specification, published only in June 2026,
and v0.1→v0.2 already changed two fields (`timestamp` → `generated.at`; the body `# Citations` →
frontmatter `sources`). Therefore:

- a specification upgrade changes **the mapping table in this file** only, and the tool follows the
  table;
- on upgrade, record in the changelog "target version x.y → x.z, and which rows of the table
  changed"; silently following a new version is not allowed.
