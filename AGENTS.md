# T2AG bilingual release router

This repository root is a bilingual release checkout, not a personal T2AG
instance. It contains the complete Chinese edition under `zh/` and the complete
English edition under `en/`.

When the user asks to install, set up, start, or use T2AG from this root:

1. Read `INSTALL.md` in full.
2. Determine whether the user wants `zh` or `en` and obtain an explicit target
   directory outside this checkout.
3. Follow the Agent installation contract in `INSTALL.md`. Do not create student
   data or run first-use initialization inside this bilingual checkout.
4. After the selected edition is copied and verified, enter the new personal
   directory. Read its `AGENTS.md` and `main/t2ag.md` in full before continuing.

Do not overwrite a non-empty target, install dependencies, download textbooks,
delete files, commit, or upload merely because the user asked to install T2AG.
Those actions require their own applicable instructions and authorization.

## Authorization is non-amplifying and budget stop-loss closes the loop

An installation request authorizes only the explicitly selected edition, source,
target, and copy operation described in `INSTALL.md`. It does not authorize an
object not yet generated, a different target, dependency installation, textbook
downloads, initialization, deletion, commit, or upload. A receipt records evidence
of authorization; it never creates or enlarges authorization.

If the applicable test, time, remediation-round, or token budget is exhausted,
stop with status `stopped_budget` and report completed work, open findings, and
existing evidence. Do not evade the stop by renaming, splitting, or restarting the
same work.

本仓根是双语发行 checkout，不是个人 T2AG 实例。用户要求安装、设置、启动或使用 T2AG 时：

1. 完整读取 `INSTALL.md`；
2. 确定用户选择 `zh` 或 `en`，并取得仓外明确目标目录；
3. 按 `INSTALL.md` 的 Agent 安装契约复制并核验，不得在双语仓内生成学生数据或执行首次初始化；
4. 进入复制后的个人目录，完整读取其中的 `AGENTS.md` 与 `main/t2ag.md`，再继续首次运行。

## 授权不可放大与闭环止损

安装请求只授权 `INSTALL.md` 中用户明确选择的版本、来源、目标和复制动作；不得扩大为尚未
生成的对象、其他目标、依赖安装、教材下载、初始化、删除、commit 或上传。receipt 只记录
授权证据，不会生成或放大授权。

达到适用的测试、时间、整改轮数或 token 预算上限时，必须以 `stopped_budget` 停止并报告
已完成项、未闭合 finding 与已有证据；不得通过改名、拆分或重启同一施工绕过止损。

## Public release-tree validation / 公开发行树验证

During construction, `python -B tools/verify_release_tree.py --worktree` is a
preview only. Before claiming that GitHub contents are structurally complete, run
the unit tests and verify the committed tree:

```text
python -B -m unittest tools/test_verify_release_tree.py
python -B tools/verify_release_tree.py --tree HEAD
```

只有第二条对已提交 Git tree 的 PASS 才能证明 GitHub ZIP / clone 的路径面；本地空目录、
未跟踪文件或 worktree preview 不得冒充发布证据。
