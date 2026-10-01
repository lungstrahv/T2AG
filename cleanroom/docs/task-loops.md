# 可复用任务回路 / Reusable task loops

回路保存常见任务的入口、关键顺序、完成条件和失败返回位置，让模型不必每次重新组织流程。先按当前任务选择一条，只读当前需要的步骤。已有的明确授权只消费一次，未变化的上下文无需反复读取；措辞、讲法和工具调用次数保持灵活。

Loops preserve task entry, essential order, completion conditions and failure return points. Select one for the current task and read only what is needed. Consume clear existing authorization once, reuse unchanged context and keep wording, teaching style and tool-call counts flexible.

```text
python -m t2ag_next workflow --language zh
python -m t2ag_next workflow feedback-save --language zh
python -m t2ag_next workflow save-close --language en
```

Python 接口为 `list_workflows(language)` 和 `get_workflow(name, language)`。唯一内容源是 `t2ag_next/workflows.py`；本页不复制六条完整表。前者返回入口列表，后者返回一条双语可选的短 JSON。它们不读写实例，也不执行其中的动作。CLI 由运行时提供同一读取接口。

The Python API is `list_workflows(language)` and `get_workflow(name, language)`. The sole catalog is `t2ag_next/workflows.py`. The first returns discovery rows; the second returns one short guide in the chosen language. Neither reads or mutates an instance or executes its listed actions. The CLI exposes the same read interface.

例如理解反馈保存的关键顺序是：

```text
原答 + 已冻结判据 → 直接反馈判断 → 保存原答/判断/停点 → 说明实际等待项 → 结束
                                  │
                                  └─ 结果未知 → lookup 原请求 → 必要时原样重试
```

For understanding feedback, the order is: actual answer and frozen criterion → prompt judgment → persist answer/judgment/cursor → report the waiting state → stop. If persistence is unknown, look up the original request before an identical retry. Correctness does not authorize the next block.

`steps[].actions` 是该步骤可能使用的现役动作，不是要求全部依次调用；正文中的“必要时”“仅当”决定分支。`commands` 是读取或检查入口。保存已存在事实不必另写一次；`activity.save` 用于尚未记录的课堂要点，保持停点与门不变。只暂离则 `session.close` 足够，完整结课另走已存在的结课语义。

`steps[].actions` lists available live actions, not mandatory calls. “If needed” and “only when” select branches. `commands` names read/check entry points. Already committed facts need no second write; `activity.save` preserves unrecorded notes without advancing the cursor or gates. A break only needs `session.close`; activity completion uses the existing closing contract.

指南不是授权，也不是执行器。当前实例、原始资料、版本和状态门仍决定动作能否发生。模型负责理解真实意图和教学语义，程序核可判定的条件；JSON 中的角色和原话仍是归因，不是宿主认证。若任务包含关键推理链，可沿用 `keystone.record` 与 `keystone.confirm` 保存逐步确认；普通反馈不因此增加确认手续。

The guide grants no authority and executes nothing. Current evidence, versions and state gates still decide whether an action can proceed. The model interprets intent and teaching meaning; programs check decidable conditions. JSON roles and statements remain attribution, not host authentication. Use existing `keystone.record` and `keystone.confirm` for an applicable reasoning chain; ordinary feedback gains no extra confirmation requirement.

先修结构性错误，允许少量可恢复的小错。失败就回到该回路写明的位置；同一核心失败没有新证据时，停止重复和扩大范围，说明具体阻点。相关检查已通过就结束。全量检查用于真实迁移、完整性调查或发行门，不用于每次作答、保存或读取指南。

Fix structural errors first while allowing small recoverable mistakes. Return to the stated point on failure; stop repeating or expanding work when the same core failure yields no new evidence. End after relevant checks pass. Full validation belongs to real migration, integrity investigation or release gates, not each answer, save or guide read.
