---
adr_id: ADR-0006
portable_key: course-type-owned-progression
status: accepted
authority_project: T2AG
source_evolution: [EV-0033]
supersedes: []
implementation_refs: [main/00_core/domain_model.md, main/50_playbook/book_management.md, main/50_playbook/progress_tracking.md, main/50_playbook/project_verification.md]
---

# ADR-0006：课程类型拥有非 Mastery 推进语义

T2AG 不再把 `course_type` 与四值 `course_driver` 视为完全正交轴。`course_type` 仍决定完成
证据；只有 Mastery Course 另选 `textbook-led / goal-led / project-led` Learning Mode。
Project Course 由 Project Plan 中下一个未闭合 Goal/Milestone 推进，Praxis Course 由真实行动、
反馈、复盘与下一行动推进；两者都没有独立 Learning Mode。

迁移期可读取旧 `default_driver/course_driver`，但不再把它们写成 Project/Praxis 的领域真相。
Mastery 的 project-led mode 仍是 Mastery；Project Goal 是计划节点，不是 goal-led mode。

## 后果

- 初始化、恢复、Doctor 与模板必须校验条件组合。
- Project Plan 复用 `course.md` + `progress.md` / `activity_ledger.md` 既有 owner，不新造第二真相源。
- Praxis 缺 driver 不构成不完整；必须由真实行动入口和行为证据证明推进。
