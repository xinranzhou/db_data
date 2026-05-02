#!/usr/bin/env python3
"""
模板匹配封装
封装已有的get_target_pos.py，提供面向对象接口
"""

import cv2
import time
from typing import List, Optional, Tuple
from pathlib import Path
from get_target_pos import get_target_pos
from utils.logger import logger


class Match:
    """匹配结果封装"""

    def __init__(self, rect, center, confidence, scale):
        self.rect = rect  # (x, y, w, h)
        self.center = center  # (x, y)
        self.confidence = confidence
        self.scale = scale

    @property
    def x(self) -> int:
        """中心点X坐标"""
        return self.center[0]

    @property
    def y(self) -> int:
        """中心点Y坐标"""
        return self.center[1]

    def __repr__(self):
        return f"Match(center={self.center}, confidence={self.confidence:.3f}, scale={self.scale:.2f})"


class TemplateMatcher:
    """模板匹配器（封装get_target_pos）"""

    def __init__(self, template_dir: str, screen_capture):
        """
        Args:
            template_dir: 模板图片目录
            screen_capture: ScreenCapture实例
        """
        self.template_dir = Path(template_dir)
        self.screen_capture = screen_capture
        self.cache = {}  # 缓存模板图片路径

        if not self.template_dir.exists():
            self.template_dir.mkdir(parents=True, exist_ok=True)
            logger.warning(f"模板目录不存在，已创建: {self.template_dir}")

        logger.info(f"模板匹配器初始化完成，模板目录: {self.template_dir}")

    def find_template(self,
                      template_name: str,
                      threshold: float = 0.7,
                      roi: Optional[Tuple[int, int, int, int]] = None) -> List[Match]:
        """
        查找模板

        Args:
            template_name: 模板文件名（如 'food_button.png'）
            threshold: 匹配阈值
            roi: 感兴趣区域 (x, y, w, h)

        Returns:
            匹配结果列表
        """
        template_path = self.template_dir / template_name

        if not template_path.exists():
            logger.error(f"模板不存在: {template_path}")
            return []

        # 截取当前屏幕
        if roi:
            target_img = self.screen_capture.capture_region(*roi)
            temp_target = "/tmp/target_roi.png"
        else:
            target_img = self.screen_capture.capture_screen()
            temp_target = "/tmp/target_full.png"

        cv2.imwrite(temp_target, target_img)

        # 调用已有的模板匹配函数
        try:
            matches = get_target_pos(str(template_path), temp_target, threshold)

            # 转换为Match对象
            result = [
                Match(m['rect'], m['center'], m['confidence'], m['scale'])
                for m in matches
            ]

            logger.info(f"模板 '{template_name}' 找到 {len(result)} 个匹配")
            return result

        except Exception as e:
            logger.error(f"模板匹配失败: {e}")
            return []

    def find_best_match(self,
                        template_name: str,
                        threshold: float = 0.7,
                        roi: Optional[Tuple[int, int, int, int]] = None) -> Optional[Match]:
        """
        返回最佳匹配（置信度最高）

        Args:
            template_name: 模板文件名
            threshold: 匹配阈值
            roi: 感兴趣区域

        Returns:
            最佳匹配结果，未找到返回None
        """
        matches = self.find_template(template_name, threshold, roi)
        return matches[0] if matches else None

    def wait_for_template(self,
                          template_name: str,
                          timeout: float = 5.0,
                          threshold: float = 0.7,
                          interval: float = 0.5,
                          roi: Optional[Tuple[int, int, int, int]] = None) -> Optional[Match]:
        """
        等待模板出现

        Args:
            template_name: 模板文件名
            timeout: 超时时间（秒）
            threshold: 匹配阈值
            interval: 检测间隔（秒）
            roi: 感兴趣区域

        Returns:
            匹配结果，超时返回None
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            matches = self.find_template(template_name, threshold, roi)
            if matches:
                logger.info(f"模板 '{template_name}' 出现")
                return matches[0]
            time.sleep(interval)

        logger.warning(f"等待模板 '{template_name}' 超时 ({timeout}秒)")
        return None

    def template_exists(self,
                        template_name: str,
                        threshold: float = 0.7,
                        roi: Optional[Tuple[int, int, int, int]] = None) -> bool:
        """
        检查模板是否存在

        Args:
            template_name: 模板文件名
            threshold: 匹配阈值
            roi: 感兴趣区域

        Returns:
            是否存在
        """
        matches = self.find_template(template_name, threshold, roi)
        return len(matches) > 0
