#!/usr/bin/env python3
"""T2AG directory guide fragment injector (零依赖).

Reads the *local* edition tree (this script's repo root) and injects into
t2ag_directory_guide.html between T2AG_GENERATED anchors.

- directory_map: from main/* _README + cloud/README (no fixed list)
- flow_first_run / flow_panorama: from main/00_core/t2ag_flow.md FLOW markers

FLOW extraction uses line-anchored HTML comments only
  ^<!-- FLOW:name -->$ … ^<!-- /FLOW:name -->$
so prose examples containing FLOW:xxx are ignored.

Usage (cwd or any path inside edition):
  python main/70_tools/build_guide.py
  python main/70_tools/build_guide.py --root C:/Users/MikeChen/T2AC/t2ag
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # edition root (…/t2ag)
MAIN = ROOT / "main"
FLOW_MD = MAIN / "00_core" / "t2ag_flow.md"
GUIDE_HTML = ROOT / "t2ag_directory_guide.html"

# True FLOW open/close (line-anchored); never match prose `FLOW:xxx`
_FLOW_OPEN = re.compile(r"^<!-- FLOW:([a-z0-9_]+) -->\s*$")
_FLOW_CLOSE = re.compile(r"^<!-- /FLOW:([a-z0-9_]+) -->\s*$")

_GEN_BLOCK = re.compile(
    r"(<!-- T2AG_GENERATED:([a-z0-9_]+) -->)(.*?)(<!-- /T2AG_GENERATED:\2 -->)",
    re.DOTALL,
)

MERMAID_CDN = (
    '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>\n'
    "<script>mermaid.initialize({startOnLoad:true,theme:'neutral'});</script>\n"
)

# HTML anchor name → FLOW id in t2ag_flow.md
FLOW_ANCHORS = {
    "flow_first_run": "first_run",
    "flow_panorama": "panorama",
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


def flow_body_to_html(body: str) -> str:
    """Convert a FLOW body (fenced mermaid or text) into HTML fragment."""
    body = body.strip()
    # mermaid fence
    m = re.match(r"^```mermaid\s*\n(.*?)```\s*$", body, re.DOTALL)
    if m:
        code = m.group(1).rstrip() + "\n"
        return f'<div class="mermaid">\n{code}</div>\n'
    # plain ```text or bare ascii
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
    return readme.parent.name


def build_directory_map_html(main_dir: Path, cloud_dir: Path) -> str:
    """Build table from actual directories in this edition (no fixed inventory)."""
    rows: list[tuple[str, str, str]] = []
    if main_dir.is_dir():
        for entry in sorted(main_dir.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            # skip non-structural noise
            if entry.name in {"__pycache__", "skin"}:
                # skin is under main; include skin as main/skin/
                pass
            rel = f"main/{entry.name}/"
            readme = entry / "_README.md"
            if entry.name == "00_core":
                auth = "main/t2ag.md"
            elif entry.name == "60_journal" and (entry / "INDEX.md").is_file():
                auth = "60_journal/INDEX.md"
            elif readme.is_file():
                auth = f"{entry.name}/_README.md"
            else:
                auth = f"{entry.name}/"
            blurb = _readme_blurb(readme) if readme.is_file() else (
                "协议与全局索引" if entry.name == "00_core" else entry.name
            )
            rows.append((rel, blurb, auth))
    if cloud_dir.is_dir():
        cloud_readme = cloud_dir / "README.md"
        rows.append(
            (
                "cloud/",
                _readme_blurb(cloud_readme) if cloud_readme.is_file() else "云端桥接",
                "cloud/README.md" if cloud_readme.is_file() else "cloud/",
            )
        )

    lines = [
        "<table>",
        "<thead><tr><th>目录</th><th>这里放什么</th><th>权威文件</th></tr></thead>",
        "<tbody>",
    ]
    for rel, blurb, auth in rows:
        lines.append(
            "<tr>"
            f"<td><code>{html.escape(rel)}</code></td>"
            f"<td>{html.escape(blurb)}</td>"
            f"<td><code>{html.escape(auth)}</code></td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>", ""])
    return "\n".join(lines)


def ensure_mermaid_cdn(html_text: str) -> str:
    if "mermaid" in html_text and "cdn.jsdelivr.net/npm/mermaid" in html_text:
        return html_text
    # inject before </body> if present, else before </html>
    snippet = "\n" + MERMAID_CDN
    if "</body>" in html_text:
        return html_text.replace("</body>", snippet + "</body>", 1)
    if "</html>" in html_text:
        return html_text.replace("</html>", snippet + "</html>", 1)
    return html_text + snippet


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
    flow_path = main / "00_core" / "t2ag_flow.md"
    if not flow_path.is_file():
        raise SystemExit(f"missing {flow_path}")
    flows = extract_flow_blocks(flow_path.read_text(encoding="utf-8"))
    out: dict[str, str] = {
        "directory_map": build_directory_map_html(main, root / "cloud"),
    }
    for anchor, flow_id in FLOW_ANCHORS.items():
        if flow_id not in flows:
            raise SystemExit(f"FLOW:{flow_id} not found in t2ag_flow.md")
        out[anchor] = flow_body_to_html(flows[flow_id])
    return out


def run(root: Path) -> int:
    guide = root / "t2ag_directory_guide.html"
    if not guide.is_file():
        print(f"ERROR: no guide at {guide}", file=sys.stderr)
        return 1
    blocks = expected_blocks(root)
    html_text = guide.read_text(encoding="utf-8")
    html_text = ensure_mermaid_cdn(html_text)
    changed: list[str] = []
    for name, inner in blocks.items():
        html_text, did = replace_generated_block(html_text, name, inner)
        if did:
            changed.append(name)
    guide.write_text(html_text, encoding="utf-8", newline="\n")
    print(f"root={root}")
    print(f"blocks={','.join(blocks.keys())}")
    if changed:
        print(f"updated: {', '.join(changed)}")
    else:
        print("updated: (none — already current)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Inject T2AG guide GENERATED fragments")
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Edition root (default: parent of main/ containing this tools/)",
    )
    args = ap.parse_args()
    root = args.root.resolve() if args.root else ROOT
    return run(root)


if __name__ == "__main__":
    sys.exit(main())
