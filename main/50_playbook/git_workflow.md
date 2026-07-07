# Git 与 GitHub 操作手册（git_workflow.md）

**保护级别**：core-playbook

> 位置：`50_playbook/`。PY1001 的 M0 验收项引用本文件；session_close 第九步引用第三节。
> 定位：够用的最小集。Git 有几百个命令,本手册只教 T2AG 日常需要的 12 个。

## 一、一次性设置（装完只做一遍）

```bash
# 1. 安装:git-scm.com 下载 Git for Windows,一路默认;验证:
git --version

# 2. 自报家门(commit 会记录作者)
git config --global user.name  "MikeChen"
git config --global user.email "你的邮箱"

# 3. Windows 换行符设置(防止 CRLF 警告刷屏)
git config --global core.autocrlf true

# 4. 项目初始化(在 T2AG 根目录)
cd C:/Users/MikeChen/T2AC/T2AG
git init

# 5. ★先写 .gitignore 再第一次提交(顺序铁律:先 ignore 后 commit)
#    .gitignore 内容(repo_governance 已定):
#    .venv/
#    __pycache__/
#    *.pyc
#    .env
#    digests/

# 6. 第一次存档
git add .
git commit -m "T2AG 0.0.06 初始入库"
```

## 二、连接 GitHub（一次性）

1. github.com 注册 → 右上 New repository → 名 `T2AG` → **Private（铁律:仓库含学生档案）**
   → 不勾选任何初始化文件（README/gitignore 都不勾,本地已有）→ Create
2. 按页面提示两行（照抄它显示的,以下是样例）：
```bash
git remote add origin https://github.com/你的用户名/T2AG.git
git push -u origin main
```
3. 首次 push 会要登录：跳出浏览器授权点确认即可。若要求 token:
   GitHub → Settings → Developer settings → Personal access tokens → 生成,当密码用。
   **token 是密钥,只贴在弹窗里,永不写进任何文件**（写进文件=.env 入库同级事故）

## 三、日常循环（每次结课仪式第九步,3 条命令）

```bash
git add .                          # 收集所有改动
git commit -m "L07结课:极限习题课,复测M-0003✓"   # 存档,留言=写入确认块首行
git push                           # 推上 GitHub(可攒几次课推一次,但≥每周一推)
```
- commit 留言规范：**人话写这次做了什么**,别写"update""修改"——
  留言是给三个月后的你和下一任老师看的
- 查状态随时用:`git status`(哪些文件改了没存) / `git log --oneline`(存档历史一屏流水)

## 四、后悔药（只教安全的三种,危险操作不教）

```bash
git diff                    # 看这次改了哪几行(存档前检查)
git restore 文件名           # 丢弃某文件未存档的改动,回到上次 commit 状态
git log --oneline           # 找到目标存档的编号(前7位),然后:
git checkout 编号 -- 文件名  # 把某个文件恢复到那个历史时刻(只动这一个文件)
```
- **禁止自行使用** `git reset --hard` / `git push --force`:这两个能真丢数据,
  需要时把情况发给老师处理,并记 problemlog

## 五、换电脑 / 灾难恢复

```bash
git clone https://github.com/你的用户名/T2AG.git   # 整仓库拉回来
cd T2AG && python -m venv .venv && pip install -r requirements.txt  # 环境按真相源重建
```
一句话:**GitHub 上有 = 电脑烧了也没事;只在本地 = 硬盘寿命就是系统寿命。**

## 六、与 T2AG 制度的对接点

| 制度 | Git 动作 |
|---|---|
| 结课仪式第九步 | add + commit(留言=确认块首行),周内至少一次 push |
| 里程碑 M 完成 | `git tag M2-done` 打标签,验收记录可引用 |
| doctor 提交间隔检查 | `git log` 即数据源(>7天 WARN,休息日豁免) |
| 版本发布(0.0.06…) | changelog 记录的同一天 commit 留言带版本号 |
| .venv/.env 追踪检查 | `git ls-files | grep -E "\.venv|\.env"` 应为空,非空=FAIL |
| 独立性审计 | `git log -p 文件名` 看任一文件的逐行演变史 |

## 七、常见报错速查

| 报错含义 | 处理 |
|---|---|
| `rejected...fetch first` | 远端比本地新(如在网页上改过文件):先 `git pull` 再 push |
| `Please tell me who you are` | 第一节第 2 步没做 |
| CRLF/LF warning | 无害;第一节第 3 步已配置则忽略 |
| push 要密码且密码不对 | 用 token 当密码(第二节第 3 条) |
| 中文文件名显示乱码 | `git config --global core.quotepath false` |
