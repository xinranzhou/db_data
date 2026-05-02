@echo off
REM 一键安装启动脚本 (Windows)

echo ==================================
echo DP采集器 - 一键安装
echo ==================================
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未找到 Python
    echo 请先安装 Python 3.8+: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ 找到 Python
python --version
echo.

REM 运行安装脚本
python install.py

echo.
pause
