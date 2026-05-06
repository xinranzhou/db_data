#!/bin/bash
# 源码环境一键安装脚本 (macOS/Linux)

echo "=================================="
echo "DP采集器 - 源码环境安装"
echo "=================================="
echo ""

# 检查 Python
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python3.11 >/dev/null 2>&1; then
    PYTHON_CMD="python3.11"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ 未找到 Python 3"
    echo "请先安装 Python 3.11+: https://www.python.org/downloads/"
    exit 1
fi

echo "✅ 找到 Python: $($PYTHON_CMD --version)"
echo ""

# 运行安装脚本
"$PYTHON_CMD" install.py

echo ""
echo "按任意键退出..."
read -n 1
