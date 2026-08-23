# Cross-repository reference management (the two tiers)

**Protection level**: playbook

> This file is one of T2AG's "skill consolidation" documents.
> Triggered when any T2AG file needs to reference a repository/system outside this one (a trading review system, a reading-assistance system, or another peer repository),
> or when an existing out-of-repository reference is found with no contract protecting it.
>
> **Applies to**: an engagement mounting an out-of-repository authority, a course referencing out-of-repository data, evaluating a new external system's integration,
> handling a broken link or drift in an out-of-repository file, and a binding version upgrade (rebinding).
>
> **Related files**:
> - The contract schema: `main/70_tools/contracts/external_reference_v1/t2ag.external_reference.v1.schema.json`
> - The full-bridge example: `docs/design/T2AG_READING_BRIDGE_CONTRACT_V1.md` (the saga tier)
> - The first instance: `main/10_student/engagements/EG-0001_TradingDiscipline/external_refs.json`
> - Provenance: `main/00_core/t2ag_problemlog.md` P-0060
>
> **Adjudication memory** (the user's adjudication, 2026-08-08): the directory layering of an external repository is that repository's domain semantics, and **the peer repository is never rebuilt for directory aesthetics**;
> T2AG only aligns the interface method and the discoverability of governance files.

---

## 1. The two tiers (assign the tier before building anything)

| Tier | Applies to | Carrier | Forbidden |
|---|---|---|---|
| **T1 reference contract** | a one-way read-only reference to an out-of-repository file (an authoritative document, a data source) | `external_refs.json` in the referring directory (`t2ag.external_reference.v1`) | building transport schemas, ledgers, receipts, or other consumerless facilities in a T1 situation |
| **T2 saga full bridge** | two-way data exchange (candidate contributions flowing back, receipts) | three contracts in the reading_bridge_v1 style + byte-identical schema copies in both repositories | using it in a read-only situation; promoting a tier requires a real backflow need as evidence |

**The tiering criterion**: does the peer need to receive T2AG output? No → T1. Yes → first confirm the
backflow need is real
(a concrete consumer, a concrete triggering event), then set up T2 following the reading-bridge pattern.
**A bare reference with no contract at all is the only forbidden shape** (P-0060's original sin).

---

## 2. Hard rules for a T1 contract

1. **An absolute path may appear only in `peer_root_hints`**. Body text, frontmatter, and tables all use
   the logical name (`external_refs.json#<reference_id>`) or a path relative to the peer repository.
   Reference identity = `peer_system` + `peer_relative_path`; a root hint is only an environment
   resolution hint.
2. **frozen_version (an authoritative document)**: must be `pinned` + `content_sha256` + `peer_version`.
   The SHA is computed from the real file (`sha256sum`); filling it in by hand or reciting it from
   memory is forbidden.
3. **living_data (live data)**: must be `existence_only` + `copy_on_use`. Do not pin a SHA — pinning a
   SHA on a live file only manufactures a permanent false alarm.
4. **copy_on_use**: whenever a T2AG file references specific content inside live data, copy the lines or
   passage used verbatim into this repository's evidence, together with that day's source file `sha256`
   and the date. Leaving only a line number, "see the ledger", or any other live reference is forbidden —
   six months later, the evidence must still look the way it did at the time.
5. **Rebinding is manual only** (`rebind: manual_only`): doctor reporting drift ≠ updating the SHA
   automatically.
   After confirming the peer's new version by hand, update `content_sha256` + `peer_version` +
   `bound_at` in one commit, and leave a version-change line in the referring file. Where the peer has a
   cooling-off clause (Trading-OS's 7-day cooling-off for relaxing changes, say), verify the cooling-off
   period has elapsed before rebinding.

---

## 3. Steps for adding an out-of-repository reference

1. Assign the tier (§1). T2 → follow the reading-bridge pattern, which this file does not cover.
2. Create or append `external_refs.json` in the referring directory, filling in every field per the schema.
3. Compute the pinned file's SHA for real with `sha256sum`; confirm the living_data file exists.
4. Change every out-of-repository mention in the referring body text to a logical name or a peer-relative
   path; re-check that directory with `grep -rn "C:/Users"`, and the hit count should be 0 (the sidecar
   excepted).
5. Run doctor's `external_references` check and confirm 0 FAIL.
6. Register it in the changelog (a new reference = a structural change).

## 4. Handling a broken link or drift

| doctor result | Meaning | Handling |
|---|---|---|
| FAIL: root unreachable / file missing / sidecar corrupt | broken link | fix the resolution first (the peer moved → change only `peer_root_hints`) and leave the reference identity alone |
| WARN: pinned SHA mismatch | the peer has been revised; the binding is stale | read what the peer changed → decide by hand whether to rebind (§2.5) or revert the peer's mistaken change |
| PASS | the binding is healthy | no action |

---

## 5. Common pitfalls

- Hunting down absolute paths in historical archives (`60_journal/` and the like) — an archive is the fact
  of its time and is not edited.
- Pinning living_data — every peer append raises a false alarm, and the end state is alarm fatigue.
- After a WARN, writing the new SHA back into the sidecar "to make the check green" — that is automatic
  synchronization and destroys explicit-rebind semantics; drift requires looking at what the peer changed
  first.
- Pre-building T2 facilities for a T1 situation "because they will come in handy" — infrastructure with
  no traffic rots (the reading bridge's batches C/R/T, built and then left with no real writes for a long
  time, are the precedent); the condition for promoting a tier is a real backflow need appearing.
