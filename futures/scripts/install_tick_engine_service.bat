@echo off
chcp 65001 >nul

echo ========================================
echo   Tick Engine 开机自启安装脚本
echo   请以管理员身份运行
echo ========================================
echo.

set TASK_NAME=HermesTickEngine
set PYTHON=C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe
set SCRIPT=F:\AIcoding_space\Hermes\strategies\futures\scripts\tick_engine.py

echo [1/3] 删除旧任务（如果有）...
schtasks /delete /tn %TASK_NAME% /f >nul 2>&1

echo [2/3] 创建开机自启任务...
schtasks /create ^
  /tn %TASK_NAME% ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\"" ^
  /sc ONLOGON ^
  /it ^
  /f ^
  /rl HIGHEST

if %ERRORLEVEL% equ 0 (
    echo [3/3] ✅ 创建成功！
    echo.
    echo 任务名称: %TASK_NAME%
    echo 启动方式: 用户登录时自动启动
    echo 运行用户: 当前用户
    echo 工作目录: F:\AIcoding_space\Hermes\strategies\futures\scripts
    echo.
    echo 验证: 运行 schtasks /query /tn %TASK_NAME%
    echo 立即测试: 运行 F:\AIcoding_space\Hermes\strategies\futures\scripts\start_tick_engine.bat
) else (
    echo [3/3] ❌ 创建失败！错误码: %ERRORLEVEL%
    echo.
    echo 可能原因:
    echo - 没有以管理员权限运行
    echo - 用户名不是 gj
    echo.
    echo 试试: 右键本文件 -> \"以管理员身份运行\"
)

echo.
pause
