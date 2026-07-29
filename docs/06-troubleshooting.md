# 06. 排错

只处理下面已经在现有环境中遇到并验证过的情况。先保留错误原文和发生步骤，再执行对应的最小修复。

## PowerShell 提示脚本未进行数字签名

不要降低整台机器的执行策略。日常增量分类可以直接双击：

```text
D:\CW700S\AI\运行CW700S_AI分类.bat
```

也可以绕过 PowerShell 脚本，直接运行 Python：

```powershell
& 'D:\CW700S\AI\.venv\Scripts\python.exe' 'D:\CW700S\AI\cw700s_ai_classifier.py'
```

若文件来自可信的本仓库副本，可只解除目标脚本的下载标记：

```powershell
Unblock-File -LiteralPath 'D:\CW700S\AI\run_ai_classifier.ps1'
Unblock-File -LiteralPath 'D:\CW700S\AI\show_recent_results.ps1'
```

## 出现 Invalid NAL unit size 或 Error splitting the input into NAL units

这些错误来自异常录像的 HEVC 解码。当前 `cw700s_ai_classifier.py` 已采用顺序抽帧，并把单条录像的解码放入带超时的子进程。失败片段会以 `failed` 状态写入 SQLite，随后继续处理后面的录像；不需要移动或删除原片。

不要换回旧分类脚本。完成后查看摘要中的失败数，并保留失败记录供后续重试。

## AI 看起来卡住

当前 `--video-timeout` 默认是 30 秒。先等待这 30 秒，让子进程退出或被终止；随后检查下一条 `[当前/总数]` 进度行和最终“失败”计数。单条坏录像不应阻止后续录像继续。

如果启动时显式修改了 `--video-timeout`，应等待所配置的秒数。只有进度在该时限后仍不继续时，才中断当前任务；已经逐条写入 SQLite 的结果仍可继续使用。

## SMB 不可用或只读

在 Home Assistant 的设置 → 系统 → 存储中确认 Windows 网络存储仍挂载为 `/media/Windows_CW700S`，并确认共享账号对目标目录有写权限。然后运行：

```bash
ls -la /media/Windows_CW700S
python3 /config/cw700s_health.py
```

健康 JSON 中的 `share_online` 和 `share_writable` 应为 `true`。未恢复挂载前不要重复启动下载任务。

## ha core check 失败

不要执行 `ha core restart`。先阅读检查输出指向的文件和行号；若不能立即修正，恢复安装章节中记录的配置备份，再次执行：

```bash
ha core check
```

只有检查成功后再重启。恢复配置不会删除 Windows 上已有的录像。

## 最近录像卡片显示 unknown

依次确认：

1. `/config/www/cw700s-recent-card.js` 已复制；
2. 设置 → 仪表板 → 资源中已注册 `/local/cw700s-recent-card.js`，类型为 JavaScript 模块；
3. 清除 Home Assistant 前端缓存；
4. 重新加载页面。

资源 URL 和磁盘路径不是同一个字符串：`/local/` 对应 `/config/www/`。

## supported_features: 0 且没有流地址

这表示当前摄像头实体没有向 Home Assistant 暴露实时流。这个公开仓库不尝试逆向实时直播，也不提供绕过设备权限的方法；实时查看请使用 Xiaomi Home。录像告警下载与实体是否提供实时流是两条独立路径。

## 发布日志前的隐私检查

公开求助前删除或遮盖以下内容：

- 完整 M3U8 URL；
- 签名查询字符串；
- access token；
- Cookie；
- 设备 ID；
- 小米账号数据；
- `D:\CW700S\AI\previews` 中未经遮盖的摄像头画面；
- 未脱敏日志。

只保留复现问题必需的错误类型、脱敏路径和时间顺序。
