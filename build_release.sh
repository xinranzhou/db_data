#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================="
echo "DP采集器 - 构建环境检查"
echo "=================================="

if command -v git >/dev/null 2>&1; then
  echo "✅ 找到 Git: $(git --version)"
else
  echo "⚠️ 未找到 Git"
  echo "   如果只是当前目录已有完整源码，可以继续打包。"
  echo "   如果需要 git clone / git pull，请先安装 Git: https://git-scm.com/downloads"
fi

PYTHON_CMD=""
if command -v python3.11 >/dev/null 2>&1; then
  PYTHON_CMD="python3.11"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
  echo "❌ 未找到 Python 3"
  echo "   请先安装 Python 3.11+: https://www.python.org/downloads/"
  exit 1
fi

if ! "$PYTHON_CMD" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)' >/dev/null 2>&1; then
  echo "❌ Python 版本不受支持: $($PYTHON_CMD --version 2>&1)"
  echo "   本地构建当前固定使用 Python 3.11.x"
  exit 1
fi

echo "✅ 找到 Python: $($PYTHON_CMD --version 2>&1)"
echo ""

"$PYTHON_CMD" bootstrap_build.py "$@"
