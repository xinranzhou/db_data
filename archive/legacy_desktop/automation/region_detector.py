#!/usr/bin/env python3
"""
区域识别器
识别所有可选区域的坐标
策略：预定义区域名称 + 模板匹配定位
"""

from typing import List, Dict
from utils.logger import logger


class RegionDetector:
    """区域识别器"""

    def __init__(self, matcher, clicker, regions: List[str]):
        """
        Args:
            matcher: TemplateMatcher实例
            clicker: ClickSimulator实例
            regions: 预定义区域名称列表
        """
        self.matcher = matcher
        self.clicker = clicker
        self.regions = regions
        self.detected_regions = []

        logger.info(f"区域识别器初始化完成，预定义区域数: {len(regions)}")

    def detect_all_regions(self) -> List[Dict]:
        """
        检测所有区域的坐标

        Returns:
            [
                {'name': '黄浦区', 'center': (x, y), 'confidence': 0.85},
                {'name': '徐汇区', 'center': (x, y), 'confidence': 0.82},
                ...
            ]
        """
        logger.info("开始识别所有区域")

        detected_regions = []

        for i, region_name in enumerate(self.regions):
            # 方案1: 使用区域文字模板
            template = f"region_{region_name}.png"
            match = self.matcher.find_best_match(template, threshold=0.7)

            if match:
                detected_regions.append({
                    'name': region_name,
                    'center': match.center,
                    'confidence': match.confidence
                })
                logger.info(f"识别到区域: {region_name}, 置信度: {match.confidence:.3f}")
            else:
                # 方案2: 使用固定坐标偏移（备选）
                # 假设区域按垂直排列，间距60像素
                base_x, base_y = 200, 300  # 第一个区域的坐标
                offset_y = i * 60
                detected_regions.append({
                    'name': region_name,
                    'center': (base_x, base_y + offset_y),
                    'confidence': 0.0  # 标记为估算坐标
                })
                logger.warning(f"区域 {region_name} 使用估算坐标")

        self.detected_regions = detected_regions
        logger.info(f"共识别到 {len(detected_regions)} 个区域")
        return detected_regions

    def click_region(self, region_name: str) -> bool:
        """
        点击指定区域

        Args:
            region_name: 区域名称

        Returns:
            是否成功
        """
        # 如果还没有识别过，先识别
        if not self.detected_regions:
            self.detect_all_regions()

        for region in self.detected_regions:
            if region['name'] == region_name:
                x, y = region['center']
                logger.info(f"点击区域: {region_name} at ({x}, {y})")
                return self.clicker.click(x, y)

        logger.error(f"未找到区域: {region_name}")
        return False

    def get_regions(self) -> List[str]:
        """
        获取所有区域名称

        Returns:
            区域名称列表
        """
        return self.regions
