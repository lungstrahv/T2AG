# 题库存储与考前检查规范（exam_bank_spec）

**保护级别**：core-playbook

> **0.2.3 状态：已激活。** 0.2.0 的「延期设计、不得创建 `_exam/`」封条于 2026-08-21 揭除；
> `_exam/` 为课程内合法聚合根，§五 的 doctor 检查已实现为 `runtime.exam_banks`。
>
> 配套 `main/50_playbook/exam_protocol.md`（协议条款与结算闸）。本文件只规定题库存储、
> 登记表、题级元数据和考前机械检查——**不持有场次事实与结算结论**，那些归
> `main/40_course/<COURSE_ID>/_exam/exam_ledger.md`。

enforcement: check=runtime.exam_banks
model_dependent: unknown

## 一、目录结构

> 题库位置固定为 `main/40_course/<COURSE_ID>/_exam/`，与该课
> `course.md`、`progress.md` 同属一个课程聚合根。

```text
[课程根]/_exam/
├ exam_ledger.md   ← 结算真相源（复利回路·衰减实例），归 exam_protocol.md §十三
├ index.md         ← 池状态真相源（本文件 §二）
└ papers/
   ├ MIT_18100B_2019F/
   │   ├ paper.pdf
   │   ├ solution.pdf
   │   └ meta.md
   └ Fudan_MathAnalysis_2021S/
```

- `index.md` 是卷级登记表，也是池状态唯一真相源。
- 池别、已用、已考都是登记表列，不搬文件；搬文件会断引用。
- 原卷 PDF 原样保存，题面读取走 source 缓存规则，禁止转录重排。
- 下载渠道：MIT OCW 等公开课页可由 agent 下载；国内流传卷由学生取得后归档入库。无网环境下，学生下载，老师登记。

## 二、index.md 卷级表

```markdown
| 卷ID | 校 | 年 | 课程层级(荣誉/普通) | 总时长 | 题数 | 单题基准时长 | 解答(有/无) | 池别 | 状态(在池/已考) |
|---|---|---|---|---|---|---|---|---|---|
```

## 三、meta.md 题级表

```markdown
| 题号 | 类型 | 知识节点(对照知识地图) | 难度档 | 已用于教学 | 已考 | 解答页码 | 考前检查备注(PASS/REJECT + 原因) |
|---|---|---|---|---|---|---|---|
```

题型枚举：
- 计算题（求极限 / 导数 / 积分）
- 证明题
- 构造题
- 判断改错题
- 概念叙述题

难度定级：L1 基础 / L2 标准 / L3 压轴。三信号取中位数定档，登记后不改：
- 源课程层级：荣誉课卷整体 +1 档
- 卷内位置：前 1/3 题偏低，末 1/3 偏高
- 题型：概念叙述 / 计算偏低，构造 / 多问证明偏高

## 四、考前适合性检查

对每道候选题输出 PASS / REJECT + 原因，记入 meta 的「考前检查备注」列：

| # | 检查 | 不过则 |
|---|---|---|
| 1 | 知识节点属于当前已教节点 | REJECT-超纲 |
| 2 | 节点上游依赖均已教 | REJECT-依赖缺 |
| 3 | `solution.pdf` 存在且含该题 | REJECT-无解答 |
| 4 | 中 / 英文或官方译本 | REJECT-语言 |
| 5 | 未打“已用 / 已考”标；题干与已用题非同源改编 | REJECT-已见 |
| 6 | 入选后仍满足场次配比 | 换抽 |

小测抽题：练习池未用题 → 逐题检查 → 合格集合内按当日种子随机抽 3。

期末组卷：考核池未用题 → 逐题检查 → 满足 `exam_protocol` 第七节配比约束后随机抽取。

## 五、doctor 检查（已实现：`runtime.exam_banks`）

| 检查 | 级别 |
|---|---|
| 考核池卷的题号引用出现在任何 lesson / exercise 文件 | **FAIL** |
| `papers/` 下有卷夹但 `index.md` 未登记 | WARN |
| `meta.md` 缺列或缺解答页码 | WARN |

**空库短路**：`index.md` 登记 0 卷时本检查返回 PASS。空库是「骨架优先」裁决下的合法初态，
不是故障；把它判成 WARN 会让新课一建就带噪声，噪声多了就没人看 doctor 了。

## 六、与 exam_ledger 的分界

| | `index.md`（本文件） | `exam_ledger.md`（exam_protocol.md §十三） |
|---|---|---|
| truth_scope | `exam_pool_state` | `exam_settlement` |
| 持有 | 卷、池别、已用/已考状态 | 场次、判定、补考轨迹、提醒账 |
| 回路角色 | 无（纯登记表） | 复利回路·**衰减实例** |

组卷时 ledger 从 index 取题（读），index 不因组卷改写，只在**已考**后改状态列。
两个文件都不搬 PDF——搬文件会断引用。
