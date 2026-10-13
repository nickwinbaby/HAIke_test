@echo off
chcp 65001 >nul
cd /d "%~dp0"
py "wifi_hotspot_gui.py"
if errorlevel 1 pause
