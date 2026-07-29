# 01. 环境准备

完成本章后，Home Assistant 能看到 CW700S 实体并读写 Windows 共享目录。FFmpeg 由下一章的首次同步在 Home Assistant Core 中验证。

## 最终目录与职责

Windows 和 Home Assistant 分工如下：

| 位置 | 职责 |
|---|---|
| Windows `D:\CW700S` | 保存告警录像；启用本地 AI 后，还保存 AI 数据库 |
| Home Assistant `/config` | 保存下载器组件、脚本和配置 |
| Home Assistant `/media/Windows_CW700S` | 通过 SMB 访问 Windows `D:\CW700S` |

Home Assistant 负责查询小米云事件、定时执行同步和展示状态；Windows 负责持久保存录像和可选的 AI 数据。FFmpeg 在 Home Assistant 侧完成下载、解密和合并，输出写入 SMB 挂载目录。

## Home Assistant OS 与 Terminal & SSH

本教程以 Home Assistant OS 为准。进入“设置 → 应用 → 安装应用”，安装 **Terminal & SSH**，启动后打开其 Web 界面。旧版界面可能把“应用”称为“加载项”。后续所有 Bash 命令都在这个终端中执行。

先确认两个目录可见：

```bash
ls -ld /config /media
```

正常结果是两行目录信息。如果没有 `/config`，说明当前终端不是 Home Assistant OS 的加载项终端，不要继续复制文件。

## 安装并登录 Xiaomi Miot

按照 [Xiaomi Miot 官方仓库](https://github.com/al-one/hass-xiaomi-miot) 的安装说明添加集成，并按其云模式说明登录自己的小米账号。下载器需要 Xiaomi Miot 提供的设备与云事件访问能力。

账号、密码、token、Cookie 和设备标识只应保存在集成要求的本地配置中。不要把它们写入本仓库，也不要在截图、Issue 或日志片段中公开。本教程不要求提取或发布设备 token。

## 确认 CW700S 摄像头实体

打开“开发者工具 → 状态”，搜索 `camera.`，找到属于 CW700S 设备的摄像头实体。记录完整实体 ID，例如教程占位值：

```text
camera.your_cw700s
```

后续操作中的 `camera.your_cw700s` 必须替换为刚找到的实体 ID。不要直接复制其他人的实体名；即使设备型号相同，Home Assistant 生成的实体 ID 也可能不同。

本教程验证的 MIoT 型号是 `isa.camera.hlzoom`。如果设备页显示其他型号，先按不兼容处理，不要假定事件、录像格式或加密方式相同。

## 创建 Windows D:\CW700S

在 Windows PowerShell 中创建归档目录：

```powershell
New-Item -ItemType Directory -Force 'D:\CW700S'
```

然后在文件资源管理器中右键 `D:\CW700S`，打开“属性 → 共享 → 高级共享”，共享该文件夹，建议共享名使用 `CW700S`。给一个专用于家庭网络访问的 Windows 账号授予读取和写入权限。

不要把 SMB 用户名或密码写进教程文件。下一节只在 Home Assistant 的网络存储表单中输入这些凭据。

## 将 Windows 共享挂载为 /media/Windows_CW700S

按照 Home Assistant 官方的 [Network storage](https://www.home-assistant.io/common-tasks/os/#network-storage) 说明，打开“设置 → 系统 → 存储”，添加网络存储，并填写：

| 字段 | 值 |
|---|---|
| 名称 | `Windows_CW700S` |
| 用途 | 媒体 |
| 服务器 | Windows 主机名或家庭网络地址 |
| 协议 | Samba/Windows（CIFS） |
| 远程共享 | `CW700S` |
| 用户名、密码 | 上一节授权的 Windows 账号 |

保存后，Home Assistant 将该存储显示为 `/media/Windows_CW700S`。初学者路径要求名称严格使用 `Windows_CW700S`，因为下载器、健康脚本和 AI 状态脚本都固定引用这个挂载路径。回到 Terminal & SSH，执行：

```bash
ls -la /media/Windows_CW700S
touch /media/Windows_CW700S/.cw700s-write-test
rm /media/Windows_CW700S/.cw700s-write-test
```

三条命令都成功，才表示下载器能够列目录并写入文件。若 `touch` 报只读或权限错误，先修正 Windows 共享权限和 Home Assistant 网络存储凭据。

如果确实要使用其他挂载路径，必须在复制文件前同时修改：集成 `__init__.py` 中的 `DESTINATION_ROOT`、健康脚本中的 `ROOT`、AI 状态脚本中的 `DB_PATH`，以及教程里所有包含 `/media/Windows_CW700S` 的复制、检查和回滚命令。只改网络存储名称会让下载和状态检查指向不同目录。

## 确认 FFmpeg

下载器依赖 FFmpeg 下载、解密并合并录像，但 **Terminal & SSH** 应用和 Home Assistant Core 是不同的容器。在应用终端运行 `ffmpeg -version` 不能证明 Core 中的 FFmpeg 可用，因此本章不把它作为验收门槛。

下一章的首次同步处理到录像时，会在 Home Assistant Core 中实际调用 FFmpeg。调用失败时，检查 `sensor.cw700s_sync_status` 的错误属性和“设置 → 系统 → 日志”中的 `cw700s_downloader` 或 FFmpeg 错误。

## 本章验收

在 Terminal & SSH 中检查挂载目录：

```bash
ls -la /media/Windows_CW700S
```

正常结果：命令列出挂载目录，且已在“开发者工具 → 状态”中记录自己的 CW700S 摄像头实体。FFmpeg 验收留到下一章的首次同步。

## 回滚

如果不继续安装，在“设置 → 系统 → 存储”中移除 `Windows_CW700S` 网络存储；需要时再在 Windows 中停止共享 `D:\CW700S`。

移除挂载或停止共享不会删除 `D:\CW700S` 中的文件。除非已经另行备份并明确要清理数据，否则不要删除该目录。
