# 06. 排错与回滚

先找到发生问题的阶段，只执行对应的最小检查。保留错误原文和发生步骤，但公开求助前必须按本章末尾的隐私清单脱敏。

## VMware 中没有 64 位 Linux

关闭 VMware，进入电脑 BIOS/UEFI，启用 Intel VT-x、Intel Virtualization Technology、SVM 或 AMD-V。不同主板名称不同。

重新进入 VMware 后，应能选择 **Other Linux 5.x kernel 64-bit**。不要通过关闭 Windows 安全功能来碰运气；先确认硬件虚拟化本身已经启用。

## VMware 报找不到 VMDK

确认虚拟机已经关闭，然后检查虚拟机目录：

1. HAOS 的 `.vmdk` 文件已从压缩包完整解压；
2. 文件本身位于虚拟机目录，不是外层文件夹；
3. 文件名与 VMware 配置引用一致，本教程使用 `home-assistant.vmdk`；
4. `.vmx` 中包含 `firmware = "efi"`。

版本变化时以 Home Assistant 的 [Windows 虚拟机安装页](https://www.home-assistant.io/installation/windows/) 为准。

## Home Assistant 页面打不开

先看 VMware 控制台是否已完成启动。如果 `http://homeassistant.local:8123` 无法解析，改用控制台显示的 IP：

```text
http://<Home Assistant IP>:8123
```

仍无法访问时，确认 VMware 网卡为 **Bridged**，只桥接 Windows 实际联网的物理网卡。优先用有线网络排除 Wi-Fi 桥接问题。

## HACS 搜索不到

按顺序确认：

1. **Get HACS** 应用已经完成下载；
2. Home Assistant 已重启；
3. 浏览器已强制刷新或清除缓存；
4. “设置 → 设备与服务 → 添加集成”中搜索的是 `HACS`。

HACS 当前 HAOS 安装方式见 [官方说明](https://www.hacs.xyz/docs/use/download/download/)。

## 只有 Xiaomi Miio，没有 Xiaomi Miot

本项目需要第三方 **Xiaomi Miot**，不是 Home Assistant 内置的 Xiaomi Miio。先在 Terminal & SSH 中检查：

```bash
test -d /config/custom_components/xiaomi_miot \
  && echo "xiaomi_miot 已安装" \
  || echo "未找到 xiaomi_miot"
```

显示“未找到”时，回到 [01. 通过 HACS 安装 Xiaomi Miot](01-environment.md#通过-hacs-安装-xiaomi-miot)。安装后必须重启 Home Assistant，再到“设置 → 设备与服务 → 添加集成”搜索 **Xiaomi Miot**。

## Home Assistant 找不到教程仓库

在 Terminal & SSH 中执行：

```bash
test -f /media/Windows_CW700S/cw700s-home-assistant/README.md \
  && echo "仓库路径正确" \
  || echo "仓库路径错误"
```

路径错误时检查：

- Windows 解压目录是否仍叫 `cw700s-home-assistant-main`；
- 仓库是否真的位于 `D:\CW700S`；
- Home Assistant 网络存储名是否严格为 `Windows_CW700S`。

## 找不到同步操作或状态实体

在 Terminal & SSH 中执行：

```bash
ls -la /config/custom_components/cw700s_downloader
ls -l /config/cw700s_download.py
grep -n '^cw700s_downloader:' /config/configuration.yaml
ha core check
```

组件目录应包含 `__init__.py`、`manifest.json` 和 `services.yaml`。配置键必须顶格书写。检查通过后运行：

```bash
ha core restart
```

重启后仍缺失时，查看“设置 → 系统 → 日志”中的 `cw700s_downloader` 加载错误。

## 同步完成但没有 MP4

依次确认：

1. 传入的是自己的 CW700S 摄像头实体；
2. 该实体来自 Xiaomi Miot；
3. Xiaomi Miot 已启用云连接；
4. Xiaomi Home 中最近 35 天至少有一条可播放的云告警录像；
5. `sensor.cw700s_sync_status` 的 `last_error` 没有报错。

没有近期告警时，先制造一次能正常上报的移动告警，等待录像出现在 Xiaomi Home，再执行一次 `full_scan: true`。

## FFmpeg 查找或媒体处理失败

查看 `sensor.cw700s_sync_status` 的错误属性和 Home Assistant Core 日志。Terminal & SSH 应用与 Home Assistant Core 是不同容器，因此应用中的 `ffmpeg -version` 不能证明下载器可用。

保留错误类型即可；小米云返回的完整 M3U8 或签名 URL 不得公开。

## SMB 不可用或只读

在 Home Assistant 的“设置 → 系统 → 存储”中确认网络存储仍挂载为 `/media/Windows_CW700S`。然后运行：

```bash
ls -la /media/Windows_CW700S
touch /media/Windows_CW700S/.cw700s-write-test
rm /media/Windows_CW700S/.cw700s-write-test
```

`touch` 失败时检查 Windows 是否开机、共享账号是否有写权限，以及 VMware 是否仍使用桥接网络。未恢复挂载前不要反复启动下载任务。

已经安装健康监控时，也可以运行：

```bash
python3 /config/cw700s_health.py
```

`share_online` 和 `share_writable` 应为 `true`。

## ha core check 失败

不要执行 `ha core restart`。先读取检查输出中的文件和行号，修正缩进、重复键或路径后再次运行：

```bash
ha core check
```

无法修正时，使用对应章节保存的备份回滚。恢复配置不会删除 Windows 上已有录像。

## 最近录像卡片显示 unknown

依次确认：

1. `/config/www/cw700s-recent-card.js` 已复制；
2. 仪表板资源中已注册 `/local/cw700s-recent-card.js`；
3. 资源类型为 JavaScript 模块；
4. 浏览器缓存已清除并重新加载页面。

`/local/` 对应磁盘上的 `/config/www/`，两个字符串不同是正常现象。

## PowerShell 提示脚本未进行数字签名

不要降低整台 Windows 电脑的执行策略。日常分类可以直接双击：

```text
D:\CW700S\AI\运行CW700S_AI分类.bat
```

也可以直接运行 Python：

```powershell
& 'D:\CW700S\AI\.venv\Scripts\python.exe' 'D:\CW700S\AI\cw700s_ai_classifier.py'
```

文件来自可信仓库副本时，可以只解除目标脚本的下载标记：

```powershell
Unblock-File -LiteralPath 'D:\CW700S\AI\run_ai_classifier.ps1'
Unblock-File -LiteralPath 'D:\CW700S\AI\show_recent_results.ps1'
```

## AI 出现 Invalid NAL unit size

`Invalid NAL unit size` 或 `Error splitting the input into NAL units` 来自异常 HEVC 录像。当前分类器会把单条录像解码放入带超时的子进程；失败片段写入 SQLite 后继续处理下一条。

不要移动或删除原片，也不要换回旧分类脚本。

## AI 看起来卡住

`--video-timeout` 默认是 30 秒。先等待该时限，再观察下一条进度和最终失败计数。已经完成的结果会逐条写入 SQLite，中断不会清空已有结果。

只有超过配置时限后进度仍不继续，才中断当前任务。

## supported_features: 0 且没有流地址

这表示摄像头实体没有向 Home Assistant 暴露实时流。本项目不逆向实时直播，也不提供绕过设备权限的方法；实时查看请使用 Xiaomi Home。

云告警录像下载与实时流是两条独立路径。没有直播不代表告警录像下载失败。

## 回滚入口

每章的回滚步骤默认折叠在文末：

- [01. 环境与存储回滚](01-environment.md#回滚)
- [02. 下载器回滚](02-install-downloader.md#回滚)
- [03. 自动化与仪表板回滚](03-automation-and-dashboard.md#回滚)
- [04. 健康监控回滚](04-health-monitoring.md#回滚)
- [05. 本地 AI 回滚](05-local-ai.md#回滚)

先停止正在运行的同步或 AI 任务，再执行对应回滚。任何回滚都不应删除 `D:\CW700S\PeopleMotion` 或 `D:\CW700S\ObjectMotion` 中的原始录像。

## 发布日志前的隐私检查

公开求助前删除或遮盖：

- 完整 M3U8 URL 和签名查询字符串；
- access token、Cookie、账号和密码；
- 设备 ID、真实摄像头实体 ID；
- 家庭公网或内网 IP；
- Windows 与 SMB 用户名；
- `D:\CW700S\AI\previews` 中未经遮盖的画面；
- 未脱敏日志。

只保留复现问题所需的错误类型、脱敏路径、版本和时间顺序。
