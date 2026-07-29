param(
    [int]$Limit = 0,
    [switch]$Recheck,
    [switch]$SavePreview,
    [switch]$Cpu
)

$ErrorActionPreference = "Stop"

$aiRoot = "D:\CW700S\AI"
$python = Join-Path $aiRoot ".venv\Scripts\python.exe"
$script = Join-Path $aiRoot "cw700s_ai_classifier.py"

if (-not (Test-Path $python)) {
    throw "没有找到 AI 虚拟环境：$python"
}

if (-not (Test-Path $script)) {
    throw "没有找到分类程序：$script"
}

$arguments = @($script)

if ($Limit -gt 0) {
    $arguments += @("--limit", "$Limit")
}

if ($Recheck) {
    $arguments += "--recheck"
}

if ($SavePreview) {
    $arguments += "--save-preview"
}

if ($Cpu) {
    $arguments += "--cpu"
}

& $python @arguments
exit $LASTEXITCODE
