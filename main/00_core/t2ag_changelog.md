# T2AG 变更历史

> 按需展开。启动时不全量读，由 t2ag_memory.md 的「最近变更摘要」按行号指针索引。
> 追加条目时同步更新 memory 摘要，并对超出 memory 节预算的旧条目做"下沉"处理。

---
---

## [0.0.06] 骨架初始化

- 采用数字前缀命名规范（00_core ~ 70_tools）
- memory 改为分节预算制
- doctor 预留 venv/env 与版本一致性检查位
- 宪法化（t2ag.md 五章结构 + 结构清单 + 修宪程序）
- 复利回路模式 + 三级 playbook 体系
- 课程组规则 + 考试子系统 + 项目线验证 + Git 操作手册
- **v0.0.06 整治**：
  - 全局 T2AC→T2AG 改名（文件名 + 内容 + 路径引用）
  - 补缺失 playbook（exam_protocol / exam_bank_spec / lesson_recover / ocr_correct_flow）
  - 清理数据污染（去实例化：changelog / git_workflow / course_group_rules / pattern_retire_loop）
  - 删除空目录（20_groups / 30_courses / 40_practices——首次启动时创建）
  - 修路径前缀 bug（50_50_ → 50_ 等）
  - 修 doctor 豁免逻辑：空 20_groups → WARN 而非 FAIL
  - 修 doctor 文件名大小写（t2ag.md → t2ag.md，跨平台兼容）
  - skin 文件夹（welpic → skin，编号 + README 索引）
  - doctor 验证：0 FAIL 1 WARN（空 20_groups 预期 WARN）
