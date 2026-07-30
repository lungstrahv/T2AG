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
  python main/70_tools/build_guide.py --write --root C:/Users/MikeChen/T2AC/t2ag
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import textwrap
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
    "first_run": "图 0 · 首次启动",
    "panorama": "图 1 · 一次教学会话",
    "teaching_loop": "图 1b · 正课循环",
    "authority_chain": "图 2 · 权威链",
    "cycles": "图 3 · 周期回路",
    "skin": "图 5 · 皮肤系统",
    "git": "图 6 · Git 工作流",
    "batch": "图 7 · 批次整改治理",
    "exercise_loop": "图 8 · 习题证据闭环",
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


def _label_lines(label: str) -> list[str]:
    raw_parts = re.split(r"<br\s*/?>|\n", label)
    lines: list[str] = []
    for part in raw_parts:
        wrapped = textwrap.wrap(part.strip(), width=24) or [""]
        lines.extend(wrapped)
    return lines[:4]


def mermaid_to_static_svg(code: str, flow_id: str) -> str:
    """Render the deliberately small T2AG Mermaid subset as deterministic SVG."""
    nodes: dict[str, tuple[str, str]] = {}
    order: list[str] = []
    edges: list[tuple[str, str, str]] = []
    node_patterns = (
        (re.compile(r'^([A-Za-z][A-Za-z0-9_]*)\(\["(.*)"\]\)$'), "terminal"),
        (re.compile(r'^([A-Za-z][A-Za-z0-9_]*)\{"(.*)"\}$'), "decision"),
        (re.compile(r'^([A-Za-z][A-Za-z0-9_]*)\["(.*)"\]$'), "box"),
    )
    edge_pattern = re.compile(
        r'^([A-Za-z][A-Za-z0-9_]*)\s*(?:--\s*"([^"]+)"\s*)?-->\s*'
        r'([A-Za-z][A-Za-z0-9_]*)$'
    )
    for raw in code.splitlines():
        line = raw.strip()
        if not line or line.startswith("flowchart") or line.startswith("%%"):
            continue
        matched = False
        for pattern, shape in node_patterns:
            match = pattern.match(line)
            if match:
                node_id, label = match.groups()
                if node_id not in nodes:
                    order.append(node_id)
                nodes[node_id] = (label, shape)
                matched = True
                break
        if matched:
            continue
        edge = edge_pattern.match(line)
        if edge:
            source, edge_label, target = edge.groups()
            edges.append((source, target, edge_label or ""))
            continue
        raise SystemExit(f"unsupported Mermaid line in FLOW:{flow_id}: {line}")

    if not nodes:
        raise SystemExit(f"FLOW:{flow_id} contains no Mermaid nodes")
    unknown = sorted({item for edge in edges for item in edge[:2]} - set(nodes))
    if unknown:
        raise SystemExit(f"FLOW:{flow_id} edges reference unknown nodes: {unknown}")

    ordinal = {node_id: index for index, node_id in enumerate(order)}
    level = {node_id: 0 for node_id in order}
    for _ in range(len(order)):
        changed = False
        for source, target, _ in edges:
            if ordinal[source] >= ordinal[target]:
                continue
            candidate = level[source] + 1
            if candidate > level[target]:
                level[target] = candidate
                changed = True
        if not changed:
            break

    groups: dict[int, list[str]] = {}
    for node_id in order:
        groups.setdefault(level[node_id], []).append(node_id)
    wrapped = {node_id: _label_lines(nodes[node_id][0]) for node_id in order}
    node_width = 246
    gap_x = 34
    margin = 28
    canvas_width = max(
        680,
        max(len(items) * node_width + max(0, len(items) - 1) * gap_x for items in groups.values())
        + margin * 2,
    )
    positions: dict[str, tuple[float, float, float, float]] = {}
    y = 32.0
    for level_no in sorted(groups):
        items = groups[level_no]
        heights = [max(64, 30 + 18 * len(wrapped[item])) for item in items]
        row_height = max(heights)
        row_width = len(items) * node_width + max(0, len(items) - 1) * gap_x
        x = (canvas_width - row_width) / 2
        for node_id, height in zip(items, heights):
            positions[node_id] = (x, y + (row_height - height) / 2, node_width, height)
            x += node_width + gap_x
        y += row_height + 72
    canvas_height = y - 38
    marker_id = f"arrow-{flow_id}"
    parts = [
        f'<svg class="flow-svg" role="img" aria-label="{html.escape(FLOW_TITLES[flow_id])}" '
        f'style="width:100%;height:auto;display:block" '
        f'width="{canvas_width:.0f}" height="{canvas_height:.0f}" '
        f'viewBox="0 0 {canvas_width:.0f} {canvas_height:.0f}" xmlns="http://www.w3.org/2000/svg">',
        "<defs>",
        f'<marker id="{marker_id}" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#52606d"/></marker>',
        "</defs>",
    ]
    for source, target, edge_label in edges:
        sx, sy, sw, sh = positions[source]
        tx, ty, tw, _ = positions[target]
        x1, y1 = sx + sw / 2, sy + sh
        x2, y2 = tx + tw / 2, ty
        if y2 <= y1:
            bend = max(sx + sw, tx + tw) + 24
            path = f"M{x1:.1f},{y1:.1f} C{bend:.1f},{y1 + 28:.1f} {bend:.1f},{y2 - 28:.1f} {x2:.1f},{y2:.1f}"
        else:
            middle = (y1 + y2) / 2
            path = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{middle:.1f} {x2:.1f},{middle:.1f} {x2:.1f},{y2:.1f}"
        parts.append(
            f'<path d="{path}" fill="none" stroke="#52606d" stroke-width="1.7" '
            f'marker-end="url(#{marker_id})"/>'
        )
        if edge_label:
            lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 5
            parts.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="12" '
                f'fill="#334e68" paint-order="stroke" stroke="#fff" stroke-width="5">'
                f'{html.escape(edge_label)}</text>'
            )
    for node_id in order:
        label, shape = nodes[node_id]
        x, ny, width, height = positions[node_id]
        if shape == "decision":
            points = (
                f"{x + width / 2:.1f},{ny:.1f} {x + width:.1f},{ny + height / 2:.1f} "
                f"{x + width / 2:.1f},{ny + height:.1f} {x:.1f},{ny + height / 2:.1f}"
            )
            parts.append(f'<polygon points="{points}" fill="#fff7ed" stroke="#c2410c" stroke-width="1.8"/>')
        else:
            radius = 24 if shape == "terminal" else 10
            fill = "#eef6ff" if shape == "terminal" else "#ffffff"
            parts.append(
                f'<rect x="{x:.1f}" y="{ny:.1f}" width="{width}" height="{height:.1f}" '
                f'rx="{radius}" fill="{fill}" stroke="#486581" stroke-width="1.8"/>'
            )
        lines = wrapped[node_id]
        first_y = ny + height / 2 - (len(lines) - 1) * 9 + 5
        parts.append(
            f'<text x="{x + width / 2:.1f}" y="{first_y:.1f}" text-anchor="middle" '
            'font-size="14" fill="#102a43" font-family="system-ui,Segoe UI,sans-serif">'
        )
        for index, line in enumerate(lines):
            dy = 0 if index == 0 else 18
            parts.append(
                f'<tspan x="{x + width / 2:.1f}" dy="{dy}">{html.escape(line)}</tspan>'
            )
        parts.append("</text>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def flow_body_to_html(body: str, flow_id: str) -> str:
    """Convert a FLOW body into offline HTML with source fallback."""
    body = body.strip()
    m = re.match(r"^```mermaid\s*\n(.*?)```\s*$", body, re.DOTALL)
    if m:
        code = m.group(1).rstrip() + "\n"
        svg = mermaid_to_static_svg(code, flow_id)
        fallback = (
            '<details class="flow-source"><summary>查看流程源码</summary>'
            f'<pre>{html.escape(code)}</pre></details>\n'
        )
        return (
            '<details class="flow-diagram"><summary><span>展开查看流程图</span>'
            '<small>图框内可滚动</small></summary>\n'
            f'<div class="flow-viewport">\n{svg}</div>\n'
            f'{fallback}</details>\n'
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
    match = re.search(
        r"^##\s+序\s*$\n(.*?)(?=^##\s+1\.)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise SystemExit("directory guide: main/t2ag.md lacks authoritative ## 序")

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
            if content.startswith("**序言纪律**"):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                discipline = re.sub(r"^\*\*序言纪律\*\*[：:]\s*", "", content)
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
            '<aside class="preface-discipline"><strong>序言纪律</strong>',
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
    """Return an existing edition-relative authority path, never a directory echo."""
    for filename in ("_README.md", "README.md", "INDEX.md"):
        candidate = entry / filename
        if candidate.is_file():
            return candidate.relative_to(main_dir.parent).as_posix()
    return "main/t2ag.md"


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
                blurb = "T2AG 命令入口"
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
