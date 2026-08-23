# The language-track written examination protocol (exam_protocol)

**Protection level**: core-playbook

> Applies to: the final written examination and the cycle-level quiz of a language-track course. The rule entry point is `main/50_playbook/course_group_rules.md`; problem-bank storage is in `main/50_playbook/exam_bank_spec.md`; the student's parameters are written into `main/10_student/profile/profile.md`.

## 1. The core principle: compile, do not generate

AI does not generate mathematics problems; it downloads, registers, and draws by rule. A real past paper has already been set by a professor, tested on real candidates, and calibrated against an official solution; choosing is cheaper than generating, and verification comes with its own source of truth.

## 2. Building the problem bank

- Location: `main/40_course/<COURSE_ID>/_exam/`. The usual source-cache rules apply.
- Default paper-source scope: universities in the US News top 30 of the relevant subject area; limited to China, Japan, Singapore, the UK, France, Switzerland, and the US. The student's execution parameters may override this.
- Language rule: Chinese and English papers are admitted directly; a French/Japanese/German paper is admitted only when an official English version is attached or the school provides a bilingual one — the model must never be asked to translate a mathematics problem.
- Registration tables: the paper-level table is `_exam/index.md` and the problem-level table is `_exam/papers/[paper-ID]/meta.md`; the fields are in `exam_bank_spec.md`.
- Acquisition routes: MIT OCW (with solutions), the public course pages of each school, papers circulating domestically; a paper with no official solution is downgraded and enters the practice pool only.

## 3. The problem-bank timeline and cooldown

```
cycle:  1    2◆   3▲   4    5◆   6▲   7    8◆   9▲   10   11◆  12▲  13   14 final
        ◆=bank-building day (D7 of the cycle)   ▲=cycle quiz day
```

- A bank-building day is D7 of cycles 2/5/8/11; a quiz day is in 3/6/9/12.
- Each bank-building day collects 1-2 papers from real-paper sources, limited to 2018 and later; after registration they are split into pools by that day's seed.
- Any sitting draws only from problems admitted on the previous bank-building day or earlier, so a new problem is never exposed immediately.
- When stock runs short, a quiz shrinks to 2 problems or is deferred until after the next bank-building day; a non-real-paper source is never brought in to rescue it.
- After cycle 12 the assessment pool is frozen; if the assessment pool holds fewer than 4 papers at the end of cycle 9, doctor WARNs.

## 4. The quiz opening line

Show the student this at the start of every quiz:

> An examination is not there to manufacture suffering; whoever chooses to learn should know what is true of themselves.

## 5. The examination execution table

| Dimension | The single rule |
|---|---|
| Problem source | compiled from real papers; limited to 2018 and later; not generated (a mistake variant excepted) |
| Bank structure | one folder per paper under `papers/`, registered in `index/meta`; the pool is metadata |
| Pool split | a random draw on the day of admission, roughly 70% practice pool / 30% assessment pool |
| Isolation | the assessment pool must never enter teaching; a textbook problem never enters a quiz; at least one bank-building cycle of cooldown |
| Paper assembly | six hard constraints + a random seed; the artifact is a reference list, and problem statements are never re-typeset |
| Suitability | a mechanical list of six REJECT conditions, with the judgement left as a trace |
| Difficulty | the median of three signals — course level, position within the paper, problem type — fixed once registered |
| Time limit | per-problem baseline = source paper's total time ÷ its problem count; quiz ×2, final ×1.2, resit ×1.5 |
| Passing | final 60 → resit ① 60 → resit ② 50 → not passed, course closed, may be retaken, the mistake bank carries over |
| Hints | the exam-version hint ladder is accounted for; when the average is >1 hint per problem, a reinforcement block is triggered and the account is presented separately |
| Review units | derived from how the study felt, the exam result, and a walk back up the dependency chain; at most 2 |
| Grading | against the official solution; the student self-assesses and the teacher reviews |
| Mistake recovery | mistakes from every sitting enter the `mistake_bank` by root cause; the variant rules are in `mistake_retest.md` |
| doctor | an isolation reference is FAIL; a missing registration column is WARN; stock and the freeze period are checked by rule |

## 6. The isolation regime

- The pool is fixed on the day of admission and may never be reassigned afterwards: roughly 70% practice pool, 30% assessment pool.
- The practice pool: drawn on for ordinary exercise classes and cycle quizzes.
- The assessment pool: nobody, the teacher included, may reference its problems while teaching.
- A paper already sat moves from the assessment pool into the practice pool; a paper is sat only once.

## 7. Paper assembly rules

The final paper is drawn mechanically from the assessment pool; if it cannot be filled, prompt for more stock rather than relaxing the rules.

- Total: 8-10 problems.
- Coverage: at least 1 problem for each trunk milestone node of this group.
- Ratio: proof problems no less than 60%, computation problems no more than 40%.
- Provenance: at least 3 schools and 2 countries; no more than 3 problems from a single school.
- Difficulty: at least half from the honours tier.
- Drawing: use a public random seed (such as the date of the day); the teacher must never pick "the ones the student can do".
- Artifact: a problem list carrying each problem's provenance and the page reference of its official solution; the statements are never reprinted into a new paper — during the exam, the student turns to the original paper by the list and answers there.

## 8. Grading and thresholds

### 8.1 The grading pipeline (the order is contractual)

Grading follows the same "compile, do not generate" rule: criteria come from the official solution;
the model extracts and checks them, and does not invent them.

```text
official solution -> blind extraction -> scoring-point table with solution-page references
student script -> student self-mapping -> point-by-point teacher check
                                      -> hit / miss / equivalent-alternative flag
optimization feedback -> separate output, never part of the score
```

The scoring-point table is completed before the student script is opened, preventing hindsight from
reshaping the rubric around the student's route. The student maps their own steps first. Each point is
then judged hit, miss, or equivalent alternative; proof problems receive step credit. Correctness and
elegance remain separate: a nicer route is feedback for review, not a score change.

### 8.2 The equivalent-alternative flag

When the student uses a proof route outside the official solution, the model may not score it alone.
It records which theorem or lemma was substituted and where the logical chain reconnects. The point
remains pending until a detailed walkthrough and student sign-off. A disagreement between student
self-mapping and model review follows the same channel. Model dependence is therefore confined to
two explicit, reviewable slots instead of being hidden throughout grading.

### 8.3 The replayable grading record

Each sitting appends to `_exam/exam_ledger.md`: the scoring-point table and page references, student
self-mapping, three-valued decisions, equivalent-alternative flags and sign-offs, disagreements, and
walkthrough conclusions. The record must let a future person or model replay the grading; otherwise
the sitting cannot settle.

### 8.4 Score composition and recovery

- Language-track final mark: 70% written paper, 30% process indicators.
- Post-exam mistakes enter `mistake_bank.md` by root cause.
- Variants follow `mistake_retest.md`; self-produced variants never enter a final or resit.

## 9. Time limits and resits

Each source school's exam duration and problem count are already calibrated together, and a mixed paper inherits the source paper's baseline:

```text
per-problem baseline time = source paper's total time / its problem count
assembled paper's baseline time = Σ the per-problem baseline of every drawn problem
```

| Sitting | Duration | Pass mark |
|---|---|---|
| cycle quiz (on a major-adjustment window day) | baseline × 2.0; distributed thinking and hints allowed | not weighted, monitoring only |
| final paper | baseline × 1.2, closed book, continuous | 60% |
| resit ① (after review unit ①) | baseline × 1.5 | 60% |
| resit ② (after review unit ②) | baseline × 1.5 | 50% |
| resit ② still failed | — | marked not passed, course closed |

- The hint ladder and the hint account apply as usual: used freely in a quiz, sparingly in a final, and presented as a separate account.
- When the average exceeds 1 hint per problem, a 3-day reinforcement block is triggered.
- Review units ① and ② are generated from how the study felt, the exam result, and a walk back up the dependency chain.

## 10. Handling a failure

- That course's `progress.md` status becomes `archived (not passed)`, with the paper trajectory (all three scores), the hint account, and the dependency-chain diagnosis written out.
- Not passing is not giving up: the course may be re-taken as a new item in any later group; the status returns to active, it enters a new cycle schedule, and it uses new assessment-pool papers.
- The mistake_bank carries on without being cleared; mistake assets are inherited across the re-take.

## 11. Parameter hierarchy

These clauses are the protocol-layer defaults. If the relaxation coefficients (2.0/1.2/1.5) and pass marks (60/50) need adjusting for a particular student, that belongs to the parameter discussion of the group-forming ritual, and the change lands in `main/10_student/profile/profile.md`.

## 12. The cycle-level quiz

A quiz may be added on a major-adjustment window day: draw 3 problems from the practice pool by random seed, with the time limit per this protocol's "cycle quiz" rule; it is process monitoring only and carries no weight.

## 13. Trigger and settlement gate

### 13.1 Trigger

| Sitting | `schedule` | `progress` |
|---|---|---|
| bank build | D7 of cycles 2/5/8/11 | every `exam_keystones_per_bank_build` completed keystones |
| cycle quiz | cycles 3/6/9/12 | every `exam_keystones_per_quiz` completed keystones |
| final | calendar node plus the §7 scope gate | all trunk keystones completed |
| resits | settlement gate reads the previous verdict | same |

The fields in group `calendar.md` are the only machine trigger source. A schedule cycle counts six
actual learning dates, not calendar weeks; the same date counts once and the rest day does not count.
Without `cycle_anchor_learning_day`, report the missing anchor and do not guess. Progress-mode stalls
route to the §4.2 triage in `course_group_rules.md`; they neither reduce the exam scope nor affect marks.

### 13.2 Settlement gate (exactly one consumer)

`_exam/exam_ledger.md` is a retire-loop decay instance. Its sole consumer is the settlement gate:
it reads the prior verdict, dispatches review units and resits, then settles or archives the debt.

```text
sitting -> grading -> settlement gate
                     | pass -> settled
                     ` fail -> review 1 -> resit 1 -> review 2 -> resit 2
                                                        | pass -> settled
                                                        ` fail -> archived (not passed)
```

The number of review units is a student parameter (0/1/2, default 2). Group `review.md` may read this
ledger but cannot drive transitions. Re-entry from archived requires a new retake project, a new
cycle placement and a new assessment-pool paper; the mistake bank is not cleared.

### 13.3 Two-layer attribution

| Layer | Owner | Landing point |
|---|---|---|
| process | `exam_ledger.md` | capacity, broken cycle, missed review unit, insufficient bank |
| concept | the course `mistake_bank.md` | the ledger keeps only an `M-xxxx` pointer; the M entry cites `EX-NNNN` |

Luck, "the paper was too hard", and model randomness are not accepted causes. Concept debt keeps one
consumer in the mistake bank; the exam ledger must not create a second review loop.

### 13.4 Evidence fixed before the event

At paper assembly, first record covered nodes, difficulty distribution, time baseline, random seed,
suitability PASS/REJECT decisions, and source references. That block is immutable after the exam;
settlement is appended beneath it. The difference between the prior commitment and the actual result
is the evidence for process attribution.

## 14. Doctor checks

`runtime.exam_banks` enforces the following from `exam_bank_spec.md`:

| Check | Level |
|---|---|
| an assessment-pool problem reference appears in a lesson or exercise | **FAIL** |
| a folder under `papers/` is absent from `index.md` | WARN |
| `meta.md` lacks a required column or solution-page reference | WARN |

An empty bank returns PASS; it is a valid initial state, not a fault.
