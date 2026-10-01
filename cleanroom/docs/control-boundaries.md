# How constraints are enforced

The learner gives the goal and decisions. The teacher interprets content and
intent. The runtime checks deterministic conditions and preserves the resulting
facts. The host controls actual file, process, network and account permissions.
These responsibilities are separate; none establishes all of the others.

## Three complementary mechanisms

| Mechanism | Use it for | Evidence and limit |
|---|---|---|
| Language rule | Faithful explanations, appropriate depth, source-role interpretation, honest uncertainty, interpreting the learner's actual request | Preserve source and reasoning references; inspect real responses. A written instruction is not machine enforcement. |
| Decision gate | Accepting a plan, advancing content, granting a hint, closing work, resolving an actual conflict, changing scope | Define the pending decision, who may make it, the exact object/version it affects and what invalidates it. Gates may need semantic judgment plus a program. |
| Program check | Stable identities, current references, scope, single-use permissions, duplicate requests, legal transitions, counts, time arithmetic, atomic saves and check selection | Execute on relevant changes; test positive and negative cases. Valid structured input does not prove its real-world assertions. |

“Gate” describes when a transition is allowed. “Program” describes how a
decidable part is enforced. A comprehension gate therefore combines an actual
answer, a teacher's semantic judgment, and program checks that the answer,
criterion and current block belong together. A correct schema is not proof that
the answer is mathematically correct.

## Assign conditions to their actual owners

| Condition | Semantic decision | Program responsibility |
|---|---|---|
| The learner accepted this plan | Interpret the actual learner message or an authenticated host choice | Bind the decision to the complete displayed plan, sources, teacher and current version; apply its results atomically. |
| The next block may start | Establish the learner's current permission for this content | Check current session, block, body version and unconsumed ticket; reject stale or reused permission. |
| Source pages were actually read | The host supplies observable delivery; the agent consumes the evidence | Check source/page identity, complete selected coverage, current version and appropriate evidence form. A caller-provided delivery label alone is not host proof. |
| The explanation respects the textbook | Interpret wording, role and depth against the actual source | Keep original titles/order and teacher arrangements distinct; retain excerpts and provenance. String containment cannot prove fidelity. |
| An answer or retest counts as independent | Assess actual assistance and answer evidence; keep unknowns unknown | Link the actual attempt and frozen criterion, reject reused/superseded evidence, carry known help and enforce required dates/counts. |
| Work may close | Interpret the decision after the complete review is presented | Bind the outcome and body version; recheck remaining questions and incomplete scope under the same transaction. |
| Progress was saved | No semantic inference from the teacher's prose | Require a durable receipt; use the same request ID after an uncertain response. Rebuild projections from committed facts. |
| A rule has executable enforcement | Inspect its actual consumer and a relevant negative scenario | Resolve the executor, bind validator version and expected failure, and invalidate stale proof. An unrelated earlier error is not proof of this gate. |
| An operation may access the computer or an external account | User authorization and host policy | Host permissions enforce access. A T2AG actor role does not grant OS or account privileges. |

## Avoid unnecessary waiting

Do not request the same decision again for an internal save, projection or check.
Interpret one clear user instruction once and bind all its authorized effects.
Different decisions remain distinct: confirming an answer does not by itself
authorize a new block, and saving does not close an activity. Expose uncertainty
only when it changes what can safely proceed.

Simple answer feedback need not wait for an unrelated audit. The runtime checks
the relevant transition before committing; the agent can give supported
teaching feedback promptly and report persistence separately. Affected checks
follow their input changes. Full checks belong at migration, integrity
investigation and release qualification.

## Current implementation boundary

The JSON API accepts attributed role, source and text fields. The host has not
provided cryptographic message attestation to this runtime. The selected action
records the formal choice; the agent interprets the actual natural-language
instruction. Limited checks reject demonstrated clear contradictions. They
are not a general intent classifier, and adding another caller-supplied
acceptance field would not establish identity or intent. Preserve the original
message and the object it authorizes without making learners repeat passwords.

Focus enforcement on structural errors with recurring consequences. Do not
turn an unlimited list of hypothetical edge cases into extra learner steps.
Readable behavior and straightforward correction are preferable for small,
reversible mistakes.

The runtime rejects covered invalid operations through its public command/API
path. An equally privileged agent that can rewrite files and code can bypass
that path; the current implementation does not claim process or permission
isolation against such an actor. Stronger protection requires a separately
controlled writer or host policy. Hashes, traces and non-author review help
detect mistakes, but do not substitute for that isolation.

New governance and compatibility modules remain candidates until their actual
consumers, positive/negative cases and non-author reviews are integrated.
Documents describe the required division of responsibility, not a claim that
every constraint is already implemented or that all agent behavior is proven.
