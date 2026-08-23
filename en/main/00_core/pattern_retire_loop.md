# The compounding-loop pattern (pattern_retire_loop.md)

> T2AG's first formal design pattern. The umbrella name is **the compounding loop**; the filename keeps the historical
> name retire_loop — "retire" is now the proper name of the **decay subtype** only, and the path stays as a
> compatibility exception under `naming_conventions.md` §4.
> **The naming law: the pattern is defined once here, and an instance keeps its domain name** (trade_journal is not renamed mistake_bank_trading).
> When a new domain needs this capability: pick the subtype → instantiate per the parameter table → name it in domain terms → declare it in the header. **Never** copy-paste another instance and edit it.

> **Note on the declaration literals**: the `【模式】复利回路·…` markers and the parameter key names below are
> **machine-read tokens**, not prose. They are written by `70_tools/migrate_020.py` and read by the exam-ledger
> check, so they stay in their canonical zh-CN form in every edition, exactly as `T2AG_SESSION_CLOSE` does.
> Translating them is a four-part change (registry + `migrate_020.py` + the reading checks + this file) and must be
> done in one batch or not at all — see the R3 note in the P-0077 work order.

## The umbrella definition

- **Loop**: a task process executed repeatedly; its stages may be entirely human, entirely system, or a mix.
- **Compounding**: the new signal produced each round (the **flow**) settles into some **stock**; the stock feeds the next
  round's input, so task-completion efficiency rises monotonically. **What compounds is the stock, not one round's output.**

## The two subtypes

|  | Error-correcting decay (a balancing loop) | Accumulating reinforcement (a calibrating loop) |
|---|---|---|
| Core dynamic | the error stock tends to zero, processing frequency falls, and it **exits** | the stock's precision rises, and it **never exits** |
| Metaphor | paying off a debt (an error is a debt; clear it and close the account) | holding a compounding asset (understanding is an asset; you add, never liquidate) |
| Why there is no exit | — the debt is cleared, so it stops | precision has no ceiling + the object is non-stationary (the student/the market keeps changing) |
| The number-one failure mode | after exiting there is no re-entry, and an old error recurs with nobody to catch it | accumulating without calibrating, so the stock goes on being confidently wrong |

One file may carry several roles (a loop instance or a loop component); the registration tables list them row by row. Component definitions are in the next section.

## A loop component: the flow ledger (not a third subtype)

Not every file with a state machine is a loop. **The admission criterion: who holds the restoring force.**

- The file carries its own driving stage that pushes the stock toward its target (a spot-check, a monthly review, a repair obligation) → it may be registered as a **loop instance**;
- The file only registers flow and maintains entry status, while both the driver and the stock live outside it → it is some loop's **flow ledger**, registered as a component.

A ledger's entry state machine (to-be-resolved / answered and so on) is **ledger hygiene**: it guarantees the flow is not lost, can be reviewed, and can be settled.
"Closing" is a **settlement**, not the elimination of an error; a ledger has no compounding of its own, and all its value accrues to the loop it belongs to.
A file whose recording, consumption, exit and re-entry are all driven by external events is registered as a ledger without exception, and must never be forced into the decay register just to fill six elements.

## Decay-type parameters (six elements)

| Element | Meaning | Constraint |
|---|---|---|
| ① what is recorded | what goes in | a single domain; out-of-domain content is redirected by the boundary rule |
| ② when it is written | evidence-before / attribution-after | the before type has more "prediction" columns (thesis/stop-loss), the after type more "root cause" columns |
| ③ attribution layer | which layer the root cause must land on | concept layer / rule layer / process layer — external causes (luck, manipulation, the model glitching) are forbidden |
| ④ consumer | who reads it when, and what they change | exactly one (the boundary rule adjudicates ambiguity) |
| ⑤ exit condition | when intensive processing ends | entering maintenance / aged / archived |
| ⑥ re-entry condition | what event brings it back to intensive processing after an exit | when there really is no re-entry, write "none" — **never leave it blank** |

## Accumulation-type parameters (five elements)

| Element | Meaning | Constraint |
|---|---|---|
| ① per-round output | the new signal each task run produces (the flow) | a nameable entry/event, not a feeling |
| ② the stock it adds to | which file/rule the signal settles into, and who reads it next round | one stock file only; the reading stage is written out |
| ③ stage composition | what the human does, what the system does | the division of labour is written item by item |
| ④ settling and compression | when a raw signal is distilled into the stock, and how the raw entry retires afterwards | guards against append-only: the stock is bounded, and retirement leaves a pointer |
| ⑤ calibration signal | what observable event proves the stock is getting **more accurate** rather than merely bigger | when a prediction fails, write a correction entry; **silent overwriting is forbidden** |

> The "gain claim" (why this loop deserves to exist) goes in the one-sentence reason on the registration row, with no parameter slot — anything unfalsifiable does not enter the parameter table.
> An accumulating loop needs ⑤ **more** than a decaying one: it has no exit mechanism to stop the loss, and without calibration it becomes prior self-reinforcement — a teacher grading their own understanding, the same disease as "recognizing the public leaderboard = recognizing AI approval".

## The register of existing instances

### Decay type

| Instance | Level | Domain | ② timing | ③ attribution layer | ④ consumer | ⑤ exit | ⑥ re-entry |
|---|---|---|---|---|---|---|---|
| each course's mistake_bank | entry | knowledge point | after | concept layer | the start-of-class spot-check → change the understanding | three independent correct answers → maintenance; six attempts without passing → aged | drawn in an aged paper and answered wrong → back to reinforcement |
| 10_student/engagements/EG-0001_TradingDiscipline/trade_journal | entry | trading | **before** | decision-rule layer | the monthly review → change the system | `clean_months >= 2` → retired | the same tag recurs → `clean_months = 0`, `reopen_count += 1` |

> What the two decay instances have in common: **the restoring force is inside the file** (the start-of-class spot-check / the monthly review) — that is the admission threshold for the decay type.

### Accumulation type

| Instance | Level | ① per-round output | ② the stock it adds to | ③ stage composition | ④ settling and compression | ⑤ calibration signal | One-sentence reason |
|---|---|---|---|---|---|---|---|
| question_bank, collection level | collection | new questions + question-direction patterns (the flow ledger = each course's `question_bank.md`) | `students/Sxxx/reasoning_patterns.md` (the teacher reads the profile at the next class start) | human = asking, expressing confusion; system = recording, recognizing patterns across courses, writing the profile | silent tidying at class start + distillation at a checkpoint milestone; a Q entry stays closed and keeps a pointer rather than being deleted | the profile's predicted sticking point vs the actual one; when it fails, write a correction entry | teaching emphasis gets more accurate and the student stays stuck for less time |
| Cocoon taste.md | collection | daily 👍/👎 and misjudgement patterns | the taste clauses in `taste.md` (the next round's filter_llm reads them to score) | human = marking feedback; system = feedback.py spots a run of misjudgements and appends a correction | only a run of misjudgements that forms a pattern enters a clause; clause governance belongs to cocoon (self-governing program, **registered only**) | the smuggling-slot reversal rate: a randomly low-scored entry getting a 👍 is evidence of a miss | recommendations get steadily more accurate without losing freshness |

> taste.md was re-registered from decay to accumulation. The reason on record: in the old table its exit column could only say "self-governing program, registered only" —
> that empty value was itself the evidence that one shape could not hold it (one of the direct triggers of this refactor).

### Components (flow ledgers)

| Ledger | Owning loop | Settlement condition | Re-entry |
|---|---|---|---|
| each course's question_bank (entry level) | question_bank collection level → the teacher profile | answered/closed | the student asks again → becomes "needs review" |
| `00_core/t2ag_problemlog` | problemlog → `50_playbook/` (the stock = the corresponding playbook) | `playbook_status=extracted`; when distillation is definitely unnecessary, `not_applicable` | a same-kind problem recurs → the original entry's `reopen_count += 1` and it reopens |

> Why the question_bank entry level is not in the decay register: its recording, consumption, settlement and re-entry are all driven by external events
> (the student asks / teaching covers it / the student asks again), and the file holds no restoring force. Forcing it into the decay register with a "passively consumed" annotation
> would make that annotation the next "self-governing program, registered only". A knowledge error behind a question is redirected to mistake_bank by the boundary rule,
> where the spot-check mechanism takes responsibility — a decay function does not open two consumers.

## Files this pattern does not apply to

- `t2ag_changelog.md` is a pure append-only change history: its job is to preserve version facts that already happened, and it does not aim at exit, re-entry, or driving an error to zero.
- The historical narratives in `60_journal/` are review evidence: an index and archival status may be built for them, but history must never be rewritten, nor an exit condition manufactured, in order to apply this pattern.
- Any other pure append-only audit record that only preserves facts is likewise not registered. A state machine, or index hygiene, is not by itself a compounding loop.

## Header declaration templates for an instance

Decay type (pasted at the top of the **record file**):

```markdown
> 【模式】复利回路·衰减（00_core/pattern_retire_loop.md）实例
> 【参数】域=X｜时机=X｜归因层=X｜消费方=X｜退出=X｜再入=X
> 【边界】越界内容转投 X（边界规则裁决）
```

Accumulation type (pasted at the top of the **stock file** — a loop may span files, and the declaration follows the stock):

```markdown
> 【模式】复利回路·积累（00_core/pattern_retire_loop.md）实例
> 【参数】产出=X｜存量=本文件｜环节=X｜沉淀=X｜校准=X
> 【边界】越界内容转投 X
```

Component (pasted at the top of the **ledger file**):

```markdown
> 【模式】复利回路·部件（00_core/pattern_retire_loop.md）｜角色=流量台账
> 【服务】所属回路=X（存量=Y）｜结算=X｜再入=X
> 【边界】越界内容转投 X
```

Where a cross-repository instance (such as taste.md in the cocoon repo) cannot carry a declaration, the register marks it "registered only".

## Additional doctor checks

1. A file containing "【模式】复利回路": the marker must be `·衰减`, `·积累` or `·部件`; the parameters are validated by **key name** per category
   (decay: the six keys 域/时机/归因层/消费方/退出/再入; accumulation: the five keys 产出/存量/环节/沉淀/校准;
   component: 角色 + 所属回路/结算/再入). A missing key is a FAIL.
2. A registered instance with no declaration → WARN (a "registered only" row is exempt).
3. ~~The compatibility window~~: **closed on 2026-07-24** (batch I / M2-tail). No subtype marker → **FAIL** (no longer WARN). An old five-parameter block still missing keys such as 再入 is still a FAIL under the six-parameter decay validation.

## Reserved for evolution

- `method_distillation` (cross-course method distillation) is in shape an **accumulating second-order loop** riding on several mistake_banks;
  it is registered once the method cards of ≥2 courses start citing each other, and until then it stays an observation entry in evolution.
- When a future domain (writing practice, a fitness course …) needs a compounding loop: pick the subtype + add a row to the register + instantiate per the template.
- If one subtype ever exceeds 6 instances with highly similar parameters, consider abstracting a unified format + scripted re-testing — until then,
  the maintenance cost of hand-written instances is lower than that of a general framework (do not engineer ahead of need; this is T2AG's consistent philosophy).
