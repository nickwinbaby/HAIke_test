@echo off
chcp 65001 >nul
echo ========================================
echo    FileOperationTool 构建工具
echo ========================================
echo.

python setup.py build

echo.
echo 构建完成!
echo 可执行文件位于 dist 目录
pause
