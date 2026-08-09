#!/usr/bin/env python3
"""T2AG A 案：从 main 全量再生 t2ag-lite（线上审查快照）。

设计（对应 2026-07-24 阶段 0 机制裁决 A）：
- 每次运行 = 整树再生，不是白名单增量补丁。
- 先清空 lite 投影内容（保留 `.git`、`.venv`、`.recovery`、`.staging`），
  再从 main 按排除清单复制。
- 半同步态在机制上不可能：lite 中不存在「main 已删而 lite 仍留」的孤儿文件。
- lite 不得反向写 main；本脚本只读 main、只写 lite。
- **前置闸门**：main 工作区必须干净（与 doctor check_release_snapshot 同义扩展到整仓
  `git status --porcelain`）。脏树再生会把「不存在于任何 commit 的中间态」投影到
  无 git 的 lite，且不可追回。`--force` 可越过并打印警告。
- **收尾核对**：对全部「应投影」文件做 SHA-256 全量比对（不抽样）；身份文件
  （lite 专用 README/AGENTS）单独列出为有意分叉。

排除（审查不需要 / 体积过大 / 环境私货）：
- 目录：.git .venv .tools .recovery .staging .agents .uploads .cache
  __pycache__ archives ATBS_3e 等
- 扩展名：PDF/EPUB/压缩包/Office 二进制/图片/可执行/编译产物/DB 等
  （图片例外见 ALLOWED_BINARY_REL 注释）
- 体积：非文本默认 >1.5MB 跳过；.md/.py/.json/.yaml 等上限 3MB
- working_pages/pages 截图页（已在 0.2.2 S3 退役，目录不再存在）

保留：
- 规则、playbook、doctor、实例 Markdown 状态、lesson 文本、cloud 文本
- main/80_interface/fable_snail.png（见 ALLOWED_BINARY_REL）
- t2ag_directory_guide.html
- lite 身份 README.md / AGENTS.md（再生后写回审查快照说明，与 main 有意不同）

用法：
  python main/70_tools/sync_lite.py                  # check-only 预演
  python main/70_tools/sync_lite.py --write          # 显式全量再生
  python main/70_tools/sync_lite.py --write --force  # 经批准从脏树再生
  python main/70_tools/sync_lite.py --write --root <工作区绝对路径>
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

FORBIDDEN_EXT = {
    ".pdf",
    ".epub",
    ".zip",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".pyd",
    ".pyc",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".ico",
    ".pptx",
    ".ppt",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".aux",
    ".log",
    ".o",
    ".obj",
    ".so",
    ".dylib",
    ".whl",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-journal",
    ".db-wal",
    ".db-shm",
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    ".tools",
    ".recovery",
    ".staging",
    ".agents",
    ".uploads",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "archives",
    "ATBS_3e",
    "node_modules",
}

MAX_FILE_BYTES = 1_500_000
MAX_TEXT_BYTES = 3_000_000
TEXT_EXT = {
    ".md",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".toml",
    ".ini",
    ".cfg",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".rs",
    ".go",
    ".java",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".ps1",
    ".bat",
    ".csv",
    ".tsv",
    ".xml",
    ".svg",
}

# 相对 main 根（或同步根）的二进制白名单。每条必须注释：是什么、为何 lite 需要。
# 例外是清单腐化的起点——新增前先问「审查是否真的缺它」。
ALLOWED_BINARY_REL: dict[str, str] = {
    # fable_snail.png：目录册 t2ag_directory_guide.html 的唯一插图资产（产品蜗牛）。
    # lite 审查界面/HTML 预览依赖它；其它 png 仍排除（教材截图/OCR 页图体积大且非规则审查所需）。
    "main/80_interface/fable_snail.png": (
        "directory-guide mascot; sole image asset for t2ag_directory_guide.html preview"
    ),
}

# 再生后由本脚本重写、与 main 有意不同的路径（不参与「应一致」哈希）。
LITE_IDENTITY_REL = frozenset({"README.md", "AGENTS.md"})
# Guide GENERATED:directory_map is rebuilt for lite tree → may differ from main (H4)
LITE_GUIDE_DIVERGE_REL = frozenset({"t2ag_directory_guide.html"})
PRESERVE_DST_TOP = frozenset({".git", ".venv", ".recovery", ".staging"})

LITE_README = """# T2AG 0.2.3 线上模型审查快照（t2ag-lite）

> **身份**：由主实例 `t2ag/` **全量再生**得到的文本优先审查快照。
> 不是空白 skeleton，不用于初始化新学生，也不得作为教学写回源。

> **产品方向**：`t2ag-skeleton/` 按可复用开源基础持续维护；个人实例不因此公开。
> 仓库根当前尚无明确开源许可证，正式对外分发前仍需单独裁决许可。

## 基线与增量

- **运行版本**：`0.2.3`（教材教学发送边界 defense-in-depth + 宿主 egress 契约；**未**宣称 FIN）
- **最近 release 资格基线**：`0.2.2`，`finalization_delta_passed` 于 2026-08-05
- **此后变更**：见 `main/00_core/t2ag_changelog.md` 顶部。
  **0.2.3 未经候选独立复审与 finalization delta，不在发布资格范围内。**

- 再生机制：A 案（`main/70_tools/sync_lite.py`）— 每次从 main 整树导出 + 排除清单
- 源实例：`../t2ag/`
- 唯一模板源：`../t2ag-skeleton/`
- 包含：系统规则、实例 Markdown 状态、课程与 lesson 文本、工具脚本、
  `docs/adr/**` 与 `docs/protocol/**` 纯文本审查闭包、
  `t2ag_directory_guide.html` 与其单一蜗牛图
- ADR/Protocol 仅为**只读审查资料**，不赋予 Lite 执行权或宿主教学硬门
- 排除：教材二进制（PDF/压缩包等）、`.venv`、`.tools`、`.git`、`.recovery`、
  缓存、二进制生成资产、DB/WAL 等；审查所需的纯文本课程材料可以保留

## 三形态基础验证内容

Doctor/测试基础结构是 Main、Skeleton、Lite 都必须携带的基础内容，包括
`doctor_contracts.md`、`test_strategy.md`、`validation_flow.md`、`t2ag_doctor.py`、
`t2ag_test.py`、`validation_control.py`、`validation_workflow.json` 与
`test_dependencies.json`。Main/Skeleton 启动只使用 `--profile runtime`；冻结候选或正式
发布才使用 `--profile release`。原子项必须先列计划并绑定 plan SHA，release 执行还要提供
登记 reason；Lite 保留这些文件供逐字节审查，但仍是只读快照，不在本目录执行 Doctor、
测试、场景或写回。

## 给线上模型的使用边界

建议按此顺序阅读：

1. `main/t2ag.md`
2. `main/00_core/t2ag_memory.md`
3. `main/10_student/profile/learning_path.md`、`main/10_student/profile/profile.md`、
   `main/20_teacher/overlay.md`
4. 当前课程、课程组与 playbook
5. 按需展开 changelog 与 problemlog

可视化浏览结构时开 `t2ag_directory_guide.html`；命名以
`main/50_playbook/naming_conventions.md` 为准。

重点查：

- 权威链与状态缓存、实例课程路径是否冲突
- 同一事实是否在多处文件重复定义
- 路径、文件命名、字段和状态机是否干净
- skeleton 通用模板与 main 实例之间是否存在不该有的分叉
- lite 是否仍混入不该上传的环境/密钥/大二进制

输出以「严重程度 + 文件/行号 + 证据 + 建议」为单元。不要在本目录执行首次启动、
教学写回、脚本依赖安装或模型下载；需要修改时先给审查建议，由本地 main/skeleton 裁决。

## 再生纪律

lite 只能由 main 再生，不是规则源。顺序固定为：

`skeleton 通用规则定稿 -> main 吸收并保留实例数据 -> sync_lite 全量再生 -> doctor`

**main 必须先 commit 落盘**（`sync_lite` 默认拒绝脏树；见 `--force`）。
不要手改 lite 后期望回写 main。半同步靠全量再生灭绝，不靠白名单补丁。
"""

LITE_AGENTS = """# t2ag-lite 0.2.3 启动说明

本目录是 **t2ag 主实例的线上审查快照**（由 `main/70_tools/sync_lite.py` 全量再生）。

## 规则

- **只读审查**：不要教学写回、不要改进度真相源、不要装依赖、不要当 skeleton 用。
- 入口仍可读 `main/t2ag.md` 与 `main/00_core/t2ag_memory.md` 以理解结构。
- 发现的问题以审查报告返回本地；由 main/skeleton 裁决后落盘，再再生 lite。

## 三形态基础内容

- Doctor/测试基础结构必须与 Main、Skeleton 对齐：runtime 是启动档，release 是发布审计档。
- `--profile runtime` 与 `--profile release` 的代码、流程树、控制文件和依赖清单均保留供
  只读审查；`validation_workflow.json` 机械约束计划 SHA、release reason 和普通预算。
- **不得在 Lite 执行** Doctor、测试选择器、release scenario 或任何写回；执行责任只在
  本地 Main/Skeleton。

## 版本

- 与源 main 对齐；当前运行版本为 `0.2.3`，权威版本号见 `main/t2ag.md`。
- **基线与增量**：最近 release 资格基线为 `0.2.2` / `finalization_delta_passed`（2026-08-05）；
  运行版本 `0.2.3` 未宣称 FIN。此后变更见 `main/00_core/t2ag_changelog.md` 顶部；
  未经候选独立复审与 finalization delta 的条目不在发布资格范围内。
- 本文件在每次 `sync_lite.py` 运行时重写为审查身份说明。
"""


def is_allowed_binary(rel: Path, tree_prefix: str = "") -> bool:
    """Match ALLOWED_BINARY_REL using path relative to t2ag root when possible."""
    rel_posix = rel.as_posix()
    candidates = [rel_posix]
    if tree_prefix:
        candidates.append(f"{tree_prefix.rstrip('/')}/{rel_posix}")
    return any(c in ALLOWED_BINARY_REL for c in candidates)


def should_skip_file(path: Path, rel: Path, tree_prefix: str = "") -> bool:
    """rel 相对于同步根（main/ 或 cloud/ 或 assets/ 或仓根单文件）。"""
    ext = path.suffix.lower()
    parts = rel.parts
    for p in parts:
        if p in SKIP_DIR_NAMES:
            return True
        if p == "pages" and "working_pages" in parts:  # Post-S3 defense（目录已退役，防御性 skip）
            return True
    if is_allowed_binary(rel, tree_prefix):
        return False
    if ext in FORBIDDEN_EXT:
        return True
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if "primary" in parts and ext in {".txt", ".html", ".htm"} and size > MAX_FILE_BYTES:
        return True
    if size > MAX_FILE_BYTES:
        if ext in TEXT_EXT:
            return size > MAX_TEXT_BYTES
        return True
    return False

def require_main_clean(src: Path, force: bool) -> None:
    """main 工作区必须干净，否则拒绝（--force 可越过）。

    脏树探测与 doctor.check_release_snapshot 共用 git_status_porcelain
    （全树 vs 发布相关 pathspec 由调用方决定）。
    """
    git_dir = src / ".git"
    if not git_dir.exists():
        print("WARN: main has no .git; skip clean-tree gate", file=sys.stderr)
        return
    try:
        # Co-located import: same 70_tools/ when run as script.
        from t2ag_doctor import git_status_porcelain  # type: ignore
    except ImportError:
        git_status_porcelain = None  # type: ignore
    if git_status_porcelain is not None:
        try:
            dirty = git_status_porcelain(src)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    else:
        run = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=src,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if run.returncode != 0:
            print(
                f"ERROR: git status failed in {src}: {run.stderr.strip()}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        dirty = run.stdout.strip()
    if not dirty:
        print("gate: main working tree clean OK")
        return
    msg = (
        "REFUSE: main working tree is dirty; refuse to project an uncommitted "
        "intermediate state onto git-less lite.\n"
        "Commit (or stash) main first, then re-run. Override: --force\n"
        "--- git status --porcelain ---\n"
        f"{dirty}"
    )
    if force:
        rows = dirty.splitlines()
        preview = "\n".join(rows[:25])
        suffix = f"\n... ({len(rows) - 25} more)" if len(rows) > 25 else ""
        print(
            "WARN: --force: operating from dirty main\n"
            + preview + suffix,
            file=sys.stderr,
        )
        return
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def clear_lite_tree(dst: Path, dry_run: bool) -> int:
    if dst.name != "t2ag-lite":
        raise SystemExit(f"REFUSE: destination must be named t2ag-lite, got {dst}")
    removed = 0
    if not dst.exists():
        if not dry_run:
            dst.mkdir(parents=True)
        return 0
    for child in list(dst.iterdir()):
        if child.name in PRESERVE_DST_TOP:
            print(f"preserve destination-local: {child.name}")
            continue
        if dry_run:
            removed += 1
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1
    return removed


def iter_projected_files(
    src_root: Path, tree_prefix: str = ""
) -> list[tuple[Path, Path]]:
    """Return (absolute src file, rel path under src_root) that should be copied."""
    out: list[tuple[Path, Path]] = []
    if not src_root.exists():
        return out
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(src_root)
        if should_skip_file(src, rel, tree_prefix):
            continue
        out.append((src, rel))
    return out


def copy_filtered(
    src_root: Path, dst_root: Path, dry_run: bool, tree_prefix: str = ""
) -> tuple[int, int]:
    copied = skipped = 0
    if not src_root.exists():
        return 0, 0
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(src_root)
        if should_skip_file(src, rel, tree_prefix):
            skipped += 1
            continue
        dst = dst_root / rel
        if dry_run:
            copied += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied, skipped

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_projection_manifest(src: Path) -> dict[str, tuple[int, int, str]]:
    """Exact stable manifest of files eligible for the Lite projection."""
    result: dict[str, tuple[int, int, str]] = {}
    for label, source, _target in projection_manifest(src, src):
        info = source.stat()
        result[label] = (
            stat.S_IMODE(info.st_mode),
            info.st_size,
            sha256_file(source),
        )
    return result


def lite_content_manifest(dst: Path) -> dict[str, tuple[int, int, str]]:
    result: dict[str, tuple[int, int, str]] = {}
    if not dst.exists():
        return result
    for path in sorted(dst.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(dst)
        if relative.parts and relative.parts[0] in PRESERVE_DST_TOP:
            continue
        info = path.stat()
        result[relative.as_posix()] = (
            stat.S_IMODE(info.st_mode),
            info.st_size,
            sha256_file(path),
        )
    return result


def is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def validate_destination(workspace: Path, src: Path, dst: Path) -> None:
    workspace = workspace.resolve()
    expected = workspace / "t2ag-lite"
    if dst.absolute() != expected or dst.name != "t2ag-lite":
        raise RuntimeError(f"destination must be exact workspace t2ag-lite: {dst}")
    if is_reparse(workspace) or is_reparse(src) or is_reparse(dst):
        raise RuntimeError("workspace/Main/Lite symlink or reparse point refused")
    if dst.exists() and src.resolve() == dst.resolve():
        raise RuntimeError("Main and Lite resolve to the same directory")


def require_distinct_file_ids(*paths: Path) -> None:
    existing = [path for path in paths if path.exists()]
    for index, left in enumerate(existing):
        for right in existing[index + 1:]:
            try:
                same = os.path.samefile(left, right)
            except OSError:
                same = False
            if same:
                raise RuntimeError(
                    f"temporary/candidate/rollback aliases protected tree: {left} == {right}"
                )


def inject_failure(point: str) -> None:
    if os.environ.get("T2AG_SYNC_LITE_FAIL_AT") == point:
        raise RuntimeError(f"injected failure at {point}")


def verify_projection(
    src: Path,
    dst: Path,
    projected: list[tuple[str, Path, Path]],
) -> int:
    """Full hash check of all projected files. projected: (label, src_file, dst_file).

    Returns number of mismatches (0 = OK).
    """
    match = missing = differ = 0
    print("--- full hash verify (projected files, no sample) ---")
    for label, s, d in sorted(projected, key=lambda x: x[0]):
        if not s.is_file():
            print(f"MISS_SRC {label}")
            missing += 1
            continue
        if not d.is_file():
            print(f"MISS_DST {label}")
            missing += 1
            continue
        hs, hd = sha256_file(s), sha256_file(d)
        if hs == hd:
            match += 1
        elif label in LITE_GUIDE_DIVERGE_REL:
            # counted separately as intentional (map rebuilt for lite)
            match += 1
            print(f"GUIDE {label}: diverge_ok (edition-local GENERATED)")
        else:
            differ += 1
            print(f"DIFFER {label}")
            print(f"  src={hs[:16]} dst={hd[:16]}")
    # intentional identity diverge
    print("--- intentional diverge (lite identity, not errors) ---")
    for rel in sorted(LITE_IDENTITY_REL):
        sp, dp = src / rel, dst / rel
        if sp.is_file() and dp.is_file():
            same = sha256_file(sp) == sha256_file(dp)
            print(f"IDENTITY {rel}: {'UNEXPECTED_MATCH' if same else 'diverge_ok'}")
        elif dp.is_file():
            print(f"IDENTITY {rel}: lite_only_ok")
        else:
            print(f"IDENTITY {rel}: missing_lite")
    print(
        f"hash_summary: match={match} differ={differ} missing={missing} "
        f"projected={len(projected)}"
    )
    if differ or missing:
        print("FAIL: projection hash verify failed", file=sys.stderr)
        return differ + missing
    print("hash_verify: projected files byte-identical to main (guide map may diverge_ok)")
    return 0


def write_identity(dst: Path, dry_run: bool) -> None:
    if dry_run:
        return
    (dst / "README.md").write_text(LITE_README, encoding="utf-8", newline="\n")
    (dst / "AGENTS.md").write_text(LITE_AGENTS, encoding="utf-8", newline="\n")


def projection_manifest(src: Path, dst: Path) -> list[tuple[str, Path, Path]]:
    projected: list[tuple[str, Path, Path]] = []
    for name in ("main", "cloud", "assets"):
        for source, rel in iter_projected_files(src / name, tree_prefix=name):
            label = f"{name}/{rel.as_posix()}"
            projected.append((label, source, dst / name / rel))
    # docs/handoffs/ — 受控投影：活跃 handoff + 宪法 §7 六份版本权威
    _project_handoffs(src, dst, projected)
    # docs/adr + docs/protocol — 只读审查闭包（文本 .md；非执行权）
    _project_decision_docs(src, dst, projected)
    for name in ("t2ag_directory_guide.html", ".gitignore"):
        source = src / name
        if source.is_file() and not should_skip_file(source, Path(name)):
            projected.append((name, source, dst / name))
    return projected


# 宪法 §7 引用的六份版本权威 handoff（无论 status，必须可校验）
_CONSTITUTION_HANDOFFS: frozenset[str] = frozenset({
    "T2AG_021_FULL_CLOSEOUT_AND_REVIEW_GOVERNANCE_WORKORDER_2026-08-04.md",
    "T2AG_021_VERSION_INDEPENDENT_REVIEW_2026-08-04.md",
    "T2AG_021_FINALIZATION_DELTA_REVIEW_2026-08-04.md",
    "T2AG_022_ACTIVITY_CLOSE_LEDGER_WORKORDER_2026-08-04.md",
    "T2AG_022_VERSION_INDEPENDENT_REVIEW_2026-08-05.md",
    "T2AG_022_FINALIZATION_DELTA_REVIEW_2026-08-05.md",
})


def _project_handoffs(
    src: Path, dst: Path, projected: list[tuple[str, Path, Path]]
) -> None:
    """Project active handoffs and constitutional references from docs/handoffs/."""
    handoff_dir = src / "docs" / "handoffs"
    if not handoff_dir.is_dir():
        return
    for path in sorted(handoff_dir.rglob("*.md")):
        if path.name.startswith("_"):
            continue  # 跳过工具脚本附件
        rel = path.relative_to(src)
        # 只投影 .md（文本可审查），跳过 backups/ 与超大文件
        if "backups" in rel.parts:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            continue
        # 宪法 §7 六份无条件投影；其余只投影带活跃状态标记的
        is_constitutional = path.name in _CONSTITUTION_HANDOFFS
        if not is_constitutional:
            # 检查 frontmatter / 首行是否有 active / in_progress 标记
            try:
                first_lines = path.read_text(encoding="utf-8")[:2000]
            except Exception:
                continue
            if not re.search(
                r"\*\*状态\*\*[：:]\s*(?:active|进行中|in.progress|方案讨论完成)",
                first_lines,
            ):
                continue
        label = rel.as_posix()
        projected.append((label, path, dst / rel))


def _project_decision_docs(
    src: Path, dst: Path, projected: list[tuple[str, Path, Path]]
) -> None:
    """Project ADR and protocol markdown for Lite review-only closure.

    Does not grant Lite execution authority or host hard gates.
    """
    for sub in ("adr", "protocol"):
        base = src / "docs" / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            rel = path.relative_to(src)
            if "backups" in rel.parts:
                continue
            if path.name.startswith("_"):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            if should_skip_file(path, rel):
                continue
            label = rel.as_posix()
            projected.append((label, path, dst / rel))


def check_current_projection(src: Path, dst: Path) -> int:
    projected = projection_manifest(src, dst)
    expected = {label for label, _, _ in projected} | set(LITE_IDENTITY_REL)
    current: set[str] = set()
    if dst.exists():
        for path in dst.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(dst)
            if rel.parts and rel.parts[0] in PRESERVE_DST_TOP:
                continue
            current.add(rel.as_posix())

    missing = sorted(expected - current)
    orphan = sorted(current - expected)
    differ: list[str] = []
    for label, source, target in projected:
        if label not in current or label in LITE_GUIDE_DIVERGE_REL:
            continue
        if sha256_file(source) != sha256_file(target):
            differ.append(label)

    identity_expected = {"README.md": LITE_README, "AGENTS.md": LITE_AGENTS}
    for label, content in identity_expected.items():
        target = dst / label
        if target.is_file() and target.read_text(encoding="utf-8") != content:
            differ.append(label)

    guide_bad = False
    guide = dst / "t2ag_directory_guide.html"
    if guide.is_file():
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        try:
            import build_guide as bg  # type: ignore

            guide_bad = bg.run(dst, write=False) != 0
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            print(f"ERROR: Lite guide check failed: {exc}", file=sys.stderr)
            guide_bad = True

    print(
        f"projection_check: expected={len(expected)} current={len(current)} "
        f"missing={len(missing)} differ={len(differ)} orphan={len(orphan)} "
        f"guide_drift={int(guide_bad)}"
    )
    for label, values in (
        ("MISSING", missing),
        ("DIFFER", sorted(set(differ))),
        ("ORPHAN", orphan),
    ):
        for value in values[:20]:
            print(f"{label} {value}")
        if len(values) > 20:
            print(f"{label} ... ({len(values) - 20} more)")
    if missing or differ or orphan or guide_bad:
        print("FAIL: Lite projection drift; rerun with --write", file=sys.stderr)
        return 1
    print("OK: Lite matches the current Main projection")
    return 0


def build_candidate(
    src: Path, candidate: Path
) -> tuple[int, int, list[tuple[str, Path, Path]]]:
    total_copied = total_skipped = 0
    for name in ("main", "cloud", "assets"):
        copied, skipped = copy_filtered(
            src / name, candidate / name, False, tree_prefix=name
        )
        total_copied += copied
        total_skipped += skipped
        print(f"tree {name}: copied={copied} skipped={skipped}")
    for name in ("t2ag_directory_guide.html", ".gitignore"):
        source = src / name
        if source.is_file() and not should_skip_file(source, Path(name)):
            shutil.copy2(source, candidate / name)
            total_copied += 1
            print(f"root file: {name}")
        elif source.is_file():
            total_skipped += 1

    # Copy projected docs/* extras (handoffs, adr, protocol) not covered by tree loops.
    projected_preview = projection_manifest(src, candidate)
    extras = 0
    for label, source, target in projected_preview:
        if label.startswith(("main/", "cloud/", "assets/")):
            continue
        if label in LITE_IDENTITY_REL or label in LITE_GUIDE_DIVERGE_REL:
            continue
        if label in {".gitignore", "t2ag_directory_guide.html"}:
            continue
        if not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        extras += 1
        total_copied += 1
    if extras:
        print(f"docs extras: copied={extras}")

    write_identity(candidate, False)
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import build_guide as bg  # type: ignore

    if bg.run(candidate, write=True):
        raise RuntimeError("build_guide returned non-zero")
    projected = projection_manifest(src, candidate)
    return total_copied, total_skipped, projected


def restore_previous_lite(
    dst: Path,
    rollback: Path,
    installed: list[Path],
    moved_old: list[Path],
) -> None:
    errors: list[str] = []
    for index, target in enumerate(reversed(installed), start=1):
        try:
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            inject_failure(f"rollback_remove:{index}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"remove {target.name}: {exc}")
    for index, old in enumerate(moved_old, start=1):
        try:
            if old.exists():
                shutil.move(str(old), str(dst / old.name))
            inject_failure(f"rollback_restore:{index}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"restore {old.name}: {exc}")
    if errors:
        residue = sorted(
            path.relative_to(dst.parent).as_posix()
            for root in (dst, rollback)
            if root.exists()
            for path in root.rglob("*")
            if path.is_file()
        )
        raise RuntimeError(
            f"Lite rollback failed: {'; '.join(errors)}; exact residue={residue}"
        )


def inherit_destination_acl(dst: Path, installed: list[Path]) -> None:
    """Make newly installed Windows entries inherit the destination ACL.

    Codex review sessions can create protected DACLs on temporary directories.
    A same-volume move preserves those DACLs, which would make the generated
    Lite unreadable to a later independent reviewer.  Reset only the newly
    installed top-level entries; destination-local preserved entries are never
    included in ``installed``.
    """
    if os.name != "nt":
        return
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise RuntimeError("SystemRoot is missing; cannot locate trusted icacls.exe")
    icacls = Path(system_root) / "System32" / "icacls.exe"
    if not icacls.is_file():
        raise RuntimeError(f"trusted icacls.exe is missing: {icacls}")
    destination = dst.resolve()
    for target in installed:
        if target.parent.resolve() != destination:
            raise RuntimeError(
                f"refusing to reset ACL outside Lite destination: {target}"
            )
        recursive = ["/T"] if target.is_dir() else []
        for operation in ("/inheritance:e", "/reset"):
            command = [str(icacls), str(target), operation, *recursive, "/Q"]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=30,
                )
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(
                    f"timed out resetting installed Lite ACL after 30s: {target} ({operation})"
                ) from error
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(
                    "failed to make installed Lite entry inherit destination ACL: "
                    f"{target} ({operation}, exit {result.returncode}): {detail}"
                )


def install_candidate(
    candidate: Path,
    dst: Path,
    rollback: Path,
) -> tuple[list[Path], list[Path]]:
    if dst.name != "t2ag-lite":
        raise RuntimeError(f"destination must be named t2ag-lite, got {dst}")
    rollback.mkdir(parents=False, exist_ok=False)
    moved_old: list[Path] = []
    installed: list[Path] = []
    dst.mkdir(parents=True, exist_ok=True)
    try:
        for index, child in enumerate(list(dst.iterdir()), start=1):
            if child.name in PRESERVE_DST_TOP:
                print(f"preserve destination-local: {child.name}")
                continue
            target = rollback / child.name
            shutil.move(str(child), str(target))
            moved_old.append(target)
            inject_failure(f"move_old:{index}")
        for index, child in enumerate(list(candidate.iterdir()), start=1):
            target = dst / child.name
            shutil.move(str(child), str(target))
            installed.append(target)
            inject_failure(f"install_new:{index}")
        inherit_destination_acl(dst, installed)
    except Exception as install_error:
        try:
            restore_previous_lite(dst, rollback, installed, moved_old)
        except Exception as rollback_error:
            raise RuntimeError(
                f"Lite install failed: {install_error}; {rollback_error}"
            ) from install_error
        raise RuntimeError(
            f"Lite install failed: {install_error}; previous Lite restored"
        ) from install_error
    return moved_old, installed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Full-regenerate t2ag-lite from t2ag (plan A)")
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="T2AC workspace root containing t2ag/ and t2ag-lite/",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Deprecated alias for the default check-only projection preview",
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="Explicitly regenerate Lite (default: check-only preview)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Allow regenerate from dirty main (prints warning; not recommended)",
    )
    args = ap.parse_args(argv)
    if args.dry_run and args.write:
        ap.error("--dry-run and --write are mutually exclusive")
    dry_run = not args.write

    script_path = Path(__file__).resolve()
    t2ag_root = script_path.parents[2]
    workspace = args.root.resolve() if args.root else t2ag_root.parent
    src = workspace / "t2ag"
    dst = workspace / "t2ag-lite"

    if not src.is_dir():
        print(f"ERROR: main missing: {src}", file=sys.stderr)
        return 1
    try:
        validate_destination(workspace, src, dst)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("plan=A full-regenerate")
    print(f"src={src}")
    print(f"dst={dst}")
    print(f"mode={'write' if args.write else 'check-only'} force={args.force}")
    print("binary_allowlist:")
    for rel, reason in sorted(ALLOWED_BINARY_REL.items()):
        print(f"  {rel}: {reason}")

    # Gate: main clean (even for dry-run — dry-run should still teach the discipline)
    require_main_clean(src, force=args.force)

    if dry_run:
        return check_current_projection(src, dst)

    source_before_build = source_projection_manifest(src)
    old_lite_manifest: dict[str, tuple[int, int, str]] | None = None
    installed_state: tuple[list[Path], list[Path], Path] | None = None
    # Use mkdtemp + finally so post-install recovery still sees rollback.
    # TemporaryDirectory would delete rollback before the outer except could restore.
    temporary_root: Path | None = None
    try:
        temporary_root = Path(
            tempfile.mkdtemp(prefix=".t2ag-lite-build-", dir=str(workspace))
        )
        candidate = temporary_root / "candidate"
        rollback = temporary_root / "rollback"
        candidate.mkdir()
        require_distinct_file_ids(temporary_root, candidate, src, dst)
        total_copied, total_skipped, projected = build_candidate(
            src, candidate
        )
        print(f"candidate={candidate}")
        print(f"TOTAL copied={total_copied} skipped={total_skipped}")
        bad = verify_projection(src, candidate, projected)
        if bad:
            print("FAIL: candidate rejected; existing Lite untouched", file=sys.stderr)
            return 3
        source_after_candidate = source_projection_manifest(src)
        if source_after_candidate != source_before_build:
            raise RuntimeError("Main projection source changed after candidate verification")
        old_lite_manifest = lite_content_manifest(dst)
        moved_old, installed = install_candidate(candidate, dst, rollback)
        installed_state = (moved_old, installed, rollback)
        require_distinct_file_ids(temporary_root, candidate, rollback, src, dst)
        print(f"installed_after_removing_top_level_entries={len(moved_old)}")
        source_after_install = source_projection_manifest(src)
        if source_after_install != source_before_build:
            raise RuntimeError("Main projection source changed after Lite installation")
        inject_failure("final_verify")
        final_projected = projection_manifest(src, dst)
        if verify_projection(src, dst, final_projected):
            raise RuntimeError("final projection hash verification failed")
        if check_current_projection(src, dst):
            raise RuntimeError("final Lite projection/guide verification failed")
        source_before_return = source_projection_manifest(src)
        if source_before_return != source_before_build:
            raise RuntimeError("Main projection source changed before final return")
        inject_failure("final_return")
        shutil.rmtree(rollback)
        installed_state = None
    except Exception as exc:  # noqa: BLE001
        rollback_detail = ""
        if installed_state is not None:
            moved_old, installed, rollback = installed_state
            try:
                restore_previous_lite(dst, rollback, installed, moved_old)
                if old_lite_manifest is None or lite_content_manifest(dst) != old_lite_manifest:
                    raise RuntimeError("restored Lite byte manifest differs from pre-install state")
                rollback_detail = "; previous Lite restored and byte manifest verified"
            except Exception as rollback_error:  # noqa: BLE001
                rollback_detail = f"; ROLLBACK FAIL: {rollback_error}"
        elif old_lite_manifest is not None and lite_content_manifest(dst) != old_lite_manifest:
            rollback_detail = "; ROLLBACK FAIL: install-time recovery did not restore exact Lite manifest"
        print(
            f"FAIL: candidate build/install/final verification failed: {exc}{rollback_detail}",
            file=sys.stderr,
        )
        return 4
    finally:
        if temporary_root is not None and temporary_root.exists():
            shutil.rmtree(temporary_root, ignore_errors=True)

    final_projected = projection_manifest(src, dst)

    # snail: confirm allowlist hit (copied via main/ tree)
    snail_label = "main/80_interface/fable_snail.png"
    if any(label == snail_label for label, _, _ in final_projected):
        print(f"{snail_label}: kept ({ALLOWED_BINARY_REL[snail_label]})")
    elif (src / "main" / "80_interface" / "fable_snail.png").is_file():
        print(
            f"WARN: {snail_label} exists on main but was not projected",
            file=sys.stderr,
        )

    courses = (
        list((dst / "main" / "40_course").glob("*/course.md"))
        if (dst / "main" / "40_course").exists()
        else []
    )
    progress = (
        list((dst / "main" / "40_course").glob("*/progress.md"))
        if (dst / "main" / "40_course").exists()
        else []
    )
    print(f"lite courses={len(courses)} progress={len(progress)}")
    print("OK: regenerate complete. Next: python main/70_tools/t2ag_doctor.py (cwd=t2ag-lite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
