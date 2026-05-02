#!/bin/bash
# 一键安装启动脚本 (macOS/Linux)

echo "=================================="
echo "DP采集器 - 一键安装"
echo "=================================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python 3"
    echo "请先安装 Python 3.8+: https://www.python.org/downloads/"
    exit 1
fi

echo "✅ 找到 Python: $(python3 --version)"
echo ""

# 运行安装脚本
python3 install.py

echo ""
echo "按任意键退出..."
read -n 1
