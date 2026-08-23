# T2AG Evolution Register (t2ag_evolution_register.md)

> **Function**: the decision-lifecycle register of **this instance** — it records this instance's observations, discussions, decisions, and implementation archives.
> **Protection level**: journal (a review layer, not a source of truth)
> **Created**: the instance-zeroed template (EV-0023, 2026-08-09)
> **Maintenance rule**: adding an observation entry requires the user to ask for it explicitly; nothing is written automatically.
> **Relation to ADRs**: this file owns the `observing → discussing → decided → archived` lifecycle;
> an ADR (`docs/adr/`) is a portable architectural-decision artifact that does not copy the state machine and must point back to this Register in both directions.

---

## Note on instance zeroing (EV-0023)

This file is **zeroed** with each release: the maintainer project's decision archive (every entry from
EV-0001 onward) stays in the maintainer's repository and is not this instance's history — **this
instance is a fresh start at the current schema and does not inherit the maintainer's birth history**.

- This instance's own decisions are registered starting at **EV-0001**.
- An EV-NNNN reference appearing in this repository's body text (the constitution, a playbook, an ADR) is
  **a provenance note about a maintainer decision**, not a pointer to an entry in this file; doctor
  exempts this instance from the EV link check, but an ADR reference must really exist.
- The entry format, the boundary notes, and the promotion criterion for "not every EV produces an ADR"
  are the same as the maintainer repository's canonical
  (`docs/adr/README.md`, with the parser in `main/70_tools/decision_record_contract.py` as the contract).
