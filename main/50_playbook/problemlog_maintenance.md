# problemlog 维护流程

**保护级别**：meta-playbook

> 本文件是 t2ac「技能固化」文档之一。
> 当会话中出现工具、环境、文件结构、规则执行或记忆治理问题时触发。
>
> **适用场景**：OCR、下载、依赖、路径、编码、课程初始化、课程恢复、doctor 修复、权威链冲突、playbook 过时、规则升级。
>
> **关联文件**：
> - 规则定义：`main/t2ac.md` → 「问题与解决日志 main/00_core/t2ac_problemlog.md」
> - 系统错题本：`main/00_core/t2ac_problemlog.md`
> - 启动索引：`main/00_core/t2ac_memory.md`
> - 结课流程：`main/50_playbook/session_close.md`

---

## 一、触发条件

- 遇到系统/流程问题，并且该问题未来可能再次出现。
- 用户指出某个机制没有被有效利用，需要补规则。
- doctor 报错、缓存与真相源冲突、课程结构不一致。
- 已有 playbook 执行失败、过时或漏掉关键步骤。

---

## 二、完整步骤

### 步骤 1：先分流

判断问题应该写到哪里：

| 问题类型 | 写入位置 |
|---|---|
| 学生概念、证明、计算、代码理解错误 | `[课程]/mistake_bank.md` |
| 课程进度、停顿点、累计课时 | `[课程]/course_status.md` |
| 学生情绪或稳定学习状态 | `t2ac_emo.md` / `10_case/students/Sxxx/` |
| 工具、环境、文件结构、规则执行、记忆治理问题 | `main/00_core/t2ac_problemlog.md` |

### 步骤 2：先查旧记录

在动手修复前，用关键词检索：

```powershell
rg -n "关键词1|关键词2" main/00_core/t2ac_problemlog.md main/playbook
```

若已有 playbook，优先按 playbook 执行；若旧日志有相似案例，先读对应条目再行动。

### 步骤 3：解决或标记阻塞

完成修复后，记录有效路径；若未解决，写清楚当前阻塞条件和下一步需要谁决策或提供什么信息。

### 步骤 4：追加 problemlog 条目

按以下字段写入：

```markdown
## [YYYY-MM-DD HH:00]

**标签**：OCR / 下载 / 环境 / 文件结构 / 课程初始化 / 课程恢复 / 权威链 / doctor / 记忆治理 / playbook / 其他

**触发条件**：下次什么情况下应该想起这条记录。

**复用价值**：低 / 中 / 高

**是否已提炼 playbook**：否 / 候选 / 已提炼：`main/50_playbook/xxx.md`

**问题**：一句话概括问题或需求。

**尝试**：
1. 尝试及结果

**解决**：最终如何解决，或当前状态。

**后续**：修改了哪些文件、规则或流程；是否需要更新 memory / playbook。

---
```

### 步骤 5：同步 memory

若条目复用价值为中/高，更新 `main/00_core/t2ac_memory.md`：

- 「最近 5 条问题」加入一句摘要。
- 若会影响未来启动或行动顺序，加入「关键决策索引」。
- 保持全文不超过 150 行；必要时替换旧摘要，而不是无限追加。

### 步骤 6：判断是否升级为 playbook

满足任一条件时，向用户建议提炼或更新 playbook：

- 同类问题出现 2 次以上。
- 单次问题高风险、步骤复杂，未来重复执行概率高。
- 已经形成稳定步骤，继续留在 problemlog 会导致下次还要重新理解。
- 已有 playbook 漏步骤，导致相同问题复发。

---

## 三、常见问题与避坑

- **只写日志不消费**：无效。下次遇到相似任务前必须先查 memory 索引、playbook 和 problemlog。
- **把课程知识错误写进 problemlog**：错层。知识性错误进 `mistake_bank.md`。
- **把一切都升级成 playbook**：过度结构化。只有可复用流程才升级。
- **写完 problemlog 忘记 memory**：高复用条目会沉底。必须同步最近摘要或关键索引。
- **已有 playbook 还只追加日志**：说明流程文档没被维护。应更新 playbook。

---

## 四、关联文件

- `main/00_core/t2ac_problemlog.md` —— 系统/流程错题本
- `main/00_core/t2ac_memory.md` —— 启动索引与行动调度器
- `main/50_playbook/session_close.md` —— 结课时触发收割
- `main/00_core/t2ac_changelog.md` —— 规则或文件结构变更历史
- `[课程]/mistake_bank.md` —— 学生知识错题本
