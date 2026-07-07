# 流程：结课仪式（session_close）

> 每次课结束时执行，保证下次开课能无缝恢复。

1. 更新对应课程 course_status.md（真相源）。
2. 刷新 t2ac_memory.md「当前状态指针」与「课程进度速览」缓存。
3. 追加 changelog / problemlog（如有），并同步 memory 摘要节。
4. 重写 memory「上次课摘要」节。
5. 跑 doctor，确认无 FAIL（含各 memory 节预算检查）。
6. Git 存档：`git add .` → `git commit` → `git push`（操作见 `50_playbook/git_workflow.md` 第三节）。
