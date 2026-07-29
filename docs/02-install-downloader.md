# 02. 安装下载器并取得第一条 MP4

完成本章后，Windows 的 `D:\CW700S\PeopleMotion` 或 `D:\CW700S\ObjectMotion` 中会出现至少一条 MP4，Home Assistant 中会出现 `sensor.cw700s_sync_status`。

开始前必须通过 [01. 连接 CW700S、Windows 存储与教程仓库](01-environment.md) 的四项验收。

## 安装前备份

**操作位置：Home Assistant 界面**

先在“设置 → 系统 → 备份”中创建完整备份。

**操作位置：Terminal & SSH**

下面的命令不会覆盖同名备份；如果备份已存在，会直接停止：

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

## 确认扫描范围

下载器默认使用：

```python
INITIAL_DAYS = 35
INCREMENTAL_DAYS = 30
```

- 首次 `full_scan: true` 查询最近 35 天；
- 日常 `full_scan: false` 查询最近 30 天；
- “完整扫描”不是不限时间的全部历史。

初次安装先保持默认值。确实需要其他范围时，在复制组件前修改 `custom_components/cw700s_downloader/__init__.py`。

## 复制下载器

**操作位置：Terminal & SSH**

```bash
mkdir -p /config/custom_components/cw700s_downloader
cp -r /media/Windows_CW700S/cw700s-home-assistant/custom_components/cw700s_downloader/* \
  /config/custom_components/cw700s_downloader/
cp /media/Windows_CW700S/cw700s-home-assistant/home-assistant/cw700s_download.py \
  /config/cw700s_download.py
```

立即检查：

```bash
ls -la /config/custom_components/cw700s_downloader
ls -l /config/cw700s_download.py
```

正常结果：组件目录中存在 `__init__.py`、`manifest.json` 和 `services.yaml`，下载脚本也存在。

## 启用组件

**操作位置：Home Assistant 文件编辑器**

打开 `/config/configuration.yaml`，添加下面的顶层键：

```yaml
cw700s_downloader:
```

这一行必须顶格书写。不要创建第二个 `homeassistant:`，也不要把它缩进现有的 `homeassistant:` 中。

**操作位置：Terminal & SSH**

```bash
ha core check && ha core restart
```

`ha core check` 失败时，`&&` 会阻止重启。先按错误提示修正 YAML；不要跳过检查强制重启。

## 确认服务和状态实体

重启完成后，打开“开发者工具 → 状态”，搜索：

```text
sensor.cw700s_sync_status
```

再打开“开发者工具 → 操作”，确认能找到：

```text
cw700s_downloader.sync
```

两者都出现才继续。如果缺少其中一项，直接查看 [找不到同步操作或状态实体](06-troubleshooting.md#找不到同步操作或状态实体)。

## 手动下载第一条录像

**操作位置：Home Assistant 开发者工具 → 操作**

切换到 YAML 编辑方式，粘贴下面内容，并把实体 ID 换成自己的：

```yaml
action: cw700s_downloader.sync
data:
  entity_id: camera.your_cw700s
  full_scan: true
```

执行一次后等待状态实体停止处理。同步过程中不要重复触发；组件会拒绝重叠任务。

如果最近 35 天没有任何云告警，先在摄像头前制造一次可正常上报到 Xiaomi Home 的移动告警，等待告警录像出现在小米云，再重新执行同步。

## 验证第一条 MP4

**操作位置：Terminal & SSH**

```bash
find /media/Windows_CW700S/PeopleMotion /media/Windows_CW700S/ObjectMotion \
  -type f -name '*.mp4' 2>/dev/null
```

正常结果：至少输出一条 MP4 路径。Windows 中对应位置是：

```text
D:\CW700S\PeopleMotion
D:\CW700S\ObjectMotion
```

这一步同时验证了 Xiaomi Miot 云连接、Home Assistant Core 中的 FFmpeg、SMB 写权限和下载器。Terminal & SSH 应用里的 `ffmpeg -version` 不能替代这项端到端检查，因为应用与 Home Assistant Core 是不同容器。

## 核心路径完成

满足以下两项即完成首次成功：

- `sensor.cw700s_sync_status` 完成一次同步；
- Windows 中出现至少一条可播放的 MP4。

现在可以停止，也可以继续 [03. 自动同步与仪表板](03-automation-and-dashboard.md)。健康监控和本地 AI 都是可选增强，不影响已经完成的下载流程。

小米云临时签名 URL 属于敏感信息。不要把完整地址放进 GitHub、Issue、截图、聊天记录或公开日志。

## 回滚

<details>
<summary>展开回滚步骤</summary>

如果组件仍在同步，先在“开发者工具 → 操作”执行 `cw700s_downloader.stop`。然后在 Terminal & SSH 中运行：

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

回滚只替换 Home Assistant 侧安装文件，不会删除 Windows 中已经下载的录像。

</details>
