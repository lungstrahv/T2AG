# 皮肤管理流程（skin_playbook.md）

**保护级别**：core-playbook

> 位置：`50_playbook/`。管理 T2AG 皮肤系统的创建、切换与校验。
> 皮肤是外观组件，不是新层——没有自己的验收逻辑，只是配置+素材。
>
> **触发条件**：用户要求更换皮肤/创建新皮肤/皮肤相关 doctor 报错。

---

## 一、架构概述

```
main/skin/
  skin.yaml              ← 全局配置（active 指针 + 注册表）
  SK001_default/         ← 皮肤文件夹
    skin.yaml            ← 皮肤元数据
    01_welcome.txt       ← 艺术素材
```

**配置格式**：扁平 YAML 子集（`key: value`），doctor 用正则解析，零依赖。
不使用 PyYAML——skin 配置复杂度撑死十几个键，引入第三方依赖不值得。

### 全局 skin.yaml 键

| 键 | 说明 | 示例 |
|---|---|---|
| `active` | 当前激活皮肤 ID | `SK001` |
| `registry.SKxxx` | 皮肤 ID → 文件夹名 | `registry.SK001: SK001_default` |

### 皮肤 skin.yaml 键

| 键 | 说明 | 示例 |
|---|---|---|
| `id` | 皮肤 ID（与文件夹前缀一致） | `SK001` |
| `name` | 显示名 | `默认皮肤` |
| `version` | 版本号 | `1` |
| `welcome_msg` | 启动欢迎语 | `欢迎使用...` |
| `art_file` | 艺术文件名 | `01_welcome.txt` |
| `style` | 风格描述 | `简洁` |

---

## 二、创建新皮肤

### 步骤 1：询问偏好

依次询问用户（等回答再问下一个）：

1. **皮肤叫什么名字？**（如"极简""二次元""学术"）
2. **想要什么风格的欢迎语？**（一句话描述，如"正式""轻松""热血"）
3. **有现成的 ASCII 艺术吗？**（有则提供文件，无则用默认或生成）

### 步骤 2：生成皮肤内容

- 根据用户偏好生成欢迎语（`welcome_msg`）
- 若用户提供了 ASCII 艺术，存为艺术文件；否则复制默认 `01_welcome.txt` 并修改
- 确定风格描述（`style`）

### 步骤 3：创建皮肤文件夹

1. 分配皮肤 ID：查注册表，最大编号 +1（如 `SK002`）
2. 创建文件夹：`main/skin/SKxxx_名称/`
3. 写入 `skin/skin/SKxxx_名称/skin.yaml`：
   ```yaml
   id: SKxxx
   name: <用户起的名字>
   version: 1
   welcome_msg: <生成的欢迎语>
   art_file: 01_welcome.txt
   style: <风格描述>
   ```
4. 放入艺术文件

### 步骤 4：登记注册表

在 `main/skin/skin.yaml` 中追加一行：
```yaml
registry.SKxxx: SKxxx_名称
```

### 步骤 5：验证

运行 `70_tools/t2ag_doctor.py`，确认 0 FAIL。

---

## 三、切换皮肤

1. 读 `main/skin/skin.yaml`，确认目标皮肤在注册表中
2. 修改 `active:` 行为目标皮肤 ID
3. 运行 doctor 验证
4. 向用户展示新皮肤的欢迎语和艺术画面

---

## 四、doctor 校验规则

| 检查项 | 级别 | 规则 |
|---|---|---|
| active 皮肤存在 | FAIL | `active` 指向的皮肤 ID 在注册表中存在，且对应文件夹和 skin.yaml 存在 |
| 艺术文件存在 | FAIL | active 皮肤的 `art_file` 指向的文件实际存在 |
| 未登记皮肤 | WARN | `skin/` 下存在 `SK` 开头文件夹但未在注册表登记 |

---

## 五、纪律

- **皮肤不得携带教学语义**：欢迎语可以有性格，但不能包含影响教学行为的指令。
  防止外观文件变成第二个 overlay 后门。
- **零依赖原则**：skin.yaml 使用扁平 key: value 格式，不引入 PyYAML。
  doctor 用正则解析，保持"删了 venv 也能跑"的可移植性。
- **艺术文件不强制格式**：ASCII 艺术用 .txt，不用图片。保持纯文本、任何编辑器可读。

---

## 六、关联文件

- `main/skin/` —— 皮肤目录
- `main/skin/skin.yaml` —— 全局配置
- `main/skin/README.md` —— 皮肤目录说明
- `main/t2ag.md` —— 结构清单登记
- `main/70_tools/t2ag_doctor.py` —— 皮肤校验检查
- `main/50_playbook/first_run.md` —— 步骤 7 展示欢迎信息
