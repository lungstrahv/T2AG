# T2AG

T2AG 是一套跑在文件系统上、由 AI agent（Claude、Codex 等）驱动的个人学习系统：课程、
练习、活动台账，以及检查全仓状态的 doctor。本仓只提供空骨架，不携带真实学生数据。

T2AG is a file-based personal learning system driven by an AI agent (Claude,
Codex, or similar): courses, exercises, activity ledgers, and a doctor that
checks the whole repository. This repository contains only empty skeletons and
never carries real student data.

中文版本是正本；英文版由它生成并保持同步。一个代码库，同一来源快照的中英文双版本；
一个 tag 始终同时覆盖两版。

The Chinese edition is the source of truth; the English edition is generated
from it and versioned in lockstep. One repository, two editions generated from
the same source snapshot; one tag always covers both.

| 版本 / Edition | 入口 / Entry | 生成来源 / Generated from |
|---|---|---|
| 中文（正本 / source of truth） | [`zh/README.md`](zh/README.md) | Skeleton source version 0.2.3, commit `dcc6812` |
| English (translated edition) | [`en/README.md`](en/README.md) | Skeleton EN source version 0.2.3, commit `26f05f8` |

> **版本状态 / Version status**：表中的 `0.2.3` 只标识生成来源与运行版本，不构成发行资格
> 声明。当前台账为 `candidate_review: not_run`、`release_qualification: not_claimed`；最近完成
> 发行资格审查的版本仍是 `0.2.2`。Here `0.2.3` identifies the source and runtime
> version, not a qualified release. The latest release-qualified version remains `0.2.2`.

## 下载时会得到什么 / What the download contains

GitHub 的 **Code → Download ZIP** 会下载一个双语压缩包，其中同时包含完整的
`zh/` 与 `en/`。解压后只需选择并复制一个版本：中文用户使用 `zh/`，英文用户使用
`en/`。`git clone` 得到的目录结构相同。

GitHub's **Code → Download ZIP** downloads one bilingual archive containing both
the complete `zh/` and `en/` editions. After extraction, choose and copy only one:
use `zh/` for Chinese or `en/` for English. A `git clone` has the same layout.

不要直接在双语下载目录中开始使用 T2AG；它是只用于选版和复制的发行 checkout。个人资料、
课程和学习进度应写入复制后的单语目录。

Do not start using T2AG inside the bilingual download directory. It is a release
checkout used only to select and copy an edition. Personal data, courses, and
learning progress belong in the copied single-edition directory.

## 手动安装 / Manual setup

1. 下载并解压仓库 ZIP，或使用下面的 `git clone`。
2. 中文用户选择 `zh/`；英文用户选择 `en/`。
3. 把所选目录完整复制到一个新的个人目录，例如 `Documents/my-t2ag`。
4. 用 AI agent 打开该个人目录并发送 `T2AG`。

1. Download and extract the repository ZIP, or use the `git clone` below.
2. Choose `zh/` for Chinese or `en/` for English.
3. Copy the selected directory into a new personal directory such as
   `Documents/my-t2ag`.
4. Open that personal directory with an AI agent and send `T2AG`.

```powershell
git clone --depth 1 https://github.com/lungstrahv/T2AG.git T2AG-release
Set-Location .\T2AG-release
$target = Join-Path $env:USERPROFILE "Documents\my-t2ag"
robocopy .\zh $target /E /XD .git __pycache__ .venv .cache .recovery .staging .uploads
Set-Location $target
```

`robocopy` 使用非标准退出码：`0`–`7` 均表示成功或非致命差异，只有 `8` 及以上表示失败。
`robocopy` uses nonstandard exit codes: `0`–`7` are successful or nonfatal;
only `8` or higher means failure.

macOS / Linux：

```bash
git clone --depth 1 https://github.com/lungstrahv/T2AG.git T2AG-release
cd T2AG-release
edition="zh" # use "en" for English
target="$HOME/Documents/my-t2ag"

test ! -e "$target" || { echo "target already exists: $target" >&2; exit 1; }
mkdir -p "$target"
rsync -a \
  --exclude='.git/' --exclude='__pycache__/' --exclude='.venv/' \
  --exclude='.cache/' --exclude='.recovery/' --exclude='.staging/' \
  --exclude='.uploads/' "./$edition/" "$target/"
cd "$target"
```

打开 `my-t2ag`，向你的 AI agent 发送 `T2AG`。实际使用与写入的是复制后的个人目录，
不是 `T2AG-release` 发行 checkout。英文用户把命令中的 `zh` 改为 `en`。

Open `my-t2ag` with your AI agent and send `T2AG`. Use and modify the copied
personal directory, not the `T2AG-release` checkout. For English, replace `zh`
with `en` in the command above.

## 让 AI agent 自动安装 / Let an AI agent install it

把下面这段提示词发给能够读取网页并操作文件的 AI agent，并补上你的目标目录：

> 请完整阅读 https://github.com/lungstrahv/T2AG/blob/main/INSTALL.md ，按其中的
> Agent 安装契约把 T2AG 中文版安装到 `<目标目录>`；安装完成后进入该目录，读取
> `AGENTS.md` 和 `main/t2ag.md`，然后启动首次运行。不要覆盖已有文件，也不要安装依赖
> 或下载教材。

For English, send this prompt and replace the target path:

> Read https://github.com/lungstrahv/T2AG/blob/main/INSTALL.md in full. Follow its
> agent installation contract to install the English edition of T2AG into
> `<target directory>`. Then enter that directory, read `AGENTS.md` and
> `main/t2ag.md`, and begin first run. Do not overwrite existing files, install
> dependencies, or download textbooks.

An agent that has already opened the bilingual repository root will also discover
the root [`AGENTS.md`](AGENTS.md), which routes it through the same installation
contract. Full manual and agent instructions: [`INSTALL.md`](INSTALL.md).

## 许可证 / Licensing

代码采用 [Apache-2.0](LICENSE)，散文采用 [CC BY-SA 4.0](LICENSE-DOCS.md)；
路径边界与「为何散文才是 copyleft 的那一半」见 [`LICENSING.md`](LICENSING.md)。
本仓转 public 之前直接交付给受邀者的发行包，仍以
[`INVITED_USE_GRANT.md`](INVITED_USE_GRANT.md)（双语）为准；从本仓 clone 的副本
适用上述两份开源许可证。

Code is licensed under [Apache-2.0](LICENSE), and prose under
[CC BY-SA 4.0](LICENSE-DOCS.md) — [`LICENSING.md`](LICENSING.md) maps which
paths are which and explains why the prose is the copyleft half.
Release zips handed directly to invited individuals before this repository went
public remain governed by [`INVITED_USE_GRANT.md`](INVITED_USE_GRANT.md)
(bilingual); a clone taken from here carries the two open licences instead.

---

*Maintained by [mikp from t2ac](https://github.com/lungstrahv)*
