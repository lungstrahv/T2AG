# T2AG 0.2.3 Skeleton (English edition)

> An empty instance master. Copy it to create a new T2AG instance; it must never
> carry real student data itself. After copying to any new directory, an
> uninitialized profile is still validated as a Skeleton empty template; once you
> complete `first_run.md` and set the profile to `initialized`, that copy is
> automatically validated as a personal instance, independent of directory name.
> The maintained Skeleton source always keeps its empty-template identity.

Empty-template identity marker: `t2ag-skeleton`. You may freely rename the copied
directory; after first run, `initialization_status` in the profile identifies the
personal instance.

0.2.3 Skeleton provides the activity ledger, the `exerciseNN` templates, and the
atomic activity lifecycle/close tools. It keeps the classified reading
`ActivityRecord` empty containers and the bidirectional JSON candidate bridge
capability. It contains no real course activity, no AR, no books, no sidecars, no
candidate contributions and no consumption receipts. The two systems always write
to their own repositories.

---

## Read this before you start: what is and is not translated

The rule and user-facing document layers are now English. The edition is not yet
English-only: historical records and parts of the tool surface deliberately retain
Chinese or bilingual text. The table is the whole disclosure.

| Layer | Language | Consequence for you |
|---|---|---|
| Entry surface (this README, `AGENTS.md`, the constitution `main/t2ag.md`, `first_run.md`, `environment_assumptions.md`, the cloud bridge docs, the profile template, the offline HTML guide) | **English** | You can install, start up, and run a first lesson without reading Chinese. |
| Teaching output the model produces for you | **Whatever you set** | Controlled by `teaching_language` in your profile. Set it to `en-US` during first run and lessons are taught in English. |
| The rule layer — every playbook in `main/50_playbook/**` and the core contracts in `main/00_core/` | **English** | This is the part that decides how the harness behaves. **You can read and modify the harness internals.** |
| Tool output — `doctor`, `t2ag_context.py`, `state_refresh` | **Mixed English and Chinese** | Top-level verdicts and many common paths are English. Some diagnostics, generated prompts, compatibility markers and test fixtures remain Chinese or bilingual. Stable IDs such as `FAIL`, `WARN` and `first_run_required` remain machine-readable. |
| Instance templates, `docs/`, the journal and the group/student scaffolds | **English** | These files can be inspected and filled in without relying on Chinese instructions. A small number of source-language examples and compatibility tokens remain where a test or migration contract needs them. |
| `main/00_core/t2ag_changelog.md` — this project's own change history | **Chinese, on purpose** | It is an append-only record of what already happened, and the harness forbids editing historical lines. It is provenance, not instruction: nothing reads it to decide behaviour, and once you start your own instance you append your own entries in your own language. |
| `INVITED_USE_GRANT.md` | **English and Simplified Chinese** | This historical grant travels with invited-use packages delivered before the public repository; GitHub copies use the open-source licences described below. |

**What this actually costs you.** T2AG is a prompt harness: the documents *are*
the program. The rule layer — the part that determines behaviour — is now English,
so you can inspect *why* the harness behaves the way it does and change it. The
remaining language friction is concentrated in diagnostics, compatibility code,
fixtures and historical provenance rather than in the operating rules or the
files a new student must fill in.

We are telling you this up front rather than letting you discover it when `doctor`
prints a mixed-language diagnostic, because a tool that misrepresents its own
completeness wastes the time of exactly the people generous enough to try it early.

**Translation coverage is not feature parity.** A clean runtime result proves that
this edition satisfies the contracts it currently carries. It does not prove that
every mechanism added later to Main has already been backported. When a Chinese
peer edition is mounted, `release.cross_edition_parity` compares registered
identifiers and section numbers. Its registered backport-debt lines are disclosures,
not proof of equivalence; current-Main parity may be claimed only after that debt is
closed and the release checks for the frozen candidate pass.

**Known rough edges.** The translated corpus is new and has had no external
readers. Expect wording that assumes context you do not have, and occasional mixed
language in diagnostics. Those are the most useful things you can report back.

---

## One-minute startup and agent preferences

Three agents are available by default: a main agent handles the welcome, user
interaction, joining, and is the sole writer; a Runtime Sentinel does read-only
checks of the runtime doctor and state; a Context Prefetcher read-only-consumes L0
and returns a minimal structured handoff. A healthy instance's timing targets are
split by driver (canonical in `startup_orchestration.md` §1): the critical route
≤10 seconds; for a **non-textbook** course, the first actionable piece of learning
content ≤15 seconds; a **textbook** course must first consume the Scope text and
visuals of the same snapshot, and targets 45–60 seconds together with a complete
`recovery-settled`. Degrade when helper agents are unavailable, but never skip a
gate.

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
live in `main/50_playbook/startup_orchestration.md`.

## Quick start

1. Enter the **English edition directory containing this README**, then copy the
   current directory into a new target, excluding `.git/` and runtime caches.
   This works both in a standalone Skeleton checkout and in the public bilingual
   repository's `en/` directory:

   ```powershell
   $target = Join-Path $env:USERPROFILE "Documents\my-t2ag"
   robocopy . $target /E /XD .git __pycache__ .venv .cache .recovery .staging .uploads
   Set-Location $target
   ```

2. In the target directory, run the three read-only startup branches in parallel
   per `startup_orchestration.md` (Main welcome / Runtime Sentinel / Context
   Prefetcher). Only single-agent environments degrade to running the commands
   below in sequence — note that these five commands belong to those three
   branches rather than being five branches of their own, and that **critical
   must run first** (the canonical healthy path is critical-first; the full
   Markdown packet comes after it):

   ```powershell
   python -B main/70_tools/t2ag_context.py --format critical
   python -B main/70_tools/t2ag_doctor.py --profile runtime
   python -B main/70_tools/t2ag_state_refresh.py --check
   python -B main/70_tools/t2ag_context.py --format markdown
   python -B main/70_tools/t2ag_context.py --include-l1 --format markdown
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
`main/50_playbook/validation_flow.md`.

Ordinary startup, doctor and first run must never create, delete, rebuild or
upgrade `.venv`, must never auto-install dependencies, download textbooks, or
generate real Engagements. Tests are composed from persistent atomic tests per
`main/50_playbook/test_strategy.md`; an on-the-fly plan exists only in memory and
on stdout, and never generates-then-deletes a temporary Python suite.

## License

A copy obtained from the public GitHub repository is open source: the code layer
is licensed under Apache-2.0 and the prose layer under CC BY-SA 4.0. See
`LICENSING.md` for the path boundary and `NOTICE` for attribution notices.

Invited packages delivered directly by the author before the repository became
public remain governed by the bundled `INVITED_USE_GRANT.md`. Do not mix the
licensing terms for those historical packages with copies obtained from GitHub.
