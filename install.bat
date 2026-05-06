@echo off
REM 源码环境一键安装脚本 (Windows)

echo ==================================
echo DP采集器 - 源码环境安装
echo ==================================
echo.

REM 检查 Python
set PYTHON_CMD=
set PYTHON_ARGS=
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
) else (
    py --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py
    )
)

if "%PYTHON_CMD%"=="" (
    echo ❌ 未找到 Python
    echo 请先安装 Python 3.11+: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ 找到 Python
%PYTHON_CMD% %PYTHON_ARGS% --version
echo.

REM 运行安装脚本
%PYTHON_CMD% %PYTHON_ARGS% install.py

echo.
pause
