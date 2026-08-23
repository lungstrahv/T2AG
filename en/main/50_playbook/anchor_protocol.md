# The long-discussion Anchor Protocol

**Protection level**: core-playbook

> An in-session discipline for containing error cascades in a long discussion; general to any model and any course.
> Trigger: the discussion is expected to, or does, exceed ~10 turns, or the student's run of follow-up questions enters territory with no external oracle.
> Origin of the mechanism: the 2026-08-18 teaching-reliability discussion (50-turn compounding + error autocorrelation + the social truncation of human teaching).

enforcement: prose_accepted (reason: in-session behaviour has no machine scan; failure visibility = the transcript shows no anchor list beyond the agreed turn distance, caught by the review and the end-of-course assessment; and a long absence of anchors is a signal the student can perceive directly)

## 1. The problem to be solved

Teaching has no external oracle: by definition the student cannot judge the error, the model is
conditioned on its own previous error, and one mistake pulls a chain behind it. No model's single-turn
accuracy survives 50 turns of compounding.

Human teaching never solved this; it merely avoided it. A teacher gets annoyed and leaves, the student
does not press further, and 50 turns of depth was never socially permitted to happen. "The teacher gets
fed up and walks out" is objectively human teaching's stop-loss line — crude, but errors do not persist
silently. A model does not get annoyed and does not leave; the stop-loss line disappears, and for the
first time a cascade can propagate unobstructed.

This protocol does not lower the error rate; it **truncates the propagation distance**: it lowers the
reliability requirement from "no error at all, throughout" to
"no error between two anchors" — a standard existing models can meet.

## 2. The protocol

1. **Drop an anchor**: roughly every 8–12 turns, or at a conceptual transition, the model emits a "list
   of claims established so far" — numbered, one sentence each, listing only what this segment of the
   discussion newly established, never textbook common knowledge.
2. **The student passes the anchor**: confirm or correct each item. A confirmed anchor = a checkpoint;
   an item in doubt is marked `?` on the spot, and **building further on top of a `?` is not allowed**.
3. **The rollback rule**: when an error is found later, roll back to the last clean anchor and walk it
   again; do not do archaeology sentence by sentence and do not tear down the whole session.
4. **An anchor is raw material**: if the discussion is later judged a load-bearing node, the anchor list
   is the first draft of the keystone's numbered chain
   (the drafting step in `keystone_records.md` §6 starts straight from the anchor list).

## 3. Cost and boundary (a decision, not an oversight)

- Each anchor costs 2–3 turns. One anchor per 10 turns is roughly 20–30% overhead, and what it buys is
  cascade truncation — **mandatory for a load-bearing discussion**,
  not required for ordinary Q&A.
- Responsibility for dropping anchors lies with the course script / teaching prompt side; drift in
  execution is noticed by the student — an anchor failing to appear for too long is itself a perceptible
  signal, which is exactly what makes this stronger than a prose clause saying "please be careful, model".
- No doctor check and no new gate; the division of labour with the keystone form: an anchor governs
  **in-session** propagation distance, and a keystone governs **cross-session** re-reviewability.
