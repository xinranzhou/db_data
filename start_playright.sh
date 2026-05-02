#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
  PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "未找到 Python 3，请先安装 Python 或创建项目虚拟环境。"
  exit 1
fi

echo "项目目录: $SCRIPT_DIR"
echo "Python: $PYTHON_BIN"
echo "启动点评详情补全..."

"$PYTHON_BIN" -m playright --mode playwright --run "$@"
