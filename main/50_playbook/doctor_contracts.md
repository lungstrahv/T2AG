# Doctor 现行契约清单（doctor_contracts）

**保护级别**：core-playbook

> 本文件界定 `t2ag_doctor.py` 在 0.2.0 中承诺机械验证的范围。只有可复现、可定位、违反明确现行契约的事实才能成为 FAIL；语义判断不得伪装成机械闸门。

## 一、结果分类

| 分类 | 含义 | doctor 行为 |
|---|---|---|
| FAIL | 可复现、可定位，违反明确现行契约 | 返回非零 |
| REVIEW | 需求含糊、模型判断不稳定，或存在多种合理设计 | 不由 doctor 自动定级；转入讨论 |
| WARN | 事实成立，但不阻断当前目标 | 返回零并报告 |
| WAIVED | 与需求提出者讨论后，明确延期或接受风险 | 不隐藏原事实；记录 waiver 证据 |

三轮、每轮最多三次实质尝试及重新分类规则见 `remediation_governance.md`。

## 二、0.2.0 自动检查矩阵

| 契约 | 自动入口 | 失败边界 |
|---|---|---|
| 九域与发行身份 | doctor 内建 | 目录、版本、Main/Skeleton/Lite 身份不闭合 |
| profile 初始化 | doctor 内建 | initialized 仍有占位符或缺时间、目标、基础、偏好 |
| Course/Group/Binding/AR/EG | doctor 内建 | schema、稳定 ID、引用或生命周期冲突 |
| progress 身份 | 统一活动路由器 + state + doctor | `type/course_id/truth_scope` 缺失、冒名或在任何 GENERATED 写入前未被拒绝；迁移后不接受 truth_source-only |
| 学习活动发行能力 | doctor 内建 | Core 学习活动契约或 Course/Lesson/Exercise 模板缺失，或 Main/Skeleton/Lite 内容分叉 |
| 恢复路径 | 统一活动路由器 + doctor | ongoing Course 缺显式 `current_activity`、`current_activity_id`、canonical `resume_path`、`activity_position`，或目标悬空；Exercise 首启不得依赖预造 Lesson |
| 学习上下文包 | `t2ag_context.py` + `t2ag_activity.py` + `test_context_packet.py` + doctor | 工具、测试或 core playbook 缺失/三发行分叉；活动/教师路由未注入同一原始字节缓存；SHA 不是文件字节摘要；缺完整序列化 L0 与 L0+首步成本；textbook Lesson 缺窗口仍 ready；非当前课程混用 memory/Group；Lesson 条件路由落到 Exercise；缺首次启动降级或 L0/L1/L2 接线 |
| 状态快照组件边界 | `test_progress_identity_is_shared` + `test_state_refresh_activity_roundtrip` | state 或 Doctor 推断缺失活动、把历史 Lesson 标成活跃、为 sentinel 构造路径、组视图假定当前活动必为 Lesson，或一次运行对同一 ongoing progress 二次读取而混合状态版本 |
| 活动事务落盘往返 | `test_activity_cli_disk_roundtrip` | 从当前发行自身建立无 hardlink 的临时完整工作树，并断言 Doctor 实际检测到本发行 flavor；真实执行 `--write → 重读 → --check → 完整 Doctor → recover route → close route`，按路由结果落盘 progress 与当前主载体后再次执行 state/Doctor；写入零命中、任一步失败或 Exercise 修改历史 Lesson |
| Lesson 上下文退役 | `test_exercise_current_lesson_driver_matrix` | 四种 driver 下 active progress 不依赖或回填 `current_lesson`；遗留非法/悬空值不得驱动路由，历史 Lesson 只从 ledger/ContentGroup 解析 |
| planned/ongoing 边界 | `test_planned_activity_fields_rejected` + doctor | planned 预填活动字段，或 ongoing 缺完整活动事务字段 |
| working pages 活动边界 | `test_working_pages_activity_matrix` + doctor | Exercise 或非教材 Lesson 继承页缓存路由，或 textbook Lesson 逃过当前窗口完整性检查 |
| GENERATED owner | doctor + `test_activity_workflows_share_executable_route` | Lesson 保留无主 `LESSON_PROGRESS` anchor，或恢复/结课未共享统一活动路由 |
| 活动边界 | doctor 内建 | 活动图单元内 ID 重复、任一 Lesson/Exercise 漏登或 ContentGroup 漂移；活动持有另一活动或恢复 ExerciseSession |
| 非教材活动边界 | `test_lesson_retired_ownership_all_drivers` | goal/project/praxis 的 Lesson 借 driver 绕过基础 schema 或退役所有权字段检查 |
| 教师模板路由 | 统一教师映射解析器 + doctor | 映射表不唯一、列 schema 漂移、重复/漏登课程、令牌走私、模板身份不符，或模板绕过当前活动主载体 |
| 教材 Exercise 持久题源 | 统一活动路由器 + doctor | Exercise 依赖 Lesson working-pages 等可清理缓存；`source_path/source_document` 不是解析后仍在本 Course book 内的 canonical 非链接路径；artifact ID、ContentGroup、locator、源文档 SHA、registry 生命周期或逐题题面不闭合；Lite 省略二进制未由完整正式 migration manifest（报告状态/路径/SHA、schema/target kind/count/sequence 和完整 operation 字段）证明 |
| Lesson/Exercise 与习题证据 | doctor 内建 | Lesson/Exercise 主载体、ContentGroup/activity map 双向关系、U/AT/RV schema、引用、图片证据或逐题结果冲突；textbook completion node 依赖无法完整解析、越出 ContentGroup 或不在 Completion nodes 表 |
| 知识台账 | doctor 内建 | question/mistake/reasoning ID、状态或 `next_id` 冲突 |
| 项目验证 | doctor 内建 | 标准/证据未拆分、未完成节点预填证据、completed M 无有效 `VER-*` 记录，或步骤缺 `passed + 含字母/数字的实际结果摘要`（纯标点不计）为 FAIL；已启动 M 缺模式为 WARN |
| 皮肤 | doctor 内建 | registry、metadata、art_file 或发行分叉错误 |
| 序言、九张流程与离线指南 | doctor + `build_guide.py --check` | 序言生成锚点、FLOW 集合/配对、guide drift、外部 Mermaid 运行时、静态 SVG、按需折叠或受控视窗缺失 |
| Cloud 暂停态 | doctor 内建 | 组件缺失、协议字段冲突、暂停门失效或 CD/CH 登记悬空 |
| active handoff | doctor 内建 | 索引、文件、元数据、唯一性或体积老化状态冲突 |
| state/journal/migration/Lite | 派生工具 | 缓存漂移、证据缺失、迁移非幂等或投影差异 |
| 发布候选隔离 | `t2ag_candidate_replay.py` + `test_candidate_replay_isolation_contract` | 有效 sparse checkout/sparse index，Git 环境/拓扑污染，Main/Skeleton 安全配置无法 preflight，源/A/B 字节清单或副本结果不一致，或全部 A/B 复核之后的末次源指纹发生变化 |
| Git/环境卫生 | doctor 内建 | 跟踪环境文件为 FAIL；未提交工作树为 WARN |

## 三、人工检查

以下判断必须由 agent 给出证据并在必要时与需求提出者讨论，doctor 只验证其载体是否存在：

- 教学解释是否准确、反馈是否足够好；
- handoff 四问是否在语义上真的可恢复；
- 项目验收内容是否达到产品质量，而不只是记录齐全；
- 习题思路观察、错因归纳和掌握推断是否合理；
- REVIEW 与 WAIVED 的裁决是否符合当前目标。

## 四、未激活与退役

- 跨课程考试系统明确不属于 0.2.0；`exam_protocol.md` 与 `exam_bank_spec.md` 只保存延期设计，不触发本版 doctor。
- 0.1.x 的 Case、CourseDefinition/CourseRun、Curriculum、FieldPractice、旧 `skin/` 与旧题库路径已经退役；doctor 只检查其不得重新进入 active 树。
- OCR 置信度确认链、KnowledgePoint 独立对象与 AbilitySummary 属于 0.2.1 设计占位，不得在 0.2.0 假装成现行 schema。

## 五、Waiver 边界

数据完整性、路径悬空、schema、权威冲突和投影差异在契约仍生效时不得豁免。只有外部环境造成、且不影响仓内正确性的检查可写正式 waiver；记录必须包含事实证据、风险、责任人、批准人和失效时间。

## 六、0.2.0 最终复审冻结

0.2.0 最终复审的新增阻断范围只认 `git_workflow.md` 9.1 的六项；此外只复核本表已经存在的
三发行闸门。清单外新发现进入 backlog，不能仅因提高威胁模型而把它升级成本代 FAIL。
日常学习链已经单独验收，可以继续；候选生成和 Git 快照仍分别需要后续明确授权。

## 七、Version campaign 与 delta review 全局门

authorization envelope、reviewer 独立性与 release 资格属于人工治理，不由 Doctor 单独裁决。
Doctor 只验证已登记且可机械复现的载体；通过 Doctor 不等于 `reviewed` 或 `released`。

无论是完整候选复审还是 delta re-review，以下现行门不可拆分，也不可用 campaign envelope、
报告声明或 waiver 跳过：

1. 数据完整性、稳定 ID、schema 与引用闭合；
2. 活动入口、恢复路径与权威链唯一性；
3. migration evidence、journal/index 和未完成 transaction；
4. Main/Skeleton 批准同源面逐文件一致；
5. Main → Lite 投影无 missing/differ/orphan/guide drift；
6. 最终源、候选 tree、index 与输入 docs manifest 指纹稳定。

delta review 只有在旧证据的输入 manifest SHA 未变、范围外文件指纹未变且影响闭包可证明时
才可复用旧结果；否则拒绝复用。权威链、schema、registry 生命周期、migration apply 语义、
事务引擎、候选生成、安全/隐私边界变化，或无法证明影响闭包时，必须退回完整独立复审。

recovery checkpoint 只证明存在恢复点，不进入 release 资格判断。release snapshot 必须由外部
独立报告绑定完整 candidate review 和有界 finalization delta review；`clean ≠ reviewed ≠ released`。
