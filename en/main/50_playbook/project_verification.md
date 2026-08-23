# Project-track verification v1.1 (project_verification.md) — consolidated final

**Protection level**: playbook

> **Placement**: this file lives in `50_playbook/` (it is mostly the operational detail of "how to accept");
> the three-mechanism clause is hung into the acceptance-mechanism section of `main/50_playbook/course_group_rules.md` as one sentence.
> The two earlier files (project_rules / project_rules_amendment) are abolished, their content is merged here, and the changelog records v1.1.

## 0. Protocol summary (the sentence hung on the constitution)

> Every milestone of a project-track course must be bound to a verification mode (A/B/B-K, registered before the group is formed or before the M starts; a major-adjustment window may change an M that has not started), and any mode must satisfy the three mechanisms: an external source of truth, an independence measurement, and a trace left by failure.

### Environment inertia and the clean-room verification boundary

- Startup, doctor, an ordinary course, and an ordinary milestone acceptance only inspect the existing
  environment; they never automatically create, delete, rebuild, or upgrade a `.venv`, and never run
  `pip install` on their own.
- Use the project's existing interpreter first for `python --version`, `pip check`, the dependency
  list, and a minimal smoke test.
- Only when there is real evidence that the existing environment is damaged, or when the user
  explicitly asks for a clean-room reproduction, may an independent verification environment be
  proposed; before running it you must state the package names, the lock file, the expected download
  size, the disk footprint, the cache location, and the time cost, and obtain authorization.
- Clean-room verification uses an independent temporary directory or `.venv-verify`; it must never
  delete, overwrite, or rewrite the current `.venv`.
- Lite is a snapshot for online model review; inside lite, review the rules and the evidence only and
  perform no environment verification or download.

#### Candidate constraint options and the current adjudication

| Option | Constraint | Advantage | Cost | Current status |
|---|---|---|---|---|
| A strict freeze | reuse the existing `.venv` read-only; on a missing package, stop and request | zero surprise downloads, most stable | cannot self-heal when the environment is damaged | **enabled by default** |
| B light/heavy split | the base environment only runs doctor/scripts; heavy OCR dependencies go into a separate `.venv-ocr` | small everyday environment, clear responsibilities | splitting now means downloading again; needs a planned migration | choose at the next formal rebuild |
| C shared cache + budget | reuse the pip/model cache; cap the size of a single download and stop when exceeded | avoids re-pulling packages | the cache itself takes space and needs periodic reporting | enabled when an install is authorized |

The current environment is healthy, so the **non-destructive combination A + C** applies: do not split,
do not delete, do not reinstall; only when an install is authorized in future are the cache reused and
the budget declared. If the projected new download exceeds the declared value by 20%, or the new disk
use exceeds 500 MB, stop immediately and request authorization again. Clearing the cache likewise needs
authorization; do not free space in a way that forces a re-download next time.

A routine environment check must not recursively stat every file in `.venv`. Only these are permitted:

1. `.venv/pyvenv.cfg` and the interpreter path;
2. `python --version`, `python -m pip check`;
3. `python -m pip list --not-required` and `pip show` on the target package;
4. the minimal smoke test directly relevant to the current task.

Recursive package-size computation is allowed only in a dedicated disk audit that the user explicitly
asked for.


## 1. Mode A · product acceptance (in detail)

**Applies to**: an M producing a runnable system or deliverable. **The external source of truth = real execution.**

### The five-step acceptance ritual (at the end of the M, about 90 minutes, complete only if all five pass)
1. **Reproducibility check** (15min): use the existing project interpreter to check the versions,
   `pip check`, the lock file, and a minimal smoke test, then run the main flow. Record an environment
   anomaly in the problem log; deleting and rebuilding the current `.venv` must never be treated as an
   ordinary acceptance step. A clean-room rebuild is performed separately, only within the
   authorization boundary above
2. **Objective acceptance** (20min): tick off the acceptance criteria registered for this M one by one.
   The criteria must have been written as decidable sentences when the M started ("runs 3 days in a
   row", "consistency rate ≥80%"); finding a vague criterion on acceptance day = a criterion-setting
   incident, recorded in the problem log, rewritten as a decidable sentence on the spot and only then
   ticked
3. **Oral explanation** (20min): seeded by the day, draw 2–3 student-written functions at random from
   the git history and have them explained line by line without notes: why it was written this way /
   what would happen if changed to X / what the pitfall was at the time.
   A stall = being unable to state the design reason (saying something wrong but reasoning coherently
   is not a stall) and goes into the stall account
4. **Blind-modification challenge** (30min, the core step): the teacher improvises a 15–30min change
   request from this M's content (add a filter condition / change the output format / swap a data-source
   field). Requirements: ① the same technology stack as the existing feature ② a decidable completion
   criterion ③ the teacher works out a solution themselves after setting it, to confirm feasibility.
   The student implements it independently, and the hint ladder is accounted for
   (a level-one direction hint = 1, a level-two step hint = 2, a level-three worked demonstration = this
   item fails)
5. **Archived** (5min): the results of all five steps go into the `progress.md` teaching record;
   conceptual errors exposed by ③ and ④ go into the mistake bank; emit an acceptance confirmation block
   (in the same format as the session-close ritual)

### The failure ladder
Failed item → a catch-up window (it consumes buffer and covers only the failed items) → re-verification →
still failing → a scope adjudication in the major-adjustment window: cut the non-core items as
"completed with a note", or roll the whole M into the next group. Core vs non-core is fixed when the M
starts and may not be changed on acceptance day.

## 2. Mode B · judge-machine type (in detail)

**Applies to**: an M of problem drilling, algorithms, or tool practice. **The external source of truth = the OJ judge**
(Codeforces / Luogu / LeetCode; register the platform and account when the group is formed, and doctor
reconciles against the submission record).

### M parameters (registered at start, decidable)
```
| segment (rating band) | problem count | tag range (mapped to course knowledge nodes) | AC-rate floor | first-kill-rate floor |
e.g.: | CF 1200-1400 | 20 problems | binary search / prefix sums / constructive | ≥60% | ≥50% |
```

### Day-to-day flow
- Problem selection: choose within the registered tags and band; deliberately farming already-mastered problem types for volume is forbidden (each tag has at least a quota, governed by the registration table)
- **Definition of a first kill**: an AC with no editorial and no AI hint whatsoever. Having read an
  editorial = that problem is marked "unlocked", does not count as a first kill, and **must be redone in
  a variant after 3 days**: substitute an unattempted problem of the same tag and band as the retake
- The AI boundary: forbidden before and during a contest; in the post-contest review AI may explain an
  editorial, and any problem so explained is treated as "unlocked" from then on
- The WA account: the number of WAs before each AC is recorded as-is (the OJ has it automatically), and
  the mean is an auxiliary independence indicator
- Error recovery: every "unlocked" problem and every high-WA problem goes into the mistake bank by root
  cause (boundary condition / complexity misjudgement / data-structure choice / misreading the problem —
  an algorithmic error is a conceptual error too)

### M acceptance (30 minutes, a reconciliation is enough — the judge has already given the exam)
1. Check the numbers against the parameter table: problem count / AC rate / first-kill rate, with the submission record governing
2. One live first kill: one unseen problem in the same band under time limit, with the teacher watching and giving no hints (mode B's equivalent of the blind modification)
3. Archiving is the same as A step 5

### The failure ladder
An indicator falls short → **drop a band to clear the blockage** (1400 stuck → go back to 1200, clear
10 problems and then climb; the drop leaves a trace) →
still short → the same scope adjudication as A. Moving a rating band up or down is a major-adjustment-window
authority.

## 2B. Mode B-K · the Kaggle variant of the judge-machine type

**Applies to**: an M of data-science competition or evaluation. **The external source of truth = the Kaggle private leaderboard or a fixed-seed CV score.**

It inherits every rule of mode B; only these four differ:

| Dimension | Mode B (OJ) | Mode B-K (Kaggle) |
|---|---|---|
| Source-of-truth signal | binary AC/WA | private-leaderboard percentile / fixed-seed CV score (continuous) |
| First-kill definition | an AC without reading an editorial | a submission reaching the target percentile without having read any public notebook or discussion solution for that competition |
| Handling an unlock | reading the editorial = unlocked; redo a same-tag variant after 3 days | reading a kernel = unlocked; after 3 days, reproduce that technique independently on another dataset or another feature group |
| Auxiliary independence account | mean WA count | submissions-to-score-gain ratio (a spike in submissions with a flat score = fitting the public leaderboard; record it as a warning) |

**M parameter registration format**:
```
| competition | target (private-LB percentile or CV score) | submission budget | permitted unlocks | first-kill-rate floor |
```

- The submission budget is discipline, not a resource: continuing to submit over budget = the problem log records that M and acceptance is downgraded.
- The public LB is a process signal only; acceptance never recognizes the public LB — it can be fitted by repeated submission, and recognizing it is recognizing AI approval.
- The AI boundary (inherited from B): AI-generated modelling code is forbidden before a leaderboard submission; AI may explain a concept and review code already written; any technique AI wrote is treated as "unlocked".

## 3. M-level binding and the mode-switch rule (from the last discussion round, final)

- One mode per M, registered in the "Verification mode" column of the `progress.md` milestone table
- A major-adjustment window may change the mode of an **M that has not started**, with a trace (old / new / reason, one line);
  an in-progress or completed M may not be switched — "the fatigue of the moment" gets no vote
- The independence account is presented per M on its own row (blind-modification hints / stalls vs first-kill rate / mean WA), and is **never converted across modes**

## 4. Doctor checks (this table replaces the old entries)
| Check | Level |
|---|---|
| a started M lacks a verification-mode registration | WARN |
| an M marked complete with no matching acceptance record (A: the five steps / B: the reconciliation) | FAIL |

The mechanical carrier in 0.2.0 is the three columns "Verification mode", "Acceptance criteria", and
"Closure evidence" in the `progress.md` Completion nodes table. Acceptance criteria are registered before
the node starts and must never masquerade as completion evidence; while a node is unfinished, the closure
evidence must be `—`. The mode may only be `A / B / B-K`; `in_progress` and `completed` both count as
started.

The closure evidence of a `completed` node must be a pointer to an in-repository acceptance record, in
the format `main/<path>.md#VER-<COURSE>-<NODE>-<YYYYMMDD>`. The target heading uses the same `VER-*` ID
and contains at least the node, the verification mode, a `passed` conclusion, and the acceptance date.
The five step fields of mode A are
"Reproducibility check / Objective acceptance / Oral explanation / Blind-modification challenge / Archived";
the fields of mode B / B-K are
"Metric reconciliation / Live independent verification / Archived". The canonical spelling of each step is
`passed · <a non-empty summary of the actual result>`; when the compatible separators `: / ： / ; / ；` are
used, a summary containing at least one Unicode letter or digit must still follow the separator —
punctuation or symbols alone do not count as an actual result. A bare `passed`,
`passed ·`, `passed:   `, `passed · :`, a missing field, or anything other than `passed` all leave it
unclosed. A `Conclusion: passed` for the record as a whole cannot substitute for any step's actual result
summary. Copying the pre-set criteria into the closure evidence, or merely flipping the status, must both
FAIL.

An external judge account, the git history of a student project repository, and rest days currently have
no stable in-repository evidence interface, so "a submission gap of >7 days" and "a git interval of >7
days" are manual checks at course start or acceptance; doctor must never guess them or fake a pass.
