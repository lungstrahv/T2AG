# 再生自证清单（REGEN_TEST.md）

> 骨架修改后逐项打勾，确认再生一个新实例不会断链。
> 全绿 = 新老师解压后能独立运转；有未勾项 = 先修再发布。

## A. 结构完整性

- [ ] 解压后 `main/t2ag.md` 存在且可读
- [ ] `main/00_core/` 下 9 个文件齐全
- [ ] `main/10_case/students/S001/` 存在（模板学生）
- [ ] `main/10_case/teachers/` 下 T001/T002/T003 存在
- [ ] `main/20_groups/` 存在且含 `_README.md`（无 G*.md = WARN 预期）
- [ ] `main/20_groups/overlays/` 不存在（首次启动后由 agent 创建）
- [ ] `main/30_courses/` 存在且含 `_README.md`（空 = 预期）
- [ ] `main/40_practices/` 存在且含 `_README.md`（空 = 预期）
- [ ] `main/50_playbook/` 下 15 个 playbook 齐全
- [ ] `main/60_journal/INDEX.md` 存在
- [ ] `main/70_tools/t2ag_doctor.py` 存在且零依赖可跑
- [ ] `main/skin/skin.yaml` 存在且 `active: SK001`
- [ ] `main/skin/SK001_default/skin.yaml` 存在
- [ ] `main/skin/SK001_default/01_welcome.txt` 存在
- [ ] `main/bin/t2ag` 存在

## B. doctor 零 FAIL

- [ ] `python main/70_tools/t2ag_doctor.py` 返回 0 FAIL
- [ ] WARN 仅来自空 20_groups（预期）

## C. 首次启动可走通

- [ ] `t2ag_memory.md`「上次课摘要」日期 = `—`
- [ ] `student_info.md` 中 SN01 指向 S001
- [ ] `first_run.md` 步骤 1-7 无断链引用
- [ ] `skin/skin.yaml` → `SK001_default/skin.yaml` → `01_welcome.txt` 链路通

## D. 指针一致性

- [ ] `t2ag.md` 结构清单登记的部件全部存在
- [ ] `t2ag.md` 版本号 = `AGENTS.md` 版本号 = `README.md` 版本号
- [ ] `t2ag_memory.md` 指针全为 `—`（骨架初始态）
- [ ] `t2ag_changelog.md` 最新条目与 memory「最近变更摘要」第 1 条一致

## E. 入口文件

- [ ] `AGENTS.md` 指向 `main/t2ag.md`（小写）
- [ ] `README.md` 品牌名为 `T2AG by T2AC`
- [ ] `.gitignore` 排除 `.venv/` `.tools/` `.uploads/` `.agents/` `__pycache__/`
