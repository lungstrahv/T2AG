#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
t2ag_doctor.py — T2AG 系统健康检查工具

职责边界：
  本工具只输出事实（文件存在/不存在、行数超限、引用断链），
  不输出判断（该怎么修、该不该合并）。判断归 playbook 和 agent。

用法：
  python 70_tools/t2ag_doctor.py

退出码：
  0 = 无 FAIL（允许首次启动类 WARN）
  1 = 有 FAIL（≥1 FAIL）
"""

import hashlib
import json
import sys
import os
import re
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ─── 基准目录（脚本所在目录的上两级 = main/） ───
SCRIPT_DIR = Path(__file__).resolve().parent
MAIN_DIR = SCRIPT_DIR.parent  # main/
ROOT_DIR = MAIN_DIR.parent     # t2ag/ or t2ag-skeleton/

# ─── 颜色 ───
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

# ─── 结果收集 ───
fails = []
warns = []
infos = []


def fail(check_name, message):
    fails.append((check_name, message))
    print(f"  {RED}[FAIL]{RESET} {message}")


def warn(check_name, message):
    warns.append((check_name, message))
    print(f"  {YELLOW}[WARN]{RESET} {message}")


def info(message):
    infos.append(message)
    print(f"  {GREEN}[OK]{RESET} {message}")


def section(title):
    print(f"\n{BOLD}── {title} ──{RESET}")


# ═══════════════════════════════════════════════════════════════
# 检查函数
# ═══════════════════════════════════════════════════════════════

def check_core_files():
    """检查核心文件是否存在"""
    section("核心文件存在性")

    core_files = [
        "main/t2ag.md",
        "main/00_core/t2ag_memory.md",
        "main/00_core/t2ag_changelog.md",
        "main/00_core/t2ag_problemlog.md",
        "main/00_core/pattern_retire_loop.md",
        "main/00_core/course_group_rules.md",
        "main/30_courses/_shared/external_resources.md",
        "main/10_case/course_info.md",
        "main/10_case/teacher_overlay.md",
        "main/50_playbook/first_run.md",
        "main/50_playbook/session_close.md",
        "main/50_playbook/book_management.md",
        "main/50_playbook/exam_protocol.md",
        "main/50_playbook/exam_bank_spec.md",
        "main/50_playbook/lesson_recover.md",
        "main/50_playbook/ocr_correct_flow.md",
        "main/50_playbook/group_transition.md",
        "main/50_playbook/project_verification.md",
        "main/50_playbook/git_workflow.md",
        "main/50_playbook/skin_playbook.md",
        "main/50_playbook/playbook_management.md",
        "main/50_playbook/journal_management.md",
        "main/50_playbook/problemlog_maintenance.md",
        "main/50_playbook/general_learning.md",
        "main/50_playbook/naming_conventions.md",
        "main/50_playbook/progress_tracking.md",
        "main/70_tools/t2ag_doctor.py",
        "main/70_tools/context_scan.py",
        "main/70_tools/t2ag_state_refresh.py",
        "main/70_tools/artifact_registry.json",
        "main/60_journal/INDEX.md",
    ]

    for rel_path in core_files:
        full_path = ROOT_DIR / rel_path
        if full_path.exists():
            info(f"{rel_path}")
        else:
            fail("core_files", f"核心文件缺失: {rel_path}")


def check_version_consistency():
    """检查版本号一致性"""
    section("版本号一致性")

    sources = {}
    version_re = re.compile(r"(?:版本|version)[^\d]*(\d+\.\d+\.\d+)", re.IGNORECASE)
    candidates = {
        "t2ag.md": ROOT_DIR / "main" / "t2ag.md",
        "AGENTS.md": ROOT_DIR / "AGENTS.md",
        "README.md": ROOT_DIR / "README.md",
        "t2ag_memory.md": ROOT_DIR / "main" / "00_core" / "t2ag_memory.md",
    }
    for name, path in candidates.items():
        if not path.exists():
            continue
        match = version_re.search(path.read_text(encoding="utf-8"))
        if match:
            sources[name] = match.group(1)

    if len(sources) < 2:
        warn("version", f"版本号来源不足 2 个，无法比对: {sources}")
        return

    versions = set(sources.values())
    if len(versions) == 1:
        info(f"版本号一致: {versions.pop()}（{', '.join(sources.keys())}）")
    else:
        fail("version", f"版本号不一致: {sources}")


def check_distribution_hygiene():
    """检查模板/审查发行包没有混入运行环境或生成缓存。"""
    section("发行环境清洁")
    if ROOT_DIR.name in {"t2ag-skeleton", "t2ag-lite"} and (ROOT_DIR / ".venv").exists():
        fail("distribution_hygiene", f"{ROOT_DIR.name} 不得携带 .venv")

    generated = list(MAIN_DIR.rglob("*.pyc")) + [
        path for path in MAIN_DIR.rglob("__pycache__") if path.is_dir()
    ]
    if generated:
        shown = ", ".join(str(path.relative_to(ROOT_DIR)) for path in generated[:5])
        fail("distribution_hygiene", f"发行内容混入 Python 生成缓存: {shown}")
    else:
        info("无 .venv / __pycache__ / *.pyc 发行污染")


def check_naming_conventions():
    """检查活动路径采用已登记命名，并验证三发行版目录册同步。"""
    section("命名与目录册")
    required = [
        MAIN_DIR / "50_playbook" / "naming_conventions.md",
        ROOT_DIR / "t2ag_directory_guide.html",
        ROOT_DIR / "assets" / "fable_snail.png",
    ]
    for path in required:
        if not path.exists():
            fail("naming", f"命名规范或目录册资产缺失: {path.relative_to(ROOT_DIR)}")

    legacy_paths = [
        ROOT_DIR / "操作目录册.html",
        ROOT_DIR / "tmp",
        MAIN_DIR / "10_case" / "emo",
    ]
    legacy_paths.extend(path for path in MAIN_DIR.rglob("temppage"))
    legacy_paths.extend(path for path in MAIN_DIR.rglob("temp_page.md"))
    existing = [path for path in legacy_paths if path.exists()]
    if existing:
        shown = ", ".join(str(path.relative_to(ROOT_DIR)) for path in existing[:5])
        fail("naming", f"活动结构残留退役名称: {shown}")

    playbook_re = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*\.md$")
    bad_playbooks = [
        path.name for path in (MAIN_DIR / "50_playbook").glob("*.md")
        if not playbook_re.fullmatch(path.name)
    ]
    if bad_playbooks:
        fail("naming", f"playbook 文件名不是小写 snake_case: {', '.join(bad_playbooks)}")

    course_re = re.compile(r"^[A-Z0-9]+_[A-Za-z][A-Za-z0-9]*$")
    course_root = MAIN_DIR / "30_courses"
    bad_courses = [
        path.name for path in course_root.iterdir()
        if path.is_dir() and path.name != "_shared" and not course_re.fullmatch(path.name)
    ] if course_root.exists() else []
    if bad_courses:
        fail("naming", f"课程目录名不符合 课程码_PascalCaseTitle: {', '.join(bad_courses)}")

    sibling_roots = [ROOT_DIR.parent / name for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")]
    synced = ("t2ag_directory_guide.html", "assets/fable_snail.png")
    if all(root.exists() for root in sibling_roots):
        for rel_path in synced:
            files = [root / rel_path for root in sibling_roots]
            if not all(path.exists() for path in files):
                fail("naming", f"目录册未同步三发行版: {rel_path}")
            elif len({_sha256(path) for path in files}) != 1:
                fail("naming", f"目录册三发行版正文分叉: {rel_path}")
    if not existing and not bad_playbooks and not bad_courses:
        info("活动路径命名与三发行版目录册一致")


def check_memory_budget():
    """检查 memory 各节行数预算"""
    section("Memory 节预算")

    memory_path = ROOT_DIR / "main" / "00_core" / "t2ag_memory.md"
    if not memory_path.exists():
        fail("memory_budget", "t2ag_memory.md 不存在")
        return

    content = memory_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    # 各节 max 定义：## 节标题 [max N]
    section_pattern = re.compile(r'^##\s+.+?\[max\s+(\d+)\]')
    total_max = 0
    total_content_lines = 0
    in_section = False
    current_max = 0
    current_name = ""
    current_lines = 0

    for i, line in enumerate(lines):
        m = section_pattern.match(line)
        if m:
            # 保存上一节
            if in_section and current_max > 0:
                total_max += current_max
                total_content_lines += current_lines
                if current_lines > current_max:
                    fail("memory_budget",
                         f"节 '{current_name}' 超预算: {current_lines}/{current_max} 行")
                else:
                    info(f"节 '{current_name}': {current_lines}/{current_max} 行")

            current_max = int(m.group(1))
            current_name = line.strip()
            current_lines = 0
            in_section = True
        elif in_section:
            # 遇到下一个 ## 或文件末尾时结束
            if line.startswith("## ") and not section_pattern.match(line):
                if current_max > 0:
                    total_max += current_max
                    total_content_lines += current_lines
                    if current_lines > current_max:
                        fail("memory_budget",
                             f"节 '{current_name}' 超预算: {current_lines}/{current_max} 行")
                    else:
                        info(f"节 '{current_name}': {current_lines}/{current_max} 行")
                in_section = False
            else:
                current_lines += 1

    # 最后一节
    if in_section and current_max > 0:
        total_max += current_max
        total_content_lines += current_lines
        if current_lines > current_max:
            fail("memory_budget",
                 f"节 '{current_name}' 超预算: {current_lines}/{current_max} 行")
        else:
            info(f"节 '{current_name}': {current_lines}/{current_max} 行")

    # 总预算
    total_lines = len(lines)
    if total_lines > 180:
        fail("memory_budget", f"总行数超 180: {total_lines} 行")
    else:
        info(f"总行数: {total_lines}/180 行")


def check_constitution_budget():
    """检查 t2ag.md 分章预算"""
    section("宪法分章预算")

    t2ag_path = ROOT_DIR / "main" / "t2ag.md"
    if not t2ag_path.exists():
        fail("constitution", "t2ag.md 不存在")
        return

    content = t2ag_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    chapter_pattern = re.compile(r'^##\s+.+?\[max\s+(\d+)\]')
    total_lines = len(lines)

    # 找各章
    chapters = []
    current_chapter = None
    current_max = 0
    current_lines = 0

    for line in lines:
        m = chapter_pattern.match(line)
        if m:
            if current_chapter:
                chapters.append((current_chapter, current_lines, current_max))
            current_chapter = line.strip()
            current_max = int(m.group(1))
            current_lines = 0
        elif current_chapter:
            current_lines += 1

    if current_chapter:
        chapters.append((current_chapter, current_lines, current_max))

    for name, line_count, max_val in chapters:
        if line_count > max_val:
            fail("constitution", f"章 '{name}' 超预算: {line_count}/{max_val} 行")
        else:
            info(f"章 '{name}': {line_count}/{max_val} 行")

    if total_lines > 400:
        fail("constitution", f"总行数超 400: {total_lines} 行")
    else:
        info(f"总行数: {total_lines}/400 行")


def check_manifest_registration():
    """结构清单双向比对：仓库有而清单无则 WARN"""
    section("结构清单注册比对")

    t2ag_path = ROOT_DIR / "main" / "t2ag.md"
    if not t2ag_path.exists():
        fail("manifest", "t2ag.md 不存在")
        return

    content = t2ag_path.read_text(encoding="utf-8")

    # 提取结构清单中登记的路径
    registered = set()
    for m in re.finditer(r'`\s*((?:main/)?[^\s`]+\.(?:md|py|yaml|json))\s*`', content):
        registered.add(m.group(1).replace("main/", ""))

    # 扫描实际文件
    actual = set()
    scan_dirs = [
        ROOT_DIR / "main" / "00_core",
        ROOT_DIR / "main" / "10_case",
        ROOT_DIR / "main" / "50_playbook",
        ROOT_DIR / "main" / "70_tools",
        ROOT_DIR / "main" / "60_journal",
    ]

    for scan_dir in scan_dirs:
        if scan_dir.exists():
            for f in scan_dir.iterdir():
                if f.is_file() and f.suffix in ('.md', '.py', '.yaml', '.json'):
                    if scan_dir.name == "60_journal" and f.name != "INDEX.md":
                        continue
                    rel = f.relative_to(ROOT_DIR / "main").as_posix()
                    actual.add(rel)

    # 仓库有而清单无
    unregistered = actual - registered
    # 过滤掉已知的合理未登记文件
    known_unregistered = {
        "00_core/t2ag_changelog.md",  # changelog 有登记但路径可能不同
        "00_core/t2ag_problemlog.md",
        "00_core/pattern_retire_loop.md",
    }
    # 只报真正未登记的
    truly_unregistered = unregistered - known_unregistered - registered

    if truly_unregistered:
        for f in sorted(truly_unregistered):
            warn("manifest", f"仓库有而清单无: {f}")
    else:
        info("结构清单与仓库文件一致")


def _skel_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from a Markdown file."""
    content = path.read_text(encoding="utf-8-sig", errors="ignore")
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    return dict(re.findall(r"^([a-z_]+):\s*(.*?)\s*$", match.group(1), re.MULTILINE))


def _discover_new_course_runs_skel() -> list:
    """发现新路径 CourseRun：35_course_runs/<case_id>/CR-*/course_status.md。"""
    results = []
    runs_root = MAIN_DIR / "35_course_runs"
    if not runs_root.is_dir():
        return results
    for status in sorted(runs_root.glob("*/CR-*/course_status.md")):
        fm = _skel_frontmatter(status)
        results.append((status, fm))
    return results


def _discover_new_definitions_skel() -> list:
    """发现新路径 CourseDefinition：30_course_definitions/<id>_<title>/course_definition.md。"""
    results = []
    defs_root = MAIN_DIR / "30_course_definitions"
    if not defs_root.is_dir():
        return results
    for d in sorted(defs_root.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        carrier = d / "course_definition.md"
        if carrier.is_file():
            fm = _skel_frontmatter(carrier)
            results.append((carrier, fm))
    return results


def check_course_group_rules():
    """检查课程组规则一致性"""
    section("课程组规则一致性")

    groups_dir = ROOT_DIR / "main" / "20_groups"
    if not groups_dir.exists():
        warn("group_rules", "20_groups/ 目录不存在")
        return

    # 检查 G*.md 文件
    g_files = sorted(groups_dir.glob("G*.md"))
    if not g_files:
        warn("group_rules", "无 G*.md 课程组文件（首次启动前正常）")
        return

    info(f"找到 {len(g_files)} 个课程组文件: {', '.join(f.name for f in g_files)}")

    # 检查每个 G 文件的状态行
    for g_file in g_files:
        content = g_file.read_text(encoding="utf-8")
        if "状态：" not in content and "状态:" not in content:
            warn("group_rules", f"{g_file.name} 缺少 '状态：' 字段")

    # 检查 memory 中的活跃课程组指针
    memory_path = ROOT_DIR / "main" / "00_core" / "t2ag_memory.md"
    if memory_path.exists():
        memory_content = memory_path.read_text(encoding="utf-8")
        active_match = re.search(r'\|\s*活跃课程组\s*\|\s*(\S+)', memory_content)
        if active_match:
            active_group = active_match.group(1)
            if active_group == "—":
                info("活跃课程组指针为空（初始状态）")
            else:
                # 检查指针指向的文件是否存在
                g_path = groups_dir / f"{active_group}.md"
                if g_path.exists():
                    info(f"活跃课程组指针: {active_group} → 文件存在")
                else:
                    fail("group_rules",
                         f"活跃课程组指针 {active_group} 指向的文件不存在")


def check_general_track():
    """第一阶段 R 冻结契约检查（skeleton）。

    规则：
    1. 不存在实例兼容注册表
    2. 25_general/ 除 _README.md 外不存在 R 文件
    3. 通用文件中不出现 PHIL、DS、LOGIC
    """
    section("R 绑定（第一阶段冻结契约）")

    # 1. 不得存在实例兼容注册表
    registry_path = ROOT_DIR / "main" / "70_tools" / "legacy_r_registry.json"
    if registry_path.exists():
        fail("general_track", "skeleton 不得携带实例兼容注册表 legacy_r_registry.json")
    else:
        info("无实例兼容注册表（正确）")

    # 2. 25_general/ 除 _README.md 外不得有 R 文件
    general_dir = ROOT_DIR / "main" / "25_general"
    if general_dir.exists():
        r_files = [f for f in sorted(general_dir.glob("*.md")) if f.name != "_README.md"]
        if r_files:
            fail("general_track", f"skeleton 25_general/ 不得含 R 文件：{[f.name for f in r_files]}")
        else:
            info("25_general/ 无 R 文件（正确）")
    else:
        info("25_general/ 目录不存在")

    # 3. 通用文件中不得出现实例名（排除 changelog/problemlog 历史记录）
    instance_names = ["PHIL1101r", "DS1001r", "LOGIC1001r"]
    skip_files = {"t2ag_changelog.md", "t2ag_problemlog.md"}
    scan_dirs = [
        ROOT_DIR / "main" / "00_core",
        ROOT_DIR / "main" / "25_general",
        ROOT_DIR / "main" / "50_playbook",
    ]
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for md_file in sorted(scan_dir.glob("*.md")):
            if md_file.name in skip_files:
                continue
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            for name in instance_names:
                if name in content:
                    fail("general_track", f"skeleton 通用文件含实例名 {name}：{md_file.name}")


def check_overlay_references():
    """检查 overlay 引用一致性"""
    section("Overlay 引用一致性")

    overlays_dir = ROOT_DIR / "main" / "20_groups" / "overlays"
    groups_dir = ROOT_DIR / "main" / "20_groups"

    if not overlays_dir.exists():
        # overlays 目录不存在不报错（首次启动前可能没有）
        info("20_groups/overlays/ 不存在（首次启动前正常）")
        return

    # 扫描 overlay 文件
    overlay_files = set()
    for f in overlays_dir.glob("overlay_*.md"):
        overlay_files.add(f.name)

    if not overlay_files:
        info("无 overlay 文件")
        return

    info(f"找到 {len(overlay_files)} 个 overlay 文件: {', '.join(sorted(overlay_files))}")

    # 扫描 G*.md 中的 overlay 引用
    referenced = set()
    if groups_dir.exists():
        for g_file in groups_dir.glob("G*.md"):
            content = g_file.read_text(encoding="utf-8")
            for m in re.finditer(r'overlays/(overlay_\S+\.md)', content):
                referenced.add(m.group(1))

    # 孤儿 overlay（未被任何 G 引用）
    orphans = overlay_files - referenced
    for orphan in sorted(orphans):
        warn("overlay", f"孤儿 overlay（未被任何 G*.md 引用）: {orphan}")

    # 断链引用（G 引用不存在的 overlay）
    broken = referenced - overlay_files
    for b in sorted(broken):
        fail("overlay", f"断链引用（G*.md 引用不存在的 overlay）: {b}")

    if not orphans and not broken:
        info("Overlay 引用一致")


def check_exam_isolation():
    """检查考核池隔离——每个检查单元只发现自己的考核池，只扫描本单元 lesson/practice"""
    section("考核池隔离")

    def _check_one_unit(unit_dir: Path) -> None:
        """以一个课程目录或 CourseRun 目录为检查单元。"""
        exam_dir = unit_dir / "_exam"
        papers_dir = exam_dir / "papers"
        if not papers_dir.exists():
            return
        # 收集本单元考核池卷号
        local_papers: list[str] = []
        for paper_dir in sorted(p for p in papers_dir.iterdir() if p.is_dir()):
            if (paper_dir / "paper.pdf").exists():
                local_papers.append(paper_dir.name)
        if not local_papers:
            return
        # 只用本单元卷号扫描本单元 lesson/practice
        for pattern in ["lesson*/**/*.md", "practice*/**/*.md"]:
            for md_file in unit_dir.glob(pattern):
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                for paper_id in local_papers:
                    if paper_id in content:
                        fail("exam_isolation",
                             f"考核池卷号 {paper_id} 出现在 {md_file.relative_to(ROOT_DIR)}")

    checked = 0
    # 旧路径
    courses_dir = MAIN_DIR / "30_courses"
    if courses_dir.exists():
        for course_dir in sorted(d for d in courses_dir.iterdir() if d.is_dir() and not d.name.startswith("_")):
            _check_one_unit(course_dir)
            checked += 1
    # 新路径 CourseRun
    runs_root = MAIN_DIR / "35_course_runs"
    if runs_root.is_dir():
        for run_dir in sorted(runs_root.glob("*/CR-*")):
            if run_dir.is_dir():
                _check_one_unit(run_dir)
                checked += 1
    if checked == 0:
        info("无课程目录（首次启动前正常）")
    else:
        info(f"已检查 {checked} 个单元的考核池隔离")


def check_skin_system():
    """检查皮肤系统"""
    section("皮肤系统")

    skin_yaml = ROOT_DIR / "skin" / "skin.yaml"
    if not skin_yaml.exists():
        fail("skin", "skin/skin.yaml 不存在")
        return

    content = skin_yaml.read_text(encoding="utf-8")

    # 提取 active
    active_match = re.search(r'^active[：:]\s*(\S+)', content, re.MULTILINE)
    if not active_match:
        fail("skin", "skin.yaml 缺少 active 字段")
        return

    active_skin = active_match.group(1).strip()
    info(f"active 皮肤: {active_skin}")

    # 提取注册表
    registry = {}
    for m in re.finditer(r'^(\S+)[：:]\s*(\S+)', content, re.MULTILINE):
        key = m.group(1).strip()
        val = m.group(2).strip()
        if key not in ("active",) and not key.startswith("#"):
            registry[key] = val

    # 检查 active 皮肤在注册表中
    if active_skin not in registry:
        fail("skin", f"active 皮肤 '{active_skin}' 未在注册表中登记")
        return

    skin_dir_name = registry[active_skin]
    skin_dir = ROOT_DIR / "skin" / skin_dir_name
    if not skin_dir.exists():
        fail("skin", f"active 皮肤目录不存在: skin/{skin_dir_name}")
        return

    # 检查皮肤元数据
    skin_meta = skin_dir / "skin.yaml"
    if not skin_meta.exists():
        fail("skin", f"皮肤元数据缺失: skin/{skin_dir_name}/skin.yaml")
        return

    meta_content = skin_meta.read_text(encoding="utf-8")

    # 检查 art_file 指向的文件是否存在
    art_match = re.search(r'^art_file[：:]\s*(\S+)', meta_content, re.MULTILINE)
    if art_match:
        art_file = art_match.group(1).strip()
        art_path = skin_dir / art_file
        if not art_path.exists():
            fail("skin", f"艺术文件不存在: skin/{skin_dir_name}/{art_file}")
        else:
            info(f"艺术文件: skin/{skin_dir_name}/{art_file}")

    # 检查 welcome_msg 不含教学指令词
    welcome_match = re.search(r'^welcome_msg[：:]\s*(.+)', meta_content, re.MULTILINE)
    if welcome_match:
        welcome_msg = welcome_match.group(1).strip()
        instruction_words = ["讲解", "教学", "上课", "复习", "预习", "做题", "练习"]
        for word in instruction_words:
            if word in welcome_msg:
                warn("skin", f"welcome_msg 含疑似教学指令词 '{word}'")
                break

    # 检查未登记的 SK* 文件夹
    skin_root = ROOT_DIR / "skin"
    registered_dirs = set(registry.values())
    for d in skin_root.iterdir():
        if d.is_dir() and d.name.startswith("SK"):
            if d.name not in registered_dirs:
                warn("skin", f"未登记的皮肤文件夹: skin/{d.name}")

    info("皮肤系统检查完成")


def check_pattern_declarations():
    """检查复利回路模式声明"""
    section("复利回路模式声明")

    pattern_path = ROOT_DIR / "main" / "00_core" / "pattern_retire_loop.md"
    if not pattern_path.exists():
        warn("pattern", "pattern_retire_loop.md 不存在")
        return

    content = pattern_path.read_text(encoding="utf-8")

    # 提取已登记的实例
    registered_instances = set()
    for m in re.finditer(r'\|\s*(\S+\.md)\s*\|.*复利回路.*\|', content):
        registered_instances.add(m.group(1))

    if not registered_instances:
        info("无复利回路模式实例登记")
        return

    info(f"登记了 {len(registered_instances)} 个模式实例")

    # 检查每个实例是否有头部声明
    required_params = ["【模式】", "【参数】", "【边界】"]
    for instance in registered_instances:
        instance_path = ROOT_DIR / "main" / instance
        if instance_path.exists():
            instance_content = instance_path.read_text(encoding="utf-8")
            missing = [p for p in required_params if p not in instance_content]
            if missing:
                warn("pattern", f"{instance} 缺少声明参数: {', '.join(missing)}")
            else:
                info(f"{instance} 声明完整")
        else:
            warn("pattern", f"登记的实例文件不存在: {instance}")


def check_external_resources():
    """检查共享资源索引的路径、字段和唯一性，不联网检查 URL。"""
    section("外部学习资料索引")
    old_path = ROOT_DIR / "main" / "00_core" / "external_resources.md"
    shared_path = ROOT_DIR / "main" / "30_courses" / "_shared" / "external_resources.md"
    if old_path.exists():
        fail("external_resources", f"旧资源索引仍在 00_core: {old_path.relative_to(ROOT_DIR)}")
    if not shared_path.exists():
        fail("external_resources", f"共享资源索引缺失: {shared_path.relative_to(ROOT_DIR)}")
        return

    required = [
        "资源 ID", "名称", "类型", "URL/本地路径", "适用课程",
        "适用知识点", "用途", "使用方式", "来源与许可", "最后核验日期",
    ]
    lines = shared_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    header = []
    rows = []
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        candidate = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if candidate != required:
            continue
        header = candidate
        j = i + 2
        while j < len(lines) and lines[j].strip().startswith("|"):
            if "---" not in lines[j]:
                rows.append([c.strip().strip("`") for c in lines[j].strip().strip("|").split("|")])
            j += 1
        break
    if header != required:
        fail("external_resources", f"共享资源索引缺少规定表头: {shared_path.relative_to(ROOT_DIR)}")
        return

    ids = {}
    locations = {}
    for row_no, row in enumerate(rows, start=1):
        if len(row) < len(required):
            fail("external_resources", f"共享索引第 {row_no} 行字段不足")
            continue
        resource_id = row[0].strip()
        location = row[3].strip().strip("`")
        if resource_id in ids:
            fail("external_resources", f"资源 ID 重复: {resource_id}")
        elif resource_id:
            ids[resource_id] = row_no
        if location in locations:
            fail("external_resources", f"资源 URL/本地路径重复: {location}")
        elif location and location not in {"—", "-"}:
            locations[location] = row_no

        if re.fullmatch(r"https?://[^\s|`]+", location):
            continue
        if "://" in location or location.startswith("www."):
            fail("external_resources", f"在线 URL 格式无效: {location}")
            continue
        if not location or location in {"—", "-"}:
            fail("external_resources", f"资源 {resource_id} 缺少 URL/本地路径")
            continue
        candidates = [
            (ROOT_DIR / location).resolve(),
            (ROOT_DIR / "main" / location).resolve(),
            (shared_path.parent / location).resolve(),
        ]
        if ROOT_DIR.name != "t2ag-lite" and not any(p.exists() for p in candidates):
            fail("external_resources", f"登记的本地路径不存在: {location}")

    active_paths = [ROOT_DIR / "main" / "t2ag.md"]
    for dirname in ("10_case", "20_groups", "25_general", "40_practices", "50_playbook"):
        root = ROOT_DIR / "main" / dirname
        if root.exists():
            active_paths.extend(root.rglob("*.md"))
    courses = ROOT_DIR / "main" / "30_courses"
    if courses.exists():
        active_paths.extend(courses.glob("*/*_book/README.md"))
    # 新 Definition 教材 README
    defs_root = MAIN_DIR / "30_course_definitions"
    if defs_root.exists():
        active_paths.extend(defs_root.glob("*/*_book/README.md"))
    old_tokens = ("00_core/external_resources.md", "main/00_core/external_resources.md")
    for path in active_paths:
        content = path.read_text(encoding="utf-8", errors="ignore")
        if any(token in content for token in old_tokens):
            fail("external_resources", f"活动规则仍引用旧资源索引路径: {path.relative_to(ROOT_DIR)}")


REFLECTION_HEADER = ["课程代码", "课程名称", "当前感想数量", "最近记录", "最近日期"]
REFLECTION_ID_RE = re.compile(r"^####\s+(REFL-([A-Z0-9]+)-(\d{4}))｜(\d{4}-\d{2}-\d{2})(?:\s+.*)?$")
COURSE_SECTION_RE = re.compile(r"^##\s+([A-Z]{2,}[A-Z0-9]*)\b.*$")


def _pipe_cells(line):
    return [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]


def check_reflection_indexes():
    """校验感想正文真相源与顶部可重算缓存。"""
    section("学习使命与课程感想索引")
    students = MAIN_DIR / "10_case" / "students"
    if not students.exists():
        info("无学生档案目录，跳过")
        return
    global_ids = {}
    checked = 0
    for path in sorted(students.glob("S*/course_reflections.md")):
        checked += 1
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        table_rows = {}
        found_header = False
        for i, line in enumerate(lines):
            if not line.strip().startswith("|") or _pipe_cells(line) != REFLECTION_HEADER:
                continue
            found_header = True
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = _pipe_cells(lines[j])
                if cells and cells[0] not in {"", "(空)"}:
                    if len(cells) < len(REFLECTION_HEADER):
                        fail("reflections", f"课程感想目录字段不足: {path.relative_to(ROOT_DIR)} 第 {j + 1} 行")
                    else:
                        table_rows[cells[0]] = cells
                j += 1
            break
        if not found_header:
            fail("reflections", f"课程感想缺规定目录表头: {path.relative_to(ROOT_DIR)}")
            continue

        records = {}
        for line in lines:
            match = REFLECTION_ID_RE.match(line)
            if not match:
                continue
            record_id, code, _, date = match.groups()
            if record_id in global_ids:
                fail("reflections", f"课程感想 ID 重复: {record_id}")
            else:
                global_ids[record_id] = path
            records.setdefault(code, []).append((record_id, date))

        sections = {}
        for i, line in enumerate(lines):
            match = COURSE_SECTION_RE.match(line)
            if not match:
                continue
            code = match.group(1)
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
            sections[code] = "\n".join(lines[i:end])

        if not table_rows and "学习使命（最后确认：—）" not in "\n".join(lines):
            fail("reflections", f"空学生模板缺学习使命字段: {path.relative_to(ROOT_DIR)}")
        for code in sorted(set(table_rows) | set(records) | set(sections)):
            if code not in table_rows:
                fail("reflections", f"课程感想正文有 {code}，但目录无对应行: {path.relative_to(ROOT_DIR)}")
                continue
            if code not in sections:
                fail("reflections", f"课程感想目录有 {code}，但正文无课程段: {path.relative_to(ROOT_DIR)}")
                continue
            if "学习使命（最后确认：" not in sections[code]:
                fail("reflections", f"课程段缺学习使命: {path.relative_to(ROOT_DIR)} / {code}")
            row = table_rows[code]
            actual = records.get(code, [])
            try:
                cached_count = int(row[2])
            except ValueError:
                fail("reflections", f"课程感想数量不是整数: {path.relative_to(ROOT_DIR)} / {code}")
                continue
            if cached_count != len(actual):
                fail("reflections", f"课程感想数量不一致: {path.relative_to(ROOT_DIR)} / {code}")
            expected_id, expected_date = actual[-1] if actual else ("—", "—")
            if row[3] != expected_id or row[4] != expected_date:
                fail("reflections", f"课程感想最近记录不一致: {path.relative_to(ROOT_DIR)} / {code}")
    info(f"已检查 {checked} 份课程感想档案")


VALID_COURSE_DRIVERS = {"textbook", "goal", "project", "praxis"}
VALID_MISTAKE_STATES = {"active", "maintenance", "aged"}


def check_course_drivers():
    section("课程驱动")
    statuses = sorted((MAIN_DIR / "30_courses").glob("*/course_status.md"))
    # 新路径 CourseRun
    runs_root = MAIN_DIR / "35_course_runs"
    if runs_root.is_dir():
        statuses = statuses + sorted(runs_root.glob("*/CR-*/course_status.md"))
    if not statuses:
        info("无实例课程状态文件，跳过")
        return
    for status in statuses:
        content = status.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"^course_driver:\s*([a-z]+)\s*$", content, re.MULTILINE)
        if not match:
            fail("course_driver", f"course_status 缺 course_driver: {status.relative_to(ROOT_DIR)}")
            continue
        driver = match.group(1)
        if driver not in VALID_COURSE_DRIVERS:
            fail("course_driver", f"course_driver 非法: {status.relative_to(ROOT_DIR)} = {driver}")
        if driver == "praxis" and "本课程的完善需要学生自己生命力的参与" not in content:
            fail("course_driver", f"praxis 课程缺生命力参与声明: {status.relative_to(ROOT_DIR)}")
    info(f"已检查 {len(statuses)} 门课程的驱动类型")


def _without_fenced_code(content):
    return re.sub(r"```.*?```", "", content, flags=re.DOTALL)


def check_mistake_bank_generation_template():
    section("错题库生成模板")
    path = MAIN_DIR / "50_playbook" / "new_course_init.md"
    if not path.exists():
        fail("mistake_template", "new_course_init.md 不存在")
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
        fail("mistake_template", f"new_course_init 错题库生成模板缺字段: {', '.join(missing)}")
    else:
        info("new_course_init 保留完整错题库生成与合并规则")


def check_mistake_bank_schema():
    section("知识点错题库")
    banks = sorted((MAIN_DIR / "30_courses").glob("*/mistake_bank.md"))
    # 新路径 CourseRun
    runs_root = MAIN_DIR / "35_course_runs"
    if runs_root.is_dir():
        banks = banks + sorted(runs_root.glob("*/CR-*/mistake_bank.md"))
    if not banks:
        info("无实例错题库，跳过")
        return
    required = (
        "## 活跃知识点", "## 维护知识点", "## 陈年知识点", "知识点键", "当前周期", "状态",
        "当前周期摘要", "陈年连续正确", "最近陈年复习卷", "下次陈年日历检查",
    )
    legacy = ("权重机制", "权重 >", "答对 -1", "权重：")
    for path in banks:
        content = path.read_text(encoding="utf-8", errors="ignore")
        for token in required:
            if token not in content:
                fail("mistake_bank", f"知识点错题库缺字段「{token}」: {path.relative_to(ROOT_DIR)}")
        for token in legacy:
            if token in content:
                fail("mistake_bank", f"知识点错题库残留旧权重规则「{token}」: {path.relative_to(ROOT_DIR)}")
        body = _without_fenced_code(content)
        entries = list(re.finditer(r"^###\s+M-(\d{4})\s*$", body, re.MULTILINE))
        max_id = 0
        for index, match in enumerate(entries):
            max_id = max(max_id, int(match.group(1)))
            end = entries[index + 1].start() if index + 1 < len(entries) else len(body)
            block = body[match.end():end]
            state_match = re.search(r"^- 状态：([^\n]+)$", block, re.MULTILINE)
            if not state_match or state_match.group(1).strip() not in VALID_MISTAKE_STATES:
                fail("mistake_bank", f"错题条目 M-{match.group(1)} 状态缺失或非法: {path.relative_to(ROOT_DIR)}")
            for field in ("知识点键", "当前周期", "当前周期摘要", "陈年连续正确", "最近陈年复习卷", "下次陈年日历检查"):
                if not re.search(rf"^- {field}：.+$", block, re.MULTILINE):
                    fail("mistake_bank", f"错题条目 M-{match.group(1)} 缺{field}: {path.relative_to(ROOT_DIR)}")
        next_match = re.search(r"^next_id:\s*(\d+)\s*$", content, re.MULTILINE)
        if not next_match:
            fail("mistake_bank", f"知识点错题库缺 next_id: {path.relative_to(ROOT_DIR)}")
        elif int(next_match.group(1)) <= max_id:
            fail("mistake_bank", f"知识点错题库 next_id 未超过现有最大 ID: {path.relative_to(ROOT_DIR)}")
    info(f"已检查 {len(banks)} 份知识点错题库")


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


def check_execution_baseline_schema():
    """检查 0.1.2 通用执行基线；空 skeleton 只检查定义文件。"""
    section("0.1.2 执行基线")
    progress = ROOT_DIR / "main" / "50_playbook" / "progress_tracking.md"
    required_tokens = (
        "planned", "ongoing", "completed", "dropped",
        "checkpoint", "completion node", "最多 12", "保存进度",
    )
    if not progress.exists():
        fail("execution_baseline", "progress_tracking.md 缺失")
    else:
        content = progress.read_text(encoding="utf-8", errors="ignore")
        missing = [token for token in required_tokens if token not in content]
        if missing:
            fail("execution_baseline", f"progress_tracking 缺规则: {missing}")

    registry = ROOT_DIR / "main" / "70_tools" / "artifact_registry.json"
    if not registry.exists():
        fail("execution_baseline", "artifact_registry.json 缺失")
    else:
        try:
            payload = json.loads(registry.read_text(encoding="utf-8-sig"))
            ids = [item.get("artifact_id") for item in payload.get("artifacts", [])]
            if any(not value for value in ids) or len(ids) != len(set(ids)):
                fail("execution_baseline", "artifact_id 缺失或重复")
        except (OSError, json.JSONDecodeError) as exc:
            fail("execution_baseline", f"artifact_registry.json 不可解析: {exc}")

    statuses = sorted((ROOT_DIR / "main" / "30_courses").glob("*/course_status.md"))
    for path in statuses:
        content = path.read_text(encoding="utf-8-sig", errors="ignore")
        lifecycle = re.search(r"^lifecycle_status:\s*([a-z_]+)", content, re.MULTILINE)
        if not lifecycle or lifecycle.group(1) not in {"planned", "ongoing", "completed", "dropped"}:
            fail("execution_baseline", f"course_status lifecycle_status 缺失或非法: {path.relative_to(ROOT_DIR)}")
    info("两级进度、artifact 注册表与课程生命周期 schema 已检查")


def _tagged_core_playbooks(root):
    folder = root / "main" / "50_playbook"
    if not folder.exists():
        return {}
    result = {}
    for path in sorted(folder.glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"^\*\*保护级别\*\*：core-playbook\s*$", content, re.MULTILINE):
            result[path.name] = path
    return result


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_core_playbook_distribution():
    section("core-playbook 发行一致性")
    local = _tagged_core_playbooks(ROOT_DIR)
    for name in sorted(REQUIRED_CORE_PLAYBOOKS - set(local)):
        fail("core_playbook", f"缺少必需 core-playbook 或保护标记: main/50_playbook/{name}")

    sibling_roots = [ROOT_DIR.parent / name for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")]
    if not all((root / "main" / "50_playbook").exists() for root in sibling_roots):
        info(f"本地 core-playbook {len(local)} 个；独立发行环境跳过跨仓哈希")
        return
    distributions = {root.name: _tagged_core_playbooks(root) for root in sibling_roots}
    all_names = set().union(*(set(files) for files in distributions.values()))
    for name in sorted(all_names):
        missing = [repo for repo, files in distributions.items() if name not in files]
        if missing:
            fail("core_playbook", f"core-playbook 未同步到 {', '.join(missing)}: {name}")
            continue
        hashes = {repo: _sha256(files[name]) for repo, files in distributions.items()}
        if len(set(hashes.values())) != 1:
            fail("core_playbook", f"core-playbook 三版本正文分叉: {name}")
    info(f"已比对三版本 {len(all_names)} 个 core-playbook")


def check_book_management():
    """检查教材管理规则"""
    section("教材管理")

    book_mgmt_path = ROOT_DIR / "main" / "50_playbook" / "book_management.md"
    if not book_mgmt_path.exists():
        fail("book_mgmt", "50_playbook/book_management.md 不存在")
        return

    info("book_management.md 存在")

    # 检查课程教材目录结构
    courses_dir = ROOT_DIR / "main" / "30_courses"
    if not courses_dir.exists():
        info("30_courses/ 不存在（首次启动前正常）")
        return

    for course_dir in courses_dir.iterdir():
        if not course_dir.is_dir():
            continue
        book_dir = course_dir / f"{course_dir.name}_book"
        if book_dir.exists():
            # 检查 README.md
            readme = book_dir / "README.md"
            if not readme.exists():
                warn("book_mgmt", f"{book_dir.name}/README.md 缺失")
            else:
                info(f"{book_dir.name}/README.md 存在")


# ---------- 培养方案语义检查 ----------

def check_curricula_semantics():
    """skeleton 必须带通用领域规则和空培养方案骨架，不带实例培养方案正文。"""
    domain_model = MAIN_DIR / "00_core" / "domain_model.md"
    if not domain_model.exists():
        fail("curricula", "缺少领域模型真相源：00_core/domain_model.md")
    curricula_dir = MAIN_DIR / "15_curricula"
    if not curricula_dir.exists():
        fail("curricula", "缺少 15_curricula 培养方案骨架")
    elif not (curricula_dir / "_README.md").exists():
        fail("curricula", "缺少 15_curricula/_README.md")
    # 检查子目录真实存在
    if not (curricula_dir / "baseline").is_dir():
        fail("curricula", "缺少 15_curricula/baseline/ 子目录")
    if not (curricula_dir / "references").is_dir():
        fail("curricula", "缺少 15_curricula/references/ 子目录")




def check_domain_model_distribution():
    """检查 domain_model.md 三发行版一致性。"""
    section("领域模型分布一致性")
    sibling_roots = [ROOT_DIR.parent / name for name in ("t2ag", "t2ag-skeleton", "t2ag-lite")]
    existing_roots = [root for root in sibling_roots if root.exists()]

    if len(existing_roots) < 3:
        info(f"domain_model 跨仓检查跳过：仅检测到 {len(existing_roots)} 个发行版目录（独立运行模式）")
        return

    dm_files = {}
    for root in sibling_roots:
        dm = root / "main" / "00_core" / "domain_model.md"
        if dm.exists():
            dm_files[root.name] = dm
        else:
            fail("domain_model", f"domain_model.md 缺失：{root.name}/main/00_core/domain_model.md")

    if len(dm_files) < 3:
        fail("domain_model", f"domain_model.md 三发行版不完整：仅 {list(dm_files.keys())}")
        return

    hashes = {name: _sha256(path) for name, path in dm_files.items()}
    if len(set(hashes.values())) != 1:
        fail("domain_model", f"domain_model.md 三版本分叉：{hashes}")
    else:
        info("domain_model.md 三版本一致")


# 对象分层迁移新目标目录（结构准备批次建立的空骨架）
NEW_OBJECT_DIRS = [
    "12_activity_records",
    "20_execution",
    "20_execution/groups",
    "20_execution/groups/overlays",
    "20_execution/groups/preplans",
    "20_execution/bindings",
    "30_course_definitions",
    "30_course_definitions/_shared",
    "35_course_runs",
    "40_field_practices",
]

# skeleton 新目录不得出现的真实实例标识
_INSTANCE_RE = re.compile(
    r"S0\d{2}|MATH\d{4}[A-Z]?|CS\d{4}|IV\d{4}|PY\d{4}|DS\d{4}r?|"
    r"PHIL\d{4}r?|LOGIC\d{4}r?|CR-S\d|AR-S\d|FP-S\d|"
    r"\bG\d{2}\b|\bP\d{3}\b|\bR\d{3}\b"
)

# 对象分层枚举（来源：domain_model.md / naming_conventions.md）
_VALID_COURSE_TYPES = {"mastery", "project", "praxis"}
_VALID_DRIVERS = {"textbook", "goal", "project", "praxis"}
_VALID_DEF_STATUS = {"active", "retired"}
_VALID_RUN_LIFECYCLE = {"planned", "ongoing", "completed", "dropped"}
_VALID_AR_STATUS = {"recording", "paused", "closed"}
_VALID_BINDING_STATUS = {"planned", "active", "paused", "ended"}
_VALID_G_STATUS = {"planned", "active", "paused", "archived"}
_TYPE_DRIVER_MAP = {
    "mastery": {"textbook", "goal"},
    "project": {"project"},
    "praxis": {"praxis"},
}


def check_object_layer_migration():
    """对象分层迁移双路径结构检查（skeleton 通用规则）。

    规则：
    1. 新目标目录必须存在
    2. skeleton 新目录只允许 _README.md，不得含实例名（文件名+正文）
    3. 按物理位置决定预期对象类型，不得绕过
    4. 缺 frontmatter / 缺 type / type 与路径不符 / 缺必填字段 → FAIL
    5. 引用完整性检查
    6. 新旧路径碰撞
    7. 同一 CourseRun 同时 active G/R → FAIL
    8. 所有对象 ID 全局唯一
    """
    section("对象分层迁移（双路径结构）")
    is_skeleton = ROOT_DIR.name == "t2ag-skeleton"

    def _rel(p):
        return str(p.relative_to(ROOT_DIR)).replace("\\", "/")

    def _fm_fields(path):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
        except OSError:
            return {}
        if not text.startswith("---"):
            return {}
        end = text.find("\n---", 3)
        if end == -1:
            return {}
        fields = {}
        for line in text[3:end].splitlines():
            m = re.match(r"^([A-Za-z][A-Za-z0-9_]*):\s*(.*?)\s*$", line)
            if m:
                fields[m.group(1)] = m.group(2)
        return fields

    def _instance_files(directory):
        hits = []
        for p in sorted(directory.rglob("*")):
            if p.name == "_README.md":
                continue
            if _INSTANCE_RE.search(p.name):
                hits.append(str(p.relative_to(MAIN_DIR)).replace("\\", "/"))
        return hits

    # 1. 新目录存在性
    missing = [d for d in NEW_OBJECT_DIRS if not (MAIN_DIR / d).is_dir()]
    if missing:
        fail("object_layer", f"缺少新目标目录：{missing}")
    else:
        info("新目标目录齐全")

    # 2. skeleton 新目录只允许 _README.md，不得含实例名（文件名 + 正文）
    if is_skeleton:
        for d in NEW_OBJECT_DIRS:
            target = MAIN_DIR / d
            if not target.is_dir():
                continue
            for p in sorted(target.rglob("*")):
                if p.is_file() and p.name != "_README.md":
                    fail("object_layer", f"skeleton 新目录只允许 _README.md：main/{d}/{p.name}")
                if p.is_file() and p.name == "_README.md":
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    hits = _INSTANCE_RE.findall(content)
                    if hits:
                        fail("object_layer", f"skeleton README 正文含实例标识：main/{d}/_README.md -> {sorted(set(hits))}")
            hits = _instance_files(target)
            if hits:
                fail("object_layer", f"skeleton 新目录含真实实例名：{hits}")

    # 3. 按物理容器发现对象（错误命名只 FAIL，不导致对象消失）
    _OBJ_REQUIRED = {
        "course_definition": ["type", "course_definition_id", "name", "course_type", "default_driver", "prerequisites", "status"],
        "course_run": ["type", "course_run_id", "case_id", "course_definition_id", "lifecycle_status", "course_driver"],
        "activity_record": ["type", "activity_record_id", "case_id", "record_status", "upgraded_to_course_run"],
        "field_practice": ["type", "field_practice_id", "case_id", "practice_status", "linked_course_runs", "evidence_index"],
        "execution_group": ["type", "group_id", "case_id", "status", "course_runs", "field_practices"],
        "elastic_binding": ["type", "binding_id", "case_id", "course_run_id", "binding_status"],
    }

    idx_definitions = {}
    idx_runs = {}
    idx_practices = {}
    idx_groups = {}
    idx_bindings = {}
    idx_records = {}
    all_ids = {}

    def _parse_inline_list(val, path, field):
        val = val.strip()
        if not val:
            return []
        if val == "[]":
            return []
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            raw_items = inner.split(",")
            if any(not x.strip() for x in raw_items):
                fail("object_layer", f"{_rel(path)} 字段 {field} 单行数组含空元素：{val[:40]}")
                return [x.strip().strip("'\"") for x in raw_items if x.strip()]
            return [x.strip().strip("'\"") for x in raw_items if x.strip()]
        fail("object_layer", f"{_rel(path)} 字段 {field} 不是单行数组格式：{val[:40]}")
        return []

    def _discover_objects():
        found = []
        defs_root = MAIN_DIR / "30_course_definitions"
        if defs_root.is_dir():
            for d in sorted(defs_root.iterdir()):
                if d.name.startswith("_"):
                    continue
                if d.is_file():
                    if d.suffix == ".md":
                        fail("object_layer", f"CourseDefinition 载体位置非法（不得位于定义根目录）：{_rel(d)}")
                    continue
                if not d.is_dir():
                    continue
                carrier = d / "course_definition.md"
                if carrier.is_file():
                    found.append((carrier, "course_definition", "course_definition_id"))
                else:
                    fail("object_layer", f"CourseDefinition 缺少正式载体 course_definition.md：{_rel(d)}")
        runs_root = MAIN_DIR / "35_course_runs"
        if runs_root.is_dir():
            for case_dir in sorted(runs_root.iterdir()):
                if not case_dir.is_dir() or case_dir.name.startswith("_"):
                    continue
                for item in sorted(case_dir.iterdir()):
                    if item.name.startswith("_"):
                        continue
                    if item.is_file():
                        if item.suffix == ".md":
                            fail("object_layer", f"CourseRun 载体位置非法（不得位于 Case 根目录）：{_rel(item)}")
                        continue
                    if not item.is_dir():
                        continue
                    carrier = item / "course_status.md"
                    if carrier.is_file():
                        found.append((carrier, "course_run", "course_run_id"))
                    else:
                        fail("object_layer", f"CourseRun 缺少正式载体 course_status.md：{_rel(item)}")
        ar_root = MAIN_DIR / "12_activity_records"
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
                            fail("object_layer", f"ActivityRecord 载体位置非法（不得位于嵌套子目录）：{_rel(item)}")
                        continue
                    if item.is_file() and item.suffix == ".md":
                        found.append((item, "activity_record", "activity_record_id"))
        fp_root = MAIN_DIR / "40_field_practices"
        if fp_root.is_dir():
            for case_dir in sorted(fp_root.iterdir()):
                if not case_dir.is_dir() or case_dir.name.startswith("_"):
                    continue
                for item in sorted(case_dir.iterdir()):
                    if item.name.startswith("_"):
                        continue
                    if item.is_file():
                        if item.suffix == ".md":
                            fail("object_layer", f"FieldPractice 载体位置非法（不得位于 Case 根目录）：{_rel(item)}")
                        continue
                    if not item.is_dir():
                        continue
                    carrier = item / "field_practice.md"
                    if carrier.is_file():
                        found.append((carrier, "field_practice", "field_practice_id"))
                    else:
                        fail("object_layer", f"FieldPractice 缺少正式载体 field_practice.md：{_rel(item)}")
        _G_RESERVED_DIRS = {"overlays", "preplans"}
        g_root = MAIN_DIR / "20_execution" / "groups"
        if g_root.is_dir():
            for item in sorted(g_root.iterdir()):
                if item.name.startswith("_"):
                    continue
                if item.is_dir():
                    if item.name not in _G_RESERVED_DIRS:
                        nested = [f for f in item.rglob("*.md") if f.name != "_README.md"]
                        if nested:
                            fail("object_layer", f"G 载体位置非法（不得位于非保留子目录）：{_rel(item)}")
                    continue
                if item.is_file() and item.suffix == ".md":
                    found.append((item, "execution_group", "group_id"))
        r_root = MAIN_DIR / "20_execution" / "bindings"
        if r_root.is_dir():
            for item in sorted(r_root.iterdir()):
                if item.name.startswith("_"):
                    continue
                if item.is_dir():
                    nested = [f for f in item.rglob("*.md") if f.name != "_README.md"]
                    if nested:
                        fail("object_layer", f"R 载体位置非法（不得位于嵌套子目录）：{_rel(item)}")
                    continue
                if item.is_file() and item.suffix == ".md":
                    found.append((item, "elastic_binding", "binding_id"))
        return found

    for md, expected_type, id_field in _discover_objects():
        if md.name == "_README.md":
            continue
        if not md.is_file():
            continue
        try:
            raw = md.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
        except OSError:
            fail("object_layer", f"无法读取：{_rel(md)}")
            continue
        if not raw.startswith("---"):
            fail("object_layer", f"缺 frontmatter：{_rel(md)}")
            continue
        fields = _fm_fields(md)
        otype = fields.get("type", "")
        if not otype:
            fail("object_layer", f"缺 type 字段：{_rel(md)}")
            continue
        if otype != expected_type:
            fail("object_layer", f"type 与路径不符：{_rel(md)} type={otype} 预期={expected_type}")
            continue
        for req in _OBJ_REQUIRED.get(expected_type, []):
            if req not in fields or not fields[req].strip():
                fail("object_layer", f"缺必填字段：{_rel(md)} -> {req}")
        obj_id = fields.get(id_field, "")
        if obj_id:
            loc_str = str(md.relative_to(MAIN_DIR)).replace("\\", "/")
            if obj_id in all_ids:
                fail("object_layer", f"对象 ID 重复：{obj_id} 在 {all_ids[obj_id]} 和 {loc_str}")
            all_ids[obj_id] = loc_str
        for arr_field in ("course_runs", "field_practices", "linked_course_runs", "prerequisites"):
            if arr_field in fields:
                _parse_inline_list(fields[arr_field], md, arr_field)
        # ---- ID 与物理路径一致性 ----
        if obj_id and expected_type == "course_definition":
            parent_name = md.parent.name
            if not parent_name.startswith(obj_id + "_"):
                fail("object_layer", f"CourseDefinition 目录名必须以 ID+下划线开头：{_rel(md)} (dir={parent_name}, id={obj_id})")
            elif len(parent_name) <= len(obj_id) + 1:
                fail("object_layer", f"CourseDefinition 目录名下划线后标题为空：{_rel(md)}")
        elif obj_id and expected_type == "course_run":
            run_dir_name = md.parent.name
            if run_dir_name != obj_id:
                fail("object_layer", f"CourseRun 目录名必须等于 course_run_id：{_rel(md)} (dir={run_dir_name}, id={obj_id})")
            case_dir_name = md.parent.parent.name
            cid_val = fields.get("case_id", "")
            if cid_val and case_dir_name != cid_val:
                fail("object_layer", f"CourseRun case 父目录必须等于 case_id：{_rel(md)} (dir={case_dir_name}, case_id={cid_val})")
            did_val = fields.get("course_definition_id", "")
            if cid_val and did_val:
                expected_run_id = f"CR-{cid_val}-{did_val}"
                if obj_id != expected_run_id:
                    fail("object_layer", f"course_run_id 必须等于 CR-<case_id>-<definition_id>：{_rel(md)} (id={obj_id}, expected={expected_run_id})")
        elif obj_id and expected_type == "activity_record":
            if not re.fullmatch(r"AR-[^-]+-\d{4}", obj_id):
                fail("object_layer", f"ActivityRecord ID 必须符合 AR-<case_id>-NNNN：{_rel(md)} (id={obj_id})")
            else:
                id_case = obj_id.split("-")[1]
                cid_val = fields.get("case_id", "")
                if cid_val and id_case != cid_val:
                    fail("object_layer", f"ActivityRecord ID 中 case 与 case_id 不一致：{_rel(md)}")
            ar_case_dir = md.parent.name
            cid_val = fields.get("case_id", "")
            if cid_val and ar_case_dir != cid_val:
                fail("object_layer", f"ActivityRecord case 父目录与 case_id 不一致：{_rel(md)} (dir={ar_case_dir}, case_id={cid_val})")
            stem = md.stem
            if not stem.startswith(obj_id + "_"):
                fail("object_layer", f"ActivityRecord 文件名必须以 ID+下划线开头：{_rel(md)}")
            elif len(stem) <= len(obj_id) + 1:
                fail("object_layer", f"ActivityRecord 文件名下划线后标题为空：{_rel(md)}")
        elif obj_id and expected_type == "field_practice":
            if not re.fullmatch(r"FP-[^-]+-\d{4}", obj_id):
                fail("object_layer", f"FieldPractice ID 必须符合 FP-<case_id>-NNNN：{_rel(md)} (id={obj_id})")
            else:
                id_case = obj_id.split("-")[1]
                cid_val = fields.get("case_id", "")
                if cid_val and id_case != cid_val:
                    fail("object_layer", f"FieldPractice ID 中 case 与 case_id 不一致：{_rel(md)}")
            fp_dir_name = md.parent.name
            if not fp_dir_name.startswith(obj_id + "_"):
                fail("object_layer", f"FieldPractice 目录名必须以 ID+下划线开头：{_rel(md)}")
            elif len(fp_dir_name) <= len(obj_id) + 1:
                fail("object_layer", f"FieldPractice 目录名下划线后标题为空：{_rel(md)}")
            case_dir_name = md.parent.parent.name
            cid_val = fields.get("case_id", "")
            if cid_val and case_dir_name != cid_val:
                fail("object_layer", f"FieldPractice case 父目录与 case_id 不一致：{_rel(md)}")
        elif obj_id and expected_type == "execution_group":
            if not re.fullmatch(r"G\d{2}", obj_id):
                fail("object_layer", f"group_id 必须符合 G+两位数字：{_rel(md)} (id={obj_id})")
            if md.stem != obj_id:
                fail("object_layer", f"G 文件 stem 必须等于 group_id：{_rel(md)}")
        elif obj_id and expected_type == "elastic_binding":
            if not re.fullmatch(r"R\d{3}", obj_id):
                fail("object_layer", f"binding_id 必须符合 R+三位数字：{_rel(md)} (id={obj_id})")
            stem = md.stem
            if not stem.startswith(obj_id + "_"):
                fail("object_layer", f"R 文件名必须以 ID+下划线开头：{_rel(md)}")
            elif len(stem) <= len(obj_id) + 1:
                fail("object_layer", f"R 文件名下划线后标题为空：{_rel(md)}")
        # ---- 枚举验证 ----
        if expected_type == "course_definition":
            ct = fields.get("course_type", "")
            if ct and ct not in _VALID_COURSE_TYPES:
                fail("object_layer", f"CourseDefinition course_type 非法：{_rel(md)} = {ct}")
            dd = fields.get("default_driver", "")
            if dd and dd not in _VALID_DRIVERS:
                fail("object_layer", f"CourseDefinition default_driver 非法：{_rel(md)} = {dd}")
            st = fields.get("status", "")
            if st and st not in _VALID_DEF_STATUS:
                fail("object_layer", f"CourseDefinition status 非法：{_rel(md)} = {st}")
            if ct and dd and ct in _TYPE_DRIVER_MAP and dd not in _TYPE_DRIVER_MAP[ct]:
                fail("object_layer", f"CourseDefinition default_driver 与 course_type 不匹配：{_rel(md)}")
        elif expected_type == "course_run":
            ls = fields.get("lifecycle_status", "")
            if ls and ls not in _VALID_RUN_LIFECYCLE:
                fail("object_layer", f"CourseRun lifecycle_status 非法：{_rel(md)} = {ls}")
            cd = fields.get("course_driver", "")
            if cd and cd not in _VALID_DRIVERS:
                fail("object_layer", f"CourseRun course_driver 非法：{_rel(md)} = {cd}")
        elif expected_type == "activity_record":
            rs = fields.get("record_status", "")
            if rs and rs not in _VALID_AR_STATUS:
                fail("object_layer", f"ActivityRecord record_status 非法：{_rel(md)} = {rs}")
        elif expected_type == "elastic_binding":
            bs = fields.get("binding_status", "")
            if bs and bs not in _VALID_BINDING_STATUS:
                fail("object_layer", f"R binding_status 非法：{_rel(md)} = {bs}")
        elif expected_type == "execution_group":
            gs = fields.get("status", "")
            if gs and gs not in _VALID_G_STATUS:
                fail("object_layer", f"G status 非法：{_rel(md)} = {gs}")
        fields["_path"] = str(md.relative_to(MAIN_DIR)).replace("\\", "/")
        if expected_type == "course_definition":
            idx_definitions[obj_id] = fields
        elif expected_type == "course_run":
            idx_runs[obj_id] = fields
        elif expected_type == "activity_record":
            idx_records[obj_id] = fields
        elif expected_type == "field_practice":
            idx_practices[obj_id] = fields
        elif expected_type == "execution_group":
            idx_groups[obj_id] = fields
        elif expected_type == "elastic_binding":
            idx_bindings[obj_id] = fields

    # 5. 引用完整性（无条件验证）
    students_dir = MAIN_DIR / "10_case" / "students"
    case_ids = set()
    if students_dir.is_dir():
        case_ids = {d.name for d in students_dir.iterdir() if d.is_dir()}

    for run_id, f in idx_runs.items():
        cid = f.get("case_id", "")
        if cid and cid not in case_ids:
            fail("object_layer", f"CourseRun {run_id} 引用的 Case 不存在：{cid}")
        did = f.get("course_definition_id", "")
        if did and did not in idx_definitions:
            fail("object_layer", f"CourseRun {run_id} 引用的 CourseDefinition 不存在：{did}")
        if did and did in idx_definitions:
            def_type = idx_definitions[did].get("course_type", "")
            run_driver = f.get("course_driver", "")
            if def_type and run_driver and def_type in _TYPE_DRIVER_MAP:
                if run_driver not in _TYPE_DRIVER_MAP[def_type]:
                    fail("object_layer", f"CourseRun {run_id} driver 与 Definition 类型不匹配：type={def_type}, driver={run_driver}")

    # CourseDefinition.prerequisites 验证
    _old_course_codes = set()
    _old_courses_dir = MAIN_DIR / "30_courses"
    if _old_courses_dir.is_dir():
        for _cs in _old_courses_dir.glob("*/course_status.md"):
            _fm = _fm_fields(_cs)
            _code = _fm.get("course", "")
            if _code:
                _old_course_codes.add(_code)
    _prereq_graph = {}  # def_id -> [new-path prereq ids]
    for def_id, f in idx_definitions.items():
        prereqs = _parse_inline_list(f.get("prerequisites", "[]"), MAIN_DIR / f["_path"], "prerequisites")
        if len(prereqs) != len(set(prereqs)):
            fail("object_layer", f"CourseDefinition prerequisites 重复：{def_id}")
        if def_id in prereqs:
            fail("object_layer", f"CourseDefinition 不得把自身列为 prerequisite：{def_id}")
        new_path_refs = []
        for p in prereqs:
            if p == def_id:
                continue
            if p in idx_definitions:
                new_path_refs.append(p)
            elif p in _old_course_codes:
                pass  # 旧路径兼容引用，视为叶节点
            else:
                fail("object_layer", f"CourseDefinition prerequisite 不存在：{def_id} -> {p}")
        _prereq_graph[def_id] = new_path_refs
    # 确定性循环检测（DFS）
    _WHITE, _GRAY, _BLACK = 0, 1, 2
    _color = {k: _WHITE for k in _prereq_graph}
    _cycle_path = []

    def _dfs_cycle(node):
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
                fail("object_layer", f"CourseDefinition prerequisites 形成循环：{' -> '.join(_cycle_path)}")
                break

    for ar_id, f in idx_records.items():
        cid = f.get("case_id", "")
        if cid and cid not in case_ids:
            fail("object_layer", f"ActivityRecord {ar_id} 引用的 Case 不存在：{cid}")
        # upgraded_to_course_run 验证
        upgraded = f.get("upgraded_to_course_run", "").strip()
        if upgraded and upgraded != "—":
            if upgraded not in idx_runs:
                fail("object_layer", f"ActivityRecord 升级指向的 CourseRun 不存在：{ar_id} -> {upgraded}")
            else:
                run_case = idx_runs[upgraded].get("case_id", "")
                if cid and run_case and run_case != cid:
                    fail("object_layer", f"ActivityRecord 跨 Case 升级到 CourseRun：{ar_id}.case_id={cid}, {upgraded}.case_id={run_case}")

    for fp_id, f in idx_practices.items():
        cid = f.get("case_id", "")
        if cid and cid not in case_ids:
            fail("object_layer", f"FieldPractice {fp_id} 引用的 Case 不存在：{cid}")
        linked = _parse_inline_list(f.get("linked_course_runs", "[]"), MAIN_DIR / f["_path"], "linked_course_runs")
        for lr in linked:
            if lr not in idx_runs:
                fail("object_layer", f"FieldPractice {fp_id} 关联的 CourseRun 不存在：{lr}")
            else:
                run_def = idx_runs[lr].get("course_definition_id", "")
                if run_def in idx_definitions:
                    ctype = idx_definitions[run_def].get("course_type", "")
                    if ctype and ctype not in ("project", "praxis"):
                        fail("object_layer", f"FieldPractice {fp_id} 只能关联 Project/Praxis CourseRun：{lr} (type={ctype})")
                run_case = idx_runs[lr].get("case_id", "")
                if cid and run_case and run_case != cid:
                    fail("object_layer", f"FieldPractice {fp_id} 跨 Case 关联 CourseRun：FP.case_id={cid}, {lr}.case_id={run_case}")
        # evidence_index 路径安全性
        ev_idx = f.get("evidence_index", "").strip()
        if ev_idx:
            fp_instance_dir = (MAIN_DIR / f["_path"]).parent
            ev_valid = True
            if "\\" in ev_idx:
                fail("object_layer", f"FieldPractice evidence_index 必须是安全相对路径（不得含反斜杠）：{fp_id}")
                ev_valid = False
            if ev_valid and (ev_idx.startswith("/") or re.match(r"^[A-Za-z]:", ev_idx) or ev_idx.startswith("\\\\")):
                fail("object_layer", f"FieldPractice evidence_index 必须是安全相对路径（不得为绝对路径）：{fp_id}")
                ev_valid = False
            if ev_valid:
                parts = ev_idx.split("/")
                if "" in parts:
                    fail("object_layer", f"FieldPractice evidence_index 含空路径段：{fp_id} -> {ev_idx}")
                    ev_valid = False
                elif ".." in parts or "." in parts:
                    fail("object_layer", f"FieldPractice evidence_index 路径逃逸（含 . 或 .. 段）：{fp_id}")
                    ev_valid = False
            if ev_valid:
                fp_resolved = fp_instance_dir.resolve()
                target = (fp_instance_dir / ev_idx).resolve()
                try:
                    target.relative_to(fp_resolved)
                except ValueError:
                    fail("object_layer", f"FieldPractice evidence_index 路径逃逸实例目录：{fp_id} -> {ev_idx}")
                    ev_valid = False
            if ev_valid:
                if not target.is_file():
                    fail("object_layer", f"FieldPractice evidence_index 必须指向已存在的 Markdown 文件（文件不存在）：{fp_id} -> {ev_idx}")
                elif target.suffix.lower() != ".md":
                    fail("object_layer", f"FieldPractice evidence_index 必须指向已存在的 Markdown 文件（非 .md）：{fp_id} -> {ev_idx}")

    active_g_runs = set()
    for gid, f in idx_groups.items():
        g_case = f.get("case_id", "")
        if g_case and g_case not in case_ids:
            fail("object_layer", f"G {gid} 引用的 Case 不存在：{g_case}")
        runs = _parse_inline_list(f.get("course_runs", "[]"), MAIN_DIR / f["_path"], "course_runs")
        for r in runs:
            if r not in idx_runs:
                fail("object_layer", f"G {gid} 引用的 CourseRun 不存在：{r}")
            else:
                run_case = idx_runs[r].get("case_id", "")
                if g_case and run_case and run_case != g_case:
                    fail("object_layer", f"G {gid} 跨 Case 引用 CourseRun：G.case_id={g_case}, {r}.case_id={run_case}")
        fps = _parse_inline_list(f.get("field_practices", "[]"), MAIN_DIR / f["_path"], "field_practices")
        for fp in fps:
            if fp not in idx_practices:
                fail("object_layer", f"G {gid} 引用的 FieldPractice 不存在：{fp}")
            else:
                fp_case = idx_practices[fp].get("case_id", "")
                if g_case and fp_case and fp_case != g_case:
                    fail("object_layer", f"G {gid} 跨 Case 引用 FieldPractice：G.case_id={g_case}, {fp}.case_id={fp_case}")
        if f.get("status") == "active":
            active_g_runs.update(runs)

    active_r_runs = set()
    for rid, f in idx_bindings.items():
        r_case = f.get("case_id", "")
        if r_case and r_case not in case_ids:
            fail("object_layer", f"R {rid} 引用的 Case 不存在：{r_case}")
        run_ref = f.get("course_run_id", "")
        if run_ref and run_ref not in idx_runs:
            fail("object_layer", f"R {rid} 绑定的 CourseRun 不存在：{run_ref}")
        if run_ref and run_ref in idx_runs:
            run_def = idx_runs[run_ref].get("course_definition_id", "")
            if run_def in idx_definitions:
                ctype = idx_definitions[run_def].get("course_type", "")
                if ctype and ctype not in ("project", "praxis"):
                    fail("object_layer", f"R {rid} 只能绑定 Project/Praxis CourseRun：{run_ref} (type={ctype})")
            run_case = idx_runs[run_ref].get("case_id", "")
            if r_case and run_case and run_case != r_case:
                fail("object_layer", f"R {rid} 跨 Case 绑定 CourseRun：R.case_id={r_case}, {run_ref}.case_id={run_case}")
        if f.get("binding_status") == "active" and run_ref:
            active_r_runs.add(run_ref)

    both = active_g_runs & active_r_runs
    if both:
        fail("object_layer", f"同一 CourseRun 同时 active G/R：{sorted(both)}")

    # 6. 新旧路径碰撞（按稳定 ID）
    old_codes = set()
    old_courses_dir = MAIN_DIR / "30_courses"
    if old_courses_dir.is_dir():
        for cs in old_courses_dir.glob("*/course_status.md"):
            fm = _fm_fields(cs)
            code = fm.get("course", "")
            if code:
                old_codes.add(code)
    new_def_ids = set(idx_definitions.keys()) - {""}
    def_id_collision = old_codes & new_def_ids
    if def_id_collision:
        fail("object_layer", f"旧课程 code 与新 CourseDefinition ID 碰撞：{sorted(def_id_collision)}")
    new_run_defs = {f.get("course_definition_id", "") for f in idx_runs.values()} - {""}
    run_collision = old_codes & new_run_defs
    if run_collision:
        fail("object_layer", f"旧课程 code 与新 CourseRun definition_id 碰撞：{sorted(run_collision)}")

    old_dir_names = set()
    if old_courses_dir.is_dir():
        old_dir_names = {p.name for p in old_courses_dir.iterdir() if p.is_dir() and not p.name.startswith("_")}
    new_def_names = set()
    new_defs_dir = MAIN_DIR / "30_course_definitions"
    if new_defs_dir.is_dir():
        new_def_names = {p.name for p in new_defs_dir.iterdir() if p.is_dir() and not p.name.startswith("_")}
    dir_collision = old_dir_names & new_def_names
    if dir_collision:
        fail("object_layer", f"同一课程目录新旧碰撞：{sorted(dir_collision)}")

    old_g_ids = set()
    old_groups_dir = MAIN_DIR / "20_groups"
    if old_groups_dir.is_dir():
        for p in old_groups_dir.glob("G*.md"):
            fm = _fm_fields(p)
            gid = fm.get("group", "") or p.stem
            old_g_ids.add(gid)
    new_g_ids = set(idx_groups.keys()) - {""}
    g_collision = old_g_ids & new_g_ids
    if g_collision:
        fail("object_layer", f"同一 G 新旧碰撞：{sorted(g_collision)}")


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    print(f"{BOLD}T2AG Doctor — 系统健康检查{RESET}")
    print(f"{BOLD}检查目录: {ROOT_DIR}{RESET}")
    print(f"{BOLD}{'═' * 60}{RESET}")

    # 运行所有检查
    check_core_files()
    check_version_consistency()
    check_distribution_hygiene()
    check_naming_conventions()
    check_memory_budget()
    check_constitution_budget()
    check_manifest_registration()
    check_course_group_rules()
    check_general_track()
    check_overlay_references()
    check_exam_isolation()
    check_skin_system()
    check_pattern_declarations()
    check_external_resources()
    check_book_management()
    check_reflection_indexes()
    check_course_drivers()
    check_mistake_bank_generation_template()
    check_mistake_bank_schema()
    check_execution_baseline_schema()
    check_core_playbook_distribution()
    check_curricula_semantics()
    check_domain_model_distribution()
    check_object_layer_migration()

    # 汇总
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    print(f"{BOLD}检查汇总{RESET}")
    print(f"{BOLD}{'═' * 60}{RESET}")
    print(f"  {GREEN}OK{RESET}:   {len(infos)}")
    print(f"  {YELLOW}WARN{RESET}: {len(warns)}")
    print(f"  {RED}FAIL{RESET}: {len(fails)}")

    if fails:
        print(f"\n{RED}{BOLD}FAIL 详情:{RESET}")
        for check_name, msg in fails:
            print(f"  [{check_name}] {msg}")

    if warns:
        print(f"\n{YELLOW}{BOLD}WARN 详情:{RESET}")
        for check_name, msg in warns:
            print(f"  [{check_name}] {msg}")

    print()

    # 退出码
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
