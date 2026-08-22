# OCR 校对标准流程

**保护级别**：playbook

> 本文件是 T2AG「技能固化」文档之一。
> 当教材 Text PDF 文字层损坏、`pdftotext` / PyMuPDF 提取中文乱码时，按本流程使用 OCR 从 Image Container PDF 提取原文并校对。
>
> **适用场景**：所有课程（MATH1607H、CS1953 等）的教材原文提取。
>
> **关联文件**：
> - 规则定义：`main/t2ag.md` →「OCR 文本提取与校验规则」
> - **产物权威（EV-0012）**：`main/50_playbook/source_page_assets.md` —— 核验文本/OCR 写入 Course
>   `source_assets`（权威）；PNG 仅可选写入 `book/.cache`（可重建派生，非真相源）；Lesson 只存 Snapshot/Map 引用。
> - 通用要求：`main/10_student/profile/learning_path.md` →「OCR 工具选择与结果校对」
> - 问题日志：`main/00_core/t2ag_problemlog.md`
> - 课程命令：对应课程 `progress.md` →「常用命令」
>
> **已退役**：`lessonXX/working_pages/` 路径已在 0.2.2 批 S3 退役；历史摘录见各课 `archive/`。
> **新建** 校对走 preparation Snapshot + source_assets，不复用 legacy 路径。

---

## 零、依赖与模型下载闸门

1. 默认优先使用已经存在的工具或模型视觉识读，不因进入课程、doctor、OCR 失败或
   “效果可能更好”而自动安装包。
2. `pip install`、包升级、OCR 权重和模型首次下载都必须先向用户说明：
   包/模型名称、用途、预计下载量、预计磁盘占用、安装/缓存位置和是否可复用。
3. 只有用户明确批准本次动作后，才可使用项目 `.venv\Scripts\python.exe -m pip`
   安装锁定版本；禁止向全局 Python 重复安装，禁止删除重建整个 `.venv`。
4. 若依赖树会引入 Torch、Transformers、ONNX、OpenCV 等大型组件，必须把它们列入
   体积说明；不能把 `pix2text` 描述成“纯 Python、依赖较轻”。
5. lite 只供线上模型审查，任何安装或模型下载建议都只能作为审查发现返回，不执行。

---

## 一、何时触发 OCR

满足以下任一条件，即触发 OCR 流程：

1. **Text PDF 文字层损坏**：用 PyMuPDF 检查字体，若出现 `GlyphLessFont` + `Identity-H`，说明文字层编码映射缺失，`pdftotext` / PyMuPDF 提取中文几乎全部乱码。
2. **公式为图片**：教材中的数学公式以图片形式嵌入，文字层无法提取。
3. **只有 Image Container PDF**：下载的教材仅有图片型 PDF，无 Text PDF 或 DjVuTXT。
4. **提取结果不可读**：直接提取的文字存在大量乱码、缺字、错字，无法用于教学。

> **不触发 OCR 的情况**：Text PDF 文字层完好、可直接提取可读文本时，优先使用 `pdftotext` 或 PyMuPDF 直接提取，不必走 OCR 流程。
>
> **判断顺序**：有结构化源（Text PDF / LaTeX 源 / EPUB+MathML）就用结构化源；只有 PDF 时，先看是不是 Text PDF，不是才 OCR。

---

## 二、OCR 工具优先级

| 优先级 | 工具 | 适用场景 | 获取方式 | 备注 |
|---|---|---|---|---|
| 1 | **模型视觉识读原图** | 公式密集的数学教材、符号识别 | 无需安装，直接读取渲染后的 PNG | 零安装、对公式最准、可逐符号转录 |
| 2 | **PaddleOCR** | 中文教材通用 OCR | 用户授权后安装锁定版本 | 开源，本地运行；可能下载额外模型 |
| 3 | **Pix2Text** | 含大量数学公式的教材 | 用户授权后安装锁定版本 | 会引入大型 ML 依赖和模型缓存 |
| 4 | **MathPix API** | 数学公式精确识别 | mathpix.com（需 API key） | 在线服务，公式识别效果最佳，需网络 |
| 5 | **Tesseract** | 无上述工具时的兜底方案 | `C:\Program Files\Tesseract-OCR` | 数学符号识别差，需大量人工校对 |

### 为什么模型视觉识读原图排第一

1. **零安装**：无需 pip install、无需配置环境变量、无需下载语言包，直接读取 PNG 原图即可。
2. **对公式最准**：模型具备多模态视觉能力，能逐符号识别数学公式（上下标、并集、无穷、属于、集合括号等），错误率远低于 Tesseract。
3. **可逐符号转录**：模型可对照原图逐行、逐符号转录，过程中即可完成第一轮校对，减少后续人工校对工作量。
4. **上下文理解**：模型可结合教材上下文（章节、定义、定理编号）推断 OCR 难以识别的符号，降低误识别率。

> **降级策略**：若公式太多、页面太长，模型视觉识读不便（超出上下文或识别效率低），降级使用 Pix2Text 批量识别；Pix2Text 不可用时降级使用 Tesseract 兜底。

---

## 三、完整步骤

### 步骤 1：渲染 PNG 到 Course `.cache`（默认 300 DPI）

使用 PyMuPDF（`fitz`）或等价工具，将目标 **SourceDocument PDF** 页面渲染为 PNG。

| 规则 | 要求 |
|---|---|
| **默认** | 全书统一 **300 DPI、RGB**；与 `render_profile` `pdf-300dpi-rgb-v1` 一致 |
| **下限** | 不得低于 **200 DPI**（糊字、OCR 崩溃） |
| **难页例外** | 小字/密公式/污迹可另渲 **400–600 DPI**，写入 **另一** `render_profile`，不覆盖默认 300 键 |
| **禁止** | 同一课无标记混用 180 与 300；新建核验不得再产出混档默认图 |

页码：PDF **1-based 页 N** ↔ 渲染 `page[N-1]`；文件名中的索引必须与 `pdf_page_index=N` 一致。

**新建输出路径（canonical）**：

```text
40_course/<COURSE_ID>/book/.cache/source_pages/
  <source_document_sha256>/<render_profile>/page_<pdf_index>.png
```

工具中立契约（**禁止**新建 Lesson-local `ocr_page.py` 或任何 `working_pages/scripts`）：

```text
输入：book/primary 下 SourceDocument PDF；pdf_page_index = N（人类页码）
渲染：page[N-1] → PNG，默认 pdf-300dpi-rgb-v1
输出：仅写入上列 Course .cache 键路径
禁止：写入 lessons/**/working_pages/pages|raw_ocr|scripts
```

示例（占位；路径按课程与 document SHA 替换）：

```powershell
# 概念示例：用 PyMuPDF 将 PDF 第 21 页渲染到 Course .cache（写盘前须用户/任务授权）
# page index: human N=21 → fitz page 20
# out: main/40_course/<COURSE_ID>/book/.cache/source_pages/<doc_sha>/pdf-300dpi-rgb-v1/page_21.png
```

> **路径与环境**：教材 PDF 从课程根 `book/primary/` 读取。Tesseract 通过 PATH、
> `TESSERACT_CMD` 或 `--tesseract` 定位；不得在脚本中保存用户名绝对路径，也不得自动
> 安装依赖或改造 `.venv`。

### 步骤 2：优先用模型视觉识读原图逐符号转录

将 **Course `.cache`** 中刚渲染（或已存在）的 PNG 用模型视觉能力直接识读，逐行、逐符号转录为文本。

**操作要点**：
- 逐页识读，每页对照原图完整转录
- 数学公式逐符号核对：上下标、并集 ∪、交集 ∩、属于 ∈、包含 ⊂、无穷 ∞、花括号 {} 等
- 转录过程中即可完成第一轮校对，发现可疑符号立即对照原图确认
- 汉字识别不确定时，结合上下文推断

> 此步骤产出的文本质量最高，可直接作为校对后的基础文本。**持久写入**见步骤 6
> （`source_assets`），不得落到 Lesson `working_pages`。

### 步骤 3：若公式太多视觉识读不便，用 Pix2Text

当页面公式密集、模型视觉识读效率降低时，使用 Pix2Text 批量识别：

```python
from pix2text import Pix2Text

p2t = Pix2Text()
# 输入必须是 Course .cache 中的页图，不是 lessons/**/working_pages/pages
text = p2t.recognize(
    "main/40_course/<COURSE_ID>/book/.cache/source_pages/"
    "<source_document_sha256>/pdf-300dpi-rgb-v1/page_21.png"
)
print(text)
```

> Pix2Text 专门识别数学公式，对 LaTeX 符号支持好，适合数学教材批量处理。
>
> 首次使用通常会下载模型。执行前必须按“依赖与模型下载闸门”报告体积与缓存位置并取得授权；
> 未授权时停在这里，继续使用模型视觉识读或现有工具。

### 步骤 4：Tesseract 兜底

当模型视觉识读和 Pix2Text 均不可用时，使用 Tesseract 作为兜底方案：

```bash
# 确保 Tesseract 在 PATH 中
export PATH="$PATH:/c/Program Files/Tesseract-OCR"
export TESSDATA_PREFIX="$HOME/tessdata"

# 输入：Course .cache PNG；输出：Course source_assets raw OCR（禁止 working_pages）
tesseract \
  "main/40_course/<COURSE_ID>/book/.cache/source_pages/<doc_sha>/pdf-300dpi-rgb-v1/page_21.png" \
  "main/40_course/<COURSE_ID>/book/primary/source_assets/<document_id>/raw_ocr/page_21_raw" \
  -l chi_sim+eng
```

> 也可使用 `pytesseract` Python 接口，但 Bash 直接调用 / 文件输出模式更稳定（避免 subprocess stdout 编码问题）。
>
> Tesseract 对数学符号识别较差，**必须**在步骤 5 中重点校对。
> **禁止**将输出写到 `lessons/**/working_pages/raw_ocr/`。

### 步骤 5：逐行对照原图校对

无论使用哪种 OCR 工具，**都必须逐行对照原图进行人工校对**。

**校对流程**：
1. 将 OCR 结果与 **Course `.cache`** 中的 PNG 原图并排对照
2. 逐行核对文字，重点关注数学符号
3. 对无法理解的汉字组合、缺字、疑似错字，**联网搜索**教材目录、官方出版信息、网络题库或 Wikipedia 进行交叉验证
4. 关键定义、定理编号、公式必须对照 Image Container PDF 图片做最终核对
5. 校对过程中的错误模式记入「常见错误对照表」（见下文），持续积累

### 步骤 6：校对后写入 Course 页资产（权威）

**优先路径（EV-0012）** — 详见 `source_page_assets.md`：

- **校对文本** → `book/primary/source_assets/<document_id>/pages/page_<pdf_index>.md`（持久）
- **raw OCR** → `book/primary/source_assets/<document_id>/raw_ocr/page_<pdf_index>_raw.txt`
- **页图 PNG** → `book/.cache/source_pages/<doc_sha>/<render_profile>/page_<pdf_index>.png`（可重建缓存）
- **Lesson** → 更新 `LessonScope` / `LessonMap` / **新** `LessonPreparationSnapshot` + load receipts
- 工具：`python -B main/70_tools/t2ag_source_pages.py prepare ...`
- prepare / Context 对 LessonMap 与资产的校验使用**文件原始字节**（含 CRLF）；不得仅按
  `read_text` 规范化后的文本宣称 hash 一致。

**Legacy Compatibility**（已退役，0.2.2 批 S3）：

- 历史可读：各课 `archive/` 中的 tombstone 归档文件。
- **新建核验禁止**向 `working_pages` 路径写入；新输出只走 `source_assets` / `.cache`。
- **结课不得删除**已提升为 Course `source_assets` 的持久证据。
- `working_pages` 目录清理不再需要；历史摘录已归档。
```

新字段（可选，工具可写）：`lesson_scope_version`、`preparation_snapshot_id`、`short_document`。

---

## 四、常见错误对照表

OCR 对数学符号识别错误率极高，校对时务必对照下表逐项排查：

| 实际符号 | OCR 常见误识别 | 示例 |
|---|---|---|
| `A` / `B` / `C` | `4` / `8` / `(` | `A_n` → `4,` |
| `∪`（并集） | `U` / `J` / `L` | `⋃ A_n` → `U 4` |
| `∞`（无穷） | `o` / `ce` / `8` | `+∞` → `+o` |
| `∈`（属于） | `s` / `e` | `n ∈ Z` → `nsZ` |
| `⊂` / `⊃` | `C` / `D` | `S ⊂ T` → `SC T` |
| `{}`（花括号） | `\|` 或遗漏 | `{x \| ...}` → `\|x...\|` |
| 下标 `x_{ij}` | 中文乱码或遗漏 | `x_{12}` → `X12` 或 `氛 1` |
| 省略号 `…` | 遗漏或 `...` | `0,1,-1,…` → `0 T2 2 r` |
| 逗号 `,` | 空格或遗漏 | `0, 1, -1` → `0 1 1` |
| `≥` / `≤` | `乏` / `《` | `x ≥ 0` → `x 乏 0` |
| `≠` | `三` / `门` | `i ≠ j` → `i 三 门` |
| `∅`（空集） | `么` / `0` | `∅` → `么` |

> **使用方式**：校对时对照此表，将 OCR 结果中的可疑字符逐一还原。随着校对经验积累，可向此表补充新的错误模式。

---

## 五、校对要点

### 数学公式逐符号核对

- **上下标**：`x_{ij}`、`a_n`、`x^2` 等下标上标极易被识别为同行文字或乱码
- **集合符号**：`∪`、`∩`、`∈`、`∉`、`⊂`、`⊃`、`⊆`、`∅` 必须逐一核对
- **逻辑符号**：`∀`、`∃`、`⇒`、`⇔`、`∧`、`∨` 容易被误识别为字母或遗漏
- **希腊字母**：`ε`、`δ`、`α`、`β`、`λ`、`∞` 等容易与英文字母或汉字混淆
- **花括号与竖线**：`{x | P(x)}` 中的花括号和分隔竖线极易被误识别

### 联网交叉验证不确定术语

- 对无法理解的汉字组合、缺字、疑似错字，联网搜索教材目录、官方出版信息、网络题库或 Wikipedia 进行交叉验证
- 关键定义、定理编号、公式必须对照 Image Container PDF 图片做最终核对
- 若教材有公开目录或章节标题，可对照确认 OCR 结果的章节归属

### 其他校对要点

- **页码连续性**：检查 OCR 结果的页码与教材实际页码是否一致
- **定理编号**：定理、引理、例题编号（如「定理 1.1.1」「例 1.1.1」）必须准确
- **段落完整性**：检查是否有段落遗漏或截断
- **标点符号**：中文逗号、句号、顿号易被误识别为空格或遗漏

---

## 六、记录与沉淀

- **问题日志**：OCR 踩坑与成功经验记入 `main/00_core/t2ag_problemlog.md`
- **环境配置**：稳定的 OCR 环境配置（PATH、`TESSDATA_PREFIX` 等）写入对应课程 `progress.md`「常用命令」和 `~/.bashrc`
- **错误模式**：新发现的 OCR 错误模式补充到本文件「常见错误对照表」

---

## 七、注意事项

1. **OCR 不能替代人工校对**：任何 OCR 工具都无法保证 100% 准确，数学公式部分必须逐符号人工核对。
2. **原始结果保留备查**：`page_XX_raw.txt` 保留原始 OCR 结果，不修改，便于追溯校对过程。
3. **核验文本持续累积**：优先写入 Course `source_assets`；legacy `source_excerpt.md`
   若仍存在可继续追加，但**课程结束不得自动删除**；删除须 E 的 exact RT3。
4. **优先使用模型视觉识读**：在条件允许时，优先使用模型视觉识读原图，可显著减少校对工作量。
5. **DPI 纪律**：默认全书 **300 DPI**；不得低于 200；难页可另档 400–600；**禁止**同一课无标记混用 180/300（见 `source_page_assets.md` §1.1）。
6. **批量处理效率**：多页 OCR 时，可先批量渲染 PNG，再逐页识读校对，避免反复打开 PDF。
