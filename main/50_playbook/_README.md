# Playbook 流程手册目录

> **这里放什么**：教学 agent 的操作手册——结课怎么做、开课怎么做、教材怎么导入、考试怎么出。
> **谁写・谁读**：系统演进时维护；教学 agent 执行流程时读取。
> **什么时候来这里**：要执行某个流程（结课、开课、教材管理、考试），来这里找对应手册。

流程按名索引，命名见 `naming_conventions.md`。

- `process_governance.md`：过程管理（meta-playbook）。过程对象（门 + 流程 + 有向图）
  的准入 / 修订 / 退役与图维护纪律；本批为骨架，三流程扩全文属第二阶段。
- `environment_assumptions.md`：宿主环境假设登记（`EA-XXXX`）。代码里成立但没写进规则的
  环境前提，逐条给出探测方法与探测失败时的正确反应；由 doctor `runtime.environment` 实现。
- `changelog_management.md`：changelog 验证层（漂移留痕 / 不腐烂）。锚定与佐证两层分写；
  形式清单复用 `handoff_management.md` §5.6.2。**不证明完整性**。U3 落地前为规范约定，
  doctor 自动对照见后续 `runtime.changelog`（本批未授权实现）。
