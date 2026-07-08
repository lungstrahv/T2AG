# 外部资源索引（external_resources.md）

> 位置：`00_core/`。登记 t2ag 全系统共享的在线学习资源。
> 各课程 `*_book/README.md` 引用本文件，不重复登记。
> agent 教学时按需用 WebFetch 读取在线内容。

---

## Cambridge Math Tripos Notes

> 来源：https://dec41.user.srcf.net/notes/
> 作者：Dexter Chua（剑桥数学本科四年全套笔记，4266 页）
> 许可：公开免费，源码在 GitHub (dalcde/cam-notes)
> 特点：每门课提供 5 个版本（full / trim / defs-only / thm-only / thm+proof），天然匹配 t2ag 四级梯子

### 四级梯子映射

| 梯子级别 | 使用版本 | 揭示内容 |
|---|---|---|
| 第 1 级（自己想 10min） | defs-only | 只给定义，学生自己想 |
| 第 2 级（一句提示） | thm-only | 给定理陈述，不给证明 |
| 第 3 级（查参考） | thm+proof | 给证明思路 |
| 第 4 级（完整讲解进 mistake_bank） | full | 综合主教材 + Cambridge Notes 完整讲解 |

### 课程映射表

> HTML 版入口格式：`https://dec41.user.srcf.net/h/{Part}_{Term}/{course_name}`
> agent 用 WebFetch 读取 HTML 版即可，无需下载 PDF。

#### Part IA（大一，对应 MATH1607H 上册 + 基础课）

| 剑桥课程 | 对应 t2ag 课程 | 对应内容 | HTML 入口 |
|---|---|---|---|
| Numbers and Sets | MATH1607H | 第 1 章集合与映射 | `https://dec41.user.srcf.net/h/IA_M/numbers_and_sets` |
| Analysis I | MATH1607H | 第 2-5 章极限/连续/微分 | `https://dec41.user.srcf.net/h/IA_L/analysis_i` |
| Vectors and Matrices | 未来线性代数 | 向量空间、矩阵 | `https://dec41.user.srcf.net/h/IA_M/vectors_and_matrices` |
| Groups | 未来抽象代数 | 群论入门 | `https://dec41.user.srcf.net/h/IA_M/groups` |
| Differential Equations | MATH1607H 下册 | 常微分方程 | `https://dec41.user.srcf.net/h/IA_M/differential_equations` |
| Probability | IV1001 | 概率论基础 | `https://dec41.user.srcf.net/h/IA_L/probability` |
| Vector Calculus | MATH1607H 下册 | 向量微积分 | `https://dec41.user.srcf.net/h/IA_L/vector_calculus` |
| Dynamics and Relativity | 物理选修 | 经典力学 | `https://dec41.user.srcf.net/h/IA_L/dynamics_and_relativity` |

#### Part IB（大二，对应 MATH1607H 下册 + 进阶课）

| 剑桥课程 | 对应 t2ag 课程 | 对应内容 | HTML 入口 |
|---|---|---|---|
| Analysis II | MATH1607H 下册 | 多元分析 | `https://dec41.user.srcf.net/h/IB_M/analysis_ii` |
| Linear Algebra | 未来线性代数 | 线性代数完整版 | `https://dec41.user.srcf.net/h/IB_M/linear_algebra` |
| Metric and Topological Spaces | MATH1607H 下册 | 度量空间、拓扑（一致收敛前置） | `https://dec41.user.srcf.net/h/IB_E/metric_and_topological_spaces` |
| Complex Analysis | MATH1607H 下册 | 复分析 | `https://dec41.user.srcf.net/h/IB_L/complex_analysis` |
| Complex Methods | MATH1607H 下册 | 复变方法 | `https://dec41.user.srcf.net/h/IB_L/complex_methods` |
| Methods | MATH1607H 下册 | 数学方法 | `https://dec41.user.srcf.net/h/IB_M/methods` |
| Statistics | IV1001 | 统计基础 | `https://dec41.user.srcf.net/h/IB_L/statistics` |
| Markov Chains | IV1001 | 马尔可夫链 | `https://dec41.user.srcf.net/h/IB_M/markov_chains` |
| Numerical Analysis | PY1001/CS1953 | 数值分析 | `https://dec41.user.srcf.net/h/IB_L/numerical_analysis` |
| Groups, Rings and Modules | 未来抽象代数 | 群环模 | `https://dec41.user.srcf.net/h/IB_L/groups_rings_and_modules` |
| Geometry | 未来几何 | 微分几何入门 | `https://dec41.user.srcf.net/h/IB_L/geometry` |
| Quantum Mechanics | 物理选修 | 量子力学 | `https://dec41.user.srcf.net/h/IB_M/quantum_mechanics` |
| Electromagnetism | 物理选修 | 电磁学 | `https://dec41.user.srcf.net/h/IB_L/electromagnetism` |
| Fluid Dynamics | 物理选修 | 流体力学 | `https://dec41.user.srcf.net/h/IB_L/fluid_dynamics` |
| Optimisation | IV1001 | 优化理论 | `https://dec41.user.srcf.net/h/IB_E/optimisation` |
| Variational Principles | MATH1607H 下册 | 变分原理 | `https://dec41.user.srcf.net/h/IB_E/variational_principles` |

#### Part II（大三，对应高阶选修）

| 剑桥课程 | 对应 t2ag 方向 | HTML 入口 |
|---|---|---|
| Algebraic Topology | 代数拓扑选修 | `https://dec41.user.srcf.net/h/II_M/algebraic_topology` |
| Galois Theory | 代数选修 | `https://dec41.user.srcf.net/h/II_M/galois_theory` |
| Linear Analysis | 分析选修 | `https://dec41.user.srcf.net/h/II_M/linear_analysis` |
| Probability and Measure | IV1001 进阶 | `https://dec41.user.srcf.net/h/II_M/probability_and_measure` |
| Logic and Set Theory | MATH1607H 补充 | `https://dec41.user.srcf.net/h/II_L/logic_and_set_theory` |
| Number Fields | 数论选修 | `https://dec41.user.srcf.net/h/II_L/number_fields` |
| Representation Theory | 代数选修 | `https://dec41.user.srcf.net/h/II_L/representation_theory` |
| Statistical Physics | 物理选修 | `https://dec41.user.srcf.net/h/II_L/statistical_physics` |
| Integrable Systems | 应用数学 | `https://dec41.user.srcf.net/h/II_M/integrable_systems` |

#### Part III/IV（研究生级，暂不映射，按需查用）

完整列表见 https://dec41.user.srcf.net/notes/

---

## 使用规则

- **在线引用，不下载**：agent 用 WebFetch 读取 HTML 版，按需取用
- **辅助定位**：Cambridge Notes 是"换一个讲法"的参考，不替代主教材
- **梯子优先**：学生卡住时，先查 defs-only 版给定义，逐级揭示
- **课程映射不锁死**：映射表是推荐对应关系，agent 可根据具体知识点灵活跨课引用
