# The Keystone record form

**Protection level**: core-playbook

> Triggered when a discussion becomes the foundation of later study — "without it, nothing after it can be learned".
> This form settles the reasoning chain of a load-bearing discussion into a re-reviewable archive; it does not verify whether an argument is correct (the bare mathematical zone has no instrument),
> it only guarantees that the reasoning chain **can be re-attacked step by step by a future strong model** and that the persuasion path does not leak.
> Origin of the mechanism: the 2026-08-18 model-selection discussion (the MATH1607H countable-set case);
> safety basis: the 2026-08-18 addendum to seed ④ *The Archive Is a Weapon* (protection asymmetry).

enforcement: prose_accepted (reason: whether an argument is correct has no machine judgement; failure visibility = a keystone file whose "review status" stays "unreviewed" is a visible debt, caught by the ledger morning brief and the end-of-course review)

## 1. Definition and the admission threshold

A keystone: a discussion in which the student's original reasoning was adjudicated by the model and on
which later material rests.
There is exactly one criterion: **without it, nothing after it can be learned**.

- At most 3 per course. Beyond that, mark it as inflation and go back to re-review which one is not
  really load-bearing.
- An ordinary difficulty, a brilliant discussion, or a standard proof **is not admitted** — those go
  through the existing lessons / mistake_bank routes.

## 2. Location and naming

```text
40_course/<COURSE_ID>/keystones/
  _index.md          # one line per node: ID | the claim in one sentence | review status
  K-01_<slug>.md
```

**No cross-course master library and no entry in the global index** — pointer density is deliberately
suppressed (seed ④: what needs governing is pointer density; deleting records does not lower the risk,
lowering the index does).

## 3. The file skeleton (four items; missing any one leaves it incomplete)

1. **The claim**: what this node establishes, in one paragraph.
2. **The numbered reasoning chain**: step by step, "claim + reason", never narrative prose. The purpose:
   a future model can point at step N and say "there is a hole here", instead of saying "broadly fine"
   to a lump of prose.
3. **The load-bearing list**: which later material rests on it (an in-course pointer is enough; no
   external links).
4. **The review status**: `unreviewed` | `re-attacked (model / date / conclusion)` | `hole found
   (numbered step + description)`.
   Whether a hole is escalated into a problem-log entry is the student's adjudication; this form does
   not wire it up automatically.

## 4. The two-layer split (a safety discipline, hard constraint)

- **The logic-chain layer** (the four items above): a public argument with no personal information; it
  enters the repo and may be fed to any model for re-review.
- **The persuasion-path layer** (where I was stuck, which step loosened my intuition, what form of
  argument works on me):
  **it does not enter the repo and does not enter any model's context**; it belongs to the gun-cabinet
  layer (the custody threat model, 2026-08-14).
  A repo file may carry at most one line, `gun-cabinet item: yes/no`, and never the content.

Reason: a reasoning chain is a learning carrier and an attack surface at the same time. A persuasion
path is a map of "how this person can be changed" — what is most worth recording pedagogically is
exactly what is sharpest for manipulation (the seed ④ addendum: leaking a conclusion exposes what you
believe; leaking the reasoning chain exposes how you can be changed). Re-attacking step N does not
require knowing whether step N was the student's soft spot, so the logic-chain layer standing alone is
enough to support a re-review.

## 5. Generation and re-review discipline

- **The model drafts and the student confirms step by step** that "this really was my path at the time".
  The confirmation step may never be skipped: a model writing it alone slides easily into the textbook
  standard proof, which loses precisely the load-bearing part.
- The criterion for choosing a model for a load-bearing discussion is **adjudicative force × how far it
  unfolds a reasoning chain** (willing to be concrete step by step, low metaphor density), not simply
  the strongest. A model that compresses thought into abstract metaphor shifts the unfolding cost onto
  the student, and in an unfamiliar field the student is exactly the party who can least afford that
  bill (measured 2026-08-18: the countable-set discussion used GPT-5.6 Sol xhigh rather than Opus,
  because the latter's compressed output raised the communication cost). A load-bearing discussion has
  almost no time ceiling, and the strong model carries the bulk of the cost — "it is rare, so it is
  cheap" does not hold.
- **The convergence criterion (the stop-loss line when the time budget has no ceiling)**: once the
  numbered reasoning chain can be written down and each step is confirmed by the student, the
  discussion has converged; talking on while the chain no longer grows is going in circles.
- A re-review is **an adversarial step-by-step re-attack** on the numbered chain in a different session,
  not a restatement of the conclusion. A consensus reached inside one discussion may have been
  collusive; the second pass changes stance and hunts specifically for "the step most likely to have
  been let slide". A **different model family** is recommended (whoever was used for the discussion,
  switch vendor for the re-attack): the blind spots are uncorrelated, and a compression habit is
  harmless in attack mode — pointing at step N does not require unfolding the whole chain.

## 6. The backfill procedure (extracting a chain from a historical discussion)

Applies when the load-bearing discussion happened in the past and the original record is in a
conversation log (the first case, K-01).

1. **Gather**: export the original discussion record and cut away the parts unrelated to the node; the
   whole thing is not required.
2. **Draft**: feed the record into any session, with the instruction "extract the reasoning path the
   student actually walked, write it as numbered steps, each with a claim and a reason; in the order in
   which they were persuaded at the time, not as a textbook standard proof". Drafting is tidying work
   and the model need not be strong; it will still slide toward the textbook, which the next step cures.
3. **Confirm item by item**: for each step, the student asks "is this really how I accepted it at the
   time", and if not, edits until it is.
   **This step cannot be delegated.** Persuasion-path content surfacing along the way (sticking points,
   loosening) goes into the gun cabinet per §4, not into the file; the file records only
   `gun-cabinet item: yes/no`.
4. **Land it**: with all four skeleton items present → `K-NN_<slug>.md`, with a matching line in
   `_index.md`, and a review status of `unreviewed`. The re-review happens on another day, in another
   session, across model families (§5), never on the same day as the backfill.

## 7. Boundaries (a decision, not an oversight)

- No doctor check and no new gate: the bare mathematical zone has no instrument, and a false guarantee
  is more toxic than no guarantee (the P-0067 family).
- Does not change the course.md schema and does not touch the existing scan gates.
- This form governs only the shape of the record, not how a load-bearing discussion is conducted.
