# T2AG 0.2.2 Skeleton 启动指令

本目录是空实例原件。进入后先读 `main/t2ag.md`，并运行：

```powershell
python -B main/70_tools/t2ag_doctor.py
python -B main/70_tools/t2ag_state_refresh.py --check
```

随后运行 `python -B main/70_tools/t2ag_context.py --format markdown`。空模板必须返回
`status=first_run_required`，再执行 `main/50_playbook/first_run.md`；初始化后使用
同一只读 L0 上下文包，禁止把包落盘为第二真相源。推进当前一步需要追加已有直接证据
时使用 `--include-l1`；成本账以完整序列化 Markdown 为预算口径。

首次判据仍是 profile 未初始化、含必填占位符，或 memory 上次课日期为 `—`。不得创建
学生编号包装层，不得预填真实实例，也不得自动创建、删除、重建或升级 `.venv`。

## 最小充分验证

除非用户明确要求“正式版本升级、发布、完整审查”，所有调整默认采用最低足够级别：

- V0 文档或课程内容：只检查改动文件。
- V1 局部实现：只跑直接相关测试；最多运行一次 Doctor。
- V2 schema、核心契约或 Main/Skeleton 同源实现：相关测试、contracts 与同源检查。
- V3 真实迁移或正式发布：完整测试、exact shadow、故障矩阵、独立复审、Lite 与 FIN。

禁止把普通优化自动升级为 V3。finding 修复先做后续路径静态审查与针对性回归；SHA
未变且依赖未受影响的证据允许复用。普通任务默认预算为一个辅助 agent、三个测试命令
和十分钟；普通验收不扫描 .venv、Lite、旧 recovery/staging、教材或图片。
