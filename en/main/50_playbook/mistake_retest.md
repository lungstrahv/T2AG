# The start-of-class knowledge spot-check (mistake_retest)

**Protection level**: core-playbook

> Triggered at the start of every formal class. The unit of the spot-check is a "knowledge point", not
> a fixed problem; a problem is only a variant probe for the knowledge point.
> Understanding in the moment is not successful delayed retrieval, and the results are all written back
> to the course `mistake_bank.md` in the session-close ritual.

## 1. Composition of the spot-check

Each class start has at most 11 independently judged slots by default:

| Source | Count | Selection range |
|---|---:|---|
| Course-coverage sampling | 2 | 1 recent and 1 distant knowledge point from completed LearningActivities |
| Active error knowledge points | 0-8 | `active` entries whose current reinforcement cycle is due |
| Aged rumination | 0-1 | an `aged` entry; it occupies the separate 11th slot and never crowds out course coverage |

- A recent knowledge point comes from the last 1-4 classes; a distant one prefers content unconfirmed
  for at least 6 classes or longest since its last retest.
- If there are fewer than 8 active entries, check them all; with more than 8, take the ones that
  "failed last time and are awaiting repair" first, and rotate the rest on a date seed.
- `maintenance` is not permanent mastery: failing a distant spot-check opens a new reinforcement cycle
  and moves the entry back to `active`.
- With no aged entry, skip the 11th slot; never manufacture a record to fill the quota.

## 2. The knowledge-point state machine

One `M-xxxx` entry corresponds to one stable knowledge-point key; when the same knowledge point goes
wrong again, merge the evidence rather than creating a duplicate entry.

| Result | Definition | Counts as an independent correct answer |
|---|---|---|
| `✓` | completed with no answer hint, on a different surface problem | yes |
| `△` | completed after a hint, partially completed, or the evidence is insufficient to judge | no, but it consumes one attempt |
| `✗` | wrong, unable to retrieve, or the root cause is still there | no |

- A restatement right after an explanation is recorded as "understood in the moment" only and does not
  enter the formal retest count.
- A formal retest is cross-session by default and at least 3 days after the previous formal retest;
  re-answering the same original problem does not count.
- The `maintenance` condition: 3 cumulative `✓` in the current reinforcement cycle; if a `✗` has
  occurred, 2 consecutive `✓` are additionally required after the last `✗`.
- The `aged` condition: 6 attempts reached in the current reinforcement cycle without passing, or a
  3rd `✗`. The first two errors continue to be repaired; the third error only triggers the move to
  aged, with no further intensive drilling.
- The "6" here is the attempt ceiling of one intensive repair cycle, not a claim that a knowledge point
  is kept for only 6 classes; a `maintenance` entry keeps taking part in the distant spot-check, which
  prioritizes the longest-unconfirmed, for the rest of the course.
- Aged rumination is not driven by the six-attempt intensive ceiling; one review paper yields at most 1
  formal result per knowledge point, and 2 consecutive `✓` on two different study dates are required to
  move back to `maintenance`. A wrong answer resets the consecutive count to zero, the entry stays
  `aged`, and no further bombardment is added.
- The end of a course only archives the records; it never declares permanent mastery. When the course
  resumes, or related knowledge appears again, the distant spot-check still applies.

## 3. Knowledge-point probes

To avoid ten homogeneous drill problems, judgement is logically independent while presentation may be
combined into 2-4 small scenarios.

| Probe | Operation | Good for checking |
|---|---|---|
| P1 restate | give the definition, rule or mechanism in their own words | basic retrieval |
| P2 discriminate | compare near-neighbour concepts or judge a boundary | conceptual distinction |
| P3 construct | give an example, a counterexample, a test case | generative ability |
| P4 transfer | change the numbers, the setting or the form of expression | cross-problem transfer |
| P5 diagnose | find the error in a proof, a piece of code or an argument | root-cause identification |
| P6 connect | state the dependency between two knowledge points | knowledge structure |

Consecutive retests of the same knowledge point must not use the same probe and the same surface
problem. Every knowledge point must be recorded separately, even when several of them are wrapped into
one scenario.

## 4. The three safety gates for a variant

1. The model must solve it completely itself, confirming the problem has a solution and a clear
   judgement.
2. The variant problem, the basis of judgement, and the probe used are all written to disk with the
   retest record.
3. A condition perturbation or a cross-context transfer is used only in the everyday spot-check the
   first time; only after it proves uncontroversial may it enter an informal quiz, and a formal exam
   still goes through `exam_protocol.md`.

## 5. The Praxis course boundary

- Factual and technical knowledge in a `course_type: praxis` course may enter this state machine (it is
  bound to the completion-semantics axis, not to `default_driver`; see `00_core/domain_model.md` §2.0).
- Judgement, discipline, and character formation cannot be certified by three correct answers; they need
  evidence from real action, a record made beforehand, and long-term review.
- IV1001's behavioural evidence goes into
  `10_student/engagements/EG-0001_TradingDiscipline/trade_journal.md` and must never be replaced by a
  knowledge quiz.

## 6. The aged review paper and the optional calendar

The student may always ask for "a review paper generated from this course's aged knowledge points". In
addition, a calendar mode may be configured in `main/10_student/profile/profile.md`:

| Mode | Behaviour |
|---|---|
| `off` | never suggests or triggers on its own; responds to a student request only |
| `suggest` | suggests when the preferred window arrives and generates after the student confirms; the default |
| `auto` | triggers directly at the preferred window when the student has authorized it explicitly |

- The calendar counts "actual study dates", not calendar days; one calendar day counts as at most 1
  study date, and a rest day does not count. The calendar span of 3-1-3 is 7 days, but one study cycle
  is 6 study dates.
- The preferred trigger window is not a mechanical due date; it is just after finishing a chapter,
  module, or knowledge cluster tightly related to the aged knowledge point. Closing the relation takes
  precedence over the calendar number.
- If a full study cycle passes with no suitable point of related closure, `suggest/auto` sends a single
  review reminder; never generate a paper detached from the course context just to keep up with the
  calendar.
- The source may only be this course's `aged` knowledge points, generating a new variant per knowledge
  point rather than reproducing the original problem; each problem keeps the knowledge-point key, the
  probe, the basis of judgement, and the write-back target.
- The review paper is saved to
  `book/course_materials/exercises/aged_review_YYYY-MM-DD.md` in the course, and is linked back from the
  current Lesson or Exercise main carrier; never pre-create a Lesson for an Exercise-first course.
- One paper provides at most 1 formal success evidence per knowledge point; 2 consecutive correct
  answers on two different study dates are required to move back to `maintenance`. Piling several
  same-kind problems into one paper cannot shortcut the pass.

### 6.1 The candidate window

- A "course study segment" is counted by the named parts, stages, modules or knowledge clusters of the
  teaching plan, not mechanically by the number of lesson files. One segment may cover several lessons
  or half a lesson; the count follows the structure of the plan.
- By default a candidate window arrives after roughly every 3 course study segments. A window only
  permits a suggestion or a trigger and does not mean a paper must be produced; producing one still
  waits for a tightly related knowledge cluster to close, and for `aged` entries to exist to draw from.
- The study cycle of 6 actual study dates carries only the forgetting-prevention reminder; the course
  study-segment count sets the content rhythm. Neither may substitute for the other.

### 6.2 Working back from problem count to time limit

- Positioning: an aged review paper is a "basic-concept error check", not a second comprehensive exam.
  The standard time limit is capped at 50 minutes, and there is no requirement to use it all.
- The planning accuracy rate is 80% by default, used only to leave room for recall, checking and a
  slight stall; it is not a pass threshold for a knowledge point, and state transitions are still judged
  per knowledge point on the formal result.
- Before assembling the paper, estimate a "time to answer it correctly without difficulty" `t_i` for
  each problem; with no historical data, estimate 3 minutes for a basic-concept problem and 6 minutes
  for a connecting problem.
- The paper's time limit is `T = ceil_5(Σt_i / 0.80)`, where `ceil_5` means rounding up to 5 minutes. A
  50-minute paper holds at most about 40 minutes of smooth answering; if the computed result exceeds 50
  minutes, split it into several papers and recompute each, rather than compressing the answering time.
- About 80% of problems check a single knowledge point, an adjacent definition, or a direct boundary;
  about 20% connect 2-3 tightly related knowledge points already studied, with no long-distance
  transfer. Once the total reaches 5 problems, arrange roughly 1 connecting problem per 5; below 5
  problems, do not force one in just to hit the ratio.
- Every knowledge point a connecting problem covers is still judged separately, and each yields at most
  1 formal result within one paper.
- Sampling priority, the formal hint rule, and answer isolation await a later adjudication; that must
  not change the time limit, problem-type structure, and evidence rules already settled in this section.

## 7. Write-back and rhythm

- Results are held provisionally first, and the session close recomputes the current cycle summary and
  the states per `session_close.md`.
- When a course-coverage problem is answered wrong, create or merge the corresponding knowledge point as
  `active`; a correct answer is written only into the spot-check record of this session's current
  activity main carrier.
- The spot-check may be grouped, delivered orally, and made interactive, but the correct/incorrect
  standard must never be bent for an emotional state.
- If 11 slots would clearly squeeze the main class, the student may ask to complete it in two parts;
  unfinished slots are kept and results are never faked.

## 8. Related files

- `[course]/mistake_bank.md`
- `main/50_playbook/lesson_recover.md`
- `main/50_playbook/session_close.md`
- `main/20_teacher/overlay.md`
- `main/70_tools/t2ag_doctor.py`
