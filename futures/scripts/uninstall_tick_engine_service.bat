@echo off
chcp 65001 >nul

echo ========================================
echo   Tick Engine 开机自启移除脚本
echo   请以管理员身份运行
echo ========================================
echo.

set TASK_NAME=HermesTickEngine

schtasks /delete /tn %TASK_NAME% /f

if %ERRORLEVEL% equ 0 (
    echo ✅ 已移除开机自启任务: %TASK_NAME%
) else (
    echo ❌ 移除失败。可能任务不存在或权限不足。
    echo 试试: 右键本文件 -> "以管理员身份运行"
)

echo.
pause
