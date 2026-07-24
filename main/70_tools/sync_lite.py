#!/usr/bin/env python3
"""T2AG A 案：从 main 全量再生 t2ag-lite（线上审查快照）。

设计（对应 2026-07-24 阶段 0 机制裁决 A）：
- 每次运行 = 整树再生，不是白名单增量补丁。
- 先清空 lite 工作树（保留路径本身），再从 main 按排除清单复制。
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
- working_pages/pages 截图页

保留：
- 规则、playbook、doctor、实例 Markdown 状态、lesson 文本、cloud 文本
- assets/fable_snail.png（见 ALLOWED_BINARY_REL）
- t2ag_directory_guide.html
- lite 身份 README.md / AGENTS.md（再生后写回审查快照说明，与 main 有意不同）

用法：
  python main/70_tools/sync_lite.py
  python main/70_tools/sync_lite.py --dry-run
  python main/70_tools/sync_lite.py --force          # 脏树仍再生（警告）
  python main/70_tools/sync_lite.py --root C:/Users/MikeChen/T2AC
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
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
    "assets/fable_snail.png": (
        "directory-guide mascot; sole image asset for t2ag_directory_guide.html preview"
    ),
}

# 再生后由本脚本重写、与 main 有意不同的路径（不参与「应一致」哈希）。
LITE_IDENTITY_REL = frozenset({"README.md", "AGENTS.md"})

LITE_README = """# T2AG 线上模型审查快照（t2ag-lite）

> **身份**：由主实例 `t2ag/` **全量再生**得到的文本优先审查快照。
> 不是空白 skeleton，不用于初始化新学生，也不得作为教学写回源。

- 再生机制：A 案（`main/70_tools/sync_lite.py`）— 每次从 main 整树导出 + 排除清单
- 源实例：`../t2ag/`
- 唯一模板源：`../t2ag-skeleton/`
- 包含：系统规则、实例 Markdown 状态、课程与 lesson 文本、工具脚本、
  `t2ag_directory_guide.html` 与其单一蜗牛图
- 排除：教材/PDF/压缩包、`.venv`、`.tools`、`.git`、`.recovery`、缓存、
  二进制生成资产、DB/WAL 等

## 给线上模型的使用边界

建议按此顺序阅读：

1. `main/t2ag.md`
2. `main/00_core/t2ag_memory.md`
3. `main/10_case/course_info.md`、`student_info.md`、`teacher_overlay.md`
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

LITE_AGENTS = """# t2ag-lite 启动说明

本目录是 **t2ag 主实例的线上审查快照**（由 `main/70_tools/sync_lite.py` 全量再生）。

## 规则

- **只读审查**：不要教学写回、不要改进度真相源、不要装依赖、不要当 skeleton 用。
- 入口仍可读 `main/t2ag.md` 与 `main/00_core/t2ag_memory.md` 以理解结构。
- 发现的问题以审查报告返回本地；由 main/skeleton 裁决后落盘，再再生 lite。

## 版本

- 与源 main 对齐；版本号见 `main/t2ag.md` / `AGENTS.md`（main）。
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
        if p == "pages" and "working_pages" in parts:
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
        print("WARN: --force: regenerating from dirty main\n" + dirty, file=sys.stderr)
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
    print("hash_verify: ALL projected files byte-identical to main")
    return 0


def write_identity(dst: Path, dry_run: bool) -> None:
    if dry_run:
        return
    (dst / "README.md").write_text(LITE_README, encoding="utf-8", newline="\n")
    (dst / "AGENTS.md").write_text(LITE_AGENTS, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Full-regenerate t2ag-lite from t2ag (plan A)")
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="T2AC workspace root containing t2ag/ and t2ag-lite/",
    )
    ap.add_argument("--dry-run", action="store_true", help="Count only, do not write")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Allow regenerate from dirty main (prints warning; not recommended)",
    )
    ap.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip post-copy full hash verify (not recommended)",
    )
    args = ap.parse_args(argv)

    script_path = Path(__file__).resolve()
    t2ag_root = script_path.parents[2]
    workspace = args.root.resolve() if args.root else t2ag_root.parent
    src = workspace / "t2ag"
    dst = workspace / "t2ag-lite"

    if not src.is_dir():
        print(f"ERROR: main missing: {src}", file=sys.stderr)
        return 1

    print("plan=A full-regenerate")
    print(f"src={src}")
    print(f"dst={dst}")
    print(f"dry_run={args.dry_run} force={args.force}")
    print("binary_allowlist:")
    for rel, reason in sorted(ALLOWED_BINARY_REL.items()):
        print(f"  {rel}: {reason}")

    # Gate: main clean (even for dry-run — dry-run should still teach the discipline)
    require_main_clean(src, force=args.force)

    removed = clear_lite_tree(dst, args.dry_run)
    print(f"cleared_top_level_entries={removed}")

    total_copied = total_skipped = 0
    projected: list[tuple[str, Path, Path]] = []

    for name in ("main", "cloud", "assets"):
        c, s = copy_filtered(src / name, dst / name, args.dry_run, tree_prefix=name)
        total_copied += c
        total_skipped += s
        print(f"tree {name}: copied={c} skipped={s}")
        for sfile, rel in iter_projected_files(src / name, tree_prefix=name):
            projected.append((f"{name}/{rel.as_posix()}", sfile, dst / name / rel))

    for name in ("t2ag_directory_guide.html", ".gitignore"):
        p = src / name
        if p.is_file() and not should_skip_file(p, Path(name)):
            if not args.dry_run:
                shutil.copy2(p, dst / name)
            total_copied += 1
            projected.append((name, p, dst / name))
            print(f"root file: {name}")
        elif p.is_file():
            total_skipped += 1

    # snail: confirm allowlist hit (copied via assets/ tree when prefix resolves)
    snail_label = "assets/fable_snail.png"
    if any(t[0] == snail_label for t in projected):
        print(f"{snail_label}: kept ({ALLOWED_BINARY_REL[snail_label]})")
    elif (src / "assets" / "fable_snail.png").is_file():
        print(f"WARN: {snail_label} exists on main but was not projected", file=sys.stderr)
    write_identity(dst, args.dry_run)
    print("identity: README.md + AGENTS.md rewritten for lite")

    # Rebuild guide GENERATED blocks for *lite* tree (map must match lite dirs, not main paste)
    if not args.dry_run and (dst / "t2ag_directory_guide.html").is_file():
        tools = Path(__file__).resolve().parent
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        try:
            import build_guide as bg  # type: ignore

            rc = bg.run(dst)
            print(f"build_guide(lite): exit={rc}")
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: build_guide on lite failed: {exc}", file=sys.stderr)

    print(f"TOTAL copied={total_copied} skipped={total_skipped}")

    if args.dry_run:
        print("dry-run: skip write verify")
        return 0

    if not args.skip_verify:
        bad = verify_projection(src, dst, projected)
        if bad:
            return 3

    defs = (
        list((dst / "main" / "30_course_definitions").glob("*"))
        if (dst / "main" / "30_course_definitions").exists()
        else []
    )
    runs = (
        list((dst / "main" / "35_course_runs").rglob("course_status.md"))
        if (dst / "main" / "35_course_runs").exists()
        else []
    )
    print(f"lite defs entries={len(defs)} course_status={len(runs)}")
    print("OK: regenerate complete. Next: python main/70_tools/t2ag_doctor.py (cwd=t2ag-lite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
