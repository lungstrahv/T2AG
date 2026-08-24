# T2AG 0.2.4 agent entry point

On entering this repository, read `main/t2ag.md` (the constitution) first: the
immutable principles, the structure of each domain, and every canonical pointer
live there. This file only orients you inside the repository; it does not restate
rules. Where it conflicts with the constitution, the constitution wins.

- **Startup**: welcome message and the two read-only recovery branches run in
  parallel. Formation, commands, handoff fields and the two-phase join are
  canonical in `main/50_playbook/startup_orchestration.md` (§0–§5).
- **Takeover**: immediate excerpt, L0/L1/L2 layering, course selection and Main
  consumption discipline are canonical in
  `main/50_playbook/context_packet.md`.
- **Textbook scan gate**: the Scope scan for this session (A1–A6, ADR-0003:
  host-observable delivery justification) must complete before teaching begins.
  A snapshot, a historical receipt, a hash, or frontmatter alone must never pose
  as this round. Canonical: `main/50_playbook/source_page_assets.md` §3.1.
- **Teaching gates**: the three-gate protocol, inter-block transitions, page
  turns, openings and the hint gate are in constitution §1.6/§4 and the gate
  ledger mechanism (EV-0018). At most one new teaching block per round; a
  "continue" expires once used.
- **Verification and authorization**: V0–V3 and test composition follow the
  canonical references in constitution §6.1.
  **Authorization is non-amplifying and budget stop-loss closes the loop** —
  canonical: constitution §6.2, including the `stopped_budget` state and the
  test / time / token budget ceilings.
- **State claims**: only after the runtime doctor reports `0 FAIL` and state
  shows no drift may you claim local closure. Write-back order is in
  constitution §5.

Role boundary: this file addresses an agent already inside the repository.
**For a single-instance install this file is the entire entry point** — once you
unpack or copy this repository into a directory, that directory is the workspace
and there is no parent-level orientation file. Only a workspace maintaining
multiple releases (with `t2ag/`, `t2ag-skeleton/`, `t2ag-lite/` and `docs/` as
siblings) additionally has a `../AGENTS.md` for cross-repository routing.
Single-instance users do not need it and should not go looking for it.

First run does not depend on this file: when `t2ag_context.py` returns
`first_run_required`, its `next_action` field points mechanically at
`main/50_playbook/first_run.md`.

## Language of this edition

The entry surface, constitution, core contracts, playbooks, instance templates,
ADR/protocol documents and journal scaffolds are English. The append-only project
changelog intentionally preserves its historical Chinese entries, and some tool
messages, compatibility markers and fixtures remain Chinese or bilingual. Those
remainders do not change which document governs. Teaching output language is set
by `teaching_language` in the student profile, not by the language of repository
files.

## Traversal guidance (no need to read everything at first run)

A first visit **does not require traversing the whole repository** (roughly 220
files / 4.5 MB). Read `README.md` → `main/t2ag.md` (the constitution), then run
`python -B main/70_tools/t2ag_context.py` and follow the `next_action` it
returns. The following directories are **not needed** during first run:

- `main/70_tools/` (implementation and tests; tools are invoked from the command
  line rather than read end to end)
- `main/60_journal/` (this instance's decision register; starts as an empty
  template)
- `docs/` (architecture decisions and design protocol records; consult when you
  need to audit where a decision came from)
