# The rule admission gate (R-GATE)

**Protection level**: meta-playbook

> This file is one of T2AG's "skill consolidation" documents.
> Triggered when a new rule is about to be written into `00_core/` or `50_playbook/`.
>
> **Applies to**: adding a behavioural constraint, changing how an existing clause is enforced,
> backfilling an enforcement landing onto an old clause,
> judging whether a suggestion should become a rule at all.
>
> **Machine landing point**: `runtime.rule_enforcement_integrity` (`70_tools/t2ag_doctor.py`).

## 1. Q0, the rejection line

The first question at admission is not "is this rule correct", but "**does it have failure
visibility**".

A clause of the following kind is **not admitted**: a character imperative telling the model to be
"safe", "beneficial", "honest", or "not lazy".
Not because they are wrong, but because **their failure produces no observable difference** — written
or not, the repository looks exactly the same. Such a clause's real function is to reassure the person
writing it, not to make the system better; putting it into the constitution or a playbook only dilutes
the density of clauses that do have a landing (the attention-overload line; see
`doctor_contracts.md` §8 item 1).

This line's own enforcement is declared honestly as follows (it is the only real annotation in this
file, and the first sample of R-GATE):

enforcement: prose_accepted (reason: semantic recognition has no machine means; failure is caught by student review)

Writing that line means: **this line itself has no machine landing point, and admits it**. R-GATE does
not require every rule to have machine enforcement; it requires every rule to **state whether it has
one**. A false guarantee is more toxic than no guarantee (the P-0067 family).

This line applies inside this file only and **does not enter the constitution** (D5-A). A constitution
section has a `[max N]` line budget with no room for an explanatory clause; putting the criterion here
and keeping the constitution lean are two sides of the same decision.

## 2. The `enforcement:` field specification

A rule's enforcement takes one of four values. **Examples always go inside a fence** (see §4):

```text
enforcement: check=runtime.problemlog_closure
enforcement: tool=70_tools/t2ag_hint_gate.py
enforcement: context=50_playbook/session_close.md#The mandatory transaction shared by Micro and full close
enforcement: prose_accepted (reason: state clearly why no machine means exists)
```

| Value | Meaning | Machine check | When dangling |
|---|---|---|---|
| `check=<doctor check ID>` | enforced by one atomic doctor check | the ID must exist | **FAIL** |
| `tool=<path relative to MAIN>` | enforced by some tool's code | the file must exist | **FAIL** |
| `context=<path>#<anchor text>` | relies on context being fed in; the rule does not self-execute | the file exists and contains the anchor | **WARN** |
| `prose_accepted (reason)` | admits there is no machine means | the parenthesized reason is non-empty | **WARN** |

**The value of `check=` must be a full key name of `doctor_checks` in
`validation_workflow.json`**, including the profile prefix (such as `runtime.gate_ledger`) — **not** a
finding code (`GATE-LEDGER-007` is a finding code, not a check ID). The problem log's
`closure: check=` **shares one namespace** with this field; only one set of IDs may exist across the
two — see the backfill contract at the top of `00_core/t2ag_problemlog.md`.

**The parsing semantics of `context=`** (three rules, prose and code from one source):

1. **The path is relative to the `MAIN/` root** — the same mental model as `tool=`; two baselines are
   two sets of bugs.
2. **Split at the first `#`**, and everything after it is the anchor text, so the anchor text may itself
   contain a `#`.
3. **Exact substring match, zero normalization** (no whitespace collapsing, no case folding). This one
   only WARNs, and fuzzy matching plus not blocking amounts to nothing — normalization here would be
   fitting a silencer to a check that only ever warns.

**Guidance on choosing the anchor text**: pick a **short, stable phrase**, not a whole sentence. An
anchor breaking is normal, not exceptional, so the design goal is **to make re-anchoring cheap**, not
to make the anchor unbreakable.

**The `model_dependent:` field** (added 2026-08-19, HARNESS Q3 adjudication): at admission, a new rule
declares whether it is still obeyed on a low-model shell — `yes` (measured: a low model obeys it too) |
`no` (measured: only a high model holds it; the rigidity has a reason) | `unknown` (unmeasured, the
default). **Existing rules are not backfilled** and are all treated as
`unknown` (a declaration semantic, not a bulk edit). The only legal source of a value is a DP scorecard
measurement (`batch_workorder_spec.md` §2.8); filling in yes/no on a hunch is not accepted. This field
has no machine check at present
(the same family as prose_accepted); it fills in gradually as scorecard data accumulates, and a rule
whose difference is 0 is a candidate for relaxing rigidity.

## 3. Placement discipline

`enforcement:` **may appear only in the following files** (the doctor allowlist, from the same source as
the code):

- all of `50_playbook/*.md`;
- `00_core/domain_model.md`, `00_core/learning_activity_model.md`,
  `00_core/pattern_retire_loop.md`.

`closure:` **may appear only in** `00_core/t2ag_problemlog.md`. Each field has its own territory, and
either appearing in the other's file is a **FAIL**.

**The exclusion list and its reasons** (this is a decision, not an oversight):

- `00_core/t2ag_changelog.md`, the body of `00_core/t2ag_problemlog.md`, and
  `00_core/t2ag_memory.md` — **append-only records whose history must not be edited back**. Bringing
  them into the scan would mean a quoted historical annotation turns into a FAIL because the check it
  cites is later renamed or retired, so "fixing" it would mean editing history. The record area is not
  scanned.
- GENERATED blocks — a projection, not a source; changing them is meaningless.
- **The constitution `main/t2ag.md` is explicitly exempt.** Two reasons: the D5-A adjudication (criteria
  do not enter the constitution); and each constitution section has a `[max N]` line budget that an
  annotation line would blow.
  **This is a decision, not a hole** — it is written down here precisely so that six months later I do
  not mistake it for a hole and reopen the round.

## 4. Self-reference escape (a hard constraint, ahead of every example)

This file lives in `50_playbook/`, and it is covered in `enforcement:` examples — **the document
triggers the very check it is creating**. Each side carries half:

- **The document-side obligation**: an `enforcement:` / `closure:` example in this file, or in any
  document, **must go inside a fenced code block**. Anything written outside a fence at the start of a
  line is treated as a real annotation and is checked.
- **The code-side obligation**: the findings pure function **strips every fence first**, then matches
  only field lines at the start of a line (tolerating a list marker and indentation).

Both safeguards are needed: with document discipline alone, one slip causes a false report; with fence
stripping alone, an inline quotation is still caught.

## 5. Two strikes and the escalation pressure

A problem with `occurrence_count >= 2` may no longer end in prose — **the contract body is in the
backfill contract at the top of `00_core/t2ag_problemlog.md` and is not copied here**, only pointed at.
Copy it and it drifts, and after it drifts nobody knows which copy counts.

Although the `context=` class only WARNs, **the escalation pressure is the same**: the same context
anchor failing repeatedly means the context it depends on is itself unstable, and after two strikes it
should become `check=` / `tool=`, or be honestly demoted to
`prose_accepted` with the reason written out. WARN means "does not block", not "may stay this way
forever".

## 6. Backfilling old clauses

Existing clauses are **not required** to be backfilled, and there is no deadline (D3-A′). When you do
want to backfill:

- the survey base is in `../../docs/handoffs/T2AG_RGATE_OLD_RULE_SURVEY_2026-08-15.md`;
- the backfill results go into that file's §4 table, updated as you go;
- a backfill is checked immediately — the moment `enforcement:` is written, everything in this document
  applies.

A clause left un-backfilled stays as it is, and doctor **does not check "should have declared but did
not"** (draft §2 R4: that is the self-referential account, already accepted as `prose_accepted`). R-GATE
governs **what was said having to hold**, not **what was left unsaid**.
