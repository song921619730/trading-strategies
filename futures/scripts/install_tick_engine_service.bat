@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Tick Engine Auto-Start Installer
echo  Run AS ADMINISTRATOR
echo ========================================
echo.

set TASK_NAME=HermesTickEngine
set PYTHON=C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe
set SCRIPT=F:\AIcoding_space\Hermes\strategies\futures\scripts\tick_engine.py

echo [1/3] Deleting old task...
schtasks /delete /tn %TASK_NAME% /f >nul 2>&1

echo [2/3] Creating task...
schtasks /create /tn %TASK_NAME% /tr "'%PYTHON%' '%SCRIPT%'" /sc ONLOGON /it /f /rl HIGHEST

if %ERRORLEVEL% equ 0 (
    echo [3/3] SUCCESS
    echo.
    echo Task: %TASK_NAME%
    echo Trigger: User logon
    echo.
) else (
    echo [3/3] FAILED (error %ERRORLEVEL%)
    echo Right-click this file ^> Run as administrator
)

echo.
pause
