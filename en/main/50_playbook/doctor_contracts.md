# Doctor's current contract list (doctor_contracts)

**Protection level**: core-playbook

> This file bounds what `t2ag_doctor.py` promises to verify mechanically in 0.2.2. Only a reproducible, locatable fact that violates an explicit current contract may become a FAIL; a semantic judgement must never pose as a mechanical gate.

## Three-form base capability

The doctor/test structure is base content shared by Main, Skeleton and Lite. It is not an
instance add-on for Main, and it is not an evidence bundle generated ad hoc at release time.
`t2ag_doctor.py`, `t2ag_test.py`, `test_dependencies.json`, `validation_control.py`,
`validation_workflow.json`, this contract, `test_strategy.md` and `validation_flow.md` must
exist in all three forms; the release profile SHA-compares the shared files. Main/Skeleton
execute these capabilities; Lite keeps only a byte-identical review copy.

`BASE_VALIDATION_FILES` is the mechanical base list. A missing file in any form, doctor no
longer defaulting to the runtime profile, or the runtime and release implementations being
merged, are all base-structure FAILs. Lite's read-only identity forbids executing scripts, but
it does not permit trimming these base files.

## 0. Run profiles

- `--profile runtime` is the default profile and the entry point for startup, recovery, sync
  and session close. It checks only the current release's local teaching state, activities and
  ledgers, the authority chain, context capability, skins and authorization safety. A daily
  startup may enter read-only `learning-ready` on a trusted L0-critical before doctor returns;
  once doctor returns a FAIL, the next teaching action and every write are blocked, and
  `recovery-settled` additionally requires `0 FAIL`.
- `--profile release` runs every runtime check first, then adds cross-release SHA, Core/Template
  parity, migration/journal/guide derived evidence, handoff, candidate isolation, the Git
  environment and the dirty-tree check.
- Doctor atoms, their order, dependencies and profile inheritance are defined solely by
  `validation_workflow.json`. Every run first prints the `t2ag.doctor_plan.v1` check list and
  plan SHA; `--check` can compose targeted atoms and pulls in their dependencies automatically.
- A full runtime run is the startup exception: after printing the fixed plan it may execute once
  directly. A targeted doctor run and every release execution must bind `--execute-plan`, and a
  release additionally requires a registered `--release-reason`.
- Lite, Git, candidates, historical migration evidence and cross-release divergence must never be
  reported by the runtime profile as a startup FAIL; those facts block only candidates and
  releases. A release profile passing is likewise not independent re-review or release approval.
- Doctor is not a test scheduler. Targeted tests are selected by `test_dependencies.json` and
  `t2ag_test.py`; the `fast / deep / release_only` boundaries are in `test_strategy.md`, and
  doctor must never widen the default startup checks because the number of test files grew.
- Release-only tests are partitioned into receipt/evidence/gate/fault/shadow domains;
  `release_suite` has no changed-path mapping and can be selected explicitly only for a frozen
  candidate or a formal release.

The full tree-shaped flow and the anti-escalation branches are in `validation_flow.md`. In the
control file, runtime is the only default profile and release must explicitly inherit runtime;
any tool bypassing the plan SHA, the release reason, the three-test-command budget or the
plan-only aggregation gate is a base-structure FAIL.

## 1. Result classes

| Class | Meaning | Doctor behaviour |
|---|---|---|
| FAIL | reproducible, locatable, violates an explicit current contract | returns non-zero |
| REVIEW | the requirement is vague, model judgement is unstable, or several reasonable designs exist | doctor does not assign this automatically; it moves to discussion |
| WARN | the fact holds but does not block the current goal | returns zero and reports |
| WAIVED | after discussion with whoever raised the requirement, explicitly deferred or the risk accepted | never hides the underlying fact; records the waiver evidence |

The three rounds, the at-most-three substantive attempts per round, and the reclassification
rules are in `remediation_governance.md`.

## 2. The 0.2.0 automatic check matrix

| Contract | Automatic entry point | Failure boundary |
|---|---|---|
| the nine domains and release identity | runtime local + release cross-release | the local directory/version does not close, or Main/Skeleton/Lite identity does not close at release |
| profile initialization and agent preferences | built into doctor | `initialized` still has placeholders, or is missing time, goals, foundation or preferences; an invalid agent schema, 1..3 ceiling, or parallel/ready/reporting enum |
| Course/Group/Binding/AR/EG | built into doctor | a schema, stable ID, reference or lifecycle conflict |
| progress identity | the unified activity router + state + doctor | `type/course_id/truth_scope` missing, impersonated, or not refused before any GENERATED write; after migration, truth_source-only is not accepted |
| learning-activity release capability | runtime local + release cross-release | a missing local Core/Template, or Main/Skeleton/Lite content divergence at release |
| recovery paths | the unified activity router + doctor | an ongoing Course missing an explicit `current_activity`, `current_activity_id`, canonical `resume_path` or `activity_position`, or a dangling target; an Exercise first start must never depend on a pre-made Lesson |
| the learning context packet | runtime local + release cross-release | a missing local tool/contract or wrong behaviour; three-release divergence blocks only in the release profile |
| Evolution Register <-> ADR linkage | runtime `decision_records` | a duplicate EV/ADR ID, a dangling bidirectional reference, an `accepted` pointing at a non-`decided` EV, a portable_key conflict, a supersedes cycle, a dead redirect; it makes **no** value judgement about "whether this deserves to be an ADR". On the skeleton side the register is zeroed for the instance (EV-0023), so the EV-link check is exempt while ADR file integrity is unchanged |
| existence of ADR/EV citations in the body | runtime `decision_record_citations` | an ADR-NNNN cited by current normative text (the constitution, AGENTS, README, `50_playbook/`, `docs/adr/` including ADR bodies, `docs/protocol/`) must exist; on the Main side an EV-NNNN must exist in the register, while on the skeleton side EV citations are exempt as maintainer provenance notes (EV-0023). The scan surface excludes append-only history such as the changelog/problemlog/journal (P-0067); ADR bodies and protocol were included after the 2026-08-09 re-review |
| state snapshot component boundary | `test_progress_identity_is_shared` + `test_state_refresh_activity_roundtrip` | state or doctor infers a missing activity, marks a historical Lesson active, constructs a path for a sentinel, has the group view assume the current activity must be a Lesson, or reads the same ongoing progress twice in one run and mixes state versions |
| activity transaction disk round-trip | `test_activity_cli_disk_roundtrip` | build a hardlink-free temporary full working tree from the current release itself and assert doctor actually detects this release's flavor; really execute `--write -> re-read -> --check -> full doctor -> recover route -> close route`, write progress and the current main carrier per the route result, then run state/doctor again; zero write hits, any step failing, or an Exercise modifying a historical Lesson |
| Lesson-context retirement | `test_exercise_current_lesson_driver_matrix` | under all four drivers, an active progress must not depend on or backfill `current_lesson`; a leftover invalid/dangling value must not drive routing, and a historical Lesson resolves only from the ledger/ContentGroup |
| planned/ongoing boundary | `test_planned_activity_fields_rejected` + doctor | a planned course pre-filling activity fields, or an ongoing course missing complete activity transaction fields |
| preparation snapshot activity boundary | `test_textbook_preparation_activity_matrix` + doctor | a textbook Lesson missing its preparation Snapshot, or a non-textbook Lesson holding a leftover page-cache reference |
| GENERATED owner | doctor + `test_activity_workflows_share_executable_route` | a Lesson retaining an ownerless `LESSON_PROGRESS` anchor, or recovery/close not sharing the unified activity route |
| activity boundary | built into doctor | a duplicate ID inside an activity-map unit, any unregistered Lesson/Exercise, or ContentGroup drift; an activity holding another activity, or recovering an ExerciseSession |
| non-textbook activity boundary | `test_lesson_retired_ownership_all_drivers` | a goal/project/praxis Lesson using its driver to bypass the base schema or the retired-ownership field check |
| teacher template routing | the unified teacher-mapping parser + doctor | the mapping table is not unique, the column schema drifted, a course is duplicated or unregistered, a token was smuggled in, a template identity does not match, or a template bypasses the current activity's main carrier |
| textbook Exercise persistent problem source | the unified activity router + doctor | an Exercise depending on a clearable cache such as Lesson working-pages; `source_path/source_document` not being a canonical, non-link path that still resolves inside this Course's book; the artifact ID, ContentGroup, locator, source-document SHA, registry lifecycle or per-problem statement failing to close; a binary omitted from Lite not proven by a complete formal migration manifest (report status/path/SHA, schema/target kind/count/sequence and the full operation fields) |
| Lesson/Exercise and exercise evidence | built into doctor | a conflict in the Lesson/Exercise main carrier, the ContentGroup/activity-map bidirectional relation, the U/AT/RV schema, references, image evidence or per-problem results; a textbook completion-node dependency that cannot be fully resolved, crosses out of the ContentGroup, or is absent from the Completion nodes table |
| knowledge ledgers | built into doctor | a question/mistake/reasoning ID, status or `next_id` conflict |
| project verification | built into doctor | criteria and evidence not separated, an unfinished node with pre-filled evidence, a completed M with no valid `VER-*` record, or a step missing `passed + an actual-result summary containing letters or digits` (punctuation alone does not count) are FAIL; a started M missing its mode is WARN |
| skins | built into doctor | a registry, metadata, art_file or release-divergence error |
| the preface, nine flows and the offline guide | release + `build_guide.py --check` | a preface generation anchor, the FLOW set/pairing, or guide drift |
| cloud paused state | built into doctor | a missing component, a protocol field conflict, a failed pause gate, or a dangling CD/CH registration |
| handoff classification and recovery routing | built into release | Active missing a lane/artifact_role, supporting material mixed into Active, a release backlog not isolated, or a conflict in the index/file/metadata/uniqueness or size-aging state |
| handoff assertion recomputation source | release `handoff` + `unsourced_handoff_assertions` | a count/existence/hash assertion in an active handoff body (`N items`, `zero hits`, `sha256:`) with no `←` recomputation source on the same line or the next line is a WARN, naming the file and line for each; fenced code and headings are not scanned, and **quotations and prose are not exempt** (`handoff_management.md` §5.6.4). The gate proves only "the source is adjacent"; it **makes no judgement** about command quality |
| host environment assumptions | runtime `environment` + `environment_probe_results` | `environment_assumptions.md` missing, or missing `EA-0001`~`EA-0003`, is FAIL; `INSTANCE_ROOT` disagreeing with the running root (a misaligned code tree) and `fitz` being unavailable are INFO; `.git` allowing create but not unlink is WARN. The probes are **read-only and report facts only** — they never install, never clean up a lock file, and never rewrite a path |
| changelog drift and rot | runtime `changelog` + `check_changelog_contract` (`parse_changelog_anchors` / `stale_changelog_claims`) | **Anchoring** (U2 approved A+B+C): the plan sha / checks / atom-set sha declared by the latest entry differing from measurement -> WARN, which must carry both the declared and the measured value. **Corroboration**: a `grep -c/-n` inside the latest entry's corroborating-assertions section returning zero hits -> WARN, which must name the entry title and the assertion text. **A missing anchor block** -> WARN. It does not prove completeness; the form is reused from `handoff_management.md` §5.6.2; the anchor measurement has zero git dependency |
| state/journal/migration/Lite | release derived tools | cache drift, missing evidence, a non-idempotent migration, or a projection difference |
| release candidate isolation | `t2ag_candidate_replay.py` + `test_candidate_replay_isolation_contract` | an effective sparse checkout/sparse index, Git environment/topology contamination, Main/Skeleton safe configuration failing preflight, the source/A/B byte lists or the copy results disagreeing, or the final source fingerprint changing after all A/B cross-checks |
| Git/environment hygiene | built into release | a tracked environment file is FAIL; an uncommitted working tree is WARN |
| teaching canonical carrier consistency (G2) | runtime `canonical_teaching_carrier` (`canonical_carrier_findings`) | for a textbook-driver course, `teaching_log.md` (C) and `emissions.jsonl` (L) must agree: a block in C with no line in L is **FAIL** (CANON-000, the writer was bypassed); a broken SHA chain in L is **FAIL** (001); a page identity disagreeing with the persistent SourcePageAsset fields is **FAIL** (002); a body hash disagreeing with the ledger is **FAIL** (003); a line in L with no block in C is **WARN** (004, interrupted-emit residue). Both missing or both empty stays silent (a grandfather clause). The old `lesson.md` is not scanned. It proves consistency, not "written via `canon_append.py`" (a self-consistent double write passes the gate; see the head of `canon_carrier.md`) |
| truthfulness of a declared enforcement (R-GATE) | runtime `rule_enforcement_integrity` (`rule_enforcement_findings` / `landing_defect`) | inside allowlisted rule files (`50_playbook/*.md` plus the three `00_core` model files), an `enforcement:` declaration must be honoured: a `check=` not in the `doctor_checks` key set, a missing `tool=` file, a value outside the four permitted values, or a misplaced field (`enforcement:` in the record area / `closure:` in a rule file) are **FAIL** (a dangling declaration is fake assurance, the P-0067 family); a dead `context=` anchor and an empty `prose_accepted` reason are **WARN** (rewording must not block teaching). Examples are handled by stripping fenced blocks first and then matching at line start (self-reference escape, `rule_admission_gate.md` §4). It **does not check "should have declared but did not"**. The record area (changelog / problemlog body / memory) and the constitution `t2ag.md` are explicitly exempt, for the reasons in `rule_admission_gate.md` §3 |
| **the approved Main<->Skeleton parity surface** | release `distribution_parity` (`check_distribution_parity`) | a byte difference inside the parity surface, or a file missing from the Skeleton, is **FAIL**; **an exemption whose two sides are now identical is a WARN** (prompting removal, so the list cannot grow into a blind spot). The parity surface is defined in §2.1 |
| **the cross-edition surface (Chinese <-> English)** | release `cross_edition_parity` (`cross_edition_parity_findings`) | the translated edition and the Chinese one must hold the same **machine identifiers** (handler names, check ids, profile registrations) and the same **section numbers**: an unregistered absence or addition is **FAIL** (CE-PAR-001/002); a missing or unparsable comparison source is **FAIL** (004 — better red than a quietly shrunken surface); a section number duplicated within one edition is **FAIL** (005, undecidable); a registered backport debt is **INFO** (000, and its reason must carry the refill condition); an exemption that has gone stale or dangles is **WARN** (003). Byte parity is unsatisfiable across languages (this edition's own foundation test calls `skipTest`), so the unit rises to identifiers and numbers; **prose wording is out of scope** — this gate proves the mechanism is present, not that the translation is faithful. Runs from either side, and stays silent when no peer edition is mounted, which is the ordinary state for anyone holding a single edition |

### 2.1 Defining the "approved parity surface" (P-0065)

Since 0.2.x, §7 item 4 has required "the approved Main/Skeleton parity surface to agree file by
file", but **that surface was never defined** — with no list, no check could reach it, and 12
files diverged silently until 2026-08-08. This section supplies the definition.

**The parity surface** = every file with extension `.md` / `.py` / `.json` under the following
directories of Main and Skeleton (excluding `__pycache__`):

```
main/50_playbook/
main/70_tools/
```

**The exemption list** (written in `DISTRIBUTION_PARITY_EXEMPT` in `t2ag_doctor.py`, where
**the reason is a mandatory value**):

| File | Reason for exemption |
|---|---|
| `main/70_tools/legacy_r_registry.json` | the Skeleton copy declares entries empty by design; the Main copy is the primary instance-level compatibility registry |
| `main/70_tools/artifact_registry.json` | Main holds real artifact entries; forcing parity would pour instance data into the Skeleton |

**Three disciplines**:

1. **An exemption must carry a reason.** An exemption with no reason hollows the check out — which is exactly the failure this clause exists to prevent.
2. **A stale exemption must be reported.** An exempt item whose two sides are in fact identical reports a WARN prompting removal; the list must not be append-only.
3. **Parity is not one-way overwriting.** Before repairing drift, judge the direction file by file: "A has it, B does not" may mean A is ahead, or it may mean **B retained retired content that A deleted**. On 2026-08-08 a line-count reading of the direction was nearly inverted, which would have kept a retired field Main had deliberately deleted as though the Skeleton were ahead.

**Release, not runtime**: per `t2ag.md` §3.2, a FAIL that is a distribution property blocks the
candidate and the release, not the day's teaching. Skeleton drift should never stop a lesson.

## 3. Human checks

The following judgements must be evidenced by the agent and, where necessary, discussed with
whoever raised the requirement; doctor verifies only whether their carrier exists:

- whether a teaching explanation is accurate and the feedback is good enough;
- whether the four handoff questions are semantically recoverable in fact;
- whether project acceptance content reaches product quality rather than merely being fully recorded;
- whether the exercise reasoning observations, error attribution and mastery inferences are reasonable;
- whether the REVIEW and WAIVED adjudications match the current goal.

## 4. Not activated, and retired

- The cross-course exam system is explicitly outside 0.2.0; `exam_protocol.md` and `exam_bank_spec.md` hold a deferred design only and trigger no doctor check in this version.
- The 0.1.x Case, CourseDefinition/CourseRun, Curriculum, FieldPractice, the old `skin/` and the old question-bank paths are retired; doctor only checks that they do not re-enter the active tree.
- KnowledgePoint and AbilitySummary are still not formal activity objects. OCR / page verification is **SourcePageAsset** provenance evidence (EV-0012 / `source_page_assets.md`), not an independent LearningActivity or a mastery record.
- Doctor runtime acceptance for a textbook Lesson:
  1. the **current** preparation Snapshot pointer (`current_snapshot.json`; guessing the newest by lexicographic order is forbidden) + LessonMap coverage/hash + load receipts + page-asset verification + PDF SHA + Scope contiguity/length + P0/quota warnings; a missing preparation is FAIL (the legacy `working_pages` path is retired).

## 5. Waiver boundary

Data integrity, a dangling path, a schema, an authority conflict and a projection difference may
never be waived while the contract is in force. Only a check that fails because of the external
environment, without affecting in-repo correctness, may have a formal waiver written; the record
must contain the factual evidence, the risk, the responsible party, the approver and the expiry.

## 6. The 0.2.0 final re-review freeze

The 0.2.0 final re-review recognizes only the six items of `git_workflow.md` §9.1 as newly
blocking; beyond that it re-checks only the three-release gates already in this table. A new
finding outside that list goes to the backlog and must not be promoted into a FAIL for this
generation merely because the threat model was raised. The daily learning chain has been
separately accepted and may continue; candidate generation and the Git snapshot still each
require later explicit authorization.

## 7. Version campaign and delta review global gates

The authorization envelope, reviewer independence and release qualification are human
governance and are not adjudicated by doctor alone. Doctor verifies only registered,
mechanically reproducible carriers; passing doctor is not `reviewed` and not `released`.

Whether for a full candidate re-review or a delta re-review, the following current gates are
indivisible and may not be skipped by a campaign envelope, a statement in a report, or a waiver:

1. data integrity, stable IDs, schema and reference closure;
2. activity entry points, recovery paths and authority-chain uniqueness;
3. migration evidence, journal/index and unfinished transactions;
4. the approved Main/Skeleton parity surface agreeing file by file (the surface and the exemption list are defined in §2.1; since 2026-08-08 this is enforced automatically by release `distribution_parity` rather than resting on manual comparison);
5. the Main -> Lite projection having no missing/differ/orphan/guide drift;
6. the final source, candidate tree, index and input docs manifest fingerprints being stable.

A delta review may reuse an old result only while the old evidence's input manifest SHA is
unchanged, the fingerprints of files outside the scope are unchanged, and the impact closure is
provable; otherwise reuse is refused. A change to the authority chain, a schema, registry
lifecycle, migration apply semantics, the transaction engine, candidate generation or a
safety/privacy boundary, or an unprovable impact closure, forces a return to full independent
re-review.

A recovery checkpoint proves only that a restore point exists and does not enter release
qualification. A release snapshot must be bound by an external independent report to a complete
candidate review and a bounded finalization delta review; `clean != reviewed != released`.

## 8. Discipline for creating a check (2026-08-10, established with the check-system work)

When adding or changing any doctor check:

1. **The four-anchor principle**: a check may hang only on the four existing anchors — startup (runtime doctor), session close (step 5 of session_close), construction (V0–V3 / t2ag_test) and release (the release profile). Never add a prose obligation that depends on "the model remembering to run it"; a check that only runs if the model remembers is treated as non-existent (root cause: the attention-overload line in the 2026-08-08 audit A3).
2. **A red-test fixture**: an added or changed check must come with at least one minimal fixture that triggers it (a NEGATIVE case in the contracts test group). A check that never fires is indistinguishable from a check that cannot fire. Existing checks are backfilled in the order the problemlog replay hits them; coverage = checks with a red test / total checks.
3. **The backfill contract and two strikes**: a problemlog entry must declare its enforcement landing point (the `closure` field, machine-checked by `runtime.problemlog_closure`); a problem with `occurrence_count >= 2` may no longer end in a prose fix and must land on `check=` (a doctor check) or `tool=` (enforcement in code). Field semantics are canonical in the backfill contract at the head of `00_core/t2ag_problemlog.md`.

4. **A marker gate must track the rule, not its surface** (2026-08-20, LV-5).
   When a check proves "rule R is stated in document D" by grepping a phrase, the
   phrase is part of prose — and prose gets re-wrapped, capitalised at the start of a
   sentence or a bold run, emphasised, re-spaced and translated. When the surface moves
   and the rule does not, the gate fails a document that satisfies it. That is
   `remediation_governance.md` §7 again: the carrier the check reads is not the fact it
   guarantees.

   The defect class stayed invisible while all prose was zh-CN — no spaces to wrap on,
   no letter case, and an untranslated surface never moves. Three instances landed
   within one day of translation work: a marker straddling a line break, a marker
   capitalised inside a bold run, and two *detection patterns* edited as though they
   were display messages.

   Two obligations follow:

   - every phrase a gate matches on lives in `MARKER_VARIANTS`, which carries one
     canonical identity plus the spellings each language edition uses. A literal that is
     matched must never sit loose among literals that are displayed — that adjacency is
     what turned a column key and a stale-claim pattern into "messages" during a bulk
     edit. Patterns are built from the registry by `field_line_re` / `heading_re` /
     `marker_alternation` rather than written inline, and handing a builder an
     unregistered key is itself a test failure: an inline `(?:状态|Status)` puts the
     spelling list in one more place the mutation cases cannot see, which is how 18
     sites stayed unprotected while 111 were covered;
   - the matcher is proven by mutation rather than by inspection. Meaning-preserving
     mutations (wrap, case, emphasis, spacing) must not change the verdict, and removing
     the marker must change it. The second half is what keeps a marker gate from passing
     vacuously.

   enforcement: tool=70_tools/test_marker_robustness.py

   **Honest boundary**: this proves the gate tracks the rule across surface change. It
   does not prove the rule's text is *correct*, and it does not detect "should have been
   marked but was not" — the same limit R-GATE declares. The case-insensitive fallback
   also applies to markers that are really machine tokens (`paused`), where a wrong-cased
   spelling would pass; that widening is recorded in the test docstring rather than
   relied on silently. The structural fix — giving each rule a machine-owned anchor ID so
   the needle stops being prose at all — is a separate migration, and `rule_id` already
   exists in the `rule_migration` tables waiting for it.

## 9. The external-source backlink contract (`source_catalog`, 2026-08-16, EV-0026)

A course's teaching structure is often **predicted** by the model first and only later compared
against the official catalogue in some round. This contract governs **not "whether it was
fetched" but "whether a diff was left behind after fetching"**.

enforcement: check=runtime.external_source_backlink

### 9.1 Field structure

A block inside the frontmatter of `40_course/<ID>/course.md` (the example is fenced and is not a
real annotation):

```yaml
source_catalog:
  url: https://example.org/course/catalog
  fetched_at: 2026-08-16
  predicted_count: 8
  actual_count: 13
  diff_recorded: 40_course/<ID>/lessons/lesson01/lesson01.md#official catalogue check
```

The anchor semantics of `diff_recorded` are **exactly the same as `enforcement: context=`**
(R-GATE `rule_admission_gate.md` §2, the same implementation `landing_defect`, with no separate
parser): the path is relative to the `main/` root, split on the **first** `#`, and matched as an
exact substring with zero normalization. Choose a short, stable phrase as the anchor, not a whole
sentence.

### 9.2 Determination and severity

| finding | Condition | Level |
|---|---|---|
| `EXTSRC-001` | a course with `lifecycle_status: ongoing` and no `source_catalog:` | **WARN** |
| `EXTSRC-002` | `source_catalog:` present but `diff_recorded` missing/unresolvable, or an inline value other than `none` | **FAIL** |
| `EXTSRC-004` | `source_catalog: none` with no reason | **WARN** |

> `EXTSRC-003` is a **retired slot** (the seed <-> course edge, moved to the T1 cross-repo
> contract before implementation). **Never reuse it** — a reused stable ID makes every later
> citation of it ambiguous (the P-0072 lesson).

#### 9.2.1 `none`: a course with no external catalogue to compare against

For textbook-driven and project-driven courses, the authoritative catalogue is **the printed
textbook's table of contents, already in the repo**, and there is no external catalogue to fetch.
Such a course writes:

```yaml
source_catalog: none (reason: textbook-driven; the authoritative catalogue is the printed book's contents, already in book/)
```

**Why this branch must exist**: otherwise such a course carries a 001 forever that **cannot
legitimately be cleared** — and permanent noise trains the whole warning channel into something
ignorable.

**Why `none` must carry a reason**: the reason is the only thing keeping `none` from becoming a
mute button, exactly as with `prose_accepted (reason)`. **`none` is not an exemption pass; it is
a refutable assertion** — whoever finds that this course does have an official catalogue page
should change it.

**Why absence is only a WARN**: the prediction itself is **legitimate and valuable** — it is a
falsifiable forecast whose value is precisely the diff in the round the catalogue is fetched
(the first measurement: 8 lessons predicted, 13 actual, with the gaps identifiable). A FAIL
would force "fetch the catalogue on day one", and that diff would then never exist — **trading
the information away for enforcement**. So absence is a **legitimate "not yet checked" state**,
not a to-do.

**Why a dangling value is a FAIL**: the presence of `source_catalog` **claims the comparison
happened**; if `diff_recorded` points at nothing, evidence is claimed and is not there — a
dangling claim, the same shape as P-0067, and more poisonous than claiming nothing.

The same discipline as R-GATE: **it governs that what was said must hold, and says nothing about
what was not said.**

### 9.3 Limits (must be written alongside the mechanism)

1. **It does not guarantee the catalogue is current**, only that "claiming to have fetched requires leaving a diff". After eight days without a fetch, this check still emits only a WARN — **enforcement was traded away for information, not lost by oversight** (the cost section of EV-0026).
2. **It does not cover the time dimension** (a stale mount cache, P-0070). The source of truth for freshness is still only the Read tool.
3. **It does not check "should have declared but did not"**: a `planned` course, and a course with no external catalogue to compare against, are outside the determination surface.

### 9.4 The seed <-> course edge is not inside this check

The backlink between a course and `docs/seeds/` travels on the **T1 reference contract**
(`cross_repo_reference.md`), with the sidecar landing on the **course side** at
`40_course/<ID>/external_refs.json`, validated by the **existing** `runtime.external_references`.
This check takes **no part** in it.

The reason: `check_external_references` only does `MAIN.rglob("external_refs.json")`, so a
sidecar placed in `docs/seeds/` would be invisible to doctor and silently produce zero findings —
that is fake assurance. The edge direction is therefore fixed as **course ──► seed** (the
referencing side is the course, lives inside `main/`, and is reachable).

> **This does not conflict with `docs/SEEDS.md`'s "there is no seed → course channel".**
> That prohibits a **promotion channel** (a seed must not become a course just because someone
> wants to study it); what is built here is a **backward reference edge** (the course records
> "this seed spilled out of this classroom"). **It is a decision, not a hole.**

## 10. The playbook grading instrument (two tiers)

| Tier | Check ID | handler | finding | Level |
|---|---|---|---|---|
| runtime (local) | `runtime.playbook_taxonomy` | `check_playbook_taxonomy` | PB-TAXO-001 invalid value | FAIL |
| runtime | same | same | PB-TAXO-002 no marker | WARN (only `_README.md` is allowlisted) |
| runtime | same | same | PB-TAXO-005 different valid values in one file | FAIL; a repeated identical value is WARN |
| release (cross-release) | `release.playbook_taxonomy_parity` | `check_playbook_taxonomy_parity` | PB-TAXO-003 meta+core set or SHA divergence | FAIL |
| release | same | same | PB-TAXO-004 Skeleton missing any meta | FAIL |

The shared parser runs `strip_fenced_blocks` first, then matches
`^(?:>\s*)?\*\*(?:保护级别|Protection level)\*\*[：:]\s*(meta-playbook|core-playbook|playbook)\b`,
returning every match (not the first). A citation inside a fence does not count. A blockquote
prefix is recognized. Both language spellings of the marker are accepted (LV-5).

**Honest boundary**: it does not check "the semantic correctness of a marker that should have
been applied" — this check verifies only the marker's form and the cross-release set/SHA, and
never judges whether a given playbook ought to be meta or core under the §4 functional criteria.

The existing `check_core_playbooks` (`release.core_playbooks`) only swaps in the same parser in
this batch, with its registration unchanged; how it divides labour with the parity check is
pooled separately.
