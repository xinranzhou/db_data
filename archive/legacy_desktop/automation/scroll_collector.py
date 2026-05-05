#!/usr/bin/env python3
"""
滚动采集器
固定向下滑动 + 识别"加载完了"
"""

import time
from utils.logger import logger
from config.settings import Settings


class ScrollCollector:
    """滚动采集器"""

    def __init__(self, clicker, matcher, scroll_config: dict):
        """
        Args:
            clicker: ClickSimulator实例
            matcher: TemplateMatcher实例
            scroll_config: 滚动配置
        """
        self.clicker = clicker
        self.matcher = matcher
        self.scroll_distance = scroll_config.get('distance', Settings.SCROLL['distance'])
        self.scroll_duration = scroll_config.get('duration', Settings.SCROLL['duration'])
        self.loading_done_template = scroll_config.get('loading_done_template')
        self.loading_done_threshold = scroll_config.get('loading_done_threshold', 0.8)
        self.max_scrolls = Settings.SCROLL['max_scrolls']

        logger.info(
            f"滚动采集器初始化完成，"
            f"滚动距离: {self.scroll_distance}px, "
            f"时长: {self.scroll_duration}s"
        )

    def collect_region_data(self, region_name: str) -> bool:
        """
        采集单个区域的数据

        流程：
        1. 循环滚动
        2. 每次滚动后识别"加载完了"
        3. 如果识别到，退出循环

        Args:
            region_name: 区域名称

        Returns:
            是否成功
        """
        logger.info(f"开始采集区域: {region_name}")

        scroll_count = 0

        while scroll_count < self.max_scrolls:
            # 1. 向下滑动
            success = self._scroll_down()
            if not success:
                logger.error("滑动失败")
                break

            scroll_count += 1
            logger.info(f"第 {scroll_count} 次滑动")

            # 2. 等待页面稳定
            time.sleep(0.5)

            # 3. 识别"加载完了"
            if self._is_loading_done():
                logger.info(f"区域 {region_name} 加载完成，共滑动 {scroll_count} 次")
                return True

        logger.warning(f"区域 {region_name} 达到最大滑动次数 ({self.max_scrolls})")
        return False

    def _scroll_down(self) -> bool:
        """
        向下滑动固定距离

        Returns:
            是否成功
        """
        # 获取屏幕尺寸
        screen_width = Settings.SCREEN['width']
        screen_height = Settings.SCREEN['height']

        # 起点：屏幕中心下方2/3处
        start_x = screen_width // 2
        start_y = screen_height * 2 // 3

        # 终点：向上滑动（屏幕内容向下）
        end_x = start_x
        end_y = start_y - self.scroll_distance

        return self.clicker.swipe(
            (start_x, start_y),
            (end_x, end_y),
            duration=self.scroll_duration
        )

    def _is_loading_done(self) -> bool:
        """
        识别是否出现"加载完了"文案

        Returns:
            是否加载完成
        """
        if not self.loading_done_template:
            logger.warning("未配置加载完成模板")
            return False

        match = self.matcher.find_best_match(
            self.loading_done_template,
            threshold=self.loading_done_threshold
        )

        return match is not None
