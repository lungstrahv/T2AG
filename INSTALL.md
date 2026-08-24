# Install T2AG / 安装 T2AG

The downloaded or cloned folder is a bilingual **Release Source**. It contains
both `zh/` and `en/` and is not the folder used for learning. Installation copies
one selected edition into a sibling **Personal Instance** named exactly `t2ag`.

下载或 clone 得到的是同时包含 `zh/` 与 `en/` 的双语**发行源**，不是日常学习目录。
安装会把所选版本复制到同级、名称精确为 `t2ag` 的**个人实例**。

## Required language prompt / 必须使用的语言问题

Before writing any file, ask exactly:

```text
Choose your language / 选择你的语言：
1. 中文
2. English
```

There is **no default language**. Do not infer the answer from the conversation,
browser, operating system, location, or model response language. If the user does
not answer, stop before copying. 中文与 English 都必须由用户明确选择；不回答就不写入。

## Installation contract / 安装契约

1. Resolve the absolute Release Source path. Its parent is the installation parent.
2. Set the target to the exact sibling path `<installation-parent>/t2ag`.
3. Refuse if `t2ag` already exists. Never merge, overwrite, or silently rename it.
4. Copy only the selected `zh/` or `en/` edition into `t2ag`. Exclude `.git`,
   `__pycache__`, `.venv`, `.cache`, `.recovery`, `.staging`, and `.uploads`.
5. Verify `t2ag/AGENTS.md`, `t2ag/README.md`, and `t2ag/main/t2ag.md` exist and
   `t2ag/.git` does not exist.
6. Enter `t2ag`, read its `AGENTS.md` and `main/t2ag.md` in full, and perform first
   initialization there. Chinese fixes the initial teaching language to `zh-CN`;
   English fixes it to `en-US`.
7. First run offers only five optional profile items: preferred name; learning
   level; whether to introduce a reference curriculum; learning interests; and
   self-introduction. An empty response uses documented defaults without follow-up.
8. Run state refresh check and Doctor as required by the selected edition.
9. Only after successful initialization and verification, ask separately whether
   to delete the exact Release Source. Do not delete it without explicit confirmation.

目标目录固定为发行源同级的 `t2ag`。目标已存在即停止；只复制所选语言版本。初始化和
验证成功后，才单独询问是否删除发行源；语言选择、复制成功或初始化成功都不构成删除授权。

## PowerShell reference route

Run from the bilingual Release Source root after the user has explicitly chosen
`zh` or `en`. This route copies and verifies; it does not delete the Release Source.

```powershell
$edition = "zh" # exact explicit choice: "zh" or "en"
if ($edition -notin @("zh", "en")) { throw "edition must be zh or en" }

$releaseRoot = (Resolve-Path -LiteralPath ".").Path
$source = (Resolve-Path -LiteralPath (Join-Path $releaseRoot $edition)).Path
$installParent = Split-Path -Parent $releaseRoot
$target = Join-Path $installParent "t2ag"

if (Test-Path -LiteralPath $target) { throw "target already exists: $target" }
foreach ($required in @("AGENTS.md", "README.md", "main\t2ag.md")) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $required))) {
        throw "selected edition is missing $required"
    }
}

New-Item -ItemType Directory -Path $target | Out-Null
robocopy $source $target /E /XD .git __pycache__ .venv .cache .recovery .staging .uploads
if ($LASTEXITCODE -ge 8) { throw "copy failed with robocopy exit code $LASTEXITCODE" }

foreach ($required in @("AGENTS.md", "README.md", "main\t2ag.md")) {
    if (-not (Test-Path -LiteralPath (Join-Path $target $required))) {
        throw "personal instance is missing $required"
    }
}
if (Test-Path -LiteralPath (Join-Path $target ".git")) {
    throw "personal instance must not contain .git"
}
Set-Location -LiteralPath $target
```

`robocopy` exit codes `0`–`7` are successful or nonfatal; `8` or higher is failure.
After initialization and verification, a model may ask whether to delete
`$releaseRoot`. If the user explicitly confirms, change into `$target` first,
re-resolve and report the exact Release Source, verify it is the previously recorded
path and is not `$target` or its parent, then delete only that directory.

## Bash reference route (macOS / Linux)

Run from the bilingual Release Source root after the explicit language choice.
This route requires `rsync` and does not delete the Release Source.

```bash
set -eu
edition="en" # exact explicit choice: "zh" or "en"
case "$edition" in zh|en) ;; *) echo "edition must be zh or en" >&2; exit 1 ;; esac
command -v rsync >/dev/null 2>&1 || { echo "rsync is required" >&2; exit 1; }

release_root="$(pwd -P)"
source="$release_root/$edition"
install_parent="$(dirname "$release_root")"
target="$install_parent/t2ag"

test ! -e "$target" || { echo "target already exists: $target" >&2; exit 1; }
for required in AGENTS.md README.md main/t2ag.md; do
  test -e "$source/$required" || { echo "selected edition is missing $required" >&2; exit 1; }
done

mkdir "$target"
rsync -a \
  --exclude='.git/' --exclude='__pycache__/' --exclude='.venv/' \
  --exclude='.cache/' --exclude='.recovery/' --exclude='.staging/' \
  --exclude='.uploads/' "$source/" "$target/"

for required in AGENTS.md README.md main/t2ag.md; do
  test -e "$target/$required" || { echo "personal instance is missing $required" >&2; exit 1; }
done
test ! -e "$target/.git" || { echo "personal instance must not contain .git" >&2; exit 1; }
cd "$target"
```

After successful first run and verification, deletion remains a separate,
explicitly confirmed operation against the previously recorded Release Source path.

## Result / 结果

During installation there may temporarily be two folders:

- the downloaded Release Source, whose name is chosen by the browser or Git; and
- the generated Personal Instance, always named `t2ag`.

The learner works only in `t2ag`. The Release Source may be kept as an installer
or deleted after the separate confirmation. It is never the live learning instance.
