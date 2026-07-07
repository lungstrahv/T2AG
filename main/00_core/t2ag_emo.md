# T2AG 学生状态索引

> 本文件是学生情绪/感想系统的索引层,不保存完整记录。
> 每个学生是一个文件夹,存放在 `main/10_case/students/Sxxx/`。

---

## 当前学生状态档案

| 当前学生 | 基本信息 | 性格基调 | 课程感想 | 读取规则 |
|---|---|---|---|---|
| S002 | `main/10_case/students/S002/basic_info.md` | `main/10_case/students/S002/personality_baseline.md` | `main/10_case/students/S002/course_reflections.md` | 开课前读取基本信息 + 性格总纲 + 当前课程知识点树形图和最近感想 |

---

## 学生文件夹结构

```text
main/10_case/students/
├── S001/
│   ├── basic_info.md
│   ├── personality_baseline.md
│   └── course_reflections.md
└── S002/
    ├── basic_info.md
    ├── personality_baseline.md
    └── course_reflections.md
```

---

## 三文件职责

| 文件 | 记录什么 | 写入规则 |
|---|---|---|
| `basic_info.md` | 学校、年级、专业、当前课程、教材、学习目标、困难、辅导偏好 | 学生基本情况变化时更新 |
| `personality_baseline.md` | 性格总纲、情绪感悟元素、哲学/生活感悟、长期压力反应 | 谨慎更新;每个感悟元素保留带日期原文 |
| `course_reflections.md` | 各门课的课程目录、知识点树形图、按日期记录的课程学习感想 | 任意课程感想都写入这里,按课程分段 |

---

## 触发词

学生消息以以下任一形式开头时,视为学生状态记录:

- `感受：`
- `心情：`
- `feeling:`
- `emo:`
- `感想：`

---

## 写入路由

1. 先确认当前学生编号 SN01 指向的 `Sxxx`。
2. 若内容是哲学感悟、生活感悟、元认知、自我调节或稳定压力反应,写入 `personality_baseline.md`。
3. 若内容与当前课程知识点、理解体验、顿悟、卡点或审美感受有关,写入 `course_reflections.md` 的对应课程段落。
4. 若内容是学校、课程、教材、目标、时间投入等事实变化,写入 `basic_info.md`。

---

## 读取规则

每次恢复课程、开始新 lesson、继续讲教材页、生成讲义或处理练习前:

1. 读取当前学生 `basic_info.md`,确认基本背景和课程。
2. 读取 `personality_baseline.md` 的「总纲」和相关情绪感悟元素。
3. 读取 `course_reflections.md` 中当前课程的知识点树形图和最近 3 条感想。
4. 据此调整语气、节奏、压力、确认频率和任务颗粒度。
