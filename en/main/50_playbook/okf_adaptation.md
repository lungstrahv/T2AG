# OKF 知识包适配（okf_adaptation）

**保护级别**：playbook

> **协议标识**：`T2AG-OKF-1`｜目标格式：Open Knowledge Format **v0.2**
>
> 本手册规定 T2AG 主库如何被讲成一个 OKF 知识包（bundle），以及外部 OKF 包在什么
> 条件下可以进入 T2AG。它是**行为规范**：机器落点是 `70_tools/okf_export.py`，
> 但规范本身在这里，工具只是它的可复算实现。二者冲突时以本文件为准，并修工具。

OKF 是一个把知识写成「目录 + markdown + YAML frontmatter」的开放规范：唯一硬性要求
是每个概念文件的 frontmatter 带非空 `type`；信任族（`sources` / `generated` /
`verified` / `status` / `stale_after`）全部可选，且**缺席有含义**——没有 `verified`
就是「未核实」这一档，不是「不知道」。消费者一侧是宽容的：缺可选字段、不认识的
`type`、断链，都不得作为拒收理由。

## 一、定位与三条不变式

T2AG 主库天然已是「markdown + frontmatter + 相互链接」，所以适配不是改造，是**翻译**。

| # | 不变式 | 理由 |
|---|---|---|
| 1 | **主库零改动** | 导出器只读。bundle 是仓外生成物，删除整目录即完全回滚 |
| 2 | **机制可交换，实例不出门** | 默认范围只含描述「系统怎么运转」的文件；学生档案、日志、进度与 cloud 一律不进 bundle |
| 3 | **不伪造信任** | 没有真实核实事件就不写 `verified`。OKF 的信任分档靠字段缺席工作，编造等于把三档压成一档 |

不变式 3 的具体后果：本协议**不签发** `verified`。doctor 通过、测试通过都不是对
「这段知识为真」的核实，只是对结构的核实；把它写成 `verified` 会让消费者以为有人
读过内容。若将来要签发，须另立裁决并写明签发者是 `process:` 还是 `human:`。

## 二、范围（scope）

| scope | 收录 | 用途 |
|---|---|---|
| `mechanism`（默认） | 宪法 `main/t2ag.md` ＋ `00_core/` 的机制三件（`domain_model.md`、`learning_activity_model.md`、`pattern_retire_loop.md`）＋ `50_playbook/` 全部 ＋ `70_tools/*.md` | 对外交换、开源展示面 |
| `course:<COURSE_ID>` | 该课程的 `course.md`（课程定义） | 单门课程设计的交换，须逐次点名 |

**不存在导出个人层的范围。** `10_student/`、`60_journal/`、`progress.md`、
`activity_ledger.md`、`mistake_bank.md`、`lessons/`、`exercises/`、`cloud/` 没有任何
代码路径通向导出器——隐私边界靠缺席保证，不靠开关。若将来确有本地消费需求（例如让
本地 agent 读完整学习史），须另开工单，并在那份工单里独立回答落点、留存期与打包
事故面三个问题。

两处**看起来该收却不收**的，理由要写明，否则下一个人会当成遗漏补回来：

- **`00_core/` 的台账三件**（`t2ag_changelog.md`、`t2ag_memory.md`、`t2ag_problemlog.md`）
  不进 bundle。它们记的是「这个实例经历了什么」，不是「系统怎么运转」——changelog 与
  problemlog 含宿主路径与对端私有仓名，memory 本身就是学生状态的派生缓存。changelog
  只以**标题层**转写成 `log.md`（§四），正文不出门。
- **课程不进 `mechanism`**。`course.md` 是课程设计，可交换，但它点名真实教材、培养方案
  与院校，属实例识别面。要交换就走 `course:<ID>` 显式点名，并照样过泄漏闸门——闸门
  拦下来时的正确反应是承认「这门课的定义确实带着我的院校」，而不是给它开豁免。

白名单是**目录级正列举**，不是排除法。新增内容默认不进 bundle，除非本表加行。

宪法 `main/t2ag.md` 进 `mechanism`：它是整套机制的入口，实测也是被引用最多的节点
（bundle 内 14 条入边）。落在 bundle 根，`type: Governance Doc`。

## 三、映射表（T2AG → OKF frontmatter）

### 3.0 概览

| 来源 | bundle 落点 |
|---|---|
| `main/t2ag.md` | `/t2ag.md` |
| `main/<域>/<文件>.md` | `/<域>/<文件>.md`（去掉 `main/` 前缀） |

### 3.1 `type`：必填，按来源注入

主库多数散文文件没有 frontmatter，导出时按目录注入；已有 `type` 的一律透传原值。

| 来源 | 注入 `type` | 说明 |
|---|---|---|
| `00_core/domain_model.md` | `Domain Model` | 单列，它是领域词汇的权威 |
| `00_core/` 其余机制件 | `Governance Doc` | 宪法依赖的领域模型层 |
| `50_playbook/` | `Playbook` | OKF 原生示例类型 |
| `70_tools/*.md` | `Reference` | 工具说明面 |
| `40_course/*/course.md` | 透传（现为 `course`） | 已有 frontmatter 不改写 |
| 各目录 `_README.md` | 转写为该目录 `index.md`，不作为概念 | 见 §四 |

`type` 值风格取 OKF 示例的大写词组（`Playbook`、`Reference`），与主库已有的小写
`course` 并存。OKF 不设中央注册表，两风格同时出现是合法的；消费者对未知 `type`
必须优雅降级。

### 3.2 信任族

| OKF 字段 | 取值 | 备注 |
|---|---|---|
| `generated.by` | `t2ag/okf_export-<工具版本>` | 遵 OKF §7 actor 约定 |
| `generated.at` | 该文件最后一次 git commit 时间；不可得时回退文件 mtime | ISO 8601 UTC |
| `verified` | **不写** | 见 §一不变式 3 |
| `status` | 透传主库已有 `status` | 缺省即 `stable`，不主动写 |
| `stale_after` | **不写** | 见下 |
| `sources` | 仅当主库文件已有可机器识别的来源字段时透传 | 不为凑字段而编造来源 |
| `title` / `description` | 取正文首个 H1 与其后首句 | 供 `index.md` 汇编 |

`stale_after` 不写，因为可导出范围里没有会过期的东西：机制层的规则在被改写之前一直
有效，没有「到某天自动失效」的语义。宪法 §1.4 点名的 GENERATED 缓存（`t2ag_memory.md`、
`learning_path.md`）本来就在范围之外（§二），所以也不存在「派生缓存要标过期」这一
情形。若将来收录范围扩到会过期的内容，先在本表加行，再改工具。

### 3.3 链接与图结构

- 主库内部相对链接改写为 bundle 绝对形（`/xxx.md`，OKF §6.1 推荐形，文件移动后仍稳定）。
- 指向未收录文件的链接**保留原样，不报错**：OKF §6.1 明确断链代表「尚未写出的知识」，
  不是格式错误。
- 指向仓外或网络的链接原样保留。

**反引号引用升格为链接。** T2AG 散文引用其他文件用的是行内反引号
（`` `session_close.md` ``）而不是 markdown 链接——实测机制层 1266 处文件引用里，
markdown 链接是 **0**。而 OKF 的图结构完全靠链接表达（§6.1：消费者把每条链接当作
一条有向边）。照搬就等于导出一堆互不相连的文件，「知识包」退化成「文件夹」，OKF
相对于普通 wiki 的全部价值正好丢在这里。因此导出时把能解析到 bundle 内目标的反引号
引用升格为链接，**三条**克制规则：

1. **每个目标每文件只升格首次出现**。重复升格既让正文变吵，图上也只是同一条边。
2. **只升格解析得到 bundle 内目标的引用**。指向实例层（`progress.md`、`profile.md`
   一类）的引用留作反引号——既不伪造边，也不制造断链。
3. **只升格内联代码内容恰为单一路径 token 的情况**（EV-0024 R-3，2026-08-18 补）。
   判据：无空白、无引号与 shell 元字符、不以 `-` 开头、以 `.md` 结尾。机器落点是
   `okf_export.py` 的 `is_single_path_token()`，红测在 `test_okf_export.py`。

第 3 条是独立复审实测出来的：原实现用 `` `([^`\n]+\.md)` `` 匹配整段内联代码，于是
`` `grep -rn "x" file.md` `` 这类完整命令被整体升格成链接、多目标命令被压成一条边。
那不是展示问题，是**实质语义改写**——bundle 消费者会把一条命令读成一条知识边。
模板占位（`` `40_course/<COURSE_ID>/course.md` ``）尤其危险：旧实现会经裸文件名回退
匹配到某个真实 `course.md`，凭空造出一条错边。修正后机制层有 64 处内联代码由升格面
退出。

围栏代码块内不改写：那里的文件名是示例或命令，不是引用。同名文件出现在多处时不猜，
按不可解析处理。实测机制层导出得到 157 条边（2026-08-18 重测；复审期为 133，差额主要
来自期间新增的 playbook 文件），入边最多的是宪法。

## 四、保留文件

| 文件 | 生成来源 |
|---|---|
| bundle 根 `index.md` | 汇编各目录条目；**唯一**允许带 frontmatter 的 index，且只放 `okf_version: "0.2"` |
| 各目录 `index.md` | 由该目录 `_README.md` 与各概念的 `title`/`description` 汇编 |
| 根 `log.md` | 由 `00_core/t2ag_changelog.md` 近期条目转写为 OKF §9 的日期倒序格式 |

`index.md` 的作用是**渐进披露**——让人或 agent 先看见有什么，再决定打开哪个，因此
条目描述必须来自被链接概念自己的 `description`，不得另写一套。

## 五、泄漏闸门（写盘前，非写盘后）

导出**先在内存里渲染完整 bundle，扫描通过才落盘**；命中即零写入并列出全部命中点。
写完再扫等于事故已经发生。

扫描复用 `t2ag_doctor.py` 的 `SKELETON_PRIVACY_PATTERNS`（宿主用户目录绝对路径、
维护者用户名、院校名、对端私有仓名）。该词表是**共享真相源**：新增模式只改 doctor
一处，导出器随之生效，不得在导出器里另抄一份。

命中不可豁免。mechanism 范围里出现个人痕迹，说明主库该文件本身该脱敏，正确反应是
修主库，不是给导出器加白名单——豁免列表会把闸门蛀空（P-0065 / P-0067 同族教训）。

### 5.1 交付目录准入（EV-0024 P0，2026-08-18 补）

上面那道闸门架在**内容**上，但 2026-08-09 独立复审指出：闸门没架在**落点**上。
`write_bundle()` 会删掉目标目录里清单外的 `.md`，而 `--out` 原本是个裸路径，无任何
仓界校验——一次 `--write --out main/50_playbook` 就会递归删掉 playbook 里所有不在本次
导出清单里的 markdown。该 finding 被判为「可破坏主库的高危写路径」，整批因此暂缓
commit 九天。

准入规则（机器落点 `validate_out_dir()`，在任何删除动作之前运行）：

| # | 规则 | 拒绝的东西 |
|---|---|---|
| 1 | `--out` 不得是仓根、`main/`、工作区根或其祖先 | 手滑指向仓内 |
| 2 | `--out` 不得落在仓内 | bundle 是仓外生成物（不变式 1 的落点侧表述） |
| 3 | 落在任意 git 工作树内时必须带 `.t2ag-okf-bundle` 标记 | Skeleton、Lite、外仓 |
| 4 | 已存在且非空的目录必须带该标记 | 「不是我上次写出来的包」就不碰 |

标记文件 `.t2ag-okf-bundle` 由导出器在写入全新目录时自建。它是**目录的身份声明**，
不是配置：删掉它，下一次 `--write` 就会拒绝写入该目录。

另两条同批收口（P0-2 / P0-4）：

- 每个写入目标 `resolve()` 后必须严格落在 `--out` 之内（防相对路径里混进 `..`）；
- 残留文件删不掉、或交付目录里出现清单外文件（**不限 `.md`**）时**返回错误、退出码 1**。
  原实现只 WARN 且最终 exit 0，于是旧泄漏物可以留在交付目录里，而调用方看不出交付
  已经失败——「删不干净又不吭声」正是本协议最不该有的形态。

## 六、自检（conformance）

`okf_export.py --check-bundle <path>` 按 OKF §11 三条硬性条件复算：

1. 每个非保留 `.md` 有可解析的 YAML frontmatter；
2. 每个 frontmatter 有非空 `type`；
3. `index.md` / `log.md` 符合 §8 / §9 结构。

外加泄漏复扫。**不注册进 doctor runtime**：bundle 是可选生成物，它缺席或过期不该
让当天的教学 FAIL；这与 `t2ag.md` §3.2「发行问题不阻断教学」同一取向。

## 七、二期：导入边界（本期不实现）

外部 OKF 包进入 T2AG 时的约束，先立规矩再谈实现：

1. **只读引用层**。外部概念映射为 `SourceDocument` 候选或参考资料，**永不**直接生成
   T2AG 对象（Course / progress / ledger）。外部内容不得成为进度事实。
2. **不越宪法 §1.5**。教学仍必须以可追溯至 `SourceDocument` 的教材原文为依据，并消费
   当前 `LessonScope` 的 `SourcePageAsset` 证据。导入内容可作参考，不可替代原文。
3. **信任门**。默认只接受 human-reviewed（`verified` 含 `human:` actor）的概念；
   unverified 与 machine-confirmed 需逐次放行。`status: deprecated` 一律不收；
   `today >= stale_after` 的概念在教学侧禁用。
4. **不执行 Attested Computation**。OKF §10 的 `executor` / `attester` 指向可运行代码，
   等于把外部代码执行权引进主库，须独立裁决，本协议不授予。
5. 实现另开工单。本节只定边界，不构成施工授权。

## 八、版本与漂移

bundle 根 `index.md` 声明 `okf_version`，让消费者对不认识的版本自行降级（OKF §12）。
OKF 是 2026 年 6 月才发布的年轻规范，v0.1→v0.2 已经改过两个字段（`timestamp` →
`generated.at`；正文 `# Citations` → frontmatter `sources`）。因此：

- 规范升级只改**本文件的映射表**，工具跟着表走；
- 升级时在 changelog 记明「目标版本 x.y → x.z，改了哪几行表」，不许静默跟版。
