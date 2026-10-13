@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0source\build_terminal_split_distributed.ps1"
if errorlevel 1 (
    echo.
    echo Distributed build failed. Close the running application and try again.
    pause
    exit /b 1
)
echo.
echo Distributed build completed successfully.
pause
