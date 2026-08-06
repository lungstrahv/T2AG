# T2AG Architecture Decision Records

**Owner**: portable architecture decisions for T2AG  
**Lifecycle owner**: Evolution Register (`main/60_journal/t2ag_evolution_register.md`)  
**Not**: a second decision state machine

## What belongs here

Only decisions that are:

- cross-module or hard to reverse;
- change responsibility / trust boundaries; or
- worth reusing across projects.

Most Evolution Register entries never become an ADR.

## Metadata (required for new ADRs)

Use YAML frontmatter (or an equivalent first-block metadata form):

```yaml
---
adr_id: ADR-0001
portable_key: textbook-source-assets-and-bounded-cache
status: proposed | accepted | superseded
authority_project: T2AG
source_evolution: [EV-0012]
supersedes: []
implementation_refs: []
---
```

| Field | Rule |
|---|---|
| `adr_id` | Local identity `ADR-NNNN` |
| `portable_key` | Stable cross-project semantic key; unique in this repo |
| `status` | `proposed` \| `accepted` \| `superseded` |
| `source_evolution` | Local EV ids that own lifecycle for this decision |
| `supersedes` | Other ADR ids; must exist and form no cycle |
| `implementation_refs` | Optional paths / protocols / tools |

### Status mapping to Evolution Register

| ADR status | Register EV requirement |
|---|---|
| `proposed` | May point at `discussing` (or decided) architecture EVs |
| `accepted` | Must include ≥1 local `decided` or `archived` architecture EV |
| `superseded` | Keep history; superseding ADR must list this id |

**Accepted ≠ implemented.** Implementation continues via EV, changelog, version state, and live protocols.

## Reuse / adoption in another project

```yaml
origin:
  project: T2AG
  adr_id: ADR-0001
  portable_key: textbook-source-assets-and-bounded-cache
local_adoption_evolution: EV-XXXX
```

## Index

| ADR | portable_key | status | source_evolution |
|---|---|---|---|
| [0001](./0001-textbook-source-assets-and-bounded-cache.md) | textbook-source-assets-and-bounded-cache | accepted | EV-0012 |
| [0002](./0002-host-controlled-textbook-teaching-egress.md) | host-controlled-textbook-teaching-egress | proposed | EV-0013 |

Superseded filename stub: [0002-teaching-admission-capability-gate.md](./0002-teaching-admission-capability-gate.md) (redirect only; not a second decision).

## Validation

Deterministic checks live in `main/70_tools/decision_record_contract.py` and runtime Doctor
`runtime.decision_records`. They verify IDs, links, status compatibility, portable_key
uniqueness, supersedes closure, and redirect integrity — not whether a decision “deserves”
an ADR.
