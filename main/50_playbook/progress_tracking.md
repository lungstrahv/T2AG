# 进度节点与自动存档流程（progress_tracking）

**保护级别**：core-playbook

> 本流程定义课程生命周期、容量组合、细粒度恢复点与粗粒度完成节点。
> `course_status.md` 仍是正式进度唯一真相源；课程组只决定当前保留容量，不决定课程是否仍在进行。

## 一、两组彼此独立的状态

### 1.1 课程生命周期

每门课程在 `course_status.md` 文件头使用：

```yaml
lifecycle_status: planned  # planned / ongoing / completed / dropped
```

- `planned`：已有方案或档案，但尚未进入实际学习。
- `ongoing`：课程已经开始且尚未结束；即使不在当前容量组合中，也可保持 ongoing。
- `completed`：课程完成标准已经闭合。
- `dropped`：用户明确终止，保留原因和历史。

### 1.2 当前容量组合

当前 active 的 `Gxx.md` 是用户确认的重点执行组合：组内课程获得时间预算、最低频率和里程碑承诺。
组外 `ongoing` 课程仍可在用户明确提出时临时推进，但不得自动挤占组内预算，也不得因一次临时学习自动换组。
系统可依据实际时长、启动失败、学习能力、截止期、依赖和项目限制提出调组建议；成员变更仍须用户确认。

## 二、两层进度节点

### 2.1 checkpoint：到达节点

checkpoint 是细粒度恢复点，用来回答“具体讲到哪一句、哪个证明步骤或哪个项目动作”。

- 教材课以当前 4–6 页工作窗口为范围；一页可有多个 checkpoint，当前窗口最多 12 个。
- 项目/实践课按当前时间表、里程碑或项目顺序表的细步骤生成。
- checkpoint 使用来源定位 ID，例如 `MATH1607H-B001-P026-N02`。
- 到达 checkpoint 时静默自动保存，不要求学生说“保存进度”。
- 状态至少区分 `queued / arrived / pending / confirmed / archived`。
- checkpoint 只证明到达位置与确认状态，不等于完成一个教材小节或项目节点。

### 2.2 completion node：完成节点

completion node 是粗粒度、永久稳定的正式进度单元，通常跨若干 checkpoint 或若干页。

- 教材课通常对应教材目录中的一个小节、完整定理链或其他自然内容边界。
- 项目课对应项目计划中的稳定步骤或里程碑。
- 实践课对应时间表中的行动/复盘单元。
- ID 一经生成不得重排或复用；标题、页码或说明可修订。
- 状态使用 `queued / in_progress / completed / superseded`。
- 临时补充内容挂在父 completion node 下，不擅自改变主线顺序。

## 三、生成与滚动窗口

1. completion node 先从已核验教材目录、项目顺序表或实践时间表生成；不凭模型记忆猜结构。
2. 教材课只为当前 4–6 页生成 checkpoint，当前窗口上限 12 个；翻页时归档离开窗口的 checkpoint，再生成新窗口。
3. 非活跃课程只保留最小生命周期字段，首次激活或真正恢复时惰性生成节点。
4. `node_id` 绑定来源身份；文件改名通过 artifact registry 解析，不重造节点 ID。

## 四、保存与正式提升入口

### 4.1 自动 checkpoint

进入 checkpoint 时立即更新 `course_status.md` 的当前 checkpoint、精确停点和确认状态，并刷新机器生成缓存。
这只保存位置，不得把父 completion node 写成 completed。

### 4.2 自动完成节点

completion node 的既有完成证据满足后，自动把该节点标为 completed，并把下一节点标为 in_progress。

- 教材课：内容讲完，且没有悬空确认或未回答问题；不额外强制生成习题。
- 教材原有例题/习题：继续执行习题闭环，但习题闭环不是每个完成节点的附加考试。
- 项目课：以计划中已有的代码运行、文件产出或功能结果关闭。
- 实践课：以计划中已有的行动记录或复盘结果关闭。
- 错题复测、章节卷与陈年卷保持独立，不与每个 completion node 捆绑。

### 4.3 学生手动“保存进度”

学生说“保存进度”时，无论是否处于节点边界，都立即强制保存当前 checkpoint、pending 状态和课堂要点。
手动保存不自动完成父节点，也不替代结课仪式。

### 4.4 结课与恢复确认

正常结课按 `session_close.md` 完成正式写回。异常中断后恢复时，若 lesson、云端事件或学生陈述比真相源更新，
先暂停新内容并核对；经学生确认后更新 `course_status.md`，再统一刷新缓存。

## 五、云端检查点

- 手机端 checkpoint 在云端内部静默记录。
- 每完成一个 completion node，云端自动生成紧凑的 `T2AG_PROGRESS_RECEIPT`。
- 学生说“保存进度”时立即生成回执；正常结课仍生成完整 `T2AG_SESSION_CLOSE`。
- 本地按事件 ID 去重；已被后续结课块包含的回执不重复计入。
- 云端不能直接把本地 `course_status.md` 写成已同步；回执在本地核对前保持 pending。

## 六、机器生成缓存

memory 当前进度区、lesson 头部进度区、`course_info.md` 课程/容量索引和移动端入口的机器字段
由 `70_tools/t2ag_state_refresh.py` 从正式来源统一生成。生成区块不得手写修改。

执行顺序固定为：

```text
course_status / active G 文件
  → t2ag_state_refresh.py --write
  → t2ag_state_refresh.py --check
  → t2ag_doctor.py
```

工具失败时不得用手抄结果冒充生成成功。
