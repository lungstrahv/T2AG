# Git 版本与灾难恢复流程（git_workflow）

**保护级别**：core-playbook

> Git 为 T2AG 提供本地版本历史、误改恢复、变更审计和可选异地备份。
> `core-playbook` 表示本流程需要跨发行版保留，不表示每次结课都必须 commit 或联网 push。

## 一、触发与运行模式

以下情况触发：首次启用 Git、结课准备存档、课程/系统里程碑、版本发布、需要恢复历史文件。

| 模式 | 判定 | 结课行为 |
|---|---|---|
| `disabled` | 当前目录不在 Git 仓库中 | 跳过并如实报告 |
| `local` | 已有 Git，无远端或本次不联网 | 可在授权后本地 commit |
| `remote` | 已有 Git 与远端 | 可在逐次授权后本地 commit；远端上传由用户手动执行 |

Git 是保护层，不是教学真相源。Git 不可用时课程仍可结课，doctor 与文件写回仍必须完成。

## 二、安全边界

1. 先看状态和差异，再暂存；禁止把 `git add .` 当作日常默认动作。
2. 只暂存本次写入确认中列出的 T2AG 文件，使用显式路径；工作区中的其他改动视为用户或并行任务所有。
3. 不提交 `.env`、密钥、token、虚拟环境、缓存和未确认的个人材料。含学生档案的远端默认设为 Private。
4. agent 每次执行 `git add` 或 `git commit` 前都必须获得当前操作的明确授权；不接受“持续授权”替代本次确认。
5. 禁止自行使用 `git reset --hard`、`git clean -fd`、`git push --force`。冲突和历史改写先停下说明。
6. agent 不执行 `git push` 或其他远端仓库上传；只生成用户可核对的手动上传说明。
7. commit 成功与用户报告的远端上传结果分开记录；无网络或无快照不能阻塞教学文件写回。

## 三、首次启用

```bash
git --version
git rev-parse --is-inside-work-tree
git init -b main                         # 仅在确认当前目录就是目标仓库后执行
git config user.name "你的提交署名"      # 优先仓库级配置，不强改全局身份
git config user.email "你的提交邮箱"
```

第一次暂存前先检查或创建 `.gitignore`，至少覆盖：

```gitignore
.venv/
__pycache__/
*.pyc
.env
```

首次提交也要先运行第四节的预览流程。只有全新、专用且已人工确认的仓库，才可以在预览后使用范围较大的暂存命令。

## 四、结课或里程碑存档

```bash
git status --short
git diff --check
git diff -- path/to/file1 path/to/file2
git add -- path/to/file1 path/to/file2
git diff --cached --check
git diff --cached
git commit -m "MATH1607H lesson01: 更新进度与知识点复测"
```

- 路径来自 `session_close.md` 的写入确认，不从工作区猜测。
- 暂存后发现混入无关内容，停止 commit，先用 `git restore --staged -- <path>` 撤销该路径的暂存；不改工作区内容。
- commit 留言写“课程/系统对象 + 实际变化”，不使用 `update`、`misc` 等无信息词。
- 没有实际差异时不制造空 commit。

远端已配置且本次需要同步时，agent 只展示用户手动执行的命令：

```bash
git remote -v
git push
```

远端比本地新时先查看差异。是否执行 `pull`、处理冲突或上传都由用户在仓库客户端手动完成。

## 五、远端与隐私

```bash
git remote add origin <远端仓库地址>
git remote -v
git push -u origin main
```

- 含学生档案、课程感想或交易日志时，远端默认 Private。
- token 只进入系统认证界面或凭据管理器，不写入 Markdown、命令历史示例或 `.env` 后再提交。
- push 节奏由学生决定；agent 永远只提醒和展示清单，不代替用户执行远端上传。

## 六、恢复与审计

```bash
git log --oneline -- path/to/file
git diff <旧提交> -- path/to/file
git show <提交>:path/to/file
```

需要恢复时，先展示目标版本，再在学生确认后执行：

```bash
git restore --source <提交> -- path/to/file
git diff -- path/to/file
git add -- path/to/file
git commit -m "恢复 <文件> 到 <提交> 的已确认版本"
```

`git restore -- <path>` 会丢弃未提交改动，只能在学生明确要求丢弃后使用。优先把恢复动作做成一个新 commit，保留完整审计链。

## 七、T2AG 对接

| 场景 | Git 行为 |
|---|---|
| 结课仪式 | 检查状态与差异；按逐次授权决定待提交 / 本地 commit；远端由用户手动上传 |
| 里程碑完成 | 建议 commit；tag 只在版本或课程规则明确要求时创建 |
| doctor | 检查 `.venv/.env` 追踪、版本一致性和跨发行版 core-playbook |
| 版本发布 | changelog、版本号和发行版同步完成后再提交 |
| 灾难恢复 | 先读历史和展示目标，再恢复单文件或明确范围 |

## 八、常见报错

| 现象 | 处理 |
|---|---|
| `Please tell me who you are` | 设置当前仓库的 `user.name` 与 `user.email` |
| `rejected ... fetch first` | 查看远端差异；可快进时 `git pull --ff-only` |
| CRLF/LF warning | 通常无害；不要为消除提示批量改写全仓库 |
| push 认证失败 | 使用系统认证或 token，不把凭据写进文件 |
| 中文路径显示转义 | 可设置 `git config core.quotepath false` |
| 工作区已有不明改动 | 不暂存、不还原；只处理本次明确拥有的文件 |

## 九、教学与发布声明

- 未提交、无 Git、无网络都不阻断开课、教学写回或结课。
- core-playbook、doctor、目录结构或云端协议变化后，维护结束必须生成“待快照清单”并提示 `WARN`。
- 只有存在可恢复的本地快照，正式发布或 handoff 强制换代验收才能宣称“可发布”。
- 没有快照时可以如实报告“教学可继续，发布快照未完成”，不得把工作树状态冒充已发布版本。
