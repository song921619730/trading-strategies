@echo off
echo ========================================
echo  Tick Engine Auto-Start Remover
echo  Run AS ADMINISTRATOR
echo ========================================
echo.
schtasks /delete /tn HermesTickEngine /f
if %ERRORLEVEL% equ 0 (
    echo SUCCESS: Task HermesTickEngine removed
) else (
    echo FAILED: Try right-click ^> Run as administrator
)
echo.
pause
