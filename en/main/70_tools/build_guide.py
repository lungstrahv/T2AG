#!/usr/bin/env python3
"""T2AG directory guide fragment injector (零依赖).

Reads the *local* edition tree (this script's repo root) and injects into
t2ag_directory_guide.html between T2AG_GENERATED anchors.

- preface: from the authoritative `## 序` section in main/t2ag.md
- directory_map: from main/t2ag.md domain metadata + local index/README files
- flow_first_run / flow_panorama: from main/50_playbook/t2ag_flow.md FLOW markers

FLOW extraction uses line-anchored HTML comments only
  ^<!-- FLOW:name -->$ … ^<!-- /FLOW:name -->$
so prose examples containing FLOW:xxx are ignored.

Usage (cwd or any path inside edition):
  python main/70_tools/build_guide.py              # check only
  python main/70_tools/build_guide.py --write      # explicit write
  python main/70_tools/build_guide.py --write --root <本仓绝对路径>
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # edition root (…/t2ag)
MAIN = ROOT / "main"
FLOW_MD = MAIN / "50_playbook" / "t2ag_flow.md"
GUIDE_HTML = ROOT / "t2ag_directory_guide.html"

# True FLOW open/close (line-anchored); never match prose `FLOW:xxx`
_FLOW_OPEN = re.compile(r"^<!-- FLOW:([a-z0-9_]+) -->\s*$")
_FLOW_CLOSE = re.compile(r"^<!-- /FLOW:([a-z0-9_]+) -->\s*$")

_GEN_BLOCK = re.compile(
    r"(<!-- T2AG_GENERATED:([a-z0-9_]+) -->)(.*?)(<!-- /T2AG_GENERATED:\2 -->)",
    re.DOTALL,
)

# HTML anchor name → FLOW id in t2ag_flow.md
FLOW_ANCHORS = {
    "flow_first_run": "first_run",
    "flow_panorama": "panorama",
}
FLOW_ORDER = (
    "first_run", "panorama", "teaching_loop", "authority_chain", "cycles",
    "skin", "git", "batch", "exercise_loop",
)
FLOW_TITLES = {
    "first_run": "Diagram 0 - First run",
    "panorama": "Diagram 1 - One teaching session",
    "teaching_loop": "Diagram 1b - Main teaching loop",
    "authority_chain": "Diagram 2 - Authority chain",
    "cycles": "Diagram 3 - Cycle loops",
    "skin": "Diagram 5 - Skin system",
    "git": "Diagram 6 - Git workflow",
    "batch": "Diagram 7 - Batch remediation governance",
    "exercise_loop": "Diagram 8 - Exercise evidence loop",
}


def extract_flow_blocks(text: str) -> dict[str, str]:
    """Return {name: inner markdown of diagram block} for real FLOW markers."""
    lines = text.splitlines()
    blocks: dict[str, str] = {}
    i = 0
    while i < len(lines):
        m = _FLOW_OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        i += 1
        body: list[str] = []
        while i < len(lines):
            if _FLOW_CLOSE.match(lines[i]):
                cname = _FLOW_CLOSE.match(lines[i]).group(1)
                if cname != name:
                    raise SystemExit(
                        f"FLOW marker mismatch: open {name} close {cname}"
                    )
                blocks[name] = "\n".join(body).strip("\n")
                i += 1
                break
            body.append(lines[i])
            i += 1
        else:
            raise SystemExit(f"FLOW:{name} missing close marker")
    return blocks


def flow_body_to_html(body: str, flow_id: str) -> str:
    """Convert a FLOW body into offline HTML with source fallback."""
    body = body.strip()
    if re.match(r"^```mermaid\s*\n", body):
        # No renderer on the guide side any more: the hand-rolled SVG layout engine
        # was removed because Mermaid never delivered the reason it was adopted
        # (auto-tracking structure changes) and its output looked worse than text.
        # Failing loudly beats silently shipping an ugly diagram.
        raise SystemExit(
            f"FLOW:{flow_id} 使用了 ```mermaid；本文件统一用 ```text 字符图，"
            "见 50_playbook/t2ag_flow.md 顶部排版约定"
        )
    m2 = re.match(r"^```(?:text)?\s*\n(.*?)```\s*$", body, re.DOTALL)
    if m2:
        code = m2.group(1).rstrip("\n")
        return f"<pre class=\"flow-ascii\">{html.escape(code)}\n</pre>\n"
    return f"<pre class=\"flow-ascii\">{html.escape(body)}\n</pre>\n"


def _readme_blurb(readme: Path) -> str:
    if not readme.is_file():
        return "（无说明文件）"
    try:
        lines = readme.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "（无法读取）"
    for raw in lines[:20]:
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith("<!--"):
            continue
        s = s.lstrip(">").strip()
        if not s:
            continue
        # drop bold labels like **位置**
        s = re.sub(r"^\*\*[^*]+\*\*[：:]\s*", "", s)
        if "放什么" in s or "职能" in s:
            s = re.sub(r"^.*?[：:]\s*", "", s)
        if len(s) >= 4:
            return s[:100]
    return "（说明文件未提供用途摘要）"


def build_preface_html(main_dir: Path) -> str:
    """Render the authoritative student-written preface from main/t2ag.md."""
    constitution = main_dir / "t2ag.md"
    if not constitution.is_file():
        raise SystemExit("directory guide: missing authoritative main/t2ag.md")
    text = constitution.read_text(encoding="utf-8-sig", errors="replace")
    # LV-5 (2026-08-20): translated editions title this section "Preface".
    match = re.search(
        r"^##\s+(?:序|Preface)(?:\s+\[max\s+\d+\])?\s*$\n(.*?)(?=^##\s+1\.)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise SystemExit(
            "directory guide: main/t2ag.md lacks authoritative ## 序 / ## Preface"
        )

    paragraphs: list[str] = []
    current: list[str] = []
    discipline = ""
    for raw in match.group(1).splitlines():
        if raw.startswith(">"):
            content = raw[1:].lstrip()
            if not content:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue
            if content.startswith("**序言纪律**") or content.startswith(
                "**Preface discipline**"
            ):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                discipline = re.sub(
                    r"^\*\*(?:序言纪律|Preface discipline)\*\*[：:]\s*", "", content
                )
                continue
            current.append(content)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    if len(paragraphs) < 2 or not discipline:
        raise SystemExit("directory guide: preface prose or discipline is incomplete")

    lines = ['<div class="preface-copy">']
    for paragraph in paragraphs:
        cls = ' class="preface-signature"' if paragraph.lower().startswith("yours sincerely") else ""
        lines.append(f"<p{cls}>{html.escape(paragraph)}</p>")
    lines.extend(
        [
            "</div>",
            '<aside class="preface-discipline"><strong>Preface discipline</strong>',
            f"<span>{html.escape(discipline)}</span></aside>",
            "",
        ]
    )
    return "\n".join(lines)


def _domain_metadata(main_dir: Path) -> dict[str, str]:
    """Parse the authoritative nine-domain responsibility table in main/t2ag.md."""
    constitution = main_dir / "t2ag.md"
    if not constitution.is_file():
        raise SystemExit("directory guide: missing authoritative main/t2ag.md")
    text = constitution.read_text(encoding="utf-8-sig", errors="replace")
    rows = re.findall(
        r"^\|\s*`([^`]+?)/`\s*\|\s*(.+?)\s*\|\s*$",
        text,
        re.MULTILINE,
    )
    metadata = {name: responsibility.replace("`", "") for name, responsibility in rows}
    numbered = {name for name in metadata if re.fullmatch(r"\d\d_[a-z]+", name)}
    if len(numbered) != 9:
        raise SystemExit(
            "directory guide: main/t2ag.md must define exactly nine numbered domains"
        )
    return metadata


def _directory_authority(entry: Path, main_dir: Path) -> str:
    """Return the directory's own authority entry, or "" when it has none.

    Previously this fell back to `main/t2ag.md`, so six of eleven rows repeated
    the same path and the column carried no information. An empty string is the
    honest answer: the constitution governs the domain, the directory adds nothing.
    """
    for filename in ("_README.md", "README.md", "INDEX.md"):
        candidate = entry / filename
        if candidate.is_file():
            return candidate.relative_to(main_dir.parent).as_posix()
    return ""


def build_directory_map_html(main_dir: Path, cloud_dir: Path) -> str:
    """Build from actual directories and authoritative responsibility metadata."""
    rows: list[tuple[str, str, str]] = []
    if main_dir.is_dir():
        metadata = _domain_metadata(main_dir)
        for entry in sorted(main_dir.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            # skip non-structural noise
            if entry.name in {"__pycache__", "skin"}:
                continue
            rel = f"main/{entry.name}/"
            if entry.name in metadata:
                blurb = metadata[entry.name]
            elif entry.name == "bin":
                blurb = "T2AG command entry point"
            else:
                readme = next(
                    (
                        entry / filename
                        for filename in ("_README.md", "README.md", "INDEX.md")
                        if (entry / filename).is_file()
                    ),
                    None,
                )
                if readme is None:
                    raise SystemExit(
                        f"directory guide: main/{entry.name}/ lacks authoritative metadata"
                    )
                blurb = _readme_blurb(readme)
            auth = _directory_authority(entry, main_dir)
            rows.append((rel, blurb, auth))
    if cloud_dir.is_dir():
        cloud_readme = cloud_dir / "README.md"
        if not cloud_readme.is_file():
            raise SystemExit("directory guide: cloud/ lacks README.md authority")
        rows.append(
            (
                "cloud/",
                _readme_blurb(cloud_readme),
                "cloud/README.md",
            )
        )

    return _render_directory_tree(rows)


def _render_directory_tree(rows: list[tuple[str, str, str]]) -> str:
    """Render the directory map as one character tree, matching the flow diagrams.

    A flat three-column table could not show nesting -- the one thing a reader
    opens this section for -- and its third column was mostly a repeated echo of
    the constitution. The tree is generated from the real filesystem on every
    build, so a structural change tracks itself; only the flow diagrams stay hand
    written, because they encode intent rather than layout.
    """
    main_rows = [row for row in rows if row[0].startswith("main/")]
    other_rows = [row for row in rows if not row[0].startswith("main/")]
    names = [row[0].split("/")[1] for row in main_rows]
    names += [row[0].rstrip("/") for row in other_rows]
    width = max((len(name) for name in names), default=0) + 1

    body: list[str] = []

    def emit(prefix: str, name: str, blurb: str, auth: str) -> None:
        label = f"{name}/".ljust(width)
        body.append(f"{prefix}{label}  {blurb}".rstrip())
        if auth:
            body.append(f"{' ' * (len(prefix) + width + 2)}authority {auth}")

    if main_rows:
        body.append("main/   the instance itself")
        for index, (rel, blurb, auth) in enumerate(main_rows):
            connector = "└─ " if index == len(main_rows) - 1 else "├─ "
            emit(connector, rel.split("/")[1], blurb, auth)
    for rel, blurb, auth in other_rows:
        body.append("")
        emit("", rel.rstrip("/"), blurb, auth)

    escaped = "\n".join(html.escape(line) for line in body)
    return f'<pre class="dir-tree">{escaped}\n</pre>\n'


def remove_mermaid_runtime(html_text: str) -> str:
    html_text = re.sub(
        r'\s*<script src="https://cdn\.jsdelivr\.net/npm/mermaid[^\"]*"></script>\s*',
        "\n",
        html_text,
    )
    html_text = re.sub(
        r'\s*<script>\s*mermaid\.initialize\(.*?</script>\s*',
        "\n",
        html_text,
        flags=re.DOTALL,
    )
    return html_text


def replace_generated_block(html_text: str, name: str, inner: str) -> tuple[str, bool]:
    """Replace content between GENERATED markers. Returns (new_html, changed)."""
    pattern = re.compile(
        rf"(<!-- T2AG_GENERATED:{re.escape(name)} -->)(.*?)(<!-- /T2AG_GENERATED:{re.escape(name)} -->)",
        re.DOTALL,
    )
    m = pattern.search(html_text)
    if not m:
        raise SystemExit(f"missing HTML anchor T2AG_GENERATED:{name}")
    # normalize: leading newline + content + trailing newline inside block
    new_inner = "\n" + inner.rstrip() + "\n"
    old_inner = m.group(2)
    if old_inner == new_inner:
        return html_text, False
    new_html = html_text[: m.start()] + m.group(1) + new_inner + m.group(3) + html_text[m.end() :]
    return new_html, True


def expected_blocks(root: Path) -> dict[str, str]:
    """Compute what each GENERATED block should contain for this edition."""
    main = root / "main"
    flow_path = main / "50_playbook" / "t2ag_flow.md"
    if not flow_path.is_file():
        raise SystemExit(f"missing {flow_path}")
    flows = extract_flow_blocks(flow_path.read_text(encoding="utf-8"))
    out: dict[str, str] = {
        "preface": build_preface_html(main),
        "directory_map": build_directory_map_html(main, root / "cloud"),
    }
    for anchor, flow_id in FLOW_ANCHORS.items():
        if flow_id not in flows:
            raise SystemExit(f"FLOW:{flow_id} not found in t2ag_flow.md")
        out[anchor] = flow_body_to_html(flows[flow_id], flow_id)
    missing = [flow_id for flow_id in FLOW_ORDER if flow_id not in flows]
    extras = sorted(set(flows) - set(FLOW_ORDER))
    if missing or extras:
        raise SystemExit(f"FLOW catalog mismatch: missing={missing} extras={extras}")
    cards: list[str] = []
    for flow_id in FLOW_ORDER:
        if flow_id in FLOW_ANCHORS.values():
            continue
        cards.append(
            f'<article class="flow-card"><h3>{html.escape(FLOW_TITLES[flow_id])}</h3>\n'
            f'{flow_body_to_html(flows[flow_id], flow_id)}</article>\n'
        )
    out["flow_catalog"] = "".join(cards)
    return out


def run(root: Path, *, write: bool = False) -> int:
    guide = root / "t2ag_directory_guide.html"
    if not guide.is_file():
        print(f"ERROR: no guide at {guide}", file=sys.stderr)
        return 1
    blocks = expected_blocks(root)
    original_html = guide.read_text(encoding="utf-8")
    html_text = original_html
    html_text = remove_mermaid_runtime(html_text)
    changed: list[str] = []
    if html_text != original_html:
        changed.append("offline_runtime")
    for name, inner in blocks.items():
        html_text, did = replace_generated_block(html_text, name, inner)
        if did:
            changed.append(name)
    print(f"root={root}")
    print(f"blocks={','.join(blocks.keys())}")
    if changed:
        if write:
            guide.write_text(html_text, encoding="utf-8", newline="\n")
            print(f"updated: {', '.join(changed)}")
        else:
            print(f"drift: {', '.join(changed)}")
            print("check-only: rerun with --write")
            return 1
    else:
        print("drift: none")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Inject T2AG guide GENERATED fragments")
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Edition root (default: parent of main/ containing this tools/)",
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="Write regenerated blocks (default: check only)",
    )
    args = ap.parse_args()
    root = args.root.resolve() if args.root else ROOT
    return run(root, write=args.write)


if __name__ == "__main__":
    sys.exit(main())
