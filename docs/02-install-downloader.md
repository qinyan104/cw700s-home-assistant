# 02. 安装录像下载器

本章把下载器复制到 Home Assistant，完成配置检查，并手动执行一次完整同步。仓库默认位于 Windows `D:\CW700S\cw700s-home-assistant`，在 Home Assistant 中对应 `/media/Windows_CW700S/cw700s-home-assistant`。

## 安装前备份

先在 Home Assistant 的“设置 → 系统 → 备份”中创建备份。下面使用固定的 `.cw700s.bak` 名称，并在同名备份已存在时停止，避免覆盖上一次可用备份。后两项只在旧文件存在时执行：

```bash
test ! -e /config/configuration.yaml.cw700s.bak || { echo '配置备份已存在，请先改名保存'; exit 1; }
test ! -e /config/custom_components/cw700s_downloader.cw700s.bak || { echo '组件备份已存在，请先改名保存'; exit 1; }
test ! -e /config/cw700s_download.py.cw700s.bak || { echo '脚本备份已存在，请先改名保存'; exit 1; }

cp /config/configuration.yaml /config/configuration.yaml.cw700s.bak

if [ -d /config/custom_components/cw700s_downloader ]; then
  cp -r /config/custom_components/cw700s_downloader \
    /config/custom_components/cw700s_downloader.cw700s.bak
fi

if [ -f /config/cw700s_download.py ]; then
  cp /config/cw700s_download.py /config/cw700s_download.py.cw700s.bak
fi
```

## 复制自定义组件

复制前先确认扫描窗口。`custom_components/cw700s_downloader/__init__.py` 默认包含：

```python
INITIAL_DAYS = 35
INCREMENTAL_DAYS = 30
```

`full_scan: true` 使用 `INITIAL_DAYS`，只查询最近 35 天，不是不限时间扫描全部历史；日常 `full_scan: false` 使用 `INCREMENTAL_DAYS`，查询最近 30 天。需要其他窗口时，先修改仓库中的这两个常量，再复制组件。

在 Terminal & SSH 中执行：

```bash
mkdir -p /config/custom_components/cw700s_downloader
cp -r /media/Windows_CW700S/cw700s-home-assistant/custom_components/cw700s_downloader/* \
  /config/custom_components/cw700s_downloader/
```

确认组件的三个文件已经到位：

```bash
ls -la /config/custom_components/cw700s_downloader
```

应看到 `__init__.py`、`manifest.json` 和 `services.yaml`。

## 复制下载脚本

执行：

```bash
cp /media/Windows_CW700S/cw700s-home-assistant/home-assistant/cw700s_download.py \
  /config/cw700s_download.py
```

确认目标文件存在：

```bash
ls -l /config/cw700s_download.py
```

## 启用组件

用文件编辑器打开 `/config/configuration.yaml`，添加以下顶层集成项：

```yaml
cw700s_downloader:
```

这一行应顶格书写。不要为了添加它创建第二个 `homeassistant:` 块，也不要把它缩进现有的 `homeassistant:` 块内。

## 修改摄像头实体示例

使用上一章在“开发者工具 → 状态”中找到的实体 ID，替换后续操作里的：

```text
camera.your_cw700s
```

仓库保留的是公开占位值，不应提交自己的实体 ID。首次同步操作会通过 `entity_id` 明确传入真实实体；不要把小米账号、token、Cookie 或临时签名 URL 写进 YAML。

## 检查并重启 Home Assistant

每次修改配置后先检查，成功后再重启：

```bash
ha core check && ha core restart
```

`ha core check` 失败时，`&&` 会阻止重启。检查失败时保留错误信息，修正缩进、重复键或文件路径后重新检查。

## 手动执行首次完整同步

重启完成后，打开“开发者工具 → 操作”，切换到 YAML 编辑方式，填入以下操作，并把实体 ID 换成自己的：

```yaml
action: cw700s_downloader.sync
data:
  entity_id: camera.your_cw700s
  full_scan: true
```

执行一次即可。这里的“完整”是当前实现的 35 天首次窗口，不是小米云账号的无限历史；自动任务使用 30 天增量窗口，在下一章配置。同步过程中不要重复触发同一操作。

## 确认生成的录像与状态实体

回到“开发者工具 → 状态”，搜索：

```text
sensor.cw700s_sync_status
```

正常结果是该实体出现并显示同步进度。根据告警事件类型，MP4 文件会出现在 Windows 的 `D:\CW700S\PeopleMotion` 或 `D:\CW700S\ObjectMotion` 下。也可以从 Terminal & SSH 查看对应挂载目录：

```bash
find /media/Windows_CW700S/PeopleMotion /media/Windows_CW700S/ObjectMotion \
  -type f -name '*.mp4' 2>/dev/null
```

首次同步处理到至少一条云告警录像时，也完成真正的 Home Assistant Core FFmpeg 验收。以状态实体持续更新、最终停止处理，并至少在有云告警的类别目录中出现 MP4 为正常结果。若 FFmpeg 查找或媒体处理失败，查看 `sensor.cw700s_sync_status` 的错误属性和“设置 → 系统 → 日志”；Terminal & SSH 应用中的 `ffmpeg -version` 不能替代这项检查。

下载过程使用的小米云临时签名 URL 属于敏感信息，绝不能分享到仓库、Issue、聊天记录或公开日志中。

## 常见错误

- 找不到 `cw700s_downloader.sync`：确认组件目录内有三个文件、`configuration.yaml` 中存在顶层 `cw700s_downloader:`，然后重新执行 `ha core check` 和重启。
- `ha core check` 失败：先检查 YAML 缩进和重复键；无法立即修正时，按回滚步骤恢复备份，不要带着失败配置重启。
- `sensor.cw700s_sync_status` 出现但没有录像：确认传入的是自己的 CW700S 实体，并重新执行 `ls -la /media/Windows_CW700S` 检查 SMB 挂载。
- 写入时报权限或只读错误：回到 Windows 共享权限和 Home Assistant 网络存储设置，修正后再同步。
- FFmpeg 查找或媒体处理失败：查看 `sensor.cw700s_sync_status` 的错误属性和 Home Assistant Core 日志，不要用 Terminal & SSH 应用容器中的命令结果判断 Core 状态。
- 小米云访问失败：在 Xiaomi Miot 集成中检查登录状态；排错时不要发布临时签名 URL、Cookie 或账号信息。

## 回滚

如果组件已经开始同步，先在“开发者工具 → 操作”执行 `cw700s_downloader.stop`。然后在 Terminal & SSH 中恢复安装前文件。

下面的命令会恢复安装前已有的组件和脚本；没有对应备份时，只删除本教程新安装的文件：

```bash
if [ -d /config/custom_components/cw700s_downloader.cw700s.bak ]; then
  rm -r /config/custom_components/cw700s_downloader
  cp -r /config/custom_components/cw700s_downloader.cw700s.bak \
    /config/custom_components/cw700s_downloader
else
  rm -r /config/custom_components/cw700s_downloader
fi

if [ -f /config/cw700s_download.py.cw700s.bak ]; then
  cp /config/cw700s_download.py.cw700s.bak /config/cw700s_download.py
else
  rm -f /config/cw700s_download.py
fi

cp /config/configuration.yaml.cw700s.bak /config/configuration.yaml
ha core check && ha core restart
```

回滚只替换 Home Assistant 侧安装文件，不会删除 Windows `D:\CW700S\PeopleMotion` 或 `D:\CW700S\ObjectMotion` 中已经下载的录像。
