# Playbook 流程手册目录

> **这里放什么**：教学 agent 的操作手册——结课怎么做、开课怎么做、教材怎么导入、考试怎么出。
> **谁写・谁读**：系统演进时维护；教学 agent 执行流程时读取。
> **什么时候来这里**：要执行某个流程（结课、开课、教材管理、考试），来这里找对应手册。

流程按名索引，命名见 `naming_conventions.md`。

- `process_governance.md`：过程管理（meta-playbook）。过程对象（门 + 流程 + 有向图）
  的准入 / 修订 / 退役与图维护纪律；本批为骨架，三流程扩全文属第二阶段。
- `gate_index.md`：门索引（playbook，managed_by: process_governance）。T2AG 全部门的一张表——有向图 + 每道门管什么 +
  正文 owner 指针，**只放指针不复制正文**。四线分层：A 教学门、B 施工门、C 机器门、
  D 跨边界门，外加横切的取证纪律。含两条诚实标注：取证纪律目前只注册在 AIF1001r 一门课
  （待裁是否升全局）；⑥与三档校准叠加后仍有「该读没读」的空间维缺口未覆盖。
  自身 `enforcement: prose_accepted`——**它是索引不是约束，无机器兜底**。
- `rule_admission_gate.md`：规则准入门（R-GATE）。新规则要进 `00_core`/`50_playbook` 先过
  这道门：Q0 拒收线（没有失败可见性的品性条款不收）、`enforcement:` 四取值与
  `check=` 命名空间、位置纪律与排除名单（记录区与宪法显式豁免）、自指逃逸硬约束。
  管的是**说了的话必须算数**，不管没说的话。机器落点
  `runtime.rule_enforcement_integrity`。
- `canon_carrier.md`：教学正文正典载体（G2 地板，EV-0030）。textbook driver 课程的教学
  正文只经 `70_tools/canon_append.py` 写入 `teaching_log.md` + `emissions.jsonl` 才算数；
  聊天只发指路语。机器落点 `runtime.canonical_teaching_carrier`（CANON-000..004，不一致
  检测：抓笨绕过，不抓自洽双写，不是 ADR-0002 硬门）。
- `host_g1_optional.md`：宿主 G1 可选写前拦截（加强，非地板）。四格测过才许标该壳
  「可开」；不进 doctor、不进课目录、不进发行面。Grok 2026-08-19 已测可开未常驻。
- `okf_adaptation.md`：OKF v0.2 知识包适配协议（`T2AG-OKF-1`，EV-0024）。主库怎么被讲成
  可交换的 OKF bundle：范围白名单、frontmatter 映射、反引号引用升格为图的边、落盘前的
  泄漏闸门；末节是二期导入边界（只定规矩，未授权实现）。机器落点 `70_tools/okf_export.py`。
- `environment_assumptions.md`：宿主环境假设登记（`EA-XXXX`）。代码里成立但没写进规则的
  环境前提，逐条给出探测方法与探测失败时的正确反应；由 doctor `runtime.environment` 实现。
- `changelog_management.md`：changelog 验证层（漂移留痕 / 不腐烂）。锚定与佐证两层分写；
  形式清单复用 `handoff_management.md` §5.6.2。**不证明完整性**。U3 落地前为规范约定，
  doctor 自动对照见后续 `runtime.changelog`（本批未授权实现）。
