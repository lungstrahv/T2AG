#!/usr/bin/env python3
"""Pure validation for Evolution Register ↔ ADR linkage.

No CLI. Called by Doctor and unit tests. Does not judge whether a decision
"deserves" an ADR — only deterministic structural facts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


EV_HEADING_RE = re.compile(r"^###\s+(EV-\d{4})\s*[|｜]")
EV_ID_LINE_RE = re.compile(r"^\s*-\s*\*\*ID\*\*\s*[：:]\s*(EV-\d{4})\b", re.I)
STATUS_RE = re.compile(
    r"^\s*-\s*\*\*状态\*\*\s*[：:]\s*`?(observing|discussing|decided|archived)`?",
    re.I,
)
DECISION_CLASS_RE = re.compile(
    r"^\s*-\s*\*\*decision_class\*\*\s*[：:]\s*`?(observation|architecture|implementation|policy)`?",
    re.I,
)
ADR_REFS_RE = re.compile(r"^\s*-\s*\*\*adr_refs\*\*\s*[：:]\s*(.+)$", re.I)
ADR_EXCEPTION_RE = re.compile(r"^\s*-\s*\*\*adr_exception\*\*\s*[：:]\s*(.+)$", re.I)
ADR_TOKEN_RE = re.compile(r"ADR-\d{4}")
EV_TOKEN_RE = re.compile(r"EV-\d{4}")

REGISTER_REL = "main/60_journal/t2ag_evolution_register.md"
REDIRECT_REL = "main/60_journal/t2ag_evolution.md"
ADR_DIR_REL = "docs/adr"


@dataclass
class EvolutionEntry:
    ev_id: str
    status: str
    decision_class: str | None = None
    adr_refs: list[str] = field(default_factory=list)
    adr_exception: str | None = None
    has_metadata_block: bool = False


@dataclass
class AdrRecord:
    path: Path
    adr_id: str
    portable_key: str
    status: str
    source_evolution: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    is_redirect_stub: bool = False


def _parse_frontmatter(text: str) -> dict[str, object]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, object] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        value = raw.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                meta[key] = []
            else:
                meta[key] = [
                    part.strip().strip("'\"")
                    for part in inner.split(",")
                    if part.strip()
                ]
        else:
            meta[key] = value.strip("'\"")
    return meta


def parse_evolution_register(text: str) -> list[EvolutionEntry]:
    entries: list[EvolutionEntry] = []
    current: EvolutionEntry | None = None
    for line in text.splitlines():
        head = EV_HEADING_RE.match(line)
        if head:
            if current:
                entries.append(current)
            current = EvolutionEntry(ev_id=head.group(1), status="")
            continue
        if current is None:
            continue
        id_line = EV_ID_LINE_RE.match(line)
        if id_line:
            current.ev_id = id_line.group(1)
            continue
        st = STATUS_RE.match(line)
        if st:
            current.status = st.group(1).lower()
            current.has_metadata_block = True
            continue
        dc = DECISION_CLASS_RE.match(line)
        if dc:
            current.decision_class = dc.group(1).lower()
            current.has_metadata_block = True
            continue
        ar = ADR_REFS_RE.match(line)
        if ar:
            current.adr_refs = ADR_TOKEN_RE.findall(ar.group(1))
            current.has_metadata_block = True
            continue
        ex = ADR_EXCEPTION_RE.match(line)
        if ex:
            current.adr_exception = ex.group(1).strip()
            current.has_metadata_block = True
            continue
    if current:
        entries.append(current)
    return entries


def parse_adr_file(path: Path) -> AdrRecord | None:
    text = path.read_text(encoding="utf-8")
    meta = _parse_frontmatter(text)
    # redirect / superseded filename stubs without full metadata
    if "superseded filename" in text[:400].lower() or (
        "status: superseded" in text[:200].lower() and "redirect" in text[:600].lower()
    ):
        # stub: do not treat as active ADR unless adr_id present
        if "adr_id" not in meta:
            return AdrRecord(
                path=path,
                adr_id=path.stem.split("-")[0].upper().replace("0002", "ADR-0002")
                if path.name.startswith("0002-teaching")
                else path.stem,
                portable_key="",
                status="redirect_stub",
                is_redirect_stub=True,
            )
    if "adr_id" not in meta:
        # legacy body-only ADR: try heading
        m = re.search(r"^#\s+(ADR-\d{4})\b", text, re.M)
        if not m:
            return None
        status_m = re.search(r"\*\*Status:\*\*\s*(\w+)", text)
        return AdrRecord(
            path=path,
            adr_id=m.group(1),
            portable_key="",
            status=(status_m.group(1).lower() if status_m else "unknown"),
            source_evolution=EV_TOKEN_RE.findall(text[:800]),
        )
    src = meta.get("source_evolution") or []
    if isinstance(src, str):
        src = EV_TOKEN_RE.findall(src)
    sup = meta.get("supersedes") or []
    if isinstance(sup, str):
        sup = ADR_TOKEN_RE.findall(sup)
    return AdrRecord(
        path=path,
        adr_id=str(meta["adr_id"]),
        portable_key=str(meta.get("portable_key") or ""),
        status=str(meta.get("status") or "").lower(),
        source_evolution=list(src),
        supersedes=list(sup),
    )


def load_adrs(root: Path) -> list[AdrRecord]:
    adr_dir = root / ADR_DIR_REL
    if not adr_dir.is_dir():
        return []
    records: list[AdrRecord] = []
    for path in sorted(adr_dir.glob("*.md")):
        if path.name.upper() == "README.MD":
            continue
        parsed = parse_adr_file(path)
        if parsed is not None:
            records.append(parsed)
    return records


def validate_redirect(root: Path) -> list[str]:
    errors: list[str] = []
    redirect = root / REDIRECT_REL
    canonical = root / REGISTER_REL
    if not canonical.is_file():
        errors.append(f"missing Evolution Register canonical: {REGISTER_REL}")
    if not redirect.is_file():
        errors.append(f"missing Evolution Register redirect: {REDIRECT_REL}")
        return errors
    text = redirect.read_text(encoding="utf-8")
    if "t2ag_evolution_register.md" not in text:
        errors.append("redirect does not point at t2ag_evolution_register.md")
    if "journal_index" not in text.lower() or "false" not in text.lower():
        errors.append("redirect missing journal_index: false marker")
    # redirect must not contain full EV bodies
    if len(EV_HEADING_RE.findall(text)) > 0:
        errors.append("redirect must not contain EV entry bodies")
    return errors


def _supersedes_cycle(adrs: dict[str, AdrRecord]) -> list[str]:
    errors: list[str] = []
    for start in adrs:
        seen: list[str] = []
        cur = start
        while cur in adrs and adrs[cur].supersedes:
            if cur in seen:
                errors.append(f"supersedes cycle involving {cur}")
                break
            seen.append(cur)
            nxt = adrs[cur].supersedes[0] if adrs[cur].supersedes else ""
            if not nxt:
                break
            if nxt not in adrs:
                errors.append(f"supersedes target missing: {cur} -> {nxt}")
                break
            cur = nxt
    return errors


def register_is_instance_fresh(root: Path) -> bool:
    """True when the local Evolution Register holds no EV records at all.

    EV-0023 clears the register on the release surface, so every EV token in
    shipped prose is maintainer provenance rather than a locally resolvable
    record. Keying the exemption on `flavor == "skeleton"` alone broke the first
    thing a real user does: `t2ag_init.py init` flips the flavor to `main`, and
    the freshly generated instance then reported ~30 dangling EV citations it had
    no way to fix. A *cleared* register is the honest signal; a *partially*
    populated one still means drift and stays strict.
    """
    register_path = root / REGISTER_REL
    if not register_path.is_file():
        return True
    return not parse_evolution_register(register_path.read_text(encoding="utf-8"))


def ev_linkage_is_exempt(root: Path, flavor: str) -> bool:
    return flavor == "skeleton" or register_is_instance_fresh(root)


def validate_decision_records(root: Path, flavor: str = "main") -> list[str]:
    """Return human-readable FAIL messages (empty = pass).

    EV linkage is skipped when the local register is instance-fresh (EV-0023):
    EV references in ADR frontmatter are then provenance annotations pointing at
    the maintainer's register and are never locally resolvable. ADR file
    integrity checks always apply. See `register_is_instance_fresh`.
    """
    errors: list[str] = []
    errors.extend(validate_redirect(root))

    register_path = root / REGISTER_REL
    if not register_path.is_file():
        return errors

    entries = parse_evolution_register(register_path.read_text(encoding="utf-8"))
    by_ev = {e.ev_id: e for e in entries}
    if len(by_ev) != len(entries):
        errors.append("duplicate EV ids in Evolution Register")

    adrs = [a for a in load_adrs(root) if not a.is_redirect_stub]
    by_adr = {a.adr_id: a for a in adrs}
    if len(by_adr) != len(adrs):
        errors.append("duplicate ADR ids among active ADR files")

    # portable_key uniqueness (non-empty)
    keys: dict[str, str] = {}
    for adr in adrs:
        if not adr.portable_key:
            continue
        if adr.portable_key in keys:
            errors.append(
                f"duplicate portable_key {adr.portable_key!r}: "
                f"{keys[adr.portable_key]} and {adr.adr_id}"
            )
        else:
            keys[adr.portable_key] = adr.adr_id

    errors.extend(_supersedes_cycle(by_adr))

    ev_exempt = ev_linkage_is_exempt(root, flavor)
    for adr in adrs:
        if not ev_exempt:
            for ev_id in adr.source_evolution:
                if ev_id not in by_ev:
                    errors.append(f"dangling ADR→EV: {adr.adr_id} -> {ev_id}")
                    continue
                ev = by_ev[ev_id]
                if adr.status == "accepted" and ev.status not in {"decided", "archived"}:
                    errors.append(
                        f"accepted ADR {adr.adr_id} points at non-decided EV {ev_id} "
                        f"(status={ev.status})"
                    )
                if adr.status == "proposed" and ev.status not in {
                    "discussing",
                    "decided",
                    "archived",
                    "observing",
                }:
                    errors.append(
                        f"proposed ADR {adr.adr_id} has incompatible EV status {ev.status}"
                    )
        if adr.status == "accepted" and not adr.source_evolution:
            errors.append(f"accepted ADR {adr.adr_id} missing source_evolution")

    for ev in entries:
        for adr_id in ev.adr_refs:
            if adr_id not in by_adr:
                # allow pointer to redirect stub ADR-0002 filename? only active metadata ADRs
                if not any(a.adr_id == adr_id for a in load_adrs(root)):
                    errors.append(f"dangling EV→ADR: {ev.ev_id} -> {adr_id}")
        # architecture + decided/archived must have adr_refs unless exception
        # Only enforce when decision_class is present (legacy without class stays valid)
        if (
            ev.decision_class == "architecture"
            and ev.status in {"decided", "archived"}
            and not ev.adr_refs
            and not ev.adr_exception
        ):
            errors.append(
                f"architecture EV {ev.ev_id} ({ev.status}) missing adr_refs "
                "and adr_exception"
            )
        # bidirectional soft check: if EV lists ADR, ADR should list EV when metadata present
        for adr_id in ev.adr_refs:
            adr = by_adr.get(adr_id)
            if adr is None:
                continue
            if adr.source_evolution and ev.ev_id not in adr.source_evolution:
                errors.append(
                    f"EV {ev.ev_id} refs {adr_id} but ADR source_evolution "
                    f"omits {ev.ev_id}"
                )

    return errors


# Live normative prose whose ADR/EV citations must resolve.  Historical
# append-only documents (changelog, problemlog, journal, handoffs, memory)
# legitimately cite retired or external records and are deliberately out of
# scope: the carrier of this guarantee is live normative text only — a guard
# whose scope is wider than its claim is the carrier_mismatch family
# (remediation_governance.md §七).
CITATION_SURFACE_FILES = (
    "main/t2ag.md",
    "AGENTS.md",
    "README.md",
)
# Widened by the 2026-08-09 re-review: an ADR body and docs/protocol are current specifications just as
# much as anything else, but were outside the scan surface, so a dangling ADR reference in them read as
# false green (independent re-review P2). They were included after a pre-check found zero dangling
# references in both repositories.
CITATION_SURFACE_GLOBS = (
    "main/50_playbook/*.md",
    "docs/adr/*.md",
    "docs/protocol/*.md",
)


def validate_decision_citations(root: Path, flavor: str = "main") -> list[str]:
    """ADR/EV tokens cited by live normative prose must name real records.

    ADR citations must always resolve (ADRs are portable and ship with the
    distribution). EV citations are maintainer provenance annotations and are
    exempt whenever the local register is instance-fresh (EV-0023) — see
    `register_is_instance_fresh` for why this is not keyed on flavor alone.
    """
    errors: list[str] = []
    adrs = {a.adr_id for a in load_adrs(root)}
    evs: set[str] = set()
    ev_exempt = ev_linkage_is_exempt(root, flavor)
    register_path = root / REGISTER_REL
    if not ev_exempt and register_path.is_file():
        evs = {
            e.ev_id
            for e in parse_evolution_register(
                register_path.read_text(encoding="utf-8")
            )
        }
    targets: list[Path] = []
    for rel in CITATION_SURFACE_FILES:
        path = root / rel
        if path.is_file():
            targets.append(path)
    for pattern in CITATION_SURFACE_GLOBS:
        targets.extend(sorted(root.glob(pattern)))
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        for token in sorted(set(ADR_TOKEN_RE.findall(text))):
            if token not in adrs:
                errors.append(f"dangling citation: {rel} references a non-existent {token}")
        if ev_exempt:
            continue
        for token in sorted(set(EV_TOKEN_RE.findall(text))):
            if token not in evs:
                errors.append(f"dangling citation: {rel} references a non-existent {token}")
    return errors


def validate_decision_records_as_report(
    root: Path, flavor: str = "main"
) -> Iterable[tuple[str, str]]:
    for message in validate_decision_records(root, flavor):
        yield ("FAIL", message)
