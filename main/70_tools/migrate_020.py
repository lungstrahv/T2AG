#!/usr/bin/env python3
"""T2AG 0.2.0 one-generation structural migration.

Default mode is read-only ``--check`` against Main.  ``--apply`` performs the
copy/verify/remove sequence and writes a machine report plus a review checklist.
Skeleton is opt-in; Lite is deliberately rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Iterable


EXCLUDED_DIRS = {
    ".git", ".venv", ".tools", ".recovery", ".staging", ".uploads",
    "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules",
}
TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".ps1", ".json", ".yaml", ".yml", ".html",
    ".css", ".js", ".ts", ".toml", ".ini", ".cfg", ".csv", ".tex", ".aux",
    ".log", ".cpp", ".h", ".hpp",
}
KNOWN_BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".docx", ".pptx",
    ".xlsx", ".zip", ".epub", ".exe", ".dll", ".ico",
}
RETIRED_DOMAINS = (
    "10_case", "12_activity_records", "15_curricula", "20_groups",
    "25_general", "30_courses", "30_course_definitions", "35_course_runs",
    "40_field_practices", "skin",
)
COURSES = {
    "CS1953": "CS1953_CppProgramming",
    "IV1001": "IV1001_Investing",
    "MATH1205H": "MATH1205H_LinearAlgebra",
    "MATH1607H": "MATH1607H_MathematicalAnalysis",
    "PY1001": "PY1001_PythonCocoon",
}


@dataclass(frozen=True)
class Operation:
    kind: str
    source: str
    target: str
    disposition: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        base = Path(current)
        for name in files:
            yield base / name


def relative(path: Path, repo: Path) -> str:
    return path.relative_to(repo).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-020")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def copy_verified(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(source) != sha256(target):
            raise RuntimeError(f"target collision: {target}")
        return
    shutil.copy2(source, target)
    if sha256(source) != sha256(target):
        raise RuntimeError(f"hash verification failed: {source} -> {target}")


def add_tree_ops(
    operations: list[Operation],
    repo: Path,
    source: Path,
    target: Path,
    disposition: str,
) -> None:
    if not source.exists():
        return
    for item in iter_files(source):
        dst = target / item.relative_to(source)
        operations.append(Operation(
            "copy", relative(item, repo), relative(dst, repo), disposition
        ))


def add_file_op(
    operations: list[Operation],
    repo: Path,
    source: Path,
    target: Path,
    disposition: str,
) -> None:
    if source.is_file():
        operations.append(Operation(
            "copy", relative(source, repo), relative(target, repo), disposition
        ))


def build_plan(repo: Path, target_kind: str) -> list[Operation]:
    main = repo / "main"
    ops: list[Operation] = []

    add_file_op(
        ops, repo, main / "00_core/course_group_rules.md",
        main / "50_playbook/course_group_rules.md", "move protocol out of Core",
    )
    add_file_op(
        ops, repo, main / "00_core/t2ag_flow.md",
        main / "50_playbook/t2ag_flow.md", "move derived flow view",
    )

    student_id = "S002" if target_kind == "main" else "S001"
    student = main / "10_case/students" / student_id
    if student.exists():
        ops.append(Operation(
            "merge_profile",
            f"main/10_case/students/{student_id}/basic_info.md||"
            f"main/10_case/students/{student_id}/personality_baseline.md",
            "main/10_student/profile.md",
            "merge profile and observable baseline",
        ))
        add_file_op(
            ops, repo, student / "reasoning_patterns.md",
            main / "10_student/reasoning_patterns.md", "move student reasoning",
        )
        add_file_op(
            ops, repo, student / "course_reflections.md",
            main / "10_student/course_reflections.md", "move reflections",
        )
    add_file_op(
        ops, repo, main / "10_case/course_info.md",
        main / "10_student/learning_path.md", "move generated learning path",
    )
    add_tree_ops(
        ops, repo, main / "10_case/teachers", main / "20_teacher",
        "move reusable teacher templates",
    )
    add_file_op(
        ops, repo, main / "10_case/teacher_overlay.md",
        main / "20_teacher/overlay.md", "move active teacher overlay",
    )

    if target_kind == "main":
        activity_root = main / "12_activity_records/S002"
        add_file_op(
            ops, repo, activity_root / "AR-S002-0001_InvestingNotes.md",
            main / "10_student/activities/AR-0001_InvestingNotes.md",
            "rewrite stable activity ID",
        )
        engagement_root = main / "40_field_practices/S002"
        add_tree_ops(
            ops, repo, engagement_root / "FP-S002-0001_TradingDiscipline",
            main / "10_student/engagements/EG-0001_TradingDiscipline",
            "rewrite FieldPractice as Engagement EG-0001",
        )
        ops[-3:] = [
            Operation(
                op.kind, op.source,
                op.target.replace("/field_practice.md", "/engagement.md"),
                op.disposition,
            )
            for op in ops[-3:]
        ]
        add_tree_ops(
            ops, repo, engagement_root / "FP-S002-0002_CocoonProduct",
            main / "10_student/engagements/EG-0002_CocoonProduct",
            "rewrite FieldPractice as Engagement EG-0002",
        )
        ops[-2:] = [
            Operation(
                op.kind, op.source,
                op.target.replace("/field_practice.md", "/engagement.md"),
                op.disposition,
            )
            for op in ops[-2:]
        ]

        add_tree_ops(
            ops, repo, main / "15_curricula/baseline",
            main / "30_group/curricula", "move baseline curriculum",
        )
        add_tree_ops(
            ops, repo, main / "15_curricula/references",
            main / "30_group/curricula", "move reference curriculum",
        )
        for gid in ("G01", "G02"):
            add_file_op(
                ops, repo, main / f"20_groups/{gid}.md",
                main / f"30_group/{gid}/plan.md", "move group plan",
            )
            add_file_op(
                ops, repo, main / f"20_groups/preplans/{gid}/calendar.md",
                main / f"30_group/{gid}/calendar.md", "move group calendar",
            )
            add_file_op(
                ops, repo, main / f"20_groups/preplans/{gid}/review.md",
                main / f"30_group/{gid}/review.md", "move group review",
            )
        add_tree_ops(
            ops, repo, main / "20_groups/bindings",
            main / "30_group/G01/bindings", "move group bindings",
        )
        for name in ("overlay_atlas.md", "overlay_cycle.md", "overlay_daily.md", "overlay_march.md"):
            add_file_op(
                ops, repo, main / "20_groups/overlays" / name,
                main / "60_journal/retired_020_sources/overlays" / name,
                "archive dissolved composite overlay",
            )

        for course_id, folder in COURSES.items():
            definition = main / "30_course_definitions" / folder
            run = main / "35_course_runs/S002" / f"CR-S002-{course_id}"
            course = main / "40_course" / course_id
            add_file_op(
                ops, repo, definition / "course_definition.md",
                course / "course.md", "merge reusable course definition",
            )
            book = definition / f"{course_id}_book"
            add_tree_ops(ops, repo, book, course / "book", "move course book")
            if (run / "course_status.md").exists():
                sources = [f"main/35_course_runs/S002/CR-S002-{course_id}/course_status.md"]
                if (run / "progress_nodes.md").exists():
                    sources.append(f"main/35_course_runs/S002/CR-S002-{course_id}/progress_nodes.md")
                ops.append(Operation(
                    "merge_progress", "||".join(sources),
                    f"main/40_course/{course_id}/progress.md",
                    "merge CourseRun status and progress nodes",
                ))
            add_tree_ops(
                ops, repo, run / "lesson01", course / "lessons/lesson01",
                "move lesson tree",
            )
            for filename in ("mistake_bank.md", "question_bank.md"):
                add_file_op(
                    ops, repo, run / filename, course / filename,
                    "move course-owned learning state",
                )
            if course_id == "CS1953":
                add_file_op(
                    ops, repo, run / "notes.md", course / "lessons/README.md",
                    "move course lesson notes index",
                )
            if course_id == "IV1001":
                add_file_op(
                    ops, repo, run / "IV1001_plan_archive.md",
                    main / "60_journal/IV1001_plan_archive.md",
                    "archive absorbed IV1001 plan",
                )
            if course_id == "PY1001":
                add_file_op(
                    ops, repo, run / "cocoon_plan.md",
                    main / "60_journal/PY1001_cocoon_plan_archive.md",
                    "archive absorbed Cocoon plan",
                )

        add_tree_ops(
            ops, repo, main / "30_course_definitions/_shared",
            main / "40_course/_shared", "move shared course resources",
        )
        for course_id, filename, binding_id in (
            ("DS1001r", "DS1001r_Kaggle.md", "R001"),
            ("PHIL1101r", "PHIL1101r_ZhouYi.md", "R002"),
        ):
            source = main / "25_general" / filename
            if source.exists():
                ops.extend([
                    Operation(
                        "split_general_course", relative(source, repo),
                        f"main/40_course/{course_id}/course.md",
                        "split frozen R content into Course",
                    ),
                    Operation(
                        "split_general_progress", relative(source, repo),
                        f"main/40_course/{course_id}/progress.md",
                        "split frozen R state into progress",
                    ),
                    Operation(
                        "generate_binding", relative(source, repo),
                        f"main/30_group/G01/bindings/{binding_id}_{course_id}.md",
                        "represent flexible execution only in binding",
                    ),
                    Operation(
                        "generate_general_support", relative(source, repo),
                        f"main/40_course/{course_id}/lessons/_README.md",
                        "persist empty lesson domain",
                    ),
                    Operation(
                        "generate_general_support", relative(source, repo),
                        f"main/40_course/{course_id}/exercises/_README.md",
                        "persist empty exercise domain",
                    ),
                    Operation(
                        "generate_general_support", relative(source, repo),
                        f"main/40_course/{course_id}/book/_README.md",
                        "persist empty book domain",
                    ),
                    Operation(
                        "generate_general_support", relative(source, repo),
                        f"main/40_course/{course_id}/mistake_bank.md",
                        "split mistake ledger from progress",
                    ),
                    Operation(
                        "generate_general_support", relative(source, repo),
                        f"main/40_course/{course_id}/question_bank.md",
                        "create question bank V2",
                    ),
                ])

    add_tree_ops(
        ops, repo, main / "skin", main / "80_interface",
        "move interface templates from main/skin",
    )
    add_file_op(
        ops, repo, repo / "assets/fable_snail.png",
        main / "80_interface/fable_snail.png", "move interface asset",
    )

    # Every old live source not otherwise mapped is preserved verbatim under
    # a historical audit tree before its active path is retired.
    covered: set[str] = set()
    for op in ops:
        for source in op.source.split("||"):
            if source.startswith("main/") or source.startswith("assets/"):
                covered.add(source)
    for domain in RETIRED_DOMAINS:
        root = main / domain
        for source in iter_files(root):
            rel = relative(source, repo)
            if rel in covered:
                continue
            ops.append(Operation(
                "copy", rel,
                f"main/60_journal/retired_020_sources/{rel}",
                "archive unmapped old-domain source for audit",
            ))
    asset = repo / "assets/fable_snail.png"
    if asset.is_file() and "assets/fable_snail.png" not in covered:
        ops.append(Operation(
            "copy", "assets/fable_snail.png",
            "main/60_journal/retired_020_sources/assets/fable_snail.png",
            "archive unmapped root asset",
        ))
    return deduplicate_ops(ops)


def deduplicate_ops(ops: list[Operation]) -> list[Operation]:
    result: list[Operation] = []
    seen: set[tuple[str, str, str]] = set()
    for op in ops:
        key = (op.kind, op.source, op.target)
        if key not in seen:
            seen.add(key)
            result.append(op)
    return result


def source_paths(op: Operation, repo: Path) -> list[Path]:
    return [repo / item for item in op.source.split("||")]


def collision_for(op: Operation, repo: Path) -> str | None:
    target = repo / op.target
    sources = source_paths(op, repo)
    if not target.exists():
        return None
    if op.kind == "copy" and sources[0].is_file():
        return None if sha256(sources[0]) == sha256(target) else op.target
    # Generated artifacts can be verified only by materialising their content.
    return op.target if any(source.exists() for source in sources) else None


def split_general(content: str, want_progress: bool) -> str:
    chunks = re.split(r"(?=^##\s+)", content, flags=re.MULTILINE)
    if not chunks:
        return content
    head, sections = chunks[0], chunks[1:]
    progress_titles = ("进度记录", "验收记录", "自测记录")
    selected: list[str] = []
    for section in sections:
        title = section.splitlines()[0]
        if "mistake_bank" in title:
            continue
        is_progress = any(token in title for token in progress_titles)
        if is_progress == want_progress:
            selected.append(section)
    if want_progress:
        return "\n".join(selected).strip() + "\n"
    return (head + "\n" + "\n".join(selected)).strip() + "\n"


def normalize_general_course(course_id: str, body: str) -> str:
    body = re.sub(r"^>\s*\*\*状态\*\*[：:].*\n", "", body, flags=re.MULTILINE)
    if course_id == "DS1001r":
        body = body.replace("> **子型**：project", "> **课程类型**：project")
        body = body.replace("本 R 不得启动", "本课程不得启动")
        body = re.sub(r"^-\s*\*\*R 类别\*\*：.*\n", "", body, flags=re.MULTILINE)
        body = body.replace("## 时间预算与组内关系", "## 课程关系")
        body = re.sub(r"^-\s*不占 G 的 4h 预算.*\n", "", body, flags=re.MULTILINE)
        lines = body.splitlines()
        in_milestones = False
        rewritten: list[str] = []
        for line in lines:
            if line == "## 里程碑表":
                in_milestones = True
            elif in_milestones and line.startswith("## "):
                in_milestones = False
            if in_milestones and line.startswith("|") and line.endswith("|"):
                cells = line.split("|")
                if (
                    len(cells) >= 7
                    and (
                        line.startswith("| M |")
                        or line.startswith("|---|---|---|---|---|")
                        or re.match(r"^\|\s*M\d+\s*\|", line)
                    )
                ):
                    del cells[-2]
                    line = "|".join(cells)
            rewritten.append(line)
        body = "\n".join(rewritten).strip() + "\n"
    elif course_id == "PHIL1101r":
        body = body.replace("> **子型**：reading", "> **课程类型**：mastery（教材驱动的知识课程）")
        body = body.replace(
            "> 自定循环，不绑 `overlay_cycle.md` 的 3-1-3 模板。通识课用自己的节奏。",
            "> 自定循环，不绑定学生 profile 或 group calendar 的固定节奏；课程使用自己的节奏。",
        )
        body = body.replace(
            "> D4 闲读说明：R 的 D4 阅读是\"想读就读\"，不是\"今天该读第三卦了\"。不设每日进度 KPI。",
            "> 弹性阅读说明：阅读不设每日进度 KPI；具体执行约束只由合法 binding 决定。",
        )
        body += (
            "\n## 自测三件套（稳定验收方法）\n\n"
            "1. **卦名卦序卦画默写**（纯客观，自测）。\n"
            "2. **随机抽爻辞白话训释**（对照译注评分）。\n"
            "3. **经传盲判**：给 10 段文字判“经 / 传 / 宋注 / 现代通俗”。\n\n"
            "- **外部真相源**：权威译注；分歧题存疑并查第三家。\n"
            "- **独立性账**：训释时的查书次数。\n"
            "- **失败留痕**：写入 `mistake_bank.md`。\n"
        )
    return body


def normalize_general_progress(course_id: str, body: str) -> str:
    if course_id == "PHIL1101r":
        body = re.sub(
            r"## 自测记录.*\Z",
            "## 自测记录\n\n"
            "> 稳定的自测方法定义在 `course.md`；这里只记录实际结果。\n\n"
            "（尚未自测）\n",
            body,
            flags=re.DOTALL,
        )
    if course_id == "DS1001r":
        body = (
            body.rstrip()
            + "\n\n## 里程碑状态\n\n"
            "| M | 当前状态 |\n|---|---|\n"
            "| M0 | planned |\n| M1 | planned |\n"
            "| M2 | planned |\n| M3 | planned |\n"
        )
    return body.strip() + "\n"


def general_support_content(course_id: str, target: Path) -> str:
    if target.name == "_README.md":
        domain = target.parent.name
        labels = {
            "lessons": "lesson 域",
            "exercises": "习题册",
            "book": "教材与资料",
        }
        rules = {
            "lessons": "课程开始时再创建 `lesson01/lesson01.md`；planned 阶段不伪造课堂记录。",
            "exercises": "按课程单元创建稳定 `Uxxxx/`；没有真实任务时不预建题号、作答或复盘证据。",
            "book": "课程启动后按 `main/50_playbook/book_management.md` 登记真实资料；当前不下载或伪造教材。",
        }
        return f"# {course_id} {labels[domain]}\n\n{rules[domain]}\n"
    if target.name == "mistake_bank.md":
        tags = (
            "数据泄漏 / 验证集污染 / 过拟合公榜 / 评估指标误解 / "
            "特征-目标混淆 / 分布偏移 / 随机性误读"
            if course_id == "DS1001r"
            else "训诂错 / 经传混读 / 卦爻错位 / 投射当原义 / 术数混入"
        )
        return (
            "> 【模式】复利回路·衰减（00_core/pattern_retire_loop.md）实例\n"
            f"> 【参数】域=知识点（{course_id}）｜时机=事后归因｜归因层=概念层"
            "｜消费方=复测与课程调整｜退出=maintenance/aged｜再入=陈年卷答错→回强化\n\n"
            f"# {course_id} 知识点错题库\n\n> 根因标签：{tags}。\n\n"
            "next_id: 1\n\n## 活跃知识点\n\n（暂无）\n\n"
            "## 维护知识点\n\n（暂无）\n\n## 陈年知识点\n\n（暂无）\n"
        )
    return (
        "<!-- QUESTION_BANK_TEMPLATE_V2 -->\n"
        "> 【模式】复利回路·部件（00_core/pattern_retire_loop.md）｜角色=流量台账\n"
        "> 【服务】所属回路=question_bank 集合层→教师画像｜结算=answered/closed"
        "｜再入=学生复问→转“需要回看”\n\n"
        f"# {course_id} 课程疑问库\n\n"
        "> 状态只使用 `open / answered / closed`；lesson 保存完整问答，本文件只保存索引与状态。\n\n"
        "next_id: 1\n\n## 待解决\n\n暂无。\n\n## 需要回看\n\n暂无。\n\n"
        "## 已解答\n\n暂无。\n"
    )


def materialize(op: Operation, repo: Path, target_kind: str) -> None:
    target = repo / op.target
    sources = source_paths(op, repo)
    if op.kind == "copy":
        copy_verified(sources[0], target)
        return
    if op.kind == "merge_profile":
        parts = [read_text(path).strip() for path in sources if path.exists()]
        label = "\n\n---\n\n## 可观察的个体基线（迁入）\n\n"
        content = parts[0] + (label + parts[1] if len(parts) > 1 else "") + "\n"
        if target_kind == "skeleton":
            content = content.replace("S001", "<student>")
        atomic_write(target, normalize_text(content))
        return
    if op.kind == "merge_progress":
        content = read_text(sources[0]).rstrip() + "\n"
        if len(sources) > 1 and sources[1].exists():
            content += (
                "\n---\n\n## 进度节点（0.2.0 合并）\n\n"
                + read_text(sources[1]).strip() + "\n"
            )
        course_id = re.search(r"CR-S002-([A-Za-z0-9]+)", op.source)
        content = normalize_progress(content, course_id.group(1) if course_id else "")
        atomic_write(target, normalize_text(content))
        return
    if op.kind in {"split_general_course", "split_general_progress"}:
        course_id = Path(op.target).parent.name
        body = split_general(
            read_text(sources[0]),
            want_progress=(op.kind == "split_general_progress"),
        )
        if op.kind == "split_general_course":
            schemas = {
                "DS1001r": (
                    'school_course_code: —\nname: "Kaggle 数据科学入门"\n'
                    "course_type: project\ndefault_driver: project\n"
                    "prerequisites: [PY1001]\nstatus: active\n"
                ),
                "PHIL1101r": (
                    'school_course_code: —\nname: "周易——历史·思想·流派·学法"\n'
                    "course_type: mastery\ndefault_driver: textbook\n"
                    "prerequisites: []\nstatus: active\n"
                ),
            }
            header = (
                "---\ntype: course\n"
                f"course_id: {course_id}\n"
                f"{schemas[course_id]}"
                "---\n"
            )
            content = header + normalize_general_course(course_id, body)
        else:
            drivers = {"DS1001r": "project", "PHIL1101r": "textbook"}
            actions = {
                "DS1001r": (
                    "用户确认激活 R001 且 PY1001 达到 M2 后，再创建 lesson01 "
                    "并登记首个 Kaggle 验证参数。"
                ),
                "PHIL1101r": (
                    "永久冻结 R002；若用户明确启动本 mastery 课程，只能先确认 "
                    "group 容量并加入 G，再创建 lesson01。"
                ),
            }
            header = (
                "---\ntype: course_progress\n"
                f"course_id: {course_id}\n"
                "lifecycle_status: planned\n"
                f"course_driver: {drivers[course_id]}\n"
                "truth_source: true\ncurrent_lesson: none\n"
                "progress_nodes_status: lazy_on_activation\n"
                f"updated: {date.today().isoformat()}\n"
                f"next_action: {actions[course_id]}\n"
                "---\n"
                f"# {course_id} 进度\n\n"
            )
            content = header + normalize_general_progress(
                course_id, body or "（尚未开始）\n"
            )
        atomic_write(target, normalize_text(content))
        return
    if op.kind == "generate_binding":
        match = re.match(r"([A-Z]\d+)_([A-Za-z0-9]+)\.md", Path(op.target).name)
        binding_id, course_id = match.groups() if match else ("R000", "UNKNOWN")
        frozen = "legacy_frozen: true\n" if binding_id == "R002" else ""
        content = (
            "---\n"
            "type: binding\n"
            f"binding_id: {binding_id}\n"
            f"course_id: {course_id}\n"
            "group_id: G01\n"
            "binding_status: idle\n"
            "execution_mode: flexible\n"
            f"{frozen}"
            "---\n"
            f"# {binding_id} · {course_id}\n\n"
            "> 本文件只表达弹性执行绑定；课程内容与进度分别归该课程的 "
            "`course.md` 与 `progress.md`。\n"
        )
        atomic_write(target, content)
        return
    if op.kind == "generate_general_support":
        atomic_write(target, general_support_content(Path(op.target).parts[2], target))
        return
    raise RuntimeError(f"unknown operation kind: {op.kind}")


def normalize_progress(content: str, course_id: str) -> str:
    content = re.sub(r"^type:\s*course_run\s*$", "type: course_progress", content, flags=re.MULTILINE)
    content = re.sub(r"^course_run_id:.*\n", "", content, flags=re.MULTILINE)
    content = re.sub(r"^case_id:.*\n", "", content, flags=re.MULTILINE)
    content = re.sub(r"^course_definition_id:.*\n", "", content, flags=re.MULTILINE)
    content = re.sub(r"^course:\s*.*$", f"course_id: {course_id}", content, flags=re.MULTILINE)
    content = re.sub(r"^progress_nodes:\s*.*\n", "", content, flags=re.MULTILINE)
    content = content.replace(f"CR-S002-{course_id}", course_id)
    return content


PATH_REWRITES = {
    "main/10_case/students/S002/basic_info.md": "main/10_student/profile.md",
    "main/10_case/students/S002/personality_baseline.md": "main/10_student/profile.md",
    "main/10_case/students/S002/reasoning_patterns.md": "main/10_student/reasoning_patterns.md",
    "main/10_case/students/S002/course_reflections.md": "main/10_student/course_reflections.md",
    "main/10_case/teacher_overlay.md": "main/20_teacher/overlay.md",
    "main/10_case/teachers/": "main/20_teacher/",
    "main/10_case/course_info.md": "main/10_student/learning_path.md",
    "main/12_activity_records/S002/AR-S002-0001_InvestingNotes.md": "main/10_student/activities/AR-0001_InvestingNotes.md",
    "main/20_groups/G01.md": "main/30_group/G01/plan.md",
    "main/20_groups/G02.md": "main/30_group/G02/plan.md",
    "main/20_groups/preplans/G01/calendar.md": "main/30_group/G01/calendar.md",
    "main/20_groups/preplans/G01/review.md": "main/30_group/G01/review.md",
    "main/20_groups/preplans/G02/calendar.md": "main/30_group/G02/calendar.md",
    "main/20_groups/preplans/G02/review.md": "main/30_group/G02/review.md",
    "main/15_curricula/baseline/": "main/30_group/curricula/",
    "main/15_curricula/references/": "main/30_group/curricula/",
    "main/30_course_definitions/_shared/": "main/40_course/_shared/",
    "main/40_field_practices/S002/FP-S002-0001_TradingDiscipline/": "main/10_student/engagements/EG-0001_TradingDiscipline/",
    "main/40_field_practices/S002/FP-S002-0002_CocoonProduct/": "main/10_student/engagements/EG-0002_CocoonProduct/",
    "10_case/teachers/": "20_teacher/",
    "10_case/teacher_overlay.md": "20_teacher/overlay.md",
    "10_case/students/S002/": "10_student/",
    "10_case/course_info.md": "10_student/learning_path.md",
    "10_case/student_info.md": "10_student/profile.md",
    "students/S002/reasoning_patterns.md": "10_student/reasoning_patterns.md",
    "12_activity_records/S002/AR-0001_InvestingNotes.md": "10_student/activities/AR-0001_InvestingNotes.md",
    "40_field_practices/S002/EG-0001_TradingDiscipline/": "10_student/engagements/EG-0001_TradingDiscipline/",
    "40_field_practices/S002/EG-0002_CocoonProduct/": "10_student/engagements/EG-0002_CocoonProduct/",
    "main/skin/": "main/80_interface/",
    "assets/fable_snail.png": "main/80_interface/fable_snail.png",
}
for _course_id, _folder in COURSES.items():
    PATH_REWRITES[f"main/30_course_definitions/{_folder}/course_definition.md"] = (
        f"main/40_course/{_course_id}/course.md"
    )
    PATH_REWRITES[f"main/30_course_definitions/{_folder}/{_course_id}_book/"] = (
        f"main/40_course/{_course_id}/book/"
    )
    PATH_REWRITES[f"main/35_course_runs/S002/CR-S002-{_course_id}/lesson"] = (
        f"main/40_course/{_course_id}/lessons/lesson"
    )
    PATH_REWRITES[f"main/35_course_runs/S002/CR-S002-{_course_id}/course_status.md"] = (
        f"main/40_course/{_course_id}/progress.md"
    )
    PATH_REWRITES[f"main/35_course_runs/S002/CR-S002-{_course_id}/mistake_bank.md"] = (
        f"main/40_course/{_course_id}/mistake_bank.md"
    )
    PATH_REWRITES[f"main/35_course_runs/S002/CR-S002-{_course_id}/question_bank.md"] = (
        f"main/40_course/{_course_id}/question_bank.md"
    )


def normalize_text(content: str) -> str:
    for old, new in sorted(PATH_REWRITES.items(), key=lambda item: -len(item[0])):
        content = content.replace(old, new)
    content = content.replace("AR-S002-0001", "AR-0001")
    content = content.replace("FP-S002-0001", "EG-0001")
    content = content.replace("FP-S002-0002", "EG-0002")
    content = re.sub(r"CR-S002-([A-Za-z0-9]+)", r"\1", content)
    content = re.sub(r"^case_id:\s*S002\s*\n", "", content, flags=re.MULTILINE)
    content = content.replace("type: course_definition", "type: course")
    content = content.replace("course_definition_id:", "course_id:")
    content = content.replace("type: capacity_group", "type: group")
    content = re.sub(r"^group:\s*(G\d+)\s*$", r"group_id: \1", content, flags=re.MULTILINE)
    content = content.replace("type: field_practice", "type: engagement")
    content = content.replace("field_practice_id:", "engagement_id:")
    content = content.replace("field_practice.md", "engagement.md")
    content = content.replace("practice_status:", "status:")
    content = content.replace("linked_course_runs:", "linked_courses:")
    content = content.replace("course_status.md", "progress.md")
    content = content.replace("CourseDefinition", "Course")
    content = content.replace("CourseRun", "课程进度")
    for course_id, folder in COURSES.items():
        content = content.replace(
            f"30_course_definitions/{folder}/", f"40_course/{course_id}/"
        )
        content = content.replace(
            f"35_course_runs/S002/{course_id}/", f"40_course/{course_id}/"
        )
        content = content.replace(
            f"35_course_runs/S002/CR-S002-{course_id}/", f"40_course/{course_id}/"
        )
    return content


def rewrite_active_text(repo: Path) -> list[str]:
    main = repo / "main"
    changed: list[str] = []
    roots = [
        main / "00_core", main / "10_student", main / "20_teacher",
        main / "30_group", main / "40_course", main / "50_playbook",
        main / "70_tools", main / "80_interface", main / "t2ag.md",
        repo / "README.md", repo / "AGENTS.md", repo / "cloud",
    ]
    for root in roots:
        paths = [root] if root.is_file() else list(iter_files(root)) if root.exists() else []
        for path in paths:
            if any(
                protected in path.parents
                for protected in (repo / "cloud/inbox", repo / "cloud/outbox")
            ):
                continue
            if path.name in {
                "migrate_020.py",
                "t2ag_doctor.py",
                "artifact_registry.json",
                "legacy_r_registry.json",
                "t2ag_changelog.md",
                "t2ag_problemlog.md",
            }:
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                content = read_text(path)
            except UnicodeDecodeError:
                continue
            updated = normalize_text(content)
            if updated != content:
                atomic_write(path, updated)
                changed.append(relative(path, repo))
    return changed


def update_registry(repo: Path) -> None:
    path = repo / "main/70_tools/artifact_registry.json"
    if not path.exists():
        return
    data = json.loads(read_text(path))
    artifacts = data.setdefault("artifacts", [])
    by_id = {item.get("artifact_id"): item for item in artifacts}

    canonical_updates = {
        "MATH1607H_LESSON01_SOURCE": "main/40_course/MATH1607H/book/primary/verified_excerpts/math1607h_b001_c01_s01.md",
        "SYSU_LOGIC_CURRICULUM": "main/30_group/curricula/CUR-SYSU-LOGIC.md",
        "DIR_ACTIVITY_RECORDS": "main/10_student/activities/",
        "DIR_EXECUTION": "main/30_group/",
        "DIR_COURSE_DEFINITIONS": "main/40_course/",
        "DIR_COURSE_RUNS": "main/40_course/",
        "DIR_FIELD_PRACTICES": "main/10_student/engagements/",
        "MATH1205H_COURSE_RUN": "main/40_course/MATH1205H/progress.md",
        "MATH1205H_COURSE_DEFINITION": "main/40_course/MATH1205H/course.md",
        "IV1001_COURSE_RUN": "main/40_course/IV1001/progress.md",
        "PY1001_COURSE_RUN": "main/40_course/PY1001/progress.md",
        "CS1953_COURSE_RUN": "main/40_course/CS1953/progress.md",
        "MATH1607H_COURSE_RUN": "main/40_course/MATH1607H/progress.md",
        "EXTERNAL_RESOURCES_INDEX": "main/40_course/_shared/external_resources.md",
        "AR_S002_0001_INVESTING_NOTES": "main/10_student/activities/AR-0001_InvestingNotes.md",
        "FP_S002_0001_FIELD_PRACTICE": "main/10_student/engagements/EG-0001_TradingDiscipline/engagement.md",
        "FP_S002_0001_TRADE_JOURNAL": "main/10_student/engagements/EG-0001_TradingDiscipline/trade_journal.md",
        "FP_S002_0002_FIELD_PRACTICE": "main/10_student/engagements/EG-0002_CocoonProduct/engagement.md",
        "IV1001_PLAN_ARCHIVE": "main/60_journal/IV1001_plan_archive.md",
    }
    for artifact_id, canonical in canonical_updates.items():
        item = by_id.get(artifact_id)
        if not item:
            continue
        old = item.get("canonical_path")
        redirects = item.setdefault("redirects", [])
        if old and old != canonical and old not in redirects:
            redirects.append(old)
        item["canonical_path"] = canonical
        item["migration_reason"] = "0.2.0 structural migration"
    if "MATH1607H_LESSON01_SOURCE" in by_id:
        by_id["MATH1607H_LESSON01_SOURCE"]["migration_reason"] = (
            "0.2.0 promoted from disposable Lesson cache to persistent "
            "ContentGroup source"
        )
    if "IV1001_PLAN_ARCHIVE" in by_id:
        by_id["IV1001_PLAN_ARCHIVE"]["status"] = "archived"

    overlay_successors = {
        "G01_DAILY_OVERLAY": [
            "main/30_group/G01/calendar.md", "main/20_teacher/overlay.md",
        ],
        "G01_MARCH_OVERLAY": [
            "main/30_group/G01/calendar.md", "main/40_course/MATH1607H/course.md",
            "main/40_course/PY1001/course.md",
        ],
        "G01_ATLAS_OVERLAY": [
            "main/40_course/MATH1607H/course.md", "main/30_group/G01/plan.md",
            "main/30_group/G02/plan.md",
        ],
    }
    if repo.name == "t2ag-skeleton":
        generic_overlay_successors = [
            "main/10_student/profile.md",
            "main/20_teacher/overlay.md",
            "main/30_group/",
        ]
        overlay_successors = {
            artifact_id: generic_overlay_successors
            for artifact_id in overlay_successors
        }
    for artifact_id, successors in overlay_successors.items():
        item = by_id.get(artifact_id)
        if item:
            item["status"] = "tombstone"
            item["successors"] = successors
            item["migration_reason"] = "0.2.0 composite overlay dissolved by owner"

    progress_alias = {
        "MATH1607H_PROGRESS_NODES": "MATH1607H_COURSE_RUN",
        "PY1001_PROGRESS_NODES": "PY1001_COURSE_RUN",
        "DIR_COURSE_RUNS": "DIR_COURSE_DEFINITIONS",
    }
    for artifact_id, survivor in progress_alias.items():
        item = by_id.get(artifact_id)
        if item:
            item["status"] = "tombstone"
            item["alias_to"] = survivor
            item["successors"] = [by_id[survivor]["canonical_path"]]
            item["migration_reason"] = "0.2.0 progress nodes merged into survivor"

    tombstone_canonicals = {
        "MATH1607H_PROGRESS_NODES":
            "main/35_course_runs/S002/CR-S002-MATH1607H/progress_nodes.md",
        "PY1001_PROGRESS_NODES":
            "main/35_course_runs/S002/CR-S002-PY1001/progress_nodes.md",
        "DIR_COURSE_RUNS": "main/35_course_runs/",
    }
    for artifact_id, canonical in tombstone_canonicals.items():
        if artifact_id in by_id:
            by_id[artifact_id]["canonical_path"] = canonical

    historical_paths = {
        "MATH1607H_LESSON01_SOURCE": [
            "main/40_course/MATH1607H/lessons/lesson01/working_pages/source_excerpt.md",
            "main/35_course_runs/S002/CR-S002-MATH1607H/lesson01/working_pages/source_excerpt.md",
            "main/35_course_runs/S002/CR-S002-MATH1607H/lesson01/temppage/temp_page.md",
            "main/35_course_runs/S002/CR-S002-MATH1607H/lesson01/working_pages/temp_page.md",
        ],
        "SYSU_LOGIC_CURRICULUM": [
            "main/15_curricula/references/CUR-SYSU-LOGIC.md",
            "main/25_general/LOGIC1001r_SYSULogicCurriculum.md",
            "main/15_curricula/references/CUR-SYSU-LOGIC-2026.md",
        ],
        "DIR_ACTIVITY_RECORDS": ["main/12_activity_records/"],
        "DIR_EXECUTION": ["main/20_groups/", "main/20_execution/"],
        "DIR_COURSE_DEFINITIONS": ["main/30_course_definitions/"],
        "DIR_FIELD_PRACTICES": ["main/40_field_practices/"],
        "MATH1205H_COURSE_RUN": [
            "main/35_course_runs/S002/CR-S002-MATH1205H/course_status.md",
            "main/30_courses/MATH1205H_LinearAlgebra/course_status.md",
            "main/30_courses/MATH1205H_LinearAlgebra/",
        ],
        "MATH1205H_COURSE_DEFINITION": [
            "main/30_course_definitions/MATH1205H_LinearAlgebra/course_definition.md",
        ],
        "IV1001_COURSE_RUN": [
            "main/35_course_runs/S002/CR-S002-IV1001/course_status.md",
            "main/30_courses/IV1001_Investing/course_status.md",
            "main/30_courses/IV1001_Investing/",
        ],
        "PY1001_COURSE_RUN": [
            "main/35_course_runs/S002/CR-S002-PY1001/course_status.md",
            "main/30_courses/PY1001_PythonCocoon/course_status.md",
            "main/30_courses/PY1001_PythonCocoon/",
        ],
        "CS1953_COURSE_RUN": [
            "main/35_course_runs/S002/CR-S002-CS1953/course_status.md",
            "main/30_courses/CS1953_CppProgramming/course_status.md",
            "main/30_courses/CS1953_CppProgramming/",
        ],
        "MATH1607H_COURSE_RUN": [
            "main/35_course_runs/S002/CR-S002-MATH1607H/course_status.md",
            "main/30_courses/MATH1607H_MathematicalAnalysis/course_status.md",
            "main/30_courses/MATH1607H_MathematicalAnalysis/",
        ],
        "EXTERNAL_RESOURCES_INDEX": [
            "main/30_course_definitions/_shared/external_resources.md",
            "main/30_courses/_shared/external_resources.md",
        ],
        "AR_S002_0001_INVESTING_NOTES": [
            "main/12_activity_records/S002/AR-S002-0001_InvestingNotes.md",
            "main/40_practices/trading/notes.md",
        ],
        "FP_S002_0001_FIELD_PRACTICE": [
            "main/40_field_practices/S002/FP-S002-0001_TradingDiscipline/field_practice.md",
            "main/40_practices/P002_TradingDiscipline.md",
        ],
        "FP_S002_0001_TRADE_JOURNAL": [
            "main/40_field_practices/S002/FP-S002-0001_TradingDiscipline/trade_journal.md",
            "main/40_practices/trading/trade_journal.md",
        ],
        "FP_S002_0002_FIELD_PRACTICE": [
            "main/40_field_practices/S002/FP-S002-0002_CocoonProduct/field_practice.md",
            "main/40_practices/P001_CocoonProduct.md",
        ],
        "IV1001_PLAN_ARCHIVE": [
            "main/35_course_runs/S002/CR-S002-IV1001/IV1001_plan_archive.md",
            "main/40_practices/trading/IV1001_plan.md",
        ],
    }
    for artifact_id, paths in historical_paths.items():
        item = by_id.get(artifact_id)
        if not item:
            continue
        canonical = item.get("canonical_path")
        redirects = [
            path for path in dict.fromkeys([*item.get("redirects", []), *paths])
            if path != canonical
        ]
        item["redirects"] = redirects

    if "G01_CYCLE_OVERLAY" not in by_id:
        artifacts.append({
            "artifact_id": "G01_CYCLE_OVERLAY",
            "canonical_path": "main/20_groups/overlays/overlay_cycle.md",
            "redirects": [],
            "status": "tombstone",
            "successors": (
                [
                    "main/10_student/profile.md",
                    "main/20_teacher/overlay.md",
                    "main/30_group/",
                ]
                if repo.name == "t2ag-skeleton"
                else [
                    "main/10_student/profile.md",
                    "main/30_group/G01/calendar.md",
                    "main/30_group/G02/calendar.md",
                ]
            ),
            "migration_reason": "0.2.0 composite overlay dissolved by owner",
        })
    elif repo.name == "t2ag-skeleton":
        by_id["G01_CYCLE_OVERLAY"]["status"] = "tombstone"
        by_id["G01_CYCLE_OVERLAY"]["successors"] = [
            "main/10_student/profile.md",
            "main/20_teacher/overlay.md",
            "main/30_group/",
        ]
        by_id["G01_CYCLE_OVERLAY"]["migration_reason"] = (
            "0.2.0 composite overlay dissolved by generic owner"
        )
    for item in artifacts:
        canonical = item.get("canonical_path")
        item["redirects"] = [
            value for value in dict.fromkeys(item.get("redirects", []))
            if value != canonical
        ]
    data["schema_version"] = 2
    data["updated"] = str(date.today())
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    legacy = repo / "main/70_tools/legacy_r_registry.json"
    if legacy.exists():
        rdata = json.loads(read_text(legacy))
        mapping = {
            "PHIL1101r_ZhouYi.md": ("PHIL1101r", "R002_PHIL1101r.md"),
            "DS1001r_Kaggle.md": ("DS1001r", "R001_DS1001r.md"),
        }
        for entry in rdata.get("entries", []):
            course_id, binding = mapping.get(entry.get("file"), ("", ""))
            if course_id:
                entry["status"] = "migrated"
                entry["course_id"] = course_id
                entry["canonical_course"] = f"main/40_course/{course_id}/course.md"
                entry["binding"] = f"main/30_group/G01/bindings/{binding}"
        rdata["schema_version"] = 2
        atomic_write(legacy, json.dumps(rdata, ensure_ascii=False, indent=2) + "\n")


def unknown_binaries(repo: Path) -> list[str]:
    result: list[str] = []
    for domain in RETIRED_DOMAINS:
        for path in iter_files(repo / "main" / domain):
            suffix = path.suffix.lower()
            if suffix in TEXT_SUFFIXES or suffix in KNOWN_BINARY_SUFFIXES:
                continue
            try:
                sample = path.read_bytes()[:4096]
            except OSError:
                continue
            if b"\0" in sample:
                result.append(relative(path, repo))
    return result


def duplicate_active_canonicals(repo: Path) -> list[str]:
    registry = repo / "main/70_tools/artifact_registry.json"
    if not registry.exists():
        return []
    try:
        artifacts = json.loads(read_text(registry)).get("artifacts", [])
    except (json.JSONDecodeError, OSError):
        return ["registry-unreadable"]
    owners: dict[str, list[str]] = {}
    for item in artifacts:
        if item.get("status") != "active":
            continue
        owners.setdefault(item.get("canonical_path", ""), []).append(item.get("artifact_id", ""))
    return [f"{path}: {ids}" for path, ids in owners.items() if path and len(ids) > 1]


def preflight(repo: Path, ops: list[Operation]) -> dict:
    pending = []
    missing = []
    collisions = []
    for op in ops:
        sources = source_paths(op, repo)
        existing = [source.exists() for source in sources]
        target = repo / op.target
        if all(existing):
            pending.append(asdict(op))
            collision = collision_for(op, repo)
            if collision:
                collisions.append(collision)
        elif target.exists():
            continue
        else:
            missing.append({"operation": asdict(op), "missing_sources": [
                relative(source, repo) for source, exists in zip(sources, existing) if not exists
            ]})
    return {
        "target_root": str(repo),
        "pending_count": len(pending),
        "missing": missing,
        "collisions": sorted(set(collisions)),
        "duplicate_active_canonicals": duplicate_active_canonicals(repo),
        "unknown_binaries": unknown_binaries(repo),
        "pending": pending,
    }


def remove_retired_paths(repo: Path) -> list[str]:
    removed: list[str] = []
    main = repo / "main"
    for name in RETIRED_DOMAINS:
        path = main / name
        if path.exists():
            resolved = path.resolve()
            if resolved.parent != main.resolve():
                raise RuntimeError(f"unsafe removal target: {resolved}")
            shutil.rmtree(resolved)
            removed.append(relative(path, repo))
    for source_name in ("course_group_rules.md", "t2ag_flow.md"):
        source = main / "00_core" / source_name
        target = main / "50_playbook" / source_name
        if source.exists():
            if not target.exists() or sha256(source) != sha256(target):
                raise RuntimeError(f"refusing to retire unverified Core source: {source}")
            source.unlink()
            removed.append(relative(source, repo))
    asset = repo / "assets/fable_snail.png"
    if asset.exists():
        resolved = asset.resolve()
        if resolved.parent != (repo / "assets").resolve():
            raise RuntimeError(f"unsafe removal target: {resolved}")
        resolved.unlink()
        removed.append(relative(asset, repo))
    assets_dir = repo / "assets"
    if assets_dir.exists() and not any(assets_dir.iterdir()):
        assets_dir.rmdir()
        removed.append("assets/")
    if repo.name == "t2ag-skeleton":
        root_skin = repo / "skin"
        if root_skin.exists():
            resolved = root_skin.resolve()
            if resolved.parent != repo.resolve():
                raise RuntimeError(f"unsafe removal target: {resolved}")
            shutil.rmtree(resolved)
            removed.append("skin/")
    return removed


def ensure_target_skeleton(repo: Path) -> None:
    main = repo / "main"
    for path in (
        main / "10_student/activities",
        main / "10_student/engagements",
        main / "20_teacher",
        main / "30_group/curricula",
        main / "40_course/_shared",
        main / "80_interface",
    ):
        path.mkdir(parents=True, exist_ok=True)


def write_reports(repo: Path, report: dict) -> None:
    journal = repo / "main/60_journal"
    json_path = journal / "migration_020_report.json"
    md_path = journal / "migration_020_review.md"
    if json_path.exists() and report.get("applied_count", 0) == 0:
        try:
            previous = json.loads(json_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        if previous.get("applied_count", 0) > 0:
            print("migration report: preserved first non-zero apply evidence")
            return
    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    checklist = f"""# T2AG 0.2.0 迁移审查

- 日期：{date.today()}
- 目标：`{repo.name}`
- 已执行操作：{report.get("applied_count", 0)}
- 已退役 active 路径：{len(report.get("removed", []))}
- 文本引用改写：{len(report.get("rewritten_text", []))}

## 人工检查清单

- [ ] `main/` 的编号域恰为 00/10/20/30/40/50/60/70/80。
- [ ] `10_student/` 不再出现 Case/学生编号包装层。
- [ ] 每门课程只有一个 `course.md` 和一个 `progress.md`。
- [ ] progress nodes 已并入 `progress.md`，旧文件不再 active。
- [ ] G01/G02 的 plan/calendar/review/bindings 职责分离。
- [ ] overlay registry 条目均为 tombstone + successors。
- [ ] registry 不存在两个 active artifact 共用 canonical。
- [ ] OCR 与其他脚本路径常量全部指向 `40_course/`。
- [ ] `.venv`、`.recovery`、`.staging` 未被迁移或删除。
- [ ] 第二次 `--check` 返回零待迁移项。
"""
    atomic_write(md_path, checklist)


def capture_operation_manifest(
    repo: Path,
    ops: list[Operation],
    target_kind: str,
    evidence_source: str,
) -> dict:
    rows: list[dict] = []
    for sequence, op in enumerate(ops, start=1):
        sources = []
        for path in source_paths(op, repo):
            sources.append({
                "path": relative(path, repo),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
        rows.append({
            "sequence": sequence,
            "kind": op.kind,
            "sources": sources,
            "target": op.target,
            "disposition": op.disposition,
        })
    return {
        "schema_version": "T2AG-MIGRATION-OPERATIONS-1",
        "target_kind": target_kind,
        "evidence_source": evidence_source,
        "operation_count": len(rows),
        "operations": rows,
    }


def finalize_operation_manifest(repo: Path, manifest: dict) -> dict:
    for row in manifest["operations"]:
        target = repo / row["target"]
        row["outcome"] = "applied"
        row["post_target"] = (
            {
                "path": row["target"],
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
            if target.is_file() else None
        )
    path = repo / "main/60_journal/migration_020_operations.json"
    atomic_write(path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return {
        "path": "main/60_journal/migration_020_operations.json",
        "operation_count": manifest["operation_count"],
        "sha256": sha256(path),
    }


def resolve_repo(script_repo: Path, target: str) -> Path:
    readme = script_repo / "README.md"
    readme_text = readme.read_text(encoding="utf-8-sig") if readme.exists() else ""
    is_skeleton = script_repo.name == "t2ag-skeleton" or "t2ag-skeleton" in readme_text.lower()
    if target == "main":
        profile = script_repo / "main/10_student/profile.md"
        if (
            profile.exists()
            and "initialization_status: uninitialized" in profile.read_text(encoding="utf-8-sig")
            and is_skeleton
        ):
            raise ValueError(
                "Main target is only implicit from the Main repository; "
                "use --target skeleton explicitly for Skeleton"
            )
        repo = script_repo
    elif target == "skeleton":
        repo = (
            script_repo
            if is_skeleton
            else script_repo.parent / "t2ag-skeleton"
        )
    else:
        raise ValueError("Lite is a derived snapshot and cannot be a migration input")
    if repo.name == "t2ag-lite":
        raise ValueError("Lite is a derived snapshot and cannot be a migration input")
    if not (repo / "main").is_dir():
        raise ValueError(f"invalid repository root: {repo}")
    return repo.resolve()


def main_cli() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only preflight (default)")
    mode.add_argument("--apply", action="store_true", help="perform copy/verify/remove migration")
    mode.add_argument("--rewrite-active", action="store_true", help="rewrite active references only")
    parser.add_argument("--target", choices=("main", "skeleton", "lite"), default="main")
    parser.add_argument("--json", action="store_true", help="print full JSON preflight")
    parser.add_argument(
        "--evidence-source",
        default="direct pre-migration tree",
        help="provenance label stored with an applied operation manifest",
    )
    args = parser.parse_args()

    script_repo = Path(__file__).resolve().parents[2]
    try:
        repo = resolve_repo(script_repo, args.target)
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 2
    target_kind = "skeleton" if args.target == "skeleton" else "main"
    if args.rewrite_active:
        changed = rewrite_active_text(repo)
        print(f"rewritten active text files: {len(changed)}")
        return 0
    ops = build_plan(repo, target_kind)
    report = preflight(repo, ops)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"target: {repo}")
        print(f"pending: {report['pending_count']}")
        print(f"missing: {len(report['missing'])}")
        print(f"collisions: {len(report['collisions'])}")
        print(f"duplicate active canonicals: {len(report['duplicate_active_canonicals'])}")
        print(f"unknown binaries: {len(report['unknown_binaries'])}")

    blockers = (
        report["missing"]
        or report["collisions"]
        or report["duplicate_active_canonicals"]
        or report["unknown_binaries"]
    )
    if not args.apply:
        return 1 if report["pending_count"] or blockers else 0
    if blockers:
        print("[FAIL] preflight blockers exist; no changes applied")
        return 2
    if report["pending_count"] == 0:
        print("already applied: 0 pending; existing migration report preserved")
        return 0

    operation_manifest = capture_operation_manifest(
        repo, ops, target_kind, args.evidence_source
    )
    ensure_target_skeleton(repo)
    applied = 0
    for op in ops:
        if all(path.exists() for path in source_paths(op, repo)):
            materialize(op, repo, target_kind)
            applied += 1
    update_registry(repo)
    rewritten = rewrite_active_text(repo)
    removed = remove_retired_paths(repo)
    ensure_target_skeleton(repo)
    operation_manifest_summary = finalize_operation_manifest(repo, operation_manifest)
    final_report = {
        **report,
        "status": "applied",
        "applied_count": applied,
        "rewritten_text": rewritten,
        "removed": removed,
        "operation_manifest": operation_manifest_summary,
        "post_apply_duplicate_active_canonicals": duplicate_active_canonicals(repo),
    }
    write_reports(repo, final_report)
    print(f"applied: {applied}")
    print(f"removed active paths: {len(removed)}")
    print(f"rewritten active text files: {len(rewritten)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
