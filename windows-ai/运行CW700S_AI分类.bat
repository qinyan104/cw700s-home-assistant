@echo off
chcp 65001 >nul
title CW700S 本地 AI 分类

set "AI_ROOT=D:\CW700S\AI"
set "PYTHON=%AI_ROOT%\.venv\Scripts\python.exe"
set "SCRIPT=%AI_ROOT%\cw700s_ai_classifier.py"

echo ==========================================
echo        CW700S 本地 AI 二次分类
echo ==========================================
echo.

if not exist "%PYTHON%" (
    echo [错误] 未找到 Python 环境：
    echo %PYTHON%
    echo.
    pause
    exit /b 1
)

if not exist "%SCRIPT%" (
    echo [错误] 未找到分类程序：
    echo %SCRIPT%
    echo.
    pause
    exit /b 1
)

cd /d "%AI_ROOT%"

echo 正在扫描新增的 ObjectMotion 录像……
echo 已分析过的录像会自动跳过。
echo 原始录像不会被移动、改名或删除。
echo.
echo 中途停止请按 Ctrl+C
echo.

"%PYTHON%" "%SCRIPT%"

set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo ==========================================
if "%EXIT_CODE%"=="0" (
    echo 分类任务已完成。
) else (
    echo 分类任务结束，退出代码：%EXIT_CODE%
)
echo ==========================================
echo.
pause

exit /b %EXIT_CODE%
