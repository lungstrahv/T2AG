#!/usr/bin/env python3
"""Public generation entry: first run, new Course, new Group.

Why this module exists
----------------------
Before it, a fresh Skeleton could only become a real instance by having an Agent
hand-write files while reading `50_playbook/first_run.md` prose. Nothing failed
when a template was missing or a schema was reinvented, and the clean-room disk
roundtrip test proved only that the runtime *kernel* could process a complete
instance — it built that instance from hardcoded strings, never from the path a
user actually walks. This module is that public path, and the roundtrip test
drives it.

Authority boundary
------------------
This tool materializes structure from `_templates`. It does not decide anything
that belongs to the user: course choice, hint-gate mode, timezone, group
membership, teacher assignment. Missing required input is an error, never a
default. It does not create `.venv`, install dependencies, download textbooks,
generate Engagements, or run git. It does not run Doctor or state refresh on the
user's behalf — it prints the commands the playbook requires next, because
"generated" is not "verified".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_ledger as ledger_contract  # noqa: E402

DEFAULT_ROOT = TOOLS.parent.parent
COURSE_TEMPLATES = "main/40_course/_templates/course"
GROUP_TEMPLATES = "main/30_group/_templates/group"
DEFAULT_PERSONAL_ART = "03_inori_2.txt"

COURSE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]{2,}[0-9]{3,}[A-Za-z]?$")
GROUP_ID_RE = re.compile(r"^G\d{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDER_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
FENCE_RE = re.compile(r"(?ms)^```.*?^```\s*?$")

# Uppercase tokens that are real content, not placeholders to be filled.
PLACEHOLDER_ALLOWLIST = frozenset(
    {
        "QUESTION_BANK_TEMPLATE_V2",
        "T2AG_SESSION_CLOSE",
        "T2AG_CLOUD_CHANGE_DIRECTIVE",
        "T2AG_CLOUD_HANDOFF",
    }
)

PROFILE_REQUIRED_ANSWERS = (
    "nickname",
    "school",
    "stage",
    "direction",
    "weekly_time",
    "goals",
    "tutoring_preference",
    "long_explanation_mode",
    "branch_confirmation",
    "cycle_structure",
    "small_adjustment",
    "big_adjustment",
    "aged_review_mode",
    "existing_basis",
    "current_difficulty",
    "teaching_notes",
    "exercise_hint_gate",
    "learning_timezone",
    "learning_day_cutoff",
    "lesson_actual_review",
    "lesson_student_feedback",
    "lesson_knowledge_absorption",
    "exercise_problem_review",
    "exercise_knowledge_mastery",
    "updated",
)
ONOFF = ("on", "off")
ANSWER_ENUMS = {
    "exercise_hint_gate": ("enabled", "disabled"),
    "long_explanation_mode": ("map-first", "continuous", "user-defined"),
    "aged_review_mode": ("off", "suggest", "auto"),
    "lesson_actual_review": ONOFF,
    "lesson_student_feedback": ONOFF,
    "lesson_knowledge_absorption": ONOFF,
    "exercise_problem_review": ONOFF,
    "exercise_knowledge_mastery": ONOFF,
}
AGENT_DEFAULTS = {
    "agent_pool_limit": 6,
    "agent_max_active": 3,
    "agent_parallel_startup": "enabled",
    "agent_startup_readiness": "learning_ready_first",
    "agent_background_reporting": "blockers_only",
}


class GenerationError(Exception):
    """Raised for every refusal; the CLI turns it into a non-zero exit."""


def fail(message: str) -> "GenerationError":
    return GenerationError(message)


def read_text(path: Path) -> str:
    if not path.is_file():
        raise fail(f"缺文件：{path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str, *, allow_overwrite: bool = False) -> None:
    if path.exists() and not allow_overwrite:
        raise fail(f"目标已存在，拒绝覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def strip_fences(text: str) -> str:
    return FENCE_RE.sub("", text)


def render(template: str, mapping: dict[str, str], *, label: str) -> str:
    """Substitute placeholders longest-first, then refuse leftovers.

    Longest-first matters: ``CONTENT_GROUP_ID`` contains ``GROUP_ID``, so naive
    ordering would corrupt it. The leftover scan ignores fenced blocks because
    templates legitimately document their own entry format inside fences.
    """
    template_tokens = {
        token
        for token in PLACEHOLDER_RE.findall(strip_fences(template))
        if token not in PLACEHOLDER_ALLOWLIST
    }
    rendered = template
    for key in sorted(mapping, key=len, reverse=True):
        rendered = rendered.replace(key, mapping[key])
    body = strip_fences(rendered)
    # Only tokens the *template* declared count as unfilled. A generated value may
    # itself look like a placeholder (e.g. artifact_id TEST1001_EXERCISE01_SOURCE);
    # scanning the output alone would reject legitimate content.
    leftover = sorted(token for token in template_tokens if token in body)
    if leftover:
        raise fail(f"{label} 仍含未填占位符：{leftover}")
    if "YYYY-MM-DD" in body:
        raise fail(f"{label} 仍含未填日期占位符")
    return rendered


def materialize(
    template_root: Path,
    relative_template: str,
    target: Path,
    mapping: dict[str, str],
) -> None:
    source = template_root / relative_template
    write_text(target, render(read_text(source), mapping, label=relative_template))


def replace_field(text: str, field: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(field)}:\s*.*$", re.MULTILINE)
    if not pattern.search(text):
        raise fail(f"字段不存在，拒绝盲写：{field}")
    return pattern.sub(f"{field}: {value}", text, count=1)


def require_root(root: Path) -> Path:
    resolved = root.resolve()
    if not (resolved / "main/t2ag.md").is_file():
        raise fail(f"不是 T2AG 实例根目录（缺 main/t2ag.md）：{resolved}")
    return resolved


def profile_is_initialized(profile_text: str) -> bool:
    return bool(
        re.search(r"^initialization_status:\s*initialized\s*$", profile_text, re.MULTILINE)
    )


def load_answers(args: argparse.Namespace) -> dict[str, object]:
    if args.answers and args.answers_json:
        raise fail("--answers 与 --answers-json 只能给一个")
    if args.answers:
        payload = json.loads(read_text(Path(args.answers)))
    elif args.answers_json:
        payload = json.loads(args.answers_json)
    else:
        raise fail("init 需要 --answers 或 --answers-json；不得由工具代填学生答案")
    if not isinstance(payload, dict):
        raise fail("answers 必须是 JSON 对象")
    # 示例必须保持为合法 JSON，才能真实展示输入形状；也因此必须按键拒绝，
    # 不能依赖文件名（重命名不应把示例值变成用户确认）。
    if payload.get("example_only") is True:
        raise fail(
            "这是 answers.example.json 的示例值，不是学生的确认（example_only: true）。"
            "逐项与用户确认后另存为自己的 answers.json，并删除 example_only 键。"
            "字段说明见 main/70_tools/answers.schema.json"
        )
    missing = [key for key in PROFILE_REQUIRED_ANSWERS if key not in payload]
    if missing:
        raise fail(f"answers 缺必答项（这些必须由用户确认，不能默认）：{missing}")
    for key, allowed in ANSWER_ENUMS.items():
        if str(payload[key]) not in allowed:
            raise fail(f"answers.{key} 非法：{payload[key]!r}，允许 {list(allowed)}")
    if not DATE_RE.match(str(payload["updated"])):
        raise fail("answers.updated 必须是 YYYY-MM-DD")
    goals = payload["goals"]
    if not isinstance(goals, list) or not goals:
        raise fail("answers.goals 必须是非空列表")
    return payload


def render_profile(answers: dict[str, object]) -> str:
    def value(key: str) -> str:
        return str(answers[key])

    goals = "\n".join(f"- {item}" for item in answers["goals"])
    frontmatter = "\n".join(
        [
            "---",
            "type: student_profile",
            "initialization_status: initialized",
            f"exercise_hint_gate: {value('exercise_hint_gate')}",
            "agent_collaboration_schema: agent_collaboration_preferences.v1",
            f"agent_pool_limit: {answers.get('agent_pool_limit', AGENT_DEFAULTS['agent_pool_limit'])}",
            f"agent_max_active: {answers.get('agent_max_active', AGENT_DEFAULTS['agent_max_active'])}",
            f"agent_parallel_startup: {answers.get('agent_parallel_startup', AGENT_DEFAULTS['agent_parallel_startup'])}",
            f"agent_startup_readiness: {answers.get('agent_startup_readiness', AGENT_DEFAULTS['agent_startup_readiness'])}",
            f"agent_background_reporting: {answers.get('agent_background_reporting', AGENT_DEFAULTS['agent_background_reporting'])}",
            "activity_close_preference_schema: activity_close_preferences.v1",
            f"activity_close_preferences_initialized_at: {value('updated')}",
            "activity_close_first_prompt_status: pending",
            "activity_close_first_prompt_at: none",
            f"learning_timezone: {value('learning_timezone')}",
            f"learning_day_cutoff: {value('learning_day_cutoff')}",
            f"lesson_actual_review: {value('lesson_actual_review')}",
            f"lesson_student_feedback: {value('lesson_student_feedback')}",
            f"lesson_knowledge_absorption: {value('lesson_knowledge_absorption')}",
            f"exercise_problem_review: {value('exercise_problem_review')}",
            f"exercise_knowledge_mastery: {value('exercise_knowledge_mastery')}",
            f"updated: {value('updated')}",
            "---",
        ]
    )
    return (
        f"{frontmatter}\n"
        "# 学生档案\n\n"
        "> 由 `70_tools/t2ag_init.py init` 从用户确认的答案生成。\n"
        "> 未经用户确认的信息不得补写；变更偏好后同步刷新 memory 缓存。\n\n"
        "## 基本信息\n\n"
        f"- 姓名或昵称：{value('nickname')}\n"
        f"- 学校或机构：{value('school')}\n"
        f"- 年级或阶段：{value('stage')}\n"
        f"- 学习方向：{value('direction')}\n\n"
        "## 每周可投入学习时间\n\n"
        f"- {value('weekly_time')}\n\n"
        "## 学习目标\n\n"
        f"{goals}\n\n"
        "## 辅导与展现偏好\n\n"
        f"- 一般辅导偏好：{value('tutoring_preference')}\n"
        f"- 多块长篇讲解：{value('long_explanation_mode')}\n"
        f"- 分支间确认方式：{value('branch_confirmation')}\n\n"
        "## 执行参数\n\n"
        f"- 周期结构：{value('cycle_structure')}\n"
        f"- 小调整频率：{value('small_adjustment')}\n"
        f"- 大调整窗口：{value('big_adjustment')}\n"
        f"- 陈年复习卷模式：{value('aged_review_mode')}\n\n"
        "## 个体基线\n\n"
        f"- 已有基础：{value('existing_basis')}\n"
        f"- 当前困难：{value('current_difficulty')}\n"
        f"- 稳定教学注意事项：{value('teaching_notes')}\n"
    )


def switch_release_identity(root: Path, art_file: str, notes: list[str]) -> None:
    """first_run.md §8: personal instance identity, cloud still paused."""
    skin_registry = root / "main/80_interface/skin.yaml"
    active = re.search(r"^active:\s*(\S+)\s*$", read_text(skin_registry), re.MULTILINE)
    if not active:
        raise fail("skin.yaml 无 active 皮肤，无法切换发行身份")
    folder = re.search(
        rf"^registry\.{re.escape(active.group(1))}:\s*(\S+)\s*$",
        read_text(skin_registry),
        re.MULTILINE,
    )
    if not folder:
        raise fail(f"skin.yaml 未登记 active 皮肤目录：{active.group(1)}")
    skin_meta = root / f"main/80_interface/{folder.group(1)}/skin.yaml"
    art_path = root / f"main/80_interface/{folder.group(1)}/{art_file}"
    if not art_path.is_file():
        raise fail(f"字符画不存在，拒绝写入悬空 art_file：{art_path}")
    write_text(
        skin_meta,
        replace_field(read_text(skin_meta), "art_file", art_file),
        allow_overwrite=True,
    )
    notes.append(f"skin art_file → {art_file}")

    state_path = root / "cloud/cloud_sync_state.md"
    if state_path.is_file():
        state = read_text(state_path)
        if "- current_cloud_project_mode: generic_skeleton" in state:
            state = state.replace(
                "- current_cloud_project_mode: generic_skeleton",
                "- current_cloud_project_mode: personal_instance",
                1,
            )
            notes.append("cloud project mode → personal_instance")
        elif "- current_cloud_project_mode: personal_instance" not in state:
            raise fail("cloud_sync_state 无可识别的 current_cloud_project_mode")
        if "new_cloud_sessions_allowed:" not in state:
            state = state.replace(
                "- cloud_bridge_status: paused\n",
                "- cloud_bridge_status: paused\n"
                "- new_cloud_sessions_allowed: false\n"
                "- new_component_directives_allowed: false\n",
                1,
            )
            notes.append("cloud 新会话/新指令闸门 → false")
        write_text(state_path, state, allow_overwrite=True)

    prompt_path = root / "cloud/T2AG_PROJECT_INSTRUCTIONS.txt"
    if prompt_path.is_file():
        prompt = read_text(prompt_path)
        if "cloud_project_mode: generic_skeleton" in prompt:
            prompt = prompt.replace(
                "cloud_project_mode: generic_skeleton",
                "cloud_project_mode: personal_instance",
                1,
            )
        elif "cloud_project_mode: personal_instance" not in prompt:
            raise fail("cloud 提示词无可识别的 cloud_project_mode")
        if "personal_instance_protocol_markers:" not in prompt:
            prompt += (
                "\n\npersonal_instance_protocol_markers:\n"
                "- T2AG_SESSION_CLOSE\n"
                "- T2AG_CLOUD_CHANGE_DIRECTIVE\n"
                "- T2AG_CLOUD_HANDOFF\n"
            )
            notes.append("个人实例协议 marker 已写入云提示词")
        write_text(prompt_path, prompt, allow_overwrite=True)


def cmd_init(args: argparse.Namespace) -> int:
    root = require_root(Path(args.root))
    answers = load_answers(args)
    profile_path = root / "main/10_student/profile/profile.md"
    if profile_is_initialized(read_text(profile_path)):
        raise fail(
            "profile 已 initialized：这不是首次启动。改偏好请直接编辑 profile，"
            "不要用 init 重置实例。"
        )
    notes: list[str] = []
    write_text(profile_path, render_profile(answers), allow_overwrite=True)
    notes.append("profile → initialized")
    switch_release_identity(root, args.art_file, notes)
    print("[OK] first run initialized")
    for note in notes:
        print(f"  - {note}")
    print(
        "\n下一步（本工具不代跑，也不代替课程与课程组的用户确认）：\n"
        "  1. python -B main/70_tools/t2ag_init.py new-course ...      # first_run.md §5\n"
        "  2. python -B main/70_tools/t2ag_init.py new-group ...       # first_run.md §6（只生 planned）\n"
        "  3. 建组仪式（议容量参数；progress 组另需写真实碑行）\n"
        "  4. python -B main/70_tools/t2ag_init.py activate-group ...  # 公证激活\n"
        "  5. python -B main/70_tools/t2ag_state_refresh.py --write\n"
        "  6. python -B main/70_tools/t2ag_state_refresh.py --check\n"
        "  7. python -B main/70_tools/t2ag_doctor.py --profile runtime"
    )
    return 0


def drop_gate_ledger_section(body: str) -> str:
    """Remove 门台账 from a freshly created carrier.

    `check_gate_ledger` skips carriers without the section by design: the section
    arrives with the `ledger_since` anchor at the first real gate crossing. Keeping
    the template's placeholder anchor instead would point at a checkpoint that no
    honest generator can populate — the row needs a real textbook `block_id` with
    a `#` block key, and no page has been prepared yet.
    """
    marker = body.find("## 门台账")
    if marker == -1:
        return body
    return (
        body[:marker]
        + "## 教学门记录\n\n"
        "尚未启用。首次真实门穿越时按 `00_core/learning_activity_model.md` §2.4 建立\n"
        "`ledger_since` 锚与留痕表；本节标题届时改为「门台账」。未备页、未开讲的 Lesson\n"
        "不预造锚——空锚会被 Doctor 判为台账损坏（fail-closed），比没有台账更糟。\n"
    )


def validate_teacher_target(root: Path, teacher: str) -> None:
    if not re.fullmatch(r"T\d{3}", teacher):
        raise fail(f"教师模板 ID 非法：{teacher}")
    if not (root / f"main/20_teacher/{teacher}.md").is_file():
        raise fail(f"教师模板不存在：main/20_teacher/{teacher}.md")
    overlay = root / "main/20_teacher/overlay.md"
    if "| (默认) |" not in read_text(overlay):
        raise fail("overlay.md 缺默认映射行，无法定位课程—教师映射表")


def ensure_teacher_row(root: Path, course_id: str, course_name: str, teacher: str) -> None:
    overlay = root / "main/20_teacher/overlay.md"
    text = read_text(overlay)
    if re.search(rf"^\|\s*{re.escape(course_id)}\s*\|", text, re.MULTILINE):
        return
    anchor = "| (默认) |"
    row = (
        f"| {course_id} | {course_name} | `main/20_teacher/{teacher}.md` | "
        "首次开课后确认 |\n"
    )
    write_text(overlay, text.replace(anchor, row + anchor, 1), allow_overwrite=True)


def register_artifact(root: Path, artifact_id: str, canonical_path: str) -> None:
    registry_path = root / "main/70_tools/artifact_registry.json"
    registry = json.loads(read_text(registry_path))
    artifacts = registry.setdefault("artifacts", [])
    if any(item.get("artifact_id") == artifact_id for item in artifacts):
        raise fail(f"artifact 已登记，拒绝重复：{artifact_id}")
    artifacts.append(
        {
            "artifact_id": artifact_id,
            "canonical_path": canonical_path,
            "redirects": [],
            "status": "active",
            "migration_reason": "created by t2ag_init new-course",
        }
    )
    write_text(
        registry_path,
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        allow_overwrite=True,
    )


def genesis_event(
    *,
    course_id: str,
    activity_type: str,
    activity_id: str,
    recorded_at: str,
    evidence_ref: str,
    content_group: str,
) -> str:
    """P-0062 genesis: first event is transition planned→ongoing, not a migration."""
    ledger_contract.validate_activity_id(activity_type, activity_id)
    return "\n".join(
        [
            "### ALE-000001",
            "event_id: ALE-000001",
            "event_kind: transition",
            f"course_id: {course_id}",
            f"activity_type: {activity_type}",
            f"activity_id: {activity_id}",
            "from_state: planned",
            "to_state: ongoing",
            f"occurred_at: {recorded_at}",
            f"recorded_at: {recorded_at}",
            "triggered_by: user",
            "trigger: activity_created",
            f"transaction_id: INIT-{course_id}-{activity_id}",
            f"content_group_ids: [{content_group}]",
            f"evidence_refs: [{evidence_ref}]",
            "",
        ]
    )


def cmd_new_course(args: argparse.Namespace) -> int:
    root = require_root(Path(args.root))
    course_id = args.course_id
    if not COURSE_ID_RE.match(course_id):
        raise fail(f"course_id 不符合 naming_conventions.md：{course_id}")
    course = root / f"main/40_course/{course_id}"
    if course.exists():
        raise fail(f"课程目录已存在，拒绝覆盖：{course}")
    if not DATE_RE.match(args.date):
        raise fail("--date 必须是 YYYY-MM-DD")
    if args.entry != "none" and args.lifecycle != "ongoing":
        raise fail("planned 课程不得创建首个学习活动（new_course_init.md §3）")
    if args.entry == "none" and args.lifecycle == "ongoing":
        raise fail("ongoing 课程必须有真实入口：--entry lesson 或 exercise")
    if args.entry == "exercise" and args.driver == "textbook" and not args.source_document:
        raise fail(
            "教材驱动的 Exercise 首启必须先有持久校对题源："
            "给 --source-document / --source-locator / --problem-text"
        )
    # Validate every precondition before the first write: a half-written course
    # that failed on a late check is worse than a refusal, because Doctor then
    # reports cascading failures the user did not cause.
    validate_teacher_target(root, args.teacher)
    if args.source_document and not Path(args.source_document).is_file():
        raise fail(f"题源文档不存在：{args.source_document}")

    templates = root / COURSE_TEMPLATES
    content_group = args.content_group or f"{course_id}-B001-C01-S01"
    base = {
        "COURSE_ID": course_id,
        "COURSE_NAME": args.name,
        "COURSE_DRIVER": args.driver,
        "CONTENT_GROUP_ID": content_group,
        "SOURCE_SCOPE": args.source_scope,
        "SOURCE_LANGUAGE": args.source_language,
        "YYYY-MM-DD": args.date,
    }
    created: list[str] = []

    def note(path: Path) -> None:
        created.append(str(path.relative_to(root)).replace("\\", "/"))

    course_meta = render(read_text(templates / "course.md.template"), base, label="course.md")
    course_meta = replace_field(course_meta, "school_course_code", args.school_code or course_id)
    course_meta = replace_field(course_meta, "course_type", args.course_type)
    course_meta = replace_field(course_meta, "default_driver", args.driver)
    write_text(course / "course.md", course_meta)
    note(course / "course.md")

    for relative, target in (
        ("question_bank.md.template", "question_bank.md"),
        ("mistake_bank.md.template", "mistake_bank.md"),
    ):
        materialize(templates, relative, course / target, base)
        note(course / target)
    # Every Course owns a book/ root, textbook-driven or not: Doctor treats a
    # missing book/ as a structural fault, and non-textbook courses still need a
    # place to declare where their evidence comes from.
    materialize(templates, "book/README.md.template", course / "book/README.md", base)
    note(course / "book/README.md")
    if args.driver != "textbook":
        write_text(
            course / "book/README.md",
            read_text(course / "book/README.md").replace(
                "## 主教材\n\n| 文件 | 资料 | 用途 |\n|---|---|---|\n",
                f"## 主教材\n\n无主教材：本课程由 `{args.driver}` 驱动，"
                "证据来源写在下方参考表或 Course 定义中。\n",
                1,
            ),
            allow_overwrite=True,
        )

    activity_type = args.entry
    activity_id = "lesson01" if activity_type == "lesson" else "exercise01"

    if args.lifecycle == "planned":
        planned = render(
            read_text(templates / "progress_planned.md.template"),
            {**base, "NEXT_ACTION": args.next_action},
            label="progress.md",
        )
        write_text(course / "progress.md", planned)
        note(course / "progress.md")
        write_text(course / "activity_ledger.md", ledger_contract.empty_ledger(course_id))
        note(course / "activity_ledger.md")
        write_text(course / "lessons/_README.md", "尚无 Lesson：课程为 planned。\n")
        write_text(course / "exercises/_README.md", "尚无 Exercise：课程为 planned。\n")
    else:
        completion_node = f"{content_group}-N01"
        checkpoint = args.checkpoint or f"{course_id}-B001-P001-N01"
        progress_map = {
            **base,
            "START_POSITION": args.position,
            "COMPLETION_NODE": completion_node,
            "CHECKPOINT": checkpoint,
            "NEXT_ACTION": f"resume {activity_type}:{activity_id}",
        }
        progress = render(
            read_text(templates / "progress.md.template"), progress_map, label="progress.md"
        )
        progress = replace_field(progress, "course_driver", args.driver)
        progress = replace_field(progress, "current_activity", activity_type)
        progress = replace_field(progress, "current_activity_id", activity_id)
        progress = replace_field(
            progress,
            "resume_path",
            f"main/40_course/{course_id}/{activity_type}s/{activity_id}/"
            f"{activity_id if activity_type == 'lesson' else 'exercise'}.md",
        )
        progress = replace_field(progress, "next_activity_type", activity_type)
        progress = replace_field(progress, "next_activity_id", activity_id)
        progress += (
            "\n## Completion nodes\n\n"
            "| node_id | 标题 | 来源范围 | 状态 | 完成证据 |\n"
            "|---|---|---|---|---|\n"
            f"| {completion_node} | {args.node_title} | {args.source_scope} | queued | — |\n"
        )
        write_text(course / "progress.md", progress)
        note(course / "progress.md")

        if activity_type == "lesson":
            lesson_dir = course / "lessons/lesson01"
            lesson_map = {
                **base,
                "START_POSITION": args.position,
                "FIRST_CHECKPOINT_ID": checkpoint,
            }
            body = render(
                read_text(templates / "lessons/lessonNN/lessonNN.md.template"),
                lesson_map,
                label="lesson01.md",
            ).replace("lessonNN", "lesson01")
            body = drop_gate_ledger_section(body)
            write_text(lesson_dir / "lesson01.md", body)
            note(lesson_dir / "lesson01.md")
            if args.driver == "textbook":
                # LessonMap ships empty; page rows arrive with the first real
                # preparation run. No preparation Snapshot is written here on
                # purpose: a Snapshot asserts prepared pages, load receipts and
                # complete scope coverage, and this tool must not fabricate source
                # evidence. Doctor accepts "created but never entered" because the
                # ledger has no learning_enter event yet.
                materialize(
                    templates,
                    "lessons/lessonNN/lesson_map.md.template",
                    lesson_dir / "lesson_map.md",
                    base,
                )
                note(lesson_dir / "lesson_map.md")
            write_text(course / "exercises/_README.md", "尚无 Exercise：本课从讲授进入。\n")
            evidence = f"main/40_course/{course_id}/lessons/lesson01/lesson01.md"
        else:
            exercise_dir = course / "exercises/exercise01"
            source_id = content_group.lower().replace("-", "_")
            artifact_id = f"{course_id}_EXERCISE01_SOURCE"
            source_relative = (
                f"main/40_course/{course_id}/book/primary/verified_excerpts/{source_id}.md"
            )
            document_relative = ""
            document_sha = ""
            if args.source_document:
                document = Path(args.source_document)
                if not document.is_file():
                    raise fail(f"题源文档不存在：{document}")
                document_relative = (
                    f"main/40_course/{course_id}/book/primary/source_documents/"
                    f"{document.name}"
                )
                target_document = root / document_relative
                target_document.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(document, target_document)
                note(target_document)
                document_sha = hashlib.sha256(target_document.read_bytes()).hexdigest()
            source_map = {
                **base,
                "SOURCE_ARTIFACT_ID": artifact_id,
                "SOURCE_DOCUMENT_PATH": document_relative or "none",
                "SOURCE_DOCUMENT_SHA256": document_sha or "none",
                "SOURCE_LOCATOR": args.source_locator,
                "SOURCE_PAGE": args.source_page,
                "PROBLEM_TEXT": args.problem_text,
                "exerciseNN": "exercise01",
            }
            source_body = render(
                read_text(templates / "book/primary/verified_excerpts/source.md.template"),
                source_map,
                label="verified excerpt",
            )
            if args.verification_status != "human_verified":
                source_body = replace_field(
                    source_body, "verification_status", args.verification_status
                )
            write_text(root / source_relative, source_body)
            note(root / source_relative)
            register_artifact(root, artifact_id, source_relative)
            source_sha = hashlib.sha256((root / source_relative).read_bytes()).hexdigest()

            exercise_body = render(
                read_text(templates / "exercises/exerciseNN/exercise.md.template"),
                {
                    **base,
                    "START_POSITION": args.position,
                    "PROBLEM_ID": "exercise01-Q001",
                },
                label="exercise01.md",
            ).replace("exerciseNN", "exercise01")
            write_text(exercise_dir / "exercise.md", exercise_body)
            note(exercise_dir / "exercise.md")
            problems_body = render(
                read_text(templates / "exercises/exerciseNN/problems.md.template"),
                {
                    **source_map,
                    "SOURCE_ID": source_id,
                    "SOURCE_SHA256": source_sha,
                },
                label="problems.md",
            ).replace("exerciseNN", "exercise01")
            write_text(exercise_dir / "problems.md", problems_body)
            note(exercise_dir / "problems.md")
            (exercise_dir / "attempts").mkdir(parents=True, exist_ok=True)
            (exercise_dir / "reviews").mkdir(parents=True, exist_ok=True)
            write_text(
                course / "lessons/_README.md", "尚无 Lesson：本课从做题进入。\n"
            )
            evidence = f"main/40_course/{course_id}/exercises/exercise01/exercise.md"

        write_text(
            course / "activity_ledger.md",
            ledger_contract.build_ledger_with_events(
                course_id,
                genesis_event(
                    course_id=course_id,
                    activity_type=activity_type,
                    activity_id=activity_id,
                    recorded_at=f"{args.date}T00:00:00Z",
                    evidence_ref=evidence,
                    content_group=content_group,
                ),
            ),
        )
        note(course / "activity_ledger.md")

        if args.driver == "textbook":
            activity_map = render(
                read_text(templates / "activity_map.md.template"), base, label="activity_map.md"
            )
            if activity_type == "exercise":
                activity_map = activity_map.replace(
                    f"| {content_group} | {args.source_scope} | lesson01 | — |",
                    f"| {content_group} | {args.source_scope} | — | exercise01 |",
                )
            write_text(course / "activity_map.md", activity_map)
            note(course / "activity_map.md")

    ensure_teacher_row(root, course_id, args.name, args.teacher)
    print(f"[OK] course {course_id} generated ({args.lifecycle}, entry={args.entry})")
    for path in created:
        print(f"  + {path}")
    print(
        "\n下一步：\n"
        "  python -B main/70_tools/t2ag_state_refresh.py --write\n"
        "  python -B main/70_tools/t2ag_state_refresh.py --check\n"
        "  python -B main/70_tools/t2ag_doctor.py --profile runtime"
    )
    return 0


def drop_keystone_sections(plan: str) -> str:
    """Remove §主干碑序列 and §碑变更台账 from a schedule-mode plan.

    The template instructs schedule groups to delete both sections (the keystone
    ledger is a progress-container instrument; schedule groups bound scope by
    deadline instead, course_group_rules.md §4.3). Leaving template keystone rows
    in a schedule plan would be dead prose at best and a fake anchor surface at
    worst, so the generator applies the template's own instruction.
    """
    match = re.search(r"^#+\s.*主干碑序列.*$", plan, flags=re.MULTILINE)
    if not match:
        return plan
    ledger = re.search(r"^#+\s.*碑变更台账.*$", plan, flags=re.MULTILINE)
    scan_from = ledger.end() if ledger and ledger.start() > match.start() else match.end()
    nxt = re.search(r"^#+\s", plan[scan_from:], flags=re.MULTILINE)
    end = scan_from + nxt.start() if nxt else len(plan)
    return plan[: match.start()] + plan[end:]


def cmd_new_group(args: argparse.Namespace) -> int:
    """Create a Group — always planned, never active.

    Birth and activation are deliberately separate commands (user ruling
    2026-08-22). `active` is post-ritual state: for a progress group it implies
    a keystone anchor, and the anchor is the receipt of a judgment
    (per-keystone confirmation at the 建组仪式) that no flag can substitute
    for. A command that births `active` produces the state without the
    evidence — exactly the P-0077/P-0078 family. Activation lives in
    `activate-group`, which refuses to run until the evidence is on disk.
    """
    root = require_root(Path(args.root))
    if not GROUP_ID_RE.match(args.group_id):
        raise fail(f"group_id 必须形如 G01：{args.group_id}")
    group = root / f"main/30_group/{args.group_id}"
    if group.exists():
        raise fail(f"课程组目录已存在，拒绝覆盖：{group}")
    if not DATE_RE.match(args.date):
        raise fail("--date 必须是 YYYY-MM-DD")
    members = [item.strip() for item in args.members.split(",") if item.strip()]
    if not members:
        raise fail("课程组必须有至少一个课程成员")
    for course_id in members:
        if not (root / f"main/40_course/{course_id}/progress.md").is_file():
            raise fail(f"成员课程不存在：{course_id}")

    templates = root / GROUP_TEMPLATES
    mapping = {
        "GROUP_ID": args.group_id,
        "COURSE_ID": members[0],
        "CURRENT_COURSE": "none",
        "CYCLE_SHAPE": args.cycle,
        "YYYY-MM-DD": args.date,
    }
    for relative, target in (
        ("plan.md.template", "plan.md"),
        ("calendar.md.template", "calendar.md"),
        ("review.md.template", "review.md"),
        ("bindings/_README.md.template", "bindings/_README.md"),
    ):
        materialize(templates, relative, group / target, mapping)

    plan = read_text(group / "plan.md")
    plan = replace_field(plan, "course_members", "[" + ", ".join(members) + "]")
    plan = replace_field(plan, "container_mode", args.container_mode)
    if args.container_mode == "schedule":
        plan = drop_keystone_sections(plan)
    write_text(group / "plan.md", plan, allow_overwrite=True)
    calendar = read_text(group / "calendar.md")
    calendar = replace_field(calendar, "container_mode", args.container_mode)
    write_text(group / "calendar.md", calendar, allow_overwrite=True)

    print(
        f"[OK] group {args.group_id} generated (planned, {args.container_mode}), "
        f"members={members}"
    )
    print(
        "\n下一步：\n"
        "  1. 建组仪式：与用户议定容量参数（calendar.md 三处 TBD）"
        + (
            "，并把 plan.md「主干碑序列」的模板行替换为逐碑确认后的真实碑行\n"
            if args.container_mode == "progress"
            else "\n"
        )
        + "  2. python -B main/70_tools/t2ag_init.py activate-group --group-id "
        f"{args.group_id} --date YYYY-MM-DD\n"
        "  3. python -B main/70_tools/t2ag_state_refresh.py --write\n"
        "  4. python -B main/70_tools/t2ag_doctor.py --profile runtime"
    )
    return 0


# Template keystone rows are placeholders, not evidence. `- K01 碑描述` passing
# for a confirmed keystone would recreate the exact hole activation exists to
# close, so the notary refuses any row still carrying the template description.
TEMPLATE_KEYSTONE_RE = re.compile(r"^-\s+K\d+\s+碑描述", re.MULTILINE)
KEYSTONE_ROW_RE = re.compile(r"^-\s+K\d+\b", re.MULTILINE)


def plan_section(text: str, title: str) -> str:
    """Extract a section body by heading keyword — mirrors doctor's parser.

    Keeping the two parsers shape-identical matters: if activation counted
    keystones one way and reconciliation another, the anchor would be wrong the
    moment it was notarized.
    """
    match = re.search(rf"^#+\s.*{title}.*$", text, flags=re.MULTILINE)
    if not match:
        return ""
    rest = text[match.end():]
    nxt = re.search(r"^#+\s", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def cmd_activate_group(args: argparse.Namespace) -> int:
    """建组仪式收尾：planned → active，公证而非代判。

    The judgment (which keystones, which capacity parameters) happens in the
    files, by the user, before this command runs. The command only checks that
    the evidence exists — real keystone rows, eligible member courses, a single
    active group — then notarizes it: counts the rows, writes
    `keystone_total_frozen`, flips the status. It can verify form, not thought;
    that boundary is the system's own (裁决在人，机器只判走没走门，§4.3).
    """
    root = require_root(Path(args.root))
    if not DATE_RE.match(args.date):
        raise fail("--date 必须是 YYYY-MM-DD")
    group = root / f"main/30_group/{args.group_id}"
    plan_path = group / "plan.md"
    if not plan_path.is_file():
        raise fail(f"课程组不存在：{plan_path}")
    plan = read_text(plan_path)

    status = re.search(r"^status:\s*(\S+)\s*$", plan, re.MULTILINE)
    if not status or status.group(1) != "planned":
        raise fail(
            f"只有 planned 组可以激活；{args.group_id} 当前 status="
            f"{status.group(1) if status else '缺失'}"
        )
    existing = [
        path.parent.name
        for path in (root / "main/30_group").glob("G*/plan.md")
        if re.search(r"^status:\s*active\s*$", read_text(path), re.MULTILINE)
    ]
    if existing:
        raise fail(f"已有 active 课程组，拒绝激活第二个：{existing}")

    mode = re.search(r"^container_mode:\s*(\S+)\s*$", plan, re.MULTILINE)
    if not mode or mode.group(1) not in {"progress", "schedule"}:
        raise fail(
            f"container_mode 非法或缺失：{mode.group(1) if mode else '缺失'}"
            "（合法值 progress/schedule，没有容器不是模式）"
        )
    container_mode = mode.group(1)

    members_match = re.search(r"^course_members:\s*\[(.*)\]\s*$", plan, re.MULTILINE)
    members = [
        item.strip() for item in (members_match.group(1) if members_match else "").split(",")
        if item.strip()
    ]
    if not members:
        raise fail("课程组无课程成员，无法激活")
    for course_id in members:
        progress = root / f"main/40_course/{course_id}/progress.md"
        if not progress.is_file():
            raise fail(f"成员课程不存在：{course_id}")
        lifecycle = re.search(
            r"^lifecycle_status:\s*(\S+)\s*$", read_text(progress), re.MULTILINE
        )
        if lifecycle and lifecycle.group(1) in {"planned", "completed", "dropped"}:
            raise fail(
                f"active 课程组不得包含 {lifecycle.group(1)} 课程：{course_id}"
                "（planned 课程须经用户确认转 ongoing 后再激活组）"
            )

    current_course = args.current_course or (members[0] if len(members) == 1 else "")
    if not current_course:
        raise fail("多成员课程组必须由用户指定当前前台课程：--current-course")
    if current_course not in members:
        raise fail(f"--current-course 不在成员中：{current_course}")

    if container_mode == "progress":
        if re.search(r"^keystone_total_frozen:", plan, re.MULTILINE):
            raise fail(
                "planned 组不应已有 keystone_total_frozen（planned 阶段不冻结，"
                "§4.3）；该锚只能由本命令在激活时写入"
            )
        section = plan_section(plan, "主干碑序列")
        if not section:
            raise fail(
                "plan.md 缺「主干碑序列」节：progress 组的容器就是这张表（§4.3）"
            )
        template_rows = TEMPLATE_KEYSTONE_RE.findall(section)
        if template_rows:
            raise fail(
                f"主干碑序列仍是模板占位行 {len(template_rows)} 条（`碑描述`）："
                "激活前须在建组仪式上逐碑确认并写成真实碑行"
                "（属哪门课、达成判据指向该课 progress.md 哪一行）"
            )
        keystones = KEYSTONE_ROW_RE.findall(section)
        if not keystones:
            raise fail("主干碑序列节内无 `- Knn` 碑行，无碑可冻，拒绝激活")
        plan = re.sub(
            r"^(container_mode:.*)$",
            rf"\1\nkeystone_total_frozen: {len(keystones)}",
            plan,
            count=1,
            flags=re.MULTILINE,
        )
        anchor_note = f"，keystone_total_frozen={len(keystones)}"
    else:
        anchor_note = ""

    plan = replace_field(plan, "status", "active")
    plan = replace_field(plan, "current_course", current_course)
    plan = replace_field(plan, "updated", args.date)
    write_text(plan_path, plan, allow_overwrite=True)
    calendar_path = group / "calendar.md"
    if calendar_path.is_file():
        write_text(
            calendar_path,
            replace_field(read_text(calendar_path), "status", "active"),
            allow_overwrite=True,
        )
    review_path = group / "review.md"
    if review_path.is_file():
        write_text(
            review_path,
            replace_field(read_text(review_path), "status", "open"),
            allow_overwrite=True,
        )

    print(
        f"[OK] group {args.group_id} activated ({container_mode}"
        f"{anchor_note}), current_course={current_course}"
    )
    print(
        "\n下一步：\n"
        "  python -B main/70_tools/t2ag_state_refresh.py --write\n"
        "  python -B main/70_tools/t2ag_doctor.py --profile runtime"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="T2AG public generation entry (first run / new Course / new Group)"
    )
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="实例根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="首次启动：写 profile 与发行身份")
    init.add_argument("--answers", help="用户确认答案的 JSON 文件")
    init.add_argument("--answers-json", help="用户确认答案的内联 JSON")
    init.add_argument("--art-file", default=DEFAULT_PERSONAL_ART)
    init.set_defaults(handler=cmd_init)

    course = sub.add_parser("new-course", help="新建课程与首个学习活动")
    course.add_argument("--course-id", required=True)
    course.add_argument("--name", required=True)
    course.add_argument("--school-code")
    course.add_argument("--course-type", default="mastery")
    # Required on purpose, no default: source_language is the language of the
    # course's own materials (existing courses run both en and zh-CN), and the
    # T001 §9 terminology discipline reads it to decide which words must keep
    # their original form. A wrong value fails silently — the teacher keeps
    # obeying the discipline, just against the wrong language. Asking once at
    # course creation is cheaper than a mislabelled course nobody notices.
    course.add_argument("--source-language", required=True, help="教材/原始材料语言，如 en、zh-CN")
    course.add_argument(
        "--driver", default="textbook", choices=("textbook", "goal", "project", "praxis")
    )
    course.add_argument("--lifecycle", default="ongoing", choices=("ongoing", "planned"))
    course.add_argument("--entry", default="lesson", choices=("lesson", "exercise", "none"))
    course.add_argument("--teacher", default="T001", help="main/20_teacher/Tddd.md")
    course.add_argument("--content-group")
    course.add_argument("--source-scope", default="待确认范围")
    course.add_argument("--position", default="课程刚建立，尚未推进")
    course.add_argument("--node-title", default="首个完成节点")
    course.add_argument("--checkpoint")
    course.add_argument("--next-action", default="等待用户确认开课时间")
    course.add_argument("--source-document")
    course.add_argument("--source-locator", default="待登记")
    course.add_argument("--source-page", default="1")
    course.add_argument("--problem-text", default="待录入")
    course.add_argument(
        "--verification-status",
        default="human_verified",
        choices=("human_verified", "synthetic_verified"),
    )
    course.add_argument("--date", required=True, help="YYYY-MM-DD")
    course.set_defaults(handler=cmd_new_course)

    group = sub.add_parser("new-group", help="新建课程组（只生 planned；激活走 activate-group）")
    group.add_argument("--group-id", required=True)
    group.add_argument("--members", required=True, help="逗号分隔的 course_id")
    # Required on purpose, no default: the container shape (deadline-bounded
    # schedule vs budget-bounded progress) is an intent the user knows at
    # creation and the tool must not guess — same criterion as new-course's
    # --source-language (course_group_rules.md §4.1: having *no* container is
    # not a mode, so silence is not an answer either).
    group.add_argument(
        "--container-mode", required=True, choices=("progress", "schedule"),
        help="容器形态：progress=固定预算放开时间；schedule=固定 deadline 放开范围",
    )
    group.add_argument("--cycle", default="待确认")
    group.add_argument("--date", required=True, help="YYYY-MM-DD")
    group.set_defaults(handler=cmd_new_group)

    activate = sub.add_parser(
        "activate-group",
        help="建组仪式收尾：planned → active（公证式：progress 组验真实碑行并落锚）",
    )
    activate.add_argument("--group-id", required=True)
    activate.add_argument("--current-course", help="多成员组必填：当前前台课程")
    activate.add_argument("--date", required=True, help="YYYY-MM-DD")
    activate.set_defaults(handler=cmd_activate_group)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except GenerationError as exc:
        print(f"[FAIL] {exc}")
        return 1
    except ledger_contract.LedgerError as exc:
        print(f"[FAIL] ledger 契约拒绝生成结果：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
