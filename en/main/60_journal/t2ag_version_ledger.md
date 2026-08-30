# T2AG version ledger (canonical; sunk from constitution §7 on 2026-08-08 / EV-0020)

> **This file is the single source of truth for the three version-status fields**
> (`implementation_status` / `candidate_review` / `release_qualification`)
> (CR-1=A 2026-08-23, P-0086); constitution §7 points, it does not carry — the
> runtime version number itself is read from §7's first line.
> The old header ("present state is in §7") formed a circular pointer and is
> retired (2026-08-23 review correction).
> **Write ownership (adjudicated 2026-08-23, narrowed the same day into three
> layers)**:
> (1) the **source-intrinsic status** `implementation_status` follows the three
> sources and ships with the package, written before repacking — an instance's
> later version bump needs the predecessor row;
> (2) the **post-build qualifications** `candidate_review` /
> `release_qualification` have their authoritative values in the **Main ledger
> plus independent review evidence**; the `not_run` / `not_claimed` values in a
> Skeleton or package are **build-time snapshots**, never final qualification —
> a V3 verdict is a post-build fact, and requiring it to pre-exist inside the
> reviewed package is the infinite loop "write pass → repack → new package
> unreviewed";
> (3) the `release_candidate` **freeze-binding row** (which references package
> commits) is written once the packages and their source commits exist, and
> **before the full V3 run**, into Main only, as its own commit — Main is never
> packaged, so there is no commit cycle; a V3 executed with no binding row lets
> candidate_binding fall into its silent branch, making that green
> under-covered. The binding proves *which* two candidates are under review,
> not that the review passed. A binding row must carry zh/en exactly once each
> (enforced by CAND-BIND-004..006; corrupted, missing or duplicated ends all
> FAIL).
> The same-shaped disposal for changelog entries is in
> `50_playbook/changelog_management.md#When a release fact is written`.

- 0.2.0 baseline structural authority：`60_journal/T2AG_0.2.0_STRUCTURE_PLAN.md`；migrator：`70_tools/migrate_020.py`
- 0.2.1 incremental construction authority：`T2AG-STUDENT-PROFILE-READING-BRIDGE-20260730`
- 0.2.1 full closeout and review-governance authority：
  `docs/handoffs/T2AG_021_FULL_CLOSEOUT_AND_REVIEW_GOVERNANCE_WORKORDER_2026-08-04.md`
- 0.2.1 `implementation_status`：`complete`；`candidate_review`：`passed`
- 0.2.1 candidate review：
  `docs/handoffs/T2AG_021_VERSION_INDEPENDENT_REVIEW_2026-08-04.md`，SHA-256
  `92194e00259fe7f5d80b1e458196329fbcfe7bd4e1ec1a15dd01f1383e6dd3ea`
- 0.2.1 external authority for release eligibility：
  `docs/handoffs/T2AG_021_FINALIZATION_DELTA_REVIEW_2026-08-04.md`；a release PASS must not be written before that report is issued
- 0.2.2 Activity Close construction authority：
  `docs/handoffs/T2AG_022_ACTIVITY_CLOSE_LEDGER_WORKORDER_2026-08-04.md`
- 0.2.2 `implementation_status`：`complete`；`candidate_review`：`passed`
- 0.2.2 candidate review：
  `docs/handoffs/T2AG_022_VERSION_INDEPENDENT_REVIEW_2026-08-05.md`，SHA-256
  `45548a3d66f717df6d92c8c5ae163bc89ca504c55cb9d1e4867e834a615dcffd`
- 0.2.2 in-repo `release_qualification`: `finalization_delta_passed`; the independent conclusion is in
  `docs/handoffs/T2AG_022_FINALIZATION_DELTA_REVIEW_2026-08-05.md`（`finalization_delta_passed`）
- 0.2.3 scope re-adjudication and closeout authority:
  `<workspace>/docs/handoffs/T2AG_023_SCOPE_CUT_AND_CLOSEOUT_2026-08-23.md`
- 0.2.3 `implementation_status`：`complete`（the host interceptor was explicitly
  re-adjudicated out of scope on 2026-08-23 and returned to EV-0013 as an open
  evolution item; criterion: batch_workorder_spec.md §1.4.1 situation #3）
- 0.2.3 `candidate_review`：`passed`；in-repo `release_qualification`：`finalization_delta_passed`
- Most recent release-qualified version: `0.2.3` (authority lives in the Main ledger
  plus independent review evidence; the preceding row was backfilled from the
  independent review completed on 2026-08-24 — **backfilling is not pre-writing**:
  the review preceded it, so it does not create the
  "write passed -> repackage -> the new package was never reviewed" loop)
- 0.2.4 `implementation_status`: `complete` (same reading across all three sources; the
  authoritative value lives in the Main ledger and this row is the projection-side sync.
  The content axis is caught up in this edition; the mechanism axis — the doctor
  modularization projection — is explicitly rescoped to the clean-room rebuild per
  spec 1.4.1 case #3, authority: T2AC closeout workorder 14.130)
- 0.2.4 `candidate_review`: `not_run`; in-repo `release_qualification`: `not_claimed`
- 0.2.4 is currently a development baseline only; no candidate has been frozen and no
  independent review or release qualification has been obtained
