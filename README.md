# T2AG

T2AG 是一套跑在文件系统上、由 AI agent（Claude、Codex 等）驱动的个人学习系统：课程、
练习、活动台账，以及检查全仓状态的 Doctor。本仓只提供空骨架，不携带真实学生数据。

T2AG is a file-based personal learning system driven by an AI agent (Claude,
Codex, or similar): courses, exercises, activity ledgers, and a Doctor that checks
the whole repository. This release contains empty skeletons, not student data.

| 版本 / Edition | 入口 / Entry | 生成来源 / Generated from |
|---|---|---|
| 中文（正本） | [`zh/README.md`](zh/README.md) | Skeleton 0.2.4 development, commit `538a5c9` |
| English | [`en/README.md`](en/README.md) | Skeleton EN 0.2.4 development, commit `0f151eb` |

> **版本状态 / Version status**：当前树是 `0.2.4` 开发态：
> `implementation_status = partial`、`candidate_review = not_run`、
> `release_qualification = not_claimed`。`0.2.3` 仍是最近完成候选复审与
> finalization-delta 独立复审的发行版本。
> This tree is the `0.2.4` development baseline: `implementation_status = partial`,
> `candidate_review = not_run`, and `release_qualification = not_claimed`.
> T2AG `0.2.3` remains the latest release-qualified version.

## 下载与初始化 / Download and initialize

GitHub **Code → Download ZIP** 会下载一个同时包含完整 `zh/` 与 `en/` 的双语发行源。
它只是安装来源；最终学习目录不是这个解压目录。

GitHub **Code → Download ZIP** downloads one bilingual Release Source containing
the complete `zh/` and `en/` editions. It is installation material, not the live
learning folder.

1. 下载并解压 ZIP（或 clone 本仓）。
2. 用 AI agent 打开发行源根目录并发送 `T2AG`。
3. Agent 必须无默认地询问：

   ```text
   Choose your language / 选择你的语言：
   1. 中文
   2. English
   ```

4. Agent 只把所选版本复制为发行源同级的 `t2ag/`，并在 `t2ag/` 中初始化。
5. 首次资料只有五项且全部可选：称呼、学习水平、是否引入参考培养方案、学习兴趣、自我介绍。
   全部跳过时使用公开默认值，不再追问。中文版初始讲解语言为中文，英文版为英文。
6. 初始化和验证成功后，Agent 才单独询问是否删除发行源。没有明确确认就保留。

1. Download and extract the ZIP (or clone this repository).
2. Open the Release Source root with an AI agent and send `T2AG`.
3. Answer the no-default bilingual language prompt shown above.
4. The agent copies only that edition into a sibling `t2ag/` and initializes there.
5. First run offers five optional profile items: preferred name, learning level,
   reference curriculum preference, learning interests, and self-introduction.
   Skipping all five uses public defaults without follow-up. English edition
   teaching is English; Chinese edition teaching is Chinese.
6. Only after successful initialization and verification may the agent separately
   ask whether to delete the Release Source. No confirmation means keep it.

安装期间可能暂时存在两个目录：浏览器命名的发行源，以及固定名为 `t2ag` 的个人实例。
用户始终只在 `t2ag` 中学习。发行源可以留作安装包，也可以在单独确认后删除。

Two folders may temporarily coexist: the browser-named Release Source and the
Personal Instance named exactly `t2ag`. The learner uses only `t2ag`. The Release
Source can be kept as installation material or deleted after separate confirmation.

完整的人工命令、路径核验与 AI 自动执行契约见 [`INSTALL.md`](INSTALL.md)。
See [`INSTALL.md`](INSTALL.md) for manual commands, path checks, and the agent route.

## 让 AI agent 自动执行 / Agent prompt

> 完整读取本目录的 `INSTALL.md`，严格使用无默认的双语语言问题。把我明确选择的版本复制
> 到发行源同级、名称精确为 `t2ag` 的新目录，在那里完成首次初始化与验证。不得覆盖已有
> `t2ag`。初始化成功后再单独问我是否删除发行源；没有明确确认就保留。

> Read `INSTALL.md` in full. Use its bilingual language question with no default.
> Copy only my explicit edition choice into a new sibling directory named exactly
> `t2ag`, then initialize and verify it there. Do not overwrite an existing `t2ag`.
> After success, ask separately whether to delete the Release Source; keep it unless
> I explicitly confirm deletion.

## 许可证 / Licensing

代码采用 [Apache-2.0](LICENSE)，散文采用 [CC BY-SA 4.0](LICENSE-DOCS.md)；路径边界见
[`LICENSING.md`](LICENSING.md)，归属与声明见 [`NOTICE`](NOTICE)。

Code is licensed under [Apache-2.0](LICENSE), prose under
[CC BY-SA 4.0](LICENSE-DOCS.md). See [`LICENSING.md`](LICENSING.md) for path
boundaries and [`NOTICE`](NOTICE) for attribution and notices.

---

*Maintained by [mikp from t2ac](https://github.com/lungstrahv)*
