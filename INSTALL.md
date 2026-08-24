# T2AG installation / T2AG 安装

This repository is one bilingual release checkout. It contains two complete
editions:

- `zh/` — Chinese edition and maintained source of truth;
- `en/` — English translated edition.

本仓库是一个双语发行 checkout，同时包含两个完整版本：`zh/` 为中文正本，`en/` 为
英文翻译版。安装的含义是把其中一个版本复制到新的个人目录；双语 checkout 本身不是个人实例。

## Human path / 用户操作路径

1. On GitHub, select **Code → Download ZIP**. The downloaded archive contains both
   `zh/` and `en/`.
2. Extract the archive.
3. Choose exactly one edition: `zh/` for Chinese or `en/` for English.
4. Copy the contents of that edition into a new, dedicated personal directory.
5. Open the personal directory with an AI agent and send `T2AG`.

1. 在 GitHub 选择 **Code → Download ZIP**；下载的是同时包含 `zh/` 和 `en/` 的双语包。
2. 解压压缩包。
3. 只选择一个版本：中文选 `zh/`，英文选 `en/`。
4. 将所选版本的内容完整复制到一个全新、专用的个人目录。
5. 用 AI agent 打开个人目录并发送 `T2AG`。

## Agent installation contract / Agent 安装契约

An agent asked to install T2AG from this repository must execute the following
route in order:

1. Determine two inputs from the user's request:
   - `edition`: exactly `zh` or `en`;
   - `target`: an explicit personal directory outside this bilingual checkout.
   If either input is missing or ambiguous, ask the user before writing files.
2. Resolve the absolute source and target paths and report them before copying.
3. Refuse to copy if the target is the bilingual repository root, its `zh/` or
   `en/` source directory, or any other tracked source checkout.
4. Create the target only when it does not exist. If it exists and is not empty,
   stop and ask the user; never merge into or overwrite an existing directory.
5. Copy the complete selected edition while excluding `.git`, `__pycache__`,
   `.venv`, `.cache`, `.recovery`, `.staging`, and `.uploads`.
6. Verify that the target contains `AGENTS.md`, `README.md`, and `main/t2ag.md`,
   and that the target does not contain a copied `.git` directory.
7. Enter the target, read `AGENTS.md` and `main/t2ag.md` in full, and follow their
   first-run route. The installation request does not authorize dependency
   installation, textbook downloads, creation of real courses or Engagements,
   deletion, Git commits, or remote uploads.

收到从本仓安装 T2AG 的请求后，agent 必须依次执行：

1. 从用户请求中确定两个输入：`edition` 只能是 `zh` 或 `en`；`target` 必须是双语 checkout
   之外的明确个人目录。任一输入缺失或含糊时，写文件前先询问用户。
2. 解析并报告源目录与目标目录的绝对路径，然后才复制。
3. 如果目标是双语仓根、仓内 `zh/`/`en/` 源目录或其他受 Git 跟踪的源 checkout，拒绝复制。
4. 仅在目标不存在时创建。目标已存在且非空时停止并询问；不得合并或覆盖已有目录。
5. 完整复制所选版本，同时排除 `.git`、`__pycache__`、`.venv`、`.cache`、`.recovery`、
   `.staging` 与 `.uploads`。
6. 核验目标中存在 `AGENTS.md`、`README.md`、`main/t2ag.md`，且没有复制 `.git`。
7. 进入目标目录，完整读取 `AGENTS.md` 与 `main/t2ag.md`，再按首次运行流程继续。安装请求
   不授权安装依赖、下载教材、创建真实课程或 Engagement、删除文件、Git commit 或远端上传。

### PowerShell copy route

Run this from the extracted or cloned bilingual repository root after replacing
the two input values:

```powershell
$edition = "zh" # exactly "zh" or "en"
$target = Join-Path $env:USERPROFILE "Documents\my-t2ag"

if ($edition -notin @("zh", "en")) { throw "edition must be zh or en" }
$releaseRoot = (Resolve-Path -LiteralPath ".").Path
$source = (Resolve-Path -LiteralPath (Join-Path $releaseRoot $edition)).Path
$target = [System.IO.Path]::GetFullPath($target)
$releasePrefix = $releaseRoot.TrimEnd("\") + "\"

if ($target -eq $releaseRoot -or $target.StartsWith(
        $releasePrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    throw "target must be outside the bilingual release checkout: $target"
}
if (Test-Path -LiteralPath $target) { throw "target already exists: $target" }

New-Item -ItemType Directory -Path $target | Out-Null
robocopy $source $target /E /XD .git __pycache__ .venv .cache .recovery .staging .uploads
if ($LASTEXITCODE -ge 8) { throw "copy failed with robocopy exit code $LASTEXITCODE" }

foreach ($required in @("AGENTS.md", "README.md", "main\t2ag.md")) {
    if (-not (Test-Path -LiteralPath (Join-Path $target $required))) {
        throw "installed copy is missing $required"
    }
}
if (Test-Path -LiteralPath (Join-Path $target ".git")) {
    throw "installed copy must not contain .git"
}
Set-Location -LiteralPath $target
```

After the copy succeeds, the edition's own `AGENTS.md` and `main/t2ag.md` become
the authoritative startup instructions.

`robocopy` uses nonstandard exit codes. Values `0` through `7` are successful or
nonfatal copy states; only `8` or higher is a copy failure. Agents must use the
explicit check above instead of treating every nonzero value as failure.

### Bash copy route (macOS / Linux)

Run this from the extracted or cloned bilingual repository root after replacing
the two input values. This route requires `rsync` and refuses an existing target
or a target inside the bilingual checkout.

```bash
set -eu

edition="en" # exactly "zh" or "en"
target="$HOME/Documents/my-t2ag"

case "$edition" in
  zh|en) ;;
  *) echo "edition must be zh or en" >&2; exit 1 ;;
esac

command -v rsync >/dev/null 2>&1 || {
  echo "rsync is required for the exclusion-preserving copy route" >&2
  exit 1
}

release_root="$(pwd -P)"
source="$release_root/$edition"
target_parent="$(dirname "$target")"

test -d "$target_parent" || {
  echo "target parent does not exist: $target_parent" >&2
  exit 1
}
target_parent="$(cd "$target_parent" && pwd -P)"
target="$target_parent/$(basename "$target")"

case "$target" in
  "$release_root"|"$release_root"/*)
    echo "target must be outside the bilingual release checkout: $target" >&2
    exit 1
    ;;
esac
test ! -e "$target" || {
  echo "target already exists: $target" >&2
  exit 1
}

mkdir "$target"
rsync -a \
  --exclude='.git/' --exclude='__pycache__/' --exclude='.venv/' \
  --exclude='.cache/' --exclude='.recovery/' --exclude='.staging/' \
  --exclude='.uploads/' "$source/" "$target/"

for required in AGENTS.md README.md main/t2ag.md; do
  test -e "$target/$required" || {
    echo "installed copy is missing $required" >&2
    exit 1
  }
done
test ! -e "$target/.git" || {
  echo "installed copy must not contain .git" >&2
  exit 1
}
cd "$target"
```

After the copy succeeds, the edition's own `AGENTS.md` and `main/t2ag.md` become
the authoritative startup instructions.
