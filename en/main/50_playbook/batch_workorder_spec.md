# Work order and construction report specification (batch_workorder_spec.md)

> **Function**: the single specification for writing, executing, reporting on and re-reviewing a structural batch's work order. Any batch involving file moves, rule changes, or container additions/removals is ordered and delivered under this specification.
> **Protection level**: playbook (changes go through a batch).
> **Origin**: the re-review lessons of batches C / D / E2 (a silently diverging FP directory name, an unnamed WARN, an undeclared scope trim, a conflicting commit assumption, incomplete sampling of the three-release sync). On first release this was recorded in evolution as an EV entry, "batch scheduling preference promoted to a rule", with the pointer backfilled here.
> **Default execution mode**: `independent_batch`. `version_campaign` is enabled only once the user has approved a frozen, enumerated, expiring authorization envelope.

---

## 1. Execution mode, risk tier and batch class

Every work order must declare both `execution_mode` and `risk_tier`. The batch class describes
the shape of the file operations; the risk tier decides checkpoint and re-review strength. They
never substitute for each other.

### 1.1 Execution mode

| `execution_mode` | Applies to | Authorization rule |
|---|---|---|
| `independent_batch` | the default; a single batch, or work whose boundary is not yet frozen | each batch is authorized separately, per the actual operations |
| `version_campaign` | several RT1/RT2 units within one version, already frozen, enumerable, with a provable impact closure | after the user approves one complete authorization envelope, execution continues per that envelope; this is not unlimited standing authorization |

### 1.2 Risk tier

| `risk_tier` | Typical scope | Minimum checkpoint |
|---|---|---|
| `RT0` | read-only checks, hashes, tests, reports | evidence checkpoint |
| `RT1` | local, reversible, does not touch an active authority/schema/real instance | targeted verification + evidence checkpoint |
| `RT2` | Core/Playbook/Tool/Schema/Registry, cross-release sync, migration dry-run, candidate generation | targeted tests + runtime doctor; a release doctor is added only for cross-release sync or a candidate |
| `RT3` | real or protected data migration apply, terminal lifecycle, strict student confirmation, cross-boundary external writes, destructive operations, push/release | separately and explicitly authorized once the body and the exact objects are visible; a campaign envelope must never pre-authorize an unknown fact |

#### 1.2.1 CacheEviction (derived cache eviction, not an RT3 deletion of a real asset)

> **Source**: EV-0012 (`decided`). It applies to derived caches such as textbook page images that are **deterministically rebuildable from an authoritative source**, and must never be read as permission to delete arbitrary files.

**Definition**: `CacheEviction` is the deletion, or overwrite-to-make-room, of a derived file inside a course's agreed cache root (by default `40_course/<ID>/book/.cache/**`) that has been proven rebuildable.

**It does not constitute an RT3 "destructive operation / deletion of a real asset"** if and only if **all** of the following hold:

1. The path lies inside that course's registered cache root (by default `.cache`; it must never touch `source_assets`, the PDF, Lesson body text, the ledger or progress).
2. The full cache key resolves, and the source `SourceDocument` PDF **exists**, its SHA matches, and `render_profile` agrees with the rebuild parameters (proof of rebuildability).
3. The target is **not** in the current protected set P0 (the page-image identity of the current `LessonScope`; P0 may live in the cache or in session_temp).
4. The deletion is triggered by the quota algorithm, an explicit `cache_gc --apply` (not a dry run), or an equivalent tool, and leaves an auditable reason (trigger type, key, heat_at).
5. It does not delete verified text, raw OCR, the PDF, learning evidence, or a Snapshot record. The `working_pages` path is retired; historical copies are in each course's `archive/`.

**Still RT3** (requires an exact list plus confirmation in the current round):

- The `working_pages` path is retired (0.2.2 batch S3) and its historical copies are archived; it must not be rebuilt or reused.
- The PDF, page-asset body text, or the only visible copy when it is unrebuildable or the source is missing.
- Widening the cache root, bulk deletion across courses, or reading CacheEviction as a general `rm`.

**When the conditions above are not met**, deleting a file on disk defaults to being handled as an RT3 destructive operation. A campaign envelope **must not** pre-authorize any path outside a known CacheEviction list.

### 1.3 Batch class (must be labelled when the order is written)

| Class | Definition | Risk | Preconditions |
|---|---|---|---|
| **Audit batch** | read-only: grep / hash comparison / doctor / difference report. **Changes no byte** | none | none. May run at any time; **every modifying batch must be followed by an audit batch** (or fold an equivalent audit into that batch's verification section) |
| **Append batch** | only adds files, or appends text to existing files; changes, moves and deletes nothing that already exists | low | the previous unit completed the evidence/recovery checkpoint its risk tier requires |
| **Modify batch** | moves, rewrites or deletes existing content or structure | high | the previous unit completed the checkpoint its risk tier requires, and the most recent applicable audit passed (or an equivalent audit is embedded in this unit's step 0); every human gate is listed explicitly |

A mixed batch is **split by preference**; where it genuinely cannot be split, the whole batch is managed as a modify batch. The executor may trim the scope (running only one class), but must declare it in the report's "scope deviation" field — **the reason for a trim is almost always good; silence is the problem**.

### 1.4 The version campaign authorization envelope

`version_campaign` takes effect only once the user-approved envelope has frozen at least these fields:

```text
campaign_id / target_version / baseline
included_scope / deferred_scope
repositories / file_scope / allowed_operations
risk_tier / Git checkpoint plan
reserved_RT3_gates
stop_conditions / invalidation_conditions
rule_migration (required for semantic removal/merge/relocation/retirement of normative rules; otherwise not_applicable + reason)
```

An envelope covers only the repositories, paths, operations and limited local checkpoints it
lists. On a scope expansion, a baseline change, a risk escalation, an unknown FAIL/WARN, a
cross-repository boundary change, or an unprovable impact closure, the continuous authorization
lapses immediately and work stops. An unlisted path, an unknown repository or an RT3 operation
must never be presumed authorized on the grounds of being "the same version".

Whenever current normative text in `main/t2ag.md`, `AGENTS.md`, a core/meta playbook or another
hard-boundary governance document is deleted, merged, generalized, relocated or retired, or the
owner/trigger/authorization/result of a named hard boundary changes, the envelope or the work
order must carry a `rule_migration` table (see §3 item 11). Pure additions, formatting, and
meaning-preserving clarifications may register `rule_migration: not_applicable` with a reason;
a whole-file rewrite still requires freezing the complete migration table first.

### 1.4.1 Version-bump criteria: when a new version number is warranted

The envelope requires freezing `target_version`, but until now no clause said **what makes a new
number warranted**. Measured evidence: between the 0.2.3 declaration on 2026-08-06 and
2026-08-18, all 14 changelog entries were marked "no version bump" — the criterion rested
entirely on human judgement, with nothing written down and no backstop. This section supplies it.

#### The hard precondition (a question of fact)

**When the previous version's `implementation_status` is not `complete`, a new version number must not be started.**

enforcement: check=runtime.version_bump_precondition

The reason is not fastidiousness: once the version number moves forward, nobody comes back to
close out the old one, and the history permanently keeps a version that is `partial` and was
never reviewed. This shares a root with `handoff_management.md` §10.1 "preconditions for
delisting" — formal closure arriving before semantic closure, so open items that were never
migrated out go offline with their carrier and nobody takes them over.

Closing out is defined by exactly those three fields in the version ledger:
`implementation_status: complete`, `candidate_review: passed`, `release_qualification`. A
missing predecessor record, a record that is not `complete`, or letting a neighbouring version's
record answer on its behalf, are all FAIL. A predecessor whose `candidate_review` has not passed
reports WARN — it may still be the runtime version, but it must not be cited as a basis for
release qualification. The version ledger is the **single source of truth** for those three
fields; constitution §7 points, it does not carry (CR-1=A 2026-08-23, P-0086: two coexisting
carriers once made the check report "no record" for a version whose status was recorded).
If the version has an external release surface, closeout also writes a `release_candidate`
freeze-binding row (one commit per edition, each exactly once — enforced by
CAND-BIND-004..006). Ownership splits three ways (adjudicated 2026-08-23, narrowed same day):
the **source-intrinsic status** `implementation_status` follows the source and ships with the
package (written into all three ledgers before repacking); the **post-build qualifications**
`candidate_review` / `release_qualification` have their authoritative values in the Main
ledger plus independent review evidence — the in-package `not_run` / `not_claimed` values are
**build-time snapshots**, never final qualification; the **binding row** is written after
repacking and **before the full V3 run**, into Main only, as its own commit — a V3 executed
with no binding row lets candidate_binding fall silent, making that green under-covered.
The binding proves *which* two candidates are under review, not that the review passed.
Comparing the serving package against the frozen commit is carried by
check=release.candidate_binding (CR-3=B 2026-08-23).

#### Triggering situations (a question of judgement, exhaustive)

enforcement: prose_accepted (reason: whether a new version is worth opening is a judgement call with no machine handle; the half that can be machine-checked has been split out as the hard precondition above, check=runtime.version_bump_precondition, and this clause honestly admits it has no landing point rather than pretending coverage)

A new number is assigned only in the following three situations; everything else is "no version bump":

| # | Situation | Criterion |
|---|---|---|
| 1 | **Structural generation change** | the domain model, a migrator or a directory contract changed, and an old-version instance needs migration to run under the new version |
| 2 | **External distribution needs a reviewed number** | a delivery, an open-source release or an external trial needs to cite a version with `candidate_review: passed`, and the newest reviewed version is not sufficient |
| 3 | **Closing out after the previous version's partial items are finished** | the unimplemented items left when the previous version was declared are now done, or have been explicitly ruled out of scope, and the number advances on closure |

The adjudicator clause for situation #3 (CR-2=B 2026-08-23): whether an item has been
"explicitly ruled out of scope" is adjudicated by **the student in person**; the constructing
party must not sign for itself. Evidence shape and knock-on boundaries follow precedent rather
than additional written criteria: `T2AG_023_SCOPE_CUT_AND_CLOSEOUT_2026-08-23.md` (the
authority file records what was moved out and the substitute guarantee, and does not advance
the ADR/EV decision status of the item moved out).

**Explicitly not triggering**: adding a doctor check, adding or changing a playbook, repairing an
existing defect, or an independent EV-numbered batch. Those are accounted for through EV and the
changelog and do not move the version number. **A version bump is the product of a campaign, not
of time or of effort** — having done a lot of work is not a reason to bump; it only means the
changelog got longer.

#### Relationship to the envelope

The new number is fixed at the moment a `version_campaign` envelope freezes `target_version`, and
must never be written into `t2ag.md` §7 in passing by some batch. A routine batch that finds it
has "bumped the version along the way" was in fact an unauthorized campaign.

### 1.5 Authorization is non-amplifying

Verification level and authorization level are independent; V0–V3 define only the cost of
evidence and never change who approves. Any `continuous execution`, `version_campaign`, old
conversation or general standing permission covers only the RT1/RT2 the envelope lists, and can
never cover RT3. A real migration, a terminal lifecycle action, a strict student confirmation and
a cross-boundary write all require the user to confirm directly in the current round, after the
exact object, the body, the ID, the SHA and the result have all been generated and displayed.

A handoff, a receipt chain, a deterministic policy, a model recommendation, and an implementer's
or reviewer's technical conclusion can only preserve evidence; none of them may generate, renew
or countersign the user's authorization, and **an object not yet generated cannot be
pre-authorized**. After compaction, recovery or a handoff, the authorization scope may only be
preserved or narrowed, and when the exact boundary cannot be reconstructed, work must stop before
RT3.

## 2. Required structure of a work order (the obligation of whoever writes it)

1. **Header**: function | baseline snapshot declaration (version/date, whether line numbers are trustworthy) | **Evolution Register link** (which EV this order elaborates, registered in `t2ag_evolution_register.md`; on conflict the approved EV wins; the older name "EV link" means the same) | `execution_mode` | `risk_tier` | batch class | dependencies on other batches; a `version_campaign` must additionally give the complete envelope;
2. **Hard rules section**: one line citing "hard rules per §3 of this specification", plus the **iron rules specific to this order's domain** (such as "the evidence index comes before the instance main file"); never copy the general rule text;
3. **Numbered steps**: each step gives an anchor for locating plus a verification command; a gate step is explicitly marked "precondition: a one-sentence approval from the student", and a content-adjudication step is explicitly marked "the agent produces a difference report and does not decide on its own";
4. **Reference-surface closure table**: based on a measured grep, and noting that "**the list is a lower bound, not an upper bound** — if the closing grep finds an active reference beyond the list, the executor extends the handling and lists it in the report";
5. **Registration section**: changelog draft (placeholders clearly marked) | EV advancement actions (decided → changelog → archived backfill) | skeleton sync scope;
   entry structure, anchored/corroborating assertions and verification semantics are in `changelog_management.md` (the canonical owner of the verification layer; the order-writer's "write the draft" obligation stays in this section and does not sink).
6. **Risk registration and rollback granularity**: each stage's checkpoint unit, Git plan, retained RT3 items, and the authorization expiry conditions.
7. **Cross-model boundary economics** (the residual TB-5 clause, adjudicated 2026-08-19): a work order must be **self-contained** — the executor can start from the order and its explicit references alone, and must never be required to carry or restate the order-writer's conversation history. A construction report is skeletoned as a **change list + recomputation commands**; process narration is archived and does not enter the returned body. No hard byte budget is set (quality first, on the same reasoning as `handoff_management.md`'s "no hard budget, keep by relevance"; the remaining TB-5 clauses were judged absorbed by this specification plus the ASCII work-order form plus the 2026-08-18 model-selection default — see `docs/handoffs/T2AG_TOKEN_BUDGET_ADJUDICATION_CANDIDATES_2026-08-08.md` §5).
8. **Executor model selection + the DP scorecard** (HARNESS Q2/Q4, adjudicated 2026-08-19): construction with clear criteria (scanning, regeneration, format checking, mechanical diffs) runs on a low-model shell by default; adjudication questions and prose-layer judgement belong to the high model (the load-bearing discussion selection criteria are in `keystone_records.md` §5). A low-model construction session's report must carry a **DP scorecard** (observational, one pass/fail line each): DP-1 out-of-bounds write (does the diff file list contain a forbidden path) | DP-2 unauthorized construction (a write with no authorization statement) | DP-3 overstepping an adjudication stop point (was a required stop crossed) | DP-4 fake assurance (is a newly written rule's `check=` dangling). **The hybrid escalation rule**: only when a rule's score shows a suspicious difference is that single rule double-run under control (the same order on two shells) to verify; this never enters doctor and never enters daily work. The score difference *is* that rule's measured `model_dependent` value, backfilled into the R-GATE field (`rule_admission_gate.md` §2).

## 3. The standard set of hard rules (cited by every work order, never copied)

1. Locate by content anchor (`grep -n`) always; operating by line number is forbidden;
2. An ordinary RT1/RT2 unit runs targeted tests and `t2ag_doctor.py --profile runtime` first; only cross-release sync, a formal candidate or a release audit runs `--profile release`. A FAIL/WARN in the relevant profile that **this order did not predict** → stop and report it verbatim; a release-only divergence must never block daily teaching in reverse.
   Targeted tests must be selected from `test_dependencies.json` and planned in memory by `t2ag_test.py`; never create or delete a one-off Python suite. The plan must be listed first, then executed with that same selection and plan SHA. Doctor atoms, V0–V3, budgets and the anti-escalation gate follow `validation_workflow.json`; without a valid reason or a matching plan SHA, a release execution may only produce a plan;
3. Registry entries are only added or tombstoned, never deleted; the redirects array is append-only;
4. Historical lines in `60_journal/`, the changelog, memory and the problemlog are never edited;
   (the anchored/corroborating structure and spot-check semantics of a new changelog entry are in `changelog_management.md`; this item remains an executor hard rule and does not sink.)
5. A sole copy is never deleted; a file migration always uses `git mv`;
6. "Move + update every reference" is one commit unit, leaving no intermediate state;
7. **Checkpoint / commit protocol**: in the default mode the agent still needs explicit authorization for each Git write; an approved `version_campaign` may create recovery checkpoints per the limited Git plan it lists. Each time, use explicit paths and show the actual state and the cached diff; never use `git add .`. A checkpoint covers no push, tag, reset, checkout, stash, history rewrite, deletion of recovery, or release;
8. Content adjudication belongs to the student (the agent produces a difference report → the student approves → execution); structural adjudication is executed per the order.
9. **The cloud CH block status invariant** (the M4 precedent, 2026-07-24): inside the `T2AG_CLOUD_HANDOFF` block of `cloud/inbox/CH-*.md`, `status` must always be the cloud-produced value `proposed_for_local_review` (see `cloud_learning_sync.md` §7.2 and doctor). The **local terminal state** (accepted / partial_accept / rejected + sync_completed) is written only into the handoff table of `cloud_sync_state.md` and into the local adjudication section **outside** the block in the CH file. A work order demanding a change to the in-block status **is a defective order**: the executor refuses the change and declares the deviation, and must never silently rewrite it or silently skip the loop.
10. `clean != reviewed != released`. An evidence checkpoint proves only evidence; a recovery checkpoint provides only a restore point; a release snapshot must bind a passed full candidate re-review and a finalization delta independent re-review, and can never be inferred from a clean working tree or an ordinary commit.
11. **Rule semantic migration**: for the constitution, AGENTS, core/meta playbooks and hard-boundary governance documents, **diff-patch** is the default.
    When semantic migration is triggered, register line by line:
    `rule_id | old location/text anchor | action (keep/sink/retire) | new owner/equivalence gate | consumer | verification`.
    A `sink` must simultaneously prove the canonical owner, the necessary entry pointer, the consumer and the verification closure; a `retire` requires a valid adjudication. File length, keywords, a historical inventory or a model suggestion trigger a review only and constitute neither a rule, an authorization nor a finding; a finding forms only when a named rule is missing with no valid new landing point or retirement basis. The construction report must carry the rule_migration execution result, or a `not_applicable` reason. The full contract is in `main/t2ag.md` §6.3.

## 4. Construction report template (the executor's obligation; no field may be omitted)

```markdown
# Batch <X> construction report
**batch_id** / **executor** / **date** / **execution_mode** / **risk_tier** / **campaign_id (if applicable)** / **batch class** / **status**

## Baseline
Doctor before and after; **every WARN must name its object and quote the original** — "a known notice" is not naming.

## Student adjudications
Gate → adjudication, item by item.

## Files actually changed
Number | file | corresponding step | what changed.

## Delta manifest
Each unit records the before/after fingerprints, changed files, consumers, generated artifacts, the three-release impact closure and the checkpoint; one merged construction report is appended to throughout a version, rather than mechanically copying a report per unit.

## Scope deviation: none / yes (list + reason)
Steps not executed, batch trims, reordering.

## Execution deviation: none / yes (list + reason)
Anything done differently from the order (naming, exemptions, workarounds), including decisions changed midway.

## Three-release sync
Hash comparison results listed one by one for **every** core / playbook / tools file this batch touched — enumerate all, never sample.

## Closing grep verification
Every remaining reference attributed by class (historical line / redirects / inside an archive / a past-tense description).

## rule_migration execution result
For each row in the table: kept / sunk into ... / retired with reason; with no table, write "this batch touched no entry-point rule".

## Confirmation of prohibitions, and the definition of done
Ticked item by item.

## Remaining open items
To-dos where a conditional branch took the else, deferrals, and findings for the next batch.
```

"Scope deviation" and "execution deviation" are two separate fields: the first is "which subset of
the order was done", the second is "how what was done differs from the order". Batch D's FP
directory name belongs to the second and batch E2's trim to the first; mixed into one field,
neither can be driven to zero.

## 5. Re-review specification (the reviewer's obligation)

1. Check the report against the work order section by section; produce F-numbered findings, sorted by severity, each with a handling action;
2. **An empty deviation field while the re-review finds a deviation → reject outright**, whether or not the deviation itself was reasonable — this specification is designed so that honest declaration is the cheapest option;
3. An unnamed WARN → reject, have it named, then review again;
4. State the passing condition explicitly at the end of the review opinion ("passes once F_x is completed"); leave no open-ended conclusion;
5. The reviewer and the executor must be different models or different sessions.
6. The first version candidate must be fully re-reviewed; only when the input manifest is unchanged and the impact closure is provable may a later finding go through a delta re-review per `remediation_governance.md`.

## 6. Maintaining this specification

- Changes to this file go through a batch plus the changelog; the verification-layer conventions for a changelog entry are in `changelog_management.md` (this item remains the order-writer's / maintainer's discipline and does not sink).
- The bar for a new lesson entering this document: the same class of problem **occurring a second time** — once is enough for a re-review note; only the second occurrence is worth writing down (this guards against specification bloat).
