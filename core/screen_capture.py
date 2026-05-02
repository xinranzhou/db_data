#!/usr/bin/env python3
"""
截屏模块
支持PyAutoGUI（PC）和ADB（Android）两种模式
"""

import pyautogui
from PIL import Image
import numpy as np
import cv2
from typing import Tuple, Optional
from utils.logger import logger


class ScreenCapture:
    """跨平台截屏模块"""

    def __init__(self, adb_device=None, device_scale: float = 1.0):
        """
        Args:
            adb_device: ADBDevice实例，如果提供则使用ADB模式
            device_scale: 设备缩放比例（Retina屏为2.0）
        """
        self.adb_device = adb_device
        self.use_adb = adb_device is not None
        self.device_scale = device_scale

        if not self.use_adb:
            pyautogui.FAILSAFE = True

        mode = "ADB" if self.use_adb else "PyAutoGUI"
        logger.info(f"截屏模块初始化完成，模式: {mode}，设备缩放比例: {device_scale}")

    def capture_screen(self) -> np.ndarray:
        """
        截取全屏并转换为OpenCV格式

        Returns:
            BGR格式的numpy数组
        """
        try:
            if self.use_adb:
                # ADB模式
                screenshot_path = self.adb_device.screenshot('/tmp/adb_screenshot.png')
                if screenshot_path:
                    img_bgr = cv2.imread(screenshot_path)
                    logger.debug(f"ADB截取全屏成功，尺寸: {img_bgr.shape}")
                    return img_bgr
                else:
                    raise Exception("ADB截图失败")
            else:
                # PyAutoGUI模式
                screenshot = pyautogui.screenshot()
                img_rgb = np.array(screenshot)
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
                logger.debug(f"截取全屏成功，尺寸: {img_bgr.shape}")
                return img_bgr

        except Exception as e:
            logger.error(f"截取全屏失败: {e}")
            raise

    def capture_region(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        """
        截取指定区域（ROI优化）

        Args:
            x, y: 左上角坐标
            w, h: 宽度和高度

        Returns:
            BGR格式的numpy数组
        """
        try:
            if self.use_adb:
                # ADB模式：先截全屏再裁剪
                full_img = self.capture_screen()
                img_bgr = full_img[y:y+h, x:x+w]
                logger.debug(f"ADB截取区域成功: ({x}, {y}, {w}, {h})")
                return img_bgr
            else:
                # PyAutoGUI模式
                screenshot = pyautogui.screenshot(region=(x, y, w, h))
                img_rgb = np.array(screenshot)
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
                logger.debug(f"截取区域成功: ({x}, {y}, {w}, {h})")
                return img_bgr

        except Exception as e:
            logger.error(f"截取区域失败: {e}")
            raise

    def save_screenshot(self, path: str, region: Optional[Tuple[int, int, int, int]] = None) -> str:
        """
        保存截图用于调试

        Args:
            path: 保存路径
            region: 可选的区域 (x, y, w, h)

        Returns:
            保存的文件路径
        """
        try:
            if region:
                img = self.capture_region(*region)
            else:
                img = self.capture_screen()

            cv2.imwrite(path, img)
            logger.info(f"截图已保存: {path}")
            return path
        except Exception as e:
            logger.error(f"保存截图失败: {e}")
            raise

    def get_screen_size(self) -> Tuple[int, int]:
        """
        获取屏幕尺寸

        Returns:
            (width, height)
        """
        if self.use_adb:
            size = self.adb_device.get_screen_size()
            if size:
                return size
            else:
                logger.warning("无法获取ADB设备屏幕尺寸，使用默认值")
                return (1080, 2340)
        else:
            size = pyautogui.size()
            return size.width, size.height
