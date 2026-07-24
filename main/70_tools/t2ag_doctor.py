#!/usr/bin/env python3
"""
t2ag_doctor —— 档案一致性体检

职责边界：确定性机器检查（同输入同输出，零裁量）。需要理解判断的检查不属于本文件——那归 50_playbook/。
零依赖。退出码：0 = 无 FAIL，1 = 至少一个 FAIL。

检查项：
  - 启动文件存在性 / 宪法分章预算 / 结构清单登记
  - 学生四文件档案完整性
  - memory 分节预算制 / 版本号一致性 / venv/env 审核
  - 复利回路模式声明 / 课程组规则 / overlay 引用完整性
  - 考试题库引用隔离 / 皮肤系统配置 / R 绑定语义检查
  - 云端同步协议字段 / Project 提示词关键规则 / 同步状态
  - 教材 working_pages 窗口 / 页文件 / OCR / 校对状态 / course_status 一致性
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # 项目根
MAIN = ROOT / "main"
RESULTS: list[tuple[str, str]] = []
# C2 检疫：旧路径扫描「实际触发」计数（非代码中含旧路径字符串）
LEGACY_PATH_HITS: list[tuple[str, str]] = []


def rep(level: str, msg: str) -> None:
    RESULTS.append((level, msg))
    print(f"[{level}] {msg}")


def legacy_path_hit(check_name: str, obj: str) -> None:
    """Record one real legacy-path fallback/scan match (C2 quarantine metric).

    Call only when a live object under an old path was matched and the
    compatibility branch ran — not merely because source code mentions
    30_courses or the empty shell directory exists.
    """
    LEGACY_PATH_HITS.append((check_name, obj))
    rep("INFO", f"legacy_path_hit: {check_name} {obj}")


def emit_legacy_path_hits_total() -> None:
    """Always emit total (including 0) so silence ≠ 'counter off'."""
    rep("INFO", f"legacy_path_hits_total: {len(LEGACY_PATH_HITS)}")


def _iter_legacy_course_status() -> list[Path]:
    """Live course_status.md under 30_courses (excludes _shared / underscore dirs)."""
    root = MAIN / "30_courses"
    if not root.is_dir():
        return []
    out: list[Path] = []
    for status in sorted(root.glob("*/course_status.md")):
        name = status.parent.name
        if name.startswith("_"):
            continue
        out.append(status)
    return out


def rel(p: Path) -> str:
    """Display path relative to MAIN (no `main/` prefix). Fallback: ROOT-relative, then str(p).

    Display only — callers must not parse this string for filesystem logic.
    """
    try:
        return str(p.relative_to(MAIN)).replace("\\", "/")
    except ValueError:
        try:
            return str(p.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            return str(p)


def _guide_html_shell_hash(path: Path) -> str:
    """Hash of directory guide with GENERATED blocks blanked (edition maps may differ)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    blanked = re.sub(
        r"<!-- T2AG_GENERATED:([a-z0-9_]+) -->.*?<!-- /T2AG_GENERATED:\1 -->",
        r"<!-- T2AG_GENERATED:\1 -->\n<!-- /T2AG_GENERATED:\1 -->",
        text,
        flags=re.DOTALL,
    )
    return hashlib.sha256(blanked.encode("utf-8")).hexdigest()


def git_status_porcelain(
    root: Path,
    pathspecs: list[str] | None = None,
) -> str:
    """Return stripped `git status --porcelain` output for root.

    Empty string means clean (or no .git — caller decides). Raises RuntimeError
    if git fails. Shared by check_release_snapshot and sync_lite.require_main_clean.
    """
    if not (root / ".git").exists():
        return ""
    cmd = ["git", "status", "--porcelain"]
    if pathspecs:
        cmd.extend(["--"] + list(pathspecs))
    run = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if run.returncode != 0:
        raise RuntimeError(
            f"git status failed in {root}: {(run.stderr or '').strip()}"
        )
    return run.stdout.strip()


# ---------- 1. 启动文件存在性 ----------
def check_startup_files() -> None:
    expect = {
        MAIN / "t2ag.md": "FAIL",
        MAIN / "00_core" / "t2ag_memory.md": "WARN",
        MAIN / "10_case" / "t2ag_case.md": "WARN",
        MAIN / "10_case" / "teacher_overlay.md": "WARN",
        MAIN / "10_case" / "student_info.md": "WARN",
        MAIN / "10_case" / "course_info.md": "WARN",
    }
    for path, level in expect.items():
        if not path.exists():
            rep(level, f"缺少启动文件：{rel(path)}")


def check_student_archive_files() -> None:
    students = MAIN / "10_case" / "students"
    if not students.exists():
        return
    required = (
        "basic_info.md",
        "personality_baseline.md",
        "course_reflections.md",
        "reasoning_patterns.md",
    )
    for folder in sorted(students.iterdir()):
        if not folder.is_dir() or not re.fullmatch(r"S\d+", folder.name):
            continue
        missing = [name for name in required if not (folder / name).exists()]
        if missing:
            rep("WARN", f"学生档案缺文件：{rel(folder)} -> {', '.join(missing)}")


# ---------- 学习使命与课程感想索引 ----------
REFLECTION_HEADER = ["课程代码", "课程名称", "当前感想数量", "最近记录", "最近日期"]
REFLECTION_ID_RE = re.compile(r"^####\s+(REFL-([A-Z0-9]+)-(\d{4}))｜(\d{4}-\d{2}-\d{2})(?:\s+.*)?$")
COURSE_SECTION_RE = re.compile(r"^##\s+([A-Z]{2,}[A-Z0-9]*)\b.*$")


def _pipe_cells(line: str) -> list[str]:
    return [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]


def check_reflection_indexes() -> None:
    """校验感想正文真相源与顶部可重算缓存。"""
    students = MAIN / "10_case" / "students"
    if not students.exists():
        return
    global_ids: dict[str, Path] = {}
    for path in sorted(students.glob("S*/course_reflections.md")):
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        table_rows: dict[str, list[str]] = {}
        for i, line in enumerate(lines):
            if not line.strip().startswith("|") or _pipe_cells(line) != REFLECTION_HEADER:
                continue
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = _pipe_cells(lines[j])
                if cells and cells[0] not in {"", "(空)"}:
                    if len(cells) < len(REFLECTION_HEADER):
                        rep("FAIL", f"课程感想目录字段不足：{rel(path)} 第 {j + 1} 行")
                    else:
                        table_rows[cells[0]] = cells
                j += 1
            break
        else:
            rep("FAIL", f"课程感想缺规定目录表头：{rel(path)}")
            continue

        records: dict[str, list[tuple[str, str]]] = {}
        for line in lines:
            match = REFLECTION_ID_RE.match(line)
            if not match:
                continue
            record_id, code, _, date = match.groups()
            if record_id in global_ids:
                rep("FAIL", f"课程感想 ID 重复：{record_id}（{rel(global_ids[record_id])}、{rel(path)}）")
            else:
                global_ids[record_id] = path
            records.setdefault(code, []).append((record_id, date))

        sections: dict[str, str] = {}
        for i, line in enumerate(lines):
            match = COURSE_SECTION_RE.match(line)
            if not match:
                continue
            code = match.group(1)
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
            sections[code] = "\n".join(lines[i:end])

        for code in sorted(set(table_rows) | set(records) | set(sections)):
            if code not in table_rows:
                rep("FAIL", f"课程感想正文有 {code}，但目录无对应行：{rel(path)}")
                continue
            if code not in sections:
                rep("FAIL", f"课程感想目录有 {code}，但正文无课程段：{rel(path)}")
                continue
            if "学习使命（最后确认：" not in sections[code]:
                rep("FAIL", f"课程段缺学习使命：{rel(path)} / {code}")
            row = table_rows[code]
            actual = records.get(code, [])
            try:
                cached_count = int(row[2])
            except ValueError:
                rep("FAIL", f"课程感想数量不是整数：{rel(path)} / {code} = {row[2]}")
                continue
            if cached_count != len(actual):
                rep("FAIL", f"课程感想数量不一致：{rel(path)} / {code}，目录={cached_count}，正文={len(actual)}")
            expected_id, expected_date = actual[-1] if actual else ("—", "—")
            if row[3] != expected_id or row[4] != expected_date:
                rep("FAIL", f"课程感想最近记录不一致：{rel(path)} / {code}，应为 {expected_id} / {expected_date}")


# ---------- 2. memory 分节预算制 ----------
# 节标题正则：## 节名  [max N]
SECTION_RE = re.compile(r"^##\s+(.*?)\s*\[max\s+(\d+)\]\s*$")
MEMORY_TOTAL_MAX = 180


def check_memory_budget() -> None:
    mem = MAIN / "00_core" / "t2ag_memory.md"
    if not mem.exists():
        return
    lines = mem.read_text(encoding="utf-8").splitlines()
    if len(lines) > MEMORY_TOTAL_MAX:
        rep("FAIL", f"t2ag_memory.md 共 {len(lines)} 行 > 总预算 {MEMORY_TOTAL_MAX}")
    # 逐节数行
    cur_name, cur_max, cur_count = None, None, 0

    def flush():
        if cur_name is not None and cur_count > cur_max:
            rep("FAIL", f"memory 节「{cur_name}」{cur_count} 行 > 预算 {cur_max}（在节内淘汰）")

    for ln in lines:
        m = SECTION_RE.match(ln)
        if m:
            flush()
            cur_name, cur_max, cur_count = m.group(1), int(m.group(2)), 0
        elif cur_name is not None:
            s = ln.strip()
            # 只数实质内容行：跳过空行、引言(>)、HTML 注释
            if s and not s.startswith(">") and not s.startswith("<!--"):
                cur_count += 1
    flush()
    if cur_name is None:
        rep("WARN", "memory 未使用分节预算标记 [max N]，建议启用分节预算制")


# ---------- 3. 版本号一致性 ----------
VER_RE = re.compile(r"(?:版本|version)[^\d]*(\d+\.\d+\.\d+)", re.IGNORECASE)


def _first_version(path: Path) -> str | None:
    if not path.exists():
        return None
    m = VER_RE.search(path.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def check_version_consistency() -> None:
    sources = {
        "t2ag.md": _first_version(MAIN / "t2ag.md"),
        "AGENTS.md": _first_version(ROOT / "AGENTS.md"),
        "README.md": _first_version(ROOT / "README.md"),
        "t2ag_memory.md": _first_version(MAIN / "00_core" / "t2ag_memory.md"),
    }
    found = {k: v for k, v in sources.items() if v}
    uniq = set(found.values())
    if len(uniq) > 1:
        detail = ", ".join(f"{k}={v}" for k, v in found.items())
        rep("FAIL", f"版本号不一致：{detail}")


# ---------- 4. venv / env 审核 ----------
def _git_tracked(pattern: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", pattern],
            capture_output=True, text=True, timeout=10,
        )
        return [l for l in out.stdout.splitlines() if l.strip()]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def check_env_hygiene() -> None:
    if ROOT.name in {"t2ag-skeleton", "t2ag-lite"} and (ROOT / ".venv").exists():
        rep("FAIL", f"{ROOT.name} 不得携带 .venv")

    generated = list(MAIN.rglob("*.pyc")) + [
        path for path in MAIN.rglob("__pycache__") if path.is_dir()
    ]
    if generated:
        rep("FAIL", f"发行内容混入 Python 生成缓存：{', '.join(rel(path) for path in generated[:5])}")

    if ROOT.name == "t2ag-lite":
        readme = ROOT / "README.md"
        if not readme.exists() or "线上模型审查快照" not in readme.read_text(encoding="utf-8"):
            rep("FAIL", "lite 身份声明缺失或仍被误标为运行实例/空白骨架")
        forbidden_exts = {
            ".pdf", ".epub", ".zip", ".7z", ".rar", ".exe", ".dll", ".pyd",
            ".pyc", ".png", ".jpg", ".jpeg", ".webp", ".gif",
        }
        allowed_assets = {(ROOT / "assets" / "fable_snail.png").resolve()}
        forbidden = [
            path for path in ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in forbidden_exts
            and path.resolve() not in allowed_assets
        ]
        if forbidden:
            rep("FAIL", f"lite 混入二进制、缓存或生成资产：{', '.join(rel(path) for path in forbidden[:5])}")

    if not (ROOT / ".git").exists():
        rep("WARN", "无 .git，跳过 venv/env 追踪检查")
        return
    if _git_tracked(".venv/*") or _git_tracked(".venv"):
        rep("FAIL", ".venv 被 git 追踪，请从版本库移除并加 .gitignore")
    env_tracked = _git_tracked(".env") + _git_tracked("*/.env")
    if env_tracked:
        rep("FAIL", ".env 被 git 追踪——移除后【立即轮换所有密钥】")
    # requirements 手写锁版本提醒（不是 FAIL）
    req = ROOT / "requirements.txt"
    if req.exists() and req.read_text(encoding="utf-8").count("\n") > 60:
        rep("WARN", "requirements.txt 超 60 行，疑似 pip freeze 全量导出，建议手写锁直接依赖")


def check_naming_conventions() -> None:
    required = [
        MAIN / "50_playbook" / "naming_conventions.md",
        ROOT / "t2ag_directory_guide.html",
        ROOT / "assets" / "fable_snail.png",
    ]
    for path in required:
        if not path.exists():
            rep("FAIL", f"命名规范或目录册资产缺失：{rel(path)}")

    legacy = [ROOT / "操作目录册.html", ROOT / "tmp", MAIN / "10_case" / "emo"]
    legacy.extend(MAIN.rglob("temppage"))
    legacy.extend(MAIN.rglob("temp_page.md"))
    existing = [path for path in legacy if path.exists()]
    if existing:
        rep("FAIL", f"活动结构残留退役名称：{', '.join(rel(path) for path in existing[:5])}")

    playbook_re = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*\.md$")
    playbook_whitelist = {"_README.md"}
    bad_playbooks = [
        path.name for path in (MAIN / "50_playbook").glob("*.md")
        if not playbook_re.fullmatch(path.name) and path.name not in playbook_whitelist
    ]
    if bad_playbooks:
        rep("FAIL", f"playbook 文件名不是小写 snake_case：{', '.join(bad_playbooks)}")

    course_re = re.compile(r"^[A-Z0-9]+_[A-Za-z][A-Za-z0-9]*$")
    course_root = MAIN / "30_courses"
    if course_root.exists():
        bad_courses = [
            path.name for path in course_root.iterdir()
            if path.is_dir() and path.name != "_shared" and not course_re.fullmatch(path.name)
        ]
        if bad_courses:
            rep("FAIL", f"课程目录名不符合 课程码_PascalCaseTitle：{', '.join(bad_courses)}")

    sibling_roots = [ROOT.parent / name for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")]
    if all(root.exists() for root in sibling_roots):
        # snail: full byte-identity across editions
        snail_files = [root / "assets" / "fable_snail.png" for root in sibling_roots]
        if not all(path.exists() for path in snail_files):
            rep("FAIL", "目录册未同步三发行版：assets/fable_snail.png")
        elif len({_sha256(path) for path in snail_files}) != 1:
            rep("FAIL", "目录册三发行版正文分叉：assets/fable_snail.png")
        # guide HTML: static shell must match; GENERATED blocks may diverge by edition
        # (directory_map reflects each edition's tree — H4 expected diverge, not drift)
        guide_files = [root / "t2ag_directory_guide.html" for root in sibling_roots]
        if not all(path.exists() for path in guide_files):
            rep("FAIL", "目录册未同步三发行版：t2ag_directory_guide.html")
        else:
            shells = {_guide_html_shell_hash(path) for path in guide_files}
            if len(shells) != 1:
                rep(
                    "FAIL",
                    "目录册三发行版静态正文分叉：t2ag_directory_guide.html"
                    "（GENERATED 块以外的叙述应一致；目录地图可按发行版分叉）",
                )



# ---------- 5. 复利回路模式声明检查 ----------
PATTERN_RE = re.compile(r"【模式】复利回路")
SUBTYPE_RE = re.compile(r"【模式】复利回路(·衰减|·积累|·部件)")
DECAY_KEYS = ("域", "时机", "归因层", "消费方", "退出", "再入")
ACCUM_KEYS = ("产出", "存量", "环节", "沉淀", "校准")
LEDGER_KEYS = ("所属回路", "结算", "再入")


def _param_keys(line: str) -> list:
    """Extract parameter key names from a 【参数】or【服务】line."""
    for tag in ("【参数】", "【服务】"):
        if tag in line:
            body = line.split(tag, 1)[1]
            return [seg.split("=", 1)[0].strip() for seg in body.split("｜")]
    return []


def check_pattern_declarations() -> None:
    """检查复利回路模式实例的头部声明（v2：三类别验键名）

    两段各司其职（替换旧「全树缺子型」双报段，禁止只加不删）：
    1. known_instances —— 已登记实例：缺声明 / 缺子型 / 键名校验（逻辑保持 v2）
    2. 全树扫描 —— 排除已登记与模式定义/模板载体，只捕未登记但含声明的野生文件
    显示路径一律相对 MAIN（经 rel()）。
    """
    # Known instances (relative to MAIN)
    known_instances = [
        "00_core/t2ag_problemlog.md",
        "40_field_practices/S002/FP-S002-0001_TradingDiscipline/trade_journal.md",
    ]
    # Add all CourseRun mistake_bank and question_bank
    runs_dir = MAIN / "35_course_runs"
    if runs_dir.is_dir():
        for mb in runs_dir.rglob("mistake_bank.md"):
            known_instances.append(str(mb.relative_to(MAIN)).replace("\\", "/"))
        for qb in runs_dir.rglob("question_bank.md"):
            known_instances.append(str(qb.relative_to(MAIN)).replace("\\", "/"))
    # reasoning_patterns (S001 default template exempt)
    students_dir = MAIN / "10_case" / "students"
    if students_dir.is_dir():
        for rp in students_dir.glob("S*/reasoning_patterns.md"):
            if "S001" in rp.name or "S001" in str(rp.parent):
                continue
            known_instances.append(str(rp.relative_to(MAIN)).replace("\\", "/"))

    known_set = set(known_instances)

    for rel_path in known_instances:
        path = MAIN / rel_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if not PATTERN_RE.search(content):
            rep("WARN", f"复利回路实例缺声明：{rel_path}")
            continue
        # Check subtype marker
        m = SUBTYPE_RE.search(content)
        if not m:
            # 兼容期已关闭（2026-07-24 M2-tail / 批次 I）：无子型 = FAIL
            rep("FAIL", f"复利回路声明缺子型：{rel_path}")
            continue
        subtype = m.group(1)
        lines = content.split("\n")
        if subtype == "·衰减":
            keys = []
            for ln in lines:
                if "【参数】" in ln:
                    keys = _param_keys(ln)
                    break
            missing = [k for k in DECAY_KEYS if k not in keys]
            if missing:
                rep("FAIL", f"复利回路·衰减缺键 {missing}：{rel_path}")
        elif subtype == "·积累":
            keys = []
            for ln in lines:
                if "【参数】" in ln:
                    keys = _param_keys(ln)
                    break
            missing = [k for k in ACCUM_KEYS if k not in keys]
            if missing:
                rep("FAIL", f"复利回路·积累缺键 {missing}：{rel_path}")
        elif subtype == "·部件":
            # Check role=流量台账 in first declaration line
            has_role = any("角色=流量台账" in ln for ln in lines if "【模式】" in ln)
            if not has_role:
                rep("FAIL", f"复利回路·部件缺角色=流量台账：{rel_path}")
            keys = []
            for ln in lines:
                if "【服务】" in ln:
                    keys = _param_keys(ln)
                    break
            missing = [k for k in LEDGER_KEYS if k not in keys]
            if missing:
                rep("FAIL", f"复利回路·部件缺键 {missing}：{rel_path}")

    # 全树扫描（替换旧段）：跳过 known_instances，只捕未登记但含声明的野生文件。
    # 模式定义正文与 new_course_init 模板不是实例，排除。
    pattern_doc_files = {
        "00_core/pattern_retire_loop.md",
        "50_playbook/new_course_init.md",
    }
    skip_dirs = {".venv", ".recovery", ".staging", "node_modules", "__pycache__"}
    for md in MAIN.rglob("*.md"):
        if any(sd in md.parts for sd in skip_dirs):
            continue
        rel_path = str(md.relative_to(MAIN)).replace("\\", "/")
        if rel_path in known_set or rel_path in pattern_doc_files:
            continue
        # 与 known 段一致：S001 默认学生模板豁免，不当野生实例
        if rel_path.startswith("10_case/students/S001/"):
            continue
        content = md.read_text(encoding="utf-8")
        if PATTERN_RE.search(content):
            rep("WARN", f"未登记的复利回路声明：{rel_path}")


# ---------- 宪法分章预算（同 memory 分节预算制） ----------
CH_RE = re.compile(r"^##\s+第.+?章.*?\[max\s+(\d+)\]\s*$")
T2AG_TOTAL_MAX = 400


def check_constitution_budget() -> None:
    t2ag = MAIN / "t2ag.md"
    if not t2ag.exists():
        rep("FAIL", "t2ag.md 缺失，请从 skeleton 恢复")
        return
    lines = t2ag.read_text(encoding="utf-8").splitlines()
    if len(lines) > T2AG_TOTAL_MAX:
        rep("FAIL", f"t2ag.md 共 {len(lines)} 行 > 总预算 {T2AG_TOTAL_MAX}（防复辟：模板/流程正文勿回流）")
    cur_max, cur_count, cur_title = None, 0, None

    def flush():
        if cur_max is not None and cur_count > cur_max:
            rep("FAIL", f"宪法「{cur_title}」{cur_count} 行 > 预算 {cur_max}")

    for ln in lines:
        m = CH_RE.match(ln)
        if m:
            flush()
            cur_max, cur_count, cur_title = int(m.group(1)), 0, ln.strip("# ").split("[")[0].strip()
        elif cur_max is not None:
            s = ln.strip()
            if s and not s.startswith(">") and not s.startswith("<!--"):
                cur_count += 1
    flush()
    if cur_max is None:
        rep("WARN", "t2ag.md 未使用分章预算标记 [max N]，建议按宪法五章结构组织")


# ---------- 结构清单登记检查（防漂移） ----------
# 已知系统部件目录（数字前缀段 + 可选辅助），仓库有而清单未登记 → WARN
def check_manifest_registration() -> None:
    t2ag = MAIN / "t2ag.md"
    if not t2ag.exists():
        return
    manifest = t2ag.read_text(encoding="utf-8")
    # 扫 main/ 下的一级数字前缀目录与关键文件名，检查是否在清单中被提及
    for entry in sorted(MAIN.iterdir()):
        name = entry.name
        if name == "t2ag.md":
            continue
        # 只审数字前缀部件目录与 .py/.md 顶层部件
        is_numbered = re.match(r"^\d\d_", name)
        if is_numbered or name.endswith((".md", ".py")):
            token = name.split("_", 1)[0] if is_numbered else name
            if token not in manifest and name not in manifest:
                rep("WARN", f"部件未在结构清单登记：{name}（先登记后创建）")


# ---------- 外部学习资料索引检查 ----------
RESOURCE_HEADERS = [
    "资源 ID", "名称", "类型", "URL/本地路径", "适用课程",
    "适用知识点", "用途", "使用方式", "来源与许可", "最后核验日期",
]


def _resource_table_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    """只读取共享索引的规定登记表，不误把正文中的其他表格当资源。"""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        header = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if header != RESOURCE_HEADERS:
            continue
        rows: list[list[str]] = []
        j = i + 2
        while j < len(lines) and lines[j].strip().startswith("|"):
            if "---" not in lines[j]:
                rows.append([c.strip().strip("`") for c in lines[j].strip().strip("|").split("|")])
            j += 1
        return header, rows
    return [], []


def check_external_resources() -> None:
    """检查共享资源索引的路径、字段和唯一性，不联网检查 URL。"""
    old_path = MAIN / "00_core" / "external_resources.md"
    shared_path = MAIN / "30_course_definitions" / "_shared" / "external_resources.md"
    if old_path.exists():
        rep("FAIL", f"旧资源索引仍在 00_core：{rel(old_path)}")
    if not shared_path.exists():
        rep("FAIL", f"共享资源索引缺失：{rel(shared_path)}")
        return

    header, rows = _resource_table_rows(shared_path)
    if header != RESOURCE_HEADERS:
        rep("FAIL", f"共享资源索引缺少规定表头：{rel(shared_path)}")
        return

    ids: dict[str, int] = {}
    locations: dict[str, int] = {}
    for row_no, row in enumerate(rows, start=1):
        if len(row) < len(RESOURCE_HEADERS):
            rep("FAIL", f"共享索引第 {row_no} 行字段不足：{rel(shared_path)}")
            continue
        resource_id = row[0].strip()
        location = row[3].strip().strip("`")
        if resource_id in ids:
            rep("FAIL", f"资源 ID 重复：{resource_id}（第 {ids[resource_id]}、{row_no} 行）")
        elif resource_id:
            ids[resource_id] = row_no
        if location in locations:
            rep("FAIL", f"资源 URL/本地路径重复：{location}（第 {locations[location]}、{row_no} 行）")
        elif location and location not in {"—", "-"}:
            locations[location] = row_no

        if re.fullmatch(r"https?://[^\s|`]+", location):
            continue
        if "://" in location or location.startswith("www."):
            rep("FAIL", f"在线 URL 格式无效：{location}")
            continue
        if not location or location in {"—", "-"}:
            rep("FAIL", f"资源 {resource_id} 缺少 URL/本地路径")
            continue
        candidates = [
            (ROOT / location).resolve(),
            (MAIN / location).resolve(),
            (shared_path.parent / location).resolve(),
        ]
        if ROOT.name != "t2ag-lite" and not any(p.exists() for p in candidates):
            rep("FAIL", f"登记的本地路径不存在：{location}")

    active_roots = [MAIN / "t2ag.md"]
    for dirname in ("10_case", "12_activity_records", "20_groups", "25_general", "40_field_practices", "50_playbook"):
        root = MAIN / dirname
        if root.exists():
            active_roots.extend(root.rglob("*.md"))
    courses = MAIN / "30_courses"
    if courses.exists():
        active_roots.extend(courses.glob("*/*_book/README.md"))
    # 新 Definition 教材 README
    defs_root = MAIN / "30_course_definitions"
    if defs_root.exists():
        active_roots.extend(defs_root.glob("*/*_book/README.md"))
    old_tokens = ("00_core/external_resources.md", "main/00_core/external_resources.md")
    for path in active_roots:
        content = path.read_text(encoding="utf-8", errors="ignore")
        if any(token in content for token in old_tokens):
            rep("FAIL", f"活动规则仍引用旧资源索引路径：{rel(path)}")



# ---------- 课程生命周期、容量组合与进度节点 ----------
VALID_LIFECYCLE = {"planned", "ongoing", "completed", "dropped"}
VALID_NODE_STATES = {"queued", "in_progress", "completed", "superseded"}
VALID_CHECKPOINT_STATES = {"queued", "arrived", "pending", "confirmed", "archived"}


def _frontmatter(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8-sig", errors="ignore")
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    return dict(re.findall(r"^([a-z_]+):\s*(.*?)\s*$", match.group(1), re.MULTILINE))


def _list_value(raw: str) -> list[str]:
    return re.findall(r"[A-Z]{2,4}\d{3,4}[A-Z]?", raw or "")


def _discover_new_course_runs() -> list[tuple[Path, dict[str, str]]]:
    """发现新路径 CourseRun：35_course_runs/<case_id>/CR-*/course_status.md。

    返回 [(course_status_path, frontmatter_dict), ...]。
    """
    results: list[tuple[Path, dict[str, str]]] = []
    runs_root = MAIN / "35_course_runs"
    if not runs_root.is_dir():
        return results
    for status in sorted(runs_root.glob("*/CR-*/course_status.md")):
        fm = _frontmatter(status)
        results.append((status, fm))
    return results


def _discover_new_definitions() -> list[tuple[Path, dict[str, str]]]:
    """发现新路径 CourseDefinition：30_course_definitions/<id>_<title>/course_definition.md。

    返回 [(course_definition_path, frontmatter_dict), ...]。
    """
    results: list[tuple[Path, dict[str, str]]] = []
    defs_root = MAIN / "30_course_definitions"
    if not defs_root.is_dir():
        return results
    for d in sorted(defs_root.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        carrier = d / "course_definition.md"
        if carrier.is_file():
            fm = _frontmatter(carrier)
            results.append((carrier, fm))
    return results


def _group_meta(path: Path) -> dict[str, str]:
    data = _frontmatter(path)
    if data:
        return data
    content = path.read_text(encoding="utf-8-sig", errors="ignore")
    block = re.search(r"<!--\s*T2AG_CAPACITY_GROUP(.*?)-->", content, re.DOTALL)
    return dict(re.findall(r"^([a-z_]+):\s*(.*?)\s*$", block.group(1), re.MULTILINE)) if block else {}


def check_course_group_rules() -> None:
    """生命周期与 capacity group 独立；组外 ongoing 课程合法。"""
    groups_dir = MAIN / "20_groups"
    courses_dir = MAIN / "30_courses"

    # 1. 旧路径课程状态
    old_codes: dict[str, str] = {}  # code -> lifecycle
    for status in _iter_legacy_course_status():
        legacy_path_hit("course_group_old_status", rel(status))
        data = _frontmatter(status)
        code = data.get("course", status.parent.name.split("_", 1)[0])
        lifecycle = data.get("lifecycle_status", "")
        if lifecycle not in VALID_LIFECYCLE:
            rep("FAIL", f"课程 lifecycle_status 非法或缺失：{rel(status)} = {lifecycle or 'MISSING'}")
        else:
            old_codes[code] = lifecycle

    # 2. 新路径 CourseRun：按 case_id 分组
    new_runs_by_case: dict[str, dict[str, str]] = {}  # case_id -> {def_id: lifecycle}
    all_new_runs: list[tuple[Path, dict[str, str]]] = _discover_new_course_runs()
    for status, data in all_new_runs:
        def_id = data.get("course_definition_id", "")
        lifecycle = data.get("lifecycle_status", "")
        case_id = data.get("case_id", "")
        if not def_id:
            continue
        if lifecycle not in VALID_LIFECYCLE:
            rep("FAIL", f"新 CourseRun lifecycle_status 非法或缺失：{rel(status)} = {lifecycle or 'MISSING'}")
            continue
        # 新旧碰撞：只有旧课程码与新 Definition 同码时才报告
        if def_id in old_codes:
            legacy_path_hit("course_group_dual_path_collision", def_id)
            rep("FAIL", f"课程同时存在于新旧路径，不得静默选择：{def_id}")
        new_runs_by_case.setdefault(case_id, {})
        new_runs_by_case[case_id][def_id] = lifecycle

    # 3. 确定当前 Case
    current_case = ""
    si_path = MAIN / "10_case" / "student_info.md"
    if si_path.exists():
        si_content = si_path.read_text(encoding="utf-8-sig", errors="ignore")
        sn_match = re.search(r"指向学生库编号[*\s]*[：:]\s*(S\d+)", si_content)
        if sn_match:
            current_case = sn_match.group(1)
    if not current_case and new_runs_by_case:
        if len(new_runs_by_case) == 1:
            current_case = next(iter(new_runs_by_case))
        elif len(new_runs_by_case) > 1:
            rep("FAIL", "旧 G 无 case_id，无法确定当前 Case")

    # 4. 合并课程状态索引：旧 + 当前 Case 的新 Run
    course_states: dict[str, str] = dict(old_codes)
    if current_case and current_case in new_runs_by_case:
        for def_id, lifecycle in new_runs_by_case[current_case].items():
            if def_id not in old_codes:  # 新旧碰撞已在上方报告
                course_states[def_id] = lifecycle

    group_files = sorted(groups_dir.glob("G*.md")) if groups_dir.exists() else []
    if not group_files:
        rep("WARN", "20_groups/ 无容量组合（首次启动后由用户确认创建）")
        return
    active: list[tuple[Path, dict[str, str]]] = []
    for path in group_files:
        meta = _group_meta(path)
        if not meta:
            rep("FAIL", f"课程组缺机器可读元数据：{rel(path)}")
            continue
        if meta.get("status") == "active":
            active.append((path, meta))
    if len(active) != 1:
        rep("FAIL", f"active capacity group 数量应为 1，实际 {len(active)}")
        return

    group_path, meta = active[0]
    members = _list_value(meta.get("course_members", ""))
    if not members:
        rep("FAIL", f"active capacity group 无课程成员：{rel(group_path)}")
    for code in members:
        lifecycle = course_states.get(code)
        if lifecycle is None:
            rep("FAIL", f"active capacity group 引用不存在课程：{code}")
        elif lifecycle in {"planned", "completed", "dropped"}:
            rep("FAIL", f"active capacity group 包含 {lifecycle} 课程：{code}")

    current = meta.get("current_course", "")
    if current and current not in members:
        rep("FAIL", f"current_course 不在 active group 成员中：{current}")

    mem = MAIN / "00_core" / "t2ag_memory.md"
    if mem.exists():
        pointer = re.search(r"当前课程组[^G]*?(G\d+)", mem.read_text(encoding="utf-8-sig", errors="ignore"))
        if pointer and pointer.group(1) != group_path.stem:
            rep("FAIL", f"memory 课程组指针 {pointer.group(1)} 与 active group {group_path.stem} 不一致")


def check_progress_nodes() -> None:
    def _check_one_status(status: Path, data: dict[str, str]) -> None:
        if data.get("lifecycle_status") != "ongoing":
            return
        nodes_name = data.get("progress_nodes", "")
        if not nodes_name:
            if data.get("progress_nodes_status") in {"lazy_on_resume", "lazy_on_activation"}:
                rep("INFO", f"组外 ongoing 课程尚未迁移进度节点：{rel(status)}")
                return
            rep("FAIL", f"ongoing 课程缺 progress_nodes：{rel(status)}")
            return
        nodes = status.parent / nodes_name
        if not nodes.exists():
            rep("FAIL", f"progress_nodes 文件不存在：{rel(nodes)}")
            return
        content = nodes.read_text(encoding="utf-8-sig", errors="ignore")
        node_rows = re.findall(r"^\|\s*([A-Z0-9-]+)\s*\|.*?\|\s*(queued|in_progress|completed|superseded)\s*\|", content, re.MULTILINE)
        checkpoint_rows = re.findall(r"^\|\s*([A-Z0-9-]+)\s*\|\s*([A-Z0-9-]+)\s*\|.*?\|\s*(queued|arrived|pending|confirmed|archived)\s*\|", content, re.MULTILINE)
        node_ids = [row[0] for row in node_rows]
        checkpoint_ids = [row[0] for row in checkpoint_rows]
        if len(node_ids) != len(set(node_ids)) or len(checkpoint_ids) != len(set(checkpoint_ids)):
            rep("FAIL", f"进度节点 ID 重复：{rel(nodes)}")
        current_node = data.get("current_completion_node", "")
        current_checkpoint = data.get("current_checkpoint", "")
        if current_node not in node_ids:
            rep("FAIL", f"当前 completion node 不存在：{current_node}（{rel(status)}）")
        if current_checkpoint not in checkpoint_ids:
            rep("FAIL", f"当前 checkpoint 不存在：{current_checkpoint}（{rel(status)}）")
        parents = {row[1] for row in checkpoint_rows}
        missing_parents = sorted(parents - set(node_ids))
        if missing_parents:
            rep("FAIL", f"checkpoint parent 不存在：{missing_parents}（{rel(nodes)}）")
        current_rows = [row for row in checkpoint_rows if row[0] == current_checkpoint]
        if current_rows and current_rows[0][2] != data.get("checkpoint_state"):
            rep("FAIL", f"course_status 与 progress_nodes checkpoint 状态不一致：{rel(status)}")
        if data.get("course_driver") == "textbook":
            live = [row for row in checkpoint_rows if row[2] != "archived"]
            if len(live) > 12:
                rep("FAIL", f"教材当前 checkpoint 超过 12 个：{rel(nodes)} = {len(live)}")

    for status in _iter_legacy_course_status():
        legacy_path_hit("progress_nodes_old_status", rel(status))
        _check_one_status(status, _frontmatter(status))
    # 新路径 CourseRun
    for status, data in _discover_new_course_runs():
        _check_one_status(status, data)


def check_generated_state() -> None:
    refresh = MAIN / "70_tools" / "t2ag_state_refresh.py"
    if not refresh.exists():
        rep("FAIL", f"缺确定性状态刷新器：{rel(refresh)}")
        return
    run = subprocess.run(
        [sys.executable, str(refresh), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if run.returncode:
        detail = (run.stdout + run.stderr).strip().replace("\n", "；")
        rep("FAIL", f"生成缓存漂移或区块不唯一：{detail}")


def check_artifact_registry() -> None:
    registry = MAIN / "70_tools" / "artifact_registry.json"
    if not registry.exists():
        rep("FAIL", f"缺 artifact 注册表：{rel(registry)}")
        return
    try:
        payload = json.loads(registry.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        rep("FAIL", f"artifact 注册表不可解析：{exc}")
        return
    ids: set[str] = set()
    redirects: dict[str, dict[str, str]] = {}
    canonical_paths: set[str] = set()
    for item in payload.get("artifacts", []):
        artifact_id = item.get("artifact_id", "")
        canonical = item.get("canonical_path", "").replace("\\", "/")
        status = item.get("status", "")
        if not artifact_id or artifact_id in ids:
            rep("FAIL", f"artifact_id 缺失或重复：{artifact_id or 'MISSING'}")
        ids.add(artifact_id)
        if not canonical or canonical in canonical_paths:
            rep("FAIL", f"canonical_path 缺失或重复：{canonical or 'MISSING'}")
        canonical_paths.add(canonical)
        if status not in {"active", "tombstone"}:
            rep("FAIL", f"artifact 状态非法：{artifact_id} = {status}")
        if status == "active" and not (ROOT / canonical).exists():
            rep("FAIL", f"artifact canonical_path 不存在：{artifact_id} -> {canonical}")
        for old in item.get("redirects", []):
            old = old.replace("\\", "/")
            if old in redirects:
                rep("FAIL", f"redirect 路径重复登记：{old}")
            redirects[old] = {"status": status, "canonical": canonical, "id": artifact_id}

    scan_specs: list[tuple[str, Path]] = []
    scan_specs.extend(("current", p) for p in (
        MAIN / "t2ag.md",
        MAIN / "00_core" / "t2ag_memory.md",
        MAIN / "10_case" / "course_info.md",
    ) if p.exists())
    for status in _iter_legacy_course_status():
        legacy_path_hit("artifact_scan_old_status", rel(status))
        lifecycle = _frontmatter(status).get("lifecycle_status", "")
        scan_specs.append(("current" if lifecycle == "ongoing" else "future", status))
    # 新路径 CourseRun
    for status, data in _discover_new_course_runs():
        lifecycle = data.get("lifecycle_status", "")
        scan_specs.append(("current" if lifecycle == "ongoing" else "future", status))
    # 新路径 CourseDefinition：至少一个 ongoing Run 按 current，否则 future
    _new_def_has_ongoing: dict[str, bool] = {}
    for _st, _d in _discover_new_course_runs():
        _did = _d.get("course_definition_id", "")
        if _did and _d.get("lifecycle_status") == "ongoing":
            _new_def_has_ongoing[_did] = True
    for def_path, def_data in _discover_new_definitions():
        def_id = def_data.get("course_definition_id", "")
        scope = "current" if _new_def_has_ongoing.get(def_id) else "future"
        scan_specs.append((scope, def_path))
    for group in sorted((MAIN / "20_groups").glob("G*.md")) if (MAIN / "20_groups").exists() else []:
        scan_specs.append(("current" if _group_meta(group).get("status") == "active" else "future", group))
    for path in sorted((MAIN / "60_journal").glob("*.md")) if (MAIN / "60_journal").exists() else []:
        scan_specs.append(("historical", path))

    path_re = re.compile(r"(?:`|\()((?:main/)[A-Za-z0-9_./-]+\.md)(?:`|\))")
    for scope, path in scan_specs:
        content = path.read_text(encoding="utf-8-sig", errors="ignore")
        for raw in sorted(set(path_re.findall(content))):
            ref = raw.replace("\\", "/")
            if (ROOT / ref).exists():
                continue
            redirect = redirects.get(ref)
            if redirect:
                if redirect["status"] == "active":
                    if scope == "current":
                        rep("WARN", f"当前引用经 redirect 解析：{rel(path)} -> {ref}")
                    elif scope == "future":
                        rep("INFO", f"未来引用经 redirect 解析：{rel(path)} -> {ref}")
                elif scope == "current":
                    rep("FAIL", f"当前引用命中 tombstone：{rel(path)} -> {ref}")
                elif scope == "future":
                    rep("WARN", f"未来引用命中 tombstone：{rel(path)} -> {ref}")
                continue
            if scope == "current":
                rep("FAIL", f"当前执行路径断链：{rel(path)} -> {ref}")
            elif scope == "future":
                rep("WARN", f"未来路径断链：{rel(path)} -> {ref}")
            else:
                rep("WARN", f"历史路径未解析且未登记：{rel(path)} -> {ref}")


# ---------- handoff 元数据与索引一致性 ----------
_HANDOFF_REQUIRED_FIELDS = (
    "handoff_id", "scope", "applies_to", "status", "aging_state",
    "task_match", "created_at", "updated_at", "version_context",
    "supersedes", "superseded_by", "close_condition",
    "canonical_sources", "next_action", "semantic_check",
)
_HANDOFF_SCOPE_ENUM = {"course_session", "project", "topic", "implementation"}
_HANDOFF_STATUS_ENUM = {"active", "resolved", "superseded", "stale", "archived"}
_HANDOFF_AGING_ENUM = {"normal", "check_1", "check_2", "old"}
_ISO8601_TZ_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$"
)


def _parse_handoff_metadata(content: str) -> dict[str, str]:
    """解析文档顶部、第一个 --- 之前的 blockquote 元数据。

    接受中文全角冒号和 ASCII 冒号，接受行尾双空格。
    不扫描正文中的同名文字。
    """
    lines = content.splitlines()
    meta: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            break
        if not stripped.startswith(">"):
            continue
        inner = stripped.lstrip(">").strip()
        if inner.endswith("  "):
            inner = inner[:-2].rstrip()
        m = re.match(r"\*\*(\w+)\*\*\s*[：:]\s*(.*)", inner)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta


def _parse_readme_active_table(content: str) -> list[dict[str, str]]:
    """只解析 README 的「 Active 交接」表，不误读历史表。"""
    lines = content.splitlines()
    rows: list[dict[str, str]] = []
    in_active = False
    header: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#{1,3}\s*Active", stripped):
            in_active = True
            header = []
            continue
        if in_active and re.match(r"^#{1,3}\s", stripped):
            break
        if not in_active:
            continue
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not header:
            header = cells
            continue
        if all(set(c) <= {"-", " ", ":"} for c in cells):
            continue
        row: dict[str, str] = {}
        for i, h in enumerate(header):
            row[h.strip()] = cells[i].strip() if i < len(cells) else ""
        rows.append(row)
    return rows


def check_handoff_aging() -> None:
    if ROOT.name != "t2ag":
        return
    handoff_root = ROOT.parent / "docs" / "handoffs"
    index = handoff_root / "README.md"
    if not index.exists():
        return
    index_content = index.read_text(encoding="utf-8-sig", errors="ignore")

    # --- 解析 Active 索引表 ---
    active_rows = _parse_readme_active_table(index_content)
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    seen_scope_applies: set[tuple[str, str]] = set()
    indexed_handoffs: dict[str, dict[str, str]] = {}  # filename -> row

    for row in active_rows:
        fname = row.get("文件", "").strip("`").strip()
        hid = row.get("handoff_id", "").strip()
        scope = row.get("scope", "").strip()
        applies = row.get("applies_to", "").strip()
        updated = row.get("updated_at", "").strip()
        # 必填单元格非空检查
        _cell_check = {"handoff_id": hid, "scope": scope, "applies_to": applies, "updated_at": updated, "文件": fname}
        _empty_cells = [k for k, v in _cell_check.items() if not v]
        if _empty_cells:
            rep("FAIL", f"Active 索引缺必填单元格 {_empty_cells}：行含 '{hid or fname or scope or applies or '?'}'")
        if not fname:
            continue
        # 重复检查
        if hid and hid in seen_ids:
            rep("FAIL", f"Active 索引 handoff_id 重复：{hid}")
        seen_ids.add(hid)
        if fname in seen_files:
            rep("FAIL", f"Active 索引文件重复：{fname}")
        seen_files.add(fname)
        key = (scope, applies)
        if key in seen_scope_applies:
            rep("FAIL", f"Active 索引 (scope, applies_to) 重复：{key}")
        seen_scope_applies.add(key)
        # 文件存在性
        path = handoff_root / fname
        if not path.exists():
            rep("FAIL", f"active handoff 文件不存在：{fname}")
            continue
        indexed_handoffs[fname] = row
        # 解析文档元数据
        content = path.read_text(encoding="utf-8-sig", errors="ignore")
        doc_meta = _parse_handoff_metadata(content)
        # 文档 status 必须为 active
        doc_status = doc_meta.get("status", "")
        if doc_status != "active":
            rep("FAIL", f"Active 索引中文档实际 status 为 '{doc_status or 'MISSING'}'：{fname}")
            continue
        # 15 字段完整性
        missing = [f for f in _HANDOFF_REQUIRED_FIELDS if f not in doc_meta or not doc_meta[f]]
        if missing:
            rep("FAIL", f"active handoff 缺字段 {missing}：{fname}")
        # 枚举校验
        if doc_meta.get("scope") and doc_meta["scope"] not in _HANDOFF_SCOPE_ENUM:
            rep("FAIL", f"active handoff 非法 scope '{doc_meta['scope']}'：{fname}")
        if doc_status and doc_status not in _HANDOFF_STATUS_ENUM:
            rep("FAIL", f"active handoff 非法 status '{doc_status}'：{fname}")
        aging = doc_meta.get("aging_state", "")
        if aging and aging not in _HANDOFF_AGING_ENUM:
            rep("FAIL", f"active handoff 非法 aging_state '{aging}'：{fname}")
        # 时间校验
        doc_updated = doc_meta.get("updated_at", "")
        if doc_updated == "—":
            rep("FAIL", f"active handoff updated_at 不得为未知值 '—'：{fname}")
        elif doc_updated and not _ISO8601_TZ_RE.match(doc_updated):
            rep("FAIL", f"active handoff updated_at 非 ISO 8601 带时区：'{doc_updated}'：{fname}")
        doc_created = doc_meta.get("created_at", "")
        if doc_created and doc_created != "—" and not _ISO8601_TZ_RE.match(doc_created):
            rep("FAIL", f"active handoff created_at 非 ISO 8601 且非 '—'：'{doc_created}'：{fname}")
        # 索引与文档一致性
        if hid and doc_meta.get("handoff_id") and hid != doc_meta["handoff_id"]:
            rep("FAIL", f"Active 索引 handoff_id 与文档不一致：索引 '{hid}' vs 文档 '{doc_meta['handoff_id']}'：{fname}")
        if scope and doc_meta.get("scope") and scope != doc_meta["scope"]:
            rep("FAIL", f"Active 索引 scope 与文档不一致：{fname}")
        if applies and doc_meta.get("applies_to") and applies != doc_meta["applies_to"]:
            rep("FAIL", f"Active 索引 applies_to 与文档不一致：{fname}")
        if updated and doc_updated and updated != doc_updated:
            rep("FAIL", f"Active 索引 updated_at 与文档不一致：索引 '{updated}' vs 文档 '{doc_updated}'：{fname}")
        if not updated and doc_updated:
            rep("FAIL", f"Active 索引 updated_at 为空但文档为 '{doc_updated}'：{fname}")
        # aging_state 阈值检查
        lines_count = len(content.splitlines())
        chars_count = len(content)
        expected_aging = (
            "old" if lines_count >= 1200 or chars_count >= 90000
            else "check_2" if lines_count >= 800 or chars_count >= 60000
            else "check_1" if lines_count >= 400 or chars_count >= 30000
            else "normal"
        )
        if aging and aging != expected_aging:
            rep("WARN", f"handoff aging_state 应为 {expected_aging}，实际 {aging}：{fname}")
        if expected_aging == "old":
            rep("FAIL", f"active handoff 已达第三次门槛，必须先生成验证后的替代交接：{fname}")

    # --- 反向检查：每个 active 文档必须在索引中 ---
    if handoff_root.is_dir():
        for path in sorted(handoff_root.glob("*.md")):
            if path.name == "README.md":
                continue
            content = path.read_text(encoding="utf-8-sig", errors="ignore")
            doc_meta = _parse_handoff_metadata(content)
            if doc_meta.get("status") == "active" and path.name not in indexed_handoffs:
                rep("FAIL", f"active handoff 未登记索引：{path.name}")


def check_evolution_ids() -> None:
    """检查 t2ag_evolution.md 的 EV-ID 格式、唯一性和状态枚举。"""
    evo_path = MAIN / "60_journal" / "t2ag_evolution.md"
    if not evo_path.exists():
        return
    content = evo_path.read_text(encoding="utf-8", errors="ignore")
    ev_ids = re.findall(r"^###\s+(EV-\d{4})", content, re.MULTILINE)
    valid_statuses = {"observing", "discussing", "decided", "archived"}
    seen: dict[str, int] = {}
    for eid in ev_ids:
        seen[eid] = seen.get(eid, 0) + 1
    for eid, count in seen.items():
        if count > 1:
            rep("FAIL", f"EV-ID 重复：{eid} 出现 {count} 次")
    # 状态枚举检查
    status_lines = re.findall(
        r"^\-\s*\*{0,2}状态\*{0,2}[：:]\s*`?(\w+)`?", content, re.MULTILINE
    )
    for st in status_lines:
        if st not in valid_statuses:
            rep("FAIL", f"EV 状态非法：{st}（允许：{', '.join(sorted(valid_statuses))}）")
    # decided 超 30 天未落地 → WARN
    blocks = re.split(r"^###\s+EV-", content, flags=re.MULTILINE)[1:]
    today = date.today()
    for block in blocks:
        id_match = re.match(r"(\d{4})", block)
        st_match = re.search(r"状态[：:]\s*`?(\w+)`?", block)
        date_match = re.search(r"日期[：:]\s*(\d{4}-\d{2}-\d{2})", block)
        if id_match and st_match and date_match:
            if st_match.group(1) == "decided":
                try:
                    decided_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
                    if (today - decided_date).days > 30:
                        rep(
                            "WARN",
                            f"EV-{id_match.group(1)} 处于 decided 已 "
                            f"{(today - decided_date).days} 天未落地（阈值 30 天）",
                        )
                except ValueError:
                    pass


def check_release_snapshot() -> None:
    if not (ROOT / ".git").exists():
        return
    try:
        dirty = git_status_porcelain(
            ROOT,
            ["main/50_playbook", "main/70_tools", "main/t2ag.md", "cloud"],
        )
    except RuntimeError as exc:
        rep("WARN", f"无法检查发布快照状态：{exc}")
        return
    if dirty:
        rep("WARN", "core-playbook、doctor、宪法或云端协议存在未快照改动；教学可继续，但不得宣称可发布")


def check_guide_generated() -> None:
    """WARN if t2ag_directory_guide.html GENERATED blocks drift from md/README sources."""
    guide = ROOT / "t2ag_directory_guide.html"
    if not guide.is_file():
        return
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    try:
        import build_guide as bg  # type: ignore
    except ImportError:
        rep("WARN", "build_guide.py 不可导入，跳过 guide 注入一致性检查")
        return
    try:
        expected = bg.expected_blocks(ROOT)
    except SystemExit as exc:
        rep("WARN", f"guide 源无法生成：{exc}")
        return
    except Exception as exc:  # noqa: BLE001 — surface any generator failure as WARN
        rep("WARN", f"guide 源生成异常：{exc}")
        return
    html = guide.read_text(encoding="utf-8", errors="replace")
    for name, want in expected.items():
        m = re.search(
            rf"<!-- T2AG_GENERATED:{re.escape(name)} -->(.*?)<!-- /T2AG_GENERATED:{re.escape(name)} -->",
            html,
            re.DOTALL,
        )
        if not m:
            rep(
                "WARN",
                f"guide 缺 T2AG_GENERATED:{name} 锚点（请检查 HTML 或运行 build_guide.py）",
            )
            continue
        got = m.group(1).strip()
        if got != want.strip():
            rep(
                "WARN",
                f"guide GENERATED 块与源不一致：{name}（请运行 python main/70_tools/build_guide.py）",
            )


# ---------- 考试题库检查 ----------
EXAM_META_REQUIRED = ["题号", "类型", "知识节点", "难度档", "已用于教学", "已考", "解答页码", "考前检查备注"]


def _md_table_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    header: list[str] = []
    rows: list[list[str]] = []
    if not path.exists():
        return header, rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            continue
        cells = [c.strip().strip("`") for c in s.strip("|").split("|")]
        if not header:
            header = cells
        else:
            rows.append(cells)
    return header, rows


def _row_value(header: list[str], row: list[str], key: str) -> str:
    for i, h in enumerate(header):
        if key in h and i < len(row):
            return row[i].strip()
    return ""


def check_exam_pool_isolation() -> None:
    """检查考核池隔离、卷夹登记和题级 meta 完整性。"""
    courses_dir = MAIN / "30_courses"

    def _check_exam_dir(exam_dir: Path, course_dir: Path) -> None:
        index = exam_dir / "index.md"
        papers_dir = exam_dir / "papers"
        index_header, index_rows = _md_table_rows(index)
        registered: set[str] = set()
        exam_pool_ids: set[str] = set()

        for row in index_rows:
            exam_id = _row_value(index_header, row, "卷ID") or (row[0].strip() if row else "")
            pool = _row_value(index_header, row, "池别")
            if exam_id and exam_id != "卷ID":
                registered.add(exam_id)
            if exam_id and "考核池" in pool:
                exam_pool_ids.add(exam_id)

        if papers_dir.exists():
            if not index.exists():
                rep("WARN", f"考试题库存在 papers/ 但缺 index.md：{rel(exam_dir)}")
            for paper_dir in sorted(p for p in papers_dir.iterdir() if p.is_dir()):
                if paper_dir.name not in registered:
                    rep("WARN", f"papers/ 卷夹未在 index 登记：{rel(paper_dir)}")

                meta = paper_dir / "meta.md"
                meta_header, meta_rows = _md_table_rows(meta)
                if not meta.exists():
                    rep("WARN", f"卷夹缺 meta.md：{rel(paper_dir)}")
                    continue
                missing = [col for col in EXAM_META_REQUIRED if not any(col in h for h in meta_header)]
                if missing:
                    rep("WARN", f"meta.md 缺列 {missing}：{rel(meta)}")
                if any("解答页码" in h for h in meta_header):
                    for row in meta_rows:
                        qid = _row_value(meta_header, row, "题号")
                        page = _row_value(meta_header, row, "解答页码")
                        if qid and page in {"", "-", "—", "无", "待填"}:
                            rep("WARN", f"meta.md 缺解答页码：{rel(meta)} 题号 {qid}")

        if not exam_pool_ids:
            return

        exam_questions: dict[str, set[str]] = {}
        for exam_id in exam_pool_ids:
            meta = papers_dir / exam_id / "meta.md"
            meta_header, meta_rows = _md_table_rows(meta)
            qids = {
                _row_value(meta_header, row, "题号")
                for row in meta_rows
                if _row_value(meta_header, row, "题号")
            }
            exam_questions[exam_id] = qids

        for md in course_dir.rglob("*.md"):
            if "_exam" in md.parts:
                continue
            rel_parts = set(md.relative_to(course_dir).parts)
            if not any(part.startswith("lesson") or part in {"practice", "practices"} for part in rel_parts):
                continue
            content = md.read_text(encoding="utf-8", errors="ignore")
            for exam_id, qids in exam_questions.items():
                if exam_id in content:
                    for qid in qids:
                        q_patterns = [qid, f"第{qid}题", f"题{qid}", f"Q{qid}"]
                        if any(p and p in content for p in q_patterns):
                            rep("FAIL", f"考核池题号被教学文件引用：{rel(md)} 引用 {exam_id} / {qid}")

    # 旧路径：仅当某课下真有 _exam 容器时计触发
    if courses_dir.exists():
        for exam_dir in courses_dir.glob("*/_exam"):
            if exam_dir.parent.name.startswith("_"):
                continue
            legacy_path_hit("exam_old_exam_dir", rel(exam_dir))
            _check_exam_dir(exam_dir, exam_dir.parent)
    # 新路径 CourseRun
    runs_root = MAIN / "35_course_runs"
    if runs_root.is_dir():
        for exam_dir in runs_root.glob("*/CR-*/_exam"):
            _check_exam_dir(exam_dir, exam_dir.parent)


# ---------- 皮肤系统检查 ----------
def _parse_flat_yaml(path: Path) -> dict[str, str]:
    """解析扁平 YAML 子集（key: value），零依赖。"""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if ":" in s:
            k, _, v = s.partition(":")
            result[k.strip()] = v.strip()
    return result


def check_skin_system() -> None:
    """检查皮肤系统配置完整性。"""
    skin_dir = MAIN / "skin"
    global_yaml = skin_dir / "skin.yaml"
    if not global_yaml.exists():
        rep("WARN", "skin/skin.yaml 不存在（皮肤系统未初始化）")
        return

    config = _parse_flat_yaml(global_yaml)
    active = config.get("active", "")
    if not active:
        rep("FAIL", "skin/skin.yaml 缺少 active 键")
        return

    # 查注册表获取皮肤文件夹名
    reg_key = f"registry.{active}"
    skin_folder = config.get(reg_key, "")
    if not skin_folder:
        rep("FAIL", f"active 皮肤 {active} 未在注册表登记")
        return

    # 检查皮肤文件夹和 skin.yaml 存在
    skin_path = skin_dir / skin_folder
    skin_yaml = skin_path / "skin.yaml"
    if not skin_path.exists() or not skin_yaml.exists():
        rep("FAIL", f"active 皮肤 {active} 的文件夹或 skin.yaml 不存在：{rel(skin_path)}")
        return

    # 检查艺术文件存在
    skin_config = _parse_flat_yaml(skin_yaml)
    art_file = skin_config.get("art_file", "")
    if art_file:
        art_path = skin_path / art_file
        if not art_path.exists():
            rep("FAIL", f"active 皮肤的艺术文件不存在：{rel(art_path)}")

    # 检查未登记的 SK 开头文件夹
    if skin_dir.exists():
        registered = {v.strip() for k, v in config.items() if k.startswith("registry.")}
        for d in sorted(skin_dir.iterdir()):
            if d.is_dir() and d.name.startswith("SK") and d.name not in registered:
                rep("WARN", f"未登记的皮肤文件夹：{rel(d)}")

    # 检查 welcome_msg 是否包含疑似指令词（外观不得成为 overlay 后门）
    welcome = skin_config.get("welcome_msg", "")
    if welcome:
        instruction_words = ["必须", "规则", "进度", "禁止", "要求", "应该", "不得"]
        for w in instruction_words:
            if w in welcome:
                rep("WARN", f"active 皮肤 welcome_msg 含疑似指令词「{w}」（外观不得携带教学语义）")
                break


# ---------- overlay 引用检查 ----------
def check_overlay_references() -> None:
    """检查 20_groups/overlays/ 的引用完整性。"""
    groups_dir = MAIN / "20_groups"
    overlays_dir = groups_dir / "overlays"
    if not overlays_dir.exists():
        return  # skeleton 初始状态无 overlays

    # 收集所有 overlay 文件名
    overlay_files = set()
    for f in overlays_dir.glob("overlay_*.md"):
        overlay_files.add(f.name)

    if not overlay_files:
        return  # 空目录，跳过

    # 收集所有 Gxx.md 中引用的 overlay 路径
    referenced_overlays: set[str] = set()
    group_files = list(groups_dir.glob("G*.md"))
    for gf in group_files:
        content = gf.read_text(encoding="utf-8")
        # 匹配 overlays/overlay_xxx.md 引用
        for m in re.finditer(r"overlays/(overlay_\w+\.md)", content):
            referenced_overlays.add(m.group(1))

    # 1. 孤儿 overlay：overlays/ 下文件未被任何 Gxx.md 引用 → WARN
    for orphan in sorted(overlay_files - referenced_overlays):
        rep("WARN", f"overlay 孤儿文件（未被任何 Gxx.md 引用）：overlays/{orphan}")

    # 2. 断链：Gxx.md 引用的 overlay 路径不存在 → FAIL
    for broken in sorted(referenced_overlays - overlay_files):
        rep("FAIL", f"Gxx.md 引用了不存在的 overlay：overlays/{broken}")


# ---------- R 绑定检查（第一阶段：冻结契约） ----------
R_STATUS_RE = re.compile(r"(?:状态|binding_status)\*{0,2}\s*[：:]\s*(\w+)")
R_SUBTYPE_RE = re.compile(r"(?:子型|课程类型|course_type)\*{0,2}\s*[：:]\s*(\w+)")

# 主实例 R 兼容注册表
LEGACY_R_REGISTRY = MAIN / "70_tools" / "legacy_r_registry.json"


def _load_legacy_r_registry() -> dict:
    """加载实例级 R 兼容注册表，返回 {filename: {category, status}}。"""
    if not LEGACY_R_REGISTRY.exists():
        return {}
    try:
        data = json.loads(LEGACY_R_REGISTRY.read_text(encoding="utf-8"))
        return {e["file"]: e for e in data.get("entries", [])}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def check_general_track() -> None:
    """第一阶段 R 冻结契约检查。

    规则：
    1. legacy_r_registry.json 恰好登记 PHIL 和 DS
    2. 登记文件实际存在
    3. PHIL 类别为 legacy_reading、文件子型为 reading
    4. DS 类别为 legacy_project、文件子型为 project
    5. 两者均不是 active/reading
    6. LOGIC 不在 registry
    7. 25_general/ 出现未登记的新 R 文件 → FAIL
    8. memory 不把 frozen/idle 文件列为 active
    """
    # --- registry 结构检查 ---
    registry = _load_legacy_r_registry()
    expected_files = {"PHIL1101r_ZhouYi.md", "DS1001r_Kaggle.md"}
    registered_files = set(registry.keys())
    general_dir = MAIN / "25_general"
    disk_r_files = []
    if general_dir.exists():
        disk_r_files = [
            f for f in sorted(general_dir.glob("*.md")) if f.name != "_README.md"
        ]

    # skeleton 空模板：无实例 R 文件时，registry 必须为空（不得拷贝 main 实例登记）
    if ROOT.name == "t2ag-skeleton" and not disk_r_files:
        if registered_files:
            rep(
                "FAIL",
                f"skeleton legacy_r_registry 不得含实例条目：{sorted(registered_files)}",
            )
        # 跳过 main/lite 的「恰好 PHIL+DS」契约；其余 memory 指针仍检查
        memory_path = MAIN / "00_core" / "t2ag_memory.md"
        if memory_path.exists():
            mem_content = memory_path.read_text(encoding="utf-8")
            for line in mem_content.splitlines():
                if "R 活跃绑定" in line or "通识轨活跃项目" in line:
                    if any(kw in line for kw in ("active", "reading")):
                        rep("FAIL", f"memory 把 frozen R 文件列为 active：{line.strip()}")
                    break
        return

    if registered_files != expected_files:
        extra = registered_files - expected_files
        missing = expected_files - registered_files
        if extra:
            rep("FAIL", f"legacy_r_registry 含多余条目：{sorted(extra)}")
        if missing:
            rep("FAIL", f"legacy_r_registry 缺少条目：{sorted(missing)}")

    # LOGIC 不得在 registry
    if "LOGIC1001r_SYSULogicCurriculum.md" in registered_files:
        rep("FAIL", "LOGIC1001r 不得登记在 legacy_r_registry")

    # --- 登记文件存在性 + 类别/子型/状态检查 ---
    for fname, entry in registry.items():
        fpath = general_dir / fname
        if not fpath.exists():
            rep("FAIL", f"registry 登记的文件不存在：{fname}")
            continue

        content = fpath.read_text(encoding="utf-8")
        category = entry.get("category", "")
        reg_status = entry.get("status", "")

        # 文件子型
        subtype_m = R_SUBTYPE_RE.search(content)
        subtype = subtype_m.group(1).strip().lower() if subtype_m else ""

        # 文件状态
        status_m = R_STATUS_RE.search(content)
        file_status = status_m.group(1).strip().lower() if status_m else ""

        # PHIL: category=legacy_reading, 子型=reading
        if fname == "PHIL1101r_ZhouYi.md":
            if category != "legacy_reading":
                rep("FAIL", f"PHIL1101r registry 类别应为 legacy_reading，实际={category}")
            if subtype and subtype != "reading":
                rep("FAIL", f"PHIL1101r 文件子型应为 reading，实际={subtype}")

        # DS: category=legacy_project, 子型=project
        if fname == "DS1001r_Kaggle.md":
            if category != "legacy_project":
                rep("FAIL", f"DS1001r registry 类别应为 legacy_project，实际={category}")
            if subtype and subtype != "project":
                rep("FAIL", f"DS1001r 文件子型应为 project，实际={subtype}")

        # 两者均不得 active/reading
        if file_status in ("active", "reading"):
            rep("FAIL", f"冻结 R 文件不得为 active/reading：{fname}（状态={file_status}）")
        if reg_status != "frozen":
            rep("FAIL", f"registry 状态应为 frozen：{fname}（实际={reg_status}）")

    # --- 未登记新 R 文件检查 ---
    if general_dir.exists():
        r_files = sorted(general_dir.glob("*.md"))
        r_files = [f for f in r_files if f.name != "_README.md"]
        for rf in r_files:
            if rf.name not in registered_files:
                rep("FAIL", f"25_general/ 出现未登记的新 R 文件：{rf.name}")

    # --- memory 指针检查 ---
    memory_path = MAIN / "00_core" / "t2ag_memory.md"
    if memory_path.exists():
        mem_content = memory_path.read_text(encoding="utf-8")
        for line in mem_content.splitlines():
            if "R 活跃绑定" in line or "通识轨活跃项目" in line:
                # 不得把 frozen 文件列为 active
                if any(kw in line for kw in ("active", "reading")):
                    rep("FAIL", f"memory 把 frozen R 文件列为 active：{line.strip()}")
                break


# ---------- 课程驱动与知识点错题库 ----------
VALID_COURSE_DRIVERS = {"textbook", "goal", "project", "praxis"}
VALID_MISTAKE_STATES = {"active", "maintenance", "aged"}


def check_course_drivers() -> None:
    def _check_one_driver(status: Path) -> None:
        content = status.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"^course_driver:\s*([a-z]+)\s*$", content, re.MULTILINE)
        if not match:
            rep("FAIL", f"course_status 缺 course_driver：{rel(status)}")
            return
        driver = match.group(1)
        if driver not in VALID_COURSE_DRIVERS:
            rep("FAIL", f"course_driver 非法：{rel(status)} = {driver}")
        if driver == "praxis" and "本课程的完善需要学生自己生命力的参与" not in content:
            rep("FAIL", f"praxis 课程缺生命力参与声明：{rel(status)}")

    for status in _iter_legacy_course_status():
        legacy_path_hit("course_drivers_old_status", rel(status))
        _check_one_driver(status)
    # 新路径 CourseRun
    for status, _data in _discover_new_course_runs():
        _check_one_driver(status)


# ---------- 教材 working_pages 预加载验收 ----------
def _page_numbers(raw: str) -> list[int]:
    return [int(value) for value in re.findall(r"\d+", raw)]


def check_working_page_windows() -> None:
    """机械核对教材页窗口；人工校对质量仍由视觉复核负责。"""

    def _check_one_source(source: Path) -> None:
        content = source.read_text(encoding="utf-8", errors="ignore")
        window_match = re.search(r"^>\s*当前 temp 窗口：\[([^\]]+)\]", content, re.MULTILINE)
        page_match = re.search(r"^>\s*当前讲授页：第\s*(\d+)\s*页", content, re.MULTILINE)
        if not window_match or not page_match:
            rep("FAIL", f"教材缓存缺当前页/窗口头：{rel(source)}")
            return

        window = _page_numbers(window_match.group(1))
        current = int(page_match.group(1))
        base_window = [current - 1, current, current + 1, current + 2]
        if not 4 <= len(window) <= 6:
            rep("FAIL", f"教材窗口页数必须为 4–6：{rel(source)} = {window}")
        if window != list(range(window[0], window[0] + len(window))):
            rep("FAIL", f"教材窗口必须连续且递增：{rel(source)} = {window}")
        if not set(base_window).issubset(window):
            rep("FAIL", f"教材窗口未覆盖前一页+当前页+后两页：{rel(source)} 当前={current} 窗口={window}")

        course_dir = source.parents[2]
        status = course_dir / "course_status.md"
        if not status.exists():
            rep("FAIL", f"教材缓存找不到 course_status：{rel(source)}")
        else:
            status_content = status.read_text(encoding="utf-8", errors="ignore")
            status_page = re.search(r"^textbook_page:\s*(\d+)\s*$", status_content, re.MULTILINE)
            status_window = re.search(r"^working_pages_window:\s*\[([^\]]+)\]\s*$", status_content, re.MULTILINE)
            if not status_page or not status_window:
                rep("FAIL", f"course_status 缺 textbook_page/working_pages_window：{rel(status)}")
            else:
                saved_page = int(status_page.group(1))
                saved_window = _page_numbers(status_window.group(1))
                if saved_page != current:
                    rep("FAIL", f"course_status 与教材缓存当前页不一致：{rel(status)} {saved_page} != {current}")
                if saved_window != window:
                    rep("FAIL", f"course_status 与教材缓存窗口不一致：{rel(status)} {saved_window} != {window}")

        working = source.parent
        is_lite = ROOT.name == "t2ag-lite"
        for number in window:
            page_png = working / "pages" / f"page{number}.png"
            raw_ocr = working / "raw_ocr" / f"page_{number}_raw.txt"
            # lite 禁止混入 PNG；原图由 main 持有，审查快照只验 OCR/摘录文本
            artifacts = [] if is_lite else [(page_png, "原图")]
            artifacts.append((raw_ocr, "原始 OCR"))
            for artifact, label in artifacts:
                if not artifact.exists() or artifact.stat().st_size == 0:
                    rep("FAIL", f"教材窗口缺{label}：{rel(artifact)}")
            if not re.search(rf"^##\s+第\s*{number}\s+页\s*$", content, re.MULTILINE):
                rep("FAIL", f"教材摘录缺第 {number} 页校对章节：{rel(source)}")
            row = re.search(rf"^\|\s*{number}\s*\|[^\n]+$", content, re.MULTILINE)
            if not row:
                rep("FAIL", f"教材状态表缺第 {number} 页：{rel(source)}")
                continue
            cells = _pipe_cells(row.group(0))
            if len(cells) < 5 or cells[1:5] != ["✓", "✓", "✓", "✓"]:
                rep("FAIL", f"教材第 {number} 页未完成扫描/OCR/校对/加载四门：{rel(source)}")

    # 旧路径：仅当 source_excerpt 真实存在时计触发
    courses = MAIN / "30_courses"
    if courses.exists():
        for source in sorted(courses.glob("*/lesson*/working_pages/source_excerpt.md")):
            if source.parents[2].name.startswith("_"):
                continue
            legacy_path_hit("working_pages_old_source", rel(source))
            _check_one_source(source)
    # 新路径 CourseRun
    runs_root = MAIN / "35_course_runs"
    if runs_root.is_dir():
        for source in sorted(runs_root.glob("*/CR-*/lesson*/working_pages/source_excerpt.md")):
            _check_one_source(source)


def _without_fenced_code(content: str) -> str:
    return re.sub(r"```.*?```", "", content, flags=re.DOTALL)


def check_mistake_bank_generation_template() -> None:
    path = MAIN / "50_playbook" / "new_course_init.md"
    if not path.exists():
        rep("FAIL", "new_course_init.md 不存在，无法验证错题库生成模板")
        return
    content = path.read_text(encoding="utf-8", errors="ignore")
    required = (
        "MISTAKE_BANK_TEMPLATE_V1",
        "next_id: 1",
        "## 活跃知识点",
        "## 维护知识点",
        "## 陈年知识点",
        "知识点键",
        "当堂理解",
        "当前周期摘要",
        "陈年连续正确",
        "最近陈年复习卷",
        "下次陈年日历检查",
        "同一知识点换数字、换题面或换 lesson 再错时",
    )
    missing = [token for token in required if token not in content]
    if missing:
        rep("FAIL", f"new_course_init 错题库生成模板缺字段：{', '.join(missing)}")


def check_mistake_bank_schema() -> None:
    required = (
        "## 活跃知识点", "## 维护知识点", "## 陈年知识点", "知识点键", "当前周期", "状态",
        "当前周期摘要", "陈年连续正确", "最近陈年复习卷", "下次陈年日历检查",
    )
    legacy = ("权重机制", "权重 >", "答对 -1", "权重：")

    def _check_one_bank(path: Path) -> None:
        content = path.read_text(encoding="utf-8", errors="ignore")
        for token in required:
            if token not in content:
                rep("FAIL", f"知识点错题库缺字段「{token}」：{rel(path)}")
        for token in legacy:
            if token in content:
                rep("FAIL", f"知识点错题库残留旧权重规则「{token}」：{rel(path)}")

        body = _without_fenced_code(content)
        entries = list(re.finditer(r"^###\s+M-(\d{4})\s*$", body, re.MULTILINE))
        max_id = 0
        for index, match in enumerate(entries):
            max_id = max(max_id, int(match.group(1)))
            end = entries[index + 1].start() if index + 1 < len(entries) else len(body)
            block = body[match.end():end]
            state_match = re.search(r"^- 状态：([^\n]+)$", block, re.MULTILINE)
            if not state_match:
                rep("FAIL", f"错题条目 M-{match.group(1)} 缺状态：{rel(path)}")
            elif state_match.group(1).strip() not in VALID_MISTAKE_STATES:
                rep("FAIL", f"错题条目 M-{match.group(1)} 状态非法：{rel(path)}")
            for field in ("知识点键", "当前周期", "当前周期摘要", "陈年连续正确", "最近陈年复习卷", "下次陈年日历检查"):
                if not re.search(rf"^- {field}：.+$", block, re.MULTILINE):
                    rep("FAIL", f"错题条目 M-{match.group(1)} 缺{field}：{rel(path)}")

        next_match = re.search(r"^next_id:\s*(\d+)\s*$", content, re.MULTILINE)
        if not next_match:
            rep("FAIL", f"知识点错题库缺 next_id：{rel(path)}")
        elif int(next_match.group(1)) <= max_id:
            rep("FAIL", f"知识点错题库 next_id 未超过现有最大 ID：{rel(path)}")

    # 旧路径：仅当 mistake_bank 真实存在时计触发
    courses = MAIN / "30_courses"
    if courses.exists():
        for path in sorted(courses.glob("*/mistake_bank.md")):
            if path.parent.name.startswith("_"):
                continue
            legacy_path_hit("mistake_bank_old_path", rel(path))
            _check_one_bank(path)
    # 新路径 CourseRun
    runs_root = MAIN / "35_course_runs"
    if runs_root.is_dir():
        for path in sorted(runs_root.glob("*/CR-*/mistake_bank.md")):
            _check_one_bank(path)


# ---------- 云端学习与本地回写协议 ----------
CLOUD_PROTOCOL = "T2AG-CLOUD-1"
CLOUD_SHARED_TOKENS = (
    CLOUD_PROTOCOL,
    "course_status.md",
    "session_id",
    "base_state_id",
    "cloud_project_mode",
    "personal_instance",
    "generic_skeleton",
    "source_evidence",
    "covered",
    "completed",
    "confirmation_state",
    "pending_checkpoint",
    "mastery_evidence",
    "练习答对",
    "正例",
    "反例",
    "继续 / 再讲一遍 / 提问",
    "sync_status: pending",
    "privacy_scope: uploaded_project_only",
    "不得声称",
    "问题：",
    "疑问：",
    "T2AG_CLOUD_CHANGE_DIRECTIVE",
    "T2AG_CLOUD_HANDOFF",
    "T2AG_PROGRESS_RECEIPT",
    "receipt_id",
    "manual_save",
    "safe_degraded",
    "automatic_sync_allowlist",
    "directive_id",
    "handoff_id",
    "expected_cloud_changes",
    "acceptance_criteria",
    "proposed_for_local_review",
)


def check_cloud_sync_protocol() -> None:
    """检查云端协议、Project 提示词和本地同步元数据没有分叉。"""
    playbook = MAIN / "50_playbook" / "cloud_learning_sync.md"
    prompt = ROOT / "cloud" / "T2AG_PROJECT_INSTRUCTIONS.txt"
    state = ROOT / "cloud" / "cloud_sync_state.md"
    cloud_readme = ROOT / "cloud" / "README.md"
    outbox = ROOT / "cloud" / "outbox"
    inbox = ROOT / "cloud" / "inbox"
    inbox_readme = inbox / "README.md"
    for path in (playbook, prompt, state, cloud_readme, outbox, inbox, inbox_readme):
        if not path.exists():
            rep("FAIL", f"云端同步部件缺失：{rel(path)}")
            return

    documents = {
        "云端同步 playbook": playbook.read_text(encoding="utf-8", errors="ignore"),
        "Project 提示词": prompt.read_text(encoding="utf-8", errors="ignore"),
    }
    for label, content in documents.items():
        missing = [token for token in CLOUD_SHARED_TOKENS if token not in content]
        if missing:
            rep("FAIL", f"{label} 缺少关键规则：{', '.join(missing)}")
        if content.count("T2AG_SESSION_CLOSE") < 2:
            rep("FAIL", f"{label} 缺少完整结课块边界")

    state_content = state.read_text(encoding="utf-8", errors="ignore")
    state_required = (
        "protocol_version: T2AG-CLOUD-1",
        "privacy_model: two_scope",
        "existing_project_scope:",
        "automatic_sync_allowlist_status:",
        "automatic_sync_allowlist:",
        "current_cloud_project_mode:",
        "current_base_state_id:",
        "last_synced_session_id:",
        "last_change_directive_id:",
        "last_change_directive_status:",
        "last_cloud_handoff_id:",
        "## 已处理会话",
        "## 部件变更指令",
        "## 云端交接",
    )
    missing = [token for token in state_required if token not in state_content]
    if missing:
        rep("FAIL", f"云端同步状态缺字段：{', '.join(missing)}")
    privacy = re.search(r"automatic_sync_allowlist_status:\s*([a-z_]+)", state_content)
    if not privacy or privacy.group(1) != "approved_minimal_low_risk":
        rep("FAIL", "automatic_sync_allowlist_status 必须是 approved_minimal_low_risk")
    project_mode = re.search(r"current_cloud_project_mode:\s*([a-z_]+)", state_content)
    if not project_mode or project_mode.group(1) not in {"personal_instance", "generic_skeleton"}:
        rep("FAIL", "current_cloud_project_mode 只能是 personal_instance 或 generic_skeleton")

    overlay = MAIN / "10_case" / "teacher_overlay.md"
    mobile = ROOT / "cloud" / "t2ag_mobile_entry.md"
    if mobile.exists():
        mobile_content = mobile.read_text(encoding="utf-8", errors="ignore")
        mobile_bs = re.search(r"^-\s*base_state_id:\s*(\S+)\s*$", mobile_content, re.MULTILINE)
        state_bs = re.search(r"^-\s*current_base_state_id:\s*(\S+)\s*$", state_content, re.MULTILINE)
        mobile_id = mobile_bs.group(1) if mobile_bs else ""
        state_id = state_bs.group(1) if state_bs else ""
        if project_mode and project_mode.group(1) == "personal_instance":
            if not mobile_id or mobile_id in {"UNINITIALIZED", "UNKNOWN", "—"}:
                rep("FAIL", f"personal_instance 的 mobile_entry base_state_id 无效：{mobile_id or '(缺)'}")
            elif state_id and mobile_id != state_id:
                rep(
                    "FAIL",
                    f"mobile_entry base_state_id 与 cloud_sync_state 不一致："
                    f"{mobile_id} != {state_id}",
                )
    if overlay.exists() and mobile.exists():
        overlay_content = overlay.read_text(encoding="utf-8", errors="ignore")
        mobile_content = mobile.read_text(encoding="utf-8", errors="ignore")
        suffix_match = re.search(r"普通教学回复句尾[^`]*`([^`]+)`", overlay_content)
        if not suffix_match:
            rep("FAIL", "teacher_overlay 缺普通教学回复句尾配置")
        else:
            suffix = suffix_match.group(1)
            if f"reply_suffix: {suffix}" not in mobile_content:
                rep("FAIL", "移动端入口与 teacher_overlay 句尾不一致")
            if "reply_suffix_semantics: literal_marker_not_file" not in mobile_content:
                rep("FAIL", "移动端入口未声明句尾是字面标记而非文件")
            if suffix not in documents["Project 提示词"] or "不是文件名或路径" not in documents["Project 提示词"]:
                rep("FAIL", "Project 提示词未同步字面句尾及非文件语义")

    directive_required = (
        "protocol_version", "directive_id", "created_at", "local_t2ag_version", "target_cloud",
        "affected_components", "local_changed_files", "expected_cloud_changes", "acceptance_criteria",
        "attachments_to_send", "migration_notes", "privacy_impact", "reply_required", "sent_at",
        "send_evidence", "status",
    )
    directive_statuses = {"draft", "ready_to_send", "sent", "acknowledged", "closed"}
    for path in sorted(outbox.glob("CD-*.md")):
        content = path.read_text(encoding="utf-8", errors="ignore")
        if content.count("T2AG_CLOUD_CHANGE_DIRECTIVE") < 2:
            rep("FAIL", f"云端变更指令缺块边界：{rel(path)}")
        fields = dict(re.findall(r"^- ([a-z0-9_]+):\s*(.+)$", content, re.MULTILINE))
        missing = [field for field in directive_required if field not in fields]
        if missing:
            rep("FAIL", f"云端变更指令缺字段 {missing}：{rel(path)}")
            continue
        if fields["directive_id"] != path.stem:
            rep("FAIL", f"变更指令 ID 与文件名不一致：{rel(path)}")
        status_value = fields["status"].strip()
        if status_value not in directive_statuses:
            rep("FAIL", f"变更指令状态非法：{rel(path)} = {status_value}")
        if status_value in {"sent", "acknowledged", "closed"}:
            if fields["sent_at"].strip() in {"NONE", "—", "-"} or fields["send_evidence"].strip() in {"NONE", "—", "-"}:
                rep("FAIL", f"已发送的变更指令缺 sent_at/send_evidence：{rel(path)}")
        if "云端同步协议" in fields["affected_components"] and "main/50_playbook/cloud_learning_sync.md" not in fields["attachments_to_send"]:
            rep("FAIL", f"同步协议变更指令未附定义源 cloud_learning_sync.md：{rel(path)}")

    handoff_required = (
        "protocol_version", "handoff_id", "directive_id", "produced_at", "cloud_project",
        "cloud_base_state_id", "changes_applied", "generated_files", "deviations", "verification",
        "open_questions", "proposed_local_changes", "privacy_impact", "status",
    )
    for path in sorted(inbox.glob("CH-*.md")):
        content = path.read_text(encoding="utf-8", errors="ignore")
        if content.count("T2AG_CLOUD_HANDOFF") < 2:
            rep("FAIL", f"云端交接缺块边界：{rel(path)}")
        fields = dict(re.findall(r"^- ([a-z0-9_]+):\s*(.+)$", content, re.MULTILINE))
        missing = [field for field in handoff_required if field not in fields]
        if missing:
            rep("FAIL", f"云端交接缺字段 {missing}：{rel(path)}")
            continue
        if fields["handoff_id"] != path.stem:
            rep("FAIL", f"云端交接 ID 与文件名不一致：{rel(path)}")
        if fields["status"].strip() != "proposed_for_local_review":
            rep("FAIL", f"云端交接初始状态必须是 proposed_for_local_review：{rel(path)}")

    # --- 时效检查（WARN） ---
    today = date.today()
    # 指令表中 ready_to_send 超 7 天
    directive_table = re.search(
        r"## 部件变更指令\s*\n((?:\|.*\n)+)", state_content
    )
    if directive_table:
        for row in directive_table.group(1).strip().splitlines():
            cells = [c.strip() for c in row.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 4 and cells[3] == "ready_to_send":
                try:
                    created = datetime.fromisoformat(cells[1]).date()
                    if (today - created).days > 7:
                        rep(
                            "WARN",
                            f"云端变更指令 {cells[0]} 处于 ready_to_send 已 "
                            f"{(today - created).days} 天（阈值 7 天）",
                        )
                except (ValueError, IndexError):
                    pass
    # 交接表中 local_decision=pending 超 3 天
    handoff_table = re.search(
        r"## 云端交接\s*\n((?:\|.*\n)+)", state_content
    )
    if handoff_table:
        for row in handoff_table.group(1).strip().splitlines():
            cells = [c.strip() for c in row.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 4 and cells[3] == "pending":
                try:
                    produced = datetime.fromisoformat(cells[2]).date()
                    if (today - produced).days > 3:
                        rep(
                            "WARN",
                            f"云端交接 {cells[0]} 待裁决已 "
                            f"{(today - produced).days} 天（阈值 3 天）",
                        )
                except (ValueError, IndexError):
                    pass


# ---------- core-playbook 发行一致性 ----------
CORE_MARKER = "**保护级别**：core-playbook"
REQUIRED_CORE_PLAYBOOKS = {
    "exam_bank_spec.md",
    "exam_protocol.md",
    "first_run.md",
    "git_workflow.md",
    "group_transition.md",
    "handoff_management.md",
    "method_distillation.md",
    "naming_conventions.md",
    "progress_tracking.md",
    "skin_playbook.md",
}


def _tagged_core_playbooks(root: Path) -> dict[str, Path]:
    folder = root / "main" / "50_playbook"
    if not folder.exists():
        return {}
    result: dict[str, Path] = {}
    for path in sorted(folder.glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"^\*\*保护级别\*\*：core-playbook\s*$", content, re.MULTILINE):
            result[path.name] = path
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_core_playbook_distribution() -> None:
    local = _tagged_core_playbooks(ROOT)
    for name in sorted(REQUIRED_CORE_PLAYBOOKS - set(local)):
        rep("FAIL", f"缺少必需 core-playbook 或保护标记：50_playbook/{name}")

    sibling_roots = [ROOT.parent / name for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")]
    if not all((root / "main" / "50_playbook").exists() for root in sibling_roots):
        return
    distributions = {root.name: _tagged_core_playbooks(root) for root in sibling_roots}
    all_names = set().union(*(set(files) for files in distributions.values()))
    for name in sorted(all_names):
        missing = [repo for repo, files in distributions.items() if name not in files]
        if missing:
            rep("FAIL", f"core-playbook 未同步到 {', '.join(missing)}：{name}")
            continue
        hashes = {repo: _sha256(files[name]) for repo, files in distributions.items()}
        if len(set(hashes.values())) != 1:
            rep("FAIL", f"core-playbook 三版本正文分叉：{name}")


# ---------- 培养方案语义检查 ----------
CURRICULA_REQUIRED_FIELDS = ("plan_id", "role", "institution", "program", "applicable_year", "source_url", "verified_date", "completeness")
VALID_COMPLETENESS = {"full", "summary", "partial"}
VALID_ROLES = {"baseline", "reference"}


def check_curricula_semantics() -> None:
    """检查 15_curricula 培养方案的结构事实和语义约束。

    检查项：
    - frontmatter 必须位于文件开头（第一行）
    - role 与目录位置一致（baseline/ ↔ role: baseline）
    - Case 必须实际引用恰好一个存在的 baseline
    - Case 引用的每个 reference 必须存在
    - plan_id 必须唯一
    - 不得仅用目录文件数量代替 Case 引用检查
    """
    # skeleton 和 lite 不强制要求培养方案实例数据，但必须带通用规则
    if ROOT.name in {"t2ag-skeleton", "t2ag-lite"}:
        # 检查通用领域规则和空培养方案骨架存在
        domain_model = MAIN / "00_core" / "domain_model.md"
        if not domain_model.exists():
            rep("FAIL", "缺少领域模型真相源：00_core/domain_model.md")
        curricula_dir = MAIN / "15_curricula"
        if not curricula_dir.exists():
            rep("FAIL", "缺少 15_curricula 培养方案骨架")
        elif not (curricula_dir / "_README.md").exists():
            rep("FAIL", "缺少 15_curricula/_README.md")
        return

    curricula_dir = MAIN / "15_curricula"
    if not curricula_dir.exists():
        rep("FAIL", "缺少 15_curricula 培养方案区域")
        return

    readme = curricula_dir / "_README.md"
    if not readme.exists():
        rep("FAIL", "缺少 15_curricula/_README.md")
        return

    # 检查 domain_model.md 存在
    domain_model = MAIN / "00_core" / "domain_model.md"
    if not domain_model.exists():
        rep("FAIL", "缺少领域模型真相源：00_core/domain_model.md")

    # 收集所有培养方案文件
    baseline_dir = curricula_dir / "baseline"
    references_dir = curricula_dir / "references"
    baseline_files = list(baseline_dir.glob("*.md")) if baseline_dir.exists() else []
    reference_files = list(references_dir.glob("*.md")) if references_dir.exists() else []
    all_plan_files = baseline_files + reference_files

    # 解析每份方案的 frontmatter
    plan_ids: set[str] = set()
    plan_id_to_path: dict[str, Path] = {}
    for path in all_plan_files:
        content = path.read_text(encoding="utf-8", errors="ignore")
        # frontmatter 必须位于文件开头（第一行是 ---）
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            rep("FAIL", f"培养方案 frontmatter 必须位于文件开头：{rel(path)}")
            continue
        fields = dict(re.findall(r"^([a-z_]+):\s*(.*?)\s*$", match.group(1), re.MULTILINE))
        missing = [f for f in CURRICULA_REQUIRED_FIELDS if f not in fields or not fields[f]]
        if missing:
            rep("FAIL", f"培养方案缺字段 {missing}：{rel(path)}")
        # 检查 role 合法性
        role = fields.get("role", "")
        if role and role not in VALID_ROLES:
            rep("FAIL", f"培养方案 role 非法：{rel(path)} = {role}")
        # 检查 role 与目录位置一致
        if role == "baseline" and path.parent.name != "baseline":
            rep("FAIL", f"role=baseline 但文件不在 baseline/ 目录：{rel(path)}")
        if role == "reference" and path.parent.name != "references":
            rep("FAIL", f"role=reference 但文件不在 references/ 目录：{rel(path)}")
        # 检查 completeness 合法性
        completeness = fields.get("completeness", "")
        if completeness and completeness not in VALID_COMPLETENESS:
            rep("FAIL", f"培养方案 completeness 非法：{rel(path)} = {completeness}")
        # 检查 plan_id 唯一性
        plan_id = fields.get("plan_id", "")
        if plan_id:
            if plan_id in plan_ids:
                rep("FAIL", f"培养方案 plan_id 重复：{plan_id}")
            plan_ids.add(plan_id)
            plan_id_to_path[plan_id] = path
            # 检查 plan_id 不伪装成课程代码
            if re.fullmatch(r"[A-Z]{2,4}\d{3,4}[A-Z]?r", plan_id):
                rep("FAIL", f"培养方案 ID 不得伪装成课程代码：{plan_id}")

    # 检查 R 索引中不包含培养方案
    general_readme = MAIN / "25_general" / "_README.md"
    if general_readme.exists():
        r_content = general_readme.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\|\s*CUR-[A-Z0-9-]+\s*\|", r_content):
            rep("FAIL", "R 索引中不得包含培养方案 ID（CUR- 开头）")
        for plan_path in all_plan_files:
            if plan_path.name in r_content:
                rep("FAIL", f"培养方案被登记为 R：{rel(plan_path)}")

    # 解析 Case 中的实际 plan_id 引用（从表格中提取 CUR- 开头的 ID）
    case_file = MAIN / "10_case" / "t2ag_case.md"
    if not case_file.exists():
        rep("FAIL", "缺少 Case 文件：10_case/t2ag_case.md")
        return
    case_content = case_file.read_text(encoding="utf-8", errors="ignore")
    case_plan_ids = set(re.findall(r"\b(CUR-[A-Z0-9-]+)\b", case_content))

    # Case 必须引用恰好一个存在的 baseline
    case_baselines = [pid for pid in case_plan_ids if pid in plan_id_to_path and plan_id_to_path[pid].parent.name == "baseline"]
    if len(case_baselines) == 0:
        rep("FAIL", "Case 未引用任何 baseline 培养方案")
    elif len(case_baselines) > 1:
        rep("FAIL", f"Case 引用了多个 baseline：{case_baselines}")

    # Case 引用的每个 plan_id 必须存在
    for pid in case_plan_ids:
        if pid not in plan_id_to_path:
            rep("FAIL", f"Case 引用的培养方案不存在：{pid}")

    # baseline 目录多个文件而 Case 只引用一个 -> FAIL
    if len(baseline_files) > 1 and len(case_baselines) <= 1:
        rep("FAIL", f"baseline 目录有 {len(baseline_files)} 个文件但 Case 只引用 {len(case_baselines)} 个")

    # 目录中的 baseline 必须被 Case 引用（反向检查）
    for path in baseline_files:
        content = path.read_text(encoding="utf-8", errors="ignore")
        m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if m:
            fields = dict(re.findall(r"^([a-z_]+):\s*(.*?)\s*$", m.group(1), re.MULTILINE))
            pid = fields.get("plan_id", "")
            if pid and pid not in case_plan_ids:
                rep("WARN", f"baseline 培养方案未被 Case 引用：{pid}")


def check_domain_model_distribution() -> None:
    """检查 domain_model.md 三发行版一致性。

    开发工作区（三个发行版目录都存在）：要求三个文件全部存在且哈希一致。
    独立发行版运行（只剩自己）：跳过跨仓检查并说明原因。
    """
    sibling_roots = [ROOT.parent / name for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")]
    existing_roots = [root for root in sibling_roots if root.exists()]

    if len(existing_roots) < 3:
        # 独立发行版运行，跳过跨仓检查
        rep("INFO", f"domain_model 跨仓检查跳过：仅检测到 {len(existing_roots)} 个发行版目录（独立运行模式）")
        return

    # 开发工作区：三个文件必须全部存在
    dm_files = {}
    for root in sibling_roots:
        dm = root / "main" / "00_core" / "domain_model.md"
        if dm.exists():
            dm_files[root.name] = dm
        else:
            rep("FAIL", f"domain_model.md 缺失：{root.name}/main/00_core/domain_model.md")

    if len(dm_files) < 3:
        rep("FAIL", f"domain_model.md 三发行版不完整：仅 {list(dm_files.keys())}")
        return

    hashes = {name: _sha256(path) for name, path in dm_files.items()}
    if len(set(hashes.values())) != 1:
        rep("FAIL", f"domain_model.md 三版本分叉：{hashes}")


# ---------- 对象分层迁移：双路径结构检查（结构准备批次） ----------
# 新目标目录（结构准备批次建立的空骨架）
NEW_OBJECT_DIRS = [
    "12_activity_records",
    "20_groups/bindings",
    "30_course_definitions",
    "30_course_definitions/_shared",
    "35_course_runs",
    "40_field_practices",
]

# 旧兼容路径 → 新目标路径（用于同一对象新旧碰撞检测）
LEGACY_TO_NEW = {
    "25_general": "20_groups/bindings",
    "30_courses": "30_course_definitions",
}

# skeleton 不得出现的真实实例标识
_INSTANCE_RE = re.compile(
    r"S0\d{2}|MATH\d{4}[A-Z]?|CS\d{4}|IV\d{4}|PY\d{4}|DS\d{4}r?|"
    r"PHIL\d{4}r?|LOGIC\d{4}r?|CR-S\d|AR-S\d|FP-S\d|"
    r"\bG\d{2}\b|\bP\d{3}\b|\bR\d{3}\b"
)

# ---------- 对象分层枚举（来源：domain_model.md / naming_conventions.md） ----------
_VALID_COURSE_TYPES = {"mastery", "project", "praxis"}
_VALID_DRIVERS = {"textbook", "goal", "project", "praxis"}
_VALID_DEF_STATUS = {"active", "retired"}
_VALID_RUN_LIFECYCLE = {"planned", "ongoing", "completed", "dropped"}
_VALID_AR_STATUS = {"recording", "paused", "closed"}
_VALID_BINDING_STATUS = {"planned", "active", "paused", "ended"}
_VALID_G_STATUS = {"planned", "active", "paused", "archived"}
_TYPE_DRIVER_MAP: dict[str, set[str]] = {
    "mastery": {"textbook", "goal"},
    "project": {"project"},
    "praxis": {"praxis"},
}


def _frontmatter_fields(path: Path) -> dict[str, str]:
    """读取 Markdown 首部 YAML frontmatter 的 key: value 字段。"""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fields: dict[str, str] = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z0-9_]*):\s*(.*?)\s*$", line)
        if m:
            fields[m.group(1)] = m.group(2)
    return fields


def _instance_files(directory: Path) -> list[str]:
    """列出目录中命中真实实例标识的文件/目录名（排除 _README.md）。"""
    hits: list[str] = []
    for p in sorted(directory.rglob("*")):
        if p.name == "_README.md":
            continue
        if _INSTANCE_RE.search(p.name):
            hits.append(str(p.relative_to(MAIN)).replace("\\", "/"))
    return hits


def check_object_layer_migration() -> None:
    """对象分层迁移双路径结构检查（结构准备批次 + 定点返工）。

    规则：
    1. 新目标目录必须存在
    2. skeleton 新目录只允许 _README.md，不得含实例名（文件名+正文）
    3. 按物理位置决定预期对象类型，不得绕过
    4. 缺 frontmatter / 缺 type / type 与路径不符 / 缺必填字段 / ID 不符 → FAIL
    5. 引用完整性检查
    6. 新旧路径碰撞
    7. 同一 CourseRun 同时 active G/R → FAIL
    8. 所有对象 ID 全局唯一
    """
    is_skeleton = ROOT.name == "t2ag-skeleton"

    # 1. 新目录存在性
    for d in NEW_OBJECT_DIRS:
        if not (MAIN / d).is_dir():
            rep("FAIL", f"缺少新目标目录：{d}")

    # 2. skeleton 新目录只允许 _README.md（及系统级共享索引模板），不得含实例名
    # external_resources.md 是跨课共享索引模板，允许出现在 30_course_definitions/_shared/
    _SKELETON_ALLOWED_FILES = {
        "_README.md",
    }
    _SKELETON_ALLOWED_REL = {
        "30_course_definitions/_shared/external_resources.md",
    }
    if is_skeleton:
        for d in NEW_OBJECT_DIRS:
            target = MAIN / d
            if not target.is_dir():
                continue
            for p in sorted(target.rglob("*")):
                if not p.is_file():
                    continue
                rel_main = str(p.relative_to(MAIN)).replace("\\", "/")
                if p.name in _SKELETON_ALLOWED_FILES or rel_main in _SKELETON_ALLOWED_REL:
                    if p.name == "_README.md":
                        content = p.read_text(encoding="utf-8", errors="ignore")
                        hits = _INSTANCE_RE.findall(content)
                        if hits:
                            rep(
                                "FAIL",
                                f"skeleton README 正文含实例标识：{d}/_README.md -> {sorted(set(hits))}",
                            )
                    continue
                rep(
                    "FAIL",
                    f"skeleton 新目录只允许 _README.md（及登记白名单）：{rel_main}",
                )
            hits = _instance_files(target)
            if hits:
                rep("FAIL", f"skeleton 新目录含真实实例名：{hits}")

    # 3. 按物理容器发现对象（错误命名只 FAIL，不导致对象消失）
    _OBJ_REQUIRED: dict[str, list[str]] = {
        "course_definition": ["type", "course_definition_id", "name", "course_type", "default_driver", "prerequisites", "status"],
        "course_run": ["type", "course_run_id", "case_id", "course_definition_id", "lifecycle_status", "course_driver"],
        "activity_record": ["type", "activity_record_id", "case_id", "record_status", "upgraded_to_course_run"],
        "field_practice": ["type", "field_practice_id", "case_id", "practice_status", "linked_course_runs", "evidence_index"],
        "capacity_group": ["type", "group", "status", "course_members", "practice_members"],
        "elastic_binding": ["type", "binding_id", "case_id", "course_run_id", "binding_status"],
    }

    # 对象索引（用于引用完整性）
    idx_definitions: dict[str, dict[str, str]] = {}  # def_id -> fields
    idx_runs: dict[str, dict[str, str]] = {}  # run_id -> fields
    idx_practices: dict[str, dict[str, str]] = {}  # fp_id -> fields
    idx_groups: dict[str, dict[str, str]] = {}  # group_id -> fields
    idx_bindings: dict[str, dict[str, str]] = {}  # binding_id -> fields
    idx_records: dict[str, dict[str, str]] = {}  # ar_id -> fields
    all_ids: dict[str, str] = {}  # id -> location

    def _parse_inline_list(val: str, path: Path, field: str) -> list[str]:
        """解析单行数组 [A, B]；拒绝多行数组和空元素。"""
        val = val.strip()
        if not val:
            return []
        if val == "[]":
            return []
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            raw_items = inner.split(",")
            if any(not x.strip() for x in raw_items):
                rep("FAIL", f"{rel(path)} 字段 {field} 单行数组含空元素：{val[:40]}")
                return [x.strip().strip("'\"") for x in raw_items if x.strip()]
            return [x.strip().strip("'\"") for x in raw_items if x.strip()]
        rep("FAIL", f"{rel(path)} 字段 {field} 不是单行数组格式：{val[:40]}")
        return []

    def _discover_objects() -> list[tuple[Path, str, str]]:
        """容器扫描：返回 (载体文件路径, expected_type, id_field) 列表。"""
        found: list[tuple[Path, str, str]] = []
        # 1. CourseDefinition: 30_course_definitions/ 下除 _shared/下划线前缀外的一级目录
        defs_root = MAIN / "30_course_definitions"
        if defs_root.is_dir():
            for d in sorted(defs_root.iterdir()):
                if d.name.startswith("_"):
                    continue
                if d.is_file():
                    if d.suffix == ".md":
                        rep("FAIL", f"CourseDefinition 载体位置非法（不得位于定义根目录）：{rel(d)}")
                    continue
                if not d.is_dir():
                    continue
                carrier = d / "course_definition.md"
                if carrier.is_file():
                    found.append((carrier, "course_definition", "course_definition_id"))
                else:
                    rep("FAIL", f"CourseDefinition 缺少正式载体 course_definition.md：{rel(d)}")
        # 2. CourseRun: 35_course_runs/<case_id>/ 下所有非下划线前缀实例目录
        runs_root = MAIN / "35_course_runs"
        if runs_root.is_dir():
            for case_dir in sorted(runs_root.iterdir()):
                if not case_dir.is_dir() or case_dir.name.startswith("_"):
                    continue
                for item in sorted(case_dir.iterdir()):
                    if item.name.startswith("_"):
                        continue
                    if item.is_file():
                        if item.suffix == ".md":
                            rep("FAIL", f"CourseRun 载体位置非法（不得位于 Case 根目录）：{rel(item)}")
                        continue
                    if not item.is_dir():
                        continue
                    carrier = item / "course_status.md"
                    if carrier.is_file():
                        found.append((carrier, "course_run", "course_run_id"))
                    else:
                        rep("FAIL", f"CourseRun 缺少正式载体 course_status.md：{rel(item)}")
        # 3. ActivityRecord: 12_activity_records/<case_id>/ 直属 .md 文件
        ar_root = MAIN / "12_activity_records"
        if ar_root.is_dir():
            for case_dir in sorted(ar_root.iterdir()):
                if not case_dir.is_dir() or case_dir.name.startswith("_"):
                    continue
                for item in sorted(case_dir.iterdir()):
                    if item.name.startswith("_"):
                        continue
                    if item.is_dir():
                        nested = [f for f in item.rglob("*.md") if f.name != "_README.md"]
                        if nested:
                            rep("FAIL", f"ActivityRecord 载体位置非法（不得位于嵌套子目录）：{rel(item)}")
                        continue
                    if item.is_file() and item.suffix == ".md":
                        found.append((item, "activity_record", "activity_record_id"))
        # 4. FieldPractice: 40_field_practices/<case_id>/ 下所有非下划线前缀实例目录
        fp_root = MAIN / "40_field_practices"
        if fp_root.is_dir():
            for case_dir in sorted(fp_root.iterdir()):
                if not case_dir.is_dir() or case_dir.name.startswith("_"):
                    continue
                for item in sorted(case_dir.iterdir()):
                    if item.name.startswith("_"):
                        continue
                    if item.is_file():
                        if item.suffix == ".md":
                            rep("FAIL", f"FieldPractice 载体位置非法（不得位于 Case 根目录）：{rel(item)}")
                        continue
                    if not item.is_dir():
                        continue
                    carrier = item / "field_practice.md"
                    if carrier.is_file():
                        found.append((carrier, "field_practice", "field_practice_id"))
                    else:
                        rep("FAIL", f"FieldPractice 缺少正式载体 field_practice.md：{rel(item)}")
        # 5. G: 20_groups/ 直属非 _README.md 的 .md 文件
        _G_RESERVED_DIRS = {"overlays", "preplans", "bindings"}
        g_root = MAIN / "20_groups"
        if g_root.is_dir():
            for item in sorted(g_root.iterdir()):
                if item.name.startswith("_"):
                    continue
                if item.is_dir():
                    if item.name not in _G_RESERVED_DIRS:
                        nested = [f for f in item.rglob("*.md") if f.name != "_README.md"]
                        if nested:
                            rep("FAIL", f"G 载体位置非法（不得位于非保留子目录）：{rel(item)}")
                    continue
                if item.is_file() and item.suffix == ".md":
                    found.append((item, "capacity_group", "group"))
        # 6. R: 20_groups/bindings/ 直属非 _README.md 的 .md 文件
        r_root = MAIN / "20_groups" / "bindings"
        if r_root.is_dir():
            for item in sorted(r_root.iterdir()):
                if item.name.startswith("_"):
                    continue
                if item.is_dir():
                    nested = [f for f in item.rglob("*.md") if f.name != "_README.md"]
                    if nested:
                        rep("FAIL", f"R 载体位置非法（不得位于嵌套子目录）：{rel(item)}")
                    continue
                if item.is_file() and item.suffix == ".md":
                    found.append((item, "elastic_binding", "binding_id"))
        return found

    for md, expected_type, id_field in _discover_objects():
        if md.name == "_README.md":
            continue
        if not md.is_file():
            continue
        # frontmatter 存在性
        try:
            raw = md.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
        except OSError:
            rep("FAIL", f"无法读取：{rel(md)}")
            continue
        if not raw.startswith("---"):
            rep("FAIL", f"缺 frontmatter：{rel(md)}")
            continue
        fields = _frontmatter_fields(md)
        # type 存在性
        otype = fields.get("type", "")
        if not otype:
            rep("FAIL", f"缺 type 字段：{rel(md)}")
            continue
        # type 与路径相符
        if otype != expected_type:
            rep("FAIL", f"type 与路径不符：{rel(md)} type={otype} 预期={expected_type}")
            continue
        # 必填字段
        for req in _OBJ_REQUIRED.get(expected_type, []):
            if req not in fields or not fields[req].strip():
                rep("FAIL", f"缺必填字段：{rel(md)} -> {req}")
        # ID 与文件名/目录名相符
        obj_id = fields.get(id_field, "")
        if obj_id:
            # 全局唯一性
            loc_str = str(md.relative_to(MAIN)).replace("\\", "/")
            if obj_id in all_ids:
                rep("FAIL", f"对象 ID 重复：{obj_id} 在 {all_ids[obj_id]} 和 {loc_str}")
            all_ids[obj_id] = loc_str
        # 数组字段检查（拒绝多行）
        for arr_field in ("course_members", "practice_members", "linked_course_runs", "prerequisites"):
            if arr_field in fields:
                _parse_inline_list(fields[arr_field], md, arr_field)
        # ---- ID 与物理路径一致性 ----
        if obj_id and expected_type == "course_definition":
            parent_name = md.parent.name
            if not parent_name.startswith(obj_id + "_"):
                rep("FAIL", f"CourseDefinition 目录名必须以 ID+下划线开头：{rel(md)} (dir={parent_name}, id={obj_id})")
            elif len(parent_name) <= len(obj_id) + 1:
                rep("FAIL", f"CourseDefinition 目录名下划线后标题为空：{rel(md)}")
        elif obj_id and expected_type == "course_run":
            run_dir_name = md.parent.name
            if run_dir_name != obj_id:
                rep("FAIL", f"CourseRun 目录名必须等于 course_run_id：{rel(md)} (dir={run_dir_name}, id={obj_id})")
            case_dir_name = md.parent.parent.name
            cid_val = fields.get("case_id", "")
            if cid_val and case_dir_name != cid_val:
                rep("FAIL", f"CourseRun case 父目录必须等于 case_id：{rel(md)} (dir={case_dir_name}, case_id={cid_val})")
            did_val = fields.get("course_definition_id", "")
            if cid_val and did_val:
                expected_run_id = f"CR-{cid_val}-{did_val}"
                if obj_id != expected_run_id:
                    rep("FAIL", f"course_run_id 必须等于 CR-<case_id>-<definition_id>：{rel(md)} (id={obj_id}, expected={expected_run_id})")
        elif obj_id and expected_type == "activity_record":
            if not re.fullmatch(r"AR-[^-]+-\d{4}", obj_id):
                rep("FAIL", f"ActivityRecord ID 必须符合 AR-<case_id>-NNNN：{rel(md)} (id={obj_id})")
            else:
                id_case = obj_id.split("-")[1]
                cid_val = fields.get("case_id", "")
                if cid_val and id_case != cid_val:
                    rep("FAIL", f"ActivityRecord ID 中 case 与 case_id 不一致：{rel(md)} (id={obj_id}, case_id={cid_val})")
            ar_case_dir = md.parent.name
            cid_val = fields.get("case_id", "")
            if cid_val and ar_case_dir != cid_val:
                rep("FAIL", f"ActivityRecord case 父目录与 case_id 不一致：{rel(md)} (dir={ar_case_dir}, case_id={cid_val})")
            stem = md.stem
            if not stem.startswith(obj_id + "_"):
                rep("FAIL", f"ActivityRecord 文件名必须以 ID+下划线开头：{rel(md)} (stem={stem}, id={obj_id})")
            elif len(stem) <= len(obj_id) + 1:
                rep("FAIL", f"ActivityRecord 文件名下划线后标题为空：{rel(md)}")
        elif obj_id and expected_type == "field_practice":
            if not re.fullmatch(r"FP-[^-]+-\d{4}", obj_id):
                rep("FAIL", f"FieldPractice ID 必须符合 FP-<case_id>-NNNN：{rel(md)} (id={obj_id})")
            else:
                id_case = obj_id.split("-")[1]
                cid_val = fields.get("case_id", "")
                if cid_val and id_case != cid_val:
                    rep("FAIL", f"FieldPractice ID 中 case 与 case_id 不一致：{rel(md)} (id={obj_id}, case_id={cid_val})")
            fp_dir_name = md.parent.name
            if not fp_dir_name.startswith(obj_id + "_"):
                rep("FAIL", f"FieldPractice 目录名必须以 ID+下划线开头：{rel(md)} (dir={fp_dir_name}, id={obj_id})")
            elif len(fp_dir_name) <= len(obj_id) + 1:
                rep("FAIL", f"FieldPractice 目录名下划线后标题为空：{rel(md)}")
            case_dir_name = md.parent.parent.name
            cid_val = fields.get("case_id", "")
            if cid_val and case_dir_name != cid_val:
                rep("FAIL", f"FieldPractice case 父目录与 case_id 不一致：{rel(md)} (dir={case_dir_name}, case_id={cid_val})")
        elif obj_id and expected_type == "capacity_group":
            if not re.fullmatch(r"G\d{2}", obj_id):
                rep("FAIL", f"group_id 必须符合 G+两位数字：{rel(md)} (id={obj_id})")
            if md.stem != obj_id:
                rep("FAIL", f"G 文件 stem 必须等于 group_id：{rel(md)} (stem={md.stem}, id={obj_id})")
        elif obj_id and expected_type == "elastic_binding":
            if not re.fullmatch(r"R\d{3}", obj_id):
                rep("FAIL", f"binding_id 必须符合 R+三位数字：{rel(md)} (id={obj_id})")
            stem = md.stem
            if not stem.startswith(obj_id + "_"):
                rep("FAIL", f"R 文件名必须以 ID+下划线开头：{rel(md)} (stem={stem}, id={obj_id})")
            elif len(stem) <= len(obj_id) + 1:
                rep("FAIL", f"R 文件名下划线后标题为空：{rel(md)}")
        # ---- 枚举验证 ----
        if expected_type == "course_definition":
            ct = fields.get("course_type", "")
            if ct and ct not in _VALID_COURSE_TYPES:
                rep("FAIL", f"CourseDefinition course_type 非法：{rel(md)} = {ct}")
            dd = fields.get("default_driver", "")
            if dd and dd not in _VALID_DRIVERS:
                rep("FAIL", f"CourseDefinition default_driver 非法：{rel(md)} = {dd}")
            st = fields.get("status", "")
            if st and st not in _VALID_DEF_STATUS:
                rep("FAIL", f"CourseDefinition status 非法：{rel(md)} = {st}")
            if ct and dd and ct in _TYPE_DRIVER_MAP and dd not in _TYPE_DRIVER_MAP[ct]:
                rep("FAIL", f"CourseDefinition default_driver 与 course_type 不匹配：{rel(md)} (type={ct}, driver={dd})")
        elif expected_type == "course_run":
            ls = fields.get("lifecycle_status", "")
            if ls and ls not in _VALID_RUN_LIFECYCLE:
                rep("FAIL", f"CourseRun lifecycle_status 非法：{rel(md)} = {ls}")
            cd = fields.get("course_driver", "")
            if cd and cd not in _VALID_DRIVERS:
                rep("FAIL", f"CourseRun course_driver 非法：{rel(md)} = {cd}")
        elif expected_type == "activity_record":
            rs = fields.get("record_status", "")
            if rs and rs not in _VALID_AR_STATUS:
                rep("FAIL", f"ActivityRecord record_status 非法：{rel(md)} = {rs}")
        elif expected_type == "elastic_binding":
            bs = fields.get("binding_status", "")
            if bs and bs not in _VALID_BINDING_STATUS:
                rep("FAIL", f"R binding_status 非法：{rel(md)} = {bs}")
        elif expected_type == "capacity_group":
            gs = fields.get("status", "")
            if gs and gs not in _VALID_G_STATUS:
                rep("FAIL", f"G status 非法：{rel(md)} = {gs}")
        # 建立索引
        fields["_path"] = str(md.relative_to(MAIN)).replace("\\", "/")
        if expected_type == "course_definition":
            idx_definitions[obj_id] = fields
        elif expected_type == "course_run":
            idx_runs[obj_id] = fields
        elif expected_type == "activity_record":
            idx_records[obj_id] = fields
        elif expected_type == "field_practice":
            idx_practices[obj_id] = fields
        elif expected_type == "capacity_group":
            idx_groups[obj_id] = fields
        elif expected_type == "elastic_binding":
            idx_bindings[obj_id] = fields

    # 5. 引用完整性（无条件验证，不以索引非空为前提）
    students_dir = MAIN / "10_case" / "students"
    case_ids: set[str] = set()
    if students_dir.is_dir():
        case_ids = {d.name for d in students_dir.iterdir() if d.is_dir()}

    # CourseRun.case_id → Case
    for run_id, f in idx_runs.items():
        cid = f.get("case_id", "")
        if cid and cid not in case_ids:
            rep("FAIL", f"CourseRun {run_id} 引用的 Case 不存在：{cid}")
        # CourseRun.course_definition_id → CourseDefinition
        did = f.get("course_definition_id", "")
        if did and did not in idx_definitions:
            rep("FAIL", f"CourseRun {run_id} 引用的 CourseDefinition 不存在：{did}")
        # CourseRun driver 与 Definition 类型匹配
        if did and did in idx_definitions:
            def_type = idx_definitions[did].get("course_type", "")
            run_driver = f.get("course_driver", "")
            if def_type and run_driver and def_type in _TYPE_DRIVER_MAP:
                if run_driver not in _TYPE_DRIVER_MAP[def_type]:
                    rep("FAIL", f"CourseRun {run_id} driver 与 Definition 类型不匹配：type={def_type}, driver={run_driver}")

    # CourseDefinition.prerequisites 验证
    _old_course_codes: set[str] = set()
    for _cs in _iter_legacy_course_status():
        _fm = _frontmatter_fields(_cs)
        _code = _fm.get("course", "") or _cs.parent.name.split("_", 1)[0]
        if _code:
            legacy_path_hit("object_layer_old_course_code", _code)
            _old_course_codes.add(_code)
    _prereq_graph: dict[str, list[str]] = {}  # def_id -> [new-path prereq ids]
    for def_id, f in idx_definitions.items():
        prereqs = _parse_inline_list(f.get("prerequisites", "[]"), MAIN / f["_path"], "prerequisites")
        if len(prereqs) != len(set(prereqs)):
            rep("FAIL", f"CourseDefinition prerequisites 重复：{def_id}")
        if def_id in prereqs:
            rep("FAIL", f"CourseDefinition 不得把自身列为 prerequisite：{def_id}")
        new_path_refs: list[str] = []
        for p in prereqs:
            if p == def_id:
                continue
            if p in idx_definitions:
                new_path_refs.append(p)
            elif p in _old_course_codes:
                # 旧路径兼容引用，视为叶节点（真触发回退）
                legacy_path_hit("object_layer_prereq_old_leaf", f"{def_id}->{p}")
            else:
                rep("FAIL", f"CourseDefinition prerequisite 不存在：{def_id} -> {p}")
        _prereq_graph[def_id] = new_path_refs
    # 确定性循环检测（DFS）
    _WHITE, _GRAY, _BLACK = 0, 1, 2
    _color: dict[str, int] = {k: _WHITE for k in _prereq_graph}
    _cycle_path: list[str] = []

    def _dfs_cycle(node: str) -> bool:
        _color[node] = _GRAY
        _cycle_path.append(node)
        for nb in _prereq_graph.get(node, []):
            if nb not in _color:
                continue
            if _color[nb] == _GRAY:
                _cycle_path.append(nb)
                return True
            if _color[nb] == _WHITE and _dfs_cycle(nb):
                return True
        _cycle_path.pop()
        _color[node] = _BLACK
        return False

    for _node in sorted(_prereq_graph):
        if _color[_node] == _WHITE:
            _cycle_path.clear()
            if _dfs_cycle(_node):
                rep("FAIL", f"CourseDefinition prerequisites 形成循环：{' -> '.join(_cycle_path)}")
                break

    # ActivityRecord.case_id → Case + upgraded_to_course_run
    for ar_id, f in idx_records.items():
        cid = f.get("case_id", "")
        if cid and cid not in case_ids:
            rep("FAIL", f"ActivityRecord {ar_id} 引用的 Case 不存在：{cid}")
        # upgraded_to_course_run 验证
        upgraded = f.get("upgraded_to_course_run", "").strip()
        if upgraded and upgraded != "—":
            if upgraded not in idx_runs:
                rep("FAIL", f"ActivityRecord 升级指向的 CourseRun 不存在：{ar_id} -> {upgraded}")
            else:
                run_case = idx_runs[upgraded].get("case_id", "")
                if cid and run_case and run_case != cid:
                    rep("FAIL", f"ActivityRecord 跨 Case 升级到 CourseRun：{ar_id}.case_id={cid}, {upgraded}.case_id={run_case}")

    # FieldPractice.case_id → Case + 跨 Case 检查
    for fp_id, f in idx_practices.items():
        cid = f.get("case_id", "")
        if cid and cid not in case_ids:
            rep("FAIL", f"FieldPractice {fp_id} 引用的 Case 不存在：{cid}")
        # FieldPractice.linked_course_runs → 已存在 CourseRun，且只能关联 Project/Praxis，且同 Case
        linked = _parse_inline_list(f.get("linked_course_runs", "[]"), MAIN / f["_path"], "linked_course_runs")
        for lr in linked:
            if lr not in idx_runs:
                rep("FAIL", f"FieldPractice {fp_id} 关联的 CourseRun 不存在：{lr}")
            else:
                run_def = idx_runs[lr].get("course_definition_id", "")
                if run_def in idx_definitions:
                    ctype = idx_definitions[run_def].get("course_type", "")
                    if ctype and ctype not in ("project", "praxis"):
                        rep("FAIL", f"FieldPractice {fp_id} 只能关联 Project/Praxis CourseRun：{lr} (type={ctype})")
                run_case = idx_runs[lr].get("case_id", "")
                if cid and run_case and run_case != cid:
                    rep("FAIL", f"FieldPractice {fp_id} 跨 Case 关联 CourseRun：FP.case_id={cid}, {lr}.case_id={run_case}")
        # evidence_index 路径安全性
        ev_idx = f.get("evidence_index", "").strip()
        if ev_idx:
            fp_instance_dir = (MAIN / f["_path"]).parent
            ev_valid = True
            if "\\" in ev_idx:
                rep("FAIL", f"FieldPractice evidence_index 必须是安全相对路径（不得含反斜杠）：{fp_id}")
                ev_valid = False
            if ev_valid and (ev_idx.startswith("/") or re.match(r"^[A-Za-z]:", ev_idx) or ev_idx.startswith("\\\\")):
                rep("FAIL", f"FieldPractice evidence_index 必须是安全相对路径（不得为绝对路径）：{fp_id}")
                ev_valid = False
            if ev_valid:
                parts = ev_idx.split("/")
                if "" in parts:
                    rep("FAIL", f"FieldPractice evidence_index 含空路径段：{fp_id} -> {ev_idx}")
                    ev_valid = False
                elif ".." in parts or "." in parts:
                    rep("FAIL", f"FieldPractice evidence_index 路径逃逸（含 . 或 .. 段）：{fp_id}")
                    ev_valid = False
            if ev_valid:
                fp_resolved = fp_instance_dir.resolve()
                target = (fp_instance_dir / ev_idx).resolve()
                try:
                    target.relative_to(fp_resolved)
                except ValueError:
                    rep("FAIL", f"FieldPractice evidence_index 路径逃逸实例目录：{fp_id} -> {ev_idx}")
                    ev_valid = False
            if ev_valid:
                if not target.is_file():
                    rep("FAIL", f"FieldPractice evidence_index 必须指向已存在的 Markdown 文件（文件不存在）：{fp_id} -> {ev_idx}")
                elif target.suffix.lower() != ".md":
                    rep("FAIL", f"FieldPractice evidence_index 必须指向已存在的 Markdown 文件（非 .md）：{fp_id} -> {ev_idx}")

    # G.course_members 引用完整性（课程代码必须在 30_course_definitions 中存在）
    active_g_runs: set[str] = set()
    for gid, f in idx_groups.items():
        members = _parse_inline_list(f.get("course_members", "[]"), MAIN / f["_path"], "course_members")
        for m in members:
            # 课程代码在 definitions 中存在性（允许前缀匹配，如 MATH1607H → MATH1607H_MathematicalAnalysis）
            defs_dir = MAIN / "30_course_definitions"
            if defs_dir.is_dir():
                found_def = any(d.name.startswith(m) for d in defs_dir.iterdir() if d.is_dir())
                if not found_def:
                    rep("WARN", f"G {gid} 引用的课程代码未在 30_course_definitions 中找到：{m}")
        fps = _parse_inline_list(f.get("practice_members", "[]"), MAIN / f["_path"], "practice_members")
        for fp in fps:
            if fp not in idx_practices:
                rep("WARN", f"G {gid} 引用的 FieldPractice 不存在：{fp}")
        if f.get("status") == "active":
            active_g_runs.update(members)

    # R.case_id → Case + R.course_run_id 跨 Case 检查
    active_r_runs: set[str] = set()
    for rid, f in idx_bindings.items():
        r_case = f.get("case_id", "")
        if r_case and r_case not in case_ids:
            rep("FAIL", f"R {rid} 引用的 Case 不存在：{r_case}")
        run_ref = f.get("course_run_id", "")
        if run_ref and run_ref not in idx_runs:
            rep("FAIL", f"R {rid} 绑定的 CourseRun 不存在：{run_ref}")
        if run_ref and run_ref in idx_runs:
            run_def = idx_runs[run_ref].get("course_definition_id", "")
            if run_def in idx_definitions:
                ctype = idx_definitions[run_def].get("course_type", "")
                if ctype and ctype not in ("project", "praxis"):
                    rep("FAIL", f"R {rid} 只能绑定 Project/Praxis CourseRun：{run_ref} (type={ctype})")
            run_case = idx_runs[run_ref].get("case_id", "")
            if r_case and run_case and run_case != r_case:
                rep("FAIL", f"R {rid} 跨 Case 绑定 CourseRun：R.case_id={r_case}, {run_ref}.case_id={run_case}")
        if f.get("binding_status") == "active" and run_ref:
            active_r_runs.add(run_ref)

    # 同一 CourseRun 同时 active G/R
    both = active_g_runs & active_r_runs
    if both:
        rep("FAIL", f"同一 CourseRun 同时 active G/R：{sorted(both)}")

    # 6. 新旧路径碰撞（按稳定 ID 比较）
    old_codes: set[str] = set()
    for cs in _iter_legacy_course_status():
        fm = _frontmatter_fields(cs)
        code = fm.get("course", "") or cs.parent.name.split("_", 1)[0]
        if code:
            # 与 object_layer_old_course_code 可能重复计数：此处专指碰撞扫描段触发
            legacy_path_hit("object_layer_collision_scan_code", code)
            old_codes.add(code)
    # 6a. 旧课程 code 与新 CourseDefinition ID 碰撞
    new_def_ids = set(idx_definitions.keys()) - {""}
    def_id_collision = old_codes & new_def_ids
    if def_id_collision:
        for code in sorted(def_id_collision):
            legacy_path_hit("object_layer_collision_def", code)
        rep("FAIL", f"旧课程 code 与新 CourseDefinition ID 碰撞：{sorted(def_id_collision)}")
    # 6b. 旧课程 code 与新 CourseRun 的 definition_id 碰撞
    new_run_defs = {f.get("course_definition_id", "") for f in idx_runs.values()} - {""}
    run_collision = old_codes & new_run_defs
    if run_collision:
        for code in sorted(run_collision):
            legacy_path_hit("object_layer_collision_run", code)
        rep("FAIL", f"旧课程 code 与新 CourseRun definition_id 碰撞：{sorted(run_collision)}")
    # 6c. 旧课程目录名与新 CourseDefinition 目录名碰撞
    old_courses_dir = MAIN / "30_courses"
    old_dir_names: set[str] = set()
    if old_courses_dir.is_dir():
        old_dir_names = {
            p.name for p in old_courses_dir.iterdir()
            if p.is_dir() and not p.name.startswith("_")
        }
        for name in sorted(old_dir_names):
            # 仅有空壳目录、无 course_status 时也计一次「旧课目录仍在」
            if not (old_courses_dir / name / "course_status.md").exists():
                legacy_path_hit("object_layer_old_course_dir_shell", name)
    new_def_names: set[str] = set()
    new_defs_dir = MAIN / "30_course_definitions"
    if new_defs_dir.is_dir():
        new_def_names = {p.name for p in new_defs_dir.iterdir() if p.is_dir() and not p.name.startswith("_")}
    dir_collision = old_dir_names & new_def_names
    if dir_collision:
        for name in sorted(dir_collision):
            legacy_path_hit("object_layer_collision_dir", name)
        rep("FAIL", f"同一课程目录新旧碰撞：{sorted(dir_collision)}")
    # 6d. G 碰撞检查已移除（20_execution 删除后 G 只在 20_groups/ 一处，无新旧碰撞可能）


def main() -> int:
    LEGACY_PATH_HITS.clear()
    check_startup_files()
    check_student_archive_files()
    check_reflection_indexes()
    check_constitution_budget()
    check_manifest_registration()
    check_external_resources()
    check_memory_budget()
    check_version_consistency()
    check_env_hygiene()
    check_naming_conventions()
    check_pattern_declarations()
    check_course_group_rules()
    check_progress_nodes()
    check_generated_state()
    check_artifact_registry()
    check_handoff_aging()
    check_overlay_references()
    check_exam_pool_isolation()
    check_skin_system()
    check_general_track()
    check_course_drivers()
    check_working_page_windows()
    check_mistake_bank_generation_template()
    check_mistake_bank_schema()
    check_cloud_sync_protocol()
    check_core_playbook_distribution()
    check_curricula_semantics()
    check_domain_model_distribution()
    check_object_layer_migration()
    check_evolution_ids()
    check_release_snapshot()
    check_guide_generated()
    emit_legacy_path_hits_total()
    fails = sum(1 for lv, _ in RESULTS if lv == "FAIL")
    warns = sum(1 for lv, _ in RESULTS if lv == "WARN")
    print(f"\nresult: {fails} FAIL, {warns} WARN")
    if fails:
        print("开课前先修掉 FAIL。course_status.md 是进度唯一真相源。")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
