---
adr_id: ADR-0004
portable_key: cloud-protocol-instance-separation
status: accepted
authority_project: T2AG
source_evolution: [EV-0021]
supersedes: []
implementation_refs: [main/70_tools/sync_cloud.py, main/50_playbook/cloud_instructions_template.md, main/50_playbook/cloud_learning_sync.md]
---

# ADR-0004: cloud protocol/instance separation and the open-source boundary

## Background

T2AG's cloud block crams five functions into one directory: the protocol definition
(`cloud_learning_sync.md`), the execution projection
(`T2AG_PROJECT_INSTRUCTIONS.txt`), the baseline cache (`t2ag_mobile_entry.md`), the sync ledger
(`cloud_sync_state.md`), and the channel archive (`outbox/`, `inbox/`). The execution projection is a
**hand-maintained dual-identity file**: protocol rules (open-sourceable) and instance identity routing
(course, teacher mapping, the anti-impersonation end-of-message marker) are interleaved line by line. The
protocol playbook §9 demands "prompt consistency", but only in prose, with no machine check at all —
consistent with the 2026-08-08 full-audit conclusion: the holes are produced in the prose enforcement
layer.

Open-sourcing pressure upgrades that interleaving from "inconvenient to maintain" to "a leak surface":
the end-of-message marker is an anti-impersonation shared secret and is burned the moment it is
published; and t2ag-lite carried the complete instance ledger and channel archive because `sync_lite`
deliberately kept the cloud text.

## Decision (the user's three consecutive adjudications, 2026-08-09)

1. **Separate protocol from instance; the projection is regenerable**: `T2AG_PROJECT_INSTRUCTIONS.txt`
   is demoted to a generated artifact. The protocol template
   `main/50_playbook/cloud_instructions_template.md` (covered by parity, with placeholders and zero
   instance values) plus the instance fields of `t2ag_mobile_entry.md` are assembled by `sync_cloud.py`.
   Hand-editing the generated artifact counts as drift and doctor reports a FAIL.
2. **The open-source boundary is the skeleton only**: the cloud block's sole open-source surface is
   t2ag-skeleton (generic_skeleton mode, verified to carry zero personal traces). t2ag-lite is a review
   snapshot, not an open-source master. The instance layer (mobile_entry, the ledger, the channel
   archive) never enters an open-source surface.
3. **reply_suffix records the mechanism, not the value**: the **mechanism** of the anti-impersonation
   end-of-message marker enters the protocol layer and the open-source surface (so a user knows the
   defence exists), while the **value** exists only in instance files. The leak scan treats "the value
   appears in the skeleton or the template" as a FAIL.

## How the trust boundary changes

Before: the correctness of the cloud prompt's content depended on the maintainer aligning the playbook
and the instance state by hand on every edit.
After: the source of truth for protocol content is the parity-covered template (skeleton synchronization
then holds naturally), and the source of truth for instance content is mobile_entry; the projection file
itself no longer carries any independent fact.

## Consequences

- When the 0.2.0 bridge resumes, re-sending a baseline is just a regeneration (update mobile_entry →
  `sync_cloud.py --write`) instead of hand-rewriting 188 lines of prompt.
- The skeleton's cloud isolation goes from "happens to be clean right now" to "an invariant with a scan
  gate".
- The cost: one more template file and one more tool; a template change must go through parity
  synchronization, one step more than editing the prompt directly.
