# 测试选择与证据复用（test_strategy）

**保护级别**：core-playbook

本规则把“保存测试能力”和“本次执行组合”分开。测试代码是长期资产；一次任务只生成
内存中的执行计划，不生成临时 Python suite，也不在执行后删除测试代码。

本规则与 Doctor profile 分层共同组成三形态基础能力，由 `distribution_foundation` 组件和
`test_distribution_foundation.py` 做原子自检；Lite 只携带并供审查，不执行。
完整检测树见 `validation_flow.md`。`validation_workflow.json` 管 profile、V0–V3、预算与
防越级门；`test_dependencies.json` 只管理测试库存、档位、组件和源码依赖。

## 1. 持久层

- 原子断言保存在稳定的 `test_*.py` 或共享断言库中；按领域组织，不按某次施工单组织。
- `70_tools/test_dependencies.json` 是测试、组件、档位与源码依赖的唯一清单。
- 清单显式区分 `kind=atomic` 与 `kind=scenario`；前者只能是 `70_tools/test_*.py`，后者
  只能位于 `70_tools/scenarios/` 且不得使用 `test_` 文件名。
- `70_tools/t2ag_test.py` 校验清单完整性，按组件或改动路径选择测试，并给每个被选文件
  绑定 SHA-256。
- 也可用稳定 `--test ID` 明确组合原子测试；普通执行最多三个测试命令。
- 普通发现范围内新增或删除 `test_*.py` 时，必须同一批更新依赖清单；不得用 glob 把新增
  测试自动纳入迁移、发布或全量边界。
- 需要真实物理根、故障注入或跨仓编排的完整场景放在 `70_tools/scenarios/`，不使用
  `test_` 文件名，也不参加普通测试发现。

## 2. 临时组合

现场组合只存在于 `t2ag.test_plan.v1` 内存对象及标准输出中。先列计划，再用完全相同的
选择参数和 plan SHA 执行：

```powershell
python -B main/70_tools/t2ag_test.py --test foundation.structure --test doctor.postcheck --tier fast --plan-only
python -B main/70_tools/t2ag_test.py --test foundation.structure --test doctor.postcheck --tier fast --execute-plan <PLAN_SHA>
python -B main/70_tools/t2ag_test.py --changed main/70_tools/activity_close.py --tier fast --plan-only
python -B main/70_tools/t2ag_test.py --changed main/70_tools/activity_close.py --tier fast --execute-plan <PLAN_SHA>
python -B main/70_tools/t2ag_test.py --component transaction --tier deep --plan-only
python -B main/70_tools/t2ag_test.py --component release_suite --tier release_only --plan-only
```

没有 `--execute-plan` 时选择器只输出计划，不启动测试；SHA 不匹配时拒绝执行。release_only
执行还要求 `--release-reason`，而 `release_suite` 聚合项始终只读。执行器按清单顺序启动
已保存的测试文件。禁止拼接并落盘 `test_adhoc.py`、
`test_current_batch.py` 等一次性代码；因此也不存在“用完删除临时测试文件”的清理步骤。
需要留存的只是计划 SHA、测试文件 SHA 和结果摘要。

## 3. 档位

| 档位 | 默认用途 | 内容 |
|---|---|---|
| `fast` | V1 与普通 V2 定向回归 | 直接相关的本地契约和 round-trip |
| `deep` | 受影响的核心事务、迁移、恢复 | `fast` 加相关深度测试 |
| `release_only` | 冻结候选或正式发布 | 对应的发布原子契约、矩阵证据和显式场景 |

档位是上限，不是“始终跑满”的命令。普通任务不得因为清单中存在 `deep` 或
`release_only` 条目而自动升级；未进入本次档位的条目在计划中标为 deferred。
普通选择超过三个可执行测试文件时，计划仍可查看，但执行器必须拒绝并要求缩小组合。

发布测试也必须按组件定向选择。`release_receipts`、`release_evidence`、`release_gates`、
`release_faults`、`release_shadow` 各自只绑定直接工具；`release_suite` 是没有 changed-path
映射且只能 `--plan-only` 的显式聚合组件，任何普通改动都不能自动选中或执行它。物理根
scenario 在组合中只登记为 deferred，必须按计划给出所需 fixture 后显式调用。

## 4. 现行领域入口

- `test_runtime_contracts.py`：profile、路由、teacher、state refresh、skin。
- `test_activity_contracts.py`：活动模型、课程模板、证据和可执行路径。
- `test_release_contracts.py`：候选隔离及发布流程契约，仅发布档位。
- `test_release_receipts.py`：receipt chain 原子契约。
- `test_release_evidence.py`：结构化 evidence 原子契约。
- `test_release_gates.py`：gate matrix 与冻结成员原子契约。
- `test_release_fault_contracts.py`：故障边界枚举原子契约，不执行完整故障矩阵。
- `test_release_shadow_contracts.py`：shadow 授权、清理与不可覆写原子契约。
- `test_legacy_migrations.py`：历史迁移兼容，只在相应迁移受影响时运行。
- `test_022_close_roundtrip.py`：包含 close runtime 的独有断言；不再保留重复入口。
- `scenarios/release_reading_bridge_saga.py`：完整物理根 release scenario，须显式提供 fixture。
- `scenarios/release_shadow_apply.py`：完整物理根 shadow apply/rollback/second-run 场景。

## 5. 变更与删除规则

删除测试必须证明断言已并入其他稳定入口，或被现行契约明确退役；只因运行慢、当前任务
未选中或已经通过，不构成删除理由。重复断言先合并，历史迁移和发布证据测试降档保留。

SHA 未变化且依赖未受影响的结果允许复用。finding 修复只重跑受影响组件；冻结候选才统一
执行一次 `release_only` 组合和完整独立复审。选择结果超出普通任务预算时，记录 deferred
项，等待正式候选，不得自动扩大验证范围。
