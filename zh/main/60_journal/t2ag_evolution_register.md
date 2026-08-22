# T2AG Evolution Register（t2ag_evolution_register.md）

> **职能**：**本实例**的决策生命周期登记簿——记录本实例的观察、讨论、决定与实施归档。
> **保护级别**：journal（回看层，不是真相源）
> **创建**：实例清零模板（EV-0023，2026-08-09）
> **维护规则**：新增观察条目需用户明确要求；不得自动写入。
> **与 ADR**：本文件拥有 `observing → discussing → decided → archived` 生命周期；
> ADR（`docs/adr/`）是可移植架构决定产物，不复制状态机，须双向回指本 Register。

---

## 实例清零说明（EV-0023）

本文件随发行版**清零**：维护者项目的决策档案（EV-0001 起的全部条目）保留在维护仓，
不构成本实例的历史——**本实例是当前 schema 的新起点，不继承维护者的出生历史**。

- 本实例自己的决策从 **EV-0001** 开始登记。
- 本仓正文（宪法、playbook、ADR）中出现的 EV-NNNN 引用是**维护者决策的出处注释**，
  不指向本文件条目；doctor 对本实例豁免 EV 链接检查，但 ADR 引用必须真实存在。
- 条目格式、边界说明与「不是每个 EV 都生成 ADR」的提升判据，同维护仓 canonical
  （`docs/adr/README.md` 与 `main/70_tools/decision_record_contract.py` 的解析器即契约）。
