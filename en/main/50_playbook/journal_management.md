# The journal management flow

**Protection level**: meta-playbook

> This file is one of T2AG's "skill consolidation" documents.
> Triggered when the user explicitly asks to save an important conversation, a key decision, a to-do, or a cross-course event record.
>
> **Applies to**: recording events and decisions that are not course progress, not a system fault, and not a rule change, but are worth going back to on purpose later.

---

## 1. Core principles

- A journal stores **events, decisions, to-dos**; it is not a fact injection, not a mistake book, and not a rule source.
- It is never written automatically by default; write only when the user explicitly says "record this in the journal / save this passage / this part matters".
- Each entry keeps only the non-trivial decisions and conclusions; small talk, repeated confirmations, and meaningless process are deleted.
- By default, every conversation with a non-trivial result gets a new `YYYY-MM-DD-<topic>.md`.
- Append to an old file only when the new content is a direct continuation or correction of that old journal.
- When merging is uncertain, read this month's and last month's indexes first, then ask the user whether to create a new entry or append.

---

## 2. Triage against the existing files

| Content type | Written to |
|---|---|
| a rule, structure, template, or tool change | `main/00_core/t2ag_changelog.md` |
| a system/process problem and its solution | `main/00_core/t2ag_problemlog.md` |
| course progress, the stopping point, the teaching record | `[course]/progress.md` / the current Lesson or Exercise main carrier |
| a student knowledge error | `[course]/mistake_bank.md` |
| the student's emotions, character, how the course felt | `main/10_student/profile/profile.md` / `course_reflections.md` |
| a local thought inside a Lesson | `lessons/lessonNN/lesson_thoughts.md` (created when one really appears) |
| a student's verbatim words in an Exercise, and the cross-problem index | the matching Attempt / `exercises/exercise_thoughts.md` |
| a core-content reflection spanning lessons / exercises | the current course section of `main/10_student/profile/course_reflections.md`, linked back to the local source |
| an important cross-course, cross-practice, non-fault event / decision / to-do | `main/60_journal/` |

The journal is a review layer; it never overrides any source of truth.

---

## 2.5 The Evolution Register and ADRs

| Object | Path | Responsibility |
|---|---|---|
| **Evolution Register** | `main/60_journal/t2ag_evolution_register.md` | the decision lifecycle: `observing → discussing → decided → archived` |
| **Compatibility redirect** | `main/60_journal/t2ag_evolution.md` | no body; `journal_index: false`; points at the Register |
| **ADR** | `docs/adr/` | the portable body of an architectural decision; it does **not** copy the state machine |

Rules (summary; the full field list is in `docs/adr/README.md`):

1. Not every EV produces an ADR; only an architectural decision that crosses modules, is hard to reverse, changes a responsibility/trust boundary, or is reusable across projects gets promoted.
2. A local `accepted` ADR must be linked to ≥1 local `decided`/`archived` architecture EV (`source_evolution`).
3. A `proposed` ADR may be linked to a `discussing` EV.
4. A new `architecture` + `decided`/`archived` EV should have `adr_refs`, or an explicit `adr_exception`.
5. An ADR being accepted ≠ the implementation being done; landing is still expressed by the EV, the changelog, the version state, and the protocol.
6. Deterministic validation: `main/70_tools/decision_record_contract.py` + Doctor `runtime.decision_records`.

`decided → archived` still requires a changelog batch + a landing pointer + one line in that month's index (see the state machine in the Register body).

---

## 3. Directory and naming

```text
main/60_journal/
├── INDEX.md
├── YYYY-MM.md
├── t2ag_evolution_register.md   # the Evolution Register (canonical)
├── t2ag_evolution.md            # redirect only (journal_index: false)
└── YYYY-MM-DD-<topic-keyword>.md
```

- `INDEX.md`: the master index.
- `YYYY-MM.md`: the monthly index/report.
- `YYYY-MM-DD-<topic-keyword>.md`: a single journal entry.

The index tables are maintained by `main/70_tools/build_journal_index.py`. After adding or changing a journal:

```powershell
python -B main/70_tools/build_journal_index.py --write
python -B main/70_tools/build_journal_index.py --check
```

- With no argument, and with an explicit `--check`, it only inspects; only `--write` rewrites a generated block.
- The `T2AG_GENERATED` blocks in `INDEX.md` and the current `YYYY-MM.md` must never be hand-edited; the prose outside a block is still maintained by hand.
- For a new month, create the matching `YYYY-MM.md` and install a monthly-list generation block first, then run the generator.

---

## 4. The single-entry template

```markdown
# YYYY-MM-DD Topic

> **Date**: YYYY-MM-DD
> **Status**: in progress / awaiting verification / done / archived

## Topic

1. ...

## Skills used

| Skill name | Times | Purpose |
|---|---|---|
| `skill-name` | 1 | ... |

> If no skill was loaded this time, write: no skill was loaded in this conversation.

## Key decisions

- ...

## To-do

- [ ] ...

## Related files

- ...
```

### The minimal index metadata schema

- The first level-one heading (`# ...`) is the index title.
- `Date` and `Status` use the blockquote lines from the template; the date format is `YYYY-MM-DD`.
- For compatibility with existing journals, when `Date` is missing it falls back in order to the filename prefix, the date in the level-one heading, and the first ISO date appearing in the heading's lead-in area; when `Status` is missing, `—` is displayed.
- This is the minimal schema for compatibility with old files. The generator never rewrites journal prose in reverse; a new file should fill in the date and status explicitly rather than relying on a fallback.

---

## 5. Common problems

- **Treating the journal as an automatic running log**: wrong. It is not written automatically by default; write only when the user asks.
- **Putting a system fault into the journal**: wrong. A system fault goes into the `problemlog`.
- **Recording a rule change only in the journal**: wrong. A rule change must go into the `changelog`.
- **Merging a new conversation into an old journal by default**: wrong. Merge only for a direct continuation or correction; otherwise create a new entry.
- **Leaving out the skills-used table**: not acceptable. Even when no skill was loaded, write "no skill was loaded in this conversation".
- **Hand-editing a generated index block**: wrong. Change the journal's title or metadata, then run the generator.

---

## 6. Related files

- `main/60_journal/INDEX.md` — the journal master index.
- `main/60_journal/YYYY-MM.md` — the monthly index.
- `main/00_core/t2ag_changelog.md` — rule changes.
- `main/00_core/t2ag_problemlog.md` — system/process problems.
- `main/50_playbook/playbook_management.md` — procedural memory management.
