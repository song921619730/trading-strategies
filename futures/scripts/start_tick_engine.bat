@echo off
REM 启动统一 Tick Engine 守护进程
REM 运行在 Windows Python 下（需要 MT5 库）
REM 
REM 用法:
REM   start_tick_engine.bat           ← 前台运行
REM   start /B start_tick_engine.bat  ← 后台运行
REM

set PYTHON=C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe
set SCRIPT=F:\AIcoding_space\Hermes\strategies\futures\scripts\tick_engine.py

echo [StartTickEngine] Starting Tick Engine...
echo [StartTickEngine] Python: %PYTHON%
echo [StartTickEngine] Script: %SCRIPT%
echo.

%PYTHON% %SCRIPT%

echo.
echo [StartTickEngine] Tick Engine stopped.
pause
