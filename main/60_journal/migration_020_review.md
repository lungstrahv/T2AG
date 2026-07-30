# T2AG 0.2.0 Skeleton 迁移审查

- 日期：2026-07-26
- 目标：`t2ag-skeleton`
- 已执行操作：34
- active 文本改写：19
- 已退役路径：15
- 当前二次检查：pending / missing / collision / duplicate canonical / unknown binary 全为 0

## 人工检查清单

- [x] `main/` 的编号域恰为 00/10/20/30/40/50/60/70/80。
- [x] `10_student/` 无 Case/学生编号包装层。
- [x] Skeleton 不含课程、学生、ActivityRecord 或 Engagement 实例。
- [x] overlay registry 条目为 tombstone + generic successors。
- [x] registry 不存在两个 active artifact 共用 canonical。
- [x] OCR 与其他脚本使用新路径且无机器专属用户绝对路径。
- [x] `.venv`、`.recovery`、`.staging` 未被迁移或删除。
- [x] 第二次 `--check --target skeleton` 返回零待迁移项。
- [x] 首次非零报告已保护，零 pending 的幂等 `--apply` 不再覆写。
