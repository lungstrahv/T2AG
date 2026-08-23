# Test selection and evidence reuse (test_strategy)

**Protection level**: core-playbook

This rule separates "keeping test capability" from "this run's combination". Test code is a long-term
asset; one task only produces an in-memory execution plan — it does not generate a temporary Python
suite, and it does not delete test code afterwards.

Together with the Doctor profile tiers, this rule forms the three-form base capability, self-checked
atomically by the `distribution_foundation` component and `test_distribution_foundation.py`; Lite
carries it for review only and does not execute it.
The full detection tree is in `validation_flow.md`. `validation_workflow.json` governs profiles, V0–V3,
budgets and the anti-escalation gate; `test_dependencies.json` governs only the test inventory, tiers,
components, and source dependencies.

## 1. The persistent layer

- Atomic assertions live in stable `test_*.py` files or a shared assertion library; they are organized by
  domain, not by whichever work order created them.
- `70_tools/test_dependencies.json` is the single manifest of tests, components, tiers, and source
  dependencies.
- The manifest distinguishes `kind=atomic` from `kind=scenario` explicitly; the former may only be
  `70_tools/test_*.py`, and the latter may only live under `70_tools/scenarios/` and must not use a
  `test_` filename.
- `70_tools/t2ag_test.py` validates the manifest's completeness, selects tests by component or by changed
  path, and binds a SHA-256 to each selected file.
- Atomic tests may also be combined explicitly by stable `--test ID`; an ordinary run allows at most
  three test commands.
- When a `test_*.py` is added or removed within ordinary discovery scope, the dependency manifest must be
  updated in the same batch; a glob must never be used to sweep a new test automatically into a
  migration, release, or full-run boundary.
- A complete scenario needing a real physical root, fault injection, or cross-repository orchestration
  goes in `70_tools/scenarios/`, does not use a `test_` filename, and does not take part in ordinary test
  discovery.

## 2. The ad-hoc combination

An on-the-fly combination exists only inside the `t2ag.test_plan.v1` in-memory object and in standard
output. List the plan first, then execute with exactly the same selection parameters and plan SHA:

```powershell
python -B main/70_tools/t2ag_test.py --test foundation.structure --test doctor.postcheck --tier fast --plan-only
python -B main/70_tools/t2ag_test.py --test foundation.structure --test doctor.postcheck --tier fast --execute-plan <PLAN_SHA>
python -B main/70_tools/t2ag_test.py --changed main/70_tools/activity_close.py --tier fast --plan-only
python -B main/70_tools/t2ag_test.py --changed main/70_tools/activity_close.py --tier fast --execute-plan <PLAN_SHA>
python -B main/70_tools/t2ag_test.py --component transaction --tier deep --plan-only
python -B main/70_tools/t2ag_test.py --component release_suite --tier release_only --plan-only
```

Without `--execute-plan`, the selector only prints the plan and starts no test; a SHA mismatch refuses to
execute. A release_only run additionally requires `--release-reason`, and the `release_suite` aggregate is
always read-only. The executor starts the saved test files in manifest order. Concatenating and writing
one-off code such as `test_adhoc.py` or
`test_current_batch.py` to disk is forbidden — which is also why there is no "delete the temporary test
file afterwards" cleanup step.
What has to be kept is only the plan SHA, the test-file SHAs, and the result summary.

## 3. Tiers

| Tier | Default use | Contents |
|---|---|---|
| `fast` | V1 and ordinary V2 targeted regression | the directly related local contracts and round-trips |
| `deep` | the affected core transactions, migrations, recovery | `fast` plus the related deep tests |
| `release_only` | a frozen candidate or a formal release | the corresponding release atomic contracts, matrix evidence, and explicit scenarios |

A tier is a ceiling, not an order to "always run everything". An ordinary task must never escalate
automatically because a `deep` or `release_only` entry exists in the manifest; an entry outside this
run's tier is marked deferred in the plan.
When an ordinary selection exceeds three executable test files, the plan may still be viewed, but the
executor must refuse and demand a smaller combination.

Release tests must likewise be selected by component. `release_receipts`, `release_evidence`,
`release_gates`,
`release_faults`, and `release_shadow` each bind only their direct tools; `release_suite` is an explicit
aggregate component with no changed-path mapping and `--plan-only` execution, and no ordinary change may
select or execute it automatically. A physical-root scenario is registered in a combination only as
deferred, and must be invoked explicitly after the required fixture is supplied per the plan.

## 4. Current domain entry points

- `test_runtime_contracts.py`: profiles, routing, teacher, state refresh, skin.
- `test_activity_contracts.py`: the activity model, course templates, evidence, and executable paths.
- `test_release_contracts.py`: candidate isolation and release-process contracts; release tier only.
- `test_release_receipts.py`: the receipt-chain atomic contracts.
- `test_release_evidence.py`: the structured-evidence atomic contracts.
- `test_release_gates.py`: the gate matrix and frozen-member atomic contracts.
- `test_release_fault_contracts.py`: the fault-boundary enumeration atomic contracts; it does not run the full fault matrix.
- `test_release_shadow_contracts.py`: the shadow authorization, cleanup, and non-overwritability atomic contracts.
- `test_legacy_migrations.py`: historical migration compatibility; run only when the relevant migration is affected.
- `test_022_close_roundtrip.py`: holds the assertions unique to the close runtime; no duplicate entry point is kept.
- `scenarios/release_reading_bridge_saga.py`: the full physical-root release scenario; a fixture must be supplied explicitly.
- `scenarios/release_shadow_apply.py`: the full physical-root shadow apply/rollback/second-run scenario.

## 5. Rules for changing and deleting

Deleting a test must prove the assertion has been merged into another stable entry point, or explicitly
retired by a current contract; being slow, not selected by the current task, or already passing are none
of them grounds for deletion. Duplicate assertions are merged first, and historical migration and release
evidence tests are kept at a lower tier.

A result may be reused when the SHA has not changed and its dependencies were not affected. A finding fix
re-runs only the affected components; only a frozen candidate runs the `release_only` combination once
and gets a full independent re-review. When the selection result exceeds an ordinary task's budget,
record the deferred items and wait for a formal candidate; never widen the verification scope
automatically.
