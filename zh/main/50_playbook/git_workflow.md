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
9. **外仓 `docs/` 跟踪边界（DOCS-TRACKING-BOUNDARY，2026-08-19 裁）**：裁决面**默认应
   跟踪**——工单、裁决记录、candidates、seeds、design、reports、tools 及顶层索引件
   （`docs/README.md`、`T2AG_PROGRESS.md`、`T2AG_PENDING_LEDGER_*.md`、
   `AUG_SHELL_WATCH.md`、`SEEDS.md`）。裁决记录是正典，不应活在仓外。豁免（入
   `.gitignore` 显式列）：`docs/recovery_points/`、`docs/handoffs/backups/`、
   `docs/publishing/` 生成物。背景：显式路径纪律（本节第 1/2 条）使跟踪集自然退化为
   「历史被点名 add 的并集」，半跟踪是纪律副产物而非裁决——此条补上应然边界。
   补 add 仍走显式目录路径，不豁免第 4 条授权。

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
| doctor | 检查 `.venv/.env` 追踪、版本一致性和跨发行版 core/meta-playbook |
| 版本发布 | changelog、版本号和发行版同步完成后再提交 |
| 灾难恢复 | 先读历史和展示目标，再恢复单文件或明确范围 |

## 八、常见报错

| 现象 | 处理 |
|---|---|
| `Please tell me who you are` | 设置当前仓库的 `user.name` 与 `user.email` |
| `rejected ... fetch first` | 查看远端差异；可快进时 `git pull --ff-only` |
| CRLF/LF warning | **不是无害**，按 §十一 处理：核对 `git diff -w` 是否为空，是则还原而非提交 |
| `hash binding mismatch` 且提示 `LINE ENDING DRIFT` | 宿主改写了行尾；还原文件，**不要**重新生成 plan 或重跑证据矩阵 |
| push 认证失败 | 使用系统认证或 token，不把凭据写进文件 |
| 中文路径显示转义 | 可设置 `git config core.quotepath false` |
| 工作区已有不明改动 | 不暂存、不还原；只处理本次明确拥有的文件 |

## 九、发布候选的只读重放

候选 tree 不是日常教学步骤。只有用户明确进入发布复审、Main 与 Skeleton 已进入安静窗口，
且工作树连续采样没有变化时，才允许生成候选 tree 证据。

<!-- rule: CAND-REPLAY-003 -->
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

<!-- rule: CAND-REPLAY-004 -->
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
<!-- rule: CAND-REPLAY-001 -->
- 源根、临时根、两个副本或其祖先/后代含 symlink、junction、mount/reparse point；
- 任一普通文件链接数不是 1、File ID 在同树重复，或源/A/B 三树之间复用 File ID；
<!-- rule: CAND-REPLAY-002 -->
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

## 十一、字节稳定性（canonical owner）

本节是**宿主相关字节漂移**的唯一现行 owner。

### 11.1 为什么这不是格式洁癖

T2AG 把证据绑定到**文件字节**的 SHA-256：冻结 plan、executor manifest、
`LessonPreparationSnapshot`、receipt chain 全部如此。宿主换一次行尾，所有下游证据静默
失效，而报错只说 `hash mismatch`。已复发三次：

1. 0.2.2 campaign — Windows `git clone` 重写历史证据换行 → 冻结 manifest SHA 失配 → 重跑 shadow；
2. 2026-08-06 — 某 Windows 工具把 83 个已跟踪文件 LF→CRLF（`git diff` 2.5 万行，`git diff -w` 为 0）；
3. 2026-08-06 — 交付的 `.ps1` 存为 UTF-8 无 BOM，PowerShell 5.1 按系统 codepage 解码 → 解析错乱。

前两条是行尾，第三条是字符编码，根因同一个：**交付物的字节依赖了宿主的解释默认值**。

### 11.2 仓库行尾

`.gitattributes` 是执行点，Main 与 Skeleton 必须字节一致：

```
* text=auto eol=lf
```

必须写 `eol=lf`，不能只写 `text=auto`。后者只规范化 blob，**工作树仍随宿主变**，
而被哈希的正是工作树文件。二进制类型需显式声明，不依赖自动探测。

### 11.3 发现漂移时

```
git diff HEAD --numstat | wc -l      # 有差异的文件数
git diff HEAD -w --numstat | wc -l   # 忽略空白后仍有差异的文件数
```

第二个为 `0` 即纯行尾噪音：**还原，不要提交**。提交它会污染 `git log -S`、blame 与全部
SHA 绑定证据。还原后确认全仓无 CRLF 残留——扫描要用可靠实现，嵌套引号的 shell 单行
命令曾静默返回空并被误读为“干净”。

### 11.4 跨宿主交付脚本

任何要在别的宿主上执行的交付脚本（`.ps1`、`.sh`、`.bat`）：

1. **纯 ASCII**，不含任何非 ASCII 字节——比“记得加 BOM”更彻底，宿主 codepage 就无从介入；
2. **LF 换行**；
3. 文件哈希类参数**运行时实算**，不硬编码（内容指纹如 payload SHA 可以硬编码，那不随宿主变）；
4. 取值后**断言非空**再传给下游命令，否则空串会被当成缺参数，错误信息指向错误的地方；
5. **不得假设外部命令的失败语义**。退出码非零不一定是错误——`sync_lite.py:707` 的
   check-only 就用 `return 1` 表示“存在漂移，去跑 `--write`”。动手前读它的源码或先跑一次，
   然后**断言真正有意义的字段**（如 `missing=0`、`orphan=0`），不要拿退出码当判据；
6. **包装外部命令的辅助函数必须自带已知答案探针**。函数在动真格之前先执行一条结果已知的
   调用（如 `git --version`），对不上就立即停止，不得让后续输出参与任何判断。

第 6 条的代价是实打实的：一个把参数名写成 `$Args`（PowerShell 保留自动变量）的封装函数
静默丢掉了全部参数，`git` 因此打印 40 行 usage 帮助，而调用方把这 40 行当成“40 个已修改
文件”，闸门于是“正确地”拦下了一个根本不存在的问题。**工具静默失效时产出的不是空值，
而是看起来合理的假数据**；只有先让工具自证在工作，它的输出才配当证据。这与 §11.3 里
“扫描要用可靠实现”是同一条教训的两个位置。

> 已知的 PowerShell 保留自动变量（不得用作参数名）：`$Args`、`$Input`、`$Error`、`$Host`、
> `$PSItem`、`$Matches`、`$This`、`$PID`、`$PWD`。

### 11.5 消费者

- `activity_close.line_ending_drift()` — SHA 失配时判别是否仅行尾差异，并在错误信息里
  直接写明 `LINE ENDING DRIFT`，指向本节而不是让人重跑矩阵。挂载点：plan 绑定、授权
  收据、post-close 哈希、plan 内容哈希四处。
- L2 已并入 `runtime.line_endings`：runtime 做有界扫描，release profile 继承同一 ID 并扩展为
  全量 tracked 扫描（2026-08-07 注册，2026-08-25 合并）；
  L1 仍缓（2026-08-19 裁，不排期），方案原件见
  `docs/handoffs/T2AG_HOST_BYTE_DRIFT_PREVENTION_PLAN_2026-08-06.md`（P-0088 勘误在其 status 行）。

> **rule_migration**（§6.3）：§八「CRLF/LF warning｜通常无害；不要为消除提示批量改写全
> 仓库」判定为 `retire + replace`。旧表述的前半句（“通常无害”）是本类事故的放行条件，
> 已被证伪；后半句（“不要批量改写全仓库”）语义**保留并强化**为 §11.3 的“还原，不要提交”
> ——两者都反对把行尾差异写进历史，区别只在处置方向。新 owner 为本节 §十一，消费方为
> `activity_close.line_ending_drift()` 与 §八报错表的两行指针，验证为该函数的正负例
> 断言（真实内容改动不得被判为漂移）。
