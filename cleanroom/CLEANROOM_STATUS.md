# T2AG 0.3 净室重构候选 / Cleanroom candidate

2026-10-01：净室重构已有可运行的中英文候选。60 项必需结果经非作者角色复核通过；一次真实实例已切换到新入口，并恢复到最新待答停点，原件保留。版本仍为 `0.3.0.dev0`，尚未作为稳定版发行。

验收关注相同输入、状态和授权下的教学结果与持久后果。旧文件布局、模块划分和操作步骤可以重建。实现从一份事务日志、具名领域动作和可重建视图出发；后续以实际使用场景的缺口增量完善。

日常学习先反馈判断，再按实际回执报告保存。原答、判断与停点一起保存；结果未知时查原请求，避免重复写入。检查随相关变化触发。教材事实与教师的讲解安排分别保存；讲解、举例、示范和提问都可以使用。

六条简短任务回路覆盖建计划、恢复教材课、反馈保存、练习提示、保存结课和相关修复。它们指导关键顺序，不是额外执行引擎或重复确认手续。手机遥控同一宿主时使用同一实例；独立离线交换默认不启用。

本目录包含运行时、双语指南和合成测试。Python 3.11+：

```console
cd cleanroom
python -m t2ag_next --instance ./instance init --language zh
python -m t2ag_next workflow --language zh
python -m unittest discover -s tests
```

语言需明确选择 `zh` 或 `en`；不要用新建空白实例覆盖已有课堂。操作入口见 [AGENTS.md](AGENTS.md)，日常使用见 [中文指南](docs/user-guide.zh.md) / [English guide](docs/user-guide.en.md)。PDF 与 OKF 的可选依赖见 [README](README.md)。

验证记录见 [ACCEPTANCE.json](ACCEPTANCE.json)：一次冻结集成运行 356 项，354 通过、2 项 Windows 符号链接权限跳过；最终学习模块 45 项通过，最后变化另有 3 项非作者验证。候选中英文实际安装的 37 个运行文件一致。后续变化按文件差分绑定已有证据，没有把旧包的结果冒充新包全量重跑。

迁移已做真实快照与恢复演练，并在最新保存点完成一次实际入口切换。切换前源与快照无漂移；切换后只改变已备份的入口指引，教材、成绩和学习记录保持原字节。非作者从新运行时解析安装配置，实际恢复同一待答问题；切换没有生成学生回答、教学会话、扫描或继续许可。

其他实例仍需在自己的明确停点核对增量。新旧任一侧产生后续事实时，保留并核对双方增量后再决定退回，不能丢弃新记录。未知项继续明确保留；不重评历史。个人实例、教材、私有快照和协调记录均不随本目录发布。

计量已区分 provider token 回执、缓存输入、输出、质量样本与运行时耗时；缺失货币成本保持未知。未宣称已测真实手机网络、生产对端联调、物理断电、长期教学效果或不同模型的性能排名。

## English

This is a reviewed, executable bilingual cleanroom candidate. All 60 required observable outcomes passed the bounded non-author review. One real instance has switched to the new entry and recovered its latest pending question, with originals retained. Version `0.3.0.dev0` remains a candidate.

Equivalent input, state and authorization preserve required results; internal methods can change. The runtime uses one transaction journal, named actions, derived views and six short task loops. Source meaning, actual learning evidence and learner choices remain distinct. Direct explanation is part of teaching.

The frozen integration suite passed 354 of 356 tests, with two Windows symlink permission skips. The final learning module passed 45 tests, with three further non-author delta checks. Both editions were actually installed and their 37 runtime payload files matched. See the acceptance record for scope and limits.

Personal data and textbooks are excluded. The actual cutover checked source drift, preserved original learning bytes and changed only backed-up entry instructions. A non-author recovered the same pending question through the installed runtime and its instance configuration. No answer, teaching session, scan or continuation permission was created by the switch. Other instances require their own final delta check; later writes must be retained and reconciled before returning to an earlier authority. No real mobile network, production peer transport, physical power-loss or comparative model-performance claim is made.
