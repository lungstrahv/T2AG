#!/usr/bin/env python3
"""
t2ag_doctor —— 档案一致性体检

职责边界：确定性机器检查（同输入同输出，零裁量）。需要理解判断的检查不属于本文件——那归 50_playbook/。
零依赖。退出码：0 = 无 FAIL，1 = 至少一个 FAIL。

检查项：
  - 启动文件存在性 / 宪法分章预算 / 结构清单登记
  - memory 分节预算制 / 版本号一致性 / venv/env 审核
  - 复利回路模式声明 / 课程组规则 / overlay 引用完整性
  - 考试题库引用隔离 / 皮肤系统配置
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # 项目根
MAIN = ROOT / "main"
RESULTS: list[tuple[str, str]] = []


def rep(level: str, msg: str) -> None:
    RESULTS.append((level, msg))
    print(f"[{level}] {msg}")


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


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



# ---------- 5. 复利回路模式声明检查 ----------
PATTERN_RE = re.compile(r"【模式】复利回路")
PARAM_RE = re.compile(r"【参数】(.*?)｜(.*?)｜(.*?)｜(.*?)｜(.*)")


def check_pattern_declarations() -> None:
    """检查复利回路模式实例的头部声明"""
    # Known instances (relative to MAIN)
    known_instances = [
        "00_core/t2ag_problemlog.md",
    ]
    # When courses exist, also check:
    # - 30_courses/*/mistake_bank.md
    # - 40_practices/*/trade_journal.md

    for rel_path in known_instances:
        path = MAIN / rel_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if not PATTERN_RE.search(content):
            rep("WARN", f"复利回路实例缺声明：{rel_path}")
            continue
        if not PARAM_RE.search(content):
            rep("WARN", f"复利回路实例参数不齐：{rel_path}")

    # Also scan for any file with pattern declaration and check params
    for md in MAIN.rglob("*.md"):
        content = md.read_text(encoding="utf-8")
        if PATTERN_RE.search(content) and not PARAM_RE.search(content):
            rep("WARN", f"复利回路声明缺参数：{rel(md)}")


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
                rep("WARN", f"部件未在结构清单登记：main/{name}（先登记后创建）")



# ---------- 课程组规则检查 ----------
def check_course_group_rules() -> None:
    """检查课程识别与课程组规则（course_group_rules.md 第六节）"""
    STATUS_ACTIVE_RE = re.compile(r"状态\*{0,2}\s*[：:]\s*active")
    STATUS_NONACTIVE_RE = re.compile(r"状态\*{0,2}\s*[：:]\s*(archived|paused)")
    GROUP_PTR_RE = re.compile(r"活跃课程组.*?[Gg](\d+)")

    groups_dir = MAIN / "20_groups"

    # 2. 全库 active 组数量 ≠ 1 → FAIL（空 skeleton 豁免：无 G*.md 文件时只 WARN）
    active_count = 0
    active_groups = []
    active_group_file = None
    if groups_dir.exists():
        for gf in sorted(groups_dir.glob("G*.md")):
            gc = gf.read_text(encoding="utf-8")
            if STATUS_ACTIVE_RE.search(gc):
                active_count += 1
                active_groups.append(gf.name)
                if active_group_file is None:
                    active_group_file = gf
    if active_count != 1:
        has_group_files = groups_dir.exists() and any(groups_dir.glob("G*.md"))
        if active_count == 0 and not has_group_files:
            rep("WARN", "20_groups/ 无课程组文件（skeleton 初始状态，首次启动后应创建课程组）")
        else:
            rep("FAIL", f"active 组数量 = {active_count}（应为 1）：{active_groups}")

    # 1. memory 指针指向的组文件不存在或状态非 active → FAIL
    mem = MAIN / "00_core" / "t2ag_memory.md"
    if mem.exists():
        content = mem.read_text(encoding="utf-8")
        m = GROUP_PTR_RE.search(content)
        if m:
            group_num = m.group(1)
            group_file = groups_dir / f"G{group_num}.md"
            if not group_file.exists():
                rep("FAIL", f"memory 指针指向 G{group_num}，但组文件不存在")
            else:
                gc = group_file.read_text(encoding="utf-8")
                if STATUS_NONACTIVE_RE.search(gc):
                    rep("FAIL", f"memory 指针指向 G{group_num}，但组文件状态非 active")
        elif any(groups_dir.glob("G*.md")) if groups_dir.exists() else False:
            rep("WARN", "存在组文件但 memory 无活跃课程组指针")

    # 3. active 课程未出现在当前组成员表 → FAIL
    if active_group_file:
        gc = active_group_file.read_text(encoding="utf-8")
        group_courses = set(re.findall(r"[A-Z]{2,4}\d{3,4}[A-Z]?", gc))
        ci_path = MAIN / "10_case" / "course_info.md"
        if ci_path.exists():
            ci = ci_path.read_text(encoding="utf-8")
            for m in re.finditer(r"\|\s*([A-Z]{2,4}\d{3,4}[A-Z]?)\s*\|.*?\|\s*active\s*\|", ci):
                code = m.group(1)
                if code not in group_courses:
                    rep("FAIL", f"课程 {code} 状态为 active 但未出现在当前组成员表")

    # 4. 权威链外的 .md 出现枚举式课程清单 → WARN
    enum_re = re.compile(r"当前课程.*?([A-Z]{2,4}\d{3,4}[A-Z]?).+?([A-Z]{2,4}\d{3,4}[A-Z]?)")
    skip_dirs = {"00_core", "50_playbook", "70_tools", ".venv", "__pycache__"}
    for root_dir, dirs, files in os.walk(MAIN):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if not f.endswith(".md"):
                continue
            filepath = os.path.join(root_dir, f)
            if "course_group_rules" in filepath:
                continue
            try:
                content = open(filepath, "r", encoding="utf-8").read()
            except (UnicodeDecodeError, PermissionError):
                continue
            if enum_re.search(content):
                rel = os.path.relpath(filepath, MAIN)
                rep("WARN", f"枚举式课程清单（应改指针）：{rel}")


# ---------- 考试题库检查 ----------
EXAM_META_REQUIRED = ["题号", "类型", "知识节点", "难度档", "已用于教学", "已考", "解答页码"]


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
    if not courses_dir.exists():
        return

    for exam_dir in courses_dir.glob("*/_exam"):
        index = exam_dir / "index.md"
        papers_dir = exam_dir / "papers"
        course_dir = exam_dir.parent
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
            continue

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


def main() -> int:
    check_startup_files()
    check_constitution_budget()
    check_manifest_registration()
    check_memory_budget()
    check_version_consistency()
    check_env_hygiene()
    check_pattern_declarations()
    check_course_group_rules()
    check_overlay_references()
    check_exam_pool_isolation()
    check_skin_system()
    fails = sum(1 for lv, _ in RESULTS if lv == "FAIL")
    warns = sum(1 for lv, _ in RESULTS if lv == "WARN")
    print(f"\nresult: {fails} FAIL, {warns} WARN")
    if fails:
        print("开课前先修掉 FAIL。course_status.md 是进度唯一真相源。")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
