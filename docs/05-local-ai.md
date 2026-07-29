# 05. Windows 本地 AI 分类（可选）

本章在 Windows 本地分析已经归档的 `ObjectMotion` 录像。AI 是可选阶段；不安装它不会影响 Home Assistant 下载、归档或健康检查。

## 硬件与软件要求

- Windows 能读取 `D:\CW700S\ObjectMotion`；
- Python 3.11，可通过 `py -3.11` 启动；
- 首次安装依赖和下载模型时可访问对应的官方软件源；
- NVIDIA GPU 不是必需条件。现有环境在 RTX 3050 上验证，脚本也支持 CPU 模式。

分类程序默认只扫描 `D:\CW700S\ObjectMotion`，结果写入 `D:\CW700S\AI\cw700s_ai.db`。它不会移动、改名或删除原始录像。

## 复制 AI 文件

在 Windows PowerShell 中创建目标目录。复制前，下面的代码会为已经存在的四个运行文件创建 `.before_github_tutorial` 备份；若任一备份名已存在，它会在覆盖前停止：

```powershell
New-Item -ItemType Directory -Force 'D:\CW700S\AI' | Out-Null
$names = @(
    'cw700s_ai_classifier.py',
    '运行CW700S_AI分类.bat',
    'run_ai_classifier.ps1',
    'show_recent_results.ps1'
)
$backupSuffix = '.before_github_tutorial'
$conflicts = $names | Where-Object {
    Test-Path -LiteralPath ((Join-Path 'D:\CW700S\AI' $_) + $backupSuffix)
}
if ($conflicts) {
    throw '已有 .before_github_tutorial 备份；请改用 .before_github_tutorial.2 等未使用后缀'
}
foreach ($name in $names) {
    $target = Join-Path 'D:\CW700S\AI' $name
    if (Test-Path -LiteralPath $target) {
        Copy-Item -LiteralPath $target -Destination ($target + $backupSuffix)
    }
}
```

如果需要把 `$backupSuffix` 改成 `.before_github_tutorial.2`，记下该值，回滚时使用同一后缀。备份成功后复制仓库文件：

```powershell
Copy-Item 'D:\CW700S\cw700s-home-assistant\windows-ai\cw700s_ai_classifier.py' 'D:\CW700S\AI\'
Copy-Item 'D:\CW700S\cw700s-home-assistant\windows-ai\运行CW700S_AI分类.bat' 'D:\CW700S\AI\'
Copy-Item 'D:\CW700S\cw700s-home-assistant\windows-ai\run_ai_classifier.ps1' 'D:\CW700S\AI\'
Copy-Item 'D:\CW700S\cw700s-home-assistant\windows-ai\show_recent_results.ps1' 'D:\CW700S\AI\'
```

## 创建 Python 虚拟环境

```powershell
Set-Location 'D:\CW700S\AI'
py -3.11 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
```

正常结果是 `D:\CW700S\AI\.venv\Scripts\python.exe` 存在。后续命令都显式使用这个解释器，不依赖全局 Python 环境。

## 安装 Ultralytics、OpenCV 与 PyTorch

需要 GPU 时，先访问 PyTorch 官方 [Start Locally](https://pytorch.org/get-started/locally/) 页面，按当前 Windows、Pip、Python 和 CUDA 环境生成安装命令，并用虚拟环境中的 Python 执行。不要复制未经确认的 CUDA wheel 地址。

随后安装分类程序直接使用的包：

```powershell
& '.\.venv\Scripts\python.exe' -m pip install ultralytics opencv-python
```

安装完成后，`torch`、`cv2` 和 `ultralytics` 都应能从该虚拟环境导入。

## 检查 CUDA

```powershell
& '.\.venv\Scripts\python.exe' -c "import torch; print(torch.cuda.is_available())"
```

输出 `True` 时脚本会自动选择第一块 CUDA GPU；输出 `False` 时使用 CPU。若本应使用 NVIDIA GPU，请回到 PyTorch 官方页面选择与本机驱动兼容的安装命令，不要仅凭其他机器的 wheel URL 判断。

## 先测试 10 条录像

```powershell
& '.\.venv\Scripts\python.exe' '.\cw700s_ai_classifier.py' --limit 10 --save-preview
```

该命令最多处理 10 条待分析录像，并在 `D:\CW700S\AI\previews` 下保存检测预览。逐条结果会立即写入 SQLite；中途停止不会丢失已经完成的记录。

`D:\CW700S\AI\previews` 包含摄像头画面。不要把其中的图片未经遮盖就发布到 GitHub、帖子或问题日志。

常用参数与当前默认值：

- `--cpu`：强制使用 CPU；
- `--recheck`：重新分析所有录像，包括内容未变化且已成功分析的录像；
- `--confidence`：最低检测置信度，默认 `0.30`；
- `--video-timeout`：单条录像抽帧超时，默认 `30` 秒；
- `--limit`：本次最多分析的新录像数，默认 `0`，表示不限制。

`--cpu`、`--recheck` 和 `--save-preview` 默认都不启用；只在命令中明确写出时生效。

## 增量分析全部录像

```powershell
& '.\.venv\Scripts\python.exe' '.\cw700s_ai_classifier.py'
```

正常日常使用也可以双击 `运行CW700S_AI分类.bat`。脚本按文件路径、大小和修改时间识别未变化的成功记录，重复运行时会跳过它们；失败记录可在后续运行中重试。

## 查看最近结果

在 `D:\CW700S\AI` 中执行：

```powershell
& '.\show_recent_results.ps1'
```

输出包含分析时间、主分类、最高置信度和相对路径。需要限制行数时可用 `& '.\show_recent_results.ps1' -Top 10`。

## 接入 Home Assistant

先按 [04. 系统健康监控](04-health-monitoring.md) 启用 `/config/packages`。然后在 Home Assistant Terminal & SSH 中检查备份名并备份已有文件：

```bash
test ! -e /config/cw700s_ai_status.py.cw700s.bak || { echo '脚本备份已存在，请改用 .cw700s.bak.2'; exit 1; }
test ! -e /config/packages/cw700s_ai_package.yaml.cw700s.bak || { echo '配置包备份已存在，请改用 .cw700s.bak.2'; exit 1; }
[ ! -e /config/cw700s_ai_status.py ] || cp /config/cw700s_ai_status.py /config/cw700s_ai_status.py.cw700s.bak
[ ! -e /config/packages/cw700s_ai_package.yaml ] || cp /config/packages/cw700s_ai_package.yaml /config/packages/cw700s_ai_package.yaml.cw700s.bak
```

任何 `.cw700s.bak` 已存在时都不要覆盖；把两处检查、备份和后续回滚使用的后缀改为同一个未使用名称。完成备份后执行：

```bash
cp /media/Windows_CW700S/cw700s-home-assistant/home-assistant/scripts/cw700s_ai_status.py \
  /config/cw700s_ai_status.py
cp /media/Windows_CW700S/cw700s-home-assistant/home-assistant/packages/cw700s_ai_package.yaml \
  /config/packages/cw700s_ai_package.yaml
python3 /config/cw700s_ai_status.py
ha core check && ha core restart
```

JSON 输出应表明数据库可读。重启后，开发者工具 → 状态中应出现 `sensor.cw700s_ai_classification`。在仪表板新增手动卡片，粘贴 `home-assistant/dashboard/cw700s_ai_card.yaml`；卡片应显示总数、人物/车辆/动物相关计数、组合计数、未识别和失败数。

## 分类含义与局限

结果分为人物、车辆、动物、它们的组合，以及“未识别目标”。程序只抽取每条录像的三个位置并检查模型支持的目标类别；“未识别目标”只表示采样画面在当前模型和置信度下没有命中这些类别，不表示录像无用，也不应作为删除录像的依据。

分类数据库是派生数据。原始录像始终保留在 `D:\CW700S\ObjectMotion`，AI 程序不会移动、改名或删除它们。

## 回滚

先从仪表板删除 AI 卡片。下面的命令会恢复安装前已有的 Home Assistant 文件；没有备份时，只删除本章新安装的对应文件：

```bash
if [ -e /config/cw700s_ai_status.py.cw700s.bak ]; then
  cp /config/cw700s_ai_status.py.cw700s.bak /config/cw700s_ai_status.py
else
  rm -f /config/cw700s_ai_status.py
fi

if [ -e /config/packages/cw700s_ai_package.yaml.cw700s.bak ]; then
  cp /config/packages/cw700s_ai_package.yaml.cw700s.bak /config/packages/cw700s_ai_package.yaml
else
  rm -f /config/packages/cw700s_ai_package.yaml
fi

ha core check && ha core restart
```

使用了 `.cw700s.bak.2` 时，把回滚命令中的备份名改为该实际名称。

Windows 端停止运行批处理文件即可停用分类。若要撤销本章复制的四个运行文件，下面的代码会恢复有备份的旧文件，并只删除安装前不存在的文件：

```powershell
$names = @(
    'cw700s_ai_classifier.py',
    '运行CW700S_AI分类.bat',
    'run_ai_classifier.ps1',
    'show_recent_results.ps1'
)
$backupSuffix = '.before_github_tutorial'
foreach ($name in $names) {
    $target = Join-Path 'D:\CW700S\AI' $name
    $backup = $target + $backupSuffix
    if (Test-Path -LiteralPath $backup) {
        Copy-Item -LiteralPath $backup -Destination $target -Force
    } else {
        Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
    }
}
```

如果安装时使用了 `.before_github_tutorial.2`，先把回滚代码的 `$backupSuffix` 改为相同值。可以保留 `D:\CW700S\AI\cw700s_ai.db` 供以后继续增量分析；若决定删除数据库、预览或虚拟环境，先备份需要的结果，且不要删除 `D:\CW700S\ObjectMotion`。
