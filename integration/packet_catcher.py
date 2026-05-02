#!/usr/bin/env python3
"""
Rust抓包工具桥接
与Rust抓包工具通信
"""

import subprocess
import json
import time
from typing import Dict, Optional
from pathlib import Path
from utils.logger import logger


class PacketCatcher:
    """Rust抓包工具桥接"""

    def __init__(self, rust_config: dict):
        """
        Args:
            rust_config: Rust配置字典
        """
        self.rust_executable = Path(rust_config.get('command', './rust_collector'))
        self.data_dir = Path(rust_config.get('data_dir', './data'))
        self.timeout = rust_config.get('timeout', 300)
        self.process: Optional[subprocess.Popen] = None
        self.status_file = self.data_dir / "status.json"

        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Rust抓包工具桥接初始化完成，可执行文件: {self.rust_executable}")

    def start(self, region: str = None) -> bool:
        """
        启动Rust抓包工具

        Args:
            region: 可选的区域名称

        Returns:
            是否成功
        """
        try:
            # 检查可执行文件是否存在
            if not self.rust_executable.exists():
                logger.warning(f"Rust可执行文件不存在: {self.rust_executable}")
                logger.info("跳过Rust抓包工具启动")
                return True  # 不阻塞流程

            logger.info(f"启动Rust抓包工具")

            # 构建命令
            cmd = [str(self.rust_executable)]
            if region:
                cmd.extend(['--region', region])
            cmd.extend(['--output', str(self.data_dir)])

            # 启动进程
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            logger.info(f"Rust进程已启动: PID={self.process.pid}")
            return True

        except Exception as e:
            logger.error(f"启动Rust工具失败: {e}")
            return False

    def stop(self) -> bool:
        """
        停止Rust抓包工具

        Returns:
            是否成功
        """
        if self.process:
            logger.info("停止Rust抓包工具")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
                logger.info("Rust进程已停止")
            except subprocess.TimeoutExpired:
                logger.warning("Rust进程未响应，强制终止")
                self.process.kill()
            self.process = None
            return True
        return False

    def is_running(self) -> bool:
        """
        检查Rust进程是否运行中

        Returns:
            是否运行中
        """
        if self.process:
            return self.process.poll() is None
        return False

    def wait_for_completion(self, timeout: float = None) -> bool:
        """
        等待抓包完成

        Args:
            timeout: 超时时间（秒）

        Returns:
            是否成功
        """
        if not self.process:
            logger.warning("Rust进程未启动")
            return True

        timeout = timeout or self.timeout

        try:
            returncode = self.process.wait(timeout=timeout)

            if returncode == 0:
                logger.info("Rust抓包完成")
                return True
            else:
                logger.error(f"Rust进程异常退出: {returncode}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Rust抓包超时")
            self.stop()
            return False

    def get_status(self) -> Dict:
        """
        获取抓包状态（通过状态文件）

        Returns:
            状态字典
        """
        if self.status_file.exists():
            try:
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"读取状态文件失败: {e}")

        return {
            'status': 'unknown',
            'collected': 0,
            'progress': 0.0
        }
