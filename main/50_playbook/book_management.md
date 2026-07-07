# 教材管理流程（book_management.md）

> 位置：`50_playbook/`。管理各课程 `[课程代码]_book/` 目录的结构与内容组织。
>
> **触发条件**：新建课程初始化教材目录、整理现有教材结构、添加新教材。

---

## 一、统一目录结构

每个课程的 `_book/` 目录遵循以下结构（子目录按需创建，空目录不建）：

```
[课程代码]_book/
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
- **特征**：在 course_status.md「教学方案」节指定的教材
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

## 三、README.md 必须内容

每个 `_book/README.md` 必须包含：

1. **教材清单表**：文件名 / 资料 / 来源 / 用途
2. **主教材用法说明**：如何按页推进、OCR 文本层怎么用
3. **参考书用途标注**：每本参考书写明"什么场景查它"
4. **使用规则**：教材优先级、查询顺序

## 四、新建课程时的初始化

1. 创建 `[课程代码]_book/` 目录
2. 写 `README.md`（即使暂无教材，也写"当前无教材，待添加"）
3. 不预建 primary/ reference/ 等子目录——有文件时才建
4. 下载/放入教材时按分类规则归入对应子目录

## 五、OCR 产物管理

- 活跃中的 OCR 产物（页面截图、raw 文本）放 `course_materials/ocr/`
- OCR 完成后，最终文本层并入 primary/（如 `_text.pdf`），中间产物移入 `archives/` 或删除
- `archives/tmp_*` 目录名带 `tmp_` 前缀的，可在 OCR 完成后直接删除

## 六、纪律

- **不复制教材内容到其他文件**：temppage 是教学时的临时缓存，不替代教材原文
- **archives 可删**：archives 里的文件不参与 doctor 检查，删除不影响系统
- **文件命名**：保留原始文件名（包括中文），不强制重命名——可读性优先于一致性
- **大小限制**：单文件 >100MB 的教材考虑分割或仅保留 OCR 文本层

## 七、关联文件

- `main/30_courses/[课程代码]_[课程名]/[课程代码]_book/` — 教材目录
- `main/30_courses/[课程代码]_[课程名]/course_status.md` — 教学方案指定主教材
- `main/50_playbook/first_run.md` — 步骤 5b 创建课程文件夹
- `main/50_playbook/new_course_init.md` — 新课程初始化流程
