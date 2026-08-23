---
adr_id: ADR-0005
portable_key: okf-knowledge-bundle-export-boundary
status: accepted
authority_project: T2AG
source_evolution: [EV-0024]
supersedes: []
implementation_refs: [main/50_playbook/okf_adaptation.md, main/70_tools/okf_export.py]
---

# ADR-0005: the OKF knowledge-bundle export boundary — the mechanism is exchangeable, the instance never leaves

## Background

The Open Knowledge Format (OKF, published by Google Cloud in 2026-06; this file targets v0.2) writes
knowledge as "directories + markdown + YAML frontmatter": the one hard requirement is that every concept
carries a non-empty `type`, while the trust family
(`sources` / `generated` / `verified` / `status` / `stale_after`) is entirely optional and **absence
carries meaning**; a consumer may not reject content for a missing field, an unknown `type`, or a broken
link. It standardizes the spontaneous "LLM wiki" shape into a format exchangeable between
organizations.

The T2AG main repository is already markdown + frontmatter + mutual references, so the technical
difficulty of adapting is close to zero. The real decision is not "how to convert" but **what to
convert**: one tree in the main repository mixes two kinds of content with opposite natures —

- **Mechanism**: the constitution, the domain model, the playbooks, the tool documentation. They describe
  how the system runs and contain no personal fact.
- **Instance**: the student profile, learning progress, the activity ledger, mistakes, teaching
  transcripts, logs, the cloud channel.

And OKF exists in order to exchange. The moment the exporter can render the instance layer, only one
command separates "a private repository" from "a directory ready to be packaged and sent out"; and a
bundle is a **flattened copy** — in the main repository `progress.md` is the sole authority, while in the
bundle it becomes a second copy with no lifecycle management. That is the classic new attack surface of
introducing an outward interface, not a format-conversion problem.

## Decision (the user's four consecutive adjudications, 2026-08-09)

1. **The substance of the adaptation is behaviour, not a script**. The canonical is the core-playbook
   `main/50_playbook/okf_adaptation.md`, shipped with the Skeleton; `main/70_tools/okf_export.py` is its
   recomputable implementation. When the two conflict, the playbook governs and the tool gets fixed.
   Why: prose with no machine landing point is exactly the hole-producing layer the 2026-08-08 full audit
   named (the same as EV-0016/0018's "a claim must have a landing a machine can reach"); conversely, a
   script with no specification leaves nowhere to edit when the OKF version is upgraded.
2. **The scope is a directory-level positive-enumeration allowlist**, with only two tiers, `mechanism`
   and `course:<COURSE_ID>`.
   **No scope exporting the personal layer is implemented** — the personal layer has no reachable code
   path. The boundary is guaranteed by **absence**, not by a switch: a defence of the "remember not to
   pass that flag" kind is a procedural defence, exactly the weak layer the audit named.
3. **Never fabricate trust**. `verified` is never written anywhere: a doctor pass or a test pass is only
   a structural verification, not evidence that someone read the content. OKF's three trust tiers
   (unverified / machine-confirmed / human-reviewed) work through field absence, and inventing one
   collapses three tiers into one, letting a downstream reader believe somebody endorsed it. The same
   applies to `stale_after`.
4. **The leak gate sits before the write to disk**; on a hit it writes nothing and **cannot be
   exempted**. The word list has a single source,
   `t2ag_doctor.SKELETON_PRIVACY_PATTERNS`, and if the list cannot be obtained the export is refused
   rather than degraded.
   When a personal trace appears in the mechanism layer, the correct response is to redact the main
   repository, not to add an exporter allowlist — an exemption list hollows the gate out (the same-family
   lesson as P-0065 / P-0067).
5. **A backtick reference is promoted to a link**. T2AG prose references files with inline backticks,
   and measured across the mechanism layer, of 1266 references markdown links number 0. OKF's graph
   structure is expressed entirely through links, so without promotion the "knowledge bundle" degrades
   into a "folder", and precisely the whole value of OKF over an ordinary wiki is lost. Promotion is
   limited to "the first occurrence of each target per file" and only for targets inside the bundle.
6. **Not registered in the doctor runtime**. A bundle is an optional artifact, and its absence or
   staleness must not FAIL that day's teaching (the same as `t2ag.md` §3.2, "a release problem does not
   block teaching"). Self-checking goes through the explicit `--check-bundle` command.

## Consequences

**Gained**: the main repository gets an outward face in a standard format, so any agent or tool that
knows OKF can read its mechanism layer without knowing T2AG; the open-source display surface is upgraded
from "a directory convention" to "an exchangeable package in an industry format"; and deleting the whole
bundle directory rolls it back completely, with zero change to the main repository.

**Given up**: there is no one-command export of the personal learning history for a local tool to
consume — that needs its own work order, which must independently answer three questions: the landing
point, the retention period, and the packaging accident surface. This is deliberate: leaving the question
until there is a real use case is safer than building a switchable capability now.

**A new maintenance obligation**: OKF is a young specification (v0.1→v0.2 already changed two things,
`timestamp`→`generated.at` and the body `# Citations`→frontmatter `sources`). A specification upgrade
changes only the playbook's mapping table, the tool follows the table, and the changelog must record
"target version x.y → x.z, and which rows of the table changed"; silently following a new version is not
allowed.

**Known residual risks**: promotion may treat a filename literal that is not a reference as an edge (the
error direction is one extra edge, never lost content); and a `course:<ID>` scope may still be stopped by
the gate because the course definition names a real institution — that is correct behaviour, and the
right response when it is stopped is to admit the course definition carries an instance-identifying
surface, not to grant an exemption.

## Portability

This decision does not depend on T2AG's directory numbering or object model; it applies to any personal
knowledge system that "mixes mechanism and personal data in one tree and wants to publish the mechanism
layer". Three things carry over: **an allowlist rather than a blocklist**, **the gate before the write to
disk and not exemptible**, and **a trust field omitted rather than overstated**.
