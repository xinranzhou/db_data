#!/usr/bin/env python3
"""
点击模拟器
支持PyAutoGUI（PC）和ADB（Android）两种模式
"""

import pyautogui
import random
import time
from typing import Tuple, Optional
from utils.logger import logger
from config.settings import Settings


class ClickSimulator:
    """人类化点击模拟器"""

    def __init__(self,
                 adb_device=None,
                 random_offset_range: int = None,
                 min_delay: float = None,
                 max_delay: float = None):
        """
        Args:
            adb_device: ADBDevice实例，如果提供则使用ADB模式
            random_offset_range: 随机偏移范围（像素）
            min_delay: 最小延迟（秒）
            max_delay: 最大延迟（秒）
        """
        self.adb_device = adb_device
        self.use_adb = adb_device is not None
        self.random_offset_range = random_offset_range or Settings.RANDOMIZATION['click_offset_range']
        self.min_delay = min_delay or Settings.DELAYS['click_min']
        self.max_delay = max_delay or Settings.DELAYS['click_max']

        if not self.use_adb:
            pyautogui.PAUSE = 0.1
            pyautogui.FAILSAFE = True

        mode = "ADB" if self.use_adb else "PyAutoGUI"
        logger.info(f"点击模拟器初始化完成，模式: {mode}，随机偏移范围: ±{self.random_offset_range}px")

    def click(self, x: int, y: int, random_offset: bool = True) -> bool:
        """
        模拟人类点击

        Args:
            x, y: 点击坐标
            random_offset: 是否添加随机偏移

        Returns:
            是否成功
        """
        try:
            # 添加随机偏移
            if random_offset:
                offset_x = random.randint(-self.random_offset_range, self.random_offset_range)
                offset_y = random.randint(-self.random_offset_range, self.random_offset_range)
                x += offset_x
                y += offset_y

            if self.use_adb:
                # ADB模式
                success = self.adb_device.tap(x, y)
            else:
                # PyAutoGUI模式
                duration = random.uniform(0.1, 0.3)
                pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)
                time.sleep(random.uniform(0.05, 0.15))
                pyautogui.click(x, y)
                success = True

            # 点击后延迟
            self.add_human_delay()

            logger.info(f"点击坐标: ({x}, {y})")
            return success

        except Exception as e:
            logger.error(f"点击失败: {e}")
            return False

    def double_click(self, x: int, y: int) -> bool:
        """
        双击

        Args:
            x, y: 点击坐标

        Returns:
            是否成功
        """
        try:
            if self.use_adb:
                # ADB模式：连续点击两次
                self.adb_device.tap(x, y)
                time.sleep(0.1)
                self.adb_device.tap(x, y)
            else:
                pyautogui.doubleClick(x, y)

            self.add_human_delay()
            logger.info(f"双击坐标: ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"双击失败: {e}")
            return False

    def swipe(self, start: Tuple[int, int], end: Tuple[int, int],
              duration: float = 0.5) -> bool:
        """
        模拟滑动操作

        Args:
            start: 起点坐标 (x, y)
            end: 终点坐标 (x, y)
            duration: 滑动时长（秒）

        Returns:
            是否成功
        """
        try:
            if self.use_adb:
                # ADB模式
                duration_ms = int(duration * 1000)
                success = self.adb_device.swipe(start[0], start[1], end[0], end[1], duration_ms)
            else:
                # PyAutoGUI模式
                pyautogui.moveTo(start[0], start[1], duration=0.1)
                time.sleep(0.05)
                pyautogui.drag(
                    end[0] - start[0],
                    end[1] - start[1],
                    duration=duration,
                    button='left'
                )
                success = True

            self.add_human_delay()
            logger.info(f"滑动: {start} -> {end}")
            return success

        except Exception as e:
            logger.error(f"滑动失败: {e}")
            return False

    def add_human_delay(self, min_ms: float = None, max_ms: float = None):
        """
        添加随机延迟模拟人类操作

        Args:
            min_ms: 最小延迟（秒）
            max_ms: 最大延迟（秒）
        """
        min_delay = min_ms if min_ms is not None else self.min_delay
        max_delay = max_ms if max_ms is not None else self.max_delay
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
