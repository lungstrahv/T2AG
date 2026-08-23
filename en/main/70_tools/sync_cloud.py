#!/usr/bin/env python3
"""The T2AG cloud prompt generator (EV-0021 / ADR-0004: protocol/instance separation).

Design (following the three adjudications of 2026-08-09: route B, the skeleton as the only open-source
surface, and reply_suffix recording the mechanism but not the value):
- `cloud/T2AG_PROJECT_INSTRUCTIONS.txt` is a generated artifact, not a source of truth.
- The source of truth for protocol content: `main/50_playbook/cloud_instructions_template.md`
  (covered by parity, with zero instance values).
- The source of truth for instance values: the five fields of `cloud/t2ag_mobile_entry.md`
  （cloud_project_mode / course / teacher_role / teacher_template / reply_suffix）。
- Template leak self-check: any instance value appearing literally in the template is a FAIL — the
  template and the skeleton never contain the value of the anti-impersonation end-of-message marker.
- This tool reads only the template and mobile_entry and writes only the instructions; it never touches
  the ledger, the channel archive, or the skeleton.
- A skeleton or an uninstantiated repository (no mobile_entry) has nothing to generate, so the check
  passes directly.

Usage:
  python main/70_tools/sync_cloud.py            # check-only: regenerate and compare, writing nothing
  python main/70_tools/sync_cloud.py --write    # regenerate and write the instructions back

Doctor integration: `check_cloud_contract` calls `run_checks(root)` and reports drift as a FAIL.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TEMPLATE_REL = "main/50_playbook/cloud_instructions_template.md"
ENTRY_REL = "cloud/t2ag_mobile_entry.md"
OUTPUT_REL = "cloud/T2AG_PROJECT_INSTRUCTIONS.txt"
BODY_MARKER = "<!-- T2AG_TEMPLATE_BODY_START -->\n"

INSTANCE_FIELDS = (
    "cloud_project_mode",
    "course",
    "teacher_role",
    "teacher_template",
    "reply_suffix",
)
PLACEHOLDER_RE = re.compile(r"\{\{([a-z_]+)\}\}")

# The leak scan covers instance-identifying values only. `cloud_project_mode` is a protocol mode
# enumeration (personal_instance / generic_skeleton) that legitimately appears in protocol prose and is
# not a secret.
LEAK_FIELDS = ("course", "teacher_role", "teacher_template", "reply_suffix")


class SyncCloudError(RuntimeError):
    pass


def parse_mobile_entry(text: str) -> dict[str, str]:
    """Extract the instance fields. Format: `- field: value` (tolerated inside or outside a GENERATED block)."""
    values: dict[str, str] = {}
    for field in INSTANCE_FIELDS:
        m = re.search(rf"^-\s*{field}:\s*(\S+)\s*$", text, re.MULTILINE)
        if m:
            values[field] = m.group(1)
    missing = [f for f in INSTANCE_FIELDS if f not in values]
    if missing:
        raise SyncCloudError(f"mobile_entry lacks instance fields: {missing}")
    return values


def template_body(text: str) -> str:
    if BODY_MARKER not in text:
        raise SyncCloudError(f"the template lacks the generation-body marker {BODY_MARKER.strip()}")
    return text.split(BODY_MARKER, 1)[1]


def leak_scan(template_text: str, values: dict[str, str]) -> list[str]:
    """No instance value may appear literally in the template (the protocol layer records the mechanism, not the value)."""
    leaks = []
    for field in LEAK_FIELDS:
        value = values.get(field, "")
        if value and value in template_text:
            leaks.append(f"{field}={value}")
    return leaks


def render(body: str, values: dict[str, str]) -> str:
    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            raise SyncCloudError(f"a template placeholder has no matching instance field: {{{{{key}}}}}")
        return values[key]

    rendered = PLACEHOLDER_RE.sub(sub, body)
    leftover = PLACEHOLDER_RE.findall(rendered)
    if leftover:
        raise SyncCloudError(f"placeholders remain unresolved after rendering: {leftover}")
    return rendered


def expected_instructions(root: Path) -> str:
    template_text = (root / TEMPLATE_REL).read_text(encoding="utf-8")
    entry_text = (root / ENTRY_REL).read_text(encoding="utf-8")
    values = parse_mobile_entry(entry_text)
    leaks = leak_scan(template_text, values)
    if leaks:
        raise SyncCloudError(f"the template leaks instance values: {leaks}")
    return render(template_body(template_text), values)


def run_checks(root: Path) -> list[tuple[str, str]]:
    """Return a list of (level, message); level ∈ FAIL / WARN / INFO. Reused by doctor."""
    reports: list[tuple[str, str]] = []
    entry = root / ENTRY_REL
    template = root / TEMPLATE_REL
    output = root / OUTPUT_REL
    if not entry.exists():
        reports.append(("INFO", "sync_cloud: no mobile_entry (skeleton/uninstantiated); nothing to generate"))
        return reports
    if not template.exists():
        reports.append(("FAIL", f"sync_cloud: the template is missing: {TEMPLATE_REL}"))
        return reports
    try:
        expected = expected_instructions(root)
    except SyncCloudError as exc:
        reports.append(("FAIL", f"sync_cloud: {exc}"))
        return reports
    if not output.exists():
        reports.append(("FAIL", f"sync_cloud: the generated artifact is missing: {OUTPUT_REL} (run --write to regenerate)"))
        return reports
    actual = output.read_text(encoding="utf-8")
    if actual != expected:
        diff = list(
            difflib.unified_diff(
                expected.splitlines(), actual.splitlines(),
                "expected(template+entry)", "on-disk", lineterm="", n=0,
            )
        )
        head = "; ".join(diff[2:8])
        reports.append(("FAIL", f"sync_cloud: the instructions drift from the template regeneration ({len(diff)} diff lines): {head}"))
    else:
        reports.append(("INFO", "sync_cloud: the instructions match the template + mobile_entry regeneration"))
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="regenerate and write the instructions back")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.write:
        entry = root / ENTRY_REL
        if not entry.exists():
            print("FAIL sync_cloud: no mobile_entry; refusing to generate in a skeleton/uninstantiated repository")
            return 1
        try:
            expected = expected_instructions(root)
        except SyncCloudError as exc:
            print(f"FAIL sync_cloud: {exc}")
            return 1
        out = root / OUTPUT_REL
        old = out.read_text(encoding="utf-8") if out.exists() else None
        out.write_text(expected, encoding="utf-8")
        print(f"WROTE {OUTPUT_REL} ({'unchanged' if old == expected else 'updated'})")
        return 0

    worst = 0
    for level, message in run_checks(root):
        print(f"{level} {message}")
        if level == "FAIL":
            worst = 1
    return worst


if __name__ == "__main__":
    sys.exit(main())
