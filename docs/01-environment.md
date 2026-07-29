# 01. 连接 CW700S、Windows 存储与教程仓库

完成本章后，Home Assistant 能通过 **Xiaomi Miot** 找到 CW700S，并能读写 Windows 的 `D:\CW700S`。教程仓库也会位于 `D:\CW700S\cw700s-home-assistant`。

开始前应已完成 [00. 在 VMware 中安装 Home Assistant OS](00-install-haos-vmware.md)。

## 先认清两个容易混淆的集成

本项目依赖第三方集成 **Xiaomi Miot**，其目录是：

```text
/config/custom_components/xiaomi_miot
```

它不是 Home Assistant 内置的 **Xiaomi Miio**。即使“设置 → 设备与服务”中已经有 Xiaomi Miio，也不能跳过 Xiaomi Miot；下载器会直接使用 Xiaomi Miot 提供的摄像头实体与小米云连接。

## 创建 Home Assistant 备份

**操作位置：Home Assistant 界面**

打开“设置 → 系统 → 备份”，创建一个完整备份。名称可以使用：

```text
安装 CW700S 前
```

正常结果：备份列表中出现刚创建的备份。HACS 与 Xiaomi Miot 都属于第三方组件，遇到启动问题时先恢复备份，不要在失败状态下继续叠加修改。

## 安装 HACS

**操作位置：Home Assistant 界面**

本节按 HACS 当前的 [Home Assistant OS 官方流程](https://www.hacs.xyz/docs/use/download/download/) 编写；这条安装路径尚未在本项目的现有运行环境中回归验证。

1. 打开“设置 → 应用 → 安装应用”。
2. 打开应用商店右上角菜单，选择“存储库”。
3. 添加下面的第三方应用存储库：

```text
https://github.com/hacs/addons
```

4. 回到应用商店，找到 **Get HACS**，安装并启动。
5. 打开 **Get HACS** 日志，按日志提示完成下载。
6. 打开“设置 → 系统”，重启 Home Assistant。

重启后按 HACS 的 [初始配置说明](https://hacs.xyz/docs/use/configuration/basic/) 完成集成配置：

1. 强制刷新浏览器页面或清除缓存。
2. 打开“设置 → 设备与服务”，选择右下角“添加集成”。
3. 搜索并选择 **HACS**。
4. 阅读并确认界面中的提示。
5. 复制 GitHub 设备代码，打开界面给出的 `github.com/login/device` 链接。
6. 登录自己的 GitHub 账号，输入设备代码并授权 HACS。
7. 回到 Home Assistant，完成配置。

正常结果：“设置 → 设备与服务”中出现 HACS，侧边栏也能打开 HACS 页面。GitHub 设备代码是一次性授权信息，不要发到 Issue、截图或聊天记录。

HACS 搜索不到时，跳到 [HACS 搜索不到](06-troubleshooting.md#hacs-搜索不到)。

## 通过 HACS 安装 Xiaomi Miot

**操作位置：Home Assistant 界面**

1. 打开 HACS，进入集成页面。
2. 搜索 **Xiaomi Miot**，仓库作者应为 `al-one`。
3. 下载该仓库。需要复现实测环境时选择 `1.1.4`；使用更高版本时记录版本号。
4. 下载完成后重启 Home Assistant。
5. 打开“设置 → 设备与服务 → 添加集成”。
6. 搜索并选择 **Xiaomi Miot**，不要选择 Xiaomi Miio。
7. 使用自己的小米账号添加设备，服务器地区必须与 Xiaomi Home（米家）应用一致。
8. 为 CW700S 使用云连接模式，或在 Xiaomi Miot 选项中确认已启用 Miot cloud。

上游安装与配置细节见 [Xiaomi Miot 官方仓库](https://github.com/al-one/hass-xiaomi-miot)。

账号、密码、token、Cookie 和设备标识只保存在集成本地配置中。本教程不要求提取或公开设备 token。

正常结果：“设置 → 设备与服务”中出现 **Xiaomi Miot**。如果只有 Xiaomi Miio，跳到 [只有 Xiaomi Miio，没有 Xiaomi Miot](06-troubleshooting.md#只有-xiaomi-miio没有-xiaomi-miot)。

## 确认 CW700S 摄像头实体

**操作位置：Home Assistant 界面**

打开“开发者工具 → 状态”，搜索 `camera.`，找到属于 CW700S 的摄像头实体。记录完整实体 ID，后文统一使用公开占位值：

```text
camera.your_cw700s
```

后续每次看到这个占位值，都必须替换为自己的实体 ID。不要复制其他人的实体名。

本项目验证的 MIoT 型号是：

```text
isa.camera.hlzoom
```

如果设备页显示其他型号，先按不兼容处理。不要假定其他摄像机使用相同的事件、加密方式或录像格式。

找不到 CW700S 实体时，先回到 Xiaomi Miot 检查小米账号地区、设备筛选和云连接，不要继续安装下载器。

## 创建 Windows 归档目录

**操作位置：Windows PowerShell**

```powershell
New-Item -ItemType Directory -Force 'D:\CW700S'
```

正常结果：文件资源管理器中能打开 `D:\CW700S`。

## 获取本教程仓库

### 主路径：GitHub Download ZIP

**操作位置：Windows 浏览器和文件资源管理器**

1. 打开 [qinyan104/cw700s-home-assistant](https://github.com/qinyan104/cw700s-home-assistant)。
2. 选择 **Code → Download ZIP**。
3. 解压 ZIP，把得到的 `cw700s-home-assistant-main` 文件夹移动到 `D:\CW700S`。
4. 将文件夹重命名为 `cw700s-home-assistant`。

正常结果：下面的文件存在：

```text
D:\CW700S\cw700s-home-assistant\README.md
```

如果目标文件夹已经存在，不要覆盖。先确认它是否是旧版教程仓库，再决定备份、更新或改名。

### 可选路径：git clone

已安装 Git for Windows 的用户可以执行：

```powershell
Set-Location 'D:\CW700S'
git clone https://github.com/qinyan104/cw700s-home-assistant.git
```

以后更新：

```powershell
git -C 'D:\CW700S\cw700s-home-assistant' pull --ff-only
```

如果 `git` 命令不存在，使用上面的 ZIP 主路径即可，不必为了本教程额外学习 Git。

## 共享 D:\CW700S

**操作位置：Windows 文件资源管理器**

1. 右键 `D:\CW700S`，打开“属性 → 共享 → 高级共享”。
2. 共享该文件夹，共享名使用 `CW700S`。
3. 给一个专用于家庭网络访问的 Windows 账号授予读取和写入权限。

不要把 SMB 用户名或密码写入教程、截图或仓库。Windows 宿主机休眠或关机时，Home Assistant 将无法访问这个共享。

## 在 Home Assistant 中添加网络存储

**操作位置：Home Assistant 界面**

按 Home Assistant 官方 [Network storage](https://www.home-assistant.io/common-tasks/os/#network-storage) 说明，打开“设置 → 系统 → 存储”，添加网络存储：

| 字段 | 值 |
|---|---|
| 名称 | `Windows_CW700S` |
| 用途 | 媒体 |
| 服务器 | Windows 主机名或家庭网络地址 |
| 协议 | Samba/Windows（CIFS） |
| 远程共享 | `CW700S` |
| 用户名、密码 | 上一节授权的 Windows 账号 |

名称必须是 `Windows_CW700S`，这样挂载路径才会是代码使用的：

```text
/media/Windows_CW700S
```

## 验证共享与仓库

**操作位置：Terminal & SSH**

```bash
ls -la /media/Windows_CW700S
test -f /media/Windows_CW700S/cw700s-home-assistant/README.md
touch /media/Windows_CW700S/.cw700s-write-test
rm /media/Windows_CW700S/.cw700s-write-test
```

正常结果：命令没有报错，目录中能看到 `cw700s-home-assistant`。只有读、写和仓库路径全部通过，才继续安装下载器。

仓库不存在时跳到 [Home Assistant 找不到教程仓库](06-troubleshooting.md#home-assistant-找不到教程仓库)；写入失败时跳到 [SMB 不可用或只读](06-troubleshooting.md#smb-不可用或只读)。

## 本章验收

- “开发者工具 → 状态”中找到自己的 CW700S 摄像头实体；
- 使用的是 Xiaomi Miot，不是 Xiaomi Miio；
- `/media/Windows_CW700S` 可读写；
- `/media/Windows_CW700S/cw700s-home-assistant/README.md` 存在。

全部满足后，继续 [02. 安装下载器并取得第一条 MP4](02-install-downloader.md)。

## 回滚

<details>
<summary>不继续安装时如何回滚</summary>

在 Home Assistant 的“设置 → 系统 → 存储”中移除 `Windows_CW700S` 网络存储；需要时在 Windows 中停止共享 `D:\CW700S`。

移除挂载或停止共享不会删除 `D:\CW700S` 中的文件。除非已经备份并明确要清理数据，否则不要删除该目录。

</details>
