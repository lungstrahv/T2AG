# t2ag 变更历史

> 按需展开。启动时不全量读，由 t2ag_memory.md 的「最近变更摘要」按行号指针索引。
> 追加条目时同步更新 memory 摘要，并对超出 memory 节预算的旧条目做"下沉"处理。

---
---

## [0.0.06] 骨架重建（全小写目录名）

- 全局 T2AC→T2AG 改名 + 全小写目录名统一
- skin 系统升级（core-playbook + YAML 配置 + doctor 检查）
- skeleton 预建 20_groups / 30_courses / 40_practices 目录 + _README.md
- git_workflow → core-playbook
- Hermes 引用清除
- doctor 修复（大小写兼容 + 空目录豁免 + 皮肤检查）
- 从主项目重建骨架，去除实例数据
