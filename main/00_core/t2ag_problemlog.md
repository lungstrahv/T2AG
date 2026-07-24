> 【模式】复利回路·衰减（00_core/pattern_retire_loop.md）实例
> 【参数】域=系统运维｜时机=事后归因｜归因层=流程/工具层｜消费方=修 playbook→改系统｜退出=同类不再发｜再入=同类故障再现→重开条目
> 【边界】课程知识性错误转投对应课程 mistake_bank（边界规则裁决）

> 本文件记录 T2AG 使用过程中遇到的问题、用户个性化需求、解决方案与优化调整过程。
> 时间精确到小时，概括性记录用户与模型的对话。

> **定位**：本文件是 T2AG 的**系统/流程错题本**，不是聊天归档。它记录会影响下一次行动质量的问题：OCR、下载、环境、文件结构、课程初始化、权威链、doctor、记忆治理、规则执行偏差等。
> **消费原则**：启动时不全量读取；由 `t2ag_memory.md` 的索引按需展开。遇到相似任务前，先检索本文件和 `main/50_playbook/`，再行动。
> **维护流程**：写入、检索、归因和下沉按 `main/50_playbook/problemlog_maintenance.md` 执行。

---

## [2026-07-07] 永久定律：手写两遍必然不一致

**标签**：权威链 / 引用纪律

**复用价值**：高（永久）

**是否已提炼 playbook**：已提炼：`00_core/course_group_rules.md` 第二节

**问题**：S002 档案「当前课程」手写三门课（CS1953+MATH1607H+PY1001），与课程组成员表（G01 含 MATH1607H+PY1001）及 course_info（四门含 IV1001）三方不一致。这是一个月内第三次验证同一定律：进度缓存与真相源不一致（第一次）、版本号跨文件漂移（第二次）、课程清单多处手写不一致（第三次）。

**根因**：信息被手写两遍以上，必然有一天不一致。每次都靠 agent 自由心证裁决，没有定义层的唯一真相源。

**解决**：删副本，留指针。课程清单的唯一真相源 = 当前课程组成员表；学生档案只写指针"见 memory 指针"，不枚举课程代码；course_info 加状态列但状态取值由组文件成员表决定。doctor 加检查：权威链外的 .md 出现枚举式课程清单 → WARN。

**通用推论**：凡发现同一信息在两个以上文件中手写，立即按"删副本留指针"修法处理，不等它腐烂。

---
```

### 5. 写入后的维护动作

- 若新增条目有中/高复用价值：同步更新 `main/00_core/t2ag_memory.md` 的「最近 5 条问题」或「关键决策索引」。
- 若同类标签反复出现，或本次解决方案已经可标准化：把条目标为 `候选`，并询问是否提炼为 `main/50_playbook/*.md`。
- 若已有 playbook，但本次仍踩坑：更新对应 playbook 的常见问题/步骤，而不是只追加日志。

---

## [2026-07-07 10:00]

**标签**：记忆治理 / playbook / journal / 路径更正

**触发条件**：下次迁移外部 agent 系统规则时,如果只找到 journal 摘要而没找到原始规则文件,必须继续确认默认 skill/config 目录。

**复用价值**：高

**是否已提炼 playbook**：已提炼并修正：`main/50_playbook/playbook_management.md`、`main/50_playbook/journal_management.md`

**问题**：此前只找到 `~/.hermes/journal/` 摘要,未定位到 Hermes 原始 skill 文件；用户更正实际 skill 目录为 `C:\Users\MikeChen\AppData\Local\hermes\skills\`。

**尝试**：
1. 初次读取 `C:\Users\MikeChen\AppData\Local\hermes\skills\` 被沙箱拒绝。
2. 经用户明确指出路径后,请求提升权限只读该目录。
3. 定位并读取原始文件：`skill-creation-gate/SKILL.md`、`hermes-memory-and-skills/SKILL.md`、`hermes-journal/SKILL.md`、`hermes-journal-management/SKILL.md`。

**解决**：将 `playbook_management.md` 与 `journal_management.md` 的来源从 Hermes journal 摘要更正为 Hermes 原始 skill 文件；同步修正 `t2ag.md`、`t2ag_changelog.md` 和 memory 摘要。

**后续**：迁移其他 agent 系统规则时,优先找原始规则文件；journal 只能作为线索或事件摘要,不能替代规则源。

---

## [2026-07-07 10:00]

**标签**：记忆治理 / playbook / journal

**触发条件**：下次用户提到 Hermes、skill gate、pinned skill、meta-skill、journal 或其他 agent 系统的记忆治理规则,并要求迁移到 T2AG 时。

**复用价值**：高

**是否已提炼 playbook**：已提炼：`main/50_playbook/playbook_management.md`、`main/50_playbook/journal_management.md`

**问题**：用户要求找到 Hermes 的 pin skill、meta skill 和日志管理规则,并加入 T2AG 的 playbook 管理规则和 journal 管理规则。

**尝试**：
1. 直接枚举 `C:\Users\MikeChen` 被权限拒绝；改为读取明确路径 `C:\Users\MikeChen\.hermes`。
2. 确认 Hermes 默认用户目录为 `~/.hermes/`,本机存在 `60_journal/`、`patches/`、`skins/`。
3. 读取 `~/.hermes/journal/2026-07-06-skill-creation-gate-refinement.md`、`2026-07-06-skin-caduceus-skill-taxonomy.md`、`INDEX.md`、`2026-07.md`。
4. 当前 PowerShell 环境未找到 `hermes` 命令,实际 `skill-creation-gate/SKILL.md` 当时未在可读 Hermes 目录中定位到；因此先以 Hermes journal 中记录的规则为迁移来源。后续已由 2026-07-07 10:00「路径更正」条目修正为原始 skill 来源。

**解决**：新增 `main/50_playbook/playbook_management.md` 和 `main/50_playbook/journal_management.md`；在 `main/t2ag.md` 中新增 Journal 管理章节,并把 playbook 创建门槛扩展为类似 Hermes skill gate 的规则；新增可选 `main/60_journal/INDEX.md` 与 `main/60_journal/2026-07.md`；同步更新 changelog 与 memory。

**后续**：以后迁移外部 agent 规则时,先确认其默认目录和可读来源；若找不到实际规则文件,必须在记录中标明来源是 journal 摘要而非原始 skill 文件。迁移后不得直接新增层级,要先判断是否能映射到现有 playbook / journal / changelog / problemlog。

---

## [2026-07-07 10:00]

**标签**：记忆治理 / playbook

**触发条件**：下次发现某个日志文件“有记录但不被行动消费”，或需要把事后记录升级为可执行规则时。

**复用价值**：高

**是否已提炼 playbook**：已提炼：`main/50_playbook/problemlog_maintenance.md`

**问题**：用户指出 `problemlog` 没有被有效利用；原规则偏向“事后记录”，缺少“事前检索、写后同步、反复出现后提炼 playbook”的维护闭环。

**尝试**：
1. 检查 `main/00_core/t2ag_memory.md`，发现已声明 problemlog 按需展开，但只停留在索引层，缺少具体维护动作。
2. 检查 `main/t2ag.md`，发现「问题与解决日志」章节仍残留“启动时一并读取”的旧说法，且模板字段只有问题/尝试/解决/后续。
3. 检查 `main/50_playbook/session_close.md`，发现只说工具问题归 problemlog，没有强制结课时收割和同步 memory。

**解决**：将 `t2ag_problemlog.md` 定位为系统/流程错题本，新增必查场景、写入边界、标准字段和写入后维护动作；同步更新 `t2ag.md` 种子模板；新增 `main/50_playbook/problemlog_maintenance.md`；在 `session_close.md` 中加入系统问题收割；刷新 `t2ag_memory.md` 与 `t2ag_changelog.md`。

**后续**：以后执行 OCR、下载、课程初始化、课程恢复、doctor 修复、权威链调整、规则升级前，先查 playbook 和 problemlog；新增中/高复用价值问题后，必须同步 memory，必要时提炼 playbook。

---

## [2026-07-05 10:00]

**问题**：MATH1607H lesson01 第 25 页（陈纪修《数学分析》第三版上册，定理 1.1.1 可列集证明）的 Tesseract OCR 结果中，数学公式、下标、集合符号、矩阵几乎全部误识别，`page_25_raw.txt` 公式部分几乎不可读。典型错误：`0,1,-1,2,-2,...` → `0 T2 2 r`；`⋃A_n` → `U 4` / `L 4,`；无穷方块阵 `x_{ij}` → `氛 1 X12 怡 1`；对角线排列序列 → `光 | y Mins 标 21`；`i ≠ j` → `i 三 门`；`(-∞,+∞)` → `(- ,+o )`；`(n,n+1](n∈Z)` → `(n,an+1](nsZ)`。已写入 `t2ag.md` 与 `course_info.md` 的 OCR 工具优先级（PaddleOCR → Pix2Text → MathPix → Tesseract 兜底）和常见错误对照表未能根治，因环境中仅装了 pytesseract。

**尝试**：
1. 检查 `.venv`：仅有 `pytesseract`、`PIL`、`pdf2image`，**未安装** `paddleocr`、`pix2text`、`PyMuPDF(fitz)`。而 `ocr_page25.py` 等 OCR 脚本依赖 `fitz`，说明脚本运行时用的是系统 Python 而非 `.venv`。
2. 直接读取 `pdf_page25_render.png` 原图，由模型视觉能力逐符号识读：整数排列 `0, 1, -1, 2, -2, …, n, -n, …`；并集定义 `⋃_{n=1}^{∞} A_n = A_1 ∪ A_2 ∪ … = {x | ∃ n∈N*, x∈A_n}`；无穷方块阵 `x_{11} x_{12} x_{13} x_{14} …` 配 `↘` 对角线箭头；对角线法则排列 `x_{11}, x_{12}, x_{21}, x_{13}, x_{22}, x_{31}, x_{14}, …`；`i ≠ j`、`(-∞, +∞)`、`(n, n+1] (n∈Z)` 等全部还原。
3. 将校对后的正确文本写回 `temp_page.md` 第 25 页区块，原始 OCR 结果保留在 `page_25_raw.txt` 备查；更新 `temp_page.md` 头部 OCR 状态说明（25 页已校对，22–24 页仍需复核）。

**解决**：第 25 页已通过「原图视觉识读 + 人工逐符号校对」完全还原，可直接用于教学。本次未安装 PaddleOCR/Pix2Text（环境依赖较重，留作后续优化）。

**后续**：
- 短期：对公式密集页优先用「模型视觉识读原图」替代 Tesseract，比安装新 OCR 工具链更快、更准。
- 中期：在 `.venv` 中补装 `pymupdf` 与 `pix2text`（`pip install pix2text`，纯 Python，依赖较轻），实现公式自动识别。
- 长期：考虑把「OCR 工具链 + 视觉识读 + 人工校对」沉淀为 `course_status.md` 常用命令的标准流程。

---

## [2026-07-04 17:00]

**问题**：用 Tesseract OCR 提取陈纪修教材时，经历了「失败 → 部分成功 → 完全可用」的过程，需要把完整过程和关键踩坑点保存下来，并建立 OCR 结果校验规则。

**尝试与解决**：
1. **第一阶段：直接读取 Text PDF 失败**
   - `pdftotext` 和 PyMuPDF `get_text()` 对 `_text.pdf` 输出全为乱码。
   - PyMuPDF 检查字体发现使用 `GlyphLessFont` + `Identity-H`，文字层编码映射缺失。
2. **第二阶段：Tesseract 环境搭建**
   - 发现 Tesseract 已安装但不在 PATH，通过 `export PATH="$PATH:/c/Program Files/Tesseract-OCR"` 加入当前会话。
   - 缺少 `chi_sim.traineddata`，从 GitHub 下载到 `~/tessdata`，并复制 `eng.traineddata` 到同一目录。
   - 设置 `TESSDATA_PREFIX=~/tessdata`，验证 `tesseract --list-langs` 可看到 `chi_sim` 和 `eng`。
3. **第三阶段：Python subprocess 调用 OCR 失败**
   - 用 Python `subprocess.run([tesseract, img, "stdout", "-l", "chi_sim+eng"], capture_output=True, text=True)` 读取结果，输出全是乱码或异常字符（如 `ˮ һ _ ӳ`）。
   - 推测原因：Tesseract stdout 在 Windows/Git Bash 环境下的编码/换行处理与 Python 不兼容。
4. **第四阶段：Bash 直接调用成功**
   - 在 Git Bash 中直接执行 `tesseract page.png stdout -l chi_sim+eng`，输出中文正常可读。
   - 改用文件输出模式 `tesseract page.png outputbase -l chi_sim+eng`，生成 `outputbase.txt`，再用 Bash 读取，结果正常。
5. **第五阶段：批量 OCR 与内容拆分**
   - 对教材第 21–40 页批量渲染为 200 DPI PNG，再用 Bash 循环调用 Tesseract 文件输出模式。
   - 得到可读 OCR 文本，据此重写并拆分 lesson01/lesson02。

**OCR 结果校验规则**：
- OCR 后的文本若出现无法理解的汉字组合、明显缺字、符号错配（如 `xe S` 应为 `x ∈ S`），应优先结合数学上下文修正。
- 对不确定的术语、人名、出版社信息或整句语义，可通过联网搜索（如教材目录、官方出版信息、网络题库）交叉验证。
- 关键定义、定理编号、公式必须对照教材 Image Container PDF 图片做最终人工校对。

**解决**：OCR 流程稳定为「PyMuPDF 渲染 PNG → Bash 调用 Tesseract 文件输出 → 人工校对 → 生成讲义」。

**后续**：
- 将 OCR 踩坑过程写入本日志，作为后续课程生成的参考。
- 在生成讲义时，对 OCR 异常汉字组合主动联网查询验证。
- 持续优化：尝试更高 DPI、Tesseract 页面分割模式（`-psm`）或 ABBYY FineReader 以提升识别率。

---

## [2026-07-04 14:00]

**问题**：在陈纪修《数学分析》第三版教材上推进 MATH1607H 教学时，遇到多个工具链与资源获取问题：
1. `_text.pdf` 文字层编码损坏，`pdftotext` / PyMuPDF 提取中文几乎全部乱码。
2. 本地 Tesseract OCR 最初不在 PATH，且缺少 `chi_sim` 中文语言包。
3. `MATH1607H_book/` 中下载的 PDF 文件名含空格、括号，重命名时上册 Image Container PDF 被其他进程占用。
4. 尝试安装 poppler-data 修复 PDF 文字提取，失败。
5. 尝试用 WPS 提取 PDF 文字，WPS PDF 模块未安装。
6. 搜索 Z-Library 等替代来源，未找到带正常文字层的可下载版本。

**尝试与解决**：
1. 用 PyMuPDF 检查字体，确认 `_text.pdf` 使用 `GlyphLessFont` + `Identity-H`，文字层本身损坏。
2. 将 Tesseract 加入 PATH 并写进 `~/.bashrc`，下载 `chi_sim.traineddata` 到 `~/tessdata`，OCR 测试成功。
3. 用户解除文件占用后，完成四本陈纪修教材 PDF 的规范重命名。
4. 下载 poppler-data-0.4.12 并配置 `.xpdfrc`，因编码不匹配仍无法正确提取。
5. 确认 WPS 安装不完整，无 PDF 提取功能。
6. 发现复旦大学教务处 PDF 链接为 11 页样本，honeypdf 等来源估计与 archive.org 同源。

**解决**：以 Tesseract OCR 作为当前最可靠的中文教材文字提取方案；其余方案均不可行或效果不佳。

**后续**：
- 后续 lesson 讲义优先用 OCR 从 Image Container PDF 提取原文，再人工校对。
- 如需更高精度，可考虑 ABBYY FineReader 或寻找带正常文字层的其他 PDF 来源。
- 已将 OCR 环境配置写入 `course_status.md` 常用命令和 `~/.bashrc`。

---

## [2026-07-03 12:00]

**问题**：用户希望把《高数笔谈.pdf》纳入 T2AG 课程体系，并新增 MATH1607H 数学分析（荣誉）I。

**尝试与解决**：
1. 确认《高数笔谈》适合 MATH1607H / MATH1608H 作为辅助读物。
2. 在 `t2ag.md` 课程列表新增 MATH1607H。
3. 创建 `MATH1607H_MathematicalAnalysis/` 文件夹及内部结构。
4. 移动 `高数笔谈.pdf` 到 `MATH1607H_book/`。
5. 生成 `course_status.md` 和 `emo.md`。

**后续**：MATH1607H 课程初始化完成，默认教材定为陈纪修《数学分析》。

---

## [2026-07-03 13:00]

**问题**：用户发现 `lesson01.md` 没有引用《高数笔谈》原文，质疑内容来源。

**尝试**：
1. 使用 `pdftotext` 提取 PDF 文字，报错缺少 `GBK-EUC-H` CMap。
2. 使用 `pypdf` 提取，输出为空。
3. 尝试通过 Chocolatey 安装 tesseract OCR，失败（权限/锁文件问题）。
4. 发现用户已提前安装 tesseract，下载 `chi_sim.traineddata` 中文语言包。
5. 使用 PyMuPDF 将 PDF 页面渲染为图片，再用 Tesseract OCR 识别。

**解决**：OCR 成功读取《高数笔谈》第 9–10 页「1.1 极限」原文，并据此重写了 `lesson01.md`。

**后续**：
- `lesson01.md` 内容贴合原书（婴儿成长、百米赛跑、ε-δ 定义、蛋糕例子）。
- 在 `course_status.md` 中记录了 OCR 成功和重写过程。

---

## [2026-07-03 14:00]

**问题**：用户希望 T2AG 增加两项功能：
1. 记录问题与解决过程的日志（时间精确到小时）。
2. 支持根据网站链接下载书籍，并询问适合下载的格式。

**尝试与解决**：
1. 在 `t2ag.md` 中新增「问题与解决日志」章节，定义 `t2ag_problemlog.md` 的记录规则。
2. 在 `t2ag.md` 中新增「书籍下载规则」章节，明确推荐格式（EPUB > Text PDF > PDF > DjVuTXT > HTML）和不推荐格式（DAISY、LCP 加密、JP2 ZIP）。
3. 创建本文件 `T2AG_problem_log.md`。

**后续**：等待用户提供 archive.org 上的三本书链接，确认下载格式后开始下载。

---

## [2026-07-03 21:00]

**问题**：用户进一步要求：问题日志文件需要与 `t2ag.md`、`t2ag_changelog.txt`、`t2ag_case.txt` 同级，使用 `.txt` 格式，并随 T2AG 启动时检查、读取、自动生成。

**尝试与解决**：
1. 将 `T2AG_problem_log.md` 重命名为 `T2AG_problem_log.txt`。
2. 更新 `t2ag.md` 启动读取顺序：
   ```text
   t2ag.md → t2ag_changelog.txt → t2ag_case.txt → T2AG_problem_log.txt
   ```
3. 更新「与 t2ag.md 的关系」表格，将问题日志文件名改为 `.txt`。
4. 在「问题与解决日志」章节中增加自动生成规则：启动时若不存在，自动生成空文件。

**后续**：T2AG 启动流程现在包含四个文件；`t2ag_changelog.txt` 已记录该调整。

---

## [2026-07-03 22:00]

**问题**：用户要求将问题日志文件名从 `T2AG_problem_log.txt` 改为 `t2ag_problemlog.txt`（去掉下划线），并描述 `t2ag_problemlog.txt` 的格式。

**尝试与解决**：
1. 重命名文件：`T2AG_problem_log.txt` → `t2ag_problemlog.txt`。
2. 更新 `t2ag.md` 中所有引用（启动顺序、文件关系表、章节标题、自动生成规则）。
3. 更新 `t2ag_problemlog.txt` 自身引用。
4. 在 `t2ag.md` 中补充 `t2ag_problemlog.txt` 的格式说明。

**后续**：文件名统一为 `t2ag_problemlog.txt`；`t2ag.md` 已包含完整的格式规范。

---

## [2026-07-03 23:00]

**问题**：用户提出两点 T2AG 规则优化：
1. 确认最适合模型阅读的书籍格式，并允许一次下载多个格式。
2. 为保证模型记忆稳定，T2AG 初始化完成后需要设置教师 reply 的句子尾部格式。

**尝试与解决**：
1. 在 `t2ag.md`「书籍下载规则」中细化格式建议：
   - 数学/物理教材最佳组合：`PDF` + `Text PDF`
   - 无 Text PDF 时：`PDF` + `DjVuTXT`
   - 一般文字书：`EPUB`
   - 单格式优先级：`Text PDF` > `PDF` > `EPUB` > `DjVuTXT` > `HTML`
2. 新增「教师回复格式」章节：
   - 普通教学回复末尾统一加 `【教师回复结束】`
   - 灵感记录末尾写 `关于想法的讨论已记录。`
   - 情绪记录末尾写 `关于情绪的回应已记录。`

**后续**：`t2ag.md` 已包含完整的书籍下载格式建议和教师回复格式规范；`t2ag_changelog.md` 已记录。

---

## [2026-07-04 00:00]

**问题**：用户指出启动文件缺失处理逻辑有误：原规则说任一文件缺失都会进入初始化流程，但实际上只有 `t2ag_case.md` 需要专门初始化（代表师生基本状况），其他两个文件只需自动生成。

**尝试与解决**：
1. 修正 `t2ag.md`「如何使用」中的说明：
   - `t2ag_case.md` 缺失 → 自动生成并进入初始化流程
   - `t2ag_changelog.md` 缺失 → 自动生成空文件，不进入初始化
   - `t2ag_problemlog.md` 缺失 → 自动生成空文件，不进入初始化
   - `t2ag.md` 缺失 → 提醒用户提供或重新初始化项目

**后续**：启动流程逻辑更清晰；`t2ag_changelog.md` 已记录该修正。

---

## [2026-07-04 01:00]

**问题**：用户同意按模型建议，将四个 T2AG 相关文件统一为 Markdown（`.md`）格式，并按模型建议下载教材（PDF + Text PDF 双格式）。但下载 large PDF 的命令被用户拒绝。

**尝试与解决**：
1. 将 `t2ag_changelog.txt`、`t2ag_case.txt`、`t2ag_problemlog.txt` 重命名为 `.md`。
2. 更新 `t2ag.md` 中所有相关文件扩展名引用。
3. 在 `t2ag.md` 中新增「文件格式说明」：解释为何四个启动文件统一使用 `.md`。
4. 在 `t2ag.md`「书籍下载规则」中明确默认行为：数学/物理教材同时下载 `PDF` + `Text PDF`。
5. 尝试下载三本教材的 Image Container PDF（因 Text PDF 已存在），但下载命令被用户拒绝，未执行。

**后续**：
- 启动文件已全部改为 `.md`。
- 教材下载停留在已有的 Text PDF 状态；如需补充 Image Container PDF，需用户再次授权。
- `t2ag_changelog.md` 已记录该调整。

---

## [2026-07-04 02:00]

**问题**：用户指出教师回复句尾格式规则不应只写在 `t2ag.md`，而应在 `t2ag_case.md` 初始化完成后保存到 case 中。

**尝试与解决**：
1. 在 `t2ag_case.md`「教师介绍」下新增「回复格式」条目，写入标准结尾标记与特殊场景结尾。
2. 更新 `t2ag.md`「教师回复格式」章节，说明该规则在 `t2ag_case.md` 初始化时持久化。
3. 更新 `t2ag.md`「初始化流程」，新增第 9 步：初始化完成后在 `t2ag_case.md` 写入「回复格式」条目。
4. 修正 `t2ag_case.md` 中残留的旧引用 `t2ag_changelog.txt` → `t2ag_changelog.md`。

**后续**：教师回复格式规则现在同时存在于 `t2ag.md`（通用说明）和 `t2ag_case.md`（案例持久化）；`t2ag_changelog.md` 已记录该调整。

---

## [2026-07-04 03:00]

**问题**：用户明确本案例的教师回复句尾需要自定义：默认句尾为 `not hard`，本学生指定句尾为 `imurs.md`。

**尝试与解决**：
1. 将 `t2ag_case.md`「教师介绍 → 回复格式」中的标准句尾从 `【教师回复结束】` 改为 `imurs.md`，并注明默认句尾为 `not hard`。
2. 更新 `t2ag.md`「教师回复格式」章节：默认句尾为 `not hard`，`t2ag_case.md` 可根据学生要求覆盖。
3. 更新 `t2ag.md` 中灵感/情绪记录场景说明，使其句尾也跟随当前案例指定的标记。

**后续**：`t2ag.md` 保留默认规则，`t2ag_case.md` 记录本案例实际使用的 `imurs.md`；`t2ag_changelog.md` 已记录该自定义。

---

## [2026-07-04 04:00]

**问题**：用户此前误触拒绝导致 Image Container PDF 下载中断，现要求按模型建议完成教材下载，并强调下载前必须检查现有书籍；同时要求减少 T2AG 与 changelog 中的重复和逻辑混乱。

**尝试与解决**：
1. 检查 `MATH1607H_MathematicalAnalysis/MATH1607H_book/`：确认已存在《高数笔谈.pdf》、第三版上下册 Text PDF、第二版习题答案 Text PDF；缺失第三版上下册 Image Container PDF。
2. 从 archive.org 补下缺失的两本 Image Container PDF（上册 56.5 MB，下册 51.8 MB）；第二次下载因 SSL 握手失败重试后成功。
3. 在 `t2ag.md`「书籍下载规则 → 下载流程」中新增步骤：下载前先检查 `课程缩写_book/` 中是否已存在同名或同格式文件。
4. 精简 `t2ag.md`「问题与解决日志」章节：合并重复的自动生成规则与格式规范，修正格式描述为 Markdown，删除冗余示例。
5. 修正 `t2ag_changelog.md` 中 2026-07-03 21:00 条目的 confusing 文件名描述（`t2ag_problemlog.md` 调整为 `t2ag_problemlog.md` → 实际是从 `T2AG_problem_log.md` 调整为 `t2ag_problemlog.md`）。
6. 统一目录示例中的参考书文件夹为 `课程缩写_book/`。

**后续**：
- MATH1607H 教材现已同时具备 `PDF` + `Text PDF` 双格式。
- 下载前查重规则已写入 `t2ag.md` 和 `t2ag_changelog.md`。
- T2AG 与 changelog 的冗余和混乱点已清理。

---

## [2026-07-04 03:00]

**问题**：用户要求读取教材目录，按小时估算每章学习时长，并以 4 小时为 1 个 lesson 写入课程信息。

**尝试与解决**：
1. 通过 archive.org 元数据和网络检索获取陈纪修《数学分析》第三版上、下册目录，以及《高数笔谈》目录。
2. 由于 Image Container PDF 文字层 OCR 质量不佳，未直接通过 OCR 读完整目录，改用已验证的公开目录信息。
3. 按章节内容密度、证明难度、习题量估算每章学习时长。
4. 在 `MATH1607H_MathematicalAnalysis/course_status.md` 中新增「教材各章学习时长参考」章节，包含上册、下册、《高数笔谈》三张表，每张表给出小时数与 lesson 数。
5. 更新「临时学习计划」，按新时长重新划分阶段。

**后续**：`course_status.md` 已包含详细课时估算；`t2ag_changelog.md` 已记录该更新。

---

## [2026-07-04 05:00]

**问题**：用户质疑之前的学习时长估算缺乏参考资料，要求说明计算依据并鼓励查证。

**尝试与解决**：
1. 检索并找到可参考的高校教学大纲：
   - 复旦大学《数学分析》教学大纲（陈纪修教材配套），给出上册 120 学时、下册 152 学时的完整章节分配。
   - 上海交通大学致远学院教师主页，给出 MATH1607H 为 6 学分 96–128 学时、MATH1608H 为 4 学分 64 学时。
   - 惠州学院、瀚海网等大纲用于交叉验证积分与级数章节。
2. 重新计算 `course_status.md` 中的估算：
   - 以复旦各章学时为基准，按上交大 96–128 总学时缩放，并增加 20%–50% 自学时间。
   - 陈纪修上册：120–181 小时，60–91 lessons。
   - 陈纪修下册：152–230 小时，76–115 lessons。
   - 《高数笔谈》保持用户指定的 48 小时 / 24 lessons。
3. 在 `course_status.md`「教材各章学习时长参考」中新增「主要参考资料」「估算方法」「局限性」三节，列出具体网址与计算逻辑。
4. 更新「临时学习计划」中的陈纪修补回内容时长。

**后续**：估算已基于公开教学大纲重新校准，并明确标注为初步估算；`t2ag_changelog.md` 已更新。

---

## [2026-07-04 07:00]

**问题**：用户要求在制定大纲、定制教学方案、了解学生情况时，鼓励查找资料，优先参考当地前 2% 学校的信息；同时允许在学生学习欲望不强时调整难度和进度。

**尝试与解决**：
1. 在 `t2ag.md`「course_status.md 的生成与更新规则」中新增规则：制定教学方案时应主动检索并参考当地前 2% 学校的教学大纲、课程安排、评价标准与培养方案。
2. 新增调节条款：若学生学习欲望不强，可适当降低难度、放慢进度、减少拓展内容，优先保证基础掌握。
3. 在 `t2ag_case.md`「教师介绍」中新增「教学方案调研原则」，明确检索顶尖学校公开资料，并根据学生学习欲望调整难度与进度。

**后续**：教学方案制定原则已写入 `t2ag.md` 和 `t2ag_case.md`；`t2ag_changelog.md` 已记录。

---

## [2026-07-04 08:00]

**问题**：用户要求优化 `t2ag.md`，并给出 problem 日志格式。

**尝试与解决**：
1. 通读 `t2ag.md`，发现「生成与更新规则」条目过多、层次不清，且「笔记格式规范（通用）」实际为 C++ 课程专用。
2. 将 `course_status.md` 的「生成与更新规则」重组为三个子章节：教学方案生成、教学方案调节、学习时长与 lesson 划分。
3. 将「笔记格式规范（通用）」泛化为跨课程模板，并补充编程课与数学课特化说明。
4. 确认 `t2ag.md` 中「问题与解决日志」的格式规范已清晰可用。

**后续**：`t2ag.md` 已优化；`t2ag_changelog.md` 已记录。

---

## [2026-07-04 09:00]

**问题**：用户指出 `t2ag_problemlog.md` 的空文件模板和定位描述不准确：不应局限于「T2AG 学习过程中遇到的问题」，而应聚焦于 T2AG 使用过程中的问题、用户个性化需求、解决方案与优化调整。

**尝试与解决**：
1. 更新 `t2ag.md` 中「问题与解决日志」章节对 `t2ag_problemlog.md` 的定位描述。
2. 更新 `t2ag.md` 中空文件模板的引言文本。
3. 同步更新 `t2ag_problemlog.md` 文件顶部的引言文本。

**后续**：`t2ag_problemlog.md` 的定位已明确为 T2AG 使用、个性化定制与优化调整的记录；`t2ag_changelog.md` 已记录。

---

## [2026-07-04 04:00]

**问题**：用户要求将单个 lesson 时长从 4 小时降到 2 小时，并明确《高数笔谈》按 48 学时学完，共 24 个 lesson。

**尝试与解决**：
1. 在 `t2ag.md`「course_status.md 的生成与更新规则」中新增 lesson 划分原则：先通读章节划定学时，再按约 **2 小时 = 1 个 lesson** 拆分。
2. 重新计算陈纪修《数学分析》上、下册各章 lesson 数（全部翻倍）。
3. 调整《高数笔谈》总时长为 **48 小时**，共 **24 lessons**，并按 2 小时/lesson 重新分配 5 章时长。
4. 更新 `MATH1607H_MathematicalAnalysis/course_status.md` 中「教材各章学习时长参考」和「临时学习计划」两张表。

**后续**：lesson 长度规则已写入 `t2ag.md`；《高数笔谈》48 小时 / 24 lessons 的计划已落地到 `course_status.md`。

---

## [2026-07-04 05:00]

**问题**：用户指出之前的学习时长估算缺乏实际资料支撑，可能是凭空编造；要求将学习时长估算规则写入 `course_status.md` 初始化要求，避免胡编。

**尝试与解决**：
1. 承认此前估算主要基于数学分析课程的一般经验，并非来自实测数据或严格统计。
2. 在 `t2ag.md`「course_status.md 的生成与更新规则」中新增「学习时长估算原则」：
   - 必须基于教材目录、章节篇幅、定理/定义密度、例题与习题量的实际阅读或检索
   - 不得凭空编造
   - 估算结果须标注为「初步估算」，并根据实际教学进度持续修正
3. 在 `MATH1607H_MathematicalAnalysis/course_status.md` 顶部和「教材各章学习时长参考」章节增加「初步估算」声明，并说明估算依据。
4. 强调当前 `course_status.md` 中的数字仅为教学规划参考，需在实际学习中按真实进度调整。

**后续**：学习时长估算规则已同时写入 `t2ag.md`（全局规则）和 `course_status.md`（本课程声明）；后续每次修订时长都应说明依据。

---

## [2026-07-04 06:00]

**问题**：用户指出习题答案书也可以下载 Text PDF 版本。

**尝试与解决**：
1. 检查 `MATH1607H_book/` 中现有习题答案文件：`数学分析(陈纪修.第二版上下册)习题答案.pdf`（6.0 MB，572 页）。
2. 核对 archive.org 元数据：该文件实际格式为 Text PDF，且该习题答案书在 archive.org 上**只有 Text PDF，没有 Image Container PDF**。
3. 为保持与主教材 `_text.pdf` 命名一致，将文件重命名为 `数学分析(陈纪修.第二版上下册)习题答案_text.pdf`。
4. 更新 `MATH1607H_MathematicalAnalysis/course_status.md` 参考书目中的文件名。

**后续**：三本书现在统一为 PDF + Text PDF 双格式（主教材）或 Text PDF（习题答案）；`t2ag_changelog.md` 已记录。
