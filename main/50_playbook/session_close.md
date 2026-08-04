# 结课与手动存档

**保护级别**：core-playbook

`progress.md` 是课程进度唯一真相源。Lesson 与 Exercise 是同级活动；结课写回必须由
显式 `current_activity / current_activity_id / resume_path` 路由，不能由兼容
`current_lesson` 决定。

## 一、结课前解析唯一活动

先执行只读路由：

```powershell
python -B main/70_tools/t2ag_activity.py --course <COURSE_ID> --intent close
```

命令非零时停止结课并修复 `progress.md`。输出中的 `activity_write_target` 是本次唯一活动
主载体：

- `lesson`：写 `lessons/<current_activity_id>/<current_activity_id>.md`；
- `exercise`：写 `exercises/<current_activity_id>/exercise.md`，真实提交和批改再分别写
  Attempt / Review；
- Exercise 的历史 `current_lesson` 只作兼容上下文，不在默认写入目标中；
- planned 课程没有当前活动，不得执行结课。

## 二、Micro 与完整结课共享的强制事务

Micro close 和完整结课都必须原子完成以下步骤。不能把未完成步骤推迟给下一次恢复，
也不使用 `close_type: micro` 或其他“以后补账”标记。

### 步骤 1：先写进度真相源

更新 `main/40_course/<COURSE_ID>/progress.md`：

- `updated`；
- `current_activity`、`current_activity_id` 与 canonical `resume_path`；
- `activity_position`、completion node、checkpoint 与
  `queued / arrived / pending / confirmed / archived` 状态；
- 下次第一件事与当次教学摘要；
- `current_lesson`：Lesson 时与活动 ID 一致；Exercise-first 写 `none`；已有真实历史
  Lesson 时可保留其 ID，但不因此改变写入路由。

### 步骤 2：写当前活动主载体

- Lesson：追加本次讲授、问答、确认和错误尝试；“Lesson 最后停点快照”是局部证据，
  不使用 `T2AG_GENERATED`，也不覆盖 progress。
- Exercise：更新 `exercise.md` 的当前题目、精确停点和证据指针；有真实提交才按
  `exercise_evidence.md` 创建 Attempt，有真实批改才创建 Review；新 Attempt 同时保存
  创建时的 `hint_gate` 快照、最高 `assistance_level` 和真实授权/污染记录。概念问答若
  遵守 scope-only 不升级帮助等级；未经授权泄露关键结构时不得计作独立掌握。
- 两类活动都只写自己的正文。跨活动关系只写 `activity_map.md`；Exercise 结课不得顺手
  改历史 Lesson。

### 步骤 3：闭合本次真实产生的台账

- 疑问写或合并 `question_bank.md`；
- 明确知识错误与正式复测写或合并 `mistake_bank.md`；
- Exercise 的学生原图只进入对应 Attempt 的 `assets/`，不得放入教学示意图目录；
- 学生明确表达的想法按 Lesson thoughts 或 Attempt/Exercise thoughts 路由；没有真实证据
  不创建空对象。

### 步骤 4：刷新并验证落盘结果

```powershell
python -B main/70_tools/t2ag_state_refresh.py --write
python -B main/70_tools/t2ag_state_refresh.py --check
python -B main/70_tools/t2ag_doctor.py
```

随后重新读取 progress、`activity_write_target`、命令输出中的
`mandatory_write_targets`，以及本次实际变化的 `conditional_write_targets`。只有全部
写入可回读、state 无 drift、Doctor 为 `0 FAIL`，
才能宣称本次结课已闭合。只回读这些实际目标，不因验证重载全部历史。当前活动为
Exercise 时，还要确认历史 Lesson 未被本事务修改。

写回使本会话原 L0 上下文包立即失效；若结课后继续同一课堂，按
`context_packet.md` 重新生成一次，不编辑或沿用旧包。

### 步骤 5：处理 working pages 与课堂交接

- 仅当前活动为 textbook Lesson 时，working pages 才属于默认结课范围。
- Lesson 仍在继续时保留所需窗口；关闭 Lesson 或切换到 Exercise 时，可清理物理缓存，
  但必须同时正确处理 Lesson 专用页窗口字段。
- Exercise 不读取或写入历史 Lesson 的 working pages，即使 progress 暂时保留旧页字段。
- 若存在匹配本次 `course_session` 的 active handoff，按其 `close_condition` 核对正式写回；
  只有核对通过后才标 `resolved` 并登记验证结果。项目级施工交接不随课堂结课关闭。

## 三、Micro close

适用于五分钟热身、短复测、手动“保存进度”或学生中途停止。它仍完整执行第二节的
强制事务；只可跳过本次没有新证据触发的课程反思、组合层总结等可选综合。

Micro close 不生成欠账、不写 deferred marker。若因信息或权限不足无法完成强制事务，
本次就不是已闭合的 Micro close；应保留/建立匹配的 active `course_session` handoff，
明确缺口和恢复入口。

## 四、完整结课的附加综合

在强制事务之外，按真实触发补充：

1. 检查 `lesson_thoughts.md` 与 `exercise_thoughts.md`；满足提炼门时更新
   `10_student/profile/course_reflections.md` 并保留来源回链。
2. 跨题重复模式达到证据门槛后才更新 `reasoning_patterns.md`。
3. 组合层频率、时间偏差与欠债处置写 group `review.md`，不复制单课掌握度。
4. Cloud bridge 为 `paused` 时跳过移动端投影；云端 handoff 不能覆盖本地 progress。

## 五、手动存档

学生说“保存进度”时立即执行 Micro close；成功后可以继续同一课堂。不得只改 memory、
learning path 或历史 Lesson。
