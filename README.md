# T2AG

一个代码库，同一版本的中英文双版本。选择语言即可开始。

One repository, two editions of the same release. Pick your language and go.

| 版本 / Edition | 入口 / Entry | 维护来源 / Maintained source |
|---|---|---|
| 中文（正本 / source of truth） | [`zh/README.md`](zh/README.md) | 0.2.3 Skeleton, commit `251ca57` |
| English (translated edition) | [`en/README.md`](en/README.md) | 0.2.3 Skeleton EN, commit `0d892d3` |

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

打开 `my-t2ag`，向你的 AI agent 发送 `T2AG`。实际使用与写入的是复制后的个人目录，
不是 `T2AG-release` 发行 checkout。英文用户把命令中的 `zh` 改为 `en`。

Open `my-t2ag` with your AI agent and send `T2AG`. Use and modify the copied
personal directory, not the `T2AG-release` checkout. For English, replace `zh`
with `en` in the command above.

## 让 AI agent 自动安装 / Let an AI agent install it

把下面一句发给能够读取网页并操作文件的 AI agent，并补上你的目标目录：

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

## 中文

T2AG 是一套跑在文件系统上、由 AI agent（Claude、Codex 等）驱动的学习系统：课程、
练习、活动台账，外加一个对全仓做机器检查的 doctor。本仓只发行**空骨架**——永不携带
真实学生数据。把 `zh/` 复制到任意目录，用你的 agent 打开并按 `zh/README.md` 走
首跑流程，该副本即成为你的个人实例。

`zh/` 是正本；`en/` 由正本生成、同刀发行——同一个 tag 永远同时覆盖两个版本。

**许可证**：代码 [Apache-2.0](LICENSE)，散文 [CC BY-SA 4.0](LICENSE-DOCS.md)；
路径边界与「为何散文才是 copyleft 的那一半」见 [`LICENSING.md`](LICENSING.md)。
本仓转 public 之前直接交付给受邀者的发行包，仍以
[`INVITED_USE_GRANT.md`](INVITED_USE_GRANT.md)（双语）为准；从本仓 clone 的副本
适用上述两份开源许可证。

## English

T2AG is a file-based learning system you run with an AI agent (Claude, Codex, or
similar): courses, exercises, activity ledgers, and a doctor that machine-checks
the whole structure. This repository ships the **empty skeleton** — no real
student data, ever. Copy `en/` somewhere, open it with your agent, and follow
`en/README.md`; the first-run flow turns the copy into your personal instance.

The Chinese edition under `zh/` is the source of truth; the English edition is
generated from it and ships in lockstep — one tag always covers both.

**Licensing**: code under [Apache-2.0](LICENSE), prose under
[CC BY-SA 4.0](LICENSE-DOCS.md) — [`LICENSING.md`](LICENSING.md) maps which
paths are which and explains why the prose is the copyleft half.
Release zips handed directly to invited individuals before this repository went
public remain governed by [`INVITED_USE_GRANT.md`](INVITED_USE_GRANT.md)
(bilingual); a clone taken from here carries the two open licences instead.

---

*Maintained by mikp from t2ac · t2ac@tutamail.com*
