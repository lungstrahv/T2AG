# 教材管理流程（book_management.md）

> 位置：`50_playbook/`。管理各课程 `book/` 目录的结构与内容组织。
>
> **触发条件**：新建课程初始化教材目录、整理现有教材结构、添加新教材。
>
> **路径解析约定**：课程教材目录固定为
> `main/40_course/<COURSE_ID>/book/`。

---

## 一、统一目录结构

每个课程的 `book/` 目录遵循以下结构（子目录按需创建，空目录不建）：

```
book/
  README.md                      ← 教材清单（必须有）
  primary/                       ← 主教材（每课必读的书）
  reference/                     ← 辅助参考书（换讲法、补概念）
  course_materials/              ← 课程配套材料（不是"书"）
    slides/                      ← 课件
    syllabus/                    ← 教学大纲
    code_samples/                ← 代码清单
    supplements/                 ← 补充材料（题单、摘要等）
    exercises/                   ← 习题
    ocr/                         ← OCR 工作产物（活跃中）
  archives/                      ← 原始下载包 / 已完成使命的临时产物
```

## 二、分类规则

### primary/ — 主教材

- **判据**：教学流程中每课必读、agent 按原文讲解的书
- **特征**：在 progress.md「教学方案」节指定的教材
- **格式**：PDF / EPUB / 纯文本（如有 OCR 文本层，放同名 `_text.pdf` 或 `.txt`）
- **一课可有多本主教材**：如中文版 + 英文版对照，都放 primary/

### reference/ — 辅助参考书

- **判据**：概念讲不清时"换一个讲法"的书，不是每课必读
- **特征**：在 README 中标注用途（如"编程思维补充""网络概念入门"）
- **与 primary 的区别**：reference 是 agent 可选查询的，primary 是必须按页推进的

### course_materials/ — 课程配套材料

- **判据**：不是"书"，是学校/教师配套发放的教学材料
- **按实际内容建子目录**：有什么内容建什么目录，不预建空目录
- **常见子目录**：
  - `slides/` — PPT/PPTX/TXT 课件
  - `syllabus/` — 教学大纲
  - `code_samples/` — 教材代码清单
  - `supplements/` — 补充材料（题单、摘要、笔记）
  - `exercises/` — 习题集
  - `ocr/` — OCR 工作产物（活跃中，完成后移入 archives 或删除）

### archives/ — 归档

- **判据**：原始下载包（zip）、已完成使命的临时产物
- **规则**：archives 里的文件可随时删除不影响教学；保留只为溯源

## 三、课程驱动与来源使用

每门课在 `progress.md` 声明 `course_driver`；它表示什么决定下一课，而不是课程行政分类。

| course_driver | 推进依据 | 来源规则 |
|---|---|---|
| `textbook` | 教材章节和页码 | `progress.md` 指定主教材；lesson 只记精确页码，不重复登记 ER |
| `goal` | 明确能力目标 | 每个 lesson 指定一个主要可信来源；跨课程来源可引用 ER |
| `project` | 可运行产物和里程碑 | 仓库、测试、数据和官方文档是主要证据，教材按需查询 |
| `praxis` | 真实行动、反馈和长期修炼 | 书籍、数据、官方资料和行为记录组成证据束，不要求单一教材主导 |

`course_type: praxis` 是实践修炼型课程，不是通识课，也不是 `course_type: project`（后者的裁判可复现，praxis 的裁判是开放世界后果——轴定义见 `00_core/domain_model.md` §2.0）。它必须在课程说明中保留以下声明：

> 本课程面向开放世界中的不确定性。仅通过 T2AG 学习，其效果仍有待提升；T2AG 可以提供结构、资料、记录、反馈与复盘，但不能替代真实行动、风险承担、时间投入和生命经验。本课程的完善需要学生自己生命力的参与。

Praxis 课程必须声明真实行动入口和行为证据；仅在对话中理解概念不能证明课程完成。来源是行动的证据，不是课程顺序本身。

## 四、外部学习资料入库

外部资料先按复用范围分类，再决定登记位置。资源索引是登记真相源，课程 README 只保留课程专属资料和共享资源 ID，不复制共享说明。

### 1. 在线资源

- **跨课程在线资源**：同时服务两门及以上课程、尚未建立目标课程但未来可能复用、或属于系统通用资料库/公开课/公共工具的，登记到 `main/40_course/_shared/external_resources.md`。原则上只登记 URL 和使用信息，不下载全文。
- **单门课程在线资源**：登记到对应课程的 `book/README.md`，不得再登记到共享索引。

### 2. 下载文件

- **单门课程文件**：按本文件第一节存入对应课程的 `book/`：

```text
book/
  primary/ reference/
  course_materials/{slides,syllabus,code_samples,supplements,exercises,ocr}/
  archives/
```

- **跨课程文件**：只有确需离线保存且被两门以上课程共同使用时，才存入 `main/40_course/_shared/library/[资源ID]/`。不得复制到多个课程的 `_book/`；其他课程通过共享索引中的本地相对路径引用。
- **教材页证据（EV-0012）**：核验文本与 raw OCR 在
  `book/primary/source_assets/<document_id>/` **Course 持久**持有；可重建 PNG 在
  `book/.cache/source_pages/`（CacheEviction，见 `source_page_assets.md` 与
  `batch_workorder_spec` §1.2.1）。Lesson **不**长期复制教材二进制。
- **Legacy 已退役**：原 `lessons/lessonXX/working_pages/` 路径已在 0.2.2 批 S3 退役；历史摘录见各课 `archive/`。
- Exercise 作答图片放对应 Attempt 的 `assets/`；可复用教学资料放
  `book/course_materials/supplements/`。确认长期跨课使用后再转入 `_shared/library/`。
- **lite 审查快照**：不打包 PDF、教材、压缩包、环境、缓存、生成资产或
  `_shared/library/` 二进制内容；被排除的文件在索引中标记“主项目持有”。

### 3. 共享索引登记字段

`external_resources.md` 每项至少登记一行：

| 资源 ID | 名称 | 类型 | URL/本地路径 | 适用课程 | 适用知识点 | 用途 | 使用方式 | 来源与许可 | 最后核验日期 |
|---|---|---|---|---|---|---|---|---|---|
| 全局唯一 | 资料名称 | 网站/公开课/教材/题库/工具 | 唯一 URL 或本地相对路径 | 课程代码列表 | 章节或主题 | 主教材/辅助解释/练习/查证 | 在线读取/下载/按需查询 | 发布者及公开使用情况 | 最近核验日期 |

同一 URL 或本地文件只能登记一次。在线 URL 只需格式有效，不要求 doctor 联网；本地相对路径必须真实存在（lite 中主项目持有的排除文件除外）。

## 五、README.md 必须内容

每个 `book/README.md` 必须包含：

1. **教材清单表**：文件名 / 资料 / 来源 / 用途
2. **主教材用法说明**：如何按页推进、OCR 文本层怎么用
3. **参考书用途标注**：每本参考书写明"什么场景查它"
4. **使用规则**：教材优先级、查询顺序

## 六、新建课程时的初始化

1. 创建 `book/` 目录
2. 写 `README.md`（即使暂无教材，也写"当前无教材，待添加"）
3. 不预建 primary/ reference/ 等子目录——有文件时才建
4. 下载/放入教材时按分类规则归入对应子目录

## 七、OCR / 页资产产物管理

- **权威链**：`SourceDocument`/原版 PDF + Course `source_assets`（核验文本 / raw OCR 及元数据）。
  **`.cache` PNG 不是真相源**：仅为可从 PDF 按 `render_profile` **重建的派生物**，可被 CacheEviction 驱逐；缺失不得改写教学事实。流程见 `source_page_assets.md` 与 ADR-0001。
- `course_materials/ocr/` 仅作可选工作暂存；完成后应并入 `source_assets` 或 archives，不得成为第二真相源。
- 最终可读文本层可另存 primary 的 `_text.pdf`；**页级核验**以 `source_assets/pages/` 为准。
- `archives/tmp_*` 可在完成后删除；**不得**用 archives 清理代替 CacheEviction 规则。
- 结课：**不**删除持久 `source_assets` 或 PDF；可对 `.cache` 合法驱逐。

## 八、纪律

- **不按 Lesson 复制教材二进制**为权威；Lesson 持引用与 Snapshot。
- **archives 可删**：不参与 doctor 权威链（页资产除外）。
- **文件命名**：主教材保留原始文件名；页资产用稳定 `page_<pdf_index>`。
- **大小限制**：单文件 >100MB 的教材考虑分割或仅保留文本层 + 页资产。

## 九、关联文件

- 课程教材目录：`main/40_course/<COURSE_ID>/book/`
- 课程教学方案：按 §5 解析出的 `progress.md`
- `main/50_playbook/first_run.md` — 步骤 5b 创建课程文件夹
- `main/50_playbook/new_course_init.md` — 新课程初始化流程
