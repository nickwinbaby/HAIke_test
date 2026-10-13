@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0source\build_terminal_split.ps1"
if errorlevel 1 (
    echo.
    echo Build failed. Close the running application and try again.
    pause
    exit /b 1
)
echo.
echo Build completed successfully.
pause
