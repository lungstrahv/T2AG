# T2AG / T2AG 启动指令

本目录是 T2AG（by T2AG）vibe learning 项目的工作根目录。

## 启动规则

每次用户在本项目范围内开始新对话、或用户发送 `T2AG` /「读取 T2AG.md」时，
请先读取 `main/T2AG.md`，并按其中定义的启动规则执行。

## 首次启动判断（pin）

进入文件夹后，检查是否首次启动：
- 读取 `main/00_core/T2AG_memory.md` 的「上次课摘要」
- 若日期为 `—`（空），或 `main/10_case/student_info.md` 中 SN01 仍指向 S001
- → **首次启动**：先读 `main/50_playbook/first_run.md`，按其中步骤执行初始化
- → **非首次**：走 `main/T2AG.md` 4.2 日常接管流程

## 补充说明

- 当前 T2AG 版本：`0.0.06`
- 项目根目录：`<解压目标路径>`
- 核心内容位于 `main/` 文件夹内
- 本入口文件与其他工具入口（CLAUDE.md / SOUL.md / .cursorrules）内容等价，均指向 `main/T2AG.md`
