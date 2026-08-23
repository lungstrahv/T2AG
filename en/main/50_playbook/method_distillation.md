# Distilling and superseding a way of thinking

**Protection level**: core-playbook

> Triggered when a classroom error, a run of follow-up questions, a behaviour repeated across problems, or the student's own attribution exposes a transferable path of thought. This flow turns real behavioural evidence into a method that can be invoked, trained, and verified; it never dresses up a single piece of advice or a single moment of understanding as a new habit.

---

## 1. Goal and boundary

This flow answers: how an old default path is identified, how a replacement action is generated, how it
gradually takes over through training, and how the system stores the evidence of the takeover.

This flow is not responsible for:

- Storing a specific knowledge error; a specific error still goes into the course `mistake_bank.md`.
- Making a psychological diagnosis or a personality judgement about the student; it records only
  observable behaviour and what the student stated explicitly.
- Packaging every miscalculation, slip of the pen, or teacher mistake as a "way of thinking".
- Declaring a habit formed because the student said "I understand".

The reasoning analysis in the exercise loop is this flow's observation entry point, not an automatic
command to open a file.

## 2. Inputs, outputs, and the write route

### Inputs

- The course, the current Lesson/Exercise, and the problem or Q&A position.
- The student's raw answer, follow-up question, or after-the-fact attribution.
- Observable evidence that the old path failed.
- The counterexample, the correction process, and the later performance on variants.

### Outputs

- One takeover memory of "trigger cue — old path — stop signal — minimal replacement action —
  verification evidence".
- The method takeover state `candidate → reinforced → automatic → superseded`.
- The trigger structure to invoke at the next retest, rather than the answer to the original problem.

### Route

| Content | Written to |
|---|---|
| the error scene, the student's words, and the in-class correction inside a Lesson | the current Lesson main carrier |
| the student's words and raw answer inside an Exercise | the matching Attempt; a non-submission classroom observation goes into the current `exercise.md` |
| the teacher's judgement and correction inside an Exercise | the matching Review; before a Review exists, the current `exercise.md` |
| a specific course knowledge error and its mastery state | the course's `mistake_bank.md` |
| a cross-course thinking pattern and the state of its replacement method | the current student's `reasoning_patterns.md` |
| a dispute about the flow's design, or a major adjudication process | `60_journal/` |

By default a replacement method is related through its parent `RP-XXXX`; do not invent a separate method
numbering system before one pattern really does correspond to several independent methods.

## 3. The admission threshold

A candidate method may be established only when one of the following holds:

1. The same path of thought recurs in at least two problems.
2. The student points out a stable old path, trigger feeling, or failure mechanism on their own.
3. A single error has clear cross-problem transfer value and an executable replacement action can be
   written for it.
4. An existing `reasoning_patterns.md` entry needs upgrading from a description into a training protocol.

These do not enter: an ordinary miscalculation, an isolated slip, an error made before the material was
taught, pure missing knowledge, an error caused by the teacher or a tool, and a vague evaluation that
cannot be written as a behavioural action.

## 4. The nine-step distillation

### 1. Capture the old path

Record what the student actually attended to, ignored, assumed, or executed before the answer appeared.
Keep the student's own words; a teacher inference must be labelled as a candidate.

### 2. Classify the source of failure

Distinguish missing facts, a misunderstood concept, a calculation slip, an omitted condition, and a wrong
strategic path. Only the part that can become a procedural replacement continues.

### 3. Build the old/new contrast

State where the old path diverges, what advantage the new path preserves, and what evidence shows the old
path fails in this setting.

### 4. Locate the trigger cue

Find when the old path starts automatically. The trigger cue should be recognizable, for example
"starts calculating before finishing the outer condition" or "gets the strong feeling of identity that
'it is essentially just …'".

### 5. Generate the stop signal

Specify when a formal commitment is paused — not when thinking is forbidden. For example: "while the
conclusion has not been checked for direction, quantifier or scope, it may only be marked as a
candidate."

### 6. Generate the minimal replacement action

The action must be short, executable, and checkable. Preserve the productivity of the old path where
possible, adding a minimal gate only at the point of failure.

### 7. Build the causal explanation

State how the replacement action blocks the original failure mechanism. A mnemonic with no causal
explanation easily becomes a new mechanical error.

### 8. Schedule training and hint withdrawal

Withdraw teacher support in stages: full reminder → the trigger word only → no prompting at all. A retest
changes the surface and the problem type, and where necessary the course.

### 9. Update the takeover state

Update the state on real invocation evidence, and write the next training as a concrete trigger
structure. Never promote automatically with the passage of time.

## 5. From advice to habit

The playbook stores the training protocol and the evidence; the classroom and the retest form the habit.
The standard loop is:

```text
recognize the trigger cue
→ execute the minimal replacement action
→ get immediate corrective feedback
→ invoke it again on a variant
→ invoke it unprompted after an interval
→ update the takeover state
```

### State definitions

| State | Criterion |
|---|---|
| `candidate` | there is evidence the method is worth trying, but no independent transfer performance yet |
| `reinforced` | successfully invoked at least once on a variant; a hint is permitted but its strength must be recorded |
| `automatic` | across at least a day's interval, on at least two surface-different problems, the student recognized the trigger cue and executed the replacement action before any teacher prompt, and the old path did not take over |
| `superseded` | replaced by a more general, more reliable, or cheaper method; the origin and the supersession relation are kept |

Keep "pattern state" and "method takeover state" separate: the student may have confirmed an old pattern
exists while the replacement method is still only a `candidate`.

## 6. The candidate-synthesis protection principle

Forming a candidate synthesis quickly is allowed; letting a candidate synthesis swallow the original
differences is not.

Whenever a synthesis crosses concepts, textbooks, or texts, these must be preserved:

- Definitions that cannot be aligned between authors.
- Different quantifiers, directions, or scopes behind the same term.
- Different results from different algorithms on the same data.
- A counterexample that does not fit the current synthesis hypothesis.
- A gap that cannot be explained yet.

A candidate synthesis may be promoted once verified, but the original evidence must never be overwritten
or rewritten backwards.

## 7. Worked instance: compress fast, but defer commitment

- **Trigger cue**: the immediate certainty of "it is essentially just …" or "I have the core already".
- **Advantage of the old path**: rapid reuse of a familiar structure, sharply lowering cognitive
  complexity.
- **Failure risk**: the reward for a successful compression arrives before the differences are checked,
  producing premature identification.
- **Stop signal**: the remaining differences between the new and old objects have not been listed, or the
  direction, quantifiers, and outer conditions have not been checked.
- **Minimal replacement action**: mark the conclusion as a "candidate", and write down at least one
  remaining difference or look for one failing counterexample.
- **Invocation phrase**: **compress fast, but defer commitment.**

```text
copy the old model
→ mark the candidate structure
→ record the remaining differences
→ check direction, quantifiers, and outer conditions
→ actively look for a failing counterexample
→ promote to a stable structure once it passes
```

## 8. Common pitfalls

- Recording "the student agrees with the analysis" as `automatic`.
- Suppressing the student's existing strength in order to train the new method, making the action too
  expensive.
- The teacher states the trigger cue first, then counts the student's answer as an unprompted invocation.
- Redoing only the original problem, which measures answer memory rather than method transfer.
- Substituting a psychological label for behavioural evidence.
- Copying the same passage into the lesson, the mistake bank, and the reasoning patterns, creating
  several sources of truth.
- A candidate synthesis overwrites the original differences, leaving later counter-evidence nowhere to
  live.

## 9. Maintenance rules

- This file is kept long-term at the user's explicit request and is protected as a core-playbook; it must
  never be archived, merged, or substantially rewritten automatically.
- A major modification must state its reason in `00_core/t2ag_changelog.md` and be synchronized to the
  skeleton and lite.
- A new method instance does not modify this playbook; it is written into the student's
  `reasoning_patterns.md`.
- The session close only harvests candidates and schedules retests; it must never promote falsely for the
  sake of closing a loop.
