#!/usr/bin/env python3
"""T2AG → OKF v0.2 知识包导出器（EV-0024 / 协议 `T2AG-OKF-1`）。

规范真相源是 `main/50_playbook/okf_adaptation.md`；本文件是它的可复算实现。
二者冲突时以 playbook 为准，并修本文件——这是「散文宣称必须有机器落点」
（EV-0016 / EV-0018 同族）在本协议上的落法。

三条不变式（playbook §一）在代码里的对应位置：
1. 主库零改动 —— 全流程只读主库；唯一写路径是 `--write` 指向的仓外目录。
2. 机制可交换，实例不出门 —— `collect_sources()` 是目录级正列举白名单，
   `10_student/`、`60_journal/`、`progress.md`、`activity_ledger.md`、`cloud/`
   没有任何代码路径通向它。
3. 不伪造信任 —— 全程不写 `verified`：结构核实不等于内容核实。

泄漏闸门在**内存渲染完成、落盘之前**运行（`leak_findings`），命中即零写入。
词表从 `t2ag_doctor.SKELETON_PRIVACY_PATTERNS` 导入，是共享真相源；导入失败
直接退出，而不是退化成一份弱词表——「找不到词表就不扫」正是闸门失效的经典形态。

用法：
  python main/70_tools/okf_export.py                      # check-only（默认）：渲染 + 全检，不落盘
  python main/70_tools/okf_export.py --write              # 通过后写入 <workspace>/t2ag-okf/
  python main/70_tools/okf_export.py --scope course:PY1001 --write
  python main/70_tools/okf_export.py --check-bundle <dir> # 对已有 bundle 复算 conformance

退出码：0 通过；1 有 FAIL（泄漏命中、conformance 不合格、范围为空）。
本工具**不注册进 doctor runtime**：bundle 是可选生成物，它缺席不该阻断当天教学
（同 `t2ag.md` §3.2「发行问题不阻断教学」）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main"

TOOL_VERSION = "0.1.0"
ACTOR = f"t2ag/okf_export-{TOOL_VERSION}"
OKF_VERSION = "0.2"
# 输出目录随仓名派生，而不是硬写 `t2ag-okf`：Main 与 Skeleton 同处一个工作区，
# 固定名会让两仓的导出互相覆盖（EV-0022 同族：落点从机器字面量改为由仓根派生）。
DEFAULT_OUT = ROOT.parent / f"{ROOT.name}-okf"

# EV-0024 R-1 / P0-3：交付目录的身份标记。`--write` 只肯写「空目录」或「带本标记的
# 既有目录」，其余一律拒绝。没有这个标记，`--out` 就只是一个任意路径，而 write_bundle
# 会删掉目标目录里清单外的 .md——独立复审实测的高危写路径正是这条。
BUNDLE_MARKER = ".t2ag-okf-bundle"

# EV-0024 R-1 / P0-1：course scope 的 ID 白名单。只认字母数字与 `_-`，因此
# `..`、`/`、`\`、绝对路径与空白全部落在拒绝面上，不靠逐个枚举危险字符。
COURSE_ID_RE = re.compile(r"\A[A-Za-z0-9_-]+\Z")

# EV-0024 R-3：允许升格为链接的内联代码形态——单一路径 token，无空白、无引号、
# 无 shell 元字符。判据实现见 `is_single_path_token()`。
SINGLE_PATH_RE = re.compile(r"\A[A-Za-z0-9._/-]+\Z")

RESERVED_NAMES = {"index.md", "log.md"}
CHANGELOG_REL = "00_core/t2ag_changelog.md"
LOG_ENTRY_LIMIT = 25

# playbook §二：mechanism 范围的目录级正列举。台账三件（changelog/memory/problemlog）
# 与全部课程刻意不在此表内，理由见 playbook §二。
MECHANISM_CORE_FILES = (
    "domain_model.md",
    "learning_activity_model.md",
    "pattern_retire_loop.md",
)

# playbook §3.1：type 注入表。已有 frontmatter 的文件一律透传原 type，不进本表。
TYPE_DOMAIN_MODEL = "Domain Model"
TYPE_GOVERNANCE = "Governance Doc"
TYPE_PLAYBOOK = "Playbook"
TYPE_REFERENCE = "Reference"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\]\(([^)]+)\)")
CHANGELOG_HEADING_RE = re.compile(r"^##\s*\[(\d{4}-\d{2}-\d{2})\]\s*(.+?)\s*$", re.MULTILINE)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------- 工具


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def privacy_patterns() -> tuple[tuple[str, str], ...]:
    """泄漏词表的唯一来源是 doctor；取不到就停，不退化。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import t2ag_doctor  # noqa: PLC0415 - 延迟导入：只有导出时才需要
    except Exception as error:  # pragma: no cover - 环境损坏时的诚实失败
        raise SystemExit(
            f"okf_export: 无法从 t2ag_doctor 载入泄漏词表，拒绝在无闸门状态下导出：{error}"
        ) from error
    return tuple(t2ag_doctor.SKELETON_PRIVACY_PATTERNS)


def split_frontmatter(text: str) -> tuple[dict | None, str]:
    """拆出 YAML frontmatter 与正文。无 frontmatter 时返回 (None, 原文)。"""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None, text
    if not isinstance(data, dict):
        return None, text
    return data, text[match.end():]


def first_h1(body: str) -> str | None:
    match = H1_RE.search(body)
    return match.group(1).strip() if match else None


def lead_description(body: str) -> str | None:
    """取 H1 之后第一段可读散文的首句，供 index.md 汇编（OKF §8）。"""
    match = H1_RE.search(body)
    tail = body[match.end():] if match else body
    for raw in tail.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "|", "-", "*", "```", "<!--")):
            continue
        line = line.lstrip("> ").strip()
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"`(.+?)`", r"\1", line)
        if not line:
            continue
        for stop in ("。", "；", ". "):
            if stop in line:
                line = line.split(stop)[0] + (stop.strip() if stop != ". " else ".")
                break
        return line[:160]
    return None


def git_committed_at(rel: str) -> str | None:
    """该文件最后一次 commit 时间。只读命令；--no-optional-locks 保证不碰 .git 锁。"""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "log", "-1", "--format=%cI", "--", rel],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    stamp = result.stdout.strip()
    return stamp or None


def timestamp_for(path: Path) -> str:
    """playbook §3.2：git commit 时间优先，不可得回退 mtime。统一 UTC。"""
    rel = path.relative_to(ROOT).as_posix()
    stamp = git_committed_at(rel)
    if stamp:
        try:
            return _dt.datetime.fromisoformat(stamp).astimezone(
                _dt.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    return _dt.datetime.fromtimestamp(
        path.stat().st_mtime, tz=_dt.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- 收集


def collect_sources(scope: str) -> tuple[list[tuple[Path, str, str | None]], list[str]]:
    """按 scope 正列举源文件。

    返回 (条目, 错误)。条目为 (源路径, bundle 内相对路径, 注入 type|None)；
    `None` 表示该文件自带 frontmatter，type 透传不注入。
    """
    items: list[tuple[Path, str, str | None]] = []
    errors: list[str] = []

    if scope == "mechanism":
        constitution = MAIN / "t2ag.md"
        if constitution.is_file():
            items.append((constitution, "t2ag.md", TYPE_GOVERNANCE))
        else:
            errors.append("mechanism 范围缺文件：main/t2ag.md")

        for name in MECHANISM_CORE_FILES:
            path = MAIN / "00_core" / name
            if not path.is_file():
                errors.append(f"mechanism 范围缺文件：main/00_core/{name}")
                continue
            injected = TYPE_DOMAIN_MODEL if name == "domain_model.md" else TYPE_GOVERNANCE
            items.append((path, f"00_core/{name}", injected))

        for path in sorted((MAIN / "50_playbook").glob("*.md")):
            if path.name == "_README.md":
                continue
            items.append((path, f"50_playbook/{path.name}", TYPE_PLAYBOOK))

        for path in sorted((MAIN / "70_tools").glob("*.md")):
            if path.name == "_README.md":
                continue
            items.append((path, f"70_tools/{path.name}", TYPE_REFERENCE))

    elif scope.startswith("course:"):
        course_id = scope.split(":", 1)[1].strip()
        if not course_id:
            errors.append("course scope 未给课程 ID")
            return items, errors
        # P0-1：先校验再拼路径。course_id 同时进源路径与输出相对路径，未校验时
        # `..` 可同时形成读穿越与写穿越（独立复审 §一「实例层无可达路径」finding）。
        if not COURSE_ID_RE.match(course_id):
            errors.append(
                f"course ID 非法：{course_id!r}（只允许字母、数字、下划线与连字符；"
                "路径分隔符、`.`、`..` 与绝对路径一律拒绝）"
            )
            return items, errors
        path = MAIN / "40_course" / course_id / "course.md"
        if not path.is_file():
            errors.append(f"课程定义不存在：main/40_course/{course_id}/course.md")
            return items, errors
        # course.md 自带 frontmatter（含 type: course），透传不注入。
        items.append((path, f"40_course/{course_id}/course.md", None))

    else:
        errors.append(f"未知 scope：{scope}（可用：mechanism、course:<COURSE_ID>）")

    return items, errors


# --------------------------------------------------------------------------- 渲染


def basename_index(known: set[str]) -> dict[str, str]:
    """裸文件名 → bundle 路径。同名多处时不收录，避免猜错目标。"""
    seen: dict[str, list[str]] = {}
    for rel in known:
        seen.setdefault(Path(rel).name, []).append(rel)
    return {name: rels[0] for name, rels in seen.items() if len(rels) == 1}


def is_single_path_token(raw: str) -> bool:
    """内联代码内容是否「恰为一个可解析的 .md 路径」（EV-0024 R-3 判据）。

    只有通过本判据的内联代码才允许升格成链接。判据刻意保守：宁可漏升格几条真引用，
    也不把命令、参数串与示例改写成链接——前者只是少一条边，后者是伪造语义。

    拒绝面（各举一例）：
    - 含空白：`` `grep -rn "x" file.md` ``、`` `a.md b.md` ``（多目标压成一条边）
    - 含 shell 元字符或引号：`` `cat a.md | less` ``
    - 以 `-` 开头：`` `--out a.md` ``（命令选项而非路径）
    - 不以 `.md` 结尾：`` `okf_export.py` ``
    """
    token = raw.strip()
    if not token or token.startswith("-"):
        return False
    if not token.endswith(".md"):
        return False
    return bool(SINGLE_PATH_RE.match(token))


def resolve_reference(raw: str, known: set[str], by_name: dict[str, str]) -> str | None:
    """把主库散文里的文件引用解析成 bundle 路径；解析不了返回 None。"""
    target = raw.strip().lstrip("./")
    if target.startswith("main/"):
        target = target[len("main/"):]
    if target in known:
        return target
    return by_name.get(Path(target).name)


def link_references(
    body: str, source_rel: str, known: set[str], by_name: dict[str, str]
) -> str:
    """把反引号文件引用升格为 markdown 链接，让 bundle 真的成为一张有向图。

    T2AG 散文引用其他文件用的是行内反引号（`` `session_close.md` ``）而不是 markdown
    链接，实测机制层 1266 处引用里 markdown 链接为 0。照搬只会导出一堆互不相连的
    文件：OKF 的图结构靠链接表达（§6.1），没有链接就没有边，「知识包」退化成「文件夹」。

    三条克制规则：
    - **每个目标每文件只升格首次出现**。重复升格既吵，图上也只是同一条边。
    - **只升格解析得到的 bundle 内目标**。指向实例层（`progress.md` 一类）的引用留作
      反引号，既不伪造边，也不制造断链。
    - **只升格内联代码内容恰为单一可解析路径的情况**（EV-0024 R-3）。原实现用
      `` `([^`\n]+\.md)` `` 匹配整段内联代码，于是
      `` `grep -rn "x" file.md` `` 这类完整命令被整体升格成链接，多目标命令还被压成
      一条边——那不是展示问题，是实质语义改写。判据见 `is_single_path_token()`。
    """
    linked: set[str] = set()
    pattern = re.compile(r"`([^`\n]+)`")

    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        if not is_single_path_token(raw):
            return match.group(0)
        target = resolve_reference(raw, known, by_name)
        if target is None or target == source_rel or target in linked:
            return match.group(0)
        linked.add(target)
        return f"[`{raw}`](/{target})"

    # 围栏代码块内不改写：那里的文件名是示例或命令，不是引用。
    parts = body.split("```")
    for index in range(0, len(parts), 2):
        parts[index] = pattern.sub(replace, parts[index])
    return "```".join(parts)


def rewrite_links(body: str, source_rel: str, known: set[str]) -> str:
    """既有 markdown 链接改写为 bundle 绝对形（OKF §6.1）。

    指向未收录文件的链接原样保留：OKF 明确断链代表「尚未写出的知识」，不是错误。
    """
    source_dir = (MAIN / source_rel).parent

    def replace(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        if not target or target.startswith(("http://", "https://", "#", "mailto:", "/")):
            return match.group(0)
        anchor = ""
        if "#" in target:
            target, anchor = target.split("#", 1)
            anchor = "#" + anchor
        if not target:
            return match.group(0)
        try:
            resolved = (source_dir / target).resolve()
            rel = resolved.relative_to(MAIN.resolve()).as_posix()
        except (ValueError, OSError):
            return match.group(0)
        if rel in known:
            return f"](/{rel}{anchor})"
        return match.group(0)

    return LINK_RE.sub(replace, body)


def render_concept(
    path: Path,
    bundle_rel: str,
    injected_type: str | None,
    known: set[str],
    by_name: dict[str, str],
) -> tuple[str, str, str | None]:
    """渲染一个概念文件，返回 (文本, title, description)。"""
    original = read(path)
    existing, body = split_frontmatter(original)

    front: dict = {}
    if existing:
        # 透传全部已有键：OKF 要求消费者保留未知键，生产者更不该丢。
        front.update(existing)
    if injected_type is not None:
        front["type"] = injected_type
    if not str(front.get("type", "")).strip():
        front["type"] = TYPE_REFERENCE

    title = str(front.get("title") or "").strip() or first_h1(body) or path.stem
    front["title"] = title

    description = str(front.get("description") or "").strip() or lead_description(body)
    if description:
        front["description"] = description

    front["generated"] = {"by": ACTOR, "at": timestamp_for(path)}
    # `verified` 刻意不写（playbook §一不变式 3）：结构核实 ≠ 内容核实。
    front.pop("verified", None)

    ordered_keys = ["type", "title", "description", "status", "tags", "generated"]
    ordered = {k: front[k] for k in ordered_keys if k in front}
    ordered.update({k: v for k, v in front.items() if k not in ordered})

    dumped = yaml.safe_dump(
        ordered, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).rstrip("\n")
    rendered = rewrite_links(body, bundle_rel, known)
    rendered = link_references(rendered, bundle_rel, known, by_name)
    text = f"---\n{dumped}\n---\n\n{rendered.lstrip()}"
    return text, title, description


def build_directory_index(
    dir_rel: str, entries: list[tuple[str, str, str | None]], readme: Path | None
) -> str:
    """目录 index.md（OKF §8）：条目描述来自被链接概念自己的 description。"""
    lines: list[str] = [f"# {dir_rel}", ""]
    if readme and readme.is_file():
        lead = lead_description(split_frontmatter(read(readme))[1])
        if lead:
            lines += [lead, ""]
    for name, title, description in sorted(entries):
        suffix = f" - {description}" if description else ""
        lines.append(f"* [{title}]({name}){suffix}")
    lines.append("")
    return "\n".join(lines)


def build_root_index(scope: str, groups: dict[str, list[tuple[str, str, str | None]]]) -> str:
    """根 index.md：唯一允许带 frontmatter 的 index，且只放 okf_version（OKF §12）。"""
    lines = [
        "---",
        f'okf_version: "{OKF_VERSION}"',
        "---",
        "",
        "# T2AG 知识包",
        "",
        f"T2AG 主库按协议 `T2AG-OKF-1` 导出的 OKF v{OKF_VERSION} 知识包。",
        f"范围 `{scope}`：只含描述系统如何运转的机制层文件，不含学生档案、学习进度、",
        "教学实录与日志。规范见主库 `main/50_playbook/okf_adaptation.md`。",
        "",
        "本包是生成物，不是真相源：任何修改都应改回主库后重新导出。",
        "",
    ]
    root_entries = groups.get(".", [])
    if root_entries:
        lines.append("# 入口")
        lines.append("")
        for name, title, description in sorted(root_entries):
            suffix = f" - {description}" if description else ""
            lines.append(f"* [{title}]({name}){suffix}")
        lines.append("")
    for dir_rel in sorted(k for k in groups if k != "."):
        lines += [f"# {dir_rel}", "", f"* [{dir_rel}/]({dir_rel}/) - 见该目录 index.md", ""]
    return "\n".join(lines)


def build_log() -> str | None:
    """根 log.md（OKF §9）：只转写 changelog 的**标题层**，正文不出门。"""
    changelog = MAIN / CHANGELOG_REL
    if not changelog.is_file():
        return None
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for date, title in CHANGELOG_HEADING_RE.findall(read(changelog))[:LOG_ENTRY_LIMIT]:
        if date not in grouped:
            grouped[date] = []
            order.append(date)
        grouped[date].append(title)
    if not order:
        return None
    lines = ["# T2AG Update Log", ""]
    for date in order:
        lines.append(f"## {date}")
        for title in grouped[date]:
            lines.append(f"* **Update**: {title}")
        lines.append("")
    return "\n".join(lines)


def render_bundle(scope: str) -> tuple[dict[str, str], list[str]]:
    """把整个 bundle 渲染进内存。落盘前的一切检查都在这份产物上做。"""
    items, errors = collect_sources(scope)
    if errors:
        return {}, errors
    if not items:
        return {}, [f"scope `{scope}` 没有可导出的文件"]

    known = {rel for _, rel, _ in items}
    by_name = basename_index(known)
    files: dict[str, str] = {}
    groups: dict[str, list[tuple[str, str, str | None]]] = {}

    for path, bundle_rel, injected in items:
        text, title, description = render_concept(path, bundle_rel, injected, known, by_name)
        files[bundle_rel] = text
        dir_rel = str(Path(bundle_rel).parent).replace("\\", "/")
        groups.setdefault(dir_rel, []).append((Path(bundle_rel).name, title, description))

    for dir_rel, entries in groups.items():
        if dir_rel == ".":
            continue  # bundle 根的概念由根 index.md 收录，不另生成同级 index
        readme = MAIN / dir_rel / "_README.md"
        files[f"{dir_rel}/index.md"] = build_directory_index(dir_rel, entries, readme)

    files["index.md"] = build_root_index(scope, groups)
    log = build_log()
    if log:
        files["log.md"] = log
    return files, []


# --------------------------------------------------------------------------- 检查


def leak_findings(files: dict[str, str]) -> list[str]:
    """泄漏闸门（playbook §五）。命中不可豁免：正确反应是修主库。"""
    findings: list[str] = []
    for pattern, label in privacy_patterns():
        compiled = re.compile(pattern)
        for rel, text in sorted(files.items()):
            if compiled.search(text):
                findings.append(f"个人信息泄漏：{rel} -> {label}")
    return findings


def conformance_findings(files: dict[str, str]) -> list[str]:
    """OKF §11 三条硬性条件 + index/log 结构（§8/§9）。"""
    findings: list[str] = []
    for rel, text in sorted(files.items()):
        name = Path(rel).name
        if name in RESERVED_NAMES:
            if name == "index.md":
                front, _ = split_frontmatter(text)
                if rel == "index.md":
                    if not front or set(front) != {"okf_version"}:
                        findings.append("根 index.md 的 frontmatter 只允许 okf_version 一个键")
                elif front is not None:
                    findings.append(f"非根 index.md 不得带 frontmatter：{rel}")
            else:
                for line in text.splitlines():
                    if line.startswith("## ") and not ISO_DATE_RE.match(line[3:].strip()):
                        findings.append(f"log.md 日期标题非 ISO 8601：{rel} -> {line.strip()}")
            continue
        front, _ = split_frontmatter(text)
        if front is None:
            findings.append(f"缺少可解析的 YAML frontmatter：{rel}")
            continue
        if not str(front.get("type", "")).strip():
            findings.append(f"frontmatter 缺少非空 type：{rel}")
    return findings


def load_bundle(path: Path) -> dict[str, str]:
    return {
        p.relative_to(path).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(path.rglob("*.md"))
    }


# --------------------------------------------------------------------------- 落盘


def validate_out_dir(out: Path) -> list[str]:
    """`--write` 落盘前的目标目录准入检查（EV-0024 P0-3）。

    `write_bundle()` 会删掉目标目录里清单外的 `.md`。在本函数存在之前，`--out` 是个
    裸 `Path`，没有任何仓界校验——一次路径打错（如 `--write --out main/50_playbook`）
    就会递归删掉那里所有不在本次导出清单里的 markdown。独立复审把它列为
    「可破坏主库的高危写路径」，本函数是该 finding 的机器落点。

    拒绝面：
    1. 仓根、`main/`、工作区根，以及它们的任何祖先；
    2. 主库或 Skeleton 内部的任意子目录（凡祖先含 `.git` 或落在 ROOT 之下）；
    3. 已存在、非空、且**没有** `BUNDLE_MARKER` 标记文件的目录——
       「不是我上次写出来的包」就不碰。
    """
    errors: list[str] = []
    try:
        target = out.resolve()
    except OSError as error:
        return [f"--out 无法解析：{out}（{error.strerror}）"]

    root = ROOT.resolve()
    forbidden = {root, MAIN.resolve(), root.parent}
    if target in forbidden or target in root.parents or target in root.parent.parents:
        return [f"--out 指向仓根/主库/工作区根，拒绝写入：{target}"]
    if root == target or root in target.parents:
        return [f"--out 落在仓内（{root}），bundle 必须写到仓外：{target}"]
    if (target / ".git").exists() or any((p / ".git").exists() for p in target.parents if p != target.anchor):
        # 落在任意 git 工作树内都拒绝：Skeleton、Lite 与外仓都由此挡下。
        if not (target / BUNDLE_MARKER).exists():
            errors.append(f"--out 落在 git 工作树内且无 {BUNDLE_MARKER} 标记，拒绝写入：{target}")

    if target.exists():
        if not target.is_dir():
            errors.append(f"--out 已存在且不是目录：{target}")
        elif any(target.iterdir()) and not (target / BUNDLE_MARKER).exists():
            errors.append(
                f"--out 是非空的既有目录且无 {BUNDLE_MARKER} 标记，拒绝写入：{target}"
                f"（若确为 bundle 目录，手工建一个空的 {BUNDLE_MARKER} 文件后重试）"
            )
    return errors


def write_bundle(files: dict[str, str], out: Path) -> list[str]:
    """只在全检通过且 `validate_out_dir()` 通过后调用。返回**致命错误**列表。

    先删后写，避免上一次导出的概念在范围收窄后仍留在包里冒充当前知识。

    EV-0024 P0-2/P0-4 之后的三条硬约束：
    - 每个写入目标 `resolve()` 后必须严格落在 `out` 之内（防 rel 里混进 `..`）；
    - 残留文件删不掉时**返回错误**而不是 WARN——原实现只 WARN 且最终 exit 0，
      旧泄漏物可以留在交付目录里，而调用方看不出交付失败；
    - 写后扫描**完整交付目录**（不限 `.md`），清单外的任何文件都报出来。
    """
    errors: list[str] = []
    out.mkdir(parents=True, exist_ok=True)
    marker = out / BUNDLE_MARKER
    if not marker.exists():
        marker.write_text(
            "T2AG OKF bundle 目录标记（okf_export.py 生成）。删除本文件会让下次 --write 拒绝写入。\n",
            encoding="utf-8",
        )

    out_resolved = out.resolve()
    for stale in sorted(out.rglob("*.md"), reverse=True):
        if stale.relative_to(out).as_posix() in files:
            continue  # 本次会重写，无需先删
        try:
            stale.unlink()
        except OSError as error:
            errors.append(f"残留文件未能删除：{stale}（{error.strerror}）")
    if errors:
        return errors  # 删不干净就不写：半新半旧的包比没有包更危险

    for rel, text in sorted(files.items()):
        target = out / rel
        try:
            resolved = target.resolve()
        except OSError as error:
            errors.append(f"写入路径无法解析：{rel}（{error.strerror}）")
            continue
        if resolved != out_resolved and out_resolved not in resolved.parents:
            errors.append(f"写入路径逃出交付目录，拒绝写入：{rel} → {resolved}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    if errors:
        return errors

    # P0-4 写后扫描：不限 .md，交付目录里出现清单外的东西一律报出。
    expected = set(files) | {BUNDLE_MARKER}
    for item in sorted(out.rglob("*")):
        if item.is_dir():
            continue
        rel = item.relative_to(out).as_posix()
        if rel not in expected:
            errors.append(f"交付目录含清单外文件：{rel}")
    return errors


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T2AG → OKF v0.2 导出器（协议 T2AG-OKF-1）")
    parser.add_argument("--scope", default="mechanism", help="mechanism（默认）或 course:<COURSE_ID>")
    parser.add_argument("--write", action="store_true", help="全检通过后落盘；缺省为 check-only")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"输出目录（默认 {DEFAULT_OUT.name}/）")
    parser.add_argument("--check-bundle", type=Path, help="对已有 bundle 复算 conformance 与泄漏")
    args = parser.parse_args(argv)

    if args.check_bundle:
        target = args.check_bundle
        if not target.is_dir():
            print(f"FAIL bundle 目录不存在：{target}")
            return 1
        files = load_bundle(target)
        if not files:
            print(f"FAIL bundle 内没有 markdown 文件：{target}")
            return 1
        findings = conformance_findings(files) + leak_findings(files)
        for item in findings:
            print(f"FAIL {item}")
        print(f"{'FAIL' if findings else 'OK  '} check-bundle：{len(files)} 文件，{len(findings)} 项问题")
        return 1 if findings else 0

    files, errors = render_bundle(args.scope)
    for item in errors:
        print(f"FAIL {item}")
    if errors:
        return 1

    findings = conformance_findings(files) + leak_findings(files)
    for item in findings:
        print(f"FAIL {item}")
    if findings:
        print(f"FAIL 渲染 {len(files)} 文件，{len(findings)} 项问题；按闸门约定零落盘")
        return 1

    concepts = sum(1 for rel in files if Path(rel).name not in RESERVED_NAMES)
    print(f"OK   scope={args.scope}｜概念 {concepts}｜含保留文件共 {len(files)}｜泄漏 0｜conformance 0 FAIL")
    if args.write:
        # P0-3：准入检查先于任何删除与写入。它是「闸门先于写盘且不可豁免」这条
        # 硬边界在**目标目录**上的落法——原实现只把闸门架在内容上，没架在落点上。
        gate = validate_out_dir(args.out)
        for item in gate:
            print(f"FAIL {item}")
        if gate:
            print("FAIL --out 未通过交付目录准入检查；零删除、零写入")
            return 1
        write_errors = write_bundle(files, args.out)
        for item in write_errors:
            print(f"FAIL {item}")
        if write_errors:
            print(f"FAIL 交付未完成：{args.out}（{len(write_errors)} 项）")
            return 1
        print(f"OK   已写入 {args.out}")
    else:
        print("INFO check-only：未落盘。加 --write 生成 bundle。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
