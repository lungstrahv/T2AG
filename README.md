# T2AG 0.2.0 Skeleton

> 空实例原件。它可复制为新的 T2AG 实例，但自身不得承载真实学生数据。
> 复制到任意新目录后，未初始化 profile 仍按 Skeleton 空模板验收；完成
> `first_run.md` 并把 profile 改为 initialized 后，该副本自动按个人实例验收，
> 不依赖目录名。原始 `t2ag-skeleton/` 仓本身永远保持空模板身份。

## 快速开始

1. 复制整个目录到新的目标目录。
2. 在目标目录运行：

   ```powershell
   python -B main/70_tools/t2ag_doctor.py
   python -B main/70_tools/t2ag_state_refresh.py --check
   python -B main/70_tools/t2ag_context.py --format markdown
   python -B main/70_tools/t2ag_context.py --include-l1 --format markdown
   ```

3. 空模板的上下文命令必须返回 `first_run_required`；随后读取 `main/t2ag.md` 和
   `main/50_playbook/first_run.md`。
4. 与用户确认 profile、首门课程和首个 group 后再显式写入。

初始化后的来源库存比例只说明选择范围；软预算以完整序列化 Markdown（L0 及
L0+首个 L1）为准，不把该比例称为端到端 Token 降幅。

## 发行角色

- Main：规则与真实实例原件。
- Skeleton：通用规则与空实例原件。
- Lite：只能从 Main 单向生成的审查快照。

普通启动、doctor 和首次启动不得创建、删除、重建或升级 `.venv`，也不得自动
安装依赖、下载教材或生成真实 Engagement。
