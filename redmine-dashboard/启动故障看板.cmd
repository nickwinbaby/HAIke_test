@echo off
setlocal
cd /d "%~dp0"
set AUTO_OPEN_BROWSER=1
"C:\Program Files\nodejs\node.exe" server.js
echo.
echo Dashboard service stopped.
pause
