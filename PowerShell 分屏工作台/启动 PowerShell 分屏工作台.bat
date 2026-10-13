@echo off
set "APP=%~dp0dist\powershell 分屏工作台 V1.3.1 - Mangetic - 2026-9-11.exe"
if not defined APP (
    echo [Error] Cannot locate the V1.3.1 build in the dist folder.
    echo Run source\build_terminal_split.ps1 first.
    pause
    exit /b 1
)
if not exist "%APP%" (
    echo [Error] Cannot find: %APP%
    echo Run source\build_terminal_split.ps1 first.
    pause
    exit /b 1
)
start "" "%APP%"
