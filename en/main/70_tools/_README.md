# Tools — the script directory

> **What goes here**: deterministic check scripts — the doctor health check, the state_refresh cache refresh, the artifact_registry migration register.
> **Who writes, who reads**: maintained as the system evolves; run automatically at every acceptance and session close.
> **When to come here**: when you want to run the health check (doctor), refresh a cache (state_refresh), or look up a migration registration.

tools = deterministic checks, playbook = discretionary flows (constitution 2.7).

Added in the 0.2.1 closeout:

- `migration_txn_021.py`: the durable transaction protocol shared by the profile and ActivityRecord migrations;
- `migrate_021_activity_records.py`: reading ActivityRecord classification migration and Main-only evidence;
- `t2ag_reading_bridge.py`: the T2AG owner's context export, candidate import and receipt outbox;
- `contracts/reading_bridge_v1/`: six schemas byte-identical to the Skeleton's and the peer reading system's, plus their strict validators.
- `test_021_closeout.py`: migration transactions, ActivityRecord, Attempt, the bridge, and Lite rollback counterexamples;
- `scenarios/release_reading_bridge_saga.py`: the release-only two-repository LOOP and three kinds of interruption recovery;
- `contract_test_support.py` and four domain test entry points: shared atomic assertions, no longer invoked wholesale by a single aggregate file;
- `validation_workflow.json` + `validation_control.py`: Doctor atoms/profiles, V0–V3, budgets,
  plan SHA, and the anti-escalation control.
- `test_dependencies.json` + `t2ag_test.py`: the persistent test inventory, the dependency manifest, and the plan-bound executor.
- `test_release_*.py`: release atomic contracts split by candidate, receipt, evidence, gate, fault, and shadow;
- `scenarios/release_shadow_apply.py`: the full physical-root shadow scenario, kept out of ordinary discovery.
- `test_distribution_foundation.py`: the atomic self-check of the base Doctor/test/flow-control content across the three forms.
- `t2ag_source_pages.py`: the EV-0012 page-asset Scope / load receipt / immutable Snapshot +
  the `current_snapshot.json` pointer / fail-closed prepare / safe CacheEviction
  (`prepare --current`, `cache-gc --dry-run|--apply`, `scope`).
- `test_source_pages.py`: Scope geometry, sparse failure, heat_at, P0/out-of-bounds eviction, Snapshot idempotence and
  overwrite refusal, CLI arguments, and prepare negative cases.
- `50_playbook/source_page_assets.md`: the executable flow for page assets and the cache.
- `host_teaching_egress.py` + `test_host_teaching_egress.py`: the pure contract for host textbook-teaching egress
  (`lesson_emit` / freeform closed / status templates / reserve→commit). It does **not** send messages and does
  **not** constitute a structural hard gate; the design is in `docs/protocol/host-teaching-egress-api.md` and ADR-0002.
- critical packet withhold (`t2ag_context.py`): while a scope scan is pending, `route_ready` plus
  stripping the directly-sendable body; see `PendingScopeScanWithholdTests`.
- `decision_record_contract.py` + `test_decision_record_contract.py`: the deterministic relation between the Evolution Register
  and ADRs (no CLI); called by Doctor's `runtime.decision_records`.
- `build_journal_index.py`: supports the general `journal_index: false` (a redirect stays out of the generated index).

- `okf_export.py`: the T2AG → OKF v0.2 knowledge-bundle exporter (EV-0024, protocol `T2AG-OKF-1`). It is
  check-only by default; `--write` lands outside the repository in `t2ag-okf/`; `--scope mechanism|course:<ID>`;
  the leak gate runs before the write to disk and reuses the word list from `t2ag_doctor.SKELETON_PRIVACY_PATTERNS`;
  `--check-bundle` recomputes OKF §11 conformance. The specification is in `50_playbook/okf_adaptation.md`, and this
  tool is its recomputable implementation.
  **Not registered in doctor**: a bundle is an optional artifact and its absence must not block teaching.

The bridge tools write only this repository's sidecar; they never read or start the peer reading system, and
cross-repository calls are orchestrated by an external saga layer.
