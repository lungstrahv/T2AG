#!/usr/bin/env python3
"""T2AG 0.2.2 activity-close migrator (D-hardened).

Modes:
  --check              inventory only
  --dry-run --plan-out PATH
      Build an immutable UTF-8 plan file once; zero instance writes.
  --apply --plan-file PATH --expect-payload-sha S --expect-file-sha F
      --confirm E_migration_apply
      Requires T2AG_022_ALLOW_APPLY=1 and exact SHA binding.
      Applies only through activity_transaction with rollback.

Fidelity rules:
  - strip Activity status only from lessonNN.md / exercise.md
  - never strip problems.md or Review/Attempt status
  - rewrite only structured canonical fields + pure path link targets
  - preserve progress activity_position text and free prose U1101-Q mentions
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import activity_ledger as ledger  # noqa: E402
import activity_transaction as txn  # noqa: E402
import campaign_receipt as campaign  # noqa: E402
import occurrence_classify as occurrence  # noqa: E402
import t2ag_state_refresh as state_refresh  # noqa: E402

PRODUCTION_ROOT = Path(r"C:\Users\MikeChen\T2AC\t2ag").resolve()
# 0.2.2 migration has already been applied and released.  Keeping the dry-run
# oracle is useful, but the production apply entry is permanently retired so a
# historical delegated receipt can never be replayed as RT3 authority.
PRODUCTION_MIGRATION_APPLY_ENABLED = False

COURSES = [
    "CS1953",
    "DS1001r",
    "IV1001",
    "MATH1205H",
    "MATH1607H",
    "PHIL1101r",
    "PY1001",
]

# Workspace-relative active reference roots under Main (allowlist-aligned).
ACTIVE_REF_GLOBS = [
    "main/40_course/*/activity_map.md",
    "main/40_course/*/course.md",
    "main/40_course/*/progress.md",
    "main/40_course/*/question_bank.md",
    "main/40_course/*/mistake_bank.md",
    "main/40_course/*/exercises/exercise_thoughts.md",
    "main/40_course/*/lessons/*/lesson*.md",
    "main/40_course/*/book/primary/verified_excerpts/*.md",
    "main/10_student/profile/profile.md",
    "main/10_student/profile/learning_path.md",
    "main/10_student/profile/course_reflections.md",
    "main/30_group/*/plan.md",
    "main/00_core/t2ag_memory.md",
]


class MigrateError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: Path) -> str:
    # Decode raw bytes — never use universal-newline translation (Windows CRLF).
    return path.read_bytes().decode("utf-8")


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    # verify roundtrip
    if tmp.read_bytes() != data:
        raise MigrateError(f"atomic write verify failed: {tmp}")
    os.replace(tmp, path)


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def manifest_digest(rows: list[dict[str, Any]]) -> str:
    return sha256_text(canonical_json(rows))


def path_manifest(repo: Path, relative_paths: Iterable[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for rel in sorted(set(relative_paths)):
        path = repo / rel
        if path.is_dir():
            rows.append(
                {
                    "path": rel,
                    "kind": "tree",
                    "sha256": txn.sha256_tree(path),
                }
            )
        elif path.is_file():
            rows.append(
                {
                    "path": rel,
                    "kind": "file",
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        else:
            rows.append({"path": rel, "kind": "absent", "sha256": None})
    return {"rows": rows, "sha256": manifest_digest(rows)}


def executor_source_manifest(main_root: Path) -> dict[str, Any]:
    workspace = main_root.parent
    skeleton = workspace / "t2ag-skeleton"
    selected = {
        "main/00_core/learning_activity_model.md",
        "main/50_playbook/validation_flow.md",
        "main/50_playbook/naming_conventions.md",
        "main/40_course/_templates/course/activity_ledger.md.template",
        "main/40_course/_templates/course/progress.md.template",
        "main/40_course/_templates/course/lessons/lessonNN/lessonNN.md.template",
    }
    tool_names = {
        "activity_ledger.py",
        "activity_transaction.py",
        "activity_close.py",
        "activity_lifecycle.py",
        "migrate_022_activity_close.py",
        "t2ag_activity.py",
        "t2ag_context.py",
        "t2ag_doctor.py",
        "t2ag_state_refresh.py",
        "sync_lite.py",
        "campaign_receipt.py",
        "evidence_runner.py",
        "exact_plan_kill_matrix.py",
        "exact_plan_exception_matrix.py",
        "exact_plan_shadow.py",
        "gate_matrix.py",
        "occurrence_classify.py",
        "contract_test_support.py",
        "migration_test_support.py",
        "test_runtime_contracts.py",
        "test_activity_contracts.py",
        "test_release_contracts.py",
        "test_legacy_migrations.py",
        "test_dependencies.json",
        "t2ag_test.py",
        "validation_control.py",
        "validation_workflow.json",
        "test_distribution_foundation.py",
        "test_context_packet.py",
        "test_021_closeout.py",
        "scenarios/__init__.py",
        "scenarios/release_reading_bridge_saga.py",
        "test_022_activity_close.py",
        "test_022_close_roundtrip.py",
        "test_022_doctor_postcheck.py",
        "test_022_kill_recover.py",
        "test_022_lifecycle_runtime.py",
        "test_022_migration.py",
        "test_022_transaction.py",
        "test_release_receipts.py",
        "test_release_evidence.py",
        "test_release_gates.py",
        "test_release_fault_contracts.py",
        "test_release_shadow_contracts.py",
        "scenarios/release_shadow_apply.py",
    }
    selected.update(f"main/70_tools/{name}" for name in tool_names)
    template_root = main_root / "main/40_course/_templates/course/exercises/exerciseNN"
    if template_root.is_dir():
        selected.update(
            path.relative_to(main_root).as_posix()
            for path in template_root.rglob("*")
            if path.is_file()
        )
    records: list[dict[str, Any]] = []
    for label, repo in (("main", main_root), ("skeleton", skeleton)):
        if not repo.is_dir():
            records.append({"repo": label, "status": "absent"})
            continue
        manifest = path_manifest(repo, selected)
        for row in manifest["rows"]:
            records.append({"repo": label, **row})
    return {"rows": records, "sha256": manifest_digest(records)}


def repository_binding(repo: Path) -> dict[str, Any]:
    if not repo.is_dir():
        return {"present": False}
    return {
        "present": True,
        "head": campaign.git(repo, "rev-parse", "HEAD"),
        "tree": campaign.git(repo, "show", "-s", "--format=%T", "HEAD"),
        "worktree_manifest_sha256": campaign.worktree_manifest_sha(repo),
    }


def candidate_overlay_manifest(repo: Path) -> dict[str, Any]:
    """Bind every dirty candidate path without traversing ignored/protected trees."""
    porcelain = campaign.git(repo, "status", "--porcelain=v1", "-uall")
    rows: list[dict[str, Any]] = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        rel = line[3:]
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        rel = rel.strip().strip('"').replace("\\", "/")
        if rel == ".activity_txn" or rel.startswith(".activity_txn/"):
            continue
        path = repo / rel
        if path.is_file():
            rows.append(
                {
                    "path": rel,
                    "status": status,
                    "kind": "file",
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        elif path.is_dir():
            rows.append(
                {
                    "path": rel,
                    "status": status,
                    "kind": "tree",
                    "sha256": txn.sha256_tree(path),
                }
            )
        else:
            rows.append(
                {
                    "path": rel,
                    "status": status,
                    "kind": "absent",
                    "sha256": None,
                }
            )
    rows.sort(key=lambda row: (row["path"], row["status"]))
    return {"rows": rows, "sha256": manifest_digest(rows)}


def unaffected_overlay_rows(
    manifest: dict[str, Any], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    affected: set[str] = set(plan["expected_head"])
    for source, move in plan.get("move_tree_hashes", {}).items():
        affected.add(source)
        affected.add(move["target"])

    def touched(path: str) -> bool:
        return any(path == root or path.startswith(root.rstrip("/") + "/") for root in affected)

    return [row for row in manifest.get("rows") or [] if not touched(row["path"])]


def frontmatter_split(text: str) -> tuple[dict[str, str], str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        return {}, "", text
    meta: dict[str, str] = {}
    order: list[str] = []
    for line in match.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        meta[key] = value.strip()
        order.append(key)
    return meta, "\n".join(order), text[match.end() :]


def rebuild_frontmatter(meta: dict[str, str], preferred_order: Iterable[str] | None = None) -> str:
    order: list[str] = []
    if preferred_order:
        for key in preferred_order:
            if key in meta and key not in order:
                order.append(key)
    for key in meta:
        if key not in order:
            order.append(key)
    lines = [f"{key}: {meta[key]}" for key in order]
    return "---\n" + "\n".join(lines) + "\n---\n"


def parse_list_field(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip("'\"") for part in inner.split(",")]
    return [raw]


def format_list_field(values: list[str]) -> str:
    return "[" + ", ".join(values) + "]"


def map_id(value: str, aliases: dict[str, str]) -> str:
    return aliases.get(value, value)


def map_ids_in_list_field(raw: str, aliases: dict[str, str]) -> str:
    values = [map_id(v, aliases) for v in parse_list_field(raw)]
    return format_list_field(values)


def strip_activity_status_from_main_carrier(text: str, *, filename: str) -> str:
    """Only lessonNN.md / exercise.md may lose Activity status."""
    if filename not in {"exercise.md"} and not re.fullmatch(r"lesson\d+\.md", filename):
        return text
    meta, _, body = frontmatter_split(text)
    if "status" not in meta:
        return text
    # keep order minus status
    order = [k for k in meta if k != "status"]
    del meta["status"]
    return rebuild_frontmatter(meta, order) + body


def rewrite_structured_canonical(
    text: str,
    *,
    filename: str,
    path_posix: str,
    aliases: dict[str, str],
    path_rewrites: list[tuple[str, str]],
) -> str:
    """Rewrite structured fields and pure path targets; keep free prose IDs."""
    meta, _order, body = frontmatter_split(text)

    changed = False
    # frontmatter structured keys
    for key in ("exercise_id", "current_activity_id", "unit_id"):
        if key in meta and meta[key] in aliases:
            meta[key] = aliases[meta[key]]
            changed = True
    for key in ("problem_ids", "source_order", "teaching_sequence", "exercise_ids"):
        if key in meta:
            new_val = map_ids_in_list_field(meta[key], aliases)
            if new_val != meta[key]:
                meta[key] = new_val
                changed = True
    if "resume_path" in meta:
        for old, new in path_rewrites:
            if old in meta["resume_path"]:
                meta["resume_path"] = meta["resume_path"].replace(old, new)
                changed = True

    # Problem section headings are structural IDs in the problem set, the
    # durable textbook source and Attempt/Review carriers.  Narrative mentions
    # elsewhere remain byte-for-byte evidence.
    new_body = body
    structural_problem_headings = (
        filename in {"problems.md", "attempt.md"}
        or bool(re.fullmatch(r"RV\d{4}\.md", filename))
        or "/book/primary/verified_excerpts/" in f"/{path_posix}"
    )
    if structural_problem_headings:
        def repl_header(match: re.Match[str]) -> str:
            legacy = match.group(1)
            return f"## {aliases.get(legacy, legacy)}"

        new_body2 = re.sub(r"(?m)^##\s+(U\d{4}-Q\d{3})\s*$", repl_header, new_body)
        if new_body2 != new_body:
            new_body = new_body2
            changed = True
    if filename == "problems.md":
        # This exact bullet is a machine field; prose uses are preserved.
        def repl_bullet(match: re.Match[str]) -> str:
            legacy = match.group(1)
            return f"- 题号：{aliases.get(legacy, legacy)}"

        new_body2 = re.sub(r"(?m)^-\s*题号：\s*(U\d{4}-Q\d{3})\s*$", repl_bullet, new_body)
        if new_body2 != new_body:
            new_body = new_body2
            changed = True

    # activity_map table cells: exact token U1101 in exercise_ids column rows
    if filename == "activity_map.md":
        for legacy, canonical in aliases.items():
            if re.fullmatch(r"U\d{4}", legacy):
                # only whole-cell-ish replacements in table rows
                pattern = rf"(?m)(\|\s*){re.escape(legacy)}(\s*\|)"
                new_body2 = re.sub(pattern, rf"\1{canonical}\2", new_body)
                if new_body2 != new_body:
                    new_body = new_body2
                    changed = True
        new_body2 = new_body.replace("`U1101`", "`exercise01`").replace(
            "U1101/exercise.md", "exercise01/exercise.md"
        )
        if new_body2 != new_body:
            new_body = new_body2
            changed = True

    if filename == "exercise.md":
        def repl_current_problem(match: re.Match[str]) -> str:
            legacy = match.group(2)
            return f"{match.group(1)}{aliases.get(legacy, legacy)}"

        new_body2 = re.sub(
            r"(?m)^(-\s*当前题目[：:]\s*)(U\d{4}-Q\d{3})\s*$",
            repl_current_problem,
            new_body,
        )
        if new_body2 != new_body:
            new_body = new_body2
            changed = True

    # Active human/index pointers use an exact structural spelling.  Do not
    # replace free prose U1101 occurrences.
    if filename in {"t2ag_memory.md", "plan.md"}:
        new_body2 = re.sub(r"\bexercise:\s*U1101\b", "exercise: exercise01", new_body)
        if new_body2 != new_body:
            new_body = new_body2
            changed = True
    if filename == "t2ag_memory.md":
        new_body2 = re.sub(
            r"(?m)^(- \*\*学到哪\*\*：\S+\s+exercise\s+)U1101(?=，)",
            r"\1exercise01",
            new_body,
        )
        new_body2 = re.sub(
            r"(?m)^\| Lesson 上下文 \| [^|]* \| [^|]* \|$",
            "| Lesson 上下文 | 无 | — |",
            new_body2,
        )
        if new_body2 != new_body:
            new_body = new_body2
            changed = True
    if filename == "course.md":
        new_body2 = re.sub(r"(\|\s*)`U1101`(\s*\|)", r"\1`exercise01`\2", new_body)
        if new_body2 != new_body:
            new_body = new_body2
            changed = True

    # pure path rewrites in body (links / resume paths), not bare U1101-Q prose
    for old, new in path_rewrites:
        if old in new_body:
            new_body = new_body.replace(old, new)
            changed = True

    if not changed and new_body == body:
        return text
    if not meta:
        return new_body
    order = list(meta.keys())
    # preserve original key order from text
    orig_meta, _, _ = frontmatter_split(text)
    order = list(orig_meta.keys())
    # drop status only for main carriers
    if filename == "exercise.md" or re.fullmatch(r"lesson\d+\.md", filename or ""):
        if "status" in meta:
            del meta["status"]
            order = [k for k in order if k != "status"]
    return rebuild_frontmatter(meta, order) + new_body


def rewrite_progress_preserve_position(
    text: str,
    *,
    updates: dict[str, str],
    path_rewrites: list[tuple[str, str]],
    aliases: dict[str, str],
) -> str:
    meta, _, body = frontmatter_split(text)
    if not meta:
        raise MigrateError("progress missing frontmatter")
    order = list(meta.keys())
    meta.pop("current_lesson", None)
    meta.pop("truth_source", None)
    order = [k for k in order if k != "current_lesson"]
    order = [k for k in order if k != "truth_source"]
    if meta.get("truth_source") == "true" or "truth_scope" in updates:
        meta["truth_scope"] = updates.get(
            "truth_scope", "course_lifecycle,course_frontend,activity_position"
        )
        if "truth_scope" not in order:
            order.append("truth_scope")
    # preserve activity_position when keeping a real activity foreground;
    # when migrating to current none, force between_activities (CR-016).
    preserved_position = meta.get("activity_position")
    for key in (
        "current_activity",
        "current_activity_id",
        "resume_path",
        "next_action_kind",
        "next_activity_type",
        "next_activity_id",
    ):
        if key in updates:
            meta[key] = updates[key]
            if key not in order:
                order.append(key)
    if updates.get("current_activity") == "none":
        meta["activity_position"] = "between_activities"
        if "activity_position" not in order:
            order.append("activity_position")
    elif preserved_position is not None:
        meta["activity_position"] = preserved_position
    # map ids in current fields
    if meta.get("current_activity_id") in aliases:
        meta["current_activity_id"] = aliases[meta["current_activity_id"]]
    for old, new in path_rewrites:
        if "resume_path" in meta:
            meta["resume_path"] = meta["resume_path"].replace(old, new)
    # body: only path rewrites for links, not prose U1101-Q
    new_body = body
    for old, new in path_rewrites:
        new_body = new_body.replace(old, new)
    kind = meta.get("next_action_kind", "none")
    next_type = meta.get("next_activity_type", "none")
    next_id = meta.get("next_activity_id", "none")
    if kind in {"resume", "confirm_close", "start_activity"}:
        summary = f"{kind} {next_type}:{next_id}；以结构化 next_action_* 字段为准。"
    elif kind == "choose_activity":
        summary = "从多个可用活动中选择下一项；以结构化 next_action_* 字段为准。"
    else:
        summary = "当前没有自动选择的下一活动；以结构化 next_action_* 字段为准。"
    next_pattern = re.compile(
        r"(?ms)^-\s+\*\*(?:下一步计划|下一步|下次第一件事)\*\*[：:].*?"
        r"(?=^-\s+\*\*|^##\s|\Z)"
    )
    if next_pattern.search(new_body):
        new_body = next_pattern.sub(
            f"- **下一步计划**：{summary}\n", new_body, count=1
        )
    return rebuild_frontmatter(meta, order) + new_body


PROFILE_PREF_DEFAULTS = {
    "lesson_actual_review": "on",
    "lesson_student_feedback": "on",
    "lesson_knowledge_absorption": "on",
    "exercise_problem_review": "on",
    "exercise_knowledge_mastery": "on",
}


def rewrite_profile_preferences(text: str, *, recorded_at: str) -> str:
    """Initialize the real 0.2.1 instance's 0.2.2 preference contract."""
    meta, _, body = frontmatter_split(text)
    if not meta:
        raise MigrateError("profile missing frontmatter")
    order = list(meta)
    additions = {
        "activity_close_preference_schema": "activity_close_preferences.v1",
        "activity_close_preferences_initialized_at": meta.get(
            "activity_close_preferences_initialized_at", recorded_at
        ),
        "activity_close_first_prompt_status": meta.get(
            "activity_close_first_prompt_status", "pending"
        ),
        "activity_close_first_prompt_at": meta.get(
            "activity_close_first_prompt_at", "none"
        ),
        "learning_timezone": meta.get("learning_timezone", "Asia/Singapore"),
        "learning_day_cutoff": meta.get("learning_day_cutoff", "04:00"),
        **{
            key: meta.get(key, value)
            for key, value in PROFILE_PREF_DEFAULTS.items()
        },
    }
    for key, value in additions.items():
        meta[key] = value
        if key not in order:
            order.append(key)
    meta["updated"] = recorded_at[:10]
    return rebuild_frontmatter(meta, order) + body


@dataclass
class ActivityPlan:
    course_id: str
    activity_type: str
    activity_id: str
    observed_state: str
    source_paths: list[str] = field(default_factory=list)
    binding_status: str = "bound"
    binding_reason: str = ""
    content_group_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def discover_course(root: Path, course_id: str) -> dict[str, Any]:
    course_root = root / "main" / "40_course" / course_id
    activities: list[ActivityPlan] = []
    path_ops: list[dict[str, str]] = []
    aliases: dict[str, str] = {}
    notes: list[str] = []
    progress_updates: dict[str, str] = {
        "truth_scope": "course_lifecycle,course_frontend,activity_position",
    }
    if not course_root.is_dir():
        return {
            "course_id": course_id,
            "activities": [],
            "path_ops": [],
            "aliases": [],
            "progress_updates": progress_updates,
            "empty_ledger": True,
            "notes": ["course dir missing"],
        }

    progress = course_root / "progress.md"
    progress_meta: dict[str, str] = {}
    if progress.is_file():
        progress_meta, _, _ = frontmatter_split(read_text(progress))
    lifecycle = progress_meta.get("lifecycle_status", "")

    existing_ledger = course_root / "activity_ledger.md"
    if existing_ledger.is_file():
        existing_doc = ledger.parse_ledger_text(read_text(existing_ledger))
        errors = existing_doc.validate()
        if errors:
            raise MigrateError(f"existing ledger invalid for {course_id}: {errors}")
        for alias in existing_doc.aliases:
            legacy_id = str(alias.get("legacy_id") or "")
            canonical_id = str(alias.get("canonical_id") or "")
            if legacy_id and canonical_id:
                aliases[legacy_id] = canonical_id

    lessons_dir = course_root / "lessons"
    if lessons_dir.is_dir():
        for lesson_dir in sorted(p for p in lessons_dir.iterdir() if p.is_dir()):
            lesson_md = lesson_dir / f"{lesson_dir.name}.md"
            if not lesson_md.is_file():
                continue
            meta, _, _ = frontmatter_split(read_text(lesson_md))
            state = meta.get("status") or "ongoing"
            if state not in ledger.ACTIVITY_STATES:
                state = "ongoing"
            cgs = parse_list_field(meta.get("content_group_ids"))
            activities.append(
                ActivityPlan(
                    course_id=course_id,
                    activity_type="lesson",
                    activity_id=lesson_dir.name,
                    observed_state=state,
                    source_paths=[
                        lesson_md.relative_to(root).as_posix()
                    ],
                    binding_status="bound" if cgs else "unbound",
                    binding_reason="" if cgs else "no content_group_ids",
                    content_group_ids=cgs,
                    notes=["strip only lesson status field"],
                )
            )

    exercises_dir = course_root / "exercises"
    if exercises_dir.is_dir():
        for ex_dir in sorted(p for p in exercises_dir.iterdir() if p.is_dir()):
            name = ex_dir.name
            if name in {"assets", "attempts", "reviews"}:
                continue
            if not (
                ledger.LEGACY_EXERCISE_RE.match(name)
                or ledger.EXERCISE_ID_RE.match(name)
            ):
                continue
            exercise_md = ex_dir / "exercise.md"
            meta: dict[str, str] = {}
            if exercise_md.is_file():
                meta, _, _ = frontmatter_split(read_text(exercise_md))
            state = meta.get("status") or "ongoing"
            if state not in ledger.ACTIVITY_STATES:
                state = "ongoing"
            cgs = parse_list_field(meta.get("content_group_ids"))
            if ledger.LEGACY_EXERCISE_RE.match(name):
                if name != "U1101":
                    raise MigrateError(f"unsupported legacy exercise without mapping: {name}")
                canonical = "exercise01"
                rel_old = f"main/40_course/{course_id}/exercises/{name}"
                rel_new = f"main/40_course/{course_id}/exercises/{canonical}"
                path_ops.append({"op": "move", "from": rel_old, "to": rel_new})
                aliases[name] = canonical
                # unique problem aliases from problems.md frontmatter lists + headers
                problems = ex_dir / "problems.md"
                found: set[str] = set()
                if problems.is_file():
                    ptext = read_text(problems)
                    pmeta, _, pbody = frontmatter_split(ptext)
                    for field_name in ("source_order", "teaching_sequence"):
                        for item in parse_list_field(pmeta.get(field_name)):
                            if re.fullmatch(rf"{name}-Q\d{{3}}", item):
                                found.add(item)
                    for match in re.finditer(
                        rf"(?m)^##\s+({name}-Q\d{{3}})\s*$", pbody
                    ):
                        found.add(match.group(1))
                for legacy_problem in sorted(found):
                    q = legacy_problem.split("-Q", 1)[1]
                    aliases[legacy_problem] = f"{canonical}-Q{q}"
                activities.append(
                    ActivityPlan(
                        course_id=course_id,
                        activity_type="exercise",
                        activity_id=canonical,
                        observed_state=state,
                        source_paths=[f"{rel_old}/exercise.md"],
                        binding_status="bound" if cgs else "unbound",
                        binding_reason="" if cgs else "exercise lacks content_group_ids",
                        content_group_ids=cgs,
                        notes=[
                            f"canonical replacement {name}->{canonical}",
                            "preserve Review/Problem status and free prose",
                        ],
                    )
                )
            else:
                activities.append(
                    ActivityPlan(
                        course_id=course_id,
                        activity_type="exercise",
                        activity_id=name,
                        observed_state=state,
                        source_paths=[
                            exercise_md.relative_to(root).as_posix()
                            if exercise_md.is_file()
                            else f"main/40_course/{course_id}/exercises/{name}"
                        ],
                        binding_status="bound" if cgs else "unbound",
                        binding_reason="" if cgs else "exercise lacks content_group_ids",
                        content_group_ids=cgs,
                    )
                )

    if course_id == "PY1001":
        for act in activities:
            if not act.content_group_ids:
                act.binding_status = "unbound"
                act.binding_reason = (
                    "PY1001 lacks valid activity_map; do not invent ContentGroup"
                )

    if (
        lifecycle == "ongoing"
        and course_id == "MATH1607H"
        and any(a.activity_id == "exercise01" for a in activities)
    ):
        progress_updates.update(
            {
                "current_activity": "exercise",
                "current_activity_id": "exercise01",
                "resume_path": "main/40_course/MATH1607H/exercises/exercise01/exercise.md",
                "next_action_kind": "resume",
                "next_activity_type": "exercise",
                "next_activity_id": "exercise01",
            }
        )
        notes.append("lesson01 remains background ongoing; foreground=exercise01")
    elif lifecycle == "ongoing" and activities:
        chosen = None
        if progress_meta:
            cur_id = progress_meta.get("current_activity_id")
            for act in activities:
                if cur_id in {act.activity_id, "U1101"}:
                    chosen = act
                    break
        if chosen is None and len(activities) == 1:
            chosen = activities[0]
        if chosen is not None:
            resume = (
                f"main/40_course/{course_id}/lessons/{chosen.activity_id}/{chosen.activity_id}.md"
                if chosen.activity_type == "lesson"
                else f"main/40_course/{course_id}/exercises/{chosen.activity_id}/exercise.md"
            )
            progress_updates.update(
                {
                    "current_activity": chosen.activity_type,
                    "current_activity_id": chosen.activity_id,
                    "resume_path": resume,
                    "next_action_kind": "resume",
                    "next_activity_type": chosen.activity_type,
                    "next_activity_id": chosen.activity_id,
                }
            )
        else:
            notes.append("frontend none")
    elif lifecycle == "ongoing":
        progress_updates.update(
            {
                "current_activity": "none",
                "current_activity_id": "none",
                "resume_path": "none",
                "next_action_kind": "none",
                "next_activity_type": "none",
                "next_activity_id": "none",
            }
        )
        notes.append("empty ledger; frontend none")
    else:
        progress_updates.update(
            {
                "current_activity": "none",
                "current_activity_id": "none",
                "resume_path": "none",
                "next_action_kind": "none",
                "next_activity_type": "none",
                "next_activity_id": "none",
            }
        )
        notes.append("non-ongoing course normalized to canonical frontend none")

    alias_list = [
        {
            "scope": "problem" if "-Q" in legacy else "activity",
            "course_id": course_id,
            "legacy_id": legacy,
            "canonical_id": canonical,
        }
        for legacy, canonical in sorted(aliases.items())
    ]
    return {
        "course_id": course_id,
        "activities": [asdict(a) for a in activities],
        "path_ops": path_ops,
        "aliases": alias_list,
        "progress_updates": progress_updates,
        "empty_ledger": len(activities) == 0,
        "notes": notes,
    }


def render_course_ledger(
    course: dict[str, Any], *, transaction_id: str, recorded_at: str
) -> str:
    if course["empty_ledger"]:
        return ledger.empty_ledger(course["course_id"])
    blocks: list[str] = []
    for index, act in enumerate(course["activities"], start=1):
        blocks.append(
            ledger.render_migration_snapshot_event(
                event_id=f"ALE-{index:06d}",
                course_id=course["course_id"],
                activity_type=act["activity_type"],
                activity_id=act["activity_id"],
                observed_state=act["observed_state"],
                recorded_at=recorded_at,
                transaction_id=transaction_id,
                observed_from_refs=act["source_paths"],
                evidence_refs=[f"migrate_022:{course['course_id']}"],
                binding_status=act["binding_status"],
                binding_reason=act["binding_reason"],
                content_group_ids=act["content_group_ids"],
            )
        )
    aliases_md = "_none_\n"
    if course["aliases"]:
        parts = []
        for alias in course["aliases"]:
            parts.append(
                "### alias {legacy_id}\n"
                "scope: {scope}\n"
                "course_id: {course_id}\n"
                "legacy_id: {legacy_id}\n"
                "canonical_id: {canonical_id}\n".format(**alias)
            )
        aliases_md = "\n".join(parts)
    text = ledger.build_ledger_with_events(
        course["course_id"], "\n".join(blocks), aliases_markdown=aliases_md
    )
    errors = ledger.parse_ledger_text(text).validate()
    if errors:
        raise MigrateError(f"ledger invalid for {course['course_id']}: {errors}")
    return text


def collect_active_reference_paths(root: Path) -> list[str]:
    found: set[str] = set()
    for pattern in ACTIVE_REF_GLOBS:
        for path in root.glob(pattern):
            if path.is_file():
                found.add(path.relative_to(root).as_posix())
    return sorted(found)


# Injectable clock for tests only; production uses real timezone-aware UTC.
_CLOCK = None


def set_clock(fn) -> None:
    global _CLOCK
    _CLOCK = fn


def now_tz() -> str:
    if _CLOCK is not None:
        return _CLOCK()
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_write_set(root: Path, *, recorded_at: str | None = None) -> dict[str, Any]:
    """Build complete plan content. recorded_at must be real tz time (or injected clock)."""
    courses = [discover_course(root, cid) for cid in COURSES]
    seed_obj = {
        "courses": courses,
        "root_name": root.name,
    }
    seed = sha256_text(canonical_json(seed_obj))
    recorded_at = recorded_at or now_tz()
    transaction_id = f"MIG022-{sha256_text(seed + '|' + recorded_at)[:16]}"

    global_aliases: dict[str, str] = {}
    path_rewrites: list[tuple[str, str]] = []
    for course in courses:
        for alias in course["aliases"]:
            leg = alias["legacy_id"]
            can = alias["canonical_id"]
            if leg in global_aliases and global_aliases[leg] != can:
                raise MigrateError(f"conflicting alias {leg}")
            global_aliases[leg] = can
        for op in course["path_ops"]:
            variants = [(op["from"], op["to"])]
            marker = f"main/40_course/{course['course_id']}/"
            if op["from"].startswith(marker) and op["to"].startswith(marker):
                variants.append((op["from"][len(marker) :], op["to"][len(marker) :]))
            course_marker = f"main/40_course/"
            variants.append(
                (
                    op["from"].removeprefix(course_marker),
                    op["to"].removeprefix(course_marker),
                )
            )
            for old, new in variants:
                path_rewrites.append((old, new))
                path_rewrites.append((old + "/", new + "/"))
            path_rewrites.append(
                (Path(op["from"]).name + "/", Path(op["to"]).name + "/")
            )
    path_rewrites = list(dict.fromkeys(path_rewrites))

    # unique alias count check
    if len(global_aliases) != len(set(global_aliases)):
        raise MigrateError("duplicate aliases")

    ledgers: dict[str, str] = {}
    for course in courses:
        existing = root / f"main/40_course/{course['course_id']}/activity_ledger.md"
        if existing.is_file():
            existing_text = read_text(existing)
            errors = ledger.parse_ledger_text(existing_text).validate()
            if errors:
                raise MigrateError(
                    f"existing ledger invalid for {course['course_id']}: {errors}"
                )
            ledgers[course["course_id"]] = existing_text
        else:
            ledgers[course["course_id"]] = render_course_ledger(
                course, transaction_id=transaction_id, recorded_at=recorded_at
            )

    # proposed file contents (posix rel -> text); build fully, then emit ops once
    files: dict[str, str] = {}
    pre_hashes: dict[str, str | None] = {}
    post_hashes: dict[str, str] = {}
    move_ops: list[dict[str, str]] = []

    for course in courses:
        for op in course["path_ops"]:
            pre_hashes[op["from"]] = txn.sha256_tree(root / op["from"])
            pre_hashes[op["to"]] = None
            move_ops.append(
                {
                    "kind": "move",
                    "relative_path": op["to"],
                    "source_relative": op["from"],
                }
            )

    # ledgers
    for course in courses:
        rel = f"main/40_course/{course['course_id']}/activity_ledger.md"
        content = ledgers[course["course_id"]]
        before = sha256_file(root / rel)
        after = sha256_text(content)
        if before != after:
            files[rel] = content
            pre_hashes[rel] = before
            post_hashes[rel] = after

    # progress
    progress_full: dict[str, str] = {}
    for course in courses:
        rel = f"main/40_course/{course['course_id']}/progress.md"
        if not (root / rel).is_file():
            continue
        original = read_text(root / rel)
        updated = rewrite_progress_preserve_position(
            original,
            updates=course["progress_updates"],
            path_rewrites=path_rewrites,
            aliases=global_aliases,
        )
        progress_full[rel] = updated
        if updated != original:
            files[rel] = updated
            pre_hashes[rel] = sha256_text(original)
            post_hashes[rel] = sha256_text(updated)

    # Main's old instance gets explicit global defaults and a one-shot first
    # close prompt marker.  Skeleton retains placeholders; this transformer is
    # executed only against the real Main migration root.
    profile_rel = "main/10_student/profile/profile.md"
    profile_path = root / profile_rel
    if profile_path.is_file():
        original_profile = read_text(profile_path)
        updated_profile = rewrite_profile_preferences(
            original_profile,
            recorded_at=recorded_at,
        )
        if updated_profile != original_profile:
            files[profile_rel] = updated_profile
            pre_hashes[profile_rel] = sha256_text(original_profile)
            post_hashes[profile_rel] = sha256_text(updated_profile)

    # lessons + moved exercise tree structured rewrites
    for course in courses:
        cid = course["course_id"]
        lessons = root / "main/40_course" / cid / "lessons"
        if lessons.is_dir():
            for lesson_md in lessons.rglob("lesson*.md"):
                if not lesson_md.is_file():
                    continue
                rel = lesson_md.relative_to(root).as_posix()
                original = read_text(lesson_md)
                updated = strip_activity_status_from_main_carrier(
                    original, filename=lesson_md.name
                )
                updated = rewrite_structured_canonical(
                    updated,
                    filename=lesson_md.name,
                    path_posix=rel,
                    aliases=global_aliases,
                    path_rewrites=path_rewrites,
                )
                if updated != original:
                    files[rel] = updated
                    pre_hashes[rel] = sha256_text(original)
                    post_hashes[rel] = sha256_text(updated)

        for op in course["path_ops"]:
            old_root = root / op["from"]
            if not old_root.is_dir():
                continue
            for path in sorted(old_root.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                    continue
                rel_old = path.relative_to(root).as_posix()
                rel_new = rel_old.replace(op["from"], op["to"], 1)
                original = read_text(path)
                updated = rewrite_structured_canonical(
                    original,
                    filename=path.name,
                    path_posix=rel_new,
                    aliases=global_aliases,
                    path_rewrites=path_rewrites,
                )
                updated = strip_activity_status_from_main_carrier(
                    updated, filename=path.name
                )
                if updated != original:
                    files[rel_new] = updated
                    pre_hashes[rel_old] = sha256_text(original)
                    post_hashes[rel_new] = sha256_text(updated)

    # external active references (do not clobber progress/ledger already finalized)
    active_refs: list[dict[str, Any]] = []
    protected = set(files.keys())
    for rel in collect_active_reference_paths(root):
        if rel in protected:
            active_refs.append(
                {
                    "path": rel,
                    "pre_sha256": pre_hashes.get(rel) or sha256_file(root / rel),
                    "post_sha256": post_hashes.get(rel)
                    or sha256_text(files.get(rel, read_text(root / rel))),
                    "handled_earlier": True,
                }
            )
            continue
        path = root / rel
        original = read_text(path)
        updated = rewrite_structured_canonical(
            original,
            filename=path.name,
            path_posix=rel,
            aliases=global_aliases,
            path_rewrites=path_rewrites,
        )
        for old, new in path_rewrites:
            updated = updated.replace(old, new)
        if updated != original:
            files[rel] = updated
            pre_hashes[rel] = sha256_text(original)
            post_hashes[rel] = sha256_text(updated)
            active_refs.append(
                {
                    "path": rel,
                    "pre_sha256": pre_hashes[rel],
                    "post_sha256": post_hashes[rel],
                }
            )
        else:
            active_refs.append(
                {
                    "path": rel,
                    "pre_sha256": sha256_text(original),
                    "post_sha256": sha256_text(original),
                    "unchanged": True,
                }
            )

    # Canonicalizing the durable textbook problem headings changes its bytes.
    # Rebind each projected problems.md to that exact projected source hash in
    # the same plan; otherwise Doctor correctly detects a stale evidence pin.
    for course in courses:
        for pop in course["path_ops"]:
            problems_rel = f"{pop['to']}/problems.md"
            problems_text = files.get(problems_rel)
            if problems_text is None:
                continue
            pmeta, porder, pbody = frontmatter_split(problems_text)
            source_rel = pmeta.get("source_path", "")
            if not source_rel:
                continue
            source_text = files.get(source_rel)
            if source_text is None and (root / source_rel).is_file():
                source_text = read_text(root / source_rel)
            if source_text is None:
                raise MigrateError(f"projected textbook source missing: {source_rel}")
            projected_source_sha = sha256_text(source_text)
            if pmeta.get("source_sha256") != projected_source_sha:
                pmeta["source_sha256"] = projected_source_sha
                if "source_sha256" not in porder:
                    porder.append("source_sha256")
                problems_text = rebuild_frontmatter(pmeta, porder) + pbody
                files[problems_rel] = problems_text
                post_hashes[problems_rel] = sha256_text(problems_text)

    # Generated caches are consumers of the projected progress/profile/group
    # bytes.  Freeze their exact projected content into the same transaction;
    # otherwise a successful install would immediately leave Doctor/state
    # drift and the migration could not honestly commit.
    overrides = {root / rel: content for rel, content in files.items()}
    for course in courses:
        for move in course["path_ops"]:
            source_root = root / move["from"]
            for source in source_root.rglob("*"):
                if not source.is_file() or source.suffix.lower() in {
                    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf",
                }:
                    continue
                rel_source = source.relative_to(root).as_posix()
                rel_target = rel_source.replace(move["from"], move["to"], 1)
                target = root / rel_target
                overrides.setdefault(target, files.get(rel_target, read_text(source)))
    try:
        generated_updates = (
            state_refresh.planned_updates(root=root, overrides=overrides)
            if any(
                path.exists()
                for path in (
                    root / "main/00_core/t2ag_memory.md",
                    root / "main/10_student/profile/learning_path.md",
                    root / "main/30_group",
                )
            )
            else []
        )
    except ValueError as exc:
        raise MigrateError(f"cannot project generated state: {exc}") from exc
    for path, content in generated_updates:
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise MigrateError(f"generated state escaped root: {path}") from exc
        current = overrides.get(path)
        if current is None:
            current = read_text(path)
        if content == current:
            continue
        files[rel] = content
        pre_hashes.setdefault(rel, sha256_file(path))
        post_hashes[rel] = sha256_text(content)
        overrides[path] = content
        for ref in active_refs:
            if ref["path"] == rel:
                ref["post_sha256"] = post_hashes[rel]
                ref.pop("unchanged", None)
                ref["generated_state"] = True
                break

    def projected_rel(rel: str) -> str:
        for course in courses:
            for pop in course["path_ops"]:
                if rel == pop["from"] or rel.startswith(pop["from"] + "/"):
                    return pop["to"] + rel[len(pop["from"]) :]
        return rel

    # Bind occurrence-level attribution and prove that no legacy occurrence
    # remains active in the projected tree.  Immutable prose may remain.
    pre_occurrences = occurrence.scan_root(root)
    projected_documents: dict[str, str] = {}
    occurrence_roots = [
        root / "main/40_course",
        root / "main/10_student",
        root / "main/30_group",
        root / "main/00_core/t2ag_memory.md",
    ]
    occurrence_paths: list[Path] = []
    for occurrence_root in occurrence_roots:
        if occurrence_root.is_file():
            occurrence_paths.append(occurrence_root)
        elif occurrence_root.is_dir():
            occurrence_paths.extend(
                p for p in occurrence_root.rglob("*.md") if p.is_file()
            )
    for path in sorted(occurrence_paths):
        rel = path.relative_to(root).as_posix()
        post_rel = projected_rel(rel)
        projected_documents[post_rel] = files.get(
            post_rel, files.get(rel, read_text(path))
        )
    for rel, text in files.items():
        if rel.endswith(".md"):
            projected_documents[rel] = text
    projected_occurrences = occurrence.scan_documents(projected_documents)
    if projected_occurrences["active_occurrence_count"]:
        sample = [
            {
                "path": h["path"],
                "line": h["line"],
                "kind": h["kind"],
                "class": h["class"],
                "excerpt": h["excerpt"],
            }
            for h in projected_occurrences["hits"]
            if h["active"]
        ][:10]
        raise MigrateError(
            "projected active legacy occurrences remain: "
            + canonical_json(sample)
        )
    occurrence_active_refs: list[dict[str, Any]] = []
    active_hits_by_path: dict[str, list[dict[str, Any]]] = {}
    for hit in pre_occurrences["hits"]:
        hit["projected_path"] = projected_rel(hit["path"])
        hit["disposition"] = "canonicalized" if hit["active"] else "preserved"
        if hit["active"]:
            active_hits_by_path.setdefault(hit["path"], []).append(hit)
    for rel, hits in sorted(active_hits_by_path.items()):
        post_rel = projected_rel(rel)
        post_text = projected_documents[post_rel]
        occurrence_active_refs.append(
            {
                "path": rel,
                "projected_path": post_rel,
                "pre_sha256": sha256_file(root / rel),
                "post_sha256": sha256_text(post_text),
                "occurrence_ids": [h["occurrence_id"] for h in hits],
            }
        )

    # Full source and projected target manifests for every move.
    move_tree_hashes: dict[str, Any] = {}
    for course in courses:
        for pop in course["path_ops"]:
            source_root = root / pop["from"]
            source_rows: list[dict[str, Any]] = []
            target_rows: list[dict[str, Any]] = []
            for source_file in sorted(source_root.rglob("*")):
                if not source_file.is_file():
                    continue
                sub = source_file.relative_to(source_root).as_posix()
                old_rel = source_file.relative_to(root).as_posix()
                new_rel = f"{pop['to']}/{sub}"
                raw = source_file.read_bytes()
                post_raw = (
                    files[new_rel].encode("utf-8") if new_rel in files else raw
                )
                source_rows.append(
                    {
                        "path": old_rel,
                        "relative_path": sub,
                        "bytes": len(raw),
                        "sha256": sha256_bytes(raw),
                    }
                )
                target_rows.append(
                    {
                        "path": new_rel,
                        "relative_path": sub,
                        "bytes": len(post_raw),
                        "sha256": sha256_bytes(post_raw),
                        "changed": post_raw != raw,
                    }
                )
            def tree_digest(rows: list[dict[str, Any]]) -> str:
                digest = hashlib.sha256()
                for row in rows:
                    digest.update(row["relative_path"].encode("utf-8"))
                    digest.update(b"\0")
                    digest.update(row["sha256"].encode("ascii"))
                    digest.update(b"\n")
                return digest.hexdigest()
            move_tree_hashes[pop["from"]] = {
                "target": pop["to"],
                "source_file_count": len(source_rows),
                "source_manifest": source_rows,
                "pre_tree_sha256": tree_digest(source_rows),
                "target_file_count": len(target_rows),
                "target_manifest": target_rows,
                "post_tree_sha256": tree_digest(target_rows),
            }

    # emit ops once from final files + moves
    ops: list[dict[str, Any]] = list(move_ops)
    for rel, content in sorted(files.items()):
        ops.append({"kind": "write", "relative_path": rel, "content": content})

    expected_head: dict[str, str | None] = {}
    for op in ops:
        if op["kind"] == "move":
            expected_head[op["source_relative"]] = pre_hashes.get(op["source_relative"])
            expected_head[op["relative_path"]] = None
        else:
            rel = op["relative_path"]
            under_new = any(
                rel.startswith(pop["to"].rstrip("/") + "/") or rel == pop["to"]
                for course in courses
                for pop in course["path_ops"]
            )
            if under_new:
                expected_head[rel] = None
            else:
                expected_head[rel] = (
                    pre_hashes.get(rel)
                    if rel in pre_hashes
                    else sha256_file(root / rel)
                )

    # alias uniqueness validation via ledger docs
    for course in courses:
        doc = ledger.parse_ledger_text(ledgers[course["course_id"]])
        errs = doc.validate()
        if errs:
            raise MigrateError(f"{course['course_id']} ledger errors: {errs}")

    # Bind all watched reference files and every active occurrence file.
    for ref in active_refs:
        rel = ref["path"]
        if rel not in expected_head:
            expected_head[rel] = ref.get("pre_sha256")
    for ref in occurrence_active_refs:
        if ref["path"] not in expected_head:
            expected_head[ref["path"]] = ref["pre_sha256"]

    logical = {
        "schema": "t2ag.migrate_022_activity_close.plan.v3",
        "campaign_id": "T2AG-022-ACTIVITY-CLOSE-V2-20260804",
        "transaction_id": transaction_id,
        "recorded_at": recorded_at,
        "courses": courses,
        "aliases": [
            {"legacy_id": k, "canonical_id": v} for k, v in sorted(global_aliases.items())
        ],
        "alias_count": len(global_aliases),
        "path_rewrites": [{"from": a, "to": b} for a, b in path_rewrites],
        "summary": {
            "courses": len(courses),
            "activities": sum(len(c["activities"]) for c in courses),
            "path_ops": sum(len(c["path_ops"]) for c in courses),
            "aliases": len(global_aliases),
            "write_ops": sum(1 for o in ops if o["kind"] == "write"),
            "move_ops": sum(1 for o in ops if o["kind"] == "move"),
        },
        "progress_full": progress_full,
        "ledgers": ledgers,
        "ledger_sha256": {k: sha256_text(v) for k, v in ledgers.items()},
        "files": files,
        "file_sha256": {k: sha256_text(v) for k, v in files.items()},
        "pre_hashes": pre_hashes,
        "post_hashes": post_hashes,
        "reference_files": active_refs,
        "active_references": occurrence_active_refs,
        "occurrence_report": pre_occurrences,
        "projected_occurrence_report": projected_occurrences,
        "occurrence_closure": {
            "active_occurrences_bound": (
                f"{pre_occurrences['active_occurrence_count']}/"
                f"{pre_occurrences['active_occurrence_count']}"
            ),
            "active_files_bound": (
                f"{pre_occurrences['active_file_count']}/"
                f"{pre_occurrences['active_file_count']}"
            ),
            "projected_active_occurrences": 0,
            "immutable_occurrences_preserved": sum(
                1 for h in pre_occurrences["hits"] if not h["active"]
            ),
        },
        "ops": [
            {
                "kind": o["kind"],
                "relative_path": o["relative_path"],
                "source_relative": o.get("source_relative"),
                "content_sha256": (
                    sha256_text(o["content"]) if o.get("content") is not None else None
                ),
            }
            for o in ops
        ],
        "expected_head": expected_head,
        "move_tree_hashes": move_tree_hashes,
        # internal payloads for apply (same file; UTF-8)
        "_write_contents": files,
    }
    payload_text = canonical_json(
        {k: v for k, v in logical.items() if not k.startswith("_")}
    )
    payload_sha = sha256_text(payload_text)
    logical["payload_sha256"] = payload_sha
    return logical


def materialize_plan_file(root: Path, plan_out: Path) -> dict[str, Any]:
    """Write a brand-new plan path once (temp + atomic replace). Never overwrite.

    payload_sha256 = hash(logical core without file_sha / private keys)
    file_sha256 = hash(exact durable bytes on disk)
    """
    import subprocess

    if plan_out.exists():
        raise MigrateError(
            f"plan path already exists (refuse overwrite): {plan_out}"
        )
    started = now_tz()
    plan = build_write_set(root, recorded_at=started)

    def git(fmt: str) -> str:
        run = subprocess.run(
            ["git", "show", "-s", f"--format={fmt}", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if run.returncode != 0:
            raise MigrateError(f"git failed in {root}: {run.stderr}")
        return run.stdout.strip()

    workspace = root.parent
    skeleton = workspace / "t2ag-skeleton"
    reading = Path(r"C:\Users\MikeChen\Documents\辅助阅读系统")
    plan["generator_version"] = "T2AG-022-V4"
    plan["plan_id"] = "PLAN022-" + sha256_text(
        plan["transaction_id"] + "|" + started
    )[:16]
    plan["baseline"] = {
        "main_head": git("%H") if (root / ".git").exists() else None,
        "main_tree": git("%T") if (root / ".git").exists() else None,
    }
    bindings = {
        "main": repository_binding(root),
        "skeleton": repository_binding(skeleton),
        "reading": repository_binding(reading),
        "lite_baseline_manifest_sha256": (
            "684e6f58753f4d725edc5291be26a9e1491a7d992944fea09783d84d84386081"
        ),
        "cloud_state": "paused",
    }
    executor_manifest = executor_source_manifest(root)
    overlay_manifest = candidate_overlay_manifest(root)
    # Main/Skeleton same-source records must match by relative path when both
    # repositories exist.  Missing template/tool files also count as drift.
    if skeleton.is_dir():
        main_rows = {
            row["path"]: (row.get("kind"), row.get("bytes"), row.get("sha256"))
            for row in executor_manifest["rows"]
            if row.get("repo") == "main"
        }
        skeleton_rows = {
            row["path"]: (row.get("kind"), row.get("bytes"), row.get("sha256"))
            for row in executor_manifest["rows"]
            if row.get("repo") == "skeleton"
        }
        if main_rows != skeleton_rows:
            differing = sorted(
                path
                for path in set(main_rows) | set(skeleton_rows)
                if main_rows.get(path) != skeleton_rows.get(path)
            )
            raise MigrateError(
                f"Main/Skeleton executor mirror drift: {differing[:20]}"
            )
    source_manifest = path_manifest(root, plan["expected_head"].keys())
    projected_by_path: dict[str, dict[str, Any]] = {}
    for rel, content in plan["files"].items():
        raw = content.encode("utf-8")
        projected_by_path[rel] = {
            "path": rel,
            "bytes": len(raw),
            "sha256": sha256_bytes(raw),
        }
    for move in plan["move_tree_hashes"].values():
        for row in move["target_manifest"]:
            current = projected_by_path.get(row["path"])
            if current and current["sha256"] != row["sha256"]:
                raise MigrateError(f"projected target conflict: {row['path']}")
            projected_by_path[row["path"]] = {
                "path": row["path"],
                "bytes": row["bytes"],
                "sha256": row["sha256"],
            }
    projected_rows = [projected_by_path[k] for k in sorted(projected_by_path)]
    projected_manifest = {
        "rows": projected_rows,
        "sha256": manifest_digest(projected_rows),
        "source_absent": sorted(plan["move_tree_hashes"]),
    }
    plan["bindings"] = bindings
    plan["baseline_binding_sha256"] = sha256_text(canonical_json(bindings))
    plan["worktree_manifest_sha256"] = bindings["main"].get(
        "worktree_manifest_sha256"
    )
    plan["executor_manifest"] = executor_manifest
    plan["candidate_overlay_manifest"] = overlay_manifest
    plan["executor_bundle_sha256"] = executor_manifest["sha256"]
    plan["source_tree_manifest"] = source_manifest
    plan["projected_target_manifest"] = projected_manifest
    watched = {
        "source_manifest_sha256": source_manifest["sha256"],
        "candidate_overlay_manifest_sha256": overlay_manifest["sha256"],
        "projected_manifest_sha256": projected_manifest["sha256"],
        "executor_manifest_sha256": executor_manifest["sha256"],
        "occurrence_pre_sha256": sha256_text(
            canonical_json(plan["occurrence_report"])
        ),
        "occurrence_post_sha256": sha256_text(
            canonical_json(plan["projected_occurrence_report"])
        ),
    }
    plan["watched_root_manifest"] = {
        **watched,
        "sha256": sha256_text(canonical_json(watched)),
    }
    plan["revoked_plans"] = [
        {
            "transaction_id": "MIG022-01d4214e75560949",
            "payload_sha256": "9517c4fae9977f5fe4e31695597f109a3ab1e44b23dc0162795a81e20adbf960",
            "file_sha256": "4e586f5475130ee6ba47b10e50a1b019296f7280711d28de548238e8d33fca4c",
        },
        {
            "payload_sha256": "d897e665d1f8813767c5113839127b3a3d2d70c7bd381f317118498cbe9b3e4f",
            "file_sha256": "22795758372e493b8cb285b8838055eff869aa553555662c15460abeec9d2069",
        },
        {
            "payload_sha256": "4affe7c0466ef0175e99cfc3c1c5cffad83c5072837599f4dacd6e802519a790",
            "file_sha256": "197c685ffd18c78d4f3c06ead8c76fb8b844496e014f4caa473cf81b8e35537b",
        },
    ]
    plan["plan_started_at"] = started
    plan["plan_finished_at"] = now_tz()
    write_contents = plan.get("_write_contents") or plan.get("files") or {}
    core = {
        k: v
        for k, v in plan.items()
        if not k.startswith("_") and k not in {"payload_sha256", "file_sha256"}
    }
    payload_sha = sha256_text(canonical_json(core))
    durable = {
        **core,
        "payload_sha256": payload_sha,
        "_write_contents": write_contents,
    }
    write_bytes = (canonical_json(durable) + "\n").encode("utf-8")
    if write_bytes.startswith(b"\xff\xfe") or write_bytes.startswith(b"\xfe\xff"):
        raise MigrateError("plan must not be UTF-16")
    plan_out.parent.mkdir(parents=True, exist_ok=True)
    tmp = plan_out.with_name(plan_out.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    with tmp.open("wb") as handle:
        handle.write(write_bytes)
        handle.flush()
        os.fsync(handle.fileno())
    if tmp.read_bytes() != write_bytes:
        raise MigrateError("plan temp verify failed")
    os.replace(tmp, plan_out)
    # no second write after replace
    file_sha = sha256_bytes(plan_out.read_bytes())
    loaded = json.loads(plan_out.read_bytes().decode("utf-8"))
    validate_plan_structure(loaded)
    for cid, text in loaded["ledgers"].items():
        if sha256_text(text) != loaded["ledger_sha256"][cid]:
            raise MigrateError(f"ledger sha mismatch for {cid}")
    return {
        "ok": True,
        "mode": "dry-run",
        "plan_file": str(plan_out),
        "payload_sha256": payload_sha,
        "file_sha256": file_sha,
        "transaction_id": core["transaction_id"],
        "plan_id": core["plan_id"],
        "recorded_at": core["recorded_at"],
        "summary": core["summary"],
        "alias_count": core["alias_count"],
        "aliases": core["aliases"],
        "ledger_sha256": core["ledger_sha256"],
        "baseline": core.get("baseline"),
        "writes": 0,
        "schema": core.get("schema"),
        "executor_bundle_sha256": core.get("executor_bundle_sha256"),
        "baseline_binding_sha256": core.get("baseline_binding_sha256"),
        "worktree_manifest_sha256": core.get("worktree_manifest_sha256"),
        "watched_root_manifest_sha256": core.get("watched_root_manifest", {}).get(
            "sha256"
        ),
    }


def validate_plan_structure(plan: dict[str, Any]) -> None:
    required = {
        "schema",
        "generator_version",
        "campaign_id",
        "plan_id",
        "transaction_id",
        "recorded_at",
        "plan_started_at",
        "plan_finished_at",
        "bindings",
        "baseline_binding_sha256",
        "worktree_manifest_sha256",
        "executor_manifest",
        "executor_bundle_sha256",
        "source_tree_manifest",
        "candidate_overlay_manifest",
        "projected_target_manifest",
        "watched_root_manifest",
        "occurrence_report",
        "projected_occurrence_report",
        "occurrence_closure",
        "revoked_plans",
        "expected_head",
        "ops",
        "summary",
    }
    missing = sorted(required - set(plan))
    if missing:
        raise MigrateError(f"plan missing required field(s): {missing}")
    if plan["schema"] != "t2ag.migrate_022_activity_close.plan.v3":
        raise MigrateError(f"unsupported plan schema: {plan['schema']}")
    if plan["campaign_id"] != campaign.CAMPAIGN_ID:
        raise MigrateError(f"wrong campaign: {plan['campaign_id']}")
    if plan["executor_manifest"].get("sha256") != manifest_digest(
        plan["executor_manifest"].get("rows") or []
    ):
        raise MigrateError("executor manifest digest mismatch")
    if plan["executor_bundle_sha256"] != plan["executor_manifest"]["sha256"]:
        raise MigrateError("executor bundle alias mismatch")
    if plan["candidate_overlay_manifest"].get("sha256") != manifest_digest(
        plan["candidate_overlay_manifest"].get("rows") or []
    ):
        raise MigrateError("candidate overlay manifest digest mismatch")
    if plan["baseline_binding_sha256"] != sha256_text(
        canonical_json(plan["bindings"])
    ):
        raise MigrateError("baseline binding digest mismatch")
    for name in ("source_tree_manifest", "projected_target_manifest"):
        manifest = plan[name]
        if manifest.get("sha256") != manifest_digest(manifest.get("rows") or []):
            raise MigrateError(f"{name} digest mismatch")
    watched = dict(plan["watched_root_manifest"])
    watched_sha = watched.pop("sha256", None)
    if watched_sha != sha256_text(canonical_json(watched)):
        raise MigrateError("watched-root manifest digest mismatch")
    if plan["projected_occurrence_report"].get("active_occurrence_count") != 0:
        raise MigrateError("projected active occurrence closure is not zero")
    closure = plan["occurrence_closure"]
    expected_occ = plan["occurrence_report"].get("active_occurrence_count")
    expected_files = plan["occurrence_report"].get("active_file_count")
    if closure.get("active_occurrences_bound") != f"{expected_occ}/{expected_occ}":
        raise MigrateError("active occurrence coverage mismatch")
    if closure.get("active_files_bound") != f"{expected_files}/{expected_files}":
        raise MigrateError("active file coverage mismatch")
    if len(plan["ops"]) != (
        plan["summary"].get("write_ops", 0) + plan["summary"].get("move_ops", 0)
    ):
        raise MigrateError("operation count mismatch")
    contents = plan.get("_write_contents") or {}
    if contents != plan.get("files"):
        raise MigrateError("write content envelope mismatch")
    for op in plan["ops"]:
        if op.get("kind") == "write":
            rel = op["relative_path"]
            if rel not in contents:
                raise MigrateError(f"missing write content for {rel}")
            if sha256_text(contents[rel]) != op.get("content_sha256"):
                raise MigrateError(f"write content digest mismatch for {rel}")
    for source, move in plan.get("move_tree_hashes", {}).items():
        digest = hashlib.sha256()
        for row in move.get("target_manifest") or []:
            digest.update(row["relative_path"].encode("utf-8"))
            digest.update(b"\0")
            digest.update(row["sha256"].encode("ascii"))
            digest.update(b"\n")
        if digest.hexdigest() != move.get("post_tree_sha256"):
            raise MigrateError(f"move target tree digest mismatch for {source}")
    revoked_transactions = {
        item.get("transaction_id") for item in plan["revoked_plans"]
    }
    if plan["transaction_id"] in revoked_transactions:
        raise MigrateError("current transaction is in revoked registry")


def load_plan(plan_file: Path) -> dict[str, Any]:
    raw = plan_file.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        raise MigrateError("plan file is UTF-16; refuse")
    text = raw.decode("utf-8")
    plan = json.loads(text)
    validate_plan_structure(plan)
    file_sha = sha256_bytes(raw)
    core = {k: v for k, v in plan.items() if not k.startswith("_") and k not in {"payload_sha256", "file_sha256"}}
    payload_sha = sha256_text(canonical_json(core))
    if plan.get("payload_sha256") != payload_sha:
        raise MigrateError(
            f"payload_sha256 mismatch: plan={plan.get('payload_sha256')} recomputed={payload_sha}"
        )
    return plan | {"_file_sha256": file_sha, "_raw": raw}


def validate_apply_authorization(
    root: Path,
    plan: dict[str, Any],
    *,
    authorization_receipt: Path,
    expect_authorization_sha: str,
) -> dict[str, Any]:
    production = root.resolve() == PRODUCTION_ROOT
    if production and not PRODUCTION_MIGRATION_APPLY_ENABLED:
        raise MigrateError(
            "apply blocked: 0.2.2 production migration entry is retired; "
            "a future migration requires a new exact current-turn user authorization path"
        )
    if not authorization_receipt.is_file():
        raise MigrateError("apply blocked: authorization receipt missing")
    raw = authorization_receipt.read_bytes()
    actual_sha = sha256_bytes(raw)
    if actual_sha != expect_authorization_sha:
        raise MigrateError(
            "apply blocked: authorization receipt sha mismatch: "
            f"expected={expect_authorization_sha} actual={actual_sha}"
        )
    try:
        auth = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise MigrateError(f"apply blocked: invalid authorization receipt: {exc}") from exc
    required = {
        "campaign_id",
        "phase",
        "state",
        "authorization_mode",
        "plan_id",
        "transaction_id",
        "plan_file_sha256",
        "payload_sha256",
        "d_review_sha256",
        "executor_bundle_sha256",
        "baseline_binding_sha256",
        "worktree_manifest_sha256",
        "watched_root_manifest_sha256",
        "approval_text",
        "approval_text_sha256",
        "authorization_source_sha256",
    }
    missing = sorted(required - set(auth))
    if missing:
        raise MigrateError(f"apply blocked: authorization missing {missing}")
    if auth["campaign_id"] != plan["campaign_id"]:
        raise MigrateError("apply blocked: authorization campaign mismatch")
    if auth["phase"] != "E_AUTHORIZED":
        raise MigrateError("apply blocked: receipt is not E_AUTHORIZED")
    expected_pairs = {
        "plan_id": plan["plan_id"],
        "transaction_id": plan["transaction_id"],
        "payload_sha256": plan["payload_sha256"],
        "executor_bundle_sha256": plan["executor_bundle_sha256"],
        "baseline_binding_sha256": plan["baseline_binding_sha256"],
        "worktree_manifest_sha256": plan["worktree_manifest_sha256"],
        "watched_root_manifest_sha256": plan["watched_root_manifest"]["sha256"],
    }
    for key, expected in expected_pairs.items():
        if auth.get(key) != expected:
            raise MigrateError(f"apply blocked: authorization {key} mismatch")
    if sha256_text(auth["approval_text"]) != auth["approval_text_sha256"]:
        raise MigrateError("apply blocked: approval text digest mismatch")
    mode = auth["authorization_mode"]
    transaction_plan = root / ".activity_txn" / plan["transaction_id"] / "plan.json"
    transaction_state = None
    if transaction_plan.is_file():
        transaction_state = json.loads(
            transaction_plan.read_bytes().decode("utf-8")
        ).get("status")
    projected_transaction = transaction_state in {
        "installed_pending_postcheck",
        "postcheck_passed",
        "committed",
    }
    if production:
        if (
            mode != "direct_user"
            or auth.get("state") != "direct_user_authorized"
            or auth.get("decision_actor") != "user"
            or auth.get("authorization_procedure_status") != "valid_direct_user"
        ):
            raise MigrateError(
                "apply blocked: production migration requires exact direct-user authority"
            )
        workspace = root.parent
        head_path, head_data, _ = campaign.validate_receipt_chain(workspace)
        if not head_path or head_path.resolve() != authorization_receipt.resolve():
            raise MigrateError("apply blocked: authorization receipt is not chain head")
        if head_data != auth:
            raise MigrateError("apply blocked: authorization chain payload mismatch")
        review_path = Path(auth.get("d_review_path") or "")
        source_path = Path(auth.get("authorization_source_path") or "")
        if sha256_file(review_path) != auth["d_review_sha256"]:
            raise MigrateError("apply blocked: independent review digest mismatch")
        if sha256_file(source_path) != auth["authorization_source_sha256"]:
            raise MigrateError("apply blocked: direct authorization source digest mismatch")
        live_main = repository_binding(root)
        live_skeleton = repository_binding(workspace / "t2ag-skeleton")
        live_reading = repository_binding(
            Path(r"C:\Users\MikeChen\Documents\辅助阅读系统")
        )
        live_bindings = {
            "main": live_main,
            "skeleton": live_skeleton,
            "reading": live_reading,
            "lite_baseline_manifest_sha256": plan["bindings"][
                "lite_baseline_manifest_sha256"
            ],
            "cloud_state": "paused",
        }
        if projected_transaction:
            for key in ("present", "head", "tree"):
                if live_main.get(key) != plan["bindings"]["main"].get(key):
                    raise MigrateError(f"apply blocked: projected Main {key} drift")
            if live_skeleton != plan["bindings"]["skeleton"]:
                raise MigrateError("apply blocked: Skeleton binding drift")
            if live_reading != plan["bindings"]["reading"]:
                raise MigrateError("apply blocked: Reading binding drift")
            verify_projected_state(root, plan)
            live_overlay = candidate_overlay_manifest(root)
            if unaffected_overlay_rows(live_overlay, plan) != unaffected_overlay_rows(
                plan["candidate_overlay_manifest"], plan
            ):
                raise MigrateError("apply blocked: unrelated candidate overlay drift")
        else:
            if live_bindings != plan["bindings"]:
                raise MigrateError("apply blocked: repository binding drift")
            if candidate_overlay_manifest(root) != plan["candidate_overlay_manifest"]:
                raise MigrateError("apply blocked: candidate overlay drift")
        if executor_source_manifest(root) != plan["executor_manifest"]:
            raise MigrateError("apply blocked: executor/source manifest drift")
    else:
        if mode not in {"shadow", "test"}:
            raise MigrateError("apply blocked: non-production mode must be shadow/test")
        if os.environ.get("T2AG_022_SHADOW_APPLY") != "1":
            raise MigrateError("apply blocked: shadow/test environment flag missing")
        if root.resolve() == PRODUCTION_ROOT:
            raise MigrateError("apply blocked: shadow/test mode refused on production root")
    committed = transaction_state == "committed"
    if committed:
        verify_projected_state(root, plan)
    else:
        live_source = path_manifest(root, plan["expected_head"].keys())
        if live_source != plan["source_tree_manifest"]:
            raise MigrateError("apply blocked: source/watched manifest drift")
    return auth


def verify_projected_state(root: Path, plan: dict[str, Any]) -> None:
    for row in plan["projected_target_manifest"]["rows"]:
        path = root / row["path"]
        if not path.is_file():
            raise MigrateError(f"projected file missing: {row['path']}")
        if path.stat().st_size != row["bytes"] or sha256_file(path) != row["sha256"]:
            raise MigrateError(f"projected file drift: {row['path']}")
    for source in plan["projected_target_manifest"].get("source_absent") or []:
        if (root / source).exists():
            raise MigrateError(f"projected source still exists: {source}")
    for source, move in plan.get("move_tree_hashes", {}).items():
        if txn.sha256_tree(root / move["target"]) != move["post_tree_sha256"]:
            raise MigrateError(f"projected target tree drift: {move['target']}")


def run_phase_postchecks(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("T2AG_022_FAIL_POSTCHECK"):
        raise MigrateError("injected postcheck failure")
    verify_projected_state(root, plan)
    if os.environ.get("T2AG_022_FAIL_POSTCHECK_AT") == "projected_state":
        raise MigrateError("injected postcheck failure at projected_state")
    for course_id in COURSES:
        ledger_path = root / f"main/40_course/{course_id}/activity_ledger.md"
        if not ledger_path.is_file():
            raise MigrateError(f"postcheck ledger missing: {course_id}")
        errors = ledger.parse_ledger_text(read_text(ledger_path)).validate()
        if errors:
            raise MigrateError(f"postcheck ledger invalid {course_id}: {errors}")
    if os.environ.get("T2AG_022_FAIL_POSTCHECK_AT") == "ledger_replay":
        raise MigrateError("injected postcheck failure at ledger_replay")
    fresh = build_write_set(root)
    if any(
        fresh["summary"].get(key, 0) != 0
        for key in ("path_ops", "write_ops", "move_ops")
    ):
        raise MigrateError(f"fresh planner not zero-op: {fresh['summary']}")
    if os.environ.get("T2AG_022_FAIL_POSTCHECK_AT") == "fresh_zero":
        raise MigrateError("injected postcheck failure at fresh_zero")
    commands: list[dict[str, Any]] = []
    tools = root / "main/70_tools"
    specs = [
        ("doctor", [sys.executable, "-B", str(tools / "t2ag_doctor.py")]),
        (
            "state",
            [sys.executable, "-B", str(tools / "t2ag_state_refresh.py"), "--check"],
        ),
        (
            "context",
            [
                sys.executable,
                "-B",
                str(tools / "t2ag_context.py"),
                "--course",
                "MATH1607H",
                "--format",
                "json",
            ],
        ),
        (
            "activity",
            [
                sys.executable,
                "-B",
                str(tools / "t2ag_activity.py"),
                "--course",
                "MATH1607H",
                "--intent",
                "recover",
            ],
        ),
    ]
    # Minimal transaction fixtures intentionally omit runtime consumers.
    if all(Path(argv[2]).is_file() for _, argv in specs):
        child_env = os.environ.copy()
        child_env["PYTHONIOENCODING"] = "utf-8"
        child_env["T2AG_022_EXPECT_TRANSACTION_ID"] = plan["transaction_id"]
        for name, argv in specs:
            injection = os.environ.get("T2AG_022_FAIL_POSTCHECK_AT")
            # The public failure-point name is ``recover`` because this
            # consumer exercises the recovery intent.  Keep ``activity`` as
            # an implementation-level alias so old fixture evidence remains
            # reproducible.
            accepted_injections = {name}
            if name == "activity":
                accepted_injections.add("recover")
            if injection in accepted_injections:
                raise MigrateError(f"injected postcheck failure at {injection}")
            run = subprocess.run(
                argv,
                cwd=str(root),
                env=child_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            commands.append(
                {
                    "name": name,
                    "exit": run.returncode,
                    "stdout_sha256": sha256_text(run.stdout or ""),
                    "stderr_sha256": sha256_text(run.stderr or ""),
                }
            )
            if run.returncode != 0:
                raise MigrateError(
                    f"postcheck consumer failed {name}: exit={run.returncode}: "
                    f"{(run.stdout + run.stderr)[-20000:]}"
                )
    return {"fresh_summary": fresh["summary"], "consumers": commands}


def apply_plan(
    root: Path,
    plan_file: Path,
    *,
    expect_payload_sha: str,
    expect_file_sha: str,
    confirm: str,
    authorization_receipt: Path,
    expect_authorization_sha: str,
) -> dict[str, Any]:
    if os.environ.get("T2AG_022_ALLOW_APPLY") != "1":
        raise MigrateError("apply blocked: T2AG_022_ALLOW_APPLY is not 1")
    if confirm != "E_migration_apply":
        raise MigrateError("apply blocked: --confirm must be E_migration_apply")
    plan = load_plan(plan_file)
    raw = plan.pop("_raw")
    file_sha = plan.pop("_file_sha256")
    if file_sha != expect_file_sha:
        raise MigrateError(
            f"file sha mismatch: expected {expect_file_sha} actual {file_sha}"
        )
    if plan.get("payload_sha256") != expect_payload_sha:
        raise MigrateError(
            f"payload sha mismatch: expected {expect_payload_sha} "
            f"actual {plan.get('payload_sha256')}"
        )
    authorization = validate_apply_authorization(
        root,
        plan,
        authorization_receipt=authorization_receipt,
        expect_authorization_sha=expect_authorization_sha,
    )
    if authorization.get("plan_file_sha256") != file_sha:
        raise MigrateError("apply blocked: authorization plan file sha mismatch")
    # baseline HEAD check
    if (root / ".git").exists() and plan.get("baseline", {}).get("main_head"):
        import subprocess

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ).stdout.strip()
        if head != plan["baseline"]["main_head"]:
            raise MigrateError(
                f"HEAD changed: plan={plan['baseline']['main_head']} actual={head}"
            )
    engine = txn.ActivityTransaction(root)
    plan_json = engine.plan_dir(plan["transaction_id"]) / "plan.json"
    already_committed = False
    if plan_json.is_file():
        already_committed = (
            json.loads(plan_json.read_bytes().decode("utf-8")).get("status")
            == "committed"
        )
    if not already_committed:
        live_head = engine.current_head(list(plan["expected_head"].keys()))
        for rel, want in plan["expected_head"].items():
            got = live_head.get(rel)
            if got != want:
                raise MigrateError(
                    f"pre-hash mismatch {rel}: plan={want} live={got}"
                )

    contents: dict[str, str] = plan.get("_write_contents") or plan.get("files") or {}
    file_ops: list[txn.FileOp] = []
    for op in plan["ops"]:
        if op["kind"] == "move":
            file_ops.append(
                txn.FileOp(
                    relative_path=op["relative_path"],
                    kind="move",
                    source_relative=op["source_relative"],
                )
            )
        elif op["kind"] == "write":
            rel = op["relative_path"]
            text = contents.get(rel)
            if text is None:
                raise MigrateError(f"missing write content for {rel}")
            data = text.encode("utf-8")
            if sha256_bytes(data) != op.get("content_sha256"):
                raise MigrateError(f"content sha mismatch for {rel}")
            file_ops.append(
                txn.FileOp(relative_path=rel, kind="write", content=data)
            )
    tplan = txn.TransactionPlan(
        scope_id="main",
        transaction_id=plan["transaction_id"],
        ops=file_ops,
        expected_head=plan["expected_head"],
        metadata={
            "payload_sha256": plan["payload_sha256"],
            "plan_file": str(plan_file),
        },
    )
    if already_committed:
        result = engine.apply(plan["transaction_id"])
        postcheck = run_phase_postchecks(root, plan)
        return {
            "ok": True,
            "mode": "apply",
            "status": result["status"],
            "second_apply": result["status"],
            "transaction_id": plan["transaction_id"],
            "payload_sha256": plan["payload_sha256"],
            "file_sha256": file_sha,
            "summary": plan["summary"],
            "postcheck": postcheck,
        }
    engine.stage(tplan)
    try:
        installed = engine.apply(plan["transaction_id"], defer_commit=True)
        if installed["status"] != "installed_pending_postcheck":
            raise MigrateError(f"unexpected install state: {installed['status']}")
        postcheck = run_phase_postchecks(root, plan)
        if os.environ.get("T2AG_022_FAIL_POSTCHECK_AT") == "pending_replay":
            raise MigrateError("injected postcheck failure at pending_replay")
        pending_replay = engine.apply(plan["transaction_id"], defer_commit=True)
        if pending_replay["status"] != "installed_pending_postcheck":
            raise MigrateError(
                f"pending same-plan oracle failed: {pending_replay['status']}"
            )
        if os.environ.get("T2AG_022_FAIL_POSTCHECK_AT") == "postcheck_marker":
            raise MigrateError("injected postcheck failure at postcheck_marker")
        engine.mark_postcheck_passed(plan["transaction_id"])
        if os.environ.get("T2AG_022_FAIL_POSTCHECK_AT") == "commit_marker":
            raise MigrateError("injected postcheck failure at commit_marker")
        result = engine.commit(plan["transaction_id"])
        if os.environ.get("T2AG_022_FAIL_POSTCHECK_AT") == "committed_replay":
            raise MigrateError("injected postcheck failure at committed_replay")
        again = engine.apply(plan["transaction_id"])
        if again["status"] != "already_committed_verified":
            raise MigrateError(f"committed replay failed: {again['status']}")
    except Exception as exc:
        engine.rollback(plan["transaction_id"])
        restored = path_manifest(root, plan["expected_head"].keys())
        if restored != plan["source_tree_manifest"]:
            raise MigrateError(
                f"postcheck failed and rollback did not converge: {exc}"
            ) from exc
        raise MigrateError(f"postcheck failed and rolled back: {exc}") from exc
    return {
        "ok": True,
        "mode": "apply",
        "status": result["status"],
        "second_apply": again["status"],
        "transaction_id": plan["transaction_id"],
        "payload_sha256": plan["payload_sha256"],
        "file_sha256": file_sha,
        "summary": plan["summary"],
        "postcheck": postcheck,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--plan-out", type=Path, default=None)
    parser.add_argument("--plan-file", type=Path, default=None)
    parser.add_argument("--expect-payload-sha", default="")
    parser.add_argument("--expect-file-sha", default="")
    parser.add_argument("--authorization-receipt", type=Path, default=None)
    parser.add_argument("--expect-authorization-sha", default="")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    root = (args.root or TOOLS.parents[1]).resolve()
    try:
        if args.check:
            courses = [discover_course(root, cid) for cid in COURSES]
            payload = {
                "ok": True,
                "mode": "check",
                "summary": {
                    "courses": len(courses),
                    "activities": sum(len(c["activities"]) for c in courses),
                    "aliases": sum(len(c["aliases"]) for c in courses),
                },
                "courses": courses,
            }
        elif args.dry_run:
            if not args.plan_out:
                raise MigrateError("--dry-run requires --plan-out")
            payload = materialize_plan_file(root, args.plan_out)
        else:
            if not args.plan_file:
                raise MigrateError("--apply requires --plan-file")
            if (
                not args.expect_payload_sha
                or not args.expect_file_sha
                or not args.authorization_receipt
                or not args.expect_authorization_sha
            ):
                raise MigrateError(
                    "--apply requires plan hashes and exact authorization receipt binding"
                )
            payload = apply_plan(
                root,
                args.plan_file,
                expect_payload_sha=args.expect_payload_sha,
                expect_file_sha=args.expect_file_sha,
                confirm=args.confirm,
                authorization_receipt=args.authorization_receipt.resolve(),
                expect_authorization_sha=args.expect_authorization_sha,
            )
    except Exception as exc:  # noqa: BLE001
        print(canonical_json({"ok": False, "error": str(exc)}))
        return 1
    print(canonical_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
