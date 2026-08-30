# Remediation governance rules

**Protection level**: meta-playbook

> These rules govern defect repair, independent re-review and release remediation. The goal
> is to separate reproducible fact from model inference and from the requirement itself, so
> that repeated model failure never silently raises a severity or forces a repair through.

## 1. Classifying a problem

| Class | Criterion | Default handling |
|---|---|---|
| `FAIL` | reproducible, locatable, and violates an explicit current contract | repair; blocks the release while a hard release gate is non-zero |
| `REVIEW` | the requirement is vague, model judgement is unstable, or several reasonable designs exist | separate fact / inference / requirement and discuss with whoever raised it |
| `WARN` | the fact holds but does not block the current goal | keep the evidence and handle it in the agreed window |
| `WAIVED` | after discussion with whoever raised it, explicitly deferred or accepted as an external environment risk | record the approval, evidence, risk and expiry |

`REVIEW` is not a milder `FAIL`, and `WAIVED` is not a fake green. A change of class requires
new evidence, a contract change, or an explicit adjudication from whoever raised the
requirement — never merely the fact that the model has tried several times.

## 2. Bounded remediation and campaign stop-loss

<!-- rule: AUTH-NONAMP-005 -->
Before a formal campaign begins, freeze the acceptance specification and its version, the
definition of done, the maximum number of remediation rounds, the number of full re-reviews,
and the count of test commands, the time and the token budget. The default is
**at most two rounds of finding remediation by default** and two full candidate re-reviews,
with at most three substantively different attempts per round:

1. When round one still fails, reclassify and enter round two.
2. When round two has not converged, or any frozen budget reaches its ceiling first, stop
   construction immediately, record the state as `stopped_budget`, output the evidence held
   and the unclosed items, and wait for whoever raised the requirement to decide.
3. Never evade the ceiling by changing the RD number, re-freezing an equivalent package,
   opening a continuation order, or splitting one finding.
4. If a new criterion reveals that an existing safety or core contract was violated, stop and
   report; never auto-expand the current definition of done and never auto-generate the next
   round of remediation.

One valid attempt must contain a new change, diagnostic method, piece of evidence, or reading
of the contract. Re-running the same command against the same state is not a new attempt.
Record the hypothesis, action, result and reason for classification each round. Work may
continue only when whoever raised the requirement explicitly approves a new bounded envelope
after the budget is exhausted.

## 3. Hard release gates and waivers

A failure of any of the following current contracts may never be waived:

- data integrity, or the risk of irreversible loss;
- a dangling activity entry point, pointer or recovery path;
- a schema conflict or a stable-ID conflict;
- authoritative sources that contradict each other;
- a Main/Skeleton contract difference beyond the approved divergence;
- a missing file, a difference, or an orphan in the Main -> Lite projection.

If the requirement itself is unreasonable, whoever raised it may explicitly amend or withdraw
the contract; that is a requirement change, not a waiver.

Only a check that fails because of the external environment, without affecting in-repo
correctness, may apply for `WAIVED`. A formal waiver must record:

- the check and the reproduction evidence;
- why it cannot be fixed inside the repo;
- the risk to the current release;
- the approver and the time of approval;
- the expiry time, or the condition for re-verification.

Doctor must never display a waiver as PASS; it displays `WARN/WAIVED`. An independent
re-review may still reject a waiver.

## 4. How acceptance is stated

- A mechanical check passing says only that the checked contract passed.
- While a `REVIEW` is open, never write "independent re-review found no blockers".
- A release conclusion must list the WARNs and WAIVEDs still in force and the boundary of
  human review.
- Retry count, model confidence, and the tone of a problem description are not substitutes
  for evidence.

## 5. Version candidates and delta re-review

### 5.1 The first candidate

The first release candidate of every version must undergo a full independent re-review. The
current 0.2.1 has no inheritable fully-passed baseline, so a finding delta or a self-check by
the implementer must not stand in for a full-version review.

### 5.2 Delta manifest and impact closure

Each remediation uses a stable `D-n` and records at least:

```text
pre/post fingerprints
changed files and permitted paths
direct / indirect consumers
generated artifacts
Main/Skeleton/Lite impact closure
reused evidence ID, input manifest SHA, and the new delta
```

Several already-listed RT1/RT2 optimizations within one version may accumulate into a single
candidate delta pack, reviewed once for its full impact closure, rather than mechanically
re-reading the whole repo once per requirement. A historical scope that already passed and
whose fingerprint has not changed must not be re-reviewed in full merely because an ordinary
optimization was added.

### 5.3 The indivisible global gates

A delta re-review may re-review only the finding delta, but every one of the following global
gates must be re-run each time:

- `t2ag_doctor.py --profile release` and state refresh;
- migration, journal/index and unfinished transactions;
- Main/Skeleton parity files;
- the Main -> Lite projection;
- the final source, the candidate tree, and the input docs manifest fingerprints.

An existing report, citation attribution or test evidence may be reused only while its input
manifest SHA is unchanged. When reusing, record the old evidence ID and the new delta rather
than copying the text; a fingerprint change in a file outside the scope must refuse reuse.

### 5.4 Boundaries that force a return to full review

None of the following may be handled by a delta re-review alone: the authority chain, a
schema, registry lifecycle, migration apply semantics, the transaction engine, candidate
generation, a safety/privacy boundary, or an unprovable impact closure. The old candidate is
then void: a new candidate must be formed and fully independently re-reviewed.

### 5.5 Reviewer independence and finalization

- A delta reviewer must not be that delta's operator. The previous round's independent
  reviewer may be reused, but the model/session, the pre/post output, the `expected tree`,
  the staged diff SHA and the final attestation SHA must all be recorded;
- finalization reviews the expected tree before the commit and verifies parent/tree/diff
  after it; a tree mismatch, an out-of-scope path, operator self-review, a report written
  back, or an early PASS are all refused;
- the reviewer output is an immutable external report produced last, after the stability
  checks complete. A PASS is never written back into the target repo, the construction report
  or an index, which would otherwise mean "writing a pass conclusion while creating a fresh
  unreviewed delta".

### 5.6 Review cost and environment pre-checks

- An ordinary in-version optimization reviews only the proven impact closure and re-runs the
  §5.3 global gates; a full V runs once against one frozen release candidate. Only a new
  P0/P1/P2, a scope expansion, or an unprovable impact closure voids the candidate, at which
  point a new candidate is frozen and the full V re-run; finalization reviews only the bounded
  delta of §5.5;
- before a long test, verify that the reviewer can read Main/Skeleton/Lite, that the report
  parent can be written atomically, that a temp-root can complete one create/delete, and that
  scripts and contracts are readable. Permission failures, timeouts and unreadable scripts are
  infrastructure failures and must never pose as a product negative-case PASS;
- a LOOP does a single random `mkdir` write probe before building fixtures, gives every
  subprocess an explicit timeout, and lands durable progress somewhere other than stdout
  first. Per environment boundary: at most one normal attempt plus one bounded diagnostic, and
  never a repeated empty run of the same long command while the preconditions are unchanged;
- `.venv` must never be recursively hashed as an ordinary review object. Confirm only that the
  directory still exists, that `pyvenv.cfg` matches the frozen evidence, and that the campaign
  ran no create, delete, install or upgrade command; check the dependency manifest only when a
  dependency change is in scope;
- ordinary review of `.recovery` and `.staging` confirms only that they still exist and that
  nothing was deleted; inspect the contents only when the recovery/staging function itself is
  in the construction scope;
- tracked content is bound by a clean HEAD/tree plus `git status`, so large files are not read
  again. Real course evidence prefers a frozen manifest; only files whose path/size/mtime or
  Git blob changed get a recomputed SHA;
- any check expected to read more than 100 MB or 10,000 files must record, before running, the
  specific reason the existing digest cannot be reused. Without that proof, refuse the
  automatic full scan; and evidence from a large scan that already happened must never be
  promoted into a standing gate.

## 6. The trade-off principle: quality first, saving cost is the concession

> **Guaranteeing quality is mandatory; saving tokens / time / compute is a last resort.
> Trading system reliability for cost never holds, at any time.**

The student set this principle explicitly on 2026-08-07, to decide which way "cheaper" and
"more reliable" resolve when they conflict. It is a **criterion**, not a statement of attitude
— two corollaries apply directly:

1. **A false positive (extra cost) and a false negative (lost content) are not symmetric, and
   false negatives must never be increased to reduce false positives.**
   Typical shapes: raising a threshold to lower the hit rate, turning a disjunctive criterion
   into a conjunctive one, adding an exemption to a gate. Such changes trade a **cost error**
   for a **content error** — the wrong direction, and **never to be made on unverified evidence**.
2. **A cost-saving change must first prove it does not reduce correctness**; where that cannot
   be proven, the correct action is not to make it, rather than "ship it and watch". The cost
   of watching falls on the student, not on whoever made the change.

**Precedent already applied** (`source_page_assets.md` §3.2.5, the C5 criterion of
`layout_critical`): across a 14-page sample, `ratio > 2.2` produced 5 false positives and
**0 false negatives**. Under this principle the threshold stands, which rejected both
"raise the threshold to dodge inline formulas" (would miss small figures) and "add a
conjunctive term to cut false positives" (turns a cost error into a content error), at the
price of continuing to pay more page-image tokens.

## 7. The re-review criterion: the carrier a check reads is not the fact it guarantees

**When reviewing any newly added automatic check, gate or acceptance criterion, an independent
re-review must ask:**

> **Is the carrier this check actually reads the same thing as the fact it claims to guarantee?
> If it is not, it cannot guarantee that fact.**

The criterion comes from three defects of the same shape that appeared within one day. The
common structure is "the declaring carrier is cheap and machine-readable, the substantive
carrier is expensive or unreadable, and the check can only reach the former":

| Case | What the check read (declaring carrier) | What it had to guarantee (substantive carrier) | Consequence |
|---|---|---|---|
| `P-0058` | the `progress.md` frontmatter pointer | the checkpoint table | a hand-written value passed, and `--check` reported green twice running |
| the frontmatter trap (`source_page_assets.md` §3.2.4) | the four preconditions of `page_NN.md`, all in frontmatter | the page body | all four preconditions were satisfied while not one word of the body was delivered |
| `P-0059` | the checkpoint row marked `confirmed` | the figure actually delivered | recorded as covered, with no delivery trace in any of the three places |

**All three were noticed by a human, and not one was found by any automatic check** — which is
exactly why this belongs as a re-review question rather than as another check: a meta-check
that audits this kind of mismatch would itself depend on every check honestly declaring what
it reads, and that is one more instance of the same defect.

**When a mismatch is found** (choose one; leaving it open is not permitted):
make the check read the substantive carrier; or add a producer for the substantive carrier so
the two become one (what `P-0058` did); or **state explicitly next to the check what it cannot
guarantee**, so a caller never assumes coverage
(the known false negative in `source_page_assets.md` §3.2.5 is handled this way, and pinned by a test).
