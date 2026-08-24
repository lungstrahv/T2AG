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

本仓根是双语发行 checkout，不是个人 T2AG 实例。用户要求安装、设置、启动或使用 T2AG 时：

1. 完整读取 `INSTALL.md`；
2. 确定用户选择 `zh` 或 `en`，并取得仓外明确目标目录；
3. 按 `INSTALL.md` 的 Agent 安装契约复制并核验，不得在双语仓内生成学生数据或执行首次初始化；
4. 进入复制后的个人目录，完整读取其中的 `AGENTS.md` 与 `main/t2ag.md`，再继续首次运行。

