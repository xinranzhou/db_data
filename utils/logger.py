#!/usr/bin/env python3
"""日志工具模块。优先使用 loguru，不存在时回退到标准库 logging。"""

import logging
import sys
from pathlib import Path

log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

try:
    from loguru import logger

    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )
    logger.add(
        log_dir / "automation_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",
        retention="7 days",
        compression="zip",
    )
except Exception:  # pragma: no cover - fallback path depends on env
    logger = logging.getLogger("auto_ocr")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
        )

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        file_handler = logging.FileHandler(log_dir / "automation_fallback.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


def setup_logger():
    """初始化日志系统"""
    logger.info("日志系统初始化完成")
    return logger


__all__ = ["logger", "setup_logger"]
