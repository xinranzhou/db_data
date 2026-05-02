#!/usr/bin/env python3
"""
重试处理器
提供装饰器实现重试机制
"""

import time
import functools
from typing import Callable
from utils.logger import logger
from config.settings import Settings


class RetryHandler:
    """重试机制处理器"""

    @staticmethod
    def with_retry(max_attempts: int = None,
                   backoff_factor: float = None,
                   initial_wait: float = None):
        """
        重试装饰器

        Args:
            max_attempts: 最大重试次数
            backoff_factor: 退避因子
            initial_wait: 初始等待时间（秒）

        Returns:
            装饰器函数
        """
        max_attempts = max_attempts or Settings.RETRY['max_attempts']
        backoff_factor = backoff_factor or Settings.RETRY['backoff_factor']
        initial_wait = initial_wait or Settings.RETRY['initial_wait']

        def decorator(func: Callable):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                wait_time = initial_wait

                for attempt in range(1, max_attempts + 1):
                    try:
                        result = func(*args, **kwargs)
                        if result:
                            return result
                        else:
                            if attempt < max_attempts:
                                logger.warning(
                                    f"{func.__name__} 失败，"
                                    f"第 {attempt}/{max_attempts} 次尝试，"
                                    f"等待 {wait_time:.1f}秒后重试"
                                )
                                time.sleep(wait_time)
                                wait_time *= backoff_factor
                            else:
                                logger.error(f"{func.__name__} 达到最大重试次数")
                                return False

                    except Exception as e:
                        if attempt < max_attempts:
                            logger.error(
                                f"{func.__name__} 异常: {e}，"
                                f"第 {attempt}/{max_attempts} 次尝试，"
                                f"等待 {wait_time:.1f}秒后重试"
                            )
                            time.sleep(wait_time)
                            wait_time *= backoff_factor
                        else:
                            logger.error(f"{func.__name__} 达到最大重试次数，异常: {e}")
                            raise

                return False

            return wrapper

        return decorator
