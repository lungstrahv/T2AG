# t2ag 0.2.3 已知缺陷告示 · Known Issues (2026-08-26)

## 中文版

**t2ag 0.2.3 已知缺陷告示**

0.2.3 公开版存在四个已确认缺陷。下列 FAIL 是产品缺陷，不是你的操作错误，不必自行排查或改配置：

1. **时区硬编码**：doctor 把作者本地时区写成契约（learning_timezone=Asia/Singapore、cutoff=04:00），其他时区的学生首次闭合必定 FAIL。
2. **flavor 按目录名判定**：用默认目录名 t2ag-skeleton 解压并初始化后，doctor 会报 8 项 FAIL。
3. **profile 误判**：字段填“未提供”被当作未回答，导致 FAIL。
4. **new-course 缺文件**：不生成 activity_map.md，doctor 报 ContentGroup 悬空。

四项在 0.2.4 中均已修复，尚未发布，预计 9 月中旬发布。在此之前遇到上述 FAIL，可按本告示对照忽略。

**从 0.2.3 升级（0.2.4 发布后）**：先把整个 `t2ag/` 目录完整备份一份；然后只替换随发行走的那一半（`main/t2ag.md`、`50_playbook/`、`70_tools/`、`80_interface/`、`AGENTS.md`、`README.md` 与模板），保留你的课程、进度、错题本和 journal；最后跑一次 doctor。旧字段（如 `default_driver`）在 0.2.4 下照常可读，字段重写属单独授权的迁移，不必现在做。

遇到本表未列出的问题，欢迎通过本仓 GitHub Issues 反馈。

感谢在早期版本上花时间试用并把问题报回来的每一位——这四个缺陷都是外部实测发现的。

## English version

**t2ag 0.2.3 — Known Defects**

Four confirmed defects exist in the public 0.2.3 release. The failures below are product defects, not user mistakes; no troubleshooting or config changes on your side are needed.

1. **Hard-coded timezone**: doctor treats the author's local settings as contract (learning_timezone=Asia/Singapore, cutoff=04:00), so a student in any other timezone always FAILs the first closeout.
2. **flavor detected by directory name**: unpacking under the default name `t2ag-skeleton` and initializing produces 8 FAILs.
3. **profile misread**: a field answered "not provided" is scored as unanswered, causing a FAIL.
4. **new-course**: does not generate `activity_map.md`, so doctor reports a dangling ContentGroup.

All four are fixed in 0.2.4, which is not yet released. We expect to publish it in mid-September. Until then, please match any of the failures above against this notice and disregard them.

**Upgrading from 0.2.3 (once 0.2.4 ships)**: back up your entire `t2ag/` directory first; then replace only the distribution half (`main/t2ag.md`, `50_playbook/`, `70_tools/`, `80_interface/`, `AGENTS.md`, `README.md`, templates), keeping your courses, progress, mistake bank and journal; finally run doctor once. Legacy fields such as `default_driver` remain readable under 0.2.4 -- the field rewrite is a separately authorized migration and can wait.

For anything not on this list, please open a GitHub Issue on this repository.

Thanks to everyone who spent time on an early version and reported back — all four defects were found by outside testing.
