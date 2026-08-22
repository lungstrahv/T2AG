# T2AG 0.2.3 Skeleton (English edition)

> An empty instance master. Copy it to create a new T2AG instance; it must never
> carry real student data itself. After copying to any new directory, an
> uninitialized profile is still validated as a Skeleton empty template; once you
> complete `first_run.md` and set the profile to `initialized`, that copy is
> automatically validated as a personal instance, independent of directory name.
> The original `t2ag-skeleton/` repository always keeps its empty-template identity.

0.2.3 Skeleton provides the activity ledger, the `exerciseNN` templates, and the
atomic activity lifecycle/close tools. It keeps the classified reading
`ActivityRecord` empty containers and the bidirectional JSON candidate bridge
capability. It contains no real course activity, no AR, no books, no sidecars, no
candidate contributions and no consumption receipts. The two systems always write
to their own repositories.

---

## Read this before you start: what is and is not translated

This edition is **honest about being partial**. The table is the whole disclosure.

| Layer | Language | Consequence for you |
|---|---|---|
| Entry surface (this README, `AGENTS.md`, the constitution `main/t2ag.md`, `first_run.md`, `environment_assumptions.md`, the cloud bridge docs, the profile template, the offline HTML guide) | **English** | You can install, start up, and run a first lesson without reading Chinese. |
| Teaching output the model produces for you | **Whatever you set** | Controlled by `teaching_language` in your profile. Set it to `en-US` during first run and lessons are taught in English. |
| Playbook internals (`main/50_playbook/**`, ~111k characters) and the tool source comments | **Chinese** | The model reads these fine — it is bilingual, and the harness behaves correctly. **You cannot yet read or modify the harness internals.** |
| Tool output — `doctor`, `t2ag_context.py`, `state_refresh` | **Chinese** | The very first command in Quick start prints its verdict in Chinese. `result: 0 FAIL, 0 WARN` is machine-readable, and the trailing line means "local teaching run check passed". Roughly 850 message strings are still Chinese. This is the most visible rough edge and we know it. |

**What this actually costs you.** T2AG is a prompt harness: the documents *are*
the program. Leaving the internals in Chinese means the machine still works, but
you lose the ability to inspect *why* it behaves the way it does, and to change
it. If your reason for trying T2AG is "I want to shape my own learning shell,"
that part is not available to you in this edition yet. If your reason is "I want
to see whether this way of studying helps," that part works today.

We are telling you this up front rather than letting you discover it at the first
Chinese playbook, because a tool that misrepresents its own completeness wastes
the time of exactly the people generous enough to try it early.

**Known rough edges.** The English entry surface is new and has had one author
and no external readers. Expect wording that assumes context you do not have.
That is the single most useful thing you can report back.

---

## One-minute startup and agent preferences

Three agents are available by default: a main agent handles the welcome, user
interaction, joining, and is the sole writer; a Runtime Sentinel does read-only
checks of the runtime doctor and state; a Context Prefetcher read-only-consumes L0
and returns a minimal structured handoff. A healthy instance targets the first
actionable piece of learning content within 60 seconds. Degrade when helper agents
are unavailable, but never skip a gate.

The empty-template profile uses the generic defaults from
`agent_collaboration_preferences.v1`: `agent_pool_limit: 6`,
`agent_max_active: 3`, `agent_parallel_startup: enabled`. The former is the
identity-pool capacity including Main; the latter is the concurrent-run ceiling
including Main. A student may override both at first run. The preference also
defaults to `agent_startup_readiness: learning_ready_first` and reports only
blockers in the background. It grants no write, close, migration or RT3
authority.

Startup formation and construction-helper budget are different things: routine
takeover may use two read-only helpers, while ordinary system changes and
verification still default to one helper, three tests, ten minutes. Full rules
live in `main/50_playbook/startup_orchestration.md` (Chinese).

## Quick start

1. Copy the whole directory to a new target directory.
2. In the target directory, run the three read-only startup paths in parallel per
   `startup_orchestration.md`. Only single-agent environments degrade to running
   the commands below in sequence:

   ```powershell
python -B main/70_tools/t2ag_doctor.py --profile runtime
   python -B main/70_tools/t2ag_state_refresh.py --check
   python -B main/70_tools/t2ag_context.py --format markdown
   python -B main/70_tools/t2ag_context.py --include-l1 --format markdown
   python -B main/70_tools/t2ag_test.py --component doctor --tier fast --plan-only
   ```

3. On an empty template the context command must return `first_run_required`.
   Then read `main/t2ag.md` and `main/50_playbook/first_run.md`.
4. Confirm the profile, the first course and the first group with the user before
   writing anything explicitly.

**Choosing your first course (important)**: you do not have to start from a
textbook. When creating the first course, tell the agent to use a `goal` or
`project` driver (for example "learn X by building Y"). That bypasses the
textbook page-asset pipeline entirely — PDF scanning, page images and
page-by-page proofreading are the heaviest chain in the system and a poor fit
for a first run. Open a `textbook`-driven course later, once the system runs
smoothly and you genuinely need to work through a book page by page.

**Expected output**: on a fresh copy, `doctor --profile runtime` should report
**`0 FAIL, 0 WARN`**. If you see `EA-0003 ... can create files but cannot unlink`,
the mount holding that directory does not support deletion (common when a
container mounts a host directory). In that case **do not run any git write
operation in that environment**; switch to the host machine. Nothing else is
affected. See `main/50_playbook/environment_assumptions.md`.

Any **FAIL** is not expected. Fix it before continuing.

The post-initialization source-inventory ratio only describes the selection
range. The soft budget is measured against fully serialized Markdown (L0, and L0
plus the first L1). Do not call that ratio an end-to-end token reduction.

## Release roles

- Main: the master copy of rules and the real instance.
- Skeleton: generic rules and the empty-instance master.
- Lite: a review snapshot, generated one-way from Main only.

All three forms must carry the runtime/release doctor layering, the atomic check
control file, the test selector, the dependency manifest and the tree-shaped
flows. Main and Skeleton are executable; Lite keeps only a byte-identical
read-only review copy. Base files are enforced by `BASE_VALIDATION_FILES` in
`t2ag_doctor.py` and are not optional release attachments. Full flow in
`main/50_playbook/validation_flow.md` (Chinese).

Ordinary startup, doctor and first run must never create, delete, rebuild or
upgrade `.venv`, must never auto-install dependencies, download textbooks, or
generate real Engagements. Tests are composed from persistent atomic tests per
`main/50_playbook/test_strategy.md`; an on-the-fly plan exists only in memory and
on stdout, and never generates-then-deletes a temporary Python suite.

## License

This package is **not open source yet**. It ships under
`INVITED_USE_GRANT.md` — a bilingual (English / 简体中文), per-release,
revocable grant to invited individuals. Read §3: the consideration for a free
grant is that you give feedback. Read §5: every learning record you produce
belongs to you, is never uploaded, and survives revocation.

The author's current plan is Apache-2.0 for the code layer and CC BY-SA 4.0 for
the prose layer once the trial closes, but that plan is stated in §8 as a plan
and explicitly not a commitment.
