# T2AG bilingual release router

This repository root is a bilingual **Release Source**, not a personal T2AG
instance. The complete Chinese edition is in `zh/`; the complete English edition
is in `en/`. A learner works only in a sibling **Personal Instance** named exactly
`t2ag`.

When the user asks to install, initialize, start, or use T2AG from this root:

1. Read `INSTALL.md` in full.
2. Ask exactly this question and wait for an explicit answer:

   ```text
   Choose your language / 选择你的语言：
   1. 中文
   2. English
   ```

   There is no default. Do not infer the choice from the conversation, browser,
   operating system, location, or model response language. No answer means no write.
3. Resolve the Release Source and its sibling target named `t2ag`. Refuse if the
   target already exists; never merge with or overwrite it.
4. Copy only the selected edition into `t2ag`, excluding `.git`, caches, virtual
   environments, recovery directories, staging directories, and upload scratch.
5. Verify the copied Personal Instance contains `AGENTS.md`, `README.md`, and
   `main/t2ag.md`, contains no `.git`, then enter it and read its `AGENTS.md` and
   `main/t2ag.md` in full.
6. Run first initialization in `t2ag`. The selected edition fixes the initial
   teaching language (`zh-CN` or `en-US`). Ask at most the five optional profile
   questions documented in `main/50_playbook/first_run.md`; an empty response uses
   public defaults and must not trigger follow-up questions.
7. After initialization, state-refresh check, and Doctor complete successfully,
   report that the learner should use `t2ag`. Only then ask a separate question:
   whether to delete the exact Release Source directory. A successful install or
   a language choice is not deletion authorization. If the user does not explicitly
   confirm, leave the Release Source untouched.

Do not install dependencies, download textbooks, create real courses or
Engagements, commit, push, or delete the Release Source merely because the user
asked to install T2AG.

## 中文执行契约

本仓根是双语**发行源**，不是个人实例。最终学习目录必须是发行源同级、名称精确为
`t2ag` 的**个人实例**。收到安装、初始化、启动或使用请求时：

1. 完整读取 `INSTALL.md`；
2. 用上面的双语问题询问语言并等待明确回答；语言无默认值，不得根据对话语言、浏览器、
   操作系统、地区或模型回复语言代选；未回答就不写文件；
3. 解析发行源与同级 `t2ag` 的绝对路径；目标已存在就停止，不合并、不覆盖；
4. 只把所选版本复制到 `t2ag`，并排除 Git 元数据、缓存、虚拟环境及临时目录；
5. 核验必需入口、确认没有 `.git`，进入 `t2ag` 并完整读取其启动指令；
6. 在 `t2ag` 内完成首次初始化。中文版初始讲解语言为 `zh-CN`，英文版为 `en-US`；
   首启最多询问五项可选资料，用户全部跳过时采用公开默认值，不得追问补齐；
7. 初始化、状态检查与 Doctor 成功后，才单独询问是否删除精确的发行源目录。选择语言或
   安装成功本身都不授权删除；没有明确确认就保留发行源。

## Authorization and validation

Authorization is non-amplifying: a receipt records evidence but never creates or
widens permission. During construction, `--worktree` is preview evidence only.
Before claiming GitHub ZIP or clone completeness, run the unit tests and validate
the committed Git tree:

```text
python -B .github/scripts/test_verify_release_tree.py
python -B .github/scripts/verify_release_tree.py --tree HEAD
```

If an applicable test, time, remediation-round, or token budget is exhausted,
stop with `stopped_budget` and report completed work, open findings, and evidence.
