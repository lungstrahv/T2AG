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
| `remote` | 已有 Git 与远端 | 默认逐次授权；已批准的有界 campaign Git 计划可覆盖列明的本地 checkpoint；远端上传由用户手动执行 |

Git 是保护层，不是教学真相源。Git 不可用时课程仍可结课，doctor 与文件写回仍必须完成。

## 二、安全边界

1. 先看状态和差异，再暂存；禁止把 `git add .` 当作日常默认动作。
2. 只暂存本次写入确认中列出的 T2AG 文件，使用显式路径；工作区中的其他改动视为用户或并行任务所有。
3. 不提交 `.env`、密钥、token、虚拟环境、缓存和未确认的个人材料。含学生档案的远端默认设为 Private。
4. 默认模式下，agent 每次执行 `git add` 或 `git commit` 前都必须获得当前操作的明确授权。
   `version_campaign` 只在用户批准了列举仓库、显式路径、commit 数量/用途、subject、停止条件
   和失效条件的有限 Git 计划后，才可覆盖其中列明的本地 checkpoint；无限期、跨版本或未列
   路径的“持续授权”无效。
5. 禁止自行使用 `git reset --hard`、`git clean -fd`、`git push --force`。冲突和历史改写先停下说明。
6. agent 不执行 `git push` 或其他远端仓库上传；只生成用户可核对的手动上传说明。
7. commit 成功与用户报告的远端上传结果分开记录；无网络或无快照不能阻塞教学文件写回。
8. `clean ≠ reviewed ≠ released`：干净工作树只说明没有未提交差异；普通 commit 或 recovery
   checkpoint 只提供恢复点，不自动取得独立复审或发布资格。

### 2.1 Campaign Git 计划

有界 campaign Git 计划必须绑定 `campaign_id`、目标版本、冻结 baseline、仓库、显式 pathspec、
允许的本地 checkpoint 数量与用途、commit subject、RT3 保留项和授权失效条件。每次 checkpoint
前仍须：

1. 重取实际 HEAD、工作树和 index 状态；
2. 展示本次拥有的显式路径及工作区 diff；
3. 只暂存列明路径；不得使用 `git add .`；
4. 展示 `git diff --cached --check`、cached diff、index tree 与 parent；
5. 发现未列路径、未知仓、基线变化、风险升级或未知 FAIL/WARN 时停止，不能消费剩余额度。

该计划不包含 push、tag、reset、checkout、stash、历史改写、删除 recovery 或未列明的 release
能力。release snapshot 与 push 始终是独立能力门。

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

checkpoint 分三类，名称不得混用：

| 类型 | 作用 | 是否可称发布 |
|---|---|---|
| evidence checkpoint | 保存文件清单、指纹、测试、WARN 与恢复来源；不要求 Git | 否 |
| recovery checkpoint | 有授权的本地中间 commit，用于恢复缺陷树或施工边界 | 否 |
| release snapshot | 绑定已通过完整候选复审和 finalization delta 独立复审的最终 HEAD/tree | 是；仅限报告指明的本地快照，不自动含 push/tag |

### 4.1 有界 finalization 协议

finalization 只允许候选完整复审通过后的精确状态/报告指针 delta，并使用以下固定顺序：

1. release operator 形成精确工作树，按 allowlist stage，冻结 parent、staged diff SHA 与 index tree；
2. 与 operator 不同模型或不同会话的 reviewer 在 commit 前审查语义、路径和全局门，记录
   `expected tree`；operator 不得自审；
3. reviewer 明确 `proposed_delta_passed` 后，operator 才可 commit **同一个** index tree；
4. reviewer 在 commit 后核对 parent、commit tree、实际 diff SHA、工作树和所有不可分割全局门；
5. tree 不等、额外路径、commit 后补字、报告回写或提前 PASS 均使本轮 finalization 失败。

reviewer output 最后生成、立即冻结且不可变。最终 PASS 只写外部 reviewer report；不得再回写
目标仓、施工报告或索引去制造新的未审 delta。报告写入后目标仓任一字节变化都会使对应
release snapshot 结论失效。

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
| 结课仪式 | 检查状态与差异；默认逐次授权，或按已批准 campaign Git 计划建立列明的本地 checkpoint；远端由用户手动上传 |
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

## 九、发布候选的只读重放

候选 tree 不是日常教学步骤。只有用户明确进入发布复审、Main 与 Skeleton 已进入安静窗口，
且工作树连续采样没有变化时，才允许生成候选 tree 证据。

### 9.1 0.2.0 冻结验收边界

本边界由用户于 2026-07-27 冻结；冻结的是 0.2.0 验收范围，不是 Git 快照，也不暂停
日常学习。0.2.0 的候选工具只支持当前 Windows/NTFS、普通非 sparse Git 仓和显式教学
安静窗口。最终独立复审只允许把以下六项及既有三发行闸门作为本代阻断：

1. 候选工具拒绝 `core.sparseCheckout`、`core.sparseCheckoutCone`、`index.sparse` 和
   `.git/info/sparse-checkout` 所表达的有效 sparse 状态，并有“工作树已改、候选静默漏改”
   负例；
2. Main 与 Skeleton 在当前安全本地配置下都能运行 `--preflight`；显式
   `core.fsmonitor=false` 是安全关闭态，只有启用值或外部 monitor 路径才拒绝；
3. 候选末次源指纹必须发生在全部 A/B 重放与复核之后；该末次指纹通过并成功返回即结束
   本轮安静窗口，之后发生的新学习写回不追溯否定已经形成的时点候选；
4. Doctor 一次运行对每门课程只读取并使用一个 `ProgressSnapshot`；
5. 所有声明为“精确替换”的测试辅助同时拒绝零命中和重复命中；
6. Lite 省略原始教材文档时，必须验证报告状态、正式 manifest 路径与 SHA、schema、
   target kind、operation count/sequence，以及每项 source/target/disposition/outcome/
   post-target 完整字段。

以下只进入后续加固 backlog，不再阻断 0.2.0：mode/File ID 的额外元数据证明、Lite
目录占位、最终检查结束后不可消除的纳秒级并发窗、非 Windows/NTFS 或 SHA-256 Git 等
跨平台威胁、特殊挂载，以及清单外新提出的理论攻击面。已有防御实现可以保留；复审者不能
因要求更强的证明而移动本代终点。清单外事实只有证明其直接违反上述六项或既有三发行闸门
时，才能重新归入 0.2.0 阻断。

对真实仓库的“只读”必须同时覆盖工作树、index、refs 和对象库元数据。仅设置临时 index
并把真实 `.git/objects` 配成 alternate 仍可能 freshen 真实对象的 mtime，不属于严格隔离；
禁止使用这种算法，也禁止 hardlink、`git clone --shared`、`--reference` 或其他会共享对象库
的复制方式。

规范重放必须满足：

1. 对源仓工作树内容、`HEAD`、refs、真实 index 和 `.git/objects` 元数据建立前置指纹；
2. 将整个仓库（工作树与 `.git`）物理复制到新的临时目录；复制不得使用 hardlink 或
   alternate，候选目录不得反向引用源仓；
3. 在物理副本中屏蔽用户级和系统级 Git 配置，并使用副本内的新临时 index 执行
   `read-tree HEAD → add -A -- . → write-tree → diff --cached --check`；
4. 删除副本前在第二个全新物理副本中独立重放；文件数、tree SHA 和 whitespace 结果
   必须一致；
5. 完成全部 A/B 复核后再重取源仓完整指纹；任一工作树内容、`HEAD`、refs、index、
   对象数量或对象元数据变化，立即废弃本轮全部候选值并报告事实，不得把相近值写成
   发布证据；
6. 临时副本清理只作用于已解析并确认位于临时根下的精确目录。候选操作绝不进入真实仓
   的 `.git`，也不以“没有新增对象”代替元数据不变证明。

上述条件由 `main/70_tools/t2ag_candidate_replay.py` 强制执行，不允许用手写复制命令或
报告声明替代。独立复审通过但尚未获候选授权时，只可运行不调用 Git、不生成副本的源仓
预检：

```powershell
python -B main/70_tools/t2ag_candidate_replay.py --preflight
```

工具在任何 Git 调用前必须 FAIL：

- 继承环境含任意大小写形式的 `GIT_*` 时，先全部清除，只注入工具控制目录中的 config、
  attributes、exclude、hooks 与 index；不得设置 object directory 或 alternate；
- `.git` 是 gitfile/链接，或存在 `commondir`、`gitdir`、`worktrees`、alternates、
  `config.worktree`、外部 `core.worktree`、include/includeIf、promisor/partial clone、
  worktree filter、已启用的 fsmonitor、有效 sparse checkout/sparse index、Git lock；
- 源根、临时根、两个副本或其祖先/后代含 symlink、junction、mount/reparse point；
- 任一普通文件链接数不是 1、File ID 在同树重复，或源/A/B 三树之间复用 File ID；
- 路径发生大小写/Unicode 规范化碰撞，或源与 A/B 的逐文件相对路径、大小、SHA-256
  字节清单不完全相等；
- 复制期间或重放期间源仓任一文件内容、mode、mtime，包含 HEAD、refs、index 和对象库
  元数据，发生变化。

只有用户针对本轮候选明确授权后，才可在源仓之外的全新空目录执行生成入口；文字 token
只是防误触门，不能替代用户授权：

```powershell
python -B main/70_tools/t2ag_candidate_replay.py `
  --generate `
  --workspace <源仓外的全新空目录> `
  --authorization-token CANDIDATE_REPLAY_AUTHORIZED
```

工具从同一个已核验源分别逐字节复制 A/B，Git 以预先解析并哈希的可执行文件、显式
`--git-dir`/`--work-tree` 和位于副本外控制目录的 index 运行。只有 A/B 的 tree SHA、
文件数、whitespace 结果一致，副本工作树字节不变，且源仓前后完整状态一致时才输出候选。

真实学习仍在写回、Lite 尚未同步、独立复审未通过或用户尚未授权发布复审时，只能把候选
状态记为 `revoked / not generated`；不得为了刷新报告而追逐一个持续变化的 tree SHA。

## 十、教学与发布声明

- 未提交、无 Git、无网络都不阻断开课、教学写回或结课。
- core-playbook、doctor、目录结构或云端协议变化后，维护结束必须生成“待快照清单”并提示 `WARN`。
- 只有存在可恢复的本地快照，正式发布或 handoff 强制换代验收才能宣称“可发布”。
- 没有快照时可以如实报告“教学可继续，发布快照未完成”，不得把工作树状态冒充已发布版本。
