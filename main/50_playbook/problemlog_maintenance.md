# problemlog 维护流程

**保护级别**：meta-playbook

> 本文件是 T2AG「技能固化」文档之一。
> 当会话中出现工具、环境、文件结构、规则执行或记忆治理问题时触发。
>
> **适用场景**：OCR、下载、依赖、路径、编码、课程初始化、课程恢复、doctor 修复、权威链冲突、playbook 过时、规则升级。
>
> **关联文件**：
> - 规则定义：`main/t2ag.md` → 「问题与解决日志 main/00_core/t2ag_problemlog.md」
> - 系统错题本：`main/00_core/t2ag_problemlog.md`
> - 启动索引：`main/00_core/t2ag_memory.md`
> - 结课流程：`main/50_playbook/session_close.md`
>
> **回路角色**：`t2ag_problemlog.md` 是
> `problemlog → 50_playbook/` 回路的流量台账，不是 mistake_bank 式衰减实例。
> 条目以稳定 `P-NNNN` 引用；是否已提炼 playbook 是结算字段，同类复发用计数器留痕。

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
| 课程进度、停顿点、累计课时 | `[课程]/progress.md` |
| 学生情绪或稳定学习状态 | `main/10_student/profile/profile.md` |
| 工具、环境、文件结构、规则执行、记忆治理问题 | `main/00_core/t2ag_problemlog.md` |

### 步骤 2：先查旧记录

在动手修复前，用关键词检索：

```powershell
rg -n "关键词1|关键词2" main/00_core/t2ag_problemlog.md main/playbook
```

若已有 playbook，优先按 playbook 执行；若旧日志有相似案例，先读对应条目再行动。

若命中同一根因的旧条目：

- 不新建 ID；`occurrence_count += 1`。
- 旧条目已经 resolved 又复发时，另做 `reopen_count += 1`，把状态改回 `open`。
- 已有 playbook 时，先按 playbook 复跑；若仍失败，更新旧条目的归因与处置，并修订该 playbook。

只有“标签相似但根因不同”时才分配新 ID；标签不是条目身份。

### 步骤 3：解决或标记阻塞

完成修复后，记录有效路径；若未解决，写清楚当前阻塞条件和下一步需要谁决策或提供什么信息。

### 步骤 4：追加 problemlog 条目

从文件顶部读取 `next_id`，分配后立即递增。按以下字段写入：

```markdown
## P-NNNN | [YYYY-MM-DD HH:00] | 一句话标题

- tags: [OCR, doctor]
- playbook_status: none
- occurrence_count: 1
- reopen_count: 0

**现象**：发生了什么；写可观察事实，不写推测。

**归因**：根因落在流程、规则或工具的哪一层。

**处置**：已执行的修复；未解决时写阻塞条件与下一步。

**判例价值**：低 / 中 / 高；说明未来什么场景应检索本条。

**状态**：open / resolved / blocked

---
```

字段规则：

- `tags` 至少一个，可多选；用于检索和同类计数，不替代稳定 ID。
- `playbook_status` 只能是：
  - `none`：尚未判断；
  - `candidate`：已达到提炼门槛；
  - `extracted:<path>`：已提炼并以路径指向存量原件；
  - `not_applicable:<reason>`：明确不应提炼。
- `occurrence_count` 是同一根因累计出现次数，初始为 1。
- `reopen_count` 是 resolved 后再次复发次数，初始为 0。
- `extracted:<path>` 是本台账的正式结算标记；不得只在正文中写“已更新 playbook”而漏填该字段。
- 历史条目无法可靠回填时使用明确的 `legacy_unknown`，不得留空或伪造结论。

### 步骤 5：同步 memory

若条目复用价值为中/高，更新 `main/00_core/t2ag_memory.md`：

- 「最近 5 条问题」加入一句摘要。
- 若会影响未来启动或行动顺序，加入「关键决策索引」。
- 保持全文不超过 150 行；必要时替换旧摘要，而不是无限追加。

### 步骤 6：判断是否升级为 playbook

满足任一条件时，向用户建议提炼或更新 playbook：

- 同一根因 `occurrence_count >= 2`。
- 单次问题高风险、步骤复杂，未来重复执行概率高。
- 已经形成稳定步骤，继续留在 problemlog 会导致下次还要重新理解。
- 已有 playbook 漏步骤，导致相同问题复发。

完成提炼后，把 `playbook_status` 写成 `extracted:<path>`；若判断不适合提炼，
写成 `not_applicable:<reason>`。同类问题再次出现时仍重开原条目并增加计数，
不得因为已经结算而新建重复条目。

---

## 三、常见问题与避坑

- **只写日志不消费**：无效。下次遇到相似任务前必须先查 memory 索引、playbook 和 problemlog。
- **把课程知识错误写进 problemlog**：错层。知识性错误进 `mistake_bank.md`。
- **把一切都升级成 playbook**：过度结构化。只有可复用流程才升级。
- **写完 problemlog 忘记 memory**：高复用条目会沉底。必须同步最近摘要或关键索引。
- **已有 playbook 还只追加日志**：说明流程文档没被维护。应更新 playbook。

---

## 四、关联文件

- `main/00_core/t2ag_problemlog.md` —— 系统/流程错题本
- `main/00_core/t2ag_memory.md` —— 启动索引与行动调度器
- `main/50_playbook/session_close.md` —— 结课时触发收割
- `main/00_core/t2ag_changelog.md` —— 规则或文件结构变更历史
- `[课程]/mistake_bank.md` —— 学生知识错题本
