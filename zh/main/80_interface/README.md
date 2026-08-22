# skin —— 启动欢迎画面皮肤系统

> 位置：`main/80_interface/`。存放启动时展示的 ASCII 艺术与皮肤配置。
> 皮肤是**外观组件**，不是新层——没有自己的验收逻辑，只是配置+素材。

## 目录结构

```
main/80_interface/
  skin.yaml              ← 全局配置（active 指针 + 注册表）
  README.md              ← 本文件
  SK001_default/         ← 默认皮肤
    skin.yaml            ← 皮肤元数据（id/名称/欢迎语/艺术文件/风格）
    01_welcome.txt       ← Skeleton 安装模板默认的 t2AG 字母画
    02_inori.txt         ← 备用角色字符画
    03_inori_2.txt       ← Main/Lite 当前选中的 Inori 角色字符画
    04_inori_3.txt       ← 备用角色字符画
```

## 配置格式

使用**扁平 YAML 子集**（`key: value`），doctor 用正则解析，零依赖（不需要 PyYAML）。

### 全局 `main/80_interface/skin.yaml`

| 键 | 说明 |
|---|---|
| `active` | 当前激活的皮肤 ID |
| `registry.SKxxx` | 皮肤 ID → 文件夹名映射 |

### 皮肤 `SKxxx/skin.yaml`

| 键 | 说明 |
|---|---|
| `id` | 皮肤 ID（与文件夹名前缀一致） |
| `name` | 皮肤显示名 |
| `version` | 皮肤版本号 |
| `welcome_msg` | 启动欢迎语 |
| `art_file` | 欢迎画面艺术文件名（相对本皮肤目录） |
| `style` | 风格描述 |

## 启动逻辑

`main/t2ag.md`「3.0 启动欢迎信息」要求首次初始化和日常接管都执行一次：

1. 读 `main/80_interface/skin.yaml` → 获取 `active` 值
2. 查注册表 → 获取 active 皮肤文件夹名
3. 读 `SKxxx/skin.yaml` → 获取 `welcome_msg` 和 `art_file`
4. 输出欢迎语 + 原样展示艺术文件内容 + 版本号

Main/Lite 当前显示 `03_inori_2.txt`；Skeleton 首次安装显示 `01_welcome.txt`。这是批准的
发行角色分叉，不得用 Skeleton 默认标识画覆盖 Main 已选择的角色画。

## 皮肤管理

创建、切换、校验流程详见 `50_playbook/skin_playbook.md`（core-playbook）。
