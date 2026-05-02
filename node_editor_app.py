#!/usr/bin/env python3
"""
GUI节点编辑器启动入口
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

# 确保日志系统初始化
from utils.logger import setup_logger
setup_logger()

from gui.node_editor import main

if __name__ == '__main__':
    main()
